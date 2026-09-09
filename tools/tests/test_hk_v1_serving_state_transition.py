"""Focused Task 10 local Serving-State rollback/restoration tests."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_promotion import ServingStateCandidate
from asklegal_promotion_worker.local_serving_state import (
    FileServingStateStore,
    initial_serving_state_bytes,
)

from tools.hk_v1_serving_state_transition import (
    ServingStateTransitionError,
    execute_serving_state_transition,
    main,
    plan_serving_state_transition,
    transition_plan_bytes,
)

STATE_0 = "srv_" + "0" * 48
STATE_1 = "srv_" + "1" * 48
STATE_2 = "srv_" + "2" * 48


def _fp(character: str) -> str:
    return "sha256:" + character * 64


def _sealed(body: dict[str, JsonValue]) -> bytes:
    unsigned = canonicalize(checked_json_value(body))
    return canonicalize(
        checked_json_value({**body, "fingerprint": "sha256:" + sha256(unsigned).hexdigest()})
    )


def _readback(path: Path, *, predecessor: str, state: str, marker: str) -> bytes:
    content = _sealed(
        {
            "schema_id": "asklegal.hk-v1-promotion-readback/v1",
            "schema_version": "1.0.0",
            "operation": "PROMOTION",
            "proposal_fingerprint": _fp(marker),
            "approval_fingerprint": _fp(chr(ord(marker) + 1)),
            "predecessor_serving_state_id": predecessor,
            "predecessor_serving_state_fingerprint": None,
            "predecessor_target_name": None,
            "predecessor_target_fingerprint": None,
            "serving_state_id": state,
            "serving_state_fingerprint": _fp(chr(ord(marker) + 2)),
            "target_name": f"asklegal-hk-{marker}",
            "target_fingerprint": _fp(chr(ord(marker) + 3)),
            "backup_fingerprint": _fp(chr(ord(marker) + 4)),
            "readback_fingerprint": _fp(chr(ord(marker) + 5)),
            "result": "COMPLETE",
        }
    )
    path.write_bytes(content)
    return content


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, ServingStateCandidate, str]:
    state_path = tmp_path / "promotion" / "current-serving-state.json"
    state_path.parent.mkdir()
    state_path.write_bytes(initial_serving_state_bytes(STATE_1))
    t1_path = tmp_path / "t1-promotion-readback.json"
    t2_path = tmp_path / "t2-promotion-readback.json"
    _readback(t1_path, predecessor=STATE_0, state=STATE_1, marker="1")
    _readback(t2_path, predecessor=STATE_1, state=STATE_2, marker="2")
    candidate = ServingStateCandidate(
        state_id=STATE_2,
        state_fingerprint=_fp("4"),
        predecessor_state_id=STATE_1,
        target_name="asklegal-hk-2",
        desired_inventory_fingerprint=_fp("8"),
        coverage_fingerprint=_fp("9"),
        embedding_profile_id="emb_hk_v1",
        embedding_profile_fingerprint=_fp("a"),
        approval_id="apr_" + "b" * 48,
        execution_lineage_id="exe_" + "c" * 48,
    )
    activation = FileServingStateStore(state_path).activate(STATE_1, candidate)
    return state_path, t1_path, t2_path, tmp_path / "receipts", candidate, activation.receipt_id


def _authority(plan_bytes: bytes, *, plan_fingerprint: str) -> bytes:
    plan = cast("dict[str, JsonValue]", json.loads(plan_bytes))
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1-serving-state-transition-authority/v1",
        "schema_version": "1.0.0",
        "authority_id": "auth_" + "d" * 48,
        "operation_id": plan["operation_id"],
        "plan_fingerprint": plan_fingerprint,
        "serving_state_path": plan["serving_state_path"],
        "t1_serving_state_id": STATE_1,
        "t2_serving_state_id": STATE_2,
        "authorized_operations": ["ROLLBACK_T2_TO_T1", "RESTORE_T1_TO_T2"],
        "decision": "AUTHORIZED",
    }
    return _sealed(body)


def test_plan_binds_exact_t1_t2_evidence_without_mutating_state(tmp_path: Path) -> None:
    """Default planning only reads canonical owner evidence and Serving State."""
    state_path, t1_path, t2_path, receipt_root, _candidate, _receipt = _fixture(tmp_path)
    before = state_path.read_bytes()

    plan = plan_serving_state_transition(state_path, t1_path, t2_path, receipt_root)
    content = transition_plan_bytes(plan)
    document = cast("dict[str, object]", json.loads(content))

    assert state_path.read_bytes() == before
    assert not receipt_root.exists()
    assert document["mode"] == "PLAN_ONLY"
    assert document["operations"] == ["ROLLBACK_T2_TO_T1", "RESTORE_T1_TO_T2"]
    assert document["t1_backup_fingerprint"] == _fp("5")
    assert document["t2_backup_fingerprint"] == _fp("6")
    assert document["activation_receipt_id"]


def test_execute_requires_exact_detached_authority_before_write(tmp_path: Path) -> None:
    """Missing or drifted authority leaves Serving State and receipt root untouched."""
    state_path, t1_path, t2_path, receipt_root, _candidate, _receipt = _fixture(tmp_path)
    plan = plan_serving_state_transition(state_path, t1_path, t2_path, receipt_root)
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(transition_plan_bytes(plan))
    before = state_path.read_bytes()

    with pytest.raises(ServingStateTransitionError, match="TRANSITION_AUTHORITY_INVALID"):
        execute_serving_state_transition(plan_path, tmp_path / "missing-authority.json")

    authority_path = tmp_path / "authority.json"
    authority_path.write_bytes(_authority(plan_path.read_bytes(), plan_fingerprint=_fp("f")))
    with pytest.raises(ServingStateTransitionError, match="TRANSITION_AUTHORITY_INVALID"):
        execute_serving_state_transition(plan_path, authority_path)

    assert state_path.read_bytes() == before
    assert not receipt_root.exists()


def test_authorized_rollback_and_restoration_are_exact_and_replayable(tmp_path: Path) -> None:
    """Authorized T2→T1→T2 persists both readbacks and replays after restart."""
    state_path, t1_path, t2_path, receipt_root, _candidate, _receipt = _fixture(tmp_path)
    plan = plan_serving_state_transition(state_path, t1_path, t2_path, receipt_root)
    plan_path = tmp_path / "plan.json"
    plan_bytes = transition_plan_bytes(plan)
    plan_path.write_bytes(plan_bytes)
    authority_path = tmp_path / "authority.json"
    authority_path.write_bytes(_authority(plan_bytes, plan_fingerprint=plan.fingerprint))

    first = execute_serving_state_transition(plan_path, authority_path)
    replay = execute_serving_state_transition(plan_path, authority_path)
    document = cast("dict[str, object]", json.loads(first))

    assert replay == first
    assert document["result"] == "COMPLETE"
    assert document["final_serving_state_id"] == STATE_2
    assert document["rollback_receipt_id"] != document["restoration_receipt_id"]
    assert document["t1_readback_fingerprint"] == _fp("6")
    assert document["t2_readback_fingerprint"] == _fp("7")
    assert document["routing_mutated"] is False
    assert document["index_deleted"] is False
    assert FileServingStateStore(state_path).active_state_id == STATE_2
    evidence_root = receipt_root / plan.operation_id
    rollback = cast(
        "dict[str, object]", json.loads((evidence_root / "rollback-readback.json").read_bytes())
    )
    restoration = cast(
        "dict[str, object]",
        json.loads((evidence_root / "restoration-readback.json").read_bytes()),
    )
    assert rollback["schema_id"] == "asklegal.hk-v1-promotion-readback/v1"
    assert rollback["operation"] == "ROLLBACK"
    assert rollback["predecessor_serving_state_id"] == STATE_2
    assert rollback["predecessor_target_name"] == "asklegal-hk-2"
    assert rollback["target_name"] == "asklegal-hk-1"
    assert rollback["serving_state_id"] == STATE_1
    assert restoration["operation"] == "RESTORATION"
    assert restoration["predecessor_serving_state_id"] == STATE_1
    assert restoration["predecessor_target_name"] == "asklegal-hk-1"
    assert restoration["target_name"] == "asklegal-hk-2"
    assert restoration["serving_state_id"] == STATE_2


def test_lost_rollback_ack_reconciles_without_second_transition(tmp_path: Path) -> None:
    """A crash after rollback mutation replays its exact receipt before restoration."""
    state_path, t1_path, t2_path, receipt_root, candidate, activation_receipt = _fixture(tmp_path)
    plan = plan_serving_state_transition(state_path, t1_path, t2_path, receipt_root)
    plan_path = tmp_path / "plan.json"
    plan_bytes = transition_plan_bytes(plan)
    plan_path.write_bytes(plan_bytes)
    authority_path = tmp_path / "authority.json"
    authority_path.write_bytes(_authority(plan_bytes, plan_fingerprint=plan.fingerprint))
    rollback = FileServingStateStore(state_path).rollback(candidate, activation_receipt)

    result = execute_serving_state_transition(plan_path, authority_path)

    document = cast("dict[str, object]", json.loads(result))
    assert document["rollback_receipt_id"] == rollback.receipt_id
    assert FileServingStateStore(state_path).active_state_id == STATE_2


def test_completed_authority_cannot_mutate_a_regressed_state_again(tmp_path: Path) -> None:
    """A completed single-use authority cannot repeat mutations after state regression."""
    state_path, t1_path, t2_path, receipt_root, _candidate, _receipt = _fixture(tmp_path)
    initial = state_path.read_bytes()
    plan = plan_serving_state_transition(state_path, t1_path, t2_path, receipt_root)
    plan_path = tmp_path / "plan.json"
    plan_bytes = transition_plan_bytes(plan)
    plan_path.write_bytes(plan_bytes)
    authority_path = tmp_path / "authority.json"
    authority_path.write_bytes(_authority(plan_bytes, plan_fingerprint=plan.fingerprint))
    execute_serving_state_transition(plan_path, authority_path)
    state_path.write_bytes(initial)

    with pytest.raises(ServingStateTransitionError, match="TRANSITION_REPORT_CONFLICT"):
        execute_serving_state_transition(plan_path, authority_path)

    assert state_path.read_bytes() == initial


def test_serving_state_drift_fails_without_receipt_or_additional_write(tmp_path: Path) -> None:
    """State drift after planning is rejected before rollback or retained success."""
    state_path, t1_path, t2_path, receipt_root, _candidate, _receipt = _fixture(tmp_path)
    plan = plan_serving_state_transition(state_path, t1_path, t2_path, receipt_root)
    plan_path = tmp_path / "plan.json"
    plan_bytes = transition_plan_bytes(plan)
    plan_path.write_bytes(plan_bytes)
    authority_path = tmp_path / "authority.json"
    authority_path.write_bytes(_authority(plan_bytes, plan_fingerprint=plan.fingerprint))
    drifted = cast("dict[str, JsonValue]", json.loads(state_path.read_bytes()))
    drifted["active_state_id"] = "srv_" + "f" * 48
    state_path.write_bytes(canonicalize(checked_json_value(drifted)))
    before = state_path.read_bytes()

    with pytest.raises(ServingStateTransitionError, match="TRANSITION_STATE_DRIFT"):
        execute_serving_state_transition(plan_path, authority_path)

    assert state_path.read_bytes() == before
    assert not receipt_root.exists()


def test_cli_defaults_to_plan_only_atomic_output_and_execute_needs_authority(
    tmp_path: Path,
) -> None:
    """The operator entrypoint freezes a 0600 plan and cannot infer execution authority."""
    state_path, t1_path, t2_path, receipt_root, _candidate, _receipt = _fixture(tmp_path)
    before = state_path.read_bytes()
    output = tmp_path / "frozen" / "transition-plan.json"

    assert (
        main(
            [
                "--serving-state",
                str(state_path),
                "--t1-readback",
                str(t1_path),
                "--t2-readback",
                str(t2_path),
                "--receipt-root",
                str(receipt_root),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.stat().st_mode & 0o777 == 0o600
    assert state_path.read_bytes() == before
    assert not receipt_root.exists()

    assert main(["--execute", "--plan", str(output)]) == 2
    assert state_path.read_bytes() == before
    assert not receipt_root.exists()
