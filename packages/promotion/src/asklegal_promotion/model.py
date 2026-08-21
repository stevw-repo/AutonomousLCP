"""Immutable M6 promotion, embedding, target, and routing values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asklegal_corpus import CoverageStatusManifest, DesiredStateInventory


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
    validity_predicates: tuple[tuple[str, str], ...]
    batch_size: int
    project_id: str
    action_ids: tuple[str, ...]
    exact_retirement_target_ids: tuple[str, ...]
    capability_enabled: bool


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
    validity_predicates: tuple[tuple[str, str], ...]
    batch_size: int
    project_id: str
    action_ids: tuple[str, ...]
    exact_retirement_target_ids: tuple[str, ...] = ()
    capability_enabled: bool = False


@dataclass(frozen=True, slots=True)
class EmbeddingRequestInput:
    """Record and batch bindings used to create one Embedding Request."""

    record_id: str
    serving_payload_fingerprint: str
    text: str
    batch_id: str
    position: int
