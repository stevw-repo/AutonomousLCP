"""Source-neutral HKEX component-inventory accounting conformance."""

from __future__ import annotations

from dataclasses import replace

import pytest
from asklegal_legal_desks import (
    HKEX_GEM_SCOPE_ID,
    HKEX_MAIN_SCOPE_ID,
    HKEX_REGULATORY_SOURCE_IDS,
    HKEX_REGULATORY_SOURCE_UNIVERSE,
    HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
    HKEXApplicabilityBranch,
    HKEXBranchState,
    HKEXComponentState,
    HKEXInventoryCycle,
    HKEXInventoryError,
    HKEXInventoryErrorCode,
    HKEXMaterialDisposition,
    HKEXMembership,
    HKEXObservedSourceEntry,
    HKEXProcessingOutcome,
    HKEXRuleComponent,
    HKEXSourceObservation,
    account_hkex_component_inventory,
    derive_hkex_component_state,
)

SCOPES = (HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID)


def _branches(*states: HKEXBranchState) -> tuple[HKEXApplicabilityBranch, ...]:
    return tuple(
        HKEXApplicabilityBranch(
            branch_id=f"branch-{index}",
            state=state,
            evidence_refs=(f"evidence-branch-{index}",),
        )
        for index, state in enumerate(states, start=1)
    )


def _observations() -> tuple[HKEXSourceObservation, ...]:
    return tuple(
        HKEXSourceObservation(
            observation_id=f"observation-{index}",
            source_id=source_id,
            scope_ids=SCOPES,
            complete=True,
            evidence_refs=(f"evidence-observation-{index}",),
        )
        for index, source_id in enumerate(HKEX_REGULATORY_SOURCE_IDS, start=1)
    )


def _entry(
    entry_id: str,
    source_id: str,
    scope_id: str,
    component_id: str,
) -> HKEXObservedSourceEntry:
    return HKEXObservedSourceEntry(
        entry_id=entry_id,
        source_id=source_id,
        scope_ids=(scope_id,),
        membership=HKEXMembership.RULE_COMPONENT,
        owner_scope_id=scope_id,
        component_ids=(component_id,),
        evidence_refs=(f"evidence-{entry_id}",),
    )


def _component(
    component_id: str,
    scope_id: str,
    entry_id: str,
    branch_state: HKEXBranchState,
    processing: HKEXProcessingOutcome = HKEXProcessingOutcome.PASS,
) -> HKEXRuleComponent:
    branches = _branches(branch_state)
    state = derive_hkex_component_state(branches)
    if processing is not HKEXProcessingOutcome.PASS:
        disposition = HKEXMaterialDisposition.QUARANTINE
    elif state in {HKEXComponentState.CURRENT, HKEXComponentState.TRANSITIONAL_CURRENT}:
        disposition = HKEXMaterialDisposition.SEARCHABLE_CURRENT_RULE_COMPONENT
    elif state in {
        HKEXComponentState.FUTURE_FIXED_DATE,
        HKEXComponentState.FUTURE_CONDITIONAL,
    }:
        disposition = HKEXMaterialDisposition.REGULATORY_WAITING_ROOM
    elif state in {HKEXComponentState.SUPERSEDED, HKEXComponentState.WITHDRAWN}:
        disposition = HKEXMaterialDisposition.HISTORICAL
    else:
        disposition = HKEXMaterialDisposition.QUARANTINE
    return HKEXRuleComponent(
        component_id=component_id,
        scope_id=scope_id,
        source_entry_ids=(entry_id,),
        parent_component_id=None,
        structural_order=0,
        branches=branches,
        component_state=state,
        disposition=disposition,
        processing_outcome=processing,
        evidence_refs=(f"evidence-{component_id}",),
    )


def _complete_cycle() -> HKEXInventoryCycle:
    main_entry = _entry(
        "entry-main-current",
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        HKEX_MAIN_SCOPE_ID,
        "component-main-current",
    )
    gem_entry = _entry(
        "entry-gem-future",
        "HK-REG-HKEX-RULE-UPDATES",
        HKEX_GEM_SCOPE_ID,
        "component-gem-future",
    )
    return HKEXInventoryCycle(
        cutoff="2026-08-24T00:00:00Z",
        observations=_observations(),
        entries=(main_entry, gem_entry),
        components=(
            _component(
                "component-main-current",
                HKEX_MAIN_SCOPE_ID,
                main_entry.entry_id,
                HKEXBranchState.CURRENT,
            ),
            _component(
                "component-gem-future",
                HKEX_GEM_SCOPE_ID,
                gem_entry.entry_id,
                HKEXBranchState.FUTURE_FIXED_DATE,
            ),
        ),
    )


def test_five_role_source_universe_is_closed_and_sorted() -> None:
    assert tuple(source.source_id for source in HKEX_REGULATORY_SOURCE_UNIVERSE) == (
        HKEX_REGULATORY_SOURCE_IDS
    )
    assert len(HKEX_REGULATORY_SOURCE_IDS) == 5
    assert HKEX_RULEBOOK_CATALOGUE_SOURCE_ID in HKEX_REGULATORY_SOURCE_IDS


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ((HKEXBranchState.CURRENT,), HKEXComponentState.CURRENT),
        (
            (HKEXBranchState.CURRENT, HKEXBranchState.FUTURE_FIXED_DATE),
            HKEXComponentState.CURRENT,
        ),
        (
            (HKEXBranchState.TRANSITIONAL_CURRENT,),
            HKEXComponentState.TRANSITIONAL_CURRENT,
        ),
        (
            (HKEXBranchState.FUTURE_CONDITIONAL,),
            HKEXComponentState.FUTURE_CONDITIONAL,
        ),
        ((HKEXBranchState.SUPERSEDED,), HKEXComponentState.SUPERSEDED),
        ((HKEXBranchState.WITHDRAWN,), HKEXComponentState.WITHDRAWN),
        (
            (HKEXBranchState.FUTURE_FIXED_DATE, HKEXBranchState.FUTURE_CONDITIONAL),
            HKEXComponentState.UNKNOWN,
        ),
        (
            (HKEXBranchState.CURRENT, HKEXBranchState.UNKNOWN),
            HKEXComponentState.UNKNOWN,
        ),
    ],
)
def test_component_summary_preserves_branch_meaning(
    states: tuple[HKEXBranchState, ...], expected: HKEXComponentState
) -> None:
    assert derive_hkex_component_state(_branches(*states)) is expected


def test_complete_inventory_is_candidate_ready_but_never_claims_serving_ready() -> None:
    results = account_hkex_component_inventory(_complete_cycle())

    assert tuple(result.scope_id for result in results) == SCOPES
    assert all(result.source_observations_complete for result in results)
    assert all(result.source_entry_accounting_complete for result in results)
    assert all(result.component_ownership_structure_complete for result in results)
    assert all(result.current_state_accounting_complete for result in results)
    assert all(result.inventory_candidate_ready for result in results)
    assert all(not result.serving_ready for result in results)
    assert {result.serving_blocker for result in results} == {
        "ENGLISH_RECORD_TRACEABILITY_AND_RELEASE_LAYER_NOT_EVALUATED"
    }


def test_unresolved_membership_blocks_only_its_declared_board() -> None:
    cycle = _complete_cycle()
    unresolved = HKEXObservedSourceEntry(
        entry_id="entry-main-unresolved",
        source_id=HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
        scope_ids=(HKEX_MAIN_SCOPE_ID,),
        membership=HKEXMembership.UNRESOLVED_MEMBERSHIP,
        owner_scope_id=None,
        component_ids=(),
        evidence_refs=("evidence-unresolved",),
    )
    results = account_hkex_component_inventory(replace(cycle, entries=(*cycle.entries, unresolved)))
    by_scope = {result.scope_id: result for result in results}

    assert by_scope[HKEX_GEM_SCOPE_ID].inventory_candidate_ready
    assert not by_scope[HKEX_MAIN_SCOPE_ID].inventory_candidate_ready
    assert by_scope[HKEX_MAIN_SCOPE_ID].blocking_entry_ids == (unresolved.entry_id,)


def test_board_bounded_source_failure_does_not_invalidate_other_board() -> None:
    cycle = _complete_cycle()
    source_id = "HK-REG-HKEX-REGULATORY-FORMS"
    retained = tuple(item for item in cycle.observations if item.source_id != source_id)
    split = (
        HKEXSourceObservation(
            observation_id="observation-forms-gem",
            source_id=source_id,
            scope_ids=(HKEX_GEM_SCOPE_ID,),
            complete=False,
            evidence_refs=("evidence-forms-gem",),
        ),
        HKEXSourceObservation(
            observation_id="observation-forms-main",
            source_id=source_id,
            scope_ids=(HKEX_MAIN_SCOPE_ID,),
            complete=True,
            evidence_refs=("evidence-forms-main",),
        ),
    )
    by_scope = {
        result.scope_id: result
        for result in account_hkex_component_inventory(
            replace(cycle, observations=(*retained, *split))
        )
    }

    assert not by_scope[HKEX_GEM_SCOPE_ID].source_observations_complete
    assert by_scope[HKEX_MAIN_SCOPE_ID].source_observations_complete


def test_catalogue_observation_cannot_hide_one_board() -> None:
    with pytest.raises(HKEXInventoryError) as caught:
        HKEXSourceObservation(
            observation_id="observation-catalogue-main-only",
            source_id=HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
            scope_ids=(HKEX_MAIN_SCOPE_ID,),
            complete=True,
            evidence_refs=("evidence-catalogue",),
        )
    assert caught.value.code is HKEXInventoryErrorCode.SOURCE


def test_duplicate_source_scope_observation_fails_closed() -> None:
    cycle = _complete_cycle()
    duplicate = replace(cycle.observations[0], observation_id="observation-duplicate")
    with pytest.raises(HKEXInventoryError) as caught:
        account_hkex_component_inventory(
            replace(cycle, observations=(*cycle.observations, duplicate))
        )
    assert caught.value.code is HKEXInventoryErrorCode.DUPLICATE


def test_non_rule_entry_cannot_own_a_component() -> None:
    with pytest.raises(HKEXInventoryError) as caught:
        replace(
            _complete_cycle().entries[0],
            membership=HKEXMembership.EXCLUDED_NON_RULE,
        )
    assert caught.value.code is HKEXInventoryErrorCode.ENTRY


def test_orphan_and_wrong_board_components_fail_closed() -> None:
    cycle = _complete_cycle()
    orphan = replace(cycle.components[0], component_id="component-orphan")
    with pytest.raises(HKEXInventoryError) as caught:
        account_hkex_component_inventory(replace(cycle, components=(orphan,)))
    assert caught.value.code in {
        HKEXInventoryErrorCode.ENTRY,
        HKEXInventoryErrorCode.COMPONENT,
    }

    wrong_board = replace(cycle.components[0], scope_id=HKEX_GEM_SCOPE_ID)
    with pytest.raises(HKEXInventoryError) as caught:
        account_hkex_component_inventory(
            replace(cycle, components=(wrong_board, cycle.components[1]))
        )
    assert caught.value.code is HKEXInventoryErrorCode.ENTRY


def test_structure_cycle_duplicate_position_and_disposition_drift_fail() -> None:
    cycle = _complete_cycle()
    entry = cycle.entries[0]
    parent = replace(
        cycle.components[0],
        parent_component_id="component-main-child",
    )
    child = replace(
        cycle.components[0],
        component_id="component-main-child",
        parent_component_id=parent.component_id,
        structural_order=1,
    )
    expanded_entry = replace(
        entry,
        component_ids=(parent.component_id, child.component_id),
    )
    parent = replace(parent, source_entry_ids=(expanded_entry.entry_id,))
    child = replace(child, source_entry_ids=(expanded_entry.entry_id,))
    with pytest.raises(HKEXInventoryError) as caught:
        account_hkex_component_inventory(
            replace(
                cycle,
                entries=(expanded_entry, cycle.entries[1]),
                components=(parent, child, cycle.components[1]),
            )
        )
    assert caught.value.code is HKEXInventoryErrorCode.STRUCTURE

    with pytest.raises(HKEXInventoryError) as caught:
        replace(
            cycle.components[0],
            disposition=HKEXMaterialDisposition.HISTORICAL,
        )
    assert caught.value.code is HKEXInventoryErrorCode.COMPONENT


def test_unknown_state_is_accounted_quarantine_not_repaired() -> None:
    cycle = _complete_cycle()
    unknown = _component(
        "component-main-unknown",
        HKEX_MAIN_SCOPE_ID,
        cycle.entries[0].entry_id,
        HKEXBranchState.UNKNOWN,
        processing=HKEXProcessingOutcome.QUARANTINE,
    )
    entry = replace(cycle.entries[0], component_ids=(unknown.component_id,))
    results = account_hkex_component_inventory(
        replace(cycle, entries=(entry, cycle.entries[1]), components=(unknown, cycle.components[1]))
    )
    main = next(result for result in results if result.scope_id == HKEX_MAIN_SCOPE_ID)

    assert main.current_state_accounting_complete
    assert main.blocking_component_ids == (unknown.component_id,)
    assert not main.inventory_candidate_ready
