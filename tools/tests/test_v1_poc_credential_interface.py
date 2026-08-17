"""Fail-closed tests for disabled V1 credential-interface proof inputs."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.v1_poc_artifacts import ARTIFACT_POLICY_PATH, load_artifact_policy
from tools.v1_poc_credential_interface import (
    CREDENTIAL_INTERFACE_POLICY_PATH,
    CredentialInterfaceCode,
    CredentialInterfaceReport,
    check_credential_interface_policy,
    validate_credential_interface_policy,
)
from tools.v1_poc_systemd_units import SYSTEMD_POLICY_PATH

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _policy() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / CREDENTIAL_INTERFACE_POLICY_PATH)


def _artifacts() -> dict[str, object]:
    return load_artifact_policy(REPOSITORY_ROOT / ARTIFACT_POLICY_PATH)


def _systemd() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / SYSTEMD_POLICY_PATH)


def _subject(policy: dict[str, object], service_id: str) -> dict[str, object]:
    subjects = policy["subjects"]
    assert isinstance(subjects, list)
    return next(
        item
        for item in subjects
        if isinstance(item, dict) and item.get("service_id") == service_id
    )


def _codes(
    policy: dict[str, object],
    artifacts: dict[str, object] | None = None,
    systemd: dict[str, object] | None = None,
) -> set[CredentialInterfaceCode]:
    return {
        finding.code
        for finding in validate_credential_interface_policy(
            policy, artifacts or _artifacts(), systemd or _systemd()
        )
    }


def test_credential_interface_plan_is_complete_disabled_and_unexecuted() -> None:
    """Freeze the exact host proof without claiming image or credential authority."""
    assert check_credential_interface_policy(REPOSITORY_ROOT) == CredentialInterfaceReport(
        subjects=3,
        steps=6,
        inspection_surfaces=7,
        blockers=(
            "UBUNTU_HOST_ACCESS",
            "READ_ONLY_IMAGE_RESOLUTION_AUTHORITY",
            "IMAGE_PULL_RUN_AUTHORITY",
            "VERSITY_VERSION_AND_DIGEST",
            "SYNTHETIC_CREDENTIAL_CREATION_AUTHORITY",
            "NAMED_THROWAWAY_STATE_MUTATION_AND_CLEANUP_AUTHORITY",
        ),
        executed=0,
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("ready", CredentialInterfaceCode.ADMISSION),
        ("authority", CredentialInterfaceCode.AUTHORITY),
        ("secret_rule", CredentialInterfaceCode.SECRET),
        ("isolation", CredentialInterfaceCode.STATE),
        ("step", CredentialInterfaceCode.STATE),
        ("evidence", CredentialInterfaceCode.EVIDENCE),
        ("blocker", CredentialInterfaceCode.BLOCKER),
        ("subject_state", CredentialInterfaceCode.STATE),
        ("embedded_secret", CredentialInterfaceCode.SECRET),
    ],
)
def test_credential_interface_policy_drift_fails_closed(
    mutation: str, expected: CredentialInterfaceCode
) -> None:
    """Reject invented readiness, authority, proof, evidence, or secret transport."""
    policy = deepcopy(_policy())
    if mutation == "ready":
        policy["ready"] = True
    elif mutation == "authority":
        authority = policy["authority"]
        assert isinstance(authority, dict)
        authority["image_pull_authorized"] = True
    elif mutation == "secret_rule":
        secret_rule = policy["secret_rule"]
        assert isinstance(secret_rule, dict)
        secret_rule["environment_forbidden"] = False
    elif mutation == "isolation":
        isolation = policy["isolation_rule"]
        assert isinstance(isolation, dict)
        isolation["real_credentials_forbidden"] = False
    elif mutation == "step":
        steps = policy["required_steps"]
        assert isinstance(steps, list)
        assert isinstance(steps[0], dict)
        steps[0]["state"] = "PASSED"
    elif mutation == "evidence":
        evidence = policy["required_evidence"]
        assert isinstance(evidence, list)
        evidence.pop()
    elif mutation == "blocker":
        blockers = policy["blockers"]
        assert isinstance(blockers, list)
        blockers.pop()
    elif mutation == "subject_state":
        _subject(policy, "sql-server")["result"] = "PASSED"
    else:
        policy["password"] = "forbidden-canary"
    assert expected in _codes(policy)


def test_artifact_selection_and_digest_drift_fail_closed() -> None:
    """Bind each subject to the current credential-gated artifact selection."""
    artifacts = deepcopy(_artifacts())
    entries = artifacts["artifacts"]
    assert isinstance(entries, list)
    sql = next(
        item
        for item in entries
        if isinstance(item, dict) and item.get("artifact_id") == "sql-server"
    )
    sql["artifact_ref"] = "mcr.microsoft.com/mssql/server@sha256:" + ("0" * 64)
    assert CredentialInterfaceCode.ARTIFACT in _codes(_policy(), artifacts=artifacts)


def test_systemd_credential_inventory_drift_fails_closed() -> None:
    """Use exactly the credential files assigned to each product unit."""
    systemd = deepcopy(_systemd())
    units = systemd["service_units"]
    assert isinstance(units, list)
    primary = next(
        item
        for item in units
        if isinstance(item, dict) and item.get("service_id") == "vault-primary"
    )
    primary["credential_names"] = ["vault-primary-root-access"]
    assert CredentialInterfaceCode.SYSTEMD in _codes(_policy(), systemd=systemd)
