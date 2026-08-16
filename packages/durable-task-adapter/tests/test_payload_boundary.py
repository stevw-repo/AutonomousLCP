"""Closed payload and deterministic-orchestrator boundary proofs."""

import ast
from pathlib import Path

import pytest
from asklegal_durable_task.models import (
    MAX_HISTORY_PAYLOAD_BYTES,
    PayloadBoundaryViolation,
    WorkflowInput,
    validate_payload,
)
from durable_test_support import workflow_input


def test_every_workflow_input_field_is_opaque_and_bounded() -> None:
    """Accept the exact small fingerprint-and-ID-only workflow input."""
    request = workflow_input("payload-execution")
    validate_payload(request.to_json())


def test_payload_above_internal_64_kib_ceiling_is_rejected() -> None:
    """Reject a scheduler value before it crosses the local history boundary."""
    with pytest.raises(PayloadBoundaryViolation, match="DURABLE_PAYLOAD_TOO_LARGE"):
        validate_payload({"opaque": "x" * MAX_HISTORY_PAYLOAD_BYTES})


def test_invalid_fingerprint_is_rejected() -> None:
    """Reject an unbound value where an exact fingerprint is required."""
    request = workflow_input("invalid-fingerprint-execution")
    with pytest.raises(PayloadBoundaryViolation, match="DURABLE_FINGERPRINT_INVALID"):
        WorkflowInput(
            execution_id=request.execution_id,
            workflow_version=request.workflow_version,
            build_fingerprint="not-a-fingerprint",
            configuration_fingerprint=request.configuration_fingerprint,
            contract_fingerprint=request.contract_fingerprint,
            input_fingerprint=request.input_fingerprint,
            effect_command_id=request.effect_command_id,
            effect_command_fingerprint=request.effect_command_fingerprint,
        )


def test_orchestrator_module_has_no_effect_capable_imports() -> None:
    """Keep filesystem, network, database, clock, and randomness out of orchestration code."""
    source_path = (
        Path(__file__).resolve().parents[1] / "src" / "asklegal_durable_task" / "workflow.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_roots = {"azure", "mssql_python", "os", "pathlib", "random", "socket", "time"}
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.partition(".")[0])
    assert imported_roots.isdisjoint(forbidden_roots)
