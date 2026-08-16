"""Fail-closed tests for exact migration packages."""

import json
import shutil
from pathlib import Path

import pytest
from asklegal_management_register.migration import MigrationViolation, load_package

_PACKAGE = Path(__file__).parents[1] / "migrations" / "000001_management_register_spike"


def test_repository_migration_package_is_exact() -> None:
    """The checked-in package matches every declared byte and fingerprint."""
    package = load_package(_PACKAGE)
    assert package.migration_id == "000001"
    assert len(package.batches) == 5


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
