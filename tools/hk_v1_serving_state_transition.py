"""Plan and authorize one exact local T2→T1→T2 Serving-State transition."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Never, cast

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_promotion import PromotionError, ServingStateCandidate, ServingStateReceipt
from asklegal_promotion_worker.local_serving_state import FileServingStateStore
from asklegal_promotion_worker.promotion_evidence import (
    PromotionReadbackEvidence,
    parse_promotion_readback,
)

_PLAN_SCHEMA = "asklegal.hk-v1-serving-state-transition-plan/v1"
_AUTHORITY_SCHEMA = "asklegal.hk-v1-serving-state-transition-authority/v1"
_REPORT_SCHEMA = "asklegal.hk-v1-serving-state-transition-report/v1"
_VERSION = "1.0.0"
_OPERATIONS = ("ROLLBACK_T2_TO_T1", "RESTORE_T1_TO_T2")
_PROHIBITED_EFFECTS = (
    "INDEX_DELETE",
    "ROUTING_MUTATION",
    "SOURCE_CALL",
    "PROVIDER_CALL",
)
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPERATION_ID = re.compile(r"^sst_[0-9a-f]{48}$")
_AUTHORITY_ID = re.compile(r"^auth_[0-9a-f]{48}$")
_RECEIPT_ID = re.compile(r"^ssr_[0-9a-f]{48}$")
_SERVING_STATE_ID = re.compile(r"^srv_[0-9a-f]{48}$")
_APPROVAL_ID = re.compile(r"^apr_[0-9a-f]{48}$")
_EXECUTION_ID = re.compile(r"^exe_[0-9a-f]{48}$")
_MAX_BYTES = 1_000_000


class ServingStateTransitionError(ValueError):
    """One safe, exact planning, authority, drift, or persistence failure."""


def _fail(code: str) -> Never:
    raise ServingStateTransitionError(code)


def _fingerprint(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


def _sealed(body: dict[str, JsonValue]) -> bytes:
    unsigned = canonicalize(checked_json_value(body))
    return canonicalize(checked_json_value({**body, "fingerprint": _fingerprint(unsigned)}))


def _safe_path(path: Path, code: str, *, existing_file: bool = False) -> Path:
    if not path.is_absolute() or path == Path(path.anchor) or path != path.resolve(strict=False):
        _fail(code)
    current = path
    while current != Path(current.anchor):
        if current.is_symlink():
            _fail(code)
        current = current.parent
    if existing_file and not path.is_file():
        _fail(code)
    return path


def _read_canonical(path: Path, code: str) -> tuple[bytes, dict[str, JsonValue]]:
    _safe_path(path, code, existing_file=True)
    try:
        content = path.read_bytes()
        value = parse_json_bytes(content, max_bytes=_MAX_BYTES)
    except (OSError, RuntimeError, ValueError) as error:
        raise ServingStateTransitionError(code) from error
    if type(value) is not dict or canonicalize(value) != content:
        _fail(code)
    return content, value


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value:
        _fail(code)
    return value


def _fp(value: object, code: str) -> str:
    text = _text(value, code)
    if _FINGERPRINT.fullmatch(text) is None:
        _fail(code)
    return text


def _candidate_document(candidate: ServingStateCandidate) -> dict[str, str]:
    return {
        "approval_id": candidate.approval_id,
        "candidate_serving_state_id": candidate.state_id,
        "candidate_serving_state_fingerprint": candidate.state_fingerprint,
        "coverage_fingerprint": candidate.coverage_fingerprint,
        "desired_inventory_fingerprint": candidate.desired_inventory_fingerprint,
        "embedding_profile_fingerprint": candidate.embedding_profile_fingerprint,
        "embedding_profile_id": candidate.embedding_profile_id,
        "execution_lineage_id": candidate.execution_lineage_id,
        "predecessor_state_id": candidate.predecessor_state_id,
        "target_name": candidate.target_name,
    }


def _candidate(value: object, code: str) -> ServingStateCandidate:
    if type(value) is not dict:
        _fail(code)
    document = cast("dict[str, JsonValue]", value)
    if set(document) != {
        "approval_id",
        "candidate_serving_state_id",
        "candidate_serving_state_fingerprint",
        "coverage_fingerprint",
        "desired_inventory_fingerprint",
        "embedding_profile_fingerprint",
        "embedding_profile_id",
        "execution_lineage_id",
        "predecessor_state_id",
        "target_name",
    }:
        _fail(code)
    candidate = ServingStateCandidate(
        _text(document["candidate_serving_state_id"], code),
        _fp(document["candidate_serving_state_fingerprint"], code),
        _text(document["predecessor_state_id"], code),
        _text(document["target_name"], code),
        _fp(document["desired_inventory_fingerprint"], code),
        _fp(document["coverage_fingerprint"], code),
        _text(document["embedding_profile_id"], code),
        _fp(document["embedding_profile_fingerprint"], code),
        _text(document["approval_id"], code),
        _text(document["execution_lineage_id"], code),
    )
    if (
        _SERVING_STATE_ID.fullmatch(candidate.state_id) is None
        or _SERVING_STATE_ID.fullmatch(candidate.predecessor_state_id) is None
        or _APPROVAL_ID.fullmatch(candidate.approval_id) is None
        or _EXECUTION_ID.fullmatch(candidate.execution_lineage_id) is None
        or candidate.state_id == candidate.predecessor_state_id
    ):
        _fail(code)
    return candidate


def _receipt(
    operation: str, predecessor: str, state: str, candidate_fingerprint: str
) -> ServingStateReceipt:
    material = canonicalize(
        checked_json_value(
            {
                "candidate_fingerprint": candidate_fingerprint,
                "operation": operation,
                "predecessor_state_id": predecessor,
                "state_id": state,
            }
        )
    )
    return ServingStateReceipt(
        "ssr_" + sha256(material).hexdigest()[:48],
        operation,
        predecessor,
        state,
        candidate_fingerprint,
    )


def _entry(candidate: ServingStateCandidate, receipt: ServingStateReceipt) -> dict[str, object]:
    return {"candidate": _candidate_document(candidate), "receipt_id": receipt.receipt_id}


@dataclass(frozen=True, slots=True)
class ServingStateTransitionPlan:
    """Frozen local-only T2 rollback and restoration subject."""

    operation_id: str
    serving_state_path: Path
    receipt_root: Path
    t1_readback_path: Path
    t1_evidence: PromotionReadbackEvidence
    t1_evidence_fingerprint: str
    t2_readback_path: Path
    t2_evidence: PromotionReadbackEvidence
    t2_evidence_fingerprint: str
    initial_serving_state_fingerprint: str
    activation_receipt_id: str
    candidate: ServingStateCandidate
    fingerprint: str


def _plan_body(plan: ServingStateTransitionPlan) -> dict[str, JsonValue]:
    return {
        "schema_id": _PLAN_SCHEMA,
        "schema_version": _VERSION,
        "mode": "PLAN_ONLY",
        "operation_id": plan.operation_id,
        "serving_state_path": str(plan.serving_state_path),
        "receipt_root": str(plan.receipt_root),
        "t1_readback_path": str(plan.t1_readback_path),
        "t1_evidence_fingerprint": plan.t1_evidence_fingerprint,
        "t1_serving_state_id": plan.t1_evidence.serving_state_id,
        "t1_serving_state_fingerprint": plan.t1_evidence.serving_state_fingerprint,
        "t1_target_name": plan.t1_evidence.target_name,
        "t1_target_fingerprint": plan.t1_evidence.target_fingerprint,
        "t1_backup_fingerprint": plan.t1_evidence.backup_fingerprint,
        "t1_readback_fingerprint": plan.t1_evidence.readback_fingerprint,
        "t2_readback_path": str(plan.t2_readback_path),
        "t2_evidence_fingerprint": plan.t2_evidence_fingerprint,
        "t2_serving_state_id": plan.t2_evidence.serving_state_id,
        "t2_serving_state_fingerprint": plan.t2_evidence.serving_state_fingerprint,
        "t2_target_name": plan.t2_evidence.target_name,
        "t2_target_fingerprint": plan.t2_evidence.target_fingerprint,
        "t2_backup_fingerprint": plan.t2_evidence.backup_fingerprint,
        "t2_readback_fingerprint": plan.t2_evidence.readback_fingerprint,
        "initial_serving_state_fingerprint": plan.initial_serving_state_fingerprint,
        "activation_receipt_id": plan.activation_receipt_id,
        "candidate": checked_json_value(_candidate_document(plan.candidate)),
        "operations": list(_OPERATIONS),
        "prohibited_effects": list(_PROHIBITED_EFFECTS),
    }


def transition_plan_bytes(plan: ServingStateTransitionPlan) -> bytes:
    """Return the canonical detached plan that an authority must fingerprint-bind."""
    body = _plan_body(plan)
    if _fingerprint(canonicalize(body)) != plan.fingerprint:
        _fail("TRANSITION_PLAN_INVALID")
    return canonicalize(checked_json_value({**body, "fingerprint": plan.fingerprint}))


def _validate_readbacks(
    t1: PromotionReadbackEvidence,
    t2: PromotionReadbackEvidence,
    candidate: ServingStateCandidate,
) -> None:
    fingerprints = (
        t1.proposal_fingerprint,
        t1.approval_fingerprint,
        t1.serving_state_fingerprint,
        t1.target_fingerprint,
        t1.backup_fingerprint,
        t1.readback_fingerprint,
        t1.fingerprint,
        t2.proposal_fingerprint,
        t2.approval_fingerprint,
        t2.serving_state_fingerprint,
        t2.target_fingerprint,
        t2.backup_fingerprint,
        t2.readback_fingerprint,
        t2.fingerprint,
    )
    if (
        t1.operation != "PROMOTION"
        or t2.operation != "PROMOTION"
        or any(_FINGERPRINT.fullmatch(value) is None for value in fingerprints)
        or _SERVING_STATE_ID.fullmatch(t1.predecessor_serving_state_id) is None
        or _SERVING_STATE_ID.fullmatch(t1.serving_state_id) is None
        or _SERVING_STATE_ID.fullmatch(t2.predecessor_serving_state_id) is None
        or _SERVING_STATE_ID.fullmatch(t2.serving_state_id) is None
        or t1.serving_state_id == t2.serving_state_id
        or t2.predecessor_serving_state_id != t1.serving_state_id
        or candidate.predecessor_state_id != t1.serving_state_id
        or candidate.state_id != t2.serving_state_id
        or candidate.state_fingerprint != t2.serving_state_fingerprint
        or candidate.target_name != t2.target_name
    ):
        _fail("TRANSITION_INPUT_NOT_READY")


def _stable_operation_id(  # noqa: PLR0913 - every exact identity input is load-bearing.
    *,
    serving_state_path: Path,
    receipt_root: Path,
    t1_evidence_fingerprint: str,
    t2_evidence_fingerprint: str,
    initial_serving_state_fingerprint: str,
    activation_receipt_id: str,
    candidate: ServingStateCandidate,
) -> str:
    identity: dict[str, JsonValue] = {
        "serving_state_path": str(serving_state_path),
        "receipt_root": str(receipt_root),
        "t1_evidence_fingerprint": t1_evidence_fingerprint,
        "t2_evidence_fingerprint": t2_evidence_fingerprint,
        "initial_serving_state_fingerprint": initial_serving_state_fingerprint,
        "activation_receipt_id": activation_receipt_id,
        "candidate": checked_json_value(_candidate_document(candidate)),
        "operations": list(_OPERATIONS),
    }
    return "sst_" + sha256(canonicalize(identity)).hexdigest()[:48]


def _initial_state(
    state_path: Path,
) -> tuple[bytes, ServingStateCandidate, str, dict[str, JsonValue]]:
    content, document = _read_canonical(state_path, "TRANSITION_INPUT_NOT_READY")
    if set(document) != {"activation", "active_state_id", "rollback", "schema_id"}:
        _fail("TRANSITION_INPUT_NOT_READY")
    activation = document.get("activation")
    if (
        document.get("schema_id") != "asklegal.local-serving-state/v1"
        or type(activation) is not dict
        or set(activation) != {"candidate", "receipt_id"}
        or document.get("rollback") is not None
    ):
        _fail("TRANSITION_INPUT_NOT_READY")
    candidate = _candidate(activation["candidate"], "TRANSITION_INPUT_NOT_READY")
    receipt_id = _text(activation["receipt_id"], "TRANSITION_INPUT_NOT_READY")
    expected = _receipt(
        "ACTIVATED", candidate.predecessor_state_id, candidate.state_id, candidate.state_fingerprint
    )
    if (
        _RECEIPT_ID.fullmatch(receipt_id) is None
        or receipt_id != expected.receipt_id
        or document.get("active_state_id") != candidate.state_id
    ):
        _fail("TRANSITION_INPUT_NOT_READY")
    return content, candidate, receipt_id, document


def plan_serving_state_transition(
    serving_state_path: Path,
    t1_readback_path: Path,
    t2_readback_path: Path,
    receipt_root: Path,
) -> ServingStateTransitionPlan:
    """Read and bind exact retained inputs without changing Serving State."""
    _safe_path(receipt_root, "TRANSITION_INPUT_NOT_READY")
    state_content, candidate, activation_receipt_id, _document = _initial_state(serving_state_path)
    t1_content, _t1_document = _read_canonical(t1_readback_path, "TRANSITION_INPUT_NOT_READY")
    t2_content, _t2_document = _read_canonical(t2_readback_path, "TRANSITION_INPUT_NOT_READY")
    try:
        t1 = parse_promotion_readback(t1_content)
        t2 = parse_promotion_readback(t2_content)
    except Exception as error:
        message = "TRANSITION_INPUT_NOT_READY"
        raise ServingStateTransitionError(message) from error
    _validate_readbacks(t1, t2, candidate)
    operation_id = _stable_operation_id(
        serving_state_path=serving_state_path,
        receipt_root=receipt_root,
        t1_evidence_fingerprint=_fingerprint(t1_content),
        t2_evidence_fingerprint=_fingerprint(t2_content),
        initial_serving_state_fingerprint=_fingerprint(state_content),
        activation_receipt_id=activation_receipt_id,
        candidate=candidate,
    )
    draft = ServingStateTransitionPlan(
        operation_id,
        serving_state_path,
        receipt_root,
        t1_readback_path,
        t1,
        _fingerprint(t1_content),
        t2_readback_path,
        t2,
        _fingerprint(t2_content),
        _fingerprint(state_content),
        activation_receipt_id,
        candidate,
        "",
    )
    return replace(draft, fingerprint=_fingerprint(canonicalize(_plan_body(draft))))


def _parse_plan(path: Path) -> ServingStateTransitionPlan:
    content, document = _read_canonical(path, "TRANSITION_PLAN_INVALID")
    required = {
        "schema_id",
        "schema_version",
        "mode",
        "operation_id",
        "serving_state_path",
        "receipt_root",
        "t1_readback_path",
        "t1_evidence_fingerprint",
        "t1_serving_state_id",
        "t1_serving_state_fingerprint",
        "t1_target_name",
        "t1_target_fingerprint",
        "t1_backup_fingerprint",
        "t1_readback_fingerprint",
        "t2_readback_path",
        "t2_evidence_fingerprint",
        "t2_serving_state_id",
        "t2_serving_state_fingerprint",
        "t2_target_name",
        "t2_target_fingerprint",
        "t2_backup_fingerprint",
        "t2_readback_fingerprint",
        "initial_serving_state_fingerprint",
        "activation_receipt_id",
        "candidate",
        "operations",
        "prohibited_effects",
        "fingerprint",
    }
    if (
        set(document) != required
        or document.get("schema_id") != _PLAN_SCHEMA
        or document.get("schema_version") != _VERSION
        or document.get("mode") != "PLAN_ONLY"
        or document.get("operations") != list(_OPERATIONS)
        or document.get("prohibited_effects") != list(_PROHIBITED_EFFECTS)
    ):
        _fail("TRANSITION_PLAN_INVALID")
    unsigned = dict(document)
    supplied = _fp(unsigned.pop("fingerprint"), "TRANSITION_PLAN_INVALID")
    if supplied != _fingerprint(canonicalize(unsigned)):
        _fail("TRANSITION_PLAN_INVALID")
    operation_id = _text(document["operation_id"], "TRANSITION_PLAN_INVALID")
    if _OPERATION_ID.fullmatch(operation_id) is None:
        _fail("TRANSITION_PLAN_INVALID")
    state_path = _safe_path(
        Path(_text(document["serving_state_path"], "TRANSITION_PLAN_INVALID")),
        "TRANSITION_PLAN_INVALID",
    )
    receipt_root = _safe_path(
        Path(_text(document["receipt_root"], "TRANSITION_PLAN_INVALID")),
        "TRANSITION_PLAN_INVALID",
    )
    t1_path = _safe_path(
        Path(_text(document["t1_readback_path"], "TRANSITION_PLAN_INVALID")),
        "TRANSITION_PLAN_INVALID",
        existing_file=True,
    )
    t2_path = _safe_path(
        Path(_text(document["t2_readback_path"], "TRANSITION_PLAN_INVALID")),
        "TRANSITION_PLAN_INVALID",
        existing_file=True,
    )
    candidate = _candidate(document["candidate"], "TRANSITION_PLAN_INVALID")
    t1_content, _ = _read_canonical(t1_path, "TRANSITION_PLAN_INVALID")
    t2_content, _ = _read_canonical(t2_path, "TRANSITION_PLAN_INVALID")
    if (
        _fingerprint(t1_content) != document["t1_evidence_fingerprint"]
        or _fingerprint(t2_content) != document["t2_evidence_fingerprint"]
    ):
        _fail("TRANSITION_EVIDENCE_DRIFT")
    try:
        t1 = parse_promotion_readback(t1_content)
        t2 = parse_promotion_readback(t2_content)
    except Exception as error:
        message = "TRANSITION_EVIDENCE_DRIFT"
        raise ServingStateTransitionError(message) from error
    _validate_readbacks(t1, t2, candidate)
    projected = {
        "t1_serving_state_id": t1.serving_state_id,
        "t1_serving_state_fingerprint": t1.serving_state_fingerprint,
        "t1_target_name": t1.target_name,
        "t1_target_fingerprint": t1.target_fingerprint,
        "t1_backup_fingerprint": t1.backup_fingerprint,
        "t1_readback_fingerprint": t1.readback_fingerprint,
        "t2_serving_state_id": t2.serving_state_id,
        "t2_serving_state_fingerprint": t2.serving_state_fingerprint,
        "t2_target_name": t2.target_name,
        "t2_target_fingerprint": t2.target_fingerprint,
        "t2_backup_fingerprint": t2.backup_fingerprint,
        "t2_readback_fingerprint": t2.readback_fingerprint,
    }
    if any(document[key] != value for key, value in projected.items()):
        _fail("TRANSITION_EVIDENCE_DRIFT")
    plan = ServingStateTransitionPlan(
        operation_id,
        state_path,
        receipt_root,
        t1_path,
        t1,
        _fp(document["t1_evidence_fingerprint"], "TRANSITION_PLAN_INVALID"),
        t2_path,
        t2,
        _fp(document["t2_evidence_fingerprint"], "TRANSITION_PLAN_INVALID"),
        _fp(document["initial_serving_state_fingerprint"], "TRANSITION_PLAN_INVALID"),
        _text(document["activation_receipt_id"], "TRANSITION_PLAN_INVALID"),
        candidate,
        supplied,
    )
    if (
        plan.operation_id
        != _stable_operation_id(
            serving_state_path=plan.serving_state_path,
            receipt_root=plan.receipt_root,
            t1_evidence_fingerprint=plan.t1_evidence_fingerprint,
            t2_evidence_fingerprint=plan.t2_evidence_fingerprint,
            initial_serving_state_fingerprint=plan.initial_serving_state_fingerprint,
            activation_receipt_id=plan.activation_receipt_id,
            candidate=plan.candidate,
        )
        or transition_plan_bytes(plan) != content
    ):
        _fail("TRANSITION_PLAN_INVALID")
    return plan


def _validate_authority(path: Path, plan: ServingStateTransitionPlan) -> None:
    _content, document = _read_canonical(path, "TRANSITION_AUTHORITY_INVALID")
    fields = {
        "schema_id",
        "schema_version",
        "authority_id",
        "operation_id",
        "plan_fingerprint",
        "serving_state_path",
        "t1_serving_state_id",
        "t2_serving_state_id",
        "authorized_operations",
        "decision",
        "fingerprint",
    }
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    if (
        set(document) != fields
        or document.get("schema_id") != _AUTHORITY_SCHEMA
        or document.get("schema_version") != _VERSION
        or _AUTHORITY_ID.fullmatch(str(document.get("authority_id"))) is None
        or document.get("operation_id") != plan.operation_id
        or document.get("plan_fingerprint") != plan.fingerprint
        or document.get("serving_state_path") != str(plan.serving_state_path)
        or document.get("t1_serving_state_id") != plan.t1_evidence.serving_state_id
        or document.get("t2_serving_state_id") != plan.t2_evidence.serving_state_id
        or document.get("authorized_operations") != list(_OPERATIONS)
        or document.get("decision") != "AUTHORIZED"
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
    ):
        _fail("TRANSITION_AUTHORITY_INVALID")


def _state_document(path: Path) -> tuple[bytes, dict[str, JsonValue]]:
    return _read_canonical(path, "TRANSITION_STATE_DRIFT")


def _classify_state(plan: ServingStateTransitionPlan) -> str:
    content, document = _state_document(plan.serving_state_path)
    activation = _entry(
        plan.candidate,
        _receipt(
            "ACTIVATED",
            plan.candidate.predecessor_state_id,
            plan.candidate.state_id,
            plan.candidate.state_fingerprint,
        ),
    )
    rollback = _entry(
        plan.candidate,
        _receipt(
            "ROLLED_BACK",
            plan.candidate.state_id,
            plan.candidate.predecessor_state_id,
            plan.candidate.state_fingerprint,
        ),
    )
    base = {
        "schema_id": "asklegal.local-serving-state/v1",
        "activation": activation,
    }
    if (
        document == {**base, "active_state_id": plan.candidate.state_id, "rollback": None}
        and _fingerprint(content) == plan.initial_serving_state_fingerprint
    ):
        return "INITIAL_T2"
    if document == {
        **base,
        "active_state_id": plan.candidate.predecessor_state_id,
        "rollback": rollback,
    }:
        return "ROLLED_BACK_T1"
    if document == {**base, "active_state_id": plan.candidate.state_id, "rollback": rollback}:
        return "RESTORED_T2"
    _fail("TRANSITION_STATE_DRIFT")


def _expected_rollback_state(plan: ServingStateTransitionPlan) -> bytes:
    activation = _entry(
        plan.candidate,
        _receipt(
            "ACTIVATED",
            plan.candidate.predecessor_state_id,
            plan.candidate.state_id,
            plan.candidate.state_fingerprint,
        ),
    )
    rollback = _entry(
        plan.candidate,
        _receipt(
            "ROLLED_BACK",
            plan.candidate.state_id,
            plan.candidate.predecessor_state_id,
            plan.candidate.state_fingerprint,
        ),
    )
    return canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.local-serving-state/v1",
                "activation": activation,
                "active_state_id": plan.candidate.predecessor_state_id,
                "rollback": rollback,
            }
        )
    )


def _transition_readback_bytes(plan: ServingStateTransitionPlan, operation: str) -> bytes:
    if operation == "ROLLBACK":
        evidence = plan.t1_evidence
        predecessor_evidence = plan.t2_evidence
    elif operation == "RESTORATION":
        evidence = plan.t2_evidence
        predecessor_evidence = plan.t1_evidence
    else:
        _fail("TRANSITION_REPORT_INVALID")
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1-promotion-readback/v1",
        "schema_version": _VERSION,
        "operation": operation,
        "proposal_fingerprint": plan.t2_evidence.proposal_fingerprint,
        "approval_fingerprint": plan.t2_evidence.approval_fingerprint,
        "predecessor_serving_state_id": predecessor_evidence.serving_state_id,
        "predecessor_serving_state_fingerprint": predecessor_evidence.serving_state_fingerprint,
        "predecessor_target_name": predecessor_evidence.target_name,
        "predecessor_target_fingerprint": predecessor_evidence.target_fingerprint,
        "serving_state_id": evidence.serving_state_id,
        "serving_state_fingerprint": evidence.serving_state_fingerprint,
        "target_name": evidence.target_name,
        "target_fingerprint": evidence.target_fingerprint,
        "backup_fingerprint": evidence.backup_fingerprint,
        "readback_fingerprint": evidence.readback_fingerprint,
        "result": "COMPLETE",
    }
    return _sealed(body)


def _report_bytes(
    plan: ServingStateTransitionPlan,
    rollback_readback: bytes,
    restoration_readback: bytes,
) -> bytes:
    rollback = _receipt(
        "ROLLED_BACK",
        plan.candidate.state_id,
        plan.candidate.predecessor_state_id,
        plan.candidate.state_fingerprint,
    )
    restoration = _receipt(
        "RESTORED",
        plan.candidate.predecessor_state_id,
        plan.candidate.state_id,
        plan.candidate.state_fingerprint,
    )
    final_state, _ = _state_document(plan.serving_state_path)
    body: dict[str, JsonValue] = {
        "schema_id": _REPORT_SCHEMA,
        "schema_version": _VERSION,
        "operation_id": plan.operation_id,
        "plan_fingerprint": plan.fingerprint,
        "result": "COMPLETE",
        "rollback_receipt_id": rollback.receipt_id,
        "rollback_state_fingerprint": _fingerprint(_expected_rollback_state(plan)),
        "rollback_serving_state_id": plan.candidate.predecessor_state_id,
        "restoration_receipt_id": restoration.receipt_id,
        "restoration_state_fingerprint": _fingerprint(final_state),
        "final_serving_state_id": plan.candidate.state_id,
        "t1_evidence_fingerprint": plan.t1_evidence_fingerprint,
        "t1_backup_fingerprint": plan.t1_evidence.backup_fingerprint,
        "t1_readback_fingerprint": plan.t1_evidence.readback_fingerprint,
        "t2_evidence_fingerprint": plan.t2_evidence_fingerprint,
        "t2_backup_fingerprint": plan.t2_evidence.backup_fingerprint,
        "t2_readback_fingerprint": plan.t2_evidence.readback_fingerprint,
        "rollback_evidence_path": str(
            plan.receipt_root / plan.operation_id / "rollback-readback.json"
        ),
        "rollback_evidence_fingerprint": _fingerprint(rollback_readback),
        "restoration_evidence_path": str(
            plan.receipt_root / plan.operation_id / "restoration-readback.json"
        ),
        "restoration_evidence_fingerprint": _fingerprint(restoration_readback),
        "routing_mutated": False,
        "index_deleted": False,
        "source_called": False,
        "provider_called": False,
    }
    return _sealed(body)


def _retain_exact(path: Path, content: bytes) -> None:
    _safe_path(path, "TRANSITION_REPORT_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with exclusive_local_state_lock(path):
        if path.exists():
            if path.is_symlink() or path.read_bytes() != content:
                _fail("TRANSITION_REPORT_CONFLICT")
        else:
            temporary = path.with_name(f".{path.name}.{token_hex(16)}.tmp")
            try:
                descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
    if path.read_bytes() != content:
        _fail("TRANSITION_REPORT_INVALID")


def _retain_report(plan: ServingStateTransitionPlan) -> bytes:
    evidence_root = plan.receipt_root / plan.operation_id
    rollback_readback = _transition_readback_bytes(plan, "ROLLBACK")
    restoration_readback = _transition_readback_bytes(plan, "RESTORATION")
    _retain_exact(evidence_root / "rollback-readback.json", rollback_readback)
    _retain_exact(evidence_root / "restoration-readback.json", restoration_readback)
    content = _report_bytes(plan, rollback_readback, restoration_readback)
    _retain_exact(evidence_root / "result.json", content)
    return content


def _retained_report(plan: ServingStateTransitionPlan) -> bytes | None:
    report_path = plan.receipt_root / plan.operation_id / "result.json"
    _safe_path(report_path, "TRANSITION_REPORT_INVALID")
    if not report_path.exists():
        return None
    if report_path.is_symlink() or not report_path.is_file():
        _fail("TRANSITION_REPORT_INVALID")
    content = report_path.read_bytes()
    try:
        document = parse_json_bytes(content, max_bytes=_MAX_BYTES)
    except (RuntimeError, ValueError) as error:
        message = "TRANSITION_REPORT_INVALID"
        raise ServingStateTransitionError(message) from error
    if type(document) is not dict or canonicalize(document) != content:
        _fail("TRANSITION_REPORT_INVALID")
    return content


def _completed_replay(
    plan: ServingStateTransitionPlan, state: str, retained: bytes | None
) -> bytes | None:
    if retained is None:
        return None
    if state != "RESTORED_T2":
        _fail("TRANSITION_REPORT_CONFLICT")
    expected = _report_bytes(
        plan,
        _transition_readback_bytes(plan, "ROLLBACK"),
        _transition_readback_bytes(plan, "RESTORATION"),
    )
    if retained != expected:
        _fail("TRANSITION_REPORT_CONFLICT")
    return retained


def execute_serving_state_transition(plan_path: Path, authority_path: Path) -> bytes:
    """Execute only the authority-bound local CAS rollback and restoration."""
    plan = _parse_plan(plan_path)
    _validate_authority(authority_path, plan)
    state = _classify_state(plan)
    replay = _completed_replay(plan, state, _retained_report(plan))
    if replay is not None:
        return replay
    store = FileServingStateStore(plan.serving_state_path)
    rollback_receipt = _receipt(
        "ROLLED_BACK",
        plan.candidate.state_id,
        plan.candidate.predecessor_state_id,
        plan.candidate.state_fingerprint,
    )
    try:
        if state == "INITIAL_T2":
            observed = store.rollback(plan.candidate, plan.activation_receipt_id)
            if observed.receipt_id != rollback_receipt.receipt_id:
                _fail("TRANSITION_STATE_DRIFT")
            state = _classify_state(plan)
        if state == "ROLLED_BACK_T1":
            observed = store.rollback(plan.candidate, plan.activation_receipt_id)
            if observed.receipt_id != rollback_receipt.receipt_id or not observed.replayed:
                _fail("TRANSITION_STATE_DRIFT")
            store.restore(plan.candidate, rollback_receipt.receipt_id)
            state = _classify_state(plan)
    except ServingStateTransitionError:
        raise
    except PromotionError as error:
        message = "TRANSITION_STATE_DRIFT"
        raise ServingStateTransitionError(message) from error
    if state != "RESTORED_T2":
        _fail("TRANSITION_STATE_DRIFT")
    store.verify(plan.candidate.state_id)
    return _retain_report(plan)


def _write_output(path: Path, content: bytes) -> None:
    _safe_path(path, "TRANSITION_OUTPUT_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{token_hex(16)}.tmp")
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            if path.is_symlink() or path.read_bytes() != content:
                _fail("TRANSITION_OUTPUT_CONFLICT")
            temporary.unlink()
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    if path.read_bytes() != content:
        _fail("TRANSITION_OUTPUT_INVALID")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or authority-gate exact local HK V1 Serving-State rollback/restoration"
    )
    parser.add_argument("--serving-state", type=Path)
    parser.add_argument("--t1-readback", type=Path)
    parser.add_argument("--t2-readback", type=Path)
    parser.add_argument("--receipt-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--authority", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Plan by default; mutate only from a frozen plan and detached authority."""
    arguments = _parser().parse_args(argv)
    try:
        if arguments.execute:
            if not isinstance(arguments.plan, Path) or not isinstance(arguments.authority, Path):
                _fail("TRANSITION_AUTHORITY_INVALID")
            content = execute_serving_state_transition(arguments.plan, arguments.authority)
        else:
            required = (
                arguments.serving_state,
                arguments.t1_readback,
                arguments.t2_readback,
                arguments.receipt_root,
            )
            if any(not isinstance(value, Path) for value in required):
                _fail("TRANSITION_INPUT_NOT_READY")
            plan = plan_serving_state_transition(*cast("tuple[Path, Path, Path, Path]", required))
            content = transition_plan_bytes(plan)
        if arguments.output is None:
            sys.stdout.buffer.write(content + b"\n")
        else:
            _write_output(arguments.output, content)
    except OSError, PromotionError, ServingStateTransitionError, ValueError:
        sys.stderr.write("SERVING_STATE_TRANSITION_NOT_READY\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
