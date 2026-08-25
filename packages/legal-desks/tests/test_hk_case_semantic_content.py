"""ADR 0063/0064/0068 semantic proposition-content evaluator tests."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKCaseSemanticContentError,
    HKCaseSemanticContentEvaluationRequest,
    HKCaseSemanticContentResolution,
    evaluate_hk_case_semantic_content,
    hk_case_frozen_pair_memberships,
    hk_case_semantic_content_evaluation_request_document,
    hk_case_semantic_content_evaluation_request_from_document,
    hk_case_semantic_content_result_document,
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
        "forbidden_content_codes",
        "forbidden_meaning_codes",
        "mapped_reference_proposition_id",
        "pair_memberships",
        "pair_role",
        "reference_map_id",
        "reference_path",
        "required_content_codes",
        "required_meaning_codes",
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


def _packaged_request(number: int) -> HKCaseSemanticContentEvaluationRequest:
    case_id = f"HKCASE-PROP-SEM-CNT-{number:03d}"
    reference = _json(_PACKAGE_ROOT / f"evaluations/semantic-content/references/{case_id}.json")
    observation = _json(_PACKAGE_ROOT / f"evaluations/semantic-content/observations/{case_id}.json")
    return hk_case_semantic_content_evaluation_request_from_document(
        {
            "schema_id": "asklegal.hk-cases.semantic-content-evaluation-request",
            "schema_version": "1.0.0",
            "rule_id": "HKCASE-PROP-SEM-CONTENT-EVALUATOR-001",
            "evaluator_fingerprint": _fingerprint("semantic-content-evaluator-v1"),
            "reference": reference,
            "observation": observation,
        }
    )


def _result(request: HKCaseSemanticContentEvaluationRequest) -> dict[str, JsonValue]:
    return hk_case_semantic_content_result_document(evaluate_hk_case_semantic_content(request))


def _reasons(result: dict[str, JsonValue]) -> set[str]:
    value = result["reasons"]
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return {item for item in value if isinstance(item, str)}


def test_all_eighteen_frozen_content_cases_are_separated_and_execute() -> None:
    schema_root = _PACKAGE_ROOT / "contracts/schemas"
    case_schema = _json(schema_root / "hk-case-semantic-content-case.schema.json")
    request_schema = _json(schema_root / "hk-case-semantic-content-evaluation-request.schema.json")
    result_schema = _json(schema_root / "hk-case-semantic-content-case-result.schema.json")
    for schema in (case_schema, request_schema, result_schema):
        Draft202012Validator.check_schema(schema)
    case_validator = _validator(case_schema)
    request_validator = _validator(request_schema)
    result_validator = _validator(result_schema)
    candidate_counts = (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1)
    for number, candidate_count in enumerate(candidate_counts, 1):
        case_id = f"HKCASE-PROP-SEM-CNT-{number:03d}"
        case = _json(_PACKAGE_ROOT / f"fixtures/semantic/content/{case_id}.json")
        expected = _json(_PACKAGE_ROOT / f"expected/semantic-content/{case_id}.json")
        request = _packaged_request(number)
        request_document = hk_case_semantic_content_evaluation_request_document(request)
        case_validator.validate(case)
        request_validator.validate(request_document)
        result_validator.validate(expected)
        model_input = _object(case["model_facing_input"])
        assert not _field_names(model_input).intersection(_FORBIDDEN_MODEL_FIELDS)
        assert model_input["hidden_reference_included"] is False
        actual = _result(request)
        assert actual == expected["result"]
        assert actual["outcome"] == "PASS"
        assert actual["expected_candidate_count"] == candidate_count
        assert actual["provider_calls_authorized"] == 0
        assert actual["workflow_admission_created"] is False
        assert actual["search_records_created"] == 0
        assert actual["release_eligible"] is False


def test_content_catalogue_has_exact_ids_cells_and_three_complete_pairs() -> None:
    catalogue = _json(_PACKAGE_ROOT / "catalogues/semantic-content-cases.json")
    entries = _objects(catalogue["entries"])
    case_ids = [f"HKCASE-PROP-SEM-CNT-{number:03d}" for number in range(1, 19)]
    coverage_ids = [f"HKCASE-PROP-COV-SCNT-{number:03d}" for number in range(1, 19)]
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
    assert catalogue["case_count"] == catalogue["coverage_cell_count"] == 18
    assert catalogue["executed_semantic_case_count"] == 36
    assert catalogue["remaining_semantic_case_count"] == 42
    assert catalogue["complete_pair_ids"] == [
        "HKCASE-PROP-PAIR-006",
        "HKCASE-PROP-PAIR-007",
        "HKCASE-PROP-PAIR-008",
    ]
    assert catalogue["pending_cross_checkpoint_pair_ids"] == []


@pytest.mark.parametrize(("positive", "near_miss"), [(2, 8), (9, 14), (18, 17)])
def test_each_content_pair_rejects_the_other_members_observation(
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


def test_equivalent_nonempty_wording_passes_without_preferred_prose_equality() -> None:
    request = _packaged_request(18)
    proposition = replace(
        request.observation.propositions[0],
        derived_statement=(
            "The principal is bound only after reasonable third-party reliance and due inquiry."
        ),
    )
    observation = replace(request.observation, propositions=(proposition,))
    assert _result(replace(request, observation=observation))["outcome"] == "PASS"


def test_missing_later_qualification_fails_meaning_and_content() -> None:
    request = _packaged_request(2)
    proposition = request.observation.propositions[0]
    observation = replace(
        request.observation,
        propositions=(
            replace(
                proposition,
                meaning_codes=("DELAY_BAR",),
                content_codes=("RULE",),
            ),
        ),
    )
    result = _result(replace(request, observation=observation))
    assert result["outcome"] == "FAIL"
    assert {"CONTENT_MISMATCH", "MEANING_MISMATCH"}.issubset(_reasons(result))


def test_optional_narrative_cannot_be_added_to_the_exact_evidence_set() -> None:
    request = _packaged_request(8)
    proposition = request.observation.propositions[0]
    evidence = proposition.evidence_assertions[0]
    observation = replace(
        request.observation,
        propositions=(
            replace(
                proposition,
                evidence_assertions=(replace(evidence, ordered_range_ids=("range_1", "range_2")),),
            ),
        ),
    )
    result = _result(replace(request, observation=observation))
    assert result["outcome"] == "FAIL"
    assert "EVIDENCE_MISMATCH" in _reasons(result)


def test_adopted_quotation_must_preserve_exact_text() -> None:
    request = _packaged_request(9)
    proposition = request.observation.propositions[0]
    quotation = proposition.selected_quotations[0]
    observation = replace(
        request.observation,
        propositions=(
            replace(
                proposition,
                selected_quotations=(replace(quotation, exact_text=f"{quotation.exact_text} "),),
            ),
        ),
    )
    result = _result(replace(request, observation=observation))
    assert result["outcome"] == "FAIL"
    assert "QUOTATION_MISMATCH" in _reasons(result)


def test_defined_term_dependency_must_be_exact() -> None:
    request = _packaged_request(13)
    proposition = request.observation.propositions[0]
    observation = replace(
        request.observation,
        propositions=(replace(proposition, dependency_ids=()),),
    )
    result = _result(replace(request, observation=observation))
    assert result["outcome"] == "FAIL"
    assert "DEPENDENCY_MISMATCH" in _reasons(result)


def test_ambiguity_missing_locator_and_broadening_are_quarantined_without_statement() -> None:
    for number in (15, 16, 17):
        request = _packaged_request(number)
        assert request.observation.disposition.value == "ACCOUNTED_WITH_QUARANTINE"
        assert request.observation.selected_candidate_ids == ()
        assert len(request.observation.propositions) == 1
        proposition = request.observation.propositions[0]
        assert proposition.resolution is HKCaseSemanticContentResolution.QUARANTINED
        assert proposition.derived_statement is None
        result = _result(request)
        assert result["outcome"] == "PASS"
        assert result["quarantined_candidate_count"] == 1


def test_quarantined_candidate_cannot_leak_a_publishable_statement() -> None:
    request = _packaged_request(17)
    proposition = replace(
        request.observation.propositions[0],
        derived_statement="A principal is always bound by an agent's apparent authority.",
    )
    result = _result(
        replace(request, observation=replace(request.observation, propositions=(proposition,)))
    )
    assert result["outcome"] == "FAIL"
    assert "STATEMENT_STATE_MISMATCH" in _reasons(result)


def test_unit_ledger_and_selection_must_match_reference_exactly() -> None:
    request = _packaged_request(6)
    first = request.observation.units[0]
    result = _result(
        replace(
            request,
            observation=replace(
                request.observation,
                units=(
                    replace(first, candidate_ids=("candidate_1",)),
                    *request.observation.units[1:],
                ),
                selected_candidate_ids=(),
            ),
        )
    )
    assert result["outcome"] == "FAIL"
    assert {"SELECTION_MISMATCH", "UNIT_ACCOUNTING_MISMATCH"}.issubset(_reasons(result))


def test_reference_uncertainty_blocks_the_evaluator_instead_of_guessing() -> None:
    request = _packaged_request(15)
    result = _result(
        replace(
            request,
            reference=replace(request.reference, unresolved_reference_ambiguity=True),
        )
    )
    assert result["outcome"] == "EVALUATOR_BLOCKED"
    assert "REFERENCE_BLOCKED" in _reasons(result)


def test_evaluation_leakage_fails_closed() -> None:
    request = _packaged_request(1)
    result = _result(
        replace(
            request,
            observation=replace(request.observation, hidden_reference_received_by_workflow=True),
        )
    )
    assert result["outcome"] == "FAIL"
    assert "EVALUATION_LEAKAGE" in _reasons(result)


def test_request_round_trip_is_exact_and_unknown_fields_fail_closed() -> None:
    document = hk_case_semantic_content_evaluation_request_document(_packaged_request(1))
    decoded = hk_case_semantic_content_evaluation_request_from_document(document)
    assert hk_case_semantic_content_evaluation_request_document(decoded) == document
    document["case_id"] = "answer-bearing"
    with pytest.raises(HKCaseSemanticContentError):
        hk_case_semantic_content_evaluation_request_from_document(document)
