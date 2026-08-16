"""Bounded deadlock-victim retry proof for the store adapter."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from asklegal_management_register.store import ManagementRegisterStore

if TYPE_CHECKING:
    from asklegal_management_register.dbapi import Cursor, SqlParameters


@dataclass
class _Scenario:
    failures_remaining: int
    attempts: int = 0


class _Cursor:
    def __init__(self, scenario: _Scenario) -> None:
        self._scenario = scenario

    def execute(self, operation: str, params: SqlParameters = ()) -> Cursor:
        assert operation.startswith("EXEC review.consume_approval")
        assert len(params) == 5
        self._scenario.attempts += 1
        if self._scenario.failures_remaining > 0:
            self._scenario.failures_remaining -= 1
            message = "SQL Server error 1205: deadlock victim"
            raise RuntimeError(message)
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return ("command-deadlock", "APPROVAL_CONSUMED", b'{"status":"consumed"}', False)

    def fetchall(self) -> list[tuple[object, ...]]:
        return []

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, scenario: _Scenario) -> None:
        self._scenario = scenario

    def cursor(self) -> Cursor:
        return _Cursor(self._scenario)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


class _Factory:
    def __init__(self, scenario: _Scenario) -> None:
        self._scenario = scenario

    def __call__(self) -> _Connection:
        return _Connection(self._scenario)


def test_deadlock_victim_is_retried_then_succeeds() -> None:
    """A 1205 victim receives a fresh operation and succeeds within the bound."""
    scenario = _Scenario(failures_remaining=1)
    store = ManagementRegisterStore(_Factory(scenario), retry_delay_seconds=0)
    result = store.consume_approval(
        command_id="command-deadlock",
        command_fingerprint=b"f" * 32,
        approval_id="approval-deadlock",
        manifest_fingerprint=b"m" * 32,
        canonical_command=b"{}",
    )
    assert result.result_code == "APPROVAL_CONSUMED"
    assert scenario.attempts == 2


def test_deadlock_retry_is_bounded() -> None:
    """Persistent 1205 errors stop at the configured attempt ceiling."""
    scenario = _Scenario(failures_remaining=5)
    store = ManagementRegisterStore(_Factory(scenario), deadlock_attempts=2, retry_delay_seconds=0)
    with pytest.raises(RuntimeError, match="1205"):
        store.consume_approval(
            command_id="command-deadlock",
            command_fingerprint=b"f" * 32,
            approval_id="approval-deadlock",
            manifest_fingerprint=b"m" * 32,
            canonical_command=b"{}",
        )
    assert scenario.attempts == 2
