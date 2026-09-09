"""Distinct restart-safe native and recovery filesystem backup writers."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from asklegal_application_runtime import exclusive_local_state_lock
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_promotion import PromotionError, PromotionErrorCode
from asklegal_promotion.backup import (
    BackupAcknowledgement,
    BackupReadback,
    BackupRequest,
    BackupRole,
    NativeBackupPort,
    RecoveryCopyPort,
)

_SHA256_HEX_LENGTH = 64


def _reference(value: ImmutableReference) -> dict[str, str]:
    return {
        "fingerprint": value.fingerprint,
        "ref_id": value.ref_id,
        "ref_type": value.ref_type.value,
    }


def _request_document(request: BackupRequest, role: BackupRole, backend: str) -> bytes:
    return canonicalize(
        checked_json_value(
            {
                "backend_id": backend,
                "backup_profile_ref": _reference(request.backup_profile_ref),
                "desired_inventory_fingerprint": request.desired_inventory_fingerprint,
                "request_fingerprint": request.request_fingerprint,
                "role": role.value,
                "schema_id": "asklegal.local-backup-artifact/v1",
                "source_export_ref": _reference(request.source_export_ref),
                "target_definition_ref": _reference(request.target_definition_ref),
                "target_name": request.target_name,
            }
        )
    )


class _FileBackupWriter:
    role: BackupRole

    def __init__(self, root: Path, backend_id: str) -> None:
        if root.is_symlink() or not root.is_dir() or not backend_id:
            raise PromotionError(PromotionErrorCode.BACKUP_FAILED)
        self._root = root
        self._backend_id = backend_id

    @property
    def backend_id(self) -> str:
        return self._backend_id

    def _write(self, request: BackupRequest) -> BackupAcknowledgement:
        content = _request_document(request, self.role, self.backend_id)
        path = self._path(request)
        with exclusive_local_state_lock(path):
            if path.exists():
                if path.is_symlink() or path.read_bytes() != content:
                    raise PromotionError(PromotionErrorCode.BACKUP_FAILED)
            else:
                temporary = path.with_suffix(".tmp")
                temporary.write_bytes(content)
                temporary.replace(path)
        readback = self._read(request)
        if readback is None:
            raise PromotionError(PromotionErrorCode.BACKUP_FAILED)
        return BackupAcknowledgement(
            self.role,
            self.backend_id,
            request.request_fingerprint,
            readback.receipt_ref,
            readback.evidence_ref,
        )

    def _read(self, request: BackupRequest) -> BackupReadback | None:
        path = self._path(request)
        if path.is_symlink() or not path.is_file():
            return None
        content = path.read_bytes()
        try:
            value = parse_json_bytes(content, max_bytes=1_000_000)
        except (RuntimeError, ValueError) as error:
            raise PromotionError(PromotionErrorCode.BACKUP_FAILED) from error
        if (
            not isinstance(value, dict)
            or canonicalize(value) != content
            or content != _request_document(request, self.role, self.backend_id)
        ):
            raise PromotionError(PromotionErrorCode.BACKUP_FAILED)
        digest = f"sha256:{sha256(content).hexdigest()}"
        suffix = sha256((self.role.value + request.request_fingerprint).encode()).hexdigest()[:48]
        artifact = ImmutableReference(ReferenceType.ARTIFACT, f"art_{suffix}", digest)
        receipt = ImmutableReference(ReferenceType.EFFECT_RECEIPT, f"efr_{suffix}", digest)
        evidence = ImmutableReference(ReferenceType.EVIDENCE, f"evi_{suffix}", digest)
        return BackupReadback(
            self.role,
            self.backend_id,
            request.request_fingerprint,
            request.target_name,
            request.target_definition_ref,
            request.desired_inventory_fingerprint,
            request.backup_profile_ref,
            request.source_export_ref,
            artifact,
            receipt,
            evidence,
        )

    def _path(self, request: BackupRequest) -> Path:
        digest = request.request_fingerprint.removeprefix("sha256:")
        if len(digest) != _SHA256_HEX_LENGTH or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise PromotionError(PromotionErrorCode.BACKUP_FAILED)
        return self._root / f"{digest}.json"


class FileNativeBackupWriter(_FileBackupWriter, NativeBackupPort):
    """Nominal provider-native local backup path."""

    role = BackupRole.NATIVE

    def write_native(self, request: BackupRequest) -> BackupAcknowledgement:
        """Atomically write or exactly replay one native backup."""
        return self._write(request)

    def read_native(self, request: BackupRequest) -> BackupReadback | None:
        """Reread one exact native artifact."""
        return self._read(request)


class FileRecoveryBackupWriter(_FileBackupWriter, RecoveryCopyPort):
    """Nominal separately administered recovery-copy local backup path."""

    role = BackupRole.RECOVERY

    def write_recovery(self, request: BackupRequest) -> BackupAcknowledgement:
        """Atomically write or exactly replay one recovery copy."""
        return self._write(request)

    def read_recovery(self, request: BackupRequest) -> BackupReadback | None:
        """Reread one exact recovery artifact."""
        return self._read(request)
