"""Tests for the generated V1 POC systemd units and their launchers."""

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from tools.v1_poc_render_units import OUTPUT_ROOT, RUNTIME_COMMANDS_PATH, check, render

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _commands() -> dict[str, object]:
    return json.loads((REPOSITORY_ROOT / RUNTIME_COMMANDS_PATH).read_bytes())


def _services() -> list[dict[str, object]]:
    services = _commands()["services"]
    assert isinstance(services, list)
    return cast("list[dict[str, object]]", services)


def _rendered() -> dict[str, str]:
    return render(REPOSITORY_ROOT)


def _service_ids() -> list[str]:
    return [str(service["service_id"]) for service in _services()]


def test_checked_in_units_match_the_contracts() -> None:
    """A hand edit or an unpropagated contract change must fail here, not at boot."""
    assert check(REPOSITORY_ROOT) == ()


def test_every_proven_service_has_a_unit_and_a_launcher() -> None:
    """A service without both would be silently dropped from the boot sequence."""
    rendered = _rendered()
    for service in _services():
        assert str(service["unit_name"]) in rendered
        assert f"launch/{service['service_id']}.sh" in rendered


@pytest.mark.parametrize("service_id", _service_ids())
def test_every_launcher_is_valid_bash(service_id: str) -> None:
    """A launcher that cannot parse would fail after systemd reports the unit started."""
    path = REPOSITORY_ROOT / OUTPUT_ROOT / "launch" / f"{service_id}.sh"
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/bash", "-n", str(path)], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("service_id", _service_ids())
def test_every_launcher_fails_fast(service_id: str) -> None:
    """A launcher that continued past a failed step could start a half-configured service."""
    content = _rendered()[f"launch/{service_id}.sh"]
    assert "set -euo pipefail" in content


def test_no_secret_value_is_written_into_any_generated_file() -> None:
    """The whole point of sealing credentials is defeated if one is rendered in."""
    for name, content in _rendered().items():
        assert "PASSWORD=" not in content.replace("MSSQL_SA_PASSWORD=", ""), name
        assert "SECRET_ACCESS_KEY=" not in content.replace('ROOT_SECRET_ACCESS_KEY="$(cat', ""), (
            name
        )


@pytest.mark.parametrize("service_id", _service_ids())
def test_secrets_never_reach_the_container_through_arguments(service_id: str) -> None:
    """A value on the command line is visible to every process on the host."""
    content = _rendered()[f"launch/{service_id}.sh"]
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("-e ") and "=" in stripped:
            # Only non-secret settings may carry a literal value.
            assert "PASSWORD" not in stripped
            assert "SECRET" not in stripped
            assert "ACCESS_KEY" not in stripped


def test_every_declared_credential_is_loaded_encrypted() -> None:
    """A credential the unit never loads would arrive as an empty file at runtime."""
    rendered = _rendered()
    for service in _services():
        unit = rendered[str(service["unit_name"])]
        for name in service["credential_names"]:  # type: ignore[union-attr]
            assert f"LoadCredentialEncrypted={name}:" in unit


def test_every_application_gets_its_credentials_at_the_mode_its_loader_requires() -> None:
    """The loader rejects anything but a 0400 file owned by the runtime uid."""
    rendered = _rendered()
    for service in _services():
        if service.get("credential_delivery") != "DIRECTORY_OWNED_BY_RUNTIME_UID":
            continue
        launcher = rendered[f"launch/{service['service_id']}.sh"]
        for name in service["credential_names"]:  # type: ignore[union-attr]
            assert f'-m 0400 "$CREDENTIALS_DIRECTORY"/{name}' in launcher


@pytest.mark.parametrize("service_id", _service_ids())
def test_every_network_is_attached_before_the_process_starts(service_id: str) -> None:
    """Attaching a network after start races the readiness gate."""
    launcher = _rendered()[f"launch/{service_id}.sh"]
    connect = launcher.find("docker network connect")
    start = launcher.find("docker start --attach")
    assert start != -1
    if connect != -1:
        assert connect < start


@pytest.mark.parametrize("service_id", _service_ids())
def test_every_container_drops_capabilities_and_privilege_escalation(service_id: str) -> None:
    """A container that kept capabilities would undo the unit's own hardening."""
    launcher = _rendered()[f"launch/{service_id}.sh"]
    assert "--cap-drop ALL" in launcher
    assert "--security-opt no-new-privileges" in launcher


@pytest.mark.parametrize("service_id", _service_ids())
def test_every_container_runs_as_its_allocated_identity(service_id: str) -> None:
    """Two services sharing an identity would break the accepted uid allocation."""
    service = next(item for item in _services() if item["service_id"] == service_id)
    launcher = _rendered()[f"launch/{service_id}.sh"]
    assert f"runtime_uid={service['runtime_uid']}" in launcher
    assert '--user "$runtime_uid":"$runtime_uid"' in launcher


def test_the_runtime_identities_are_collision_free() -> None:
    """The identity allocation is only least privilege if no two services share one."""
    uids = [service["runtime_uid"] for service in _services()]
    assert len(uids) == len(set(uids))


def test_units_are_installed_but_not_enabled_by_the_install_step() -> None:
    """Installation must not start anything; enabling stays a deliberate act."""
    install = _rendered()["80-install.sh"]
    assert "systemctl daemon-reload" in install
    assert "systemctl enable --now" not in install.replace(
        'printf "  sudo systemctl enable --now asklegal.target\\n"', ""
    )


def test_the_credential_step_seals_to_the_host_tpm() -> None:
    """A host-only key would leave the credentials readable from a stolen disk."""
    sealing = _rendered()["70-credentials.sh"]
    assert "--with-key=host+tpm2" in sealing


def test_services_that_were_never_run_are_recorded_rather_than_rendered() -> None:
    """Rendering a unit for an unproven service would claim more than was shown."""
    not_rendered = _commands()["not_rendered"]
    assert isinstance(not_rendered, list)
    rendered = _rendered()
    for entry in cast("list[dict[str, object]]", not_rendered):
        service_id = entry["service_id"]
        assert f"asklegal-{service_id}.service" not in rendered
        assert str(entry["reason"])
