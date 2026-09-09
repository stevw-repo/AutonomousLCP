"""Focused tests for source-owned Gate A/B admission evidence."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from tools.hk_v1_admission_source_evidence import (
    RetainedSourceAttempt,
    SourceAdmissionEvidenceError,
    SourceExerciseInputs,
    build_source_authority_evidence,
    build_source_exercise_evidence,
    parse_source_authority_evidence,
    parse_source_exercise_evidence,
)

_CUTOFF = "2026-08-27T22:52:09+08:00"
_AUTHORITY = "sha256:" + "a" * 64
_EXECUTION = "sha256:" + "b" * 64
_SOURCES = {
    "GLD": ("HK-LEG-GLD-EGAZETTE",),
    "HKEL": (
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
    ),
    "JUDICIARY": ("HK-CASE-HKLII-DISCOVERY", "HK-CASE-JUDICIARY-LRS-INVENTORY"),
}


def _attempt(  # noqa: PLR0913 - compact exact report fixture.
    root: Path,
    family: str,
    attempt_id: str,
    *,
    result: str = "COMPLETE",
    predecessor: str | None = None,
    no_change: bool = False,
) -> RetainedSourceAttempt:
    body = f"{family}:{attempt_id}:{result}".encode()
    digest = sha256(body).hexdigest()
    object_key = f"objects/{digest}.bin"
    object_path = root / object_key
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(body)
    terminal = {
        "COMPLETE": "CAPTURED",
        "SOURCE_CONTRACT_CHANGED": "SOURCE_CONTRACT_CHANGED",
        "SOURCE_OUTAGE": "OUTAGE",
    }[result]
    procedure_terminal = {
        "COMPLETE": "COMPLETE",
        "SOURCE_CONTRACT_CHANGED": "SOURCE_CONTRACT_CHANGED",
        "SOURCE_OUTAGE": "INCOMPLETE",
    }[result]
    report = {
        "attempt_id": attempt_id,
        "authority_manifest_fingerprint": _AUTHORITY,
        "authority_provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "change_state": (
            "NO_CHANGE_OBSERVED"
            if no_change
            else "FIRST_OBSERVATION"
            if predecessor is None
            else "CHANGED_OBSERVED"
        ),
        "endpoint_counts": {terminal: 1},
        "endpoints": [
            {
                "body_fingerprint": "sha256:" + digest,
                "byte_length": len(body),
                "endpoint_id": "endpoint-" + attempt_id,
                "endpoint_version": "1.0.0",
                "media_type": "application/octet-stream",
                "method": "GET",
                "object_key": object_key,
                "requested_url": f"https://example.invalid/{attempt_id}",
                "status": 200 if result == "COMPLETE" else 503,
                "terminal_code": terminal,
            }
        ],
        "execution_authorization_fingerprint": _EXECUTION,
        "observation_cutoff": _CUTOFF,
        "predecessor_attempt_id": predecessor,
        "readback_verified": True,
        "result": result,
        "source_family": family,
        "source_procedures": [
            {
                "declared_member_count": 1,
                "source_id": source_id,
                "terminal_code": procedure_terminal,
            }
            for source_id in _SOURCES[family]
        ],
    }
    report_path = root / "attempts" / attempt_id / "report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return RetainedSourceAttempt(report_path, root)


def _complete_set(
    root: Path, prefix: str, *, no_change: bool = False
) -> tuple[RetainedSourceAttempt, ...]:
    return tuple(
        _attempt(
            root / family.lower(),
            family,
            f"{prefix}-{family.lower()}",
            predecessor=f"prior-{family.lower()}" if no_change else None,
            no_change=no_change,
        )
        for family in _SOURCES
    )


def test_source_authority_and_all_six_scenarios_derive_from_exact_reports(tmp_path: Path) -> None:
    """Exact reports and objects derive authority plus all six source exercises."""
    baseline = _complete_set(tmp_path / "baseline", "baseline")
    authority_raw = build_source_authority_evidence(baseline)
    authority = parse_source_authority_evidence(authority_raw)
    assert authority.source_families == ("GLD", "HKEL", "JUDICIARY")
    assert authority.authority_manifest_fingerprint == _AUTHORITY

    failed = _attempt(tmp_path / "retry-before", "GLD", "retry-before", result="SOURCE_OUTAGE")
    replay_root = tmp_path / "restart-after"
    restart_before = baseline[0]
    restart_after_path = replay_root / "attempts" / "restart-copy" / "report.json"
    restart_after_path.parent.mkdir(parents=True)
    restart_after_path.write_bytes(restart_before.report_path.read_bytes())
    source_object = next((restart_before.output_root / "objects").iterdir())
    destination = replay_root / "objects" / source_object.name
    destination.parent.mkdir(parents=True)
    destination.write_bytes(source_object.read_bytes())
    exercise_raw = build_source_exercise_evidence(
        SourceExerciseInputs(
            completeness=baseline,
            contract_drift=_attempt(
                tmp_path / "drift", "HKEL", "drift-hkel", result="SOURCE_CONTRACT_CHANGED"
            ),
            incomplete=_attempt(
                tmp_path / "incomplete", "JUDICIARY", "incomplete-jud", result="SOURCE_OUTAGE"
            ),
            no_change=_complete_set(tmp_path / "no-change", "nochange", no_change=True),
            restart_before=restart_before,
            restart_after=RetainedSourceAttempt(restart_after_path, replay_root),
            retry_before=failed,
            retry_after=_attempt(
                tmp_path / "retry-after",
                "GLD",
                "retry-after",
                predecessor="retry-before",
            ),
        )
    )
    exercise = parse_source_exercise_evidence(exercise_raw)
    assert exercise.scenario_names == (
        "SOURCE_COMPLETENESS",
        "SOURCE_CONTRACT_DRIFT",
        "SOURCE_INCOMPLETE",
        "SOURCE_NO_CHANGE",
        "SOURCE_RESTART",
        "SOURCE_RETRY",
    )


def test_source_aggregate_rejects_embedded_object_tamper(tmp_path: Path) -> None:
    """An embedded object mutation cannot survive digest and report revalidation."""
    raw = build_source_authority_evidence(_complete_set(tmp_path, "baseline"))
    document = cast("dict[str, object]", json.loads(raw))
    groups = cast("dict[str, object]", document["groups"])
    authority = cast("list[object]", groups["authority"])
    first = cast("dict[str, object]", authority[0])
    objects = cast("list[object]", first["objects"])
    cast("dict[str, object]", objects[0])["body_hex"] = "00"
    forged = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(SourceAdmissionEvidenceError):
        parse_source_authority_evidence(forged)
