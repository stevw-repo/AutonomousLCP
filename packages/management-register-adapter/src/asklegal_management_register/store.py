"""Fingerprint-bound Management Register commands and recovery."""

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

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


@dataclass(frozen=True, slots=True)
class ClaimedEffect:
    """One effect intent this claimant now holds under a fencing token."""

    effect_intent_id: str
    effect_type: str
    aggregate_id: str
    intent_bytes: bytes
    fencing_token: int
    attempt_ceiling: int


class EffectHandoffStore:
    """Record intended effects, and let their owning application claim them.

    **An application may only record intents it owns.** `commit_command_v1` rejects
    any command whose `owning_application` is not the caller, with
    `REJECTED_UNAUTHORIZED`, so this cannot be used to hand work to another
    application. The scheduler enforces the same rule from the other side. A stage
    does not push work to the next stage; it records what it did, and the next
    stage notices and records its own intent.

    Everything goes through the register's own procedures and views. Applications
    hold EXECUTE on the procedures and SELECT on `effect_status_v1`, and are denied
    INSERT, UPDATE, and DELETE on the schema outright, so direct table access is
    not merely discouraged here — the database refuses it.
    """

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        """Bind the store to one connection factory."""
        self._connection_factory = connection_factory

    def record_intent(
        self,
        *,
        effect_intent_id: str,
        owning_application: str,
        command_id: str,
        aggregate_id: str,
        effect_type: str,
        intent_bytes: bytes,
        intent_fingerprint: bytes,
        deadline_seconds: int = 3600,
        attempt_ceiling: int = 3,
        event_type: str = "EFFECT_REQUESTED",
    ) -> bool:
        """Record one intended effect through the command protocol.

        A command that applied must carry the event it produced, so the intent is
        recorded together with the fact that requested it. That is the protocol's
        rule, not an incidental parameter: an effect with no recorded cause would
        be an effect nobody asked for.

        An intent is committed as part of a command, which is what makes it
        idempotent: replaying the same command id with the same fingerprint is a
        replay, not a second intent. Returns False when the intent already existed.
        """
        if self.intent_exists(effect_intent_id):
            return False
        command_bytes = intent_bytes
        # EXEC parameters must be values, not expressions, so the horizon is
        # computed here rather than with DATEADD inside the call.
        horizon = datetime.now(UTC) + timedelta(seconds=deadline_seconds)
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.commit_command_v1 "
                "@owning_application = ?, @command_id = ?, @command_fingerprint = ?, "
                "@command_bytes = ?, @target_id = ?, @expected_absent = ?, "
                "@expires_at = ?, @guard_result_code = ?, "
                "@event_id = ?, @event_type = ?, @event_bytes = ?, "
                "@event_fingerprint = ?, "
                "@effect_intent_id = ?, @effect_type = ?, @intent_bytes = ?, "
                "@intent_fingerprint = ?, @effect_deadline = ?, "
                "@attempt_ceiling = ?",
                (
                    owning_application,
                    command_id,
                    sha256(command_bytes).digest(),
                    command_bytes,
                    aggregate_id,
                    1,
                    horizon,
                    "APPLIED",
                    f"evt_{effect_intent_id.removeprefix('eint_')}"[:80],
                    event_type,
                    intent_bytes,
                    intent_fingerprint,
                    effect_intent_id,
                    effect_type,
                    intent_bytes,
                    intent_fingerprint,
                    horizon,
                    attempt_ceiling,
                ),
            )
            # The procedure selects its result and only then commits, so the row
            # has to be consumed. Closing without reading it cancels the statement
            # and the command is silently lost.
            row = cursor.fetchone()
            if row is None:
                message = "commit_command_v1 returned no result"
                raise RuntimeError(message)
            result_code = str(row[1])
            if result_code != "APPLIED":
                message = f"commit_command_v1 rejected the command: {result_code}"
                raise RuntimeError(message)
            connection.commit()
        finally:
            connection.close()
        return True

    def intent_exists(self, effect_intent_id: str) -> bool:
        """Report whether one intent is already recorded."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT 1 FROM register.effect_status_v1 WHERE effect_intent_id = ?",
                (effect_intent_id,),
            )
            return cursor.fetchone() is not None
        finally:
            connection.close()

    def claim_next(
        self,
        *,
        owning_application: str,
        effect_type: str,
        claimant_id: str,
        lease_seconds: int = 900,
    ) -> ClaimedEffect | None:
        """Claim the oldest intent with no live claim and no receipt, or None.

        The view supplies the candidate; `claim_effect_v1` decides the winner. Two
        workers can read the same candidate, and only one claim succeeds, so the
        race is resolved by the register rather than by the read.
        """
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT TOP 1 effect_intent_id, effect_type FROM register.effect_status_v1"
                " WHERE owning_application = ? AND effect_type = ?"
                "   AND effect_receipt_id IS NULL"
                "   AND (expires_at IS NULL OR expires_at <= SYSUTCDATETIME())"
                "   AND deadline > SYSUTCDATETIME()"
                " ORDER BY effect_intent_id",
                (owning_application, effect_type),
            )
            candidate = cursor.fetchone()
            if candidate is None:
                return None
            intent_id = str(candidate[0])
            cursor.execute(
                "EXEC register.claim_effect_v1 ?, ?, ?",
                (intent_id, claimant_id, lease_seconds),
            )
            claim = cursor.fetchone()
            connection.commit()
            if claim is None:
                return None
            fencing_token = _claim_fencing_token(claim)
            cursor.execute(
                "SELECT intent_bytes, aggregate_id, attempt_ceiling"
                " FROM register.effect_intent_fact WHERE effect_intent_id = ?",
                (intent_id,),
            )
            detail = cursor.fetchone()
        finally:
            connection.close()
        if detail is None:
            return None
        return ClaimedEffect(
            intent_id,
            str(candidate[1]),
            str(detail[1]),
            bytes(detail[0]),
            fencing_token,
            int(detail[2]),
        )

    def record_receipt(
        self,
        *,
        effect_receipt_id: str,
        effect_intent_id: str,
        terminal_status: str,
        attempt_count: int,
        receipt_bytes: bytes,
        receipt_fingerprint: bytes,
        fencing_token: int | None,
        claimant_id: str | None = None,
    ) -> None:
        """Record the terminal outcome of one claimed effect."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.record_effect_receipt_v1 ?, ?, ?, ?, ?, ?, ?, ?",
                (
                    effect_receipt_id,
                    effect_intent_id,
                    terminal_status,
                    attempt_count,
                    receipt_bytes,
                    receipt_fingerprint,
                    claimant_id,
                    fencing_token,
                ),
            )
            connection.commit()
        finally:
            connection.close()


def _claim_fencing_token(row: tuple[object, ...]) -> int:
    """Read the fencing token from a claim result, whatever its column order."""
    for value in row:
        if isinstance(value, int) and value > 0:
            return value
    return 1
