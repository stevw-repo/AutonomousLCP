"""Approval-bound serving promotion rules and local conformance adapters."""

from .builder import (
    embedding_request,
    freeze_embedding_profile,
    freeze_promotion_manifest,
    pinecone_index_name,
    verify_embedding_profile,
    verify_promotion_manifest,
)
from .local import (
    LocalBackupStore,
    LocalCoverageStore,
    LocalEmbeddingAdapter,
    LocalFailurePlan,
    LocalRoutingStore,
    LocalServingTargetStore,
    OutcomeUnknown,
)
from .model import (
    BackupVerification,
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingProfileInput,
    EmbeddingReceipt,
    EmbeddingRequest,
    EmbeddingRequestInput,
    PromotionError,
    PromotionErrorCode,
    PromotionExecutionResult,
    PromotionManifest,
    PromotionPlan,
    TargetDefinition,
    TargetRecord,
)
from .ports import BackupPort, CoveragePort, EmbeddingPort, RoutingPort, ServingTargetPort

PACKAGE_ROLE: str = "promotion"

__all__ = [
    "PACKAGE_ROLE",
    "BackupPort",
    "BackupVerification",
    "CoveragePort",
    "EmbeddedVector",
    "EmbeddingPort",
    "EmbeddingProfile",
    "EmbeddingProfileInput",
    "EmbeddingReceipt",
    "EmbeddingRequest",
    "EmbeddingRequestInput",
    "LocalBackupStore",
    "LocalCoverageStore",
    "LocalEmbeddingAdapter",
    "LocalFailurePlan",
    "LocalRoutingStore",
    "LocalServingTargetStore",
    "OutcomeUnknown",
    "PromotionError",
    "PromotionErrorCode",
    "PromotionExecutionResult",
    "PromotionManifest",
    "PromotionPlan",
    "RoutingPort",
    "ServingTargetPort",
    "TargetDefinition",
    "TargetRecord",
    "embedding_request",
    "freeze_embedding_profile",
    "freeze_promotion_manifest",
    "pinecone_index_name",
    "verify_embedding_profile",
    "verify_promotion_manifest",
]
