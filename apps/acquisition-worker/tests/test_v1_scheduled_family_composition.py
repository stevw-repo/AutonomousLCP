"""Focused scheduled-to-family acquisition composition proofs."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Never, cast

import pytest
from asklegal_acquisition_worker import hk_v1_due_cycle as due_cycle
from asklegal_acquisition_worker import v1_service
from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    CycleSafetyProfilePayload,
    DiscoveredPayload,
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    WorkItemIdentity,
)
from asklegal_acquisition_worker.hk_cases_acquisition import (
    YearShardDisposition,
    build_cases_acquisition_manifest,
)
from asklegal_acquisition_worker.hk_legislation_acquisition import LegislationVerifiedItem
from asklegal_acquisition_worker.hk_v1_due_cycle import acquire_hk_v1_due_cycle
from asklegal_acquisition_worker.hk_v1_due_predecessor import LocalDueCyclePredecessorStore
from asklegal_acquisition_worker.source_role_evidence import SourceRoleDisposition
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_durable_task import ActivityContext, OrchestrationContext
from asklegal_evidence_vault import LocalImmutableVault, VaultName
from asklegal_reporting import (
    DueCycleKind,
    HongKongV1DueCycleError,
    HongKongV1DueCycleInstruction,
    load_hk_v1_coverage_matrix,
    parse_hk_v1_due_terminal,
)


class _RecordingContext:
    """Capture exact activity and child-orchestration calls."""

    def __init__(self) -> None:
        self.activities: list[tuple[str, object]] = []
        self.children: list[tuple[str, object, str | None, str | None]] = []

    def call_activity(self, name: str, *, input: object) -> object:  # noqa: A002
        self.activities.append((name, input))
        return object()

    def call_sub_orchestrator(
        self,
        name: str,
        *,
        input: object,  # noqa: A002 - mirror the Durable SDK keyword.
        instance_id: str | None = None,
        version: str | None = None,
    ) -> object:
        self.children.append((name, input, instance_id, version))
        return object()


def _instruction() -> dict[str, str]:
    matrix = load_hk_v1_coverage_matrix()
    return {
        "cycle_id": "hk-v1-daily-current-law-20260908t0215000800",
        "cycle_kind": DueCycleKind.DAILY_CURRENT_LAW.value,
        "scheduled_at": "2026-09-07T18:15:00Z",
        "observation_cutoff": "2026-09-07T18:15:00Z",
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
    }


def _cases_result(cycle_id: str, cutoff: str) -> bytes:
    manifest = build_cases_acquisition_manifest(
        cycle_id=cycle_id,
        observation_cutoff=cutoff,
        year_dispositions=(
            YearShardDisposition(
                1997,
                "1997-07-01",
                0,
                0,
                0,
                0,
                1,
                AcquisitionCycleResult.INCOMPLETE_RETRYABLE,
            ),
        ),
        judgment_bundle_refs=(),
        discrepancy_refs=(),
        journal_head_fingerprint="sha256:" + "a" * 64,
        runner_result=AcquisitionCycleResult.INCOMPLETE_RETRYABLE,
    )
    return canonicalize(manifest.to_json())


def _legislation_result(cycle_id: str, cutoff: str) -> bytes:
    body: dict[str, object] = {
        "schema_id": "asklegal.legislation-acquisition-manifest",
        "schema_version": "1.0.0",
        "cycle_id": cycle_id,
        "observation_cutoff": cutoff,
        "scope_dispositions": [
            {
                "scope_id": scope_id,
                "required_item_count": 1,
                "verified_item_count": 0,
                "retryable_item_count": 1,
                "rejected_item_count": 0,
                "result": "INCOMPLETE_RETRYABLE",
            }
            for scope_id in (
                "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                "HK-LEG-ORDINANCES",
                "HK-LEG-SUBSIDIARY",
            )
        ],
        "verified_item_refs": [],
        "review_issue_refs": [],
        "journal_head_fingerprint": "sha256:" + "b" * 64,
        "source_register_fingerprint": "sha256:" + "c" * 64,
        "source_baseline_fingerprint": "sha256:" + "d" * 64,
        "work_plan_fingerprint": "sha256:" + "e" * 64,
        "result": "INCOMPLETE_RETRYABLE",
    }
    checked_body = checked_json_value(body)
    if type(checked_body) is not dict:
        raise TypeError
    body["fingerprint"] = "sha256:" + sha256(canonicalize(checked_body)).hexdigest()
    return canonicalize(checked_json_value(body))


def _complete_cases_result(cycle_id: str, cutoff: str, journal_head: str) -> bytes:
    manifest = build_cases_acquisition_manifest(
        cycle_id=cycle_id,
        observation_cutoff=cutoff,
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
            for year in range(1997, int(cutoff[:4]) + 1)
        ),
        judgment_bundle_refs=(),
        discrepancy_refs=(),
        journal_head_fingerprint=journal_head,
        source_dispositions=tuple(
            SourceRoleDisposition(source_id, 1, 1, 0, 0, AcquisitionCycleResult.COMPLETE)
            for source_id in (
                "HK-CASE-HKLII-DISCOVERY",
                "HK-CASE-JUDICIARY-LRS-INVENTORY",
            )
        ),
    )
    return canonicalize(manifest.to_json())


def _complete_legislation_result(
    cycle_id: str,
    cutoff: str,
    journal_head: str,
    verified_refs: tuple[str, ...],
    *,
    omit_source_id: str | None = None,
) -> bytes:
    body: dict[str, object] = {
        "schema_id": "asklegal.legislation-acquisition-manifest",
        "schema_version": "1.0.0",
        "cycle_id": cycle_id,
        "observation_cutoff": cutoff,
        "scope_dispositions": [
            {
                "scope_id": scope_id,
                "required_item_count": 1,
                "verified_item_count": 1,
                "retryable_item_count": 0,
                "rejected_item_count": 0,
                "result": "COMPLETE",
            }
            for scope_id in (
                "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                "HK-LEG-ORDINANCES",
                "HK-LEG-SUBSIDIARY",
            )
        ],
        "verified_item_refs": list(verified_refs[:3]),
        "review_issue_refs": [],
        "journal_head_fingerprint": journal_head,
        "source_register_fingerprint": "sha256:" + "3" * 64,
        "source_baseline_fingerprint": "sha256:" + "4" * 64,
        "work_plan_fingerprint": "sha256:" + "5" * 64,
        "result": "COMPLETE",
        "source_dispositions": [
            {
                "source_id": source_id,
                "required_item_count": 1,
                "verified_item_count": 1,
                "retryable_item_count": 0,
                "rejected_item_count": 0,
                "result": "COMPLETE",
            }
            for source_id in (
                "HK-LEG-BASIC-LAW-PORTAL",
                "HK-LEG-GLD-EGAZETTE",
                "HK-LEG-HKEL-CURRENT-DATA",
                "HK-LEG-HKEL-CURRENT-INVENTORY",
                "HK-LEG-HKEL-EDITORIAL-RECORDS",
                "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
            )
            if source_id != omit_source_id
        ],
    }
    checked_body = checked_json_value(body)
    if type(checked_body) is not dict:
        raise TypeError
    body["fingerprint"] = "sha256:" + sha256(canonicalize(checked_body)).hexdigest()
    return canonicalize(checked_json_value(body))


def _complete_journal(  # noqa: PLR0913
    activities: due_cycle.HongKongV1DueCycleActivities,
    cycle_id: str,
    cutoff: str,
    family: str,
    roles: tuple[str, ...],
    *,
    retain_objects: bool = True,
) -> tuple[str, tuple[str, ...]]:
    state_root = activities._acquisition_state_root  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    vault = activities._vault  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    assert state_root is not None
    verified_refs: list[str] = []
    with LocalAcquisitionJournal(state_root, cycle_id) as journal:
        pending: list[tuple[WorkItemIdentity, bytes, str, str]] = []
        for index, role in enumerate(roles, start=1):
            body = f"{family}:{role}".encode()
            fingerprint = f"sha256:{sha256(body).hexdigest()}"
            object_ref = f"objects/{fingerprint.removeprefix('sha256:')}.bin"
            if retain_objects:
                receipt = vault.conditional_create(object_ref, body, due_cycle._RETENTION)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                assert receipt.read_back_verified is True
            stable_key = f"item-{index}"
            item = WorkItemIdentity.issue(
                source_family=family,
                source_role=role.replace("-", "_") if family == "LEGISLATION" else role,
                cycle_id=cycle_id,
                observation_cutoff=cutoff,
                procedure_version="1.0.0",
                locator=f"https://example.invalid/{family.lower()}/{index}",
                stage="TEST_CAPTURE",
                parent_id=stable_key,
                media_type="text/plain",
                max_bytes=1_024,
            )
            journal.append(item, JournalTransition.DISCOVERED, DiscoveredPayload(1))
            pending.append((item, body, fingerprint, object_ref))
            if family == "LEGISLATION":
                verified_refs.append(
                    LegislationVerifiedItem.issue(stable_key, object_ref, fingerprint).reference
                )
        journal.append(
            pending[0][0],
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            CycleSafetyProfilePayload(
                "asklegal.acquisition-cycle-safety-profile",
                "1.0.0",
                100,
                100_000,
                3_600,
                100,
                4,
                0,
                2,
                20,
                1,
            ),
        )
        for item, body, fingerprint, object_ref in pending:
            journal.append(
                item,
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
                ImportedCaptureVerifiedPayload(
                    "test-source-attempt",
                    "sha256:" + "1" * 64,
                    "sha256:" + "2" * 64,
                    "sha256:" + "3" * 64,
                    200,
                    "text/plain",
                    item.locator,
                    len(body),
                    fingerprint,
                    object_ref,
                    read_back_verified=True,
                ),
            )
        entries = journal.replay()
    return entries[-1].fingerprint, tuple(verified_refs)


def _retain_complete_family_evidence(
    activities: due_cycle.HongKongV1DueCycleActivities,
    instruction_body: dict[str, str],
    *,
    omit_legislation_source_id: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    instruction = HongKongV1DueCycleInstruction.from_json(instruction_body)
    plan = cast(
        "dict[str, object]",
        activities.plan_hk_v1_due_cycle(ActivityContext("family-plan", 1), instruction_body),
    )
    children = due_cycle.scheduled_hk_v1_family_children(instruction)
    case_roles = (
        "HK-CASE-HKLII-DISCOVERY",
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
    )
    legislation_roles = tuple(
        source_id
        for source_id in (
            "HK-LEG-BASIC-LAW-PORTAL",
            "HK-LEG-GLD-EGAZETTE",
            "HK-LEG-HKEL-CURRENT-DATA",
            "HK-LEG-HKEL-CURRENT-INVENTORY",
            "HK-LEG-HKEL-EDITORIAL-RECORDS",
            "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        )
        if source_id != omit_legislation_source_id
    )
    cases_head, _ = _complete_journal(
        activities,
        children[0]["cycle_id"],
        instruction.observation_cutoff,
        "CASES",
        case_roles,
    )
    legislation_head, legislation_refs = _complete_journal(
        activities,
        children[1]["cycle_id"],
        cast("str", children[1]["instruction"]["observation_cutoff"]),
        "LEGISLATION",
        legislation_roles,
    )
    contents = (
        _complete_cases_result(children[0]["cycle_id"], instruction.observation_cutoff, cases_head),
        _complete_legislation_result(
            children[1]["cycle_id"],
            cast("str", children[1]["instruction"]["observation_cutoff"]),
            legislation_head,
            legislation_refs,
            omit_source_id=omit_legislation_source_id,
        ),
    )
    summaries = [
        {
            **due_cycle._scheduled_family_result(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                content, child, instruction
            ),
            "manifest_content": content.decode("utf-8"),
        }
        for child, content in zip(children, contents, strict=True)
    ]
    receipt = activities.record_hk_v1_family_acquisitions(
        ActivityContext("family-record", 2),
        {
            "instruction": instruction_body,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "children": summaries,
        },
    )
    return plan, receipt


def _complete_family_payload(
    activities: due_cycle.HongKongV1DueCycleActivities,
    instruction_body: dict[str, str],
    cases_head: str,
    legislation_head: str,
    legislation_refs: tuple[str, ...],
) -> dict[str, object]:
    """Build one root record request around caller-controlled complete journal facts."""
    instruction = HongKongV1DueCycleInstruction.from_json(instruction_body)
    plan = cast(
        "dict[str, object]",
        activities.plan_hk_v1_due_cycle(ActivityContext("adversarial-plan", 1), instruction_body),
    )
    children = due_cycle.scheduled_hk_v1_family_children(instruction)
    contents = (
        _complete_cases_result(children[0]["cycle_id"], instruction.observation_cutoff, cases_head),
        _complete_legislation_result(
            children[1]["cycle_id"],
            cast("str", children[1]["instruction"]["observation_cutoff"]),
            legislation_head,
            legislation_refs,
        ),
    )
    summaries = [
        {
            **due_cycle._scheduled_family_result(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                content, child, instruction
            ),
            "manifest_content": content.decode("utf-8"),
        }
        for child, content in zip(children, contents, strict=True)
    ]
    return {
        "instruction": instruction_body,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "children": summaries,
    }


def test_schedule_dispatches_both_real_family_boundaries_with_replay_stable_identities() -> None:
    """A root replay must call both Task 5/6 boundaries with the same journals and IDs."""
    instruction = _instruction()
    plan = due_cycle._plan_body(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        due_cycle._plan(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            HongKongV1DueCycleInstruction.from_json(instruction)
        )
    )

    def drive(context: _RecordingContext) -> None:
        workflow = acquire_hk_v1_due_cycle(cast("OrchestrationContext", context), instruction)
        next(workflow)
        workflow.send(plan)
        cases_payload = cast("dict[str, object]", context.children[0][1])
        assert cases_payload["work_graph_ref"] == (
            f"hk-v1-schedule/{cases_payload['cycle_id']}/daily_current_law/cases/20260907T181500Z"
        )
        workflow.send(
            _cases_result(cast("str", cases_payload["cycle_id"]), instruction["observation_cutoff"])
        )
        legislation_payload = cast("dict[str, object]", context.children[1][1])
        workflow.send(
            _legislation_result(
                cast("str", legislation_payload["cycle_id"]),
                cast("str", legislation_payload["observation_cutoff"]),
            )
        )

    first = _RecordingContext()
    replay = _RecordingContext()
    drive(first)
    drive(replay)

    assert first.children == replay.children
    assert [item[0] for item in first.children] == [
        "acquire_resumable_source_cycle",
        "acquire_resumable_source_cycle",
    ]
    assert [cast("dict[str, object]", item[1])["source_family"] for item in first.children] == [
        "CASES",
        "LEGISLATION",
    ]
    assert all(item[2] == cast("dict[str, object]", item[1])["cycle_id"] for item in first.children)
    assert all(item[3] == "1.0.0" for item in first.children)
    family_record = first.activities[-1]
    assert family_record[0] == "record_hk_v1_family_acquisitions"
    children = cast("dict[str, object]", family_record[1])["children"]
    for child in cast("list[object]", children):
        child_document = cast("dict[str, object]", child)
        assert child_document["journal_ref"] == (
            "acquisition-journals/" + cast("str", child_document["cycle_id"])
        )
        assert isinstance(child_document["manifest_content"], str)


def test_family_results_are_strictly_validated_and_retained_with_readback(
    tmp_path: Path,
) -> None:
    """The root evidence is immutable and a malformed child result cannot reach it."""
    instruction_body = _instruction()
    instruction = HongKongV1DueCycleInstruction.from_json(instruction_body)
    cases, legislation = due_cycle.scheduled_hk_v1_family_children(instruction)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_FAMILY_RESULT_INVALID"):
        due_cycle._scheduled_family_result(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            b"{}", cases, instruction
        )
    cases_content = _cases_result(cases["cycle_id"], instruction.observation_cutoff)
    legislation_content = _legislation_result(
        legislation["cycle_id"],
        cast("str", legislation["instruction"]["observation_cutoff"]),
    )
    summaries = [
        {
            **due_cycle._scheduled_family_result(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                cases_content,
                cases,
                instruction,
            ),
            "manifest_content": cases_content.decode("utf-8"),
        },
        {
            **due_cycle._scheduled_family_result(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                legislation_content,
                legislation,
                instruction,
            ),
            "manifest_content": legislation_content.decode("utf-8"),
        },
    ]
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    store = LocalDueCyclePredecessorStore(tmp_path / "state")
    activities = due_cycle.HongKongV1DueCycleActivities(vault, store)
    plan = cast(
        "dict[str, object]",
        activities.plan_hk_v1_due_cycle(ActivityContext("family", 1), instruction_body),
    )
    payload = {
        "instruction": instruction_body,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "children": summaries,
    }

    try:
        first = activities.record_hk_v1_family_acquisitions(ActivityContext("family", 2), payload)
        replay = activities.record_hk_v1_family_acquisitions(ActivityContext("family", 3), payload)

        assert first["evidence_created"] is True
        assert replay["evidence_created"] is False
        assert first["evidence_reference"] == replay["evidence_reference"]
        cases_reference = vault.resolve_current(
            due_cycle._family_manifest_key(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                instruction.cycle_id, "CASES"
            )
        )
        legislation_reference = vault.resolve_current(
            due_cycle._family_manifest_key(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                instruction.cycle_id, "LEGISLATION"
            )
        )
        assert cases_reference is not None
        assert legislation_reference is not None
        assert vault.read_exact(cases_reference) == cases_content
        assert vault.read_exact(legislation_reference) == legislation_content
        family_reference = vault.resolve_current(
            due_cycle._family_evidence_key(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                instruction.cycle_id
            )
        )
        assert family_reference is not None
        family_evidence = parse_json_bytes(vault.read_exact(family_reference), max_bytes=4_194_304)
        assert type(family_evidence) is dict
        retained_children = family_evidence["children"]
        assert type(retained_children) is list
        retained_fingerprints: list[object] = []
        for item in retained_children:
            assert type(item) is dict
            manifest_reference = item["manifest_reference"]
            assert type(manifest_reference) is dict
            retained_fingerprints.append(manifest_reference["fingerprint"])
        assert retained_fingerprints == [
            cases_reference.fingerprint,
            legislation_reference.fingerprint,
        ]

        drifted_children = [dict(item) for item in summaries]
        drifted_children[0]["manifest_content"] = legislation_content.decode("utf-8")
        with pytest.raises(HongKongV1DueCycleError, match="DUE_FAMILY_EVIDENCE_INVALID"):
            activities.record_hk_v1_family_acquisitions(
                ActivityContext("family", 4),
                {**payload, "children": drifted_children},
            )
        assert vault.read_exact(cases_reference) == cases_content
    finally:
        store.close()


def test_complete_family_manifest_without_local_journal_is_rejected(tmp_path: Path) -> None:
    """A self-consistent COMPLETE manifest cannot substitute for its absent journal."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    activities = due_cycle.HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "state")
    )
    instruction = {**_instruction(), "cycle_id": "hk-v1-adversarial-no-journal"}
    refs = tuple(
        LegislationVerifiedItem.issue(
            f"item-{index}", f"objects/{index}.bin", "sha256:" + str(index) * 64
        ).reference
        for index in range(1, 4)
    )
    payload = _complete_family_payload(
        activities,
        instruction,
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
        refs,
    )

    with pytest.raises(HongKongV1DueCycleError, match="DUE_FAMILY_EVIDENCE_INVALID"):
        activities.record_hk_v1_family_acquisitions(ActivityContext("no-journal", 2), payload)


def test_complete_family_manifest_with_journal_head_drift_is_rejected(tmp_path: Path) -> None:
    """A manifest fingerprint cannot hide a head that differs from canonical replay."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    activities = due_cycle.HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "state")
    )
    instruction_body = {**_instruction(), "cycle_id": "hk-v1-adversarial-head-drift"}
    instruction = HongKongV1DueCycleInstruction.from_json(instruction_body)
    children = due_cycle.scheduled_hk_v1_family_children(instruction)
    case_roles = ("HK-CASE-HKLII-DISCOVERY", "HK-CASE-JUDICIARY-LRS-INVENTORY")
    legislation_roles = (
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
    )
    _complete_journal(
        activities,
        children[0]["cycle_id"],
        instruction.observation_cutoff,
        "CASES",
        case_roles,
    )
    legislation_head, legislation_refs = _complete_journal(
        activities,
        children[1]["cycle_id"],
        cast("str", children[1]["instruction"]["observation_cutoff"]),
        "LEGISLATION",
        legislation_roles,
    )
    payload = _complete_family_payload(
        activities,
        instruction_body,
        "sha256:" + "f" * 64,
        legislation_head,
        legislation_refs,
    )

    with pytest.raises(HongKongV1DueCycleError, match="DUE_FAMILY_EVIDENCE_INVALID"):
        activities.record_hk_v1_family_acquisitions(ActivityContext("head-drift", 2), payload)


def test_complete_family_manifest_with_missing_terminal_object_is_rejected(
    tmp_path: Path,
) -> None:
    """Every terminal journal object is reread before root evidence can be retained."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    activities = due_cycle.HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "state")
    )
    instruction_body = {**_instruction(), "cycle_id": "hk-v1-adversarial-object-missing"}
    instruction = HongKongV1DueCycleInstruction.from_json(instruction_body)
    children = due_cycle.scheduled_hk_v1_family_children(instruction)
    cases_head, _ = _complete_journal(
        activities,
        children[0]["cycle_id"],
        instruction.observation_cutoff,
        "CASES",
        ("HK-CASE-HKLII-DISCOVERY", "HK-CASE-JUDICIARY-LRS-INVENTORY"),
        retain_objects=False,
    )
    legislation_head, legislation_refs = _complete_journal(
        activities,
        children[1]["cycle_id"],
        cast("str", children[1]["instruction"]["observation_cutoff"]),
        "LEGISLATION",
        (
            "HK-LEG-BASIC-LAW-PORTAL",
            "HK-LEG-GLD-EGAZETTE",
            "HK-LEG-HKEL-CURRENT-DATA",
            "HK-LEG-HKEL-CURRENT-INVENTORY",
            "HK-LEG-HKEL-EDITORIAL-RECORDS",
            "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        ),
    )
    payload = _complete_family_payload(
        activities,
        instruction_body,
        cases_head,
        legislation_head,
        legislation_refs,
    )

    with pytest.raises(HongKongV1DueCycleError, match="DUE_FAMILY_EVIDENCE_INVALID"):
        activities.record_hk_v1_family_acquisitions(ActivityContext("missing-object", 2), payload)


def test_current_family_evidence_owns_all_roles_and_binds_every_scheduled_terminal(
    tmp_path: Path,
) -> None:
    """Current child manifests, including GLD, replace frozen baseline reports."""
    exact_family_roles = {
        "HK-CASE-HKLII-DISCOVERY",
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
    }
    family_roles = due_cycle._CURRENT_FAMILY_SOURCE_IDS  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    owned_roles = {source_id for roles in family_roles.values() for source_id in roles}
    assert owned_roles == exact_family_roles

    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    activities = due_cycle.HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "state")
    )
    instruction = {
        **_instruction(),
        "cycle_kind": DueCycleKind.FULL_PERIODIC.value,
        "cycle_id": "hk-v1-full-current-family-20260908",
    }
    plan, family_receipt = _retain_complete_family_evidence(activities, instruction)
    scheduled_roles = cast("list[str]", plan["source_ids"])
    assert set(scheduled_roles) == exact_family_roles - {"HK-LEG-HKEL-CURRENT-DATA"}

    terminal_references: list[dict[str, object]] = []
    for source_id in scheduled_roles:
        captured = activities.capture_hk_v1_due_source(
            ActivityContext("family-capture", 3),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": source_id,
                "family_evidence_reference": family_receipt["evidence_reference"],
            },
        )
        assert captured["evidence_created"] is True
        terminal_references.append(
            {"source_id": source_id, "reference": captured["terminal_reference"]}
        )
        payload_ref = vault.resolve_current(
            due_cycle.hk_v1_due_source_payload_key(instruction["cycle_id"], source_id)
        )
        assert payload_ref is not None
        payload = parse_json_bytes(vault.read_exact(payload_ref), max_bytes=65_536)
        assert type(payload) is dict
        assert payload["outcome"] == "COMPLETE"
        terminal_ref = vault.resolve_current(
            due_cycle.hk_v1_due_source_terminal_key(instruction["cycle_id"], source_id)
        )
        assert terminal_ref is not None
        terminal = parse_hk_v1_due_terminal(vault.read_exact(terminal_ref))
        assert terminal.evidence_kind == "CURRENT_FAMILY_ROLE_PROOF"
        assert terminal.requirement.technical_state == "NOT_ADMITTED"
        assert terminal.requirement.rights_state == "NOT_ADMITTED"
        evidence_ref = vault.resolve_current(
            due_cycle._source_evidence_key(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                instruction["cycle_id"], source_id
            )
        )
        assert evidence_ref is not None
        evidence = parse_json_bytes(vault.read_exact(evidence_ref), max_bytes=65_536)
        assert type(evidence) is dict
        assert evidence["source_id"] == source_id
        assert evidence["observation_cutoff"] == instruction["observation_cutoff"]
        source_disposition = evidence["source_disposition"]
        assert type(source_disposition) is dict
        assert source_disposition["source_id"] == source_id
        assert evidence["family_evidence_reference"] == family_receipt["evidence_reference"]

    assembled = activities.assemble_hk_v1_due_cycle(
        ActivityContext("family-assemble", 4),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": terminal_references,
        },
    )
    assert assembled["disposition"] == "COMPLETE"
    assert assembled["release_blocking"] is False


@dataclass
class _FrozenBaselineMustNotRun:
    calls: int = 0

    def capture(self, *, source_id: str, observation_cutoff: str) -> Never:
        del source_id, observation_cutoff
        self.calls += 1
        message = "current-cycle evidence must precede frozen report lookup"
        raise AssertionError(message)

    def verify_retained_object(
        self, object_ref: str, content_fingerprint: str, byte_length: int
    ) -> Never:
        del object_ref, content_fingerprint, byte_length
        self.calls += 1
        message = "current-cycle primary evidence must precede frozen report lookup"
        raise AssertionError(message)


def test_second_cutoff_uses_its_own_family_manifests_without_frozen_report_fallback(
    tmp_path: Path,
) -> None:
    """An update cutoff cannot reuse or mismatch the earlier Task 7 observation."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    frozen = _FrozenBaselineMustNotRun()
    activities = due_cycle.HongKongV1DueCycleActivities(
        vault,
        LocalDueCyclePredecessorStore(tmp_path / "state"),
        source_adapter=frozen,
    )
    first_instruction = {
        **_instruction(),
        "cycle_id": "hk-v1-daily-current-family-first",
    }
    second_instruction = {
        **_instruction(),
        "cycle_id": "hk-v1-daily-current-family-second",
        "scheduled_at": "2026-09-08T18:15:00Z",
        "observation_cutoff": "2026-09-08T18:15:00Z",
    }
    first_plan, first_family = _retain_complete_family_evidence(activities, first_instruction)
    second_plan, second_family = _retain_complete_family_evidence(activities, second_instruction)
    source_id = "HK-LEG-GLD-EGAZETTE"
    for instruction, plan, family in (
        (first_instruction, first_plan, first_family),
        (second_instruction, second_plan, second_family),
    ):
        activities.capture_hk_v1_due_source(
            ActivityContext("family-update", 4),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": source_id,
                "family_evidence_reference": family["evidence_reference"],
            },
        )
    assert frozen.calls == 0
    second_evidence_ref = vault.resolve_current(
        due_cycle._source_evidence_key(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            second_instruction["cycle_id"], source_id
        )
    )
    assert second_evidence_ref is not None
    second_evidence = parse_json_bytes(vault.read_exact(second_evidence_ref), max_bytes=65_536)
    assert type(second_evidence) is dict
    assert second_evidence["observation_cutoff"] == second_instruction["observation_cutoff"]
    assert second_evidence["family_evidence_reference"] == second_family["evidence_reference"]
    assert second_evidence["family_evidence_reference"] != first_family["evidence_reference"]
    assert second_evidence["family_result"] == "COMPLETE"


def test_family_complete_cannot_synthesize_a_missing_source_role(tmp_path: Path) -> None:
    """A family summary never substitutes for the GLD role's own accounting."""
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    activities = due_cycle.HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "state")
    )
    instruction = {
        **_instruction(),
        "cycle_id": "hk-v1-missing-gld-role-proof",
    }
    plan, family = _retain_complete_family_evidence(
        activities,
        instruction,
        omit_legislation_source_id="HK-LEG-GLD-EGAZETTE",
    )
    activities.capture_hk_v1_due_source(
        ActivityContext("family-missing-role", 3),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
            "family_evidence_reference": family["evidence_reference"],
        },
    )
    payload_ref = vault.resolve_current(
        due_cycle.hk_v1_due_source_payload_key(instruction["cycle_id"], "HK-LEG-GLD-EGAZETTE")
    )
    assert payload_ref is not None
    payload = parse_json_bytes(vault.read_exact(payload_ref), max_bytes=65_536)
    assert type(payload) is dict
    assert payload["outcome"] == "INCOMPLETE_OBSERVATION"
    assert payload["failure_codes"] == ["FAMILY_SOURCE_ROLE_EVIDENCE_MISSING"]


@dataclass
class _UnreadyActivities:
    production_cases_configured: bool = False
    production_legislation_configured: bool = True


class _NeverScheduler:
    task_hub = "acquisition"
    create_calls = 0

    def create_worker(self, *, concurrency_options: object) -> Never:
        del concurrency_options
        self.create_calls += 1
        message = "worker creation must follow complete family composition"
        raise AssertionError(message)


@dataclass
class _Infrastructure:
    due_cycle_state_root: Path
    scheduler: _NeverScheduler


def test_missing_cases_production_port_is_not_ready_before_worker_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The service cannot start a worker whose scheduled Cases child will always fail."""
    scheduler = _NeverScheduler()
    state_root = tmp_path / "state"
    infrastructure = _Infrastructure(state_root, scheduler)

    def reject_store(_root: Path) -> Never:
        message = "predecessor state must not open before family input readiness"
        raise AssertionError(message)

    def load_infrastructure(_environment: Mapping[str, str]) -> _Infrastructure:
        return infrastructure

    def unready_activities(*_args: object) -> _UnreadyActivities:
        return _UnreadyActivities()

    monkeypatch.setattr(v1_service, "load_v1_infrastructure", load_infrastructure)
    monkeypatch.setattr(v1_service, "build_activities", unready_activities)
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", reject_store)

    assert asyncio.run(v1_service._run({})) is v1_service.ServiceExitCode.NOT_READY  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    assert scheduler.create_calls == 0
    assert not state_root.exists()
