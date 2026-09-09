"""Exact Task 9 schedule-slot identity and overlap domain.

This module is deliberately transport-free.  The live adapter must retain each
``ScheduleRequest`` before dispatching its stable operation identity to Durable
Task.  The in-memory implementation exists only for deterministic tests; the
process entry point never composes it as a live success path.
"""

from __future__ import annotations

import os
import re
import threading
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Never, Protocol, cast

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import OrchestrationStatus
from asklegal_reporting import (
    DueCycleKind,
    HongKongV1CoverageMatrix,
    HongKongV1DueCycleInstruction,
    is_hk_v1_coverage_matrix_policy_approved,
)

from .v1_acceptance import validate_hk_v1_acceptance_cycle_result

if TYPE_CHECKING:
    from collections.abc import Generator

    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

_LOCAL_TIMESTAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00$")
_SYSTEMD_INVOCATION_ID = re.compile(r"^[0-9a-f]{32}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_HONG_KONG_OFFSET = timedelta(hours=8)
_SOURCE_FAMILIES = ("CASES", "LEGISLATION")
_SOURCE_GROUP = "HK_V1_TWO_FAMILY_SOURCE"
_MAX_SCHEDULE_STATE_BYTES = 16_777_216
MAINTENANCE_ACTIVITIES = (
    "perform_hk_v1_audit_archive",
    "perform_hk_v1_recovery_verification",
    "perform_hk_v1_telemetry_retention",
)


class LiveScheduleError(ValueError):
    """One closed schedule request or retained-state failure."""


class ScheduleKind(StrEnum):
    """The five and only five recurring local V1 activities."""

    OBSERVATION = "OBSERVATION"
    RECONCILIATION = "RECONCILIATION"
    AUDIT_ARCHIVE = "AUDIT_ARCHIVE"
    RECOVERY_VERIFY = "RECOVERY_VERIFY"
    TELEMETRY_RETENTION = "TELEMETRY_RETENTION"


class ScheduleState(StrEnum):
    """Initial ownership outcome retained for one schedule command."""

    STARTED = "STARTED"
    COALESCED_IN_PROGRESS = "COALESCED_IN_PROGRESS"


@dataclass(frozen=True, slots=True)
class ScheduleDefinition:
    """One exact Hong Kong calendar and its durable activity class."""

    kind: ScheduleKind
    on_calendar: str
    hour: int
    minute: int
    weekday: int | None
    activity_group: str
    due_cycle_kind: DueCycleKind | None
    source_families: tuple[str, ...]


_DEFINITIONS = (
    ScheduleDefinition(
        ScheduleKind.OBSERVATION,
        "*-*-* 02:15:00 Asia/Hong_Kong",
        2,
        15,
        None,
        _SOURCE_GROUP,
        DueCycleKind.DAILY_CURRENT_LAW,
        _SOURCE_FAMILIES,
    ),
    ScheduleDefinition(
        ScheduleKind.RECONCILIATION,
        "Sun *-*-* 03:15:00 Asia/Hong_Kong",
        3,
        15,
        6,
        _SOURCE_GROUP,
        DueCycleKind.FULL_PERIODIC,
        _SOURCE_FAMILIES,
    ),
    ScheduleDefinition(
        ScheduleKind.AUDIT_ARCHIVE,
        "*-*-* 04:30:00 Asia/Hong_Kong",
        4,
        30,
        None,
        "AUDIT_ARCHIVE",
        None,
        (),
    ),
    ScheduleDefinition(
        ScheduleKind.RECOVERY_VERIFY,
        "Mon *-*-* 05:15:00 Asia/Hong_Kong",
        5,
        15,
        0,
        "RECOVERY_VERIFY",
        None,
        (),
    ),
    ScheduleDefinition(
        ScheduleKind.TELEMETRY_RETENTION,
        "*-*-* 06:00:00 Asia/Hong_Kong",
        6,
        0,
        None,
        "TELEMETRY_RETENTION",
        None,
        (),
    ),
)
_BY_KIND = {item.kind: item for item in _DEFINITIONS}


@dataclass(frozen=True, slots=True)
class ScheduleRequest:
    """One immutable command candidate derived only from an exact calendar slot."""

    command_id: str
    command_fingerprint: str
    matrix_revision: str
    matrix_fingerprint: str
    kind: ScheduleKind
    scheduled_at: str
    activity_group: str
    operation_id: str
    cycle_id: str | None
    journal_ref: str | None
    source_families: tuple[str, ...]
    instruction: HongKongV1DueCycleInstruction | None


@dataclass(frozen=True, slots=True)
class StoredScheduleCommand:
    """Retained first resolution for a schedule command."""

    request: ScheduleRequest
    state: ScheduleState
    root_operation_id: str
    root_schedule_kind: ScheduleKind
    root_scheduled_at: str
    root_matrix_revision: str
    root_matrix_fingerprint: str
    root_cycle_id: str | None
    root_journal_ref: str | None
    root_source_families: tuple[str, ...]
    root_instruction: HongKongV1DueCycleInstruction | None
    delivery_invocation_ids: tuple[str, ...]
    attempt_number: int
    attempt_operation_id: str


@dataclass(frozen=True, slots=True)
class ScheduleEnqueueResult:
    """Truthful durable-command projection; it never claims activity completion."""

    command_id: str
    command_fingerprint: str
    schedule_kind: ScheduleKind
    scheduled_at: str
    resolution: str
    state: ScheduleState
    operation_id: str
    root_schedule_kind: ScheduleKind
    root_scheduled_at: str
    matrix_revision: str
    matrix_fingerprint: str
    attempt_number: int
    cycle_id: str | None
    journal_ref: str | None
    source_families: tuple[str, ...]
    instruction: HongKongV1DueCycleInstruction | None
    delivery_invocation_ids: tuple[str, ...]


class LiveScheduleStore(Protocol):
    """Atomic retained command and active-operation port."""

    def claim(
        self, request: ScheduleRequest, invocation_id: str | None = None
    ) -> tuple[StoredScheduleCommand, bool]:
        """Retain or exactly replay one request; return whether it was a replay."""
        ...

    def mark_terminal(self, operation_id: str) -> StoredScheduleCommand | None:
        """Release one exact root and return any newly promoted waiting command."""
        ...

    def advance_retry(
        self, root_operation_id: str, completed_attempt_operation_id: str
    ) -> StoredScheduleCommand:
        """Atomically retain the next deterministic attempt for one active root."""
        ...

    def active_operation_ids(self) -> tuple[str, ...]:
        """Return stable active roots for scheduler reconciliation."""
        ...

    def active_commands(self) -> tuple[StoredScheduleCommand, ...]:
        """Return the exact retained active roots for restart reconciliation."""
        ...


class LiveSchedulerClient(Protocol):
    """Narrow Durable Task client surface used by the timer adapter."""

    def get_orchestration_state(self, instance_id: str) -> object | None:
        """Return an existing durable instance or ``None`` after scheduler loss."""
        ...

    def schedule_new_orchestration(
        self,
        orchestrator: str,
        *,
        input: object,  # noqa: A002 - exact Durable Task client keyword.
        instance_id: str,
        version: str,
    ) -> str:
        """Schedule one exact stable instance."""
        ...


class InMemoryLiveScheduleStore:
    """Thread-safe deterministic fake for the retained live schedule port."""

    def __init__(self) -> None:
        """Create empty test-only schedule state."""
        self._lock = threading.Lock()
        self._commands: dict[str, StoredScheduleCommand] = {}
        self._active: dict[str, StoredScheduleCommand] = {}

    def claim(
        self, request: ScheduleRequest, invocation_id: str | None = None
    ) -> tuple[StoredScheduleCommand, bool]:
        """Resolve duplicate and overlapping requests in one critical section."""
        if type(request) is not ScheduleRequest:
            _fail("SCHEDULE_REQUEST_INVALID")
        delivery_ids = _new_delivery_invocation_ids(invocation_id)
        with self._lock:
            prior = self._commands.get(request.command_id)
            if prior is not None:
                if prior.request.command_fingerprint != request.command_fingerprint:
                    _fail("SCHEDULE_COMMAND_CONFLICT")
                updated = _bind_delivery_invocations(prior, delivery_ids)
                self._commands[request.command_id] = updated
                active = self._active.get(request.activity_group)
                if active is not None and active.request.command_id == request.command_id:
                    self._active[request.activity_group] = updated
                return updated, True
            active = self._active.get(request.activity_group)
            if active is None:
                stored = StoredScheduleCommand(
                    request,
                    ScheduleState.STARTED,
                    request.operation_id,
                    request.kind,
                    request.scheduled_at,
                    request.matrix_revision,
                    request.matrix_fingerprint,
                    request.cycle_id,
                    request.journal_ref,
                    request.source_families,
                    request.instruction,
                    delivery_ids,
                    0,
                    request.operation_id,
                )
                self._active[request.activity_group] = stored
            else:
                stored = StoredScheduleCommand(
                    request,
                    ScheduleState.COALESCED_IN_PROGRESS,
                    active.root_operation_id,
                    active.root_schedule_kind,
                    active.root_scheduled_at,
                    active.root_matrix_revision,
                    active.root_matrix_fingerprint,
                    active.root_cycle_id,
                    active.root_journal_ref,
                    active.root_source_families,
                    active.root_instruction,
                    delivery_ids,
                    active.attempt_number,
                    active.attempt_operation_id,
                )
            self._commands[request.command_id] = stored
            return stored, False

    def mark_terminal(self, operation_id: str) -> StoredScheduleCommand | None:
        """Release an active group only when its exact root identity matches."""
        if type(operation_id) is not str or not operation_id:
            _fail("SCHEDULE_OPERATION_INVALID")
        with self._lock:
            matching = tuple(
                group
                for group, active in self._active.items()
                if active.root_operation_id == operation_id
            )
            if len(matching) != 1:
                _fail("SCHEDULE_OPERATION_NOT_ACTIVE")
            group = matching[0]
            del self._active[group]
            promoted = _promote_waiting_command(self._commands, group, operation_id)
            if promoted is not None:
                self._active[group] = promoted
            return promoted

    def advance_retry(
        self, root_operation_id: str, completed_attempt_operation_id: str
    ) -> StoredScheduleCommand:
        """Advance once, or replay a concurrently retained retry attempt."""
        _validate_retry_transition_ids(root_operation_id, completed_attempt_operation_id)
        with self._lock:
            group, active = _active_root(self._active, root_operation_id)
            updated = _advance_retry_command(active, completed_attempt_operation_id)
            if updated != active:
                self._active[group] = updated
                _replace_root_attempt(self._commands, active, updated)
            return updated

    @property
    def command_count(self) -> int:
        """Expose deterministic fake accounting to tests."""
        with self._lock:
            return len(self._commands)

    def active_operation_ids(self) -> tuple[str, ...]:
        """Return the sorted distinct active operation identities."""
        with self._lock:
            return tuple(sorted({item.attempt_operation_id for item in self._active.values()}))

    def active_commands(self) -> tuple[StoredScheduleCommand, ...]:
        """Return active roots in deterministic activity-group order."""
        with self._lock:
            return tuple(self._active[group] for group in sorted(self._active))

    @property
    def active_count(self) -> int:
        """Expose deterministic fake active ownership to tests."""
        with self._lock:
            return len(self._active)


class LocalLiveScheduleStore:
    """Process-safe retained local implementation for the prototype host."""

    def __init__(self, state_path: Path) -> None:
        """Bind one absolute retained local state file."""
        if not state_path.is_absolute():
            _fail("SCHEDULE_STATE_PATH_INVALID")
        self._state_path = state_path

    def claim(
        self, request: ScheduleRequest, invocation_id: str | None = None
    ) -> tuple[StoredScheduleCommand, bool]:
        """Resolve one request under a process-shared exclusive file lock."""
        if type(request) is not ScheduleRequest:
            _fail("SCHEDULE_REQUEST_INVALID")
        delivery_ids = _new_delivery_invocation_ids(invocation_id)
        with exclusive_local_state_lock(self._state_path):
            commands, active = self._read_state()
            prior = commands.get(request.command_id)
            if prior is not None:
                if prior.request.command_fingerprint != request.command_fingerprint:
                    _fail("SCHEDULE_COMMAND_CONFLICT")
                updated = _bind_delivery_invocations(prior, delivery_ids)
                if updated != prior:
                    commands[request.command_id] = updated
                    self._write_state(commands, active)
                return updated, True
            active_command_id = active.get(request.activity_group)
            active_command = commands.get(active_command_id) if active_command_id else None
            if active_command_id is not None and active_command is None:
                _fail("SCHEDULE_STATE_INVALID")
            if active_command is None:
                stored = StoredScheduleCommand(
                    request,
                    ScheduleState.STARTED,
                    request.operation_id,
                    request.kind,
                    request.scheduled_at,
                    request.matrix_revision,
                    request.matrix_fingerprint,
                    request.cycle_id,
                    request.journal_ref,
                    request.source_families,
                    request.instruction,
                    delivery_ids,
                    0,
                    request.operation_id,
                )
                active[request.activity_group] = request.command_id
            else:
                stored = StoredScheduleCommand(
                    request,
                    ScheduleState.COALESCED_IN_PROGRESS,
                    active_command.root_operation_id,
                    active_command.root_schedule_kind,
                    active_command.root_scheduled_at,
                    active_command.root_matrix_revision,
                    active_command.root_matrix_fingerprint,
                    active_command.root_cycle_id,
                    active_command.root_journal_ref,
                    active_command.root_source_families,
                    active_command.root_instruction,
                    delivery_ids,
                    active_command.attempt_number,
                    active_command.attempt_operation_id,
                )
            commands[request.command_id] = stored
            self._write_state(commands, active)
            return stored, False

    def mark_terminal(self, operation_id: str) -> StoredScheduleCommand | None:
        """Persist release of one exact active root operation."""
        if type(operation_id) is not str or not operation_id:
            _fail("SCHEDULE_OPERATION_INVALID")
        with exclusive_local_state_lock(self._state_path):
            commands, active = self._read_state()
            matching = tuple(
                group
                for group, command_id in active.items()
                if commands[command_id].root_operation_id == operation_id
            )
            if len(matching) != 1:
                _fail("SCHEDULE_OPERATION_NOT_ACTIVE")
            group = matching[0]
            del active[group]
            promoted = _promote_waiting_command(commands, group, operation_id)
            if promoted is not None:
                active[group] = promoted.request.command_id
            self._write_state(commands, active)
            return promoted

    def advance_retry(
        self, root_operation_id: str, completed_attempt_operation_id: str
    ) -> StoredScheduleCommand:
        """Persist one deterministic retry transition under the state lock."""
        _validate_retry_transition_ids(root_operation_id, completed_attempt_operation_id)
        with exclusive_local_state_lock(self._state_path):
            commands, active_ids = self._read_state()
            active_commands = {
                group: commands[command_id] for group, command_id in active_ids.items()
            }
            _group, active = _active_root(active_commands, root_operation_id)
            updated = _advance_retry_command(active, completed_attempt_operation_id)
            if updated != active:
                _replace_root_attempt(commands, active, updated)
                self._write_state(commands, active_ids)
            return updated

    def _read_state(self) -> tuple[dict[str, StoredScheduleCommand], dict[str, str]]:
        if self._state_path.is_symlink():
            _fail("SCHEDULE_STATE_INVALID")
        if not self._state_path.exists():
            return {}, {}
        if not self._state_path.is_file():
            _fail("SCHEDULE_STATE_INVALID")
        try:
            document = parse_json_bytes(
                self._state_path.read_bytes(), max_bytes=_MAX_SCHEDULE_STATE_BYTES
            )
            result = _decode_state(document)
        except LiveScheduleError:
            raise
        except Exception as error:
            message = "SCHEDULE_STATE_INVALID"
            raise LiveScheduleError(message) from error
        else:
            return result

    def active_operation_ids(self) -> tuple[str, ...]:
        """Read sorted active roots under the same process-shared lock."""
        with exclusive_local_state_lock(self._state_path):
            commands, active = self._read_state()
            return tuple(
                sorted(
                    {commands[command_id].attempt_operation_id for command_id in active.values()}
                )
            )

    def active_commands(self) -> tuple[StoredScheduleCommand, ...]:
        """Read exact active roots under the same process-shared lock."""
        with exclusive_local_state_lock(self._state_path):
            commands, active = self._read_state()
            return tuple(commands[active[group]] for group in sorted(active))

    def _write_state(
        self,
        commands: dict[str, StoredScheduleCommand],
        active: dict[str, str],
    ) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        body: dict[str, JsonValue] = {
            "schema_id": "asklegal.hk-v1-live-schedule-state",
            "schema_version": "1.3.0",
            "commands": [_stored_to_json(commands[command_id]) for command_id in sorted(commands)],
            "active": {group: active[group] for group in sorted(active)},
        }
        document = dict(body)
        document["fingerprint"] = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
        content = canonicalize(document) + b"\n"
        temporary = self._state_path.with_name(f".{self._state_path.name}.{token_hex(16)}.tmp")
        try:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self._state_path)
            directory = os.open(self._state_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            if self._state_path.read_bytes() != content:
                _fail("SCHEDULE_STATE_WRITE_FAILED")
        finally:
            with suppress(FileNotFoundError):
                temporary.unlink()


class UnavailableMaintenanceActivities:
    """Fail-visible boundaries until capability-owning local adapters are composed."""

    def perform_hk_v1_audit_archive(self, _context: ActivityContext, payload: object) -> object:
        """Reject rather than claim an unavailable audit export."""
        _maintenance_request(payload, ScheduleKind.AUDIT_ARCHIVE)
        _fail("HK_V1_AUDIT_ARCHIVE_ADAPTER_UNAVAILABLE")

    def perform_hk_v1_recovery_verification(
        self, _context: ActivityContext, payload: object
    ) -> object:
        """Reject rather than claim an unavailable recovery proof."""
        _maintenance_request(payload, ScheduleKind.RECOVERY_VERIFY)
        _fail("HK_V1_RECOVERY_VERIFICATION_ADAPTER_UNAVAILABLE")

    def perform_hk_v1_telemetry_retention(
        self, _context: ActivityContext, payload: object
    ) -> object:
        """Reject rather than claim unavailable telemetry retention."""
        _maintenance_request(payload, ScheduleKind.TELEMETRY_RETENTION)
        _fail("HK_V1_TELEMETRY_RETENTION_ADAPTER_UNAVAILABLE")


def run_hk_v1_audit_archive(
    context: OrchestrationContext, payload: object
) -> Generator[Task[object], object, object]:
    """Dispatch one retained audit request through its named activity boundary."""
    result = yield context.call_activity(MAINTENANCE_ACTIVITIES[0], input=payload)
    return result


def run_hk_v1_recovery_verification(
    context: OrchestrationContext, payload: object
) -> Generator[Task[object], object, object]:
    """Dispatch one retained recovery request through its named activity boundary."""
    result = yield context.call_activity(MAINTENANCE_ACTIVITIES[1], input=payload)
    return result


def run_hk_v1_telemetry_retention(
    context: OrchestrationContext, payload: object
) -> Generator[Task[object], object, object]:
    """Dispatch one retained telemetry request through its named activity boundary."""
    result = yield context.call_activity(MAINTENANCE_ACTIVITIES[2], input=payload)
    return result


def schedule_definitions() -> tuple[ScheduleDefinition, ...]:
    """Return the closed ordered V1 schedule catalogue."""
    return _DEFINITIONS


def applicable_schedule_slot(kind: ScheduleKind, now: datetime) -> str:
    """Resolve the latest applicable calendar slot from an adapter-supplied time."""
    if type(kind) is not ScheduleKind or type(now) is not datetime:
        _fail("SCHEDULE_SLOT_INVALID")
    if now.tzinfo is None or now.utcoffset() is None:
        _fail("SCHEDULE_SLOT_INVALID")
    definition = _BY_KIND[kind]
    local = now.astimezone(UTC) + _HONG_KONG_OFFSET
    candidate = local.replace(
        hour=definition.hour,
        minute=definition.minute,
        second=0,
        microsecond=0,
    )
    if definition.weekday is not None:
        candidate -= timedelta(days=(candidate.weekday() - definition.weekday) % 7)
    if candidate > local:
        candidate -= timedelta(days=7 if definition.weekday is not None else 1)
    return candidate.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def validate_systemd_invocation_id(value: object) -> str:
    """Validate one non-null lowercase systemd ID128 delivery identity."""
    if (
        type(value) is not str
        or _SYSTEMD_INVOCATION_ID.fullmatch(value) is None
        or value == "0" * 32
    ):
        _fail("SCHEDULE_INVOCATION_ID_INVALID")
    return value


def _new_delivery_invocation_ids(invocation_id: str | None) -> tuple[str, ...]:
    if invocation_id is None:
        return ()
    return (validate_systemd_invocation_id(invocation_id),)


def _bind_delivery_invocations(
    stored: StoredScheduleCommand,
    delivery_invocation_ids: tuple[str, ...],
) -> StoredScheduleCommand:
    if not delivery_invocation_ids:
        return stored
    combined = tuple(sorted({*stored.delivery_invocation_ids, *delivery_invocation_ids}))
    return replace(stored, delivery_invocation_ids=combined)


def schedule_request(
    kind: ScheduleKind,
    scheduled_at: str,
    *,
    matrix: HongKongV1CoverageMatrix,
) -> ScheduleRequest:
    """Derive stable command and operation identities from one exact HK slot."""
    if type(kind) is not ScheduleKind:
        _fail("SCHEDULE_KIND_INVALID")
    _validate_matrix(matrix)
    definition = _BY_KIND[kind]
    local = _slot(scheduled_at, definition)
    slot_body: dict[str, JsonValue] = {
        "schedule_kind": kind.value,
        "scheduled_at": scheduled_at,
        "timezone": "Asia/Hong_Kong",
    }
    digest = sha256(canonicalize(slot_body)).hexdigest()
    command_id = f"cmd_{digest[:48]}"
    command_fingerprint = _expected_command_fingerprint(
        kind,
        scheduled_at,
        matrix.revision,
        matrix.fingerprint,
    )
    if definition.due_cycle_kind is None:
        operation_id = f"op_{digest}"
        return ScheduleRequest(
            command_id,
            command_fingerprint,
            matrix.revision,
            matrix.fingerprint,
            kind,
            scheduled_at,
            definition.activity_group,
            operation_id,
            None,
            None,
            (),
            None,
        )
    cycle_digest = sha256(
        canonicalize(
            {
                "cycle_kind": definition.due_cycle_kind.value,
                "schedule_kind": kind.value,
                "scheduled_at": scheduled_at,
                "timezone": "Asia/Hong_Kong",
            }
        )
    ).hexdigest()
    cycle_id = f"cyc_{cycle_digest}"
    cutoff = local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    instruction = HongKongV1DueCycleInstruction(
        cycle_id,
        definition.due_cycle_kind,
        cutoff,
        cutoff,
        matrix.revision,
        matrix.fingerprint,
    )
    return ScheduleRequest(
        command_id,
        command_fingerprint,
        matrix.revision,
        matrix.fingerprint,
        kind,
        scheduled_at,
        definition.activity_group,
        cycle_id,
        cycle_id,
        f"acquisition-journals/{cycle_id}",
        _SOURCE_FAMILIES,
        instruction,
    )


def enqueue_schedule(
    store: LiveScheduleStore,
    kind: ScheduleKind,
    scheduled_at: str,
    *,
    matrix: HongKongV1CoverageMatrix,
    invocation_id: str | None = None,
) -> ScheduleEnqueueResult:
    """Atomically retain or replay one slot without claiming task completion."""
    if not callable(getattr(store, "claim", None)):
        _fail("SCHEDULE_STORE_INVALID")
    request = schedule_request(kind, scheduled_at, matrix=matrix)
    stored, replayed = store.claim(request, invocation_id)
    if type(stored) is not StoredScheduleCommand or type(replayed) is not bool:
        _fail("SCHEDULE_STORE_RESULT_INVALID")
    return ScheduleEnqueueResult(
        command_id=request.command_id,
        command_fingerprint=request.command_fingerprint,
        schedule_kind=request.kind,
        scheduled_at=request.scheduled_at,
        resolution="EXACT_REPLAY" if replayed else "RESULT_RECORDED",
        state=stored.state,
        operation_id=stored.attempt_operation_id,
        root_schedule_kind=stored.root_schedule_kind,
        root_scheduled_at=stored.root_scheduled_at,
        matrix_revision=stored.root_matrix_revision,
        matrix_fingerprint=stored.root_matrix_fingerprint,
        attempt_number=stored.attempt_number,
        cycle_id=stored.root_cycle_id,
        journal_ref=stored.root_journal_ref,
        source_families=stored.root_source_families,
        instruction=stored.root_instruction,
        delivery_invocation_ids=stored.delivery_invocation_ids,
    )


def mark_schedule_terminal(store: LiveScheduleStore, operation_id: str) -> None:
    """Release one exact operation through the retained-state port."""
    if not callable(getattr(store, "mark_terminal", None)):
        _fail("SCHEDULE_STORE_INVALID")
    store.mark_terminal(operation_id)


def release_terminal_schedules(
    store: LiveScheduleStore, client: LiveSchedulerClient
) -> tuple[ScheduleEnqueueResult, ...]:
    """Resume absent attempts and release only semantically completed roots."""
    if not callable(getattr(store, "active_commands", None)) or not callable(
        getattr(client, "get_orchestration_state", None)
    ):
        _fail("SCHEDULE_RECONCILIATION_INVALID")
    try:
        active_commands = store.active_commands()
        resumable: list[ScheduleEnqueueResult] = []
        for active in active_commands:
            resumable.extend(_reconcile_active_schedule(store, client, active))
    except LiveScheduleError:
        raise
    except Exception as error:
        message = "SCHEDULE_RECONCILIATION_FAILED"
        raise LiveScheduleError(message) from error
    else:
        return tuple(resumable)


def _reconcile_active_schedule(
    store: LiveScheduleStore,
    client: LiveSchedulerClient,
    active: StoredScheduleCommand,
) -> tuple[ScheduleEnqueueResult, ...]:
    if type(active) is not StoredScheduleCommand or active.state is not ScheduleState.STARTED:
        _fail("SCHEDULE_RECONCILIATION_INVALID")
    operation_id = active.attempt_operation_id
    state = client.get_orchestration_state(operation_id)
    if state is None:
        return (_started_result(active, resolution="RESULT_RESUMED"),)
    status = getattr(state, "runtime_status", None)
    if type(status) is not OrchestrationStatus:
        _fail("SCHEDULE_RECONCILIATION_INVALID")
    retry = status in {OrchestrationStatus.FAILED, OrchestrationStatus.TERMINATED}
    if status is OrchestrationStatus.COMPLETED and active.root_instruction is not None:
        retry = not _due_cycle_is_terminal_success(state, active)
    if retry:
        retried = store.advance_retry(active.root_operation_id, operation_id)
        return (_started_result(retried, resolution="RESULT_RETRY"),)
    if status is OrchestrationStatus.COMPLETED:
        waiting = store.mark_terminal(active.root_operation_id)
        if waiting is not None:
            return (_started_result(waiting, resolution="RESULT_PROMOTED"),)
    return ()


def _due_cycle_is_terminal_success(state: object, active: StoredScheduleCommand) -> bool:
    serialized = getattr(state, "serialized_output", None)
    if type(serialized) is not str or not serialized:
        return False
    try:
        output = parse_json_bytes(serialized.encode("utf-8"), max_bytes=_MAX_SCHEDULE_STATE_BYTES)
    except Exception as error:
        message = "SCHEDULE_RECONCILIATION_INVALID"
        raise LiveScheduleError(message) from error
    if type(output) is not dict:
        _fail("SCHEDULE_RECONCILIATION_INVALID")
    acceptance_value = output.get("acceptance")
    if acceptance_value is None:
        return False
    try:
        acceptance = validate_hk_v1_acceptance_cycle_result(acceptance_value)
    except Exception as error:
        message = "SCHEDULE_RECONCILIATION_INVALID"
        raise LiveScheduleError(message) from error
    instruction = active.root_instruction
    if instruction is None or acceptance["observation_cutoff"] != instruction.observation_cutoff:
        _fail("SCHEDULE_RECONCILIATION_INVALID")
    return acceptance["result"] in {"NO_CHANGE", "PROPOSAL_READY"}


def _started_result(stored: StoredScheduleCommand, *, resolution: str) -> ScheduleEnqueueResult:
    if type(stored) is not StoredScheduleCommand or stored.state is not ScheduleState.STARTED:
        _fail("SCHEDULE_STORE_RESULT_INVALID")
    if resolution not in {"RESULT_PROMOTED", "RESULT_RESUMED", "RESULT_RETRY"}:
        _fail("SCHEDULE_STORE_RESULT_INVALID")
    request = stored.request
    return ScheduleEnqueueResult(
        command_id=request.command_id,
        command_fingerprint=request.command_fingerprint,
        schedule_kind=request.kind,
        scheduled_at=request.scheduled_at,
        resolution=resolution,
        state=stored.state,
        operation_id=stored.attempt_operation_id,
        root_schedule_kind=stored.root_schedule_kind,
        root_scheduled_at=stored.root_scheduled_at,
        matrix_revision=stored.root_matrix_revision,
        matrix_fingerprint=stored.root_matrix_fingerprint,
        attempt_number=stored.attempt_number,
        cycle_id=stored.root_cycle_id,
        journal_ref=stored.root_journal_ref,
        source_families=stored.root_source_families,
        instruction=stored.root_instruction,
        delivery_invocation_ids=stored.delivery_invocation_ids,
    )


def dispatch_schedule(client: LiveSchedulerClient, result: ScheduleEnqueueResult) -> str:
    """Ensure one exact durable instance exists, without claiming task completion."""
    if (
        type(result) is not ScheduleEnqueueResult
        or not callable(getattr(client, "get_orchestration_state", None))
        or not callable(getattr(client, "schedule_new_orchestration", None))
    ):
        _fail("SCHEDULE_DISPATCH_INVALID")
    try:
        if client.get_orchestration_state(result.operation_id) is not None:
            return "INSTANCE_PRESENT"
        orchestration = {
            ScheduleKind.OBSERVATION: "run_hk_v1_due_cycle",
            ScheduleKind.RECONCILIATION: "run_hk_v1_due_cycle",
            ScheduleKind.AUDIT_ARCHIVE: "run_hk_v1_audit_archive",
            ScheduleKind.RECOVERY_VERIFY: "run_hk_v1_recovery_verification",
            ScheduleKind.TELEMETRY_RETENTION: "run_hk_v1_telemetry_retention",
        }[result.root_schedule_kind]
        payload = _dispatch_payload(result)
        instance_id = client.schedule_new_orchestration(
            orchestration,
            input=payload,
            instance_id=result.operation_id,
            version="1.0.0",
        )
        if type(instance_id) is not str or instance_id != result.operation_id:
            _fail("SCHEDULE_DISPATCH_INVALID")
        resolution = "SCHEDULED"
    except LiveScheduleError:
        raise
    except Exception as error:
        try:
            existing = client.get_orchestration_state(result.operation_id)
        except Exception:  # noqa: BLE001 - second hostile scheduler read is best effort only.
            existing = None
        if existing is not None:
            return "INSTANCE_PRESENT"
        message = "SCHEDULE_DISPATCH_FAILED"
        raise LiveScheduleError(message) from error
    else:
        return resolution


def _dispatch_payload(result: ScheduleEnqueueResult) -> dict[str, object]:
    instruction = result.instruction
    if instruction is not None:
        return {
            "cycle_id": instruction.cycle_id,
            "cycle_kind": instruction.cycle_kind.value,
            "scheduled_at": instruction.scheduled_at,
            "observation_cutoff": instruction.observation_cutoff,
            "matrix_revision": instruction.matrix_revision,
            "matrix_fingerprint": instruction.matrix_fingerprint,
        }
    return {
        "command_id": _command_id(result.root_schedule_kind, result.root_scheduled_at),
        "command_fingerprint": _expected_command_fingerprint(
            result.root_schedule_kind,
            result.root_scheduled_at,
            result.matrix_revision,
            result.matrix_fingerprint,
        ),
        "matrix_revision": result.matrix_revision,
        "matrix_fingerprint": result.matrix_fingerprint,
        "attempt_number": result.attempt_number,
        "operation_id": result.operation_id,
        "schedule_kind": result.root_schedule_kind.value,
        "scheduled_at": result.root_scheduled_at,
        "state": "REQUESTED",
    }


def _maintenance_request(value: object, expected: ScheduleKind) -> dict[str, JsonValue]:
    document = _exact_object(
        value,
        {
            "command_id",
            "command_fingerprint",
            "matrix_revision",
            "matrix_fingerprint",
            "attempt_number",
            "operation_id",
            "schedule_kind",
            "scheduled_at",
            "state",
        },
    )
    attempt_number = document["attempt_number"]
    scheduled_at = _text(document["scheduled_at"])
    if (
        document["schedule_kind"] != expected.value
        or document["state"] != "REQUESTED"
        or type(attempt_number) is not int
        or attempt_number < 0
        or document["command_id"] != _command_id(expected, scheduled_at)
        or document["command_fingerprint"]
        != _expected_command_fingerprint(
            expected,
            scheduled_at,
            _text(document["matrix_revision"]),
            _text(document["matrix_fingerprint"]),
        )
        or document["operation_id"]
        != schedule_attempt_operation_id(expected, scheduled_at, attempt_number)
    ):
        _fail("HK_V1_MAINTENANCE_REQUEST_INVALID")
    definition = _BY_KIND[expected]
    _slot(scheduled_at, definition)
    for field in (
        "command_id",
        "command_fingerprint",
        "matrix_revision",
        "matrix_fingerprint",
        "operation_id",
    ):
        _text(document[field])
    return document


def _stored_to_json(stored: StoredScheduleCommand) -> dict[str, JsonValue]:
    return {
        "request": _request_to_json(stored.request),
        "delivery_invocation_ids": list(stored.delivery_invocation_ids),
        "state": stored.state.value,
        "root_operation_id": stored.root_operation_id,
        "root_schedule_kind": stored.root_schedule_kind.value,
        "root_scheduled_at": stored.root_scheduled_at,
        "root_matrix_revision": stored.root_matrix_revision,
        "root_matrix_fingerprint": stored.root_matrix_fingerprint,
        "root_cycle_id": stored.root_cycle_id,
        "root_journal_ref": stored.root_journal_ref,
        "root_source_families": list(stored.root_source_families),
        "root_instruction": _instruction_to_json(stored.root_instruction),
        "attempt_number": stored.attempt_number,
        "attempt_operation_id": stored.attempt_operation_id,
    }


def _request_to_json(request: ScheduleRequest) -> dict[str, JsonValue]:
    return {
        "command_id": request.command_id,
        "command_fingerprint": request.command_fingerprint,
        "matrix_revision": request.matrix_revision,
        "matrix_fingerprint": request.matrix_fingerprint,
        "kind": request.kind.value,
        "scheduled_at": request.scheduled_at,
        "activity_group": request.activity_group,
        "operation_id": request.operation_id,
        "cycle_id": request.cycle_id,
        "journal_ref": request.journal_ref,
        "source_families": list(request.source_families),
        "instruction": _instruction_to_json(request.instruction),
    }


def _instruction_to_json(
    instruction: HongKongV1DueCycleInstruction | None,
) -> dict[str, JsonValue] | None:
    if instruction is None:
        return None
    return {
        "cycle_id": instruction.cycle_id,
        "cycle_kind": instruction.cycle_kind.value,
        "scheduled_at": instruction.scheduled_at,
        "observation_cutoff": instruction.observation_cutoff,
        "matrix_revision": instruction.matrix_revision,
        "matrix_fingerprint": instruction.matrix_fingerprint,
    }


def _decode_state(
    value: object,
) -> tuple[dict[str, StoredScheduleCommand], dict[str, str]]:
    document = _exact_object(
        value,
        {"schema_id", "schema_version", "commands", "active", "fingerprint"},
    )
    version = document["schema_version"]
    if (
        document["schema_id"] != "asklegal.hk-v1-live-schedule-state"
        or version not in {"1.2.0", "1.3.0"}
        or type(document["fingerprint"]) is not str
    ):
        _fail("SCHEDULE_STATE_INVALID")
    unsigned = dict(document)
    fingerprint = unsigned.pop("fingerprint")
    if fingerprint != f"sha256:{sha256(canonicalize(unsigned)).hexdigest()}":
        _fail("SCHEDULE_STATE_INVALID")
    raw_commands = document["commands"]
    raw_active = document["active"]
    if type(raw_commands) is not list or type(raw_active) is not dict:
        _fail("SCHEDULE_STATE_INVALID")
    commands = _decode_commands(raw_commands, version)
    active = _decode_active(raw_active, commands)
    _validate_waiting_commands(commands, active)
    return commands, active


def parse_live_schedule_state_bytes(
    content: bytes,
) -> tuple[tuple[StoredScheduleCommand, ...], tuple[str, ...]]:
    """Parse canonical retained schedule bytes for independent read-only evidence."""
    if type(content) is not bytes or not content or len(content) > _MAX_SCHEDULE_STATE_BYTES:
        _fail("SCHEDULE_STATE_INVALID")
    try:
        document = parse_json_bytes(content, max_bytes=_MAX_SCHEDULE_STATE_BYTES)
        if canonicalize(document) + b"\n" != content:
            _fail("SCHEDULE_STATE_INVALID")
        commands, active = _decode_state(document)
    except LiveScheduleError:
        raise
    except Exception as error:
        message = "SCHEDULE_STATE_INVALID"
        raise LiveScheduleError(message) from error
    return (
        tuple(commands[command_id] for command_id in sorted(commands)),
        tuple(active[group] for group in sorted(active)),
    )


def _promote_waiting_command(
    commands: dict[str, StoredScheduleCommand],
    activity_group: str,
    terminal_operation_id: str,
) -> StoredScheduleCommand | None:
    waiting = tuple(
        stored
        for stored in commands.values()
        if stored.state is ScheduleState.COALESCED_IN_PROGRESS
        and stored.request.activity_group == activity_group
        and stored.root_operation_id == terminal_operation_id
    )
    if not waiting:
        return None
    selected = min(waiting, key=lambda item: (item.request.scheduled_at, item.request.command_id))
    promoted = _started_command(selected.request, selected.delivery_invocation_ids)
    commands[promoted.request.command_id] = promoted
    for stored in waiting:
        if stored.request.command_id != promoted.request.command_id:
            commands[stored.request.command_id] = _coalesced_command(
                stored.request,
                promoted,
                stored.delivery_invocation_ids,
            )
    return promoted


def _validate_retry_transition_ids(root_operation_id: str, attempt_operation_id: str) -> None:
    if (
        type(root_operation_id) is not str
        or not root_operation_id
        or type(attempt_operation_id) is not str
        or not attempt_operation_id
    ):
        _fail("SCHEDULE_OPERATION_INVALID")


def _active_root(
    active: dict[str, StoredScheduleCommand], root_operation_id: str
) -> tuple[str, StoredScheduleCommand]:
    matches = tuple(
        (group, command)
        for group, command in active.items()
        if command.root_operation_id == root_operation_id
    )
    if len(matches) != 1:
        _fail("SCHEDULE_OPERATION_NOT_ACTIVE")
    return matches[0]


def _advance_retry_command(
    active: StoredScheduleCommand, completed_attempt_operation_id: str
) -> StoredScheduleCommand:
    if active.attempt_operation_id != completed_attempt_operation_id:
        if active.attempt_number == 0 or completed_attempt_operation_id != _attempt_operation_id(
            active.root_operation_id, active.attempt_number - 1
        ):
            _fail("SCHEDULE_RETRY_CONFLICT")
        return active
    attempt_number = active.attempt_number + 1
    return replace(
        active,
        attempt_number=attempt_number,
        attempt_operation_id=_attempt_operation_id(active.root_operation_id, attempt_number),
    )


def _replace_root_attempt(
    commands: dict[str, StoredScheduleCommand],
    prior: StoredScheduleCommand,
    updated: StoredScheduleCommand,
) -> None:
    for command_id, command in tuple(commands.items()):
        if (
            command.request.activity_group == prior.request.activity_group
            and command.root_operation_id == prior.root_operation_id
        ):
            commands[command_id] = replace(
                command,
                attempt_number=updated.attempt_number,
                attempt_operation_id=updated.attempt_operation_id,
            )


def _attempt_operation_id(root_operation_id: str, attempt_number: int) -> str:
    if attempt_number == 0:
        return root_operation_id
    digest = sha256(
        canonicalize(
            {
                "schema_id": "asklegal.hk-v1-schedule-attempt/v1",
                "root_operation_id": root_operation_id,
                "attempt_number": attempt_number,
            }
        )
    ).hexdigest()
    return f"att_{digest}"


def schedule_attempt_operation_id(
    kind: ScheduleKind,
    scheduled_at: str,
    attempt_number: int,
) -> str:
    """Derive the exact retained operation identity for one schedule attempt."""
    if type(kind) is not ScheduleKind or type(attempt_number) is not int or attempt_number < 0:
        _fail("SCHEDULE_OPERATION_INVALID")
    definition = _BY_KIND[kind]
    _slot(scheduled_at, definition)
    return _attempt_operation_id(
        _operation_id(kind, scheduled_at, definition),
        attempt_number,
    )


def _started_command(
    request: ScheduleRequest,
    delivery_invocation_ids: tuple[str, ...],
) -> StoredScheduleCommand:
    return StoredScheduleCommand(
        request,
        ScheduleState.STARTED,
        request.operation_id,
        request.kind,
        request.scheduled_at,
        request.matrix_revision,
        request.matrix_fingerprint,
        request.cycle_id,
        request.journal_ref,
        request.source_families,
        request.instruction,
        delivery_invocation_ids,
        0,
        request.operation_id,
    )


def _coalesced_command(
    request: ScheduleRequest,
    root: StoredScheduleCommand,
    delivery_invocation_ids: tuple[str, ...],
) -> StoredScheduleCommand:
    return StoredScheduleCommand(
        request,
        ScheduleState.COALESCED_IN_PROGRESS,
        root.root_operation_id,
        root.root_schedule_kind,
        root.root_scheduled_at,
        root.root_matrix_revision,
        root.root_matrix_fingerprint,
        root.root_cycle_id,
        root.root_journal_ref,
        root.root_source_families,
        root.root_instruction,
        delivery_invocation_ids,
        root.attempt_number,
        root.attempt_operation_id,
    )


def _validate_waiting_commands(
    commands: dict[str, StoredScheduleCommand],
    active: dict[str, str],
) -> None:
    for stored in commands.values():
        if stored.state is not ScheduleState.COALESCED_IN_PROGRESS:
            continue
        active_id = active.get(stored.request.activity_group)
        root = commands.get(active_id) if active_id is not None else None
        if root is None or root.state is not ScheduleState.STARTED:
            _fail("SCHEDULE_STATE_INVALID")
        expected = _coalesced_command(stored.request, root, stored.delivery_invocation_ids)
        if stored != expected:
            _fail("SCHEDULE_STATE_INVALID")


def _decode_commands(
    values: list[JsonValue], state_version: str
) -> dict[str, StoredScheduleCommand]:
    commands: dict[str, StoredScheduleCommand] = {}
    for value in values:
        stored = _stored_from_json(value, state_version)
        if stored.request.command_id in commands:
            _fail("SCHEDULE_STATE_INVALID")
        commands[stored.request.command_id] = stored
    return commands


def _decode_active(
    values: dict[str, JsonValue],
    commands: dict[str, StoredScheduleCommand],
) -> dict[str, str]:
    active: dict[str, str] = {}
    for group, command_id in values.items():
        if type(command_id) is not str:
            _fail("SCHEDULE_STATE_INVALID")
        command = commands.get(command_id)
        if (
            command is None
            or command.request.activity_group != group
            or command.state is not ScheduleState.STARTED
        ):
            _fail("SCHEDULE_STATE_INVALID")
        active[group] = command_id
    return active


def _stored_from_json(value: object, state_version: str) -> StoredScheduleCommand:
    try:
        fields = {
            "request",
            "state",
            "root_operation_id",
            "root_schedule_kind",
            "root_scheduled_at",
            "root_matrix_revision",
            "root_matrix_fingerprint",
            "root_cycle_id",
            "root_journal_ref",
            "root_source_families",
            "root_instruction",
            "delivery_invocation_ids",
        }
        if state_version == "1.3.0":
            fields.update({"attempt_number", "attempt_operation_id"})
        document = _exact_object(
            value,
            fields,
        )
        request = _request_from_json(document["request"])
        attempt_number = (
            _nonnegative_int(document["attempt_number"]) if state_version == "1.3.0" else 0
        )
        attempt_operation_id = (
            _text(document["attempt_operation_id"])
            if state_version == "1.3.0"
            else _text(document["root_operation_id"])
        )
        stored = StoredScheduleCommand(
            request,
            ScheduleState(_text(document["state"])),
            _text(document["root_operation_id"]),
            ScheduleKind(_text(document["root_schedule_kind"])),
            _text(document["root_scheduled_at"]),
            _text(document["root_matrix_revision"]),
            _matrix_fingerprint(document["root_matrix_fingerprint"]),
            _optional_text(document["root_cycle_id"]),
            _optional_text(document["root_journal_ref"]),
            _families(document["root_source_families"]),
            _instruction_from_json(document["root_instruction"]),
            _invocation_ids(document["delivery_invocation_ids"]),
            attempt_number,
            attempt_operation_id,
        )
        _validate_stored_root(stored)
        result = stored
    except LiveScheduleError:
        raise
    except Exception as error:
        message = "SCHEDULE_STATE_INVALID"
        raise LiveScheduleError(message) from error
    else:
        return result


def _request_from_json(value: object) -> ScheduleRequest:
    document = _exact_object(
        value,
        {
            "command_id",
            "command_fingerprint",
            "matrix_revision",
            "matrix_fingerprint",
            "kind",
            "scheduled_at",
            "activity_group",
            "operation_id",
            "cycle_id",
            "journal_ref",
            "source_families",
            "instruction",
        },
    )
    request = ScheduleRequest(
        _text(document["command_id"]),
        _text(document["command_fingerprint"]),
        _text(document["matrix_revision"]),
        _matrix_fingerprint(document["matrix_fingerprint"]),
        ScheduleKind(_text(document["kind"])),
        _text(document["scheduled_at"]),
        _text(document["activity_group"]),
        _text(document["operation_id"]),
        _optional_text(document["cycle_id"]),
        _optional_text(document["journal_ref"]),
        _families(document["source_families"]),
        _instruction_from_json(document["instruction"]),
    )
    definition = _BY_KIND[request.kind]
    _slot(request.scheduled_at, definition)
    expected_digest = sha256(
        canonicalize(
            {
                "schedule_kind": request.kind.value,
                "scheduled_at": request.scheduled_at,
                "timezone": "Asia/Hong_Kong",
            }
        )
    ).hexdigest()
    if (
        request.command_id != f"cmd_{expected_digest[:48]}"
        or request.activity_group != definition.activity_group
        or request.source_families != definition.source_families
    ):
        _fail("SCHEDULE_STATE_INVALID")
    _validate_request_operation(request, definition)
    if request.command_fingerprint != _expected_command_fingerprint(
        request.kind,
        request.scheduled_at,
        request.matrix_revision,
        request.matrix_fingerprint,
    ):
        _fail("SCHEDULE_STATE_INVALID")
    return request


def _expected_command_fingerprint(
    kind: ScheduleKind,
    scheduled_at: str,
    matrix_revision: str,
    matrix_fingerprint: str,
) -> str:
    body: dict[str, JsonValue] = {
        "schedule_kind": kind.value,
        "scheduled_at": scheduled_at,
        "timezone": "Asia/Hong_Kong",
        "matrix_revision": matrix_revision,
        "matrix_fingerprint": matrix_fingerprint,
    }
    return f"sha256:{sha256(canonicalize(body)).hexdigest()}"


def _validate_request_operation(request: ScheduleRequest, definition: ScheduleDefinition) -> None:
    operation_id = _operation_id(request.kind, request.scheduled_at, definition)
    if definition.due_cycle_kind is None:
        if (
            request.operation_id != operation_id
            or request.cycle_id is not None
            or request.journal_ref is not None
            or request.instruction is not None
        ):
            _fail("SCHEDULE_STATE_INVALID")
        return
    instruction = request.instruction
    if (
        instruction is None
        or request.operation_id != operation_id
        or request.cycle_id != operation_id
        or request.journal_ref != f"acquisition-journals/{operation_id}"
        or instruction.cycle_id != operation_id
        or instruction.cycle_kind is not definition.due_cycle_kind
        or instruction.matrix_revision != request.matrix_revision
        or instruction.matrix_fingerprint != request.matrix_fingerprint
    ):
        _fail("SCHEDULE_STATE_INVALID")
    expected_cutoff = (
        _slot(request.scheduled_at, definition).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    if (
        instruction.scheduled_at != expected_cutoff
        or instruction.observation_cutoff != expected_cutoff
    ):
        _fail("SCHEDULE_STATE_INVALID")


def _validate_stored_root(stored: StoredScheduleCommand) -> None:
    definition = _BY_KIND[stored.root_schedule_kind]
    _slot(stored.root_scheduled_at, definition)
    if (
        definition.activity_group != stored.request.activity_group
        or stored.root_source_families != definition.source_families
    ):
        _fail("SCHEDULE_STATE_INVALID")
    root_request = ScheduleRequest(
        stored.request.command_id,
        stored.request.command_fingerprint,
        stored.root_matrix_revision,
        stored.root_matrix_fingerprint,
        stored.root_schedule_kind,
        stored.root_scheduled_at,
        definition.activity_group,
        stored.root_operation_id,
        stored.root_cycle_id,
        stored.root_journal_ref,
        stored.root_source_families,
        stored.root_instruction,
    )
    _validate_request_operation(root_request, definition)
    if stored.attempt_number < 0 or stored.attempt_operation_id != _attempt_operation_id(
        stored.root_operation_id, stored.attempt_number
    ):
        _fail("SCHEDULE_STATE_INVALID")
    if stored.state is ScheduleState.STARTED and (
        stored.root_schedule_kind != stored.request.kind
        or stored.root_scheduled_at != stored.request.scheduled_at
        or stored.root_operation_id != stored.request.operation_id
        or stored.root_matrix_revision != stored.request.matrix_revision
        or stored.root_matrix_fingerprint != stored.request.matrix_fingerprint
    ):
        _fail("SCHEDULE_STATE_INVALID")


def _operation_id(kind: ScheduleKind, scheduled_at: str, definition: ScheduleDefinition) -> str:
    if definition.due_cycle_kind is None:
        digest = sha256(
            canonicalize(
                checked_json_value(
                    {
                        "schedule_kind": kind.value,
                        "scheduled_at": scheduled_at,
                        "timezone": "Asia/Hong_Kong",
                    }
                )
            )
        ).hexdigest()
        return f"op_{digest}"
    digest = sha256(
        canonicalize(
            checked_json_value(
                {
                    "cycle_kind": definition.due_cycle_kind.value,
                    "schedule_kind": kind.value,
                    "scheduled_at": scheduled_at,
                    "timezone": "Asia/Hong_Kong",
                }
            )
        )
    ).hexdigest()
    return f"cyc_{digest}"


def _command_id(kind: ScheduleKind, scheduled_at: str) -> str:
    digest = sha256(
        canonicalize(
            checked_json_value(
                {
                    "schedule_kind": kind.value,
                    "scheduled_at": scheduled_at,
                    "timezone": "Asia/Hong_Kong",
                }
            )
        )
    ).hexdigest()
    return f"cmd_{digest[:48]}"


def _validate_matrix(matrix: HongKongV1CoverageMatrix) -> None:
    if (
        type(matrix) is not HongKongV1CoverageMatrix
        or not is_hk_v1_coverage_matrix_policy_approved(matrix)
        or tuple(sorted(matrix.included_material_families)) != _SOURCE_FAMILIES
    ):
        _fail("SCHEDULE_MATRIX_INVALID")


def _matrix_fingerprint(value: object) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        _fail("SCHEDULE_STATE_INVALID")
    return value


def _nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        _fail("SCHEDULE_STATE_INVALID")
    return value


def _instruction_from_json(value: object) -> HongKongV1DueCycleInstruction | None:
    if value is None:
        return None
    document = _exact_object(
        value,
        {
            "cycle_id",
            "cycle_kind",
            "scheduled_at",
            "observation_cutoff",
            "matrix_revision",
            "matrix_fingerprint",
        },
    )
    return HongKongV1DueCycleInstruction.from_json(document)


def _exact_object(value: object, fields: set[str]) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if type(checked) is not dict or set(checked) != fields:
        _fail("SCHEDULE_STATE_INVALID")
    return checked


def _text(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail("SCHEDULE_STATE_INVALID")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value)


def _families(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        _fail("SCHEDULE_STATE_INVALID")
    items = cast("list[object]", value)
    if any(type(item) is not str for item in items):
        _fail("SCHEDULE_STATE_INVALID")
    return tuple(cast("list[str]", items))


def _invocation_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        _fail("SCHEDULE_STATE_INVALID")
    items = cast("list[object]", value)
    try:
        result = tuple(validate_systemd_invocation_id(item) for item in items)
    except LiveScheduleError:
        _fail("SCHEDULE_STATE_INVALID")
    if result != tuple(sorted(set(result))):
        _fail("SCHEDULE_STATE_INVALID")
    return result


def _slot(scheduled_at: str, definition: ScheduleDefinition) -> datetime:
    if type(scheduled_at) is not str or _LOCAL_TIMESTAMP.fullmatch(scheduled_at) is None:
        _fail("SCHEDULE_SLOT_INVALID")
    try:
        value = datetime.fromisoformat(scheduled_at)
    except ValueError:
        _fail("SCHEDULE_SLOT_INVALID")
    if (
        value.utcoffset() != _HONG_KONG_OFFSET
        or value.second != 0
        or value.microsecond != 0
        or value.hour != definition.hour
        or value.minute != definition.minute
        or (definition.weekday is not None and value.weekday() != definition.weekday)
    ):
        _fail("SCHEDULE_SLOT_INVALID")
    return value


def _fail(code: str) -> Never:
    raise LiveScheduleError(code)


__all__ = [
    "MAINTENANCE_ACTIVITIES",
    "InMemoryLiveScheduleStore",
    "LiveScheduleError",
    "LiveScheduleStore",
    "LiveSchedulerClient",
    "LocalLiveScheduleStore",
    "ScheduleDefinition",
    "ScheduleEnqueueResult",
    "ScheduleKind",
    "ScheduleRequest",
    "ScheduleState",
    "StoredScheduleCommand",
    "UnavailableMaintenanceActivities",
    "applicable_schedule_slot",
    "dispatch_schedule",
    "enqueue_schedule",
    "mark_schedule_terminal",
    "parse_live_schedule_state_bytes",
    "release_terminal_schedules",
    "run_hk_v1_audit_archive",
    "run_hk_v1_recovery_verification",
    "run_hk_v1_telemetry_retention",
    "schedule_attempt_operation_id",
    "schedule_definitions",
    "schedule_request",
]
