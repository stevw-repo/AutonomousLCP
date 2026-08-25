"""Deterministic evaluator for Hong Kong Case semantic risk and safety cases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

HK_CASE_SEMANTIC_RISK_CONTRACT_VERSION = "1.0.0"
HK_CASE_SEMANTIC_RISK_RULE_ID = "HKCASE-PROP-SEM-RISK-EVALUATOR-001"

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_IDENTITY_PATTERN = r"[a-z][a-z0-9_]{2,95}"
_CODE_PATTERN = r"[A-Z][A-Z0-9_]{2,95}"


class HKCaseSemanticRiskErrorCode(StrEnum):
    """Closed malformed evaluator-input failures."""

    CONTRACT = "HK_CASE_SEMANTIC_RISK_CONTRACT_INVALID"
    FINGERPRINT = "HK_CASE_SEMANTIC_RISK_FINGERPRINT_INVALID"
    IDENTITY = "HK_CASE_SEMANTIC_RISK_IDENTITY_INVALID"


class HKCaseSemanticRiskError(ValueError):
    """One strict semantic-risk contract failure."""

    code: HKCaseSemanticRiskErrorCode

    def __init__(self, code: HKCaseSemanticRiskErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKCaseSemanticRiskCourtFamily(StrEnum):
    """Frozen court families exercised by this checkpoint."""

    CA = "CA"
    CFA = "CFA"
    CFI = "CFI"
    CT = "CT"
    HKPC = "HKPC"
    HKSUPERIOR = "HKSUPERIOR"


class HKCaseSemanticRiskLanguage(StrEnum):
    """Accepted original-language forms."""

    ENGLISH = "ENGLISH"
    MIXED = "MIXED"
    TRADITIONAL_CHINESE = "TRADITIONAL_CHINESE"


class HKCaseSemanticRiskDisposition(StrEnum):
    """Closed judgment-wide risk dispositions."""

    ACCOUNTED_WITH_QUARANTINE = "ACCOUNTED_WITH_QUARANTINE"
    BLOCKED = "BLOCKED"
    COMPLETE_WITH_PROPOSITIONS = "COMPLETE_WITH_PROPOSITIONS"


class HKCaseSemanticRiskResolution(StrEnum):
    """One candidate's exact adjudicated consequence."""

    ACCEPTED = "ACCEPTED"
    QUARANTINED = "QUARANTINED"


class HKCaseSemanticRiskTranslationUse(StrEnum):
    """Permitted use of an optional official translation."""

    AUXILIARY_ONLY = "AUXILIARY_ONLY"
    CONFLICT_ISOLATED = "CONFLICT_ISOLATED"
    NONE = "NONE"


class HKCaseSemanticRiskOutcome(StrEnum):
    """Deterministic evaluator outcomes."""

    EVALUATOR_BLOCKED = "EVALUATOR_BLOCKED"
    FAIL = "FAIL"
    PASS = "PASS"


class HKCaseSemanticRiskReason(StrEnum):
    """Closed risk evaluator reasons."""

    CANDIDATE_INVENTORY_MISMATCH = "CANDIDATE_INVENTORY_MISMATCH"
    CORRECTION_MISMATCH = "CORRECTION_MISMATCH"
    COURT_FAMILY_MISMATCH = "COURT_FAMILY_MISMATCH"
    COVERAGE_GAP_MISMATCH = "COVERAGE_GAP_MISMATCH"
    DEPENDENCY_MISMATCH = "DEPENDENCY_MISMATCH"
    DISPOSITION_MISMATCH = "DISPOSITION_MISMATCH"
    EVALUATION_LEAKAGE = "EVALUATION_LEAKAGE"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
    LEDGER_INCOMPLETE = "LEDGER_INCOMPLETE"
    MEANING_MISMATCH = "MEANING_MISMATCH"
    OBSERVATION_BINDING_INVALID = "OBSERVATION_BINDING_INVALID"
    ORIGINAL_AUTHORITY_MISMATCH = "ORIGINAL_AUTHORITY_MISMATCH"
    PARSER_SUPPORT_MISMATCH = "PARSER_SUPPORT_MISMATCH"
    PASS = "PASS"
    REFERENCE_BLOCKED = "REFERENCE_BLOCKED"
    REFERENCE_INVALID = "REFERENCE_INVALID"
    RESOLUTION_MISMATCH = "RESOLUTION_MISMATCH"
    RISK_CONSEQUENCE_MISMATCH = "RISK_CONSEQUENCE_MISMATCH"
    SEGMENT_ACCOUNTING_MISMATCH = "SEGMENT_ACCOUNTING_MISMATCH"
    SELECTION_MISMATCH = "SELECTION_MISMATCH"
    STATEMENT_STATE_MISMATCH = "STATEMENT_STATE_MISMATCH"
    TRANSLATION_USE_MISMATCH = "TRANSLATION_USE_MISMATCH"


@dataclass(frozen=True, slots=True)
class HKCaseSemanticRiskReferenceCandidate:
    """One hidden adjudicated risk-case candidate assertion set."""

    reference_proposition_id: str
    expected_resolution: HKCaseSemanticRiskResolution
    issue_code: str
    language: HKCaseSemanticRiskLanguage
    source_version_id: str
    required_meaning_codes: tuple[str, ...]
    required_risk_codes: tuple[str, ...]
    forbidden_risk_codes: tuple[str, ...]
    required_range_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticRiskReference:
    """Evaluator-only truth for one court/language/length/safety case."""

    reference_map_id: str
    model_input_fingerprint: str
    court_family: HKCaseSemanticRiskCourtFamily
    original_language: HKCaseSemanticRiskLanguage
    accepted_original_version_id: str
    auxiliary_translation_version_ids: tuple[str, ...]
    expected_examined_segment_ids: tuple[str, ...]
    expected_resolved_dependency_ids: tuple[str, ...]
    candidates: tuple[HKCaseSemanticRiskReferenceCandidate, ...]
    expected_disposition: HKCaseSemanticRiskDisposition
    expected_selected_reference_proposition_ids: tuple[str, ...]
    expected_coverage_gap_ids: tuple[str, ...]
    expected_translation_use: HKCaseSemanticRiskTranslationUse
    expected_parser_supported: bool
    expected_re_evaluated_reference_proposition_ids: tuple[str, ...]
    prior_result_immutable_required: bool
    adjudication_complete: bool
    unresolved_reference_ambiguity: bool


@dataclass(frozen=True, slots=True)
class HKCaseSemanticRiskObservedCandidate:
    """One post-run candidate reduced to evaluator-visible risk facts."""

    candidate_id: str
    mapped_reference_proposition_id: str | None
    resolution: HKCaseSemanticRiskResolution
    issue_code: str
    language: HKCaseSemanticRiskLanguage
    source_version_id: str
    meaning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    range_ids: tuple[str, ...]
    derived_statement: str | None


@dataclass(frozen=True, slots=True)
class HKCaseSemanticRiskObservation:
    """One candidate workflow result reduced to evaluator-visible risk facts."""

    model_input_fingerprint: str
    workflow_result_fingerprint: str
    court_family: HKCaseSemanticRiskCourtFamily
    original_language: HKCaseSemanticRiskLanguage
    accepted_original_version_id: str
    auxiliary_translation_version_ids: tuple[str, ...]
    examined_segment_ids: tuple[str, ...]
    resolved_dependency_ids: tuple[str, ...]
    candidates: tuple[HKCaseSemanticRiskObservedCandidate, ...]
    disposition: HKCaseSemanticRiskDisposition
    selected_candidate_ids: tuple[str, ...]
    coverage_gap_ids: tuple[str, ...]
    translation_use: HKCaseSemanticRiskTranslationUse
    parser_supported: bool
    complete_ledger: bool
    re_evaluated_candidate_ids: tuple[str, ...]
    prior_result_immutable: bool
    source_text_treated_as_instruction: bool
    hidden_reference_received_by_workflow: bool


@dataclass(frozen=True, slots=True)
class HKCaseSemanticRiskEvaluationRequest:
    """One evaluator-only reference and one post-run observation."""

    evaluator_fingerprint: str
    reference: HKCaseSemanticRiskReference
    observation: HKCaseSemanticRiskObservation


@dataclass(frozen=True, slots=True)
class HKCaseSemanticRiskEvaluationResult:
    """One effect-free deterministic risk comparison."""

    request_fingerprint: str
    reference_map_fingerprint: str
    outcome: HKCaseSemanticRiskOutcome
    reasons: tuple[HKCaseSemanticRiskReason, ...]
    expected_candidate_count: int
    observed_candidate_count: int
    matched_candidate_count: int
    accepted_candidate_count: int
    quarantined_candidate_count: int
    examined_segment_count: int
    resolved_dependency_count: int
    provider_calls_authorized: int
    workflow_admission_created: bool
    search_records_created: int
    release_eligible: bool
    external_effects: str


def evaluate_hk_case_semantic_risk(
    request: HKCaseSemanticRiskEvaluationRequest,
) -> HKCaseSemanticRiskEvaluationResult:
    """Compare risk and safety facts without case identity or external effects."""
    request_fingerprint = fingerprint(
        checked_json_value(hk_case_semantic_risk_evaluation_request_document(request))
    )
    reference_fingerprint = fingerprint(
        checked_json_value(hk_case_semantic_risk_reference_document(request.reference))
    )
    reasons = _reference_reasons(request.reference) | _observation_reasons(request)
    if HKCaseSemanticRiskReason.REFERENCE_BLOCKED in reasons:
        outcome = HKCaseSemanticRiskOutcome.EVALUATOR_BLOCKED
    elif reasons:
        outcome = HKCaseSemanticRiskOutcome.FAIL
    else:
        outcome = HKCaseSemanticRiskOutcome.PASS
        reasons = {HKCaseSemanticRiskReason.PASS}
    return HKCaseSemanticRiskEvaluationResult(
        request_fingerprint=request_fingerprint,
        reference_map_fingerprint=reference_fingerprint,
        outcome=outcome,
        reasons=tuple(sorted(reasons, key=lambda item: item.value)),
        expected_candidate_count=len(request.reference.candidates),
        observed_candidate_count=len(request.observation.candidates),
        matched_candidate_count=_matched_candidate_count(request),
        accepted_candidate_count=sum(
            item.resolution is HKCaseSemanticRiskResolution.ACCEPTED
            for item in request.observation.candidates
        ),
        quarantined_candidate_count=sum(
            item.resolution is HKCaseSemanticRiskResolution.QUARANTINED
            for item in request.observation.candidates
        ),
        examined_segment_count=len(request.observation.examined_segment_ids),
        resolved_dependency_count=len(request.observation.resolved_dependency_ids),
        provider_calls_authorized=0,
        workflow_admission_created=False,
        search_records_created=0,
        release_eligible=False,
        external_effects="NONE",
    )


def _reference_reasons(
    reference: HKCaseSemanticRiskReference,
) -> set[HKCaseSemanticRiskReason]:
    reasons: set[HKCaseSemanticRiskReason] = set()
    reference_ids = tuple(item.reference_proposition_id for item in reference.candidates)
    accepted_ids = tuple(
        item.reference_proposition_id
        for item in reference.candidates
        if item.expected_resolution is HKCaseSemanticRiskResolution.ACCEPTED
    )
    quarantined_ids = tuple(
        item.reference_proposition_id
        for item in reference.candidates
        if item.expected_resolution is HKCaseSemanticRiskResolution.QUARANTINED
    )
    selected = reference.expected_selected_reference_proposition_ids
    disposition_valid = (
        (
            reference.expected_disposition
            is HKCaseSemanticRiskDisposition.COMPLETE_WITH_PROPOSITIONS
            and bool(accepted_ids)
            and not quarantined_ids
            and tuple(selected) == accepted_ids
        )
        or (
            reference.expected_disposition
            is HKCaseSemanticRiskDisposition.ACCOUNTED_WITH_QUARANTINE
            and bool(quarantined_ids)
            and not accepted_ids
            and not selected
        )
        or (
            reference.expected_disposition is HKCaseSemanticRiskDisposition.BLOCKED
            and not reference.candidates
            and not selected
        )
    )
    if (
        _duplicates(reference_ids)
        or _duplicates(reference.auxiliary_translation_version_ids)
        or _duplicates(reference.expected_examined_segment_ids)
        or _duplicates(reference.expected_resolved_dependency_ids)
        or _duplicates(reference.expected_coverage_gap_ids)
        or _duplicates(reference.expected_re_evaluated_reference_proposition_ids)
        or any(not _reference_candidate_valid(item) for item in reference.candidates)
        or not set(selected).issubset(reference_ids)
        or not set(reference.expected_re_evaluated_reference_proposition_ids).issubset(
            reference_ids
        )
        or not disposition_valid
        or (
            reference.expected_translation_use is HKCaseSemanticRiskTranslationUse.NONE
            and reference.auxiliary_translation_version_ids
        )
        or (
            reference.expected_translation_use is not HKCaseSemanticRiskTranslationUse.NONE
            and not reference.auxiliary_translation_version_ids
        )
    ):
        reasons.add(HKCaseSemanticRiskReason.REFERENCE_INVALID)
    if not reference.adjudication_complete or reference.unresolved_reference_ambiguity:
        reasons.add(HKCaseSemanticRiskReason.REFERENCE_BLOCKED)
    return reasons


def _reference_candidate_valid(candidate: HKCaseSemanticRiskReferenceCandidate) -> bool:
    return (
        bool(candidate.required_meaning_codes)
        and bool(candidate.required_risk_codes)
        and bool(candidate.required_range_ids)
        and not _duplicates(candidate.required_meaning_codes)
        and not _duplicates(candidate.required_risk_codes)
        and not _duplicates(candidate.forbidden_risk_codes)
        and not _duplicates(candidate.required_range_ids)
        and not set(candidate.required_risk_codes).intersection(candidate.forbidden_risk_codes)
    )


def _observation_reasons(
    request: HKCaseSemanticRiskEvaluationRequest,
) -> set[HKCaseSemanticRiskReason]:
    observation = request.observation
    reasons = (
        _binding_reasons(request)
        | _source_reasons(request)
        | _accounting_reasons(request)
        | _terminal_reasons(request)
    )
    reasons.update(_mapped_candidate_reasons(request))
    if (
        observation.source_text_treated_as_instruction
        or observation.hidden_reference_received_by_workflow
    ):
        reasons.add(HKCaseSemanticRiskReason.EVALUATION_LEAKAGE)
    return reasons


def _binding_reasons(
    request: HKCaseSemanticRiskEvaluationRequest,
) -> set[HKCaseSemanticRiskReason]:
    reference = request.reference
    observation = request.observation
    reasons: set[HKCaseSemanticRiskReason] = set()
    if (
        observation.model_input_fingerprint != reference.model_input_fingerprint
        or fullmatch(_FINGERPRINT_PATTERN, request.evaluator_fingerprint) is None
        or fullmatch(_FINGERPRINT_PATTERN, observation.workflow_result_fingerprint) is None
    ):
        reasons.add(HKCaseSemanticRiskReason.OBSERVATION_BINDING_INVALID)
    return reasons


def _source_reasons(
    request: HKCaseSemanticRiskEvaluationRequest,
) -> set[HKCaseSemanticRiskReason]:
    reference = request.reference
    observation = request.observation
    reasons: set[HKCaseSemanticRiskReason] = set()
    if observation.court_family is not reference.court_family:
        reasons.add(HKCaseSemanticRiskReason.COURT_FAMILY_MISMATCH)
    if observation.original_language is not reference.original_language:
        reasons.add(HKCaseSemanticRiskReason.LANGUAGE_MISMATCH)
    if (
        observation.accepted_original_version_id != reference.accepted_original_version_id
        or observation.auxiliary_translation_version_ids
        != reference.auxiliary_translation_version_ids
    ):
        reasons.add(HKCaseSemanticRiskReason.ORIGINAL_AUTHORITY_MISMATCH)
    if observation.examined_segment_ids != reference.expected_examined_segment_ids:
        reasons.add(HKCaseSemanticRiskReason.SEGMENT_ACCOUNTING_MISMATCH)
    if observation.resolved_dependency_ids != reference.expected_resolved_dependency_ids:
        reasons.add(HKCaseSemanticRiskReason.DEPENDENCY_MISMATCH)
    if observation.parser_supported is not reference.expected_parser_supported:
        reasons.add(HKCaseSemanticRiskReason.PARSER_SUPPORT_MISMATCH)
    if observation.translation_use is not reference.expected_translation_use:
        reasons.add(HKCaseSemanticRiskReason.TRANSLATION_USE_MISMATCH)
    return reasons


def _accounting_reasons(
    request: HKCaseSemanticRiskEvaluationRequest,
) -> set[HKCaseSemanticRiskReason]:
    observation = request.observation
    reasons: set[HKCaseSemanticRiskReason] = set()
    if not _candidate_inventory_valid(request):
        reasons.add(HKCaseSemanticRiskReason.CANDIDATE_INVENTORY_MISMATCH)
    if not _selection_valid(request):
        reasons.add(HKCaseSemanticRiskReason.SELECTION_MISMATCH)
    if not observation.complete_ledger:
        reasons.add(HKCaseSemanticRiskReason.LEDGER_INCOMPLETE)
    return reasons


def _terminal_reasons(
    request: HKCaseSemanticRiskEvaluationRequest,
) -> set[HKCaseSemanticRiskReason]:
    reference = request.reference
    observation = request.observation
    reasons: set[HKCaseSemanticRiskReason] = set()
    if observation.disposition is not reference.expected_disposition:
        reasons.add(HKCaseSemanticRiskReason.DISPOSITION_MISMATCH)
    if observation.coverage_gap_ids != reference.expected_coverage_gap_ids:
        reasons.add(HKCaseSemanticRiskReason.COVERAGE_GAP_MISMATCH)
    if not _correction_valid(request):
        reasons.add(HKCaseSemanticRiskReason.CORRECTION_MISMATCH)
    return reasons


def _candidate_inventory_valid(request: HKCaseSemanticRiskEvaluationRequest) -> bool:
    reference_ids = tuple(item.reference_proposition_id for item in request.reference.candidates)
    mapped_ids = tuple(
        item.mapped_reference_proposition_id for item in request.observation.candidates
    )
    candidate_ids = tuple(item.candidate_id for item in request.observation.candidates)
    return (
        not _duplicates(candidate_ids)
        and len(mapped_ids) == len(reference_ids)
        and all(item is not None for item in mapped_ids)
        and sorted(item for item in mapped_ids if item is not None) == sorted(reference_ids)
    )


def _matched_candidate_count(request: HKCaseSemanticRiskEvaluationRequest) -> int:
    return sum(
        sum(
            observed.mapped_reference_proposition_id == expected.reference_proposition_id
            for observed in request.observation.candidates
        )
        == 1
        for expected in request.reference.candidates
    )


def _mapped_candidate_reasons(
    request: HKCaseSemanticRiskEvaluationRequest,
) -> set[HKCaseSemanticRiskReason]:
    references = {item.reference_proposition_id: item for item in request.reference.candidates}
    reasons: set[HKCaseSemanticRiskReason] = set()
    for observed in request.observation.candidates:
        expected = references.get(observed.mapped_reference_proposition_id or "")
        if expected is not None:
            reasons.update(_candidate_reasons(expected, observed))
    return reasons


def _candidate_reasons(
    expected: HKCaseSemanticRiskReferenceCandidate,
    observed: HKCaseSemanticRiskObservedCandidate,
) -> set[HKCaseSemanticRiskReason]:
    reasons: set[HKCaseSemanticRiskReason] = set()
    if observed.resolution is not expected.expected_resolution:
        reasons.add(HKCaseSemanticRiskReason.RESOLUTION_MISMATCH)
    if observed.issue_code != expected.issue_code:
        reasons.add(HKCaseSemanticRiskReason.MEANING_MISMATCH)
    if observed.language is not expected.language:
        reasons.add(HKCaseSemanticRiskReason.LANGUAGE_MISMATCH)
    if observed.source_version_id != expected.source_version_id:
        reasons.add(HKCaseSemanticRiskReason.ORIGINAL_AUTHORITY_MISMATCH)
    if not set(expected.required_meaning_codes).issubset(observed.meaning_codes):
        reasons.add(HKCaseSemanticRiskReason.MEANING_MISMATCH)
    if not set(expected.required_risk_codes).issubset(observed.risk_codes) or set(
        expected.forbidden_risk_codes
    ).intersection(observed.risk_codes):
        reasons.add(HKCaseSemanticRiskReason.RISK_CONSEQUENCE_MISMATCH)
    if observed.range_ids != expected.required_range_ids:
        reasons.add(HKCaseSemanticRiskReason.EVIDENCE_MISMATCH)
    if not _statement_state_valid(expected, observed):
        reasons.add(HKCaseSemanticRiskReason.STATEMENT_STATE_MISMATCH)
    return reasons


def _statement_state_valid(
    expected: HKCaseSemanticRiskReferenceCandidate,
    observed: HKCaseSemanticRiskObservedCandidate,
) -> bool:
    return (
        expected.expected_resolution is HKCaseSemanticRiskResolution.ACCEPTED
        and observed.derived_statement is not None
        and bool(observed.derived_statement.strip())
    ) or (
        expected.expected_resolution is HKCaseSemanticRiskResolution.QUARANTINED
        and observed.derived_statement is None
    )


def _selection_valid(request: HKCaseSemanticRiskEvaluationRequest) -> bool:
    mapping = {
        item.candidate_id: item.mapped_reference_proposition_id
        for item in request.observation.candidates
    }
    return (
        not _duplicates(request.observation.selected_candidate_ids)
        and tuple(mapping.get(item) for item in request.observation.selected_candidate_ids)
        == request.reference.expected_selected_reference_proposition_ids
    )


def _correction_valid(request: HKCaseSemanticRiskEvaluationRequest) -> bool:
    mapping = {
        item.candidate_id: item.mapped_reference_proposition_id
        for item in request.observation.candidates
    }
    observed = tuple(mapping.get(item) for item in request.observation.re_evaluated_candidate_ids)
    reference = request.reference
    return (
        not _duplicates(request.observation.re_evaluated_candidate_ids)
        and observed == reference.expected_re_evaluated_reference_proposition_ids
        and (
            not reference.prior_result_immutable_required
            or request.observation.prior_result_immutable
        )
    )


def hk_case_semantic_risk_reference_document(
    reference: HKCaseSemanticRiskReference,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator-only risk reference projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-risk-reference",
        "schema_version": HK_CASE_SEMANTIC_RISK_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_RISK_RULE_ID,
        "reference_map_id": reference.reference_map_id,
        "model_input_fingerprint": reference.model_input_fingerprint,
        "court_family": reference.court_family.value,
        "original_language": reference.original_language.value,
        "accepted_original_version_id": reference.accepted_original_version_id,
        "auxiliary_translation_version_ids": list(reference.auxiliary_translation_version_ids),
        "expected_examined_segment_ids": list(reference.expected_examined_segment_ids),
        "expected_resolved_dependency_ids": list(reference.expected_resolved_dependency_ids),
        "candidates": [_reference_candidate_document(item) for item in reference.candidates],
        "expected_disposition": reference.expected_disposition.value,
        "expected_selected_reference_proposition_ids": list(
            reference.expected_selected_reference_proposition_ids
        ),
        "expected_coverage_gap_ids": list(reference.expected_coverage_gap_ids),
        "expected_translation_use": reference.expected_translation_use.value,
        "expected_parser_supported": reference.expected_parser_supported,
        "expected_re_evaluated_reference_proposition_ids": list(
            reference.expected_re_evaluated_reference_proposition_ids
        ),
        "prior_result_immutable_required": reference.prior_result_immutable_required,
        "adjudication_complete": reference.adjudication_complete,
        "unresolved_reference_ambiguity": reference.unresolved_reference_ambiguity,
    }


def _reference_candidate_document(
    candidate: HKCaseSemanticRiskReferenceCandidate,
) -> dict[str, JsonValue]:
    return {
        "reference_proposition_id": candidate.reference_proposition_id,
        "expected_resolution": candidate.expected_resolution.value,
        "issue_code": candidate.issue_code,
        "language": candidate.language.value,
        "source_version_id": candidate.source_version_id,
        "required_meaning_codes": list(candidate.required_meaning_codes),
        "required_risk_codes": list(candidate.required_risk_codes),
        "forbidden_risk_codes": list(candidate.forbidden_risk_codes),
        "required_range_ids": list(candidate.required_range_ids),
    }


def hk_case_semantic_risk_observation_document(
    observation: HKCaseSemanticRiskObservation,
) -> dict[str, JsonValue]:
    """Return the canonical post-run risk observation projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-risk-observation",
        "schema_version": HK_CASE_SEMANTIC_RISK_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_RISK_RULE_ID,
        "model_input_fingerprint": observation.model_input_fingerprint,
        "workflow_result_fingerprint": observation.workflow_result_fingerprint,
        "court_family": observation.court_family.value,
        "original_language": observation.original_language.value,
        "accepted_original_version_id": observation.accepted_original_version_id,
        "auxiliary_translation_version_ids": list(observation.auxiliary_translation_version_ids),
        "examined_segment_ids": list(observation.examined_segment_ids),
        "resolved_dependency_ids": list(observation.resolved_dependency_ids),
        "candidates": [_observed_candidate_document(item) for item in observation.candidates],
        "disposition": observation.disposition.value,
        "selected_candidate_ids": list(observation.selected_candidate_ids),
        "coverage_gap_ids": list(observation.coverage_gap_ids),
        "translation_use": observation.translation_use.value,
        "parser_supported": observation.parser_supported,
        "complete_ledger": observation.complete_ledger,
        "re_evaluated_candidate_ids": list(observation.re_evaluated_candidate_ids),
        "prior_result_immutable": observation.prior_result_immutable,
        "source_text_treated_as_instruction": observation.source_text_treated_as_instruction,
        "hidden_reference_received_by_workflow": observation.hidden_reference_received_by_workflow,
    }


def _observed_candidate_document(
    candidate: HKCaseSemanticRiskObservedCandidate,
) -> dict[str, JsonValue]:
    return {
        "candidate_id": candidate.candidate_id,
        "mapped_reference_proposition_id": candidate.mapped_reference_proposition_id,
        "resolution": candidate.resolution.value,
        "issue_code": candidate.issue_code,
        "language": candidate.language.value,
        "source_version_id": candidate.source_version_id,
        "meaning_codes": list(candidate.meaning_codes),
        "risk_codes": list(candidate.risk_codes),
        "range_ids": list(candidate.range_ids),
        "derived_statement": candidate.derived_statement,
    }


def hk_case_semantic_risk_evaluation_request_document(
    request: HKCaseSemanticRiskEvaluationRequest,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator request projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-risk-evaluation-request",
        "schema_version": HK_CASE_SEMANTIC_RISK_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_RISK_RULE_ID,
        "evaluator_fingerprint": request.evaluator_fingerprint,
        "reference": hk_case_semantic_risk_reference_document(request.reference),
        "observation": hk_case_semantic_risk_observation_document(request.observation),
    }


def hk_case_semantic_risk_result_document(
    result: HKCaseSemanticRiskEvaluationResult,
) -> dict[str, JsonValue]:
    """Return the canonical effect-free evaluator result."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-risk-evaluation-result",
        "schema_version": HK_CASE_SEMANTIC_RISK_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_RISK_RULE_ID,
        "request_fingerprint": result.request_fingerprint,
        "reference_map_fingerprint": result.reference_map_fingerprint,
        "outcome": result.outcome.value,
        "reasons": [item.value for item in result.reasons],
        "expected_candidate_count": result.expected_candidate_count,
        "observed_candidate_count": result.observed_candidate_count,
        "matched_candidate_count": result.matched_candidate_count,
        "accepted_candidate_count": result.accepted_candidate_count,
        "quarantined_candidate_count": result.quarantined_candidate_count,
        "examined_segment_count": result.examined_segment_count,
        "resolved_dependency_count": result.resolved_dependency_count,
        "provider_calls_authorized": result.provider_calls_authorized,
        "workflow_admission_created": result.workflow_admission_created,
        "search_records_created": result.search_records_created,
        "release_eligible": result.release_eligible,
        "external_effects": result.external_effects,
    }


def hk_case_semantic_risk_evaluation_request_from_document(
    document: object,
) -> HKCaseSemanticRiskEvaluationRequest:
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
    _constants(root, "asklegal.hk-cases.semantic-risk-evaluation-request")
    return HKCaseSemanticRiskEvaluationRequest(
        evaluator_fingerprint=_fingerprint(root["evaluator_fingerprint"]),
        reference=_reference(root["reference"]),
        observation=_observation(root["observation"]),
    )


def _reference(value: JsonValue) -> HKCaseSemanticRiskReference:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "reference_map_id",
            "model_input_fingerprint",
            "court_family",
            "original_language",
            "accepted_original_version_id",
            "auxiliary_translation_version_ids",
            "expected_examined_segment_ids",
            "expected_resolved_dependency_ids",
            "candidates",
            "expected_disposition",
            "expected_selected_reference_proposition_ids",
            "expected_coverage_gap_ids",
            "expected_translation_use",
            "expected_parser_supported",
            "expected_re_evaluated_reference_proposition_ids",
            "prior_result_immutable_required",
            "adjudication_complete",
            "unresolved_reference_ambiguity",
        },
    )
    _constants(root, "asklegal.hk-cases.semantic-risk-reference")
    return HKCaseSemanticRiskReference(
        reference_map_id=_identity(root["reference_map_id"]),
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        court_family=_enum(root["court_family"], HKCaseSemanticRiskCourtFamily),
        original_language=_enum(root["original_language"], HKCaseSemanticRiskLanguage),
        accepted_original_version_id=_identity(root["accepted_original_version_id"]),
        auxiliary_translation_version_ids=_identities(root["auxiliary_translation_version_ids"]),
        expected_examined_segment_ids=_identities(root["expected_examined_segment_ids"]),
        expected_resolved_dependency_ids=_identities(root["expected_resolved_dependency_ids"]),
        candidates=tuple(_reference_candidate(item) for item in _array(root["candidates"])),
        expected_disposition=_enum(root["expected_disposition"], HKCaseSemanticRiskDisposition),
        expected_selected_reference_proposition_ids=_identities(
            root["expected_selected_reference_proposition_ids"]
        ),
        expected_coverage_gap_ids=_identities(root["expected_coverage_gap_ids"]),
        expected_translation_use=_enum(
            root["expected_translation_use"], HKCaseSemanticRiskTranslationUse
        ),
        expected_parser_supported=_boolean(root["expected_parser_supported"]),
        expected_re_evaluated_reference_proposition_ids=_identities(
            root["expected_re_evaluated_reference_proposition_ids"]
        ),
        prior_result_immutable_required=_boolean(root["prior_result_immutable_required"]),
        adjudication_complete=_boolean(root["adjudication_complete"]),
        unresolved_reference_ambiguity=_boolean(root["unresolved_reference_ambiguity"]),
    )


def _reference_candidate(value: JsonValue) -> HKCaseSemanticRiskReferenceCandidate:
    root = _object(value)
    _exact_keys(
        root,
        {
            "reference_proposition_id",
            "expected_resolution",
            "issue_code",
            "language",
            "source_version_id",
            "required_meaning_codes",
            "required_risk_codes",
            "forbidden_risk_codes",
            "required_range_ids",
        },
    )
    return HKCaseSemanticRiskReferenceCandidate(
        reference_proposition_id=_identity(root["reference_proposition_id"]),
        expected_resolution=_enum(root["expected_resolution"], HKCaseSemanticRiskResolution),
        issue_code=_code(root["issue_code"]),
        language=_enum(root["language"], HKCaseSemanticRiskLanguage),
        source_version_id=_identity(root["source_version_id"]),
        required_meaning_codes=_codes(root["required_meaning_codes"]),
        required_risk_codes=_codes(root["required_risk_codes"]),
        forbidden_risk_codes=_codes(root["forbidden_risk_codes"]),
        required_range_ids=_identities(root["required_range_ids"]),
    )


def _observation(value: JsonValue) -> HKCaseSemanticRiskObservation:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "model_input_fingerprint",
            "workflow_result_fingerprint",
            "court_family",
            "original_language",
            "accepted_original_version_id",
            "auxiliary_translation_version_ids",
            "examined_segment_ids",
            "resolved_dependency_ids",
            "candidates",
            "disposition",
            "selected_candidate_ids",
            "coverage_gap_ids",
            "translation_use",
            "parser_supported",
            "complete_ledger",
            "re_evaluated_candidate_ids",
            "prior_result_immutable",
            "source_text_treated_as_instruction",
            "hidden_reference_received_by_workflow",
        },
    )
    _constants(root, "asklegal.hk-cases.semantic-risk-observation")
    return HKCaseSemanticRiskObservation(
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        workflow_result_fingerprint=_fingerprint(root["workflow_result_fingerprint"]),
        court_family=_enum(root["court_family"], HKCaseSemanticRiskCourtFamily),
        original_language=_enum(root["original_language"], HKCaseSemanticRiskLanguage),
        accepted_original_version_id=_identity(root["accepted_original_version_id"]),
        auxiliary_translation_version_ids=_identities(root["auxiliary_translation_version_ids"]),
        examined_segment_ids=_identities(root["examined_segment_ids"]),
        resolved_dependency_ids=_identities(root["resolved_dependency_ids"]),
        candidates=tuple(_observed_candidate(item) for item in _array(root["candidates"])),
        disposition=_enum(root["disposition"], HKCaseSemanticRiskDisposition),
        selected_candidate_ids=_identities(root["selected_candidate_ids"]),
        coverage_gap_ids=_identities(root["coverage_gap_ids"]),
        translation_use=_enum(root["translation_use"], HKCaseSemanticRiskTranslationUse),
        parser_supported=_boolean(root["parser_supported"]),
        complete_ledger=_boolean(root["complete_ledger"]),
        re_evaluated_candidate_ids=_identities(root["re_evaluated_candidate_ids"]),
        prior_result_immutable=_boolean(root["prior_result_immutable"]),
        source_text_treated_as_instruction=_boolean(root["source_text_treated_as_instruction"]),
        hidden_reference_received_by_workflow=_boolean(
            root["hidden_reference_received_by_workflow"]
        ),
    )


def _observed_candidate(value: JsonValue) -> HKCaseSemanticRiskObservedCandidate:
    root = _object(value)
    _exact_keys(
        root,
        {
            "candidate_id",
            "mapped_reference_proposition_id",
            "resolution",
            "issue_code",
            "language",
            "source_version_id",
            "meaning_codes",
            "risk_codes",
            "range_ids",
            "derived_statement",
        },
    )
    return HKCaseSemanticRiskObservedCandidate(
        candidate_id=_identity(root["candidate_id"]),
        mapped_reference_proposition_id=_optional_identity(root["mapped_reference_proposition_id"]),
        resolution=_enum(root["resolution"], HKCaseSemanticRiskResolution),
        issue_code=_code(root["issue_code"]),
        language=_enum(root["language"], HKCaseSemanticRiskLanguage),
        source_version_id=_identity(root["source_version_id"]),
        meaning_codes=_codes(root["meaning_codes"]),
        risk_codes=_codes(root["risk_codes"]),
        range_ids=_identities(root["range_ids"]),
        derived_statement=_optional_string(root["derived_statement"]),
    )


def _object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if not isinstance(checked, dict):
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.CONTRACT)
    return checked


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.CONTRACT)
    return value


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.CONTRACT)


def _constants(root: dict[str, JsonValue], schema_id: str) -> None:
    if (
        root["schema_id"] != schema_id
        or root["schema_version"] != HK_CASE_SEMANTIC_RISK_CONTRACT_VERSION
        or root["rule_id"] != HK_CASE_SEMANTIC_RISK_RULE_ID
    ):
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.CONTRACT)


def _string(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.CONTRACT)
    return value


def _optional_string(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _string(value)


def _identity(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_IDENTITY_PATTERN, result) is None:
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.IDENTITY)
    return result


def _optional_identity(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _identity(value)


def _identities(value: JsonValue) -> tuple[str, ...]:
    return tuple(_identity(item) for item in _array(value))


def _code(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_CODE_PATTERN, result) is None:
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.CONTRACT)
    return result


def _codes(value: JsonValue) -> tuple[str, ...]:
    return tuple(_code(item) for item in _array(value))


def _fingerprint(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.FINGERPRINT)
    return result


def _boolean(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.CONTRACT)
    return value


def _enum[T: StrEnum](value: JsonValue, enum_type: type[T]) -> T:
    raw = _string(value)
    try:
        return enum_type(raw)
    except ValueError:
        raise HKCaseSemanticRiskError(HKCaseSemanticRiskErrorCode.CONTRACT) from None


def _duplicates(values: tuple[object, ...]) -> bool:
    return len(set(values)) != len(values)
