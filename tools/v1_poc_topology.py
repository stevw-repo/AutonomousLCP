"""Fail-closed validation for the disabled V1 POC Ubuntu topology."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

TOPOLOGY_PATH = Path("infrastructure/poc/topology.json")
_DIGEST_REF = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_EXPECTED_SERVICES = frozenset(
    {
        "acquisition-worker",
        "control-plane",
        "dts-general",
        "dts-promotion",
        "egress-model",
        "egress-promotion",
        "egress-source",
        "grafana",
        "legal-processing-worker",
        "otel-collector",
        "prometheus",
        "promotion-worker",
        "review-api",
        "sql-server",
        "vault-primary",
        "vault-recovery",
    }
)
_EXPECTED_DATABASES = ("AskLegalPocIntegration", "AskLegalPocOperational")
_EXPECTED_TOP_LEVEL_KEYS = frozenset(
    {
        "authoritative_audit",
        "databases",
        "host",
        "networks",
        "pinecone",
        "recovery_class",
        "scheduler_instances",
        "schema_version",
        "services",
        "status",
        "vaults",
    }
)
_EXPECTED_SERVICE_KEYS = frozenset(
    {
        "artifact_ref",
        "artifact_state",
        "credential_names",
        "enabled",
        "identity",
        "kind",
        "listeners",
        "networks",
        "outbound_profile",
        "service_id",
        "write_paths",
    }
)
_EXPECTED_LISTENER_KEYS = frozenset({"port", "scope"})
_EXPECTED_NETWORK_KEYS = frozenset({"internal", "members", "network_id"})
_EXPECTED_EGRESS_NETWORKS = frozenset(
    {"asklegal-egress-model", "asklegal-egress-promotion", "asklegal-egress-source"}
)
_EXPECTED_VAULT_KEYS = frozenset(
    {
        "bucket",
        "manifest_last_required",
        "object_lock_required",
        "root",
        "service_id",
        "sidecar",
        "versioning_required",
        "versions",
    }
)
_EXPECTED_SCHEDULER_KEYS = frozenset({"loss_result", "persistence", "service_id", "task_hubs"})
_PAIR_COUNT = 2
_MAX_PORT = 65_535
_MAX_TOPOLOGY_BYTES = 1_000_000
_TOPOLOGY_TOO_LARGE = "topology too large"
_TOPOLOGY_ROOT_TYPE = "topology root"


class TopologyCode(StrEnum):
    """Closed topology validation findings."""

    ARTIFACT = "ARTIFACT"
    AUTHORITY = "AUTHORITY"
    CREDENTIAL = "CREDENTIAL"
    DUPLICATE = "DUPLICATE"
    HOST = "HOST"
    INVENTORY = "INVENTORY"
    NETWORK = "NETWORK"
    RECOVERY = "RECOVERY"
    SCHEDULER = "SCHEDULER"
    SECRET = "SECRET"
    SURFACE = "SURFACE"
    VAULT = "VAULT"


@dataclass(frozen=True, slots=True)
class TopologyFinding:
    """One stable fail-closed topology finding."""

    code: TopologyCode
    detail: str


@dataclass(frozen=True, slots=True)
class TopologyReport:
    """One successful closed topology summary."""

    services: int
    networks: int
    credentials: int
    pinned_artifacts: int
    pins_required: int


def _objects(value: object, label: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(label)
    return tuple(item for item in value if isinstance(item, dict))


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(type(item) is str and item for item in value):
        raise ValueError(label)
    return tuple(item for item in value if isinstance(item, str))


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(label)
    return value


def _duplicates(values: Iterable[str]) -> bool:
    sequence = tuple(values)
    return len(sequence) != len(set(sequence))


def _secret_findings(value: object, path: str = "$") -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    if isinstance(value, dict):
        forbidden_keys = {"password", "secret", "token", "api_key", "private_key"}
        for key, child in value.items():
            if key.lower() in forbidden_keys:
                findings.append(TopologyFinding(TopologyCode.SECRET, f"{path}.{key}"))
            findings.extend(_secret_findings(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_secret_findings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        findings.append(TopologyFinding(TopologyCode.SECRET, path))
    return tuple(findings)


def _validate_host(document: dict[str, object]) -> tuple[TopologyFinding, ...]:
    host = document.get("host")
    if not isinstance(host, dict):
        return (TopologyFinding(TopologyCode.HOST, "host"),)
    expected = {
        "os": "Ubuntu 24.04",
        "architecture": "x86_64",
        "minimum_ram_gib": 60,
        "physical_disk_count": 3,
        "minimum_ext4_capacity_tb": 3,
        "mac_runtime_dependency": False,
    }
    return () if host == expected else (TopologyFinding(TopologyCode.HOST, "exact host"),)


def _validate_artifact(service: dict[str, object], service_id: str) -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    state = service.get("artifact_state")
    artifact = service.get("artifact_ref")
    if service.get("enabled") is not False:
        findings.append(TopologyFinding(TopologyCode.ARTIFACT, f"{service_id} enabled"))
    if state == "PINNED":
        if not isinstance(artifact, str) or not _DIGEST_REF.fullmatch(artifact):
            findings.append(TopologyFinding(TopologyCode.ARTIFACT, service_id))
    elif state == "PIN_REQUIRED":
        if artifact is not None:
            findings.append(TopologyFinding(TopologyCode.ARTIFACT, service_id))
    else:
        findings.append(TopologyFinding(TopologyCode.ARTIFACT, service_id))
    if isinstance(artifact, str) and "latest" in artifact.lower():
        findings.append(TopologyFinding(TopologyCode.ARTIFACT, f"{service_id} latest"))
    return tuple(findings)


def _validate_service(service: dict[str, object]) -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    service_id = _text(service.get("service_id"), "service_id")
    if frozenset(service) != _EXPECTED_SERVICE_KEYS:
        findings.append(TopologyFinding(TopologyCode.INVENTORY, f"{service_id} schema"))
    findings.extend(_validate_artifact(service, service_id))
    for listener in _objects(service.get("listeners"), "listeners"):
        if frozenset(listener) != _EXPECTED_LISTENER_KEYS:
            findings.append(TopologyFinding(TopologyCode.SURFACE, f"{service_id} listener"))
        if listener.get("scope") not in {"CONTAINER_ONLY", "PRIVATE_HOST"}:
            findings.append(TopologyFinding(TopologyCode.SURFACE, service_id))
        port = listener.get("port")
        if type(port) is not int or not 1 <= port <= _MAX_PORT:
            findings.append(TopologyFinding(TopologyCode.SURFACE, f"{service_id} port"))
    credential_names = _strings(service.get("credential_names"), "credential_names")
    if _duplicates(credential_names):
        findings.append(TopologyFinding(TopologyCode.CREDENTIAL, service_id))
    return tuple(findings)


def _validate_services(
    services: tuple[dict[str, object], ...],
) -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    service_ids = tuple(_text(service.get("service_id"), "service_id") for service in services)
    identities = tuple(_text(service.get("identity"), "identity") for service in services)
    if _duplicates(service_ids) or _duplicates(identities):
        findings.append(TopologyFinding(TopologyCode.DUPLICATE, "service identity"))
    if frozenset(service_ids) != _EXPECTED_SERVICES:
        findings.append(TopologyFinding(TopologyCode.INVENTORY, "service inventory"))
    for service in services:
        findings.extend(_validate_service(service))
    return tuple(findings)


def _validate_networks(
    services: tuple[dict[str, object], ...],
    networks: tuple[dict[str, object], ...],
) -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    service_networks = {
        _text(service.get("service_id"), "service_id"): set(
            _strings(service.get("networks"), "networks")
        )
        for service in services
    }
    network_ids = tuple(_text(network.get("network_id"), "network_id") for network in networks)
    if _duplicates(network_ids):
        findings.append(TopologyFinding(TopologyCode.DUPLICATE, "network"))
    declared_networks = set(network_ids)
    if set().union(*service_networks.values()) != declared_networks:
        findings.append(TopologyFinding(TopologyCode.NETWORK, "network inventory"))
    for network in networks:
        network_id = _text(network.get("network_id"), "network_id")
        expected_internal = network_id not in _EXPECTED_EGRESS_NETWORKS
        if (
            frozenset(network) != _EXPECTED_NETWORK_KEYS
            or network.get("internal") is not expected_internal
        ):
            findings.append(TopologyFinding(TopologyCode.NETWORK, f"{network_id} schema"))
        members = set(_strings(network.get("members"), "members"))
        if not members <= _EXPECTED_SERVICES:
            findings.append(TopologyFinding(TopologyCode.NETWORK, f"{network_id} member"))
        for service_id in _EXPECTED_SERVICES:
            declared = network_id in service_networks.get(service_id, set())
            if declared != (service_id in members):
                findings.append(TopologyFinding(TopologyCode.NETWORK, f"{network_id}/{service_id}"))
    return tuple(findings)


def _validate_vaults(document: dict[str, object]) -> tuple[TopologyFinding, ...]:
    vaults = _objects(document.get("vaults"), "vaults")
    if len(vaults) != _PAIR_COUNT:
        return (TopologyFinding(TopologyCode.VAULT, "count"),)
    compared = ("service_id", "bucket", "root", "versions", "sidecar")
    findings: list[TopologyFinding] = []
    expected_service_ids = {"vault-primary", "vault-recovery"}
    if {_text(vault.get("service_id"), "service_id") for vault in vaults} != expected_service_ids:
        findings.append(TopologyFinding(TopologyCode.VAULT, "service inventory"))
    findings.extend(
        TopologyFinding(TopologyCode.VAULT, field)
        for field in compared
        if len({_text(vault.get(field), field) for vault in vaults}) != _PAIR_COUNT
    )
    for vault in vaults:
        if frozenset(vault) != _EXPECTED_VAULT_KEYS:
            findings.append(TopologyFinding(TopologyCode.VAULT, "schema"))
        if any(
            vault.get(field) is not True
            for field in ("object_lock_required", "versioning_required", "manifest_last_required")
        ):
            findings.append(TopologyFinding(TopologyCode.VAULT, "required behavior"))
    return tuple(findings)


def _validate_schedulers(document: dict[str, object]) -> tuple[TopologyFinding, ...]:
    schedulers = _objects(document.get("scheduler_instances"), "scheduler_instances")
    if len(schedulers) != _PAIR_COUNT:
        return (TopologyFinding(TopologyCode.SCHEDULER, "count"),)
    hubs: list[str] = []
    if {_text(item.get("service_id"), "service_id") for item in schedulers} != {
        "dts-general",
        "dts-promotion",
    }:
        return (TopologyFinding(TopologyCode.SCHEDULER, "service inventory"),)
    for scheduler in schedulers:
        if frozenset(scheduler) != _EXPECTED_SCHEDULER_KEYS:
            return (TopologyFinding(TopologyCode.SCHEDULER, "schema"),)
        hubs.extend(_strings(scheduler.get("task_hubs"), "task_hubs"))
        if (
            scheduler.get("persistence") != "MEMORY_ONLY"
            or scheduler.get("loss_result") != "REPLACEMENT_FROM_SAFE_CHECKPOINT"
        ):
            return (TopologyFinding(TopologyCode.SCHEDULER, "loss semantics"),)
    if _duplicates(hubs) or set(hubs) != {
        "acquisition",
        "control",
        "legal-processing",
        "promotion",
    }:
        return (TopologyFinding(TopologyCode.SCHEDULER, "task hubs"),)
    return ()


def validate_topology(document: dict[str, object]) -> tuple[TopologyFinding, ...]:
    """Return every stable topology finding; an empty tuple is admission."""
    findings = list(_secret_findings(document))
    if frozenset(document) != _EXPECTED_TOP_LEVEL_KEYS:
        findings.append(TopologyFinding(TopologyCode.INVENTORY, "document schema"))
    if document.get("schema_version") != 1 or document.get("status") != "DESIGN_ONLY_DISABLED":
        findings.append(TopologyFinding(TopologyCode.INVENTORY, "header"))
    findings.extend(_validate_host(document))
    if document.get("recovery_class") != "LOGICALLY_SEPARATE_POC_RECOVERY":
        findings.append(TopologyFinding(TopologyCode.RECOVERY, "recovery class"))
    if tuple(document.get("databases", ())) != _EXPECTED_DATABASES:
        findings.append(TopologyFinding(TopologyCode.AUTHORITY, "databases"))
    services = _objects(document.get("services"), "services")
    networks = _objects(document.get("networks"), "networks")
    findings.extend(_validate_services(services))
    findings.extend(_validate_networks(services, networks))
    findings.extend(_validate_vaults(document))
    findings.extend(_validate_schedulers(document))
    if set(document.get("authoritative_audit", ())) != {
        "RECOVERY_VAULT_IMMUTABLE_ARCHIVE",
        "SQL_SERVER_LEDGER",
    }:
        findings.append(TopologyFinding(TopologyCode.AUTHORITY, "audit"))
    pinecone = document.get("pinecone")
    if not isinstance(pinecone, dict) or pinecone != {
        "project_isolation": "DEDICATED_POC_PROJECT",
        "mutation_owner": "promotion-worker",
        "replacement_indexes_only": True,
        "real_write_authorized": False,
        "plan": "UNSELECTED_PENDING_MEASUREMENT",
    }:
        findings.append(TopologyFinding(TopologyCode.AUTHORITY, "pinecone"))
    return tuple(findings)


def load_topology(path: Path) -> dict[str, object]:
    """Load one bounded JSON topology object."""
    raw = path.read_bytes()
    if len(raw) > _MAX_TOPOLOGY_BYTES:
        raise ValueError(_TOPOLOGY_TOO_LARGE)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError(_TOPOLOGY_ROOT_TYPE)
    return value


def check_topology(root: Path) -> TopologyReport:
    """Validate the repository topology and return its exact summary."""
    document = load_topology(root / TOPOLOGY_PATH)
    findings = validate_topology(document)
    if findings:
        detail = ", ".join(f"{finding.code.value}:{finding.detail}" for finding in findings)
        raise ValueError(detail)
    services = _objects(document["services"], "services")
    credentials = {
        credential
        for service in services
        for credential in _strings(service.get("credential_names"), "credential_names")
    }
    return TopologyReport(
        services=len(services),
        networks=len(_objects(document["networks"], "networks")),
        credentials=len(credentials),
        pinned_artifacts=sum(service.get("artifact_state") == "PINNED" for service in services),
        pins_required=sum(service.get("artifact_state") == "PIN_REQUIRED" for service in services),
    )


def main() -> None:
    """Run the repository topology gate."""
    root = Path(__file__).resolve().parents[1]
    report = check_topology(root)
    print(
        "PASS V1 POC topology: "
        f"{report.services} services, {report.networks} networks, "
        f"{report.credentials} credential references, {report.pinned_artifacts} pinned, "
        f"{report.pins_required} pins required"
    )


if __name__ == "__main__":
    main()
