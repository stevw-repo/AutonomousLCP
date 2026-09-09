"""V1 Serving State activation is not Ask.Legal routing."""

from dataclasses import replace
from hashlib import sha256

import pytest
from asklegal_domain import EffectType
from asklegal_promotion import (
    LocalServingStateStore,
    PromotionError,
    PromotionErrorCode,
    ServingStateCandidate,
)
from asklegal_promotion.builder import validate_hk_v1_effect_types


def _candidate(*, predecessor: str = "srv_" + "a" * 48) -> ServingStateCandidate:
    return ServingStateCandidate(
        "srv_" + "b" * 48,
        "sha256:" + "b" * 64,
        predecessor,
        "asklegal-dev-hk-20260827-b" * 1,
        "sha256:" + "c" * 64,
        "sha256:" + "d" * 64,
        "emp_" + "e" * 48,
        "sha256:" + "e" * 64,
        "apr_" + "f" * 48,
        "exe_" + "1" * 48,
    )


def test_v1_manifest_rejects_an_asklegal_routing_action() -> None:
    """The V1 manifest boundary has no route, setting, or slot action."""
    with pytest.raises(PromotionError, match="V1 has no routing action"):
        validate_hk_v1_effect_types((EffectType.ROUTING_ACTIVATION,))


def test_serving_state_activation_loses_on_base_or_predecessor_drift() -> None:
    """A candidate cannot overwrite a changed state or name another predecessor."""
    store = LocalServingStateStore("srv_" + "a" * 48)

    with pytest.raises(PromotionError) as base_error:
        store.activate("srv_" + "c" * 48, _candidate())
    assert base_error.value.code is PromotionErrorCode.BASE_STATE_DRIFT

    with pytest.raises(PromotionError) as predecessor_error:
        store.activate("srv_" + "a" * 48, _candidate(predecessor="srv_" + "d" * 48))
    assert predecessor_error.value.code is PromotionErrorCode.BASE_STATE_DRIFT


def test_serving_state_activation_replays_and_rollback_is_exact() -> None:
    """Activation facts are immutable and reversal is predecessor-bound."""
    base = "srv_" + "a" * 48
    candidate = _candidate(predecessor=base)
    store = LocalServingStateStore(base)

    receipt = store.activate(base, candidate)
    replay = store.activate(base, candidate)
    assert store.active_state_id == candidate.state_id
    assert replay.receipt_id == receipt.receipt_id
    assert replay.replayed is True
    store.verify(candidate.state_id)

    rollback = store.rollback(candidate, receipt.receipt_id)
    assert rollback.operation == "ROLLED_BACK"
    assert store.active_state_id == base
    assert store.rollback(candidate, receipt.receipt_id).replayed is True
    with pytest.raises(PromotionError, match="rollback failed"):
        store.rollback(candidate, "ssr_" + "9" * 48)


def test_stale_activation_replay_and_unrelated_rollback_are_rejected() -> None:
    """No old candidate fact can become current again through a replay shortcut."""
    base = "srv_" + "a" * 48
    candidate = _candidate(predecessor=base)
    store = LocalServingStateStore(base)
    receipt = store.activate(base, candidate)
    store.rollback(candidate, receipt.receipt_id)

    with pytest.raises(PromotionError, match="BASE_STATE_DRIFT"):
        store.activate(base, candidate)
    with pytest.raises(PromotionError, match="rollback failed"):
        store.rollback(candidate, "ssr_" + "9" * 48)


def test_local_receipt_matches_sql_identity_and_binds_every_candidate_fact() -> None:
    """Local facts use the SQL SHA-256 identity, never a short synthetic receipt."""
    base = "srv_" + "a" * 48
    candidate = _candidate(predecessor=base)
    receipt = LocalServingStateStore(base).activate(base, candidate)
    assert receipt.receipt_id.startswith("ssr_")
    assert len(receipt.receipt_id) == 68
    expected = (
        f"{base}|{candidate.state_id}|{candidate.state_fingerprint}|{candidate.target_name}|"
        f"{candidate.desired_inventory_fingerprint}|{candidate.coverage_fingerprint}|"
        f"{candidate.embedding_profile_id}|{candidate.embedding_profile_fingerprint}|"
        f"{candidate.approval_id}|{candidate.execution_lineage_id}"
    )
    assert receipt.receipt_id == f"ssr_{sha256(expected.encode()).hexdigest()}"
    for changed in (
        {"target_name": "asklegal-dev-hk-20260827-c"},
        {"embedding_profile_id": "emp_" + "2" * 48},
        {"approval_id": "apr_" + "3" * 48},
        {"execution_lineage_id": "exe_" + "4" * 48},
    ):
        other = replace(candidate, **changed)
        replay_store = LocalServingStateStore(base)
        activated = replay_store.activate(base, candidate)
        replay_store.rollback(candidate, activated.receipt_id)
        changed_activation = replay_store.activate(base, other)
        assert changed_activation.replayed is False
        assert changed_activation.receipt_id != receipt.receipt_id
