"""V1 file-credential and encrypted SQL connection boundary proofs."""

from dataclasses import replace

import mssql_python
import pytest
from asklegal_management_register import (
    SqlCredentialError,
    SqlCredentialErrorCode,
    SqlServerPassword,
    V1MssqlConnectionFactory,
)
from mssql_python.connection_string_parser import sanitize_connection_string


class _FakeDriverConnection:
    """Minimal concrete stand-in returned by the patched driver call."""

    def cursor(self) -> object:
        return object()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


class _ReadinessCursor:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row
        self.closed = False

    def execute(self, operation: str, *_parameters: object) -> _ReadinessCursor:
        if operation != "SELECT CAST(1 AS int)":
            raise AssertionError(operation)
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row

    def close(self) -> None:
        self.closed = True


class _ReadinessConnection:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.readiness_cursor = _ReadinessCursor(row)
        self.closed = False

    def cursor(self) -> _ReadinessCursor:
        return self.readiness_cursor

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_v1_factory_passes_password_only_at_encrypted_connection_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep secrets out of stored connection strings, arguments, and representations."""
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_connect(*args: object, **kwargs: object) -> _FakeDriverConnection:
        calls.append((args, kwargs))
        return _FakeDriverConnection()

    monkeypatch.setattr(mssql_python, "connect", fake_connect)
    secret = "synthetic;pass}=word"
    password = SqlServerPassword.from_bytes(secret.encode())
    factory = V1MssqlConnectionFactory("asklegal_control_app", password)

    factory()

    assert calls == [
        (
            ("",),
            {
                "Encrypt": "Strict",
                "HostNameInCertificate": "sql-server",
                "TrustServerCertificate": "No",
                "autocommit": False,
                "database": "AskLegalPocOperational",
                "pwd": secret,
                "server": "sql-server,1433",
                "timeout": 10,
                "uid": "asklegal_control_app",
            },
        )
    ]
    assert secret not in repr(password)
    assert secret not in repr(factory)
    assert "connection_string" not in repr(factory)


def test_pinned_driver_sanitizes_braced_passwords_without_tail_leakage() -> None:
    """Bind the exact pinned driver's log sanitizer to a hostile-looking password."""
    secret = "synthetic;pass}=word"
    sanitized = sanitize_connection_string(
        "Server=sql-server;UID=asklegal_control_app;PWD={synthetic;pass}}=word}"
    )
    assert secret not in sanitized
    assert "PWD=***" in sanitized


@pytest.mark.parametrize(
    "raw",
    [b"", b"line\nbreak", b"carriage\rreturn", b"nul\x00byte", b"\xff"],
)
def test_sql_password_rejects_empty_control_or_non_utf8_material(raw: bytes) -> None:
    """Reject malformed credential-file bytes without echoing their content."""
    with pytest.raises(SqlCredentialError) as error:
        SqlServerPassword.from_bytes(raw)
    assert error.value.code is SqlCredentialErrorCode.PASSWORD
    assert str(error.value) == "SQL_PASSWORD_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("username", "sa"),
        ("server", "127.0.0.1"),
        ("port", 1434),
        ("database", "master"),
        ("login_timeout_seconds", 0),
        ("autocommit", 1),
    ],
)
def test_v1_factory_rejects_identity_topology_and_type_drift(field: str, value: object) -> None:
    """Allow only the exact application principal and V1 operational endpoint."""
    factory = V1MssqlConnectionFactory(
        "asklegal_review_app", SqlServerPassword.from_bytes(b"synthetic-password")
    )
    with pytest.raises(SqlCredentialError) as error:
        replace(factory, **{field: value})
    assert error.value.code is SqlCredentialErrorCode.SETTINGS


def test_v1_factory_normalizes_driver_failure_without_secret_or_chaining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not propagate a driver error that contains connection material."""
    secret = "synthetic-password"

    def fail_connect(*_args: object, **_kwargs: object) -> None:
        message = f"driver accidentally echoed {secret}"
        raise ValueError(message)

    monkeypatch.setattr(mssql_python, "connect", fail_connect)
    factory = V1MssqlConnectionFactory(
        "asklegal_promotion_app", SqlServerPassword.from_bytes(secret.encode())
    )
    with pytest.raises(SqlCredentialError) as error:
        factory()
    assert error.value.code is SqlCredentialErrorCode.CONNECTION
    assert str(error.value) == "SQL_CONNECTION_FAILED"
    assert secret not in repr(error.value)
    assert error.value.__cause__ is None
    assert error.value.__context__ is not None
    assert error.value.__suppress_context__ is True


def test_v1_sql_readiness_is_exact_non_mutating_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require the exact scalar response and close both cursor and connection."""
    connection = _ReadinessConnection((1,))
    monkeypatch.setattr(mssql_python, "connect", lambda *_args, **_kwargs: connection)
    factory = V1MssqlConnectionFactory(
        "asklegal_control_app", SqlServerPassword.from_bytes(b"synthetic-password")
    )

    factory.check_readiness()

    assert connection.readiness_cursor.closed is True
    assert connection.closed is True


def test_v1_sql_readiness_fails_closed_on_wrong_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not accept a connection whose readiness query is not exact."""
    connection = _ReadinessConnection((2,))
    monkeypatch.setattr(mssql_python, "connect", lambda *_args, **_kwargs: connection)
    factory = V1MssqlConnectionFactory(
        "asklegal_review_app", SqlServerPassword.from_bytes(b"synthetic-password")
    )

    with pytest.raises(SqlCredentialError) as error:
        factory.check_readiness()

    assert error.value.code is SqlCredentialErrorCode.READINESS
    assert connection.readiness_cursor.closed is True
    assert connection.closed is True
