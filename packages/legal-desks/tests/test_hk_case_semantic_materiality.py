"""ADR 0063/0064/0068 semantic materiality evaluator tests."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKCaseSemanticMaterialityAuthorityRole,
    HKCaseSemanticMaterialityDisposition,
    HKCaseSemanticMaterialityError,
    HKCaseSemanticMaterialityEvaluationRequest,
    HKCaseSemanticMaterialityObservation,
    HKCaseSemanticMaterialityObservedProposition,
    HKCaseSemanticMaterialityReference,
    HKCaseSemanticMaterialityReferenceProposition,
    HKCaseSemanticMaterialityUnitObservation,
    HKCaseSemanticMaterialityUnitUse,
    evaluate_hk_case_semantic_materiality,
    hk_case_frozen_pair_memberships,
    hk_case_semantic_materiality_evaluation_request_document,
    hk_case_semantic_materiality_evaluation_request_from_document,
    hk_case_semantic_materiality_result_document,
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
        "fixture_id",
        "mapped_reference_proposition_id",
        "pair_memberships",
        "pair_role",
        "reference_map_id",
        "reference_path",
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


def _request() -> HKCaseSemanticMaterialityEvaluationRequest:
    reference = HKCaseSemanticMaterialityReference(
        reference_map_id="reference_map_1",
        model_input_fingerprint=_fingerprint("model-input"),
        coverage_unit_ids=("unit_1", "unit_2"),
        propositions=(
            HKCaseSemanticMaterialityReferenceProposition(
                reference_proposition_id="reference_prop_1",
                authority_role=HKCaseSemanticMaterialityAuthorityRole.OPERATIVE,
                required_meaning_codes=("LEGAL_TEST", "MATERIAL_APPLICATION"),
                forbidden_meaning_codes=("UNADOPTED_SUBMISSION",),
                required_evidence_role_codes=(
                    "ANSWER",
                    "APPLICATION",
                    "ATTRIBUTION",
                    "ISSUE",
                    "RESULT",
                ),
                required_range_ids=("range_1", "range_2"),
            ),
        ),
        expected_disposition=HKCaseSemanticMaterialityDisposition.COMPLETE_WITH_PROPOSITIONS,
        required_handoff_ids=(),
        expected_selected_reference_proposition_ids=("reference_prop_1",),
        adjudication_complete=True,
        unresolved_reference_ambiguity=False,
    )
    observation = HKCaseSemanticMaterialityObservation(
        model_input_fingerprint=reference.model_input_fingerprint,
        workflow_result_fingerprint=_fingerprint("workflow-result"),
        propositions=(
            HKCaseSemanticMaterialityObservedProposition(
                candidate_id="candidate_1",
                mapped_reference_proposition_id="reference_prop_1",
                authority_role=HKCaseSemanticMaterialityAuthorityRole.OPERATIVE,
                meaning_codes=("LEGAL_TEST", "MATERIAL_APPLICATION"),
                evidence_role_codes=(
                    "ANSWER",
                    "APPLICATION",
                    "ATTRIBUTION",
                    "ISSUE",
                    "RESULT",
                ),
                range_ids=("range_1", "range_2"),
            ),
        ),
        unit_observations=(
            HKCaseSemanticMaterialityUnitObservation(
                unit_id="unit_1",
                use=HKCaseSemanticMaterialityUnitUse.PROPOSITION_EVIDENCE,
                candidate_ids=("candidate_1",),
                handoff_ids=(),
            ),
            HKCaseSemanticMaterialityUnitObservation(
                unit_id="unit_2",
                use=HKCaseSemanticMaterialityUnitUse.PROPOSITION_EVIDENCE,
                candidate_ids=("candidate_1",),
                handoff_ids=(),
            ),
        ),
        disposition=HKCaseSemanticMaterialityDisposition.COMPLETE_WITH_PROPOSITIONS,
        handoff_ids=(),
        selected_candidate_ids=("candidate_1",),
        complete_ledger=True,
        source_text_treated_as_instruction=False,
        hidden_reference_received_by_workflow=False,
    )
    return HKCaseSemanticMaterialityEvaluationRequest(
        evaluator_fingerprint=_fingerprint("evaluator"),
        reference=reference,
        observation=observation,
    )


def _packaged_request(number: int) -> HKCaseSemanticMaterialityEvaluationRequest:
    case_id = f"HKCASE-PROP-SEM-MAT-{number:03d}"
    reference = _json(_PACKAGE_ROOT / f"evaluations/semantic-materiality/references/{case_id}.json")
    observation = _json(
        _PACKAGE_ROOT / f"evaluations/semantic-materiality/observations/{case_id}.json"
    )
    return hk_case_semantic_materiality_evaluation_request_from_document(
        {
            "schema_id": "asklegal.hk-cases.semantic-materiality-evaluation-request",
            "schema_version": "1.0.0",
            "rule_id": "HKCASE-PROP-SEM-MATERIALITY-EVALUATOR-001",
            "evaluator_fingerprint": _fingerprint("semantic-materiality-evaluator-v1"),
            "reference": reference,
            "observation": observation,
        }
    )


def _result(request: HKCaseSemanticMaterialityEvaluationRequest) -> dict[str, JsonValue]:
    return hk_case_semantic_materiality_result_document(
        evaluate_hk_case_semantic_materiality(request)
    )


def _reasons(result: dict[str, JsonValue]) -> set[str]:
    value = result["reasons"]
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return {item for item in value if isinstance(item, str)}


def test_exact_reference_match_passes_without_any_downstream_authority() -> None:
    result = _result(_request())
    assert result["outcome"] == "PASS"
    assert result["reasons"] == ["PASS"]
    assert result["required_proposition_count"] == 1
    assert result["matched_proposition_count"] == 1
    assert result["provider_calls_authorized"] == 0
    assert result["workflow_admission_created"] is False
    assert result["search_records_created"] == 0
    assert result["release_eligible"] is False
    assert result["external_effects"] == "NONE"


def test_all_eighteen_frozen_materiality_cases_are_separated_and_execute() -> None:
    schema_root = _PACKAGE_ROOT / "contracts/schemas"
    case_schema = _json(schema_root / "hk-case-semantic-materiality-case.schema.json")
    request_schema = _json(
        schema_root / "hk-case-semantic-materiality-evaluation-request.schema.json"
    )
    result_schema = _json(schema_root / "hk-case-semantic-materiality-case-result.schema.json")
    for schema in (case_schema, request_schema, result_schema):
        Draft202012Validator.check_schema(schema)
    case_validator = _validator(case_schema)
    request_validator = _validator(request_schema)
    result_validator = _validator(result_schema)
    proposition_counts = (1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 3, 0, 1, 0, 2)
    for number, proposition_count in enumerate(proposition_counts, 1):
        case_id = f"HKCASE-PROP-SEM-MAT-{number:03d}"
        case = _json(_PACKAGE_ROOT / f"fixtures/semantic/materiality/{case_id}.json")
        expected = _json(_PACKAGE_ROOT / f"expected/semantic-materiality/{case_id}.json")
        request = _packaged_request(number)
        request_document = hk_case_semantic_materiality_evaluation_request_document(request)
        case_validator.validate(case)
        request_validator.validate(request_document)
        result_validator.validate(expected)
        model_input = _object(case["model_facing_input"])
        assert not _field_names(model_input).intersection(_FORBIDDEN_MODEL_FIELDS)
        assert model_input["hidden_reference_included"] is False
        actual = hk_case_semantic_materiality_result_document(
            evaluate_hk_case_semantic_materiality(request)
        )
        assert actual == expected["result"]
        assert actual["outcome"] == "PASS"
        assert actual["required_proposition_count"] == proposition_count
        assert actual["provider_calls_authorized"] == 0
        assert actual["workflow_admission_created"] is False


def test_materiality_catalogue_has_exact_ids_cells_and_pair_roles() -> None:
    catalogue = _json(_PACKAGE_ROOT / "catalogues/semantic-materiality-cases.json")
    entries = _objects(catalogue["entries"])
    case_ids = [f"HKCASE-PROP-SEM-MAT-{number:03d}" for number in range(1, 19)]
    coverage_ids = [f"HKCASE-PROP-COV-SMAT-{number:03d}" for number in range(1, 19)]
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
    assert catalogue["executed_semantic_case_count"] == 18
    assert catalogue["remaining_semantic_case_count"] == 60
    assert catalogue["complete_pair_ids"] == [
        f"HKCASE-PROP-PAIR-{number:03d}" for number in range(1, 6)
    ] + ["HKCASE-PROP-PAIR-031", "HKCASE-PROP-PAIR-019"]
    assert catalogue["completed_cross_checkpoint_pair_ids"] == ["HKCASE-PROP-PAIR-019"]
    assert catalogue["pending_cross_checkpoint_pair_ids"] == []


@pytest.mark.parametrize(
    ("positive", "near_miss"),
    [(1, 13), (2, 3), (4, 5), (6, 7), (12, 13), (1, 15)],
)
def test_each_complete_materiality_pair_rejects_the_other_members_observation(
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
    positive_result = _result(replace(positive_request, observation=near_on_positive))
    near_miss_result = _result(replace(near_miss_request, observation=positive_on_near))
    assert positive_result["outcome"] == "FAIL"
    assert near_miss_result["outcome"] == "FAIL"


def test_downstream_zero_does_not_erase_extracted_propositions() -> None:
    request = _packaged_request(18)
    assert len(request.reference.propositions) == len(request.observation.propositions) == 2
    assert request.reference.expected_selected_reference_proposition_ids == ()
    assert request.observation.selected_candidate_ids == ()
    result = _result(request)
    assert result["outcome"] == "PASS"
    assert result["required_proposition_count"] == 2


def test_request_round_trip_is_exact_and_unknown_fields_fail_closed() -> None:
    document = hk_case_semantic_materiality_evaluation_request_document(_request())
    decoded = hk_case_semantic_materiality_evaluation_request_from_document(document)
    assert hk_case_semantic_materiality_evaluation_request_document(decoded) == document
    document["case_id"] = "answer-bearing"
    with pytest.raises(HKCaseSemanticMaterialityError):
        hk_case_semantic_materiality_evaluation_request_from_document(document)


def test_missing_required_proposition_is_a_false_zero_not_a_valid_empty_result() -> None:
    request = _request()
    observation = replace(
        request.observation,
        propositions=(),
        unit_observations=tuple(
            replace(
                item,
                use=HKCaseSemanticMaterialityUnitUse.NON_PROPOSITIONAL,
                candidate_ids=(),
            )
            for item in request.observation.unit_observations
        ),
        disposition=HKCaseSemanticMaterialityDisposition.COMPLETE_NO_PROPOSITION,
        selected_candidate_ids=(),
    )
    result = _result(replace(request, observation=observation))
    assert result["outcome"] == "FAIL"
    assert {
        "FALSE_ZERO",
        "MEANING_MISMATCH",
        "REQUIRED_PROPOSITION_MISSING",
    }.issubset(_reasons(result))


def test_unmatched_or_duplicate_mapping_is_unsupported_and_cannot_raise_recall() -> None:
    request = _request()
    extra = replace(
        request.observation.propositions[0],
        candidate_id="candidate_2",
        mapped_reference_proposition_id=None,
    )
    result = _result(
        replace(
            request,
            observation=replace(
                request.observation,
                propositions=(*request.observation.propositions, extra),
            ),
        )
    )
    assert result["outcome"] == "FAIL"
    assert "UNSUPPORTED_PROPOSITION" in _reasons(result)
    assert result["unsupported_candidate_ids"] == ["candidate_2"]


def test_authority_meaning_and_evidence_are_independent_failures() -> None:
    request = _request()
    observed = replace(
        request.observation.propositions[0],
        authority_role=HKCaseSemanticMaterialityAuthorityRole.OBITER,
        meaning_codes=("LEGAL_TEST", "UNADOPTED_SUBMISSION"),
        evidence_role_codes=("ANSWER",),
        range_ids=("range_1",),
    )
    result = _result(
        replace(
            request,
            observation=replace(request.observation, propositions=(observed,)),
        )
    )
    assert {
        "AUTHORITY_ROLE_MISMATCH",
        "EVIDENCE_INCOMPLETE",
        "MEANING_MISMATCH",
    }.issubset(_reasons(result))


def test_coverage_handoff_and_downstream_selection_are_exact() -> None:
    request = _request()
    reference = replace(request.reference, required_handoff_ids=("handoff_1",))
    observation = replace(
        request.observation,
        unit_observations=request.observation.unit_observations[:-1],
        selected_candidate_ids=(),
    )
    result = _result(replace(request, reference=reference, observation=observation))
    assert {
        "COVERAGE_INCOMPLETE",
        "DOWNSTREAM_SELECTION_MISMATCH",
        "HANDOFF_MISMATCH",
    }.issubset(_reasons(result))


def test_unresolved_reference_blocks_evaluator_instead_of_failing_candidate() -> None:
    request = _request()
    result = _result(
        replace(
            request,
            reference=replace(
                request.reference,
                adjudication_complete=False,
                unresolved_reference_ambiguity=True,
            ),
        )
    )
    assert result["outcome"] == "EVALUATOR_BLOCKED"
    assert "REFERENCE_BLOCKED" in _reasons(result)


def test_reference_or_source_instruction_leakage_is_a_hard_failure() -> None:
    request = _request()
    result = _result(
        replace(
            request,
            observation=replace(
                request.observation,
                source_text_treated_as_instruction=True,
                hidden_reference_received_by_workflow=True,
            ),
        )
    )
    assert result["outcome"] == "FAIL"
    assert "EVALUATION_LEAKAGE" in _reasons(result)


def test_zero_proposition_reference_requires_complete_units_and_exact_handoffs() -> None:
    request = _request()
    reference = replace(
        request.reference,
        propositions=(),
        expected_disposition=HKCaseSemanticMaterialityDisposition.COMPLETE_NO_PROPOSITION,
        required_handoff_ids=("citation_1",),
        expected_selected_reference_proposition_ids=(),
    )
    observation = replace(
        request.observation,
        propositions=(),
        unit_observations=(
            replace(
                request.observation.unit_observations[0],
                use=HKCaseSemanticMaterialityUnitUse.CITATION_ONLY,
                candidate_ids=(),
                handoff_ids=("citation_1",),
            ),
            replace(
                request.observation.unit_observations[1],
                use=HKCaseSemanticMaterialityUnitUse.NON_PROPOSITIONAL,
                candidate_ids=(),
            ),
        ),
        disposition=HKCaseSemanticMaterialityDisposition.COMPLETE_NO_PROPOSITION,
        handoff_ids=("citation_1",),
        selected_candidate_ids=(),
    )
    result = _result(replace(request, reference=reference, observation=observation))
    assert result["outcome"] == "PASS"
    assert result["required_proposition_count"] == 0
    assert result["observed_proposition_count"] == 0
