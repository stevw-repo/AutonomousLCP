"""Control-plane-facing tests for Task 9 live schedule identities."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from asklegal_control_plane import main as control_main
from asklegal_control_plane import v1_schedule
from asklegal_durable_task import ActivityContext, OrchestrationStatus
from asklegal_reporting import HongKongV1CoverageMatrix, load_hk_v1_coverage_matrix

from tools.hk_v1_live_cycle import (
    InMemoryLiveScheduleStore,
    LiveScheduleError,
    LocalLiveScheduleStore,
    ScheduleKind,
    UnavailableMaintenanceActivities,
    dispatch_schedule,
    enqueue_schedule,
    release_terminal_schedules,
)


class _SchedulerClient:
    def __init__(self) -> None:
        self.states: dict[str, object] = {}
        self.schedules: list[tuple[str, object, str, str]] = []

    def get_orchestration_state(self, instance_id: str) -> object | None:
        return self.states.get(instance_id)

    def schedule_new_orchestration(
        self,
        orchestrator: str,
        *,
        input: object,  # noqa: A002 - exact client keyword.
        instance_id: str,
        version: str,
    ) -> str:
        self.schedules.append((orchestrator, input, instance_id, version))
        self.states[instance_id] = SimpleNamespace(runtime_status=OrchestrationStatus.RUNNING)
        return instance_id


class _SchedulerSettings:
    def __init__(self, client: _SchedulerClient) -> None:
        self.client = client

    def create_client(self, *, default_version: str) -> _SchedulerClient:
        assert default_version == "1.0.0"
        return self.client


def _object(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast("dict[str, object]", value)


def _objects(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


_INVOCATION_A = "0123456789abcdef0123456789abcdef"
_INVOCATION_B = "fedcba9876543210fedcba9876543210"


def _completed_due_state(result: str) -> SimpleNamespace:
    proposal: dict[str, object] | None = None
    blockers: list[str] = []
    if result == "NOT_READY":
        blockers = ["LEGAL_PROCESSING_ACCEPTANCE_NOT_READY"]
    elif result == "PROPOSAL_READY":
        proposal = {
            "vault": "PRIMARY",
            "logical_key": "hk-v1/proposals/prp_" + "1" * 48 + ".json",
            "version_id": "version-1",
            "fingerprint": "sha256:" + "2" * 64,
            "byte_length": 1,
        }
    return SimpleNamespace(
        runtime_status=OrchestrationStatus.COMPLETED,
        serialized_output=json.dumps(
            {
                "acceptance": {
                    "schema_id": "asklegal.hk-v1.acceptance-cycle-result",
                    "schema_version": "1.0.0",
                    "kind": "UPDATE",
                    "operation_id": "cyc_" + "3" * 64,
                    "command_fingerprint": "sha256:" + "4" * 64,
                    "observation_cutoff": "2026-09-07T18:15:00Z",
                    "families": ["CASES", "LEGISLATION"],
                    "scope_ids": [
                        "HK-CASE-BINDING-POST-1997",
                        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                        "HK-LEG-ORDINANCES",
                        "HK-LEG-SUBSIDIARY",
                    ],
                    "result": result,
                    "blocker_codes": blockers,
                    "proposal_reference": proposal,
                }
            }
        ),
    )


def test_control_timer_duplicate_is_one_exact_durable_command() -> None:
    """Control receives one stable command identity for a duplicated systemd slot."""
    store = InMemoryLiveScheduleStore()
    matrix = load_hk_v1_coverage_matrix()

    first = enqueue_schedule(
        store,
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=matrix,
    )
    replay = enqueue_schedule(
        store,
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=matrix,
    )

    assert replay.command_id == first.command_id
    assert replay.resolution == "EXACT_REPLAY"
    assert replay.cycle_id == first.cycle_id
    assert replay.journal_ref == first.journal_ref


def test_new_delivery_invocation_is_evidence_not_command_identity() -> None:
    """A systemd retry binds both deliveries while replaying one slot-derived command."""
    store = InMemoryLiveScheduleStore()
    matrix = load_hk_v1_coverage_matrix()

    first = enqueue_schedule(
        store,
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=matrix,
        invocation_id=_INVOCATION_A,
    )
    retry = enqueue_schedule(
        store,
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=matrix,
        invocation_id=_INVOCATION_B,
    )

    assert retry.resolution == "EXACT_REPLAY"
    assert retry.command_id == first.command_id
    assert retry.command_fingerprint == first.command_fingerprint
    assert retry.operation_id == first.operation_id
    assert retry.delivery_invocation_ids == (_INVOCATION_A, _INVOCATION_B)


def test_reopened_store_retains_duplicate_invocations_without_identity_drift(
    tmp_path: Path,
) -> None:
    """Process restart retains delivery evidence without changing the durable command."""
    state_path = tmp_path / "control" / "hk-v1-live-schedules.json"
    matrix = load_hk_v1_coverage_matrix()
    first = enqueue_schedule(
        LocalLiveScheduleStore(state_path),
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=matrix,
        invocation_id=_INVOCATION_A,
    )
    retry = enqueue_schedule(
        LocalLiveScheduleStore(state_path),
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=matrix,
        invocation_id=_INVOCATION_B,
    )

    assert retry.resolution == "EXACT_REPLAY"
    assert retry.command_id == first.command_id
    assert retry.operation_id == first.operation_id
    assert retry.delivery_invocation_ids == (_INVOCATION_A, _INVOCATION_B)
    retained = _object(json.loads(state_path.read_bytes()))
    commands = _objects(retained["commands"])
    assert _object(commands[0])["delivery_invocation_ids"] == [
        _INVOCATION_A,
        _INVOCATION_B,
    ]


def test_control_source_schedule_contains_only_current_two_family_instruction() -> None:
    """The scheduled acquisition instruction is exact and excludes every third family."""
    result = enqueue_schedule(
        InMemoryLiveScheduleStore(),
        ScheduleKind.RECONCILIATION,
        "2026-09-13T03:15:00+08:00",
        matrix=load_hk_v1_coverage_matrix(),
    )

    assert result.instruction is not None
    assert result.source_families == ("CASES", "LEGISLATION")
    assert result.instruction.cycle_id == result.cycle_id
    assert result.instruction.scheduled_at == "2026-09-12T19:15:00Z"
    assert result.instruction.observation_cutoff == "2026-09-12T19:15:00Z"


def test_control_dispatches_stable_source_instance_and_restart_does_not_compete() -> None:
    """The durable scheduler receives the exact retained cycle identity at most once."""
    result = enqueue_schedule(
        InMemoryLiveScheduleStore(),
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=load_hk_v1_coverage_matrix(),
    )
    client = _SchedulerClient()
    instruction = result.instruction
    assert instruction is not None

    first = dispatch_schedule(client, result)
    replay = dispatch_schedule(client, result)

    assert first == "SCHEDULED"
    assert replay == "INSTANCE_PRESENT"
    assert client.schedules == [
        (
            "run_hk_v1_due_cycle",
            {
                "cycle_id": result.cycle_id,
                "cycle_kind": "DAILY_CURRENT_LAW",
                "scheduled_at": "2026-09-07T18:15:00Z",
                "observation_cutoff": "2026-09-07T18:15:00Z",
                "matrix_revision": instruction.matrix_revision,
                "matrix_fingerprint": instruction.matrix_fingerprint,
            },
            result.operation_id,
            "1.0.0",
        )
    ]


def test_control_dispatches_each_maintenance_command_without_claiming_completion() -> None:
    """Every non-source timer gets a named stable queue destination, not fake success."""
    matrix = load_hk_v1_coverage_matrix()
    client = _SchedulerClient()
    slots = {
        ScheduleKind.AUDIT_ARCHIVE: "2026-09-08T04:30:00+08:00",
        ScheduleKind.RECOVERY_VERIFY: "2026-09-14T05:15:00+08:00",
        ScheduleKind.TELEMETRY_RETENTION: "2026-09-08T06:00:00+08:00",
    }
    for kind, slot in slots.items():
        result = enqueue_schedule(InMemoryLiveScheduleStore(), kind, slot, matrix=matrix)
        assert dispatch_schedule(client, result) == "SCHEDULED"

    assert [call[0] for call in client.schedules] == [
        "run_hk_v1_audit_archive",
        "run_hk_v1_recovery_verification",
        "run_hk_v1_telemetry_retention",
    ]
    assert all(_object(call[1])["state"] == "REQUESTED" for call in client.schedules)
    for _orchestrator, payload, _instance_id, _version in client.schedules:
        request = _object(payload)
        assert request["matrix_revision"] == matrix.revision
        assert request["matrix_fingerprint"] == matrix.fingerprint
        assert request["command_fingerprint"]


@pytest.mark.parametrize(
    ("kind", "slot"),
    [
        (ScheduleKind.OBSERVATION, "2026-09-08T02:15:00+08:00"),
        (ScheduleKind.RECONCILIATION, "2026-09-13T03:15:00+08:00"),
        (ScheduleKind.AUDIT_ARCHIVE, "2026-09-08T04:30:00+08:00"),
        (ScheduleKind.RECOVERY_VERIFY, "2026-09-14T05:15:00+08:00"),
        (ScheduleKind.TELEMETRY_RETENTION, "2026-09-08T06:00:00+08:00"),
    ],
)
def test_every_schedule_command_fingerprint_binds_exact_matrix_lineage(
    kind: ScheduleKind,
    slot: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matrix drift changes command lineage while the calendar command ID stays stable."""
    matrix = load_hk_v1_coverage_matrix()
    drifted = replace(
        matrix,
        revision="HK-V1-004",
        fingerprint="sha256:" + "4" * 64,
    )

    def approve_matrix(_matrix: HongKongV1CoverageMatrix) -> bool:
        return True

    monkeypatch.setattr(v1_schedule, "is_hk_v1_coverage_matrix_policy_approved", approve_matrix)

    first = v1_schedule.schedule_request(kind, slot, matrix=matrix)
    changed = v1_schedule.schedule_request(kind, slot, matrix=drifted)

    assert changed.command_id == first.command_id
    assert changed.operation_id == first.operation_id
    assert changed.command_fingerprint != first.command_fingerprint
    assert changed.matrix_revision == drifted.revision
    assert changed.matrix_fingerprint == drifted.fingerprint


def test_retained_maintenance_replay_rejects_matrix_drift(tmp_path: Path) -> None:
    """A slot already retained under one Matrix cannot replay under another lineage."""
    store = LocalLiveScheduleStore(tmp_path / "control" / "hk-v1-live-schedules.json")
    matrix = load_hk_v1_coverage_matrix()
    enqueue_schedule(
        store,
        ScheduleKind.AUDIT_ARCHIVE,
        "2026-09-08T04:30:00+08:00",
        matrix=matrix,
    )
    drifted = replace(
        matrix,
        revision="HK-V1-004",
        fingerprint="sha256:" + "4" * 64,
    )

    with pytest.raises(LiveScheduleError, match="SCHEDULE_MATRIX_INVALID"):
        enqueue_schedule(
            LocalLiveScheduleStore(tmp_path / "control" / "hk-v1-live-schedules.json"),
            ScheduleKind.AUDIT_ARCHIVE,
            "2026-09-08T04:30:00+08:00",
            matrix=drifted,
        )


@pytest.mark.parametrize(
    ("kind", "slot", "method_name", "code"),
    [
        (
            ScheduleKind.AUDIT_ARCHIVE,
            "2026-09-08T04:30:00+08:00",
            "perform_hk_v1_audit_archive",
            "HK_V1_AUDIT_ARCHIVE_ADAPTER_UNAVAILABLE",
        ),
        (
            ScheduleKind.RECOVERY_VERIFY,
            "2026-09-14T05:15:00+08:00",
            "perform_hk_v1_recovery_verification",
            "HK_V1_RECOVERY_VERIFICATION_ADAPTER_UNAVAILABLE",
        ),
        (
            ScheduleKind.TELEMETRY_RETENTION,
            "2026-09-08T06:00:00+08:00",
            "perform_hk_v1_telemetry_retention",
            "HK_V1_TELEMETRY_RETENTION_ADAPTER_UNAVAILABLE",
        ),
    ],
)
def test_unavailable_maintenance_adapter_fails_visible_without_fake_completion(
    kind: ScheduleKind,
    slot: str,
    method_name: str,
    code: str,
) -> None:
    """A registered boundary fails closed until the capability owner is composed."""
    result = enqueue_schedule(
        InMemoryLiveScheduleStore(), kind, slot, matrix=load_hk_v1_coverage_matrix()
    )
    client = _SchedulerClient()
    assert dispatch_schedule(client, result) == "SCHEDULED"
    method = getattr(UnavailableMaintenanceActivities(), method_name)

    with pytest.raises(LiveScheduleError, match=code):
        method(ActivityContext("maintenance", 1), client.schedules[-1][1])


def test_control_cli_retains_then_dispatches_exact_explicit_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The timer CLI uses retained file state and the control Durable Task hub."""
    client = _SchedulerClient()
    monkeypatch.setenv("ASKLEGAL_CONTROL_STATE_ROOT", str(tmp_path / "control"))

    def scheduler_for(application: str) -> _SchedulerSettings:
        if application != "CONTROL_PLANE":
            pytest.fail("wrong scheduler")
        return _SchedulerSettings(client)

    monkeypatch.setattr(
        control_main.V1SchedulerSettings,
        "for_application",
        scheduler_for,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "asklegal-control-plane",
            "--enqueue-schedule",
            "OBSERVATION",
            "--scheduled-at",
            "2026-09-08T02:15:00+08:00",
            "--invocation-id",
            _INVOCATION_A,
        ],
    )

    control_main.main()

    output = _object(json.loads(capsys.readouterr().out))
    assert output["dispatch"] == "SCHEDULED"
    assert output["resolution"] == "RESULT_RECORDED"
    assert output["state"] == "STARTED"
    assert output["activity_complete"] is False
    assert output["delivery_invocation_id"] == _INVOCATION_A
    assert output["delivery_invocation_ids"] == [_INVOCATION_A]
    assert (tmp_path / "control" / "hk-v1-live-schedules.json").is_file()


def test_control_cli_immediately_dispatches_promoted_waiting_source_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Terminal reconciliation wakes a retained source slot without another timer."""
    state_path = tmp_path / "control" / "hk-v1-live-schedules.json"
    store = LocalLiveScheduleStore(state_path)
    matrix = load_hk_v1_coverage_matrix()
    active = enqueue_schedule(
        store,
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=matrix,
        invocation_id=_INVOCATION_A,
    )
    waiting = enqueue_schedule(
        store,
        ScheduleKind.RECONCILIATION,
        "2026-09-13T03:15:00+08:00",
        matrix=matrix,
        invocation_id=_INVOCATION_B,
    )
    assert waiting.state.value == "COALESCED_IN_PROGRESS"

    client = _SchedulerClient()
    client.states[active.operation_id] = _completed_due_state("NO_CHANGE")
    monkeypatch.setenv("ASKLEGAL_CONTROL_STATE_ROOT", str(tmp_path / "control"))

    def scheduler_for(application: str) -> _SchedulerSettings:
        assert application == "CONTROL_PLANE"
        return _SchedulerSettings(client)

    monkeypatch.setattr(
        control_main.V1SchedulerSettings,
        "for_application",
        scheduler_for,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "asklegal-control-plane",
            "--enqueue-schedule",
            "AUDIT_ARCHIVE",
            "--scheduled-at",
            "2026-09-14T04:30:00+08:00",
            "--invocation-id",
            "11111111111111111111111111111111",
        ],
    )

    control_main.main()

    output = _object(json.loads(capsys.readouterr().out))
    assert output["schedule_kind"] == "AUDIT_ARCHIVE"
    assert [call[0] for call in client.schedules] == [
        "run_hk_v1_due_cycle",
        "run_hk_v1_audit_archive",
    ]
    promoted = enqueue_schedule(
        LocalLiveScheduleStore(state_path),
        ScheduleKind.RECONCILIATION,
        "2026-09-13T03:15:00+08:00",
        matrix=matrix,
    )
    assert promoted.state.value == "STARTED"
    assert client.schedules[0][2] == promoted.operation_id


def test_completed_not_ready_retries_same_retained_cycle_after_restart(
    tmp_path: Path,
) -> None:
    """A completed transport cannot strand a semantically incomplete due cycle."""
    state_path = tmp_path / "control" / "hk-v1-live-schedules.json"
    store = LocalLiveScheduleStore(state_path)
    root = enqueue_schedule(
        store,
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=load_hk_v1_coverage_matrix(),
    )
    client = _SchedulerClient()
    client.states[root.operation_id] = _completed_due_state("NOT_READY")

    retry = release_terminal_schedules(store, client)

    assert len(retry) == 1
    assert retry[0].resolution == "RESULT_RETRY"
    assert retry[0].operation_id != root.operation_id
    assert retry[0].cycle_id == root.cycle_id
    assert retry[0].journal_ref == root.journal_ref
    assert retry[0].instruction == root.instruction
    assert LocalLiveScheduleStore(state_path).active_operation_ids() == (retry[0].operation_id,)
    retained = _object(json.loads(state_path.read_bytes()))
    assert retained["schema_version"] == "1.3.0"
    retained_root = _object(_objects(retained["commands"])[0])
    assert retained_root["attempt_number"] == 1
    assert retained_root["attempt_operation_id"] == retry[0].operation_id

    # Simulate a process crash after the retry transition was retained but before dispatch.
    resumed = release_terminal_schedules(LocalLiveScheduleStore(state_path), client)
    assert len(resumed) == 1
    assert resumed[0].resolution == "RESULT_RESUMED"
    assert resumed[0].operation_id == retry[0].operation_id
    assert dispatch_schedule(client, resumed[0]) == "SCHEDULED"
    assert client.schedules[-1][0] == "run_hk_v1_due_cycle"
    assert _object(client.schedules[-1][1])["cycle_id"] == root.cycle_id


@pytest.mark.parametrize(
    "runtime_status",
    [OrchestrationStatus.FAILED, OrchestrationStatus.TERMINATED],
)
def test_failed_or_terminated_attempt_retries_same_retained_lineage(
    runtime_status: OrchestrationStatus,
) -> None:
    """Transport failure advances a stable attempt without changing root lineage."""
    store = InMemoryLiveScheduleStore()
    root = enqueue_schedule(
        store,
        ScheduleKind.RECONCILIATION,
        "2026-09-13T03:15:00+08:00",
        matrix=load_hk_v1_coverage_matrix(),
    )
    client = _SchedulerClient()
    client.states[root.operation_id] = SimpleNamespace(runtime_status=runtime_status)

    retry = release_terminal_schedules(store, client)

    assert len(retry) == 1
    assert retry[0].resolution == "RESULT_RETRY"
    assert retry[0].operation_id != root.operation_id
    assert retry[0].cycle_id == root.cycle_id
    assert retry[0].journal_ref == root.journal_ref


@pytest.mark.parametrize("result", ["NO_CHANGE", "PROPOSAL_READY"])
def test_completed_semantic_success_releases_due_cycle(result: str) -> None:
    """Only final acceptance outcomes release the active source group."""
    store = InMemoryLiveScheduleStore()
    root = enqueue_schedule(
        store,
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=load_hk_v1_coverage_matrix(),
    )
    client = _SchedulerClient()
    client.states[root.operation_id] = _completed_due_state(result)

    assert release_terminal_schedules(store, client) == ()
    assert store.active_count == 0


def test_control_cli_redispatches_retained_root_missing_from_scheduler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A crash after retention but before dispatch cannot strand the source queue."""
    state_path = tmp_path / "control" / "hk-v1-live-schedules.json"
    matrix = load_hk_v1_coverage_matrix()
    retained = enqueue_schedule(
        LocalLiveScheduleStore(state_path),
        ScheduleKind.OBSERVATION,
        "2026-09-08T02:15:00+08:00",
        matrix=matrix,
        invocation_id=_INVOCATION_A,
    )
    client = _SchedulerClient()
    monkeypatch.setenv("ASKLEGAL_CONTROL_STATE_ROOT", str(tmp_path / "control"))

    def scheduler_for(application: str) -> _SchedulerSettings:
        assert application == "CONTROL_PLANE"
        return _SchedulerSettings(client)

    monkeypatch.setattr(control_main.V1SchedulerSettings, "for_application", scheduler_for)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "asklegal-control-plane",
            "--enqueue-schedule",
            "RECONCILIATION",
            "--scheduled-at",
            "2026-09-13T03:15:00+08:00",
            "--invocation-id",
            _INVOCATION_B,
        ],
    )

    control_main.main()

    output = _object(json.loads(capsys.readouterr().out))
    assert output["state"] == "COALESCED_IN_PROGRESS"
    assert output["operation_id"] == retained.operation_id
    assert client.schedules == [
        (
            "run_hk_v1_due_cycle",
            client.schedules[0][1],
            retained.operation_id,
            "1.0.0",
        )
    ]
    retained = _object(
        json.loads((tmp_path / "control" / "hk-v1-live-schedules.json").read_bytes())
    )
    commands = _objects(retained["commands"])
    assert _object(commands[0])["delivery_invocation_ids"] == [_INVOCATION_A]
    assert client.schedules[0][0] == "run_hk_v1_due_cycle"


def test_control_cli_delayed_catch_up_uses_latest_applicable_hong_kong_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A delayed persistent delivery resolves the latest due slot, not wall-clock identity."""
    client = _SchedulerClient()
    monkeypatch.setenv("ASKLEGAL_CONTROL_STATE_ROOT", str(tmp_path / "control"))

    def scheduler_for(_application: str) -> _SchedulerSettings:
        return _SchedulerSettings(client)

    monkeypatch.setattr(
        control_main.V1SchedulerSettings,
        "for_application",
        scheduler_for,
    )
    monkeypatch.setattr(
        control_main,
        "_schedule_now",
        lambda: datetime(2026, 9, 8, 21, 4, tzinfo=UTC),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "asklegal-control-plane",
            "--enqueue-schedule",
            "AUDIT_ARCHIVE",
            "--invocation-id",
            _INVOCATION_B,
        ],
    )

    control_main.main()

    output = _object(json.loads(capsys.readouterr().out))
    assert output["scheduled_at"] == "2026-09-09T04:30:00+08:00"
    assert output["delivery_invocation_id"] == _INVOCATION_B
    assert _object(client.schedules[0][1])["scheduled_at"] == "2026-09-09T04:30:00+08:00"


@pytest.mark.parametrize(
    "invocation_id",
    [
        "",
        "0" * 32,
        "0123456789abcdef0123456789abcde",
        "0123456789ABCDEF0123456789ABCDEF",
        "01234567-89ab-cdef-0123-456789abcdef",
        "g123456789abcdef0123456789abcdef",
    ],
)
def test_control_cli_rejects_non_systemd_invocation_ids(
    invocation_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only a non-null lowercase systemd ID128 reaches retained schedule state."""
    monkeypatch.setenv("ASKLEGAL_CONTROL_STATE_ROOT", str(tmp_path / "control"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "asklegal-control-plane",
            "--enqueue-schedule",
            "OBSERVATION",
            "--invocation-id",
            invocation_id,
        ],
    )

    with pytest.raises(SystemExit) as error:
        control_main.main()

    assert error.value.code == 2
    assert "SCHEDULE_COMMAND_FAILED" in capsys.readouterr().err
    assert not (tmp_path / "control" / "hk-v1-live-schedules.json").exists()


def test_control_cli_requires_invocation_evidence_for_enqueue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A schedule command cannot silently lose its systemd delivery evidence."""
    monkeypatch.setenv("ASKLEGAL_CONTROL_STATE_ROOT", str(tmp_path / "control"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["asklegal-control-plane", "--enqueue-schedule", "OBSERVATION"],
    )

    with pytest.raises(SystemExit) as error:
        control_main.main()

    assert error.value.code == 2
    assert "--enqueue-schedule requires --invocation-id" in capsys.readouterr().err
    assert not (tmp_path / "control" / "hk-v1-live-schedules.json").exists()
