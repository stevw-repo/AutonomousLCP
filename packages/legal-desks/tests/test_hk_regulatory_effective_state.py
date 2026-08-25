"""Source-neutral ADR 0071 applicability-branch conformance."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue
from asklegal_legal_desks import (
    HKEX_EFFECTIVE_STATE_RULE_ID,
    HKEX_GEM_SCOPE_ID,
    HKEXApplicabilityBranch,
    HKEXBranchBasis,
    HKEXBranchState,
    HKEXComponentState,
    HKEXConditionFact,
    HKEXConditionOperator,
    HKEXConditionState,
    HKEXCurrentProductReconciliation,
    HKEXEffectiveStateError,
    HKEXEffectiveStateErrorCode,
    HKEXEffectiveStateReason,
    HKEXEffectiveStateRequest,
    HKEXFinality,
    HKEXMaterialDisposition,
    HKEXProcessingOutcome,
    HKEXRetirementEvidence,
    HKEXServingChoice,
    HKEXSourceFailureImpact,
    HKEXStateUncertainty,
    HKEXTransitionState,
    decide_hkex_effective_state,
    derive_hkex_component_state,
    hkex_effective_state_request_from_document,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)

FINGERPRINT = f"sha256:{'a' * 64}"


def _condition(
    condition_id: str,
    state: HKEXConditionState,
) -> HKEXConditionFact:
    return HKEXConditionFact(
        condition_id=condition_id,
        registered_source_id=f"registered-source-{condition_id}",
        state=state,
        evidence_refs=(f"evidence-{condition_id}",),
    )


def _request(**changes: object) -> HKEXEffectiveStateRequest:
    request = HKEXEffectiveStateRequest(
        decision_id="decision-main-2.01-ordinary",
        branch_id="branch-main-2.01-ordinary",
        component_id="component-main-2.01",
        scope_id=HKEX_GEM_SCOPE_ID,
        legal_location_id="legal-location-main-2.01",
        cutoff="2026-08-24T00:00:00+08:00",
        update_part_id="update-153-part-a",
        update_source_ranges=("evidence-update-153#part-a",),
        current_product_ranges=("evidence-current-product#rule-2.01",),
        basis=HKEXBranchBasis.ORDINARY,
        finality=HKEXFinality.FINAL_PUBLICATION_APPROVAL_INFERRED,
        effective_at=None,
        condition_operator=None,
        conditions=(),
        transition_state=HKEXTransitionState.ORDINARY,
        applicability_context=None,
        retirement_evidence=HKEXRetirementEvidence.NONE,
        predecessor_branch_id=None,
        successor_branch_ids=(),
        current_product_reconciliation=HKEXCurrentProductReconciliation.MATCH,
        uncertainty_codes=(),
        source_failure_impact=HKEXSourceFailureImpact.NONE,
        source_failure_choice=HKEXServingChoice.NONE,
        source_rule_id=HKEX_EFFECTIVE_STATE_RULE_ID,
        evidence_refs=("evidence-current-product", "evidence-update-153"),
        evidence_fingerprint=FINGERPRINT,
    )
    return replace(request, **changes)


def _state(**changes: object) -> HKEXBranchState:
    return decide_hkex_effective_state(_request(**changes)).state


@pytest.mark.parametrize(
    "finality",
    [
        HKEXFinality.FINAL_PUBLICATION_APPROVAL_INFERRED,
        HKEXFinality.FINAL_DIRECT_APPROVAL_PROVED,
    ],
)
def test_ordinary_current_requires_accepted_finality_and_product_match(
    finality: HKEXFinality,
) -> None:
    result = decide_hkex_effective_state(_request(finality=finality))

    assert result.state is HKEXBranchState.CURRENT
    assert result.reason is HKEXEffectiveStateReason.CURRENT_PRODUCT_MATCHED
    assert result.disposition is HKEXMaterialDisposition.SEARCHABLE_CURRENT_RULE_COMPONENT
    assert result.processing_outcome is HKEXProcessingOutcome.PASS
    assert result.current_product_reconciled
    assert not result.search_record_authorized
    assert not result.serving_ready


@pytest.mark.parametrize(
    "finality",
    [
        HKEXFinality.CONSULTATION_OR_PROPOSAL,
        HKEXFinality.APPROVAL_PENDING,
        HKEXFinality.DIRECT_APPROVAL_REQUIRED_MISSING,
        HKEXFinality.CONFLICTING,
    ],
)
def test_nonfinal_or_unproved_approval_never_becomes_current(
    finality: HKEXFinality,
) -> None:
    result = decide_hkex_effective_state(_request(finality=finality))

    assert result.state is HKEXBranchState.UNKNOWN
    assert result.reason is HKEXEffectiveStateReason.FINAL_PUBLICATION_NOT_PROVED
    assert result.processing_outcome is HKEXProcessingOutcome.QUARANTINE


def test_fixed_date_uses_hong_kong_calendar_and_never_promotes_early() -> None:
    future = decide_hkex_effective_state(
        _request(
            basis=HKEXBranchBasis.FIXED_DATE,
            effective_at="2026-09-01",
            cutoff="2026-08-31T23:59:59+08:00",
            current_product_reconciliation=HKEXCurrentProductReconciliation.MATCH,
        )
    )
    current = decide_hkex_effective_state(
        _request(
            basis=HKEXBranchBasis.FIXED_DATE,
            effective_at="2026-09-01",
            cutoff="2026-09-01T00:00:00+08:00",
        )
    )

    assert future.state is HKEXBranchState.FUTURE_FIXED_DATE
    assert future.reason is HKEXEffectiveStateReason.FUTURE_FIXED_DATE_PENDING
    assert not future.current_product_reconciled
    assert current.state is HKEXBranchState.CURRENT


def test_one_update_can_split_across_several_fixed_dates() -> None:
    first = _state(
        basis=HKEXBranchBasis.FIXED_DATE,
        effective_at="2026-08-20",
        update_part_id="update-153-part-a",
    )
    second = _state(
        basis=HKEXBranchBasis.FIXED_DATE,
        effective_at="2026-09-01",
        update_part_id="update-153-part-b",
    )

    assert first is HKEXBranchState.CURRENT
    assert second is HKEXBranchState.FUTURE_FIXED_DATE


@pytest.mark.parametrize(
    ("reconciliation", "reason"),
    [
        (
            HKEXCurrentProductReconciliation.CONFLICT,
            HKEXEffectiveStateReason.CURRENT_PRODUCT_CONFLICT,
        ),
        (
            HKEXCurrentProductReconciliation.MISSING_STALE_OR_INCOMPLETE,
            HKEXEffectiveStateReason.CURRENT_PRODUCT_EVIDENCE_INCOMPLETE,
        ),
        (
            HKEXCurrentProductReconciliation.NOT_YET_REQUIRED,
            HKEXEffectiveStateReason.CURRENT_PRODUCT_EVIDENCE_INCOMPLETE,
        ),
    ],
)
def test_elapsed_date_cannot_use_clock_only_promotion(
    reconciliation: HKEXCurrentProductReconciliation,
    reason: HKEXEffectiveStateReason,
) -> None:
    result = decide_hkex_effective_state(
        _request(
            basis=HKEXBranchBasis.FIXED_DATE,
            effective_at="2026-08-20",
            current_product_reconciliation=reconciliation,
        )
    )

    assert result.state is HKEXBranchState.UNKNOWN
    assert result.reason is reason


def test_all_of_condition_activates_only_after_every_fact() -> None:
    common = {
        "basis": HKEXBranchBasis.CONDITIONAL,
        "condition_operator": HKEXConditionOperator.ALL_OF,
    }
    active = _state(
        **common,
        conditions=(
            _condition("legislation", HKEXConditionState.OCCURRED),
            _condition("exchange-notice", HKEXConditionState.OCCURRED),
        ),
    )
    future = _state(
        **common,
        conditions=(
            _condition("legislation", HKEXConditionState.NOT_OCCURRED_FRESH),
            _condition("exchange-notice", HKEXConditionState.UNRESOLVED),
        ),
    )
    unknown = _state(
        **common,
        conditions=(
            _condition("legislation", HKEXConditionState.OCCURRED),
            _condition("exchange-notice", HKEXConditionState.UNRESOLVED),
        ),
    )

    assert active is HKEXBranchState.CURRENT
    assert future is HKEXBranchState.FUTURE_CONDITIONAL
    assert unknown is HKEXBranchState.UNKNOWN


def test_any_of_condition_needs_every_negative_to_remain_future() -> None:
    common = {
        "basis": HKEXBranchBasis.CONDITIONAL,
        "condition_operator": HKEXConditionOperator.ANY_OF,
    }
    active = _state(
        **common,
        conditions=(
            _condition("route-a", HKEXConditionState.UNRESOLVED),
            _condition("route-b", HKEXConditionState.OCCURRED),
        ),
    )
    future = _state(
        **common,
        conditions=(
            _condition("route-a", HKEXConditionState.NOT_OCCURRED_FRESH),
            _condition("route-b", HKEXConditionState.NOT_OCCURRED_FRESH),
        ),
    )
    unknown = _state(
        **common,
        conditions=(
            _condition("route-a", HKEXConditionState.NOT_OCCURRED_FRESH),
            _condition("route-b", HKEXConditionState.UNRESOLVED),
        ),
    )

    assert active is HKEXBranchState.CURRENT
    assert future is HKEXBranchState.FUTURE_CONDITIONAL
    assert unknown is HKEXBranchState.UNKNOWN


def test_trigger_occurrence_still_requires_current_product_reconciliation() -> None:
    result = decide_hkex_effective_state(
        _request(
            basis=HKEXBranchBasis.CONDITIONAL,
            condition_operator=HKEXConditionOperator.ALL_OF,
            conditions=(_condition("trigger", HKEXConditionState.OCCURRED),),
            current_product_reconciliation=HKEXCurrentProductReconciliation.CONFLICT,
        )
    )

    assert result.state is HKEXBranchState.UNKNOWN
    assert result.reason is HKEXEffectiveStateReason.CURRENT_PRODUCT_CONFLICT


def test_concurrently_live_old_and_new_cohorts_stay_transitional() -> None:
    old = decide_hkex_effective_state(
        _request(
            branch_id="branch-old-cohort",
            transition_state=HKEXTransitionState.MATERIALLY_LIMITED_CURRENT,
            applicability_context="Transactions entered before 2026-08-01",
        )
    )
    new = decide_hkex_effective_state(
        _request(
            branch_id="branch-new-cohort",
            transition_state=HKEXTransitionState.MATERIALLY_LIMITED_CURRENT,
            applicability_context="Transactions entered on or after 2026-08-01",
        )
    )
    branches = tuple(
        HKEXApplicabilityBranch(
            branch_id=result.branch_id,
            state=result.state,
            evidence_refs=(result.evidence_fingerprint,),
        )
        for result in (old, new)
    )

    assert old.state is HKEXBranchState.TRANSITIONAL_CURRENT
    assert new.state is HKEXBranchState.TRANSITIONAL_CURRENT
    assert derive_hkex_component_state(branches) is HKEXComponentState.TRANSITIONAL_CURRENT


def test_partial_and_complete_successor_coverage_are_not_collapsed() -> None:
    partial = _state(
        retirement_evidence=HKEXRetirementEvidence.PARTIAL_SUCCESSOR,
        successor_branch_ids=("branch-successor",),
        applicability_context="Legacy cohort remains subject to old wording",
    )
    complete = _state(
        retirement_evidence=HKEXRetirementEvidence.COMPLETE_SUCCESSOR,
        successor_branch_ids=("branch-successor",),
        transition_state=HKEXTransitionState.PROVED_ENDED,
    )

    assert partial is HKEXBranchState.TRANSITIONAL_CURRENT
    assert complete is HKEXBranchState.SUPERSEDED


def test_withdrawal_requires_official_evidence_and_no_successor() -> None:
    withdrawn = _state(
        retirement_evidence=HKEXRetirementEvidence.OFFICIAL_WITHDRAWAL_NO_SUCCESSOR,
        transition_state=HKEXTransitionState.PROVED_ENDED,
    )
    disappeared = decide_hkex_effective_state(
        _request(retirement_evidence=HKEXRetirementEvidence.DISAPPEARANCE_ONLY)
    )

    assert withdrawn is HKEXBranchState.WITHDRAWN
    assert disappeared.state is HKEXBranchState.UNKNOWN
    assert disappeared.reason is HKEXEffectiveStateReason.RETIREMENT_EVIDENCE_INSUFFICIENT


@pytest.mark.parametrize("uncertainty", list(HKEXStateUncertainty))
def test_every_current_affecting_uncertainty_quarantines(
    uncertainty: HKEXStateUncertainty,
) -> None:
    result = decide_hkex_effective_state(_request(uncertainty_codes=(uncertainty,)))

    assert result.state is HKEXBranchState.UNKNOWN
    assert result.disposition is HKEXMaterialDisposition.QUARANTINE
    assert result.processing_outcome is HKEXProcessingOutcome.QUARANTINE


def test_optional_chinese_difference_is_nonblocking_until_it_signals_english_defect() -> None:
    harmless = _state()
    defect = _state(
        uncertainty_codes=(HKEXStateUncertainty.OPTIONAL_CHINESE_SIGNALS_ENGLISH_DEFECT,)
    )

    assert harmless is HKEXBranchState.CURRENT
    assert defect is HKEXBranchState.UNKNOWN


@pytest.mark.parametrize(
    "choice",
    [
        HKEXServingChoice.CARRY_FORWARD_LAST_APPROVED,
        HKEXServingChoice.WITHHOLD,
        HKEXServingChoice.NO_REBUILD,
    ],
)
def test_source_failure_preserves_separate_adr_0005_choice(
    choice: HKEXServingChoice,
) -> None:
    result = decide_hkex_effective_state(
        _request(
            source_failure_impact=HKEXSourceFailureImpact.COULD_CHANGE_CURRENT,
            source_failure_choice=choice,
        )
    )

    assert result.state is HKEXBranchState.UNKNOWN
    assert result.source_failure_choice is choice
    assert not result.current_product_reconciled


def test_malformed_or_ambiguous_temporal_and_branch_contracts_fail_closed() -> None:
    with pytest.raises(HKEXEffectiveStateError) as temporal:
        _request(
            basis=HKEXBranchBasis.FIXED_DATE,
            effective_at="2026-09-01T12:00:00",
        )
    assert temporal.value.code is HKEXEffectiveStateErrorCode.TEMPORAL

    with pytest.raises(HKEXEffectiveStateError) as conditional:
        _request(
            basis=HKEXBranchBasis.CONDITIONAL,
            condition_operator=HKEXConditionOperator.ALL_OF,
        )
    assert conditional.value.code is HKEXEffectiveStateErrorCode.CONTRACT

    with pytest.raises(HKEXEffectiveStateError) as missing_context:
        _request(transition_state=HKEXTransitionState.MATERIALLY_LIMITED_CURRENT)
    assert missing_context.value.code is HKEXEffectiveStateErrorCode.CONTRACT


def test_proved_transition_end_without_retirement_disposition_is_unknown() -> None:
    result = decide_hkex_effective_state(
        _request(transition_state=HKEXTransitionState.PROVED_ENDED)
    )

    assert result.state is HKEXBranchState.UNKNOWN
    assert result.reason is HKEXEffectiveStateReason.TRANSITION_END_UNRESOLVED


def test_frozen_effective_state_fixture_reproduces_exact_results() -> None:
    fixture = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "fixtures/deterministic/HKREG-EFFECTIVE-STATE-FIX-001.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    expected = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "expected/effective-state/HKREG-EFFECTIVE-STATE-FIX-001.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    request_schema = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "contracts/schemas/hkex-effective-state-request.schema.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    result_schema = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "contracts/schemas/hkex-effective-state-result.schema.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator.check_schema(result_schema)
    base = _json_object(fixture["base_request"])
    cases = _json_array(fixture["cases"])
    expected_cases = _json_array(expected["cases"])
    assert len(cases) == 22
    assert len(expected_cases) == len(cases)

    actual: list[dict[str, str | bool]] = []
    for raw_case in cases:
        case = _json_object(raw_case)
        case_id = _json_text(case["case_id"])
        request_document = {**base, **_json_object(case["overrides"])}
        decision = decide_hkex_effective_state(
            hkex_effective_state_request_from_document(request_document)
        )
        result_document = decision.document(case_id=case_id)
        actual.append(result_document)

    assert actual == [_json_object(item) for item in expected_cases]


def test_effective_state_document_parser_rejects_extra_or_unknown_codes() -> None:
    request = _request()
    document: dict[str, JsonValue] = {
        "decision_id": request.decision_id,
        "branch_id": request.branch_id,
        "component_id": request.component_id,
        "scope_id": request.scope_id,
        "legal_location_id": request.legal_location_id,
        "cutoff": request.cutoff,
        "update_part_id": request.update_part_id,
        "update_source_ranges": list(request.update_source_ranges),
        "current_product_ranges": list(request.current_product_ranges),
        "basis": request.basis.value,
        "finality": request.finality.value,
        "effective_at": request.effective_at,
        "condition_operator": None,
        "conditions": [],
        "transition_state": request.transition_state.value,
        "applicability_context": request.applicability_context,
        "retirement_evidence": request.retirement_evidence.value,
        "predecessor_branch_id": request.predecessor_branch_id,
        "successor_branch_ids": [],
        "current_product_reconciliation": request.current_product_reconciliation.value,
        "uncertainty_codes": [],
        "source_failure_impact": request.source_failure_impact.value,
        "source_failure_choice": request.source_failure_choice.value,
        "source_rule_id": request.source_rule_id,
        "evidence_refs": list(request.evidence_refs),
        "evidence_fingerprint": request.evidence_fingerprint,
    }
    with pytest.raises(HKEXEffectiveStateError):
        hkex_effective_state_request_from_document({**document, "extra": "forbidden"})
    with pytest.raises(HKEXEffectiveStateError):
        hkex_effective_state_request_from_document({**document, "basis": "NEWEST_WINS"})


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    result: dict[str, JsonValue] = {}
    for key, item in value.items():
        assert isinstance(key, str)
        result[key] = item
    return result


def _json_array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _json_text(value: JsonValue) -> str:
    assert isinstance(value, str)
    assert value
    return value
