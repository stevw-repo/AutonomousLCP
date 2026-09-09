# ruff: noqa: D100, D103

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    CapturedVerifiedPayload,
    CycleSafetyProfilePayload,
    DiscoveredPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    StartedPayload,
    TransportStartedPayload,
    WorkItemIdentity,
    read_retained_acquisition_journal,
)
from asklegal_acquisition_worker.hk_cases_acquisition import (
    YearShardDisposition,
    build_cases_acquisition_manifest,
)
from asklegal_acquisition_worker.hk_legislation_acquisition import (
    LEGISLATION_SCOPE_IDS,
    LegislationAcquisitionManifest,
    LegislationScopeDisposition,
)
from asklegal_acquisition_worker.main import main
from asklegal_acquisition_worker.resumable_acquisition import semantic_journal_head
from asklegal_acquisition_worker.v1_progress import (
    HKV1ProgressError,
    canonical_hk_v1_progress,
    load_hk_v1_progress,
)
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_observability import HKV1ProgressStatus

NOW = datetime(2026, 9, 8, 23, 59, tzinfo=UTC)
CASES_CYCLE = "cyc_20260908_cases"
LEGISLATION_CYCLE = "cyc_20260908_legislation"


def _empty_two_family_state(root: Path) -> None:
    with LocalAcquisitionJournal(root, CASES_CYCLE):
        pass
    with LocalAcquisitionJournal(root, LEGISLATION_CYCLE):
        pass


def _captured_family(root: Path, cycle_id: str, family: str) -> str:
    item = WorkItemIdentity.issue(
        source_family=family,
        source_role=f"HK_{family}_TEST",
        cycle_id=cycle_id,
        observation_cutoff="2026-09-08T00:00:00+00:00",
        procedure_version="1.0.0",
        locator=(
            "https://legalref.judiciary.hk/test"
            if family == "CASES"
            else "https://www.elegislation.gov.hk/test"
        ),
        stage="TEST_CAPTURE",
        parent_id="test-parent",
        media_type="text/html",
        max_bytes=100,
    )
    with LocalAcquisitionJournal(root, cycle_id) as journal:
        journal.append(item, JournalTransition.DISCOVERED, DiscoveredPayload(0))
        journal.append(
            item,
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            CycleSafetyProfilePayload(
                "asklegal.acquisition-cycle-safety-profile",
                "1.0.0",
                10,
                1_000,
                60,
                10,
                1,
                0,
                1,
                1,
                0,
            ),
        )
        journal.append(item, JournalTransition.STARTED, StartedPayload(1, 0, 0, 1))
        journal.append(item, JournalTransition.TRANSPORT_STARTED, TransportStartedPayload(1, 0, 0))
        journal.append(
            item,
            JournalTransition.CAPTURED_VERIFIED,
            CapturedVerifiedPayload(
                attempt=1,
                status=200,
                media_type="text/html",
                final_url=item.locator,
                redirect_chain=(),
                body_length=4,
                content_fingerprint="sha256:" + "a" * 64,
                object_ref=f"opaque/{'a' * 64}",
                read_back_verified=True,
            ),
        )
    timestamp = NOW.timestamp()
    entries = root / "acquisition-journals" / cycle_id / "entries"
    for path in entries.iterdir():
        os.utime(path, (timestamp, timestamp))
    return semantic_journal_head(read_retained_acquisition_journal(root, cycle_id).entries)


def _write_complete_results(
    root: Path, cases_head: str, legislation_head: str
) -> tuple[Path, Path]:
    cases = build_cases_acquisition_manifest(
        cycle_id=CASES_CYCLE,
        observation_cutoff="2026-09-08T00:00:00Z",
        year_dispositions=tuple(
            YearShardDisposition(
                year,
                "1997-07-01" if year == 1997 else f"{year:04d}-01-01",
                1,
                1,
                0,
                0,
                0,
                AcquisitionCycleResult.COMPLETE,
            )
            for year in range(1997, 2027)
        ),
        judgment_bundle_refs=(),
        discrepancy_refs=(),
        journal_head_fingerprint=cases_head,
    )
    fingerprint = "sha256:" + "b" * 64
    scopes = tuple(
        LegislationScopeDisposition(scope_id, 1, 1, 0, 0, AcquisitionCycleResult.COMPLETE)
        for scope_id in LEGISLATION_SCOPE_IDS
    )
    body = {
        "schema_id": "asklegal.legislation-acquisition-manifest",
        "schema_version": "1.0.0",
        "cycle_id": LEGISLATION_CYCLE,
        "observation_cutoff": "2026-09-08T00:00:00+00:00",
        "scope_dispositions": [item.to_json() for item in scopes],
        "verified_item_refs": [],
        "review_issue_refs": [],
        "journal_head_fingerprint": legislation_head,
        "source_register_fingerprint": fingerprint,
        "source_baseline_fingerprint": fingerprint,
        "work_plan_fingerprint": fingerprint,
        "result": "COMPLETE",
    }
    legislation = LegislationAcquisitionManifest(
        LEGISLATION_CYCLE,
        "2026-09-08T00:00:00+00:00",
        scopes,
        (),
        (),
        legislation_head,
        fingerprint,
        fingerprint,
        fingerprint,
        AcquisitionCycleResult.COMPLETE,
        "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest(),
    )
    cases_path = (root.parent / "cases-result.json").resolve()
    legislation_path = (root.parent / "legislation-result.json").resolve()
    cases_path.write_bytes(canonicalize(cases.to_json()))
    legislation_path.write_bytes(canonicalize(legislation.to_json()))
    return cases_path, legislation_path


def test_empty_retained_journals_are_truthfully_not_started(tmp_path: Path) -> None:
    root = (tmp_path / "state").resolve()
    _empty_two_family_state(root)

    snapshot = load_hk_v1_progress(
        state_root=root,
        cases_cycle_id=CASES_CYCLE,
        legislation_cycle_id=LEGISLATION_CYCLE,
        cases_result_path=None,
        legislation_result_path=None,
        as_of=NOW,
    )

    assert snapshot.status is HKV1ProgressStatus.NOT_STARTED
    document = json.loads(canonical_hk_v1_progress(snapshot))
    assert tuple(item["material_family"] for item in document["families"]) == (
        "CASES",
        "LEGISLATION",
    )
    assert str(root) not in repr(document)


def test_missing_or_corrupt_retained_journal_fails_closed(tmp_path: Path) -> None:
    root = (tmp_path / "state").resolve()
    _empty_two_family_state(root)
    corrupt = root / "acquisition-journals" / CASES_CYCLE / "entries" / "bad.json"
    corrupt.write_bytes(b"{}")

    with pytest.raises(HKV1ProgressError, match="HK_V1_PROGRESS_UNAVAILABLE"):
        load_hk_v1_progress(
            state_root=root,
            cases_cycle_id=CASES_CYCLE,
            legislation_cycle_id=LEGISLATION_CYCLE,
            cases_result_path=None,
            legislation_result_path=None,
            as_of=NOW,
        )


def test_complete_requires_both_exact_replay_bound_family_results(tmp_path: Path) -> None:
    root = (tmp_path / "state").resolve()
    cases_head = _captured_family(root, CASES_CYCLE, "CASES")
    legislation_head = _captured_family(root, LEGISLATION_CYCLE, "LEGISLATION")
    cases_result, legislation_result = _write_complete_results(root, cases_head, legislation_head)

    without_results = load_hk_v1_progress(
        state_root=root,
        cases_cycle_id=CASES_CYCLE,
        legislation_cycle_id=LEGISLATION_CYCLE,
        cases_result_path=None,
        legislation_result_path=None,
        as_of=NOW,
    )
    complete = load_hk_v1_progress(
        state_root=root,
        cases_cycle_id=CASES_CYCLE,
        legislation_cycle_id=LEGISLATION_CYCLE,
        cases_result_path=cases_result,
        legislation_result_path=legislation_result,
        as_of=NOW,
    )

    assert without_results.status is HKV1ProgressStatus.INCOMPLETE_RETRYABLE
    assert complete.status is HKV1ProgressStatus.COMPLETE


def test_cli_emits_only_canonical_progress_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = (tmp_path / "state").resolve()
    _empty_two_family_state(root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "asklegal-acquisition-worker",
            "--show-hk-v1-progress",
            "--state-root",
            str(root),
            "--cases-cycle-id",
            CASES_CYCLE,
            "--legislation-cycle-id",
            LEGISLATION_CYCLE,
            "--as-of",
            "2026-09-08T23:59:00Z",
        ],
    )

    main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["status"] == "NOT_STARTED"
    assert captured.out.encode() == canonical_hk_v1_progress(
        load_hk_v1_progress(
            state_root=root,
            cases_cycle_id=CASES_CYCLE,
            legislation_cycle_id=LEGISLATION_CYCLE,
            cases_result_path=None,
            legislation_result_path=None,
            as_of=NOW,
        )
    )


def test_cli_fails_nonzero_without_echoing_corrupt_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = (tmp_path / "state").resolve()
    _empty_two_family_state(root)
    corrupt = root / "acquisition-journals" / CASES_CYCLE / "entries" / "unexpected"
    corrupt.write_bytes(b"operator-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "asklegal-acquisition-worker",
            "--show-hk-v1-progress",
            "--state-root",
            str(root),
            "--cases-cycle-id",
            CASES_CYCLE,
            "--legislation-cycle-id",
            LEGISLATION_CYCLE,
        ],
    )

    with pytest.raises(SystemExit) as failure:
        main()

    captured = capsys.readouterr()
    assert failure.value.code == 2
    assert captured.out == ""
    assert captured.err == "HK_V1_PROGRESS_UNAVAILABLE\n"
