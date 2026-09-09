"""Synthetic tests for the read-only V1 POC host-admission boundary."""

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from tools.v1_poc_collect_host_facts import (
    HostFactClass,
    HostFactClassOutcome,
    HostFactFailureCode,
    build_hk_v1_host_facts,
    write_host_facts_output,
)
from tools.v1_poc_host_admission import (
    HostCode,
    HostEnvelopeAdmissionEvaluation,
    HostPolicyReport,
    check_policy,
    evaluate_host_facts,
    evaluate_host_facts_envelope,
    main,
    validate_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _policy() -> dict[str, object]:
    value: object = json.loads(
        (REPOSITORY_ROOT / "infrastructure/poc/host_admission_policy.json").read_bytes()
    )
    return _object_map(value)


def _object_map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _facts() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": "READ_ONLY_HOST_FACTS",
        "os": {"id": "ubuntu", "version_id": "24.04"},
        "architecture": "x86_64",
        "memory_bytes": 67_252_903_936,
        "physical_disks": [
            {"stable_id": "disk-poc-data", "size_bytes": 4_000_787_030_016},
            {"stable_id": "disk-poc-root", "size_bytes": 500_107_862_016},
            {"stable_id": "disk-poc-spare", "size_bytes": 500_107_862_016},
        ],
        "paths": [
            {
                "path": path,
                "real_path": path,
                "fs_type": "ext4",
                "physical_disk_id": "disk-poc-data",
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
            "docker_group_non_root_members": ["docpro"],
        },
        "host_packages": {
            "ca-certificates": "20260601~24.04.1",
            "containerd.io": "2.3.3-1~ubuntu.24.04~noble",
            "docker-ce": "5:29.7.2-1~ubuntu.24.04~noble",
            "docker-ce-cli": "5:29.7.2-1~ubuntu.24.04~noble",
            "e2fsprogs": "1.47.0-2.4~exp1ubuntu4.1",
            "nftables": "1.0.9-1ubuntu0.1",
            "systemd": "255.4-1ubuntu8.17",
            "systemd-timesyncd": "255.4-1ubuntu8.17",
            "util-linux": "2.39.3-9ubuntu6.6",
        },
        "private_subnets": {
            "declared": {
                "asklegal-register": "10.90.0.0/24",
                "asklegal-scheduler-general": "10.90.1.0/24",
                "asklegal-scheduler-promotion": "10.90.2.0/24",
                "asklegal-vault-primary": "10.90.3.0/24",
                "asklegal-vault-recovery": "10.90.4.0/24",
                "asklegal-review": "10.90.5.0/24",
                "asklegal-telemetry": "10.90.6.0/24",
                "asklegal-egress-source": "10.90.7.0/24",
                "asklegal-egress-model": "10.90.8.0/24",
                "asklegal-egress-promotion": "10.90.9.0/24",
            },
            "foreign": ["10.2.0.2/32", "172.17.0.1/16", "192.168.9.126/22"],
        },
    }


def _codes(facts: dict[str, object]) -> set[HostCode]:
    return {finding.code for finding in evaluate_host_facts(_policy(), facts).findings}


def test_repository_policy_is_valid_but_not_ready() -> None:
    """Keep missing admission work explicit instead of inventing defaults."""
    assert check_policy(REPOSITORY_ROOT) == HostPolicyReport(
        required_paths=3,
        blockers=("CREDENTIAL_INTERFACE_PROOF",),
        host_mutation_authorized=False,
    )


@pytest.mark.parametrize(
    "mutation",
    ["missing", "overlapping", "public", "wrong_prefix", "host_collision", "malformed"],
)
def test_private_subnet_selection_fails_closed(mutation: str) -> None:
    """Keep every declared network on a distinct, private, non-colliding subnet."""
    policy = deepcopy(_policy())
    runtime = _object_map(policy["runtime"])
    subnets = _object_map(runtime["selected_private_subnets"])
    if mutation == "missing":
        del subnets["asklegal-register"]
    elif mutation == "overlapping":
        subnets["asklegal-review"] = subnets["asklegal-register"]
    elif mutation == "public":
        subnets["asklegal-register"] = "8.8.8.0/24"
    elif mutation == "wrong_prefix":
        subnets["asklegal-register"] = "10.90.0.0/16"
    elif mutation == "host_collision":
        subnets["asklegal-register"] = "172.17.0.0/24"
    else:
        subnets["asklegal-register"] = "not-a-subnet"
    assert HostCode.POLICY in {finding.code for finding in validate_policy(policy)}


def test_conforming_synthetic_facts_do_not_override_blockers() -> None:
    """Matching reported facts still cannot authorize or mutate the host."""
    result = evaluate_host_facts(_policy(), _facts())
    assert result.facts_conform is True
    assert result.admitted is False
    assert result.findings == ()
    assert len(result.blockers) == 1


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("os", HostCode.OPERATING_SYSTEM),
        ("memory", HostCode.MEMORY),
        ("disk", HostCode.STORAGE),
        ("split_disk", HostCode.STORAGE),
        ("small_disk", HostCode.STORAGE),
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
    elif mutation == "split_disk":
        paths = facts["paths"]
        assert isinstance(paths, list)
        assert isinstance(paths[2], dict)
        paths[2]["physical_disk_id"] = "disk-poc-spare"
    elif mutation == "small_disk":
        disks = facts["physical_disks"]
        assert isinstance(disks, list)
        assert isinstance(disks[0], dict)
        disks[0]["size_bytes"] = 1_000_000_000_000
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


@pytest.mark.parametrize("mutation", ["missing", "extra", "empty", "wildcard", "not_a_mapping"])
def test_host_package_locks_fail_closed(mutation: str) -> None:
    """Require one exact installed version for every locked host package."""
    policy = deepcopy(_policy())
    runtime = _object_map(policy["runtime"])
    locks = _object_map(runtime["host_package_locks"])
    if mutation == "missing":
        del locks["systemd"]
    elif mutation == "extra":
        locks["unexpected-package"] = "1.0"
    elif mutation == "empty":
        locks["systemd"] = ""
    elif mutation == "wildcard":
        locks["systemd"] = "255.*"
    else:
        runtime["host_package_locks"] = []
    assert HostCode.POLICY in {finding.code for finding in validate_policy(policy)}


@pytest.mark.parametrize("mutation", ["drift", "missing", "not_installed"])
def test_installed_host_packages_must_equal_the_locks(mutation: str) -> None:
    """An upgraded, absent, or uninstalled host package is not the admitted host."""
    facts = deepcopy(_facts())
    packages = facts["host_packages"]
    assert isinstance(packages, dict)
    if mutation == "drift":
        packages["systemd"] = "255.4-1ubuntu8.18"
    elif mutation == "missing":
        del packages["nftables"]
    else:
        packages["nftables"] = "NOT_INSTALLED"
    assert HostCode.PACKAGE in _codes(facts)


@pytest.mark.parametrize(
    "mutation", ["unprovisioned", "wrong_subnet", "host_collision", "malformed", "shape"]
)
def test_observed_networks_fail_closed(mutation: str) -> None:
    """The ten declared networks must exist exactly and never collide with a host network."""
    facts = deepcopy(_facts())
    networks = _object_map(facts["private_subnets"])
    declared = _object_map(networks["declared"])
    foreign = _object_list(networks["foreign"])
    if mutation == "unprovisioned":
        networks["declared"] = {}
    elif mutation == "wrong_subnet":
        declared["asklegal-register"] = "10.91.0.0/24"
    elif mutation == "host_collision":
        foreign.append("10.90.5.1/24")
    elif mutation == "malformed":
        foreign.append("not-a-network")
    else:
        del networks["foreign"]
    assert HostCode.NETWORK in _codes(facts)


def _outcomes(*, missing: HostFactClass | None = None) -> tuple[HostFactClassOutcome, ...]:
    return tuple(
        HostFactClassOutcome(
            fact_class=fact_class,
            collected=fact_class is not missing,
            failure_code=(HostFactFailureCode.NOT_IMPLEMENTED if fact_class is missing else None),
        )
        for fact_class in HostFactClass
    )


def test_valid_legacy_facts_in_incomplete_envelope_cannot_admit() -> None:
    """Completeness is independently mandatory even when every legacy value conforms."""
    envelope = build_hk_v1_host_facts(
        legacy_facts=_facts(),
        outcomes=_outcomes(missing=HostFactClass.TELEMETRY_FRESHNESS),
    )

    result = evaluate_host_facts_envelope(_policy(), envelope)

    assert result == HostEnvelopeAdmissionEvaluation(
        facts_conform=False,
        admitted=False,
        findings=(),
        blockers=("CREDENTIAL_INTERFACE_PROOF", "HOST_FACTS_INCOMPLETE"),
        missing_fact_classes=(HostFactClass.TELEMETRY_FRESHNESS,),
    )


def test_complete_envelope_with_legacy_drift_keeps_drift_and_cannot_admit() -> None:
    """A complete class inventory cannot erase an unsafe observed host value."""
    facts = _facts()
    facts["memory_bytes"] = 1
    envelope = build_hk_v1_host_facts(
        legacy_facts=facts,
        outcomes=_outcomes(),
    )

    result = evaluate_host_facts_envelope(_policy(), envelope)

    assert result.facts_conform is False
    assert result.admitted is False
    assert HostCode.MEMORY in {finding.code for finding in result.findings}
    assert "HOST_FACTS_INCOMPLETE" not in result.blockers


def test_saved_incomplete_envelope_cli_reports_the_collection_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route retained collector output through the envelope evaluator, not legacy JSON."""
    facts_path = tmp_path / "observed.json"
    envelope = build_hk_v1_host_facts(
        legacy_facts=_facts(),
        outcomes=_outcomes(missing=HostFactClass.SYSTEMD_UNITS_TIMERS),
    )
    write_host_facts_output(envelope, facts_path)
    monkeypatch.setattr("sys.argv", ["v1_poc_host_admission", "--facts", str(facts_path)])

    with pytest.raises(ValueError, match="HOST_FACTS_INCOMPLETE") as failure:
        main()

    assert "INVENTORY:facts header" not in str(failure.value)


def test_partial_legacy_snapshot_is_not_misreported_as_host_drift() -> None:
    """An incomplete collection has unknown facts, not proved legacy mismatches."""
    envelope = build_hk_v1_host_facts(
        legacy_facts={"schema_version": 1, "source": "READ_ONLY_HOST_FACTS"},
        outcomes=_outcomes(missing=HostFactClass.SYSTEMD_UNITS_TIMERS),
    )

    result = evaluate_host_facts_envelope(_policy(), envelope)

    assert result.findings == ()
    assert result.blockers == ("CREDENTIAL_INTERFACE_PROOF", "HOST_FACTS_INCOMPLETE")
