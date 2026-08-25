"""ADR 0063/0064/0068 semantic proposition-boundary evaluator tests."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKCaseSemanticBoundaryAuthorityRole,
    HKCaseSemanticBoundaryError,
    HKCaseSemanticBoundaryEvaluationRequest,
    HKCaseSemanticBoundaryResolution,
    HKCaseSemanticBoundaryUnitUse,
    evaluate_hk_case_semantic_boundary,
    hk_case_frozen_pair_memberships,
    hk_case_semantic_boundary_evaluation_request_document,
    hk_case_semantic_boundary_evaluation_request_from_document,
    hk_case_semantic_boundary_result_document,
)
from jsonschema import Draft202012Validator

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_cases_package"
_FORBIDDEN_MODEL_FIELDS = frozenset(
    {
        "authority_role",
        "boundary_codes",
        "case_id",
        "coverage_cell_id",
        "critical_error_tag",
        "expected_answer",
        "expected_disposition",
        "expected_resolution",
        "fixture_id",
        "forbidden_boundary_codes",
        "mapped_reference_proposition_id",
        "pair_memberships",
        "pair_role",
        "reference_map_id",
        "reference_path",
        "required_boundary_codes",
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


def _packaged_request(number: int) -> HKCaseSemanticBoundaryEvaluationRequest:
    case_id = f"HKCASE-PROP-SEM-BND-{number:03d}"
    reference = _json(_PACKAGE_ROOT / f"evaluations/semantic-boundary/references/{case_id}.json")
    observation = _json(
        _PACKAGE_ROOT / f"evaluations/semantic-boundary/observations/{case_id}.json"
    )
    return hk_case_semantic_boundary_evaluation_request_from_document(
        {
            "schema_id": "asklegal.hk-cases.semantic-boundary-evaluation-request",
            "schema_version": "1.0.0",
            "rule_id": "HKCASE-PROP-SEM-BOUNDARY-EVALUATOR-001",
            "evaluator_fingerprint": _fingerprint("semantic-boundary-evaluator-v1"),
            "reference": reference,
            "observation": observation,
        }
    )


def _result(request: HKCaseSemanticBoundaryEvaluationRequest) -> dict[str, JsonValue]:
    return hk_case_semantic_boundary_result_document(evaluate_hk_case_semantic_boundary(request))


def _reasons(result: dict[str, JsonValue]) -> set[str]:
    value = result["reasons"]
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return {item for item in value if isinstance(item, str)}


def test_all_twenty_two_frozen_boundary_cases_are_separated_and_execute() -> None:
    schema_root = _PACKAGE_ROOT / "contracts/schemas"
    case_schema = _json(schema_root / "hk-case-semantic-boundary-case.schema.json")
    request_schema = _json(schema_root / "hk-case-semantic-boundary-evaluation-request.schema.json")
    result_schema = _json(schema_root / "hk-case-semantic-boundary-case-result.schema.json")
    for schema in (case_schema, request_schema, result_schema):
        Draft202012Validator.check_schema(schema)
    case_validator = _validator(case_schema)
    request_validator = _validator(request_schema)
    result_validator = _validator(result_schema)
    candidate_counts = (1, 1, 2, 2, 1, 1, 2, 1, 2, 1, 1, 1, 2, 2, 2, 1, 2, 3, 3, 2, 2, 2)
    for number, candidate_count in enumerate(candidate_counts, 1):
        case_id = f"HKCASE-PROP-SEM-BND-{number:03d}"
        case = _json(_PACKAGE_ROOT / f"fixtures/semantic/boundary/{case_id}.json")
        expected = _json(_PACKAGE_ROOT / f"expected/semantic-boundary/{case_id}.json")
        request = _packaged_request(number)
        request_document = hk_case_semantic_boundary_evaluation_request_document(request)
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
        assert actual["external_effects"] == "NONE"


def test_boundary_catalogue_has_exact_ids_cells_roles_and_complete_pairs() -> None:
    catalogue = _json(_PACKAGE_ROOT / "catalogues/semantic-boundary-cases.json")
    entries = _objects(catalogue["entries"])
    case_ids = [f"HKCASE-PROP-SEM-BND-{number:03d}" for number in range(1, 23)]
    coverage_ids = [f"HKCASE-PROP-COV-SBND-{number:03d}" for number in range(1, 23)]
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
    assert catalogue["case_count"] == catalogue["coverage_cell_count"] == 22
    assert catalogue["executed_semantic_case_count"] == 58
    assert catalogue["remaining_semantic_case_count"] == 20
    assert catalogue["complete_pair_ids"] == [
        f"HKCASE-PROP-PAIR-{number:03d}" for number in range(9, 16)
    ]
    assert catalogue["pending_cross_checkpoint_pair_ids"] == []


@pytest.mark.parametrize(
    ("positive", "near_miss"),
    [(1, 3), (5, 7), (10, 13), (16, 17), (10, 14), (5, 21), (19, 18)],
)
def test_each_boundary_pair_rejects_the_other_members_observation(
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


def test_cumulative_test_cannot_split_and_independent_grounds_cannot_merge() -> None:
    cumulative = _packaged_request(1)
    extra = replace(
        cumulative.observation.propositions[0],
        candidate_id="candidate_2",
        mapped_reference_proposition_id=None,
        range_ids=("range_2",),
    )
    split_result = _result(
        replace(
            cumulative,
            observation=replace(
                cumulative.observation,
                propositions=(*cumulative.observation.propositions, extra),
            ),
        )
    )
    independent = _packaged_request(3)
    merge_result = _result(
        replace(
            independent,
            observation=replace(
                independent.observation,
                propositions=independent.observation.propositions[:1],
                selected_candidate_ids=("candidate_1",),
            ),
        )
    )
    assert "CANDIDATE_INVENTORY_MISMATCH" in _reasons(split_result)
    assert "CANDIDATE_INVENTORY_MISMATCH" in _reasons(merge_result)


def test_joint_opinion_is_one_reasoning_path_not_one_candidate_per_judge() -> None:
    request = _packaged_request(10)
    assert len(request.reference.opinions) == 1
    assert request.reference.opinions[0].judge_ids == ("judge_1", "judge_2", "judge_3")
    assert len(request.reference.propositions) == len(request.observation.propositions) == 1
    assert _result(request)["outcome"] == "PASS"


def test_agreement_only_opinion_is_accounted_without_duplicate_proposition() -> None:
    request = _packaged_request(12)
    assert len(request.reference.opinions) == 2
    assert len(request.reference.propositions) == 1
    agreement = request.observation.units[1]
    assert agreement.use is HKCaseSemanticBoundaryUnitUse.AGREEMENT_ONLY
    assert agreement.candidate_ids == ()
    assert _result(request)["outcome"] == "PASS"


def test_concurrence_and_dissent_role_and_opinion_paths_are_exact() -> None:
    for number in (13, 14):
        request = _packaged_request(number)
        separate = request.observation.propositions[1]
        changed = replace(
            separate,
            authority_role=HKCaseSemanticBoundaryAuthorityRole.OPERATIVE,
            opinion_path_ids=("opinion_1",),
        )
        result = _result(
            replace(
                request,
                observation=replace(
                    request.observation,
                    propositions=(request.observation.propositions[0], changed),
                ),
            )
        )
        assert {"AUTHORITY_ROLE_MISMATCH", "OPINION_PATH_MISMATCH"}.issubset(_reasons(result))


def test_express_adoption_cannot_be_inferred_from_a_shared_result() -> None:
    adopted = _packaged_request(16)
    same_result = _packaged_request(17)
    assert adopted.reference.opinions[0].expressly_adopted_opinion_ids == ("opinion_2",)
    assert same_result.reference.opinions[0].expressly_adopted_opinion_ids == ()
    swapped = replace(
        same_result.observation,
        model_input_fingerprint=adopted.reference.model_input_fingerprint,
    )
    result = _result(replace(adopted, observation=swapped))
    assert result["outcome"] == "FAIL"
    assert "OPINION_INVENTORY_MISMATCH" in _reasons(result)


def test_unsupported_plurality_is_quarantined_without_manufactured_majority() -> None:
    request = _packaged_request(18)
    assert request.reference.expected_selected_reference_proposition_ids == ()
    assert request.observation.selected_candidate_ids == ()
    assert len(request.observation.propositions) == 3
    assert all(
        item.resolution is HKCaseSemanticBoundaryResolution.QUARANTINED
        and item.derived_statement is None
        for item in request.observation.propositions
    )
    result = _result(request)
    assert result["outcome"] == "PASS"
    assert result["quarantined_candidate_count"] == 3
    assert result["accepted_candidate_count"] == 0


def test_inventory_units_selection_and_leakage_fail_independently() -> None:
    request = _packaged_request(19)
    altered_opinion = replace(request.observation.opinions[0], judge_ids=("judge_9",))
    altered_unit = replace(request.observation.units[0], candidate_ids=())
    observation = replace(
        request.observation,
        opinions=(altered_opinion, *request.observation.opinions[1:]),
        units=(altered_unit, *request.observation.units[1:]),
        selected_candidate_ids=(),
        hidden_reference_received_by_workflow=True,
    )
    result = _result(replace(request, observation=observation))
    assert {
        "EVALUATION_LEAKAGE",
        "OPINION_INVENTORY_MISMATCH",
        "SELECTION_MISMATCH",
        "UNIT_ACCOUNTING_MISMATCH",
    }.issubset(_reasons(result))


def test_reference_uncertainty_blocks_evaluator_instead_of_guessing() -> None:
    request = _packaged_request(18)
    result = _result(
        replace(
            request,
            reference=replace(request.reference, unresolved_reference_ambiguity=True),
        )
    )
    assert result["outcome"] == "EVALUATOR_BLOCKED"
    assert "REFERENCE_BLOCKED" in _reasons(result)


def test_request_round_trip_is_exact_and_unknown_fields_fail_closed() -> None:
    document = hk_case_semantic_boundary_evaluation_request_document(_packaged_request(1))
    decoded = hk_case_semantic_boundary_evaluation_request_from_document(document)
    assert hk_case_semantic_boundary_evaluation_request_document(decoded) == document
    document["case_id"] = "answer-bearing"
    with pytest.raises(HKCaseSemanticBoundaryError):
        hk_case_semantic_boundary_evaluation_request_from_document(document)
