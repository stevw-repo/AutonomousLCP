"""Serving State SQL-adapter and disposable-engine proofs."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

import mssql_python
import pytest
from asklegal_management_register import (
    RegisterProjectionError,
    ServingStateCandidate,
    ServingStateStore,
)
from asklegal_management_register.driver import MssqlConnectionFactory
from asklegal_management_register.migration import apply_packages, load_package

if TYPE_CHECKING:
    from asklegal_management_register.dbapi import Cursor, SqlParameter, SqlParameters

_PACKAGE = Path(__file__).parents[1] / "migrations" / "000011_serving_state_transition"


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]], error: Exception | None = None) -> None:
        self.rows = rows
        self.error = error
        self.operations: list[tuple[str, tuple[SqlParameter, ...]]] = []

    def execute(self, operation: str, params: SqlParameters = ()) -> Cursor:
        self.operations.append((operation, tuple(params)))
        if self.error is not None:
            raise self.error
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows.pop(0) if self.rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        rows, self.rows = self.rows, []
        return rows

    def close(self) -> None:
        pass


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_value = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> Cursor:
        return self.cursor_value

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        pass


def _candidate() -> ServingStateCandidate:
    return ServingStateCandidate(
        "srv_" + "b" * 48,
        "sha256:" + "b" * 64,
        "srv_" + "a" * 48,
        "asklegal-dev-hk-20260827-b",
        "sha256:" + "c" * 64,
        "sha256:" + "d" * 64,
        "emp_" + "e" * 48,
        "sha256:" + "e" * 64,
        "apr_" + "f" * 48,
        "exe_" + "1" * 48,
    )


def _activation_receipt(candidate: ServingStateCandidate) -> str:
    raw = (
        f"{candidate.predecessor_state_id}|{candidate.state_id}|{candidate.state_fingerprint}|"
        f"{candidate.target_name}|{candidate.desired_inventory_fingerprint}|"
        f"{candidate.coverage_fingerprint}|{candidate.embedding_profile_id}|"
        f"{candidate.embedding_profile_fingerprint}|{candidate.approval_id}|"
        f"{candidate.execution_lineage_id}"
    )
    return "ssr_" + sha256(raw.encode()).hexdigest()


def _role_ownership_candidate() -> ServingStateCandidate:
    """Candidate reserved solely for the role ownership-chain proof."""
    return replace(
        _candidate(),
        state_id="srv_" + "4" * 48,
        state_fingerprint="sha256:" + "4" * 64,
        target_name="asklegal-dev-hk-20260827-role-owner",
        desired_inventory_fingerprint="sha256:" + "4" * 64,
        coverage_fingerprint="sha256:" + "4" * 64,
        embedding_profile_id="emp_" + "4" * 48,
        embedding_profile_fingerprint="sha256:" + "4" * 64,
        approval_id="apr_" + "4" * 48,
        execution_lineage_id="exe_" + "4" * 48,
    )


def test_stateful_sql_scenarios_reserve_distinct_candidate_identities() -> None:
    """One rolled-back role proof must never poison later activation replay history."""
    assert _role_ownership_candidate() != _candidate()


def test_migration_is_one_fresh_prefix_batch_with_promotion_only_authority() -> None:
    """The reviewed package has finite-lock procedures and no direct DML path."""
    package = load_package(_PACKAGE)
    assert package.migration_id == "000011"
    assert tuple(batch.path for batch in package.batches) == (
        "001_serving_state_tables.sql",
        "002_read_serving_state.sql",
        "003_activate_serving_state.sql",
        "004_rollback_serving_state.sql",
        "005_serving_state_permissions.sql",
    )
    tables, read, activate, rollback, permissions = (
        (package.directory / batch.path).read_text(encoding="utf-8") for batch in package.batches
    )
    assert "CREATE OR ALTER PROCEDURE" not in tables
    assert read.startswith("CREATE OR ALTER PROCEDURE promotion.read_serving_state_v1")
    assert activate.startswith("CREATE OR ALTER PROCEDURE promotion.activate_serving_state_v1")
    assert rollback.startswith("CREATE OR ALTER PROCEDURE promotion.rollback_serving_state_v1")
    assert "SET LOCK_TIMEOUT 5000" in read + activate + rollback
    assert "IF ERROR_NUMBER() = 1222 THROW 52100, 'ASKLEGAL_SERVING_STATE_LOCK_TIMEOUT', 1" in read
    assert "target_name = @target_name" in activate
    assert "last_receipt_id = @receipt_id" in activate
    assert "@activation_receipt_id varchar(80)" in rollback
    assert "@activation_receipt <> @activation_receipt_id" in rollback
    assert (
        "GRANT EXECUTE ON OBJECT::promotion.activate_serving_state_v1 "
        "TO asklegal_promotion_role" in permissions
    )
    assert (
        "DENY SELECT, INSERT, UPDATE, DELETE ON "
        "OBJECT::promotion.serving_state_v1_current" in permissions
    )
    for role in (
        "asklegal_control_role",
        "asklegal_review_role",
        "asklegal_acquisition_role",
        "asklegal_legal_processing_role",
    ):
        for procedure in (
            "read_serving_state_v1",
            "activate_serving_state_v1",
            "rollback_serving_state_v1",
        ):
            assert f"DENY EXECUTE ON OBJECT::promotion.{procedure} TO {role}" in permissions
        assert (
            "DENY SELECT, INSERT, UPDATE, DELETE ON "
            f"OBJECT::promotion.serving_state_v1_current TO {role}" in permissions
        )


def test_adapter_requires_complete_receipt_and_sanitizes_sql_errors() -> None:
    """One incomplete or driver-derived row never becomes a success receipt."""
    candidate = _candidate()
    activation_receipt = _activation_receipt(candidate)
    cursor = _Cursor(
        [
            (
                activation_receipt,
                "ACTIVATED",
                candidate.predecessor_state_id,
                candidate.state_id,
                candidate.state_fingerprint,
                0,
            )
        ]
    )
    connection = _Connection(cursor)
    receipt = ServingStateStore(lambda: connection).activate(
        candidate.predecessor_state_id, candidate
    )
    assert receipt.state_id == candidate.state_id
    assert connection.committed is True
    statement, parameters = cursor.operations[0]
    assert statement.startswith("EXEC promotion.activate_serving_state_v1")
    assert parameters[0] == candidate.predecessor_state_id
    assert parameters[-1] == candidate.execution_lineage_id

    broken = _Connection(_Cursor([("ssr_" + "1" * 64,)]))
    with pytest.raises(RegisterProjectionError, match="ASKLEGAL_REGISTER_PROJECTION_FAILED"):
        ServingStateStore(lambda: broken).activate(candidate.predecessor_state_id, candidate)
    assert broken.rolled_back is True


def test_adapter_rejects_returned_operation_or_candidate_drift_before_commit() -> None:
    """A syntactically complete row is not success unless it echoes the exact request."""
    candidate = _candidate()
    activation_receipt = _activation_receipt(candidate)
    cursor = _Cursor(
        [
            (
                activation_receipt,
                "ROLLED_BACK",
                candidate.predecessor_state_id,
                candidate.state_id,
                candidate.state_fingerprint,
                0,
            )
        ]
    )
    connection = _Connection(cursor)
    with pytest.raises(RegisterProjectionError, match="ASKLEGAL_REGISTER_PROJECTION_FAILED"):
        ServingStateStore(lambda: connection).activate(candidate.predecessor_state_id, candidate)
    assert connection.rolled_back is True


def test_adapter_rejects_malformed_input_and_preserves_base_exception() -> None:
    """No invalid candidate reaches SQL, while cancellation is never wrapped."""
    candidate = _candidate()
    malformed = ServingStateCandidate(
        candidate.state_id,
        "sha256:" + "A" * 64,
        candidate.predecessor_state_id,
        candidate.target_name,
        candidate.desired_inventory_fingerprint,
        candidate.coverage_fingerprint,
        candidate.embedding_profile_id,
        candidate.embedding_profile_fingerprint,
        candidate.approval_id,
        candidate.execution_lineage_id,
    )
    cursor = _Cursor([])
    with pytest.raises(RegisterProjectionError, match="ASKLEGAL_REGISTER_PROJECTION_FAILED"):
        ServingStateStore(lambda: _Connection(cursor)).activate(
            malformed.predecessor_state_id, malformed
        )
    assert cursor.operations == []

    def interrupted() -> _Connection:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _ = ServingStateStore(interrupted).active_state_id


def test_adapter_sanitizes_the_closed_read_lock_timeout_code() -> None:
    """The SQL procedure's translated 1222 code never leaks driver details."""
    connection = _Connection(
        _Cursor([], RuntimeError("ASKLEGAL_SERVING_STATE_LOCK_TIMEOUT raw-driver-detail"))
    )
    with pytest.raises(
        RegisterProjectionError, match="ASKLEGAL_SERVING_STATE_LOCK_TIMEOUT"
    ) as raised:
        _ = ServingStateStore(lambda: connection).active_state_id
    assert str(raised.value) == "ASKLEGAL_SERVING_STATE_LOCK_TIMEOUT"
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("target_name", [" bad-target", "bad target", "Bad-target", object()])
def test_adapter_rejects_noncontract_target_before_hashing_or_sql(target_name: object) -> None:
    """Only one exact target grammar reaches the stored procedure boundary."""
    candidate = replace(_candidate(), target_name=target_name)
    cursor = _Cursor([])
    with pytest.raises(
        RegisterProjectionError, match="ASKLEGAL_REGISTER_PROJECTION_FAILED"
    ) as raised:
        ServingStateStore(lambda: _Connection(cursor)).activate(
            candidate.predecessor_state_id, candidate
        )
    assert str(raised.value) == "ASKLEGAL_REGISTER_PROJECTION_FAILED"
    assert raised.value.__cause__ is None
    assert cursor.operations == []


@pytest.mark.sql_server
def test_disposable_sql_serving_state_proof_requires_explicit_connection() -> None:
    """Fresh-prefix SQL Server proof of CAS, replay, and exact predecessor rollback."""
    base = os.environ.get("ASKLEGAL_SQL_CONNECTION_BASE")
    if base is None:
        pytest.skip("ASKLEGAL_SQL_CONNECTION_BASE is not set")
    database_name = "AskLegalServingStateTask3"
    master = MssqlConnectionFactory(f"{base};Database=master;", autocommit=True)
    connection = master()
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"IF DB_ID('{database_name}') IS NOT NULL BEGIN ALTER DATABASE [{database_name}] "
            "SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE "
            f"[{database_name}]; END; CREATE DATABASE [{database_name}];"
        )
    finally:
        cursor.close()
        connection.close()
    database = MssqlConnectionFactory(f"{base};Database={database_name};")
    root = Path(__file__).parents[1] / "migrations"
    packages = (*tuple(next(root.glob(f"{number:06d}_*")) for number in range(1, 11)), _PACKAGE)
    apply_packages(database, packages, runner_build="serving-state-task-3")
    candidate = _candidate()
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT promotion.serving_state_v1_current "
            "(singleton_id, state_id, last_receipt_id, updated_at) "
            "VALUES (1, ?, ?, SYSUTCDATETIME())",
            (candidate.predecessor_state_id, "ssr_" + "0" * 48),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()
    promotion_connection = database()
    promotion_cursor = promotion_connection.cursor()
    role_candidate = _role_ownership_candidate()
    try:
        promotion_cursor.execute(
            "EXECUTE AS USER = 'asklegal_promotion_app'; "
            "EXEC promotion.activate_serving_state_v1 ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?; REVERT;",
            (
                role_candidate.predecessor_state_id,
                role_candidate.state_id,
                role_candidate.state_fingerprint,
                role_candidate.predecessor_state_id,
                role_candidate.target_name,
                role_candidate.desired_inventory_fingerprint,
                role_candidate.coverage_fingerprint,
                role_candidate.embedding_profile_id,
                role_candidate.embedding_profile_fingerprint,
                role_candidate.approval_id,
                role_candidate.execution_lineage_id,
            ),
        )
        activation_row = promotion_cursor.fetchone()
        assert activation_row is not None and activation_row[1] == "ACTIVATED"
        activation_receipt = str(activation_row[0])
        promotion_cursor.execute(
            "EXECUTE AS USER = 'asklegal_promotion_app'; "
            "EXEC promotion.read_serving_state_v1; REVERT;"
        )
        assert promotion_cursor.fetchone() == (role_candidate.state_id,)
        promotion_cursor.execute(
            "EXECUTE AS USER = 'asklegal_promotion_app'; "
            "EXEC promotion.rollback_serving_state_v1 ?, ?, ?; REVERT;",
            (role_candidate.state_id, role_candidate.predecessor_state_id, activation_receipt),
        )
        rollback_row = promotion_cursor.fetchone()
        assert rollback_row is not None and rollback_row[1] == "ROLLED_BACK"
        promotion_cursor.execute(
            "EXECUTE AS USER = 'asklegal_promotion_app'; "
            "EXEC promotion.read_serving_state_v1; REVERT;"
        )
        assert promotion_cursor.fetchone() == (role_candidate.predecessor_state_id,)
    finally:
        promotion_cursor.close()
        promotion_connection.close()
    store = ServingStateStore(database)
    receipt = store.activate(candidate.predecessor_state_id, candidate)
    assert receipt.replayed is False
    assert store.activate(candidate.predecessor_state_id, candidate).replayed is True
    for field, value in (
        ("state_fingerprint", "sha256:" + "9" * 64),
        ("target_name", "asklegal-dev-hk-20260827-drift"),
        ("desired_inventory_fingerprint", "sha256:" + "9" * 64),
        ("coverage_fingerprint", "sha256:" + "9" * 64),
        ("embedding_profile_id", "emp_" + "9" * 48),
        ("embedding_profile_fingerprint", "sha256:" + "9" * 64),
        ("approval_id", "apr_" + "9" * 48),
        ("execution_lineage_id", "exe_" + "9" * 48),
    ):
        with pytest.raises(
            RegisterProjectionError, match="ASKLEGAL_SERVING_STATE_BASE_STATE_DRIFT"
        ):
            store.activate(candidate.predecessor_state_id, replace(candidate, **{field: value}))
    store.verify(candidate.state_id)
    with pytest.raises(
        RegisterProjectionError, match="ASKLEGAL_SERVING_STATE_ROLLBACK_BINDING_INVALID"
    ):
        store.rollback(
            replace(candidate, predecessor_state_id="srv_" + "9" * 48), receipt.receipt_id
        )
    with pytest.raises(RegisterProjectionError, match="ASKLEGAL_SERVING_STATE_ROLLBACK_DRIFT"):
        store.rollback(candidate, "ssr_" + "9" * 64)
    assert store.rollback(candidate, receipt.receipt_id).replayed is False
    assert store.rollback(candidate, receipt.receipt_id).replayed is True
    assert store.active_state_id == candidate.predecessor_state_id

    concurrent_candidate_a = replace(
        candidate,
        state_id="srv_" + "2" * 48,
        state_fingerprint="sha256:" + "2" * 64,
        target_name="asklegal-dev-hk-20260827-candidate-a",
    )
    concurrent_candidate_b = replace(
        candidate,
        state_id="srv_" + "3" * 48,
        state_fingerprint="sha256:" + "3" * 64,
        target_name="asklegal-dev-hk-20260827-candidate-b",
    )

    def activate_concurrently(candidate_to_activate: ServingStateCandidate) -> object:
        try:
            return ServingStateStore(database).activate(
                candidate_to_activate.predecessor_state_id, candidate_to_activate
            )
        except RegisterProjectionError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = (
            workers.submit(activate_concurrently, concurrent_candidate_a),
            workers.submit(activate_concurrently, concurrent_candidate_b),
        )
        outcomes = tuple(future.result() for future in futures)
    assert sum(not isinstance(outcome, RegisterProjectionError) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, RegisterProjectionError) for outcome in outcomes) == 1
    loser = next(outcome for outcome in outcomes if isinstance(outcome, RegisterProjectionError))
    assert "ASKLEGAL_SERVING_STATE_BASE_STATE_DRIFT" in str(loser)

    holder = database()
    holder_cursor = holder.cursor()
    try:
        holder_cursor.execute(
            "BEGIN TRANSACTION; SELECT state_id FROM promotion.serving_state_v1_current "
            "WITH (TABLOCKX, HOLDLOCK) WHERE singleton_id = 1"
        )
        with pytest.raises(RegisterProjectionError, match="ASKLEGAL_SERVING_STATE_LOCK_TIMEOUT"):
            _ = ServingStateStore(database).active_state_id
    finally:
        holder.rollback()
        holder_cursor.close()
        holder.close()

    promotion_connection = database()
    promotion_cursor = promotion_connection.cursor()
    try:
        promotion_cursor.execute(
            "EXECUTE AS USER = 'asklegal_promotion_app'; "
            "EXEC promotion.read_serving_state_v1; REVERT;"
        )
        assert promotion_cursor.fetchone() is not None
    finally:
        promotion_cursor.close()
        promotion_connection.close()

    def denied_as(user: str, statement: str) -> None:
        connection = database()
        cursor = connection.cursor()
        try:
            with pytest.raises(mssql_python.Error, match=r"(?i)permission"):
                cursor.execute(f"EXECUTE AS USER = '{user}'; {statement}; REVERT;")
        finally:
            cursor.close()
            connection.close()

    for user in (
        "asklegal_control_app",
        "asklegal_review_app",
        "asklegal_acquisition_app",
        "asklegal_legal_processing_app",
    ):
        denied_as(user, "EXEC promotion.read_serving_state_v1")
        denied_as(
            user,
            "EXEC promotion.activate_serving_state_v1 "
            "'srv_x', 'srv_x', 'sha256:x', 'srv_x', 'target', 'sha256:x', "
            "'sha256:x', 'emp_x', 'sha256:x', 'apr_x', 'exe_x'",
        )
        denied_as(user, "EXEC promotion.rollback_serving_state_v1 'srv_x', 'srv_x', 'ssr_x'")
        denied_as(user, "SELECT state_id FROM promotion.serving_state_v1_current")
        denied_as(
            user,
            "INSERT promotion.serving_state_v1_current "
            "(singleton_id, state_id, last_receipt_id, updated_at) "
            "VALUES (2, 'srv_x', 'ssr_x', SYSUTCDATETIME())",
        )
        denied_as(user, "UPDATE promotion.serving_state_v1_current SET state_id = 'srv_x'")
        denied_as(user, "DELETE FROM promotion.serving_state_v1_current")
        denied_as(user, "SELECT state_id FROM promotion.serving_state_v1_fact")
        denied_as(
            user,
            "INSERT promotion.serving_state_v1_fact "
            "(receipt_id, operation_code, predecessor_state_id, state_id, state_fingerprint, "
            "target_name, desired_inventory_fingerprint, coverage_fingerprint, "
            "embedding_profile_id, embedding_profile_fingerprint, approval_id, "
            "execution_lineage_id, recorded_at) VALUES "
            "('ssr_x', 'ACTIVATED', 'srv_x', 'srv_x', 'sha256:x', 'target', 'sha256:x', "
            "'sha256:x', 'emp_x', 'sha256:x', 'apr_x', 'exe_x', SYSUTCDATETIME())",
        )
        denied_as(user, "UPDATE promotion.serving_state_v1_fact SET state_id = 'srv_x'")
        denied_as(user, "DELETE FROM promotion.serving_state_v1_fact")
