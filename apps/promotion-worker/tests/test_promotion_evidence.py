"""Focused canonical Promotion owner-evidence tests."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_promotion import PromotionExecutionResult
from asklegal_promotion_worker.promotion_evidence import (
    PromotionEvidenceError,
    _sealed,
    _validate_serving_transition,
    parse_promotion_failure_stop,
    parse_promotion_readback,
)
from asklegal_promotion_worker.v1_infrastructure import V1PromotionPreflight


def _promotion() -> bytes:
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1-promotion-readback/v1",
        "schema_version": "1.0.0",
        "operation": "PROMOTION",
        "proposal_fingerprint": "sha256:" + "1" * 64,
        "approval_fingerprint": "sha256:" + "2" * 64,
        "predecessor_serving_state_id": "srv_" + "3" * 48,
        "predecessor_serving_state_fingerprint": None,
        "predecessor_target_name": None,
        "predecessor_target_fingerprint": None,
        "serving_state_id": "srv_" + "4" * 48,
        "serving_state_fingerprint": "sha256:" + "5" * 64,
        "target_name": "asklegal-v1-hk-local-20260908t120000",
        "target_fingerprint": "sha256:" + "6" * 64,
        "backup_fingerprint": "sha256:" + "7" * 64,
        "readback_fingerprint": "sha256:" + "8" * 64,
        "result": "COMPLETE",
    }
    return _sealed(body)


def test_exact_promotion_readback_round_trips_and_tamper_fails() -> None:
    """The parser accepts the closed owner projection, then rejects changed bytes."""
    content = _promotion()
    parsed = parse_promotion_readback(content)
    assert parsed.operation == "PROMOTION"
    assert parsed.serving_state_id == "srv_" + "4" * 48

    with pytest.raises(PromotionEvidenceError):
        parse_promotion_readback(content + b"\n")

    loose = json.loads(content)
    loose.pop("fingerprint")
    loose["serving_state_id"] = "srv_t1"
    with pytest.raises(PromotionEvidenceError):
        parse_promotion_readback(_sealed(loose))


def test_rollback_readback_binds_candidate_from_side_and_actual_predecessor_target() -> None:
    """T2 may identify the rollback origin but cannot masquerade as active T1."""
    body = {
        **json.loads(_promotion()),
        "operation": "ROLLBACK",
        "predecessor_serving_state_id": "srv_" + "4" * 48,
        "predecessor_serving_state_fingerprint": "sha256:" + "5" * 64,
        "predecessor_target_name": "asklegal-v1-hk-local-t2",
        "predecessor_target_fingerprint": "sha256:" + "6" * 64,
        "serving_state_id": "srv_" + "3" * 48,
        "serving_state_fingerprint": "sha256:" + "7" * 64,
        "target_name": "asklegal-v1-hk-local-t1",
        "target_fingerprint": "sha256:" + "8" * 64,
    }
    body.pop("fingerprint")
    parsed = parse_promotion_readback(_sealed(body))
    assert parsed.predecessor_serving_state_id == "srv_" + "4" * 48
    assert parsed.serving_state_id == "srv_" + "3" * 48
    assert parsed.predecessor_target_name != parsed.target_name

    body["target_name"] = body["predecessor_target_name"]
    body["target_fingerprint"] = body["predecessor_target_fingerprint"]
    with pytest.raises(PromotionEvidenceError):
        parse_promotion_readback(_sealed(body))


def test_rollback_owner_evidence_requires_exact_t2_to_t1_retained_cas() -> None:
    """A final T1 label cannot prove rollback without the exact retained T2 transition."""
    candidate = {
        "approval_id": "apr_" + "a" * 48,
        "candidate_serving_state_id": "srv_" + "2" * 48,
        "candidate_serving_state_fingerprint": "sha256:" + "2" * 64,
        "coverage_fingerprint": "sha256:" + "3" * 64,
        "desired_inventory_fingerprint": "sha256:" + "4" * 64,
        "embedding_profile_fingerprint": "sha256:" + "5" * 64,
        "embedding_profile_id": "emp_" + "5" * 48,
        "execution_lineage_id": "exe_" + "b" * 48,
        "predecessor_state_id": "srv_" + "1" * 48,
        "target_name": "asklegal-v1-hk-local-t2",
    }
    preflight = cast(
        "V1PromotionPreflight",
        SimpleNamespace(
            approval_id=candidate["approval_id"],
            execution_lineage_id=candidate["execution_lineage_id"],
            manifest=SimpleNamespace(
                candidate_serving_state_id=candidate["candidate_serving_state_id"],
                candidate_serving_state_fingerprint=candidate[
                    "candidate_serving_state_fingerprint"
                ],
                rollback_serving_state_id=candidate["predecessor_state_id"],
                coverage_status=SimpleNamespace(fingerprint=candidate["coverage_fingerprint"]),
                desired_state=SimpleNamespace(
                    inventory_fingerprint=candidate["desired_inventory_fingerprint"]
                ),
                embedding_profile=SimpleNamespace(
                    profile_id=candidate["embedding_profile_id"],
                    profile_fingerprint=candidate["embedding_profile_fingerprint"],
                ),
            ),
        ),
    )
    result = PromotionExecutionResult(
        candidate["execution_lineage_id"],
        "pmf_" + "6" * 48,
        candidate["target_name"],
        "EXECUTION_ROLLED_BACK",
        (),
        "native",
        "recovery",
        "ssr_activation",
        "ssr_rollback",
        0,
    )
    state = cast(
        "dict[str, JsonValue]",
        checked_json_value(
            {
                "schema_id": "asklegal.local-serving-state/v1",
                "activation": {"candidate": candidate, "receipt_id": "ssr_activation"},
                "active_state_id": candidate["predecessor_state_id"],
                "rollback": {"candidate": candidate, "receipt_id": "ssr_rollback"},
            }
        ),
    )
    content = canonicalize(state)
    _validate_serving_transition(
        preflight,
        result,
        content,
        candidate["target_name"],
        "ROLLBACK",
    )

    state["active_state_id"] = candidate["candidate_serving_state_id"]
    with pytest.raises(PromotionEvidenceError):
        _validate_serving_transition(
            preflight,
            result,
            canonicalize(state),
            candidate["target_name"],
            "ROLLBACK",
        )


def test_failure_stop_is_a_distinct_schema() -> None:
    """A failure-stop cannot be relabelled as a successful Promotion readback."""
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1-promotion-failure-stop/v1",
        "schema_version": "1.0.0",
        "approval_fingerprint": "sha256:" + "2" * 64,
        "execution_lineage_id": "exe_" + "3" * 48,
        "failure_code": "BACKUP_FAILED",
        "proposal_fingerprint": "sha256:" + "1" * 64,
        "serving_state_fingerprint": "sha256:" + "4" * 64,
        "serving_state_id": "srv_" + "5" * 48,
        "result": "STOPPED_NO_SERVING_STATE_CHANGE",
    }
    content = _sealed(body)

    assert parse_promotion_failure_stop(content).failure_code == "BACKUP_FAILED"
    with pytest.raises(PromotionEvidenceError):
        parse_promotion_readback(content)
