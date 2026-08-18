"""Read-only, fail-closed V1 POC Ubuntu host-admission contract."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

POLICY_PATH = Path("infrastructure/poc/host_admission_policy.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_MIN_MEMORY_BYTES = 64_424_509_440
_MIN_DISK_BYTES = 3_900_000_000_000
_PHYSICAL_DISK_COUNT = 3
_PERMITTED_DOCKER_GROUP_MEMBERS = ("docpro",)
_RUNTIME_KEYS = frozenset({"name", "service_manager", "docker_group_non_root_members"})
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_POLICY_KEYS = frozenset(
    {
        "admission_blockers",
        "authority",
        "host",
        "runtime",
        "schema_version",
        "security",
        "status",
        "storage",
    }
)
_FACT_KEYS = frozenset(
    {
        "architecture",
        "container_runtime",
        "credentials",
        "firewall",
        "host_packages",
        "journal",
        "memory_bytes",
        "os",
        "paths",
        "physical_disks",
        "private_subnets",
        "schema_version",
        "source",
        "time",
    }
)
_DISK_KEYS = frozenset({"size_bytes", "stable_id"})
_PATH_KEYS = frozenset({"fs_type", "path", "physical_disk_id", "real_path", "symlink", "writable"})
_EXPECTED_BLOCKERS = (
    "CREDENTIAL_INTERFACE_PROOF",
    "HOST_PACKAGE_LOCKS",
    "PRIVATE_SUBNET_SELECTION",
)
_REQUIRED_PATHS = (
    "/srv/asklegal/sql",
    "/srv/asklegal/vault-primary",
    "/srv/asklegal/vault-recovery",
)


class HostCode(StrEnum):
    """Stable host-fact failure codes."""

    ARCHITECTURE = "ARCHITECTURE"
    AUTHORITY = "AUTHORITY"
    CONTAINER = "CONTAINER"
    CREDENTIAL = "CREDENTIAL"
    FIREWALL = "FIREWALL"
    INVENTORY = "INVENTORY"
    JOURNAL = "JOURNAL"
    MEMORY = "MEMORY"
    OPERATING_SYSTEM = "OPERATING_SYSTEM"
    PATH = "PATH"
    POLICY = "POLICY"
    SECRET = "SECRET"
    STORAGE = "STORAGE"
    TIME = "TIME"


@dataclass(frozen=True, slots=True)
class HostFinding:
    """One exact host-fact mismatch."""

    code: HostCode
    detail: str


@dataclass(frozen=True, slots=True)
class HostPolicyReport:
    """One valid but deliberately blocked policy summary."""

    required_paths: int
    blockers: tuple[str, ...]
    host_mutation_authorized: bool


@dataclass(frozen=True, slots=True)
class HostAdmissionEvaluation:
    """Result of comparing read-only host facts with the checked-in policy."""

    facts_conform: bool
    admitted: bool
    findings: tuple[HostFinding, ...]
    blockers: tuple[str, ...]


def _mapping(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def _mappings(value: object) -> tuple[dict[str, object], ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        return None
    return tuple(item for item in value if isinstance(item, dict))


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(type(item) is str and item for item in value):
        return None
    return tuple(item for item in value if isinstance(item, str))


def _has_secret(value: object) -> bool:
    if isinstance(value, dict):
        forbidden = {"api_key", "password", "private_key", "secret", "token"}
        return any(key.lower() in forbidden or _has_secret(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_has_secret(child) for child in value)
    return isinstance(value, str) and _SECRET_VALUE.search(value) is not None


def _read_object(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        message = "host admission document too large"
        raise ValueError(message)
    value = json.loads(raw)
    if not isinstance(value, dict):
        message = "host admission document root"
        raise TypeError(message)
    return value


def validate_policy(policy: dict[str, object]) -> tuple[HostFinding, ...]:
    """Validate the exact disabled policy without inspecting or changing a host."""
    findings: list[HostFinding] = []
    if frozenset(policy) != _POLICY_KEYS or policy.get("schema_version") != 1:
        findings.append(HostFinding(HostCode.POLICY, "schema"))
    if policy.get("status") != "DESIGN_ONLY_DISABLED":
        findings.append(HostFinding(HostCode.POLICY, "status"))
    if _has_secret(policy):
        findings.append(HostFinding(HostCode.SECRET, "policy"))
    host = _mapping(policy.get("host"))
    if host != {
        "os_id": "ubuntu",
        "os_version_id": "24.04",
        "architecture": "x86_64",
        "minimum_memory_bytes": _MIN_MEMORY_BYTES,
    }:
        findings.append(HostFinding(HostCode.POLICY, "host"))
    storage = _mapping(policy.get("storage"))
    if storage != {
        "physical_disk_count": _PHYSICAL_DISK_COUNT,
        "minimum_disk_bytes": _MIN_DISK_BYTES,
        "filesystem_type": "ext4",
        "required_paths": list(_REQUIRED_PATHS),
        "same_physical_disk_required": True,
        "distinct_real_paths_required": True,
        "symlinks_forbidden": True,
        "recovery_class": "LOGICALLY_SEPARATE_POC_RECOVERY",
    }:
        findings.append(HostFinding(HostCode.POLICY, "storage"))
    security = _mapping(policy.get("security"))
    if security != {
        "credential_delivery": "SYSTEMD_CREDS_LOAD_CREDENTIAL_ENCRYPTED",
        "allowed_credential_protection_modes": ["TPM2_PLUS_HOST_KEY", "HOST_KEY_ONLY"],
        "encrypted_credential_blob_mode": "0400",
        "persistent_plaintext_credentials_forbidden": True,
        "permitted_docker_group_members": list(_PERMITTED_DOCKER_GROUP_MEMBERS),
        "nftables_input_default": "DROP",
        "nftables_forward_default": "DROP",
        "direct_container_egress_default": "DROP",
        "public_tcp_ports": [],
        "persistent_journal_required": True,
        "forward_secure_sealing_required": True,
        "time_synchronization_required": True,
    }:
        findings.append(HostFinding(HostCode.POLICY, "security"))
    runtime = _mapping(policy.get("runtime"))
    if runtime != {
        "service_manager": "systemd",
        "container_runtime": "docker",
        "exact_host_package_locks_required": True,
        "host_package_locks": {},
        "collision_free_private_subnets_required": True,
        "selected_private_subnets": {},
    }:
        findings.append(HostFinding(HostCode.POLICY, "runtime"))
    authority = _mapping(policy.get("authority"))
    if authority != {
        "host_mutation_authorized": False,
        "credential_creation_authorized": False,
        "external_write_authorized": False,
    }:
        findings.append(HostFinding(HostCode.AUTHORITY, "policy"))
    if tuple(policy.get("admission_blockers", ())) != _EXPECTED_BLOCKERS:
        findings.append(HostFinding(HostCode.POLICY, "blockers"))
    return tuple(findings)


def check_policy(root: Path) -> HostPolicyReport:
    """Load and validate the repository policy."""
    policy = _read_object(root / POLICY_PATH)
    findings = validate_policy(policy)
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    return HostPolicyReport(
        required_paths=len(_REQUIRED_PATHS),
        blockers=_EXPECTED_BLOCKERS,
        host_mutation_authorized=False,
    )


def _disk_inventory(facts: dict[str, object]) -> dict[str, int] | HostFinding:
    """Return the exact declared disk sizes by identity, or the first failure."""
    disks = _mappings(facts.get("physical_disks"))
    if disks is None or len(disks) != _PHYSICAL_DISK_COUNT:
        return HostFinding(HostCode.STORAGE, "physical disk count")
    by_disk: dict[str, int] = {}
    for disk in disks:
        stable_id = disk.get("stable_id")
        size_bytes = disk.get("size_bytes")
        if (
            frozenset(disk) != _DISK_KEYS
            or type(stable_id) is not str
            or type(size_bytes) is not int
        ):
            return HostFinding(HostCode.STORAGE, "physical disk")
        by_disk[stable_id] = size_bytes
    if len(by_disk) != len(disks):
        return HostFinding(HostCode.STORAGE, "duplicate disk identity")
    return by_disk


def _backing_disk_findings(
    by_disk: dict[str, int], by_path: dict[object, dict[str, object]]
) -> tuple[HostFinding, ...]:
    """Require one shared backing disk of at least the accepted minimum size."""
    backing = {by_path[required_path].get("physical_disk_id") for required_path in _REQUIRED_PATHS}
    if len(backing) != 1:
        return (HostFinding(HostCode.STORAGE, "same physical disk"),)
    backing_id = next(iter(backing))
    backing_bytes = by_disk.get(backing_id) if type(backing_id) is str else None
    if backing_bytes is None:
        return (HostFinding(HostCode.STORAGE, "unknown backing disk"),)
    if backing_bytes < _MIN_DISK_BYTES:
        return (HostFinding(HostCode.STORAGE, "physical disk"),)
    return ()


def _validate_storage(facts: dict[str, object]) -> tuple[HostFinding, ...]:
    findings: list[HostFinding] = []
    inventory = _disk_inventory(facts)
    if isinstance(inventory, HostFinding):
        return (inventory,)
    by_disk = inventory
    paths = _mappings(facts.get("paths"))
    if paths is None:
        return (*findings, HostFinding(HostCode.PATH, "path facts"))
    by_path = {item.get("path"): item for item in paths if type(item.get("path")) is str}
    if set(by_path) != set(_REQUIRED_PATHS):
        findings.append(HostFinding(HostCode.PATH, "path inventory"))
        return tuple(findings)
    findings.extend(_backing_disk_findings(by_disk, by_path))
    real_paths: list[str] = []
    for required_path in _REQUIRED_PATHS:
        item = by_path[required_path]
        real_path = item.get("real_path")
        if type(real_path) is str:
            real_paths.append(real_path)
        if (
            frozenset(item) != _PATH_KEYS
            or item.get("fs_type") != "ext4"
            or item.get("symlink") is not False
            or item.get("writable") is not True
            or real_path != required_path
        ):
            findings.append(HostFinding(HostCode.PATH, required_path))
    if len(real_paths) != len(set(real_paths)):
        findings.append(HostFinding(HostCode.PATH, "distinct real paths"))
    return tuple(findings)


def _validate_security_facts(facts: dict[str, object]) -> tuple[HostFinding, ...]:
    findings: list[HostFinding] = []
    if _mapping(facts.get("time")) != {"synchronized": True}:
        findings.append(HostFinding(HostCode.TIME, "synchronization"))
    credentials = _mapping(facts.get("credentials"))
    if (
        credentials is None
        or credentials.get("systemd_creds_available") is not True
        or credentials.get("protection_mode") not in {"TPM2_PLUS_HOST_KEY", "HOST_KEY_ONLY"}
        or credentials.get("encrypted_blob_mode") != "0400"
        or credentials.get("persistent_plaintext_credential_paths") != []
    ):
        findings.append(HostFinding(HostCode.CREDENTIAL, "credential storage"))
    if _mapping(facts.get("firewall")) != {
        "nftables_available": True,
        "input_default": "DROP",
        "forward_default": "DROP",
        "direct_container_egress_default": "DROP",
        "public_tcp_ports": [],
    }:
        findings.append(HostFinding(HostCode.FIREWALL, "default deny"))
    if _mapping(facts.get("journal")) != {
        "storage": "PERSISTENT",
        "forward_secure_sealing": True,
    }:
        findings.append(HostFinding(HostCode.JOURNAL, "persistent sealed journal"))
    runtime = _mapping(facts.get("container_runtime"))
    if (
        runtime is None
        or frozenset(runtime) != _RUNTIME_KEYS
        or runtime.get("name") != "docker"
        or runtime.get("service_manager") != "systemd"
        or runtime.get("docker_group_non_root_members")
        != list(_PERMITTED_DOCKER_GROUP_MEMBERS)
    ):
        findings.append(HostFinding(HostCode.CONTAINER, "runtime boundary"))
    return tuple(findings)


def evaluate_host_facts(
    policy: dict[str, object], facts: dict[str, object]
) -> HostAdmissionEvaluation:
    """Evaluate supplied read-only facts; never collect or mutate host state."""
    findings = list(validate_policy(policy))
    if _has_secret(facts):
        findings.append(HostFinding(HostCode.SECRET, "facts"))
    if (
        frozenset(facts) != _FACT_KEYS
        or facts.get("schema_version") != 1
        or facts.get("source") != "READ_ONLY_HOST_FACTS"
        or _mapping(facts.get("host_packages")) != {}
        or _mapping(facts.get("private_subnets")) != {}
    ):
        findings.append(HostFinding(HostCode.INVENTORY, "facts header"))
    operating_system = _mapping(facts.get("os"))
    if operating_system != {"id": "ubuntu", "version_id": "24.04"}:
        findings.append(HostFinding(HostCode.OPERATING_SYSTEM, "exact Ubuntu release"))
    if facts.get("architecture") != "x86_64":
        findings.append(HostFinding(HostCode.ARCHITECTURE, "x86_64"))
    memory_bytes = facts.get("memory_bytes")
    if type(memory_bytes) is not int or memory_bytes < _MIN_MEMORY_BYTES:
        findings.append(HostFinding(HostCode.MEMORY, "minimum 64 GiB"))
    findings.extend(_validate_storage(facts))
    findings.extend(_validate_security_facts(facts))
    return HostAdmissionEvaluation(
        facts_conform=not findings,
        admitted=False,
        findings=tuple(findings),
        blockers=_EXPECTED_BLOCKERS,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, help="optional read-only host-facts JSON")
    return parser


def main() -> None:
    """Validate policy and optionally evaluate already-collected facts."""
    root = Path(__file__).resolve().parents[1]
    arguments = _parser().parse_args()
    report = check_policy(root)
    if arguments.facts is not None:
        policy = _read_object(root / POLICY_PATH)
        evaluation = evaluate_host_facts(policy, _read_object(arguments.facts))
        if evaluation.findings:
            detail = ", ".join(
                f"{finding.code.value}:{finding.detail}" for finding in evaluation.findings
            )
            message = f"host facts failed: {detail}"
            raise ValueError(message)
    print(
        "PASS V1 POC host-admission policy; NOT_READY: "
        f"{len(report.blockers)} blockers, host mutation authorized=false"
    )


if __name__ == "__main__":
    main()
