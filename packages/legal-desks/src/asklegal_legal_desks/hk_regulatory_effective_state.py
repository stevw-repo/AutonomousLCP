"""Deterministic, source-neutral HKEX applicability-branch state decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from re import fullmatch
from typing import Literal, TypeIs
from weakref import ReferenceType, ref
from zoneinfo import ZoneInfo

from .hk_regulatory_inventory import (
    HKEX_SCOPE_IDS,
    HKEXBranchState,
    HKEXMaterialDisposition,
    HKEXProcessingOutcome,
)

HKEX_EFFECTIVE_STATE_RULE_ID = "HKREG-EFFECTIVE-STATE-001"
HKEX_EFFECTIVE_STATE_CONTRACT_VERSION = "1.0.0"
_HONG_KONG = ZoneInfo("Asia/Hong_Kong")
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_DATE_LENGTH = 10
_PRIOR_TUPLE_LENGTH = 4
_SOURCE_NEUTRAL_PROJECTION_FACTORY_ONLY = "source-neutral state projections are factory-owned"

_SourceNeutralProjectionPrimitiveValues = tuple[
    object,
    object,
    object,
    object,
    object,
    object,
]


class HKEXEffectiveStateErrorCode(StrEnum):
    """Closed request-contract failures, distinct from legal-state uncertainty."""

    CONTRACT = "HKREG_EFFECTIVE_STATE_CONTRACT_INVALID"
    EVIDENCE = "HKREG_EFFECTIVE_STATE_EVIDENCE_INVALID"
    TEMPORAL = "HKREG_EFFECTIVE_STATE_TEMPORAL_INVALID"
    PRIOR = "HKREG_EFFECTIVE_STATE_PRIOR_INVALID"


class HKEXEffectiveStateError(ValueError):
    """One malformed request that cannot become a plausible legal decision."""

    code: HKEXEffectiveStateErrorCode

    def __init__(self, code: HKEXEffectiveStateErrorCode) -> None:
        """Create one stable fail-closed contract error."""
        self.code = code
        super().__init__(code.value)


class HKEXBranchBasis(StrEnum):
    """The supported mechanism controlling when one final branch applies."""

    ORDINARY = "ORDINARY"
    FIXED_DATE = "FIXED_DATE"
    CONDITIONAL = "CONDITIONAL"


class HKEXFinality(StrEnum):
    """Exact final-publication and approval status under ADR 0070."""

    FINAL_PUBLICATION_APPROVAL_INFERRED = "FINAL_PUBLICATION_APPROVAL_INFERRED"
    FINAL_DIRECT_APPROVAL_PROVED = "FINAL_DIRECT_APPROVAL_PROVED"
    CONSULTATION_OR_PROPOSAL = "CONSULTATION_OR_PROPOSAL"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    DIRECT_APPROVAL_REQUIRED_MISSING = "DIRECT_APPROVAL_REQUIRED_MISSING"
    CONFLICTING = "CONFLICTING"


class HKEXCurrentProductReconciliation(StrEnum):
    """Comparison with the fact-specific controlling prevailing English product."""

    MATCH = "MATCH"
    CONFLICT = "CONFLICT"
    MISSING_STALE_OR_INCOMPLETE = "MISSING_STALE_OR_INCOMPLETE"
    NOT_YET_REQUIRED = "NOT_YET_REQUIRED"


class HKEXConditionOperator(StrEnum):
    """Closed compound-condition operators."""

    ALL_OF = "ALL_OF"
    ANY_OF = "ANY_OF"


class HKEXConditionState(StrEnum):
    """Fresh fact-specific trigger evidence result."""

    OCCURRED = "OCCURRED"
    NOT_OCCURRED_FRESH = "NOT_OCCURRED_FRESH"
    UNRESOLVED = "UNRESOLVED"


class HKEXTransitionState(StrEnum):
    """Material applicability status for a potentially current branch."""

    ORDINARY = "ORDINARY"
    MATERIALLY_LIMITED_CURRENT = "MATERIALLY_LIMITED_CURRENT"
    PROVED_ENDED = "PROVED_ENDED"


class HKEXRetirementEvidence(StrEnum):
    """Exact successor or withdrawal evidence for a formerly current branch."""

    NONE = "NONE"
    COMPLETE_SUCCESSOR = "COMPLETE_SUCCESSOR"
    PARTIAL_SUCCESSOR = "PARTIAL_SUCCESSOR"
    OFFICIAL_WITHDRAWAL_NO_SUCCESSOR = "OFFICIAL_WITHDRAWAL_NO_SUCCESSOR"
    DISAPPEARANCE_ONLY = "DISAPPEARANCE_ONLY"
    CONFLICTING = "CONFLICTING"


class HKEXStateUncertainty(StrEnum):
    """Facts that could change the current branch result at the cutoff."""

    AMENDMENT_COMPONENT_MAPPING_AMBIGUOUS = "AMENDMENT_COMPONENT_MAPPING_AMBIGUOUS"
    EFFECTIVE_TIME_AMBIGUOUS = "EFFECTIVE_TIME_AMBIGUOUS"
    CONFLICTING_EFFECTIVE_FACTS = "CONFLICTING_EFFECTIVE_FACTS"
    TRANSITION_SCOPE_AMBIGUOUS = "TRANSITION_SCOPE_AMBIGUOUS"
    BRANCH_COLLISION_OR_GAP = "BRANCH_COLLISION_OR_GAP"
    OPTIONAL_CHINESE_SIGNALS_ENGLISH_DEFECT = "OPTIONAL_CHINESE_SIGNALS_ENGLISH_DEFECT"
    UNEXPLAINED_CURRENT_PRODUCT_CHANGE = "UNEXPLAINED_CURRENT_PRODUCT_CHANGE"


class HKEXSourceFailureImpact(StrEnum):
    """Whether a technical source failure can alter current-state truth."""

    NONE = "NONE"
    COULD_CHANGE_CURRENT = "COULD_CHANGE_CURRENT"


class HKEXServingChoice(StrEnum):
    """Separate ADR 0005 consequence; never a fresh effective-state claim."""

    NONE = "NONE"
    CARRY_FORWARD_LAST_APPROVED = "CARRY_FORWARD_LAST_APPROVED"
    WITHHOLD = "WITHHOLD"
    NO_REBUILD = "NO_REBUILD"


class HKEXEffectiveStateReason(StrEnum):
    """Stable terminal reason codes for the deterministic decision."""

    CURRENT_PRODUCT_MATCHED = "CURRENT_PRODUCT_MATCHED"
    TRANSITIONAL_CURRENT_PRODUCT_MATCHED = "TRANSITIONAL_CURRENT_PRODUCT_MATCHED"
    FUTURE_FIXED_DATE_PENDING = "FUTURE_FIXED_DATE_PENDING"
    FUTURE_CONDITION_PROVED_UNMET = "FUTURE_CONDITION_PROVED_UNMET"
    COMPLETE_SUCCESSOR_PROVED = "COMPLETE_SUCCESSOR_PROVED"
    WITHDRAWAL_WITHOUT_SUCCESSOR_PROVED = "WITHDRAWAL_WITHOUT_SUCCESSOR_PROVED"
    FINAL_PUBLICATION_NOT_PROVED = "FINAL_PUBLICATION_NOT_PROVED"
    CURRENT_PRODUCT_CONFLICT = "CURRENT_PRODUCT_CONFLICT"
    CURRENT_PRODUCT_EVIDENCE_INCOMPLETE = "CURRENT_PRODUCT_EVIDENCE_INCOMPLETE"
    CONDITION_EVIDENCE_UNRESOLVED = "CONDITION_EVIDENCE_UNRESOLVED"
    RETIREMENT_EVIDENCE_INSUFFICIENT = "RETIREMENT_EVIDENCE_INSUFFICIENT"
    UNRESOLVED_LEGAL_STATE_FACT = "UNRESOLVED_LEGAL_STATE_FACT"
    SOURCE_FAILURE_COULD_CHANGE_CURRENT = "SOURCE_FAILURE_COULD_CHANGE_CURRENT"
    TRANSITION_END_UNRESOLVED = "TRANSITION_END_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class HKEXConditionFact:
    """One condition and its exact registered fact authority."""

    condition_id: str
    registered_source_id: str
    state: HKEXConditionState
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject incomplete or non-authoritative trigger evidence."""
        _text(self.condition_id)
        _text(self.registered_source_id)
        if type(self.state) is not HKEXConditionState:
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
        _strings(self.evidence_refs)


@dataclass(frozen=True, slots=True)
class HKEXEffectiveStateRequest:
    """One complete atomic ADR 0071 decision request."""

    decision_id: str
    branch_id: str
    component_id: str
    scope_id: str
    legal_location_id: str
    cutoff: str
    update_part_id: str
    update_source_ranges: tuple[str, ...]
    current_product_ranges: tuple[str, ...]
    basis: HKEXBranchBasis
    finality: HKEXFinality
    effective_at: str | None
    condition_operator: HKEXConditionOperator | None
    conditions: tuple[HKEXConditionFact, ...]
    transition_state: HKEXTransitionState
    applicability_context: str | None
    retirement_evidence: HKEXRetirementEvidence
    predecessor_branch_id: str | None
    successor_branch_ids: tuple[str, ...]
    current_product_reconciliation: HKEXCurrentProductReconciliation
    uncertainty_codes: tuple[HKEXStateUncertainty, ...]
    source_failure_impact: HKEXSourceFailureImpact
    source_failure_choice: HKEXServingChoice
    source_rule_id: str
    evidence_refs: tuple[str, ...]
    evidence_fingerprint: str

    def __post_init__(self) -> None:
        """Validate every atomic identity, evidence, and branch fact."""
        _validate_request(self)


@dataclass(frozen=True, slots=True)
class HKEXEffectiveStateDecision:
    """One evidence-bound result with no serving or effect authority."""

    decision_id: str
    branch_id: str
    component_id: str
    scope_id: str
    legal_location_id: str
    cutoff: str
    state: HKEXBranchState
    disposition: HKEXMaterialDisposition
    processing_outcome: HKEXProcessingOutcome
    reason: HKEXEffectiveStateReason
    source_rule_id: str
    evidence_fingerprint: str
    source_failure_choice: HKEXServingChoice
    current_product_reconciled: bool
    search_record_authorized: bool = False
    serving_ready: bool = False

    def document(self, *, case_id: str) -> dict[str, str | bool]:
        """Return the exact conformance projection without granting authority."""
        _text(case_id)
        return {
            "case_id": case_id,
            "state": self.state.value,
            "disposition": self.disposition.value,
            "processing_outcome": self.processing_outcome.value,
            "reason": self.reason.value,
            "source_failure_choice": self.source_failure_choice.value,
            "current_product_reconciled": self.current_product_reconciled,
            "search_record_authorized": self.search_record_authorized,
            "serving_ready": self.serving_ready,
        }


@dataclass(frozen=True, slots=True)
class HKEXSourceNeutralPriorBranchState:
    """One prior source-neutral branch result with no source or serving claim."""

    component_id: str
    branch_id: str
    state: HKEXBranchState
    decision_fingerprint: str

    def __post_init__(self) -> None:
        """Reject a prior that cannot safely support retention consequences."""
        _source_neutral_prior_snapshot(self)


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class HKEXSourceNeutralStateProjection:
    """A source-neutral projection of an established deterministic branch result."""

    component_id: str
    branch_id: str
    state: Literal["CURRENT", "WAITING_ROOM", "HISTORY", "QUARANTINE"]
    keep_prior_current: bool
    reason_code: str
    evidence_refs: tuple[str, ...]

    def __init__(self) -> None:
        """Prevent direct construction outside the validated projection factory."""
        raise TypeError(_SOURCE_NEUTRAL_PROJECTION_FACTORY_ONLY)

    def __post_init__(self) -> None:
        """Require the exact factory-issued identity and immutable primitive snapshot."""
        _assert_source_neutral_projection_issued(self)

    def assert_factory_issued(self) -> None:
        """Revalidate this issued projection before any later consumer relies on it."""
        self.__post_init__()


_SOURCE_NEUTRAL_PROJECTION_ISSUANCE: dict[
    int,
    tuple[
        ReferenceType[HKEXSourceNeutralStateProjection],
        bytes,
        _SourceNeutralProjectionAuthority,
    ],
] = {}


@dataclass(frozen=True, slots=True)
class _SourceNeutralProjectionValues:
    """Primitive values issued together after one validated state decision."""

    component_id: str
    branch_id: str
    state: Literal["CURRENT", "WAITING_ROOM", "HISTORY", "QUARANTINE"]
    keep_prior_current: bool
    reason_code: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SourceNeutralProjectionAuthority:
    """One retained request, prior, and kernel result that the issuer replays."""

    request: HKEXEffectiveStateRequest
    prior: tuple[str, str, HKEXBranchState, str] | None
    decision: HKEXEffectiveStateDecision


def project_hkex_source_neutral_state(
    request: HKEXEffectiveStateRequest,
    prior: object,
) -> HKEXSourceNeutralStateProjection:
    """Project one established branch decision without interpreting source material."""
    authority = _source_neutral_projection_authority(request, prior)
    return _issue_source_neutral_projection(authority)


def _source_neutral_projection_authority(
    request: object,
    prior: object,
) -> _SourceNeutralProjectionAuthority:
    """Retain one validated request and exact deterministic decision for issuance replay."""
    request_snapshot = _source_neutral_request_snapshot(request)
    prior_snapshot = _source_neutral_prior_snapshot(prior)
    decision = decide_hkex_effective_state(request_snapshot)
    prior_component_id: str | None = None
    prior_branch_id: str | None = None
    if prior_snapshot is not None:
        prior_component_id, prior_branch_id, _, _ = prior_snapshot
        if prior_component_id != decision.component_id or prior_branch_id != decision.branch_id:
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.PRIOR)
    return _SourceNeutralProjectionAuthority(request_snapshot, prior_snapshot, decision)


def _source_neutral_request_snapshot(request: object) -> HKEXEffectiveStateRequest:
    """Rebuild one exact deep request snapshot before any legal-state decision."""
    if type(request) is not HKEXEffectiveStateRequest:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    try:
        decision_id = request.decision_id
        branch_id = request.branch_id
        component_id = request.component_id
        scope_id = request.scope_id
        legal_location_id = request.legal_location_id
        cutoff = request.cutoff
        update_part_id = request.update_part_id
        update_source_ranges = request.update_source_ranges
        current_product_ranges = request.current_product_ranges
        basis = request.basis
        finality = request.finality
        effective_at = request.effective_at
        condition_operator = request.condition_operator
        conditions = request.conditions
        transition_state = request.transition_state
        applicability_context = request.applicability_context
        retirement_evidence = request.retirement_evidence
        predecessor_branch_id = request.predecessor_branch_id
        successor_branch_ids = request.successor_branch_ids
        current_product_reconciliation = request.current_product_reconciliation
        uncertainty_codes = request.uncertainty_codes
        source_failure_impact = request.source_failure_impact
        source_failure_choice = request.source_failure_choice
        source_rule_id = request.source_rule_id
        evidence_refs = request.evidence_refs
        evidence_fingerprint = request.evidence_fingerprint
        _source_neutral_exact_texts(
            decision_id,
            branch_id,
            component_id,
            scope_id,
            legal_location_id,
            cutoff,
            update_part_id,
            source_rule_id,
            evidence_fingerprint,
        )
        _source_neutral_exact_optional_text(effective_at)
        _source_neutral_exact_optional_text(applicability_context)
        _source_neutral_exact_optional_text(predecessor_branch_id)
        _source_neutral_exact_enums(
            basis,
            HKEXBranchBasis,
            finality,
            HKEXFinality,
            transition_state,
            HKEXTransitionState,
            retirement_evidence,
            HKEXRetirementEvidence,
            current_product_reconciliation,
            HKEXCurrentProductReconciliation,
            source_failure_impact,
            HKEXSourceFailureImpact,
            source_failure_choice,
            HKEXServingChoice,
        )
        _source_neutral_exact_optional_enum(condition_operator, HKEXConditionOperator)
        _source_neutral_require(
            condition=(
                type(update_source_ranges) is tuple
                and type(current_product_ranges) is tuple
                and type(conditions) is tuple
                and type(successor_branch_ids) is tuple
                and type(uncertainty_codes) is tuple
                and type(evidence_refs) is tuple
            )
        )
        _source_neutral_exact_text_tuple(update_source_ranges)
        _source_neutral_exact_text_tuple(current_product_ranges)
        _source_neutral_exact_text_tuple(successor_branch_ids)
        _source_neutral_exact_text_tuple(evidence_refs)
        _source_neutral_exact_enum_tuple(uncertainty_codes, HKEXStateUncertainty)
        return HKEXEffectiveStateRequest(
            decision_id=decision_id,
            branch_id=branch_id,
            component_id=component_id,
            scope_id=scope_id,
            legal_location_id=legal_location_id,
            cutoff=cutoff,
            update_part_id=update_part_id,
            update_source_ranges=tuple(update_source_ranges),
            current_product_ranges=tuple(current_product_ranges),
            basis=basis,
            finality=finality,
            effective_at=effective_at,
            condition_operator=condition_operator,
            conditions=tuple(_source_neutral_condition_snapshot(item) for item in conditions),
            transition_state=transition_state,
            applicability_context=applicability_context,
            retirement_evidence=retirement_evidence,
            predecessor_branch_id=predecessor_branch_id,
            successor_branch_ids=tuple(successor_branch_ids),
            current_product_reconciliation=current_product_reconciliation,
            uncertainty_codes=tuple(uncertainty_codes),
            source_failure_impact=source_failure_impact,
            source_failure_choice=source_failure_choice,
            source_rule_id=source_rule_id,
            evidence_refs=tuple(evidence_refs),
            evidence_fingerprint=evidence_fingerprint,
        )
    except HKEXEffectiveStateError:
        raise
    except Exception as error:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT) from error


def _source_neutral_condition_snapshot(value: object) -> HKEXConditionFact:
    """Rebuild one exact condition fact before it reaches request validation."""
    if type(value) is not HKEXConditionFact:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    try:
        condition_id = value.condition_id
        registered_source_id = value.registered_source_id
        state = value.state
        evidence_refs = value.evidence_refs
        _source_neutral_exact_texts(condition_id, registered_source_id)
        _source_neutral_exact_enums(state, HKEXConditionState)
        _source_neutral_require(condition=type(evidence_refs) is tuple)
        _source_neutral_exact_text_tuple(evidence_refs)
        return HKEXConditionFact(
            condition_id=condition_id,
            registered_source_id=registered_source_id,
            state=state,
            evidence_refs=tuple(evidence_refs),
        )
    except HKEXEffectiveStateError:
        raise
    except Exception as error:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT) from error


def _source_neutral_contract_error() -> HKEXEffectiveStateError:
    """Return one ordinary malformed-source-neutral-input rejection."""
    return HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)


def _source_neutral_require(*, condition: bool) -> None:
    """Reject one missing exact source-neutral primitive before reconstruction."""
    if not condition:
        raise _source_neutral_contract_error()


def _source_neutral_exact_texts(*values: object) -> None:
    """Require exact primitive text before any validation can compare or hash it."""
    if any(type(value) is not str for value in values):
        raise _source_neutral_contract_error()


def _source_neutral_exact_optional_text(value: object) -> None:
    """Require an exact primitive optional text value."""
    if value is not None and type(value) is not str:
        raise _source_neutral_contract_error()


def _source_neutral_exact_text_tuple(values: tuple[object, ...]) -> None:
    """Require each influential tuple leaf to be exact text before set operations."""
    _source_neutral_exact_texts(*values)


def _source_neutral_exact_enums[E: StrEnum](
    value: object,
    expected: type[E],
    *remaining: object,
) -> None:
    """Require exact enums from alternating value/type pairs without equality checks."""
    pairs = (value, expected, *remaining)
    if len(pairs) % 2:
        raise _source_neutral_contract_error()
    for index in range(0, len(pairs), 2):
        candidate = pairs[index]
        enum_type = pairs[index + 1]
        if not isinstance(enum_type, type) or type(candidate) is not enum_type:
            raise _source_neutral_contract_error()


def _source_neutral_exact_optional_enum[E: StrEnum](value: object, expected: type[E]) -> None:
    """Require an exact enum when an optional enum is present."""
    if value is not None and type(value) is not expected:
        raise _source_neutral_contract_error()


def _source_neutral_exact_enum_tuple[E: StrEnum](
    values: tuple[object, ...], expected: type[E]
) -> None:
    """Require exact enum tuple leaves before the regular validator deduplicates them."""
    for value in values:
        if type(value) is not expected:
            raise _source_neutral_contract_error()


def _source_neutral_prior_snapshot(
    prior: object,
) -> tuple[str, str, HKEXBranchState, str] | None:
    """Copy only exact primitive prior facts before they affect a projection."""
    if prior is None:
        return None
    if type(prior) is not HKEXSourceNeutralPriorBranchState:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.PRIOR)
    try:
        component_id = prior.component_id
        branch_id = prior.branch_id
        state = prior.state
        fingerprint = prior.decision_fingerprint
    except (AttributeError, TypeError, ValueError) as error:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.PRIOR) from error
    if (
        type(component_id) is not str
        or not component_id
        or component_id.strip() != component_id
        or type(branch_id) is not str
        or not branch_id
        or branch_id.strip() != branch_id
        or type(state) is not HKEXBranchState
        or type(fingerprint) is not str
        or fullmatch(_FINGERPRINT_PATTERN, fingerprint) is None
    ):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.PRIOR)
    return component_id, branch_id, state, fingerprint


def _source_neutral_projection_state(
    disposition: HKEXMaterialDisposition,
) -> Literal["CURRENT", "WAITING_ROOM", "HISTORY", "QUARANTINE"]:
    """Map the established kernel disposition without adding legal interpretation."""
    if disposition is HKEXMaterialDisposition.SEARCHABLE_CURRENT_RULE_COMPONENT:
        return "CURRENT"
    if disposition is HKEXMaterialDisposition.REGULATORY_WAITING_ROOM:
        return "WAITING_ROOM"
    if disposition is HKEXMaterialDisposition.HISTORICAL:
        return "HISTORY"
    if disposition is HKEXMaterialDisposition.QUARANTINE:
        return "QUARANTINE"
    raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)


def _source_neutral_projection_authority_snapshot(
    authority: object,
) -> tuple[
    HKEXEffectiveStateRequest,
    tuple[str, str, HKEXBranchState, str] | None,
    HKEXEffectiveStateDecision,
]:
    """Replay retained authority and reject any non-derived decision successor."""
    if type(authority) is not _SourceNeutralProjectionAuthority:
        raise _source_neutral_contract_error()
    try:
        request = authority.request
        prior = authority.prior
        decision = authority.decision
    except Exception as error:
        raise _source_neutral_contract_error() from error
    request_snapshot = _source_neutral_request_snapshot(request)
    prior_snapshot = _source_neutral_prior_tuple_snapshot(prior)
    expected = decide_hkex_effective_state(request_snapshot)
    if not _source_neutral_decision_matches(decision, expected):
        raise _source_neutral_contract_error()
    return request_snapshot, prior_snapshot, expected


def _source_neutral_prior_tuple_snapshot(
    value: object,
) -> tuple[str, str, HKEXBranchState, str] | None:
    """Revalidate a retained prior primitive tuple without equality or hashing."""
    if value is None:
        return None
    if not _is_object_tuple(value) or len(value) != _PRIOR_TUPLE_LENGTH:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.PRIOR)
    component_id, branch_id, state, fingerprint = value
    if (
        type(component_id) is not str
        or type(branch_id) is not str
        or type(state) is not HKEXBranchState
        or type(fingerprint) is not str
        or not component_id
        or component_id.strip() != component_id
        or not branch_id
        or branch_id.strip() != branch_id
        or fullmatch(_FINGERPRINT_PATTERN, fingerprint) is None
    ):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.PRIOR)
    return component_id, branch_id, state, fingerprint


def _source_neutral_decision_matches(
    supplied: object,
    expected: HKEXEffectiveStateDecision,
) -> bool:
    """Compare only exact primitive decision fields after full replay."""
    if type(supplied) is not HKEXEffectiveStateDecision:
        return False
    try:
        supplied_values = (
            supplied.decision_id,
            supplied.branch_id,
            supplied.component_id,
            supplied.scope_id,
            supplied.legal_location_id,
            supplied.cutoff,
            supplied.state,
            supplied.disposition,
            supplied.processing_outcome,
            supplied.reason,
            supplied.source_rule_id,
            supplied.evidence_fingerprint,
            supplied.source_failure_choice,
            supplied.current_product_reconciled,
            supplied.search_record_authorized,
            supplied.serving_ready,
        )
    except AttributeError:
        return False
    expected_values = (
        expected.decision_id,
        expected.branch_id,
        expected.component_id,
        expected.scope_id,
        expected.legal_location_id,
        expected.cutoff,
        expected.state,
        expected.disposition,
        expected.processing_outcome,
        expected.reason,
        expected.source_rule_id,
        expected.evidence_fingerprint,
        expected.source_failure_choice,
        expected.current_product_reconciled,
        expected.search_record_authorized,
        expected.serving_ready,
    )
    expected_types = (
        str,
        str,
        str,
        str,
        str,
        str,
        HKEXBranchState,
        HKEXMaterialDisposition,
        HKEXProcessingOutcome,
        HKEXEffectiveStateReason,
        str,
        str,
        HKEXServingChoice,
        bool,
        bool,
        bool,
    )
    return all(
        type(supplied_value) is expected_type and supplied_value == expected_value
        for supplied_value, expected_value, expected_type in zip(
            supplied_values,
            expected_values,
            expected_types,
            strict=True,
        )
    )


def _source_neutral_projection_values(
    request: HKEXEffectiveStateRequest,
    prior: tuple[str, str, HKEXBranchState, str] | None,
    decision: HKEXEffectiveStateDecision,
) -> _SourceNeutralProjectionValues:
    """Derive every projection field from a replayed decision and prior snapshot."""
    if prior is not None and (prior[0] != decision.component_id or prior[1] != decision.branch_id):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.PRIOR)
    state = _source_neutral_projection_state(decision.disposition)
    keep_prior_current = (
        state == "QUARANTINE"
        and prior is not None
        and prior[2]
        in {
            HKEXBranchState.CURRENT,
            HKEXBranchState.TRANSITIONAL_CURRENT,
        }
    )
    return _SourceNeutralProjectionValues(
        decision.component_id,
        decision.branch_id,
        state,
        keep_prior_current,
        decision.reason.value,
        request.evidence_refs,
    )


def _issue_source_neutral_projection(
    authority: object,
) -> HKEXSourceNeutralStateProjection:
    """Issue only the result re-derived from one retained validated authority."""
    return _materialize_source_neutral_projection(authority)


def _materialize_source_neutral_projection(
    authority: object,
) -> HKEXSourceNeutralStateProjection:
    """Materialize only values freshly derived from replayed retained authority."""
    request, prior, decision = _source_neutral_projection_authority_snapshot(authority)
    values = _source_neutral_projection_values(request, prior, decision)
    projection = object.__new__(HKEXSourceNeutralStateProjection)
    object.__setattr__(projection, "component_id", values.component_id)
    object.__setattr__(projection, "branch_id", values.branch_id)
    object.__setattr__(projection, "state", values.state)
    object.__setattr__(projection, "keep_prior_current", values.keep_prior_current)
    object.__setattr__(projection, "reason_code", values.reason_code)
    object.__setattr__(projection, "evidence_refs", values.evidence_refs)
    snapshot = _source_neutral_projection_bytes(projection)
    retained_authority = _SourceNeutralProjectionAuthority(request, prior, decision)
    identity = id(projection)

    def forget(
        reference: ReferenceType[HKEXSourceNeutralStateProjection], identity: int = identity
    ) -> None:
        issued = _SOURCE_NEUTRAL_PROJECTION_ISSUANCE.get(identity)
        if issued is not None and issued[0] is reference:
            _SOURCE_NEUTRAL_PROJECTION_ISSUANCE.pop(identity, None)

    _SOURCE_NEUTRAL_PROJECTION_ISSUANCE[identity] = (
        ref(projection, forget),
        snapshot,
        retained_authority,
    )
    projection.__post_init__()
    return projection


def _assert_source_neutral_projection_issued(
    projection: object,
) -> None:
    """Reject direct, replaced, copied, or mutated projection-shaped values."""
    if type(projection) is not HKEXSourceNeutralStateProjection:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    snapshot = _source_neutral_projection_bytes(projection)
    issued = _SOURCE_NEUTRAL_PROJECTION_ISSUANCE.get(id(projection))
    if issued is None:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    reference, issued_snapshot, retained_authority = issued
    if reference() is not projection or issued_snapshot != snapshot:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    request, prior, decision = _source_neutral_projection_authority_snapshot(retained_authority)
    expected_values = _source_neutral_projection_values(request, prior, decision)
    expected_snapshot = _source_neutral_projection_values_bytes(expected_values)
    if expected_snapshot != snapshot or expected_snapshot != issued_snapshot:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)


def _source_neutral_projection_bytes(projection: object) -> bytes:
    """Validate and canonically bind every public projection primitive."""
    if type(projection) is not HKEXSourceNeutralStateProjection:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    try:
        component_id = projection.component_id
        branch_id = projection.branch_id
        state = projection.state
        keep_prior_current = projection.keep_prior_current
        reason_code = projection.reason_code
        evidence_refs = projection.evidence_refs
    except Exception as error:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT) from error
    return _source_neutral_projection_primitive_bytes(
        (component_id, branch_id, state, keep_prior_current, reason_code, evidence_refs)
    )


def _source_neutral_projection_values_bytes(values: _SourceNeutralProjectionValues) -> bytes:
    """Encode freshly derived output values for replay-equality verification."""
    return _source_neutral_projection_primitive_bytes(
        (
            values.component_id,
            values.branch_id,
            values.state,
            values.keep_prior_current,
            values.reason_code,
            values.evidence_refs,
        )
    )


def _source_neutral_projection_primitive_bytes(
    values: _SourceNeutralProjectionPrimitiveValues,
) -> bytes:
    """Validate and canonically encode one complete source-neutral projection."""
    component_id, branch_id, state, keep_prior_current, reason_code, evidence_refs = values
    if (
        type(component_id) is not str
        or not component_id
        or component_id.strip() != component_id
        or type(branch_id) is not str
        or not branch_id
        or branch_id.strip() != branch_id
        or type(state) is not str
        or state not in {"CURRENT", "WAITING_ROOM", "HISTORY", "QUARANTINE"}
        or type(keep_prior_current) is not bool
        or type(reason_code) is not str
        or reason_code not in {item.value for item in HKEXEffectiveStateReason}
    ):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    if keep_prior_current and state != "QUARANTINE":
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    evidence_refs_snapshot = _source_neutral_projection_evidence_refs(evidence_refs)
    return json.dumps(
        {
            "branch_id": branch_id,
            "component_id": component_id,
            "evidence_refs": evidence_refs_snapshot,
            "keep_prior_current": keep_prior_current,
            "reason_code": reason_code,
            "state": state,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _source_neutral_projection_evidence_refs(value: object) -> tuple[str, ...]:
    """Copy exact projection evidence before canonical equality can rely on it."""
    if not _is_object_tuple(value):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    snapshot: list[str] = []
    for item in value:
        if type(item) is not str:
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
        snapshot.append(item)
    try:
        return _strings(tuple(snapshot))
    except HKEXEffectiveStateError as error:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT) from error


def hkex_effective_state_request_from_document(
    document: object,
) -> HKEXEffectiveStateRequest:
    """Strictly decode one JSON-compatible request without repairing drift."""
    value = _document(document)
    _exact_keys(
        value,
        {
            "decision_id",
            "branch_id",
            "component_id",
            "scope_id",
            "legal_location_id",
            "cutoff",
            "update_part_id",
            "update_source_ranges",
            "current_product_ranges",
            "basis",
            "finality",
            "effective_at",
            "condition_operator",
            "conditions",
            "transition_state",
            "applicability_context",
            "retirement_evidence",
            "predecessor_branch_id",
            "successor_branch_ids",
            "current_product_reconciliation",
            "uncertainty_codes",
            "source_failure_impact",
            "source_failure_choice",
            "source_rule_id",
            "evidence_refs",
            "evidence_fingerprint",
        },
    )
    return HKEXEffectiveStateRequest(
        decision_id=_json_text(value["decision_id"]),
        branch_id=_json_text(value["branch_id"]),
        component_id=_json_text(value["component_id"]),
        scope_id=_json_text(value["scope_id"]),
        legal_location_id=_json_text(value["legal_location_id"]),
        cutoff=_json_text(value["cutoff"]),
        update_part_id=_json_text(value["update_part_id"]),
        update_source_ranges=_json_strings(value["update_source_ranges"]),
        current_product_ranges=_json_strings(value["current_product_ranges"]),
        basis=_json_enum(value["basis"], HKEXBranchBasis),
        finality=_json_enum(value["finality"], HKEXFinality),
        effective_at=_json_nullable_text(value["effective_at"]),
        condition_operator=_json_nullable_enum(value["condition_operator"], HKEXConditionOperator),
        conditions=_json_conditions(value["conditions"]),
        transition_state=_json_enum(value["transition_state"], HKEXTransitionState),
        applicability_context=_json_nullable_text(value["applicability_context"]),
        retirement_evidence=_json_enum(value["retirement_evidence"], HKEXRetirementEvidence),
        predecessor_branch_id=_json_nullable_text(value["predecessor_branch_id"]),
        successor_branch_ids=_json_strings(value["successor_branch_ids"], empty=True),
        current_product_reconciliation=_json_enum(
            value["current_product_reconciliation"],
            HKEXCurrentProductReconciliation,
        ),
        uncertainty_codes=_json_enum_tuple(value["uncertainty_codes"], HKEXStateUncertainty),
        source_failure_impact=_json_enum(value["source_failure_impact"], HKEXSourceFailureImpact),
        source_failure_choice=_json_enum(value["source_failure_choice"], HKEXServingChoice),
        source_rule_id=_json_text(value["source_rule_id"]),
        evidence_refs=_json_strings(value["evidence_refs"]),
        evidence_fingerprint=_json_text(value["evidence_fingerprint"]),
    )


def decide_hkex_effective_state(
    request: HKEXEffectiveStateRequest,
) -> HKEXEffectiveStateDecision:
    """Apply ADR 0071 without inventing dates, triggers, continuity, or text."""
    if type(request) is not HKEXEffectiveStateRequest:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    result = _preliminary_result(request)
    if result is None:
        result = _retirement_result(request)
    if result is None:
        result = _activation_result(request)
    if result is None:
        result = _current_result(request)
    return _decision(request, *result)


def _preliminary_result(
    request: HKEXEffectiveStateRequest,
) -> tuple[HKEXBranchState, HKEXEffectiveStateReason] | None:
    if request.source_failure_impact is HKEXSourceFailureImpact.COULD_CHANGE_CURRENT:
        return (
            HKEXBranchState.UNKNOWN,
            HKEXEffectiveStateReason.SOURCE_FAILURE_COULD_CHANGE_CURRENT,
        )
    if request.uncertainty_codes:
        return (
            HKEXBranchState.UNKNOWN,
            HKEXEffectiveStateReason.UNRESOLVED_LEGAL_STATE_FACT,
        )
    if request.finality not in {
        HKEXFinality.FINAL_PUBLICATION_APPROVAL_INFERRED,
        HKEXFinality.FINAL_DIRECT_APPROVAL_PROVED,
    }:
        return (
            HKEXBranchState.UNKNOWN,
            HKEXEffectiveStateReason.FINAL_PUBLICATION_NOT_PROVED,
        )
    return None


def _retirement_result(
    request: HKEXEffectiveStateRequest,
) -> tuple[HKEXBranchState, HKEXEffectiveStateReason] | None:
    retirement = request.retirement_evidence
    if retirement is HKEXRetirementEvidence.COMPLETE_SUCCESSOR:
        return (
            HKEXBranchState.SUPERSEDED,
            HKEXEffectiveStateReason.COMPLETE_SUCCESSOR_PROVED,
        )
    if retirement is HKEXRetirementEvidence.OFFICIAL_WITHDRAWAL_NO_SUCCESSOR:
        return (
            HKEXBranchState.WITHDRAWN,
            HKEXEffectiveStateReason.WITHDRAWAL_WITHOUT_SUCCESSOR_PROVED,
        )
    if retirement in {
        HKEXRetirementEvidence.DISAPPEARANCE_ONLY,
        HKEXRetirementEvidence.CONFLICTING,
    }:
        return (
            HKEXBranchState.UNKNOWN,
            HKEXEffectiveStateReason.RETIREMENT_EVIDENCE_INSUFFICIENT,
        )
    if request.transition_state is HKEXTransitionState.PROVED_ENDED:
        return (
            HKEXBranchState.UNKNOWN,
            HKEXEffectiveStateReason.TRANSITION_END_UNRESOLVED,
        )
    return None


def _activation_result(
    request: HKEXEffectiveStateRequest,
) -> tuple[HKEXBranchState, HKEXEffectiveStateReason] | None:
    if request.basis is HKEXBranchBasis.FIXED_DATE:
        if _cutoff(request.cutoff) < _effective_point(request.effective_at):
            return (
                HKEXBranchState.FUTURE_FIXED_DATE,
                HKEXEffectiveStateReason.FUTURE_FIXED_DATE_PENDING,
            )
    elif request.basis is HKEXBranchBasis.CONDITIONAL:
        condition_result = _condition_result(request)
        if condition_result is False:
            return (
                HKEXBranchState.FUTURE_CONDITIONAL,
                HKEXEffectiveStateReason.FUTURE_CONDITION_PROVED_UNMET,
            )
        if condition_result is None:
            return (
                HKEXBranchState.UNKNOWN,
                HKEXEffectiveStateReason.CONDITION_EVIDENCE_UNRESOLVED,
            )
    return None


def _current_result(
    request: HKEXEffectiveStateRequest,
) -> tuple[HKEXBranchState, HKEXEffectiveStateReason]:
    reconciliation = request.current_product_reconciliation
    if reconciliation is HKEXCurrentProductReconciliation.CONFLICT:
        return (
            HKEXBranchState.UNKNOWN,
            HKEXEffectiveStateReason.CURRENT_PRODUCT_CONFLICT,
        )
    if reconciliation is not HKEXCurrentProductReconciliation.MATCH:
        return (
            HKEXBranchState.UNKNOWN,
            HKEXEffectiveStateReason.CURRENT_PRODUCT_EVIDENCE_INCOMPLETE,
        )

    transitional = (
        request.retirement_evidence is HKEXRetirementEvidence.PARTIAL_SUCCESSOR
        or request.transition_state is HKEXTransitionState.MATERIALLY_LIMITED_CURRENT
    )
    if transitional:
        return (
            HKEXBranchState.TRANSITIONAL_CURRENT,
            HKEXEffectiveStateReason.TRANSITIONAL_CURRENT_PRODUCT_MATCHED,
        )
    return (
        HKEXBranchState.CURRENT,
        HKEXEffectiveStateReason.CURRENT_PRODUCT_MATCHED,
    )


def _condition_result(request: HKEXEffectiveStateRequest) -> bool | None:
    states = tuple(condition.state for condition in request.conditions)
    if request.condition_operator is HKEXConditionOperator.ALL_OF:
        if all(state is HKEXConditionState.OCCURRED for state in states):
            return True
        if HKEXConditionState.NOT_OCCURRED_FRESH in states:
            return False
        return None
    if request.condition_operator is HKEXConditionOperator.ANY_OF:
        if HKEXConditionState.OCCURRED in states:
            return True
        if all(state is HKEXConditionState.NOT_OCCURRED_FRESH for state in states):
            return False
        return None
    raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)


def _decision(
    request: HKEXEffectiveStateRequest,
    state: HKEXBranchState,
    reason: HKEXEffectiveStateReason,
) -> HKEXEffectiveStateDecision:
    if state in {HKEXBranchState.CURRENT, HKEXBranchState.TRANSITIONAL_CURRENT}:
        disposition = HKEXMaterialDisposition.SEARCHABLE_CURRENT_RULE_COMPONENT
        outcome = HKEXProcessingOutcome.PASS
    elif state in {
        HKEXBranchState.FUTURE_FIXED_DATE,
        HKEXBranchState.FUTURE_CONDITIONAL,
    }:
        disposition = HKEXMaterialDisposition.REGULATORY_WAITING_ROOM
        outcome = HKEXProcessingOutcome.PASS
    elif state in {HKEXBranchState.SUPERSEDED, HKEXBranchState.WITHDRAWN}:
        disposition = HKEXMaterialDisposition.HISTORICAL
        outcome = HKEXProcessingOutcome.PASS
    else:
        disposition = HKEXMaterialDisposition.QUARANTINE
        outcome = HKEXProcessingOutcome.QUARANTINE
    return HKEXEffectiveStateDecision(
        decision_id=request.decision_id,
        branch_id=request.branch_id,
        component_id=request.component_id,
        scope_id=request.scope_id,
        legal_location_id=request.legal_location_id,
        cutoff=request.cutoff,
        state=state,
        disposition=disposition,
        processing_outcome=outcome,
        reason=reason,
        source_rule_id=request.source_rule_id,
        evidence_fingerprint=request.evidence_fingerprint,
        source_failure_choice=request.source_failure_choice,
        current_product_reconciled=(
            request.current_product_reconciliation is HKEXCurrentProductReconciliation.MATCH
            and state in {HKEXBranchState.CURRENT, HKEXBranchState.TRANSITIONAL_CURRENT}
        ),
    )


def _validate_request(request: HKEXEffectiveStateRequest) -> None:
    _validate_request_core(request)
    _validate_basis(request)
    _validate_relationships(request)
    _validate_source_failure(request)


def _validate_request_core(request: HKEXEffectiveStateRequest) -> None:
    for value in (
        request.decision_id,
        request.branch_id,
        request.component_id,
        request.legal_location_id,
        request.update_part_id,
        request.source_rule_id,
    ):
        _text(value)
    if request.scope_id not in HKEX_SCOPE_IDS:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    _cutoff(request.cutoff)
    _strings(request.update_source_ranges)
    _strings(request.current_product_ranges)
    _strings(request.evidence_refs)
    if fullmatch(_FINGERPRINT_PATTERN, request.evidence_fingerprint) is None:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.EVIDENCE)
    _enum(request.basis, HKEXBranchBasis)
    _enum(request.finality, HKEXFinality)
    _enum(request.transition_state, HKEXTransitionState)
    _enum(request.retirement_evidence, HKEXRetirementEvidence)
    _enum(request.current_product_reconciliation, HKEXCurrentProductReconciliation)
    _enum(request.source_failure_impact, HKEXSourceFailureImpact)
    _enum(request.source_failure_choice, HKEXServingChoice)
    _unique_enums(request.uncertainty_codes, HKEXStateUncertainty)


def _validate_basis(request: HKEXEffectiveStateRequest) -> None:
    if request.basis is HKEXBranchBasis.FIXED_DATE:
        _effective_point(request.effective_at)
        if request.condition_operator is not None or request.conditions:
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    elif request.basis is HKEXBranchBasis.CONDITIONAL:
        if request.effective_at is not None:
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
        _enum(request.condition_operator, HKEXConditionOperator)
        if type(request.conditions) is not tuple or not request.conditions:
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
        if len({condition.condition_id for condition in request.conditions}) != len(
            request.conditions
        ):
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    elif (
        request.effective_at is not None
        or request.condition_operator is not None
        or request.conditions
    ):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)

    limited = (
        request.transition_state is HKEXTransitionState.MATERIALLY_LIMITED_CURRENT
        or request.retirement_evidence is HKEXRetirementEvidence.PARTIAL_SUCCESSOR
    )
    if limited != (request.applicability_context is not None):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    if request.applicability_context is not None:
        _text(request.applicability_context)


def _validate_relationships(request: HKEXEffectiveStateRequest) -> None:
    if request.predecessor_branch_id is not None:
        _text(request.predecessor_branch_id)
        if request.predecessor_branch_id == request.branch_id:
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    if type(request.successor_branch_ids) is not tuple or len(request.successor_branch_ids) != len(
        set(request.successor_branch_ids)
    ):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    for successor in request.successor_branch_ids:
        _text(successor)
        if successor == request.branch_id:
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    successor_required = request.retirement_evidence in {
        HKEXRetirementEvidence.COMPLETE_SUCCESSOR,
        HKEXRetirementEvidence.PARTIAL_SUCCESSOR,
    }
    if successor_required != bool(request.successor_branch_ids):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    if (
        request.transition_state is HKEXTransitionState.PROVED_ENDED
        and request.retirement_evidence
        not in {
            HKEXRetirementEvidence.COMPLETE_SUCCESSOR,
            HKEXRetirementEvidence.OFFICIAL_WITHDRAWAL_NO_SUCCESSOR,
            HKEXRetirementEvidence.NONE,
        }
    ):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)


def _validate_source_failure(request: HKEXEffectiveStateRequest) -> None:
    failed = request.source_failure_impact is HKEXSourceFailureImpact.COULD_CHANGE_CURRENT
    if failed != (request.source_failure_choice is not HKEXServingChoice.NONE):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)


def _cutoff(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.TEMPORAL) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.TEMPORAL)
    return parsed.astimezone(_HONG_KONG)


def _effective_point(value: str | None) -> datetime:
    if value is None:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.TEMPORAL)
    try:
        if len(value) == _DATE_LENGTH:
            return datetime.combine(date.fromisoformat(value), time.min, tzinfo=_HONG_KONG)
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.TEMPORAL) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.TEMPORAL)
    return parsed.astimezone(_HONG_KONG)


def _enum[E: StrEnum](value: object, expected: type[E]) -> E:
    if type(value) is not expected:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    return value


def _unique_enums[E: StrEnum](values: tuple[E, ...], expected: type[E]) -> tuple[E, ...]:
    if type(values) is not tuple or len(values) != len(set(values)):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    for value in values:
        _enum(value, expected)
    return values


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    return value


def _strings(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple or not values or len(values) != len(set(values)):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.EVIDENCE)
    for value in values:
        _text(value)
    return values


def _document(value: object) -> dict[str, object]:
    if not _is_object_dict(value):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    result: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
        result[key] = item
    return result


def _exact_keys(value: dict[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)


def _json_text(value: object) -> str:
    return _text(value)


def _json_nullable_text(value: object) -> str | None:
    if value is None:
        return None
    return _json_text(value)


def _json_array(value: object) -> tuple[object, ...]:
    if not _is_object_list(value):
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT)
    return tuple(value)


def _is_object_dict(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return isinstance(value, list)


def _is_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _json_strings(value: object, *, empty: bool = False) -> tuple[str, ...]:
    result = tuple(_json_text(item) for item in _json_array(value))
    if not empty and not result:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.EVIDENCE)
    return result


def _json_enum[E: StrEnum](value: object, enum_type: type[E]) -> E:
    text = _json_text(value)
    try:
        return enum_type(text)
    except ValueError as error:
        raise HKEXEffectiveStateError(HKEXEffectiveStateErrorCode.CONTRACT) from error


def _json_nullable_enum[E: StrEnum](value: object, enum_type: type[E]) -> E | None:
    if value is None:
        return None
    return _json_enum(value, enum_type)


def _json_enum_tuple[E: StrEnum](value: object, enum_type: type[E]) -> tuple[E, ...]:
    return tuple(_json_enum(item, enum_type) for item in _json_array(value))


def _json_conditions(value: object) -> tuple[HKEXConditionFact, ...]:
    result: list[HKEXConditionFact] = []
    for raw in _json_array(value):
        condition = _document(raw)
        _exact_keys(
            condition,
            {"condition_id", "registered_source_id", "state", "evidence_refs"},
        )
        result.append(
            HKEXConditionFact(
                condition_id=_json_text(condition["condition_id"]),
                registered_source_id=_json_text(condition["registered_source_id"]),
                state=_json_enum(condition["state"], HKEXConditionState),
                evidence_refs=_json_strings(condition["evidence_refs"]),
            )
        )
    return tuple(result)
