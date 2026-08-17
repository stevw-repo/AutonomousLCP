"""Fail-closed validation for disabled V1 POC host identity inputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

IDENTITY_POLICY_PATH = Path("infrastructure/poc/host_identity_inputs.json")
TOPOLOGY_PATH = Path("infrastructure/poc/topology.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_DOCUMENT_TOO_LARGE = "host identity document too large"
_DOCUMENT_ROOT = "host identity document root"
_OBJECT_LIST = "host identity object list"
_STRING_LIST = "host identity string list"
_SECRET_VALUE = re.compile(
    r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)"
)
_DOCUMENT_KEYS = frozenset(
    {
        "authority",
        "identities",
        "identity_profile",
        "required_blockers",
        "schema_version",
        "status",
    }
)
_IDENTITY_KEYS = frozenset(
    {"created", "gid", "identity", "owned_write_paths", "service_id", "uid"}
)
_AUTHORITY = {
    "identity_creation_authorized": False,
    "path_ownership_change_authorized": False,
    "service_enablement_authorized": False,
    "host_mutation_authorized": False,
}
_PROFILE = {
    "account_locked": True,
    "login_shell": "/usr/sbin/nologin",
    "home_directory": "/nonexistent",
    "supplementary_groups": [],
    "shared_identity_forbidden": True,
    "numeric_uid_gid_state": "HOST_ALLOCATION_REQUIRED",
    "created": False,
}
_BLOCKERS = (
    "COLLISION_FREE_UID_GID_ALLOCATION",
    "CONTAINER_UID_GID_MAPPING",
    "PATH_OWNERSHIP_PROOF",
    "UBUNTU_IDENTITY_PROOF",
)
_EXPECTED_SERVICES = frozenset(
    {
        "acquisition-worker",
        "control-plane",
        "grafana",
        "legal-processing-worker",
        "otel-collector",
        "prometheus",
        "promotion-worker",
        "review-api",
        "vault-primary",
        "vault-recovery",
    }
)


class HostIdentityCode(StrEnum):
    """Closed host-identity validation findings."""

    AUTHORITY = "AUTHORITY"
    DUPLICATE = "DUPLICATE"
    INVENTORY = "INVENTORY"
    OWNERSHIP = "OWNERSHIP"
    PROFILE = "PROFILE"
    SECRET = "SECRET"
    STATE = "STATE"
    TOPOLOGY = "TOPOLOGY"


@dataclass(frozen=True, slots=True)
class HostIdentityFinding:
    """One stable fail-closed host-identity finding."""

    code: HostIdentityCode
    detail: str


@dataclass(frozen=True, slots=True)
class HostIdentityReport:
    """One successful but deliberately uncreated host-identity summary."""

    identities: int
    owned_paths: int
    blockers: tuple[str, ...]
    created: int


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


def _secret_findings(value: object, path: str = "$") -> tuple[HostIdentityFinding, ...]:
    findings: list[HostIdentityFinding] = []
    if isinstance(value, dict):
        forbidden = {"api_key", "password", "private_key", "secret", "token"}
        for key, child in value.items():
            if key.lower() in forbidden:
                findings.append(HostIdentityFinding(HostIdentityCode.SECRET, f"{path}.{key}"))
            findings.extend(_secret_findings(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_secret_findings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        findings.append(HostIdentityFinding(HostIdentityCode.SECRET, path))
    return tuple(findings)


def _by_id(items: tuple[dict[str, object], ...], field: str) -> dict[str, dict[str, object]]:
    return {value: item for item in items if isinstance((value := item.get(field)), str)}


def _validate_identity(
    identity: dict[str, object], topology_service: dict[str, object] | None
) -> tuple[HostIdentityFinding, ...]:
    service_id = identity.get("service_id")
    label = service_id if isinstance(service_id, str) else "unknown"
    findings: list[HostIdentityFinding] = []
    if frozenset(identity) != _IDENTITY_KEYS:
        return (HostIdentityFinding(HostIdentityCode.INVENTORY, label),)
    if topology_service is None or identity.get("identity") != topology_service.get("identity"):
        return (HostIdentityFinding(HostIdentityCode.TOPOLOGY, label),)
    try:
        owned_paths = _strings(identity.get("owned_write_paths"))
        topology_paths = _strings(topology_service.get("write_paths"))
    except TypeError:
        return (HostIdentityFinding(HostIdentityCode.OWNERSHIP, label),)
    if owned_paths != topology_paths:
        findings.append(HostIdentityFinding(HostIdentityCode.OWNERSHIP, label))
    if (
        identity.get("uid") is not None
        or identity.get("gid") is not None
        or identity.get("created") is not False
    ):
        findings.append(HostIdentityFinding(HostIdentityCode.STATE, label))
    return tuple(findings)


def validate_host_identity_policy(
    policy: dict[str, object], topology: dict[str, object]
) -> tuple[HostIdentityFinding, ...]:
    """Return every drift; empty proves only one disabled identity contract."""
    findings = list(_secret_findings(policy))
    if (
        frozenset(policy) != _DOCUMENT_KEYS
        or policy.get("schema_version") != 1
        or policy.get("status") != "DESIGN_ONLY_DISABLED"
    ):
        findings.append(HostIdentityFinding(HostIdentityCode.INVENTORY, "document"))
    if policy.get("authority") != _AUTHORITY:
        findings.append(HostIdentityFinding(HostIdentityCode.AUTHORITY, "authority"))
    if policy.get("identity_profile") != _PROFILE:
        findings.append(HostIdentityFinding(HostIdentityCode.PROFILE, "profile"))
    if tuple(policy.get("required_blockers", ())) != _BLOCKERS:
        findings.append(HostIdentityFinding(HostIdentityCode.STATE, "blockers"))
    identities = _objects(policy.get("identities"))
    service_ids = tuple(item.get("service_id") for item in identities)
    names = tuple(item.get("identity") for item in identities)
    if (
        len(service_ids) != len(set(service_ids))
        or frozenset(service_ids) != _EXPECTED_SERVICES
    ):
        findings.append(HostIdentityFinding(HostIdentityCode.INVENTORY, "services"))
    if len(names) != len(set(names)) or any(name in {"mssql", "root"} for name in names):
        findings.append(HostIdentityFinding(HostIdentityCode.DUPLICATE, "identity"))
    topology_services = _by_id(_objects(topology.get("services")), "service_id")
    for identity in identities:
        service_id = identity.get("service_id")
        findings.extend(
            _validate_identity(
                identity,
                topology_services.get(service_id) if isinstance(service_id, str) else None,
            )
        )
    return tuple(findings)


def check_host_identity_policy(root: Path) -> HostIdentityReport:
    """Validate exact disabled host identities without inspecting or changing a host."""
    policy = _read_object(root / IDENTITY_POLICY_PATH)
    findings = validate_host_identity_policy(policy, _read_object(root / TOPOLOGY_PATH))
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    identities = _objects(policy["identities"])
    return HostIdentityReport(
        identities=len(identities),
        owned_paths=sum(len(_strings(item["owned_write_paths"])) for item in identities),
        blockers=_BLOCKERS,
        created=sum(item.get("created") is True for item in identities),
    )


def main() -> None:
    """Run the disabled host-identity input contract gate."""
    root = Path(__file__).resolve().parents[1]
    report = check_host_identity_policy(root)
    print(  # noqa: T201
        "PASS V1 POC host identity inputs; NOT_READY: "
        f"{report.identities} identities, {report.owned_paths} owned paths, "
        f"{len(report.blockers)} blockers, created={report.created}"
    )


if __name__ == "__main__":
    main()
