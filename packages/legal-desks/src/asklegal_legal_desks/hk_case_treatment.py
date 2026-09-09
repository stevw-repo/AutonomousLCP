# ruff: noqa: BLE001, PLR0913, PLR0917
"""Deterministic admission of evidence-bound Hong Kong later-treatment edges.

Whole-judgment discovery is deliberately not legal effect.  This module accepts
only an exact, complete discovery candidate plus a matching admitted Legal Desk
decision.  It never reads a source, invokes a model, or allocates a record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from hashlib import sha256
from typing import SupportsIndex
from weakref import ReferenceType, WeakKeyDictionary, ref

from .hk_case_proposition import HKCasePropositionAdmissionResult
from .hk_case_treatment_discovery import (
    HKCaseTreatmentDiscoveryEvaluationRequest,
    HKCaseTreatmentDiscoveryEvaluationResult,
    HKCaseTreatmentDiscoveryOutcome,
    evaluate_hk_case_treatment_discovery,
)

_CLASSIFICATION_FACTORY_REQUIRED = "HK_CASE_TREATMENT_CLASSIFICATION_FACTORY_REQUIRED"
_CLASSIFICATION_INVALID = "HK_CASE_TREATMENT_CLASSIFICATION_INVALID"
_CLASSIFICATION_NOT_TRANSFERABLE = "HK_CASE_TREATMENT_CLASSIFICATION_NOT_TRANSFERABLE"
_EDGE_INVALID = "HK_CASE_TREATMENT_EDGE_INVALID"


class HKCaseTreatment(StrEnum):
    """The closed treatment classes proposed and decided by the Legal Desk."""

    APPLIED = "APPLIED"
    FOLLOWED = "FOLLOWED"
    DISTINGUISHED = "DISTINGUISHED"
    DOUBTED = "DOUBTED"
    DISAPPROVED = "DISAPPROVED"
    OVERRULED = "OVERRULED"


class HKCaseTreatmentAuthorityConsequence(StrEnum):
    """The exact Legal-Desk consequence; a treatment label alone is insufficient."""

    AUTHORITY_NOTE = "AUTHORITY_NOTE"
    NO_CHANGE = "NO_CHANGE"
    RETIRE = "RETIRE"


class HKCaseTreatmentOpinionAuthority(StrEnum):
    """Whether the candidate passage belongs to an operative judicial opinion."""

    DISSENT = "DISSENT"
    NON_OPERATIVE = "NON_OPERATIVE"
    OPERATIVE = "OPERATIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentCandidate:
    """One complete, source-neutral candidate after whole-judgment discovery."""

    candidate_id: str
    later_proposition_id: str
    earlier_proposition_id: str
    opinion_id: str
    opinion_authority: HKCaseTreatmentOpinionAuthority
    support_paragraph_refs: tuple[str, ...]
    effective_date: str
    whole_judgment_evidence_complete: bool
    candidate_evidence_complete: bool
    bare_citation: bool


@dataclass(frozen=True, slots=True)
class HKCaseTreatmentDecision:
    """One admitted Legal-Desk decision bound to exactly one candidate."""

    decision_id: str
    candidate_id: str
    admitted: bool
    treatment: HKCaseTreatment
    authority_consequence: HKCaseTreatmentAuthorityConsequence
    evidence_complete: bool


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class HKCaseTreatmentEdge:
    """One settled directional relationship from a later to an earlier proposition."""

    later_proposition_id: str
    earlier_proposition_id: str
    treatment: HKCaseTreatment
    opinion_id: str
    support_paragraph_refs: tuple[str, ...]
    effective_date: str
    authority_consequence: HKCaseTreatmentAuthorityConsequence
    decision_id: str

    @property
    def relationship_id(self) -> str:
        """Return the canonical relationship identity without trusting a caller ID."""
        return "trt_" + self.relationship_fingerprint.removeprefix("sha256:")[:32]

    @property
    def relationship_fingerprint(self) -> str:
        """Fingerprint the complete directional relationship independently of decision IDs."""
        try:
            return _raw_fingerprint(_canonical_bytes(_edge_relationship_document(self)))
        except Exception:
            raise ValueError(_EDGE_INVALID) from None


_ISSUED_EDGES: WeakKeyDictionary[HKCaseTreatmentEdge, bytes] = WeakKeyDictionary()


class HKCaseTreatmentClassificationError(ValueError):
    """One closed ordinary classification-input failure."""


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class _HKCaseTreatmentClassificationIssuance:
    """Opaque process-local classification authority."""

    projection: bytes

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[object, ...]:
        """Require restart recovery to rerun classification from upstream facts."""
        del protocol
        raise TypeError(_CLASSIFICATION_NOT_TRANSFERABLE)


@dataclass(frozen=True, slots=True)
class _HKCaseTreatmentClassificationFacts:
    """Registry-only facts bound to one exact factory result."""

    projection: bytes
    result_reference: ReferenceType[HKCaseTreatmentClassification] | None


_ISSUED_CLASSIFICATIONS: WeakKeyDictionary[
    _HKCaseTreatmentClassificationIssuance, _HKCaseTreatmentClassificationFacts
] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKCaseTreatmentClassification:
    """The complete edge and Quarantine outcome for one candidate/decision batch."""

    edges: tuple[HKCaseTreatmentEdge, ...]
    quarantined_candidate_ids: tuple[str, ...]
    issuance: _HKCaseTreatmentClassificationIssuance | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Replay exact process-local issuance and every public output primitive."""
        _issued_classification_facts(self)

    def __copy__(self) -> HKCaseTreatmentClassification:
        """Classification authority cannot be transferred by shallow copy."""
        raise TypeError(_CLASSIFICATION_NOT_TRANSFERABLE)

    def __deepcopy__(self, memo: dict[int, object]) -> HKCaseTreatmentClassification:
        """Classification authority cannot be transferred by deep copy."""
        del memo
        raise TypeError(_CLASSIFICATION_NOT_TRANSFERABLE)

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[object, ...]:
        """Classification authority cannot cross serialization or process restart."""
        del protocol
        raise TypeError(_CLASSIFICATION_NOT_TRANSFERABLE)


def classify_hk_case_treatment(
    candidates: tuple[HKCaseTreatmentCandidate, ...],
    decisions: tuple[HKCaseTreatmentDecision, ...],
    discovery_request: HKCaseTreatmentDiscoveryEvaluationRequest | None = None,
    discovery_result: HKCaseTreatmentDiscoveryEvaluationResult | None = None,
    later_admission: HKCasePropositionAdmissionResult | None = None,
    earlier_admission: HKCasePropositionAdmissionResult | None = None,
) -> HKCaseTreatmentClassification:
    """Create edges only for exact complete candidates and matching admitted decisions.

    A bare citation, an unaccepted proposal, a dissent, conflicting decision, or
    malformed evidence is deliberately Quarantined rather than treated as a
    harmless no-treatment result.
    """
    try:
        return _classify_hk_case_treatment(
            candidates,
            decisions,
            discovery_request,
            discovery_result,
            later_admission,
            earlier_admission,
        )
    except HKCaseTreatmentClassificationError:
        raise
    except Exception:
        raise HKCaseTreatmentClassificationError(_CLASSIFICATION_INVALID) from None


def _classify_hk_case_treatment(
    candidates: tuple[HKCaseTreatmentCandidate, ...],
    decisions: tuple[HKCaseTreatmentDecision, ...],
    discovery_request: HKCaseTreatmentDiscoveryEvaluationRequest | None,
    discovery_result: HKCaseTreatmentDiscoveryEvaluationResult | None,
    later_admission: HKCasePropositionAdmissionResult | None,
    earlier_admission: HKCasePropositionAdmissionResult | None,
) -> HKCaseTreatmentClassification:
    """Validate exact outer and identity shapes before hashing or field use."""
    candidate_ids = _validated_candidate_ids(candidates)
    validated_candidates = candidates
    decision_ids = _validated_decision_ids(decisions)
    validated_decisions = decisions
    duplicate_candidates = _duplicates(candidate_ids)
    duplicate_decisions = _duplicates(decision_ids)
    decisions_by_candidate: dict[str, list[HKCaseTreatmentDecision]] = {}
    for decision in validated_decisions:
        decisions_by_candidate.setdefault(decision.candidate_id, []).append(decision)

    edges: list[HKCaseTreatmentEdge] = []
    quarantined: list[str] = []
    exact_upstream = _exact_upstream_replayed(
        discovery_request, discovery_result, later_admission, earlier_admission
    )
    for candidate in validated_candidates:
        matching = decisions_by_candidate.get(candidate.candidate_id, [])
        if (
            duplicate_candidates
            or duplicate_decisions
            or not exact_upstream
            or not is_hk_case_treatment_candidate_complete(candidate)
            or len(matching) != 1
            or not _decision_matches(candidate, matching[0])
        ):
            quarantined.append(candidate.candidate_id)
            continue
        decision = matching[0]
        # No executable Cases treatment Rulebook/Rule Trace exists in this
        # source-neutral slice.  Even exact upstream replay cannot turn caller
        # supplied Legal-Desk booleans into authority or retirement.
        quarantined.append(candidate.candidate_id)
    known_candidates = set(candidate_ids)
    quarantined.extend(
        decision.candidate_id
        for decision in validated_decisions
        if decision.candidate_id not in known_candidates
    )
    return _issue_classification(
        edges=tuple(edges),
        quarantined_candidate_ids=tuple(sorted(set(quarantined))),
    )


def is_hk_case_treatment_candidate_complete(candidate: HKCaseTreatmentCandidate) -> bool:
    """Check only deterministic candidate facts; semantic interpretation is already decided."""
    return (
        type(candidate) is HKCaseTreatmentCandidate
        and all(
            type(value) is str and bool(value)
            for value in (
                candidate.candidate_id,
                candidate.later_proposition_id,
                candidate.earlier_proposition_id,
                candidate.opinion_id,
            )
        )
        and candidate.later_proposition_id != candidate.earlier_proposition_id
        and type(candidate.opinion_authority) is HKCaseTreatmentOpinionAuthority
        and candidate.opinion_authority is HKCaseTreatmentOpinionAuthority.OPERATIVE
        and type(candidate.support_paragraph_refs) is tuple
        and bool(candidate.support_paragraph_refs)
        and all(type(item) is str and bool(item) for item in candidate.support_paragraph_refs)
        and len(set(candidate.support_paragraph_refs)) == len(candidate.support_paragraph_refs)
        and _parse_canonical_date(candidate.effective_date) is not None
        and type(candidate.whole_judgment_evidence_complete) is bool
        and candidate.whole_judgment_evidence_complete is True
        and type(candidate.candidate_evidence_complete) is bool
        and candidate.candidate_evidence_complete is True
        and type(candidate.bare_citation) is bool
        and candidate.bare_citation is False
    )


def _decision_matches(
    candidate: HKCaseTreatmentCandidate, decision: HKCaseTreatmentDecision
) -> bool:
    """Require one exact admitted decision rather than treating a proposal as legal effect."""
    return (
        type(decision) is HKCaseTreatmentDecision
        and type(decision.decision_id) is str
        and bool(decision.decision_id)
        and decision.candidate_id == candidate.candidate_id
        and type(decision.admitted) is bool
        and decision.admitted is True
        and type(decision.evidence_complete) is bool
        and decision.evidence_complete is True
        and type(decision.treatment) is HKCaseTreatment
        and type(decision.authority_consequence) is HKCaseTreatmentAuthorityConsequence
    )


def _exact_upstream_replayed(
    request: HKCaseTreatmentDiscoveryEvaluationRequest | None,
    result: HKCaseTreatmentDiscoveryEvaluationResult | None,
    later: HKCasePropositionAdmissionResult | None,
    earlier: HKCasePropositionAdmissionResult | None,
) -> bool:
    """Replay exact mature sources; absent treatment Rulebook authority remains closed."""
    try:
        if (
            type(request) is not HKCaseTreatmentDiscoveryEvaluationRequest
            or type(result) is not HKCaseTreatmentDiscoveryEvaluationResult
            or type(later) is not HKCasePropositionAdmissionResult
            or type(earlier) is not HKCasePropositionAdmissionResult
            or evaluate_hk_case_treatment_discovery(request) != result
            or result.outcome is not HKCaseTreatmentDiscoveryOutcome.PASS
        ):
            return False
        later.__post_init__()
        earlier.__post_init__()
    except Exception:
        return False
    return True


def is_hk_case_treatment_edge_issued(edge: HKCaseTreatmentEdge) -> bool:
    """Return whether this exact edge was produced by the private factory boundary."""
    if type(edge) is not HKCaseTreatmentEdge:
        return False
    try:
        projection = _ISSUED_EDGES.get(edge)
        return projection is not None and projection == _canonical_bytes(_edge_document(edge))
    except Exception:
        return False


def replay_hk_case_treatment_classification(
    classification: HKCaseTreatmentClassification,
) -> HKCaseTreatmentClassification:
    """Replay an exact live classification; restart recovery reruns its factory inputs."""
    if type(classification) is not HKCaseTreatmentClassification:
        raise HKCaseTreatmentClassificationError(_CLASSIFICATION_INVALID)
    try:
        classification.__post_init__()
    except Exception:
        raise HKCaseTreatmentClassificationError(_CLASSIFICATION_INVALID) from None
    return classification


def _validated_candidate_ids(
    candidates: tuple[HKCaseTreatmentCandidate, ...],
) -> tuple[str, ...]:
    """Return safe candidate identities before any hashing or nested traversal."""
    if type(candidates) is not tuple or any(
        type(item) is not HKCaseTreatmentCandidate for item in candidates
    ):
        raise HKCaseTreatmentClassificationError(_CLASSIFICATION_INVALID)
    identities = tuple(item.candidate_id for item in candidates)
    if any(type(item) is not str or not item for item in identities):
        raise HKCaseTreatmentClassificationError(_CLASSIFICATION_INVALID)
    return identities


def _validated_decision_ids(
    decisions: tuple[HKCaseTreatmentDecision, ...],
) -> tuple[str, ...]:
    """Return safe decision identities and candidate bindings before hashing."""
    if type(decisions) is not tuple or any(
        type(item) is not HKCaseTreatmentDecision for item in decisions
    ):
        raise HKCaseTreatmentClassificationError(_CLASSIFICATION_INVALID)
    identities = tuple(item.decision_id for item in decisions)
    candidate_ids = tuple(item.candidate_id for item in decisions)
    if any(type(item) is not str or not item for item in identities + candidate_ids):
        raise HKCaseTreatmentClassificationError(_CLASSIFICATION_INVALID)
    return identities


def _edge_document(edge: HKCaseTreatmentEdge) -> dict[str, object]:
    """Return complete safe edge primitives only after exact nested validation."""
    if (
        type(edge) is not HKCaseTreatmentEdge
        or any(
            type(value) is not str or not value
            for value in (
                edge.later_proposition_id,
                edge.earlier_proposition_id,
                edge.opinion_id,
                edge.effective_date,
                edge.decision_id,
            )
        )
        or type(edge.treatment) is not HKCaseTreatment
        or type(edge.authority_consequence) is not HKCaseTreatmentAuthorityConsequence
        or type(edge.support_paragraph_refs) is not tuple
        or not edge.support_paragraph_refs
        or any(type(item) is not str or not item for item in edge.support_paragraph_refs)
        or len(set(edge.support_paragraph_refs)) != len(edge.support_paragraph_refs)
        or _parse_canonical_date(edge.effective_date) is None
    ):
        raise ValueError(_EDGE_INVALID)
    return {
        "authority_consequence": edge.authority_consequence.value,
        "decision_id": edge.decision_id,
        "earlier_proposition_id": edge.earlier_proposition_id,
        "effective_date": edge.effective_date,
        "later_proposition_id": edge.later_proposition_id,
        "opinion_id": edge.opinion_id,
        "support_paragraph_refs": list(edge.support_paragraph_refs),
        "treatment": edge.treatment.value,
    }


def _edge_relationship_document(edge: HKCaseTreatmentEdge) -> dict[str, object]:
    """Exclude the caller decision identity from canonical relationship identity."""
    document = _edge_document(edge)
    del document["decision_id"]
    return document


def _classification_projection(
    edges: tuple[HKCaseTreatmentEdge, ...], quarantined_candidate_ids: tuple[str, ...]
) -> bytes:
    """Return the canonical complete terminal classification projection."""
    if (
        type(edges) is not tuple
        or any(type(item) is not HKCaseTreatmentEdge for item in edges)
        or type(quarantined_candidate_ids) is not tuple
        or any(type(item) is not str or not item for item in quarantined_candidate_ids)
        or len(set(quarantined_candidate_ids)) != len(quarantined_candidate_ids)
        or any(not is_hk_case_treatment_edge_issued(item) for item in edges)
    ):
        raise TypeError(_CLASSIFICATION_INVALID)
    return _canonical_bytes(
        {
            "edges": [_edge_document(item) for item in edges],
            "quarantined_candidate_ids": list(quarantined_candidate_ids),
        }
    )


def _issue_classification(
    *, edges: tuple[HKCaseTreatmentEdge, ...], quarantined_candidate_ids: tuple[str, ...]
) -> HKCaseTreatmentClassification:
    """Issue one exact process-local classification after canonical validation."""
    projection = _classification_projection(edges, quarantined_candidate_ids)
    issuance = _HKCaseTreatmentClassificationIssuance(projection)
    _ISSUED_CLASSIFICATIONS[issuance] = _HKCaseTreatmentClassificationFacts(projection, None)
    result = HKCaseTreatmentClassification(edges, quarantined_candidate_ids, issuance)
    _ISSUED_CLASSIFICATIONS[issuance] = _HKCaseTreatmentClassificationFacts(projection, ref(result))
    result.__post_init__()
    return result


def _issued_classification_facts(classification: HKCaseTreatmentClassification) -> None:
    """Require exact identity plus the originally issued complete projection."""
    issuance = classification.issuance
    if type(issuance) is not _HKCaseTreatmentClassificationIssuance:
        raise TypeError(_CLASSIFICATION_FACTORY_REQUIRED)
    facts = _ISSUED_CLASSIFICATIONS.get(issuance)
    projection = _classification_projection(
        classification.edges, classification.quarantined_candidate_ids
    )
    if (
        facts is None
        or issuance.projection != facts.projection
        or projection != facts.projection
        or (facts.result_reference is not None and facts.result_reference() is not classification)
    ):
        raise TypeError(_CLASSIFICATION_FACTORY_REQUIRED)


def _parse_canonical_date(value: object) -> date | None:
    """Accept only the exact calendar ``YYYY-MM-DD`` round trip."""
    if type(value) is not str:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _canonical_bytes(document: dict[str, object]) -> bytes:
    """Encode one local primitive projection deterministically."""
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _raw_fingerprint(raw: bytes) -> str:
    """Fingerprint exact canonical bytes."""
    return "sha256:" + sha256(raw).hexdigest()


def _duplicates(values: tuple[str, ...]) -> bool:
    """Return whether a supposedly unique immutable identity occurs more than once."""
    return len(values) != len(set(values))
