"""Focused tests for the offline interview demonstration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from asklegal_application_runtime import CredentialMaterial
from asklegal_contracts import parse_json_bytes
from asklegal_review_api.api import create_app, local_dependencies
from httpx import ASGITransport, AsyncClient

from tools.interview_demo import InterviewDemoError, prepare_interview_demo

if TYPE_CHECKING:
    from fastapi import FastAPI

_ROOT = Path(__file__).resolve().parents[2]
_TOKEN = "asklegal-offline-interview-demo"


async def _review_round_trip(
    prepared_root: Path,
    app: FastAPI,
    proposal_id: str,
    *,
    action: str,
    expected: str,
) -> None:
    transport = ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {_TOKEN}",
        "Origin": "http://127.0.0.1:8002",
    }
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        detail = await client.get(f"/api/v1/proposal-packages/{proposal_id}", headers=headers)
        assert detail.status_code == 200
        decision = await client.post(
            f"/api/v1/proposal-packages/{proposal_id}/decisions",
            headers={
                **headers,
                "Content-Type": "application/json",
                "Idempotency-Key": "cmd_" + "a" * 48,
                "If-Match": str(detail.headers["etag"]),
            },
            json={
                "action": action,
                "manifest_fingerprint": detail.json()["proposal"]["manifest_fingerprint"],
                "reason": "Interview operator reviewed the complete synthetic proposal",
            },
        )
        retained = await client.get(
            f"/api/v1/proposal-packages/{proposal_id}",
            headers=headers,
        )
    assert decision.status_code == 200
    assert decision.json()["result_code"] == expected
    assert retained.status_code == 200
    assert retained.json()["proposal"]["status"] == expected
    assert retained.json()["proposal"]["review_version"] == 1
    assert retained.json()["decision"]["decision"] == expected
    assert (prepared_root / "review-state/approval-register.json").is_file()


async def _assert_retained_after_restart(app: FastAPI, proposal_id: str, expected: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        retained = await client.get(
            f"/api/v1/proposal-packages/{proposal_id}",
            headers={
                "Authorization": f"Bearer {_TOKEN}",
                "Origin": "http://127.0.0.1:8002",
            },
        )
        proposals = await client.get(
            "/api/v1/proposal-packages",
            headers={
                "Authorization": f"Bearer {_TOKEN}",
                "Origin": "http://127.0.0.1:8002",
            },
        )
    assert retained.status_code == 200
    assert retained.json()["proposal"]["status"] == expected
    assert retained.json()["decision"]["decision"] == expected
    assert proposals.status_code == 200
    assert [item["proposal_id"] for item in proposals.json()["items"]] == [proposal_id]
    assert proposals.json()["items"][0]["status"] == expected


async def _assert_report_visible(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/demo/change-report.json")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.json()["schema_id"] == "asklegal.offline-interview-change-report/v1"
    assert response.json()["change_counts"] == {
        "additions": 0,
        "replacements": 2,
        "retirements": 0,
        "unchanged": 0,
        "withholdings": 0,
    }
    assert [change["material_type"] for change in response.json()["changes"]] == [
        "Case",
        "Legislation",
    ]
    assert [change["action"] for change in response.json()["changes"]] == [
        "UPDATED",
        "UPDATED",
    ]
    assert response.json()["no_change_scope_ids"] == [
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-SUBSIDIARY",
    ]
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        config = await client.get("/demo/config.json")
    assert config.status_code == 200
    assert config.json() == {"review_token": _TOKEN}


@pytest.mark.parametrize(
    ("action", "expected"),
    [("APPROVE", "APPROVED"), ("REJECT", "REJECTED")],
)
def test_prepare_demo_runs_golden_proof_and_persists_separate_review_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    expected: str,
) -> None:
    """The two honest demo halves work and the UI decision reaches durable state."""
    prepared = prepare_interview_demo(
        workspace_root=tmp_path,
        fixture_repository_root=_ROOT,
    )

    assert prepared.root == tmp_path / "var/interview-demo"
    assert prepared.proof.result_code == "GOLDEN_FLOW_RECOVERED"
    summary = parse_json_bytes(
        (prepared.root / "demo-summary.json").read_bytes(),
        max_bytes=100_000,
    )
    assert isinstance(summary, dict)
    assert summary.get("external_systems") == "LOCAL_FAKES_ONLY"
    review_demo = summary.get("review_demo")
    assert isinstance(review_demo, dict)
    assert review_demo.get("ui_approval_drives_e2e_proof") is False
    assert (prepared.root / "e2e-proof/E2E-001/result.json").is_file()
    assert (prepared.root / "change-report.json").is_file()
    asyncio.run(_assert_report_visible(prepared.review_app))

    asyncio.run(
        _review_round_trip(
            prepared.root,
            prepared.review_app,
            prepared.review_fixture.proposal_id,
            action=action,
            expected=expected,
        )
    )
    monkeypatch.setenv("ASKLEGAL_LOCAL_REVIEW_DECISION_TIME", "2026-08-16T00:00:00Z")
    monkeypatch.setenv("ASKLEGAL_LOCAL_REVIEW_COMMAND_EXPIRES_AT", "2026-08-16T00:05:00Z")
    restarted = local_dependencies(
        state_root=prepared.root / "review-state",
        artifact_root=prepared.root / "review-artifacts",
        authority_path=prepared.root / "review-authority.json",
        review_api_credential=CredentialMaterial(_TOKEN.encode("ascii")),
        allowed_origin="http://127.0.0.1:8002",
    )
    asyncio.run(
        _assert_retained_after_restart(
            create_app(restarted),
            prepared.review_fixture.proposal_id,
            expected,
        )
    )


def test_prepare_demo_refuses_to_delete_an_unmarked_exact_root(tmp_path: Path) -> None:
    """An unrelated directory can never be mistaken for disposable demo state."""
    root = tmp_path / "var/interview-demo"
    root.mkdir(parents=True)
    (root / "operator-file.txt").write_text("preserve me", encoding="utf-8")

    with pytest.raises(InterviewDemoError, match="INTERVIEW_DEMO_MARKER_MISSING_OR_INVALID"):
        prepare_interview_demo(
            workspace_root=tmp_path,
            fixture_repository_root=_ROOT,
        )

    assert (root / "operator-file.txt").read_text(encoding="utf-8") == "preserve me"
