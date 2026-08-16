"""Fingerprint-bound Management Register commands and recovery."""

import time
from dataclasses import dataclass

from asklegal_management_register.dbapi import ConnectionFactory


class CommandFingerprintMismatch(RuntimeError):
    """An idempotency key was reused with different canonical bytes."""


class AmbiguousCommit(RuntimeError):
    """The database committed but the client did not receive acknowledgement."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Immutable result returned for an original or replayed command."""

    command_id: str
    result_code: str
    result_bytes: bytes
    replayed: bool


class ManagementRegisterStore:
    """Run one short stored-procedure command per fresh connection."""

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        deadlock_attempts: int = 3,
        retry_delay_seconds: float = 0.01,
    ) -> None:
        """Configure bounded retry for database-selected deadlock victims."""
        if deadlock_attempts < 1:
            raise ValueError("deadlock_attempts must be positive")
        self._connection_factory = connection_factory
        self._deadlock_attempts = deadlock_attempts
        self._retry_delay_seconds = retry_delay_seconds

    def consume_approval(
        self,
        *,
        command_id: str,
        command_fingerprint: bytes,
        approval_id: str,
        manifest_fingerprint: bytes,
        canonical_command: bytes,
        simulate_lost_ack: bool = False,
    ) -> CommandResult:
        """Consume one approval, resolving a lost acknowledgement by immutable result."""
        for attempt in range(1, self._deadlock_attempts + 1):
            connection = self._connection_factory()
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "EXEC review.consume_approval ?, ?, ?, ?, ?",
                    (
                        command_id,
                        command_fingerprint,
                        approval_id,
                        manifest_fingerprint,
                        canonical_command,
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("consume_approval returned no result")
                connection.commit()
                if simulate_lost_ack:
                    raise AmbiguousCommit(command_id)
                return _command_result(row)
            except Exception as error:
                try:
                    connection.rollback()
                except Exception:
                    pass
                if isinstance(error, AmbiguousCommit):
                    return self.resolve_command(command_id, command_fingerprint)
                if _is_fingerprint_mismatch(error):
                    raise CommandFingerprintMismatch(command_id) from error
                if _is_deadlock(error) and attempt < self._deadlock_attempts:
                    time.sleep(self._retry_delay_seconds * attempt)
                    continue
                raise
            finally:
                cursor.close()
                connection.close()
        raise RuntimeError("unreachable deadlock retry state")

    def resolve_command(self, command_id: str, command_fingerprint: bytes) -> CommandResult:
        """Resolve an ambiguous outcome without rerunning the command."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.resolve_command ?, ?",
                (command_id, command_fingerprint),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(command_id)
            return _command_result(row)
        except Exception as error:
            if _is_fingerprint_mismatch(error):
                raise CommandFingerprintMismatch(command_id) from error
            raise
        finally:
            cursor.close()
            connection.close()


def _command_result(row: tuple[object, ...]) -> CommandResult:
    command_id, result_code, result_bytes, replayed = row
    if not isinstance(command_id, str):
        raise TypeError("command_id is not text")
    if not isinstance(result_code, str):
        raise TypeError("result_code is not text")
    if not isinstance(result_bytes, bytes):
        raise TypeError("result_bytes are not bytes")
    if not isinstance(replayed, bool | int):
        raise TypeError("replayed is not boolean-like")
    return CommandResult(command_id, result_code, result_bytes, bool(replayed))


def _is_deadlock(error: Exception) -> bool:
    return "1205" in str(error).lower() or "deadlock" in str(error).lower()


def _is_fingerprint_mismatch(error: Exception) -> bool:
    return "ASKLEGAL_COMMAND_FINGERPRINT_MISMATCH" in str(error)
