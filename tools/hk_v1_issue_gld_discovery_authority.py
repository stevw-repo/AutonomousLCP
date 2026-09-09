"""Issue one exact local GLD contract-discovery authority from standing approval.

The receipt authorizes only a bounded, no-click observation of the registered
GLD listing route.  It cannot accept terms, submit personal data, issue a
challenge contract, or authorize the later listing-window observation.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Never

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_source_connectors import load_hk_legislation_source_register

_ENDPOINT_ID = "sep_00000000000000000000000000000000000000000000003b"
_SOURCE_ID = "HK-LEG-GLD-EGAZETTE"
_ALLOWED_PATHS = ("/challenge.js", "/en/list-of-gazette")
_MAX_BYTES = 65_536
_CYCLE_ID_LENGTH = 68
_PRIVATE_FILE_MODE = 0o600


class GldDiscoveryAuthorityError(ValueError):
    """One sanitized receipt-issuance error."""


def _fail(code: str) -> Never:
    raise GldDiscoveryAuthorityError(code)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        message = "GLD_DISCOVERY_AUTHORITY_TIME_INVALID"
        raise GldDiscoveryAuthorityError(message) from error
    if parsed.tzinfo is None or parsed.microsecond != 0:
        _fail("GLD_DISCOVERY_AUTHORITY_TIME_INVALID")
    return parsed.astimezone(UTC)


def _fingerprint(document: dict[str, JsonValue]) -> str:
    return "sha256:" + sha256(canonicalize(checked_json_value(document))).hexdigest()


def issue_gld_discovery_authority(
    *,
    cycle_id: str,
    observation_cutoff: str,
    named_authorizer: str,
    authorized_at: str,
    expires_at: str,
) -> bytes:
    """Build canonical authority bytes for one registered discovery attempt."""
    authorized = _timestamp(authorized_at)
    expiry = _timestamp(expires_at)
    cutoff = _timestamp(observation_cutoff)
    if (
        not cycle_id.startswith("cyc_")
        or len(cycle_id) != _CYCLE_ID_LENGTH
        or any(character not in "0123456789abcdef" for character in cycle_id[4:])
        or not named_authorizer
        or named_authorizer.strip() != named_authorizer
        or not authorized < expiry
        or not authorized <= datetime.now(UTC) < expiry
    ):
        _fail("GLD_DISCOVERY_AUTHORITY_INPUT_INVALID")
    register = load_hk_legislation_source_register()
    endpoint = next(item for item in register.endpoints if item.endpoint_id == _ENDPOINT_ID)
    exact_cutoff = cutoff.replace(microsecond=0).isoformat()
    attempt_material = checked_json_value(
        {"cycle_id": cycle_id, "observation_cutoff": exact_cutoff}
    )
    attempt_id = "gld-discover-" + sha256(canonicalize(attempt_material)).hexdigest()[:32]
    authorization_material = checked_json_value(
        {
            "attempt_id": attempt_id,
            "authorized_at": authorized_at,
            "named_authorizer": named_authorizer,
        }
    )
    authorization_id = "gld-auth-" + sha256(canonicalize(authorization_material)).hexdigest()[:32]
    body: dict[str, JsonValue] = {
        "admitted_host": "egazette.gld.gov.hk",
        "allowed_paths": list(_ALLOWED_PATHS),
        "attempt_id": attempt_id,
        "authorization_id": authorization_id,
        "authorized_action": "DISCOVER_GLD_CHALLENGE_CONTRACT",
        "authorized_at": authorized_at,
        "challenge_contract_fingerprint": None,
        "cycle_id": cycle_id,
        "deadline_seconds": 60,
        "discovery_observation_fingerprint": None,
        "endpoint_id": endpoint.endpoint_id,
        "endpoint_version": endpoint.version,
        "expires_at": expires_at,
        "listing_deadline_seconds": None,
        "listing_max_requests": None,
        "manifest_prefix": "poc/report/gld-contract-discovery",
        "maximum_requests": 64,
        "maximum_response_bytes": endpoint.max_bytes,
        "named_authorizer": named_authorizer,
        "object_prefix": "poc/isolation/gld-contract-discovery",
        "observation_cutoff": exact_cutoff,
        "operation_deadline_seconds": 60,
        "primary_vault": "PRIMARY",
        "register_fingerprint": register.fingerprint,
        "register_version": register.register_version,
        "rights_basis": "USER_REPORTED_LEGAL_TEAM_CLEARANCE",
        "schema_id": "asklegal.gld-challenge-authority",
        "schema_version": "1.0.0",
        "session_deadline_seconds": None,
        "session_max_attempts": None,
        "session_max_requests_per_attempt": None,
        "session_root": None,
        "source_id": _SOURCE_ID,
    }
    return canonicalize(checked_json_value({**body, "fingerprint": _fingerprint(body)}))


def write_exact(path: Path, raw: bytes) -> None:
    """Create-or-match one exact authority receipt with durable local readback."""
    if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
        _fail("GLD_DISCOVERY_AUTHORITY_OUTPUT_INVALID")
    if path.exists():
        if (
            not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != _PRIVATE_FILE_MODE
            or path.read_bytes() != raw
        ):
            _fail("GLD_DISCOVERY_AUTHORITY_OUTPUT_DRIFT")
        return
    temporary = path.parent / f".{path.name}.{token_hex(16)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        _PRIVATE_FILE_MODE,
    )
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.replace(path)
    if path.read_bytes() != raw:
        _fail("GLD_DISCOVERY_AUTHORITY_OUTPUT_INVALID")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--observation-cutoff", required=True)
    parser.add_argument("--named-authorizer", required=True)
    parser.add_argument("--authorized-at", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Issue and read back one exact authority without any source effect."""
    arguments = _parser().parse_args(argv)
    try:
        raw = issue_gld_discovery_authority(
            cycle_id=arguments.cycle_id,
            observation_cutoff=arguments.observation_cutoff,
            named_authorizer=arguments.named_authorizer,
            authorized_at=arguments.authorized_at,
            expires_at=arguments.expires_at,
        )
        write_exact(arguments.output, raw)
        parsed = parse_json_bytes(raw, max_bytes=_MAX_BYTES)
        if type(parsed) is not dict or type(parsed.get("fingerprint")) is not str:
            _fail("GLD_DISCOVERY_AUTHORITY_OUTPUT_INVALID")
    except GldDiscoveryAuthorityError as error:
        print(error, file=sys.stderr)  # noqa: T201
        return 2
    print(f"ISSUED_NO_EFFECT {parsed['fingerprint']}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
