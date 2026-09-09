"""Offline V1 Boto3/Versity immutable-vault adapter proofs."""

from __future__ import annotations

import base64
import importlib
from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from typing import Protocol, TypeIs, runtime_checkable

import pytest
from asklegal_contracts import canonicalize
from asklegal_evidence_vault import (
    ArtifactClass,
    ArtifactDescriptor,
    CorruptEvidence,
    ExactObjectReference,
    ManifestLastPackageWriter,
    RecoveryCopier,
    RetentionProfile,
    S3AccessCredential,
    S3ImmutableVault,
    S3VaultError,
    S3VaultErrorCode,
    V1S3VaultSettings,
    VaultCollision,
    VaultName,
    content_logical_key,
    create_exact_v1_s3_vault,
    create_v1_s3_client,
    s3_version_reference,
)


class _SessionNamespace(Protocol):
    Session: object


@runtime_checkable
class _Boto3Module(Protocol):
    session: _SessionNamespace


@runtime_checkable
class _ConfigView(Protocol):
    signature_version: str
    retries: Mapping[str, object]
    s3: Mapping[str, object]
    connect_timeout: int
    read_timeout: int


class _ClientErrorFactory(Protocol):
    def __call__(self, response: dict[str, object], operation: str) -> object:
        """Create one provider exception."""
        ...


def _load_boto3() -> _Boto3Module:
    module = importlib.import_module("boto3")
    if not isinstance(module, _Boto3Module):
        message = "boto3 module does not expose the required session boundary"
        raise TypeError(message)
    return module


def _is_client_error_factory(value: object) -> TypeIs[_ClientErrorFactory]:
    return callable(value)


def _load_client_error_factory() -> _ClientErrorFactory:
    value = vars(importlib.import_module("botocore.exceptions")).get("ClientError")
    if not _is_client_error_factory(value):
        message = "botocore ClientError factory is unavailable"
        raise RuntimeError(message)
    return value


boto3 = _load_boto3()
ClientError = _load_client_error_factory()

_RETENTION = RetentionProfile("source-evidence", "2030-01-01T00:00:00Z")
_CONNECT_TIMEOUT_SECONDS = 4
_READ_TIMEOUT_SECONDS = 5
_V1_CONNECT_TIMEOUT_SECONDS = 5
_V1_READ_TIMEOUT_SECONDS = 30
_PRECONDITION_CODE = "PreconditionFailed"
_MISSING_VERSION_CODE = "NoSuchVersion"
_PROVIDER_DETAIL = "synthetic provider detail"
_INVALID_PUT_FIXTURE = "invalid put fixture"


class _Body:
    """Bounded in-memory streaming body fake."""

    def __init__(self, content: bytes) -> None:
        self._content = content
        self.closed = False

    def read(self, amount: int | None = None) -> bytes:
        return self._content if amount is None else self._content[:amount]

    def close(self) -> None:
        self.closed = True


class _FakeS3Client:
    """Small exact-version S3 behavioral fake behind the adapter protocol."""

    def __init__(self) -> None:
        self._objects: dict[tuple[str, str, str], dict[str, object]] = {}
        self._current: dict[tuple[str, str], str] = {}
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._next_version = 1
        self.versioning_enabled = True
        self.object_lock_enabled = True

    def put_object(self, **kwargs: object) -> Mapping[str, object]:
        self.calls.append(("put_object", dict(kwargs)))
        bucket = _text_argument(kwargs, "Bucket")
        key = _text_argument(kwargs, "Key")
        identity = (bucket, key)
        if identity in self._current:
            raise _client_error(_PRECONDITION_CODE, _PROVIDER_DETAIL, "PutObject")
        content = kwargs.get("Body")
        metadata = _string_object_dict(kwargs.get("Metadata"))
        retain_until = kwargs.get("ObjectLockRetainUntilDate")
        hold = kwargs.get("ObjectLockLegalHoldStatus")
        if (
            type(content) is not bytes
            or metadata is None
            or type(retain_until) is not datetime
            or hold not in {"ON", "OFF"}
        ):
            raise AssertionError(_INVALID_PUT_FIXTURE)
        version = f"opaque/version+{self._next_version}=="
        self._next_version += 1
        self._current[identity] = version
        self._objects[(bucket, key, version)] = {
            "content": content,
            "hold": hold,
            "metadata": dict(metadata),
            "retain_until": retain_until,
        }
        return {"VersionId": version}

    def get_object(self, **kwargs: object) -> Mapping[str, object]:
        self.calls.append(("get_object", dict(kwargs)))
        record = self._record(kwargs, "GetObject")
        return {"Body": _Body(_bytes_record(record, "content"))}

    def head_object(self, **kwargs: object) -> Mapping[str, object]:
        self.calls.append(("head_object", dict(kwargs)))
        record, version = self._record_and_version(kwargs, "HeadObject")
        return {
            "Metadata": record["metadata"],
            "VersionId": version,
            "ContentLength": len(_bytes_record(record, "content")),
        }

    def get_object_retention(self, **kwargs: object) -> Mapping[str, object]:
        self.calls.append(("get_object_retention", dict(kwargs)))
        record = self._record(kwargs, "GetObjectRetention")
        return {
            "Retention": {
                "Mode": "COMPLIANCE",
                "RetainUntilDate": record["retain_until"],
            }
        }

    def get_object_legal_hold(self, **kwargs: object) -> Mapping[str, object]:
        self.calls.append(("get_object_legal_hold", dict(kwargs)))
        record = self._record(kwargs, "GetObjectLegalHold")
        return {"LegalHold": {"Status": record["hold"]}}

    def get_bucket_versioning(self, **kwargs: object) -> Mapping[str, object]:
        self.calls.append(("get_bucket_versioning", dict(kwargs)))
        return {"Status": "Enabled" if self.versioning_enabled else "Suspended"}

    def get_object_lock_configuration(self, **kwargs: object) -> Mapping[str, object]:
        self.calls.append(("get_object_lock_configuration", dict(kwargs)))
        state = "Enabled" if self.object_lock_enabled else "Disabled"
        return {"ObjectLockConfiguration": {"ObjectLockEnabled": state}}

    def corrupt(self, bucket: str, key: str) -> None:
        version = self._current[(bucket, key)]
        self._objects[(bucket, key, version)]["content"] = b"corrupt"

    def _record(self, kwargs: dict[str, object], operation: str) -> dict[str, object]:
        return self._record_and_version(kwargs, operation)[0]

    def _record_and_version(
        self, kwargs: dict[str, object], operation: str
    ) -> tuple[dict[str, object], str]:
        bucket = _text_argument(kwargs, "Bucket")
        key = _text_argument(kwargs, "Key")
        version_value = kwargs.get("VersionId")
        version = (
            version_value
            if isinstance(version_value, str)
            else self._current.get((bucket, key), "missing")
        )
        record = self._objects.get((bucket, key, version))
        if record is None:
            raise _client_error(_MISSING_VERSION_CODE, _PROVIDER_DETAIL, operation)
        return record, version


def _text_argument(values: dict[str, object], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str):
        raise TypeError(name)
    return value


def _bytes_record(record: dict[str, object], name: str) -> bytes:
    value = record.get(name)
    if not isinstance(value, bytes):
        raise TypeError(name)
    return value


def _string_object_dict(value: object) -> dict[str, object] | None:
    if not _is_object_dict(value):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str:
            return None
        result[key] = item
    return result


def _is_object_dict(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def _client_error(code: str, message: str, operation: str) -> Exception:
    error = ClientError({"Error": {"Code": code, "Message": message}}, operation)
    if not isinstance(error, Exception):
        message = "botocore ClientError factory returned a non-exception"
        raise TypeError(message)
    return error


def _credential() -> S3AccessCredential:
    return S3AccessCredential.from_bytes(
        canonicalize(
            {
                "access_key_id": "synthetic-access",
                "secret_access_key": "synthetic-secret",
            }
        )
    )


def _descriptor() -> ArtifactDescriptor:
    return ArtifactDescriptor(
        artifact_id="art_" + "1" * 48,
        artifact_version_id="evi_" + "2" * 48,
        artifact_class=ArtifactClass.SOURCE_CONTENT,
        source_id="src_" + "3" * 48,
        observation_id="obs_" + "4" * 48,
        observation_cutoff="2026-08-17T00:00:00Z",
        acquired_at="2026-08-17T00:00:00Z",
        acquisition_method="GET",
        source_locator="https://synthetic.invalid/source",
        declared_media_type="application/octet-stream",
        detected_media_type="application/octet-stream",
        content_encoding="identity",
        character_encoding="binary",
        transport_metadata=(("status-code", "200"),),
        retention=_RETENTION,
    )


def test_v1_s3_credentials_and_settings_are_closed_and_redacted() -> None:
    """Reject ambient or malformed credentials and cross-vault endpoint drift."""
    credential = _credential()
    assert "synthetic-access" not in repr(credential)
    assert "synthetic-secret" not in repr(credential)
    assert V1S3VaultSettings.for_vault(VaultName.PRIMARY).endpoint_url == (
        "https://vault-primary:7070"
    )
    assert V1S3VaultSettings.for_vault(VaultName.RECOVERY).bucket == ("asklegal-recovery-evidence")

    for raw in (
        b"",
        b"{}",
        b'{"access_key_id":"only"}',
        b'{"access_key_id":"a","secret_access_key":"s","extra":"x"}',
    ):
        with pytest.raises(S3VaultError) as error:
            S3AccessCredential.from_bytes(raw)
        assert error.value.code is S3VaultErrorCode.CREDENTIAL

    primary = V1S3VaultSettings.for_vault(VaultName.PRIMARY)
    with pytest.raises(S3VaultError) as error:
        V1S3VaultSettings(
            VaultName.PRIMARY,
            "https://vault-recovery:7070",
            primary.bucket,
            primary.ca_bundle_path,
        )
    assert error.value.code is S3VaultErrorCode.CONFIGURATION


def test_boto3_client_factory_uses_only_explicit_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disable the ambient credential chain and bind TLS, SigV4, path style, and retries."""
    session_calls: list[dict[str, object]] = []
    client_calls: list[tuple[str, dict[str, object]]] = []
    client = _FakeS3Client()

    class FakeSession:
        def __init__(self, **kwargs: object) -> None:
            session_calls.append(kwargs)

        def client(self, service: str, **kwargs: object) -> _FakeS3Client:
            client_calls.append((service, kwargs))
            return client

    monkeypatch.setattr(boto3.session, "Session", FakeSession)
    settings = V1S3VaultSettings.for_vault(VaultName.PRIMARY)
    created = create_v1_s3_client(
        settings,
        _credential(),
        retry_attempts=3,
        connect_timeout_seconds=_CONNECT_TIMEOUT_SECONDS,
        read_timeout_seconds=_READ_TIMEOUT_SECONDS,
    )

    assert created is client
    assert session_calls == [
        {
            "aws_access_key_id": "synthetic-access",
            "aws_secret_access_key": "synthetic-secret",
            "aws_session_token": None,
            "region_name": "us-east-1",
        }
    ]
    service, arguments = client_calls[0]
    assert service == "s3"
    assert arguments["endpoint_url"] == "https://vault-primary:7070"
    assert arguments["verify"] == "/etc/asklegal/trust/vault-primary-ca.pem"
    config = arguments["config"]
    assert isinstance(config, _ConfigView)
    assert config.signature_version == "s3v4"
    assert config.retries == {"mode": "standard", "total_max_attempts": 3}
    assert config.s3 == {"addressing_style": "path"}
    assert config.connect_timeout == _CONNECT_TIMEOUT_SECONDS
    assert config.read_timeout == _READ_TIMEOUT_SECONDS

    exact_vault = create_exact_v1_s3_vault(VaultName.PRIMARY, _credential())
    assert exact_vault.vault_name is VaultName.PRIMARY
    exact_config = client_calls[1][1]["config"]
    assert isinstance(exact_config, _ConfigView)
    assert exact_config.retries == {"mode": "standard", "total_max_attempts": 3}
    assert exact_config.connect_timeout == _V1_CONNECT_TIMEOUT_SECONDS
    assert exact_config.read_timeout == _V1_READ_TIMEOUT_SECONDS


def test_s3_conditional_create_replay_retention_and_exact_read() -> None:
    """Create once with Object Lock, then adopt only one byte-identical exact version."""
    client = _FakeS3Client()
    vault = S3ImmutableVault(client, V1S3VaultSettings.for_vault(VaultName.PRIMARY))
    content = b"immutable source"
    key = content_logical_key("sha256:" + sha256(content).hexdigest())

    first = vault.conditional_create(key, content, _RETENTION)
    replay = vault.conditional_create(key, content, _RETENTION)

    assert first.created is True
    assert replay.created is False
    assert replay.reference == first.reference
    assert vault.read_exact(first.reference) == content
    put = next(arguments for operation, arguments in client.calls if operation == "put_object")
    assert put["IfNoneMatch"] == "*"
    assert put["ObjectLockMode"] == "COMPLIANCE"
    assert put["ObjectLockLegalHoldStatus"] == "OFF"
    assert put["ChecksumSHA256"] == base64_sha256(content)


def test_s3_resolve_current_preserves_the_provider_version_reference() -> None:
    """Read-only key resolution returns an `s3v_` reference, never a local hash version."""
    client = _FakeS3Client()
    vault = S3ImmutableVault(client, V1S3VaultSettings.for_vault(VaultName.PRIMARY))
    key = "proof/provider-version.json"
    assert vault.resolve_current(key) is None
    receipt = vault.conditional_create(key, b"immutable", _RETENTION)
    resolved = vault.resolve_current(key)
    assert resolved == receipt.reference
    assert resolved is not None
    assert resolved.version_id.startswith("s3v_")


def test_s3_readiness_requires_versioning_and_object_lock_without_writing() -> None:
    """Reject a bucket that cannot preserve exact immutable versions."""
    client = _FakeS3Client()
    vault = S3ImmutableVault(client, V1S3VaultSettings.for_vault(VaultName.PRIMARY))

    vault.check_readiness()
    assert all(operation != "put_object" for operation, _ in client.calls)

    client.versioning_enabled = False
    with pytest.raises(S3VaultError) as error:
        vault.check_readiness()
    assert error.value.code is S3VaultErrorCode.READINESS


def base64_sha256(content: bytes) -> str:
    """Return the expected Boto3 checksum value."""
    return base64.b64encode(sha256(content).digest()).decode("ascii")


def test_s3_collision_corruption_and_provider_errors_fail_closed() -> None:
    """Never adopt different bytes and never expose provider error text."""
    client = _FakeS3Client()
    vault = S3ImmutableVault(client, V1S3VaultSettings.for_vault(VaultName.PRIMARY))
    key = "objects/sha256/aa/exact"
    receipt = vault.conditional_create(key, b"first", _RETENTION)
    with pytest.raises(VaultCollision):
        vault.conditional_create(key, b"different", _RETENTION)

    client.corrupt("asklegal-primary-evidence", key)
    with pytest.raises(CorruptEvidence):
        vault.read_exact(receipt.reference)

    missing = ExactObjectReference(
        receipt.reference.vault,
        receipt.reference.logical_key,
        s3_version_reference("absent-version"),
        receipt.reference.fingerprint,
        receipt.reference.byte_length,
    )
    with pytest.raises(FileNotFoundError) as error:
        vault.read_exact(missing)
    assert "synthetic provider detail" not in str(error.value)


def test_manifest_and_recovery_copy_are_content_first_and_manifest_last() -> None:
    """Use the shared package protocol across two separately configured S3 vaults."""
    primary_client = _FakeS3Client()
    recovery_client = _FakeS3Client()
    primary = S3ImmutableVault(primary_client, V1S3VaultSettings.for_vault(VaultName.PRIMARY))
    recovery = S3ImmutableVault(recovery_client, V1S3VaultSettings.for_vault(VaultName.RECOVERY))
    writer = ManifestLastPackageWriter(primary)
    writer.stage_content(_descriptor(), b"exact evidence")
    writer.commit_manifest(
        package_kind="source-snapshot",
        package_id="pkg_" + "5" * 48,
        observation_id="obs_" + "4" * 48,
        retention=_RETENTION,
    )
    complete = writer.finalize_recovery(RecoveryCopier(primary, recovery), _RETENTION)

    assert len(complete.copies) == 1
    primary_puts = [call[1]["Key"] for call in primary_client.calls if call[0] == "put_object"]
    recovery_puts = [call[1]["Key"] for call in recovery_client.calls if call[0] == "put_object"]
    assert str(primary_puts[0]).startswith("objects/")
    assert str(primary_puts[-1]).startswith("packages/")
    assert str(recovery_puts[0]).startswith("objects/")
    assert str(recovery_puts[-1]).startswith("packages/")
