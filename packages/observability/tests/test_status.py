# ruff: noqa: D100, D103, EM101, INP001, PLR0913, PLR2004, PLW1641, RUF005, S101, SLOT001, TRY003

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta

import pytest
from asklegal_observability.events import (
    OPERATIONAL_CATEGORY_ORDER,
    ObservabilityError,
    ObservabilityErrorCode,
    OperationalAlertCode,
    OperationalCategory,
    OperationalEmitter,
    OperationalEvent,
    OperationalEventCode,
    OperationalStatusScope,
    OperationalStreamSpec,
    alert_code_for,
    allowed_emitters,
    build_event_observation,
    build_operational_event,
    build_status_scope,
    build_stream_spec,
    clear_code_for,
    derive_operational_fingerprint,
)
from asklegal_observability.status import (
    HKV1FamilyCycleResult,
    HKV1FamilyProgress,
    HKV1ProgressSnapshot,
    HKV1ProgressStatus,
    OperationalAlertProjection,
    OperationalStatusSnapshot,
    OperationalStreamStatus,
    aggregate_hk_v1_progress,
    aggregate_operational_status,
    parse_operational_status,
    serialize_hk_v1_progress,
    serialize_operational_status,
)

NOW = datetime(2026, 8, 27, 1, 2, 3, tzinfo=UTC)
FP_A = "sha256:" + "a" * 64
FP_B = "sha256:" + "b" * 64


def _scope() -> OperationalStatusScope:
    streams = tuple(
        build_stream_spec(
            category,
            allowed_emitters(category)[0],
            f"sha256:{index:064x}",
        )
        for index, category in enumerate(OPERATIONAL_CATEGORY_ORDER, start=1)
    )
    return build_status_scope(streams)


def _event(
    scope: OperationalStatusScope,
    stream: OperationalStreamSpec,
    sequence: int = 1,
    *,
    clear: bool = True,
    occurred_at: datetime = NOW,
) -> OperationalEvent:
    code = clear_code_for(stream.category) if clear else alert_code_for(stream.category)
    observation = build_event_observation(sequence, occurred_at, code)
    return build_operational_event(scope, stream, observation)


def _all_events(
    scope: OperationalStatusScope, *, clear: bool = True
) -> tuple[OperationalEvent, ...]:
    return tuple(_event(scope, stream, clear=clear) for stream in scope.streams)


def _family_progress(
    family: str,
    *,
    discovered: int = 3,
    verified: int = 3,
    retryable: int = 0,
    rejected: int = 0,
    terminal: int = 3,
    active: int = 0,
    queued: int = 0,
    cycle_result: HKV1FamilyCycleResult | None = HKV1FamilyCycleResult.COMPLETE,
) -> HKV1FamilyProgress:
    return HKV1FamilyProgress(
        material_family=family,
        cycle_id=f"cyc_20260827_{family.lower()}",
        discovered_count=discovered,
        verified_count=verified,
        retryable_count=retryable,
        rejected_count=rejected,
        terminal_count=terminal,
        active_count=active,
        queued_count=queued,
        retained_byte_count=123,
        journal_head_fingerprint=FP_A if family == "CASES" else FP_B,
        last_progress_at=NOW,
        cycle_result=cycle_result,
        result_fingerprint=(None if cycle_result is None else FP_A),
    )


def test_two_family_progress_is_exact_closed_and_has_no_percentage() -> None:
    snapshot = aggregate_hk_v1_progress(
        (_family_progress("LEGISLATION"), _family_progress("CASES")),
        NOW,
    )

    assert type(snapshot) is HKV1ProgressSnapshot
    assert snapshot.status is HKV1ProgressStatus.COMPLETE
    assert tuple(item.material_family for item in snapshot.families) == (
        "CASES",
        "LEGISLATION",
    )
    serialized = serialize_hk_v1_progress(snapshot)
    assert set(serialized) == {"as_of", "status", "families", "fingerprint"}
    assert "percent" not in repr(serialized).lower()
    assert "HKEX" not in repr(serialized)


def test_retryable_work_is_progress_but_never_success() -> None:
    snapshot = aggregate_hk_v1_progress(
        (
            _family_progress("CASES"),
            _family_progress(
                "LEGISLATION",
                discovered=5,
                verified=3,
                retryable=1,
                terminal=3,
                queued=1,
                cycle_result=HKV1FamilyCycleResult.INCOMPLETE_RETRYABLE,
            ),
        ),
        NOW,
    )

    assert snapshot.status is HKV1ProgressStatus.INCOMPLETE_RETRYABLE
    assert serialize_hk_v1_progress(snapshot)["status"] == "INCOMPLETE_RETRYABLE"


def test_rejected_work_is_incomplete_terminal() -> None:
    snapshot = aggregate_hk_v1_progress(
        (
            _family_progress(
                "CASES",
                discovered=3,
                verified=2,
                rejected=1,
                terminal=3,
                cycle_result=HKV1FamilyCycleResult.INCOMPLETE_TERMINAL,
            ),
            _family_progress("LEGISLATION"),
        ),
        NOW,
    )
    assert snapshot.status is HKV1ProgressStatus.INCOMPLETE_TERMINAL


def test_zero_work_is_not_started_and_never_complete() -> None:
    snapshot = aggregate_hk_v1_progress(
        (
            _family_progress("CASES", discovered=0, verified=0, terminal=0, cycle_result=None),
            _family_progress(
                "LEGISLATION", discovered=0, verified=0, terminal=0, cycle_result=None
            ),
        ),
        NOW,
    )

    assert snapshot.status is HKV1ProgressStatus.NOT_STARTED


def test_terminal_counts_without_sealed_family_results_are_never_complete() -> None:
    snapshot = aggregate_hk_v1_progress(
        (
            _family_progress("CASES", cycle_result=None),
            _family_progress("LEGISLATION", cycle_result=None),
        ),
        NOW,
    )

    assert snapshot.status is HKV1ProgressStatus.INCOMPLETE_RETRYABLE


@pytest.mark.parametrize(
    "families",
    [
        (_family_progress("CASES"),),
        (_family_progress("CASES"), _family_progress("CASES")),
        (_family_progress("CASES"), _family_progress("HKEX")),
        (
            _family_progress(
                "CASES",
                discovered=3,
                verified=3,
                terminal=2,
            ),
            _family_progress("LEGISLATION"),
        ),
    ],
)
def test_two_family_progress_rejects_partial_duplicate_hkex_or_bad_arithmetic(
    families: tuple[HKV1FamilyProgress, ...],
) -> None:
    with pytest.raises(ObservabilityError):
        aggregate_hk_v1_progress(families, NOW)


def test_progress_serializer_revalidates_fingerprint_and_derived_status() -> None:
    snapshot = aggregate_hk_v1_progress(
        (_family_progress("CASES"), _family_progress("LEGISLATION")),
        NOW,
    )
    with pytest.raises(ObservabilityError):
        serialize_hk_v1_progress(replace(snapshot, fingerprint=FP_A))
    with pytest.raises(ObservabilityError):
        serialize_hk_v1_progress(replace(snapshot, status=HKV1ProgressStatus.INCOMPLETE_RETRYABLE))


def test_all_clear_complete_scope_is_narrowly_healthy() -> None:
    scope = _scope()
    snapshot = aggregate_operational_status(scope, _all_events(scope), NOW)
    assert snapshot.complete is True
    assert snapshot.healthy is True
    assert snapshot.alerts == ()
    assert len(snapshot.streams) == 12
    assert snapshot.fingerprint.startswith("sha256:")


def test_source_failure_projects_exact_blocker() -> None:
    scope = _scope()
    source = next(
        stream for stream in scope.streams if stream.category is OperationalCategory.SOURCE
    )
    event_tuple = tuple(
        _event(scope, stream, clear=stream is not source) for stream in scope.streams
    )
    snapshot = aggregate_operational_status(scope, event_tuple, NOW)
    assert snapshot.complete is True
    assert snapshot.healthy is False
    assert len(snapshot.alerts) == 1
    alert = snapshot.alerts[0]
    assert alert.code is OperationalAlertCode.SOURCE_CYCLE_BLOCKED
    assert alert.event_id is not None
    assert alert.occurred_at == NOW


@pytest.mark.parametrize("category", OPERATIONAL_CATEGORY_ORDER)
def test_each_category_projects_its_closed_alert(category: OperationalCategory) -> None:
    scope = _scope()
    selected = next(stream for stream in scope.streams if stream.category is category)
    event_tuple = tuple(
        _event(scope, stream, clear=stream is not selected) for stream in scope.streams
    )
    snapshot = aggregate_operational_status(scope, event_tuple, NOW)
    assert tuple(alert.code for alert in snapshot.alerts) == (
        OperationalAlertCode(alert_code_for(category).value),
    )


def test_missing_stream_is_incomplete_unhealthy_and_deterministically_alerted() -> None:
    scope = _scope()
    snapshot = aggregate_operational_status(scope, _all_events(scope)[:-1], NOW)
    assert snapshot.complete is False
    assert snapshot.healthy is False
    assert snapshot.alerts[-1].code is OperationalAlertCode.OPERATIONAL_STREAM_MISSING
    assert snapshot.alerts[-1].event_id is None
    assert snapshot.alerts[-1].occurred_at is None
    missing_status = snapshot.streams[-1]
    assert missing_status.observed is False
    assert missing_status.latest_event_id is None


def test_alert_clear_alert_preserves_last_success_and_failure() -> None:
    scope = _scope()
    selected = scope.streams[0]
    first_failure = _event(scope, selected, 1, clear=False, occurred_at=NOW)
    success = _event(scope, selected, 2, clear=True, occurred_at=NOW + timedelta(seconds=1))
    last_failure = _event(scope, selected, 3, clear=False, occurred_at=NOW + timedelta(seconds=2))
    other = tuple(_event(scope, stream) for stream in scope.streams[1:])
    snapshot = aggregate_operational_status(
        scope,
        other + (last_failure, first_failure, success),
        NOW + timedelta(seconds=2),
    )
    status = snapshot.streams[0]
    assert status.latest_event_id == last_failure.event_id
    assert status.last_success_event_id == success.event_id
    assert status.last_success_at == success.occurred_at
    assert status.last_failure_event_id == last_failure.event_id
    assert status.last_failure_at == last_failure.occurred_at
    assert snapshot.alerts[0].event_id == last_failure.event_id


def test_latest_clear_resolves_previous_alert() -> None:
    scope = _scope()
    selected = scope.streams[0]
    failure = _event(scope, selected, 1, clear=False)
    success = _event(scope, selected, 2, clear=True, occurred_at=NOW + timedelta(seconds=1))
    snapshot = aggregate_operational_status(
        scope,
        tuple(_event(scope, stream) for stream in scope.streams[1:]) + (success, failure),
        NOW + timedelta(seconds=1),
    )
    assert snapshot.complete is True
    assert snapshot.healthy is True
    assert snapshot.alerts == ()


def test_input_order_and_exact_replay_do_not_change_snapshot() -> None:
    scope = _scope()
    event_tuple = _all_events(scope)
    expected = aggregate_operational_status(scope, event_tuple, NOW)
    reordered = aggregate_operational_status(scope, tuple(reversed(event_tuple)), NOW)
    replayed = aggregate_operational_status(scope, event_tuple + event_tuple + event_tuple, NOW)
    assert reordered == expected
    assert replayed == expected
    assert serialize_operational_status(replayed) == serialize_operational_status(expected)


def test_same_sequence_different_content_conflicts() -> None:
    scope = _scope()
    stream = scope.streams[0]
    clear = _event(scope, stream, 1, clear=True)
    alert = _event(scope, stream, 1, clear=False)
    with pytest.raises(ObservabilityError) as caught:
        aggregate_operational_status(scope, (clear, alert), NOW)
    assert caught.value.code is ObservabilityErrorCode.STREAM_SEQUENCE_CONFLICT


def test_higher_sequence_with_earlier_timestamp_is_time_regression() -> None:
    scope = _scope()
    stream = scope.streams[0]
    first = _event(scope, stream, 1, occurred_at=NOW)
    second = _event(scope, stream, 2, occurred_at=NOW - timedelta(seconds=1))
    with pytest.raises(ObservabilityError) as caught:
        aggregate_operational_status(scope, (second, first), NOW)
    assert caught.value.code is ObservabilityErrorCode.STREAM_TIME_REGRESSION


def test_equal_timestamp_for_higher_sequence_is_permitted() -> None:
    scope = _scope()
    stream = scope.streams[0]
    first = _event(scope, stream, 1, clear=False)
    second = _event(scope, stream, 2, clear=True)
    snapshot = aggregate_operational_status(scope, (second, first), NOW)
    assert snapshot.streams[0].latest_event_id == second.event_id


def test_event_after_explicit_as_of_rejects_without_wall_clock() -> None:
    scope = _scope()
    event = _event(scope, scope.streams[0], occurred_at=NOW + timedelta(seconds=1))
    with pytest.raises(ObservabilityError) as caught:
        aggregate_operational_status(scope, (event,), NOW)
    assert caught.value.code is ObservabilityErrorCode.EVENT_AFTER_AS_OF


def test_aggregation_rejects_cross_scope_undeclared_and_forged_events() -> None:
    scope = _scope()
    altered = list(scope.streams)
    altered[0] = build_stream_spec(
        altered[0].category,
        altered[0].emitter,
        "sha256:" + "f" * 64,
    )
    other_scope = build_status_scope(tuple(altered))
    cross_scope = _event(other_scope, other_scope.streams[0])
    with pytest.raises(ObservabilityError) as cross:
        aggregate_operational_status(scope, (cross_scope,), NOW)
    assert cross.value.code is ObservabilityErrorCode.CROSS_SCOPE_EVENT

    valid = _event(scope, scope.streams[0])
    object.__setattr__(valid, "event_id", "sha256:" + "0" * 64)
    with pytest.raises(ObservabilityError) as forged:
        aggregate_operational_status(scope, (valid,), NOW)
    assert forged.value.code is ObservabilityErrorCode.INVALID_EVENT


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("stream_id", "sha256:" + "f" * 64),
        ("category", OperationalCategory.RESOURCE),
        ("emitter", OperationalEmitter.TELEMETRY_COLLECTOR),
        ("code", OperationalEventCode.RESOURCE_EXHAUSTED),
        ("scope_fingerprint", "sha256:" + "f" * 64),
        ("occurred_at", NOW.replace(microsecond=1)),
        ("sequence", True),
        ("fingerprint", "sha256:" + "f" * 64),
    ],
)
def test_aggregation_revalidates_every_event_field(field_name: str, value: object) -> None:
    scope = _scope()
    event = _event(scope, scope.streams[0])
    object.__setattr__(event, field_name, value)
    with pytest.raises(ObservabilityError):
        aggregate_operational_status(scope, (event,), NOW)


class _Hostile:
    @property
    def category(self) -> object:
        raise AssertionError("hostile property executed")

    def __eq__(self, other: object) -> bool:
        raise AssertionError("hostile equality executed")


class _HostileTuple(tuple[object, ...]):
    def __iter__(self) -> Iterator[object]:
        raise AssertionError("hostile iterator executed")


def test_hostile_event_and_container_reject_without_execution() -> None:
    scope = _scope()
    with pytest.raises(ObservabilityError):
        aggregate_operational_status(scope, _HostileTuple(), NOW)
    with pytest.raises(ObservabilityError):
        aggregate_operational_status(scope, (_Hostile(),), NOW)

    event = _event(scope, scope.streams[0])
    object.__setattr__(event, "category", _Hostile())
    with pytest.raises(ObservabilityError):
        aggregate_operational_status(scope, (event,), NOW)


def test_snapshot_serialization_is_closed_ordered_and_secret_free() -> None:
    scope = _scope()
    snapshot = aggregate_operational_status(scope, _all_events(scope), NOW)
    serialized = serialize_operational_status(snapshot)
    assert set(serialized) == {
        "scope_fingerprint",
        "as_of",
        "complete",
        "healthy",
        "streams",
        "alerts",
        "fingerprint",
    }
    assert type(serialized["streams"]) is tuple
    assert type(serialized["alerts"]) is tuple
    serialized_streams = serialized["streams"]
    assert type(serialized_streams) is tuple
    first_stream = serialized_streams[0]
    assert type(first_stream) is dict
    assert len(first_stream) == 12
    assert all(
        key in first_stream
        for key in (
            "stream_id",
            "category",
            "emitter",
            "observed",
            "latest_sequence",
            "latest_code",
            "latest_event_id",
            "latest_at",
            "last_success_event_id",
            "last_success_at",
            "last_failure_event_id",
            "last_failure_at",
        )
    )
    assert all(
        term not in repr(serialized).lower()
        for term in (
            "password",
            "connection_string",
            "token",
            "exception",
            "payload",
            "legal_text",
            "person_name",
        )
    )
    forbidden = {"reason", "detail", "metadata", "payload", "body", "exception"}
    assert not forbidden & {field.name for field in fields(OperationalStreamStatus)}
    assert not forbidden & {field.name for field in fields(OperationalAlertProjection)}
    assert not forbidden & {field.name for field in fields(OperationalStatusSnapshot)}


def test_serialized_operational_status_round_trips_through_strict_parser() -> None:
    """The retained primitive is independently reconstructible without live objects."""
    snapshot = aggregate_operational_status(_scope(), _all_events(_scope()), NOW)
    serialized = serialize_operational_status(snapshot)

    assert parse_operational_status(serialized) == snapshot

    forged = dict(serialized)
    forged["healthy"] = False
    with pytest.raises(ObservabilityError):
        parse_operational_status(forged)


def test_mutated_scope_and_as_of_reject_cause_free() -> None:
    scope = _scope()
    object.__setattr__(scope, "scope_fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(ObservabilityError) as invalid_scope:
        aggregate_operational_status(scope, (), NOW)
    assert invalid_scope.value.code is ObservabilityErrorCode.INVALID_SCOPE
    assert invalid_scope.value.__cause__ is None
    assert invalid_scope.value.__context__ is None

    valid_scope = _scope()
    with pytest.raises(ObservabilityError) as invalid_time:
        aggregate_operational_status(valid_scope, (), NOW.replace(microsecond=1))
    assert invalid_time.value.code is ObservabilityErrorCode.INVALID_AS_OF


def test_refingerprinted_snapshot_rejects_reordered_streams() -> None:
    scope = _scope()
    snapshot = aggregate_operational_status(scope, _all_events(scope), NOW)
    primitive = serialize_operational_status(snapshot)
    streams = tuple(reversed(snapshot.streams))
    primitive_streams = tuple(reversed(primitive["streams"]))
    payload = {
        "scope_fingerprint": primitive["scope_fingerprint"],
        "as_of": primitive["as_of"],
        "complete": primitive["complete"],
        "healthy": primitive["healthy"],
        "streams": primitive_streams,
        "alerts": primitive["alerts"],
    }
    fingerprint = derive_operational_fingerprint(
        ("operational-status-snapshot-v1", payload),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    forged = replace(snapshot, streams=streams, fingerprint=fingerprint)
    with pytest.raises(ObservabilityError) as caught:
        serialize_operational_status(forged)
    assert caught.value.code is ObservabilityErrorCode.INVALID_EVENT


def test_refingerprinted_snapshot_cannot_claim_healthy_with_blocker() -> None:
    scope = _scope()
    source = scope.streams[0]
    events = tuple(_event(scope, stream, clear=stream is not source) for stream in scope.streams)
    snapshot = aggregate_operational_status(scope, events, NOW)
    primitive = serialize_operational_status(snapshot)
    payload = {
        "scope_fingerprint": primitive["scope_fingerprint"],
        "as_of": primitive["as_of"],
        "complete": primitive["complete"],
        "healthy": True,
        "streams": primitive["streams"],
        "alerts": primitive["alerts"],
    }
    fingerprint = derive_operational_fingerprint(
        ("operational-status-snapshot-v1", payload),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    forged = replace(snapshot, healthy=True, fingerprint=fingerprint)
    with pytest.raises(ObservabilityError) as caught:
        serialize_operational_status(forged)
    assert caught.value.code is ObservabilityErrorCode.INVALID_EVENT


def test_refingerprinted_snapshot_rejects_latest_event_after_as_of() -> None:
    scope = _scope()
    snapshot = aggregate_operational_status(scope, _all_events(scope), NOW)
    primitive = serialize_operational_status(snapshot)
    earlier = NOW - timedelta(seconds=1)
    payload = {
        "scope_fingerprint": primitive["scope_fingerprint"],
        "as_of": earlier.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "complete": primitive["complete"],
        "healthy": primitive["healthy"],
        "streams": primitive["streams"],
        "alerts": primitive["alerts"],
    }
    fingerprint = derive_operational_fingerprint(
        ("operational-status-snapshot-v1", payload),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    forged = replace(snapshot, as_of=earlier, fingerprint=fingerprint)
    with pytest.raises(ObservabilityError) as caught:
        serialize_operational_status(forged)
    assert caught.value.code is ObservabilityErrorCode.INVALID_EVENT


def test_refingerprinted_snapshot_rejects_history_after_latest_event() -> None:
    scope = _scope()
    source = scope.streams[0]
    failure = _event(scope, source, 1, clear=False, occurred_at=NOW)
    success = _event(scope, source, 2, clear=True, occurred_at=NOW + timedelta(seconds=1))
    other_events = tuple(
        _event(scope, stream, occurred_at=NOW + timedelta(seconds=1))
        for stream in scope.streams[1:]
    )
    as_of = NOW + timedelta(seconds=1)
    snapshot = aggregate_operational_status(scope, (failure, success, *other_events), as_of)
    impossible_time = NOW + timedelta(seconds=10)
    status = replace(snapshot.streams[0], last_failure_at=impossible_time)
    statuses = (status, *snapshot.streams[1:])
    primitive = serialize_operational_status(snapshot)
    first_stream = dict(primitive["streams"][0])
    first_stream["last_failure_at"] = impossible_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    primitive_streams = (first_stream, *primitive["streams"][1:])
    payload = {
        "scope_fingerprint": primitive["scope_fingerprint"],
        "as_of": primitive["as_of"],
        "complete": primitive["complete"],
        "healthy": primitive["healthy"],
        "streams": primitive_streams,
        "alerts": primitive["alerts"],
    }
    fingerprint = derive_operational_fingerprint(
        ("operational-status-snapshot-v1", payload),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    forged = replace(snapshot, streams=statuses, fingerprint=fingerprint)
    with pytest.raises(ObservabilityError) as caught:
        serialize_operational_status(forged)
    assert caught.value.code is ObservabilityErrorCode.INVALID_EVENT


def test_refingerprinted_snapshot_rejects_one_event_as_success_and_failure() -> None:
    scope = _scope()
    source = scope.streams[0]
    failure = _event(scope, source, 1, clear=False, occurred_at=NOW)
    success = _event(scope, source, 2, clear=True, occurred_at=NOW + timedelta(seconds=1))
    other_events = tuple(
        _event(scope, stream, occurred_at=NOW + timedelta(seconds=1))
        for stream in scope.streams[1:]
    )
    snapshot = aggregate_operational_status(
        scope,
        (failure, success, *other_events),
        NOW + timedelta(seconds=1),
    )
    status = snapshot.streams[0]
    assert status.last_success_event_id is not None
    forged_status = replace(status, last_failure_event_id=status.last_success_event_id)
    statuses = (forged_status, *snapshot.streams[1:])
    primitive = serialize_operational_status(snapshot)
    first_stream = dict(primitive["streams"][0])
    first_stream["last_failure_event_id"] = status.last_success_event_id
    primitive_streams = (first_stream, *primitive["streams"][1:])
    payload = {
        "scope_fingerprint": primitive["scope_fingerprint"],
        "as_of": primitive["as_of"],
        "complete": primitive["complete"],
        "healthy": primitive["healthy"],
        "streams": primitive_streams,
        "alerts": primitive["alerts"],
    }
    fingerprint = derive_operational_fingerprint(
        ("operational-status-snapshot-v1", payload),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    forged = replace(snapshot, streams=statuses, fingerprint=fingerprint)
    with pytest.raises(ObservabilityError) as caught:
        serialize_operational_status(forged)
    assert caught.value.code is ObservabilityErrorCode.INVALID_EVENT
