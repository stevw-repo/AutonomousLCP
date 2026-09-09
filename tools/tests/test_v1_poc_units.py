"""Tests for the generated V1 POC systemd units and their launchers."""

import json
import shutil
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


def _service(service_id: str) -> dict[str, object]:
    return next(service for service in _services() if service["service_id"] == service_id)


def _named_environment(service_id: str) -> dict[str, str]:
    environment = _service(service_id)["environment"]
    assert isinstance(environment, list)
    return {
        str(entry["name"]): str(entry["value"])
        for entry in cast("list[dict[str, object]]", environment)
    }


def _mount_triplets(service_id: str) -> set[tuple[str, str, str]]:
    mounts = _service(service_id)["mounts"]
    assert isinstance(mounts, list)
    return {
        (str(entry["source"]), str(entry["target"]), str(entry["mode"]))
        for entry in cast("list[dict[str, object]]", mounts)
    }


def test_checked_in_units_match_the_contracts() -> None:
    """A hand edit or an unpropagated contract change must fail here, not at boot."""
    assert check(REPOSITORY_ROOT) == ()


def test_control_plane_retains_schedule_and_maintenance_state_on_the_host() -> None:
    """A recreated Control container must reopen its exact local schedule state."""
    state_root = "/var/lib/asklegal/control"
    cutoff_root = "/var/lib/asklegal/acceptance-cutoffs"
    assert _named_environment("control-plane") == {
        "ASKLEGAL_CONTROL_STATE_ROOT": state_root,
        "ASKLEGAL_HK_V1_ACCEPTANCE_CUTOFF_ROOT": cutoff_root,
    }
    assert (state_root, state_root, "rw") in _mount_triplets("control-plane")
    assert (cutoff_root, cutoff_root, "ro") in _mount_triplets("control-plane")
    launcher = _rendered()["launch/control-plane.sh"]
    assert f"-e 'ASKLEGAL_CONTROL_STATE_ROOT={state_root}'" in launcher
    assert f"-e 'ASKLEGAL_HK_V1_ACCEPTANCE_CUTOFF_ROOT={cutoff_root}'" in launcher
    assert f"-v '{state_root}:{state_root}:rw'" in launcher
    assert f"-v '{cutoff_root}:{cutoff_root}:ro'" in launcher


def test_review_api_receives_exact_read_only_package_and_persistent_approval_state() -> None:
    """Container replacement must preserve named Approval and reread exact package bytes."""
    state_root = "/var/lib/asklegal/review"
    artifact_root = "/var/lib/asklegal/review-artifacts"
    assert _named_environment("review-api") == {
        "ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT": artifact_root,
        "ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH": f"{state_root}/review-authority.json",
        "ASKLEGAL_LOCAL_REVIEW_STATE_ROOT": state_root,
    }
    mounts = _mount_triplets("review-api")
    assert (state_root, state_root, "rw") in mounts
    assert (artifact_root, artifact_root, "ro") in mounts
    launcher = _rendered()["launch/review-api.sh"]
    assert f"-v '{state_root}:{state_root}:rw'" in launcher
    assert f"-v '{artifact_root}:{artifact_root}:ro'" in launcher


def test_promotion_worker_receives_only_explicit_retained_authority_paths() -> None:
    """Promotion has no deployment-wide write switch or implicit transient state."""
    state_root = "/var/lib/asklegal/promotion"
    expected = {
        "ASKLEGAL_PROMOTION_APPROVAL_LEDGER": ("/var/lib/asklegal/review/approval-register.json"),
        "ASKLEGAL_PROMOTION_CURRENT_SERVING_STATE": f"{state_root}/current-serving-state",
        "ASKLEGAL_PROMOTION_EFFECT_INTENT_LEDGER": f"{state_root}/effect-intents",
        "ASKLEGAL_PROMOTION_NATIVE_BACKUP_ROOT": "/var/lib/asklegal/promotion-backup-native",
        "ASKLEGAL_PROMOTION_PACKAGE_ROOT": "/var/lib/asklegal/review-artifacts",
        "ASKLEGAL_PROMOTION_RECOVERY_BACKUP_ROOT": ("/var/lib/asklegal/promotion-backup-recovery"),
        "ASKLEGAL_PROMOTION_SERVING_PROFILE": (
            "/etc/asklegal/config/hk-v1-promotion/serving-profile.json"
        ),
        "ASKLEGAL_PROMOTION_STATE_ROOT": state_root,
        "ASKLEGAL_PROMOTION_TOKENIZER_RESOURCE": (
            "/etc/asklegal/config/hk-v1-promotion/o200k_base.tiktoken"
        ),
    }
    assert _named_environment("promotion-worker") == expected
    assert "PROMOTION_WRITE_AUTHORIZED" not in _named_environment("promotion-worker")
    mounts = _mount_triplets("promotion-worker")
    assert ("/var/lib/asklegal/review", "/var/lib/asklegal/review", "rw") in mounts
    assert (state_root, state_root, "rw") in mounts
    assert (
        "/var/lib/asklegal/promotion-backup-native",
        "/var/lib/asklegal/promotion-backup-native",
        "rw",
    ) in mounts
    assert (
        "/var/lib/asklegal/promotion-backup-recovery",
        "/var/lib/asklegal/promotion-backup-recovery",
        "rw",
    ) in mounts


def test_acquisition_worker_receives_exact_read_only_inputs_and_persistent_state() -> None:
    """Scheduled family work must survive recreation and never mutate its input authority."""
    state_root = "/var/lib/asklegal/acquisition"
    source_root = "/var/lib/asklegal/source-admission"
    config_root = "/etc/asklegal/config/hk-v1-acquisition"
    assert _named_environment("acquisition-worker") == {
        "ASKLEGAL_HK_V1_DUE_STATE_ROOT": f"{state_root}/due-cycle",
        "ASKLEGAL_HK_V1_GLD_WINDOW_SNAPSHOT": f"{config_root}/gld-window-snapshot.json",
        "ASKLEGAL_HK_V1_GLD_OPERATOR_MODE": "DISABLED",
        "ASKLEGAL_HK_V1_GLD_CHALLENGE_AUTHORITY_RECEIPT": (
            f"{config_root}/gld-challenge-authority.json"
        ),
        "ASKLEGAL_HK_V1_GLD_CHALLENGE_CONTRACT": (f"{config_root}/gld-challenge-contract.json"),
        "ASKLEGAL_HK_V1_GLD_SESSION_ROOT": f"{state_root}/gld-sessions",
        "ASKLEGAL_HK_V1_GLD_START_DATE": "1997-07-01",
        "ASKLEGAL_HK_V1_HKEL_ADMISSION_RECEIPT": f"{config_root}/hkel-admission-receipt.json",
        "ASKLEGAL_HK_V1_HKEL_ARCHIVE_OBSERVATION": (f"{config_root}/hkel-archive-observation.json"),
        "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM": (
            f"{config_root}/judiciary-advanced-search-form.html"
        ),
        "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM_FINGERPRINT": (
            f"{config_root}/judiciary-advanced-search-form.sha256"
        ),
        "ASKLEGAL_HK_V1_LEGISLATION_STATE_ROOT": f"{state_root}/legislation",
        "ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT": source_root,
    }
    mounts = _mount_triplets("acquisition-worker")
    assert (state_root, state_root, "rw") in mounts
    assert (source_root, source_root, "ro") in mounts
    assert (config_root, config_root, "ro") in mounts
    launcher = _rendered()["launch/acquisition-worker.sh"]
    assert "ASKLEGAL_HK_V1_GLD_OPERATOR_MODE=DISABLED" in launcher
    assert "ASKLEGAL_HK_V1_GLD_CHALLENGE_AUTHORITY_RECEIPT=" in launcher
    assert "ASKLEGAL_HK_V1_GLD_CHALLENGE_CONTRACT=" in launcher
    assert "ASKLEGAL_HK_V1_GLD_SESSION_ROOT=" in launcher
    assert f"-v '{state_root}:{state_root}:rw'" in launcher
    assert f"-v '{source_root}:{source_root}:ro'" in launcher
    assert f"-v '{config_root}:{config_root}:ro'" in launcher


def test_every_proven_service_has_a_unit_and_a_launcher() -> None:
    """A service without both would be silently dropped from the boot sequence."""
    rendered = _rendered()
    for service in _services():
        assert str(service["unit_name"]) in rendered
        assert f"launch/{service['service_id']}.sh" in rendered


def test_every_launcher_requires_the_atomic_authority_bound_image_manifest() -> None:
    """No reboot or manual restart may resolve an application through a mutable tag."""
    for service_id in (
        "acquisition-worker",
        "control-plane",
        "legal-processing-worker",
        "promotion-worker",
        "review-api",
    ):
        launcher = _rendered()[f"launch/{service_id}.sh"]
        assert "deployment_manifest=/etc/asklegal/deployment-images" in launcher
        assert f"^{service_id} sha256:[0-9a-f]{{64}}$" in launcher
        assert "docker image inspect --format '{{.Id}}' \"$image_id\"" in launcher
        assert f"'asklegal/{service_id}:v1'" not in launcher


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


def test_egress_bridges_pin_only_proxy_and_worker_addresses() -> None:
    """The host firewall must be able to distinguish proxies from their workers."""
    expected = {
        "egress-source": ("asklegal-egress-source", "10.90.7.2"),
        "acquisition-worker": ("asklegal-egress-source", "10.90.7.3"),
        "egress-model": ("asklegal-egress-model", "10.90.8.2"),
        "legal-processing-worker": ("asklegal-egress-model", "10.90.8.3"),
        "egress-promotion": ("asklegal-egress-promotion", "10.90.9.2"),
        "promotion-worker": ("asklegal-egress-promotion", "10.90.9.3"),
    }
    for service_id, (network, address) in expected.items():
        service = _service(service_id)
        networks = cast("list[dict[str, object]]", service["networks"])
        entry = next(item for item in networks if item["network"] == network)
        assert entry["ipv4_address"] == address
        launcher = _rendered()[f"launch/{service_id}.sh"]
        if networks.index(entry) == 0:
            assert f"--ip '{address}'" in launcher
        else:
            assert f"docker network connect --ip '{address}'" in launcher


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


def test_shared_runtime_paths_have_numeric_least_privilege_acl_contracts() -> None:
    """Distinct container UIDs must be able to traverse only their declared handoff paths."""
    script = (REPOSITORY_ROOT / "infrastructure/poc/provisioning/30-identities.sh").read_text(
        encoding="utf-8"
    )
    assert 'create_group "asklegal-acquisition-readers" 3100' in script
    assert 'create_group "asklegal-review-artifacts" 3101' in script
    assert 'create_group "asklegal-review-promotion" 3102' in script
    assert 'create_shared_directory "/var/lib/asklegal/acquisition" 3000 3100 2750' in script
    assert 'set_default_acl "/var/lib/asklegal/acquisition" 3003 "r-X"' in script
    assert 'create_shared_directory "/var/lib/asklegal/review-artifacts" 3003 3101 2770' in script
    assert 'set_default_acl "/var/lib/asklegal/review-artifacts" 3007 "r-X"' in script
    assert 'set_default_acl "/var/lib/asklegal/review-artifacts" 3006 "r-X"' in script
    assert 'create_shared_directory "/var/lib/asklegal/review" 3007 3102 2770' in script
    assert 'set_default_acl "/var/lib/asklegal/review" 3006 "rwx"' in script
    assert 'create_shared_directory "/var/lib/asklegal/acceptance-cutoffs" 3001 3001 2750' in script
    assert (
        'create_shared_directory "/var/lib/asklegal/promotion-backup-native" 3006 3006 2750'
        in script
    )
    assert (
        'create_shared_directory "/var/lib/asklegal/promotion-backup-recovery" 3006 3006 2750'
        in script
    )


@pytest.mark.parametrize(
    ("path", "uid", "permission", "allowed"),
    [
        ("acquisition", 3000, "w", True),
        ("acquisition", 3003, "r", True),
        ("acquisition", 3003, "w", False),
        ("acquisition", 3007, "r", False),
        ("review-artifacts", 3003, "w", True),
        ("review-artifacts", 3007, "r", True),
        ("review-artifacts", 3007, "w", False),
        ("review-artifacts", 3006, "r", True),
        ("review-artifacts", 3006, "w", False),
        ("review", 3007, "w", True),
        ("review", 3006, "w", True),
        ("review", 3003, "r", False),
        ("acceptance-cutoffs", 3001, "w", True),
        ("promotion-backup-native", 3006, "w", True),
        ("promotion-backup-recovery", 3006, "w", True),
        ("promotion-backup-recovery", 3007, "r", False),
    ],
)
def test_numeric_runtime_identity_access_model(
    path: str, uid: int, permission: str, *, allowed: bool
) -> None:
    """Model POSIX owner/group/mode and named ACL precedence for every handoff root."""
    memberships = {
        3000: {3000, 3100},
        3001: {3001},
        3003: {3003, 3100, 3101},
        3006: {3006, 3101, 3102},
        3007: {3007, 3101, 3102},
    }
    policies: dict[str, tuple[int, int, int, dict[int, str]]] = {
        "acquisition": (3000, 3100, 0o2750, {3003: "r-x"}),
        "review-artifacts": (3003, 3101, 0o2770, {3007: "r-x", 3006: "r-x"}),
        "review": (3007, 3102, 0o2770, {3006: "rwx"}),
        "acceptance-cutoffs": (3001, 3001, 0o2750, {}),
        "promotion-backup-native": (3006, 3006, 0o2750, {}),
        "promotion-backup-recovery": (3006, 3006, 0o2750, {}),
    }
    owner, group, mode, named_acl = policies[path]
    shifts = {"r": 2, "w": 1, "x": 0}
    if uid in named_acl:
        observed = permission in named_acl[uid]
    else:
        shift = 6 if uid == owner else 3 if group in memberships[uid] else 0
        observed = bool((mode >> shift) & (1 << shifts[permission]))
    assert observed is allowed


def test_bootstrap_units_are_rendered_and_dependencies_are_not_silently_dropped() -> None:
    """SQL/vault consumers must wait for owning fail-visible bootstrap readback units."""
    rendered = _rendered()
    assert "asklegal-filesystems.target" in rendered
    for name in ("asklegal-register-migrate.service", "asklegal-vault-bootstrap.service"):
        assert name in rendered
        assert "Type=oneshot" in rendered[name]
        assert "RemainAfterExit=yes" in rendered[name]
        assert "User=root" in rendered[name]
        assert "Group=root" in rendered[name]
        assert "UMask=0077" in rendered[name]
        assert "/usr/bin/test -x /usr/local/libexec/" in rendered[name]
        assert "--verify-only" in rendered[name]
    install = rendered["80-install.sh"]
    assert "infrastructure/poc/libexec/asklegal-register-migrate" in install
    assert "infrastructure/poc/libexec/asklegal-vault-bootstrap" in install
    assert "infrastructure/poc/libexec/asklegal-vault-application-rotation-network" in install
    assert "/usr/local/libexec/asklegal-vault-application-rotation-network" in install
    assert "packages/management-register-adapter/migrations/." in install
    assert "/opt/asklegal/management-register/migrations" in install
    control = rendered["asklegal-control-plane.service"]
    assert "asklegal-register-migrate.service" in control
    assert "asklegal-vault-bootstrap.service" in control
    assert "After=" in rendered["asklegal-sql-server.service"]
    assert "asklegal-filesystems.target" in rendered["asklegal-sql-server.service"]
    register = rendered["asklegal-register-migrate.service"]
    for name in (
        "sql-acquisition",
        "sql-control",
        "sql-processing",
        "sql-promotion",
        "sql-review",
    ):
        assert f"LoadCredentialEncrypted={name}:" in register


@pytest.mark.parametrize(
    ("helper", "module_command", "invalid_code"),
    [
        (
            "asklegal-register-migrate",
            "-m asklegal_control_plane.bootstrap register",
            "REGISTER_BOOTSTRAP_INPUT_INVALID",
        ),
        (
            "asklegal-vault-bootstrap",
            "-m asklegal_control_plane.bootstrap vault",
            "VAULT_BOOTSTRAP_INPUT_INVALID",
        ),
    ],
)
def test_bootstrap_helpers_have_fixed_root_only_no_effect_boundary(
    helper: str, module_command: str, invalid_code: str
) -> None:
    """Helpers expose fixed container argv and reject malformed input before Docker."""
    path = REPOSITORY_ROOT / "infrastructure/poc/libexec" / helper
    body = path.read_text(encoding="utf-8")
    if helper == "asklegal-register-migrate":
        assert "/usr/bin/docker run --rm" in body
    else:
        assert '/usr/bin/docker create --name "$container"' in body
        assert body.count("--network asklegal-vault-primary") == 1
        assert '/usr/bin/docker network connect asklegal-vault-recovery "$container"' in body
        assert '/usr/bin/docker start --attach "$container"' in body
        assert "trap cleanup EXIT" in body
        assert 'if [ "$created" -eq 1 ]' in body
        assert '/usr/bin/docker rm -f "$container"' in body
    assert "--user 0:0" in body
    assert "--read-only" in body
    assert "--cap-drop ALL" in body
    assert "--security-opt no-new-privileges" in body
    assert "dst=/run/credentials,readonly" in body
    assert "deployment_manifest=/etc/asklegal/deployment-images" in body
    assert "^control-plane sha256:[0-9a-f]{64}$" in body
    assert '--entrypoint /opt/asklegal/bin/python "$image_id"' in body
    assert "asklegal/control-plane:v1" not in body
    assert module_command in body
    assert " -e " not in body
    syntax = subprocess.run(  # noqa: S603 - fixed shell and repository-owned path.
        ["/usr/bin/bash", "-n", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr
    rejected = subprocess.run(  # noqa: S603 - fixed shell and repository-owned path.
        ["/usr/bin/bash", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 2
    assert rejected.stderr == invalid_code + "\n"


def test_renderer_rejects_an_unrendered_dependency(tmp_path: Path) -> None:
    """A dependency typo must stop rendering rather than disappear from the unit."""
    root = tmp_path / "repo"
    shutil.copytree(REPOSITORY_ROOT / "infrastructure", root / "infrastructure")
    policy_path = root / "infrastructure/poc/systemd_unit_inputs.json"
    policy = json.loads(policy_path.read_bytes())
    policy["service_units"][0]["requires"] = ["asklegal-missing.service"]
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(Exception, match="unrendered dependency"):
        render(root)


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
