"""Source-neutral projection of established HKEX branch-state decisions."""

from __future__ import annotations

import copy
import gc
import pickle
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol
from weakref import ref

import asklegal_legal_desks.hk_regulatory_effective_state as effective_state
import pytest
from asklegal_legal_desks.hk_regulatory_effective_state import (
    HKEX_EFFECTIVE_STATE_RULE_ID,
    HKEXBranchBasis,
    HKEXBranchState,
    HKEXCurrentProductReconciliation,
    HKEXEffectiveStateError,
    HKEXEffectiveStateErrorCode,
    HKEXEffectiveStateReason,
    HKEXEffectiveStateRequest,
    HKEXFinality,
    HKEXRetirementEvidence,
    HKEXServingChoice,
    HKEXSourceFailureImpact,
    HKEXSourceNeutralPriorBranchState,
    HKEXSourceNeutralStateProjection,
    HKEXStateUncertainty,
    HKEXTransitionState,
    project_hkex_source_neutral_state,
)
from asklegal_legal_desks.hk_regulatory_inventory import HKEX_GEM_SCOPE_ID

FINGERPRINT = f"sha256:{'a' * 64}"


class _ProjectionValuesFactory(Protocol):
    """Typed test-only access to one intentionally private integrity boundary."""

    def __call__(self, **values: object) -> object:
        """Construct one private candidate shape for the issuer rejection test."""


class _ProjectionIssuer(Protocol):
    """Typed test-only access to the private issuance boundary."""

    def __call__(self, authority: object) -> object:
        """Attempt one private issuance."""


class _LocalPickleLoader(Protocol):
    """Typed local round-trip loader for a self-generated pickle payload."""

    def __call__(self, payload: bytes) -> object:
        """Deserialize one immediately preceding local pickle payload."""


class _ProjectionSnapshotter(Protocol):
    """Typed test-only access to the projection's canonical bytes helper."""

    def __call__(self, projection: object) -> bytes:
        """Return the canonical primitive bytes for a shaped projection."""
        ...


def _request(**changes: object) -> HKEXEffectiveStateRequest:
    request = HKEXEffectiveStateRequest(
        decision_id="decision-source-neutral-2.01",
        branch_id="branch-source-neutral-2.01",
        component_id="component-source-neutral-2.01",
        scope_id=HKEX_GEM_SCOPE_ID,
        legal_location_id="location-source-neutral-2.01",
        cutoff="2026-08-25T00:00:00+08:00",
        update_part_id="update-source-neutral-part-a",
        update_source_ranges=("evidence-update#part-a",),
        current_product_ranges=("evidence-current#rule-2.01",),
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
        evidence_refs=("evidence-current", "evidence-update"),
        evidence_fingerprint=FINGERPRINT,
    )
    return replace(request, **changes)


def _prior(
    request: HKEXEffectiveStateRequest,
    *,
    state: HKEXBranchState = HKEXBranchState.CURRENT,
    **changes: object,
) -> HKEXSourceNeutralPriorBranchState:
    prior = HKEXSourceNeutralPriorBranchState(
        component_id=request.component_id,
        branch_id=request.branch_id,
        state=state,
        decision_fingerprint=FINGERPRINT,
    )
    return replace(prior, **changes)


def _other_component_prior(request: HKEXEffectiveStateRequest) -> HKEXSourceNeutralPriorBranchState:
    return _prior(request, component_id="component-other")


def _other_branch_prior(request: HKEXEffectiveStateRequest) -> HKEXSourceNeutralPriorBranchState:
    return _prior(request, branch_id="branch-other")


def test_future_fixed_date_projects_waiting_room() -> None:
    """Catch an adapter that promotes a branch before its established date."""
    result = project_hkex_source_neutral_state(
        _request(
            basis=HKEXBranchBasis.FIXED_DATE,
            effective_at="2026-09-01",
        ),
        None,
    )

    assert result.state == "WAITING_ROOM"
    assert result.reason_code == HKEXEffectiveStateReason.FUTURE_FIXED_DATE_PENDING.value
    assert not result.keep_prior_current


def test_unresolved_transition_preserves_matching_prior_current() -> None:
    """Catch an adapter that replaces a prior current branch on uncertainty."""
    request = _request(uncertainty_codes=(HKEXStateUncertainty.TRANSITION_SCOPE_AMBIGUOUS,))

    result = project_hkex_source_neutral_state(request, _prior(request))

    assert result.state == "QUARANTINE"
    assert result.reason_code == HKEXEffectiveStateReason.UNRESOLVED_LEGAL_STATE_FACT.value
    assert result.keep_prior_current


def test_complete_successor_projects_history_without_prior_retention() -> None:
    """Catch an adapter that retains a current branch after a complete successor."""
    request = _request(
        retirement_evidence=HKEXRetirementEvidence.COMPLETE_SUCCESSOR,
        successor_branch_ids=("branch-successor",),
        transition_state=HKEXTransitionState.PROVED_ENDED,
    )

    result = project_hkex_source_neutral_state(request, _prior(request))

    assert result.state == "HISTORY"
    assert result.reason_code == HKEXEffectiveStateReason.COMPLETE_SUCCESSOR_PROVED.value
    assert not result.keep_prior_current


@pytest.mark.parametrize(
    "prior_builder",
    [
        _other_component_prior,
        _other_branch_prior,
    ],
)
def test_prior_identity_mismatch_fails_closed(
    prior_builder: Callable[[HKEXEffectiveStateRequest], HKEXSourceNeutralPriorBranchState],
) -> None:
    """Catch cross-component or cross-branch prior-current retention."""
    request = _request()

    with pytest.raises(HKEXEffectiveStateError) as caught:
        project_hkex_source_neutral_state(request, prior_builder(request))

    assert caught.value.code is HKEXEffectiveStateErrorCode.PRIOR


class _FingerprintText(str):
    """Hostile equal text that is not an exact primitive string."""

    __slots__ = ()


class _FingerprintEqualityLiar(str):
    """Hostile text that claims equality with every candidate fingerprint."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0


@pytest.mark.parametrize(
    "fingerprint",
    [
        "sha256:ABCDEF" + "a" * 58,
        "",
        _FingerprintText(FINGERPRINT),
        _FingerprintEqualityLiar(FINGERPRINT),
    ],
)
def test_malformed_prior_fingerprint_fails_closed(fingerprint: str) -> None:
    """Catch a prior whose displayed fingerprint cannot be exact evidence."""
    request = _request()

    with pytest.raises(HKEXEffectiveStateError) as caught:
        _prior(request, decision_fingerprint=fingerprint)

    assert caught.value.code is HKEXEffectiveStateErrorCode.PRIOR


def test_forged_prior_state_and_raw_prior_fail_closed() -> None:
    """Catch enum-shaped or raw prior inputs before they influence a projection."""
    request = _request()
    forged = object.__new__(HKEXSourceNeutralPriorBranchState)
    object.__setattr__(forged, "component_id", request.component_id)
    object.__setattr__(forged, "branch_id", request.branch_id)
    object.__setattr__(forged, "state", "CURRENT")
    object.__setattr__(forged, "decision_fingerprint", FINGERPRINT)

    for prior in (forged, object()):
        with pytest.raises(HKEXEffectiveStateError) as caught:
            project_hkex_source_neutral_state(request, prior)
        assert caught.value.code is HKEXEffectiveStateErrorCode.PRIOR


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("scope_id", "HK-REG-HKEX-UNKNOWN", HKEXEffectiveStateErrorCode.CONTRACT),
        ("evidence_refs", (), HKEXEffectiveStateErrorCode.EVIDENCE),
        ("evidence_fingerprint", "sha256:bad", HKEXEffectiveStateErrorCode.EVIDENCE),
    ],
)
def test_post_construction_request_mutation_fails_before_projection(
    field: str,
    value: object,
    code: HKEXEffectiveStateErrorCode,
) -> None:
    """Catch a mutable request that could otherwise return a false current result."""
    request = _request()
    object.__setattr__(request, field, value)

    with pytest.raises(HKEXEffectiveStateError) as caught:
        project_hkex_source_neutral_state(request, None)

    assert caught.value.code is code


class _ForeignComponentEqualityLiar(str):
    """Hostile foreign component identity that compares equal to every prior."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False

    def __hash__(self) -> int:
        return 0


class _ScopeEqualityLiar(str):
    """Hostile foreign scope identity that compares equal to accepted scopes."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0


class _ValidTextSubclass(str):
    """Hostile text with valid displayed bytes but a non-exact runtime type."""

    __slots__ = ()


def test_equality_lying_request_component_cannot_retain_foreign_prior() -> None:
    """Catch an equality liar that could retain a different component's prior state."""
    request = _request(uncertainty_codes=(HKEXStateUncertainty.TRANSITION_SCOPE_AMBIGUOUS,))
    prior = _prior(request)
    object.__setattr__(
        request,
        "component_id",
        _ForeignComponentEqualityLiar("component-foreign"),
    )

    with pytest.raises(HKEXEffectiveStateError) as caught:
        project_hkex_source_neutral_state(request, prior)

    assert caught.value.code is HKEXEffectiveStateErrorCode.CONTRACT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope_id", _ScopeEqualityLiar(HKEX_GEM_SCOPE_ID)),
        ("cutoff", _ValidTextSubclass("2026-08-25T00:00:00+08:00")),
        ("evidence_fingerprint", _ValidTextSubclass(FINGERPRINT)),
    ],
)
def test_valid_shaped_request_scalar_subclasses_fail_before_any_comparison(
    field: str,
    value: str,
) -> None:
    """Catch equality/hash-liar or subtype scalar facts before reconstruction."""
    request = _request()
    object.__setattr__(request, field, value)

    with pytest.raises(HKEXEffectiveStateError) as caught:
        project_hkex_source_neutral_state(request, None)

    assert caught.value.code is HKEXEffectiveStateErrorCode.CONTRACT


def test_private_issuer_rejects_arbitrary_current_values() -> None:
    """Catch issuer membership that accepts a forged output instead of derivation."""
    values_factory_name = "_SourceNeutralProjectionValues"
    issuer_name = "_issue_source_neutral_projection"
    values_factory: _ProjectionValuesFactory = getattr(effective_state, values_factory_name)
    issuer: _ProjectionIssuer = getattr(effective_state, issuer_name)
    values = values_factory(
        component_id="component-forged",
        branch_id="branch-forged",
        state="CURRENT",
        keep_prior_current=False,
        reason_code=HKEXEffectiveStateReason.FUTURE_FIXED_DATE_PENDING.value,
        evidence_refs=("evidence-forged",),
    )

    with pytest.raises(HKEXEffectiveStateError) as caught:
        issuer(values)

    assert caught.value.code is HKEXEffectiveStateErrorCode.CONTRACT


def test_raw_exact_class_request_missing_fields_normalizes_to_closed_error() -> None:
    """Catch raw exact-class request shapes that previously leaked AttributeError."""
    raw = object.__new__(HKEXEffectiveStateRequest)

    with pytest.raises(HKEXEffectiveStateError) as caught:
        project_hkex_source_neutral_state(raw, None)

    assert caught.value.code is HKEXEffectiveStateErrorCode.CONTRACT


def test_request_mutation_during_kernel_call_cannot_change_returned_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch a time-of-check/use gap between the kernel result and output evidence."""
    request = _request()
    original = effective_state.decide_hkex_effective_state

    def decide_then_mutate(value: HKEXEffectiveStateRequest) -> object:
        decision = original(value)
        object.__setattr__(request, "evidence_refs", ())
        return decision

    monkeypatch.setattr(effective_state, "decide_hkex_effective_state", decide_then_mutate)

    result = project_hkex_source_neutral_state(request, None)

    assert result.state == "CURRENT"
    assert result.evidence_refs == ("evidence-current", "evidence-update")


def test_direct_or_replaced_projection_cannot_mint_current_or_retention() -> None:
    """Catch a freely constructible result that claims impossible current retention."""
    result = project_hkex_source_neutral_state(_request(), None)

    with pytest.raises(TypeError):
        HKEXSourceNeutralStateProjection()
    with pytest.raises(TypeError):
        replace(result, state="CURRENT", keep_prior_current=True)


def test_forged_or_mutated_projection_fails_factory_replay() -> None:
    """Catch a projection-shaped object that borrows no issued result authority."""
    result = project_hkex_source_neutral_state(_request(), None)
    forged = object.__new__(HKEXSourceNeutralStateProjection)
    for name, value in (
        ("component_id", result.component_id),
        ("branch_id", result.branch_id),
        ("state", result.state),
        ("keep_prior_current", result.keep_prior_current),
        ("reason_code", result.reason_code),
        ("evidence_refs", result.evidence_refs),
    ):
        object.__setattr__(forged, name, value)

    object.__setattr__(result, "evidence_refs", ("evidence-forged",))
    for projection in (forged, result):
        with pytest.raises(HKEXEffectiveStateError) as caught:
            projection.assert_factory_issued()
        assert caught.value.code is HKEXEffectiveStateErrorCode.CONTRACT


def test_registry_byte_replacement_cannot_authorize_mutated_projection() -> None:
    """Catch a registry snapshot rewrite after an issued result becomes impossible."""
    result = project_hkex_source_neutral_state(_request(), None)
    registry_name = "_SOURCE_NEUTRAL_PROJECTION_ISSUANCE"
    snapshotter_name = "_source_neutral_projection_bytes"
    registry: dict[int, tuple[object, bytes, object]] = getattr(effective_state, registry_name)
    snapshotter: _ProjectionSnapshotter = getattr(effective_state, snapshotter_name)
    reference, _, authority = registry[id(result)]
    object.__setattr__(result, "state", "QUARANTINE")
    object.__setattr__(result, "keep_prior_current", True)
    object.__setattr__(
        result,
        "reason_code",
        HKEXEffectiveStateReason.FUTURE_FIXED_DATE_PENDING.value,
    )
    registry[id(result)] = (reference, snapshotter(result), authority)

    with pytest.raises(HKEXEffectiveStateError) as caught:
        result.assert_factory_issued()

    assert caught.value.code is HKEXEffectiveStateErrorCode.CONTRACT


def test_projection_copy_pickle_and_gc_preserve_factory_issuance_boundaries() -> None:
    """Catch copied or resurrected projection shapes that retain factory authority."""
    result = project_hkex_source_neutral_state(_request(), None)
    pickle_loader_name = "loads"
    pickle_loader: _LocalPickleLoader = getattr(pickle, pickle_loader_name)
    copies = (
        copy.copy(result),
        copy.deepcopy(result),
        pickle_loader(pickle.dumps(result)),
    )

    for copied in copies:
        assert copied is not result
        assert isinstance(copied, HKEXSourceNeutralStateProjection)
        with pytest.raises(HKEXEffectiveStateError) as caught:
            copied.assert_factory_issued()
        assert caught.value.code is HKEXEffectiveStateErrorCode.CONTRACT

    result_reference = ref(result)
    del result
    gc.collect()
    assert result_reference() is None

    fresh = project_hkex_source_neutral_state(_request(), None)
    fresh.assert_factory_issued()


def test_keyboard_interrupt_from_kernel_remains_observable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch a broad normalization path that hides process-control interruption."""

    def interrupt(_: HKEXEffectiveStateRequest) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(effective_state, "decide_hkex_effective_state", interrupt)

    with pytest.raises(KeyboardInterrupt):
        project_hkex_source_neutral_state(_request(), None)
