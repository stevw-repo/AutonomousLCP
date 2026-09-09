# ruff: noqa: D100, D103, EM101, INP001, PLR2004, PLW1641, RUF005, S101, SIM300, SLOT001, TRY003

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum

import asklegal_observability.events as events_module
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
    OperationalEventObservation,
    OperationalStatusScope,
    OperationalStreamSpec,
    alert_code_for,
    allowed_emitters,
    build_event_observation,
    build_operational_event,
    build_status_scope,
    build_stream_spec,
    clear_code_for,
    event_alert_code_for,
    serialize_operational_event,
)

FP_A = "sha256:" + "a" * 64
FP_B = "sha256:" + "b" * 64
NOW = datetime(2026, 8, 27, 1, 2, 3, tzinfo=UTC)


EXPECTED_CATALOGUE = (
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

INVALID_SCOPE_VALUES: tuple[object, ...] = (
    [],
    {},
    set[object](),
    None,
    (),
    (
        build_stream_spec(
            OperationalCategory.SOURCE,
            OperationalEmitter.ACQUISITION_WORKER,
            FP_A,
        ),
    ),
)


def _scope() -> OperationalStatusScope:
    streams = tuple(
        build_stream_spec(category, emitters[0], f"sha256:{index:064x}")
        for index, (category, _, _, _, emitters) in enumerate(EXPECTED_CATALOGUE, start=1)
    )
    return build_status_scope(tuple(reversed(streams)))


def _observation(
    sequence: object,
    occurred_at: object,
    code: object,
    correlation_fingerprint: object = None,
) -> OperationalEventObservation:
    return build_event_observation(
        sequence,
        occurred_at,
        code,
        correlation_fingerprint,
    )


def test_catalogue_and_emitter_ownership_are_closed() -> None:
    assert OPERATIONAL_CATEGORY_ORDER == tuple(row[0] for row in EXPECTED_CATALOGUE)
    assert len(OperationalCategory) == 12
    assert len(OperationalEventCode) == 24
    assert len(OperationalAlertCode) == 13
    assert OperationalAlertCode.OPERATIONAL_STREAM_MISSING in OperationalAlertCode

    for category, clear, alert, projected, emitters in EXPECTED_CATALOGUE:
        assert clear_code_for(category) is clear
        assert alert_code_for(category) is alert
        assert event_alert_code_for(alert) is projected
        assert event_alert_code_for(clear) is None
        assert allowed_emitters(category) == emitters


def test_stream_and_scope_builders_are_stable_sorted_and_detached() -> None:
    first = build_stream_spec(
        OperationalCategory.SOURCE, OperationalEmitter.ACQUISITION_WORKER, FP_A
    )
    same = build_stream_spec(
        OperationalCategory.SOURCE, OperationalEmitter.ACQUISITION_WORKER, FP_A
    )
    assert first == same
    assert first.stream_id.startswith("sha256:")

    scope = _scope()
    assert scope.streams == tuple(
        sorted(
            scope.streams,
            key=lambda stream: (
                OPERATIONAL_CATEGORY_ORDER.index(stream.category),
                stream.stream_id,
            ),
        )
    )
    assert scope.scope_fingerprint.startswith("sha256:")
    assert build_status_scope(scope.streams) == scope


@pytest.mark.parametrize(
    "value",
    INVALID_SCOPE_VALUES,
)
def test_scope_rejects_mutable_empty_and_incomplete_stream_collections(
    value: object,
) -> None:
    with pytest.raises(ObservabilityError) as caught:
        build_status_scope(value)
    assert caught.value.code is ObservabilityErrorCode.INVALID_SCOPE


def test_scope_rejects_duplicate_or_extra_invalid_streams() -> None:
    scope = _scope()
    with pytest.raises(ObservabilityError) as duplicate:
        build_status_scope(scope.streams + (scope.streams[0],))
    assert duplicate.value.code is ObservabilityErrorCode.INVALID_SCOPE

    forged = object.__new__(OperationalStreamSpec)
    object.__setattr__(forged, "category", OperationalCategory.SOURCE)
    object.__setattr__(forged, "emitter", OperationalEmitter.ACQUISITION_WORKER)
    object.__setattr__(forged, "subject_fingerprint", FP_A)
    object.__setattr__(forged, "stream_id", FP_B)
    with pytest.raises(ObservabilityError) as drift:
        build_status_scope(scope.streams + (forged,))
    assert drift.value.code is ObservabilityErrorCode.INVALID_STREAM


@pytest.mark.parametrize(
    ("category", "emitter", "fingerprint"),
    [
        ("SOURCE", OperationalEmitter.ACQUISITION_WORKER, FP_A),
        (OperationalCategory.SOURCE, "ACQUISITION_WORKER", FP_A),
        (OperationalCategory.SOURCE, OperationalEmitter.CONTROL_PLANE, FP_A),
        (
            OperationalCategory.SOURCE,
            OperationalEmitter.ACQUISITION_WORKER,
            "token=secret",
        ),
        (
            OperationalCategory.SOURCE,
            OperationalEmitter.ACQUISITION_WORKER,
            {"token": "secret"},
        ),
        (
            OperationalCategory.SOURCE,
            OperationalEmitter.ACQUISITION_WORKER,
            ValueError("raw"),
        ),
    ],
)
def test_stream_rejects_open_or_secret_shaped_inputs(
    category: object, emitter: object, fingerprint: object
) -> None:
    with pytest.raises(ObservabilityError):
        build_stream_spec(category, emitter, fingerprint)


def test_event_builder_binds_closed_scope_stream_and_derived_identities() -> None:
    scope = _scope()
    stream = scope.streams[0]
    event = build_operational_event(
        scope,
        stream,
        _observation(1, NOW, clear_code_for(stream.category), FP_B),
    )
    assert event.scope_fingerprint == scope.scope_fingerprint
    assert event.stream_id == stream.stream_id
    assert event.category is stream.category
    assert event.emitter is stream.emitter
    assert event.event_id.startswith("sha256:")
    assert event.fingerprint.startswith("sha256:")
    assert (
        build_operational_event(
            scope,
            stream,
            _observation(1, NOW, clear_code_for(stream.category), FP_B),
        )
        == event
    )


@pytest.mark.parametrize("sequence", [True, False, 0, -1, 1.0, "1"])
def test_event_rejects_non_positive_or_non_exact_integer_sequence(sequence: object) -> None:
    scope = _scope()
    stream = scope.streams[0]
    with pytest.raises(ObservabilityError) as caught:
        build_operational_event(
            scope,
            stream,
            _observation(sequence, NOW, clear_code_for(stream.category)),
        )
    assert caught.value.code is ObservabilityErrorCode.INVALID_EVENT


@pytest.mark.parametrize(
    "occurred_at",
    [
        NOW.replace(microsecond=1),
        NOW.replace(tzinfo=None),
        NOW.astimezone(timezone(timedelta(hours=8))),
        "2026-08-27T01:02:03Z",
    ],
)
def test_event_rejects_noncanonical_utc_whole_second_timestamp(
    occurred_at: object,
) -> None:
    scope = _scope()
    stream = scope.streams[0]
    with pytest.raises(ObservabilityError) as caught:
        build_operational_event(
            scope,
            stream,
            _observation(1, occurred_at, clear_code_for(stream.category)),
        )
    assert caught.value.code is ObservabilityErrorCode.INVALID_EVENT


def test_event_rejects_cross_scope_stream_and_category_incompatible_code() -> None:
    scope = _scope()
    altered = list(scope.streams)
    altered[0] = build_stream_spec(altered[0].category, altered[0].emitter, "sha256:" + "f" * 64)
    other_scope = build_status_scope(tuple(altered))

    with pytest.raises(ObservabilityError) as cross_scope:
        build_operational_event(
            other_scope,
            scope.streams[0],
            _observation(1, NOW, clear_code_for(scope.streams[0].category)),
        )
    assert cross_scope.value.code is ObservabilityErrorCode.UNDECLARED_STREAM

    with pytest.raises(ObservabilityError) as wrong_code:
        build_operational_event(
            scope,
            scope.streams[0],
            _observation(1, NOW, OperationalEventCode.RESOURCE_EXHAUSTED),
        )
    assert wrong_code.value.code is ObservabilityErrorCode.INVALID_EVENT


def test_serialized_event_contains_only_closed_primitive_fields() -> None:
    scope = _scope()
    stream = scope.streams[0]
    event = build_operational_event(
        scope,
        stream,
        _observation(1, NOW, clear_code_for(stream.category), FP_B),
    )
    serialized = serialize_operational_event(event)
    assert set(serialized) == {
        "scope_fingerprint",
        "stream_id",
        "category",
        "emitter",
        "sequence",
        "occurred_at",
        "code",
        "correlation_fingerprint",
        "event_id",
        "fingerprint",
    }
    assert all(value is None or type(value) in {str, int} for value in serialized.values())
    forbidden = (
        "secret",
        "token",
        "password",
        "connection",
        "exception",
        "reason",
        "legal_text",
        "person",
        "payload",
        "body",
        "url",
    )
    assert not set(forbidden) & {field.name for field in fields(OperationalEvent)}
    assert all(term not in repr(serialized).lower() for term in forbidden)


class _HostileEquality:
    def __eq__(self, other: object) -> bool:
        raise AssertionError("hostile equality executed")


class _HostileErrorCode:
    @property
    def value(self) -> str:
        message = "raw hostile error"
        raise ValueError(message)


class _HostileTuple(tuple[object, ...]):
    def __iter__(self) -> Iterator[object]:
        raise AssertionError("hostile iterator executed")


class _HostileList(list[object]):
    def __iter__(self) -> Iterator[object]:
        raise AssertionError("hostile iterator executed")


def test_hostile_containers_and_mutated_exact_objects_reject_without_execution() -> None:
    for hostile in (_HostileTuple(), _HostileList()):
        with pytest.raises(ObservabilityError):
            build_status_scope(hostile)

    scope = _scope()
    object.__setattr__(scope.streams[0], "category", _HostileEquality())
    with pytest.raises(ObservabilityError) as caught:
        build_status_scope(scope.streams)
    assert caught.value.code is ObservabilityErrorCode.INVALID_STREAM


def test_ordinary_errors_are_closed_cause_free_and_base_exception_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ObservabilityError) as caught:
        build_stream_spec(
            OperationalCategory.SOURCE,
            OperationalEmitter.CONTROL_PLANE,
            FP_A,
        )
    assert caught.value.args == (ObservabilityErrorCode.INVALID_STREAM.value,)
    assert str(caught.value) == ObservabilityErrorCode.INVALID_STREAM.value
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None

    def ordinary_failure(_: object) -> str:
        message = "internal raw failure"
        raise ValueError(message)

    monkeypatch.setattr(events_module, "_digest", ordinary_failure)
    with pytest.raises(ObservabilityError) as sanitized:
        build_stream_spec(
            OperationalCategory.SOURCE,
            OperationalEmitter.ACQUISITION_WORKER,
            FP_A,
        )
    assert sanitized.value.code is ObservabilityErrorCode.INVALID_STREAM
    assert sanitized.value.__cause__ is None
    assert sanitized.value.__context__ is None
    assert "internal raw failure" not in str(sanitized.value)

    def interrupt(_: object) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(events_module, "_digest", interrupt)
    with pytest.raises(KeyboardInterrupt):
        build_stream_spec(
            OperationalCategory.SOURCE,
            OperationalEmitter.ACQUISITION_WORKER,
            FP_A,
        )


def test_direct_error_construction_closes_non_enum_and_hostile_codes() -> None:
    for supplied in ("token=secret-value", _HostileErrorCode()):
        error = ObservabilityError(supplied)
        assert error.code is ObservabilityErrorCode.INVALID_EVENT
        assert error.args == (ObservabilityErrorCode.INVALID_EVENT.value,)
        assert "secret" not in str(error).lower()
        assert error.__cause__ is None
        assert error.__context__ is None


@pytest.mark.parametrize("ordinary_error", [RuntimeError, OSError])
def test_every_ordinary_digest_failure_is_sanitized_cause_free(
    monkeypatch: pytest.MonkeyPatch,
    ordinary_error: type[Exception],
) -> None:
    def fail(_: object) -> str:
        message = "token=raw-internal-secret"
        raise ordinary_error(message)

    monkeypatch.setattr(events_module, "_digest", fail)
    with pytest.raises(ObservabilityError) as caught:
        build_stream_spec(
            OperationalCategory.SOURCE,
            OperationalEmitter.ACQUISITION_WORKER,
            FP_A,
        )
    assert caught.value.code is ObservabilityErrorCode.INVALID_STREAM
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "secret" not in str(caught.value).lower()


class _DirectBaseException(BaseException):
    pass


@pytest.mark.parametrize("visible_error", [SystemExit, _DirectBaseException])
def test_non_exception_base_failures_remain_visible(
    monkeypatch: pytest.MonkeyPatch,
    visible_error: type[BaseException],
) -> None:
    def fail(_: object) -> str:
        raise visible_error

    monkeypatch.setattr(events_module, "_digest", fail)
    with pytest.raises(visible_error):
        build_stream_spec(
            OperationalCategory.SOURCE,
            OperationalEmitter.ACQUISITION_WORKER,
            FP_A,
        )


def test_public_types_are_frozen_slotted_and_exact_enums() -> None:
    stream = build_stream_spec(
        OperationalCategory.SOURCE, OperationalEmitter.ACQUISITION_WORKER, FP_A
    )
    assert not hasattr(stream, "__dict__")
    field_name = "stream_id"
    with pytest.raises((AttributeError, TypeError)):
        setattr(stream, field_name, FP_B)
    assert issubclass(OperationalCategory, StrEnum)
    assert type(stream) is OperationalStreamSpec
