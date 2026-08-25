"""Executable ADR 0074/0075 HKEX record-boundary checkpoint tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_BOUNDARY_DECISION_CASE_COUNT,
    HKEXBoundaryDecisionCase,
    HKEXBoundaryDecisionError,
    HKEXBoundaryDecisionErrorCode,
    HKEXBoundaryOutcome,
    HKEXBoundaryReason,
    decide_hkex_boundary_case,
    hkex_boundary_decision_case_from_document,
    run_hkex_boundary_case,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)
CATALOGUE_PATH = PACKAGE_ROOT / "catalogues/boundary-decision-cases.json"
CASE_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-boundary-decision-case.schema.json"
REPORT_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-boundary-decision-report.schema.json"
CATALOGUE_SCHEMA_PATH = (
    PACKAGE_ROOT / "contracts/schemas/hkex-boundary-decision-catalogue.schema.json"
)


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def test_all_30_cases_validate_execute_and_match_complete_frozen_decisions() -> None:
    catalogue = _document(CATALOGUE_PATH)
    catalogue_schema = _document(CATALOGUE_SCHEMA_PATH)
    case_schema = _document(CASE_SCHEMA_PATH)
    report_schema = _document(REPORT_SCHEMA_PATH)
    for schema in (catalogue_schema, case_schema, report_schema):
        Draft202012Validator.check_schema(schema)
    _validator(catalogue_schema).validate(catalogue)

    entries = _objects(catalogue["entries"])
    assert len(entries) == HKEX_BOUNDARY_DECISION_CASE_COUNT == 30
    assert tuple(entry["case_id"] for entry in entries) == tuple(
        f"HKREG-DEC-BND-{ordinal:03d}" for ordinal in range(1, 31)
    )
    assert tuple(entry["primary_coverage_cell_id"] for entry in entries) == tuple(
        f"HKREG-COV-DBND-{ordinal:03d}" for ordinal in range(1, 31)
    )

    for entry in entries:
        fixture_raw = (PACKAGE_ROOT / _text(entry["fixture_path"])).read_bytes()
        expected_raw = (PACKAGE_ROOT / _text(entry["expected_path"])).read_bytes()
        assert _raw_fingerprint(fixture_raw) == entry["fixture_fingerprint"]
        assert _raw_fingerprint(expected_raw) == entry["expected_fingerprint"]
        fixture = _json_object(parse_json_bytes(fixture_raw, max_bytes=500_000))
        expected = _json_object(parse_json_bytes(expected_raw, max_bytes=100_000))
        _validator(case_schema).validate(fixture)
        _validator(report_schema).validate(expected)

        actual = run_hkex_boundary_case(
            hkex_boundary_decision_case_from_document(fixture)
        ).document()
        assert actual == expected
        assert actual["conformance_status"] == "PASS"
        for field in (
            "source_authorized",
            "provider_authorized",
            "release_authorized",
            "serving_authorized",
            "deployment_authorized",
        ):
            assert actual[field] is False
        assert actual["external_effects"] == "NONE"


def test_catalogue_is_exact_and_all_seven_high_risk_pairs_are_complete() -> None:
    catalogue = _document(CATALOGUE_PATH)
    entries = _objects(catalogue["entries"])
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "fixtures/conformance/boundary-decision").iterdir()
        if path.is_file()
    } == {_text(entry["fixture_path"]) for entry in entries}
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "expected/conformance/boundary-decision").iterdir()
        if path.is_file()
    } == {_text(entry["expected_path"]) for entry in entries}

    pair_roles: dict[str, set[str]] = {}
    for entry in entries:
        for membership in _objects(entry["pair_memberships"]):
            pair_roles.setdefault(_text(membership["pair_id"]), set()).add(
                _text(membership["role"])
            )
    assert pair_roles == {
        f"HKREG-PAIR-{ordinal:03d}": {"POSITIVE", "NEAR_MISS"} for ordinal in range(25, 32)
    }
    assert catalogue["high_risk_pair_ids"] == [
        f"HKREG-PAIR-{ordinal:03d}" for ordinal in range(25, 32)
    ]


def test_checkpoint_covers_every_boundary_assertion_scope_and_terminal_outcome() -> None:
    entries = _objects(_document(CATALOGUE_PATH)["entries"])
    assert {_text(entry["assertion_scope"]) for entry in entries} == {
        "NORMAL_UNIT",
        "GOVERNING_DEPENDENCY",
        "DEFINITION",
        "LEGAL_STRUCTURE",
        "CROSS_REFERENCE",
    }
    assert {_text(entry["expected_outcome"]) for entry in entries} == {
        "PASS",
        "BLOCK",
        "QUARANTINE",
    }
    assert len({_text(entry["expected_reason"]) for entry in entries}) == 22


def test_evaluator_derives_result_from_facts_and_scope_not_case_id() -> None:
    case = _case("HKREG-DEC-BND-001")
    original = decide_hkex_boundary_case(case)
    renamed = decide_hkex_boundary_case(
        replace(
            case,
            case_id="HKREG-DEC-BND-004",
            primary_coverage_cell_id="HKREG-COV-DBND-004",
        )
    )
    assert original == renamed
    assert original.outcome is HKEXBoundaryOutcome.PASS
    assert original.reason is HKEXBoundaryReason.ONE_COMPLETE_NORMAL_UNIT


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("UNKNOWN_ROOT", HKEXBoundaryDecisionErrorCode.CONTRACT),
        ("UNKNOWN_SCOPE", HKEXBoundaryDecisionErrorCode.CONTRACT),
        ("CASE_CELL_MISMATCH", HKEXBoundaryDecisionErrorCode.IDENTITY),
        ("PAIR_ROLE_MISMATCH", HKEXBoundaryDecisionErrorCode.IDENTITY),
        ("EVIDENCE_HASH_MISMATCH", HKEXBoundaryDecisionErrorCode.FINGERPRINT),
        ("TRUTH_LEAKAGE", HKEXBoundaryDecisionErrorCode.CONTRACT),
        ("STALE_CASE_FINGERPRINT", HKEXBoundaryDecisionErrorCode.FINGERPRINT),
    ],
)
def test_strict_envelope_rejects_unknown_misbound_or_leaking_documents(
    mutation: str, code: HKEXBoundaryDecisionErrorCode
) -> None:
    document = _case_document("HKREG-DEC-BND-002")
    if mutation == "UNKNOWN_ROOT":
        document["undeclared"] = False
    elif mutation == "UNKNOWN_SCOPE":
        document["assertion_scope"] = "FUTURE_SCOPE"
    elif mutation == "CASE_CELL_MISMATCH":
        document["primary_coverage_cell_ids"] = ["HKREG-COV-DBND-030"]
    elif mutation == "PAIR_ROLE_MISMATCH":
        membership = _json_array(document["pair_memberships"])[0]
        _mutable_object(membership)["role"] = "NEAR_MISS"
    elif mutation == "EVIDENCE_HASH_MISMATCH":
        _mutable_object(document["evidence_packet"])["content_fingerprint"] = f"sha256:{'0' * 64}"
    elif mutation == "TRUTH_LEAKAGE":
        document["evidence_packet_fields"] = ["case_id"]
    elif mutation == "STALE_CASE_FINGERPRINT":
        document["title"] = "changed without a new case fingerprint"

    with pytest.raises(HKEXBoundaryDecisionError) as failure:
        hkex_boundary_decision_case_from_document(document)
    assert failure.value.code is code


def test_independent_and_dependent_children_have_opposite_responsibilities() -> None:
    independent = decide_hkex_boundary_case(_case("HKREG-DEC-BND-027"))
    dependent = decide_hkex_boundary_case(_case("HKREG-DEC-BND-028"))
    assert independent.outcome is HKEXBoundaryOutcome.PASS
    assert tuple(item.record_unit_id for item in independent.responsibilities) == (
        "record-independent-child-27",
    )
    assert dependent.outcome is HKEXBoundaryOutcome.BLOCK
    assert dependent.responsibilities[0].record_unit_id == "record-parent-28"
    assert dependent.rejected_candidate


def test_references_never_copy_target_text_and_changed_target_is_relationship_only() -> None:
    ordinary = decide_hkex_boundary_case(_case("HKREG-DEC-BND-021"))
    copied = decide_hkex_boundary_case(_case("HKREG-DEC-BND-022"))
    cross_board = decide_hkex_boundary_case(_case("HKREG-DEC-BND-025"))
    changed = decide_hkex_boundary_case(_case("HKREG-DEC-BND-026"))
    assert ordinary.references[0].referring_words == "see rule-21-target"
    assert ordinary.references[0].referring_scope_id == "HK-REG-HKEX-MAIN-BOARD"
    assert copied.outcome is HKEXBoundaryOutcome.BLOCK
    assert all(not reference.target_text_included for reference in copied.references)
    assert cross_board.references[0].referring_scope_id == "HK-REG-HKEX-MAIN-BOARD"
    assert cross_board.references[0].target_scope_id == "HK-REG-HKEX-GEM"
    assert changed.outcome is HKEXBoundaryOutcome.PASS
    assert changed.relationship_revision_only
    assert not changed.referring_payload_change_required


def test_exclusion_and_quarantine_results_name_the_exact_affected_units() -> None:
    background = decide_hkex_boundary_case(_case("HKREG-DEC-BND-019"))
    unresolved = decide_hkex_boundary_case(_case("HKREG-DEC-BND-024"))
    over_limit = decide_hkex_boundary_case(_case("HKREG-DEC-BND-029"))
    assert background.excluded_background_unit_ids == ("helpful-background-19",)
    assert unresolved.quarantined_unit_ids == ("unit-24",)
    assert over_limit.quarantined_unit_ids == ("complete-unit-29",)


def test_changed_reference_truth_fails_without_changing_observed_decision() -> None:
    document = _case_document("HKREG-DEC-BND-001")
    expected = _mutable_object(document["expected_decision"])
    expected["outcome"] = "BLOCK"
    expected["reason"] = "UNRELATED_PACKING_REJECTED"
    _refresh_case_fingerprint(document)

    case = hkex_boundary_decision_case_from_document(document)
    assert decide_hkex_boundary_case(case).outcome is HKEXBoundaryOutcome.PASS
    assert run_hkex_boundary_case(case).conformance_status == "FAIL"


def _case(case_id: str) -> HKEXBoundaryDecisionCase:
    return hkex_boundary_decision_case_from_document(_case_document(case_id))


def _case_document(case_id: str) -> dict[str, JsonValue]:
    entry = next(
        entry
        for entry in _objects(_document(CATALOGUE_PATH)["entries"])
        if entry["case_id"] == case_id
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
