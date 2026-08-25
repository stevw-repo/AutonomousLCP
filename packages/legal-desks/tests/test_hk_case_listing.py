"""ADR 0046/0048 Hong Kong judgment listing-accounting conformance."""

from __future__ import annotations

from dataclasses import replace

import pytest
from asklegal_legal_desks import (
    HK_CASE_COURT_REGISTRY_SOURCE_ID,
    HK_CASE_HKLII_DISCOVERY_SOURCE_ID,
    HK_CASE_JUDICIARY_JUDGMENT_SOURCE_ID,
    HK_CASE_LRS_INVENTORY_SOURCE_ID,
    HK_CASE_SCOPE_FAMILIES,
    HK_CASE_SOURCE_UNIVERSE,
    HKCaseArtifactClass,
    HKCaseArtifactRole,
    HKCaseCourtFamily,
    HKCaseDecisionDisposition,
    HKCaseDecisionOutcome,
    HKCaseListingCycle,
    HKCaseListingError,
    HKCaseListingErrorCode,
    HKCaseListingOutcome,
    HKCaseScopeBoundary,
    OfficialJudgmentListingEntry,
    account_hk_case_listing_cycle,
    freeze_hk_case_release_scope_registry,
    hk_case_release_scope_id,
)

CUTOFF = "2026-08-24T12:00:00+00:00"
EVIDENCE = ("art_listing_evidence",)


def test_case_source_universe_is_closed_and_keeps_discovery_noncontrolling() -> None:
    source_ids = tuple(item.source_id for item in HK_CASE_SOURCE_UNIVERSE)
    assert source_ids == tuple(sorted(source_ids))
    assert len(source_ids) == len(set(source_ids)) == 7
    by_id = {item.source_id: item for item in HK_CASE_SOURCE_UNIVERSE}
    assert by_id[HK_CASE_LRS_INVENTORY_SOURCE_ID].role == "CONTROLLING"
    assert by_id[HK_CASE_JUDICIARY_JUDGMENT_SOURCE_ID].permitted_use == (
        "ORIGINAL_WORDING_VERSION_LANGUAGE_AND_OPINION_EVIDENCE"
    )
    assert by_id[HK_CASE_COURT_REGISTRY_SOURCE_ID].completeness_rule == (
        "CANNOT_PROVE_COMPLETE_ONLINE_INVENTORY"
    )
    assert by_id[HK_CASE_HKLII_DISCOVERY_SOURCE_ID].role == "DISCOVERY"
    assert by_id[HK_CASE_HKLII_DISCOVERY_SOURCE_ID].outage_consequence == "NONBLOCKING"


def test_case_scope_families_are_complete_without_inventing_year_boundaries() -> None:
    families = tuple(item.court_family for item in HK_CASE_SCOPE_FAMILIES)
    assert frozenset(families) == frozenset(
        {
            HKCaseCourtFamily.CFA,
            HKCaseCourtFamily.CA,
            HKCaseCourtFamily.CFI,
            HKCaseCourtFamily.COMPETITION_TRIBUNAL,
            HKCaseCourtFamily.HISTORICAL_SUPERIOR,
            HKCaseCourtFamily.PRIVY_COUNCIL_HK,
        }
    )
    assert len(families) == len(set(families)) == 6
    assert all(
        item.historical_boundary_required is (not item.ordinary_current_scope)
        for item in HK_CASE_SCOPE_FAMILIES
    )


def _synthetic_boundaries() -> tuple[HKCaseScopeBoundary, ...]:
    evidence = ("art_synthetic_boundary_evidence",)
    return (
        HKCaseScopeBoundary(HKCaseCourtFamily.CA, 1997, 2026, evidence),
        HKCaseScopeBoundary(HKCaseCourtFamily.CFA, 1997, 2026, evidence),
        HKCaseScopeBoundary(HKCaseCourtFamily.CFI, 1997, 2026, evidence),
        HKCaseScopeBoundary(HKCaseCourtFamily.COMPETITION_TRIBUNAL, 2016, 2026, evidence),
        HKCaseScopeBoundary(HKCaseCourtFamily.PRIVY_COUNCIL_HK, 1844, 1997, evidence),
        HKCaseScopeBoundary(HKCaseCourtFamily.HISTORICAL_SUPERIOR, 1844, 1997, evidence),
    )


def test_complete_evidenced_family_boundaries_generate_every_court_year_scope() -> None:
    scopes = freeze_hk_case_release_scope_registry(_synthetic_boundaries(), cutoff_year=2026)
    assert len(scopes) == 409
    assert scopes[0].scope_id == "HK-CASE-CA-1997"
    assert scopes[-1].scope_id == "HK-CASE-HKSUPERIOR-1997"
    assert len({item.scope_id for item in scopes}) == len(scopes)
    assert all(item.boundary_evidence_refs for item in scopes)


@pytest.mark.parametrize(
    "boundaries",
    [
        _synthetic_boundaries()[:-1],
        (
            replace(_synthetic_boundaries()[0], last_year=2025),
            *_synthetic_boundaries()[1:],
        ),
        (
            *_synthetic_boundaries()[:4],
            replace(_synthetic_boundaries()[4], last_year=2026),
            _synthetic_boundaries()[5],
        ),
    ],
)
def test_scope_freeze_rejects_missing_stale_current_or_post_1997_historical_boundaries(
    boundaries: tuple[HKCaseScopeBoundary, ...],
) -> None:
    with pytest.raises(HKCaseListingError) as caught:
        freeze_hk_case_release_scope_registry(boundaries, cutoff_year=2026)
    assert caught.value.code is HKCaseListingErrorCode.SCOPE


def _entry() -> OfficialJudgmentListingEntry:
    return OfficialJudgmentListingEntry(
        listing_entry_id="jle_1",
        source_id=HK_CASE_LRS_INVENTORY_SOURCE_ID,
        observed_at="2026-08-24T11:00:00+00:00",
        cutoff=CUTOFF,
        court_family=HKCaseCourtFamily.CFA,
        artifact_class=HKCaseArtifactClass.JUDGMENT,
        decision_date="2025-07-01",
        release_scope_id=hk_case_release_scope_id(HKCaseCourtFamily.CFA, "2025-07-01"),
        artifact_role=HKCaseArtifactRole.ORIGINAL,
        outcome=HKCaseListingOutcome.ACQUIRED,
        decision_id="lit_decision_1",
        artifact_id="art_judgment_1",
        duplicate_of_listing_entry_id=None,
        reason_code=None,
        evidence_refs=EVIDENCE,
    )


def _disposition(
    *,
    decision_id: str = "lit_decision_1",
    outcome: HKCaseDecisionOutcome = HKCaseDecisionOutcome.PROPOSITIONS,
    count: int = 2,
    reason: str = "SUPPORTED_MATERIAL_PROPOSITIONS",
) -> HKCaseDecisionDisposition:
    return HKCaseDecisionDisposition(
        decision_id=decision_id,
        outcome=outcome,
        search_record_count=count,
        reason_code=reason,
        evidence_refs=("art_processing_evidence",),
    )


def _cycle(
    *entries: OfficialJudgmentListingEntry,
    dispositions: tuple[HKCaseDecisionDisposition, ...] = (_disposition(),),
) -> HKCaseListingCycle:
    return HKCaseListingCycle(
        observation_id="obs_hk_case_listing_1",
        cutoff=CUTOFF,
        due_source_ids=(HK_CASE_LRS_INVENTORY_SOURCE_ID,),
        completed_source_ids=(HK_CASE_LRS_INVENTORY_SOURCE_ID,),
        entries=entries or (_entry(),),
        decision_dispositions=dispositions,
    )


def test_complete_cycle_separates_inventory_evidence_and_search_counts() -> None:
    result = account_hk_case_listing_cycle(_cycle())
    assert result.inventory_accounting_complete
    assert result.evidence_coverage_complete
    assert result.processing_accounting_complete
    assert result.acquired_decision_count == 1
    assert result.zero_record_decision_count == 0
    assert result.one_record_decision_count == 0
    assert result.many_record_decision_count == 1
    assert result.search_record_count == 2
    assert result.coverage_gap_codes == ()
    assert result.release_eligible


def test_valid_zero_proposition_decision_remains_completely_accounted() -> None:
    disposition = _disposition(
        outcome=HKCaseDecisionOutcome.VALID_NO_MATERIAL_PROPOSITION,
        count=0,
        reason="VALID_NO_MATERIAL_PROPOSITION",
    )
    result = account_hk_case_listing_cycle(_cycle(dispositions=(disposition,)))
    assert result.zero_record_decision_count == 1
    assert result.search_record_count == 0
    assert result.release_eligible


def test_duplicate_and_translation_link_to_one_acquired_decision() -> None:
    duplicate = replace(
        _entry(),
        listing_entry_id="jle_2",
        outcome=HKCaseListingOutcome.DUPLICATE_OR_ALIAS,
        artifact_id=None,
        duplicate_of_listing_entry_id="jle_1",
    )
    translation = replace(
        _entry(),
        listing_entry_id="jle_3",
        outcome=HKCaseListingOutcome.TRANSLATION_ARTIFACT,
        artifact_id="art_translation_1",
        artifact_role=HKCaseArtifactRole.JUDICIARY_TRANSLATION,
    )
    result = account_hk_case_listing_cycle(_cycle(_entry(), duplicate, translation))
    assert result.listing_entry_count == 3
    assert result.acquired_decision_count == 1
    assert result.release_eligible


def test_excluded_body_is_visible_without_expanding_case_scope() -> None:
    excluded = replace(
        _entry(),
        listing_entry_id="jle_excluded",
        outcome=HKCaseListingOutcome.OUT_OF_SCOPE,
        decision_id=None,
        artifact_id=None,
        court_family=HKCaseCourtFamily.EXCLUDED_BODY,
        release_scope_id=None,
        reason_code="LOWER_BODY_OUTSIDE_ADR_0046",
    )
    result = account_hk_case_listing_cycle(_cycle(excluded, dispositions=()))
    assert result.listing_entry_count == 1
    assert result.acquired_decision_count == 0
    assert result.release_eligible


def test_unavailable_original_is_gap_not_zero_record_decision() -> None:
    unavailable = replace(
        _entry(),
        outcome=HKCaseListingOutcome.BLOCKED_UNAVAILABLE,
        artifact_id=None,
        reason_code="ORIGINATING_JUDGMENT_UNAVAILABLE",
    )
    result = account_hk_case_listing_cycle(_cycle(unavailable, dispositions=()))
    assert result.inventory_accounting_complete
    assert not result.evidence_coverage_complete
    assert result.zero_record_decision_count == 0
    assert result.coverage_gap_codes == ("ORIGINATING_JUDGMENT_UNAVAILABLE",)
    assert not result.release_eligible


def test_missing_processing_disposition_blocks_release() -> None:
    result = account_hk_case_listing_cycle(_cycle(dispositions=()))
    assert result.evidence_coverage_complete
    assert not result.processing_accounting_complete
    assert result.coverage_gap_codes == ("HK_CASE_DECISION_PROCESSING_MISSING:lit_decision_1",)
    assert not result.release_eligible


def test_incomplete_due_official_source_is_not_supported_no_change() -> None:
    cycle = replace(_cycle(), completed_source_ids=())
    result = account_hk_case_listing_cycle(cycle)
    assert not result.inventory_accounting_complete
    assert result.coverage_gap_codes == (
        f"HK_CASE_DUE_SOURCE_INCOMPLETE:{HK_CASE_LRS_INVENTORY_SOURCE_ID}",
    )
    assert not result.release_eligible


def test_hklii_cannot_be_due_completeness_source() -> None:
    cycle = replace(
        _cycle(),
        due_source_ids=(HK_CASE_HKLII_DISCOVERY_SOURCE_ID,),
        completed_source_ids=(HK_CASE_HKLII_DISCOVERY_SOURCE_ID,),
    )
    with pytest.raises(HKCaseListingError) as caught:
        account_hk_case_listing_cycle(cycle)
    assert caught.value.code is HKCaseListingErrorCode.SOURCE


def test_post_cutoff_listing_cannot_mutate_frozen_cycle() -> None:
    entry = replace(_entry(), observed_at="2026-08-24T13:00:00+00:00")
    with pytest.raises(HKCaseListingError) as caught:
        account_hk_case_listing_cycle(_cycle(entry))
    assert caught.value.code is HKCaseListingErrorCode.POST_CUTOFF


def test_scope_is_derived_from_issuing_court_and_decision_year() -> None:
    entry = replace(_entry(), release_scope_id="HK-CASE-CFA-2026")
    with pytest.raises(HKCaseListingError) as caught:
        account_hk_case_listing_cycle(_cycle(entry))
    assert caught.value.code is HKCaseListingErrorCode.SCOPE


def test_duplicate_must_resolve_to_acquired_entry_for_same_decision() -> None:
    duplicate = replace(
        _entry(),
        listing_entry_id="jle_2",
        outcome=HKCaseListingOutcome.DUPLICATE_OR_ALIAS,
        artifact_id=None,
        duplicate_of_listing_entry_id="missing",
    )
    with pytest.raises(HKCaseListingError) as caught:
        account_hk_case_listing_cycle(_cycle(_entry(), duplicate))
    assert caught.value.code is HKCaseListingErrorCode.OUTCOME
