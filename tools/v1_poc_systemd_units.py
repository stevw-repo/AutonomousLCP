"""Fail-closed validation for disabled V1 POC systemd unit inputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

SYSTEMD_POLICY_PATH = Path("infrastructure/poc/systemd_unit_inputs.json")
TOPOLOGY_PATH = Path("infrastructure/poc/topology.json")
HOST_POLICY_PATH = Path("infrastructure/poc/host_admission_policy.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_DOCUMENT_TOO_LARGE = "systemd input document too large"
_DOCUMENT_ROOT = "systemd input document root"
_OBJECT_LIST = "systemd object list"
_STRING_LIST = "systemd string list"
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_DOCUMENT_KEYS = frozenset(
    {
        "authority",
        "bootstrap_units",
        "container_networks",
        "credential_transport",
        "hardening_profile",
        "required_blockers",
        "schema_version",
        "service_units",
        "status",
        "timer_units",
    }
)
_SERVICE_KEYS = frozenset(
    {
        "after_targets",
        "credential_names",
        "enabled",
        "read_write_paths",
        "requires",
        "runtime_command_state",
        "runtime_identity",
        "service_id",
        "unit_name",
    }
)
_AUTHORITY = {
    "credential_creation_authorized": False,
    "image_pull_authorized": False,
    "unit_installation_authorized": False,
    "service_enablement_authorized": False,
    "host_mutation_authorized": False,
}
_CREDENTIAL_TRANSPORT = {
    "systemd_directive": "LoadCredentialEncrypted",
    "runtime_directory_variable": "CREDENTIALS_DIRECTORY",
    "container_bridge_state": "ENVIRONMENT_FROM_LOADED_CREDENTIAL",
    "secret_environment_forbidden": False,
    "secret_arguments_forbidden": True,
    "persistent_plaintext_forbidden": True,
}
_HARDENING = {
    "manager_user": "root",
    "restart": "on-failure",
    "no_new_privileges": True,
    "protect_system": "strict",
    "private_tmp": True,
    "capability_bounding_set": [],
    "runtime_command_state": "REQUIRED",
    "enabled": False,
}
_BLOCKERS = (
    "ARTIFACT_PINS",
    "UBUNTU_SYSTEMD_PROOF",
)
_NETWORK_KEYS = frozenset({"created", "created_by_unit", "internal", "network_id", "subnet"})
_NETWORK_UNIT_NAME = "asklegal-networks.service"
_UNIT_NAMES = {
    "acquisition-worker": "asklegal-acquisition-worker.service",
    "control-plane": "asklegal-control-plane.service",
    "dts-general": "asklegal-dts-general.service",
    "dts-promotion": "asklegal-dts-promotion.service",
    "egress-model": "asklegal-egress-model.service",
    "egress-promotion": "asklegal-egress-promotion.service",
    "egress-source": "asklegal-egress-source.service",
    "grafana": "asklegal-grafana.service",
    "legal-processing-worker": "asklegal-legal-processing-worker.service",
    "otel-collector": "asklegal-otel-collector.service",
    "prometheus": "asklegal-prometheus.service",
    "promotion-worker": "asklegal-promotion-worker.service",
    "review-api": "asklegal-review-api.service",
    "sql-server": "asklegal-sql-server.service",
    "vault-primary": "asklegal-vault-primary.service",
    "vault-recovery": "asklegal-vault-recovery.service",
}
_REQUIRES = {
    "acquisition-worker": (
        "asklegal-dts-general.service",
        "asklegal-egress-source.service",
        "asklegal-otel-collector.service",
        "asklegal-register-migrate.service",
        "asklegal-vault-bootstrap.service",
    ),
    "control-plane": (
        "asklegal-dts-general.service",
        "asklegal-otel-collector.service",
        "asklegal-register-migrate.service",
        "asklegal-vault-bootstrap.service",
    ),
    "dts-general": ("asklegal-register-migrate.service",),
    "dts-promotion": ("asklegal-register-migrate.service",),
    "egress-model": (),
    "egress-promotion": (),
    "egress-source": (),
    "grafana": ("asklegal-prometheus.service",),
    "legal-processing-worker": (
        "asklegal-dts-general.service",
        "asklegal-egress-model.service",
        "asklegal-otel-collector.service",
        "asklegal-register-migrate.service",
        "asklegal-vault-bootstrap.service",
    ),
    "otel-collector": (),
    "prometheus": ("asklegal-otel-collector.service",),
    "promotion-worker": (
        "asklegal-dts-promotion.service",
        "asklegal-egress-promotion.service",
        "asklegal-otel-collector.service",
        "asklegal-register-migrate.service",
        "asklegal-vault-bootstrap.service",
    ),
    "review-api": (
        "asklegal-otel-collector.service",
        "asklegal-register-migrate.service",
        "asklegal-vault-bootstrap.service",
    ),
    "sql-server": (),
    "vault-primary": (),
    "vault-recovery": (),
}
_FILESYSTEM_SERVICES = frozenset({"sql-server", "vault-primary", "vault-recovery"})
_BOOTSTRAP_UNITS = (
    {
        "unit_name": _NETWORK_UNIT_NAME,
        "kind": "ONESHOT",
        "requires": [],
        "credential_names": [],
        "disable_after_verified_success": False,
        "runtime_command_state": "REQUIRED",
        "enabled": False,
    },
    {
        "unit_name": "asklegal-register-migrate.service",
        "kind": "ONESHOT",
        "requires": ["asklegal-sql-server.service"],
        "credential_names": ["sql-bootstrap-password"],
        "disable_after_verified_success": True,
        "runtime_command_state": "REQUIRED",
        "enabled": False,
    },
    {
        "unit_name": "asklegal-vault-bootstrap.service",
        "kind": "ONESHOT",
        "requires": [
            "asklegal-vault-primary.service",
            "asklegal-vault-recovery.service",
        ],
        "credential_names": [
            "vault-primary-root-access",
            "vault-primary-root-secret",
            "vault-recovery-root-access",
            "vault-recovery-root-secret",
        ],
        "disable_after_verified_success": True,
        "runtime_command_state": "REQUIRED",
        "enabled": False,
    },
)
_TIMER_UNITS = (
    {
        "timer_id": "audit-archive",
        "unit_name": "asklegal-audit-archive.timer",
        "cadence_state": "ADMISSION_VALUE_REQUIRED",
        "enabled": False,
    },
    {
        "timer_id": "full-reconciliation",
        "unit_name": "asklegal-full-reconciliation.timer",
        "cadence_state": "ADMISSION_VALUE_REQUIRED",
        "enabled": False,
    },
    {
        "timer_id": "ordinary-observation",
        "unit_name": "asklegal-ordinary-observation.timer",
        "cadence_state": "PACKAGE_VALUE_REQUIRED",
        "enabled": False,
    },
    {
        "timer_id": "recovery-verification",
        "unit_name": "asklegal-recovery-verification.timer",
        "cadence_state": "ADMISSION_VALUE_REQUIRED",
        "enabled": False,
    },
    {
        "timer_id": "telemetry-retention",
        "unit_name": "asklegal-telemetry-retention.timer",
        "cadence_state": "ADMISSION_VALUE_REQUIRED",
        "enabled": False,
    },
)


class SystemdInputCode(StrEnum):
    """Closed systemd-input validation findings."""

    AUTHORITY = "AUTHORITY"
    BOOTSTRAP = "BOOTSTRAP"
    NETWORK = "NETWORK"
    CREDENTIAL = "CREDENTIAL"
    DEPENDENCY = "DEPENDENCY"
    HARDENING = "HARDENING"
    INVENTORY = "INVENTORY"
    RUNTIME = "RUNTIME"
    SECRET = "SECRET"
    TIMER = "TIMER"
    TOPOLOGY = "TOPOLOGY"


@dataclass(frozen=True, slots=True)
class SystemdInputFinding:
    """One stable fail-closed systemd-input finding."""

    code: SystemdInputCode
    detail: str


@dataclass(frozen=True, slots=True)
class SystemdInputReport:
    """One successful but deliberately disabled systemd-input summary."""

    services: int
    bootstrap_units: int
    networks: int
    timers: int
    blockers: tuple[str, ...]
    enabled: int


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


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(type(item) is str and item for item in value):
        raise TypeError(_STRING_LIST)
    return tuple(item for item in value if isinstance(item, str))


def _secret_findings(value: object, path: str = "$") -> tuple[SystemdInputFinding, ...]:
    findings: list[SystemdInputFinding] = []
    if isinstance(value, dict):
        forbidden = {"api_key", "password", "private_key", "secret", "token"}
        for key, child in value.items():
            if key.lower() in forbidden:
                findings.append(SystemdInputFinding(SystemdInputCode.SECRET, f"{path}.{key}"))
            findings.extend(_secret_findings(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_secret_findings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        findings.append(SystemdInputFinding(SystemdInputCode.SECRET, path))
    return tuple(findings)


def _by_id(items: tuple[dict[str, object], ...], field: str) -> dict[str, dict[str, object]]:
    return {value: item for item in items if isinstance((value := item.get(field)), str)}


def _validate_service_unit(
    unit: dict[str, object], topology_service: dict[str, object] | None
) -> tuple[SystemdInputFinding, ...]:
    service_id = unit.get("service_id")
    label = service_id if isinstance(service_id, str) else "unknown"
    findings: list[SystemdInputFinding] = []
    if frozenset(unit) != _SERVICE_KEYS or label not in _UNIT_NAMES:
        findings.append(SystemdInputFinding(SystemdInputCode.INVENTORY, label))
        return tuple(findings)
    if topology_service is None:
        return (SystemdInputFinding(SystemdInputCode.TOPOLOGY, label),)
    try:
        credentials = tuple(sorted(_strings(unit.get("credential_names"))))
        topology_credentials = tuple(sorted(_strings(topology_service.get("credential_names"))))
        write_paths = _strings(unit.get("read_write_paths"))
        topology_write_paths = _strings(topology_service.get("write_paths"))
        requires = _strings(unit.get("requires"))
        after_targets = _strings(unit.get("after_targets"))
    except TypeError:
        return (SystemdInputFinding(SystemdInputCode.INVENTORY, label),)
    if (
        unit.get("unit_name") != _UNIT_NAMES[label]
        or unit.get("runtime_identity") != topology_service.get("identity")
        or credentials != topology_credentials
        or write_paths != topology_write_paths
    ):
        findings.append(SystemdInputFinding(SystemdInputCode.TOPOLOGY, label))
    expected_targets = ("asklegal-filesystems.target",) if label in _FILESYSTEM_SERVICES else ()
    if requires != _REQUIRES[label] or after_targets != expected_targets:
        findings.append(SystemdInputFinding(SystemdInputCode.DEPENDENCY, label))
    if unit.get("runtime_command_state") != "REQUIRED" or unit.get("enabled") is not False:
        findings.append(SystemdInputFinding(SystemdInputCode.RUNTIME, label))
    return tuple(findings)


def _validate_container_networks(
    value: object, host_policy: dict[str, object], topology: dict[str, object]
) -> tuple[SystemdInputFinding, ...]:
    """Require the unit graph to create exactly the subnets host admission allocated."""
    runtime = host_policy.get("runtime")
    allocation = runtime.get("selected_private_subnets") if isinstance(runtime, dict) else None
    if not isinstance(allocation, dict):
        return (SystemdInputFinding(SystemdInputCode.NETWORK, "host allocation"),)
    try:
        networks = _objects(value)
    except TypeError:
        return (SystemdInputFinding(SystemdInputCode.NETWORK, "inventory"),)
    declared_topology = _objects(topology.get("networks"))
    isolation = {
        network_id: item.get("internal")
        for item in declared_topology
        if isinstance((network_id := item.get("network_id")), str)
    }
    network_ids = tuple(item.get("network_id") for item in networks)
    if len(network_ids) != len(set(network_ids)) or frozenset(network_ids) != frozenset(allocation):
        return (SystemdInputFinding(SystemdInputCode.NETWORK, "coverage"),)
    findings: list[SystemdInputFinding] = []
    for network in networks:
        network_id = network.get("network_id")
        label = network_id if isinstance(network_id, str) else "unknown"
        if (
            frozenset(network) != _NETWORK_KEYS
            or network.get("subnet") != allocation.get(network_id)
            or network.get("internal") is not isolation.get(network_id)
            or network.get("created_by_unit") != _NETWORK_UNIT_NAME
            or network.get("created") is not False
        ):
            findings.append(SystemdInputFinding(SystemdInputCode.NETWORK, label))
    return tuple(findings)


def validate_systemd_input_policy(
    policy: dict[str, object], topology: dict[str, object], host_policy: dict[str, object]
) -> tuple[SystemdInputFinding, ...]:
    """Return every drift; empty proves only one disabled unit-input contract."""
    findings = list(_secret_findings(policy))
    if (
        frozenset(policy) != _DOCUMENT_KEYS
        or policy.get("schema_version") != 1
        or policy.get("status") != "DESIGN_ONLY_DISABLED"
    ):
        findings.append(SystemdInputFinding(SystemdInputCode.INVENTORY, "document"))
    if policy.get("authority") != _AUTHORITY:
        findings.append(SystemdInputFinding(SystemdInputCode.AUTHORITY, "authority"))
    if policy.get("credential_transport") != _CREDENTIAL_TRANSPORT:
        findings.append(SystemdInputFinding(SystemdInputCode.CREDENTIAL, "transport"))
    if policy.get("hardening_profile") != _HARDENING:
        findings.append(SystemdInputFinding(SystemdInputCode.HARDENING, "profile"))
    if tuple(policy.get("required_blockers", ())) != _BLOCKERS:
        findings.append(SystemdInputFinding(SystemdInputCode.RUNTIME, "blockers"))
    services = _objects(policy.get("service_units"))
    service_ids = tuple(item.get("service_id") for item in services)
    if len(service_ids) != len(set(service_ids)) or frozenset(service_ids) != frozenset(
        _UNIT_NAMES
    ):
        findings.append(SystemdInputFinding(SystemdInputCode.INVENTORY, "services"))
    topology_services = _by_id(_objects(topology.get("services")), "service_id")
    for service in services:
        service_id = service.get("service_id")
        findings.extend(
            _validate_service_unit(
                service,
                topology_services.get(service_id) if isinstance(service_id, str) else None,
            )
        )
    findings.extend(
        _validate_container_networks(policy.get("container_networks"), host_policy, topology)
    )
    if _objects(policy.get("bootstrap_units")) != _BOOTSTRAP_UNITS:
        findings.append(SystemdInputFinding(SystemdInputCode.BOOTSTRAP, "units"))
    if _objects(policy.get("timer_units")) != _TIMER_UNITS:
        findings.append(SystemdInputFinding(SystemdInputCode.TIMER, "units"))
    return tuple(findings)


def check_systemd_input_policy(root: Path) -> SystemdInputReport:
    """Validate exact disabled unit inputs without reading or changing systemd."""
    policy = _read_object(root / SYSTEMD_POLICY_PATH)
    findings = validate_systemd_input_policy(
        policy,
        _read_object(root / TOPOLOGY_PATH),
        _read_object(root / HOST_POLICY_PATH),
    )
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    service_units = _objects(policy["service_units"])
    bootstrap_units = _objects(policy["bootstrap_units"])
    timer_units = _objects(policy["timer_units"])
    return SystemdInputReport(
        services=len(service_units),
        bootstrap_units=len(bootstrap_units),
        networks=len(_objects(policy["container_networks"])),
        timers=len(timer_units),
        blockers=_BLOCKERS,
        enabled=sum(item.get("enabled") is True for item in (*service_units, *timer_units)),
    )


def main() -> None:
    """Run the disabled systemd unit-input contract gate."""
    root = Path(__file__).resolve().parents[1]
    report = check_systemd_input_policy(root)
    print(  # noqa: T201
        "PASS V1 POC systemd unit inputs; NOT_READY: "
        f"{report.services} services, {report.bootstrap_units} bootstrap units, "
        f"{report.networks} networks, "
        f"{report.timers} timers, {len(report.blockers)} blockers, "
        f"enabled={report.enabled}"
    )


if __name__ == "__main__":
    main()
