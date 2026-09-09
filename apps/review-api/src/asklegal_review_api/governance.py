"""Atomic local Review-command adapter backed by the M6 Approval register."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import RLock
from typing import TYPE_CHECKING, Protocol

from asklegal_application_runtime import (
    CommandOutcome,
    LocalAdapterError,
    LocalAdapterErrorCode,
    Principal,
    ProposalDetailProjection,
    TokenType,
)
from asklegal_contracts import SchemaRegistry, canonicalize, fingerprint
from asklegal_contracts.json_types import checked_json_value
from asklegal_management_register import (
    RegisteredApprovalTerminalCommand,
    RegisterEventCommand,
    V1CommandResult,
)
from asklegal_management_register_ports import (
    ApprovalError,
    ApprovalErrorCode,
    InMemoryApprovalRegister,
    ManifestSnapshot,
    ReviewerPrincipal,
)

from asklegal_review_api.registered_proposals import (
    ProposalProjectionError,
    validate_hk_v1_review_readiness,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")
_REVOCATION_VERSION = 2


@dataclass(frozen=True, slots=True)
class ReviewCommand:
    """One authenticated, optimistic, idempotent Review command."""

    command_id: str
    target: str
    expected_version: int
    body: Mapping[str, JsonValue]
    principal: Principal


class ReviewGovernance(Protocol):
    """Named-human command boundary consumed by the HTTP adapter."""

    def submit(self, command: ReviewCommand) -> CommandOutcome:
        """Apply or exactly replay one governance command."""
        ...

    def check(self) -> bool:
        """Perform a non-mutating readiness check."""
        ...


@dataclass(frozen=True, slots=True)
class ReviewAuthorityEvidence:
    """Current assignment plus immutable identity and authority evidence."""

    subject: str
    roles: frozenset[str]
    reviewer_identity_id: str
    reviewer_identity_fingerprint: str
    authority_evidence_id: str
    authority_evidence_fingerprint: str

    def __post_init__(self) -> None:
        """Reject a floating or malformed named-human authority claim."""
        if type(self.subject) is not str or not self.subject:
            message = "subject must be one exact non-empty string"
            raise TypeError(message)
        if type(self.roles) is not frozenset or any(type(item) is not str for item in self.roles):
            message = "roles must be one exact frozen string set"
            raise TypeError(message)
        for identity in (self.reviewer_identity_id, self.authority_evidence_id):
            if _IDENTIFIER.fullmatch(identity) is None:
                message = "authority identity must be register-issued"
                raise ValueError(message)
        for value in (
            self.reviewer_identity_fingerprint,
            self.authority_evidence_fingerprint,
        ):
            if _FINGERPRINT.fullmatch(value) is None:
                message = "authority evidence must be fingerprint-bound"
                raise ValueError(message)


class ReviewAuthoritySource(Protocol):
    """Current named-human assignment and immutable evidence lookup."""

    def current(self, subject: str) -> ReviewAuthorityEvidence | None:
        """Return current evidence for one stable subject, if assigned."""
        ...

    def check(self) -> bool:
        """Perform a non-mutating source readiness check."""
        ...


class ReviewDecisionWriter(Protocol):
    """Atomic generic Management Register command surface."""

    def record_event(self, command: RegisterEventCommand) -> V1CommandResult:
        """Commit or replay one immutable no-effect decision event."""
        ...


class ReviewProposalSource(Protocol):
    """Fully reread proposal detail required immediately before decision."""

    def detail(self, proposal_id: str) -> ProposalDetailProjection | None:
        """Return one exact complete proposal projection."""
        ...

    def check(self) -> bool:
        """Perform a non-mutating projection readiness check."""
        ...


class RegisteredReviewApprovalSource(Protocol):
    """Fully reread approved decision lookup for exact revocation."""

    def approved(self, approval_id: str) -> ProposalDetailProjection | None:
        """Return one exact approved proposal by Approval identity."""
        ...


class RegisteredReviewRevocationWriter(Protocol):
    """Atomic Review-owned registered Approval revocation command."""

    def revoke(
        self,
        command: RegisteredApprovalTerminalCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Revoke once or exactly resolve a committed command."""
        ...


class StaticReviewAuthoritySource:
    """Mutable local assignment fake with immutable evidence values."""

    def __init__(self, evidence: Mapping[str, ReviewAuthorityEvidence]) -> None:
        """Freeze an initial subject-indexed assignment projection."""
        self._evidence = dict(evidence)

    def current(self, subject: str) -> ReviewAuthorityEvidence | None:
        """Return current evidence for one stable subject."""
        return self._evidence.get(subject)

    def set(self, evidence: ReviewAuthorityEvidence) -> None:
        """Replace one local subject's current assignment evidence."""
        self._evidence[evidence.subject] = evidence

    def remove(self, subject: str) -> None:
        """Remove one local subject's current assignment."""
        self._evidence.pop(subject, None)

    def check(self) -> bool:
        """Report whether at least one exact current assignment exists."""
        return bool(self._evidence)


@dataclass(frozen=True, slots=True)
class ReviewDecisionWindow:
    """Exact decision time and bounded generic-command expiry."""

    decision_time: str
    command_expires_at: str

    def __post_init__(self) -> None:
        """Require the command to remain live after its recorded decision time."""
        if self.decision_time >= self.command_expires_at:
            message = "command expiry must follow decision time"
            raise ValueError(message)

    def current(self) -> ReviewDecisionWindow:
        """Serve as a deterministic window source for tests and exact replay."""
        return self


@dataclass(frozen=True, slots=True)
class SystemReviewDecisionWindowSource:
    """Create a fresh bounded Review-command window for every local decision."""

    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ttl: timedelta = timedelta(minutes=5)

    def current(self) -> ReviewDecisionWindow:
        """Return one second-precise UTC window from the current local clock."""
        now = self.clock()
        if now.tzinfo is None or self.ttl <= timedelta(0):
            message = "review clock must be timezone-aware and TTL positive"
            raise ValueError(message)
        decision = now.astimezone(UTC).replace(microsecond=0)
        expiry = decision + self.ttl
        return ReviewDecisionWindow(
            decision.isoformat().replace("+00:00", "Z"),
            expiry.isoformat().replace("+00:00", "Z"),
        )


class ReviewDecisionWindowSource(Protocol):
    """Supply a fresh exact decision/command window when a command is handled."""

    def current(self) -> ReviewDecisionWindow:
        """Return the current exact decision window."""
        ...


@dataclass(frozen=True, slots=True)
class RegisteredReviewGovernanceConfiguration:
    """Decision window plus optional durable registered-revocation boundary."""

    window: ReviewDecisionWindowSource
    approved: RegisteredReviewApprovalSource | None = None
    revocations: RegisteredReviewRevocationWriter | None = None

    def __post_init__(self) -> None:
        """Require the two revocation dependencies to be admitted together."""
        if (self.approved is None) != (self.revocations is None):
            message = "registered revocation source and writer must be configured together"
            raise ValueError(message)


class RegisteredReviewGovernanceService:
    """Record one schema-valid human decision without promotion authority."""

    def __init__(
        self,
        writer: ReviewDecisionWriter,
        proposals: ReviewProposalSource,
        authority: ReviewAuthoritySource,
        schemas: SchemaRegistry,
        configuration: RegisteredReviewGovernanceConfiguration,
    ) -> None:
        """Bind exact current inputs and the no-effect register writer."""
        self._writer = writer
        self._proposals = proposals
        self._authority = authority
        self._schemas = schemas
        self._approved = configuration.approved
        self._revocations = configuration.revocations
        self._window = configuration.window

    def submit(self, command: ReviewCommand) -> CommandOutcome:  # noqa: C901, PLR0912
        """Re-read, authorize, validate, and atomically record one decision."""
        window = self._window.current()
        action = _required_string(command.body, "action")
        if action == "REVOKE":
            return self._revoke(command)
        if action not in {"APPROVE", "REJECT"}:
            raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
        if command.expected_version != 0:
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        evidence = self._authorized_evidence(command.principal)
        proposal = self._proposals.detail(command.target)
        if proposal is None:
            raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
        manifest_fingerprint = _required_string(command.body, "manifest_fingerprint")
        if manifest_fingerprint != proposal.proposal.manifest_fingerprint:
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        if not proposal.valid_from <= window.decision_time <= proposal.valid_until:
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        two_family_bindings = tuple(
            item
            for item in proposal.validity_predicates
            if item[0] == "HK_V1_TWO_FAMILY_PROPOSAL" and item[1] == "1.0.0"
        )
        if (
            action == "APPROVE"
            and (len(two_family_bindings) != 1 or proposal.hk_v1_readiness is None)
            and two_family_bindings
        ):
            raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
        if action == "APPROVE" and proposal.hk_v1_readiness is not None:
            if len(two_family_bindings) != 1:
                raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
            try:
                validate_hk_v1_review_readiness(
                    proposal.hk_v1_readiness,
                    two_family_bindings[0][2],
                )
            except ProposalProjectionError as error:
                raise LocalAdapterError(LocalAdapterErrorCode.DISABLED) from error
        reason = _required_string(command.body, "reason")
        decision = "APPROVED" if action == "APPROVE" else "REJECTED"
        approval_id = _stable_id(
            "apr",
            proposal.promotion_manifest_id,
            manifest_fingerprint,
            decision,
        )
        decision_document: dict[str, JsonValue] = {
            "approval_id": approval_id,
            "authority_evidence_ref": _reference(
                "EVIDENCE",
                evidence.authority_evidence_id,
                evidence.authority_evidence_fingerprint,
            ),
            "decision": decision,
            "decision_time": window.decision_time,
            "expected_base_serving_state_ref": _reference(
                "SERVING_STATE",
                proposal.base_serving_state_id,
                proposal.base_serving_state_fingerprint,
            ),
            "governance_policy_state": "CONFIGURED",
            "immutable": True,
            "promotion_manifest_ref": _reference(
                "PROMOTION_MANIFEST",
                proposal.promotion_manifest_id,
                manifest_fingerprint,
            ),
            "reason": reason,
            "reviewer_identity_ref": _reference(
                "ACTOR",
                evidence.reviewer_identity_id,
                evidence.reviewer_identity_fingerprint,
            ),
            "schema_id": "asklegal.approval-decision",
            "schema_version": "1.1.0",
            "valid_from": proposal.valid_from,
            "validity_condition_refs": [
                {
                    "contract_id": contract_id,
                    "fingerprint": condition_fingerprint,
                    "version": version,
                }
                for contract_id, version, condition_fingerprint in proposal.validity_predicates
            ],
        }
        if action == "APPROVE" and proposal.hk_v1_readiness is not None:
            decision_document["review_readiness_fingerprint"] = proposal.hk_v1_readiness.fingerprint
        document = checked_json_value(decision_document)
        self._schemas.validate(
            document,
            "schemas/promotion-domain.schema.json#/$defs/approval_decision",
        )
        event_bytes = canonicalize(document)
        event_fingerprint = f"sha256:{sha256(event_bytes).hexdigest()}"
        command_bytes = canonicalize(
            checked_json_value(
                {
                    "action": "RECORD_PROPOSAL_DECISION",
                    "approval_id": approval_id,
                    "decision_fingerprint": event_fingerprint,
                    "expected_review_version": command.expected_version,
                    "proposal_package_id": command.target,
                    "reviewer_subject": command.principal.subject,
                }
            )
        )
        result = self._writer.record_event(
            RegisterEventCommand(
                owning_application="REVIEW_APPLICATION",
                command_id=command.command_id,
                command_bytes=command_bytes,
                target_id=command.target,
                expected_version=None,
                expected_absent=True,
                expires_at=window.command_expires_at,
                winner_key=f"proposal-decision:{proposal.promotion_manifest_id}",
                event_id=f"evt_{sha256(event_bytes).hexdigest()[:48]}",
                event_type="PROPOSAL_APPROVED" if decision == "APPROVED" else "PROPOSAL_REJECTED",
                event_bytes=event_bytes,
            )
        )
        if result.result_code == "REJECTED_STALE_VERSION":
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        if result.result_code == "REJECTED_CONFLICT":
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        if result.result_code != "APPLIED" or result.authoritative_version != 1:
            raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
        return CommandOutcome(
            command.command_id,
            "EXACT_REPLAY" if result.replayed else "RESULT_RECORDED",
            decision,
            result.authoritative_version,
            approval_id,
        )

    def _revoke(self, command: ReviewCommand) -> CommandOutcome:
        """Authorize and atomically revoke one exact unconsumed registered Approval."""
        window = self._window.current()
        if command.expected_version != 1:
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        if self._approved is None or self._revocations is None:
            raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
        if _required_string(command.body, "approval_ref") != command.target:
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        evidence = self._authorized_evidence(command.principal)
        proposal = self._approved.approved(command.target)
        if (
            proposal is None
            or proposal.decision is None
            or proposal.decision.decision != "APPROVED"
        ):
            raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
        decision = proposal.decision
        manifest_fingerprint = _required_string(command.body, "manifest_fingerprint")
        if manifest_fingerprint != proposal.proposal.manifest_fingerprint:
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        reason = _required_string(command.body, "reason")
        event_id = _stable_id(
            "ape",
            command.target,
            "REVOKE",
            command.command_id,
            decision.event_fingerprint,
        )
        authority_refs = (
            _reference(
                "EVIDENCE",
                decision.authority_evidence_id,
                decision.authority_evidence_fingerprint,
            ),
            _reference(
                "EVIDENCE",
                evidence.authority_evidence_id,
                evidence.authority_evidence_fingerprint,
            ),
        )
        event = checked_json_value(
            {
                "approval_lifecycle_event_id": event_id,
                "approval_ref": _reference(
                    "APPROVAL",
                    decision.approval_id,
                    decision.event_fingerprint,
                ),
                "event_time": window.decision_time,
                "event_type": "REVOKE",
                "evidence_refs": _unique_references(authority_refs),
                "execution_lineage_refs": [],
                "from_state": "APPROVAL_APPROVED",
                "immutable": True,
                "responsible_identity_ref": _reference(
                    "ACTOR",
                    evidence.reviewer_identity_id,
                    evidence.reviewer_identity_fingerprint,
                ),
                "schema_id": "asklegal.approval-lifecycle-event",
                "schema_version": "1.1.0",
                "to_state": "APPROVAL_REVOKED",
            }
        )
        self._schemas.validate(
            event,
            "schemas/promotion-domain.schema.json#/$defs/approval_lifecycle_event",
        )
        command_document = checked_json_value(
            {
                "action": "REVOKE_REGISTERED_APPROVAL",
                "approval_id": decision.approval_id,
                "decision_fingerprint": decision.event_fingerprint,
                "manifest_fingerprint": manifest_fingerprint,
                "manifest_id": proposal.promotion_manifest_id,
                "proposal_package_id": proposal.proposal.proposal_id,
                "reason": reason,
                "revoker_subject": command.principal.subject,
            }
        )
        result = self._revocations.revoke(
            RegisteredApprovalTerminalCommand(
                command.command_id,
                canonicalize(command_document),
                decision.approval_id,
                proposal.proposal.proposal_id,
                bytes.fromhex(decision.event_fingerprint.removeprefix("sha256:")),
                proposal.promotion_manifest_id,
                manifest_fingerprint,
                window.command_expires_at,
                event_id,
                canonicalize(event),
            )
        )
        if result.result_code in {"REJECTED_CONFLICT", "REJECTED_STALE_VERSION"}:
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        if result.result_code != "APPLIED" or result.authoritative_version != _REVOCATION_VERSION:
            raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
        return CommandOutcome(
            command.command_id,
            "EXACT_REPLAY" if result.replayed else "RESULT_RECORDED",
            "REVOKED",
            result.authoritative_version,
            decision.approval_id,
        )

    def _authorized_evidence(self, principal: Principal) -> ReviewAuthorityEvidence:
        evidence = self._authority.current(principal.subject)
        if (
            principal.token_type is not TokenType.DELEGATED_HUMAN
            or "PipelineAdministrator" not in principal.roles
            or evidence is None
            or "PipelineAdministrator" not in evidence.roles
        ):
            raise ApprovalError(ApprovalErrorCode.UNAUTHORIZED_PRINCIPAL)
        return evidence

    def check(self) -> bool:
        """Require both exact proposal and current-authority reads."""
        return self._proposals.check() and self._authority.check()


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


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def _reference(ref_type: str, ref_id: str, value_fingerprint: str) -> dict[str, JsonValue]:
    return {
        "fingerprint": value_fingerprint,
        "ref_id": ref_id,
        "ref_type": ref_type,
    }


def _unique_references(
    references: tuple[dict[str, JsonValue], ...],
) -> list[dict[str, JsonValue]]:
    """Preserve first occurrence while removing exact duplicate evidence refs."""
    result: list[dict[str, JsonValue]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in references:
        ref_type = _required_reference_text(item, "ref_type")
        ref_id = _required_reference_text(item, "ref_id")
        item_fingerprint = _required_reference_text(item, "fingerprint")
        key = (ref_type, ref_id, item_fingerprint)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _required_reference_text(reference: Mapping[str, JsonValue], field: str) -> str:
    value = reference.get(field)
    if type(value) is not str or not value:
        raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
    return value
