"""Exact command-surface proofs for the complete local shipping gate."""

from pathlib import Path

from tools.dev_test import require_host_entrypoint_grammar, shipping_gate_commands

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_shipping_gate_owns_every_repository_wide_boundary() -> None:
    """A passing pytest run alone must never be reported as a shipping proof."""
    node_path = Path("/exact/node")
    workspace_python = REPOSITORY_ROOT / ".venv/bin/python"

    commands = shipping_gate_commands(REPOSITORY_ROOT, node_path, workspace_python)

    assert tuple(failure for failure, _command in commands) == (
        "STRICT_PYRIGHT_FAILED",
        "RUFF_LINT_FAILED",
        "RUFF_FORMAT_FAILED",
        "PYTHON_BOUNDARY_FAILED",
        "ARCHITECTURE_BOUNDARY_FAILED",
        "CONTRACT_VALIDATION_FAILED",
    )
    assert commands[0][1] == (
        str(node_path),
        str(REPOSITORY_ROOT / "node_modules/pyright/index.js"),
    )
    assert commands[-1][1] == (str(node_path), "tools/validate-contracts.mjs")


def test_shipping_gate_entrypoints_parse_as_python_3_12() -> None:
    """The documented system-Python launcher must remain able to import every gate."""
    require_host_entrypoint_grammar(REPOSITORY_ROOT)
