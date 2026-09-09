"""Pure fingerprint, manifest, embedding-request, and target-name construction."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import PROPOSAL_ROLE_PATHS, verify_v1_coverage_release_gate
from asklegal_domain import (
    ApplicationCode,
    ContractReference,
    DeclaredCompensation,
    DestinationClass,
    DomainInvariantError,
    EffectCapability,
    EffectType,
    ImmutableReference,
    NoCompensation,
    ReferenceType,
    RetryClass,
    StopCondition,
)
from asklegal_evidence_vault import ExactObjectReference, VaultName

from .model import (
    EmbeddingProfile,
    EmbeddingProfileInput,
    EmbeddingRequest,
    EmbeddingRequestInput,
    PromotionActionAuthority,
    PromotionApprovalSnapshot,
    PromotionError,
    PromotionErrorCode,
    PromotionManifest,
    PromotionPlan,
    ProposalMemberReceipt,
    StoredProposalPackage,
    TargetRecord,
    TraceabilityShardReceipt,
)
from .ports import EmbeddingTokenCounter

_INDEX_NAME_LIMIT = 40
_PROJECT_INDEX_NAME_LIMIT = 52
_PREDICATE_PARTS = 3
_ACTION_CONTRACT_VERSION = "1.0.0"
_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_TIMESTAMP = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,9})?Z$"
)
_PROMOTION_EFFECT_BINDINGS = {
    EffectType.BACKUP_MUTATION: (
        EffectCapability.MANAGE_BACKUP,
        DestinationClass.BACKUP_STORE,
    ),
    EffectType.EMBEDDING_PROVIDER_CALL: (
        EffectCapability.CALL_EMBEDDING_PROVIDER,
        DestinationClass.EMBEDDING_PROVIDER,
    ),
    EffectType.PINECONE_MUTATION: (
        EffectCapability.MUTATE_PINECONE,
        DestinationClass.SERVING_TARGET,
    ),
    EffectType.RELEASE_PUBLICATION: (
        EffectCapability.PUBLISH_RELEASE,
        DestinationClass.RELEASE_STORE,
    ),
    EffectType.ROUTING_ACTIVATION: (
        EffectCapability.ACTIVATE_ROUTING,
        DestinationClass.ROUTING_TARGET,
    ),
}
_MANDATORY_STOP_CONDITIONS = frozenset(
    {
        StopCondition.ATTEMPT_CEILING,
        StopCondition.AUTHORITY_INVALID,
        StopCondition.CANCELLATION_BEFORE_EFFECT,
        StopCondition.CAPABILITY_INACTIVE,
        StopCondition.DEADLINE,
        StopCondition.POSTCONDITION_MET,
        StopCondition.PRECONDITION_CHANGED,
    }
)


@dataclass(frozen=True, slots=True)
class _ActionBindings:
    candidate_serving_state_fingerprint: str
    desired_state_fingerprint: str
    embedding_profile_fingerprint: str
    valid_from: str
    valid_until: str


SERVING_METADATA_KEYS = (
    "authority_note",
    "country",
    "jurisdiction",
    "source",
    "text",
    "type",
)
"""The exact closed property set of the serving payload, in canonical order."""

_SERVING_METADATA_LIMIT = 40_000
"""The target rejects a metadata object above 40 KB. Refusing beats truncating a warning."""


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _canonical(value: object) -> bytes:
    return canonicalize(checked_json_value(value))


def serving_metadata(record: TargetRecord) -> dict[str, str]:
    """Build exactly the six-property serving payload one record must carry.

    Built from the contract rather than from the caller, so a field the caller
    forgot is a refused write rather than a record that lands without it.
    """
    payload = {
        "authority_note": record.authority_note,
        "country": record.country,
        "jurisdiction": record.jurisdiction,
        "source": record.source,
        "text": record.metadata_text,
        "type": record.material_type,
    }
    empty = sorted(key for key, value in payload.items() if not value)
    if empty:
        message = f"record {record.record_id} carries no {', '.join(empty)}"
        raise PromotionError(PromotionErrorCode.SERVING_PAYLOAD_INVALID, message)
    encoded = _canonical(payload)
    if len(encoded) > _SERVING_METADATA_LIMIT:
        message = (
            f"record {record.record_id} payload is {len(encoded)} bytes, "
            f"over the {_SERVING_METADATA_LIMIT} limit"
        )
        raise PromotionError(PromotionErrorCode.SERVING_PAYLOAD_INVALID, message)
    return payload


def serving_metadata_fingerprint(payload: dict[str, str]) -> str:
    """Fingerprint exactly the six-field payload, as the corpus release does.

    The same bytes over the same closed key set, so a fingerprint computed here
    equals the `serving_payload_fingerprint` the approved release carries.
    """
    if set(payload) != set(SERVING_METADATA_KEYS):
        message = f"payload keys {sorted(payload)} are not the six serving fields"
        raise PromotionError(PromotionErrorCode.SERVING_PAYLOAD_INVALID, message)
    return _fingerprint(_canonical(dict(payload)))


def _embedding_profile_body(profile: EmbeddingProfile) -> dict[str, object]:
    return {
        "allowed_environments": list(profile.allowed_environments),
        "api_contract": profile.api_contract,
        "cost_limit_microunits": profile.cost_limit_microunits,
        "deployment_name": profile.deployment_name,
        "dimensions": profile.dimensions,
        "encoding": profile.encoding,
        "expires_at": profile.expires_at,
        "geography_class": profile.geography_class,
        "max_input_tokens": profile.max_input_tokens,
        "metric": profile.metric,
        "model_id": profile.model_id,
        "model_version": profile.model_version,
        "normalization": profile.normalization,
        "provider": profile.provider,
        "resource_class": profile.resource_class,
        "stateful_features": profile.stateful_features,
        "tokenizer": profile.tokenizer,
    }


def verify_embedding_profile(profile: EmbeddingProfile) -> None:
    """Reject a profile whose issued identity or fingerprint does not match its fields."""
    fingerprint = _fingerprint(canonicalize(checked_json_value(_embedding_profile_body(profile))))
    if profile.profile_fingerprint != fingerprint or profile.profile_id != _stable_id(
        "emp", fingerprint
    ):
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "profile fingerprint")


def freeze_embedding_profile(inputs: EmbeddingProfileInput) -> EmbeddingProfile:
    """Issue one fingerprinted immutable embedding profile."""
    provisional = EmbeddingProfile(
        "",
        "",
        inputs.provider,
        inputs.resource_class,
        inputs.geography_class,
        inputs.deployment_name,
        inputs.model_id,
        inputs.model_version,
        inputs.api_contract,
        inputs.tokenizer,
        inputs.dimensions,
        inputs.encoding,
        inputs.normalization,
        inputs.metric,
        inputs.max_input_tokens,
        inputs.cost_limit_microunits,
        inputs.expires_at,
        inputs.allowed_environments,
        inputs.stateful_features,
    )
    fingerprint = _fingerprint(
        canonicalize(checked_json_value(_embedding_profile_body(provisional)))
    )
    return EmbeddingProfile(
        _stable_id("emp", fingerprint),
        fingerprint,
        provisional.provider,
        provisional.resource_class,
        provisional.geography_class,
        provisional.deployment_name,
        provisional.model_id,
        provisional.model_version,
        provisional.api_contract,
        provisional.tokenizer,
        provisional.dimensions,
        provisional.encoding,
        provisional.normalization,
        provisional.metric,
        provisional.max_input_tokens,
        provisional.cost_limit_microunits,
        provisional.expires_at,
        provisional.allowed_environments,
        provisional.stateful_features,
    )


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def _reference_body(reference: ImmutableReference) -> dict[str, str]:
    return {
        "fingerprint": reference.fingerprint,
        "ref_id": reference.ref_id,
        "ref_type": reference.ref_type.value,
    }


def _contract_reference_body(reference: ContractReference) -> dict[str, str]:
    return {
        "contract_id": reference.contract_id,
        "fingerprint": reference.fingerprint,
        "version": reference.version,
    }


def _compensation_body(
    compensation: NoCompensation | DeclaredCompensation,
) -> dict[str, object]:
    if type(compensation) is NoCompensation:
        return {"mode": "NO_COMPENSATION"}
    if type(compensation) is DeclaredCompensation:
        return {
            "contract_ref": _contract_reference_body(compensation.contract_ref),
            "mode": "DECLARED_COMPENSATION",
        }
    raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action compensation")


def _action_body(action: PromotionActionAuthority) -> dict[str, object]:
    return {
        "action_id": action.action_id,
        "attempt_ceiling": action.attempt_ceiling,
        "capability_profile_ref": _reference_body(action.capability_profile_ref),
        "compensation": _compensation_body(action.compensation),
        "deadline": action.deadline,
        "destination_class": action.destination_class.value,
        "effect_command_fingerprint": action.effect_command_fingerprint,
        "effect_type": action.effect_type.value,
        "expected_remote_precondition_ref": _contract_reference_body(
            action.expected_remote_precondition_ref
        ),
        "input_refs": [_reference_body(item) for item in action.input_refs],
        "owning_application": action.owning_application.value,
        "permitted_checkpoint": action.permitted_checkpoint,
        "required_capability": action.required_capability.value,
        "retry_class": action.retry_class.value,
        "sequence": action.sequence,
        "stable_idempotency_key": action.stable_idempotency_key,
        "stop_conditions": [item.value for item in action.stop_conditions],
        "success_postcondition_ref": _contract_reference_body(action.success_postcondition_ref),
    }


def promotion_action_authority_document(
    action: PromotionActionAuthority,
) -> dict[str, JsonValue]:
    """Render one canonicalizable action-authority object without enabling it."""
    value = checked_json_value(_action_body(action))
    if not isinstance(value, dict):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action authority")
    return value


def promotion_action_authority_fingerprint(action: PromotionActionAuthority) -> str:
    """Fingerprint exactly the action-authority bytes approved in the manifest."""
    return _fingerprint(canonicalize(promotion_action_authority_document(action)))


def _validate_action_authorities(
    contract_version: str,
    actions: tuple[PromotionActionAuthority, ...],
    bindings: _ActionBindings,
) -> None:
    if contract_version != _ACTION_CONTRACT_VERSION:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action contract version")
    if (
        type(actions) is not tuple
        or not actions
        or any(type(action) is not PromotionActionAuthority for action in actions)
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "actions")
    if tuple(action.sequence for action in actions) != tuple(range(1, len(actions) + 1)):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action sequence")
    action_ids = tuple(action.action_id for action in actions)
    idempotency_keys = tuple(action.stable_idempotency_key for action in actions)
    if len(set(action_ids)) != len(action_ids) or len(set(idempotency_keys)) != len(
        idempotency_keys
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action identity")
    for action in actions:
        _validate_action_authority(
            action,
            valid_from=bindings.valid_from,
            valid_until=bindings.valid_until,
        )
        refs = {(item.ref_type, item.fingerprint) for item in action.input_refs}
        required_refs = {
            EffectType.EMBEDDING_PROVIDER_CALL: {
                (ReferenceType.DESIRED_STATE_INVENTORY, bindings.desired_state_fingerprint),
                (ReferenceType.EMBEDDING_PROFILE, bindings.embedding_profile_fingerprint),
            },
            EffectType.PINECONE_MUTATION: {
                (ReferenceType.DESIRED_STATE_INVENTORY, bindings.desired_state_fingerprint),
                (ReferenceType.SERVING_STATE, bindings.candidate_serving_state_fingerprint),
            },
            EffectType.BACKUP_MUTATION: {
                (ReferenceType.SERVING_STATE, bindings.candidate_serving_state_fingerprint),
            },
            EffectType.RELEASE_PUBLICATION: {
                (ReferenceType.DESIRED_STATE_INVENTORY, bindings.desired_state_fingerprint),
            },
            EffectType.ROUTING_ACTIVATION: {
                (ReferenceType.SERVING_STATE, bindings.candidate_serving_state_fingerprint),
            },
        }[action.effect_type]
        if not required_refs.issubset(refs):
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action input binding")


def _validate_action_authority(
    action: PromotionActionAuthority,
    *,
    valid_from: str,
    valid_until: str,
) -> None:
    if (
        _CODE.fullmatch(action.action_id) is None
        or _CODE.fullmatch(action.permitted_checkpoint) is None
        or action.owning_application is not ApplicationCode.PROMOTION_WORKER
        or type(action.effect_type) is not EffectType
        or action.effect_type not in _PROMOTION_EFFECT_BINDINGS
        or type(action.required_capability) is not EffectCapability
        or type(action.destination_class) is not DestinationClass
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action authority")
    capability, destination = _PROMOTION_EFFECT_BINDINGS[action.effect_type]
    if action.required_capability is not capability or action.destination_class is not destination:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action effect binding")
    references = action.input_refs
    if (
        type(references) is not tuple
        or not references
        or any(type(item) is not ImmutableReference for item in references)
        or type(action.capability_profile_ref) is not ImmutableReference
        or action.capability_profile_ref.ref_type is not ReferenceType.CAPABILITY_PROFILE
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action references")
    reference_keys = tuple(
        (item.ref_type.value, item.ref_id, item.fingerprint) for item in references
    )
    if reference_keys != tuple(sorted(set(reference_keys))):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action references")
    if (
        _FINGERPRINT.fullmatch(action.effect_command_fingerprint) is None
        or not action.stable_idempotency_key
        or action.stable_idempotency_key.strip() != action.stable_idempotency_key
        or type(action.retry_class) is not RetryClass
        or type(action.attempt_ceiling) is not int
        or action.attempt_ceiling < 1
        or (action.retry_class is RetryClass.NEVER and action.attempt_ceiling != 1)
        or _TIMESTAMP.fullmatch(action.deadline) is None
        or not (valid_from < action.deadline <= valid_until)
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action retry authority")
    stop_conditions = action.stop_conditions
    if (
        type(stop_conditions) is not tuple
        or any(type(item) is not StopCondition for item in stop_conditions)
        or tuple(item.value for item in stop_conditions)
        != tuple(sorted({item.value for item in stop_conditions}))
        or frozenset(stop_conditions) != _MANDATORY_STOP_CONDITIONS
        or type(action.expected_remote_precondition_ref) is not ContractReference
        or type(action.success_postcondition_ref) is not ContractReference
        or type(action.compensation) not in {NoCompensation, DeclaredCompensation}
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action completion authority")


def _manifest_body(plan: PromotionPlan) -> dict[str, object]:
    return {
        "action_contract_version": plan.action_contract_version,
        "actions": [_action_body(item) for item in plan.actions],
        "base_serving_state_id": plan.base_serving_state_id,
        "batch_size": plan.batch_size,
        "candidate_serving_state_fingerprint": plan.candidate_serving_state_fingerprint,
        "candidate_serving_state_id": plan.candidate_serving_state_id,
        "coverage_fingerprint": plan.coverage_status.fingerprint,
        "desired_state_fingerprint": plan.desired_state.inventory_fingerprint,
        "embedding_profile_fingerprint": plan.embedding_profile.profile_fingerprint,
        "environment": plan.environment,
        "exact_retirement_target_ids": list(plan.exact_retirement_target_ids),
        "freeze_date": plan.freeze_date,
        "jurisdiction": plan.jurisdiction,
        "project_id": plan.project_id,
        "rollback_serving_state_id": plan.rollback_serving_state_id,
        "valid_from": plan.valid_from,
        "valid_until": plan.valid_until,
        "validity_predicates": [list(item) for item in plan.validity_predicates],
    }


def freeze_generic_promotion_manifest(plan: PromotionPlan) -> PromotionManifest:
    """Freeze an explicitly non-V1 compatibility manifest without authorizing effects."""
    if (
        plan.batch_size < 1
        or not plan.validity_predicates
        or len(plan.validity_predicates) != len(set(plan.validity_predicates))
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "manifest inputs")
    _validate_action_authorities(
        plan.action_contract_version,
        plan.actions,
        _ActionBindings(
            plan.candidate_serving_state_fingerprint,
            plan.desired_state.inventory_fingerprint,
            plan.embedding_profile.profile_fingerprint,
            plan.valid_from,
            plan.valid_until,
        ),
    )
    body = _manifest_body(plan)
    fingerprint = _fingerprint(canonicalize(checked_json_value(body)))
    return PromotionManifest(
        _stable_id("pmn", fingerprint),
        fingerprint,
        plan.environment,
        plan.jurisdiction,
        plan.freeze_date,
        plan.valid_from,
        plan.valid_until,
        plan.base_serving_state_id,
        plan.candidate_serving_state_id,
        plan.candidate_serving_state_fingerprint,
        plan.rollback_serving_state_id,
        plan.desired_state,
        plan.coverage_status,
        plan.embedding_profile,
        plan.validity_predicates,
        plan.batch_size,
        plan.project_id,
        plan.action_contract_version,
        plan.actions,
        plan.exact_retirement_target_ids,
    )


def freeze_v1_promotion_manifest(plan: PromotionPlan) -> PromotionManifest:
    """Freeze the canonical V1 form, whose activation is Serving State only."""
    verify_v1_coverage_release_gate(plan.coverage_status)
    validate_hk_v1_effect_types(tuple(action.effect_type for action in plan.actions))
    return freeze_generic_promotion_manifest(plan)


def freeze_hk_v1_promotion_manifest(plan: PromotionPlan) -> PromotionManifest:
    """Compatibility alias for the canonical V1 manifest entry point."""
    return freeze_v1_promotion_manifest(plan)


def validate_hk_v1_effect_types(effect_types: tuple[EffectType, ...]) -> None:
    """Reject excluded Ask.Legal route authority before freezing the V1 manifest."""
    if EffectType.ROUTING_ACTIVATION in effect_types:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "V1 has no routing action")
    if EffectType.RELEASE_PUBLICATION not in effect_types:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "V1 requires release publication")


def verify_promotion_manifest(manifest: PromotionManifest) -> None:
    """Verify one canonical V1 manifest, including its no-routing action guard."""
    _verify_manifest(manifest, freeze_v1_promotion_manifest)


def verify_generic_promotion_manifest(manifest: PromotionManifest) -> None:
    """Verify an explicit non-V1 compatibility manifest."""
    _verify_manifest(manifest, freeze_generic_promotion_manifest)


def _verify_manifest(
    manifest: PromotionManifest, freezer: Callable[[PromotionPlan], PromotionManifest]
) -> None:
    """Re-freeze one typed manifest through exactly its selected lifecycle path."""
    plan = PromotionPlan(
        manifest.environment,
        manifest.jurisdiction,
        manifest.freeze_date,
        manifest.valid_from,
        manifest.valid_until,
        manifest.base_serving_state_id,
        manifest.candidate_serving_state_id,
        manifest.candidate_serving_state_fingerprint,
        manifest.rollback_serving_state_id,
        manifest.desired_state,
        manifest.coverage_status,
        manifest.embedding_profile,
        manifest.validity_predicates,
        manifest.batch_size,
        manifest.project_id,
        manifest.action_contract_version,
        manifest.actions,
        manifest.exact_retirement_target_ids,
    )
    refrozen = freezer(plan)
    if refrozen.manifest_id != manifest.manifest_id or refrozen.fingerprint != manifest.fingerprint:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT)


def promotion_manifest_bytes(manifest: PromotionManifest) -> bytes:
    """Render the exact canonical bytes whose fingerprint identifies the manifest."""
    verify_generic_promotion_manifest(manifest)
    plan = PromotionPlan(
        manifest.environment,
        manifest.jurisdiction,
        manifest.freeze_date,
        manifest.valid_from,
        manifest.valid_until,
        manifest.base_serving_state_id,
        manifest.candidate_serving_state_id,
        manifest.candidate_serving_state_fingerprint,
        manifest.rollback_serving_state_id,
        manifest.desired_state,
        manifest.coverage_status,
        manifest.embedding_profile,
        manifest.validity_predicates,
        manifest.batch_size,
        manifest.project_id,
        manifest.action_contract_version,
        manifest.actions,
        manifest.exact_retirement_target_ids,
    )
    return canonicalize(checked_json_value(_manifest_body(plan)))


def promotion_approval_snapshot_from_bytes(
    content: bytes,
    *,
    expected_manifest_id: str,
    expected_fingerprint: str,
) -> PromotionApprovalSnapshot:
    """Recover only exact Approval facts from one canonical executable manifest."""
    try:
        document = parse_json_bytes(content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise PromotionError(
            PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest JSON"
        ) from error
    expected_fields = {
        "action_contract_version",
        "actions",
        "base_serving_state_id",
        "batch_size",
        "candidate_serving_state_fingerprint",
        "candidate_serving_state_id",
        "coverage_fingerprint",
        "desired_state_fingerprint",
        "embedding_profile_fingerprint",
        "environment",
        "exact_retirement_target_ids",
        "freeze_date",
        "jurisdiction",
        "project_id",
        "rollback_serving_state_id",
        "valid_from",
        "valid_until",
        "validity_predicates",
    }
    if not isinstance(document, dict) or set(document) != expected_fields:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest fields")
    if canonicalize(document) != content:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest canonical")
    actual_fingerprint = _fingerprint(content)
    if (
        actual_fingerprint != expected_fingerprint
        or _stable_id("pmn", actual_fingerprint) != expected_manifest_id
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest identity")

    action_contract_version = _json_text(document, "action_contract_version")
    actions = _json_action_authorities(document)
    retirements = _json_string_sequence(document, "exact_retirement_target_ids")
    predicates = _json_predicates(document)
    valid_from = _json_text(document, "valid_from")
    valid_until = _json_text(document, "valid_until")
    fingerprints = (
        _json_text(document, "candidate_serving_state_fingerprint"),
        _json_text(document, "coverage_fingerprint"),
        _json_text(document, "desired_state_fingerprint"),
        _json_text(document, "embedding_profile_fingerprint"),
    )
    if (
        len(retirements) != len(set(retirements))
        or not predicates
        or len(predicates) != len(set(predicates))
        or valid_from >= valid_until
        or any(re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None for value in fingerprints)
        or _json_integer(document, "batch_size") < 1
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest values")
    _validate_action_authorities(
        action_contract_version,
        actions,
        _ActionBindings(
            fingerprints[0],
            fingerprints[2],
            fingerprints[3],
            valid_from,
            valid_until,
        ),
    )
    for field in (
        "environment",
        "freeze_date",
        "jurisdiction",
        "project_id",
        "rollback_serving_state_id",
    ):
        _json_text(document, field)
    return PromotionApprovalSnapshot(
        expected_manifest_id,
        expected_fingerprint,
        _json_text(document, "base_serving_state_id"),
        _json_text(document, "candidate_serving_state_id"),
        valid_from,
        valid_until,
        predicates,
        action_contract_version,
        actions,
    )


def pinecone_index_name(
    environment: str,
    jurisdiction: str,
    freeze_date: str,
    state_fingerprint: str,
    project_id: str,
) -> str:
    """Apply the accepted exact final Pinecone naming contract."""
    if (
        environment not in {"dev", "stg", "prd"}
        or re.fullmatch(r"[a-z0-9]{3}", jurisdiction) is None
        or re.fullmatch(r"[0-9]{8}", freeze_date) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", state_fingerprint) is None
    ):
        raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID)
    name = f"asklegal-{environment}-{jurisdiction}-{freeze_date}-{state_fingerprint[7:19]}"
    if (
        len(name) > _INDEX_NAME_LIMIT
        or len(f"{name}-{project_id}") > _PROJECT_INDEX_NAME_LIMIT
        or re.fullmatch(r"[a-z0-9-]+", name) is None
    ):
        raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID)
    return name


def embedding_request(
    inputs: EmbeddingRequestInput,
    profile: EmbeddingProfile,
    token_counter: EmbeddingTokenCounter,
) -> EmbeddingRequest:
    """Bind only exact metadata.text, exact tokens, and the complete profile."""
    if not inputs.text:
        raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "empty text")
    text_bytes = inputs.text.encode()
    text_fingerprint = _fingerprint(text_bytes)
    try:
        tokenizer_id = token_counter.tokenizer_id
    except Exception as error:
        message = "tokenizer identity"
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message) from error
    if type(tokenizer_id) is not str or tokenizer_id != profile.tokenizer:
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "tokenizer identity")
    try:
        token_count = token_counter.count(inputs.text)
    except Exception as error:
        message = "token count"
        raise PromotionError(PromotionErrorCode.VECTOR_INVALID, message) from error
    if type(token_count) is not int or not 1 <= token_count <= profile.max_input_tokens:
        raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "oversized text")
    cache_key = _fingerprint((text_fingerprint + profile.profile_fingerprint).encode())
    request_id = _stable_id(
        "emr",
        inputs.record_id,
        inputs.serving_payload_fingerprint,
        cache_key,
        inputs.batch_id,
        str(inputs.position),
    )
    return EmbeddingRequest(
        request_id,
        inputs.record_id,
        inputs.serving_payload_fingerprint,
        inputs.text,
        text_fingerprint,
        token_count,
        profile.profile_id,
        inputs.batch_id,
        inputs.position,
        cache_key,
    )


def _object_reference_document(reference: ExactObjectReference) -> dict[str, object]:
    return {
        "byte_length": reference.byte_length,
        "fingerprint": reference.fingerprint,
        "logical_key": reference.logical_key,
        "vault": reference.vault.value,
        "version_id": reference.version_id,
    }


def proposal_receipt_document(receipt: StoredProposalPackage) -> dict[str, object]:
    """Render the closed Management Register value for one stored proposal."""
    return {
        "manifest_reference": _object_reference_document(receipt.manifest_reference),
        "members": [
            {
                "path": member.path,
                "reference": _object_reference_document(member.reference),
                "role": member.role,
            }
            for member in receipt.members
        ],
        "package_fingerprint": receipt.package_fingerprint,
        "package_id": receipt.package_id,
        "promotion_manifest_fingerprint": receipt.promotion_manifest_fingerprint,
        "promotion_manifest_id": receipt.promotion_manifest_id,
        "traceability_shards": [
            {
                "path": shard.path,
                "reference": _object_reference_document(shard.reference),
            }
            for shard in receipt.traceability_shards
        ],
    }


def proposal_receipt_fingerprint(receipt: StoredProposalPackage) -> str:
    """Fingerprint the complete portable receipt without its claimed fingerprint."""
    return _fingerprint(canonicalize(checked_json_value(proposal_receipt_document(receipt))))


def verify_stored_proposal_package(receipt: StoredProposalPackage) -> None:
    """Reject role, vault, or receipt-fingerprint drift before any package read."""
    if (
        tuple(member.role for member in receipt.members) != tuple(sorted(PROPOSAL_ROLE_PATHS))
        or any(
            PROPOSAL_ROLE_PATHS.get(member.role) != member.path
            or member.reference.vault is not VaultName.PRIMARY
            for member in receipt.members
        )
        or not receipt.traceability_shards
        or tuple(shard.path for shard in receipt.traceability_shards)
        != tuple(sorted({shard.path for shard in receipt.traceability_shards}))
        or any(
            not shard.path.startswith("entries/")
            or not shard.path.endswith(".ndjson")
            or shard.reference.vault is not VaultName.PRIMARY
            or shard.reference.logical_key
            != f"proposal-packages/{receipt.package_id}/traceability/{shard.path}"
            for shard in receipt.traceability_shards
        )
        or receipt.manifest_reference.vault is not VaultName.PRIMARY
        or proposal_receipt_fingerprint(receipt) != receipt.receipt_fingerprint
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal receipt")


def stored_proposal_package_from_bytes(content: bytes) -> StoredProposalPackage:
    """Parse one canonical registered receipt into exact vault references."""
    document = parse_json_bytes(content, max_bytes=1_000_000)
    expected = {
        "manifest_reference",
        "members",
        "package_fingerprint",
        "package_id",
        "promotion_manifest_fingerprint",
        "promotion_manifest_id",
        "traceability_shards",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal document")
    if canonicalize(document) != content:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal canonical bytes")
    raw_members = document.get("members")
    if not isinstance(raw_members, list):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal members")
    members = tuple(_proposal_member(value) for value in raw_members)
    raw_shards = document.get("traceability_shards")
    if not isinstance(raw_shards, list):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "traceability shards")
    shards = tuple(_traceability_shard(value) for value in raw_shards)
    provisional = StoredProposalPackage(
        _json_text(document, "package_id"),
        _json_text(document, "package_fingerprint"),
        _json_text(document, "promotion_manifest_id"),
        _json_text(document, "promotion_manifest_fingerprint"),
        members,
        shards,
        _object_reference(document.get("manifest_reference")),
        _fingerprint(content),
    )
    verify_stored_proposal_package(provisional)
    return provisional


def _proposal_member(value: JsonValue) -> ProposalMemberReceipt:
    if not isinstance(value, dict) or set(value) != {"path", "reference", "role"}:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal member")
    return ProposalMemberReceipt(
        _json_text(value, "role"),
        _json_text(value, "path"),
        _object_reference(value.get("reference")),
    )


def _traceability_shard(value: JsonValue) -> TraceabilityShardReceipt:
    if not isinstance(value, dict) or set(value) != {"path", "reference"}:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "traceability shard")
    return TraceabilityShardReceipt(
        _json_text(value, "path"),
        _object_reference(value.get("reference")),
    )


def _object_reference(value: JsonValue | None) -> ExactObjectReference:
    expected = {"byte_length", "fingerprint", "logical_key", "vault", "version_id"}
    if not isinstance(value, dict) or set(value) != expected:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal reference")
    try:
        return ExactObjectReference(
            VaultName(_json_text(value, "vault")),
            _json_text(value, "logical_key"),
            _json_text(value, "version_id"),
            _json_text(value, "fingerprint"),
            _json_integer(value, "byte_length"),
        )
    except (TypeError, ValueError) as error:
        raise PromotionError(
            PromotionErrorCode.MANIFEST_DRIFT,
            "stored proposal reference",
        ) from error


def _json_action_authorities(
    document: dict[str, JsonValue],
) -> tuple[PromotionActionAuthority, ...]:
    raw_actions = document.get("actions")
    if not isinstance(raw_actions, list):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "actions")
    actions: list[PromotionActionAuthority] = []
    expected = {
        "action_id",
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
        "sequence",
        "stable_idempotency_key",
        "stop_conditions",
        "success_postcondition_ref",
    }
    try:
        for value in raw_actions:
            if not isinstance(value, dict) or set(value) != expected:
                raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action fields")
            raw_inputs = value.get("input_refs")
            raw_stops = value.get("stop_conditions")
            if not isinstance(raw_inputs, list) or not isinstance(raw_stops, list):
                raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action lists")
            actions.append(
                PromotionActionAuthority(
                    _json_integer(value, "sequence"),
                    _json_text(value, "action_id"),
                    EffectType(_json_text(value, "effect_type")),
                    ApplicationCode(_json_text(value, "owning_application")),
                    _json_text(value, "permitted_checkpoint"),
                    tuple(_json_immutable_reference(item) for item in raw_inputs),
                    _json_text(value, "effect_command_fingerprint"),
                    EffectCapability(_json_text(value, "required_capability")),
                    _json_immutable_reference(value.get("capability_profile_ref")),
                    DestinationClass(_json_text(value, "destination_class")),
                    _json_text(value, "stable_idempotency_key"),
                    RetryClass(_json_text(value, "retry_class")),
                    _json_integer(value, "attempt_ceiling"),
                    _json_text(value, "deadline"),
                    tuple(
                        StopCondition(_json_string(item, "stop_conditions")) for item in raw_stops
                    ),
                    _json_contract_reference(value.get("expected_remote_precondition_ref")),
                    _json_contract_reference(value.get("success_postcondition_ref")),
                    _json_compensation(value.get("compensation")),
                )
            )
    except (DomainInvariantError, TypeError, ValueError) as error:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action values") from error
    return tuple(actions)


def _json_immutable_reference(value: JsonValue | None) -> ImmutableReference:
    if not isinstance(value, dict) or set(value) != {"fingerprint", "ref_id", "ref_type"}:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action reference")
    return ImmutableReference(
        ReferenceType(_json_text(value, "ref_type")),
        _json_text(value, "ref_id"),
        _json_text(value, "fingerprint"),
    )


def _json_contract_reference(value: JsonValue | None) -> ContractReference:
    if not isinstance(value, dict) or set(value) != {"contract_id", "fingerprint", "version"}:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action contract reference")
    return ContractReference(
        _json_text(value, "contract_id"),
        _json_text(value, "version"),
        _json_text(value, "fingerprint"),
    )


def _json_compensation(value: JsonValue | None) -> NoCompensation | DeclaredCompensation:
    if not isinstance(value, dict):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action compensation")
    mode = _json_text(value, "mode")
    if mode == "NO_COMPENSATION" and set(value) == {"mode"}:
        return NoCompensation()
    if mode == "DECLARED_COMPENSATION" and set(value) == {"contract_ref", "mode"}:
        return DeclaredCompensation(_json_contract_reference(value.get("contract_ref")))
    raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "action compensation")


def _json_string(value: JsonValue, field: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, field)
    return value


def _json_text(document: dict[str, JsonValue], field: str) -> str:
    value = document.get(field)
    if type(value) is not str or not value:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, field)
    return value


def _json_integer(document: dict[str, JsonValue], field: str) -> int:
    value = document.get(field)
    if type(value) is not int:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, field)
    return value


def _json_string_sequence(document: dict[str, JsonValue], field: str) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list) or any(type(item) is not str or not item for item in value):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, field)
    return tuple(item for item in value if type(item) is str)


def _json_predicates(document: dict[str, JsonValue]) -> tuple[tuple[str, str, str], ...]:
    value = document.get("validity_predicates")
    if not isinstance(value, list):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "validity_predicates")
    result: list[tuple[str, str, str]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != _PREDICATE_PARTS
            or any(type(part) is not str or not part for part in item)
        ):
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "validity_predicates")
        first, second, third = item
        if type(first) is str and type(second) is str and type(third) is str:
            result.append((first, second, third))
    return tuple(result)
