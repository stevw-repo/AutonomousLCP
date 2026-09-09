"""Operator-path proofs for exact Gate F/G evidence production."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_control_plane.v1_schedule import (
    LocalLiveScheduleStore,
    ScheduleKind,
    enqueue_schedule,
    mark_schedule_terminal,
    parse_live_schedule_state_bytes,
)
from asklegal_durable_task import OrchestrationStatus
from asklegal_reporting import load_hk_v1_coverage_matrix

import tools.tests.test_hk_v1_admission_operational_evidence as evidence_fixture
from tools.hk_v1_admission_operational_evidence import (
    build_gate_f_operational_evidence,
    parse_gate_f_operational_evidence,
    parse_gate_g_live_lineage,
    parse_scheduled_cycle_readback,
)
from tools.hk_v1_operational_evidence import (
    build_live_schedule_execution_readback,
    main,
)


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _document(content: bytes) -> dict[str, JsonValue]:
    value: object = json.loads(content)
    assert isinstance(value, dict)
    return cast("dict[str, JsonValue]", value)


def _scheduler_output(kind: ScheduleKind) -> bytes:
    wrapper = evidence_fixture.scheduled_cycle_fixture(
        kind,
        "NO_CHANGE" if kind is ScheduleKind.OBSERVATION else "PROPOSAL_READY",
        None if kind is ScheduleKind.OBSERVATION else "proposals/live-schedule.json",
        evidence_fixture.FP,
    )
    encoded = _document(wrapper)["scheduler_output_hex"]
    assert isinstance(encoded, str)
    return bytes.fromhex(encoded)


@dataclass
class _Client:
    states: dict[str, object]

    def get_orchestration_state(self, instance_id: str) -> object | None:
        return self.states.get(instance_id)


def _live_schedule_fixture(
    root: Path,
    schedule_state: bytes | None = None,
) -> tuple[bytes, _Client]:
    schedule_state = schedule_state or evidence_fixture.schedule_state_fixture()
    commands, active = parse_live_schedule_state_bytes(schedule_state)
    assert active == ()
    states: dict[str, object] = {}
    for command in commands:
        kind = command.request.kind
        if kind in {ScheduleKind.OBSERVATION, ScheduleKind.RECONCILIATION}:
            output = _scheduler_output(kind)
        else:
            if kind is ScheduleKind.AUDIT_ARCHIVE:
                details: dict[str, JsonValue] = {
                    "result": "AUDIT_ARCHIVE_COMPLETE",
                    "input_count": 1,
                    "inventory": [{"read_back_verified": True}],
                }
            elif kind is ScheduleKind.RECOVERY_VERIFY:
                details = {
                    "result": "LIVE_RECOVERY_PROOF_VERIFIED",
                    "proof_fingerprint": evidence_fixture.FP,
                    "recovery_executed": True,
                }
            else:
                details = {
                    "result": "RETENTION_ASSESSMENT_RETAINED",
                    "retention_days": 30,
                    "candidate_paths": [],
                    "inventory": [],
                    "deletion_performed": False,
                }
            retained = evidence_fixture.maintenance_result_fixture(kind, details, schedule_state)
            relative = (
                f"maintenance-results/{kind.value.lower()}/{command.attempt_operation_id}.json"
            )
            _write(root / relative, retained)
            output = canonicalize(
                checked_json_value(
                    {
                        **details,
                        "result_reference": relative,
                        "result_created": True,
                    }
                )
            )
        states[command.attempt_operation_id] = SimpleNamespace(
            instance_id=command.attempt_operation_id,
            name={
                ScheduleKind.OBSERVATION: "run_hk_v1_due_cycle",
                ScheduleKind.RECONCILIATION: "run_hk_v1_due_cycle",
                ScheduleKind.AUDIT_ARCHIVE: "run_hk_v1_audit_archive",
                ScheduleKind.RECOVERY_VERIFY: "run_hk_v1_recovery_verification",
                ScheduleKind.TELEMETRY_RETENTION: "run_hk_v1_telemetry_retention",
            }[kind],
            runtime_status=OrchestrationStatus.COMPLETED,
            serialized_output=output.decode("ascii"),
        )
    return schedule_state, _Client(states)


def _schedule_state_with_audit_retry(tmp_path: Path) -> bytes:
    path = tmp_path / "retry-schedule.json"
    store = LocalLiveScheduleStore(path)
    matrix = load_hk_v1_coverage_matrix()
    slots = (
        (ScheduleKind.OBSERVATION, "2026-09-07T02:15:00+08:00"),
        (ScheduleKind.RECONCILIATION, "2026-09-13T03:15:00+08:00"),
        (ScheduleKind.AUDIT_ARCHIVE, "2026-09-07T04:30:00+08:00"),
        (ScheduleKind.RECOVERY_VERIFY, "2026-09-07T05:15:00+08:00"),
        (ScheduleKind.TELEMETRY_RETENTION, "2026-09-07T06:00:00+08:00"),
    )
    for kind, slot in slots:
        result = enqueue_schedule(store, kind, slot, matrix=matrix)
        if kind is ScheduleKind.AUDIT_ARCHIVE:
            store.advance_retry(result.operation_id, result.operation_id)
        mark_schedule_terminal(store, result.operation_id)
    return path.read_bytes()


def test_schedule_live_reads_all_five_owner_outputs_and_cli_replays(tmp_path: Path) -> None:
    """One read-only scheduler pass resolves both cycle and retained maintenance results."""
    state_root = tmp_path / "control"
    state_root.mkdir()
    schedule_state, client = _live_schedule_fixture(state_root)
    host_facts = evidence_fixture.operational_host_facts()
    content = build_live_schedule_execution_readback(
        schedule_state,
        host_facts,
        state_root,
        client,
    )
    assert b'"schedule_kind":"OBSERVATION"' in content
    assert b'"schedule_kind":"RECOVERY_VERIFY"' in content

    state_path = _write(tmp_path / "schedule.json", schedule_state)
    output = tmp_path / "out" / "schedule-execution.json"
    arguments = [
        "schedule-live",
        "--schedule-state",
        str(state_path),
        "--host-facts",
        str(_write(tmp_path / "host.json", host_facts)),
        "--control-state-root",
        str(state_root),
        "--output",
        str(output),
    ]
    assert main(arguments, scheduler_client=client) == 0
    assert main(arguments, scheduler_client=client) == 0
    assert output.read_bytes() == content
    assert output.stat().st_mode & 0o777 == 0o600


def test_schedule_live_accepts_exact_retained_maintenance_retry(tmp_path: Path) -> None:
    """Gate F preserves a deterministic maintenance retry instead of stranding it."""
    state_root = tmp_path / "control"
    state_root.mkdir()
    schedule_state = _schedule_state_with_audit_retry(tmp_path)
    commands, active = parse_live_schedule_state_bytes(schedule_state)
    audit = next(item for item in commands if item.request.kind is ScheduleKind.AUDIT_ARCHIVE)
    assert active == ()
    assert audit.attempt_number == 1
    assert audit.attempt_operation_id.startswith("att_")
    schedule_state, client = _live_schedule_fixture(state_root, schedule_state)

    content = build_live_schedule_execution_readback(
        schedule_state,
        evidence_fixture.operational_host_facts(),
        state_root,
        client,
    )

    sources = replace(evidence_fixture.gate_f_sources_fixture(), schedule_state=content)
    assert (
        parse_gate_f_operational_evidence(build_gate_f_operational_evidence(sources)).result
        == "COMPLETE"
    )


def test_gate_f_cli_derives_serving_state_and_supervision_from_owner_files(
    tmp_path: Path,
) -> None:
    """The CLI cannot accept caller-declared serving or supervision fingerprints."""
    sources = evidence_fixture.gate_f_sources_fixture()
    supervision = _document(sources.supervision)
    manifest = bytes.fromhex(cast("str", supervision["credential_manifest_hex"]))
    host_apply = bytes.fromhex(cast("str", supervision["host_apply_state_hex"]))
    rotation_rows = cast("list[dict[str, JsonValue]]", supervision["credential_rotation_reports"])
    rotations = [bytes.fromhex(cast("str", row["content_hex"])) for row in rotation_rows]
    paths = {
        "schedule": _write(tmp_path / "schedule.json", sources.schedule_state),
        "host": _write(tmp_path / "host.json", sources.host_facts),
        "status": _write(tmp_path / "status.json", sources.operational_status),
        "apply": _write(tmp_path / "apply.json", host_apply),
        "manifest": _write(tmp_path / "credentials.json", manifest),
        "recovery": _write(tmp_path / "recovery.json", sources.recovery),
        "restart": _write(tmp_path / "restart.json", sources.restart),
        "serving": _write(tmp_path / "serving.json", sources.serving_state),
    }
    rotation_paths = [
        _write(tmp_path / "rotation" / f"{index:02d}.json", raw)
        for index, raw in enumerate(reversed(rotations))
    ]
    output = tmp_path / "gate-f.json"
    arguments = [
        "gate-f",
        "--schedule-execution",
        str(paths["schedule"]),
        "--host-facts",
        str(paths["host"]),
        "--operational-status",
        str(paths["status"]),
        "--host-apply-state",
        str(paths["apply"]),
        "--credential-manifest",
        str(paths["manifest"]),
        "--recovery",
        str(paths["recovery"]),
        "--restart",
        str(paths["restart"]),
        "--serving-state",
        str(paths["serving"]),
        "--output",
        str(output),
    ]
    for path in rotation_paths:
        arguments.extend(("--credential-rotation-report", str(path)))
    assert main(arguments) == 0
    parsed = parse_gate_f_operational_evidence(output.read_bytes())
    assert parsed.serving_state_id == evidence_fixture.STATE_2


def test_scheduled_cycle_and_gate_g_clis_publish_replayable_exact_outputs(
    tmp_path: Path,
) -> None:
    """The two remaining operator products round-trip through their strict parsers."""
    wrapper = evidence_fixture.scheduled_cycle_fixture(
        ScheduleKind.RECONCILIATION,
        "PROPOSAL_READY",
        "proposals/cli.json",
        evidence_fixture.FP,
    )
    wrapped = _document(wrapper)
    schedule_state = bytes.fromhex(cast("str", wrapped["schedule_state_hex"]))
    host_facts = bytes.fromhex(cast("str", wrapped["host_facts_hex"]))
    scheduler_output = bytes.fromhex(cast("str", wrapped["scheduler_output_hex"]))
    scheduled_output = tmp_path / "scheduled-cycle.json"
    assert (
        main(
            [
                "scheduled-cycle",
                "--schedule-state",
                str(_write(tmp_path / "state.json", schedule_state)),
                "--host-facts",
                str(_write(tmp_path / "host.json", host_facts)),
                "--root-operation-id",
                cast("str", wrapped["root_operation_id"]),
                "--scheduler-output",
                str(_write(tmp_path / "scheduler.json", scheduler_output)),
                "--output",
                str(scheduled_output),
            ]
        )
        == 0
    )
    parse_scheduled_cycle_readback(scheduled_output.read_bytes())

    sources = evidence_fixture.gate_g_sources_fixture()
    arguments = ["gate-g"]
    for name in (
        "baseline_cycle",
        "baseline_promotion",
        "changed_cycle",
        "changed_promotion",
        "no_change_cycle",
        "pre_reboot",
        "post_reboot",
        "rollback",
        "restoration",
        "post_reboot_no_change_cycle",
        "post_reboot_changed_cycle",
        "next_health",
    ):
        path = _write(tmp_path / "g" / f"{name}.json", cast("bytes", getattr(sources, name)))
        arguments.extend(("--" + name.replace("_", "-"), str(path)))
    lineage = tmp_path / "gate-g.json"
    arguments.extend(("--output", str(lineage)))
    assert main(arguments) == 0
    assert parse_gate_g_live_lineage(lineage.read_bytes()).result == "COMPLETE"
