"""Framework-free immutable lifecycle kernel for the accepted M2 protocol."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Never


class DomainInvariantError(ValueError):
    """A supplied value violates the closed domain contract."""


def _raise_invariant(message: str) -> Never:
    raise DomainInvariantError(message)


def _raise_type(message: str) -> Never:
    raise TypeError(message)


def _validate_exact_text(value: object, field_name: str) -> None:
    if type(value) is not str:
        _raise_type(f"{field_name} must be an exact string")
    if not value or value.strip() != value:
        _raise_invariant(f"{field_name} must be non-empty and whitespace-exact")


def _validate_exact_integer(value: object, field_name: str, *, minimum: int) -> None:
    if type(value) is not int:
        _raise_type(f"{field_name} must be an exact integer")
    if value < minimum:
        _raise_invariant(f"{field_name} must be at least {minimum}")


def _validate_str_enum(value: object, field_name: str) -> None:
    if not isinstance(value, StrEnum):
        _raise_type(f"{field_name} must be a StrEnum member")


def _validate_state_type(value: object) -> None:
    if not isinstance(value, type) or not issubclass(value, StrEnum):
        _raise_type("state_type must be a StrEnum type")


def _validate_snapshot(value: object) -> None:
    if not isinstance(value, LifecycleSnapshot):
        _raise_type("snapshot must be a LifecycleSnapshot")


class TransitionResultCode(StrEnum):
    """Closed outcomes from applying one pure lifecycle transition."""

    APPLIED = "APPLIED"
    REJECTED_STALE_VERSION = "REJECTED_STALE_VERSION"
    REJECTED_INVALID_STATE = "REJECTED_INVALID_STATE"


class PipelineRunState(StrEnum):
    """Closed Pipeline Run states from D1 section 5."""

    RUN_PLANNED = "RUN_PLANNED"
    RUN_ADMITTED = "RUN_ADMITTED"
    RUN_ACTIVE = "RUN_ACTIVE"
    RUN_AWAITING_REVIEW = "RUN_AWAITING_REVIEW"
    RUN_APPROVED = "RUN_APPROVED"
    RUN_PROMOTING = "RUN_PROMOTING"
    RUN_SUCCEEDED = "RUN_SUCCEEDED"
    RUN_NO_CHANGE = "RUN_NO_CHANGE"
    RUN_REJECTED = "RUN_REJECTED"
    RUN_CANCELLED = "RUN_CANCELLED"
    RUN_BLOCKED = "RUN_BLOCKED"
    RUN_FAILED = "RUN_FAILED"
    RUN_ROLLED_BACK = "RUN_ROLLED_BACK"


class WorkItemState(StrEnum):
    """Closed Work Item states from D1 section 6."""

    WORK_PLANNED = "WORK_PLANNED"
    WORK_DISPATCHED = "WORK_DISPATCHED"
    WORK_RUNNING = "WORK_RUNNING"
    WORK_RETRY_WAIT = "WORK_RETRY_WAIT"
    WORK_SUCCEEDED = "WORK_SUCCEEDED"
    WORK_NO_CHANGE = "WORK_NO_CHANGE"
    WORK_BLOCKED = "WORK_BLOCKED"
    WORK_QUARANTINED = "WORK_QUARANTINED"
    WORK_CANCELLED = "WORK_CANCELLED"
    WORK_FAILED_FINAL = "WORK_FAILED_FINAL"


class SourceContractReviewState(StrEnum):
    """Closed Source Contract Review states from D1 section 7."""

    OPEN = "OPEN"
    RESOLVED_SUPPORTED = "RESOLVED_SUPPORTED"
    RESOLVED_CHANGED = "RESOLVED_CHANGED"
    RESOLVED_UNSUPPORTED = "RESOLVED_UNSUPPORTED"
    SUPERSEDED = "SUPERSEDED"


class CoverageGapState(StrEnum):
    """Closed Coverage Gap states from D1 section 7."""

    OPEN = "OPEN"
    MITIGATED_CARRY_FORWARD = "MITIGATED_CARRY_FORWARD"
    MITIGATED_WITHHOLDING = "MITIGATED_WITHHOLDING"
    RESOLVED_COMPLETE = "RESOLVED_COMPLETE"
    SUPERSEDED = "SUPERSEDED"


class QuarantineState(StrEnum):
    """Closed Quarantine states from D1 section 7."""

    OPEN = "OPEN"
    RELEASED_TO_REPROCESSING = "RELEASED_TO_REPROCESSING"
    PERMANENTLY_EXCLUDED = "PERMANENTLY_EXCLUDED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot[StateT: StrEnum]:
    """One immutable authoritative aggregate state at a monotonic version."""

    entity_id: str
    state: StateT
    version: int
    predecessor_ref: str | None = None

    def __post_init__(self) -> None:
        """Reject identities and versions that cannot enter the domain."""
        _validate_exact_text(self.entity_id, "entity_id")
        _validate_str_enum(self.state, "state")
        _validate_exact_integer(self.version, "version", minimum=1)
        if self.predecessor_ref is not None:
            _validate_exact_text(self.predecessor_ref, "predecessor_ref")
            if self.predecessor_ref == self.entity_id:
                _raise_invariant("an entity cannot be its own predecessor")


@dataclass(frozen=True, slots=True)
class LifecycleEvent[StateT: StrEnum]:
    """The exact event produced by one applied transition."""

    entity_id: str
    from_state: StateT
    to_state: StateT
    prior_version: int
    new_version: int

    def __post_init__(self) -> None:
        """Reject malformed events even when constructed outside a machine."""
        _validate_exact_text(self.entity_id, "entity_id")
        _validate_str_enum(self.from_state, "from_state")
        _validate_str_enum(self.to_state, "to_state")
        if type(self.from_state) is not type(self.to_state):
            _raise_type("event states must belong to the same lifecycle")
        if self.from_state is self.to_state:
            _raise_invariant("event states must describe a lifecycle change")
        _validate_exact_integer(self.prior_version, "prior_version", minimum=1)
        _validate_exact_integer(self.new_version, "new_version", minimum=2)
        if self.new_version != self.prior_version + 1:
            _raise_invariant("new_version must increment prior_version exactly once")


@dataclass(frozen=True, slots=True)
class TransitionResult[StateT: StrEnum]:
    """Pure transition result with no persistence or external effect."""

    code: TransitionResultCode
    snapshot: LifecycleSnapshot[StateT]
    event: LifecycleEvent[StateT] | None

    def __post_init__(self) -> None:
        """Keep applied and rejected results structurally self-consistent."""
        if type(self.code) is not TransitionResultCode:
            _raise_type("code must be a TransitionResultCode member")
        _validate_snapshot(self.snapshot)
        if self.code is TransitionResultCode.APPLIED:
            if self.event is None:
                _raise_invariant("an applied transition must contain an event")
            if self.event.entity_id != self.snapshot.entity_id:
                _raise_invariant("event and snapshot identities must match")
            if self.event.to_state is not self.snapshot.state:
                _raise_invariant("event target and snapshot state must match")
            if self.event.new_version != self.snapshot.version:
                _raise_invariant("event and snapshot versions must match")
        elif self.event is not None:
            _raise_invariant("a rejected transition cannot contain an event")

    @property
    def applied(self) -> bool:
        """Return whether this result appended one lifecycle event."""
        return self.code is TransitionResultCode.APPLIED


@dataclass(frozen=True, slots=True)
class ReprocessingAdmission:
    """A released quarantine authorizes one new linked Work Item identity."""

    quarantine_id: str
    work_item: LifecycleSnapshot[WorkItemState]

    def __post_init__(self) -> None:
        """Require a new planned work item linked to its predecessor."""
        _validate_exact_text(self.quarantine_id, "quarantine_id")
        if type(self.work_item.state) is not WorkItemState:
            _raise_type("work_item must belong to the Work Item lifecycle")
        if self.work_item.state is not WorkItemState.WORK_PLANNED or self.work_item.version != 1:
            _raise_invariant("re-entry must create a new planned version-one Work Item")
        if self.work_item.predecessor_ref is None:
            _raise_invariant("re-entry Work Item must name its predecessor")


def admit_quarantine_reentry(
    quarantine: LifecycleSnapshot[QuarantineState],
    *,
    new_work_item_id: str,
    predecessor_work_item_ref: str,
) -> ReprocessingAdmission:
    """Create a linked work item only after an exact release-to-reprocessing fact."""
    if type(quarantine.state) is not QuarantineState:
        _raise_type("quarantine must belong to the Quarantine lifecycle")
    if quarantine.state is not QuarantineState.RELEASED_TO_REPROCESSING:
        _raise_invariant("quarantine must be released before re-entry")
    return ReprocessingAdmission(
        quarantine.entity_id,
        WORK_ITEM_MACHINE.start(
            new_work_item_id,
            predecessor_ref=predecessor_work_item_ref,
        ),
    )


@dataclass(frozen=True, slots=True)
class StateMachine[StateT: StrEnum]:
    """A closed, reachable, forward-only lifecycle definition."""

    machine_id: str
    machine_version: str
    entity_type: str
    state_type: type[StateT]
    initial_state: StateT
    terminal_states: frozenset[StateT]
    transitions: frozenset[tuple[StateT, StateT]]

    def __post_init__(self) -> None:
        """Prove that the declared machine is closed and every state reachable."""
        _validate_exact_text(self.machine_id, "machine_id")
        _validate_exact_text(self.machine_version, "machine_version")
        _validate_exact_text(self.entity_type, "entity_type")
        _validate_state_type(self.state_type)

        states = frozenset(self.state_type)
        if type(self.initial_state) is not self.state_type:
            _raise_invariant("initial_state is outside the closed state type")
        if any(type(state) is not self.state_type for state in self.terminal_states):
            _raise_invariant("terminal_states contain an unknown state")

        self._validate_transition_rules()
        reachable = self._reachable_states()
        if reachable != set(states):
            missing = sorted(state.value for state in states - reachable)
            _raise_invariant(f"unreachable lifecycle states: {missing}")

    def _validate_transition_rules(self) -> None:
        for from_state, to_state in self.transitions:
            if type(from_state) is not self.state_type or type(to_state) is not self.state_type:
                _raise_invariant("transition contains an unknown state")
            if from_state in self.terminal_states:
                _raise_invariant("terminal states cannot have outgoing transitions")
            if from_state is to_state:
                _raise_invariant("self-transitions are not lifecycle changes")

    def _reachable_states(self) -> set[StateT]:
        reachable = {self.initial_state}
        while True:
            expanded = reachable | {
                to_state for from_state, to_state in self.transitions if from_state in reachable
            }
            if expanded == reachable:
                return reachable
            reachable = expanded

    def start(
        self,
        entity_id: str,
        *,
        predecessor_ref: str | None = None,
    ) -> LifecycleSnapshot[StateT]:
        """Create a new aggregate at version one; recurrence uses a new identity."""
        return LifecycleSnapshot(
            entity_id=entity_id,
            state=self.initial_state,
            version=1,
            predecessor_ref=predecessor_ref,
        )

    def transition(
        self,
        snapshot: LifecycleSnapshot[StateT],
        to_state: StateT,
        *,
        expected_version: int,
    ) -> TransitionResult[StateT]:
        """Apply one exact transition or return an immutable rejection."""
        _validate_snapshot(snapshot)
        if type(snapshot.state) is not self.state_type:
            _raise_type("snapshot state belongs to a different lifecycle")
        if type(to_state) is not self.state_type:
            _raise_type("target state belongs to a different lifecycle")
        _validate_exact_integer(expected_version, "expected_version", minimum=0)
        if expected_version != snapshot.version:
            return TransitionResult(
                code=TransitionResultCode.REJECTED_STALE_VERSION,
                snapshot=snapshot,
                event=None,
            )
        if (snapshot.state, to_state) not in self.transitions:
            return TransitionResult(
                code=TransitionResultCode.REJECTED_INVALID_STATE,
                snapshot=snapshot,
                event=None,
            )

        new_version = snapshot.version + 1
        event = LifecycleEvent(
            entity_id=snapshot.entity_id,
            from_state=snapshot.state,
            to_state=to_state,
            prior_version=snapshot.version,
            new_version=new_version,
        )
        return TransitionResult(
            code=TransitionResultCode.APPLIED,
            snapshot=LifecycleSnapshot(
                entity_id=snapshot.entity_id,
                state=to_state,
                version=new_version,
                predecessor_ref=snapshot.predecessor_ref,
            ),
            event=event,
        )


PIPELINE_RUN_MACHINE = StateMachine(
    machine_id="asklegal.pipeline-run-lifecycle.v1",
    machine_version="1.0.0",
    entity_type="Pipeline Run",
    state_type=PipelineRunState,
    initial_state=PipelineRunState.RUN_PLANNED,
    terminal_states=frozenset(
        {
            PipelineRunState.RUN_SUCCEEDED,
            PipelineRunState.RUN_NO_CHANGE,
            PipelineRunState.RUN_REJECTED,
            PipelineRunState.RUN_CANCELLED,
            PipelineRunState.RUN_BLOCKED,
            PipelineRunState.RUN_FAILED,
            PipelineRunState.RUN_ROLLED_BACK,
        }
    ),
    transitions=frozenset(
        {
            (PipelineRunState.RUN_PLANNED, PipelineRunState.RUN_ADMITTED),
            (PipelineRunState.RUN_PLANNED, PipelineRunState.RUN_BLOCKED),
            (PipelineRunState.RUN_PLANNED, PipelineRunState.RUN_CANCELLED),
            (PipelineRunState.RUN_PLANNED, PipelineRunState.RUN_FAILED),
            (PipelineRunState.RUN_ADMITTED, PipelineRunState.RUN_ACTIVE),
            (PipelineRunState.RUN_ADMITTED, PipelineRunState.RUN_BLOCKED),
            (PipelineRunState.RUN_ADMITTED, PipelineRunState.RUN_CANCELLED),
            (PipelineRunState.RUN_ADMITTED, PipelineRunState.RUN_FAILED),
            (PipelineRunState.RUN_ACTIVE, PipelineRunState.RUN_AWAITING_REVIEW),
            (PipelineRunState.RUN_ACTIVE, PipelineRunState.RUN_NO_CHANGE),
            (PipelineRunState.RUN_ACTIVE, PipelineRunState.RUN_BLOCKED),
            (PipelineRunState.RUN_ACTIVE, PipelineRunState.RUN_CANCELLED),
            (PipelineRunState.RUN_ACTIVE, PipelineRunState.RUN_FAILED),
            (PipelineRunState.RUN_AWAITING_REVIEW, PipelineRunState.RUN_APPROVED),
            (PipelineRunState.RUN_AWAITING_REVIEW, PipelineRunState.RUN_REJECTED),
            (PipelineRunState.RUN_AWAITING_REVIEW, PipelineRunState.RUN_BLOCKED),
            (PipelineRunState.RUN_AWAITING_REVIEW, PipelineRunState.RUN_CANCELLED),
            (PipelineRunState.RUN_AWAITING_REVIEW, PipelineRunState.RUN_FAILED),
            (PipelineRunState.RUN_APPROVED, PipelineRunState.RUN_PROMOTING),
            (PipelineRunState.RUN_APPROVED, PipelineRunState.RUN_BLOCKED),
            (PipelineRunState.RUN_APPROVED, PipelineRunState.RUN_CANCELLED),
            (PipelineRunState.RUN_APPROVED, PipelineRunState.RUN_FAILED),
            (PipelineRunState.RUN_PROMOTING, PipelineRunState.RUN_SUCCEEDED),
            (PipelineRunState.RUN_PROMOTING, PipelineRunState.RUN_ROLLED_BACK),
            (PipelineRunState.RUN_PROMOTING, PipelineRunState.RUN_FAILED),
        }
    ),
)


WORK_ITEM_MACHINE = StateMachine(
    machine_id="asklegal.work-item-lifecycle.v1",
    machine_version="1.0.0",
    entity_type="Work Item",
    state_type=WorkItemState,
    initial_state=WorkItemState.WORK_PLANNED,
    terminal_states=frozenset(
        {
            WorkItemState.WORK_SUCCEEDED,
            WorkItemState.WORK_NO_CHANGE,
            WorkItemState.WORK_BLOCKED,
            WorkItemState.WORK_QUARANTINED,
            WorkItemState.WORK_CANCELLED,
            WorkItemState.WORK_FAILED_FINAL,
        }
    ),
    transitions=frozenset(
        {
            (WorkItemState.WORK_PLANNED, WorkItemState.WORK_DISPATCHED),
            (WorkItemState.WORK_PLANNED, WorkItemState.WORK_BLOCKED),
            (WorkItemState.WORK_PLANNED, WorkItemState.WORK_CANCELLED),
            (WorkItemState.WORK_PLANNED, WorkItemState.WORK_FAILED_FINAL),
            (WorkItemState.WORK_DISPATCHED, WorkItemState.WORK_RUNNING),
            (WorkItemState.WORK_DISPATCHED, WorkItemState.WORK_BLOCKED),
            (WorkItemState.WORK_DISPATCHED, WorkItemState.WORK_CANCELLED),
            (WorkItemState.WORK_DISPATCHED, WorkItemState.WORK_FAILED_FINAL),
            (WorkItemState.WORK_RUNNING, WorkItemState.WORK_SUCCEEDED),
            (WorkItemState.WORK_RUNNING, WorkItemState.WORK_NO_CHANGE),
            (WorkItemState.WORK_RUNNING, WorkItemState.WORK_BLOCKED),
            (WorkItemState.WORK_RUNNING, WorkItemState.WORK_QUARANTINED),
            (WorkItemState.WORK_RUNNING, WorkItemState.WORK_CANCELLED),
            (WorkItemState.WORK_RUNNING, WorkItemState.WORK_FAILED_FINAL),
            (WorkItemState.WORK_RUNNING, WorkItemState.WORK_RETRY_WAIT),
            (WorkItemState.WORK_RETRY_WAIT, WorkItemState.WORK_DISPATCHED),
            (WorkItemState.WORK_RETRY_WAIT, WorkItemState.WORK_BLOCKED),
            (WorkItemState.WORK_RETRY_WAIT, WorkItemState.WORK_CANCELLED),
            (WorkItemState.WORK_RETRY_WAIT, WorkItemState.WORK_FAILED_FINAL),
        }
    ),
)


SOURCE_CONTRACT_REVIEW_MACHINE = StateMachine(
    machine_id="asklegal.source-contract-review-lifecycle.v1",
    machine_version="1.0.0",
    entity_type="Source Contract Review",
    state_type=SourceContractReviewState,
    initial_state=SourceContractReviewState.OPEN,
    terminal_states=frozenset(
        {
            SourceContractReviewState.RESOLVED_SUPPORTED,
            SourceContractReviewState.RESOLVED_CHANGED,
            SourceContractReviewState.RESOLVED_UNSUPPORTED,
            SourceContractReviewState.SUPERSEDED,
        }
    ),
    transitions=frozenset(
        {
            (SourceContractReviewState.OPEN, SourceContractReviewState.RESOLVED_SUPPORTED),
            (SourceContractReviewState.OPEN, SourceContractReviewState.RESOLVED_CHANGED),
            (SourceContractReviewState.OPEN, SourceContractReviewState.RESOLVED_UNSUPPORTED),
            (SourceContractReviewState.OPEN, SourceContractReviewState.SUPERSEDED),
        }
    ),
)


COVERAGE_GAP_MACHINE = StateMachine(
    machine_id="asklegal.coverage-gap-lifecycle.v1",
    machine_version="1.0.0",
    entity_type="Coverage Gap",
    state_type=CoverageGapState,
    initial_state=CoverageGapState.OPEN,
    terminal_states=frozenset(
        {
            CoverageGapState.RESOLVED_COMPLETE,
            CoverageGapState.SUPERSEDED,
        }
    ),
    transitions=frozenset(
        {
            (
                CoverageGapState.MITIGATED_CARRY_FORWARD,
                CoverageGapState.MITIGATED_WITHHOLDING,
            ),
            (
                CoverageGapState.MITIGATED_WITHHOLDING,
                CoverageGapState.MITIGATED_CARRY_FORWARD,
            ),
            (CoverageGapState.OPEN, CoverageGapState.MITIGATED_CARRY_FORWARD),
            (CoverageGapState.OPEN, CoverageGapState.MITIGATED_WITHHOLDING),
            (CoverageGapState.OPEN, CoverageGapState.RESOLVED_COMPLETE),
            (CoverageGapState.OPEN, CoverageGapState.SUPERSEDED),
            (
                CoverageGapState.MITIGATED_CARRY_FORWARD,
                CoverageGapState.RESOLVED_COMPLETE,
            ),
            (CoverageGapState.MITIGATED_CARRY_FORWARD, CoverageGapState.SUPERSEDED),
            (CoverageGapState.MITIGATED_WITHHOLDING, CoverageGapState.RESOLVED_COMPLETE),
            (CoverageGapState.MITIGATED_WITHHOLDING, CoverageGapState.SUPERSEDED),
        }
    ),
)


QUARANTINE_MACHINE = StateMachine(
    machine_id="asklegal.quarantine-lifecycle.v1",
    machine_version="1.0.0",
    entity_type="Quarantine",
    state_type=QuarantineState,
    initial_state=QuarantineState.OPEN,
    terminal_states=frozenset(
        {
            QuarantineState.RELEASED_TO_REPROCESSING,
            QuarantineState.PERMANENTLY_EXCLUDED,
            QuarantineState.SUPERSEDED,
        }
    ),
    transitions=frozenset(
        {
            (QuarantineState.OPEN, QuarantineState.RELEASED_TO_REPROCESSING),
            (QuarantineState.OPEN, QuarantineState.PERMANENTLY_EXCLUDED),
            (QuarantineState.OPEN, QuarantineState.SUPERSEDED),
        }
    ),
)


__all__ = [
    "COVERAGE_GAP_MACHINE",
    "PIPELINE_RUN_MACHINE",
    "QUARANTINE_MACHINE",
    "SOURCE_CONTRACT_REVIEW_MACHINE",
    "WORK_ITEM_MACHINE",
    "CoverageGapState",
    "DomainInvariantError",
    "LifecycleEvent",
    "LifecycleSnapshot",
    "PipelineRunState",
    "QuarantineState",
    "ReprocessingAdmission",
    "SourceContractReviewState",
    "StateMachine",
    "TransitionResult",
    "TransitionResultCode",
    "WorkItemState",
    "admit_quarantine_reentry",
]
