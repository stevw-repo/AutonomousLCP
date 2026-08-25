"""Fail-closed handling of one claimed approved Promotion Effect Intent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol

from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import (
    ApplicationCode,
    EffectCancelledDetail,
    EffectFinalFailureDetail,
    EffectReceipt,
    EffectReceiptDetail,
    EffectReceiptStatus,
    EffectSuccessDetail,
    EffectUnknownDetail,
    ImmutableReference,
    ReferenceType,
)
from asklegal_management_register import EffectReceiptRecord
from asklegal_promotion import (
    PromotionActionAuthority,
    promotion_action_authority_document,
)

from .registered_execution_begin import (
    CurrentCapabilityEvidence,
    CurrentCapabilityEvidenceSource,
)

if TYPE_CHECKING:
    from asklegal_management_register import ClaimedEffect, RecordedEffectReceipt


class RegisteredEffectHandlerErrorCode(StrEnum):
    """Closed failures that never imply an external effect succeeded."""

    AUTHORITY_UNAVAILABLE = "REGISTERED_EFFECT_HANDLER_AUTHORITY_UNAVAILABLE"
    INVALID_INTENT = "REGISTERED_EFFECT_HANDLER_INVALID_INTENT"
    RECEIPT_REJECTED = "REGISTERED_EFFECT_HANDLER_RECEIPT_REJECTED"


class RegisteredEffectHandlerError(RuntimeError):
    """One fail-closed claimed-intent handling failure."""

    def __init__(self, code: RegisteredEffectHandlerErrorCode) -> None:
        """Create one sanitized failure."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class CurrentExecutionActionAuthority:
    """Current authority for the exact action represented by one claimed intent."""

    execution_lineage_ref: ImmutableReference
    action: PromotionActionAuthority
    active: bool
    evidence_ref: ImmutableReference


class CurrentExecutionActionAuthoritySource(Protocol):
    """Current execution/action authority re-read immediately before handling."""

    def current(
        self,
        execution_lineage_id: str,
        effect_intent_id: str,
        at: str,
    ) -> CurrentExecutionActionAuthority | None:
        """Resolve the exact current action authority, if readable."""
        ...


@dataclass(frozen=True, slots=True)
class RegisteredEffectOutcome:
    """One sanitized terminal outcome returned by an injected effect fake."""

    terminal_status: EffectReceiptStatus
    evidence_refs: tuple[ImmutableReference, ...]
    detail: EffectReceiptDetail

    def __post_init__(self) -> None:
        """Require the detail type dictated by the closed terminal status."""
        expected = {
            EffectReceiptStatus.SUCCEEDED: EffectSuccessDetail,
            EffectReceiptStatus.FAILED_FINAL: EffectFinalFailureDetail,
            EffectReceiptStatus.CANCELLED_BEFORE_EFFECT: EffectCancelledDetail,
            EffectReceiptStatus.OUTCOME_UNKNOWN: EffectUnknownDetail,
        }[self.terminal_status]
        if type(self.detail) is not expected:
            message = "terminal outcome detail does not match its status"
            raise TypeError(message)
        _ordered_evidence(self.evidence_refs)


class RegisteredEffectPort(Protocol):
    """Injected effect/reconciliation port; no real implementation is composed."""

    def perform(self, intent_bytes: bytes, fencing_token: int) -> RegisteredEffectOutcome:
        """Perform one exact claimed intent or raise without claiming an outcome."""
        ...

    def reconcile(self, intent_bytes: bytes) -> RegisteredEffectOutcome:
        """Resolve a prior attempt whose terminal receipt was not recorded."""
        ...


class RegisteredEffectHandoff(Protocol):
    """Least-privilege claimed-intent register operations."""

    def claim_next(
        self,
        *,
        owning_application: str,
        effect_type: str,
        claimant_id: str,
        lease_seconds: int = 900,
    ) -> ClaimedEffect | None:
        """Claim and independently read back one exact unreceipted intent."""
        ...

    def renew_claim(self, claim: ClaimedEffect, *, lease_seconds: int = 900) -> None:
        """Renew the exact live claim."""
        ...

    def append_attempt(
        self,
        claim: ClaimedEffect,
        *,
        attempt_number: int,
        event_code: str,
        event_bytes: bytes,
    ) -> None:
        """Append one attempt under the live fence."""
        ...

    def record_receipt(
        self,
        record: EffectReceiptRecord,
    ) -> RecordedEffectReceipt:
        """Record or replay exactly one terminal receipt."""
        ...


@dataclass(frozen=True, slots=True)
class RegisteredEffectHandlerContext:
    """Dynamic worker facts admitted at claim and receipt time."""

    claimant_id: str
    at: str
    lease_seconds: int = 900


@dataclass(frozen=True, slots=True)
class RegisteredEffectHandlingResult:
    """One selected receipt and whether the register returned a replay."""

    effect_intent_id: str
    terminal_status: EffectReceiptStatus
    attempt_count: int
    receipt_bytes: bytes
    replayed: bool


@dataclass(frozen=True, slots=True)
class RegisteredEffectHandlerDependencies:
    """Ports and schemas required by one disabled handler revision."""

    handoff: RegisteredEffectHandoff
    authorities: CurrentExecutionActionAuthoritySource
    capabilities: CurrentCapabilityEvidenceSource
    effect_port: RegisteredEffectPort
    schemas: SchemaRegistry


class RegisteredEffectHandler:
    """Handle at most one exact effect type through an injected fake port."""

    def __init__(
        self,
        effect_type: str,
        dependencies: RegisteredEffectHandlerDependencies,
    ) -> None:
        """Bind one closed handler without registering it in the real runtime."""
        if not effect_type:
            message = "effect_type must not be empty"
            raise ValueError(message)
        self._effect_type = effect_type
        self._handoff = dependencies.handoff
        self._authorities = dependencies.authorities
        self._capabilities = dependencies.capabilities
        self._effect_port = dependencies.effect_port
        self._schemas = dependencies.schemas

    def handle_next(
        self,
        context: RegisteredEffectHandlerContext,
    ) -> RegisteredEffectHandlingResult | None:
        """Claim, revalidate, attempt/reconcile, and select one terminal receipt."""
        claim = self._handoff.claim_next(
            owning_application=ApplicationCode.PROMOTION_WORKER.value,
            effect_type=self._effect_type,
            claimant_id=context.claimant_id,
            lease_seconds=context.lease_seconds,
        )
        if claim is None:
            return None
        intent = self._intent_document(claim)
        authority = self._authorities.current(
            claim.aggregate_id,
            claim.effect_intent_id,
            context.at,
        )
        if authority is None:
            raise RegisteredEffectHandlerError(
                RegisteredEffectHandlerErrorCode.AUTHORITY_UNAVAILABLE
            )
        capability = self._capabilities.current(
            authority.action.capability_profile_ref.ref_id,
            context.at,
        )
        if capability is None:
            raise RegisteredEffectHandlerError(
                RegisteredEffectHandlerErrorCode.AUTHORITY_UNAVAILABLE
            )
        if (
            authority.evidence_ref.ref_type is not ReferenceType.EVIDENCE
            or capability.evidence_ref.ref_type is not ReferenceType.EVIDENCE
        ):
            raise RegisteredEffectHandlerError(
                RegisteredEffectHandlerErrorCode.AUTHORITY_UNAVAILABLE
            )
        authority_evidence = _ordered_evidence((authority.evidence_ref, capability.evidence_ref))
        if not _authority_is_current(claim, intent, authority) or not _capability_is_current(
            capability,
            authority.action,
            context.at,
        ):
            outcome = RegisteredEffectOutcome(
                EffectReceiptStatus.CANCELLED_BEFORE_EFFECT,
                authority_evidence,
                EffectCancelledDetail(authority_evidence),
            )
            return self._record(claim, intent, outcome, context.at, attempt_count=0)

        if claim.prior_attempt_count:
            outcome = self._effect_port.reconcile(claim.intent_bytes)
            return self._record(
                claim,
                intent,
                outcome,
                context.at,
                attempt_count=claim.prior_attempt_count,
            )
        self._handoff.renew_claim(claim, lease_seconds=context.lease_seconds)
        attempt_number = 1
        self._handoff.append_attempt(
            claim,
            attempt_number=attempt_number,
            event_code="STARTED",
            event_bytes=_attempt_bytes(
                claim,
                context.at,
                attempt_number,
                authority_evidence,
            ),
        )
        outcome = self._effect_port.perform(claim.intent_bytes, claim.fencing_token)
        return self._record(
            claim,
            intent,
            outcome,
            context.at,
            attempt_count=attempt_number,
        )

    def _intent_document(self, claim: ClaimedEffect) -> dict[str, JsonValue]:
        """Parse, schema-check, and fingerprint one claimed canonical intent."""
        if (
            sha256(claim.intent_bytes).digest() != claim.intent_fingerprint
            or claim.effect_type != self._effect_type
        ):
            raise RegisteredEffectHandlerError(RegisteredEffectHandlerErrorCode.INVALID_INTENT)
        parsed = parse_json_bytes(claim.intent_bytes, max_bytes=1_000_000)
        if not isinstance(parsed, dict) or canonicalize(parsed) != claim.intent_bytes:
            raise RegisteredEffectHandlerError(RegisteredEffectHandlerErrorCode.INVALID_INTENT)
        try:
            self._schemas.validate(
                parsed,
                "schemas/operation-domain.schema.json#/$defs/effect_intent",
            )
        except Exception as error:
            raise RegisteredEffectHandlerError(
                RegisteredEffectHandlerErrorCode.INVALID_INTENT
            ) from error
        return parsed

    def _record(
        self,
        claim: ClaimedEffect,
        intent: dict[str, JsonValue],
        outcome: RegisteredEffectOutcome,
        at: str,
        *,
        attempt_count: int,
    ) -> RegisteredEffectHandlingResult:
        """Construct, validate, and record the sole terminal receipt."""
        command_ref = _reference_from_value(intent.get("command_ref"))
        execution_ref = _reference_from_value(intent.get("execution_lineage_ref"))
        evidence = _ordered_evidence(outcome.evidence_refs)
        receipt = EffectReceipt(
            _stable_id("efr", claim.effect_intent_id),
            ImmutableReference(
                ReferenceType.EFFECT_INTENT,
                claim.effect_intent_id,
                f"sha256:{claim.intent_fingerprint.hex()}",
            ),
            command_ref,
            execution_ref,
            outcome.terminal_status,
            attempt_count,
            at,
            evidence,
            outcome.detail,
        )
        receipt_document = _receipt_document(receipt)
        self._schemas.validate(
            receipt_document,
            "schemas/operation-domain.schema.json#/$defs/effect_receipt",
        )
        receipt_bytes = canonicalize(receipt_document)
        attempted = outcome.terminal_status is not EffectReceiptStatus.CANCELLED_BEFORE_EFFECT
        selected = self._handoff.record_receipt(
            EffectReceiptRecord(
                receipt.effect_receipt_id,
                claim.effect_intent_id,
                receipt.terminal_status.value,
                attempt_count,
                receipt_bytes,
                sha256(receipt_bytes).digest(),
                claim.fencing_token if attempted else None,
                claim.claimant_id if attempted else None,
            )
        )
        if (
            selected.effect_receipt_id != receipt.effect_receipt_id
            or selected.effect_intent_id != claim.effect_intent_id
            or selected.terminal_status != receipt.terminal_status.value
            or selected.attempt_count != attempt_count
            or selected.receipt_bytes != receipt_bytes
        ):
            raise RegisteredEffectHandlerError(RegisteredEffectHandlerErrorCode.RECEIPT_REJECTED)
        return RegisteredEffectHandlingResult(
            claim.effect_intent_id,
            receipt.terminal_status,
            attempt_count,
            receipt_bytes,
            selected.replayed,
        )


_ACTION_INTENT_FIELDS = (
    "attempt_ceiling",
    "capability_profile_ref",
    "compensation",
    "deadline",
    "destination_class",
    "effect_command_fingerprint",
    "effect_type",
    "expected_remote_precondition_ref",
    "input_refs",
    "owning_application",
    "permitted_checkpoint",
    "required_capability",
    "retry_class",
    "stable_idempotency_key",
    "stop_conditions",
    "success_postcondition_ref",
)


def _authority_is_current(
    claim: ClaimedEffect,
    intent: dict[str, JsonValue],
    authority: CurrentExecutionActionAuthority,
) -> bool:
    action = authority.action
    action_document = promotion_action_authority_document(action)
    return (
        authority.active
        and authority.execution_lineage_ref.ref_type is ReferenceType.EXECUTION_LINEAGE
        and authority.execution_lineage_ref.ref_id == claim.aggregate_id
        and authority.evidence_ref.ref_type is ReferenceType.EVIDENCE
        and action.sequence == 1
        and action.effect_type.value == claim.effect_type
        and action.attempt_ceiling == claim.attempt_ceiling
        and all(intent.get(field) == action_document.get(field) for field in _ACTION_INTENT_FIELDS)
        and _reference_from_value(intent.get("aggregate_ref")) == authority.execution_lineage_ref
        and _reference_from_value(intent.get("execution_lineage_ref"))
        == authority.execution_lineage_ref
    )


def _capability_is_current(
    capability: CurrentCapabilityEvidence,
    action: PromotionActionAuthority,
    at: str,
) -> bool:
    return (
        capability.active
        and capability.profile_ref == action.capability_profile_ref
        and capability.owning_application is ApplicationCode.PROMOTION_WORKER
        and action.required_capability in capability.capabilities
        and capability.valid_from <= at < capability.valid_until
        and capability.evidence_ref.ref_type is ReferenceType.EVIDENCE
    )


def _attempt_bytes(
    claim: ClaimedEffect,
    at: str,
    attempt_number: int,
    evidence_refs: tuple[ImmutableReference, ...],
) -> bytes:
    return canonicalize(
        checked_json_value(
            {
                "attempt_number": attempt_number,
                "effect_intent_id": claim.effect_intent_id,
                "event_code": "STARTED",
                "evidence_refs": [_reference_document(item) for item in evidence_refs],
                "fencing_token": claim.fencing_token,
                "immutable": True,
                "recorded_at": at,
                "schema_id": "asklegal.effect-attempt-event",
                "schema_version": "1.0.0",
            }
        )
    )


def _receipt_document(receipt: EffectReceipt) -> dict[str, JsonValue]:
    value = checked_json_value(
        {
            "attempt_count": receipt.attempt_count,
            "command_ref": _reference_document(receipt.command_ref),
            "detail": _detail_document(receipt.detail),
            "effect_intent_ref": _reference_document(receipt.effect_intent_ref),
            "effect_receipt_id": receipt.effect_receipt_id,
            "evidence_refs": [_reference_document(item) for item in receipt.evidence_refs],
            "execution_lineage_ref": _reference_document(receipt.execution_lineage_ref),
            "immutable": True,
            "observed_at": receipt.observed_at,
            "schema_id": "asklegal.effect-receipt",
            "schema_version": "1.0.0",
            "terminal_status": receipt.terminal_status.value,
        }
    )
    if not isinstance(value, dict):
        raise RegisteredEffectHandlerError(RegisteredEffectHandlerErrorCode.INVALID_INTENT)
    return value


def _detail_document(detail: EffectReceiptDetail) -> dict[str, object]:
    if type(detail) is EffectSuccessDetail:
        return {
            "detail_type": "SUCCEEDED",
            "postcondition_evidence_refs": [
                _reference_document(item) for item in detail.postcondition_evidence_refs
            ],
            "provider_request_id": detail.provider_request_id,
            "remote_identity": detail.remote_identity,
            "remote_version": detail.remote_version,
            "response_fingerprint": detail.response_fingerprint,
        }
    if type(detail) is EffectFinalFailureDetail:
        return {
            "detail_type": "FAILED_FINAL",
            "failure_code": detail.failure_code.value,
            "failure_evidence_refs": [
                _reference_document(item) for item in detail.failure_evidence_refs
            ],
        }
    if type(detail) is EffectCancelledDetail:
        return {
            "cancellation_evidence_refs": [
                _reference_document(item) for item in detail.cancellation_evidence_refs
            ],
            "detail_type": "CANCELLED_BEFORE_EFFECT",
        }
    if type(detail) is EffectUnknownDetail:
        return {
            "detail_type": "OUTCOME_UNKNOWN",
            "failure_code": detail.failure_code.value,
            "reconciliation_evidence_refs": [
                _reference_document(item) for item in detail.reconciliation_evidence_refs
            ],
            "reconciliation_required": True,
        }
    raise RegisteredEffectHandlerError(RegisteredEffectHandlerErrorCode.INVALID_INTENT)


def _reference_from_value(value: JsonValue | None) -> ImmutableReference:
    if not isinstance(value, dict):
        raise RegisteredEffectHandlerError(RegisteredEffectHandlerErrorCode.INVALID_INTENT)
    ref_type = value.get("ref_type")
    ref_id = value.get("ref_id")
    reference_fingerprint = value.get("fingerprint")
    if (
        not isinstance(ref_type, str)
        or not isinstance(ref_id, str)
        or not isinstance(reference_fingerprint, str)
    ):
        raise RegisteredEffectHandlerError(RegisteredEffectHandlerErrorCode.INVALID_INTENT)
    try:
        return ImmutableReference(
            ReferenceType(ref_type),
            ref_id,
            reference_fingerprint,
        )
    except (TypeError, ValueError) as error:
        raise RegisteredEffectHandlerError(
            RegisteredEffectHandlerErrorCode.INVALID_INTENT
        ) from error


def _reference_document(reference: ImmutableReference) -> dict[str, str]:
    return {
        "fingerprint": reference.fingerprint,
        "ref_id": reference.ref_id,
        "ref_type": reference.ref_type.value,
    }


def _ordered_evidence(
    references: tuple[ImmutableReference, ...],
) -> tuple[ImmutableReference, ...]:
    if (
        type(references) is not tuple
        or not references
        or any(
            type(item) is not ImmutableReference or item.ref_type is not ReferenceType.EVIDENCE
            for item in references
        )
    ):
        message = "evidence references must be one non-empty exact tuple"
        raise TypeError(message)
    return tuple(
        sorted(
            set(references),
            key=lambda item: (item.ref_type.value, item.ref_id, item.fingerprint),
        )
    )


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"
