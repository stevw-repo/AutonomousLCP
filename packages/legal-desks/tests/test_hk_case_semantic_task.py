"""ADR 0065/0066 Hong Kong Case semantic-task preflight tests."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKCaseOpinionRole,
    HKCaseOriginalLanguage,
    HKCaseSemanticDependency,
    HKCaseSemanticEvidenceRange,
    HKCaseSemanticOpinionManifest,
    HKCaseSemanticRequestKind,
    HKCaseSemanticSuppliedUnit,
    HKCaseSemanticTaskError,
    HKCaseSemanticTaskFamily,
    HKCaseSemanticTaskOutcome,
    HKCaseSemanticTaskReason,
    HKCaseSemanticTaskRequest,
    HKCaseSemanticUnitManifest,
    HKCaseSemanticWorkflowComponent,
    evaluate_hk_case_semantic_task_request,
    hk_case_semantic_task_request_document,
    hk_case_semantic_task_request_from_document,
    hk_case_semantic_task_result_document,
)
from jsonschema import Draft202012Validator

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_cases_package"

_WORKFLOW_ROLES = (
    "COVERAGE_LEDGER",
    "MODEL_SETTINGS",
    "OUTPUT_SCHEMA",
    "PARSER_PROFILE",
    "PROCESSING_BUILD",
    "PROMPT",
    "SEGMENTATION_CONTRACT",
    "SOURCE_RULEBOOK",
    "STRUCTURE_CONTRACT",
    "VALIDATOR",
)
_EVIDENCE_ROLES = (
    "ANSWER",
    "APPLICATION",
    "ATTRIBUTION",
    "CONTEXT",
    "ISSUE",
    "QUALIFICATION",
    "QUOTATION",
    "RESULT",
)
_ANALYSIS_KINDS = {
    HKCaseSemanticRequestKind.EVIDENCE_PACKET,
    HKCaseSemanticRequestKind.FULL_JUDGMENT,
    HKCaseSemanticRequestKind.JUDGMENT_INTEGRATION,
    HKCaseSemanticRequestKind.TARGETED_REANALYSIS,
}
_CHALLENGE_KINDS = set(HKCaseSemanticRequestKind) - _ANALYSIS_KINDS
_PACKET_KINDS = {
    HKCaseSemanticRequestKind.COVERAGE_PACKET_CHALLENGE,
    HKCaseSemanticRequestKind.EVIDENCE_PACKET,
}
_TARGETED_KINDS = {
    HKCaseSemanticRequestKind.FINAL_TARGETED_CHALLENGE,
    HKCaseSemanticRequestKind.TARGETED_REANALYSIS,
}
_SEMANTIC_TASK_PREFLIGHT_ORDER = (
    HKCaseSemanticRequestKind.FULL_JUDGMENT,
    HKCaseSemanticRequestKind.EVIDENCE_PACKET,
    HKCaseSemanticRequestKind.JUDGMENT_INTEGRATION,
    HKCaseSemanticRequestKind.TARGETED_REANALYSIS,
    HKCaseSemanticRequestKind.FULL_JUDGMENT_CHALLENGE,
    HKCaseSemanticRequestKind.COVERAGE_PACKET_CHALLENGE,
    HKCaseSemanticRequestKind.JUDGMENT_RESULT_CHALLENGE,
    HKCaseSemanticRequestKind.FINAL_TARGETED_CHALLENGE,
)
_PROPOSAL_KINDS = _CHALLENGE_KINDS | {
    HKCaseSemanticRequestKind.JUDGMENT_INTEGRATION,
    HKCaseSemanticRequestKind.TARGETED_REANALYSIS,
}


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


def _fingerprint(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _request(
    kind: HKCaseSemanticRequestKind = HKCaseSemanticRequestKind.FULL_JUDGMENT,
) -> HKCaseSemanticTaskRequest:
    texts = {
        "unit_1": "The applicable test has three cumulative limbs.",
        "unit_2": "On the evidence, the second limb was not established.",
        "unit_3": "The statutory definition supplies the relevant threshold.",
    }
    units = (
        HKCaseSemanticUnitManifest(
            unit_id="unit_1",
            opinion_id="opinion_1",
            source_order=1,
            primary=True,
            text_fingerprint=_fingerprint(texts["unit_1"]),
            required_dependency_unit_ids=("unit_3",),
        ),
        HKCaseSemanticUnitManifest(
            unit_id="unit_2",
            opinion_id="opinion_1",
            source_order=2,
            primary=True,
            text_fingerprint=_fingerprint(texts["unit_2"]),
            required_dependency_unit_ids=(),
        ),
        HKCaseSemanticUnitManifest(
            unit_id="unit_3",
            opinion_id="opinion_1",
            source_order=3,
            primary=False,
            text_fingerprint=_fingerprint(texts["unit_3"]),
            required_dependency_unit_ids=(),
        ),
    )
    packet = kind in _PACKET_KINDS
    assigned = ("unit_1",) if packet else ("unit_1", "unit_2")
    supplied_ids = ("unit_1", "unit_3") if packet else ("unit_1", "unit_2", "unit_3")
    supplied = tuple(
        HKCaseSemanticSuppliedUnit(unit_id, texts[unit_id]) for unit_id in supplied_ids
    )
    ranges = tuple(
        HKCaseSemanticEvidenceRange(
            f"range_{unit_id[-1]}",
            unit_id,
            0,
            len(texts[unit_id].encode("utf-8")),
            _fingerprint(texts[unit_id]),
        )
        for unit_id in supplied_ids
    )
    family = (
        HKCaseSemanticTaskFamily.ANALYSIS
        if kind in _ANALYSIS_KINDS
        else HKCaseSemanticTaskFamily.CHALLENGE
    )
    return HKCaseSemanticTaskRequest(
        task_family=family,
        request_kind=kind,
        execution_id="execution_1",
        attempt_id="attempt_1",
        packet_id="packet_1" if packet else None,
        judgment_work_id="judgment_work_1",
        workflow_components=tuple(
            HKCaseSemanticWorkflowComponent(role, _fingerprint(role)) for role in _WORKFLOW_ROLES
        ),
        judicial_decision_id="judicial_decision_1",
        official_version_id="official_version_1",
        artifact_fingerprint=_fingerprint("artifact"),
        source_snapshot_fingerprint=_fingerprint("snapshot"),
        cutoff="2026-08-25",
        court="Court of Final Appeal",
        decision_date="2026-07-01",
        citation="[2026] HKCFA 1",
        original_language=HKCaseOriginalLanguage.ENGLISH,
        opinions=(
            HKCaseSemanticOpinionManifest(
                "opinion_1",
                1,
                HKCaseOpinionRole.LEAD,
                ("judge_1",),
            ),
        ),
        units=units,
        assigned_primary_unit_ids=assigned,
        supplied_units=supplied,
        evidence_ranges=ranges,
        dependencies=(HKCaseSemanticDependency("unit_1", "unit_3", _fingerprint(texts["unit_3"])),),
        allowed_object_ids=supplied_ids + tuple(item.range_id for item in ranges),
        required_evidence_role_codes=_EVIDENCE_ROLES,
        output_budget_bytes=4096,
        validated_proposal_fingerprint=(
            _fingerprint("proposal") if kind in _PROPOSAL_KINDS else None
        ),
        reconciled_objection_fingerprint=(
            _fingerprint("objection") if kind in _TARGETED_KINDS else None
        ),
        source_text_is_instruction=False,
        external_tools_permitted=False,
        hidden_reference_included=False,
        confidence_score_requested=False,
        source_evidence_available=True,
    )


def _evaluate(request: HKCaseSemanticTaskRequest) -> dict[str, JsonValue]:
    return hk_case_semantic_task_result_document(evaluate_hk_case_semantic_task_request(request))


def _reasons(result: dict[str, JsonValue]) -> tuple[str, ...]:
    value = result["reasons"]
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return tuple(item for item in value if isinstance(item, str))


def test_all_eight_request_kinds_have_one_valid_source_neutral_envelope() -> None:
    for kind in HKCaseSemanticRequestKind:
        result = _evaluate(_request(kind))
        assert result["outcome"] == HKCaseSemanticTaskOutcome.VALID_REQUEST.value
        assert result["reasons"] == [HKCaseSemanticTaskReason.VALID_REQUEST.value]
        assert result["complete_judgment_assignment"] is (kind not in _PACKET_KINDS)
        assert result["provider_call_authorized"] is False
        assert result["semantic_result_accepted"] is False
        assert result["search_records_created"] == 0
        assert result["release_eligible"] is False
        assert result["external_effects"] == "NONE"


def test_generated_preflight_package_executes_all_eight_kinds_without_semantic_claim() -> None:
    schema_root = _PACKAGE_ROOT / "contracts/schemas"
    case_schema = _json(schema_root / "hk-case-semantic-task-case.schema.json")
    expected_schema = _json(schema_root / "hk-case-semantic-task-case-result.schema.json")
    Draft202012Validator.check_schema(case_schema)
    Draft202012Validator.check_schema(expected_schema)
    case_validator = _validator(case_schema)
    expected_validator = _validator(expected_schema)
    catalogue = _json(_PACKAGE_ROOT / "catalogues/semantic-task-preflight-cases.json")
    entries = _objects(catalogue["entries"])
    assert catalogue["fixture_count"] == catalogue["request_kind_count"] == 8
    assert catalogue["frozen_semantic_case_count"] == 0
    assert catalogue["frozen_semantic_cases_executed"] is False
    assert [item["request_kind"] for item in entries] == [
        item.value for item in _SEMANTIC_TASK_PREFLIGHT_ORDER
    ]
    for entry in entries:
        fixture = _json(_PACKAGE_ROOT / str(entry["fixture_path"]))
        expected = _json(_PACKAGE_ROOT / str(entry["expected_path"]))
        case_validator.validate(fixture)
        expected_validator.validate(expected)
        request = hk_case_semantic_task_request_from_document(fixture["request"])
        actual = hk_case_semantic_task_result_document(
            evaluate_hk_case_semantic_task_request(request)
        )
        assert actual == expected["result"]
        assert actual["provider_call_authorized"] is False
        assert actual["semantic_result_accepted"] is False


def test_request_round_trip_is_exact_and_unknown_fields_fail_closed() -> None:
    document = hk_case_semantic_task_request_document(_request())
    decoded = hk_case_semantic_task_request_from_document(document)
    assert hk_case_semantic_task_request_document(decoded) == document
    document["unknown"] = True
    with pytest.raises(HKCaseSemanticTaskError):
        hk_case_semantic_task_request_from_document(document)


def test_task_family_and_prior_stage_bindings_are_exact() -> None:
    mismatch = replace(_request(), task_family=HKCaseSemanticTaskFamily.CHALLENGE)
    missing_proposal = replace(
        _request(HKCaseSemanticRequestKind.FULL_JUDGMENT_CHALLENGE),
        validated_proposal_fingerprint=None,
    )
    unexpected_objection = replace(
        _request(),
        reconciled_objection_fingerprint=_fingerprint("objection"),
    )
    assert set(_reasons(_evaluate(mismatch))) == {
        "PRIOR_STAGE_BINDING_INVALID",
        "TASK_KIND_MISMATCH",
    }
    assert _evaluate(missing_proposal)["reasons"] == ["PRIOR_STAGE_BINDING_INVALID"]
    assert _evaluate(unexpected_objection)["reasons"] == ["PRIOR_STAGE_BINDING_INVALID"]


def test_complete_request_cannot_omit_or_reorder_a_primary_unit() -> None:
    omitted = replace(_request(), assigned_primary_unit_ids=("unit_1",))
    reordered = replace(_request(), assigned_primary_unit_ids=("unit_2", "unit_1"))
    omitted_result = _evaluate(omitted)
    reordered_result = _evaluate(reordered)
    assert "COMPLETE_COVERAGE_REQUIRED" in _reasons(omitted_result)
    assert "ASSIGNED_PRIMARY_UNITS_INVALID" in _reasons(reordered_result)
    assert "COMPLETE_COVERAGE_REQUIRED" in _reasons(reordered_result)


def test_packet_requires_exact_dependency_text_and_supplied_range() -> None:
    request = _request(HKCaseSemanticRequestKind.EVIDENCE_PACKET)
    assert _evaluate(request)["outcome"] == "VALID_REQUEST"
    missing_dependency = replace(request, dependencies=())
    wrong_dependency = replace(
        request,
        dependencies=(
            replace(request.dependencies[0], dependency_text_fingerprint=_fingerprint("wrong")),
        ),
    )
    missing_range = replace(request, evidence_ranges=request.evidence_ranges[:-1])
    assert "DEPENDENCY_PACKET_INVALID" in _reasons(_evaluate(missing_dependency))
    assert "DEPENDENCY_PACKET_INVALID" in _reasons(_evaluate(wrong_dependency))
    assert "EVIDENCE_RANGE_INVALID" in _reasons(_evaluate(missing_range))


def test_text_fingerprints_and_utf8_byte_boundaries_are_not_repaired() -> None:
    request = _request()
    changed_text = replace(
        request,
        supplied_units=(
            replace(request.supplied_units[0], exact_text="plausible replacement"),
            *request.supplied_units[1:],
        ),
    )
    split_utf8 = replace(
        request,
        supplied_units=(
            replace(request.supplied_units[0], exact_text="法 rule"),
            *request.supplied_units[1:],
        ),
        units=(
            replace(request.units[0], text_fingerprint=_fingerprint("法 rule")),
            *request.units[1:],
        ),
        evidence_ranges=(
            replace(request.evidence_ranges[0], end_byte=1),
            *request.evidence_ranges[1:],
        ),
    )
    assert "EVIDENCE_RANGE_INVALID" in _reasons(_evaluate(changed_text))
    assert "EVIDENCE_RANGE_INVALID" in _reasons(_evaluate(split_utf8))


@pytest.mark.parametrize(
    "field",
    [
        "source_text_is_instruction",
        "external_tools_permitted",
        "hidden_reference_included",
        "confidence_score_requested",
    ],
)
def test_hidden_authority_and_source_instruction_flags_are_rejected(field: str) -> None:
    request = replace(_request(), **{field: True})
    result = _evaluate(request)
    assert result["outcome"] == "INVALID"
    assert "CONSTRAINT_BOUNDARY_INVALID" in _reasons(result)


def test_missing_source_blocks_only_an_otherwise_valid_request() -> None:
    unavailable = replace(_request(), source_evidence_available=False)
    result = _evaluate(unavailable)
    assert result["outcome"] == "BLOCKED"
    assert result["reasons"] == ["SOURCE_EVIDENCE_UNAVAILABLE"]
    malformed = replace(unavailable, hidden_reference_included=True)
    malformed_result = _evaluate(malformed)
    assert malformed_result["outcome"] == "INVALID"
    assert malformed_result["reasons"] == ["CONSTRAINT_BOUNDARY_INVALID"]


def test_direct_dataclass_construction_cannot_bypass_scalar_validation() -> None:
    invalid = replace(
        _request(),
        artifact_fingerprint="not-a-fingerprint",
        decision_date="2026-02-30",
        output_budget_bytes=0,
    )
    result = _evaluate(invalid)
    assert result["outcome"] == "INVALID"
    assert "WORKFLOW_BINDING_INVALID" in _reasons(result)


def test_duplicate_ids_and_incomplete_allowed_object_universe_are_rejected() -> None:
    request = _request()
    duplicate = replace(
        request,
        evidence_ranges=(request.evidence_ranges[0], request.evidence_ranges[0]),
    )
    incomplete = replace(request, allowed_object_ids=request.allowed_object_ids[:-1])
    assert "DUPLICATE_IDENTITY" in _reasons(_evaluate(duplicate))
    assert "CONSTRAINT_BOUNDARY_INVALID" in _reasons(_evaluate(incomplete))
