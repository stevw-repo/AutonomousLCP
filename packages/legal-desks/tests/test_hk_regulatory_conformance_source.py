"""Executable ADR 0074/0075 HKEX source-decision checkpoint tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_SOURCE_DECISION_CASE_COUNT,
    HKEXSourceDecisionCase,
    HKEXSourceDecisionError,
    HKEXSourceDecisionErrorCode,
    HKEXSourceDecisionOutcome,
    HKEXSourceDecisionReason,
    decide_hkex_source_case,
    hkex_source_decision_case_from_document,
    run_hkex_source_case,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)
CATALOGUE_PATH = PACKAGE_ROOT / "catalogues/source-decision-cases.json"
CASE_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-source-decision-case.schema.json"
REPORT_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-source-decision-report.schema.json"
CATALOGUE_SCHEMA_PATH = (
    PACKAGE_ROOT / "contracts/schemas/hkex-source-decision-catalogue.schema.json"
)


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def test_all_62_cases_validate_execute_and_match_complete_frozen_decisions() -> None:
    catalogue = _document(CATALOGUE_PATH)
    catalogue_schema = _document(CATALOGUE_SCHEMA_PATH)
    case_schema = _document(CASE_SCHEMA_PATH)
    report_schema = _document(REPORT_SCHEMA_PATH)
    for schema in (catalogue_schema, case_schema, report_schema):
        Draft202012Validator.check_schema(schema)
    _validator(catalogue_schema).validate(catalogue)

    entries = _objects(catalogue["entries"])
    assert len(entries) == HKEX_SOURCE_DECISION_CASE_COUNT == 62
    assert tuple(entry["case_id"] for entry in entries) == tuple(
        f"HKREG-DEC-SRC-{ordinal:03d}" for ordinal in range(1, 63)
    )
    assert tuple(entry["primary_coverage_cell_id"] for entry in entries) == tuple(
        f"HKREG-COV-DSRC-{ordinal:03d}" for ordinal in range(1, 63)
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

        actual = run_hkex_source_case(hkex_source_decision_case_from_document(fixture)).document()
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


def test_catalogue_is_exact_and_all_15_high_risk_pairs_are_complete() -> None:
    entries = _objects(_document(CATALOGUE_PATH)["entries"])
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "fixtures/conformance/source-decision").iterdir()
        if path.is_file()
    } == {_text(entry["fixture_path"]) for entry in entries}
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "expected/conformance/source-decision").iterdir()
        if path.is_file()
    } == {_text(entry["expected_path"]) for entry in entries}

    pair_roles: dict[str, set[str]] = {}
    for entry in entries:
        membership = entry["pair_membership"]
        if membership is not None:
            item = _json_object(membership)
            pair_roles.setdefault(_text(item["pair_id"]), set()).add(_text(item["role"]))
    assert pair_roles == {
        f"HKREG-PAIR-{ordinal:03d}": {"POSITIVE", "NEAR_MISS"} for ordinal in range(1, 16)
    }


def test_expected_inventory_covers_critical_source_and_ownership_boundaries() -> None:
    entries = _objects(_document(CATALOGUE_PATH)["entries"])
    observed = {
        _text(entry["case_id"]): (
            _text(entry["expected_outcome"]),
            _text(entry["expected_reason"]),
        )
        for entry in entries
    }
    assert observed["HKREG-DEC-SRC-001"] == ("PASS", "ASSIGNED_FACTS_ACCEPTED")
    assert observed["HKREG-DEC-SRC-012"] == ("BLOCK", "UNIVERSE_INCOMPLETE")
    assert observed["HKREG-DEC-SRC-041"] == ("QUARANTINE", "MEMBERSHIP_UNRESOLVED")
    assert observed["HKREG-DEC-SRC-052"] == ("BLOCK", "DOUBLE_OWNED_INSTANCE")
    assert observed["HKREG-DEC-SRC-055"] == ("BLOCK", "CRITICAL_WRONG_BOARD")
    assert observed["HKREG-DEC-SRC-059"] == (
        "QUARANTINE",
        "CHINESE_ENGLISH_DEFECT_SIGNAL",
    )
    assert observed["HKREG-DEC-SRC-061"] == ("BLOCK", "PROHIBITED_SOURCE_REPAIR")


def test_evaluator_derives_result_from_facts_and_scope_not_case_id() -> None:
    case = _case("HKREG-DEC-SRC-001")
    original = decide_hkex_source_case(case)
    renamed = decide_hkex_source_case(
        replace(
            case,
            case_id="HKREG-DEC-SRC-002",
            primary_coverage_cell_id="HKREG-COV-DSRC-002",
        )
    )
    assert original == renamed
    assert original.outcome is HKEXSourceDecisionOutcome.PASS
    assert original.reason is HKEXSourceDecisionReason.ASSIGNED_FACTS_ACCEPTED


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("UNKNOWN_ROOT", HKEXSourceDecisionErrorCode.CONTRACT),
        ("UNKNOWN_SCOPE", HKEXSourceDecisionErrorCode.CONTRACT),
        ("CASE_CELL_MISMATCH", HKEXSourceDecisionErrorCode.IDENTITY),
        ("PAIR_ROLE_MISMATCH", HKEXSourceDecisionErrorCode.IDENTITY),
        ("EVIDENCE_HASH_MISMATCH", HKEXSourceDecisionErrorCode.CONTRACT),
        ("TRUTH_LEAKAGE", HKEXSourceDecisionErrorCode.CONTRACT),
        ("STALE_CASE_FINGERPRINT", HKEXSourceDecisionErrorCode.FINGERPRINT),
    ],
)
def test_strict_envelope_rejects_unknown_misbound_or_leaking_documents(
    mutation: str,
    code: HKEXSourceDecisionErrorCode,
) -> None:
    document = _case_document("HKREG-DEC-SRC-001")
    if mutation == "UNKNOWN_ROOT":
        document["undeclared"] = False
    elif mutation == "UNKNOWN_SCOPE":
        document["assertion_scope"] = "FUTURE_SCOPE"
    elif mutation == "CASE_CELL_MISMATCH":
        document["primary_coverage_cell_ids"] = ["HKREG-COV-DSRC-062"]
    elif mutation == "PAIR_ROLE_MISMATCH":
        _mutable_object(document["pair_membership"])["role"] = "NEAR_MISS"
    elif mutation == "EVIDENCE_HASH_MISMATCH":
        _mutable_object(document["evidence_packet"])["content_fingerprint"] = f"sha256:{'0' * 64}"
    elif mutation == "TRUTH_LEAKAGE":
        document["evidence_packet_fields"] = ["case_id"]
    elif mutation == "STALE_CASE_FINGERPRINT":
        document["title"] = "changed without a new case fingerprint"

    with pytest.raises(HKEXSourceDecisionError) as failure:
        hkex_source_decision_case_from_document(document)
    assert failure.value.code is code


def test_changed_fact_authority_changes_result_without_changing_identity() -> None:
    document = _case_document("HKREG-DEC-SRC-001")
    facts = _mutable_object(document["facts"])
    facts["claimed_fact_codes"] = ["INDIVIDUAL_RULE_WORDING"]
    _refresh_evidence_and_case_fingerprints(document)

    decision = decide_hkex_source_case(hkex_source_decision_case_from_document(document))
    assert decision.outcome is HKEXSourceDecisionOutcome.BLOCK
    assert decision.reason is HKEXSourceDecisionReason.OUT_OF_ROLE_FACT_REJECTED


def test_due_source_completeness_requires_every_exact_five_role_observation() -> None:
    document = _case_document("HKREG-DEC-SRC-011")
    facts = _mutable_object(document["facts"])
    fresh = _json_array(facts["fresh_source_ids"])
    fresh.pop()
    _refresh_evidence_and_case_fingerprints(document)

    decision = decide_hkex_source_case(hkex_source_decision_case_from_document(document))
    assert decision.outcome is HKEXSourceDecisionOutcome.BLOCK
    assert decision.reason is HKEXSourceDecisionReason.UNIVERSE_INCOMPLETE


def test_changed_reference_truth_fails_without_changing_observed_decision() -> None:
    document = _case_document("HKREG-DEC-SRC-001")
    expected = _mutable_object(document["expected_decision"])
    expected["outcome"] = "BLOCK"
    expected["reason"] = "OUT_OF_ROLE_FACT_REJECTED"
    _refresh_case_fingerprint(document)

    case = hkex_source_decision_case_from_document(document)
    assert decide_hkex_source_case(case).outcome is HKEXSourceDecisionOutcome.PASS
    assert run_hkex_source_case(case).conformance_status == "FAIL"


def _case(case_id: str) -> HKEXSourceDecisionCase:
    return hkex_source_decision_case_from_document(_case_document(case_id))


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
