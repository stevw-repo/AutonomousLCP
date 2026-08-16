"""Synthetic conformance proof against the real local SQL Server engine."""

import os
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_management_register.driver import MssqlConnectionFactory
from asklegal_management_register.migration import apply_packages
from asklegal_management_register.store import (
    CommandFingerprintMismatch,
    ManagementRegisterStore,
)

_DATABASE = "AskLegalManagementRegisterSpike"
_MIGRATION = Path(__file__).parents[1] / "migrations" / "000001_management_register_spike"


def _factory(database: str, *, autocommit: bool = False) -> MssqlConnectionFactory:
    base = os.environ.get("ASKLEGAL_SQL_CONNECTION_BASE")
    if base is None:
        pytest.skip("ASKLEGAL_SQL_CONNECTION_BASE is not set")
    return MssqlConnectionFactory(f"{base};Database={database};", autocommit=autocommit)


def _execute(
    factory: MssqlConnectionFactory, sql: str, *, fetch: bool = False
) -> list[tuple[object, ...]]:
    connection = factory()
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchall() if fetch else []
        connection.commit()
        return rows
    finally:
        cursor.close()
        connection.close()


@pytest.mark.sql_server
def test_management_register_sql_server_proof() -> None:
    """Prove migration, command, concurrency, privilege, atomicity, and ledger behavior."""
    master = _factory("master", autocommit=True)
    _execute(
        master,
        f"""
        IF DB_ID('{_DATABASE}') IS NOT NULL
        BEGIN
            ALTER DATABASE [{_DATABASE}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
            DROP DATABASE [{_DATABASE}];
        END;
        CREATE DATABASE [{_DATABASE}];
        """,
    )
    _execute(
        master,
        f"ALTER DATABASE [{_DATABASE}] SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;",
    )
    _execute(
        master,
        f"ALTER DATABASE [{_DATABASE}] SET ALLOW_SNAPSHOT_ISOLATION ON;",
    )
    database = _factory(_DATABASE)
    apply_packages(database, (_MIGRATION,), runner_build="management-register-spike-1")
    apply_packages(database, (_MIGRATION,), runner_build="management-register-spike-1")

    manifest = sha256(b"synthetic-manifest").digest()
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT review.approval_current
                (approval_id, manifest_fingerprint, state_code, updated_at)
            VALUES
                ('approval-idempotent', ?, 'VALID', SYSUTCDATETIME()),
                ('approval-concurrent', ?, 'VALID', SYSUTCDATETIME()),
                ('approval-ambiguous', ?, 'VALID', SYSUTCDATETIME()),
                ('approval-role', ?, 'VALID', SYSUTCDATETIME());
            """,
            (manifest, manifest, manifest, manifest),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    store = ManagementRegisterStore(database)
    raw = b'{"approval_id":"approval-idempotent"}'
    fingerprint = sha256(raw).digest()
    original = store.consume_approval(
        command_id="command-idempotent",
        command_fingerprint=fingerprint,
        approval_id="approval-idempotent",
        manifest_fingerprint=manifest,
        canonical_command=raw,
    )
    replay = store.consume_approval(
        command_id="command-idempotent",
        command_fingerprint=fingerprint,
        approval_id="approval-idempotent",
        manifest_fingerprint=manifest,
        canonical_command=raw,
    )
    assert original.replayed is False
    assert replay.replayed is True
    assert original.result_bytes == replay.result_bytes == b'{"status":"consumed"}'

    with pytest.raises(CommandFingerprintMismatch):
        store.resolve_command("command-idempotent", sha256(b"different").digest())

    def race(command_id: str) -> str:
        race_raw = f'{{"command_id":"{command_id}"}}'.encode()
        try:
            store.consume_approval(
                command_id=command_id,
                command_fingerprint=sha256(race_raw).digest(),
                approval_id="approval-concurrent",
                manifest_fingerprint=manifest,
                canonical_command=race_raw,
            )
        except Exception as error:
            return str(error)
        return "winner"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(race, ("command-race-a", "command-race-b")))
    assert outcomes.count("winner") == 1
    assert sum("ASKLEGAL_APPROVAL_NOT_VALID" in outcome for outcome in outcomes) == 1

    ambiguous_raw = b'{"approval_id":"approval-ambiguous"}'
    ambiguous = store.consume_approval(
        command_id="command-ambiguous",
        command_fingerprint=sha256(ambiguous_raw).digest(),
        approval_id="approval-ambiguous",
        manifest_fingerprint=manifest,
        canonical_command=ambiguous_raw,
        simulate_lost_ack=True,
    )
    assert ambiguous.replayed is True

    connection = database()
    cursor = connection.cursor()
    role_raw = b'{"approval_id":"approval-role"}'
    try:
        cursor.execute("EXECUTE AS USER='asklegal_review_app';")
        cursor.execute(
            "EXEC review.consume_approval ?, ?, ?, ?, ?",
            (
                "command-role-review",
                sha256(role_raw).digest(),
                "approval-role",
                manifest,
                role_raw,
            ),
        )
        assert cursor.fetchone() is not None
        cursor.execute("REVERT;")
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    connection = database()
    cursor = connection.cursor()
    activation_raw = b'{"manifest":"synthetic-manifest"}'
    try:
        cursor.execute("EXECUTE AS USER='asklegal_promotion_app';")
        cursor.execute(
            "EXEC promotion.activate_serving_state ?, ?, ?, ?, ?",
            (
                "command-activate",
                sha256(activation_raw).digest(),
                "approval-idempotent",
                manifest,
                activation_raw,
            ),
        )
        assert cursor.fetchone() is not None
        cursor.execute("REVERT;")
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    atomic_counts = _execute(
        database,
        """
        SELECT
          (SELECT COUNT(*) FROM register.command_fact WHERE command_id='command-ambiguous'),
          (SELECT COUNT(*) FROM register.inbox_fact WHERE command_id='command-ambiguous'),
          (SELECT COUNT(*) FROM register.lifecycle_fact WHERE command_id='command-ambiguous'),
          (SELECT COUNT(*) FROM register.outbox_fact WHERE command_id='command-ambiguous');
        """,
        fetch=True,
    )
    assert atomic_counts == [(1, 1, 1, 1)]

    permission_error = ""
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute("EXECUTE AS USER='asklegal_review_app';")
        cursor.execute(
            "INSERT review.approval_current VALUES "
            "('forbidden', 0x00, 'VALID', NULL, SYSUTCDATETIME());"
        )
    except Exception as error:
        permission_error = str(error)
        connection.rollback()
    finally:
        cursor.close()
        connection.close()
    assert "permission" in permission_error.lower()

    connection = _factory(_DATABASE, autocommit=True)()
    cursor = connection.cursor()
    try:
        cursor.execute("EXEC sys.sp_generate_database_ledger_digest;")
        digest_row = cursor.fetchone()
        assert digest_row is not None and isinstance(digest_row[0], str)
        cursor.execute(
            "DECLARE @digests nvarchar(max) = CONVERT(nvarchar(max), ?); "
            "EXEC sys.sp_verify_database_ledger @digests;",
            (f"[{digest_row[0]}]",),
        )
        verification = cursor.fetchone()
        assert verification is not None
    finally:
        cursor.close()
        connection.close()

    migration_count = _execute(
        database,
        "SELECT COUNT(*) FROM migration.applied_fact WHERE migration_id='000001';",
        fetch=True,
    )
    assert migration_count == [(1,)]
