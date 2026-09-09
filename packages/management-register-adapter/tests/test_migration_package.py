"""Fail-closed tests for exact migration packages."""

import json
import shutil
from pathlib import Path
from typing import Never

import pytest
from asklegal_management_register.migration import MigrationViolation, apply_packages, load_package

_PACKAGE = Path(__file__).parents[1] / "migrations" / "000001_management_register_spike"
_M2_PACKAGE = Path(__file__).parents[1] / "migrations" / "000002_complete_m2_register"
_V1_REVIEW_PACKAGE = Path(__file__).parents[1] / "migrations" / "000003_review_ready_proposals"
_V1_DECISION_PACKAGE = Path(__file__).parents[1] / "migrations" / "000004_proposal_decisions"
_V1_CONSUMPTION_PACKAGE = (
    Path(__file__).parents[1] / "migrations" / "000005_registered_approval_consumption"
)
_V1_TERMINAL_PACKAGE = (
    Path(__file__).parents[1] / "migrations" / "000006_registered_approval_terminal_lifecycle"
)
_V1_EXECUTION_AUTHORIZATION_PACKAGE = (
    Path(__file__).parents[1] / "migrations" / "000007_registered_execution_authorization"
)
_V1_EXECUTION_BEGIN_PACKAGE = (
    Path(__file__).parents[1] / "migrations" / "000008_registered_execution_begin"
)
_V1_CLAIMED_EFFECT_READBACK_PACKAGE = (
    Path(__file__).parents[1] / "migrations" / "000009_claimed_effect_readback"
)
_V1_APPROVED_PROMOTION_WAKEUP_PACKAGE = (
    Path(__file__).parents[1] / "migrations" / "000010_approved_promotion_wakeup"
)
_V1_SERVING_STATE_PACKAGE = (
    Path(__file__).parents[1] / "migrations" / "000011_serving_state_transition"
)


def test_repository_migration_package_is_exact() -> None:
    """The checked-in package matches every declared byte and fingerprint."""
    package = load_package(_PACKAGE)
    assert package.migration_id == "000001"
    assert len(package.batches) == 5
    complete = load_package(_M2_PACKAGE)
    assert complete.migration_id == "000002"
    assert len(complete.batches) == 9
    review = load_package(_V1_REVIEW_PACKAGE)
    assert review.migration_id == "000003"
    assert len(review.batches) == 1
    decision = load_package(_V1_DECISION_PACKAGE)
    assert decision.migration_id == "000004"
    assert len(decision.batches) == 1
    consumption = load_package(_V1_CONSUMPTION_PACKAGE)
    assert consumption.migration_id == "000005"
    assert len(consumption.batches) == 1
    terminal = load_package(_V1_TERMINAL_PACKAGE)
    assert terminal.migration_id == "000006"
    assert len(terminal.batches) == 2
    authorization = load_package(_V1_EXECUTION_AUTHORIZATION_PACKAGE)
    assert authorization.migration_id == "000007"
    assert len(authorization.batches) == 1
    begin = load_package(_V1_EXECUTION_BEGIN_PACKAGE)
    assert begin.migration_id == "000008"
    assert len(begin.batches) == 1
    readback = load_package(_V1_CLAIMED_EFFECT_READBACK_PACKAGE)
    assert readback.migration_id == "000009"
    assert len(readback.batches) == 2
    create_batch = (readback.directory / readback.batches[0].path).read_bytes()
    permission_batch = (readback.directory / readback.batches[1].path).read_bytes()
    assert b"GRANT EXECUTE" not in create_batch
    assert b"GRANT EXECUTE" in permission_batch
    serving_state = load_package(_V1_SERVING_STATE_PACKAGE)
    assert serving_state.migration_id == "000011"
    assert tuple(batch.path for batch in serving_state.batches) == (
        "001_serving_state_tables.sql",
        "002_read_serving_state.sql",
        "003_activate_serving_state.sql",
        "004_rollback_serving_state.sql",
        "005_serving_state_permissions.sql",
    )
    wakeup = load_package(_V1_APPROVED_PROMOTION_WAKEUP_PACKAGE)
    assert wakeup.migration_id == "000010"
    assert tuple(batch.path for batch in wakeup.batches) == (
        "001_approved_promotion_wakeup_tables.sql",
        "002_claim_next_approved_promotion.sql",
        "003_acknowledge_approved_promotion_started.sql",
        "004_approved_promotion_wakeup_permissions.sql",
    )
    table_batch, claim_batch, acknowledgement_batch, permission_batch = (
        (wakeup.directory / batch.path).read_bytes() for batch in wakeup.batches
    )
    assert b"CREATE PROCEDURE" not in table_batch
    assert claim_batch.startswith(b"CREATE PROCEDURE")
    assert acknowledgement_batch.startswith(b"CREATE PROCEDURE")
    assert b"CREATE PROCEDURE" not in permission_batch
    assert b"GRANT EXECUTE" not in table_batch + claim_batch + acknowledgement_batch
    assert b"GRANT EXECUTE" in permission_batch


def test_approved_promotion_worker_guard_rejects_non_lower_hex_suffixes() -> None:
    """The package guard uses LIKE to reject malformed worker input before SQL selection."""
    wakeup = load_package(_V1_APPROVED_PROMOTION_WAKEUP_PACKAGE)
    claim_batch = (wakeup.directory / wakeup.batches[1].path).read_text(encoding="utf-8")
    guard = claim_batch.split("IF @worker_id IS NULL", maxsplit=1)[1].split(
        "THROW 52001", maxsplit=1
    )[0]

    assert "RIGHT(@worker_id, 48) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%'" in guard
    assert "NOT LIKE '%[^0-9a-f]%'" not in guard


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
