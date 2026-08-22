"""Exact SQL command and projection boundary for Review-ready proposals."""

from collections.abc import Sequence
from hashlib import sha256

from asklegal_management_register import RegisterEventCommand, RegisterEventStore

type Parameter = bytes | int | str | None


class FakeCursor:
    """Record exact parameterized operations and return configured rows."""

    def __init__(
        self,
        *,
        one: tuple[object, ...] | None = None,
        many: list[tuple[object, ...]] | None = None,
    ) -> None:
        """Configure scalar and sequence results for one fake cursor."""
        self.one = one
        self.many = many or []
        self.operations: list[tuple[str, tuple[Parameter, ...]]] = []
        self.closed = False

    def execute(self, operation: str, params: Sequence[Parameter] = ()) -> FakeCursor:
        """Record one parameterized operation."""
        self.operations.append((operation, tuple(params)))
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        """Return the configured scalar row."""
        return self.one

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return the configured row sequence."""
        return list(self.many)

    def close(self) -> None:
        """Record cursor closure."""
        self.closed = True


class FakeConnection:
    """Expose one cursor and record transaction closure."""

    def __init__(self, cursor: FakeCursor) -> None:
        """Bind one cursor and clear transaction flags."""
        self.bound_cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        """Return the bound cursor."""
        return self.bound_cursor

    def commit(self) -> None:
        """Record a commit."""
        self.committed = True

    def rollback(self) -> None:
        """Record a rollback."""
        self.rolled_back = True

    def close(self) -> None:
        """Record connection closure."""
        self.closed = True


def test_review_ready_event_uses_the_generic_atomic_command_protocol() -> None:
    """No application receives direct fact-table write access."""
    cursor = FakeCursor(one=("cmd_1", "APPLIED", 1, b'{"result":"APPLIED"}', False))
    connection = FakeConnection(cursor)
    store = RegisterEventStore(lambda: connection)
    command = b'{"action":"REGISTER_REVIEW_READY_PROPOSAL"}'
    event = b'{"package_id":"ppk_1"}'

    result = store.record_event(
        RegisterEventCommand(
            owning_application="CONTROL_PLANE",
            command_id="cmd_1",
            command_bytes=command,
            target_id="ppk_1",
            expected_version=None,
            expected_absent=True,
            expires_at="2026-08-22T00:00:00Z",
            winner_key="review-ready:ppk_1",
            event_id="evt_1",
            event_type="PROPOSAL_REVIEW_READY",
            event_bytes=event,
        )
    )

    assert result.authoritative_version == 1
    assert result.replayed is False
    assert connection.committed is True
    assert connection.closed is True
    operation, parameters = cursor.operations[0]
    assert operation.startswith("EXEC register.commit_command_v1")
    assert parameters[2] == sha256(command).digest()
    assert parameters[6] == 1
    assert parameters[13] == sha256(event).digest()


def test_review_and_promotion_read_only_the_least_privilege_projection() -> None:
    """Projection rows retain exact receipt bytes and fingerprints."""
    event = b'{"package_id":"ppk_1"}'
    cursor = FakeCursor(
        many=[
            (
                "ppk_1",
                event,
                sha256(event).digest(),
                1,
                "2026-08-21T12:00:00",
                None,
                None,
                0,
                None,
                None,
            )
        ]
    )
    connection = FakeConnection(cursor)

    rows = RegisterEventStore(lambda: connection).review_ready_proposals()

    assert len(rows) == 1
    assert rows[0].receipt_bytes == event
    assert rows[0].receipt_fingerprint == sha256(event).digest()
    assert "review.proposal_package_review_v1" in cursor.operations[0][0]
    assert connection.closed is True
