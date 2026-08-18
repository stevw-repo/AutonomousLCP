"""Fail-closed tests for the disabled V1 POC infrastructure topology."""

from copy import deepcopy
from pathlib import Path

import pytest

from tools.v1_poc_topology import (
    TopologyCode,
    TopologyReport,
    check_topology,
    load_topology,
    validate_topology,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _document() -> dict[str, object]:
    return load_topology(REPOSITORY_ROOT / "infrastructure/poc/topology.json")


def _service(document: dict[str, object], service_id: str) -> dict[str, object]:
    services = document["services"]
    assert isinstance(services, list)
    return next(
        service
        for service in services
        if isinstance(service, dict) and service.get("service_id") == service_id
    )


def _codes(document: dict[str, object]) -> set[TopologyCode]:
    return {finding.code for finding in validate_topology(document)}


def test_repository_topology_passes_with_exact_summary() -> None:
    """Keep the checked-in topology synchronized with its closed admission policy."""
    assert check_topology(REPOSITORY_ROOT) == TopologyReport(
        services=16,
        networks=10,
        credentials=25,
        pinned_artifacts=11,
        pins_required=5,
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("enable", TopologyCode.ARTIFACT),
        ("latest", TopologyCode.ARTIFACT),
        ("public", TopologyCode.SURFACE),
        ("secret", TopologyCode.SECRET),
        ("network", TopologyCode.NETWORK),
        ("vault", TopologyCode.VAULT),
        ("scheduler", TopologyCode.SCHEDULER),
        ("pinecone", TopologyCode.AUTHORITY),
        ("unknown", TopologyCode.INVENTORY),
    ],
)
def test_authority_and_isolation_regressions_fail_closed(
    mutation: str, expected_code: TopologyCode
) -> None:
    """Reject representative regressions before generating any runtime files."""
    document = deepcopy(_document())
    if mutation == "enable":
        _service(document, "control-plane")["enabled"] = True
    elif mutation == "latest":
        service = _service(document, "control-plane")
        service["artifact_state"] = "PINNED"
        service["artifact_ref"] = "asklegal/control-plane:latest"
    elif mutation == "public":
        listeners = _service(document, "review-api")["listeners"]
        assert isinstance(listeners, list)
        assert isinstance(listeners[0], dict)
        listeners[0]["scope"] = "PUBLIC"
    elif mutation == "secret":
        document["api_key"] = "do-not-store-secret-values"
    elif mutation == "network":
        networks = document["networks"]
        assert isinstance(networks, list)
        assert isinstance(networks[0], dict)
        members = networks[0]["members"]
        assert isinstance(members, list)
        members.pop()
    elif mutation == "vault":
        vaults = document["vaults"]
        assert isinstance(vaults, list)
        assert all(isinstance(vault, dict) for vault in vaults)
        vaults[1]["root"] = vaults[0]["root"]
    elif mutation == "scheduler":
        schedulers = document["scheduler_instances"]
        assert isinstance(schedulers, list)
        assert isinstance(schedulers[0], dict)
        schedulers[0]["loss_result"] = "RESUMED"
    elif mutation == "pinecone":
        pinecone = document["pinecone"]
        assert isinstance(pinecone, dict)
        pinecone["real_write_authorized"] = True
    else:
        document["unexpected"] = "field"
    assert expected_code in _codes(document)
