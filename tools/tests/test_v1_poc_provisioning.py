"""Tests for the generated V1 POC root provisioning scripts."""

import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from tools.v1_poc_render_provisioning import OUTPUT_ROOT, check, render

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = (
    "provision.sh",
    "10-preflight.sh",
    "20-storage.sh",
    "30-identities.sh",
    "40-networks.sh",
    "50-journal-time.sh",
    "60-firewall.sh",
)


def test_checked_in_scripts_match_the_contracts() -> None:
    """A hand edit or an unpropagated contract change must fail here, not on the host."""
    assert check(REPOSITORY_ROOT) == ()


@pytest.mark.parametrize("name", _SCRIPTS)
def test_every_script_is_valid_bash(name: str) -> None:
    """A script that cannot parse would fail halfway through changing the host."""
    path = REPOSITORY_ROOT / OUTPUT_ROOT / name
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/bash", "-n", str(path)], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", _SCRIPTS)
def test_every_script_fails_fast_and_supports_a_dry_run(name: str) -> None:
    """Provisioning must be previewable and must stop at the first failure."""
    content = (REPOSITORY_ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8")
    assert "set -euo pipefail" in content
    assert 'DRY_RUN="${DRY_RUN:-0}"' in content


def test_no_script_carries_a_credential_or_enables_a_service() -> None:
    """Provisioning creates hosts and paths only; credentials and services are gated."""
    for name, content in render(REPOSITORY_ROOT).items():
        assert "systemctl enable" not in content, name
        assert "docker pull" not in content, name
        assert "systemd-creds encrypt" not in content, name
        assert "PASSWORD" not in content.upper().replace("--LOCK", ""), name


def test_the_firewall_step_is_not_run_by_the_top_level_script() -> None:
    """The one step that can lock the user out must be deliberate and separate."""
    scripts = render(REPOSITORY_ROOT)
    assert "60-firewall" not in scripts["provision.sh"].split("for step in")[1].split("\n")[0]
    firewall = scripts["60-firewall.sh"]
    assert "I_HAVE_CONSOLE_ACCESS" in firewall
    assert "nft delete table inet asklegal" in firewall
    assert "dead-man" in firewall


def test_the_firewall_enforces_proxy_only_container_egress() -> None:
    """Workers on routable bridges must not bypass their designated proxies."""
    firewall = render(REPOSITORY_ROOT)["60-firewall.sh"]
    assert "hook input" in firewall
    assert "chain asklegal-container-egress" in firewall
    assert "hook forward" in firewall
    assert "policy drop" in firewall
    assert "ip saddr != 10.90.0.0/16 accept" in firewall
    assert "ip daddr 10.90.0.0/16 accept" in firewall
    assert "ip saddr { 10.90.7.2, 10.90.8.2, 10.90.9.2 } accept" in firewall


def test_identities_match_the_allocation_exactly() -> None:
    """Every account in the script must be the one the contract allocated."""
    policy = json.loads(
        (REPOSITORY_ROOT / "infrastructure/poc/host_identity_inputs.json").read_bytes()
    )
    script = render(REPOSITORY_ROOT)["30-identities.sh"]
    identities = policy["identities"]
    assert isinstance(identities, list)
    typed_identities = cast("list[dict[str, object]]", identities)
    for entry in typed_identities:
        assert f'create_identity "{entry["identity"]}" {entry["uid"]}' in script
    assert script.count('create_identity "') == len(typed_identities)


def test_preflight_requires_acl_capability_before_shared_path_mutation() -> None:
    """The cross-UID handoff contract must fail before provisioning if ACLs are unavailable."""
    preflight = render(REPOSITORY_ROOT)["10-preflight.sh"]
    assert "command -v setfacl" in preflight
    assert "setfacl unavailable" in preflight


def test_networks_match_the_topology_isolation_exactly() -> None:
    """An internal network wrongly created as routable would open a silent egress path."""
    units = json.loads(
        (REPOSITORY_ROOT / "infrastructure/poc/systemd_unit_inputs.json").read_bytes()
    )
    script = render(REPOSITORY_ROOT)["40-networks.sh"]
    for network in units["container_networks"]:
        isolation = "internal" if network["internal"] else "routable"
        assert (
            f'create_network "{network["network_id"]}" "{network["subnet"]}" {isolation}' in script
        )


def test_a_contract_change_drifts_the_rendered_script(tmp_path: Path) -> None:
    """The generator must actually read the contracts rather than embed a copy."""
    workspace = tmp_path / "repo"
    (workspace / "infrastructure/poc").mkdir(parents=True)
    for name in (
        "host_admission_policy.json",
        "host_identity_inputs.json",
        "topology.json",
        "systemd_unit_inputs.json",
    ):
        source = REPOSITORY_ROOT / "infrastructure/poc" / name
        (workspace / "infrastructure/poc" / name).write_bytes(source.read_bytes())
    path = workspace / "infrastructure/poc/host_identity_inputs.json"
    policy = json.loads(path.read_bytes())
    changed = deepcopy(policy)
    changed["identities"][0]["uid"] = 3099
    changed["identities"][0]["gid"] = 3099
    path.write_text(json.dumps(changed, indent=2))
    assert render(workspace)["30-identities.sh"] != render(REPOSITORY_ROOT)["30-identities.sh"]
