"""Bootstrap the exact locked workspace and run its complete shipping gate."""

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

from tools.package_spike import load_manifest
from tools.v1_poc_admission import check_v1_admission
from tools.v1_poc_application_images import check_application_image_policy
from tools.v1_poc_application_runtime import check_runtime_input_policy
from tools.v1_poc_artifacts import check_artifact_policy
from tools.v1_poc_credential_interface import check_credential_interface_policy
from tools.v1_poc_host_admission import check_policy
from tools.v1_poc_host_identities import check_host_identity_policy
from tools.v1_poc_render_provisioning import check as check_provisioning
from tools.v1_poc_render_units import check as check_units
from tools.v1_poc_systemd_units import check_systemd_input_policy
from tools.v1_poc_topology import check_topology
from tools.v1_poc_wheelhouse import check_wheelhouse

_EXPECTED_UV_VERSION = "0.12.5"
_EXPECTED_NODE_VERSION = "v24.19.0"
_EXPECTED_PYTHON_VERSION = "Python 3.14.7"
_UV_VERSION_FIELD_COUNT = 3
_HOST_PYTHON_FEATURE_VERSION = (3, 12)
_MINIMUM_HOST_ENTRYPOINTS = 10


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


def _require_current_provisioning(root: Path) -> None:
    """Reject rendered provisioning scripts that no longer match the contracts."""
    drifted = check_provisioning(root)
    if drifted:
        message = f"PROVISIONING_SCRIPTS_STALE:{','.join(drifted)}"
        raise DeveloperTestFailure(message)


def _require_current_units(root: Path) -> None:
    """Reject rendered units that no longer match the contracts."""
    drifted = check_units(root)
    if drifted:
        message = f"SYSTEMD_UNITS_STALE:{','.join(drifted)}"
        raise DeveloperTestFailure(message)


def _workspace_source_path(root: Path) -> str:
    manifest = load_manifest(root / "tools/package_spike_manifest.json")
    source_paths: list[str] = []
    for member in manifest.members:
        source_path = (root / member.path / "src").resolve()
        if not source_path.is_dir():
            raise DeveloperTestFailure(f"WORKSPACE_SOURCE_MISSING:{member.path}")
        source_paths.append(str(source_path))
    return os.pathsep.join(source_paths)


def require_host_entrypoint_grammar(root: Path) -> None:
    """Keep every system-Python gate importable on the Ubuntu 24.04 host."""
    entrypoints = sorted(
        [
            *(root / "tools").glob("v1_poc_*.py"),
            root / "tools/dev_test.py",
            root / "tools/python_boundary_check.py",
        ]
    )
    if len(entrypoints) < _MINIMUM_HOST_ENTRYPOINTS:
        raise DeveloperTestFailure("HOST_ENTRYPOINT_INVENTORY_INVALID")
    for path in entrypoints:
        try:
            ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
                feature_version=_HOST_PYTHON_FEATURE_VERSION,
            )
        except (OSError, SyntaxError) as error:
            raise DeveloperTestFailure(f"HOST_ENTRYPOINT_GRAMMAR_FAILED:{path.name}") from error


def shipping_gate_commands(
    root: Path,
    node_path: Path,
    workspace_python: Path,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the exact locked, repository-wide gates that precede pytest."""
    return (
        (
            "STRICT_PYRIGHT_FAILED",
            (
                str(node_path),
                str(root / "node_modules/pyright/index.js"),
            ),
        ),
        ("RUFF_LINT_FAILED", (str(workspace_python), "-m", "ruff", "check", ".")),
        (
            "RUFF_FORMAT_FAILED",
            (str(workspace_python), "-m", "ruff", "format", "--check", "."),
        ),
        (
            "PYTHON_BOUNDARY_FAILED",
            (str(workspace_python), "tools/python_boundary_check.py"),
        ),
        (
            "ARCHITECTURE_BOUNDARY_FAILED",
            (str(workspace_python), "tools/architecture_spike.py"),
        ),
        (
            "CONTRACT_VALIDATION_FAILED",
            (str(node_path), "tools/validate-contracts.mjs"),
        ),
    )


def _require_v1_static_admission(root: Path) -> None:
    try:
        check_topology(root)
        check_policy(root)
        check_artifact_policy(root)
        check_credential_interface_policy(root)
        check_application_image_policy(root)
        check_wheelhouse(root)
        _require_current_provisioning(root)
        _require_current_units(root)
        check_runtime_input_policy(root)
        check_systemd_input_policy(root)
        check_host_identity_policy(root)
        check_v1_admission(root)
    except (OSError, TypeError, ValueError) as error:
        raise DeveloperTestFailure("V1_POC_STATIC_ADMISSION_FAILED") from error


def _prepare_locked_workspace(
    root: Path,
    uv_path: Path,
    node_path: Path,
) -> tuple[Path, Path]:
    """Validate exact tools, validate the lock, sync, and return the pinned Python."""
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
    if node_version.returncode != 0 or node_version.stdout.strip() != _EXPECTED_NODE_VERSION:
        raise DeveloperTestFailure("NODE_VERSION_MISMATCH")

    lock_check = _run([str(exact_uv), "lock", "--check"], root=root)
    if lock_check.returncode != 0:
        raise DeveloperTestFailure("WORKSPACE_LOCK_INVALID")

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
    if python_version.returncode != 0 or python_version.stdout.strip() != _EXPECTED_PYTHON_VERSION:
        raise DeveloperTestFailure("PYTHON_VERSION_MISMATCH")
    return exact_node, workspace_python


def _require_shipping_gates(
    root: Path,
    exact_node: Path,
    workspace_python: Path,
    environment: dict[str, str],
) -> None:
    for failure, command in shipping_gate_commands(root, exact_node, workspace_python):
        gate = _run(list(command), root=root, environment=environment)
        if gate.returncode != 0:
            raise DeveloperTestFailure(failure)


def run(uv_path: Path, node_path: Path, pytest_arguments: list[str]) -> None:
    """Validate the toolchain, sync the lock, and run the complete shipping gate."""
    root = Path(__file__).resolve().parents[1]
    require_host_entrypoint_grammar(root)
    _require_v1_static_admission(root)
    exact_node, workspace_python = _prepare_locked_workspace(root, uv_path, node_path)

    test_environment = os.environ.copy()
    test_environment["ASKLEGAL_NODE_EXECUTABLE"] = str(exact_node)
    test_environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    test_environment["PYTHONPATH"] = _workspace_source_path(root)
    _require_shipping_gates(root, exact_node, workspace_python, test_environment)
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
