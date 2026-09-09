"""No-network proofs for the SQL/vault bootstrap owner boundaries."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from asklegal_contracts.json_types import checked_json_value
from asklegal_control_plane import bootstrap
from asklegal_control_plane.bootstrap import (
    BootstrapError,
    VersityIdentityAdministration,
    create_v1_vault_identity_administrator,
    run_register_bootstrap,
    run_vault_bootstrap,
)
from asklegal_evidence_vault import VaultName
from asklegal_evidence_vault.s3 import S3AccessCredential
from asklegal_management_register.migration import MigrationPackage

_MIGRATIONS = Path(__file__).parents[3] / "packages" / "management-register-adapter" / "migrations"


def _object(value: object) -> dict[str, object]:
    parsed = checked_json_value(value)
    assert isinstance(parsed, dict)
    return dict(parsed)


def _empty_prefix() -> tuple[tuple[str, str], ...]:
    return ()


@dataclass
class _Register:
    prefix: tuple[tuple[str, str], ...] = field(default_factory=_empty_prefix)
    apply_calls: int = 0
    identity_calls: int = 0
    identities: tuple[str, ...] = ()

    def apply(self, packages: tuple[MigrationPackage, ...]) -> None:
        """Record the exact requested prefix without opening SQL."""
        self.apply_calls += 1
        self.prefix = tuple(
            (package.migration_id, "sha256:" + package.package_fingerprint.hex())
            for package in packages
        )

    def read_prefix(self) -> tuple[tuple[str, str], ...]:
        """Return the retained fake prefix."""
        return self.prefix

    def provision_application_identities(self, passwords: dict[str, str]) -> None:
        """Retain no password; record only the exact closed identity inventory."""
        self.identity_calls += 1
        self.identities = tuple(passwords)

    def read_application_identities(self, passwords: dict[str, str]) -> tuple[str, ...]:
        """Model successful login and role readback for the supplied credentials."""
        assert tuple(passwords) == self.identities
        return self.identities


def _sql_passwords() -> dict[str, str]:
    return {
        "asklegal_acquisition_app": "acquisition-secret",
        "asklegal_control_app": "control-secret",
        "asklegal_legal_processing_app": "processing-secret",
        "asklegal_promotion_app": "promotion-secret",
        "asklegal_review_app": "review-secret",
    }


def _empty_calls() -> list[str]:
    return []


@dataclass
class _Vault:
    present: bool = False
    versioning: bool = False
    lock_mode: str = "Disabled"
    lock_days: int = 0
    policy: str = ""
    calls: list[str] = field(default_factory=_empty_calls)

    def head_bucket(self, **_kwargs: object) -> Mapping[str, object]:
        """Report fake presence without provider access."""
        self.calls.append("head")
        if not self.present:
            raise _MissingBucket({"Error": {"Code": "NoSuchBucket"}}, "HeadBucket")
        return {}

    def create_bucket(self, **_kwargs: object) -> Mapping[str, object]:
        """Create only the fake in-memory bucket."""
        self.calls.append("create")
        self.present = True
        return {}

    def put_bucket_versioning(self, **_kwargs: object) -> Mapping[str, object]:
        """Set fake versioning."""
        self.calls.append("version")
        self.versioning = True
        return {}

    def put_object_lock_configuration(self, **kwargs: object) -> Mapping[str, object]:
        """Set fake Object Lock."""
        self.calls.append("lock")
        configuration = _object(kwargs.get("ObjectLockConfiguration"))
        rule = _object(configuration.get("Rule"))
        retention = _object(rule.get("DefaultRetention"))
        mode = retention.get("Mode")
        days = retention.get("Days")
        assert type(mode) is str
        assert type(days) is int
        self.lock_mode = mode
        self.lock_days = days
        return {}

    def get_bucket_versioning(self, **_kwargs: object) -> Mapping[str, object]:
        """Read fake versioning."""
        self.calls.append("get-version")
        return {"Status": "Enabled" if self.versioning else "Suspended"}

    def get_object_lock_configuration(self, **_kwargs: object) -> Mapping[str, object]:
        """Read fake Object Lock."""
        self.calls.append("get-lock")
        return {
            "ObjectLockConfiguration": {
                "ObjectLockEnabled": "Enabled" if self.lock_mode != "Disabled" else "Disabled",
                "Rule": {
                    "DefaultRetention": {
                        "Mode": self.lock_mode,
                        "Days": self.lock_days,
                    }
                },
            }
        }

    def put_bucket_policy(self, **kwargs: object) -> Mapping[str, object]:
        """Retain the exact access-key policy without a provider call."""
        self.calls.append("policy")
        policy = kwargs.get("Policy")
        assert type(policy) is str
        self.policy = policy
        return {}

    def get_bucket_policy(self, **_kwargs: object) -> Mapping[str, object]:
        """Return the exact fake bucket policy."""
        self.calls.append("get-policy")
        return {"Policy": self.policy}


@dataclass
class _VaultAdmin:
    identities: tuple[tuple[str, str], ...] = ()
    calls: int = 0

    def provision(self, credentials: tuple[S3AccessCredential, ...]) -> None:
        """Retain the exact fake identities without provider access."""
        self.calls += 1
        self.identities = tuple(item.reveal_for_client() for item in credentials)

    def readback(self, credentials: tuple[S3AccessCredential, ...]) -> tuple[str, ...]:
        """Verify fake secret equality and return only access identities."""
        if tuple(item.reveal_for_client() for item in credentials) != self.identities:
            return ()
        return tuple(access for access, _secret in self.identities)


class _MissingBucket(Exception):
    response: object

    def __init__(self, response: object, _operation: str) -> None:
        self.response = response


def _vault_credential(access: str) -> S3AccessCredential:
    return S3AccessCredential.from_bytes(
        ('{"access_key_id":"' + access + '","secret_access_key":"synthetic-secret"}').encode()
    )


def _versity_users(*rows: tuple[str, str, str]) -> bytes:
    accounts = "".join(
        "<Account>"
        f"<Access>{access}</Access><Secret>{secret}</Secret><Role>{role}</Role>"
        "<UserID>0</UserID><GroupID>0</GroupID><ProjectID>0</ProjectID>"
        "</Account>"
        for access, secret, role in rows
    )
    return f"<ListUserAccountsResult>{accounts}</ListUserAccountsResult>".encode()


def _vault_inputs() -> tuple[
    tuple[tuple[VaultName, _VaultAdmin], ...],
    tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
]:
    admins = ((VaultName.PRIMARY, _VaultAdmin()), (VaultName.RECOVERY, _VaultAdmin()))
    credentials = (
        (
            VaultName.PRIMARY,
            tuple(
                _vault_credential(access)
                for access in (
                    "asklegal-primary-acquisition",
                    "asklegal-primary-control",
                    "asklegal-primary-processing",
                    "asklegal-primary-promotion",
                    "asklegal-primary-review",
                )
            ),
        ),
        (
            VaultName.RECOVERY,
            tuple(
                _vault_credential(access)
                for access in (
                    "asklegal-recovery-acquisition",
                    "asklegal-recovery-promotion",
                )
            ),
        ),
    )
    return admins, credentials


def test_register_bootstrap_applies_once_then_verifies_exact_prefix(tmp_path: Path) -> None:
    """The SQL owner retains exact migration readback and verify-only cannot apply."""
    port = _Register()
    receipt = tmp_path / "state" / "register.json"
    passwords = _sql_passwords()
    first = run_register_bootstrap(_MIGRATIONS, receipt, port, passwords, verify_only=False)
    replay = run_register_bootstrap(_MIGRATIONS, receipt, port, passwords, verify_only=True)
    assert first == replay == receipt.read_bytes()
    assert port.apply_calls == 1
    assert port.identity_calls == 1
    assert port.identities == tuple(passwords)
    assert all(secret.encode() not in first for secret in passwords.values())
    assert b'"result":"COMPLETE"' in first


def test_register_verify_only_rejects_missing_or_drifted_prefix(tmp_path: Path) -> None:
    """An empty or truncated database cannot receive a success receipt."""
    port = _Register()
    with pytest.raises(BootstrapError, match="REGISTER_MIGRATION_READBACK_INVALID"):
        run_register_bootstrap(
            _MIGRATIONS,
            tmp_path / "state" / "register.json",
            port,
            _sql_passwords(),
            verify_only=True,
        )


def test_register_rejects_invalid_application_password_before_any_effect(tmp_path: Path) -> None:
    """Every application password is validated before database creation or login mutation."""
    port = _Register()
    passwords = _sql_passwords()
    passwords["asklegal_control_app"] = "newline-is-not-valid\n"
    with pytest.raises(BootstrapError, match="REGISTER_APPLICATION_IDENTITY_INPUT_INVALID"):
        run_register_bootstrap(
            _MIGRATIONS,
            tmp_path / "state" / "register.json",
            port,
            passwords,
            verify_only=False,
        )
    assert port.apply_calls == 0
    assert port.identity_calls == 0
    assert not (tmp_path / "state").exists()


def test_vault_bootstrap_creates_configures_reads_back_and_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both fake vaults prove create, versioning, Object Lock, and exact readback."""
    monkeypatch.setattr(bootstrap, "ClientError", _MissingBucket)
    primary = _Vault()
    recovery = _Vault()
    receipt = tmp_path / "state" / "vault.json"
    clients = ((VaultName.PRIMARY, primary), (VaultName.RECOVERY, recovery))
    admins, credentials = _vault_inputs()
    first = run_vault_bootstrap(receipt, clients, admins, credentials, verify_only=False)
    replay = run_vault_bootstrap(receipt, clients, admins, credentials, verify_only=True)
    assert first == replay == receipt.read_bytes()
    expected_calls = [
        "head",
        "create",
        "version",
        "lock",
        "policy",
        "get-version",
        "get-lock",
        "get-policy",
        "get-version",
        "get-lock",
        "get-policy",
    ]
    assert primary.calls == expected_calls
    assert recovery.calls == expected_calls
    assert all(admin.calls == 1 for _vault, admin in admins)
    assert b"synthetic-secret" not in first
    primary_policy = json.loads(primary.policy)
    assert primary_policy["Statement"][0]["Principal"] == [
        "asklegal-primary-acquisition",
        "asklegal-primary-control",
        "asklegal-primary-processing",
        "asklegal-primary-promotion",
        "asklegal-primary-review",
    ]


def test_vault_readback_rejects_retention_or_policy_drift(tmp_path: Path) -> None:
    """Enabled Object Lock alone cannot hide the wrong mode, days, or access policy."""
    primary = _Vault(
        present=True,
        versioning=True,
        lock_mode="GOVERNANCE",
        lock_days=2555,
        policy='{"Statement":[],"Version":"2012-10-17"}',
    )
    recovery = _Vault(
        present=True,
        versioning=True,
        lock_mode="COMPLIANCE",
        lock_days=2555,
        policy='{"Statement":[],"Version":"2012-10-17"}',
    )
    admins, credentials = _vault_inputs()
    for (_vault, admin), (_credential_vault, values) in zip(admins, credentials, strict=True):
        admin.provision(values)
    with pytest.raises(BootstrapError, match="VAULT_BOOTSTRAP_READBACK_INVALID"):
        run_vault_bootstrap(
            tmp_path / "state" / "vault.json",
            ((VaultName.PRIMARY, primary), (VaultName.RECOVERY, recovery)),
            admins,
            credentials,
            verify_only=True,
        )


def test_vault_verify_only_cannot_create_or_claim_unconfigured_bucket(tmp_path: Path) -> None:
    """Readback failure remains inert in verify-only mode."""
    primary = _Vault()
    recovery = _Vault()
    admins, credentials = _vault_inputs()
    with pytest.raises(BootstrapError, match="VAULT_IDENTITY_ADMIN_READBACK_INVALID"):
        run_vault_bootstrap(
            tmp_path / "state" / "vault.json",
            ((VaultName.PRIMARY, primary), (VaultName.RECOVERY, recovery)),
            admins,
            credentials,
            verify_only=True,
        )
    assert "create" not in primary.calls
    assert "create" not in recovery.calls


def test_vault_admin_uses_exact_documented_create_and_update_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reusable admin boundary emits only the documented fixed PATCH shapes."""
    root = _vault_credential("root-access")
    administrator = VersityIdentityAdministration(
        bootstrap.V1S3VaultSettings.for_vault(VaultName.PRIMARY), root
    )
    calls: list[tuple[str, bytes, int]] = []
    existing = _versity_users(("existing-access", "old-secret", "user"))

    def request(_self: VersityIdentityAdministration, path: str, body: bytes, status: int) -> bytes:
        calls.append((path, body, status))
        return existing if path == "/list-users" else b""

    monkeypatch.setattr(VersityIdentityAdministration, "_request", request)
    credentials = (
        S3AccessCredential.from_bytes(
            b'{"access_key_id":"existing-access","secret_access_key":"new-secret"}'
        ),
        S3AccessCredential.from_bytes(
            b'{"access_key_id":"new-access","secret_access_key":"new-user-secret"}'
        ),
    )
    administrator.provision(credentials)
    assert calls[0] == ("/list-users", b"", 200)
    assert calls[1] == (
        "/update-user?access=existing-access",
        (
            b'<?xml version="1.0" encoding="UTF-8"?><MutableProps>'
            b"<Secret>new-secret</Secret></MutableProps>"
        ),
        200,
    )
    assert calls[2] == (
        "/create-user",
        (
            b'<?xml version="1.0" encoding="UTF-8"?><Account>'
            b"<Access>new-access</Access><Secret>new-user-secret</Secret>"
            b"<Role>user</Role></Account>"
        ),
        201,
    )


def test_vault_admin_rejects_obsolete_or_ambiguous_users_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap never infers user deletion or accepts duplicate XML fields."""
    administrator = VersityIdentityAdministration(
        bootstrap.V1S3VaultSettings.for_vault(VaultName.PRIMARY),
        _vault_credential("root-access"),
    )
    responses = iter(
        (
            _versity_users(("obsolete", "secret", "user")),
            (
                b"<ListUserAccountsResult><Account><Access>wanted</Access>"
                b"<Access>shadow</Access><Secret>secret</Secret><Role>user</Role>"
                b"<UserID>0</UserID><GroupID>0</GroupID><ProjectID>0</ProjectID>"
                b"</Account></ListUserAccountsResult>"
            ),
        )
    )
    calls: list[str] = []

    def request(
        _self: VersityIdentityAdministration, path: str, _body: bytes, _status: int
    ) -> bytes:
        calls.append(path)
        return next(responses)

    monkeypatch.setattr(VersityIdentityAdministration, "_request", request)
    wanted = (_vault_credential("wanted"),)
    with pytest.raises(BootstrapError, match="VAULT_IDENTITY_ADMIN_READBACK_INVALID"):
        administrator.provision(wanted)
    assert calls == ["/list-users"]
    with pytest.raises(BootstrapError, match="VAULT_IDENTITY_ADMIN_READBACK_INVALID"):
        administrator.readback(wanted)
    assert calls == ["/list-users", "/list-users"]


def test_public_vault_admin_factory_reads_only_exact_root_files(tmp_path: Path) -> None:
    """Rotation/bootstrap callers can share the closed root-file parser without ambient state."""
    access = tmp_path / "root-access"
    secret = tmp_path / "root-secret"
    access.write_bytes(b"root-access")
    secret.write_bytes(b"root-secret")
    administrator = create_v1_vault_identity_administrator(VaultName.RECOVERY, access, secret)
    assert administrator.settings.vault_name is VaultName.RECOVERY
    assert repr(administrator.root_credential) == "S3AccessCredential(<redacted>)"
