"""Executable ADR 0074/0075 HKEX package-integrity checkpoint tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_PACKAGE_INTEGRITY_CASE_COUNT,
    HKEXPackageIntegrityCase,
    HKEXPackageIntegrityError,
    HKEXPackageIntegrityErrorCode,
    HKEXPackageIntegrityOutcome,
    HKEXPackageIntegrityReason,
    evaluate_hkex_package_integrity,
    hkex_package_integrity_case_from_document,
    run_hkex_package_integrity_case,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)
CATALOGUE_PATH = PACKAGE_ROOT / "catalogues/package-integrity-cases.json"
CASE_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-package-integrity-case.schema.json"
REPORT_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-package-integrity-report.schema.json"
CATALOGUE_SCHEMA_PATH = (
    PACKAGE_ROOT / "contracts/schemas/hkex-package-integrity-catalogue.schema.json"
)


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def test_all_38_declared_cases_validate_execute_and_match_frozen_reports() -> None:
    catalogue = _document(CATALOGUE_PATH)
    catalogue_schema = _document(CATALOGUE_SCHEMA_PATH)
    case_schema = _document(CASE_SCHEMA_PATH)
    report_schema = _document(REPORT_SCHEMA_PATH)
    for schema in (catalogue_schema, case_schema, report_schema):
        Draft202012Validator.check_schema(schema)
    _validator(catalogue_schema).validate(catalogue)

    entries = _objects(catalogue["entries"])
    assert len(entries) == HKEX_PACKAGE_INTEGRITY_CASE_COUNT == 38
    assert tuple(entry["case_id"] for entry in entries) == tuple(
        f"HKREG-DET-PKG-{ordinal:03d}" for ordinal in range(1, 39)
    )
    assert tuple(entry["primary_coverage_cell_id"] for entry in entries) == tuple(
        f"HKREG-COV-DPKG-{ordinal:03d}" for ordinal in range(1, 39)
    )

    for entry in entries:
        fixture_path = PACKAGE_ROOT / _text(entry["fixture_path"])
        expected_path = PACKAGE_ROOT / _text(entry["expected_path"])
        fixture_raw = fixture_path.read_bytes()
        expected_raw = expected_path.read_bytes()
        assert _raw_fingerprint(fixture_raw) == entry["fixture_fingerprint"]
        assert _raw_fingerprint(expected_raw) == entry["expected_fingerprint"]
        fixture = _json_object(parse_json_bytes(fixture_raw, max_bytes=2_000_000))
        expected = _json_object(parse_json_bytes(expected_raw, max_bytes=100_000))
        _validator(case_schema).validate(fixture)
        _validator(report_schema).validate(expected)

        case = hkex_package_integrity_case_from_document(fixture)
        actual = run_hkex_package_integrity_case(case).document()
        assert actual == expected
        assert actual["conformance_status"] == "PASS"
        assert actual["source_authorized"] is False
        assert actual["provider_authorized"] is False
        assert actual["release_authorized"] is False
        assert actual["serving_authorized"] is False
        assert actual["deployment_authorized"] is False
        assert actual["external_effects"] == "NONE"


def test_catalogue_is_the_exact_inventory_and_all_seven_pairs_are_complete() -> None:
    catalogue = _document(CATALOGUE_PATH)
    entries = _objects(catalogue["entries"])
    fixture_paths = {_text(entry["fixture_path"]) for entry in entries}
    expected_paths = {_text(entry["expected_path"]) for entry in entries}
    actual_fixtures = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "fixtures/conformance/package-integrity").iterdir()
        if path.is_file()
    }
    actual_expected = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "expected/conformance/package-integrity").iterdir()
        if path.is_file()
    }
    assert actual_fixtures == fixture_paths
    assert actual_expected == expected_paths

    pair_roles: dict[str, set[str]] = {}
    for entry in entries:
        membership = entry["pair_membership"]
        if membership is None:
            continue
        item = _json_object(membership)
        pair_roles.setdefault(_text(item["pair_id"]), set()).add(_text(item["role"]))
    assert pair_roles == {
        f"HKREG-PAIR-{ordinal:03d}": {"POSITIVE", "NEAR_MISS"} for ordinal in range(50, 57)
    }


def test_expected_branch_inventory_covers_positive_and_negative_semantics() -> None:
    entries = _objects(_document(CATALOGUE_PATH)["entries"])
    observed = {
        _text(entry["case_id"]): (
            _text(entry["expected_outcome"]),
            _text(entry["expected_reason"]),
        )
        for entry in entries
    }
    assert observed["HKREG-DET-PKG-001"] == ("ACCEPTED", "PACKAGE_VALID")
    assert observed["HKREG-DET-PKG-003"] == ("REJECTED", "ARTIFACT_HASH_MISMATCH")
    assert observed["HKREG-DET-PKG-013"] == (
        "ACCEPTED",
        "DELIBERATE_ABSENCE_ADMITTED",
    )
    assert observed["HKREG-DET-PKG-014"] == ("REJECTED", "INPUT_AVAILABLE_INVALID")
    assert observed["HKREG-DET-PKG-029"] == ("ACCEPTED", "REPRODUCIBLE")
    assert observed["HKREG-DET-PKG-030"] == (
        "REJECTED",
        "REPRODUCIBILITY_FAILURE",
    )
    assert observed["HKREG-DET-PKG-035"] == ("ACCEPTED", "PACKAGE_VALIDITY_ONLY")
    assert observed["HKREG-DET-PKG-036"] == (
        "ACCEPTED",
        "BUILD_COMPATIBILITY_ONLY",
    )


def test_evaluator_derives_results_from_facts_not_case_id() -> None:
    case = _case("HKREG-DET-PKG-003")
    original = evaluate_hkex_package_integrity(case)
    renamed = evaluate_hkex_package_integrity(
        replace(
            case,
            case_id="HKREG-DET-PKG-038",
            primary_coverage_cell_id="HKREG-COV-DPKG-038",
        )
    )
    assert original == renamed
    assert original.outcome is HKEXPackageIntegrityOutcome.REJECTED
    assert original.reason is HKEXPackageIntegrityReason.ARTIFACT_HASH_MISMATCH


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("UNKNOWN_ROOT", HKEXPackageIntegrityErrorCode.CONTRACT),
        ("UNKNOWN_SCOPE", HKEXPackageIntegrityErrorCode.CONTRACT),
        ("CASE_CELL_MISMATCH", HKEXPackageIntegrityErrorCode.IDENTITY),
        ("PAIR_ROLE_MISMATCH", HKEXPackageIntegrityErrorCode.IDENTITY),
        ("STALE_CASE_FINGERPRINT", HKEXPackageIntegrityErrorCode.FINGERPRINT),
    ],
)
def test_strict_envelope_rejects_unknown_misbound_or_stale_documents(
    mutation: str,
    code: HKEXPackageIntegrityErrorCode,
) -> None:
    case_id = "HKREG-DET-PKG-011" if mutation == "PAIR_ROLE_MISMATCH" else "HKREG-DET-PKG-001"
    document = _case_document(case_id)
    if mutation == "UNKNOWN_ROOT":
        document["undeclared"] = False
    elif mutation == "UNKNOWN_SCOPE":
        document["assertion_scope"] = "FUTURE_SCOPE"
    elif mutation == "CASE_CELL_MISMATCH":
        document["primary_coverage_cell_ids"] = ["HKREG-COV-DPKG-038"]
    elif mutation == "PAIR_ROLE_MISMATCH":
        membership = _mutable_object(document["pair_membership"])
        membership["role"] = "NEAR_MISS"
    elif mutation == "STALE_CASE_FINGERPRINT":
        document["title"] = "changed without a new case fingerprint"

    with pytest.raises(HKEXPackageIntegrityError) as failure:
        hkex_package_integrity_case_from_document(document)
    assert failure.value.code is code


def test_changed_facts_change_result_even_when_case_identity_is_unchanged() -> None:
    document = _case_document("HKREG-DET-PKG-001")
    facts = _mutable_object(document["facts"])
    facts["attempted_capabilities"] = ["SOURCE"]
    _refresh_case_fingerprint(document)

    decision = evaluate_hkex_package_integrity(hkex_package_integrity_case_from_document(document))
    assert decision.outcome is HKEXPackageIntegrityOutcome.REJECTED
    assert decision.reason is HKEXPackageIntegrityReason.FORBIDDEN_CAPABILITY_ATTEMPT


def test_changed_expected_truth_fails_conformance_without_changing_observed_result() -> None:
    document = _case_document("HKREG-DET-PKG-001")
    document["expected_outcome"] = "REJECTED"
    document["expected_reason"] = "CLOSED_SCHEMA_VIOLATION"
    _refresh_case_fingerprint(document)

    case = hkex_package_integrity_case_from_document(document)
    decision = evaluate_hkex_package_integrity(case)
    report = run_hkex_package_integrity_case(case)
    assert decision.outcome is HKEXPackageIntegrityOutcome.ACCEPTED
    assert decision.reason is HKEXPackageIntegrityReason.PACKAGE_VALID
    assert report.conformance_status == "FAIL"


def _case(case_id: str) -> HKEXPackageIntegrityCase:
    return hkex_package_integrity_case_from_document(_case_document(case_id))


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
    assert isinstance(value, list)
    return tuple(_json_object(item) for item in value)


def _json_object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    assert isinstance(checked, dict)
    return checked


def _mutable_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _raw_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)
