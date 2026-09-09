"""Focused local-only maintenance activity proofs."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_control_plane import v1_maintenance, v1_schedule
from asklegal_control_plane.v1_maintenance import (
    LocalMaintenanceActivities,
    MaintenanceConfiguration,
)
from asklegal_control_plane.v1_schedule import (
    LiveScheduleError,
    ScheduleKind,
    schedule_attempt_operation_id,
    schedule_request,
)
from asklegal_durable_task import ActivityContext
from asklegal_reporting import HongKongV1CoverageMatrix, load_hk_v1_coverage_matrix


def _payload(kind: ScheduleKind, scheduled_at: str) -> dict[str, object]:
    request = schedule_request(kind, scheduled_at, matrix=load_hk_v1_coverage_matrix())
    return {
        "command_id": request.command_id,
        "command_fingerprint": request.command_fingerprint,
        "matrix_fingerprint": request.matrix_fingerprint,
        "matrix_revision": request.matrix_revision,
        "attempt_number": 0,
        "operation_id": request.operation_id,
        "schedule_kind": kind.value,
        "scheduled_at": scheduled_at,
        "state": "REQUESTED",
    }


def _configuration(tmp_path: Path) -> MaintenanceConfiguration:
    state_root = tmp_path / "state"
    return MaintenanceConfiguration(
        state_root=state_root,
        schedule_state_path=tmp_path / "inputs" / "hk-v1-live-schedules.json",
        operational_input_root=tmp_path / "inputs" / "operational",
        recovery_proof_path=tmp_path / "inputs" / "recovery" / "latest-proof.json",
        recovery_proof_fingerprint_path=(tmp_path / "inputs" / "recovery" / "latest-proof.sha256"),
        telemetry_root=tmp_path / "inputs" / "telemetry",
    )


def _activities(tmp_path: Path) -> LocalMaintenanceActivities:
    return LocalMaintenanceActivities(
        _configuration(tmp_path),
        load_hk_v1_coverage_matrix(),
    )


def _write_recovery_proof(tmp_path: Path) -> bytes:
    proof = canonicalize(
        {
            "blockers": [],
            "contract_proved": True,
            "gate_f_eligible": False,
            "result_code": "LOCAL_RECOVERY_CONTRACT_PROVED",
            "scheduler_result": "PROVED",
            "sql_result": "PROVED",
            "vault_result": "PROVED",
        }
    )
    root = tmp_path / "inputs" / "recovery"
    root.mkdir(parents=True)
    (root / "latest-proof.json").write_bytes(proof)
    (root / "latest-proof.sha256").write_text(f"sha256:{sha256(proof).hexdigest()}\n")
    return proof


def _write_live_recovery_proof(tmp_path: Path) -> bytes:
    plan_fingerprint = "sha256:" + "a" * 64
    steps = (
        "SQL_RESTORE_READBACK",
        "PRIMARY_VAULT_CLEAN_ROOM_READBACK",
        "RECOVERY_VAULT_CLEAN_ROOM_READBACK",
        "SCHEDULER_GENERAL_FORWARD",
        "SCHEDULER_GENERAL_REVERSE",
        "SCHEDULER_PROMOTION_FORWARD",
        "SCHEDULER_PROMOTION_REVERSE",
    )
    receipts: list[JsonValue] = []
    for index, step in enumerate(steps):
        fingerprint = "sha256:" + f"{index + 1:x}" * 64
        receipts.append(
            {
                "effect_fingerprint": fingerprint,
                "plan_fingerprint": plan_fingerprint,
                "readback_fingerprint": fingerprint,
                "step": step,
                "target_identity": f"r_{index:032x}",
            }
        )
    body: dict[str, JsonValue] = {
        "live_recovery_proved": True,
        "operation_id": "r_" + "b" * 32,
        "plan_fingerprint": plan_fingerprint,
        "receipts": receipts,
        "schema": "asklegal.hk-v1-live-recovery-execution-result/v1",
    }
    body["fingerprint"] = "sha256:" + sha256(canonicalize(body)).hexdigest()
    proof = canonicalize(checked_json_value(body))
    root = tmp_path / "inputs" / "recovery"
    root.mkdir(parents=True)
    (root / "latest-proof.json").write_bytes(proof)
    (root / "latest-proof.sha256").write_text(f"sha256:{sha256(proof).hexdigest()}\n")
    return proof


def test_audit_archive_is_exact_read_back_verified_and_restart_safe(tmp_path: Path) -> None:
    """The archive copies the bounded local inventory and never invents source success."""
    schedule_path = tmp_path / "inputs" / "hk-v1-live-schedules.json"
    schedule_path.parent.mkdir(parents=True)
    schedule_path.write_bytes(b'{"retained":"schedule"}\n')
    operational = tmp_path / "inputs" / "operational"
    operational.mkdir()
    (operational / "audit.ndjson").write_bytes(b'{"event":"one"}\n')
    activities = _activities(tmp_path)
    payload = _payload(ScheduleKind.AUDIT_ARCHIVE, "2026-09-08T04:30:00+08:00")

    first = activities.perform_hk_v1_audit_archive(ActivityContext("audit", 1), payload)
    replay = activities.perform_hk_v1_audit_archive(ActivityContext("audit", 2), payload)

    assert first["result"] == "AUDIT_ARCHIVE_COMPLETE"
    assert first["result_created"] is True
    assert replay["result_created"] is False
    assert first["result_reference"] == replay["result_reference"]
    assert first["input_count"] == 2
    inventory = cast("list[dict[str, object]]", first["inventory"])
    for item in inventory:
        archived = tmp_path / "state" / cast("str", item["archive_object_ref"])
        assert archived.read_bytes()


def test_maintenance_retry_uses_exact_attempt_identity_and_replays(tmp_path: Path) -> None:
    """A failed maintenance run can resume under its deterministic retry identity."""
    schedule_path = tmp_path / "inputs" / "hk-v1-live-schedules.json"
    schedule_path.parent.mkdir(parents=True)
    schedule_path.write_bytes(b'{"retained":"schedule"}\n')
    operational = tmp_path / "inputs" / "operational"
    operational.mkdir()
    (operational / "audit.ndjson").write_bytes(b'{"event":"one"}\n')
    activities = _activities(tmp_path)
    slot = "2026-09-08T04:30:00+08:00"
    payload: dict[str, object] = _payload(ScheduleKind.AUDIT_ARCHIVE, slot)
    payload["attempt_number"] = 1
    payload["operation_id"] = schedule_attempt_operation_id(
        ScheduleKind.AUDIT_ARCHIVE,
        slot,
        1,
    )

    first = activities.perform_hk_v1_audit_archive(ActivityContext("audit-retry", 1), payload)
    replay = activities.perform_hk_v1_audit_archive(ActivityContext("audit-retry", 2), payload)

    assert str(first["result_reference"]).endswith(f"/{payload['operation_id']}.json")
    assert first["result_created"] is True
    assert replay["result_created"] is False


def test_recovery_verification_consumes_exact_retained_proof(tmp_path: Path) -> None:
    """The timer verifies an existing proof and retains that fact without running recovery."""
    proof = _write_recovery_proof(tmp_path)
    activities = _activities(tmp_path)
    payload = _payload(ScheduleKind.RECOVERY_VERIFY, "2026-09-14T05:15:00+08:00")

    result = activities.perform_hk_v1_recovery_verification(ActivityContext("recovery", 1), payload)

    assert result["result"] == "RECOVERY_PROOF_VERIFIED"
    assert result["proof_fingerprint"] == f"sha256:{sha256(proof).hexdigest()}"
    assert result["recovery_executed"] is False


def test_recovery_verification_reports_real_live_execution_separately(tmp_path: Path) -> None:
    """A seven-step live readback produces the only Gate-F-eligible timer result."""
    proof = _write_live_recovery_proof(tmp_path)
    activities = _activities(tmp_path)
    payload = _payload(ScheduleKind.RECOVERY_VERIFY, "2026-09-14T05:15:00+08:00")

    result = activities.perform_hk_v1_recovery_verification(ActivityContext("recovery", 1), payload)

    assert result["result"] == "LIVE_RECOVERY_PROOF_VERIFIED"
    assert result["proof_fingerprint"] == f"sha256:{sha256(proof).hexdigest()}"
    assert result["recovery_executed"] is True


def test_telemetry_retention_only_plans_bounded_candidates_and_replays(tmp_path: Path) -> None:
    """Retention assesses exact local files but performs no deletion without authority."""
    telemetry = tmp_path / "inputs" / "telemetry"
    telemetry.mkdir(parents=True)
    (telemetry / "2026-07-01.ndjson").write_bytes(b"old\n")
    (telemetry / "2026-09-07.ndjson").write_bytes(b"current\n")
    activities = _activities(tmp_path)
    payload = _payload(ScheduleKind.TELEMETRY_RETENTION, "2026-09-08T06:00:00+08:00")

    first = activities.perform_hk_v1_telemetry_retention(ActivityContext("telemetry", 1), payload)
    replay = activities.perform_hk_v1_telemetry_retention(ActivityContext("telemetry", 2), payload)

    assert first["result"] == "RETENTION_ASSESSMENT_RETAINED"
    assert first["deletion_performed"] is False
    assert first["candidate_paths"] == ["2026-07-01.ndjson"]
    assert replay["result_reference"] == first["result_reference"]
    assert replay["result_created"] is False
    assert (telemetry / "2026-07-01.ndjson").read_bytes() == b"old\n"


@pytest.mark.parametrize(
    ("kind", "slot", "method_name", "code"),
    [
        (
            ScheduleKind.AUDIT_ARCHIVE,
            "2026-09-08T04:30:00+08:00",
            "perform_hk_v1_audit_archive",
            "HK_V1_AUDIT_ARCHIVE_NOT_READY",
        ),
        (
            ScheduleKind.RECOVERY_VERIFY,
            "2026-09-14T05:15:00+08:00",
            "perform_hk_v1_recovery_verification",
            "HK_V1_RECOVERY_VERIFICATION_NOT_READY",
        ),
        (
            ScheduleKind.TELEMETRY_RETENTION,
            "2026-09-08T06:00:00+08:00",
            "perform_hk_v1_telemetry_retention",
            "HK_V1_TELEMETRY_RETENTION_NOT_READY",
        ),
    ],
)
def test_missing_prerequisite_is_not_ready_and_writes_no_result(
    tmp_path: Path,
    kind: ScheduleKind,
    slot: str,
    method_name: str,
    code: str,
) -> None:
    """Absent local evidence fails before any maintenance result is retained."""
    activities = _activities(tmp_path)
    method = getattr(activities, method_name)

    with pytest.raises(LiveScheduleError, match=code):
        method(ActivityContext("missing", 1), _payload(kind, slot))

    assert not (tmp_path / "state").exists()


def test_retained_result_binds_request_and_current_matrix_lineage(tmp_path: Path) -> None:
    """Every successful result carries its exact command plus approved Matrix identity."""
    _write_recovery_proof(tmp_path)
    activities = _activities(tmp_path)
    payload = _payload(ScheduleKind.RECOVERY_VERIFY, "2026-09-14T05:15:00+08:00")

    result = activities.perform_hk_v1_recovery_verification(ActivityContext("lineage", 1), payload)
    reference = cast("str", result["result_reference"])
    retained_value = parse_json_bytes(
        (tmp_path / "state" / reference).read_bytes(), max_bytes=1_000_000
    )
    assert type(retained_value) is dict
    retained = cast("dict[str, object]", retained_value)

    assert retained["request"] == payload
    matrix = load_hk_v1_coverage_matrix()
    assert retained["matrix_revision"] == matrix.revision
    assert retained["matrix_fingerprint"] == matrix.fingerprint


@pytest.mark.parametrize(
    "case",
    [
        (
            ScheduleKind.AUDIT_ARCHIVE,
            "2026-09-08T04:30:00+08:00",
            "perform_hk_v1_audit_archive",
            "HK_V1_AUDIT_ARCHIVE_NOT_READY",
        ),
        (
            ScheduleKind.RECOVERY_VERIFY,
            "2026-09-14T05:15:00+08:00",
            "perform_hk_v1_recovery_verification",
            "HK_V1_RECOVERY_VERIFICATION_NOT_READY",
        ),
        (
            ScheduleKind.TELEMETRY_RETENTION,
            "2026-09-08T06:00:00+08:00",
            "perform_hk_v1_telemetry_retention",
            "HK_V1_TELEMETRY_RETENTION_NOT_READY",
        ),
    ],
)
def test_maintenance_matrix_drift_fails_before_any_local_read_or_write(
    tmp_path: Path,
    case: tuple[ScheduleKind, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retained request from another Matrix lineage cannot begin local work."""
    kind, slot, method_name, code = case
    payload = _payload(kind, slot)
    matrix = load_hk_v1_coverage_matrix()
    drifted = replace(
        matrix,
        revision="HK-V1-004",
        fingerprint="sha256:" + "4" * 64,
    )

    def approve_matrix(_matrix: HongKongV1CoverageMatrix) -> bool:
        return True

    def unexpected_read(*_args: object, **_kwargs: object) -> None:
        pytest.fail("matrix drift reached a local read")

    def unexpected_inventory(*_args: object, **_kwargs: object) -> None:
        pytest.fail("matrix drift reached an inventory read")

    monkeypatch.setattr(v1_schedule, "is_hk_v1_coverage_matrix_policy_approved", approve_matrix)
    monkeypatch.setattr(v1_maintenance, "is_hk_v1_coverage_matrix_policy_approved", approve_matrix)
    monkeypatch.setattr(v1_maintenance, "_read_regular", unexpected_read)
    monkeypatch.setattr(v1_maintenance, "_directory_inventory", unexpected_inventory)
    activities = LocalMaintenanceActivities(_configuration(tmp_path), drifted)

    with pytest.raises(LiveScheduleError, match=code):
        getattr(activities, method_name)(ActivityContext("drift", 1), payload)

    assert not (tmp_path / "state").exists()
