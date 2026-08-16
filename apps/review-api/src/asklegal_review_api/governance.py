"""Atomic local Review-command adapter backed by the M6 Approval register."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING

from asklegal_application_runtime import (
    CommandOutcome,
    LocalAdapterError,
    LocalAdapterErrorCode,
    Principal,
    TokenType,
)
from asklegal_contracts import fingerprint
from asklegal_management_register_ports import (
    InMemoryApprovalRegister,
    ManifestSnapshot,
    ReviewerPrincipal,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class ReviewCommand:
    """One authenticated, optimistic, idempotent Review command."""

    command_id: str
    target: str
    expected_version: int
    body: Mapping[str, JsonValue]
    principal: Principal


class ReviewGovernanceService:
    """Atomically resolve commands and append their governance facts."""

    def __init__(
        self,
        approvals: InMemoryApprovalRegister,
        manifests: Mapping[str, ManifestSnapshot],
        *,
        local_time: str,
    ) -> None:
        """Create a no-network service over exact immutable proposal snapshots."""
        self.approvals = approvals
        self.manifests = dict(manifests)
        self._local_time = local_time
        self._lock = RLock()
        self._commands: dict[str, tuple[str, CommandOutcome]] = {}
        self._versions: dict[str, int] = {}

    def submit(self, command: ReviewCommand) -> CommandOutcome:
        """Apply or exactly replay one human governance command."""
        request_fingerprint = fingerprint(
            {
                "body": dict(command.body),
                "expected_version": command.expected_version,
                "subject": command.principal.subject,
                "target": command.target,
            }
        )
        with self._lock:
            prior = self._commands.get(command.command_id)
            if prior is not None:
                if prior[0] != request_fingerprint:
                    raise LocalAdapterError(LocalAdapterErrorCode.COMMAND_ID_CONFLICT)
                return CommandOutcome(
                    prior[1].command_id,
                    "EXACT_REPLAY",
                    prior[1].result_code,
                    prior[1].authoritative_version,
                    prior[1].result_ref,
                )
            current = self._versions.get(command.target, 0)
            if current != command.expected_version:
                raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
            result_code, result_ref = self._apply(command)
            version = current + 1
            outcome = CommandOutcome(
                command.command_id,
                "RESULT_RECORDED",
                result_code,
                version,
                result_ref,
            )
            self._versions[command.target] = version
            self._commands[command.command_id] = (request_fingerprint, outcome)
            return outcome

    def _apply(self, command: ReviewCommand) -> tuple[str, str]:
        principal = ReviewerPrincipal(
            command.principal.subject,
            command.principal.token_type is TokenType.DELEGATED_HUMAN,
            command.principal.roles,
        )
        action = _required_string(command.body, "action")
        reason_key = "comment" if action == "COMMENT" else "reason"
        reason = _required_string(command.body, reason_key)
        if action == "REVOKE":
            approval = self.approvals.get(command.target)
            if approval.decision.manifest_fingerprint != _required_string(
                command.body, "manifest_fingerprint"
            ):
                raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
            revoked = self.approvals.revoke(
                principal, command.target, reason=reason, at=self._local_time
            )
            return "REVOKED", revoked.decision.approval_id
        manifest = self.manifests[command.target]
        if action == "COMMENT":
            comment = self.approvals.comment(
                principal,
                manifest,
                section=_required_string(command.body, "review_section"),
                reason=reason,
                recorded_at=self._local_time,
            )
            return "COMMENTED", comment.comment_id
        decision = self.approvals.decide(
            principal,
            manifest,
            decision="APPROVED" if action == "APPROVE" else "REJECTED",
            reason=reason,
            decision_time=self._local_time,
        )
        return decision.decision.decision, decision.decision.approval_id

    def check(self) -> bool:
        """Report deterministic local readiness without changing state."""
        return bool(self.manifests)


def _required_string(body: Mapping[str, JsonValue], key: str) -> str:
    value = body.get(key)
    if type(value) is not str or not value:
        raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
    return value
