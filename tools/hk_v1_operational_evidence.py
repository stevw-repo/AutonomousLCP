"""Produce exact Gate F/G composites from capability-owner readbacks."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Never, Protocol, cast

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_control_plane.v1_schedule import (
    LiveScheduleError,
    ScheduleKind,
    StoredScheduleCommand,
    parse_live_schedule_state_bytes,
)
from asklegal_durable_task import OrchestrationStatus, V1SchedulerSettings

from tools.hk_v1_admission_operational_evidence import (
    GateFEvidenceSources,
    GateGEvidenceSources,
    OperationalEvidenceError,
    build_gate_f_operational_evidence,
    build_gate_g_live_lineage,
    build_host_supervision_readback,
    build_schedule_execution_readback,
    build_scheduled_cycle_readback,
)
from tools.hk_v1_rotate_credentials import parse_credential_rotation_report_bytes

_MAX_BYTES = 10_000_000
_OUTPUT_MODE = 0o600
_VERSION = "1.0.0"
_ORCHESTRATIONS = {
    "OBSERVATION": "run_hk_v1_due_cycle",
    "RECONCILIATION": "run_hk_v1_due_cycle",
    "AUDIT_ARCHIVE": "run_hk_v1_audit_archive",
    "RECOVERY_VERIFY": "run_hk_v1_recovery_verification",
    "TELEMETRY_RETENTION": "run_hk_v1_telemetry_retention",
}
_G_ARGUMENTS = (
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
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue


class OperationalEvidenceCliError(ValueError):
    """One safe input, scheduler-readback, or output-publication failure."""


class SchedulerReadClient(Protocol):
    """Read-only scheduler boundary used to export retained terminal outputs."""

    def get_orchestration_state(self, instance_id: str) -> object | None:
        """Return one orchestration state without changing it."""
        ...


def _fail(code: str) -> Never:
    raise OperationalEvidenceCliError(code)


def _safe_file(path: Path, code: str) -> Path:
    if (
        not path.is_absolute()
        or path == Path(path.anchor)
        or path != path.resolve(strict=False)
        or path.is_symlink()
        or not path.is_file()
    ):
        _fail(code)
    return path


def _safe_directory(path: Path, code: str) -> Path:
    if (
        not path.is_absolute()
        or path == Path(path.anchor)
        or path != path.resolve(strict=False)
        or path.is_symlink()
        or not path.is_dir()
    ):
        _fail(code)
    return path


def _read(path: Path, code: str) -> bytes:
    _safe_file(path, code)
    try:
        content = path.read_bytes()
    except OSError as error:
        raise OperationalEvidenceCliError(code) from error
    if not content or len(content) > _MAX_BYTES:
        _fail(code)
    return content


def _output_path(path: Path) -> Path:
    code = "OPERATIONAL_EVIDENCE_OUTPUT_INVALID"
    if not path.is_absolute() or path == Path(path.anchor) or path != path.resolve(strict=False):
        _fail(code)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink() or path.parent.resolve(strict=True) != path.parent:
            _fail(code)
    except OSError as error:
        raise OperationalEvidenceCliError(code) from error
    return path


def _write(path: Path, content: bytes) -> None:
    code = "OPERATIONAL_EVIDENCE_OUTPUT_INVALID"
    output = _output_path(path)
    try:
        with exclusive_local_state_lock(output):
            if output.exists():
                mode = stat.S_IMODE(output.stat(follow_symlinks=False).st_mode)
                if output.is_symlink() or not output.is_file() or mode != _OUTPUT_MODE:
                    _fail(code)
                if output.read_bytes() != content:
                    _fail("OPERATIONAL_EVIDENCE_OUTPUT_DRIFT")
                return
            temporary = output.with_name(f".{output.name}.{token_hex(16)}.tmp")
            try:
                descriptor = os.open(
                    temporary,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_CLOEXEC,
                    _OUTPUT_MODE,
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(output)
                directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                with suppress(FileNotFoundError):
                    temporary.unlink()
            if (
                output.read_bytes() != content
                or stat.S_IMODE(output.stat().st_mode) != _OUTPUT_MODE
            ):
                _fail(code)
    except OperationalEvidenceCliError:
        raise
    except OSError as error:
        raise OperationalEvidenceCliError(code) from error


def _json_output(serialized: object, code: str) -> tuple[bytes, dict[str, JsonValue]]:
    if type(serialized) is not str or not serialized:
        _fail(code)
    try:
        value = parse_json_bytes(serialized.encode("utf-8"), max_bytes=_MAX_BYTES)
    except (RuntimeError, ValueError) as error:
        raise OperationalEvidenceCliError(code) from error
    if not isinstance(value, dict):
        _fail(code)
    return canonicalize(value), value


def _terminal_output(client: SchedulerReadClient, command: StoredScheduleCommand) -> bytes:
    code = "SCHEDULE_EXECUTION_READBACK_NOT_READY"
    state = client.get_orchestration_state(command.attempt_operation_id)
    if (
        state is None
        or getattr(state, "instance_id", None) != command.attempt_operation_id
        or getattr(state, "name", None) != _ORCHESTRATIONS[command.request.kind.value]
        or getattr(state, "runtime_status", None) is not OrchestrationStatus.COMPLETED
    ):
        _fail(code)
    content, document = _json_output(getattr(state, "serialized_output", None), code)
    kind = command.request.kind
    if kind in {ScheduleKind.OBSERVATION, ScheduleKind.RECONCILIATION}:
        return content
    reference = document.get("result_reference")
    expected = f"maintenance-results/{kind.value.lower()}/{command.attempt_operation_id}.json"
    if reference != expected:
        _fail(code)
    return expected.encode("ascii")


def build_live_schedule_execution_readback(
    schedule_state: bytes,
    host_facts: bytes,
    state_root: Path,
    client: SchedulerReadClient,
) -> bytes:
    """Read all five terminal scheduler results and their retained owner artifacts."""
    code = "SCHEDULE_EXECUTION_READBACK_NOT_READY"
    root = _safe_directory(state_root, code)
    try:
        commands, active = parse_live_schedule_state_bytes(schedule_state)
    except (LiveScheduleError, TypeError, ValueError) as error:
        raise OperationalEvidenceCliError(code) from error
    if active or {command.request.kind.value for command in commands} != set(_ORCHESTRATIONS):
        _fail(code)
    executions: dict[str, bytes] = {}
    for command in commands:
        result = _terminal_output(client, command)
        if command.request.kind in {ScheduleKind.OBSERVATION, ScheduleKind.RECONCILIATION}:
            executions[command.request.kind.value] = build_scheduled_cycle_readback(
                schedule_state=schedule_state,
                host_facts=host_facts,
                root_operation_id=command.root_operation_id,
                scheduler_output=result,
            )
            continue
        reference = result.decode("ascii")
        path = root / reference
        if not path.is_relative_to(root):
            _fail(code)
        executions[command.request.kind.value] = _read(path, code)
    try:
        return build_schedule_execution_readback(schedule_state, executions)
    except (OperationalEvidenceError, TypeError, ValueError) as error:
        raise OperationalEvidenceCliError(code) from error


def _rotation_reports(paths: Sequence[Path]) -> tuple[bytes, ...]:
    code = "GATE_F_ROTATION_REPORT_INVALID"
    rows: list[tuple[str, bytes]] = []
    for path in paths:
        raw = _read(path, code)
        try:
            report = parse_credential_rotation_report_bytes(raw)
        except (TypeError, ValueError) as error:
            raise OperationalEvidenceCliError(code) from error
        rows.append((report.credential_name, raw))
    if len({name for name, _raw in rows}) != len(rows):
        _fail(code)
    return tuple(raw for _name, raw in sorted(rows))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    schedule = commands.add_parser("schedule-live")
    schedule.add_argument("--schedule-state", type=Path, required=True)
    schedule.add_argument("--host-facts", type=Path, required=True)
    schedule.add_argument("--control-state-root", type=Path, required=True)
    schedule.add_argument("--output", type=Path, required=True)

    scheduled = commands.add_parser("scheduled-cycle")
    scheduled.add_argument("--schedule-state", type=Path, required=True)
    scheduled.add_argument("--host-facts", type=Path, required=True)
    scheduled.add_argument("--root-operation-id", required=True)
    scheduled.add_argument("--scheduler-output", type=Path, required=True)
    scheduled.add_argument("--output", type=Path, required=True)

    gate_f = commands.add_parser("gate-f")
    gate_f.add_argument("--schedule-execution", type=Path, required=True)
    gate_f.add_argument("--host-facts", type=Path, required=True)
    gate_f.add_argument("--operational-status", type=Path, required=True)
    gate_f.add_argument("--host-apply-state", type=Path, required=True)
    gate_f.add_argument("--credential-manifest", type=Path, required=True)
    gate_f.add_argument(
        "--credential-rotation-report",
        type=Path,
        action="append",
        required=True,
    )
    gate_f.add_argument("--recovery", type=Path, required=True)
    gate_f.add_argument("--restart", type=Path, required=True)
    gate_f.add_argument("--serving-state", type=Path, required=True)
    gate_f.add_argument("--output", type=Path, required=True)

    gate_g = commands.add_parser("gate-g")
    for name in _G_ARGUMENTS:
        gate_g.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    gate_g.add_argument("--output", type=Path, required=True)
    return parser


def _gate_f(arguments: argparse.Namespace) -> bytes:
    host_facts = _read(arguments.host_facts, "GATE_F_HOST_INVALID")
    supervision = build_host_supervision_readback(
        host_apply_state=_read(arguments.host_apply_state, "GATE_F_SUPERVISION_INVALID"),
        host_facts=host_facts,
        credential_manifest=_read(
            arguments.credential_manifest,
            "GATE_F_SUPERVISION_INVALID",
        ),
        credential_rotation_reports=_rotation_reports(arguments.credential_rotation_report),
    )
    return build_gate_f_operational_evidence(
        GateFEvidenceSources(
            schedule_state=_read(arguments.schedule_execution, "GATE_F_SCHEDULE_INVALID"),
            host_facts=host_facts,
            operational_status=_read(
                arguments.operational_status,
                "GATE_F_OBSERVABILITY_INVALID",
            ),
            supervision=supervision,
            recovery=_read(arguments.recovery, "GATE_F_RECOVERY_INVALID"),
            restart=_read(arguments.restart, "GATE_F_RESTART_INVALID"),
            serving_state=_read(arguments.serving_state, "GATE_F_SERVING_STATE_INVALID"),
        )
    )


def _gate_g(arguments: argparse.Namespace) -> bytes:
    values = tuple(
        _read(cast("Path", getattr(arguments, name)), "GATE_G_INPUT_INVALID")
        for name in _G_ARGUMENTS
    )
    return build_gate_g_live_lineage(GateGEvidenceSources(*values))


def main(
    argv: list[str] | None = None,
    *,
    scheduler_client: SchedulerReadClient | None = None,
) -> int:
    """Build one requested artifact; only schedule-live performs read-only local RPC."""
    try:
        arguments = _parser().parse_args(argv)
        if arguments.command == "schedule-live":
            client = scheduler_client
            if client is None:
                client = cast(
                    "SchedulerReadClient",
                    V1SchedulerSettings.for_application("CONTROL_PLANE").create_client(
                        default_version=_VERSION
                    ),
                )
            content = build_live_schedule_execution_readback(
                _read(arguments.schedule_state, "GATE_F_SCHEDULE_INVALID"),
                _read(arguments.host_facts, "GATE_F_HOST_INVALID"),
                arguments.control_state_root,
                client,
            )
        elif arguments.command == "scheduled-cycle":
            content = build_scheduled_cycle_readback(
                schedule_state=_read(arguments.schedule_state, "GATE_G_SCHEDULED_CYCLE_INVALID"),
                host_facts=_read(arguments.host_facts, "GATE_G_SCHEDULED_CYCLE_INVALID"),
                root_operation_id=arguments.root_operation_id,
                scheduler_output=_read(
                    arguments.scheduler_output,
                    "GATE_G_SCHEDULED_CYCLE_INVALID",
                ),
            )
        elif arguments.command == "gate-f":
            content = _gate_f(arguments)
        else:
            content = _gate_g(arguments)
        _write(arguments.output, content)
    except (
        LiveScheduleError,
        OperationalEvidenceCliError,
        OperationalEvidenceError,
        OSError,
        TypeError,
        ValueError,
    ):
        sys.stderr.write("HK_V1_OPERATIONAL_EVIDENCE_NOT_READY\n")
        return 2
    sys.stdout.write("HK_V1_OPERATIONAL_EVIDENCE_COMPLETE\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
