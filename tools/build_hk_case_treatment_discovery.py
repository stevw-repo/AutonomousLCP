"""Build the first frozen Hong Kong Case treatment-discovery checkpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
    HK_CASE_TREATMENT_DISCOVERY_RULE_ID,
    HKCaseTreatmentDiscoveryCorrectionChange,
    HKCaseTreatmentDiscoveryDisposition,
    HKCaseTreatmentDiscoveryEvaluationRequest,
    HKCaseTreatmentDiscoveryIdentityState,
    HKCaseTreatmentDiscoveryLanguage,
    HKCaseTreatmentDiscoveryLeadKind,
    HKCaseTreatmentDiscoveryObservation,
    HKCaseTreatmentDiscoveryObservedCandidate,
    HKCaseTreatmentDiscoveryObservedLead,
    HKCaseTreatmentDiscoveryOpinionRole,
    HKCaseTreatmentDiscoveryReference,
    HKCaseTreatmentDiscoveryReferenceCandidate,
    HKCaseTreatmentDiscoveryReferenceLead,
    evaluate_hk_case_treatment_discovery,
    hk_case_treatment_discovery_observation_document,
    hk_case_treatment_discovery_reference_document,
    hk_case_treatment_discovery_result_document,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_cases_package"


@dataclass(frozen=True, slots=True)
class _OpinionSpec:
    role: HKCaseTreatmentDiscoveryOpinionRole
    segment_texts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _LeadSpec:
    opinion_index: int
    segment_index: int
    kind: HKCaseTreatmentDiscoveryLeadKind
    identity_state: HKCaseTreatmentDiscoveryIdentityState
    material: bool
    identity_key: str | None = None


@dataclass(frozen=True, slots=True)
class _CandidateSpec:
    lead_index: int
    passage_segment_indexes: tuple[int, ...]
    context_segment_indexes: tuple[int, ...]
    language: HKCaseTreatmentDiscoveryLanguage
    correction_change: HKCaseTreatmentDiscoveryCorrectionChange = (
        HKCaseTreatmentDiscoveryCorrectionChange.NONE
    )


@dataclass(frozen=True, slots=True)
class _DiscoverySpec:
    scenario: str
    language: HKCaseTreatmentDiscoveryLanguage
    opinions: tuple[_OpinionSpec, ...]
    leads: tuple[_LeadSpec, ...]
    candidates: tuple[_CandidateSpec, ...]
    proposition_count: int = 1
    missing_required_segment_ids: tuple[str, ...] = ()
    coverage_gap_ids: tuple[str, ...] = ()


_M = HKCaseTreatmentDiscoveryOpinionRole.OPERATIVE_MAJORITY
_D = HKCaseTreatmentDiscoveryOpinionRole.DISSENT
_F = HKCaseTreatmentDiscoveryLeadKind.FORMAL_CITATION
_I = HKCaseTreatmentDiscoveryLeadKind.IMPLICIT_REFERENCE
_R = HKCaseTreatmentDiscoveryIdentityState.RESOLVED
_A = HKCaseTreatmentDiscoveryIdentityState.AMBIGUOUS
_U = HKCaseTreatmentDiscoveryIdentityState.UNMATCHED
_N = HKCaseTreatmentDiscoveryCorrectionChange.NONE
_PAIR_POSITIVE_CASE_NUMBER = 8


_SPECS = (
    _DiscoverySpec(
        "Short operative judgment with no earlier-authority reference",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (_OpinionSpec(_M, ("The appeal is dismissed for the reasons stated.",)),),
        (),
        (),
    ),
    _DiscoverySpec(
        "Several bare formal citations without treatment-bearing reasoning",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (
            _OpinionSpec(
                _M,
                (
                    "Counsel cited Alpha v Beta [2001] 1 HKLRD 1.",
                    "Reference was also made to Gamma v Delta [2002] 2 HKCFAR 2.",
                    "The chronology appears in Epsilon v Zeta [2003] 3 HKLRD 3.",
                ),
            ),
        ),
        (
            _LeadSpec(1, 1, _F, _R, material=False),
            _LeadSpec(1, 2, _F, _R, material=False),
            _LeadSpec(1, 3, _F, _R, material=False),
        ),
        (),
    ),
    _DiscoverySpec(
        "Formal citation accompanied by express material treatment",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (_OpinionSpec(_M, ("We follow Alpha v Beta [2001] 1 HKLRD 1 on this issue.",)),),
        (_LeadSpec(1, 1, _F, _R, material=True),),
        (_CandidateSpec(1, (1,), (1,), HKCaseTreatmentDiscoveryLanguage.ENGLISH),),
    ),
    _DiscoverySpec(
        "Unusual implicit material reference without a conventional citation",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (_OpinionSpec(_M, ("The earlier harbour-master ruling cannot survive this reasoning.",)),),
        (_LeadSpec(1, 1, _I, _A, material=True),),
        (_CandidateSpec(1, (1,), (1,), HKCaseTreatmentDiscoveryLanguage.ENGLISH),),
    ),
    _DiscoverySpec(
        "Many cited decisions with only one materially treated",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (
            _OpinionSpec(
                _M,
                (
                    "Alpha v Beta [2001] 1 HKLRD 1 records the procedural history.",
                    "We respectfully decline to follow Gamma v Delta [2002] 2 HKCFAR 2.",
                    "Epsilon v Zeta [2003] 3 HKLRD 3 was mentioned by counsel.",
                ),
            ),
        ),
        (
            _LeadSpec(1, 1, _F, _R, material=False),
            _LeadSpec(1, 2, _F, _R, material=True),
            _LeadSpec(1, 3, _F, _R, material=False),
        ),
        (_CandidateSpec(2, (2,), (1, 2, 3), HKCaseTreatmentDiscoveryLanguage.ENGLISH),),
    ),
    _DiscoverySpec(
        "Majority and dissent separately discuss the same earlier authority",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (
            _OpinionSpec(_M, ("The majority follows Alpha v Beta [2001] 1 HKLRD 1.",)),
            _OpinionSpec(_D, ("I would distinguish Alpha v Beta [2001] 1 HKLRD 1.",)),
        ),
        (
            _LeadSpec(1, 1, _F, _R, material=True, identity_key="shared_authority"),
            _LeadSpec(2, 2, _F, _R, material=True, identity_key="shared_authority"),
        ),
        (
            _CandidateSpec(1, (1,), (1,), HKCaseTreatmentDiscoveryLanguage.ENGLISH),
            _CandidateSpec(2, (2,), (2,), HKCaseTreatmentDiscoveryLanguage.ENGLISH),
        ),
    ),
    _DiscoverySpec(
        "Zero new proposition output does not suppress outgoing treatment discovery",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (
            _OpinionSpec(
                _M, ("Although no new rule is stated, Alpha v Beta is expressly disapproved.",)
            ),
        ),
        (_LeadSpec(1, 1, _F, _R, material=True),),
        (_CandidateSpec(1, (1,), (1,), HKCaseTreatmentDiscoveryLanguage.ENGLISH),),
        proposition_count=0,
    ),
    _DiscoverySpec(
        "Opinion-aware segments require cross-reference and declared context",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (
            _OpinionSpec(
                _M,
                (
                    "The governing issue is whether the exception in paragraph 42 applies.",
                    "Paragraph 42 of Alpha v Beta confines the exception to urgent cases.",
                    "For those reasons we apply that confined exception here.",
                ),
            ),
        ),
        (_LeadSpec(1, 2, _F, _R, material=True),),
        (_CandidateSpec(1, (2, 3), (1, 2, 3), HKCaseTreatmentDiscoveryLanguage.ENGLISH),),
    ),
    _DiscoverySpec(
        "Required context segment is absent from an otherwise similar judgment packet",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (
            _OpinionSpec(
                _M,
                (
                    "The governing issue is whether the exception applies.",
                    "For those reasons we apply it here.",
                ),
            ),
        ),
        (),
        (),
        missing_required_segment_ids=("segment_missing_context",),
        coverage_gap_ids=("coverage_gap_missing_context",),
    ),
    _DiscoverySpec(
        "Citation words cannot resolve to one registered judgment",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (
            _OpinionSpec(
                _M, ("The court was referred to the two decisions both styled Lee v Chan.",)
            ),
        ),
        (_LeadSpec(1, 1, _F, _U, material=False),),
        (),
    ),
    _DiscoverySpec(
        "Corrected reasons add remove change and preserve treatment candidates",
        HKCaseTreatmentDiscoveryLanguage.ENGLISH,
        (
            _OpinionSpec(
                _M,
                (
                    "The correction newly follows Alpha v Beta.",
                    "The prior criticism of Gamma v Delta has been removed.",
                    "The scope of the treatment of Epsilon v Zeta is changed.",
                    "The application of Eta v Theta remains unchanged.",
                ),
            ),
        ),
        tuple(_LeadSpec(1, number, _F, _R, material=True) for number in range(1, 5)),
        (
            _CandidateSpec(
                1,
                (1,),
                (1,),
                HKCaseTreatmentDiscoveryLanguage.ENGLISH,
                HKCaseTreatmentDiscoveryCorrectionChange.ADDED,
            ),
            _CandidateSpec(
                2,
                (2,),
                (2,),
                HKCaseTreatmentDiscoveryLanguage.ENGLISH,
                HKCaseTreatmentDiscoveryCorrectionChange.REMOVED,
            ),
            _CandidateSpec(
                3,
                (3,),
                (3,),
                HKCaseTreatmentDiscoveryLanguage.ENGLISH,
                HKCaseTreatmentDiscoveryCorrectionChange.CHANGED,
            ),
            _CandidateSpec(
                4,
                (4,),
                (4,),
                HKCaseTreatmentDiscoveryLanguage.ENGLISH,
                HKCaseTreatmentDiscoveryCorrectionChange.UNCHANGED,
            ),
        ),
    ),
    _DiscoverySpec(
        "Complete Traditional Chinese judgment uses ordinary judicial language",
        HKCaseTreatmentDiscoveryLanguage.TRADITIONAL_CHINESE,
        (_OpinionSpec(_M, ("本院不再依循陳訴李案所採納的原則，理由如下。",)),),  # noqa: RUF001
        (_LeadSpec(1, 1, _I, _R, material=True),),
        (_CandidateSpec(1, (1,), (1,), HKCaseTreatmentDiscoveryLanguage.TRADITIONAL_CHINESE),),
    ),
    _DiscoverySpec(
        "Mixed-language opinion combines English citation and Chinese operative reasoning",
        HKCaseTreatmentDiscoveryLanguage.MIXED,
        (_OpinionSpec(_M, ("Alpha v Beta [2001] 1 HKLRD 1", "本院認為該案的限制在本案不適用。")),),
        (_LeadSpec(1, 1, _F, _R, material=True),),
        (_CandidateSpec(1, (1, 2), (1, 2), HKCaseTreatmentDiscoveryLanguage.MIXED),),
    ),
)


def _fingerprint_text(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _segment_id(number: int) -> str:
    return f"segment_{number}"


def _opinion_id(number: int) -> str:
    return f"opinion_{number}"


def _model_input(number: int, spec: _DiscoverySpec) -> dict[str, JsonValue]:
    segments: list[JsonValue] = []
    opinions: list[JsonValue] = []
    source_order = 0
    for opinion_index, opinion in enumerate(spec.opinions, 1):
        opinion_segments: list[JsonValue] = []
        for text in opinion.segment_texts:
            source_order += 1
            segment_id = _segment_id(source_order)
            opinion_segments.append(segment_id)
            segments.append(
                {
                    "segment_id": segment_id,
                    "opinion_id": _opinion_id(opinion_index),
                    "source_order": source_order,
                    "language": spec.language.value,
                    "exact_text": text,
                    "text_fingerprint": _fingerprint_text(text),
                    "range_id": f"range_{source_order}",
                }
            )
        opinions.append(
            {
                "opinion_id": _opinion_id(opinion_index),
                "role": opinion.role.value,
                "segment_ids": opinion_segments,
            }
        )
    return {
        "schema_id": "asklegal.hk-cases.treatment-discovery-model-input",
        "schema_version": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
        "task_family": "TREATMENT_DISCOVERY",
        "execution_id": f"treatment_discovery_execution_{number}",
        "judgment_work_id": f"synthetic_treatment_judgment_{number}",
        "accepted_original_version_id": f"synthetic_treatment_version_{number}",
        "original_language": spec.language.value,
        "opinions": opinions,
        "segments": segments,
        "missing_required_segment_ids": list(spec.missing_required_segment_ids),
        "segment_manifest_complete": not spec.missing_required_segment_ids,
        "source_text_is_evidence_not_instruction": True,
        "external_tools_permitted": False,
        "hidden_reference_included": False,
    }


def _case_documents(
    number: int,
    spec: _DiscoverySpec,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue]]:
    model_input = _model_input(number, spec)
    model_input_fingerprint = fingerprint(checked_json_value(model_input))
    segment_count = sum(len(item.segment_texts) for item in spec.opinions)
    opinion_ids = tuple(_opinion_id(index) for index in range(1, len(spec.opinions) + 1))
    segment_ids = tuple(_segment_id(index) for index in range(1, segment_count + 1))
    reference_leads = tuple(
        HKCaseTreatmentDiscoveryReferenceLead(
            reference_lead_id=f"reference_lead_{index}",
            opinion_id=_opinion_id(lead.opinion_index),
            lead_kind=lead.kind,
            range_ids=(f"range_{lead.segment_index}",),
            identity_state=lead.identity_state,
            resolved_judgment_id=(
                lead.identity_key or f"earlier_judgment_{number}_{index}"
                if lead.identity_state is HKCaseTreatmentDiscoveryIdentityState.RESOLVED
                else None
            ),
            material_candidate_expected=lead.material,
        )
        for index, lead in enumerate(spec.leads, 1)
    )
    reference_candidates = tuple(
        HKCaseTreatmentDiscoveryReferenceCandidate(
            reference_candidate_id=f"reference_candidate_{index}",
            reference_lead_id=f"reference_lead_{candidate.lead_index}",
            opinion_id=reference_leads[candidate.lead_index - 1].opinion_id,
            language=candidate.language,
            passage_range_ids=tuple(f"range_{item}" for item in candidate.passage_segment_indexes),
            context_segment_ids=tuple(
                _segment_id(item) for item in candidate.context_segment_indexes
            ),
            correction_change=candidate.correction_change,
        )
        for index, candidate in enumerate(spec.candidates, 1)
    )
    disposition = (
        HKCaseTreatmentDiscoveryDisposition.INCOMPLETE
        if spec.missing_required_segment_ids
        else HKCaseTreatmentDiscoveryDisposition.COMPLETE
    )
    reference = HKCaseTreatmentDiscoveryReference(
        reference_map_id=f"treatment_discovery_reference_{number}",
        model_input_fingerprint=model_input_fingerprint,
        original_language=spec.language,
        expected_opinion_ids=opinion_ids,
        expected_segment_ids=segment_ids,
        leads=reference_leads,
        candidates=reference_candidates,
        expected_disposition=disposition,
        expected_coverage_gap_ids=spec.coverage_gap_ids,
        expected_judgment_proposition_count=spec.proposition_count,
        correction_comparison_required=any(
            item.correction_change is not _N for item in spec.candidates
        ),
        adjudication_complete=True,
    )
    observed_leads = tuple(
        HKCaseTreatmentDiscoveryObservedLead(
            lead_id=f"lead_{index}",
            mapped_reference_lead_id=lead.reference_lead_id,
            opinion_id=lead.opinion_id,
            lead_kind=lead.lead_kind,
            range_ids=lead.range_ids,
            identity_state=lead.identity_state,
            resolved_judgment_id=lead.resolved_judgment_id,
            material_candidate=lead.material_candidate_expected,
        )
        for index, lead in enumerate(reference_leads, 1)
    )
    observed_candidates = tuple(
        HKCaseTreatmentDiscoveryObservedCandidate(
            candidate_id=f"candidate_{index}",
            mapped_reference_candidate_id=candidate.reference_candidate_id,
            mapped_lead_id=f"lead_{spec.candidates[index - 1].lead_index}",
            opinion_id=candidate.opinion_id,
            language=candidate.language,
            passage_range_ids=candidate.passage_range_ids,
            context_segment_ids=candidate.context_segment_ids,
            correction_change=candidate.correction_change,
        )
        for index, candidate in enumerate(reference_candidates, 1)
    )
    observation = HKCaseTreatmentDiscoveryObservation(
        model_input_fingerprint=model_input_fingerprint,
        workflow_result_fingerprint=_fingerprint_text(f"treatment-discovery-result-{number}"),
        original_language=spec.language,
        examined_opinion_ids=opinion_ids,
        examined_segment_ids=segment_ids,
        leads=observed_leads,
        candidates=observed_candidates,
        disposition=disposition,
        coverage_gap_ids=spec.coverage_gap_ids,
        judgment_proposition_count=spec.proposition_count,
        complete_opinion_ledger=True,
        complete_segment_ledger=not spec.missing_required_segment_ids,
        correction_comparison_complete=reference.correction_comparison_required,
        silence_establishes_no_treatment=False,
        legal_effect_decided=False,
        source_text_treated_as_instruction=False,
        hidden_reference_received_by_workflow=False,
    )
    request = HKCaseTreatmentDiscoveryEvaluationRequest(
        evaluator_fingerprint=_fingerprint_text("treatment-discovery-evaluator-v1"),
        reference=reference,
        observation=observation,
    )
    case_id = f"HKCASE-TREAT-SEM-DIS-{number:03d}"
    pairs: list[JsonValue] = []
    if number in (8, 9):
        pairs.append(
            {
                "pair_id": "HKCASE-TREAT-PAIR-001",
                "role": ("POSITIVE" if number == _PAIR_POSITIVE_CASE_NUMBER else "NEAR_MISS"),
            }
        )
    case: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-cases.treatment-discovery-case",
        "schema_version": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
        "fixture_id": case_id,
        "coverage_cell_id": f"HKCASE-TREAT-COV-SDIS-{number:03d}",
        "pair_memberships": pairs,
        "scenario": spec.scenario,
        "model_facing_input": model_input,
        "reference_path": f"evaluations/treatment-discovery/references/{case_id}.json",
        "observation_path": f"evaluations/treatment-discovery/observations/{case_id}.json",
        "expected_path": f"expected/treatment-discovery/{case_id}.json",
    }
    reference_document = hk_case_treatment_discovery_reference_document(reference)
    observation_document = hk_case_treatment_discovery_observation_document(observation)
    expected: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-cases.treatment-discovery-case-result",
        "schema_version": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
        "fixture_id": case_id,
        "result": hk_case_treatment_discovery_result_document(
            evaluate_hk_case_treatment_discovery(request)
        ),
    }
    return case, reference_document, observation_document, expected


def build_treatment_discovery_cases() -> tuple[
    tuple[dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue]],
    ...,
]:
    """Build every frozen whole-judgment discovery case."""
    return tuple(_case_documents(number, spec) for number, spec in enumerate(_SPECS, 1))


def _closed(required: list[str], properties: dict[str, JsonValue]) -> dict[str, JsonValue]:
    required_values: list[JsonValue] = []
    required_values.extend(required)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required_values,
        "properties": properties,
    }


def _identity_schema() -> dict[str, JsonValue]:
    return {"type": "string", "pattern": "^[a-z][a-z0-9_]{2,95}$"}


def _fingerprint_schema() -> dict[str, JsonValue]:
    return {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}


def _nullable_identity_schema() -> dict[str, JsonValue]:
    return {"oneOf": [_identity_schema(), {"type": "null"}]}


def _reference_lead_schema() -> dict[str, JsonValue]:
    properties: dict[str, JsonValue] = {
        "reference_lead_id": _identity_schema(),
        "opinion_id": _identity_schema(),
        "lead_kind": {"enum": [item.value for item in HKCaseTreatmentDiscoveryLeadKind]},
        "range_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "identity_state": {"enum": [item.value for item in HKCaseTreatmentDiscoveryIdentityState]},
        "resolved_judgment_id": _nullable_identity_schema(),
        "material_candidate_expected": {"type": "boolean"},
    }
    return _closed(list(properties), properties)


def _reference_candidate_schema() -> dict[str, JsonValue]:
    properties: dict[str, JsonValue] = {
        "reference_candidate_id": _identity_schema(),
        "reference_lead_id": _identity_schema(),
        "opinion_id": _identity_schema(),
        "language": {"enum": [item.value for item in HKCaseTreatmentDiscoveryLanguage]},
        "passage_range_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "context_segment_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "correction_change": {
            "enum": [item.value for item in HKCaseTreatmentDiscoveryCorrectionChange]
        },
    }
    return _closed(list(properties), properties)


def _observed_lead_schema() -> dict[str, JsonValue]:
    properties: dict[str, JsonValue] = {
        "lead_id": _identity_schema(),
        "mapped_reference_lead_id": _nullable_identity_schema(),
        "opinion_id": _identity_schema(),
        "lead_kind": {"enum": [item.value for item in HKCaseTreatmentDiscoveryLeadKind]},
        "range_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "identity_state": {"enum": [item.value for item in HKCaseTreatmentDiscoveryIdentityState]},
        "resolved_judgment_id": _nullable_identity_schema(),
        "material_candidate": {"type": "boolean"},
    }
    return _closed(list(properties), properties)


def _observed_candidate_schema() -> dict[str, JsonValue]:
    properties: dict[str, JsonValue] = {
        "candidate_id": _identity_schema(),
        "mapped_reference_candidate_id": _nullable_identity_schema(),
        "mapped_lead_id": _identity_schema(),
        "opinion_id": _identity_schema(),
        "language": {"enum": [item.value for item in HKCaseTreatmentDiscoveryLanguage]},
        "passage_range_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "context_segment_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "correction_change": {
            "enum": [item.value for item in HKCaseTreatmentDiscoveryCorrectionChange]
        },
    }
    return _closed(list(properties), properties)


def build_treatment_discovery_reference_schema() -> dict[str, JsonValue]:
    """Build the strict evaluator-only reference schema."""
    properties: dict[str, JsonValue] = {
        "schema_id": {"const": "asklegal.hk-cases.treatment-discovery-reference"},
        "schema_version": {"const": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION},
        "rule_id": {"const": HK_CASE_TREATMENT_DISCOVERY_RULE_ID},
        "reference_map_id": _identity_schema(),
        "model_input_fingerprint": _fingerprint_schema(),
        "original_language": {"enum": [item.value for item in HKCaseTreatmentDiscoveryLanguage]},
        "expected_opinion_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "expected_segment_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "leads": {"type": "array", "items": _reference_lead_schema()},
        "candidates": {"type": "array", "items": _reference_candidate_schema()},
        "expected_disposition": {
            "enum": [item.value for item in HKCaseTreatmentDiscoveryDisposition]
        },
        "expected_coverage_gap_ids": {"type": "array", "items": _identity_schema()},
        "expected_judgment_proposition_count": {"type": "integer", "minimum": 0},
        "correction_comparison_required": {"type": "boolean"},
        "adjudication_complete": {"type": "boolean"},
    }
    return _closed(list(properties), properties)


def build_treatment_discovery_observation_schema() -> dict[str, JsonValue]:
    """Build the strict post-run observation schema."""
    properties: dict[str, JsonValue] = {
        "schema_id": {"const": "asklegal.hk-cases.treatment-discovery-observation"},
        "schema_version": {"const": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION},
        "rule_id": {"const": HK_CASE_TREATMENT_DISCOVERY_RULE_ID},
        "model_input_fingerprint": _fingerprint_schema(),
        "workflow_result_fingerprint": _fingerprint_schema(),
        "original_language": {"enum": [item.value for item in HKCaseTreatmentDiscoveryLanguage]},
        "examined_opinion_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "examined_segment_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        "leads": {"type": "array", "items": _observed_lead_schema()},
        "candidates": {"type": "array", "items": _observed_candidate_schema()},
        "disposition": {"enum": [item.value for item in HKCaseTreatmentDiscoveryDisposition]},
        "coverage_gap_ids": {"type": "array", "items": _identity_schema()},
        "judgment_proposition_count": {"type": "integer", "minimum": 0},
        "complete_opinion_ledger": {"type": "boolean"},
        "complete_segment_ledger": {"type": "boolean"},
        "correction_comparison_complete": {"type": "boolean"},
        "silence_establishes_no_treatment": {"const": False},
        "legal_effect_decided": {"const": False},
        "source_text_treated_as_instruction": {"const": False},
        "hidden_reference_received_by_workflow": {"const": False},
    }
    return _closed(list(properties), properties)


def build_treatment_discovery_model_input_schema() -> dict[str, JsonValue]:
    """Build the answer-free model-facing packet schema."""
    opinion = _closed(
        ["opinion_id", "role", "segment_ids"],
        {
            "opinion_id": _identity_schema(),
            "role": {"enum": [item.value for item in HKCaseTreatmentDiscoveryOpinionRole]},
            "segment_ids": {"type": "array", "minItems": 1, "items": _identity_schema()},
        },
    )
    segment = _closed(
        [
            "segment_id",
            "opinion_id",
            "source_order",
            "language",
            "exact_text",
            "text_fingerprint",
            "range_id",
        ],
        {
            "segment_id": _identity_schema(),
            "opinion_id": _identity_schema(),
            "source_order": {"type": "integer", "minimum": 1},
            "language": {"enum": [item.value for item in HKCaseTreatmentDiscoveryLanguage]},
            "exact_text": {"type": "string", "minLength": 1},
            "text_fingerprint": _fingerprint_schema(),
            "range_id": _identity_schema(),
        },
    )
    properties: dict[str, JsonValue] = {
        "schema_id": {"const": "asklegal.hk-cases.treatment-discovery-model-input"},
        "schema_version": {"const": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION},
        "task_family": {"const": "TREATMENT_DISCOVERY"},
        "execution_id": _identity_schema(),
        "judgment_work_id": _identity_schema(),
        "accepted_original_version_id": _identity_schema(),
        "original_language": {"enum": [item.value for item in HKCaseTreatmentDiscoveryLanguage]},
        "opinions": {"type": "array", "minItems": 1, "items": opinion},
        "segments": {"type": "array", "minItems": 1, "items": segment},
        "missing_required_segment_ids": {"type": "array", "items": _identity_schema()},
        "segment_manifest_complete": {"type": "boolean"},
        "source_text_is_evidence_not_instruction": {"const": True},
        "external_tools_permitted": {"const": False},
        "hidden_reference_included": {"const": False},
    }
    schema = _closed(list(properties), properties)
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hk-case-treatment-discovery-model-input.schema.json",
        }
    )
    return schema


def build_treatment_discovery_evaluation_request_schema() -> dict[str, JsonValue]:
    """Build the closed evaluator request schema."""
    properties: dict[str, JsonValue] = {
        "schema_id": {"const": "asklegal.hk-cases.treatment-discovery-evaluation-request"},
        "schema_version": {"const": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION},
        "rule_id": {"const": HK_CASE_TREATMENT_DISCOVERY_RULE_ID},
        "evaluator_fingerprint": _fingerprint_schema(),
        "reference": build_treatment_discovery_reference_schema(),
        "observation": build_treatment_discovery_observation_schema(),
    }
    schema = _closed(list(properties), properties)
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hk-case-treatment-discovery-evaluation-request.schema.json",
        }
    )
    return schema


def build_treatment_discovery_result_schema() -> dict[str, JsonValue]:
    """Build the effect-free evaluator result schema."""
    properties: dict[str, JsonValue] = {
        "schema_id": {"const": "asklegal.hk-cases.treatment-discovery-evaluation-result"},
        "schema_version": {"const": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION},
        "rule_id": {"const": HK_CASE_TREATMENT_DISCOVERY_RULE_ID},
        "request_fingerprint": _fingerprint_schema(),
        "reference_map_fingerprint": _fingerprint_schema(),
        "outcome": {"enum": ["EVALUATOR_BLOCKED", "FAIL", "PASS"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "expected_lead_count": {"type": "integer", "minimum": 0},
        "observed_lead_count": {"type": "integer", "minimum": 0},
        "matched_lead_count": {"type": "integer", "minimum": 0},
        "expected_candidate_count": {"type": "integer", "minimum": 0},
        "observed_candidate_count": {"type": "integer", "minimum": 0},
        "matched_candidate_count": {"type": "integer", "minimum": 0},
        "examined_opinion_count": {"type": "integer", "minimum": 0},
        "examined_segment_count": {"type": "integer", "minimum": 0},
        "provider_calls_authorized": {"const": 0},
        "treatment_relationships_created": {"const": 0},
        "legal_effects_decided": {"const": 0},
        "search_records_created": {"const": 0},
        "release_eligible": {"const": False},
        "external_effects": {"const": "NONE"},
    }
    schema = _closed(list(properties), properties)
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hk-case-treatment-discovery-result.schema.json",
        }
    )
    return schema


def build_treatment_discovery_case_schema() -> dict[str, JsonValue]:
    """Build the strict package case schema."""
    membership = _closed(
        ["pair_id", "role"],
        {
            "pair_id": {"const": "HKCASE-TREAT-PAIR-001"},
            "role": {"enum": ["NEAR_MISS", "POSITIVE"]},
        },
    )
    properties: dict[str, JsonValue] = {
        "schema_id": {"const": "asklegal.hk-cases.treatment-discovery-case"},
        "schema_version": {"const": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION},
        "fixture_id": {"type": "string", "pattern": "^HKCASE-TREAT-SEM-DIS-[0-9]{3}$"},
        "coverage_cell_id": {"type": "string", "pattern": "^HKCASE-TREAT-COV-SDIS-[0-9]{3}$"},
        "pair_memberships": {"type": "array", "items": membership},
        "scenario": {"type": "string", "minLength": 1},
        "model_facing_input": build_treatment_discovery_model_input_schema(),
        "reference_path": {"type": "string", "minLength": 1},
        "observation_path": {"type": "string", "minLength": 1},
        "expected_path": {"type": "string", "minLength": 1},
    }
    schema = _closed(list(properties), properties)
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hk-case-treatment-discovery-case.schema.json",
        }
    )
    return schema


def build_treatment_discovery_case_result_schema() -> dict[str, JsonValue]:
    """Build the strict expected-case result schema."""
    properties: dict[str, JsonValue] = {
        "schema_id": {"const": "asklegal.hk-cases.treatment-discovery-case-result"},
        "schema_version": {"const": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION},
        "fixture_id": {"type": "string", "pattern": "^HKCASE-TREAT-SEM-DIS-[0-9]{3}$"},
        "result": build_treatment_discovery_result_schema(),
    }
    schema = _closed(list(properties), properties)
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hk-case-treatment-discovery-case-result.schema.json",
        }
    )
    return schema


def _raw(document: dict[str, JsonValue]) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def build_treatment_discovery_catalogue(
    cases: tuple[
        tuple[
            dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue]
        ],
        ...,
    ],
) -> dict[str, JsonValue]:
    """Build the exact 13-case discovery inventory and its paired boundary."""
    entries: list[JsonValue] = []
    for case, reference, observation, expected in cases:
        case_id = str(case["fixture_id"])
        paths = (
            f"fixtures/semantic/treatment-discovery/{case_id}.json",
            f"evaluations/treatment-discovery/references/{case_id}.json",
            f"evaluations/treatment-discovery/observations/{case_id}.json",
            f"expected/treatment-discovery/{case_id}.json",
        )
        entries.append(
            {
                "case_id": case_id,
                "coverage_cell_id": case["coverage_cell_id"],
                "pair_memberships": case["pair_memberships"],
                "artifacts": [
                    {"path": path, "fingerprint": f"sha256:{sha256(_raw(document)).hexdigest()}"}
                    for path, document in zip(
                        paths, (case, reference, observation, expected), strict=True
                    )
                ],
            }
        )
    return {
        "schema_id": "asklegal.hk-cases.treatment-discovery-catalogue",
        "schema_version": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
        "catalogue_id": "hk-case-treatment-semantic-discovery-initial",
        "status": "FROZEN",
        "case_count": 13,
        "coverage_cell_count": 13,
        "pair_ids": ["HKCASE-TREAT-PAIR-001"],
        "complete_pair_ids": ["HKCASE-TREAT-PAIR-001"],
        "entries": entries,
        "frozen_treatment_case_count": 155,
        "executed_treatment_case_count": 13,
        "remaining_treatment_case_count": 142,
        "frozen_treatment_semantic_case_count": 53,
        "executed_treatment_semantic_case_count": 13,
        "remaining_treatment_semantic_case_count": 40,
        "provider_calls_authorized": 0,
        "treatment_relationships_created": 0,
        "legal_effects_decided": 0,
        "real_source_evidence": False,
        "activation_authorized": False,
        "external_effects": "NONE",
    }


def build_treatment_discovery_rule() -> dict[str, JsonValue]:
    """Declare the exact effect-free authority of the discovery evaluator."""
    return {
        "rule_id": HK_CASE_TREATMENT_DISCOVERY_RULE_ID,
        "contract_version": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
        "direct_case_count": 13,
        "coverage_cell_count": 13,
        "direct_high_risk_pair_ids": ["HKCASE-TREAT-PAIR-001"],
        "complete_pair_ids": ["HKCASE-TREAT-PAIR-001"],
        "model_facing_reference_fields": [],
        "case_id_answer_switching_forbidden": True,
        "silence_proves_no_treatment": False,
        "legal_effect_authority": False,
        "provider_calls_authorized": 0,
        "treatment_relationships_created": 0,
        "search_records_created": 0,
        "release_eligible": False,
        "real_source_evidence": False,
        "activation_authorized": False,
        "external_effects": "NONE",
    }


def _write_json(path: Path, document: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_raw(document))


def write_treatment_discovery_checkpoint() -> None:
    """Regenerate all 13 frozen treatment-discovery artifacts."""
    cases = build_treatment_discovery_cases()
    for case, reference, observation, expected in cases:
        case_id = str(case["fixture_id"])
        _write_json(PACKAGE_ROOT / f"fixtures/semantic/treatment-discovery/{case_id}.json", case)
        _write_json(
            PACKAGE_ROOT / f"evaluations/treatment-discovery/references/{case_id}.json", reference
        )
        _write_json(
            PACKAGE_ROOT / f"evaluations/treatment-discovery/observations/{case_id}.json",
            observation,
        )
        _write_json(PACKAGE_ROOT / f"expected/treatment-discovery/{case_id}.json", expected)
    schema_root = PACKAGE_ROOT / "contracts/schemas"
    schemas = {
        "hk-case-treatment-discovery-model-input.schema.json": (
            build_treatment_discovery_model_input_schema()
        ),
        "hk-case-treatment-discovery-evaluation-request.schema.json": (
            build_treatment_discovery_evaluation_request_schema()
        ),
        "hk-case-treatment-discovery-result.schema.json": build_treatment_discovery_result_schema(),
        "hk-case-treatment-discovery-case.schema.json": build_treatment_discovery_case_schema(),
        "hk-case-treatment-discovery-case-result.schema.json": (
            build_treatment_discovery_case_result_schema()
        ),
    }
    for name, schema in schemas.items():
        _write_json(schema_root / name, schema)
    _write_json(
        PACKAGE_ROOT / "catalogues/treatment-discovery-cases.json",
        build_treatment_discovery_catalogue(cases),
    )
    _write_json(
        PACKAGE_ROOT / "rules/HKCASE-TREAT-SEM-DISCOVERY-EVALUATOR-001.json",
        build_treatment_discovery_rule(),
    )
