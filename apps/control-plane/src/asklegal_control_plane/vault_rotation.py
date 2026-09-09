"""Dual-network helper for exact V1 application-vault credential rotation."""

# Provider errors are deliberately normalized to value-free boundary codes.
# ruff: noqa: BLE001

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Never, Protocol, runtime_checkable
from urllib.parse import quote

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import (
    S3AccessCredential,
    S3VaultError,
    V1S3VaultSettings,
    VaultName,
    create_v1_s3_client,
)

from asklegal_control_plane.bootstrap import (
    VersityIdentityAdministration,
    create_v1_vault_identity_administrator,
)

_MAX_CREDENTIAL = 16_384
_MAX_PLAN = 65_536
_PLAN_MODE = 0o600
_SCHEMA = "asklegal.hk-v1-vault-application-rotation-network-receipt"
_VERSION = "1.0.0"
_PRIMARY = (
    "vault-primary-acquisition",
    "vault-primary-control",
    "vault-primary-processing",
    "vault-primary-promotion",
    "vault-primary-review",
)
_RECOVERY = ("vault-recovery-acquisition", "vault-recovery-promotion")
_NAMES = (*_PRIMARY, *_RECOVERY)
_PLAN_SCHEMA = "asklegal.hk-v1-vault-application-rotation-plan"


class VaultRotationNetworkError(RuntimeError):
    """Sanitized dual-network helper failure."""


def _fail(code: str) -> Never:
    raise VaultRotationNetworkError(code)


@dataclass(frozen=True, slots=True)
class _PlanBinding:
    plan_fingerprint: str
    predecessor_binding_ref: str
    candidate_binding_ref: str
    control_plane_candidate_image_id: str
    application_build_results_fingerprint: str | None
    predecessor_digests: tuple[tuple[str, str], ...]
    candidate_digests: tuple[tuple[str, str], ...]


def _read_plan_bytes(path: Path) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        facts = os.fstat(descriptor)
        if (
            not stat.S_ISREG(facts.st_mode)
            or stat.S_IMODE(facts.st_mode) != _PLAN_MODE
            or not 1 <= facts.st_size <= _MAX_PLAN
        ):
            _fail("ROTATION_NETWORK_PLAN_INVALID")
        raw = os.pread(descriptor, facts.st_size, 0)
        after = os.fstat(descriptor)
        if (
            len(raw) != facts.st_size
            or after.st_dev != facts.st_dev
            or after.st_ino != facts.st_ino
            or after.st_size != facts.st_size
            or after.st_mtime_ns != facts.st_mtime_ns
        ):
            _fail("ROTATION_NETWORK_PLAN_INVALID")
    except OSError as error:
        code = "ROTATION_NETWORK_PLAN_INVALID"
        raise VaultRotationNetworkError(code) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return raw


def _digest_rows(document: dict[str, JsonValue], field: str) -> tuple[tuple[str, str], ...]:
    raw_rows = document.get(field)
    if type(raw_rows) is not list:
        _fail("ROTATION_NETWORK_PLAN_INVALID")
    result: list[tuple[str, str]] = []
    for row in raw_rows:
        if type(row) is not dict or set(row) != {"credential_name", "sha256"}:
            _fail("ROTATION_NETWORK_PLAN_INVALID")
        name = row.get("credential_name")
        digest = row.get("sha256")
        if type(name) is not str or type(digest) is not str:
            _fail("ROTATION_NETWORK_PLAN_INVALID")
        result.append((name, digest))
    if tuple(name for name, _digest in result) != _NAMES or any(
        re.fullmatch(r"[0-9a-f]{64}", digest) is None for _name, digest in result
    ):
        _fail("ROTATION_NETWORK_PLAN_INVALID")
    return tuple(result)


def _plan(path: Path) -> _PlanBinding:
    raw = _read_plan_bytes(path)
    try:
        value = parse_json_bytes(raw, max_bytes=65_536)
    except (TypeError, ValueError) as error:
        code = "ROTATION_NETWORK_PLAN_INVALID"
        raise VaultRotationNetworkError(code) from error
    if type(value) is not dict or canonicalize(checked_json_value(value)) != raw:
        _fail("ROTATION_NETWORK_PLAN_INVALID")
    document = value
    if set(document) != {
        "candidate_binding_ref",
        "candidate_plaintext_sha256",
        "application_build_results_fingerprint",
        "control_plane_candidate_image_id",
        "credential_units",
        "dependent_units",
        "plan_fingerprint",
        "predecessor_binding_ref",
        "predecessor_plaintext_sha256",
        "predecessor_sealed_state_ref",
        "rotated_credential_names",
        "rotation_id",
        "schema_id",
        "schema_version",
        "sealed_credential_names",
        "staging_receipt_fingerprint",
    }:
        _fail("ROTATION_NETWORK_PLAN_INVALID")
    fingerprint = document.get("plan_fingerprint")
    unsigned = {
        key: item
        for key, item in document.items()
        if key not in {"plan_fingerprint", "schema_id", "schema_version"}
    }
    if (
        document.get("schema_id") != _PLAN_SCHEMA
        or document.get("schema_version") != _VERSION
        or document.get("rotated_credential_names") != list(_NAMES)
        or document.get("sealed_credential_names") != list(_NAMES)
        or type(fingerprint) is not str
        or fingerprint != "sha256:" + sha256(canonicalize(checked_json_value(unsigned))).hexdigest()
    ):
        _fail("ROTATION_NETWORK_PLAN_INVALID")

    predecessor_ref = document.get("predecessor_binding_ref")
    candidate_ref = document.get("candidate_binding_ref")
    image_id = document.get("control_plane_candidate_image_id")
    build_results_fingerprint = document.get("application_build_results_fingerprint")
    if (
        type(predecessor_ref) is not str
        or type(candidate_ref) is not str
        or type(image_id) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
        or (
            build_results_fingerprint is not None
            and (
                type(build_results_fingerprint) is not str
                or re.fullmatch(r"sha256:[0-9a-f]{64}", build_results_fingerprint) is None
            )
        )
    ):
        _fail("ROTATION_NETWORK_PLAN_INVALID")
    return _PlanBinding(
        fingerprint,
        predecessor_ref,
        candidate_ref,
        image_id,
        build_results_fingerprint,
        _digest_rows(document, "predecessor_plaintext_sha256"),
        _digest_rows(document, "candidate_plaintext_sha256"),
    )


class _RotationAdministrator(VersityIdentityAdministration):
    def users(self) -> tuple[tuple[str, str, str], ...]:
        """Expose the existing strict bounded provider readback."""
        return self._users()

    def delete(self, access: str) -> None:
        """Delete one already union-validated obsolete identity."""
        self._request("/delete-user?access=" + quote(access, safe=""), b"", 204)


@runtime_checkable
class _HeadBucket(Protocol):
    def head_bucket(self, **kwargs: object) -> Mapping[str, object]:
        """Read one bucket's metadata."""
        ...


def _safe_directory(path: Path, expected: tuple[str, ...]) -> Path:
    if (
        not path.is_absolute()
        or path == Path(path.anchor)
        or path.is_symlink()
        or path != path.resolve(strict=True)
        or not path.is_dir()
    ):
        _fail("ROTATION_NETWORK_INPUT_INVALID")
    if tuple(sorted(item.name for item in path.iterdir())) != tuple(sorted(expected)):
        _fail("ROTATION_NETWORK_INPUT_INVALID")
    return path


def _credential_raw(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        facts = os.fstat(descriptor)
        if (
            not stat.S_ISREG(facts.st_mode)
            or stat.S_IMODE(facts.st_mode) not in {0o400, 0o600, 0o640}
            or not 1 <= facts.st_size <= _MAX_CREDENTIAL
        ):
            _fail("ROTATION_NETWORK_INPUT_INVALID")
        raw = os.pread(descriptor, facts.st_size, 0)
        after = os.fstat(descriptor)
        if (
            len(raw) != facts.st_size
            or after.st_dev != facts.st_dev
            or after.st_ino != facts.st_ino
            or after.st_size != facts.st_size
            or after.st_mtime_ns != facts.st_mtime_ns
        ):
            _fail("ROTATION_NETWORK_INPUT_INVALID")
    finally:
        os.close(descriptor)
    return raw


def _bound_groups(
    root: Path, digests: tuple[tuple[str, str], ...]
) -> tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...]:
    credentials: list[S3AccessCredential] = []
    for name, digest in digests:
        raw = _credential_raw(root / name)
        if sha256(raw).hexdigest() != digest:
            _fail("ROTATION_NETWORK_PLAN_DRIFT")
        try:
            credentials.append(S3AccessCredential.from_bytes(raw))
        except S3VaultError as error:
            code = "ROTATION_NETWORK_INPUT_INVALID"
            raise VaultRotationNetworkError(code) from error
    return (
        (VaultName.PRIMARY, tuple(credentials[: len(_PRIMARY)])),
        (VaultName.RECOVERY, tuple(credentials[len(_PRIMARY) :])),
    )


def _administrators(
    root: Path,
) -> tuple[tuple[VaultName, _RotationAdministrator], tuple[VaultName, _RotationAdministrator]]:
    def administrator(vault: VaultName) -> _RotationAdministrator:
        prefix = f"vault-{vault.value.lower()}-root"
        base = create_v1_vault_identity_administrator(
            vault, root / f"{prefix}-access", root / f"{prefix}-secret"
        )
        return _RotationAdministrator(base.settings, base.root_credential)

    return (
        (VaultName.PRIMARY, administrator(VaultName.PRIMARY)),
        (VaultName.RECOVERY, administrator(VaultName.RECOVERY)),
    )


class _Administrator(Protocol):
    def users(self) -> tuple[tuple[str, str, str], ...]: ...

    def provision(self, credentials: tuple[S3AccessCredential, ...]) -> None: ...

    def delete(self, access: str) -> None: ...

    def readback(self, credentials: tuple[S3AccessCredential, ...]) -> tuple[str, ...]: ...


def _pairs(items: tuple[S3AccessCredential, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(item.reveal_for_client() for item in items)


def reconcile(
    predecessor: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    candidate: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    administrators: tuple[tuple[VaultName, _Administrator], tuple[VaultName, _Administrator]],
    *,
    target: str,
) -> None:
    """Converge both vaults to exactly one of two complete bound sets."""
    selected = candidate if target == "candidate" else predecessor
    if target not in {"candidate", "predecessor"}:
        _fail("ROTATION_NETWORK_INPUT_INVALID")
    for (vault, administrator), (selected_vault, selected_items), (
        old_vault,
        old_items,
    ), (new_vault, new_items) in zip(administrators, selected, predecessor, candidate, strict=True):
        if not (vault is selected_vault is old_vault is new_vault):
            _fail("ROTATION_NETWORK_INPUT_INVALID")
        allowed = set(_pairs(old_items)) | set(_pairs(new_items))
        current = administrator.users()
        if len({access for access, _secret, _role in current}) != len(current) or any(
            role != "user" or (access, secret) not in allowed for access, secret, role in current
        ):
            _fail("ROTATION_NETWORK_READBACK_INVALID")
        administrator.provision(selected_items)
        requested = {access for access, _secret in _pairs(selected_items)}
        for access, _secret, _role in administrator.users():
            if access not in requested:
                administrator.delete(access)
        expected = tuple(access for access, _secret in _pairs(selected_items))
        if administrator.readback(selected_items) != expected:
            _fail("ROTATION_NETWORK_READBACK_INVALID")


def probe(
    groups: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Classify all seven exact HEAD-bucket requests without exposing errors."""
    accepted: list[str] = []
    rejected: list[str] = []
    offset = 0
    for vault, items in groups:
        settings = V1S3VaultSettings.for_vault(vault)
        for credential in items:
            name = _NAMES[offset]
            offset += 1
            client = create_v1_s3_client(
                settings,
                credential,
                retry_attempts=1,
                connect_timeout_seconds=5,
                read_timeout_seconds=10,
            )
            if not isinstance(client, _HeadBucket):
                _fail("ROTATION_NETWORK_PROVIDER_FAILED")
            try:
                client.head_bucket(Bucket=settings.bucket)
            except Exception as error:
                response_value: object = vars(error).get("response")
                try:
                    response = checked_json_value(response_value)
                except TypeError:
                    response = None
                metadata = response.get("ResponseMetadata") if isinstance(response, dict) else None
                status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
                error_value = response.get("Error") if isinstance(response, dict) else None
                code = error_value.get("Code") if isinstance(error_value, dict) else None
                if status not in {401, 403} and code not in {
                    "AccessDenied",
                    "InvalidAccessKeyId",
                    "SignatureDoesNotMatch",
                }:
                    _fail("ROTATION_NETWORK_PROVIDER_FAILED")
                rejected.append(name)
            else:
                accepted.append(name)
    if offset != len(_NAMES):
        _fail("ROTATION_NETWORK_INPUT_INVALID")
    return tuple(accepted), tuple(rejected)


def _receipt(
    plan: _PlanBinding,
    *,
    action: str,
    target: str,
    accepted: tuple[str, ...] = (),
    rejected: tuple[str, ...] = (),
) -> bytes:
    body: dict[str, JsonValue] = {
        "accepted_names": list(accepted),
        "action": action,
        "application_build_results_fingerprint": plan.application_build_results_fingerprint,
        "candidate_binding_ref": plan.candidate_binding_ref,
        "control_plane_candidate_image_id": plan.control_plane_candidate_image_id,
        "plan_fingerprint": plan.plan_fingerprint,
        "predecessor_binding_ref": plan.predecessor_binding_ref,
        "rejected_names": list(rejected),
        "schema_id": _SCHEMA,
        "schema_version": _VERSION,
        "target": target,
    }
    fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
    return canonicalize(checked_json_value({**body, "fingerprint": fingerprint}))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("reconcile", "probe"))
    parser.add_argument("--target", choices=("candidate", "predecessor"), required=True)
    parser.add_argument("--predecessor-directory", type=Path, required=True)
    parser.add_argument("--candidate-directory", type=Path, required=True)
    parser.add_argument("--root-credential-directory", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--authorized-plan-fingerprint", required=True)
    parser.add_argument("--expected-control-plane-image-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run only inside the exact candidate image attached to both vault networks."""
    arguments = _parser().parse_args(argv)
    try:
        plan = _plan(arguments.plan)
        if (
            plan.plan_fingerprint != arguments.authorized_plan_fingerprint
            or plan.control_plane_candidate_image_id != arguments.expected_control_plane_image_id
        ):
            _fail("ROTATION_NETWORK_PLAN_DRIFT")
        predecessor_root = _safe_directory(arguments.predecessor_directory, _NAMES)
        candidate_root = _safe_directory(arguments.candidate_directory, _NAMES)
        root_credentials = _safe_directory(
            arguments.root_credential_directory,
            (
                "vault-primary-root-access",
                "vault-primary-root-secret",
                "vault-recovery-root-access",
                "vault-recovery-root-secret",
            ),
        )
        predecessor = _bound_groups(predecessor_root, plan.predecessor_digests)
        candidate = _bound_groups(candidate_root, plan.candidate_digests)
        if arguments.action == "reconcile":
            reconcile(
                predecessor,
                candidate,
                _administrators(root_credentials),
                target=arguments.target,
            )
            raw = _receipt(
                plan,
                action="reconcile",
                target=arguments.target,
            )
        else:
            selected = candidate if arguments.target == "candidate" else predecessor
            accepted, rejected = probe(selected)
            raw = _receipt(
                plan,
                action="probe",
                target=arguments.target,
                accepted=accepted,
                rejected=rejected,
            )
    except Exception:
        sys.stderr.write("ROTATION_NETWORK_NOT_READY\n")
        return 2
    sys.stdout.buffer.write(raw + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
