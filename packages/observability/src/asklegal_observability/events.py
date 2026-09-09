"""Closed, sanitized operational event contracts for local status projection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Never, TypeGuard


class OperationalCategory(StrEnum):
    """Closed operational stream categories."""

    SOURCE = "SOURCE"
    WORKFLOW = "WORKFLOW"
    COVERAGE = "COVERAGE"
    MODEL = "MODEL"
    PROVIDER = "PROVIDER"
    STORAGE = "STORAGE"
    REVIEW = "REVIEW"
    PROMOTION = "PROMOTION"
    BACKUP = "BACKUP"
    ROLLBACK = "ROLLBACK"
    DISK = "DISK"
    RESOURCE = "RESOURCE"


class OperationalEmitter(StrEnum):
    """Closed application and collector emitters."""

    CONTROL_PLANE = "CONTROL_PLANE"
    REVIEW_APPLICATION = "REVIEW_APPLICATION"
    ACQUISITION_WORKER = "ACQUISITION_WORKER"
    LEGAL_PROCESSING_WORKER = "LEGAL_PROCESSING_WORKER"
    PROMOTION_WORKER = "PROMOTION_WORKER"
    TELEMETRY_COLLECTOR = "TELEMETRY_COLLECTOR"


class OperationalEventCode(StrEnum):
    """Closed clear and blocker event codes."""

    SOURCE_CYCLE_SUCCEEDED = "SOURCE_CYCLE_SUCCEEDED"
    SOURCE_CYCLE_BLOCKED = "SOURCE_CYCLE_BLOCKED"
    WORKFLOW_SUCCEEDED = "WORKFLOW_SUCCEEDED"
    WORKFLOW_BLOCKED = "WORKFLOW_BLOCKED"
    COVERAGE_VERIFIED = "COVERAGE_VERIFIED"
    COVERAGE_BLOCKED = "COVERAGE_BLOCKED"
    MODEL_OPERATION_SUCCEEDED = "MODEL_OPERATION_SUCCEEDED"
    MODEL_OPERATION_BLOCKED = "MODEL_OPERATION_BLOCKED"
    PROVIDER_AVAILABLE = "PROVIDER_AVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    STORAGE_AVAILABLE = "STORAGE_AVAILABLE"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    REVIEW_OPERATION_SUCCEEDED = "REVIEW_OPERATION_SUCCEEDED"
    REVIEW_OPERATION_BLOCKED = "REVIEW_OPERATION_BLOCKED"
    PROMOTION_SUCCEEDED = "PROMOTION_SUCCEEDED"
    PROMOTION_BLOCKED = "PROMOTION_BLOCKED"
    BACKUP_VERIFIED = "BACKUP_VERIFIED"
    BACKUP_UNVERIFIED = "BACKUP_UNVERIFIED"
    ROLLBACK_VERIFIED = "ROLLBACK_VERIFIED"
    ROLLBACK_UNVERIFIED = "ROLLBACK_UNVERIFIED"
    DISK_WITHIN_LIMIT = "DISK_WITHIN_LIMIT"
    DISK_PRESSURE = "DISK_PRESSURE"
    RESOURCE_WITHIN_LIMIT = "RESOURCE_WITHIN_LIMIT"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"


class OperationalAlertCode(StrEnum):
    """Closed projected blocker and missing-stream alert codes."""

    SOURCE_CYCLE_BLOCKED = "SOURCE_CYCLE_BLOCKED"
    WORKFLOW_BLOCKED = "WORKFLOW_BLOCKED"
    COVERAGE_BLOCKED = "COVERAGE_BLOCKED"
    MODEL_OPERATION_BLOCKED = "MODEL_OPERATION_BLOCKED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    REVIEW_OPERATION_BLOCKED = "REVIEW_OPERATION_BLOCKED"
    PROMOTION_BLOCKED = "PROMOTION_BLOCKED"
    BACKUP_UNVERIFIED = "BACKUP_UNVERIFIED"
    ROLLBACK_UNVERIFIED = "ROLLBACK_UNVERIFIED"
    DISK_PRESSURE = "DISK_PRESSURE"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    OPERATIONAL_STREAM_MISSING = "OPERATIONAL_STREAM_MISSING"


class ObservabilityErrorCode(StrEnum):
    """Closed boundary failure codes."""

    INVALID_CATEGORY = "INVALID_CATEGORY"
    INVALID_STREAM = "INVALID_STREAM"
    INVALID_SCOPE = "INVALID_SCOPE"
    UNDECLARED_STREAM = "UNDECLARED_STREAM"
    INVALID_EVENT = "INVALID_EVENT"
    CROSS_SCOPE_EVENT = "CROSS_SCOPE_EVENT"
    STREAM_SEQUENCE_CONFLICT = "STREAM_SEQUENCE_CONFLICT"
    STREAM_TIME_REGRESSION = "STREAM_TIME_REGRESSION"
    EVENT_AFTER_AS_OF = "EVENT_AFTER_AS_OF"
    INVALID_AS_OF = "INVALID_AS_OF"


class ObservabilityError(Exception):
    """Cause-free closed failure at the observability package boundary."""

    code: ObservabilityErrorCode

    def __init__(self, code: object) -> None:
        """Create a sanitized error carrying only its closed code."""
        closed_code = (
            code if type(code) is ObservabilityErrorCode else ObservabilityErrorCode.INVALID_EVENT
        )
        self.code = closed_code
        super().__init__(closed_code.value)


OPERATIONAL_CATEGORY_ORDER: tuple[OperationalCategory, ...] = tuple(OperationalCategory)

_CATEGORY_INDEX = {category: index for index, category in enumerate(OPERATIONAL_CATEGORY_ORDER)}
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_ORDINARY_BOUNDARY_ERRORS = (Exception,)

_CATALOGUE: tuple[
    tuple[
        OperationalCategory,
        OperationalEventCode,
        OperationalEventCode,
        OperationalAlertCode,
        tuple[OperationalEmitter, ...],
    ],
    ...,
] = (
    (
        OperationalCategory.SOURCE,
        OperationalEventCode.SOURCE_CYCLE_SUCCEEDED,
        OperationalEventCode.SOURCE_CYCLE_BLOCKED,
        OperationalAlertCode.SOURCE_CYCLE_BLOCKED,
        (OperationalEmitter.ACQUISITION_WORKER,),
    ),
    (
        OperationalCategory.WORKFLOW,
        OperationalEventCode.WORKFLOW_SUCCEEDED,
        OperationalEventCode.WORKFLOW_BLOCKED,
        OperationalAlertCode.WORKFLOW_BLOCKED,
        (
            OperationalEmitter.CONTROL_PLANE,
            OperationalEmitter.ACQUISITION_WORKER,
            OperationalEmitter.LEGAL_PROCESSING_WORKER,
            OperationalEmitter.PROMOTION_WORKER,
        ),
    ),
    (
        OperationalCategory.COVERAGE,
        OperationalEventCode.COVERAGE_VERIFIED,
        OperationalEventCode.COVERAGE_BLOCKED,
        OperationalAlertCode.COVERAGE_BLOCKED,
        (
            OperationalEmitter.CONTROL_PLANE,
            OperationalEmitter.ACQUISITION_WORKER,
            OperationalEmitter.LEGAL_PROCESSING_WORKER,
        ),
    ),
    (
        OperationalCategory.MODEL,
        OperationalEventCode.MODEL_OPERATION_SUCCEEDED,
        OperationalEventCode.MODEL_OPERATION_BLOCKED,
        OperationalAlertCode.MODEL_OPERATION_BLOCKED,
        (OperationalEmitter.LEGAL_PROCESSING_WORKER,),
    ),
    (
        OperationalCategory.PROVIDER,
        OperationalEventCode.PROVIDER_AVAILABLE,
        OperationalEventCode.PROVIDER_UNAVAILABLE,
        OperationalAlertCode.PROVIDER_UNAVAILABLE,
        (
            OperationalEmitter.LEGAL_PROCESSING_WORKER,
            OperationalEmitter.PROMOTION_WORKER,
        ),
    ),
    (
        OperationalCategory.STORAGE,
        OperationalEventCode.STORAGE_AVAILABLE,
        OperationalEventCode.STORAGE_UNAVAILABLE,
        OperationalAlertCode.STORAGE_UNAVAILABLE,
        (
            OperationalEmitter.CONTROL_PLANE,
            OperationalEmitter.REVIEW_APPLICATION,
            OperationalEmitter.ACQUISITION_WORKER,
            OperationalEmitter.LEGAL_PROCESSING_WORKER,
            OperationalEmitter.PROMOTION_WORKER,
        ),
    ),
    (
        OperationalCategory.REVIEW,
        OperationalEventCode.REVIEW_OPERATION_SUCCEEDED,
        OperationalEventCode.REVIEW_OPERATION_BLOCKED,
        OperationalAlertCode.REVIEW_OPERATION_BLOCKED,
        (OperationalEmitter.REVIEW_APPLICATION,),
    ),
    (
        OperationalCategory.PROMOTION,
        OperationalEventCode.PROMOTION_SUCCEEDED,
        OperationalEventCode.PROMOTION_BLOCKED,
        OperationalAlertCode.PROMOTION_BLOCKED,
        (OperationalEmitter.PROMOTION_WORKER,),
    ),
    (
        OperationalCategory.BACKUP,
        OperationalEventCode.BACKUP_VERIFIED,
        OperationalEventCode.BACKUP_UNVERIFIED,
        OperationalAlertCode.BACKUP_UNVERIFIED,
        (OperationalEmitter.PROMOTION_WORKER,),
    ),
    (
        OperationalCategory.ROLLBACK,
        OperationalEventCode.ROLLBACK_VERIFIED,
        OperationalEventCode.ROLLBACK_UNVERIFIED,
        OperationalAlertCode.ROLLBACK_UNVERIFIED,
        (OperationalEmitter.PROMOTION_WORKER,),
    ),
    (
        OperationalCategory.DISK,
        OperationalEventCode.DISK_WITHIN_LIMIT,
        OperationalEventCode.DISK_PRESSURE,
        OperationalAlertCode.DISK_PRESSURE,
        (OperationalEmitter.TELEMETRY_COLLECTOR,),
    ),
    (
        OperationalCategory.RESOURCE,
        OperationalEventCode.RESOURCE_WITHIN_LIMIT,
        OperationalEventCode.RESOURCE_EXHAUSTED,
        OperationalAlertCode.RESOURCE_EXHAUSTED,
        (OperationalEmitter.TELEMETRY_COLLECTOR,),
    ),
)


@dataclass(frozen=True, slots=True)
class OperationalStreamSpec:
    """One expected stream bound to an opaque subject fingerprint."""

    category: OperationalCategory
    emitter: OperationalEmitter
    subject_fingerprint: str
    stream_id: str


@dataclass(frozen=True, slots=True)
class OperationalStatusScope:
    """A complete closed set of expected operational streams."""

    streams: tuple[OperationalStreamSpec, ...]
    scope_fingerprint: str


@dataclass(frozen=True, slots=True)
class OperationalEventObservation:
    """Closed caller-supplied observation facts before identity derivation."""

    sequence: int
    occurred_at: datetime
    code: OperationalEventCode
    correlation_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class OperationalEvent:
    """A sanitized immutable observation for one declared stream."""

    scope_fingerprint: str
    stream_id: str
    category: OperationalCategory
    emitter: OperationalEmitter
    sequence: int
    occurred_at: datetime
    code: OperationalEventCode
    correlation_fingerprint: str | None
    event_id: str
    fingerprint: str


def _fail(code: ObservabilityErrorCode) -> Never:
    raise ObservabilityError(code) from None


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
    return f"sha256:{sha256(encoded).hexdigest()}"


def derive_operational_fingerprint(value: object, error_code: ObservabilityErrorCode) -> str:
    result: str | None
    try:
        result = _digest(value)
    except _ORDINARY_BOUNDARY_ERRORS:
        result = None
    if result is None:
        _fail(error_code)
    return result


def _row_for(
    category: OperationalCategory,
) -> tuple[
    OperationalCategory,
    OperationalEventCode,
    OperationalEventCode,
    OperationalAlertCode,
    tuple[OperationalEmitter, ...],
]:
    if type(category) is not OperationalCategory:
        _fail(ObservabilityErrorCode.INVALID_CATEGORY)
    return _CATALOGUE[_CATEGORY_INDEX[category]]


def clear_code_for(category: OperationalCategory) -> OperationalEventCode:
    """Return the sole clear code admitted for ``category``."""
    return _row_for(category)[1]


def alert_code_for(category: OperationalCategory) -> OperationalEventCode:
    """Return the sole blocker code admitted for ``category``."""
    return _row_for(category)[2]


def allowed_emitters(
    category: OperationalCategory,
) -> tuple[OperationalEmitter, ...]:
    """Return the closed emitter ownership tuple for ``category``."""
    return _row_for(category)[4]


def event_alert_code_for(
    code: OperationalEventCode,
) -> OperationalAlertCode | None:
    """Project a blocker event to its alert code, or clear it."""
    if type(code) is not OperationalEventCode:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    for _, clear, alert, projected, _ in _CATALOGUE:
        if code is clear:
            return None
        if code is alert:
            return projected
    _fail(ObservabilityErrorCode.INVALID_EVENT)


def is_opaque_fingerprint(value: object) -> bool:
    return type(value) is str and _FINGERPRINT.fullmatch(value) is not None


def _is_exact_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return type(value) is tuple


def canonical_operational_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_canonical_operational_time(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is UTC
        and value.microsecond == 0
        and value.fold == 0
    )


def _stream_seed(
    category: OperationalCategory,
    emitter: OperationalEmitter,
    subject_fingerprint: str,
) -> tuple[str, str, str, str]:
    return ("operational-stream-v1", category.value, emitter.value, subject_fingerprint)


def validated_stream_snapshot(
    stream: OperationalStreamSpec,
) -> tuple[OperationalCategory, OperationalEmitter, str, str]:
    if type(stream) is not OperationalStreamSpec:
        _fail(ObservabilityErrorCode.INVALID_STREAM)
    category = stream.category
    emitter = stream.emitter
    subject_fingerprint = stream.subject_fingerprint
    stream_id = stream.stream_id
    if (
        type(category) is not OperationalCategory
        or type(emitter) is not OperationalEmitter
        or type(subject_fingerprint) is not str
        or not is_opaque_fingerprint(subject_fingerprint)
        or not is_opaque_fingerprint(stream_id)
    ):
        _fail(ObservabilityErrorCode.INVALID_STREAM)
    if emitter not in allowed_emitters(category):
        _fail(ObservabilityErrorCode.INVALID_STREAM)
    expected_id = derive_operational_fingerprint(
        _stream_seed(category, emitter, subject_fingerprint),
        ObservabilityErrorCode.INVALID_STREAM,
    )
    if stream_id != expected_id:
        _fail(ObservabilityErrorCode.INVALID_STREAM)
    return category, emitter, subject_fingerprint, stream_id


def build_stream_spec(
    category: object,
    emitter: object,
    subject_fingerprint: object,
) -> OperationalStreamSpec:
    """Build a validated stream with a code-derived identity."""
    if (
        type(category) is not OperationalCategory
        or type(emitter) is not OperationalEmitter
        or type(subject_fingerprint) is not str
        or not is_opaque_fingerprint(subject_fingerprint)
    ):
        _fail(ObservabilityErrorCode.INVALID_STREAM)
    if emitter not in allowed_emitters(category):
        _fail(ObservabilityErrorCode.INVALID_STREAM)
    stream_id = derive_operational_fingerprint(
        _stream_seed(category, emitter, subject_fingerprint),
        ObservabilityErrorCode.INVALID_STREAM,
    )
    return OperationalStreamSpec(category, emitter, subject_fingerprint, stream_id)


def _scope_seed(stream_ids: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    return ("operational-status-scope-v1", stream_ids)


def validated_scope_streams(
    scope: OperationalStatusScope,
) -> tuple[OperationalStreamSpec, ...]:
    if type(scope) is not OperationalStatusScope or type(scope.streams) is not tuple:
        _fail(ObservabilityErrorCode.INVALID_SCOPE)
    snapshots = tuple(validated_stream_snapshot(stream) for stream in scope.streams)
    if not is_opaque_fingerprint(scope.scope_fingerprint):
        _fail(ObservabilityErrorCode.INVALID_SCOPE)
    ordered = tuple(sorted(snapshots, key=lambda item: (_CATEGORY_INDEX[item[0]], item[3])))
    if tuple(item[3] for item in snapshots) != tuple(item[3] for item in ordered):
        _fail(ObservabilityErrorCode.INVALID_SCOPE)
    ids = tuple(item[3] for item in snapshots)
    if len(set(ids)) != len(ids):
        _fail(ObservabilityErrorCode.INVALID_SCOPE)
    if {item[0] for item in snapshots} != set(OPERATIONAL_CATEGORY_ORDER):
        _fail(ObservabilityErrorCode.INVALID_SCOPE)
    expected = derive_operational_fingerprint(
        _scope_seed(ids), ObservabilityErrorCode.INVALID_SCOPE
    )
    if scope.scope_fingerprint != expected:
        _fail(ObservabilityErrorCode.INVALID_SCOPE)
    return scope.streams


def build_status_scope(
    streams: object,
) -> OperationalStatusScope:
    """Build a sorted, complete operational status scope."""
    if not _is_exact_tuple(streams):
        _fail(ObservabilityErrorCode.INVALID_SCOPE)
    checked_streams: list[OperationalStreamSpec] = []
    snapshots: list[tuple[OperationalCategory, OperationalEmitter, str, str]] = []
    for candidate in streams:
        if type(candidate) is not OperationalStreamSpec:
            _fail(ObservabilityErrorCode.INVALID_STREAM)
        checked_streams.append(candidate)
        snapshots.append(validated_stream_snapshot(candidate))
    ids = tuple(item[3] for item in snapshots)
    if len(set(ids)) != len(ids):
        _fail(ObservabilityErrorCode.INVALID_SCOPE)
    if {item[0] for item in snapshots} != set(OPERATIONAL_CATEGORY_ORDER):
        _fail(ObservabilityErrorCode.INVALID_SCOPE)
    ordered_pairs = sorted(
        zip(snapshots, checked_streams, strict=True),
        key=lambda pair: (_CATEGORY_INDEX[pair[0][0]], pair[0][3]),
    )
    ordered_streams = tuple(pair[1] for pair in ordered_pairs)
    ordered_ids = tuple(pair[0][3] for pair in ordered_pairs)
    scope_fingerprint = derive_operational_fingerprint(
        _scope_seed(ordered_ids), ObservabilityErrorCode.INVALID_SCOPE
    )
    return OperationalStatusScope(ordered_streams, scope_fingerprint)


@dataclass(frozen=True, slots=True)
class _EventSeed:
    scope_fingerprint: str
    stream_id: str
    category: OperationalCategory
    emitter: OperationalEmitter
    sequence: int
    occurred_at: datetime
    code: OperationalEventCode
    correlation_fingerprint: str | None


def _event_seed(
    seed: _EventSeed,
) -> tuple[str, str, str, str, str, int, str, str, str | None]:
    return (
        "operational-event-v1",
        seed.scope_fingerprint,
        seed.stream_id,
        seed.category.value,
        seed.emitter.value,
        seed.sequence,
        canonical_operational_time(seed.occurred_at),
        seed.code.value,
        seed.correlation_fingerprint,
    )


def _validated_observation(
    observation: OperationalEventObservation,
) -> tuple[int, datetime, OperationalEventCode, str | None]:
    if type(observation) is not OperationalEventObservation:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    sequence = observation.sequence
    occurred_at = observation.occurred_at
    code = observation.code
    correlation = observation.correlation_fingerprint
    if (
        type(sequence) is not int
        or sequence <= 0
        or not is_canonical_operational_time(occurred_at)
        or type(code) is not OperationalEventCode
        or (correlation is not None and not is_opaque_fingerprint(correlation))
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return sequence, occurred_at, code, correlation


def build_event_observation(
    sequence: object,
    occurred_at: object,
    code: object,
    correlation_fingerprint: object = None,
) -> OperationalEventObservation:
    """Build exact closed event facts before binding them to a stream."""
    if (
        type(sequence) is not int
        or type(occurred_at) is not datetime
        or type(code) is not OperationalEventCode
        or (correlation_fingerprint is not None and type(correlation_fingerprint) is not str)
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    observation = OperationalEventObservation(
        sequence,
        occurred_at,
        code,
        correlation_fingerprint,
    )
    _validated_observation(observation)
    return observation


def validated_event_snapshot(
    event: OperationalEvent,
) -> tuple[
    str,
    str,
    OperationalCategory,
    OperationalEmitter,
    int,
    datetime,
    OperationalEventCode,
    str | None,
    str,
    str,
]:
    if type(event) is not OperationalEvent:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    scope_fingerprint = event.scope_fingerprint
    stream_id = event.stream_id
    category = event.category
    emitter = event.emitter
    sequence = event.sequence
    occurred_at = event.occurred_at
    code = event.code
    correlation = event.correlation_fingerprint
    event_id = event.event_id
    fingerprint = event.fingerprint
    if (
        not is_opaque_fingerprint(scope_fingerprint)
        or not is_opaque_fingerprint(stream_id)
        or type(category) is not OperationalCategory
        or type(emitter) is not OperationalEmitter
        or type(sequence) is not int
        or sequence <= 0
        or not is_canonical_operational_time(occurred_at)
        or type(code) is not OperationalEventCode
        or (correlation is not None and not is_opaque_fingerprint(correlation))
        or not is_opaque_fingerprint(event_id)
        or not is_opaque_fingerprint(fingerprint)
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    if emitter not in allowed_emitters(category) or code not in (
        clear_code_for(category),
        alert_code_for(category),
    ):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    seed = _event_seed(
        _EventSeed(
            scope_fingerprint=scope_fingerprint,
            stream_id=stream_id,
            category=category,
            emitter=emitter,
            sequence=sequence,
            occurred_at=occurred_at,
            code=code,
            correlation_fingerprint=correlation,
        )
    )
    expected_id = derive_operational_fingerprint(
        ("operational-event-id-v1", seed), ObservabilityErrorCode.INVALID_EVENT
    )
    expected_fingerprint = derive_operational_fingerprint(
        ("operational-event-fingerprint-v1", seed),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    if event_id != expected_id or fingerprint != expected_fingerprint:
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    return (
        scope_fingerprint,
        stream_id,
        category,
        emitter,
        sequence,
        occurred_at,
        code,
        correlation,
        event_id,
        fingerprint,
    )


def build_operational_event(
    scope: OperationalStatusScope,
    stream: OperationalStreamSpec,
    observation: OperationalEventObservation,
) -> OperationalEvent:
    """Build one closed event bound to an exact scope and stream."""
    scoped_streams = validated_scope_streams(scope)
    stream_snapshot = validated_stream_snapshot(stream)
    category, emitter, _, stream_id = stream_snapshot
    sequence, occurred_at, code, correlation_fingerprint = _validated_observation(observation)
    declared = {item.stream_id: item for item in scoped_streams}
    declared_stream = declared.get(stream_id)
    if declared_stream is None:
        _fail(ObservabilityErrorCode.UNDECLARED_STREAM)
    declared_snapshot = validated_stream_snapshot(declared_stream)
    if declared_snapshot != stream_snapshot:
        _fail(ObservabilityErrorCode.UNDECLARED_STREAM)
    if code not in (clear_code_for(category), alert_code_for(category)):
        _fail(ObservabilityErrorCode.INVALID_EVENT)
    seed = _event_seed(
        _EventSeed(
            scope_fingerprint=scope.scope_fingerprint,
            stream_id=stream_id,
            category=category,
            emitter=emitter,
            sequence=sequence,
            occurred_at=occurred_at,
            code=code,
            correlation_fingerprint=correlation_fingerprint,
        )
    )
    event_id = derive_operational_fingerprint(
        ("operational-event-id-v1", seed), ObservabilityErrorCode.INVALID_EVENT
    )
    fingerprint = derive_operational_fingerprint(
        ("operational-event-fingerprint-v1", seed),
        ObservabilityErrorCode.INVALID_EVENT,
    )
    return OperationalEvent(
        scope.scope_fingerprint,
        stream_id,
        category,
        emitter,
        sequence,
        occurred_at,
        code,
        correlation_fingerprint,
        event_id,
        fingerprint,
    )


def serialize_operational_event(
    event: OperationalEvent,
) -> dict[str, str | int | None]:
    """Return the closed primitive representation of a valid event."""
    snapshot = validated_event_snapshot(event)
    return {
        "scope_fingerprint": snapshot[0],
        "stream_id": snapshot[1],
        "category": snapshot[2].value,
        "emitter": snapshot[3].value,
        "sequence": snapshot[4],
        "occurred_at": canonical_operational_time(snapshot[5]),
        "code": snapshot[6].value,
        "correlation_fingerprint": snapshot[7],
        "event_id": snapshot[8],
        "fingerprint": snapshot[9],
    }


__all__ = [
    "OPERATIONAL_CATEGORY_ORDER",
    "ObservabilityError",
    "ObservabilityErrorCode",
    "OperationalAlertCode",
    "OperationalCategory",
    "OperationalEmitter",
    "OperationalEvent",
    "OperationalEventCode",
    "OperationalEventObservation",
    "OperationalStatusScope",
    "OperationalStreamSpec",
    "alert_code_for",
    "allowed_emitters",
    "build_event_observation",
    "build_operational_event",
    "build_status_scope",
    "build_stream_spec",
    "clear_code_for",
    "event_alert_code_for",
    "serialize_operational_event",
]
