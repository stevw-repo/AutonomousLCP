"""One stable approval-triggered V1 promotion scheduler boundary."""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from asklegal_promotion import (
    EmbeddingTokenCounter,
    LocalCoverageStore,
    LocalRoutingStore,
)

from asklegal_promotion_worker.local_backup import (
    FileNativeBackupWriter,
    FileRecoveryBackupWriter,
)
from asklegal_promotion_worker.promotion_evidence import (
    retain_promotion_failure_stop,
    retain_promotion_readback,
)
from asklegal_promotion_worker.real_effects import approved_v1_backup_request
from asklegal_promotion_worker.service import (
    PromotionDependencies,
    PromotionExecutionContext,
    PromotionService,
    compose_hk_v1_local_promotion_service,
)
from asklegal_promotion_worker.v1_infrastructure import (
    V1PromotionInfrastructure,
    V1PromotionPreflight,
    compose_approved_provider_effects,
    compose_independent_backup_adapter,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue
    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task
    from asklegal_promotion.remote import ProviderCall


@dataclass(frozen=True, slots=True)
class ApprovedPromotionActivity:
    """Exact service plus its immutable retained trigger facts."""

    service: PromotionService
    preflight: V1PromotionPreflight
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC), repr=False)

    def promote_approved_hk_v1(
        self,
        _context: ActivityContext,
        payload: object,
    ) -> dict[str, JsonValue]:
        """Execute only when scheduler payload repeats the retained trigger exactly."""
        expected = {
            "approval_id": self.preflight.approval_id,
            "execution_lineage_id": self.preflight.execution_lineage_id,
        }
        if payload != expected:
            message = "PROMOTION_TRIGGER_DRIFT"
            raise RuntimeError(message)
        observed_now = self.now()
        if (
            type(observed_now) is not datetime
            or observed_now.tzinfo is None
            or observed_now.utcoffset() is None
        ):
            message = "PROMOTION_EXECUTION_TIME_INVALID"
            raise RuntimeError(message)
        current = observed_now.astimezone(UTC)
        current_text = current.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        try:
            deadlines = tuple(
                datetime.fromisoformat(item.deadline.removesuffix("Z") + "+00:00").astimezone(UTC)
                for item in self.preflight.intents.effect_intents(
                    self.preflight.execution_lineage_id
                )
            )
            valid_from = datetime.fromisoformat(
                self.preflight.manifest.valid_from.removesuffix("Z") + "+00:00"
            ).astimezone(UTC)
            valid_until = datetime.fromisoformat(
                self.preflight.manifest.valid_until.removesuffix("Z") + "+00:00"
            ).astimezone(UTC)
        except (TypeError, ValueError) as error:
            message = "PROMOTION_EXECUTION_TIME_INVALID"
            raise RuntimeError(message) from error
        if (
            not deadlines
            or not valid_from <= current <= valid_until
            or any(current >= deadline for deadline in deadlines)
        ):
            message = "PROMOTION_EXECUTION_WINDOW_CLOSED"
            raise RuntimeError(message)
        before_state = self.preflight.serving_states.canonical_bytes()
        try:
            composition, result = self.service.execute_hk_v1(
                self.preflight.manifest,
                self.preflight.approval_id,
                self.preflight.execution_lineage_id,
                PromotionExecutionContext(
                    self.preflight.manifest.base_serving_state_id,
                    self.preflight.manifest.validity_predicates,
                    current_text,
                ),
            )
        except Exception as error:
            code_value = getattr(error, "code", None)
            code = getattr(code_value, "value", "PROMOTION_EXECUTION_FAILED")
            retain_promotion_failure_stop(
                self.preflight,
                before_state=before_state,
                failure_code=code if type(code) is str else "PROMOTION_EXECUTION_FAILED",
            )
            raise
        retain_promotion_readback(self.preflight, result)
        return {
            "approval_id": self.preflight.approval_id,
            "execution_lineage_id": result.execution_lineage_id,
            "manifest_id": result.manifest_id,
            "proposal_fingerprint": composition.proposal_fingerprint,
            "serving_state": result.state,
            "target_name": result.target_name,
        }


@dataclass(frozen=True, slots=True)
class RetainedPromotionActivity:
    """Resolve every activity call from its exact retained trigger at execution time."""

    resolve: Callable[[object], ApprovedPromotionActivity]

    def promote_approved_hk_v1(
        self,
        context: ActivityContext,
        payload: object,
    ) -> dict[str, JsonValue]:
        """Reread authority and package state before any promotion effect."""
        return self.resolve(payload).promote_approved_hk_v1(context, payload)


def compose_approved_promotion_activity(  # noqa: PLR0913 - exact injected boundaries.
    preflight: V1PromotionPreflight,
    infrastructure: V1PromotionInfrastructure,
    token_counter: EmbeddingTokenCounter,
    embedding_transport: ProviderCall,
    target_transport: ProviderCall,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ApprovedPromotionActivity:
    """Compose exact gated effects without invoking any provider or backup operation."""
    effects = compose_approved_provider_effects(
        infrastructure,
        preflight.serving_profile,
        preflight.manifest,
        token_counter,
        preflight.approvals,
        preflight.intents,
        embedding_transport,
        target_transport,
        approval_id=preflight.approval_id,
        execution_lineage_id=preflight.execution_lineage_id,
        backup_profile_ref=preflight.serving_profile.backup_profile_ref,
        now=now,
    )
    request = approved_v1_backup_request(preflight.serving_profile, preflight.manifest)
    backup = compose_independent_backup_adapter(
        preflight.serving_profile,
        request,
        FileNativeBackupWriter(preflight.native_backup_root, "native-local-v1"),
        FileRecoveryBackupWriter(preflight.recovery_backup_root, "recovery-local-v1"),
        activation=effects.activation,
    )
    service = compose_hk_v1_local_promotion_service(
        PromotionDependencies(
            preflight.approvals,
            effects.embeddings,
            token_counter,
            effects.targets,
            backup,
            LocalRoutingStore(preflight.current_serving_state_id),
            LocalCoverageStore(preflight.manifest.coverage_status),
            preflight.serving_states,
            preflight.serving_profile,
            preflight.serving_profile.backup_profile_ref,
            effects.activation,
        ),
        preflight.approvals,
    )
    return ApprovedPromotionActivity(service, preflight, now)


def promote_approved_hk_v1(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Checkpoint the sole named Approval-triggered promotion activity."""
    result = yield context.call_activity("promote_approved_hk_v1", input=payload)
    return result


class PromotionWorker(Protocol):
    """Minimal scheduler registration surface."""

    def add_activity(self, fn: Callable[..., object]) -> str:
        """Register one activity."""
        ...

    def add_orchestrator(self, fn: Callable[..., object]) -> str:
        """Register one orchestrator."""
        ...


def register_approved_promotion_handlers(
    worker: PromotionWorker,
    activity: ApprovedPromotionActivity | RetainedPromotionActivity,
) -> None:
    """Register exactly one stable activity and orchestrator name."""
    worker.add_activity(activity.promote_approved_hk_v1)
    worker.add_orchestrator(promote_approved_hk_v1)
