"""Fail-closed tests for the recorded V1 credential-interface proof results."""

import json
from collections.abc import Callable
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
        item for item in subjects if isinstance(item, dict) and item.get("service_id") == service_id
    )


def _list(policy: dict[str, object], key: str) -> list[object]:
    value = policy[key]
    assert isinstance(value, list)
    return value


def _first(policy: dict[str, object], key: str) -> dict[str, object]:
    entry = _list(policy, key)[0]
    assert isinstance(entry, dict)
    return entry


def _nested(policy: dict[str, object], key: str) -> dict[str, object]:
    value = policy[key]
    assert isinstance(value, dict)
    return value


def _claim_ready(policy: dict[str, object]) -> None:
    policy["ready"] = True


_MUTATIONS: dict[str, Callable[[dict[str, object]], None]] = {
    "ready_with_blockers": _claim_ready,
    "unevidenced_step": lambda policy: _first(policy, "required_steps").__setitem__(
        "evidence_refs", []
    ),
    "unrun_step_with_evidence": lambda policy: _first(policy, "required_steps").__setitem__(
        "state", "NOT_RUN"
    ),
    "unknown_step_evidence": lambda policy: _first(policy, "required_steps").__setitem__(
        "evidence_refs", ["INVENTED_EVIDENCE"]
    ),
    "evidence_inventory": lambda policy: _list(policy, "required_evidence").pop(),
    "blocker": lambda policy: _list(policy, "blockers").pop(),
    "unevidenced_subject": lambda policy: _subject(policy, "sql-server").__setitem__(
        "evidence_refs", []
    ),
    "embedded_secret": lambda policy: policy.__setitem__("password", "forbidden-canary"),
}


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


def test_credential_interface_record_is_executed_but_not_ready() -> None:
    """Record the executed proof without turning partial results into readiness."""
    assert check_credential_interface_policy(REPOSITORY_ROOT) == CredentialInterfaceReport(
        subjects=3,
        steps=6,
        inspection_surfaces=7,
        blockers=(
            "SYSTEM_UNIT_AND_ENCRYPTED_CREDENTIAL_REPROOF",
            "HOST_AND_CONTAINER_UID_ALIGNMENT",
            "MANIFEST_LAST_EVIDENCE_PACKAGE",
        ),
        executed=6,
        exceptions=0,
        findings=3,
        ready=False,
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("ready_with_blockers", CredentialInterfaceCode.ADMISSION),
        ("authority", CredentialInterfaceCode.AUTHORITY),
        ("secret_rule", CredentialInterfaceCode.SECRET),
        ("isolation", CredentialInterfaceCode.STATE),
        ("unevidenced_step", CredentialInterfaceCode.EVIDENCE),
        ("unrun_step_with_evidence", CredentialInterfaceCode.EVIDENCE),
        ("unknown_step_evidence", CredentialInterfaceCode.EVIDENCE),
        ("evidence_inventory", CredentialInterfaceCode.EVIDENCE),
        ("blocker", CredentialInterfaceCode.BLOCKER),
        ("unevidenced_subject", CredentialInterfaceCode.EVIDENCE),
        ("embedded_secret", CredentialInterfaceCode.SECRET),
    ],
)
def test_credential_interface_record_drift_fails_closed(
    mutation: str, expected: CredentialInterfaceCode
) -> None:
    """Reject invented readiness, authority, evidence, or secret transport."""
    policy = deepcopy(_policy())
    _nested(policy, "authority")["host_mutation_authorized"] = mutation == "authority"
    if mutation == "secret_rule":
        _nested(policy, "secret_rule")["arguments_forbidden"] = False
    if mutation == "isolation":
        _nested(policy, "isolation_rule")["real_credentials_forbidden"] = False
    _MUTATIONS.get(mutation, lambda _: None)(policy)
    assert expected in _codes(policy)


def _synthetic_exception() -> dict[str, object]:
    """One well-formed exception, so the mechanism stays tested after the real one retired."""
    return {
        "exception_id": "SYNTHETIC_TEST_EXCEPTION",
        "subjects": ["vault-primary"],
        "relaxed_rules": ["logs_forbidden"],
        "permitted_delivery": "ENVIRONMENT_ONLY",
        "forbidden_delivery": "ARGUMENTS",
        "reason": "synthetic exception used only to prove the mechanism still fails closed",
        "residual_risk": "none; this exception exists only inside this test",
        "bounded_by": ["TEST_ONLY"],
        "retirement_path": "DELETE_THIS_TEST_FIXTURE",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "unbacked_exception",
        "unused_exception",
        "unrelaxable_rule",
        "unknown_rule",
        "unknown_subject",
        "argument_delivery",
        "missing_residual_risk",
    ],
)
def test_exception_mechanism_cannot_be_abused(mutation: str) -> None:
    """Keep every accepted relaxation named, bounded, and tied to a real subject."""
    policy = deepcopy(_policy())
    policy["accepted_exceptions"] = [_synthetic_exception()]
    if mutation == "unbacked_exception":
        _subject(policy, "sql-server")["result"] = "EXCEPTION_ACCEPTED"
        _subject(policy, "sql-server")["exception_id"] = "INVENTED_EXCEPTION"
    elif mutation == "unused_exception":
        _subject(policy, "sql-server")["exception_id"] = "SYNTHETIC_TEST_EXCEPTION"
    elif mutation == "unrelaxable_rule":
        _first(policy, "accepted_exceptions")["relaxed_rules"] = ["arguments_forbidden"]
    elif mutation == "unknown_rule":
        _first(policy, "accepted_exceptions")["relaxed_rules"] = ["invented_rule"]
    elif mutation == "unknown_subject":
        _first(policy, "accepted_exceptions")["subjects"] = ["not-a-service"]
    elif mutation == "argument_delivery":
        _first(policy, "accepted_exceptions")["forbidden_delivery"] = "NONE"
    else:
        _first(policy, "accepted_exceptions")["residual_risk"] = ""
    assert CredentialInterfaceCode.EXCEPTION in _codes(policy)


@pytest.mark.parametrize("mutation", ["severity", "unproved_flag", "unknown_subject"])
def test_recorded_findings_must_stay_well_formed(mutation: str) -> None:
    """Keep executed findings typed, scoped, and honest about proved remedies."""
    policy = deepcopy(_policy())
    if mutation == "severity":
        _first(policy, "findings")["severity"] = "CATASTROPHIC"
    elif mutation == "unproved_flag":
        _first(policy, "findings")["procedure_proved"] = "yes"
    else:
        _first(policy, "findings")["subjects"] = ["not-a-service"]
    assert CredentialInterfaceCode.FINDING in _codes(policy)


def test_ready_is_allowed_only_when_every_step_passed_and_nothing_blocks() -> None:
    """Permit readiness exactly once the record itself justifies it."""
    policy = deepcopy(_policy())
    policy["ready"] = True
    policy["blockers"] = []
    for step in _list(policy, "required_steps"):
        assert isinstance(step, dict)
        step["state"] = "PASSED"
    assert CredentialInterfaceCode.ADMISSION not in _codes(policy)


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
