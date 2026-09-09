"""Focused tests for secret-safe Primary-vault credential candidate staging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.hk_v1_stage_vault_credential_rotation import (
    VaultCredentialStagingError,
    deployment_credential_names,
    main,
    stage_vault_credential_rotation,
)

_ROTATION = "rot_" + "1" * 48
_OLD_SECRET = "old-secret-never-print"
_NEW_SECRET = "new-secret-never-print"
_VAULT_ACCESS_IDS = {
    "vault-primary-acquisition": "asklegal-primary-acquisition",
    "vault-primary-control": "asklegal-primary-control",
    "vault-primary-processing": "asklegal-primary-processing",
    "vault-primary-promotion": "asklegal-primary-promotion",
    "vault-primary-review": "asklegal-primary-review",
    "vault-recovery-acquisition": "asklegal-recovery-acquisition",
    "vault-recovery-promotion": "asklegal-recovery-promotion",
}
_PRIMARY_ROOT_NAMES = ("vault-primary-root-access", "vault-primary-root-secret")


def test_deployment_inventory_matches_exact_sealing_contract() -> None:
    """The candidate mirrors the 25 credentials consumed by rendered units."""
    names = deployment_credential_names()
    assert len(names) == 25
    assert "grafana-admin" not in names
    assert "vault-primary-acquisition" in names


def _source(root: Path) -> Path:
    source = root / "source"
    source.mkdir(mode=0o700)
    for name in deployment_credential_names():
        raw = (
            json.dumps(
                {
                    "access_key_id": "legacy-" + name,
                    "secret_access_key": _OLD_SECRET + name,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
            if name in _VAULT_ACCESS_IDS
            else f"opaque-{name}".encode()
        )
        path = source / name
        path.write_bytes(raw)
        path.chmod(0o600)
    return source.resolve()


def test_stage_changes_only_target_and_replays_without_secret_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The full candidate is exact, private, immutable, and value-free externally."""
    source = _source(tmp_path)
    candidate = (tmp_path / "candidate").resolve()
    receipt = (tmp_path / "receipt.json").resolve()
    generated = iter(f"{_NEW_SECRET}-{index}" for index in range(7))
    raw = stage_vault_credential_rotation(
        source_root=source,
        candidate_root=candidate,
        receipt_path=receipt,
        rotation_id=_ROTATION,
        secret_factory=lambda: next(generated),
        root_access_factory=lambda: "new-primary-root-access-never-print",
        root_secret_factory=lambda: "new-primary-root-secret-never-print",
    )
    assert stat_mode(candidate) == 0o700
    assert all(stat_mode(candidate / name) == 0o600 for name in deployment_credential_names())
    assert all(
        (candidate / name).read_bytes() == (source / name).read_bytes()
        for name in deployment_credential_names()
        if name not in _VAULT_ACCESS_IDS and name not in _PRIMARY_ROOT_NAMES
    )
    assert all(
        (candidate / name).read_bytes() != (source / name).read_bytes()
        for name in _VAULT_ACCESS_IDS
    )
    assert all(
        (candidate / name).read_bytes() != (source / name).read_bytes()
        for name in _PRIMARY_ROOT_NAMES
    )
    document = json.loads(raw)
    assert document["rotated_credential_count"] == 9
    assert document["unchanged_credential_count"] == 16
    assert document["credential_names"] == sorted((*_VAULT_ACCESS_IDS, *_PRIMARY_ROOT_NAMES))
    assert all(
        json.loads((candidate / name).read_bytes())["access_key_id"] == access_key_id
        for name, access_key_id in _VAULT_ACCESS_IDS.items()
    )
    assert _OLD_SECRET.encode() not in raw
    assert _NEW_SECRET.encode() not in raw
    assert (
        stage_vault_credential_rotation(
            source_root=source,
            candidate_root=candidate,
            receipt_path=receipt,
            rotation_id=_ROTATION,
            secret_factory=lambda: "unused-secret",
        )
        == raw
    )
    assert (
        main(
            [
                "--source-root",
                str(source),
                "--candidate-root",
                str(candidate),
                "--receipt",
                str(receipt),
                "--rotation-id",
                _ROTATION,
            ]
        )
        == 0
    )
    output = capsys.readouterr()
    assert _OLD_SECRET not in output.out + output.err
    assert _NEW_SECRET not in output.out + output.err


def stat_mode(path: Path) -> int:
    """Return only permission bits for focused assertions."""
    return path.lstat().st_mode & 0o777


def test_symlinked_source_or_candidate_drift_fails_closed(tmp_path: Path) -> None:
    """Aliases and post-staging modification never get adopted."""
    source = _source(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(VaultCredentialStagingError):
        stage_vault_credential_rotation(
            source_root=alias.absolute(),
            candidate_root=(tmp_path / "candidate-a").resolve(),
            receipt_path=(tmp_path / "receipt-a.json").resolve(),
            rotation_id=_ROTATION,
            secret_factory=lambda: _NEW_SECRET,
        )
    candidate = (tmp_path / "candidate-b").resolve()
    receipt = (tmp_path / "receipt-b.json").resolve()
    generated = iter(f"{_NEW_SECRET}-{index}" for index in range(7))
    stage_vault_credential_rotation(
        source_root=source,
        candidate_root=candidate,
        receipt_path=receipt,
        rotation_id=_ROTATION,
        secret_factory=lambda: next(generated),
        root_access_factory=lambda: "new-primary-root-access-never-print",
        root_secret_factory=lambda: "new-primary-root-secret-never-print",
    )
    (candidate / "sql-control").write_bytes(b"drift")
    with pytest.raises(VaultCredentialStagingError, match="CANDIDATE_DRIFT"):
        stage_vault_credential_rotation(
            source_root=source,
            candidate_root=candidate,
            receipt_path=receipt,
            rotation_id=_ROTATION,
        )


def test_cli_preserves_symlink_evidence(tmp_path: Path) -> None:
    """CLI path handling cannot erase a symlink before validation."""
    source = _source(tmp_path)
    alias = tmp_path / "source-alias"
    alias.symlink_to(source, target_is_directory=True)
    assert (
        main(
            [
                "--source-root",
                str(alias.absolute()),
                "--candidate-root",
                str((tmp_path / "candidate").resolve()),
                "--receipt",
                str((tmp_path / "receipt.json").resolve()),
                "--rotation-id",
                _ROTATION,
            ]
        )
        == 2
    )


def test_predecessor_secrets_cannot_be_permuted_into_candidates(tmp_path: Path) -> None:
    """Every replacement is new across the complete predecessor credential set."""
    source = _source(tmp_path)
    old_secrets = [(_OLD_SECRET + name) for name in _VAULT_ACCESS_IDS]
    permuted = iter(old_secrets[1:] + old_secrets[:1])
    with pytest.raises(VaultCredentialStagingError, match="GENERATION_FAILED"):
        stage_vault_credential_rotation(
            source_root=source,
            candidate_root=(tmp_path / "candidate").resolve(),
            receipt_path=(tmp_path / "receipt.json").resolve(),
            rotation_id=_ROTATION,
            secret_factory=lambda: next(permuted),
        )
    assert not (tmp_path / "candidate").exists()


@pytest.mark.parametrize("part", ["access", "secret"])
def test_primary_root_pair_must_change_as_one_disjoint_pair(tmp_path: Path, part: str) -> None:
    """Reusing either compromised root component fails before candidate publication."""
    source = _source(tmp_path)
    old_access = (source / _PRIMARY_ROOT_NAMES[0]).read_text()
    old_secret = (source / _PRIMARY_ROOT_NAMES[1]).read_text()
    with pytest.raises(VaultCredentialStagingError, match="CANDIDATE_DRIFT"):
        stage_vault_credential_rotation(
            source_root=source,
            candidate_root=(tmp_path / "candidate").resolve(),
            receipt_path=(tmp_path / "receipt.json").resolve(),
            rotation_id=_ROTATION,
            secret_factory=(item for item in [f"new-{index}" for index in range(7)]).__next__,
            root_access_factory=lambda: old_access if part == "access" else "new-root-access",
            root_secret_factory=lambda: old_secret if part == "secret" else "new-root-secret",
        )


def test_overlapping_receipt_and_candidate_are_rejected_before_write(tmp_path: Path) -> None:
    """A success receipt cannot invalidate its own exact credential inventory."""
    source = _source(tmp_path)
    candidate = (tmp_path / "candidate").resolve()
    with pytest.raises(VaultCredentialStagingError, match="PATH_OVERLAP"):
        stage_vault_credential_rotation(
            source_root=source,
            candidate_root=candidate,
            receipt_path=candidate / "receipt.json",
            rotation_id=_ROTATION,
        )
    assert not candidate.exists()
