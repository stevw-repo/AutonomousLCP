"""Executable ADR 0074/0075 HKEX effective-state checkpoint tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_STATE_DECISION_CASE_COUNT,
    HKEXRecordResponsibility,
    HKEXStateConformanceOutcome,
    HKEXStateDecisionCase,
    HKEXStateDecisionError,
    HKEXStateDecisionErrorCode,
    HKEXStateDecisionReason,
    decide_hkex_state_case,
    hkex_state_decision_case_from_document,
    run_hkex_state_case,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)
CATALOGUE_PATH = PACKAGE_ROOT / "catalogues/state-decision-cases.json"
CASE_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-state-decision-case.schema.json"
REPORT_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-state-decision-report.schema.json"
CATALOGUE_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-state-decision-catalogue.schema.json"


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def test_all_51_cases_validate_execute_and_match_complete_frozen_decisions() -> None:
    catalogue = _document(CATALOGUE_PATH)
    catalogue_schema = _document(CATALOGUE_SCHEMA_PATH)
    case_schema = _document(CASE_SCHEMA_PATH)
    report_schema = _document(REPORT_SCHEMA_PATH)
    for schema in (catalogue_schema, case_schema, report_schema):
        Draft202012Validator.check_schema(schema)
    _validator(catalogue_schema).validate(catalogue)

    entries = _objects(catalogue["entries"])
    assert len(entries) == HKEX_STATE_DECISION_CASE_COUNT == 51
    assert tuple(entry["case_id"] for entry in entries) == tuple(
        f"HKREG-DEC-STA-{ordinal:03d}" for ordinal in range(1, 52)
    )
    assert tuple(entry["primary_coverage_cell_id"] for entry in entries) == tuple(
        f"HKREG-COV-DSTA-{ordinal:03d}" for ordinal in range(1, 52)
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

        actual = run_hkex_state_case(hkex_state_decision_case_from_document(fixture)).document()
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


def test_catalogue_is_exact_and_all_nine_high_risk_pairs_are_complete() -> None:
    catalogue = _document(CATALOGUE_PATH)
    entries = _objects(catalogue["entries"])
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "fixtures/conformance/state-decision").iterdir()
        if path.is_file()
    } == {_text(entry["fixture_path"]) for entry in entries}
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "expected/conformance/state-decision").iterdir()
        if path.is_file()
    } == {_text(entry["expected_path"]) for entry in entries}

    pair_roles: dict[str, set[str]] = {}
    for entry in entries:
        for membership in _objects(entry["pair_memberships"]):
            pair_roles.setdefault(_text(membership["pair_id"]), set()).add(
                _text(membership["role"])
            )
    assert pair_roles == {
        f"HKREG-PAIR-{ordinal:03d}": {"POSITIVE", "NEAR_MISS"} for ordinal in range(16, 25)
    }
    assert catalogue["high_risk_pair_ids"] == [
        f"HKREG-PAIR-{ordinal:03d}" for ordinal in range(16, 25)
    ]


def test_expected_inventory_covers_every_distinct_state_consequence() -> None:
    entries = _objects(_document(CATALOGUE_PATH)["entries"])
    observed = {
        _text(entry["case_id"]): (
            _text(entry["expected_outcome"]),
            _text(entry["expected_reason"]),
        )
        for entry in entries
    }
    assert observed["HKREG-DEC-STA-008"] == ("PASS", "NON_RULE_NOT_APPLICABLE")
    assert observed["HKREG-DEC-STA-017"] == ("QUARANTINE", "COMPONENT_SUMMARIZED")
    assert observed["HKREG-DEC-STA-037"] == (
        "PASS",
        "SEPARATE_COMPLETE_RECORDS_REQUIRED",
    )
    assert observed["HKREG-DEC-STA-043"] == (
        "PASS",
        "EFFECTIVE_FACT_ORDER_APPLIED",
    )
    assert observed["HKREG-DEC-STA-047"] == (
        "PASS",
        "LAST_APPROVED_CARRY_FORWARD",
    )
    assert observed["HKREG-DEC-STA-049"] == ("BLOCK", "NO_NEW_TARGET")
    assert observed["HKREG-DEC-STA-051"] == (
        "QUARANTINE",
        "UNKNOWN_REPAIR_REJECTED",
    )


def test_evaluator_derives_result_from_facts_and_scope_not_case_id() -> None:
    case = _case("HKREG-DEC-STA-001")
    original = decide_hkex_state_case(case)
    renamed = decide_hkex_state_case(
        replace(
            case,
            case_id="HKREG-DEC-STA-002",
            primary_coverage_cell_id="HKREG-COV-DSTA-002",
        )
    )
    assert original == renamed
    assert original.outcome is HKEXStateConformanceOutcome.PASS
    assert original.reason is HKEXStateDecisionReason.ATOMIC_STATE_DECIDED


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("UNKNOWN_ROOT", HKEXStateDecisionErrorCode.CONTRACT),
        ("UNKNOWN_SCOPE", HKEXStateDecisionErrorCode.CONTRACT),
        ("CASE_CELL_MISMATCH", HKEXStateDecisionErrorCode.IDENTITY),
        ("PAIR_ROLE_MISMATCH", HKEXStateDecisionErrorCode.IDENTITY),
        ("EVIDENCE_HASH_MISMATCH", HKEXStateDecisionErrorCode.FINGERPRINT),
        ("TRUTH_LEAKAGE", HKEXStateDecisionErrorCode.CONTRACT),
        ("STALE_CASE_FINGERPRINT", HKEXStateDecisionErrorCode.FINGERPRINT),
    ],
)
def test_strict_envelope_rejects_unknown_misbound_or_leaking_documents(
    mutation: str,
    code: HKEXStateDecisionErrorCode,
) -> None:
    document = _case_document("HKREG-DEC-STA-004")
    if mutation == "UNKNOWN_ROOT":
        document["undeclared"] = False
    elif mutation == "UNKNOWN_SCOPE":
        document["assertion_scope"] = "FUTURE_SCOPE"
    elif mutation == "CASE_CELL_MISMATCH":
        document["primary_coverage_cell_ids"] = ["HKREG-COV-DSTA-051"]
    elif mutation == "PAIR_ROLE_MISMATCH":
        membership = _json_array(document["pair_memberships"])[0]
        _mutable_object(membership)["role"] = "NEAR_MISS"
    elif mutation == "EVIDENCE_HASH_MISMATCH":
        _mutable_object(document["evidence_packet"])["content_fingerprint"] = f"sha256:{'0' * 64}"
    elif mutation == "TRUTH_LEAKAGE":
        document["evidence_packet_fields"] = ["case_id"]
    elif mutation == "STALE_CASE_FINGERPRINT":
        document["title"] = "changed without a new case fingerprint"

    with pytest.raises(HKEXStateDecisionError) as failure:
        hkex_state_decision_case_from_document(document)
    assert failure.value.code is code


def test_exact_non_hong_kong_time_zone_is_applied_before_state_decision() -> None:
    decision = decide_hkex_state_case(_case("HKREG-DEC-STA-023"))
    assert decision.branch_decisions[0].state.value == "CURRENT"


def test_complete_component_summary_preserves_every_branch_decision() -> None:
    decision = decide_hkex_state_case(_case("HKREG-DEC-STA-011"))
    assert decision.component_state is not None
    assert decision.component_state.value == "CURRENT"
    assert tuple(item.state.value for item in decision.branch_decisions) == (
        "CURRENT",
        "FUTURE_FIXED_DATE",
    )


def test_record_responsibility_and_effective_order_are_explicit() -> None:
    separate = decide_hkex_state_case(_case("HKREG-DEC-STA-037"))
    limited = decide_hkex_state_case(_case("HKREG-DEC-STA-038"))
    ordered = decide_hkex_state_case(_case("HKREG-DEC-STA-043"))
    assert separate.record_responsibility is HKEXRecordResponsibility.SEPARATE_COMPLETE_RECORDS
    assert limited.record_responsibility is HKEXRecordResponsibility.ONE_LIMITED_RECORD_ELIGIBLE
    assert ordered.ordered_branch_ids == (
        "branch-043-a",
        "branch-043-c",
        "branch-043-b",
    )


def test_carry_forward_preserves_complete_support_but_never_claims_freshness() -> None:
    decision = decide_hkex_state_case(_case("HKREG-DEC-STA-047"))
    assert decision.carry_forward_support is not None
    assert decision.carry_forward_support.last_approved_status == "APPROVED_CURRENT"
    assert decision.carry_forward_support.coverage_gap_id == "coverage-gap-047"
    assert decision.branch_decisions[0].state.value == "UNKNOWN"
    assert not decision.rebuild_target_authorized


def test_changed_current_product_fact_changes_result_without_case_identity() -> None:
    document = _case_document("HKREG-DEC-STA-001")
    branch = _json_array(_mutable_object(document["facts"])["branches"])[0]
    _mutable_object(branch)["current_product_reconciliation"] = "CONFLICT"
    _refresh_evidence_and_case_fingerprints(document)

    decision = decide_hkex_state_case(hkex_state_decision_case_from_document(document))
    assert decision.outcome is HKEXStateConformanceOutcome.QUARANTINE
    assert decision.branch_decisions[0].state.value == "UNKNOWN"


def test_changed_reference_truth_fails_without_changing_observed_decision() -> None:
    document = _case_document("HKREG-DEC-STA-001")
    expected = _mutable_object(document["expected_decision"])
    expected["outcome"] = "BLOCK"
    expected["reason"] = "OTHER_REQUIRED_GATE_FAILED"
    _refresh_case_fingerprint(document)

    case = hkex_state_decision_case_from_document(document)
    assert decide_hkex_state_case(case).outcome is HKEXStateConformanceOutcome.PASS
    assert run_hkex_state_case(case).conformance_status == "FAIL"


def _case(case_id: str) -> HKEXStateDecisionCase:
    return hkex_state_decision_case_from_document(_case_document(case_id))


def _case_document(case_id: str) -> dict[str, JsonValue]:
    entry = next(
        entry
        for entry in _objects(_document(CATALOGUE_PATH)["entries"])
        if entry["case_id"] == case_id
    )
    return _document(PACKAGE_ROOT / _text(entry["fixture_path"]))


def _refresh_evidence_and_case_fingerprints(document: dict[str, JsonValue]) -> None:
    facts = document["facts"]
    _mutable_object(document["evidence_packet"])["content_fingerprint"] = fingerprint(facts)
    _refresh_case_fingerprint(document)


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
