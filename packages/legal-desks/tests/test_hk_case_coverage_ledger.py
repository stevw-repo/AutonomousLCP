"""ADR 0062 deterministic Hong Kong Case Proposition coverage tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKCaseCandidateOutcome,
    HKCaseCoverageDependency,
    HKCaseCoverageLedgerRequest,
    HKCaseCoverageSegment,
    HKCaseCoverageUnit,
    HKCaseCoverageUnitKind,
    HKCaseDependencyKind,
    HKCaseEvidenceRole,
    HKCaseLedgerError,
    HKCaseLedgerOutcome,
    HKCaseLedgerReason,
    HKCaseNonPropositionalReason,
    HKCaseOpinion,
    HKCaseOpinionRole,
    HKCasePrimaryUse,
    HKCasePropositionCandidate,
    HKCaseUnitResolution,
    evaluate_hk_case_coverage_ledger,
    hk_case_coverage_ledger_request_document,
    hk_case_coverage_ledger_request_from_document,
    hk_case_coverage_ledger_result_document,
)
from jsonschema import Draft202012Validator

FP_A = f"sha256:{'a' * 64}"
FP_B = f"sha256:{'b' * 64}"
FP_C = f"sha256:{'c' * 64}"
PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_cases_package"


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)


def _json(path: Path) -> dict[str, JsonValue]:
    value = checked_json_value(json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(value, dict)
    return value


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _json_object_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [_json_object(item) for item in value]


def _json_text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _unit(
    number: int,
    *,
    opinion_id: str = "opn_lead",
    kind: HKCaseCoverageUnitKind = HKCaseCoverageUnitKind.PARAGRAPH,
) -> HKCaseCoverageUnit:
    return HKCaseCoverageUnit(
        unit_id=f"unit_{number}",
        opinion_id=opinion_id,
        source_order=number,
        kind=kind,
        source_range_id=f"range_{number}",
        text_fingerprint={1: FP_A, 2: FP_B}.get(number, FP_C),
        resolutions=(HKCaseUnitResolution.RESOLVED,),
        primary_uses=(HKCasePrimaryUse.NON_PROPOSITIONAL,),
        evidence_roles=(),
        non_propositional_reason=(
            HKCaseNonPropositionalReason.UNUSED_PROCEDURAL_OR_FACTUAL_NARRATIVE
        ),
        citation_or_treatment_lead=False,
        screening_handoff_ids=(),
    )


def _request() -> HKCaseCoverageLedgerRequest:
    units = (
        _unit(1, kind=HKCaseCoverageUnitKind.HEADING),
        replace(
            _unit(2),
            primary_uses=(HKCasePrimaryUse.PROPOSITION_EVIDENCE,),
            non_propositional_reason=None,
            evidence_roles=(HKCaseEvidenceRole.ISSUE, HKCaseEvidenceRole.ANSWER),
        ),
        replace(
            _unit(3, kind=HKCaseCoverageUnitKind.DISPOSITION),
            primary_uses=(HKCasePrimaryUse.CONTEXT_EVIDENCE,),
            non_propositional_reason=None,
            evidence_roles=(HKCaseEvidenceRole.RESULT,),
        ),
    )
    return HKCaseCoverageLedgerRequest(
        judicial_decision_id="decision_1",
        official_version_id="version_1",
        artifact_fingerprint=FP_A,
        parser_fingerprint=FP_B,
        rulebook_fingerprint=FP_C,
        cutoff="2026-08-25T00:00:00Z",
        source_support_available=True,
        source_support_refs=("evidence_1",),
        semantic_resolution_complete=False,
        opinions=(HKCaseOpinion("opn_lead", HKCaseOpinionRole.LEAD, ("judge_1",)),),
        units=units,
        segments=(
            HKCaseCoverageSegment("segment_1", "opn_lead", tuple(x.unit_id for x in units), ()),
        ),
        candidates=(
            HKCasePropositionCandidate("candidate_1", HKCaseCandidateOutcome.ACCEPTED, ("unit_2",)),
        ),
    )


def _evaluate(request: HKCaseCoverageLedgerRequest | None = None):
    return evaluate_hk_case_coverage_ledger(request or _request())


def test_dled_001_complete_short_judgment_has_exact_inventory() -> None:
    result = _evaluate()
    assert result.outcome is HKCaseLedgerOutcome.STRUCTURE_VALID
    assert (result.opinion_count, result.unit_count, result.segment_count) == (1, 3, 1)
    assert result.reasons == (HKCaseLedgerReason.STRUCTURE_VALID,)
    assert result.search_records_created == 0
    assert not result.release_eligible
    assert not result.semantic_analysis_authorized
    assert result.external_effects == "NONE"


def test_dled_002_all_delivered_opinions_and_judges_remain_distinct() -> None:
    opinions = (
        HKCaseOpinion("opn_lead", HKCaseOpinionRole.LEAD, ("judge_1",)),
        HKCaseOpinion("opn_concurrence", HKCaseOpinionRole.CONCURRENCE, ("judge_2",)),
        HKCaseOpinion("opn_dissent", HKCaseOpinionRole.DISSENT, ("judge_3",)),
        HKCaseOpinion("opn_agreement", HKCaseOpinionRole.AGREEMENT_ONLY, ("judge_4",)),
    )
    units = tuple(
        _unit(index, opinion_id=item.opinion_id) for index, item in enumerate(opinions, 1)
    )
    segments = tuple(
        HKCaseCoverageSegment(f"segment_{index}", item.opinion_id, (units[index - 1].unit_id,), ())
        for index, item in enumerate(opinions, 1)
    )
    result = _evaluate(replace(_request(), opinions=opinions, units=units, segments=segments))
    assert result.outcome is HKCaseLedgerOutcome.STRUCTURE_VALID
    assert result.opinion_count == 4
    assert result.unit_count == 4


def test_dled_003_numbered_unnumbered_and_heading_units_keep_source_order() -> None:
    units = (
        _unit(1),
        _unit(2),
        _unit(3, kind=HKCaseCoverageUnitKind.HEADING),
    )
    result = _evaluate(replace(_request(), units=units))
    assert result.outcome is HKCaseLedgerOutcome.STRUCTURE_VALID
    assert result.unit_count == 3


def test_dled_004_every_supported_source_part_is_inventory_material() -> None:
    kinds = (
        HKCaseCoverageUnitKind.FOOTNOTE,
        HKCaseCoverageUnitKind.TABLE,
        HKCaseCoverageUnitKind.QUOTED_BLOCK,
        HKCaseCoverageUnitKind.ORDER,
        HKCaseCoverageUnitKind.DISPOSITION,
        HKCaseCoverageUnitKind.SCHEDULE,
        HKCaseCoverageUnitKind.APPENDIX,
        HKCaseCoverageUnitKind.COVER,
        HKCaseCoverageUnitKind.APPEARANCE,
    )
    units = tuple(_unit(index, kind=kind) for index, kind in enumerate(kinds, 1))
    segment = replace(_request().segments[0], primary_unit_ids=tuple(x.unit_id for x in units))
    result = _evaluate(replace(_request(), units=units, segments=(segment,), candidates=()))
    assert result.outcome is HKCaseLedgerOutcome.STRUCTURE_VALID
    assert result.unit_count == len(kinds)


def test_dled_005_exact_primary_union_is_valid() -> None:
    request = _request()
    segments = (
        replace(request.segments[0], segment_id="segment_1", primary_unit_ids=("unit_1",)),
        replace(request.segments[0], segment_id="segment_2", primary_unit_ids=("unit_2", "unit_3")),
    )
    assert (
        _evaluate(replace(request, segments=segments)).outcome
        is HKCaseLedgerOutcome.STRUCTURE_VALID
    )


@pytest.mark.parametrize(
    ("primary_ids", "reason"),
    [
        (("unit_1", "unit_2", "unit_2", "unit_3"), HKCaseLedgerReason.DUPLICATE_PRIMARY_COVERAGE),
        (("unit_1", "unit_2"), HKCaseLedgerReason.MISSING_PRIMARY_COVERAGE),
        (("unit_2", "unit_1", "unit_3"), HKCaseLedgerReason.PRIMARY_COVERAGE_REORDERED),
    ],
)
def test_dled_006_to_008_invalid_primary_coverage_cannot_pass(
    primary_ids: tuple[str, ...], reason: HKCaseLedgerReason
) -> None:
    request = _request()
    segment = replace(request.segments[0], primary_unit_ids=primary_ids)
    result = _evaluate(replace(request, segments=(segment,)))
    assert result.outcome is HKCaseLedgerOutcome.INVALID
    assert reason in result.reasons


def test_dled_009_exact_context_dependency_does_not_duplicate_primary_coverage() -> None:
    request = _request()
    dependency = HKCaseCoverageDependency("unit_1", FP_A, HKCaseDependencyKind.CONTEXT, ())
    segment = replace(request.segments[0], dependencies=(dependency,))
    result = _evaluate(replace(request, segments=(segment,)))
    assert result.outcome is HKCaseLedgerOutcome.STRUCTURE_VALID
    assert result.dependency_count == 1
    assert result.unit_count == 3


@pytest.mark.parametrize(
    ("dependency", "reason"),
    [
        (
            HKCaseCoverageDependency("unit_missing", FP_A, HKCaseDependencyKind.CONTEXT, ()),
            HKCaseLedgerReason.DEPENDENCY_UNKNOWN_PRIMARY,
        ),
        (
            HKCaseCoverageDependency("unit_1", FP_B, HKCaseDependencyKind.CONTEXT, ()),
            HKCaseLedgerReason.DEPENDENCY_FINGERPRINT_MISMATCH,
        ),
    ],
)
def test_dled_010_dangling_or_drifted_dependency_fails_closed(
    dependency: HKCaseCoverageDependency, reason: HKCaseLedgerReason
) -> None:
    request = _request()
    segment = replace(request.segments[0], dependencies=(dependency,))
    result = _evaluate(replace(request, segments=(segment,)))
    assert result.outcome is HKCaseLedgerOutcome.INVALID
    assert reason in result.reasons


def test_dled_011_cross_opinion_adoption_keeps_primary_inventories_separate() -> None:
    opinions = (
        HKCaseOpinion("opn_lead", HKCaseOpinionRole.LEAD, ("judge_1",)),
        HKCaseOpinion("opn_adopting", HKCaseOpinionRole.JOINT, ("judge_2",)),
    )
    units = (_unit(1), _unit(2, opinion_id="opn_adopting"))
    dependency = HKCaseCoverageDependency(
        "unit_1",
        FP_A,
        HKCaseDependencyKind.CROSS_OPINION_ADOPTION,
        ("range_adoption", "range_adopted"),
    )
    segments = (
        HKCaseCoverageSegment("segment_1", "opn_lead", ("unit_1",), ()),
        HKCaseCoverageSegment("segment_2", "opn_adopting", ("unit_2",), (dependency,)),
    )
    result = _evaluate(
        replace(_request(), opinions=opinions, units=units, segments=segments, candidates=())
    )
    assert result.outcome is HKCaseLedgerOutcome.STRUCTURE_VALID
    assert result.dependency_count == 1


def test_dled_012_every_unit_has_one_resolution() -> None:
    result = _evaluate()
    assert result.resolved_unit_count == result.unit_count


@pytest.mark.parametrize(
    "resolutions",
    [(), (HKCaseUnitResolution.RESOLVED, HKCaseUnitResolution.QUARANTINED)],
)
def test_dled_013_missing_or_conflicting_resolution_is_invalid(
    resolutions: tuple[HKCaseUnitResolution, ...],
) -> None:
    request = _request()
    units = (replace(request.units[0], resolutions=resolutions), *request.units[1:])
    result = _evaluate(replace(request, units=units))
    assert result.outcome is HKCaseLedgerOutcome.INVALID
    assert HKCaseLedgerReason.INVALID_RESOLUTION in result.reasons


def test_dled_014_resolved_units_require_exactly_one_primary_use() -> None:
    request = _request()
    invalid = replace(
        request.units[0],
        primary_uses=(HKCasePrimaryUse.NON_PROPOSITIONAL, HKCasePrimaryUse.CONTEXT_EVIDENCE),
    )
    result = _evaluate(replace(request, units=(invalid, *request.units[1:])))
    assert result.outcome is HKCaseLedgerOutcome.INVALID
    assert HKCaseLedgerReason.INVALID_PRIMARY_USE in result.reasons


def test_dled_015_non_propositional_reason_is_required_and_closed() -> None:
    request = _request()
    invalid = replace(request.units[0], non_propositional_reason=None)
    result = _evaluate(replace(request, units=(invalid, *request.units[1:])))
    assert result.outcome is HKCaseLedgerOutcome.INVALID
    assert HKCaseLedgerReason.INVALID_NON_PROPOSITIONAL_REASON in result.reasons


def test_dled_016_treatment_lead_requires_separate_screening_handoff() -> None:
    request = _request()
    treatment = replace(
        request.units[0],
        non_propositional_reason=HKCaseNonPropositionalReason.TREATMENT_ONLY_REASONING,
        citation_or_treatment_lead=True,
        screening_handoff_ids=("treatment_handoff_1",),
    )
    result = _evaluate(replace(request, units=(treatment, *request.units[1:])))
    assert result.outcome is HKCaseLedgerOutcome.STRUCTURE_VALID
    assert result.screening_handoff_count == 1


def test_dled_017_complete_with_accepted_proposition_is_explicit() -> None:
    result = _evaluate(replace(_request(), semantic_resolution_complete=True))
    assert result.outcome is HKCaseLedgerOutcome.COMPLETE_WITH_PROPOSITIONS
    assert result.accepted_candidate_count == 1
    assert result.proposition_evidence_unit_count == 1
    assert result.search_records_created == 0


def test_dled_018_complete_zero_requires_no_proposition_evidence_and_handoffs() -> None:
    request = _request()
    units = tuple(
        replace(
            item,
            primary_uses=(HKCasePrimaryUse.NON_PROPOSITIONAL,),
            evidence_roles=(),
            non_propositional_reason=(
                HKCaseNonPropositionalReason.TREATMENT_ONLY_REASONING
                if item.unit_id == "unit_2"
                else HKCaseNonPropositionalReason.SOURCE_SCAFFOLDING
            ),
            citation_or_treatment_lead=item.unit_id == "unit_2",
            screening_handoff_ids=("treatment_handoff_1",) if item.unit_id == "unit_2" else (),
        )
        for item in request.units
    )
    result = _evaluate(
        replace(request, semantic_resolution_complete=True, units=units, candidates=())
    )
    assert result.outcome is HKCaseLedgerOutcome.COMPLETE_NO_PROPOSITION
    assert result.accepted_candidate_count == 0
    assert result.search_records_created == 0


def test_dled_019_material_quarantine_is_not_complete() -> None:
    request = _request()
    quarantined = replace(
        request.units[1],
        resolutions=(HKCaseUnitResolution.QUARANTINED,),
        primary_uses=(),
        evidence_roles=(),
    )
    candidate = replace(request.candidates[0], outcome=HKCaseCandidateOutcome.QUARANTINED)
    result = _evaluate(
        replace(
            request,
            semantic_resolution_complete=True,
            units=(request.units[0], quarantined, request.units[2]),
            candidates=(candidate,),
        )
    )
    assert result.outcome is HKCaseLedgerOutcome.ACCOUNTED_WITH_QUARANTINE
    assert not result.release_eligible


def test_dled_020_absent_support_is_blocked_and_bad_arithmetic_is_invalid() -> None:
    blocked = _evaluate(replace(_request(), source_support_available=False))
    assert blocked.outcome is HKCaseLedgerOutcome.BLOCKED
    assert blocked.reasons == (HKCaseLedgerReason.SOURCE_SUPPORT_ABSENT,)
    request = _request()
    invalid_segment = replace(request.segments[0], primary_unit_ids=("unit_1", "unit_2"))
    invalid = _evaluate(replace(request, segments=(invalid_segment,)))
    assert invalid.outcome is HKCaseLedgerOutcome.INVALID
    assert HKCaseLedgerReason.MISSING_PRIMARY_COVERAGE in invalid.reasons


def test_request_document_round_trips_and_rejects_unknown_fields() -> None:
    document = hk_case_coverage_ledger_request_document(_request())
    assert hk_case_coverage_ledger_request_from_document(document) == _request()
    document["unknown"] = True
    with pytest.raises(HKCaseLedgerError):
        hk_case_coverage_ledger_request_from_document(document)


def test_frozen_package_executes_all_twenty_ledger_cases_from_ordinary_facts() -> None:
    schema_root = PACKAGE_ROOT / "contracts/schemas"
    case_schema = _json(schema_root / "hk-case-coverage-ledger-case.schema.json")
    result_schema = _json(schema_root / "hk-case-coverage-ledger-case-result.schema.json")
    Draft202012Validator.check_schema(case_schema)
    Draft202012Validator.check_schema(result_schema)
    case_validator = _validator(case_schema)
    result_validator = _validator(result_schema)
    fixture_paths = sorted((PACKAGE_ROOT / "fixtures/deterministic/coverage-ledger").glob("*.json"))
    assert len(fixture_paths) == 20
    observed_outcomes: set[str] = set()
    for fixture_path in fixture_paths:
        fixture = _json(fixture_path)
        expected = _json(PACKAGE_ROOT / f"expected/coverage-ledger/{fixture_path.name}")
        case_validator.validate(fixture)
        result_validator.validate(expected)
        fixture_variants = _json_object_list(fixture["variants"])
        expected_variants = _json_object_list(expected["variants"])
        assert [item["variant_id"] for item in fixture_variants] == [
            item["variant_id"] for item in expected_variants
        ]
        for input_variant, output_variant in zip(fixture_variants, expected_variants, strict=True):
            request = hk_case_coverage_ledger_request_from_document(input_variant["request"])
            result = hk_case_coverage_ledger_result_document(
                evaluate_hk_case_coverage_ledger(request)
            )
            assert result == output_variant["result"]
            observed_outcomes.add(_json_text(result["outcome"]))
            assert result["search_records_created"] == 0
            assert result["release_eligible"] is False
            assert result["external_effects"] == "NONE"
    assert observed_outcomes == {
        "ACCOUNTED_WITH_QUARANTINE",
        "BLOCKED",
        "COMPLETE_NO_PROPOSITION",
        "COMPLETE_WITH_PROPOSITIONS",
        "INVALID",
        "STRUCTURE_VALID",
    }


def test_frozen_ledger_catalogue_has_exact_ids_cells_pairs_and_paths() -> None:
    catalogue = _json(PACKAGE_ROOT / "catalogues/coverage-ledger-cases.json")
    entries = _json_object_list(catalogue["entries"])
    assert catalogue["case_count"] == catalogue["coverage_cell_count"] == len(entries) == 20
    assert [item["case_id"] for item in entries] == [
        f"HKCASE-PROP-DET-LED-{number:03d}" for number in range(1, 21)
    ]
    assert [item["coverage_cell_id"] for item in entries] == [
        f"HKCASE-PROP-COV-DLED-{number:03d}" for number in range(1, 21)
    ]
    pairs = {
        _json_text(membership["pair_id"]): _json_text(membership["role"])
        for entry in entries
        for membership in _json_object_list(entry["pair_memberships"])
    }
    assert pairs == {
        "HKCASE-PROP-PAIR-020": "NEAR_MISS",
        "HKCASE-PROP-PAIR-021": "NEAR_MISS",
    }
    pair_members = [
        (membership["pair_id"], membership["role"], entry["case_id"])
        for entry in entries
        for membership in _json_object_list(entry["pair_memberships"])
    ]
    assert pair_members == [
        ("HKCASE-PROP-PAIR-020", "POSITIVE", "HKCASE-PROP-DET-LED-005"),
        ("HKCASE-PROP-PAIR-020", "NEAR_MISS", "HKCASE-PROP-DET-LED-006"),
        ("HKCASE-PROP-PAIR-021", "POSITIVE", "HKCASE-PROP-DET-LED-009"),
        ("HKCASE-PROP-PAIR-021", "NEAR_MISS", "HKCASE-PROP-DET-LED-010"),
    ]
    assert catalogue["checkpoint_complete"] is True
    assert catalogue["full_proposition_suite_complete"] is False
    assert catalogue["real_source_evidence"] is False
    assert catalogue["activation_authorized"] is False
