"""Synthetic conformance cases for the Python boundary checker."""

import re
from pathlib import Path

import pytest

from tools.python_boundary_check import (
    ApprovedException,
    BoundaryCode,
    ExceptionKey,
    check_files,
    check_repository,
    discover_python_files,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _write_fixture(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("relative_path", "source", "expected_code"),
    [
        (
            "packages/domain/src/example.py",
            "from typing import Any\nvalue: Any\n",
            BoundaryCode.ANY,
        ),
        (
            "packages/domain/src/example.py",
            "import typing as t\nvalue: t.Any\n",
            BoundaryCode.ANY,
        ),
        (
            "packages/domain/src/example.py",
            "def values() -> dict:\n    return {}\n",
            BoundaryCode.UNPARAMETERIZED_COLLECTION,
        ),
        (
            "packages/domain/src/example.py",
            "from typing import cast\nvalue = cast(str, object())\n",
            BoundaryCode.CAST,
        ),
        (
            "packages/domain/src/example.py",
            "value = object()  # pyright: ignore[reportUnknownVariableType]\n",
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "packages/domain/src/example.py",
            "import os  # noqa: F401\n",
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "packages/domain/src/example.py",
            "from azure.storage.blob import BlobClient\n",
            BoundaryCode.INFRASTRUCTURE_IMPORT,
        ),
        (
            "packages/domain/src/example.py",
            "from fastapi import FastAPI\n",
            BoundaryCode.FRAMEWORK_IMPORT,
        ),
        (
            "packages/contracts/src/example.py",
            "from starlette.requests import Request\n",
            BoundaryCode.FRAMEWORK_IMPORT,
        ),
        (
            "apps/control_plane/src/example.py",
            "import pinecone\n",
            BoundaryCode.INFRASTRUCTURE_IMPORT,
        ),
    ],
)
def test_synthetic_violation_is_rejected(
    tmp_path: Path,
    relative_path: str,
    source: str,
    expected_code: BoundaryCode,
) -> None:
    """Reject one representative violation with its stable policy code."""
    path = _write_fixture(tmp_path, relative_path, source)
    findings = check_files(tmp_path, (path,))
    assert expected_code in {finding.code for finding in findings}


def test_parameterized_closed_annotations_pass(tmp_path: Path) -> None:
    """Accept closed fully parameterized collection annotations."""
    path = _write_fixture(
        tmp_path,
        "packages/domain/src/example.py",
        "type Names = tuple[str, ...]\ndef values(items: list[str]) -> dict[str, int]:\n"
        "    return {item: len(item) for item in items}\n",
    )
    assert check_files(tmp_path, (path,)) == ()


def test_repository_policy_passes_and_consumes_every_exception() -> None:
    """Keep the real source tree and its narrow exception register synchronized."""
    assert check_repository(REPOSITORY_ROOT) == ()


def test_discovery_includes_future_packages_and_applications(tmp_path: Path) -> None:
    """Discover new source and test trees without a manually maintained package list."""
    expected = {
        _write_fixture(tmp_path, "packages/new_domain/src/example.py", "value: str = 'x'\n"),
        _write_fixture(tmp_path, "packages/new_domain/tests/test_example.py", "value = 'x'\n"),
        _write_fixture(tmp_path, "apps/control/src/example.py", "value: str = 'x'\n"),
        _write_fixture(tmp_path, "apps/control/tests/test_example.py", "value = 'x'\n"),
    }
    assert set(discover_python_files(tmp_path)) == expected


def test_pyright_configuration_is_strict_and_repository_wide() -> None:
    """Prevent the official type-check gate from being narrowed silently."""
    configuration = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'typeCheckingMode\s*=\s*"strict"', configuration) is not None
    assert re.search(r'pythonVersion\s*=\s*"3\.14"', configuration) is not None
    assert re.search(r'include\s*=\s*\[\s*"\."\s*,?\s*\]', configuration) is not None
    assert 'reportMissingTypeStubs = "error"' in configuration
    assert 'reportUnnecessaryTypeIgnoreComment = "error"' in configuration


def test_stale_exception_is_rejected(tmp_path: Path) -> None:
    """Fail when reviewed exception coordinates no longer contain the exception."""
    relative_path = "packages/domain/src/example.py"
    path = _write_fixture(tmp_path, relative_path, "value: str = 'x'\n")
    exception = ApprovedException(
        ExceptionKey(relative_path, 1, BoundaryCode.CAST),
        "synthetic reviewed reason long enough for the policy",
    )
    findings = check_files(
        tmp_path,
        (path,),
        (exception,),
        require_all_exceptions=True,
    )
    assert {finding.code for finding in findings} == {BoundaryCode.INVALID_POLICY}
