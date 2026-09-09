"""Deterministic bounded scheduling over one immutable acquisition journal."""

from __future__ import annotations

import threading
import weakref
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Never, Protocol, TypeIs
from urllib.parse import urlsplit

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value

from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    AcquisitionFailureCode,
    AcquisitionJournalEntry,
    AdmissionFailedBeforeTransportPayload,
    AuthorizationRejectedPayload,
    CapturedVerifiedPayload,
    CheckpointItem,
    ContractRejectedPayload,
    CycleSafetyProfilePayload,
    DiscoveredPayload,
    ElapsedBudgetExhaustedPayload,
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    RetryableFailurePayload,
    RetryExhaustedPayload,
    StartedPayload,
    TerminalUnavailablePayload,
    TransportStartedPayload,
    WorkItemIdentity,
)

_NANOSECONDS_PER_SECOND = 1_000_000_000
_NANOSECONDS_PER_MICROSECOND = 1_000
_MICROSECONDS_PER_SECOND = 1_000_000
_MAXIMUM_ITEMS = 1_000_000
_MAXIMUM_PRIORITY_TEXT = 512
_MAXIMUM_HOST_LENGTH = 253
_MAXIMUM_ATTEMPTS = 1_000_000
_MAXIMUM_REDIRECTS_PER_CAPTURE = 20
_FINGERPRINT_PREFIX = "sha256:"
_ASCII_CONTROL_LIMIT = 32
_ASCII_DELETE = 127
_PRIORITY_PARTS = 3
_DEPENDENCY_ROW_PARTS = 2
_IMPORT_ROW_PARTS = 2
_WORK_ITEM_ID_LENGTH = 68
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_CYCLE_PROFILE_SCHEMA_ID = "asklegal.acquisition-cycle-safety-profile"
_SCHEMA_VERSION = "1.0.0"


class ResumableAcquisitionError(RuntimeError):
    """One closed scheduler, authorization, or work-contract failure."""

    def __init__(self, code: str) -> None:
        """Retain only one closed code safe for reports and logs."""
        super().__init__(code)
        self.code = code


class CaptureAuthorizationFailure(RuntimeError):
    """Transport signal that current read authority failed before a valid outcome."""


def _fail(code: str) -> Never:
    raise ResumableAcquisitionError(code)


def _exact_integer(value: object, *, minimum: int, maximum: int, code: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(code)
    return value


def _exact_text(value: object, *, maximum: int, code: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(
            ord(character) < _ASCII_CONTROL_LIMIT or ord(character) == _ASCII_DELETE
            for character in value
        )
    ):
        _fail(code)
    return value


def _optional_text(value: object, *, maximum: int, code: str) -> str | None:
    if value is None:
        return None
    return _exact_text(value, maximum=maximum, code=code)


def _fingerprint(value: object) -> str:
    return f"{_FINGERPRINT_PREFIX}{sha256(canonicalize(checked_json_value(value))).hexdigest()}"


class CaptureTransport(Protocol):
    """Read-only effect boundary supplied by one admitted source-family adapter."""

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        """Capture one exact immutable work item and return only closed facts."""
        ...


class RetainedObjectVerifier(Protocol):
    """Read-only boundary that re-reads one opaque retained object by exact facts."""

    def verify(
        self,
        item: WorkItemIdentity,
        object_ref: str,
        content_fingerprint: str,
        body_length: int,
    ) -> bool:
        """Return exact true only after current length and digest read-back agree."""
        ...


class AcquisitionClock(Protocol):
    """Injected wall and monotonic time used for pacing and retry eligibility."""

    def monotonic_ns(self) -> int:
        """Return one non-negative monotonic instant."""
        ...

    def now(self) -> datetime:
        """Return one aware wall-clock instant."""
        ...


@dataclass(frozen=True, slots=True)
class ScheduledWorkItem:
    """One immutable work identity plus deterministic scheduling facts."""

    identity: WorkItemIdentity
    priority: tuple[int, int, str]
    host: str
    not_before_monotonic_ns: int

    def __post_init__(self) -> None:
        """Validate exact immutable scheduling and identity facts."""
        if type(self.identity) is not WorkItemIdentity:
            _fail("WORK_ITEM_INVALID")
        try:
            WorkItemIdentity.from_json(self.identity.to_json())
        except (AttributeError, TypeError, ValueError) as error:
            code = "WORK_ITEM_INVALID"
            raise ResumableAcquisitionError(code) from error
        if (
            type(self.priority) is not tuple
            or len(self.priority) != _PRIORITY_PARTS
            or type(self.priority[0]) is not int
            or type(self.priority[1]) is not int
        ):
            _fail("SCHEDULE_INVALID")
        _exact_text(self.priority[2], maximum=_MAXIMUM_PRIORITY_TEXT, code="SCHEDULE_INVALID")
        host = _exact_text(self.host, maximum=_MAXIMUM_HOST_LENGTH, code="SCHEDULE_INVALID")
        parsed = urlsplit(self.identity.locator)
        if parsed.hostname != host or host != host.lower() or parsed.port not in {None, 443}:
            _fail("SCHEDULE_INVALID")
        _exact_integer(
            self.not_before_monotonic_ns,
            minimum=0,
            maximum=9_223_372_036_854_775_807,
            code="SCHEDULE_INVALID",
        )


@dataclass(frozen=True, slots=True)
class CaptureOutcome:
    """Complete transport and retained-object facts for one physical attempt."""

    work_item_id: str
    transition: JournalTransition
    status_code: int | None
    media_type: str | None
    final_url: str | None
    body_length: int
    body_fingerprint: str | None
    object_ref: str | None
    failure_code: str | None
    retry_not_before: str | None
    read_back_verified: bool
    redirect_chain: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject inexact primitives before the coordinator interprets the outcome."""
        work_item_id = _exact_text(
            self.work_item_id,
            maximum=_WORK_ITEM_ID_LENGTH,
            code="CAPTURE_OUTCOME_INVALID",
        )
        if not work_item_id.startswith("awi_") or len(work_item_id) != _WORK_ITEM_ID_LENGTH:
            _fail("CAPTURE_OUTCOME_INVALID")
        if type(self.transition) is not JournalTransition:
            _fail("CAPTURE_OUTCOME_INVALID")
        if self.status_code is not None:
            _exact_integer(
                self.status_code,
                minimum=100,
                maximum=599,
                code="CAPTURE_OUTCOME_INVALID",
            )
        _optional_text(self.media_type, maximum=127, code="CAPTURE_OUTCOME_INVALID")
        _optional_text(self.final_url, maximum=4_096, code="CAPTURE_OUTCOME_INVALID")
        _exact_integer(
            self.body_length,
            minimum=0,
            maximum=1_073_741_824,
            code="CAPTURE_OUTCOME_INVALID",
        )
        _optional_text(self.body_fingerprint, maximum=71, code="CAPTURE_OUTCOME_INVALID")
        _optional_text(self.object_ref, maximum=2_048, code="CAPTURE_OUTCOME_INVALID")
        _optional_text(self.failure_code, maximum=127, code="CAPTURE_OUTCOME_INVALID")
        _optional_text(self.retry_not_before, maximum=40, code="CAPTURE_OUTCOME_INVALID")
        if type(self.read_back_verified) is not bool:
            _fail("CAPTURE_OUTCOME_INVALID")
        if (
            type(self.redirect_chain) is not tuple
            or len(self.redirect_chain) > _MAXIMUM_REDIRECTS_PER_CAPTURE
        ):
            _fail("CAPTURE_OUTCOME_INVALID")
        for locator in self.redirect_chain:
            _exact_text(locator, maximum=4_096, code="CAPTURE_OUTCOME_INVALID")


@dataclass(frozen=True, slots=True)
class CycleBudget:
    """Exact cycle-wide request, retained-byte, elapsed, and redirect ceilings."""

    maximum_starts: int
    maximum_retained_bytes: int
    maximum_elapsed_seconds: int
    maximum_redirects: int

    def __post_init__(self) -> None:
        """Require exact non-negative bounded ceiling values."""
        _exact_integer(
            self.maximum_starts,
            minimum=0,
            maximum=1_000_000_000,
            code="CYCLE_BUDGET_INVALID",
        )
        _exact_integer(
            self.maximum_retained_bytes,
            minimum=0,
            maximum=1_152_921_504_606_846_976,
            code="CYCLE_BUDGET_INVALID",
        )
        _exact_integer(
            self.maximum_elapsed_seconds,
            minimum=0,
            maximum=31_536_000,
            code="CYCLE_BUDGET_INVALID",
        )
        _exact_integer(
            self.maximum_redirects,
            minimum=0,
            maximum=1_000_000_000,
            code="CYCLE_BUDGET_INVALID",
        )


@dataclass(frozen=True, slots=True, weakref_slot=True)
class AcquisitionCycleReport:
    """Canonical release-facing projection of one journaled cycle."""

    cycle_id: str
    result: AcquisitionCycleResult
    item_dispositions: tuple[CheckpointItem, ...]
    request_starts: int
    retained_bytes: int
    journal_head_fingerprint: str
    fingerprint: str

    def to_json(self) -> dict[str, JsonValue]:
        """Return byte-stable JSON independent of physical completion order."""
        return _json_object({**_report_body(self), "fingerprint": self.fingerprint})


@dataclass(frozen=True, slots=True)
class VerifiedCaptureBinding:
    """Exact retained-body facts carried by one runner-issued report."""

    work_item_id: str
    object_ref: str
    content_fingerprint: str
    body_length: int
    final_url: str
    redirect_chain: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ReportIssuance:
    reference: weakref.ReferenceType[object]
    fingerprint: str
    bindings: tuple[VerifiedCaptureBinding, ...]


_REPORT_ISSUANCE: dict[int, _ReportIssuance] = {}


def runner_verified_capture_bindings(report: object) -> tuple[VerifiedCaptureBinding, ...]:
    """Return journal-derived capture facts only for the live report issued by the runner."""
    if type(report) is not AcquisitionCycleReport:
        _fail("REPORT_NOT_RUNNER_ISSUED")
    issued = _REPORT_ISSUANCE.get(id(report))
    if (
        issued is None
        or issued.reference() is not report
        or issued.fingerprint != report.fingerprint
        or report.fingerprint != _fingerprint(_report_body(report))
    ):
        _fail("REPORT_NOT_RUNNER_ISSUED")
    return issued.bindings


def _json_object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if type(checked) is not dict:
        _fail("REPORT_INVALID")
    return checked


def _report_body(report: AcquisitionCycleReport) -> dict[str, object]:
    return {
        "schema_id": "asklegal.resumable-acquisition-report",
        "schema_version": "1.0.0",
        "cycle_id": report.cycle_id,
        "result": report.result.value,
        "item_dispositions": [item.to_json() for item in report.item_dispositions],
        "request_starts": report.request_starts,
        "retained_bytes": report.retained_bytes,
        # This is the canonical semantic journal projection. The physical hash-chain
        # head remains in LocalAcquisitionJournal and may reflect real completion order.
        "journal_head_fingerprint": report.journal_head_fingerprint,
    }


@dataclass(frozen=True, slots=True)
class _PendingAttempt:
    scheduled: ScheduledWorkItem
    attempt: int
    ready_monotonic_ns: int


@dataclass(frozen=True, slots=True)
class _InFlightAttempt:
    pending: _PendingAttempt
    reserved_retained_bytes: int
    reserved_redirects: int
    reserved_start_monotonic_ns: int
    host_not_before_epoch_us: int


@dataclass(frozen=True, slots=True)
class _CaptureExecution:
    """Worker-returned actual physical start plus its outcome or closed exception."""

    started_at_epoch_us: int
    outcome: CaptureOutcome | None
    failure: Exception | None


@dataclass(frozen=True, slots=True)
class _ElapsedExpiredBeforeTransport:
    """Typed worker result proving that no physical transport call began."""


@dataclass(frozen=True, slots=True)
class _AdmissionFailedBeforeTransport:
    """Typed worker result proving that admission failed before physical transport."""


@dataclass(slots=True)
class _BudgetState:
    starts: int
    retained_bytes: int
    redirects: int
    reserved_starts: int = 0
    reserved_retained_bytes: int = 0
    reserved_redirects: int = 0


@dataclass(slots=True)
class _RunStop:
    clean: bool = False
    budget: bool = False
    contract: bool = False
    evidence: bool = False
    authorization: bool = False
    elapsed_budget: bool = False

    @property
    def dispatch_stopped(self) -> bool:
        return self.clean or self.budget or self.contract or self.evidence or self.authorization


@dataclass(slots=True)
class _HostStartGate:
    """One host-local start lock and exact next transport-start instant."""

    lock: threading.Lock
    next_start_monotonic_ns: int = 0


class ResumableAcquisitionRunner:
    """Single-coordinator worker pool shared by all admitted acquisition families."""

    def __init__(  # noqa: PLR0913 - each injected control is an independent safety boundary.
        self,
        *,
        journal: LocalAcquisitionJournal,
        items: tuple[ScheduledWorkItem, ...],
        transport: CaptureTransport,
        retained_verifier: RetainedObjectVerifier,
        clock: AcquisitionClock,
        sleeper: Callable[[float], None],
        budget: CycleBudget,
        per_host_limit: int = 4,
        minimum_start_interval_ns: int = 0,
        maximum_attempts_per_item: int = 2,
        maximum_redirects_per_start: int = _MAXIMUM_REDIRECTS_PER_CAPTURE,
        stop_requested: Callable[[], bool] | None = None,
        dependencies: tuple[tuple[str, tuple[str, ...]], ...] = (),
        preverified_imports: tuple[tuple[str, ImportedCaptureVerifiedPayload], ...] = (),
    ) -> None:
        """Bind one journal, queue, transport, and complete set of safety controls."""
        if type(journal) is not LocalAcquisitionJournal:
            _fail("RUNNER_CONFIGURATION_INVALID")
        if type(items) is not tuple or not items or len(items) > _MAXIMUM_ITEMS:
            if type(items) is tuple and not items:
                _fail("WORK_GRAPH_EMPTY")
            _fail("RUNNER_CONFIGURATION_INVALID")
        if not callable(getattr(transport, "capture", None)):
            _fail("RUNNER_CONFIGURATION_INVALID")
        if not callable(getattr(retained_verifier, "verify", None)):
            _fail("RUNNER_CONFIGURATION_INVALID")
        if not callable(getattr(clock, "monotonic_ns", None)) or not callable(
            getattr(clock, "now", None)
        ):
            _fail("RUNNER_CONFIGURATION_INVALID")
        if not callable(sleeper) or (stop_requested is not None and not callable(stop_requested)):
            _fail("RUNNER_CONFIGURATION_INVALID")
        if type(budget) is not CycleBudget:
            _fail("RUNNER_CONFIGURATION_INVALID")
        _exact_integer(per_host_limit, minimum=1, maximum=4, code="RUNNER_CONFIGURATION_INVALID")
        _exact_integer(
            minimum_start_interval_ns,
            minimum=0,
            maximum=86_400 * _NANOSECONDS_PER_SECOND,
            code="RUNNER_CONFIGURATION_INVALID",
        )
        _exact_integer(
            maximum_attempts_per_item,
            minimum=1,
            maximum=_MAXIMUM_ATTEMPTS,
            code="RUNNER_CONFIGURATION_INVALID",
        )
        _exact_integer(
            maximum_redirects_per_start,
            minimum=0,
            maximum=_MAXIMUM_REDIRECTS_PER_CAPTURE,
            code="RUNNER_CONFIGURATION_INVALID",
        )
        self._journal = journal
        self._items = _deduplicate_items(items, journal.cycle_id)
        self._dependencies = _validate_dependencies(dependencies, self._items)
        if (
            type(preverified_imports) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != _IMPORT_ROW_PARTS
                or type(item[0]) is not str
                or type(item[1]) is not ImportedCaptureVerifiedPayload
                for item in preverified_imports
            )
            or len({item[0] for item in preverified_imports}) != len(preverified_imports)
            or {item[0] for item in preverified_imports}
            - {item.identity.work_item_id for item in self._items}
        ):
            _fail("RUNNER_CONFIGURATION_INVALID")
        self._preverified_imports = dict(preverified_imports)
        self._transport = transport
        self._retained_verifier = retained_verifier
        self._clock = clock
        self._sleeper = sleeper
        self._budget = budget
        self._per_host_limit = per_host_limit
        self._minimum_start_interval_ns = minimum_start_interval_ns
        self._maximum_attempts_per_item = maximum_attempts_per_item
        self._maximum_redirects_per_start = maximum_redirects_per_start
        self._stop_requested = stop_requested or _never_stop
        self._host_start_gates = {
            host: _HostStartGate(threading.Lock()) for host in {item.host for item in self._items}
        }

    def run(self) -> AcquisitionCycleReport:  # noqa: C901, PLR0912, PLR0915
        """Resume verified progress, execute bounded work, and return one canonical report."""
        entries = self._journal.replay()
        _reconcile_journal_work(entries, self._items)
        entries = self._discover_missing(entries)
        entries, profile = self._bind_or_validate_cycle_profile(entries)
        entries = self._seed_preverified_imports(entries)
        stop = _stop_from_entries(entries)
        if not self._retained_objects_verify(entries):
            stop.evidence = True
        if stop.dispatch_stopped:
            checkpoint = self._journal.write_checkpoint()
            return _build_report(entries, checkpoint.items, self._journal.cycle_id, stop)
        entries = self._account_orphan_starts(entries)
        entries = self._account_exhausted_retries(entries)
        checkpoint = self._journal.write_checkpoint()
        pending = self._pending_attempts(checkpoint.items)
        dependency_successes = {
            item.work_item_id
            for item in checkpoint.items
            if item.transition
            in {
                JournalTransition.CAPTURED_VERIFIED,
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
                JournalTransition.ACCOUNTED_EXCLUDED,
            }
        }
        budget_state = _budget_state(entries)
        active_by_host: dict[str, int] = defaultdict(int)
        started_at = self._monotonic_now()
        wall_now_us = _epoch_microseconds(self._wall_now())
        cycle_started_us = profile.cycle_started_at_epoch_us
        if wall_now_us < cycle_started_us:
            _fail("CLOCK_INVALID")
        remaining_elapsed_ns = (
            self._budget.maximum_elapsed_seconds * _NANOSECONDS_PER_SECOND
            - (wall_now_us - cycle_started_us) * _NANOSECONDS_PER_MICROSECOND
        )
        deadline = started_at + max(0, remaining_elapsed_ns)
        if remaining_elapsed_ns <= 0:
            stop.budget = True
            stop.elapsed_budget = True
        next_start_by_host = defaultdict(
            int,
            _replayed_host_not_before(
                entries,
                self._items,
                (wall_now_us, started_at),
                profile,
            ),
        )
        for host, ready in next_start_by_host.items():
            self._host_start_gates[host].next_start_monotonic_ns = ready
        workers = max(1, min(len(pending), max(1, len({item.host for item in self._items}) * 4)))
        in_flight: dict[
            Future[
                _CaptureExecution | _ElapsedExpiredBeforeTransport | _AdmissionFailedBeforeTransport
            ],
            _InFlightAttempt,
        ] = {}
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="acquisition-capture",
        ) as pool:
            while pending or in_flight:
                if not stop.dispatch_stopped and self._stop_requested():
                    stop.clean = True
                dispatched = False
                if not stop.dispatch_stopped:
                    pending.sort(key=_pending_order)
                    for candidate in tuple(pending):
                        if not self._dependencies[
                            candidate.scheduled.identity.work_item_id
                        ].issubset(dependency_successes):
                            continue
                        if active_by_host[candidate.scheduled.host] >= self._per_host_limit:
                            continue
                        now = self._monotonic_now()
                        reserved_start = max(
                            now,
                            candidate.ready_monotonic_ns,
                            next_start_by_host[candidate.scheduled.host],
                        )
                        if reserved_start >= deadline:
                            if not in_flight:
                                stop.budget = True
                                stop.elapsed_budget = True
                            continue
                        if not _can_reserve(
                            budget_state,
                            self._budget,
                            candidate.scheduled.identity.max_bytes,
                            self._maximum_redirects_per_start,
                        ):
                            if not in_flight:
                                stop.budget = True
                            continue
                        admitted_at_us = (
                            _epoch_microseconds(self._wall_now())
                            + (max(0, reserved_start - now) + _NANOSECONDS_PER_MICROSECOND - 1)
                            // _NANOSECONDS_PER_MICROSECOND
                        )
                        host_not_before_epoch_us = (
                            admitted_at_us
                            + (self._minimum_start_interval_ns + _NANOSECONDS_PER_MICROSECOND - 1)
                            // _NANOSECONDS_PER_MICROSECOND
                        )
                        self._journal.append(
                            candidate.scheduled.identity,
                            JournalTransition.STARTED,
                            StartedPayload(
                                attempt=candidate.attempt,
                                started_at_epoch_us=admitted_at_us,
                                host_not_before_epoch_us=host_not_before_epoch_us,
                                reserved_redirects=self._maximum_redirects_per_start,
                            ),
                        )
                        _reserve(
                            budget_state,
                            candidate.scheduled.identity.max_bytes,
                            self._maximum_redirects_per_start,
                        )
                        pending.remove(candidate)
                        active_by_host[candidate.scheduled.host] += 1
                        next_start_by_host[candidate.scheduled.host] = (
                            reserved_start + self._minimum_start_interval_ns
                        )
                        future = pool.submit(
                            self._capture_at,
                            candidate,
                            reserved_start,
                            deadline,
                        )
                        in_flight[future] = _InFlightAttempt(
                            candidate,
                            candidate.scheduled.identity.max_bytes,
                            self._maximum_redirects_per_start,
                            reserved_start,
                            host_not_before_epoch_us,
                        )
                        dispatched = True
                        if self._stop_requested():
                            stop.clean = True
                            break
                if not in_flight:
                    if stop.dispatch_stopped or not pending:
                        break
                    if not dispatched:
                        eligible = tuple(
                            item
                            for item in pending
                            if self._dependencies[item.scheduled.identity.work_item_id].issubset(
                                dependency_successes
                            )
                        )
                        if not eligible:
                            break
                        next_ready = min(
                            max(
                                item.ready_monotonic_ns,
                                next_start_by_host[item.scheduled.host],
                            )
                            for item in eligible
                        )
                        if next_ready >= deadline:
                            stop.budget = True
                            stop.elapsed_budget = True
                            continue
                        self._sleep_until(next_ready)
                    continue
                completed, _ = wait(tuple(in_flight), return_when=FIRST_COMPLETED)
                for future in completed:
                    flight = in_flight.pop(future)
                    active_by_host[flight.pending.scheduled.host] -= 1
                    try:
                        execution = future.result()
                    except Exception:  # noqa: BLE001 - unobserved worker faults stay interrupted.
                        _cancel_reservation(budget_state, flight)
                        self._record_pretransport_interruption(
                            flight.pending.scheduled.identity,
                            flight.pending.attempt,
                        )
                        stop.clean = True
                        continue
                    if isinstance(execution, _ElapsedExpiredBeforeTransport):
                        _cancel_reservation(budget_state, flight)
                        stop.budget = True
                        stop.elapsed_budget = True
                        continue
                    if isinstance(execution, _AdmissionFailedBeforeTransport):
                        _cancel_reservation(budget_state, flight)
                        self._record_admission_failure(
                            flight.pending.scheduled.identity,
                            flight.pending.attempt,
                            flight.host_not_before_epoch_us,
                        )
                        stop.clean = True
                        continue
                    _release_reservation(budget_state, flight)
                    self._journal.append(
                        flight.pending.scheduled.identity,
                        JournalTransition.TRANSPORT_STARTED,
                        TransportStartedPayload(
                            attempt=flight.pending.attempt,
                            started_at_epoch_us=execution.started_at_epoch_us,
                            host_not_before_epoch_us=execution.started_at_epoch_us
                            + (self._minimum_start_interval_ns + _NANOSECONDS_PER_MICROSECOND - 1)
                            // _NANOSECONDS_PER_MICROSECOND,
                        ),
                    )
                    if isinstance(execution.failure, CaptureAuthorizationFailure):
                        self._journal.append(
                            flight.pending.scheduled.identity,
                            JournalTransition.AUTHORIZATION_REJECTED,
                            AuthorizationRejectedPayload(flight.pending.attempt),
                        )
                        stop.authorization = True
                        continue
                    if execution.failure is not None:
                        self._record_evidence_failure(
                            flight.pending.scheduled.identity,
                            flight.pending.attempt,
                        )
                        stop.evidence = True
                        continue
                    try:
                        outcome = _rebuild_capture_outcome(execution.outcome)
                    except Exception:  # noqa: BLE001 - untyped transport failures cannot be guessed.
                        self._record_evidence_failure(
                            flight.pending.scheduled.identity,
                            flight.pending.attempt,
                        )
                        stop.evidence = True
                        continue
                    action = self._accept_outcome(flight.pending, outcome, budget_state)
                    if action == "CAPTURED":
                        dependency_successes.add(flight.pending.scheduled.identity.work_item_id)
                    elif action == "RETRY":
                        pending.append(self._retry_attempt(flight.pending, outcome))
                    elif action == "CONTRACT":
                        stop.contract = True
                    elif action == "EVIDENCE":
                        stop.evidence = True
                if self._monotonic_now() >= deadline:
                    stop.budget = True
                    stop.elapsed_budget = True
        if stop.elapsed_budget:
            self._journal.append(
                self._items[0].identity,
                JournalTransition.ELAPSED_BUDGET_EXHAUSTED,
                ElapsedBudgetExhaustedPayload(self._budget.maximum_elapsed_seconds),
            )
        checkpoint = self._journal.write_checkpoint()
        return _build_report(
            self._journal.replay(),
            checkpoint.items,
            self._journal.cycle_id,
            stop,
        )

    def _bind_or_validate_cycle_profile(
        self,
        entries: tuple[AcquisitionJournalEntry, ...],
    ) -> tuple[tuple[AcquisitionJournalEntry, ...], CycleSafetyProfilePayload]:
        profiles = tuple(
            entry.payload
            for entry in entries
            if entry.transition is JournalTransition.CYCLE_SAFETY_PROFILE_BOUND
            and type(entry.payload) is CycleSafetyProfilePayload
        )
        if len(profiles) > 1:
            _fail("JOURNAL_STATE_INVALID")
        if profiles:
            profile = profiles[0]
            if _profile_control_facts(profile) != self._configured_control_facts():
                _fail("CYCLE_SAFETY_PROFILE_DRIFT")
            return entries, profile
        if not entries:
            _fail("JOURNAL_STATE_INVALID")
        cycle_starts = {
            entry.payload.cycle_started_at_epoch_us
            for entry in entries
            if entry.transition is JournalTransition.DISCOVERED
            and type(entry.payload) is DiscoveredPayload
        }
        if len(cycle_starts) != 1:
            _fail("JOURNAL_STATE_INVALID")
        wall_now_us = _epoch_microseconds(self._wall_now())
        cycle_started_at_epoch_us = next(iter(cycle_starts))
        if wall_now_us < cycle_started_at_epoch_us:
            _fail("CLOCK_INVALID")
        profile = CycleSafetyProfilePayload(
            schema_id=_CYCLE_PROFILE_SCHEMA_ID,
            schema_version=_SCHEMA_VERSION,
            maximum_starts=self._budget.maximum_starts,
            maximum_retained_bytes=self._budget.maximum_retained_bytes,
            maximum_elapsed_seconds=self._budget.maximum_elapsed_seconds,
            maximum_redirects=self._budget.maximum_redirects,
            per_host_limit=self._per_host_limit,
            minimum_start_interval_ns=self._minimum_start_interval_ns,
            maximum_attempts_per_item=self._maximum_attempts_per_item,
            maximum_redirects_per_start=self._maximum_redirects_per_start,
            cycle_started_at_epoch_us=cycle_started_at_epoch_us,
        )
        self._journal.append(
            entries[0].work_item,
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            profile,
        )
        return self._journal.replay(), profile

    def _configured_control_facts(self) -> tuple[int, ...]:
        return (
            self._budget.maximum_starts,
            self._budget.maximum_retained_bytes,
            self._budget.maximum_elapsed_seconds,
            self._budget.maximum_redirects,
            self._per_host_limit,
            self._minimum_start_interval_ns,
            self._maximum_attempts_per_item,
            self._maximum_redirects_per_start,
        )

    def _seed_preverified_imports(
        self,
        entries: tuple[AcquisitionJournalEntry, ...],
    ) -> tuple[AcquisitionJournalEntry, ...]:
        """Append exact verified import facts before transport eligibility is computed."""
        latest = _latest_entries(entries)
        by_id = {item.identity.work_item_id: item.identity for item in self._items}
        for work_item_id, payload in self._preverified_imports.items():
            current = latest[work_item_id]
            if current.transition is JournalTransition.IMPORTED_CAPTURE_VERIFIED:
                if current.payload != payload:
                    _fail("JOURNAL_STATE_INVALID")
                continue
            if current.transition is not JournalTransition.DISCOVERED:
                _fail("JOURNAL_STATE_INVALID")
            self._journal.append(
                by_id[work_item_id],
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
                payload,
            )
        return self._journal.replay()

    def _discover_missing(
        self,
        entries: tuple[AcquisitionJournalEntry, ...],
    ) -> tuple[AcquisitionJournalEntry, ...]:
        known = {entry.work_item.work_item_id for entry in entries}
        starts = {
            entry.payload.cycle_started_at_epoch_us
            for entry in entries
            if entry.transition is JournalTransition.DISCOVERED
            and type(entry.payload) is DiscoveredPayload
        }
        if len(starts) > 1:
            _fail("JOURNAL_STATE_INVALID")
        selected_cycle_start = (
            next(iter(starts)) if starts else _epoch_microseconds(self._wall_now())
        )
        for item in self._items:
            if item.identity.work_item_id not in known:
                self._journal.append(
                    item.identity,
                    JournalTransition.DISCOVERED,
                    DiscoveredPayload(selected_cycle_start),
                )
        return self._journal.replay()

    def _retained_objects_verify(self, entries: tuple[AcquisitionJournalEntry, ...]) -> bool:
        by_id = {item.identity.work_item_id: item.identity for item in self._items}
        for entry in entries:
            if entry.transition not in {
                JournalTransition.CAPTURED_VERIFIED,
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
            }:
                continue
            payload = entry.payload
            if not isinstance(
                payload,
                (CapturedVerifiedPayload, ImportedCaptureVerifiedPayload),
            ) or type(payload) not in {
                CapturedVerifiedPayload,
                ImportedCaptureVerifiedPayload,
            }:
                return False
            try:
                verified = self._retained_verifier.verify(
                    by_id[entry.work_item.work_item_id],
                    payload.object_ref,
                    payload.content_fingerprint,
                    payload.body_length,
                )
            except Exception:  # noqa: BLE001 - hostile read-back adapters fail integrity closed.
                return False
            if verified is not True:
                return False
        return True

    def _account_orphan_starts(
        self, entries: tuple[AcquisitionJournalEntry, ...]
    ) -> tuple[AcquisitionJournalEntry, ...]:
        latest = _latest_entries(entries)
        interval_us = (
            self._minimum_start_interval_ns + _NANOSECONDS_PER_MICROSECOND - 1
        ) // _NANOSECONDS_PER_MICROSECOND
        recovery_floor_epoch_us = _epoch_microseconds(self._wall_now()) + interval_us
        by_id = {item.identity.work_item_id: item for item in self._items}
        for work_item_id in sorted(
            (key for key, entry in latest.items() if entry.transition is JournalTransition.STARTED),
            key=lambda key: _scheduled_order(by_id[key]),
        ):
            entry = latest[work_item_id]
            payload = entry.payload
            if type(payload) is not StartedPayload:
                _fail("JOURNAL_STATE_INVALID")
            retry_floor_epoch_us = max(
                recovery_floor_epoch_us,
                payload.host_not_before_epoch_us or 0,
            )
            try:
                retry_not_before = _canonical_timestamp(
                    _UNIX_EPOCH + timedelta(microseconds=retry_floor_epoch_us)
                )
            except OverflowError as error:
                code = "JOURNAL_STATE_INVALID"
                raise ResumableAcquisitionError(code) from error
            self._journal.append(
                entry.work_item,
                JournalTransition.RETRYABLE_FAILURE,
                RetryableFailurePayload(
                    attempt=payload.attempt,
                    failure_code=AcquisitionFailureCode.WORKER_INTERRUPTED,
                    retry_not_before=retry_not_before,
                ),
            )
        return self._journal.replay()

    def _account_exhausted_retries(
        self, entries: tuple[AcquisitionJournalEntry, ...]
    ) -> tuple[AcquisitionJournalEntry, ...]:
        latest = _latest_entries(entries)
        by_id = {item.identity.work_item_id: item for item in self._items}
        for work_item_id in sorted(
            (
                key
                for key, entry in latest.items()
                if (
                    entry.transition is JournalTransition.RETRYABLE_FAILURE
                    and type(entry.payload) is RetryableFailurePayload
                    and entry.payload.attempt >= self._maximum_attempts_per_item
                )
                or (
                    entry.transition is JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT
                    and type(entry.payload) is AdmissionFailedBeforeTransportPayload
                    and entry.payload.attempt >= self._maximum_attempts_per_item
                )
            ),
            key=lambda key: _scheduled_order(by_id[key]),
        ):
            entry = latest[work_item_id]
            payload = entry.payload
            if (
                isinstance(payload, RetryableFailurePayload)
                and type(payload) is RetryableFailurePayload
            ) or (
                isinstance(payload, AdmissionFailedBeforeTransportPayload)
                and type(payload) is AdmissionFailedBeforeTransportPayload
            ):
                exhausted_attempt = payload.attempt
            else:
                _fail("JOURNAL_STATE_INVALID")
            self._journal.append(
                entry.work_item,
                JournalTransition.RETRY_EXHAUSTED,
                RetryExhaustedPayload(exhausted_attempt),
            )
        return self._journal.replay()

    def _pending_attempts(self, checkpoint: tuple[CheckpointItem, ...]) -> list[_PendingAttempt]:
        if type(checkpoint) is not tuple:
            _fail("JOURNAL_STATE_INVALID")
        states = {item.work_item_id: item for item in checkpoint if _is_checkpoint_item(item)}
        pending: list[_PendingAttempt] = []
        now_monotonic = self._monotonic_now()
        now_wall = self._wall_now()
        for scheduled in self._items:
            state = states.get(scheduled.identity.work_item_id)
            if state is None:
                _fail("JOURNAL_STATE_INVALID")
            if state.transition in {
                JournalTransition.CAPTURED_VERIFIED,
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
                JournalTransition.ACCOUNTED_EXCLUDED,
                JournalTransition.CONTRACT_REJECTED,
                JournalTransition.AUTHORIZATION_REJECTED,
                JournalTransition.RETRY_EXHAUSTED,
                JournalTransition.TERMINAL_UNAVAILABLE,
            }:
                continue
            if state.transition is JournalTransition.DISCOVERED:
                pending.append(
                    _PendingAttempt(
                        scheduled,
                        1,
                        max(scheduled.not_before_monotonic_ns, now_monotonic),
                    )
                )
                continue
            if state.transition not in {
                JournalTransition.RETRYABLE_FAILURE,
                JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
            }:
                _fail("JOURNAL_STATE_INVALID")
            if state.attempt_count >= self._maximum_attempts_per_item:
                continue
            retry_wall = _parse_timestamp(state.retry_not_before)
            retry_delay_ns = max(
                0,
                round((retry_wall - now_wall).total_seconds() * _NANOSECONDS_PER_SECOND),
            )
            pending.append(
                _PendingAttempt(
                    scheduled,
                    state.attempt_count + 1,
                    max(
                        scheduled.not_before_monotonic_ns,
                        now_monotonic + retry_delay_ns,
                    ),
                )
            )
        return pending

    def _capture_at(
        self,
        pending: _PendingAttempt,
        reserved_start_monotonic_ns: int,
        cycle_deadline_monotonic_ns: int,
    ) -> _CaptureExecution | _ElapsedExpiredBeforeTransport | _AdmissionFailedBeforeTransport:
        try:
            gate = self._host_start_gates[pending.scheduled.host]
            with gate.lock:
                self._sleep_until(max(reserved_start_monotonic_ns, gate.next_start_monotonic_ns))
                actual_start = self._monotonic_now()
                if actual_start >= cycle_deadline_monotonic_ns:
                    return _ElapsedExpiredBeforeTransport()
                gate.next_start_monotonic_ns = actual_start + self._minimum_start_interval_ns
            actual_start_epoch_us = _epoch_microseconds(self._wall_now())
            if self._monotonic_now() >= cycle_deadline_monotonic_ns:
                return _ElapsedExpiredBeforeTransport()
        except Exception:  # noqa: BLE001 - coordinator records a typed pre-transport interruption.
            return _AdmissionFailedBeforeTransport()
        try:
            outcome = self._transport.capture(pending.scheduled.identity)
        except Exception as error:  # noqa: BLE001 - the coordinator classifies the exact signal.
            return _CaptureExecution(actual_start_epoch_us, None, error)
        return _CaptureExecution(actual_start_epoch_us, outcome, None)

    def _accept_outcome(  # noqa: C901, PLR0911, PLR0912 - closed transition interpreter.
        self,
        pending: _PendingAttempt,
        outcome: CaptureOutcome,
        budget: _BudgetState,
    ) -> str:
        scheduled = pending.scheduled
        item = scheduled.identity
        if type(outcome) is not CaptureOutcome:
            return "EVIDENCE"
        if outcome.work_item_id != item.work_item_id:
            return self._record_evidence_failure(item, pending.attempt)
        if outcome.transition is JournalTransition.CAPTURED_VERIFIED:
            try:
                payload = CapturedVerifiedPayload(
                    attempt=pending.attempt,
                    status=_required(outcome.status_code),
                    media_type=_required(outcome.media_type),
                    final_url=_required(outcome.final_url),
                    redirect_chain=outcome.redirect_chain,
                    body_length=outcome.body_length,
                    content_fingerprint=_required(outcome.body_fingerprint),
                    object_ref=_required(outcome.object_ref),
                    read_back_verified=outcome.read_back_verified,
                )
                if (
                    outcome.failure_code is not None
                    or outcome.retry_not_before is not None
                    or payload.media_type != item.media_type
                    or payload.body_length > item.max_bytes
                    or len(payload.redirect_chain) > self._maximum_redirects_per_start
                    or not _locator_is_admitted(payload.final_url, scheduled.host)
                    or any(
                        not _locator_is_admitted(locator, scheduled.host)
                        for locator in payload.redirect_chain
                    )
                ):
                    return self._record_evidence_failure(item, pending.attempt)
                verified = self._retained_verifier.verify(
                    item,
                    payload.object_ref,
                    payload.content_fingerprint,
                    payload.body_length,
                )
                if verified is not True:
                    return self._record_evidence_failure(item, pending.attempt)
                self._journal.append(item, JournalTransition.CAPTURED_VERIFIED, payload)
            except Exception:  # noqa: BLE001 - outcome/read-back adapters fail integrity closed.
                return self._record_evidence_failure(item, pending.attempt)
            budget.retained_bytes += payload.body_length
            return "CAPTURED"
        if not _empty_evidence_facts(outcome):
            return self._record_evidence_failure(item, pending.attempt)
        try:
            failure = AcquisitionFailureCode(_required(outcome.failure_code))
        except ResumableAcquisitionError, TypeError, ValueError:
            return self._record_evidence_failure(item, pending.attempt)
        if outcome.transition is JournalTransition.RETRYABLE_FAILURE:
            try:
                payload = RetryableFailurePayload(
                    pending.attempt,
                    failure,
                    _required(outcome.retry_not_before),
                )
                self._journal.append(item, JournalTransition.RETRYABLE_FAILURE, payload)
            except ResumableAcquisitionError, TypeError, ValueError:
                return self._record_evidence_failure(item, pending.attempt)
            if pending.attempt < self._maximum_attempts_per_item:
                return "RETRY"
            self._journal.append(
                item,
                JournalTransition.RETRY_EXHAUSTED,
                RetryExhaustedPayload(pending.attempt),
            )
            return "EXHAUSTED"
        if outcome.retry_not_before is not None:
            return self._record_evidence_failure(item, pending.attempt)
        if outcome.transition is JournalTransition.CONTRACT_REJECTED:
            try:
                self._journal.append(
                    item,
                    JournalTransition.CONTRACT_REJECTED,
                    ContractRejectedPayload(pending.attempt, failure),
                )
            except ResumableAcquisitionError, TypeError, ValueError:
                return self._record_evidence_failure(item, pending.attempt)
            return "CONTRACT"
        if outcome.transition is JournalTransition.TERMINAL_UNAVAILABLE:
            try:
                self._journal.append(
                    item,
                    JournalTransition.TERMINAL_UNAVAILABLE,
                    TerminalUnavailablePayload(pending.attempt, failure),
                )
            except ResumableAcquisitionError, TypeError, ValueError:
                return self._record_evidence_failure(item, pending.attempt)
            return "INCOMPLETE"
        return self._record_evidence_failure(item, pending.attempt)

    def _record_evidence_failure(self, item: WorkItemIdentity, attempt: int) -> str:
        """Close one started attempt without inventing successful capture facts."""
        self._journal.append(
            item,
            JournalTransition.TERMINAL_UNAVAILABLE,
            TerminalUnavailablePayload(
                attempt=attempt,
                failure_code=AcquisitionFailureCode.EVIDENCE_INTEGRITY_FAILURE,
            ),
        )
        return "EVIDENCE"

    def _record_pretransport_interruption(
        self,
        item: WorkItemIdentity,
        attempt: int,
    ) -> None:
        retry_not_before = _canonical_timestamp(
            self._wall_now()
            + timedelta(
                microseconds=(self._minimum_start_interval_ns + _NANOSECONDS_PER_MICROSECOND - 1)
                // _NANOSECONDS_PER_MICROSECOND
            )
        )
        self._journal.append(
            item,
            JournalTransition.RETRYABLE_FAILURE,
            RetryableFailurePayload(
                attempt=attempt,
                failure_code=AcquisitionFailureCode.WORKER_INTERRUPTED,
                retry_not_before=retry_not_before,
            ),
        )

    def _record_admission_failure(
        self,
        item: WorkItemIdentity,
        attempt: int,
        host_not_before_epoch_us: int,
    ) -> None:
        """Persist a proved no-call disposition at the originating host retry floor."""
        retry_not_before = _canonical_timestamp(
            _UNIX_EPOCH + timedelta(microseconds=host_not_before_epoch_us)
        )
        self._journal.append(
            item,
            JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
            AdmissionFailedBeforeTransportPayload(
                attempt=attempt,
                retry_not_before=retry_not_before,
            ),
        )
        if attempt >= self._maximum_attempts_per_item:
            self._journal.append(
                item,
                JournalTransition.RETRY_EXHAUSTED,
                RetryExhaustedPayload(attempt),
            )

    def _retry_attempt(self, pending: _PendingAttempt, outcome: CaptureOutcome) -> _PendingAttempt:
        now_monotonic = self._monotonic_now()
        retry_wall = _parse_timestamp(outcome.retry_not_before)
        retry_delay_ns = max(
            0,
            round((retry_wall - self._wall_now()).total_seconds() * _NANOSECONDS_PER_SECOND),
        )
        return _PendingAttempt(
            pending.scheduled,
            pending.attempt + 1,
            max(pending.scheduled.not_before_monotonic_ns, now_monotonic + retry_delay_ns),
        )

    def _monotonic_now(self) -> int:
        value = self._clock.monotonic_ns()
        return _exact_integer(
            value,
            minimum=0,
            maximum=9_223_372_036_854_775_807,
            code="CLOCK_INVALID",
        )

    def _wall_now(self) -> datetime:
        value = self._clock.now()
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            _fail("CLOCK_INVALID")
        return value

    def _sleep_until(self, ready_ns: int) -> None:
        while True:
            remaining = ready_ns - self._monotonic_now()
            if remaining <= 0:
                return
            self._sleeper(remaining / _NANOSECONDS_PER_SECOND)


def _never_stop() -> bool:
    return False


def _rebuild_capture_outcome(value: object) -> CaptureOutcome:
    if type(value) is not CaptureOutcome:
        _fail("CAPTURE_OUTCOME_INVALID")
    return CaptureOutcome(
        work_item_id=value.work_item_id,
        transition=value.transition,
        status_code=value.status_code,
        media_type=value.media_type,
        final_url=value.final_url,
        body_length=value.body_length,
        body_fingerprint=value.body_fingerprint,
        object_ref=value.object_ref,
        failure_code=value.failure_code,
        retry_not_before=value.retry_not_before,
        read_back_verified=value.read_back_verified,
        redirect_chain=value.redirect_chain,
    )


def _required[T](value: T | None) -> T:
    if value is None:
        _fail("CAPTURE_OUTCOME_INVALID")
    return value


def _empty_evidence_facts(outcome: CaptureOutcome) -> bool:
    return (
        outcome.status_code is None
        and outcome.media_type is None
        and outcome.final_url is None
        and outcome.body_length == 0
        and outcome.body_fingerprint is None
        and outcome.object_ref is None
        and outcome.read_back_verified is False
        and not outcome.redirect_chain
    )


def _canonical_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _epoch_microseconds(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    delta = normalized - _UNIX_EPOCH
    result = (
        delta.days * 86_400 * _MICROSECONDS_PER_SECOND
        + delta.seconds * _MICROSECONDS_PER_SECOND
        + delta.microseconds
    )
    return _exact_integer(
        result,
        minimum=0,
        maximum=9_007_199_254_740_991,
        code="CLOCK_INVALID",
    )


def _parse_timestamp(value: object) -> datetime:
    text = _exact_text(value, maximum=40, code="RETRY_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        code = "RETRY_TIME_INVALID"
        raise ResumableAcquisitionError(code) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("RETRY_TIME_INVALID")
    return parsed


def _scheduled_order(item: ScheduledWorkItem) -> tuple[tuple[int, int, str], str]:
    return item.priority, item.identity.work_item_id


def _pending_order(item: _PendingAttempt) -> tuple[tuple[int, int, str], str, int]:
    return item.scheduled.priority, item.scheduled.identity.work_item_id, item.attempt


def _locator_is_admitted(locator: str, host: str) -> bool:
    try:
        parsed = urlsplit(locator)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == host
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
    )


def _deduplicate_items(
    items: tuple[ScheduledWorkItem, ...], cycle_id: str
) -> tuple[ScheduledWorkItem, ...]:
    unique: dict[str, ScheduledWorkItem] = {}
    for item in items:
        if type(item) is not ScheduledWorkItem:
            _fail("WORK_ITEM_INVALID")
        ScheduledWorkItem(
            identity=item.identity,
            priority=item.priority,
            host=item.host,
            not_before_monotonic_ns=item.not_before_monotonic_ns,
        )
        if item.identity.cycle_id != cycle_id:
            _fail("WORK_ITEM_INVALID")
        prior = unique.get(item.identity.work_item_id)
        if prior is not None and prior != item:
            _fail("WORK_ITEM_FACT_DRIFT")
        unique[item.identity.work_item_id] = item
    return tuple(sorted(unique.values(), key=_scheduled_order))


def _validate_dependencies(  # noqa: C901 - validates one closed graph including cycles.
    supplied: tuple[tuple[str, tuple[str, ...]], ...],
    items: tuple[ScheduledWorkItem, ...],
) -> dict[str, frozenset[str]]:
    """Return one closed acyclic prerequisite map for the exact runner membership."""
    work_ids = tuple(item.identity.work_item_id for item in items)
    if supplied == ():
        return {work_id: frozenset() for work_id in work_ids}
    if type(supplied) is not tuple:
        _fail("WORK_DEPENDENCY_INVALID")
    projected: dict[str, frozenset[str]] = {}
    for row in supplied:
        if (
            type(row) is not tuple
            or len(row) != _DEPENDENCY_ROW_PARTS
            or type(row[0]) is not str
            or type(row[1]) is not tuple
            or any(type(dependency) is not str for dependency in row[1])
            or tuple(sorted(set(row[1]))) != row[1]
            or row[0] in row[1]
            or row[0] in projected
        ):
            _fail("WORK_DEPENDENCY_INVALID")
        projected[row[0]] = frozenset(row[1])
    if set(projected) != set(work_ids) or any(
        not dependencies.issubset(projected) for dependencies in projected.values()
    ):
        _fail("WORK_DEPENDENCY_INVALID")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(work_id: str) -> None:
        if work_id in visiting:
            _fail("WORK_DEPENDENCY_INVALID")
        if work_id in visited:
            return
        visiting.add(work_id)
        for dependency in projected[work_id]:
            visit(dependency)
        visiting.remove(work_id)
        visited.add(work_id)

    for work_id in work_ids:
        visit(work_id)
    return projected


def _reconcile_journal_work(
    entries: tuple[AcquisitionJournalEntry, ...], items: tuple[ScheduledWorkItem, ...]
) -> None:
    expected = {item.identity.work_item_id: item.identity for item in items}
    retained: dict[str, WorkItemIdentity] = {}
    for entry in entries:
        prior = retained.setdefault(entry.work_item.work_item_id, entry.work_item)
        if prior != entry.work_item:
            _fail("WORK_ITEM_FACT_DRIFT")
    if not set(retained).issubset(expected):
        _fail("WORK_ITEM_FACT_DRIFT")
    if any(expected[key] != identity for key, identity in retained.items()):
        _fail("WORK_ITEM_FACT_DRIFT")


def _profile_control_facts(profile: CycleSafetyProfilePayload) -> tuple[int, ...]:
    return (
        profile.maximum_starts,
        profile.maximum_retained_bytes,
        profile.maximum_elapsed_seconds,
        profile.maximum_redirects,
        profile.per_host_limit,
        profile.minimum_start_interval_ns,
        profile.maximum_attempts_per_item,
        profile.maximum_redirects_per_start,
    )


def _latest_entries(
    entries: tuple[AcquisitionJournalEntry, ...],
) -> dict[str, AcquisitionJournalEntry]:
    latest: dict[str, AcquisitionJournalEntry] = {}
    for entry in entries:
        if entry.transition in {
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            JournalTransition.TRANSPORT_STARTED,
            JournalTransition.ELAPSED_BUDGET_EXHAUSTED,
        }:
            continue
        latest[entry.work_item.work_item_id] = entry
    return latest


def _replayed_host_not_before(
    entries: tuple[AcquisitionJournalEntry, ...],
    items: tuple[ScheduledWorkItem, ...],
    now: tuple[int, int],
    profile: CycleSafetyProfilePayload,
) -> dict[str, int]:
    by_id = {item.identity.work_item_id: item.host for item in items}
    wall_now_us, monotonic_now_ns = now
    durable_by_host = _durable_host_deadlines(
        entries,
        profile,
        by_id,
    )
    return {
        host: monotonic_now_ns + max(0, ready_us - wall_now_us) * _NANOSECONDS_PER_MICROSECOND
        for host, ready_us in durable_by_host.items()
    }


def _durable_host_deadlines(
    entries: tuple[AcquisitionJournalEntry, ...],
    profile: CycleSafetyProfilePayload,
    by_id: dict[str, str],
) -> dict[str, int]:
    durable_by_host: dict[str, int] = defaultdict(int)
    current_interval_us = (
        profile.minimum_start_interval_ns + _NANOSECONDS_PER_MICROSECOND - 1
    ) // _NANOSECONDS_PER_MICROSECOND
    for entry in entries:
        host = by_id[entry.work_item.work_item_id]
        for deadline in (
            _physical_host_deadline(entry, current_interval_us),
            _recovery_host_deadline(entry),
        ):
            if deadline is not None:
                durable_by_host[host] = max(
                    durable_by_host[host],
                    deadline,
                )
    return durable_by_host


def _physical_host_deadline(
    entry: AcquisitionJournalEntry,
    current_interval_us: int,
) -> int | None:
    if entry.transition is JournalTransition.TRANSPORT_STARTED:
        payload = entry.payload
        if type(payload) is not TransportStartedPayload:
            _fail("JOURNAL_STATE_INVALID")
        return max(
            payload.host_not_before_epoch_us,
            payload.started_at_epoch_us + current_interval_us,
        )
    return None


def _recovery_host_deadline(entry: AcquisitionJournalEntry) -> int | None:
    payload = entry.payload
    if entry.transition is JournalTransition.RETRYABLE_FAILURE:
        if (
            type(payload) is RetryableFailurePayload
            and payload.failure_code is AcquisitionFailureCode.WORKER_INTERRUPTED
        ):
            return _epoch_microseconds(_parse_timestamp(payload.retry_not_before))
        return None
    if entry.transition is JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT:
        if type(payload) is not AdmissionFailedBeforeTransportPayload:
            _fail("JOURNAL_STATE_INVALID")
        return _epoch_microseconds(_parse_timestamp(payload.retry_not_before))
    return None


def _stop_from_entries(entries: tuple[AcquisitionJournalEntry, ...]) -> _RunStop:
    stop = _RunStop()
    transitions = {entry.transition for entry in entries}
    stop.contract = JournalTransition.CONTRACT_REJECTED in transitions
    stop.authorization = JournalTransition.AUTHORIZATION_REJECTED in transitions
    stop.budget = JournalTransition.ELAPSED_BUDGET_EXHAUSTED in transitions
    stop.elapsed_budget = stop.budget
    stop.evidence = any(
        entry.transition is JournalTransition.TERMINAL_UNAVAILABLE
        and type(entry.payload) is TerminalUnavailablePayload
        and entry.payload.failure_code is AcquisitionFailureCode.EVIDENCE_INTEGRITY_FAILURE
        for entry in entries
    )
    return stop


def _is_checkpoint_item(value: object) -> TypeIs[CheckpointItem]:
    return type(value) is CheckpointItem


def _can_reserve(
    state: _BudgetState,
    budget: CycleBudget,
    retained_bytes: int,
    redirects: int,
) -> bool:
    return (
        state.starts + state.reserved_starts + 1 <= budget.maximum_starts
        and state.retained_bytes + state.reserved_retained_bytes + retained_bytes
        <= budget.maximum_retained_bytes
        and state.redirects + state.reserved_redirects + redirects <= budget.maximum_redirects
    )


def _reserve(state: _BudgetState, retained_bytes: int, redirects: int) -> None:
    state.reserved_starts += 1
    state.reserved_retained_bytes += retained_bytes
    state.reserved_redirects += redirects


def _release_reservation(state: _BudgetState, flight: _InFlightAttempt) -> None:
    state.reserved_starts -= 1
    state.reserved_retained_bytes -= flight.reserved_retained_bytes
    state.reserved_redirects -= flight.reserved_redirects
    state.starts += 1
    state.redirects += flight.reserved_redirects


def _cancel_reservation(state: _BudgetState, flight: _InFlightAttempt) -> None:
    state.reserved_starts -= 1
    state.reserved_retained_bytes -= flight.reserved_retained_bytes
    state.reserved_redirects -= flight.reserved_redirects


def _budget_state(entries: tuple[AcquisitionJournalEntry, ...]) -> _BudgetState:
    physical_attempts = {
        (entry.work_item.work_item_id, entry.payload.attempt)
        for entry in entries
        if entry.transition is JournalTransition.TRANSPORT_STARTED
        and type(entry.payload) is TransportStartedPayload
    }
    closed_attempts: set[tuple[str, int]] = set()
    for entry in entries:
        if entry.transition not in {
            JournalTransition.CAPTURED_VERIFIED,
            JournalTransition.RETRYABLE_FAILURE,
            JournalTransition.CONTRACT_REJECTED,
            JournalTransition.AUTHORIZATION_REJECTED,
            JournalTransition.TERMINAL_UNAVAILABLE,
        }:
            continue
        payload = entry.payload
        if not isinstance(
            payload,
            (
                CapturedVerifiedPayload,
                RetryableFailurePayload,
                ContractRejectedPayload,
                AuthorizationRejectedPayload,
                TerminalUnavailablePayload,
            ),
        ):
            _fail("JOURNAL_STATE_INVALID")
        closed_attempts.add((entry.work_item.work_item_id, payload.attempt))
    starts = 0
    retained = 0
    redirects = 0
    for entry in entries:
        if entry.transition is JournalTransition.STARTED:
            payload = entry.payload
            if type(payload) is not StartedPayload:
                _fail("JOURNAL_STATE_INVALID")
            attempt = (entry.work_item.work_item_id, payload.attempt)
            if attempt in physical_attempts or attempt in closed_attempts:
                starts += 1
                redirects += payload.reserved_redirects
        elif entry.transition is JournalTransition.CAPTURED_VERIFIED:
            payload = entry.payload
            if type(payload) is not CapturedVerifiedPayload:
                _fail("JOURNAL_STATE_INVALID")
            retained += payload.body_length
    return _BudgetState(starts, retained, redirects)


def _semantic_journal_head(entries: tuple[AcquisitionJournalEntry, ...]) -> str:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for entry in entries:
        grouped[entry.work_item.work_item_id].append(
            {
                "work_item": entry.work_item.to_json(),
                "transition": entry.transition.value,
                "payload": _semantic_payload(entry),
            }
        )
    return _fingerprint(
        {
            "projection": "asklegal.canonical-acquisition-journal-head/1.0.0",
            "items": [
                {"work_item_id": work_item_id, "entries": grouped[work_item_id]}
                for work_item_id in sorted(grouped)
            ],
        }
    )


def semantic_journal_head(entries: tuple[AcquisitionJournalEntry, ...]) -> str:
    """Return the manifest-bound deterministic projection of replayed entries."""
    if type(entries) is not tuple or any(
        type(item) is not AcquisitionJournalEntry for item in entries
    ):
        _fail("JOURNAL_STATE_INVALID")
    return _semantic_journal_head(entries)


def _semantic_payload(entry: AcquisitionJournalEntry) -> dict[str, JsonValue]:
    payload = entry.payload.to_json()
    if entry.transition is JournalTransition.DISCOVERED:
        payload.pop("cycle_started_at_epoch_us", None)
    elif entry.transition in {
        JournalTransition.STARTED,
        JournalTransition.TRANSPORT_STARTED,
    }:
        payload.pop("started_at_epoch_us", None)
        payload.pop("host_not_before_epoch_us", None)
    elif entry.transition is JournalTransition.CYCLE_SAFETY_PROFILE_BOUND:
        payload.pop("cycle_started_at_epoch_us", None)
    return payload


def _issue_report(
    report: AcquisitionCycleReport,
    entries: tuple[AcquisitionJournalEntry, ...],
) -> AcquisitionCycleReport:
    """Bind one live report to the exact verified payloads in its journal replay."""
    bindings: list[VerifiedCaptureBinding] = []
    seen: set[str] = set()
    for entry in entries:
        if entry.transition not in {
            JournalTransition.CAPTURED_VERIFIED,
            JournalTransition.IMPORTED_CAPTURE_VERIFIED,
        }:
            continue
        payload = entry.payload
        if type(payload) is CapturedVerifiedPayload:
            object_ref = payload.object_ref
            content_fingerprint = payload.content_fingerprint
            body_length = payload.body_length
            final_url = payload.final_url
            redirect_chain = payload.redirect_chain
        elif type(payload) is ImportedCaptureVerifiedPayload:
            object_ref = payload.object_ref
            content_fingerprint = payload.content_fingerprint
            body_length = payload.body_length
            final_url = payload.final_url
            redirect_chain = ()
        else:
            _fail("JOURNAL_STATE_INVALID")
        work_item_id = entry.work_item.work_item_id
        if work_item_id in seen:
            _fail("JOURNAL_STATE_INVALID")
        seen.add(work_item_id)
        bindings.append(
            VerifiedCaptureBinding(
                work_item_id,
                object_ref,
                content_fingerprint,
                body_length,
                final_url,
                redirect_chain,
            )
        )
    identity = id(report)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        issued = _REPORT_ISSUANCE.get(identity)
        if issued is not None and issued.reference is reference:
            del _REPORT_ISSUANCE[identity]

    _REPORT_ISSUANCE[identity] = _ReportIssuance(
        weakref.ref(report, cleanup),
        report.fingerprint,
        tuple(sorted(bindings, key=lambda item: item.work_item_id)),
    )
    return report


def _build_report(
    entries: tuple[AcquisitionJournalEntry, ...],
    dispositions: tuple[CheckpointItem, ...],
    cycle_id: str,
    stop: _RunStop,
) -> AcquisitionCycleReport:
    budget = _budget_state(entries)
    transitions = {item.transition for item in dispositions}
    retained_integrity_failure = any(
        entry.transition is JournalTransition.TERMINAL_UNAVAILABLE
        and type(entry.payload) is TerminalUnavailablePayload
        and entry.payload.failure_code is AcquisitionFailureCode.EVIDENCE_INTEGRITY_FAILURE
        for entry in entries
    )
    if stop.evidence or retained_integrity_failure:
        result = AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
    elif stop.contract or JournalTransition.CONTRACT_REJECTED in transitions:
        result = AcquisitionCycleResult.SOURCE_CONTRACT_CHANGED
    elif stop.authorization or JournalTransition.AUTHORIZATION_REJECTED in transitions:
        result = AcquisitionCycleResult.AUTHORIZATION_FAILURE
    elif JournalTransition.RETRY_EXHAUSTED in transitions:
        result = AcquisitionCycleResult.RETRY_EXHAUSTED
    elif stop.budget:
        result = AcquisitionCycleResult.BUDGET_EXHAUSTED
    elif JournalTransition.TERMINAL_UNAVAILABLE in transitions:
        result = AcquisitionCycleResult.INCOMPLETE_TERMINAL
    elif transitions.issubset(
        {
            JournalTransition.CAPTURED_VERIFIED,
            JournalTransition.IMPORTED_CAPTURE_VERIFIED,
            JournalTransition.ACCOUNTED_EXCLUDED,
        }
    ):
        result = AcquisitionCycleResult.COMPLETE
    else:
        result = AcquisitionCycleResult.INCOMPLETE_RETRYABLE
    semantic_head = _semantic_journal_head(entries)
    canonical_dispositions = tuple(
        CheckpointItem(
            work_item_id=item.work_item_id,
            latest_sequence=index,
            transition=item.transition,
            attempt_count=item.attempt_count,
            object_ref=item.object_ref,
            retry_not_before=item.retry_not_before,
        )
        for index, item in enumerate(
            sorted(dispositions, key=lambda value: value.work_item_id),
            start=1,
        )
    )
    provisional = AcquisitionCycleReport(
        cycle_id=cycle_id,
        result=result,
        # Physical journal sequence is deliberately replaced by stable projection order.
        item_dispositions=canonical_dispositions,
        request_starts=budget.starts,
        retained_bytes=budget.retained_bytes,
        journal_head_fingerprint=semantic_head,
        fingerprint="",
    )
    report = AcquisitionCycleReport(
        cycle_id=provisional.cycle_id,
        result=provisional.result,
        item_dispositions=provisional.item_dispositions,
        request_starts=provisional.request_starts,
        retained_bytes=provisional.retained_bytes,
        journal_head_fingerprint=provisional.journal_head_fingerprint,
        fingerprint=_fingerprint(_report_body(provisional)),
    )
    return _issue_report(report, entries)
