"""No-ingress promotion-worker process boundary."""

APPLICATION_NAME: str = "promotion-worker"
CAPABILITY_PORTS: tuple[str, ...] = (
    "approved_manifest_read",
    "asklegal_routing",
    "backup_mutation",
    "durable_promotion_work",
    "embedding_provider",
    "pinecone_mutation",
    "recovery_copy",
    "serving_state_write",
)

from asklegal_promotion_worker.local_approval import LocalRetainedPromotionApprovalStore
from asklegal_promotion_worker.local_intents import (
    LocalRetainedEffectIntentSource,
    local_effect_intent_ledger_bytes,
)
from asklegal_promotion_worker.proposal_evidence import (
    PromotionProposalEvidenceError,
    issue_embedding_provider_disabled_evidence,
)
from asklegal_promotion_worker.registered_effect_handler import (
    CurrentExecutionActionAuthority,
    CurrentExecutionActionAuthoritySource,
    RegisteredEffectHandler,
    RegisteredEffectHandlerContext,
    RegisteredEffectHandlerDependencies,
    RegisteredEffectHandlerError,
    RegisteredEffectHandlerErrorCode,
    RegisteredEffectHandlingResult,
    RegisteredEffectHandoff,
    RegisteredEffectOutcome,
    RegisteredEffectPort,
)
from asklegal_promotion_worker.registered_execution_begin import (
    CurrentCapabilityEvidence,
    CurrentCapabilityEvidenceSource,
    RegisteredExecutionBeginContext,
    RegisteredExecutionBeginError,
    RegisteredExecutionBeginErrorCode,
    RegisteredExecutionBeginService,
    RegisteredExecutionBeginWriter,
)
from asklegal_promotion_worker.runtime import create_runtime
from asklegal_promotion_worker.service import (
    HKV1LocalApprovalStore,
    PromotionDependencies,
    PromotionExecutionContext,
    PromotionService,
    compose_hk_v1_local_promotion_service,
)

__all__ = [
    "APPLICATION_NAME",
    "CAPABILITY_PORTS",
    "CurrentCapabilityEvidence",
    "CurrentCapabilityEvidenceSource",
    "CurrentExecutionActionAuthority",
    "CurrentExecutionActionAuthoritySource",
    "HKV1LocalApprovalStore",
    "LocalRetainedEffectIntentSource",
    "LocalRetainedPromotionApprovalStore",
    "PromotionDependencies",
    "PromotionExecutionContext",
    "PromotionProposalEvidenceError",
    "PromotionService",
    "RegisteredEffectHandler",
    "RegisteredEffectHandlerContext",
    "RegisteredEffectHandlerDependencies",
    "RegisteredEffectHandlerError",
    "RegisteredEffectHandlerErrorCode",
    "RegisteredEffectHandlingResult",
    "RegisteredEffectHandoff",
    "RegisteredEffectOutcome",
    "RegisteredEffectPort",
    "RegisteredExecutionBeginContext",
    "RegisteredExecutionBeginError",
    "RegisteredExecutionBeginErrorCode",
    "RegisteredExecutionBeginService",
    "RegisteredExecutionBeginWriter",
    "compose_hk_v1_local_promotion_service",
    "create_runtime",
    "issue_embedding_provider_disabled_evidence",
    "local_effect_intent_ledger_bytes",
]
