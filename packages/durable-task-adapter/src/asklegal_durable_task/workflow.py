"""Deterministic orchestration and effect activities for the local spike."""

from collections.abc import Generator
from datetime import timedelta

from durabletask.task import (
    ActivityContext,
    OrchestrationContext,
    RetryPolicy,
    Task,
)

from asklegal_durable_task.fake_register import FakeManagementRegister
from asklegal_durable_task.models import (
    REVIEW_EVENT_NAME,
    EffectRequest,
    EffectResult,
    ReviewEventRef,
    ReviewEventRequest,
    ReviewResolution,
    ReviewResolutionCode,
    WorkflowInput,
    WorkflowOutput,
    WorkflowResultCode,
)

MAX_REVIEW_EVENT_ATTEMPTS = 16
_EFFECT_RESULT_TYPE_INVALID = "DURABLE_EFFECT_RESULT_TYPE_INVALID"
_EVENT_TYPE_INVALID = "DURABLE_EVENT_TYPE_INVALID"
_REGISTER_WRONG_EXECUTION = "REGISTER_WRONG_EXECUTION"
_RESOLUTION_TYPE_INVALID = "DURABLE_RESOLUTION_TYPE_INVALID"
_EFFECT_RETRY_POLICY = RetryPolicy(
    first_retry_interval=timedelta(milliseconds=10),
    max_number_of_attempts=2,
)

type WorkflowTask = Task[ReviewEventRef] | Task[ReviewResolution] | Task[EffectResult]
type WorkflowSend = ReviewEventRef | ReviewResolution | EffectResult


def review_gate_orchestrator(
    context: OrchestrationContext,
    workflow_input: WorkflowInput,
) -> Generator[WorkflowTask, WorkflowSend, WorkflowOutput]:
    """Wait for an authoritative event, then schedule one idempotent effect."""
    if context.version != workflow_input.workflow_version:
        return WorkflowOutput(WorkflowResultCode.VERSION_REJECTED, None, None)

    accepted_event_id: str | None = None
    for attempt in range(1, MAX_REVIEW_EVENT_ATTEMPTS + 1):
        context.set_custom_status({"attempt": attempt, "code": "WAITING_REVIEW"})
        event_value = yield context.wait_for_external_event(
            REVIEW_EVENT_NAME,
            data_type=ReviewEventRef,
        )
        if not isinstance(event_value, ReviewEventRef):
            raise TypeError(_EVENT_TYPE_INVALID)
        resolution_value = yield context.call_activity(
            "resolve_review_event_activity",
            input=ReviewEventRequest(
                workflow_input.execution_id,
                event_value.event_id,
                event_value.event_fingerprint,
            ),
            return_type=ReviewResolution,
        )
        if not isinstance(resolution_value, ReviewResolution):
            raise TypeError(_RESOLUTION_TYPE_INVALID)
        if resolution_value.code is ReviewResolutionCode.ACCEPTED:
            accepted_event_id = resolution_value.event_id
            break

    if accepted_event_id is None:
        return WorkflowOutput(WorkflowResultCode.EVENT_LIMIT_REACHED, None, None)

    context.set_custom_status({"code": "EFFECT_PENDING"})
    effect_value = yield context.call_activity(
        "apply_effect_activity",
        input=EffectRequest(
            execution_id=workflow_input.execution_id,
            workflow_version=workflow_input.workflow_version,
            build_fingerprint=workflow_input.build_fingerprint,
            configuration_fingerprint=workflow_input.configuration_fingerprint,
            contract_fingerprint=workflow_input.contract_fingerprint,
            input_fingerprint=workflow_input.input_fingerprint,
            approval_event_id=accepted_event_id,
            command_id=workflow_input.effect_command_id,
            command_fingerprint=workflow_input.effect_command_fingerprint,
        ),
        retry_policy=_EFFECT_RETRY_POLICY,
        return_type=EffectResult,
    )
    if not isinstance(effect_value, EffectResult):
        raise TypeError(_EFFECT_RESULT_TYPE_INVALID)
    return WorkflowOutput(
        WorkflowResultCode.EFFECT_RECORDED,
        accepted_event_id,
        effect_value.receipt_id,
    )


class DurableWorkflowActivities:
    """Activities bound to the current authoritative register adapter."""

    def __init__(self, register: FakeManagementRegister) -> None:
        """Bind activities to the current register adapter."""
        self._register = register

    def resolve_review_event_activity(
        self,
        context: ActivityContext,
        request: ReviewEventRequest,
    ) -> ReviewResolution:
        """Resolve one opaque event without trusting Scheduler delivery."""
        if context.orchestration_id != request.execution_id:
            return ReviewResolution(ReviewResolutionCode.WRONG_EXECUTION, request.event_id)
        return self._register.resolve_review_event(
            request.execution_id,
            ReviewEventRef(request.event_id, request.event_fingerprint),
        )

    def apply_effect_activity(
        self,
        context: ActivityContext,
        request: EffectRequest,
    ) -> EffectResult:
        """Apply one exact effect and resolve a synthetic lost acknowledgement."""
        if context.orchestration_id != request.execution_id:
            raise ValueError(_REGISTER_WRONG_EXECUTION)
        result = self._register.apply_effect(request)
        self._register.acknowledge_effect(request.command_id)
        return result
