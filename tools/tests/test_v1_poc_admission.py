"""Fail-closed tests for the complete V1 POC admission verdict."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

import tools.v1_poc_admission as admission
from tools.v1_poc_admission import (
    ADMISSION_POLICY_PATH,
    V1AdmissionCode,
    V1AdmissionReport,
    check_v1_admission,
    validate_v1_admission_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_STATIC_GATE_FAILED = "STATIC_GATE_FAILED"


def _policy() -> dict[str, object]:
    value = json.loads((REPOSITORY_ROOT / ADMISSION_POLICY_PATH).read_bytes())
    assert isinstance(value, dict)
    return value


def _component(policy: dict[str, object], component_id: str) -> dict[str, object]:
    components = policy["components"]
    assert isinstance(components, list)
    return next(
        item
        for item in components
        if isinstance(item, dict) and item.get("component_id") == component_id
    )


def _codes(policy: dict[str, object]) -> set[V1AdmissionCode]:
    return {finding.code for finding in validate_v1_admission_policy(policy, REPOSITORY_ROOT)}


def test_composite_gate_reports_static_validation_without_v1_admission() -> None:
    """Expose one exact verdict that cannot confuse static proof with readiness."""
    assert check_v1_admission(REPOSITORY_ROOT) == V1AdmissionReport(
        components=14,
        static_contracts_validated=8,
        blockers=14,
        admitted=False,
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("ready", True, V1AdmissionCode.ADMISSION),
        ("admission_statement", "V1_POC_ADMITTED", V1AdmissionCode.ADMISSION),
        ("status", "READY", V1AdmissionCode.INVENTORY),
    ],
)
def test_document_admission_or_status_drift_fails_closed(
    field: str, value: object, expected: V1AdmissionCode
) -> None:
    """Reject an invented admission statement or a changed document state."""
    policy = deepcopy(_policy())
    policy[field] = value
    assert expected in _codes(policy)


def test_authority_expansion_fails_closed() -> None:
    """Keep host, image, credential, service, and external authority false."""
    policy = deepcopy(_policy())
    authority = policy["authority"]
    assert isinstance(authority, dict)
    authority["image_pull_authorized"] = True
    assert V1AdmissionCode.AUTHORITY in _codes(policy)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("state", "ADMITTED"),
        ("admission_blocker", "NONE"),
        ("evidence", "NOT_CREATED"),
    ],
)
def test_component_state_blocker_or_evidence_drift_fails_closed(field: str, value: object) -> None:
    """Require the exact ordered component inventory and evidence binding."""
    policy = deepcopy(_policy())
    _component(policy, "STATIC_TOPOLOGY")[field] = value
    assert V1AdmissionCode.COMPONENT in _codes(policy)


def test_missing_evidence_file_fails_closed() -> None:
    """Do not count a static contract whose declared evidence is absent."""
    policy = deepcopy(_policy())
    component = _component(policy, "STATIC_TOPOLOGY")
    component["evidence"] = "tools/does_not_exist.py"
    codes = _codes(policy)
    assert V1AdmissionCode.COMPONENT in codes
    assert V1AdmissionCode.EVIDENCE in codes


def test_missing_or_reordered_component_fails_closed() -> None:
    """Require all fourteen admission components in their frozen order."""
    policy = deepcopy(_policy())
    components = policy["components"]
    assert isinstance(components, list)
    components[0], components[1] = components[1], components[0]
    assert V1AdmissionCode.COMPONENT in _codes(policy)


def test_secret_bearing_addition_fails_closed() -> None:
    """Keep the aggregate admission contract free of secret material."""
    policy = deepcopy(_policy())
    policy["api_key"] = "sk-forbidden"
    assert V1AdmissionCode.SECRET in _codes(policy)


def test_composite_check_propagates_a_static_gate_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Propagate a static-gate failure instead of reporting aggregate success."""

    def _fail(_root: Path) -> None:
        raise ValueError(_STATIC_GATE_FAILED)

    monkeypatch.setattr(admission, "check_topology", _fail)
    with pytest.raises(ValueError, match="STATIC_GATE_FAILED"):
        check_v1_admission(REPOSITORY_ROOT)
