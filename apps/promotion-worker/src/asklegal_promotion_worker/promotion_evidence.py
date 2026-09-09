"""Canonical retained evidence emitted by the live local Promotion owner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Never

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_promotion import (
    PromotionExecutionResult,
    pinecone_index_name,
    target_state_fingerprint,
)

from asklegal_promotion_worker.real_effects import approved_v1_backup_request
from asklegal_promotion_worker.v1_infrastructure import V1PromotionPreflight

_REPORT_SCHEMA = "asklegal.hk-v1-promotion-readback/v1"
_FAILURE_SCHEMA = "asklegal.hk-v1-promotion-failure-stop/v1"
_VERSION = "1.0.0"
_INVALID = "PROMOTION_EVIDENCE_INVALID"
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_SERVING_STATE = re.compile(r"^srv_[0-9a-f]{48}$")


@dataclass(frozen=True, slots=True)
class PromotionReadbackEvidence:
    """Parsed successful Promotion/rollback readback facts."""

    operation: str
    proposal_fingerprint: str
    approval_fingerprint: str
    predecessor_serving_state_id: str
    predecessor_serving_state_fingerprint: str | None
    predecessor_target_name: str | None
    predecessor_target_fingerprint: str | None
    serving_state_id: str
    serving_state_fingerprint: str
    target_name: str
    target_fingerprint: str
    backup_fingerprint: str
    readback_fingerprint: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PromotionFailureStopEvidence:
    """Parsed proof that one failed execution left Serving State unchanged."""

    proposal_fingerprint: str
    approval_fingerprint: str
    execution_lineage_id: str
    failure_code: str
    serving_state_id: str
    serving_state_fingerprint: str
    fingerprint: str


class PromotionEvidenceError(ValueError):
    """One exact Promotion evidence persistence or replay failure."""


def _fail() -> Never:
    raise PromotionEvidenceError(_INVALID)


def _fingerprint(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


def _sealed(body: dict[str, JsonValue]) -> bytes:
    content = canonicalize(checked_json_value(body))
    return canonicalize(checked_json_value({**body, "fingerprint": _fingerprint(content)}))


def _parse_sealed(content: bytes, schema: str, fields: frozenset[str]) -> dict[str, JsonValue]:
    try:
        value = parse_json_bytes(content, max_bytes=1_000_000)
    except (RuntimeError, ValueError) as error:
        raise PromotionEvidenceError(_INVALID) from error
    if not isinstance(value, dict) or canonicalize(value) != content:
        _fail()
    if frozenset(value) != fields | {"schema_id", "schema_version", "fingerprint"}:
        _fail()
    unsigned = dict(value)
    supplied = unsigned.pop("fingerprint", None)
    if (
        value.get("schema_id") != schema
        or value.get("schema_version") != _VERSION
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
    ):
        _fail()
    return value


def _required_text(document: dict[str, JsonValue], key: str) -> str:
    value = document.get(key)
    if type(value) is not str or not value:
        _fail()
    return value


def parse_promotion_readback(content: bytes) -> PromotionReadbackEvidence:
    """Strictly parse the exact terminal artifact emitted after all owner readbacks."""
    fields = frozenset(
        {
            "operation",
            "proposal_fingerprint",
            "approval_fingerprint",
            "predecessor_serving_state_id",
            "predecessor_serving_state_fingerprint",
            "predecessor_target_name",
            "predecessor_target_fingerprint",
            "serving_state_id",
            "serving_state_fingerprint",
            "target_name",
            "target_fingerprint",
            "backup_fingerprint",
            "readback_fingerprint",
            "result",
        }
    )
    value = _parse_sealed(content, _REPORT_SCHEMA, fields)
    operation = _required_text(value, "operation")
    if (
        operation not in {"PROMOTION", "ROLLBACK", "RESTORATION"}
        or value.get("result") != "COMPLETE"
    ):
        _fail()
    predecessor_values = (
        value.get("predecessor_serving_state_fingerprint"),
        value.get("predecessor_target_name"),
        value.get("predecessor_target_fingerprint"),
    )
    if operation == "PROMOTION":
        if predecessor_values != (None, None, None):
            _fail()
    elif (
        any(type(item) is not str or not item for item in predecessor_values)
        or value.get("predecessor_serving_state_id") == value.get("serving_state_id")
        or value.get("predecessor_target_name") == value.get("target_name")
        or value.get("predecessor_target_fingerprint") == value.get("target_fingerprint")
    ):
        _fail()
    fingerprint_fields = (
        "proposal_fingerprint",
        "approval_fingerprint",
        "serving_state_fingerprint",
        "target_fingerprint",
        "backup_fingerprint",
        "readback_fingerprint",
        "fingerprint",
    )
    if (
        _SERVING_STATE.fullmatch(str(value.get("predecessor_serving_state_id"))) is None
        or _SERVING_STATE.fullmatch(str(value.get("serving_state_id"))) is None
        or any(
            _FINGERPRINT.fullmatch(str(value.get(field))) is None for field in fingerprint_fields
        )
        or (
            operation != "PROMOTION"
            and _FINGERPRINT.fullmatch(str(value.get("predecessor_serving_state_fingerprint")))
            is None
        )
    ):
        _fail()
    return PromotionReadbackEvidence(
        operation,
        _required_text(value, "proposal_fingerprint"),
        _required_text(value, "approval_fingerprint"),
        _required_text(value, "predecessor_serving_state_id"),
        None if predecessor_values[0] is None else str(predecessor_values[0]),
        None if predecessor_values[1] is None else str(predecessor_values[1]),
        None if predecessor_values[2] is None else str(predecessor_values[2]),
        _required_text(value, "serving_state_id"),
        _required_text(value, "serving_state_fingerprint"),
        _required_text(value, "target_name"),
        _required_text(value, "target_fingerprint"),
        _required_text(value, "backup_fingerprint"),
        _required_text(value, "readback_fingerprint"),
        _required_text(value, "fingerprint"),
    )


def parse_promotion_failure_stop(content: bytes) -> PromotionFailureStopEvidence:
    """Strictly parse a no-Serving-State-change failure artifact."""
    fields = frozenset(
        {
            "approval_fingerprint",
            "execution_lineage_id",
            "failure_code",
            "proposal_fingerprint",
            "serving_state_fingerprint",
            "serving_state_id",
            "result",
        }
    )
    value = _parse_sealed(content, _FAILURE_SCHEMA, fields)
    if value.get("result") != "STOPPED_NO_SERVING_STATE_CHANGE":
        _fail()
    return PromotionFailureStopEvidence(
        _required_text(value, "proposal_fingerprint"),
        _required_text(value, "approval_fingerprint"),
        _required_text(value, "execution_lineage_id"),
        _required_text(value, "failure_code"),
        _required_text(value, "serving_state_id"),
        _required_text(value, "serving_state_fingerprint"),
        _required_text(value, "fingerprint"),
    )


def _proposal_fingerprint(preflight: V1PromotionPreflight) -> str:
    candidates = tuple(
        fingerprint
        for contract_id, _version, fingerprint in preflight.manifest.validity_predicates
        if contract_id == "HK_V1_TWO_FAMILY_PROPOSAL"
    )
    if len(candidates) != 1:
        _fail()
    return candidates[0]


def _backup_bytes(preflight: V1PromotionPreflight, target_name: str) -> tuple[bytes, bytes]:
    request = approved_v1_backup_request(preflight.serving_profile, preflight.manifest)
    name = request.request_fingerprint.removeprefix("sha256:") + ".json"
    native = preflight.native_backup_root / name
    recovery = preflight.recovery_backup_root / name
    if (
        native.is_symlink()
        or recovery.is_symlink()
        or not native.is_file()
        or not recovery.is_file()
    ):
        _fail()
    native_bytes = native.read_bytes()
    recovery_bytes = recovery.read_bytes()
    for content, role in ((native_bytes, "NATIVE"), (recovery_bytes, "RECOVERY")):
        try:
            value = parse_json_bytes(content, max_bytes=1_000_000)
        except (RuntimeError, ValueError) as error:
            raise PromotionEvidenceError(_INVALID) from error
        if (
            not isinstance(value, dict)
            or canonicalize(value) != content
            or value.get("schema_id") != "asklegal.local-backup-artifact/v1"
            or value.get("role") != role
            or value.get("request_fingerprint") != request.request_fingerprint
            or value.get("target_name") != target_name
        ):
            _fail()
    return native_bytes, recovery_bytes


def _retained_predecessor(
    preflight: V1PromotionPreflight, serving_state_id: str
) -> PromotionReadbackEvidence:
    """Resolve one exact prior terminal that identifies the active predecessor target."""
    root = preflight.state_root / "promotion-evidence"
    if root.is_symlink() or not root.is_dir():
        _fail()
    matches: list[PromotionReadbackEvidence] = []
    for path in sorted(root.glob("*.complete.json")):
        if path.name == f"{preflight.execution_lineage_id}.complete.json":
            continue
        if path.is_symlink() or not path.is_file():
            _fail()
        evidence = parse_promotion_readback(path.read_bytes())
        if evidence.serving_state_id == serving_state_id:
            matches.append(evidence)
    if len(matches) != 1:
        _fail()
    return matches[0]


def _validate_serving_transition(
    preflight: V1PromotionPreflight,
    result: PromotionExecutionResult,
    content: bytes,
    target_name: str,
    operation: str,
) -> None:
    """Prove the retained CAS moved from the named from-side to the named to-side."""
    try:
        value = parse_json_bytes(content, max_bytes=1_000_000)
    except (RuntimeError, ValueError) as error:
        raise PromotionEvidenceError(_INVALID) from error
    expected_candidate: dict[str, JsonValue] = {
        "approval_id": preflight.approval_id,
        "candidate_serving_state_id": preflight.manifest.candidate_serving_state_id,
        "candidate_serving_state_fingerprint": (
            preflight.manifest.candidate_serving_state_fingerprint
        ),
        "coverage_fingerprint": preflight.manifest.coverage_status.fingerprint,
        "desired_inventory_fingerprint": preflight.manifest.desired_state.inventory_fingerprint,
        "embedding_profile_fingerprint": preflight.manifest.embedding_profile.profile_fingerprint,
        "embedding_profile_id": preflight.manifest.embedding_profile.profile_id,
        "execution_lineage_id": preflight.execution_lineage_id,
        "predecessor_state_id": preflight.manifest.rollback_serving_state_id,
        "target_name": target_name,
    }
    if (
        not isinstance(value, dict)
        or canonicalize(value) != content
        or set(value) != {"activation", "active_state_id", "rollback", "schema_id"}
        or value.get("schema_id") != "asklegal.local-serving-state/v1"
    ):
        _fail()
    activation = value.get("activation")
    rollback = value.get("rollback")
    if (
        not isinstance(activation, dict)
        or set(activation) != {"candidate", "receipt_id"}
        or activation.get("candidate") != expected_candidate
        or activation.get("receipt_id") != result.routing_receipt_ref
    ):
        _fail()
    if operation == "PROMOTION":
        if (
            value.get("active_state_id") != preflight.manifest.candidate_serving_state_id
            or rollback is not None
            or result.rollback_receipt_ref != ""
        ):
            _fail()
        return
    if (
        not isinstance(rollback, dict)
        or set(rollback) != {"candidate", "receipt_id"}
        or rollback.get("candidate") != expected_candidate
        or rollback.get("receipt_id") != result.rollback_receipt_ref
        or value.get("active_state_id") != preflight.manifest.rollback_serving_state_id
    ):
        _fail()


def _persist(root: Path, lineage: str, suffix: str, content: bytes) -> Path:
    evidence_root = root / "promotion-evidence"
    evidence_root.mkdir(mode=0o700, exist_ok=True)
    path = evidence_root / f"{lineage}.{suffix}.json"
    with exclusive_local_state_lock(path):
        if path.exists():
            if path.is_symlink() or path.read_bytes() != content:
                _fail()
        else:
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
    if path.read_bytes() != content:
        _fail()
    return path


def retain_promotion_readback(
    preflight: V1PromotionPreflight,
    result: PromotionExecutionResult,
) -> Path:
    """Persist success only after service readback, backup and Serving-State verification."""
    if (
        type(result) is not PromotionExecutionResult
        or result.execution_lineage_id != preflight.execution_lineage_id
        or result.manifest_id != preflight.manifest.manifest_id
        or result.state not in {"EXECUTION_SUCCEEDED", "EXECUTION_ROLLED_BACK"}
        or not result.native_backup_receipt_ref
        or not result.recovery_receipt_ref
    ):
        _fail()
    target_name = pinecone_index_name(
        preflight.manifest.environment,
        preflight.manifest.jurisdiction,
        preflight.manifest.freeze_date,
        preflight.manifest.candidate_serving_state_fingerprint,
        preflight.manifest.project_id,
    )
    if result.target_name != target_name:
        _fail()
    operation = "PROMOTION" if result.state == "EXECUTION_SUCCEEDED" else "ROLLBACK"
    state = preflight.serving_states.canonical_bytes()
    _validate_serving_transition(preflight, result, state, target_name, operation)
    native, recovery = _backup_bytes(preflight, target_name)
    serving_state_id = (
        preflight.manifest.candidate_serving_state_id
        if operation == "PROMOTION"
        else preflight.manifest.rollback_serving_state_id
    )
    if preflight.serving_states.active_state_id != serving_state_id:
        _fail()
    backup = canonicalize(
        checked_json_value(
            {
                "native_fingerprint": _fingerprint(native),
                "recovery_fingerprint": _fingerprint(recovery),
            }
        )
    )
    readback = canonicalize(
        checked_json_value(
            {
                "embedding_receipt_ids": list(result.embedding_receipt_ids),
                "routing_receipt_ref": result.routing_receipt_ref,
                "serving_state_bytes_fingerprint": _fingerprint(state),
            }
        )
    )
    predecessor = (
        None if operation == "PROMOTION" else _retained_predecessor(preflight, serving_state_id)
    )
    predecessor_serving_state_id = (
        preflight.manifest.base_serving_state_id
        if operation == "PROMOTION"
        else preflight.manifest.candidate_serving_state_id
    )
    emitted_target_name = result.target_name if predecessor is None else predecessor.target_name
    emitted_target_fingerprint = (
        target_state_fingerprint(
            target_name,
            preflight.serving_profile.dimensions,
            preflight.serving_profile.metric,
            preflight.serving_profile.namespace,
        )
        if predecessor is None
        else predecessor.target_fingerprint
    )
    body: dict[str, JsonValue] = {
        "schema_id": _REPORT_SCHEMA,
        "schema_version": _VERSION,
        "operation": operation,
        "proposal_fingerprint": _proposal_fingerprint(preflight),
        "approval_fingerprint": preflight.approvals.decision_fingerprint(preflight.approval_id),
        "predecessor_serving_state_id": predecessor_serving_state_id,
        "predecessor_serving_state_fingerprint": (
            None if predecessor is None else preflight.manifest.candidate_serving_state_fingerprint
        ),
        "predecessor_target_name": None if predecessor is None else result.target_name,
        "predecessor_target_fingerprint": (
            None
            if predecessor is None
            else target_state_fingerprint(
                target_name,
                preflight.serving_profile.dimensions,
                preflight.serving_profile.metric,
                preflight.serving_profile.namespace,
            )
        ),
        "serving_state_id": serving_state_id,
        "serving_state_fingerprint": (
            preflight.manifest.candidate_serving_state_fingerprint
            if predecessor is None
            else predecessor.serving_state_fingerprint
        ),
        "target_name": emitted_target_name,
        "target_fingerprint": emitted_target_fingerprint,
        "backup_fingerprint": (
            _fingerprint(backup) if predecessor is None else predecessor.backup_fingerprint
        ),
        "readback_fingerprint": (
            _fingerprint(readback) if predecessor is None else predecessor.readback_fingerprint
        ),
        "result": "COMPLETE",
    }
    return _persist(preflight.state_root, preflight.execution_lineage_id, "complete", _sealed(body))


def retain_promotion_failure_stop(
    preflight: V1PromotionPreflight,
    *,
    before_state: bytes,
    failure_code: str,
) -> Path:
    """Persist a failure stop only when the exact Serving State did not move."""
    after_state = preflight.serving_states.canonical_bytes()
    if (
        type(before_state) is not bytes
        or not before_state
        or before_state != after_state
        or type(failure_code) is not str
        or not failure_code
    ):
        _fail()
    body: dict[str, JsonValue] = {
        "schema_id": _FAILURE_SCHEMA,
        "schema_version": _VERSION,
        "approval_fingerprint": preflight.approvals.decision_fingerprint(preflight.approval_id),
        "execution_lineage_id": preflight.execution_lineage_id,
        "failure_code": failure_code,
        "proposal_fingerprint": _proposal_fingerprint(preflight),
        "serving_state_fingerprint": _fingerprint(before_state),
        "serving_state_id": preflight.current_serving_state_id,
        "result": "STOPPED_NO_SERVING_STATE_CHANGE",
    }
    return _persist(preflight.state_root, preflight.execution_lineage_id, "failure", _sealed(body))
