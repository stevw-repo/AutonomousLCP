"""ADR 0060-0064 deterministic Hong Kong Case Proposition output tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKCaseCodepointTokenCounter,
    HKCaseOutputError,
    HKCaseOutputOutcome,
    evaluate_hk_case_output,
    hk_case_output_request_document,
    hk_case_output_request_from_document,
    hk_case_output_result_document,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_cases_package"


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def _json(path: Path) -> dict[str, JsonValue]:
    value = checked_json_value(json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(value, dict)
    return value


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _objects(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [_object(item) for item in value]


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _texts(value: JsonValue) -> list[str]:
    assert isinstance(value, list)
    return [_text(item) for item in value]


def _integer(value: JsonValue) -> int:
    assert type(value) is int
    return value


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)


def _case(number: int) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    name = f"HKCASE-PROP-DET-OUT-{number:03d}.json"
    return (
        _json(PACKAGE_ROOT / f"fixtures/deterministic/output/{name}"),
        _json(PACKAGE_ROOT / f"expected/output/{name}"),
    )


def _execute(number: int) -> list[dict[str, JsonValue]]:
    fixture, expected = _case(number)
    fixture_variants = _objects(fixture["variants"])
    expected_variants = _objects(expected["variants"])
    assert [item["variant_id"] for item in fixture_variants] == [
        item["variant_id"] for item in expected_variants
    ]
    results: list[dict[str, JsonValue]] = []
    for fixture_variant, expected_variant in zip(
        fixture_variants,
        expected_variants,
        strict=True,
    ):
        request = hk_case_output_request_from_document(fixture_variant["request"])
        counter = HKCaseCodepointTokenCounter(request.tokenizer_profile_fingerprint)
        result = hk_case_output_result_document(evaluate_hk_case_output(request, counter=counter))
        assert result == expected_variant["result"]
        assert result["search_records_created"] == 0
        assert result["release_eligible"] is False
        assert result["semantic_analysis_authorized"] is False
        assert result["external_effects"] == "NONE"
        results.append(result)
    return results


def test_all_sixteen_frozen_output_cases_validate_and_execute() -> None:
    schema_root = PACKAGE_ROOT / "contracts/schemas"
    case_schema = _json(schema_root / "hk-case-output-case.schema.json")
    result_schema = _json(schema_root / "hk-case-output-case-result.schema.json")
    Draft202012Validator.check_schema(case_schema)
    Draft202012Validator.check_schema(result_schema)
    case_validator = _validator(case_schema)
    result_validator = _validator(result_schema)
    observed: set[str] = set()
    for number in range(1, 17):
        fixture, expected = _case(number)
        case_validator.validate(fixture)
        result_validator.validate(expected)
        observed.update(_text(item["outcome"]) for item in _execute(number))
    assert observed == {
        "BLOCKED",
        "INVALID",
        "QUARANTINED_OVER_LIMIT",
        "VALID_OUTPUT",
        "VALID_ZERO_OUTPUT",
    }


def test_request_round_trip_is_strict_and_rejects_unknown_fields() -> None:
    fixture, _ = _case(11)
    request_document = _object(_objects(fixture["variants"])[0]["request"])
    request = hk_case_output_request_from_document(request_document)
    assert hk_case_output_request_document(request) == request_document
    request_document["unknown"] = True
    with pytest.raises(HKCaseOutputError):
        hk_case_output_request_from_document(request_document)


def test_candidate_inventory_counts_every_final_outcome_and_rejects_loss() -> None:
    complete = _execute(1)[0]
    missing = _execute(2)[0]
    counts = {
        _text(item["outcome"]): _integer(item["count"])
        for item in _objects(complete["candidate_outcome_counts"])
    }
    assert counts == {
        "ACCEPTED": 3,
        "BLOCKED": 1,
        "MERGED": 1,
        "QUARANTINED": 1,
        "REJECTED": 1,
        "SPLIT": 1,
    }
    assert complete["discovered_candidate_count"] == complete["final_candidate_count"] == 8
    assert missing["outcome"] == HKCaseOutputOutcome.INVALID.value
    assert "CANDIDATE_ACCOUNTING_INVALID" in _texts(missing["reasons"])


def test_complete_evidence_roles_pass_and_one_missing_role_invalidates() -> None:
    assert _execute(3)[0]["outcome"] == "VALID_OUTPUT"
    missing = _execute(4)[0]
    assert missing["outcome"] == "INVALID"
    assert "EVIDENCE_ROLE_INCOMPLETE" in _texts(missing["reasons"])


def test_traceability_positive_and_every_orphan_variant_fail() -> None:
    assert _execute(5)[0]["validated_record_count"] == 1
    assert {_text(item["outcome"]) for item in _execute(6)} == {"INVALID"}


def test_exact_quotation_passes_and_every_changed_quote_fails() -> None:
    assert _execute(7)[0]["outcome"] == "VALID_OUTPUT"
    altered = _execute(8)
    assert len(altered) == 3
    assert all(item["outcome"] == "INVALID" for item in altered)
    assert all("QUOTATION_MISMATCH" in _texts(item["reasons"]) for item in altered)


def test_missing_locator_is_invalid_but_unavailable_source_map_is_blocked() -> None:
    missing, unavailable = _execute(9)
    assert missing["outcome"] == "INVALID"
    assert "EVIDENCE_ROLE_OR_RANGE_INVALID" in _texts(missing["reasons"])
    assert unavailable["outcome"] == "BLOCKED"
    assert unavailable["reasons"] == ["SOURCE_MAP_UNAVAILABLE"]
    assert unavailable["validated_record_count"] == 0


def test_mixed_unit_subranges_do_not_duplicate_the_source_unit() -> None:
    result = _execute(10)[0]
    assert result["outcome"] == "VALID_OUTPUT"
    assert result["source_unit_count"] == 1
    assert result["source_range_count"] == 4
    assert result["evidence_link_count"] == 8


def test_canonical_renderer_produces_one_exact_six_field_payload() -> None:
    fixture, _ = _case(11)
    request = _object(_objects(fixture["variants"])[0]["request"])
    record = _objects(request["proposed_records"])[0]
    assert record["country"] == record["jurisdiction"] == "Hong Kong"
    assert record["type"] == "case"
    assert record["source"] == "Hong Kong Judiciary"
    assert "Exact judgment support:" in _text(record["text"])
    assert _text(request["ledger_fingerprint"]) not in _text(record["text"])
    assert _execute(11)[0]["validated_record_count"] == 1


def test_inapplicable_optional_section_is_omitted_without_legal_claim() -> None:
    fixture, _ = _case(12)
    request = _object(_objects(fixture["variants"])[0]["request"])
    text = _text(_objects(request["proposed_records"])[0]["text"])
    assert "Material context:" not in text
    assert "None found" not in text
    assert _execute(12)[0]["outcome"] == "VALID_OUTPUT"


def test_authority_note_remains_separate_from_metadata_text() -> None:
    fixture, _ = _case(13)
    request = _object(_objects(fixture["variants"])[0]["request"])
    record = _objects(request["proposed_records"])[0]
    note = _text(record["authority_note"])
    assert note == "Limited to the synthetic authority state frozen at the cutoff."
    assert note not in _text(record["text"])
    assert _execute(13)[0]["outcome"] == "VALID_OUTPUT"


def test_zero_one_and_many_output_inventories_are_explicit() -> None:
    results = _execute(14)
    assert [
        (item["outcome"], item["proposition_count"], item["validated_record_count"])
        for item in results
    ] == [
        ("VALID_ZERO_OUTPUT", 0, 0),
        ("VALID_OUTPUT", 1, 1),
        ("VALID_OUTPUT", 2, 2),
    ]


def test_indivisible_over_limit_output_quarantines_with_coverage_gap() -> None:
    result = _execute(15)[0]
    assert result["outcome"] == "QUARANTINED_OVER_LIMIT"
    assert result["coverage_gap_ids"] == ["gap_over_limit_1"]
    assert result["validated_record_count"] == 0


def test_exact_limit_variants_preserve_mandatory_text_and_authority_note() -> None:
    fixture, _ = _case(16)
    variants = _objects(fixture["variants"])
    at_request = _object(variants[0]["request"])
    below_request = _object(variants[1]["request"])
    at_record = _objects(at_request["proposed_records"])[0]
    below_record = _objects(below_request["proposed_records"])[0]
    assert at_record["text"] == below_record["text"]
    assert at_record["authority_note"] == below_record["authority_note"]
    results = _execute(16)
    assert [item["outcome"] for item in results] == [
        "VALID_OUTPUT",
        "VALID_OUTPUT",
        "QUARANTINED_OVER_LIMIT",
    ]


def test_output_catalogue_has_exact_ids_cells_pairs_and_paths() -> None:
    catalogue = _json(PACKAGE_ROOT / "catalogues/output-cases.json")
    entries = _objects(catalogue["entries"])
    assert catalogue["case_count"] == catalogue["coverage_cell_count"] == len(entries) == 16
    assert [item["case_id"] for item in entries] == [
        f"HKCASE-PROP-DET-OUT-{number:03d}" for number in range(1, 17)
    ]
    assert [item["coverage_cell_id"] for item in entries] == [
        f"HKCASE-PROP-COV-DOUT-{number:03d}" for number in range(1, 17)
    ]
    pair_members = [
        (membership["pair_id"], membership["role"], entry["case_id"])
        for entry in entries
        for membership in _objects(entry["pair_memberships"])
    ]
    assert pair_members == [
        ("HKCASE-PROP-PAIR-022", "POSITIVE", "HKCASE-PROP-DET-OUT-001"),
        ("HKCASE-PROP-PAIR-022", "NEAR_MISS", "HKCASE-PROP-DET-OUT-002"),
        ("HKCASE-PROP-PAIR-023", "POSITIVE", "HKCASE-PROP-DET-OUT-003"),
        ("HKCASE-PROP-PAIR-023", "NEAR_MISS", "HKCASE-PROP-DET-OUT-004"),
        ("HKCASE-PROP-PAIR-024", "POSITIVE", "HKCASE-PROP-DET-OUT-005"),
        ("HKCASE-PROP-PAIR-024", "NEAR_MISS", "HKCASE-PROP-DET-OUT-006"),
        ("HKCASE-PROP-PAIR-025", "POSITIVE", "HKCASE-PROP-DET-OUT-007"),
        ("HKCASE-PROP-PAIR-025", "NEAR_MISS", "HKCASE-PROP-DET-OUT-008"),
    ]
    assert catalogue["checkpoint_complete"] is True
    assert catalogue["full_proposition_suite_complete"] is False
    assert catalogue["real_source_evidence"] is False
    assert catalogue["activation_authorized"] is False
