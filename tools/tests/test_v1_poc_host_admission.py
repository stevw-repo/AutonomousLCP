"""Synthetic tests for the read-only V1 POC host-admission boundary."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.v1_poc_host_admission import (
    HostCode,
    HostPolicyReport,
    check_policy,
    evaluate_host_facts,
    validate_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _policy() -> dict[str, object]:
    value = json.loads(
        (REPOSITORY_ROOT / "infrastructure/poc/host_admission_policy.json").read_bytes()
    )
    assert isinstance(value, dict)
    return value


def _facts() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": "READ_ONLY_HOST_FACTS",
        "os": {"id": "ubuntu", "version_id": "24.04"},
        "architecture": "x86_64",
        "memory_bytes": 68_719_476_736,
        "physical_disks": [{"stable_id": "disk-poc", "size_bytes": 5_000_000_000_000}],
        "paths": [
            {
                "path": path,
                "real_path": path,
                "fs_type": "ext4",
                "physical_disk_id": "disk-poc",
                "symlink": False,
                "writable": True,
            }
            for path in (
                "/srv/asklegal/sql",
                "/srv/asklegal/vault-primary",
                "/srv/asklegal/vault-recovery",
            )
        ],
        "time": {"synchronized": True},
        "credentials": {
            "systemd_creds_available": True,
            "protection_mode": "TPM2_PLUS_HOST_KEY",
            "encrypted_blob_mode": "0400",
            "persistent_plaintext_credential_paths": [],
        },
        "firewall": {
            "nftables_available": True,
            "input_default": "DROP",
            "forward_default": "DROP",
            "direct_container_egress_default": "DROP",
            "public_tcp_ports": [],
        },
        "journal": {"storage": "PERSISTENT", "forward_secure_sealing": True},
        "container_runtime": {
            "name": "docker",
            "service_manager": "systemd",
            "docker_group_non_root_members": [],
        },
        "host_packages": {},
        "private_subnets": {},
    }


def _codes(facts: dict[str, object]) -> set[HostCode]:
    return {finding.code for finding in evaluate_host_facts(_policy(), facts).findings}


def test_repository_policy_is_valid_but_not_ready() -> None:
    """Keep missing admission work explicit instead of inventing defaults."""
    assert check_policy(REPOSITORY_ROOT) == HostPolicyReport(
        required_paths=3,
        blockers=(
            "CREDENTIAL_INTERFACE_PROOF",
            "HOST_PACKAGE_LOCKS",
            "PRIVATE_SUBNET_SELECTION",
        ),
        host_mutation_authorized=False,
    )


def test_conforming_synthetic_facts_do_not_override_blockers() -> None:
    """Matching reported facts still cannot authorize or mutate the host."""
    result = evaluate_host_facts(_policy(), _facts())
    assert result.facts_conform is True
    assert result.admitted is False
    assert result.findings == ()
    assert len(result.blockers) == 3


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("os", HostCode.OPERATING_SYSTEM),
        ("memory", HostCode.MEMORY),
        ("disk", HostCode.STORAGE),
        ("path", HostCode.PATH),
        ("time", HostCode.TIME),
    ],
)
def test_unsafe_or_incomplete_host_facts_fail_closed(
    mutation: str, expected_code: HostCode
) -> None:
    """Reject each safety-critical class of reported host drift."""
    facts = deepcopy(_facts())
    if mutation == "os":
        facts["os"] = {"id": "ubuntu", "version_id": "26.04"}
    elif mutation == "memory":
        facts["memory_bytes"] = 8_000_000_000
    elif mutation == "disk":
        facts["physical_disks"] = []
    elif mutation == "path":
        paths = facts["paths"]
        assert isinstance(paths, list)
        assert isinstance(paths[1], dict)
        paths[1]["symlink"] = True
    else:
        facts["time"] = {"synchronized": False}
    assert expected_code in _codes(facts)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("credential", HostCode.CREDENTIAL),
        ("firewall", HostCode.FIREWALL),
        ("journal", HostCode.JOURNAL),
        ("container", HostCode.CONTAINER),
        ("secret", HostCode.SECRET),
        ("unknown", HostCode.INVENTORY),
    ],
)
def test_unsafe_or_incomplete_security_facts_fail_closed(
    mutation: str, expected_code: HostCode
) -> None:
    """Reject unsafe security, credential, and schema facts."""
    facts = deepcopy(_facts())
    if mutation == "credential":
        facts["credentials"] = {"systemd_creds_available": False}
    elif mutation == "firewall":
        firewall = facts["firewall"]
        assert isinstance(firewall, dict)
        firewall["input_default"] = "ACCEPT"
    elif mutation == "journal":
        facts["journal"] = {"storage": "VOLATILE", "forward_secure_sealing": False}
    elif mutation == "container":
        runtime = facts["container_runtime"]
        assert isinstance(runtime, dict)
        runtime["docker_group_non_root_members"] = ["admin"]
    elif mutation == "secret":
        facts["api_key"] = "must-not-be-present"
    else:
        facts["unexpected"] = "field"
    assert expected_code in _codes(facts)


def test_authority_cannot_be_enabled_in_policy() -> None:
    """Reject mutation authority even when every other policy field is unchanged."""
    policy = deepcopy(_policy())
    authority = policy["authority"]
    assert isinstance(authority, dict)
    authority["host_mutation_authorized"] = True
    assert HostCode.AUTHORITY in {finding.code for finding in validate_policy(policy)}
