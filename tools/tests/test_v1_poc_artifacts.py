"""Fail-closed tests for V1 POC artifact admission."""

from copy import deepcopy
from pathlib import Path

import pytest

from tools.v1_poc_artifacts import (
    ARTIFACT_POLICY_PATH,
    ArtifactCode,
    ArtifactReport,
    check_artifact_policy,
    load_artifact_policy,
    validate_artifact_policy,
)
from tools.v1_poc_topology import TOPOLOGY_PATH, load_topology

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _policy() -> dict[str, object]:
    return load_artifact_policy(REPOSITORY_ROOT / ARTIFACT_POLICY_PATH)


def _topology() -> dict[str, object]:
    return load_topology(REPOSITORY_ROOT / TOPOLOGY_PATH)


def _artifact(policy: dict[str, object], artifact_id: str) -> dict[str, object]:
    artifacts = policy["artifacts"]
    assert isinstance(artifacts, list)
    return next(
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and artifact.get("artifact_id") == artifact_id
    )


def _codes(
    policy: dict[str, object], topology: dict[str, object] | None = None
) -> set[ArtifactCode]:
    actual_topology = _topology() if topology is None else topology
    return {item.code for item in validate_artifact_policy(policy, actual_topology)}


def test_repository_artifact_inventory_passes_but_admits_nothing() -> None:
    """Cover every service while keeping selection and admission state honest."""
    assert check_artifact_policy(REPOSITORY_ROOT) == ArtifactReport(
        artifacts=12,
        consumers=16,
        pinned_candidates=2,
        selections_pending=10,
        admitted=0,
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("admit", ArtifactCode.ADMISSION),
        ("authority", ArtifactCode.AUTHORITY),
        ("consumer", ArtifactCode.COVERAGE),
        ("floating", ArtifactCode.PIN),
        ("secret", ArtifactCode.SECRET),
        ("credential_gate", ArtifactCode.ADMISSION),
        ("schema", ArtifactCode.INVENTORY),
    ],
)
def test_artifact_policy_regressions_fail_closed(
    mutation: str, expected_code: ArtifactCode
) -> None:
    """Reject false admission, mutable artifacts, secret values, and drift."""
    policy = deepcopy(_policy())
    if mutation == "admit":
        _artifact(policy, "sql-server")["admitted"] = True
    elif mutation == "authority":
        authority = policy["authority"]
        assert isinstance(authority, dict)
        authority["registry_pull_authorized"] = True
    elif mutation == "consumer":
        _artifact(policy, "control-plane")["consumers"] = []
    elif mutation == "floating":
        sql = _artifact(policy, "sql-server")
        sql["artifact_ref"] = "mcr.microsoft.com/mssql/server:latest"
    elif mutation == "secret":
        policy["api_key"] = "must-not-exist"
    elif mutation == "credential_gate":
        _artifact(policy, "versity-gateway")["credential_interface_gate"] = False
    else:
        _artifact(policy, "grafana")["unexpected"] = "field"
    assert expected_code in _codes(policy)


def test_topology_pin_drift_fails_closed() -> None:
    """Bind the artifact registry to the exact service topology references."""
    topology = deepcopy(_topology())
    services = topology["services"]
    assert isinstance(services, list)
    sql = next(
        service
        for service in services
        if isinstance(service, dict) and service.get("service_id") == "sql-server"
    )
    sql["artifact_ref"] = "mcr.microsoft.com/mssql/server@sha256:" + ("0" * 64)
    assert ArtifactCode.PIN in _codes(_policy(), topology)
