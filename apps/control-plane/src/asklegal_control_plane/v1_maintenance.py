"""Truthful local-only maintenance adapters for the Hong Kong V1 prototype."""

from __future__ import annotations

import os
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path, PurePath
from secrets import token_hex
from typing import TYPE_CHECKING, Never, cast

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_reporting import (
    HongKongV1CoverageMatrix,
    is_hk_v1_coverage_matrix_policy_approved,
)

from asklegal_control_plane.v1_schedule import (
    LiveScheduleError,
    ScheduleKind,
    schedule_attempt_operation_id,
    schedule_request,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from asklegal_durable_task import ActivityContext

_DEFAULT_STATE_ROOT = "/var/lib/asklegal/control"
_MAX_INPUT_FILES = 512
_MAX_INPUT_BYTES = 64 * 1024 * 1024
_MAX_RECOVERY_PROOF_BYTES = 1_000_000
_RETENTION_DAYS = 30
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OPERATION_ID = re.compile(r"(?:att|op)_[0-9a-f]{64}\Z")
_TELEMETRY_NAME = re.compile(r"(?P<day>[0-9]{4}-[0-9]{2}-[0-9]{2})\.ndjson\Z")
_RECOVERY_FIELDS = {
    "blockers",
    "contract_proved",
    "gate_f_eligible",
    "result_code",
    "scheduler_result",
    "sql_result",
    "vault_result",
}
_LIVE_RECOVERY_FIELDS = {
    "fingerprint",
    "live_recovery_proved",
    "operation_id",
    "plan_fingerprint",
    "receipts",
    "schema",
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


def _fail(code: str) -> Never:
    raise LiveScheduleError(code)


def _safe_absolute(path: Path) -> bool:
    lexical = PurePath(path)
    return (
        path.is_absolute()
        and path != Path(path.anchor)
        and all(part not in {"", ".", ".."} for part in lexical.parts[1:])
    )


@dataclass(frozen=True, slots=True)
class MaintenanceConfiguration:
    """Explicit local authorities consumed by the three maintenance activities."""

    state_root: Path
    schedule_state_path: Path
    operational_input_root: Path
    recovery_proof_path: Path
    recovery_proof_fingerprint_path: Path
    telemetry_root: Path

    def __post_init__(self) -> None:
        """Reject inferred, relative, or lexically aliased local authorities."""
        paths = (
            self.state_root,
            self.schedule_state_path,
            self.operational_input_root,
            self.recovery_proof_path,
            self.recovery_proof_fingerprint_path,
            self.telemetry_root,
        )
        if any(not _safe_absolute(path) for path in paths):
            _fail("HK_V1_MAINTENANCE_CONFIGURATION_INVALID")
        if len(set(paths)) != len(paths):
            _fail("HK_V1_MAINTENANCE_CONFIGURATION_INVALID")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> MaintenanceConfiguration:
        """Resolve explicit overrides against one fixed local prototype namespace."""
        try:
            state_root = Path(environment.get("ASKLEGAL_CONTROL_STATE_ROOT", _DEFAULT_STATE_ROOT))
            return cls(
                state_root=state_root,
                schedule_state_path=state_root / "hk-v1-live-schedules.json",
                operational_input_root=Path(
                    environment.get(
                        "ASKLEGAL_HK_V1_OPERATIONAL_INPUT_ROOT",
                        str(state_root / "operational"),
                    )
                ),
                recovery_proof_path=Path(
                    environment.get(
                        "ASKLEGAL_HK_V1_RECOVERY_PROOF",
                        str(state_root / "recovery" / "latest-proof.json"),
                    )
                ),
                recovery_proof_fingerprint_path=Path(
                    environment.get(
                        "ASKLEGAL_HK_V1_RECOVERY_PROOF_FINGERPRINT",
                        str(state_root / "recovery" / "latest-proof.sha256"),
                    )
                ),
                telemetry_root=Path(
                    environment.get(
                        "ASKLEGAL_HK_V1_TELEMETRY_ROOT",
                        str(state_root / "telemetry"),
                    )
                ),
            )
        except Exception as error:
            code = "HK_V1_MAINTENANCE_CONFIGURATION_INVALID"
            raise LiveScheduleError(code) from error


def _read_regular(path: Path, *, code: str, maximum: int = _MAX_INPUT_BYTES) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            _fail(code)
        content = path.read_bytes()
    except LiveScheduleError:
        raise
    except Exception as error:
        raise LiveScheduleError(code) from error
    if not content or len(content) > maximum:
        _fail(code)
    return content


def _directory_inventory(root: Path, *, code: str) -> list[tuple[str, bytes]]:
    """Read one bounded symlink-free recursive inventory in lexical order."""
    try:
        if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
            _fail(code)
        paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
        if any(path.is_symlink() for path in paths):
            _fail(code)
        files = [path for path in paths if path.is_file()]
        if not files or len(files) > _MAX_INPUT_FILES:
            _fail(code)
        inventory = [
            (path.relative_to(root).as_posix(), _read_regular(path, code=code)) for path in files
        ]
    except LiveScheduleError:
        raise
    except Exception as error:
        raise LiveScheduleError(code) from error
    if sum(len(content) for _name, content in inventory) > _MAX_INPUT_BYTES:
        _fail(code)
    return inventory


def _request(
    payload: object,
    kind: ScheduleKind,
    matrix: HongKongV1CoverageMatrix,
    *,
    code: str,
) -> dict[str, JsonValue]:
    try:
        document = checked_json_value(payload)
        if type(document) is not dict or set(document) != {
            "command_id",
            "command_fingerprint",
            "matrix_fingerprint",
            "matrix_revision",
            "attempt_number",
            "operation_id",
            "schedule_kind",
            "scheduled_at",
            "state",
        }:
            _fail(code)
        scheduled_at = document["scheduled_at"]
        if type(scheduled_at) is not str:
            _fail(code)
        expected = schedule_request(kind, scheduled_at, matrix=matrix)
        attempt_number = document["attempt_number"]
        if (
            type(attempt_number) is not int
            or attempt_number < 0
            or document
            != {
                "command_id": expected.command_id,
                "command_fingerprint": expected.command_fingerprint,
                "matrix_fingerprint": expected.matrix_fingerprint,
                "matrix_revision": expected.matrix_revision,
                "attempt_number": attempt_number,
                "operation_id": schedule_attempt_operation_id(kind, scheduled_at, attempt_number),
                "schedule_kind": kind.value,
                "scheduled_at": scheduled_at,
                "state": "REQUESTED",
            }
        ):
            _fail(code)
    except LiveScheduleError:
        raise
    except Exception as error:
        raise LiveScheduleError(code) from error
    else:
        return document


def _atomic_retain(path: Path, content: bytes, *, code: str) -> bool:
    """Create one replay-safe local object and verify its exact bytes."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.parent.resolve(strict=True) != path.parent or path.is_symlink():
            _fail(code)
        with exclusive_local_state_lock(path):
            if path.exists():
                if path.is_symlink() or path.read_bytes() != content:
                    _fail(code)
                return False
            temporary = path.with_name(f".{path.name}.{token_hex(16)}.tmp")
            try:
                descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(path)
            finally:
                with suppress(FileNotFoundError):
                    temporary.unlink()
            if path.read_bytes() != content:
                _fail(code)
            return True
    except LiveScheduleError:
        raise
    except Exception as error:
        raise LiveScheduleError(code) from error


def _live_recovery_proved(document: dict[str, JsonValue]) -> bool:
    if set(document) != _LIVE_RECOVERY_FIELDS:
        return False
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    receipts = document.get("receipts")
    if (
        document.get("schema") != "asklegal.hk-v1-live-recovery-execution-result/v1"
        or document.get("live_recovery_proved") is not True
        or _FINGERPRINT.fullmatch(str(document.get("plan_fingerprint"))) is None
        or supplied != f"sha256:{sha256(canonicalize(checked_json_value(unsigned))).hexdigest()}"
        or not isinstance(receipts, list)
        or len(receipts) != len(_LIVE_RECOVERY_STEPS)
    ):
        return False
    for expected_step, raw in zip(_LIVE_RECOVERY_STEPS, receipts, strict=True):
        if not isinstance(raw, dict):
            return False
        if set(raw) != {
            "effect_fingerprint",
            "plan_fingerprint",
            "readback_fingerprint",
            "step",
            "target_identity",
        }:
            return False
        if (
            raw.get("step") != expected_step
            or raw.get("plan_fingerprint") != document.get("plan_fingerprint")
            or _FINGERPRINT.fullmatch(str(raw.get("effect_fingerprint"))) is None
            or raw.get("readback_fingerprint") != raw.get("effect_fingerprint")
            or not str(raw.get("target_identity")).startswith("r_")
        ):
            return False
    return True


class LocalMaintenanceActivities:
    """Perform only bounded local archival, verification, and assessment effects."""

    def __init__(
        self,
        configuration: MaintenanceConfiguration,
        matrix: HongKongV1CoverageMatrix,
    ) -> None:
        """Bind approved Matrix lineage without opening any local prerequisite."""
        if (
            type(configuration) is not MaintenanceConfiguration
            or type(matrix) is not HongKongV1CoverageMatrix
            or not is_hk_v1_coverage_matrix_policy_approved(matrix)
        ):
            _fail("HK_V1_MAINTENANCE_CONFIGURATION_INVALID")
        self._configuration = configuration
        self._matrix = matrix

    def _retain_result(
        self,
        request: dict[str, JsonValue],
        kind: ScheduleKind,
        details: dict[str, JsonValue],
        *,
        code: str,
    ) -> dict[str, object]:
        operation_id = request["operation_id"]
        if type(operation_id) is not str or _OPERATION_ID.fullmatch(operation_id) is None:
            _fail(code)
        relative = f"maintenance-results/{kind.value.lower()}/{operation_id}.json"
        body: dict[str, JsonValue] = {
            "schema_id": "asklegal.hk-v1.local-maintenance-result",
            "schema_version": "1.0.0",
            "request": request,
            "matrix_revision": self._matrix.revision,
            "matrix_fingerprint": self._matrix.fingerprint,
            "details": details,
        }
        document = dict(body)
        document["fingerprint"] = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
        content = canonicalize(document) + b"\n"
        created = _atomic_retain(self._configuration.state_root / relative, content, code=code)
        retained = _read_regular(self._configuration.state_root / relative, code=code)
        if retained != content:
            _fail(code)
        return {
            **cast("dict[str, object]", details),
            "result_reference": relative,
            "result_created": created,
        }

    def perform_hk_v1_audit_archive(
        self, _context: ActivityContext, payload: object
    ) -> dict[str, object]:
        """Archive and read back one exact bounded operational input inventory."""
        code = "HK_V1_AUDIT_ARCHIVE_NOT_READY"
        request = _request(payload, ScheduleKind.AUDIT_ARCHIVE, self._matrix, code=code)
        inputs = [
            (
                "schedule/hk-v1-live-schedules.json",
                _read_regular(self._configuration.schedule_state_path, code=code),
            ),
            *(
                (f"operational/{name}", content)
                for name, content in _directory_inventory(
                    self._configuration.operational_input_root, code=code
                )
            ),
        ]
        inventory: list[dict[str, JsonValue]] = []
        for name, content in inputs:
            digest = sha256(content).hexdigest()
            object_ref = f"audit-archive/objects/{digest}.bin"
            _atomic_retain(self._configuration.state_root / object_ref, content, code=code)
            inventory.append(
                {
                    "input_path": name,
                    "byte_length": len(content),
                    "fingerprint": f"sha256:{digest}",
                    "archive_object_ref": object_ref,
                    "read_back_verified": True,
                }
            )
        details = cast(
            "dict[str, JsonValue]",
            checked_json_value(
                {
                    "result": "AUDIT_ARCHIVE_COMPLETE",
                    "input_count": len(inventory),
                    "inventory": inventory,
                }
            ),
        )
        return self._retain_result(request, ScheduleKind.AUDIT_ARCHIVE, details, code=code)

    def perform_hk_v1_recovery_verification(
        self, _context: ActivityContext, payload: object
    ) -> dict[str, object]:
        """Verify one retained exact local recovery-contract proof without rerunning it."""
        code = "HK_V1_RECOVERY_VERIFICATION_NOT_READY"
        request = _request(payload, ScheduleKind.RECOVERY_VERIFY, self._matrix, code=code)
        proof = _read_regular(
            self._configuration.recovery_proof_path,
            code=code,
            maximum=_MAX_RECOVERY_PROOF_BYTES,
        )
        claimed = _read_regular(
            self._configuration.recovery_proof_fingerprint_path,
            code=code,
            maximum=100,
        )
        proof_fingerprint = f"sha256:{sha256(proof).hexdigest()}"
        if claimed != f"{proof_fingerprint}\n".encode():
            _fail(code)
        try:
            document = parse_json_bytes(proof, max_bytes=_MAX_RECOVERY_PROOF_BYTES)
        except Exception as error:
            raise LiveScheduleError(code) from error
        if type(document) is not dict or canonicalize(document) != proof:
            _fail(code)
        if _live_recovery_proved(document):
            details: dict[str, JsonValue] = {
                "result": "LIVE_RECOVERY_PROOF_VERIFIED",
                "proof_fingerprint": proof_fingerprint,
                "recovery_executed": True,
            }
        else:
            if (
                set(document) != _RECOVERY_FIELDS
                or document["result_code"] != "LOCAL_RECOVERY_CONTRACT_PROVED"
                or document["contract_proved"] is not True
                or document["gate_f_eligible"] is not False
                or document["blockers"] != []
                or any(
                    document[name] != "PROVED"
                    for name in ("sql_result", "vault_result", "scheduler_result")
                )
            ):
                _fail(code)
            details = {
                "result": "RECOVERY_PROOF_VERIFIED",
                "proof_fingerprint": proof_fingerprint,
                "recovery_executed": False,
            }
        return self._retain_result(request, ScheduleKind.RECOVERY_VERIFY, details, code=code)

    def perform_hk_v1_telemetry_retention(
        self, _context: ActivityContext, payload: object
    ) -> dict[str, object]:
        """Retain a bounded deletion-free telemetry assessment for later authorization."""
        code = "HK_V1_TELEMETRY_RETENTION_NOT_READY"
        request = _request(payload, ScheduleKind.TELEMETRY_RETENTION, self._matrix, code=code)
        inventory = _directory_inventory(self._configuration.telemetry_root, code=code)
        if any("/" in name or _TELEMETRY_NAME.fullmatch(name) is None for name, _ in inventory):
            _fail(code)
        scheduled_at = cast("str", request["scheduled_at"])
        cutoff = datetime.fromisoformat(scheduled_at).date() - timedelta(days=_RETENTION_DAYS)
        entries: list[dict[str, JsonValue]] = []
        candidates: list[str] = []
        for name, content in inventory:
            match = _TELEMETRY_NAME.fullmatch(name)
            if match is None:
                _fail(code)
            try:
                file_day = date.fromisoformat(match.group("day"))
            except ValueError as error:
                raise LiveScheduleError(code) from error
            candidate = file_day < cutoff
            if candidate:
                candidates.append(name)
            entries.append(
                {
                    "path": name,
                    "byte_length": len(content),
                    "fingerprint": f"sha256:{sha256(content).hexdigest()}",
                    "disposition": "DELETE_REQUIRES_AUTHORITY" if candidate else "RETAIN",
                }
            )
        details = cast(
            "dict[str, JsonValue]",
            checked_json_value(
                {
                    "result": "RETENTION_ASSESSMENT_RETAINED",
                    "retention_days": _RETENTION_DAYS,
                    "candidate_paths": candidates,
                    "inventory": entries,
                    "deletion_performed": False,
                }
            ),
        )
        return self._retain_result(request, ScheduleKind.TELEMETRY_RETENTION, details, code=code)


__all__ = ["LocalMaintenanceActivities", "MaintenanceConfiguration"]
