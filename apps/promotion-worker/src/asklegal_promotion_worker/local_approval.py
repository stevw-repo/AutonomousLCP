"""Promotion-side reader/consumer for the retained local Review Approval ledger."""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from threading import RLock

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_management_register_ports import (
    ApprovalConsumption,
    ApprovalDecision,
    ApprovalError,
    ApprovalErrorCode,
    ApprovalProjection,
    ApprovalState,
    ManifestSnapshot,
    ReviewerPrincipal,
)

_LEDGER_SCHEMA = "asklegal.local-review-approval-ledger/v1"
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_ACTOR_ID = re.compile(r"^act_[0-9a-f]{48}$")
_EVIDENCE_ID = re.compile(r"^evi_[0-9a-f]{48}$")
_Authority = tuple[str, str, str, str, str]


class LocalRetainedPromotionApprovalStore:
    """Reread and consume the exact file written by the local Review application."""

    def __init__(self, state_path: Path, authority_path: Path | None = None) -> None:
        """Open one explicit non-symlinked retained ledger file."""
        if state_path.is_symlink() or not state_path.is_file():
            raise ApprovalError(ApprovalErrorCode.APPROVAL_NOT_FOUND)
        self._state_path = state_path
        self._authority = None if authority_path is None else _load_authority(authority_path)
        self._lock = RLock()
        self._approvals: dict[str, ApprovalProjection] = {}
        self._packages: dict[str, tuple[bytes, bytes]] = {}
        self._predicates: dict[str, tuple[tuple[str, str, str], ...]] = {}
        self._document: dict[str, JsonValue] = {}
        self._load()

    def decide(
        self,
        principal: ReviewerPrincipal,
        manifest: ManifestSnapshot,
        *,
        decision: str,
        reason: str,
        decision_time: str,
    ) -> ApprovalProjection:
        """Refuse decisions because only the Review application owns that capability."""
        del principal, manifest, decision, reason, decision_time
        raise ApprovalError(ApprovalErrorCode.UNAUTHORIZED_PRINCIPAL)

    def get(self, approval_id: str) -> ApprovalProjection:
        """Return one projection reconstructed from exact retained event bytes."""
        try:
            return self._approvals[approval_id]
        except KeyError as error:
            raise ApprovalError(ApprovalErrorCode.APPROVAL_NOT_FOUND) from error

    def approved_package(self, approval_id: str) -> tuple[bytes, bytes]:
        """Return the exact proposal/readiness bytes frozen at Approval time."""
        state = self.get(approval_id).state
        if state is ApprovalState.REVOKED:
            raise ApprovalError(ApprovalErrorCode.APPROVAL_REVOKED)
        if state is ApprovalState.INVALIDATED:
            raise ApprovalError(ApprovalErrorCode.APPROVAL_INVALIDATED)
        if state not in {ApprovalState.APPROVED, ApprovalState.CONSUMED}:
            raise ApprovalError(ApprovalErrorCode.APPROVAL_REJECTED)
        try:
            return self._packages[approval_id]
        except KeyError as error:
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT) from error

    def decision_fingerprint(self, approval_id: str) -> str:
        """Return the exact retained approved-decision event fingerprint."""
        self.get(approval_id)
        events = self._document.get("events")
        if not isinstance(events, list):
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
        matches: list[str] = []
        for item in events:
            if not isinstance(item, dict):
                continue
            event_hex = item.get("event_bytes")
            if type(event_hex) is not str:
                continue
            try:
                event_bytes = bytes.fromhex(event_hex)
                event = parse_json_bytes(event_bytes, max_bytes=1_000_000)
            except (TypeError, ValueError) as error:
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT) from error
            if isinstance(event, dict) and event.get("approval_id") == approval_id:
                matches.append("sha256:" + sha256(event_bytes).hexdigest())
        if len(matches) != 1:
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
        return matches[0]

    def consume(
        self,
        approval_id: str,
        execution_lineage_id: str,
        manifest: ManifestSnapshot,
        context: ApprovalConsumption,
    ) -> ApprovalProjection:
        """Atomically persist one exact consumption before returning it as visible."""
        with self._lock, exclusive_local_state_lock(self._state_path):
            self._load()
            current = self.get(approval_id)
            if current.state is ApprovalState.CONSUMED:
                if current.execution_lineage_id == execution_lineage_id:
                    return current
                raise ApprovalError(ApprovalErrorCode.APPROVAL_CONSUMED)
            if (
                current.state is not ApprovalState.APPROVED
                or current.decision.manifest_id != manifest.manifest_id
                or current.decision.manifest_fingerprint != manifest.fingerprint
                or current.decision.expected_base_serving_state_id
                != context.current_base_serving_state_id
                or manifest.validity_predicates != self._predicates.get(approval_id)
                or manifest.validity_predicates != context.current_predicates
                or not manifest.valid_from <= context.at <= manifest.valid_until
            ):
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
            states = self._document.get("approval_states")
            if not isinstance(states, dict):
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
            next_states = dict(states)
            next_states[approval_id] = {
                "lineage": execution_lineage_id,
                "state": ApprovalState.CONSUMED.value,
            }
            next_document = dict(self._document)
            next_document["approval_states"] = next_states
            temporary = self._state_path.with_suffix(".promotion.tmp")
            temporary.write_bytes(canonicalize(checked_json_value(next_document)))
            temporary.replace(self._state_path)
            self._load()
            return self.get(approval_id)

    def _load(  # noqa: C901, PLR0912 - one exact ledger reconstruction boundary.
        self,
    ) -> None:
        """Reconstruct all state from canonical bounded bytes on every transition."""
        try:
            content = self._state_path.read_bytes()
            value = parse_json_bytes(content, max_bytes=5_000_000)
        except (OSError, ContractViolation, ValueError) as error:
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT) from error
        if (
            not isinstance(value, dict)
            or set(value) != {"approval_states", "events", "revoked", "schema_id"}
            or value.get("schema_id") != _LEDGER_SCHEMA
            or canonicalize(value) != content
        ):
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
        events = value.get("events")
        states = value.get("approval_states")
        revoked = value.get("revoked")
        if (
            not isinstance(events, list)
            or not isinstance(states, dict)
            or not isinstance(revoked, list)
        ):
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
        approvals: dict[str, ApprovalProjection] = {}
        packages: dict[str, tuple[bytes, bytes]] = {}
        predicates: dict[str, tuple[tuple[str, str, str], ...]] = {}
        for item in events:
            parsed = _approval_event(item, self._authority)
            if parsed is None:
                continue
            approval, package, conditions = parsed
            approval_id = approval.decision.approval_id
            if approval_id in approvals:
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
            approvals[approval_id] = approval
            packages[approval_id] = package
            predicates[approval_id] = conditions
        if set(states) != set(approvals):
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
        for approval_id, raw in states.items():
            if (
                approval_id not in approvals
                or not isinstance(raw, dict)
                or set(raw) != {"lineage", "state"}
                or type(raw.get("lineage")) is not str
                or type(raw.get("state")) is not str
            ):
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
            raw_state = raw.get("state")
            raw_lineage = raw.get("lineage")
            if type(raw_state) is not str or type(raw_lineage) is not str:
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
            try:
                state = ApprovalState(raw_state)
            except ValueError as error:
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT) from error
            if (state is ApprovalState.CONSUMED) != bool(raw_lineage):
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
            approvals[approval_id] = ApprovalProjection(
                approvals[approval_id].decision,
                state,
                raw_lineage,
            )
        if (
            any(type(item) is not str or item not in approvals for item in revoked)
            or len(set(revoked)) != len(revoked)
            or set(revoked)
            != {
                approval_id
                for approval_id, approval in approvals.items()
                if approval.state is ApprovalState.REVOKED
            }
        ):
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
        self._approvals = approvals
        self._packages = packages
        self._predicates = predicates
        self._document = value


def _approval_event(
    value: JsonValue,
    expected_authority: _Authority | None,
) -> (
    tuple[
        ApprovalProjection,
        tuple[bytes, bytes],
        tuple[tuple[str, str, str], ...],
    ]
    | None
):
    if not isinstance(value, dict) or set(value) != {
        "command_bytes",
        "command_id",
        "event_bytes",
        "proposal_bytes",
        "readiness_bytes",
        "target_id",
        "winner_key",
    }:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    event_hex = value.get("event_bytes")
    if type(event_hex) is not str:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    try:
        event_bytes = bytes.fromhex(event_hex)
        event = parse_json_bytes(event_bytes, max_bytes=1_000_000)
    except (ValueError, TypeError) as error:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT) from error
    if not isinstance(event, dict) or canonicalize(event) != event_bytes:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    if event.get("decision") != "APPROVED":
        return None
    promotion = event.get("promotion_manifest_ref")
    reviewer = event.get("reviewer_identity_ref")
    authority = event.get("authority_evidence_ref")
    base = event.get("expected_base_serving_state_ref")
    approval_id = event.get("approval_id")
    if (
        not isinstance(promotion, dict)
        or not isinstance(reviewer, dict)
        or not isinstance(authority, dict)
        or not isinstance(base, dict)
        or type(approval_id) is not str
    ):
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    reviewer_subject = _bound_reviewer_subject(value, event, event_bytes, expected_authority)
    manifest_fingerprint = _fingerprint(promotion.get("fingerprint"))
    conditions = _conditions(event.get("validity_condition_refs"))
    readiness_fingerprint = _fingerprint(event.get("review_readiness_fingerprint"))
    proposal_hex = value.get("proposal_bytes")
    readiness_hex = value.get("readiness_bytes")
    if type(proposal_hex) is not str or type(readiness_hex) is not str:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    try:
        package = (bytes.fromhex(proposal_hex), bytes.fromhex(readiness_hex))
    except ValueError as error:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT) from error
    if (
        not package[0]
        or not package[1]
        or readiness_fingerprint
        not in {item[2] for item in conditions if item[0] == "HK_V1_REVIEW_READINESS"}
    ):
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    decision = ApprovalDecision(
        approval_id,
        _text(promotion, "ref_id"),
        manifest_fingerprint,
        "APPROVED",
        reviewer_subject,
        _text(event, "reason"),
        _text(event, "decision_time"),
        _text(base, "ref_id"),
        _text(authority, "ref_id"),
    )
    return ApprovalProjection(decision, ApprovalState.APPROVED, ""), package, conditions


def _bound_reviewer_subject(
    value: dict[str, JsonValue],
    event: dict[str, JsonValue],
    event_bytes: bytes,
    expected_authority: _Authority | None,
) -> str:
    """Recover the named human from canonical command bytes bound to the event."""
    approval_id = _text(event, "approval_id")
    promotion = event.get("promotion_manifest_ref")
    reviewer = event.get("reviewer_identity_ref")
    authority = event.get("authority_evidence_ref")
    if (
        not isinstance(promotion, dict)
        or not isinstance(reviewer, dict)
        or not isinstance(authority, dict)
    ):
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    promotion_manifest_id = _text(promotion, "ref_id")
    reviewer_identity_ref = _text(reviewer, "ref_id")
    authority_evidence_ref = _text(authority, "ref_id")
    _fingerprint(reviewer.get("fingerprint"))
    _fingerprint(authority.get("fingerprint"))
    command_hex = value.get("command_bytes")
    target_id = value.get("target_id")
    winner_key = value.get("winner_key")
    if type(command_hex) is not str or type(target_id) is not str or type(winner_key) is not str:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    try:
        command_bytes = bytes.fromhex(command_hex)
        command = parse_json_bytes(command_bytes, max_bytes=100_000)
    except (ContractViolation, ValueError, TypeError) as error:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT) from error
    if (
        not isinstance(command, dict)
        or set(command)
        != {
            "action",
            "approval_id",
            "decision_fingerprint",
            "expected_review_version",
            "proposal_package_id",
            "reviewer_subject",
        }
        or canonicalize(command) != command_bytes
        or command.get("action") != "RECORD_PROPOSAL_DECISION"
        or command.get("approval_id") != approval_id
        or command.get("decision_fingerprint") != f"sha256:{sha256(event_bytes).hexdigest()}"
        or command.get("expected_review_version") != 0
        or command.get("proposal_package_id") != target_id
        or winner_key != f"proposal-decision:{promotion_manifest_id}"
        or _ACTOR_ID.fullmatch(reviewer_identity_ref) is None
        or _EVIDENCE_ID.fullmatch(authority_evidence_ref) is None
    ):
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    reviewer_subject = _text(command, "reviewer_subject")
    if expected_authority is not None:
        (
            expected_subject,
            expected_actor,
            expected_actor_fp,
            expected_evidence,
            expected_evidence_fp,
        ) = expected_authority
        if (
            reviewer_subject != expected_subject
            or reviewer_identity_ref != expected_actor
            or reviewer.get("fingerprint") != expected_actor_fp
            or authority_evidence_ref != expected_evidence
            or authority.get("fingerprint") != expected_evidence_fp
        ):
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    return reviewer_subject


def _load_authority(path: Path) -> _Authority:
    """Read the same retained authority configuration that Review used."""
    try:
        content = path.read_bytes()
        value = parse_json_bytes(content, max_bytes=100_000)
    except (OSError, ContractViolation, ValueError) as error:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT) from error
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "authority_evidence_fingerprint",
            "authority_evidence_id",
            "reviewer_identity_fingerprint",
            "reviewer_identity_id",
            "roles",
            "schema_id",
            "subject",
        }
        or value.get("schema_id") != "asklegal.local-review-authority/v1"
        or canonicalize(value) != content
    ):
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    subject = _text(value, "subject")
    actor = _text(value, "reviewer_identity_id")
    actor_fingerprint = _fingerprint(value.get("reviewer_identity_fingerprint"))
    evidence = _text(value, "authority_evidence_id")
    evidence_fingerprint = _fingerprint(value.get("authority_evidence_fingerprint"))
    roles = value.get("roles")
    if (
        _ACTOR_ID.fullmatch(actor) is None
        or _EVIDENCE_ID.fullmatch(evidence) is None
        or not isinstance(roles, list)
        or not roles
        or any(type(role) is not str or not role for role in roles)
    ):
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    return subject, actor, actor_fingerprint, evidence, evidence_fingerprint


def _conditions(value: JsonValue | None) -> tuple[tuple[str, str, str], ...]:
    if not isinstance(value, list):
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    result: list[tuple[str, str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "contract_id",
            "fingerprint",
            "version",
        }:
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
        result.append(
            (
                _text(item, "contract_id"),
                _text(item, "version"),
                _fingerprint(item.get("fingerprint")),
            )
        )
    return tuple(result)


def _text(value: dict[str, JsonValue], field: str) -> str:
    item = value.get(field)
    if type(item) is not str or not item or item.strip() != item:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    return item


def _fingerprint(value: JsonValue | None) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
    return value
