"""Small typed surface shielding the adapter from third-party typing gaps."""

from collections.abc import Sequence
from typing import Protocol

type SqlParameter = bytes | int | str | None
type SqlParameters = Sequence[SqlParameter]


class Cursor(Protocol):
    """Exact cursor operations used by the adapter."""

    def execute(self, operation: str, params: SqlParameters = ()) -> Cursor:
        """Execute one parameterized statement."""
        ...

    def fetchone(self) -> tuple[object, ...] | None:
        """Fetch one normalized row."""
        ...

    def fetchall(self) -> list[tuple[object, ...]]:
        """Fetch all normalized rows."""
        ...

    def close(self) -> None:
        """Close the cursor."""
        ...


class Connection(Protocol):
    """Exact connection operations used by the adapter."""

    def cursor(self) -> Cursor:
        """Create a cursor."""
        ...

    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    def rollback(self) -> None:
        """Roll back the current transaction."""
        ...

    def close(self) -> None:
        """Close the connection."""
        ...


class ConnectionFactory(Protocol):
    """Open a fresh, non-shared connection."""

    def __call__(self) -> Connection:
        """Return a fresh connection."""
        ...
