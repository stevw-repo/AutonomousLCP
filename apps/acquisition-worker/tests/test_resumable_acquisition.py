"""Deterministic, bounded, resumable acquisition-runner tests."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from itertools import pairwise
from pathlib import Path

import pytest
from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    AcquisitionFailureCode,
    AcquisitionJournalEntry,
    AcquisitionJournalError,
    AdmissionFailedBeforeTransportPayload,
    AuthorizationRejectedPayload,
    CapturedVerifiedPayload,
    CycleSafetyProfilePayload,
    DiscoveredPayload,
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
from asklegal_acquisition_worker.resumable_acquisition import (
    CaptureAuthorizationFailure,
    CaptureOutcome,
    CaptureTransport,
    CycleBudget,
    ResumableAcquisitionError,
    ResumableAcquisitionRunner,
    ScheduledWorkItem,
)
from asklegal_contracts import canonicalize


class _Clock:
    """Thread-safe deterministic wall and monotonic clock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._monotonic_ns = 0
        self._now = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)

    def monotonic_ns(self) -> int:
        with self._lock:
            return self._monotonic_ns

    def now(self) -> datetime:
        with self._lock:
            return self._now

    def sleep(self, seconds: float) -> None:
        with self._lock:
            elapsed_ns = round(seconds * 1_000_000_000)
            self._monotonic_ns += elapsed_ns
            self._now = datetime.fromtimestamp(
                self._now.timestamp() + seconds,
                tz=UTC,
            )


class _RetainedVerifier:
    def __init__(self, *, verified: bool = True) -> None:
        self.verified = verified
        self.calls: list[tuple[str, str, str, int]] = []

    def verify(
        self,
        item: WorkItemIdentity,
        object_ref: str,
        content_fingerprint: str,
        body_length: int,
    ) -> bool:
        self.calls.append((item.work_item_id, object_ref, content_fingerprint, body_length))
        return self.verified


class _ExplodingCaptureTransport:
    def __init__(self) -> None:
        self.calls = 0

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        del item
        self.calls += 1
        msg = "retained import must not be recaptured"
        raise AssertionError(msg)


def _identity(
    index: int,
    *,
    cycle_id: str = "cyc_20260902_cases",
    host: str = "legalref.judiciary.hk",
    max_bytes: int = 1,
) -> WorkItemIdentity:
    return WorkItemIdentity.issue(
        source_family="CASES",
        source_role="HK_CASES_JUDICIARY_CURRENT",
        cycle_id=cycle_id,
        observation_cutoff="2026-09-02T00:00:00+00:00",
        procedure_version="1.0.0",
        locator=f"https://{host}/judgments?page={index}",
        stage="LISTING_PAGE",
        parent_id=f"year-{1997 + index // 100}",
        media_type="text/html",
        max_bytes=max_bytes,
    )


def _scheduled(
    index: int,
    *,
    cycle_id: str = "cyc_20260902_cases",
    host: str = "legalref.judiciary.hk",
    max_bytes: int = 1,
    not_before_monotonic_ns: int = 0,
) -> ScheduledWorkItem:
    return ScheduledWorkItem(
        identity=_identity(index, cycle_id=cycle_id, host=host, max_bytes=max_bytes),
        priority=(0, index, f"item-{index:04d}"),
        host=host,
        not_before_monotonic_ns=not_before_monotonic_ns,
    )


def _captured(
    item: WorkItemIdentity,
    *,
    redirects: int = 0,
    verified: bool = True,
) -> CaptureOutcome:
    digest = sha256(item.work_item_id.encode()).hexdigest()
    return CaptureOutcome(
        work_item_id=item.work_item_id,
        transition=JournalTransition.CAPTURED_VERIFIED,
        status_code=200,
        media_type=item.media_type,
        final_url=item.locator,
        body_length=item.max_bytes,
        body_fingerprint=f"sha256:{digest}",
        object_ref=f"opaque/{digest}",
        failure_code=None,
        retry_not_before=None,
        read_back_verified=verified,
        redirect_chain=tuple(
            f"https://{item.locator.split('/')[2]}/redirect/{index}" for index in range(redirects)
        ),
    )


def _budget(
    *,
    starts: int = 100,
    retained_bytes: int = 100,
    elapsed_seconds: int = 60,
    redirects: int = 100,
) -> CycleBudget:
    return CycleBudget(
        maximum_starts=starts,
        maximum_retained_bytes=retained_bytes,
        maximum_elapsed_seconds=elapsed_seconds,
        maximum_redirects=redirects,
    )


def _cycle_profile(  # noqa: PLR0913 - test helper exposes each immutable profile control.
    *,
    cycle_started_at_epoch_us: int = 1_788_307_200_000_000,
    starts: int = 100,
    retained_bytes: int = 100,
    elapsed_seconds: int = 60,
    redirects: int = 100,
    per_host_limit: int = 4,
    minimum_start_interval_ns: int = 0,
    maximum_attempts_per_item: int = 2,
    maximum_redirects_per_start: int = 1,
) -> CycleSafetyProfilePayload:
    return CycleSafetyProfilePayload(
        schema_id="asklegal.acquisition-cycle-safety-profile",
        schema_version="1.0.0",
        maximum_starts=starts,
        maximum_retained_bytes=retained_bytes,
        maximum_elapsed_seconds=elapsed_seconds,
        maximum_redirects=redirects,
        per_host_limit=per_host_limit,
        minimum_start_interval_ns=minimum_start_interval_ns,
        maximum_attempts_per_item=maximum_attempts_per_item,
        maximum_redirects_per_start=maximum_redirects_per_start,
        cycle_started_at_epoch_us=cycle_started_at_epoch_us,
    )


def _runner(  # noqa: PLR0913 - test helper exposes each independently tested control.
    journal: LocalAcquisitionJournal,
    items: tuple[ScheduledWorkItem, ...],
    transport: CaptureTransport,
    *,
    clock: _Clock | None = None,
    budget: CycleBudget | None = None,
    per_host_limit: int = 4,
    minimum_start_interval_ns: int = 0,
    maximum_attempts_per_item: int = 2,
    maximum_redirects_per_start: int = 1,
    stop_requested: Callable[[], bool] | None = None,
    retained_verifier: _RetainedVerifier | None = None,
    dependencies: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> ResumableAcquisitionRunner:
    selected_clock = clock or _Clock()
    return ResumableAcquisitionRunner(
        journal=journal,
        items=items,
        transport=transport,
        retained_verifier=retained_verifier or _RetainedVerifier(),
        clock=selected_clock,
        sleeper=selected_clock.sleep,
        budget=budget or _budget(),
        per_host_limit=per_host_limit,
        minimum_start_interval_ns=minimum_start_interval_ns,
        maximum_attempts_per_item=maximum_attempts_per_item,
        maximum_redirects_per_start=maximum_redirects_per_start,
        stop_requested=stop_requested,
        dependencies=dependencies,
    )


class _BlockingCountingTransport:
    """Force genuine overlap while measuring calls inside the transport boundary."""

    def __init__(self, wave_size: int) -> None:
        self._barrier = threading.Barrier(wave_size)
        self._lock = threading.Lock()
        self._active: dict[str, int] = defaultdict(int)
        self.maximum_active_by_host: dict[str, int] = defaultdict(int)
        self.calls: list[str] = []

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        host = item.locator.split("/")[2]
        with self._lock:
            self.calls.append(item.work_item_id)
            self._active[host] += 1
            self.maximum_active_by_host[host] = max(
                self.maximum_active_by_host[host],
                self._active[host],
            )
        try:
            self._barrier.wait(timeout=5)
            time.sleep(0.005)
            return _captured(item)
        finally:
            with self._lock:
                self._active[host] -= 1


def test_one_host_never_exceeds_four_active_requests(tmp_path: Path) -> None:
    """Removing the host gate must allow the fifth real transport call to overlap."""
    items = tuple(_scheduled(index) for index in range(12))
    transport = _BlockingCountingTransport(wave_size=4)
    with LocalAcquisitionJournal(tmp_path / "state", items[0].identity.cycle_id) as journal:
        report = _runner(journal, items, transport).run()

    assert dict(transport.maximum_active_by_host) == {"legalref.judiciary.hk": 4}
    assert len(transport.calls) == 12
    assert report.result is AcquisitionCycleResult.COMPLETE


class _PacingTransport:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.starts: dict[str, list[int]] = defaultdict(list)

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        host = item.locator.split("/")[2]
        with self._lock:
            self.starts[host].append(time.monotonic_ns())
        time.sleep(0.015)
        return _captured(item)


class _RealClock:
    @staticmethod
    def monotonic_ns() -> int:
        return time.monotonic_ns()

    @staticmethod
    def now() -> datetime:
        return datetime.now(tz=UTC)


class _AdvancingClock:
    """Real monotonic elapsed time projected from one identical fixed wall origin."""

    def __init__(self) -> None:
        self._monotonic_origin = time.monotonic_ns()
        self._wall_origin = datetime(2026, 9, 2, tzinfo=UTC)

    @staticmethod
    def monotonic_ns() -> int:
        return time.monotonic_ns()

    def now(self) -> datetime:
        elapsed_ns = time.monotonic_ns() - self._monotonic_origin
        return self._wall_origin + timedelta(microseconds=elapsed_ns // 1_000)


def test_hosts_progress_independently_while_each_host_is_exactly_paced(tmp_path: Path) -> None:
    """A global pacing lock would serialize unrelated official hosts."""
    interval_ns = 50_000_000
    items = tuple(
        _scheduled(index, host=host)
        for index in range(3)
        for host in ("legalref.judiciary.hk", "www.elegislation.gov.hk")
    )
    transport = _PacingTransport()
    with LocalAcquisitionJournal(tmp_path / "state", items[0].identity.cycle_id) as journal:
        runner = ResumableAcquisitionRunner(
            journal=journal,
            items=items,
            transport=transport,
            retained_verifier=_RetainedVerifier(),
            clock=_RealClock(),
            sleeper=time.sleep,
            budget=_budget(),
            per_host_limit=4,
            minimum_start_interval_ns=interval_ns,
            maximum_attempts_per_item=1,
            maximum_redirects_per_start=1,
        )
        assert runner.run().result is AcquisitionCycleResult.COMPLETE

    for starts in transport.starts.values():
        assert all(right - left >= interval_ns for left, right in pairwise(starts))
    first_starts = [starts[0] for starts in transport.starts.values()]
    assert max(first_starts) - min(first_starts) < 40_000_000


class _DelayedTransport:
    def __init__(self, delays: tuple[float, ...]) -> None:
        self._delays = delays

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        index = int(item.locator.rsplit("=", maxsplit=1)[1])
        time.sleep(self._delays[index])
        return _captured(item)


def _deterministic_run(root: Path, delays: tuple[float, ...]) -> tuple[bytes, str]:
    items = tuple(_scheduled(index) for index in range(len(delays)))
    with LocalAcquisitionJournal(root, items[0].identity.cycle_id) as journal:
        report = _runner(journal, items, _DelayedTransport(delays)).run()
        physical_head = journal.load_checkpoint().journal_head_fingerprint
    return canonicalize(report.to_json()), physical_head


def _advancing_deterministic_run(root: Path, delays: tuple[float, ...]) -> bytes:
    items = tuple(_scheduled(index) for index in range(len(delays)))
    clock = _AdvancingClock()
    with LocalAcquisitionJournal(root, items[0].identity.cycle_id) as journal:
        report = ResumableAcquisitionRunner(
            journal=journal,
            items=items,
            transport=_DelayedTransport(delays),
            retained_verifier=_RetainedVerifier(),
            clock=clock,
            sleeper=time.sleep,
            budget=_budget(),
            maximum_redirects_per_start=1,
        ).run()
    return canonicalize(report.to_json())


def test_report_bytes_ignore_forward_reverse_and_random_completion_order(tmp_path: Path) -> None:
    """Completion timing must not leak into release-facing bytes or their fingerprint."""
    forward = tuple(index * 0.001 for index in range(8))
    reverse = tuple(reversed(forward))
    random_order = (0.006, 0.001, 0.007, 0.0, 0.004, 0.002, 0.005, 0.003)
    results = tuple(
        _deterministic_run(tmp_path / f"run-{index}", delays)
        for index, delays in enumerate((forward, reverse, random_order))
    )

    assert len({body for body, _head in results}) == 1
    assert len({sha256(body).hexdigest() for body, _head in results}) == 1
    assert len({head for _body, head in results}) > 1


def test_release_projection_omits_durable_operational_timing(tmp_path: Path) -> None:
    """Persisted pacing/elapsed timestamps cannot leak completion timing into release bytes."""
    forward = tuple(index * 0.002 for index in range(8))
    reverse = tuple(reversed(forward))
    assert _advancing_deterministic_run(tmp_path / "forward", forward) == (
        _advancing_deterministic_run(tmp_path / "reverse", reverse)
    )


class _RetryTransport:
    def __init__(self, retry_item_id: str) -> None:
        self.retry_item_id = retry_item_id
        self.calls: dict[str, int] = defaultdict(int)

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.calls[item.work_item_id] += 1
        if item.work_item_id == self.retry_item_id and self.calls[item.work_item_id] == 1:
            return CaptureOutcome(
                work_item_id=item.work_item_id,
                transition=JournalTransition.RETRYABLE_FAILURE,
                status_code=None,
                media_type=None,
                final_url=None,
                body_length=0,
                body_fingerprint=None,
                object_ref=None,
                failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE.value,
                retry_not_before="2026-09-02T00:00:00+00:00",
                read_back_verified=False,
                redirect_chain=(),
            )
        return _captured(item)


class _AlwaysRetryTransport:
    def __init__(self) -> None:
        self.calls = 0

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.calls += 1
        return CaptureOutcome(
            work_item_id=item.work_item_id,
            transition=JournalTransition.RETRYABLE_FAILURE,
            status_code=None,
            media_type=None,
            final_url=None,
            body_length=0,
            body_fingerprint=None,
            object_ref=None,
            failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE.value,
            retry_not_before="2026-09-02T00:00:00+00:00",
            read_back_verified=False,
            redirect_chain=(),
        )


def test_retryable_failure_reenters_queue_without_stopping_unrelated_items(tmp_path: Path) -> None:
    """Treating one outage as a cycle stop must leave unrelated items uncaptured."""
    items = tuple(_scheduled(index) for index in range(5))
    transport = _RetryTransport(items[0].identity.work_item_id)
    with LocalAcquisitionJournal(tmp_path / "state", items[0].identity.cycle_id) as journal:
        report = _runner(journal, items, transport).run()

    assert report.result is AcquisitionCycleResult.COMPLETE
    assert transport.calls[items[0].identity.work_item_id] == 2
    assert all(transport.calls[item.identity.work_item_id] >= 1 for item in items)


def test_retry_attempt_ceiling_becomes_durable_exhaustion_not_inert_retry(
    tmp_path: Path,
) -> None:
    """A final failed attempt cannot remain forever labeled retryable with no eligible retry."""
    item = _scheduled(0)
    state = tmp_path / "state"
    transport = _AlwaysRetryTransport()
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            transport,
            maximum_attempts_per_item=1,
        ).run()
        entries = journal.replay()

    assert report.result.value == "RETRY_EXHAUSTED"
    assert entries[-1].transition.value == "RETRY_EXHAUSTED"
    assert isinstance(entries[-1].payload, RetryExhaustedPayload)
    assert entries[-1].payload.attempt == 1
    assert transport.calls == 1

    resumed = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        assert (
            _runner(
                journal,
                (item,),
                resumed,
                maximum_attempts_per_item=1,
            )
            .run()
            .result.value
            == "RETRY_EXHAUSTED"
        )
    assert resumed.calls == []


class _OutcomeTransport:
    def __init__(self, first: CaptureOutcome | BaseException) -> None:
        self.first = first
        self.calls = 0

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.calls += 1
        if self.calls == 1:
            if isinstance(self.first, BaseException):
                raise self.first
            return self.first
        return _captured(item)


class _DependencyStoppingTransport:
    """Prove a descendant never starts after its prerequisite fails."""

    def __init__(self, parent_id: str) -> None:
        self.parent_id = parent_id
        self.calls: list[str] = []

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.calls.append(item.work_item_id)
        if item.work_item_id != self.parent_id:
            msg = "dependent work started before its prerequisite completed"
            raise AssertionError(msg)
        return CaptureOutcome(
            work_item_id=item.work_item_id,
            transition=JournalTransition.TERMINAL_UNAVAILABLE,
            status_code=None,
            media_type=None,
            final_url=None,
            body_length=0,
            body_fingerprint=None,
            object_ref=None,
            failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE.value,
            retry_not_before=None,
            read_back_verified=False,
            redirect_chain=(),
        )


def test_stage_dependency_waits_for_verified_prerequisite(tmp_path: Path) -> None:
    """A failed prerequisite leaves its descendant discovered and unstarted."""
    parent = _scheduled(0)
    child = _scheduled(1)
    transport = _DependencyStoppingTransport(parent.identity.work_item_id)
    dependencies = (
        (parent.identity.work_item_id, ()),
        (child.identity.work_item_id, (parent.identity.work_item_id,)),
    )

    with LocalAcquisitionJournal(tmp_path / "state", parent.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (parent, child),
            transport,
            dependencies=dependencies,
        ).run()

    assert transport.calls == [parent.identity.work_item_id]
    assert report.result is AcquisitionCycleResult.INCOMPLETE_TERMINAL
    assert {item.work_item_id: item.transition for item in report.item_dispositions}[
        child.identity.work_item_id
    ] is JournalTransition.DISCOVERED


class _RedirectTransport:
    def __init__(self) -> None:
        self.calls = 0

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.calls += 1
        return _captured(item, redirects=1)


def _contract_outcome(item: WorkItemIdentity) -> CaptureOutcome:
    return CaptureOutcome(
        work_item_id=item.work_item_id,
        transition=JournalTransition.CONTRACT_REJECTED,
        status_code=None,
        media_type=None,
        final_url=None,
        body_length=0,
        body_fingerprint=None,
        object_ref=None,
        failure_code=AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED.value,
        retry_not_before=None,
        read_back_verified=False,
        redirect_chain=(),
    )


def test_contract_drift_stops_new_dispatch_but_drains_already_started_work(tmp_path: Path) -> None:
    """Continuing the queue after root drift could issue unsafe descendant requests."""
    items = tuple(_scheduled(index) for index in range(20))
    transport = _OutcomeTransport(_contract_outcome(items[0].identity))
    with LocalAcquisitionJournal(tmp_path / "state", items[0].identity.cycle_id) as journal:
        report = _runner(journal, items, transport).run()

    assert report.result is AcquisitionCycleResult.SOURCE_CONTRACT_CHANGED
    assert 1 <= transport.calls <= 4


def test_unverified_readback_never_maps_to_captured_verified(tmp_path: Path) -> None:
    """Ignoring the read-back bit would journal false verified evidence."""
    item = _scheduled(0)
    transport = _OutcomeTransport(_captured(item.identity, verified=False))
    with LocalAcquisitionJournal(tmp_path / "state", item.identity.cycle_id) as journal:
        report = _runner(journal, (item,), transport).run()
        entries = journal.replay()

    assert report.result is AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
    assert all(entry.transition is not JournalTransition.CAPTURED_VERIFIED for entry in entries)
    assert entries[-1].transition is JournalTransition.TERMINAL_UNAVAILABLE
    assert entries[-1].payload == TerminalUnavailablePayload(
        attempt=1,
        failure_code=AcquisitionFailureCode.EVIDENCE_INTEGRITY_FAILURE,
    )

    resumed = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(
        tmp_path / "state",
        item.identity.cycle_id,
    ) as journal:
        assert _runner(journal, (item,), resumed).run().result is (
            AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
        )
    assert resumed.calls == []


@pytest.mark.parametrize(
    "hostile_outcome",
    [
        replace(
            _captured(_identity(0)),
            final_url="https://attacker.invalid/stolen",
        ),
        replace(
            _captured(_identity(0)),
            redirect_chain=("https://attacker.invalid/bounce",),
        ),
    ],
)
def test_captured_final_and_redirect_origins_must_remain_on_exact_admitted_host(
    tmp_path: Path,
    hostile_outcome: CaptureOutcome,
) -> None:
    """Canonical HTTPS alone cannot authorize an outcome from another origin."""
    item = _scheduled(0)
    with LocalAcquisitionJournal(tmp_path / "state", item.identity.cycle_id) as journal:
        report = _runner(journal, (item,), _OutcomeTransport(hostile_outcome)).run()
        entries = journal.replay()
    assert report.result is AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
    assert all(entry.transition is not JournalTransition.CAPTURED_VERIFIED for entry in entries)


def test_stale_other_item_capture_outcome_cannot_complete_current_work(tmp_path: Path) -> None:
    """A same-host response for another immutable request cannot satisfy this work ID."""
    current = _scheduled(0)
    stale = _scheduled(1)
    with LocalAcquisitionJournal(tmp_path / "state", current.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (current,),
            _OutcomeTransport(_captured(stale.identity)),
        ).run()
        entries = journal.replay()
    assert report.result is AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
    assert all(entry.transition is not JournalTransition.CAPTURED_VERIFIED for entry in entries)


def test_mutated_capture_outcome_is_reconstructed_before_interpretation(tmp_path: Path) -> None:
    """An empty list substituted into a frozen retry outcome cannot pass as an exact tuple."""
    item = _scheduled(0)
    outcome = _AlwaysRetryTransport().capture(item.identity)
    object.__setattr__(outcome, "redirect_chain", [])
    with LocalAcquisitionJournal(tmp_path / "state", item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            _OutcomeTransport(outcome),
            maximum_attempts_per_item=1,
        ).run()
        entries = journal.replay()
    assert report.result is AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
    assert entries[-2].transition is JournalTransition.TRANSPORT_STARTED
    assert entries[-1].transition is JournalTransition.TERMINAL_UNAVAILABLE


def test_resume_reverifies_retained_object_before_success_or_transport(tmp_path: Path) -> None:
    """A journaled captured claim cannot grant current success after retained read-back fails."""
    item = _scheduled(0)
    captured = _captured(item.identity)
    state = tmp_path / "state"
    cycle_started_at_epoch_us = 1_788_307_200_000_000
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        journal.append(
            item.identity,
            JournalTransition.DISCOVERED,
            DiscoveredPayload(cycle_started_at_epoch_us),
        )
        journal.append(
            item.identity,
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            CycleSafetyProfilePayload(
                schema_id="asklegal.acquisition-cycle-safety-profile",
                schema_version="1.0.0",
                maximum_starts=100,
                maximum_retained_bytes=100,
                maximum_elapsed_seconds=60,
                maximum_redirects=100,
                per_host_limit=4,
                minimum_start_interval_ns=0,
                maximum_attempts_per_item=2,
                maximum_redirects_per_start=1,
                cycle_started_at_epoch_us=cycle_started_at_epoch_us,
            ),
        )
        journal.append(
            item.identity,
            JournalTransition.STARTED,
            StartedPayload(
                attempt=1,
                started_at_epoch_us=cycle_started_at_epoch_us,
                host_not_before_epoch_us=cycle_started_at_epoch_us,
                reserved_redirects=1,
            ),
        )
        journal.append(
            item.identity,
            JournalTransition.TRANSPORT_STARTED,
            TransportStartedPayload(
                attempt=1,
                started_at_epoch_us=cycle_started_at_epoch_us,
                host_not_before_epoch_us=cycle_started_at_epoch_us,
            ),
        )
        journal.append(
            item.identity,
            JournalTransition.CAPTURED_VERIFIED,
            CapturedVerifiedPayload(
                attempt=1,
                status=200,
                media_type=item.identity.media_type,
                final_url=item.identity.locator,
                redirect_chain=(),
                body_length=1,
                content_fingerprint=captured.body_fingerprint or "",
                object_ref=captured.object_ref or "",
                read_back_verified=True,
            ),
        )
    verifier = _RetainedVerifier(verified=False)
    transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        runner = ResumableAcquisitionRunner(
            journal=journal,
            items=(item,),
            transport=transport,
            retained_verifier=verifier,
            clock=_Clock(),
            sleeper=lambda _seconds: None,
            budget=_budget(),
            maximum_redirects_per_start=1,
        )
        report = runner.run()
    assert report.result is AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
    assert verifier.calls == [
        (
            item.identity.work_item_id,
            captured.object_ref,
            captured.body_fingerprint,
            1,
        )
    ]
    assert transport.calls == []


def test_retained_readback_failure_precedes_a_prior_durable_stop(tmp_path: Path) -> None:
    """A closed stop cannot suppress current integrity verification of retained success."""
    captured_item, rejected_item = _scheduled(0), _scheduled(1)
    state = tmp_path / "state"
    cycle_started_at_epoch_us = 1_788_307_200_000_000
    with LocalAcquisitionJournal(state, captured_item.identity.cycle_id) as journal:
        for item in (captured_item, rejected_item):
            journal.append(
                item.identity,
                JournalTransition.DISCOVERED,
                DiscoveredPayload(cycle_started_at_epoch_us),
            )
        journal.append(
            captured_item.identity,
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            CycleSafetyProfilePayload(
                schema_id="asklegal.acquisition-cycle-safety-profile",
                schema_version="1.0.0",
                maximum_starts=100,
                maximum_retained_bytes=100,
                maximum_elapsed_seconds=60,
                maximum_redirects=100,
                per_host_limit=4,
                minimum_start_interval_ns=0,
                maximum_attempts_per_item=2,
                maximum_redirects_per_start=1,
                cycle_started_at_epoch_us=cycle_started_at_epoch_us,
            ),
        )
        for item in (captured_item, rejected_item):
            journal.append(
                item.identity,
                JournalTransition.STARTED,
                StartedPayload(
                    attempt=1,
                    started_at_epoch_us=cycle_started_at_epoch_us,
                    host_not_before_epoch_us=cycle_started_at_epoch_us,
                    reserved_redirects=1,
                ),
            )
            journal.append(
                item.identity,
                JournalTransition.TRANSPORT_STARTED,
                TransportStartedPayload(
                    attempt=1,
                    started_at_epoch_us=cycle_started_at_epoch_us,
                    host_not_before_epoch_us=cycle_started_at_epoch_us,
                ),
            )
        journal.append(
            captured_item.identity,
            JournalTransition.CAPTURED_VERIFIED,
            CapturedVerifiedPayload(
                attempt=1,
                status=200,
                media_type=captured_item.identity.media_type,
                final_url=captured_item.identity.locator,
                redirect_chain=(),
                body_length=1,
                content_fingerprint="sha256:" + "a" * 64,
                object_ref="opaque:captured",
                read_back_verified=True,
            ),
        )
        journal.append(
            rejected_item.identity,
            JournalTransition.AUTHORIZATION_REJECTED,
            AuthorizationRejectedPayload(attempt=1),
        )

    transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, captured_item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (captured_item, rejected_item),
            transport,
            retained_verifier=_RetainedVerifier(verified=False),
        ).run()
    assert report.result is AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
    assert transport.calls == []


def test_transport_contract_exception_closes_exact_attempt_as_evidence_failure(
    tmp_path: Path,
) -> None:
    """A completed hostile future is not an interrupted worker and must not retry on resume."""
    item = _scheduled(0)
    state = tmp_path / "state"
    transport = _OutcomeTransport(TypeError("hostile transport result"))
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        report = _runner(journal, (item,), transport).run()
        entries = journal.replay()

    assert report.result is AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
    assert entries[-1].transition is JournalTransition.TERMINAL_UNAVAILABLE
    assert entries[-1].payload == TerminalUnavailablePayload(
        attempt=1,
        failure_code=AcquisitionFailureCode.EVIDENCE_INTEGRITY_FAILURE,
    )

    resumed = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        assert _runner(journal, (item,), resumed).run().result is (
            AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE
        )
    assert resumed.calls == []


def test_authorization_failure_is_a_closed_exception_and_stops_new_dispatch(tmp_path: Path) -> None:
    """Authorization loss must be durable and cannot become interruption on resume."""
    items = tuple(_scheduled(index) for index in range(20))
    transport = _OutcomeTransport(CaptureAuthorizationFailure())
    state = tmp_path / "state"
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        report = _runner(journal, items, transport).run()
        entries = journal.replay()
    assert report.result.value == "AUTHORIZATION_FAILURE"
    assert any(entry.transition is JournalTransition.TRANSPORT_STARTED for entry in entries)
    assert any(entry.transition.value == "AUTHORIZATION_REJECTED" for entry in entries)
    assert 1 <= transport.calls <= 4

    resumed = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        assert _runner(journal, items, resumed).run().result.value == "AUTHORIZATION_FAILURE"
    assert resumed.calls == []


@pytest.mark.parametrize(
    ("budget", "items", "expected_calls"),
    [
        (_budget(starts=4), tuple(_scheduled(index) for index in range(8)), 4),
        (
            _budget(retained_bytes=10),
            tuple(_scheduled(index, max_bytes=5) for index in range(8)),
            2,
        ),
        (_budget(redirects=2), tuple(_scheduled(index) for index in range(8)), 2),
    ],
)
def test_concurrent_budget_reservations_cannot_overshoot(
    tmp_path: Path,
    budget: CycleBudget,
    items: tuple[ScheduledWorkItem, ...],
    expected_calls: int,
) -> None:
    """Removing pre-dispatch reservations must admit one call beyond a cycle ceiling."""
    transport = (
        _RedirectTransport()
        if budget.maximum_redirects == 2
        else _OutcomeTransport(_captured(items[0].identity))
    )
    with LocalAcquisitionJournal(tmp_path / "state", items[0].identity.cycle_id) as journal:
        report = _runner(journal, items, transport, budget=budget).run()

    assert transport.calls == expected_calls
    assert report.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert report.request_starts == expected_calls
    assert report.retained_bytes <= budget.maximum_retained_bytes


def test_failed_start_consumes_durable_redirect_reservation_across_resume(
    tmp_path: Path,
) -> None:
    """Failure cannot release an already admitted redirect allowance for reuse."""
    item = _scheduled(0)
    state = tmp_path / "state"
    first = _AlwaysRetryTransport()
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            first,
            budget=_budget(redirects=1),
            maximum_redirects_per_start=1,
        ).run()
    assert first.calls == 1
    assert report.result is AcquisitionCycleResult.BUDGET_EXHAUSTED

    resumed = _AlwaysRetryTransport()
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        second = _runner(
            journal,
            (item,),
            resumed,
            budget=_budget(redirects=1),
            maximum_redirects_per_start=1,
        ).run()
    assert second.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert resumed.calls == 0


def test_elapsed_budget_blocks_a_future_start_without_sleeping_past_deadline(
    tmp_path: Path,
) -> None:
    """A not-before time beyond the cycle deadline must not become a post-budget request."""
    item = _scheduled(0, not_before_monotonic_ns=2_000_000_000)
    transport = _OutcomeTransport(_captured(item.identity))
    with LocalAcquisitionJournal(tmp_path / "state", item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            transport,
            budget=_budget(elapsed_seconds=1),
        ).run()
    assert report.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert transport.calls == 0


class _ElapsedTransport:
    def __init__(self, clock: _Clock) -> None:
        self._clock = clock

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self._clock.sleep(2)
        return _captured(item)


def test_elapsed_budget_exhaustion_drains_and_accounts_an_inflight_capture(
    tmp_path: Path,
) -> None:
    """An in-flight outcome crossing the deadline is retained but cannot yield success."""
    clock = _Clock()
    item = _scheduled(0)
    with LocalAcquisitionJournal(tmp_path / "state", item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            _ElapsedTransport(clock),
            clock=clock,
            budget=_budget(elapsed_seconds=1),
        ).run()
    assert report.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert report.request_starts == 1
    assert report.retained_bytes == 1


def test_elapsed_budget_remains_exhausted_after_restart(tmp_path: Path) -> None:
    """A completed in-flight item cannot turn prior cycle-wide exhaustion into success."""
    clock = _Clock()
    item = _scheduled(0)
    state = tmp_path / "state"
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        first = _runner(
            journal,
            (item,),
            _ElapsedTransport(clock),
            clock=clock,
            budget=_budget(elapsed_seconds=1),
        ).run()
    assert first.result is AcquisitionCycleResult.BUDGET_EXHAUSTED

    resumed = _InterruptingTransport(threading.Event())
    restarted_clock = _Clock()
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        second = _runner(
            journal,
            (item,),
            resumed,
            clock=restarted_clock,
            budget=_budget(elapsed_seconds=1),
        ).run()
    assert second.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert resumed.calls == []


class _InterruptingTransport:
    def __init__(self, stop: threading.Event, *, stop_after: int | None = None) -> None:
        self.stop = stop
        self.stop_after = stop_after
        self.calls: list[str] = []

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.calls.append(item.work_item_id)
        if self.stop_after is not None and len(self.calls) == self.stop_after:
            self.stop.set()
        return _captured(item)


def test_clean_interruption_after_seven_verified_items_resumes_without_repeat(
    tmp_path: Path,
) -> None:
    """A restarted runner must not redownload any of the seven verified objects."""
    items = tuple(_scheduled(index) for index in range(12))
    state = tmp_path / "state"
    stop = threading.Event()
    first_transport = _InterruptingTransport(stop, stop_after=7)
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        first_report = _runner(
            journal,
            items,
            first_transport,
            per_host_limit=1,
            stop_requested=stop.is_set,
        ).run()
    assert first_report.result is AcquisitionCycleResult.INCOMPLETE_RETRYABLE
    assert len(first_transport.calls) == 7

    second_transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        second_report = _runner(journal, items, second_transport, per_host_limit=1).run()

    assert second_report.result is AcquisitionCycleResult.COMPLETE
    assert len(second_transport.calls) == 5
    assert set(first_transport.calls).isdisjoint(second_transport.calls)


class _StartRecordingTransport:
    def __init__(self, clock: _Clock) -> None:
        self._clock = clock
        self.starts: list[int] = []

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.starts.append(self._clock.monotonic_ns())
        return _captured(item)


def test_host_pacing_deadline_survives_clean_restart(tmp_path: Path) -> None:
    """Restart cannot discard the prior host's persisted next-admitted-start instant."""
    interval_ns = 1_000_000_000
    items = tuple(_scheduled(index) for index in range(2))
    state = tmp_path / "state"
    clock = _Clock()
    stop = threading.Event()
    first = _InterruptingTransport(stop, stop_after=1)
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        assert (
            _runner(
                journal,
                items,
                first,
                clock=clock,
                per_host_limit=1,
                minimum_start_interval_ns=interval_ns,
                stop_requested=stop.is_set,
            )
            .run()
            .result
            is AcquisitionCycleResult.INCOMPLETE_RETRYABLE
        )

    resumed = _StartRecordingTransport(clock)
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        assert (
            _runner(
                journal,
                items,
                resumed,
                clock=clock,
                per_host_limit=1,
                minimum_start_interval_ns=interval_ns,
            )
            .run()
            .result
            is AcquisitionCycleResult.COMPLETE
        )
    assert resumed.starts == [interval_ns]


def test_resume_rejects_minimum_interval_profile_drift_before_effect(
    tmp_path: Path,
) -> None:
    """A resumed pacing change is profile drift even when it would be stricter."""
    interval_ns = 1_000_000_000
    items = tuple(_scheduled(index) for index in range(2))
    state = tmp_path / "state"
    clock = _Clock()
    stop = threading.Event()
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        _runner(
            journal,
            items,
            _InterruptingTransport(stop, stop_after=1),
            clock=clock,
            per_host_limit=1,
            minimum_start_interval_ns=0,
            stop_requested=stop.is_set,
        ).run()

    resumed = _StartRecordingTransport(clock)
    with (
        LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal,
        pytest.raises(ResumableAcquisitionError, match="CYCLE_SAFETY_PROFILE_DRIFT"),
    ):
        (
            _runner(
                journal,
                items,
                resumed,
                clock=clock,
                per_host_limit=1,
                minimum_start_interval_ns=interval_ns,
            ).run()
        )
    assert resumed.starts == []


def test_orphan_started_is_interrupted_at_exact_attempt_before_attempt_plus_one(
    tmp_path: Path,
) -> None:
    """Reusing attempt one or calling it timeout/outage would falsify physical history."""
    item = _scheduled(0)
    state = tmp_path / "state"
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        journal.append(
            item.identity,
            JournalTransition.DISCOVERED,
            DiscoveredPayload(cycle_started_at_epoch_us=1_788_307_200_000_000),
        )
        journal.append(
            item.identity,
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            _cycle_profile(),
        )
        journal.append(
            item.identity,
            JournalTransition.STARTED,
            StartedPayload(
                attempt=1,
                started_at_epoch_us=1_788_307_200_000_000,
                host_not_before_epoch_us=1_788_307_200_000_000,
                reserved_redirects=1,
            ),
        )
    transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        report = _runner(journal, (item,), transport).run()
        entries = journal.replay()

    assert report.result is AcquisitionCycleResult.COMPLETE
    interruption = next(
        entry for entry in entries if entry.transition is JournalTransition.RETRYABLE_FAILURE
    )
    assert interruption.transition is JournalTransition.RETRYABLE_FAILURE
    assert interruption.payload == RetryableFailurePayload(
        attempt=1,
        failure_code=AcquisitionFailureCode.WORKER_INTERRUPTED,
        retry_not_before="2026-09-02T00:00:00+00:00",
    )
    restarted = tuple(entry for entry in entries if entry.transition is JournalTransition.STARTED)[
        -1
    ]
    assert type(restarted.payload) is StartedPayload
    assert restarted.payload.attempt == 2


def test_exact_duplicate_converges_once_but_scheduling_fact_drift_fails_pre_effect(
    tmp_path: Path,
) -> None:
    """One work ID cannot create two requests or hide different scheduling facts."""
    item = _scheduled(0)
    exact_transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(tmp_path / "exact", item.identity.cycle_id) as journal:
        report = _runner(journal, (item, item), exact_transport).run()
    assert report.result is AcquisitionCycleResult.COMPLETE
    assert len(exact_transport.calls) == 1

    drift_transport = _InterruptingTransport(threading.Event())
    with (
        LocalAcquisitionJournal(tmp_path / "drift", item.identity.cycle_id) as journal,
        pytest.raises(ResumableAcquisitionError, match="WORK_ITEM_FACT_DRIFT"),
    ):
        _runner(
            journal,
            (item, replace(item, priority=(9, 9, "drift"))),
            drift_transport,
        ).run()
    assert drift_transport.calls == []


def test_mutated_scheduling_facts_fail_runner_admission_before_effect(tmp_path: Path) -> None:
    """Frozen-object mutation cannot split one official host across forged gate identities."""
    item = _scheduled(0)
    object.__setattr__(item, "host", "forged.invalid")
    transport = _InterruptingTransport(threading.Event())
    with (
        LocalAcquisitionJournal(tmp_path / "state", item.identity.cycle_id) as journal,
        pytest.raises(ResumableAcquisitionError, match="SCHEDULE_INVALID"),
    ):
        _runner(journal, (item,), transport)
    assert transport.calls == []


def test_journal_integrity_failure_stops_before_transport(tmp_path: Path) -> None:
    """A corrupt chain cannot be hidden behind a derived runner report."""
    item = _scheduled(0)
    state = tmp_path / "state"
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        journal.append(
            item.identity,
            JournalTransition.DISCOVERED,
            DiscoveredPayload(1_788_307_200_000_000),
        )
    entry = (
        state
        / "acquisition-journals"
        / item.identity.cycle_id
        / "entries"
        / "00000000000000000001.json"
    )
    entry.write_bytes(b"not-json")
    transport = _InterruptingTransport(threading.Event())
    with (
        LocalAcquisitionJournal(state, item.identity.cycle_id) as journal,
        pytest.raises(AcquisitionJournalError, match="JOURNAL_REPLAY_INVALID"),
    ):
        _runner(journal, (item,), transport).run()
    assert transport.calls == []


def test_compact_journal_bytes_fail_before_verifier_or_transport(tmp_path: Path) -> None:
    """Mixed pre-modern bytes cannot enter automatic upgrade or any effect boundary."""
    item = _scheduled(0)
    state = tmp_path / "state"
    cycle_started_at_epoch_us = 1_788_307_200_000_000
    modern = AcquisitionJournalEntry.issue(
        sequence=1,
        previous_entry_fingerprint="sha256:" + "0" * 64,
        work_item=item.identity,
        transition=JournalTransition.DISCOVERED,
        payload=DiscoveredPayload(cycle_started_at_epoch_us),
    ).to_json()
    modern["payload"] = {}
    body = {key: value for key, value in modern.items() if key != "fingerprint"}
    modern["fingerprint"] = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    with LocalAcquisitionJournal(state, item.identity.cycle_id):
        pass
    entry_path = (
        state
        / "acquisition-journals"
        / item.identity.cycle_id
        / "entries"
        / "00000000000000000001.json"
    )
    entry_path.write_bytes(canonicalize(modern))
    verifier = _RetainedVerifier()
    transport = _InterruptingTransport(threading.Event())

    with (
        LocalAcquisitionJournal(state, item.identity.cycle_id) as journal,
        pytest.raises(AcquisitionJournalError, match="JOURNAL_REPLAY_INVALID"),
    ):
        _runner(
            journal,
            (item,),
            transport,
            retained_verifier=verifier,
        ).run()
    assert verifier.calls == []
    assert transport.calls == []


def test_empty_work_graph_cannot_be_reported_complete(tmp_path: Path) -> None:
    """An absent required work graph is not evidence of a complete source cycle."""
    with (
        LocalAcquisitionJournal(tmp_path / "state", "cyc_20260902_cases") as journal,
        pytest.raises(ResumableAcquisitionError, match="WORK_GRAPH_EMPTY"),
    ):
        _runner(journal, (), _InterruptingTransport(threading.Event()))


class _OversleepClock(_Clock):
    """Deterministically overshoot every requested host-pacing sleep."""

    def __init__(self, overshoot_ns: int) -> None:
        super().__init__()
        self._overshoot_ns = overshoot_ns

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds + self._overshoot_ns / 1_000_000_000)


class _StoppingStartRecordingTransport(_StartRecordingTransport):
    def __init__(self, clock: _Clock, stop: threading.Event) -> None:
        super().__init__(clock)
        self._stop = stop

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        outcome = super().capture(item)
        self._stop.set()
        return outcome


def test_resume_pacing_uses_actual_transport_start_after_worker_oversleep(
    tmp_path: Path,
) -> None:
    """Persisting planned admission permits restart at the same late physical instant."""
    interval_ns = 1_000_000_000
    clock = _OversleepClock(overshoot_ns=2_000_000_000)
    items = (
        _scheduled(0, not_before_monotonic_ns=interval_ns),
        _scheduled(1),
    )
    state = tmp_path / "state"
    stop = threading.Event()
    first = _StoppingStartRecordingTransport(clock, stop)
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        _runner(
            journal,
            items,
            first,
            clock=clock,
            per_host_limit=1,
            minimum_start_interval_ns=interval_ns,
            stop_requested=stop.is_set,
        ).run()

    resumed = _StartRecordingTransport(clock)
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        _runner(
            journal,
            items,
            resumed,
            clock=clock,
            per_host_limit=1,
            minimum_start_interval_ns=interval_ns,
        ).run()
        transitions = tuple(entry.transition.value for entry in journal.replay())

    assert first.starts == [3_000_000_000]
    assert resumed.starts[0] - first.starts[0] >= interval_ns
    assert "TRANSPORT_STARTED" in transitions


def test_worker_oversleep_past_cycle_deadline_never_starts_transport(
    tmp_path: Path,
) -> None:
    """A pre-deadline admission cannot become a physical request after gate oversleep."""
    clock = _OversleepClock(overshoot_ns=1_000_000_000)
    item = _scheduled(0, not_before_monotonic_ns=500_000_000)
    state = tmp_path / "state"
    transport = _OutcomeTransport(_captured(item.identity))
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            transport,
            clock=clock,
            budget=_budget(elapsed_seconds=1),
        ).run()
        transitions = tuple(entry.transition for entry in journal.replay())

    assert report.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert report.request_starts == 0
    assert transport.calls == 0
    assert JournalTransition.TRANSPORT_STARTED not in transitions
    assert JournalTransition.ELAPSED_BUDGET_EXHAUSTED in transitions

    resumed = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        second = _runner(
            journal,
            (item,),
            resumed,
            budget=_budget(elapsed_seconds=1),
        ).run()
    assert second.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert resumed.calls == []


class _WorkerWallFailureClock(_Clock):
    """Fail only the worker's final pre-transport wall-clock admission read."""

    def now(self) -> datetime:
        if threading.current_thread().name.startswith("acquisition-capture"):
            message = "test-only worker admission fault"
            raise RuntimeError(message)
        return super().now()


def test_pretransport_admission_fault_is_interrupted_without_physical_marker(
    tmp_path: Path,
) -> None:
    """A known pre-transport worker fault cannot invent a physical terminal outcome."""
    item = _scheduled(0)
    transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(tmp_path / "state", item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            transport,
            clock=_WorkerWallFailureClock(),
        ).run()
        entries = journal.replay()

    assert report.result is AcquisitionCycleResult.INCOMPLETE_RETRYABLE
    assert transport.calls == []
    assert all(entry.transition is not JournalTransition.TRANSPORT_STARTED for entry in entries)
    assert entries[-1].payload == AdmissionFailedBeforeTransportPayload(
        attempt=1,
        retry_not_before="2026-09-02T00:00:00+00:00",
    )


def test_proven_no_transport_fault_preserves_one_start_budget_for_resume(
    tmp_path: Path,
) -> None:
    """A proved no-call admission fault cannot consume request or redirect budget."""
    item = _scheduled(0)
    state = tmp_path / "state"
    first_transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        first = _runner(
            journal,
            (item,),
            first_transport,
            clock=_WorkerWallFailureClock(),
            budget=_budget(starts=1, redirects=1),
        ).run()
        first_entries = journal.replay()

    assert first.result is AcquisitionCycleResult.INCOMPLETE_RETRYABLE
    assert first.request_starts == 0
    assert first_transport.calls == []
    assert first_entries[-1].transition.value == "ADMISSION_FAILED_BEFORE_TRANSPORT"

    resumed_transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        resumed = _runner(
            journal,
            (item,),
            resumed_transport,
            budget=_budget(starts=1, redirects=1),
        ).run()
        resumed_entries = journal.replay()

    assert resumed.result is AcquisitionCycleResult.COMPLETE
    assert resumed.request_starts == 1
    assert resumed_transport.calls == [item.identity.work_item_id]
    starts = tuple(
        entry.payload for entry in resumed_entries if entry.transition is JournalTransition.STARTED
    )
    assert tuple(payload.attempt for payload in starts if type(payload) is StartedPayload) == (
        1,
        2,
    )


def test_proven_no_transport_at_attempt_ceiling_is_truthfully_exhausted(
    tmp_path: Path,
) -> None:
    """A marker-free failure with no permitted retry cannot report retryable work."""
    item = _scheduled(0)
    transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(tmp_path / "state", item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            transport,
            clock=_WorkerWallFailureClock(),
            budget=_budget(starts=1, redirects=1),
            maximum_attempts_per_item=1,
        ).run()
        entries = journal.replay()

    assert report.result is AcquisitionCycleResult.RETRY_EXHAUSTED
    assert report.request_starts == 0
    assert transport.calls == []
    assert tuple(entry.transition for entry in entries)[-2:] == (
        JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
        JournalTransition.RETRY_EXHAUSTED,
    )


def test_ambiguous_modern_orphan_remains_conservatively_charged(
    tmp_path: Path,
) -> None:
    """An unobserved worker may have called transport and must retain its full debit."""
    item = _scheduled(0)
    state = tmp_path / "state"
    cycle_started_at_epoch_us = 1_788_307_200_000_000
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        journal.append(
            item.identity,
            JournalTransition.DISCOVERED,
            DiscoveredPayload(cycle_started_at_epoch_us),
        )
        journal.append(
            item.identity,
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            CycleSafetyProfilePayload(
                schema_id="asklegal.acquisition-cycle-safety-profile",
                schema_version="1.0.0",
                maximum_starts=1,
                maximum_retained_bytes=100,
                maximum_elapsed_seconds=60,
                maximum_redirects=1,
                per_host_limit=1,
                minimum_start_interval_ns=0,
                maximum_attempts_per_item=2,
                maximum_redirects_per_start=1,
                cycle_started_at_epoch_us=cycle_started_at_epoch_us,
            ),
        )
        journal.append(
            item.identity,
            JournalTransition.STARTED,
            StartedPayload(
                attempt=1,
                started_at_epoch_us=cycle_started_at_epoch_us,
                host_not_before_epoch_us=cycle_started_at_epoch_us,
                reserved_redirects=1,
            ),
        )

    transport = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            transport,
            budget=_budget(starts=1, redirects=1),
            per_host_limit=1,
        ).run()
        entries = journal.replay()

    assert report.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert report.request_starts == 1
    assert transport.calls == []
    assert entries[-1].payload == RetryableFailurePayload(
        attempt=1,
        failure_code=AcquisitionFailureCode.WORKER_INTERRUPTED,
        retry_not_before="2026-09-02T00:00:00+00:00",
    )


def test_modern_orphan_recovery_preserves_the_later_durable_host_floor(
    tmp_path: Path,
) -> None:
    """Current-wall recovery cannot shorten the originating modern host deadline."""
    item = _scheduled(0)
    state = tmp_path / "state"
    clock = _Clock()
    cycle_started_at_epoch_us = 1_788_307_200_000_000
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        journal.append(
            item.identity,
            JournalTransition.DISCOVERED,
            DiscoveredPayload(cycle_started_at_epoch_us),
        )
        journal.append(
            item.identity,
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            CycleSafetyProfilePayload(
                schema_id="asklegal.acquisition-cycle-safety-profile",
                schema_version="1.0.0",
                maximum_starts=2,
                maximum_retained_bytes=100,
                maximum_elapsed_seconds=60,
                maximum_redirects=2,
                per_host_limit=1,
                minimum_start_interval_ns=1_000_000_000,
                maximum_attempts_per_item=2,
                maximum_redirects_per_start=1,
                cycle_started_at_epoch_us=cycle_started_at_epoch_us,
            ),
        )
        journal.append(
            item.identity,
            JournalTransition.STARTED,
            StartedPayload(
                attempt=1,
                started_at_epoch_us=cycle_started_at_epoch_us,
                host_not_before_epoch_us=cycle_started_at_epoch_us + 2_000_000,
                reserved_redirects=1,
            ),
        )

    transport = _StartRecordingTransport(clock)
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        report = _runner(
            journal,
            (item,),
            transport,
            clock=clock,
            budget=_budget(starts=2, redirects=2),
            per_host_limit=1,
            minimum_start_interval_ns=1_000_000_000,
        ).run()
        entries = journal.replay()

    interruption = next(
        entry.payload
        for entry in entries
        if entry.transition is JournalTransition.RETRYABLE_FAILURE
    )
    assert interruption == RetryableFailurePayload(
        attempt=1,
        failure_code=AcquisitionFailureCode.WORKER_INTERRUPTED,
        retry_not_before="2026-09-02T00:00:02+00:00",
    )
    assert report.result is AcquisitionCycleResult.COMPLETE
    assert report.request_starts == 2
    assert transport.starts == [2_000_000_000]


def test_cycle_safety_profile_drift_cannot_reopen_a_budget_stopped_cycle(
    tmp_path: Path,
) -> None:
    """Increasing a persisted request ceiling must fail before a second transport effect."""
    items = tuple(_scheduled(index) for index in range(2))
    state = tmp_path / "state"
    with LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal:
        first = _runner(
            journal,
            items,
            _InterruptingTransport(threading.Event()),
            budget=_budget(starts=1),
            per_host_limit=1,
        ).run()
    assert first.result is AcquisitionCycleResult.BUDGET_EXHAUSTED

    resumed = _InterruptingTransport(threading.Event())
    with (
        LocalAcquisitionJournal(state, items[0].identity.cycle_id) as journal,
        pytest.raises(ResumableAcquisitionError, match="CYCLE_SAFETY_PROFILE_DRIFT"),
    ):
        _runner(
            journal,
            items,
            resumed,
            budget=_budget(starts=2),
            per_host_limit=1,
        ).run()
    assert resumed.calls == []


def test_ordinary_terminal_unavailable_has_nonretryable_incomplete_result(
    tmp_path: Path,
) -> None:
    """A durable terminal source absence cannot be projected as retryable progress."""
    item = _scheduled(0)
    outcome = CaptureOutcome(
        work_item_id=item.identity.work_item_id,
        transition=JournalTransition.TERMINAL_UNAVAILABLE,
        status_code=None,
        media_type=None,
        final_url=None,
        body_length=0,
        body_fingerprint=None,
        object_ref=None,
        failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE.value,
        retry_not_before=None,
        read_back_verified=False,
        redirect_chain=(),
    )
    state = tmp_path / "state"
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        first = _runner(journal, (item,), _OutcomeTransport(outcome)).run()
    assert first.result.value == "INCOMPLETE_TERMINAL"

    resumed = _InterruptingTransport(threading.Event())
    with LocalAcquisitionJournal(state, item.identity.cycle_id) as journal:
        second = _runner(journal, (item,), resumed).run()
    assert second.result.value == "INCOMPLETE_TERMINAL"
    assert resumed.calls == []


def test_offline_import_is_reverified_and_completed_without_transport(tmp_path: Path) -> None:
    """Imported evidence is re-read but never re-requested by the shared runner."""
    scheduled = _scheduled(0)
    item = scheduled.identity
    profile = _cycle_profile()
    transport = _ExplodingCaptureTransport()
    verifier = _RetainedVerifier()
    with LocalAcquisitionJournal(tmp_path / "state", item.cycle_id) as journal:
        journal.append_many(
            (
                (
                    item,
                    JournalTransition.DISCOVERED,
                    DiscoveredPayload(profile.cycle_started_at_epoch_us),
                ),
                (item, JournalTransition.CYCLE_SAFETY_PROFILE_BOUND, profile),
                (
                    item,
                    JournalTransition.IMPORTED_CAPTURE_VERIFIED,
                    ImportedCaptureVerifiedPayload(
                        source_attempt_id="judiciary-retained-fixture",
                        source_report_fingerprint="sha256:" + "a" * 64,
                        authority_manifest_fingerprint="sha256:" + "b" * 64,
                        execution_authorization_fingerprint="sha256:" + "c" * 64,
                        status=200,
                        media_type=item.media_type,
                        final_url=item.locator,
                        body_length=item.max_bytes,
                        content_fingerprint="sha256:" + "d" * 64,
                        object_ref="objects/retained.bin",
                        read_back_verified=True,
                    ),
                ),
            )
        )
        report = _runner(
            journal,
            (scheduled,),
            transport,
            retained_verifier=verifier,
        ).run()

    assert report.result is AcquisitionCycleResult.COMPLETE
    assert report.request_starts == 0
    assert transport.calls == 0
    assert len(verifier.calls) == 1
