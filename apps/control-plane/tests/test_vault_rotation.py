"""No-network proofs for the dual-vault rotation helper."""

# pyright: reportPrivateUsage=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false
# Focused fakes intentionally implement the private transport extension.
# ruff: noqa: D101, SLF001

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_control_plane import vault_rotation
from asklegal_evidence_vault import S3AccessCredential, VaultName


def _credential(access: str, secret: str) -> S3AccessCredential:
    return S3AccessCredential.from_bytes(
        canonicalize(checked_json_value({"access_key_id": access, "secret_access_key": secret}))
    )


class FakeAdministrator:
    def __init__(self, values: tuple[S3AccessCredential, ...]) -> None:
        self.values = values
        self.deleted: list[str] = []

    def users(self) -> tuple[tuple[str, str, str], ...]:
        return tuple((*item.reveal_for_client(), "user") for item in self.values)

    def provision(self, credentials: tuple[S3AccessCredential, ...]) -> None:
        current = {item.reveal_for_client()[0]: item for item in self.values}
        current.update({item.reveal_for_client()[0]: item for item in credentials})
        self.values = tuple(current.values())

    def delete(self, access: str) -> None:
        self.deleted.append(access)
        self.values = tuple(item for item in self.values if item.reveal_for_client()[0] != access)

    def readback(self, credentials: tuple[S3AccessCredential, ...]) -> tuple[str, ...]:
        assert self.values == credentials
        return tuple(item.reveal_for_client()[0] for item in credentials)


def test_reconcile_converges_both_vaults_forward_and_backward() -> None:
    """Only the exact old/new union may exist during reversible convergence."""
    old_primary = tuple(_credential(f"old-p-{index}", f"old-secret-{index}") for index in range(5))
    new_primary = tuple(_credential(f"new-p-{index}", f"new-secret-{index}") for index in range(5))
    old_recovery = tuple(
        _credential(f"old-r-{index}", f"old-r-secret-{index}") for index in range(2)
    )
    new_recovery = tuple(
        _credential(f"new-r-{index}", f"new-r-secret-{index}") for index in range(2)
    )
    predecessor = (
        (VaultName.PRIMARY, old_primary),
        (VaultName.RECOVERY, old_recovery),
    )
    candidate = (
        (VaultName.PRIMARY, new_primary),
        (VaultName.RECOVERY, new_recovery),
    )
    primary = FakeAdministrator(old_primary)
    recovery = FakeAdministrator(old_recovery)
    administrators = ((VaultName.PRIMARY, primary), (VaultName.RECOVERY, recovery))

    vault_rotation.reconcile(predecessor, candidate, administrators, target="candidate")
    assert primary.values == new_primary
    assert recovery.values == new_recovery
    vault_rotation.reconcile(predecessor, candidate, administrators, target="predecessor")
    assert primary.values == old_primary
    assert recovery.values == old_recovery
    assert len(primary.deleted) == 10
    assert len(recovery.deleted) == 4


def test_main_emits_only_value_free_canonical_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The container entrypoint never prints credentials or provider detail."""
    predecessor = (tmp_path / "predecessor").resolve()
    candidate = (tmp_path / "candidate").resolve()
    predecessor.mkdir()
    candidate.mkdir()
    roots = (tmp_path / "roots").resolve()
    roots.mkdir()
    plan_path = (tmp_path / "plan.json").resolve()
    plan_path.write_bytes(b"unused")
    groups = (
        (VaultName.PRIMARY, tuple(_credential(f"p-{i}", f"hidden-old-{i}") for i in range(5))),
        (VaultName.RECOVERY, tuple(_credential(f"r-{i}", f"hidden-old-r-{i}") for i in range(2))),
    )
    monkeypatch.setattr(vault_rotation, "_bound_groups", lambda _root, _digests: groups)
    binding = vault_rotation._PlanBinding(
        "sha256:" + "a" * 64,
        "binding_" + "b" * 48,
        "binding_" + "c" * 48,
        "sha256:" + "f" * 64,
        None,
        tuple((name, "d" * 64) for name in vault_rotation._NAMES),
        tuple((name, "e" * 64) for name in vault_rotation._NAMES),
    )
    monkeypatch.setattr(vault_rotation, "_plan", lambda _path: binding)
    monkeypatch.setattr(vault_rotation, "_safe_directory", lambda path, _expected: path)
    binding = vault_rotation._PlanBinding(
        binding.plan_fingerprint,
        binding.predecessor_binding_ref,
        binding.candidate_binding_ref,
        binding.control_plane_candidate_image_id,
        binding.application_build_results_fingerprint,
        tuple((name, sha256(b"candidate").hexdigest()) for name in vault_rotation._NAMES),
        tuple((name, sha256(b"candidate").hexdigest()) for name in vault_rotation._NAMES),
    )
    monkeypatch.setattr(vault_rotation, "_plan", lambda _path: binding)
    monkeypatch.setattr(
        vault_rotation,
        "probe",
        lambda _groups: (vault_rotation._NAMES, ()),
    )

    assert (
        vault_rotation.main(
            [
                "probe",
                "--target",
                "candidate",
                "--predecessor-directory",
                str(predecessor),
                "--candidate-directory",
                str(candidate),
                "--root-credential-directory",
                str(roots),
                "--plan",
                str(plan_path),
                "--authorized-plan-fingerprint",
                binding.plan_fingerprint,
                "--expected-control-plane-image-id",
                binding.control_plane_candidate_image_id,
            ]
        )
        == 0
    )
    output = capsys.readouterr()
    document = json.loads(output.out)
    assert document["action"] == "probe"
    assert document["accepted_names"] == list(vault_rotation._NAMES)
    assert "hidden" not in output.out
    assert not output.err
