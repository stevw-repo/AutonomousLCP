"""Unwired source-neutral durable blocked-work contract for Hong Kong Cases."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol, SupportsIndex, TypeGuard
from weakref import ReferenceType, ref

_MAX_TEXT_LENGTH = 512
_FINGERPRINT_LENGTH = 71
_CHECKPOINT_SNAPSHOT_LENGTH = 6
_MAX_CHECKPOINT_BYTES = 16_384
_REQUEST_SCHEMA = "asklegal.hk-case-work-request/v1"
_CHECKPOINT_SCHEMA = "asklegal.hk-case-work-checkpoint/v1"
_OPAQUE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,511}")
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_REQUEST_FIELDS = (
    "workflow_version",
    "source_cycle_ref",
    "source_cycle_fingerprint",
    "accounting_checkpoint_ref",
    "accounting_checkpoint_fingerprint",
    "withholding_checkpoint_ref",
    "withholding_checkpoint_fingerprint",
    "listing_id",
    "stage",
    "subject_fingerprint",
    "input_fingerprint",
)


class HKCaseWorkStage(StrEnum):
    """Closed source-neutral work stages."""

    PROPOSITION_DECISION = "PROPOSITION_DECISION"
    PROPOSITION_CHALLENGE = "PROPOSITION_CHALLENGE"
    TREATMENT_DECISION = "TREATMENT_DECISION"
    TREATMENT_CHALLENGE = "TREATMENT_CHALLENGE"


class HKCaseWorkCheckpointStatus(StrEnum):
    """The only truthful Task 6A checkpoint state."""

    BLOCKED_SEMANTIC_CAPABILITY_DISABLED = "BLOCKED_SEMANTIC_CAPABILITY_DISABLED"


HK_CASE_WORK_REQUIRED_BLOCKERS = (
    "AUTHENTIC_INVENTORY_NOT_ADMITTED",
    "CURRENT_AUTHORITY_NOT_ESTABLISHED",
    "REGISTER_IDENTITY_ISSUANCE_UNAVAILABLE",
    "SEMANTIC_WORKFLOW_NOT_ADMITTED",
    "SEMANTIC_CAPABILITY_DISABLED",
)


class HKCaseWorkErrorCode(StrEnum):
    """Closed durable-work failures."""

    REQUEST_INVALID = "HK_CASE_WORK_REQUEST_INVALID"
    CHECKPOINT_INVALID = "HK_CASE_WORK_CHECKPOINT_INVALID"
    IDENTITY_CONFLICT = "HK_CASE_WORK_IDENTITY_CONFLICT"
    REPLAY_MISMATCH = "HK_CASE_WORK_REPLAY_MISMATCH"
    CHECKPOINT_MISSING = "HK_CASE_WORK_CHECKPOINT_MISSING"
    POSITIVE_RESULT_UNSUPPORTED = "HK_CASE_WORK_POSITIVE_RESULT_UNSUPPORTED"


class HKCaseWorkError(ValueError):
    """Sanitized Task 6A boundary failure."""

    def __init__(self, code: HKCaseWorkErrorCode) -> None:
        """Expose only the stable closed code."""
        self.code = code
        super().__init__(code.value)


def _fingerprint_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _raise_type_error() -> None:
    raise TypeError


def _is_exact_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return type(value) is tuple


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _text(value: object) -> str:
    if type(value) is not str or not value or len(value) > _MAX_TEXT_LENGTH:
        raise TypeError
    return value


def _fingerprint(value: object) -> str:
    text = _text(value)
    if len(text) != _FINGERPRINT_LENGTH or _FINGERPRINT.fullmatch(text) is None:
        raise TypeError
    return text


def _opaque_ref(value: object) -> str:
    text = _text(value)
    if "://" in text or _OPAQUE_REF.fullmatch(text) is None:
        raise TypeError
    return text


def _work_item_id(value: object) -> str:
    text = _text(value)
    prefix = "hk-case-work:"
    if len(text) != len(prefix) + 64 or not text.startswith(prefix):
        raise TypeError
    int(text[len(prefix) :], 16)
    return text


@dataclass(frozen=True, slots=True)
class HKCaseWorkRequest:
    """Exact opaque inputs used to derive one orchestration identity."""

    workflow_version: str
    source_cycle_ref: str
    source_cycle_fingerprint: str
    accounting_checkpoint_ref: str
    accounting_checkpoint_fingerprint: str
    withholding_checkpoint_ref: str
    withholding_checkpoint_fingerprint: str
    listing_id: str
    stage: HKCaseWorkStage
    subject_fingerprint: str
    input_fingerprint: str


@dataclass(frozen=True, slots=True)
class _RequestSnapshot:
    workflow_version: str
    source_cycle_ref: str
    source_cycle_fingerprint: str
    accounting_checkpoint_ref: str
    accounting_checkpoint_fingerprint: str
    withholding_checkpoint_ref: str
    withholding_checkpoint_fingerprint: str
    listing_id: str
    stage: HKCaseWorkStage
    subject_fingerprint: str
    input_fingerprint: str


def _capture_request(value: object) -> tuple[object, ...]:
    if type(value) is not HKCaseWorkRequest:
        raise TypeError
    return tuple(object.__getattribute__(value, name) for name in _REQUEST_FIELDS)


def _validate_request_snapshot(raw: tuple[object, ...]) -> _RequestSnapshot:
    if type(raw) is not tuple or len(raw) != len(_REQUEST_FIELDS):
        raise TypeError
    stage = raw[8]
    if type(stage) is not HKCaseWorkStage:
        raise TypeError
    return _RequestSnapshot(
        _opaque_ref(raw[0]),
        _opaque_ref(raw[1]),
        _fingerprint(raw[2]),
        _opaque_ref(raw[3]),
        _fingerprint(raw[4]),
        _opaque_ref(raw[5]),
        _fingerprint(raw[6]),
        _opaque_ref(raw[7]),
        stage,
        _fingerprint(raw[9]),
        _fingerprint(raw[10]),
    )


def _request_from_snapshot(snapshot: _RequestSnapshot) -> HKCaseWorkRequest:
    result = object.__new__(HKCaseWorkRequest)
    for name, value in (
        ("workflow_version", snapshot.workflow_version),
        ("source_cycle_ref", snapshot.source_cycle_ref),
        ("source_cycle_fingerprint", snapshot.source_cycle_fingerprint),
        ("accounting_checkpoint_ref", snapshot.accounting_checkpoint_ref),
        ("accounting_checkpoint_fingerprint", snapshot.accounting_checkpoint_fingerprint),
        ("withholding_checkpoint_ref", snapshot.withholding_checkpoint_ref),
        ("withholding_checkpoint_fingerprint", snapshot.withholding_checkpoint_fingerprint),
        ("listing_id", snapshot.listing_id),
        ("stage", snapshot.stage),
        ("subject_fingerprint", snapshot.subject_fingerprint),
        ("input_fingerprint", snapshot.input_fingerprint),
    ):
        object.__setattr__(result, name, value)
    return result


def snapshot_hk_case_work_request(value: object) -> HKCaseWorkRequest:
    """Capture every request primitive before validation or reentrant work."""
    try:
        snapshot = _validate_request_snapshot(_capture_request(value))
        return _request_from_snapshot(snapshot)
    except AttributeError, TypeError, ValueError:
        raise HKCaseWorkError(HKCaseWorkErrorCode.REQUEST_INVALID) from None


def _request_document(snapshot: _RequestSnapshot) -> dict[str, object]:
    return {
        "schema_id": _REQUEST_SCHEMA,
        "workflow_version": snapshot.workflow_version,
        "source_cycle_ref": snapshot.source_cycle_ref,
        "source_cycle_fingerprint": snapshot.source_cycle_fingerprint,
        "accounting_checkpoint_ref": snapshot.accounting_checkpoint_ref,
        "accounting_checkpoint_fingerprint": snapshot.accounting_checkpoint_fingerprint,
        "withholding_checkpoint_ref": snapshot.withholding_checkpoint_ref,
        "withholding_checkpoint_fingerprint": snapshot.withholding_checkpoint_fingerprint,
        "listing_id": snapshot.listing_id,
        "stage": snapshot.stage.value,
        "subject_fingerprint": snapshot.subject_fingerprint,
        "input_fingerprint": snapshot.input_fingerprint,
    }


@dataclass(frozen=True, slots=True)
class HKCaseWorkIdentity:
    """Deterministic orchestration identity, never a legal identity."""

    work_item_id: str
    workflow_version: str
    source_cycle_ref: str
    source_cycle_fingerprint: str
    accounting_checkpoint_ref: str
    accounting_checkpoint_fingerprint: str
    withholding_checkpoint_ref: str
    withholding_checkpoint_fingerprint: str
    listing_id: str
    stage: HKCaseWorkStage
    subject_fingerprint: str
    input_fingerprint: str

    def __post_init__(self) -> None:
        """Validate every opaque authority and the derived work ID."""
        try:
            _validate_identity_snapshot(_capture_identity(self))
        except AttributeError, TypeError, ValueError:
            raise HKCaseWorkError(HKCaseWorkErrorCode.REQUEST_INVALID) from None

    def facts(self, *, include_id: bool) -> dict[str, object]:
        """Return the complete canonical primitive projection."""
        snapshot = _validate_identity_snapshot(_capture_identity(self))
        return _identity_document(snapshot, include_id=include_id)


@dataclass(frozen=True, slots=True)
class _IdentitySnapshot:
    work_item_id: str
    request: _RequestSnapshot


def _capture_identity(value: object) -> tuple[object, ...]:
    if type(value) is not HKCaseWorkIdentity:
        raise TypeError
    return (
        object.__getattribute__(value, "work_item_id"),
        *(object.__getattribute__(value, name) for name in _REQUEST_FIELDS),
    )


def _validate_identity_snapshot(raw: tuple[object, ...]) -> _IdentitySnapshot:
    if type(raw) is not tuple or len(raw) != len(_REQUEST_FIELDS) + 1:
        raise TypeError
    work_item_id = _work_item_id(raw[0])
    request_snapshot = _validate_request_snapshot(raw[1:])
    expected = (
        f"hk-case-work:{_fingerprint_bytes(_canonical(_request_document(request_snapshot)))[7:]}"
    )
    if work_item_id != expected:
        raise TypeError
    return _IdentitySnapshot(work_item_id, request_snapshot)


def _identity_from_snapshot(snapshot: _IdentitySnapshot) -> HKCaseWorkIdentity:
    request = snapshot.request
    result = object.__new__(HKCaseWorkIdentity)
    for name, value in (
        ("work_item_id", snapshot.work_item_id),
        ("workflow_version", request.workflow_version),
        ("source_cycle_ref", request.source_cycle_ref),
        ("source_cycle_fingerprint", request.source_cycle_fingerprint),
        ("accounting_checkpoint_ref", request.accounting_checkpoint_ref),
        ("accounting_checkpoint_fingerprint", request.accounting_checkpoint_fingerprint),
        ("withholding_checkpoint_ref", request.withholding_checkpoint_ref),
        ("withholding_checkpoint_fingerprint", request.withholding_checkpoint_fingerprint),
        ("listing_id", request.listing_id),
        ("stage", request.stage),
        ("subject_fingerprint", request.subject_fingerprint),
        ("input_fingerprint", request.input_fingerprint),
    ):
        object.__setattr__(result, name, value)
    return result


def _identity_document(snapshot: _IdentitySnapshot, *, include_id: bool) -> dict[str, object]:
    document = _request_document(snapshot.request)
    if include_id:
        document["work_item_id"] = snapshot.work_item_id
    return document


def build_hk_case_work_identity(request: HKCaseWorkRequest) -> HKCaseWorkIdentity:
    """Derive one stable work ID from a detached exact request snapshot."""
    detached = snapshot_hk_case_work_request(request)
    snapshot = _validate_request_snapshot(_capture_request(detached))
    work_id = f"hk-case-work:{_fingerprint_bytes(_canonical(_request_document(snapshot)))[7:]}"
    return _identity_from_snapshot(_IdentitySnapshot(work_id, snapshot))


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKCaseWorkCheckpoint:
    """Immutable terminal negative checkpoint with no positive-result fields."""

    identity: HKCaseWorkIdentity
    status: HKCaseWorkCheckpointStatus
    blocker_codes: tuple[str, ...]
    result_ref: None
    result_fingerprint: None
    checkpoint_fingerprint: str

    def __post_init__(self) -> None:
        """Recompute the complete negative checkpoint projection."""
        try:
            _validate_checkpoint_snapshot(_capture_checkpoint(self))
        except HKCaseWorkError:
            raise
        except AttributeError, TypeError, ValueError:
            raise HKCaseWorkError(HKCaseWorkErrorCode.CHECKPOINT_INVALID) from None

    def __copy__(self) -> HKCaseWorkCheckpoint:
        """Return a detached, structurally replayable shallow copy."""
        return _checkpoint_from_snapshot(_validate_checkpoint_snapshot(_capture_checkpoint(self)))

    def __deepcopy__(self, memo: dict[int, object]) -> HKCaseWorkCheckpoint:
        """Return a detached, structurally replayable deep copy."""
        del memo
        return _checkpoint_from_snapshot(_validate_checkpoint_snapshot(_capture_checkpoint(self)))


def _capture_checkpoint(value: object) -> tuple[object, ...]:
    if type(value) is not HKCaseWorkCheckpoint:
        raise TypeError
    identity = object.__getattribute__(value, "identity")
    identity_snapshot = _capture_identity(identity)
    return (
        identity_snapshot,
        object.__getattribute__(value, "status"),
        object.__getattribute__(value, "blocker_codes"),
        object.__getattribute__(value, "result_ref"),
        object.__getattribute__(value, "result_fingerprint"),
        object.__getattribute__(value, "checkpoint_fingerprint"),
    )


def _validate_blocker_codes(value: object) -> tuple[str, ...]:
    if not _is_exact_tuple(value):
        raise TypeError
    typed = tuple(_text(item) for item in value)
    if typed != HK_CASE_WORK_REQUIRED_BLOCKERS:
        raise TypeError
    return typed


def _checkpoint_document(
    identity_snapshot: _IdentitySnapshot,
    blocker_codes: tuple[str, ...],
    *,
    include_fingerprint: str | None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_id": _CHECKPOINT_SCHEMA,
        "identity": _identity_document(identity_snapshot, include_id=True),
        "status": HKCaseWorkCheckpointStatus.BLOCKED_SEMANTIC_CAPABILITY_DISABLED.value,
        "blocker_codes": list(blocker_codes),
        "result_ref": None,
        "result_fingerprint": None,
    }
    if include_fingerprint is not None:
        document["checkpoint_fingerprint"] = include_fingerprint
    return document


@dataclass(frozen=True, slots=True)
class _CheckpointSnapshot:
    identity: _IdentitySnapshot
    status: HKCaseWorkCheckpointStatus
    blocker_codes: tuple[str, ...]
    checkpoint_fingerprint: str


def _validate_checkpoint_snapshot(raw: tuple[object, ...]) -> _CheckpointSnapshot:
    if type(raw) is not tuple or len(raw) != _CHECKPOINT_SNAPSHOT_LENGTH:
        raise TypeError
    nested_identity = raw[0]
    if not _is_exact_tuple(nested_identity):
        raise TypeError
    identity_snapshot = _validate_identity_snapshot(nested_identity)
    status = raw[1]
    blocker_codes = _validate_blocker_codes(raw[2])
    if raw[3] is not None or raw[4] is not None:
        raise HKCaseWorkError(HKCaseWorkErrorCode.POSITIVE_RESULT_UNSUPPORTED)
    if (
        type(status) is not HKCaseWorkCheckpointStatus
        or status is not HKCaseWorkCheckpointStatus.BLOCKED_SEMANTIC_CAPABILITY_DISABLED
    ):
        raise TypeError
    fingerprint = _fingerprint(raw[5])
    expected = _fingerprint_bytes(
        _canonical(_checkpoint_document(identity_snapshot, blocker_codes, include_fingerprint=None))
    )
    if fingerprint != expected:
        raise TypeError
    return _CheckpointSnapshot(identity_snapshot, status, blocker_codes, fingerprint)


def _checkpoint_from_snapshot(snapshot: _CheckpointSnapshot) -> HKCaseWorkCheckpoint:
    result = object.__new__(HKCaseWorkCheckpoint)
    for name, value in (
        ("identity", _identity_from_snapshot(snapshot.identity)),
        ("status", snapshot.status),
        ("blocker_codes", snapshot.blocker_codes),
        ("result_ref", None),
        ("result_fingerprint", None),
        ("checkpoint_fingerprint", snapshot.checkpoint_fingerprint),
    ):
        object.__setattr__(result, name, value)
    return result


def _canonical_checkpoint_snapshot(snapshot: _CheckpointSnapshot) -> bytes:
    return _canonical(
        _checkpoint_document(
            snapshot.identity,
            snapshot.blocker_codes,
            include_fingerprint=snapshot.checkpoint_fingerprint,
        )
    )


type HKCaseWorkPreparedWrite = tuple[
    HKCaseWorkCheckpoint,
    bytes,
    str,
    str,
    tuple[str, ...],
]


class HKCaseWorkCheckpointFactory:
    """Process-local issuer for structurally durable blocked checkpoints."""

    __slots__ = ("_issued",)

    def __init__(self) -> None:
        """Create a new non-transferable issuance registry."""
        self._issued: dict[int, tuple[ReferenceType[HKCaseWorkCheckpoint], bytes]] = {}

    def __copy__(self) -> HKCaseWorkCheckpointFactory:
        """Reject copying of process-local issuance authority."""
        raise HKCaseWorkError(HKCaseWorkErrorCode.REPLAY_MISMATCH)

    def __deepcopy__(self, memo: dict[int, object]) -> HKCaseWorkCheckpointFactory:
        """Reject deep copying of process-local issuance authority."""
        del memo
        raise HKCaseWorkError(HKCaseWorkErrorCode.REPLAY_MISMATCH)

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[object, ...]:
        """Reject serialization of process-local issuance authority."""
        del protocol
        raise HKCaseWorkError(HKCaseWorkErrorCode.REPLAY_MISMATCH)

    def issue_blocked(
        self, identity: HKCaseWorkIdentity, blocker_codes: tuple[str, ...]
    ) -> HKCaseWorkCheckpoint:
        """Issue the sole blocked checkpoint from fully detached primitives."""
        try:
            identity_snapshot = _validate_identity_snapshot(_capture_identity(identity))
            blockers = _validate_blocker_codes(blocker_codes)
            fingerprint = _fingerprint_bytes(
                _canonical(
                    _checkpoint_document(identity_snapshot, blockers, include_fingerprint=None)
                )
            )
            snapshot = _CheckpointSnapshot(
                identity_snapshot,
                HKCaseWorkCheckpointStatus.BLOCKED_SEMANTIC_CAPABILITY_DISABLED,
                blockers,
                fingerprint,
            )
            checkpoint = _checkpoint_from_snapshot(snapshot)
            canonical = _canonical_checkpoint_snapshot(snapshot)
            self._issued[id(checkpoint)] = (ref(checkpoint), canonical)
        except HKCaseWorkError:
            raise
        except AttributeError, TypeError, ValueError:
            raise HKCaseWorkError(HKCaseWorkErrorCode.CHECKPOINT_INVALID) from None
        else:
            return checkpoint

    def assert_issued(self, checkpoint: HKCaseWorkCheckpoint) -> HKCaseWorkCheckpoint:
        """Require the exact original object and immutable factory projection."""
        try:
            self._issued_snapshot(checkpoint)
        except AttributeError, KeyError, TypeError, ValueError, HKCaseWorkError:
            raise HKCaseWorkError(HKCaseWorkErrorCode.REPLAY_MISMATCH) from None
        else:
            return checkpoint

    def prepare_port_write(self, checkpoint: HKCaseWorkCheckpoint) -> HKCaseWorkPreparedWrite:
        """Derive port value and expected primitives only from one private exact snapshot."""
        try:
            snapshot = self._issued_snapshot(checkpoint)
            canonical = _canonical_checkpoint_snapshot(snapshot)
            return (
                _checkpoint_from_snapshot(snapshot),
                canonical,
                snapshot.identity.work_item_id,
                snapshot.checkpoint_fingerprint,
                snapshot.blocker_codes,
            )
        except HKCaseWorkError:
            raise
        except AttributeError, KeyError, TypeError, ValueError:
            raise HKCaseWorkError(HKCaseWorkErrorCode.REPLAY_MISMATCH) from None

    def returned_projection(
        self, checkpoint: HKCaseWorkCheckpoint, expected_canonical: bytes
    ) -> tuple[str, str, tuple[str, ...]]:
        """Validate returned detached facts without invoking caller methods."""
        try:
            if type(expected_canonical) is not bytes:
                _raise_type_error()
            snapshot = _validate_checkpoint_snapshot(_capture_checkpoint(checkpoint))
            if _canonical_checkpoint_snapshot(snapshot) != expected_canonical:
                _raise_type_error()
        except HKCaseWorkError:
            raise
        except AttributeError, TypeError, ValueError:
            raise HKCaseWorkError(HKCaseWorkErrorCode.REPLAY_MISMATCH) from None
        else:
            return (
                snapshot.identity.work_item_id,
                snapshot.checkpoint_fingerprint,
                snapshot.blocker_codes,
            )

    def _issued_snapshot(self, checkpoint: HKCaseWorkCheckpoint) -> _CheckpointSnapshot:
        if type(checkpoint) is not HKCaseWorkCheckpoint:
            raise TypeError
        snapshot = _validate_checkpoint_snapshot(_capture_checkpoint(checkpoint))
        canonical = _canonical_checkpoint_snapshot(snapshot)
        issued_ref, expected = self._issued[id(checkpoint)]
        if issued_ref() is not checkpoint or canonical != expected:
            raise TypeError
        return snapshot


def build_blocked_hk_case_work_checkpoint(
    identity: HKCaseWorkIdentity, blocker_codes: tuple[str, ...]
) -> HKCaseWorkCheckpoint:
    """Issue a blocked checkpoint for callers that do not retain factory authority."""
    return HKCaseWorkCheckpointFactory().issue_blocked(identity, blocker_codes)


def replay_hk_case_work_checkpoint(value: HKCaseWorkCheckpoint) -> HKCaseWorkCheckpoint:
    """Strictly replay one exact durable negative checkpoint."""
    try:
        _validate_checkpoint_snapshot(_capture_checkpoint(value))
    except HKCaseWorkError:
        raise
    except AttributeError, TypeError, ValueError:
        raise HKCaseWorkError(HKCaseWorkErrorCode.CHECKPOINT_INVALID) from None
    else:
        return value


def canonical_hk_case_work_checkpoint(value: HKCaseWorkCheckpoint) -> bytes:
    """Return deterministic canonical checkpoint bytes."""
    try:
        snapshot = _validate_checkpoint_snapshot(_capture_checkpoint(value))
        return _canonical_checkpoint_snapshot(snapshot)
    except HKCaseWorkError:
        raise
    except AttributeError, TypeError, ValueError:
        raise HKCaseWorkError(HKCaseWorkErrorCode.CHECKPOINT_INVALID) from None


class HKCaseWorkCheckpointStore(Protocol):
    """Authoritative blocked-checkpoint port."""

    def record_checkpoint(
        self, checkpoint: HKCaseWorkCheckpoint, expected_canonical: bytes
    ) -> HKCaseWorkCheckpoint:
        """Record or replay one checkpoint bound to pre-callback canonical bytes."""
        ...

    def get_checkpoint(self, work_item_id: str) -> HKCaseWorkCheckpoint:
        """Read one exact checkpoint or fail missing."""
        ...


class InMemoryHKCaseWorkCheckpointStore:
    """Deterministic fake whose state may outlive a recreated service object."""

    def __init__(self) -> None:
        """Create empty authoritative fake state."""
        self._values: dict[str, HKCaseWorkCheckpoint] = {}

    def record_checkpoint(
        self, checkpoint: HKCaseWorkCheckpoint, expected_canonical: bytes
    ) -> HKCaseWorkCheckpoint:
        """Adopt once, replay exactly, and reject divergent identity reuse."""
        try:
            if (
                type(expected_canonical) is not bytes
                or not expected_canonical
                or len(expected_canonical) > _MAX_CHECKPOINT_BYTES
            ):
                _raise_type_error()
            incoming = _checkpoint_from_snapshot(
                _validate_checkpoint_snapshot(_capture_checkpoint(checkpoint))
            )
            incoming_snapshot = _validate_checkpoint_snapshot(_capture_checkpoint(incoming))
            incoming_canonical = _canonical_checkpoint_snapshot(incoming_snapshot)
            if incoming_canonical != expected_canonical:
                _raise_type_error()
        except HKCaseWorkError:
            raise
        except AttributeError, TypeError, ValueError:
            raise HKCaseWorkError(HKCaseWorkErrorCode.CHECKPOINT_INVALID) from None
        work_item_id = incoming.identity.work_item_id
        current = self._values.get(work_item_id)
        if current is not None:
            current_snapshot = _validate_checkpoint_snapshot(_capture_checkpoint(current))
            if _canonical_checkpoint_snapshot(current_snapshot) != incoming_canonical:
                raise HKCaseWorkError(HKCaseWorkErrorCode.IDENTITY_CONFLICT)
        if current is None:
            self._values[work_item_id] = incoming
        stored_snapshot = _validate_checkpoint_snapshot(
            _capture_checkpoint(self._values[work_item_id])
        )
        return _checkpoint_from_snapshot(stored_snapshot)

    def get_checkpoint(self, work_item_id: str) -> HKCaseWorkCheckpoint:
        """Read one detached checkpoint by deterministic work identity."""
        try:
            key = _work_item_id(work_item_id)
        except TypeError, ValueError:
            raise HKCaseWorkError(HKCaseWorkErrorCode.CHECKPOINT_MISSING) from None
        try:
            snapshot = _validate_checkpoint_snapshot(_capture_checkpoint(self._values[key]))
            return _checkpoint_from_snapshot(snapshot)
        except KeyError:
            raise HKCaseWorkError(HKCaseWorkErrorCode.CHECKPOINT_MISSING) from None
