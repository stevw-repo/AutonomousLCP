"""Executable ADR 0074/0075 HKEX canonical-rendering checkpoint tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_RENDERING_DECISION_CASE_COUNT,
    HKEXRenderingDecisionCase,
    HKEXRenderingError,
    HKEXRenderingErrorCode,
    HKEXRenderingIdentityConsequence,
    HKEXRenderingOutcome,
    HKEXRenderingReason,
    HKEXRenderingVectorResponsibility,
    decide_hkex_rendering_case,
    hkex_rendering_decision_case_from_document,
    run_hkex_rendering_case,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)
CATALOGUE_PATH = PACKAGE_ROOT / "catalogues/rendering-decision-cases.json"
CASE_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-rendering-decision-case.schema.json"
REPORT_SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-rendering-decision-report.schema.json"
CATALOGUE_SCHEMA_PATH = (
    PACKAGE_ROOT / "contracts/schemas/hkex-rendering-decision-catalogue.schema.json"
)
ADR_0073_EXPECTED_PATH = PACKAGE_ROOT / "expected/english-record/HKREG-ENGLISH-RECORD-FIX-001.json"


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def test_all_35_cases_validate_execute_and_match_complete_frozen_artifacts() -> None:
    catalogue = _document(CATALOGUE_PATH)
    catalogue_schema = _document(CATALOGUE_SCHEMA_PATH)
    case_schema = _document(CASE_SCHEMA_PATH)
    report_schema = _document(REPORT_SCHEMA_PATH)
    for schema in (catalogue_schema, case_schema, report_schema):
        Draft202012Validator.check_schema(schema)
    _validator(catalogue_schema).validate(catalogue)

    entries = _objects(catalogue["entries"])
    assert len(entries) == HKEX_RENDERING_DECISION_CASE_COUNT == 35
    assert tuple(entry["case_id"] for entry in entries) == tuple(
        f"HKREG-DET-RND-{ordinal:03d}" for ordinal in range(1, 36)
    )
    assert tuple(entry["primary_coverage_cell_id"] for entry in entries) == tuple(
        f"HKREG-COV-DRND-{ordinal:03d}" for ordinal in range(1, 36)
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

        actual = run_hkex_rendering_case(
            hkex_rendering_decision_case_from_document(fixture)
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
        for path in (PACKAGE_ROOT / "fixtures/conformance/rendering-decision").iterdir()
        if path.is_file()
    } == {_text(entry["fixture_path"]) for entry in entries}
    assert {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / "expected/conformance/rendering-decision").iterdir()
        if path.is_file()
    } == {_text(entry["expected_path"]) for entry in entries}
    pair_roles: dict[str, set[str]] = {}
    for entry in entries:
        for membership in _objects(entry["pair_memberships"]):
            pair_roles.setdefault(_text(membership["pair_id"]), set()).add(
                _text(membership["role"])
            )
    expected_pairs = {32, 33, 34, 35, 36, 37, 57}
    assert pair_roles == {
        f"HKREG-PAIR-{ordinal:03d}": {"POSITIVE", "NEAR_MISS"} for ordinal in expected_pairs
    }
    assert catalogue["high_risk_pair_ids"] == [
        f"HKREG-PAIR-{ordinal:03d}" for ordinal in sorted(expected_pairs)
    ]


def test_checkpoint_covers_every_artifact_scope_and_terminal_outcome() -> None:
    entries = _objects(_document(CATALOGUE_PATH)["entries"])
    assert {_text(entry["assertion_scope"]) for entry in entries} == {
        "ORDINARY",
        "TABLE",
        "FEE",
        "FORM",
        "LANGUAGE",
        "UNCERTAINTY",
        "AUTHORITY_NOTE",
    }
    assert {_text(entry["expected_outcome"]) for entry in entries} == {
        "PASS",
        "BLOCK",
        "QUARANTINE",
    }


def test_evaluator_derives_artifact_from_facts_and_scope_not_case_id() -> None:
    case = _case("HKREG-DET-RND-001")
    original = decide_hkex_rendering_case(case)
    renamed = decide_hkex_rendering_case(
        replace(
            case,
            case_id="HKREG-DET-RND-004",
            primary_coverage_cell_id="HKREG-COV-DRND-004",
        )
    )
    assert original == renamed
    assert original.outcome is HKEXRenderingOutcome.PASS
    assert original.reason is HKEXRenderingReason.CANONICAL_RENDERED


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("UNKNOWN_ROOT", HKEXRenderingErrorCode.CONTRACT),
        ("UNKNOWN_SCOPE", HKEXRenderingErrorCode.CONTRACT),
        ("CASE_CELL_MISMATCH", HKEXRenderingErrorCode.IDENTITY),
        ("PAIR_ROLE_MISMATCH", HKEXRenderingErrorCode.IDENTITY),
        ("EVIDENCE_HASH_MISMATCH", HKEXRenderingErrorCode.FINGERPRINT),
        ("TRUTH_LEAKAGE", HKEXRenderingErrorCode.CONTRACT),
        ("STALE_CASE_FINGERPRINT", HKEXRenderingErrorCode.FINGERPRINT),
    ],
)
def test_strict_envelope_rejects_unknown_misbound_or_leaking_documents(
    mutation: str, code: HKEXRenderingErrorCode
) -> None:
    document = _case_document("HKREG-DET-RND-005")
    if mutation == "UNKNOWN_ROOT":
        document["undeclared"] = False
    elif mutation == "UNKNOWN_SCOPE":
        document["assertion_scope"] = "FUTURE_SCOPE"
    elif mutation == "CASE_CELL_MISMATCH":
        document["primary_coverage_cell_ids"] = ["HKREG-COV-DRND-035"]
    elif mutation == "PAIR_ROLE_MISMATCH":
        membership = _json_array(document["pair_memberships"])[0]
        _mutable_object(membership)["role"] = "NEAR_MISS"
    elif mutation == "EVIDENCE_HASH_MISMATCH":
        _mutable_object(document["evidence_packet"])["content_fingerprint"] = f"sha256:{'0' * 64}"
    elif mutation == "TRUTH_LEAKAGE":
        document["evidence_packet_fields"] = ["case_id"]
    elif mutation == "STALE_CASE_FINGERPRINT":
        document["title"] = "changed without a new case fingerprint"

    with pytest.raises(HKEXRenderingError) as failure:
        hkex_rendering_decision_case_from_document(document)
    assert failure.value.code is code


def test_canonical_blocks_are_exact_and_optional_blocks_are_really_omitted() -> None:
    heading = decide_hkex_rendering_case(_case("HKREG-DET-RND-003"))
    no_heading = decide_hkex_rendering_case(_case("HKREG-DET-RND-004"))
    dependency = decide_hkex_rendering_case(_case("HKREG-DET-RND-007"))
    no_reference = decide_hkex_rendering_case(_case("HKREG-DET-RND-010"))
    assert heading.canonical_text is not None
    assert "Official heading: Continuing obligations" in heading.canonical_text
    assert no_heading.canonical_text is not None
    assert "Official heading:" not in no_heading.canonical_text
    assert dependency.canonical_text is not None
    assert "Required governing context:" in dependency.canonical_text
    assert no_reference.canonical_text is not None
    assert "Referenced locations:" not in no_reference.canonical_text


def test_permanent_governing_context_case_matches_the_accepted_adr_0073_renderer() -> None:
    permanent = decide_hkex_rendering_case(_case("HKREG-DET-RND-007"))
    accepted = _document(ADR_0073_EXPECTED_PATH)
    first_case = _json_object(_json_array(accepted["cases"])[0])
    first_result = _json_object(_json_array(first_case["record_results"])[0])
    first_part = _json_object(_json_array(first_result["parts"])[0])
    assert permanent.canonical_text == first_part["text"]
    assert permanent.embedding_input == first_part["text"]


def test_unicode_and_line_endings_normalize_without_changing_source_meaning() -> None:
    decision = decide_hkex_rendering_case(_case("HKREG-DET-RND-012"))
    assert decision.reason is HKEXRenderingReason.CANONICAL_NORMALIZED
    assert decision.canonical_text is not None
    assert "Café rule\nline two" in decision.canonical_text
    assert "\r" not in decision.canonical_text


def test_authority_note_is_required_separate_and_never_embedded_in_text() -> None:
    none = decide_hkex_rendering_case(_case("HKREG-DET-RND-014"))
    warning = decide_hkex_rendering_case(_case("HKREG-DET-RND-015"))
    assert none.authority_note == "None"
    assert warning.authority_note is not None
    assert warning.canonical_text == warning.embedding_input
    assert warning.canonical_text is not None
    authority_note = warning.authority_note
    canonical_text = warning.canonical_text
    assert authority_note is not None
    assert canonical_text is not None
    assert authority_note not in canonical_text
    assert warning.identity_consequence is (HKEXRenderingIdentityConsequence.NEW_RECORD_REQUIRED)


def test_table_projection_rejects_detached_values_and_tracks_material_change() -> None:
    complete = decide_hkex_rendering_case(_case("HKREG-DET-RND-017"))
    detached = decide_hkex_rendering_case(_case("HKREG-DET-RND-018"))
    presentation = decide_hkex_rendering_case(_case("HKREG-DET-RND-020"))
    material = decide_hkex_rendering_case(_case("HKREG-DET-RND-021"))
    assert complete.outcome is HKEXRenderingOutcome.PASS
    assert detached.outcome is HKEXRenderingOutcome.BLOCK
    assert detached.rejected_element_ids == ("header", "unit")
    assert presentation.identity_consequence is (HKEXRenderingIdentityConsequence.PRESERVE_EXISTING)
    assert material.identity_consequence is (HKEXRenderingIdentityConsequence.NEW_RECORD_REQUIRED)


def test_fee_form_and_language_paths_are_complete_and_fail_closed() -> None:
    fee = decide_hkex_rendering_case(_case("HKREG-DET-RND-022"))
    bad_fee = decide_hkex_rendering_case(_case("HKREG-DET-RND-023"))
    form = decide_hkex_rendering_case(_case("HKREG-DET-RND-024"))
    fragmented = decide_hkex_rendering_case(_case("HKREG-DET-RND-028"))
    english = decide_hkex_rendering_case(_case("HKREG-DET-RND-029"))
    chinese = decide_hkex_rendering_case(_case("HKREG-DET-RND-030"))
    assert fee.outcome is HKEXRenderingOutcome.PASS
    assert bad_fee.outcome is HKEXRenderingOutcome.BLOCK
    assert form.vector_responsibility is HKEXRenderingVectorResponsibility.ONE_ENGLISH_TEXT
    assert fragmented.outcome is HKEXRenderingOutcome.BLOCK
    assert english.identity_consequence is HKEXRenderingIdentityConsequence.PRESERVE_EXISTING
    assert chinese.vector_responsibility is HKEXRenderingVectorResponsibility.NONE
    assert chinese.outcome is HKEXRenderingOutcome.BLOCK


def test_ambiguity_names_the_smallest_quarantined_branch() -> None:
    decision = decide_hkex_rendering_case(_case("HKREG-DET-RND-031"))
    assert decision.outcome is HKEXRenderingOutcome.QUARANTINE
    assert decision.quarantined_element_ids == ("ambiguous-branch",)
    assert decision.canonical_text is None


def test_measurement_binds_all_six_fields_and_embedding_input_is_text_only() -> None:
    decision = decide_hkex_rendering_case(_case("HKREG-DET-RND-016"))
    assert decision.text_tokens is not None
    assert decision.metadata_bytes is not None
    assert decision.text_limit == 10_000
    assert decision.metadata_limit == 20_000
    assert decision.fits is True
    assert decision.embedding_input == decision.canonical_text
    authority_note = decision.authority_note
    embedding_input = decision.embedding_input
    assert authority_note is not None
    assert embedding_input is not None
    assert authority_note not in embedding_input


def test_changed_reference_truth_fails_without_changing_observed_artifact() -> None:
    document = _case_document("HKREG-DET-RND-001")
    expected = _mutable_object(document["expected_decision"])
    expected["outcome"] = "BLOCK"
    expected["reason"] = "TABLE_INCOMPLETE"
    _refresh_case_fingerprint(document)

    case = hkex_rendering_decision_case_from_document(document)
    assert decide_hkex_rendering_case(case).outcome is HKEXRenderingOutcome.PASS
    assert run_hkex_rendering_case(case).conformance_status == "FAIL"


def _case(case_id: str) -> HKEXRenderingDecisionCase:
    return hkex_rendering_decision_case_from_document(_case_document(case_id))


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
