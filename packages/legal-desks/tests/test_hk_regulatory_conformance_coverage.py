"""Executable ADR 0074/0075 HKEX source-unit coverage checkpoint tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_COVERAGE_DECISION_CASE_COUNT,
    HKEXCoverageDecisionCase,
    HKEXCoverageError,
    HKEXCoverageErrorCode,
    HKEXCoverageOutcome,
    HKEXCoverageReason,
    HKEXCoverageUnitOutcome,
    decide_hkex_coverage_case,
    hkex_coverage_decision_case_from_document,
    run_hkex_coverage_case,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)
CATALOGUE_PATH = PACKAGE_ROOT / "catalogues/coverage-decision-cases.json"
CASE_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-coverage-decision-case.schema.json"
REPORT_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-coverage-decision-report.schema.json"
CATALOGUE_SCHEMA_PATH = (
    PACKAGE_ROOT / "contracts/schemas/hkex-coverage-decision-catalogue.schema.json"
)


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def test_all_20_cases_validate_execute_and_match_complete_frozen_results() -> None:
    catalogue = _document(CATALOGUE_PATH)
    schemas = tuple(
        _document(path) for path in (CATALOGUE_SCHEMA_PATH, CASE_SCHEMA_PATH, REPORT_SCHEMA_PATH)
    )
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
    catalogue_schema, case_schema, report_schema = schemas
    _validator(catalogue_schema).validate(catalogue)

    entries = _objects(catalogue["entries"])
    assert len(entries) == HKEX_COVERAGE_DECISION_CASE_COUNT == 20
    assert tuple(entry["case_id"] for entry in entries) == tuple(
        f"HKREG-DET-COV-{ordinal:03d}" for ordinal in range(1, 21)
    )
    assert tuple(entry["primary_coverage_cell_id"] for entry in entries) == tuple(
        f"HKREG-COV-DCOV-{ordinal:03d}" for ordinal in range(1, 21)
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
        actual = run_hkex_coverage_case(
            hkex_coverage_decision_case_from_document(fixture)
        ).document()
        assert actual == expected
        assert actual["conformance_status"] == "PASS"
        assert actual["external_effects"] == "NONE"


def test_catalogue_inventory_and_all_five_pairs_are_exact_and_complete() -> None:
    catalogue = _document(CATALOGUE_PATH)
    entries = _objects(catalogue["entries"])
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "fixtures/conformance/coverage-decision").iterdir()
        if path.is_file()
    } == {_text(entry["fixture_path"]) for entry in entries}
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "expected/conformance/coverage-decision").iterdir()
        if path.is_file()
    } == {_text(entry["expected_path"]) for entry in entries}
    pair_roles: dict[str, set[str]] = {}
    for entry in entries:
        for membership in _objects(entry["pair_memberships"]):
            pair_roles.setdefault(_text(membership["pair_id"]), set()).add(
                _text(membership["role"])
            )
    assert pair_roles == {
        f"HKREG-PAIR-{ordinal:03d}": {"POSITIVE", "NEAR_MISS"} for ordinal in range(41, 46)
    }


def test_every_coverage_assertion_is_direct_and_all_outcomes_exist() -> None:
    entries = _objects(_document(CATALOGUE_PATH)["entries"])
    assert len({_text(entry["assertion_scope"]) for entry in entries}) == 20
    assert {_text(entry["expected_outcome"]) for entry in entries} == {
        "PASS",
        "INVALID",
        "COMPLETE_NOT_READY",
    }


def test_evaluator_uses_scope_and_facts_not_case_identity() -> None:
    case = _case("HKREG-DET-COV-001")
    original = decide_hkex_coverage_case(case)
    renamed = decide_hkex_coverage_case(
        replace(
            case,
            case_id="HKREG-DET-COV-007",
            primary_coverage_cell_id="HKREG-COV-DCOV-007",
        )
    )
    assert original == renamed
    assert original.reason is HKEXCoverageReason.COMPLETE_PRIMARY_OWNERSHIP


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("UNKNOWN_ROOT", HKEXCoverageErrorCode.CONTRACT),
        ("UNKNOWN_SCOPE", HKEXCoverageErrorCode.CONTRACT),
        ("CASE_CELL_MISMATCH", HKEXCoverageErrorCode.IDENTITY),
        ("PAIR_ROLE_MISMATCH", HKEXCoverageErrorCode.IDENTITY),
        ("EVIDENCE_HASH_MISMATCH", HKEXCoverageErrorCode.FINGERPRINT),
        ("TRUTH_LEAKAGE", HKEXCoverageErrorCode.CONTRACT),
        ("STALE_CASE_FINGERPRINT", HKEXCoverageErrorCode.FINGERPRINT),
    ],
)
def test_strict_envelope_rejects_unknown_misbound_or_leaking_documents(
    mutation: str,
    code: HKEXCoverageErrorCode,
) -> None:
    document = _case_document("HKREG-DET-COV-001")
    if mutation == "UNKNOWN_ROOT":
        document["undeclared"] = False
    elif mutation == "UNKNOWN_SCOPE":
        document["assertion_scope"] = "INVENTED"
    elif mutation == "CASE_CELL_MISMATCH":
        document["primary_coverage_cell_ids"] = ["HKREG-COV-DCOV-020"]
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
    with pytest.raises(HKEXCoverageError) as failure:
        hkex_coverage_decision_case_from_document(document)
    assert failure.value.code is code


def test_primary_ownership_has_exact_reproducible_totals_and_board_owners() -> None:
    decision = decide_hkex_coverage_case(_case("HKREG-DET-COV-001"))
    assert decision.outcome is HKEXCoverageOutcome.PASS
    assert decision.coverage_complete is True
    assert decision.total_source_unit_count == 8
    assert decision.primary_owned_unit_count == 6
    assert len(decision.board_results) == 2
    assert all(item.search_record_candidate_count == 1 for item in decision.board_results)


def test_unsafe_required_unit_is_explicit_and_never_silently_omitted() -> None:
    decision = decide_hkex_coverage_case(_case("HKREG-DET-COV-002"))
    assert decision.outcome is HKEXCoverageOutcome.COMPLETE_NOT_READY
    assert decision.coverage_complete is True
    assert decision.non_serving_unit_count == decision.total_source_unit_count
    assert decision.board_results[0].blocked_or_quarantined_unit_count == 1
    assert decision.board_results[0].later_gate_candidate_ready is False


def test_repeated_dependency_has_one_primary_owner_and_exact_labelled_pointer() -> None:
    case = _case("HKREG-DET-COV-003")
    dependency = next(
        item
        for item in case.facts.declared_units
        if item.outcome is HKEXCoverageUnitOutcome.PRIMARY and item.dependency_uses
    )
    assert len(dependency.primary_owner_record_ids) == 1
    assert len(dependency.dependency_uses) == 1
    use = dependency.dependency_uses[0]
    assert use.label.startswith("Governing context:")
    assert use.owner_record_id == dependency.primary_owner_record_ids[0]
    assert use.source_fingerprint.startswith("sha256:")


def test_classification_complex_and_noncurrent_units_are_all_explicit() -> None:
    classification = _case("HKREG-DET-COV-004").facts.declared_units
    assert {
        HKEXCoverageUnitOutcome.CONTEXT_ONLY,
        HKEXCoverageUnitOutcome.PRESENTATION_ONLY,
    }.issubset({item.outcome for item in classification})
    assert decide_hkex_coverage_case(_case("HKREG-DET-COV-005")).coverage_complete
    noncurrent = _case("HKREG-DET-COV-006").facts.declared_units
    assert {
        HKEXCoverageUnitOutcome.WAITING_ROOM,
        HKEXCoverageUnitOutcome.HISTORY,
        HKEXCoverageUnitOutcome.QUARANTINED,
        HKEXCoverageUnitOutcome.EXCLUDED,
    }.issubset({item.outcome for item in noncurrent})


@pytest.mark.parametrize(
    ("case_id", "reason", "violation"),
    [
        ("HKREG-DET-COV-008", HKEXCoverageReason.MISSING_SOURCE_UNIT, "MISSING_SOURCE_UNIT"),
        (
            "HKREG-DET-COV-009",
            HKEXCoverageReason.DUPLICATE_PRIMARY_OWNER,
            "DUPLICATE_PRIMARY_OWNER",
        ),
        ("HKREG-DET-COV-010", HKEXCoverageReason.SOURCE_ORDER_CHANGED, "SOURCE_ORDER_CHANGED"),
        ("HKREG-DET-COV-011", HKEXCoverageReason.ORPHANED_OUTPUT, "ORPHAN_OUTPUT"),
        ("HKREG-DET-COV-012", HKEXCoverageReason.WRONG_BOARD_OWNER, "WRONG_BOARD_OWNER"),
        (
            "HKREG-DET-COV-013",
            HKEXCoverageReason.DEPENDENCY_BINDING_INCOMPLETE,
            "DEPENDENCY_BINDING_INCOMPLETE",
        ),
        (
            "HKREG-DET-COV-014",
            HKEXCoverageReason.SOURCE_FIDELITY_CHANGED,
            "SOURCE_FIDELITY_CHANGED",
        ),
    ],
)
def test_missing_duplicate_reordered_orphan_wrong_board_dependency_and_fidelity_fail(
    case_id: str,
    reason: HKEXCoverageReason,
    violation: str,
) -> None:
    decision = decide_hkex_coverage_case(_case(case_id))
    assert decision.outcome is HKEXCoverageOutcome.INVALID
    assert decision.reason is reason
    assert violation in decision.violation_codes
    assert all(item.later_gate_candidate_ready is False for item in decision.board_results)


def test_complete_and_quarantined_proofs_separate_accounting_from_readiness() -> None:
    ready = decide_hkex_coverage_case(_case("HKREG-DET-COV-015"))
    quarantined = decide_hkex_coverage_case(_case("HKREG-DET-COV-016"))
    assert ready.coverage_complete
    assert all(item.later_gate_candidate_ready for item in ready.board_results)
    assert quarantined.coverage_complete
    assert quarantined.board_results[0].later_gate_candidate_ready is False
    assert ready.document(case_id="HKREG-DET-COV-015")["search_record_authorized"] is False


def test_bounded_board_failure_is_isolated_but_shared_gap_blocks_both() -> None:
    isolated = decide_hkex_coverage_case(_case("HKREG-DET-COV-017"))
    shared = decide_hkex_coverage_case(_case("HKREG-DET-COV-018"))
    assert [item.later_gate_candidate_ready for item in isolated.board_results].count(True) == 1
    assert all(item.inventory_bounded is False for item in shared.board_results)
    assert all(item.later_gate_candidate_ready is False for item in shared.board_results)


def test_proxy_counts_cannot_replace_proof_and_zero_output_can_be_complete() -> None:
    proxy = decide_hkex_coverage_case(_case("HKREG-DET-COV-019"))
    zero = decide_hkex_coverage_case(_case("HKREG-DET-COV-020"))
    assert proxy.outcome is HKEXCoverageOutcome.INVALID
    assert proxy.reason is HKEXCoverageReason.WEAK_PROXY_REJECTED
    assert zero.outcome is HKEXCoverageOutcome.PASS
    assert zero.primary_owned_unit_count == 0
    assert zero.non_serving_unit_count == zero.total_source_unit_count
    assert all(item.search_record_candidate_count == 0 for item in zero.board_results)


def test_changed_reference_truth_fails_without_changing_observed_coverage() -> None:
    document = _case_document("HKREG-DET-COV-001")
    expected = _mutable_object(document["expected_decision"])
    expected["outcome"] = "INVALID"
    expected["reason"] = "MISSING_SOURCE_UNIT"
    _refresh_case_fingerprint(document)
    case = hkex_coverage_decision_case_from_document(document)
    assert decide_hkex_coverage_case(case).outcome is HKEXCoverageOutcome.PASS
    assert run_hkex_coverage_case(case).conformance_status == "FAIL"


def _case(case_id: str) -> HKEXCoverageDecisionCase:
    return hkex_coverage_decision_case_from_document(_case_document(case_id))


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


def _raw_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)
