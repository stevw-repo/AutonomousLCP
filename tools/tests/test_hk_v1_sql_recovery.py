"""No-effect tests for the concrete local SQL Server recovery-admin port."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from tools.hk_v1_recovery_proof import (
    LiveRecoveryExecutionError,
    LiveRecoveryStep,
    SealedCredentialReference,
)
from tools.hk_v1_sql_recovery import (
    SQLBackupPathBinding,
    SQLRecoveryCommandResult,
    SQLServerLiveRecoveryPort,
    SubprocessSQLRecoveryCommandRunner,
    build_sql_backup_path_manifest,
)


def _fingerprint(number: int) -> str:
    return f"sha256:{number:064x}"


def _opaque(number: int) -> str:
    return f"r_{number:032x}"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def _seal(body: dict[str, object]) -> bytes:
    document = {**body, "fingerprint": f"sha256:{sha256(_canonical(body)).hexdigest()}"}
    return _canonical(document) + b"\n"


def _manifest() -> bytes:
    return build_sql_backup_path_manifest(
        (
            SQLBackupPathBinding(
                _opaque(15),
                _fingerprint(15),
                "/var/opt/mssql/backup/asklegal-operational-2026-09-08.bak",
            ),
        )
    )


def _plan(manifest: bytes | None = None) -> dict[str, object]:
    manifest = _manifest() if manifest is None else manifest
    manifest_document = json.loads(manifest)
    manifest_fingerprint = f"sha256:{sha256(_canonical(manifest_document)).hexdigest()}"
    operation_id = _opaque(40)
    request_fingerprint = _fingerprint(101)
    target_token = sha256(f"{operation_id}|{request_fingerprint}".encode()).hexdigest()[:24]
    target_identity = f"r_{sha256(f'{target_token}|sql-database'.encode()).hexdigest()[:32]}"
    credential_reference_fingerprint = f"sha256:{
        sha256(
            _canonical(
                {
                    'credential_id': 'SQL_SERVER_RECOVERY_ADMIN',
                    'fingerprint': _fingerprint(700),
                    'sealed_path': '/run/credentials/asklegal/sql-server-recovery-admin',
                }
            )
        ).hexdigest()
    }"
    return {
        "fingerprint": _fingerprint(100),
        "operation_id": operation_id,
        "request_fingerprint": request_fingerprint,
        "sql": {
            "backup_path_manifest_fingerprint": manifest_fingerprint,
            "backup_reference": {
                "evidence_id": _opaque(15),
                "fingerprint": _fingerprint(15),
            },
            "credential_reference_fingerprint": credential_reference_fingerprint,
            "expected_families": [
                {
                    "content_fingerprint": _fingerprint(3),
                    "family": "commands",
                    "row_count": 3,
                },
                {
                    "content_fingerprint": _fingerprint(4),
                    "family": "events",
                    "row_count": 4,
                },
            ],
            "expected_migrations": [
                {"migration_id": "m_000001", "package_fingerprint": _fingerprint(1)},
                {"migration_id": "m_000002", "package_fingerprint": _fingerprint(2)},
            ],
            "external_ledger_digest_reference": {
                "evidence_id": _opaque(19),
                "fingerprint": _fingerprint(19),
            },
            "projection_rebuild_fingerprint": _fingerprint(18),
            "restored_ledger_verification_receipt": {
                "evidence_id": _opaque(21),
                "fingerprint": _fingerprint(21),
            },
            "source_ledger_verification_receipt": {
                "evidence_id": _opaque(20),
                "fingerprint": _fingerprint(20),
            },
            "target_database_identity": target_identity,
            "target_database_name": f"asklegal_recovery_sql_{target_token}",
        },
        "steps": [
            {
                "step": LiveRecoveryStep.SQL_RESTORE_READBACK.value,
                "target_identity": target_identity,
            }
        ],
    }


def _credentials() -> tuple[SealedCredentialReference, ...]:
    return (
        SealedCredentialReference(
            "SQL_SERVER_RECOVERY_ADMIN",
            "/run/credentials/asklegal/sql-server-recovery-admin",
            _fingerprint(700),
        ),
    )


def _verified_receipt(plan: dict[str, object]) -> bytes:
    sql = plan["sql"]
    assert type(sql) is dict
    typed_sql = cast("dict[str, object]", sql)
    body: dict[str, object] = {
        "backup_path_manifest_fingerprint": typed_sql["backup_path_manifest_fingerprint"],
        "backup_reference": typed_sql["backup_reference"],
        "database_state": "ONLINE",
        "dbcc_checkdb": "CLEAN",
        "external_ledger_digest_reference": typed_sql["external_ledger_digest_reference"],
        "ledger_verification": "VERIFIED",
        "migration_prefix": typed_sql["expected_migrations"],
        "plan_fingerprint": plan["fingerprint"],
        "projection_rebuild": "VERIFIED",
        "projection_rebuild_fingerprint": typed_sql["projection_rebuild_fingerprint"],
        "register_families": typed_sql["expected_families"],
        "request_fingerprint": plan["request_fingerprint"],
        "restore_verification_fingerprint": _fingerprint(500),
        "restored_ledger_verification_receipt": typed_sql["restored_ledger_verification_receipt"],
        "schema": "asklegal.hk-v1-sql-recovery-readback/v1",
        "source_database_identity": _opaque(16),
        "source_ledger_verification_receipt": typed_sql["source_ledger_verification_receipt"],
        "target_database_identity": typed_sql["target_database_identity"],
        "target_database_name": typed_sql["target_database_name"],
        "sql_visible_backup_path": ("/var/opt/mssql/backup/asklegal-operational-2026-09-08.bak"),
    }
    return _seal(body)


class _Runner:
    def __init__(self, result: SQLRecoveryCommandResult) -> None:
        self.result = result
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...]) -> SQLRecoveryCommandResult:
        self.calls.append(argv)
        return self.result


class _CredentialVerifier:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[SealedCredentialReference] = []

    def verify(self, reference: SealedCredentialReference) -> bool:
        self.calls.append(reference)
        return self.allowed


def _port(runner: _Runner, manifest: bytes | None = None) -> SQLServerLiveRecoveryPort:
    return SQLServerLiveRecoveryPort(
        runner,
        _manifest() if manifest is None else manifest,
        helper_path=Path("/usr/local/libexec/asklegal-sql-recovery-admin"),
        credential_verifier=_CredentialVerifier(),
    )


def test_execute_uses_one_fixed_argv_and_returns_exact_verified_receipt() -> None:
    """The adapter supplies only references and exact public facts to its helper."""
    plan = _plan()
    runner = _Runner(SQLRecoveryCommandResult(0, _verified_receipt(plan), b""))

    receipt = _port(runner).execute(LiveRecoveryStep.SQL_RESTORE_READBACK, plan, _credentials())

    assert receipt.step is LiveRecoveryStep.SQL_RESTORE_READBACK
    assert receipt.effect_fingerprint == _fingerprint(500)
    assert receipt.readback_fingerprint == _fingerprint(500)
    assert len(runner.calls) == 1
    command = runner.calls[0]
    assert command[0] == "/usr/local/libexec/asklegal-sql-recovery-admin"
    assert command[1] == "restore-and-readback"
    assert "/run/credentials/asklegal/sql-server-recovery-admin" in command
    assert "/var/opt/mssql/backup/asklegal-operational-2026-09-08.bak" in command
    assert all("secret" not in item.casefold() for item in command)


def test_reconcile_returns_none_only_for_exact_not_found_response() -> None:
    """Read-only reconciliation has an explicit target-absent result."""
    plan = _plan()
    sql = plan["sql"]
    assert type(sql) is dict
    absent = _seal(
        {
            "plan_fingerprint": plan["fingerprint"],
            "schema": "asklegal.hk-v1-sql-recovery-not-found/v1",
            "target_database_identity": sql["target_database_identity"],
            "target_database_name": sql["target_database_name"],
        }
    )
    runner = _Runner(SQLRecoveryCommandResult(3, absent, b""))

    assert (
        _port(runner).reconcile(LiveRecoveryStep.SQL_RESTORE_READBACK, plan, _credentials()) is None
    )
    assert runner.calls[0][1] == "reconcile-readback"


@pytest.mark.parametrize("change", ["path", "reference", "manifest_fingerprint", "credential"])
def test_every_mapping_or_credential_drift_fails_before_command(change: str) -> None:
    """Authority cannot be replayed against another backup or credential reference."""
    manifest = _manifest()
    plan = _plan(manifest)
    credentials = _credentials()
    if change == "path":
        document = json.loads(manifest)
        document["bindings"][0]["sql_visible_path"] = "/var/opt/mssql/backup/other.bak"
        manifest = _canonical(document) + b"\n"
    elif change == "reference":
        document = json.loads(manifest)
        document["bindings"][0]["backup_reference"]["evidence_id"] = _opaque(99)
        manifest = _canonical(document) + b"\n"
    elif change == "manifest_fingerprint":
        sql = plan["sql"]
        assert type(sql) is dict
        sql["backup_path_manifest_fingerprint"] = _fingerprint(999)
    else:
        credentials = (
            SealedCredentialReference(
                "SQL_SERVER_RECOVERY_ADMIN",
                "/run/credentials/asklegal/different-admin",
                _fingerprint(999),
            ),
        )
    runner = _Runner(SQLRecoveryCommandResult(0, _verified_receipt(plan), b""))

    with pytest.raises(LiveRecoveryExecutionError):
        _port(runner, manifest).execute(LiveRecoveryStep.SQL_RESTORE_READBACK, plan, credentials)

    assert runner.calls == []


def test_current_credential_file_drift_fails_before_command() -> None:
    """The manifest binding is insufficient if its referenced runtime bytes changed."""
    plan = _plan()
    runner = _Runner(SQLRecoveryCommandResult(0, _verified_receipt(plan), b""))
    verifier = _CredentialVerifier(allowed=False)
    port = SQLServerLiveRecoveryPort(
        runner,
        _manifest(),
        credential_verifier=verifier,
    )

    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_SQL_RECOVERY_CREDENTIAL_DRIFT"):
        port.execute(LiveRecoveryStep.SQL_RESTORE_READBACK, plan, _credentials())

    assert len(verifier.calls) == 1
    assert runner.calls == []


def test_validly_resealed_backup_path_rebinding_still_needs_fresh_authority() -> None:
    """A new self-consistent mapping cannot reuse a plan bound to the prior mapping."""
    plan = _plan()
    rebound = build_sql_backup_path_manifest(
        (
            SQLBackupPathBinding(
                _opaque(15),
                _fingerprint(15),
                "/var/opt/mssql/backup/rebound.bak",
            ),
        )
    )
    runner = _Runner(SQLRecoveryCommandResult(0, _verified_receipt(plan), b""))

    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_SQL_BACKUP_PATH_MANIFEST_DRIFT"):
        _port(runner, rebound).execute(LiveRecoveryStep.SQL_RESTORE_READBACK, plan, _credentials())

    assert runner.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_state", "RECOVERING"),
        ("dbcc_checkdb", "FAILED"),
        ("ledger_verification", "UNRUN"),
        ("projection_rebuild", "UNRUN"),
        ("register_families", []),
        ("target_database_identity", _opaque(999)),
    ],
)
def test_incomplete_or_drifted_sql_readback_is_never_a_receipt(field: str, value: object) -> None:
    """A zero exit code cannot override semantic verification failure."""
    plan = _plan()
    document = json.loads(_verified_receipt(plan))
    document[field] = value
    unsigned = dict(document)
    unsigned.pop("fingerprint")
    document["fingerprint"] = f"sha256:{sha256(_canonical(unsigned)).hexdigest()}"
    runner = _Runner(SQLRecoveryCommandResult(0, _canonical(document) + b"\n", b""))

    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_SQL_RECOVERY_READBACK_INVALID"):
        _port(runner).execute(LiveRecoveryStep.SQL_RESTORE_READBACK, plan, _credentials())


def test_wrong_step_and_command_failure_are_sanitized() -> None:
    """The SQL port owns one step and never includes helper stderr in errors."""
    plan = _plan()
    runner = _Runner(SQLRecoveryCommandResult(9, b"", b"database secret detail"))
    port = _port(runner)

    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_SQL_RECOVERY_STEP_INVALID"):
        port.execute(LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD, plan, _credentials())
    assert runner.calls == []

    with pytest.raises(
        LiveRecoveryExecutionError, match="LIVE_SQL_RECOVERY_COMMAND_FAILED"
    ) as error:
        port.execute(LiveRecoveryStep.SQL_RESTORE_READBACK, plan, _credentials())
    assert "secret" not in str(error.value)


def test_concrete_runner_rejects_every_non_protocol_argv_before_subprocess() -> None:
    """The concrete command boundary is not a general process-execution capability."""
    runner = SubprocessSQLRecoveryCommandRunner()

    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_SQL_RECOVERY_COMMAND_INVALID"):
        runner.run(("/bin/sh", "-c", "true"))
