"""Collect bounded read-only Ubuntu facts for the disabled V1 POC admission gate."""

from __future__ import annotations

import argparse
import grp
import ipaddress
import json
import os
import platform
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, NoReturn, Protocol, Self, cast

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_REQUIRED_PATHS = (
    "/srv/asklegal/sql",
    "/srv/asklegal/vault-primary",
    "/srv/asklegal/vault-recovery",
)
_COMMAND_ENV = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
}
_MAX_COMMAND_OUTPUT = 1_000_000
_MAX_PATH_LENGTH = 4096
_MAX_TCP_PORT = 65535
_PRIVATE_DIRECTORY_MODE = 0o700
_SS_MIN_FIELDS = 5
_ENVELOPE_FAILURES = (OSError, TypeError, ValueError)
_OUTPUT_FAILURES = (OSError, TypeError, ValueError)
_PERMISSION_FAILURE_MARKERS = ("operation not permitted", "permission denied")
_IP_ADDRESS_ERRORS = (ipaddress.AddressValueError, ipaddress.NetmaskValueError)
_ENVELOPE_KEYS = frozenset(
    {
        "collected_fact_classes",
        "complete",
        "failures",
        "legacy_facts",
        "missing_fact_classes",
        "schema_version",
        "source",
    }
)
_COMPLETE_FACT_KEYS = (
    "applications",
    "architecture",
    "backup_freshness",
    "container_runtime",
    "containers",
    "credentials",
    "firewall",
    "host_packages",
    "journal",
    "kernel",
    "listeners",
    "memory_bytes",
    "mount_capacity",
    "os",
    "paths",
    "physical_disks",
    "private_subnets",
    "resources",
    "schedulers",
    "systemd",
    "telemetry",
    "time",
)
_ARCHITECTURES = frozenset({"aarch64", "x86_64"})
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}\Z")
_SAFE_ACCOUNT = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
_SAFE_OS_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_SAFE_OS_VERSION = re.compile(r"[0-9][0-9.]{0,31}\Z")
_SAFE_PACKAGE_VERSION = re.compile(r"[0-9][A-Za-z0-9.+:~_-]{0,127}\Z")
_SAFE_FILESYSTEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}\Z")
_LOCKED_HOST_PACKAGES = (
    "ca-certificates",
    "containerd.io",
    "docker-ce",
    "docker-ce-cli",
    "e2fsprogs",
    "nftables",
    "systemd",
    "systemd-timesyncd",
    "util-linux",
)
_DECLARED_NETWORK_IDS = (
    "asklegal-register",
    "asklegal-scheduler-general",
    "asklegal-scheduler-promotion",
    "asklegal-vault-primary",
    "asklegal-vault-recovery",
    "asklegal-review",
    "asklegal-telemetry",
    "asklegal-egress-source",
    "asklegal-egress-model",
    "asklegal-egress-promotion",
)
_SYSTEMD_TARGET = "asklegal.target"
_SYSTEMD_SERVICE_UNITS = (
    "asklegal-acquisition-worker.service",
    "asklegal-control-plane.service",
    "asklegal-dts-general.service",
    "asklegal-dts-promotion.service",
    "asklegal-egress-model.service",
    "asklegal-egress-promotion.service",
    "asklegal-egress-source.service",
    "asklegal-legal-processing-worker.service",
    "asklegal-networks.service",
    "asklegal-otel-collector.service",
    "asklegal-promotion-worker.service",
    "asklegal-register-migrate.service",
    "asklegal-review-api.service",
    "asklegal-sql-server.service",
    "asklegal-vault-bootstrap.service",
    "asklegal-vault-primary.service",
    "asklegal-vault-recovery.service",
)
_SYSTEMD_TIMER_UNITS = (
    "asklegal-audit-archive.timer",
    "asklegal-full-reconciliation.timer",
    "asklegal-ordinary-observation.timer",
    "asklegal-recovery-verification.timer",
    "asklegal-telemetry-retention.timer",
)
_APPLICATIONS = (
    ("ACQUISITION_WORKER", "asklegal-acquisition-worker", "asklegal-acquisition-worker.service"),
    ("CONTROL_PLANE", "asklegal-control-plane", "asklegal-control-plane.service"),
    (
        "LEGAL_PROCESSING_WORKER",
        "asklegal-legal-processing-worker",
        "asklegal-legal-processing-worker.service",
    ),
    ("PROMOTION_WORKER", "asklegal-promotion-worker", "asklegal-promotion-worker.service"),
    ("REVIEW_API", "asklegal-review-api", "asklegal-review-api.service"),
)
_SCHEDULERS = (
    ("GENERAL", "asklegal-dts-general"),
    ("PROMOTION", "asklegal-dts-promotion"),
)
_BACKUP_ROOTS = (
    ("NATIVE", "/var/lib/asklegal/promotion-backup-native"),
    ("RECOVERY", "/var/lib/asklegal/promotion-backup-recovery"),
)
_TELEMETRY_ROOT = Path("/var/lib/asklegal/control/telemetry")
_HEX_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_KERNEL_RELEASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\Z")


class HostFactClass(StrEnum):
    """Closed Plan 8 inventory of required current-host fact classes."""

    APPLICATION_READINESS = "APPLICATION_READINESS"
    BACKUP_FRESHNESS = "BACKUP_FRESHNESS"
    CONTAINERS_IMAGES_HEALTH = "CONTAINERS_IMAGES_HEALTH"
    CREDENTIAL_METADATA = "CREDENTIAL_METADATA"
    FILESYSTEM_CAPACITY = "FILESYSTEM_CAPACITY"
    NETWORK_POLICY = "NETWORK_POLICY"
    OS_KERNEL = "OS_KERNEL"
    RESOURCES = "RESOURCES"
    SCHEDULER_IDENTITIES = "SCHEDULER_IDENTITIES"
    SYSTEMD_UNITS_TIMERS = "SYSTEMD_UNITS_TIMERS"
    TELEMETRY_FRESHNESS = "TELEMETRY_FRESHNESS"


class HostFactFailureCode(StrEnum):
    """Sanitized reasons one required fact class was not collected."""

    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"
    NOT_FOUND = "NOT_FOUND"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PROBE_FAILED = "PROBE_FAILED"
    TIMEOUT = "TIMEOUT"


class HostFactAbsent(Exception):
    """Signal that one inspected object was proved absent, not unreadable."""


class HostFactsOutputError(RuntimeError):
    """One sanitized local output failure."""


@dataclass(frozen=True, slots=True)
class HostFactClassOutcome:
    """One and only one collected-or-missing outcome for a required class."""

    fact_class: HostFactClass
    collected: bool
    failure_code: HostFactFailureCode | None


@dataclass(frozen=True, slots=True)
class HostFactFailure:
    """One sanitized missing-class fact with no probe-owned detail."""

    fact_class: HostFactClass
    code: HostFactFailureCode


@dataclass(frozen=True, slots=True, init=False)
class HKV1HostFacts:
    """Detached deterministic envelope for complete or incomplete host facts."""

    complete: bool
    collected_fact_classes: tuple[HostFactClass, ...]
    missing_fact_classes: tuple[HostFactClass, ...]
    failures: tuple[HostFactFailure, ...]
    _legacy_facts_bytes: bytes = field(repr=False)

    @property
    def legacy_facts(self) -> dict[str, object]:
        """Return a fresh copy of the accepted legacy fact snapshot."""
        value: object = json.loads(self._legacy_facts_bytes)
        document = _string_object(value)
        if document is None:
            message = "HOST_FACT_ENVELOPE_INVALID"
            raise ValueError(message)
        return document


class _ProbeBoundary:
    """Capture ordinary failures without hiding process-control exceptions."""

    failure_code: HostFactFailureCode | None

    def __init__(self) -> None:
        self.failure_code = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exception_type, traceback
        if exception is None:
            return False
        if isinstance(exception, Exception):
            self.failure_code = _probe_failure_code(exception)
            return True
        return False


class HostFactsSource(Protocol):
    """Semantic read-only facts supplied by an Ubuntu probe or a deterministic fake."""

    def operating_system(self) -> dict[str, JsonValue]:
        """Return exact ID and VERSION_ID facts."""
        ...

    def architecture(self) -> str:
        """Return the kernel-reported machine architecture."""
        ...

    def memory_bytes(self) -> int:
        """Return physical memory size in bytes."""
        ...

    def physical_disks(self) -> list[JsonValue]:
        """Return bounded physical-disk identity and size facts."""
        ...

    def path_facts(self) -> list[JsonValue]:
        """Return exact facts for only the three required storage paths."""
        ...

    def time_facts(self) -> dict[str, JsonValue]:
        """Return time-synchronization state."""
        ...

    def credential_facts(self) -> dict[str, JsonValue]:
        """Return credential mechanism and file-mode facts without values."""
        ...

    def firewall_facts(self) -> dict[str, JsonValue]:
        """Return default policy and public-listener facts."""
        ...

    def journal_facts(self) -> dict[str, JsonValue]:
        """Return persistent and forward-secure journal facts."""
        ...

    def container_runtime_facts(self) -> dict[str, JsonValue]:
        """Return Docker service and group-boundary facts."""
        ...

    def host_package_facts(self) -> dict[str, JsonValue]:
        """Return exact installed versions for only the locked host packages."""
        ...

    def observed_network_facts(self) -> dict[str, JsonValue]:
        """Return the declared container subnets and every other host network in use."""
        ...

    def kernel_facts(self) -> dict[str, JsonValue]:
        """Return kernel release and a non-reversible boot identity."""
        ...

    def systemd_facts(self) -> dict[str, JsonValue]:
        """Return the exact target, service-unit, and persistent-timer states."""
        ...

    def container_facts(self) -> list[JsonValue]:
        """Return all container names, immutable image IDs, and health states."""
        ...

    def listener_facts(self) -> list[JsonValue]:
        """Return a secret-free TCP/UDP listener inventory."""
        ...

    def resource_facts(self) -> list[JsonValue]:
        """Return per-service cgroup limits and current usage."""
        ...

    def mount_capacity_facts(self) -> list[JsonValue]:
        """Return capacity and inode availability for each required mount."""
        ...

    def backup_freshness_facts(self) -> dict[str, JsonValue]:
        """Return metadata-only native/recovery backup freshness."""
        ...

    def scheduler_identity_facts(self) -> list[JsonValue]:
        """Return exact local scheduler container and image identities."""
        ...

    def telemetry_freshness_facts(self) -> dict[str, JsonValue]:
        """Return metadata-only local telemetry freshness."""
        ...

    def application_readiness_facts(self) -> list[JsonValue]:
        """Return five application service/container readiness observations."""
        ...


def parse_os_release(raw: str) -> dict[str, str]:
    """Parse declared key/value facts from one bounded OS release document."""
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key] = value.strip().strip('"')
    return values


def _json_object(raw: str, label: str) -> dict[str, object]:
    value: object = json.loads(raw)
    document = _string_object(value)
    if document is None:
        raise TypeError(label)
    return document


def _json_objects(value: object, label: str) -> tuple[dict[str, object], ...]:
    items = _object_list(value)
    if items is None:
        raise ValueError(label)
    result: list[dict[str, object]] = []
    for item in items:
        document = _string_object(item)
        if document is None:
            raise ValueError(label)
        result.append(document)
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


def _probe_failure_code(exception: Exception) -> HostFactFailureCode:
    if isinstance(exception, HostFactAbsent):
        return HostFactFailureCode.NOT_FOUND
    if isinstance(exception, PermissionError):
        return HostFactFailureCode.PERMISSION_DENIED
    if isinstance(exception, (subprocess.TimeoutExpired, TimeoutError)):
        return HostFactFailureCode.TIMEOUT
    if isinstance(
        exception,
        (json.JSONDecodeError, TypeError, UnicodeDecodeError, ValueError),
    ):
        return HostFactFailureCode.MALFORMED_OUTPUT
    return HostFactFailureCode.PROBE_FAILED


def _snapshot_json(value: object) -> object:
    raw = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return json.loads(raw)


def _exact_object(value: object, keys: frozenset[str], label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError(label)
    candidate = cast("dict[object, object]", value)
    if any(type(key) is not str for key in candidate) or frozenset(candidate) != keys:
        raise ValueError(label)
    return cast("dict[str, object]", candidate)


def _exact_list(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise TypeError(label)
    return cast("list[object]", value)


def _closed_string(
    value: object,
    *,
    label: str,
    allowed: frozenset[str] | None = None,
    grammar: re.Pattern[str] | None = None,
) -> str:
    if type(value) is not str:
        raise TypeError(label)
    text = value
    if (allowed is not None and text not in allowed) or (
        grammar is not None and grammar.fullmatch(text) is None
    ):
        raise ValueError(label)
    return text


def _closed_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(label)
    return value


def _closed_positive_int(value: object, label: str, *, maximum: int = 2**63 - 1) -> int:
    if type(value) is not int:
        raise TypeError(label)
    number = value
    if not 0 < number <= maximum:
        raise ValueError(label)
    return number


def _closed_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise TypeError(label)
    return value


def _optional_nonnegative_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _closed_nonnegative_int(value, label)


def _fingerprint(value: object, label: str) -> str:
    return _closed_string(value, label=label, grammar=_HEX_FINGERPRINT)


def _unit_rows(value: object, label: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    names: list[str] = []
    fields = frozenset({"active_state", "load_state", "sub_state", "unit_file_state", "unit_name"})
    for raw in _exact_list(value, label):
        item = _exact_object(raw, fields, label)
        name = _closed_string(item["unit_name"], label=label, grammar=_SAFE_IDENTIFIER)
        names.append(name)
        rows.append(
            {
                "active_state": _closed_string(
                    item["active_state"], label=label, grammar=_SAFE_IDENTIFIER
                ),
                "load_state": _closed_string(
                    item["load_state"], label=label, grammar=_SAFE_IDENTIFIER
                ),
                "sub_state": _closed_string(
                    item["sub_state"], label=label, grammar=_SAFE_IDENTIFIER
                ),
                "unit_file_state": _closed_string(
                    item["unit_file_state"], label=label, grammar=_SAFE_IDENTIFIER
                ),
                "unit_name": name,
            }
        )
    if names != sorted(set(names)):
        raise ValueError(label)
    return rows


def _validate_systemd(value: object, label: str) -> object:
    item = _exact_object(
        value,
        frozenset({"service_units", "target", "timer_units"}),
        label,
    )
    target_rows = _unit_rows([item["target"]], label)
    if len(target_rows) != 1 or target_rows[0].get("unit_name") != _SYSTEMD_TARGET:
        raise ValueError(label)
    service_units = _unit_rows(item["service_units"], label)
    timer_units = _unit_rows(item["timer_units"], label)
    if [row.get("unit_name") for row in service_units] != list(_SYSTEMD_SERVICE_UNITS):
        raise ValueError(label)
    if [row.get("unit_name") for row in timer_units] != list(_SYSTEMD_TIMER_UNITS):
        raise ValueError(label)
    return {
        "service_units": service_units,
        "target": target_rows[0],
        "timer_units": timer_units,
    }


def _validate_containers(value: object, label: str) -> object:
    rows: list[object] = []
    names: list[str] = []
    fields = frozenset({"health", "image_id", "name", "runtime_state"})
    for raw in _exact_list(value, label):
        item = _exact_object(raw, fields, label)
        name = _closed_string(item["name"], label=label, grammar=_SAFE_IDENTIFIER)
        names.append(name)
        rows.append(
            {
                "health": _closed_string(
                    item["health"],
                    label=label,
                    allowed=frozenset({"HEALTHY", "NONE", "STARTING", "UNHEALTHY", "UNKNOWN"}),
                ),
                "image_id": _fingerprint(item["image_id"], label),
                "name": name,
                "runtime_state": _closed_string(
                    item["runtime_state"], label=label, grammar=_SAFE_IDENTIFIER
                ),
            }
        )
    if names != sorted(set(names)):
        raise ValueError(label)
    return rows


def _validate_listeners(value: object, label: str) -> object:
    rows: list[object] = []
    identities: list[tuple[str, str, int]] = []
    fields = frozenset({"address", "port", "public", "transport"})
    for raw in _exact_list(value, label):
        item = _exact_object(raw, fields, label)
        transport = _closed_string(
            item["transport"], label=label, allowed=frozenset({"TCP", "UDP"})
        )
        address = _closed_string(item["address"], label=label)
        try:
            address = str(ipaddress.ip_address(address))
        except ValueError:
            raise ValueError(label) from None
        port = _closed_positive_int(item["port"], label, maximum=_MAX_TCP_PORT)
        public = _closed_bool(item["public"], label)
        identities.append((transport, address, port))
        rows.append({"address": address, "port": port, "public": public, "transport": transport})
    if identities != sorted(set(identities)):
        raise ValueError(label)
    return rows


def _validate_resources(value: object, label: str) -> object:
    rows: list[object] = []
    names: list[str] = []
    fields = frozenset(
        {
            "cpu_usage_nsec",
            "memory_current_bytes",
            "memory_max_bytes",
            "tasks_current",
            "tasks_max",
            "unit_name",
        }
    )
    for raw in _exact_list(value, label):
        item = _exact_object(raw, fields, label)
        name = _closed_string(item["unit_name"], label=label, grammar=_SAFE_IDENTIFIER)
        names.append(name)
        rows.append(
            {
                "cpu_usage_nsec": _optional_nonnegative_int(item["cpu_usage_nsec"], label),
                "memory_current_bytes": _optional_nonnegative_int(
                    item["memory_current_bytes"], label
                ),
                "memory_max_bytes": _optional_nonnegative_int(item["memory_max_bytes"], label),
                "tasks_current": _optional_nonnegative_int(item["tasks_current"], label),
                "tasks_max": _optional_nonnegative_int(item["tasks_max"], label),
                "unit_name": name,
            }
        )
    if names != sorted(set(names)) or names != list(_SYSTEMD_SERVICE_UNITS):
        raise ValueError(label)
    return rows


def _validate_capacity(value: object, label: str) -> object:
    rows: list[object] = []
    paths: list[str] = []
    fields = frozenset({"available_bytes", "inode_available", "inode_total", "path", "total_bytes"})
    for raw in _exact_list(value, label):
        item = _exact_object(raw, fields, label)
        path = _absolute_path(item["path"], label)
        paths.append(path)
        total = _closed_positive_int(item["total_bytes"], label)
        available = _closed_nonnegative_int(item["available_bytes"], label)
        inode_total = _closed_positive_int(item["inode_total"], label)
        inode_available = _closed_nonnegative_int(item["inode_available"], label)
        if available > total or inode_available > inode_total:
            raise ValueError(label)
        rows.append(
            {
                "available_bytes": available,
                "inode_available": inode_available,
                "inode_total": inode_total,
                "path": path,
                "total_bytes": total,
            }
        )
    if paths != list(_REQUIRED_PATHS):
        raise ValueError(label)
    return rows


def _timestamp(value: object, label: str) -> str:
    text = _closed_string(value, label=label)
    try:
        instant = datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError:
        raise ValueError(label) from None
    if not text.endswith("Z") or instant.tzinfo is None or instant.microsecond:
        raise ValueError(label)
    return text


def _freshness_row(
    value: object,
    label: str,
    *,
    allowed_root: str,
) -> dict[str, object]:
    fields = frozenset(
        {
            "age_seconds",
            "file_count",
            "latest_mtime_ns",
            "present",
            "root",
            "total_bytes",
        }
    )
    item = _exact_object(value, fields, label)
    present = _closed_bool(item["present"], label)
    file_count = _closed_nonnegative_int(item["file_count"], label)
    total_bytes = _closed_nonnegative_int(item["total_bytes"], label)
    latest = _optional_nonnegative_int(item["latest_mtime_ns"], label)
    age = _optional_nonnegative_int(item["age_seconds"], label)
    if (
        _absolute_path(item["root"], label) != allowed_root
        or (present and (file_count < 1 or latest is None or age is None))
        or (
            not present
            and (file_count != 0 or total_bytes != 0 or latest is not None or age is not None)
        )
    ):
        raise ValueError(label)
    return {
        "age_seconds": age,
        "file_count": file_count,
        "latest_mtime_ns": latest,
        "present": present,
        "root": allowed_root,
        "total_bytes": total_bytes,
    }


def _validate_backups(value: object, label: str) -> object:
    item = _exact_object(value, frozenset({"backups", "observed_at"}), label)
    observed_at = _timestamp(item["observed_at"], label)
    rows: list[object] = []
    for raw, (expected_class, expected_root) in zip(
        _exact_list(item["backups"], label), _BACKUP_ROOTS, strict=True
    ):
        document = _exact_object(raw, frozenset({"backup_class", "freshness"}), label)
        backup_class = _closed_string(
            document["backup_class"], label=label, grammar=_SAFE_IDENTIFIER
        )
        if backup_class != expected_class:
            raise ValueError(label)
        rows.append(
            {
                "backup_class": backup_class,
                "freshness": _freshness_row(
                    document["freshness"], label, allowed_root=expected_root
                ),
            }
        )
    return {"backups": rows, "observed_at": observed_at}


def _validate_schedulers(value: object, label: str) -> object:
    rows: list[object] = []
    identities: list[tuple[str, str]] = []
    fields = frozenset({"container_id", "container_name", "image_id", "present", "scheduler_id"})
    for raw in _exact_list(value, label):
        item = _exact_object(raw, fields, label)
        scheduler_id = _closed_string(item["scheduler_id"], label=label, grammar=_SAFE_IDENTIFIER)
        container_name = _closed_string(
            item["container_name"], label=label, grammar=_SAFE_IDENTIFIER
        )
        present = _closed_bool(item["present"], label)
        container_id = item["container_id"]
        image_id = item["image_id"]
        if present:
            container_id = _closed_string(container_id, label=label, grammar=_SAFE_IDENTIFIER)
            image_id = _fingerprint(image_id, label)
        elif container_id is not None or image_id is not None:
            raise ValueError(label)
        identities.append((scheduler_id, container_name))
        rows.append(
            {
                "container_id": container_id,
                "container_name": container_name,
                "image_id": image_id,
                "present": present,
                "scheduler_id": scheduler_id,
            }
        )
    if identities != list(_SCHEDULERS):
        raise ValueError(label)
    return rows


def _validate_telemetry(value: object, label: str) -> object:
    item = _exact_object(value, frozenset({"freshness", "observed_at"}), label)
    return {
        "freshness": _freshness_row(
            item["freshness"], label, allowed_root=_TELEMETRY_ROOT.as_posix()
        ),
        "observed_at": _timestamp(item["observed_at"], label),
    }


def _validate_applications(value: object, label: str) -> object:
    rows: list[object] = []
    identities: list[tuple[str, str, str]] = []
    fields = frozenset(
        {"active_state", "application_id", "container_name", "health", "systemd_unit"}
    )
    health_values = frozenset({"HEALTHY", "NONE", "STARTING", "UNHEALTHY", "UNKNOWN"})
    for raw in _exact_list(value, label):
        item = _exact_object(raw, fields, label)
        application_id = _closed_string(
            item["application_id"], label=label, grammar=_SAFE_IDENTIFIER
        )
        container_name = _closed_string(
            item["container_name"], label=label, grammar=_SAFE_IDENTIFIER
        )
        systemd_unit = _closed_string(item["systemd_unit"], label=label, grammar=_SAFE_IDENTIFIER)
        identities.append((application_id, container_name, systemd_unit))
        rows.append(
            {
                "active_state": _closed_string(
                    item["active_state"], label=label, grammar=_SAFE_IDENTIFIER
                ),
                "application_id": application_id,
                "container_name": container_name,
                "health": _closed_string(item["health"], label=label, allowed=health_values),
                "systemd_unit": systemd_unit,
            }
        )
    if identities != list(_APPLICATIONS):
        raise ValueError(label)
    return rows


def _absolute_path(value: object, label: str) -> str:
    text = _closed_string(value, label=label)
    if len(text) > _MAX_PATH_LENGTH or not text.startswith("/") or "\x00" in text:
        raise ValueError(label)
    return text


def _ipv4_network(value: object, label: str) -> str:
    text = _closed_string(value, label=label)
    try:
        parsed = ipaddress.IPv4Network(text, strict=True)
    except _IP_ADDRESS_ERRORS:
        raise ValueError(label) from None
    return str(parsed)


def _ipv4_interface(value: object, label: str) -> str:
    text = _closed_string(value, label=label)
    try:
        parsed = ipaddress.IPv4Interface(text)
    except _IP_ADDRESS_ERRORS:
        raise ValueError(label) from None
    return str(parsed)


def _validate_probe_result(  # noqa: C901, PLR0911, PLR0912, PLR0915
    key: str, value: object
) -> object:
    """Detach one probe result only after its exact semantic schema is proved."""
    if key == "os":
        item = _exact_object(value, frozenset({"id", "version_id"}), key)
        return {
            "id": _closed_string(item["id"], label=key, grammar=_SAFE_OS_ID),
            "version_id": _closed_string(item["version_id"], label=key, grammar=_SAFE_OS_VERSION),
        }
    if key == "architecture":
        return _closed_string(value, label=key, allowed=_ARCHITECTURES)
    if key == "memory_bytes":
        return _closed_positive_int(value, key)
    if key == "physical_disks":
        disks: list[object] = []
        identities: set[str] = set()
        for raw in _exact_list(value, key):
            item = _exact_object(raw, frozenset({"size_bytes", "stable_id"}), key)
            identity = _closed_string(item["stable_id"], label=key, grammar=_SAFE_IDENTIFIER)
            if not identity.startswith("disk:") or identity in identities:
                raise ValueError(key)
            identities.add(identity)
            disks.append(
                {
                    "size_bytes": _closed_positive_int(item["size_bytes"], key),
                    "stable_id": identity,
                }
            )
        if not disks:
            raise ValueError(key)
        return disks
    if key == "paths":
        paths: list[object] = []
        observed: set[str] = set()
        required = frozenset(
            {"fs_type", "path", "physical_disk_id", "real_path", "symlink", "writable"}
        )
        for raw in _exact_list(value, key):
            item = _exact_object(raw, required, key)
            path = _absolute_path(item["path"], key)
            if path not in _REQUIRED_PATHS or path in observed:
                raise ValueError(key)
            observed.add(path)
            paths.append(
                {
                    "fs_type": _closed_string(item["fs_type"], label=key, grammar=_SAFE_FILESYSTEM),
                    "path": path,
                    "physical_disk_id": _closed_string(
                        item["physical_disk_id"], label=key, grammar=_SAFE_IDENTIFIER
                    ),
                    "real_path": _absolute_path(item["real_path"], key),
                    "symlink": _closed_bool(item["symlink"], key),
                    "writable": _closed_bool(item["writable"], key),
                }
            )
        if observed != set(_REQUIRED_PATHS):
            raise ValueError(key)
        return paths
    if key == "time":
        item = _exact_object(value, frozenset({"synchronized"}), key)
        return {"synchronized": _closed_bool(item["synchronized"], key)}
    if key == "credentials":
        item = _exact_object(
            value,
            frozenset(
                {
                    "encrypted_blob_mode",
                    "persistent_plaintext_credential_paths",
                    "protection_mode",
                    "systemd_creds_available",
                }
            ),
            key,
        )
        plaintext = [
            _absolute_path(path, key)
            for path in _exact_list(item["persistent_plaintext_credential_paths"], key)
        ]
        if plaintext != sorted(set(plaintext)):
            raise ValueError(key)
        return {
            "encrypted_blob_mode": _closed_string(
                item["encrypted_blob_mode"],
                label=key,
                allowed=frozenset({"0400", "UNPROVED"}),
            ),
            "persistent_plaintext_credential_paths": plaintext,
            "protection_mode": _closed_string(
                item["protection_mode"],
                label=key,
                allowed=frozenset({"HOST_KEY_ONLY", "TPM2_PLUS_HOST_KEY", "UNPROVED"}),
            ),
            "systemd_creds_available": _closed_bool(item["systemd_creds_available"], key),
        }
    if key == "firewall":
        item = _exact_object(
            value,
            frozenset(
                {
                    "direct_container_egress_default",
                    "forward_default",
                    "input_default",
                    "nftables_available",
                    "public_tcp_ports",
                }
            ),
            key,
        )
        policy = frozenset({"ACCEPT", "DROP", "UNPROVED"})
        ports = [
            _closed_positive_int(port, key, maximum=_MAX_TCP_PORT)
            for port in _exact_list(item["public_tcp_ports"], key)
        ]
        if ports != sorted(set(ports)):
            raise ValueError(key)
        return {
            "direct_container_egress_default": _closed_string(
                item["direct_container_egress_default"], label=key, allowed=policy
            ),
            "forward_default": _closed_string(item["forward_default"], label=key, allowed=policy),
            "input_default": _closed_string(item["input_default"], label=key, allowed=policy),
            "nftables_available": _closed_bool(item["nftables_available"], key),
            "public_tcp_ports": ports,
        }
    if key == "journal":
        item = _exact_object(value, frozenset({"forward_secure_sealing", "storage"}), key)
        return {
            "forward_secure_sealing": _closed_bool(item["forward_secure_sealing"], key),
            "storage": _closed_string(
                item["storage"], label=key, allowed=frozenset({"PERSISTENT", "VOLATILE"})
            ),
        }
    if key == "container_runtime":
        item = _exact_object(
            value,
            frozenset({"docker_group_non_root_members", "name", "service_manager"}),
            key,
        )
        members = [
            _closed_string(member, label=key, grammar=_SAFE_ACCOUNT)
            for member in _exact_list(item["docker_group_non_root_members"], key)
        ]
        if members != sorted(set(members)):
            raise ValueError(key)
        return {
            "docker_group_non_root_members": members,
            "name": _closed_string(
                item["name"], label=key, allowed=frozenset({"UNPROVED", "docker"})
            ),
            "service_manager": _closed_string(
                item["service_manager"],
                label=key,
                allowed=frozenset({"UNPROVED", "systemd"}),
            ),
        }
    if key == "host_packages":
        item = _exact_object(value, frozenset(_LOCKED_HOST_PACKAGES), key)
        result: dict[str, object] = {}
        for package in _LOCKED_HOST_PACKAGES:
            version = _closed_string(item[package], label=key)
            if version != "NOT_INSTALLED" and _SAFE_PACKAGE_VERSION.fullmatch(version) is None:
                raise ValueError(key)
            result[package] = version
        return result
    if key == "private_subnets":
        item = _exact_object(value, frozenset({"declared", "foreign"}), key)
        declared_value = item["declared"]
        if type(declared_value) is not dict:
            raise TypeError(key)
        declared_raw = cast("dict[object, object]", declared_value)
        if any(type(name) is not str for name in declared_raw):
            raise ValueError(key)
        if not frozenset(declared_raw).issubset(_DECLARED_NETWORK_IDS):
            raise ValueError(key)
        declared = {
            cast("str", name): _ipv4_network(subnet, key) for name, subnet in declared_raw.items()
        }
        foreign = [_ipv4_interface(cidr, key) for cidr in _exact_list(item["foreign"], key)]
        if len(foreign) != len(set(foreign)):
            raise ValueError(key)
        return {"declared": declared, "foreign": sorted(foreign)}
    if key == "kernel":
        item = _exact_object(value, frozenset({"boot_id_fingerprint", "release"}), key)
        return {
            "boot_id_fingerprint": _fingerprint(item["boot_id_fingerprint"], key),
            "release": _closed_string(item["release"], label=key, grammar=_KERNEL_RELEASE),
        }
    if key == "systemd":
        return _validate_systemd(value, key)
    if key == "containers":
        return _validate_containers(value, key)
    if key == "listeners":
        return _validate_listeners(value, key)
    if key == "resources":
        return _validate_resources(value, key)
    if key == "mount_capacity":
        return _validate_capacity(value, key)
    if key == "backup_freshness":
        return _validate_backups(value, key)
    if key == "schedulers":
        return _validate_schedulers(value, key)
    if key == "telemetry":
        return _validate_telemetry(value, key)
    if key == "applications":
        return _validate_applications(value, key)
    message = "unknown host probe"
    raise ValueError(message)


def _legacy_snapshot(value: object) -> bytes:
    snapshot = _snapshot_json(value)
    document = _string_object(snapshot)
    if document is None:
        message = "HOST_FACT_ENVELOPE_INVALID"
        raise ValueError(message)
    return json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _invalid_envelope() -> NoReturn:
    message = "HOST_FACT_ENVELOPE_INVALID"
    raise ValueError(message)


def _validated_outcomes(
    outcomes: tuple[HostFactClassOutcome, ...],
) -> tuple[HostFactClassOutcome, ...]:
    if type(outcomes) is not tuple or any(
        type(item) is not HostFactClassOutcome
        or type(item.fact_class) is not HostFactClass
        or type(item.collected) is not bool
        or (item.failure_code is not None and type(item.failure_code) is not HostFactFailureCode)
        for item in outcomes
    ):
        _invalid_envelope()
    ordered = tuple(sorted(outcomes, key=lambda item: item.fact_class.value))
    if tuple(item.fact_class for item in ordered) != tuple(
        sorted(HostFactClass, key=lambda item: item.value)
    ):
        _invalid_envelope()
    if any(
        (item.collected and item.failure_code is not None)
        or (not item.collected and item.failure_code is None)
        for item in ordered
    ):
        _invalid_envelope()
    return ordered


def build_hk_v1_host_facts(
    *,
    legacy_facts: object,
    outcomes: tuple[HostFactClassOutcome, ...],
) -> HKV1HostFacts:
    """Validate, detach, and issue one exhaustive collection envelope."""
    try:
        ordered = _validated_outcomes(outcomes)
        legacy_bytes = _legacy_snapshot(legacy_facts)
    except _ENVELOPE_FAILURES:
        message = "HOST_FACT_ENVELOPE_INVALID"
        raise ValueError(message) from None

    collected = tuple(item.fact_class for item in ordered if item.collected)
    missing = tuple(item.fact_class for item in ordered if not item.collected)
    failures = tuple(
        HostFactFailure(item.fact_class, item.failure_code)
        for item in ordered
        if item.failure_code is not None
    )
    envelope = object.__new__(HKV1HostFacts)
    object.__setattr__(envelope, "complete", not missing)
    object.__setattr__(envelope, "collected_fact_classes", collected)
    object.__setattr__(envelope, "missing_fact_classes", missing)
    object.__setattr__(envelope, "failures", failures)
    object.__setattr__(envelope, "_legacy_facts_bytes", legacy_bytes)
    return envelope


def host_facts_document(envelope: HKV1HostFacts) -> dict[str, object]:
    """Return the canonical secret-free JSON projection for local retention."""
    return {
        "collected_fact_classes": [item.value for item in envelope.collected_fact_classes],
        "complete": envelope.complete,
        "failures": [
            {"code": item.code.value, "fact_class": item.fact_class.value}
            for item in envelope.failures
        ],
        "legacy_facts": envelope.legacy_facts,
        "missing_fact_classes": [item.value for item in envelope.missing_fact_classes],
        "schema_version": 1,
        "source": "READ_ONLY_HK_V1_HOST_FACTS_ENVELOPE",
    }


def _envelope_list(document: dict[str, object], key: str) -> list[object]:
    value = document[key]
    if type(value) is not list:
        _invalid_envelope()
    return cast("list[object]", value)


def _fact_classes(values: list[object]) -> tuple[HostFactClass, ...]:
    result: list[HostFactClass] = []
    for value in values:
        if type(value) is not str:
            _invalid_envelope()
        result.append(HostFactClass(value))
    return tuple(result)


def _failure_codes(values: list[object]) -> dict[HostFactClass, HostFactFailureCode]:
    failures: dict[HostFactClass, HostFactFailureCode] = {}
    for raw_failure in values:
        failure = _string_object(raw_failure)
        if failure is None or frozenset(failure) != frozenset({"code", "fact_class"}):
            _invalid_envelope()
        fact_class_value = failure["fact_class"]
        code_value = failure["code"]
        if type(fact_class_value) is not str or type(code_value) is not str:
            _invalid_envelope()
        fact_class = HostFactClass(fact_class_value)
        code = HostFactFailureCode(code_value)
        if fact_class in failures:
            _invalid_envelope()
        failures[fact_class] = code
    return failures


def parse_host_facts_output_bytes(raw: bytes) -> HKV1HostFacts:
    """Parse one exact canonical envelope previously written by this collector."""
    try:
        if type(raw) is not bytes:
            _invalid_envelope()
        if len(raw) > _MAX_COMMAND_OUTPUT:
            _invalid_envelope()
        value: object = json.loads(raw)
        document = _string_object(value)
        if document is None or frozenset(document) != _ENVELOPE_KEYS:
            _invalid_envelope()
        if (
            document["schema_version"] != 1
            or document["source"] != "READ_ONLY_HK_V1_HOST_FACTS_ENVELOPE"
            or type(document["complete"]) is not bool
        ):
            _invalid_envelope()
        collected = _fact_classes(_envelope_list(document, "collected_fact_classes"))
        missing = _fact_classes(_envelope_list(document, "missing_fact_classes"))
        if (
            collected != tuple(sorted(collected, key=lambda item: item.value))
            or missing != tuple(sorted(missing, key=lambda item: item.value))
            or len({*collected, *missing}) != len(HostFactClass)
            or frozenset((*collected, *missing)) != frozenset(HostFactClass)
            or document["complete"] is not (not missing)
        ):
            _invalid_envelope()
        failures = _failure_codes(_envelope_list(document, "failures"))
        if frozenset(failures) != frozenset(missing):
            _invalid_envelope()
        envelope = build_hk_v1_host_facts(
            legacy_facts=document["legacy_facts"],
            outcomes=tuple(
                HostFactClassOutcome(
                    fact_class,
                    fact_class in collected,
                    failures.get(fact_class),
                )
                for fact_class in HostFactClass
            ),
        )
        canonical = _canonical_envelope_bytes(envelope)
        if raw != canonical:
            _invalid_envelope()
    except _ENVELOPE_FAILURES:
        message = "HOST_FACT_ENVELOPE_INVALID"
        raise ValueError(message) from None
    else:
        return envelope


def validated_complete_host_facts(envelope: HKV1HostFacts) -> dict[str, object]:
    """Revalidate every fact in a complete collector envelope for downstream evidence."""
    try:
        if type(envelope) is not HKV1HostFacts or not envelope.complete:
            _invalid_envelope()
        document = _string_object(_snapshot_json(envelope.legacy_facts))
        if (
            document is None
            or frozenset(document) != frozenset({"schema_version", "source", *_COMPLETE_FACT_KEYS})
            or document["schema_version"] != 1
            or document["source"] != "READ_ONLY_HOST_FACTS"
        ):
            _invalid_envelope()
        result: dict[str, object] = {
            "schema_version": 1,
            "source": "READ_ONLY_HOST_FACTS",
        }
        for key in _COMPLETE_FACT_KEYS:
            result[key] = _validate_probe_result(key, document[key])
    except _ENVELOPE_FAILURES:
        _invalid_envelope()
    return result


def load_host_facts_output(path: Path) -> HKV1HostFacts:
    """Load one exact canonical envelope previously written by this collector."""
    try:
        raw = path.read_bytes()
    except OSError:
        message = "HOST_FACT_ENVELOPE_INVALID"
        raise ValueError(message) from None
    return parse_host_facts_output_bytes(raw)


def _proved_absence(command: tuple[str, ...], returncode: int, stderr: str) -> bool:
    """Recognize only one exact absent-object result for its owning probe type."""
    if returncode != 1:
        return False
    if command[:3] == ("docker", "network", "inspect"):
        normalized = stderr.strip()
        return normalized.startswith("error: no such network:") or (
            normalized.startswith("error response from daemon: network ")
            and normalized.endswith(" not found")
        )
    if command[:2] == ("docker", "inspect"):
        normalized = stderr.strip()
        return "no such object:" in normalized or "no such container:" in normalized
    if command and command[0] == "dpkg-query":
        return stderr.strip().startswith("dpkg-query: no packages found matching pattern")
    return False


def _strict_exists(path: Path) -> bool:
    """Distinguish a missing filesystem object from an unreadable one."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _strict_regular_files(
    root: Path,
    *,
    recursive: bool = False,
    reject_symlinks: bool = False,
) -> tuple[Path, ...]:
    """List only regular files while surfacing stat, scan, and permission failures."""
    try:
        root_status = os.lstat(root)
    except FileNotFoundError:
        return ()
    if not stat.S_ISDIR(root_status.st_mode):
        message = "host metadata directory"
        raise TypeError(message)
    pending = [root]
    files: list[Path] = []
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                entry_status = entry.stat(follow_symlinks=False)
                path = Path(entry.path)
                if stat.S_ISLNK(entry_status.st_mode) and reject_symlinks:
                    message = "host metadata symlink"
                    raise TypeError(message)
                if stat.S_ISREG(entry_status.st_mode):
                    files.append(path)
                elif recursive and stat.S_ISDIR(entry_status.st_mode):
                    pending.append(path)
    return tuple(sorted(files, key=lambda path: path.as_posix()))


class UbuntuHostFactsSource:
    """Strict read-only collector; unavailable or ambiguous facts fail closed."""

    def __init__(self) -> None:
        """Reject non-Linux execution before any command is issued."""
        if platform.system() != "Linux":
            message = "host fact collection requires Linux"
            raise RuntimeError(message)
        self._disk_ids: dict[str, str] = {}

    def _run(self, command: Sequence[str]) -> str:
        result = subprocess.run(  # noqa: S603
            tuple(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=_COMMAND_ENV,
        )
        if result.returncode != 0:
            stderr = result.stderr.casefold()
            if any(marker in stderr for marker in _PERMISSION_FAILURE_MARKERS):
                raise PermissionError
            if _proved_absence(tuple(command), result.returncode, stderr):
                raise HostFactAbsent
            message = f"read-only probe failed: {command[0]}"
            raise RuntimeError(message)
        if len(result.stdout.encode()) > _MAX_COMMAND_OUTPUT:
            message = f"read-only probe failed: {command[0]}"
            raise RuntimeError(message)
        return result.stdout.strip()

    def _absent_or_run(self, command: Sequence[str]) -> str | None:
        """Return output, or None when the inspected object simply does not exist yet."""
        try:
            return self._run(command)
        except HostFactAbsent:
            return None

    def operating_system(self) -> dict[str, JsonValue]:
        """Read the bounded operating-system release file."""
        values = parse_os_release(Path("/etc/os-release").read_text(encoding="utf-8"))
        return {
            "id": values.get("ID", "UNKNOWN"),
            "version_id": values.get("VERSION_ID", "UNKNOWN"),
        }

    def architecture(self) -> str:
        """Read the machine architecture without executing a command."""
        return platform.machine()

    def kernel_facts(self) -> dict[str, JsonValue]:
        """Read the release and retain only a hash of the current boot identifier."""
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        if re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot_id) is None:
            message = "kernel boot identity"
            raise ValueError(message)
        return {
            "boot_id_fingerprint": f"sha256:{sha256(boot_id.encode()).hexdigest()}",
            "release": platform.release(),
        }

    def memory_bytes(self) -> int:
        """Compute physical memory from kernel page counters."""
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        return page_size * page_count

    def physical_disks(self) -> list[JsonValue]:
        """Read physical disk paths and sizes through lsblk JSON."""
        raw = self._run(("lsblk", "--json", "--bytes", "--output", "PATH,TYPE,SIZE,WWN,SERIAL"))
        document = _json_object(raw, "lsblk document")
        devices = _json_objects(document.get("blockdevices"), "lsblk devices")
        disks: list[JsonValue] = []
        for device in devices:
            if device.get("type") != "disk":
                continue
            path = device.get("path")
            size = device.get("size")
            if not isinstance(path, str) or not isinstance(size, int):
                message = "physical disk fact"
                raise TypeError(message)
            stable_value = device.get("wwn") or device.get("serial") or path
            if not isinstance(stable_value, str) or not stable_value:
                message = "physical disk identity"
                raise TypeError(message)
            stable_id = f"disk:{stable_value}"
            self._disk_ids[path] = stable_id
            disks.append({"stable_id": stable_id, "size_bytes": size})
        return disks

    def _physical_disk_id(self, source: str) -> str:
        parent = self._run(("lsblk", "--noheadings", "--output", "PKNAME", source)).splitlines()
        disk_path = f"/dev/{parent[-1].strip()}" if parent and parent[-1].strip() else source
        return self._disk_ids.get(disk_path, f"UNRESOLVED:{disk_path}")

    def path_facts(self) -> list[JsonValue]:
        """Read filesystem and backing-disk facts for required paths only."""
        if not self._disk_ids:
            self.physical_disks()
        facts: list[JsonValue] = []
        for path_text in _REQUIRED_PATHS:
            path = Path(path_text)
            real_path = path.resolve(strict=False).as_posix()
            filesystem = self._run(
                ("findmnt", "--json", "--target", path_text, "--output", "FSTYPE,SOURCE")
            )
            document = _json_object(filesystem, "findmnt document")
            filesystems = _json_objects(document.get("filesystems"), "findmnt filesystems")
            if len(filesystems) != 1:
                message = f"ambiguous filesystem: {path_text}"
                raise TypeError(message)
            fs_type = filesystems[0].get("fstype")
            source = filesystems[0].get("source")
            if not isinstance(fs_type, str) or not isinstance(source, str):
                message = f"filesystem fact: {path_text}"
                raise TypeError(message)
            facts.append(
                {
                    "path": path_text,
                    "real_path": real_path,
                    "fs_type": fs_type,
                    "physical_disk_id": self._physical_disk_id(source),
                    "symlink": path.is_symlink(),
                    "writable": path.is_dir() and os.access(path, os.W_OK),
                }
            )
        return facts

    def time_facts(self) -> dict[str, JsonValue]:
        """Read systemd's NTP synchronization fact."""
        synchronized = self._run(("timedatectl", "show", "--property=NTPSynchronized", "--value"))
        normalized = synchronized.lower()
        if normalized not in {"no", "yes"}:
            message = "timedatectl"
            raise ValueError(message)
        return {"synchronized": normalized == "yes"}

    def credential_facts(self) -> dict[str, JsonValue]:
        """Inspect only credential mechanisms, modes, and suspicious path names."""
        credential_root = Path("/etc/asklegal/credentials")
        encrypted_blobs = tuple(
            path for path in _strict_regular_files(credential_root) if path.suffix == ".cred"
        )
        modes = {stat.S_IMODE(os.lstat(path).st_mode) for path in encrypted_blobs}
        encrypted_mode = "0400" if encrypted_blobs and modes == {0o400} else "UNPROVED"
        plaintext_names: list[str] = []
        config_root = Path("/etc/asklegal")
        for path in _strict_regular_files(config_root, recursive=True):
            lowered = path.name.lower()
            if path.suffix != ".cred" and any(
                marker in lowered for marker in ("credential", "password", "secret", "token")
            ):
                plaintext_names.append(path.as_posix())
        protection_mode = (
            "TPM2_PLUS_HOST_KEY"
            if _strict_exists(Path("/dev/tpmrm0")) or _strict_exists(Path("/dev/tpm0"))
            else "HOST_KEY_ONLY"
        )
        plaintext_paths: list[JsonValue] = []
        plaintext_paths.extend(sorted(plaintext_names))
        return {
            "systemd_creds_available": shutil.which("systemd-creds") is not None,
            "protection_mode": protection_mode,
            "encrypted_blob_mode": encrypted_mode,
            "persistent_plaintext_credential_paths": plaintext_paths,
        }

    def _nft_defaults(self) -> tuple[bool, str, str, str]:  # noqa: C901, PLR0912
        nft_available = shutil.which("nft") is not None
        input_default = "UNPROVED"
        forward_default = "UNPROVED"
        egress_default = "UNPROVED"
        if nft_available:
            malformed = "nft"
            ruleset = _json_object(self._run(("nft", "--json", "list", "ruleset")), "nft")
            if frozenset(ruleset) != frozenset({"nftables"}):
                raise ValueError(malformed)
            entry_items = _exact_list(ruleset["nftables"], "nft")
            allowed_entries = frozenset(
                {
                    "chain",
                    "counter",
                    "element",
                    "flowtable",
                    "limit",
                    "map",
                    "metainfo",
                    "quota",
                    "rule",
                    "secmark",
                    "set",
                    "synproxy",
                    "table",
                }
            )
            for raw_entry in entry_items:
                if type(raw_entry) is not dict:
                    raise TypeError(malformed)
                entry = cast("dict[object, object]", raw_entry)
                if (
                    len(entry) != 1
                    or any(type(name) is not str for name in entry)
                    or not frozenset(entry).issubset(allowed_entries)
                ):
                    raise ValueError(malformed)
                entry_name, payload = next(iter(entry.items()))
                if type(payload) is not dict:
                    raise TypeError(malformed)
                if entry_name != "chain":
                    continue
                chain = cast("dict[object, object]", payload)
                if any(type(name) is not str for name in chain):
                    raise ValueError(malformed)
                name = chain.get("name")
                hook = chain.get("hook")
                if type(name) is not str or (hook is not None and type(hook) is not str):
                    raise TypeError(malformed)
                relevant = hook in {"input", "forward"} or name == "asklegal-container-egress"
                if not relevant:
                    continue
                policy = chain.get("policy")
                if type(policy) is not str or policy.lower() not in {"accept", "drop"}:
                    raise ValueError(malformed)
                normalized = policy.upper()
                if hook == "input":
                    input_default = normalized
                elif hook == "forward":
                    forward_default = normalized
                if name == "asklegal-container-egress":
                    egress_default = normalized
        return nft_available, input_default, forward_default, egress_default

    def _public_tcp_ports(self) -> list[int]:
        public_ports: list[int] = []
        malformed = "ss"
        for line in self._run(
            ("ss", "--no-header", "--tcp", "--listening", "--numeric")
        ).splitlines():
            fields = line.split()
            if len(fields) < _SS_MIN_FIELDS:
                raise ValueError(malformed)
            endpoint = fields[3]
            host, _, port_text = endpoint.rpartition(":")
            if not host or not port_text.isdigit():
                raise ValueError(malformed)
            port = int(port_text)
            if not 0 < port <= _MAX_TCP_PORT:
                raise ValueError(malformed)
            normalized_host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
            if normalized_host not in {"127.0.0.1", "::1"}:
                public_ports.append(port)
        return sorted(set(public_ports))

    def firewall_facts(self) -> dict[str, JsonValue]:
        """Read nftables default policies and non-loopback TCP listeners."""
        nft_available, input_default, forward_default, egress_default = self._nft_defaults()
        public_ports: list[JsonValue] = []
        public_ports.extend(self._public_tcp_ports())
        return {
            "nftables_available": nft_available,
            "input_default": input_default,
            "forward_default": forward_default,
            "direct_container_egress_default": egress_default,
            "public_tcp_ports": public_ports,
        }

    def journal_facts(self) -> dict[str, JsonValue]:
        """Inspect persistent journal and sealing-key presence without reading logs."""
        journal_root = Path("/var/log/journal")
        return {
            "storage": "PERSISTENT" if journal_root.is_dir() else "VOLATILE",
            "forward_secure_sealing": bool(tuple(journal_root.glob("*/fss"))),
        }

    def container_runtime_facts(self) -> dict[str, JsonValue]:
        """Inspect Docker presence, systemd activity, and non-root group membership."""
        try:
            docker_group = grp.getgrnam("docker")
        except KeyError:
            members: set[str] = set()
        else:
            members = set(docker_group.gr_mem)
            members.update(
                entry.pw_name
                for entry in pwd.getpwall()
                if entry.pw_gid == docker_group.gr_gid and entry.pw_uid != 0
            )
        docker_active = self._run(("systemctl", "is-active", "docker")) == "active"
        group_members: list[JsonValue] = []
        group_members.extend(sorted(members))
        return {
            "name": "docker"
            if shutil.which("docker") is not None and docker_active
            else "UNPROVED",
            "service_manager": "systemd" if Path("/run/systemd/system").is_dir() else "UNPROVED",
            "docker_group_non_root_members": group_members,
        }

    def host_package_facts(self) -> dict[str, JsonValue]:
        """Read exact installed versions for only the locked packages; absent means absent."""
        versions: dict[str, JsonValue] = {}
        for name in _LOCKED_HOST_PACKAGES:
            raw = self._absent_or_run(
                ("dpkg-query", "--showformat=${Version}|${Status}", "--show", name)
            )
            version, _, status = (raw or "").partition("|")
            if status.strip() != "install ok installed" or not version:
                versions[name] = "NOT_INSTALLED"
                continue
            versions[name] = version
        return versions

    def observed_network_facts(self) -> dict[str, JsonValue]:
        """Report the declared container subnets and every other IPv4 network on this host."""
        declared: dict[str, str] = {}
        for network_id in _DECLARED_NETWORK_IDS:
            raw = self._absent_or_run(
                (
                    "docker",
                    "network",
                    "inspect",
                    "--format",
                    "{{range .IPAM.Config}}{{.Subnet}}{{end}}",
                    network_id,
                )
            )
            if raw:
                declared[network_id] = raw
        declared_json: dict[str, JsonValue] = dict(declared)
        return {
            "declared": declared_json,
            "foreign": self._foreign_networks(set(declared.values())),
        }

    def _systemd_properties(self, unit_name: str, names: tuple[str, ...]) -> dict[str, str]:
        raw = self._run(
            (
                "systemctl",
                "show",
                unit_name,
                f"--property={','.join(names)}",
                "--no-pager",
            )
        )
        properties: dict[str, str] = {}
        for line in raw.splitlines():
            name, separator, value = line.partition("=")
            if not separator or name not in names or name in properties:
                message = "systemctl show"
                raise ValueError(message)
            properties[name] = value
        if frozenset(properties) != frozenset(names):
            message = "systemctl show"
            raise ValueError(message)
        return properties

    def _unit_state(self, unit_name: str) -> dict[str, JsonValue]:
        properties = self._systemd_properties(
            unit_name,
            ("ActiveState", "LoadState", "SubState", "UnitFileState"),
        )
        return {
            "active_state": properties["ActiveState"] or "unknown",
            "load_state": properties["LoadState"] or "unknown",
            "sub_state": properties["SubState"] or "unknown",
            "unit_file_state": properties["UnitFileState"] or "unknown",
            "unit_name": unit_name,
        }

    def systemd_facts(self) -> dict[str, JsonValue]:
        """Inspect the exact target, 17 service/bootstrap units, and five timers."""
        return {
            "target": self._unit_state(_SYSTEMD_TARGET),
            "service_units": [self._unit_state(name) for name in _SYSTEMD_SERVICE_UNITS],
            "timer_units": [self._unit_state(name) for name in _SYSTEMD_TIMER_UNITS],
        }

    def _inspect_container(self, identity: str) -> dict[str, JsonValue] | None:
        raw = self._absent_or_run(
            ("docker", "inspect", "--type=container", "--format={{json .}}", identity)
        )
        if raw is None:
            return None
        document = _json_object(raw, "docker inspect")
        state = _string_object(document.get("State"))
        if state is None:
            message = "docker inspect state"
            raise TypeError(message)
        health = _string_object(state.get("Health"))
        health_status = "NONE" if health is None else str(health.get("Status", "UNKNOWN")).upper()
        name = document.get("Name")
        container_id = document.get("Id")
        image_id = document.get("Image")
        runtime_state = state.get("Status")
        identity_values = (name, container_id, image_id, runtime_state)
        if not all(type(value) is str and value for value in identity_values):
            message = "docker inspect identity"
            raise TypeError(message)
        return {
            "container_id": cast("str", container_id),
            "health": health_status,
            "image_id": cast("str", image_id),
            "name": cast("str", name).removeprefix("/"),
            "runtime_state": cast("str", runtime_state),
        }

    def container_facts(self) -> list[JsonValue]:
        """Inspect every container returned by Docker without reading its environment."""
        identities = self._run(("docker", "container", "ls", "--all", "--quiet", "--no-trunc"))
        rows: list[JsonValue] = []
        for identity in identities.splitlines():
            if re.fullmatch(r"[0-9a-f]{64}", identity) is None:
                message = "docker container identity"
                raise ValueError(message)
            inspected = self._inspect_container(identity)
            if inspected is None:
                raise HostFactAbsent
            rows.append(
                {
                    "health": inspected["health"],
                    "image_id": inspected["image_id"],
                    "name": inspected["name"],
                    "runtime_state": inspected["runtime_state"],
                }
            )
        return sorted(rows, key=lambda row: cast("str", cast("dict[str, object]", row)["name"]))

    def listener_facts(self) -> list[JsonValue]:
        """Read canonical kernel socket tables without retaining process data."""
        minimum_fields = 4
        ipv4_address_bytes = 4
        identities: dict[tuple[str, str, int], dict[str, JsonValue]] = {}
        for filename, transport, address_bytes, listening_state in (
            ("tcp", "TCP", 4, "0A"),
            ("tcp6", "TCP", 16, "0A"),
            ("udp", "UDP", 4, "07"),
            ("udp6", "UDP", 16, "07"),
        ):
            raw = (Path("/proc/net") / filename).read_bytes()
            if len(raw) > _MAX_COMMAND_OUTPUT:
                message = "proc net listener"
                raise ValueError(message)
            try:
                lines = raw.decode("ascii").splitlines()
            except UnicodeDecodeError as error:
                message = "proc net listener"
                raise ValueError(message) from error
            if not lines or not {"local_address", "st"}.issubset(lines[0].split()):
                message = "proc net listener"
                raise ValueError(message)
            for line in lines[1:]:
                fields = line.split()
                if len(fields) < minimum_fields or fields[3].upper() != listening_state:
                    continue
                address_text, separator, port_text = fields[1].partition(":")
                expected_hex_length = address_bytes * 2
                if (
                    not separator
                    or len(address_text) != expected_hex_length
                    or re.fullmatch(r"[0-9A-Fa-f]+", address_text) is None
                    or re.fullmatch(r"[0-9A-Fa-f]{4}", port_text) is None
                ):
                    message = "proc net listener"
                    raise ValueError(message)
                packed = bytes.fromhex(address_text)
                if address_bytes == ipv4_address_bytes:
                    packed = packed[::-1]
                else:
                    packed = b"".join(
                        packed[offset : offset + 4][::-1] for offset in range(0, 16, 4)
                    )
                parsed = ipaddress.ip_address(packed)
                port = int(port_text, 16)
                if not 0 < port <= _MAX_TCP_PORT:
                    message = "proc net listener"
                    raise ValueError(message)
                identity = (transport, str(parsed), port)
                identities[identity] = {
                    "address": str(parsed),
                    "port": port,
                    "public": not parsed.is_loopback,
                    "transport": transport,
                }
        return sorted(
            identities.values(),
            key=lambda row: (
                cast("dict[str, object]", row)["transport"],
                cast("dict[str, object]", row)["address"],
                cast("dict[str, object]", row)["port"],
            ),
        )

    @staticmethod
    def _systemd_counter(value: str, label: str) -> int | None:
        if value in {"", "[not set]", "infinity"}:
            return None
        if not value.isdigit():
            raise ValueError(label)
        return int(value)

    def resource_facts(self) -> list[JsonValue]:
        """Inspect current service cgroup usage and configured finite/unlimited ceilings."""
        rows: list[JsonValue] = []
        names = (
            "CPUUsageNSec",
            "MemoryCurrent",
            "MemoryMax",
            "TasksCurrent",
            "TasksMax",
        )
        for unit_name in _SYSTEMD_SERVICE_UNITS:
            properties = self._systemd_properties(unit_name, names)
            memory_current = self._systemd_counter(properties["MemoryCurrent"], "resources")
            cpu_usage = self._systemd_counter(properties["CPUUsageNSec"], "resources")
            tasks_current = self._systemd_counter(properties["TasksCurrent"], "resources")
            rows.append(
                {
                    "cpu_usage_nsec": cpu_usage,
                    "memory_current_bytes": memory_current,
                    "memory_max_bytes": self._systemd_counter(properties["MemoryMax"], "resources"),
                    "tasks_current": tasks_current,
                    "tasks_max": self._systemd_counter(properties["TasksMax"], "resources"),
                    "unit_name": unit_name,
                }
            )
        return rows

    def mount_capacity_facts(self) -> list[JsonValue]:
        """Read capacity and inode availability for exactly the required storage paths."""
        rows: list[JsonValue] = []
        for path in _REQUIRED_PATHS:
            values = os.statvfs(path)
            rows.append(
                {
                    "available_bytes": values.f_bavail * values.f_frsize,
                    "inode_available": values.f_favail,
                    "inode_total": values.f_files,
                    "path": path,
                    "total_bytes": values.f_blocks * values.f_frsize,
                }
            )
        return rows

    @staticmethod
    def _observed_at(now: datetime) -> str:
        return now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _freshness(root: Path, now_ns: int) -> dict[str, JsonValue]:
        files = _strict_regular_files(root, recursive=True, reject_symlinks=True)
        if not files:
            return {
                "age_seconds": None,
                "file_count": 0,
                "latest_mtime_ns": None,
                "present": False,
                "root": root.as_posix(),
                "total_bytes": 0,
            }
        metadata = [os.lstat(path) for path in files]
        latest = max(item.st_mtime_ns for item in metadata)
        return {
            "age_seconds": max(0, (now_ns - latest) // 1_000_000_000),
            "file_count": len(files),
            "latest_mtime_ns": latest,
            "present": True,
            "root": root.as_posix(),
            "total_bytes": sum(item.st_size for item in metadata),
        }

    def backup_freshness_facts(self) -> dict[str, JsonValue]:
        """Inspect only file metadata under the two exact local backup roots."""
        now = datetime.now(UTC)
        now_ns = int(now.timestamp() * 1_000_000_000)
        return {
            "backups": [
                {
                    "backup_class": backup_class,
                    "freshness": self._freshness(Path(root), now_ns),
                }
                for backup_class, root in _BACKUP_ROOTS
            ],
            "observed_at": self._observed_at(now),
        }

    def scheduler_identity_facts(self) -> list[JsonValue]:
        """Inspect exact scheduler container identities without reading configuration values."""
        rows: list[JsonValue] = []
        for scheduler_id, container_name in _SCHEDULERS:
            inspected = self._inspect_container(container_name)
            rows.append(
                {
                    "container_id": None if inspected is None else inspected["container_id"],
                    "container_name": container_name,
                    "image_id": None if inspected is None else inspected["image_id"],
                    "present": inspected is not None,
                    "scheduler_id": scheduler_id,
                }
            )
        return rows

    def telemetry_freshness_facts(self) -> dict[str, JsonValue]:
        """Inspect only metadata under the exact retained telemetry root."""
        now = datetime.now(UTC)
        now_ns = int(now.timestamp() * 1_000_000_000)
        return {
            "freshness": self._freshness(_TELEMETRY_ROOT, now_ns),
            "observed_at": self._observed_at(now),
        }

    def application_readiness_facts(self) -> list[JsonValue]:
        """Combine exact systemd activity with Docker-owned health state for five apps."""
        rows: list[JsonValue] = []
        for application_id, container_name, systemd_unit in _APPLICATIONS:
            unit = self._unit_state(systemd_unit)
            inspected = self._inspect_container(container_name)
            rows.append(
                {
                    "active_state": unit["active_state"],
                    "application_id": application_id,
                    "container_name": container_name,
                    "health": "UNKNOWN" if inspected is None else inspected["health"],
                    "systemd_unit": systemd_unit,
                }
            )
        return rows

    def _foreign_networks(self, declared: set[str]) -> list[JsonValue]:
        """Return every non-loopback IPv4 host network that is not a declared subnet."""
        declared_networks = {ipaddress.IPv4Network(value, strict=True) for value in declared}
        interfaces = _json_objects(json.loads(self._run(("ip", "-json", "addr", "show"))), "ip")
        foreign: set[str] = set()
        malformed = "ip"
        for interface in interfaces:
            ifname = interface.get("ifname")
            addresses = interface.get("addr_info")
            if type(ifname) is not str or type(addresses) is not list:
                raise TypeError(malformed)
            for raw_address in cast("list[object]", addresses):
                address = _string_object(raw_address)
                if address is None:
                    raise TypeError(malformed)
                family = address.get("family")
                if type(family) is not str:
                    raise TypeError(malformed)
                if family != "inet":
                    continue
                local = address.get("local")
                prefix = address.get("prefixlen")
                if type(local) is not str or type(prefix) is not int:
                    raise TypeError(malformed)
                cidr = _ipv4_interface(f"{local}/{prefix}", "ip")
                if (
                    ifname != "lo"
                    and ipaddress.IPv4Interface(cidr).network not in declared_networks
                ):
                    foreign.add(cidr)
        result: list[JsonValue] = []
        result.extend(sorted(foreign))
        return result


def collect_host_facts(source: HostFactsSource) -> dict[str, JsonValue]:
    """Build the exact secret-free fact document consumed by host admission."""
    return {
        "schema_version": 1,
        "source": "READ_ONLY_HOST_FACTS",
        "os": source.operating_system(),
        "architecture": source.architecture(),
        "memory_bytes": source.memory_bytes(),
        "physical_disks": source.physical_disks(),
        "paths": source.path_facts(),
        "time": source.time_facts(),
        "credentials": source.credential_facts(),
        "firewall": source.firewall_facts(),
        "journal": source.journal_facts(),
        "container_runtime": source.container_runtime_facts(),
        "host_packages": source.host_package_facts(),
        "private_subnets": source.observed_network_facts(),
        "kernel": source.kernel_facts(),
        "systemd": source.systemd_facts(),
        "containers": source.container_facts(),
        "listeners": source.listener_facts(),
        "resources": source.resource_facts(),
        "mount_capacity": source.mount_capacity_facts(),
        "backup_freshness": source.backup_freshness_facts(),
        "schedulers": source.scheduler_identity_facts(),
        "telemetry": source.telemetry_freshness_facts(),
        "applications": source.application_readiness_facts(),
    }


def collect_hk_v1_host_facts(source: HostFactsSource) -> HKV1HostFacts:
    """Collect every existing probe independently and expose remaining Plan 8 gaps."""
    facts: dict[str, object] = {
        "schema_version": 1,
        "source": "READ_ONLY_HOST_FACTS",
    }
    probes: tuple[tuple[str, HostFactClass, Callable[[], object]], ...] = (
        ("os", HostFactClass.OS_KERNEL, source.operating_system),
        ("architecture", HostFactClass.OS_KERNEL, source.architecture),
        ("memory_bytes", HostFactClass.RESOURCES, source.memory_bytes),
        (
            "physical_disks",
            HostFactClass.FILESYSTEM_CAPACITY,
            source.physical_disks,
        ),
        ("paths", HostFactClass.FILESYSTEM_CAPACITY, source.path_facts),
        ("time", HostFactClass.OS_KERNEL, source.time_facts),
        (
            "credentials",
            HostFactClass.CREDENTIAL_METADATA,
            source.credential_facts,
        ),
        ("firewall", HostFactClass.NETWORK_POLICY, source.firewall_facts),
        (
            "journal",
            HostFactClass.TELEMETRY_FRESHNESS,
            source.journal_facts,
        ),
        (
            "container_runtime",
            HostFactClass.CONTAINERS_IMAGES_HEALTH,
            source.container_runtime_facts,
        ),
        ("host_packages", HostFactClass.OS_KERNEL, source.host_package_facts),
        (
            "private_subnets",
            HostFactClass.NETWORK_POLICY,
            source.observed_network_facts,
        ),
        ("kernel", HostFactClass.OS_KERNEL, source.kernel_facts),
        ("systemd", HostFactClass.SYSTEMD_UNITS_TIMERS, source.systemd_facts),
        (
            "containers",
            HostFactClass.CONTAINERS_IMAGES_HEALTH,
            source.container_facts,
        ),
        ("listeners", HostFactClass.NETWORK_POLICY, source.listener_facts),
        ("resources", HostFactClass.RESOURCES, source.resource_facts),
        (
            "mount_capacity",
            HostFactClass.FILESYSTEM_CAPACITY,
            source.mount_capacity_facts,
        ),
        (
            "backup_freshness",
            HostFactClass.BACKUP_FRESHNESS,
            source.backup_freshness_facts,
        ),
        (
            "schedulers",
            HostFactClass.SCHEDULER_IDENTITIES,
            source.scheduler_identity_facts,
        ),
        (
            "telemetry",
            HostFactClass.TELEMETRY_FRESHNESS,
            source.telemetry_freshness_facts,
        ),
        (
            "applications",
            HostFactClass.APPLICATION_READINESS,
            source.application_readiness_facts,
        ),
    )
    first_failure: dict[HostFactClass, HostFactFailureCode] = {}
    successful: dict[HostFactClass, int] = {}
    expected: dict[HostFactClass, int] = {}
    for key, fact_class, callback in probes:
        expected[fact_class] = expected.get(fact_class, 0) + 1
        boundary = _ProbeBoundary()
        snapshot: object | None = None
        with boundary:
            snapshot = _validate_probe_result(key, callback())
        if boundary.failure_code is None:
            facts[key] = snapshot
            successful[fact_class] = successful.get(fact_class, 0) + 1
        elif fact_class not in first_failure:
            first_failure[fact_class] = boundary.failure_code

    outcomes: list[HostFactClassOutcome] = []
    for fact_class in sorted(HostFactClass, key=lambda item: item.value):
        failure = first_failure.get(fact_class)
        collected = failure is None and successful.get(fact_class, 0) == expected.get(fact_class, 0)
        outcomes.append(
            HostFactClassOutcome(
                fact_class,
                collected,
                None if collected else failure or HostFactFailureCode.NOT_IMPLEMENTED,
            )
        )
    return build_hk_v1_host_facts(legacy_facts=facts, outcomes=tuple(outcomes))


def _canonical_envelope_bytes(envelope: HKV1HostFacts) -> bytes:
    return (
        json.dumps(
            host_facts_document(envelope),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _ensure_private_output_parent(parent: Path) -> None:
    """Create only missing lexical parent components and never follow an alias."""
    current = Path(parent.anchor) if parent.is_absolute() else Path.cwd()
    parts = parent.parts[1:] if parent.is_absolute() else parent.parts
    for part in parts:
        if part in {"", "."}:
            continue
        if part == "..":
            message = "HOST_FACTS_OUTPUT_FAILED"
            raise HostFactsOutputError(message)
        current /= part
        created = False
        try:
            status = os.lstat(current)
        except FileNotFoundError:
            current.mkdir(mode=_PRIVATE_DIRECTORY_MODE)
            current.chmod(_PRIVATE_DIRECTORY_MODE, follow_symlinks=False)
            status = os.lstat(current)
            created = True
        if (
            not stat.S_ISDIR(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or (created and stat.S_IMODE(status.st_mode) != _PRIVATE_DIRECTORY_MODE)
        ):
            message = "HOST_FACTS_OUTPUT_FAILED"
            raise HostFactsOutputError(message)


def _validate_output(output: Path) -> None:
    try:
        _ensure_private_output_parent(output.parent)
        parent_status = os.lstat(output.parent)
        try:
            output_status = os.lstat(output)
        except FileNotFoundError:
            output_status = None
    except OSError:
        message = "HOST_FACTS_OUTPUT_FAILED"
        raise HostFactsOutputError(message) from None
    if (
        not stat.S_ISDIR(parent_status.st_mode)
        or not output.name
        or (output_status is not None and not stat.S_ISREG(output_status.st_mode))
    ):
        message = "HOST_FACTS_OUTPUT_FAILED"
        raise HostFactsOutputError(message)


def write_host_facts_output(envelope: HKV1HostFacts, output: Path) -> None:
    """Write canonical facts by private same-directory atomic replacement."""
    temporary_path: Path | None = None
    try:
        _validate_output(output)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=output.parent,
            prefix=f".{output.name}.",
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_envelope_bytes(envelope))
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(output)
        temporary_path = None
    except HostFactsOutputError:
        raise
    except _OUTPUT_FAILURES:
        message = "HOST_FACTS_OUTPUT_FAILED"
        raise HostFactsOutputError(message) from None
    finally:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--acknowledge-read-only-host-inspection",
        action="store_true",
        help="required acknowledgement; performs no provisioning or credential reads",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    """Write facts only after explicit read-only inspection acknowledgement."""
    arguments = _parser().parse_args()
    if not arguments.acknowledge_read_only_host_inspection:
        message = "explicit read-only host-inspection acknowledgement required"
        raise SystemExit(message)
    envelope = collect_hk_v1_host_facts(UbuntuHostFactsSource())
    write_host_facts_output(envelope, arguments.output)
    print("PASS READ_ONLY_HOST_FACTS_WRITTEN")  # noqa: T201


if __name__ == "__main__":
    main()
