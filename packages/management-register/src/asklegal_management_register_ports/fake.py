"""Deterministic, thread-safe in-memory implementation of the M2 register port."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import RLock

from asklegal_domain import (
    ApplicationCode,
    CommandResult,
    CommandResultCode,
    CommandSubmissionResolutionCode,
    EffectIntent,
    EffectReceipt,
    EffectReceiptStatus,
    ExpectedVersion,
    ImmutableReference,
    ReferenceType,
)

from .model import (
    CommandIdentityConflict,
    CommandSubmission,
    CommandTransaction,
    EffectAttemptEvent,
    EffectClaim,
    EffectClaimConflict,
    PolicyState,
    ProjectionRow,
    RecoveryDigestMismatch,
    RecoveryPackage,
    RegisterEvent,
    RegisterInvariantError,
    RegisterSnapshot,
    StaleFencingToken,
)


@dataclass(frozen=True, slots=True)
class _StoredCommand:
    transaction: CommandTransaction
    submission: CommandSubmission


class InMemoryManagementRegister:
    """One atomic behavioral reference model with no infrastructure effects."""

    def __init__(self) -> None:
        """Create one empty writable register."""
        self._lock = RLock()
        self._commands: dict[str, _StoredCommand] = {}
        self._events: list[RegisterEvent] = []
        self._intents: dict[str, EffectIntent] = {}
        self._claims: dict[str, EffectClaim] = {}
        self._attempts: list[EffectAttemptEvent] = []
        self._receipts: dict[str, EffectReceipt] = {}
        self._policies: list[PolicyState] = []
        self._aggregate_versions: dict[str, int] = {}
        self._winners: dict[str, str] = {}
        self._projections: dict[str, ProjectionRow] = {}

    @property
    def events(self) -> tuple[RegisterEvent, ...]:
        """Expose immutable event facts for conformance assertions."""
        with self._lock:
            return tuple(self._events)

    @property
    def attempts(self) -> tuple[EffectAttemptEvent, ...]:
        """Expose immutable attempt facts for conformance assertions."""
        with self._lock:
            return tuple(self._attempts)

    @property
    def receipts(self) -> tuple[EffectReceipt, ...]:
        """Expose immutable terminal receipts for conformance assertions."""
        with self._lock:
            return tuple(self._receipts.values())

    def submit_command(self, transaction: CommandTransaction, *, now: str) -> CommandSubmission:
        """Atomically resolve identity, guards, result, event, intents, and projection."""
        instant = _utc(now)
        with self._lock:
            command_id = transaction.envelope.command_id
            stored = self._commands.get(command_id)
            if stored is not None:
                if stored.transaction.command_fingerprint != transaction.command_fingerprint:
                    raise CommandIdentityConflict(command_id)
                return CommandSubmission(
                    CommandSubmissionResolutionCode.EXACT_REPLAY,
                    stored.submission.result,
                    stored.submission.result_bytes,
                )

            result_code = self._effective_result_code(transaction, instant)
            current = self._aggregate_versions.get(transaction.envelope.target_ref.ref_id)
            authoritative_version: int | ExpectedVersion = (
                ExpectedVersion.ABSENT if current is None else current
            )
            event_refs: tuple[ImmutableReference, ...] = ()
            effect_refs: tuple[ImmutableReference, ...] = ()
            event: RegisterEvent | None = None
            if result_code is CommandResultCode.APPLIED:
                if any(
                    intent.effect_intent_id in self._intents
                    for intent in transaction.effect_intents
                ):
                    raise RegisterInvariantError("duplicate effect intent identity")
                prior_version = current or 0
                new_version = prior_version + 1
                event = self._new_event(transaction, prior_version, new_version, now)
                event_refs = (event.event_ref,)
                effect_refs = tuple(
                    ImmutableReference(
                        ReferenceType.EFFECT_INTENT,
                        intent.effect_intent_id,
                        intent.effect_command_fingerprint,
                    )
                    for intent in transaction.effect_intents
                )
                authoritative_version = new_version

            result = CommandResult(
                command_result_id=_issued_id("cmr", len(self._commands) + 1),
                command_ref=ImmutableReference(
                    ReferenceType.COMMAND,
                    command_id,
                    transaction.command_fingerprint,
                ),
                recorded_at=now,
                result_code=result_code,
                authoritative_version=authoritative_version,
                event_refs=event_refs,
                effect_intent_refs=effect_refs,
                evidence_refs=transaction.evidence_refs,
            )
            result_bytes = _result_bytes(result)
            submission = CommandSubmission(
                CommandSubmissionResolutionCode.RESULT_RECORDED,
                result,
                result_bytes,
            )
            if event is not None:
                self._events.append(event)
                self._aggregate_versions[transaction.envelope.target_ref.ref_id] = event.new_version
                for intent in transaction.effect_intents:
                    self._intents[intent.effect_intent_id] = intent
                if transaction.decision.winner_key is not None:
                    self._winners[transaction.decision.winner_key] = command_id
            self._commands[command_id] = _StoredCommand(transaction, submission)
            self.rebuild_projections()
            return submission

    def resolve_command(self, command_id: str, command_fingerprint: str) -> CommandSubmission:
        """Return original bytes after an ambiguous submission acknowledgement."""
        with self._lock:
            stored = self._commands.get(command_id)
            if stored is None:
                raise LookupError(command_id)
            if stored.transaction.command_fingerprint != command_fingerprint:
                raise CommandIdentityConflict(command_id)
            return CommandSubmission(
                CommandSubmissionResolutionCode.EXACT_REPLAY,
                stored.submission.result,
                stored.submission.result_bytes,
            )

    def claim_effect(
        self,
        effect_intent_id: str,
        *,
        owning_application: ApplicationCode,
        claimant_id: str,
        now: str,
        lease_seconds: int,
    ) -> EffectClaim:
        """Select one owner and fence every expired prior claimant."""
        instant = _utc(now)
        _lease_seconds(lease_seconds)
        with self._lock:
            intent = self._intents.get(effect_intent_id)
            if intent is None:
                raise LookupError(effect_intent_id)
            if intent.owning_application is not owning_application:
                raise EffectClaimConflict("effect owner does not match")
            if effect_intent_id in self._receipts:
                raise EffectClaimConflict("effect already has a terminal receipt")
            if instant >= _utc(intent.deadline):
                raise EffectClaimConflict("effect deadline has passed")
            previous = self._claims.get(effect_intent_id)
            if previous is not None and instant < _utc(previous.expires_at):
                if previous.claimant_id == claimant_id:
                    return previous
                raise EffectClaimConflict("effect has an active claimant")
            generation = 1 if previous is None else previous.generation + 1
            token = 1 if previous is None else previous.fencing_token + 1
            claim = EffectClaim(
                effect_intent_id,
                claimant_id,
                generation,
                token,
                now,
                _format_utc(instant + timedelta(seconds=lease_seconds)),
            )
            self._claims[effect_intent_id] = claim
            return claim

    def renew_effect_claim(
        self,
        effect_intent_id: str,
        *,
        claimant_id: str,
        fencing_token: int,
        now: str,
        lease_seconds: int,
    ) -> EffectClaim:
        """Extend only the current unexpired claim without changing its fence."""
        instant = _utc(now)
        _lease_seconds(lease_seconds)
        with self._lock:
            current = self._live_claim(effect_intent_id, claimant_id, fencing_token, instant)
            renewed = EffectClaim(
                effect_intent_id,
                claimant_id,
                current.generation,
                current.fencing_token,
                now,
                _format_utc(instant + timedelta(seconds=lease_seconds)),
            )
            self._claims[effect_intent_id] = renewed
            return renewed

    def append_effect_attempt(self, event: EffectAttemptEvent, *, now: str) -> None:
        """Append one exact next attempt under a live fencing token."""
        instant = _utc(now)
        with self._lock:
            claim = self._claims.get(event.effect_intent_id)
            if claim is None:
                raise StaleFencingToken("effect has no claim")
            self._live_claim(
                event.effect_intent_id,
                claim.claimant_id,
                event.fencing_token,
                instant,
            )
            if event.recorded_at != now:
                raise RegisterInvariantError("attempt event and register time differ")
            count = sum(
                attempt.effect_intent_id == event.effect_intent_id for attempt in self._attempts
            )
            if event.attempt_number != count + 1:
                raise RegisterInvariantError("attempt_number is not the exact next attempt")
            intent = self._intents[event.effect_intent_id]
            if event.attempt_number > intent.attempt_ceiling:
                raise EffectClaimConflict("effect attempt ceiling exceeded")
            self._attempts.append(event)

    def record_effect_receipt(
        self,
        receipt: EffectReceipt,
        *,
        fencing_token: int | None,
        now: str,
    ) -> EffectReceipt:
        """Select one terminal receipt or return its exact replay."""
        instant = _utc(now)
        intent_id = receipt.effect_intent_ref.ref_id
        with self._lock:
            existing = self._receipts.get(intent_id)
            if existing is not None:
                if existing == receipt:
                    return existing
                raise EffectClaimConflict("effect already has a different terminal receipt")
            intent = self._intents.get(intent_id)
            if intent is None:
                raise LookupError(intent_id)
            if receipt.command_ref != intent.command_ref:
                raise RegisterInvariantError("receipt command does not match intent")
            if receipt.execution_lineage_ref != intent.execution_lineage_ref:
                raise RegisterInvariantError("receipt lineage does not match intent")
            attempt_count = sum(attempt.effect_intent_id == intent_id for attempt in self._attempts)
            if (
                receipt.terminal_status is EffectReceiptStatus.CANCELLED_BEFORE_EFFECT
                and attempt_count != 0
            ):
                raise EffectClaimConflict("effect has already started")
            if receipt.attempt_count != attempt_count:
                raise RegisterInvariantError("receipt attempt count does not match facts")
            if receipt.terminal_status is not EffectReceiptStatus.CANCELLED_BEFORE_EFFECT:
                if fencing_token is None:
                    raise StaleFencingToken("attempted effect receipt requires a fence")
                claim = self._claims.get(intent_id)
                if claim is None:
                    raise StaleFencingToken("effect has no claim")
                self._live_claim(intent_id, claim.claimant_id, fencing_token, instant)
            self._receipts[intent_id] = receipt
            return receipt

    def set_policy_state(self, state: PolicyState) -> None:
        """Append an explicit policy state without inventing a default value."""
        if type(state) is not PolicyState:
            raise TypeError("state must be a PolicyState")
        with self._lock:
            self._policies.append(state)

    def rebuild_projections(self) -> tuple[ProjectionRow, ...]:
        """Rebuild disposable current-version rows solely from immutable events."""
        with self._lock:
            projections: dict[str, ProjectionRow] = {}
            for checkpoint, event in enumerate(self._events, start=1):
                event_bytes = _event_bytes(event)
                projections[event.aggregate_ref.ref_id] = ProjectionRow(
                    event.aggregate_ref.ref_id,
                    event.new_version,
                    checkpoint,
                    f"sha256:{sha256(event_bytes).hexdigest()}",
                )
            self._projections = projections
            return tuple(projections[key] for key in sorted(projections))

    def export_recovery(self, migration_set: tuple[str, ...]) -> RecoveryPackage:
        """Capture all state required to reconstruct the deterministic register."""
        if (
            type(migration_set) is not tuple
            or not migration_set
            or any(type(item) is not str or not item for item in migration_set)
        ):
            raise RegisterInvariantError("migration_set must be a non-empty exact tuple")
        with self._lock:
            snapshot = RegisterSnapshot(
                schema_version=1,
                migration_set=migration_set,
                commands=tuple(stored.transaction for stored in self._commands.values()),
                submissions=tuple(stored.submission for stored in self._commands.values()),
                events=tuple(self._events),
                intents=tuple(self._intents.values()),
                claims=tuple(self._claims[key] for key in sorted(self._claims)),
                attempts=tuple(self._attempts),
                receipts=tuple(self._receipts[key] for key in sorted(self._receipts)),
                policies=tuple(self._policies),
                projections=tuple(self._projections[key] for key in sorted(self._projections)),
                winners=tuple(sorted(self._winners.items())),
            )
            return RecoveryPackage(snapshot, _snapshot_digest(snapshot))

    def restore_recovery(self, package: RecoveryPackage) -> None:
        """Fail closed on digest mismatch, restore facts, then rebuild projections."""
        if _snapshot_digest(package.snapshot) != package.external_digest:
            raise RecoveryDigestMismatch("recovery snapshot digest differs")
        snapshot = package.snapshot
        if len(snapshot.commands) != len(snapshot.submissions):
            raise RegisterInvariantError("recovery commands and submissions differ")
        with self._lock:
            commands = {
                transaction.envelope.command_id: _StoredCommand(transaction, submission)
                for transaction, submission in zip(
                    snapshot.commands,
                    snapshot.submissions,
                    strict=True,
                )
            }
            if len(commands) != len(snapshot.commands):
                raise RegisterInvariantError("recovery contains duplicate command identities")
            self._commands = commands
            self._events = list(snapshot.events)
            self._intents = {intent.effect_intent_id: intent for intent in snapshot.intents}
            self._claims = {claim.effect_intent_id: claim for claim in snapshot.claims}
            self._attempts = list(snapshot.attempts)
            self._receipts = {
                receipt.effect_intent_ref.ref_id: receipt for receipt in snapshot.receipts
            }
            self._policies = list(snapshot.policies)
            self._aggregate_versions = {
                event.aggregate_ref.ref_id: event.new_version for event in snapshot.events
            }
            self._winners = dict(snapshot.winners)
            self.rebuild_projections()

    def _effective_result_code(
        self,
        transaction: CommandTransaction,
        now: datetime,
    ) -> CommandResultCode:
        envelope = transaction.envelope
        current = self._aggregate_versions.get(envelope.target_ref.ref_id)
        if now >= _utc(envelope.expires_at):
            return CommandResultCode.REJECTED_EXPIRED
        expected = envelope.expected_version
        if expected is ExpectedVersion.ABSENT:
            if current is not None:
                return CommandResultCode.REJECTED_STALE_VERSION
        elif current != expected:
            return CommandResultCode.REJECTED_STALE_VERSION
        winner_key = transaction.decision.winner_key
        if winner_key is not None and winner_key in self._winners:
            return CommandResultCode.REJECTED_CONFLICT
        return transaction.decision.result_code

    def _new_event(
        self,
        transaction: CommandTransaction,
        prior_version: int,
        new_version: int,
        now: str,
    ) -> RegisterEvent:
        event_seed = (
            f"{transaction.envelope.command_id}:{transaction.decision.event_type}:{new_version}"
        ).encode()
        fingerprint = f"sha256:{sha256(event_seed).hexdigest()}"
        return RegisterEvent(
            ImmutableReference(
                ReferenceType.EXECUTION_EVENT,
                _issued_id("evt", len(self._events) + 1),
                fingerprint,
            ),
            transaction.envelope.command_id,
            transaction.envelope.target_ref,
            transaction.decision.event_type or "UNREACHABLE",
            prior_version,
            new_version,
            now,
        )

    def _live_claim(
        self,
        effect_intent_id: str,
        claimant_id: str,
        fencing_token: int,
        now: datetime,
    ) -> EffectClaim:
        claim = self._claims.get(effect_intent_id)
        if (
            claim is None
            or claim.claimant_id != claimant_id
            or claim.fencing_token != fencing_token
            or now >= _utc(claim.expires_at)
        ):
            raise StaleFencingToken(effect_intent_id)
        return claim


def _issued_id(prefix: str, counter: int) -> str:
    return f"{prefix}_{counter:048x}"


def _utc(value: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise RegisterInvariantError("timestamp must be exact UTC text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise RegisterInvariantError("timestamp is invalid") from error
    if parsed.tzinfo != UTC:
        raise RegisterInvariantError("timestamp must be UTC")
    return parsed


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _lease_seconds(value: int) -> None:
    if type(value) is not int:
        raise TypeError("lease_seconds must be an exact integer")
    if value < 1:
        raise RegisterInvariantError("lease_seconds must be positive")


def _result_bytes(result: CommandResult) -> bytes:
    payload = {
        "authoritative_version": (
            result.authoritative_version.value
            if isinstance(result.authoritative_version, ExpectedVersion)
            else result.authoritative_version
        ),
        "command_result_id": result.command_result_id,
        "result_code": result.result_code.value,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _event_bytes(event: RegisterEvent) -> bytes:
    payload = {
        "aggregate_id": event.aggregate_ref.ref_id,
        "command_id": event.command_id,
        "event_id": event.event_ref.ref_id,
        "event_type": event.event_type,
        "new_version": event.new_version,
        "prior_version": event.prior_version,
        "recorded_at": event.recorded_at,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _snapshot_digest(snapshot: RegisterSnapshot) -> str:
    raw = repr(snapshot).encode()
    return f"sha256:{sha256(raw).hexdigest()}"


__all__ = ["InMemoryManagementRegister"]
