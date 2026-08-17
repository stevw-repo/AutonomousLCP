"""Composite fail-closed admission verdict for the complete local V1 POC."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tools.v1_poc_application_images import check_application_image_policy
from tools.v1_poc_application_runtime import check_runtime_input_policy
from tools.v1_poc_artifacts import check_artifact_policy
from tools.v1_poc_credential_interface import check_credential_interface_policy
from tools.v1_poc_host_admission import check_policy
from tools.v1_poc_host_identities import check_host_identity_policy
from tools.v1_poc_systemd_units import check_systemd_input_policy
from tools.v1_poc_topology import check_topology

ADMISSION_POLICY_PATH = Path("infrastructure/poc/v1_admission_gate.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_DOCUMENT_TOO_LARGE = "V1 admission document too large"
_DOCUMENT_ROOT = "V1 admission document root"
_OBJECT_LIST = "V1 admission component list"
_SECRET_VALUE = re.compile(
    r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)"
)
_DOCUMENT_KEYS = frozenset(
    {
        "admission_statement",
        "authority",
        "components",
        "ready",
        "schema_version",
        "status",
    }
)
_COMPONENT_KEYS = frozenset(
    {"admission_blocker", "component_id", "evidence", "state"}
)
_AUTHORITY = {
    "credential_creation_authorized": False,
    "external_access_authorized": False,
    "host_mutation_authorized": False,
    "image_pull_authorized": False,
    "pinecone_write_authorized": False,
    "service_enablement_authorized": False,
}
_STATIC_STATE = "STATIC_CONTRACT_VALIDATED_NOT_ADMITTED"
_EXPECTED_COMPONENTS = (
    (
        "STATIC_TOPOLOGY",
        "tools/v1_poc_topology.py",
        _STATIC_STATE,
        "ARTIFACT_PINS_AND_HOST_RESOLUTION",
    ),
    (
        "HOST_ADMISSION",
        "tools/v1_poc_host_admission.py",
        _STATIC_STATE,
        "REAL_HOST_FACTS",
    ),
    (
        "CREDENTIAL_INTERFACE_PROOF_PLAN",
        "tools/v1_poc_credential_interface.py",
        _STATIC_STATE,
        "UBUNTU_EXECUTABLE_CREDENTIAL_PROOF",
    ),
    (
        "ARTIFACT_ADMISSION",
        "tools/v1_poc_artifacts.py",
        _STATIC_STATE,
        "ARTIFACT_EVIDENCE",
    ),
    (
        "APPLICATION_IMAGE_ADMISSION",
        "tools/v1_poc_application_images.py",
        _STATIC_STATE,
        "IMAGE_BUILD_AND_UBUNTU_PROOF",
    ),
    (
        "APPLICATION_RUNTIME_ADMISSION",
        "tools/v1_poc_application_runtime.py",
        _STATIC_STATE,
        "REAL_RUNTIME_ADAPTERS_AND_PROBES",
    ),
    (
        "SYSTEMD_UNIT_ADMISSION",
        "tools/v1_poc_systemd_units.py",
        _STATIC_STATE,
        "UNIT_RUNTIME_INPUTS_AND_UBUNTU_PROOF",
    ),
    (
        "HOST_IDENTITY_ADMISSION",
        "tools/v1_poc_host_identities.py",
        _STATIC_STATE,
        "UID_GID_AND_OWNERSHIP_PROOF",
    ),
    (
        "REAL_HONG_KONG_PACKAGE_ADMISSION",
        "packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/package.json",
        "NOT_READY",
        "REAL_PACKAGE_ADMISSION",
    ),
    (
        "OFFICIAL_SOURCE_ADMISSION",
        "NOT_CREATED",
        "NOT_STARTED",
        "EXTERNAL_SOURCE_PROFILE_AND_RIGHTS",
    ),
    (
        "MODEL_AND_EMBEDDING_ADMISSION",
        "NOT_CREATED",
        "NOT_STARTED",
        "DEPLOYMENT_PROFILE_AND_EVALUATION",
    ),
    (
        "PINECONE_ADMISSION",
        "NOT_CREATED",
        "NOT_STARTED",
        "PLAN_PROJECT_CREDENTIALS_AND_WRITE_AUTHORITY",
    ),
    (
        "UBUNTU_END_TO_END_ADMISSION",
        "NOT_CREATED",
        "NOT_STARTED",
        "DEPLOYMENT_RECOVERY_AND_OPERATIONAL_PROOF",
    ),
    (
        "V1_ACCEPTANCE",
        "NOT_CREATED",
        "NOT_STARTED",
        "COMPLETE_EVIDENCE_AND_NAMED_HUMAN_ACCEPTANCE",
    ),
)


class V1AdmissionCode(StrEnum):
    """Closed composite admission validation findings."""

    ADMISSION = "ADMISSION"
    AUTHORITY = "AUTHORITY"
    COMPONENT = "COMPONENT"
    EVIDENCE = "EVIDENCE"
    INVENTORY = "INVENTORY"
    SECRET = "SECRET"
    STATE = "STATE"


@dataclass(frozen=True, slots=True)
class V1AdmissionFinding:
    """One stable fail-closed composite admission finding."""

    code: V1AdmissionCode
    detail: str


@dataclass(frozen=True, slots=True)
class V1AdmissionReport:
    """One complete V1 verdict that cannot imply readiness from static checks."""

    components: int
    static_contracts_validated: int
    blockers: int
    admitted: bool


def _read_object(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise ValueError(_DOCUMENT_TOO_LARGE)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError(_DOCUMENT_ROOT)
    return value


def _objects(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError(_OBJECT_LIST)
    return tuple(item for item in value if isinstance(item, dict))


def _secret_findings(value: object, path: str = "$") -> tuple[V1AdmissionFinding, ...]:
    findings: list[V1AdmissionFinding] = []
    if isinstance(value, dict):
        forbidden = {"api_key", "password", "private_key", "secret", "token"}
        for key, child in value.items():
            if key.lower() in forbidden:
                findings.append(V1AdmissionFinding(V1AdmissionCode.SECRET, f"{path}.{key}"))
            findings.extend(_secret_findings(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_secret_findings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        findings.append(V1AdmissionFinding(V1AdmissionCode.SECRET, path))
    return tuple(findings)


def _component_tuple(component: dict[str, object]) -> tuple[object, ...]:
    return (
        component.get("component_id"),
        component.get("evidence"),
        component.get("state"),
        component.get("admission_blocker"),
    )


def validate_v1_admission_policy(
    policy: dict[str, object], root: Path
) -> tuple[V1AdmissionFinding, ...]:
    """Return every drift in the complete deliberately blocked V1 verdict."""
    findings = list(_secret_findings(policy))
    if (
        frozenset(policy) != _DOCUMENT_KEYS
        or policy.get("schema_version") != 1
        or policy.get("status") != "DESIGN_ONLY_DISABLED"
    ):
        findings.append(V1AdmissionFinding(V1AdmissionCode.INVENTORY, "document"))
    if policy.get("authority") != _AUTHORITY:
        findings.append(V1AdmissionFinding(V1AdmissionCode.AUTHORITY, "authority"))
    if (
        policy.get("admission_statement") != "V1_POC_NOT_ADMITTED"
        or policy.get("ready") is not False
    ):
        findings.append(V1AdmissionFinding(V1AdmissionCode.ADMISSION, "verdict"))
    components = _objects(policy.get("components"))
    if tuple(_component_tuple(item) for item in components) != _EXPECTED_COMPONENTS:
        findings.append(V1AdmissionFinding(V1AdmissionCode.COMPONENT, "inventory"))
    for component in components:
        component_id = component.get("component_id")
        label = component_id if isinstance(component_id, str) else "unknown"
        if frozenset(component) != _COMPONENT_KEYS:
            findings.append(V1AdmissionFinding(V1AdmissionCode.INVENTORY, label))
        evidence = component.get("evidence")
        state = component.get("state")
        if evidence != "NOT_CREATED" and (
            not isinstance(evidence, str) or not (root / evidence).is_file()
        ):
            findings.append(V1AdmissionFinding(V1AdmissionCode.EVIDENCE, label))
        if state not in {_STATIC_STATE, "NOT_READY", "NOT_STARTED"}:
            findings.append(V1AdmissionFinding(V1AdmissionCode.STATE, label))
    return tuple(findings)


def _check_static_contracts(root: Path) -> None:
    check_topology(root)
    check_policy(root)
    check_credential_interface_policy(root)
    check_artifact_policy(root)
    check_application_image_policy(root)
    check_runtime_input_policy(root)
    check_systemd_input_policy(root)
    check_host_identity_policy(root)


def check_v1_admission(root: Path) -> V1AdmissionReport:
    """Validate every present static gate and return the complete non-admission."""
    policy = _read_object(root / ADMISSION_POLICY_PATH)
    findings = validate_v1_admission_policy(policy, root)
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    _check_static_contracts(root)
    components = _objects(policy["components"])
    static_count = sum(item.get("state") == _STATIC_STATE for item in components)
    return V1AdmissionReport(
        components=len(components),
        static_contracts_validated=static_count,
        blockers=len(components),
        admitted=False,
    )


def main() -> None:
    """Run the complete local V1 admission verdict."""
    root = Path(__file__).resolve().parents[1]
    report = check_v1_admission(root)
    print(  # noqa: T201
        "PASS V1 POC composite admission gate; NOT_ADMITTED: "
        f"{report.components} components, "
        f"{report.static_contracts_validated} static contracts validated, "
        f"{report.blockers} blockers, admitted={str(report.admitted).lower()}"
    )


if __name__ == "__main__":
    main()
