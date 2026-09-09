# ruff: noqa: BLE001, C901, FBT003, PLR0912, PLR0913, PLR0915, PLR0917, PLR2004, TRY300, TRY301
"""Pure, source-neutral construction of Hong Kong Case proposition request pairs.

This legal-desk module intentionally owns no processing-runner dependency.  It
produces a desk-native, immutable request shape which a later processing-owned
adapter may translate to its generic runner request without reversing the
repository dependency direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
from re import fullmatch
from typing import Protocol, SupportsIndex, TypeIs
from weakref import ReferenceType, WeakKeyDictionary, ref

from asklegal_contracts import canonicalize, fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_case_coverage_ledger import (
    HKCaseCandidateOutcome,
    HKCaseCoverageLedgerRequest,
    HKCaseCoverageLedgerResult,
    HKCaseCoverageSegment,
    HKCaseCoverageUnit,
    HKCaseCoverageUnitKind,
    HKCaseEvidenceRole,
    HKCaseLedgerOutcome,
    HKCaseNonPropositionalReason,
    HKCaseOpinion,
    HKCaseOpinionRole,
    HKCasePrimaryUse,
    HKCasePropositionCandidate,
    HKCaseUnitResolution,
    evaluate_hk_case_coverage_ledger,
)
from .hk_case_judgment import HKCaseJudgmentBundle
from .hk_case_output import (
    HK_CASE_OUTPUT_RENDERER_ID,
    HKCaseCodepointTokenCounter,
    HKCaseOutputCandidate,
    HKCaseOutputOutcome,
    HKCaseOutputProposition,
    HKCaseOutputRequest,
    HKCaseOutputResult,
    HKCasePropositionEvidenceLink,
    HKCaseQuotation,
    HKCaseSourceRange,
    HKCaseSourceUnitText,
    build_hk_case_proposed_serving_record,
    evaluate_hk_case_output,
)
from .hk_case_semantic_task import (
    HKCaseOriginalLanguage,
    HKCaseSemanticEvidenceRange,
    HKCaseSemanticOpinionManifest,
    HKCaseSemanticRequestKind,
    HKCaseSemanticSuppliedUnit,
    HKCaseSemanticTaskFamily,
    HKCaseSemanticTaskOutcome,
    HKCaseSemanticTaskRequest,
    HKCaseSemanticUnitManifest,
    HKCaseSemanticWorkflowComponent,
    evaluate_hk_case_semantic_task_request,
    hk_case_semantic_task_request_document,
)
from .model import SemanticTaskProfile

_FINGERPRINT = r"sha256:[0-9a-f]{64}"
_IDENTITY = r"[a-z][a-z0-9_]{2,95}"
_ISO_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
_DECISION_TASK = "HK_CASE_PROPOSITION_ANALYSIS"
_CHALLENGE_TASK = "HK_CASE_PROPOSITION_CHALLENGE"
_EVIDENCE_SCHEMA = "asklegal.hk-case-proposition-evidence/v1"
_CODEPOINT_FIXTURE_TOKENIZER = "HK_CASE_CODEPOINT_FIXTURE_V1"
_COURTS = frozenset({"CA", "CFA", "CFI", "CT"})
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


class HKCaseAdmissionTokenCounter(Protocol):
    """Exact tokenizer supplied by the processing owner for live admission."""

    @property
    def tokenizer_id(self) -> str:
        """Return the exact tokenizer named by the semantic profile."""
        ...

    @property
    def profile_fingerprint(self) -> str:
        """Return the exact profile-bound counter fingerprint."""
        ...

    def count(self, text: str) -> int:
        """Count exact rendered text without provider or registry access."""
        ...


class HKCasePropositionRequestErrorCode(StrEnum):
    """Closed failures for pure proposition-request construction."""

    BUNDLE_INVALID = "HK_CASE_PROPOSITION_BUNDLE_INVALID"
    PROFILE_BINDING_INVALID = "HK_CASE_PROPOSITION_PROFILE_BINDING_INVALID"
    READING_LEDGER_INVALID = "HK_CASE_PROPOSITION_READING_LEDGER_INVALID"
    REQUEST_INVALID = "HK_CASE_PROPOSITION_REQUEST_INVALID"


class HKCasePropositionRequestError(ValueError):
    """One closed request-construction error without untrusted detail."""

    code: HKCasePropositionRequestErrorCode

    def __init__(self, code: HKCasePropositionRequestErrorCode) -> None:
        """Expose one stable local error code without retaining source text."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HKCaseAdmittedProposition:
    """Source-neutral admitted proposition, distinct from the mature ledger candidate."""

    proposition_id: str
    candidate_id: str
    proposition_text: str
    text_mode: str
    court_id: str
    opinion_id: str
    judge_names: tuple[str, ...]
    qualification_texts: tuple[str, ...]
    exception_texts: tuple[str, ...]
    support_paragraph_refs: tuple[str, ...]
    support_fingerprint: str
    authority_role: HKCaseOpinionRole
    legal_issue: str
    material_context: str | None
    result_context: str
    quotation_paragraph_refs: tuple[str, ...]
    evidence_links: tuple[HKCaseAdmittedEvidenceLink, ...]

    def __post_init__(self) -> None:
        """Reject forged candidate shapes before any admission function observes them."""
        try:
            _identity(self.proposition_id)
            _identity(self.candidate_id)
            _text(self.proposition_text)
            if (
                type(self.text_mode) is not str
                or self.text_mode not in {"EXACT_QUOTATION", "FAITHFUL_DISTILLATION"}
                or type(self.court_id) is not str
                or self.court_id not in _COURTS
            ):
                raise TypeError
            _identity(self.opinion_id)
            _texts(self.judge_names)
            _optional_texts(self.qualification_texts)
            _optional_texts(self.exception_texts)
            _texts(self.support_paragraph_refs)
            _fingerprint(self.support_fingerprint)
            if (
                type(self.authority_role) is not HKCaseOpinionRole
                or type(self.material_context) not in {str, type(None)}
                or (self.material_context is not None and not self.material_context)
                or type(self.quotation_paragraph_refs) is not tuple
                or type(self.evidence_links) is not tuple
                or not self.quotation_paragraph_refs
                or not self.evidence_links
            ):
                raise TypeError
            _text(self.legal_issue)
            _text(self.result_context)
            _texts(self.quotation_paragraph_refs)
            for link in self.evidence_links:
                if type(link) is not HKCaseAdmittedEvidenceLink:
                    raise TypeError
                link.__post_init__()
        except HKCasePropositionRequestError:
            raise
        except Exception:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.REQUEST_INVALID
            ) from None


@dataclass(frozen=True, slots=True)
class HKCaseAdmittedEvidenceLink:
    """One explicit mature-output evidence role mapped to one retained paragraph."""

    role: HKCaseEvidenceRole
    paragraph_ref: str

    def __post_init__(self) -> None:
        """Reject loose role/ref shapes before output adaptation."""
        if (
            type(self.role) is not HKCaseEvidenceRole
            or type(self.paragraph_ref) is not str
            or not self.paragraph_ref
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)


@dataclass(frozen=True, slots=True)
class HKCaseAdmittedSemanticDecision:
    """Pure parsed decision input; provider truth/admission remains deliberately deferred."""

    request_id: str
    proposal_fingerprint: str
    complete_reading: bool
    challenge_complete: bool
    propositions: tuple[HKCaseAdmittedProposition, ...]
    unit_resolutions: tuple[HKCaseAdmittedUnitResolution, ...]

    def __post_init__(self) -> None:
        """Reject malformed or subclassed decision material at its construction boundary."""
        if (
            type(self.request_id) is not str
            or type(self.proposal_fingerprint) is not str
            or type(self.complete_reading) is not bool
            or type(self.challenge_complete) is not bool
            or type(self.propositions) is not tuple
            or type(self.unit_resolutions) is not tuple
            or any(type(item) is not HKCaseAdmittedProposition for item in self.propositions)
            or any(type(item) is not HKCaseAdmittedUnitResolution for item in self.unit_resolutions)
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        try:
            _identity(self.request_id)
            _fingerprint(self.proposal_fingerprint)
            for item in self.propositions:
                item.__post_init__()
            for item in self.unit_resolutions:
                item.__post_init__()
            if self.proposal_fingerprint != _propositions_fingerprint(
                self.propositions, self.unit_resolutions
            ):
                raise TypeError
        except HKCasePropositionRequestError:
            raise
        except Exception:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.REQUEST_INVALID
            ) from None


@dataclass(frozen=True, slots=True)
class HKCaseAdmittedUnitResolution:
    """One exact semantic-unit accounting decision, prior to mature-ledger adaptation."""

    paragraph_ref: str
    resolution: HKCaseUnitResolution
    primary_use: HKCasePrimaryUse
    evidence_roles: tuple[HKCaseEvidenceRole, ...]
    non_propositional_reason: HKCaseNonPropositionalReason | None
    citation_or_treatment_lead: bool
    screening_handoff_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject loose source-unit accounting before it can be adapted into a ledger."""
        if (
            type(self.paragraph_ref) is not str
            or not self.paragraph_ref
            or type(self.resolution) is not HKCaseUnitResolution
            or type(self.primary_use) is not HKCasePrimaryUse
            or type(self.evidence_roles) is not tuple
            or type(self.citation_or_treatment_lead) is not bool
            or type(self.screening_handoff_ids) is not tuple
            or (
                self.non_propositional_reason is not None
                and type(self.non_propositional_reason) is not HKCaseNonPropositionalReason
            )
            or any(type(item) is not HKCaseEvidenceRole for item in self.evidence_roles)
            or len(set(self.evidence_roles)) != len(self.evidence_roles)
            or any(
                type(item) is not str or fullmatch(_IDENTITY, item) is None
                for item in self.screening_handoff_ids
            )
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)


class HKCasePropositionAdmissionDisposition(StrEnum):
    """Closed complete local dispositions after ledger and output validation."""

    COMPLETE_PROPOSITIONS = "COMPLETE_PROPOSITIONS"
    COMPLETE_ZERO_PROPOSITIONS = "COMPLETE_ZERO_PROPOSITIONS"


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class _HKCasePropositionAdmissionIssuance:
    """Opaque process-local witness; its facts live only in the identity registry."""

    projection: bytes

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[object, ...]:
        """Forbid copying-by-serialization: a restart must replay source admission."""
        del protocol
        code = "HK_CASE_PROPOSITION_ISSUANCE_NOT_SERIALIZABLE"
        raise TypeError(code)


@dataclass(frozen=True, slots=True)
class _HKCasePropositionIssuedFacts:
    """Registry-only issuance facts that cannot be supplied by a result reconstruction."""

    projection: bytes
    projection_fingerprint: str
    request_pair: HKCasePropositionRequestPair
    admitted_decision: HKCaseAdmittedSemanticDecision
    result_reference: ReferenceType[HKCasePropositionAdmissionResult] | None


_ADMISSION_ISSUANCE_REGISTRY: WeakKeyDictionary[
    _HKCasePropositionAdmissionIssuance, _HKCasePropositionIssuedFacts
] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKCasePropositionAdmissionResult:
    """One coherent source-neutral ledger/output admission with no release authority."""

    disposition: HKCasePropositionAdmissionDisposition
    proposal_fingerprint: str
    propositions: tuple[HKCaseAdmittedProposition, ...]
    request_pair: HKCasePropositionRequestPair
    admitted_decision: HKCaseAdmittedSemanticDecision
    admission_projection: bytes
    admission_fingerprint: str
    issuance: _HKCasePropositionAdmissionIssuance
    ledger_request: HKCaseCoverageLedgerRequest
    ledger_result: HKCaseCoverageLedgerResult
    output_request: HKCaseOutputRequest
    output_result: HKCaseOutputResult

    @property
    def _issuance(self) -> _HKCasePropositionAdmissionIssuance:
        """Compatibility-only observer; it is not a replaceable result field."""
        return self.issuance

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[object, ...]:
        """Reject serialization: factory issuance is process-local rather than durable authority."""
        del protocol
        code = "HK_CASE_PROPOSITION_ADMISSION_NOT_SERIALIZABLE"
        raise TypeError(code)

    def __post_init__(self) -> None:
        """Replay both deterministic evaluators when a retained result is reconstructed."""
        try:
            if (
                type(self.disposition) is not HKCasePropositionAdmissionDisposition
                or type(self.propositions) is not tuple
                or any(type(item) is not HKCaseAdmittedProposition for item in self.propositions)
                or type(self.request_pair) is not HKCasePropositionRequestPair
                or type(self.admitted_decision) is not HKCaseAdmittedSemanticDecision
                or type(self.admission_projection) is not bytes
                or not self.admission_projection
                or _raw_fingerprint(self.admission_projection) != self.admission_fingerprint
                or type(self.ledger_request) is not HKCaseCoverageLedgerRequest
                or type(self.ledger_result) is not HKCaseCoverageLedgerResult
                or type(self.output_request) is not HKCaseOutputRequest
                or type(self.output_result) is not HKCaseOutputResult
                or evaluate_hk_case_coverage_ledger(self.ledger_request) != self.ledger_result
            ):
                raise TypeError
            _pair_facts(self.request_pair)
            decision = _admitted_decision_snapshot(self.admitted_decision)
            _validated_admission_inputs(self.request_pair, decision)
            if (
                self.propositions != decision.propositions
                or self.proposal_fingerprint != decision.proposal_fingerprint
                or self.admission_projection
                != canonical_hk_case_proposition_admission_projection(self.request_pair, decision)
            ):
                raise TypeError
            _issued_admission_facts(self)
            counter = HKCaseCodepointTokenCounter(self.output_request.tokenizer_profile_fingerprint)
            if evaluate_hk_case_output(self.output_request, counter=counter) != self.output_result:
                raise TypeError
            proposition_ids = tuple(item.proposition_id for item in self.propositions)
            if (
                self.output_request.ledger_fingerprint != self.ledger_result.request_fingerprint
                or self.output_request.ledger_proposition_ids != proposition_ids
                or tuple(item.proposition_id for item in self.output_request.propositions)
                != proposition_ids
                or not _result_propositions_match(
                    self.propositions,
                    self.ledger_request,
                    self.output_request,
                )
                or not _result_resolutions_match(decision, self.ledger_request)
            ):
                raise TypeError
            if self.disposition is HKCasePropositionAdmissionDisposition.COMPLETE_PROPOSITIONS:
                if (
                    not self.propositions
                    or self.ledger_result.outcome
                    is not HKCaseLedgerOutcome.COMPLETE_WITH_PROPOSITIONS
                    or self.output_result.outcome is not HKCaseOutputOutcome.VALID_OUTPUT
                ):
                    raise TypeError
            elif (
                self.propositions
                or self.ledger_result.outcome is not HKCaseLedgerOutcome.COMPLETE_NO_PROPOSITION
                or self.output_result.outcome is not HKCaseOutputOutcome.VALID_ZERO_OUTPUT
            ):
                raise TypeError
        except HKCasePropositionRequestError:
            raise
        except Exception:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.REQUEST_INVALID
            ) from None


def _issued_admission_facts(result: HKCasePropositionAdmissionResult) -> None:
    """Require the original in-process factory witness and its exact immutable issuance facts."""
    if type(result.issuance) is not _HKCasePropositionAdmissionIssuance:
        raise TypeError
    facts = _ADMISSION_ISSUANCE_REGISTRY.get(result.issuance)
    if (
        facts is None
        or result.issuance.projection != facts.projection
        or result.admission_projection != facts.projection
        or result.admission_fingerprint != facts.projection_fingerprint
        or result.request_pair is not facts.request_pair
        or result.admitted_decision is not facts.admitted_decision
        or (facts.result_reference is not None and facts.result_reference() is not result)
    ):
        raise TypeError


def _finalize_admission_issuance(result: HKCasePropositionAdmissionResult) -> None:
    """Bind a provisional factory witness to this exact result after construction completes."""
    if type(result.issuance) is not _HKCasePropositionAdmissionIssuance:
        raise TypeError
    facts = _ADMISSION_ISSUANCE_REGISTRY.get(result.issuance)
    if facts is None or facts.result_reference is not None:
        raise TypeError
    _ADMISSION_ISSUANCE_REGISTRY[result.issuance] = _HKCasePropositionIssuedFacts(
        projection=facts.projection,
        projection_fingerprint=facts.projection_fingerprint,
        request_pair=facts.request_pair,
        admitted_decision=facts.admitted_decision,
        result_reference=ref(result),
    )
    _issued_admission_facts(result)


def admit_hk_case_propositions(
    pair: HKCasePropositionRequestPair,
    decision: HKCaseAdmittedSemanticDecision,
    *,
    counter: HKCaseAdmissionTokenCounter | None = None,
) -> HKCasePropositionAdmissionResult:
    """Normalize every ordinary parsed-decision failure to the closed desk boundary."""
    try:
        return _admit_hk_case_propositions(pair, decision, counter=counter)
    except HKCasePropositionRequestError:
        raise
    except Exception:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.REQUEST_INVALID
        ) from None


def replay_hk_case_proposition_admission_projection(
    pair: HKCasePropositionRequestPair,
    decision: HKCaseAdmittedSemanticDecision,
) -> bytes:
    """Return the canonical source-validated projection without issuing a result authority."""
    try:
        validated = _validated_admission_inputs(pair, decision)
        return canonical_hk_case_proposition_admission_projection(pair, validated.decision)
    except HKCasePropositionRequestError:
        raise
    except Exception:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.REQUEST_INVALID
        ) from None


@dataclass(frozen=True, slots=True)
class _ValidatedHKCasePropositionAdmission:
    """Detached source-bound facts shared by factory admission and result replay."""

    decision: HKCaseAdmittedSemanticDecision
    source: dict[str, JsonValue]
    paragraph_texts: dict[str, str]
    resolution_by_ref: dict[str, HKCaseAdmittedUnitResolution]


def _validated_admission_inputs(
    pair: HKCasePropositionRequestPair,
    decision: HKCaseAdmittedSemanticDecision,
) -> _ValidatedHKCasePropositionAdmission:
    """Replay every source-bound input rule before either admission or result reconstruction."""
    if (
        type(pair) is not HKCasePropositionRequestPair
        or type(decision) is not HKCaseAdmittedSemanticDecision
    ):
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    _pair_facts(pair)
    decision = _admitted_decision_snapshot(decision)
    if (
        type(decision.request_id) is not str
        or decision.request_id != pair.decision.request_id
        or type(decision.proposal_fingerprint) is not str
        or decision.proposal_fingerprint
        != _propositions_fingerprint(decision.propositions, decision.unit_resolutions)
        or not decision.complete_reading
        or not decision.challenge_complete
        or type(decision.propositions) is not tuple
    ):
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    refs = set(pair.paragraph_refs)
    resolution_refs = tuple(item.paragraph_ref for item in decision.unit_resolutions)
    if set(resolution_refs) != refs or len(set(resolution_refs)) != len(resolution_refs):
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    proposition_refs = {
        reference for item in decision.propositions for reference in item.support_paragraph_refs
    }
    for item in decision.unit_resolutions:
        if item.paragraph_ref in proposition_refs:
            if item.primary_use not in {
                HKCasePrimaryUse.CONTEXT_EVIDENCE,
                HKCasePrimaryUse.PROPOSITION_EVIDENCE,
            }:
                raise HKCasePropositionRequestError(
                    HKCasePropositionRequestErrorCode.REQUEST_INVALID
                )
        elif (
            item.primary_use is not HKCasePrimaryUse.NON_PROPOSITIONAL
            or item.non_propositional_reason is None
            or item.evidence_roles
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    semantic_units = {item.unit_id: item for item in pair.decision.semantic_task.units}
    semantic_ranges = {item.range_id: item for item in pair.decision.semantic_task.evidence_ranges}
    semantic_opinions = {item.opinion_id: item for item in pair.decision.semantic_task.opinions}
    source = _judgment_from_evidence(pair.decision.evidence_bytes)
    paragraph_texts: dict[str, str] = {}
    source_opinions: dict[str, tuple[tuple[str, ...], HKCaseOpinionRole]] = {}
    opinions = source["opinions"]
    if type(opinions) is not list:
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    for opinion in opinions:
        if type(opinion) is not dict:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        opinion_id = _text(opinion["opinion_id"])
        judge_names_raw = opinion["judge_names"]
        if type(judge_names_raw) is not list:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        judge_names = tuple(_text(item) for item in judge_names_raw)
        role = _semantic_opinion_role(_text(opinion["opinion_role"]))
        source_opinions[opinion_id] = (judge_names, role)
        paragraphs = opinion["paragraphs"]
        if type(paragraphs) is not list:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        for paragraph in paragraphs:
            if type(paragraph) is not dict:
                raise HKCasePropositionRequestError(
                    HKCasePropositionRequestErrorCode.REQUEST_INVALID
                )
            paragraph_texts[f"{opinion_id}:{_text(paragraph['paragraph_id'])}"] = _text(
                paragraph["text"]
            )
    candidate_ids: set[str] = set()
    proposition_ids: set[str] = set()
    resolution_by_ref = {item.paragraph_ref: item for item in decision.unit_resolutions}
    for item in decision.propositions:
        if (
            type(item) is not HKCaseAdmittedProposition
            or type(item.support_paragraph_refs) is not tuple
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        if not item.support_paragraph_refs or not set(item.support_paragraph_refs).issubset(refs):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        if item.candidate_id in candidate_ids or item.proposition_id in proposition_ids:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        candidate_ids.add(item.candidate_id)
        proposition_ids.add(item.proposition_id)
        source_opinion = source_opinions.get(item.opinion_id)
        if (
            item.court_id != _text(source["court_id"])
            or source_opinion is None
            or item.judge_names != source_opinion[0]
            or item.authority_role is not source_opinion[1]
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        support_texts = tuple(paragraph_texts[ref] for ref in item.support_paragraph_refs)
        if item.support_fingerprint != _support_fingerprint(
            item.support_paragraph_refs, paragraph_texts
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        if any(
            text not in support_texts for text in item.qualification_texts + item.exception_texts
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        if item.text_mode == "EXACT_QUOTATION" and item.proposition_text not in support_texts:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        if not item.quotation_paragraph_refs or not set(item.quotation_paragraph_refs).issubset(
            set(item.support_paragraph_refs)
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        required_roles = {
            HKCaseEvidenceRole.ANSWER,
            HKCaseEvidenceRole.APPLICATION,
            HKCaseEvidenceRole.ATTRIBUTION,
            HKCaseEvidenceRole.CONTEXT,
            HKCaseEvidenceRole.ISSUE,
            HKCaseEvidenceRole.QUALIFICATION,
            HKCaseEvidenceRole.QUOTATION,
            HKCaseEvidenceRole.RESULT,
        }
        if (
            len({(link.role, link.paragraph_ref) for link in item.evidence_links})
            != len(item.evidence_links)
            or any(
                link.paragraph_ref not in item.support_paragraph_refs
                for link in item.evidence_links
            )
            or {link.role for link in item.evidence_links} != required_roles
            or {
                link.paragraph_ref
                for link in item.evidence_links
                if link.role is HKCaseEvidenceRole.QUOTATION
            }
            != set(item.quotation_paragraph_refs)
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        roles = {
            role
            for resolution in decision.unit_resolutions
            if resolution.paragraph_ref in item.support_paragraph_refs
            for role in resolution.evidence_roles
        }
        if not {link.role for link in item.evidence_links}.issubset(roles):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        if any(
            link.role not in resolution_by_ref[link.paragraph_ref].evidence_roles
            for link in item.evidence_links
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        if not any(
            resolution_by_ref[reference].primary_use is HKCasePrimaryUse.PROPOSITION_EVIDENCE
            for reference in item.support_paragraph_refs
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        opinion_ids = {reference.split(":", 1)[0] for reference in item.support_paragraph_refs}
        if opinion_ids != {item.opinion_id}:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        semantic_opinion = semantic_opinions.get(_derived_id("opinion", item.opinion_id))
        if semantic_opinion is None or semantic_opinion.role is not item.authority_role:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        for reference in item.support_paragraph_refs:
            paragraph_id = reference.split(":", 1)[1]
            unit_id = _derived_id("unit", f"{item.opinion_id}:{paragraph_id}")
            range_id = _derived_id("range", f"{item.opinion_id}:{paragraph_id}")
            unit = semantic_units.get(unit_id)
            range_item = semantic_ranges.get(range_id)
            if unit is None or range_item is None or range_item.unit_id != unit_id:
                raise HKCasePropositionRequestError(
                    HKCasePropositionRequestErrorCode.REQUEST_INVALID
                )
    return _ValidatedHKCasePropositionAdmission(
        decision=decision,
        source=source,
        paragraph_texts=paragraph_texts,
        resolution_by_ref=resolution_by_ref,
    )


def _admit_hk_case_propositions(
    pair: HKCasePropositionRequestPair,
    decision: HKCaseAdmittedSemanticDecision,
    *,
    counter: HKCaseAdmissionTokenCounter | None,
) -> HKCasePropositionAdmissionResult:
    """Build mature ledger/output artifacts from one already source-validated decision."""
    validated = _validated_admission_inputs(pair, decision)
    decision = validated.decision
    source = validated.source
    paragraph_texts = validated.paragraph_texts
    resolution_by_ref = validated.resolution_by_ref
    units: list[HKCaseCoverageUnit] = []
    by_opinion: dict[str, list[str]] = {}
    for index, reference in enumerate(pair.paragraph_refs, start=1):
        opinion_id, paragraph_id = reference.split(":", 1)
        unit_id = _derived_id("unit", f"{opinion_id}:{paragraph_id}")
        range_id = _derived_id("range", f"{opinion_id}:{paragraph_id}")
        resolution = resolution_by_ref[reference]
        units.append(
            HKCaseCoverageUnit(
                unit_id,
                _derived_id("opinion", opinion_id),
                index,
                HKCaseCoverageUnitKind.PARAGRAPH,
                range_id,
                _raw_fingerprint(paragraph_texts[reference].encode("utf-8")),
                (resolution.resolution,),
                (resolution.primary_use,),
                resolution.evidence_roles,
                resolution.non_propositional_reason,
                resolution.citation_or_treatment_lead,
                resolution.screening_handoff_ids,
            )
        )
        by_opinion.setdefault(_derived_id("opinion", opinion_id), []).append(unit_id)
    segments = tuple(
        HKCaseCoverageSegment(_derived_id("segment", opinion_id), opinion_id, tuple(unit_ids), ())
        for opinion_id, unit_ids in by_opinion.items()
    )
    components = {
        item.component_role: item.fingerprint
        for item in pair.decision.semantic_task.workflow_components
    }
    ledger_request = HKCaseCoverageLedgerRequest(
        pair.decision.semantic_task.judicial_decision_id,
        pair.decision.semantic_task.official_version_id,
        pair.decision.semantic_task.artifact_fingerprint,
        components["PARSER_PROFILE"],
        components["SOURCE_RULEBOOK"],
        pair.decision.semantic_task.cutoff,
        True,
        pair.decision.evidence_refs,
        True,
        tuple(
            HKCaseOpinion(item.opinion_id, item.role, item.judge_ids)
            for item in pair.decision.semantic_task.opinions
        ),
        tuple(units),
        segments,
        tuple(
            HKCasePropositionCandidate(
                item.candidate_id,
                HKCaseCandidateOutcome.ACCEPTED,
                tuple(
                    _derived_id("unit", f"{ref.split(':', 1)[0]}:{ref.split(':', 1)[1]}")
                    for ref in item.support_paragraph_refs
                ),
            )
            for item in decision.propositions
        ),
    )
    ledger = evaluate_hk_case_coverage_ledger(ledger_request)
    if ledger.outcome not in {
        HKCaseLedgerOutcome.COMPLETE_WITH_PROPOSITIONS,
        HKCaseLedgerOutcome.COMPLETE_NO_PROPOSITION,
    }:
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    output_request = _output_request(
        pair=pair,
        propositions=tuple(decision.propositions),
        ledger_result=ledger,
        paragraph_texts=paragraph_texts,
        source=source,
        counter=counter,
    )
    output_counter = (
        HKCaseCodepointTokenCounter(output_request.tokenizer_profile_fingerprint)
        if counter is None
        else counter
    )
    output_result = evaluate_hk_case_output(output_request, counter=output_counter)
    if output_result.outcome is HKCaseOutputOutcome.VALID_OUTPUT:
        disposition = HKCasePropositionAdmissionDisposition.COMPLETE_PROPOSITIONS
    elif output_result.outcome is HKCaseOutputOutcome.VALID_ZERO_OUTPUT:
        disposition = HKCasePropositionAdmissionDisposition.COMPLETE_ZERO_PROPOSITIONS
    else:
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    projection = canonical_hk_case_proposition_admission_projection(pair, decision)
    issuance = _HKCasePropositionAdmissionIssuance(projection=projection)
    _ADMISSION_ISSUANCE_REGISTRY[issuance] = _HKCasePropositionIssuedFacts(
        projection=projection,
        projection_fingerprint=_raw_fingerprint(projection),
        request_pair=pair,
        admitted_decision=decision,
        result_reference=None,
    )
    result = HKCasePropositionAdmissionResult(
        disposition=disposition,
        proposal_fingerprint=decision.proposal_fingerprint,
        propositions=tuple(decision.propositions),
        request_pair=pair,
        admitted_decision=decision,
        admission_projection=projection,
        admission_fingerprint=_raw_fingerprint(projection),
        issuance=issuance,
        ledger_request=ledger_request,
        ledger_result=ledger,
        output_request=output_request,
        output_result=output_result,
    )
    _finalize_admission_issuance(result)
    return result


def _output_request(
    *,
    pair: HKCasePropositionRequestPair,
    propositions: tuple[HKCaseAdmittedProposition, ...],
    ledger_result: HKCaseCoverageLedgerResult,
    paragraph_texts: dict[str, str],
    source: dict[str, JsonValue],
    counter: HKCaseAdmissionTokenCounter | None,
) -> HKCaseOutputRequest:
    """Adapt retained original paragraphs into the existing mature output contract."""
    profile = _profile_document(pair.decision.profile_bytes)
    tokenizer = _text(profile["tokenizer"])
    counter_fingerprint = fingerprint(
        checked_json_value(
            {"tokenizer": tokenizer, "profile_fingerprint": pair.decision.profile_fingerprint}
        )
    )
    if counter is None:
        if tokenizer != _CODEPOINT_FIXTURE_TOKENIZER:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        output_counter: HKCaseAdmissionTokenCounter = HKCaseCodepointTokenCounter(
            counter_fingerprint
        )  # type: ignore[assignment]
    else:
        if counter.tokenizer_id != tokenizer or counter.profile_fingerprint != counter_fingerprint:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        output_counter = counter
    source_units: list[HKCaseSourceUnitText] = []
    source_ranges: list[HKCaseSourceRange] = []
    range_by_paragraph: dict[str, str] = {}
    for source_order, paragraph_ref in enumerate(pair.paragraph_refs, start=1):
        opinion_id, paragraph_id = paragraph_ref.split(":", 1)
        exact_text = paragraph_texts[paragraph_ref]
        unit_id = _derived_id("unit", f"{opinion_id}:{paragraph_id}")
        range_id = _derived_id("range", f"{opinion_id}:{paragraph_id}")
        source_units.append(HKCaseSourceUnitText(unit_id, source_order, exact_text))
        source_ranges.append(
            HKCaseSourceRange(
                range_id,
                unit_id,
                0,
                len(exact_text.encode("utf-8")),
                _raw_fingerprint(exact_text.encode("utf-8")),
            )
        )
        range_by_paragraph[paragraph_ref] = range_id
    case_name = _text(source["case_name"])
    citation = _text(source["citation"])
    court = _text(source["court_id"])
    decision_date = _text(source["decision_date"])
    output_propositions = tuple(
        _output_proposition(
            proposition,
            case_name=case_name,
            citation=citation,
            court=court,
            decision_date=decision_date,
            paragraph_texts=paragraph_texts,
            range_by_paragraph=range_by_paragraph,
        )
        for proposition in propositions
    )
    candidates = tuple(
        HKCaseOutputCandidate(
            item.candidate_id,
            HKCaseCandidateOutcome.ACCEPTED,
            (item.proposition_id,),
            (),
            None,
        )
        for item in propositions
    )
    proposed_records = tuple(
        build_hk_case_proposed_serving_record(
            record_id=_derived_id("record", item.proposition_id),
            proposition=item,
            ledger_fingerprint=ledger_result.request_fingerprint,
            counter=output_counter,
        )
        for item in output_propositions
    )
    return HKCaseOutputRequest(
        pair.decision.semantic_task.judicial_decision_id,
        pair.decision.semantic_task.official_version_id,
        ledger_result.request_fingerprint,
        HK_CASE_OUTPUT_RENDERER_ID,
        counter_fingerprint,
        _positive_int(profile["max_output_tokens"]),
        pair.decision.authorities.output_budget_bytes,
        True,
        tuple(item.candidate_id for item in candidates),
        candidates,
        tuple(source_units),
        tuple(source_ranges),
        output_propositions,
        tuple(item.proposition_id for item in propositions),
        proposed_records,
    )


def _output_proposition(
    proposition: HKCaseAdmittedProposition,
    *,
    case_name: str,
    citation: str,
    court: str,
    decision_date: str,
    paragraph_texts: dict[str, str],
    range_by_paragraph: dict[str, str],
) -> HKCaseOutputProposition:
    """Copy only accepted source-neutral proposition facts into one mature record."""
    quotation_refs = tuple(proposition.quotation_paragraph_refs)
    quotation_links = tuple(
        item.paragraph_ref
        for item in proposition.evidence_links
        if item.role is HKCaseEvidenceRole.QUOTATION
    )
    if quotation_links != quotation_refs:
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    qualifications = proposition.qualification_texts + proposition.exception_texts
    return HKCaseOutputProposition(
        proposition.proposition_id,
        proposition.candidate_id,
        case_name,
        citation,
        court,
        decision_date,
        proposition.opinion_id,
        proposition.authority_role,
        proposition.legal_issue,
        proposition.proposition_text,
        proposition.material_context,
        "\n".join(qualifications) if qualifications else None,
        proposition.result_context,
        tuple(
            HKCasePropositionEvidenceLink(link.role, range_by_paragraph[link.paragraph_ref])
            for link in proposition.evidence_links
        ),
        tuple(
            HKCaseQuotation(range_by_paragraph[reference], paragraph_texts[reference])
            for reference in quotation_refs
        ),
        "No authority-state claim is made by this source-neutral admission.",
        False,
        None,
    )


@dataclass(frozen=True, slots=True)
class HKCasePropositionReadingLedgerEntry:
    """One completely supplied original-language paragraph reading obligation."""

    paragraph_ref: str
    evidence_ref: str
    text_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCasePropositionRequestAuthorities:
    """Exact non-profile authorities required to construct one proposition semantic request."""

    processing_cutoff: str
    source_snapshot_id: str
    source_snapshot_fingerprint: str
    judgment_artifact_fingerprint: str
    official_version_id: str
    official_version_fingerprint: str
    decision_workflow_components: tuple[HKCaseSemanticWorkflowComponent, ...]
    challenge_workflow_components: tuple[HKCaseSemanticWorkflowComponent, ...]
    output_budget_bytes: int

    def __post_init__(self) -> None:
        """Require one closed, non-synthesized component fingerprint per workflow role."""
        if (
            type(self.processing_cutoff) is not str
            or type(self.source_snapshot_id) is not str
            or type(self.source_snapshot_fingerprint) is not str
            or type(self.judgment_artifact_fingerprint) is not str
            or type(self.official_version_id) is not str
            or type(self.official_version_fingerprint) is not str
            or type(self.decision_workflow_components) is not tuple
            or type(self.challenge_workflow_components) is not tuple
            or type(self.output_budget_bytes) is not int
            or self.output_budget_bytes <= 0
        ):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        if fullmatch(_ISO_DATE, self.processing_cutoff) is None:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
        _identity(self.source_snapshot_id)
        _fingerprint(self.source_snapshot_fingerprint)
        _fingerprint(self.judgment_artifact_fingerprint)
        _identity(self.official_version_id)
        _fingerprint(self.official_version_fingerprint)
        for components in (
            self.decision_workflow_components,
            self.challenge_workflow_components,
        ):
            for item in components:
                if type(item) is not HKCaseSemanticWorkflowComponent:
                    raise HKCasePropositionRequestError(
                        HKCasePropositionRequestErrorCode.REQUEST_INVALID
                    )
            roles = tuple(_text(item.component_role) for item in components)
            if set(roles) != set(_WORKFLOW_ROLES) or len(roles) != len(set(roles)):
                raise HKCasePropositionRequestError(
                    HKCasePropositionRequestErrorCode.REQUEST_INVALID
                )
            for item in components:
                _fingerprint(item.fingerprint)


@dataclass(frozen=True, slots=True)
class HKCasePropositionSemanticRequest:
    """One detached request for a later processing-owned semantic runner adapter."""

    request_id: str
    task: str
    phase: str
    profile_id: str
    profile_fingerprint: str
    profile_bytes: bytes
    subject_id: str
    evidence_refs: tuple[str, ...]
    evidence_bytes: bytes
    input_fingerprint: str
    source_snapshot_fingerprint: str
    authorities: HKCasePropositionRequestAuthorities
    reading_ledger: tuple[HKCasePropositionReadingLedgerEntry, ...]
    semantic_task: HKCaseSemanticTaskRequest

    def __post_init__(self) -> None:
        """Revalidate direct reconstruction rather than trusting cached request fields."""
        try:
            _request_facts(self)
        except HKCasePropositionRequestError:
            raise
        except Exception:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.REQUEST_INVALID
            ) from None


@dataclass(frozen=True, slots=True)
class HKCasePropositionChallengePreparation:
    """Inert challenge material that cannot be invoked before a validated proposal exists."""

    profile_id: str
    profile_fingerprint: str
    profile_bytes: bytes
    subject_id: str
    evidence_refs: tuple[str, ...]
    evidence_bytes: bytes
    input_fingerprint: str
    source_snapshot_fingerprint: str
    authorities: HKCasePropositionRequestAuthorities
    reading_ledger: tuple[HKCasePropositionReadingLedgerEntry, ...]

    def __post_init__(self) -> None:
        """Revalidate complete retained evidence and exact challenge-profile material."""
        try:
            _preparation_facts(self)
        except HKCasePropositionRequestError:
            raise
        except Exception:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.REQUEST_INVALID
            ) from None


@dataclass(frozen=True, slots=True)
class HKCasePropositionRequestPair:
    """One decision/challenge pair with identical judgment evidence and input binding."""

    decision: HKCasePropositionSemanticRequest
    challenge: HKCasePropositionChallengePreparation
    judgment_fingerprint: str
    paragraph_refs: tuple[str, ...]
    reading_ledger: tuple[HKCasePropositionReadingLedgerEntry, ...]

    def __post_init__(self) -> None:
        """Revalidate one decision/challenge binding and its complete reading ledger."""
        try:
            _pair_facts(self)
        except HKCasePropositionRequestError:
            raise
        except Exception:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.REQUEST_INVALID
            ) from None


def build_hk_case_proposition_requests(
    bundle: HKCaseJudgmentBundle,
    profiles: tuple[SemanticTaskProfile, SemanticTaskProfile],
    authorities: HKCasePropositionRequestAuthorities,
) -> HKCasePropositionRequestPair:
    """Build two inert, exact judgment-only requests without provider or vault I/O."""
    decision_profile, challenge_profile = _profile_pair_snapshot(profiles)
    authorities = _authority_snapshot(authorities)
    judgment, _, bundle_fingerprint = _bundle_snapshot(bundle)
    _authority_facts(authorities)
    if authorities.judgment_artifact_fingerprint != bundle_fingerprint:
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    _authority_profile_facts(authorities, decision_profile, _DECISION_TASK)
    _authority_profile_facts(authorities, challenge_profile, _CHALLENGE_TASK)
    if date.fromisoformat(authorities.processing_cutoff) < date.fromisoformat(
        _text(judgment["decision_date"])
    ):
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    evidence_document, paragraph_refs, ledger, evidence_refs = _judgment_evidence(
        judgment, authorities
    )
    evidence_bytes = canonicalize(checked_json_value(evidence_document))
    input_fingerprint = fingerprint(checked_json_value(evidence_document))
    _evidence_budgets(evidence_bytes, decision_profile, challenge_profile)
    subject_id = _text(judgment["judgment_id"])
    decision = _request(
        task=_DECISION_TASK,
        phase="DECISION",
        profile=decision_profile,
        subject_id=subject_id,
        evidence_refs=evidence_refs,
        evidence_bytes=evidence_bytes,
        input_fingerprint=input_fingerprint,
        source_snapshot_fingerprint=authorities.source_snapshot_fingerprint,
        authorities=authorities,
        ledger=ledger,
        semantic_task=_semantic_task(
            judgment,
            task=_DECISION_TASK,
            profile_fingerprint=fingerprint(checked_json_value(decision_profile)),
            input_fingerprint=input_fingerprint,
            source_snapshot_fingerprint=authorities.source_snapshot_fingerprint,
            authorities=authorities,
        ),
    )
    challenge = _preparation(
        profile=challenge_profile,
        subject_id=subject_id,
        evidence_refs=evidence_refs,
        evidence_bytes=evidence_bytes,
        input_fingerprint=input_fingerprint,
        source_snapshot_fingerprint=authorities.source_snapshot_fingerprint,
        authorities=authorities,
        ledger=ledger,
    )
    return HKCasePropositionRequestPair(
        decision=decision,
        challenge=challenge,
        judgment_fingerprint=bundle_fingerprint,
        paragraph_refs=paragraph_refs,
        reading_ledger=ledger,
    )


def bind_hk_case_proposition_challenge(
    preparation: HKCasePropositionChallengePreparation,
    validated_proposal_fingerprint: str,
    authorities: HKCasePropositionRequestAuthorities,
) -> HKCasePropositionSemanticRequest:
    """Bind one actual validated proposal before emitting an executable full-judgment challenge."""
    _preparation_facts(preparation)
    proposal_fingerprint = _fingerprint(validated_proposal_fingerprint)
    profile = _profile_document(preparation.profile_bytes)
    bound_authorities = _authority_snapshot(authorities)
    _authority_facts(bound_authorities)
    if canonicalize(_authority_document(bound_authorities)) != canonicalize(
        _authority_document(preparation.authorities)
    ):
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    judgment = _judgment_from_evidence(preparation.evidence_bytes)
    return _request(
        task=_CHALLENGE_TASK,
        phase="CHALLENGE",
        profile=profile,
        subject_id=preparation.subject_id,
        evidence_refs=preparation.evidence_refs,
        evidence_bytes=preparation.evidence_bytes,
        input_fingerprint=preparation.input_fingerprint,
        source_snapshot_fingerprint=preparation.source_snapshot_fingerprint,
        authorities=bound_authorities,
        ledger=preparation.reading_ledger,
        semantic_task=_semantic_task(
            judgment,
            task=_CHALLENGE_TASK,
            profile_fingerprint=fingerprint(checked_json_value(profile)),
            input_fingerprint=preparation.input_fingerprint,
            source_snapshot_fingerprint=preparation.source_snapshot_fingerprint,
            authorities=bound_authorities,
            validated_proposal_fingerprint=proposal_fingerprint,
        ),
    )


def _bundle_snapshot(bundle: HKCaseJudgmentBundle) -> tuple[dict[str, JsonValue], str, str]:
    try:
        if type(bundle) is not HKCaseJudgmentBundle:
            raise TypeError
        bundle.__post_init__()
        judgment = bundle.judgment
        if judgment is None:
            raise TypeError
        opinions: list[JsonValue] = []
        for opinion in judgment.opinions:
            opinion.__post_init__()
            paragraphs: list[JsonValue] = []
            for paragraph in opinion.paragraphs:
                paragraph.__post_init__()
                paragraphs.append(
                    {
                        "paragraph_id": _text(paragraph.paragraph_id),
                        "locator": _text(paragraph.locator),
                        "text": _text(paragraph.text),
                    }
                )
            opinions.append(
                {
                    "opinion_id": _text(opinion.opinion_id),
                    "judge_names": list(_texts(opinion.judge_names)),
                    "opinion_role": _text(opinion.opinion_role),
                    "language": _text(opinion.language),
                    "evidence_ref": _text(opinion.evidence_ref),
                    "evidence_fingerprint": _fingerprint(opinion.evidence_fingerprint),
                    "evidence_byte_length": _positive_int(opinion.evidence_byte_length),
                    "content_fingerprint": _fingerprint(opinion.content_fingerprint),
                    "paragraphs": paragraphs,
                }
            )
        if not opinions:
            raise TypeError
        snapshot: dict[str, JsonValue] = {
            "judgment_id": _text(judgment.judgment_id),
            "case_name": _text(judgment.case_name),
            "court_id": _text(judgment.court_id),
            "decision_date": _text(judgment.decision_date),
            "citation": _citation_from_inventories(
                judgment.neutral_citations,
                judgment.reported_citations,
                judgment.proceeding_numbers,
            ),
            "opinions": opinions,
        }
        return (
            snapshot,
            fingerprint(checked_json_value(snapshot)),
            _fingerprint(bundle.bundle_fingerprint),
        )
    except HKCasePropositionRequestError:
        raise
    except Exception:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.BUNDLE_INVALID
        ) from None


def _profile_pair_snapshot(
    profiles: tuple[SemanticTaskProfile, SemanticTaskProfile],
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    try:
        if type(profiles) is not tuple or len(profiles) != 2:
            raise TypeError
        decision, challenge = (_profile_snapshot(item) for item in profiles)
        if (
            decision["task"] != _DECISION_TASK
            or challenge["task"] != _CHALLENGE_TASK
            or decision["profile_id"] == challenge["profile_id"]
            or decision["prompt_fingerprint"] == challenge["prompt_fingerprint"]
        ):
            raise TypeError
        return decision, challenge
    except HKCasePropositionRequestError:
        raise
    except Exception:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.PROFILE_BINDING_INVALID
        ) from None


def _profile_snapshot(profile: object) -> dict[str, JsonValue]:
    if type(profile) is not SemanticTaskProfile:
        raise TypeError
    fields: dict[str, JsonValue] = {
        "profile_id": _identity(profile.profile_id),
        "task": _text(profile.task),
        "provider": _text(profile.provider),
        "resource_class": _text(profile.resource_class),
        "geography_class": _text(profile.geography_class),
        "deployment_name": _text(profile.deployment_name),
        "model_id": _text(profile.model_id),
        "model_version": _text(profile.model_version),
        "api_contract": _text(profile.api_contract),
        "tokenizer": _text(profile.tokenizer),
        "prompt_fingerprint": _fingerprint(profile.prompt_fingerprint),
        "input_schema": _text(profile.input_schema),
        "output_schema": _text(profile.output_schema),
        "evidence_budget_bytes": _positive_int(profile.evidence_budget_bytes),
        "max_output_tokens": _positive_int(profile.max_output_tokens),
        "content_filter_policy": _text(profile.content_filter_policy),
        "retry_policy": _text(profile.retry_policy),
        "data_handling_profile": _text(profile.data_handling_profile),
        "evaluator_id": _text(profile.evaluator_id),
        "threshold_basis_points": _positive_int(profile.threshold_basis_points),
        "expires_at": _text(profile.expires_at),
        "stateful_features": _boolean(profile.stateful_features),
        "allowed_environments": list(_texts(profile.allowed_environments)),
    }
    if fields["stateful_features"] is True:
        raise TypeError
    return fields


def _judgment_evidence(
    judgment: dict[str, JsonValue],
    authorities: HKCasePropositionRequestAuthorities,
) -> tuple[
    dict[str, JsonValue],
    tuple[str, ...],
    tuple[HKCasePropositionReadingLedgerEntry, ...],
    tuple[str, ...],
]:
    opinions = judgment["opinions"]
    if not isinstance(opinions, list):
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
    refs: list[str] = []
    ledger: list[HKCasePropositionReadingLedgerEntry] = []
    evidence_opinions: list[JsonValue] = []
    for opinion in opinions:
        if not isinstance(opinion, dict):
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
        opinion_id = _text(opinion["opinion_id"])
        evidence_ref = _text(opinion["evidence_ref"])
        refs.append(evidence_ref)
        paragraphs = opinion["paragraphs"]
        if not isinstance(paragraphs, list) or not paragraphs:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
        copied_paragraphs: list[JsonValue] = []
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict):
                raise HKCasePropositionRequestError(
                    HKCasePropositionRequestErrorCode.BUNDLE_INVALID
                )
            paragraph_id = _text(paragraph["paragraph_id"])
            text = _text(paragraph["text"])
            paragraph_ref = f"{opinion_id}:{paragraph_id}"
            ledger.append(
                HKCasePropositionReadingLedgerEntry(
                    paragraph_ref=paragraph_ref,
                    evidence_ref=evidence_ref,
                    text_fingerprint=_raw_fingerprint(text.encode("utf-8")),
                )
            )
            copied_paragraphs.append(
                {
                    "paragraph_id": paragraph_id,
                    "locator": _text(paragraph["locator"]),
                    "text": text,
                }
            )
        evidence_opinions.append(
            {
                "opinion_id": opinion_id,
                "judge_names": opinion["judge_names"],
                "opinion_role": opinion["opinion_role"],
                "language": opinion["language"],
                "evidence_ref": evidence_ref,
                "evidence_fingerprint": opinion["evidence_fingerprint"],
                "evidence_byte_length": opinion["evidence_byte_length"],
                "content_fingerprint": opinion["content_fingerprint"],
                "paragraphs": copied_paragraphs,
            }
        )
    paragraph_refs = tuple(item.paragraph_ref for item in ledger)
    if len(set(refs)) != len(refs) or len(set(paragraph_refs)) != len(paragraph_refs):
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
    return (
        {
            "schema_id": _EVIDENCE_SCHEMA,
            "source_snapshot_id": authorities.source_snapshot_id,
            "source_snapshot_fingerprint": authorities.source_snapshot_fingerprint,
            "judgment_artifact_fingerprint": authorities.judgment_artifact_fingerprint,
            "official_version_id": authorities.official_version_id,
            "official_version_fingerprint": authorities.official_version_fingerprint,
            "judgment_id": judgment["judgment_id"],
            "case_name": judgment["case_name"],
            "court_id": judgment["court_id"],
            "decision_date": judgment["decision_date"],
            "citation": judgment["citation"],
            "opinions": evidence_opinions,
        },
        paragraph_refs,
        tuple(ledger),
        tuple(refs),
    )


def _request(
    *,
    task: str,
    phase: str,
    profile: dict[str, JsonValue],
    subject_id: str,
    evidence_refs: tuple[str, ...],
    evidence_bytes: bytes,
    input_fingerprint: str,
    source_snapshot_fingerprint: str,
    authorities: HKCasePropositionRequestAuthorities,
    ledger: tuple[HKCasePropositionReadingLedgerEntry, ...],
    semantic_task: HKCaseSemanticTaskRequest,
) -> HKCasePropositionSemanticRequest:
    profile_id = profile["profile_id"]
    if type(profile_id) is not str:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.PROFILE_BINDING_INVALID
        )
    return HKCasePropositionSemanticRequest(
        request_id=_request_id(
            task,
            input_fingerprint,
            fingerprint(checked_json_value(profile)),
            source_snapshot_fingerprint,
            authorities,
            semantic_task.validated_proposal_fingerprint,
        ),
        task=task,
        phase=phase,
        profile_id=profile_id,
        profile_fingerprint=fingerprint(checked_json_value(profile)),
        profile_bytes=canonicalize(checked_json_value(profile)),
        subject_id=subject_id,
        evidence_refs=evidence_refs,
        evidence_bytes=evidence_bytes,
        input_fingerprint=input_fingerprint,
        source_snapshot_fingerprint=source_snapshot_fingerprint,
        authorities=authorities,
        reading_ledger=ledger,
        semantic_task=semantic_task,
    )


def _preparation(
    *,
    profile: dict[str, JsonValue],
    subject_id: str,
    evidence_refs: tuple[str, ...],
    evidence_bytes: bytes,
    input_fingerprint: str,
    source_snapshot_fingerprint: str,
    authorities: HKCasePropositionRequestAuthorities,
    ledger: tuple[HKCasePropositionReadingLedgerEntry, ...],
) -> HKCasePropositionChallengePreparation:
    profile_id = profile["profile_id"]
    if type(profile_id) is not str:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.PROFILE_BINDING_INVALID
        )
    return HKCasePropositionChallengePreparation(
        profile_id=profile_id,
        profile_fingerprint=fingerprint(checked_json_value(profile)),
        profile_bytes=canonicalize(checked_json_value(profile)),
        subject_id=subject_id,
        evidence_refs=evidence_refs,
        evidence_bytes=evidence_bytes,
        input_fingerprint=input_fingerprint,
        source_snapshot_fingerprint=source_snapshot_fingerprint,
        authorities=authorities,
        reading_ledger=ledger,
    )


def _semantic_task(
    judgment: dict[str, JsonValue],
    *,
    task: str,
    profile_fingerprint: str,
    input_fingerprint: str,
    source_snapshot_fingerprint: str,
    authorities: HKCasePropositionRequestAuthorities,
    validated_proposal_fingerprint: str | None = None,
) -> HKCaseSemanticTaskRequest:
    """Adapt one full reading ledger into the existing complete semantic preflight envelope."""
    opinions_raw = judgment["opinions"]
    if type(opinions_raw) is not list:
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
    opinions: list[HKCaseSemanticOpinionManifest] = []
    units: list[HKCaseSemanticUnitManifest] = []
    supplied: list[HKCaseSemanticSuppliedUnit] = []
    ranges: list[HKCaseSemanticEvidenceRange] = []
    for opinion_index, raw_opinion in enumerate(opinions_raw, start=1):
        if type(raw_opinion) is not dict:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
        original_opinion_id = _text(raw_opinion["opinion_id"])
        raw_judge_names = raw_opinion["judge_names"]
        if type(raw_judge_names) is not list or not raw_judge_names:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
        judge_ids = tuple(
            _derived_id("judge", f"{original_opinion_id}:{index}:{_text(name)}")
            for index, name in enumerate(raw_judge_names, start=1)
        )
        opinions.append(
            HKCaseSemanticOpinionManifest(
                _derived_id("opinion", original_opinion_id),
                opinion_index,
                _semantic_opinion_role(_text(raw_opinion["opinion_role"])),
                judge_ids,
            )
        )
        paragraphs = raw_opinion["paragraphs"]
        if type(paragraphs) is not list:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
        for raw_paragraph in paragraphs:
            if type(raw_paragraph) is not dict:
                raise HKCasePropositionRequestError(
                    HKCasePropositionRequestErrorCode.BUNDLE_INVALID
                )
            paragraph_id = _text(raw_paragraph["paragraph_id"])
            text = _text(raw_paragraph["text"])
            unit_id = _derived_id("unit", f"{original_opinion_id}:{paragraph_id}")
            range_id = _derived_id("range", f"{original_opinion_id}:{paragraph_id}")
            units.append(
                HKCaseSemanticUnitManifest(
                    unit_id,
                    opinions[-1].opinion_id,
                    len(units) + 1,
                    True,
                    _raw_fingerprint(text.encode("utf-8")),
                    (),
                )
            )
            supplied.append(HKCaseSemanticSuppliedUnit(unit_id, text))
            ranges.append(
                HKCaseSemanticEvidenceRange(
                    range_id,
                    unit_id,
                    0,
                    len(text.encode("utf-8")),
                    _raw_fingerprint(text.encode("utf-8")),
                )
            )
    judgment_id = _text(judgment["judgment_id"])
    is_decision = task == _DECISION_TASK
    task_family = (
        HKCaseSemanticTaskFamily.ANALYSIS if is_decision else HKCaseSemanticTaskFamily.CHALLENGE
    )
    request_kind = (
        HKCaseSemanticRequestKind.FULL_JUDGMENT
        if is_decision
        else HKCaseSemanticRequestKind.FULL_JUDGMENT_CHALLENGE
    )
    return HKCaseSemanticTaskRequest(
        task_family=task_family,
        request_kind=request_kind,
        execution_id=_derived_id("execution", input_fingerprint),
        attempt_id=_derived_id(
            "attempt",
            task
            + input_fingerprint
            + profile_fingerprint
            + fingerprint(checked_json_value(_authority_document(authorities)))
            + (validated_proposal_fingerprint or ""),
        ),
        packet_id=None,
        judgment_work_id=_derived_id("judgment", judgment_id),
        workflow_components=(
            authorities.decision_workflow_components
            if is_decision
            else authorities.challenge_workflow_components
        ),
        judicial_decision_id=_derived_id("decision", judgment_id),
        official_version_id=authorities.official_version_id,
        artifact_fingerprint=authorities.judgment_artifact_fingerprint,
        source_snapshot_fingerprint=source_snapshot_fingerprint,
        cutoff=authorities.processing_cutoff,
        court=_text(judgment["court_id"]),
        decision_date=_text(judgment["decision_date"]),
        citation=_text(judgment["citation"]),
        original_language=_semantic_language(opinions_raw),
        opinions=tuple(opinions),
        units=tuple(units),
        assigned_primary_unit_ids=tuple(item.unit_id for item in units),
        supplied_units=tuple(supplied),
        evidence_ranges=tuple(ranges),
        dependencies=(),
        allowed_object_ids=tuple(item.unit_id for item in supplied)
        + tuple(item.range_id for item in ranges),
        required_evidence_role_codes=(
            "ANSWER",
            "APPLICATION",
            "ATTRIBUTION",
            "CONTEXT",
            "ISSUE",
            "QUALIFICATION",
            "QUOTATION",
            "RESULT",
        ),
        output_budget_bytes=authorities.output_budget_bytes,
        validated_proposal_fingerprint=validated_proposal_fingerprint,
        reconciled_objection_fingerprint=None,
        source_text_is_instruction=False,
        external_tools_permitted=False,
        hidden_reference_included=False,
        confidence_score_requested=False,
        source_evidence_available=True,
    )


def _request_facts(request: HKCasePropositionSemanticRequest) -> None:
    if type(request) is not HKCasePropositionSemanticRequest:
        raise TypeError
    _identity(request.request_id)
    if (request.task, request.phase) not in {
        (_DECISION_TASK, "DECISION"),
        (_CHALLENGE_TASK, "CHALLENGE"),
    }:
        raise TypeError
    _identity(request.profile_id)
    _fingerprint(request.profile_fingerprint)
    profile = _profile_document(request.profile_bytes)
    if (
        fingerprint(checked_json_value(profile)) != request.profile_fingerprint
        or profile["profile_id"] != request.profile_id
        or profile["task"] != request.task
    ):
        raise TypeError
    _text(request.subject_id)
    refs = _texts(request.evidence_refs)
    if len(set(refs)) != len(refs):
        raise TypeError
    if type(request.evidence_bytes) is not bytes or not request.evidence_bytes:
        raise TypeError
    _fingerprint(request.input_fingerprint)
    _fingerprint(request.source_snapshot_fingerprint)
    _authority_facts(request.authorities)
    _authority_profile_facts(request.authorities, profile, request.task)
    _ledger_facts(request.reading_ledger, refs)
    document = _evidence_document(request.evidence_bytes)
    if fingerprint(checked_json_value(document)) != request.input_fingerprint:
        raise TypeError
    if (
        document["source_snapshot_id"] != request.authorities.source_snapshot_id
        or document["source_snapshot_fingerprint"]
        != request.authorities.source_snapshot_fingerprint
        or document["judgment_artifact_fingerprint"]
        != request.authorities.judgment_artifact_fingerprint
        or document["official_version_id"] != request.authorities.official_version_id
        or document["official_version_fingerprint"]
        != request.authorities.official_version_fingerprint
    ):
        raise TypeError
    if request.subject_id != _text(document["judgment_id"]):
        raise TypeError
    if request.reading_ledger != _expected_ledger(request.evidence_bytes):
        raise TypeError
    if type(request.semantic_task) is not HKCaseSemanticTaskRequest:
        raise TypeError
    expected = _semantic_task(
        _judgment_from_evidence(request.evidence_bytes),
        task=request.task,
        profile_fingerprint=request.profile_fingerprint,
        input_fingerprint=request.input_fingerprint,
        source_snapshot_fingerprint=request.source_snapshot_fingerprint,
        authorities=request.authorities,
        validated_proposal_fingerprint=request.semantic_task.validated_proposal_fingerprint,
    )
    if canonicalize(
        checked_json_value(hk_case_semantic_task_request_document(expected))
    ) != canonicalize(
        checked_json_value(hk_case_semantic_task_request_document(request.semantic_task))
    ):
        raise TypeError
    if request.request_id != _request_id(
        request.task,
        request.input_fingerprint,
        request.profile_fingerprint,
        request.source_snapshot_fingerprint,
        request.authorities,
        request.semantic_task.validated_proposal_fingerprint,
    ):
        raise TypeError
    result = evaluate_hk_case_semantic_task_request(request.semantic_task)
    if (
        result.outcome is not HKCaseSemanticTaskOutcome.VALID_REQUEST
        or not result.complete_judgment_assignment
        or result.provider_call_authorized
    ):
        raise TypeError


def _pair_facts(pair: HKCasePropositionRequestPair) -> None:
    if (
        type(pair.decision) is not HKCasePropositionSemanticRequest
        or type(pair.challenge) is not HKCasePropositionChallengePreparation
    ):
        raise TypeError
    _request_facts(pair.decision)
    _preparation_facts(pair.challenge)
    if pair.judgment_fingerprint != pair.decision.authorities.judgment_artifact_fingerprint:
        raise TypeError
    paragraph_refs = _texts(pair.paragraph_refs)
    _ledger_facts(pair.reading_ledger, pair.decision.evidence_refs)
    ledger_refs = tuple(item.paragraph_ref for item in pair.reading_ledger)
    if (
        len(set(paragraph_refs)) != len(paragraph_refs)
        or paragraph_refs != ledger_refs
        or pair.decision.task != _DECISION_TASK
        or pair.decision.phase != "DECISION"
        or pair.decision.profile_id == pair.challenge.profile_id
        or pair.decision.profile_fingerprint == pair.challenge.profile_fingerprint
        or pair.decision.subject_id != pair.challenge.subject_id
        or pair.decision.evidence_refs != pair.challenge.evidence_refs
        or pair.decision.evidence_bytes != pair.challenge.evidence_bytes
        or pair.decision.input_fingerprint != pair.challenge.input_fingerprint
        or pair.decision.source_snapshot_fingerprint != pair.challenge.source_snapshot_fingerprint
        or pair.decision.reading_ledger != pair.challenge.reading_ledger
        or pair.decision.reading_ledger != pair.reading_ledger
        or canonicalize(_authority_document(pair.decision.authorities))
        != canonicalize(_authority_document(pair.challenge.authorities))
    ):
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
        )
    evidence_refs, evidence_paragraph_refs = _evidence_bindings(pair.decision.evidence_bytes)
    if evidence_refs != pair.decision.evidence_refs or evidence_paragraph_refs != paragraph_refs:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
        )


def _preparation_facts(preparation: HKCasePropositionChallengePreparation) -> None:
    if type(preparation) is not HKCasePropositionChallengePreparation:
        raise TypeError
    _identity(preparation.profile_id)
    _fingerprint(preparation.profile_fingerprint)
    profile = _profile_document(preparation.profile_bytes)
    if (
        fingerprint(checked_json_value(profile)) != preparation.profile_fingerprint
        or profile["profile_id"] != preparation.profile_id
        or profile["task"] != _CHALLENGE_TASK
    ):
        raise TypeError
    _text(preparation.subject_id)
    refs = _texts(preparation.evidence_refs)
    _fingerprint(preparation.input_fingerprint)
    _fingerprint(preparation.source_snapshot_fingerprint)
    _authority_facts(preparation.authorities)
    _authority_profile_facts(preparation.authorities, profile, _CHALLENGE_TASK)
    _ledger_facts(preparation.reading_ledger, refs)
    document = _judgment_from_evidence(preparation.evidence_bytes)
    if fingerprint(checked_json_value(document)) != preparation.input_fingerprint:
        raise TypeError
    if preparation.subject_id != _text(document["judgment_id"]):
        raise TypeError
    if (
        document["source_snapshot_id"] != preparation.authorities.source_snapshot_id
        or document["source_snapshot_fingerprint"]
        != preparation.authorities.source_snapshot_fingerprint
        or document["judgment_artifact_fingerprint"]
        != preparation.authorities.judgment_artifact_fingerprint
        or document["official_version_id"] != preparation.authorities.official_version_id
        or document["official_version_fingerprint"]
        != preparation.authorities.official_version_fingerprint
    ):
        raise TypeError
    if preparation.reading_ledger != _expected_ledger(preparation.evidence_bytes):
        raise TypeError
    evidence_refs, paragraph_refs = _evidence_bindings(preparation.evidence_bytes)
    if evidence_refs != refs or paragraph_refs != tuple(
        item.paragraph_ref for item in preparation.reading_ledger
    ):
        raise TypeError


def _ledger_facts(
    ledger: tuple[HKCasePropositionReadingLedgerEntry, ...], evidence_refs: tuple[str, ...]
) -> None:
    if type(ledger) is not tuple or not ledger:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
        )
    paragraph_refs: list[str] = []
    for item in ledger:
        if type(item) is not HKCasePropositionReadingLedgerEntry:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
            )
        paragraph_refs.append(_text(item.paragraph_ref))
        if _text(item.evidence_ref) not in evidence_refs:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
            )
        _fingerprint(item.text_fingerprint)
    if len(set(paragraph_refs)) != len(paragraph_refs):
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
        )


def _expected_ledger(raw: bytes) -> tuple[HKCasePropositionReadingLedgerEntry, ...]:
    document = _judgment_from_evidence(raw)
    opinions = document["opinions"]
    if type(opinions) is not list:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
        )
    entries: list[HKCasePropositionReadingLedgerEntry] = []
    for opinion in opinions:
        if type(opinion) is not dict:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
            )
        opinion_id = _text(opinion["opinion_id"])
        evidence_ref = _text(opinion["evidence_ref"])
        paragraphs = opinion["paragraphs"]
        if type(paragraphs) is not list:
            raise HKCasePropositionRequestError(
                HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
            )
        for paragraph in paragraphs:
            if type(paragraph) is not dict:
                raise HKCasePropositionRequestError(
                    HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
                )
            paragraph_id = _text(paragraph["paragraph_id"])
            text = _text(paragraph["text"])
            entries.append(
                HKCasePropositionReadingLedgerEntry(
                    f"{opinion_id}:{paragraph_id}",
                    evidence_ref,
                    _raw_fingerprint(text.encode("utf-8")),
                )
            )
    return tuple(entries)


def _evidence_document(raw: bytes) -> dict[str, JsonValue]:
    try:
        value = parse_json_bytes(raw, max_bytes=len(raw))
        if type(value) is not dict:
            raise TypeError
        return value
    except Exception:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.REQUEST_INVALID
        ) from None


def _evidence_bindings(raw: bytes) -> tuple[tuple[str, ...], tuple[str, ...]]:
    document = _evidence_document(raw)
    try:
        if set(document) != {
            "schema_id",
            "source_snapshot_id",
            "source_snapshot_fingerprint",
            "judgment_artifact_fingerprint",
            "official_version_id",
            "official_version_fingerprint",
            "judgment_id",
            "case_name",
            "court_id",
            "decision_date",
            "citation",
            "opinions",
        }:
            raise TypeError
        if _text(document["schema_id"]) != _EVIDENCE_SCHEMA:
            raise TypeError
        _identity(document["source_snapshot_id"])
        _fingerprint(document["source_snapshot_fingerprint"])
        _fingerprint(document["judgment_artifact_fingerprint"])
        _identity(document["official_version_id"])
        _fingerprint(document["official_version_fingerprint"])
        _text(document["judgment_id"])
        _text(document["case_name"])
        _text(document["court_id"])
        _text(document["decision_date"])
        _text(document["citation"])
        opinions = document["opinions"]
        if type(opinions) is not list or not opinions:
            raise TypeError
        refs: list[str] = []
        paragraph_refs: list[str] = []
        for opinion in opinions:
            if type(opinion) is not dict or set(opinion) != {
                "opinion_id",
                "judge_names",
                "opinion_role",
                "language",
                "evidence_ref",
                "evidence_fingerprint",
                "evidence_byte_length",
                "content_fingerprint",
                "paragraphs",
            }:
                raise TypeError
            opinion_id = _text(opinion["opinion_id"])
            refs.append(_text(opinion["evidence_ref"]))
            judge_names = opinion["judge_names"]
            if type(judge_names) is not list:
                raise TypeError
            _texts(tuple(judge_names))
            _text(opinion["opinion_role"])
            _text(opinion["language"])
            _fingerprint(opinion["evidence_fingerprint"])
            _positive_int(opinion["evidence_byte_length"])
            _fingerprint(opinion["content_fingerprint"])
            paragraphs = opinion["paragraphs"]
            if type(paragraphs) is not list or not paragraphs:
                raise TypeError
            for paragraph in paragraphs:
                if type(paragraph) is not dict or set(paragraph) != {
                    "paragraph_id",
                    "locator",
                    "text",
                }:
                    raise TypeError
                paragraph_id = paragraph["paragraph_id"]
                paragraph_refs.append(f"{opinion_id}:{_text(paragraph_id)}")
                _text(paragraph["locator"])
                _text(paragraph["text"])
        if len(set(refs)) != len(refs) or len(set(paragraph_refs)) != len(paragraph_refs):
            raise TypeError
        return tuple(refs), tuple(paragraph_refs)
    except Exception:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
        ) from None


def _text(value: object) -> str:
    if type(value) is not str or not value:
        raise TypeError
    return value


def _texts(value: tuple[object, ...]) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise TypeError
    return tuple(_text(item) for item in value)


def _identity(value: object) -> str:
    result = _text(value)
    if fullmatch(_IDENTITY, result) is None:
        raise TypeError
    return result


def _fingerprint(value: object) -> str:
    result = _text(value)
    if fullmatch(_FINGERPRINT, result) is None:
        raise TypeError
    return result


def _positive_int(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise TypeError
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise TypeError
    return value


def _raw_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _optional_texts(value: object) -> tuple[str, ...]:
    if not _is_object_tuple(value):
        raise TypeError
    return tuple(_text(item) for item in value)


def _is_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _support_fingerprint(paragraph_refs: tuple[str, ...], paragraph_texts: dict[str, str]) -> str:
    return fingerprint(
        checked_json_value(
            {
                "support": [
                    {
                        "paragraph_ref": reference,
                        "text_fingerprint": _raw_fingerprint(
                            paragraph_texts[reference].encode("utf-8")
                        ),
                    }
                    for reference in paragraph_refs
                ]
            }
        )
    )


def _proposition_document(item: HKCaseAdmittedProposition) -> dict[str, JsonValue]:
    if type(item) is not HKCaseAdmittedProposition:
        raise TypeError
    item.__post_init__()
    return {
        "proposition_id": item.proposition_id,
        "candidate_id": item.candidate_id,
        "proposition_text": item.proposition_text,
        "text_mode": item.text_mode,
        "court_id": item.court_id,
        "opinion_id": item.opinion_id,
        "judge_names": list(item.judge_names),
        "qualification_texts": list(item.qualification_texts),
        "exception_texts": list(item.exception_texts),
        "support_paragraph_refs": list(item.support_paragraph_refs),
        "support_fingerprint": item.support_fingerprint,
        "authority_role": item.authority_role.value,
        "legal_issue": item.legal_issue,
        "material_context": item.material_context,
        "result_context": item.result_context,
        "quotation_paragraph_refs": list(item.quotation_paragraph_refs),
        "evidence_links": [
            {"role": link.role.value, "paragraph_ref": link.paragraph_ref}
            for link in item.evidence_links
        ],
    }


def _propositions_fingerprint(
    items: tuple[HKCaseAdmittedProposition, ...],
    resolutions: tuple[HKCaseAdmittedUnitResolution, ...],
) -> str:
    """Bind proposal identity to every proposition and complete unit accounting."""
    if type(items) is not tuple or type(resolutions) is not tuple:
        raise TypeError
    return fingerprint(
        checked_json_value(
            {
                "propositions": [_proposition_document(item) for item in items],
                "unit_resolutions": [_unit_resolution_document(item) for item in resolutions],
            }
        )
    )


def _unit_resolution_document(item: HKCaseAdmittedUnitResolution) -> dict[str, JsonValue]:
    if type(item) is not HKCaseAdmittedUnitResolution:
        raise TypeError
    item.__post_init__()
    return {
        "paragraph_ref": item.paragraph_ref,
        "resolution": item.resolution.value,
        "primary_use": item.primary_use.value,
        "evidence_roles": [role.value for role in item.evidence_roles],
        "non_propositional_reason": (
            item.non_propositional_reason.value
            if item.non_propositional_reason is not None
            else None
        ),
        "citation_or_treatment_lead": item.citation_or_treatment_lead,
        "screening_handoff_ids": list(item.screening_handoff_ids),
    }


def _admitted_decision_snapshot(
    decision: HKCaseAdmittedSemanticDecision,
) -> HKCaseAdmittedSemanticDecision:
    if type(decision) is not HKCaseAdmittedSemanticDecision:
        raise TypeError
    decision.__post_init__()
    propositions = tuple(
        HKCaseAdmittedProposition(
            proposition_id=item.proposition_id,
            candidate_id=item.candidate_id,
            proposition_text=item.proposition_text,
            text_mode=item.text_mode,
            court_id=item.court_id,
            opinion_id=item.opinion_id,
            judge_names=tuple(item.judge_names),
            qualification_texts=tuple(item.qualification_texts),
            exception_texts=tuple(item.exception_texts),
            support_paragraph_refs=tuple(item.support_paragraph_refs),
            support_fingerprint=item.support_fingerprint,
            authority_role=item.authority_role,
            legal_issue=item.legal_issue,
            material_context=item.material_context,
            result_context=item.result_context,
            quotation_paragraph_refs=tuple(item.quotation_paragraph_refs),
            evidence_links=tuple(
                HKCaseAdmittedEvidenceLink(link.role, link.paragraph_ref)
                for link in item.evidence_links
            ),
        )
        for item in decision.propositions
    )
    resolutions = tuple(
        HKCaseAdmittedUnitResolution(
            paragraph_ref=item.paragraph_ref,
            resolution=item.resolution,
            primary_use=item.primary_use,
            evidence_roles=tuple(item.evidence_roles),
            non_propositional_reason=item.non_propositional_reason,
            citation_or_treatment_lead=item.citation_or_treatment_lead,
            screening_handoff_ids=tuple(item.screening_handoff_ids),
        )
        for item in decision.unit_resolutions
    )
    return HKCaseAdmittedSemanticDecision(
        request_id=decision.request_id,
        proposal_fingerprint=decision.proposal_fingerprint,
        complete_reading=decision.complete_reading,
        challenge_complete=decision.challenge_complete,
        propositions=propositions,
        unit_resolutions=resolutions,
    )


def _reading_ledger_document(
    entries: tuple[HKCasePropositionReadingLedgerEntry, ...],
) -> list[JsonValue]:
    if type(entries) is not tuple:
        raise TypeError
    return [
        {
            "paragraph_ref": entry.paragraph_ref,
            "evidence_ref": entry.evidence_ref,
            "text_fingerprint": entry.text_fingerprint,
        }
        for entry in entries
    ]


def _task2_request_document(request: HKCasePropositionSemanticRequest) -> dict[str, JsonValue]:
    """Project every result-affecting Task 2 decision request fact without aliases."""
    _request_facts(request)
    return {
        "request_id": request.request_id,
        "task": request.task,
        "phase": request.phase,
        "profile_id": request.profile_id,
        "profile_fingerprint": request.profile_fingerprint,
        "profile_bytes_fingerprint": _raw_fingerprint(request.profile_bytes),
        "subject_id": request.subject_id,
        "evidence_refs": list(request.evidence_refs),
        "evidence_bytes_fingerprint": _raw_fingerprint(request.evidence_bytes),
        "input_fingerprint": request.input_fingerprint,
        "source_snapshot_fingerprint": request.source_snapshot_fingerprint,
        "authorities": _authority_document(request.authorities),
        "reading_ledger": _reading_ledger_document(request.reading_ledger),
        "semantic_task": hk_case_semantic_task_request_document(request.semantic_task),
    }


def _task2_challenge_document(
    preparation: HKCasePropositionChallengePreparation,
) -> dict[str, JsonValue]:
    """Project the inert challenge authority, including its own profile/workflow facts."""
    _preparation_facts(preparation)
    return {
        "profile_id": preparation.profile_id,
        "profile_fingerprint": preparation.profile_fingerprint,
        "profile_bytes_fingerprint": _raw_fingerprint(preparation.profile_bytes),
        "subject_id": preparation.subject_id,
        "evidence_refs": list(preparation.evidence_refs),
        "evidence_bytes_fingerprint": _raw_fingerprint(preparation.evidence_bytes),
        "input_fingerprint": preparation.input_fingerprint,
        "source_snapshot_fingerprint": preparation.source_snapshot_fingerprint,
        "authorities": _authority_document(preparation.authorities),
        "reading_ledger": _reading_ledger_document(preparation.reading_ledger),
    }


def canonical_hk_case_proposition_admission_projection(
    pair: HKCasePropositionRequestPair,
    decision: HKCaseAdmittedSemanticDecision,
) -> bytes:
    """Return the one canonical projection; this pure helper never issues result authority."""
    _pair_facts(pair)
    snapshot = _admitted_decision_snapshot(decision)
    return canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-case-proposition-admission/v1",
                "task2_pair": {
                    "judgment_fingerprint": pair.judgment_fingerprint,
                    "paragraph_refs": list(pair.paragraph_refs),
                    "reading_ledger": _reading_ledger_document(pair.reading_ledger),
                    "decision": _task2_request_document(pair.decision),
                    "challenge": _task2_challenge_document(pair.challenge),
                },
                "admitted_decision": {
                    "request_id": snapshot.request_id,
                    "proposal_fingerprint": snapshot.proposal_fingerprint,
                    "complete_reading": snapshot.complete_reading,
                    "challenge_complete": snapshot.challenge_complete,
                    "propositions": [_proposition_document(item) for item in snapshot.propositions],
                    "unit_resolutions": [
                        _unit_resolution_document(item) for item in snapshot.unit_resolutions
                    ],
                },
            }
        )
    )


def _result_propositions_match(
    propositions: tuple[HKCaseAdmittedProposition, ...],
    ledger_request: HKCaseCoverageLedgerRequest,
    output_request: HKCaseOutputRequest,
) -> bool:
    if (
        type(propositions) is not tuple
        or type(ledger_request) is not HKCaseCoverageLedgerRequest
        or type(output_request) is not HKCaseOutputRequest
    ):
        return False
    outputs = {item.proposition_id: item for item in output_request.propositions}
    candidates = {item.candidate_id: item for item in ledger_request.candidates}
    opinions = {item.opinion_id: item for item in ledger_request.opinions}
    source_units = {item.unit_id: item.exact_text for item in output_request.source_units}
    for item in propositions:
        output = outputs.get(item.proposition_id)
        candidate = candidates.get(item.candidate_id)
        opinion = opinions.get(_derived_id("opinion", item.opinion_id))
        support_texts = {
            reference: source_units[_derived_id("unit", reference)]
            for reference in item.support_paragraph_refs
        }
        expected_links = tuple(
            HKCasePropositionEvidenceLink(link.role, _derived_id("range", link.paragraph_ref))
            for link in item.evidence_links
        )
        expected_quotations = tuple(
            HKCaseQuotation(_derived_id("range", reference), support_texts[reference])
            for reference in item.quotation_paragraph_refs
        )
        if (
            output is None
            or candidate is None
            or opinion is None
            or item.support_fingerprint
            != _support_fingerprint(item.support_paragraph_refs, support_texts)
            or output.candidate_id != item.candidate_id
            or output.court != item.court_id
            or output.opinion_label != item.opinion_id
            or output.authority_role is not item.authority_role
            or output.legal_issue != item.legal_issue
            or output.derived_statement != item.proposition_text
            or output.material_context != item.material_context
            or output.qualifications
            != (
                "\n".join(item.qualification_texts + item.exception_texts)
                if item.qualification_texts or item.exception_texts
                else None
            )
            or output.application_and_result != item.result_context
            or output.evidence_links != expected_links
            or output.quotations != expected_quotations
            or candidate.outcome is not HKCaseCandidateOutcome.ACCEPTED
            or candidate.evidence_unit_ids
            != tuple(_derived_id("unit", reference) for reference in item.support_paragraph_refs)
            or opinion.role is not item.authority_role
            or opinion.judge_ids
            != tuple(
                _derived_id("judge", f"{item.opinion_id}:{index}:{name}")
                for index, name in enumerate(item.judge_names, start=1)
            )
        ):
            return False
    return len(outputs) == len(propositions)


def _result_resolutions_match(
    decision: HKCaseAdmittedSemanticDecision,
    ledger_request: HKCaseCoverageLedgerRequest,
) -> bool:
    """Require the ledger to retain every exact admitted unit-resolution fact."""
    if (
        type(decision) is not HKCaseAdmittedSemanticDecision
        or type(ledger_request) is not HKCaseCoverageLedgerRequest
    ):
        return False
    units = {item.unit_id: item for item in ledger_request.units}
    if len(units) != len(decision.unit_resolutions):
        return False
    for resolution in decision.unit_resolutions:
        opinion_id, paragraph_id = resolution.paragraph_ref.split(":", 1)
        unit = units.get(_derived_id("unit", f"{opinion_id}:{paragraph_id}"))
        if (
            unit is None
            or unit.resolutions != (resolution.resolution,)
            or unit.primary_uses != (resolution.primary_use,)
            or unit.evidence_roles != resolution.evidence_roles
            or unit.non_propositional_reason is not resolution.non_propositional_reason
            or unit.citation_or_treatment_lead is not resolution.citation_or_treatment_lead
            or unit.screening_handoff_ids != resolution.screening_handoff_ids
        ):
            return False
    return True


def _request_id(
    task: str,
    input_fingerprint: str,
    profile_fingerprint: str,
    source_snapshot_fingerprint: str,
    authorities: HKCasePropositionRequestAuthorities,
    validated_proposal_fingerprint: str | None,
) -> str:
    material = canonicalize(
        checked_json_value(
            {
                "task": task,
                "input_fingerprint": input_fingerprint,
                "profile_fingerprint": profile_fingerprint,
                "source_snapshot_fingerprint": source_snapshot_fingerprint,
                "authorities": _authority_document(authorities),
                "validated_proposal_fingerprint": validated_proposal_fingerprint,
            }
        )
    )
    return f"request_{sha256(material).hexdigest()[:48]}"


def _evidence_budgets(
    evidence_bytes: bytes, decision: dict[str, JsonValue], challenge: dict[str, JsonValue]
) -> None:
    if len(evidence_bytes) > _profile_evidence_budget(decision) or len(
        evidence_bytes
    ) > _profile_evidence_budget(challenge):
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.PROFILE_BINDING_INVALID
        )


def _authority_facts(authorities: HKCasePropositionRequestAuthorities) -> None:
    if type(authorities) is not HKCasePropositionRequestAuthorities:
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    authorities.__post_init__()


def _authority_snapshot(
    authorities: HKCasePropositionRequestAuthorities,
) -> HKCasePropositionRequestAuthorities:
    """Detach every caller-owned authority leaf before any replayable input executes."""
    _authority_facts(authorities)
    return HKCasePropositionRequestAuthorities(
        processing_cutoff=authorities.processing_cutoff,
        source_snapshot_id=authorities.source_snapshot_id,
        source_snapshot_fingerprint=authorities.source_snapshot_fingerprint,
        judgment_artifact_fingerprint=authorities.judgment_artifact_fingerprint,
        official_version_id=authorities.official_version_id,
        official_version_fingerprint=authorities.official_version_fingerprint,
        decision_workflow_components=tuple(
            HKCaseSemanticWorkflowComponent(item.component_role, item.fingerprint)
            for item in authorities.decision_workflow_components
        ),
        challenge_workflow_components=tuple(
            HKCaseSemanticWorkflowComponent(item.component_role, item.fingerprint)
            for item in authorities.challenge_workflow_components
        ),
        output_budget_bytes=authorities.output_budget_bytes,
    )


def _authority_profile_facts(
    authorities: HKCasePropositionRequestAuthorities,
    profile: dict[str, JsonValue],
    task: str,
) -> None:
    components = (
        authorities.decision_workflow_components
        if task == _DECISION_TASK
        else authorities.challenge_workflow_components
    )
    role_map = {item.component_role: item.fingerprint for item in components}
    prompt = profile["prompt_fingerprint"]
    if (
        type(prompt) is not str
        or role_map["PROMPT"] != prompt
        or role_map["MODEL_SETTINGS"] != fingerprint(checked_json_value(profile))
    ):
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)


def _authority_document(authorities: HKCasePropositionRequestAuthorities) -> dict[str, JsonValue]:
    """Canonical retained authority material; it is part of replay identity."""
    _authority_facts(authorities)
    return {
        "processing_cutoff": authorities.processing_cutoff,
        "source_snapshot_id": authorities.source_snapshot_id,
        "source_snapshot_fingerprint": authorities.source_snapshot_fingerprint,
        "judgment_artifact_fingerprint": authorities.judgment_artifact_fingerprint,
        "official_version_id": authorities.official_version_id,
        "official_version_fingerprint": authorities.official_version_fingerprint,
        "decision_workflow_components": [
            {"role": item.component_role, "fingerprint": item.fingerprint}
            for item in authorities.decision_workflow_components
        ],
        "challenge_workflow_components": [
            {"role": item.component_role, "fingerprint": item.fingerprint}
            for item in authorities.challenge_workflow_components
        ],
        "output_budget_bytes": authorities.output_budget_bytes,
    }


def _profile_evidence_budget(profile: dict[str, JsonValue]) -> int:
    value = profile["evidence_budget_bytes"]
    if type(value) is not int or value <= 0:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.PROFILE_BINDING_INVALID
        )
    return value


def _profile_document(raw: bytes) -> dict[str, JsonValue]:
    document = _evidence_document(raw)
    expected = {
        "profile_id",
        "task",
        "provider",
        "resource_class",
        "geography_class",
        "deployment_name",
        "model_id",
        "model_version",
        "api_contract",
        "tokenizer",
        "prompt_fingerprint",
        "input_schema",
        "output_schema",
        "evidence_budget_bytes",
        "max_output_tokens",
        "content_filter_policy",
        "retry_policy",
        "data_handling_profile",
        "evaluator_id",
        "threshold_basis_points",
        "expires_at",
        "stateful_features",
        "allowed_environments",
    }
    if set(document) != expected:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.PROFILE_BINDING_INVALID
        )
    return document


def _judgment_from_evidence(raw: bytes) -> dict[str, JsonValue]:
    document = _evidence_document(raw)
    if set(document) != {
        "schema_id",
        "source_snapshot_id",
        "source_snapshot_fingerprint",
        "judgment_artifact_fingerprint",
        "official_version_id",
        "official_version_fingerprint",
        "judgment_id",
        "case_name",
        "court_id",
        "decision_date",
        "citation",
        "opinions",
    }:
        raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.REQUEST_INVALID)
    return document


def _derived_id(prefix: str, value: str) -> str:
    """Return a closed semantic-envelope identity without normalizing source evidence."""
    return f"{prefix}_{sha256(value.encode('utf-8')).hexdigest()[:48]}"


def _citation_from_inventories(
    neutral: tuple[object, ...],
    reported: tuple[object, ...],
    proceedings: tuple[object, ...],
) -> str:
    """Select the first retained source citation: neutral, then reported, then proceeding."""
    for inventory in (neutral, reported, proceedings):
        if inventory:
            return _text(inventory[0])
    raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)


def _semantic_opinion_role(value: str) -> HKCaseOpinionRole:
    """Map the judgment loader's source role to the mature semantic-manifest role."""
    mapping = {
        "COURT": HKCaseOpinionRole.COURT,
        "MAJORITY": HKCaseOpinionRole.LEAD,
        "CONCURRENCE": HKCaseOpinionRole.CONCURRENCE,
        "DISSENT": HKCaseOpinionRole.DISSENT,
        "SEPARATE": HKCaseOpinionRole.OTHER,
    }
    try:
        return mapping[value]
    except KeyError:
        raise HKCasePropositionRequestError(
            HKCasePropositionRequestErrorCode.BUNDLE_INVALID
        ) from None


def _semantic_language(opinions: list[JsonValue]) -> HKCaseOriginalLanguage:
    languages: set[str] = set()
    for item in opinions:
        if type(item) is not dict:
            raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
        languages.add(_text(item["language"]))
    if languages == {"EN"}:
        return HKCaseOriginalLanguage.ENGLISH
    if languages == {"ZH_HANT"}:
        return HKCaseOriginalLanguage.TRADITIONAL_CHINESE
    if languages.issubset({"EN", "ZH_HANT"}):
        return HKCaseOriginalLanguage.MIXED
    raise HKCasePropositionRequestError(HKCasePropositionRequestErrorCode.BUNDLE_INVALID)
