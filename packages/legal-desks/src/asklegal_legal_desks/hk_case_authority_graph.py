# ruff: noqa: BLE001, TRY301
"""Fail-closed deterministic current-authority selection for Hong Kong Cases."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import SupportsIndex
from weakref import ReferenceType, WeakKeyDictionary, ref

from .hk_case_coverage_ledger import HKCaseOpinionRole
from .hk_case_proposition import HKCaseAdmittedProposition, HKCasePropositionAdmissionResult
from .hk_case_treatment import (
    HKCaseTreatment,
    HKCaseTreatmentAuthorityConsequence,
    HKCaseTreatmentEdge,
    is_hk_case_treatment_edge_issued,
)

_IN_SCOPE_COURTS = frozenset({"CFA", "CA", "CFI", "CT"})
_GRAPH_FACTORY_REQUIRED = "HK_CASE_AUTHORITY_GRAPH_FACTORY_REQUIRED"
_GRAPH_INVALID = "HK_CASE_AUTHORITY_GRAPH_INVALID"
_GRAPH_NOT_TRANSFERABLE = "HK_CASE_AUTHORITY_GRAPH_NOT_TRANSFERABLE"
_PROPOSITION_INVALID = "HK_CASE_AUTHORITY_PROPOSITION_INVALID"
_SELECTION_FACTORY_REQUIRED = "HK_CASE_AUTHORITY_SELECTION_FACTORY_REQUIRED"
_SELECTION_NOT_TRANSFERABLE = "HK_CASE_AUTHORITY_SELECTION_NOT_TRANSFERABLE"


class HKCaseAuthoritySelectionState(StrEnum):
    """The only authority selections emitted by this source-neutral graph."""

    CURRENT = "CURRENT"
    QUARANTINED = "QUARANTINED"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class HKCaseAuthorityProposition:
    """An already admitted proposition with source-supported authority facts."""

    proposition_id: str
    judgment_id: str
    court_id: str
    decision_date: str
    opinion_id: str
    opinion_is_operative: bool
    admitted: bool
    evidence_complete: bool
    opinion_role: HKCaseOpinionRole | None = None


@dataclass(frozen=True, slots=True)
class _HKCaseAuthorityPropositionIssuedFacts:
    """Exact retained upstream and derived facts for one proposition identity."""

    admission: HKCasePropositionAdmissionResult
    admission_projection: bytes
    admission_fingerprint: str
    proposition_projection: bytes


_ISSUED_PROPOSITIONS: WeakKeyDictionary[
    HKCaseAuthorityProposition, _HKCaseAuthorityPropositionIssuedFacts
] = WeakKeyDictionary()


def build_hk_case_authority_propositions(
    admission: HKCasePropositionAdmissionResult,
) -> tuple[HKCaseAuthorityProposition, ...]:
    """Adapt one factory-issued Task 3 admission into graph facts without caller authority."""
    try:
        if type(admission) is not HKCasePropositionAdmissionResult:
            raise TypeError
        admission.__post_init__()
        result: list[HKCaseAuthorityProposition] = []
        for proposition in admission.propositions:
            fact = _authority_proposition_from_admission(admission, proposition)
            _ISSUED_PROPOSITIONS[fact] = _HKCaseAuthorityPropositionIssuedFacts(
                admission=admission,
                admission_projection=admission.admission_projection,
                admission_fingerprint=admission.admission_fingerprint,
                proposition_projection=_authority_proposition_projection(fact),
            )
            if not _is_issued_proposition(fact):
                raise TypeError
            result.append(fact)
        return tuple(result)
    except Exception as error:
        raise HKCaseAuthorityGraphError(_PROPOSITION_INVALID) from error


def _is_issued_proposition(proposition: HKCaseAuthorityProposition) -> bool:
    """Replay exact identity, derived primitives, retained admission, and source projection."""
    if type(proposition) is not HKCaseAuthorityProposition:
        return False
    issued = _ISSUED_PROPOSITIONS.get(proposition)
    if type(issued) is not _HKCaseAuthorityPropositionIssuedFacts:
        return False
    try:
        admission = issued.admission
        if type(admission) is not HKCasePropositionAdmissionResult:
            return False
        admission.__post_init__()
        matching = tuple(
            item
            for item in admission.propositions
            if item.proposition_id == proposition.proposition_id
        )
        if len(matching) != 1:
            return False
        expected = _authority_proposition_from_admission(admission, matching[0])
        return (
            admission.admission_projection == issued.admission_projection
            and admission.admission_fingerprint == issued.admission_fingerprint
            and _authority_proposition_projection(proposition) == issued.proposition_projection
            and _authority_proposition_projection(expected) == issued.proposition_projection
        )
    except Exception:
        return False


def _authority_proposition_from_admission(
    admission: HKCasePropositionAdmissionResult,
    proposition: HKCaseAdmittedProposition,
) -> HKCaseAuthorityProposition:
    """Derive every graph primitive from one exact retained Task 3 proposition."""
    if (
        type(admission) is not HKCasePropositionAdmissionResult
        or type(proposition) is not HKCaseAdmittedProposition
    ):
        raise TypeError
    task = admission.request_pair.decision.semantic_task
    return HKCaseAuthorityProposition(
        proposition_id=proposition.proposition_id,
        judgment_id=task.judicial_decision_id,
        court_id=proposition.court_id,
        decision_date=task.decision_date,
        opinion_id=proposition.opinion_id,
        opinion_is_operative=proposition.authority_role
        in {HKCaseOpinionRole.COURT, HKCaseOpinionRole.JOINT, HKCaseOpinionRole.LEAD},
        admitted=True,
        evidence_complete=True,
        opinion_role=proposition.authority_role,
    )


def _authority_proposition_projection(proposition: HKCaseAuthorityProposition) -> bytes:
    """Project the complete exact authority proposition primitive set."""
    if (
        type(proposition) is not HKCaseAuthorityProposition
        or any(
            type(value) is not str or not value
            for value in (
                proposition.proposition_id,
                proposition.judgment_id,
                proposition.court_id,
                proposition.decision_date,
                proposition.opinion_id,
            )
        )
        or _parse_date(proposition.decision_date) is None
        or type(proposition.opinion_is_operative) is not bool
        or type(proposition.admitted) is not bool
        or type(proposition.evidence_complete) is not bool
        or type(proposition.opinion_role) is not HKCaseOpinionRole
        or proposition.opinion_is_operative
        is not (
            proposition.opinion_role
            in {HKCaseOpinionRole.COURT, HKCaseOpinionRole.JOINT, HKCaseOpinionRole.LEAD}
        )
    ):
        raise TypeError
    return _canonical_bytes(
        {
            "admitted": proposition.admitted,
            "court_id": proposition.court_id,
            "decision_date": proposition.decision_date,
            "evidence_complete": proposition.evidence_complete,
            "judgment_id": proposition.judgment_id,
            "opinion_id": proposition.opinion_id,
            "opinion_is_operative": proposition.opinion_is_operative,
            "opinion_role": proposition.opinion_role.value,
            "proposition_id": proposition.proposition_id,
        }
    )


class HKCaseAuthorityGraphError(ValueError):
    """Closed ordinary graph input failure; factory objects remain process-local."""


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class _HKCaseAuthorityOutputIssuance:
    """Opaque process-local authority shared by selection and graph outputs."""

    kind: str
    projection: bytes

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[object, ...]:
        """Reject transfer; restart recovery must rerun the owning factory."""
        del protocol
        code = _SELECTION_NOT_TRANSFERABLE if self.kind == "SELECTION" else _GRAPH_NOT_TRANSFERABLE
        raise TypeError(code)


@dataclass(frozen=True, slots=True)
class _HKCaseAuthorityOutputIssuedFacts:
    """Registry-only output facts bound to one exact result identity."""

    kind: str
    projection: bytes
    result_reference: ReferenceType[HKCaseAuthoritySelection | HKCaseAuthorityGraph] | None


_ISSUED_OUTPUTS: WeakKeyDictionary[
    _HKCaseAuthorityOutputIssuance, _HKCaseAuthorityOutputIssuedFacts
] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class HKCaseAuthorityCorrection:
    """One evidence-bound forward correction lineage relation between judgments."""

    correction_id: str
    superseded_judgment_id: str
    replacement_judgment_id: str
    admitted: bool
    evidence_complete: bool
    effective_date: str = ""
    source_admitted: bool = False
    superseded_admission_fingerprint: str = ""
    replacement_admission_fingerprint: str = ""


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKCaseAuthoritySelection:
    """One proposition's exact result at the supplied cutoff."""

    proposition_id: str
    state: HKCaseAuthoritySelectionState
    authority_note_required: bool
    issuance: _HKCaseAuthorityOutputIssuance | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Replay exact process-local selection issuance and primitive projection."""
        _issued_output_facts(self, "SELECTION", _selection_projection(self))

    def __copy__(self) -> HKCaseAuthoritySelection:
        """Reject transfer of selection authority by shallow copy."""
        raise TypeError(_SELECTION_NOT_TRANSFERABLE)

    def __deepcopy__(self, memo: dict[int, object]) -> HKCaseAuthoritySelection:
        """Reject transfer of selection authority by deep copy."""
        del memo
        raise TypeError(_SELECTION_NOT_TRANSFERABLE)

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[object, ...]:
        """Reject selection serialization; restart recovery reruns graph construction."""
        del protocol
        raise TypeError(_SELECTION_NOT_TRANSFERABLE)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKCaseAuthorityGraph:
    """A deterministic projection of one directional-edge fact universe."""

    selections: tuple[HKCaseAuthoritySelection, ...]
    quarantined_edge_ids: tuple[str, ...]
    issuance: _HKCaseAuthorityOutputIssuance | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Replay exact process-local graph issuance and every issued selection."""
        _issued_output_facts(self, "GRAPH", _graph_projection(self))

    def selection(self, proposition_id: str) -> HKCaseAuthoritySelection:
        """Return the exact selection or reject an unknown proposition identity."""
        self.__post_init__()
        if type(proposition_id) is not str or not proposition_id:
            raise KeyError(proposition_id)
        for selection in self.selections:
            if selection.proposition_id == proposition_id:
                selection.__post_init__()
                return selection
        raise KeyError(proposition_id)

    def __copy__(self) -> HKCaseAuthorityGraph:
        """Reject transfer of graph authority by shallow copy."""
        raise TypeError(_GRAPH_NOT_TRANSFERABLE)

    def __deepcopy__(self, memo: dict[int, object]) -> HKCaseAuthorityGraph:
        """Reject transfer of graph authority by deep copy."""
        del memo
        raise TypeError(_GRAPH_NOT_TRANSFERABLE)

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[object, ...]:
        """Reject graph serialization; restart recovery reruns admitted inputs."""
        del protocol
        raise TypeError(_GRAPH_NOT_TRANSFERABLE)


def build_hk_case_authority_graph(
    propositions: tuple[HKCaseAuthorityProposition, ...],
    edges: tuple[HKCaseTreatmentEdge, ...],
    corrections: tuple[HKCaseAuthorityCorrection, ...],
    cutoff: str,
) -> HKCaseAuthorityGraph:
    """Normalize ordinary hostile inputs to one closed graph error."""
    try:
        return _build_hk_case_authority_graph(propositions, edges, corrections, cutoff)
    except HKCaseAuthorityGraphError:
        raise
    except Exception:
        raise HKCaseAuthorityGraphError(_GRAPH_INVALID) from None


def _build_hk_case_authority_graph(
    propositions: tuple[HKCaseAuthorityProposition, ...],
    edges: tuple[HKCaseTreatmentEdge, ...],
    corrections: tuple[HKCaseAuthorityCorrection, ...],
    cutoff: str,
) -> HKCaseAuthorityGraph:
    """Select current authority only after every identity and legal-effect check passes.

    The graph never guesses through uncertainty.  Any malformed, duplicate,
    temporally impossible, hierarchy-invalid, conflicting, cyclic, or
    correction-lineage-invalid fact quarantines the smallest affected earlier
    proposition and prevents retirement.
    """
    propositions = _validated_proposition_facts(propositions)
    edge_shapes = _validated_edge_facts(edges)
    corrections = _validated_correction_facts(corrections)
    cutoff_date = _parse_date(cutoff)
    proposition_map = {item.proposition_id: item for item in propositions}
    invalid_propositions = _invalid_proposition_ids(propositions, proposition_map, cutoff_date)
    invalid_targets: set[str] = set(invalid_propositions)
    quarantined_edge_ids: set[str] = set()

    correction_invalid_judgments, superseded_judgments = _correction_lineage(
        corrections, proposition_map
    )
    invalid_targets.update(
        proposition.proposition_id
        for proposition in propositions
        if proposition.judgment_id in correction_invalid_judgments
    )
    structurally_valid_edges = tuple(
        edge for edge, shape_is_valid in zip(edges, edge_shapes, strict=True) if shape_is_valid
    )
    duplicate_decision_ids = _duplicate_decision_ids(structurally_valid_edges)
    valid_edges: list[HKCaseTreatmentEdge] = []
    for edge, shape_is_valid in zip(edges, edge_shapes, strict=True):
        target = edge.earlier_proposition_id
        if (
            not shape_is_valid
            or edge.decision_id in duplicate_decision_ids
            or not _edge_is_valid(edge, proposition_map, cutoff_date, correction_invalid_judgments)
        ):
            invalid_targets.add(target)
            quarantined_edge_ids.add(edge.decision_id)
            continue
        later = proposition_map[edge.later_proposition_id]
        # Only an exact issued DISSENT fact reaches this point.  Its edge stays
        # rejected, but the known non-operative attempt is not uncertainty
        # about the earlier proposition itself.
        if later.opinion_role is HKCaseOpinionRole.DISSENT:
            quarantined_edge_ids.add(edge.decision_id)
            continue
        # A complete admitted replacement retracts its superseded reasons from
        # the current graph.  The older edge remains immutable history but can
        # no longer keep the earlier proposition retired.
        if later.judgment_id in superseded_judgments:
            continue
        # No treatment Rulebook/Rule Trace exists in this source-neutral slice.
        # An otherwise coherent operative edge therefore remains uncertainty
        # about its target and cannot create a relationship or legal effect.
        invalid_targets.add(target)
        quarantined_edge_ids.add(edge.decision_id)
        continue

    for target, group in _edges_by_target(valid_edges).items():
        if len({edge.authority_consequence for edge in group}) > 1:
            invalid_targets.add(target)
            quarantined_edge_ids.update(edge.decision_id for edge in group)

    for cycle in _edge_cycles(valid_edges):
        for edge in cycle:
            invalid_targets.add(edge.earlier_proposition_id)
            quarantined_edge_ids.add(edge.decision_id)

    # Task 3 admission establishes an evidence-bound proposition, not current-law
    # authority.  This slice has no admitted complete-treatment result, treatment
    # RuleTrace, court-finality fact, or appellate-disposition authority to replay.
    # Keep the accepted set empty until a later contract supplies and replays every
    # one of those authorities; never infer acceptance from the absence of an edge.
    accepted_authority_ids: frozenset[str] = frozenset()
    selections = tuple(
        _selection_for(
            proposition,
            valid_edges,
            invalid_targets,
            accepted_authority_ids,
        )
        for proposition in propositions
    )
    return _issue_graph(
        selections=tuple(sorted(selections, key=lambda item: item.proposition_id)),
        quarantined_edge_ids=tuple(sorted(quarantined_edge_ids)),
    )


def _validated_proposition_facts(
    propositions: tuple[HKCaseAuthorityProposition, ...],
) -> tuple[HKCaseAuthorityProposition, ...]:
    """Validate every outer and nested primitive before mapping or hashing."""
    if type(propositions) is not tuple or any(
        type(item) is not HKCaseAuthorityProposition for item in propositions
    ):
        raise HKCaseAuthorityGraphError(_GRAPH_INVALID)
    for item in propositions:
        if (
            any(
                type(value) is not str or not value
                for value in (
                    item.proposition_id,
                    item.judgment_id,
                    item.court_id,
                    item.decision_date,
                    item.opinion_id,
                )
            )
            or type(item.opinion_is_operative) is not bool
            or type(item.admitted) is not bool
            or type(item.evidence_complete) is not bool
            or (item.opinion_role is not None and type(item.opinion_role) is not HKCaseOpinionRole)
        ):
            raise HKCaseAuthorityGraphError(_GRAPH_INVALID)
    return propositions


def _validated_edge_facts(edges: tuple[HKCaseTreatmentEdge, ...]) -> tuple[bool, ...]:
    """Validate edge identities before returning exact nested-shape dispositions."""
    if type(edges) is not tuple or any(type(item) is not HKCaseTreatmentEdge for item in edges):
        raise HKCaseAuthorityGraphError(_GRAPH_INVALID)
    results: list[bool] = []
    for edge in edges:
        if any(
            type(value) is not str or not value
            for value in (
                edge.later_proposition_id,
                edge.earlier_proposition_id,
                edge.decision_id,
            )
        ):
            raise HKCaseAuthorityGraphError(_GRAPH_INVALID)
        results.append(
            type(edge.opinion_id) is str
            and bool(edge.opinion_id)
            and type(edge.effective_date) is str
            and _parse_date(edge.effective_date) is not None
            and type(edge.support_paragraph_refs) is tuple
            and bool(edge.support_paragraph_refs)
            and all(type(item) is str and bool(item) for item in edge.support_paragraph_refs)
            and len(set(edge.support_paragraph_refs)) == len(edge.support_paragraph_refs)
            and type(edge.treatment) is HKCaseTreatment
            and type(edge.authority_consequence) is HKCaseTreatmentAuthorityConsequence
        )
    return tuple(results)


def _validated_correction_facts(
    corrections: tuple[HKCaseAuthorityCorrection, ...],
) -> tuple[HKCaseAuthorityCorrection, ...]:
    """Validate exact correction primitives before set or mapping operations."""
    if type(corrections) is not tuple or any(
        type(item) is not HKCaseAuthorityCorrection for item in corrections
    ):
        raise HKCaseAuthorityGraphError(_GRAPH_INVALID)
    for item in corrections:
        if (
            any(
                type(value) is not str
                for value in (
                    item.correction_id,
                    item.superseded_judgment_id,
                    item.replacement_judgment_id,
                    item.effective_date,
                    item.superseded_admission_fingerprint,
                    item.replacement_admission_fingerprint,
                )
            )
            or type(item.admitted) is not bool
            or type(item.evidence_complete) is not bool
            or type(item.source_admitted) is not bool
        ):
            raise HKCaseAuthorityGraphError(_GRAPH_INVALID)
    return corrections


def _invalid_proposition_ids(
    propositions: tuple[HKCaseAuthorityProposition, ...],
    proposition_map: dict[str, HKCaseAuthorityProposition],
    cutoff: date | None,
) -> set[str]:
    """Reject malformed/duplicate proposition facts before any edge can rely on them."""
    invalid: set[str] = set()
    for item in propositions:
        if not _proposition_is_operative_graph_input(item, cutoff):
            invalid.add(item.proposition_id)
    if len(proposition_map) != len(propositions):
        invalid.update(item.proposition_id for item in propositions)
    return invalid


def _proposition_common_facts_are_valid(
    proposition: HKCaseAuthorityProposition, cutoff: date | None
) -> bool:
    """Validate exact issuance, source evidence, court, and cutoff facts."""
    decision_date = _parse_date(proposition.decision_date)
    return (
        decision_date is not None
        and cutoff is not None
        and decision_date <= cutoff
        and proposition.court_id in _IN_SCOPE_COURTS
        and proposition.admitted is True
        and proposition.evidence_complete is True
        and type(proposition.opinion_role) is HKCaseOpinionRole
        and _is_issued_proposition(proposition)
    )


def _proposition_is_operative_graph_input(
    proposition: HKCaseAuthorityProposition, cutoff: date | None
) -> bool:
    """Require one exact issued operative proposition before authority screening."""
    return (
        _proposition_common_facts_are_valid(proposition, cutoff)
        and proposition.opinion_role
        in {HKCaseOpinionRole.COURT, HKCaseOpinionRole.JOINT, HKCaseOpinionRole.LEAD}
        and proposition.opinion_is_operative is True
    )


def _proposition_is_edge_source(
    proposition: HKCaseAuthorityProposition, cutoff: date | None
) -> bool:
    """Allow only exact issued operative or exact issued DISSENT later facts."""
    return _proposition_common_facts_are_valid(proposition, cutoff) and (
        (
            proposition.opinion_role
            in {HKCaseOpinionRole.COURT, HKCaseOpinionRole.JOINT, HKCaseOpinionRole.LEAD}
            and proposition.opinion_is_operative is True
        )
        or (
            proposition.opinion_role is HKCaseOpinionRole.DISSENT
            and proposition.opinion_is_operative is False
        )
    )


def _correction_lineage(
    corrections: tuple[HKCaseAuthorityCorrection, ...],
    propositions: dict[str, HKCaseAuthorityProposition],
) -> tuple[set[str], set[str]]:
    """Return invalid judgments and valid superseded judgments for reselection."""
    judgment_ids = {item.judgment_id for item in propositions.values()}
    invalid: set[str] = set()
    seen_ids: set[str] = set()
    mapping: dict[str, str] = {}
    for correction in corrections:
        if (
            not correction.correction_id
            or correction.correction_id in seen_ids
            or not correction.admitted
            or not correction.evidence_complete
            or correction.superseded_judgment_id not in judgment_ids
            or correction.replacement_judgment_id not in judgment_ids
            or correction.superseded_judgment_id == correction.replacement_judgment_id
            or correction.superseded_judgment_id in mapping
        ):
            invalid.update((correction.superseded_judgment_id, correction.replacement_judgment_id))
        else:
            mapping[correction.superseded_judgment_id] = correction.replacement_judgment_id
        seen_ids.add(correction.correction_id)
    for start in tuple(mapping):
        visited: set[str] = set()
        current = start
        while current in mapping:
            if current in visited:
                invalid.update(visited)
                break
            visited.add(current)
            current = mapping[current]
    # This first source-neutral slice has no issued correction/finality/cutoff
    # contract.  A caller-created correction cannot reselect authority.
    invalid.update(
        judgment_id
        for correction in corrections
        for judgment_id in (
            correction.superseded_judgment_id,
            correction.replacement_judgment_id,
        )
    )
    return invalid, set()


def _edge_is_valid(
    edge: HKCaseTreatmentEdge,
    propositions: dict[str, HKCaseAuthorityProposition],
    cutoff: date | None,
    correction_invalid_judgments: set[str],
) -> bool:
    """Apply exact edge, evidence, opinion, temporal, court, and correction checks."""
    later = propositions.get(edge.later_proposition_id)
    earlier = propositions.get(edge.earlier_proposition_id)
    edge_date = _parse_date(edge.effective_date)
    later_date = None if later is None else _parse_date(later.decision_date)
    earlier_date = None if earlier is None else _parse_date(earlier.decision_date)
    return not (
        later is None
        or earlier is None
        or edge.later_proposition_id == edge.earlier_proposition_id
        or type(edge.decision_id) is not str
        or not edge.decision_id
        or type(edge.opinion_id) is not str
        or edge.opinion_id != later.opinion_id
        or not edge.support_paragraph_refs
        or len(set(edge.support_paragraph_refs)) != len(edge.support_paragraph_refs)
        or not all(type(ref) is str and ref for ref in edge.support_paragraph_refs)
        or edge_date is None
        or cutoff is None
        or edge_date > cutoff
        or later_date is None
        or earlier_date is None
        or edge_date != later_date
        or later_date <= earlier_date
        or type(edge.authority_consequence) is not HKCaseTreatmentAuthorityConsequence
        or not is_hk_case_treatment_edge_issued(edge)
        or not _proposition_is_edge_source(later, cutoff)
        or not _proposition_is_operative_graph_input(earlier, cutoff)
        or later.judgment_id in correction_invalid_judgments
        or earlier.judgment_id in correction_invalid_judgments
    )


def _duplicate_decision_ids(edges: tuple[HKCaseTreatmentEdge, ...]) -> set[str]:
    """Return duplicate canonical relationships, independent of caller decision IDs."""
    counts: dict[str, int] = {}
    for edge in edges:
        counts[edge.relationship_id] = counts.get(edge.relationship_id, 0) + 1
    return {
        edge.decision_id
        for edge in edges
        if not edge.decision_id or counts[edge.relationship_id] > 1
    }


def _edges_by_target(edges: list[HKCaseTreatmentEdge]) -> dict[str, list[HKCaseTreatmentEdge]]:
    """Group already valid edges by the proposition whose selection they can affect."""
    grouped: dict[str, list[HKCaseTreatmentEdge]] = {}
    for edge in edges:
        grouped.setdefault(edge.earlier_proposition_id, []).append(edge)
    return grouped


def _edge_cycles(edges: list[HKCaseTreatmentEdge]) -> tuple[tuple[HKCaseTreatmentEdge, ...], ...]:
    """Detect cycles defensively even though valid temporal direction should preclude them."""
    by_later = {edge.later_proposition_id: edge for edge in edges}
    cycles: list[tuple[HKCaseTreatmentEdge, ...]] = []
    for edge in edges:
        path: list[HKCaseTreatmentEdge] = []
        current = edge
        while current not in path:
            path.append(current)
            next_edge = by_later.get(current.earlier_proposition_id)
            if next_edge is None:
                break
            current = next_edge
        else:
            cycles.append(tuple(path[path.index(current) :]))
    return tuple(cycles)


def _selection_for(
    proposition: HKCaseAuthorityProposition,
    edges: list[HKCaseTreatmentEdge],
    invalid_targets: set[str],
    accepted_authority_ids: frozenset[str],
) -> HKCaseAuthoritySelection:
    """Select only authority identities backed by every replayed accepted authority."""
    relevant = [edge for edge in edges if edge.earlier_proposition_id == proposition.proposition_id]
    if (
        proposition.proposition_id in invalid_targets
        or proposition.proposition_id not in accepted_authority_ids
    ):
        state = HKCaseAuthoritySelectionState.QUARANTINED
    elif any(
        edge.authority_consequence is HKCaseTreatmentAuthorityConsequence.RETIRE
        for edge in relevant
    ):
        state = HKCaseAuthoritySelectionState.RETIRED
    else:
        state = HKCaseAuthoritySelectionState.CURRENT
    return _issue_selection(
        proposition_id=proposition.proposition_id,
        state=state,
        authority_note_required=state is HKCaseAuthoritySelectionState.CURRENT
        and any(
            edge.authority_consequence is HKCaseTreatmentAuthorityConsequence.AUTHORITY_NOTE
            for edge in relevant
        ),
    )


def replay_hk_case_authority_selection(
    selection: HKCaseAuthoritySelection,
) -> HKCaseAuthoritySelection:
    """Replay one exact live selection; restart recovery rebuilds the whole graph."""
    if type(selection) is not HKCaseAuthoritySelection:
        raise HKCaseAuthorityGraphError(_GRAPH_INVALID)
    try:
        selection.__post_init__()
    except Exception:
        raise HKCaseAuthorityGraphError(_GRAPH_INVALID) from None
    return selection


def replay_hk_case_authority_graph(graph: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
    """Replay one exact live graph; restart recovery reruns admitted upstream inputs."""
    if type(graph) is not HKCaseAuthorityGraph:
        raise HKCaseAuthorityGraphError(_GRAPH_INVALID)
    try:
        graph.__post_init__()
    except Exception:
        raise HKCaseAuthorityGraphError(_GRAPH_INVALID) from None
    return graph


def _selection_projection(selection: HKCaseAuthoritySelection) -> bytes:
    """Return one complete exact selection projection without trusting enum access."""
    if (
        type(selection) is not HKCaseAuthoritySelection
        or type(selection.proposition_id) is not str
        or not selection.proposition_id
        or type(selection.state) is not HKCaseAuthoritySelectionState
        or type(selection.authority_note_required) is not bool
        or (
            selection.authority_note_required
            and selection.state is not HKCaseAuthoritySelectionState.CURRENT
        )
    ):
        raise TypeError
    return _canonical_bytes(
        {
            "authority_note_required": selection.authority_note_required,
            "proposition_id": selection.proposition_id,
            "state": selection.state.value,
        }
    )


def _graph_projection(graph: HKCaseAuthorityGraph) -> bytes:
    """Return one complete graph projection after replaying every nested selection."""
    if (
        type(graph) is not HKCaseAuthorityGraph
        or type(graph.selections) is not tuple
        or any(type(item) is not HKCaseAuthoritySelection for item in graph.selections)
        or type(graph.quarantined_edge_ids) is not tuple
        or any(type(item) is not str or not item for item in graph.quarantined_edge_ids)
    ):
        raise TypeError
    for selection in graph.selections:
        selection.__post_init__()
    proposition_ids = tuple(item.proposition_id for item in graph.selections)
    if len(set(proposition_ids)) != len(proposition_ids) or len(
        set(graph.quarantined_edge_ids)
    ) != len(graph.quarantined_edge_ids):
        raise TypeError
    return _canonical_bytes(
        {
            "quarantined_edge_ids": list(graph.quarantined_edge_ids),
            "selections": [
                {
                    "authority_note_required": item.authority_note_required,
                    "proposition_id": item.proposition_id,
                    "state": item.state.value,
                }
                for item in graph.selections
            ],
        }
    )


def _issue_selection(
    *,
    proposition_id: str,
    state: HKCaseAuthoritySelectionState,
    authority_note_required: bool,
) -> HKCaseAuthoritySelection:
    """Issue one exact nontransferable process-local selection."""
    provisional = object.__new__(HKCaseAuthoritySelection)
    object.__setattr__(provisional, "proposition_id", proposition_id)
    object.__setattr__(provisional, "state", state)
    object.__setattr__(provisional, "authority_note_required", authority_note_required)
    object.__setattr__(provisional, "issuance", None)
    projection = _selection_projection(provisional)
    issuance = _HKCaseAuthorityOutputIssuance("SELECTION", projection)
    _ISSUED_OUTPUTS[issuance] = _HKCaseAuthorityOutputIssuedFacts("SELECTION", projection, None)
    result = HKCaseAuthoritySelection(proposition_id, state, authority_note_required, issuance)
    _ISSUED_OUTPUTS[issuance] = _HKCaseAuthorityOutputIssuedFacts(
        "SELECTION", projection, ref(result)
    )
    result.__post_init__()
    return result


def _issue_graph(
    *, selections: tuple[HKCaseAuthoritySelection, ...], quarantined_edge_ids: tuple[str, ...]
) -> HKCaseAuthorityGraph:
    """Issue one exact nontransferable process-local graph."""
    provisional = object.__new__(HKCaseAuthorityGraph)
    object.__setattr__(provisional, "selections", selections)
    object.__setattr__(provisional, "quarantined_edge_ids", quarantined_edge_ids)
    object.__setattr__(provisional, "issuance", None)
    projection = _graph_projection(provisional)
    issuance = _HKCaseAuthorityOutputIssuance("GRAPH", projection)
    _ISSUED_OUTPUTS[issuance] = _HKCaseAuthorityOutputIssuedFacts("GRAPH", projection, None)
    result = HKCaseAuthorityGraph(selections, quarantined_edge_ids, issuance)
    _ISSUED_OUTPUTS[issuance] = _HKCaseAuthorityOutputIssuedFacts("GRAPH", projection, ref(result))
    result.__post_init__()
    return result


def _issued_output_facts(
    output: HKCaseAuthoritySelection | HKCaseAuthorityGraph,
    kind: str,
    projection: bytes,
) -> None:
    """Require exact output identity and its originally issued complete projection."""
    issuance = output.issuance
    factory_code = _SELECTION_FACTORY_REQUIRED if kind == "SELECTION" else _GRAPH_FACTORY_REQUIRED
    if type(issuance) is not _HKCaseAuthorityOutputIssuance:
        raise TypeError(factory_code)
    facts = _ISSUED_OUTPUTS.get(issuance)
    if (
        facts is None
        or issuance.kind != kind
        or facts.kind != kind
        or issuance.projection != facts.projection
        or projection != facts.projection
        or (facts.result_reference is not None and facts.result_reference() is not output)
    ):
        raise TypeError(factory_code)


def _canonical_bytes(document: dict[str, object]) -> bytes:
    """Encode one local primitive projection deterministically."""
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _parse_date(value: object) -> date | None:
    """Return one strict ISO date or ``None`` without leaking raw malformed input."""
    if type(value) is not str:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None
