"""Always-on SDK proof using Microsoft's in-process test backend."""

import socket

from asklegal_durable_task import (
    REVIEW_EVENT_NAME,
    FakeManagementRegister,
    ReviewEventRef,
    ReviewResolutionCode,
    WorkflowOutput,
    WorkflowResultCode,
    review_gate_orchestrator,
)
from durable_test_support import (
    configure_worker,
    seeded_register,
    synthetic_fingerprint,
    wait_until_waiting,
    workflow_input,
)
from durabletask.client import OrchestrationStatus, TaskHubGrpcClient
from durabletask.testing import InMemoryOrchestrationBackend
from durabletask.worker import TaskHubGrpcWorker


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as listener:
        listener.bind(("::1", 0))
        return listener.getsockname()[1]


def _worker(address: str, register: FakeManagementRegister) -> TaskHubGrpcWorker:
    worker = TaskHubGrpcWorker(host_address=address, secure_channel=False)
    configure_worker(worker, register)
    return worker


def test_worker_restart_duplicate_events_and_lost_ack_recover_deterministically() -> None:
    """Resume exact history in a fresh worker and produce one effect receipt."""
    backend = InMemoryOrchestrationBackend(port=_free_local_port())
    address = backend.start()
    request = workflow_input("in-memory-restart-execution")
    register = seeded_register(request)
    first_worker = _worker(address, register)
    client = TaskHubGrpcClient(host_address=address, secure_channel=False)
    second_worker: TaskHubGrpcWorker | None = None
    try:
        first_worker.start()
        instance_id = client.schedule_new_orchestration(
            review_gate_orchestrator,
            input=request,
            instance_id=request.execution_id,
            version=request.workflow_version,
        )
        assert instance_id == request.execution_id
        wait_until_waiting(client, instance_id)

        first_worker.stop()
        recovered = FakeManagementRegister.recover(register.snapshot())
        stale = ReviewEventRef("stale-event-1", synthetic_fingerprint("6"))
        valid = ReviewEventRef("valid-event-1", synthetic_fingerprint("7"))
        client.raise_orchestration_event(instance_id, REVIEW_EVENT_NAME, data=stale)
        client.raise_orchestration_event(instance_id, REVIEW_EVENT_NAME, data=stale)
        client.raise_orchestration_event(instance_id, REVIEW_EVENT_NAME, data=valid)

        second_worker = _worker(address, recovered)
        second_worker.start()
        state = client.wait_for_orchestration_completion(instance_id, timeout=10)

        assert state is not None
        assert state.runtime_status is OrchestrationStatus.COMPLETED
        output = state.get_output(WorkflowOutput)
        assert output == WorkflowOutput(
            WorkflowResultCode.EFFECT_RECORDED,
            "valid-event-1",
            "receipt:effect-command-1",
        )
        assert [fact.code for fact in recovered.event_audit()] == [
            ReviewResolutionCode.STALE_FINGERPRINT,
            ReviewResolutionCode.DUPLICATE_EVENT,
            ReviewResolutionCode.ACCEPTED,
        ]
        assert recovered.effect_count(request.effect_command_id) == 1
        assert recovered.effect_attempt_count(request.effect_command_id) == 2
        assert len(client.get_orchestration_history(instance_id)) > 0
    finally:
        first_worker.stop()
        if second_worker is not None:
            second_worker.stop()
        client.close()
        backend.stop()


def test_explicit_workflow_version_mismatch_fails_closed() -> None:
    """Complete without an activity when Scheduler and register versions differ."""
    backend = InMemoryOrchestrationBackend(port=_free_local_port())
    address = backend.start()
    request = workflow_input("version-mismatch-execution")
    register = seeded_register(request)
    worker = _worker(address, register)
    client = TaskHubGrpcClient(host_address=address, secure_channel=False)
    try:
        worker.start()
        instance_id = client.schedule_new_orchestration(
            review_gate_orchestrator,
            input=request,
            instance_id=request.execution_id,
            version="2.0.0",
        )
        state = client.wait_for_orchestration_completion(instance_id, timeout=5)
        assert state is not None
        assert state.get_output(WorkflowOutput) == WorkflowOutput(
            WorkflowResultCode.VERSION_REJECTED,
            None,
            None,
        )
        assert register.effect_count(request.effect_command_id) == 0
    finally:
        worker.stop()
        client.close()
        backend.stop()
