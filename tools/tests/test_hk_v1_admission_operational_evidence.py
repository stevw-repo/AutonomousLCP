"""Closed Gate F/G owner-evidence aggregate tests."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_control_plane.v1_schedule import (
    LocalLiveScheduleStore,
    ScheduleKind,
    enqueue_schedule,
    mark_schedule_terminal,
    parse_live_schedule_state_bytes,
)
from asklegal_observability import (
    OPERATIONAL_CATEGORY_ORDER,
    aggregate_operational_status,
    allowed_emitters,
    build_event_observation,
    build_operational_event,
    build_status_scope,
    build_stream_spec,
    clear_code_for,
    serialize_operational_status,
)
from asklegal_reporting import (
    hk_v1_due_cycle_manifest_key,
    hk_v1_due_family_acquisition_key,
    load_hk_v1_coverage_matrix,
)

from tools.hk_v1_admission_operational_evidence import (
    GateFEvidenceSources,
    GateGEvidenceSources,
    OperationalEvidenceError,
    build_gate_f_operational_evidence,
    build_gate_g_live_lineage,
    build_host_supervision_readback,
    build_schedule_execution_readback,
    build_scheduled_cycle_readback,
    parse_gate_f_operational_evidence,
    parse_gate_g_live_lineage,
)
from tools.hk_v1_host_reboot import (
    RebootCommandResult,
    build_host_reboot_authority,
    build_host_reboot_plan,
    host_reboot_plan_bytes,
    run_host_reboot,
)
from tools.hk_v1_rotate_credentials import (
    CredentialManifestEntry,
    CredentialRotationReport,
    CredentialRotationState,
    build_credential_manifest,
    credential_manifest_bytes,
    credential_rotation_report_bytes,
    required_credential_names,
)
from tools.tests.test_v1_poc_collect_host_facts import complete_fake_host_facts
from tools.v1_poc_collect_host_facts import (
    host_facts_document,
    parse_host_facts_output_bytes,
)

FP = "sha256:" + "a" * 64
STATE_0 = "srv_" + "0" * 48
STATE_1 = "srv_" + "1" * 48
STATE_2 = "srv_" + "2" * 48
BOOT_0 = "sha256:" + "0" * 64
BOOT_1 = "sha256:" + "1" * 64
_CONTAINERS = (
    "asklegal-acquisition-worker",
    "asklegal-control-plane",
    "asklegal-dts-general",
    "asklegal-dts-promotion",
    "asklegal-egress-model",
    "asklegal-egress-promotion",
    "asklegal-egress-source",
    "asklegal-legal-processing-worker",
    "asklegal-otel-collector",
    "asklegal-promotion-worker",
    "asklegal-review-api",
    "asklegal-sql-server",
    "asklegal-vault-primary",
    "asklegal-vault-recovery",
)
_HOST_APPLY_ACTIONS = (
    "PROVISION_RUNTIME_PATHS",
    "STAGE_RUNTIME_CONFIGURATION",
    "RECONCILE_NETWORKS",
    "INSTALL_SYSTEMD_UNITS",
    *("REPLACE_DIGEST_PINNED_SERVICE" for _ in range(5)),
    "ENABLE_START_TARGET_AND_TIMERS",
    "RECOLLECT_HOST_FACTS",
)


def _empty_reboot_calls() -> list[tuple[str, ...]]:
    return []


@dataclass
class _RebootRunner:
    calls: list[tuple[str, ...]] = field(default_factory=_empty_reboot_calls)

    def run(self, argv: tuple[str, ...]) -> RebootCommandResult:
        self.calls.append(argv)
        return RebootCommandResult(0, "accepted", "")


def _identity(kind: str, value: str) -> str:
    return "sha256:" + sha256(f"{kind}:{value}".encode()).hexdigest()


def _sealed(value: dict[str, JsonValue]) -> bytes:
    body = dict(value)
    body["fingerprint"] = "sha256:" + sha256(canonicalize(value)).hexdigest()
    return canonicalize(checked_json_value(body))


def _test_object(value: object) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    assert isinstance(parsed, dict)
    return parsed


def _test_array(value: object) -> list[JsonValue]:
    parsed = checked_json_value(value)
    assert isinstance(parsed, list)
    return parsed


def _schedule_state(*, include_reconciliation: bool = True) -> bytes:
    slots = (
        (ScheduleKind.OBSERVATION, "2026-09-07T02:15:00+08:00"),
        (ScheduleKind.RECONCILIATION, "2026-09-13T03:15:00+08:00"),
        (ScheduleKind.AUDIT_ARCHIVE, "2026-09-07T04:30:00+08:00"),
        (ScheduleKind.RECOVERY_VERIFY, "2026-09-07T05:15:00+08:00"),
        (ScheduleKind.TELEMETRY_RETENTION, "2026-09-07T06:00:00+08:00"),
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "schedule.json"
        store = LocalLiveScheduleStore(path)
        matrix = load_hk_v1_coverage_matrix()
        for kind, slot in slots:
            if kind is ScheduleKind.RECONCILIATION and not include_reconciliation:
                continue
            result = enqueue_schedule(store, kind, slot, matrix=matrix)
            mark_schedule_terminal(store, result.operation_id)
        return path.read_bytes()


def operational_host_facts(boot_id_fingerprint: str = FP) -> bytes:
    """Return one complete operational host envelope with the requested boot identity."""
    envelope = complete_fake_host_facts()
    document = host_facts_document(envelope)
    legacy = _test_object(document["legacy_facts"])
    document["legacy_facts"] = legacy
    kernel = _test_object(legacy["kernel"])
    legacy["kernel"] = kernel
    kernel["boot_id_fingerprint"] = boot_id_fingerprint
    systemd = _test_object(legacy["systemd"])
    legacy["systemd"] = systemd
    target = _test_object(systemd["target"])
    systemd["target"] = target
    target["sub_state"] = "active"
    timer_rows = [_test_object(timer) for timer in _test_array(systemd["timer_units"])]
    for timer in timer_rows:
        timer["sub_state"] = "waiting"
    timers: list[JsonValue] = []
    timers.extend(timer_rows)
    systemd["timer_units"] = timers
    legacy["containers"] = [
        {
            "health": "HEALTHY",
            "image_id": "sha256:" + f"{index:x}" * 64,
            "name": name,
            "runtime_state": "running",
        }
        for index, name in enumerate(_CONTAINERS, start=1)
    ]
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )


def _host_semantic_fingerprint(raw: bytes) -> str:
    envelope = parse_host_facts_output_bytes(raw)
    content = canonicalize(checked_json_value(host_facts_document(envelope)))
    return "sha256:" + sha256(content).hexdigest()


def _host_apply_state(host_fingerprint: str) -> bytes:
    receipts: list[JsonValue] = []
    for sequence, action in enumerate(_HOST_APPLY_ACTIONS, start=1):
        receipts.append(
            {
                "action": f"{sequence:03d}|{action}|fixture=exact",
                "argv_fingerprint": _identity("argv", str(sequence)),
                "readback": (
                    {"host_facts_fingerprint": host_fingerprint}
                    if sequence == len(_HOST_APPLY_ACTIONS)
                    else {"action_complete": True}
                ),
                "returncode": 0,
                "sequence": sequence,
                "stderr_fingerprint": _identity("stderr", str(sequence)),
                "stdout_fingerprint": _identity("stdout", str(sequence)),
            }
        )
    return _sealed(
        {
            "application_build_results_fingerprint": _identity("build", "results"),
            "application_build_results_path": None,
            "authority_fingerprint": _identity("host", "authority"),
            "authority_id": "auth_" + "a" * 48,
            "complete": True,
            "index_deleted": False,
            "plan_fingerprint": _identity("host", "plan"),
            "provider_called": False,
            "reboot_performed": False,
            "recollected_host_facts_fingerprint": host_fingerprint,
            "recollected_host_facts_path": "/var/lib/asklegal/host/post-reconcile.json",
            "result": "COMPLETE",
            "rollback_complete": False,
            "rollback_receipts": [],
            "routing_mutated": False,
            "schema_id": "asklegal.hk-v1-host-apply-state/v1",
            "schema_version": "1.0.0",
            "source_called": False,
            "step_receipts": receipts,
        }
    )


def _credential_evidence() -> tuple[bytes, tuple[bytes, ...]]:
    entries = tuple(
        CredentialManifestEntry(name, ("asklegal-control-plane.service",))
        for name in required_credential_names()
    )
    manifest = build_credential_manifest(entries)
    reports = tuple(
        credential_rotation_report_bytes(
            CredentialRotationReport(
                rotation_id="rot_" + sha256(name.encode()).hexdigest()[:48],
                manifest_fingerprint=manifest.manifest_fingerprint,
                credential_name=name,
                predecessor_binding_ref=(
                    "binding_" + sha256((name + ":old").encode()).hexdigest()[:48]
                ),
                candidate_binding_ref=(
                    "binding_" + sha256((name + ":new").encode()).hexdigest()[:48]
                ),
                dependent_units=("asklegal-control-plane.service",),
                state=CredentialRotationState.SUCCEEDED,
                complete=True,
                new_value_works=True,
                old_value_rejected=True,
                old_binding_restored=False,
                candidate_material_absent=False,
                obsolete_binding_absent=True,
                plaintext_staging_absent=True,
                blocker_codes=(),
            )
        )
        for name in required_credential_names()
    )
    return credential_manifest_bytes(manifest), reports


def _reboot_readback(post_host_facts: bytes, pre_boot_id_fingerprint: str | None = None) -> bytes:
    document = host_facts_document(parse_host_facts_output_bytes(post_host_facts))
    legacy = _test_object(document["legacy_facts"])
    kernel = _test_object(legacy["kernel"])
    post_boot = kernel["boot_id_fingerprint"]
    assert isinstance(post_boot, str)
    pre_boot = pre_boot_id_fingerprint or (
        "sha256:" + ("e" if post_boot != "sha256:" + "e" * 64 else "f") * 64
    )
    pre_host = operational_host_facts(pre_boot)
    now = datetime(2026, 9, 9, 1, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        post_path = root / "post-host.json"
        state_path = root / "state" / "reboot.json"
        plan = build_host_reboot_plan(pre_host, post_path, state_path)
        authority = build_host_reboot_authority(
            plan,
            authority_id="auth_" + "d" * 48,
            signer_subject="person-local-1",
            authorized_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=5),
        )
        runner = _RebootRunner()
        plan_bytes = host_reboot_plan_bytes(plan)
        run_host_reboot(plan_bytes, authority, now=now, runner=runner)
        post_path.write_bytes(post_host_facts)
        result = run_host_reboot(
            plan_bytes,
            authority,
            now=now + timedelta(minutes=1),
            runner=runner,
        )
        assert len(runner.calls) == 1
        return result


def _owner(schema: str, **facts: JsonValue) -> bytes:
    return _sealed({"schema_id": schema, "schema_version": "1.0.0", **facts})


def _operational_status() -> bytes:
    streams = tuple(
        build_stream_spec(
            category,
            allowed_emitters(category)[0],
            _identity("observability-subject", category.value),
        )
        for category in OPERATIONAL_CATEGORY_ORDER
    )
    scope = build_status_scope(streams)
    observed_at = datetime(2026, 9, 8, 1, 2, 3, tzinfo=UTC)
    events = tuple(
        build_operational_event(
            scope,
            stream,
            build_event_observation(1, observed_at, clear_code_for(stream.category)),
        )
        for stream in scope.streams
    )
    return json.dumps(
        serialize_operational_status(aggregate_operational_status(scope, events, observed_at)),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


_LIVE_RECOVERY_STEPS = (
    "SQL_RESTORE_READBACK",
    "PRIMARY_VAULT_CLEAN_ROOM_READBACK",
    "RECOVERY_VAULT_CLEAN_ROOM_READBACK",
    "SCHEDULER_GENERAL_FORWARD",
    "SCHEDULER_GENERAL_REVERSE",
    "SCHEDULER_PROMOTION_FORWARD",
    "SCHEDULER_PROMOTION_REVERSE",
)


def _recovery() -> bytes:
    receipts: list[JsonValue] = []
    for index, step in enumerate(_LIVE_RECOVERY_STEPS):
        readback = _identity("live-recovery-readback", step)
        receipts.append(
            {
                "effect_fingerprint": readback,
                "plan_fingerprint": FP,
                "readback_fingerprint": readback,
                "step": step,
                "target_identity": f"r_{index:032x}",
            }
        )
    return (
        _sealed(
            {
                "live_recovery_proved": True,
                "operation_id": "r_" + "f" * 32,
                "plan_fingerprint": FP,
                "receipts": receipts,
                "schema": "asklegal.hk-v1-live-recovery-execution-result/v1",
            }
        )
        + b"\n"
    )


def _local_prototype_recovery() -> bytes:
    return (
        canonicalize(
            checked_json_value(
                {
                    "assessment_fingerprint": FP,
                    "blockers": [],
                    "live_recovery_proved": False,
                    "local_contract_proved": True,
                    "mode": "EXECUTE_LOCAL_PROTOTYPE",
                    "operation_id": "rec_local_proof",
                    "request_fingerprint": FP,
                    "schema": "asklegal.hk-v1-local-recovery-result/v1",
                    "status": "LOCAL_PROTOTYPE_PROVED",
                    "targets": {
                        "scheduler_directory_name": "scheduler-a-b",
                        "sql_database_identity": "db_identity",
                        "sql_database_name": "disposable_database",
                        "vault_directory_name": "vault-restore",
                        "vault_identity": "vault_identity",
                    },
                }
            )
        )
        + b"\n"
    )


def _serving_state(state: str) -> bytes:
    predecessor = STATE_0 if state == STATE_1 else STATE_1
    candidate = {
        "approval_id": "apr_" + "a" * 48,
        "candidate_serving_state_id": state,
        "candidate_serving_state_fingerprint": _identity("serving-state", state),
        "coverage_fingerprint": _identity("coverage", state),
        "desired_inventory_fingerprint": _identity("inventory", state),
        "embedding_profile_fingerprint": _identity("embedding", state),
        "embedding_profile_id": "embedding-profile-v1",
        "execution_lineage_id": "exe_" + "b" * 48,
        "predecessor_state_id": predecessor,
        "target_name": "target-" + state[-1],
    }
    return canonicalize(
        checked_json_value(
            {
                "activation": {"candidate": candidate, "receipt_id": "ssr_" + "c" * 48},
                "active_state_id": state,
                "rollback": None,
                "schema_id": "asklegal.local-serving-state/v1",
            }
        )
    )


def _gate_f(
    state: str = STATE_2,
    boot_id_fingerprint: str = FP,
    *,
    restart: bytes | None = None,
) -> bytes:
    host = operational_host_facts(boot_id_fingerprint)
    credential_manifest, reports = _credential_evidence()
    return build_gate_f_operational_evidence(
        GateFEvidenceSources(
            schedule_state=_schedule_execution_readback(boot_id_fingerprint),
            host_facts=host,
            operational_status=_operational_status(),
            supervision=build_host_supervision_readback(
                host_apply_state=_host_apply_state(_host_semantic_fingerprint(host)),
                host_facts=host,
                credential_manifest=credential_manifest,
                credential_rotation_reports=reports,
            ),
            recovery=_recovery(),
            restart=restart or _reboot_readback(host),
            serving_state=_serving_state(state),
        )
    )


def _cycle(kind: str, cutoff: str, result: str, proposal: str | None) -> bytes:
    return canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-v1.acceptance-cycle-result",
                "schema_version": "1.0.0",
                "kind": kind,
                "operation_id": "cyc_" + sha256((kind + cutoff).encode()).hexdigest()[:24],
                "command_fingerprint": FP,
                "observation_cutoff": cutoff,
                "families": ["CASES", "LEGISLATION"],
                "scope_ids": [
                    "HK-CASE-BINDING-POST-1997",
                    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                    "HK-LEG-ORDINANCES",
                    "HK-LEG-SUBSIDIARY",
                ],
                "result": result,
                "blocker_codes": [],
                "proposal_reference": (
                    None
                    if proposal is None
                    else {
                        "vault": "PRIMARY",
                        "logical_key": proposal,
                        "version_id": "v" + "1" * 64,
                        "fingerprint": "sha256:" + sha256(proposal.encode()).hexdigest(),
                        "byte_length": 100,
                    }
                ),
            }
        )
    )


def _promotion(
    operation: str,
    proposal: str,
    predecessor: str,
    state: str,
    target: str,
) -> bytes:
    predecessor_target = "target-t2" if operation == "ROLLBACK" else "target-t1"
    return _owner(
        "asklegal.hk-v1-promotion-readback/v1",
        operation=operation,
        proposal_fingerprint="sha256:" + sha256(proposal.encode()).hexdigest(),
        approval_fingerprint=_identity("approval", proposal),
        predecessor_serving_state_id=predecessor,
        predecessor_serving_state_fingerprint=(
            None if operation == "PROMOTION" else _identity("serving-state", predecessor)
        ),
        predecessor_target_name=None if operation == "PROMOTION" else predecessor_target,
        predecessor_target_fingerprint=(
            None
            if operation == "PROMOTION"
            else "sha256:" + sha256(predecessor_target.encode()).hexdigest()
        ),
        serving_state_id=state,
        serving_state_fingerprint=_identity("serving-state", state),
        target_name=target,
        target_fingerprint="sha256:" + sha256(target.encode()).hexdigest(),
        backup_fingerprint=_identity("backup", target),
        readback_fingerprint=_identity("readback", target),
        result="COMPLETE",
    )


def _gate_g_sources() -> GateGEvidenceSources:
    baseline = "proposals/baseline.json"
    changed = "proposals/changed.json"
    post_host = operational_host_facts(BOOT_1)
    linked_restart = _reboot_readback(post_host, BOOT_0)
    first_schedule_state = _schedule_state(include_reconciliation=False)
    second_schedule_state = _schedule_state()
    return GateGEvidenceSources(
        baseline_cycle=_cycle("BASELINE", "2026-09-01T00:00:00+00:00", "PROPOSAL_READY", baseline),
        baseline_promotion=_promotion("PROMOTION", baseline, STATE_0, STATE_1, "target-t1"),
        changed_cycle=_cycle("UPDATE", "2026-09-02T00:00:00+00:00", "PROPOSAL_READY", changed),
        changed_promotion=_promotion("PROMOTION", changed, STATE_1, STATE_2, "target-t2"),
        no_change_cycle=_cycle("UPDATE", "2026-09-03T00:00:00+00:00", "NO_CHANGE", None),
        pre_reboot=_gate_f(boot_id_fingerprint=BOOT_0),
        post_reboot=_gate_f(boot_id_fingerprint=BOOT_1, restart=linked_restart),
        rollback=_promotion("ROLLBACK", changed, STATE_2, STATE_1, "target-t1"),
        restoration=_promotion("RESTORATION", changed, STATE_1, STATE_2, "target-t2"),
        post_reboot_no_change_cycle=_scheduled_cycle(
            ScheduleKind.OBSERVATION,
            "NO_CHANGE",
            None,
            BOOT_1,
            schedule_state=first_schedule_state,
        ),
        post_reboot_changed_cycle=_scheduled_cycle(
            ScheduleKind.RECONCILIATION,
            "PROPOSAL_READY",
            "proposals/post-reboot-changed.json",
            BOOT_1,
            schedule_state=second_schedule_state,
        ),
        next_health=_gate_f(boot_id_fingerprint=BOOT_1, restart=linked_restart),
    )


def _due_source_ids(cycle_kind: str) -> list[str]:
    daily = {
        "DAILY_AND_COMPLETE_AT_CYCLE_CUTOFF",
        "DAILY_AND_COMPLETE_WITHIN_24_HOURS_OF_CUTOFF",
        "DAILY_DISCOVERY",
        "DAILY_INVENTORY_AND_ON_CHANGE_ACQUISITION",
        "DAILY_SIGNAL_AND_ON_CHANGE_ACQUISITION",
    }
    weekly = {"WEEKLY", "WEEKLY_AND_EVENT_TRIGGERED"}
    monthly = {"MONTHLY_AND_EVENT_TRIGGERED", "MONTHLY_EVENT_TRIGGERED_AND_ON_DEMAND"}
    allowed = daily if cycle_kind == "DAILY_CURRENT_LAW" else daily | weekly | monthly
    return sorted(
        {row.source_id for row in load_hk_v1_coverage_matrix().rows if row.cadence in allowed}
    )


def _scheduled_cycle(
    schedule_kind: ScheduleKind,
    result: str,
    proposal: str | None,
    boot_id_fingerprint: str,
    *,
    schedule_state: bytes | None = None,
) -> bytes:
    schedule_state = schedule_state or _schedule_state()
    commands, _active = parse_live_schedule_state_bytes(schedule_state)
    command = next(item for item in commands if item.request.kind is schedule_kind)
    instruction = command.root_instruction
    assert instruction is not None
    complete_sources = _due_source_ids(instruction.cycle_kind.value)
    due: dict[str, object] = {
        "cycle_id": instruction.cycle_id,
        "plan_fingerprint": _identity("plan", instruction.cycle_id),
        "manifest_reference": {
            "vault": "PRIMARY",
            "logical_key": hk_v1_due_cycle_manifest_key(instruction.cycle_id),
            "version_id": "v" + "b" * 64,
            "fingerprint": _identity("manifest", instruction.cycle_id),
            "byte_length": 1,
        },
        "manifest_created": True,
        "family_acquisition_evidence": {
            "cycle_id": instruction.cycle_id,
            "evidence_reference": {
                "vault": "PRIMARY",
                "logical_key": hk_v1_due_family_acquisition_key(instruction.cycle_id),
                "version_id": "v" + "d" * 64,
                "fingerprint": _identity("family-evidence", instruction.cycle_id),
                "byte_length": 2,
            },
            "evidence_created": True,
        },
        "predecessor_state_fingerprint": _identity("predecessor", instruction.cycle_id),
        "predecessor_state_created": True,
        "complete_source_ids": complete_sources,
        "missing_source_ids": [],
        "duplicate_source_ids": [],
        "gap_source_ids": [],
        "failed_source_ids": [],
        "accounting_complete": True,
        "release_blocking": False,
        "disposition": "COMPLETE",
        "acceptance": json.loads(
            _cycle(
                "UPDATE",
                instruction.observation_cutoff,
                result,
                proposal,
            )
        ),
    }
    return build_scheduled_cycle_readback(
        schedule_state=schedule_state,
        host_facts=operational_host_facts(boot_id_fingerprint),
        root_operation_id=command.root_operation_id,
        scheduler_output=canonicalize(checked_json_value(due)),
    )


def _maintenance_result(
    kind: ScheduleKind,
    details: dict[str, JsonValue],
    schedule_state: bytes | None = None,
) -> bytes:
    schedule_state = schedule_state or _schedule_state()
    commands, _active = parse_live_schedule_state_bytes(schedule_state)
    command = next(item for item in commands if item.request.kind is kind)
    request = command.request
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1.local-maintenance-result",
        "schema_version": "1.0.0",
        "request": {
            "command_id": request.command_id,
            "command_fingerprint": request.command_fingerprint,
            "matrix_fingerprint": request.matrix_fingerprint,
            "matrix_revision": request.matrix_revision,
            "attempt_number": command.attempt_number,
            "operation_id": command.attempt_operation_id,
            "schedule_kind": kind.value,
            "scheduled_at": request.scheduled_at,
            "state": "REQUESTED",
        },
        "matrix_revision": request.matrix_revision,
        "matrix_fingerprint": request.matrix_fingerprint,
        "details": details,
    }
    body["fingerprint"] = "sha256:" + sha256(canonicalize(body)).hexdigest()
    return canonicalize(checked_json_value(body)) + b"\n"


def _schedule_execution_readback(boot_id_fingerprint: str) -> bytes:
    state = _schedule_state()
    return build_schedule_execution_readback(
        state,
        {
            "OBSERVATION": _scheduled_cycle(
                ScheduleKind.OBSERVATION,
                "NO_CHANGE",
                None,
                boot_id_fingerprint,
            ),
            "RECONCILIATION": _scheduled_cycle(
                ScheduleKind.RECONCILIATION,
                "PROPOSAL_READY",
                "proposals/gate-f-reconciliation.json",
                boot_id_fingerprint,
            ),
            "AUDIT_ARCHIVE": _maintenance_result(
                ScheduleKind.AUDIT_ARCHIVE,
                {
                    "result": "AUDIT_ARCHIVE_COMPLETE",
                    "input_count": 1,
                    "inventory": [{"read_back_verified": True}],
                },
            ),
            "RECOVERY_VERIFY": _maintenance_result(
                ScheduleKind.RECOVERY_VERIFY,
                {
                    "result": "LIVE_RECOVERY_PROOF_VERIFIED",
                    "proof_fingerprint": FP,
                    "recovery_executed": True,
                },
            ),
            "TELEMETRY_RETENTION": _maintenance_result(
                ScheduleKind.TELEMETRY_RETENTION,
                {
                    "result": "RETENTION_ASSESSMENT_RETAINED",
                    "retention_days": 30,
                    "candidate_paths": [],
                    "inventory": [],
                    "deletion_performed": False,
                },
            ),
        },
    )


def test_gate_f_round_trip_parses_every_owning_artifact() -> None:
    """The operational aggregate is derived from six strict owner schemas."""
    result = parse_gate_f_operational_evidence(_gate_f())
    assert result.result == "COMPLETE"
    assert result.serving_state_id == STATE_2
    assert result.evidence_kinds == (
        "HOST",
        "OBSERVABILITY",
        "RECOVERY",
        "RESTART",
        "SCHEDULE",
        "SUPERVISION",
    )


def test_gate_f_rejects_self_declared_or_incomplete_host_claim() -> None:
    """A generic VERIFIED document cannot substitute for the host collector envelope."""
    sources = replace(_gate_f_sources(), host_facts=_owner("generic", result="VERIFIED"))
    with pytest.raises(OperationalEvidenceError, match="GATE_F_HOST_INVALID"):
        build_gate_f_operational_evidence(sources)


def test_gate_f_rejects_local_prototype_recovery_as_live_recovery() -> None:
    """A filesystem prototype cannot satisfy the real Gate-F recovery requirement."""
    sources = replace(_gate_f_sources(), recovery=_local_prototype_recovery())
    with pytest.raises(OperationalEvidenceError, match="GATE_F_RECOVERY_INVALID"):
        build_gate_f_operational_evidence(sources)


def test_gate_f_rejects_terminal_schedule_flags_without_all_five_outputs() -> None:
    """A terminal Control state alone cannot prove that any timer achieved its work."""
    sources = replace(_gate_f_sources(), schedule_state=_schedule_state())
    with pytest.raises(OperationalEvidenceError, match="GATE_F_SCHEDULE_INVALID"):
        build_gate_f_operational_evidence(sources)


def _gate_f_sources() -> GateFEvidenceSources:
    """Recover fixture source bytes used by the positive Gate F helper."""
    host = operational_host_facts()
    credential_manifest, reports = _credential_evidence()
    return GateFEvidenceSources(
        _schedule_execution_readback(FP),
        host,
        _operational_status(),
        build_host_supervision_readback(
            host_apply_state=_host_apply_state(_host_semantic_fingerprint(host)),
            host_facts=host,
            credential_manifest=credential_manifest,
            credential_rotation_reports=reports,
        ),
        _recovery(),
        _reboot_readback(host),
        _serving_state(STATE_2),
    )


def test_gate_g_round_trip_binds_ordered_two_state_lineage() -> None:
    """Baseline, update, no-change, reboot, rollback, restore, and health remain ordered."""
    result = parse_gate_g_live_lineage(build_gate_g_live_lineage(_gate_g_sources()))
    assert result.result == "COMPLETE"
    assert result.baseline_serving_state_id == STATE_1
    assert result.current_serving_state_id == STATE_2
    assert result.target_name == "target-t2"
    assert result.proposal_fingerprint == "sha256:" + sha256(b"proposals/changed.json").hexdigest()


def test_gate_g_rejects_wrong_rollback_predecessor() -> None:
    """A rollback that does not move exact T2 to T1 cannot enter Gate G."""
    sources = _gate_g_sources()
    changed = "proposals/changed.json"
    forged = replace(
        sources,
        rollback=_promotion("ROLLBACK", changed, STATE_0, STATE_1, "target-t1"),
    )
    with pytest.raises(OperationalEvidenceError, match="GATE_G_LINEAGE_INVALID"):
        build_gate_g_live_lineage(forged)


def test_gate_g_rejects_replayed_same_boot_as_reboot_evidence() -> None:
    """One Gate-F snapshot cannot be relabelled as both sides of a reboot."""
    sources = _gate_g_sources()
    forged = replace(sources, post_reboot=sources.pre_reboot, next_health=sources.pre_reboot)
    with pytest.raises(OperationalEvidenceError, match="GATE_G_LINEAGE_INVALID"):
        build_gate_g_live_lineage(forged)


def test_gate_g_rejects_unrelated_reboot_that_does_not_bridge_pre_to_post() -> None:
    """A changed post boot is insufficient unless its reboot began at the pre boot."""
    sources = _gate_g_sources()
    unrelated_post = _gate_f(boot_id_fingerprint=BOOT_1)
    forged = replace(sources, post_reboot=unrelated_post, next_health=unrelated_post)
    with pytest.raises(OperationalEvidenceError, match="GATE_G_LINEAGE_INVALID"):
        build_gate_g_live_lineage(forged)


def test_gate_g_rejects_same_schedule_state_replayed_as_two_cycles() -> None:
    """Different acceptance bytes cannot turn one retained scheduler state into two cycles."""
    sources = _gate_g_sources()
    replayed_state = _schedule_state()
    forged = replace(
        sources,
        post_reboot_no_change_cycle=_scheduled_cycle(
            ScheduleKind.OBSERVATION,
            "NO_CHANGE",
            None,
            BOOT_1,
            schedule_state=replayed_state,
        ),
        post_reboot_changed_cycle=_scheduled_cycle(
            ScheduleKind.RECONCILIATION,
            "PROPOSAL_READY",
            "proposals/post-reboot-changed.json",
            BOOT_1,
            schedule_state=replayed_state,
        ),
    )
    with pytest.raises(OperationalEvidenceError, match="GATE_G_LINEAGE_INVALID"):
        build_gate_g_live_lineage(forged)


def test_gate_g_rejects_identical_t1_t2_and_no_op_transitions() -> None:
    """A renamed update cannot prove changed promotion, rollback, or restoration."""
    sources = _gate_g_sources()
    changed = "proposals/changed.json"
    target = "target-t1"
    target_fingerprint = "sha256:" + sha256(target.encode()).hexdigest()

    def no_op(operation: str) -> bytes:
        return _owner(
            "asklegal.hk-v1-promotion-readback/v1",
            operation=operation,
            proposal_fingerprint="sha256:" + sha256(changed.encode()).hexdigest(),
            approval_fingerprint=FP,
            predecessor_serving_state_id=STATE_1,
            predecessor_serving_state_fingerprint=None if operation == "PROMOTION" else FP,
            predecessor_target_name=None if operation == "PROMOTION" else target,
            predecessor_target_fingerprint=(
                None if operation == "PROMOTION" else target_fingerprint
            ),
            serving_state_id=STATE_1,
            serving_state_fingerprint=FP,
            target_name=target,
            target_fingerprint=target_fingerprint,
            backup_fingerprint=FP,
            readback_fingerprint=FP,
            result="COMPLETE",
        )

    forged = replace(
        sources,
        changed_promotion=no_op("PROMOTION"),
        pre_reboot=_gate_f(STATE_1),
        post_reboot=_gate_f(STATE_1),
        rollback=no_op("ROLLBACK"),
        restoration=no_op("RESTORATION"),
        next_health=_gate_f(STATE_1),
    )
    with pytest.raises(OperationalEvidenceError, match="GATE_G_PROMOTION_INVALID"):
        build_gate_g_live_lineage(forged)


def test_gate_g_rejects_unrelated_transition_proposal_and_approval() -> None:
    """Correct state names cannot launder rollback under an unrelated authority lineage."""
    sources = _gate_g_sources()
    forged = replace(
        sources,
        rollback=_promotion("ROLLBACK", "proposals/unrelated.json", STATE_2, STATE_1, "target-t1"),
        restoration=_promotion(
            "RESTORATION", "proposals/another.json", STATE_1, STATE_2, "target-t2"
        ),
    )
    with pytest.raises(OperationalEvidenceError, match="GATE_G_LINEAGE_INVALID"):
        build_gate_g_live_lineage(forged)


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("rollback", "serving_state_fingerprint"),
        ("rollback", "backup_fingerprint"),
        ("rollback", "readback_fingerprint"),
        ("restoration", "serving_state_fingerprint"),
        ("restoration", "backup_fingerprint"),
        ("restoration", "readback_fingerprint"),
    ],
)
def test_gate_g_rejects_transition_state_backup_or_readback_drift(kind: str, field: str) -> None:
    """Each transition repeats the exact active T1 or T2 verified artifact set."""
    sources = _gate_g_sources()
    document = json.loads(getattr(sources, kind))
    document.pop("fingerprint")
    document[field] = "sha256:" + "f" * 64
    forged = replace(sources, **{kind: _sealed(document)})
    with pytest.raises(OperationalEvidenceError, match="GATE_G_LINEAGE_INVALID"):
        build_gate_g_live_lineage(forged)


def test_gate_g_parser_rejects_embedded_artifact_tampering() -> None:
    """The composite cannot preserve VERIFIED after an owning byte changes."""
    content = build_gate_g_live_lineage(_gate_g_sources())
    tampered = content.replace(b"7461726765742d7432", b"7461726765742d7832", 1)
    with pytest.raises(OperationalEvidenceError):
        parse_gate_g_live_lineage(tampered)


# Public fixture API used by operator-path tests without copying large owner artifacts.
schedule_state_fixture = _schedule_state
scheduled_cycle_fixture = _scheduled_cycle
maintenance_result_fixture = _maintenance_result
gate_f_sources_fixture = _gate_f_sources
gate_g_sources_fixture = _gate_g_sources
