"""Fail-closed tests for disabled V1 POC host identity inputs."""

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

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
    return _object(REPOSITORY_ROOT / IDENTITY_POLICY_PATH)


def _topology() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / TOPOLOGY_PATH)


def _identity(policy: dict[str, object], service_id: str) -> dict[str, object]:
    return _item_by_id(policy["identities"], service_id)


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
        owned_paths=16,
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
    identities = _object_list(policy["identities"])
    identities[-1] = deepcopy(identities[0])
    codes = _codes(policy)
    assert HostIdentityCode.INVENTORY in codes
    assert HostIdentityCode.DUPLICATE in codes


def test_authority_and_login_profile_drift_fail_closed() -> None:
    """Reject host mutation authority or an interactive account profile."""
    policy = deepcopy(_policy())
    authority = _object_map(policy["authority"])
    authority["identity_creation_authorized"] = True
    assert HostIdentityCode.AUTHORITY in _codes(policy)

    policy = deepcopy(_policy())
    profile = _object_map(policy["identity_profile"])
    profile["login_shell"] = "/bin/bash"
    assert HostIdentityCode.PROFILE in _codes(policy)


def test_topology_and_embedded_secret_drift_fail_closed() -> None:
    """Bind identities to topology and keep the contract secret-free."""
    topology = _topology()
    control = _item_by_id(topology["services"], "control-plane")
    control["identity"] = "changed-identity"
    assert HostIdentityCode.TOPOLOGY in _codes(_policy(), topology)

    policy = deepcopy(_policy())
    policy["password"] = "forbidden"
    assert HostIdentityCode.SECRET in _codes(policy)


def _map_entry(policy: dict[str, object], service_id: str) -> dict[str, object]:
    return _item_by_id(policy["container_identity_map"], service_id)


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
    entries = _object_list(policy["container_identity_map"])
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
    rule = _object_map(policy["container_identity_rule"])
    rule[field] = False
    assert HostIdentityCode.PROFILE in _codes(policy)


def test_allocated_range_cannot_be_widened_to_reach_a_real_account() -> None:
    """A widened range would let an application account collide with the login user."""
    policy = deepcopy(_policy())
    profile = _object_map(policy["identity_profile"])
    profile["allocated_uid_gid_range"] = [1000, 3014]
    assert HostIdentityCode.PROFILE in _codes(policy)
