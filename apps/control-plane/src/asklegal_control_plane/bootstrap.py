"""Fail-visible SQL migration and immutable-vault bootstrap entrypoints."""

from __future__ import annotations

import argparse
import http.client
import importlib
import os
import re
import ssl
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Never, Protocol, runtime_checkable
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree as ET

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import S3AccessCredential, S3VaultError, VaultName
from asklegal_evidence_vault.s3 import V1S3VaultSettings, create_v1_s3_client
from asklegal_management_register.driver import (
    SqlServerPassword,
    V1MssqlAdminConnectionFactory,
    V1MssqlConnectionFactory,
)
from asklegal_management_register.migration import (
    MigrationPackage,
    apply_packages,
    load_package,
)

if TYPE_CHECKING:
    from asklegal_management_register.dbapi import ConnectionFactory

    class ClientError(Exception):
        """Static view of the untyped Botocore provider error."""

        response: object

    class BotoCoreError(Exception):
        """Static view of a provider transport or parameter failure."""

    class MssqlError(Exception):
        """Static view of a SQL driver operation failure."""

else:
    ClientError = vars(importlib.import_module("botocore.exceptions"))["ClientError"]
    BotoCoreError = vars(importlib.import_module("botocore.exceptions"))["BotoCoreError"]
    MssqlError = vars(importlib.import_module("mssql_python"))["Error"]


class _PreparedAwsRequest(Protocol):
    headers: Mapping[str, object]


class _SignableAwsRequest(Protocol):
    def prepare(self) -> _PreparedAwsRequest:
        """Return provider-ready signed request fields."""
        ...


class _AwsRequestFactory(Protocol):
    def __call__(self, **kwargs: object) -> _SignableAwsRequest:
        """Construct one request without opening a connection."""
        ...


class _AwsCredentials(Protocol):
    """Opaque botocore credentials value."""


class _AwsCredentialsFactory(Protocol):
    def __call__(self, access_key: str, secret_key: str) -> _AwsCredentials:
        """Construct one in-memory signing credential."""
        ...


class _AwsSigner(Protocol):
    def add_auth(self, request: _SignableAwsRequest) -> None:
        """Sign one request in place."""
        ...


class _AwsSignerFactory(Protocol):
    def __call__(self, credentials: _AwsCredentials, service: str, region: str) -> _AwsSigner:
        """Construct one exact SigV4 signer."""
        ...


_AWS_REQUEST: _AwsRequestFactory = vars(importlib.import_module("botocore.awsrequest"))[
    "AWSRequest"
]
_AWS_CREDENTIALS: _AwsCredentialsFactory = vars(importlib.import_module("botocore.credentials"))[
    "Credentials"
]
_AWS_SIGNER: _AwsSignerFactory = vars(importlib.import_module("botocore.auth"))["SigV4Auth"]

_REGISTER_SCHEMA = "asklegal.hk-v1-register-bootstrap-readback/v1"
_VAULT_SCHEMA = "asklegal.hk-v1-vault-bootstrap-readback/v1"
_VERSION = "1.0.0"
_DATABASE = "AskLegalPocOperational"
_RUNNER_BUILD = "asklegal-hk-v1-bootstrap-1"
_FP = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_CREDENTIAL_BYTES = 4096
_RETENTION_DAYS = 2555
_VAULT_POLICY_VERSION = "2012-10-17"
_VAULT_BUCKET_ACTIONS = (
    "s3:GetBucketVersioning",
    "s3:GetObjectLockConfiguration",
    "s3:ListBucket",
)
_VAULT_OBJECT_ACTIONS = (
    "s3:GetObject",
    "s3:GetObjectLegalHold",
    "s3:GetObjectRetention",
    "s3:GetObjectVersion",
    "s3:PutObject",
    "s3:PutObjectLegalHold",
    "s3:PutObjectRetention",
)
_APPLICATION_IDENTITIES = (
    ("asklegal_acquisition_app", "asklegal_acquisition_role", "sql-acquisition"),
    ("asklegal_control_app", "asklegal_control_role", "sql-control"),
    ("asklegal_legal_processing_app", "asklegal_legal_processing_role", "sql-processing"),
    ("asklegal_promotion_app", "asklegal_promotion_role", "sql-promotion"),
    ("asklegal_review_app", "asklegal_review_role", "sql-review"),
)
_VAULT_APPLICATION_IDENTITIES = {
    VaultName.PRIMARY: (
        ("vault-primary-acquisition", "asklegal-primary-acquisition"),
        ("vault-primary-control", "asklegal-primary-control"),
        ("vault-primary-processing", "asklegal-primary-processing"),
        ("vault-primary-promotion", "asklegal-primary-promotion"),
        ("vault-primary-review", "asklegal-primary-review"),
    ),
    VaultName.RECOVERY: (
        ("vault-recovery-acquisition", "asklegal-recovery-acquisition"),
        ("vault-recovery-promotion", "asklegal-recovery-promotion"),
    ),
}
_MAX_ADMIN_RESPONSE_BYTES = 1_048_576
_MAX_POLICY_BYTES = 32_768
_VAULT_PORT = 7070
_VERSITY_USER_FIELDS = frozenset({"Access", "Secret", "Role", "UserID", "GroupID", "ProjectID"})


class BootstrapError(RuntimeError):
    """One sanitized bootstrap configuration, provider, or readback failure."""


class RegisterBootstrapPort(Protocol):
    """Exact migration effect and readback boundary."""

    def apply(self, packages: tuple[MigrationPackage, ...]) -> None:
        """Create the database if absent and apply the complete prefix."""
        ...

    def read_prefix(self) -> tuple[tuple[str, str], ...]:
        """Read the exact applied migration prefix."""
        ...

    def provision_application_identities(self, passwords: dict[str, str]) -> None:
        """Create or rotate the five fixed SQL logins and bind their users."""
        ...

    def read_application_identities(self, passwords: dict[str, str]) -> tuple[str, ...]:
        """Authenticate every supplied login and verify its database role."""
        ...


@runtime_checkable
class VaultBootstrapClient(Protocol):
    """Exact bucket create/configure/readback calls needed once."""

    def head_bucket(self, **kwargs: object) -> Mapping[str, object]:
        """Read bucket existence without a body."""
        ...

    def create_bucket(self, **kwargs: object) -> Mapping[str, object]:
        """Create one exact Object-Lock-enabled bucket."""
        ...

    def put_bucket_versioning(self, **kwargs: object) -> Mapping[str, object]:
        """Enable bucket versioning."""
        ...

    def put_object_lock_configuration(self, **kwargs: object) -> Mapping[str, object]:
        """Set the immutable default retention rule."""
        ...

    def get_bucket_versioning(self, **kwargs: object) -> Mapping[str, object]:
        """Read back bucket versioning."""
        ...

    def get_object_lock_configuration(self, **kwargs: object) -> Mapping[str, object]:
        """Read back Object Lock configuration."""
        ...

    def put_bucket_policy(self, **kwargs: object) -> Mapping[str, object]:
        """Grant only the exact application identities and required operations."""
        ...

    def get_bucket_policy(self, **kwargs: object) -> Mapping[str, object]:
        """Read back the exact access-key policy."""
        ...


class VaultIdentityAdministrationPort(Protocol):
    """Create/rotate and read back only the fixed local vault users."""

    def provision(self, credentials: tuple[S3AccessCredential, ...]) -> None:
        """Create missing identities or rotate an existing identity's secret."""
        ...

    def readback(self, credentials: tuple[S3AccessCredential, ...]) -> tuple[str, ...]:
        """Return the exact admitted access identities after secret/role verification."""
        ...


def _fail(code: str) -> Never:
    raise BootstrapError(code)


def _fingerprint(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


def _json_object(value: object, code: str) -> dict[str, JsonValue]:
    try:
        parsed = checked_json_value(value)
    except TypeError as error:
        raise BootstrapError(code) from error
    if not isinstance(parsed, dict):
        _fail(code)
    return parsed


def _safe_path(path: Path, code: str, *, file: bool = False, directory: bool = False) -> Path:
    if not path.is_absolute() or path == Path(path.anchor) or path != path.resolve(strict=False):
        _fail(code)
    current = path
    while current != Path(current.anchor):
        if current.is_symlink():
            _fail(code)
        current = current.parent
    if file and not path.is_file():
        _fail(code)
    if directory and not path.is_dir():
        _fail(code)
    return path


def _credential(path: Path) -> bytes:
    code = "BOOTSTRAP_CREDENTIAL_INVALID"
    _safe_path(path, code, file=True)
    try:
        content = path.read_bytes()
    except OSError as error:
        raise BootstrapError(code) from error
    if not 1 <= len(content) <= _MAX_CREDENTIAL_BYTES or b"\x00" in content:
        _fail("BOOTSTRAP_CREDENTIAL_INVALID")
    return content


def _atomic_receipt(path: Path, body: dict[str, JsonValue]) -> bytes:
    _safe_path(path, "BOOTSTRAP_RECEIPT_INVALID")
    content = canonicalize(
        checked_json_value(
            {**body, "fingerprint": _fingerprint(canonicalize(checked_json_value(body)))}
        )
    )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        _fail("BOOTSTRAP_RECEIPT_INVALID")
    if path.exists():
        if path.is_symlink() or path.read_bytes() != content:
            _fail("BOOTSTRAP_RECEIPT_DRIFT")
        return content
    temporary = path.parent / f".{path.name}.{token_hex(8)}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        os.write(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.replace(path)
    if path.read_bytes() != content:
        _fail("BOOTSTRAP_RECEIPT_INVALID")
    return content


def _migration_packages(root: Path) -> tuple[MigrationPackage, ...]:
    code = "REGISTER_MIGRATION_INPUT_INVALID"
    _safe_path(root, code, directory=True)
    directories = tuple(path for path in sorted(root.iterdir()) if path.is_dir())
    if not directories or any(path.is_symlink() for path in directories):
        _fail("REGISTER_MIGRATION_INPUT_INVALID")
    try:
        packages = tuple(load_package(path) for path in directories)
    except (OSError, RuntimeError, ValueError) as error:
        raise BootstrapError(code) from error
    expected = tuple(f"{index:06d}" for index in range(1, len(packages) + 1))
    if tuple(package.migration_id for package in packages) != expected:
        _fail("REGISTER_MIGRATION_INPUT_INVALID")
    return packages


@dataclass(frozen=True, slots=True)
class SqlRegisterBootstrap:
    """Concrete SQL bootstrap over the repository migration runner."""

    password: SqlServerPassword

    def _factory(self, database: str, *, autocommit: bool = False) -> ConnectionFactory:
        return V1MssqlAdminConnectionFactory(
            self.password,
            database=database,
            autocommit=autocommit,
        )

    def apply(self, packages: tuple[MigrationPackage, ...]) -> None:
        """Create the exact database if absent and apply the complete prefix."""
        master = self._factory("master", autocommit=True)()
        cursor = master.cursor()
        try:
            cursor.execute(
                "IF DB_ID(?) IS NULL EXEC(N'CREATE DATABASE [AskLegalPocOperational]');",
                (_DATABASE,),
            )
        finally:
            cursor.close()
            master.close()
        apply_packages(
            self._factory(_DATABASE),
            tuple(package.directory for package in packages),
            runner_build=_RUNNER_BUILD,
        )

    def read_prefix(self) -> tuple[tuple[str, str], ...]:
        """Read the exact ordered migration identities and SHA-256 values."""
        connection = self._factory(_DATABASE)()
        cursor = connection.cursor()
        try:
            rows = cursor.execute(
                "SELECT migration_id, package_fingerprint FROM migration.applied_fact "
                "ORDER BY migration_id;"
            ).fetchall()
        finally:
            cursor.close()
            connection.close()
        result: list[tuple[str, str]] = []
        for migration_id, fingerprint in rows:
            if type(migration_id) is not str or type(fingerprint) is not bytes:
                _fail("REGISTER_MIGRATION_READBACK_INVALID")
            result.append((migration_id, "sha256:" + fingerprint.hex()))
        return tuple(result)

    def provision_application_identities(self, passwords: dict[str, str]) -> None:
        """Create/rotate only the fixed logins and map migration-owned users."""
        expected = tuple(login for login, _role, _credential in _APPLICATION_IDENTITIES)
        if tuple(passwords) != expected:
            _fail("REGISTER_APPLICATION_IDENTITY_INPUT_INVALID")
        master = self._factory("master", autocommit=True)()
        cursor = master.cursor()
        try:
            for login, _role, _credential in _APPLICATION_IDENTITIES:
                present = cursor.execute(
                    "SELECT CASE WHEN SUSER_ID(?) IS NULL THEN 0 ELSE 1 END;", (login,)
                ).fetchone()
                if present is None or present[0] not in {0, 1}:
                    _fail("REGISTER_APPLICATION_IDENTITY_READBACK_INVALID")
                if present[0] == 0:
                    cursor.execute(
                        "EXEC sys.sp_addlogin @loginame=?, @passwd=?, @defdb=?;",
                        (login, passwords[login], _DATABASE),
                    )
                else:
                    cursor.execute(
                        "EXEC sys.sp_password @old=NULL, @new=?, @loginame=?;",
                        (passwords[login], login),
                    )
        finally:
            cursor.close()
            master.close()
        database = self._factory(_DATABASE, autocommit=True)()
        cursor = database.cursor()
        try:
            for login, _role, _credential in _APPLICATION_IDENTITIES:
                cursor.execute(f"ALTER USER [{login}] WITH LOGIN = [{login}];")
        finally:
            cursor.close()
            database.close()

    def read_application_identities(self, passwords: dict[str, str]) -> tuple[str, ...]:
        """Prove each credential logs in to the one expected database role."""
        expected = tuple(login for login, _role, _credential in _APPLICATION_IDENTITIES)
        if tuple(passwords) != expected:
            _fail("REGISTER_APPLICATION_IDENTITY_INPUT_INVALID")
        verified: list[str] = []
        for login, role, _credential in _APPLICATION_IDENTITIES:
            password = SqlServerPassword.from_bytes(passwords[login].encode())
            connection = V1MssqlConnectionFactory(login, password)()
            cursor = connection.cursor()
            try:
                row = cursor.execute("SELECT DB_NAME(), IS_ROLEMEMBER(?);", (role,)).fetchone()
            finally:
                cursor.close()
                connection.close()
            if row is None or row[0] != _DATABASE or row[1] != 1:
                _fail("REGISTER_APPLICATION_IDENTITY_READBACK_INVALID")
            verified.append(login)
        return tuple(verified)


def run_register_bootstrap(
    migrations_root: Path,
    receipt_path: Path,
    port: RegisterBootstrapPort,
    application_passwords: dict[str, str],
    *,
    verify_only: bool,
) -> bytes:
    """Apply or verify the complete migration prefix and retain exact readback."""
    expected_identities = tuple(login for login, _role, _credential in _APPLICATION_IDENTITIES)
    if tuple(application_passwords) != expected_identities:
        _fail("REGISTER_APPLICATION_IDENTITY_INPUT_INVALID")
    try:
        for login in expected_identities:
            SqlServerPassword.from_bytes(
                application_passwords[login].encode("utf-8", errors="strict")
            )
    except AttributeError, UnicodeEncodeError, ValueError:
        code = "REGISTER_APPLICATION_IDENTITY_INPUT_INVALID"
        raise BootstrapError(code) from None
    packages = _migration_packages(migrations_root)
    expected = tuple(
        (package.migration_id, "sha256:" + package.package_fingerprint.hex())
        for package in packages
    )
    if not verify_only:
        port.apply(packages)
        port.provision_application_identities(application_passwords)
    if port.read_prefix() != expected:
        _fail("REGISTER_MIGRATION_READBACK_INVALID")
    identities = port.read_application_identities(application_passwords)
    if identities != expected_identities:
        _fail("REGISTER_APPLICATION_IDENTITY_READBACK_INVALID")
    return _atomic_receipt(
        receipt_path,
        {
            "schema_id": _REGISTER_SCHEMA,
            "schema_version": _VERSION,
            "database": _DATABASE,
            "application_identities": list(identities),
            "migration_prefix": [
                {"migration_id": migration_id, "fingerprint": fingerprint}
                for migration_id, fingerprint in expected
            ],
            "result": "COMPLETE",
            "verified": True,
        },
    )


def _credential_pair(access_path: Path, secret_path: Path) -> S3AccessCredential:
    code = "BOOTSTRAP_CREDENTIAL_INVALID"
    access = _credential(access_path)
    secret = _credential(secret_path)
    try:
        access_text = access.decode("utf-8", errors="strict")
        secret_text = secret.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise BootstrapError(code) from error
    try:
        return S3AccessCredential.from_bytes(
            canonicalize(
                checked_json_value({"access_key_id": access_text, "secret_access_key": secret_text})
            )
        )
    except S3VaultError as error:
        raise BootstrapError(code) from error


def _vault_application_credentials(
    vault: VaultName, credentials: Path
) -> tuple[S3AccessCredential, ...]:
    code = "BOOTSTRAP_CREDENTIAL_INVALID"
    result: list[S3AccessCredential] = []
    for credential_name, expected_access in _VAULT_APPLICATION_IDENTITIES[vault]:
        try:
            credential = S3AccessCredential.from_bytes(_credential(credentials / credential_name))
        except (OSError, S3VaultError, ValueError) as error:
            raise BootstrapError(code) from error
        access, _secret = credential.reveal_for_client()
        if access != expected_access:
            _fail("VAULT_APPLICATION_IDENTITY_INPUT_INVALID")
        result.append(credential)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class VersityIdentityAdministration:
    """Exact SigV4 client for the pinned gateway's bounded IAM API."""

    settings: V1S3VaultSettings
    root_credential: S3AccessCredential

    def _request(self, path: str, body: bytes, expected_status: int) -> bytes:
        parsed = urlsplit(self.settings.endpoint_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"vault-primary", "vault-recovery"}
            or parsed.port != _VAULT_PORT
            or not path.startswith("/")
        ):
            _fail("VAULT_IDENTITY_ADMIN_CONFIGURATION_INVALID")
        access, secret = self.root_credential.reveal_for_client()
        request = _AWS_REQUEST(
            method="PATCH",
            url=self.settings.endpoint_url + path,
            data=body,
            headers={
                "Content-Type": "application/xml",
                "X-Amz-Content-Sha256": sha256(body).hexdigest(),
            },
        )
        _AWS_SIGNER(_AWS_CREDENTIALS(access, secret), "s3", self.settings.region).add_auth(request)
        prepared = request.prepare()
        context = ssl.create_default_context(cafile=self.settings.ca_bundle_path)
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            parsed.port,
            timeout=30,
            context=context,
        )
        response_body: bytes
        try:
            connection.request(
                "PATCH",
                path,
                body=body,
                headers={str(key): str(value) for key, value in prepared.headers.items()},
            )
            response = connection.getresponse()
            response_body = response.read(_MAX_ADMIN_RESPONSE_BYTES + 1)
            if response.status != expected_status or len(response_body) > _MAX_ADMIN_RESPONSE_BYTES:
                _fail("VAULT_IDENTITY_ADMIN_PROVIDER_FAILED")
        except OSError, http.client.HTTPException:
            code = "VAULT_IDENTITY_ADMIN_PROVIDER_FAILED"
            raise BootstrapError(code) from None
        finally:
            connection.close()
        return response_body

    def _users(self) -> tuple[tuple[str, str, str], ...]:
        raw = self._request("/list-users", b"", 200)
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            code = "VAULT_IDENTITY_ADMIN_READBACK_INVALID"
            raise BootstrapError(code) from None
        if root.tag != "ListUserAccountsResult":
            _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
        users: list[tuple[str, str, str]] = []
        for account in root:
            if account.tag != "Account":
                _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
            fields = {child.tag: child.text for child in account}
            if len(account) != len(_VERSITY_USER_FIELDS) or frozenset(fields) != (
                _VERSITY_USER_FIELDS
            ):
                _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
            access = fields["Access"]
            secret = fields["Secret"]
            role = fields["Role"]
            if access is None or secret is None or role is None:
                _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
            users.append((access, secret, role))
        return tuple(users)

    def provision(self, credentials: tuple[S3AccessCredential, ...]) -> None:
        """Create or exactly rotate the fixed ordinary user identities."""
        current_users = self._users()
        existing = {access: (secret, role) for access, secret, role in current_users}
        if len(existing) != len(current_users):
            _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
        requested = tuple(credential.reveal_for_client() for credential in credentials)
        requested_accesses = {access for access, _secret in requested}
        if set(existing) - requested_accesses:
            _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
        for access, secret in requested:
            current = existing.get(access)
            if current is None:
                body = (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    "<Account><Access>"
                    + _xml_text(access)
                    + "</Access><Secret>"
                    + _xml_text(secret)
                    + "</Secret><Role>user</Role></Account>"
                ).encode()
                self._request("/create-user", body, 201)
            elif current != (secret, "user"):
                if current[1] != "user":
                    _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
                body = (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    "<MutableProps><Secret>" + _xml_text(secret) + "</Secret></MutableProps>"
                ).encode()
                self._request("/update-user?access=" + quote(access, safe=""), body, 200)

    def readback(self, credentials: tuple[S3AccessCredential, ...]) -> tuple[str, ...]:
        """Require exactly the requested ordinary identities and credential bytes."""
        actual = self._users()
        expected = tuple((*credential.reveal_for_client(), "user") for credential in credentials)
        if tuple(sorted(actual)) != tuple(sorted(expected)):
            _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
        return tuple(
            access for access, _secret in (item.reveal_for_client() for item in credentials)
        )


def _xml_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def create_v1_vault_identity_administrator(
    vault: VaultName,
    root_access_path: Path,
    root_secret_path: Path,
) -> VersityIdentityAdministration:
    """Create one bounded admin client from the unchanged root credential files."""
    if type(vault) is not VaultName:
        _fail("VAULT_IDENTITY_ADMIN_CONFIGURATION_INVALID")
    return VersityIdentityAdministration(
        V1S3VaultSettings.for_vault(vault),
        _credential_pair(root_access_path, root_secret_path),
    )


def _vault_client(vault: VaultName, credential: S3AccessCredential) -> VaultBootstrapClient:
    settings = V1S3VaultSettings.for_vault(vault)
    client = create_v1_s3_client(
        settings,
        credential,
        retry_attempts=3,
        connect_timeout_seconds=5,
        read_timeout_seconds=30,
    )
    if not isinstance(client, VaultBootstrapClient):
        _fail("VAULT_BOOTSTRAP_CLIENT_INVALID")
    return client


def _vault_policy(bucket: str, accesses: tuple[str, ...]) -> bytes:
    """Build the exact Versity access-key policy used by both retained buckets."""
    return canonicalize(
        checked_json_value(
            {
                "Version": _VAULT_POLICY_VERSION,
                "Statement": [
                    {
                        "Sid": "AskLegalBucketReadback",
                        "Effect": "Allow",
                        "Principal": list(accesses),
                        "Action": list(_VAULT_BUCKET_ACTIONS),
                        "Resource": [f"arn:aws:s3:::{bucket}"],
                    },
                    {
                        "Sid": "AskLegalImmutableObjects",
                        "Effect": "Allow",
                        "Principal": list(accesses),
                        "Action": list(_VAULT_OBJECT_ACTIONS),
                        "Resource": [f"arn:aws:s3:::{bucket}/*"],
                    },
                ],
            }
        )
    )


def _policy_bytes(value: object) -> bytes:
    """Parse one bounded provider policy and normalize it for exact comparison."""
    if type(value) is not str or len(value.encode("utf-8")) > _MAX_POLICY_BYTES:
        _fail("VAULT_BOOTSTRAP_READBACK_INVALID")
    try:
        return canonicalize(parse_json_bytes(value.encode("utf-8"), max_bytes=_MAX_POLICY_BYTES))
    except TypeError, ValueError:
        code = "VAULT_BOOTSTRAP_READBACK_INVALID"
        raise BootstrapError(code) from None


def _configure_vault(
    client: VaultBootstrapClient,
    bucket: str,
    application_credentials: tuple[S3AccessCredential, ...],
    *,
    verify_only: bool,
) -> None:
    accesses = tuple(item.reveal_for_client()[0] for item in application_credentials)
    expected_policy = _vault_policy(bucket, accesses)
    if not verify_only:
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as error:
            response = _json_object(error.response, "VAULT_BOOTSTRAP_PROVIDER_FAILED")
            error_row = _json_object(response.get("Error"), "VAULT_BOOTSTRAP_PROVIDER_FAILED")
            provider_code = error_row.get("Code")
            if str(provider_code) not in {"404", "NoSuchBucket", "NotFound"}:
                _fail("VAULT_BOOTSTRAP_PROVIDER_FAILED")
            client.create_bucket(Bucket=bucket, ObjectLockEnabledForBucket=True)
        client.put_bucket_versioning(
            Bucket=bucket,
            VersioningConfiguration={"Status": "Enabled"},
        )
        client.put_object_lock_configuration(
            Bucket=bucket,
            ObjectLockConfiguration={
                "ObjectLockEnabled": "Enabled",
                "Rule": {
                    "DefaultRetention": {
                        "Mode": "COMPLIANCE",
                        "Days": _RETENTION_DAYS,
                    }
                },
            },
        )
        client.put_bucket_policy(Bucket=bucket, Policy=expected_policy.decode("utf-8"))
    versioning = client.get_bucket_versioning(Bucket=bucket)
    locking = client.get_object_lock_configuration(Bucket=bucket)
    policy = client.get_bucket_policy(Bucket=bucket)
    lock = _json_object(locking.get("ObjectLockConfiguration"), "VAULT_BOOTSTRAP_READBACK_INVALID")
    rule = _json_object(lock.get("Rule"), "VAULT_BOOTSTRAP_READBACK_INVALID")
    retention = _json_object(rule.get("DefaultRetention"), "VAULT_BOOTSTRAP_READBACK_INVALID")
    if (
        versioning.get("Status") != "Enabled"
        or lock.get("ObjectLockEnabled") != "Enabled"
        or retention.get("Mode") != "COMPLIANCE"
        or retention.get("Days") != _RETENTION_DAYS
        or _policy_bytes(policy.get("Policy")) != expected_policy
    ):
        _fail("VAULT_BOOTSTRAP_READBACK_INVALID")


def run_vault_bootstrap(
    receipt_path: Path,
    clients: tuple[tuple[VaultName, VaultBootstrapClient], ...],
    identity_administrators: tuple[tuple[VaultName, VaultIdentityAdministrationPort], ...],
    application_credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    *,
    verify_only: bool,
) -> bytes:
    """Create/configure or verify both exact immutable evidence buckets."""
    if tuple(vault for vault, _client in clients) != (VaultName.PRIMARY, VaultName.RECOVERY):
        _fail("VAULT_BOOTSTRAP_INPUT_INVALID")
    if tuple(vault for vault, _admin in identity_administrators) != (
        VaultName.PRIMARY,
        VaultName.RECOVERY,
    ) or tuple(vault for vault, _credentials in application_credentials) != (
        VaultName.PRIMARY,
        VaultName.RECOVERY,
    ):
        _fail("VAULT_BOOTSTRAP_INPUT_INVALID")
    rows: list[JsonValue] = []
    for (vault, client), (_admin_vault, administrator), (
        _credential_vault,
        credentials,
    ) in zip(clients, identity_administrators, application_credentials, strict=True):
        settings = V1S3VaultSettings.for_vault(vault)
        expected_accesses = tuple(access for _name, access in _VAULT_APPLICATION_IDENTITIES[vault])
        actual_accesses = tuple(item.reveal_for_client()[0] for item in credentials)
        if actual_accesses != expected_accesses:
            _fail("VAULT_APPLICATION_IDENTITY_INPUT_INVALID")
        if not verify_only:
            administrator.provision(credentials)
        if administrator.readback(credentials) != expected_accesses:
            _fail("VAULT_IDENTITY_ADMIN_READBACK_INVALID")
        _configure_vault(client, settings.bucket, credentials, verify_only=verify_only)
        rows.append(
            {
                "vault": vault.value,
                "bucket": settings.bucket,
                "endpoint": settings.endpoint_url,
                "object_lock": "Enabled",
                "versioning": "Enabled",
                "application_credentials": [
                    name for name, _access in _VAULT_APPLICATION_IDENTITIES[vault]
                ],
            }
        )
    return _atomic_receipt(
        receipt_path,
        {
            "schema_id": _VAULT_SCHEMA,
            "schema_version": _VERSION,
            "result": "COMPLETE",
            "retention_mode": "COMPLIANCE",
            "retention_days": _RETENTION_DAYS,
            "vaults": rows,
            "verified": True,
        },
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    register = subparsers.add_parser("register")
    register.add_argument("--migrations-root", type=Path, required=True)
    register.add_argument("--credential-directory", type=Path, required=True)
    register.add_argument("--receipt", type=Path, required=True)
    register.add_argument("--verify-only", action="store_true")
    vault = subparsers.add_parser("vault")
    vault.add_argument("--credential-directory", type=Path, required=True)
    vault.add_argument("--receipt", type=Path, required=True)
    vault.add_argument("--verify-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute only the selected bootstrap operation and print no secret/provider detail."""
    arguments = _parser().parse_args(argv)
    try:
        credentials = _safe_path(
            arguments.credential_directory,
            "BOOTSTRAP_CREDENTIAL_INVALID",
            directory=True,
        )
        if arguments.command == "register":
            password = SqlServerPassword.from_bytes(
                _credential(credentials / "sql-bootstrap-password")
            )
            application_passwords = {
                login: _credential(credentials / credential).decode("utf-8", errors="strict")
                for login, _role, credential in _APPLICATION_IDENTITIES
            }
            run_register_bootstrap(
                arguments.migrations_root,
                arguments.receipt,
                SqlRegisterBootstrap(password),
                application_passwords,
                verify_only=arguments.verify_only,
            )
        else:
            roots = tuple(
                (
                    vault,
                    _credential_pair(
                        credentials / f"vault-{vault.value.lower()}-root-access",
                        credentials / f"vault-{vault.value.lower()}-root-secret",
                    ),
                )
                for vault in (VaultName.PRIMARY, VaultName.RECOVERY)
            )
            clients = tuple((vault, _vault_client(vault, root)) for vault, root in roots)
            administrators = tuple(
                (
                    vault,
                    create_v1_vault_identity_administrator(
                        vault,
                        credentials / f"vault-{vault.value.lower()}-root-access",
                        credentials / f"vault-{vault.value.lower()}-root-secret",
                    ),
                )
                for vault, _root in roots
            )
            applications = tuple(
                (vault, _vault_application_credentials(vault, credentials))
                for vault in (VaultName.PRIMARY, VaultName.RECOVERY)
            )
            run_vault_bootstrap(
                arguments.receipt,
                clients,
                administrators,
                applications,
                verify_only=arguments.verify_only,
            )
    except (
        BotoCoreError,
        BootstrapError,
        ClientError,
        MssqlError,
        OSError,
        RuntimeError,
        UnicodeDecodeError,
        UnicodeEncodeError,
        ValueError,
    ):
        sys.stderr.write("HK_V1_BOOTSTRAP_NOT_READY\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
