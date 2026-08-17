"""Strict immutable M4 evidence and vault value objects."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Never

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")
_LOCAL_VERSION = re.compile(r"^v[0-9a-f]{64}$")
_S3_VERSION = re.compile(r"^s3v_([A-Za-z0-9_-]{1,684})$")
_SAFE_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_MAX_PROVIDER_VERSION_BYTES = 512
_FIRST_CONTROL_CODEPOINT = 0x20


class EvidenceError(RuntimeError):
    """Base class for closed evidence failures."""


class VaultCollision(EvidenceError):
    """A single-assignment key already contains different bytes."""


class CorruptEvidence(EvidenceError):
    """An exact version does not match its immutable reference."""


class EvidenceIntegrityIncident(CorruptEvidence):
    """Primary corruption or primary/recovery disagreement blocks use."""


class PackageIncomplete(EvidenceError):
    """A package is staged or is missing a required verified receipt."""


class RetentionBlocked(EvidenceError):
    """An exact version cannot be removed under its retention state."""


def _fail(message: str) -> Never:
    raise ValueError(message)


def _text(value: object, field: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact string")
    if not value or value.strip() != value:
        _fail(f"{field} must be non-empty and whitespace-exact")
    return value


def _fingerprint(value: object, field: str) -> str:
    text = _text(value, field)
    if _FINGERPRINT.fullmatch(text) is None:
        _fail(f"{field} must be sha256:<64 lowercase hexadecimal characters>")
    return text


def _identifier(value: object, field: str) -> str:
    text = _text(value, field)
    if _IDENTIFIER.fullmatch(text) is None:
        _fail(f"{field} must be a register-issued opaque identifier")
    return text


def _version(value: object) -> str:
    text = _text(value, "version_id")
    if _LOCAL_VERSION.fullmatch(text) is not None:
        return text
    match = _S3_VERSION.fullmatch(text)
    if match is None:
        _fail("version_id must be one exact adapter-owned immutable version")
    payload = match.group(1)
    try:
        decoded = base64.urlsafe_b64decode(payload + ("=" * (-len(payload) % 4)))
        provider_version = decoded.decode("utf-8", errors="strict")
    except UnicodeDecodeError, ValueError:
        _fail("version_id must contain one canonical UTF-8 S3 version")
    if (
        not provider_version
        or len(decoded) > _MAX_PROVIDER_VERSION_BYTES
        or any(ord(character) < _FIRST_CONTROL_CODEPOINT for character in provider_version)
        or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != payload
    ):
        _fail("version_id must contain one canonical UTF-8 S3 version")
    return text


def s3_version_reference(provider_version_id: str) -> str:
    """Encode one provider-issued S3 version ID as a canonical safe reference."""
    provider = _text(provider_version_id, "provider_version_id")
    raw = provider.encode("utf-8")
    if len(raw) > _MAX_PROVIDER_VERSION_BYTES or any(
        ord(character) < _FIRST_CONTROL_CODEPOINT for character in provider
    ):
        _fail("provider_version_id is outside the exact safe boundary")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    reference = f"s3v_{encoded}"
    _version(reference)
    return reference


def s3_provider_version_id(version_reference: str) -> str:
    """Decode only one canonical S3 version reference for an exact provider read."""
    reference = _version(version_reference)
    match = _S3_VERSION.fullmatch(reference)
    if match is None:
        _fail("version_id is not an S3 provider version reference")
    payload = match.group(1)
    return base64.urlsafe_b64decode(payload + ("=" * (-len(payload) % 4))).decode("utf-8")


class VaultName(StrEnum):
    """Closed logical vault roles."""

    PRIMARY = "PRIMARY"
    RECOVERY = "RECOVERY"


class ArtifactClass(StrEnum):
    """M4 evidence isolation classes."""

    ACQUISITION_ATTEMPT = "ACQUISITION_ATTEMPT"
    SOURCE_CONTENT = "SOURCE_CONTENT"
    SOURCE_METADATA = "SOURCE_METADATA"
    HOSTILE_ISOLATED = "HOSTILE_ISOLATED"
    PACKAGE_MANIFEST = "PACKAGE_MANIFEST"


class HostileReason(StrEnum):
    """Closed deterministic admission failures for acquired bytes."""

    ACTIVE_CONTENT = "ACTIVE_CONTENT"
    ARCHIVE_RECURSION = "ARCHIVE_RECURSION"
    DECOMPRESSION_RATIO = "DECOMPRESSION_RATIO"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    ENCODING_DECLARATION = "ENCODING_DECLARATION"
    LENGTH_MISMATCH = "LENGTH_MISMATCH"
    MALWARE_SIGNATURE = "MALWARE_SIGNATURE"
    MEDIA_TYPE = "MEDIA_TYPE"
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    SIZE_LIMIT = "SIZE_LIMIT"
    TRUNCATED = "TRUNCATED"


@dataclass(frozen=True, slots=True)
class RetentionProfile:
    """Exact local retention facts without claiming Azure WORM."""

    profile_id: str
    retain_until: str
    legal_hold: bool = False

    def __post_init__(self) -> None:
        _text(self.profile_id, "profile_id")
        _text(self.retain_until, "retain_until")
        if type(self.legal_hold) is not bool:
            raise TypeError("legal_hold must be an exact boolean")


@dataclass(frozen=True, slots=True)
class HostileClassification:
    """Admission result that keeps hostile bytes inert."""

    admitted: bool
    reasons: tuple[HostileReason, ...]

    def __post_init__(self) -> None:
        if type(self.admitted) is not bool:
            raise TypeError("admitted must be an exact boolean")
        if type(self.reasons) is not tuple or any(
            type(item) is not HostileReason for item in self.reasons
        ):
            raise TypeError("reasons must be an exact tuple of HostileReason values")
        if self.admitted == bool(self.reasons):
            _fail("admitted content has no reasons and rejected content has at least one")


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    """Register-owned meaning and acquisition context for exact bytes."""

    artifact_id: str
    artifact_version_id: str
    artifact_class: ArtifactClass
    source_id: str
    observation_id: str
    observation_cutoff: str
    acquired_at: str
    acquisition_method: str
    source_locator: str
    declared_media_type: str
    detected_media_type: str
    content_encoding: str
    character_encoding: str
    transport_metadata: tuple[tuple[str, str], ...]
    retention: RetentionProfile

    def __post_init__(self) -> None:
        _identifier(self.artifact_id, "artifact_id")
        _identifier(self.artifact_version_id, "artifact_version_id")
        if type(self.artifact_class) is not ArtifactClass:
            raise TypeError("artifact_class must be an exact ArtifactClass")
        _identifier(self.source_id, "source_id")
        _identifier(self.observation_id, "observation_id")
        for field in (
            "observation_cutoff",
            "acquired_at",
            "acquisition_method",
            "source_locator",
            "declared_media_type",
            "detected_media_type",
            "content_encoding",
            "character_encoding",
        ):
            _text(getattr(self, field), field)
        if type(self.transport_metadata) is not tuple:
            raise TypeError("transport_metadata must be an exact tuple")
        keys: set[str] = set()
        for item in self.transport_metadata:
            if type(item) is not tuple or len(item) != len(("key", "value")):
                raise TypeError("transport metadata entries must be exact pairs")
            key, value = item
            _text(key, "transport metadata key")
            _text(value, "transport metadata value")
            if key.lower() in {"authorization", "cookie", "proxy-authorization", "set-cookie"}:
                _fail("secret-bearing transport metadata is forbidden")
            if key in keys:
                _fail("transport metadata keys must be unique")
            keys.add(key)
        if type(self.retention) is not RetentionProfile:
            raise TypeError("retention must be an exact RetentionProfile")


@dataclass(frozen=True, slots=True)
class ExactObjectReference:
    """Exact immutable vault object version and content identity."""

    vault: VaultName
    logical_key: str
    version_id: str
    fingerprint: str
    byte_length: int

    def __post_init__(self) -> None:
        if type(self.vault) is not VaultName:
            raise TypeError("vault must be an exact VaultName")
        _logical_key(self.logical_key)
        _version(self.version_id)
        _fingerprint(self.fingerprint, "fingerprint")
        if type(self.byte_length) is not int:
            raise TypeError("byte_length must be an exact integer")
        if self.byte_length < 0:
            _fail("byte_length cannot be negative")


@dataclass(frozen=True, slots=True)
class VaultWriteReceipt:
    """Conditional-create and read-back result for one exact version."""

    reference: ExactObjectReference
    created: bool
    read_back_verified: bool
    retention: RetentionProfile

    def __post_init__(self) -> None:
        if type(self.reference) is not ExactObjectReference:
            raise TypeError("reference must be an ExactObjectReference")
        if type(self.created) is not bool or type(self.read_back_verified) is not bool:
            raise TypeError("receipt flags must be exact booleans")
        if not self.read_back_verified:
            _fail("a successful vault write receipt must include verified read-back")
        if type(self.retention) is not RetentionProfile:
            raise TypeError("retention must be an exact RetentionProfile")


@dataclass(frozen=True, slots=True)
class EvidenceReadReceipt:
    """Audited exact-version read result."""

    reference: ExactObjectReference
    required_use: str
    artifact_class: ArtifactClass
    accessed_at: str

    def __post_init__(self) -> None:
        if type(self.reference) is not ExactObjectReference:
            raise TypeError("reference must be an ExactObjectReference")
        _text(self.required_use, "required_use")
        if type(self.artifact_class) is not ArtifactClass:
            raise TypeError("artifact_class must be an exact ArtifactClass")
        _text(self.accessed_at, "accessed_at")


@dataclass(frozen=True, slots=True)
class EvidenceManifestEntry:
    """One artifact context and exact primary object in a package."""

    descriptor: ArtifactDescriptor
    primary: ExactObjectReference

    def __post_init__(self) -> None:
        if type(self.descriptor) is not ArtifactDescriptor:
            raise TypeError("descriptor must be an exact ArtifactDescriptor")
        if type(self.primary) is not ExactObjectReference:
            raise TypeError("primary must be an exact ExactObjectReference")
        if self.primary.vault is not VaultName.PRIMARY:
            _fail("manifest entries require a primary-vault reference")


@dataclass(frozen=True, slots=True)
class EvidenceManifest:
    """Complete canonical inventory written only after all content objects."""

    package_kind: str
    package_id: str
    observation_id: str
    entries: tuple[EvidenceManifestEntry, ...]

    def __post_init__(self) -> None:
        if _SAFE_SEGMENT.fullmatch(_text(self.package_kind, "package_kind")) is None:
            _fail("package_kind must be one bounded lowercase path segment")
        _identifier(self.package_id, "package_id")
        _identifier(self.observation_id, "observation_id")
        if type(self.entries) is not tuple or not self.entries:
            _fail("entries must be one non-empty exact tuple")
        if any(type(entry) is not EvidenceManifestEntry for entry in self.entries):
            raise TypeError("entries must contain exact EvidenceManifestEntry values")
        artifact_ids = [entry.descriptor.artifact_id for entry in self.entries]
        if len(set(artifact_ids)) != len(artifact_ids):
            _fail("manifest artifact identities must be unique")

    def document(self) -> dict[str, JsonValue]:
        """Return the bounded JSON document whose bytes define the package."""
        entries: list[JsonValue] = []
        for item in sorted(self.entries, key=lambda value: value.descriptor.artifact_id):
            descriptor = item.descriptor
            entries.append(
                {
                    "artifact_class": descriptor.artifact_class.value,
                    "artifact_id": descriptor.artifact_id,
                    "artifact_version_id": descriptor.artifact_version_id,
                    "byte_length": item.primary.byte_length,
                    "fingerprint": item.primary.fingerprint,
                    "logical_key": item.primary.logical_key,
                    "primary_version_id": item.primary.version_id,
                }
            )
        return {
            "entries": entries,
            "observation_id": self.observation_id,
            "package_id": self.package_id,
            "package_kind": self.package_kind,
            "schema_id": "asklegal.evidence-manifest",
            "schema_version": "1.0.0",
        }


@dataclass(frozen=True, slots=True)
class RecoveryCopyReceipt:
    """Verified primary-to-recovery copy for one exact version."""

    primary: ExactObjectReference
    recovery: ExactObjectReference

    def __post_init__(self) -> None:
        if (
            type(self.primary) is not ExactObjectReference
            or type(self.recovery) is not ExactObjectReference
        ):
            raise TypeError("copy receipt references must be exact")
        if (
            self.primary.vault is not VaultName.PRIMARY
            or self.recovery.vault is not VaultName.RECOVERY
        ):
            _fail("copy receipt must bind primary to recovery")
        if (self.primary.fingerprint, self.primary.byte_length) != (
            self.recovery.fingerprint,
            self.recovery.byte_length,
        ):
            _fail("copy receipt content facts must agree")


@dataclass(frozen=True, slots=True)
class EvidencePackageReceipt:
    """Complete two-vault, manifest-last evidence package proof."""

    manifest: EvidenceManifest
    primary_manifest: ExactObjectReference
    recovery_manifest: ExactObjectReference
    copies: tuple[RecoveryCopyReceipt, ...]

    def __post_init__(self) -> None:
        if type(self.manifest) is not EvidenceManifest:
            raise TypeError("manifest must be an exact EvidenceManifest")
        if (
            type(self.primary_manifest) is not ExactObjectReference
            or type(self.recovery_manifest) is not ExactObjectReference
        ):
            raise TypeError("manifest references must be exact")
        if self.primary_manifest.vault is not VaultName.PRIMARY:
            _fail("primary manifest receipt must reference the primary vault")
        if self.recovery_manifest.vault is not VaultName.RECOVERY:
            _fail("recovery manifest receipt must reference the recovery vault")
        if self.primary_manifest.fingerprint != self.recovery_manifest.fingerprint:
            _fail("primary and recovery manifest bytes must agree")
        if type(self.copies) is not tuple:
            raise TypeError("copies must be an exact tuple")
        expected = {entry.primary for entry in self.manifest.entries}
        actual = {copy.primary for copy in self.copies}
        if expected != actual:
            raise PackageIncomplete("every manifest entry requires one recovery copy")


def content_logical_key(fingerprint: str) -> str:
    """Derive the normative content-addressed logical object key."""
    digest = _fingerprint(fingerprint, "fingerprint").removeprefix("sha256:")
    return f"objects/sha256/{digest[:2]}/{digest[2:]}"


def manifest_logical_key(manifest: EvidenceManifest, fingerprint: str) -> str:
    """Derive the normative manifest-last logical key."""
    digest = _fingerprint(fingerprint, "fingerprint").removeprefix("sha256:")
    return f"packages/{manifest.package_kind}/{manifest.package_id}/{digest}.json"


def _logical_key(value: object) -> str:
    text = _text(value, "logical_key")
    if text.startswith("/") or ".." in text.split("/") or "//" in text:
        _fail("logical_key must be relative, normalized, and contained")
    if any(_SAFE_SEGMENT.fullmatch(part) is None for part in text.split("/")):
        _fail("logical_key contains an unsafe segment")
    return text


def validate_logical_key(value: object) -> str:
    """Return one normalized contained logical object key."""
    return _logical_key(value)


def bytes_fingerprint(content: bytes) -> str:
    """Fingerprint exact raw bytes without conversion."""
    if type(content) is not bytes:
        raise TypeError("content must be exact bytes")
    return f"sha256:{sha256(content).hexdigest()}"
