"""Fail-closed tests for V1 POC application runtime-input contracts."""

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from asklegal_application_runtime import (
    V1_LOGICAL_DESTINATIONS,
    required_v1_dependencies,
)

from tools.v1_poc_application_runtime import (
    RUNTIME_POLICY_PATH,
    TOPOLOGY_PATH,
    RuntimeInputCode,
    RuntimeInputReport,
    check_runtime_input_policy,
    validate_runtime_input_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_bytes())
    return _object_map(value)


def _object_map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _item_by_id(value: object, service_id: str) -> dict[str, object]:
    for raw_item in _object_list(value):
        item = _object_map(raw_item)
        if item.get("service_id") == service_id:
            return item
    raise AssertionError(service_id)


def _policy() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / RUNTIME_POLICY_PATH)


def _application(policy: dict[str, object], service_id: str) -> dict[str, object]:
    return _item_by_id(policy["applications"], service_id)


def _codes(
    policy: dict[str, object], topology: dict[str, object] | None = None
) -> set[RuntimeInputCode]:
    return {
        finding.code
        for finding in validate_runtime_input_policy(
            policy, topology or _object(REPOSITORY_ROOT / TOPOLOGY_PATH)
        )
    }


def test_runtime_inputs_are_complete_exact_and_disabled() -> None:
    """Bind all five applications without claiming runtime readiness or admission."""
    assert check_runtime_input_policy(REPOSITORY_ROOT) == RuntimeInputReport(
        applications=5,
        credentials=20,
        logical_destinations=26,
        blockers=(
            "SYSTEMD_CREDENTIAL_DELIVERY_PROOF",
            "SQL_SERVER_CERTIFICATE_TRUST",
            "VAULT_SERVER_CERTIFICATE_TRUST",
            "UBUNTU_RUNTIME_PROOF",
        ),
        admitted=0,
    )

    policy = _policy()
    applications = _object_list(policy["applications"])
    for raw_application in applications:
        application = _object_map(raw_application)
        application_code = application["application_code"]
        assert isinstance(application_code, str)
        assert application["readiness_dependency_codes"] == [
            dependency.value for dependency in required_v1_dependencies(application_code)
        ]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("authority", RuntimeInputCode.AUTHORITY),
        ("database", RuntimeInputCode.DATABASE),
        ("credential", RuntimeInputCode.CREDENTIAL),
        ("destination", RuntimeInputCode.DESTINATION),
        ("task_hub", RuntimeInputCode.TASK_HUB),
        ("vault", RuntimeInputCode.VAULT),
        ("vault_profile", RuntimeInputCode.VAULT),
        ("admit", RuntimeInputCode.ADMISSION),
        ("secret", RuntimeInputCode.SECRET),
        ("schema", RuntimeInputCode.INVENTORY),
    ],
)
def test_runtime_input_drift_fails_closed(mutation: str, expected_code: RuntimeInputCode) -> None:
    """Reject authority, capability, topology, secret, and readiness drift."""
    policy = deepcopy(_policy())
    if mutation == "authority":
        authority = _object_map(policy["authority"])
        authority["service_enablement_authorized"] = True
    elif mutation == "database":
        _application(policy, "review-api")["database_role"] = "dbo"
    elif mutation == "credential":
        _application(policy, "control-plane")["credential_filenames"] = ["sql-control"]
    elif mutation == "destination":
        _application(policy, "promotion-worker")["destination_service_ids"] = ["sql-server"]
    elif mutation == "task_hub":
        _application(policy, "acquisition-worker")["task_hub"] = "promotion"
    elif mutation == "vault":
        _application(policy, "legal-processing-worker")["vault_service_ids"] = ["vault-recovery"]
    elif mutation == "vault_profile":
        profile = _object_map(policy["vault_client_profile"])
        profile["ambient_credentials_forbidden"] = False
    elif mutation == "admit":
        _application(policy, "review-api")["admitted"] = True
    elif mutation == "secret":
        policy["api_key"] = "must-not-exist"
    else:
        _application(policy, "control-plane")["unexpected"] = "field"
    assert expected_code in _codes(policy)


def test_runtime_readiness_dependency_drift_fails_closed() -> None:
    """Do not silently remove a mandatory application dependency probe."""
    policy = deepcopy(_policy())
    _application(policy, "control-plane")["readiness_dependency_codes"] = ["MANAGEMENT_REGISTER"]
    assert RuntimeInputCode.READINESS in _codes(policy)


def test_topology_identity_network_listener_and_scheduler_drift_fail_closed() -> None:
    """Keep runtime inputs bound to the disabled topology and scheduler inventory."""
    topology = _object(REPOSITORY_ROOT / TOPOLOGY_PATH)
    review = _item_by_id(topology["services"], "review-api")
    review["identity"] = "wrong-identity"
    assert RuntimeInputCode.TOPOLOGY in _codes(_policy(), topology)

    topology = _object(REPOSITORY_ROOT / TOPOLOGY_PATH)
    general = _item_by_id(topology["scheduler_instances"], "dts-general")
    general["task_hubs"] = ["control", "legal-processing"]
    assert RuntimeInputCode.TASK_HUB in _codes(_policy(), topology)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "wrong_host",
        "wrong_port",
        "wrong_scheme",
        "unshared_network",
        "extra_field",
    ],
)
def test_logical_destination_drift_fails_closed(mutation: str) -> None:
    """Every destination must equal the one the accepted topology implies."""
    policy = deepcopy(_policy())
    application = _application(policy, "control-plane")
    destinations = _object_list(application["logical_destinations"])
    first = _object_map(destinations[0])
    if mutation == "missing":
        destinations.pop()
    elif mutation == "extra":
        destinations.append(deepcopy(first))
    elif mutation == "wrong_host":
        first["host"] = "127.0.0.1"
    elif mutation == "wrong_port":
        first["port"] = 9999
    elif mutation == "wrong_scheme":
        first["scheme"] = "HTTP"
    elif mutation == "unshared_network":
        first["network"] = "asklegal-vault-recovery"
    else:
        first["unexpected"] = "field"
    assert RuntimeInputCode.DESTINATION in _codes(policy)


def test_destinations_follow_the_topology_rather_than_a_local_copy() -> None:
    """Changing a topology listener must invalidate the resolution, not be ignored."""
    topology = deepcopy(_object(REPOSITORY_ROOT / TOPOLOGY_PATH))
    service = _item_by_id(topology["services"], "sql-server")
    listeners = _object_list(service["listeners"])
    first = _object_map(listeners[0])
    first["port"] = 14330
    assert RuntimeInputCode.DESTINATION in _codes(_policy(), topology)


def test_destination_table_matches_the_runtime_contract_exactly() -> None:
    """The package table and the checked-in contract are one fact, not two."""
    policy = _policy()
    applications = _object_list(policy["applications"])
    assert len(applications) == len(V1_LOGICAL_DESTINATIONS)
    for raw_application in applications:
        application = _object_map(raw_application)
        code = application["application_code"]
        assert isinstance(code, str)
        destinations = _object_list(application["logical_destinations"])
        dependencies = _object_list(application["readiness_dependency_codes"])
        table = V1_LOGICAL_DESTINATIONS[code]
        assert tuple(item.value for item in table) == tuple(dependencies)
        contract: dict[str, tuple[str, int]] = {}
        for raw_item in destinations:
            item = _object_map(raw_item)
            service_id = item["service_id"]
            host = item["host"]
            port = item["port"]
            assert isinstance(service_id, str)
            assert isinstance(host, str)
            assert isinstance(port, int)
            contract[service_id] = (host, port)
        for host, port in table.values():
            assert contract[host] == (host, port)
