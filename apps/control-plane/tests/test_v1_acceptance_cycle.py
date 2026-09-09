"""Focused Task 10 Control acceptance-cycle coordinator proofs."""

from __future__ import annotations

from collections.abc import Generator
from hashlib import sha256
from json import dumps
from pathlib import Path
from types import SimpleNamespace
from typing import TypeIs, cast

import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_control_plane import v1_acceptance
from asklegal_control_plane.v1_acceptance import (
    ACCEPTANCE_ACQUISITION_ACTIVITY,
    ACCEPTANCE_LEGAL_ACTIVITY,
    AcceptanceConfiguration,
    AcceptanceCoordinatorError,
    LocalAcceptanceActivities,
    run_hk_v1_acceptance_cycle,
)
from asklegal_durable_task import ActivityContext, OrchestrationContext, OrchestrationStatus, Task
from asklegal_evidence_vault import ExactObjectReference
from asklegal_reporting import (
    hk_v1_due_cycle_manifest_key,
    hk_v1_due_family_acquisition_key,
    load_hk_v1_coverage_matrix,
)

from tools.hk_v1_live_cycle import AcceptanceCycleKind, preflight_acceptance_cycle

_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)


def _manual_family_evidence(
    cases_fingerprint: str, legislation_fingerprint: str
) -> dict[str, JsonValue]:
    children: list[JsonValue] = []
    for family, fingerprint, marker in (
        ("CASES", cases_fingerprint, "c"),
        ("LEGISLATION", legislation_fingerprint, "d"),
    ):
        cycle_id = f"cyc_{marker * 48}"
        children.append(
            {
                "source_family": family,
                "cycle_id": cycle_id,
                "journal_ref": f"acquisition-journals/{cycle_id}",
                "manifest_fingerprint": fingerprint,
                "journal_head_fingerprint": "sha256:" + marker * 64,
                "result": "COMPLETE",
                "manifest_reference": {
                    "vault": "PRIMARY",
                    "logical_key": f"retained/{family.casefold()}.json",
                    "version_id": "v" + marker * 64,
                    "fingerprint": "sha256:" + marker * 64,
                    "byte_length": 1,
                },
            }
        )
    return {
        "schema_id": "asklegal.hk-v1.acceptance-family-acquisition-evidence",
        "schema_version": "1.0.0",
        "root_cycle_id": "manual-cycle",
        "root_plan_fingerprint": "sha256:" + "e" * 64,
        "evidence_reference": {
            "vault": "PRIMARY",
            "logical_key": "retained/family-evidence.json",
            "version_id": "v" + "e" * 64,
            "fingerprint": "sha256:" + "e" * 64,
            "byte_length": 1,
        },
        "children": children,
    }


def _selection(
    *,
    t2_cutoff: str = "2026-09-08T00:00:00+08:00",
    cases_fingerprint: str = "sha256:" + "3" * 64,
    legislation_fingerprint: str = "sha256:" + "2" * 64,
) -> bytes:
    t1_cases_fingerprint = "sha256:" + "1" * 64
    t1_legislation_fingerprint = "sha256:" + "2" * 64
    body: dict[str, JsonValue] = {
        "families": ["CASES", "LEGISLATION"],
        "schema_id": "asklegal.hk-v1.acceptance-cutoff-selection",
        "schema_version": "1.0.0",
        "scope_ids": list(_SCOPES),
        "t1": {
            "authentic_changed_families": [],
            "cases_manifest_fingerprint": t1_cases_fingerprint,
            "legislation_manifest_fingerprint": t1_legislation_fingerprint,
            "observation_cutoff": "2026-09-07T00:00:00+08:00",
            "family_acquisition_evidence": _manual_family_evidence(
                t1_cases_fingerprint, t1_legislation_fingerprint
            ),
        },
        "t2": {
            "authentic_changed_families": ["CASES"],
            "cases_manifest_fingerprint": cases_fingerprint,
            "legislation_manifest_fingerprint": legislation_fingerprint,
            "observation_cutoff": t2_cutoff,
            "family_acquisition_evidence": _manual_family_evidence(
                cases_fingerprint, legislation_fingerprint
            ),
        },
    }
    body["fingerprint"] = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    return canonicalize(body)


def _request(kind: AcceptanceCycleKind) -> dict[str, JsonValue]:
    return preflight_acceptance_cycle(
        kind,
        _selection(),
        cutoff_key="t1" if kind is AcceptanceCycleKind.BASELINE else "t2",
        matrix=load_hk_v1_coverage_matrix(),
    ).document()


def _request_for_selection(selection: bytes) -> dict[str, JsonValue]:
    return preflight_acceptance_cycle(
        AcceptanceCycleKind.UPDATE,
        selection,
        cutoff_key="t2",
        matrix=load_hk_v1_coverage_matrix(),
    ).document()


def _request_with_changed_families(*families: str) -> dict[str, JsonValue]:
    """Rebind the exact request identity for the ordinary no-change path."""
    request = _request(AcceptanceCycleKind.UPDATE)
    request["authentic_changed_families"] = list(families)
    return _rebind_request(request)


def _rebind_request(request: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Recompute stable identities after an intentional hostile fixture change."""
    identity = {
        key: request[key]
        for key in (
            "kind",
            "cutoff_key",
            "observation_cutoff",
            "cases_manifest_fingerprint",
            "legislation_manifest_fingerprint",
            "authentic_changed_families",
            "family_acquisition_evidence",
            "cutoff_selection_fingerprint",
            "matrix_revision",
            "matrix_fingerprint",
            "families",
            "scope_ids",
        )
    }
    identifier = sha256(canonicalize(identity)).hexdigest()[:48]
    request["command_id"] = f"cmd_{identifier}"
    request["operation_id"] = f"cyc_{identifier}"
    command_identity = {
        **identity,
        "command_id": request["command_id"],
        "operation_id": request["operation_id"],
    }
    request["command_fingerprint"] = f"sha256:{sha256(canonicalize(command_identity)).hexdigest()}"
    return request


def _seal_manifest(body: dict[str, object]) -> bytes:
    checked = checked_json_value(body)
    assert type(checked) is dict
    unsigned = canonicalize(checked)
    document = {**checked, "fingerprint": f"sha256:{sha256(unsigned).hexdigest()}"}
    return canonicalize(document)


def _cases_manifest(
    cutoff: str,
    cycle_id: str = "cyc_cases_1997_07_03",
    result: str = "COMPLETE",
) -> bytes:
    cutoff_year = int(cutoff[:4])
    return _seal_manifest(
        {
            "cycle_id": cycle_id,
            "discrepancy_refs": [],
            "earliest_decision_date": "1997-07-01",
            "journal_head_fingerprint": "sha256:" + "a" * 64,
            "judgment_bundle_refs": ["cases/judgment-bundles/sha256/" + "b" * 64 + ".json"],
            "observation_cutoff": cutoff,
            "result": result,
            "year_dispositions": [
                {
                    "discovered_judgments": 1 if year == 1997 else 0,
                    "final_page": 1,
                    "first_in_scope_date": ("1997-07-01" if year == 1997 else f"{year:04d}-01-01"),
                    "result": "COMPLETE",
                    "retryable_items": 0,
                    "verified_judgments": 1 if year == 1997 else 0,
                    "verified_listing_pages": 1,
                    "year": year,
                }
                for year in range(1997, cutoff_year + 1)
            ],
        }
    )


def _legislation_manifest(
    cutoff: str,
    cycle_id: str = "cyc_legislation_1997_07_03",
    result: str = "COMPLETE",
) -> bytes:
    scopes = _SCOPES[1:]
    return _seal_manifest(
        {
            "schema_id": "asklegal.legislation-acquisition-manifest",
            "schema_version": "1.0.0",
            "cycle_id": cycle_id,
            "observation_cutoff": cutoff.removesuffix("Z") + "+00:00",
            "scope_dispositions": [
                {
                    "scope_id": scope_id,
                    "required_item_count": 1,
                    "verified_item_count": 1,
                    "retryable_item_count": 0,
                    "rejected_item_count": 0,
                    "result": result,
                }
                for scope_id in scopes
            ],
            "verified_item_refs": ["legislation-item/stable-key/" + "c" * 64],
            "review_issue_refs": [],
            "journal_head_fingerprint": "sha256:" + "d" * 64,
            "source_register_fingerprint": "sha256:" + "e" * 64,
            "source_baseline_fingerprint": "sha256:" + "f" * 64,
            "work_plan_fingerprint": "sha256:" + "0" * 64,
            "result": result,
        }
    )


def _manifest_fingerprint(content: bytes) -> str:
    document = parse_json_bytes(content, max_bytes=4_194_304)
    assert type(document) is dict
    fingerprint = document["fingerprint"]
    assert type(fingerprint) is str
    return fingerprint


def _string(value: JsonValue) -> str:
    assert type(value) is str
    return value


def _acquisition(request: dict[str, JsonValue], result: str = "COMPLETE") -> dict[str, JsonValue]:
    changed = request["authentic_changed_families"]
    assert type(changed) is list
    changed_families = set(changed)
    family_statuses = {
        family: (
            "NO_CHANGE"
            if result == "NO_CHANGE"
            else "COMPLETE"
            if request["kind"] == "BASELINE" or family in changed_families
            else "NO_CHANGE"
        )
        for family in ("CASES", "LEGISLATION")
    }
    return {
        "schema_id": "asklegal.hk-v1.acceptance-acquisition-result",
        "schema_version": "1.0.0",
        "operation_id": _string(request["operation_id"]),
        "command_fingerprint": _string(request["command_fingerprint"]),
        "observation_cutoff": _string(request["observation_cutoff"]),
        "scope_ids": list(_SCOPES),
        "family_manifests": [
            {
                "material_family": "CASES",
                "manifest_fingerprint": _string(request["cases_manifest_fingerprint"]),
                "result": family_statuses["CASES"],
                "retryable_count": 0,
                "rejected_count": 0,
            },
            {
                "material_family": "LEGISLATION",
                "manifest_fingerprint": _string(request["legislation_manifest_fingerprint"]),
                "result": family_statuses["LEGISLATION"],
                "retryable_count": 0,
                "rejected_count": 0,
            },
        ],
        "result": result,
    }


def _legal(request: dict[str, JsonValue], result: str) -> dict[str, JsonValue]:
    ready = result == "PROPOSAL_READY"
    return {
        "schema_id": "asklegal.hk-v1.acceptance-legal-result",
        "schema_version": "1.0.0",
        "operation_id": _string(request["operation_id"]),
        "command_fingerprint": _string(request["command_fingerprint"]),
        "observation_cutoff": _string(request["observation_cutoff"]),
        "families": ["CASES", "LEGISLATION"],
        "scope_results": (
            [
                {
                    "scope_id": scope_id,
                    "result": "COMPLETE",
                    "record_count": 1,
                    "release_id": "rel_" + sha256(scope_id.encode()).hexdigest()[:48],
                    "release_fingerprint": "sha256:"
                    + sha256(f"release:{scope_id}".encode()).hexdigest(),
                    "zero_record_justification_refs": [],
                }
                for scope_id in _SCOPES
            ]
            if ready
            else []
        ),
        "proposal_reference": (
            {
                "vault": "PRIMARY",
                "logical_key": "hk-v1/proposals/exact.json",
                "version_id": "v1",
                "fingerprint": "sha256:" + "9" * 64,
                "byte_length": 42,
            }
            if ready
            else None
        ),
        "blocker_codes": [] if ready else ["LEGAL_PROCESSING_ACCEPTANCE_NOT_READY"],
        "result": result,
    }


class _Context:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def call_activity(self, name: str, *, input: object) -> object:  # noqa: A002
        task = (name, input)
        self.calls.append(task)
        return task


def _context(value: _Context) -> OrchestrationContext:
    return cast("OrchestrationContext", value)


def _object_list(value: object) -> TypeIs[list[dict[str, JsonValue]]]:
    if type(value) is not list:
        return False
    items = cast("list[object]", value)
    return all(type(item) is dict for item in items)


def _finish(
    workflow: Generator[Task[object], object, dict[str, object]],
    values: tuple[object, ...],
) -> dict[str, object]:
    task = next(workflow)
    for value in values:
        try:
            task = workflow.send(value)
        except StopIteration as completed:
            return completed.value
    pytest.fail(f"workflow still waiting on {task!r}")


def test_no_change_returns_before_legal_processing_effect() -> None:
    """Genuine two-family NO_CHANGE never requests legal/model/proposal work."""
    request = _request_with_changed_families()
    context = _Context()

    result = _finish(
        run_hk_v1_acceptance_cycle(_context(context), request),
        (_acquisition(request, "NO_CHANGE"),),
    )

    assert context.calls == [(ACCEPTANCE_ACQUISITION_ACTIVITY, request)]
    assert result["result"] == "NO_CHANGE"


def test_no_change_rejects_a_request_that_claims_an_authentic_change() -> None:
    """A claimed family change cannot be silently converted into NO_CHANGE."""
    request = _request(AcceptanceCycleKind.UPDATE)
    workflow = run_hk_v1_acceptance_cycle(_context(_Context()), request)
    next(workflow)

    with pytest.raises(AcceptanceCoordinatorError, match="ACCEPTANCE_ACQUISITION_INVALID"):
        workflow.send(_acquisition(request, "NO_CHANGE"))


def test_changed_cycle_requires_complete_four_scope_legal_result() -> None:
    """Only a real complete legal result can produce PROPOSAL_READY."""
    request = _request(AcceptanceCycleKind.UPDATE)
    context = _Context()

    result = _finish(
        run_hk_v1_acceptance_cycle(_context(context), request),
        (_acquisition(request), _legal(request, "PROPOSAL_READY")),
    )

    assert [name for name, _payload in context.calls] == [
        ACCEPTANCE_ACQUISITION_ACTIVITY,
        ACCEPTANCE_LEGAL_ACTIVITY,
    ]
    legal_payload = cast("dict[str, JsonValue]", context.calls[1][1])
    assert legal_payload["family_acquisition_evidence"] == request["family_acquisition_evidence"]
    assert result["result"] == "PROPOSAL_READY"


def test_manual_request_cannot_drop_or_drift_family_evidence() -> None:
    """Control refuses a preseed-dependent manual request before any activity call."""
    request = _request(AcceptanceCycleKind.UPDATE)
    missing = dict(request)
    missing.pop("family_acquisition_evidence")
    with pytest.raises(AcceptanceCoordinatorError, match="ACCEPTANCE_REQUEST_INVALID"):
        next(run_hk_v1_acceptance_cycle(_context(_Context()), missing))

    drifted = dict(request)
    family_evidence = cast(
        "dict[str, JsonValue]", checked_json_value(request["family_acquisition_evidence"])
    )
    children = cast("list[JsonValue]", family_evidence["children"])
    first_child = cast("dict[str, JsonValue]", children[0])
    first_child["manifest_fingerprint"] = "sha256:" + "0" * 64
    drifted["family_acquisition_evidence"] = family_evidence
    _rebind_request(drifted)
    with pytest.raises(AcceptanceCoordinatorError, match="ACCEPTANCE_REQUEST_INVALID"):
        next(run_hk_v1_acceptance_cycle(_context(_Context()), drifted))


def test_complete_zero_record_scope_requires_explicit_justification_reference() -> None:
    """A legitimately empty scope is complete only with retained disposition evidence."""
    request = _request(AcceptanceCycleKind.UPDATE)
    legal = _legal(request, "PROPOSAL_READY")
    raw_scopes = legal["scope_results"]
    assert _object_list(raw_scopes)
    scopes = cast("list[dict[str, JsonValue]]", raw_scopes)
    scopes[0]["record_count"] = 0
    scopes[0]["zero_record_justification_refs"] = [
        "hk-v1/legal-processing/zero-record/HK-CASE-BINDING-POST-1997/sha256/" + "a" * 64 + ".json"
    ]

    result = _finish(
        run_hk_v1_acceptance_cycle(_context(_Context()), request),
        (_acquisition(request), legal),
    )

    assert result["result"] == "PROPOSAL_READY"

    scopes[0]["zero_record_justification_refs"] = []
    workflow = run_hk_v1_acceptance_cycle(_context(_Context()), request)
    next(workflow)
    workflow.send(_acquisition(request))
    with pytest.raises(AcceptanceCoordinatorError, match="ACCEPTANCE_LEGAL_RESULT_INVALID"):
        workflow.send(legal)


def test_zero_record_references_follow_the_exact_family_contracts() -> None:
    """Case paths and Desk-issued Legislation references cannot cross family boundaries."""
    request = _request(AcceptanceCycleKind.UPDATE)
    legal = _legal(request, "PROPOSAL_READY")
    raw_scopes = legal["scope_results"]
    assert _object_list(raw_scopes)
    scopes = cast("list[dict[str, JsonValue]]", raw_scopes)
    scopes[1]["record_count"] = 0
    legislation_ref = "ref_" + "b" * 48 + "@sha256:" + "c" * 64
    scopes[1]["zero_record_justification_refs"] = [legislation_ref]

    result = _finish(
        run_hk_v1_acceptance_cycle(_context(_Context()), request),
        (_acquisition(request), legal),
    )
    assert result["result"] == "PROPOSAL_READY"

    scopes[1]["zero_record_justification_refs"] = [
        "hk-v1/legal-processing/zero-record/"
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS/sha256/" + "c" * 64 + ".json"
    ]
    workflow = run_hk_v1_acceptance_cycle(_context(_Context()), request)
    next(workflow)
    workflow.send(_acquisition(request))
    with pytest.raises(AcceptanceCoordinatorError, match="ACCEPTANCE_LEGAL_RESULT_INVALID"):
        workflow.send(legal)

    scopes[1]["record_count"] = 1
    scopes[1]["zero_record_justification_refs"] = []
    scopes[0]["record_count"] = 0
    scopes[0]["zero_record_justification_refs"] = [legislation_ref]
    workflow = run_hk_v1_acceptance_cycle(_context(_Context()), request)
    next(workflow)
    workflow.send(_acquisition(request))
    with pytest.raises(AcceptanceCoordinatorError, match="ACCEPTANCE_LEGAL_RESULT_INVALID"):
        workflow.send(legal)


def test_missing_legal_processing_adapter_stays_truthfully_not_ready() -> None:
    """The durable sequence completes without inventing a proposal artifact."""
    request = _request(AcceptanceCycleKind.BASELINE)

    result = _finish(
        run_hk_v1_acceptance_cycle(_context(_Context()), request),
        (_acquisition(request), _legal(request, "NOT_READY")),
    )

    assert result["result"] == "NOT_READY"
    assert result["proposal_reference"] is None


def test_manifest_fingerprint_or_incomplete_family_fails_before_legal_activity() -> None:
    """Acquisition drift and retryable work cannot cross into legal processing."""
    request = _request(AcceptanceCycleKind.UPDATE)
    acquisition = _acquisition(request)
    raw_families = acquisition["family_manifests"]
    assert _object_list(raw_families)
    families = cast("list[dict[str, JsonValue]]", raw_families)
    families[0]["manifest_fingerprint"] = "sha256:" + "0" * 64
    families[1]["retryable_count"] = 1
    context = _Context()
    workflow = run_hk_v1_acceptance_cycle(_context(context), request)
    next(workflow)

    with pytest.raises(AcceptanceCoordinatorError, match="ACCEPTANCE_ACQUISITION_INVALID"):
        workflow.send(acquisition)

    assert len(context.calls) == 1


def test_restart_replays_the_exact_activity_names_and_payloads() -> None:
    """A restarted durable instance reconstructs the same stable sequence exactly."""
    request = _request(AcceptanceCycleKind.UPDATE)
    contexts = (_Context(), _Context())
    results = [
        _finish(
            run_hk_v1_acceptance_cycle(_context(context), request),
            (_acquisition(request), _legal(request, "NOT_READY")),
        )
        for context in contexts
    ]

    assert contexts[0].calls == contexts[1].calls
    assert results[0] == results[1]


def test_cross_application_request_shape_is_strictly_revalidated_before_activity() -> None:
    """The Control parser accepts the tool request exactly and rejects one-field drift."""
    request = _request(AcceptanceCycleKind.BASELINE)
    context = _Context()
    workflow = run_hk_v1_acceptance_cycle(_context(context), request)
    assert next(workflow) == (ACCEPTANCE_ACQUISITION_ACTIVITY, request)

    changed = dict(request)
    changed["operation_id"] = "cyc_" + "0" * 48
    with pytest.raises(AcceptanceCoordinatorError, match="ACCEPTANCE_REQUEST_INVALID"):
        next(run_hk_v1_acceptance_cycle(_context(_Context()), changed))


def test_local_acquisition_reuses_exact_frozen_pair_without_recapture(tmp_path: Path) -> None:
    """The production boundary rereads both selected manifests and returns their facts."""
    cutoff = "1997-07-03T00:00:00Z"
    root = tmp_path / "acceptance-cutoffs"
    pair = root / "t2"
    pair.mkdir(parents=True)
    cases = _cases_manifest(cutoff)
    legislation = _legislation_manifest(cutoff)
    cases_path = pair / "cases-acquisition-manifest.json"
    legislation_path = pair / "legislation-acquisition-manifest.json"
    cases_path.write_bytes(cases)
    legislation_path.write_bytes(legislation)
    request = _request_for_selection(
        _selection(
            t2_cutoff=cutoff,
            cases_fingerprint=_manifest_fingerprint(cases),
            legislation_fingerprint=_manifest_fingerprint(legislation),
        )
    )
    activities = LocalAcceptanceActivities(
        AcceptanceConfiguration(root), load_hk_v1_coverage_matrix()
    )

    result = activities.start_hk_v1_acceptance_acquisition(
        ActivityContext("acceptance", 1), request
    )

    assert result["result"] == "COMPLETE"
    assert result["operation_id"] == request["operation_id"]
    assert result["observation_cutoff"] == cutoff
    assert cases_path.read_bytes() == cases
    assert legislation_path.read_bytes() == legislation


def test_local_acquisition_rejects_manifest_drift_without_source_mutation(
    tmp_path: Path,
) -> None:
    """A different retained manifest fails without changing either frozen input."""
    cutoff = "1997-07-03T00:00:00Z"
    root = tmp_path / "acceptance-cutoffs"
    pair = root / "t2"
    pair.mkdir(parents=True)
    cases = _cases_manifest(cutoff)
    legislation = _legislation_manifest(cutoff)
    cases_path = pair / "cases-acquisition-manifest.json"
    legislation_path = pair / "legislation-acquisition-manifest.json"
    cases_path.write_bytes(cases)
    legislation_path.write_bytes(legislation)
    request = _request_for_selection(
        _selection(
            t2_cutoff=cutoff,
            cases_fingerprint="sha256:" + "9" * 64,
            legislation_fingerprint=_manifest_fingerprint(legislation),
        )
    )
    activities = LocalAcceptanceActivities(
        AcceptanceConfiguration(root), load_hk_v1_coverage_matrix()
    )

    with pytest.raises(AcceptanceCoordinatorError, match="ACCEPTANCE_ACQUISITION_INVALID"):
        activities.start_hk_v1_acceptance_acquisition(ActivityContext("acceptance", 1), request)

    assert cases_path.read_bytes() == cases
    assert legislation_path.read_bytes() == legislation


class _DueVault:
    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents
        self.calls: list[object] = []

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        self.calls.append(reference)
        return self.contents[reference.logical_key]


def _due_handoff(statuses: tuple[str, str]) -> tuple[dict[str, object], _DueVault]:
    instruction: dict[str, JsonValue] = {
        "cycle_id": "hk-v1-daily-control-20260908",
        "cycle_kind": "DAILY_CURRENT_LAW",
        "scheduled_at": "2026-09-07T18:15:00Z",
        "observation_cutoff": "2026-09-07T18:15:00Z",
        "matrix_revision": load_hk_v1_coverage_matrix().revision,
        "matrix_fingerprint": load_hk_v1_coverage_matrix().fingerprint,
    }
    root_cycle_id = _string(instruction["cycle_id"])
    child_cycle_ids = (
        "cyc_20260908_deadbeefdeadbeef_cases",
        "cyc_20260908_deadbeefdeadbeef_legislation",
    )
    manifests = (
        _cases_manifest(
            _string(instruction["observation_cutoff"]), child_cycle_ids[0], statuses[0]
        ),
        _legislation_manifest(
            _string(instruction["observation_cutoff"]), child_cycle_ids[1], statuses[1]
        ),
    )
    manifest_keys = tuple(
        f"poc/report/hk-v1-due-cycle/{root_cycle_id}/family-manifests/{family.lower()}.json"
        for family in ("CASES", "LEGISLATION")
    )
    manifest_documents = [parse_json_bytes(content, max_bytes=4_194_304) for content in manifests]
    assert all(type(item) is dict for item in manifest_documents)
    children: list[JsonValue] = []
    for family, status, cycle_id, content, key, raw_document in zip(
        ("CASES", "LEGISLATION"),
        statuses,
        child_cycle_ids,
        manifests,
        manifest_keys,
        manifest_documents,
        strict=True,
    ):
        assert type(raw_document) is dict
        content_fingerprint = f"sha256:{sha256(content).hexdigest()}"
        children.append(
            {
                "source_family": family,
                "cycle_id": cycle_id,
                "journal_ref": f"acquisition-journals/{cycle_id}",
                "manifest_fingerprint": raw_document["fingerprint"],
                "journal_head_fingerprint": raw_document["journal_head_fingerprint"],
                "result": status,
                "manifest_reference": {
                    "vault": "PRIMARY",
                    "logical_key": key,
                    "version_id": "v" + content_fingerprint[7:],
                    "fingerprint": content_fingerprint,
                    "byte_length": len(content),
                },
            }
        )
    evidence = canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-v1.scheduled-family-acquisitions",
                "schema_version": "1.0.0",
                "root_instruction": instruction,
                "root_plan_fingerprint": "sha256:" + "5" * 64,
                "children": children,
            }
        )
    )
    evidence_fingerprint = f"sha256:{sha256(evidence).hexdigest()}"
    cycle_id = _string(instruction["cycle_id"])
    due_result: dict[str, object] = {
        "cycle_id": cycle_id,
        "plan_fingerprint": "sha256:" + "5" * 64,
        "manifest_reference": {
            "vault": "PRIMARY",
            "logical_key": hk_v1_due_cycle_manifest_key(cycle_id),
            "version_id": "v" + "6" * 64,
            "fingerprint": "sha256:" + "6" * 64,
            "byte_length": 1,
        },
        "manifest_created": True,
        "predecessor_state_fingerprint": "sha256:" + "7" * 64,
        "predecessor_state_created": True,
        "complete_source_ids": [],
        "missing_source_ids": [],
        "duplicate_source_ids": [],
        "gap_source_ids": [],
        "failed_source_ids": [],
        "accounting_complete": True,
        "release_blocking": False,
        "disposition": "COMPLETE",
        "family_acquisition_evidence": {
            "cycle_id": cycle_id,
            "evidence_reference": {
                "vault": "PRIMARY",
                "logical_key": hk_v1_due_family_acquisition_key(cycle_id),
                "version_id": "v" + evidence_fingerprint[7:],
                "fingerprint": evidence_fingerprint,
                "byte_length": len(evidence),
            },
            "evidence_created": True,
        },
    }
    contents = dict(zip(manifest_keys, manifests, strict=True))
    contents[hk_v1_due_family_acquisition_key(root_cycle_id)] = evidence
    return {"instruction": instruction, "due_result": due_result}, _DueVault(contents)


def test_ordinary_due_no_change_never_creates_a_legal_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two exact NO_CHANGE manifests stop before scheduler/provider/proposal effects."""
    payload, vault = _due_handoff(("NO_CHANGE", "NO_CHANGE"))

    def forbidden(_application: str) -> object:
        message = "Legal scheduler must remain untouched"
        raise AssertionError(message)

    monkeypatch.setattr(v1_acceptance.V1SchedulerSettings, "for_application", forbidden)
    activities = LocalAcceptanceActivities(
        AcceptanceConfiguration(tmp_path),
        load_hk_v1_coverage_matrix(),
        vault,
    )

    result = activities.continue_hk_v1_due_acceptance(ActivityContext("due-no-change", 1), payload)

    assert result["result"] == "NO_CHANGE"
    assert result["proposal_reference"] is None
    assert len(vault.calls) == 3


def test_ordinary_due_rejects_retained_child_manifest_drift_before_legal_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A child ref is useful only while its exact retained canonical bytes still match."""
    payload, vault = _due_handoff(("COMPLETE", "NO_CHANGE"))
    manifest_key = next(key for key in vault.contents if key.endswith("/cases.json"))
    vault.contents[manifest_key] += b"\n"

    def forbidden(_application: str) -> object:
        message = "Drifted child evidence must not reach Legal"
        raise AssertionError(message)

    monkeypatch.setattr(v1_acceptance.V1SchedulerSettings, "for_application", forbidden)
    activities = LocalAcceptanceActivities(
        AcceptanceConfiguration(tmp_path),
        load_hk_v1_coverage_matrix(),
        vault,
    )

    with pytest.raises(AcceptanceCoordinatorError, match="HK_V1_DUE_ACCEPTANCE_INVALID"):
        activities.continue_hk_v1_due_acceptance(ActivityContext("due-drift", 1), payload)


def test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changed evidence reaches the Legal hub once and retains its exact blocker code."""
    payload, vault = _due_handoff(("COMPLETE", "NO_CHANGE"))
    scheduled: list[tuple[object, object, object, object]] = []

    class Client:
        def get_orchestration_state(self, _operation_id: object) -> None:
            return None

        def schedule_new_orchestration(
            self,
            name: object,
            *,
            input: object,  # noqa: A002 - pinned SDK keyword.
            instance_id: object,
            version: object,
        ) -> object:
            scheduled.append((name, input, instance_id, version))
            return instance_id

        def wait_for_orchestration_completion(
            self, _operation_id: object, *, timeout: object
        ) -> object:
            del timeout
            request = cast(
                "dict[str, JsonValue]", cast("dict[str, object]", scheduled[0][1])["request"]
            )
            legal = _legal(request, "NOT_READY")
            legal["blocker_codes"] = ["LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT"]
            return SimpleNamespace(
                runtime_status=OrchestrationStatus.COMPLETED,
                serialized_output=dumps(legal),
            )

    class Scheduler:
        scheduler_service = "dts-general"
        task_hub = "legal-processing"

        def create_client(self, *, default_version: object) -> Client:
            assert default_version == "1.0.0"
            return Client()

    scheduler = Scheduler()

    def scheduler_for(application: str) -> object:
        assert application == "LEGAL_PROCESSING_WORKER"
        return scheduler

    monkeypatch.setattr(
        v1_acceptance.V1SchedulerSettings,
        "for_application",
        scheduler_for,
    )
    activities = LocalAcceptanceActivities(
        AcceptanceConfiguration(tmp_path),
        load_hk_v1_coverage_matrix(),
        vault,
    )

    result = activities.continue_hk_v1_due_acceptance(ActivityContext("due-change", 1), payload)

    assert result["result"] == "NOT_READY"
    assert result["blocker_codes"] == ["LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT"]
    assert scheduled[0][0] == "run_hk_v1_acceptance_legal_processing"
    assert scheduled[0][2] == result["operation_id"]
    assert scheduled[0][3] == "1.0.0"
    dispatched = cast("dict[str, object]", scheduled[0][1])
    family_evidence = cast("dict[str, object]", dispatched["family_acquisition_evidence"])
    assert family_evidence["schema_id"] == ("asklegal.hk-v1.acceptance-family-acquisition-evidence")
    assert (
        family_evidence["root_cycle_id"]
        == (cast("dict[str, object]", payload["instruction"])["cycle_id"])
    )
    assert [
        cast("dict[str, object]", child)["source_family"]
        for child in cast("list[object]", family_evidence["children"])
    ] == ["CASES", "LEGISLATION"]
    forwarded_children = cast("list[object]", family_evidence["children"])
    assert all(
        "manifest_reference" in cast("dict[str, object]", child) for child in forwarded_children
    )
    evidence_reference = cast(
        "dict[str, object]",
        cast(
            "dict[str, object]",
            cast("dict[str, object]", payload["due_result"])["family_acquisition_evidence"],
        )["evidence_reference"],
    )
    retained = parse_json_bytes(
        vault.contents[cast("str", evidence_reference["logical_key"])],
        max_bytes=4_194_304,
    )
    assert type(retained) is dict
    assert forwarded_children == retained["children"]
