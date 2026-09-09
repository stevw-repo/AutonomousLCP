"""Atomic durable BEGIN of one authorized promotion execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from asklegal_contracts import SchemaRegistry, canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import (
    ApplicationCode,
    ContractReference,
    DeclaredCompensation,
    EffectCapability,
    EffectIntent,
    ImmutableReference,
    NoCompensation,
    ReferenceType,
)
from asklegal_management_register import RegisteredExecutionBeginCommand, V1CommandResult
from asklegal_promotion import (
    PromotionActionAuthority,
    promotion_action_authority_document,
    promotion_action_authority_fingerprint,
)

from .registered_approval import (
    RegisteredApprovalCandidate,
    RegisteredApprovalCandidateSource,
)

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMAND_ID = re.compile(r"^cmd_[0-9a-f]{48}$")
_LINEAGE_ID = re.compile(r"^exe_[0-9a-f]{48}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")
_BEGIN_AUTHORITATIVE_VERSION = 2


class RegisteredExecutionBeginErrorCode(StrEnum):
    """Closed pre-effect BEGIN failures."""

    CAPABILITY_INACTIVE = "REGISTERED_EXECUTION_BEGIN_CAPABILITY_INACTIVE"
    INVALID = "REGISTERED_EXECUTION_BEGIN_INVALID"
    NOT_APPROVED = "REGISTERED_EXECUTION_BEGIN_NOT_APPROVED"
    REJECTED = "REGISTERED_EXECUTION_BEGIN_REJECTED"


class RegisteredExecutionBeginError(RuntimeError):
    """One safe failure before any effect can be claimed."""

    def __init__(self, code: RegisteredExecutionBeginErrorCode) -> None:
        """Create one closed failure without provider or identity data."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class CurrentCapabilityEvidence:
    """Current exact evidence that one manifest capability profile is active."""

    profile_ref: ImmutableReference
    owning_application: ApplicationCode
    capabilities: frozenset[EffectCapability]
    active: bool
    valid_from: str
    valid_until: str
    evidence_ref: ImmutableReference


class CurrentCapabilityEvidenceSource(Protocol):
    """Current capability lookup used immediately before atomic BEGIN."""

    def current(self, profile_id: str, at: str) -> CurrentCapabilityEvidence | None:
        """Return exact current evidence for one profile, if available."""
        ...


@dataclass(frozen=True, slots=True)
class RegisteredExecutionBeginContext:
    """Dynamic facts permitted at the durable BEGIN boundary."""

    at: str
    command_expires_at: str
    execution_lineage_id: str
    execution_lineage_fingerprint: str
    authorization_fingerprint: str
    promotion_worker_identity_id: str
    promotion_worker_identity_fingerprint: str


class RegisteredExecutionBeginWriter(Protocol):
    """Specialized Promotion-owned BEGIN and first-intent command."""

    def begin(
        self,
        command: RegisteredExecutionBeginCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Commit BEGIN and its first intent atomically or resolve replay."""
        ...


class RegisteredExecutionBeginService:
    """Create the first exact Effect Intent from approved action bytes."""

    def __init__(
        self,
        candidates: RegisteredApprovalCandidateSource,
        capabilities: CurrentCapabilityEvidenceSource,
        writer: RegisteredExecutionBeginWriter,
        schemas: SchemaRegistry,
    ) -> None:
        """Bind complete reread, current capability evidence, writer, and schemas."""
        self._candidates = candidates
        self._capabilities = capabilities
        self._writer = writer
        self._schemas = schemas

    def begin(
        self,
        proposal_package_id: str,
        command_id: str,
        context: RegisteredExecutionBeginContext,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Atomically enter RUNNING and append only the first approved intent."""
        candidate = self._candidates.approved(proposal_package_id)
        if candidate is None:
            raise RegisteredExecutionBeginError(RegisteredExecutionBeginErrorCode.NOT_APPROVED)
        action = _first_action(candidate)
        _validate_context(candidate, proposal_package_id, command_id, context, action)
        capability = _require_capability(
            self._capabilities.current(action.capability_profile_ref.ref_id, context.at),
            action,
            context,
        )

        action_fingerprint = promotion_action_authority_fingerprint(action)
        effect_intent_id = _stable_id(
            "efi",
            context.execution_lineage_id,
            candidate.manifest.fingerprint,
            action_fingerprint,
            capability.evidence_ref.fingerprint,
        )
        command_document = checked_json_value(
            {
                "action": "BEGIN_REGISTERED_PROMOTION_EXECUTION",
                "action_authority": promotion_action_authority_document(action),
                "action_contract_version": candidate.manifest.action_contract_version,
                "action_fingerprint": action_fingerprint,
                "approval_id": candidate.approval_id,
                "authorization_fingerprint": context.authorization_fingerprint,
                "capability_evidence_ref": _reference_document(capability.evidence_ref),
                "effect_intent_id": effect_intent_id,
                "execution_lineage_fingerprint": context.execution_lineage_fingerprint,
                "execution_lineage_id": context.execution_lineage_id,
                "manifest_fingerprint": candidate.manifest.fingerprint,
                "manifest_id": candidate.manifest.manifest_id,
                "promotion_worker_identity_fingerprint": (
                    context.promotion_worker_identity_fingerprint
                ),
                "promotion_worker_identity_id": context.promotion_worker_identity_id,
                "proposal_package_id": candidate.proposal_package_id,
            }
        )
        command_bytes = canonicalize(command_document)
        command_fingerprint = f"sha256:{sha256(command_bytes).hexdigest()}"
        intent = _effect_intent(
            action,
            command_id,
            command_fingerprint,
            context,
            effect_intent_id,
        )
        intent_document = effect_intent_document(intent)
        self._schemas.validate(
            intent_document,
            "schemas/operation-domain.schema.json#/$defs/effect_intent",
        )
        intent_bytes = canonicalize(intent_document)
        event_id = _stable_id("pex", command_fingerprint)
        event_document = checked_json_value(
            {
                "action_id": "BEGIN",
                "approval_ref": _reference(
                    "APPROVAL", candidate.approval_id, candidate.decision_fingerprint
                ),
                "attempt_number": 0,
                "event_time": context.at,
                "execution_lineage_id": context.execution_lineage_id,
                "external_effects": "DECLARED_MANIFEST_ACTION",
                "failure_codes": [],
                "from_state": "EXECUTION_AUTHORIZED",
                "idempotency": {
                    "idempotency_key": f"begin:{context.execution_lineage_id}",
                    "input_fingerprint": command_fingerprint,
                },
                "immutable": True,
                "promotion_execution_event_id": event_id,
                "promotion_manifest_ref": _reference(
                    "PROMOTION_MANIFEST",
                    candidate.manifest.manifest_id,
                    candidate.manifest.fingerprint,
                ),
                "reason_codes": [
                    "APPROVAL_EXACTLY_BOUND",
                    "REFERENCE_VERIFIED",
                    "TRANSITION_ALLOWED",
                    "VALIDATION_COMPLETE",
                ],
                "receipt_refs": [],
                "result_code": "SUCCEEDED",
                "schema_id": "asklegal.promotion-execution-event",
                "schema_version": "1.0.0",
                "to_state": "EXECUTION_RUNNING",
            }
        )
        self._schemas.validate(
            event_document,
            "schemas/promotion-domain.schema.json#/$defs/promotion_execution_event",
        )
        result = self._writer.begin(
            RegisteredExecutionBeginCommand(
                command_id,
                command_bytes,
                candidate.approval_id,
                candidate.proposal_package_id,
                bytes.fromhex(candidate.decision_fingerprint.removeprefix("sha256:")),
                candidate.manifest.manifest_id,
                candidate.manifest.fingerprint,
                context.execution_lineage_id,
                context.execution_lineage_fingerprint,
                context.authorization_fingerprint,
                action.action_id,
                action_fingerprint,
                action.capability_profile_ref.ref_id,
                action.capability_profile_ref.fingerprint,
                capability.evidence_ref.ref_id,
                capability.evidence_ref.fingerprint,
                context.command_expires_at,
                event_id,
                canonicalize(event_document),
                effect_intent_id,
                action.effect_type.value,
                intent_bytes,
                action.deadline,
                action.attempt_ceiling,
            ),
            simulate_lost_ack=simulate_lost_ack,
        )
        if (
            result.result_code != "APPLIED"
            or result.authoritative_version != _BEGIN_AUTHORITATIVE_VERSION
        ):
            raise RegisteredExecutionBeginError(RegisteredExecutionBeginErrorCode.REJECTED)
        return result


def _first_action(candidate: RegisteredApprovalCandidate) -> PromotionActionAuthority:
    actions = candidate.manifest.actions
    if candidate.manifest.action_contract_version != "1.0.0" or not actions:
        raise RegisteredExecutionBeginError(RegisteredExecutionBeginErrorCode.INVALID)
    return actions[0]


def _validate_context(
    candidate: RegisteredApprovalCandidate,
    proposal_package_id: str,
    command_id: str,
    context: RegisteredExecutionBeginContext,
    action: PromotionActionAuthority,
) -> None:
    identifiers = (
        candidate.proposal_package_id,
        candidate.approval_id,
        candidate.manifest.manifest_id,
        context.promotion_worker_identity_id,
    )
    fingerprints = (
        candidate.decision_fingerprint,
        candidate.manifest.fingerprint,
        context.execution_lineage_fingerprint,
        context.authorization_fingerprint,
        context.promotion_worker_identity_fingerprint,
    )
    if (
        candidate.proposal_package_id != proposal_package_id
        or _COMMAND_ID.fullmatch(command_id) is None
        or _LINEAGE_ID.fullmatch(context.execution_lineage_id) is None
        or any(_IDENTIFIER.fullmatch(value) is None for value in identifiers)
        or any(_FINGERPRINT.fullmatch(value) is None for value in fingerprints)
        or not context.at < context.command_expires_at <= action.deadline
    ):
        raise RegisteredExecutionBeginError(RegisteredExecutionBeginErrorCode.INVALID)


def _require_capability(
    capability: CurrentCapabilityEvidence | None,
    action: PromotionActionAuthority,
    context: RegisteredExecutionBeginContext,
) -> CurrentCapabilityEvidence:
    if (
        capability is None
        or not capability.active
        or capability.profile_ref != action.capability_profile_ref
        or capability.owning_application is not ApplicationCode.PROMOTION_WORKER
        or action.required_capability not in capability.capabilities
        or not capability.valid_from <= context.at < capability.valid_until
        or capability.evidence_ref.ref_type is not ReferenceType.EVIDENCE
    ):
        raise RegisteredExecutionBeginError(RegisteredExecutionBeginErrorCode.CAPABILITY_INACTIVE)
    return capability


def _effect_intent(
    action: PromotionActionAuthority,
    command_id: str,
    command_fingerprint: str,
    context: RegisteredExecutionBeginContext,
    effect_intent_id: str,
) -> EffectIntent:
    lineage_ref = ImmutableReference(
        ReferenceType.EXECUTION_LINEAGE,
        context.execution_lineage_id,
        context.execution_lineage_fingerprint,
    )
    return EffectIntent(
        effect_intent_id,
        context.at,
        action.effect_type,
        action.owning_application,
        lineage_ref,
        ImmutableReference(ReferenceType.COMMAND, command_id, command_fingerprint),
        lineage_ref,
        action.permitted_checkpoint,
        action.input_refs,
        action.effect_command_fingerprint,
        action.required_capability,
        action.capability_profile_ref,
        action.destination_class,
        action.stable_idempotency_key,
        action.retry_class,
        action.attempt_ceiling,
        action.deadline,
        action.stop_conditions,
        action.expected_remote_precondition_ref,
        action.success_postcondition_ref,
        action.compensation,
    )


def effect_intent_document(intent: EffectIntent) -> dict[str, JsonValue]:
    """Return the canonical registered representation of one effect intent."""
    value = checked_json_value(
        {
            "aggregate_ref": _reference_document(intent.aggregate_ref),
            "attempt_ceiling": intent.attempt_ceiling,
            "capability_profile_ref": _reference_document(intent.capability_profile_ref),
            "command_ref": _reference_document(intent.command_ref),
            "compensation": _compensation_document(intent.compensation),
            "created_at": intent.created_at,
            "deadline": intent.deadline,
            "destination_class": intent.destination_class.value,
            "effect_command_fingerprint": intent.effect_command_fingerprint,
            "effect_intent_id": intent.effect_intent_id,
            "effect_type": intent.effect_type.value,
            "execution_lineage_ref": _reference_document(intent.execution_lineage_ref),
            "expected_remote_precondition_ref": _contract_document(
                intent.expected_remote_precondition_ref
            ),
            "immutable": True,
            "input_refs": [_reference_document(item) for item in intent.input_refs],
            "owning_application": intent.owning_application.value,
            "permitted_checkpoint": intent.permitted_checkpoint,
            "required_capability": intent.required_capability.value,
            "retry_class": intent.retry_class.value,
            "schema_id": "asklegal.effect-intent",
            "schema_version": "1.0.0",
            "stable_idempotency_key": intent.stable_idempotency_key,
            "stop_conditions": [item.value for item in intent.stop_conditions],
            "success_postcondition_ref": _contract_document(intent.success_postcondition_ref),
        }
    )
    if not isinstance(value, dict):
        raise RegisteredExecutionBeginError(RegisteredExecutionBeginErrorCode.INVALID)
    return value


def _reference_document(reference: ImmutableReference) -> dict[str, str]:
    return _reference(reference.ref_type.value, reference.ref_id, reference.fingerprint)


def _reference(
    reference_type: str, reference_id: str, reference_fingerprint: str
) -> dict[str, str]:
    return {
        "fingerprint": reference_fingerprint,
        "ref_id": reference_id,
        "ref_type": reference_type,
    }


def _contract_document(reference: ContractReference) -> dict[str, str]:
    return {
        "contract_id": reference.contract_id,
        "fingerprint": reference.fingerprint,
        "version": reference.version,
    }


def _compensation_document(
    compensation: NoCompensation | DeclaredCompensation,
) -> dict[str, object]:
    if type(compensation) is NoCompensation:
        return {"mode": "NO_COMPENSATION"}
    if type(compensation) is DeclaredCompensation:
        return {
            "contract_ref": _contract_document(compensation.contract_ref),
            "mode": "DECLARED_COMPENSATION",
        }
    raise RegisteredExecutionBeginError(RegisteredExecutionBeginErrorCode.INVALID)


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"
