"""Fail-closed tests for exact migration packages."""

import json
import shutil
from pathlib import Path
from typing import Never

import pytest
from asklegal_management_register.migration import MigrationViolation, apply_packages, load_package

_PACKAGE = Path(__file__).parents[1] / "migrations" / "000001_management_register_spike"
_M2_PACKAGE = Path(__file__).parents[1] / "migrations" / "000002_complete_m2_register"


def test_repository_migration_package_is_exact() -> None:
    """The checked-in package matches every declared byte and fingerprint."""
    package = load_package(_PACKAGE)
    assert package.migration_id == "000001"
    assert len(package.batches) == 5
    complete = load_package(_M2_PACKAGE)
    assert complete.migration_id == "000002"
    assert len(complete.batches) == 9


def test_changed_batch_is_rejected(tmp_path: Path) -> None:
    """A one-byte batch change fails before any database operation."""
    copy = tmp_path / _PACKAGE.name
    shutil.copytree(_PACKAGE, copy)
    batch = copy / "003_consume_approval.sql"
    batch.write_bytes(batch.read_bytes() + b"\n")
    with pytest.raises(MigrationViolation, match="batch bytes differ"):
        load_package(copy)


def test_undeclared_batch_is_rejected(tmp_path: Path) -> None:
    """Implicit discovery never adds an undeclared SQL batch."""
    copy = tmp_path / _PACKAGE.name
    shutil.copytree(_PACKAGE, copy)
    (copy / "999_surprise.sql").write_text("SELECT 1;\n", encoding="utf-8")
    with pytest.raises(MigrationViolation, match="undeclared files"):
        load_package(copy)


def test_manifest_fingerprint_is_recomputed(tmp_path: Path) -> None:
    """A manifest edit with unchanged package fingerprint fails closed."""
    copy = tmp_path / _PACKAGE.name
    shutil.copytree(_PACKAGE, copy)
    manifest_path = copy / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        pytest.fail("manifest fixture is not an object")
    manifest["operation"] = "corrective"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(MigrationViolation, match="package fingerprint differs"):
        load_package(copy)


def test_runner_rejects_an_incomplete_prefix_before_connecting() -> None:
    """Migration 000002 cannot be applied without the exact 000001 prefix."""

    def forbidden_connection() -> Never:
        pytest.fail("an incomplete prefix must fail before opening a connection")

    with pytest.raises(MigrationViolation, match="complete prefix"):
        apply_packages(forbidden_connection, (_M2_PACKAGE,), runner_build="test")
