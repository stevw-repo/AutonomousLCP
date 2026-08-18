"""Tests for the bounded read-only Ubuntu host-fact collector."""

from collections import Counter
from typing import TYPE_CHECKING

import pytest

from tools.tests.test_v1_poc_host_admission import _policy
from tools.v1_poc_collect_host_facts import (
    UbuntuHostFactsSource,
    _parse_os_release,
    collect_host_facts,
)
from tools.v1_poc_host_admission import evaluate_host_facts

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue


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
            "docker_group_non_root_members": [],
        }


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
        }
    )
    assert facts["host_packages"] == {}
    assert facts["private_subnets"] == {}


def test_os_release_parser_is_bounded_to_declared_key_value_facts() -> None:
    """Ignore comments and preserve quoted Ubuntu identity fields exactly."""
    assert _parse_os_release('# comment\nID="ubuntu"\nVERSION_ID="24.04"\n') == {
        "ID": "ubuntu",
        "VERSION_ID": "24.04",
    }


def test_non_linux_collection_fails_before_any_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never pretend that facts collected on the development Mac describe Ubuntu."""
    monkeypatch.setattr("tools.v1_poc_collect_host_facts.platform.system", lambda: "Darwin")
    with pytest.raises(RuntimeError, match="requires Linux"):
        UbuntuHostFactsSource()
