"""Deterministic current blocker projection over a closed operational scope."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Never, TypedDict, TypeGuard, TypeIs

from .events import (
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
    canonical_operational_time,
    clear_code_for,
    derive_operational_fingerprint,
    event_alert_code_for,
    is_canonical_operational_time,
    is_opaque_fingerprint,
    validated_event_snapshot,
    validated_scope_streams,
    validated_stream_snapshot,
)

_CATEGORY_INDEX = {category: index for index, category in enumerate(OPERATIONAL_CATEGORY_ORDER)}
_HK_V1_FAMILIES = ("CASES", "LEGISLATION")
_HK_V1_CYCLE_ID = re.compile(r"cyc_[a-z0-9][a-z0-9_]{0,126}", re.ASCII)


class HKV1FamilyCycleResult(StrEnum):
    """Closed acquisition-family result retained by the owning worker."""

    COMPLETE = "COMPLETE"
    NO_CHANGE = "NO_CHANGE"
    INCOMPLETE_RETRYABLE = "INCOMPLETE_RETRYABLE"
    INCOMPLETE_TERMINAL = "INCOMPLETE_TERMINAL"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    EVIDENCE_INTEGRITY_FAILURE = "EVIDENCE_INTEGRITY_FAILURE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


class HKV1ProgressStatus(StrEnum):
    """Closed truthful status for the complete two-family work set."""

    NOT_STARTED = "NOT_STARTED"
    COMPLETE = "COMPLETE"
    INCOMPLETE_RETRYABLE = "INCOMPLETE_RETRYABLE"
    INCOMPLETE_TERMINAL = "INCOMPLETE_TERMINAL"


@dataclass(frozen=True, slots=True)
class HKV1FamilyProgress:
    """Operator-visible exact counts for one V1 material family."""

    material_family: str
    cycle_id: str
    discovered_count: int
    verified_count: int
    retryable_count: int
    rejected_count: int
    terminal_count: int
    active_count: int
    queued_count: int
    retained_byte_count: int
    journal_head_fingerprint: str
    last_progress_at: datetime | None
    cycle_result: HKV1FamilyCycleResult | None
    result_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class HKV1ProgressSnapshot:
    """Fingerprint-bound two-family progress without percentage claims."""

    as_of: datetime
    status: HKV1ProgressStatus
    families: tuple[HKV1FamilyProgress, ...]
    fingerprint: str


class HKV1FamilyProgressPrimitive(TypedDict):
    """Closed serialized per-family progress shape."""

    material_family: str
    cycle_id: str
    discovered_count: int
    verified_count: int
    retryable_count: int
    rejected_count: int
    terminal_count: int
    active_count: int
    queued_count: int
    retained_byte_count: int
    journal_head_fingerprint: str
    last_progress_at: str | None
    cycle_result: str | None
    result_fingerprint: str | None


class HKV1ProgressPrimitive(TypedDict):
    """Closed serialized two-family progress shape."""

    as_of: str
    status: str
    families: tuple[HKV1FamilyProgressPrimitive, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class OperationalStreamStatus:
    """Latest and last-clear/blocker facts for one expected stream."""

    stream_id: str
    category: OperationalCategory
    emitter: OperationalEmitter
    observed: bool
    latest_sequence: int | None
    latest_code: OperationalEventCode | None
    latest_event_id: str | None
    latest_at: datetime | None
    last_success_event_id: str | None
    last_success_at: datetime | None
    last_failure_event_id: str | None
    last_failure_at: datetime | None


@dataclass(frozen=True, slots=True)
class OperationalAlertProjection:
    """One current blocker projection with no free-text detail."""

    code: OperationalAlertCode
    category: OperationalCategory
    stream_id: str
    event_id: str | None
    occurred_at: datetime | None


@dataclass(frozen=True, slots=True)
class OperationalStatusSnapshot:
    """Deterministic status for one exact scope at an explicit instant."""

    scope_fingerprint: str
    as_of: datetime
    complete: bool
    healthy: bool
    streams: tuple[OperationalStreamStatus, ...]
    alerts: tuple[OperationalAlertProjection, ...]
    fingerprint: str


class OperationalStreamPrimitive(TypedDict):
    """Closed serialized stream status shape."""

    stream_id: str
    category: str
    emitter: str
    observed: bool
    latest_sequence: int | None
    latest_code: str | None
    latest_event_id: str | None
    latest_at: str | None
    last_success_event_id: str | None
    last_success_at: str | None
    last_failure_event_id: str | None
    last_failure_at: str | None


class OperationalAlertPrimitive(TypedDict):
    """Closed serialized alert projection shape."""

    code: str
    category: str
    stream_id: str
    event_id: str | None
    occurred_at: str | None


class OperationalStatusPrimitive(TypedDict):
    """Closed serialized status snapshot shape."""

    scope_fingerprint: str
    as_of: str
    complete: bool
    healthy: bool
    streams: tuple[OperationalStreamPrimitive, ...]
    alerts: tuple[OperationalAlertPrimitive, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _EventFact:
    scope_fingerprint: str
    stream_id: str
    category: OperationalCategory
    emitter: OperationalEmitter
    sequence: int
    occurred_at: datetime
    code: OperationalEventCode
    event_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _SnapshotContent:
    scope_fingerprint: str
    as_of: datetime
    complete: bool
    healthy: bool
    streams: tuple[OperationalStreamStatus, ...]
    alerts: tuple[OperationalAlertProjection, ...]


def _fail(code: ObservabilityErrorCode) -> Never:
    raise ObservabilityError(code) from None


def _is_exact_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return type(value) is tuple


def _optional_fingerprint(value: object) -> bool:
    return value is None or is_opaque_fingerprint(value)


def _optional_time(value: object) -> bool:
    return value is None or is_canonical_operational_time(value)


def _validate_latest_status(status: OperationalStreamStatus) -> None:
    if not status.observed:
        return
    latest_code = status.latest_code
    if type(latest_code) is not OperationalEventCode or latest_code not in (
        clear_code_for(status.category),
        alert_code_for(status.category),
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if event_alert_code_for(latest_code) is None:
        if (
            status.last_success_event_id != status.latest_event_id
            or status.last_success_at != status.latest_at
        ):
            _fail(ObservabilityErrorCode.INVALID_EVENT)
    elif (
        status.last_failure_event_id != status.latest_event_id
        or status.last_failure_at != status.latest_at
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)


def _validated_status(status: OperationalStreamStatus) -> OperationalStreamStatus:
    if type(status) is not OperationalStreamStatus:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if (
        not is_opaque_fingerprint(status.stream_id)
        or type(status.category) is not OperationalCategory
        or type(status.emitter) is not OperationalEmitter
        or type(status.observed) is not bool
        or (
            status.latest_sequence is not None
            and (type(status.latest_sequence) is not int or status.latest_sequence <= 0)
        )
        or (status.latest_code is not None and type(status.latest_code) is not OperationalEventCode)
        or not _optional_fingerprint(status.latest_event_id)
        or not _optional_time(status.latest_at)
        or not _optional_fingerprint(status.last_success_event_id)
        or not _optional_time(status.last_success_at)
        or not _optional_fingerprint(status.last_failure_event_id)
        or not _optional_time(status.last_failure_at)
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    latest_fields = (
        status.latest_sequence,
        status.latest_code,
        status.latest_event_id,
        status.latest_at,
    )
    if status.observed:
        if any(value is None for value in latest_fields):
            _fail(ObservabilityErrorCode.INVALID_EVENT)
    elif any(value is not None for value in latest_fields):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if (status.last_success_event_id is None) is not (status.last_success_at is None) or (
        status.last_failure_event_id is None
    ) is not (status.last_failure_at is None):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if not status.observed and (
        status.last_success_event_id is not None or status.last_failure_event_id is not None
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if (
        status.last_success_event_id is not None
        and status.last_success_event_id == status.last_failure_event_id
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if status.emitter not in allowed_emitters(status.category):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    _validate_latest_status(status)
    return status


def _validated_alert(
    alert: OperationalAlertProjection,
) -> OperationalAlertProjection:
    if type(alert) is not OperationalAlertProjection:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if (
        type(alert.code) is not OperationalAlertCode
        or type(alert.category) is not OperationalCategory
        or not is_opaque_fingerprint(alert.stream_id)
        or not _optional_fingerprint(alert.event_id)
        or not _optional_time(alert.occurred_at)
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if (alert.event_id is None) is not (alert.occurred_at is None):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if alert.code is OperationalAlertCode.OPERATIONAL_STREAM_MISSING:
        if alert.event_id is not None:
            _fail(ObservabilityErrorCode.INVALID_EVENT)
    elif alert.event_id is None:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return alert


def _status_primitive(status: OperationalStreamStatus) -> OperationalStreamPrimitive:
    checked = _validated_status(status)
    return {
        "stream_id": checked.stream_id,
        "category": checked.category.value,
        "emitter": checked.emitter.value,
        "observed": checked.observed,
        "latest_sequence": checked.latest_sequence,
        "latest_code": (None if checked.latest_code is None else checked.latest_code.value),
        "latest_event_id": checked.latest_event_id,
        "latest_at": (
            None if checked.latest_at is None else canonical_operational_time(checked.latest_at)
        ),
        "last_success_event_id": checked.last_success_event_id,
        "last_success_at": (
            None
            if checked.last_success_at is None
            else canonical_operational_time(checked.last_success_at)
        ),
        "last_failure_event_id": checked.last_failure_event_id,
        "last_failure_at": (
            None
            if checked.last_failure_at is None
            else canonical_operational_time(checked.last_failure_at)
        ),
    }


def _alert_primitive(alert: OperationalAlertProjection) -> OperationalAlertPrimitive:
    checked = _validated_alert(alert)
    return {
        "code": checked.code.value,
        "category": checked.category.value,
        "stream_id": checked.stream_id,
        "event_id": checked.event_id,
        "occurred_at": (
            None if checked.occurred_at is None else canonical_operational_time(checked.occurred_at)
        ),
    }


def _snapshot_payload(
    content: _SnapshotContent,
) -> dict[str, object]:
    return {
        "scope_fingerprint": content.scope_fingerprint,
        "as_of": canonical_operational_time(content.as_of),
        "complete": content.complete,
        "healthy": content.healthy,
        "streams": tuple(_status_primitive(status) for status in content.streams),
        "alerts": tuple(_alert_primitive(alert) for alert in content.alerts),
    }


def _stream_status(
    stream: OperationalStreamSpec,
    ordered_events: tuple[_EventFact, ...],
) -> tuple[OperationalStreamStatus, OperationalAlertProjection | None]:
    category, emitter, _, stream_id = validated_stream_snapshot(stream)
    if not ordered_events:
        return (
            OperationalStreamStatus(
                stream_id=stream_id,
                category=category,
                emitter=emitter,
                observed=False,
                latest_sequence=None,
                latest_code=None,
                latest_event_id=None,
                latest_at=None,
                last_success_event_id=None,
                last_success_at=None,
                last_failure_event_id=None,
                last_failure_at=None,
            ),
            OperationalAlertProjection(
                OperationalAlertCode.OPERATIONAL_STREAM_MISSING,
                category,
                stream_id,
                None,
                None,
            ),
        )
    latest = ordered_events[-1]
    last_success: _EventFact | None = None
    last_failure: _EventFact | None = None
    for event in ordered_events:
        if event_alert_code_for(event.code) is None:
            last_success = event
        else:
            last_failure = event
    status = OperationalStreamStatus(
        stream_id=stream_id,
        category=category,
        emitter=emitter,
        observed=True,
        latest_sequence=latest.sequence,
        latest_code=latest.code,
        latest_event_id=latest.event_id,
        latest_at=latest.occurred_at,
        last_success_event_id=None if last_success is None else last_success.event_id,
        last_success_at=None if last_success is None else last_success.occurred_at,
        last_failure_event_id=None if last_failure is None else last_failure.event_id,
        last_failure_at=None if last_failure is None else last_failure.occurred_at,
    )
    latest_alert = event_alert_code_for(latest.code)
    alert = (
        None
        if latest_alert is None
        else OperationalAlertProjection(
            latest_alert,
            category,
            stream_id,
            latest.event_id,
            latest.occurred_at,
        )
    )
    return status, alert


def _event_fact(
    event: OperationalEvent,
    scope_fingerprint: str,
    declared: dict[str, tuple[OperationalCategory, OperationalEmitter, str, str]],
    as_of: datetime,
) -> _EventFact:
    snapshot = validated_event_snapshot(event)
    stream_id = snapshot[1]
    if snapshot[0] != scope_fingerprint:
        _fail(ObservabilityErrorCode.CROSS_SCOPE_EVENT)
    stream_snapshot = declared.get(stream_id)
    if stream_snapshot is None:
        _fail(ObservabilityErrorCode.UNDECLARED_STREAM)
    if snapshot[2] is not stream_snapshot[0] or snapshot[3] is not stream_snapshot[1]:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if snapshot[5] > as_of:
        _fail(ObservabilityErrorCode.EVENT_AFTER_AS_OF)
    return _EventFact(
        scope_fingerprint=snapshot[0],
        stream_id=stream_id,
        category=snapshot[2],
        emitter=snapshot[3],
        sequence=snapshot[4],
        occurred_at=snapshot[5],
        code=snapshot[6],
        event_id=snapshot[8],
        fingerprint=snapshot[9],
    )


def _deduplicated_facts(
    events: tuple[OperationalEvent, ...],
    scope_fingerprint: str,
    declared: dict[str, tuple[OperationalCategory, OperationalEmitter, str, str]],
    as_of: datetime,
) -> dict[tuple[str, int], _EventFact]:
    unique: dict[tuple[str, int], _EventFact] = {}
    for event in events:
        fact = _event_fact(event, scope_fingerprint, declared, as_of)
        key = (fact.stream_id, fact.sequence)
        previous = unique.get(key)
        if previous is not None:
            if previous.fingerprint != fact.fingerprint:
                _fail(ObservabilityErrorCode.STREAM_SEQUENCE_CONFLICT)
            continue
        unique[key] = fact
    return unique


def _ordered_facts_by_stream(
    declared: dict[str, tuple[OperationalCategory, OperationalEmitter, str, str]],
    unique: dict[tuple[str, int], _EventFact],
) -> dict[str, tuple[_EventFact, ...]]:
    grouped: dict[str, list[_EventFact]] = {stream_id: [] for stream_id in declared}
    for (stream_id, _), event in unique.items():
        grouped[stream_id].append(event)
    result: dict[str, tuple[_EventFact, ...]] = {}
    for stream_id, stream_events in grouped.items():
        ordered = tuple(sorted(stream_events, key=lambda item: item.sequence))
        previous_time: datetime | None = None
        for event in ordered:
            if previous_time is not None and event.occurred_at < previous_time:
                _fail(ObservabilityErrorCode.STREAM_TIME_REGRESSION)
            previous_time = event.occurred_at
        result[stream_id] = ordered
    return result


def aggregate_operational_status(
    scope: OperationalStatusScope,
    events: object,
    as_of: datetime,
) -> OperationalStatusSnapshot:
    """Project deterministic current blockers without clocks or I/O."""
    scoped_streams = validated_scope_streams(scope)
    if not _is_exact_tuple(events):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if not is_canonical_operational_time(as_of):
        _fail(ObservabilityErrorCode.INVALID_AS_OF)
    scoped_pairs = tuple((stream, validated_stream_snapshot(stream)) for stream in scoped_streams)
    declared = {snapshot[3]: snapshot for _, snapshot in scoped_pairs}
    checked_events: list[OperationalEvent] = []
    for candidate in events:
        if type(candidate) is not OperationalEvent:
            _fail(ObservabilityErrorCode.INVALID_EVENT)
        checked_events.append(candidate)
    unique = _deduplicated_facts(tuple(checked_events), scope.scope_fingerprint, declared, as_of)
    ordered_by_stream = _ordered_facts_by_stream(declared, unique)

    statuses: list[OperationalStreamStatus] = []
    alerts: list[OperationalAlertProjection] = []
    for stream, stream_snapshot in scoped_pairs:
        status, alert = _stream_status(stream, ordered_by_stream[stream_snapshot[3]])
        statuses.append(status)
        if alert is not None:
            alerts.append(alert)
    status_tuple = tuple(statuses)
    alert_tuple = tuple(alerts)
    complete = all(status.observed for status in status_tuple)
    healthy = complete and not alert_tuple
    payload = _snapshot_payload(
        _SnapshotContent(
            scope_fingerprint=scope.scope_fingerprint,
            as_of=as_of,
            complete=complete,
            healthy=healthy,
            streams=status_tuple,
            alerts=alert_tuple,
        )
    )
    fingerprint = derive_operational_fingerprint(
        ("operational-status-snapshot-v1", payload),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    return OperationalStatusSnapshot(
        scope.scope_fingerprint,
        as_of,
        complete,
        healthy,
        status_tuple,
        alert_tuple,
        fingerprint,
    )


def _validate_snapshot_scope(
    snapshot: OperationalStatusSnapshot,
    statuses: tuple[OperationalStreamStatus, ...],
) -> None:
    status_keys = tuple((_CATEGORY_INDEX[status.category], status.stream_id) for status in statuses)
    if status_keys != tuple(sorted(status_keys)):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    stream_ids = tuple(status.stream_id for status in statuses)
    if len(set(stream_ids)) != len(stream_ids):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if {status.category for status in statuses} != set(OPERATIONAL_CATEGORY_ORDER):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    expected_scope = derive_operational_fingerprint(
        ("operational-status-scope-v1", stream_ids),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    if snapshot.scope_fingerprint != expected_scope:
        _fail(ObservabilityErrorCode.INVALID_EVENT)


def _validate_snapshot_times(
    snapshot: OperationalStatusSnapshot,
    statuses: tuple[OperationalStreamStatus, ...],
) -> None:
    for status in statuses:
        times = (
            status.latest_at,
            status.last_success_at,
            status.last_failure_at,
        )
        if any(value is not None and value > snapshot.as_of for value in times):
            _fail(ObservabilityErrorCode.INVALID_EVENT)
        latest_at = status.latest_at
        if latest_at is not None and any(
            value is not None and value > latest_at for value in times[1:]
        ):
            _fail(ObservabilityErrorCode.INVALID_EVENT)


def _expected_alerts(
    statuses: tuple[OperationalStreamStatus, ...],
) -> tuple[OperationalAlertProjection, ...]:
    expected: list[OperationalAlertProjection] = []
    for status in statuses:
        if not status.observed:
            expected.append(
                OperationalAlertProjection(
                    OperationalAlertCode.OPERATIONAL_STREAM_MISSING,
                    status.category,
                    status.stream_id,
                    None,
                    None,
                )
            )
            continue
        latest_code = status.latest_code
        if type(latest_code) is not OperationalEventCode:
            _fail(ObservabilityErrorCode.INVALID_EVENT)
        projected = event_alert_code_for(latest_code)
        if projected is not None:
            expected.append(
                OperationalAlertProjection(
                    projected,
                    status.category,
                    status.stream_id,
                    status.latest_event_id,
                    status.latest_at,
                )
            )
    return tuple(expected)


def _validated_snapshot(snapshot: OperationalStatusSnapshot) -> dict[str, object]:
    if (
        type(snapshot) is not OperationalStatusSnapshot
        or not is_opaque_fingerprint(snapshot.scope_fingerprint)
        or not is_canonical_operational_time(snapshot.as_of)
        or type(snapshot.complete) is not bool
        or type(snapshot.healthy) is not bool
        or type(snapshot.streams) is not tuple
        or type(snapshot.alerts) is not tuple
        or not is_opaque_fingerprint(snapshot.fingerprint)
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    checked_statuses = tuple(_validated_status(status) for status in snapshot.streams)
    _validate_snapshot_scope(snapshot, checked_statuses)
    _validate_snapshot_times(snapshot, checked_statuses)
    expected_alerts = _expected_alerts(checked_statuses)
    checked_alerts = tuple(_validated_alert(alert) for alert in snapshot.alerts)
    if tuple(_alert_primitive(alert) for alert in checked_alerts) != tuple(
        _alert_primitive(alert) for alert in expected_alerts
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    complete = all(status.observed for status in checked_statuses)
    healthy = complete and not checked_alerts
    if snapshot.complete is not complete or snapshot.healthy is not healthy:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    payload = _snapshot_payload(
        _SnapshotContent(
            scope_fingerprint=snapshot.scope_fingerprint,
            as_of=snapshot.as_of,
            complete=snapshot.complete,
            healthy=snapshot.healthy,
            streams=snapshot.streams,
            alerts=snapshot.alerts,
        )
    )
    expected = derive_operational_fingerprint(
        ("operational-status-snapshot-v1", payload),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    if expected != snapshot.fingerprint:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return payload


def serialize_operational_status(
    snapshot: OperationalStatusSnapshot,
) -> OperationalStatusPrimitive:
    """Return the closed primitive representation of a valid snapshot."""
    _validated_snapshot(snapshot)
    return OperationalStatusPrimitive(
        scope_fingerprint=snapshot.scope_fingerprint,
        as_of=canonical_operational_time(snapshot.as_of),
        complete=snapshot.complete,
        healthy=snapshot.healthy,
        streams=tuple(_status_primitive(status) for status in snapshot.streams),
        alerts=tuple(_alert_primitive(alert) for alert in snapshot.alerts),
        fingerprint=snapshot.fingerprint,
    )


def _parsed_operational_time(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if not is_canonical_operational_time(parsed) or canonical_operational_time(parsed) != value:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return parsed


def _parsed_optional_time(value: object) -> datetime | None:
    return None if value is None else _parsed_operational_time(value)


def _parsed_optional_text(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return value


def _is_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not _is_untyped_dict(value):
        return False
    return all(type(key) is str for key in value)


def _is_untyped_dict(value: object) -> TypeIs[dict[object, object]]:
    return type(value) is dict


def _is_object_sequence(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    return type(value) in {list, tuple}


def _parsed_text(value: object) -> str:
    if type(value) is not str:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return value


def _parsed_boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return value


def _parsed_integer(value: object) -> int:
    if type(value) is not int:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return value


def _parsed_stream(value: object) -> OperationalStreamStatus:
    if not _is_object_dict(value) or set(value) != {
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
    }:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    raw = value
    try:
        category = OperationalCategory(_parsed_text(raw["category"]))
        emitter = OperationalEmitter(_parsed_text(raw["emitter"]))
        latest_code = (
            None
            if raw["latest_code"] is None
            else OperationalEventCode(_parsed_text(raw["latest_code"]))
        )
    except TypeError, ValueError:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return _validated_status(
        OperationalStreamStatus(
            stream_id=_parsed_text(raw["stream_id"]),
            category=category,
            emitter=emitter,
            observed=_parsed_boolean(raw["observed"]),
            latest_sequence=_parsed_integer(raw["latest_sequence"]),
            latest_code=latest_code,
            latest_event_id=_parsed_optional_text(raw["latest_event_id"]),
            latest_at=_parsed_optional_time(raw["latest_at"]),
            last_success_event_id=_parsed_optional_text(raw["last_success_event_id"]),
            last_success_at=_parsed_optional_time(raw["last_success_at"]),
            last_failure_event_id=_parsed_optional_text(raw["last_failure_event_id"]),
            last_failure_at=_parsed_optional_time(raw["last_failure_at"]),
        )
    )


def _parsed_alert(value: object) -> OperationalAlertProjection:
    if not _is_object_dict(value) or set(value) != {
        "code",
        "category",
        "stream_id",
        "event_id",
        "occurred_at",
    }:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    raw = value
    try:
        code = OperationalAlertCode(_parsed_text(raw["code"]))
        category = OperationalCategory(_parsed_text(raw["category"]))
    except TypeError, ValueError:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return _validated_alert(
        OperationalAlertProjection(
            code=code,
            category=category,
            stream_id=_parsed_text(raw["stream_id"]),
            event_id=_parsed_optional_text(raw["event_id"]),
            occurred_at=_parsed_optional_time(raw["occurred_at"]),
        )
    )


def parse_operational_status(value: object) -> OperationalStatusSnapshot:
    """Rebuild and independently validate one serialized operational snapshot."""
    if not _is_object_dict(value) or set(value) != {
        "scope_fingerprint",
        "as_of",
        "complete",
        "healthy",
        "streams",
        "alerts",
        "fingerprint",
    }:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    raw_streams = value["streams"]
    raw_alerts = value["alerts"]
    if not _is_object_sequence(raw_streams) or not _is_object_sequence(raw_alerts):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    snapshot = OperationalStatusSnapshot(
        scope_fingerprint=_parsed_text(value["scope_fingerprint"]),
        as_of=_parsed_operational_time(value["as_of"]),
        complete=_parsed_boolean(value["complete"]),
        healthy=_parsed_boolean(value["healthy"]),
        streams=tuple(_parsed_stream(item) for item in raw_streams),
        alerts=tuple(_parsed_alert(item) for item in raw_alerts),
        fingerprint=_parsed_text(value["fingerprint"]),
    )
    _validated_snapshot(snapshot)
    return snapshot


def _validated_hk_v1_family_progress(
    progress: object,
    as_of: datetime,
) -> HKV1FamilyProgress:
    if type(progress) is not HKV1FamilyProgress:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    checked = progress
    counts = (
        checked.discovered_count,
        checked.verified_count,
        checked.retryable_count,
        checked.rejected_count,
        checked.terminal_count,
        checked.active_count,
        checked.queued_count,
        checked.retained_byte_count,
    )
    if (
        type(checked.material_family) is not str
        or checked.material_family not in _HK_V1_FAMILIES
        or type(checked.cycle_id) is not str
        or _HK_V1_CYCLE_ID.fullmatch(checked.cycle_id) is None
        or any(type(value) is not int or value < 0 for value in counts)
        or checked.terminal_count != checked.verified_count + checked.rejected_count
        or checked.discovered_count
        != (
            checked.terminal_count
            + checked.retryable_count
            + checked.active_count
            + checked.queued_count
        )
        or not is_opaque_fingerprint(checked.journal_head_fingerprint)
        or (
            checked.last_progress_at is not None
            and (
                not is_canonical_operational_time(checked.last_progress_at)
                or checked.last_progress_at > as_of
            )
        )
        or (
            checked.cycle_result is not None
            and type(checked.cycle_result) is not HKV1FamilyCycleResult
        )
        or (
            checked.result_fingerprint is not None
            and not is_opaque_fingerprint(checked.result_fingerprint)
        )
        or (checked.cycle_result is None) is not (checked.result_fingerprint is None)
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if checked.cycle_result in {
        HKV1FamilyCycleResult.COMPLETE,
        HKV1FamilyCycleResult.NO_CHANGE,
    } and (
        checked.discovered_count == 0
        or checked.terminal_count != checked.discovered_count
        or checked.retryable_count != 0
        or checked.rejected_count != 0
        or checked.active_count != 0
        or checked.queued_count != 0
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return checked


def _hk_v1_family_primitive(
    progress: HKV1FamilyProgress,
) -> HKV1FamilyProgressPrimitive:
    return {
        "material_family": progress.material_family,
        "cycle_id": progress.cycle_id,
        "discovered_count": progress.discovered_count,
        "verified_count": progress.verified_count,
        "retryable_count": progress.retryable_count,
        "rejected_count": progress.rejected_count,
        "terminal_count": progress.terminal_count,
        "active_count": progress.active_count,
        "queued_count": progress.queued_count,
        "retained_byte_count": progress.retained_byte_count,
        "journal_head_fingerprint": progress.journal_head_fingerprint,
        "last_progress_at": (
            None
            if progress.last_progress_at is None
            else canonical_operational_time(progress.last_progress_at)
        ),
        "cycle_result": None if progress.cycle_result is None else progress.cycle_result.value,
        "result_fingerprint": progress.result_fingerprint,
    }


def _hk_v1_progress_status(
    families: tuple[HKV1FamilyProgress, ...],
) -> HKV1ProgressStatus:
    if all(item.discovered_count == 0 and item.cycle_result is None for item in families):
        return HKV1ProgressStatus.NOT_STARTED
    terminal_results = {
        HKV1FamilyCycleResult.INCOMPLETE_TERMINAL,
        HKV1FamilyCycleResult.SOURCE_CONTRACT_CHANGED,
        HKV1FamilyCycleResult.EVIDENCE_INTEGRITY_FAILURE,
        HKV1FamilyCycleResult.AUTHORIZATION_FAILURE,
        HKV1FamilyCycleResult.RETRY_EXHAUSTED,
    }
    if any(item.rejected_count > 0 or item.cycle_result in terminal_results for item in families):
        return HKV1ProgressStatus.INCOMPLETE_TERMINAL
    complete_results = {HKV1FamilyCycleResult.COMPLETE, HKV1FamilyCycleResult.NO_CHANGE}
    if all(item.cycle_result in complete_results for item in families):
        return HKV1ProgressStatus.COMPLETE
    return HKV1ProgressStatus.INCOMPLETE_RETRYABLE


def aggregate_hk_v1_progress(
    families: object,
    as_of: datetime,
) -> HKV1ProgressSnapshot:
    """Project exact two-family progress; incomplete work is never a percentage success."""
    if not _is_exact_tuple(families) or not is_canonical_operational_time(as_of):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    checked = tuple(_validated_hk_v1_family_progress(item, as_of) for item in families)
    ordered = tuple(sorted(checked, key=lambda item: item.material_family))
    if tuple(item.material_family for item in ordered) != _HK_V1_FAMILIES:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    status = _hk_v1_progress_status(ordered)
    payload = {
        "as_of": canonical_operational_time(as_of),
        "status": status.value,
        "families": tuple(_hk_v1_family_primitive(item) for item in ordered),
    }
    fingerprint = derive_operational_fingerprint(
        ("hk-v1-two-family-progress-v1", payload),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    return HKV1ProgressSnapshot(as_of, status, ordered, fingerprint)


def serialize_hk_v1_progress(snapshot: HKV1ProgressSnapshot) -> HKV1ProgressPrimitive:
    """Return the closed primitive representation after full derived-state validation."""
    if (
        type(snapshot) is not HKV1ProgressSnapshot
        or type(snapshot.status) is not HKV1ProgressStatus
        or type(snapshot.families) is not tuple
        or not is_opaque_fingerprint(snapshot.fingerprint)
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    rebuilt = aggregate_hk_v1_progress(snapshot.families, snapshot.as_of)
    if rebuilt != snapshot:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return HKV1ProgressPrimitive(
        as_of=canonical_operational_time(snapshot.as_of),
        status=snapshot.status.value,
        families=tuple(_hk_v1_family_primitive(item) for item in snapshot.families),
        fingerprint=snapshot.fingerprint,
    )


__all__ = [
    "HKV1FamilyCycleResult",
    "HKV1FamilyProgress",
    "HKV1ProgressSnapshot",
    "HKV1ProgressStatus",
    "OperationalAlertProjection",
    "OperationalStatusSnapshot",
    "OperationalStreamStatus",
    "aggregate_hk_v1_progress",
    "aggregate_operational_status",
    "parse_operational_status",
    "serialize_hk_v1_progress",
    "serialize_operational_status",
]
