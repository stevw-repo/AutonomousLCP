"""Deterministic evaluator for frozen Hong Kong Case semantic materiality truth."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

HK_CASE_SEMANTIC_MATERIALITY_CONTRACT_VERSION = "1.0.0"
HK_CASE_SEMANTIC_MATERIALITY_RULE_ID = "HKCASE-PROP-SEM-MATERIALITY-EVALUATOR-001"

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_IDENTITY_PATTERN = r"[a-z][a-z0-9_]{2,95}"
_CODE_PATTERN = r"[A-Z][A-Z0-9_]{2,95}"


class HKCaseSemanticMaterialityErrorCode(StrEnum):
    """Closed malformed evaluator-input failures."""

    CONTRACT = "HK_CASE_SEMANTIC_MATERIALITY_CONTRACT_INVALID"
    FINGERPRINT = "HK_CASE_SEMANTIC_MATERIALITY_FINGERPRINT_INVALID"
    IDENTITY = "HK_CASE_SEMANTIC_MATERIALITY_IDENTITY_INVALID"


class HKCaseSemanticMaterialityError(ValueError):
    """One strict semantic materiality contract failure."""

    code: HKCaseSemanticMaterialityErrorCode

    def __init__(self, code: HKCaseSemanticMaterialityErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKCaseSemanticMaterialityDisposition(StrEnum):
    """Closed judgment-wide semantic dispositions used by this checkpoint."""

    ACCOUNTED_WITH_QUARANTINE = "ACCOUNTED_WITH_QUARANTINE"
    BLOCKED = "BLOCKED"
    COMPLETE_NO_PROPOSITION = "COMPLETE_NO_PROPOSITION"
    COMPLETE_WITH_PROPOSITIONS = "COMPLETE_WITH_PROPOSITIONS"


class HKCaseSemanticMaterialityAuthorityRole(StrEnum):
    """Authority role material to the frozen materiality checkpoint."""

    OBITER = "OBITER"
    OPERATIVE = "OPERATIVE"


class HKCaseSemanticMaterialityUnitUse(StrEnum):
    """One complete semantic use for an observed primary unit."""

    CITATION_ONLY = "CITATION_ONLY"
    NON_PROPOSITIONAL = "NON_PROPOSITIONAL"
    PROPOSITION_EVIDENCE = "PROPOSITION_EVIDENCE"
    TREATMENT_ONLY = "TREATMENT_ONLY"


class HKCaseSemanticMaterialityOutcome(StrEnum):
    """Deterministic evaluator outcomes."""

    EVALUATOR_BLOCKED = "EVALUATOR_BLOCKED"
    FAIL = "FAIL"
    PASS = "PASS"


class HKCaseSemanticMaterialityReason(StrEnum):
    """Closed semantic materiality evaluator reasons."""

    AUTHORITY_ROLE_MISMATCH = "AUTHORITY_ROLE_MISMATCH"
    COVERAGE_INCOMPLETE = "COVERAGE_INCOMPLETE"
    DOWNSTREAM_SELECTION_MISMATCH = "DOWNSTREAM_SELECTION_MISMATCH"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    EVALUATION_LEAKAGE = "EVALUATION_LEAKAGE"
    FALSE_ZERO = "FALSE_ZERO"
    HANDOFF_MISMATCH = "HANDOFF_MISMATCH"
    MEANING_MISMATCH = "MEANING_MISMATCH"
    OBSERVATION_BINDING_INVALID = "OBSERVATION_BINDING_INVALID"
    PASS = "PASS"
    REFERENCE_BLOCKED = "REFERENCE_BLOCKED"
    REFERENCE_INVALID = "REFERENCE_INVALID"
    REQUIRED_PROPOSITION_MISSING = "REQUIRED_PROPOSITION_MISSING"
    UNSUPPORTED_PROPOSITION = "UNSUPPORTED_PROPOSITION"


@dataclass(frozen=True, slots=True)
class HKCaseSemanticMaterialityReferenceProposition:
    """One hidden adjudicated proposition assertion set."""

    reference_proposition_id: str
    authority_role: HKCaseSemanticMaterialityAuthorityRole
    required_meaning_codes: tuple[str, ...]
    forbidden_meaning_codes: tuple[str, ...]
    required_evidence_role_codes: tuple[str, ...]
    required_range_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticMaterialityReference:
    """Evaluator-only Reference Proposition Map for one synthetic judgment."""

    reference_map_id: str
    model_input_fingerprint: str
    coverage_unit_ids: tuple[str, ...]
    propositions: tuple[HKCaseSemanticMaterialityReferenceProposition, ...]
    expected_disposition: HKCaseSemanticMaterialityDisposition
    required_handoff_ids: tuple[str, ...]
    expected_selected_reference_proposition_ids: tuple[str, ...]
    adjudication_complete: bool
    unresolved_reference_ambiguity: bool


@dataclass(frozen=True, slots=True)
class HKCaseSemanticMaterialityObservedProposition:
    """One post-run proposition mapped by the deterministic evaluator."""

    candidate_id: str
    mapped_reference_proposition_id: str | None
    authority_role: HKCaseSemanticMaterialityAuthorityRole
    meaning_codes: tuple[str, ...]
    evidence_role_codes: tuple[str, ...]
    range_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticMaterialityUnitObservation:
    """One primary unit's complete observed semantic accounting."""

    unit_id: str
    use: HKCaseSemanticMaterialityUnitUse
    candidate_ids: tuple[str, ...]
    handoff_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticMaterialityObservation:
    """One candidate workflow result reduced to adjudicated semantic facts."""

    model_input_fingerprint: str
    workflow_result_fingerprint: str
    propositions: tuple[HKCaseSemanticMaterialityObservedProposition, ...]
    unit_observations: tuple[HKCaseSemanticMaterialityUnitObservation, ...]
    disposition: HKCaseSemanticMaterialityDisposition
    handoff_ids: tuple[str, ...]
    selected_candidate_ids: tuple[str, ...]
    complete_ledger: bool
    source_text_treated_as_instruction: bool
    hidden_reference_received_by_workflow: bool


@dataclass(frozen=True, slots=True)
class HKCaseSemanticMaterialityEvaluationRequest:
    """One evaluator-only reference and one post-run observation."""

    evaluator_fingerprint: str
    reference: HKCaseSemanticMaterialityReference
    observation: HKCaseSemanticMaterialityObservation


@dataclass(frozen=True, slots=True)
class HKCaseSemanticMaterialityEvaluationResult:
    """One effect-free deterministic semantic comparison."""

    request_fingerprint: str
    reference_map_fingerprint: str
    outcome: HKCaseSemanticMaterialityOutcome
    reasons: tuple[HKCaseSemanticMaterialityReason, ...]
    required_proposition_count: int
    observed_proposition_count: int
    matched_proposition_count: int
    missing_reference_proposition_ids: tuple[str, ...]
    unsupported_candidate_ids: tuple[str, ...]
    complete_unit_count: int
    provider_calls_authorized: int
    workflow_admission_created: bool
    search_records_created: int
    release_eligible: bool
    external_effects: str


def evaluate_hk_case_semantic_materiality(
    request: HKCaseSemanticMaterialityEvaluationRequest,
) -> HKCaseSemanticMaterialityEvaluationResult:
    """Apply frozen reference truth without case identity or provider access."""
    request_document = hk_case_semantic_materiality_evaluation_request_document(request)
    request_fingerprint = fingerprint(checked_json_value(request_document))
    reference_document = hk_case_semantic_materiality_reference_document(request.reference)
    reference_fingerprint = fingerprint(checked_json_value(reference_document))
    reference_reasons = _reference_reasons(request.reference)
    missing, unsupported, matched = _proposition_inventory(request)
    reasons = reference_reasons | _observation_reasons(request, missing, unsupported)
    if HKCaseSemanticMaterialityReason.REFERENCE_BLOCKED in reasons:
        outcome = HKCaseSemanticMaterialityOutcome.EVALUATOR_BLOCKED
    elif reasons:
        outcome = HKCaseSemanticMaterialityOutcome.FAIL
    else:
        outcome = HKCaseSemanticMaterialityOutcome.PASS
        reasons = {HKCaseSemanticMaterialityReason.PASS}
    return HKCaseSemanticMaterialityEvaluationResult(
        request_fingerprint=request_fingerprint,
        reference_map_fingerprint=reference_fingerprint,
        outcome=outcome,
        reasons=tuple(sorted(reasons, key=lambda item: item.value)),
        required_proposition_count=len(request.reference.propositions),
        observed_proposition_count=len(request.observation.propositions),
        matched_proposition_count=matched,
        missing_reference_proposition_ids=missing,
        unsupported_candidate_ids=unsupported,
        complete_unit_count=len(request.observation.unit_observations),
        provider_calls_authorized=0,
        workflow_admission_created=False,
        search_records_created=0,
        release_eligible=False,
        external_effects="NONE",
    )


def _reference_reasons(
    reference: HKCaseSemanticMaterialityReference,
) -> set[HKCaseSemanticMaterialityReason]:
    reasons: set[HKCaseSemanticMaterialityReason] = set()
    reference_ids = tuple(item.reference_proposition_id for item in reference.propositions)
    if (
        not reference.coverage_unit_ids
        or _duplicates(reference.coverage_unit_ids)
        or _duplicates(reference_ids)
        or _duplicates(reference.required_handoff_ids)
        or _duplicates(reference.expected_selected_reference_proposition_ids)
        or not set(reference.expected_selected_reference_proposition_ids).issubset(reference_ids)
        or any(not _reference_proposition_valid(item) for item in reference.propositions)
        or (
            bool(reference.propositions)
            != (
                reference.expected_disposition
                is HKCaseSemanticMaterialityDisposition.COMPLETE_WITH_PROPOSITIONS
            )
        )
    ):
        reasons.add(HKCaseSemanticMaterialityReason.REFERENCE_INVALID)
    if not reference.adjudication_complete or reference.unresolved_reference_ambiguity:
        reasons.add(HKCaseSemanticMaterialityReason.REFERENCE_BLOCKED)
    return reasons


def _reference_proposition_valid(
    proposition: HKCaseSemanticMaterialityReferenceProposition,
) -> bool:
    return (
        bool(proposition.required_meaning_codes)
        and bool(proposition.required_evidence_role_codes)
        and bool(proposition.required_range_ids)
        and not _duplicates(proposition.required_meaning_codes)
        and not _duplicates(proposition.forbidden_meaning_codes)
        and not _duplicates(proposition.required_evidence_role_codes)
        and not _duplicates(proposition.required_range_ids)
        and not set(proposition.required_meaning_codes).intersection(
            proposition.forbidden_meaning_codes
        )
    )


def _proposition_inventory(
    request: HKCaseSemanticMaterialityEvaluationRequest,
) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    required_ids = tuple(item.reference_proposition_id for item in request.reference.propositions)
    mapped_ids = tuple(
        item.mapped_reference_proposition_id
        for item in request.observation.propositions
        if item.mapped_reference_proposition_id is not None
    )
    missing = tuple(item for item in required_ids if mapped_ids.count(item) != 1)
    unsupported = tuple(
        item.candidate_id
        for item in request.observation.propositions
        if item.mapped_reference_proposition_id not in required_ids
        or mapped_ids.count(item.mapped_reference_proposition_id) != 1
    )
    return missing, unsupported, len(required_ids) - len(missing)


def _observation_reasons(
    request: HKCaseSemanticMaterialityEvaluationRequest,
    missing: tuple[str, ...],
    unsupported: tuple[str, ...],
) -> set[HKCaseSemanticMaterialityReason]:
    reference = request.reference
    observation = request.observation
    reasons: set[HKCaseSemanticMaterialityReason] = set()
    if (
        observation.model_input_fingerprint != reference.model_input_fingerprint
        or fullmatch(_FINGERPRINT_PATTERN, request.evaluator_fingerprint) is None
        or fullmatch(_FINGERPRINT_PATTERN, observation.workflow_result_fingerprint) is None
    ):
        reasons.add(HKCaseSemanticMaterialityReason.OBSERVATION_BINDING_INVALID)
    if not _coverage_valid(reference, observation):
        reasons.add(HKCaseSemanticMaterialityReason.COVERAGE_INCOMPLETE)
    if missing:
        reasons.add(HKCaseSemanticMaterialityReason.REQUIRED_PROPOSITION_MISSING)
    if unsupported:
        reasons.add(HKCaseSemanticMaterialityReason.UNSUPPORTED_PROPOSITION)
    if reference.propositions and (
        not observation.propositions
        or observation.disposition is HKCaseSemanticMaterialityDisposition.COMPLETE_NO_PROPOSITION
    ):
        reasons.add(HKCaseSemanticMaterialityReason.FALSE_ZERO)
    reasons.update(_mapped_proposition_reasons(reference, observation))
    if observation.disposition is not reference.expected_disposition:
        reasons.add(HKCaseSemanticMaterialityReason.MEANING_MISMATCH)
    if observation.handoff_ids != reference.required_handoff_ids:
        reasons.add(HKCaseSemanticMaterialityReason.HANDOFF_MISMATCH)
    if not _selection_valid(reference, observation):
        reasons.add(HKCaseSemanticMaterialityReason.DOWNSTREAM_SELECTION_MISMATCH)
    if (
        observation.source_text_treated_as_instruction
        or observation.hidden_reference_received_by_workflow
    ):
        reasons.add(HKCaseSemanticMaterialityReason.EVALUATION_LEAKAGE)
    return reasons


def _coverage_valid(
    reference: HKCaseSemanticMaterialityReference,
    observation: HKCaseSemanticMaterialityObservation,
) -> bool:
    candidate_ids = {item.candidate_id for item in observation.propositions}
    unit_ids = tuple(item.unit_id for item in observation.unit_observations)
    return (
        observation.complete_ledger
        and unit_ids == reference.coverage_unit_ids
        and not _duplicates(unit_ids)
        and not _duplicates(tuple(item.candidate_id for item in observation.propositions))
        and all(
            set(item.candidate_ids).issubset(candidate_ids)
            for item in observation.unit_observations
        )
        and all(
            set(item.handoff_ids).issubset(observation.handoff_ids)
            for item in observation.unit_observations
        )
    )


def _mapped_proposition_reasons(
    reference: HKCaseSemanticMaterialityReference,
    observation: HKCaseSemanticMaterialityObservation,
) -> set[HKCaseSemanticMaterialityReason]:
    references = {item.reference_proposition_id: item for item in reference.propositions}
    reasons: set[HKCaseSemanticMaterialityReason] = set()
    for observed in observation.propositions:
        expected = references.get(observed.mapped_reference_proposition_id or "")
        if expected is None:
            continue
        if observed.authority_role is not expected.authority_role:
            reasons.add(HKCaseSemanticMaterialityReason.AUTHORITY_ROLE_MISMATCH)
        if not set(expected.required_meaning_codes).issubset(observed.meaning_codes) or set(
            expected.forbidden_meaning_codes
        ).intersection(observed.meaning_codes):
            reasons.add(HKCaseSemanticMaterialityReason.MEANING_MISMATCH)
        if not set(expected.required_evidence_role_codes).issubset(
            observed.evidence_role_codes
        ) or not set(expected.required_range_ids).issubset(observed.range_ids):
            reasons.add(HKCaseSemanticMaterialityReason.EVIDENCE_INCOMPLETE)
    return reasons


def _selection_valid(
    reference: HKCaseSemanticMaterialityReference,
    observation: HKCaseSemanticMaterialityObservation,
) -> bool:
    selected_reference_ids = tuple(
        item.mapped_reference_proposition_id
        for item in observation.propositions
        if item.candidate_id in observation.selected_candidate_ids
    )
    return (
        not _duplicates(observation.selected_candidate_ids)
        and set(observation.selected_candidate_ids).issubset(
            item.candidate_id for item in observation.propositions
        )
        and selected_reference_ids == reference.expected_selected_reference_proposition_ids
    )


def hk_case_semantic_materiality_reference_document(
    reference: HKCaseSemanticMaterialityReference,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator-only reference projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-materiality-reference",
        "schema_version": HK_CASE_SEMANTIC_MATERIALITY_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_MATERIALITY_RULE_ID,
        "reference_map_id": reference.reference_map_id,
        "model_input_fingerprint": reference.model_input_fingerprint,
        "coverage_unit_ids": list(reference.coverage_unit_ids),
        "propositions": [
            {
                "reference_proposition_id": item.reference_proposition_id,
                "authority_role": item.authority_role.value,
                "required_meaning_codes": list(item.required_meaning_codes),
                "forbidden_meaning_codes": list(item.forbidden_meaning_codes),
                "required_evidence_role_codes": list(item.required_evidence_role_codes),
                "required_range_ids": list(item.required_range_ids),
            }
            for item in reference.propositions
        ],
        "expected_disposition": reference.expected_disposition.value,
        "required_handoff_ids": list(reference.required_handoff_ids),
        "expected_selected_reference_proposition_ids": list(
            reference.expected_selected_reference_proposition_ids
        ),
        "adjudication_complete": reference.adjudication_complete,
        "unresolved_reference_ambiguity": reference.unresolved_reference_ambiguity,
    }


def hk_case_semantic_materiality_observation_document(
    observation: HKCaseSemanticMaterialityObservation,
) -> dict[str, JsonValue]:
    """Return the canonical post-run observation projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-materiality-observation",
        "schema_version": HK_CASE_SEMANTIC_MATERIALITY_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_MATERIALITY_RULE_ID,
        "model_input_fingerprint": observation.model_input_fingerprint,
        "workflow_result_fingerprint": observation.workflow_result_fingerprint,
        "propositions": [
            {
                "candidate_id": item.candidate_id,
                "mapped_reference_proposition_id": item.mapped_reference_proposition_id,
                "authority_role": item.authority_role.value,
                "meaning_codes": list(item.meaning_codes),
                "evidence_role_codes": list(item.evidence_role_codes),
                "range_ids": list(item.range_ids),
            }
            for item in observation.propositions
        ],
        "unit_observations": [
            {
                "unit_id": item.unit_id,
                "use": item.use.value,
                "candidate_ids": list(item.candidate_ids),
                "handoff_ids": list(item.handoff_ids),
            }
            for item in observation.unit_observations
        ],
        "disposition": observation.disposition.value,
        "handoff_ids": list(observation.handoff_ids),
        "selected_candidate_ids": list(observation.selected_candidate_ids),
        "complete_ledger": observation.complete_ledger,
        "source_text_treated_as_instruction": observation.source_text_treated_as_instruction,
        "hidden_reference_received_by_workflow": observation.hidden_reference_received_by_workflow,
    }


def hk_case_semantic_materiality_evaluation_request_document(
    request: HKCaseSemanticMaterialityEvaluationRequest,
) -> dict[str, JsonValue]:
    """Return the canonical evaluator request projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-materiality-evaluation-request",
        "schema_version": HK_CASE_SEMANTIC_MATERIALITY_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_MATERIALITY_RULE_ID,
        "evaluator_fingerprint": request.evaluator_fingerprint,
        "reference": hk_case_semantic_materiality_reference_document(request.reference),
        "observation": hk_case_semantic_materiality_observation_document(request.observation),
    }


def hk_case_semantic_materiality_result_document(
    result: HKCaseSemanticMaterialityEvaluationResult,
) -> dict[str, JsonValue]:
    """Return the canonical effect-free evaluator result."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-materiality-evaluation-result",
        "schema_version": HK_CASE_SEMANTIC_MATERIALITY_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_MATERIALITY_RULE_ID,
        "request_fingerprint": result.request_fingerprint,
        "reference_map_fingerprint": result.reference_map_fingerprint,
        "outcome": result.outcome.value,
        "reasons": [item.value for item in result.reasons],
        "required_proposition_count": result.required_proposition_count,
        "observed_proposition_count": result.observed_proposition_count,
        "matched_proposition_count": result.matched_proposition_count,
        "missing_reference_proposition_ids": list(result.missing_reference_proposition_ids),
        "unsupported_candidate_ids": list(result.unsupported_candidate_ids),
        "complete_unit_count": result.complete_unit_count,
        "provider_calls_authorized": result.provider_calls_authorized,
        "workflow_admission_created": result.workflow_admission_created,
        "search_records_created": result.search_records_created,
        "release_eligible": result.release_eligible,
        "external_effects": result.external_effects,
    }


def hk_case_semantic_materiality_evaluation_request_from_document(
    document: object,
) -> HKCaseSemanticMaterialityEvaluationRequest:
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
    _constants(root, "asklegal.hk-cases.semantic-materiality-evaluation-request")
    return HKCaseSemanticMaterialityEvaluationRequest(
        evaluator_fingerprint=_fingerprint(root["evaluator_fingerprint"]),
        reference=_reference(root["reference"]),
        observation=_observation(root["observation"]),
    )


def _reference(value: JsonValue) -> HKCaseSemanticMaterialityReference:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "reference_map_id",
            "model_input_fingerprint",
            "coverage_unit_ids",
            "propositions",
            "expected_disposition",
            "required_handoff_ids",
            "expected_selected_reference_proposition_ids",
            "adjudication_complete",
            "unresolved_reference_ambiguity",
        },
    )
    _constants(root, "asklegal.hk-cases.semantic-materiality-reference")
    return HKCaseSemanticMaterialityReference(
        reference_map_id=_identity(root["reference_map_id"]),
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        coverage_unit_ids=_identities(root["coverage_unit_ids"]),
        propositions=tuple(_reference_proposition(item) for item in _array(root["propositions"])),
        expected_disposition=_enum(
            root["expected_disposition"], HKCaseSemanticMaterialityDisposition
        ),
        required_handoff_ids=_identities(root["required_handoff_ids"]),
        expected_selected_reference_proposition_ids=_identities(
            root["expected_selected_reference_proposition_ids"]
        ),
        adjudication_complete=_boolean(root["adjudication_complete"]),
        unresolved_reference_ambiguity=_boolean(root["unresolved_reference_ambiguity"]),
    )


def _reference_proposition(value: JsonValue) -> HKCaseSemanticMaterialityReferenceProposition:
    root = _object(value)
    _exact_keys(
        root,
        {
            "reference_proposition_id",
            "authority_role",
            "required_meaning_codes",
            "forbidden_meaning_codes",
            "required_evidence_role_codes",
            "required_range_ids",
        },
    )
    return HKCaseSemanticMaterialityReferenceProposition(
        reference_proposition_id=_identity(root["reference_proposition_id"]),
        authority_role=_enum(root["authority_role"], HKCaseSemanticMaterialityAuthorityRole),
        required_meaning_codes=_codes(root["required_meaning_codes"]),
        forbidden_meaning_codes=_codes(root["forbidden_meaning_codes"]),
        required_evidence_role_codes=_codes(root["required_evidence_role_codes"]),
        required_range_ids=_identities(root["required_range_ids"]),
    )


def _observation(value: JsonValue) -> HKCaseSemanticMaterialityObservation:
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
            "unit_observations",
            "disposition",
            "handoff_ids",
            "selected_candidate_ids",
            "complete_ledger",
            "source_text_treated_as_instruction",
            "hidden_reference_received_by_workflow",
        },
    )
    _constants(root, "asklegal.hk-cases.semantic-materiality-observation")
    return HKCaseSemanticMaterialityObservation(
        model_input_fingerprint=_fingerprint(root["model_input_fingerprint"]),
        workflow_result_fingerprint=_fingerprint(root["workflow_result_fingerprint"]),
        propositions=tuple(_observed_proposition(item) for item in _array(root["propositions"])),
        unit_observations=tuple(
            _unit_observation(item) for item in _array(root["unit_observations"])
        ),
        disposition=_enum(root["disposition"], HKCaseSemanticMaterialityDisposition),
        handoff_ids=_identities(root["handoff_ids"]),
        selected_candidate_ids=_identities(root["selected_candidate_ids"]),
        complete_ledger=_boolean(root["complete_ledger"]),
        source_text_treated_as_instruction=_boolean(root["source_text_treated_as_instruction"]),
        hidden_reference_received_by_workflow=_boolean(
            root["hidden_reference_received_by_workflow"]
        ),
    )


def _observed_proposition(value: JsonValue) -> HKCaseSemanticMaterialityObservedProposition:
    root = _object(value)
    _exact_keys(
        root,
        {
            "candidate_id",
            "mapped_reference_proposition_id",
            "authority_role",
            "meaning_codes",
            "evidence_role_codes",
            "range_ids",
        },
    )
    return HKCaseSemanticMaterialityObservedProposition(
        candidate_id=_identity(root["candidate_id"]),
        mapped_reference_proposition_id=_optional_identity(root["mapped_reference_proposition_id"]),
        authority_role=_enum(root["authority_role"], HKCaseSemanticMaterialityAuthorityRole),
        meaning_codes=_codes(root["meaning_codes"]),
        evidence_role_codes=_codes(root["evidence_role_codes"]),
        range_ids=_identities(root["range_ids"]),
    )


def _unit_observation(value: JsonValue) -> HKCaseSemanticMaterialityUnitObservation:
    root = _object(value)
    _exact_keys(root, {"unit_id", "use", "candidate_ids", "handoff_ids"})
    return HKCaseSemanticMaterialityUnitObservation(
        unit_id=_identity(root["unit_id"]),
        use=_enum(root["use"], HKCaseSemanticMaterialityUnitUse),
        candidate_ids=_identities(root["candidate_ids"]),
        handoff_ids=_identities(root["handoff_ids"]),
    )


def _object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if not isinstance(checked, dict):
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.CONTRACT)
    return checked


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.CONTRACT)
    return value


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.CONTRACT)


def _constants(root: dict[str, JsonValue], schema_id: str) -> None:
    if (
        root["schema_id"] != schema_id
        or root["schema_version"] != HK_CASE_SEMANTIC_MATERIALITY_CONTRACT_VERSION
        or root["rule_id"] != HK_CASE_SEMANTIC_MATERIALITY_RULE_ID
    ):
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.CONTRACT)


def _string(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.CONTRACT)
    return value


def _identity(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_IDENTITY_PATTERN, result) is None:
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.IDENTITY)
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
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.CONTRACT)
    return result


def _codes(value: JsonValue) -> tuple[str, ...]:
    return tuple(_code(item) for item in _array(value))


def _fingerprint(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.FINGERPRINT)
    return result


def _boolean(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.CONTRACT)
    return value


def _enum[T: StrEnum](value: JsonValue, enum_type: type[T]) -> T:
    raw = _string(value)
    try:
        return enum_type(raw)
    except ValueError:
        raise HKCaseSemanticMaterialityError(HKCaseSemanticMaterialityErrorCode.CONTRACT) from None


def _duplicates(values: tuple[object, ...]) -> bool:
    return len(set(values)) != len(values)
