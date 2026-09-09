"""Plan, authorize, execute once, and reconcile one exact local host reboot."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Never, Protocol

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

from tools.v1_poc_collect_host_facts import (
    host_facts_document,
    parse_host_facts_output_bytes,
    validated_complete_host_facts,
)

_PLAN_SCHEMA = "asklegal.hk-v1-host-reboot-plan/v1"
_AUTHORITY_SCHEMA = "asklegal.hk-v1-host-reboot-authority/v1"
_STATE_SCHEMA = "asklegal.hk-v1-host-reboot-state/v1"
_VERSION = "1.0.0"
_ACTION = ("/usr/bin/systemctl", "reboot", "--no-wall")
_FP = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPERATION_ID = re.compile(r"^rbt_[0-9a-f]{48}$")
_AUTHORITY_ID = re.compile(r"^auth_[0-9a-f]{48}$")
_SUBJECT = re.compile(r"^[a-z][a-z0-9._-]{2,127}$")
_MAX_BYTES = 10_000_000


class HostRebootError(ValueError):
    """One exact plan, authority, state, command, or host-readback failure."""


@dataclass(frozen=True, slots=True)
class RebootCommandResult:
    """Sanitized fixed-command result."""

    returncode: int
    stdout: str
    stderr: str


class RebootRunner(Protocol):
    """Closed one-command reboot boundary."""

    def run(self, argv: tuple[str, ...]) -> RebootCommandResult:
        """Run the already frozen reboot argv."""
        ...


@dataclass(frozen=True, slots=True)
class HostRebootPlan:
    """One immutable reboot subject and its pre/post readback paths."""

    operation_id: str
    pre_host_facts: bytes
    pre_host_facts_fingerprint: str
    pre_boot_id_fingerprint: str
    post_host_facts_path: Path
    state_path: Path
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HostRebootAuthority:
    """One named, expiring, exact reboot authorization."""

    authority_id: str
    signer_subject: str
    authorized_at: datetime
    expires_at: datetime
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HostRebootReadback:
    """Owner-parsed pre/post identities and bindings for one completed reboot."""

    operation_id: str
    pre_boot_id_fingerprint: str
    post_boot_id_fingerprint: str
    pre_host_facts_fingerprint: str
    post_host_facts_fingerprint: str
    state_fingerprint: str


def _fail(code: str) -> Never:
    raise HostRebootError(code)


def _fingerprint(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


def _seal(body: dict[str, JsonValue]) -> bytes:
    unsigned = canonicalize(checked_json_value(body))
    return canonicalize(checked_json_value({**body, "fingerprint": _fingerprint(unsigned)}))


def _object(value: object, code: str) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    if not isinstance(parsed, dict):
        _fail(code)
    return parsed


def _document(content: bytes, code: str) -> dict[str, JsonValue]:
    if type(content) is not bytes or not content or len(content) > _MAX_BYTES:
        _fail(code)
    try:
        value = parse_json_bytes(content, max_bytes=_MAX_BYTES)
    except (RuntimeError, ValueError) as error:
        raise HostRebootError(code) from error
    if not isinstance(value, dict) or canonicalize(value) != content:
        _fail(code)
    return value


def _safe_path(path: Path, code: str, *, existing_file: bool = False) -> Path:
    if not path.is_absolute() or path == Path(path.anchor) or path != path.resolve(strict=False):
        _fail(code)
    current = path
    while current != Path(current.anchor):
        if current.is_symlink():
            _fail(code)
        current = current.parent
    if existing_file and not path.is_file():
        _fail(code)
    return path


def _host(content: bytes, code: str) -> tuple[str, str]:
    try:
        envelope = parse_host_facts_output_bytes(content)
        legacy = validated_complete_host_facts(envelope)
        document = host_facts_document(envelope)
    except (TypeError, ValueError) as error:
        raise HostRebootError(code) from error
    kernel = _object(legacy.get("kernel"), code)
    boot = kernel.get("boot_id_fingerprint")
    if _FP.fullmatch(str(boot)) is None:
        _fail(code)
    return str(boot), _fingerprint(canonicalize(checked_json_value(document)))


def _plan_body(plan: HostRebootPlan) -> dict[str, JsonValue]:
    return {
        "schema_id": _PLAN_SCHEMA,
        "schema_version": _VERSION,
        "mode": "PLAN_ONLY",
        "operation_id": plan.operation_id,
        "action": list(_ACTION),
        "pre_host_facts_hex": plan.pre_host_facts.hex(),
        "pre_host_facts_fingerprint": plan.pre_host_facts_fingerprint,
        "pre_boot_id_fingerprint": plan.pre_boot_id_fingerprint,
        "post_host_facts_path": str(plan.post_host_facts_path),
        "state_path": str(plan.state_path),
        "effects": ["HOST_REBOOT"],
        "prohibited_effects": [
            "SOURCE_CALL",
            "PROVIDER_CALL",
            "INDEX_DELETE",
            "ROUTING_MUTATION",
        ],
    }


def build_host_reboot_plan(
    pre_host_facts: bytes,
    post_host_facts_path: Path,
    state_path: Path,
) -> HostRebootPlan:
    """Freeze one plan from the exact complete pre-reboot collector envelope."""
    pre_boot, semantic_fingerprint = _host(pre_host_facts, "HOST_REBOOT_PRE_FACTS_INVALID")
    _safe_path(post_host_facts_path, "HOST_REBOOT_PATH_INVALID")
    _safe_path(state_path, "HOST_REBOOT_PATH_INVALID")
    if post_host_facts_path == state_path:
        _fail("HOST_REBOOT_PATH_INVALID")
    identity = canonicalize(
        checked_json_value(
            {
                "pre_host_facts_fingerprint": semantic_fingerprint,
                "post_host_facts_path": str(post_host_facts_path),
                "state_path": str(state_path),
            }
        )
    )
    operation_id = "rbt_" + sha256(identity).hexdigest()[:48]
    provisional = HostRebootPlan(
        operation_id,
        pre_host_facts,
        semantic_fingerprint,
        pre_boot,
        post_host_facts_path,
        state_path,
        "",
    )
    fingerprint = _fingerprint(canonicalize(checked_json_value(_plan_body(provisional))))
    return HostRebootPlan(
        operation_id,
        pre_host_facts,
        semantic_fingerprint,
        pre_boot,
        post_host_facts_path,
        state_path,
        fingerprint,
    )


def host_reboot_plan_bytes(plan: HostRebootPlan) -> bytes:
    """Serialize and internally revalidate a reboot plan."""
    body = _plan_body(plan)
    if _fingerprint(canonicalize(checked_json_value(body))) != plan.fingerprint:
        _fail("HOST_REBOOT_PLAN_INVALID")
    return canonicalize(checked_json_value({**body, "fingerprint": plan.fingerprint}))


def _parse_plan(content: bytes) -> HostRebootPlan:
    code = "HOST_REBOOT_PLAN_INVALID"
    document = _document(content, code)
    expected = {
        "action",
        "effects",
        "fingerprint",
        "mode",
        "operation_id",
        "post_host_facts_path",
        "pre_boot_id_fingerprint",
        "pre_host_facts_fingerprint",
        "pre_host_facts_hex",
        "prohibited_effects",
        "schema_id",
        "schema_version",
        "state_path",
    }
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    encoded = document.get("pre_host_facts_hex")
    if type(encoded) is not str:
        _fail(code)
    try:
        pre_host_facts = bytes.fromhex(encoded)
    except ValueError as error:
        raise HostRebootError(code) from error
    post_path = Path(str(document.get("post_host_facts_path")))
    state_path = Path(str(document.get("state_path")))
    pre_boot, semantic_fingerprint = _host(pre_host_facts, code)
    if (
        frozenset(document) != frozenset(expected)
        or document.get("schema_id") != _PLAN_SCHEMA
        or document.get("schema_version") != _VERSION
        or document.get("mode") != "PLAN_ONLY"
        or _OPERATION_ID.fullmatch(str(document.get("operation_id"))) is None
        or document.get("action") != list(_ACTION)
        or document.get("effects") != ["HOST_REBOOT"]
        or document.get("prohibited_effects")
        != ["SOURCE_CALL", "PROVIDER_CALL", "INDEX_DELETE", "ROUTING_MUTATION"]
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
        or document.get("pre_boot_id_fingerprint") != pre_boot
        or document.get("pre_host_facts_fingerprint") != semantic_fingerprint
        or post_path == state_path
    ):
        _fail(code)
    _safe_path(post_path, code)
    _safe_path(state_path, code)
    plan = HostRebootPlan(
        str(document["operation_id"]),
        pre_host_facts,
        semantic_fingerprint,
        pre_boot,
        post_path,
        state_path,
        str(supplied),
    )
    if host_reboot_plan_bytes(plan) != content:
        _fail(code)
    return plan


def build_host_reboot_authority(
    plan: HostRebootPlan,
    *,
    authority_id: str,
    signer_subject: str,
    authorized_at: datetime,
    expires_at: datetime,
) -> bytes:
    """Build the detached exact authority that a named operator must approve."""
    if (
        _AUTHORITY_ID.fullmatch(authority_id) is None
        or _SUBJECT.fullmatch(signer_subject) is None
        or authorized_at.tzinfo is None
        or expires_at.tzinfo is None
        or authorized_at >= expires_at
    ):
        _fail("HOST_REBOOT_AUTHORITY_INVALID")
    return _seal(
        {
            "schema_id": _AUTHORITY_SCHEMA,
            "schema_version": _VERSION,
            "action": "REBOOT_HOST_ONCE",
            "authority_id": authority_id,
            "authorized_at": authorized_at.astimezone(UTC).isoformat(),
            "expires_at": expires_at.astimezone(UTC).isoformat(),
            "operation_id": plan.operation_id,
            "plan_fingerprint": plan.fingerprint,
            "post_host_facts_path": str(plan.post_host_facts_path),
            "pre_boot_id_fingerprint": plan.pre_boot_id_fingerprint,
            "signer_subject": signer_subject,
            "state_path": str(plan.state_path),
        }
    )


def _parse_time(value: object, code: str) -> datetime:
    if type(value) is not str:
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise HostRebootError(code) from error
    if parsed.tzinfo is None:
        _fail(code)
    return parsed.astimezone(UTC)


def _parse_authority(content: bytes, plan: HostRebootPlan) -> HostRebootAuthority:
    code = "HOST_REBOOT_AUTHORITY_INVALID"
    document = _document(content, code)
    expected = {
        "action",
        "authority_id",
        "authorized_at",
        "expires_at",
        "fingerprint",
        "operation_id",
        "plan_fingerprint",
        "post_host_facts_path",
        "pre_boot_id_fingerprint",
        "schema_id",
        "schema_version",
        "signer_subject",
        "state_path",
    }
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    authorized_at = _parse_time(document.get("authorized_at"), code)
    expires_at = _parse_time(document.get("expires_at"), code)
    authority_id = str(document.get("authority_id"))
    subject = str(document.get("signer_subject"))
    if (
        frozenset(document) != frozenset(expected)
        or document.get("schema_id") != _AUTHORITY_SCHEMA
        or document.get("schema_version") != _VERSION
        or document.get("action") != "REBOOT_HOST_ONCE"
        or _AUTHORITY_ID.fullmatch(authority_id) is None
        or _SUBJECT.fullmatch(subject) is None
        or authorized_at >= expires_at
        or document.get("operation_id") != plan.operation_id
        or document.get("plan_fingerprint") != plan.fingerprint
        or document.get("pre_boot_id_fingerprint") != plan.pre_boot_id_fingerprint
        or document.get("post_host_facts_path") != str(plan.post_host_facts_path)
        or document.get("state_path") != str(plan.state_path)
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
    ):
        _fail(code)
    return HostRebootAuthority(authority_id, subject, authorized_at, expires_at, str(supplied))


def _state_body(
    plan_content: bytes,
    authority_content: bytes,
    phase: str,
    *,
    command_receipt: dict[str, JsonValue] | None,
    post_host_facts: bytes | None,
) -> dict[str, JsonValue]:
    plan = _parse_plan(plan_content)
    authority = _parse_authority(authority_content, plan)
    post_boot: str | None = None
    post_fingerprint: str | None = None
    post_hex: str | None = None
    if post_host_facts is not None:
        post_boot, post_fingerprint = _host(post_host_facts, "HOST_REBOOT_POST_FACTS_INVALID")
        post_hex = post_host_facts.hex()
    return {
        "schema_id": _STATE_SCHEMA,
        "schema_version": _VERSION,
        "operation_id": plan.operation_id,
        "phase": phase,
        "complete": phase == "COMPLETE",
        "plan_fingerprint": plan.fingerprint,
        "plan_hex": plan_content.hex(),
        "authority_fingerprint": authority.fingerprint,
        "authority_id": authority.authority_id,
        "authority_hex": authority_content.hex(),
        "pre_boot_id_fingerprint": plan.pre_boot_id_fingerprint,
        "post_boot_id_fingerprint": post_boot,
        "post_host_facts_fingerprint": post_fingerprint,
        "post_host_facts_hex": post_hex,
        "command_receipt": command_receipt,
        "effects": ["HOST_REBOOT"],
        "provider_called": False,
        "source_called": False,
        "index_deleted": False,
        "routing_mutated": False,
    }


def _write_state(path: Path, body: dict[str, JsonValue]) -> bytes:
    content = _seal(body)
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.is_symlink() or (parent.stat().st_mode & 0o077) != 0:
        _fail("HOST_REBOOT_STATE_INVALID")
    temporary = parent / f".{path.name}.{token_hex(8)}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        os.write(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.replace(path)
    if path.read_bytes() != content:
        _fail("HOST_REBOOT_STATE_INVALID")
    return content


def _validate_state_receipt(value: object, phase: object, code: str) -> None:
    if phase == "REQUESTED":
        if value is not None:
            _fail(code)
        return
    if phase not in {"AWAITING_REBOOT", "FAILED", "COMPLETE"}:
        return
    row = _object(value, code)
    if (
        frozenset(row)
        != frozenset({"argv", "outcome", "returncode", "stderr_fingerprint", "stdout_fingerprint"})
        or row.get("argv") != list(_ACTION)
        or row.get("outcome") not in {"COMMAND_RETURNED", "ADOPTED_FROM_CHANGED_BOOT"}
    ):
        _fail(code)
    if row.get("outcome") == "COMMAND_RETURNED":
        if (
            type(row.get("returncode")) is not int
            or _FP.fullmatch(str(row.get("stderr_fingerprint"))) is None
            or _FP.fullmatch(str(row.get("stdout_fingerprint"))) is None
        ):
            _fail(code)
    elif any(
        row.get(field) is not None
        for field in ("returncode", "stderr_fingerprint", "stdout_fingerprint")
    ):
        _fail(code)


def _validate_state_post_facts(
    document: dict[str, JsonValue], phase: object, plan: HostRebootPlan, code: str
) -> None:
    post_hex = document.get("post_host_facts_hex")
    if phase != "COMPLETE":
        if any(
            document.get(field) is not None
            for field in (
                "post_boot_id_fingerprint",
                "post_host_facts_fingerprint",
                "post_host_facts_hex",
            )
        ):
            _fail(code)
        return
    if type(post_hex) is not str:
        _fail(code)
    try:
        post = bytes.fromhex(post_hex)
    except ValueError as error:
        raise HostRebootError(code) from error
    post_boot, post_fp = _host(post, code)
    if (
        post_boot == plan.pre_boot_id_fingerprint
        or document.get("post_boot_id_fingerprint") != post_boot
        or document.get("post_host_facts_fingerprint") != post_fp
    ):
        _fail(code)


def _parse_state(
    content: bytes, plan: HostRebootPlan, authority: HostRebootAuthority
) -> dict[str, JsonValue]:
    code = "HOST_REBOOT_STATE_INVALID"
    document = _document(content, code)
    expected = {
        "authority_fingerprint",
        "authority_hex",
        "authority_id",
        "command_receipt",
        "complete",
        "effects",
        "fingerprint",
        "index_deleted",
        "operation_id",
        "phase",
        "plan_fingerprint",
        "plan_hex",
        "post_boot_id_fingerprint",
        "post_host_facts_fingerprint",
        "post_host_facts_hex",
        "pre_boot_id_fingerprint",
        "provider_called",
        "routing_mutated",
        "schema_id",
        "schema_version",
        "source_called",
    }
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    phase = document.get("phase")
    if (
        frozenset(document) != frozenset(expected)
        or document.get("schema_id") != _STATE_SCHEMA
        or document.get("schema_version") != _VERSION
        or phase not in {"REQUESTED", "AWAITING_REBOOT", "FAILED", "COMPLETE"}
        or document.get("complete") is not (phase == "COMPLETE")
        or document.get("operation_id") != plan.operation_id
        or document.get("plan_fingerprint") != plan.fingerprint
        or document.get("authority_fingerprint") != authority.fingerprint
        or document.get("authority_id") != authority.authority_id
        or document.get("pre_boot_id_fingerprint") != plan.pre_boot_id_fingerprint
        or document.get("effects") != ["HOST_REBOOT"]
        or any(
            document.get(field) is not False
            for field in ("provider_called", "source_called", "index_deleted", "routing_mutated")
        )
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
    ):
        _fail(code)
    plan_hex = document.get("plan_hex")
    authority_hex = document.get("authority_hex")
    if type(plan_hex) is not str or type(authority_hex) is not str:
        _fail(code)
    try:
        if bytes.fromhex(plan_hex) != host_reboot_plan_bytes(plan):
            _fail(code)
        if bytes.fromhex(authority_hex) != build_host_reboot_authority(
            plan,
            authority_id=authority.authority_id,
            signer_subject=authority.signer_subject,
            authorized_at=authority.authorized_at,
            expires_at=authority.expires_at,
        ):
            _fail(code)
    except ValueError as error:
        raise HostRebootError(code) from error
    _validate_state_receipt(document.get("command_receipt"), phase, code)
    _validate_state_post_facts(document, phase, plan, code)
    return document


def parse_host_reboot_readback_details(
    content: bytes, expected_post_host_facts: bytes
) -> HostRebootReadback:
    """Revalidate and return exact owner-derived pre/post reboot identities."""
    code = "HOST_REBOOT_READBACK_INVALID"
    document = _document(content, code)
    plan_hex = document.get("plan_hex")
    authority_hex = document.get("authority_hex")
    if type(plan_hex) is not str or type(authority_hex) is not str:
        _fail(code)
    try:
        plan_content = bytes.fromhex(plan_hex)
        plan = _parse_plan(plan_content)
        authority_content = bytes.fromhex(authority_hex)
        authority = _parse_authority(authority_content, plan)
        parsed = _parse_state(content, plan, authority)
    except (HostRebootError, ValueError) as error:
        raise HostRebootError(code) from error
    if (
        parsed.get("phase") != "COMPLETE"
        or parsed.get("post_host_facts_hex") != expected_post_host_facts.hex()
    ):
        _fail(code)
    return HostRebootReadback(
        operation_id=plan.operation_id,
        pre_boot_id_fingerprint=plan.pre_boot_id_fingerprint,
        post_boot_id_fingerprint=str(parsed["post_boot_id_fingerprint"]),
        pre_host_facts_fingerprint=plan.pre_host_facts_fingerprint,
        post_host_facts_fingerprint=str(parsed["post_host_facts_fingerprint"]),
        state_fingerprint=str(parsed["fingerprint"]),
    )


def parse_host_reboot_readback(content: bytes, expected_post_host_facts: bytes) -> str:
    """Revalidate a COMPLETE reboot readback and return its post-boot identity."""
    return parse_host_reboot_readback_details(
        content, expected_post_host_facts
    ).post_boot_id_fingerprint


def _read(path: Path, code: str) -> bytes:
    _safe_path(path, code, existing_file=True)
    try:
        content = path.read_bytes()
    except OSError as error:
        raise HostRebootError(code) from error
    if len(content) > _MAX_BYTES:
        _fail(code)
    return content


def run_host_reboot(
    plan_content: bytes,
    authority_content: bytes,
    *,
    now: datetime,
    runner: RebootRunner,
) -> bytes:
    """Issue at most one reboot, or reconcile its exact post-boot facts."""
    plan = _parse_plan(plan_content)
    authority = _parse_authority(authority_content, plan)
    if now.tzinfo is None:
        _fail("HOST_REBOOT_TIME_INVALID")
    observed_now = now.astimezone(UTC)
    plan.state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if plan.state_path.parent.is_symlink() or plan.state_path.parent.stat().st_mode & 0o077 != 0:
        _fail("HOST_REBOOT_STATE_INVALID")
    with exclusive_local_state_lock(plan.state_path):
        if plan.state_path.exists():
            state_content = _read(plan.state_path, "HOST_REBOOT_STATE_INVALID")
            state = _parse_state(state_content, plan, authority)
            if state.get("phase") in {"FAILED", "COMPLETE"}:
                return state_content
            if plan.post_host_facts_path.is_file():
                post = _read(plan.post_host_facts_path, "HOST_REBOOT_POST_FACTS_INVALID")
                post_boot, _post_fp = _host(post, "HOST_REBOOT_POST_FACTS_INVALID")
                if post_boot != plan.pre_boot_id_fingerprint:
                    retained_receipt = state.get("command_receipt")
                    if retained_receipt is not None:
                        command_receipt = _object(retained_receipt, "HOST_REBOOT_STATE_INVALID")
                    else:
                        command_receipt: dict[str, JsonValue] = {
                            "argv": list(_ACTION),
                            "outcome": "ADOPTED_FROM_CHANGED_BOOT",
                            "returncode": None,
                            "stdout_fingerprint": None,
                            "stderr_fingerprint": None,
                        }
                    return _write_state(
                        plan.state_path,
                        _state_body(
                            plan_content,
                            authority_content,
                            "COMPLETE",
                            command_receipt=command_receipt,
                            post_host_facts=post,
                        ),
                    )
            return state_content
        if not (authority.authorized_at <= observed_now <= authority.expires_at):
            _fail("HOST_REBOOT_AUTHORITY_EXPIRED")
        _write_state(
            plan.state_path,
            _state_body(
                plan_content,
                authority_content,
                "REQUESTED",
                command_receipt=None,
                post_host_facts=None,
            ),
        )
        result = runner.run(_ACTION)
        receipt: dict[str, JsonValue] = {
            "argv": list(_ACTION),
            "outcome": "COMMAND_RETURNED",
            "returncode": result.returncode,
            "stdout_fingerprint": _fingerprint(result.stdout[-100_000:].encode()),
            "stderr_fingerprint": _fingerprint(result.stderr[-100_000:].encode()),
        }
        phase = "AWAITING_REBOOT" if result.returncode == 0 else "FAILED"
        return _write_state(
            plan.state_path,
            _state_body(
                plan_content,
                authority_content,
                phase,
                command_receipt=receipt,
                post_host_facts=None,
            ),
        )


class SystemctlRebootRunner:
    """Production fixed-argv reboot adapter."""

    def run(self, argv: tuple[str, ...]) -> RebootCommandResult:
        """Invoke only the frozen systemctl reboot command without a shell."""
        if argv != _ACTION:
            _fail("HOST_REBOOT_COMMAND_INVALID")
        completed = subprocess.run(  # noqa: S603 - argv is exact and checked above.
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return RebootCommandResult(completed.returncode, completed.stdout, completed.stderr)


def _write_output(path: Path, content: bytes) -> None:
    _safe_path(path, "HOST_REBOOT_OUTPUT_INVALID")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        os.write(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main(argv: Sequence[str] | None = None) -> int:
    """Plan by default; execute only with an exact detached authority and flag."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    planning = subparsers.add_parser("plan")
    planning.add_argument("--pre-host-facts", type=Path, required=True)
    planning.add_argument("--post-host-facts", type=Path, required=True)
    planning.add_argument("--state", type=Path, required=True)
    planning.add_argument("--output", type=Path, required=True)
    executing = subparsers.add_parser("execute")
    executing.add_argument("--plan", type=Path, required=True)
    executing.add_argument("--authority", type=Path, required=True)
    executing.add_argument("--execute", action="store_true", required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "plan":
            pre = _read(arguments.pre_host_facts, "HOST_REBOOT_PRE_FACTS_INVALID")
            plan = build_host_reboot_plan(pre, arguments.post_host_facts, arguments.state)
            _write_output(arguments.output, host_reboot_plan_bytes(plan))
            return 0
        result = run_host_reboot(
            _read(arguments.plan, "HOST_REBOOT_PLAN_INVALID"),
            _read(arguments.authority, "HOST_REBOOT_AUTHORITY_INVALID"),
            now=datetime.now(UTC),
            runner=SystemctlRebootRunner(),
        )
        return 0 if _document(result, "HOST_REBOOT_STATE_INVALID").get("phase") == "COMPLETE" else 2
    except HostRebootError as error:
        sys.stderr.write(f"{error}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
