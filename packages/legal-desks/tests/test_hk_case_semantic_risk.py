"""ADR 0063/0064/0068 semantic court, length, uncertainty, and safety tests."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKCaseSemanticRiskDisposition,
    HKCaseSemanticRiskError,
    HKCaseSemanticRiskEvaluationRequest,
    HKCaseSemanticRiskResolution,
    HKCaseSemanticRiskTranslationUse,
    evaluate_hk_case_semantic_risk,
    hk_case_frozen_pair_memberships,
    hk_case_semantic_risk_evaluation_request_document,
    hk_case_semantic_risk_evaluation_request_from_document,
    hk_case_semantic_risk_result_document,
)
from jsonschema import Draft202012Validator

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_cases_package"
_FORBIDDEN_MODEL_FIELDS = frozenset(
    {
        "case_id",
        "coverage_cell_id",
        "critical_error_tag",
        "expected_answer",
        "expected_disposition",
        "expected_resolution",
        "fixture_id",
        "forbidden_risk_codes",
        "mapped_reference_proposition_id",
        "pair_memberships",
        "pair_role",
        "reference_map_id",
        "reference_path",
        "required_meaning_codes",
        "required_risk_codes",
        "risk_codes",
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


def _packaged_request(number: int) -> HKCaseSemanticRiskEvaluationRequest:
    case_id = f"HKCASE-PROP-SEM-RSK-{number:03d}"
    reference = _json(_PACKAGE_ROOT / f"evaluations/semantic-risk/references/{case_id}.json")
    observation = _json(_PACKAGE_ROOT / f"evaluations/semantic-risk/observations/{case_id}.json")
    return hk_case_semantic_risk_evaluation_request_from_document(
        {
            "schema_id": "asklegal.hk-cases.semantic-risk-evaluation-request",
            "schema_version": "1.0.0",
            "rule_id": "HKCASE-PROP-SEM-RISK-EVALUATOR-001",
            "evaluator_fingerprint": _fingerprint("semantic-risk-evaluator-v1"),
            "reference": reference,
            "observation": observation,
        }
    )


def _result(request: HKCaseSemanticRiskEvaluationRequest) -> dict[str, JsonValue]:
    return hk_case_semantic_risk_result_document(evaluate_hk_case_semantic_risk(request))


def _reasons(result: dict[str, JsonValue]) -> set[str]:
    value = result["reasons"]
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return {item for item in value if isinstance(item, str)}


def test_all_twenty_frozen_risk_cases_are_separated_and_execute() -> None:
    schema_root = _PACKAGE_ROOT / "contracts/schemas"
    case_schema = _json(schema_root / "hk-case-semantic-risk-case.schema.json")
    request_schema = _json(schema_root / "hk-case-semantic-risk-evaluation-request.schema.json")
    result_schema = _json(schema_root / "hk-case-semantic-risk-case-result.schema.json")
    for schema in (case_schema, request_schema, result_schema):
        Draft202012Validator.check_schema(schema)
    case_validator = _validator(case_schema)
    request_validator = _validator(request_schema)
    result_validator = _validator(result_schema)
    candidate_counts = (1, 1, 1, 1, 1, 2, 1, 1, 1, 2, 0, 1, 1, 1, 2, 1, 1, 0, 1, 1)
    for number, candidate_count in enumerate(candidate_counts, 1):
        case_id = f"HKCASE-PROP-SEM-RSK-{number:03d}"
        case = _json(_PACKAGE_ROOT / f"fixtures/semantic/risk/{case_id}.json")
        expected = _json(_PACKAGE_ROOT / f"expected/semantic-risk/{case_id}.json")
        request = _packaged_request(number)
        request_document = hk_case_semantic_risk_evaluation_request_document(request)
        case_validator.validate(case)
        request_validator.validate(request_document)
        result_validator.validate(expected)
        model_input = _object(case["model_facing_input"])
        assert not _field_names(model_input).intersection(_FORBIDDEN_MODEL_FIELDS)
        assert model_input["hidden_reference_included"] is False
        assert model_input["source_text_is_evidence_not_instruction"] is True
        actual = _result(request)
        assert actual == expected["result"]
        assert actual["outcome"] == "PASS"
        assert actual["expected_candidate_count"] == candidate_count
        assert actual["provider_calls_authorized"] == 0
        assert actual["workflow_admission_created"] is False
        assert actual["search_records_created"] == 0
        assert actual["release_eligible"] is False
        assert actual["external_effects"] == "NONE"


def test_risk_catalogue_completes_all_semantic_cases_and_pairs() -> None:
    catalogue = _json(_PACKAGE_ROOT / "catalogues/semantic-risk-cases.json")
    entries = _objects(catalogue["entries"])
    case_ids = [f"HKCASE-PROP-SEM-RSK-{number:03d}" for number in range(1, 21)]
    coverage_ids = [f"HKCASE-PROP-COV-SRSK-{number:03d}" for number in range(1, 21)]
    assert [item["case_id"] for item in entries] == case_ids
    assert [item["coverage_cell_id"] for item in entries] == coverage_ids
    expected_memberships = [
        {"pair_id": item.pair_id, "role": item.role}
        for item in hk_case_frozen_pair_memberships()
        if item.case_id in case_ids
    ]
    observed_memberships = [
        pair for entry in entries for pair in _objects(entry["pair_memberships"])
    ]
    assert sorted((item["pair_id"], item["role"]) for item in observed_memberships) == sorted(
        (item["pair_id"], item["role"]) for item in expected_memberships
    )
    assert catalogue["case_count"] == catalogue["coverage_cell_count"] == 20
    assert catalogue["frozen_semantic_case_count"] == 78
    assert catalogue["executed_semantic_case_count"] == 78
    assert catalogue["remaining_semantic_case_count"] == 0
    assert catalogue["complete_pair_ids"] == [
        f"HKCASE-PROP-PAIR-{number:03d}" for number in range(16, 20)
    ]
    assert catalogue["completed_cross_checkpoint_pair_ids"] == ["HKCASE-PROP-PAIR-019"]
    assert catalogue["pending_cross_checkpoint_pair_ids"] == []


@pytest.mark.parametrize(("positive", "near_miss"), [(10, 11), (15, 14), (1, 7)])
def test_each_within_checkpoint_risk_pair_rejects_cross_member_observation(
    positive: int,
    near_miss: int,
) -> None:
    positive_request = _packaged_request(positive)
    near_miss_request = _packaged_request(near_miss)
    near_on_positive = replace(
        near_miss_request.observation,
        model_input_fingerprint=positive_request.reference.model_input_fingerprint,
    )
    positive_on_near = replace(
        positive_request.observation,
        model_input_fingerprint=near_miss_request.reference.model_input_fingerprint,
    )
    assert _result(replace(positive_request, observation=near_on_positive))["outcome"] == "FAIL"
    assert _result(replace(near_miss_request, observation=positive_on_near))["outcome"] == "FAIL"


def test_original_language_authority_is_not_replaced_by_translation() -> None:
    original = _packaged_request(1)
    translated = _packaged_request(7)
    assert original.observation.translation_use is HKCaseSemanticRiskTranslationUse.NONE
    assert translated.observation.translation_use is HKCaseSemanticRiskTranslationUse.AUXILIARY_ONLY
    assert translated.observation.candidates[0].source_version_id == (
        translated.observation.accepted_original_version_id
    )
    changed = replace(
        translated.observation.candidates[0],
        source_version_id=translated.observation.auxiliary_translation_version_ids[0],
    )
    result = _result(
        replace(
            translated,
            observation=replace(translated.observation, candidates=(changed,)),
        )
    )
    assert "ORIGINAL_AUTHORITY_MISMATCH" in _reasons(result)


def test_missing_segment_is_blocked_not_complete_or_false_zero() -> None:
    request = _packaged_request(11)
    assert request.observation.disposition is HKCaseSemanticRiskDisposition.BLOCKED
    assert request.observation.candidates == ()
    assert request.observation.coverage_gap_ids == ("coverage_gap_missing_segment",)
    assert _result(request)["outcome"] == "PASS"
    changed = replace(
        request.observation,
        disposition=HKCaseSemanticRiskDisposition.COMPLETE_WITH_PROPOSITIONS,
    )
    assert "DISPOSITION_MISMATCH" in _reasons(_result(replace(request, observation=changed)))


def test_indivisible_overlimit_candidate_is_quarantined_but_real_split_passes() -> None:
    indivisible = _packaged_request(14)
    split = _packaged_request(15)
    assert (
        indivisible.observation.disposition
        is HKCaseSemanticRiskDisposition.ACCOUNTED_WITH_QUARANTINE
    )
    assert (
        indivisible.observation.candidates[0].resolution is HKCaseSemanticRiskResolution.QUARANTINED
    )
    assert indivisible.observation.candidates[0].derived_statement is None
    assert len(split.observation.candidates) == 2
    assert all(
        item.resolution is HKCaseSemanticRiskResolution.ACCEPTED
        for item in split.observation.candidates
    )
    assert _result(indivisible)["outcome"] == _result(split)["outcome"] == "PASS"


def test_unresolved_materiality_completes_pair_019_without_becoming_no_proposition() -> None:
    materiality_expected = _json(
        _PACKAGE_ROOT / "expected/semantic-materiality/HKCASE-PROP-SEM-MAT-017.json"
    )
    uncertain = _packaged_request(16)
    materiality_result = _object(materiality_expected["result"])
    assert materiality_result["outcome"] == "PASS"
    assert materiality_result["required_proposition_count"] == 0
    assert (
        uncertain.observation.disposition is HKCaseSemanticRiskDisposition.ACCOUNTED_WITH_QUARANTINE
    )
    assert len(uncertain.observation.candidates) == 1
    assert (
        uncertain.observation.candidates[0].resolution is HKCaseSemanticRiskResolution.QUARANTINED
    )
    assert _result(uncertain)["outcome"] == "PASS"


def test_unsupported_parser_structure_blocks_supported_looking_text() -> None:
    request = _packaged_request(18)
    assert request.observation.parser_supported is False
    assert request.observation.disposition is HKCaseSemanticRiskDisposition.BLOCKED
    assert request.observation.candidates == ()
    changed = replace(request.observation, parser_supported=True)
    result = _result(replace(request, observation=changed))
    assert "PARSER_SUPPORT_MISMATCH" in _reasons(result)


def test_hostile_quoted_instructions_remain_source_evidence() -> None:
    request = _packaged_request(19)
    assert _result(request)["outcome"] == "PASS"
    changed = replace(request.observation, source_text_treated_as_instruction=True)
    result = _result(replace(request, observation=changed))
    assert "EVALUATION_LEAKAGE" in _reasons(result)


def test_corrected_reasons_require_affected_re_evaluation_and_immutable_prior() -> None:
    request = _packaged_request(20)
    assert request.observation.re_evaluated_candidate_ids == ("candidate_1",)
    assert request.observation.prior_result_immutable is True
    changed = replace(
        request.observation,
        re_evaluated_candidate_ids=(),
        prior_result_immutable=False,
    )
    result = _result(replace(request, observation=changed))
    assert "CORRECTION_MISMATCH" in _reasons(result)


def test_segments_dependencies_ledger_selection_and_reference_are_fail_closed() -> None:
    request = _packaged_request(10)
    changed = replace(
        request.observation,
        examined_segment_ids=request.observation.examined_segment_ids[:-1],
        resolved_dependency_ids=(),
        selected_candidate_ids=(),
        complete_ledger=False,
    )
    result = _result(replace(request, observation=changed))
    assert {
        "DEPENDENCY_MISMATCH",
        "LEDGER_INCOMPLETE",
        "SEGMENT_ACCOUNTING_MISMATCH",
        "SELECTION_MISMATCH",
    }.issubset(_reasons(result))
    blocked = _result(
        replace(request, reference=replace(request.reference, unresolved_reference_ambiguity=True))
    )
    assert blocked["outcome"] == "EVALUATOR_BLOCKED"
    assert "REFERENCE_BLOCKED" in _reasons(blocked)


def test_request_round_trip_is_exact_and_unknown_fields_fail_closed() -> None:
    document = hk_case_semantic_risk_evaluation_request_document(_packaged_request(1))
    decoded = hk_case_semantic_risk_evaluation_request_from_document(document)
    assert hk_case_semantic_risk_evaluation_request_document(decoded) == document
    document["case_id"] = "answer-bearing"
    with pytest.raises(HKCaseSemanticRiskError):
        hk_case_semantic_risk_evaluation_request_from_document(document)
