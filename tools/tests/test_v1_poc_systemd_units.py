"""Fail-closed tests for disabled V1 POC systemd unit inputs."""

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from tools.v1_poc_render_units import render
from tools.v1_poc_systemd_units import (
    HOST_POLICY_PATH,
    SYSTEMD_POLICY_PATH,
    TOPOLOGY_PATH,
    SystemdInputCode,
    SystemdInputReport,
    check_systemd_input_policy,
    validate_systemd_input_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_bytes())
    return _object_map(value)


def _object_map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _item_by_id(value: object, service_id: str) -> dict[str, object]:
    for raw_item in _object_list(value):
        item = _object_map(raw_item)
        if item.get("service_id") == service_id:
            return item
    raise AssertionError(service_id)


def _policy() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / SYSTEMD_POLICY_PATH)


def _topology() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / TOPOLOGY_PATH)


def _host_policy() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / HOST_POLICY_PATH)


def _service(policy: dict[str, object], service_id: str) -> dict[str, object]:
    return _item_by_id(policy["service_units"], service_id)


def _timer(policy: dict[str, object], timer_id: str) -> dict[str, object]:
    for raw_item in _object_list(policy["timer_units"]):
        item = _object_map(raw_item)
        if item.get("timer_id") == timer_id:
            return item
    raise AssertionError(timer_id)


def _codes(
    policy: dict[str, object],
    topology: dict[str, object] | None = None,
    host_policy: dict[str, object] | None = None,
) -> set[SystemdInputCode]:
    return {
        finding.code
        for finding in validate_systemd_input_policy(
            policy, topology or _topology(), host_policy or _host_policy()
        )
    }


def test_systemd_unit_inputs_are_complete_hardened_and_disabled() -> None:
    """Bind every service/bootstrap/timer without installing or enabling it."""
    assert check_systemd_input_policy(REPOSITORY_ROOT) == SystemdInputReport(
        services=14,
        bootstrap_units=4,
        networks=10,
        timers=5,
        blockers=(
            "ARTIFACT_PINS",
            "UBUNTU_SYSTEMD_PROOF",
        ),
        enabled=0,
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("runtime_identity", "root", SystemdInputCode.TOPOLOGY),
        ("credential_names", ["sql-control"], SystemdInputCode.TOPOLOGY),
        ("requires", [], SystemdInputCode.DEPENDENCY),
        ("runtime_command_state", "READY", SystemdInputCode.RUNTIME),
        ("enabled", True, SystemdInputCode.RUNTIME),
    ],
)
def test_service_identity_credentials_dependencies_and_runtime_drift_fail_closed(
    field: str, value: object, expected: SystemdInputCode
) -> None:
    """Keep the Control unit bound to topology and explicitly non-runnable."""
    policy = deepcopy(_policy())
    _service(policy, "control-plane")[field] = value
    assert expected in _codes(policy)


def test_missing_or_duplicate_service_unit_fails_closed() -> None:
    """Require exactly one unit input for every topology service."""
    policy = deepcopy(_policy())
    units = _object_list(policy["service_units"])
    units[-1] = deepcopy(units[0])
    assert SystemdInputCode.INVENTORY in _codes(policy)


def test_authority_hardening_and_credential_transport_drift_fail_closed() -> None:
    """Reject host mutation authority, weaker hardening, or secret transport drift."""
    policy = deepcopy(_policy())
    authority = _object_map(policy["authority"])
    authority["unit_installation_authorized"] = True
    assert SystemdInputCode.AUTHORITY in _codes(policy)

    policy = deepcopy(_policy())
    hardening = _object_map(policy["hardening_profile"])
    hardening["no_new_privileges"] = False
    assert SystemdInputCode.HARDENING in _codes(policy)

    policy = deepcopy(_policy())
    transport = _object_map(policy["credential_transport"])
    transport["secret_arguments_forbidden"] = False
    assert SystemdInputCode.CREDENTIAL in _codes(policy)


def test_bootstrap_drift_fails_closed() -> None:
    """Keep privileged one-shots disabled."""
    policy = deepcopy(_policy())
    bootstrap = _object_list(policy["bootstrap_units"])
    _object_map(bootstrap[0])["enabled"] = True
    assert SystemdInputCode.BOOTSTRAP in _codes(policy)


@pytest.mark.parametrize(
    ("timer_id", "schedule_kind", "on_calendar"),
    [
        ("ordinary-observation", "OBSERVATION", "*-*-* 02:15:00 Asia/Hong_Kong"),
        (
            "full-reconciliation",
            "RECONCILIATION",
            "Sun *-*-* 03:15:00 Asia/Hong_Kong",
        ),
        ("audit-archive", "AUDIT_ARCHIVE", "*-*-* 04:30:00 Asia/Hong_Kong"),
        (
            "recovery-verification",
            "RECOVERY_VERIFY",
            "Mon *-*-* 05:15:00 Asia/Hong_Kong",
        ),
        (
            "telemetry-retention",
            "TELEMETRY_RETENTION",
            "*-*-* 06:00:00 Asia/Hong_Kong",
        ),
    ],
)
def test_exact_hong_kong_timer_contract_is_persistent_and_deterministic(
    timer_id: str, schedule_kind: str, on_calendar: str
) -> None:
    """Bind every operation to one exact local slot with deterministic catch-up."""
    timer = _timer(_policy(), timer_id)
    assert timer == {
        "timer_id": timer_id,
        "unit_name": f"asklegal-{timer_id}.timer",
        "trigger_unit_name": f"asklegal-{timer_id}.service",
        "schedule_kind": schedule_kind,
        "on_calendar": on_calendar,
        "persistent": True,
        "accuracy_sec": "1min",
        "randomized_delay_sec": "0",
        "enabled": False,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("on_calendar", "*-*-* 02:16:00 Asia/Hong_Kong"),
        ("persistent", False),
        ("accuracy_sec", "5min"),
        ("randomized_delay_sec", "1min"),
        ("schedule_kind", "HKEX"),
        ("trigger_unit_name", "asklegal-hkex.service"),
        ("enabled", True),
    ],
)
def test_timer_schedule_or_safety_drift_fails_closed(field: str, value: object) -> None:
    """Reject cadence, catch-up, jitter, V1-family, trigger, or authority drift."""
    policy = deepcopy(_policy())
    _timer(policy, "ordinary-observation")[field] = value
    assert SystemdInputCode.TIMER in _codes(policy)


def test_renderer_emits_five_safe_timer_and_trigger_pairs() -> None:
    """Render persistent timers and bounded one-shot enqueue operations without host mutation."""
    rendered = render(REPOSITORY_ROOT)
    policy = _policy()
    timers = [_object_map(item) for item in _object_list(policy["timer_units"])]
    assert len(timers) == 5
    for timer in timers:
        timer_name = str(timer["unit_name"])
        trigger_name = str(timer["trigger_unit_name"])
        timer_unit = rendered[timer_name]
        trigger_unit = rendered[trigger_name]
        assert f"OnCalendar={timer['on_calendar']}" in timer_unit
        assert f"Unit={trigger_name}" in timer_unit
        assert "Persistent=true" in timer_unit
        assert "AccuracySec=1min" in timer_unit
        assert "RandomizedDelaySec=0" in timer_unit
        assert "PartOf=asklegal.target" in timer_unit
        assert "Conflicts=shutdown.target" in timer_unit
        assert "Before=shutdown.target" in timer_unit
        assert "Requires=asklegal-control-plane.service" in trigger_unit
        assert "After=asklegal-control-plane.service" in trigger_unit
        assert "PartOf=asklegal.target" in trigger_unit
        assert "Conflicts=shutdown.target" in trigger_unit
        assert "Before=shutdown.target" in trigger_unit
        assert "Type=oneshot" in trigger_unit
        assert "TimeoutStartSec=60" in trigger_unit
        assert "TimeoutStopSec=30" in trigger_unit
        assert "KillMode=control-group" in trigger_unit
        assert (
            "ExecStart=/usr/bin/docker exec asklegal-control-plane "
            f"asklegal-control-plane --enqueue-schedule {timer['schedule_kind']} "
            "--invocation-id ${INVOCATION_ID}"
        ) in trigger_unit

    generated_timer_text = "\n".join(
        rendered[str(timer["unit_name"])] + rendered[str(timer["trigger_unit_name"])]
        for timer in timers
    ).lower()
    assert "hkex" not in generated_timer_text


def test_target_and_install_script_include_the_timer_units_without_enabling_them() -> None:
    """A future authorized target start includes timers; rendering itself changes no host state."""
    rendered = render(REPOSITORY_ROOT)
    target = rendered["asklegal.target"]
    for timer in _object_list(_policy()["timer_units"]):
        timer_name = str(_object_map(timer)["unit_name"])
        assert timer_name in target
    install = rendered["80-install.sh"]
    assert '"$here"/*.service "$here"/*.target "$here"/*.timer' in install
    assert "systemctl enable --now" not in install.replace(
        'printf "  sudo systemctl enable --now asklegal.target\\n"', ""
    )


def test_topology_and_embedded_secret_drift_fail_closed() -> None:
    """Bind unit inputs to topology and reject secret-bearing additions."""
    topology = _topology()
    control = _item_by_id(topology["services"], "control-plane")
    control["identity"] = "changed-identity"
    assert SystemdInputCode.TOPOLOGY in _codes(_policy(), topology)

    policy = deepcopy(_policy())
    policy["api_key"] = "sk-forbidden"
    assert SystemdInputCode.SECRET in _codes(policy)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "subnet_drift", "public_facing", "wrong_owner", "already_created"],
)
def test_container_network_drift_fails_closed(mutation: str) -> None:
    """The unit graph must create exactly the subnets host admission allocated."""
    policy = deepcopy(_policy())
    networks = _object_list(policy["container_networks"])
    first = _object_map(networks[0])
    if mutation == "missing":
        networks.pop()
    elif mutation == "extra":
        networks.append(dict(first, network_id="asklegal-extra", subnet="10.90.20.0/24"))
    elif mutation == "subnet_drift":
        first["subnet"] = "10.99.0.0/24"
    elif mutation == "public_facing":
        first["internal"] = not first["internal"]
    elif mutation == "wrong_owner":
        first["created_by_unit"] = "asklegal-control-plane.service"
    else:
        first["created"] = True
    assert SystemdInputCode.NETWORK in _codes(policy)


def test_network_subnets_follow_the_host_allocation_rather_than_a_local_copy() -> None:
    """Changing the host allocation must invalidate the unit graph, not be ignored."""
    host_policy = deepcopy(_host_policy())
    runtime = _object_map(host_policy["runtime"])
    subnets = _object_map(runtime["selected_private_subnets"])
    subnets["asklegal-register"] = "10.91.0.0/24"
    assert SystemdInputCode.NETWORK in _codes(_policy(), host_policy=host_policy)
