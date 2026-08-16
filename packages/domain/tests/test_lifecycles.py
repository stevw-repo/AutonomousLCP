"""Conformance tests for the first bounded M2 domain-kernel checkpoint."""

from enum import StrEnum

import pytest
from asklegal_domain import (
    COVERAGE_GAP_MACHINE,
    PIPELINE_RUN_MACHINE,
    QUARANTINE_MACHINE,
    SOURCE_CONTRACT_REVIEW_MACHINE,
    WORK_ITEM_MACHINE,
    CoverageGapState,
    LifecycleSnapshot,
    PipelineRunState,
    QuarantineState,
    SourceContractReviewState,
    StateMachine,
    TransitionResult,
    TransitionResultCode,
    WorkItemState,
)


def _assert_machine_is_exhaustive[StateT: StrEnum](machine: StateMachine[StateT]) -> None:
    for from_state, to_state in machine.transitions:
        before = LifecycleSnapshot(entity_id="entity-1", state=from_state, version=7)
        result = machine.transition(before, to_state, expected_version=7)

        assert result.code is TransitionResultCode.APPLIED
        assert result.applied
        assert result.snapshot.entity_id == before.entity_id
        assert result.snapshot.state is to_state
        assert result.snapshot.version == 8
        assert result.event is not None
        assert result.event.from_state is from_state
        assert result.event.to_state is to_state
        assert result.event.prior_version == 7
        assert result.event.new_version == 8

    for from_state in machine.state_type:
        for to_state in machine.state_type:
            if (from_state, to_state) in machine.transitions:
                continue
            before = LifecycleSnapshot(entity_id="entity-2", state=from_state, version=4)
            result = machine.transition(before, to_state, expected_version=4)

            assert result.code is TransitionResultCode.REJECTED_INVALID_STATE
            assert not result.applied
            assert result.snapshot is before
            assert result.event is None


def test_all_declared_transitions_apply_and_every_unlisted_transition_fails() -> None:
    _assert_machine_is_exhaustive(PIPELINE_RUN_MACHINE)
    _assert_machine_is_exhaustive(WORK_ITEM_MACHINE)
    _assert_machine_is_exhaustive(SOURCE_CONTRACT_REVIEW_MACHINE)
    _assert_machine_is_exhaustive(COVERAGE_GAP_MACHINE)
    _assert_machine_is_exhaustive(QUARANTINE_MACHINE)


def test_stale_version_rejects_without_changing_the_snapshot() -> None:
    before = PIPELINE_RUN_MACHINE.start("run-1")

    result = PIPELINE_RUN_MACHINE.transition(
        before,
        PipelineRunState.RUN_ADMITTED,
        expected_version=0,
    )

    assert result.code is TransitionResultCode.REJECTED_STALE_VERSION
    assert result.snapshot is before
    assert result.event is None


def test_applied_transition_increments_version_exactly_once() -> None:
    planned = PIPELINE_RUN_MACHINE.start("run-2")
    admitted = PIPELINE_RUN_MACHINE.transition(
        planned,
        PipelineRunState.RUN_ADMITTED,
        expected_version=1,
    ).snapshot
    active = PIPELINE_RUN_MACHINE.transition(
        admitted,
        PipelineRunState.RUN_ACTIVE,
        expected_version=2,
    ).snapshot

    assert planned.version == 1
    assert admitted.version == 2
    assert active.version == 3


def test_pipeline_run_cannot_be_cancelled_after_promotion_starts() -> None:
    promoting = LifecycleSnapshot(
        entity_id="run-promoting",
        state=PipelineRunState.RUN_PROMOTING,
        version=6,
    )

    cancelled = PIPELINE_RUN_MACHINE.transition(
        promoting,
        PipelineRunState.RUN_CANCELLED,
        expected_version=6,
    )
    rolled_back = PIPELINE_RUN_MACHINE.transition(
        promoting,
        PipelineRunState.RUN_ROLLED_BACK,
        expected_version=6,
    )

    assert cancelled.code is TransitionResultCode.REJECTED_INVALID_STATE
    assert rolled_back.code is TransitionResultCode.APPLIED


def test_work_retry_preserves_identity_and_returns_to_dispatch() -> None:
    running = LifecycleSnapshot(
        entity_id="work-1",
        state=WorkItemState.WORK_RUNNING,
        version=3,
    )

    retry_wait = WORK_ITEM_MACHINE.transition(
        running,
        WorkItemState.WORK_RETRY_WAIT,
        expected_version=3,
    ).snapshot
    dispatched = WORK_ITEM_MACHINE.transition(
        retry_wait,
        WorkItemState.WORK_DISPATCHED,
        expected_version=4,
    ).snapshot

    assert retry_wait.entity_id == running.entity_id
    assert dispatched.entity_id == running.entity_id
    assert dispatched.version == 5


@pytest.mark.parametrize(
    "mitigated_state",
    [CoverageGapState.MITIGATED_CARRY_FORWARD, CoverageGapState.MITIGATED_WITHHOLDING],
)
def test_mitigated_gap_remains_open_to_later_complete_resolution(
    mitigated_state: CoverageGapState,
) -> None:
    opened = COVERAGE_GAP_MACHINE.start("gap-1")
    mitigated = COVERAGE_GAP_MACHINE.transition(
        opened,
        mitigated_state,
        expected_version=1,
    ).snapshot

    resolved = COVERAGE_GAP_MACHINE.transition(
        mitigated,
        CoverageGapState.RESOLVED_COMPLETE,
        expected_version=2,
    )

    assert mitigated.state not in COVERAGE_GAP_MACHINE.terminal_states
    assert resolved.code is TransitionResultCode.APPLIED


@pytest.mark.parametrize(
    ("machine", "closed_state"),
    [
        (SOURCE_CONTRACT_REVIEW_MACHINE, SourceContractReviewState.RESOLVED_SUPPORTED),
        (QUARANTINE_MACHINE, QuarantineState.RELEASED_TO_REPROCESSING),
    ],
)
def test_closed_record_cannot_reopen_and_recurrence_gets_a_new_identity(
    machine: StateMachine[SourceContractReviewState] | StateMachine[QuarantineState],
    closed_state: SourceContractReviewState | QuarantineState,
) -> None:
    if machine is SOURCE_CONTRACT_REVIEW_MACHINE:
        opened_review = SOURCE_CONTRACT_REVIEW_MACHINE.start("review-old")
        closed_review = SOURCE_CONTRACT_REVIEW_MACHINE.transition(
            opened_review,
            SourceContractReviewState.RESOLVED_SUPPORTED,
            expected_version=1,
        ).snapshot
        reopen = SOURCE_CONTRACT_REVIEW_MACHINE.transition(
            closed_review,
            SourceContractReviewState.OPEN,
            expected_version=2,
        )
        recurrence = SOURCE_CONTRACT_REVIEW_MACHINE.start(
            "review-new",
            predecessor_ref="review-old",
        )
    else:
        opened_quarantine = QUARANTINE_MACHINE.start("quarantine-old")
        closed_quarantine = QUARANTINE_MACHINE.transition(
            opened_quarantine,
            QuarantineState.RELEASED_TO_REPROCESSING,
            expected_version=1,
        ).snapshot
        reopen = QUARANTINE_MACHINE.transition(
            closed_quarantine,
            QuarantineState.OPEN,
            expected_version=2,
        )
        recurrence = QUARANTINE_MACHINE.start(
            "quarantine-new",
            predecessor_ref="quarantine-old",
        )

    assert closed_state in machine.terminal_states
    assert reopen.code is TransitionResultCode.REJECTED_INVALID_STATE
    assert recurrence.version == 1
    assert recurrence.predecessor_ref is not None
    assert recurrence.entity_id != recurrence.predecessor_ref


@pytest.mark.parametrize("invalid_id", ["", " leading", "trailing "])
def test_invalid_entity_identity_is_rejected(invalid_id: str) -> None:
    with pytest.raises(ValueError, match="entity_id"):
        PIPELINE_RUN_MACHINE.start(invalid_id)


def test_self_predecessor_is_rejected() -> None:
    with pytest.raises(ValueError, match="own predecessor"):
        QUARANTINE_MACHINE.start("quarantine-1", predecessor_ref="quarantine-1")


def test_negative_expected_version_is_rejected() -> None:
    planned = WORK_ITEM_MACHINE.start("work-negative-version")

    with pytest.raises(ValueError, match="at least 0"):
        WORK_ITEM_MACHINE.transition(
            planned,
            WorkItemState.WORK_DISPATCHED,
            expected_version=-1,
        )


@pytest.mark.parametrize("invalid_version", [True, False, 1.5])
def test_snapshot_version_requires_an_exact_runtime_integer(invalid_version: object) -> None:
    snapshot = PIPELINE_RUN_MACHINE.start("run-invalid-runtime-version")
    object.__setattr__(snapshot, "version", invalid_version)

    with pytest.raises(TypeError, match="version must be an exact integer"):
        snapshot.__post_init__()


def test_expected_version_rejects_boolean_integers() -> None:
    planned = WORK_ITEM_MACHINE.start("work-boolean-version")

    for invalid_expected_version in (True, False):
        with pytest.raises(TypeError, match="expected_version must be an exact integer"):
            WORK_ITEM_MACHINE.transition(
                planned,
                WorkItemState.WORK_DISPATCHED,
                expected_version=invalid_expected_version,
            )


def test_applied_result_requires_an_event() -> None:
    planned = PIPELINE_RUN_MACHINE.start("run-result-without-event")

    with pytest.raises(ValueError, match="must contain an event"):
        TransitionResult(
            code=TransitionResultCode.APPLIED,
            snapshot=planned,
            event=None,
        )


def test_machine_definition_rejects_unreachable_states() -> None:
    class ExampleState(StrEnum):
        FIRST = "FIRST"
        SECOND = "SECOND"

    with pytest.raises(ValueError, match="unreachable"):
        StateMachine(
            machine_id="example.v1",
            machine_version="1.0.0",
            entity_type="Example",
            state_type=ExampleState,
            initial_state=ExampleState.FIRST,
            terminal_states=frozenset({ExampleState.FIRST}),
            transitions=frozenset(),
        )
