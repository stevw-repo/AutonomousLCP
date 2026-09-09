"""Provider-neutral independent backup read-back verification.

This module defines only an uncomposed local contract kernel.  Its injected
ports may later be implemented by a provider-native backup adapter and a
separately administered recovery-copy adapter, but this module has no network,
credential, provider, vault, SQL, or Serving State capability.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from types import TracebackType
from typing import Never, Self

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType

from .model import BackupVerification, OutcomeUnknown, PromotionError, PromotionErrorCode

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_BACKEND_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_TARGET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
_ORDINARY_FAILURES = (OSError, RuntimeError, TypeError, ValueError)


class BackupRole(StrEnum):
    """Closed independently administered backup roles."""

    NATIVE = "NATIVE"
    RECOVERY = "RECOVERY"


@dataclass(frozen=True, slots=True)
class BackupRequest:
    """Exact immutable facts required to reproduce both backup artifacts."""

    target_name: str
    target_definition_ref: ImmutableReference
    desired_inventory_fingerprint: str
    backup_profile_ref: ImmutableReference
    source_export_ref: ImmutableReference
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class BackupAcknowledgement:
    """Non-authoritative provider acknowledgement for one role-specific write."""

    role: BackupRole
    backend_id: str
    request_fingerprint: str
    receipt_ref: ImmutableReference
    evidence_ref: ImmutableReference


@dataclass(frozen=True, slots=True)
class BackupReadback:
    """Complete independently read-back facts for one backup artifact."""

    role: BackupRole
    backend_id: str
    request_fingerprint: str
    target_name: str
    target_definition_ref: ImmutableReference
    desired_inventory_fingerprint: str
    backup_profile_ref: ImmutableReference
    source_export_ref: ImmutableReference
    artifact_ref: ImmutableReference
    receipt_ref: ImmutableReference
    evidence_ref: ImmutableReference


@dataclass(frozen=True, slots=True, init=False)
class VerifiedBackupPair:
    """Two distinct exact read-backs verified against one frozen request."""

    request_fingerprint: str
    native_backend_id: str
    recovery_backend_id: str
    native_artifact_ref: ImmutableReference
    recovery_artifact_ref: ImmutableReference
    native_receipt_ref: ImmutableReference
    recovery_receipt_ref: ImmutableReference
    native_evidence_ref: ImmutableReference
    recovery_evidence_ref: ImmutableReference
    fingerprint: str

    def __init__(self) -> None:
        """Forbid constructing a verified result without the verifier."""
        message = "verified backup pairs are issued only after both read-backs"
        raise TypeError(message)


class NativeBackupPort(ABC):
    """Nominal native-backup write and independent read-back boundary."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Return one stable non-secret backend identity."""
        ...

    @abstractmethod
    def write_native(self, request: BackupRequest) -> BackupAcknowledgement:
        """Write or exactly replay one provider-native backup request."""
        ...

    @abstractmethod
    def read_native(self, request: BackupRequest) -> BackupReadback | None:
        """Read back the exact provider-native artifact or return no fact."""
        ...


class RecoveryCopyPort(ABC):
    """Nominal separately administered recovery-copy boundary."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Return one stable non-secret backend identity."""
        ...

    @abstractmethod
    def write_recovery(self, request: BackupRequest) -> BackupAcknowledgement:
        """Write or exactly replay one independent recovery-copy request."""
        ...

    @abstractmethod
    def read_recovery(self, request: BackupRequest) -> BackupReadback | None:
        """Read back the exact recovery artifact or return no fact."""
        ...


class IndependentBackupAdapter:
    """Bind one frozen backup request to two independently administered ports."""

    def __init__(
        self,
        request: BackupRequest,
        native: NativeBackupPort,
        recovery: RecoveryCopyPort,
    ) -> None:
        """Retain exact identities without performing either write."""
        self._request = request
        self._native = native
        self._recovery = recovery

    @property
    def backup_profile_ref(self) -> ImmutableReference:
        """Expose the immutable backup profile used by both paths."""
        return self._request.backup_profile_ref

    def create_and_verify(
        self,
        target_name: str,
        inventory_fingerprint: str,
        backup_profile_ref: ImmutableReference | None,
    ) -> BackupVerification:
        """Run the existing nominal dual-write/readback verifier for exact facts."""
        if (
            target_name != self._request.target_name
            or inventory_fingerprint != self._request.desired_inventory_fingerprint
            or backup_profile_ref is None
            or backup_profile_ref != self._request.backup_profile_ref
        ):
            _fail()
        pair = create_and_verify_backup(self._request, self._native, self._recovery)
        return BackupVerification(
            pair.native_receipt_ref.ref_id,
            pair.recovery_receipt_ref.ref_id,
            native_verified=True,
            recovery_verified=True,
        )


class _AdapterFailureBoundary:
    """Normalize every ordinary callback failure without catching BaseException."""

    def __enter__(self) -> Self:
        """Enter one synchronous adapter callback boundary."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """Map ordinary failures and preserve process-control exceptions."""
        del exception_type, traceback
        if exception is None:
            return False
        if isinstance(exception, Exception):
            _fail()
        return False


class _WriteFailureBoundary(_AdapterFailureBoundary):
    """Additionally recognize an unknown write acknowledgement for reconciliation."""

    outcome_unknown: bool

    def __init__(self) -> None:
        """Start with no observed acknowledgement loss."""
        self.outcome_unknown = False

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """Suppress only OutcomeUnknown so the exact read-back can decide."""
        if isinstance(exception, OutcomeUnknown):
            self.outcome_unknown = True
            return True
        return super().__exit__(exception_type, exception, traceback)


@dataclass(frozen=True, slots=True)
class _ReferenceSnapshot:
    ref_type: ReferenceType
    ref_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _RequestSnapshot:
    target_name: str
    target_definition_ref: _ReferenceSnapshot
    desired_inventory_fingerprint: str
    backup_profile_ref: _ReferenceSnapshot
    source_export_ref: _ReferenceSnapshot
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class _AcknowledgementSnapshot:
    role: BackupRole
    backend_id: str
    request_fingerprint: str
    receipt_ref: _ReferenceSnapshot
    evidence_ref: _ReferenceSnapshot


@dataclass(frozen=True, slots=True)
class _ReadbackSnapshot:
    role: BackupRole
    backend_id: str
    request_fingerprint: str
    target_name: str
    target_definition_ref: _ReferenceSnapshot
    desired_inventory_fingerprint: str
    backup_profile_ref: _ReferenceSnapshot
    source_export_ref: _ReferenceSnapshot
    artifact_ref: _ReferenceSnapshot
    receipt_ref: _ReferenceSnapshot
    evidence_ref: _ReferenceSnapshot


def freeze_backup_request(
    *,
    target_name: str,
    target_definition_ref: ImmutableReference,
    desired_inventory_fingerprint: str,
    backup_profile_ref: ImmutableReference,
    source_export_ref: ImmutableReference,
) -> BackupRequest:
    """Detach and fingerprint the exact facts both backup paths must reproduce."""
    try:
        snapshot = _RequestSnapshot(
            _target_name(target_name),
            _reference(
                target_definition_ref,
                frozenset({ReferenceType.PINECONE_INDEX_GENERATION}),
            ),
            _fingerprint(desired_inventory_fingerprint),
            _reference(
                backup_profile_ref,
                frozenset({ReferenceType.CAPABILITY_PROFILE}),
            ),
            _reference(
                source_export_ref,
                frozenset({ReferenceType.ARTIFACT, ReferenceType.EVIDENCE}),
            ),
            "",
        )
        fingerprint = _request_fingerprint(snapshot)
        return _request_from_snapshot(
            _RequestSnapshot(
                snapshot.target_name,
                snapshot.target_definition_ref,
                snapshot.desired_inventory_fingerprint,
                snapshot.backup_profile_ref,
                snapshot.source_export_ref,
                fingerprint,
            )
        )
    except PromotionError:
        raise
    except _ORDINARY_FAILURES:
        _fail()


def create_and_verify_backup(
    request: BackupRequest,
    native: object,
    recovery: object,
) -> VerifiedBackupPair:
    """Write/replay and independently read back two exact backup artifacts."""
    try:
        return _create_and_verify_backup(request, native, recovery)
    except PromotionError:
        raise
    except _ORDINARY_FAILURES:
        _fail()


def _create_and_verify_backup(
    request: BackupRequest,
    native: object,
    recovery: object,
) -> VerifiedBackupPair:
    if not isinstance(native, NativeBackupPort) or not isinstance(recovery, RecoveryCopyPort):
        _fail()
    if id(native) == id(recovery):
        _fail()
    expected = _request_snapshot(request)
    native_backend_id = _port_backend_identity(native)
    recovery_backend_id = _port_backend_identity(recovery)
    if native_backend_id == recovery_backend_id:
        _fail()

    native_ack = _write_native(native, expected, native_backend_id)
    native_fact = _read_native(native, expected, native_backend_id)
    _ack_matches_readback(native_ack, native_fact)

    recovery_ack = _write_recovery(recovery, expected, recovery_backend_id)
    recovery_fact = _read_recovery(recovery, expected, recovery_backend_id)
    _ack_matches_readback(recovery_ack, recovery_fact)

    if (
        _reference_identity(native_fact.artifact_ref)
        == _reference_identity(recovery_fact.artifact_ref)
        or _reference_identity(native_fact.receipt_ref)
        == _reference_identity(recovery_fact.receipt_ref)
        or _reference_identity(native_fact.evidence_ref)
        == _reference_identity(recovery_fact.evidence_ref)
    ):
        _fail()
    return _verified_pair(expected, native_fact, recovery_fact)


def _write_native(
    backend: NativeBackupPort,
    expected: _RequestSnapshot,
    backend_id: str,
) -> _AcknowledgementSnapshot | None:
    boundary = _WriteFailureBoundary()
    value: object | None = None
    with boundary:
        value = backend.write_native(_request_from_snapshot(expected))
    if boundary.outcome_unknown:
        return None
    return _acknowledgement_snapshot(value, BackupRole.NATIVE, backend_id, expected)


def _write_recovery(
    backend: RecoveryCopyPort,
    expected: _RequestSnapshot,
    backend_id: str,
) -> _AcknowledgementSnapshot | None:
    boundary = _WriteFailureBoundary()
    value: object | None = None
    with boundary:
        value = backend.write_recovery(_request_from_snapshot(expected))
    if boundary.outcome_unknown:
        return None
    return _acknowledgement_snapshot(value, BackupRole.RECOVERY, backend_id, expected)


def _read_native(
    backend: NativeBackupPort,
    expected: _RequestSnapshot,
    backend_id: str,
) -> _ReadbackSnapshot:
    value: object | None = None
    with _AdapterFailureBoundary():
        value = backend.read_native(_request_from_snapshot(expected))
    return _readback_snapshot(value, BackupRole.NATIVE, backend_id, expected)


def _read_recovery(
    backend: RecoveryCopyPort,
    expected: _RequestSnapshot,
    backend_id: str,
) -> _ReadbackSnapshot:
    value: object | None = None
    with _AdapterFailureBoundary():
        value = backend.read_recovery(_request_from_snapshot(expected))
    return _readback_snapshot(value, BackupRole.RECOVERY, backend_id, expected)


def _acknowledgement_snapshot(
    value: object,
    role: BackupRole,
    backend_id: str,
    expected: _RequestSnapshot,
) -> _AcknowledgementSnapshot:
    if not isinstance(value, BackupAcknowledgement) or type(value) is not BackupAcknowledgement:
        _fail()
    snapshot = _AcknowledgementSnapshot(
        _role(value.role),
        _backend_identity(value.backend_id),
        _fingerprint(value.request_fingerprint),
        _reference(value.receipt_ref, frozenset({ReferenceType.EFFECT_RECEIPT})),
        _reference(value.evidence_ref, frozenset({ReferenceType.EVIDENCE})),
    )
    if (
        snapshot.role is not role
        or snapshot.backend_id != backend_id
        or snapshot.request_fingerprint != expected.request_fingerprint
    ):
        _fail()
    return snapshot


def _readback_snapshot(
    value: object,
    role: BackupRole,
    backend_id: str,
    expected: _RequestSnapshot,
) -> _ReadbackSnapshot:
    if not isinstance(value, BackupReadback) or type(value) is not BackupReadback:
        _fail()
    snapshot = _ReadbackSnapshot(
        _role(value.role),
        _backend_identity(value.backend_id),
        _fingerprint(value.request_fingerprint),
        _target_name(value.target_name),
        _reference(
            value.target_definition_ref,
            frozenset({ReferenceType.PINECONE_INDEX_GENERATION}),
        ),
        _fingerprint(value.desired_inventory_fingerprint),
        _reference(
            value.backup_profile_ref,
            frozenset({ReferenceType.CAPABILITY_PROFILE}),
        ),
        _reference(
            value.source_export_ref,
            frozenset({ReferenceType.ARTIFACT, ReferenceType.EVIDENCE}),
        ),
        _reference(value.artifact_ref, frozenset({ReferenceType.ARTIFACT})),
        _reference(value.receipt_ref, frozenset({ReferenceType.EFFECT_RECEIPT})),
        _reference(value.evidence_ref, frozenset({ReferenceType.EVIDENCE})),
    )
    if (
        snapshot.role is not role
        or snapshot.backend_id != backend_id
        or snapshot.request_fingerprint != expected.request_fingerprint
        or snapshot.target_name != expected.target_name
        or snapshot.target_definition_ref != expected.target_definition_ref
        or snapshot.desired_inventory_fingerprint != expected.desired_inventory_fingerprint
        or snapshot.backup_profile_ref != expected.backup_profile_ref
        or snapshot.source_export_ref != expected.source_export_ref
    ):
        _fail()
    return snapshot


def _ack_matches_readback(
    acknowledgement: _AcknowledgementSnapshot | None,
    readback: _ReadbackSnapshot,
) -> None:
    if acknowledgement is None:
        return
    if (
        acknowledgement.role is not readback.role
        or acknowledgement.backend_id != readback.backend_id
        or acknowledgement.request_fingerprint != readback.request_fingerprint
        or acknowledgement.receipt_ref != readback.receipt_ref
        or acknowledgement.evidence_ref != readback.evidence_ref
    ):
        _fail()


def _verified_pair(
    request: _RequestSnapshot,
    native: _ReadbackSnapshot,
    recovery: _ReadbackSnapshot,
) -> VerifiedBackupPair:
    document = checked_json_value(
        {
            "native": _readback_document(native),
            "recovery": _readback_document(recovery),
            "request_fingerprint": request.request_fingerprint,
            "type": "asklegal.verified-backup-pair.local.v1",
        }
    )
    fingerprint = f"sha256:{sha256(canonicalize(document)).hexdigest()}"
    result = object.__new__(VerifiedBackupPair)
    object.__setattr__(result, "request_fingerprint", request.request_fingerprint)
    object.__setattr__(result, "native_backend_id", native.backend_id)
    object.__setattr__(result, "recovery_backend_id", recovery.backend_id)
    object.__setattr__(
        result,
        "native_artifact_ref",
        _reference_from_snapshot(native.artifact_ref),
    )
    object.__setattr__(
        result,
        "recovery_artifact_ref",
        _reference_from_snapshot(recovery.artifact_ref),
    )
    object.__setattr__(
        result,
        "native_receipt_ref",
        _reference_from_snapshot(native.receipt_ref),
    )
    object.__setattr__(
        result,
        "recovery_receipt_ref",
        _reference_from_snapshot(recovery.receipt_ref),
    )
    object.__setattr__(
        result,
        "native_evidence_ref",
        _reference_from_snapshot(native.evidence_ref),
    )
    object.__setattr__(
        result,
        "recovery_evidence_ref",
        _reference_from_snapshot(recovery.evidence_ref),
    )
    object.__setattr__(result, "fingerprint", fingerprint)
    return result


def _request_snapshot(value: object) -> _RequestSnapshot:
    if not isinstance(value, BackupRequest) or type(value) is not BackupRequest:
        _fail()
    snapshot = _RequestSnapshot(
        _target_name(value.target_name),
        _reference(
            value.target_definition_ref,
            frozenset({ReferenceType.PINECONE_INDEX_GENERATION}),
        ),
        _fingerprint(value.desired_inventory_fingerprint),
        _reference(
            value.backup_profile_ref,
            frozenset({ReferenceType.CAPABILITY_PROFILE}),
        ),
        _reference(
            value.source_export_ref,
            frozenset({ReferenceType.ARTIFACT, ReferenceType.EVIDENCE}),
        ),
        _fingerprint(value.request_fingerprint),
    )
    if _request_fingerprint(snapshot) != snapshot.request_fingerprint:
        _fail()
    return snapshot


def _request_from_snapshot(value: _RequestSnapshot) -> BackupRequest:
    return BackupRequest(
        value.target_name,
        _reference_from_snapshot(value.target_definition_ref),
        value.desired_inventory_fingerprint,
        _reference_from_snapshot(value.backup_profile_ref),
        _reference_from_snapshot(value.source_export_ref),
        value.request_fingerprint,
    )


def _request_fingerprint(value: _RequestSnapshot) -> str:
    document = checked_json_value(
        {
            "backup_profile_ref": _reference_document(value.backup_profile_ref),
            "desired_inventory_fingerprint": value.desired_inventory_fingerprint,
            "source_export_ref": _reference_document(value.source_export_ref),
            "target_definition_ref": _reference_document(value.target_definition_ref),
            "target_name": value.target_name,
            "type": "asklegal.backup-request.local.v1",
        }
    )
    return f"sha256:{sha256(canonicalize(document)).hexdigest()}"


def _readback_document(value: _ReadbackSnapshot) -> dict[str, object]:
    return {
        "artifact_ref": _reference_document(value.artifact_ref),
        "backend_id": value.backend_id,
        "backup_profile_ref": _reference_document(value.backup_profile_ref),
        "desired_inventory_fingerprint": value.desired_inventory_fingerprint,
        "evidence_ref": _reference_document(value.evidence_ref),
        "receipt_ref": _reference_document(value.receipt_ref),
        "request_fingerprint": value.request_fingerprint,
        "role": value.role.value,
        "source_export_ref": _reference_document(value.source_export_ref),
        "target_definition_ref": _reference_document(value.target_definition_ref),
        "target_name": value.target_name,
    }


def _reference_document(value: _ReferenceSnapshot) -> dict[str, str]:
    return {
        "fingerprint": value.fingerprint,
        "ref_id": value.ref_id,
        "ref_type": value.ref_type.value,
    }


def _reference(
    value: object,
    allowed: frozenset[ReferenceType],
) -> _ReferenceSnapshot:
    if not isinstance(value, ImmutableReference) or type(value) is not ImmutableReference:
        _fail()
    if (
        type(value.ref_type) is not ReferenceType
        or type(value.ref_id) is not str
        or type(value.fingerprint) is not str
        or value.ref_type not in allowed
    ):
        _fail()
    rebuilt = ImmutableReference(value.ref_type, value.ref_id, value.fingerprint)
    return _ReferenceSnapshot(rebuilt.ref_type, rebuilt.ref_id, rebuilt.fingerprint)


def _reference_from_snapshot(value: _ReferenceSnapshot) -> ImmutableReference:
    return ImmutableReference(value.ref_type, value.ref_id, value.fingerprint)


def _reference_identity(value: _ReferenceSnapshot) -> tuple[str, str]:
    return (value.ref_type.value, value.ref_id)


def _role(value: object) -> BackupRole:
    if not isinstance(value, BackupRole) or type(value) is not BackupRole:
        _fail()
    return value


def _fingerprint(value: object) -> str:
    if (
        not isinstance(value, str)
        or type(value) is not str
        or _FINGERPRINT.fullmatch(value) is None
    ):
        _fail()
    return value


def _target_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or type(value) is not str
        or _TARGET_NAME.fullmatch(value) is None
    ):
        _fail()
    return value


def _backend_identity(value: object) -> str:
    if not isinstance(value, str) or type(value) is not str or _BACKEND_ID.fullmatch(value) is None:
        _fail()
    return value


def _port_backend_identity(value: NativeBackupPort | RecoveryCopyPort) -> str:
    backend_id: object | None = None
    with _AdapterFailureBoundary():
        backend_id = value.backend_id
    return _backend_identity(backend_id)


def _fail() -> Never:
    raise PromotionError(PromotionErrorCode.BACKUP_FAILED) from None
