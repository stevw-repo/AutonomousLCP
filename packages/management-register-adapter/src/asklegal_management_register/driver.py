"""Contain the concrete first-party SQL Server driver."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import mssql_python

from asklegal_management_register.dbapi import Connection, Cursor, SqlParameters

_V1_SERVER = "sql-server"
_V1_PORT = 1433
_V1_DATABASE = "AskLegalPocOperational"
_V1_APPLICATION_USERS = frozenset(
    {
        "asklegal_acquisition_app",
        "asklegal_control_app",
        "asklegal_legal_processing_app",
        "asklegal_promotion_app",
        "asklegal_review_app",
    }
)
_MAX_PASSWORD_BYTES = 1_024
_MAX_LOGIN_TIMEOUT_SECONDS = 30


class SqlCredentialErrorCode(StrEnum):
    """Closed safe SQL credential and connection rejection reasons."""

    CONNECTION = "SQL_CONNECTION_FAILED"
    PASSWORD = "SQL_PASSWORD_INVALID"
    READINESS = "SQL_READINESS_FAILED"
    SETTINGS = "SQL_SETTINGS_INVALID"


class SqlCredentialError(ValueError):
    """SQL connection rejection that never includes settings or credential values."""

    code: SqlCredentialErrorCode

    def __init__(self, code: SqlCredentialErrorCode) -> None:
        """Create one safe SQL boundary failure."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True, repr=False)
class SqlServerPassword:
    """One UTF-8 SQL password with a permanently redacted representation."""

    _value: str

    @classmethod
    def from_bytes(cls, value: bytes) -> SqlServerPassword:
        """Validate exact credential-file bytes without trimming or coercion."""
        if type(value) is not bytes or not 1 <= len(value) <= _MAX_PASSWORD_BYTES:
            raise SqlCredentialError(SqlCredentialErrorCode.PASSWORD)
        try:
            decoded = value.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise SqlCredentialError(SqlCredentialErrorCode.PASSWORD) from None
        if "\x00" in decoded or "\r" in decoded or "\n" in decoded:
            raise SqlCredentialError(SqlCredentialErrorCode.PASSWORD)
        return cls(decoded)

    def __repr__(self) -> str:
        """Never reveal the password or its size."""
        return "SqlServerPassword(<redacted>)"

    def reveal(self) -> str:
        """Return the exact value only at the concrete driver call boundary."""
        return self._value


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
    """Legacy raw-string factory retained for the opt-in local SQL proof only."""

    connection_string: str = field(repr=False)
    autocommit: bool = False

    def __call__(self) -> Connection:
        """Open a transaction-capable connection."""
        return _MssqlConnection(
            mssql_python.connect(self.connection_string, autocommit=self.autocommit)
        )


@dataclass(frozen=True, slots=True)
class V1MssqlConnectionFactory:
    """Create one V1 application connection from exact settings and file material."""

    username: str
    password: SqlServerPassword = field(repr=False)
    server: str = _V1_SERVER
    port: int = _V1_PORT
    database: str = _V1_DATABASE
    login_timeout_seconds: int = 10
    autocommit: bool = False

    def __post_init__(self) -> None:
        """Reject topology, principal, transport, and type drift before connection."""
        if (
            self.username not in _V1_APPLICATION_USERS
            or type(self.password) is not SqlServerPassword
            or self.server != _V1_SERVER
            or type(self.port) is not int
            or self.port != _V1_PORT
            or self.database != _V1_DATABASE
            or type(self.login_timeout_seconds) is not int
            or not 1 <= self.login_timeout_seconds <= _MAX_LOGIN_TIMEOUT_SECONDS
            or type(self.autocommit) is not bool
        ):
            raise SqlCredentialError(SqlCredentialErrorCode.SETTINGS)

    def __call__(self) -> Connection:
        """Open one certificate-validated encrypted connection with a bounded login."""
        try:
            connection = mssql_python.connect(
                "",
                autocommit=self.autocommit,
                timeout=self.login_timeout_seconds,
                server=f"{self.server},{self.port}",
                database=self.database,
                uid=self.username,
                pwd=self.password.reveal(),
                Encrypt="Strict",
                TrustServerCertificate="No",
                HostNameInCertificate=self.server,
            )
        except mssql_python.Error, ValueError:
            raise SqlCredentialError(SqlCredentialErrorCode.CONNECTION) from None
        return _MssqlConnection(connection)

    def check_readiness(self) -> None:
        """Open, query, and close one bounded encrypted connection without mutation."""
        try:
            connection = self()
        except SqlCredentialError:
            raise SqlCredentialError(SqlCredentialErrorCode.READINESS) from None
        cursor: Cursor | None = None
        row: tuple[object, ...] | None = None
        failed = False
        try:
            cursor = connection.cursor()
            row = cursor.execute("SELECT CAST(1 AS int)").fetchone()
        except mssql_python.Error, ValueError:
            failed = True
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except mssql_python.Error:
                    failed = True
            try:
                connection.close()
            except mssql_python.Error:
                failed = True
        if failed or row != (1,):
            raise SqlCredentialError(SqlCredentialErrorCode.READINESS)
