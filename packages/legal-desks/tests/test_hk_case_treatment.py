"""Contract tests for deterministic Hong Kong later-treatment classification."""

from __future__ import annotations

import copy
import pickle
from collections.abc import Callable

import asklegal_legal_desks.hk_case_treatment as treatment_module
import pytest
from asklegal_legal_desks.hk_case_treatment import (
    HKCaseTreatment,
    HKCaseTreatmentAuthorityConsequence,
    HKCaseTreatmentCandidate,
    HKCaseTreatmentClassification,
    HKCaseTreatmentClassificationError,
    HKCaseTreatmentDecision,
    HKCaseTreatmentEdge,
    HKCaseTreatmentOpinionAuthority,
    classify_hk_case_treatment,
    is_hk_case_treatment_candidate_complete,
    replay_hk_case_treatment_classification,
)


def _candidate(*, bare_citation: bool = False) -> HKCaseTreatmentCandidate:
    """Return an otherwise complete, evidence-bound treatment proposal."""
    return HKCaseTreatmentCandidate(
        candidate_id="treatment_candidate",
        later_proposition_id="later_proposition",
        earlier_proposition_id="earlier_proposition",
        opinion_id="majority_opinion",
        opinion_authority=HKCaseTreatmentOpinionAuthority.OPERATIVE,
        support_paragraph_refs=("para_17",),
        effective_date="2024-01-02",
        whole_judgment_evidence_complete=True,
        candidate_evidence_complete=True,
        bare_citation=bare_citation,
    )


def _admitted_decision() -> HKCaseTreatmentDecision:
    """Return a Legal-Desk decision that explicitly authorizes retirement."""
    return HKCaseTreatmentDecision(
        decision_id="treatment_decision",
        candidate_id="treatment_candidate",
        admitted=True,
        treatment=HKCaseTreatment.OVERRULED,
        authority_consequence=HKCaseTreatmentAuthorityConsequence.RETIRE,
        evidence_complete=True,
    )


def test_bare_citation_does_not_create_treatment_edge() -> None:
    """Removing the bare-citation gate would incorrectly create legal effect."""
    result = classify_hk_case_treatment((_candidate(bare_citation=True),), (_admitted_decision(),))

    assert result.edges == ()
    assert result.quarantined_candidate_ids == ("treatment_candidate",)


def test_incomplete_whole_judgment_evidence_cannot_create_treatment_edge() -> None:
    """Removing whole-judgment evidence checking would accept a partial legal reading."""
    incomplete = HKCaseTreatmentCandidate(
        candidate_id="treatment_candidate",
        later_proposition_id="later_proposition",
        earlier_proposition_id="earlier_proposition",
        opinion_id="majority_opinion",
        opinion_authority=HKCaseTreatmentOpinionAuthority.OPERATIVE,
        support_paragraph_refs=("para_17",),
        effective_date="2024-01-02",
        whole_judgment_evidence_complete=False,
        candidate_evidence_complete=True,
        bare_citation=False,
    )

    result = classify_hk_case_treatment((incomplete,), (_admitted_decision(),))

    assert result.edges == ()
    assert result.quarantined_candidate_ids == ("treatment_candidate",)


def test_unadmitted_decision_cannot_create_treatment_edge() -> None:
    """Treating a proposal as a Legal-Desk decision would bypass the authority gate."""
    unadmitted = HKCaseTreatmentDecision(
        decision_id="treatment_decision",
        candidate_id="treatment_candidate",
        admitted=False,
        treatment=HKCaseTreatment.OVERRULED,
        authority_consequence=HKCaseTreatmentAuthorityConsequence.RETIRE,
        evidence_complete=True,
    )

    result = classify_hk_case_treatment((_candidate(),), (unadmitted,))

    assert result.edges == ()
    assert result.quarantined_candidate_ids == ("treatment_candidate",)


def test_public_classification_has_no_relationship_or_effect_without_rule_trace() -> None:
    """Caller facts cannot stand in for the missing admitted treatment RuleTrace."""
    result = classify_hk_case_treatment((_candidate(),), (_admitted_decision(),))

    assert result.edges == ()
    assert result.quarantined_candidate_ids == ("treatment_candidate",)


@pytest.mark.parametrize("effective_date", ["20240102", "2024-W01-2"])
def test_treatment_candidate_date_requires_exact_calendar_text(effective_date: str) -> None:
    """Python's compact and ISO-week extensions are not the Task 4 date contract."""
    candidate = _candidate()
    object.__setattr__(candidate, "effective_date", effective_date)

    assert is_hk_case_treatment_candidate_complete(candidate) is False


@pytest.mark.parametrize(
    "malformed",
    [
        object(),
        HKCaseTreatmentCandidate(
            candidate_id="candidate_valid_before_mutation",
            later_proposition_id="later_proposition",
            earlier_proposition_id="earlier_proposition",
            opinion_id="majority_opinion",
            opinion_authority=HKCaseTreatmentOpinionAuthority.OPERATIVE,
            support_paragraph_refs=("para_17",),
            effective_date="2024-01-02",
            whole_judgment_evidence_complete=True,
            candidate_evidence_complete=True,
            bare_citation=False,
        ),
    ],
)
def test_classification_normalizes_foreign_and_unhashable_candidate_facts(
    malformed: object,
) -> None:
    """Malformed nested facts must not leak AttributeError or TypeError."""
    if type(malformed) is HKCaseTreatmentCandidate:
        object.__setattr__(malformed, "candidate_id", [])

    classifier: Callable[..., HKCaseTreatmentClassification] = classify_hk_case_treatment
    with pytest.raises(ValueError, match="HK_CASE_TREATMENT_CLASSIFICATION_INVALID"):
        classifier((malformed,), ())


def test_classification_preserves_process_control_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ordinary-error normalization must not swallow cancellation or process control."""

    def interrupt(_: object) -> tuple[str, ...]:
        raise KeyboardInterrupt

    monkeypatch.setattr(treatment_module, "_validated_candidate_ids", interrupt)
    with pytest.raises(KeyboardInterrupt):
        classify_hk_case_treatment((_candidate(),), ())


def test_classification_cannot_be_directly_forged_with_retirement() -> None:
    """Only the classifier may issue a terminal classification."""
    forged_edge = HKCaseTreatmentEdge(
        later_proposition_id="later_proposition",
        earlier_proposition_id="earlier_proposition",
        treatment=HKCaseTreatment.OVERRULED,
        opinion_id="majority_opinion",
        support_paragraph_refs=("para_17",),
        effective_date="2024-01-02",
        authority_consequence=HKCaseTreatmentAuthorityConsequence.RETIRE,
        decision_id="forged_decision",
    )

    with pytest.raises(TypeError, match="HK_CASE_TREATMENT_CLASSIFICATION_FACTORY_REQUIRED"):
        HKCaseTreatmentClassification((forged_edge,), ())


@pytest.mark.parametrize(
    "transfer",
    [copy.copy, copy.deepcopy, pickle.dumps],
)
def test_classification_factory_issuance_is_nontransferable(
    transfer: Callable[[object], object],
) -> None:
    """Restart or copying must rerun classification rather than transfer authority."""
    result = classify_hk_case_treatment((_candidate(),), (_admitted_decision(),))

    with pytest.raises(TypeError, match="HK_CASE_TREATMENT_CLASSIFICATION_NOT_TRANSFERABLE"):
        transfer(result)


def test_classification_replay_rejects_post_return_projection_mutation() -> None:
    """Retained output fields cannot be mutated into a different terminal result."""
    result = classify_hk_case_treatment((_candidate(),), (_admitted_decision(),))
    assert replay_hk_case_treatment_classification(result) is result
    object.__setattr__(result, "quarantined_candidate_ids", ())

    with pytest.raises(
        HKCaseTreatmentClassificationError,
        match="HK_CASE_TREATMENT_CLASSIFICATION_INVALID",
    ):
        replay_hk_case_treatment_classification(result)
