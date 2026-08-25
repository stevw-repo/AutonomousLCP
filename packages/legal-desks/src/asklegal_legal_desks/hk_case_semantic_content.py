"""Deterministic evaluator for frozen Hong Kong Case semantic content truth."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

HK_CASE_SEMANTIC_CONTENT_CONTRACT_VERSION = "1.0.0"
HK_CASE_SEMANTIC_CONTENT_RULE_ID = "HKCASE-PROP-SEM-CONTENT-EVALUATOR-001"

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_IDENTITY_PATTERN = r"[a-z][a-z0-9_]{2,95}"
_CODE_PATTERN = r"[A-Z][A-Z0-9_]{2,95}"


class HKCaseSemanticContentErrorCode(StrEnum):
    """Closed malformed evaluator-input failures."""

    CONTRACT = "HK_CASE_SEMANTIC_CONTENT_CONTRACT_INVALID"
    FINGERPRINT = "HK_CASE_SEMANTIC_CONTENT_FINGERPRINT_INVALID"
    IDENTITY = "HK_CASE_SEMANTIC_CONTENT_IDENTITY_INVALID"


class HKCaseSemanticContentError(ValueError):
    """One strict semantic-content contract failure."""

    code: HKCaseSemanticContentErrorCode

    def __init__(self, code: HKCaseSemanticContentErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKCaseSemanticContentDisposition(StrEnum):
    """Closed judgment-wide dispositions used by the content checkpoint."""

    ACCOUNTED_WITH_QUARANTINE = "ACCOUNTED_WITH_QUARANTINE"
    COMPLETE_NO_PROPOSITION = "COMPLETE_NO_PROPOSITION"
    COMPLETE_WITH_PROPOSITIONS = "COMPLETE_WITH_PROPOSITIONS"


class HKCaseSemanticContentResolution(StrEnum):
    """The adjudicated semantic consequence for one proposition candidate."""

    ACCEPTED = "ACCEPTED"
    QUARANTINED = "QUARANTINED"


class HKCaseSemanticContentUnitUse(StrEnum):
    """One exact primary-unit use in the evaluator ledger."""

    CITATION_ONLY = "CITATION_ONLY"
    CONTEXT_EVIDENCE = "CONTEXT_EVIDENCE"
    NON_PROPOSITIONAL = "NON_PROPOSITIONAL"
    PROPOSITION_EVIDENCE = "PROPOSITION_EVIDENCE"


class HKCaseSemanticContentOutcome(StrEnum):
    """Deterministic evaluator outcomes."""

    EVALUATOR_BLOCKED = "EVALUATOR_BLOCKED"
    FAIL = "FAIL"
    PASS = "PASS"


class HKCaseSemanticContentReason(StrEnum):
    """Closed semantic-content evaluator reasons."""

    CANDIDATE_INVENTORY_MISMATCH = "CANDIDATE_INVENTORY_MISMATCH"
    CONTENT_MISMATCH = "CONTENT_MISMATCH"
    DEPENDENCY_MISMATCH = "DEPENDENCY_MISMATCH"
    DISPOSITION_MISMATCH = "DISPOSITION_MISMATCH"
    EVALUATION_LEAKAGE = "EVALUATION_LEAKAGE"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    MEANING_MISMATCH = "MEANING_MISMATCH"
    OBSERVATION_BINDING_INVALID = "OBSERVATION_BINDING_INVALID"
    PASS = "PASS"
    QUOTATION_MISMATCH = "QUOTATION_MISMATCH"
    REFERENCE_BLOCKED = "REFERENCE_BLOCKED"
    REFERENCE_INVALID = "REFERENCE_INVALID"
    RESOLUTION_MISMATCH = "RESOLUTION_MISMATCH"
    SELECTION_MISMATCH = "SELECTION_MISMATCH"
    STATEMENT_STATE_MISMATCH = "STATEMENT_STATE_MISMATCH"
    UNIT_ACCOUNTING_MISMATCH = "UNIT_ACCOUNTING_MISMATCH"


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentEvidenceAssertion:
    """One exact evidence role and its smallest ordered range set."""

    role_code: str
    ordered_range_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentQuotationAssertion:
    """One exact selected quotation bound to a supplied range."""

    range_id: str
    exact_text: str


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentReferenceProposition:
    """One hidden adjudicated content-and-evidence assertion set."""

    reference_proposition_id: str
    expected_resolution: HKCaseSemanticContentResolution
    required_meaning_codes: tuple[str, ...]
    forbidden_meaning_codes: tuple[str, ...]
    required_content_codes: tuple[str, ...]
    forbidden_content_codes: tuple[str, ...]
    evidence_assertions: tuple[HKCaseSemanticContentEvidenceAssertion, ...]
    required_dependency_ids: tuple[str, ...]
    exact_quotations: tuple[HKCaseSemanticContentQuotationAssertion, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentReferenceUnit:
    """One evaluator-only expected primary-unit accounting row."""

    unit_id: str
    use: HKCaseSemanticContentUnitUse
    reference_proposition_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentReference:
    """Evaluator-only Reference Proposition Map for one synthetic judgment."""

    reference_map_id: str
    model_input_fingerprint: str
    propositions: tuple[HKCaseSemanticContentReferenceProposition, ...]
    units: tuple[HKCaseSemanticContentReferenceUnit, ...]
    expected_disposition: HKCaseSemanticContentDisposition
    expected_selected_reference_proposition_ids: tuple[str, ...]
    adjudication_complete: bool
    unresolved_reference_ambiguity: bool


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentObservedProposition:
    """One post-run proposition reduced to adjudicated observable facts."""

    candidate_id: str
    mapped_reference_proposition_id: str | None
    resolution: HKCaseSemanticContentResolution
    meaning_codes: tuple[str, ...]
    content_codes: tuple[str, ...]
    evidence_assertions: tuple[HKCaseSemanticContentEvidenceAssertion, ...]
    dependency_ids: tuple[str, ...]
    selected_quotations: tuple[HKCaseSemanticContentQuotationAssertion, ...]
    derived_statement: str | None


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentObservedUnit:
    """One observed primary-unit accounting row."""

    unit_id: str
    use: HKCaseSemanticContentUnitUse
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentObservation:
    """One candidate workflow result reduced to evaluator-visible facts."""

    model_input_fingerprint: str
    workflow_result_fingerprint: str
    propositions: tuple[HKCaseSemanticContentObservedProposition, ...]
    units: tuple[HKCaseSemanticContentObservedUnit, ...]
    disposition: HKCaseSemanticContentDisposition
    selected_candidate_ids: tuple[str, ...]
    complete_ledger: bool
    source_text_treated_as_instruction: bool
    hidden_reference_received_by_workflow: bool


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentEvaluationRequest:
    """One evaluator-only reference and one post-run observation."""

    evaluator_fingerprint: str
    reference: HKCaseSemanticContentReference
    observation: HKCaseSemanticContentObservation


@dataclass(frozen=True, slots=True)
class HKCaseSemanticContentEvaluationResult:
    """One effect-free deterministic semantic-content comparison."""

    request_fingerprint: str
    reference_map_fingerprint: str
    outcome: HKCaseSemanticContentOutcome
    reasons: tuple[HKCaseSemanticContentReason, ...]
    expected_candidate_count: int
    observed_candidate_count: int
    matched_candidate_count: int
    accepted_candidate_count: int
    quarantined_candidate_count: int
    complete_unit_count: int
    provider_calls_authorized: int
    workflow_admission_created: bool
    search_records_created: int
    release_eligible: bool
    external_effects: str


def evaluate_hk_case_semantic_content(
    request: HKCaseSemanticContentEvaluationRequest,
) -> HKCaseSemanticContentEvaluationResult:
    """Compare content truth without case identity, prose preference, or effects."""
    request_document = hk_case_semantic_content_evaluation_request_document(request)
    request_fingerprint = fingerprint(checked_json_value(request_document))
    reference_document = hk_case_semantic_content_reference_document(request.reference)
    reference_fingerprint = fingerprint(checked_json_value(reference_document))
    reasons = _reference_reasons(request.reference) | _observation_reasons(request)
    if HKCaseSemanticContentReason.REFERENCE_BLOCKED in reasons:
        outcome = HKCaseSemanticContentOutcome.EVALUATOR_BLOCKED
    elif reasons:
        outcome = HKCaseSemanticContentOutcome.FAIL
    else:
        outcome = HKCaseSemanticContentOutcome.PASS
        reasons = {HKCaseSemanticContentReason.PASS}
    matched = _matched_candidate_count(request)
    return HKCaseSemanticContentEvaluationResult(
        request_fingerprint=request_fingerprint,
        reference_map_fingerprint=reference_fingerprint,
        outcome=outcome,
        reasons=tuple(sorted(reasons, key=lambda item: item.value)),
        expected_candidate_count=len(request.reference.propositions),
        observed_candidate_count=len(request.observation.propositions),
        matched_candidate_count=matched,
        accepted_candidate_count=sum(
            item.resolution is HKCaseSemanticContentResolution.ACCEPTED
            for item in request.observation.propositions
        ),
        quarantined_candidate_count=sum(
            item.resolution is HKCaseSemanticContentResolution.QUARANTINED
            for item in request.observation.propositions
        ),
        complete_unit_count=len(request.observation.units),
        provider_calls_authorized=0,
        workflow_admission_created=False,
        search_records_created=0,
        release_eligible=False,
        external_effects="NONE",
    )


def _reference_reasons(
    reference: HKCaseSemanticContentReference,
) -> set[HKCaseSemanticContentReason]:
    reasons: set[HKCaseSemanticContentReason] = set()
    reference_ids = tuple(item.reference_proposition_id for item in reference.propositions)
    unit_ids = tuple(item.unit_id for item in reference.units)
    selected = reference.expected_selected_reference_proposition_ids
    accepted_ids = tuple(
        item.reference_proposition_id
        for item in reference.propositions
        if item.expected_resolution is HKCaseSemanticContentResolution.ACCEPTED
    )
    disposition_valid = (
        (
            reference.expected_disposition
            is HKCaseSemanticContentDisposition.COMPLETE_WITH_PROPOSITIONS
            and bool(accepted_ids)
            and len(accepted_ids) == len(reference.propositions)
        )
        or (
            reference.expected_disposition
            is HKCaseSemanticContentDisposition.COMPLETE_NO_PROPOSITION
            and not reference.propositions
        )
        or (
            reference.expected_disposition
            is HKCaseSemanticContentDisposition.ACCOUNTED_WITH_QUARANTINE
            and bool(reference.propositions)
            and not accepted_ids
        )
    )
    if (
        not reference.units
        or _duplicates(reference_ids)
        or _duplicates(unit_ids)
        or _duplicates(selected)
        or not set(selected).issubset(accepted_ids)
        or any(not _reference_proposition_valid(item) for item in reference.propositions)
        or any(
            not set(item.reference_proposition_ids).issubset(reference_ids)
            or _duplicates(item.reference_proposition_ids)
            for item in reference.units
        )
        or not disposition_valid
    ):
        reasons.add(HKCaseSemanticContentReason.REFERENCE_INVALID)
    if not reference.adjudication_complete or reference.unresolved_reference_ambiguity:
        reasons.add(HKCaseSemanticContentReason.REFERENCE_BLOCKED)
    return reasons


def _reference_proposition_valid(
    proposition: HKCaseSemanticContentReferenceProposition,
) -> bool:
    evidence_roles = tuple(item.role_code for item in proposition.evidence_assertions)
    evidence_ranges = {
        range_id
        for assertion in proposition.evidence_assertions
        for range_id in assertion.ordered_range_ids
    }
    quotations_valid = all(
        item.exact_text and item.range_id in evidence_ranges
        for item in proposition.exact_quotations
    )
    evidence_valid = all(
        bool(item.ordered_range_ids) and not _duplicates(item.ordered_range_ids)
        for item in proposition.evidence_assertions
    )
    locator_unavailable = "EXACT_LOCATOR_UNAVAILABLE" in proposition.required_content_codes
    return (
        bool(proposition.required_meaning_codes)
        and bool(proposition.required_content_codes)
        and not _duplicates(proposition.required_meaning_codes)
        and not _duplicates(proposition.forbidden_meaning_codes)
        and not _duplicates(proposition.required_content_codes)
        and not _duplicates(proposition.forbidden_content_codes)
        and not _duplicates(evidence_roles)
        and not _duplicates(proposition.required_dependency_ids)
        and not _duplicates(tuple(item.range_id for item in proposition.exact_quotations))
        and not set(proposition.required_meaning_codes).intersection(
            proposition.forbidden_meaning_codes
        )
        and not set(proposition.required_content_codes).intersection(
            proposition.forbidden_content_codes
        )
        and evidence_valid
        and quotations_valid
        and (bool(proposition.evidence_assertions) or locator_unavailable)
    )


def _observation_reasons(
    request: HKCaseSemanticContentEvaluationRequest,
) -> set[HKCaseSemanticContentReason]:
    reference = request.reference
    observation = request.observation
    reasons: set[HKCaseSemanticContentReason] = set()
    if (
        observation.model_input_fingerprint != reference.model_input_fingerprint
        or fullmatch(_FINGERPRINT_PATTERN, request.evaluator_fingerprint) is None
        or fullmatch(_FINGERPRINT_PATTERN, observation.workflow_result_fingerprint) is None
    ):
        reasons.add(HKCaseSemanticContentReason.OBSERVATION_BINDING_INVALID)
    if not _candidate_inventory_valid(request):
        reasons.add(HKCaseSemanticContentReason.CANDIDATE_INVENTORY_MISMATCH)
    reasons.update(_mapped_candidate_reasons(request))
    if not _unit_accounting_valid(request):
        reasons.add(HKCaseSemanticContentReason.UNIT_ACCOUNTING_MISMATCH)
    if observation.disposition is not reference.expected_disposition:
        reasons.add(HKCaseSemanticContentReason.DISPOSITION_MISMATCH)
    if not _selection_valid(request):
        reasons.add(HKCaseSemanticContentReason.SELECTION_MISMATCH)
    if (
        observation.source_text_treated_as_instruction
        or observation.hidden_reference_received_by_workflow
    ):
        reasons.add(HKCaseSemanticContentReason.EVALUATION_LEAKAGE)
    return reasons


def _candidate_inventory_valid(request: HKCaseSemanticContentEvaluationRequest) -> bool:
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


def _matched_candidate_count(request: HKCaseSemanticContentEvaluationRequest) -> int:
    reference_ids = {item.reference_proposition_id for item in request.reference.propositions}
    counts = {
        item: sum(
            observed.mapped_reference_proposition_id == item
            for observed in request.observation.propositions
        )
        for item in reference_ids
    }
    return sum(count == 1 for count in counts.values())


def _mapped_candidate_reasons(
    request: HKCaseSemanticContentEvaluationRequest,
) -> set[HKCaseSemanticContentReason]:
    references = {item.reference_proposition_id: item for item in request.reference.propositions}
    reasons: set[HKCaseSemanticContentReason] = set()
    for observed in request.observation.propositions:
        expected = references.get(observed.mapped_reference_proposition_id or "")
        if expected is None:
            continue
        if observed.resolution is not expected.expected_resolution:
            reasons.add(HKCaseSemanticContentReason.RESOLUTION_MISMATCH)
        if not set(expected.required_meaning_codes).issubset(observed.meaning_codes) or set(
            expected.forbidden_meaning_codes
        ).intersection(observed.meaning_codes):
            reasons.add(HKCaseSemanticContentReason.MEANING_MISMATCH)
        if not set(expected.required_content_codes).issubset(observed.content_codes) or set(
            expected.forbidden_content_codes
        ).intersection(observed.content_codes):
            reasons.add(HKCaseSemanticContentReason.CONTENT_MISMATCH)
        if observed.evidence_assertions != expected.evidence_assertions:
            reasons.add(HKCaseSemanticContentReason.EVIDENCE_MISMATCH)
        if observed.dependency_ids != expected.required_dependency_ids:
            reasons.add(HKCaseSemanticContentReason.DEPENDENCY_MISMATCH)
        if observed.selected_quotations != expected.exact_quotations:
            reasons.add(HKCaseSemanticContentReason.QUOTATION_MISMATCH)
        statement_valid = (
            expected.expected_resolution is HKCaseSemanticContentResolution.ACCEPTED
            and observed.derived_statement is not None
            and bool(observed.derived_statement.strip())
        ) or (
            expected.expected_resolution is HKCaseSemanticContentResolution.QUARANTINED
            and observed.derived_statement is None
        )
        if not statement_valid:
            reasons.add(HKCaseSemanticContentReason.STATEMENT_STATE_MISMATCH)
    return reasons


def _unit_accounting_valid(request: HKCaseSemanticContentEvaluationRequest) -> bool:
    observation = request.observation
    if not observation.complete_ledger:
        return False
    candidate_to_reference = {
        item.candidate_id: item.mapped_reference_proposition_id
        for item in observation.propositions
        if item.mapped_reference_proposition_id is not None
    }
    observed_rows = tuple(
        (
            item.unit_id,
            item.use,
            tuple(candidate_to_reference.get(candidate_id) for candidate_id in item.candidate_ids),
        )
        for item in observation.units
    )
    expected_rows = tuple(
        (item.unit_id, item.use, item.reference_proposition_ids) for item in request.reference.units
    )
    return (
        not _duplicates(tuple(item.unit_id for item in observation.units))
        and all(
            candidate_id in candidate_to_reference
            for item in observation.units
            for candidate_id in item.candidate_ids
        )
        and observed_rows == expected_rows
    )


def _selection_valid(request: HKCaseSemanticContentEvaluationRequest) -> bool:
    observation = request.observation
    mapping = {
        item.candidate_id: item.mapped_reference_proposition_id for item in observation.propositions
    }
    selected_reference_ids = tuple(
        mapping.get(candidate_id) for candidate_id in observation.selected_candidate_ids
    )
    return (
        not _duplicates(observation.selected_candidate_ids)
        and all(item is not None for item in selected_reference_ids)
        and selected_reference_ids == request.reference.expected_selected_reference_proposition_ids
    )


def hk_case_semantic_content_reference_document(
    reference: HKCaseSemanticContentReference,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator-only reference projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-content-reference",
        "schema_version": HK_CASE_SEMANTIC_CONTENT_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_CONTENT_RULE_ID,
        "reference_map_id": reference.reference_map_id,
        "model_input_fingerprint": reference.model_input_fingerprint,
        "propositions": [_reference_proposition_document(item) for item in reference.propositions],
        "units": [
            {
                "unit_id": item.unit_id,
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


def _reference_proposition_document(
    item: HKCaseSemanticContentReferenceProposition,
) -> dict[str, JsonValue]:
    return {
        "reference_proposition_id": item.reference_proposition_id,
        "expected_resolution": item.expected_resolution.value,
        "required_meaning_codes": list(item.required_meaning_codes),
        "forbidden_meaning_codes": list(item.forbidden_meaning_codes),
        "required_content_codes": list(item.required_content_codes),
        "forbidden_content_codes": list(item.forbidden_content_codes),
        "evidence_assertions": [_evidence_document(value) for value in item.evidence_assertions],
        "required_dependency_ids": list(item.required_dependency_ids),
        "exact_quotations": [_quotation_document(value) for value in item.exact_quotations],
    }


def hk_case_semantic_content_observation_document(
    observation: HKCaseSemanticContentObservation,
) -> dict[str, JsonValue]:
    """Return the canonical post-run observation projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-content-observation",
        "schema_version": HK_CASE_SEMANTIC_CONTENT_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_CONTENT_RULE_ID,
        "model_input_fingerprint": observation.model_input_fingerprint,
        "workflow_result_fingerprint": observation.workflow_result_fingerprint,
        "propositions": [
            {
                "candidate_id": item.candidate_id,
                "mapped_reference_proposition_id": item.mapped_reference_proposition_id,
                "resolution": item.resolution.value,
                "meaning_codes": list(item.meaning_codes),
                "content_codes": list(item.content_codes),
                "evidence_assertions": [
                    _evidence_document(value) for value in item.evidence_assertions
                ],
                "dependency_ids": list(item.dependency_ids),
                "selected_quotations": [
                    _quotation_document(value) for value in item.selected_quotations
                ],
                "derived_statement": item.derived_statement,
            }
            for item in observation.propositions
        ],
        "units": [
            {
                "unit_id": item.unit_id,
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


def _evidence_document(item: HKCaseSemanticContentEvidenceAssertion) -> dict[str, JsonValue]:
    return {"role_code": item.role_code, "ordered_range_ids": list(item.ordered_range_ids)}


def _quotation_document(
    item: HKCaseSemanticContentQuotationAssertion,
) -> dict[str, JsonValue]:
    return {"range_id": item.range_id, "exact_text": item.exact_text}


def hk_case_semantic_content_evaluation_request_document(
    request: HKCaseSemanticContentEvaluationRequest,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator request projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-content-evaluation-request",
        "schema_version": HK_CASE_SEMANTIC_CONTENT_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_CONTENT_RULE_ID,
        "evaluator_fingerprint": request.evaluator_fingerprint,
        "reference": hk_case_semantic_content_reference_document(request.reference),
        "observation": hk_case_semantic_content_observation_document(request.observation),
    }


def hk_case_semantic_content_result_document(
    result: HKCaseSemanticContentEvaluationResult,
) -> dict[str, JsonValue]:
    """Return the canonical effect-free evaluator result."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-content-evaluation-result",
        "schema_version": HK_CASE_SEMANTIC_CONTENT_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_CONTENT_RULE_ID,
        "request_fingerprint": result.request_fingerprint,
        "reference_map_fingerprint": result.reference_map_fingerprint,
        "outcome": result.outcome.value,
        "reasons": [item.value for item in result.reasons],
        "expected_candidate_count": result.expected_candidate_count,
        "observed_candidate_count": result.observed_candidate_count,
        "matched_candidate_count": result.matched_candidate_count,
        "accepted_candidate_count": result.accepted_candidate_count,
        "quarantined_candidate_count": result.quarantined_candidate_count,
        "complete_unit_count": result.complete_unit_count,
        "provider_calls_authorized": result.provider_calls_authorized,
        "workflow_admission_created": result.workflow_admission_created,
        "search_records_created": result.search_records_created,
        "release_eligible": result.release_eligible,
        "external_effects": result.external_effects,
    }


def hk_case_semantic_content_evaluation_request_from_document(
    document: object,
) -> HKCaseSemanticContentEvaluationRequest:
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
    _constants(root, "asklegal.hk-cases.semantic-content-evaluation-request")
    return HKCaseSemanticContentEvaluationRequest(
        evaluator_fingerprint=_fingerprint(root["evaluator_fingerprint"]),
        reference=_reference(root["reference"]),
        observation=_observation(root["observation"]),
    )


def _reference(value: JsonValue) -> HKCaseSemanticContentReference:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "reference_map_id",
            "model_input_fingerprint",
            "propositions",
            "units",
            "expected_disposition",
            "expected_selected_reference_proposition_ids",
            "adjudication_complete",
            "unresolved_reference_ambiguity",
        },
    )
    _constants(root, "asklegal.hk-cases.semantic-content-reference")
    return HKCaseSemanticContentReference(
        reference_map_id=_identity(root["reference_map_id"]),
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        propositions=tuple(_reference_proposition(item) for item in _array(root["propositions"])),
        units=tuple(_reference_unit(item) for item in _array(root["units"])),
        expected_disposition=_enum(root["expected_disposition"], HKCaseSemanticContentDisposition),
        expected_selected_reference_proposition_ids=_identities(
            root["expected_selected_reference_proposition_ids"]
        ),
        adjudication_complete=_boolean(root["adjudication_complete"]),
        unresolved_reference_ambiguity=_boolean(root["unresolved_reference_ambiguity"]),
    )


def _reference_proposition(value: JsonValue) -> HKCaseSemanticContentReferenceProposition:
    root = _object(value)
    _exact_keys(
        root,
        {
            "reference_proposition_id",
            "expected_resolution",
            "required_meaning_codes",
            "forbidden_meaning_codes",
            "required_content_codes",
            "forbidden_content_codes",
            "evidence_assertions",
            "required_dependency_ids",
            "exact_quotations",
        },
    )
    return HKCaseSemanticContentReferenceProposition(
        reference_proposition_id=_identity(root["reference_proposition_id"]),
        expected_resolution=_enum(root["expected_resolution"], HKCaseSemanticContentResolution),
        required_meaning_codes=_codes(root["required_meaning_codes"]),
        forbidden_meaning_codes=_codes(root["forbidden_meaning_codes"]),
        required_content_codes=_codes(root["required_content_codes"]),
        forbidden_content_codes=_codes(root["forbidden_content_codes"]),
        evidence_assertions=tuple(_evidence(item) for item in _array(root["evidence_assertions"])),
        required_dependency_ids=_identities(root["required_dependency_ids"]),
        exact_quotations=tuple(_quotation(item) for item in _array(root["exact_quotations"])),
    )


def _reference_unit(value: JsonValue) -> HKCaseSemanticContentReferenceUnit:
    root = _object(value)
    _exact_keys(root, {"unit_id", "use", "reference_proposition_ids"})
    return HKCaseSemanticContentReferenceUnit(
        unit_id=_identity(root["unit_id"]),
        use=_enum(root["use"], HKCaseSemanticContentUnitUse),
        reference_proposition_ids=_identities(root["reference_proposition_ids"]),
    )


def _observation(value: JsonValue) -> HKCaseSemanticContentObservation:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "model_input_fingerprint",
            "workflow_result_fingerprint",
            "propositions",
            "units",
            "disposition",
            "selected_candidate_ids",
            "complete_ledger",
            "source_text_treated_as_instruction",
            "hidden_reference_received_by_workflow",
        },
    )
    _constants(root, "asklegal.hk-cases.semantic-content-observation")
    return HKCaseSemanticContentObservation(
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        workflow_result_fingerprint=_fingerprint(root["workflow_result_fingerprint"]),
        propositions=tuple(_observed_proposition(item) for item in _array(root["propositions"])),
        units=tuple(_observed_unit(item) for item in _array(root["units"])),
        disposition=_enum(root["disposition"], HKCaseSemanticContentDisposition),
        selected_candidate_ids=_identities(root["selected_candidate_ids"]),
        complete_ledger=_boolean(root["complete_ledger"]),
        source_text_treated_as_instruction=_boolean(root["source_text_treated_as_instruction"]),
        hidden_reference_received_by_workflow=_boolean(
            root["hidden_reference_received_by_workflow"]
        ),
    )


def _observed_proposition(value: JsonValue) -> HKCaseSemanticContentObservedProposition:
    root = _object(value)
    _exact_keys(
        root,
        {
            "candidate_id",
            "mapped_reference_proposition_id",
            "resolution",
            "meaning_codes",
            "content_codes",
            "evidence_assertions",
            "dependency_ids",
            "selected_quotations",
            "derived_statement",
        },
    )
    return HKCaseSemanticContentObservedProposition(
        candidate_id=_identity(root["candidate_id"]),
        mapped_reference_proposition_id=_optional_identity(root["mapped_reference_proposition_id"]),
        resolution=_enum(root["resolution"], HKCaseSemanticContentResolution),
        meaning_codes=_codes(root["meaning_codes"]),
        content_codes=_codes(root["content_codes"]),
        evidence_assertions=tuple(_evidence(item) for item in _array(root["evidence_assertions"])),
        dependency_ids=_identities(root["dependency_ids"]),
        selected_quotations=tuple(_quotation(item) for item in _array(root["selected_quotations"])),
        derived_statement=_optional_string(root["derived_statement"]),
    )


def _observed_unit(value: JsonValue) -> HKCaseSemanticContentObservedUnit:
    root = _object(value)
    _exact_keys(root, {"unit_id", "use", "candidate_ids"})
    return HKCaseSemanticContentObservedUnit(
        unit_id=_identity(root["unit_id"]),
        use=_enum(root["use"], HKCaseSemanticContentUnitUse),
        candidate_ids=_identities(root["candidate_ids"]),
    )


def _evidence(value: JsonValue) -> HKCaseSemanticContentEvidenceAssertion:
    root = _object(value)
    _exact_keys(root, {"role_code", "ordered_range_ids"})
    return HKCaseSemanticContentEvidenceAssertion(
        role_code=_code(root["role_code"]),
        ordered_range_ids=_identities(root["ordered_range_ids"]),
    )


def _quotation(value: JsonValue) -> HKCaseSemanticContentQuotationAssertion:
    root = _object(value)
    _exact_keys(root, {"range_id", "exact_text"})
    return HKCaseSemanticContentQuotationAssertion(
        range_id=_identity(root["range_id"]), exact_text=_string(root["exact_text"])
    )


def _object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if not isinstance(checked, dict):
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.CONTRACT)
    return checked


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.CONTRACT)
    return value


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.CONTRACT)


def _constants(root: dict[str, JsonValue], schema_id: str) -> None:
    if (
        root["schema_id"] != schema_id
        or root["schema_version"] != HK_CASE_SEMANTIC_CONTENT_CONTRACT_VERSION
        or root["rule_id"] != HK_CASE_SEMANTIC_CONTENT_RULE_ID
    ):
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.CONTRACT)


def _string(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.CONTRACT)
    return value


def _optional_string(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _string(value)


def _identity(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_IDENTITY_PATTERN, result) is None:
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.IDENTITY)
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
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.CONTRACT)
    return result


def _codes(value: JsonValue) -> tuple[str, ...]:
    return tuple(_code(item) for item in _array(value))


def _fingerprint(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.FINGERPRINT)
    return result


def _boolean(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.CONTRACT)
    return value


def _enum[T: StrEnum](value: JsonValue, enum_type: type[T]) -> T:
    raw = _string(value)
    try:
        return enum_type(raw)
    except ValueError:
        raise HKCaseSemanticContentError(HKCaseSemanticContentErrorCode.CONTRACT) from None


def _duplicates(values: tuple[object, ...]) -> bool:
    return len(set(values)) != len(values)
