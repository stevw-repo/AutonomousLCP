"""Focused tests for exact host-apply authority issuance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from tools.hk_v1_host_apply import load_host_apply_authority
from tools.hk_v1_host_reconcile import (
    build_host_reconcile_plan,
    host_reconcile_plan_document,
)
from tools.hk_v1_issue_host_apply_authority import (
    HostApplyAuthorityIssueError,
    issue_host_apply_authority,
)
from tools.v1_poc_collect_host_facts import load_host_facts_output

_AUTHORITY = "auth_" + "a" * 48
_INCOMPLETE_BLOCKERS = {
    "ACTIONABLE_HOST_INVENTORY_UNAVAILABLE",
    "HOST_FACTS_INCOMPLETE",
    "RECOVERY_PREFLIGHT_REPORT_INVALID",
    "RECOVERY_PREFLIGHT_REPORT_REQUIRED",
}


def test_issued_authority_is_accepted_by_owning_parser(tmp_path: Path) -> None:
    """Every action, target, root, and plan identity is rebound exactly."""
    repository = Path(__file__).resolve().parents[2]
    facts = repository / "var/hk-v1/host/post-image-build-root.json"
    if not facts.is_file():
        return
    plan = build_host_reconcile_plan(repository, load_host_facts_output(facts))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(host_reconcile_plan_document(plan), separators=(",", ":"), sort_keys=True) + "\n"
    )
    state_root = (tmp_path / "state").resolve()
    state_root.mkdir()
    if not plan.actions or _INCOMPLETE_BLOCKERS.intersection(plan.blockers):
        with pytest.raises(HostApplyAuthorityIssueError, match="HOST_APPLY_PLAN_NOT_ACTIONABLE"):
            issue_host_apply_authority(
                plan_path=plan_path.resolve(),
                repository_root=repository,
                state_root=state_root,
                authority_id=_AUTHORITY,
            )
    else:
        raw = issue_host_apply_authority(
            plan_path=plan_path.resolve(),
            repository_root=repository,
            state_root=state_root,
            authority_id=_AUTHORITY,
        )
        authority_path = tmp_path / "authority.json"
        authority_path.write_bytes(raw)
        assert load_host_apply_authority(
            authority_path.resolve(), plan_path.resolve(), repository, state_root
        ).startswith("sha256:")
        assert cast("dict[str, object]", json.loads(raw))["plan_fingerprint"] == plan.fingerprint


def test_authority_id_is_closed(tmp_path: Path) -> None:
    """Caller text cannot substitute for an exact opaque authority identity."""
    repository = Path(__file__).resolve().parents[2]
    facts = repository / "var/hk-v1/host/post-image-build-root.json"
    if not facts.is_file():
        return
    plan = build_host_reconcile_plan(repository, load_host_facts_output(facts))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(host_reconcile_plan_document(plan), separators=(",", ":"), sort_keys=True) + "\n"
    )
    state_root = (tmp_path / "state").resolve()
    state_root.mkdir()
    with pytest.raises(ValueError, match="HOST_APPLY_AUTHORITY_ID_INVALID"):
        issue_host_apply_authority(
            plan_path=plan_path.resolve(),
            repository_root=repository,
            state_root=state_root,
            authority_id="user-said-everything",
        )
