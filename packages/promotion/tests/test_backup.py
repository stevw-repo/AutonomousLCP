"""Provider-neutral independent native-backup and recovery-copy proofs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_promotion.backup import (
    BackupAcknowledgement,
    BackupReadback,
    BackupRequest,
    BackupRole,
    IndependentBackupAdapter,
    NativeBackupPort,
    RecoveryCopyPort,
    VerifiedBackupPair,
    create_and_verify_backup,
    freeze_backup_request,
)
from asklegal_promotion.model import OutcomeUnknown, PromotionError, PromotionErrorCode


def _reference(ref_type: ReferenceType, prefix: str, digit: str) -> ImmutableReference:
    return ImmutableReference(
        ref_type,
        f"{prefix}_{digit * 48}",
        f"sha256:{digit * 64}",
    )


def _request(*, inventory_digit: str = "2") -> BackupRequest:
    return freeze_backup_request(
        target_name="hk-v1-20260827-a1b2c3d4e5f6",
        target_definition_ref=_reference(ReferenceType.PINECONE_INDEX_GENERATION, "pgi", "1"),
        desired_inventory_fingerprint=f"sha256:{inventory_digit * 64}",
        backup_profile_ref=_reference(ReferenceType.CAPABILITY_PROFILE, "cap", "3"),
        source_export_ref=_reference(ReferenceType.ARTIFACT, "art", "4"),
    )


def _acknowledgement(
    role: BackupRole,
    backend_id: str,
    request_fingerprint: str,
    digit: str,
) -> BackupAcknowledgement:
    return BackupAcknowledgement(
        role=role,
        backend_id=backend_id,
        request_fingerprint=request_fingerprint,
        receipt_ref=_reference(ReferenceType.EFFECT_RECEIPT, "efr", digit),
        evidence_ref=_reference(ReferenceType.EVIDENCE, "evi", digit),
    )


def _readback(
    role: BackupRole,
    backend_id: str,
    request: BackupRequest,
    digit: str,
) -> BackupReadback:
    return BackupReadback(
        role=role,
        backend_id=backend_id,
        request_fingerprint=request.request_fingerprint,
        target_name=request.target_name,
        target_definition_ref=request.target_definition_ref,
        desired_inventory_fingerprint=request.desired_inventory_fingerprint,
        backup_profile_ref=request.backup_profile_ref,
        source_export_ref=request.source_export_ref,
        artifact_ref=_reference(ReferenceType.ARTIFACT, "art", digit),
        receipt_ref=_reference(ReferenceType.EFFECT_RECEIPT, "efr", digit),
        evidence_ref=_reference(ReferenceType.EVIDENCE, "evi", digit),
    )


class NativeBackend(NativeBackupPort):
    """Scripted native-backup boundary with no provider or network."""

    def __init__(
        self,
        request: BackupRequest,
        *,
        backend_id: str = "native-backup-a",
        readback: BackupReadback | None = None,
    ) -> None:
        """Configure one exact scripted native response."""
        self._backend_id = backend_id
        initial = readback or _readback(
            BackupRole.NATIVE,
            backend_id,
            request,
            "5",
        )
        self.readback: BackupReadback | None = initial
        self.acknowledgement = BackupAcknowledgement(
            role=initial.role,
            backend_id=initial.backend_id,
            request_fingerprint=initial.request_fingerprint,
            receipt_ref=initial.receipt_ref,
            evidence_ref=initial.evidence_ref,
        )
        self.write_error: BaseException | None = None
        self.read_error: BaseException | None = None
        self.mutate_request = False

    @property
    def backend_id(self) -> str:
        """Return the scripted native backend identity."""
        return self._backend_id

    def write_native(self, request: BackupRequest) -> BackupAcknowledgement:
        """Return one scripted native acknowledgement."""
        if self.mutate_request:
            object.__setattr__(
                request,
                "desired_inventory_fingerprint",
                "sha256:" + "0" * 64,
            )
        if self.write_error is not None:
            raise self.write_error
        return self.acknowledgement

    def read_native(self, request: BackupRequest) -> BackupReadback | None:
        """Return one scripted native read-back."""
        if type(request) is not BackupRequest:
            raise TypeError
        if self.read_error is not None:
            raise self.read_error
        return self.readback


class RecoveryBackend(RecoveryCopyPort):
    """Scripted independent recovery-copy boundary with no vault service."""

    def __init__(
        self,
        request: BackupRequest,
        *,
        backend_id: str = "recovery-copy-b",
        readback: BackupReadback | None = None,
    ) -> None:
        """Configure one exact scripted recovery response."""
        self._backend_id = backend_id
        initial = readback or _readback(
            BackupRole.RECOVERY,
            backend_id,
            request,
            "6",
        )
        self.readback: BackupReadback | None = initial
        self.acknowledgement = BackupAcknowledgement(
            role=initial.role,
            backend_id=initial.backend_id,
            request_fingerprint=initial.request_fingerprint,
            receipt_ref=initial.receipt_ref,
            evidence_ref=initial.evidence_ref,
        )
        self.write_error: BaseException | None = None
        self.read_error: BaseException | None = None
        self.on_write: Callable[[], None] | None = None

    @property
    def backend_id(self) -> str:
        """Return the scripted recovery backend identity."""
        return self._backend_id

    def write_recovery(self, request: BackupRequest) -> BackupAcknowledgement:
        """Return one scripted recovery acknowledgement."""
        if type(request) is not BackupRequest:
            raise TypeError
        if self.on_write is not None:
            self.on_write()
        if self.write_error is not None:
            raise self.write_error
        return self.acknowledgement

    def read_recovery(self, request: BackupRequest) -> BackupReadback | None:
        """Return one scripted recovery read-back."""
        if type(request) is not BackupRequest:
            raise TypeError
        if self.read_error is not None:
            raise self.read_error
        return self.readback


class DualRoleBackend(NativeBackend, RecoveryBackend):
    """One object deliberately implementing both nominal role methods."""

    def write_recovery(self, request: BackupRequest) -> BackupAcknowledgement:
        """Delegate the forbidden second role to the same object."""
        return self.write_native(request)

    def read_recovery(self, request: BackupRequest) -> BackupReadback | None:
        """Delegate the forbidden second read role to the same object."""
        return self.read_native(request)


def _assert_backup_failed(action: Callable[[], object]) -> PromotionError:
    with pytest.raises(PromotionError) as raised:
        action()
    assert raised.value.code is PromotionErrorCode.BACKUP_FAILED
    assert str(raised.value) == "BACKUP_FAILED"
    assert raised.value.__cause__ is None
    return raised.value


def test_both_separate_exact_readbacks_issue_one_deterministic_pair() -> None:
    request = _request()
    native = NativeBackend(request)
    recovery = RecoveryBackend(request)

    first = create_and_verify_backup(request, native, recovery)
    replay = create_and_verify_backup(request, native, recovery)

    assert first == replay
    assert first.request_fingerprint == request.request_fingerprint
    assert first.native_backend_id == "native-backup-a"
    assert first.recovery_backend_id == "recovery-copy-b"
    assert first.native_receipt_ref.ref_id == "efr_" + "5" * 48
    assert first.recovery_receipt_ref.ref_id == "efr_" + "6" * 48
    assert first.native_evidence_ref.ref_id == "evi_" + "5" * 48
    assert first.recovery_evidence_ref.ref_id == "evi_" + "6" * 48
    assert first.fingerprint.startswith("sha256:")


def test_profile_bound_adapter_rejects_runtime_drift_and_uses_dual_readback() -> None:
    """Promotion cannot substitute a backup profile or trust two caller booleans."""
    request = _request()
    native = NativeBackend(request)
    recovery = RecoveryBackend(request)
    adapter = IndependentBackupAdapter(request, native, recovery)

    result = adapter.create_and_verify(
        request.target_name,
        request.desired_inventory_fingerprint,
        request.backup_profile_ref,
    )

    assert result.native_backup_receipt_ref == "efr_" + "5" * 48
    assert result.recovery_receipt_ref == "efr_" + "6" * 48
    with pytest.raises(PromotionError):
        adapter.create_and_verify(
            request.target_name,
            request.desired_inventory_fingerprint,
            _reference(ReferenceType.CAPABILITY_PROFILE, "cap", "9"),
        )


def test_verified_pair_cannot_be_constructed_without_both_readbacks() -> None:
    with pytest.raises(TypeError):
        VerifiedBackupPair()


def test_one_object_or_backend_identity_cannot_satisfy_both_roles() -> None:
    request = _request()
    dual = DualRoleBackend(request)
    _assert_backup_failed(lambda: create_and_verify_backup(request, dual, dual))

    _assert_backup_failed(
        lambda: create_and_verify_backup(
            request,
            NativeBackend(request, backend_id="shared-backend"),
            RecoveryBackend(request, backend_id="shared-backend"),
        )
    )


def test_structural_impostors_cannot_claim_the_nominal_native_role() -> None:
    request = _request()
    native = NativeBackend(request)

    class StructuralImpostor:
        backend_id = native.backend_id

        def write_native(self, request: BackupRequest) -> BackupAcknowledgement:
            return native.write_native(request)

        def read_native(self, request: BackupRequest) -> BackupReadback | None:
            return native.read_native(request)

    _assert_backup_failed(
        lambda: create_and_verify_backup(
            request,
            StructuralImpostor(),
            RecoveryBackend(request),
        )
    )


def test_receipt_evidence_or_artifact_identity_cannot_satisfy_both_roles() -> None:
    request = _request()
    native = NativeBackend(request)
    native_fact = native.readback
    assert native_fact is not None
    for field in ("receipt_ref", "evidence_ref", "artifact_ref"):
        recovery_fact = replace(
            _readback(BackupRole.RECOVERY, "recovery-copy-b", request, "6"),
            **{field: getattr(native_fact, field)},
        )
        _assert_backup_failed(
            lambda recovery_fact=recovery_fact: create_and_verify_backup(
                request,
                native,
                RecoveryBackend(request, readback=recovery_fact),
            )
        )


def test_same_cross_role_identity_is_rejected_even_when_its_fingerprint_drifts() -> None:
    request = _request()
    native = NativeBackend(request)
    native_fact = native.readback
    assert native_fact is not None
    for field in ("receipt_ref", "evidence_ref", "artifact_ref"):
        native_reference = getattr(native_fact, field)
        recovery_fact = replace(
            _readback(BackupRole.RECOVERY, "recovery-copy-b", request, "6"),
            **{
                field: ImmutableReference(
                    native_reference.ref_type,
                    native_reference.ref_id,
                    "sha256:" + "a" * 64,
                )
            },
        )
        _assert_backup_failed(
            lambda recovery_fact=recovery_fact: create_and_verify_backup(
                request,
                native,
                RecoveryBackend(request, readback=recovery_fact),
            )
        )


@pytest.mark.parametrize("role", [BackupRole.NATIVE, BackupRole.RECOVERY])
def test_unreadable_or_missing_readback_never_uses_the_acknowledgement_as_success(
    role: BackupRole,
) -> None:
    request = _request()
    native = NativeBackend(request)
    recovery = RecoveryBackend(request)
    if role is BackupRole.NATIVE:
        native.read_error = RuntimeError("raw storage coordinate")
    else:
        recovery.read_error = RuntimeError("raw storage coordinate")
    _assert_backup_failed(lambda: create_and_verify_backup(request, native, recovery))

    if role is BackupRole.NATIVE:
        native.read_error = None
        native.readback = None
    else:
        recovery.read_error = None
        recovery.readback = None
    _assert_backup_failed(lambda: create_and_verify_backup(request, native, recovery))


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("target_name", "hk-v1-20260827-drifted"),
        (
            "target_definition_ref",
            _reference(ReferenceType.PINECONE_INDEX_GENERATION, "pgi", "7"),
        ),
        ("desired_inventory_fingerprint", "sha256:" + "7" * 64),
        (
            "backup_profile_ref",
            _reference(ReferenceType.CAPABILITY_PROFILE, "cap", "7"),
        ),
        ("source_export_ref", _reference(ReferenceType.ARTIFACT, "art", "7")),
        ("role", BackupRole.RECOVERY),
    ],
)
def test_native_readback_must_match_every_request_fact_and_role(
    field: str,
    replacement: object,
) -> None:
    request = _request()
    native_fact = replace(
        _readback(BackupRole.NATIVE, "native-backup-a", request, "5"),
        **{field: replacement},
    )
    _assert_backup_failed(
        lambda: create_and_verify_backup(
            request,
            NativeBackend(request, readback=native_fact),
            RecoveryBackend(request),
        )
    )


def test_lost_acknowledgement_reconciles_only_from_complete_exact_readback() -> None:
    request = _request()
    native = NativeBackend(request)
    native.write_error = OutcomeUnknown("ack lost")
    verified = create_and_verify_backup(request, native, RecoveryBackend(request))
    assert verified.native_receipt_ref.ref_id == "efr_" + "5" * 48

    native.readback = None
    _assert_backup_failed(
        lambda: create_and_verify_backup(request, native, RecoveryBackend(request))
    )


def test_write_acknowledgement_must_match_the_subsequent_readback() -> None:
    request = _request()

    class DriftedAcknowledgementNative(NativeBackend):
        def write_native(self, request: BackupRequest) -> BackupAcknowledgement:
            """Return an acknowledgement that disagrees with read-back."""
            return _acknowledgement(
                BackupRole.NATIVE,
                self.backend_id,
                request.request_fingerprint,
                "7",
            )

    _assert_backup_failed(
        lambda: create_and_verify_backup(
            request,
            DriftedAcknowledgementNative(request),
            RecoveryBackend(request),
        )
    )


def test_exact_replay_cannot_be_borrowed_by_a_drifted_request() -> None:
    first_request = _request(inventory_digit="2")
    native = NativeBackend(first_request)
    recovery = RecoveryBackend(first_request)
    first = create_and_verify_backup(first_request, native, recovery)
    assert first.request_fingerprint == first_request.request_fingerprint

    drifted_request = _request(inventory_digit="8")
    _assert_backup_failed(lambda: create_and_verify_backup(drifted_request, native, recovery))


@pytest.mark.parametrize(
    "method",
    ["native-write", "native-read", "recovery-write", "recovery-read"],
)
def test_ordinary_backend_errors_are_sanitized(method: str) -> None:
    request = _request()
    native = NativeBackend(request)
    recovery = RecoveryBackend(request)
    selected = native if method.startswith("native") else recovery
    if method.endswith("write"):
        selected.write_error = RuntimeError("secret endpoint and object key")
    else:
        selected.read_error = RuntimeError("secret endpoint and object key")

    _assert_backup_failed(lambda: create_and_verify_backup(request, native, recovery))


def test_direct_exception_subclass_from_backend_is_sanitized() -> None:
    class DirectAdapterFailure(Exception):
        """Ordinary adapter failure that is not a built-in operational subclass."""

    request = _request()
    native = NativeBackend(request)
    native.read_error = DirectAdapterFailure("secret endpoint and object key")

    _assert_backup_failed(
        lambda: create_and_verify_backup(request, native, RecoveryBackend(request))
    )


def test_backend_identity_callback_error_is_sanitized() -> None:
    request = _request()

    class ExplodingIdentityNative(NativeBackupPort):
        @property
        def backend_id(self) -> str:
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "secret coordinate")

        def write_native(self, request: BackupRequest) -> BackupAcknowledgement:
            del request
            raise AssertionError

        def read_native(self, request: BackupRequest) -> BackupReadback | None:
            del request
            raise AssertionError

    _assert_backup_failed(
        lambda: create_and_verify_backup(
            request,
            ExplodingIdentityNative(),
            RecoveryBackend(request),
        )
    )


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(7)])
def test_base_exceptions_from_backends_remain_visible(failure: BaseException) -> None:
    request = _request()
    native = NativeBackend(request)
    native.read_error = failure
    with pytest.raises(type(failure)):
        create_and_verify_backup(request, native, RecoveryBackend(request))


def test_response_is_detached_before_a_later_callback_mutates_it() -> None:
    request = _request()
    native = NativeBackend(request)
    original = native.readback
    assert original is not None
    recovery = RecoveryBackend(request)

    def mutate_native_response() -> None:
        object.__setattr__(
            original,
            "evidence_ref",
            _reference(ReferenceType.EVIDENCE, "evi", "9"),
        )

    recovery.on_write = mutate_native_response
    result = create_and_verify_backup(request, native, recovery)

    assert result.native_evidence_ref.ref_id == "evi_" + "5" * 48
    assert original.evidence_ref.ref_id == "evi_" + "9" * 48


def test_backend_request_mutation_cannot_change_expected_facts() -> None:
    request = _request()
    native = NativeBackend(request)
    native.mutate_request = True

    result = create_and_verify_backup(request, native, RecoveryBackend(request))

    assert result.request_fingerprint == request.request_fingerprint
    assert request.desired_inventory_fingerprint == "sha256:" + "2" * 64


def test_callback_owned_scalar_cannot_run_equality_hooks() -> None:
    request = _request()

    class HostileText(str):
        __slots__ = ()
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            message = "equality hook ran"
            raise RuntimeError(message)

    native_fact = replace(
        _readback(BackupRole.NATIVE, "native-backup-a", request, "5"),
        target_name=HostileText(request.target_name),
    )
    _assert_backup_failed(
        lambda: create_and_verify_backup(
            request,
            NativeBackend(request, readback=native_fact),
            RecoveryBackend(request),
        )
    )
