"""Stage replacement V1 vault credentials without exposing their secrets."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from secrets import token_hex, token_urlsafe
from typing import Never, cast

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import S3AccessCredential, S3VaultError

from tools.hk_v1_rotate_credentials import required_credential_names

_APPLICATION_CREDENTIALS = {
    "vault-primary-acquisition": "asklegal-primary-acquisition",
    "vault-primary-control": "asklegal-primary-control",
    "vault-primary-processing": "asklegal-primary-processing",
    "vault-primary-promotion": "asklegal-primary-promotion",
    "vault-primary-review": "asklegal-primary-review",
    "vault-recovery-acquisition": "asklegal-recovery-acquisition",
    "vault-recovery-promotion": "asklegal-recovery-promotion",
}
_PRIMARY_ROOT_CREDENTIALS = (
    "vault-primary-root-access",
    "vault-primary-root-secret",
)
_ROTATED_CREDENTIALS = frozenset((*_APPLICATION_CREDENTIALS, *_PRIMARY_ROOT_CREDENTIALS))
_ROTATION_ID = re.compile(r"^rot_[0-9a-f]{48}$")
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_MAX_CREDENTIAL_BYTES = 32_768
_MAX_RECEIPT_BYTES = 65_536
_MAX_ROOT_PART_BYTES = 1_024
_FIRST_CONTROL_CODEPOINT = 0x20
_NON_DEPLOYED_CREDENTIAL_NAMES = frozenset({"grafana-admin"})


class VaultCredentialStagingError(ValueError):
    """One sanitized credential-staging failure."""


def _fail(code: str) -> Never:
    raise VaultCredentialStagingError(code)


def _read_regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        _fail("VAULT_CREDENTIAL_SOURCE_INVALID")
    facts = path.stat()
    if stat.S_IMODE(facts.st_mode) not in {_PRIVATE_FILE_MODE, 0o640}:
        _fail("VAULT_CREDENTIAL_SOURCE_INVALID")
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_CREDENTIAL_BYTES:
        _fail("VAULT_CREDENTIAL_SOURCE_INVALID")
    return raw


def _credential(raw: bytes) -> tuple[str, str]:
    try:
        value = S3AccessCredential.from_bytes(raw)
    except (S3VaultError, ValueError) as error:
        code = "VAULT_CREDENTIAL_SOURCE_INVALID"
        raise VaultCredentialStagingError(code) from error
    return value.reveal_for_client()


def _inventory_fingerprint(values: dict[str, bytes]) -> str:
    inventory: list[JsonValue] = [
        {
            "name": name,
            "sha256": sha256(raw).hexdigest(),
            "size": len(raw),
        }
        for name, raw in sorted(values.items())
    ]
    return sha256(canonicalize(checked_json_value(inventory))).hexdigest()


def _binding(values: dict[str, bytes]) -> str:
    return "binding_" + _inventory_fingerprint(values)[:48]


def deployment_credential_names() -> tuple[str, ...]:
    """Return the exact credentials sealed by the V1 unit installer."""
    return tuple(
        name for name in required_credential_names() if name not in _NON_DEPLOYED_CREDENTIAL_NAMES
    )


def _load_directory(root: Path) -> dict[str, bytes]:
    expected = deployment_credential_names()
    if (
        not root.is_absolute()
        or root.is_symlink()
        or _has_symlink_component(root.parent)
        or not root.is_dir()
        or stat.S_IMODE(root.stat().st_mode) != _PRIVATE_DIRECTORY_MODE
    ):
        _fail("VAULT_CREDENTIAL_SOURCE_INVALID")
    actual = tuple(sorted(path.name for path in root.iterdir()))
    if actual != expected:
        _fail("VAULT_CREDENTIAL_INVENTORY_INVALID")
    return {name: _read_regular(root / name) for name in expected}


def _replacement_bytes(access_key_id: str, secret_factory: Callable[[], str]) -> bytes:
    secret = secret_factory()
    if type(secret) is not str:
        _fail("VAULT_CREDENTIAL_GENERATION_FAILED")
    raw = canonicalize(
        checked_json_value({"access_key_id": access_key_id, "secret_access_key": secret})
    )
    access, retained = _credential(raw)
    if access != access_key_id or retained != secret:
        _fail("VAULT_CREDENTIAL_GENERATION_FAILED")
    return raw


def _root_part(factory: Callable[[], str]) -> bytes:
    value = factory()
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value.encode("utf-8")) > _MAX_ROOT_PART_BYTES
        or any(ord(character) < _FIRST_CONTROL_CODEPOINT for character in value)
    ):
        _fail("VAULT_CREDENTIAL_GENERATION_FAILED")
    return value.encode("utf-8")


def _root_pair(values: dict[str, bytes]) -> tuple[str, str]:
    try:
        return _credential(
            canonicalize(
                checked_json_value(
                    {
                        "access_key_id": values[_PRIMARY_ROOT_CREDENTIALS[0]].decode(
                            "utf-8", errors="strict"
                        ),
                        "secret_access_key": values[_PRIMARY_ROOT_CREDENTIALS[1]].decode(
                            "utf-8", errors="strict"
                        ),
                    }
                )
            )
        )
    except (UnicodeDecodeError, ValueError) as error:
        code = "VAULT_CREDENTIAL_SOURCE_INVALID"
        raise VaultCredentialStagingError(code) from error


def _write_directory(root: Path, values: dict[str, bytes]) -> None:
    if (
        not root.is_absolute()
        or root == Path(root.anchor)
        or root.is_symlink()
        or _has_symlink_component(root.parent)
    ):
        _fail("VAULT_CREDENTIAL_OUTPUT_INVALID")
    if not root.parent.is_dir():
        _fail("VAULT_CREDENTIAL_OUTPUT_INVALID")
    temporary = root.parent / f".{root.name}.{token_urlsafe(18)}.tmp"
    temporary.mkdir(mode=_PRIVATE_DIRECTORY_MODE)
    try:
        for name, raw in sorted(values.items()):
            path = temporary / name
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                _PRIVATE_FILE_MODE,
            )
            try:
                _write_all(descriptor, raw)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        temporary.rename(root)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _fingerprint(body: dict[str, JsonValue]) -> str:
    return "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    written = 0
    while written < len(view):
        count = os.write(descriptor, view[written:])
        if count < 1:
            _fail("VAULT_CREDENTIAL_OUTPUT_INVALID")
        written += count


def _receipt(
    *,
    rotation_id: str,
    source_root: Path,
    candidate_root: Path,
    predecessor: dict[str, bytes],
    candidate: dict[str, bytes],
) -> bytes:
    credential_names = cast("list[JsonValue]", sorted(_ROTATED_CREDENTIALS))
    body: dict[str, JsonValue] = {
        "candidate_binding_ref": _binding(candidate),
        "candidate_root": str(candidate_root),
        "credential_names": credential_names,
        "predecessor_binding_ref": _binding(predecessor),
        "rotated_credential_count": len(_ROTATED_CREDENTIALS),
        "rotation_id": rotation_id,
        "schema_id": "asklegal.hk-v1-vault-credential-staging-receipt",
        "schema_version": "1.0.0",
        "source_root": str(source_root),
        "unchanged_credential_count": len(candidate) - len(_ROTATED_CREDENTIALS),
    }
    return canonicalize(checked_json_value({**body, "fingerprint": _fingerprint(body)}))


def _write_receipt(path: Path, raw: bytes) -> None:
    if (
        not path.is_absolute()
        or path.is_symlink()
        or _has_symlink_component(path.parent)
        or not path.parent.is_dir()
    ):
        _fail("VAULT_CREDENTIAL_RECEIPT_INVALID")
    if path.exists():
        if (
            not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != _PRIVATE_FILE_MODE
            or path.read_bytes() != raw
        ):
            _fail("VAULT_CREDENTIAL_RECEIPT_DRIFT")
        return
    temporary = path.parent / f".{path.name}.{token_urlsafe(18)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        _PRIVATE_FILE_MODE,
    )
    try:
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.rename(path)


def stage_vault_credential_rotation(  # noqa: PLR0913
    *,
    source_root: Path,
    candidate_root: Path,
    receipt_path: Path,
    rotation_id: str,
    secret_factory: Callable[[], str] = lambda: token_urlsafe(48),
    root_access_factory: Callable[[], str] = lambda: "asklegal-primary-root-" + token_hex(16),
    root_secret_factory: Callable[[], str] = lambda: token_urlsafe(64),
) -> bytes:
    """Create or replay one full set with seven app and Primary-root replacements."""
    if _ROTATION_ID.fullmatch(rotation_id) is None:
        _fail("VAULT_CREDENTIAL_ROTATION_ID_INVALID")
    if (
        not source_root.is_absolute()
        or not candidate_root.is_absolute()
        or not receipt_path.is_absolute()
        or source_root == candidate_root
        or source_root.is_relative_to(candidate_root)
        or candidate_root.is_relative_to(source_root)
        or receipt_path.is_relative_to(source_root)
        or receipt_path.is_relative_to(candidate_root)
    ):
        _fail("VAULT_CREDENTIAL_PATH_OVERLAP")
    source = _load_directory(source_root)
    old_credentials = {name: _credential(source[name]) for name in _APPLICATION_CREDENTIALS}
    old_root = _root_pair(source)
    if candidate_root.exists():
        candidate = _load_directory(candidate_root)
    else:
        candidate = dict(source)
        generated_secrets: set[str] = set()
        for name, access_key_id in _APPLICATION_CREDENTIALS.items():
            replacement = _replacement_bytes(access_key_id, secret_factory)
            _new_access, new_secret = _credential(replacement)
            if new_secret in generated_secrets:
                _fail("VAULT_CREDENTIAL_GENERATION_FAILED")
            generated_secrets.add(new_secret)
            candidate[name] = replacement
        candidate[_PRIMARY_ROOT_CREDENTIALS[0]] = _root_part(root_access_factory)
        candidate[_PRIMARY_ROOT_CREDENTIALS[1]] = _root_part(root_secret_factory)
        if not generated_secrets.isdisjoint(
            {value[1] for value in old_credentials.values()} | {old_root[1]}
        ):
            _fail("VAULT_CREDENTIAL_GENERATION_FAILED")
        _write_directory(candidate_root, candidate)
        candidate = _load_directory(candidate_root)
    candidate_credentials = {
        name: _credential(candidate[name]) for name in _APPLICATION_CREDENTIALS
    }
    candidate_root_pair = _root_pair(candidate)
    old_secrets = {value[1] for value in old_credentials.values()} | {old_root[1]}
    new_secrets = {value[1] for value in candidate_credentials.values()}
    if (
        any(
            candidate_credentials[name][0] != access_key_id
            for name, access_key_id in _APPLICATION_CREDENTIALS.items()
        )
        or len(new_secrets) != len(_APPLICATION_CREDENTIALS)
        or not new_secrets.isdisjoint(old_secrets)
        or candidate_root_pair[0] == old_root[0]
        or candidate_root_pair[1] == old_root[1]
        or candidate_root_pair[0] in {value[0] for value in old_credentials.values()}
        or candidate_root_pair[0] in {value[0] for value in candidate_credentials.values()}
        or candidate_root_pair[1] in old_secrets
        or candidate_root_pair[1] in new_secrets
        or any(
            candidate[name] != source[name]
            for name in deployment_credential_names()
            if name not in _ROTATED_CREDENTIALS
        )
    ):
        _fail("VAULT_CREDENTIAL_CANDIDATE_DRIFT")
    raw = _receipt(
        rotation_id=rotation_id,
        source_root=source_root,
        candidate_root=candidate_root,
        predecessor=source,
        candidate=candidate,
    )
    _write_receipt(receipt_path, raw)
    parsed = parse_json_bytes(raw, max_bytes=_MAX_RECEIPT_BYTES)
    if type(parsed) is not dict or type(parsed.get("fingerprint")) is not str:
        _fail("VAULT_CREDENTIAL_RECEIPT_INVALID")
    return raw


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--rotation-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Stage the candidate and print only its value-free receipt identity."""
    arguments = _parser().parse_args(argv)
    try:
        raw = stage_vault_credential_rotation(
            source_root=arguments.source_root,
            candidate_root=arguments.candidate_root,
            receipt_path=arguments.receipt,
            rotation_id=arguments.rotation_id,
        )
        document = cast("dict[str, object]", parse_json_bytes(raw, max_bytes=_MAX_RECEIPT_BYTES))
    except (OSError, TypeError, VaultCredentialStagingError) as error:
        code = (
            error
            if isinstance(error, VaultCredentialStagingError)
            else "VAULT_CREDENTIAL_IO_FAILED"
        )
        print(code, file=sys.stderr)  # noqa: T201
        return 2
    print(  # noqa: T201
        f"STAGED_NO_REMOTE_EFFECT {document['fingerprint']} {document['candidate_binding_ref']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
