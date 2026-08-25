"""Deterministic evaluator for Hong Kong Case proposition and opinion boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_case_coverage_ledger import HKCaseOpinionRole

HK_CASE_SEMANTIC_BOUNDARY_CONTRACT_VERSION = "1.0.0"
HK_CASE_SEMANTIC_BOUNDARY_RULE_ID = "HKCASE-PROP-SEM-BOUNDARY-EVALUATOR-001"

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_IDENTITY_PATTERN = r"[a-z][a-z0-9_]{2,95}"
_CODE_PATTERN = r"[A-Z][A-Z0-9_]{2,95}"


class HKCaseSemanticBoundaryErrorCode(StrEnum):
    """Closed malformed evaluator-input failures."""

    CONTRACT = "HK_CASE_SEMANTIC_BOUNDARY_CONTRACT_INVALID"
    FINGERPRINT = "HK_CASE_SEMANTIC_BOUNDARY_FINGERPRINT_INVALID"
    IDENTITY = "HK_CASE_SEMANTIC_BOUNDARY_IDENTITY_INVALID"


class HKCaseSemanticBoundaryError(ValueError):
    """One strict semantic-boundary contract failure."""

    code: HKCaseSemanticBoundaryErrorCode

    def __init__(self, code: HKCaseSemanticBoundaryErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKCaseSemanticBoundaryDisposition(StrEnum):
    """Closed judgment-wide dispositions used by this checkpoint."""

    ACCOUNTED_WITH_QUARANTINE = "ACCOUNTED_WITH_QUARANTINE"
    COMPLETE_WITH_PROPOSITIONS = "COMPLETE_WITH_PROPOSITIONS"


class HKCaseSemanticBoundaryResolution(StrEnum):
    """The adjudicated consequence for one boundary candidate."""

    ACCEPTED = "ACCEPTED"
    QUARANTINED = "QUARANTINED"


class HKCaseSemanticBoundaryAuthorityRole(StrEnum):
    """Exact authority role of one proposition reasoning path."""

    ADOPTED_OPERATIVE = "ADOPTED_OPERATIVE"
    CONCURRENCE = "CONCURRENCE"
    DISSENT = "DISSENT"
    OBITER = "OBITER"
    OPERATIVE = "OPERATIVE"
    PLURALITY = "PLURALITY"


class HKCaseSemanticBoundaryUnitUse(StrEnum):
    """One exact primary-unit use in the boundary ledger."""

    AGREEMENT_ONLY = "AGREEMENT_ONLY"
    NON_PROPOSITIONAL = "NON_PROPOSITIONAL"
    PROPOSITION_EVIDENCE = "PROPOSITION_EVIDENCE"


class HKCaseSemanticBoundaryOutcome(StrEnum):
    """Deterministic evaluator outcomes."""

    EVALUATOR_BLOCKED = "EVALUATOR_BLOCKED"
    FAIL = "FAIL"
    PASS = "PASS"


class HKCaseSemanticBoundaryReason(StrEnum):
    """Closed proposition-boundary evaluator reasons."""

    AUTHORITY_ROLE_MISMATCH = "AUTHORITY_ROLE_MISMATCH"
    BOUNDARY_MISMATCH = "BOUNDARY_MISMATCH"
    CANDIDATE_INVENTORY_MISMATCH = "CANDIDATE_INVENTORY_MISMATCH"
    DISPOSITION_MISMATCH = "DISPOSITION_MISMATCH"
    EVALUATION_LEAKAGE = "EVALUATION_LEAKAGE"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    ISSUE_MISMATCH = "ISSUE_MISMATCH"
    MEANING_MISMATCH = "MEANING_MISMATCH"
    OBSERVATION_BINDING_INVALID = "OBSERVATION_BINDING_INVALID"
    OPINION_INVENTORY_MISMATCH = "OPINION_INVENTORY_MISMATCH"
    OPINION_PATH_MISMATCH = "OPINION_PATH_MISMATCH"
    PASS = "PASS"
    REFERENCE_BLOCKED = "REFERENCE_BLOCKED"
    REFERENCE_INVALID = "REFERENCE_INVALID"
    RESOLUTION_MISMATCH = "RESOLUTION_MISMATCH"
    SELECTION_MISMATCH = "SELECTION_MISMATCH"
    STATEMENT_STATE_MISMATCH = "STATEMENT_STATE_MISMATCH"
    UNIT_ACCOUNTING_MISMATCH = "UNIT_ACCOUNTING_MISMATCH"


@dataclass(frozen=True, slots=True)
class HKCaseSemanticBoundaryOpinion:
    """One exact delivered-opinion path and its express relationships."""

    opinion_id: str
    role: HKCaseOpinionRole
    judge_ids: tuple[str, ...]
    joined_opinion_id: str | None
    expressly_adopted_opinion_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticBoundaryReferenceProposition:
    """One hidden adjudicated proposition-boundary assertion set."""

    reference_proposition_id: str
    expected_resolution: HKCaseSemanticBoundaryResolution
    issue_code: str
    authority_role: HKCaseSemanticBoundaryAuthorityRole
    opinion_path_ids: tuple[str, ...]
    required_meaning_codes: tuple[str, ...]
    required_boundary_codes: tuple[str, ...]
    forbidden_boundary_codes: tuple[str, ...]
    required_range_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticBoundaryReferenceUnit:
    """One evaluator-only expected primary-unit accounting row."""

    unit_id: str
    opinion_id: str
    use: HKCaseSemanticBoundaryUnitUse
    reference_proposition_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticBoundaryReference:
    """Evaluator-only boundary map for one synthetic judgment."""

    reference_map_id: str
    model_input_fingerprint: str
    opinions: tuple[HKCaseSemanticBoundaryOpinion, ...]
    propositions: tuple[HKCaseSemanticBoundaryReferenceProposition, ...]
    units: tuple[HKCaseSemanticBoundaryReferenceUnit, ...]
    expected_disposition: HKCaseSemanticBoundaryDisposition
    expected_selected_reference_proposition_ids: tuple[str, ...]
    adjudication_complete: bool
    unresolved_reference_ambiguity: bool


@dataclass(frozen=True, slots=True)
class HKCaseSemanticBoundaryObservedProposition:
    """One post-run proposition reduced to evaluator-visible boundary facts."""

    candidate_id: str
    mapped_reference_proposition_id: str | None
    resolution: HKCaseSemanticBoundaryResolution
    issue_code: str
    authority_role: HKCaseSemanticBoundaryAuthorityRole
    opinion_path_ids: tuple[str, ...]
    meaning_codes: tuple[str, ...]
    boundary_codes: tuple[str, ...]
    range_ids: tuple[str, ...]
    derived_statement: str | None


@dataclass(frozen=True, slots=True)
class HKCaseSemanticBoundaryObservedUnit:
    """One observed primary-unit accounting row."""

    unit_id: str
    opinion_id: str
    use: HKCaseSemanticBoundaryUnitUse
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticBoundaryObservation:
    """One candidate workflow result reduced to evaluator-visible facts."""

    model_input_fingerprint: str
    workflow_result_fingerprint: str
    opinions: tuple[HKCaseSemanticBoundaryOpinion, ...]
    propositions: tuple[HKCaseSemanticBoundaryObservedProposition, ...]
    units: tuple[HKCaseSemanticBoundaryObservedUnit, ...]
    disposition: HKCaseSemanticBoundaryDisposition
    selected_candidate_ids: tuple[str, ...]
    complete_ledger: bool
    source_text_treated_as_instruction: bool
    hidden_reference_received_by_workflow: bool


@dataclass(frozen=True, slots=True)
class HKCaseSemanticBoundaryEvaluationRequest:
    """One evaluator-only reference and one post-run observation."""

    evaluator_fingerprint: str
    reference: HKCaseSemanticBoundaryReference
    observation: HKCaseSemanticBoundaryObservation


@dataclass(frozen=True, slots=True)
class HKCaseSemanticBoundaryEvaluationResult:
    """One effect-free deterministic boundary comparison."""

    request_fingerprint: str
    reference_map_fingerprint: str
    outcome: HKCaseSemanticBoundaryOutcome
    reasons: tuple[HKCaseSemanticBoundaryReason, ...]
    expected_candidate_count: int
    observed_candidate_count: int
    matched_candidate_count: int
    accepted_candidate_count: int
    quarantined_candidate_count: int
    opinion_count: int
    complete_unit_count: int
    provider_calls_authorized: int
    workflow_admission_created: bool
    search_records_created: int
    release_eligible: bool
    external_effects: str


def evaluate_hk_case_semantic_boundary(
    request: HKCaseSemanticBoundaryEvaluationRequest,
) -> HKCaseSemanticBoundaryEvaluationResult:
    """Compare legal boundaries and opinion paths without case identity or effects."""
    request_document = hk_case_semantic_boundary_evaluation_request_document(request)
    request_fingerprint = fingerprint(checked_json_value(request_document))
    reference_document = hk_case_semantic_boundary_reference_document(request.reference)
    reference_fingerprint = fingerprint(checked_json_value(reference_document))
    reasons = _reference_reasons(request.reference) | _observation_reasons(request)
    if HKCaseSemanticBoundaryReason.REFERENCE_BLOCKED in reasons:
        outcome = HKCaseSemanticBoundaryOutcome.EVALUATOR_BLOCKED
    elif reasons:
        outcome = HKCaseSemanticBoundaryOutcome.FAIL
    else:
        outcome = HKCaseSemanticBoundaryOutcome.PASS
        reasons = {HKCaseSemanticBoundaryReason.PASS}
    return HKCaseSemanticBoundaryEvaluationResult(
        request_fingerprint=request_fingerprint,
        reference_map_fingerprint=reference_fingerprint,
        outcome=outcome,
        reasons=tuple(sorted(reasons, key=lambda item: item.value)),
        expected_candidate_count=len(request.reference.propositions),
        observed_candidate_count=len(request.observation.propositions),
        matched_candidate_count=_matched_candidate_count(request),
        accepted_candidate_count=sum(
            item.resolution is HKCaseSemanticBoundaryResolution.ACCEPTED
            for item in request.observation.propositions
        ),
        quarantined_candidate_count=sum(
            item.resolution is HKCaseSemanticBoundaryResolution.QUARANTINED
            for item in request.observation.propositions
        ),
        opinion_count=len(request.observation.opinions),
        complete_unit_count=len(request.observation.units),
        provider_calls_authorized=0,
        workflow_admission_created=False,
        search_records_created=0,
        release_eligible=False,
        external_effects="NONE",
    )


def _reference_reasons(
    reference: HKCaseSemanticBoundaryReference,
) -> set[HKCaseSemanticBoundaryReason]:
    reasons: set[HKCaseSemanticBoundaryReason] = set()
    opinion_ids = tuple(item.opinion_id for item in reference.opinions)
    reference_ids = tuple(item.reference_proposition_id for item in reference.propositions)
    unit_ids = tuple(item.unit_id for item in reference.units)
    accepted_ids = tuple(
        item.reference_proposition_id
        for item in reference.propositions
        if item.expected_resolution is HKCaseSemanticBoundaryResolution.ACCEPTED
    )
    selected = reference.expected_selected_reference_proposition_ids
    disposition_valid = (
        reference.expected_disposition
        is HKCaseSemanticBoundaryDisposition.COMPLETE_WITH_PROPOSITIONS
        and bool(accepted_ids)
        and len(accepted_ids) == len(reference.propositions)
    ) or (
        reference.expected_disposition
        is HKCaseSemanticBoundaryDisposition.ACCOUNTED_WITH_QUARANTINE
        and bool(reference.propositions)
        and not accepted_ids
        and not selected
    )
    if (
        not reference.opinions
        or not reference.propositions
        or not reference.units
        or _duplicates(opinion_ids)
        or _duplicates(reference_ids)
        or _duplicates(unit_ids)
        or _duplicates(selected)
        or not set(selected).issubset(accepted_ids)
        or any(not _opinion_valid(item, opinion_ids) for item in reference.opinions)
        or any(
            not _reference_proposition_valid(item, opinion_ids) for item in reference.propositions
        )
        or any(
            item.opinion_id not in opinion_ids
            or _duplicates(item.reference_proposition_ids)
            or not set(item.reference_proposition_ids).issubset(reference_ids)
            for item in reference.units
        )
        or not disposition_valid
    ):
        reasons.add(HKCaseSemanticBoundaryReason.REFERENCE_INVALID)
    if not reference.adjudication_complete or reference.unresolved_reference_ambiguity:
        reasons.add(HKCaseSemanticBoundaryReason.REFERENCE_BLOCKED)
    return reasons


def _opinion_valid(
    opinion: HKCaseSemanticBoundaryOpinion,
    opinion_ids: tuple[str, ...],
) -> bool:
    return (
        bool(opinion.judge_ids)
        and not _duplicates(opinion.judge_ids)
        and not _duplicates(opinion.expressly_adopted_opinion_ids)
        and opinion.joined_opinion_id != opinion.opinion_id
        and (opinion.joined_opinion_id is None or opinion.joined_opinion_id in opinion_ids)
        and opinion.opinion_id not in opinion.expressly_adopted_opinion_ids
        and set(opinion.expressly_adopted_opinion_ids).issubset(opinion_ids)
    )


def _reference_proposition_valid(
    proposition: HKCaseSemanticBoundaryReferenceProposition,
    opinion_ids: tuple[str, ...],
) -> bool:
    return (
        bool(proposition.issue_code)
        and bool(proposition.opinion_path_ids)
        and bool(proposition.required_meaning_codes)
        and bool(proposition.required_boundary_codes)
        and bool(proposition.required_range_ids)
        and not _duplicates(proposition.opinion_path_ids)
        and set(proposition.opinion_path_ids).issubset(opinion_ids)
        and not _duplicates(proposition.required_meaning_codes)
        and not _duplicates(proposition.required_boundary_codes)
        and not _duplicates(proposition.forbidden_boundary_codes)
        and not _duplicates(proposition.required_range_ids)
        and not set(proposition.required_boundary_codes).intersection(
            proposition.forbidden_boundary_codes
        )
    )


def _observation_reasons(
    request: HKCaseSemanticBoundaryEvaluationRequest,
) -> set[HKCaseSemanticBoundaryReason]:
    reference = request.reference
    observation = request.observation
    reasons: set[HKCaseSemanticBoundaryReason] = set()
    if (
        observation.model_input_fingerprint != reference.model_input_fingerprint
        or fullmatch(_FINGERPRINT_PATTERN, request.evaluator_fingerprint) is None
        or fullmatch(_FINGERPRINT_PATTERN, observation.workflow_result_fingerprint) is None
    ):
        reasons.add(HKCaseSemanticBoundaryReason.OBSERVATION_BINDING_INVALID)
    if observation.opinions != reference.opinions:
        reasons.add(HKCaseSemanticBoundaryReason.OPINION_INVENTORY_MISMATCH)
    if not _candidate_inventory_valid(request):
        reasons.add(HKCaseSemanticBoundaryReason.CANDIDATE_INVENTORY_MISMATCH)
    reasons.update(_mapped_candidate_reasons(request))
    if not _unit_accounting_valid(request):
        reasons.add(HKCaseSemanticBoundaryReason.UNIT_ACCOUNTING_MISMATCH)
    if observation.disposition is not reference.expected_disposition:
        reasons.add(HKCaseSemanticBoundaryReason.DISPOSITION_MISMATCH)
    if not _selection_valid(request):
        reasons.add(HKCaseSemanticBoundaryReason.SELECTION_MISMATCH)
    if (
        observation.source_text_treated_as_instruction
        or observation.hidden_reference_received_by_workflow
    ):
        reasons.add(HKCaseSemanticBoundaryReason.EVALUATION_LEAKAGE)
    return reasons


def _candidate_inventory_valid(request: HKCaseSemanticBoundaryEvaluationRequest) -> bool:
    reference_ids = tuple(item.reference_proposition_id for item in request.reference.propositions)
    mapped_ids = tuple(
        item.mapped_reference_proposition_id for item in request.observation.propositions
    )
    candidate_ids = tuple(item.candidate_id for item in request.observation.propositions)
    return (
        not _duplicates(candidate_ids)
        and len(mapped_ids) == len(reference_ids)
        and all(item is not None for item in mapped_ids)
        and sorted(item for item in mapped_ids if item is not None) == sorted(reference_ids)
    )


def _matched_candidate_count(request: HKCaseSemanticBoundaryEvaluationRequest) -> int:
    return sum(
        sum(
            observed.mapped_reference_proposition_id == expected.reference_proposition_id
            for observed in request.observation.propositions
        )
        == 1
        for expected in request.reference.propositions
    )


def _mapped_candidate_reasons(
    request: HKCaseSemanticBoundaryEvaluationRequest,
) -> set[HKCaseSemanticBoundaryReason]:
    references = {item.reference_proposition_id: item for item in request.reference.propositions}
    reasons: set[HKCaseSemanticBoundaryReason] = set()
    for observed in request.observation.propositions:
        expected = references.get(observed.mapped_reference_proposition_id or "")
        if expected is None:
            continue
        reasons.update(_candidate_reasons(expected, observed))
    return reasons


def _candidate_reasons(
    expected: HKCaseSemanticBoundaryReferenceProposition,
    observed: HKCaseSemanticBoundaryObservedProposition,
) -> set[HKCaseSemanticBoundaryReason]:
    reasons: set[HKCaseSemanticBoundaryReason] = set()
    if observed.resolution is not expected.expected_resolution:
        reasons.add(HKCaseSemanticBoundaryReason.RESOLUTION_MISMATCH)
    if observed.issue_code != expected.issue_code:
        reasons.add(HKCaseSemanticBoundaryReason.ISSUE_MISMATCH)
    if observed.authority_role is not expected.authority_role:
        reasons.add(HKCaseSemanticBoundaryReason.AUTHORITY_ROLE_MISMATCH)
    if observed.opinion_path_ids != expected.opinion_path_ids:
        reasons.add(HKCaseSemanticBoundaryReason.OPINION_PATH_MISMATCH)
    if not set(expected.required_meaning_codes).issubset(observed.meaning_codes):
        reasons.add(HKCaseSemanticBoundaryReason.MEANING_MISMATCH)
    if not set(expected.required_boundary_codes).issubset(observed.boundary_codes) or set(
        expected.forbidden_boundary_codes
    ).intersection(observed.boundary_codes):
        reasons.add(HKCaseSemanticBoundaryReason.BOUNDARY_MISMATCH)
    if observed.range_ids != expected.required_range_ids:
        reasons.add(HKCaseSemanticBoundaryReason.EVIDENCE_MISMATCH)
    if not _statement_state_valid(expected, observed):
        reasons.add(HKCaseSemanticBoundaryReason.STATEMENT_STATE_MISMATCH)
    return reasons


def _statement_state_valid(
    expected: HKCaseSemanticBoundaryReferenceProposition,
    observed: HKCaseSemanticBoundaryObservedProposition,
) -> bool:
    return (
        expected.expected_resolution is HKCaseSemanticBoundaryResolution.ACCEPTED
        and observed.derived_statement is not None
        and bool(observed.derived_statement.strip())
    ) or (
        expected.expected_resolution is HKCaseSemanticBoundaryResolution.QUARANTINED
        and observed.derived_statement is None
    )


def _unit_accounting_valid(request: HKCaseSemanticBoundaryEvaluationRequest) -> bool:
    observation = request.observation
    mapping = {
        item.candidate_id: item.mapped_reference_proposition_id
        for item in observation.propositions
        if item.mapped_reference_proposition_id is not None
    }
    observed_rows = tuple(
        (
            item.unit_id,
            item.opinion_id,
            item.use,
            tuple(mapping.get(candidate_id) for candidate_id in item.candidate_ids),
        )
        for item in observation.units
    )
    expected_rows = tuple(
        (item.unit_id, item.opinion_id, item.use, item.reference_proposition_ids)
        for item in request.reference.units
    )
    return (
        observation.complete_ledger
        and not _duplicates(tuple(item.unit_id for item in observation.units))
        and all(
            candidate_id in mapping
            for item in observation.units
            for candidate_id in item.candidate_ids
        )
        and observed_rows == expected_rows
    )


def _selection_valid(request: HKCaseSemanticBoundaryEvaluationRequest) -> bool:
    observation = request.observation
    mapping = {
        item.candidate_id: item.mapped_reference_proposition_id for item in observation.propositions
    }
    return (
        not _duplicates(observation.selected_candidate_ids)
        and tuple(mapping.get(item) for item in observation.selected_candidate_ids)
        == request.reference.expected_selected_reference_proposition_ids
    )


def hk_case_semantic_boundary_reference_document(
    reference: HKCaseSemanticBoundaryReference,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator-only boundary reference projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-boundary-reference",
        "schema_version": HK_CASE_SEMANTIC_BOUNDARY_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_BOUNDARY_RULE_ID,
        "reference_map_id": reference.reference_map_id,
        "model_input_fingerprint": reference.model_input_fingerprint,
        "opinions": [_opinion_document(item) for item in reference.opinions],
        "propositions": [
            {
                "reference_proposition_id": item.reference_proposition_id,
                "expected_resolution": item.expected_resolution.value,
                "issue_code": item.issue_code,
                "authority_role": item.authority_role.value,
                "opinion_path_ids": list(item.opinion_path_ids),
                "required_meaning_codes": list(item.required_meaning_codes),
                "required_boundary_codes": list(item.required_boundary_codes),
                "forbidden_boundary_codes": list(item.forbidden_boundary_codes),
                "required_range_ids": list(item.required_range_ids),
            }
            for item in reference.propositions
        ],
        "units": [
            {
                "unit_id": item.unit_id,
                "opinion_id": item.opinion_id,
                "use": item.use.value,
                "reference_proposition_ids": list(item.reference_proposition_ids),
            }
            for item in reference.units
        ],
        "expected_disposition": reference.expected_disposition.value,
        "expected_selected_reference_proposition_ids": list(
            reference.expected_selected_reference_proposition_ids
        ),
        "adjudication_complete": reference.adjudication_complete,
        "unresolved_reference_ambiguity": reference.unresolved_reference_ambiguity,
    }


def hk_case_semantic_boundary_observation_document(
    observation: HKCaseSemanticBoundaryObservation,
) -> dict[str, JsonValue]:
    """Return the canonical post-run boundary observation projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-boundary-observation",
        "schema_version": HK_CASE_SEMANTIC_BOUNDARY_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_BOUNDARY_RULE_ID,
        "model_input_fingerprint": observation.model_input_fingerprint,
        "workflow_result_fingerprint": observation.workflow_result_fingerprint,
        "opinions": [_opinion_document(item) for item in observation.opinions],
        "propositions": [
            {
                "candidate_id": item.candidate_id,
                "mapped_reference_proposition_id": item.mapped_reference_proposition_id,
                "resolution": item.resolution.value,
                "issue_code": item.issue_code,
                "authority_role": item.authority_role.value,
                "opinion_path_ids": list(item.opinion_path_ids),
                "meaning_codes": list(item.meaning_codes),
                "boundary_codes": list(item.boundary_codes),
                "range_ids": list(item.range_ids),
                "derived_statement": item.derived_statement,
            }
            for item in observation.propositions
        ],
        "units": [
            {
                "unit_id": item.unit_id,
                "opinion_id": item.opinion_id,
                "use": item.use.value,
                "candidate_ids": list(item.candidate_ids),
            }
            for item in observation.units
        ],
        "disposition": observation.disposition.value,
        "selected_candidate_ids": list(observation.selected_candidate_ids),
        "complete_ledger": observation.complete_ledger,
        "source_text_treated_as_instruction": observation.source_text_treated_as_instruction,
        "hidden_reference_received_by_workflow": observation.hidden_reference_received_by_workflow,
    }


def _opinion_document(opinion: HKCaseSemanticBoundaryOpinion) -> dict[str, JsonValue]:
    return {
        "opinion_id": opinion.opinion_id,
        "role": opinion.role.value,
        "judge_ids": list(opinion.judge_ids),
        "joined_opinion_id": opinion.joined_opinion_id,
        "expressly_adopted_opinion_ids": list(opinion.expressly_adopted_opinion_ids),
    }


def hk_case_semantic_boundary_evaluation_request_document(
    request: HKCaseSemanticBoundaryEvaluationRequest,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator request projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-boundary-evaluation-request",
        "schema_version": HK_CASE_SEMANTIC_BOUNDARY_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_BOUNDARY_RULE_ID,
        "evaluator_fingerprint": request.evaluator_fingerprint,
        "reference": hk_case_semantic_boundary_reference_document(request.reference),
        "observation": hk_case_semantic_boundary_observation_document(request.observation),
    }


def hk_case_semantic_boundary_result_document(
    result: HKCaseSemanticBoundaryEvaluationResult,
) -> dict[str, JsonValue]:
    """Return the canonical effect-free evaluator result."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-boundary-evaluation-result",
        "schema_version": HK_CASE_SEMANTIC_BOUNDARY_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_BOUNDARY_RULE_ID,
        "request_fingerprint": result.request_fingerprint,
        "reference_map_fingerprint": result.reference_map_fingerprint,
        "outcome": result.outcome.value,
        "reasons": [item.value for item in result.reasons],
        "expected_candidate_count": result.expected_candidate_count,
        "observed_candidate_count": result.observed_candidate_count,
        "matched_candidate_count": result.matched_candidate_count,
        "accepted_candidate_count": result.accepted_candidate_count,
        "quarantined_candidate_count": result.quarantined_candidate_count,
        "opinion_count": result.opinion_count,
        "complete_unit_count": result.complete_unit_count,
        "provider_calls_authorized": result.provider_calls_authorized,
        "workflow_admission_created": result.workflow_admission_created,
        "search_records_created": result.search_records_created,
        "release_eligible": result.release_eligible,
        "external_effects": result.external_effects,
    }


def hk_case_semantic_boundary_evaluation_request_from_document(
    document: object,
) -> HKCaseSemanticBoundaryEvaluationRequest:
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
    _constants(root, "asklegal.hk-cases.semantic-boundary-evaluation-request")
    return HKCaseSemanticBoundaryEvaluationRequest(
        evaluator_fingerprint=_fingerprint(root["evaluator_fingerprint"]),
        reference=_reference(root["reference"]),
        observation=_observation(root["observation"]),
    )


def _reference(value: JsonValue) -> HKCaseSemanticBoundaryReference:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "reference_map_id",
            "model_input_fingerprint",
            "opinions",
            "propositions",
            "units",
            "expected_disposition",
            "expected_selected_reference_proposition_ids",
            "adjudication_complete",
            "unresolved_reference_ambiguity",
        },
    )
    _constants(root, "asklegal.hk-cases.semantic-boundary-reference")
    return HKCaseSemanticBoundaryReference(
        reference_map_id=_identity(root["reference_map_id"]),
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        opinions=tuple(_opinion(item) for item in _array(root["opinions"])),
        propositions=tuple(_reference_proposition(item) for item in _array(root["propositions"])),
        units=tuple(_reference_unit(item) for item in _array(root["units"])),
        expected_disposition=_enum(root["expected_disposition"], HKCaseSemanticBoundaryDisposition),
        expected_selected_reference_proposition_ids=_identities(
            root["expected_selected_reference_proposition_ids"]
        ),
        adjudication_complete=_boolean(root["adjudication_complete"]),
        unresolved_reference_ambiguity=_boolean(root["unresolved_reference_ambiguity"]),
    )


def _opinion(value: JsonValue) -> HKCaseSemanticBoundaryOpinion:
    root = _object(value)
    _exact_keys(
        root,
        {
            "opinion_id",
            "role",
            "judge_ids",
            "joined_opinion_id",
            "expressly_adopted_opinion_ids",
        },
    )
    return HKCaseSemanticBoundaryOpinion(
        opinion_id=_identity(root["opinion_id"]),
        role=_enum(root["role"], HKCaseOpinionRole),
        judge_ids=_identities(root["judge_ids"]),
        joined_opinion_id=_optional_identity(root["joined_opinion_id"]),
        expressly_adopted_opinion_ids=_identities(root["expressly_adopted_opinion_ids"]),
    )


def _reference_proposition(value: JsonValue) -> HKCaseSemanticBoundaryReferenceProposition:
    root = _object(value)
    _exact_keys(
        root,
        {
            "reference_proposition_id",
            "expected_resolution",
            "issue_code",
            "authority_role",
            "opinion_path_ids",
            "required_meaning_codes",
            "required_boundary_codes",
            "forbidden_boundary_codes",
            "required_range_ids",
        },
    )
    return HKCaseSemanticBoundaryReferenceProposition(
        reference_proposition_id=_identity(root["reference_proposition_id"]),
        expected_resolution=_enum(root["expected_resolution"], HKCaseSemanticBoundaryResolution),
        issue_code=_code(root["issue_code"]),
        authority_role=_enum(root["authority_role"], HKCaseSemanticBoundaryAuthorityRole),
        opinion_path_ids=_identities(root["opinion_path_ids"]),
        required_meaning_codes=_codes(root["required_meaning_codes"]),
        required_boundary_codes=_codes(root["required_boundary_codes"]),
        forbidden_boundary_codes=_codes(root["forbidden_boundary_codes"]),
        required_range_ids=_identities(root["required_range_ids"]),
    )


def _reference_unit(value: JsonValue) -> HKCaseSemanticBoundaryReferenceUnit:
    root = _object(value)
    _exact_keys(root, {"unit_id", "opinion_id", "use", "reference_proposition_ids"})
    return HKCaseSemanticBoundaryReferenceUnit(
        unit_id=_identity(root["unit_id"]),
        opinion_id=_identity(root["opinion_id"]),
        use=_enum(root["use"], HKCaseSemanticBoundaryUnitUse),
        reference_proposition_ids=_identities(root["reference_proposition_ids"]),
    )


def _observation(value: JsonValue) -> HKCaseSemanticBoundaryObservation:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "model_input_fingerprint",
            "workflow_result_fingerprint",
            "opinions",
            "propositions",
            "units",
            "disposition",
            "selected_candidate_ids",
            "complete_ledger",
            "source_text_treated_as_instruction",
            "hidden_reference_received_by_workflow",
        },
    )
    _constants(root, "asklegal.hk-cases.semantic-boundary-observation")
    return HKCaseSemanticBoundaryObservation(
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        workflow_result_fingerprint=_fingerprint(root["workflow_result_fingerprint"]),
        opinions=tuple(_opinion(item) for item in _array(root["opinions"])),
        propositions=tuple(_observed_proposition(item) for item in _array(root["propositions"])),
        units=tuple(_observed_unit(item) for item in _array(root["units"])),
        disposition=_enum(root["disposition"], HKCaseSemanticBoundaryDisposition),
        selected_candidate_ids=_identities(root["selected_candidate_ids"]),
        complete_ledger=_boolean(root["complete_ledger"]),
        source_text_treated_as_instruction=_boolean(root["source_text_treated_as_instruction"]),
        hidden_reference_received_by_workflow=_boolean(
            root["hidden_reference_received_by_workflow"]
        ),
    )


def _observed_proposition(value: JsonValue) -> HKCaseSemanticBoundaryObservedProposition:
    root = _object(value)
    _exact_keys(
        root,
        {
            "candidate_id",
            "mapped_reference_proposition_id",
            "resolution",
            "issue_code",
            "authority_role",
            "opinion_path_ids",
            "meaning_codes",
            "boundary_codes",
            "range_ids",
            "derived_statement",
        },
    )
    return HKCaseSemanticBoundaryObservedProposition(
        candidate_id=_identity(root["candidate_id"]),
        mapped_reference_proposition_id=_optional_identity(root["mapped_reference_proposition_id"]),
        resolution=_enum(root["resolution"], HKCaseSemanticBoundaryResolution),
        issue_code=_code(root["issue_code"]),
        authority_role=_enum(root["authority_role"], HKCaseSemanticBoundaryAuthorityRole),
        opinion_path_ids=_identities(root["opinion_path_ids"]),
        meaning_codes=_codes(root["meaning_codes"]),
        boundary_codes=_codes(root["boundary_codes"]),
        range_ids=_identities(root["range_ids"]),
        derived_statement=_optional_string(root["derived_statement"]),
    )


def _observed_unit(value: JsonValue) -> HKCaseSemanticBoundaryObservedUnit:
    root = _object(value)
    _exact_keys(root, {"unit_id", "opinion_id", "use", "candidate_ids"})
    return HKCaseSemanticBoundaryObservedUnit(
        unit_id=_identity(root["unit_id"]),
        opinion_id=_identity(root["opinion_id"]),
        use=_enum(root["use"], HKCaseSemanticBoundaryUnitUse),
        candidate_ids=_identities(root["candidate_ids"]),
    )


def _object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if not isinstance(checked, dict):
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.CONTRACT)
    return checked


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.CONTRACT)
    return value


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.CONTRACT)


def _constants(root: dict[str, JsonValue], schema_id: str) -> None:
    if (
        root["schema_id"] != schema_id
        or root["schema_version"] != HK_CASE_SEMANTIC_BOUNDARY_CONTRACT_VERSION
        or root["rule_id"] != HK_CASE_SEMANTIC_BOUNDARY_RULE_ID
    ):
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.CONTRACT)


def _string(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.CONTRACT)
    return value


def _optional_string(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _string(value)


def _identity(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_IDENTITY_PATTERN, result) is None:
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.IDENTITY)
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
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.CONTRACT)
    return result


def _codes(value: JsonValue) -> tuple[str, ...]:
    return tuple(_code(item) for item in _array(value))


def _fingerprint(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.FINGERPRINT)
    return result


def _boolean(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.CONTRACT)
    return value


def _enum[T: StrEnum](value: JsonValue, enum_type: type[T]) -> T:
    raw = _string(value)
    try:
        return enum_type(raw)
    except ValueError:
        raise HKCaseSemanticBoundaryError(HKCaseSemanticBoundaryErrorCode.CONTRACT) from None


def _duplicates(values: tuple[object, ...]) -> bool:
    return len(set(values)) != len(values)
