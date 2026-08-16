"""Contain the concrete first-party SQL Server driver."""

from dataclasses import dataclass

import mssql_python

from asklegal_management_register.dbapi import Connection, Cursor, SqlParameters


class _MssqlCursor:
    """Narrow runtime-checked cursor wrapper."""

    def __init__(self, cursor: mssql_python.Cursor) -> None:
        self._cursor = cursor

    def execute(self, operation: str, params: SqlParameters = ()) -> Cursor:
        """Execute through the driver's single known-typing gap."""
        if params:
            self._cursor.execute(operation, params)  # pyright: ignore[reportUnknownMemberType]
        else:
            self._cursor.execute(operation)  # pyright: ignore[reportUnknownMemberType]
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        """Normalize the driver's tuple-like Row to a closed tuple."""
        row = self._cursor.fetchone()
        if row is None:
            return None
        return tuple(_row_value(row, index) for index in range(len(row)))

    def fetchall(self) -> list[tuple[object, ...]]:
        """Normalize all driver Rows to closed tuples."""
        return [
            tuple(_row_value(row, index) for index in range(len(row)))
            for row in self._cursor.fetchall()
        ]

    def close(self) -> None:
        """Close the concrete cursor."""
        self._cursor.close()


class _MssqlConnection:
    """Narrow concrete connection wrapper."""

    def __init__(self, connection: mssql_python.Connection) -> None:
        self._connection = connection

    def cursor(self) -> Cursor:
        """Create a wrapped cursor."""
        return _MssqlCursor(self._connection.cursor())

    def commit(self) -> None:
        """Commit the transaction."""
        self._connection.commit()

    def rollback(self) -> None:
        """Roll back the transaction."""
        self._connection.rollback()

    def close(self) -> None:
        """Close the concrete connection."""
        self._connection.close()


def _row_value(row: mssql_python.Row, index: int) -> object:
    return row[index]


@dataclass(frozen=True, slots=True)
class MssqlConnectionFactory:
    """Create one `mssql-python` connection per complete operation."""

    connection_string: str
    autocommit: bool = False

    def __call__(self) -> Connection:
        """Open a transaction-capable connection."""
        return _MssqlConnection(
            mssql_python.connect(self.connection_string, autocommit=self.autocommit)
        )
