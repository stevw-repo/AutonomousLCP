"""Filesystem-backed deterministic M4 vault fakes and package protocol."""

from __future__ import annotations

import fcntl
import json
import os
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from hashlib import sha256
from pathlib import Path

from asklegal_contracts import canonicalize, parse_json_bytes

from .model import (
    ArtifactClass,
    ArtifactDescriptor,
    CorruptEvidence,
    EvidenceIntegrityIncident,
    EvidenceManifest,
    EvidenceManifestEntry,
    EvidencePackageReceipt,
    EvidenceReadReceipt,
    ExactObjectReference,
    PackageIncomplete,
    RecoveryCopyReceipt,
    RetentionBlocked,
    RetentionProfile,
    VaultCollision,
    VaultName,
    VaultWriteReceipt,
    bytes_fingerprint,
    content_logical_key,
    manifest_logical_key,
    validate_logical_key,
)
from .ports import ImmutableVault


class LocalImmutableVault:
    """A contained local fake with exact versions and conditional create."""

    def __init__(self, root: Path, vault_name: VaultName) -> None:
        """Create or open one explicit local fake root."""
        if type(vault_name) is not VaultName:
            raise TypeError("vault_name must be an exact VaultName")
        if root.is_symlink():
            raise ValueError("local vault vault root is invalid")
        self.root = root.resolve()
        self.vault_name = vault_name
        self._objects = self.root / "objects"
        self._metadata = self.root / "metadata"
        self._ensure_real_directory(self.root, "vault root", parents=True)
        self._ensure_real_directory(self._objects, "objects root")
        self._ensure_real_directory(self._metadata, "metadata root")

    @staticmethod
    def _ensure_real_directory(path: Path, label: str, *, parents: bool = False) -> None:
        """Create one directory only when its existing identity is not an alias."""
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_dir():
                raise ValueError(f"local vault {label} is invalid")
            return
        with suppress(FileExistsError):
            path.mkdir(parents=parents)
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"local vault {label} is invalid")

    @contextmanager
    def _key_lock(self, logical_key: str) -> Generator[None]:
        """Hold one cross-instance/process advisory lock for a contained logical key."""
        self._contained(self._objects, logical_key, "lock-validation")
        locks = self.root / ".locks"
        self._ensure_real_directory(locks, "lock root")
        directory_fd = os.open(locks, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        lock_name = f"{sha256(logical_key.encode('utf-8')).hexdigest()}.lock"
        try:
            lock_fd = os.open(
                lock_name,
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                    raise ValueError("local vault key lock is invalid")
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        finally:
            os.close(directory_fd)

    def conditional_create(
        self,
        logical_key: str,
        content: bytes,
        retention: RetentionProfile,
    ) -> VaultWriteReceipt:
        """Create/adopt under one exact cross-process key lock."""
        logical_key = validate_logical_key(logical_key)
        with self._key_lock(logical_key):
            return self._conditional_create_locked(logical_key, content, retention)

    def _conditional_create_locked(
        self,
        logical_key: str,
        content: bytes,
        retention: RetentionProfile,
    ) -> VaultWriteReceipt:
        """Create once, or accept an exact existing object after read-back."""
        if type(content) is not bytes:
            raise TypeError("content must be exact bytes")
        if type(retention) is not RetentionProfile:
            raise TypeError("retention must be an exact RetentionProfile")
        fingerprint = bytes_fingerprint(content)
        version_id = f"v{fingerprint.removeprefix('sha256:')}"
        object_path = self._contained(self._objects, logical_key, version_id)
        metadata_path = self._contained(self._metadata, logical_key, f"{version_id}.json")
        existing_versions = self._regular_child_names(object_path.parent, logical_key)
        metadata_versions = tuple(
            name.removesuffix(".json")
            for name in self._regular_child_names(metadata_path.parent, logical_key)
        )
        if (
            existing_versions not in {(), (version_id,)}
            or metadata_versions not in {(), (version_id,)}
            or bool(existing_versions) != bool(metadata_versions)
        ):
            raise VaultCollision(logical_key)
        created = not object_path.exists()
        if created:
            object_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.write_bytes(content)
            metadata_path.write_text(
                json.dumps(
                    {
                        "byte_length": len(content),
                        "fingerprint": fingerprint,
                        "legal_hold": retention.legal_hold,
                        "profile_id": retention.profile_id,
                        "retain_until": retention.retain_until,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
        else:
            existing = object_path.read_bytes()
            if len(existing) != len(content) or bytes_fingerprint(existing) != fingerprint:
                raise VaultCollision(logical_key)
        reference = ExactObjectReference(
            self.vault_name,
            logical_key,
            version_id,
            fingerprint,
            len(content),
        )
        self._read_exact_unlocked(reference)
        if self._retention_unlocked(reference) != retention:
            raise VaultCollision(logical_key)
        return VaultWriteReceipt(
            reference=reference,
            created=created,
            read_back_verified=True,
            retention=retention,
        )

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        """Read only one exact version and verify length and SHA-256."""
        if type(reference) is not ExactObjectReference:
            raise TypeError("reference must be an exact ExactObjectReference")
        if reference.vault is not self.vault_name:
            raise ValueError("reference names a different vault")
        with self._key_lock(reference.logical_key):
            return self._read_exact_unlocked(reference)

    def _read_exact_unlocked(self, reference: ExactObjectReference) -> bytes:
        """Read verified content while the caller already holds the exact key lock."""
        path = self._contained(self._objects, reference.logical_key, reference.version_id)
        if not path.is_file():
            raise FileNotFoundError(reference.logical_key)
        content = path.read_bytes()
        if (
            len(content) != reference.byte_length
            or bytes_fingerprint(content) != reference.fingerprint
        ):
            raise CorruptEvidence(reference.logical_key)
        return content

    def read_for_use(
        self,
        reference: ExactObjectReference,
        *,
        required_use: str,
        artifact_class: ArtifactClass,
        accessed_at: str,
    ) -> tuple[bytes, EvidenceReadReceipt]:
        """Verify one exact version and return its explicit access receipt."""
        content = self.read_exact(reference)
        return content, EvidenceReadReceipt(reference, required_use, artifact_class, accessed_at)

    def exists_exact(self, reference: ExactObjectReference) -> bool:
        """Return true only when the exact version exists and verifies."""
        try:
            self.read_exact(reference)
        except FileNotFoundError, CorruptEvidence:
            return False
        return True

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        """Resolve only while the matching key transaction is not in progress."""
        logical_key = validate_logical_key(logical_key)
        with self._key_lock(logical_key):
            return self._resolve_current_unlocked(logical_key)

    def _resolve_current_unlocked(self, logical_key: str) -> ExactObjectReference | None:
        """Return the sole retained local version for one key without mutation."""
        candidate = self._contained(self._objects, logical_key, "placeholder").parent
        if not candidate.is_dir():
            return None
        versions = self._regular_child_names(candidate, logical_key)
        if len(versions) != 1:
            raise CorruptEvidence(logical_key)
        metadata_parent = self._contained(self._metadata, logical_key, "placeholder.json").parent
        metadata_versions = self._regular_child_names(metadata_parent, logical_key)
        if len(metadata_versions) != 1 or metadata_versions[0] != f"{versions[0]}.json":
            raise CorruptEvidence(logical_key)
        content = (candidate / versions[0]).read_bytes()
        reference = ExactObjectReference(
            self.vault_name,
            logical_key,
            versions[0],
            bytes_fingerprint(content),
            len(content),
        )
        self._read_exact_unlocked(reference)
        self._retention_unlocked(reference)
        return reference

    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        """Read the retained local policy facts for one exact version."""
        if type(reference) is not ExactObjectReference:
            raise TypeError("reference must be an exact ExactObjectReference")
        if reference.vault is not self.vault_name:
            raise ValueError("reference names a different vault")
        with self._key_lock(reference.logical_key):
            return self._retention_unlocked(reference)

    def _retention_unlocked(self, reference: ExactObjectReference) -> RetentionProfile:
        """Read exact retained policy only while the caller holds the matching key lock."""
        path = self._contained(
            self._metadata,
            reference.logical_key,
            f"{reference.version_id}.json",
        )
        try:
            raw = path.read_bytes()
            value = parse_json_bytes(raw, max_bytes=max(len(raw), 1))
        except (OSError, TypeError, ValueError) as error:
            raise CorruptEvidence(reference.logical_key) from error
        if not isinstance(value, dict):
            raise CorruptEvidence(reference.logical_key)
        if frozenset(value) != frozenset(
            {"byte_length", "fingerprint", "legal_hold", "profile_id", "retain_until"}
        ):
            raise CorruptEvidence(reference.logical_key)
        byte_length = value.get("byte_length")
        fingerprint = value.get("fingerprint")
        profile_id = value.get("profile_id")
        retain_until = value.get("retain_until")
        legal_hold = value.get("legal_hold")
        if (
            type(byte_length) is not int
            or type(fingerprint) is not str
            or not isinstance(profile_id, str)
            or not isinstance(retain_until, str)
            or type(legal_hold) is not bool
            or byte_length != reference.byte_length
            or fingerprint != reference.fingerprint
        ):
            raise CorruptEvidence(reference.logical_key)
        retained = RetentionProfile(profile_id, retain_until, legal_hold)
        if canonicalize(value) != raw:
            raise CorruptEvidence(reference.logical_key)
        return retained

    def destroy_exact(
        self,
        reference: ExactObjectReference,
        *,
        authorized: bool,
        now: str,
    ) -> None:
        """Test exact-ID destruction; broad or held removal is impossible."""
        if type(authorized) is not bool:
            raise TypeError("authorized must be an exact boolean")
        if type(reference) is not ExactObjectReference:
            raise TypeError("reference must be an exact ExactObjectReference")
        if reference.vault is not self.vault_name:
            raise ValueError("reference names a different vault")
        if type(now) is not str:
            raise TypeError("now must be an exact string")
        with self._key_lock(reference.logical_key):
            retention = self._retention_unlocked(reference)
            if not authorized or retention.legal_hold or now < retention.retain_until:
                raise RetentionBlocked(reference.logical_key)
            self._read_exact_unlocked(reference)
            object_path = self._contained(
                self._objects, reference.logical_key, reference.version_id
            )
            metadata_path = self._contained(
                self._metadata,
                reference.logical_key,
                f"{reference.version_id}.json",
            )
            object_path.unlink()
            metadata_path.unlink()

    def inject_corruption(self, reference: ExactObjectReference, content: bytes) -> None:
        """Test-only fault injection for exact corruption branches."""
        if type(content) is not bytes:
            raise TypeError("content must be exact bytes")
        path = self._contained(self._objects, reference.logical_key, reference.version_id)
        path.write_bytes(content)

    def _regular_child_names(self, directory: Path, logical_key: str) -> tuple[str, ...]:
        """List one real directory's leaves, rejecting partial or alias state."""
        if not directory.exists():
            return ()
        if directory.is_symlink() or not directory.is_dir():
            raise CorruptEvidence(logical_key)
        children = tuple(directory.iterdir())
        if any(child.is_symlink() or not child.is_file() for child in children):
            raise CorruptEvidence(logical_key)
        return tuple(child.name for child in children)

    def _contained(self, root: Path, logical_key: str, filename: str) -> Path:
        """Build a lexical contained path while refusing every existing symlink component."""
        validated_key = validate_logical_key(logical_key)
        if logical_key != validated_key:
            raise ValueError("logical key is not canonical")
        candidate = root
        for component in (*Path(validated_key).parts, filename):
            candidate = candidate / component
            if candidate.is_symlink():
                raise ValueError("local vault path contains a symlink")
        if not candidate.is_relative_to(root):
            raise ValueError("logical key escaped the vault root")
        return candidate


class RecoveryCopier:
    """Copy and verify exact primary versions into an isolated recovery fake."""

    def __init__(self, primary: ImmutableVault, recovery: ImmutableVault) -> None:
        """Bind one primary and recovery pair without granting app authority."""
        if primary.vault_name is not VaultName.PRIMARY:
            raise ValueError("primary adapter must have PRIMARY role")
        if recovery.vault_name is not VaultName.RECOVERY:
            raise ValueError("recovery adapter must have RECOVERY role")
        self.primary = primary
        self.recovery = recovery

    def copy_exact(
        self,
        reference: ExactObjectReference,
        retention: RetentionProfile,
    ) -> RecoveryCopyReceipt:
        """Copy one exact verified version and verify recovery read-back."""
        content = self.primary.read_exact(reference)
        receipt = self.recovery.conditional_create(reference.logical_key, content, retention)
        copied = self.recovery.read_exact(receipt.reference)
        if copied != content:
            raise CorruptEvidence(reference.logical_key)
        return RecoveryCopyReceipt(reference, receipt.reference)


class TwoVaultEvidenceReader:
    """Exact reader that inspects recovery after corruption but never falls back."""

    def __init__(self, primary: ImmutableVault, recovery: ImmutableVault) -> None:
        """Bind a primary/recovery pair for explicit integrity comparison."""
        if primary.vault_name is not VaultName.PRIMARY:
            raise ValueError("primary adapter must have PRIMARY role")
        if recovery.vault_name is not VaultName.RECOVERY:
            raise ValueError("recovery adapter must have RECOVERY role")
        self.primary = primary
        self.recovery = recovery

    def read(
        self,
        copy: RecoveryCopyReceipt,
        *,
        required_use: str,
        artifact_class: ArtifactClass,
        accessed_at: str,
    ) -> tuple[bytes, EvidenceReadReceipt]:
        """Read primary exactly; compare recovery on mismatch and always block use."""
        if type(copy) is not RecoveryCopyReceipt:
            raise TypeError("copy must be an exact RecoveryCopyReceipt")
        try:
            return self.primary.read_for_use(
                copy.primary,
                required_use=required_use,
                artifact_class=artifact_class,
                accessed_at=accessed_at,
            )
        except CorruptEvidence as primary_error:
            try:
                self.recovery.read_exact(copy.recovery)
            except (CorruptEvidence, FileNotFoundError) as recovery_error:
                raise EvidenceIntegrityIncident(
                    "primary and recovery exact versions disagree or are corrupt"
                ) from recovery_error
            raise EvidenceIntegrityIncident(
                "primary exact version is corrupt; verified recovery was not substituted"
            ) from primary_error


class ManifestLastPackageWriter:
    """Restartable content-first, manifest-last package assembler."""

    def __init__(self, primary: ImmutableVault) -> None:
        """Bind package writes to the primary vault only."""
        if primary.vault_name is not VaultName.PRIMARY:
            raise ValueError("package writer requires the primary vault")
        self.primary = primary
        self._entries: dict[str, EvidenceManifestEntry] = {}
        self._manifest: EvidenceManifest | None = None
        self._primary_manifest: ExactObjectReference | None = None

    def stage_content(
        self,
        descriptor: ArtifactDescriptor,
        content: bytes,
    ) -> EvidenceManifestEntry:
        """Conditionally create and verify one content-addressed raw object."""
        if type(descriptor) is not ArtifactDescriptor:
            raise TypeError("descriptor must be an exact ArtifactDescriptor")
        fingerprint = bytes_fingerprint(content)
        receipt = self.primary.conditional_create(
            content_logical_key(fingerprint),
            content,
            descriptor.retention,
        )
        existing = self._entries.get(descriptor.artifact_id)
        entry = EvidenceManifestEntry(descriptor, receipt.reference)
        if existing is not None and existing != entry:
            raise VaultCollision(descriptor.artifact_id)
        self._entries[descriptor.artifact_id] = entry
        return entry

    def commit_manifest(
        self,
        *,
        package_kind: str,
        package_id: str,
        observation_id: str,
        retention: RetentionProfile,
    ) -> tuple[EvidenceManifest, ExactObjectReference]:
        """Make a package visible only by writing its complete manifest last."""
        manifest = EvidenceManifest(
            package_kind,
            package_id,
            observation_id,
            tuple(self._entries.values()),
        )
        manifest_bytes = canonicalize(manifest.document())
        fingerprint = bytes_fingerprint(manifest_bytes)
        receipt = self.primary.conditional_create(
            manifest_logical_key(manifest, fingerprint),
            manifest_bytes,
            retention,
        )
        if self._manifest is not None and self._manifest != manifest:
            raise VaultCollision(package_id)
        self._manifest = manifest
        self._primary_manifest = receipt.reference
        return manifest, receipt.reference

    def finalize_recovery(
        self,
        copier: RecoveryCopier,
        retention: RetentionProfile,
    ) -> EvidencePackageReceipt:
        """Verify every content copy and copy the exact manifest last to recovery."""
        if self._manifest is None or self._primary_manifest is None:
            raise PackageIncomplete("primary manifest has not been committed")
        copies = tuple(
            copier.copy_exact(entry.primary, retention) for entry in self._manifest.entries
        )
        manifest_copy = copier.copy_exact(self._primary_manifest, retention)
        return EvidencePackageReceipt(
            self._manifest,
            self._primary_manifest,
            manifest_copy.recovery,
            copies,
        )

    @property
    def committed(self) -> bool:
        """Expose only manifest-last primary visibility."""
        return self._manifest is not None and self._primary_manifest is not None

    def restart(self) -> ManifestLastPackageWriter:
        """Return an equivalent writer with no volatile staging assumptions."""
        restarted = ManifestLastPackageWriter(self.primary)
        restarted._entries = dict(self._entries)
        restarted._manifest = self._manifest
        restarted._primary_manifest = self._primary_manifest
        return restarted
