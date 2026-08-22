"""Fail-closed validation for disabled V1 POC host identity inputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

IDENTITY_POLICY_PATH = Path("infrastructure/poc/host_identity_inputs.json")
TOPOLOGY_PATH = Path("infrastructure/poc/topology.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_DOCUMENT_TOO_LARGE = "host identity document too large"
_DOCUMENT_ROOT = "host identity document root"
_OBJECT_LIST = "host identity object list"
_STRING_LIST = "host identity string list"
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_DOCUMENT_KEYS = frozenset(
    {
        "authority",
        "container_identity_map",
        "container_identity_rule",
        "identities",
        "identity_profile",
        "required_blockers",
        "schema_version",
        "status",
    }
)
_MAP_KEYS = frozenset({"runtime_gid", "runtime_uid", "service_id", "source"})
_ALLOCATED_UID_MIN = 3000
_ALLOCATED_UID_MAX = 3014
_IMAGE_DEFINED_SQL_UID = 10001
_MAP_SOURCES = frozenset({"CONTAINER_ONLY_RESERVED", "IMAGE_DEFINED", "LOCALLY_ALLOCATED"})
_CONTAINER_ONLY_SERVICES = frozenset(
    {"dts-general", "dts-promotion", "egress-model", "egress-promotion", "egress-source"}
)
_IMAGE_DEFINED_SERVICES = frozenset({"sql-server"})
_CONTAINER_IDENTITY_RULE = {
    "credential_file_owner_must_equal_runtime_uid": True,
    "root_runtime_uid_forbidden": True,
    "shared_runtime_uid_forbidden": True,
    "measured_reason": (
        "LoadCredential writes a 0400 file owned by the unit account, so a container "
        "running under a different numeric UID cannot read its own credential."
    ),
}
_IDENTITY_KEYS = frozenset({"created", "gid", "identity", "owned_write_paths", "service_id", "uid"})
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
    "numeric_uid_gid_state": "ALLOCATED",
    "allocated_uid_gid_range": [_ALLOCATED_UID_MIN, _ALLOCATED_UID_MAX],
    "created": False,
}
_BLOCKERS = (
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
    container_identities: int
    blockers: tuple[str, ...]
    created: int


def _read_object(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise ValueError(_DOCUMENT_TOO_LARGE)
    value: object = json.loads(raw)
    document = _string_object(value)
    if document is None:
        raise TypeError(_DOCUMENT_ROOT)
    return document


def _objects(value: object) -> tuple[dict[str, object], ...]:
    items = _object_list(value)
    if items is None:
        raise TypeError(_OBJECT_LIST)
    result: list[dict[str, object]] = []
    for item in items:
        document = _string_object(item)
        if document is None:
            raise TypeError(_OBJECT_LIST)
        result.append(document)
    return tuple(result)


def _strings(value: object) -> tuple[str, ...]:
    items = _object_list(value)
    if items is None:
        raise TypeError(_STRING_LIST)
    result: list[str] = []
    for item in items:
        if type(item) is not str or not item:
            raise TypeError(_STRING_LIST)
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


def _strings_or_empty(value: object) -> tuple[str, ...]:
    try:
        return _strings(value)
    except TypeError:
        return ()


def _secret_findings(value: object, path: str = "$") -> tuple[HostIdentityFinding, ...]:
    findings: list[HostIdentityFinding] = []
    document = _string_object(value)
    items = _object_list(value)
    if document is not None:
        forbidden = {"api_key", "password", "private_key", "secret", "token"}
        for key, child in document.items():
            if key.lower() in forbidden:
                findings.append(HostIdentityFinding(HostIdentityCode.SECRET, f"{path}.{key}"))
            findings.extend(_secret_findings(child, f"{path}.{key}"))
    elif items is not None:
        for index, child in enumerate(items):
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
    uid = identity.get("uid")
    gid = identity.get("gid")
    if (
        type(uid) is not int
        or type(gid) is not int
        or uid != gid
        or not _ALLOCATED_UID_MIN <= uid <= _ALLOCATED_UID_MAX
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
    if _strings_or_empty(policy.get("required_blockers")) != _BLOCKERS:
        findings.append(HostIdentityFinding(HostIdentityCode.STATE, "blockers"))
    identities = _objects(policy.get("identities"))
    service_ids = tuple(
        service_id for item in identities if isinstance((service_id := item.get("service_id")), str)
    )
    names = tuple(name for item in identities if isinstance((name := item.get("identity")), str))
    if (
        len(service_ids) != len(identities)
        or len(service_ids) != len(set(service_ids))
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
    findings.extend(
        _validate_container_identity_map(
            policy.get("container_identity_map"),
            policy.get("container_identity_rule"),
            identities,
            frozenset(topology_services),
        )
    )
    return tuple(findings)


def _validate_container_identity_map(
    value: object,
    rule: object,
    identities: tuple[dict[str, object], ...],
    topology_service_ids: frozenset[str],
) -> tuple[HostIdentityFinding, ...]:
    """Bind every container to one exact non-root numeric identity it alone runs as."""
    if rule != _CONTAINER_IDENTITY_RULE:
        return (HostIdentityFinding(HostIdentityCode.PROFILE, "container identity rule"),)
    try:
        entries = _objects(value)
    except TypeError:
        return (HostIdentityFinding(HostIdentityCode.INVENTORY, "container identity map"),)
    service_ids = tuple(
        service_id for entry in entries if isinstance((service_id := entry.get("service_id")), str)
    )
    if (
        len(service_ids) != len(entries)
        or len(service_ids) != len(set(service_ids))
        or frozenset(service_ids) != topology_service_ids
    ):
        return (HostIdentityFinding(HostIdentityCode.INVENTORY, "container identity coverage"),)
    host_uid: dict[str, object] = {
        service_id: entry.get("uid")
        for entry in identities
        if isinstance((service_id := entry.get("service_id")), str)
    }
    findings: list[HostIdentityFinding] = []
    seen: set[int] = set()
    for entry in entries:
        service_id = entry.get("service_id")
        label = service_id if isinstance(service_id, str) else "unknown"
        uid = entry.get("runtime_uid")
        if (
            frozenset(entry) != _MAP_KEYS
            or type(uid) is not int
            or entry.get("runtime_gid") != uid
            or uid <= 0
            or entry.get("source") not in _MAP_SOURCES
        ):
            findings.append(HostIdentityFinding(HostIdentityCode.INVENTORY, label))
            continue
        if uid in seen:
            findings.append(HostIdentityFinding(HostIdentityCode.DUPLICATE, label))
        seen.add(uid)
        findings.extend(_validate_map_source(entry, uid, label, host_uid))
    return tuple(findings)


def _validate_map_source(
    entry: dict[str, object], uid: int, label: str, host_uid: dict[str, object]
) -> tuple[HostIdentityFinding, ...]:
    """Require each runtime identity to match the source that actually defines it."""
    source = entry.get("source")
    if source == "IMAGE_DEFINED":
        expected = label in _IMAGE_DEFINED_SERVICES and uid == _IMAGE_DEFINED_SQL_UID
    elif source == "CONTAINER_ONLY_RESERVED":
        expected = (
            label in _CONTAINER_ONLY_SERVICES
            and _ALLOCATED_UID_MIN <= uid <= _ALLOCATED_UID_MAX
            and label not in host_uid
        )
    else:
        expected = host_uid.get(label) == uid
    return () if expected else (HostIdentityFinding(HostIdentityCode.STATE, label),)


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
        container_identities=len(_objects(policy["container_identity_map"])),
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
        f"{report.container_identities} container identities, "
        f"{len(report.blockers)} blockers, created={report.created}"
    )


if __name__ == "__main__":
    main()
