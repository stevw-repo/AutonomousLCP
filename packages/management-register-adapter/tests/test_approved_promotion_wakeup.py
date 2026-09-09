"""Provider-disabled SQL boundary for approved-Promotion wake-up leases."""

from collections.abc import Sequence
from datetime import datetime

import mssql_python
import pytest
from asklegal_management_register import (
    ApprovedPromotionClaim,
    ApprovedPromotionQueueStore,
    RegisterProjectionError,
)

type Parameter = bytes | datetime | int | str | None


class FakeCursor:
    """Record the one queue-procedure call and return a configured row."""

    def __init__(self, rows: list[tuple[object, ...]], *, error: Exception | None = None) -> None:
        """Bind one stored-procedure row."""
        self._rows = rows
        self._error = error
        self.operations: list[tuple[str, tuple[Parameter, ...]]] = []
        self.closed = False

    def execute(self, operation: str, params: Sequence[Parameter] = ()) -> FakeCursor:
        """Retain one parameterized execution."""
        self.operations.append((operation, tuple(params)))
        if self._error is not None:
            raise self._error
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        """Return the configured result row."""
        return self._rows.pop(0) if self._rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return every remaining stored-procedure row."""
        rows = self._rows
        self._rows = []
        return rows

    def close(self) -> None:
        """Record closure."""
        self.closed = True


class FakeConnection:
    """Expose one cursor with observable transaction closure."""

    def __init__(self, cursor: FakeCursor) -> None:
        """Bind the supplied cursor."""
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        """Return the bound cursor."""
        return self._cursor

    def commit(self) -> None:
        """Record the finite stored-procedure transaction acknowledgement."""
        self.committed = True

    def rollback(self) -> None:
        """Record a failed stored-procedure transaction."""
        self.rolled_back = True

    def close(self) -> None:
        """Record closure."""
        self.closed = True


def test_claim_next_returns_only_the_exact_registered_decision_facts() -> None:
    """A wake-up lease cannot introduce authority, execution, or provider inputs."""
    decision_fingerprint = bytes.fromhex("a" * 64)
    cursor = FakeCursor(
        [
            (
                "ppk_" + "1" * 48,
                "apr_" + "2" * 48,
                decision_fingerprint,
                "pmn_" + "3" * 48,
                "sha256:" + "4" * 64,
                "pwr_" + "5" * 48,
                "2026-08-27T12:05:00.0000000Z",
                1,
                1,
            )
        ]
    )
    connection = FakeConnection(cursor)

    claim = ApprovedPromotionQueueStore(lambda: connection).claim_next(
        "pwr_" + "5" * 48, "2026-08-27T12:05:00Z"
    )

    assert claim is not None
    assert claim.proposal_package_id == "ppk_" + "1" * 48
    assert claim.approval_id == "apr_" + "2" * 48
    assert claim.decision_fingerprint == "sha256:" + "a" * 64
    assert claim.manifest_id == "pmn_" + "3" * 48
    assert claim.manifest_fingerprint == "sha256:" + "4" * 64
    assert claim.claimant_worker_id == "pwr_" + "5" * 48
    assert claim.claimed_until == "2026-08-27T12:05:00.0000000Z"
    assert claim.generation == 1
    assert claim.fencing_token == 1
    assert connection.committed is True
    assert connection.closed is True
    statement, parameters = cursor.operations[0]
    assert statement.startswith("EXEC promotion.claim_next_approved_promotion_v1")
    assert parameters == ("pwr_" + "5" * 48, "2026-08-27T12:05:00.0000000Z")


def test_claim_next_closes_on_a_malformed_claim_row() -> None:
    """A corrupt queue result cannot become a claimable work item."""
    cursor = FakeCursor([("ppk_" + "1" * 48,)])
    connection = FakeConnection(cursor)

    with pytest.raises(RegisterProjectionError):
        ApprovedPromotionQueueStore(lambda: connection).claim_next(
            "pwr_" + "5" * 48, "2026-08-27T12:05:00Z"
        )

    assert connection.rolled_back is True
    assert connection.closed is True


def test_acknowledge_started_requires_the_exact_existing_consumption_lineage() -> None:
    """Acknowledgement cannot be mistaken for Approval consumption or execution begin."""
    claim = ApprovedPromotionClaim(
        "ppk_" + "1" * 48,
        "apr_" + "2" * 48,
        "sha256:" + "a" * 64,
        "pmn_" + "3" * 48,
        "sha256:" + "4" * 64,
        "pwr_" + "5" * 48,
        "2026-08-27T12:05:00.0000000Z",
        1,
        1,
    )
    cursor = FakeCursor([(claim.approval_id, "exe_" + "5" * 48, claim.fencing_token)])
    connection = FakeConnection(cursor)

    ApprovedPromotionQueueStore(lambda: connection).acknowledge_started(claim, "exe_" + "5" * 48)

    assert connection.committed is True
    assert connection.closed is True
    statement, parameters = cursor.operations[0]
    assert statement.startswith("EXEC promotion.acknowledge_approved_promotion_started_v1")
    assert parameters == (
        claim.approval_id,
        claim.proposal_package_id,
        bytes.fromhex("a" * 64),
        claim.manifest_id,
        claim.manifest_fingerprint,
        claim.claimant_worker_id,
        claim.claimed_until,
        claim.generation,
        claim.fencing_token,
        "exe_" + "5" * 48,
    )


def test_claim_next_rejects_a_returned_claimant_outside_the_promotion_worker_grammar() -> None:
    """A row from any other worker namespace cannot be treated as Promotion work."""
    cursor = FakeCursor(
        [
            (
                "ppk_" + "1" * 48,
                "apr_" + "2" * 48,
                bytes.fromhex("a" * 64),
                "pmn_" + "3" * 48,
                "sha256:" + "4" * 64,
                "worker-a",
                "2026-08-27T12:05:00Z",
                1,
                1,
            )
        ]
    )
    connection = FakeConnection(cursor)

    with pytest.raises(RegisterProjectionError):
        ApprovedPromotionQueueStore(lambda: connection).claim_next(
            "pwr_" + "5" * 48, "2026-08-27T12:05:00Z"
        )

    assert connection.rolled_back is True


def _claim_row(
    *,
    worker_id: str = "pwr_" + "5" * 48,
    claimed_until: str = "2026-08-27T12:05:00.0000000Z",
    generation: int = 1,
    fencing_token: int = 1,
) -> tuple[object, ...]:
    """Build one independently literal, SQL-shaped successful claim row."""
    return (
        "ppk_" + "1" * 48,
        "apr_" + "2" * 48,
        bytes.fromhex("a" * 64),
        "pmn_" + "3" * 48,
        "sha256:" + "4" * 64,
        worker_id,
        claimed_until,
        generation,
        fencing_token,
    )


def test_claim_next_binds_the_returned_worker_and_normalized_lease_to_the_request() -> None:
    """A foreign worker or differently bounded lease cannot be committed as this caller's claim."""
    cursor = FakeCursor([_claim_row(worker_id="pwr_" + "6" * 48)])
    connection = FakeConnection(cursor)

    with pytest.raises(RegisterProjectionError):
        ApprovedPromotionQueueStore(lambda: connection).claim_next(
            "pwr_" + "5" * 48, "2026-08-27T12:05:00Z"
        )

    assert connection.rolled_back is True
    assert connection.committed is False


def test_claim_next_rejects_zero_generation_before_committing() -> None:
    """A SQL row below the table's initial generation cannot become a lease."""
    cursor = FakeCursor([_claim_row(generation=0)])
    connection = FakeConnection(cursor)

    with pytest.raises(RegisterProjectionError):
        ApprovedPromotionQueueStore(lambda: connection).claim_next(
            "pwr_" + "5" * 48, "2026-08-27T12:05:00Z"
        )

    assert connection.rolled_back is True
    assert connection.committed is False


def test_claim_next_rejects_multiple_procedure_rows_before_committing() -> None:
    """A scalar queue call must not choose silently between two database rows."""
    cursor = FakeCursor([_claim_row(), _claim_row()])
    connection = FakeConnection(cursor)

    with pytest.raises(RegisterProjectionError):
        ApprovedPromotionQueueStore(lambda: connection).claim_next(
            "pwr_" + "5" * 48, "2026-08-27T12:05:00Z"
        )

    assert connection.rolled_back is True
    assert connection.committed is False


def test_claim_next_rejects_malformed_caller_inputs_without_opening_sql() -> None:
    """Invalid lease identity or timestamp must not reach a SQL connection boundary."""

    def forbidden_connection() -> FakeConnection:
        pytest.fail("invalid caller input opened SQL")

    store = ApprovedPromotionQueueStore(forbidden_connection)
    with pytest.raises(RegisterProjectionError):
        store.claim_next("pwr_" + "A" * 48, "2026-08-27T12:05:00Z")
    with pytest.raises(RegisterProjectionError):
        store.claim_next("pwr_" + "5" * 48, "2026-08-27 12:05:00Z")


def test_acknowledge_started_rejects_a_noncanonical_claim_before_opening_sql() -> None:
    """A digest without its canonical sha256 prefix cannot be rewritten at the SQL boundary."""
    malformed = ApprovedPromotionClaim(
        "ppk_" + "1" * 48,
        "apr_" + "2" * 48,
        "a" * 64,
        "pmn_" + "3" * 48,
        "sha256:" + "4" * 64,
        "pwr_" + "5" * 48,
        "2026-08-27T12:05:00.0000000Z",
        1,
        1,
    )

    def forbidden_connection() -> FakeConnection:
        pytest.fail("malformed claim opened SQL")

    with pytest.raises(RegisterProjectionError):
        ApprovedPromotionQueueStore(forbidden_connection).acknowledge_started(
            malformed, "exe_" + "6" * 48
        )


def test_queue_preserves_base_exception_observability() -> None:
    """Process-control exceptions must not be converted into an ordinary projection failure."""

    class StopNow(BaseException):
        pass

    def interrupted_connection() -> FakeConnection:
        raise StopNow

    with pytest.raises(StopNow):
        ApprovedPromotionQueueStore(interrupted_connection).claim_next(
            "pwr_" + "5" * 48, "2026-08-27T12:05:00Z"
        )


def test_claim_next_preserves_only_the_safe_sql_error_code() -> None:
    """A queue lock timeout remains visible without exposing driver diagnostic text."""
    cursor = FakeCursor(
        [],
        error=mssql_python.Error(
            "driver diagnostics containing connection details",
            "ASKLEGAL_APPROVED_PROMOTION_QUEUE_LOCK_TIMEOUT",
        ),
    )
    connection = FakeConnection(cursor)

    with pytest.raises(
        RegisterProjectionError, match=r"^ASKLEGAL_APPROVED_PROMOTION_QUEUE_LOCK_TIMEOUT$"
    ) as raised:
        ApprovedPromotionQueueStore(lambda: connection).claim_next(
            "pwr_" + "5" * 48, "2026-08-27T12:05:00Z"
        )

    assert raised.value.__cause__ is None
    assert connection.rolled_back is True
    assert connection.closed is True


def test_claim_next_uses_the_safe_fallback_without_a_driver_cause() -> None:
    """A driver failure without an approved code cannot cross the queue boundary."""
    cursor = FakeCursor(
        [], error=mssql_python.Error("password=not-for-callers", "driver-no-approved-code")
    )
    connection = FakeConnection(cursor)

    with pytest.raises(
        RegisterProjectionError, match=r"^ASKLEGAL_REGISTER_PROJECTION_FAILED$"
    ) as raised:
        ApprovedPromotionQueueStore(lambda: connection).claim_next(
            "pwr_" + "5" * 48, "2026-08-27T12:05:00Z"
        )

    assert raised.value.__cause__ is None
    assert "password" not in str(raised.value)
    assert connection.rolled_back is True
    assert connection.closed is True


def test_acknowledge_started_preserves_only_the_safe_sql_error_code() -> None:
    """An acknowledgement lock timeout remains observable without driver diagnostics."""
    claim = ApprovedPromotionClaim(
        "ppk_" + "1" * 48,
        "apr_" + "2" * 48,
        "sha256:" + "a" * 64,
        "pmn_" + "3" * 48,
        "sha256:" + "4" * 64,
        "pwr_" + "5" * 48,
        "2026-08-27T12:05:00.0000000Z",
        1,
        1,
    )
    cursor = FakeCursor(
        [],
        error=mssql_python.Error(
            "driver diagnostics containing connection details",
            "ASKLEGAL_APPROVED_PROMOTION_ACKNOWLEDGEMENT_LOCK_TIMEOUT",
        ),
    )
    connection = FakeConnection(cursor)

    with pytest.raises(
        RegisterProjectionError,
        match=r"^ASKLEGAL_APPROVED_PROMOTION_ACKNOWLEDGEMENT_LOCK_TIMEOUT$",
    ) as raised:
        ApprovedPromotionQueueStore(lambda: connection).acknowledge_started(
            claim, "exe_" + "6" * 48
        )

    assert raised.value.__cause__ is None
    assert connection.rolled_back is True
    assert connection.closed is True
