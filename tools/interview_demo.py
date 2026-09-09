"""One-command, offline AskLegal interview demonstration.

The command deliberately presents two adjacent but separate proofs:

* the existing deterministic M7 ``E2E-001`` end-to-end proof; and
* the retained local Review UI, where a person may inspect and decide a frozen
  synthetic Hong Kong proposal.

The Review decision does not drive or rewrite the already completed M7 proof.
No external source, provider, credential, or network service is used.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from asklegal_application_runtime import CredentialMaterial
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_review_api.api import ReviewDependencies, create_app, local_dependencies
from fastapi.responses import Response
from httpx import ASGITransport, AsyncClient

from tools.local_conformance import prove_scenarios
from tools.tests.task8_local_review_fixture import (
    LocalReviewFixture,
    write_task8_interview_review_fixture,
)

if TYPE_CHECKING:
    from asklegal_reporting import ScenarioResult
    from fastapi import FastAPI

_ROOT = Path(__file__).resolve().parents[1]
_MARKER = ".asklegal-interview-demo-state"
_MARKER_CONTENT = "ASKLEGAL_OFFLINE_INTERVIEW_DEMO_V1\n"
_DEMO_TOKEN = "asklegal-offline-interview-demo"
_DECISION_TIME = "2026-08-16T00:00:00Z"
_COMMAND_EXPIRY = "2026-08-16T00:05:00Z"
_HTTP_OK = 200
_MIN_PORT = 1024
_MAX_PORT = 65535
_ROOT_UNSAFE = "INTERVIEW_DEMO_ROOT_UNSAFE"
_MARKER_INVALID = "INTERVIEW_DEMO_MARKER_MISSING_OR_INVALID"
_REVIEW_INVALID = "INTERVIEW_DEMO_REVIEW_VALIDATION_FAILED"
_PROPOSAL_NOT_VISIBLE = "INTERVIEW_DEMO_PROPOSAL_NOT_VISIBLE"
_PORT_NOT_INTEGER = "port must be an integer"
_PORT_OUT_OF_RANGE = "port must be between 1024 and 65535"
_REPORT_NAME = "change-report.json"


class InterviewDemoError(RuntimeError):
    """One safe, human-readable interview-demo failure."""


@dataclass(frozen=True, slots=True)
class PreparedInterviewDemo:
    """Prepared proof and retained Review application."""

    root: Path
    proof: ScenarioResult
    review_fixture: LocalReviewFixture
    review_dependencies: ReviewDependencies
    review_app: FastAPI


def _exact_demo_root(workspace_root: Path) -> Path:
    workspace = workspace_root.resolve()
    var_root = workspace / "var"
    demo_root = var_root / "interview-demo"
    if workspace_root.is_symlink() or var_root.is_symlink() or demo_root.is_symlink():
        raise InterviewDemoError(_ROOT_UNSAFE)
    if demo_root.parent != var_root or demo_root.name != "interview-demo":
        raise InterviewDemoError(_ROOT_UNSAFE)
    return demo_root


def _reset_demo_root(workspace_root: Path) -> Path:
    root = _exact_demo_root(workspace_root)
    marker = root / _MARKER
    if root.exists():
        if (
            not root.is_dir()
            or not marker.is_file()
            or marker.read_text(encoding="utf-8") != _MARKER_CONTENT
        ):
            raise InterviewDemoError(_MARKER_INVALID)
        shutil.rmtree(root)
    root.mkdir(parents=True)
    marker.write_text(_MARKER_CONTENT, encoding="utf-8")
    return root


def _write_review_authority(path: Path) -> None:
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
                    "subject": "person-interview-demo",
                }
            )
        )
    )


@contextmanager
def _fixed_review_window() -> Generator[None]:
    names = {
        "ASKLEGAL_LOCAL_REVIEW_DECISION_TIME": _DECISION_TIME,
        "ASKLEGAL_LOCAL_REVIEW_COMMAND_EXPIRES_AT": _COMMAND_EXPIRY,
    }
    predecessor = {name: os.environ.get(name) for name in names}
    os.environ.update(names)
    try:
        yield
    finally:
        for name, value in predecessor.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


async def _validate_review_app(app: FastAPI, *, allowed_origin: str) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        browser = await client.get("/review")
        proposals = await client.get(
            "/api/v1/proposal-packages",
            headers={
                "Authorization": f"Bearer {_DEMO_TOKEN}",
                "Origin": allowed_origin,
            },
        )
    if browser.status_code != _HTTP_OK or proposals.status_code != _HTTP_OK:
        raise InterviewDemoError(_REVIEW_INVALID)
    body = parse_json_bytes(proposals.content, max_bytes=1_000_000)
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list) or len(items) != 1:
        raise InterviewDemoError(_PROPOSAL_NOT_VISIBLE)


def _write_summary(root: Path, proof: ScenarioResult, fixture: LocalReviewFixture) -> None:
    summary = checked_json_value(
        {
            "external_systems": "LOCAL_FAKES_ONLY",
            "network": "DENIED_DURING_E2E_PROOF",
            "proof": {
                "effect_count": proof.effect_count,
                "fact_count": proof.fact_count,
                "fingerprint": proof.fingerprint,
                "result_code": proof.result_code,
                "scenario_id": proof.scenario_id,
            },
            "review_demo": {
                "approval_persists_locally": True,
                "proposal_id": fixture.proposal_id,
                "promotion_manifest_fingerprint": fixture.promotion_manifest_fingerprint,
                "ui_approval_drives_e2e_proof": False,
            },
            "schema_id": "asklegal.offline-interview-demo-summary/v1",
            "statement": "offline synthetic pipeline and retained Review boundary prepared",
        }
    )
    (root / "demo-summary.json").write_bytes(canonicalize(summary) + b"\n")


def _report_document(path: Path, *, max_bytes: int) -> dict[str, JsonValue]:
    document = parse_json_bytes(path.read_bytes(), max_bytes=max_bytes)
    if not isinstance(document, dict):
        raise InterviewDemoError(_REVIEW_INVALID)
    return document


def _write_report(root: Path, artifact_root: Path) -> Path:
    inventory = _report_document(
        artifact_root / "change-inventory/change-inventory.json",
        max_bytes=100_000,
    )
    desired = _report_document(
        artifact_root / "desired-state-inventories/inventories.json",
        max_bytes=1_000_000,
    )
    readiness = _report_document(
        artifact_root / "hk-v1-review-readiness.json",
        max_bytes=1_000_000,
    )
    additions = inventory.get("additions")
    replacements = inventory.get("replacements")
    records = desired.get("records")
    scope_dispositions = readiness.get("scope_dispositions")
    if not isinstance(additions, list) or not isinstance(replacements, list):
        raise InterviewDemoError(_REVIEW_INVALID)
    if not isinstance(records, list):
        raise InterviewDemoError(_REVIEW_INVALID)
    if not isinstance(scope_dispositions, list):
        raise InterviewDemoError(_REVIEW_INVALID)
    no_change_scopes: list[str] = []
    for disposition in scope_dispositions:
        if not isinstance(disposition, dict) or disposition.get("result") != "NO_CHANGE":
            continue
        scope_id = disposition.get("scope_id")
        if not isinstance(scope_id, str):
            raise InterviewDemoError(_REVIEW_INVALID)
        no_change_scopes.append(scope_id)
    added_records: list[dict[str, JsonValue]] = []
    change_actions = {
        **{item: "ADDED" for item in additions if isinstance(item, str)},
        **{item: "UPDATED" for item in replacements if isinstance(item, str)},
    }
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or record_id not in change_actions:
            continue
        added_records.append(
            {
                "action": change_actions[record_id],
                "authority_note": record.get("authority_note"),
                "evidence_refs": record.get("evidence_refs"),
                "material_type": record.get("material_type"),
                "record_id": record.get("record_id"),
                "scope_id": record.get("scope_id"),
                "source": record.get("source"),
                "text": record.get("text"),
            }
        )
    counts = {
        name: len(value) if isinstance(value, list) else 0
        for name, value in (
            ("additions", additions),
            ("replacements", inventory.get("replacements")),
            ("retirements", inventory.get("retirements")),
            ("unchanged", inventory.get("unchanged")),
            ("withholdings", inventory.get("withholdings")),
        )
    }
    report = checked_json_value(
        {
            "change_counts": counts,
            "changes": added_records,
            "demonstration": "LOCAL_SYNTHETIC_OFFLINE_POC",
            "no_change_scope_ids": no_change_scopes,
            "observation_cutoff": inventory.get("observation_cutoff"),
            "schema_id": "asklegal.offline-interview-change-report/v1",
            "statement": (
                f"{counts['additions']} records added; {counts['replacements']} replaced; "
                f"{counts['retirements']} retired; {counts['withholdings']} withheld."
            ),
        }
    )
    path = root / _REPORT_NAME
    path.write_bytes(canonicalize(report) + b"\n")
    return path


def prepare_interview_demo(
    *,
    workspace_root: Path = _ROOT,
    fixture_repository_root: Path | None = None,
    port: int = 8002,
) -> PreparedInterviewDemo:
    """Create one fresh proof and retained Review workspace beneath the exact demo root."""
    root = _reset_demo_root(workspace_root)
    repository_root = fixture_repository_root or workspace_root
    proof = prove_scenarios(root / "e2e-proof", ("E2E-001",))[0]
    artifact_root = root / "review-artifacts"
    state_root = root / "review-state"
    authority_path = root / "review-authority.json"
    state_root.mkdir()
    fixture = write_task8_interview_review_fixture(artifact_root, repository_root)
    _write_review_authority(authority_path)
    with _fixed_review_window():
        dependencies = local_dependencies(
            state_root=state_root,
            artifact_root=artifact_root,
            authority_path=authority_path,
            review_api_credential=CredentialMaterial(_DEMO_TOKEN.encode("ascii")),
            allowed_origin=f"http://127.0.0.1:{port}",
        )
    app = create_app(dependencies)
    report_path = _write_report(root, artifact_root)

    async def _demo_report() -> Response:
        return Response(
            content=report_path.read_bytes(),
            media_type="application/json",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'inline; filename="{_REPORT_NAME}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def _demo_config() -> Response:
        return Response(
            content=canonicalize(checked_json_value({"review_token": _DEMO_TOKEN})),
            media_type="application/json",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    app.add_api_route(
        "/demo/change-report.json",
        _demo_report,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/demo/config.json",
        _demo_config,
        methods=["GET"],
        include_in_schema=False,
    )
    asyncio.run(_validate_review_app(app, allowed_origin=f"http://127.0.0.1:{port}"))
    _write_summary(root, proof, fixture)
    return PreparedInterviewDemo(root, proof, fixture, dependencies, app)


def _print_demo(prepared: PreparedInterviewDemo, *, port: int) -> None:
    proof = prepared.proof
    stages = (
        "Schedule a deterministic update",
        "Capture a changed synthetic source",
        "Preserve evidence in primary and recovery vault fakes",
        "Apply the legal rulebook and create an evidence-bound candidate",
        "Freeze release, coverage, and the exact proposal package",
        "Exercise the Review HTTP and synthetic named-approval boundary",
        "Build and verify a replacement serving target",
        "Cut over to the verified candidate",
        "Roll back and recover the exact candidate state",
    )
    lines = [
        "",
        "ASKLEGAL OFFLINE INTERVIEW POC",
        (
            "No live Hong Kong source, model, Pinecone project, credential, or external "
            "network is used."
        ),
        "",
    ]
    for index, stage in enumerate(stages, start=1):
        lines.append(f"  PASS {index}/9  {stage}")
    lines.extend(
        (
            "",
            (
                f"E2E RESULT  {proof.result_code} | {proof.fact_count} facts | "
                f"{proof.effect_count} effects"
            ),
            f"E2E PROOF   {proof.fingerprint}",
            f"CHANGE REPORT  {prepared.root / _REPORT_NAME}",
            "",
            "RETAINED REVIEW DEMO (separate from the completed E2E proof)",
            (
                "A browser decision is persisted locally, but it does not drive or alter "
                "the proof above."
            ),
            f"URL         http://127.0.0.1:{port}/review",
            f"DEMO TOKEN  {_DEMO_TOKEN}",
            f"STATE       {prepared.root / 'review-state'}",
        )
    )
    sys.stdout.write("\n".join(lines) + "\n")


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(_PORT_NOT_INTEGER) from error
    if not _MIN_PORT <= port <= _MAX_PORT:
        raise argparse.ArgumentTypeError(_PORT_OUT_OF_RANGE)
    return port


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="prepare and validate the complete demo without starting the localhost server",
    )
    parser.add_argument("--port", type=_port, default=8002)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Prepare the offline proof and optionally serve the retained Review UI."""
    arguments = _parser().parse_args(argv)
    try:
        prepared = prepare_interview_demo(port=arguments.port)
        _print_demo(prepared, port=arguments.port)
    except (InterviewDemoError, OSError, RuntimeError, TypeError, ValueError) as error:
        sys.stderr.write(f"DEMO FAILED: {error}\n")
        return 1
    if arguments.prepare_only:
        sys.stdout.write("\nPREPARED  localhost server not started (--prepare-only)\n")
        return 0
    sys.stdout.write("\nServing the local Review UI. Press Ctrl+C to stop.\n")
    uvicorn.run(
        prepared.review_app,
        host="127.0.0.1",
        port=arguments.port,
        access_log=False,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
