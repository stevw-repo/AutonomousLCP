"""Fail-closed V1 POC artifact-admission inventory."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

ARTIFACT_POLICY_PATH = Path("infrastructure/poc/artifact_admission.json")
TOPOLOGY_PATH = Path("infrastructure/poc/topology.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_DIGEST_REF = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_DOCUMENT_KEYS = frozenset(
    {"artifacts", "authority", "required_evidence", "schema_version", "status"}
)
_ARTIFACT_KEYS = frozenset(
    {
        "admitted",
        "artifact_id",
        "artifact_ref",
        "consumers",
        "credential_interface_gate",
        "kind",
        "selection_state",
    }
)
_REQUIRED_EVIDENCE = (
    "EXACT_DIGEST",
    "LICENSE_POLICY",
    "PROVENANCE",
    "REPRODUCIBILITY",
    "SBOM",
    "UBUNTU_24_04_X86_64_PROOF",
    "VULNERABILITY_POLICY",
)
_PINNED_STATE = "DIGEST_PINNED_REPROOF_REQUIRED"
_PENDING_STATES = frozenset(
    {
        "PRODUCT_VERSION_AND_DIGEST_REQUIRED",
        "REPRODUCIBLE_BUILD_REQUIRED",
        "VERSION_AND_DIGEST_REQUIRED",
    }
)
_EXPECTED_ARTIFACTS = frozenset(
    {
        "acquisition-worker",
        "control-plane",
        "durable-task-scheduler-emulator",
        "egress-proxy",
        "grafana",
        "legal-processing-worker",
        "otel-collector",
        "prometheus",
        "promotion-worker",
        "review-api",
        "sql-server",
        "versity-gateway",
    }
)


class ArtifactCode(StrEnum):
    """Stable artifact-policy failure codes."""

    ADMISSION = "ADMISSION"
    AUTHORITY = "AUTHORITY"
    COVERAGE = "COVERAGE"
    DUPLICATE = "DUPLICATE"
    INVENTORY = "INVENTORY"
    KIND = "KIND"
    PIN = "PIN"
    SECRET = "SECRET"


@dataclass(frozen=True, slots=True)
class ArtifactFinding:
    """One exact artifact-policy mismatch."""

    code: ArtifactCode
    detail: str


@dataclass(frozen=True, slots=True)
class ArtifactReport:
    """One successful disabled artifact inventory summary."""

    artifacts: int
    consumers: int
    pinned_candidates: int
    selections_pending: int
    admitted: int


def _objects(value: object) -> tuple[dict[str, object], ...]:
    items = _object_list(value)
    if items is None:
        message = "artifact object list"
        raise TypeError(message)
    result: list[dict[str, object]] = []
    for item in items:
        document = _string_object(item)
        if document is None:
            message = "artifact object list"
            raise TypeError(message)
        result.append(document)
    return tuple(result)


def _strings(value: object) -> tuple[str, ...]:
    items = _object_list(value)
    if items is None:
        message = "artifact string list"
        raise TypeError(message)
    result: list[str] = []
    for item in items:
        if type(item) is not str or not item:
            message = "artifact string list"
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


def load_artifact_policy(path: Path) -> dict[str, object]:
    """Load one bounded artifact-policy object."""
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        message = "artifact policy too large"
        raise ValueError(message)
    value: object = json.loads(raw)
    document = _string_object(value)
    if document is None:
        message = "artifact policy root"
        raise TypeError(message)
    return document


def _topology_services(topology: dict[str, object]) -> dict[str, dict[str, object]]:
    services = _objects(topology.get("services"))
    return {
        service_id: service
        for service in services
        if type(service_id := service.get("service_id")) is str
    }


def _validate_pin(artifact: dict[str, object], label: str) -> tuple[ArtifactFinding, ...]:
    state = artifact.get("selection_state")
    artifact_ref = artifact.get("artifact_ref")
    if state == _PINNED_STATE:
        valid = isinstance(artifact_ref, str) and _DIGEST_REF.fullmatch(artifact_ref) is not None
    else:
        valid = state in _PENDING_STATES and artifact_ref is None
    return () if valid else (ArtifactFinding(ArtifactCode.PIN, label),)


def _validate_consumer(
    consumer: str,
    service: dict[str, object] | None,
    expected_topology_kind: str,
    state: object,
    artifact_ref: object,
) -> tuple[ArtifactFinding, ...]:
    if service is None:
        return (ArtifactFinding(ArtifactCode.COVERAGE, consumer),)
    findings: list[ArtifactFinding] = []
    if service.get("kind") != expected_topology_kind:
        findings.append(ArtifactFinding(ArtifactCode.KIND, consumer))
    if state == _PINNED_STATE:
        valid_pin = (
            service.get("artifact_state") == "PINNED"
            and service.get("artifact_ref") == artifact_ref
        )
    else:
        valid_pin = (
            service.get("artifact_state") == "PIN_REQUIRED" and service.get("artifact_ref") is None
        )
    if not valid_pin:
        findings.append(ArtifactFinding(ArtifactCode.PIN, consumer))
    return tuple(findings)


def _validate_artifact(
    artifact: dict[str, object], services: dict[str, dict[str, object]]
) -> tuple[ArtifactFinding, ...]:
    findings: list[ArtifactFinding] = []
    artifact_id = artifact.get("artifact_id")
    label = artifact_id if isinstance(artifact_id, str) else "unknown"
    if frozenset(artifact) != _ARTIFACT_KEYS:
        findings.append(ArtifactFinding(ArtifactCode.INVENTORY, f"{label} schema"))
    consumers = _strings(artifact.get("consumers"))
    if len(consumers) != len(set(consumers)):
        findings.append(ArtifactFinding(ArtifactCode.DUPLICATE, f"{label} consumer"))
    if artifact.get("admitted") is not False:
        findings.append(ArtifactFinding(ArtifactCode.ADMISSION, label))
    kind = artifact.get("kind")
    expected_topology_kind = "REPOSITORY_IMAGE" if kind == "REPOSITORY_IMAGE" else "CONTAINER"
    if kind not in {"REPOSITORY_IMAGE", "UPSTREAM_CONTAINER"}:
        findings.append(ArtifactFinding(ArtifactCode.KIND, label))
    state = artifact.get("selection_state")
    artifact_ref = artifact.get("artifact_ref")
    findings.extend(_validate_pin(artifact, label))
    for consumer in consumers:
        findings.extend(
            _validate_consumer(
                consumer, services.get(consumer), expected_topology_kind, state, artifact_ref
            )
        )
    return tuple(findings)


def _validate_document(policy: dict[str, object]) -> tuple[ArtifactFinding, ...]:
    findings: list[ArtifactFinding] = []
    if (
        frozenset(policy) != _DOCUMENT_KEYS
        or policy.get("schema_version") != 1
        or policy.get("status") != "DESIGN_ONLY_DISABLED"
    ):
        findings.append(ArtifactFinding(ArtifactCode.INVENTORY, "document"))
    if _has_secret(policy):
        findings.append(ArtifactFinding(ArtifactCode.SECRET, "policy"))
    try:
        required_evidence = _strings(policy.get("required_evidence"))
    except TypeError:
        required_evidence = ()
    if required_evidence != _REQUIRED_EVIDENCE:
        findings.append(ArtifactFinding(ArtifactCode.ADMISSION, "evidence"))
    if policy.get("authority") != {
        "image_build_authorized": False,
        "registry_pull_authorized": False,
        "registry_push_authorized": False,
        "service_enablement_authorized": False,
    }:
        findings.append(ArtifactFinding(ArtifactCode.AUTHORITY, "artifact authority"))
    return tuple(findings)


def validate_artifact_policy(
    policy: dict[str, object], topology: dict[str, object]
) -> tuple[ArtifactFinding, ...]:
    """Return all policy/topology mismatches; empty means inventory conformance only."""
    findings = list(_validate_document(policy))
    artifacts = _objects(policy.get("artifacts"))
    artifact_ids = tuple(
        artifact_id
        for item in artifacts
        if isinstance((artifact_id := item.get("artifact_id")), str)
    )
    if len(artifact_ids) != len(artifacts) or len(artifact_ids) != len(set(artifact_ids)):
        findings.append(ArtifactFinding(ArtifactCode.DUPLICATE, "artifact id"))
    if frozenset(artifact_ids) != _EXPECTED_ARTIFACTS:
        findings.append(ArtifactFinding(ArtifactCode.INVENTORY, "artifact ids"))
    services = _topology_services(topology)
    consumers: list[str] = []
    credential_gate_consumers: set[str] = set()
    for artifact in artifacts:
        artifact_consumers = _strings(artifact.get("consumers"))
        consumers.extend(artifact_consumers)
        if artifact.get("credential_interface_gate") is True:
            credential_gate_consumers.update(artifact_consumers)
        findings.extend(_validate_artifact(artifact, services))
    if len(consumers) != len(set(consumers)) or set(consumers) != set(services):
        findings.append(ArtifactFinding(ArtifactCode.COVERAGE, "service consumers"))
    if credential_gate_consumers != {"sql-server", "vault-primary", "vault-recovery"}:
        findings.append(ArtifactFinding(ArtifactCode.ADMISSION, "credential interface gates"))
    return tuple(findings)


def check_artifact_policy(root: Path) -> ArtifactReport:
    """Validate the repository artifact inventory and its topology binding."""
    policy = load_artifact_policy(root / ARTIFACT_POLICY_PATH)
    topology = load_artifact_policy(root / TOPOLOGY_PATH)
    findings = validate_artifact_policy(policy, topology)
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    artifacts = _objects(policy["artifacts"])
    return ArtifactReport(
        artifacts=len(artifacts),
        consumers=sum(len(_strings(item["consumers"])) for item in artifacts),
        pinned_candidates=sum(item.get("selection_state") == _PINNED_STATE for item in artifacts),
        selections_pending=sum(
            item.get("selection_state") in _PENDING_STATES for item in artifacts
        ),
        admitted=sum(item.get("admitted") is True for item in artifacts),
    )


def main() -> None:
    """Run the disabled artifact-admission inventory gate."""
    root = Path(__file__).resolve().parents[1]
    report = check_artifact_policy(root)
    print(
        "PASS V1 POC artifacts: "
        f"{report.artifacts} artifacts cover {report.consumers} services; "
        f"{report.pinned_candidates} pinned candidates, "
        f"{report.selections_pending} selections pending, {report.admitted} admitted"
    )


if __name__ == "__main__":
    main()
