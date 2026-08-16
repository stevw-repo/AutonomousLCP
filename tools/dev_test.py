"""Bootstrap the exact locked workspace and run its ordinary local test suite."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from tools.package_spike import load_manifest

_EXPECTED_UV_VERSION = "0.12.5"
_EXPECTED_NODE_VERSION = "v24.19.0"
_EXPECTED_PYTHON_VERSION = "Python 3.14.7"
_UV_VERSION_FIELD_COUNT = 3


class DeveloperTestFailure(RuntimeError):
    """The reproducible developer bootstrap or ordinary suite failed."""


def _run(
    command: list[str],
    *,
    root: Path,
    environment: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=root,
        env=environment,
        check=False,
        capture_output=capture_output,
        text=True,
    )


def _workspace_source_path(root: Path) -> str:
    manifest = load_manifest(root / "tools/package_spike_manifest.json")
    source_paths: list[str] = []
    for member in manifest.members:
        source_path = (root / member.path / "src").resolve()
        if not source_path.is_dir():
            raise DeveloperTestFailure(f"WORKSPACE_SOURCE_MISSING:{member.path}")
        source_paths.append(str(source_path))
    return os.pathsep.join(source_paths)


def run(uv_path: Path, node_path: Path, pytest_arguments: list[str]) -> None:
    """Validate the toolchain, sync the lock, and run ordinary local tests."""
    root = Path(__file__).resolve().parents[1]
    exact_uv = uv_path.expanduser().resolve()
    if not exact_uv.is_file() or not os.access(exact_uv, os.X_OK):
        raise DeveloperTestFailure("UV_EXECUTABLE_MISSING_OR_NOT_EXECUTABLE")

    version = _run([str(exact_uv), "--version"], root=root, capture_output=True)
    version_fields = version.stdout.strip().split(maxsplit=2)
    if (
        version.returncode != 0
        or len(version_fields) != _UV_VERSION_FIELD_COUNT
        or version_fields[:2] != ["uv", _EXPECTED_UV_VERSION]
    ):
        raise DeveloperTestFailure("UV_VERSION_MISMATCH")

    exact_node = node_path.expanduser().resolve()
    if not exact_node.is_file() or not os.access(exact_node, os.X_OK):
        raise DeveloperTestFailure("NODE_EXECUTABLE_MISSING_OR_NOT_EXECUTABLE")
    node_version = _run([str(exact_node), "--version"], root=root, capture_output=True)
    if (
        node_version.returncode != 0
        or node_version.stdout.strip() != _EXPECTED_NODE_VERSION
    ):
        raise DeveloperTestFailure("NODE_VERSION_MISMATCH")

    sync = _run(
        [str(exact_uv), "sync", "--frozen", "--all-packages"],
        root=root,
    )
    if sync.returncode != 0:
        raise DeveloperTestFailure("LOCKED_WORKSPACE_SYNC_FAILED")

    workspace_python = root / ".venv/bin/python"
    python_version = _run(
        [str(workspace_python), "--version"],
        root=root,
        capture_output=True,
    )
    if (
        python_version.returncode != 0
        or python_version.stdout.strip() != _EXPECTED_PYTHON_VERSION
    ):
        raise DeveloperTestFailure("PYTHON_VERSION_MISMATCH")

    test_environment = os.environ.copy()
    test_environment["ASKLEGAL_NODE_EXECUTABLE"] = str(exact_node)
    test_environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    test_environment["PYTHONPATH"] = _workspace_source_path(root)
    tests = _run(
        [str(workspace_python), "-m", "pytest", "-q", *pytest_arguments],
        root=root,
        environment=test_environment,
    )
    if tests.returncode != 0:
        raise DeveloperTestFailure("ORDINARY_TEST_SUITE_FAILED")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", required=True, type=Path, help="exact uv 0.12.5 executable")
    parser.add_argument("--node", required=True, type=Path, help="exact Node.js 24.19.0 executable")
    parser.add_argument(
        "pytest_arguments",
        nargs=argparse.REMAINDER,
        help="optional pytest arguments after --",
    )
    return parser


def main() -> int:
    """Run the command-line developer proof."""
    arguments = _parser().parse_args()
    try:
        run(arguments.uv, arguments.node, arguments.pytest_arguments)
    except DeveloperTestFailure as error:
        sys.stderr.write(f"FAIL {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
