"""Fail-closed tests for the disabled V1 POC infrastructure topology."""

from copy import deepcopy
from pathlib import Path
from typing import cast

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
    for raw_service in _object_list(document["services"]):
        service = _object_map(raw_service)
        if service.get("service_id") == service_id:
            return service
    raise AssertionError(service_id)


def _object_map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _codes(document: dict[str, object]) -> set[TopologyCode]:
    return {finding.code for finding in validate_topology(document)}


def test_repository_topology_passes_with_exact_summary() -> None:
    """Keep the checked-in topology synchronized with its closed admission policy."""
    assert check_topology(REPOSITORY_ROOT) == TopologyReport(
        services=16,
        networks=10,
        credentials=26,
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
        listeners = _object_list(_service(document, "review-api")["listeners"])
        _object_map(listeners[0])["scope"] = "PUBLIC"
    elif mutation == "secret":
        document["api_key"] = "do-not-store-secret-values"
    elif mutation == "network":
        networks = _object_list(document["networks"])
        members = _object_list(_object_map(networks[0])["members"])
        members.pop()
    elif mutation == "vault":
        vaults = _object_list(document["vaults"])
        first_vault = _object_map(vaults[0])
        _object_map(vaults[1])["root"] = first_vault["root"]
    elif mutation == "scheduler":
        schedulers = _object_list(document["scheduler_instances"])
        _object_map(schedulers[0])["loss_result"] = "RESUMED"
    elif mutation == "pinecone":
        pinecone = _object_map(document["pinecone"])
        pinecone["real_write_authorized"] = True
    else:
        document["unexpected"] = "field"
    assert expected_code in _codes(document)
