"""Recoverable fake of the authoritative Management Register boundary."""

from dataclasses import dataclass
from threading import RLock

from asklegal_durable_task.models import (
    EffectRequest,
    EffectResult,
    ReviewEventRef,
    ReviewResolution,
    ReviewResolutionCode,
    WorkflowInput,
)

_CAPABILITY_REJECTED = "REGISTER_CAPABILITY_REJECTED"
_EFFECT_ACK_LOST = "EFFECT_ACK_LOST"
_EFFECT_FINGERPRINT_MISMATCH = "REGISTER_EFFECT_FINGERPRINT_MISMATCH"
_EVENT_CONFLICT = "REGISTER_EVENT_CONFLICT"
_EXECUTION_CONFLICT = "REGISTER_EXECUTION_CONFLICT"
_LINEAGE_REJECTED = "REGISTER_LINEAGE_REJECTED"
_APPROVAL_REJECTED = "REGISTER_APPROVAL_REJECTED"


class RegisterAuthorityError(RuntimeError):
    """The current register state does not authorize an effect."""


class EffectFingerprintMismatch(RuntimeError):
    """An effect idempotency key was reused for different exact authority."""


class LostEffectAcknowledgement(RuntimeError):
    """The effect committed but the worker did not receive acknowledgement."""


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """Current authoritative lineage and effect command for one execution."""

    workflow_input: WorkflowInput
    capability_enabled: bool = True


@dataclass(frozen=True, slots=True)
class ReviewEventFact:
    """Authoritative register fact referenced by an opaque Scheduler event."""

    execution_id: str
    event_id: str
    event_fingerprint: str
    input_fingerprint: str


@dataclass(frozen=True, slots=True)
class EventAuditFact:
    """One immutable closed result from event resolution."""

    execution_id: str
    event_id: str
    event_fingerprint: str
    code: ReviewResolutionCode


@dataclass(frozen=True, slots=True)
class EffectReceiptRecord:
    """Immutable effect request and receipt stored under one command ID."""

    request: EffectRequest
    receipt_id: str


@dataclass(frozen=True, slots=True)
class FakeRegisterSnapshot:
    """Exact state used to reconstruct the fake after worker termination."""

    executions: tuple[ExecutionRecord, ...]
    review_events: tuple[ReviewEventFact, ...]
    processed_events: tuple[tuple[str, str, str], ...]
    accepted_events: tuple[tuple[str, str], ...]
    event_audit: tuple[EventAuditFact, ...]
    effect_receipts: tuple[EffectReceiptRecord, ...]
    effect_counts: tuple[tuple[str, int], ...]
    effect_attempts: tuple[tuple[str, int], ...]
    lost_ack_remaining: tuple[tuple[str, int], ...]


class FakeManagementRegister:
    """Thread-safe fake that keeps business authority outside Scheduler history."""

    def __init__(self) -> None:
        """Create an empty authoritative fake."""
        self._lock = RLock()
        self._executions: dict[str, ExecutionRecord] = {}
        self._review_events: dict[str, ReviewEventFact] = {}
        self._processed_events: set[tuple[str, str, str]] = set()
        self._accepted_events: dict[str, str] = {}
        self._event_audit: list[EventAuditFact] = []
        self._effect_receipts: dict[str, EffectReceiptRecord] = {}
        self._effect_counts: dict[str, int] = {}
        self._effect_attempts: dict[str, int] = {}
        self._lost_ack_remaining: dict[str, int] = {}

    @classmethod
    def recover(cls, snapshot: FakeRegisterSnapshot) -> FakeManagementRegister:
        """Build a fresh fake from an exact authoritative snapshot."""
        register = cls()
        register._executions = {
            record.workflow_input.execution_id: record for record in snapshot.executions
        }
        register._review_events = {record.event_id: record for record in snapshot.review_events}
        register._processed_events = set(snapshot.processed_events)
        register._accepted_events = dict(snapshot.accepted_events)
        register._event_audit = list(snapshot.event_audit)
        register._effect_receipts = {
            record.request.command_id: record for record in snapshot.effect_receipts
        }
        register._effect_counts = dict(snapshot.effect_counts)
        register._effect_attempts = dict(snapshot.effect_attempts)
        register._lost_ack_remaining = dict(snapshot.lost_ack_remaining)
        return register

    def admit_execution(self, record: ExecutionRecord) -> None:
        """Admit one exact current execution lineage into the fake."""
        execution_id = record.workflow_input.execution_id
        with self._lock:
            existing = self._executions.get(execution_id)
            if existing is not None and existing != record:
                raise RegisterAuthorityError(_EXECUTION_CONFLICT)
            self._executions[execution_id] = record

    def record_review_event(self, fact: ReviewEventFact) -> None:
        """Record one exact review event fact before Scheduler delivery."""
        with self._lock:
            existing = self._review_events.get(fact.event_id)
            if existing is not None and existing != fact:
                raise RegisterAuthorityError(_EVENT_CONFLICT)
            self._review_events[fact.event_id] = fact

    def fail_next_effect_acknowledgement(self, command_id: str) -> None:
        """Arm one synthetic lost-ack failure after the effect commits."""
        with self._lock:
            self._lost_ack_remaining[command_id] = 1

    def resolve_review_event(
        self,
        execution_id: str,
        event: ReviewEventRef,
    ) -> ReviewResolution:
        """Resolve an opaque event against current authoritative register state."""
        with self._lock:
            execution = self._executions.get(execution_id)
            fact = self._review_events.get(event.event_id)
            code = self._review_resolution_code(execution_id, execution, fact, event)
            key = (execution_id, event.event_id, event.event_fingerprint)
            if key in self._processed_events:
                code = ReviewResolutionCode.DUPLICATE_EVENT
            else:
                self._processed_events.add(key)
                if code is ReviewResolutionCode.ACCEPTED:
                    self._accepted_events[execution_id] = event.event_id
            self._event_audit.append(
                EventAuditFact(execution_id, event.event_id, event.event_fingerprint, code)
            )
            return ReviewResolution(code, event.event_id)

    def apply_effect(self, request: EffectRequest) -> EffectResult:
        """Revalidate authority and atomically return an original or replayed receipt."""
        with self._lock:
            command_id = request.command_id
            self._effect_attempts[command_id] = self._effect_attempts.get(command_id, 0) + 1
            existing = self._effect_receipts.get(command_id)
            if existing is not None:
                if existing.request != request:
                    raise EffectFingerprintMismatch(_EFFECT_FINGERPRINT_MISMATCH)
                return EffectResult(existing.receipt_id, replayed=True)

            self._require_effect_authority(request)
            receipt_id = f"receipt:{command_id}"
            self._effect_receipts[command_id] = EffectReceiptRecord(request, receipt_id)
            self._effect_counts[command_id] = self._effect_counts.get(command_id, 0) + 1
            return EffectResult(receipt_id, replayed=False)

    def acknowledge_effect(self, command_id: str) -> None:
        """Raise once after commit to simulate an ambiguous activity acknowledgement."""
        with self._lock:
            remaining = self._lost_ack_remaining.get(command_id, 0)
            if remaining < 1:
                return
            self._lost_ack_remaining[command_id] = remaining - 1
        raise LostEffectAcknowledgement(_EFFECT_ACK_LOST)

    def snapshot(self) -> FakeRegisterSnapshot:
        """Return an exact immutable state for fake-register recovery."""
        with self._lock:
            return FakeRegisterSnapshot(
                executions=tuple(self._executions[key] for key in sorted(self._executions)),
                review_events=tuple(
                    self._review_events[key] for key in sorted(self._review_events)
                ),
                processed_events=tuple(sorted(self._processed_events)),
                accepted_events=tuple(sorted(self._accepted_events.items())),
                event_audit=tuple(self._event_audit),
                effect_receipts=tuple(
                    self._effect_receipts[key] for key in sorted(self._effect_receipts)
                ),
                effect_counts=tuple(sorted(self._effect_counts.items())),
                effect_attempts=tuple(sorted(self._effect_attempts.items())),
                lost_ack_remaining=tuple(sorted(self._lost_ack_remaining.items())),
            )

    def event_audit(self) -> tuple[EventAuditFact, ...]:
        """Return immutable event-resolution audit facts."""
        with self._lock:
            return tuple(self._event_audit)

    def effect_count(self, command_id: str) -> int:
        """Return the number of actual synthetic effects for a command."""
        with self._lock:
            return self._effect_counts.get(command_id, 0)

    def effect_attempt_count(self, command_id: str) -> int:
        """Return activity attempts, including replayed idempotent attempts."""
        with self._lock:
            return self._effect_attempts.get(command_id, 0)

    def _review_resolution_code(
        self,
        execution_id: str,
        execution: ExecutionRecord | None,
        fact: ReviewEventFact | None,
        event: ReviewEventRef,
    ) -> ReviewResolutionCode:
        if execution is None:
            return ReviewResolutionCode.WRONG_EXECUTION
        if fact is None:
            return ReviewResolutionCode.UNKNOWN_EVENT
        if fact.execution_id != execution_id:
            return ReviewResolutionCode.WRONG_EXECUTION
        if fact.event_fingerprint != event.event_fingerprint:
            return ReviewResolutionCode.STALE_FINGERPRINT
        if fact.input_fingerprint != execution.workflow_input.input_fingerprint:
            return ReviewResolutionCode.STALE_FINGERPRINT
        return ReviewResolutionCode.ACCEPTED

    def _require_effect_authority(self, request: EffectRequest) -> None:
        execution = self._executions.get(request.execution_id)
        if execution is None or not execution.capability_enabled:
            raise RegisterAuthorityError(_CAPABILITY_REJECTED)
        expected = execution.workflow_input
        exact_identity = (
            request.workflow_version == expected.workflow_version
            and request.build_fingerprint == expected.build_fingerprint
            and request.configuration_fingerprint == expected.configuration_fingerprint
            and request.contract_fingerprint == expected.contract_fingerprint
            and request.input_fingerprint == expected.input_fingerprint
            and request.command_id == expected.effect_command_id
            and request.command_fingerprint == expected.effect_command_fingerprint
        )
        if not exact_identity:
            raise RegisterAuthorityError(_LINEAGE_REJECTED)
        if self._accepted_events.get(request.execution_id) != request.approval_event_id:
            raise RegisterAuthorityError(_APPROVAL_REJECTED)
