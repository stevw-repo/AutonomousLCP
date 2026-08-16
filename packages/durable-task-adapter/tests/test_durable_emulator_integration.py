"""Opt-in proof against the digest-pinned local Scheduler emulator."""

import os

import pytest
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
from durabletask.azuremanaged.client import DurableTaskSchedulerClient
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from durabletask.client import OrchestrationStatus

pytestmark = [
    pytest.mark.durable_emulator,
    pytest.mark.skipif(
        os.environ.get("ASKLEGAL_DURABLE_EMULATOR") != "1",
        reason="set ASKLEGAL_DURABLE_EMULATOR=1 for the disposable emulator proof",
    ),
]


def _worker(register: FakeManagementRegister) -> DurableTaskSchedulerWorker:
    worker = DurableTaskSchedulerWorker(
        host_address="localhost:8080",
        taskhub="default",
        token_credential=None,
        secure_channel=False,
    )
    configure_worker(worker, register)
    return worker


def test_real_emulator_retains_history_across_fresh_worker() -> None:
    """Prove restart, buffered duplicate events, register recovery, and one effect."""
    request = workflow_input("emulator-restart-execution")
    register = seeded_register(request)
    first_worker = _worker(register)
    second_worker: DurableTaskSchedulerWorker | None = None
    client = DurableTaskSchedulerClient(
        host_address="localhost:8080",
        taskhub="default",
        token_credential=None,
        secure_channel=False,
    )
    try:
        first_worker.start()
        instance_id = client.schedule_new_orchestration(
            review_gate_orchestrator,
            input=request,
            instance_id=request.execution_id,
            version=request.workflow_version,
        )
        wait_until_waiting(client, instance_id)

        first_worker.stop()
        recovered = FakeManagementRegister.recover(register.snapshot())
        stale = ReviewEventRef("stale-event-1", synthetic_fingerprint("6"))
        valid = ReviewEventRef("valid-event-1", synthetic_fingerprint("7"))
        client.raise_orchestration_event(instance_id, REVIEW_EVENT_NAME, data=stale)
        client.raise_orchestration_event(instance_id, REVIEW_EVENT_NAME, data=stale)
        client.raise_orchestration_event(instance_id, REVIEW_EVENT_NAME, data=valid)

        second_worker = _worker(recovered)
        second_worker.start()
        state = client.wait_for_orchestration_completion(instance_id, timeout=15)

        assert state is not None
        assert state.runtime_status is OrchestrationStatus.COMPLETED
        assert state.get_output(WorkflowOutput) == WorkflowOutput(
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
    finally:
        first_worker.stop()
        if second_worker is not None:
            second_worker.stop()
        client.close()
