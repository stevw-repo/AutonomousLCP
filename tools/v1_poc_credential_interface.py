"""Fail-closed record of the executed V1 credential-interface proof."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from tools.v1_poc_artifacts import ARTIFACT_POLICY_PATH, load_artifact_policy
from tools.v1_poc_systemd_units import SYSTEMD_POLICY_PATH

CREDENTIAL_INTERFACE_POLICY_PATH = Path("infrastructure/poc/credential_interface_proof_inputs.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_DOCUMENT_KEYS = frozenset(
    {
        "accepted_exceptions",
        "authority",
        "blockers",
        "decision_gate_on_failure",
        "findings",
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
        "exception_id",
        "product",
        "result",
        "service_id",
        "test_state_ref",
    }
)
_STEP_KEYS = frozenset({"step_id", "state", "scope", "evidence_refs"})
_EXCEPTION_KEYS = frozenset(
    {
        "bounded_by",
        "exception_id",
        "forbidden_delivery",
        "permitted_delivery",
        "reason",
        "relaxed_rules",
        "residual_risk",
        "retirement_path",
        "subjects",
    }
)
_FINDING_KEYS = frozenset(
    {"finding_id", "procedure_proved", "required_procedure", "severity", "statement", "subjects"}
)
_AUTHORITY = {
    "credential_creation_authorized": True,
    "host_mutation_authorized": False,
    "image_pull_authorized": True,
    "image_resolution_authorized": True,
    "service_enablement_authorized": False,
    "throwaway_state_cleanup_authorized": True,
}
_TARGET_HOST = {
    "os_id": "ubuntu",
    "os_version_id": "24.04",
    "architecture": "x86_64",
    "container_runtime": "docker",
    "service_manager": "systemd",
}
_SECRET_RULE = {
    "delivery": "SYSTEMD_CREDS_AT_REST_ENVIRONMENT_DELIVERY",
    "plaintext_runtime_location": "PROCESS_ENVIRONMENT_OR_CREDENTIAL_FILE",
    "credential_values_in_evidence_forbidden": True,
    "persisted_canary_forbidden": True,
    "arguments_forbidden": True,
    "environment_forbidden": False,
    "logs_forbidden": True,
    "image_metadata_forbidden": True,
    "persistent_files_forbidden": True,
}
_UNRELAXABLE_RULES = frozenset(
    {
        "arguments_forbidden",
        "credential_values_in_evidence_forbidden",
        "persisted_canary_forbidden",
    }
)
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
_STEP_STATES = frozenset({"NOT_RUN", "PASSED", "FAILED_MITIGATED", "FAILED"})
_EXECUTED_STEP_STATES = frozenset({"PASSED", "FAILED_MITIGATED", "FAILED"})
_READY_STEP_STATES = frozenset({"PASSED"})
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
_SUBJECT_RESULTS = frozenset(
    {"NOT_RUN", "PASSED", "PASSED_WITH_FINDINGS", "EXCEPTION_ACCEPTED", "FAILED"}
)
_EXECUTED_SUBJECT_RESULTS = frozenset(
    {"PASSED", "PASSED_WITH_FINDINGS", "EXCEPTION_ACCEPTED", "FAILED"}
)
_EXCEPTION_RESULT = "EXCEPTION_ACCEPTED"
_SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH"})
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
    "SYSTEM_UNIT_AND_ENCRYPTED_CREDENTIAL_REPROOF",
    "HOST_AND_CONTAINER_UID_ALIGNMENT",
    "MANIFEST_LAST_EVIDENCE_PACKAGE",
)
_STATUS = "EXECUTED_PARTIAL"
_SCHEMA_VERSION = 2


class CredentialInterfaceCode(StrEnum):
    """Closed credential-interface proof-record findings."""

    ADMISSION = "ADMISSION"
    ARTIFACT = "ARTIFACT"
    AUTHORITY = "AUTHORITY"
    BLOCKER = "BLOCKER"
    EVIDENCE = "EVIDENCE"
    EXCEPTION = "EXCEPTION"
    FINDING = "FINDING"
    INVENTORY = "INVENTORY"
    SECRET = "SECRET"
    STATE = "STATE"
    SYSTEMD = "SYSTEMD"


@dataclass(frozen=True, slots=True)
class CredentialInterfaceFinding:
    """One exact proof-record mismatch."""

    code: CredentialInterfaceCode
    detail: str


@dataclass(frozen=True, slots=True)
class CredentialInterfaceReport:
    """One valid credential-interface proof record and its executed state."""

    subjects: int
    steps: int
    inspection_surfaces: int
    blockers: tuple[str, ...]
    executed: int
    exceptions: int
    findings: int
    ready: bool


def _read_object(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        message = f"credential interface document too large: {path}"
        raise ValueError(message)
    value: object = json.loads(raw)
    document = _string_object(value)
    if document is None:
        message = f"credential interface document root: {path}"
        raise TypeError(message)
    return document


def _objects(value: object) -> tuple[dict[str, object], ...]:
    items = _object_list(value)
    if items is None:
        message = "credential interface object list"
        raise TypeError(message)
    result: list[dict[str, object]] = []
    for item in items:
        document = _string_object(item)
        if document is None:
            message = "credential interface object list"
            raise TypeError(message)
        result.append(document)
    return tuple(result)


def _strings(value: object, *, empty_allowed: bool = False) -> tuple[str, ...]:
    if (items := _object_list(value)) is None or (not items and not empty_allowed):
        message = "credential interface string list"
        raise TypeError(message)
    result: list[str] = []
    for item in items:
        if type(item) is not str or not item:
            message = "credential interface string list"
            raise TypeError(message)
        result.append(item)
    return tuple(result)


def _string_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    candidate = cast("dict[object, object]", value)
    if not all(type(key) is str for key in candidate):
        return None
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast("list[object]", value)


def _has_secret(value: object) -> bool:
    document = _string_object(value)
    items = _object_list(value)
    if document is not None:
        forbidden = {"api_key", "password", "private_key", "secret", "token"}
        return any(
            key.lower() in forbidden or _has_secret(child) for key, child in document.items()
        )
    if items is not None:
        return any(_has_secret(child) for child in items)
    return isinstance(value, str) and _SECRET_VALUE.search(value) is not None


def _by_id(items: tuple[dict[str, object], ...], field: str) -> dict[str, dict[str, object]]:
    return {value: item for item in items if type(value := item.get(field)) is str}


def _validate_document(policy: dict[str, object]) -> list[CredentialInterfaceFinding]:
    findings: list[CredentialInterfaceFinding] = []
    if (
        frozenset(policy) != _DOCUMENT_KEYS
        or policy.get("schema_version") != _SCHEMA_VERSION
        or policy.get("status") != _STATUS
    ):
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.INVENTORY, "document"))
    if policy.get("authority") != _AUTHORITY:
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.AUTHORITY, "authority"))
    if policy.get("target_host") != _TARGET_HOST:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.INVENTORY, "target host")
        )
    if policy.get("secret_rule") != _SECRET_RULE:
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.SECRET, "secret rule"))
    if policy.get("isolation_rule") != _ISOLATION_RULE:
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.STATE, "isolation"))
    if _has_secret(policy):
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.SECRET, "embedded material")
        )
    findings.extend(_validate_proof_inventory(policy))
    findings.extend(_validate_exceptions(policy))
    findings.extend(_validate_findings(policy))
    findings.extend(_validate_readiness(policy))
    return findings


def _validate_step(step: dict[str, object], step_id: str) -> tuple[CredentialInterfaceFinding, ...]:
    findings: list[CredentialInterfaceFinding] = []
    if frozenset(step) != _STEP_KEYS or step.get("step_id") != step_id:
        return (CredentialInterfaceFinding(CredentialInterfaceCode.STATE, f"{step_id} schema"),)
    state = step.get("state")
    if state not in _STEP_STATES or type(step.get("scope")) is not str:
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.STATE, step_id))
    evidence = _strings(step.get("evidence_refs"), empty_allowed=True)
    if set(evidence) - set(_REQUIRED_EVIDENCE):
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.EVIDENCE, step_id))
    if state in _EXECUTED_STEP_STATES and not evidence:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.EVIDENCE, f"{step_id} unevidenced")
        )
    if state == "NOT_RUN" and evidence:
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.EVIDENCE, f"{step_id} unrun")
        )
    return tuple(findings)


def _validate_proof_inventory(
    policy: dict[str, object],
) -> tuple[CredentialInterfaceFinding, ...]:
    findings: list[CredentialInterfaceFinding] = []
    steps = _objects(policy.get("required_steps"))
    if tuple(item.get("step_id") for item in steps) != _STEPS:
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.STATE, "steps"))
        return tuple(findings)
    for step, step_id in zip(steps, _STEPS, strict=True):
        findings.extend(_validate_step(step, step_id))
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
    if _strings(policy.get("blockers"), empty_allowed=True) != _BLOCKERS:
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.BLOCKER, "blockers"))
    return tuple(findings)


def _validate_exceptions(
    policy: dict[str, object],
) -> tuple[CredentialInterfaceFinding, ...]:
    findings: list[CredentialInterfaceFinding] = []
    known_subjects = {item[0] for item in _SUBJECTS}
    for exception in _objects(policy.get("accepted_exceptions")):
        identifier = exception.get("exception_id")
        label = identifier if type(identifier) is str else "unknown"
        if frozenset(exception) != _EXCEPTION_KEYS:
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.EXCEPTION, f"{label} schema")
            )
            continue
        relaxed = _strings(exception.get("relaxed_rules"))
        if set(relaxed) - set(_SECRET_RULE) or set(relaxed) & _UNRELAXABLE_RULES:
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.EXCEPTION, f"{label} rules")
            )
        if set(_strings(exception.get("subjects"))) - known_subjects:
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.EXCEPTION, f"{label} subjects")
            )
        if (
            exception.get("forbidden_delivery") != "ARGUMENTS"
            or type(exception.get("permitted_delivery")) is not str
            or not _strings(exception.get("bounded_by"))
        ):
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.EXCEPTION, f"{label} delivery")
            )
        findings.extend(
            CredentialInterfaceFinding(CredentialInterfaceCode.EXCEPTION, f"{label} {field}")
            for field in ("reason", "residual_risk", "retirement_path")
            if type(exception.get(field)) is not str or not exception.get(field)
        )
    return tuple(findings)


def _validate_findings(
    policy: dict[str, object],
) -> tuple[CredentialInterfaceFinding, ...]:
    findings: list[CredentialInterfaceFinding] = []
    known_subjects = {item[0] for item in _SUBJECTS}
    for entry in _objects(policy.get("findings")):
        identifier = entry.get("finding_id")
        label = identifier if type(identifier) is str else "unknown"
        if frozenset(entry) != _FINDING_KEYS:
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.FINDING, f"{label} schema")
            )
            continue
        if (
            entry.get("severity") not in _SEVERITIES
            or type(entry.get("statement")) is not str
            or type(entry.get("required_procedure")) is not str
            or type(entry.get("procedure_proved")) is not bool
        ):
            findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.FINDING, label))
        if set(_strings(entry.get("subjects"))) - known_subjects:
            findings.append(
                CredentialInterfaceFinding(CredentialInterfaceCode.FINDING, f"{label} subjects")
            )
    return tuple(findings)


def _validate_readiness(
    policy: dict[str, object],
) -> tuple[CredentialInterfaceFinding, ...]:
    ready = policy.get("ready")
    if type(ready) is not bool:
        return (CredentialInterfaceFinding(CredentialInterfaceCode.ADMISSION, "ready"),)
    steps = _objects(policy.get("required_steps"))
    all_passed = all(step.get("state") in _READY_STEP_STATES for step in steps)
    no_blockers = not _strings(policy.get("blockers"), empty_allowed=True)
    if ready and not (all_passed and no_blockers):
        return (CredentialInterfaceFinding(CredentialInterfaceCode.ADMISSION, "ready claim"),)
    return ()


def _validate_subject_result(
    subject: dict[str, object], service_id: str, exception_ids: frozenset[str]
) -> tuple[CredentialInterfaceFinding, ...]:
    findings: list[CredentialInterfaceFinding] = []
    result = subject.get("result")
    exception_id = subject.get("exception_id")
    if result not in _SUBJECT_RESULTS:
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.STATE, service_id))
    if result == _EXCEPTION_RESULT:
        if type(exception_id) is not str or exception_id not in exception_ids:
            findings.append(
                CredentialInterfaceFinding(
                    CredentialInterfaceCode.EXCEPTION, f"{service_id} unbacked"
                )
            )
    elif exception_id is not None:
        findings.append(
            CredentialInterfaceFinding(
                CredentialInterfaceCode.EXCEPTION, f"{service_id} unused exception"
            )
        )
    evidence = _strings(subject.get("evidence_refs"), empty_allowed=True)
    if set(evidence) - set(_REQUIRED_EVIDENCE):
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.EVIDENCE, service_id))
    if result in _EXECUTED_SUBJECT_RESULTS and not evidence:
        findings.append(
            CredentialInterfaceFinding(
                CredentialInterfaceCode.EVIDENCE, f"{service_id} unevidenced"
            )
        )
    if result == "NOT_RUN" and (evidence or subject.get("test_state_ref") is not None):
        findings.append(
            CredentialInterfaceFinding(CredentialInterfaceCode.STATE, f"{service_id} unrun")
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
    exception_ids = frozenset(
        value
        for exception in _objects(policy.get("accepted_exceptions"))
        if type(value := exception.get("exception_id")) is str
    )
    if tuple(item.get("service_id") for item in subjects) != tuple(item[0] for item in _SUBJECTS):
        findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.INVENTORY, "subjects"))
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
            findings.append(CredentialInterfaceFinding(CredentialInterfaceCode.SYSTEMD, service_id))
        findings.extend(_validate_subject_result(subject, service_id, exception_ids))
    return tuple(findings)


def validate_credential_interface_policy(
    policy: dict[str, object],
    artifact_policy: dict[str, object],
    systemd_policy: dict[str, object],
) -> tuple[CredentialInterfaceFinding, ...]:
    """Return every drift in the recorded exact-image proof results."""
    findings = _validate_document(policy)
    findings.extend(_validate_subjects(policy, artifact_policy, systemd_policy))
    return tuple(findings)


def check_credential_interface_policy(root: Path) -> CredentialInterfaceReport:
    """Validate the proof record without host inspection, image access, or credentials."""
    policy = _read_object(root / CREDENTIAL_INTERFACE_POLICY_PATH)
    artifact_policy = load_artifact_policy(root / ARTIFACT_POLICY_PATH)
    systemd_policy = _read_object(root / SYSTEMD_POLICY_PATH)
    findings = validate_credential_interface_policy(policy, artifact_policy, systemd_policy)
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    steps = _objects(policy.get("required_steps"))
    return CredentialInterfaceReport(
        subjects=len(_SUBJECTS),
        steps=len(_STEPS),
        inspection_surfaces=len(_INSPECTION_SURFACES),
        blockers=_BLOCKERS,
        executed=sum(step.get("state") in _EXECUTED_STEP_STATES for step in steps),
        exceptions=len(_objects(policy.get("accepted_exceptions"))),
        findings=len(_objects(policy.get("findings"))),
        ready=policy.get("ready") is True,
    )


def main() -> None:
    """Print the recorded credential-interface proof summary."""
    root = Path(__file__).resolve().parents[1]
    report = check_credential_interface_policy(root)
    state = "READY" if report.ready else "NOT_READY"
    print(  # noqa: T201
        f"PASS V1 POC credential-interface proof record; {state}: "
        f"{report.subjects} subjects, {report.steps} steps, "
        f"{report.executed} executed, {report.exceptions} accepted exceptions, "
        f"{report.findings} findings, {len(report.blockers)} blockers"
    )


if __name__ == "__main__":
    main()
