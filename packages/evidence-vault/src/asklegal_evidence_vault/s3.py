"""V1 S3-compatible immutable vault adapter for the two Versity gateways."""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol, runtime_checkable

import boto3
from asklegal_contracts import parse_json_bytes
from botocore.client import Config
from botocore.exceptions import ClientError

from .model import (
    ArtifactClass,
    CorruptEvidence,
    EvidenceReadReceipt,
    ExactObjectReference,
    RetentionProfile,
    VaultCollision,
    VaultName,
    VaultWriteReceipt,
    bytes_fingerprint,
    s3_provider_version_id,
    s3_version_reference,
    validate_logical_key,
)

_CREDENTIAL_KEYS = frozenset({"access_key_id", "secret_access_key"})
_MAX_CREDENTIAL_BYTES = 4_096
_MAX_SECRET_PART_BYTES = 1_024
_MAX_RETRY_ATTEMPTS = 5
_MAX_TIMEOUT_SECONDS = 60
_V1_RETRY_ATTEMPTS = 3
_V1_CONNECT_TIMEOUT_SECONDS = 5
_V1_READ_TIMEOUT_SECONDS = 30
_FIRST_CONTROL_CODEPOINT = 0x20
_MISSING_CODES = frozenset({"404", "NoSuchKey", "NoSuchVersion", "NotFound"})
_PRECONDITION_CODES = frozenset({"412", "ConditionalRequestConflict", "PreconditionFailed"})
_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SETTINGS = {
    VaultName.PRIMARY: (
        "https://vault-primary:7070",
        "asklegal-primary-evidence",
        "/etc/asklegal/trust/vault-primary-ca.pem",
    ),
    VaultName.RECOVERY: (
        "https://vault-recovery:7070",
        "asklegal-recovery-evidence",
        "/etc/asklegal/trust/vault-recovery-ca.pem",
    ),
}


class S3VaultErrorCode(StrEnum):
    """Closed safe V1 S3 adapter failures."""

    CLIENT = "S3_CLIENT_INVALID"
    CONFIGURATION = "S3_CONFIGURATION_INVALID"
    CREDENTIAL = "S3_CREDENTIAL_INVALID"
    PROVIDER = "S3_PROVIDER_OPERATION_FAILED"
    READINESS = "S3_READINESS_FAILED"
    RESPONSE = "S3_PROVIDER_RESPONSE_INVALID"
    RETENTION = "S3_RETENTION_INVALID"


class S3VaultError(RuntimeError):
    """Vault failure that never includes credentials, endpoints, or provider text."""

    code: S3VaultErrorCode

    def __init__(self, code: S3VaultErrorCode) -> None:
        """Create one safe S3 adapter failure."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True, repr=False)
class S3AccessCredential:
    """Exact static Versity access pair with a permanently redacted representation."""

    _access_key_id: str
    _secret_access_key: str

    @classmethod
    def from_bytes(cls, raw: bytes) -> S3AccessCredential:
        """Parse one closed JSON credential file without environment fallback."""
        try:
            value = parse_json_bytes(raw, max_bytes=_MAX_CREDENTIAL_BYTES)
        except TypeError, ValueError:
            raise S3VaultError(S3VaultErrorCode.CREDENTIAL) from None
        if not isinstance(value, dict) or frozenset(value) != _CREDENTIAL_KEYS:
            raise S3VaultError(S3VaultErrorCode.CREDENTIAL)
        access_key = value.get("access_key_id")
        secret_key = value.get("secret_access_key")
        if not _credential_part(access_key) or not _credential_part(secret_key):
            raise S3VaultError(S3VaultErrorCode.CREDENTIAL)
        return cls(access_key, secret_key)

    def __repr__(self) -> str:
        """Never expose either credential component or its size."""
        return "S3AccessCredential(<redacted>)"

    def reveal_for_client(self) -> tuple[str, str]:
        """Return both values only at the Boto3 client construction boundary."""
        return self._access_key_id, self._secret_access_key


def _credential_part(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value.strip() == value
        and len(value.encode("utf-8")) <= _MAX_SECRET_PART_BYTES
        and not any(ord(character) < _FIRST_CONTROL_CODEPOINT for character in value)
    )


@dataclass(frozen=True, slots=True)
class V1S3VaultSettings:
    """One exact TLS endpoint and bucket for a logical V1 vault."""

    vault_name: VaultName
    endpoint_url: str
    bucket: str
    ca_bundle_path: str
    region: str = "us-east-1"

    def __post_init__(self) -> None:
        """Reject endpoint, bucket, TLS trust, region, and vault-role drift."""
        expected = _SETTINGS.get(self.vault_name)
        if (
            expected is None
            or (self.endpoint_url, self.bucket, self.ca_bundle_path) != expected
            or self.region != "us-east-1"
        ):
            raise S3VaultError(S3VaultErrorCode.CONFIGURATION)

    @classmethod
    def for_vault(cls, vault_name: VaultName) -> V1S3VaultSettings:
        """Return the one endpoint/bucket/trust binding for a logical vault."""
        expected = _SETTINGS.get(vault_name)
        if expected is None:
            raise S3VaultError(S3VaultErrorCode.CONFIGURATION)
        return cls(vault_name, expected[0], expected[1], expected[2])


@runtime_checkable
class ReadableBody(Protocol):
    """Bounded body operations used from a Boto3 streaming response."""

    def read(self, amount: int | None = None) -> bytes:
        """Read at most the requested amount."""
        ...

    def close(self) -> None:
        """Release the response stream."""
        ...


@runtime_checkable
class S3Client(Protocol):
    """Narrow generated S3 methods used by the immutable adapter."""

    def put_object(self, **kwargs: object) -> Mapping[str, object]:
        """Conditionally put one object."""
        ...

    def get_object(self, **kwargs: object) -> Mapping[str, object]:
        """Read one exact object version."""
        ...

    def head_object(self, **kwargs: object) -> Mapping[str, object]:
        """Read one object's non-body metadata."""
        ...

    def get_object_retention(self, **kwargs: object) -> Mapping[str, object]:
        """Read one exact version's retention state."""
        ...

    def get_object_legal_hold(self, **kwargs: object) -> Mapping[str, object]:
        """Read one exact version's legal-hold state."""
        ...

    def get_bucket_versioning(self, **kwargs: object) -> Mapping[str, object]:
        """Read the bucket versioning state."""
        ...

    def get_object_lock_configuration(self, **kwargs: object) -> Mapping[str, object]:
        """Read the bucket Object Lock state."""
        ...


def create_v1_s3_client(
    settings: V1S3VaultSettings,
    credential: S3AccessCredential,
    *,
    retry_attempts: int,
    connect_timeout_seconds: int,
    read_timeout_seconds: int,
) -> S3Client:
    """Create one exact client with explicit credentials and no ambient lookup."""
    if type(settings) is not V1S3VaultSettings or type(credential) is not S3AccessCredential:
        raise S3VaultError(S3VaultErrorCode.CONFIGURATION)
    if (
        type(retry_attempts) is not int
        or not 1 <= retry_attempts <= _MAX_RETRY_ATTEMPTS
        or type(connect_timeout_seconds) is not int
        or not 1 <= connect_timeout_seconds <= _MAX_TIMEOUT_SECONDS
        or type(read_timeout_seconds) is not int
        or not 1 <= read_timeout_seconds <= _MAX_TIMEOUT_SECONDS
    ):
        raise S3VaultError(S3VaultErrorCode.CONFIGURATION)
    access_key, secret_key = credential.reveal_for_client()
    session = boto3.session.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=None,
        region_name=settings.region,
    )
    candidate: object = session.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        verify=settings.ca_bundle_path,
        config=Config(
            signature_version="s3v4",
            retries={"mode": "standard", "total_max_attempts": retry_attempts},
            s3={"addressing_style": "path"},
            connect_timeout=connect_timeout_seconds,
            read_timeout=read_timeout_seconds,
        ),
    )
    if not isinstance(candidate, S3Client):
        raise S3VaultError(S3VaultErrorCode.CLIENT)
    return candidate


def create_exact_v1_s3_vault(
    vault_name: VaultName,
    credential: S3AccessCredential,
) -> S3ImmutableVault:
    """Compose the one bounded V1 client profile without opening a connection."""
    settings = V1S3VaultSettings.for_vault(vault_name)
    client = create_v1_s3_client(
        settings,
        credential,
        retry_attempts=_V1_RETRY_ATTEMPTS,
        connect_timeout_seconds=_V1_CONNECT_TIMEOUT_SECONDS,
        read_timeout_seconds=_V1_READ_TIMEOUT_SECONDS,
    )
    return S3ImmutableVault(client, settings)


class S3ImmutableVault:
    """Exact-version S3 vault with conditional create and verified read-back."""

    vault_name: VaultName

    def __init__(self, client: S3Client, settings: V1S3VaultSettings) -> None:
        """Bind one already-configured client to exactly one logical vault."""
        if not isinstance(client, S3Client) or type(settings) is not V1S3VaultSettings:
            raise S3VaultError(S3VaultErrorCode.CLIENT)
        self._client = client
        self._settings = settings
        self.vault_name = settings.vault_name

    def conditional_create(
        self,
        logical_key: str,
        content: bytes,
        retention: RetentionProfile,
    ) -> VaultWriteReceipt:
        """Conditionally create one retained object and verify its exact version."""
        if type(content) is not bytes or type(retention) is not RetentionProfile:
            raise TypeError("content and retention must be exact values")
        logical_key = validate_logical_key(logical_key)
        if _PROFILE_ID.fullmatch(retention.profile_id) is None:
            raise S3VaultError(S3VaultErrorCode.RETENTION)
        fingerprint = bytes_fingerprint(content)
        retain_until = _retention_datetime(retention.retain_until)
        try:
            response = self._client.put_object(
                Bucket=self._settings.bucket,
                Key=logical_key,
                Body=content,
                ContentLength=len(content),
                ChecksumSHA256=base64.b64encode(sha256(content).digest()).decode("ascii"),
                IfNoneMatch="*",
                Metadata={
                    "asklegal-sha256": fingerprint.removeprefix("sha256:"),
                    "asklegal-retention-profile": retention.profile_id,
                },
                ObjectLockMode="COMPLIANCE",
                ObjectLockRetainUntilDate=retain_until,
                ObjectLockLegalHoldStatus="ON" if retention.legal_hold else "OFF",
            )
        except ClientError as error:
            if _client_error_code(error) not in _PRECONDITION_CODES:
                raise S3VaultError(S3VaultErrorCode.PROVIDER) from None
            return self._adopt_existing(logical_key, content, retention, fingerprint)
        version_id = _response_text(response, "VersionId")
        reference = ExactObjectReference(
            self.vault_name,
            logical_key,
            s3_version_reference(version_id),
            fingerprint,
            len(content),
        )
        self.read_exact(reference)
        if self.retention(reference) != retention:
            raise S3VaultError(S3VaultErrorCode.RETENTION)
        return VaultWriteReceipt(
            reference=reference,
            created=True,
            read_back_verified=True,
            retention=retention,
        )

    def _adopt_existing(
        self,
        logical_key: str,
        content: bytes,
        retention: RetentionProfile,
        fingerprint: str,
    ) -> VaultWriteReceipt:
        try:
            response = self._client.head_object(Bucket=self._settings.bucket, Key=logical_key)
        except ClientError:
            raise S3VaultError(S3VaultErrorCode.PROVIDER) from None
        version_id = _response_text(response, "VersionId")
        reference = ExactObjectReference(
            self.vault_name,
            logical_key,
            s3_version_reference(version_id),
            fingerprint,
            len(content),
        )
        try:
            existing = self.read_exact(reference)
        except CorruptEvidence:
            raise VaultCollision(logical_key) from None
        if existing != content or self.retention(reference) != retention:
            raise VaultCollision(logical_key)
        return VaultWriteReceipt(
            reference=reference,
            created=False,
            read_back_verified=True,
            retention=retention,
        )

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        """Read only one provider version and verify length and SHA-256."""
        self._validate_reference(reference)
        try:
            response = self._client.get_object(
                Bucket=self._settings.bucket,
                Key=reference.logical_key,
                VersionId=s3_provider_version_id(reference.version_id),
                ChecksumMode="ENABLED",
            )
        except ClientError as error:
            if _client_error_code(error) in _MISSING_CODES:
                raise FileNotFoundError(reference.logical_key) from None
            raise S3VaultError(S3VaultErrorCode.PROVIDER) from None
        body = response.get("Body")
        if not isinstance(body, ReadableBody):
            raise S3VaultError(S3VaultErrorCode.RESPONSE)
        try:
            content = body.read(reference.byte_length + 1)
        finally:
            body.close()
        if (
            type(content) is not bytes
            or len(content) != reference.byte_length
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
        """Return true only when the exact provider version exists and verifies."""
        try:
            self.read_exact(reference)
        except FileNotFoundError, CorruptEvidence, S3VaultError:
            return False
        return True

    def check_readiness(self) -> None:
        """Verify the bucket's required immutable capabilities without mutation."""
        try:
            versioning = self._client.get_bucket_versioning(Bucket=self._settings.bucket)
            object_lock = self._client.get_object_lock_configuration(
                Bucket=self._settings.bucket
            )
        except ClientError:
            raise S3VaultError(S3VaultErrorCode.READINESS) from None
        lock_configuration = object_lock.get("ObjectLockConfiguration")
        if (
            versioning.get("Status") != "Enabled"
            or not isinstance(lock_configuration, dict)
            or lock_configuration.get("ObjectLockEnabled") != "Enabled"
        ):
            raise S3VaultError(S3VaultErrorCode.READINESS)

    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        """Read and validate exact COMPLIANCE retention plus legal-hold state."""
        self._validate_reference(reference)
        arguments = {
            "Bucket": self._settings.bucket,
            "Key": reference.logical_key,
            "VersionId": s3_provider_version_id(reference.version_id),
        }
        try:
            head = self._client.head_object(**arguments)
            retention_response = self._client.get_object_retention(**arguments)
            hold_response = self._client.get_object_legal_hold(**arguments)
        except ClientError:
            raise S3VaultError(S3VaultErrorCode.PROVIDER) from None
        metadata = head.get("Metadata")
        retention_value = retention_response.get("Retention")
        hold_value = hold_response.get("LegalHold")
        if (
            not isinstance(metadata, dict)
            or not isinstance(retention_value, dict)
            or not isinstance(hold_value, dict)
            or retention_value.get("Mode") != "COMPLIANCE"
            or hold_value.get("Status") not in {"ON", "OFF"}
        ):
            raise S3VaultError(S3VaultErrorCode.RETENTION)
        profile_id = metadata.get("asklegal-retention-profile")
        retain_until = retention_value.get("RetainUntilDate")
        if type(profile_id) is not str or type(retain_until) is not datetime:
            raise S3VaultError(S3VaultErrorCode.RETENTION)
        return RetentionProfile(
            profile_id,
            _canonical_utc(retain_until),
            legal_hold=hold_value["Status"] == "ON",
        )

    def _validate_reference(self, reference: ExactObjectReference) -> None:
        if type(reference) is not ExactObjectReference:
            raise TypeError("reference must be an exact ExactObjectReference")
        if reference.vault is not self.vault_name:
            raise ValueError("reference names a different vault")
        s3_provider_version_id(reference.version_id)


def _client_error_code(error: ClientError) -> str:
    response: object = error.response
    if not isinstance(response, dict):
        return "UNKNOWN"
    error_value = response.get("Error")
    if not isinstance(error_value, dict):
        return "UNKNOWN"
    code = error_value.get("Code")
    return code if isinstance(code, str) else "UNKNOWN"


def _response_text(response: Mapping[str, object], field: str) -> str:
    value = response.get(field)
    if type(value) is not str or not value:
        raise S3VaultError(S3VaultErrorCode.RESPONSE)
    return value


def _retention_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise S3VaultError(S3VaultErrorCode.RETENTION) from None
    if (
        not value.endswith("Z")
        or parsed.tzinfo is None
        or parsed.utcoffset() != UTC.utcoffset(parsed)
    ):
        raise S3VaultError(S3VaultErrorCode.RETENTION)
    return parsed


def _canonical_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise S3VaultError(S3VaultErrorCode.RETENTION)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
