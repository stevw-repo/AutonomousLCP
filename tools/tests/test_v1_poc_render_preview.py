"""Focused no-install preview-tree tests for the V1 unit renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.v1_poc_render_units import OUTPUT_ROOT, render, write_preview

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _tree(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mode & 0o777)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_preview_trees_are_exact_and_do_not_touch_checked_in_units(tmp_path: Path) -> None:
    """Two explicit outputs contain identical complete trees without installation."""
    checked_in_before = _tree(REPOSITORY_ROOT / OUTPUT_ROOT)
    first = tmp_path / "run-1"
    second = tmp_path / "run-2"

    assert write_preview(REPOSITORY_ROOT, first) == tuple(sorted(render(REPOSITORY_ROOT)))
    assert write_preview(REPOSITORY_ROOT, second) == tuple(sorted(render(REPOSITORY_ROOT)))

    assert _tree(first) == _tree(second)
    assert _tree(REPOSITORY_ROOT / OUTPUT_ROOT) == checked_in_before
    assert all(
        mode == (0o755 if name.endswith(".sh") else 0o644)
        for name, (_, mode) in _tree(first).items()
    )


def test_preview_refuses_existing_or_symlink_output(tmp_path: Path) -> None:
    """Preview never overwrites a prior review tree or follows a caller symlink."""
    existing = tmp_path / "existing"
    existing.mkdir()
    link = tmp_path / "link"
    link.symlink_to(existing, target_is_directory=True)

    for output in (existing, link):
        with pytest.raises(ValueError, match="preview output already exists"):
            write_preview(REPOSITORY_ROOT, output)
