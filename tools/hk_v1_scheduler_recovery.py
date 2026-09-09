"""Fixed-argv Scheduler replacement adapter for an authorized recovery drill.

The adapter does not impersonate a Scheduler administration API.  It validates one
retained checkpoint and one complete helper read-back, while the separately installed
privileged helper owns process replacement, old-lineage fencing, effect reconciliation,
and replacement start.  Credential values never enter argv or retained receipts.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import NoReturn, Protocol, cast

from tools.hk_v1_recovery_proof import (
    LiveRecoveryExecutionError,
    LiveRecoveryStep,
    LiveRecoveryStepReceipt,
    SealedCredentialReference,
)
from tools.hk_v1_sql_recovery import (
    FilesystemSealedCredentialVerifier,
    SealedCredentialVerifier,
)

__all__ = [
    "SchedulerLiveRecoveryPort",
    "SchedulerRecoveryCommandResult",
    "SchedulerRecoveryCommandRunner",
    "SubprocessSchedulerRecoveryCommandRunner",
]

_FP = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^r_[0-9a-f]{32}$")
_ROLE = re.compile(r"^(GENERAL|PROMOTION)$")
_DIRECTION = re.compile(r"^(FORWARD|REVERSE)$")
_HELPER = Path("/usr/local/libexec/asklegal-scheduler-recovery-admin")
_READBACK_SCHEMA = "asklegal.hk-v1-scheduler-recovery-readback/v1"
_NOT_FOUND_SCHEMA = "asklegal.hk-v1-scheduler-recovery-not-found/v1"
_MAX_OUTPUT = 2 * 1024 * 1024
_MAX_TIMEOUT_SECONDS = 900
_COMMAND_FLAGS = (
    "--plan-fingerprint",
    "--request-fingerprint",
    "--role",
    "--direction",
    "--snapshot-metadata",
    "--snapshot-fingerprint",
    "--checkpoint",
    "--checkpoint-fingerprint",
    "--lost-instance",
    "--replacement-instance",
    "--old-lineage",
    "--recovery-lineage",
    "--credential-file",
    "--credential-fingerprint",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "ascii"
    )


def _digest(value: object) -> str:
    return f"sha256:{sha256(_canonical(value)).hexdigest()}"


def _fail(code: str) -> NoReturn:
    raise LiveRecoveryExecutionError(code)


def _fingerprint(value: object, code: str) -> str:
    if type(value) is not str or _FP.fullmatch(value) is None:
        _fail(code)
    return value


def _identity(value: object, code: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        _fail(code)
    return value


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value or not value.isascii() or not value.isprintable():
        _fail(code)
    return value


def _canonical_document(raw: bytes, code: str) -> dict[str, object]:
    def invalid() -> NoReturn:
        raise ValueError

    try:
        if type(raw) is not bytes or not raw.endswith(b"\n") or len(raw) > _MAX_OUTPUT:
            invalid()
        value: object = json.loads(raw)
        if type(value) is not dict:
            invalid()
        document = cast("dict[object, object]", value)
        if any(type(key) is not str for key in document):
            invalid()
        typed = cast("dict[str, object]", document)
        if _canonical(typed) + b"\n" != raw:
            invalid()
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise LiveRecoveryExecutionError(code) from error
    else:
        return typed


def _sealed_document(raw: bytes, schema: str, code: str) -> dict[str, object]:
    document = _canonical_document(raw, code)
    unsigned = dict(document)
    fingerprint = unsigned.pop("fingerprint", None)
    if document.get("schema") != schema or fingerprint != _digest(unsigned):
        _fail(code)
    return document


def _read_exact(path: object, expected: MappingReference, code: str) -> bytes:
    if type(path) is not str:
        _fail(code)
    filesystem_path = Path(path)
    if not filesystem_path.is_absolute() or ".." in filesystem_path.parts:
        _fail(code)
    descriptor: int | None = None
    try:
        descriptor = os.open(filesystem_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        status = os.fstat(descriptor)
        if status.st_size != expected.byte_length or status.st_size > _MAX_OUTPUT:
            _fail(code)
        raw = os.read(descriptor, status.st_size + 1)
    except OSError as error:
        raise LiveRecoveryExecutionError(code) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        len(raw) != expected.byte_length
        or f"sha256:{sha256(raw).hexdigest()}" != expected.fingerprint
    ):
        _fail(code)
    return raw


@dataclass(frozen=True, slots=True)
class MappingReference:
    path: str
    byte_length: int
    fingerprint: str


def _mapping_reference(value: object, code: str) -> MappingReference:
    if type(value) is not dict:
        _fail(code)
    document = cast("dict[str, object]", value)
    if set(document) != {"byte_length", "fingerprint", "path"}:
        _fail(code)
    byte_length = document["byte_length"]
    if type(byte_length) is not int or byte_length < 1 or byte_length > _MAX_OUTPUT:
        _fail(code)
    return MappingReference(
        _text(document["path"], code),
        byte_length,
        _fingerprint(document["fingerprint"], code),
    )


@dataclass(frozen=True, slots=True)
class SchedulerRecoveryCommandResult:
    """Bounded command output with stderr retained only for disposal."""

    exit_code: int
    stdout: bytes
    stderr: bytes

    def __post_init__(self) -> None:
        """Reject coerced or unbounded process results."""
        if (
            type(self.exit_code) is not int
            or type(self.stdout) is not bytes
            or type(self.stderr) is not bytes
            or len(self.stdout) > _MAX_OUTPUT
            or len(self.stderr) > _MAX_OUTPUT
        ):
            _fail("LIVE_SCHEDULER_RECOVERY_COMMAND_RESULT_INVALID")


class SchedulerRecoveryCommandRunner(Protocol):
    """Run one exact helper argv without a shell."""

    def run(self, argv: tuple[str, ...]) -> SchedulerRecoveryCommandResult:
        """Return bounded sanitized process output."""
        ...


@dataclass(frozen=True, slots=True)
class SubprocessSchedulerRecoveryCommandRunner:
    """Concrete fixed-protocol subprocess boundary."""

    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        """Keep the privileged operation finite."""
        if (
            type(self.timeout_seconds) is not int
            or not 1 <= self.timeout_seconds <= _MAX_TIMEOUT_SECONDS
        ):
            _fail("LIVE_SCHEDULER_RECOVERY_COMMAND_RUNNER_INVALID")

    def run(self, argv: tuple[str, ...]) -> SchedulerRecoveryCommandResult:
        """Run only the repository's exact helper protocol."""
        if (
            type(argv) is not tuple
            or len(argv) != 2 + (2 * len(_COMMAND_FLAGS))
            or argv[0] != str(_HELPER)
            or argv[1] not in {"reconcile-readback", "replace-and-readback"}
            or argv[2::2] != _COMMAND_FLAGS
            or any(
                type(item) is not str or not item.isascii() or not item.isprintable()
                for item in argv
            )
        ):
            _fail("LIVE_SCHEDULER_RECOVERY_COMMAND_INVALID")
        try:
            completed = subprocess.run(  # noqa: S603
                argv,
                check=False,
                capture_output=True,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
                shell=False,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as error:
            message = "LIVE_SCHEDULER_RECOVERY_COMMAND_FAILED"
            raise LiveRecoveryExecutionError(message) from error
        return SchedulerRecoveryCommandResult(
            completed.returncode,
            completed.stdout[:_MAX_OUTPUT],
            completed.stderr[:_MAX_OUTPUT],
        )


@dataclass(frozen=True, slots=True)
class _SchedulerPlan:
    plan_fingerprint: str
    request_fingerprint: str
    role: str
    direction: str
    hubs: tuple[str, ...]
    metadata: MappingReference
    checkpoint: MappingReference
    checkpoint_fingerprint: str
    lost_instance: str
    replacement_instance: str
    old_lineage: str
    recovery_lineage: str
    credential: SealedCredentialReference


def _step_facts(step: LiveRecoveryStep) -> tuple[str, str]:
    match step:
        case LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD:
            return "GENERAL", "FORWARD"
        case LiveRecoveryStep.SCHEDULER_GENERAL_REVERSE:
            return "GENERAL", "REVERSE"
        case LiveRecoveryStep.SCHEDULER_PROMOTION_FORWARD:
            return "PROMOTION", "FORWARD"
        case LiveRecoveryStep.SCHEDULER_PROMOTION_REVERSE:
            return "PROMOTION", "REVERSE"
        case _:
            _fail("LIVE_SCHEDULER_RECOVERY_STEP_INVALID")


def _credential(
    credentials: tuple[SealedCredentialReference, ...], role: str
) -> SealedCredentialReference:
    credential_id = f"SCHEDULER_{role}_RECOVERY_ADMIN"
    matches = [item for item in credentials if item.credential_id == credential_id]
    if len(matches) != 1:
        _fail("LIVE_SCHEDULER_RECOVERY_CREDENTIAL_INVALID")
    credential = matches[0]
    path = PurePosixPath(credential.sealed_path)
    if credential.sealed_path != path.as_posix():
        _fail("LIVE_SCHEDULER_RECOVERY_CREDENTIAL_INVALID")
    return credential


def _scheduler_plan(  # noqa: C901, PLR0912, PLR0915
    step: LiveRecoveryStep,
    plan: object,
    credentials: tuple[SealedCredentialReference, ...],
) -> _SchedulerPlan:
    code = "LIVE_SCHEDULER_RECOVERY_PLAN_INVALID"
    if type(plan) is not dict:
        _fail(code)
    root = cast("dict[str, object]", plan)
    plan_fingerprint = _fingerprint(root.get("fingerprint"), code)
    request_fingerprint = _fingerprint(root.get("request_fingerprint"), code)
    operation_id = _identity(root.get("operation_id"), code)
    role, direction = _step_facts(step)
    if _ROLE.fullmatch(role) is None or _DIRECTION.fullmatch(direction) is None:
        _fail(code)
    scheduler_raw = root.get("scheduler")
    inputs_raw = root.get("input_references")
    steps_raw = root.get("steps")
    if (
        type(scheduler_raw) is not list
        or type(inputs_raw) is not dict
        or type(steps_raw) is not list
    ):
        _fail(code)
    scheduler_rows = [
        cast("dict[str, object]", item)
        for item in cast("list[object]", scheduler_raw)
        if type(item) is dict and cast("dict[str, object]", item).get("role") == role
    ]
    if len(scheduler_rows) != 1 or set(scheduler_rows[0]) != {"hubs", "role"}:
        _fail(code)
    hubs_raw = scheduler_rows[0]["hubs"]
    if type(hubs_raw) is not list:
        _fail(code)
    hubs = tuple(_identity(item, code) for item in cast("list[object]", hubs_raw))
    if not hubs or hubs != tuple(sorted(set(hubs))):
        _fail(code)
    inputs = cast("dict[str, object]", inputs_raw)
    stem = role.casefold()
    metadata = _mapping_reference(inputs.get(f"scheduler_{stem}"), code)
    checkpoint = _mapping_reference(inputs.get(f"scheduler_{stem}_checkpoint"), code)
    metadata_document = _canonical_document(_read_exact(metadata.path, metadata, code), code)
    checkpoint_bytes = _read_exact(checkpoint.path, checkpoint, code)
    if set(metadata_document) != {
        "checkpoint_fingerprint",
        "hubs",
        "lost_instance_identity",
        "old_lineage_identity",
        "request_fingerprint",
        "role",
        "schema",
    }:
        _fail(code)
    if (
        metadata_document["role"] != role
        or metadata_document["request_fingerprint"] != request_fingerprint
        or metadata_document["hubs"] != list(hubs)
        or metadata_document["checkpoint_fingerprint"]
        != f"sha256:{sha256(checkpoint_bytes).hexdigest()}"
    ):
        _fail(code)
    initial_lost = _identity(metadata_document["lost_instance_identity"], code)
    initial_lineage = _identity(metadata_document["old_lineage_identity"], code)
    step_targets: dict[str, str] = {}
    for raw_step in cast("list[object]", steps_raw):
        if type(raw_step) is not dict:
            _fail(code)
        typed_step = cast("dict[str, object]", raw_step)
        if set(typed_step) != {"step", "target_identity"}:
            _fail(code)
        step_targets[_text(typed_step["step"], code)] = _identity(
            typed_step["target_identity"], code
        )
    forward_name = f"SCHEDULER_{role}_FORWARD"
    reverse_name = f"SCHEDULER_{role}_REVERSE"
    try:
        forward_instance = step_targets[forward_name]
        reverse_instance = step_targets[reverse_name]
    except KeyError as error:
        raise LiveRecoveryExecutionError(code) from error
    forward_lineage = _derived_identity(
        operation_id, request_fingerprint, role, "FORWARD", "lineage"
    )
    if direction == "FORWARD":
        lost_instance, old_lineage = initial_lost, initial_lineage
        replacement_instance, recovery_lineage = forward_instance, forward_lineage
    else:
        lost_instance, old_lineage = forward_instance, forward_lineage
        replacement_instance = reverse_instance
        recovery_lineage = _derived_identity(
            operation_id, request_fingerprint, role, "REVERSE", "lineage"
        )
    expected_target = step_targets.get(step.value)
    if expected_target != replacement_instance:
        _fail(code)
    return _SchedulerPlan(
        plan_fingerprint,
        request_fingerprint,
        role,
        direction,
        hubs,
        metadata,
        checkpoint,
        _fingerprint(metadata_document["checkpoint_fingerprint"], code),
        lost_instance,
        replacement_instance,
        old_lineage,
        recovery_lineage,
        _credential(credentials, role),
    )


def _derived_identity(*parts: str) -> str:
    return f"r_{sha256('|'.join(parts).encode('ascii')).hexdigest()[:32]}"


def _command(mode: str, facts: _SchedulerPlan) -> tuple[str, ...]:
    return (
        str(_HELPER),
        mode,
        "--plan-fingerprint",
        facts.plan_fingerprint,
        "--request-fingerprint",
        facts.request_fingerprint,
        "--role",
        facts.role,
        "--direction",
        facts.direction,
        "--snapshot-metadata",
        facts.metadata.path,
        "--snapshot-fingerprint",
        facts.metadata.fingerprint,
        "--checkpoint",
        facts.checkpoint.path,
        "--checkpoint-fingerprint",
        facts.checkpoint_fingerprint,
        "--lost-instance",
        facts.lost_instance,
        "--replacement-instance",
        facts.replacement_instance,
        "--old-lineage",
        facts.old_lineage,
        "--recovery-lineage",
        facts.recovery_lineage,
        "--credential-file",
        facts.credential.sealed_path,
        "--credential-fingerprint",
        facts.credential.fingerprint,
    )


def _reference(value: object, code: str) -> dict[str, str]:
    if type(value) is not dict:
        _fail(code)
    document = cast("dict[str, object]", value)
    if set(document) != {"evidence_id", "fingerprint"}:
        _fail(code)
    return {
        "evidence_id": _identity(document["evidence_id"], code),
        "fingerprint": _fingerprint(document["fingerprint"], code),
    }


def _receipt(raw: bytes, step: LiveRecoveryStep, facts: _SchedulerPlan) -> LiveRecoveryStepReceipt:
    code = "LIVE_SCHEDULER_RECOVERY_READBACK_INVALID"
    document = _sealed_document(raw, _READBACK_SCHEMA, code)
    raw_effects = document.get("effect_reconciliation_receipts")
    if type(raw_effects) is not list:
        _fail(code)
    effects = [_reference(item, code) for item in cast("list[object]", raw_effects)]
    if not effects or effects != sorted(effects, key=lambda item: item["evidence_id"]):
        _fail(code)
    expected: dict[str, object] = {
        "checkpoint_fingerprint": facts.checkpoint_fingerprint,
        "direction": facts.direction,
        "effect_reconciliation_receipts": effects,
        "hubs": list(facts.hubs),
        "lost_instance_identity": facts.lost_instance,
        "old_lineage_fence_receipt": _reference(document.get("old_lineage_fence_receipt"), code),
        "old_lineage_identity": facts.old_lineage,
        "old_lineage_resumption_denied_receipt": _reference(
            document.get("old_lineage_resumption_denied_receipt"), code
        ),
        "plan_fingerprint": facts.plan_fingerprint,
        "recovery_lineage_identity": facts.recovery_lineage,
        "replacement_instance_identity": facts.replacement_instance,
        "replacement_start_result_receipt": _reference(
            document.get("replacement_start_result_receipt"), code
        ),
        "request_fingerprint": facts.request_fingerprint,
        "role": facts.role,
        "schema": _READBACK_SCHEMA,
    }
    comparison = dict(document)
    comparison.pop("fingerprint", None)
    if comparison != expected:
        _fail(code)
    proof_fingerprint = _digest(expected)
    return LiveRecoveryStepReceipt(
        step,
        facts.plan_fingerprint,
        facts.replacement_instance,
        proof_fingerprint,
        proof_fingerprint,
    )


def _not_found(raw: bytes, facts: _SchedulerPlan) -> bool:
    document = _sealed_document(raw, _NOT_FOUND_SCHEMA, "LIVE_SCHEDULER_RECOVERY_READBACK_INVALID")
    return document == {
        "direction": facts.direction,
        "fingerprint": document["fingerprint"],
        "plan_fingerprint": facts.plan_fingerprint,
        "replacement_instance_identity": facts.replacement_instance,
        "role": facts.role,
        "schema": _NOT_FOUND_SCHEMA,
    }


class SchedulerLiveRecoveryPort:
    """Create-or-match four exact Scheduler replacement legs through one helper."""

    def __init__(
        self,
        runner: SchedulerRecoveryCommandRunner,
        *,
        helper_path: Path = _HELPER,
        credential_verifier: SealedCredentialVerifier | None = None,
    ) -> None:
        """Bind the fixed helper and a credential verifier without effects."""
        if helper_path != _HELPER:
            _fail("LIVE_SCHEDULER_RECOVERY_HELPER_INVALID")
        self._runner = runner
        self._helper = helper_path
        self._credential_verifier = credential_verifier or FilesystemSealedCredentialVerifier()

    def reconcile(
        self,
        step: LiveRecoveryStep,
        plan: object,
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt | None:
        """Reconcile an exact retained replacement without changing Scheduler state."""
        facts = self._inputs(step, plan, credentials)
        result = self._runner.run(_command("reconcile-readback", facts))
        if result.exit_code == 3 and _not_found(result.stdout, facts):  # noqa: PLR2004
            return None
        if result.exit_code != 0:
            _fail("LIVE_SCHEDULER_RECOVERY_COMMAND_FAILED")
        return _receipt(result.stdout, step, facts)

    def execute(
        self,
        step: LiveRecoveryStep,
        plan: object,
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt:
        """Replace one exact role/direction and require complete semantic read-back."""
        facts = self._inputs(step, plan, credentials)
        result = self._runner.run(_command("replace-and-readback", facts))
        if result.exit_code != 0:
            _fail("LIVE_SCHEDULER_RECOVERY_COMMAND_FAILED")
        return _receipt(result.stdout, step, facts)

    def _inputs(
        self,
        step: LiveRecoveryStep,
        plan: object,
        credentials: tuple[SealedCredentialReference, ...],
    ) -> _SchedulerPlan:
        facts = _scheduler_plan(step, plan, credentials)
        if not self._credential_verifier.verify(facts.credential):
            _fail("LIVE_SCHEDULER_RECOVERY_CREDENTIAL_DRIFT")
        return facts
