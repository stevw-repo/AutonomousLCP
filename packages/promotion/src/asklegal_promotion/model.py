"""Immutable M6 promotion, embedding, target, and routing values."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


def _required_text(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if type(item) is not str or not item or item.strip() != item:
        raise ValueError(field)
    return item


def _required_list_text(value: Sequence[object]) -> tuple[str, ...]:
    if any(type(item) is not str or not item or item.strip() != item for item in value):
        message = "list text"
        raise ValueError(message)
    return tuple(item for item in value if type(item) is str)


if TYPE_CHECKING:
    from asklegal_corpus import CoverageStatusManifest, DesiredStateInventory
    from asklegal_domain import (
        ApplicationCode,
        ContractReference,
        DeclaredCompensation,
        DestinationClass,
        EffectCapability,
        EffectType,
        ImmutableReference,
        NoCompensation,
        RetryClass,
        StopCondition,
    )
    from asklegal_evidence_vault import ExactObjectReference


class PromotionErrorCode(StrEnum):
    """Closed fail-visible M6 promotion failures."""

    BACKUP_FAILED = "BACKUP_FAILED"
    BASE_STATE_DRIFT = "BASE_STATE_DRIFT"
    BROAD_RETIREMENT_FORBIDDEN = "BROAD_RETIREMENT_FORBIDDEN"
    COST_LIMIT_EXCEEDED = "COST_LIMIT_EXCEEDED"
    COVERAGE_FINGERPRINT_MISMATCH = "COVERAGE_FINGERPRINT_MISMATCH"
    COVERAGE_UNAVAILABLE = "COVERAGE_UNAVAILABLE"
    INDEX_NAME_INVALID = "INDEX_NAME_INVALID"
    INVENTORY_MISMATCH = "INVENTORY_MISMATCH"
    LOST_ACK_UNRECONCILED = "LOST_ACK_UNRECONCILED"
    MANIFEST_DRIFT = "MANIFEST_DRIFT"
    OVERLAPPING_EXECUTION = "OVERLAPPING_EXECUTION"
    POST_CUTOVER_FAILED = "POST_CUTOVER_FAILED"
    PROFILE_INVALID = "PROFILE_INVALID"
    RETRIEVAL_GATE_FAILED = "RETRIEVAL_GATE_FAILED"
    ROUTING_COMPARE_AND_SET_LOST = "ROUTING_COMPARE_AND_SET_LOST"
    SERVING_STATE_COMPARE_AND_SET_LOST = "SERVING_STATE_COMPARE_AND_SET_LOST"
    SERVING_PAYLOAD_INVALID = "SERVING_PAYLOAD_INVALID"
    SWAP_PREFLIGHT_FAILED = "SWAP_PREFLIGHT_FAILED"
    TARGET_COLLISION = "TARGET_COLLISION"
    UNKNOWN_REMOTE_RECORD = "UNKNOWN_REMOTE_RECORD"
    VECTOR_INVALID = "VECTOR_INVALID"
    WARMUP_FAILED = "WARMUP_FAILED"


class PromotionError(RuntimeError):
    """One exact M6 execution failure."""

    def __init__(self, code: PromotionErrorCode, detail: str = "") -> None:
        """Create one closed promotion failure."""
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail


class OutcomeUnknown(RuntimeError):
    """A remote mutation may have committed but no exact acknowledgement arrived."""


@dataclass(frozen=True, slots=True)
class EmbeddingProfile:
    """Exact stateless admitted embedding profile."""

    profile_id: str
    profile_fingerprint: str
    provider: str
    resource_class: str
    geography_class: str
    deployment_name: str
    model_id: str
    model_version: str
    api_contract: str
    tokenizer: str
    dimensions: int
    encoding: str
    normalization: str
    metric: str
    max_input_tokens: int
    cost_limit_microunits: int
    expires_at: str
    allowed_environments: tuple[str, ...]
    stateful_features: bool = False


@dataclass(frozen=True, slots=True)
class EmbeddingProfileInput:
    """Admitted fields used to issue an immutable embedding profile."""

    provider: str
    resource_class: str
    geography_class: str
    deployment_name: str
    model_id: str
    model_version: str
    api_contract: str
    tokenizer: str
    dimensions: int
    encoding: str
    normalization: str
    metric: str
    max_input_tokens: int
    cost_limit_microunits: int
    expires_at: str
    allowed_environments: tuple[str, ...]
    stateful_features: bool = False


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    """Exact metadata.text-only idempotent request."""

    request_id: str
    record_id: str
    serving_payload_fingerprint: str
    text: str
    text_fingerprint: str
    token_count: int
    profile_id: str
    batch_id: str
    batch_position: int
    cache_key: str


@dataclass(frozen=True, slots=True)
class EmbeddingReceipt:
    """Provider accounting without raw vectors in register state."""

    receipt_id: str
    request_id: str
    provider_request_id: str
    dimensions: int
    vector_fingerprint: str
    input_tokens: int
    latency_milliseconds: int
    result: str


@dataclass(frozen=True, slots=True)
class EmbeddedVector:
    """Adapter-private vector returned alongside its safe receipt."""

    values: tuple[float, ...]
    receipt: EmbeddingReceipt


@dataclass(frozen=True, slots=True)
class PromotionActionAuthority:
    """Immutable manifest authority for one future Effect Intent.

    Dynamic execution identities and timestamps are deliberately absent. Every
    value the durable BEGIN transition must not choose for itself is present.
    """

    sequence: int
    action_id: str
    effect_type: EffectType
    owning_application: ApplicationCode
    permitted_checkpoint: str
    input_refs: tuple[ImmutableReference, ...]
    effect_command_fingerprint: str
    required_capability: EffectCapability
    capability_profile_ref: ImmutableReference
    destination_class: DestinationClass
    stable_idempotency_key: str
    retry_class: RetryClass
    attempt_ceiling: int
    deadline: str
    stop_conditions: tuple[StopCondition, ...]
    expected_remote_precondition_ref: ContractReference
    success_postcondition_ref: ContractReference
    compensation: NoCompensation | DeclaredCompensation


@dataclass(frozen=True, slots=True)
class PromotionManifest:
    """Sole immutable local approval and execution envelope."""

    manifest_id: str
    fingerprint: str
    environment: str
    jurisdiction: str
    freeze_date: str
    valid_from: str
    valid_until: str
    base_serving_state_id: str
    candidate_serving_state_id: str
    candidate_serving_state_fingerprint: str
    rollback_serving_state_id: str
    desired_state: DesiredStateInventory
    coverage_status: CoverageStatusManifest
    embedding_profile: EmbeddingProfile
    validity_predicates: tuple[tuple[str, str, str], ...]
    batch_size: int
    project_id: str
    action_contract_version: str
    actions: tuple[PromotionActionAuthority, ...]
    exact_retirement_target_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PromotionApprovalSnapshot:
    """Exact manifest facts Review, Approval, and execution must recover."""

    manifest_id: str
    fingerprint: str
    expected_base_serving_state_id: str
    candidate_serving_state_id: str
    valid_from: str
    valid_until: str
    validity_predicates: tuple[tuple[str, str, str], ...]
    action_contract_version: str
    actions: tuple[PromotionActionAuthority, ...]


@dataclass(frozen=True, slots=True)
class TargetRecord:
    """One record stored in a replacement serving target.

    `metadata_text` and the five fields after it are the closed six-property
    serving payload ADR 0078 defines, and they travel to the target together. A
    record that reaches the index carrying only its text is one whose authority
    note was silently dropped, so a reconstructed provision comes back looking
    like the publisher's own version.
    """

    record_id: str
    content_fingerprint: str
    vector: tuple[float, ...]
    metadata_text: str
    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str


@dataclass(frozen=True, slots=True)
class TargetDefinition:
    """Exact immutable replacement-target configuration."""

    name: str
    state_fingerprint: str
    dimensions: int
    metric: str
    namespace: str


@dataclass(frozen=True, slots=True)
class BackupVerification:
    """Independent exact native-backup and recovery-copy verification refs."""

    native_backup_receipt_ref: str
    recovery_receipt_ref: str
    native_verified: bool
    recovery_verified: bool


@dataclass(frozen=True, slots=True)
class ServingStateCandidate:
    """One exact V1 state activation candidate, bound before the CAS."""

    state_id: str
    state_fingerprint: str
    predecessor_state_id: str
    target_name: str
    desired_inventory_fingerprint: str
    coverage_fingerprint: str
    embedding_profile_id: str
    embedding_profile_fingerprint: str
    approval_id: str
    execution_lineage_id: str


@dataclass(frozen=True, slots=True)
class ServingStateReceipt:
    """Immutable local receipt for one activation or exact reversal."""

    receipt_id: str
    operation: str
    predecessor_state_id: str
    state_id: str
    candidate_fingerprint: str
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class PromotionExecutionResult:
    """Terminal local execution result and exact receipts."""

    execution_lineage_id: str
    manifest_id: str
    target_name: str
    state: str
    embedding_receipt_ids: tuple[str, ...]
    native_backup_receipt_ref: str
    recovery_receipt_ref: str
    routing_receipt_ref: str
    rollback_receipt_ref: str
    total_cost_microunits: int


@dataclass(frozen=True, slots=True)
class HKV1TargetMember:
    """One approved Search Record assigned to one exact V1 scope."""

    record_id: str
    scope_id: str
    material_family: str


@dataclass(frozen=True, slots=True)
class HKV1TargetComposition:
    """Verified four-scope membership bound to one frozen Task 7 proposal."""

    proposal_fingerprint: str
    scope_ids: tuple[str, ...]
    material_families: tuple[str, ...]
    explicit_exclusions: tuple[str, ...]
    model_profile_fingerprint: str
    embedding_profile_fingerprint: str
    members: tuple[HKV1TargetMember, ...]
    zero_record_scope_ids: tuple[str, ...]
    review_readiness_fingerprint: str = ""
    serving_profile_fingerprint: str = ""
    target_namespace: str = ""
    backup_profile_fingerprint: str = ""
    target_name: str = ""


_HK_V1_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_HK_V1_FAMILIES = ("CASES", "LEGISLATION")


def verify_hk_v1_target_membership(
    proposal_content: bytes,
    members: tuple[HKV1TargetMember, ...],
    expected_record_ids: tuple[str, ...],
    *,
    zero_record_scope_ids: tuple[str, ...] = (),
) -> HKV1TargetComposition:
    """Fail before effects unless the target is the exact approved two-family set."""
    try:
        parsed = parse_json_bytes(proposal_content, max_bytes=2_000_000)
    except ContractViolation as error:
        raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "proposal bytes") from error
    if not isinstance(parsed, dict) or canonicalize(parsed) != proposal_content:
        raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "proposal canonical bytes")
    supplied = parsed.get("fingerprint")
    body = dict(parsed)
    body.pop("fingerprint", None)
    actual = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
    scopes = parsed.get("scope_ids")
    families = parsed.get("included_material_families")
    exclusions = parsed.get("explicit_exclusions")
    model_profile = parsed.get("model_profile_fingerprint")
    embedding_profile = parsed.get("embedding_profile_fingerprint")
    if (
        parsed.get("schema_id") != "asklegal.hk-v1-two-family-proposal-manifest/v1"
        or parsed.get("status") != "FROZEN_PROPOSAL_READY_FOR_REVIEW"
        or parsed.get("release_state") != "WITHHELD_PENDING_NAMED_HUMAN_REVIEW"
        or supplied != actual
        or scopes != list(_HK_V1_SCOPES)
        or families != list(_HK_V1_FAMILIES)
        or not isinstance(exclusions, list)
        or "HKEX_REGULATORY_POST_V1" not in exclusions
        or type(model_profile) is not str
        or type(embedding_profile) is not str
    ):
        raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "two-family proposal")
    if (
        type(members) is not tuple
        or type(expected_record_ids) is not tuple
        or type(zero_record_scope_ids) is not tuple
        or not expected_record_ids
        or len(set(expected_record_ids)) != len(expected_record_ids)
        or any(type(item) is not HKV1TargetMember for item in members)
        or tuple(item.record_id for item in members) != expected_record_ids
        or len({item.record_id for item in members}) != len(members)
        or not {item.scope_id for item in members}.issubset(set(_HK_V1_SCOPES))
        or any(type(scope_id) is not str for scope_id in zero_record_scope_ids)
        or len(set(zero_record_scope_ids)) != len(zero_record_scope_ids)
        or tuple(sorted(zero_record_scope_ids)) != zero_record_scope_ids
        or set(zero_record_scope_ids) & {item.scope_id for item in members}
        or {item.scope_id for item in members} | set(zero_record_scope_ids) != set(_HK_V1_SCOPES)
        or {item.material_family for item in members} != set(_HK_V1_FAMILIES)
        or any(
            item.material_family
            != ("CASES" if item.scope_id == _HK_V1_SCOPES[0] else "LEGISLATION")
            for item in members
        )
    ):
        raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "target membership")
    return HKV1TargetComposition(
        actual,
        _HK_V1_SCOPES,
        _HK_V1_FAMILIES,
        tuple(item for item in exclusions if type(item) is str),
        model_profile,
        embedding_profile,
        members,
        zero_record_scope_ids,
    )


def verify_hk_v1_approved_package(
    proposal_content: bytes,
    readiness_content: bytes,
    expected_record_ids: tuple[str, ...],
) -> HKV1TargetComposition:
    """Recover target membership only from the exact approved readiness artifact."""
    try:
        value = parse_json_bytes(readiness_content, max_bytes=2_000_000)
    except ContractViolation as error:
        raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "readiness bytes") from error
    expected = {
        "backup_profile_fingerprint",
        "embedding_profile_fingerprint",
        "fingerprint",
        "limitations",
        "model_evaluation_ref",
        "model_profile_fingerprint",
        "native_backup_ref",
        "proposal_fingerprint",
        "recovery_backup_ref",
        "retrieval_evaluation_ref",
        "retryable_count",
        "rollback_state_id",
        "schema_id",
        "scope_dispositions",
        "serving_profile_fingerprint",
        "target_members",
        "target_name",
        "target_namespace",
        "zero_record_scope_ids",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or canonicalize(value) != readiness_content
    ):
        raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "readiness contract")
    unsigned = dict(value)
    observed = unsigned.pop("fingerprint", None)
    unsigned.pop("schema_id", None)
    computed = f"sha256:{sha256(canonicalize(checked_json_value(unsigned))).hexdigest()}"
    raw_members = value.get("target_members")
    raw_zero = value.get("zero_record_scope_ids")
    raw_scopes = value.get("scope_dispositions")
    if (
        value.get("schema_id") != "asklegal.hk-v1-review-readiness/v1"
        or observed != computed
        or not isinstance(raw_members, list)
        or not isinstance(raw_zero, list)
        or not isinstance(raw_scopes, list)
        or value.get("retryable_count") != 0
    ):
        raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "readiness identity")
    try:
        members = tuple(
            HKV1TargetMember(
                _required_text(item, "record_id"),
                _required_text(item, "scope_id"),
                _required_text(item, "material_family"),
            )
            for item in raw_members
            if isinstance(item, dict) and set(item) == {"material_family", "record_id", "scope_id"}
        )
        zero_scopes = tuple(_required_list_text(raw_zero))
        scope_results = tuple(
            (
                _required_text(item, "scope_id"),
                _required_text(item, "result"),
                item.get("retryable_count"),
            )
            for item in raw_scopes
            if isinstance(item, dict) and set(item) == {"result", "retryable_count", "scope_id"}
        )
        composition = verify_hk_v1_target_membership(
            proposal_content,
            members,
            expected_record_ids,
            zero_record_scope_ids=zero_scopes,
        )
        profile = _required_text(value, "serving_profile_fingerprint")
        namespace = _required_text(value, "target_namespace")
        backup = _required_text(value, "backup_profile_fingerprint")
        target_name = _required_text(value, "target_name")
    except (TypeError, ValueError) as error:
        raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "readiness values") from error
    if (
        len(members) != len(raw_members)
        or len(scope_results) != len(raw_scopes)
        or tuple(item[0] for item in scope_results) != _HK_V1_SCOPES
        or any(
            result != ("NO_CHANGE" if scope_id in zero_scopes else "COMPLETE")
            or type(retryable) is not int
            or retryable != 0
            for scope_id, result, retryable in scope_results
        )
        or value.get("proposal_fingerprint") != composition.proposal_fingerprint
        or value.get("model_profile_fingerprint") != composition.model_profile_fingerprint
        or value.get("embedding_profile_fingerprint") != composition.embedding_profile_fingerprint
        or any(_FINGERPRINT.fullmatch(item) is None for item in (profile, backup))
    ):
        raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "approved package drift")
    return replace(
        composition,
        review_readiness_fingerprint=computed,
        serving_profile_fingerprint=profile,
        target_namespace=namespace,
        backup_profile_fingerprint=backup,
        target_name=target_name,
    )


@dataclass(frozen=True, slots=True)
class PromotionPlan:
    """Complete immutable inputs used to freeze one Promotion Manifest."""

    environment: str
    jurisdiction: str
    freeze_date: str
    valid_from: str
    valid_until: str
    base_serving_state_id: str
    candidate_serving_state_id: str
    candidate_serving_state_fingerprint: str
    rollback_serving_state_id: str
    desired_state: DesiredStateInventory
    coverage_status: CoverageStatusManifest
    embedding_profile: EmbeddingProfile
    validity_predicates: tuple[tuple[str, str, str], ...]
    batch_size: int
    project_id: str
    action_contract_version: str
    actions: tuple[PromotionActionAuthority, ...]
    exact_retirement_target_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EmbeddingRequestInput:
    """Record and batch bindings used to create one Embedding Request."""

    record_id: str
    serving_payload_fingerprint: str
    text: str
    batch_id: str
    position: int


@dataclass(frozen=True, slots=True)
class ProposalMemberReceipt:
    """One proposal role bound to an exact Primary Vault object version."""

    role: str
    path: str
    reference: ExactObjectReference


@dataclass(frozen=True, slots=True)
class TraceabilityShardReceipt:
    """One declared ADR 0078 shard bound to an exact Primary Vault version."""

    path: str
    reference: ExactObjectReference


@dataclass(frozen=True, slots=True)
class StoredProposalPackage:
    """Portable exact-version receipt for one manifest-last proposal package."""

    package_id: str
    package_fingerprint: str
    promotion_manifest_id: str
    promotion_manifest_fingerprint: str
    members: tuple[ProposalMemberReceipt, ...]
    traceability_shards: tuple[TraceabilityShardReceipt, ...]
    manifest_reference: ExactObjectReference
    receipt_fingerprint: str
