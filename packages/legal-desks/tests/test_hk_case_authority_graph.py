"""Contract tests for the deterministic Hong Kong Case authority graph."""

from __future__ import annotations

import copy
import pickle
import runpy
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import TypeIs

import asklegal_legal_desks.hk_case_authority_graph as graph_module
import pytest
from asklegal_legal_desks.hk_case_authority_graph import (
    HKCaseAuthorityCorrection,
    HKCaseAuthorityGraph,
    HKCaseAuthorityGraphError,
    HKCaseAuthorityProposition,
    HKCaseAuthoritySelection,
    HKCaseAuthoritySelectionState,
    build_hk_case_authority_graph,
    build_hk_case_authority_propositions,
    replay_hk_case_authority_graph,
    replay_hk_case_authority_selection,
)
from asklegal_legal_desks.hk_case_coverage_ledger import HKCaseEvidenceRole, HKCaseOpinionRole
from asklegal_legal_desks.hk_case_judgment import HKCaseJudgmentBundle
from asklegal_legal_desks.hk_case_proposition import (
    HKCaseAdmittedEvidenceLink,
    HKCaseAdmittedProposition,
    HKCaseAdmittedSemanticDecision,
    HKCasePropositionAdmissionResult,
    HKCasePropositionRequestPair,
    admit_hk_case_propositions,
)
from asklegal_legal_desks.hk_case_treatment import (
    HKCaseTreatment,
    HKCaseTreatmentAuthorityConsequence,
    HKCaseTreatmentEdge,
)
from asklegal_legal_desks.model import SemanticTaskProfile


def _is_object_dictionary(value: object) -> TypeIs[dict[object, object]]:
    return type(value) is dict


def _is_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _fixture_helper(namespace: object, name: str) -> object:
    if not _is_object_dictionary(namespace) or name not in namespace:
        raise TypeError(name)
    return namespace[name]


def _fixture_bundle(factory: object) -> HKCaseJudgmentBundle:
    if not callable(factory):
        raise TypeError
    result: object = factory()
    if type(result) is not HKCaseJudgmentBundle:
        raise TypeError
    return result


def _fixture_profiles(factory: object) -> tuple[SemanticTaskProfile, SemanticTaskProfile]:
    if not callable(factory):
        raise TypeError
    result: object = factory()
    if (
        not _is_object_tuple(result)
        or len(result) != 2
        or type(result[0]) is not SemanticTaskProfile
        or type(result[1]) is not SemanticTaskProfile
    ):
        raise TypeError
    return result[0], result[1]


def _fixture_pair(
    factory: object,
    bundle: HKCaseJudgmentBundle,
    profiles: tuple[SemanticTaskProfile, SemanticTaskProfile],
) -> HKCasePropositionRequestPair:
    if not callable(factory):
        raise TypeError
    result: object = factory(bundle, profiles)
    if type(result) is not HKCasePropositionRequestPair:
        raise TypeError
    return result


def _fixture_decision(
    factory: object, pair: HKCasePropositionRequestPair
) -> HKCaseAdmittedSemanticDecision:
    if not callable(factory):
        raise TypeError
    result: object = factory(pair)
    if type(result) is not HKCaseAdmittedSemanticDecision:
        raise TypeError
    return result


def test_dissent_treatment_does_not_retire_majority_proposition() -> None:
    """Treating a dissent as operative authority would wrongly retire the majority."""
    propositions = (
        HKCaseAuthorityProposition(
            proposition_id="earlier_proposition",
            judgment_id="earlier_judgment",
            court_id="CFI",
            decision_date="2020-01-01",
            opinion_id="majority_opinion",
            opinion_is_operative=True,
            admitted=True,
            evidence_complete=True,
        ),
        HKCaseAuthorityProposition(
            proposition_id="later_proposition",
            judgment_id="later_judgment",
            court_id="CFA",
            decision_date="2024-01-02",
            opinion_id="dissent_opinion",
            opinion_is_operative=False,
            admitted=True,
            evidence_complete=True,
        ),
    )
    edges = (
        HKCaseTreatmentEdge(
            later_proposition_id="later_proposition",
            earlier_proposition_id="earlier_proposition",
            treatment=HKCaseTreatment.OVERRULED,
            opinion_id="dissent_opinion",
            support_paragraph_refs=("para_17",),
            effective_date="2024-01-02",
            authority_consequence=HKCaseTreatmentAuthorityConsequence.RETIRE,
            decision_id="treatment_decision",
        ),
    )

    graph = build_hk_case_authority_graph(propositions, edges, (), "2024-12-31")

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED
    assert graph.quarantined_edge_ids == ("treatment_decision",)


def test_public_task3_admission_cannot_claim_current_without_all_authorities() -> None:
    """Proposition admission alone is not treatment, finality, or appellate authority."""
    helpers: object = runpy.run_path(str(Path(__file__).with_name("test_hk_case_proposition.py")))
    bundle = _fixture_bundle(_fixture_helper(helpers, "_bundle"))
    profiles = _fixture_profiles(_fixture_helper(helpers, "_profiles"))
    pair = _fixture_pair(_fixture_helper(helpers, "_build"), bundle, profiles)
    decision = _fixture_decision(_fixture_helper(helpers, "_admitted"), pair)
    admission = admit_hk_case_propositions(pair, decision)
    propositions = build_hk_case_authority_propositions(admission)

    graph = build_hk_case_authority_graph(propositions, (), (), "2026-08-01")

    assert admission.disposition.value == "COMPLETE_PROPOSITIONS"
    assert len(propositions) == 1
    assert graph.quarantined_edge_ids == ()
    assert all(
        selection.state is HKCaseAuthoritySelectionState.QUARANTINED
        and selection.authority_note_required is False
        and selection.state
        not in {HKCaseAuthoritySelectionState.CURRENT, HKCaseAuthoritySelectionState.RETIRED}
        for selection in graph.selections
    )


def test_direct_constructed_overruling_edge_cannot_retire_a_proposition() -> None:
    """Removing factory-issuance checking would let caller-controlled fields retire authority."""
    graph = build_hk_case_authority_graph(
        _operative_propositions(), (_retiring_edge(),), (), "2024-12-31"
    )

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED


def test_followed_label_cannot_be_relabelled_as_retirement() -> None:
    """A missing rule trace must reject an invalid label/effect pair."""
    followed = HKCaseTreatmentEdge(
        later_proposition_id="later_proposition",
        earlier_proposition_id="earlier_proposition",
        treatment=HKCaseTreatment.FOLLOWED,
        opinion_id="majority_opinion",
        support_paragraph_refs=("para_17",),
        effective_date="2024-01-02",
        authority_consequence=HKCaseTreatmentAuthorityConsequence.RETIRE,
        decision_id="followed_decision",
    )

    graph = build_hk_case_authority_graph(_operative_propositions(), (followed,), (), "2024-12-31")

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED


def test_proposition_after_cutoff_is_quarantined_without_an_edge() -> None:
    """Ignoring proposition dates would report future authority as current at an earlier cutoff."""
    future = HKCaseAuthorityProposition(
        proposition_id="future_proposition",
        judgment_id="future_judgment",
        court_id="CFA",
        decision_date="2025-01-01",
        opinion_id="majority_opinion",
        opinion_is_operative=True,
        admitted=True,
        evidence_complete=True,
    )

    graph = build_hk_case_authority_graph((future,), (), (), "2024-12-31")

    assert graph.selection("future_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED


def test_temporally_backward_retirement_is_quarantined() -> None:
    """Reversing temporal direction would let an older judgment rewrite a later authority."""
    propositions = _operative_propositions(earlier_date="2024-01-02", later_date="2020-01-01")

    graph = build_hk_case_authority_graph(propositions, (_retiring_edge(),), (), "2024-12-31")

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED
    assert graph.quarantined_edge_ids == ("treatment_decision",)


def test_lower_court_cannot_retire_higher_court_proposition() -> None:
    """Removing court hierarchy checking would let a CFI result overrule a CFA proposition."""
    propositions = _operative_propositions(earlier_court="CFA", later_court="CFI")

    graph = build_hk_case_authority_graph(propositions, (_retiring_edge(),), (), "2024-12-31")

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED


def test_duplicate_treatment_decision_is_quarantined() -> None:
    """Accepting duplicated decision identities could double-apply one legal conclusion."""
    graph = build_hk_case_authority_graph(
        _operative_propositions(),
        (_retiring_edge(), _retiring_edge()),
        (),
        "2024-12-31",
    )

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED
    assert graph.quarantined_edge_ids == ("treatment_decision",)


def test_conflicting_treatment_consequences_are_quarantined() -> None:
    """Ignoring conflicting accepted results would invent a current-authority conclusion."""
    no_change = HKCaseTreatmentEdge(
        later_proposition_id="later_proposition",
        earlier_proposition_id="earlier_proposition",
        treatment=HKCaseTreatment.FOLLOWED,
        opinion_id="majority_opinion",
        support_paragraph_refs=("para_18",),
        effective_date="2024-01-02",
        authority_consequence=HKCaseTreatmentAuthorityConsequence.NO_CHANGE,
        decision_id="later_treatment_decision",
    )

    graph = build_hk_case_authority_graph(
        _operative_propositions(), (_retiring_edge(), no_change), (), "2024-12-31"
    )

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED


def test_correction_lineage_cycle_is_quarantined() -> None:
    """Accepting a correction cycle would erase which reasons remain legally effective."""
    correction = HKCaseAuthorityCorrection(
        correction_id="correction_one",
        superseded_judgment_id="later_judgment",
        replacement_judgment_id="later_judgment",
        admitted=True,
        evidence_complete=True,
    )

    graph = build_hk_case_authority_graph(
        _operative_propositions(), (_retiring_edge(),), (correction,), "2024-12-31"
    )

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED


def test_direct_correction_cannot_reselect_without_issued_cutoff_and_finality_facts() -> None:
    """Caller-created correction facts need an admitted rule trace before reinstatement."""
    propositions = (
        *_operative_propositions(),
        HKCaseAuthorityProposition(
            proposition_id="replacement_proposition",
            judgment_id="replacement_judgment",
            court_id="CFA",
            decision_date="2024-06-01",
            opinion_id="replacement_opinion",
            opinion_is_operative=True,
            admitted=True,
            evidence_complete=True,
        ),
    )
    correction = HKCaseAuthorityCorrection(
        correction_id="correction_one",
        superseded_judgment_id="later_judgment",
        replacement_judgment_id="replacement_judgment",
        admitted=True,
        evidence_complete=True,
    )

    graph = build_hk_case_authority_graph(
        propositions, (_retiring_edge(),), (correction,), "2024-12-31"
    )

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED


def test_invalid_dissent_later_fact_cannot_bypass_complete_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-operative shortcut must not leave an earlier issued proposition current."""
    earlier, later = _operative_propositions()
    object.__setattr__(later, "opinion_is_operative", False)
    object.__setattr__(later, "opinion_role", None)

    def only_earlier_is_issued(proposition: HKCaseAuthorityProposition) -> bool:
        return proposition is earlier

    monkeypatch.setattr(
        graph_module,
        "_is_issued_proposition",
        only_earlier_is_issued,
    )
    edge = _retiring_edge()
    object.__setattr__(edge, "opinion_id", "dissent_opinion")

    graph = build_hk_case_authority_graph((earlier, later), (edge,), (), "2024-12-31")

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED
    assert graph.quarantined_edge_ids == ("treatment_decision",)


def test_issued_proposition_post_return_mutation_cannot_invent_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The issuance registry must bind the derived proposition's complete original fields."""
    admitted = HKCaseAdmittedProposition(
        proposition_id="earlier_proposition",
        candidate_id="candidate_fixture",
        proposition_text="Fixture proposition.",
        text_mode="FAITHFUL_DISTILLATION",
        court_id="CFA",
        opinion_id="majority_opinion",
        judge_names=("Judge Fixture",),
        qualification_texts=(),
        exception_texts=(),
        support_paragraph_refs=("majority:para_1",),
        support_fingerprint="sha256:" + "b" * 64,
        authority_role=HKCaseOpinionRole.LEAD,
        legal_issue="Fixture issue",
        material_context=None,
        result_context="Fixture result",
        quotation_paragraph_refs=("majority:para_1",),
        evidence_links=(HKCaseAdmittedEvidenceLink(HKCaseEvidenceRole.ANSWER, "majority:para_1"),),
    )

    def retained_admission_replays(_: HKCasePropositionAdmissionResult) -> None:
        return None

    monkeypatch.setattr(
        HKCasePropositionAdmissionResult, "__post_init__", retained_admission_replays
    )
    admission = object.__new__(HKCasePropositionAdmissionResult)
    object.__setattr__(admission, "propositions", (admitted,))
    object.__setattr__(admission, "admission_projection", b"retained-admission")
    object.__setattr__(admission, "admission_fingerprint", "sha256:" + "a" * 64)
    object.__setattr__(
        admission,
        "request_pair",
        SimpleNamespace(
            decision=SimpleNamespace(
                semantic_task=SimpleNamespace(
                    judicial_decision_id="earlier_judgment",
                    decision_date="2020-01-01",
                )
            )
        ),
    )
    (proposition,) = build_hk_case_authority_propositions(admission)
    object.__setattr__(proposition, "proposition_id", "invented_proposition")

    graph = build_hk_case_authority_graph((proposition,), (), (), "2024-12-31")

    assert graph.selection("invented_proposition").state is (
        HKCaseAuthoritySelectionState.QUARANTINED
    )


def test_graph_normalizes_unhashable_proposition_and_correction_facts() -> None:
    """Nested hostile values must close at the graph boundary instead of leaking TypeError."""
    malformed_proposition = _operative_propositions()[0]
    object.__setattr__(malformed_proposition, "proposition_id", [])
    with pytest.raises(HKCaseAuthorityGraphError, match="HK_CASE_AUTHORITY_GRAPH_INVALID"):
        build_hk_case_authority_graph((malformed_proposition,), (), (), "2024-12-31")

    malformed_correction = HKCaseAuthorityCorrection(
        correction_id="correction_before_mutation",
        superseded_judgment_id="earlier_judgment",
        replacement_judgment_id="later_judgment",
        admitted=True,
        evidence_complete=True,
    )
    object.__setattr__(malformed_correction, "correction_id", [])
    with pytest.raises(HKCaseAuthorityGraphError, match="HK_CASE_AUTHORITY_GRAPH_INVALID"):
        build_hk_case_authority_graph(
            _operative_propositions(), (), (malformed_correction,), "2024-12-31"
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("treatment", object()),
        ("effective_date", "2024-W01-2"),
        ("support_paragraph_refs", (["bad"],)),
    ],
)
def test_malformed_edge_facts_are_quarantined_before_projection(field: str, value: object) -> None:
    """An identifiable bad edge must quarantine its target before nested projection."""
    malformed = _retiring_edge()
    object.__setattr__(malformed, field, value)

    graph = build_hk_case_authority_graph(_operative_propositions(), (malformed,), (), "2024-12-31")

    assert graph.selection("earlier_proposition").state is HKCaseAuthoritySelectionState.QUARANTINED
    assert graph.quarantined_edge_ids == ("treatment_decision",)


def test_graph_preserves_process_control_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordinary graph error normalizer must leave process control observable."""

    def interrupt(_: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(graph_module, "_validated_proposition_facts", interrupt)
    with pytest.raises(KeyboardInterrupt):
        build_hk_case_authority_graph(_operative_propositions(), (), (), "2024-12-31")


def test_selection_and_graph_cannot_be_directly_forged_as_retired() -> None:
    """Only graph construction may issue a terminal retirement selection."""
    with pytest.raises(TypeError, match="HK_CASE_AUTHORITY_SELECTION_FACTORY_REQUIRED"):
        HKCaseAuthoritySelection(
            proposition_id="earlier_proposition",
            state=HKCaseAuthoritySelectionState.RETIRED,
            authority_note_required=False,
        )

    with pytest.raises(TypeError, match="HK_CASE_AUTHORITY_GRAPH_FACTORY_REQUIRED"):
        HKCaseAuthorityGraph(selections=(), quarantined_edge_ids=())


@pytest.mark.parametrize(
    "transfer",
    [copy.copy, copy.deepcopy, pickle.dumps],
)
@pytest.mark.parametrize("output_kind", ["selection", "graph"])
def test_graph_factory_outputs_are_nontransferable(
    transfer: Callable[[object], object], output_kind: str
) -> None:
    """Restart and copying must rebuild the graph from admitted upstream inputs."""
    graph = build_hk_case_authority_graph(_operative_propositions(), (), (), "2024-12-31")
    value: object = graph.selection("earlier_proposition") if output_kind == "selection" else graph

    with pytest.raises(TypeError, match=r"HK_CASE_AUTHORITY_(SELECTION|GRAPH)_NOT_TRANSFERABLE"):
        transfer(value)


def test_graph_replay_rejects_post_return_retired_mutation() -> None:
    """A caller cannot mutate an issued selection into RETIRED authority."""
    graph = build_hk_case_authority_graph(_operative_propositions(), (), (), "2024-12-31")
    selection = graph.selection("earlier_proposition")
    assert replay_hk_case_authority_selection(selection) is selection
    assert replay_hk_case_authority_graph(graph) is graph
    object.__setattr__(selection, "state", HKCaseAuthoritySelectionState.RETIRED)

    with pytest.raises(HKCaseAuthorityGraphError, match="HK_CASE_AUTHORITY_GRAPH_INVALID"):
        replay_hk_case_authority_selection(selection)
    with pytest.raises(HKCaseAuthorityGraphError, match="HK_CASE_AUTHORITY_GRAPH_INVALID"):
        replay_hk_case_authority_graph(graph)


def _operative_propositions(
    *,
    earlier_date: str = "2020-01-01",
    later_date: str = "2024-01-02",
    earlier_court: str = "CFI",
    later_court: str = "CFA",
) -> tuple[HKCaseAuthorityProposition, HKCaseAuthorityProposition]:
    """Return two admitted operative propositions with independently chosen authority facts."""
    return (
        HKCaseAuthorityProposition(
            proposition_id="earlier_proposition",
            judgment_id="earlier_judgment",
            court_id=earlier_court,
            decision_date=earlier_date,
            opinion_id="majority_opinion",
            opinion_is_operative=True,
            admitted=True,
            evidence_complete=True,
        ),
        HKCaseAuthorityProposition(
            proposition_id="later_proposition",
            judgment_id="later_judgment",
            court_id=later_court,
            decision_date=later_date,
            opinion_id="majority_opinion",
            opinion_is_operative=True,
            admitted=True,
            evidence_complete=True,
        ),
    )


def _retiring_edge() -> HKCaseTreatmentEdge:
    """Return one otherwise valid operative Legal-Desk retirement decision."""
    return HKCaseTreatmentEdge(
        later_proposition_id="later_proposition",
        earlier_proposition_id="earlier_proposition",
        treatment=HKCaseTreatment.OVERRULED,
        opinion_id="majority_opinion",
        support_paragraph_refs=("para_17",),
        effective_date="2024-01-02",
        authority_consequence=HKCaseTreatmentAuthorityConsequence.RETIRE,
        decision_id="treatment_decision",
    )
