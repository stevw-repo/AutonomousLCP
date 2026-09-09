"""Closed owner-artifact aggregates for Hong Kong V1 admission Gates F and G."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Never

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_control_plane.v1_acceptance import validate_hk_v1_acceptance_cycle_result
from asklegal_control_plane.v1_pipeline import rebuild_hk_v1_due_handoff
from asklegal_control_plane.v1_schedule import (
    LiveScheduleError,
    ScheduleState,
    StoredScheduleCommand,
    parse_live_schedule_state_bytes,
)
from asklegal_observability import (
    OPERATIONAL_CATEGORY_ORDER,
    ObservabilityError,
    parse_operational_status,
)

from tools.hk_v1_host_reboot import (
    HostRebootError,
    HostRebootReadback,
    parse_host_reboot_readback_details,
)
from tools.hk_v1_rotate_credentials import (
    CredentialRotationState,
    parse_credential_manifest_bytes,
    parse_credential_rotation_report_bytes,
    required_credential_names,
)
from tools.v1_poc_collect_host_facts import (
    host_facts_document,
    parse_host_facts_output_bytes,
    validated_complete_host_facts,
)

_FP = re.compile(r"^sha256:[0-9a-f]{64}$")
_STATE = re.compile(r"^srv_[0-9a-f]{48}$")
_RECOVERY_ID = re.compile(r"^r_[0-9a-f]{32}$")
_F_SCHEMA = "asklegal.hk-v1-gate-f-operational-evidence/v1"
_G_SCHEMA = "asklegal.hk-v1-gate-g-live-lineage/v1"
_SCHEDULED_CYCLE_SCHEMA = "asklegal.hk-v1-scheduled-cycle-readback/v1"
_SCHEDULE_EXECUTION_SCHEMA = "asklegal.hk-v1-schedule-execution-readback/v1"
_SUPERVISION_SCHEMA = "asklegal.hk-v1-host-supervision-readback/v1"
_SERVING_STATE_SCHEMA = "asklegal.local-serving-state/v1"
_VERSION = "1.0.0"
_MAX_BYTES = 10_000_000
_TIMER_COUNT = 5
_APPLICATION_COUNT = 5
_SCHEDULER_COUNT = 2
_BACKUP_COUNT = 2
_PRIVATE_SUBNET_COUNT = 10
_MAX_BACKUP_AGE_SECONDS = 86_400
_MAX_TELEMETRY_AGE_SECONDS = 300
_F_KINDS = ("HOST", "OBSERVABILITY", "RECOVERY", "RESTART", "SCHEDULE", "SUPERVISION")
_G_KINDS = (
    "BASELINE_CYCLE",
    "BASELINE_PROMOTION",
    "CHANGED_CYCLE",
    "CHANGED_PROMOTION",
    "NO_CHANGE_CYCLE",
    "PRE_REBOOT",
    "POST_REBOOT",
    "ROLLBACK",
    "RESTORATION",
    "POST_REBOOT_NO_CHANGE_CYCLE",
    "POST_REBOOT_CHANGED_CYCLE",
    "NEXT_HEALTH",
)
_HOST_CLASSES = (
    "APPLICATION_READINESS",
    "BACKUP_FRESHNESS",
    "CONTAINERS_IMAGES_HEALTH",
    "CREDENTIAL_METADATA",
    "FILESYSTEM_CAPACITY",
    "NETWORK_POLICY",
    "OS_KERNEL",
    "RESOURCES",
    "SCHEDULER_IDENTITIES",
    "SYSTEMD_UNITS_TIMERS",
    "TELEMETRY_FRESHNESS",
)
_SCHEDULE_KINDS = {
    "OBSERVATION",
    "RECONCILIATION",
    "AUDIT_ARCHIVE",
    "RECOVERY_VERIFY",
    "TELEMETRY_RETENTION",
}
_LIVE_RECOVERY_STEPS = (
    "SQL_RESTORE_READBACK",
    "PRIMARY_VAULT_CLEAN_ROOM_READBACK",
    "RECOVERY_VAULT_CLEAN_ROOM_READBACK",
    "SCHEDULER_GENERAL_FORWARD",
    "SCHEDULER_GENERAL_REVERSE",
    "SCHEDULER_PROMOTION_FORWARD",
    "SCHEDULER_PROMOTION_REVERSE",
)
_EXPECTED_CONTAINERS = (
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
    "REPLACE_DIGEST_PINNED_SERVICE",
    "REPLACE_DIGEST_PINNED_SERVICE",
    "REPLACE_DIGEST_PINNED_SERVICE",
    "REPLACE_DIGEST_PINNED_SERVICE",
    "REPLACE_DIGEST_PINNED_SERVICE",
    "ENABLE_START_TARGET_AND_TIMERS",
    "RECOLLECT_HOST_FACTS",
)
_F_OWNERS = {
    "HOST": "HOST_COLLECTOR",
    "OBSERVABILITY": "OBSERVABILITY",
    "RECOVERY": "RECOVERY_TOOL",
    "RESTART": "HOST_OPERATOR",
    "SCHEDULE": "CONTROL_PLANE",
    "SUPERVISION": "HOST_OPERATOR",
}
_G_OWNERS = {
    "BASELINE_CYCLE": "CONTROL_PLANE",
    "BASELINE_PROMOTION": "PROMOTION_WORKER",
    "CHANGED_CYCLE": "CONTROL_PLANE",
    "CHANGED_PROMOTION": "PROMOTION_WORKER",
    "NO_CHANGE_CYCLE": "CONTROL_PLANE",
    "PRE_REBOOT": "CONTROL_PLANE",
    "POST_REBOOT": "CONTROL_PLANE",
    "ROLLBACK": "PROMOTION_WORKER",
    "RESTORATION": "PROMOTION_WORKER",
    "POST_REBOOT_NO_CHANGE_CYCLE": "CONTROL_PLANE",
    "POST_REBOOT_CHANGED_CYCLE": "CONTROL_PLANE",
    "NEXT_HEALTH": "CONTROL_PLANE",
}


class OperationalEvidenceError(ValueError):
    """One exact malformed or semantically unproved F/G evidence failure."""


@dataclass(frozen=True, slots=True)
class GateFEvidenceSources:
    """Exact bytes from the six capability-owning Gate F boundaries."""

    schedule_state: bytes
    host_facts: bytes
    operational_status: bytes
    supervision: bytes
    recovery: bytes
    restart: bytes
    serving_state: bytes


@dataclass(frozen=True, slots=True)
class GateFOperationalEvidence:
    """Independently revalidated Gate F aggregate projection."""

    result: str
    serving_state_id: str
    serving_state_fingerprint: str
    boot_id_fingerprint: str
    restart_operation_id: str
    restart_pre_boot_id_fingerprint: str
    evidence_kinds: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class GateGEvidenceSources:
    """Exact ordered owner bytes for the complete Gate G live sequence."""

    baseline_cycle: bytes
    baseline_promotion: bytes
    changed_cycle: bytes
    changed_promotion: bytes
    no_change_cycle: bytes
    pre_reboot: bytes
    post_reboot: bytes
    rollback: bytes
    restoration: bytes
    post_reboot_no_change_cycle: bytes
    post_reboot_changed_cycle: bytes
    next_health: bytes


@dataclass(frozen=True, slots=True)
class ScheduledCycleReadback:
    """One exact terminal scheduled due-cycle and its post-reboot host identity."""

    schedule_kind: str
    root_operation_id: str
    attempt_operation_id: str
    boot_id_fingerprint: str
    cycle_id: str
    scheduled_at: str
    observation_cutoff: str
    terminal_root_operation_ids: tuple[str, ...]
    schedule_state_fingerprint: str
    scheduler_output_fingerprint: str
    acceptance: dict[str, JsonValue]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class GateGLiveLineage:
    """Independently revalidated baseline-to-next-health lineage."""

    result: str
    baseline_serving_state_id: str
    current_serving_state_id: str
    proposal_fingerprint: str
    approval_fingerprint: str
    target_name: str
    target_fingerprint: str
    serving_state_fingerprint: str
    evidence_kinds: tuple[str, ...]
    fingerprint: str


def _fail(code: str) -> Never:
    raise OperationalEvidenceError(code)


def _fingerprint(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


def _object(value: object, code: str) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    if not isinstance(parsed, dict):
        _fail(code)
    return parsed


def _array(value: object, code: str) -> list[JsonValue]:
    parsed = checked_json_value(value)
    if not isinstance(parsed, list):
        _fail(code)
    return parsed


def _document(raw: bytes, code: str, *, newline: bool = False) -> dict[str, JsonValue]:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_BYTES:
        _fail(code)
    canonical = raw[:-1] if newline and raw.endswith(b"\n") else raw
    if newline and raw != canonical + b"\n":
        _fail(code)
    try:
        value = parse_json_bytes(canonical, max_bytes=_MAX_BYTES)
    except (RuntimeError, ValueError) as error:
        raise OperationalEvidenceError(code) from error
    if not isinstance(value, dict) or canonicalize(value) != canonical:
        _fail(code)
    return value


def _sealed(raw: bytes, schema: str, fields: set[str], code: str) -> dict[str, JsonValue]:
    document = _document(raw, code)
    if frozenset(document) != frozenset({"schema_id", "schema_version", "fingerprint", *fields}):
        _fail(code)
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    if (
        document.get("schema_id") != schema
        or document.get("schema_version") != _VERSION
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
    ):
        _fail(code)
    return document


def _maintenance_result(
    raw: bytes, command: StoredScheduleCommand, expected_kind: str, code: str
) -> None:
    document = _document(raw, code, newline=True)
    if frozenset(document) != frozenset(
        {
            "details",
            "fingerprint",
            "matrix_fingerprint",
            "matrix_revision",
            "request",
            "schema_id",
            "schema_version",
        }
    ):
        _fail(code)
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    request = _object(document.get("request"), code)
    details = _object(document.get("details"), code)
    expected_request = {
        "command_id": command.request.command_id,
        "command_fingerprint": command.request.command_fingerprint,
        "matrix_fingerprint": command.request.matrix_fingerprint,
        "matrix_revision": command.request.matrix_revision,
        "attempt_number": command.attempt_number,
        "operation_id": command.attempt_operation_id,
        "schedule_kind": expected_kind,
        "scheduled_at": command.request.scheduled_at,
        "state": "REQUESTED",
    }
    if (
        document.get("schema_id") != "asklegal.hk-v1.local-maintenance-result"
        or document.get("schema_version") != _VERSION
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
        or request != expected_request
        or document.get("matrix_revision") != command.request.matrix_revision
        or document.get("matrix_fingerprint") != command.request.matrix_fingerprint
    ):
        _fail(code)
    if expected_kind == "AUDIT_ARCHIVE":
        inventory = details.get("inventory")
        if (
            details.get("result") != "AUDIT_ARCHIVE_COMPLETE"
            or type(details.get("input_count")) is not int
            or not isinstance(inventory, list)
            or len(inventory) != details.get("input_count")
            or not inventory
            or any(_object(row, code).get("read_back_verified") is not True for row in inventory)
        ):
            _fail(code)
    elif expected_kind == "RECOVERY_VERIFY":
        if (
            details.get("result") != "LIVE_RECOVERY_PROOF_VERIFIED"
            or details.get("recovery_executed") is not True
            or _FP.fullmatch(str(details.get("proof_fingerprint"))) is None
        ):
            _fail(code)
    elif expected_kind == "TELEMETRY_RETENTION":
        if (
            details.get("result") != "RETENTION_ASSESSMENT_RETAINED"
            or details.get("deletion_performed") is not False
            or not isinstance(details.get("inventory"), list)
            or not isinstance(details.get("candidate_paths"), list)
        ):
            _fail(code)
    else:
        _fail(code)


def _schedule(raw: bytes) -> None:
    code = "GATE_F_SCHEDULE_INVALID"
    fields = {"executions", "schedule_state_fingerprint", "schedule_state_hex"}
    document = _sealed(raw, _SCHEDULE_EXECUTION_SCHEMA, fields, code)
    schedule_state = _hex_artifact(
        document, "schedule_state_hex", "schedule_state_fingerprint", code
    )
    try:
        commands, active_command_ids = parse_live_schedule_state_bytes(schedule_state)
    except (LiveScheduleError, TypeError, ValueError) as error:
        raise OperationalEvidenceError(code) from error
    by_kind = {command.request.kind.value: command for command in commands}
    executions = document.get("executions")
    if (
        active_command_ids
        or frozenset(by_kind) != frozenset(_SCHEDULE_KINDS)
        or not isinstance(executions, list)
        or len(executions) != len(_SCHEDULE_KINDS)
    ):
        _fail(code)
    for expected_kind, raw_row in zip(sorted(_SCHEDULE_KINDS), executions, strict=True):
        row = _object(raw_row, code)
        if frozenset(row) != frozenset({"content_hex", "fingerprint", "schedule_kind"}):
            _fail(code)
        content = _hex_artifact(row, "content_hex", "fingerprint", code)
        if row.get("schedule_kind") != expected_kind:
            _fail(code)
        command = by_kind[expected_kind]
        if (
            command.state is not ScheduleState.STARTED
            or command.request.matrix_fingerprint != command.root_matrix_fingerprint
            or command.request.operation_id != command.root_operation_id
        ):
            _fail(code)
        if expected_kind in {"OBSERVATION", "RECONCILIATION"}:
            cycle = parse_scheduled_cycle_readback(content)
            if (
                cycle.schedule_kind != expected_kind
                or cycle.root_operation_id != command.root_operation_id
            ):
                _fail(code)
        else:
            _maintenance_result(content, command, expected_kind, code)


def build_schedule_execution_readback(schedule_state: bytes, executions: dict[str, bytes]) -> bytes:
    """Bind all five terminal timer executions to the exact retained schedule state."""
    if frozenset(executions) != frozenset(_SCHEDULE_KINDS):
        _fail("GATE_F_SCHEDULE_INVALID")
    body: dict[str, JsonValue] = {
        "schema_id": _SCHEDULE_EXECUTION_SCHEMA,
        "schema_version": _VERSION,
        "schedule_state_hex": schedule_state.hex(),
        "schedule_state_fingerprint": _fingerprint(schedule_state),
        "executions": [
            {
                "schedule_kind": kind,
                "content_hex": executions[kind].hex(),
                "fingerprint": _fingerprint(executions[kind]),
            }
            for kind in sorted(_SCHEDULE_KINDS)
        ],
    }
    body["fingerprint"] = _fingerprint(canonicalize(checked_json_value(body)))
    content = canonicalize(checked_json_value(body))
    _schedule(content)
    return content


def _host_details(raw: bytes) -> tuple[str, str, dict[str, JsonValue]]:
    code = "GATE_F_HOST_INVALID"
    try:
        envelope = parse_host_facts_output_bytes(raw)
        legacy = _object(validated_complete_host_facts(envelope), code)
        kernel = _object(legacy.get("kernel"), code)
    except (OperationalEvidenceError, ValueError) as error:
        raise OperationalEvidenceError(code) from error
    boot_id_fingerprint = kernel.get("boot_id_fingerprint")
    if (
        envelope.complete is not True
        or tuple(item.value for item in envelope.collected_fact_classes) != _HOST_CLASSES
        or envelope.missing_fact_classes
        or envelope.failures
        or frozenset(kernel) != frozenset({"boot_id_fingerprint", "release"})
        or _FP.fullmatch(str(boot_id_fingerprint)) is None
    ):
        _fail(code)
    semantic_fingerprint = _fingerprint(
        canonicalize(checked_json_value(host_facts_document(envelope)))
    )
    return str(boot_id_fingerprint), semantic_fingerprint, legacy


def _host(raw: bytes) -> str:
    return _host_details(raw)[0]


def _resource_and_freshness_is_healthy(
    resources: list[JsonValue],
    capacity: list[JsonValue],
    backups: list[JsonValue],
    telemetry: object,
) -> bool:
    resource_rows = [_object(item, "GATE_F_HOST_INVALID") for item in resources]
    for row in resource_rows:
        memory_current = row.get("memory_current_bytes")
        memory_max = row.get("memory_max_bytes")
        tasks_current = row.get("tasks_current")
        tasks_max = row.get("tasks_max")
        if (
            type(memory_current) is not int
            or type(memory_max) is not int
            or memory_current > memory_max
            or type(tasks_current) is not int
            or type(tasks_max) is not int
            or tasks_current > tasks_max
        ):
            return False
    capacity_rows = [_object(item, "GATE_F_HOST_INVALID") for item in capacity]
    for row in capacity_rows:
        available_bytes = row.get("available_bytes")
        inode_available = row.get("inode_available")
        if (
            type(available_bytes) is not int
            or available_bytes <= 0
            or type(inode_available) is not int
            or inode_available <= 0
        ):
            return False
    backup_rows = [_object(item, "GATE_F_HOST_INVALID") for item in backups]
    if len(backup_rows) != _BACKUP_COUNT:
        return False
    for row in backup_rows:
        freshness = _object(row.get("freshness"), "GATE_F_HOST_INVALID")
        age_seconds = freshness.get("age_seconds")
        if (
            freshness.get("present") is not True
            or type(age_seconds) is not int
            or age_seconds > _MAX_BACKUP_AGE_SECONDS
        ):
            return False
    telemetry_freshness = _object(telemetry, "GATE_F_HOST_INVALID")
    telemetry_age_seconds = telemetry_freshness.get("age_seconds")
    return (
        telemetry_freshness.get("present") is True
        and type(telemetry_age_seconds) is int
        and telemetry_age_seconds <= _MAX_TELEMETRY_AGE_SECONDS
    )


def _host_is_operational(legacy: dict[str, JsonValue]) -> bool:  # noqa: PLR0911
    """Derive health from every collector-owned fact instead of summary booleans."""
    try:
        systemd = _object(legacy.get("systemd"), "GATE_F_HOST_INVALID")
        target = _object(systemd.get("target"), "GATE_F_HOST_INVALID")
        services = _array(systemd.get("service_units"), "GATE_F_HOST_INVALID")
        timers = _array(systemd.get("timer_units"), "GATE_F_HOST_INVALID")
        containers = _array(legacy.get("containers"), "GATE_F_HOST_INVALID")
        applications = _array(legacy.get("applications"), "GATE_F_HOST_INVALID")
        schedulers = _array(legacy.get("schedulers"), "GATE_F_HOST_INVALID")
        resources = _array(legacy.get("resources"), "GATE_F_HOST_INVALID")
        capacity = _array(legacy.get("mount_capacity"), "GATE_F_HOST_INVALID")
        backups = _array(
            _object(legacy.get("backup_freshness"), "GATE_F_HOST_INVALID").get("backups"),
            "GATE_F_HOST_INVALID",
        )
        telemetry = _object(legacy.get("telemetry"), "GATE_F_HOST_INVALID").get("freshness")
        credentials = _object(legacy.get("credentials"), "GATE_F_HOST_INVALID")
        firewall = _object(legacy.get("firewall"), "GATE_F_HOST_INVALID")
        journal = _object(legacy.get("journal"), "GATE_F_HOST_INVALID")
        runtime = _object(legacy.get("container_runtime"), "GATE_F_HOST_INVALID")
        time = _object(legacy.get("time"), "GATE_F_HOST_INVALID")
        paths = _array(legacy.get("paths"), "GATE_F_HOST_INVALID")
        listeners = _array(legacy.get("listeners"), "GATE_F_HOST_INVALID")
        packages = _object(legacy.get("host_packages"), "GATE_F_HOST_INVALID")
        private_subnets = _object(legacy.get("private_subnets"), "GATE_F_HOST_INVALID")
        declared_subnets = _object(private_subnets.get("declared"), "GATE_F_HOST_INVALID")
        if target != {
            "active_state": "active",
            "load_state": "loaded",
            "sub_state": "active",
            "unit_file_state": "enabled",
            "unit_name": "asklegal.target",
        }:
            return False
        service_rows = [_object(item, "GATE_F_HOST_INVALID") for item in services]
        if any(
            row.get("active_state") != "active"
            or row.get("load_state") != "loaded"
            or row.get("sub_state") not in {"exited", "running"}
            or row.get("unit_file_state") not in {"enabled", "static"}
            for row in service_rows
        ):
            return False
        timer_rows = [_object(item, "GATE_F_HOST_INVALID") for item in timers]
        if len(timer_rows) != _TIMER_COUNT or any(
            row.get("active_state") != "active"
            or row.get("load_state") != "loaded"
            or row.get("sub_state") not in {"running", "waiting"}
            or row.get("unit_file_state") != "enabled"
            for row in timer_rows
        ):
            return False
        container_rows = [_object(item, "GATE_F_HOST_INVALID") for item in containers]
        if tuple(str(row.get("name")) for row in container_rows) != _EXPECTED_CONTAINERS or any(
            row.get("runtime_state") != "running" or row.get("health") not in {"HEALTHY", "NONE"}
            for row in container_rows
        ):
            return False
        application_rows = [_object(item, "GATE_F_HOST_INVALID") for item in applications]
        if len(application_rows) != _APPLICATION_COUNT or any(
            row.get("active_state") != "active" or row.get("health") != "HEALTHY"
            for row in application_rows
        ):
            return False
        scheduler_rows = [_object(item, "GATE_F_HOST_INVALID") for item in schedulers]
        if len(scheduler_rows) != _SCHEDULER_COUNT or any(
            row.get("present") is not True for row in scheduler_rows
        ):
            return False
        if not _resource_and_freshness_is_healthy(resources, capacity, backups, telemetry):
            return False
        path_rows = [_object(item, "GATE_F_HOST_INVALID") for item in paths]
        listener_rows = [_object(item, "GATE_F_HOST_INVALID") for item in listeners]
        return (
            credentials.get("systemd_creds_available") is True
            and credentials.get("encrypted_blob_mode") == "0400"
            and credentials.get("protection_mode") in {"HOST_KEY_ONLY", "TPM2_PLUS_HOST_KEY"}
            and credentials.get("persistent_plaintext_credential_paths") == []
            and firewall.get("nftables_available") is True
            and firewall.get("input_default") == "DROP"
            and firewall.get("forward_default") == "DROP"
            and firewall.get("direct_container_egress_default") == "DROP"
            and firewall.get("public_tcp_ports") == []
            and journal == {"forward_secure_sealing": True, "storage": "PERSISTENT"}
            and runtime.get("name") == "docker"
            and runtime.get("service_manager") == "systemd"
            and time.get("synchronized") is True
            and all(
                row.get("symlink") is False and row.get("writable") is True for row in path_rows
            )
            and all(row.get("public") is False for row in listener_rows)
            and all(value != "NOT_INSTALLED" for value in packages.values())
            and len(declared_subnets) == _PRIVATE_SUBNET_COUNT
        )
    except OperationalEvidenceError, KeyError, TypeError, ValueError:
        return False


def _operational_status(raw: bytes) -> None:
    code = "GATE_F_OBSERVABILITY_INVALID"
    try:
        snapshot = parse_operational_status(_document(raw, code))
    except (ObservabilityError, OperationalEvidenceError, TypeError, ValueError) as error:
        raise OperationalEvidenceError(code) from error
    if (
        snapshot.complete is not True
        or snapshot.healthy is not True
        or snapshot.alerts
        or tuple(status.category for status in snapshot.streams) != OPERATIONAL_CATEGORY_ORDER
    ):
        _fail(code)


def _host_apply_state(raw: bytes, expected_host_fingerprint: str) -> str:
    code = "GATE_F_SUPERVISION_INVALID"
    document = _document(raw, code)
    required = {
        "application_build_results_fingerprint",
        "application_build_results_path",
        "authority_fingerprint",
        "authority_id",
        "complete",
        "fingerprint",
        "index_deleted",
        "plan_fingerprint",
        "provider_called",
        "reboot_performed",
        "recollected_host_facts_fingerprint",
        "recollected_host_facts_path",
        "result",
        "rollback_complete",
        "rollback_receipts",
        "routing_mutated",
        "schema_id",
        "schema_version",
        "source_called",
        "step_receipts",
    }
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    steps = document.get("step_receipts")
    if (
        frozenset(document) != frozenset(required)
        or document.get("schema_id") != "asklegal.hk-v1-host-apply-state/v1"
        or document.get("schema_version") != "1.0.0"
        or document.get("result") != "COMPLETE"
        or document.get("complete") is not True
        or document.get("rollback_complete") is not False
        or document.get("rollback_receipts") != []
        or any(
            document.get(field) is not False
            for field in (
                "index_deleted",
                "provider_called",
                "reboot_performed",
                "routing_mutated",
                "source_called",
            )
        )
        or _FP.fullmatch(str(document.get("plan_fingerprint"))) is None
        or _FP.fullmatch(str(document.get("authority_fingerprint"))) is None
        or re.fullmatch(r"auth_[0-9a-f]{48}", str(document.get("authority_id"))) is None
        or _FP.fullmatch(str(document.get("application_build_results_fingerprint"))) is None
        or document.get("application_build_results_path") is not None
        or document.get("recollected_host_facts_fingerprint") != expected_host_fingerprint
        or type(document.get("recollected_host_facts_path")) is not str
        or not str(document["recollected_host_facts_path"]).startswith("/")
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
        or not isinstance(steps, list)
        or len(steps) != len(_HOST_APPLY_ACTIONS)
    ):
        _fail(code)
    for sequence, (raw_receipt, expected_action) in enumerate(
        zip(steps, _HOST_APPLY_ACTIONS, strict=True), start=1
    ):
        receipt = _object(raw_receipt, code)
        if frozenset(receipt) != frozenset(
            {
                "action",
                "argv_fingerprint",
                "readback",
                "returncode",
                "sequence",
                "stderr_fingerprint",
                "stdout_fingerprint",
            }
        ):
            _fail(code)
        action = receipt.get("action")
        readback = _object(receipt.get("readback"), code)
        if (
            receipt.get("sequence") != sequence
            or receipt.get("returncode") != 0
            or type(action) is not str
            or not action.startswith(f"{sequence:03d}|{expected_action}|")
            or any(
                _FP.fullmatch(str(receipt.get(field))) is None
                for field in ("argv_fingerprint", "stderr_fingerprint", "stdout_fingerprint")
            )
            or (sequence < len(_HOST_APPLY_ACTIONS) and readback != {"action_complete": True})
            or (
                sequence == len(_HOST_APPLY_ACTIONS)
                and readback != {"host_facts_fingerprint": expected_host_fingerprint}
            )
        ):
            _fail(code)
    return str(document["plan_fingerprint"])


def _rotation_report_row(raw: object, code: str) -> tuple[str, str, str, tuple[str, ...]]:
    row = _object(raw, code)
    if frozenset(row) != frozenset({"content_hex", "credential_name", "fingerprint"}):
        _fail(code)
    encoded = row.get("content_hex")
    if type(encoded) is not str:
        _fail(code)
    try:
        content = bytes.fromhex(encoded)
        report = parse_credential_rotation_report_bytes(content)
    except (TypeError, ValueError) as error:
        raise OperationalEvidenceError(code) from error
    if (
        row.get("credential_name") != report.credential_name
        or row.get("fingerprint") != _fingerprint(content)
        or report.state is not CredentialRotationState.SUCCEEDED
        or report.complete is not True
    ):
        _fail(code)
    return (
        report.credential_name,
        report.manifest_fingerprint,
        report.rotation_id,
        report.dependent_units,
    )


def _supervision(raw: bytes, host_raw: bytes) -> None:
    code = "GATE_F_SUPERVISION_INVALID"
    fields = {
        "credential_manifest_hex",
        "credential_manifest_fingerprint",
        "credential_rotation_reports",
        "host_apply_state_fingerprint",
        "host_apply_state_hex",
        "host_facts_fingerprint",
        "host_facts_hex",
    }
    document = _sealed(raw, _SUPERVISION_SCHEMA, fields, code)
    manifest_bytes = _hex_artifact(
        document,
        "credential_manifest_hex",
        "credential_manifest_fingerprint",
        code,
    )
    try:
        manifest = parse_credential_manifest_bytes(manifest_bytes)
    except (TypeError, ValueError) as error:
        raise OperationalEvidenceError(code) from error
    host_bytes = _hex_artifact(document, "host_facts_hex", "host_facts_fingerprint", code)
    state_bytes = _hex_artifact(
        document, "host_apply_state_hex", "host_apply_state_fingerprint", code
    )
    if host_bytes != host_raw:
        _fail(code)
    _boot, semantic_fingerprint, legacy = _host_details(host_bytes)
    if not _host_is_operational(legacy):
        _fail(code)
    _host_apply_state(state_bytes, semantic_fingerprint)
    reports = document.get("credential_rotation_reports")
    if not isinstance(reports, list):
        _fail(code)
    rows = tuple(_rotation_report_row(row, code) for row in reports)
    names = tuple(row[0] for row in rows)
    manifests = {row[1] for row in rows}
    rotations = {row[2] for row in rows}
    manifest_names = tuple(entry.credential_name for entry in manifest.entries)
    manifest_units = {entry.credential_name: entry.dependent_units for entry in manifest.entries}
    if (
        manifest_names != required_credential_names()
        or names != manifest_names
        or len(manifests) != 1
        or manifest.manifest_fingerprint not in manifests
        or any(row[3] != manifest_units[name] for row, name in zip(rows, names, strict=True))
        or len(rotations) != len(rows)
    ):
        _fail(code)


def build_host_supervision_readback(
    *,
    host_apply_state: bytes,
    host_facts: bytes,
    credential_manifest: bytes,
    credential_rotation_reports: tuple[bytes, ...],
) -> bytes:
    """Bind successful deployment, exact healthy host facts, and every credential rotation."""
    code = "GATE_F_SUPERVISION_INVALID"
    _boot, semantic_fingerprint, legacy = _host_details(host_facts)
    if not _host_is_operational(legacy):
        _fail(code)
    _host_apply_state(host_apply_state, semantic_fingerprint)
    try:
        manifest = parse_credential_manifest_bytes(credential_manifest)
        reports = tuple(
            parse_credential_rotation_report_bytes(raw) for raw in credential_rotation_reports
        )
    except (TypeError, ValueError) as error:
        raise OperationalEvidenceError(code) from error
    if (
        tuple(entry.credential_name for entry in manifest.entries) != required_credential_names()
        or tuple(report.credential_name for report in reports) != required_credential_names()
        or any(
            report.dependent_units != entry.dependent_units
            for report, entry in zip(reports, manifest.entries, strict=True)
        )
    ):
        _fail(code)
    manifest_fingerprints = {report.manifest_fingerprint for report in reports}
    if manifest_fingerprints != {manifest.manifest_fingerprint}:
        _fail(code)
    body: dict[str, JsonValue] = {
        "schema_id": _SUPERVISION_SCHEMA,
        "schema_version": _VERSION,
        "credential_manifest_fingerprint": _fingerprint(credential_manifest),
        "credential_manifest_hex": credential_manifest.hex(),
        "credential_rotation_reports": [
            {
                "content_hex": raw.hex(),
                "credential_name": report.credential_name,
                "fingerprint": _fingerprint(raw),
            }
            for raw, report in zip(credential_rotation_reports, reports, strict=True)
        ],
        "host_apply_state_fingerprint": _fingerprint(host_apply_state),
        "host_apply_state_hex": host_apply_state.hex(),
        "host_facts_fingerprint": _fingerprint(host_facts),
        "host_facts_hex": host_facts.hex(),
    }
    body["fingerprint"] = _fingerprint(canonicalize(checked_json_value(body)))
    content = canonicalize(checked_json_value(body))
    _supervision(content, host_facts)
    return content


def _recovery(raw: bytes) -> None:
    code = "GATE_F_RECOVERY_INVALID"
    document = _document(raw, code, newline=True)
    if frozenset(document) != frozenset(
        {
            "fingerprint",
            "live_recovery_proved",
            "operation_id",
            "plan_fingerprint",
            "receipts",
            "schema",
        }
    ):
        _fail(code)
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    receipts = document.get("receipts")
    plan_fingerprint = document.get("plan_fingerprint")
    if (
        document.get("schema") != "asklegal.hk-v1-live-recovery-execution-result/v1"
        or document.get("live_recovery_proved") is not True
        or _RECOVERY_ID.fullmatch(str(document.get("operation_id"))) is None
        or _FP.fullmatch(str(plan_fingerprint)) is None
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
        or not isinstance(receipts, list)
        or len(receipts) != len(_LIVE_RECOVERY_STEPS)
    ):
        _fail(code)
    target_identities: set[str] = set()
    for expected_step, raw_receipt in zip(_LIVE_RECOVERY_STEPS, receipts, strict=True):
        receipt = _object(raw_receipt, code)
        if frozenset(receipt) != frozenset(
            {
                "effect_fingerprint",
                "plan_fingerprint",
                "readback_fingerprint",
                "step",
                "target_identity",
            }
        ):
            _fail(code)
        target = str(receipt.get("target_identity"))
        effect = receipt.get("effect_fingerprint")
        if (
            receipt.get("step") != expected_step
            or receipt.get("plan_fingerprint") != plan_fingerprint
            or _RECOVERY_ID.fullmatch(target) is None
            or target in target_identities
            or _FP.fullmatch(str(effect)) is None
            or receipt.get("readback_fingerprint") != effect
        ):
            _fail(code)
        target_identities.add(target)


def _restart(raw: bytes, host_raw: bytes) -> HostRebootReadback:
    code = "GATE_F_RESTART_INVALID"
    try:
        return parse_host_reboot_readback_details(raw, host_raw)
    except (HostRebootError, TypeError, ValueError) as error:
        raise OperationalEvidenceError(code) from error


def _serving_state_binding(raw: bytes) -> tuple[str, str]:
    """Derive the active state identity from the Promotion-owned retained CAS file."""
    code = "GATE_F_SERVING_STATE_INVALID"
    document = _document(raw, code)
    if (
        frozenset(document) != frozenset({"activation", "active_state_id", "rollback", "schema_id"})
        or document.get("schema_id") != _SERVING_STATE_SCHEMA
    ):
        _fail(code)
    active_state_id = document.get("active_state_id")
    activation = _object(document.get("activation"), code)
    if frozenset(activation) != frozenset({"candidate", "receipt_id"}):
        _fail(code)
    candidate = _object(activation.get("candidate"), code)
    candidate_fields = {
        "approval_id",
        "candidate_serving_state_id",
        "candidate_serving_state_fingerprint",
        "coverage_fingerprint",
        "desired_inventory_fingerprint",
        "embedding_profile_fingerprint",
        "embedding_profile_id",
        "execution_lineage_id",
        "predecessor_state_id",
        "target_name",
    }
    fingerprint_fields = (
        "candidate_serving_state_fingerprint",
        "coverage_fingerprint",
        "desired_inventory_fingerprint",
        "embedding_profile_fingerprint",
    )
    if (
        frozenset(candidate) != frozenset(candidate_fields)
        or _STATE.fullmatch(str(active_state_id)) is None
        or candidate.get("candidate_serving_state_id") != active_state_id
        or _STATE.fullmatch(str(candidate.get("predecessor_state_id"))) is None
        or candidate.get("predecessor_state_id") == active_state_id
        or re.fullmatch(r"ssr_[0-9a-f]{48}", str(activation.get("receipt_id"))) is None
        or any(_FP.fullmatch(str(candidate.get(field))) is None for field in fingerprint_fields)
        or any(
            type(candidate.get(field)) is not str or not candidate.get(field)
            for field in (
                "approval_id",
                "embedding_profile_id",
                "execution_lineage_id",
                "target_name",
            )
        )
    ):
        _fail(code)
    rollback = document.get("rollback")
    if rollback is not None:
        rollback_entry = _object(rollback, code)
        if (
            frozenset(rollback_entry) != frozenset({"candidate", "receipt_id"})
            or rollback_entry.get("candidate") != candidate
            or re.fullmatch(r"ssr_[0-9a-f]{48}", str(rollback_entry.get("receipt_id"))) is None
        ):
            _fail(code)
    return str(active_state_id), str(candidate["candidate_serving_state_fingerprint"])


def _artifact(kind: str, owner: str, content: bytes) -> dict[str, JsonValue]:
    return {
        "content_hex": content.hex(),
        "fingerprint": _fingerprint(content),
        "kind": kind,
        "owner": owner,
    }


def _artifact_bytes(value: object, kind: str, owner: str, code: str) -> bytes:
    document = _object(value, code)
    if frozenset(document) != frozenset({"content_hex", "fingerprint", "kind", "owner"}):
        _fail(code)
    encoded = document.get("content_hex")
    if type(encoded) is not str or document.get("kind") != kind or document.get("owner") != owner:
        _fail(code)
    try:
        content = bytes.fromhex(encoded)
    except ValueError as error:
        raise OperationalEvidenceError(code) from error
    if not content or document.get("fingerprint") != _fingerprint(content):
        _fail(code)
    return content


def _f_source_map(value: GateFEvidenceSources) -> dict[str, bytes]:
    if type(value) is not GateFEvidenceSources:
        _fail("GATE_F_INPUT_INVALID")
    return {
        "HOST": value.host_facts,
        "OBSERVABILITY": value.operational_status,
        "RECOVERY": value.recovery,
        "RESTART": value.restart,
        "SCHEDULE": value.schedule_state,
        "SUPERVISION": value.supervision,
    }


def _validate_f_sources(
    value: GateFEvidenceSources,
) -> tuple[dict[str, bytes], str, HostRebootReadback]:
    sources = _f_source_map(value)
    _schedule(sources["SCHEDULE"])
    host_boot = _host(sources["HOST"])
    _operational_status(sources["OBSERVABILITY"])
    _supervision(sources["SUPERVISION"], sources["HOST"])
    _recovery(sources["RECOVERY"])
    restart = _restart(sources["RESTART"], sources["HOST"])
    _serving_state_binding(value.serving_state)
    if restart.post_boot_id_fingerprint != host_boot:
        _fail("GATE_F_RESTART_INVALID")
    return sources, host_boot, restart


def build_gate_f_operational_evidence(value: GateFEvidenceSources) -> bytes:
    """Build Gate F only after parsing all six capability-owning artifacts."""
    sources, boot_id_fingerprint, _restart_readback = _validate_f_sources(value)
    serving_state_id, serving_state_fingerprint = _serving_state_binding(value.serving_state)
    body: dict[str, JsonValue] = {
        "schema_id": _F_SCHEMA,
        "schema_version": _VERSION,
        "result": "COMPLETE",
        "serving_state_id": serving_state_id,
        "serving_state_fingerprint": serving_state_fingerprint,
        "serving_state_hex": value.serving_state.hex(),
        "serving_state_content_fingerprint": _fingerprint(value.serving_state),
        "boot_id_fingerprint": boot_id_fingerprint,
        "artifacts": [_artifact(kind, _F_OWNERS[kind], sources[kind]) for kind in _F_KINDS],
    }
    body["fingerprint"] = _fingerprint(canonicalize(checked_json_value(body)))
    return canonicalize(checked_json_value(body))


def parse_gate_f_operational_evidence(content: bytes) -> GateFOperationalEvidence:
    """Reparse the composite and every embedded owner artifact independently."""
    code = "GATE_F_COMPOSITE_INVALID"
    document = _document(content, code)
    if frozenset(document) != frozenset(
        {
            "schema_id",
            "schema_version",
            "result",
            "serving_state_id",
            "serving_state_fingerprint",
            "serving_state_hex",
            "serving_state_content_fingerprint",
            "boot_id_fingerprint",
            "artifacts",
            "fingerprint",
        }
    ):
        _fail(code)
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    artifacts = document.get("artifacts")
    if (
        document.get("schema_id") != _F_SCHEMA
        or document.get("schema_version") != _VERSION
        or document.get("result") != "COMPLETE"
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
        or not isinstance(artifacts, list)
        or len(artifacts) != len(_F_KINDS)
    ):
        _fail(code)
    source_map = {
        kind: _artifact_bytes(raw, kind, _F_OWNERS[kind], code)
        for kind, raw in zip(_F_KINDS, artifacts, strict=True)
    }
    serving_state = _hex_artifact(
        document,
        "serving_state_hex",
        "serving_state_content_fingerprint",
        code,
    )
    value = GateFEvidenceSources(
        source_map["SCHEDULE"],
        source_map["HOST"],
        source_map["OBSERVABILITY"],
        source_map["SUPERVISION"],
        source_map["RECOVERY"],
        source_map["RESTART"],
        serving_state,
    )
    _sources, boot_id_fingerprint, restart = _validate_f_sources(value)
    serving_state_id, serving_state_fingerprint = _serving_state_binding(serving_state)
    if document.get("boot_id_fingerprint") != boot_id_fingerprint:
        _fail("GATE_F_RESTART_INVALID")
    if (
        document.get("serving_state_id") != serving_state_id
        or document.get("serving_state_fingerprint") != serving_state_fingerprint
    ):
        _fail("GATE_F_SERVING_STATE_INVALID")
    return GateFOperationalEvidence(
        "COMPLETE",
        serving_state_id,
        serving_state_fingerprint,
        boot_id_fingerprint,
        restart.operation_id,
        restart.pre_boot_id_fingerprint,
        _F_KINDS,
        str(supplied),
    )


def _cycle(raw: bytes, expected_kind: str, expected_result: str) -> dict[str, JsonValue]:
    code = "GATE_G_CYCLE_INVALID"
    document = _document(raw, code)
    expected = {
        "schema_id",
        "schema_version",
        "kind",
        "operation_id",
        "command_fingerprint",
        "observation_cutoff",
        "families",
        "scope_ids",
        "result",
        "blocker_codes",
        "proposal_reference",
    }
    proposal = document.get("proposal_reference")
    if frozenset(document) != frozenset(expected) or (
        document.get("schema_id") != "asklegal.hk-v1.acceptance-cycle-result"
        or document.get("schema_version") != _VERSION
        or document.get("kind") != expected_kind
        or document.get("result") != expected_result
        or document.get("blocker_codes") != []
        or document.get("families") != ["CASES", "LEGISLATION"]
        or not isinstance(document.get("scope_ids"), list)
        or _FP.fullmatch(str(document.get("command_fingerprint"))) is None
    ):
        _fail(code)
    try:
        datetime.fromisoformat(str(document.get("observation_cutoff")))
    except ValueError as error:
        raise OperationalEvidenceError(code) from error
    if expected_result == "PROPOSAL_READY":
        reference = _object(proposal, code)
        byte_length = reference.get("byte_length")
        if frozenset(reference) != frozenset(
            {"vault", "logical_key", "version_id", "fingerprint", "byte_length"}
        ) or (
            reference.get("vault") != "PRIMARY"
            or _FP.fullmatch(str(reference.get("fingerprint"))) is None
            or type(byte_length) is not int
            or byte_length < 1
        ):
            _fail(code)
    elif proposal is not None:
        _fail(code)
    return document


def _promotion(raw: bytes, operation: str) -> dict[str, JsonValue]:
    code = "GATE_G_PROMOTION_INVALID"
    fields = {
        "operation",
        "proposal_fingerprint",
        "approval_fingerprint",
        "predecessor_serving_state_id",
        "predecessor_serving_state_fingerprint",
        "predecessor_target_name",
        "predecessor_target_fingerprint",
        "serving_state_id",
        "serving_state_fingerprint",
        "target_name",
        "target_fingerprint",
        "backup_fingerprint",
        "readback_fingerprint",
        "result",
    }
    document = _sealed(raw, "asklegal.hk-v1-promotion-readback/v1", fields, code)
    predecessor_values = (
        document.get("predecessor_serving_state_fingerprint"),
        document.get("predecessor_target_name"),
        document.get("predecessor_target_fingerprint"),
    )
    if (
        document.get("operation") != operation
        or document.get("result") != "COMPLETE"
        or _STATE.fullmatch(str(document.get("predecessor_serving_state_id"))) is None
        or _STATE.fullmatch(str(document.get("serving_state_id"))) is None
        or type(document.get("target_name")) is not str
        or not document.get("target_name")
        or any(
            _FP.fullmatch(str(document.get(field))) is None
            for field in (
                "proposal_fingerprint",
                "approval_fingerprint",
                "serving_state_fingerprint",
                "target_fingerprint",
                "backup_fingerprint",
                "readback_fingerprint",
            )
        )
    ):
        _fail(code)
    if operation == "PROMOTION":
        if predecessor_values != (None, None, None):
            _fail(code)
    elif (
        any(type(item) is not str or not item for item in predecessor_values)
        or document.get("predecessor_serving_state_id") == document.get("serving_state_id")
        or document.get("predecessor_target_name") == document.get("target_name")
        or document.get("predecessor_target_fingerprint") == document.get("target_fingerprint")
    ):
        _fail(code)
    return document


def _proposal_fingerprint(cycle: dict[str, JsonValue]) -> str:
    return str(
        _object(cycle.get("proposal_reference"), "GATE_G_LINEAGE_INVALID").get("fingerprint")
    )


def _scheduled_cycle_parts(
    schedule_state: bytes,
    host_facts: bytes,
    root_operation_id: str,
    scheduler_output: bytes,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    tuple[str, ...],
    dict[str, JsonValue],
]:
    code = "GATE_G_SCHEDULED_CYCLE_INVALID"
    try:
        commands, active_ids = parse_live_schedule_state_bytes(schedule_state)
        boot_id_fingerprint = _host(host_facts)
        output = _document(scheduler_output, code)
    except (LiveScheduleError, OperationalEvidenceError, TypeError, ValueError) as error:
        raise OperationalEvidenceError(code) from error
    matching = tuple(
        command for command in commands if command.root_operation_id == root_operation_id
    )
    if len(matching) != 1:
        _fail(code)
    command = matching[0]
    instruction = command.root_instruction
    if (
        command.state is not ScheduleState.STARTED
        or command.request.kind.value not in {"OBSERVATION", "RECONCILIATION"}
        or command.request.command_id in active_ids
        or instruction is None
        or output.get("cycle_id") != instruction.cycle_id
        or "acceptance" not in output
    ):
        _fail(code)
    acceptance_raw = output.get("acceptance")
    due_output = dict(output)
    del due_output["acceptance"]
    instruction_payload = {
        "cycle_id": instruction.cycle_id,
        "cycle_kind": instruction.cycle_kind.value,
        "scheduled_at": instruction.scheduled_at,
        "observation_cutoff": instruction.observation_cutoff,
        "matrix_revision": instruction.matrix_revision,
        "matrix_fingerprint": instruction.matrix_fingerprint,
    }
    try:
        _instruction, due = rebuild_hk_v1_due_handoff(instruction_payload, due_output)
        acceptance = validate_hk_v1_acceptance_cycle_result(acceptance_raw)
    except Exception as error:
        raise OperationalEvidenceError(code) from error
    if (
        due.get("accounting_complete") is not True
        or due.get("release_blocking") is not False
        or due.get("disposition") != "COMPLETE"
        or acceptance.get("observation_cutoff") != instruction.observation_cutoff
    ):
        _fail(code)
    return (
        command.request.kind.value,
        command.attempt_operation_id,
        boot_id_fingerprint,
        instruction.cycle_id,
        instruction.scheduled_at,
        instruction.observation_cutoff,
        tuple(item.root_operation_id for item in commands),
        acceptance,
    )


def build_scheduled_cycle_readback(
    *,
    schedule_state: bytes,
    host_facts: bytes,
    root_operation_id: str,
    scheduler_output: bytes,
) -> bytes:
    """Freeze one independently replayable scheduled-cycle terminal readback."""
    (
        schedule_kind,
        attempt_operation_id,
        boot_id_fingerprint,
        _cycle_id,
        _scheduled_at,
        _observation_cutoff,
        _terminal_root_operation_ids,
        acceptance,
    ) = _scheduled_cycle_parts(schedule_state, host_facts, root_operation_id, scheduler_output)
    body: dict[str, JsonValue] = {
        "schema_id": _SCHEDULED_CYCLE_SCHEMA,
        "schema_version": _VERSION,
        "schedule_kind": schedule_kind,
        "root_operation_id": root_operation_id,
        "attempt_operation_id": attempt_operation_id,
        "boot_id_fingerprint": boot_id_fingerprint,
        "acceptance_result": acceptance,
        "schedule_state_hex": schedule_state.hex(),
        "schedule_state_fingerprint": _fingerprint(schedule_state),
        "host_facts_hex": host_facts.hex(),
        "host_facts_fingerprint": _fingerprint(host_facts),
        "scheduler_output_hex": scheduler_output.hex(),
        "scheduler_output_fingerprint": _fingerprint(scheduler_output),
    }
    body["fingerprint"] = _fingerprint(canonicalize(checked_json_value(body)))
    return canonicalize(checked_json_value(body))


def _hex_artifact(
    document: dict[str, JsonValue], field: str, fingerprint_field: str, code: str
) -> bytes:
    encoded = document.get(field)
    if type(encoded) is not str:
        _fail(code)
    try:
        raw = bytes.fromhex(encoded)
    except ValueError as error:
        raise OperationalEvidenceError(code) from error
    if not raw or document.get(fingerprint_field) != _fingerprint(raw):
        _fail(code)
    return raw


def parse_scheduled_cycle_readback(content: bytes) -> ScheduledCycleReadback:
    """Reparse a scheduled terminal and every embedded owning artifact."""
    code = "GATE_G_SCHEDULED_CYCLE_INVALID"
    fields = {
        "schedule_kind",
        "root_operation_id",
        "attempt_operation_id",
        "boot_id_fingerprint",
        "acceptance_result",
        "schedule_state_hex",
        "schedule_state_fingerprint",
        "host_facts_hex",
        "host_facts_fingerprint",
        "scheduler_output_hex",
        "scheduler_output_fingerprint",
    }
    document = _sealed(content, _SCHEDULED_CYCLE_SCHEMA, fields, code)
    schedule_state = _hex_artifact(
        document, "schedule_state_hex", "schedule_state_fingerprint", code
    )
    host_facts = _hex_artifact(document, "host_facts_hex", "host_facts_fingerprint", code)
    scheduler_output = _hex_artifact(
        document, "scheduler_output_hex", "scheduler_output_fingerprint", code
    )
    root_operation_id = document.get("root_operation_id")
    if type(root_operation_id) is not str or not root_operation_id:
        _fail(code)
    (
        schedule_kind,
        attempt_operation_id,
        boot_id_fingerprint,
        cycle_id,
        scheduled_at,
        observation_cutoff,
        terminal_root_operation_ids,
        acceptance,
    ) = _scheduled_cycle_parts(schedule_state, host_facts, root_operation_id, scheduler_output)
    if (
        document.get("schedule_kind") != schedule_kind
        or document.get("attempt_operation_id") != attempt_operation_id
        or document.get("boot_id_fingerprint") != boot_id_fingerprint
        or document.get("acceptance_result") != acceptance
    ):
        _fail(code)
    return ScheduledCycleReadback(
        schedule_kind,
        root_operation_id,
        attempt_operation_id,
        boot_id_fingerprint,
        cycle_id,
        scheduled_at,
        observation_cutoff,
        terminal_root_operation_ids,
        str(document["schedule_state_fingerprint"]),
        str(document["scheduler_output_fingerprint"]),
        acceptance,
        str(document["fingerprint"]),
    )


def _g_source_map(value: GateGEvidenceSources) -> dict[str, bytes]:
    if type(value) is not GateGEvidenceSources:
        _fail("GATE_G_INPUT_INVALID")
    return {
        "BASELINE_CYCLE": value.baseline_cycle,
        "BASELINE_PROMOTION": value.baseline_promotion,
        "CHANGED_CYCLE": value.changed_cycle,
        "CHANGED_PROMOTION": value.changed_promotion,
        "NO_CHANGE_CYCLE": value.no_change_cycle,
        "PRE_REBOOT": value.pre_reboot,
        "POST_REBOOT": value.post_reboot,
        "ROLLBACK": value.rollback,
        "RESTORATION": value.restoration,
        "POST_REBOOT_NO_CHANGE_CYCLE": value.post_reboot_no_change_cycle,
        "POST_REBOOT_CHANGED_CYCLE": value.post_reboot_changed_cycle,
        "NEXT_HEALTH": value.next_health,
    }


def _validate_g_sources(
    value: GateGEvidenceSources,
) -> tuple[str, str, str, str, str, str, str]:
    code = "GATE_G_LINEAGE_INVALID"
    baseline_cycle = _cycle(value.baseline_cycle, "BASELINE", "PROPOSAL_READY")
    baseline = _promotion(value.baseline_promotion, "PROMOTION")
    changed_cycle = _cycle(value.changed_cycle, "UPDATE", "PROPOSAL_READY")
    changed = _promotion(value.changed_promotion, "PROMOTION")
    no_change = _cycle(value.no_change_cycle, "UPDATE", "NO_CHANGE")
    pre = parse_gate_f_operational_evidence(value.pre_reboot)
    post = parse_gate_f_operational_evidence(value.post_reboot)
    rollback = _promotion(value.rollback, "ROLLBACK")
    restoration = _promotion(value.restoration, "RESTORATION")
    post_no_change = parse_scheduled_cycle_readback(value.post_reboot_no_change_cycle)
    post_changed = parse_scheduled_cycle_readback(value.post_reboot_changed_cycle)
    health = parse_gate_f_operational_evidence(value.next_health)
    cutoffs = tuple(
        datetime.fromisoformat(str(cycle["observation_cutoff"]))
        for cycle in (baseline_cycle, changed_cycle, no_change)
    )
    baseline_state = str(baseline["serving_state_id"])
    current_state = str(changed["serving_state_id"])
    post_no_change_acceptance = post_no_change.acceptance
    post_changed_acceptance = post_changed.acceptance
    try:
        post_no_change_scheduled_at = datetime.fromisoformat(post_no_change.scheduled_at)
        post_changed_scheduled_at = datetime.fromisoformat(post_changed.scheduled_at)
    except ValueError as error:
        raise OperationalEvidenceError(code) from error
    if (
        not cutoffs[0] < cutoffs[1] < cutoffs[2]
        or baseline_state == current_state
        or baseline["serving_state_fingerprint"] == changed["serving_state_fingerprint"]
        or baseline["target_name"] == changed["target_name"]
        or baseline["target_fingerprint"] == changed["target_fingerprint"]
        or baseline["proposal_fingerprint"] == changed["proposal_fingerprint"]
        or baseline["approval_fingerprint"] == changed["approval_fingerprint"]
        or baseline["readback_fingerprint"] == changed["readback_fingerprint"]
        or baseline["fingerprint"] == changed["fingerprint"]
        or baseline["proposal_fingerprint"] != _proposal_fingerprint(baseline_cycle)
        or changed["proposal_fingerprint"] != _proposal_fingerprint(changed_cycle)
        or changed["predecessor_serving_state_id"] != baseline_state
        or pre.serving_state_id != current_state
        or post.serving_state_id != current_state
        or health.serving_state_id != current_state
        or pre.serving_state_fingerprint != changed["serving_state_fingerprint"]
        or post.serving_state_fingerprint != changed["serving_state_fingerprint"]
        or health.serving_state_fingerprint != changed["serving_state_fingerprint"]
        or pre.boot_id_fingerprint == post.boot_id_fingerprint
        or post.restart_pre_boot_id_fingerprint != pre.boot_id_fingerprint
        or post.restart_operation_id == pre.restart_operation_id
        or health.restart_operation_id != post.restart_operation_id
        or health.restart_pre_boot_id_fingerprint != pre.boot_id_fingerprint
        or post.boot_id_fingerprint != health.boot_id_fingerprint
        or post_no_change.boot_id_fingerprint != post.boot_id_fingerprint
        or post_changed.boot_id_fingerprint != post.boot_id_fingerprint
        or post_no_change.schedule_kind != "OBSERVATION"
        or post_changed.schedule_kind not in {"OBSERVATION", "RECONCILIATION"}
        or post_no_change.root_operation_id == post_changed.root_operation_id
        or post_no_change.attempt_operation_id == post_changed.attempt_operation_id
        or post_no_change.cycle_id == post_changed.cycle_id
        or post_no_change.schedule_state_fingerprint == post_changed.schedule_state_fingerprint
        or post_no_change.scheduler_output_fingerprint == post_changed.scheduler_output_fingerprint
        or post_no_change.root_operation_id not in post_changed.terminal_root_operation_ids
        or post_changed.root_operation_id in post_no_change.terminal_root_operation_ids
        or not set(post_no_change.terminal_root_operation_ids).issubset(
            post_changed.terminal_root_operation_ids
        )
        or post_no_change_scheduled_at.tzinfo is None
        or post_changed_scheduled_at.tzinfo is None
        or not post_no_change_scheduled_at < post_changed_scheduled_at
        or post_no_change_acceptance.get("result") != "NO_CHANGE"
        or post_no_change_acceptance.get("proposal_reference") is not None
        or post_changed_acceptance.get("result") != "PROPOSAL_READY"
        or _proposal_fingerprint(post_changed_acceptance)
        in {
            str(baseline["proposal_fingerprint"]),
            str(changed["proposal_fingerprint"]),
        }
        or not cutoffs[2]
        < datetime.fromisoformat(str(post_no_change_acceptance["observation_cutoff"]))
        < datetime.fromisoformat(str(post_changed_acceptance["observation_cutoff"]))
        or rollback["predecessor_serving_state_id"] != current_state
        or rollback["predecessor_serving_state_fingerprint"] != changed["serving_state_fingerprint"]
        or rollback["predecessor_target_name"] != changed["target_name"]
        or rollback["predecessor_target_fingerprint"] != changed["target_fingerprint"]
        or rollback["proposal_fingerprint"] != changed["proposal_fingerprint"]
        or rollback["approval_fingerprint"] != changed["approval_fingerprint"]
        or rollback["serving_state_id"] != baseline_state
        or rollback["serving_state_fingerprint"] != baseline["serving_state_fingerprint"]
        or rollback["target_name"] != baseline["target_name"]
        or rollback["target_fingerprint"] != baseline["target_fingerprint"]
        or rollback["backup_fingerprint"] != baseline["backup_fingerprint"]
        or rollback["readback_fingerprint"] != baseline["readback_fingerprint"]
        or restoration["predecessor_serving_state_id"] != baseline_state
        or restoration["predecessor_serving_state_fingerprint"]
        != baseline["serving_state_fingerprint"]
        or restoration["predecessor_target_name"] != baseline["target_name"]
        or restoration["predecessor_target_fingerprint"] != baseline["target_fingerprint"]
        or restoration["proposal_fingerprint"] != changed["proposal_fingerprint"]
        or restoration["approval_fingerprint"] != changed["approval_fingerprint"]
        or restoration["serving_state_id"] != current_state
        or restoration["serving_state_fingerprint"] != changed["serving_state_fingerprint"]
        or restoration["target_name"] != changed["target_name"]
        or restoration["target_fingerprint"] != changed["target_fingerprint"]
        or restoration["backup_fingerprint"] != changed["backup_fingerprint"]
        or restoration["readback_fingerprint"] != changed["readback_fingerprint"]
    ):
        _fail(code)
    return (
        baseline_state,
        current_state,
        str(changed["proposal_fingerprint"]),
        str(changed["approval_fingerprint"]),
        str(changed["target_name"]),
        str(changed["target_fingerprint"]),
        str(changed["serving_state_fingerprint"]),
    )


def build_gate_g_live_lineage(value: GateGEvidenceSources) -> bytes:
    """Build Gate G only after replaying the complete ordered owner lineage."""
    baseline_state, current_state, *_bindings = _validate_g_sources(value)
    sources = _g_source_map(value)
    body: dict[str, JsonValue] = {
        "schema_id": _G_SCHEMA,
        "schema_version": _VERSION,
        "result": "COMPLETE",
        "baseline_serving_state_id": baseline_state,
        "current_serving_state_id": current_state,
        "artifacts": [_artifact(kind, _G_OWNERS[kind], sources[kind]) for kind in _G_KINDS],
    }
    body["fingerprint"] = _fingerprint(canonicalize(checked_json_value(body)))
    return canonicalize(checked_json_value(body))


def parse_gate_g_live_lineage(content: bytes) -> GateGLiveLineage:
    """Reparse Gate G and every embedded Control/Promotion/F artifact."""
    code = "GATE_G_COMPOSITE_INVALID"
    document = _document(content, code)
    if frozenset(document) != frozenset(
        {
            "schema_id",
            "schema_version",
            "result",
            "baseline_serving_state_id",
            "current_serving_state_id",
            "artifacts",
            "fingerprint",
        }
    ):
        _fail(code)
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    artifacts = document.get("artifacts")
    if (
        document.get("schema_id") != _G_SCHEMA
        or document.get("schema_version") != _VERSION
        or document.get("result") != "COMPLETE"
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
        or not isinstance(artifacts, list)
        or len(artifacts) != len(_G_KINDS)
    ):
        _fail(code)
    values = {
        kind: _artifact_bytes(raw, kind, _G_OWNERS[kind], code)
        for kind, raw in zip(_G_KINDS, artifacts, strict=True)
    }
    source = GateGEvidenceSources(*(values[kind] for kind in _G_KINDS))
    baseline, current, proposal, approval, target, target_fingerprint, state_fingerprint = (
        _validate_g_sources(source)
    )
    if (
        document.get("baseline_serving_state_id") != baseline
        or document.get("current_serving_state_id") != current
    ):
        _fail("GATE_G_LINEAGE_INVALID")
    return GateGLiveLineage(
        "COMPLETE",
        baseline,
        current,
        proposal,
        approval,
        target,
        target_fingerprint,
        state_fingerprint,
        _G_KINDS,
        str(supplied),
    )
