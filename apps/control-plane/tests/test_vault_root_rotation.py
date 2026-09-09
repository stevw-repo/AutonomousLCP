"""No-network tests for the candidate-image Primary-root probe."""

# pyright: reportPrivateUsage=false
# ruff: noqa: D103, FBT001, FBT003

from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_control_plane import vault_root_rotation
from asklegal_evidence_vault import S3AccessCredential

_IMAGE = "sha256:" + "3" * 64
_PLAN = "sha256:" + "4" * 64
_OLD_ACCESS = "old-primary-root-access-never-print"
_OLD_SECRET = "old-primary-root-secret-never-print"
_NEW_ACCESS = "new-primary-root-access-never-print"
_NEW_SECRET = "new-primary-root-secret-never-print"
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


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    predecessor = tmp_path / "predecessor"
    candidate = tmp_path / "candidate"
    applications = tmp_path / "applications"
    predecessor.mkdir()
    candidate.mkdir()
    applications.mkdir()
    for name in _SNAPSHOT_NAMES:
        (predecessor / name).write_text("predecessor-" + name)
        (candidate / name).write_text("predecessor-" + name)
    (predecessor / _ROOT_NAMES[0]).write_text(_OLD_ACCESS)
    (predecessor / _ROOT_NAMES[1]).write_text(_OLD_SECRET)
    (candidate / _ROOT_NAMES[0]).write_text(_NEW_ACCESS)
    (candidate / _ROOT_NAMES[1]).write_text(_NEW_SECRET)
    for index, name in enumerate(_APPLICATIONS):
        (applications / name).write_text(
            json.dumps(
                {
                    "access_key_id": f"application-{index}",
                    "secret_access_key": f"application-secret-{index}",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return predecessor, candidate, applications


def _binding(root: Path) -> str:
    rows: list[JsonValue] = [
        {
            "name": name,
            "sha256": sha256((root / name).read_bytes()).hexdigest(),
            "size": len((root / name).read_bytes()),
        }
        for name in _SNAPSHOT_NAMES
    ]
    return "binding_" + sha256(canonicalize(checked_json_value(rows))).hexdigest()[:48]


def _plan(tmp_path: Path, predecessor: Path, candidate: Path) -> Path:
    body: dict[str, JsonValue] = {
        "application_build_results_fingerprint": "sha256:" + "5" * 64,
        "candidate_binding_ref": _binding(candidate),
        "candidate_runtime_configuration_ref": "runtimecfg_" + "6" * 64,
        "control_plane_candidate_image_id": _IMAGE,
        "credential_names": list(_ROOT_NAMES),
        "predecessor_binding_ref": _binding(predecessor),
        "predecessor_runtime_configuration_ref": "runtimecfg_" + "7" * 64,
        "predecessor_sealed_state_ref": "sealed_" + "8" * 64,
        "rotation_id": "rot_" + "9" * 48,
        "staging_receipt_fingerprint": "sha256:" + "a" * 64,
        "stopped_units": [],
        "vault_data_state_ref": "vaultdata_" + "b" * 64,
    }
    fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
    raw = canonicalize(
        checked_json_value(
            {
                **body,
                "plan_fingerprint": fingerprint,
                "schema_id": "asklegal.hk-v1-primary-vault-root-rotation-plan",
                "schema_version": "1.0.0",
            }
        )
    )
    path = tmp_path / "plan.json"
    path.write_bytes(raw)
    return path


class _Client:
    def __init__(self, accepted: bool, *, rejection_code: str = "SignatureDoesNotMatch") -> None:
        self.accepted = accepted
        self.rejection_code = rejection_code

    def head_bucket(self, **_kwargs: object) -> dict[str, object]:
        if self.accepted:
            return {}
        error = RuntimeError("provider text must not escape")
        vars(error)["response"] = {
            "ResponseMetadata": {"HTTPStatusCode": 403},
            "Error": {"Code": self.rejection_code},
        }
        raise error


class _Administrator:
    def readback(self, credentials: Sequence[S3AccessCredential]) -> tuple[str, ...]:
        return tuple(item.reveal_for_client()[0] for item in credentials)


def test_candidate_acceptance_requires_bucket_and_exact_admin_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    predecessor, candidate, applications = _roots(tmp_path)
    plan = _plan(tmp_path, predecessor, candidate)

    def client_factory(*_args: object, **_kwargs: object) -> _Client:
        return _Client(True)

    def administrator_factory(*_args: object, **_kwargs: object) -> _Administrator:
        return _Administrator()

    monkeypatch.setattr(vault_root_rotation, "create_v1_s3_client", client_factory)
    monkeypatch.setattr(
        vault_root_rotation,
        "create_v1_vault_identity_administrator",
        administrator_factory,
    )
    parsed = json.loads(plan.read_bytes())
    result = vault_root_rotation.main(
        [
            "--target",
            "candidate",
            "--expect",
            "accepted",
            "--credential-directory",
            str(candidate),
            "--application-credential-directory",
            str(applications),
            "--plan",
            str(plan),
            "--authorized-plan-fingerprint",
            parsed["plan_fingerprint"],
            "--expected-control-plane-image-id",
            _IMAGE,
        ]
    )
    assert result == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["accepted"] is True
    assert _NEW_ACCESS not in output.out + output.err
    assert _NEW_SECRET not in output.out + output.err


def test_predecessor_rejection_accepts_only_authentication_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    predecessor, candidate, applications = _roots(tmp_path)
    plan = _plan(tmp_path, predecessor, candidate)

    def client_factory(*_args: object, **_kwargs: object) -> _Client:
        return _Client(False)

    monkeypatch.setattr(vault_root_rotation, "create_v1_s3_client", client_factory)
    parsed = json.loads(plan.read_bytes())
    result = vault_root_rotation.main(
        [
            "--target",
            "predecessor",
            "--expect",
            "rejected",
            "--credential-directory",
            str(predecessor),
            "--application-credential-directory",
            str(applications),
            "--plan",
            str(plan),
            "--authorized-plan-fingerprint",
            parsed["plan_fingerprint"],
            "--expected-control-plane-image-id",
            _IMAGE,
        ]
    )
    assert result == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["accepted"] is False
    assert "provider text" not in output.out + output.err


def test_generic_access_denied_does_not_prove_predecessor_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    predecessor, candidate, applications = _roots(tmp_path)
    plan = _plan(tmp_path, predecessor, candidate)

    def client_factory(*_args: object, **_kwargs: object) -> _Client:
        return _Client(False, rejection_code="AccessDenied")

    monkeypatch.setattr(vault_root_rotation, "create_v1_s3_client", client_factory)
    parsed = json.loads(plan.read_bytes())
    result = vault_root_rotation.main(
        [
            "--target",
            "predecessor",
            "--expect",
            "rejected",
            "--credential-directory",
            str(predecessor),
            "--application-credential-directory",
            str(applications),
            "--plan",
            str(plan),
            "--authorized-plan-fingerprint",
            parsed["plan_fingerprint"],
            "--expected-control-plane-image-id",
            _IMAGE,
        ]
    )
    assert result == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "PRIMARY_VAULT_ROOT_ROTATION_NOT_READY\n"
