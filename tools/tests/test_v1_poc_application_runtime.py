"""Fail-closed tests for V1 POC application runtime-input contracts."""

import json
from copy import deepcopy
from pathlib import Path

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
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _policy() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / RUNTIME_POLICY_PATH)


def _application(policy: dict[str, object], service_id: str) -> dict[str, object]:
    applications = policy["applications"]
    assert isinstance(applications, list)
    return next(
        item
        for item in applications
        if isinstance(item, dict) and item.get("service_id") == service_id
    )


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
        logical_destinations=25,
        blockers=(
            "SYSTEMD_CREDENTIAL_DELIVERY_PROOF",
            "SQL_SERVER_CERTIFICATE_TRUST",
            "VAULT_SERVER_CERTIFICATE_TRUST",
            "UBUNTU_RUNTIME_PROOF",
        ),
        admitted=0,
    )

    policy = _policy()
    applications = policy["applications"]
    assert isinstance(applications, list)
    for application in applications:
        assert isinstance(application, dict)
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
        authority = policy["authority"]
        assert isinstance(authority, dict)
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
        profile = policy["vault_client_profile"]
        assert isinstance(profile, dict)
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
    services = topology["services"]
    assert isinstance(services, list)
    review = next(
        item
        for item in services
        if isinstance(item, dict) and item.get("service_id") == "review-api"
    )
    review["identity"] = "wrong-identity"
    assert RuntimeInputCode.TOPOLOGY in _codes(_policy(), topology)

    topology = _object(REPOSITORY_ROOT / TOPOLOGY_PATH)
    schedulers = topology["scheduler_instances"]
    assert isinstance(schedulers, list)
    general = next(
        item
        for item in schedulers
        if isinstance(item, dict) and item.get("service_id") == "dts-general"
    )
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
    destinations = application["logical_destinations"]
    assert isinstance(destinations, list)
    first = destinations[0]
    assert isinstance(first, dict)
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
    services = topology["services"]
    assert isinstance(services, list)
    for service in services:
        if isinstance(service, dict) and service.get("service_id") == "sql-server":
            listeners = service["listeners"]
            assert isinstance(listeners, list)
            first = listeners[0]
            assert isinstance(first, dict)
            first["port"] = 14330
    assert RuntimeInputCode.DESTINATION in _codes(_policy(), topology)


def test_destination_table_matches_the_runtime_contract_exactly() -> None:
    """The package table and the checked-in contract are one fact, not two."""
    policy = _policy()
    applications = policy["applications"]
    assert isinstance(applications, list)
    assert len(applications) == len(V1_LOGICAL_DESTINATIONS)
    for application in applications:
        assert isinstance(application, dict)
        code = application["application_code"]
        assert isinstance(code, str)
        destinations = application["logical_destinations"]
        assert isinstance(destinations, list)
        dependencies = application["readiness_dependency_codes"]
        assert isinstance(dependencies, list)
        table = V1_LOGICAL_DESTINATIONS[code]
        assert tuple(item.value for item in table) == tuple(dependencies)
        contract = {
            str(item["service_id"]): (str(item["host"]), int(str(item["port"])))
            for item in destinations
            if isinstance(item, dict)
        }
        for host, port in table.values():
            assert contract[host] == (host, port)
