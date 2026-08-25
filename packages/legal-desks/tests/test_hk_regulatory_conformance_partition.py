"""Executable ADR 0074/0075 HKEX official-partition checkpoint tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_PARTITION_DECISION_CASE_COUNT,
    HKEXPartitionDecisionCase,
    HKEXPartitionError,
    HKEXPartitionErrorCode,
    HKEXPartitionOutcome,
    HKEXPartitionReason,
    decide_hkex_partition_case,
    hkex_partition_decision_case_from_document,
    run_hkex_partition_case,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)
CATALOGUE_PATH = PACKAGE_ROOT / "catalogues/partition-decision-cases.json"
CASE_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-partition-decision-case.schema.json"
REPORT_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-partition-decision-report.schema.json"
CATALOGUE_SCHEMA_PATH = (
    PACKAGE_ROOT / "contracts/schemas/hkex-partition-decision-catalogue.schema.json"
)


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def test_all_24_cases_validate_execute_and_match_complete_frozen_results() -> None:
    catalogue = _document(CATALOGUE_PATH)
    schemas = tuple(
        _document(path) for path in (CATALOGUE_SCHEMA_PATH, CASE_SCHEMA_PATH, REPORT_SCHEMA_PATH)
    )
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
    catalogue_schema, case_schema, report_schema = schemas
    _validator(catalogue_schema).validate(catalogue)

    entries = _objects(catalogue["entries"])
    assert len(entries) == HKEX_PARTITION_DECISION_CASE_COUNT == 24
    assert tuple(entry["case_id"] for entry in entries) == tuple(
        f"HKREG-DET-PAR-{ordinal:03d}" for ordinal in range(1, 25)
    )
    assert tuple(entry["primary_coverage_cell_id"] for entry in entries) == tuple(
        f"HKREG-COV-DPAR-{ordinal:03d}" for ordinal in range(1, 25)
    )
    for entry in entries:
        fixture_raw = (PACKAGE_ROOT / _text(entry["fixture_path"])).read_bytes()
        expected_raw = (PACKAGE_ROOT / _text(entry["expected_path"])).read_bytes()
        assert _raw_fingerprint(fixture_raw) == entry["fixture_fingerprint"]
        assert _raw_fingerprint(expected_raw) == entry["expected_fingerprint"]
        fixture = _json_object(parse_json_bytes(fixture_raw, max_bytes=2_000_000))
        expected = _json_object(parse_json_bytes(expected_raw, max_bytes=1_000_000))
        _validator(case_schema).validate(fixture)
        _validator(report_schema).validate(expected)
        actual = run_hkex_partition_case(
            hkex_partition_decision_case_from_document(fixture)
        ).document()
        assert actual == expected
        assert actual["conformance_status"] == "PASS"
        assert actual["external_effects"] == "NONE"


def test_catalogue_inventory_and_all_three_pairs_are_exact_and_complete() -> None:
    catalogue = _document(CATALOGUE_PATH)
    entries = _objects(catalogue["entries"])
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "fixtures/conformance/partition-decision").iterdir()
        if path.is_file()
    } == {_text(entry["fixture_path"]) for entry in entries}
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "expected/conformance/partition-decision").iterdir()
        if path.is_file()
    } == {_text(entry["expected_path"]) for entry in entries}
    pair_roles: dict[str, set[str]] = {}
    for entry in entries:
        for membership in _objects(entry["pair_memberships"]):
            pair_roles.setdefault(_text(membership["pair_id"]), set()).add(
                _text(membership["role"])
            )
    assert pair_roles == {
        f"HKREG-PAIR-{ordinal:03d}": {"POSITIVE", "NEAR_MISS"} for ordinal in range(38, 41)
    }
    assert catalogue["high_risk_pair_ids"] == [
        "HKREG-PAIR-038",
        "HKREG-PAIR-039",
        "HKREG-PAIR-040",
    ]


def test_every_partition_assertion_is_direct_and_all_terminal_outcomes_exist() -> None:
    entries = _objects(_document(CATALOGUE_PATH)["entries"])
    assert len({_text(entry["assertion_scope"]) for entry in entries}) == 24
    assert {_text(entry["expected_outcome"]) for entry in entries} == {
        "PASS",
        "BLOCK",
        "QUARANTINE",
    }


def test_evaluator_uses_scope_and_facts_not_case_identity() -> None:
    case = _case("HKREG-DET-PAR-010")
    original = decide_hkex_partition_case(case)
    renamed = decide_hkex_partition_case(
        replace(
            case,
            case_id="HKREG-DET-PAR-011",
            primary_coverage_cell_id="HKREG-COV-DPAR-011",
        )
    )
    assert original == renamed
    assert original.reason is HKEXPartitionReason.FEWEST_PARTS_SELECTED


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("UNKNOWN_ROOT", HKEXPartitionErrorCode.CONTRACT),
        ("UNKNOWN_SCOPE", HKEXPartitionErrorCode.CONTRACT),
        ("CASE_CELL_MISMATCH", HKEXPartitionErrorCode.IDENTITY),
        ("PAIR_ROLE_MISMATCH", HKEXPartitionErrorCode.IDENTITY),
        ("EVIDENCE_HASH_MISMATCH", HKEXPartitionErrorCode.FINGERPRINT),
        ("TRUTH_LEAKAGE", HKEXPartitionErrorCode.CONTRACT),
        ("STALE_CASE_FINGERPRINT", HKEXPartitionErrorCode.FINGERPRINT),
    ],
)
def test_strict_envelope_rejects_unknown_misbound_or_leaking_documents(
    mutation: str, code: HKEXPartitionErrorCode
) -> None:
    document = _case_document("HKREG-DET-PAR-001")
    if mutation == "UNKNOWN_ROOT":
        document["undeclared"] = False
    elif mutation == "UNKNOWN_SCOPE":
        document["assertion_scope"] = "INVENTED"
    elif mutation == "CASE_CELL_MISMATCH":
        document["primary_coverage_cell_ids"] = ["HKREG-COV-DPAR-024"]
    elif mutation == "PAIR_ROLE_MISMATCH":
        membership = _mutable_object(_json_array(document["pair_memberships"])[0])
        membership["role"] = "NEAR_MISS"
    elif mutation == "EVIDENCE_HASH_MISMATCH":
        packet = _mutable_object(document["evidence_packet"])
        packet["content_fingerprint"] = f"sha256:{'0' * 64}"
    elif mutation == "TRUTH_LEAKAGE":
        document["evidence_packet_fields"] = ["expected_decision"]
    elif mutation == "STALE_CASE_FINGERPRINT":
        document["title"] = "changed without a new fingerprint"
    with pytest.raises(HKEXPartitionError) as failure:
        hkex_partition_decision_case_from_document(document)
    assert failure.value.code is code


def test_exact_fit_preserves_one_record_and_both_equal_measurements() -> None:
    decision = decide_hkex_partition_case(_case("HKREG-DET-PAR-001"))
    branch = decision.branch_results[0]
    assert decision.partition_required is False
    assert len(branch.parts) == 1
    assert branch.unsplit_text_tokens == branch.text_limit
    assert branch.unsplit_metadata_bytes == branch.metadata_limit
    assert branch.parts[0].serving_label is None


def test_token_byte_and_dual_overflow_are_independently_enforced() -> None:
    token = decide_hkex_partition_case(_case("HKREG-DET-PAR-002")).branch_results[0]
    metadata = decide_hkex_partition_case(_case("HKREG-DET-PAR-003")).branch_results[0]
    dual = decide_hkex_partition_case(_case("HKREG-DET-PAR-004")).branch_results[0]
    assert token.unsplit_text_tokens > token.text_limit
    assert token.unsplit_metadata_bytes <= token.metadata_limit
    assert metadata.unsplit_text_tokens <= metadata.text_limit
    assert metadata.unsplit_metadata_bytes > metadata.metadata_limit
    assert dual.unsplit_text_tokens > dual.text_limit
    assert dual.unsplit_metadata_bytes > dual.metadata_limit
    assert all(part.fits for branch in (token, metadata, dual) for part in branch.parts)


def test_incomplete_measurement_blocks_before_any_fit_result() -> None:
    decision = decide_hkex_partition_case(_case("HKREG-DET-PAR-005"))
    assert decision.outcome is HKEXPartitionOutcome.BLOCK
    assert decision.measurement_complete is False
    assert decision.branch_results == ()
    assert decision.rejected_proposal_codes == ("MISSING_AUTHORITY_NOTE",)


def test_real_labels_force_replanning_and_every_final_part_is_remeasured() -> None:
    decision = decide_hkex_partition_case(_case("HKREG-DET-PAR-006"))
    branch = decision.branch_results[0]
    assert len(branch.parts) == 3
    assert tuple(part.serving_label for part in branch.parts) == (
        "Serving part: 1 of 3",
        "Serving part: 2 of 3",
        "Serving part: 3 of 3",
    )
    assert all(part.fits for part in branch.parts)


def test_only_oversized_child_is_refined_and_largest_safe_sibling_stays_whole() -> None:
    refined = decide_hkex_partition_case(_case("HKREG-DET-PAR-008")).branch_results[0]
    largest = decide_hkex_partition_case(_case("HKREG-DET-PAR-009")).branch_results[0]
    assert tuple(part.record_unit_ids for part in refined.parts) == (
        ("record-a",),
        ("record-b1",),
        ("record-b2",),
        ("record-c",),
    )
    assert tuple(part.record_unit_ids for part in largest.parts) == (
        ("record-a",),
        ("record-b",),
        ("record-c",),
    )


def test_minimum_part_and_earliest_full_rules_choose_the_same_canonical_groups() -> None:
    fewest = decide_hkex_partition_case(_case("HKREG-DET-PAR-010"))
    earliest = decide_hkex_partition_case(_case("HKREG-DET-PAR-011"))
    expected = (("record-unit-a", "record-unit-b"), ("record-unit-c",))
    assert tuple(part.record_unit_ids for part in fewest.branch_results[0].parts) == expected
    assert tuple(part.record_unit_ids for part in earliest.branch_results[0].parts) == expected


def test_applicability_branches_partition_independently() -> None:
    decision = decide_hkex_partition_case(_case("HKREG-DET-PAR-012"))
    assert len(decision.branch_results) == 2
    assert tuple(len(branch.parts) for branch in decision.branch_results) == (2, 3)
    assert len({branch.branch_id for branch in decision.branch_results}) == 2


@pytest.mark.parametrize(
    ("case_id", "reason", "code"),
    [
        (
            "HKREG-DET-PAR-014",
            HKEXPartitionReason.CROSS_NORMAL_BOUNDARY_REJECTED,
            "CROSS_NORMAL_UNIT",
        ),
        ("HKREG-DET-PAR-015", HKEXPartitionReason.UNRELATED_PACKING_REJECTED, "UNRELATED_PACKING"),
        ("HKREG-DET-PAR-017", HKEXPartitionReason.PDF_PAGE_CUT_REJECTED, "PDF_PAGE"),
        (
            "HKREG-DET-PAR-018",
            HKEXPartitionReason.SENTENCE_PUNCTUATION_CUT_REJECTED,
            "SENTENCE_OR_PUNCTUATION",
        ),
        (
            "HKREG-DET-PAR-019",
            HKEXPartitionReason.WHITESPACE_TOKEN_SIZE_CUT_REJECTED,
            "WHITESPACE_TOKEN_OR_PREFERRED",
        ),
        (
            "HKREG-DET-PAR-020",
            HKEXPartitionReason.CHARACTER_VISUAL_WINDOW_CUT_REJECTED,
            "CHARACTER_VISUAL_OR_WINDOW",
        ),
        ("HKREG-DET-PAR-021", HKEXPartitionReason.CONTEXT_REMOVAL_REJECTED, "REMOVE_CONTEXT"),
    ],
)
def test_arbitrary_boundary_packing_and_context_removal_proposals_fail_closed(
    case_id: str, reason: HKEXPartitionReason, code: str
) -> None:
    decision = decide_hkex_partition_case(_case(case_id))
    assert decision.outcome is HKEXPartitionOutcome.BLOCK
    assert decision.reason is reason
    assert decision.rejected_proposal_codes == (code,)
    assert decision.branch_results == ()


def test_official_recursion_keeps_required_context_on_every_emitted_part() -> None:
    decision = decide_hkex_partition_case(_case("HKREG-DET-PAR-022"))
    branch = decision.branch_results[0]
    assert decision.reason is HKEXPartitionReason.RECURSIVE_OFFICIAL_PARTITIONED
    assert len(branch.parts) == 4
    assert all(part.dependency_source_unit_ids == ("context",) for part in branch.parts)
    assert tuple(item for part in branch.parts for item in part.primary_source_unit_ids) == (
        "unit-a",
        "unit-b1",
        "unit-b2",
        "unit-c",
    )


def test_indivisible_and_fixed_metadata_failures_emit_no_part_and_exact_gap() -> None:
    smallest = decide_hkex_partition_case(_case("HKREG-DET-PAR-023"))
    fixed = decide_hkex_partition_case(_case("HKREG-DET-PAR-024"))
    for decision in (smallest, fixed):
        assert decision.outcome is HKEXPartitionOutcome.QUARANTINE
        assert decision.partition_required is True
        assert decision.branch_results[0].parts == ()
        assert len(decision.quarantined_branch_ids) == 1
        assert decision.coverage_gap_ids == (f"HKREG-GAP:{decision.quarantined_branch_ids[0]}",)
    assert smallest.reason is HKEXPartitionReason.SMALLEST_COMPLETE_UNIT_QUARANTINED
    assert fixed.reason is HKEXPartitionReason.FIXED_METADATA_OVER_LIMIT


def test_changed_reference_truth_fails_without_changing_observed_partition() -> None:
    document = _case_document("HKREG-DET-PAR-010")
    expected = _mutable_object(document["expected_decision"])
    expected["outcome"] = "BLOCK"
    expected["reason"] = "UNRELATED_PACKING_REJECTED"
    _refresh_case_fingerprint(document)
    case = hkex_partition_decision_case_from_document(document)
    assert decide_hkex_partition_case(case).outcome is HKEXPartitionOutcome.PASS
    assert run_hkex_partition_case(case).conformance_status == "FAIL"


def _case(case_id: str) -> HKEXPartitionDecisionCase:
    return hkex_partition_decision_case_from_document(_case_document(case_id))


def _case_document(case_id: str) -> dict[str, JsonValue]:
    entry = next(
        item
        for item in _objects(_document(CATALOGUE_PATH)["entries"])
        if item["case_id"] == case_id
    )
    return _document(PACKAGE_ROOT / _text(entry["fixture_path"]))


def _refresh_case_fingerprint(document: dict[str, JsonValue]) -> None:
    projection = dict(document)
    projection.pop("case_fingerprint")
    document["case_fingerprint"] = fingerprint(checked_json_value(projection))


def _document(path: Path) -> dict[str, JsonValue]:
    return _json_object(parse_json_bytes(path.read_bytes(), max_bytes=2_000_000))


def _objects(value: JsonValue) -> tuple[dict[str, JsonValue], ...]:
    return tuple(_json_object(item) for item in _json_array(value))


def _json_object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    assert isinstance(checked, dict)
    return checked


def _mutable_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _json_array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)


def _raw_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"
