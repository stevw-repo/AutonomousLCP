"""Effect-free evaluator for Hong Kong whole-judgment treatment discovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION = "1.0.0"
HK_CASE_TREATMENT_DISCOVERY_RULE_ID = "HKCASE-TREAT-SEM-DISCOVERY-EVALUATOR-001"

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_IDENTITY_PATTERN = r"[a-z][a-z0-9_]{2,95}"


class HKCaseTreatmentDiscoveryErrorCode(StrEnum):
    """Closed malformed evaluator-input failures."""

    CONTRACT = "HK_CASE_TREATMENT_DISCOVERY_CONTRACT_INVALID"
    FINGERPRINT = "HK_CASE_TREATMENT_DISCOVERY_FINGERPRINT_INVALID"
    IDENTITY = "HK_CASE_TREATMENT_DISCOVERY_IDENTITY_INVALID"


class HKCaseTreatmentDiscoveryError(ValueError):
    """One strict treatment-discovery contract failure."""

    code: HKCaseTreatmentDiscoveryErrorCode

    def __init__(self, code: HKCaseTreatmentDiscoveryErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKCaseTreatmentDiscoveryLanguage(StrEnum):
    """Accepted original-language forms."""

    ENGLISH = "ENGLISH"
    MIXED = "MIXED"
    TRADITIONAL_CHINESE = "TRADITIONAL_CHINESE"


class HKCaseTreatmentDiscoveryOpinionRole(StrEnum):
    """Opinion roles relevant to the first frozen discovery checkpoint."""

    DISSENT = "DISSENT"
    OPERATIVE_MAJORITY = "OPERATIVE_MAJORITY"


class HKCaseTreatmentDiscoveryLeadKind(StrEnum):
    """How a possible earlier-authority lead was found."""

    FORMAL_CITATION = "FORMAL_CITATION"
    IMPLICIT_REFERENCE = "IMPLICIT_REFERENCE"


class HKCaseTreatmentDiscoveryIdentityState(StrEnum):
    """Deterministically supplied identity-resolution state."""

    AMBIGUOUS = "AMBIGUOUS"
    RESOLVED = "RESOLVED"
    UNMATCHED = "UNMATCHED"


class HKCaseTreatmentDiscoveryCorrectionChange(StrEnum):
    """Inventory-only comparison with a prior Official Version."""

    ADDED = "ADDED"
    CHANGED = "CHANGED"
    NONE = "NONE"
    REMOVED = "REMOVED"
    UNCHANGED = "UNCHANGED"


class HKCaseTreatmentDiscoveryDisposition(StrEnum):
    """Whole-judgment discovery completeness, not legal effect."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class HKCaseTreatmentDiscoveryOutcome(StrEnum):
    """Deterministic evaluator outcomes."""

    EVALUATOR_BLOCKED = "EVALUATOR_BLOCKED"
    FAIL = "FAIL"
    PASS = "PASS"


class HKCaseTreatmentDiscoveryReason(StrEnum):
    """Closed evaluator reasons."""

    CANDIDATE_INVENTORY_MISMATCH = "CANDIDATE_INVENTORY_MISMATCH"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    CORRECTION_COMPARISON_MISMATCH = "CORRECTION_COMPARISON_MISMATCH"
    DISPOSITION_MISMATCH = "DISPOSITION_MISMATCH"
    EVALUATION_LEAKAGE = "EVALUATION_LEAKAGE"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    FORBIDDEN_CONCLUSION = "FORBIDDEN_CONCLUSION"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
    LEAD_INVENTORY_MISMATCH = "LEAD_INVENTORY_MISMATCH"
    OBSERVATION_BINDING_INVALID = "OBSERVATION_BINDING_INVALID"
    OPINION_ACCOUNTING_MISMATCH = "OPINION_ACCOUNTING_MISMATCH"
    OPINION_ATTRIBUTION_MISMATCH = "OPINION_ATTRIBUTION_MISMATCH"
    PASS = "PASS"
    PROPOSITION_INDEPENDENCE_MISMATCH = "PROPOSITION_INDEPENDENCE_MISMATCH"
    REFERENCE_BLOCKED = "REFERENCE_BLOCKED"
    REFERENCE_INVALID = "REFERENCE_INVALID"
    SEGMENT_ACCOUNTING_MISMATCH = "SEGMENT_ACCOUNTING_MISMATCH"


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentDiscoveryReferenceLead:
    """One evaluator-only expected earlier-authority lead."""

    reference_lead_id: str
    opinion_id: str
    lead_kind: HKCaseTreatmentDiscoveryLeadKind
    range_ids: tuple[str, ...]
    identity_state: HKCaseTreatmentDiscoveryIdentityState
    resolved_judgment_id: str | None
    material_candidate_expected: bool


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentDiscoveryReferenceCandidate:
    """One evaluator-only expected treatment candidate."""

    reference_candidate_id: str
    reference_lead_id: str
    opinion_id: str
    language: HKCaseTreatmentDiscoveryLanguage
    passage_range_ids: tuple[str, ...]
    context_segment_ids: tuple[str, ...]
    correction_change: HKCaseTreatmentDiscoveryCorrectionChange


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentDiscoveryReference:
    """Human-adjudicated source-neutral truth for one discovery case."""

    reference_map_id: str
    model_input_fingerprint: str
    original_language: HKCaseTreatmentDiscoveryLanguage
    expected_opinion_ids: tuple[str, ...]
    expected_segment_ids: tuple[str, ...]
    leads: tuple[HKCaseTreatmentDiscoveryReferenceLead, ...]
    candidates: tuple[HKCaseTreatmentDiscoveryReferenceCandidate, ...]
    expected_disposition: HKCaseTreatmentDiscoveryDisposition
    expected_coverage_gap_ids: tuple[str, ...]
    expected_judgment_proposition_count: int
    correction_comparison_required: bool
    adjudication_complete: bool


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentDiscoveryObservedLead:
    """One workflow lead reduced to evaluator-visible facts."""

    lead_id: str
    mapped_reference_lead_id: str | None
    opinion_id: str
    lead_kind: HKCaseTreatmentDiscoveryLeadKind
    range_ids: tuple[str, ...]
    identity_state: HKCaseTreatmentDiscoveryIdentityState
    resolved_judgment_id: str | None
    material_candidate: bool


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentDiscoveryObservedCandidate:
    """One workflow candidate reduced to evaluator-visible facts."""

    candidate_id: str
    mapped_reference_candidate_id: str | None
    mapped_lead_id: str
    opinion_id: str
    language: HKCaseTreatmentDiscoveryLanguage
    passage_range_ids: tuple[str, ...]
    context_segment_ids: tuple[str, ...]
    correction_change: HKCaseTreatmentDiscoveryCorrectionChange


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentDiscoveryObservation:
    """One post-run whole-judgment discovery observation."""

    model_input_fingerprint: str
    workflow_result_fingerprint: str
    original_language: HKCaseTreatmentDiscoveryLanguage
    examined_opinion_ids: tuple[str, ...]
    examined_segment_ids: tuple[str, ...]
    leads: tuple[HKCaseTreatmentDiscoveryObservedLead, ...]
    candidates: tuple[HKCaseTreatmentDiscoveryObservedCandidate, ...]
    disposition: HKCaseTreatmentDiscoveryDisposition
    coverage_gap_ids: tuple[str, ...]
    judgment_proposition_count: int
    complete_opinion_ledger: bool
    complete_segment_ledger: bool
    correction_comparison_complete: bool
    silence_establishes_no_treatment: bool
    legal_effect_decided: bool
    source_text_treated_as_instruction: bool
    hidden_reference_received_by_workflow: bool


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentDiscoveryEvaluationRequest:
    """One evaluator-only reference and one post-run observation."""

    evaluator_fingerprint: str
    reference: HKCaseTreatmentDiscoveryReference
    observation: HKCaseTreatmentDiscoveryObservation


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentDiscoveryEvaluationResult:
    """One effect-free discovery comparison."""

    request_fingerprint: str
    reference_map_fingerprint: str
    outcome: HKCaseTreatmentDiscoveryOutcome
    reasons: tuple[HKCaseTreatmentDiscoveryReason, ...]
    expected_lead_count: int
    observed_lead_count: int
    matched_lead_count: int
    expected_candidate_count: int
    observed_candidate_count: int
    matched_candidate_count: int
    examined_opinion_count: int
    examined_segment_count: int
    provider_calls_authorized: int
    treatment_relationships_created: int
    legal_effects_decided: int
    search_records_created: int
    release_eligible: bool
    external_effects: str


def evaluate_hk_case_treatment_discovery(
    request: HKCaseTreatmentDiscoveryEvaluationRequest,
) -> HKCaseTreatmentDiscoveryEvaluationResult:
    """Compare discovery facts without case identity, legal effect, or side effects."""
    request_fingerprint = fingerprint(
        checked_json_value(hk_case_treatment_discovery_evaluation_request_document(request))
    )
    reference_fingerprint = fingerprint(
        checked_json_value(hk_case_treatment_discovery_reference_document(request.reference))
    )
    reasons = _reference_reasons(request.reference) | _observation_reasons(request)
    if HKCaseTreatmentDiscoveryReason.REFERENCE_BLOCKED in reasons:
        outcome = HKCaseTreatmentDiscoveryOutcome.EVALUATOR_BLOCKED
    elif reasons:
        outcome = HKCaseTreatmentDiscoveryOutcome.FAIL
    else:
        outcome = HKCaseTreatmentDiscoveryOutcome.PASS
        reasons = {HKCaseTreatmentDiscoveryReason.PASS}
    return HKCaseTreatmentDiscoveryEvaluationResult(
        request_fingerprint=request_fingerprint,
        reference_map_fingerprint=reference_fingerprint,
        outcome=outcome,
        reasons=tuple(sorted(reasons, key=lambda item: item.value)),
        expected_lead_count=len(request.reference.leads),
        observed_lead_count=len(request.observation.leads),
        matched_lead_count=_matched_lead_count(request),
        expected_candidate_count=len(request.reference.candidates),
        observed_candidate_count=len(request.observation.candidates),
        matched_candidate_count=_matched_candidate_count(request),
        examined_opinion_count=len(request.observation.examined_opinion_ids),
        examined_segment_count=len(request.observation.examined_segment_ids),
        provider_calls_authorized=0,
        treatment_relationships_created=0,
        legal_effects_decided=0,
        search_records_created=0,
        release_eligible=False,
        external_effects="NONE",
    )


def _reference_reasons(
    reference: HKCaseTreatmentDiscoveryReference,
) -> set[HKCaseTreatmentDiscoveryReason]:
    lead_ids = tuple(item.reference_lead_id for item in reference.leads)
    candidate_ids = tuple(item.reference_candidate_id for item in reference.candidates)
    candidate_leads = tuple(item.reference_lead_id for item in reference.candidates)
    invalid_identity = any(
        (item.identity_state is HKCaseTreatmentDiscoveryIdentityState.RESOLVED)
        != (item.resolved_judgment_id is not None)
        for item in reference.leads
    )
    invalid_candidate = any(
        not item.passage_range_ids
        or not item.context_segment_ids
        or item.reference_lead_id not in lead_ids
        for item in reference.candidates
    )
    invalid_correction = reference.correction_comparison_required != any(
        item.correction_change is not HKCaseTreatmentDiscoveryCorrectionChange.NONE
        for item in reference.candidates
    )
    reasons: set[HKCaseTreatmentDiscoveryReason] = set()
    if (
        _duplicates(reference.expected_opinion_ids)
        or _duplicates(reference.expected_segment_ids)
        or _duplicates(lead_ids)
        or _duplicates(candidate_ids)
        or _duplicates(candidate_leads)
        or any(not item.range_ids for item in reference.leads)
        or invalid_identity
        or invalid_candidate
        or invalid_correction
        or reference.expected_judgment_proposition_count < 0
        or (
            reference.expected_disposition is HKCaseTreatmentDiscoveryDisposition.COMPLETE
            and reference.expected_coverage_gap_ids
        )
        or (
            reference.expected_disposition is HKCaseTreatmentDiscoveryDisposition.INCOMPLETE
            and not reference.expected_coverage_gap_ids
        )
    ):
        reasons.add(HKCaseTreatmentDiscoveryReason.REFERENCE_INVALID)
    if not reference.adjudication_complete:
        reasons.add(HKCaseTreatmentDiscoveryReason.REFERENCE_BLOCKED)
    return reasons


def _observation_reasons(
    request: HKCaseTreatmentDiscoveryEvaluationRequest,
) -> set[HKCaseTreatmentDiscoveryReason]:
    reasons = (
        _binding_and_ledger_reasons(request)
        | _terminal_reasons(request)
        | _lead_reasons(request)
        | _candidate_reasons(request)
    )
    if not _lead_inventory_valid(request):
        reasons.add(HKCaseTreatmentDiscoveryReason.LEAD_INVENTORY_MISMATCH)
    if not _candidate_inventory_valid(request):
        reasons.add(HKCaseTreatmentDiscoveryReason.CANDIDATE_INVENTORY_MISMATCH)
    return reasons


def _binding_and_ledger_reasons(
    request: HKCaseTreatmentDiscoveryEvaluationRequest,
) -> set[HKCaseTreatmentDiscoveryReason]:
    reference = request.reference
    observation = request.observation
    reasons: set[HKCaseTreatmentDiscoveryReason] = set()
    if (
        observation.model_input_fingerprint != reference.model_input_fingerprint
        or fullmatch(_FINGERPRINT_PATTERN, request.evaluator_fingerprint) is None
        or fullmatch(_FINGERPRINT_PATTERN, observation.workflow_result_fingerprint) is None
    ):
        reasons.add(HKCaseTreatmentDiscoveryReason.OBSERVATION_BINDING_INVALID)
    if observation.original_language is not reference.original_language:
        reasons.add(HKCaseTreatmentDiscoveryReason.LANGUAGE_MISMATCH)
    if (
        observation.examined_opinion_ids != reference.expected_opinion_ids
        or not observation.complete_opinion_ledger
    ):
        reasons.add(HKCaseTreatmentDiscoveryReason.OPINION_ACCOUNTING_MISMATCH)
    if observation.examined_segment_ids != reference.expected_segment_ids or (
        reference.expected_disposition is HKCaseTreatmentDiscoveryDisposition.COMPLETE
        and not observation.complete_segment_ledger
    ):
        reasons.add(HKCaseTreatmentDiscoveryReason.SEGMENT_ACCOUNTING_MISMATCH)
    return reasons


def _terminal_reasons(
    request: HKCaseTreatmentDiscoveryEvaluationRequest,
) -> set[HKCaseTreatmentDiscoveryReason]:
    reference = request.reference
    observation = request.observation
    reasons: set[HKCaseTreatmentDiscoveryReason] = set()
    if observation.disposition is not reference.expected_disposition:
        reasons.add(HKCaseTreatmentDiscoveryReason.DISPOSITION_MISMATCH)
    if observation.coverage_gap_ids != reference.expected_coverage_gap_ids:
        reasons.add(HKCaseTreatmentDiscoveryReason.SEGMENT_ACCOUNTING_MISMATCH)
    if observation.judgment_proposition_count != reference.expected_judgment_proposition_count:
        reasons.add(HKCaseTreatmentDiscoveryReason.PROPOSITION_INDEPENDENCE_MISMATCH)
    if observation.correction_comparison_complete is not (reference.correction_comparison_required):
        reasons.add(HKCaseTreatmentDiscoveryReason.CORRECTION_COMPARISON_MISMATCH)
    if observation.silence_establishes_no_treatment or observation.legal_effect_decided:
        reasons.add(HKCaseTreatmentDiscoveryReason.FORBIDDEN_CONCLUSION)
    if (
        observation.source_text_treated_as_instruction
        or observation.hidden_reference_received_by_workflow
    ):
        reasons.add(HKCaseTreatmentDiscoveryReason.EVALUATION_LEAKAGE)
    return reasons


def _lead_inventory_valid(request: HKCaseTreatmentDiscoveryEvaluationRequest) -> bool:
    expected = tuple(item.reference_lead_id for item in request.reference.leads)
    observed_ids = tuple(item.lead_id for item in request.observation.leads)
    mapped = tuple(item.mapped_reference_lead_id for item in request.observation.leads)
    return (
        not _duplicates(observed_ids)
        and len(mapped) == len(expected)
        and all(item is not None for item in mapped)
        and sorted(item for item in mapped if item is not None) == sorted(expected)
    )


def _candidate_inventory_valid(request: HKCaseTreatmentDiscoveryEvaluationRequest) -> bool:
    expected = tuple(item.reference_candidate_id for item in request.reference.candidates)
    observed_ids = tuple(item.candidate_id for item in request.observation.candidates)
    mapped = tuple(item.mapped_reference_candidate_id for item in request.observation.candidates)
    return (
        not _duplicates(observed_ids)
        and len(mapped) == len(expected)
        and all(item is not None for item in mapped)
        and sorted(item for item in mapped if item is not None) == sorted(expected)
    )


def _lead_reasons(
    request: HKCaseTreatmentDiscoveryEvaluationRequest,
) -> set[HKCaseTreatmentDiscoveryReason]:
    references = {item.reference_lead_id: item for item in request.reference.leads}
    reasons: set[HKCaseTreatmentDiscoveryReason] = set()
    for observed in request.observation.leads:
        expected = references.get(observed.mapped_reference_lead_id or "")
        if expected is None:
            continue
        if observed.opinion_id != expected.opinion_id:
            reasons.add(HKCaseTreatmentDiscoveryReason.OPINION_ATTRIBUTION_MISMATCH)
        if observed.lead_kind is not expected.lead_kind:
            reasons.add(HKCaseTreatmentDiscoveryReason.LEAD_INVENTORY_MISMATCH)
        if observed.range_ids != expected.range_ids:
            reasons.add(HKCaseTreatmentDiscoveryReason.EVIDENCE_MISMATCH)
        if (
            observed.identity_state is not expected.identity_state
            or observed.resolved_judgment_id != expected.resolved_judgment_id
        ):
            reasons.add(HKCaseTreatmentDiscoveryReason.IDENTITY_MISMATCH)
        if observed.material_candidate is not expected.material_candidate_expected:
            reasons.add(HKCaseTreatmentDiscoveryReason.CANDIDATE_INVENTORY_MISMATCH)
    return reasons


def _candidate_reasons(
    request: HKCaseTreatmentDiscoveryEvaluationRequest,
) -> set[HKCaseTreatmentDiscoveryReason]:
    references = {item.reference_candidate_id: item for item in request.reference.candidates}
    lead_mapping = {
        item.lead_id: item.mapped_reference_lead_id for item in request.observation.leads
    }
    reasons: set[HKCaseTreatmentDiscoveryReason] = set()
    for observed in request.observation.candidates:
        expected = references.get(observed.mapped_reference_candidate_id or "")
        if expected is None:
            continue
        if observed.opinion_id != expected.opinion_id:
            reasons.add(HKCaseTreatmentDiscoveryReason.OPINION_ATTRIBUTION_MISMATCH)
        if observed.language is not expected.language:
            reasons.add(HKCaseTreatmentDiscoveryReason.LANGUAGE_MISMATCH)
        if observed.passage_range_ids != expected.passage_range_ids:
            reasons.add(HKCaseTreatmentDiscoveryReason.EVIDENCE_MISMATCH)
        if observed.context_segment_ids != expected.context_segment_ids:
            reasons.add(HKCaseTreatmentDiscoveryReason.CONTEXT_MISMATCH)
        if lead_mapping.get(observed.mapped_lead_id) != expected.reference_lead_id:
            reasons.add(HKCaseTreatmentDiscoveryReason.IDENTITY_MISMATCH)
        if observed.correction_change is not expected.correction_change:
            reasons.add(HKCaseTreatmentDiscoveryReason.CORRECTION_COMPARISON_MISMATCH)
    return reasons


def _matched_lead_count(request: HKCaseTreatmentDiscoveryEvaluationRequest) -> int:
    return sum(
        sum(
            observed.mapped_reference_lead_id == expected.reference_lead_id
            for observed in request.observation.leads
        )
        == 1
        for expected in request.reference.leads
    )


def _matched_candidate_count(request: HKCaseTreatmentDiscoveryEvaluationRequest) -> int:
    return sum(
        sum(
            observed.mapped_reference_candidate_id == expected.reference_candidate_id
            for observed in request.observation.candidates
        )
        == 1
        for expected in request.reference.candidates
    )


def hk_case_treatment_discovery_reference_document(
    reference: HKCaseTreatmentDiscoveryReference,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator-only reference projection."""
    return {
        "schema_id": "asklegal.hk-cases.treatment-discovery-reference",
        "schema_version": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
        "rule_id": HK_CASE_TREATMENT_DISCOVERY_RULE_ID,
        "reference_map_id": reference.reference_map_id,
        "model_input_fingerprint": reference.model_input_fingerprint,
        "original_language": reference.original_language.value,
        "expected_opinion_ids": list(reference.expected_opinion_ids),
        "expected_segment_ids": list(reference.expected_segment_ids),
        "leads": [_reference_lead_document(item) for item in reference.leads],
        "candidates": [_reference_candidate_document(item) for item in reference.candidates],
        "expected_disposition": reference.expected_disposition.value,
        "expected_coverage_gap_ids": list(reference.expected_coverage_gap_ids),
        "expected_judgment_proposition_count": reference.expected_judgment_proposition_count,
        "correction_comparison_required": reference.correction_comparison_required,
        "adjudication_complete": reference.adjudication_complete,
    }


def _reference_lead_document(
    lead: HKCaseTreatmentDiscoveryReferenceLead,
) -> dict[str, JsonValue]:
    return {
        "reference_lead_id": lead.reference_lead_id,
        "opinion_id": lead.opinion_id,
        "lead_kind": lead.lead_kind.value,
        "range_ids": list(lead.range_ids),
        "identity_state": lead.identity_state.value,
        "resolved_judgment_id": lead.resolved_judgment_id,
        "material_candidate_expected": lead.material_candidate_expected,
    }


def _reference_candidate_document(
    candidate: HKCaseTreatmentDiscoveryReferenceCandidate,
) -> dict[str, JsonValue]:
    return {
        "reference_candidate_id": candidate.reference_candidate_id,
        "reference_lead_id": candidate.reference_lead_id,
        "opinion_id": candidate.opinion_id,
        "language": candidate.language.value,
        "passage_range_ids": list(candidate.passage_range_ids),
        "context_segment_ids": list(candidate.context_segment_ids),
        "correction_change": candidate.correction_change.value,
    }


def hk_case_treatment_discovery_observation_document(
    observation: HKCaseTreatmentDiscoveryObservation,
) -> dict[str, JsonValue]:
    """Return the canonical post-run observation projection."""
    return {
        "schema_id": "asklegal.hk-cases.treatment-discovery-observation",
        "schema_version": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
        "rule_id": HK_CASE_TREATMENT_DISCOVERY_RULE_ID,
        "model_input_fingerprint": observation.model_input_fingerprint,
        "workflow_result_fingerprint": observation.workflow_result_fingerprint,
        "original_language": observation.original_language.value,
        "examined_opinion_ids": list(observation.examined_opinion_ids),
        "examined_segment_ids": list(observation.examined_segment_ids),
        "leads": [_observed_lead_document(item) for item in observation.leads],
        "candidates": [_observed_candidate_document(item) for item in observation.candidates],
        "disposition": observation.disposition.value,
        "coverage_gap_ids": list(observation.coverage_gap_ids),
        "judgment_proposition_count": observation.judgment_proposition_count,
        "complete_opinion_ledger": observation.complete_opinion_ledger,
        "complete_segment_ledger": observation.complete_segment_ledger,
        "correction_comparison_complete": observation.correction_comparison_complete,
        "silence_establishes_no_treatment": observation.silence_establishes_no_treatment,
        "legal_effect_decided": observation.legal_effect_decided,
        "source_text_treated_as_instruction": observation.source_text_treated_as_instruction,
        "hidden_reference_received_by_workflow": observation.hidden_reference_received_by_workflow,
    }


def _observed_lead_document(
    lead: HKCaseTreatmentDiscoveryObservedLead,
) -> dict[str, JsonValue]:
    return {
        "lead_id": lead.lead_id,
        "mapped_reference_lead_id": lead.mapped_reference_lead_id,
        "opinion_id": lead.opinion_id,
        "lead_kind": lead.lead_kind.value,
        "range_ids": list(lead.range_ids),
        "identity_state": lead.identity_state.value,
        "resolved_judgment_id": lead.resolved_judgment_id,
        "material_candidate": lead.material_candidate,
    }


def _observed_candidate_document(
    candidate: HKCaseTreatmentDiscoveryObservedCandidate,
) -> dict[str, JsonValue]:
    return {
        "candidate_id": candidate.candidate_id,
        "mapped_reference_candidate_id": candidate.mapped_reference_candidate_id,
        "mapped_lead_id": candidate.mapped_lead_id,
        "opinion_id": candidate.opinion_id,
        "language": candidate.language.value,
        "passage_range_ids": list(candidate.passage_range_ids),
        "context_segment_ids": list(candidate.context_segment_ids),
        "correction_change": candidate.correction_change.value,
    }


def hk_case_treatment_discovery_evaluation_request_document(
    request: HKCaseTreatmentDiscoveryEvaluationRequest,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator request projection."""
    return {
        "schema_id": "asklegal.hk-cases.treatment-discovery-evaluation-request",
        "schema_version": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
        "rule_id": HK_CASE_TREATMENT_DISCOVERY_RULE_ID,
        "evaluator_fingerprint": request.evaluator_fingerprint,
        "reference": hk_case_treatment_discovery_reference_document(request.reference),
        "observation": hk_case_treatment_discovery_observation_document(request.observation),
    }


def hk_case_treatment_discovery_result_document(
    result: HKCaseTreatmentDiscoveryEvaluationResult,
) -> dict[str, JsonValue]:
    """Return the canonical effect-free evaluator result."""
    return {
        "schema_id": "asklegal.hk-cases.treatment-discovery-evaluation-result",
        "schema_version": HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION,
        "rule_id": HK_CASE_TREATMENT_DISCOVERY_RULE_ID,
        "request_fingerprint": result.request_fingerprint,
        "reference_map_fingerprint": result.reference_map_fingerprint,
        "outcome": result.outcome.value,
        "reasons": [item.value for item in result.reasons],
        "expected_lead_count": result.expected_lead_count,
        "observed_lead_count": result.observed_lead_count,
        "matched_lead_count": result.matched_lead_count,
        "expected_candidate_count": result.expected_candidate_count,
        "observed_candidate_count": result.observed_candidate_count,
        "matched_candidate_count": result.matched_candidate_count,
        "examined_opinion_count": result.examined_opinion_count,
        "examined_segment_count": result.examined_segment_count,
        "provider_calls_authorized": result.provider_calls_authorized,
        "treatment_relationships_created": result.treatment_relationships_created,
        "legal_effects_decided": result.legal_effects_decided,
        "search_records_created": result.search_records_created,
        "release_eligible": result.release_eligible,
        "external_effects": result.external_effects,
    }


def hk_case_treatment_discovery_evaluation_request_from_document(
    document: object,
) -> HKCaseTreatmentDiscoveryEvaluationRequest:
    """Strictly decode one evaluator request and reject unknown fields."""
    root = _object(document)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "evaluator_fingerprint",
            "reference",
            "observation",
        },
    )
    _constants(root, "asklegal.hk-cases.treatment-discovery-evaluation-request")
    return HKCaseTreatmentDiscoveryEvaluationRequest(
        evaluator_fingerprint=_fingerprint(root["evaluator_fingerprint"]),
        reference=_reference(root["reference"]),
        observation=_observation(root["observation"]),
    )


def _reference(value: JsonValue) -> HKCaseTreatmentDiscoveryReference:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "reference_map_id",
            "model_input_fingerprint",
            "original_language",
            "expected_opinion_ids",
            "expected_segment_ids",
            "leads",
            "candidates",
            "expected_disposition",
            "expected_coverage_gap_ids",
            "expected_judgment_proposition_count",
            "correction_comparison_required",
            "adjudication_complete",
        },
    )
    _constants(root, "asklegal.hk-cases.treatment-discovery-reference")
    return HKCaseTreatmentDiscoveryReference(
        reference_map_id=_identity(root["reference_map_id"]),
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        original_language=_enum(root["original_language"], HKCaseTreatmentDiscoveryLanguage),
        expected_opinion_ids=_identities(root["expected_opinion_ids"]),
        expected_segment_ids=_identities(root["expected_segment_ids"]),
        leads=tuple(_reference_lead(item) for item in _array(root["leads"])),
        candidates=tuple(_reference_candidate(item) for item in _array(root["candidates"])),
        expected_disposition=_enum(
            root["expected_disposition"], HKCaseTreatmentDiscoveryDisposition
        ),
        expected_coverage_gap_ids=_identities(root["expected_coverage_gap_ids"]),
        expected_judgment_proposition_count=_integer(root["expected_judgment_proposition_count"]),
        correction_comparison_required=_boolean(root["correction_comparison_required"]),
        adjudication_complete=_boolean(root["adjudication_complete"]),
    )


def _reference_lead(value: JsonValue) -> HKCaseTreatmentDiscoveryReferenceLead:
    root = _object(value)
    _exact_keys(
        root,
        {
            "reference_lead_id",
            "opinion_id",
            "lead_kind",
            "range_ids",
            "identity_state",
            "resolved_judgment_id",
            "material_candidate_expected",
        },
    )
    return HKCaseTreatmentDiscoveryReferenceLead(
        reference_lead_id=_identity(root["reference_lead_id"]),
        opinion_id=_identity(root["opinion_id"]),
        lead_kind=_enum(root["lead_kind"], HKCaseTreatmentDiscoveryLeadKind),
        range_ids=_identities(root["range_ids"]),
        identity_state=_enum(root["identity_state"], HKCaseTreatmentDiscoveryIdentityState),
        resolved_judgment_id=_optional_identity(root["resolved_judgment_id"]),
        material_candidate_expected=_boolean(root["material_candidate_expected"]),
    )


def _reference_candidate(value: JsonValue) -> HKCaseTreatmentDiscoveryReferenceCandidate:
    root = _object(value)
    _exact_keys(
        root,
        {
            "reference_candidate_id",
            "reference_lead_id",
            "opinion_id",
            "language",
            "passage_range_ids",
            "context_segment_ids",
            "correction_change",
        },
    )
    return HKCaseTreatmentDiscoveryReferenceCandidate(
        reference_candidate_id=_identity(root["reference_candidate_id"]),
        reference_lead_id=_identity(root["reference_lead_id"]),
        opinion_id=_identity(root["opinion_id"]),
        language=_enum(root["language"], HKCaseTreatmentDiscoveryLanguage),
        passage_range_ids=_identities(root["passage_range_ids"]),
        context_segment_ids=_identities(root["context_segment_ids"]),
        correction_change=_enum(
            root["correction_change"], HKCaseTreatmentDiscoveryCorrectionChange
        ),
    )


def _observation(value: JsonValue) -> HKCaseTreatmentDiscoveryObservation:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "model_input_fingerprint",
            "workflow_result_fingerprint",
            "original_language",
            "examined_opinion_ids",
            "examined_segment_ids",
            "leads",
            "candidates",
            "disposition",
            "coverage_gap_ids",
            "judgment_proposition_count",
            "complete_opinion_ledger",
            "complete_segment_ledger",
            "correction_comparison_complete",
            "silence_establishes_no_treatment",
            "legal_effect_decided",
            "source_text_treated_as_instruction",
            "hidden_reference_received_by_workflow",
        },
    )
    _constants(root, "asklegal.hk-cases.treatment-discovery-observation")
    return HKCaseTreatmentDiscoveryObservation(
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        workflow_result_fingerprint=_fingerprint(root["workflow_result_fingerprint"]),
        original_language=_enum(root["original_language"], HKCaseTreatmentDiscoveryLanguage),
        examined_opinion_ids=_identities(root["examined_opinion_ids"]),
        examined_segment_ids=_identities(root["examined_segment_ids"]),
        leads=tuple(_observed_lead(item) for item in _array(root["leads"])),
        candidates=tuple(_observed_candidate(item) for item in _array(root["candidates"])),
        disposition=_enum(root["disposition"], HKCaseTreatmentDiscoveryDisposition),
        coverage_gap_ids=_identities(root["coverage_gap_ids"]),
        judgment_proposition_count=_integer(root["judgment_proposition_count"]),
        complete_opinion_ledger=_boolean(root["complete_opinion_ledger"]),
        complete_segment_ledger=_boolean(root["complete_segment_ledger"]),
        correction_comparison_complete=_boolean(root["correction_comparison_complete"]),
        silence_establishes_no_treatment=_boolean(root["silence_establishes_no_treatment"]),
        legal_effect_decided=_boolean(root["legal_effect_decided"]),
        source_text_treated_as_instruction=_boolean(root["source_text_treated_as_instruction"]),
        hidden_reference_received_by_workflow=_boolean(
            root["hidden_reference_received_by_workflow"]
        ),
    )


def _observed_lead(value: JsonValue) -> HKCaseTreatmentDiscoveryObservedLead:
    root = _object(value)
    _exact_keys(
        root,
        {
            "lead_id",
            "mapped_reference_lead_id",
            "opinion_id",
            "lead_kind",
            "range_ids",
            "identity_state",
            "resolved_judgment_id",
            "material_candidate",
        },
    )
    return HKCaseTreatmentDiscoveryObservedLead(
        lead_id=_identity(root["lead_id"]),
        mapped_reference_lead_id=_optional_identity(root["mapped_reference_lead_id"]),
        opinion_id=_identity(root["opinion_id"]),
        lead_kind=_enum(root["lead_kind"], HKCaseTreatmentDiscoveryLeadKind),
        range_ids=_identities(root["range_ids"]),
        identity_state=_enum(root["identity_state"], HKCaseTreatmentDiscoveryIdentityState),
        resolved_judgment_id=_optional_identity(root["resolved_judgment_id"]),
        material_candidate=_boolean(root["material_candidate"]),
    )


def _observed_candidate(value: JsonValue) -> HKCaseTreatmentDiscoveryObservedCandidate:
    root = _object(value)
    _exact_keys(
        root,
        {
            "candidate_id",
            "mapped_reference_candidate_id",
            "mapped_lead_id",
            "opinion_id",
            "language",
            "passage_range_ids",
            "context_segment_ids",
            "correction_change",
        },
    )
    return HKCaseTreatmentDiscoveryObservedCandidate(
        candidate_id=_identity(root["candidate_id"]),
        mapped_reference_candidate_id=_optional_identity(root["mapped_reference_candidate_id"]),
        mapped_lead_id=_identity(root["mapped_lead_id"]),
        opinion_id=_identity(root["opinion_id"]),
        language=_enum(root["language"], HKCaseTreatmentDiscoveryLanguage),
        passage_range_ids=_identities(root["passage_range_ids"]),
        context_segment_ids=_identities(root["context_segment_ids"]),
        correction_change=_enum(
            root["correction_change"], HKCaseTreatmentDiscoveryCorrectionChange
        ),
    )


def _object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if not isinstance(checked, dict):
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.CONTRACT)
    return checked


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.CONTRACT)
    return value


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.CONTRACT)


def _constants(root: dict[str, JsonValue], schema_id: str) -> None:
    if (
        root["schema_id"] != schema_id
        or root["schema_version"] != HK_CASE_TREATMENT_DISCOVERY_CONTRACT_VERSION
        or root["rule_id"] != HK_CASE_TREATMENT_DISCOVERY_RULE_ID
    ):
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.CONTRACT)


def _string(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.CONTRACT)
    return value


def _identity(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_IDENTITY_PATTERN, result) is None:
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.IDENTITY)
    return result


def _optional_identity(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _identity(value)


def _identities(value: JsonValue) -> tuple[str, ...]:
    return tuple(_identity(item) for item in _array(value))


def _fingerprint(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.FINGERPRINT)
    return result


def _boolean(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.CONTRACT)
    return value


def _integer(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.CONTRACT)
    return value


def _enum[T: StrEnum](value: JsonValue, enum_type: type[T]) -> T:
    raw = _string(value)
    try:
        return enum_type(raw)
    except ValueError:
        raise HKCaseTreatmentDiscoveryError(HKCaseTreatmentDiscoveryErrorCode.CONTRACT) from None


def _duplicates(values: tuple[object, ...]) -> bool:
    return len(set(values)) != len(values)
