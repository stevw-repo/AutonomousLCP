"""AskLegal Durable Task orchestration adapter."""

from asklegal_durable_task.fake_register import (
    ExecutionRecord,
    FakeManagementRegister,
    ReviewEventFact,
)
from asklegal_durable_task.models import (
    REVIEW_EVENT_NAME,
    EffectRequest,
    EffectResult,
    ReviewEventRef,
    ReviewResolution,
    ReviewResolutionCode,
    WorkflowInput,
    WorkflowOutput,
    WorkflowResultCode,
)
from asklegal_durable_task.v1 import (
    ActivityContext,
    ConcurrencyOptions,
    OrchestrationContext,
    Task,
    V1SchedulerError,
    V1SchedulerErrorCode,
    V1SchedulerSettings,
)
from asklegal_durable_task.workflow import (
    DurableWorkflowActivities,
    review_gate_orchestrator,
)

PACKAGE_ROLE: str = "durable-task-adapter"

__all__ = [
    "PACKAGE_ROLE",
    "REVIEW_EVENT_NAME",
    "ActivityContext",
    "ConcurrencyOptions",
    "DurableWorkflowActivities",
    "EffectRequest",
    "EffectResult",
    "ExecutionRecord",
    "FakeManagementRegister",
    "OrchestrationContext",
    "ReviewEventFact",
    "ReviewEventRef",
    "ReviewResolution",
    "ReviewResolutionCode",
    "Task",
    "V1SchedulerError",
    "V1SchedulerErrorCode",
    "V1SchedulerSettings",
    "WorkflowInput",
    "WorkflowOutput",
    "WorkflowResultCode",
    "review_gate_orchestrator",
]
