"""Operator-facing schedule and Task 10 acceptance-cycle boundaries."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Never, cast

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_control_plane.v1_acceptance import validate_hk_v1_acceptance_cycle_result
from asklegal_control_plane.v1_schedule import (
    MAINTENANCE_ACTIVITIES,
    InMemoryLiveScheduleStore,
    LiveScheduleError,
    LiveSchedulerClient,
    LiveScheduleStore,
    LocalLiveScheduleStore,
    ScheduleDefinition,
    ScheduleEnqueueResult,
    ScheduleKind,
    ScheduleRequest,
    ScheduleState,
    StoredScheduleCommand,
    UnavailableMaintenanceActivities,
    applicable_schedule_slot,
    dispatch_schedule,
    enqueue_schedule,
    mark_schedule_terminal,
    release_terminal_schedules,
    run_hk_v1_audit_archive,
    run_hk_v1_recovery_verification,
    run_hk_v1_telemetry_retention,
    schedule_definitions,
    schedule_request,
)
from asklegal_durable_task import OrchestrationStatus, V1SchedulerSettings
from asklegal_reporting import (
    HongKongV1CoverageMatrix,
    is_hk_v1_coverage_matrix_policy_approved,
    load_hk_v1_coverage_matrix,
)

_ACCEPTANCE_SELECTION_SCHEMA = "asklegal.hk-v1.acceptance-cutoff-selection"
_ACCEPTANCE_SELECTION_VERSION = "1.0.0"
_ACCEPTANCE_ORCHESTRATOR = "run_hk_v1_acceptance_cycle"
_ACCEPTANCE_VERSION = "1.0.0"
_MAX_SELECTION_BYTES = 1_000_000
_OUTPUT_MODE = 0o600
_STABLE_ID_LENGTH = 52
_FINGERPRINT_LENGTH = 71
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|\+00:00|\+08:00)\Z"
)
_FAMILIES = ("CASES", "LEGISLATION")
_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_SELECTION_FIELDS = frozenset(
    {"schema_id", "schema_version", "families", "scope_ids", "t1", "t2", "fingerprint"}
)
_CUTOFF_FIELDS = frozenset(
    {
        "observation_cutoff",
        "cases_manifest_fingerprint",
        "legislation_manifest_fingerprint",
        "authentic_changed_families",
        "family_acquisition_evidence",
    }
)
_FAMILY_EVIDENCE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "root_cycle_id",
        "root_plan_fingerprint",
        "evidence_reference",
        "children",
    }
)
_FAMILY_CHILD_FIELDS = frozenset(
    {
        "source_family",
        "cycle_id",
        "journal_ref",
        "manifest_fingerprint",
        "journal_head_fingerprint",
        "result",
        "manifest_reference",
    }
)
_REFERENCE_FIELDS = frozenset({"vault", "logical_key", "version_id", "fingerprint", "byte_length"})


class AcceptanceCycleError(RuntimeError):
    """One closed Task 10 preflight or dispatch failure."""


class AcceptanceCycleKind(StrEnum):
    """The only two explicit live-acceptance cycle roles."""

    BASELINE = "BASELINE"
    UPDATE = "UPDATE"


@dataclass(frozen=True, slots=True)
class AcceptanceCycleRequest:
    """Exact replay-safe request produced before any scheduler or source effect."""

    kind: AcceptanceCycleKind
    cutoff_key: str
    observation_cutoff: str
    cases_manifest_fingerprint: str
    legislation_manifest_fingerprint: str
    changed_families: tuple[str, ...]
    family_acquisition_evidence: dict[str, JsonValue]
    cutoff_selection_fingerprint: str
    matrix_revision: str
    matrix_fingerprint: str
    families: tuple[str, ...]
    scope_ids: tuple[str, ...]
    command_id: str
    operation_id: str
    command_fingerprint: str

    def document(self) -> dict[str, JsonValue]:
        """Return the closed scheduler payload, including its stable identities."""
        _validate_acceptance_request(self)
        return cast(
            "dict[str, JsonValue]",
            checked_json_value(
                {
                    "schema_id": "asklegal.hk-v1.acceptance-cycle-request",
                    "schema_version": _ACCEPTANCE_VERSION,
                    "kind": self.kind.value,
                    "cutoff_key": self.cutoff_key,
                    "observation_cutoff": self.observation_cutoff,
                    "cases_manifest_fingerprint": self.cases_manifest_fingerprint,
                    "legislation_manifest_fingerprint": self.legislation_manifest_fingerprint,
                    "authentic_changed_families": list(self.changed_families),
                    "family_acquisition_evidence": self.family_acquisition_evidence,
                    "cutoff_selection_fingerprint": self.cutoff_selection_fingerprint,
                    "matrix_revision": self.matrix_revision,
                    "matrix_fingerprint": self.matrix_fingerprint,
                    "families": list(self.families),
                    "scope_ids": list(self.scope_ids),
                    "command_id": self.command_id,
                    "operation_id": self.operation_id,
                    "command_fingerprint": self.command_fingerprint,
                }
            ),
        )


def preflight_acceptance_cycle(
    kind: AcceptanceCycleKind,
    cutoff_selection: bytes,
    *,
    cutoff_key: str,
    matrix: HongKongV1CoverageMatrix,
) -> AcceptanceCycleRequest:
    """Re-read and bind one exact T1/T2 request without dispatching anything."""
    if type(kind) is not AcceptanceCycleKind:
        _acceptance_fail("ACCEPTANCE_KIND_INVALID")
    expected_key = "t1" if kind is AcceptanceCycleKind.BASELINE else "t2"
    if cutoff_key != expected_key:
        _acceptance_fail("ACCEPTANCE_CUTOFF_ROLE_INVALID")
    if not is_hk_v1_coverage_matrix_policy_approved(matrix):
        _acceptance_fail("ACCEPTANCE_MATRIX_INVALID")
    selection = _selection_document(cutoff_selection)
    cutoff = _exact_object(selection[cutoff_key])
    changed = _exact_text_tuple(cutoff["authentic_changed_families"])
    if (kind is AcceptanceCycleKind.BASELINE and changed) or (
        kind is AcceptanceCycleKind.UPDATE and not changed
    ):
        _acceptance_fail("ACCEPTANCE_CHANGE_INVALID")
    cases_fingerprint = _fingerprint(cutoff["cases_manifest_fingerprint"])
    legislation_fingerprint = _fingerprint(cutoff["legislation_manifest_fingerprint"])
    family_evidence = _family_acquisition_evidence(
        cutoff["family_acquisition_evidence"],
        cases_fingerprint,
        legislation_fingerprint,
    )
    identity: dict[str, JsonValue] = {
        "kind": kind.value,
        "cutoff_key": cutoff_key,
        "observation_cutoff": _timestamp(cutoff["observation_cutoff"]),
        "cases_manifest_fingerprint": cases_fingerprint,
        "legislation_manifest_fingerprint": legislation_fingerprint,
        "authentic_changed_families": list(changed),
        "family_acquisition_evidence": family_evidence,
        "cutoff_selection_fingerprint": _fingerprint(selection["fingerprint"]),
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
        "families": list(_FAMILIES),
        "scope_ids": list(_SCOPES),
    }
    identity_digest = sha256(canonicalize(checked_json_value(identity))).hexdigest()
    command_id = f"cmd_{identity_digest[:48]}"
    operation_id = f"cyc_{identity_digest[:48]}"
    command_fingerprint = (
        "sha256:"
        + sha256(
            canonicalize(
                checked_json_value(
                    {**identity, "command_id": command_id, "operation_id": operation_id}
                )
            )
        ).hexdigest()
    )
    request = AcceptanceCycleRequest(
        kind,
        cutoff_key,
        _timestamp(cutoff["observation_cutoff"]),
        _fingerprint(cutoff["cases_manifest_fingerprint"]),
        _fingerprint(cutoff["legislation_manifest_fingerprint"]),
        changed,
        family_evidence,
        _fingerprint(selection["fingerprint"]),
        matrix.revision,
        matrix.fingerprint,
        _FAMILIES,
        _SCOPES,
        command_id,
        operation_id,
        command_fingerprint,
    )
    _validate_acceptance_request(request)
    return request


def dispatch_acceptance_cycle(
    client: LiveSchedulerClient,
    request: AcceptanceCycleRequest,
) -> str:
    """Schedule one stable Control instance or return exact replay presence."""
    _validate_acceptance_request(request)
    if not callable(getattr(client, "get_orchestration_state", None)) or not callable(
        getattr(client, "schedule_new_orchestration", None)
    ):
        _acceptance_fail("ACCEPTANCE_DISPATCH_INVALID")
    try:
        if client.get_orchestration_state(request.operation_id) is not None:
            return "INSTANCE_PRESENT"
        instance_id = client.schedule_new_orchestration(
            _ACCEPTANCE_ORCHESTRATOR,
            input=request.document(),
            instance_id=request.operation_id,
            version=_ACCEPTANCE_VERSION,
        )
        if instance_id != request.operation_id:
            _acceptance_fail("ACCEPTANCE_DISPATCH_INVALID")
    except AcceptanceCycleError:
        raise
    except Exception as error:  # noqa: BLE001 - scheduler client is an untrusted boundary.
        try:
            existing = client.get_orchestration_state(request.operation_id)
        except Exception:  # noqa: BLE001 - best-effort idempotency reconciliation.
            existing = None
        if existing is not None:
            return "INSTANCE_PRESENT"
        _acceptance_fail_from("ACCEPTANCE_DISPATCH_FAILED", error)
    else:
        return "SCHEDULED"


def retain_acceptance_cycle(root: Path, request: AcceptanceCycleRequest) -> str:
    """Persist one exact request before dispatch and replay it after process loss."""
    _validate_acceptance_request(request)
    if (
        not root.is_absolute()
        or root == Path(root.anchor)
        or root.is_symlink()
        or not root.is_dir()
    ):
        _acceptance_fail("ACCEPTANCE_STATE_ROOT_INVALID")
    state_path = root / "hk-v1-acceptance-cycles" / f"{request.operation_id}.json"
    expected = canonicalize(checked_json_value(request.document())) + b"\n"
    try:
        with exclusive_local_state_lock(state_path):
            state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if state_path.exists():
                if state_path.is_symlink() or not state_path.is_file():
                    _acceptance_fail("ACCEPTANCE_STATE_INVALID")
                if state_path.read_bytes() != expected:
                    _acceptance_fail("ACCEPTANCE_STATE_CONFLICT")
                return "EXACT_REPLAY"
            descriptor, name = tempfile.mkstemp(
                dir=state_path.parent,
                prefix=f".{request.operation_id}.",
            )
            temporary = Path(name)
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(expected)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(state_path)
            finally:
                temporary.unlink(missing_ok=True)
            if state_path.read_bytes() != expected:
                _acceptance_fail("ACCEPTANCE_STATE_INVALID")
    except AcceptanceCycleError:
        raise
    except OSError as error:
        _acceptance_fail_from("ACCEPTANCE_STATE_INVALID", error)
    return "RETAINED"


def read_acceptance_cycle_result(
    client: LiveSchedulerClient,
    request: AcceptanceCycleRequest,
) -> bytes:
    """Read and rebind one completed Control result without scheduling work."""
    _validate_acceptance_request(request)
    if not callable(getattr(client, "get_orchestration_state", None)):
        _acceptance_fail("ACCEPTANCE_RESULT_READBACK_INVALID")
    try:
        state = client.get_orchestration_state(request.operation_id)
        if (
            state is None
            or getattr(state, "instance_id", None) != request.operation_id
            or getattr(state, "name", None) != _ACCEPTANCE_ORCHESTRATOR
            or getattr(state, "runtime_status", None) is not OrchestrationStatus.COMPLETED
        ):
            _acceptance_fail("ACCEPTANCE_RESULT_NOT_READY")
        serialized = getattr(state, "serialized_output", None)
        if type(serialized) is not str or not serialized:
            _acceptance_fail("ACCEPTANCE_RESULT_NOT_READY")
        value = parse_json_bytes(serialized.encode("utf-8"), max_bytes=_MAX_SELECTION_BYTES)
        result = validate_hk_v1_acceptance_cycle_result(value)
    except AcceptanceCycleError:
        raise
    except Exception as error:  # noqa: BLE001 - scheduler state is an untrusted boundary.
        _acceptance_fail_from("ACCEPTANCE_RESULT_READBACK_INVALID", error)
    if (
        result["kind"] != request.kind.value
        or result["operation_id"] != request.operation_id
        or result["command_fingerprint"] != request.command_fingerprint
        or result["observation_cutoff"] != request.observation_cutoff
        or result["families"] != list(request.families)
        or result["scope_ids"] != list(request.scope_ids)
    ):
        _acceptance_fail("ACCEPTANCE_RESULT_READBACK_INVALID")
    return canonicalize(checked_json_value(result))


def retain_acceptance_cycle_result(path: Path, content: bytes) -> str:
    """Create or exactly replay one canonical 0600 acceptance result."""
    if (
        not path.is_absolute()
        or path == Path(path.anchor)
        or path != path.resolve(strict=False)
        or path.is_symlink()
        or type(content) is not bytes
        or not content
        or len(content) > _MAX_SELECTION_BYTES
    ):
        _acceptance_fail("ACCEPTANCE_RESULT_OUTPUT_INVALID")
    try:
        parsed = parse_json_bytes(content, max_bytes=_MAX_SELECTION_BYTES)
        if canonicalize(parsed) != content:
            _acceptance_fail("ACCEPTANCE_RESULT_OUTPUT_INVALID")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink() or path.parent.resolve(strict=True) != path.parent:
            _acceptance_fail("ACCEPTANCE_RESULT_OUTPUT_INVALID")
        with exclusive_local_state_lock(path):
            if path.exists():
                if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                    _acceptance_fail("ACCEPTANCE_RESULT_OUTPUT_CONFLICT")
                return "EXACT_REPLAY"
            descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
            temporary = Path(name)
            try:
                os.fchmod(descriptor, _OUTPUT_MODE)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(path)
                directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink(missing_ok=True)
            if path.read_bytes() != content or path.stat().st_mode & 0o777 != _OUTPUT_MODE:
                _acceptance_fail("ACCEPTANCE_RESULT_OUTPUT_INVALID")
    except AcceptanceCycleError:
        raise
    except (OSError, ValueError) as error:
        _acceptance_fail_from("ACCEPTANCE_RESULT_OUTPUT_INVALID", error)
    return "RETAINED"


def _selection_document(content: bytes) -> dict[str, JsonValue]:
    if type(content) is not bytes or not content or len(content) > _MAX_SELECTION_BYTES:
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    normalized = content[:-1] if content.endswith(b"\n") else content
    try:
        value = parse_json_bytes(normalized, max_bytes=_MAX_SELECTION_BYTES)
    except ContractViolation as error:
        _acceptance_fail_from("ACCEPTANCE_CUTOFF_INVALID", error)
    if (
        type(value) is not dict
        or canonicalize(value) != normalized
        or frozenset(value) != _SELECTION_FIELDS
    ):
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    if (
        value["schema_id"] != _ACCEPTANCE_SELECTION_SCHEMA
        or value["schema_version"] != _ACCEPTANCE_SELECTION_VERSION
        or _exact_text_tuple(value["families"]) != _FAMILIES
        or _exact_text_tuple(value["scope_ids"]) != _SCOPES
    ):
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    for key in ("t1", "t2"):
        cutoff = _exact_object(value[key])
        if frozenset(cutoff) != _CUTOFF_FIELDS:
            _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
        _timestamp(cutoff["observation_cutoff"])
        cases_fingerprint = _fingerprint(cutoff["cases_manifest_fingerprint"])
        legislation_fingerprint = _fingerprint(cutoff["legislation_manifest_fingerprint"])
        _family_acquisition_evidence(
            cutoff["family_acquisition_evidence"],
            cases_fingerprint,
            legislation_fingerprint,
        )
        changed = _exact_text_tuple(cutoff["authentic_changed_families"])
        if any(item not in _FAMILIES for item in changed) or changed != tuple(sorted(set(changed))):
            _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    fingerprint = _fingerprint(value["fingerprint"])
    unsigned = dict(value)
    unsigned.pop("fingerprint")
    if fingerprint != "sha256:" + sha256(canonicalize(checked_json_value(unsigned))).hexdigest():
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    return value


def _validate_acceptance_request(request: AcceptanceCycleRequest) -> None:
    if type(request) is not AcceptanceCycleRequest:
        _acceptance_fail("ACCEPTANCE_REQUEST_INVALID")
    expected_key = "t1" if request.kind is AcceptanceCycleKind.BASELINE else "t2"
    if (
        type(request.kind) is not AcceptanceCycleKind
        or request.cutoff_key != expected_key
        or type(request.matrix_revision) is not str
        or not request.matrix_revision
        or request.families != _FAMILIES
        or request.scope_ids != _SCOPES
        or request.changed_families != tuple(sorted(set(request.changed_families)))
        or any(item not in _FAMILIES for item in request.changed_families)
        or len(request.command_id) != _STABLE_ID_LENGTH
        or not request.command_id.startswith("cmd_")
        or len(request.operation_id) != _STABLE_ID_LENGTH
        or not request.operation_id.startswith("cyc_")
        or request.command_id[4:] != request.operation_id[4:]
    ):
        _acceptance_fail("ACCEPTANCE_REQUEST_INVALID")
    _timestamp(request.observation_cutoff)
    for value in (
        request.cases_manifest_fingerprint,
        request.legislation_manifest_fingerprint,
        request.cutoff_selection_fingerprint,
        request.matrix_fingerprint,
        request.command_fingerprint,
    ):
        _fingerprint(value)
    if (request.kind is AcceptanceCycleKind.BASELINE and request.changed_families) or (
        request.kind is AcceptanceCycleKind.UPDATE and not request.changed_families
    ):
        _acceptance_fail("ACCEPTANCE_REQUEST_INVALID")
    identity: dict[str, JsonValue] = {
        "kind": request.kind.value,
        "cutoff_key": request.cutoff_key,
        "observation_cutoff": request.observation_cutoff,
        "cases_manifest_fingerprint": request.cases_manifest_fingerprint,
        "legislation_manifest_fingerprint": request.legislation_manifest_fingerprint,
        "authentic_changed_families": list(request.changed_families),
        "family_acquisition_evidence": request.family_acquisition_evidence,
        "cutoff_selection_fingerprint": request.cutoff_selection_fingerprint,
        "matrix_revision": request.matrix_revision,
        "matrix_fingerprint": request.matrix_fingerprint,
        "families": list(request.families),
        "scope_ids": list(request.scope_ids),
    }
    digest = sha256(canonicalize(checked_json_value(identity))).hexdigest()
    expected_id = digest[:48]
    expected_fingerprint = (
        "sha256:"
        + sha256(
            canonicalize(
                checked_json_value(
                    {
                        **identity,
                        "command_id": f"cmd_{expected_id}",
                        "operation_id": f"cyc_{expected_id}",
                    }
                )
            )
        ).hexdigest()
    )
    if (
        request.command_id != f"cmd_{expected_id}"
        or request.operation_id != f"cyc_{expected_id}"
        or request.command_fingerprint != expected_fingerprint
    ):
        _acceptance_fail("ACCEPTANCE_REQUEST_INVALID")
    _family_acquisition_evidence(
        request.family_acquisition_evidence,
        request.cases_manifest_fingerprint,
        request.legislation_manifest_fingerprint,
    )


def _exact_object(value: JsonValue) -> dict[str, JsonValue]:
    if type(value) is not dict:
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    return value


def _exact_text_tuple(value: JsonValue) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    return cast("tuple[str, ...]", tuple(value))


def _family_acquisition_evidence(
    value: JsonValue,
    cases_manifest_fingerprint: str,
    legislation_manifest_fingerprint: str,
) -> dict[str, JsonValue]:
    evidence = _exact_object(value)
    if (
        frozenset(evidence) != _FAMILY_EVIDENCE_FIELDS
        or evidence["schema_id"] != "asklegal.hk-v1.acceptance-family-acquisition-evidence"
        or evidence["schema_version"] != _ACCEPTANCE_VERSION
        or type(evidence["root_cycle_id"]) is not str
        or not evidence["root_cycle_id"]
    ):
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    _fingerprint(evidence["root_plan_fingerprint"])
    _exact_reference(evidence["evidence_reference"])
    raw_children = evidence["children"]
    if type(raw_children) is not list or len(raw_children) != len(_FAMILIES):
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    expected_fingerprints = (cases_manifest_fingerprint, legislation_manifest_fingerprint)
    for family, expected_fingerprint, raw_child in zip(
        _FAMILIES, expected_fingerprints, raw_children, strict=True
    ):
        child = _exact_object(raw_child)
        if frozenset(child) != _FAMILY_CHILD_FIELDS:
            _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
        cycle_id = child["cycle_id"]
        if (
            child["source_family"] != family
            or type(cycle_id) is not str
            or not cycle_id
            or child["journal_ref"] != f"acquisition-journals/{cycle_id}"
            or child["manifest_fingerprint"] != expected_fingerprint
            or child["result"] not in {"COMPLETE", "NO_CHANGE"}
        ):
            _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
        _fingerprint(child["journal_head_fingerprint"])
        _exact_reference(child["manifest_reference"])
    return evidence


def _exact_reference(value: JsonValue) -> dict[str, JsonValue]:
    reference = _exact_object(value)
    if (
        frozenset(reference) != _REFERENCE_FIELDS
        or reference["vault"] != "PRIMARY"
        or type(reference["logical_key"]) is not str
        or not reference["logical_key"]
        or type(reference["version_id"]) is not str
        or not reference["version_id"]
        or type(reference["byte_length"]) is not int
        or reference["byte_length"] < 1
    ):
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    _fingerprint(reference["fingerprint"])
    return reference


def _fingerprint(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != _FINGERPRINT_LENGTH
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    return value


def _timestamp(value: object) -> str:
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    try:
        parsed = datetime.fromisoformat(
            value.removesuffix("Z") + ("+00:00" if value.endswith("Z") else "")
        )
    except ValueError as error:
        _acceptance_fail_from("ACCEPTANCE_CUTOFF_INVALID", error)
    if parsed.utcoffset() not in {timedelta(0), timedelta(hours=8)} or parsed.microsecond:
        _acceptance_fail("ACCEPTANCE_CUTOFF_INVALID")
    return value


def _acceptance_fail(code: str) -> Never:
    raise AcceptanceCycleError(code)


def _acceptance_fail_from(code: str, error: Exception) -> Never:
    raise AcceptanceCycleError(code) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preflight, enqueue, or read one exact HK V1 acceptance cycle"
    )
    parser.add_argument("--kind", choices=tuple(AcceptanceCycleKind), required=True)
    parser.add_argument("--cutoff-file", type=Path, required=True)
    parser.add_argument("--cutoff-key", choices=("t1", "t2"), required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--mode", choices=("preflight", "enqueue", "result"), default="preflight")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    scheduler_client: LiveSchedulerClient | None = None,
) -> int:
    """Run the no-effect default CLI; enqueue is explicit and scheduler-bound."""
    try:
        args = _parser().parse_args(argv)
        request = preflight_acceptance_cycle(
            AcceptanceCycleKind(args.kind),
            args.cutoff_file.read_bytes(),
            cutoff_key=args.cutoff_key,
            matrix=load_hk_v1_coverage_matrix(args.matrix),
        )
        resolution = "PREFLIGHT_READY"
        if args.mode == "enqueue":
            if args.state_root is None:
                _acceptance_fail("ACCEPTANCE_STATE_ROOT_INVALID")
            if args.output is not None:
                _acceptance_fail("ACCEPTANCE_RESULT_OUTPUT_INVALID")
            retained = retain_acceptance_cycle(args.state_root, request)
            client = scheduler_client
            if client is None:
                settings = V1SchedulerSettings.for_application("CONTROL_PLANE")
                client = settings.create_client(default_version=_ACCEPTANCE_VERSION)
            dispatched = dispatch_acceptance_cycle(client, request)
            resolution = f"{retained}:{dispatched}"
        elif args.mode == "result":
            if args.state_root is not None or args.output is None:
                _acceptance_fail("ACCEPTANCE_RESULT_OUTPUT_INVALID")
            client = scheduler_client
            if client is None:
                settings = V1SchedulerSettings.for_application("CONTROL_PLANE")
                client = settings.create_client(default_version=_ACCEPTANCE_VERSION)
            content = read_acceptance_cycle_result(client, request)
            resolution = "RESULT_" + retain_acceptance_cycle_result(args.output, content)
        elif args.state_root is not None or args.output is not None:
            _acceptance_fail("ACCEPTANCE_RESULT_OUTPUT_INVALID")
        output = {
            **request.document(),
            "enqueued": args.mode == "enqueue",
            "resolution": resolution,
        }
        sys.stdout.buffer.write(canonicalize(checked_json_value(output)) + b"\n")
    except AcceptanceCycleError, ContractViolation, OSError, ValueError:
        sys.stderr.write("HK_V1_ACCEPTANCE_CYCLE_NOT_READY\n")
        return 2
    return 0


__all__ = [
    "MAINTENANCE_ACTIVITIES",
    "AcceptanceCycleError",
    "AcceptanceCycleKind",
    "AcceptanceCycleRequest",
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
    "dispatch_acceptance_cycle",
    "dispatch_schedule",
    "enqueue_schedule",
    "mark_schedule_terminal",
    "preflight_acceptance_cycle",
    "read_acceptance_cycle_result",
    "release_terminal_schedules",
    "retain_acceptance_cycle",
    "retain_acceptance_cycle_result",
    "run_hk_v1_audit_archive",
    "run_hk_v1_recovery_verification",
    "run_hk_v1_telemetry_retention",
    "schedule_definitions",
    "schedule_request",
]


if __name__ == "__main__":
    raise SystemExit(main())
