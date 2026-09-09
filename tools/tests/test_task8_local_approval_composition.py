"""Boundary-allowed local Review Approval to promotion composition proof."""

# Pytest discovers the deliberately private fixture by decoration.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import runpy
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from asklegal_application_runtime import CredentialMaterial
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_management_register_ports import ApprovalError
from asklegal_promotion import (
    LocalBackupStore,
    LocalCoverageStore,
    LocalEmbeddingAdapter,
    LocalRoutingStore,
    LocalServingStateStore,
    LocalServingTargetStore,
    PromotionManifest,
    PromotionPlan,
    freeze_v1_promotion_manifest,
)
from asklegal_promotion_worker import (
    LocalRetainedPromotionApprovalStore,
    PromotionDependencies,
    PromotionExecutionContext,
    compose_hk_v1_local_promotion_service,
)
from asklegal_review_api.api import local_dependencies
from asklegal_review_api.governance import ReviewCommand
from asklegal_review_api.v1_infrastructure import V1ReviewInfrastructure, v1_dependencies

from tools.tests.task8_local_review_fixture import write_task8_local_review_fixture

_ROOT = Path(__file__).resolve().parents[2]
_M6 = runpy.run_path(str(_ROOT / "apps/promotion-worker/tests/test_m6_promotion.py"))
_MANIFEST = cast("Callable[[], PromotionManifest]", _M6["task8_v1_manifest_fixture"])
_PLAN = cast("Callable[[PromotionManifest], PromotionPlan]", _M6["task8_plan_from_manifest"])
_TOKEN_COUNTER = _M6["TASK8_TOKEN_COUNTER"]
_REVIEW_CREDENTIAL = CredentialMaterial(b"task8-review-focused-test-credential")
_REVIEW_AUTHORIZATION = "Bearer task8-review-focused-test-credential"


@pytest.fixture(autouse=True)
def _fixed_review_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the frozen Task 8 package inside its exact decision window."""
    monkeypatch.setenv("ASKLEGAL_LOCAL_REVIEW_DECISION_TIME", "2026-08-16T00:00:00Z")
    monkeypatch.setenv("ASKLEGAL_LOCAL_REVIEW_COMMAND_EXPIRES_AT", "2026-08-16T00:05:00Z")


def _authority(root: Path) -> Path:
    path = root / "review-authority.json"
    path.write_bytes(
        canonicalize(
            checked_json_value(
                {
                    "authority_evidence_fingerprint": "sha256:" + "2" * 64,
                    "authority_evidence_id": "evi_" + "2" * 48,
                    "reviewer_identity_fingerprint": "sha256:" + "1" * 64,
                    "reviewer_identity_id": "act_" + "1" * 48,
                    "roles": ["PipelineAdministrator"],
                    "schema_id": "asklegal.local-review-authority/v1",
                    "subject": "person-local-1",
                }
            )
        )
    )
    return path


def test_default_review_approval_is_consumed_by_real_local_promotion_service(
    tmp_path: Path,
) -> None:
    """One retained human decision crosses the application boundary after restart."""
    artifact_root = tmp_path / "pipeline-artifacts"
    fixture = write_task8_local_review_fixture(artifact_root, _ROOT)
    state_root = tmp_path / "review-state"
    review = local_dependencies(
        state_root=state_root,
        artifact_root=artifact_root,
        authority_path=_authority(tmp_path),
        review_api_credential=_REVIEW_CREDENTIAL,
    )
    detail = review.projections.detail(fixture.proposal_id)
    assert detail is not None
    assert review.governance is not None
    outcome = review.governance.submit(
        ReviewCommand(
            "cmd_" + "a" * 48,
            detail.proposal.proposal_id,
            0,
            {
                "action": "APPROVE",
                "manifest_fingerprint": detail.proposal.manifest_fingerprint,
                "reason": "Reviewed exact frozen local V1 package",
            },
            review.identity.verify(_REVIEW_AUTHORIZATION),
        )
    )

    base = _MANIFEST()
    manifest = freeze_v1_promotion_manifest(
        replace(_PLAN(base), validity_predicates=detail.validity_predicates)
    )
    assert manifest.manifest_id == detail.promotion_manifest_id
    assert manifest.fingerprint == detail.proposal.manifest_fingerprint
    approval_store = LocalRetainedPromotionApprovalStore(state_root / "approval-register.json")
    states = LocalServingStateStore(manifest.base_serving_state_id)
    service = compose_hk_v1_local_promotion_service(
        PromotionDependencies(
            approval_store,
            LocalEmbeddingAdapter(),
            _TOKEN_COUNTER,
            LocalServingTargetStore(),
            LocalBackupStore(),
            LocalRoutingStore(manifest.base_serving_state_id),
            LocalCoverageStore(manifest.coverage_status),
            states,
        ),
        approval_store,
    )

    composition, result = service.execute_hk_v1(
        manifest,
        outcome.result_ref,
        "exe_" + "1" * 48,
        PromotionExecutionContext(
            manifest.base_serving_state_id,
            manifest.validity_predicates,
            "2026-08-16T01:00:00Z",
        ),
    )

    assert result.state == "EXECUTION_SUCCEEDED"
    assert composition.model_profile_fingerprint.startswith("sha256:")
    assert states.active_state_id == manifest.candidate_serving_state_id
    restarted = LocalRetainedPromotionApprovalStore(state_root / "approval-register.json")
    assert restarted.get(outcome.result_ref).execution_lineage_id == "exe_" + "1" * 48

    with pytest.raises(RuntimeError, match="LOCAL_APPROVAL_LEDGER_CONFLICT"):
        review.governance.submit(
            ReviewCommand(
                "cmd_" + "c" * 48,
                outcome.result_ref,
                1,
                {
                    "action": "REVOKE",
                    "approval_ref": outcome.result_ref,
                    "manifest_fingerprint": detail.proposal.manifest_fingerprint,
                    "reason": "Stale Review process must not overwrite consumption",
                },
                review.identity.verify(_REVIEW_AUTHORIZATION),
            )
        )
    retained = LocalRetainedPromotionApprovalStore(state_root / "approval-register.json")
    assert retained.get(outcome.result_ref).state.value == "APPROVAL_CONSUMED"


def test_continuous_v1_review_restart_exposes_named_approval_to_promotion_port(
    tmp_path: Path,
) -> None:
    """The service composition and promotion-side reader share one retained ledger."""
    artifact_root = tmp_path / "pipeline-artifacts"
    fixture = write_task8_local_review_fixture(artifact_root, _ROOT)
    state_root = tmp_path / "review-state"
    state_root.mkdir()
    environment = {
        "ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT": str(artifact_root),
        "ASKLEGAL_LOCAL_REVIEW_STATE_ROOT": str(state_root),
        "ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH": str(_authority(tmp_path)),
        "ASKLEGAL_LOCAL_REVIEW_DECISION_TIME": "2026-08-16T00:00:00Z",
        "ASKLEGAL_LOCAL_REVIEW_COMMAND_EXPIRES_AT": "2026-08-16T00:05:00Z",
    }
    infrastructure = V1ReviewInfrastructure.__new__(V1ReviewInfrastructure)
    object.__setattr__(infrastructure, "review_api_credential", _REVIEW_CREDENTIAL)
    review = v1_dependencies(infrastructure, environment)
    detail = review.projections.detail(fixture.proposal_id)
    assert detail is not None
    assert review.governance is not None
    outcome = review.governance.submit(
        ReviewCommand(
            "cmd_" + "d" * 48,
            detail.proposal.proposal_id,
            0,
            {
                "action": "APPROVE",
                "manifest_fingerprint": detail.proposal.manifest_fingerprint,
                "reason": "Named local human reviewed the exact frozen V1 package",
            },
            review.identity.verify(_REVIEW_AUTHORIZATION),
        )
    )

    restarted = v1_dependencies(infrastructure, environment)
    assert restarted.governance is not None
    promotion_port = LocalRetainedPromotionApprovalStore(state_root / "approval-register.json")
    retained = promotion_port.get(outcome.result_ref)
    assert retained.decision.reviewer_subject == "person-local-1"
    assert retained.state.value == "APPROVAL_APPROVED"
    proposal, readiness = promotion_port.approved_package(outcome.result_ref)
    assert proposal == (artifact_root / "hk-v1-two-family-proposal.json").read_bytes()
    assert readiness == (artifact_root / "hk-v1-review-readiness.json").read_bytes()


def test_promotion_reader_rejects_rewritten_named_reviewer_command(
    tmp_path: Path,
) -> None:
    """Canonical rewriting cannot detach the named human from local authority."""
    artifact_root = tmp_path / "pipeline-artifacts"
    fixture = write_task8_local_review_fixture(artifact_root, _ROOT)
    state_root = tmp_path / "review-state"
    review = local_dependencies(
        state_root=state_root,
        artifact_root=artifact_root,
        authority_path=_authority(tmp_path),
        review_api_credential=_REVIEW_CREDENTIAL,
    )
    detail = review.projections.detail(fixture.proposal_id)
    assert detail is not None
    assert review.governance is not None
    review.governance.submit(
        ReviewCommand(
            "cmd_" + "e" * 48,
            detail.proposal.proposal_id,
            0,
            {
                "action": "APPROVE",
                "manifest_fingerprint": detail.proposal.manifest_fingerprint,
                "reason": "Named local human reviewed the exact frozen V1 package",
            },
            review.identity.verify(_REVIEW_AUTHORIZATION),
        )
    )
    state_path = state_root / "approval-register.json"
    state = parse_json_bytes(state_path.read_bytes(), max_bytes=5_000_000)
    assert isinstance(state, dict)
    events = state["events"]
    assert isinstance(events, list)
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, dict)
    command_hex = event["command_bytes"]
    assert isinstance(command_hex, str)
    command = parse_json_bytes(bytes.fromhex(command_hex), max_bytes=100_000)
    assert isinstance(command, dict)
    command["reviewer_subject"] = "person-forged"
    event["command_bytes"] = canonicalize(checked_json_value(command)).hex()
    state_path.write_bytes(canonicalize(checked_json_value(state)))

    with pytest.raises(ApprovalError):
        LocalRetainedPromotionApprovalStore(
            state_path,
            state_root / "review-authority.json",
        )


def test_promotion_reader_rejects_missing_approval_state_row(tmp_path: Path) -> None:
    """A truncated retained projection cannot reauthorize an Approval event."""
    artifact_root = tmp_path / "pipeline-artifacts"
    fixture = write_task8_local_review_fixture(artifact_root, _ROOT)
    state_root = tmp_path / "review-state"
    review = local_dependencies(
        state_root=state_root,
        artifact_root=artifact_root,
        authority_path=_authority(tmp_path),
        review_api_credential=_REVIEW_CREDENTIAL,
    )
    detail = review.projections.detail(fixture.proposal_id)
    assert detail is not None
    assert review.governance is not None
    outcome = review.governance.submit(
        ReviewCommand(
            "cmd_" + "b" * 48,
            detail.proposal.proposal_id,
            0,
            {
                "action": "APPROVE",
                "manifest_fingerprint": detail.proposal.manifest_fingerprint,
                "reason": "Reviewed exact frozen local V1 package",
            },
            review.identity.verify(_REVIEW_AUTHORIZATION),
        )
    )
    state_path = state_root / "approval-register.json"
    state = parse_json_bytes(state_path.read_bytes(), max_bytes=5_000_000)
    assert isinstance(state, dict)
    approval_states = state["approval_states"]
    assert isinstance(approval_states, dict)
    approval_states.pop(outcome.result_ref)
    state_path.write_bytes(canonicalize(checked_json_value(state)))

    with pytest.raises(ApprovalError):
        LocalRetainedPromotionApprovalStore(state_path)


def test_review_rejects_self_consistent_target_member_scope_drift(tmp_path: Path) -> None:
    """Review derives record ownership from DSI instead of trusting readiness display facts."""
    artifact_root = tmp_path / "pipeline-artifacts"
    write_task8_local_review_fixture(
        artifact_root,
        _ROOT,
        readiness_target_members=(
            ("rec_" + "1" * 48, "HK-LEG-ORDINANCES", "LEGISLATION"),
            ("rec_" + "2" * 48, "HK-CASE-BINDING-POST-1997", "CASES"),
        ),
    )

    with pytest.raises(RuntimeError, match="PROPOSAL_PACKAGE_INVALID"):
        local_dependencies(
            state_root=tmp_path / "review-state",
            artifact_root=artifact_root,
            authority_path=_authority(tmp_path),
            review_api_credential=_REVIEW_CREDENTIAL,
        )
