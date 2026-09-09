"""Issue one exact host-apply authority from the user's standing authorization."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path
from secrets import token_hex
from typing import cast

from asklegal_contracts import parse_json_bytes

from tools.hk_v1_host_apply import HostApplyError, build_host_apply_authority

_MAX_BYTES = 5_000_000
_PRIVATE_MODE = 0o600
_OUTPUT_INVALID = "HOST_APPLY_AUTHORITY_OUTPUT_INVALID"
_OUTPUT_DRIFT = "HOST_APPLY_AUTHORITY_OUTPUT_DRIFT"
_AUTHORITY_ID_INVALID = "HOST_APPLY_AUTHORITY_ID_INVALID"
_AUTHORITY_ID = re.compile(r"^auth_[0-9a-f]{48}$")


class HostApplyAuthorityIssueError(ValueError):
    """One sanitized authority-issuance failure."""


def issue_host_apply_authority(
    *,
    plan_path: Path,
    repository_root: Path,
    state_root: Path,
    authority_id: str,
) -> bytes:
    """Build authority bytes only after the owning host-plan parser succeeds."""
    if _AUTHORITY_ID.fullmatch(authority_id) is None:
        raise HostApplyAuthorityIssueError(_AUTHORITY_ID_INVALID)
    try:
        return build_host_apply_authority(
            plan_path,
            repository_root,
            state_root,
            authority_id=authority_id,
        )
    except HostApplyError as error:
        raise HostApplyAuthorityIssueError(str(error)) from error
    except ValueError as error:
        raise HostApplyAuthorityIssueError(_AUTHORITY_ID_INVALID) from error


def _write_exact(path: Path, raw: bytes) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
        raise HostApplyAuthorityIssueError(_OUTPUT_INVALID)
    if path.exists():
        if (
            not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != _PRIVATE_MODE
            or path.read_bytes() != raw
        ):
            raise HostApplyAuthorityIssueError(_OUTPUT_DRIFT)
        return
    temporary = path.parent / f".{path.name}.{token_hex(16)}.tmp"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            _PRIVATE_MODE,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    if path.read_bytes() != raw:
        raise HostApplyAuthorityIssueError(_OUTPUT_INVALID)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--authority-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write and read back one exact no-effect authority artifact."""
    arguments = _parser().parse_args(argv)
    try:
        raw = issue_host_apply_authority(
            plan_path=arguments.plan,
            repository_root=arguments.repository_root,
            state_root=arguments.state_root,
            authority_id=arguments.authority_id,
        )
        _write_exact(arguments.output, raw)
        document = cast("dict[str, object]", parse_json_bytes(raw, max_bytes=_MAX_BYTES))
    except OSError, TypeError, ValueError:
        print("HOST_APPLY_AUTHORITY_NOT_ISSUED", file=sys.stderr)  # noqa: T201
        return 2
    print(f"ISSUED_NO_EFFECT {document['fingerprint']}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
