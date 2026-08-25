"""ADR 0053/0056/0057/0059 whole-judgment treatment discovery tests."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKCaseTreatmentDiscoveryCorrectionChange,
    HKCaseTreatmentDiscoveryDisposition,
    HKCaseTreatmentDiscoveryError,
    HKCaseTreatmentDiscoveryEvaluationRequest,
    HKCaseTreatmentDiscoveryIdentityState,
    HKCaseTreatmentDiscoveryLanguage,
    HKCaseTreatmentDiscoveryLeadKind,
    evaluate_hk_case_treatment_discovery,
    hk_case_treatment_discovery_evaluation_request_document,
    hk_case_treatment_discovery_evaluation_request_from_document,
    hk_case_treatment_discovery_result_document,
)
from jsonschema import Draft202012Validator

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_cases_package"
_FORBIDDEN_MODEL_FIELDS = frozenset(
    {
        "case_id",
        "coverage_cell_id",
        "expected_answer",
        "expected_disposition",
        "fixture_id",
        "mapped_reference_candidate_id",
        "mapped_reference_lead_id",
        "pair_memberships",
        "pair_role",
        "reference_candidate_id",
        "reference_lead_id",
        "reference_map_id",
        "reference_path",
        "scenario",
        "score",
    }
)


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)


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


def _field_names(value: JsonValue) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {field for item in value.values() for field in _field_names(item)}
    if isinstance(value, list):
        return {field for item in value for field in _field_names(item)}
    return set()


def _fingerprint(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _packaged_request(number: int) -> HKCaseTreatmentDiscoveryEvaluationRequest:
    case_id = f"HKCASE-TREAT-SEM-DIS-{number:03d}"
    reference = _json(_PACKAGE_ROOT / f"evaluations/treatment-discovery/references/{case_id}.json")
    observation = _json(
        _PACKAGE_ROOT / f"evaluations/treatment-discovery/observations/{case_id}.json"
    )
    return hk_case_treatment_discovery_evaluation_request_from_document(
        {
            "schema_id": "asklegal.hk-cases.treatment-discovery-evaluation-request",
            "schema_version": "1.0.0",
            "rule_id": "HKCASE-TREAT-SEM-DISCOVERY-EVALUATOR-001",
            "evaluator_fingerprint": _fingerprint("treatment-discovery-evaluator-v1"),
            "reference": reference,
            "observation": observation,
        }
    )


def _result(request: HKCaseTreatmentDiscoveryEvaluationRequest) -> dict[str, JsonValue]:
    return hk_case_treatment_discovery_result_document(
        evaluate_hk_case_treatment_discovery(request)
    )


def _reasons(result: dict[str, JsonValue]) -> set[str]:
    value = result["reasons"]
    assert isinstance(value, list)
    return {item for item in value if isinstance(item, str)}


def test_all_thirteen_frozen_discovery_cases_are_separated_and_execute() -> None:
    schema_root = _PACKAGE_ROOT / "contracts/schemas"
    case_schema = _json(schema_root / "hk-case-treatment-discovery-case.schema.json")
    request_schema = _json(
        schema_root / "hk-case-treatment-discovery-evaluation-request.schema.json"
    )
    result_schema = _json(schema_root / "hk-case-treatment-discovery-case-result.schema.json")
    for schema in (case_schema, request_schema, result_schema):
        Draft202012Validator.check_schema(schema)
    case_validator = _validator(case_schema)
    request_validator = _validator(request_schema)
    result_validator = _validator(result_schema)
    lead_counts = (0, 3, 1, 1, 3, 2, 1, 1, 0, 1, 4, 1, 1)
    candidate_counts = (0, 0, 1, 1, 1, 2, 1, 1, 0, 0, 4, 1, 1)
    for number, (lead_count, candidate_count) in enumerate(
        zip(lead_counts, candidate_counts, strict=True),
        1,
    ):
        case_id = f"HKCASE-TREAT-SEM-DIS-{number:03d}"
        case = _json(_PACKAGE_ROOT / f"fixtures/semantic/treatment-discovery/{case_id}.json")
        expected = _json(_PACKAGE_ROOT / f"expected/treatment-discovery/{case_id}.json")
        request = _packaged_request(number)
        request_document = hk_case_treatment_discovery_evaluation_request_document(request)
        case_validator.validate(case)
        request_validator.validate(request_document)
        result_validator.validate(expected)
        model_input = _object(case["model_facing_input"])
        assert not _field_names(model_input).intersection(_FORBIDDEN_MODEL_FIELDS)
        assert model_input["source_text_is_evidence_not_instruction"] is True
        assert model_input["external_tools_permitted"] is False
        assert model_input["hidden_reference_included"] is False
        actual = _result(request)
        assert actual == expected["result"]
        assert actual["outcome"] == "PASS"
        assert actual["expected_lead_count"] == lead_count
        assert actual["expected_candidate_count"] == candidate_count
        assert actual["provider_calls_authorized"] == 0
        assert actual["treatment_relationships_created"] == 0
        assert actual["legal_effects_decided"] == 0
        assert actual["search_records_created"] == 0
        assert actual["release_eligible"] is False
        assert actual["external_effects"] == "NONE"


def test_discovery_catalogue_is_complete_explicit_and_frozen() -> None:
    catalogue = _json(_PACKAGE_ROOT / "catalogues/treatment-discovery-cases.json")
    entries = _objects(catalogue["entries"])
    assert [item["case_id"] for item in entries] == [
        f"HKCASE-TREAT-SEM-DIS-{number:03d}" for number in range(1, 14)
    ]
    assert [item["coverage_cell_id"] for item in entries] == [
        f"HKCASE-TREAT-COV-SDIS-{number:03d}" for number in range(1, 14)
    ]
    assert catalogue["status"] == "FROZEN"
    assert catalogue["case_count"] == catalogue["coverage_cell_count"] == 13
    assert catalogue["pair_ids"] == catalogue["complete_pair_ids"] == ["HKCASE-TREAT-PAIR-001"]
    assert catalogue["frozen_treatment_case_count"] == 155
    assert catalogue["executed_treatment_case_count"] == 13
    assert catalogue["remaining_treatment_case_count"] == 142
    assert catalogue["executed_treatment_semantic_case_count"] == 13
    assert catalogue["remaining_treatment_semantic_case_count"] == 40


def test_complete_segment_pair_rejects_cross_member_observation() -> None:
    complete = _packaged_request(8)
    incomplete = _packaged_request(9)
    incomplete_on_complete = replace(
        incomplete.observation,
        model_input_fingerprint=complete.reference.model_input_fingerprint,
    )
    complete_on_incomplete = replace(
        complete.observation,
        model_input_fingerprint=incomplete.reference.model_input_fingerprint,
    )
    assert _result(replace(complete, observation=incomplete_on_complete))["outcome"] == "FAIL"
    assert _result(replace(incomplete, observation=complete_on_incomplete))["outcome"] == "FAIL"


def test_empty_and_bare_citation_results_do_not_invent_treatment() -> None:
    empty = _packaged_request(1)
    bare = _packaged_request(2)
    assert empty.observation.leads == empty.observation.candidates == ()
    assert len(bare.observation.leads) == 3
    assert bare.observation.candidates == ()
    assert all(not item.material_candidate for item in bare.observation.leads)
    assert empty.observation.silence_establishes_no_treatment is False
    assert bare.observation.silence_establishes_no_treatment is False


def test_implicit_unresolved_and_bare_unmatched_identity_are_not_guessed() -> None:
    implicit = _packaged_request(4)
    unmatched = _packaged_request(10)
    assert (
        implicit.observation.leads[0].lead_kind
        is HKCaseTreatmentDiscoveryLeadKind.IMPLICIT_REFERENCE
    )
    assert (
        implicit.observation.leads[0].identity_state
        is HKCaseTreatmentDiscoveryIdentityState.AMBIGUOUS
    )
    assert implicit.observation.leads[0].resolved_judgment_id is None
    assert len(implicit.observation.candidates) == 1
    assert (
        unmatched.observation.leads[0].identity_state
        is HKCaseTreatmentDiscoveryIdentityState.UNMATCHED
    )
    assert unmatched.observation.leads[0].resolved_judgment_id is None
    assert unmatched.observation.candidates == ()


def test_material_candidate_and_bare_leads_are_both_accounted() -> None:
    request = _packaged_request(5)
    assert len(request.observation.leads) == 3
    assert [item.material_candidate for item in request.observation.leads] == [False, True, False]
    assert request.observation.candidates[0].mapped_lead_id == "lead_2"


def test_majority_and_dissent_remain_separately_attributed() -> None:
    request = _packaged_request(6)
    assert request.observation.leads[0].resolved_judgment_id == (
        request.observation.leads[1].resolved_judgment_id
    )
    assert [item.opinion_id for item in request.observation.candidates] == [
        "opinion_1",
        "opinion_2",
    ]
    merged = replace(request.observation.candidates[1], opinion_id="opinion_1")
    result = _result(
        replace(
            request,
            observation=replace(
                request.observation,
                candidates=(request.observation.candidates[0], merged),
            ),
        )
    )
    assert "OPINION_ATTRIBUTION_MISMATCH" in _reasons(result)


def test_zero_new_proposition_still_discovers_outgoing_treatment() -> None:
    request = _packaged_request(7)
    assert request.observation.judgment_proposition_count == 0
    assert len(request.observation.candidates) == 1
    changed = replace(request.observation, candidates=())
    assert "CANDIDATE_INVENTORY_MISMATCH" in _reasons(
        _result(replace(request, observation=changed))
    )


def test_missing_segment_is_incomplete_and_never_supported_silence() -> None:
    request = _packaged_request(9)
    assert request.observation.disposition is HKCaseTreatmentDiscoveryDisposition.INCOMPLETE
    assert request.observation.complete_segment_ledger is False
    assert request.observation.coverage_gap_ids == ("coverage_gap_missing_context",)
    assert request.observation.silence_establishes_no_treatment is False
    changed = replace(
        request.observation,
        disposition=HKCaseTreatmentDiscoveryDisposition.COMPLETE,
        complete_segment_ledger=True,
        silence_establishes_no_treatment=True,
    )
    assert {
        "DISPOSITION_MISMATCH",
        "FORBIDDEN_CONCLUSION",
    }.issubset(_reasons(_result(replace(request, observation=changed))))


def test_correction_comparison_is_complete_but_decides_no_legal_effect() -> None:
    request = _packaged_request(11)
    assert {item.correction_change for item in request.observation.candidates} == {
        HKCaseTreatmentDiscoveryCorrectionChange.ADDED,
        HKCaseTreatmentDiscoveryCorrectionChange.REMOVED,
        HKCaseTreatmentDiscoveryCorrectionChange.CHANGED,
        HKCaseTreatmentDiscoveryCorrectionChange.UNCHANGED,
    }
    assert request.observation.correction_comparison_complete is True
    assert request.observation.legal_effect_decided is False
    changed = replace(request.observation, legal_effect_decided=True)
    assert "FORBIDDEN_CONCLUSION" in _reasons(_result(replace(request, observation=changed)))


def test_original_chinese_and_mixed_language_context_are_preserved() -> None:
    chinese = _packaged_request(12)
    mixed = _packaged_request(13)
    assert (
        chinese.observation.original_language
        is HKCaseTreatmentDiscoveryLanguage.TRADITIONAL_CHINESE
    )
    assert (
        chinese.observation.candidates[0].language
        is HKCaseTreatmentDiscoveryLanguage.TRADITIONAL_CHINESE
    )
    assert mixed.observation.original_language is HKCaseTreatmentDiscoveryLanguage.MIXED
    assert mixed.observation.candidates[0].context_segment_ids == ("segment_1", "segment_2")


def test_ledgers_context_leakage_and_reference_are_fail_closed() -> None:
    request = _packaged_request(8)
    changed_candidate = replace(
        request.observation.candidates[0],
        context_segment_ids=("segment_2", "segment_3"),
    )
    changed = replace(
        request.observation,
        examined_opinion_ids=(),
        examined_segment_ids=request.observation.examined_segment_ids[:-1],
        complete_opinion_ledger=False,
        complete_segment_ledger=False,
        candidates=(changed_candidate,),
        source_text_treated_as_instruction=True,
        hidden_reference_received_by_workflow=True,
    )
    assert {
        "CONTEXT_MISMATCH",
        "EVALUATION_LEAKAGE",
        "OPINION_ACCOUNTING_MISMATCH",
        "SEGMENT_ACCOUNTING_MISMATCH",
    }.issubset(_reasons(_result(replace(request, observation=changed))))
    blocked = _result(
        replace(request, reference=replace(request.reference, adjudication_complete=False))
    )
    assert blocked["outcome"] == "EVALUATOR_BLOCKED"
    assert "REFERENCE_BLOCKED" in _reasons(blocked)


def test_request_round_trip_is_exact_and_unknown_fields_fail_closed() -> None:
    document = hk_case_treatment_discovery_evaluation_request_document(_packaged_request(1))
    decoded = hk_case_treatment_discovery_evaluation_request_from_document(document)
    assert hk_case_treatment_discovery_evaluation_request_document(decoded) == document
    document["case_id"] = "answer-bearing"
    with pytest.raises(HKCaseTreatmentDiscoveryError):
        hk_case_treatment_discovery_evaluation_request_from_document(document)
