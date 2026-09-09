"""Candidate-image probe for one exact Primary Versity root-key rotation."""

# Provider failures are deliberately collapsed to value-free result codes.
# ruff: noqa: BLE001, EM101, PERF401

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Never, Protocol, runtime_checkable

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import (
    S3AccessCredential,
    V1S3VaultSettings,
    VaultName,
    create_v1_s3_client,
)

from asklegal_control_plane.bootstrap import create_v1_vault_identity_administrator

_PLAN_SCHEMA = "asklegal.hk-v1-primary-vault-root-rotation-plan"
_RECEIPT_SCHEMA = "asklegal.hk-v1-primary-vault-root-rotation-network-receipt"
_VERSION = "1.0.0"
_ROOT_NAMES = ("vault-primary-root-access", "vault-primary-root-secret")
_APPLICATIONS = (
    "vault-primary-acquisition",
    "vault-primary-control",
    "vault-primary-processing",
    "vault-primary-promotion",
    "vault-primary-review",
)
_SNAPSHOT_NAMES = (
    "embedding-provider",
    "model-egress-proxy",
    "model-provider",
    "pinecone-poc",
    "promotion-egress-proxy",
    "review-api",
    "review-client",
    "source-egress-proxy",
    "sql-acquisition",
    "sql-bootstrap-password",
    "sql-control",
    "sql-processing",
    "sql-promotion",
    "sql-review",
    "vault-primary-acquisition",
    "vault-primary-control",
    "vault-primary-processing",
    "vault-primary-promotion",
    "vault-primary-review",
    "vault-primary-root-access",
    "vault-primary-root-secret",
    "vault-recovery-acquisition",
    "vault-recovery-promotion",
    "vault-recovery-root-access",
    "vault-recovery-root-secret",
)
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_PLAN_KEYS = {
    "application_build_results_fingerprint",
    "candidate_binding_ref",
    "candidate_runtime_configuration_ref",
    "control_plane_candidate_image_id",
    "credential_names",
    "plan_fingerprint",
    "predecessor_binding_ref",
    "predecessor_runtime_configuration_ref",
    "predecessor_sealed_state_ref",
    "rotation_id",
    "schema_id",
    "schema_version",
    "staging_receipt_fingerprint",
    "stopped_units",
    "vault_data_state_ref",
}


class VaultRootProbeError(RuntimeError):
    """One sanitized root-probe failure."""


def _fail(code: str) -> Never:
    raise VaultRootProbeError(code)


@runtime_checkable
class _HeadBucket(Protocol):
    def head_bucket(self, **kwargs: object) -> Mapping[str, object]: ...


def _read(path: Path, *, maximum: int = 65_536) -> bytes:
    if path.is_symlink() or not path.is_file():
        _fail("ROOT_ROTATION_INPUT_INVALID")
    raw = path.read_bytes()
    if not 1 <= len(raw) <= maximum:
        _fail("ROOT_ROTATION_INPUT_INVALID")
    return raw


def _json_object(value: object) -> dict[str, JsonValue]:
    try:
        checked = checked_json_value(value)
    except TypeError as error:
        raise VaultRootProbeError("ROOT_ROTATION_PLAN_INVALID") from error
    if not isinstance(checked, dict):
        _fail("ROOT_ROTATION_PLAN_INVALID")
    return checked


def _head_bucket_client(value: object) -> _HeadBucket:
    if not isinstance(value, _HeadBucket):
        _fail("ROOT_ROTATION_PROVIDER_FAILED")
    return value


def _plan(path: Path) -> dict[str, JsonValue]:
    raw = _read(path)
    try:
        value = parse_json_bytes(raw, max_bytes=65_536)
    except (TypeError, ValueError) as error:
        raise VaultRootProbeError("ROOT_ROTATION_PLAN_INVALID") from error
    if type(value) is not dict or canonicalize(checked_json_value(value)) != raw:
        _fail("ROOT_ROTATION_PLAN_INVALID")
    document = _json_object(value)
    fingerprint = document.get("plan_fingerprint")
    body = {
        key: item
        for key, item in document.items()
        if key not in {"plan_fingerprint", "schema_id", "schema_version"}
    }
    if (
        set(document) != _PLAN_KEYS
        or document.get("schema_id") != _PLAN_SCHEMA
        or document.get("schema_version") != _VERSION
        or type(fingerprint) is not str
        or fingerprint != "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
        or document.get("credential_names") != list(_ROOT_NAMES)
    ):
        _fail("ROOT_ROTATION_PLAN_INVALID")
    return document


def _snapshot_binding(root: Path) -> str:
    inventory: list[JsonValue] = []
    if tuple(sorted(path.name for path in root.iterdir())) != _SNAPSHOT_NAMES:
        _fail("ROOT_ROTATION_INPUT_DRIFT")
    for name in _SNAPSHOT_NAMES:
        raw = _read(root / name, maximum=32_768)
        inventory.append({"name": name, "sha256": sha256(raw).hexdigest(), "size": len(raw)})
    digest = sha256(canonicalize(checked_json_value(inventory))).hexdigest()
    return "binding_" + digest[:48]


def _pair(root: Path) -> S3AccessCredential:
    access = _read(root / _ROOT_NAMES[0], maximum=1_024)
    secret = _read(root / _ROOT_NAMES[1], maximum=1_024)
    try:
        return S3AccessCredential.from_bytes(
            canonicalize(
                checked_json_value(
                    {
                        "access_key_id": access.decode("utf-8", errors="strict"),
                        "secret_access_key": secret.decode("utf-8", errors="strict"),
                    }
                )
            )
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise VaultRootProbeError("ROOT_ROTATION_INPUT_INVALID") from error


def _applications(root: Path) -> tuple[S3AccessCredential, ...]:
    result: list[S3AccessCredential] = []
    for name in _APPLICATIONS:
        result.append(S3AccessCredential.from_bytes(_read(root / name, maximum=4_096)))
    return tuple(result)


def _authentication_rejection(error: Exception) -> bool:
    response_value: object = vars(error).get("response")
    try:
        response = checked_json_value(response_value)
    except TypeError:
        return False
    error_value = response.get("Error") if isinstance(response, dict) else None
    code = error_value.get("Code") if isinstance(error_value, dict) else None
    # A generic 401/403 or AccessDenied can mean an authenticated principal
    # lacked bucket permission. Only invalid-key/signature codes prove that the
    # predecessor credential itself is no longer accepted.
    return code in {"InvalidAccessKeyId", "SignatureDoesNotMatch"}


def _probe(
    root: Path,
    applications: Path,
    plan: dict[str, JsonValue],
    *,
    target: str,
    expectation: str,
) -> bool:
    binding_field = "candidate_binding_ref" if target == "candidate" else "predecessor_binding_ref"
    if _snapshot_binding(root) != plan.get(binding_field):
        _fail("ROOT_ROTATION_INPUT_DRIFT")
    credential = _pair(root)
    settings = V1S3VaultSettings.for_vault(VaultName.PRIMARY)
    client = create_v1_s3_client(
        settings,
        credential,
        retry_attempts=1,
        connect_timeout_seconds=5,
        read_timeout_seconds=10,
    )
    probe_client = _head_bucket_client(client)
    try:
        probe_client.head_bucket(Bucket=settings.bucket)
    except Exception as error:
        if expectation != "rejected" or not _authentication_rejection(error):
            _fail("ROOT_ROTATION_PROVIDER_FAILED")
        return False
    if expectation != "accepted":
        _fail("ROOT_ROTATION_PREDECESSOR_STILL_ACCEPTED")
    administrator = create_v1_vault_identity_administrator(
        VaultName.PRIMARY,
        root / _ROOT_NAMES[0],
        root / _ROOT_NAMES[1],
    )
    credentials = _applications(applications)
    expected = tuple(item.reveal_for_client()[0] for item in credentials)
    if administrator.readback(credentials) != expected:
        _fail("ROOT_ROTATION_ADMIN_READBACK_FAILED")
    return True


def _receipt(plan: dict[str, JsonValue], *, target: str, accepted: bool) -> bytes:
    body: dict[str, JsonValue] = {
        "accepted": accepted,
        "application_build_results_fingerprint": plan["application_build_results_fingerprint"],
        "candidate_binding_ref": plan["candidate_binding_ref"],
        "control_plane_candidate_image_id": plan["control_plane_candidate_image_id"],
        "plan_fingerprint": plan["plan_fingerprint"],
        "predecessor_binding_ref": plan["predecessor_binding_ref"],
        "schema_id": _RECEIPT_SCHEMA,
        "schema_version": _VERSION,
        "target": target,
    }
    return canonicalize(
        checked_json_value(
            {
                **body,
                "fingerprint": "sha256:"
                + sha256(canonicalize(checked_json_value(body))).hexdigest(),
            }
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("candidate", "predecessor"), required=True)
    parser.add_argument("--expect", choices=("accepted", "rejected"), required=True)
    parser.add_argument("--credential-directory", type=Path, required=True)
    parser.add_argument("--application-credential-directory", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--authorized-plan-fingerprint", required=True)
    parser.add_argument("--expected-control-plane-image-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Emit only one canonical value-free acceptance receipt."""
    arguments = _parser().parse_args(argv)
    try:
        plan = _plan(arguments.plan)
        if (
            plan.get("plan_fingerprint") != arguments.authorized_plan_fingerprint
            or plan.get("control_plane_candidate_image_id")
            != arguments.expected_control_plane_image_id
            or _IMAGE_ID.fullmatch(arguments.expected_control_plane_image_id) is None
        ):
            _fail("ROOT_ROTATION_PLAN_DRIFT")
        accepted = _probe(
            arguments.credential_directory,
            arguments.application_credential_directory,
            plan,
            target=arguments.target,
            expectation=arguments.expect,
        )
        raw = _receipt(plan, target=arguments.target, accepted=accepted)
    except Exception:
        sys.stderr.write("PRIMARY_VAULT_ROOT_ROTATION_NOT_READY\n")
        return 2
    sys.stdout.buffer.write(raw + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
