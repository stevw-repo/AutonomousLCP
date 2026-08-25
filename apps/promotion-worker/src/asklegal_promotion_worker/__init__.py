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
    PromotionDependencies,
    PromotionExecutionContext,
    PromotionService,
)

__all__ = [
    "APPLICATION_NAME",
    "CAPABILITY_PORTS",
    "CurrentCapabilityEvidence",
    "CurrentCapabilityEvidenceSource",
    "CurrentExecutionActionAuthority",
    "CurrentExecutionActionAuthoritySource",
    "PromotionDependencies",
    "PromotionExecutionContext",
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
    "create_runtime",
]
