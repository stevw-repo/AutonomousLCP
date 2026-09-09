"""Fingerprint-bound Management Register commands and recovery."""

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import mssql_python

from asklegal_management_register.dbapi import ConnectionFactory
from asklegal_management_register.driver import SqlCredentialError

_RESULT_FIELD_COUNT = 5
_REVIEW_PROJECTION_FIELD_COUNT = 10
_APPROVED_PROMOTION_CLAIM_FIELD_COUNT = 9
_APPROVED_PROMOTION_ACKNOWLEDGEMENT_FIELD_COUNT = 3
_SERVING_STATE_RECEIPT_FIELD_COUNT = 6
_SHA256_BYTE_LENGTH = 32
_UTC_FRACTION_START = 20
_UTC_TIMESTAMP_SECONDS_LENGTH = 19
_SQL_DATETIME2_FRACTION_DIGITS = 7
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_SERVING_TARGET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
_SAFE_SQL_ERROR_CODE = re.compile(r"\bASKLEGAL_[A-Z0-9_]+\b")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?Z$")


class CommandFingerprintMismatch(RuntimeError):
    """An idempotency key was reused with different canonical bytes."""


class AmbiguousCommit(RuntimeError):
    """The database committed but the client did not receive acknowledgement."""


class RegisterProjectionError(RuntimeError):
    """One SQL transport or row-shape failure at a read-only register projection."""


class ServingStateVerificationError(RegisterProjectionError):
    """One narrow post-activation state mismatch eligible for exact rollback."""


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


@dataclass(frozen=True, slots=True)
class ApprovedPromotionClaim:
    """One Promotion-owned, lease-only wake-up claim for an approved decision."""

    proposal_package_id: str
    approval_id: str
    decision_fingerprint: str
    manifest_id: str
    manifest_fingerprint: str
    claimant_worker_id: str
    claimed_until: str
    generation: int
    fencing_token: int


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


class ApprovedPromotionQueueStore:
    """Claim or acknowledge Promotion wake-up leases without execution authority."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        """Use one fresh connection for each short queue stored procedure."""
        self._connection_factory = connection_factory

    def claim_next(self, worker_id: str, claimed_until: str) -> ApprovedPromotionClaim | None:
        """Lease one already-approved decision without consuming its Approval."""
        try:
            if not _registered_identifier(worker_id, "pwr"):
                raise TypeError("approved Promotion worker identifier is malformed")
            normalized_claimed_until = _normalized_utc_timestamp(claimed_until)
            connection = self._connection_factory()
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "EXEC promotion.claim_next_approved_promotion_v1 "
                    "@worker_id = ?, @claimed_until = ?",
                    (worker_id, normalized_claimed_until),
                )
                row = cursor.fetchone()
                if row is None:
                    claim = None
                else:
                    claim = _approved_promotion_claim(
                        row,
                        expected_worker_id=worker_id,
                        expected_claimed_until=normalized_claimed_until,
                    )
                    if cursor.fetchall():
                        raise TypeError("approved Promotion claim returned multiple rows")
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()
                return claim
            finally:
                cursor.close()
                connection.close()
        except Exception as error:
            raise _register_projection_error(error) from None

    def acknowledge_started(self, claim: ApprovedPromotionClaim, execution_lineage_id: str) -> None:
        """Record only an existing matching durable Approval-consumption lineage."""
        try:
            decision_fingerprint, normalized_claimed_until = _validated_approved_promotion_claim(
                claim
            )
            if not _registered_identifier(execution_lineage_id, "exe"):
                raise TypeError("approved Promotion execution lineage is malformed")
            connection = self._connection_factory()
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "EXEC promotion.acknowledge_approved_promotion_started_v1 "
                    "@approval_id = ?, @proposal_package_id = ?, @decision_fingerprint = ?, "
                    "@manifest_id = ?, @manifest_fingerprint = ?, @worker_id = ?, "
                    "@claimed_until = ?, @generation = ?, @fencing_token = ?, "
                    "@execution_lineage_id = ?",
                    (
                        claim.approval_id,
                        claim.proposal_package_id,
                        decision_fingerprint,
                        claim.manifest_id,
                        claim.manifest_fingerprint,
                        claim.claimant_worker_id,
                        normalized_claimed_until,
                        claim.generation,
                        claim.fencing_token,
                        execution_lineage_id,
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    raise TypeError("approved promotion acknowledgement returned no result")
                _approved_promotion_acknowledgement(row, claim, execution_lineage_id)
                if cursor.fetchall():
                    raise TypeError("approved Promotion acknowledgement returned multiple rows")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()
                connection.close()
        except (mssql_python.Error, SqlCredentialError, TypeError, ValueError) as error:
            raise _register_projection_error(error) from None


@dataclass(frozen=True, slots=True)
class ServingStateCandidate:
    """Exact V1 candidate supplied to the Promotion-only SQL procedure."""

    state_id: str
    state_fingerprint: str
    predecessor_state_id: str
    target_name: str
    desired_inventory_fingerprint: str
    coverage_fingerprint: str
    embedding_profile_id: str
    embedding_profile_fingerprint: str
    approval_id: str
    execution_lineage_id: str


@dataclass(frozen=True, slots=True)
class ServingStateReceipt:
    """One SQL-returned immutable Serving State lifecycle receipt."""

    receipt_id: str
    operation: str
    predecessor_state_id: str
    state_id: str
    candidate_fingerprint: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class _ServingStateExpectation:
    """Exact request fields the adapter requires a procedure to echo."""

    operation: str
    predecessor_state_id: str
    state_id: str
    state_fingerprint: str | None
    receipt_id: str


class ServingStateStore:
    """Promotion-only SQL adapter for V1 Management Register Serving State."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        """Bind one fresh-connection factory for short state procedures."""
        self._connection_factory = connection_factory

    @property
    def active_state_id(self) -> str:
        """Read the current V1 state through its Promotion-owned procedure."""
        return self._read_state()

    def activate(self, expected_base: str, candidate: ServingStateCandidate) -> ServingStateReceipt:
        """Compare-and-set one complete verified candidate state."""
        try:
            _validate_serving_state_candidate(expected_base, candidate)
            receipt_id = _activation_receipt_id(expected_base, candidate)
        except Exception:
            raise RegisterProjectionError("ASKLEGAL_REGISTER_PROJECTION_FAILED") from None
        return self._transition(
            "promotion.activate_serving_state_v1",
            (
                expected_base,
                candidate.state_id,
                candidate.state_fingerprint,
                candidate.predecessor_state_id,
                candidate.target_name,
                candidate.desired_inventory_fingerprint,
                candidate.coverage_fingerprint,
                candidate.embedding_profile_id,
                candidate.embedding_profile_fingerprint,
                candidate.approval_id,
                candidate.execution_lineage_id,
            ),
            _ServingStateExpectation(
                "ACTIVATED",
                expected_base,
                candidate.state_id,
                candidate.state_fingerprint,
                receipt_id,
            ),
        )

    def verify(self, candidate_state_id: str) -> None:
        """Fail visibly if the current Register state differs after activation."""
        if not _serving_state_id(candidate_state_id):
            raise RegisterProjectionError("ASKLEGAL_REGISTER_PROJECTION_FAILED")
        actual = self._read_state()
        if actual != candidate_state_id:
            raise ServingStateVerificationError("ASKLEGAL_SERVING_STATE_POST_ACTIVATION_DRIFT")

    def rollback(
        self, candidate: ServingStateCandidate, activation_receipt_id: str
    ) -> ServingStateReceipt:
        """Append or replay the exact reversal of one active activation fact."""
        try:
            _validate_serving_state_candidate(candidate.predecessor_state_id, candidate)
            if not _serving_state_receipt_id(activation_receipt_id):
                raise TypeError("activation receipt is malformed")
            receipt_id = _rollback_receipt_id(activation_receipt_id, candidate)
        except Exception:
            raise RegisterProjectionError("ASKLEGAL_REGISTER_PROJECTION_FAILED") from None
        return self._transition(
            "promotion.rollback_serving_state_v1",
            (candidate.state_id, candidate.predecessor_state_id, activation_receipt_id),
            _ServingStateExpectation(
                "ROLLED_BACK",
                candidate.state_id,
                candidate.predecessor_state_id,
                candidate.state_fingerprint,
                receipt_id,
            ),
        )

    def _read_state(self) -> str:
        try:
            connection = self._connection_factory()
            cursor = connection.cursor()
            try:
                cursor.execute("EXEC promotion.read_serving_state_v1")
                row = cursor.fetchone()
                if (
                    row is None
                    or len(row) != 1
                    or not isinstance(row[0], str)
                    or not _serving_state_id(row[0])
                ):
                    raise TypeError("Serving State read row is malformed")
                if cursor.fetchall():
                    raise TypeError("Serving State read returned multiple rows")
                connection.commit()
                return row[0]
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()
                connection.close()
        except Exception as error:
            raise _register_projection_error(error) from None

    def _transition(
        self,
        procedure: str,
        parameters: tuple[str, ...],
        expectation: _ServingStateExpectation,
    ) -> ServingStateReceipt:
        try:
            connection = self._connection_factory()
            cursor = connection.cursor()
            try:
                cursor.execute(f"EXEC {procedure} {', '.join('?' for _ in parameters)}", parameters)
                receipt = _serving_state_receipt(cursor.fetchone(), expectation)
                if cursor.fetchall():
                    raise TypeError("Serving State transition returned multiple rows")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            else:
                return receipt
            finally:
                cursor.close()
                connection.close()
        except Exception as error:
            raise _register_projection_error(error) from None


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


def _approved_promotion_claim(
    row: tuple[object, ...], *, expected_worker_id: str, expected_claimed_until: str
) -> ApprovedPromotionClaim:
    """Decode the closed wake-up row without inferring any execution authority."""
    if len(row) != _APPROVED_PROMOTION_CLAIM_FIELD_COUNT:
        raise TypeError("approved Promotion claim row must contain nine fields")
    (
        proposal_package_id,
        approval_id,
        decision_fingerprint,
        manifest_id,
        manifest_fingerprint,
        claimant_worker_id,
        claimed_until,
        generation,
        fencing_token,
    ) = row
    if (
        not isinstance(proposal_package_id, str)
        or not isinstance(approval_id, str)
        or not isinstance(decision_fingerprint, bytes)
        or len(decision_fingerprint) != _SHA256_BYTE_LENGTH
        or not isinstance(manifest_id, str)
        or not isinstance(manifest_fingerprint, str)
        or not isinstance(claimant_worker_id, str)
        or not isinstance(claimed_until, str)
        or not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
        or not isinstance(fencing_token, int)
        or isinstance(fencing_token, bool)
        or fencing_token < 1
        or not _registered_identifier(proposal_package_id, "ppk")
        or not _registered_identifier(approval_id, "apr")
        or not _registered_identifier(manifest_id, "pmn")
        or _FINGERPRINT.fullmatch(manifest_fingerprint) is None
        or not _registered_identifier(claimant_worker_id, "pwr")
        or not _utc_timestamp(claimed_until)
        or claimant_worker_id != expected_worker_id
        or claimed_until != expected_claimed_until
    ):
        raise TypeError("approved Promotion claim row is malformed")
    return ApprovedPromotionClaim(
        proposal_package_id,
        approval_id,
        f"sha256:{decision_fingerprint.hex()}",
        manifest_id,
        manifest_fingerprint,
        claimant_worker_id,
        claimed_until,
        generation,
        fencing_token,
    )


def _registered_identifier(value: str, prefix: str) -> bool:
    """Recognize one stable lower-case register identifier without coercion."""
    return re.fullmatch(rf"{prefix}_[0-9a-f]{{48}}", value) is not None


def _utc_timestamp(value: str) -> bool:
    """Recognize an exact UTC timestamp that SQL can round-trip safely."""
    if _UTC_TIMESTAMP.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is UTC


def _normalized_utc_timestamp(value: object) -> str:
    """Canonicalize one SQL datetime2 UTC input before crossing the boundary."""
    if not isinstance(value, str) or not _utc_timestamp(value):
        raise TypeError("approved Promotion timestamp is malformed")
    fraction = value[_UTC_FRACTION_START:-1] if len(value) > _UTC_FRACTION_START else ""
    return (
        f"{value[:_UTC_TIMESTAMP_SECONDS_LENGTH]}."
        f"{fraction.ljust(_SQL_DATETIME2_FRACTION_DIGITS, '0')}Z"
    )


def _validated_approved_promotion_claim(claim: ApprovedPromotionClaim) -> tuple[bytes, str]:
    """Validate every public claim fact before lossy SQL binary conversion."""
    values: tuple[object, object, object, object, object, object, object, object, object] = (
        _runtime_value(claim.proposal_package_id),
        _runtime_value(claim.approval_id),
        _runtime_value(claim.decision_fingerprint),
        _runtime_value(claim.manifest_id),
        _runtime_value(claim.manifest_fingerprint),
        _runtime_value(claim.claimant_worker_id),
        _runtime_value(claim.claimed_until),
        _runtime_value(claim.generation),
        _runtime_value(claim.fencing_token),
    )
    (
        proposal_package_id,
        approval_id,
        decision_fingerprint,
        manifest_id,
        manifest_fingerprint,
        claimant_worker_id,
        claimed_until,
        generation,
        fencing_token,
    ) = values
    if (
        not isinstance(proposal_package_id, str)
        or not _registered_identifier(proposal_package_id, "ppk")
        or not isinstance(approval_id, str)
        or not _registered_identifier(approval_id, "apr")
        or not isinstance(decision_fingerprint, str)
        or _FINGERPRINT.fullmatch(decision_fingerprint) is None
        or not isinstance(manifest_id, str)
        or not _registered_identifier(manifest_id, "pmn")
        or not isinstance(manifest_fingerprint, str)
        or _FINGERPRINT.fullmatch(manifest_fingerprint) is None
        or not isinstance(claimant_worker_id, str)
        or not _registered_identifier(claimant_worker_id, "pwr")
        or not isinstance(claimed_until, str)
        or not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
        or not isinstance(fencing_token, int)
        or isinstance(fencing_token, bool)
        or fencing_token < 1
    ):
        raise TypeError("approved Promotion claim is malformed")
    return (
        bytes.fromhex(decision_fingerprint.removeprefix("sha256:")),
        _normalized_utc_timestamp(claimed_until),
    )


def _runtime_value(value: object) -> object:
    """Forget static dataclass types before validating public runtime inputs."""
    return value


def _register_projection_error(error: Exception) -> RegisterProjectionError:
    """Expose one safe SQL code while suppressing arbitrary driver diagnostics."""
    match = _SAFE_SQL_ERROR_CODE.search(str(error))
    return RegisterProjectionError(
        match.group(0) if match is not None else "ASKLEGAL_REGISTER_PROJECTION_FAILED"
    )


def _approved_promotion_acknowledgement(
    row: tuple[object, ...], claim: ApprovedPromotionClaim, execution_lineage_id: str
) -> None:
    """Require the procedure to echo the exact pre-existing consumption lineage."""
    if len(row) != _APPROVED_PROMOTION_ACKNOWLEDGEMENT_FIELD_COUNT:
        raise TypeError("approved Promotion acknowledgement row must contain three fields")
    approval_id, returned_lineage_id, returned_fence = row
    if (
        not isinstance(approval_id, str)
        or not isinstance(returned_lineage_id, str)
        or not isinstance(returned_fence, int)
        or isinstance(returned_fence, bool)
        or approval_id != claim.approval_id
        or returned_lineage_id != execution_lineage_id
        or returned_fence != claim.fencing_token
    ):
        raise TypeError("approved Promotion acknowledgement row is malformed")


def _serving_state_receipt(
    row: tuple[object, ...] | None,
    expected: _ServingStateExpectation,
) -> ServingStateReceipt:
    """Require one complete closed state-transition receipt row."""
    if row is None or len(row) != _SERVING_STATE_RECEIPT_FIELD_COUNT:
        raise TypeError("Serving State transition returned no complete receipt")
    receipt_id, operation, predecessor, state_id, fingerprint, replayed = row
    if not isinstance(replayed, int) or replayed not in {0, 1}:
        raise TypeError("Serving State transition receipt is malformed")
    if (
        operation != expected.operation
        or predecessor != expected.predecessor_state_id
        or state_id != expected.state_id
        or (expected.state_fingerprint is not None and fingerprint != expected.state_fingerprint)
        or not isinstance(receipt_id, str)
        or receipt_id != expected.receipt_id
    ):
        raise TypeError("Serving State transition receipt does not match request")
    return ServingStateReceipt(
        _required_text(receipt_id, "Serving State receipt ID"),
        _required_text(operation, "Serving State receipt operation"),
        _required_text(predecessor, "Serving State receipt predecessor"),
        _required_text(state_id, "Serving State receipt state"),
        _required_text(fingerprint, "Serving State receipt fingerprint"),
        bool(replayed),
    )


def _serving_state_id(value: str) -> bool:
    """Require one closed lower-hex Serving State identity."""
    return bool(re.fullmatch(r"srv_[0-9a-f]{48}", value))


def _serving_state_receipt_id(value: str) -> bool:
    """Require the exact SQL Server SHA-256 lifecycle receipt representation."""
    return bool(re.fullmatch(r"ssr_[0-9a-f]{64}", value))


def _activation_receipt_id(expected_base: str, candidate: ServingStateCandidate) -> str:
    """Mirror the procedure's canonical all-material activation receipt identity."""
    values = (
        expected_base,
        candidate.state_id,
        candidate.state_fingerprint,
        candidate.target_name,
        candidate.desired_inventory_fingerprint,
        candidate.coverage_fingerprint,
        candidate.embedding_profile_id,
        candidate.embedding_profile_fingerprint,
        candidate.approval_id,
        candidate.execution_lineage_id,
    )
    return f"ssr_{sha256('|'.join(values).encode()).hexdigest()}"


def _rollback_receipt_id(activation_receipt_id: str, candidate: ServingStateCandidate) -> str:
    """Mirror the procedure's exact activation-bound rollback receipt identity."""
    raw = f"rollback|{activation_receipt_id}|{candidate.state_id}|{candidate.predecessor_state_id}"
    return f"ssr_{sha256(raw.encode()).hexdigest()}"


def _validate_serving_state_candidate(expected_base: str, candidate: ServingStateCandidate) -> None:
    """Reject malformed or internally inconsistent candidate facts before SQL."""
    identifiers = (
        (expected_base, "srv_"),
        (candidate.state_id, "srv_"),
        (candidate.predecessor_state_id, "srv_"),
        (candidate.embedding_profile_id, "emp_"),
        (candidate.approval_id, "apr_"),
        (candidate.execution_lineage_id, "exe_"),
    )
    if (
        candidate.predecessor_state_id != expected_base
        or any(
            not _registered_identifier(value, prefix.removesuffix("_"))
            for value, prefix in identifiers
        )
        or any(
            _FINGERPRINT.fullmatch(value) is None
            for value in (
                candidate.state_fingerprint,
                candidate.desired_inventory_fingerprint,
                candidate.coverage_fingerprint,
                candidate.embedding_profile_fingerprint,
            )
        )
        or type(candidate.target_name) is not str
        or _SERVING_TARGET_NAME.fullmatch(candidate.target_name) is None
    ):
        raise TypeError("Serving State candidate is malformed")


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


def _required_text(value: object, field: str) -> str:
    """Return a non-empty text field from one closed SQL procedure row."""
    if not isinstance(value, str) or not value:
        message = f"{field} is not non-empty text"
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
