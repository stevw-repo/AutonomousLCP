"""Focused local proofs for exact archive-before-cleanup composition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import hk_v1_archive_cleanup as archive
from tools.hk_v1_archive_cleanup import (
    ArchiveCleanupPlan,
    ArchiveProtectionSet,
    archive_cleanup_authority_bytes,
    archive_cleanup_plan_bytes,
    build_archive_cleanup_plan,
    execute_archive_cleanup,
    load_archive_cleanup_plan,
    main,
)

_AUTHORITY_ID = "auth_" + "1" * 48


def _protected(tmp_path: Path) -> ArchiveProtectionSet:
    protected = tmp_path / "protected"
    protected.mkdir()
    names = (
        "approval_state",
        "current_baseline",
        "fixtures",
        "latest_journals",
        "promotion_evidence",
    )
    paths = tuple(protected / name for name in names)
    for path in paths:
        path.mkdir()
    return ArchiveProtectionSet(
        latest_journals=(paths[3],),
        current_baseline=(paths[1],),
        fixtures=(paths[2],),
        approval_state=(paths[0],),
        promotion_evidence=(paths[4],),
    )


def _source(tmp_path: Path, name: str = "old-cycle") -> Path:
    source = tmp_path / name
    nested = source / "nested"
    nested.mkdir(parents=True)
    source.joinpath("root.json").write_bytes(b'{"retained":true}')
    nested.joinpath("evidence.bin").write_bytes(b"exact-evidence")
    return source


def _plan(tmp_path: Path) -> ArchiveCleanupPlan:
    destination = tmp_path / "archive"
    destination.mkdir()
    return build_archive_cleanup_plan(
        (_source(tmp_path),),
        destination,
        _protected(tmp_path),
    )


def _authority(tmp_path: Path, plan: ArchiveCleanupPlan) -> Path:
    path = tmp_path / "authority.json"
    path.write_bytes(archive_cleanup_authority_bytes(plan, _AUTHORITY_ID))
    return path


def test_plan_inventories_explicit_recursive_metadata_and_cli_is_plan_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Default CLI reports exact metadata and performs no copy or deletion."""
    source = _source(tmp_path)
    destination = tmp_path / "archive"
    destination.mkdir()
    protections = _protected(tmp_path)
    arguments = [
        "--destination",
        str(destination),
        "--candidate",
        str(source),
        "--latest-journal",
        str(protections.latest_journals[0]),
        "--current-baseline",
        str(protections.current_baseline[0]),
        "--fixture",
        str(protections.fixtures[0]),
        "--approval-state",
        str(protections.approval_state[0]),
        "--promotion-evidence",
        str(protections.promotion_evidence[0]),
    ]

    assert main(arguments) == 0
    document = json.loads(capsys.readouterr().out)
    candidate = document["candidates"][0]
    assert candidate["byte_length"] == len(b'{"retained":true}') + len(b"exact-evidence")
    assert candidate["fingerprint"].startswith("sha256:")
    assert {member["relative_path"] for member in candidate["members"]} == {
        ".",
        "nested",
        "nested/evidence.bin",
        "root.json",
    }
    assert all("mode" in member and "mtime_ns" in member for member in candidate["members"])
    assert source.exists()
    assert not any(destination.iterdir())


@pytest.mark.parametrize(
    "category",
    [
        "latest_journals",
        "current_baseline",
        "fixtures",
        "approval_state",
        "promotion_evidence",
    ],
)
def test_every_required_protection_category_blocks_cleanup(tmp_path: Path, category: str) -> None:
    """Latest state, fixtures, Approval, and promotion evidence are never candidates."""
    destination = tmp_path / "archive"
    destination.mkdir()
    protections = _protected(tmp_path)
    protected_by_category = {
        "approval_state": protections.approval_state,
        "current_baseline": protections.current_baseline,
        "fixtures": protections.fixtures,
        "latest_journals": protections.latest_journals,
        "promotion_evidence": protections.promotion_evidence,
    }
    candidate = protected_by_category[category][0]
    with pytest.raises(ValueError, match="protected archive source"):
        build_archive_cleanup_plan((candidate,), destination, protections)


def test_destination_must_be_distinct_from_every_candidate(tmp_path: Path) -> None:
    """An archive cannot be written inside a tree it will delete."""
    source = _source(tmp_path)
    destination = source / "archive"
    destination.mkdir()
    with pytest.raises(ValueError, match="destination must be distinct"):
        build_archive_cleanup_plan((source,), destination, _protected(tmp_path))


@pytest.mark.parametrize("mutation", ["ROOT_SYMLINK", "NESTED_SYMLINK", "TRAVERSAL"])
def test_symlink_and_traversal_candidates_fail_closed(tmp_path: Path, mutation: str) -> None:
    """Inventory never follows an alias or normalized traversal path."""
    real = _source(tmp_path)
    destination = tmp_path / "archive"
    destination.mkdir()
    candidate = real
    if mutation == "ROOT_SYMLINK":
        candidate = tmp_path / "alias"
        candidate.symlink_to(real, target_is_directory=True)
    elif mutation == "NESTED_SYMLINK":
        real.joinpath("nested-link").symlink_to(real / "nested", target_is_directory=True)
    else:
        candidate = tmp_path / "unused" / ".." / real.name
    with pytest.raises(ValueError, match="archive source"):
        build_archive_cleanup_plan((candidate,), destination, _protected(tmp_path))


def test_wrong_authority_is_inert_before_copy_or_delete(tmp_path: Path) -> None:
    """Authority for a different exact inventory cannot mutate either tree."""
    plan = _plan(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(archive_cleanup_plan_bytes(plan))
    drifted_source = _source(tmp_path, "different-cycle")
    drifted = build_archive_cleanup_plan((drifted_source,), plan.destination, plan.protections)
    authority = tmp_path / "authority.json"
    authority.write_bytes(archive_cleanup_authority_bytes(drifted, _AUTHORITY_ID))

    with pytest.raises(ValueError, match="archive authority"):
        execute_archive_cleanup(load_archive_cleanup_plan(plan_path), authority)

    assert plan.candidates[0].source_path.exists()
    assert tuple(plan.destination.iterdir()) == ()


def test_verified_recursive_copy_precedes_exact_delete_and_replays(tmp_path: Path) -> None:
    """A retained plan replays after sources are deleted without copying or deleting broadly."""
    plan = _plan(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(archive_cleanup_plan_bytes(plan))
    authority = _authority(tmp_path, plan)
    loaded = load_archive_cleanup_plan(plan_path)

    first = execute_archive_cleanup(loaded, authority)
    assert first.complete is True
    assert not loaded.candidates[0].source_path.exists()
    archived = plan.destination / plan.plan_id / "items" / "0001-old-cycle"
    assert archived.joinpath("nested/evidence.bin").read_bytes() == b"exact-evidence"
    unrelated = tmp_path / "unrelated"
    unrelated.write_bytes(b"preserved")

    replay = execute_archive_cleanup(load_archive_cleanup_plan(plan_path), authority)
    assert replay == first
    assert unrelated.read_bytes() == b"preserved"


def test_copy_readback_or_source_drift_never_deletes_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed recursive copy fails before the exact source deletion boundary."""
    plan = _plan(tmp_path)
    authority = _authority(tmp_path, plan)
    original = archive.shutil.copytree

    def corrupting_copy(source: Path, target: Path, *, symlinks: bool) -> Path:
        monkeypatch.setattr(archive.shutil, "copytree", original)
        result = original(source, target, symlinks=symlinks)
        monkeypatch.setattr(archive.shutil, "copytree", corrupting_copy)
        target.joinpath("nested/evidence.bin").write_bytes(b"corrupted")
        return result

    monkeypatch.setattr(archive.shutil, "copytree", corrupting_copy)
    with pytest.raises(ValueError, match="readback mismatch"):
        execute_archive_cleanup(plan, authority)
    assert plan.candidates[0].source_path.exists()


def test_interrupted_after_copy_resumes_from_verified_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restart verifies the retained archive before resuming exact deletion."""
    plan = _plan(tmp_path)
    authority = _authority(tmp_path, plan)
    original = archive.shutil.rmtree

    def interrupt_source(path: Path) -> None:
        if path == plan.candidates[0].source_path:
            message = "synthetic interruption"
            raise OSError(message)
        original(path)

    monkeypatch.setattr(archive.shutil, "rmtree", interrupt_source)
    with pytest.raises(OSError, match="synthetic interruption"):
        execute_archive_cleanup(plan, authority)
    assert plan.candidates[0].source_path.exists()
    archived = plan.destination / plan.plan_id / "items" / plan.candidates[0].archive_name
    assert archived.exists()

    monkeypatch.setattr(archive.shutil, "rmtree", original)
    result = execute_archive_cleanup(plan, authority)
    assert result.complete is True
    assert not plan.candidates[0].source_path.exists()


def test_source_metadata_drift_after_plan_blocks_before_deletion(tmp_path: Path) -> None:
    """Changed bytes or metadata invalidate authority rather than being silently archived."""
    plan = _plan(tmp_path)
    authority = _authority(tmp_path, plan)
    plan.candidates[0].source_path.joinpath("root.json").write_bytes(b'{"drift":true}')

    with pytest.raises(ValueError, match="source drift"):
        execute_archive_cleanup(plan, authority)
    assert plan.candidates[0].source_path.exists()
    assert tuple((plan.destination / plan.plan_id / "items").iterdir()) == ()


def test_destination_symlink_swap_is_inert(tmp_path: Path) -> None:
    """Execution revalidates the approved destination before staging any copy."""
    plan = _plan(tmp_path)
    authority = _authority(tmp_path, plan)
    retained_destination = tmp_path / "retained-archive"
    plan.destination.rename(retained_destination)
    plan.destination.symlink_to(retained_destination, target_is_directory=True)

    with pytest.raises(ValueError, match="archive destination"):
        execute_archive_cleanup(plan, authority)

    assert plan.candidates[0].source_path.exists()
    assert tuple(retained_destination.iterdir()) == ()
