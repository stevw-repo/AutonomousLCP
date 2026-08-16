"""Synthetic fixtures shared by Durable Task proofs."""

import time
from collections.abc import Callable

from asklegal_durable_task import (
    DurableWorkflowActivities,
    ExecutionRecord,
    FakeManagementRegister,
    ReviewEventFact,
    WorkflowInput,
    review_gate_orchestrator,
)
from durabletask.client import OrchestrationState, OrchestrationStatus, TaskHubGrpcClient
from durabletask.worker import TaskHubGrpcWorker


def synthetic_fingerprint(character: str) -> str:
    """Return one valid deterministic synthetic fingerprint."""
    return f"sha256:{character * 64}"


def workflow_input(execution_id: str) -> WorkflowInput:
    """Return the exact synthetic workflow identity used by the proof."""
    return WorkflowInput(
        execution_id=execution_id,
        workflow_version="1.0.0",
        build_fingerprint=synthetic_fingerprint("1"),
        configuration_fingerprint=synthetic_fingerprint("2"),
        contract_fingerprint=synthetic_fingerprint("3"),
        input_fingerprint=synthetic_fingerprint("4"),
        effect_command_id="effect-command-1",
        effect_command_fingerprint=synthetic_fingerprint("5"),
    )


def seeded_register(request: WorkflowInput) -> FakeManagementRegister:
    """Admit one execution plus stale and current review-event facts."""
    register = FakeManagementRegister()
    register.admit_execution(ExecutionRecord(request))
    register.record_review_event(
        ReviewEventFact(
            request.execution_id,
            "stale-event-1",
            synthetic_fingerprint("6"),
            synthetic_fingerprint("0"),
        )
    )
    register.record_review_event(
        ReviewEventFact(
            request.execution_id,
            "valid-event-1",
            synthetic_fingerprint("7"),
            request.input_fingerprint,
        )
    )
    register.fail_next_effect_acknowledgement(request.effect_command_id)
    return register


def configure_worker(
    worker: TaskHubGrpcWorker,
    register: FakeManagementRegister,
) -> None:
    """Register the exact orchestration and its two effect activities."""
    activities = DurableWorkflowActivities(register)
    worker.add_orchestrator(review_gate_orchestrator)
    worker.add_activity(activities.resolve_review_event_activity)
    worker.add_activity(activities.apply_effect_activity)


def wait_until_waiting(
    client: TaskHubGrpcClient,
    execution_id: str,
    *,
    timeout_seconds: float = 5.0,
) -> OrchestrationState:
    """Wait until the orchestration has durably reached its human-event wait."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = client.get_orchestration_state(execution_id)
        if (
            state is not None
            and state.runtime_status is OrchestrationStatus.RUNNING
            and state.serialized_custom_status is not None
            and "WAITING_REVIEW" in state.serialized_custom_status
        ):
            return state
        time.sleep(0.01)
    raise TimeoutError("DURABLE_WAIT_NOT_REACHED")


type WorkerFactory = Callable[[FakeManagementRegister], TaskHubGrpcWorker]
