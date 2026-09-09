"""Tests for the bounded read-only Ubuntu host-fact collector."""

import json
import os
import stat
import subprocess
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from tools.v1_poc_collect_host_facts import (
    HKV1HostFacts,
    HostFactAbsent,
    HostFactClass,
    HostFactFailureCode,
    HostFactsOutputError,
    UbuntuHostFactsSource,
    collect_hk_v1_host_facts,
    collect_host_facts,
    host_facts_document,
    load_host_facts_output,
    main,
    parse_host_facts_output_bytes,
    parse_os_release,
    validated_complete_host_facts,
    write_host_facts_output,
)
from tools.v1_poc_host_admission import evaluate_host_facts

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_UNITS = (
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
_TIMER_UNITS = (
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


def _unit(unit_name: str) -> dict[str, JsonValue]:
    return {
        "active_state": "active",
        "load_state": "loaded",
        "sub_state": "running",
        "unit_file_state": "enabled",
        "unit_name": unit_name,
    }


def test_canonical_host_facts_bytes_round_trip_without_a_filesystem_loader() -> None:
    """Downstream evidence validators can consume the collector's exact bytes."""
    envelope = collect_hk_v1_host_facts(_FakeSource())
    raw = (
        json.dumps(
            host_facts_document(envelope),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )

    parsed = parse_host_facts_output_bytes(raw)

    assert host_facts_document(parsed) == host_facts_document(envelope)
    assert validated_complete_host_facts(parsed)["kernel"] == envelope.legacy_facts["kernel"]


def _mapping(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast("dict[str, object]", value)


def _items(value: object) -> list[object]:
    assert type(value) is list
    return cast("list[object]", value)


def _policy() -> dict[str, object]:
    value: object = json.loads(
        (REPOSITORY_ROOT / "infrastructure/poc/host_admission_policy.json").read_bytes()
    )
    assert isinstance(value, dict)
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


class _FakeSource:
    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()

    def _called(self, name: str) -> None:
        self.calls[name] += 1

    def operating_system(self) -> dict[str, JsonValue]:
        self._called("operating_system")
        return {"id": "ubuntu", "version_id": "24.04"}

    def architecture(self) -> str:
        self._called("architecture")
        return "x86_64"

    def memory_bytes(self) -> int:
        self._called("memory_bytes")
        return 68_719_476_736

    def physical_disks(self) -> list[JsonValue]:
        self._called("physical_disks")
        return [
            {"stable_id": "disk:poc", "size_bytes": 4_000_787_030_016},
            {"stable_id": "disk:poc-root", "size_bytes": 500_107_862_016},
            {"stable_id": "disk:poc-spare", "size_bytes": 500_107_862_016},
        ]

    def path_facts(self) -> list[JsonValue]:
        self._called("path_facts")
        return [
            {
                "path": path,
                "real_path": path,
                "fs_type": "ext4",
                "physical_disk_id": "disk:poc",
                "symlink": False,
                "writable": True,
            }
            for path in (
                "/srv/asklegal/sql",
                "/srv/asklegal/vault-primary",
                "/srv/asklegal/vault-recovery",
            )
        ]

    def time_facts(self) -> dict[str, JsonValue]:
        self._called("time_facts")
        return {"synchronized": True}

    def credential_facts(self) -> dict[str, JsonValue]:
        self._called("credential_facts")
        return {
            "systemd_creds_available": True,
            "protection_mode": "TPM2_PLUS_HOST_KEY",
            "encrypted_blob_mode": "0400",
            "persistent_plaintext_credential_paths": [],
        }

    def firewall_facts(self) -> dict[str, JsonValue]:
        self._called("firewall_facts")
        return {
            "nftables_available": True,
            "input_default": "DROP",
            "forward_default": "DROP",
            "direct_container_egress_default": "DROP",
            "public_tcp_ports": [],
        }

    def journal_facts(self) -> dict[str, JsonValue]:
        self._called("journal_facts")
        return {"storage": "PERSISTENT", "forward_secure_sealing": True}

    def container_runtime_facts(self) -> dict[str, JsonValue]:
        self._called("container_runtime_facts")
        return {
            "name": "docker",
            "service_manager": "systemd",
            "docker_group_non_root_members": ["docpro"],
        }

    def host_package_facts(self) -> dict[str, JsonValue]:
        self._called("host_package_facts")
        return {
            "ca-certificates": "20260601~24.04.1",
            "containerd.io": "2.3.3-1~ubuntu.24.04~noble",
            "docker-ce": "5:29.7.2-1~ubuntu.24.04~noble",
            "docker-ce-cli": "5:29.7.2-1~ubuntu.24.04~noble",
            "e2fsprogs": "1.47.0-2.4~exp1ubuntu4.1",
            "nftables": "1.0.9-1ubuntu0.1",
            "systemd": "255.4-1ubuntu8.17",
            "systemd-timesyncd": "255.4-1ubuntu8.17",
            "util-linux": "2.39.3-9ubuntu6.6",
        }

    def observed_network_facts(self) -> dict[str, JsonValue]:
        self._called("observed_network_facts")
        return {
            "declared": {
                "asklegal-register": "10.90.0.0/24",
                "asklegal-scheduler-general": "10.90.1.0/24",
                "asklegal-scheduler-promotion": "10.90.2.0/24",
                "asklegal-vault-primary": "10.90.3.0/24",
                "asklegal-vault-recovery": "10.90.4.0/24",
                "asklegal-review": "10.90.5.0/24",
                "asklegal-telemetry": "10.90.6.0/24",
                "asklegal-egress-source": "10.90.7.0/24",
                "asklegal-egress-model": "10.90.8.0/24",
                "asklegal-egress-promotion": "10.90.9.0/24",
            },
            "foreign": ["172.17.0.1/16", "192.168.9.126/22", "10.2.0.2/32"],
        }

    def kernel_facts(self) -> dict[str, JsonValue]:
        self._called("kernel_facts")
        return {"boot_id_fingerprint": "sha256:" + "a" * 64, "release": "6.8.0-79-generic"}

    def systemd_facts(self) -> dict[str, JsonValue]:
        self._called("systemd_facts")
        return {
            "target": _unit("asklegal.target"),
            "service_units": [_unit(name) for name in _SERVICE_UNITS],
            "timer_units": [_unit(name) for name in _TIMER_UNITS],
        }

    def container_facts(self) -> list[JsonValue]:
        self._called("container_facts")
        return [
            {
                "health": "HEALTHY",
                "image_id": "sha256:" + "b" * 64,
                "name": "asklegal-control-plane",
                "runtime_state": "running",
            }
        ]

    def listener_facts(self) -> list[JsonValue]:
        self._called("listener_facts")
        return [{"address": "127.0.0.1", "port": 8000, "public": False, "transport": "TCP"}]

    def resource_facts(self) -> list[JsonValue]:
        self._called("resource_facts")
        return [
            {
                "cpu_usage_nsec": 1,
                "memory_current_bytes": 1,
                "memory_max_bytes": 1_000_000,
                "tasks_current": 1,
                "tasks_max": 100,
                "unit_name": name,
            }
            for name in _SERVICE_UNITS
        ]

    def mount_capacity_facts(self) -> list[JsonValue]:
        self._called("mount_capacity_facts")
        return [
            {
                "available_bytes": 1_000_000,
                "inode_available": 1_000,
                "inode_total": 2_000,
                "path": path,
                "total_bytes": 2_000_000,
            }
            for path in (
                "/srv/asklegal/sql",
                "/srv/asklegal/vault-primary",
                "/srv/asklegal/vault-recovery",
            )
        ]

    def backup_freshness_facts(self) -> dict[str, JsonValue]:
        self._called("backup_freshness_facts")
        return {
            "backups": [
                {
                    "backup_class": backup_class,
                    "freshness": {
                        "age_seconds": 60,
                        "file_count": 1,
                        "latest_mtime_ns": 1,
                        "present": True,
                        "root": root,
                        "total_bytes": 1,
                    },
                }
                for backup_class, root in (
                    ("NATIVE", "/var/lib/asklegal/promotion-backup-native"),
                    ("RECOVERY", "/var/lib/asklegal/promotion-backup-recovery"),
                )
            ],
            "observed_at": "2026-09-08T00:00:00Z",
        }

    def scheduler_identity_facts(self) -> list[JsonValue]:
        self._called("scheduler_identity_facts")
        return [
            {
                "container_id": "container-" + scheduler_id.lower(),
                "container_name": container_name,
                "image_id": "sha256:" + fingerprint * 64,
                "present": True,
                "scheduler_id": scheduler_id,
            }
            for scheduler_id, container_name, fingerprint in (
                ("GENERAL", "asklegal-dts-general", "c"),
                ("PROMOTION", "asklegal-dts-promotion", "d"),
            )
        ]

    def telemetry_freshness_facts(self) -> dict[str, JsonValue]:
        self._called("telemetry_freshness_facts")
        return {
            "freshness": {
                "age_seconds": 30,
                "file_count": 1,
                "latest_mtime_ns": 1,
                "present": True,
                "root": "/var/lib/asklegal/control/telemetry",
                "total_bytes": 1,
            },
            "observed_at": "2026-09-08T00:00:00Z",
        }

    def application_readiness_facts(self) -> list[JsonValue]:
        self._called("application_readiness_facts")
        return [
            {
                "active_state": "active",
                "application_id": application_id,
                "container_name": container_name,
                "health": "HEALTHY",
                "systemd_unit": systemd_unit,
            }
            for application_id, container_name, systemd_unit in _APPLICATIONS
        ]


def complete_fake_host_facts() -> HKV1HostFacts:
    """Return the closed complete fake used by cross-tool owner-artifact tests."""
    return collect_hk_v1_host_facts(_FakeSource())


def test_collected_facts_match_the_exact_admission_boundary_but_do_not_admit() -> None:
    """Generate every declared fact once without clearing durable blockers."""
    source = _FakeSource()
    facts = collect_host_facts(source)
    facts_object: dict[str, object] = dict(facts)
    result = evaluate_host_facts(_policy(), facts_object)
    assert result.facts_conform is True
    assert result.admitted is False
    assert result.findings == ()
    assert source.calls == Counter(
        {
            "operating_system": 1,
            "architecture": 1,
            "memory_bytes": 1,
            "physical_disks": 1,
            "path_facts": 1,
            "time_facts": 1,
            "credential_facts": 1,
            "firewall_facts": 1,
            "journal_facts": 1,
            "container_runtime_facts": 1,
            "host_package_facts": 1,
            "observed_network_facts": 1,
            "kernel_facts": 1,
            "systemd_facts": 1,
            "container_facts": 1,
            "listener_facts": 1,
            "resource_facts": 1,
            "mount_capacity_facts": 1,
            "backup_freshness_facts": 1,
            "scheduler_identity_facts": 1,
            "telemetry_freshness_facts": 1,
            "application_readiness_facts": 1,
        }
    )
    packages = facts["host_packages"]
    assert isinstance(packages, dict)
    assert packages["systemd"] == "255.4-1ubuntu8.17"
    networks = facts["private_subnets"]
    assert isinstance(networks, dict)
    assert set(networks) == {"declared", "foreign"}


def test_canonical_saved_envelope_round_trips_and_pretty_json_is_rejected(
    tmp_path: Path,
) -> None:
    """The admission and reconcile CLIs consume only collector-issued canonical bytes."""
    envelope = collect_hk_v1_host_facts(_FakeSource())
    output = tmp_path / "facts.json"
    write_host_facts_output(envelope, output)

    assert host_facts_document(load_host_facts_output(output)) == host_facts_document(envelope)

    output.write_text(json.dumps(host_facts_document(envelope), indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="HOST_FACT_ENVELOPE_INVALID"):
        load_host_facts_output(output)


def test_os_release_parser_is_bounded_to_declared_key_value_facts() -> None:
    """Ignore comments and preserve quoted Ubuntu identity fields exactly."""
    assert parse_os_release('# comment\nID="ubuntu"\nVERSION_ID="24.04"\n') == {
        "ID": "ubuntu",
        "VERSION_ID": "24.04",
    }


def test_non_linux_collection_fails_before_any_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never pretend that facts collected on the development Mac describe Ubuntu."""
    monkeypatch.setattr("tools.v1_poc_collect_host_facts.platform.system", lambda: "Darwin")
    with pytest.raises(RuntimeError, match="requires Linux"):
        UbuntuHostFactsSource()


def test_network_permission_failure_is_sanitized_and_does_not_stop_later_probes() -> None:
    """A denied nft probe must name only its class and still collect later safe facts."""
    source = _FakeSource()

    def denied_firewall() -> dict[str, JsonValue]:
        source.calls["firewall_facts"] += 1
        detail = "secret nft stderr and command"
        raise PermissionError(detail)

    source.firewall_facts = denied_firewall
    envelope = collect_hk_v1_host_facts(source)

    assert envelope.complete is False
    assert HostFactClass.NETWORK_POLICY in envelope.missing_fact_classes
    failure = next(
        item for item in envelope.failures if item.fact_class is HostFactClass.NETWORK_POLICY
    )
    assert failure.code is HostFactFailureCode.PERMISSION_DENIED
    assert source.calls["observed_network_facts"] == 1
    assert source.calls["host_package_facts"] == 1
    rendered = json.dumps(host_facts_document(envelope), sort_keys=True)
    assert "secret nft stderr" not in rendered
    assert "stderr and command" not in rendered


def test_command_permission_denial_is_classified_before_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-zero nft permission result must not degrade into generic probe failure."""

    class PermissionAwareSource(_FakeSource, UbuntuHostFactsSource):
        def firewall_facts(self) -> dict[str, JsonValue]:
            self._run(("nft", "--json", "list", "ruleset"))
            raise AssertionError

    def denied_command(
        command: Sequence[str],
        **options: object,
    ) -> subprocess.CompletedProcess[str]:
        del options
        return subprocess.CompletedProcess(
            command,
            returncode=1,
            stdout="",
            stderr="Operation not permitted: private nft detail",
        )

    monkeypatch.setattr(
        "tools.v1_poc_collect_host_facts.subprocess.run",
        denied_command,
    )
    envelope = collect_hk_v1_host_facts(PermissionAwareSource())
    failure = next(
        item for item in envelope.failures if item.fact_class is HostFactClass.NETWORK_POLICY
    )

    assert failure.code is HostFactFailureCode.PERMISSION_DENIED
    assert "private nft detail" not in json.dumps(host_facts_document(envelope), sort_keys=True)


def test_proved_command_object_absence_is_not_a_generic_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exact missing Docker object remains distinct from unreadable state."""

    class AbsenceAwareSource(_FakeSource, UbuntuHostFactsSource):
        def firewall_facts(self) -> dict[str, JsonValue]:
            result = self._absent_or_run(("docker", "network", "inspect", "missing"))
            assert result is None
            raise HostFactAbsent

    def absent_command(
        command: Sequence[str],
        **options: object,
    ) -> subprocess.CompletedProcess[str]:
        del options
        return subprocess.CompletedProcess(
            command,
            returncode=1,
            stdout="",
            stderr="Error: No such network: missing",
        )

    monkeypatch.setattr(
        "tools.v1_poc_collect_host_facts.subprocess.run",
        absent_command,
    )
    envelope = collect_hk_v1_host_facts(AbsenceAwareSource())
    failure = next(
        item for item in envelope.failures if item.fact_class is HostFactClass.NETWORK_POLICY
    )

    assert failure.code is HostFactFailureCode.NOT_FOUND


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (PermissionError("private path"), HostFactFailureCode.PERMISSION_DENIED),
        (
            subprocess.TimeoutExpired(("private", "command"), 10),
            HostFactFailureCode.TIMEOUT,
        ),
        (ValueError("malformed raw output"), HostFactFailureCode.MALFORMED_OUTPUT),
        (HostFactAbsent(), HostFactFailureCode.NOT_FOUND),
    ],
)
def test_probe_failure_kinds_remain_distinct_without_raw_details(
    failure: Exception,
    expected: HostFactFailureCode,
) -> None:
    """Permission, timeout, malformed output, and true absence are not aliases."""
    source = _FakeSource()

    def failed_credentials() -> dict[str, JsonValue]:
        raise failure

    source.credential_facts = failed_credentials
    envelope = collect_hk_v1_host_facts(source)
    result = next(
        item for item in envelope.failures if item.fact_class is HostFactClass.CREDENTIAL_METADATA
    )

    assert result.code is expected
    assert repr(failure) not in json.dumps(host_facts_document(envelope), sort_keys=True)


def test_all_eleven_classes_are_complete_sorted_and_deterministic() -> None:
    """Every Plan 8 class is independently validated into a deterministic envelope."""
    first = collect_hk_v1_host_facts(_FakeSource())
    second = collect_hk_v1_host_facts(_FakeSource())

    assert first.missing_fact_classes == ()
    assert first.complete is True
    assert tuple(item.value for item in first.collected_fact_classes) == tuple(
        sorted(item.value for item in HostFactClass)
    )
    assert host_facts_document(first) == host_facts_document(second)


def test_arbitrary_ordinary_failure_is_sanitized_but_base_exception_propagates() -> None:
    """Catch all ordinary probe failures without hiding process-control signals."""

    class CustomProbeFailure(Exception):
        pass

    source = _FakeSource()

    def custom_failure() -> dict[str, JsonValue]:
        detail = "private callback detail"
        raise CustomProbeFailure(detail)

    source.credential_facts = custom_failure
    envelope = collect_hk_v1_host_facts(source)
    failure = next(
        item for item in envelope.failures if item.fact_class is HostFactClass.CREDENTIAL_METADATA
    )
    assert failure.code is HostFactFailureCode.PROBE_FAILED

    def interrupting_callback(
        process_control: BaseException,
    ) -> Callable[[], dict[str, JsonValue]]:
        def interrupt() -> dict[str, JsonValue]:
            raise process_control

        return interrupt

    for process_control in (KeyboardInterrupt(), SystemExit(7)):
        interrupted = _FakeSource()
        interrupted.credential_facts = interrupting_callback(process_control)
        with pytest.raises(type(process_control)):
            collect_hk_v1_host_facts(interrupted)


def test_callback_mutation_cannot_change_an_already_snapshotted_fact() -> None:
    """A later callback cannot rewrite the earlier accepted firewall result."""
    source = _FakeSource()
    firewall = source.firewall_facts()

    def return_firewall() -> dict[str, JsonValue]:
        return firewall

    original_networks = source.observed_network_facts

    def mutate_then_return_networks() -> dict[str, JsonValue]:
        firewall["input_default"] = "ACCEPT"
        return original_networks()

    source.firewall_facts = return_firewall
    source.observed_network_facts = mutate_then_return_networks
    envelope = collect_hk_v1_host_facts(source)

    accepted = envelope.legacy_facts
    accepted_firewall = accepted["firewall"]
    assert isinstance(accepted_firewall, dict)
    assert accepted_firewall["input_default"] == "DROP"
    assert firewall["input_default"] == "ACCEPT"


def test_secret_shaped_callback_value_is_rejected_before_retention() -> None:
    """A callback cannot place a credential value inside retained host facts."""
    source = _FakeSource()

    def unsafe_credentials() -> dict[str, JsonValue]:
        return {"token": "sk-private-host-fact"}

    source.credential_facts = unsafe_credentials
    envelope = collect_hk_v1_host_facts(source)
    failure = next(
        item for item in envelope.failures if item.fact_class is HostFactClass.CREDENTIAL_METADATA
    )

    assert failure.code is HostFactFailureCode.MALFORMED_OUTPUT
    assert "sk-private-host-fact" not in json.dumps(host_facts_document(envelope), sort_keys=True)


_MALFORMED_PROBE_VALUES: list[tuple[str, object, HostFactClass]] = [
    ("operating_system", None, HostFactClass.OS_KERNEL),
    ("operating_system", {}, HostFactClass.OS_KERNEL),
    ("operating_system", {"id": "ubuntu"}, HostFactClass.OS_KERNEL),
    (
        "operating_system",
        {"id": "ubuntu", "version_id": "24.04", "command": "id"},
        HostFactClass.OS_KERNEL,
    ),
    ("architecture", "sk-private-host-fact", HostFactClass.OS_KERNEL),
    ("memory_bytes", True, HostFactClass.RESOURCES),
    ("physical_disks", [{}], HostFactClass.FILESYSTEM_CAPACITY),
    ("path_facts", [{"path": "/srv/asklegal/sql"}], HostFactClass.FILESYSTEM_CAPACITY),
    ("time_facts", {"synchronized": 1}, HostFactClass.OS_KERNEL),
    (
        "credential_facts",
        {
            "systemd_creds_available": True,
            "protection_mode": "TPM2_PLUS_HOST_KEY",
            "encrypted_blob_mode": "0400",
            "persistent_plaintext_credential_paths": [],
            "client_secret": "private",
        },
        HostFactClass.CREDENTIAL_METADATA,
    ),
    (
        "credential_facts",
        {
            "systemd_creds_available": True,
            "protection_mode": "postgres://user:private@host/db",
            "encrypted_blob_mode": "0400",
            "persistent_plaintext_credential_paths": [],
        },
        HostFactClass.CREDENTIAL_METADATA,
    ),
    ("firewall_facts", {"nftables_available": True}, HostFactClass.NETWORK_POLICY),
    ("journal_facts", {"storage": "PERSISTENT"}, HostFactClass.TELEMETRY_FRESHNESS),
    ("container_runtime_facts", {"name": "docker"}, HostFactClass.CONTAINERS_IMAGES_HEALTH),
    ("host_package_facts", {"PATH": "/private/bin"}, HostFactClass.OS_KERNEL),
    (
        "observed_network_facts",
        {"declared": {}, "foreign": ["not-a-cidr"]},
        HostFactClass.NETWORK_POLICY,
    ),
    ("kernel_facts", {"release": "6.8.0"}, HostFactClass.OS_KERNEL),
    ("systemd_facts", {}, HostFactClass.SYSTEMD_UNITS_TIMERS),
    ("container_facts", [{"name": "unsafe"}], HostFactClass.CONTAINERS_IMAGES_HEALTH),
    ("listener_facts", [{"address": "secret"}], HostFactClass.NETWORK_POLICY),
    ("resource_facts", [], HostFactClass.RESOURCES),
    ("mount_capacity_facts", [], HostFactClass.FILESYSTEM_CAPACITY),
    ("backup_freshness_facts", {}, HostFactClass.BACKUP_FRESHNESS),
    ("scheduler_identity_facts", [], HostFactClass.SCHEDULER_IDENTITIES),
    ("telemetry_freshness_facts", {}, HostFactClass.TELEMETRY_FRESHNESS),
    ("application_readiness_facts", [], HostFactClass.APPLICATION_READINESS),
]


@pytest.mark.parametrize(
    ("method", "value", "fact_class"),
    _MALFORMED_PROBE_VALUES,
)
def test_each_probe_has_a_closed_exact_schema(
    method: str,
    value: object,
    fact_class: HostFactClass,
) -> None:
    """Partial, extra, wrong-type, command, environment, and secret data never collect."""
    source = _FakeSource()
    setattr(source, method, lambda: value)

    envelope = collect_hk_v1_host_facts(source)

    failure = next(item for item in envelope.failures if item.fact_class is fact_class)
    assert failure.code is HostFactFailureCode.MALFORMED_OUTPUT
    rendered = json.dumps(host_facts_document(envelope), sort_keys=True)
    assert "client_secret" not in rendered
    assert "postgres://" not in rendered
    assert "/private/bin" not in rendered
    assert "sk-private-host-fact" not in rendered


def test_empty_physical_disk_collection_is_malformed_and_never_retained() -> None:
    """An empty successful callback cannot masquerade as a storage observation."""
    source = _FakeSource()

    def no_disks() -> list[JsonValue]:
        return []

    source.physical_disks = no_disks

    envelope = collect_hk_v1_host_facts(source)

    failure = next(
        item for item in envelope.failures if item.fact_class is HostFactClass.FILESYSTEM_CAPACITY
    )
    assert failure.code is HostFactFailureCode.MALFORMED_OUTPUT
    assert "physical_disks" not in envelope.legacy_facts


def test_hostile_callback_containers_are_rejected_without_invoking_them() -> None:
    """Reject container subclasses before an iterator or property can execute."""

    class HostileList(list[object]):
        def __iter__(self) -> Iterator[object]:
            message = "hostile iterator executed"
            raise AssertionError(message)

    class HostileObject:
        @property
        def token(self) -> str:
            message = "hostile property executed"
            raise AssertionError(message)

    for value in (HostileList(), HostileObject()):
        source = _FakeSource()
        source.credential_facts = lambda value=value: value  # type: ignore[method-assign,return-value]
        envelope = collect_hk_v1_host_facts(source)
        failure = next(
            item
            for item in envelope.failures
            if item.fact_class is HostFactClass.CREDENTIAL_METADATA
        )
        assert failure.code is HostFactFailureCode.MALFORMED_OUTPUT


def _ubuntu_source_without_init() -> UbuntuHostFactsSource:
    return object.__new__(UbuntuHostFactsSource)


def test_ubuntu_systemd_resource_container_listener_and_readiness_probes_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New command probes request only explicit metadata and normalize exact safe fields."""
    source = _ubuntu_source_without_init()
    container_id = "a" * 64

    def scripted(command: Sequence[str]) -> str:
        if command[:2] == ("systemctl", "show"):
            requested = command[3].removeprefix("--property=").split(",")
            values = {
                "ActiveState": "active",
                "CPUUsageNSec": "10",
                "LoadState": "loaded",
                "MemoryCurrent": "20",
                "MemoryMax": "infinity",
                "SubState": "running",
                "TasksCurrent": "2",
                "TasksMax": "100",
                "UnitFileState": "enabled",
            }
            return "\n".join(f"{name}={values[name]}" for name in requested)
        if command[:4] == ("docker", "container", "ls", "--all"):
            return container_id
        if command[:2] == ("docker", "inspect"):
            identity = command[-1]
            return json.dumps(
                {
                    "Id": container_id,
                    "Image": "sha256:" + "b" * 64,
                    "Name": "/" + identity,
                    "State": {"Health": {"Status": "healthy"}, "Status": "running"},
                }
            )
        raise AssertionError(command)

    source._run = scripted  # type: ignore[method-assign]  # noqa: SLF001
    socket_tables = {
        "tcp": b"sl local_address rem_address st\n0: 0100007F:1F40 00000000:0000 0A\n",
        "tcp6": b"sl local_address rem_address st\n",
        "udp": b"sl local_address rem_address st\n",
        "udp6": (
            b"sl local_address rem_address st\n"
            b"0: 00000000000000000000000000000000:10DD "
            b"00000000000000000000000000000000:0000 07\n"
        ),
    }

    def read_socket_table(path: Path) -> bytes:
        return socket_tables[path.name]

    monkeypatch.setattr(Path, "read_bytes", read_socket_table)

    systemd = source.systemd_facts()
    resources = source.resource_facts()
    containers = source.container_facts()
    listeners = source.listener_facts()
    schedulers = source.scheduler_identity_facts()
    applications = source.application_readiness_facts()

    assert len(cast("list[object]", systemd["service_units"])) == len(_SERVICE_UNITS)
    assert len(resources) == len(_SERVICE_UNITS)
    assert _mapping(resources[0])["memory_max_bytes"] is None
    assert containers == [
        {
            "health": "HEALTHY",
            "image_id": "sha256:" + "b" * 64,
            "name": container_id,
            "runtime_state": "running",
        }
    ]
    assert listeners == [
        {"address": "127.0.0.1", "port": 8000, "public": False, "transport": "TCP"},
        {"address": "::", "port": 4317, "public": True, "transport": "UDP"},
    ]
    assert [_mapping(row)["scheduler_id"] for row in schedulers] == ["GENERAL", "PROMOTION"]
    assert [_mapping(row)["application_id"] for row in applications] == [
        item[0] for item in _APPLICATIONS
    ]


def test_ubuntu_kernel_capacity_backup_and_telemetry_probes_read_metadata_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filesystem probes retain hashes, sizes, modes, and ages without reading payload bytes."""
    source = _ubuntu_source_without_init()
    native = tmp_path / "native"
    recovery = tmp_path / "recovery"
    telemetry = tmp_path / "telemetry"
    for root in (native, recovery, telemetry):
        root.mkdir()
        (root / "retained.bin").write_bytes(b"not inspected")

    def boot_id(_path: Path, **_options: object) -> str:
        return "01234567-89ab-cdef-0123-456789abcdef\n"

    def capacity_values(_path: str) -> SimpleNamespace:
        return SimpleNamespace(
            f_bavail=10,
            f_blocks=20,
            f_favail=30,
            f_files=40,
            f_frsize=4096,
        )

    monkeypatch.setattr(
        "tools.v1_poc_collect_host_facts._BACKUP_ROOTS",
        (("NATIVE", native.as_posix()), ("RECOVERY", recovery.as_posix())),
    )
    monkeypatch.setattr("tools.v1_poc_collect_host_facts._TELEMETRY_ROOT", telemetry)
    monkeypatch.setattr(
        "tools.v1_poc_collect_host_facts.Path.read_text",
        boot_id,
    )
    monkeypatch.setattr("tools.v1_poc_collect_host_facts.platform.release", lambda: "6.8.0-test")
    monkeypatch.setattr(
        "tools.v1_poc_collect_host_facts.os.statvfs",
        capacity_values,
    )

    kernel = source.kernel_facts()
    capacity = source.mount_capacity_facts()
    backups = source.backup_freshness_facts()
    observed_telemetry = source.telemetry_freshness_facts()

    assert (
        kernel["boot_id_fingerprint"]
        == "sha256:" + sha256(b"01234567-89ab-cdef-0123-456789abcdef").hexdigest()
    )
    assert [_mapping(row)["path"] for row in capacity] == [
        "/srv/asklegal/sql",
        "/srv/asklegal/vault-primary",
        "/srv/asklegal/vault-recovery",
    ]
    backup_rows = _items(backups["backups"])
    first_backup_freshness = _mapping(_mapping(backup_rows[0])["freshness"])
    telemetry_freshness = _mapping(observed_telemetry["freshness"])
    assert first_backup_freshness["file_count"] == 1
    assert telemetry_freshness["file_count"] == 1

    (native / "retained-link").symlink_to(native / "retained.bin")
    with pytest.raises(TypeError, match="host metadata symlink"):
        source.backup_freshness_facts()


def test_invalid_nft_ss_and_ip_observations_fail_instead_of_being_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every nonempty firewall and address observation must have its exact shape."""
    source = _ubuntu_source_without_init()

    def available_tool(_name: str) -> str:
        return "/bin/tool"

    monkeypatch.setattr("tools.v1_poc_collect_host_facts.shutil.which", available_tool)
    source._run = lambda _command, **_options: '{"nftables":{}}'  # type: ignore[method-assign] # noqa: SLF001
    with pytest.raises((TypeError, ValueError)):
        source._nft_defaults()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    source._run = lambda _command, **_options: "LISTEN malformed"  # type: ignore[method-assign] # noqa: SLF001
    with pytest.raises((TypeError, ValueError)):
        source._public_tcp_ports()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    source._run = lambda _command, **_options: (  # type: ignore[method-assign] # noqa: SLF001
        '[{"ifname":"eth0","addr_info":[{"family":"inet"}]}]'
    )
    with pytest.raises((TypeError, ValueError)):
        source._foreign_networks(set())  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    source._run = lambda _command, **_options: (  # type: ignore[method-assign] # noqa: SLF001
        '[{"ifname":"lo","addr_info":[{"family":"inet"}]}]'
    )
    with pytest.raises((TypeError, ValueError)):
        source._foreign_networks(set())  # pyright: ignore[reportPrivateUsage] # noqa: SLF001


def test_declared_docker_bridge_gateway_is_not_a_foreign_subnet_collision() -> None:
    """A gateway address for the exact named Docker bridge belongs to its declared subnet."""
    source = _ubuntu_source_without_init()
    source._run = lambda _command, **_options: (  # type: ignore[method-assign] # noqa: SLF001
        '[{"ifname":"br-asklegal","addr_info":['
        '{"family":"inet","local":"10.90.0.1","prefixlen":24}]},'
        '{"ifname":"eth0","addr_info":['
        '{"family":"inet","local":"192.168.9.126","prefixlen":22}]}]'
    )

    assert source._foreign_networks(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        {"10.90.0.0/24"}
    ) == ["192.168.9.126/22"]


def test_invalid_time_observation_is_not_coerced_to_false() -> None:
    """Only systemd's exact yes/no vocabulary is a time-synchronization fact."""
    source = _ubuntu_source_without_init()
    source._run = lambda _command: "unknown"  # type: ignore[method-assign] # noqa: SLF001
    with pytest.raises(ValueError, match="timedatectl"):
        source.time_facts()


def test_credential_metadata_stat_and_scan_errors_fail_visibly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A denied credential metadata path is not equivalent to an absent path."""
    source = _ubuntu_source_without_init()

    def denied_lstat(_path: os.PathLike[str] | str) -> os.stat_result:
        message = "private credential path"
        raise PermissionError(message)

    monkeypatch.setattr("tools.v1_poc_collect_host_facts.os.lstat", denied_lstat)
    with pytest.raises(PermissionError):
        source.credential_facts()


def test_absence_markers_are_bound_to_exact_probe_and_return_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absence-looking message from another command or status is still a probe failure."""
    source = _ubuntu_source_without_init()

    def result_for(command: Sequence[str], **_options: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            returncode=2,
            stdout="",
            stderr="Error: No such network: missing",
        )

    monkeypatch.setattr("tools.v1_poc_collect_host_facts.subprocess.run", result_for)
    with pytest.raises(RuntimeError, match="read-only probe failed"):
        source._absent_or_run(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            ("docker", "network", "inspect", "missing")
        )


def test_output_runs_are_byte_identical_and_stdout_contains_only_acknowledgement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI writes canonical local bytes and never streams host facts to stdout."""
    monkeypatch.setattr(
        "tools.v1_poc_collect_host_facts.UbuntuHostFactsSource",
        _FakeSource,
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "collector",
            "--acknowledge-read-only-host-inspection",
            "--output",
            str(first),
        ],
    )
    main()
    first_stdout = capsys.readouterr().out
    monkeypatch.setattr(
        "sys.argv",
        [
            "collector",
            "--acknowledge-read-only-host-inspection",
            "--output",
            str(second),
        ],
    )
    main()
    second_stdout = capsys.readouterr().out

    assert first.read_bytes() == second.read_bytes()
    assert first_stdout == "PASS READ_ONLY_HOST_FACTS_WRITTEN\n"
    assert second_stdout == first_stdout
    assert "memory_bytes" not in first_stdout
    assert "/srv/asklegal" not in first_stdout


def test_output_requires_acknowledgement_before_probe_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without explicit acknowledgement, no source is constructed and no file appears."""
    output = tmp_path / "facts.json"

    def forbidden_source() -> _FakeSource:
        message = "source constructed"
        raise AssertionError(message)

    monkeypatch.setattr("tools.v1_poc_collect_host_facts.UbuntuHostFactsSource", forbidden_source)
    monkeypatch.setattr("sys.argv", ["collector", "--output", str(output)])
    with pytest.raises(SystemExit, match="acknowledgement required"):
        main()
    assert not output.exists()


def test_output_is_private_and_can_atomically_replace_a_regular_file(tmp_path: Path) -> None:
    """Every successful first or repeated write leaves one regular mode-0600 file."""
    output = tmp_path / "facts.json"
    output.write_text("old", encoding="utf-8")
    output.chmod(0o644)
    envelope = collect_hk_v1_host_facts(_FakeSource())

    write_host_facts_output(envelope, output)
    first = output.read_bytes()
    write_host_facts_output(envelope, output)

    assert output.read_bytes() == first
    assert stat.S_ISREG(output.lstat().st_mode)
    assert stat.S_IMODE(output.lstat().st_mode) == 0o600


@pytest.mark.parametrize("target_kind", ["symlink", "directory"])
def test_output_rejects_non_regular_targets_without_following(
    target_kind: str,
    tmp_path: Path,
) -> None:
    """Never replace a symlink or directory selected as the facts target."""
    output = tmp_path / "facts.json"
    protected = tmp_path / "protected.json"
    protected.write_text("protected", encoding="utf-8")
    if target_kind == "symlink":
        output.symlink_to(protected)
    else:
        output.mkdir()

    with pytest.raises(HostFactsOutputError, match=r"^HOST_FACTS_OUTPUT_FAILED$") as caught:
        write_host_facts_output(collect_hk_v1_host_facts(_FakeSource()), output)

    assert caught.value.__cause__ is None
    assert protected.read_text(encoding="utf-8") == "protected"


def test_output_creates_only_the_explicit_private_parent_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing retained-output chain is created privately, then read back exactly."""
    envelope = collect_hk_v1_host_facts(_FakeSource())
    output = tmp_path / "var" / "hk-v1" / "host" / "facts.json"

    write_host_facts_output(envelope, output)

    assert host_facts_document(load_host_facts_output(output)) == host_facts_document(envelope)
    for parent in (output.parent, output.parent.parent, output.parent.parent.parent):
        assert stat.S_IMODE(parent.lstat().st_mode) == 0o700

    def interrupting_mkstemp(**_options: object) -> tuple[int, str]:
        del _options
        raise KeyboardInterrupt

    monkeypatch.setattr("tools.v1_poc_collect_host_facts.tempfile.mkstemp", interrupting_mkstemp)
    with pytest.raises(KeyboardInterrupt):
        write_host_facts_output(envelope, tmp_path / "facts.json")


def test_output_rejects_a_symlink_anywhere_in_the_requested_parent_chain(
    tmp_path: Path,
) -> None:
    """Parent creation never follows an existing alias outside the explicit path."""
    protected = tmp_path / "protected"
    protected.mkdir()
    alias = tmp_path / "var"
    alias.symlink_to(protected, target_is_directory=True)
    output = alias / "hk-v1" / "host" / "facts.json"

    with pytest.raises(HostFactsOutputError, match=r"^HOST_FACTS_OUTPUT_FAILED$"):
        write_host_facts_output(collect_hk_v1_host_facts(_FakeSource()), output)

    assert tuple(protected.iterdir()) == ()


def test_envelope_is_immutable_and_returns_detached_legacy_facts() -> None:
    """Callers cannot mutate the stored canonical legacy fact snapshot."""
    envelope = collect_hk_v1_host_facts(_FakeSource())
    assert isinstance(envelope, HKV1HostFacts)
    first = envelope.legacy_facts
    first["memory_bytes"] = 1

    assert envelope.legacy_facts["memory_bytes"] == 68_719_476_736
