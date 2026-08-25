"""Fingerprint-bound Management Register commands and recovery."""

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import mssql_python

from asklegal_management_register.dbapi import ConnectionFactory
from asklegal_management_register.driver import SqlCredentialError

_RESULT_FIELD_COUNT = 5
_REVIEW_PROJECTION_FIELD_COUNT = 10


class CommandFingerprintMismatch(RuntimeError):
    """An idempotency key was reused with different canonical bytes."""


class AmbiguousCommit(RuntimeError):
    """The database committed but the client did not receive acknowledgement."""


class RegisterProjectionError(RuntimeError):
    """One SQL transport or row-shape failure at a read-only register projection."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Immutable result returned for an original or replayed command."""

    command_id: str
    result_code: str
    result_bytes: bytes
    replayed: bool


@dataclass(frozen=True, slots=True)
class V1CommandResult:
    """Closed M2 command-protocol result with authoritative aggregate version."""

    command_id: str
    result_code: str
    authoritative_version: int | None
    result_bytes: bytes
    replayed: bool


@dataclass(frozen=True, slots=True)
class ReviewReadyProposalRow:
    """One immutable proposal receipt exposed by the least-privilege Review view."""

    proposal_package_id: str
    receipt_bytes: bytes
    receipt_fingerprint: bytes
    authoritative_version: int
    review_ready_at: str
    decision_bytes: bytes | None = None
    decision_fingerprint: bytes | None = None
    review_version: int = 0
    decision_event_type: str | None = None
    decision_at: str | None = None


@dataclass(frozen=True, slots=True)
class RegisterEventCommand:
    """Exact no-effect inputs to the generic M2 command protocol."""

    owning_application: str
    command_id: str
    command_bytes: bytes
    target_id: str
    expected_version: int | None
    expected_absent: bool
    expires_at: str
    winner_key: str | None
    event_id: str
    event_type: str
    event_bytes: bytes


@dataclass(frozen=True, slots=True)
class RegisteredApprovalConsumptionCommand:
    """Exact Promotion-owned inputs to one registered Approval consumption."""

    command_id: str
    command_bytes: bytes
    approval_id: str
    proposal_package_id: str
    decision_fingerprint: bytes
    manifest_id: str
    manifest_fingerprint: str
    execution_lineage_id: str
    expires_at: str
    event_id: str
    event_bytes: bytes


@dataclass(frozen=True, slots=True)
class RegisteredApprovalTerminalCommand:
    """Exact inputs to one registered Approval revocation or invalidation."""

    command_id: str
    command_bytes: bytes
    approval_id: str
    proposal_package_id: str
    decision_fingerprint: bytes
    manifest_id: str
    manifest_fingerprint: str
    expires_at: str
    event_id: str
    event_bytes: bytes


@dataclass(frozen=True, slots=True)
class RegisteredExecutionAuthorizationCommand:
    """Exact inputs to one consumed-Approval execution authorization."""

    command_id: str
    command_bytes: bytes
    approval_id: str
    proposal_package_id: str
    decision_fingerprint: bytes
    manifest_id: str
    manifest_fingerprint: str
    execution_lineage_id: str
    execution_lineage_fingerprint: str
    authorization_fingerprint: str
    expires_at: str
    event_id: str
    event_bytes: bytes


@dataclass(frozen=True, slots=True)
class RegisteredExecutionBeginCommand:
    """Exact inputs to one atomic authorized execution BEGIN and first intent."""

    command_id: str
    command_bytes: bytes
    approval_id: str
    proposal_package_id: str
    decision_fingerprint: bytes
    manifest_id: str
    manifest_fingerprint: str
    execution_lineage_id: str
    execution_lineage_fingerprint: str
    authorization_fingerprint: str
    action_id: str
    action_fingerprint: str
    capability_profile_id: str
    capability_profile_fingerprint: str
    capability_evidence_id: str
    capability_evidence_fingerprint: str
    expires_at: str
    event_id: str
    event_bytes: bytes
    effect_intent_id: str
    effect_type: str
    intent_bytes: bytes
    effect_deadline: str
    attempt_ceiling: int


class RegisterEventStore:
    """Commit ordinary no-effect events and read exact Review-ready proposals."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        """Bind every short command or projection read to a fresh connection."""
        self._connection_factory = connection_factory

    def record_event(self, command: RegisterEventCommand) -> V1CommandResult:
        """Commit one immutable event through the exact generic command protocol."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.commit_command_v1 "
                "@owning_application = ?, @command_id = ?, @command_fingerprint = ?, "
                "@command_bytes = ?, @target_id = ?, @expected_version = ?, "
                "@expected_absent = ?, @expires_at = ?, @guard_result_code = ?, "
                "@winner_key = ?, @event_id = ?, @event_type = ?, "
                "@event_bytes = ?, @event_fingerprint = ?",
                (
                    command.owning_application,
                    command.command_id,
                    sha256(command.command_bytes).digest(),
                    command.command_bytes,
                    command.target_id,
                    command.expected_version,
                    int(command.expected_absent),
                    command.expires_at,
                    "APPLIED",
                    command.winner_key,
                    command.event_id,
                    command.event_type,
                    command.event_bytes,
                    sha256(command.event_bytes).digest(),
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("commit_command_v1 returned no result")
            result = _v1_command_result(row)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        else:
            return result
        finally:
            cursor.close()
            connection.close()

    def review_ready_proposals(self) -> tuple[ReviewReadyProposalRow, ...]:
        """Read immutable proposal receipts without direct fact-table access."""
        try:
            connection = self._connection_factory()
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "SELECT proposal_package_id, receipt_bytes, receipt_fingerprint, "
                    "registration_version, CONVERT(varchar(33), review_ready_at, 127), "
                    "decision_bytes, decision_fingerprint, review_version, "
                    "decision_event_type, CONVERT(varchar(33), decision_at, 127) "
                    "FROM review.proposal_package_review_v1 ORDER BY proposal_package_id"
                )
                return tuple(_review_ready_proposal(row) for row in cursor.fetchall())
            finally:
                cursor.close()
                connection.close()
        except (mssql_python.Error, SqlCredentialError, TypeError, ValueError) as error:
            raise RegisterProjectionError from error


class RegisteredApprovalStore:
    """Consume only the exact approved decision exposed to Promotion."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        """Bind each atomic consumption or replay query to a fresh connection."""
        self._connection_factory = connection_factory

    def consume(
        self,
        command: RegisteredApprovalConsumptionCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Consume one Approval or resolve an acknowledgement lost after commit."""
        command_fingerprint = sha256(command.command_bytes).digest()
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC promotion.consume_registered_approval_v1 "
                "@command_id = ?, @command_fingerprint = ?, @command_bytes = ?, "
                "@approval_id = ?, @proposal_package_id = ?, @decision_fingerprint = ?, "
                "@manifest_id = ?, @manifest_fingerprint = ?, @execution_lineage_id = ?, "
                "@expires_at = ?, @event_id = ?, @event_bytes = ?, @event_fingerprint = ?",
                (
                    command.command_id,
                    command_fingerprint,
                    command.command_bytes,
                    command.approval_id,
                    command.proposal_package_id,
                    command.decision_fingerprint,
                    command.manifest_id,
                    command.manifest_fingerprint,
                    command.execution_lineage_id,
                    command.expires_at,
                    command.event_id,
                    command.event_bytes,
                    sha256(command.event_bytes).digest(),
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("consume_registered_approval_v1 returned no result")
            result = _v1_command_result(row)
            connection.commit()
            if simulate_lost_ack:
                raise AmbiguousCommit(command.command_id)
        except Exception as error:
            try:
                connection.rollback()
            except Exception:
                pass
            if isinstance(error, AmbiguousCommit):
                return self.resolve(command.command_id, command_fingerprint)
            if _is_fingerprint_mismatch(error):
                raise CommandFingerprintMismatch(command.command_id) from error
            raise
        else:
            return result
        finally:
            cursor.close()
            connection.close()

    def resolve(self, command_id: str, command_fingerprint: bytes) -> V1CommandResult:
        """Resolve one uncertain Promotion command without repeating consumption."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.resolve_command_v1 ?, ?, ?",
                ("PROMOTION_WORKER", command_id, command_fingerprint),
            )
            row = cursor.fetchone()
            if row is None:
                raise AmbiguousCommit(command_id)
            return _v1_command_result(row)
        finally:
            cursor.close()
            connection.close()


class RegisteredApprovalLifecycleStore:
    """Record guarded terminal Approval lifecycle events without effects."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        """Bind each lifecycle command or replay query to a fresh connection."""
        self._connection_factory = connection_factory

    def revoke(
        self,
        command: RegisteredApprovalTerminalCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Revoke one exact registered Approval as the Review application."""
        return self._record(
            command,
            owning_application="REVIEW_APPLICATION",
            invalidate=False,
            simulate_lost_ack=simulate_lost_ack,
        )

    def invalidate(
        self,
        command: RegisteredApprovalTerminalCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Invalidate one exact registered Approval as the Promotion worker."""
        return self._record(
            command,
            owning_application="PROMOTION_WORKER",
            invalidate=True,
            simulate_lost_ack=simulate_lost_ack,
        )

    def _record(
        self,
        command: RegisteredApprovalTerminalCommand,
        *,
        owning_application: str,
        invalidate: bool,
        simulate_lost_ack: bool,
    ) -> V1CommandResult:
        command_fingerprint = sha256(command.command_bytes).digest()
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            statement = (
                "EXEC promotion.invalidate_registered_approval_v1 "
                if invalidate
                else "EXEC review.revoke_registered_approval_v1 "
            )
            cursor.execute(
                statement + "@command_id = ?, @command_fingerprint = ?, @command_bytes = ?, "
                "@approval_id = ?, @proposal_package_id = ?, @decision_fingerprint = ?, "
                "@manifest_id = ?, @manifest_fingerprint = ?, @expires_at = ?, "
                "@event_id = ?, @event_bytes = ?, @event_fingerprint = ?",
                (
                    command.command_id,
                    command_fingerprint,
                    command.command_bytes,
                    command.approval_id,
                    command.proposal_package_id,
                    command.decision_fingerprint,
                    command.manifest_id,
                    command.manifest_fingerprint,
                    command.expires_at,
                    command.event_id,
                    command.event_bytes,
                    sha256(command.event_bytes).digest(),
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("registered Approval lifecycle procedure returned no result")
            result = _v1_command_result(row)
            connection.commit()
            if simulate_lost_ack:
                raise AmbiguousCommit(command.command_id)
        except Exception as error:
            try:
                connection.rollback()
            except Exception:
                pass
            if isinstance(error, AmbiguousCommit):
                return self.resolve(
                    owning_application,
                    command.command_id,
                    command_fingerprint,
                )
            if _is_fingerprint_mismatch(error):
                raise CommandFingerprintMismatch(command.command_id) from error
            raise
        else:
            return result
        finally:
            cursor.close()
            connection.close()

    def resolve(
        self,
        owning_application: str,
        command_id: str,
        command_fingerprint: bytes,
    ) -> V1CommandResult:
        """Resolve one uncertain terminal lifecycle command without repeating it."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.resolve_command_v1 ?, ?, ?",
                (owning_application, command_id, command_fingerprint),
            )
            row = cursor.fetchone()
            if row is None:
                raise AmbiguousCommit(command_id)
            return _v1_command_result(row)
        finally:
            cursor.close()
            connection.close()


class RegisteredExecutionAuthorizationStore:
    """Authorize one exact consumed-Approval execution without an Effect Intent."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        """Bind each authorization or replay query to a fresh connection."""
        self._connection_factory = connection_factory

    def authorize(
        self,
        command: RegisteredExecutionAuthorizationCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Authorize one execution lineage or resolve an acknowledgement loss."""
        command_fingerprint = sha256(command.command_bytes).digest()
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC promotion.authorize_registered_execution_v1 "
                "@command_id = ?, @command_fingerprint = ?, @command_bytes = ?, "
                "@approval_id = ?, @proposal_package_id = ?, @decision_fingerprint = ?, "
                "@manifest_id = ?, @manifest_fingerprint = ?, @execution_lineage_id = ?, "
                "@execution_lineage_fingerprint = ?, @authorization_fingerprint = ?, "
                "@expires_at = ?, @event_id = ?, @event_bytes = ?, "
                "@event_fingerprint = ?",
                (
                    command.command_id,
                    command_fingerprint,
                    command.command_bytes,
                    command.approval_id,
                    command.proposal_package_id,
                    command.decision_fingerprint,
                    command.manifest_id,
                    command.manifest_fingerprint,
                    command.execution_lineage_id,
                    command.execution_lineage_fingerprint,
                    command.authorization_fingerprint,
                    command.expires_at,
                    command.event_id,
                    command.event_bytes,
                    sha256(command.event_bytes).digest(),
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("authorize_registered_execution_v1 returned no result")
            result = _v1_command_result(row)
            connection.commit()
            if simulate_lost_ack:
                raise AmbiguousCommit(command.command_id)
        except Exception as error:
            try:
                connection.rollback()
            except Exception:
                pass
            if isinstance(error, AmbiguousCommit):
                return self.resolve(command.command_id, command_fingerprint)
            if _is_fingerprint_mismatch(error):
                raise CommandFingerprintMismatch(command.command_id) from error
            raise
        else:
            return result
        finally:
            cursor.close()
            connection.close()

    def resolve(self, command_id: str, command_fingerprint: bytes) -> V1CommandResult:
        """Resolve one uncertain execution authorization without resubmitting it."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.resolve_command_v1 ?, ?, ?",
                ("PROMOTION_WORKER", command_id, command_fingerprint),
            )
            row = cursor.fetchone()
            if row is None:
                raise AmbiguousCommit(command_id)
            return _v1_command_result(row)
        finally:
            cursor.close()
            connection.close()


class RegisteredExecutionBeginStore:
    """Atomically begin one authorized execution and append its first intent."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        """Bind each BEGIN or replay query to a fresh connection."""
        self._connection_factory = connection_factory

    def begin(
        self,
        command: RegisteredExecutionBeginCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Begin exactly once or resolve an acknowledgement loss by command ID."""
        command_fingerprint = sha256(command.command_bytes).digest()
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC promotion.begin_registered_execution_v1 "
                "@command_id = ?, @command_fingerprint = ?, @command_bytes = ?, "
                "@approval_id = ?, @proposal_package_id = ?, @decision_fingerprint = ?, "
                "@manifest_id = ?, @manifest_fingerprint = ?, @execution_lineage_id = ?, "
                "@execution_lineage_fingerprint = ?, @authorization_fingerprint = ?, "
                "@action_id = ?, @action_fingerprint = ?, @capability_profile_id = ?, "
                "@capability_profile_fingerprint = ?, @capability_evidence_id = ?, "
                "@capability_evidence_fingerprint = ?, @expires_at = ?, @event_id = ?, "
                "@event_bytes = ?, @event_fingerprint = ?, @effect_intent_id = ?, "
                "@effect_type = ?, @intent_bytes = ?, @intent_fingerprint = ?, "
                "@effect_deadline = ?, @attempt_ceiling = ?",
                (
                    command.command_id,
                    command_fingerprint,
                    command.command_bytes,
                    command.approval_id,
                    command.proposal_package_id,
                    command.decision_fingerprint,
                    command.manifest_id,
                    command.manifest_fingerprint,
                    command.execution_lineage_id,
                    command.execution_lineage_fingerprint,
                    command.authorization_fingerprint,
                    command.action_id,
                    command.action_fingerprint,
                    command.capability_profile_id,
                    command.capability_profile_fingerprint,
                    command.capability_evidence_id,
                    command.capability_evidence_fingerprint,
                    command.expires_at,
                    command.event_id,
                    command.event_bytes,
                    sha256(command.event_bytes).digest(),
                    command.effect_intent_id,
                    command.effect_type,
                    command.intent_bytes,
                    sha256(command.intent_bytes).digest(),
                    command.effect_deadline,
                    command.attempt_ceiling,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("begin_registered_execution_v1 returned no result")
            result = _v1_command_result(row)
            connection.commit()
            if simulate_lost_ack:
                raise AmbiguousCommit(command.command_id)
        except Exception as error:
            try:
                connection.rollback()
            except Exception:
                pass
            if isinstance(error, AmbiguousCommit):
                return self.resolve(command.command_id, command_fingerprint)
            if _is_fingerprint_mismatch(error):
                raise CommandFingerprintMismatch(command.command_id) from error
            raise
        else:
            return result
        finally:
            cursor.close()
            connection.close()

    def resolve(self, command_id: str, command_fingerprint: bytes) -> V1CommandResult:
        """Resolve one uncertain execution BEGIN without resubmitting it."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.resolve_command_v1 ?, ?, ?",
                ("PROMOTION_WORKER", command_id, command_fingerprint),
            )
            row = cursor.fetchone()
            if row is None:
                raise AmbiguousCommit(command_id)
            return _v1_command_result(row)
        finally:
            cursor.close()
            connection.close()


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


def _v1_command_result(row: tuple[object, ...]) -> V1CommandResult:
    if len(row) != _RESULT_FIELD_COUNT:
        raise TypeError("V1 command result must contain five fields")
    command_id, result_code, authoritative_version, result_bytes, replayed = row
    if not isinstance(command_id, str) or not isinstance(result_code, str):
        raise TypeError("V1 command identity and result must be text")
    if authoritative_version is not None and not isinstance(authoritative_version, int):
        raise TypeError("V1 command version must be integer or null")
    if not isinstance(result_bytes, bytes) or not isinstance(replayed, bool | int):
        raise TypeError("V1 command result payload is malformed")
    return V1CommandResult(
        command_id,
        result_code,
        authoritative_version,
        result_bytes,
        bool(replayed),
    )


def _review_ready_proposal(row: tuple[object, ...]) -> ReviewReadyProposalRow:
    if len(row) != _REVIEW_PROJECTION_FIELD_COUNT:
        message = "Review-ready proposal row must contain ten fields"
        raise TypeError(message)
    (
        package_id,
        receipt_bytes,
        receipt_fingerprint,
        version,
        recorded_at,
        decision_bytes,
        decision_fingerprint,
        review_version,
        decision_event_type,
        decision_at,
    ) = row
    if (
        not isinstance(package_id, str)
        or not isinstance(receipt_bytes, bytes)
        or not isinstance(receipt_fingerprint, bytes)
        or not isinstance(version, int)
        or not isinstance(recorded_at, str)
        or (decision_bytes is not None and not isinstance(decision_bytes, bytes))
        or (decision_fingerprint is not None and not isinstance(decision_fingerprint, bytes))
        or not isinstance(review_version, int)
        or (decision_event_type is not None and not isinstance(decision_event_type, str))
        or (decision_at is not None and not isinstance(decision_at, str))
        or ((decision_bytes is None) != (decision_fingerprint is None))
        or ((decision_bytes is None) != (decision_event_type is None))
        or ((decision_bytes is None) != (decision_at is None))
        or (decision_bytes is None and review_version != 0)
        or (decision_bytes is not None and review_version != 1)
    ):
        raise TypeError("Review-ready proposal row is malformed")
    return ReviewReadyProposalRow(
        package_id,
        receipt_bytes,
        receipt_fingerprint,
        version,
        recorded_at,
        decision_bytes,
        decision_fingerprint,
        review_version,
        decision_event_type,
        decision_at,
    )


def _is_deadlock(error: Exception) -> bool:
    return "1205" in str(error).lower() or "deadlock" in str(error).lower()


def _required_bytes(value: object, field: str) -> bytes:
    if not isinstance(value, bytes):
        message = f"{field} is not bytes"
        raise TypeError(message)
    return value


def _required_int(value: object, field: str) -> int:
    if not isinstance(value, int):
        message = f"{field} is not an integer"
        raise TypeError(message)
    return value


def _is_fingerprint_mismatch(error: Exception) -> bool:
    return "ASKLEGAL_COMMAND_FINGERPRINT_MISMATCH" in str(error)


@dataclass(frozen=True, slots=True)
class ClaimedEffect:
    """One effect intent this claimant now holds under a fencing token."""

    effect_intent_id: str
    effect_type: str
    aggregate_id: str
    intent_bytes: bytes
    intent_fingerprint: bytes
    claimant_id: str
    fencing_token: int
    attempt_ceiling: int
    prior_attempt_count: int


@dataclass(frozen=True, slots=True)
class RecordedEffectReceipt:
    """One terminal receipt selected by the register, original or replayed."""

    effect_receipt_id: str
    effect_intent_id: str
    terminal_status: str
    attempt_count: int
    receipt_bytes: bytes
    fencing_token: int | None
    replayed: bool


@dataclass(frozen=True, slots=True)
class EffectReceiptRecord:
    """Exact terminal-receipt arguments supplied to the register."""

    effect_receipt_id: str
    effect_intent_id: str
    terminal_status: str
    attempt_count: int
    receipt_bytes: bytes
    receipt_fingerprint: bytes
    fencing_token: int | None
    claimant_id: str | None = None


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
            fencing_token = _required_int(claim[3], "fencing_token")
            cursor.execute(
                "EXEC register.read_claimed_effect_v1 ?, ?, ?",
                (intent_id, claimant_id, fencing_token),
            )
            detail = cursor.fetchone()
        finally:
            connection.close()
        if detail is None:
            return None
        detail_intent_id = str(detail[0])
        detail_effect_type = str(detail[1])
        intent_bytes = _required_bytes(detail[3], "intent_bytes")
        intent_fingerprint = _required_bytes(detail[4], "intent_fingerprint")
        if (
            detail_intent_id != intent_id
            or detail_effect_type != str(candidate[1])
            or sha256(intent_bytes).digest() != intent_fingerprint
        ):
            message = "claimed effect detail does not match its immutable listing"
            raise RuntimeError(message)
        return ClaimedEffect(
            detail_intent_id,
            detail_effect_type,
            str(detail[2]),
            intent_bytes,
            intent_fingerprint,
            claimant_id,
            fencing_token,
            _required_int(detail[5], "attempt_ceiling"),
            _required_int(detail[6], "prior_attempt_count"),
        )

    def renew_claim(self, claim: ClaimedEffect, *, lease_seconds: int = 900) -> None:
        """Renew only the exact still-live claimant and fencing token."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.renew_effect_claim_v1 ?, ?, ?, ?",
                (
                    claim.effect_intent_id,
                    claim.claimant_id,
                    claim.fencing_token,
                    lease_seconds,
                ),
            )
            if cursor.fetchone() is None:
                message = "renew_effect_claim_v1 returned no result"
                raise RuntimeError(message)
            connection.commit()
        finally:
            cursor.close()
            connection.close()

    def append_attempt(
        self,
        claim: ClaimedEffect,
        *,
        attempt_number: int,
        event_code: str,
        event_bytes: bytes,
    ) -> None:
        """Append one sanitized attempt under the exact live fence."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.append_effect_attempt_v1 ?, ?, ?, ?, ?, ?, ?",
                (
                    claim.effect_intent_id,
                    claim.claimant_id,
                    claim.fencing_token,
                    attempt_number,
                    event_code,
                    event_bytes,
                    sha256(event_bytes).digest(),
                ),
            )
            connection.commit()
        finally:
            cursor.close()
            connection.close()

    def record_receipt(
        self,
        record: EffectReceiptRecord,
    ) -> RecordedEffectReceipt:
        """Record or exactly replay one terminal outcome and consume its result."""
        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "EXEC register.record_effect_receipt_v1 ?, ?, ?, ?, ?, ?, ?, ?",
                (
                    record.effect_receipt_id,
                    record.effect_intent_id,
                    record.terminal_status,
                    record.attempt_count,
                    record.receipt_bytes,
                    record.receipt_fingerprint,
                    record.claimant_id,
                    record.fencing_token,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                message = "record_effect_receipt_v1 returned no result"
                raise RuntimeError(message)
            connection.commit()
            return RecordedEffectReceipt(
                str(row[0]),
                str(row[1]),
                str(row[2]),
                _required_int(row[3], "attempt_count"),
                _required_bytes(row[4], "receipt_bytes"),
                row[5] if isinstance(row[5], int) else None,
                bool(row[6]),
            )
        finally:
            cursor.close()
            connection.close()
