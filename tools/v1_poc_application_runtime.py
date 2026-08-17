"""Fail-closed validation for disabled V1 POC application runtime inputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

RUNTIME_POLICY_PATH = Path("infrastructure/poc/application_runtime_inputs.json")
TOPOLOGY_PATH = Path("infrastructure/poc/topology.json")
_APPLICATIONS = frozenset(
    {
        "acquisition-worker",
        "control-plane",
        "legal-processing-worker",
        "promotion-worker",
        "review-api",
    }
)
_TOP_LEVEL_KEYS = frozenset(
    {
        "applications",
        "authority",
        "configuration_delivery",
        "database",
        "environment",
        "required_blockers",
        "schema_version",
        "status",
        "vault_client_profile",
    }
)
_APPLICATION_KEYS = frozenset(
    {
        "adapter_state",
        "admitted",
        "application_code",
        "credential_filenames",
        "database_role",
        "destination_service_ids",
        "enabled",
        "listener_ports",
        "outbound_profile",
        "readiness_dependency_codes",
        "readiness_probe_state",
        "service_id",
        "service_identity",
        "task_hub",
        "task_scheduler_credential_filename",
        "task_scheduler_host_address",
        "task_scheduler_loss_result",
        "task_scheduler_persistence",
        "task_scheduler_service",
        "task_scheduler_transport",
        "topology_networks",
        "vault_service_ids",
    }
)
_DELIVERY = {
    "non_secret_bundle": "ROOT_OWNED_READ_ONLY_FILE",
    "credential_directory": "SYSTEMD_CREDENTIALS_DIRECTORY",
    "credential_loader_state": "IMPLEMENTED_LOCAL_PROOF",
    "host_delivery_state": "PROOF_REQUIRED",
    "credential_files_only": True,
    "secret_environment_forbidden": True,
    "secret_arguments_forbidden": True,
    "unknown_fields_rejected": True,
    "configuration_fingerprint_required": True,
}
_AUTHORITY = {
    "runtime_adapter_implementation_authorized": True,
    "credential_creation_authorized": False,
    "destination_resolution_authorized": False,
    "service_enablement_authorized": False,
    "external_effect_authorized": False,
}
_BLOCKERS = (
    "LOGICAL_DESTINATION_RESOLUTION",
    "SYSTEMD_CREDENTIAL_DELIVERY_PROOF",
    "REAL_ADAPTER_COMPOSITION",
    "BOUNDED_READINESS_PROBES",
    "SQL_SERVER_CERTIFICATE_TRUST",
    "VAULT_SERVER_CERTIFICATE_TRUST",
    "UBUNTU_RUNTIME_PROOF",
)
_VAULT_CLIENT_PROFILE = {
    "signature_version": "s3v4",
    "addressing_style": "path",
    "region": "us-east-1",
    "retry_mode": "standard",
    "total_max_attempts": 3,
    "connect_timeout_seconds": 5,
    "read_timeout_seconds": 30,
    "tls_required": True,
    "explicit_ca_bundle_required": True,
    "ambient_credentials_forbidden": True,
}
_DATABASE_ROLES = {
    "acquisition-worker": "asklegal_acquisition_role",
    "control-plane": "asklegal_control_role",
    "legal-processing-worker": "asklegal_legal_processing_role",
    "promotion-worker": "asklegal_promotion_role",
    "review-api": "asklegal_review_role",
}
_TASK_HUBS = {
    "acquisition-worker": ("dts-general", "acquisition"),
    "control-plane": ("dts-general", "control"),
    "legal-processing-worker": ("dts-general", "legal-processing"),
    "promotion-worker": ("dts-promotion", "promotion"),
    "review-api": (None, None),
}
_VAULTS = {
    "acquisition-worker": ("vault-primary", "vault-recovery"),
    "control-plane": ("vault-primary",),
    "legal-processing-worker": ("vault-primary",),
    "promotion-worker": ("vault-primary", "vault-recovery"),
    "review-api": ("vault-primary",),
}
_READINESS_DEPENDENCIES = {
    "acquisition-worker": (
        "MANAGEMENT_REGISTER",
        "TASK_SCHEDULER_GENERAL",
        "PRIMARY_VAULT",
        "RECOVERY_VAULT",
        "TELEMETRY",
        "SOURCE_EGRESS",
    ),
    "control-plane": (
        "MANAGEMENT_REGISTER",
        "TASK_SCHEDULER_GENERAL",
        "PRIMARY_VAULT",
        "TELEMETRY",
        "REVIEW_API",
    ),
    "legal-processing-worker": (
        "MANAGEMENT_REGISTER",
        "TASK_SCHEDULER_GENERAL",
        "PRIMARY_VAULT",
        "TELEMETRY",
        "MODEL_EGRESS",
    ),
    "promotion-worker": (
        "MANAGEMENT_REGISTER",
        "TASK_SCHEDULER_PROMOTION",
        "PRIMARY_VAULT",
        "RECOVERY_VAULT",
        "TELEMETRY",
        "PROMOTION_EGRESS",
    ),
    "review-api": (
        "MANAGEMENT_REGISTER",
        "PRIMARY_VAULT",
        "TELEMETRY",
    ),
}
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_OBJECTS_ERROR = "objects"
_STRINGS_ERROR = "strings"


class RuntimeInputCode(StrEnum):
    """Closed runtime-input validation findings."""

    ADMISSION = "ADMISSION"
    AUTHORITY = "AUTHORITY"
    BLOCKER = "BLOCKER"
    CREDENTIAL = "CREDENTIAL"
    DATABASE = "DATABASE"
    DESTINATION = "DESTINATION"
    INVENTORY = "INVENTORY"
    SECRET = "SECRET"
    READINESS = "READINESS"
    TASK_HUB = "TASK_HUB"
    TOPOLOGY = "TOPOLOGY"
    VAULT = "VAULT"


@dataclass(frozen=True, slots=True)
class RuntimeInputFinding:
    """One stable fail-closed runtime-input finding."""

    code: RuntimeInputCode
    detail: str


@dataclass(frozen=True, slots=True)
class RuntimeInputReport:
    """One successful disabled runtime-input summary."""

    applications: int
    credentials: int
    logical_destinations: int
    blockers: tuple[str, ...]
    admitted: int


def _objects(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(_OBJECTS_ERROR)
    return tuple(item for item in value if isinstance(item, dict))


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(type(item) is str and item for item in value):
        raise ValueError(_STRINGS_ERROR)
    return tuple(item for item in value if isinstance(item, str))


def _secret_findings(value: object, path: str = "$") -> tuple[RuntimeInputFinding, ...]:
    findings: list[RuntimeInputFinding] = []
    if isinstance(value, dict):
        forbidden = {"password", "secret", "token", "api_key", "private_key"}
        for key, child in value.items():
            if key.lower() in forbidden:
                findings.append(RuntimeInputFinding(RuntimeInputCode.SECRET, f"{path}.{key}"))
            findings.extend(_secret_findings(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_secret_findings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        findings.append(RuntimeInputFinding(RuntimeInputCode.SECRET, path))
    return tuple(findings)


def _by_id(items: tuple[dict[str, object], ...], field: str) -> dict[str, dict[str, object]]:
    return {value: item for item in items if isinstance((value := item.get(field)), str)}


def _expected_destinations(service_id: str) -> tuple[str, ...]:
    base = {"otel-collector", "sql-server"}
    scheduler, _ = _TASK_HUBS[service_id]
    if scheduler is not None:
        base.add(scheduler)
    base.update(_VAULTS[service_id])
    if service_id == "control-plane":
        base.add("review-api")
    elif service_id == "acquisition-worker":
        base.add("egress-source")
    elif service_id == "legal-processing-worker":
        base.add("egress-model")
    elif service_id == "promotion-worker":
        base.add("egress-promotion")
    return tuple(sorted(base))


def _validate_topology_binding(
    application: dict[str, object],
    topology_service: dict[str, object] | None,
    label: str,
) -> tuple[RuntimeInputFinding, ...]:
    if topology_service is None:
        return (RuntimeInputFinding(RuntimeInputCode.TOPOLOGY, label),)
    topology_listeners = topology_service.get("listeners")
    listener_ports = (
        sorted(
            item.get("port")
            for item in topology_listeners
            if isinstance(item, dict) and isinstance(item.get("port"), int)
        )
        if isinstance(topology_listeners, list)
        else None
    )
    try:
        credentials = tuple(sorted(_strings(application.get("credential_filenames"))))
        topology_credentials = tuple(sorted(_strings(topology_service.get("credential_names"))))
        networks = tuple(sorted(_strings(application.get("topology_networks"))))
        topology_networks = tuple(sorted(_strings(topology_service.get("networks"))))
    except ValueError:
        return (RuntimeInputFinding(RuntimeInputCode.INVENTORY, f"{label} lists"),)
    findings: list[RuntimeInputFinding] = []
    if credentials != topology_credentials or len(credentials) != len(set(credentials)):
        findings.append(RuntimeInputFinding(RuntimeInputCode.CREDENTIAL, label))
    if (
        application.get("service_identity") != topology_service.get("identity")
        or application.get("outbound_profile") != topology_service.get("outbound_profile")
        or application.get("listener_ports") != listener_ports
        or networks != topology_networks
        or topology_service.get("enabled") is not False
    ):
        findings.append(RuntimeInputFinding(RuntimeInputCode.TOPOLOGY, label))
    return tuple(findings)


def _validate_application(
    application: dict[str, object],
    topology_service: dict[str, object] | None,
    scheduler_hubs: dict[str, frozenset[str]],
) -> tuple[RuntimeInputFinding, ...]:
    findings: list[RuntimeInputFinding] = []
    service_id = application.get("service_id")
    label = service_id if isinstance(service_id, str) else "unknown"
    if frozenset(application) != _APPLICATION_KEYS:
        findings.append(RuntimeInputFinding(RuntimeInputCode.INVENTORY, f"{label} schema"))
    if label not in _APPLICATIONS:
        return (*findings, RuntimeInputFinding(RuntimeInputCode.INVENTORY, label))
    if application.get("database_role") != _DATABASE_ROLES[label]:
        findings.append(RuntimeInputFinding(RuntimeInputCode.DATABASE, label))
    scheduler, hub = _TASK_HUBS[label]
    scheduler_values = (
        (None, None, None, None)
        if scheduler is None
        else (
            f"{scheduler}:8080",
            "PRIVATE_INTERNAL_GRPC_NO_TLS",
            "MEMORY_ONLY",
            "REPLACEMENT_FROM_SAFE_CHECKPOINT",
        )
    )
    if (
        application.get("task_scheduler_service") != scheduler
        or application.get("task_hub") != hub
        or application.get("task_scheduler_host_address") != scheduler_values[0]
        or application.get("task_scheduler_transport") != scheduler_values[1]
        or application.get("task_scheduler_credential_filename") is not None
        or application.get("task_scheduler_persistence") != scheduler_values[2]
        or application.get("task_scheduler_loss_result") != scheduler_values[3]
        or (scheduler is not None and hub not in scheduler_hubs.get(scheduler, frozenset()))
    ):
        findings.append(RuntimeInputFinding(RuntimeInputCode.TASK_HUB, label))
    if tuple(application.get("vault_service_ids", ())) != _VAULTS[label]:
        findings.append(RuntimeInputFinding(RuntimeInputCode.VAULT, label))
    if tuple(application.get("destination_service_ids", ())) != _expected_destinations(label):
        findings.append(RuntimeInputFinding(RuntimeInputCode.DESTINATION, label))
    if (
        application.get("adapter_state") != "REQUIRED"
        or application.get("readiness_probe_state") != "REQUIRED"
    ):
        findings.append(RuntimeInputFinding(RuntimeInputCode.BLOCKER, label))
    if tuple(application.get("readiness_dependency_codes", ())) != (
        _READINESS_DEPENDENCIES[label]
    ):
        findings.append(RuntimeInputFinding(RuntimeInputCode.READINESS, label))
    if application.get("enabled") is not False or application.get("admitted") is not False:
        findings.append(RuntimeInputFinding(RuntimeInputCode.ADMISSION, label))
    findings.extend(_validate_topology_binding(application, topology_service, label))
    return tuple(findings)


def validate_runtime_input_policy(
    policy: dict[str, object], topology: dict[str, object]
) -> tuple[RuntimeInputFinding, ...]:
    """Return every drift; empty proves only a disabled runtime-input contract."""
    findings = list(_secret_findings(policy))
    if frozenset(policy) != _TOP_LEVEL_KEYS:
        findings.append(RuntimeInputFinding(RuntimeInputCode.INVENTORY, "document schema"))
    if (
        policy.get("schema_version") != 1
        or policy.get("status") != "DESIGN_ONLY_DISABLED"
        or policy.get("environment") != "V1_POC"
    ):
        findings.append(RuntimeInputFinding(RuntimeInputCode.INVENTORY, "header"))
    if policy.get("database") != "AskLegalPocOperational":
        findings.append(RuntimeInputFinding(RuntimeInputCode.DATABASE, "database"))
    if policy.get("vault_client_profile") != _VAULT_CLIENT_PROFILE:
        findings.append(RuntimeInputFinding(RuntimeInputCode.VAULT, "client profile"))
    if policy.get("configuration_delivery") != _DELIVERY:
        findings.append(RuntimeInputFinding(RuntimeInputCode.CREDENTIAL, "delivery"))
    if policy.get("authority") != _AUTHORITY:
        findings.append(RuntimeInputFinding(RuntimeInputCode.AUTHORITY, "authority"))
    if tuple(policy.get("required_blockers", ())) != _BLOCKERS:
        findings.append(RuntimeInputFinding(RuntimeInputCode.BLOCKER, "required blockers"))
    applications = _objects(policy.get("applications"))
    application_ids = tuple(item.get("service_id") for item in applications)
    if (
        len(application_ids) != len(set(application_ids))
        or frozenset(application_ids) != _APPLICATIONS
    ):
        findings.append(RuntimeInputFinding(RuntimeInputCode.INVENTORY, "application ids"))
    services = _by_id(_objects(topology.get("services")), "service_id")
    schedulers = {
        service_id: frozenset(_strings(item.get("task_hubs")))
        for item in _objects(topology.get("scheduler_instances"))
        if isinstance((service_id := item.get("service_id")), str)
    }
    for application in applications:
        service_id = application.get("service_id")
        findings.extend(
            _validate_application(
                application,
                services.get(service_id) if isinstance(service_id, str) else None,
                schedulers,
            )
        )
    return tuple(findings)


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(path)
    return value


def check_runtime_input_policy(root: Path) -> RuntimeInputReport:
    """Validate the exact disabled per-application runtime inputs."""
    policy = _read_object(root / RUNTIME_POLICY_PATH)
    findings = validate_runtime_input_policy(policy, _read_object(root / TOPOLOGY_PATH))
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    applications = _objects(policy["applications"])
    return RuntimeInputReport(
        applications=len(applications),
        credentials=sum(len(_strings(item["credential_filenames"])) for item in applications),
        logical_destinations=sum(
            len(_strings(item["destination_service_ids"])) for item in applications
        ),
        blockers=_BLOCKERS,
        admitted=sum(item.get("admitted") is True for item in applications),
    )


def main() -> None:
    """Run the disabled application runtime-input contract gate."""
    root = Path(__file__).resolve().parents[1]
    report = check_runtime_input_policy(root)
    print(  # noqa: T201
        "PASS V1 POC application runtime inputs; NOT_READY: "
        f"{report.applications} applications, {len(report.blockers)} blockers, "
        f"admitted={report.admitted}"
    )


if __name__ == "__main__":
    main()
