"""Adversarial unit proofs for register-owned durable authority."""

from dataclasses import replace

import pytest
from asklegal_durable_task import ReviewEventRef, ReviewResolutionCode
from asklegal_durable_task.fake_register import (
    EffectFingerprintMismatch,
    FakeManagementRegister,
    RegisterAuthorityError,
)
from asklegal_durable_task.models import EffectRequest
from durable_test_support import seeded_register, synthetic_fingerprint, workflow_input


def _effect_request(request_id: str = "fake-register-execution") -> EffectRequest:
    workflow = workflow_input(request_id)
    return EffectRequest(
        execution_id=workflow.execution_id,
        workflow_version=workflow.workflow_version,
        build_fingerprint=workflow.build_fingerprint,
        configuration_fingerprint=workflow.configuration_fingerprint,
        contract_fingerprint=workflow.contract_fingerprint,
        input_fingerprint=workflow.input_fingerprint,
        approval_event_id="valid-event-1",
        command_id=workflow.effect_command_id,
        command_fingerprint=workflow.effect_command_fingerprint,
    )


def test_stale_duplicate_and_valid_events_survive_register_recovery() -> None:
    """Reject stale input, deduplicate it after recovery, then accept current input."""
    workflow = workflow_input("fake-register-execution")
    register = seeded_register(workflow)
    stale = ReviewEventRef("stale-event-1", synthetic_fingerprint("6"))
    valid = ReviewEventRef("valid-event-1", synthetic_fingerprint("7"))

    first = register.resolve_review_event(workflow.execution_id, stale)
    recovered = FakeManagementRegister.recover(register.snapshot())
    duplicate = recovered.resolve_review_event(workflow.execution_id, stale)
    accepted = recovered.resolve_review_event(workflow.execution_id, valid)

    assert first.code is ReviewResolutionCode.STALE_FINGERPRINT
    assert duplicate.code is ReviewResolutionCode.DUPLICATE_EVENT
    assert accepted.code is ReviewResolutionCode.ACCEPTED


def test_effect_is_idempotent_and_bound_to_exact_request() -> None:
    """Return one receipt for retries and reject idempotency-key reuse."""
    workflow = workflow_input("fake-register-execution")
    register = seeded_register(workflow)
    register.resolve_review_event(
        workflow.execution_id,
        ReviewEventRef("valid-event-1", synthetic_fingerprint("7")),
    )
    request = _effect_request()

    first = register.apply_effect(request)
    replay = register.apply_effect(request)

    assert first.replayed is False
    assert replay.replayed is True
    assert first.receipt_id == replay.receipt_id
    assert register.effect_count(request.command_id) == 1
    assert register.effect_attempt_count(request.command_id) == 2

    changed = replace(request, input_fingerprint=synthetic_fingerprint("8"))
    with pytest.raises(EffectFingerprintMismatch, match="REGISTER_EFFECT_FINGERPRINT_MISMATCH"):
        register.apply_effect(changed)


def test_effect_rechecks_current_capability_and_lineage() -> None:
    """Reject a stale effect before a receipt or synthetic effect exists."""
    workflow = workflow_input("stale-lineage-execution")
    register = seeded_register(workflow)
    register.resolve_review_event(
        workflow.execution_id,
        ReviewEventRef("valid-event-1", synthetic_fingerprint("7")),
    )
    stale = replace(
        _effect_request("stale-lineage-execution"),
        build_fingerprint=synthetic_fingerprint("9"),
    )

    with pytest.raises(RegisterAuthorityError, match="REGISTER_LINEAGE_REJECTED"):
        register.apply_effect(stale)
    assert register.effect_count(stale.command_id) == 0
