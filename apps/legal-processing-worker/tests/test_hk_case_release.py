"""Application-owned negative Hong Kong Cases release checkpoint tests."""

from __future__ import annotations

import ast
import copy
import runpy
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
from typing import TypeIs

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_legal_desks.hk_case_output import HKCaseProposedServingRecord
from asklegal_legal_desks.hk_case_records import HKCaseRecordAccountingCheckpoint
from asklegal_legal_processing_worker.hk_case_release import (
    HKCasePositiveReleaseRequest,
    HKCaseReleaseCandidate,
    HKCaseReleaseGateError,
    HKCaseReleaseGateErrorCode,
    HKCaseReleaseGateStatus,
    build_hk_case_corpus_release,
    canonical_hk_case_release_withholding_checkpoint,
    replay_hk_case_release_withholding_checkpoint,
    withhold_hk_case_release,
    withhold_hk_case_release_after_complete_acquisition,
)

_REPOSITORY_ROOT = Path(__file__).parents[3]
_RECORD_HELPERS: object = runpy.run_path(
    str(_REPOSITORY_ROOT / "packages/legal-desks/tests/test_hk_case_records.py")
)


def _is_object_dictionary(value: object) -> TypeIs[dict[object, object]]:
    return type(value) is dict


def _accounting() -> HKCaseRecordAccountingCheckpoint:
    if not _is_object_dictionary(_RECORD_HELPERS):
        raise TypeError
    factory = _RECORD_HELPERS.get("_complete_checkpoint")
    if not callable(factory):
        raise TypeError
    result: object = factory()
    if type(result) is not HKCaseRecordAccountingCheckpoint:
        raise TypeError
    return result


def test_worker_returns_only_withheld_not_released() -> None:
    """The application boundary emits the single truthful negative status."""
    accounting = _accounting()

    result = withhold_hk_case_release(accounting)

    assert result.status is HKCaseReleaseGateStatus.WITHHELD_NOT_RELEASED
    assert result.accounting_checkpoint_fingerprint == accounting.checkpoint_fingerprint
    assert result.blocker_codes == accounting.blockers
    assert result.listing_count == 1
    assert result.quarantine_listing_ids == ("listing-current",)
    assert result.blocked_listing_ids == ()
    assert result.withholding_fingerprint.startswith("sha256:")


def test_release_boundary_requires_a_complete_cases_manifest_but_stays_withheld() -> None:
    """A complete acquisition reference is admission only, never a positive release."""
    body = {
        "cycle_id": "cyc_cases_1",
        "discrepancy_refs": [],
        "earliest_decision_date": "1997-07-01",
        "journal_head_fingerprint": "sha256:" + "b" * 64,
        "judgment_bundle_refs": ["cases/judgment-bundles/sha256/" + "1" * 64 + ".json"],
        "observation_cutoff": "1997-12-31T00:00:00Z",
        "result": "COMPLETE",
        "year_dispositions": [
            {
                "discovered_judgments": 1,
                "final_page": 1,
                "first_in_scope_date": "1997-07-01",
                "result": "COMPLETE",
                "retryable_items": 0,
                "verified_judgments": 1,
                "verified_listing_pages": 1,
                "year": 1997,
            }
        ],
    }
    raw_unsigned = canonicalize(checked_json_value(body))
    body["fingerprint"] = "sha256:" + sha256(raw_unsigned).hexdigest()

    result = withhold_hk_case_release_after_complete_acquisition(
        canonicalize(checked_json_value(body)), _accounting()
    )

    assert result.status is HKCaseReleaseGateStatus.WITHHELD_NOT_RELEASED


def test_worker_output_has_no_positive_release_surface() -> None:
    """No positive corpus or activation field exists on the refusal result."""
    result = withhold_hk_case_release(_accounting())
    forbidden = {
        "release",
        "records",
        "record_id",
        "release_id",
        "traceability_entries",
        "desired_state",
        "ready",
    }

    assert forbidden.isdisjoint(field.name for field in fields(type(result)))
    encoded = canonical_hk_case_release_withholding_checkpoint(result)
    assert b"FULL JUDGMENT FIXTURE MARKER" not in encoded
    assert b'"WITHHELD_NOT_RELEASED"' in encoded


def test_worker_checkpoint_direct_replace_copy_and_replay_are_coherent() -> None:
    """All output reconstruction paths revalidate the negative fingerprint."""
    result = withhold_hk_case_release(_accounting())

    assert replace(result) == result
    assert copy.copy(result) == result
    assert copy.deepcopy(result) == result
    assert replay_hk_case_release_withholding_checkpoint(result) is result

    object.__setattr__(result, "listing_count", 2)
    with pytest.raises(HKCaseReleaseGateError) as mutated:
        replay_hk_case_release_withholding_checkpoint(result)
    assert mutated.value.code is HKCaseReleaseGateErrorCode.CHECKPOINT_INVALID


def test_worker_owns_the_positive_case_candidate_to_release_mapper() -> None:
    """An exact accepted six-field candidate freezes one real CorpusRelease."""
    payload = {
        "authority_note": "Binding Court of Final Appeal holding.",
        "country": "Hong Kong",
        "jurisdiction": "Hong Kong",
        "source": "Hong Kong Judiciary",
        "text": "A source-faithful legal proposition.",
        "type": "case",
    }
    payload_fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(payload))).hexdigest()
    candidate = HKCaseReleaseCandidate(
        HKCaseProposedServingRecord(
            "rec_" + "1" * 48,
            "proposition_1",
            "sha256:" + "2" * 64,
            "proposition_1",
            payload["text"],
            payload["country"],
            payload["jurisdiction"],
            payload["type"],
            payload["source"],
            payload["authority_note"],
            10,
            len(canonicalize(checked_json_value(payload))),
            payload_fingerprint,
        ),
        "cases/artifacts/sha256/" + "3" * 64 + ".json",
        ("evi_" + "4" * 48,),
    )

    release = build_hk_case_corpus_release(
        HKCasePositiveReleaseRequest(
            "2026-08-16T00:00:00Z",
            (candidate,),
            ("evi_" + "5" * 48,),
            ("val_" + "6" * 48,),
        )
    )

    assert release.scope_id == "HK-CASE-BINDING-POST-1997"
    assert tuple(item.record.record_id for item in release.records) == ("rec_" + "1" * 48,)
    assert release.release_fingerprint.startswith("sha256:")


def test_worker_positive_mapper_preserves_justified_zero_record_semantics() -> None:
    """A complete empty Case scope remains valid only with immutable justification."""
    reference = (
        "hk-v1/legal-processing/zero-record/HK-CASE-BINDING-POST-1997/sha256/" + "7" * 64 + ".json"
    )
    release = build_hk_case_corpus_release(
        HKCasePositiveReleaseRequest(
            "2026-08-16T00:00:00Z",
            (),
            ("evi_" + "5" * 48,),
            ("val_" + "6" * 48,),
            (reference,),
        )
    )

    assert release.records == ()
    assert release.zero_record_justification_refs == (reference,)


def test_worker_positive_mapper_is_present_at_the_application_boundary() -> None:
    """The application now owns the formerly missing Case CorpusRelease mapper."""
    module_path = (
        _REPOSITORY_ROOT
        / "apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_case_release.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }.union(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert any(
        module == "asklegal_corpus" or module.startswith("asklegal_corpus.") for module in imports
    )
    assert "freeze_corpus_release" in called_names


def test_worker_equivalent_path_distinct_accounting_is_deterministic() -> None:
    """Fresh equivalent accounting must freeze identical refusal bytes."""
    first = withhold_hk_case_release(_accounting())
    second = withhold_hk_case_release(_accounting())

    assert first.withholding_fingerprint == second.withholding_fingerprint
    assert canonical_hk_case_release_withholding_checkpoint(first) == (
        canonical_hk_case_release_withholding_checkpoint(second)
    )


def test_worker_normalizes_ordinary_errors_but_leaves_baseexception_visible() -> None:
    """Invalid accounting closes while process-control exceptions escape."""
    accounting = _accounting()
    object.__setattr__(accounting, "checkpoint_fingerprint", "bad")
    with pytest.raises(HKCaseReleaseGateError) as ordinary:
        withhold_hk_case_release(accounting)
    assert ordinary.value.code is HKCaseReleaseGateErrorCode.CHECKPOINT_INVALID

    class _ProcessControlCheckpoint(HKCaseRecordAccountingCheckpoint):
        def __post_init__(self) -> None:
            raise KeyboardInterrupt

    process_control = object.__new__(_ProcessControlCheckpoint)
    with pytest.raises(KeyboardInterrupt):
        withhold_hk_case_release(process_control)
