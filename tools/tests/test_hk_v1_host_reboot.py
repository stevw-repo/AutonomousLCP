"""Focused no-host tests for the exact reboot planner and executor."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tools.hk_v1_host_reboot import (
    HostRebootError,
    RebootCommandResult,
    build_host_reboot_authority,
    build_host_reboot_plan,
    host_reboot_plan_bytes,
    parse_host_reboot_readback,
    parse_host_reboot_readback_details,
    run_host_reboot,
)
from tools.tests.test_hk_v1_admission_operational_evidence import operational_host_facts


def _empty_calls() -> list[tuple[str, ...]]:
    return []


@dataclass
class _Runner:
    results: list[RebootCommandResult] = field(
        default_factory=lambda: [RebootCommandResult(0, "accepted", "")]
    )
    calls: list[tuple[str, ...]] = field(default_factory=_empty_calls)

    def run(self, argv: tuple[str, ...]) -> RebootCommandResult:
        self.calls.append(argv)
        return self.results.pop(0)


class _CrashRunner:
    def run(self, argv: tuple[str, ...]) -> RebootCommandResult:
        raise RuntimeError(argv)


def _inputs(tmp_path: Path) -> tuple[bytes, bytes, Path, Path, datetime]:
    pre = operational_host_facts("sha256:" + "1" * 64)
    post = tmp_path / "post-host.json"
    state = tmp_path / "state" / "reboot.json"
    plan = build_host_reboot_plan(pre, post, state)
    now = datetime(2026, 9, 9, 2, 0, tzinfo=UTC)
    authority = build_host_reboot_authority(
        plan,
        authority_id="auth_" + "2" * 48,
        signer_subject="person-local-1",
        authorized_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=5),
    )
    return host_reboot_plan_bytes(plan), authority, post, state, now


def test_plan_is_no_effect_and_execution_issues_only_fixed_reboot(tmp_path: Path) -> None:
    """Planning is inert and execution invokes only the frozen systemctl argv."""
    plan, authority, _post, state, now = _inputs(tmp_path)
    runner = _Runner()
    result = run_host_reboot(plan, authority, now=now, runner=runner)
    assert runner.calls == [("/usr/bin/systemctl", "reboot", "--no-wall")]
    assert b'"phase":"AWAITING_REBOOT"' in result
    assert state.read_bytes() == result


def test_restart_adopts_changed_boot_without_reissuing_reboot(tmp_path: Path) -> None:
    """A changed boot identity completes from retained state without a second command."""
    plan, authority, post, _state, now = _inputs(tmp_path)
    runner = _Runner()
    run_host_reboot(plan, authority, now=now, runner=runner)
    post.write_bytes(operational_host_facts("sha256:" + "3" * 64))
    result = run_host_reboot(plan, authority, now=now + timedelta(minutes=1), runner=runner)
    assert len(runner.calls) == 1
    assert b'"phase":"COMPLETE"' in result
    assert parse_host_reboot_readback(result, post.read_bytes()) == "sha256:" + "3" * 64

    details = parse_host_reboot_readback_details(result, post.read_bytes())
    plan_document = json.loads(plan)
    state_document = json.loads(result)
    assert details.operation_id.startswith("rbt_")
    assert details.pre_boot_id_fingerprint == "sha256:" + "1" * 64
    assert details.post_boot_id_fingerprint == "sha256:" + "3" * 64
    assert details.pre_host_facts_fingerprint == plan_document["pre_host_facts_fingerprint"]
    assert details.post_host_facts_fingerprint == state_document["post_host_facts_fingerprint"]
    assert details.state_fingerprint == state_document["fingerprint"]


def test_same_boot_never_claims_complete_or_reissues(tmp_path: Path) -> None:
    """A stale post-host snapshot cannot prove completion or trigger another reboot."""
    plan, authority, post, _state, now = _inputs(tmp_path)
    runner = _Runner()
    first = run_host_reboot(plan, authority, now=now, runner=runner)
    post.write_bytes(operational_host_facts("sha256:" + "1" * 64))
    second = run_host_reboot(plan, authority, now=now + timedelta(minutes=1), runner=runner)
    assert second == first
    assert len(runner.calls) == 1


def test_expired_or_drifted_authority_stops_before_command(tmp_path: Path) -> None:
    """Expired or modified authority bytes are inert."""
    plan, authority, _post, _state, now = _inputs(tmp_path)
    runner = _Runner()
    with pytest.raises(HostRebootError, match="HOST_REBOOT_AUTHORITY_EXPIRED"):
        run_host_reboot(plan, authority, now=now + timedelta(hours=1), runner=runner)
    assert runner.calls == []
    tampered = authority.replace(b"person-local-1", b"person-local-2")
    with pytest.raises(HostRebootError, match="HOST_REBOOT_AUTHORITY_INVALID"):
        run_host_reboot(plan, tampered, now=now, runner=runner)
    assert runner.calls == []


def test_failed_command_is_terminal_and_never_retried(tmp_path: Path) -> None:
    """A known command refusal is retained and not retried under one-shot authority."""
    plan, authority, _post, _state, now = _inputs(tmp_path)
    runner = _Runner([RebootCommandResult(1, "", "denied")])
    first = run_host_reboot(plan, authority, now=now, runner=runner)
    second = run_host_reboot(plan, authority, now=now, runner=runner)
    assert b'"phase":"FAILED"' in first
    assert second == first
    assert len(runner.calls) == 1


def test_changed_boot_reconciles_after_command_ack_is_lost(tmp_path: Path) -> None:
    """A reboot between command invocation and receipt retention is adopted exactly once."""
    plan, authority, post, _state, now = _inputs(tmp_path)
    with pytest.raises(RuntimeError):
        run_host_reboot(plan, authority, now=now, runner=_CrashRunner())
    post.write_bytes(operational_host_facts("sha256:" + "4" * 64))
    result = run_host_reboot(plan, authority, now=now + timedelta(minutes=1), runner=_Runner())
    assert b'"outcome":"ADOPTED_FROM_CHANGED_BOOT"' in result
    assert parse_host_reboot_readback(result, post.read_bytes()) == "sha256:" + "4" * 64
