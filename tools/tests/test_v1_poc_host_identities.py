"""Fail-closed tests for disabled V1 POC host identity inputs."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.v1_poc_host_identities import (
    IDENTITY_POLICY_PATH,
    TOPOLOGY_PATH,
    HostIdentityCode,
    HostIdentityReport,
    check_host_identity_policy,
    validate_host_identity_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _policy() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / IDENTITY_POLICY_PATH)


def _topology() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / TOPOLOGY_PATH)


def _identity(policy: dict[str, object], service_id: str) -> dict[str, object]:
    identities = policy["identities"]
    assert isinstance(identities, list)
    return next(
        item
        for item in identities
        if isinstance(item, dict) and item.get("service_id") == service_id
    )


def _codes(
    policy: dict[str, object], topology: dict[str, object] | None = None
) -> set[HostIdentityCode]:
    return {
        finding.code for finding in validate_host_identity_policy(policy, topology or _topology())
    }


def test_host_identity_inputs_are_allocated_but_still_uncreated() -> None:
    """Bind every accepted account to an exact number without mutating the host."""
    assert check_host_identity_policy(REPOSITORY_ROOT) == HostIdentityReport(
        identities=10,
        owned_paths=14,
        container_identities=16,
        blockers=(
            "PATH_OWNERSHIP_PROOF",
            "UBUNTU_IDENTITY_PROOF",
        ),
        created=0,
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("identity", "root", HostIdentityCode.DUPLICATE),
        ("owned_write_paths", ["/var/lib/asklegal/wrong"], HostIdentityCode.OWNERSHIP),
        ("uid", 1000, HostIdentityCode.STATE),
        ("gid", 1000, HostIdentityCode.STATE),
        ("uid", None, HostIdentityCode.STATE),
        ("uid", 0, HostIdentityCode.STATE),
        ("created", True, HostIdentityCode.STATE),
    ],
)
def test_identity_name_ownership_and_allocation_drift_fail_closed(
    field: str, value: object, expected: HostIdentityCode
) -> None:
    """Do not invent root identity, ownership, numeric IDs, or creation state."""
    policy = deepcopy(_policy())
    _identity(policy, "control-plane")[field] = value
    assert expected in _codes(policy)


def test_missing_or_duplicate_identity_fails_closed() -> None:
    """Require one unique host identity for each topology service with host paths."""
    policy = deepcopy(_policy())
    identities = policy["identities"]
    assert isinstance(identities, list)
    identities[-1] = deepcopy(identities[0])
    codes = _codes(policy)
    assert HostIdentityCode.INVENTORY in codes
    assert HostIdentityCode.DUPLICATE in codes


def test_authority_and_login_profile_drift_fail_closed() -> None:
    """Reject host mutation authority or an interactive account profile."""
    policy = deepcopy(_policy())
    authority = policy["authority"]
    assert isinstance(authority, dict)
    authority["identity_creation_authorized"] = True
    assert HostIdentityCode.AUTHORITY in _codes(policy)

    policy = deepcopy(_policy())
    profile = policy["identity_profile"]
    assert isinstance(profile, dict)
    profile["login_shell"] = "/bin/bash"
    assert HostIdentityCode.PROFILE in _codes(policy)


def test_topology_and_embedded_secret_drift_fail_closed() -> None:
    """Bind identities to topology and keep the contract secret-free."""
    topology = _topology()
    services = topology["services"]
    assert isinstance(services, list)
    control = next(
        item
        for item in services
        if isinstance(item, dict) and item.get("service_id") == "control-plane"
    )
    control["identity"] = "changed-identity"
    assert HostIdentityCode.TOPOLOGY in _codes(_policy(), topology)

    policy = deepcopy(_policy())
    policy["password"] = "forbidden"
    assert HostIdentityCode.SECRET in _codes(policy)


def _map_entry(policy: dict[str, object], service_id: str) -> dict[str, object]:
    entries = policy["container_identity_map"]
    assert isinstance(entries, list)
    return next(
        item for item in entries if isinstance(item, dict) and item.get("service_id") == service_id
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("root_uid", HostIdentityCode.INVENTORY),
        ("shared_uid", HostIdentityCode.DUPLICATE),
        ("split_uid_gid", HostIdentityCode.INVENTORY),
        ("unknown_source", HostIdentityCode.INVENTORY),
        ("missing_service", HostIdentityCode.INVENTORY),
        ("extra_service", HostIdentityCode.INVENTORY),
        ("host_mismatch", HostIdentityCode.STATE),
        ("false_image_claim", HostIdentityCode.STATE),
        ("wrong_sql_uid", HostIdentityCode.STATE),
        ("pathless_becomes_host_account", HostIdentityCode.STATE),
    ],
)
def test_container_identity_map_fails_closed(mutation: str, expected: HostIdentityCode) -> None:
    """Every container must run as one exact, non-root, unshared numeric identity."""
    policy = deepcopy(_policy())
    entries = policy["container_identity_map"]
    assert isinstance(entries, list)
    control = _map_entry(policy, "control-plane")
    if mutation == "root_uid":
        control["runtime_uid"] = 0
        control["runtime_gid"] = 0
    elif mutation == "shared_uid":
        review = _map_entry(policy, "review-api")
        review["runtime_uid"] = control["runtime_uid"]
        review["runtime_gid"] = control["runtime_gid"]
    elif mutation == "split_uid_gid":
        control["runtime_gid"] = 3099
    elif mutation == "unknown_source":
        control["source"] = "TRUST_ME"
    elif mutation == "missing_service":
        entries.remove(control)
    elif mutation == "extra_service":
        entries.append(
            {
                "service_id": "not-a-service",
                "runtime_uid": 3020,
                "runtime_gid": 3020,
                "source": "CONTAINER_ONLY_RESERVED",
            }
        )
    elif mutation == "host_mismatch":
        control["runtime_uid"] = 3013
        control["runtime_gid"] = 3013
    elif mutation == "false_image_claim":
        control["source"] = "IMAGE_DEFINED"
    elif mutation == "wrong_sql_uid":
        sql = _map_entry(policy, "sql-server")
        sql["runtime_uid"] = 3005
        sql["runtime_gid"] = 3005
    else:
        control["source"] = "CONTAINER_ONLY_RESERVED"
    assert expected in _codes(policy)


@pytest.mark.parametrize(
    "field",
    [
        "credential_file_owner_must_equal_runtime_uid",
        "root_runtime_uid_forbidden",
        "shared_runtime_uid_forbidden",
    ],
)
def test_container_identity_rule_cannot_be_weakened(field: str) -> None:
    """The credential-delivery constraint is measured evidence, not a preference."""
    policy = deepcopy(_policy())
    rule = policy["container_identity_rule"]
    assert isinstance(rule, dict)
    rule[field] = False
    assert HostIdentityCode.PROFILE in _codes(policy)


def test_allocated_range_cannot_be_widened_to_reach_a_real_account() -> None:
    """A widened range would let an application account collide with the login user."""
    policy = deepcopy(_policy())
    profile = policy["identity_profile"]
    assert isinstance(profile, dict)
    profile["allocated_uid_gid_range"] = [1000, 3014]
    assert HostIdentityCode.PROFILE in _codes(policy)
