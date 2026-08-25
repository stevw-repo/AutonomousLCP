"""Executable ADR 0074/0075 HKEX identity/lineage checkpoint tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue
from asklegal_legal_desks import (
    HKEX_IDENTITY_DECISION_CASE_COUNT,
    HKEXIdentityDecisionCase,
    HKEXIdentityDecisionError,
    HKEXIdentityDecisionErrorCode,
    HKEXIdentityDecisionOutcome,
    HKEXIdentityDecisionReason,
    HKEXIdentityRecordAction,
    HKEXIdentityTraceabilityAction,
    decide_hkex_identity_case,
    hkex_identity_decision_case_from_document,
    run_hkex_identity_case,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)
CATALOGUE_PATH = PACKAGE_ROOT / "catalogues/identity-decision-cases.json"
CASE_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-identity-decision-case.schema.json"
REPORT_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-identity-decision-report.schema.json"
CATALOGUE_SCHEMA_PATH = (
    PACKAGE_ROOT / "contracts/schemas/hkex-identity-decision-catalogue.schema.json"
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
    assert len(entries) == HKEX_IDENTITY_DECISION_CASE_COUNT == 24
    assert tuple(entry["case_id"] for entry in entries) == tuple(
        f"HKREG-DET-IDN-{ordinal:03d}" for ordinal in range(1, 25)
    )
    assert tuple(entry["primary_coverage_cell_id"] for entry in entries) == tuple(
        f"HKREG-COV-DIDN-{ordinal:03d}" for ordinal in range(1, 25)
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
        actual = run_hkex_identity_case(
            hkex_identity_decision_case_from_document(fixture)
        ).document()
        assert actual == expected
        assert actual["conformance_status"] == "PASS"
        assert actual["external_effects"] == "NONE"


def test_catalogue_inventory_and_all_four_pairs_are_exact_and_complete() -> None:
    catalogue = _document(CATALOGUE_PATH)
    entries = _objects(catalogue["entries"])
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "fixtures/conformance/identity-decision").iterdir()
        if path.is_file()
    } == {_text(entry["fixture_path"]) for entry in entries}
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "expected/conformance/identity-decision").iterdir()
        if path.is_file()
    } == {_text(entry["expected_path"]) for entry in entries}
    pair_roles: dict[str, set[str]] = {}
    for entry in entries:
        for membership in _objects(entry["pair_memberships"]):
            pair_roles.setdefault(_text(membership["pair_id"]), set()).add(
                _text(membership["role"])
            )
    assert pair_roles == {
        f"HKREG-PAIR-{ordinal:03d}": {"POSITIVE", "NEAR_MISS"} for ordinal in range(46, 50)
    }


def test_every_identity_assertion_is_direct_and_all_outcomes_exist() -> None:
    entries = _objects(_document(CATALOGUE_PATH)["entries"])
    assert len({_text(entry["assertion_scope"]) for entry in entries}) == 24
    assert {_text(entry["expected_outcome"]) for entry in entries} == {
        "PASS",
        "REQUIRE_NEW_RECORD",
        "BLOCK",
        "QUARANTINE",
    }


def test_evaluator_uses_scope_and_facts_not_case_identity() -> None:
    case = _case("HKREG-DET-IDN-002")
    original = decide_hkex_identity_case(case)
    renamed = decide_hkex_identity_case(
        replace(
            case,
            case_id="HKREG-DET-IDN-011",
            primary_coverage_cell_id="HKREG-COV-DIDN-011",
        )
    )
    assert original == renamed
    assert original.reason is HKEXIdentityDecisionReason.EXACT_RECORD_REUSED


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("UNKNOWN_ROOT", HKEXIdentityDecisionErrorCode.CONTRACT),
        ("UNKNOWN_SCOPE", HKEXIdentityDecisionErrorCode.CONTRACT),
        ("CASE_CELL_MISMATCH", HKEXIdentityDecisionErrorCode.IDENTITY),
        ("PAIR_ROLE_MISMATCH", HKEXIdentityDecisionErrorCode.IDENTITY),
        ("EVIDENCE_HASH_MISMATCH", HKEXIdentityDecisionErrorCode.FINGERPRINT),
        ("TRUTH_LEAKAGE", HKEXIdentityDecisionErrorCode.CONTRACT),
        ("STALE_CASE_FINGERPRINT", HKEXIdentityDecisionErrorCode.FINGERPRINT),
    ],
)
def test_strict_envelope_rejects_unknown_misbound_or_leaking_documents(
    mutation: str,
    code: HKEXIdentityDecisionErrorCode,
) -> None:
    document = _case_document("HKREG-DET-IDN-002")
    if mutation == "UNKNOWN_ROOT":
        document["undeclared"] = False
    elif mutation == "UNKNOWN_SCOPE":
        document["assertion_scope"] = "INVENTED"
    elif mutation == "CASE_CELL_MISMATCH":
        document["primary_coverage_cell_ids"] = ["HKREG-COV-DIDN-024"]
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
    with pytest.raises(HKEXIdentityDecisionError) as failure:
        hkex_identity_decision_case_from_document(document)
    assert failure.value.code is code


def test_board_separation_reuse_reselection_and_all_payload_changes_are_exact() -> None:
    board = decide_hkex_identity_case(_case("HKREG-DET-IDN-001"))
    assert board.board_separation_valid
    assert board.record_action is HKEXIdentityRecordAction.SEPARATE_INITIALS
    assert board.register_allocation_count == 2

    reuse = decide_hkex_identity_case(_case("HKREG-DET-IDN-002"))
    assert reuse.record_action is HKEXIdentityRecordAction.REUSE
    assert reuse.register_allocation_count == 0
    reselect = decide_hkex_identity_case(_case("HKREG-DET-IDN-003"))
    assert reselect.record_action is HKEXIdentityRecordAction.RESELECT
    assert reselect.predecessor_search_record_ids == ()

    for ordinal in range(4, 11):
        decision = decide_hkex_identity_case(_case(f"HKREG-DET-IDN-{ordinal:03d}"))
        assert decision.outcome is HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD
        assert decision.record_action is HKEXIdentityRecordAction.REQUIRE_NEW
        assert decision.register_allocation_count >= 1
    authority = decide_hkex_identity_case(_case("HKREG-DET-IDN-010"))
    assert authority.cached_embedding_reuse_permitted


def test_traceability_only_changes_do_not_churn_search_record_identity() -> None:
    for ordinal in range(11, 15):
        decision = decide_hkex_identity_case(_case(f"HKREG-DET-IDN-{ordinal:03d}"))
        assert decision.outcome is HKEXIdentityDecisionOutcome.PASS
        assert decision.register_allocation_count == 0
        assert decision.traceability_action is HKEXIdentityTraceabilityAction.REVISE
    defect = decide_hkex_identity_case(_case("HKREG-DET-IDN-015"))
    assert defect.outcome is HKEXIdentityDecisionOutcome.BLOCK
    assert not defect.cached_embedding_reuse_permitted


def test_lookup_lineage_and_continuity_fail_closed_on_exact_negative_facts() -> None:
    assert decide_hkex_identity_case(_case("HKREG-DET-IDN-016")).lookup_valid
    assert not decide_hkex_identity_case(_case("HKREG-DET-IDN-017")).lookup_valid
    wrong_owner = decide_hkex_identity_case(_case("HKREG-DET-IDN-018"))
    assert wrong_owner.violation_codes == ("LOOKUP_OWNERSHIP_MISMATCH",)

    assert decide_hkex_identity_case(_case("HKREG-DET-IDN-019")).lineage_valid
    assert decide_hkex_identity_case(_case("HKREG-DET-IDN-020")).lineage_valid
    cycle = decide_hkex_identity_case(_case("HKREG-DET-IDN-021"))
    assert not cycle.lineage_valid
    assert "LINEAGE_CYCLE" in cycle.violation_codes

    proved = decide_hkex_identity_case(_case("HKREG-DET-IDN-022"))
    assert proved.outcome is HKEXIdentityDecisionOutcome.PASS
    ambiguous = decide_hkex_identity_case(_case("HKREG-DET-IDN-023"))
    assert ambiguous.outcome is HKEXIdentityDecisionOutcome.QUARANTINE
    assert ambiguous.quarantine_required
    mismatch = decide_hkex_identity_case(_case("HKREG-DET-IDN-024"))
    assert mismatch.violation_codes == ("LOOKUP_FINGERPRINT_MISMATCH",)


def test_changed_reference_truth_produces_fail_not_self_fulfilling_pass() -> None:
    case = _case("HKREG-DET-IDN-002")
    wrong_expected = replace(
        case.expected_decision,
        outcome=HKEXIdentityDecisionOutcome.BLOCK,
        reason=HKEXIdentityDecisionReason.LOOKUP_INCOMPLETE,
    )
    report = run_hkex_identity_case(replace(case, expected_decision=wrong_expected))
    assert report.conformance_status == "FAIL"
    assert report.observed_decision != report.expected_decision


def _case(case_id: str) -> HKEXIdentityDecisionCase:
    return hkex_identity_decision_case_from_document(_case_document(case_id))


def _case_document(case_id: str) -> dict[str, JsonValue]:
    return _document(PACKAGE_ROOT / f"fixtures/conformance/identity-decision/{case_id}.json")


def _document(path: Path) -> dict[str, JsonValue]:
    return _json_object(parse_json_bytes(path.read_bytes(), max_bytes=2_000_000))


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _mutable_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _json_array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _objects(value: JsonValue) -> list[dict[str, JsonValue]]:
    return [_json_object(item) for item in _json_array(value)]


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _raw_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)
