"""Fail-closed inputs for the executable V1 credential-interface proof."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tools.v1_poc_artifacts import ARTIFACT_POLICY_PATH, load_artifact_policy
from tools.v1_poc_systemd_units import SYSTEMD_POLICY_PATH

CREDENTIAL_INTERFACE_POLICY_PATH = Path(
    "infrastructure/poc/credential_interface_proof_inputs.json"
)
_MAX_DOCUMENT_BYTES = 1_000_000
_SECRET_VALUE = re.compile(
    r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)"
)
_DOCUMENT_KEYS = frozenset(
    {
        "authority",
        "blockers",
        "decision_gate_on_failure",
        "inspection_surfaces",
        "isolation_rule",
        "ready",
        "required_evidence",
        "required_steps",
        "schema_version",
        "secret_rule",
        "status",
        "subjects",
        "target_host",
    }
)
_SUBJECT_KEYS = frozenset(
    {
        "artifact_id",
        "artifact_ref",
        "artifact_selection_state",
        "credential_names",
        "evidence_refs",
        "product",
        "result",
        "service_id",
        "test_state_ref",
    }
)
_AUTHORITY = {
    "credential_creation_authorized": False,
    "host_mutation_authorized": False,
    "image_pull_authorized": False,
    "image_resolution_authorized": False,
    "service_enablement_authorized": False,
    "throwaway_state_cleanup_authorized": False,
}
_TARGET_HOST = {
    "os_id": "ubuntu",
    "os_version_id": "24.04",
    "architecture": "x86_64",
    "container_runtime": "docker",
    "service_manager": "systemd",
}
_SECRET_RULE = {
    "delivery": "SYSTEMD_CREDS_LOAD_CREDENTIAL_ENCRYPTED",
    "plaintext_runtime_location": "READ_ONLY_CREDENTIAL_FILE_ONLY",
    "credential_values_in_evidence_forbidden": True,
    "persisted_canary_forbidden": True,
    "arguments_forbidden": True,
    "environment_forbidden": True,
    "logs_forbidden": True,
    "image_metadata_forbidden": True,
    "persistent_files_forbidden": True,
}
_ISOLATION_RULE = {
    "external_network_after_image_acquisition_forbidden": True,
    "real_credentials_forbidden": True,
    "test_state": "NAMED_THROWAWAY_ONLY",
}
_STEPS = (
    "DELIVER_SYSTEMD_CREDENTIAL_FILES",
    "INITIALIZE_WITHOUT_SECRET_COPY",
    "INSPECT_CANARY_ABSENCE",
    "ROTATE_AND_REJECT_OLD_VALUE",
    "RESTART_WITHOUT_BOOTSTRAP_REINTRODUCTION",
    "CAPTURE_EVIDENCE_THEN_CLEAN_NAMED_STATE",
)
_INSPECTION_SURFACES = (
    "SYSTEMD_UNIT_CONFIGURATION",
    "CONTAINER_CONFIGURATION",
    "PROCESS_ARGUMENTS",
    "PROCESS_ENVIRONMENT",
    "SERVICE_LOGS",
    "FILESYSTEM_LAYERS",
    "PERSISTENT_VOLUMES",
)
_REQUIRED_EVIDENCE = (
    "ARTIFACT_DIGEST",
    "SYSTEMD_CREDENTIAL_DELIVERY_RECEIPT",
    "SYSTEMD_UNIT_INSPECTION",
    "CONTAINER_INSPECTION",
    "PROCESS_INSPECTION",
    "LOG_INSPECTION",
    "FILESYSTEM_LAYER_INSPECTION",
    "PERSISTENT_VOLUME_INSPECTION",
    "ROTATION_OLD_VALUE_REJECTION",
    "RESTART_WITHOUT_BOOTSTRAP_REINTRODUCTION",
    "NAMED_CLEANUP_RECEIPT",
    "MANIFEST_LAST_EVIDENCE_PACKAGE",
)
_SUBJECTS = (
    ("sql-server", "sql-server", "SQL_SERVER_2025"),
    ("vault-primary", "versity-gateway", "VERSITY_GATEWAY"),
    ("vault-recovery", "versity-gateway", "VERSITY_GATEWAY"),
)
_DECISION_GATE = {
    "silent_relaxation_forbidden": True,
    "choices": [
        "NATIVE_FILE_INPUT_PRODUCT",
        "MAINTAINED_CUSTOM_BUILD",
        "EXPLICIT_BOUNDED_RELAXATION",
    ],
    "recommendation": "PRESERVE_RULE_PREFER_NATIVE_FILE_INTERFACE",
}
_BLOCKERS = (
    "UBUNTU_HOST_ACCESS",
    "READ_ONLY_IMAGE_RESOLUTION_AUTHORITY",
    "IMAGE_PULL_RUN_AUTHORITY",
    "VERSITY_VERSION_AND_DIGEST",
    "SYNTHETIC_CREDENTIAL_CREATION_AUTHORITY",
    "NAMED_THROWAWAY_STATE_MUTATION_AND_CLEANUP_AUTHORITY",
)


class CredentialInterfaceCode(StrEnum):
    """Closed credential-interface proof-input findings."""

    ADMISSION = "ADMISSION"
    ARTIFACT = "ARTIFACT"
    AUTHORITY = "AUTHORITY"
    BLOCKER = "BLOCKER"
    EVIDENCE = "EVIDENCE"
    INVENTORY = "INVENTORY"
    SECRET = "SECRET"
    STATE = "STATE"
    SYSTEMD = "SYSTEMD"


@dataclass(frozen=True, slots=True)
class CredentialInterfaceFinding:
    """One exact proof-input mismatch."""

    code: CredentialInterfaceCode
    detail: str


@dataclass(frozen=True, slots=True)
class CredentialInterfaceReport:
    """One valid but deliberately unexecuted credential-interface plan."""

    subjects: int
    steps: int
    inspection_surfaces: int
    blockers: tuple[str, ...]
    executed: int


def _read_object(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        message = f"credential interface document too large: {path}"
        raise ValueError(message)
    value = json.loads(raw)
    if not isinstance(value, dict):
        message = f"credential interface document root: {path}"
        raise TypeError(message)
    return value


def _objects(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        message = "credential interface object list"
        raise TypeError(message)
    return tuple(item for item in value if isinstance(item, dict))


def _strings(value: object, *, empty_allowed: bool = False) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not value and not empty_allowed)
        or not all(type(item) is str and item for item in value)
    ):
        message = "credential interface string list"
        raise TypeError(message)
    return tuple(item for item in value if isinstance(item, str))


def _has_secret(value: object) -> bool:
    if isinstance(value, dict):
        forbidden = {"api_key", "password", "private_key", "secret", "token"}
        return any(key.lower() in forbidden or _has_secret(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_has_secret(child) for child in value)
    return isinstance(value, str) and _SECRET_VALUE.search(value) is not None


def _by_id(
    items: tuple[dict[str, object], ...], field: str
) -> dict[str, dict[str, object]]:
    return {value: item for item in items if type(value := item.get(field)) is str}


def _validate_document(policy: dict[str, object]) -> list[CredentialInterfaceFinding]:
    findings: list[CredentialInterfaceFinding] = []
    if (
        frozenset(policy) != _DOCUMENT_KEYS
        or policy.get("schema_version") != 1
        or policy.get("status") != "DESIGN_ONLY_DISABLED"
    ):
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.INVENTORY, "document")
        )
    if policy.get("ready") is not False:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.ADMISSION, "ready")
        )
    if policy.get("authority") != _AUTHORITY:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.AUTHORITY, "authority")
        )
    if policy.get("target_host") != _TARGET_HOST:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.INVENTORY, "target host")
        )
    if policy.get("secret_rule") != _SECRET_RULE:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.SECRET, "secret rule")
        )
    if policy.get("isolation_rule") != _ISOLATION_RULE:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.STATE, "isolation")
        )
    if _has_secret(policy):
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.SECRET, "embedded material")
        )
    findings.extend(_validate_proof_inventory(policy))
    return findings


def _validate_proof_inventory(
    policy: dict[str, object],
) -> tuple[CredentialInterfaceFinding, ...]:
    findings: list[CredentialInterfaceFinding] = []
    steps = _objects(policy.get("required_steps"))
    if tuple((item.get("step_id"), item.get("state")) for item in steps) != tuple(
        (step, "NOT_RUN") for step in _STEPS
    ):
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.STATE, "steps"))
    if _strings(policy.get("inspection_surfaces")) != _INSPECTION_SURFACES:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.EVIDENCE, "inspection surfaces")
        )
    if _strings(policy.get("required_evidence")) != _REQUIRED_EVIDENCE:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.EVIDENCE, "required evidence")
        )
    if policy.get("decision_gate_on_failure") != _DECISION_GATE:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.STATE, "failure decision")
        )
    if tuple(policy.get("blockers", ())) != _BLOCKERS:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.BLOCKER, "blockers")
        )
    return tuple(findings)


def _validate_subjects(
    policy: dict[str, object],
    artifact_policy: dict[str, object],
    systemd_policy: dict[str, object],
) -> tuple[CredentialInterfaceFinding, ...]:
    findings: list[CredentialInterfaceFinding] = []
    subjects = _objects(policy.get("subjects"))
    artifacts = _by_id(_objects(artifact_policy.get("artifacts")), "artifact_id")
    units = _by_id(_objects(systemd_policy.get("service_units")), "service_id")
    if tuple(item.get("service_id") for item in subjects) != tuple(item[0] for item in _SUBJECTS):
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.INVENTORY, "subjects")
        )
        return tuple(findings)
    for subject, (service_id, artifact_id, product) in zip(subjects, _SUBJECTS, strict=True):
        if frozenset(subject) != _SUBJECT_KEYS:
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.INVENTORY, service_id)
            )
        artifact = artifacts.get(artifact_id)
        unit = units.get(service_id)
        if artifact is None or (
            artifact.get("credential_interface_gate") is not True
            or subject.get("artifact_id") != artifact_id
            or subject.get("product") != product
            or subject.get("artifact_selection_state") != artifact.get("selection_state")
            or subject.get("artifact_ref") != artifact.get("artifact_ref")
        ):
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.ARTIFACT, service_id)
            )
        if unit is None or subject.get("credential_names") != unit.get("credential_names"):
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.SYSTEMD, service_id)
            )
        if subject.get("result") != "NOT_RUN" or subject.get("test_state_ref") is not None:
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.STATE, service_id)
            )
        if _strings(subject.get("evidence_refs"), empty_allowed=True):
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.EVIDENCE, service_id)
            )
    return tuple(findings)


def validate_credential_interface_policy(
    policy: dict[str, object],
    artifact_policy: dict[str, object],
    systemd_policy: dict[str, object],
) -> tuple[CredentialInterfaceFinding, ...]:
    """Return every drift in the disabled exact-image proof inputs."""
    findings = _validate_document(policy)
    findings.extend(_validate_subjects(policy, artifact_policy, systemd_policy))
    return tuple(findings)


def check_credential_interface_policy(root: Path) -> CredentialInterfaceReport:
    """Validate proof inputs without host inspection, image access, or credentials."""
    policy = _read_object(root / CREDENTIAL_INTERFACE_POLICY_PATH)
    artifact_policy = load_artifact_policy(root / ARTIFACT_POLICY_PATH)
    systemd_policy = _read_object(root / SYSTEMD_POLICY_PATH)
    findings = validate_credential_interface_policy(policy, artifact_policy, systemd_policy)
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    return CredentialInterfaceReport(
        subjects=len(_SUBJECTS),
        steps=len(_STEPS),
        inspection_surfaces=len(_INSPECTION_SURFACES),
        blockers=_BLOCKERS,
        executed=0,
    )


def main() -> None:
    """Print the disabled credential-interface proof summary."""
    root = Path(__file__).resolve().parents[1]
    report = check_credential_interface_policy(root)
    print(  # noqa: T201
        "PASS V1 POC credential-interface proof inputs; NOT_READY: "
        f"{report.subjects} subjects, {report.steps} steps, "
        f"{report.inspection_surfaces} inspection surfaces, "
        f"{len(report.blockers)} blockers, executed={report.executed}"
    )


if __name__ == "__main__":
    main()
