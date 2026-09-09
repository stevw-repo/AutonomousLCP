"""Registered Approval validation and single-lineage consumption."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol

from asklegal_contracts import (
    ContractViolation,
    SchemaRegistry,
    canonicalize,
    parse_json_bytes,
)
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import CorpusError
from asklegal_evidence_vault import EvidenceError, ImmutableVault, S3VaultError, VaultName
from asklegal_management_register import (
    ApprovedPromotionClaim,
    RegisteredApprovalConsumptionCommand,
    RegisteredApprovalTerminalCommand,
    RegisterProjectionError,
    ReviewReadyProposalRow,
    V1CommandResult,
)
from asklegal_promotion import (
    PromotionError,
    promotion_approval_snapshot_from_bytes,
    read_stored_proposal_package,
    stored_proposal_package_from_bytes,
)

if TYPE_CHECKING:
    from asklegal_promotion import PromotionApprovalSnapshot

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")


class RegisteredApprovalErrorCode(StrEnum):
    """Closed pre-effect Approval consumption failures."""

    ALREADY_CONSUMED = "REGISTERED_APPROVAL_ALREADY_CONSUMED"
    AUTHORITY_REMOVED = "REGISTERED_APPROVAL_AUTHORITY_REMOVED"
    INVALID = "REGISTERED_APPROVAL_INVALID"
    NOT_APPROVED = "REGISTERED_APPROVAL_NOT_APPROVED"


class RegisteredApprovalInvalidationCode(StrEnum):
    """Closed objective reasons that terminally invalidate an Approval."""

    BASE_SERVING_STATE_DRIFT = "BASE_SERVING_STATE_DRIFT"
    MANIFEST_WINDOW_CLOSED = "MANIFEST_WINDOW_CLOSED"
    REVIEWER_AUTHORITY_REMOVED = "REVIEWER_AUTHORITY_REMOVED"
    VALIDITY_PREDICATE_DRIFT = "VALIDITY_PREDICATE_DRIFT"


class RegisteredApprovalError(RuntimeError):
    """One safe fail-closed registered Approval failure."""

    def __init__(self, code: RegisteredApprovalErrorCode) -> None:
        """Create one closed failure without source or identity details."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class RegisteredApprovalCandidate:
    """Exact approved decision plus manifest facts reconstructed after restart."""

    proposal_package_id: str
    approval_id: str
    decision_fingerprint: str
    manifest: PromotionApprovalSnapshot
    reviewer_identity_id: str
    reviewer_identity_fingerprint: str
    authority_evidence_id: str
    authority_evidence_fingerprint: str


class RegisteredApprovalCandidateSource(Protocol):
    """Complete SQL/Primary-Vault reread boundary."""

    def approved(self, proposal_package_id: str) -> RegisteredApprovalCandidate | None:
        """Return one exact approved candidate or no consumable candidate."""
        ...


class ApprovedPromotionQueue(Protocol):
    """Provider-disabled discovery lease before independent Approval revalidation."""

    def claim_next(self, worker_id: str, claimed_until: str) -> ApprovedPromotionClaim | None:
        """Claim only one exact approved-decision wake-up lease."""
        ...

    def acknowledge_started(self, claim: ApprovedPromotionClaim, execution_lineage_id: str) -> None:
        """Observe an already durable matching Approval-consumption lineage."""
        ...


class RegisteredProposalRows(Protocol):
    """Least-privilege registered proposal and decision projection."""

    def review_ready_proposals(self) -> tuple[ReviewReadyProposalRow, ...]:
        """Return one immutable generation in proposal identity order."""
        ...


class RegisteredApprovalSourceError(RuntimeError):
    """One safe failure to reconstruct registered Approval authority."""


class RegisteredPromotionApprovalSource:
    """Independently reconstruct an approved decision from SQL and Primary Vault."""

    def __init__(
        self,
        rows: RegisteredProposalRows,
        primary_vault: ImmutableVault,
        schemas: SchemaRegistry,
    ) -> None:
        """Bind only the least-privilege row view, exact vault, and local schemas."""
        if primary_vault.vault_name is not VaultName.PRIMARY:
            message = "registered Approval requires the Primary Vault"
            raise RegisteredApprovalSourceError(message)
        self._rows = rows
        self._vault = primary_vault
        self._schemas = schemas

    def approved(self, proposal_package_id: str) -> RegisteredApprovalCandidate | None:
        """Re-read the complete package and exact approved decision after restart."""
        try:
            row = _selected_row(self._rows.review_ready_proposals(), proposal_package_id)
            if row is None or row.decision_event_type != "PROPOSAL_APPROVED":
                return None
            return self._candidate(row)
        except RegisteredApprovalSourceError:
            raise
        except (
            ContractViolation,
            CorpusError,
            EvidenceError,
            PromotionError,
            RegisterProjectionError,
            S3VaultError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            raise RegisteredApprovalSourceError from error

    def _candidate(self, row: ReviewReadyProposalRow) -> RegisteredApprovalCandidate:
        """Validate one row, all package bytes, manifest facts, and decision bindings."""
        if (
            row.authoritative_version != 1
            or row.review_version != 1
            or row.decision_bytes is None
            or row.decision_fingerprint is None
            or sha256(row.receipt_bytes).digest() != row.receipt_fingerprint
            or sha256(row.decision_bytes).digest() != row.decision_fingerprint
        ):
            message = "registered proposal or decision fingerprint drift"
            raise RegisteredApprovalSourceError(message)
        receipt = stored_proposal_package_from_bytes(row.receipt_bytes)
        if receipt.package_id != row.proposal_package_id:
            message = "registered proposal identity drift"
            raise RegisteredApprovalSourceError(message)
        package = read_stored_proposal_package(self._vault, receipt)
        promotion_artifacts = tuple(
            item for item in package.artifacts if item.role == "PROMOTION_MANIFEST"
        )
        if len(promotion_artifacts) != 1:
            message = "registered proposal lacks one Promotion Manifest"
            raise RegisteredApprovalSourceError(message)
        manifest = promotion_approval_snapshot_from_bytes(
            promotion_artifacts[0].content,
            expected_manifest_id=receipt.promotion_manifest_id,
            expected_fingerprint=receipt.promotion_manifest_fingerprint,
        )
        decision = parse_json_bytes(row.decision_bytes, max_bytes=1_000_000)
        if not isinstance(decision, dict) or canonicalize(decision) != row.decision_bytes:
            message = "registered Approval decision is not canonical"
            raise RegisteredApprovalSourceError(message)
        self._schemas.validate(
            decision,
            "schemas/promotion-domain.schema.json#/$defs/approval_decision",
        )
        return _candidate_from_decision(
            row.proposal_package_id,
            row.decision_fingerprint,
            decision,
            manifest,
            _proposal_base_fingerprint(package.manifest_bytes),
        )


def _selected_row(
    rows: tuple[ReviewReadyProposalRow, ...],
    proposal_package_id: str,
) -> ReviewReadyProposalRow | None:
    """Require one ordered unique generation before selecting a proposal."""
    identities = tuple(row.proposal_package_id for row in rows)
    if identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
        message = "registered proposal generation is not exact"
        raise RegisteredApprovalSourceError(message)
    return next((item for item in rows if item.proposal_package_id == proposal_package_id), None)


@dataclass(frozen=True, slots=True)
class CurrentReviewerAuthority:
    """Current role assignment and immutable evidence at consumption time."""

    reviewer_identity_id: str
    reviewer_identity_fingerprint: str
    roles: frozenset[str]
    authority_evidence_id: str
    authority_evidence_fingerprint: str


class CurrentReviewerAuthoritySource(Protocol):
    """Current reviewer assignment lookup used immediately before consumption."""

    def current(self, reviewer_identity_id: str) -> CurrentReviewerAuthority | None:
        """Return one exact current assignment, if still active."""
        ...


class RegisteredApprovalWriter(Protocol):
    """Atomic Promotion-owned Approval consumption command."""

    def consume(
        self,
        command: RegisteredApprovalConsumptionCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Consume once or exactly resolve a committed command."""
        ...


class RegisteredApprovalInvalidationWriter(Protocol):
    """Atomic Promotion-owned Approval invalidation command."""

    def invalidate(
        self,
        command: RegisteredApprovalTerminalCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Invalidate once or exactly resolve a committed command."""
        ...


@dataclass(frozen=True, slots=True)
class ApprovalConsumptionContext:
    """Exact current facts and evidence bound to one consumption attempt."""

    at: str
    command_expires_at: str
    current_base_serving_state_id: str
    current_predicates: tuple[tuple[str, str, str], ...]
    execution_lineage_id: str
    execution_lineage_fingerprint: str
    validation_evidence_id: str
    validation_evidence_fingerprint: str
    promotion_worker_identity_id: str
    promotion_worker_identity_fingerprint: str


class RegisteredApprovalConsumptionService:
    """Consume one exact still-valid Approval into one execution lineage."""

    def __init__(
        self,
        candidates: RegisteredApprovalCandidateSource,
        authority: CurrentReviewerAuthoritySource,
        writer: RegisteredApprovalWriter,
        invalidations: RegisteredApprovalInvalidationWriter,
        schemas: SchemaRegistry,
    ) -> None:
        """Bind complete reread, current authority, atomic writer, and schemas."""
        self._candidates = candidates
        self._authority = authority
        self._writer = writer
        self._invalidations = invalidations
        self._schemas = schemas

    def consume(
        self,
        proposal_package_id: str,
        command_id: str,
        context: ApprovalConsumptionContext,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Revalidate and atomically consume without creating a provider effect."""
        candidate = self._candidates.approved(proposal_package_id)
        if candidate is None:
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.NOT_APPROVED)
        _validate_candidate(candidate, proposal_package_id)
        _validate_context_shape(context)
        current = self._authority.current(candidate.reviewer_identity_id)
        invalidation = _invalidation_code(candidate, current, context)
        if invalidation is not None:
            self._invalidate(candidate, command_id, context, invalidation)
            error_code = (
                RegisteredApprovalErrorCode.AUTHORITY_REMOVED
                if invalidation is RegisteredApprovalInvalidationCode.REVIEWER_AUTHORITY_REMOVED
                else RegisteredApprovalErrorCode.INVALID
            )
            raise RegisteredApprovalError(error_code)
        if context.at < candidate.manifest.valid_from:
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.INVALID)
        if current is None:
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.AUTHORITY_REMOVED)
        event_id = _stable_id(
            "ape",
            candidate.approval_id,
            context.execution_lineage_id,
            candidate.decision_fingerprint,
        )
        event = checked_json_value(
            {
                "approval_lifecycle_event_id": event_id,
                "approval_ref": _reference(
                    "APPROVAL",
                    candidate.approval_id,
                    candidate.decision_fingerprint,
                ),
                "event_time": context.at,
                "event_type": "CONSUME_FOR_ONE_EXECUTION_LINEAGE",
                "evidence_refs": _evidence_references(candidate, current, context),
                "execution_lineage_refs": [
                    _reference(
                        "EXECUTION_LINEAGE",
                        context.execution_lineage_id,
                        context.execution_lineage_fingerprint,
                    )
                ],
                "from_state": "APPROVAL_APPROVED",
                "immutable": True,
                "responsible_identity_ref": _reference(
                    "ACTOR",
                    context.promotion_worker_identity_id,
                    context.promotion_worker_identity_fingerprint,
                ),
                "schema_id": "asklegal.approval-lifecycle-event",
                "schema_version": "1.1.0",
                "to_state": "APPROVAL_CONSUMED",
            }
        )
        self._schemas.validate(
            event,
            "schemas/promotion-domain.schema.json#/$defs/approval_lifecycle_event",
        )
        command_document = checked_json_value(
            {
                "action": "CONSUME_REGISTERED_APPROVAL",
                "approval_id": candidate.approval_id,
                "decision_fingerprint": candidate.decision_fingerprint,
                "execution_lineage_id": context.execution_lineage_id,
                "manifest_fingerprint": candidate.manifest.fingerprint,
                "manifest_id": candidate.manifest.manifest_id,
                "proposal_package_id": candidate.proposal_package_id,
            }
        )
        result = self._writer.consume(
            RegisteredApprovalConsumptionCommand(
                command_id,
                canonicalize(command_document),
                candidate.approval_id,
                candidate.proposal_package_id,
                bytes.fromhex(candidate.decision_fingerprint.removeprefix("sha256:")),
                candidate.manifest.manifest_id,
                candidate.manifest.fingerprint,
                context.execution_lineage_id,
                context.command_expires_at,
                event_id,
                canonicalize(event),
            ),
            simulate_lost_ack=simulate_lost_ack,
        )
        if result.result_code == "REJECTED_CONFLICT":
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.ALREADY_CONSUMED)
        if result.result_code != "APPLIED" or result.authoritative_version != 1:
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.INVALID)
        return result

    def _invalidate(
        self,
        candidate: RegisteredApprovalCandidate,
        source_command_id: str,
        context: ApprovalConsumptionContext,
        reason_code: RegisteredApprovalInvalidationCode,
    ) -> None:
        """Append one objective terminal event before reporting invalid consumption."""
        event_id = _stable_id(
            "ape",
            candidate.approval_id,
            "INVALIDATE",
            reason_code.value,
            candidate.decision_fingerprint,
        )
        event = checked_json_value(
            {
                "approval_lifecycle_event_id": event_id,
                "approval_ref": _reference(
                    "APPROVAL",
                    candidate.approval_id,
                    candidate.decision_fingerprint,
                ),
                "event_time": context.at,
                "event_type": "INVALIDATE",
                "evidence_refs": _invalidation_evidence(candidate, context),
                "execution_lineage_refs": [],
                "from_state": "APPROVAL_APPROVED",
                "immutable": True,
                "responsible_identity_ref": _reference(
                    "ACTOR",
                    context.promotion_worker_identity_id,
                    context.promotion_worker_identity_fingerprint,
                ),
                "schema_id": "asklegal.approval-lifecycle-event",
                "schema_version": "1.1.0",
                "to_state": "APPROVAL_INVALIDATED",
            }
        )
        self._schemas.validate(
            event,
            "schemas/promotion-domain.schema.json#/$defs/approval_lifecycle_event",
        )
        command_document = checked_json_value(
            {
                "action": "INVALIDATE_REGISTERED_APPROVAL",
                "approval_id": candidate.approval_id,
                "decision_fingerprint": candidate.decision_fingerprint,
                "manifest_fingerprint": candidate.manifest.fingerprint,
                "manifest_id": candidate.manifest.manifest_id,
                "proposal_package_id": candidate.proposal_package_id,
                "reason_code": reason_code.value,
            }
        )
        invalidation_command_id = _stable_id(
            "cmd",
            source_command_id,
            candidate.approval_id,
            reason_code.value,
        )
        result = self._invalidations.invalidate(
            RegisteredApprovalTerminalCommand(
                invalidation_command_id,
                canonicalize(command_document),
                candidate.approval_id,
                candidate.proposal_package_id,
                bytes.fromhex(candidate.decision_fingerprint.removeprefix("sha256:")),
                candidate.manifest.manifest_id,
                candidate.manifest.fingerprint,
                context.command_expires_at,
                event_id,
                canonicalize(event),
            )
        )
        if result.result_code == "REJECTED_CONFLICT":
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.ALREADY_CONSUMED)
        if result.result_code != "APPLIED" or result.authoritative_version != 1:
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.INVALID)


def _candidate_from_decision(
    proposal_package_id: str,
    decision_fingerprint: bytes,
    decision: dict[str, JsonValue],
    manifest: PromotionApprovalSnapshot,
    base_serving_state_fingerprint: str,
) -> RegisteredApprovalCandidate:
    """Bind one schema-valid decision back to exact executable manifest facts."""
    if (
        decision.get("decision") != "APPROVED"
        or decision.get("governance_policy_state") != "CONFIGURED"
        or decision.get("immutable") is not True
        or _text(decision, "valid_from") != manifest.valid_from
    ):
        message = "registered decision is not one configured Approval"
        raise RegisteredApprovalSourceError(message)
    manifest_ref = _artifact_reference(decision, "promotion_manifest_ref", "PROMOTION_MANIFEST")
    base_ref = _artifact_reference(decision, "expected_base_serving_state_ref", "SERVING_STATE")
    reviewer_ref = _artifact_reference(decision, "reviewer_identity_ref", "ACTOR")
    authority_ref = _artifact_reference(decision, "authority_evidence_ref", "EVIDENCE")
    if (
        manifest_ref != (manifest.manifest_id, manifest.fingerprint)
        or base_ref != (manifest.expected_base_serving_state_id, base_serving_state_fingerprint)
        or _contract_references(decision.get("validity_condition_refs"))
        != manifest.validity_predicates
    ):
        message = "registered decision bindings drifted"
        raise RegisteredApprovalSourceError(message)
    approval_id = _text(decision, "approval_id")
    if approval_id != _stable_id("apr", manifest.manifest_id, manifest.fingerprint, "APPROVED"):
        message = "registered Approval identity drifted"
        raise RegisteredApprovalSourceError(message)
    return RegisteredApprovalCandidate(
        proposal_package_id,
        approval_id,
        f"sha256:{decision_fingerprint.hex()}",
        manifest,
        reviewer_ref[0],
        reviewer_ref[1],
        authority_ref[0],
        authority_ref[1],
    )


def _proposal_base_fingerprint(content: bytes) -> str:
    """Recover the base Serving State fingerprint from the verified package root."""
    document = parse_json_bytes(content, max_bytes=1_000_000)
    if not isinstance(document, dict):
        message = "proposal package root is not an object"
        raise RegisteredApprovalSourceError(message)
    return _artifact_reference(document, "base_serving_state_ref", "SERVING_STATE")[1]


def _artifact_reference(
    document: Mapping[str, JsonValue],
    field: str,
    expected_type: str,
) -> tuple[str, str]:
    """Read one exact immutable reference."""
    value = document.get(field)
    if not isinstance(value, dict) or set(value) != {"fingerprint", "ref_id", "ref_type"}:
        message = f"{field} is not one exact reference"
        raise RegisteredApprovalSourceError(message)
    reference_id = _text(value, "ref_id")
    reference_fingerprint = _text(value, "fingerprint")
    if (
        value.get("ref_type") != expected_type
        or _IDENTIFIER.fullmatch(reference_id) is None
        or _FINGERPRINT.fullmatch(reference_fingerprint) is None
    ):
        message = f"{field} reference drifted"
        raise RegisteredApprovalSourceError(message)
    return reference_id, reference_fingerprint


def _contract_references(value: JsonValue | None) -> tuple[tuple[str, str, str], ...]:
    """Read exact ordered versioned validity-condition references."""
    if not isinstance(value, list):
        message = "validity condition references are absent"
        raise RegisteredApprovalSourceError(message)
    result: list[tuple[str, str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"contract_id", "fingerprint", "version"}:
            message = "validity condition reference drifted"
            raise RegisteredApprovalSourceError(message)
        contract_id = _text(item, "contract_id")
        version = _text(item, "version")
        condition_fingerprint = _text(item, "fingerprint")
        if _FINGERPRINT.fullmatch(condition_fingerprint) is None:
            message = "validity condition fingerprint drifted"
            raise RegisteredApprovalSourceError(message)
        result.append((contract_id, version, condition_fingerprint))
    return tuple(result)


def _text(document: Mapping[str, JsonValue], field: str) -> str:
    """Read one exact non-empty string."""
    value = document.get(field)
    if type(value) is not str or not value:
        message = f"{field} must be one non-empty string"
        raise RegisteredApprovalSourceError(message)
    return value


def _validate_candidate(candidate: RegisteredApprovalCandidate, proposal_package_id: str) -> None:
    """Reject any malformed value from the complete reread adapter."""
    if (
        candidate.proposal_package_id != proposal_package_id
        or _IDENTIFIER.fullmatch(candidate.proposal_package_id) is None
        or _IDENTIFIER.fullmatch(candidate.approval_id) is None
        or _FINGERPRINT.fullmatch(candidate.decision_fingerprint) is None
        or _IDENTIFIER.fullmatch(candidate.manifest.manifest_id) is None
        or _FINGERPRINT.fullmatch(candidate.manifest.fingerprint) is None
    ):
        raise RegisteredApprovalError(RegisteredApprovalErrorCode.INVALID)
    for identity, identity_fingerprint in (
        (candidate.reviewer_identity_id, candidate.reviewer_identity_fingerprint),
        (candidate.authority_evidence_id, candidate.authority_evidence_fingerprint),
    ):
        if (
            _IDENTIFIER.fullmatch(identity) is None
            or _FINGERPRINT.fullmatch(identity_fingerprint) is None
        ):
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.INVALID)


def _currently_authorized(
    candidate: RegisteredApprovalCandidate,
    current: CurrentReviewerAuthority,
) -> bool:
    """Require the same stable reviewer identity and a current exact role."""
    return (
        current.reviewer_identity_id == candidate.reviewer_identity_id
        and current.reviewer_identity_fingerprint == candidate.reviewer_identity_fingerprint
        and "PipelineAdministrator" in current.roles
        and _IDENTIFIER.fullmatch(current.authority_evidence_id) is not None
        and _FINGERPRINT.fullmatch(current.authority_evidence_fingerprint) is not None
    )


def _validate_context_shape(context: ApprovalConsumptionContext) -> None:
    """Reject malformed caller facts without turning them into invalidation evidence."""
    if (
        context.at >= context.command_expires_at
        or _IDENTIFIER.fullmatch(context.current_base_serving_state_id) is None
        or re.fullmatch(r"exe_[0-9a-f]{48}", context.execution_lineage_id) is None
    ):
        raise RegisteredApprovalError(RegisteredApprovalErrorCode.INVALID)
    for identity in (
        context.validation_evidence_id,
        context.promotion_worker_identity_id,
    ):
        if _IDENTIFIER.fullmatch(identity) is None:
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.INVALID)
    for value in (
        context.execution_lineage_fingerprint,
        context.validation_evidence_fingerprint,
        context.promotion_worker_identity_fingerprint,
    ):
        if _FINGERPRINT.fullmatch(value) is None:
            raise RegisteredApprovalError(RegisteredApprovalErrorCode.INVALID)


def _invalidation_code(
    candidate: RegisteredApprovalCandidate,
    current: CurrentReviewerAuthority | None,
    context: ApprovalConsumptionContext,
) -> RegisteredApprovalInvalidationCode | None:
    """Select one objective terminal reason from independently rechecked facts."""
    if current is None or not _currently_authorized(candidate, current):
        return RegisteredApprovalInvalidationCode.REVIEWER_AUTHORITY_REMOVED
    if context.at > candidate.manifest.valid_until:
        return RegisteredApprovalInvalidationCode.MANIFEST_WINDOW_CLOSED
    if context.current_base_serving_state_id != candidate.manifest.expected_base_serving_state_id:
        return RegisteredApprovalInvalidationCode.BASE_SERVING_STATE_DRIFT
    if context.current_predicates != candidate.manifest.validity_predicates:
        return RegisteredApprovalInvalidationCode.VALIDITY_PREDICATE_DRIFT
    return None


def _evidence_references(
    candidate: RegisteredApprovalCandidate,
    current: CurrentReviewerAuthority,
    context: ApprovalConsumptionContext,
) -> list[dict[str, str]]:
    """Bind historical/current authority and current validity evidence once each."""
    references = (
        _reference(
            "EVIDENCE",
            candidate.authority_evidence_id,
            candidate.authority_evidence_fingerprint,
        ),
        _reference(
            "EVIDENCE",
            current.authority_evidence_id,
            current.authority_evidence_fingerprint,
        ),
        _reference(
            "EVIDENCE",
            context.validation_evidence_id,
            context.validation_evidence_fingerprint,
        ),
    )
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in references:
        key = (item["ref_type"], item["ref_id"], item["fingerprint"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _invalidation_evidence(
    candidate: RegisteredApprovalCandidate,
    context: ApprovalConsumptionContext,
) -> list[dict[str, str]]:
    """Bind the historical authority and current validation evidence."""
    references = (
        _reference(
            "EVIDENCE",
            candidate.authority_evidence_id,
            candidate.authority_evidence_fingerprint,
        ),
        _reference(
            "EVIDENCE",
            context.validation_evidence_id,
            context.validation_evidence_fingerprint,
        ),
    )
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in references:
        key = (item["ref_type"], item["ref_id"], item["fingerprint"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _reference(
    reference_type: str, reference_id: str, reference_fingerprint: str
) -> dict[str, str]:
    """Build one exact immutable reference."""
    return {
        "fingerprint": reference_fingerprint,
        "ref_id": reference_id,
        "ref_type": reference_type,
    }


def _stable_id(prefix: str, *values: str) -> str:
    """Derive one stable register identity."""
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"
