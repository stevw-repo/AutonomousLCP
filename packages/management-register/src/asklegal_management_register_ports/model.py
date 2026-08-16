"""Framework-free value objects for the authoritative Management Register."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from asklegal_domain import (
    CommandEnvelope,
    CommandResult,
    CommandResultCode,
    CommandSubmissionResolutionCode,
    EffectIntent,
    EffectReceipt,
    ImmutableReference,
    ReferenceType,
)


class RegisterInvariantError(ValueError):
    """A register request violates the closed M2 persistence contract."""


class CommandIdentityConflict(RuntimeError):
    """A command identity was reused with different canonical bytes."""


class EffectClaimConflict(RuntimeError):
    """An effect is terminal or has an active claim owned elsewhere."""


class StaleFencingToken(RuntimeError):
    """An effect mutation used an expired or superseded fencing token."""


class RecoveryDigestMismatch(RuntimeError):
    """A recovery package does not match its externally supplied digest."""


class PolicyDecisionState(StrEnum):
    """Every policy value is explicitly configured or explicitly undecided."""

    CONFIGURED = "CONFIGURED"
    UNDECIDED = "UNDECIDED"


@dataclass(frozen=True, slots=True)
class PolicyState:
    """One exact policy state without a floating application default."""

    policy_ref: ImmutableReference
    state: PolicyDecisionState
    value_ref: ImmutableReference | None

    def __post_init__(self) -> None:
        """Require configured policies to bind one exact immutable value."""
        if self.policy_ref.ref_type is not ReferenceType.POLICY_PROFILE:
            raise RegisterInvariantError("policy_ref must be a POLICY_PROFILE reference")
        if type(self.state) is not PolicyDecisionState:
            raise TypeError("state must be a PolicyDecisionState")
        if (self.state is PolicyDecisionState.CONFIGURED) is (self.value_ref is None):
            raise RegisterInvariantError("configured policy state requires exactly one value_ref")


@dataclass(frozen=True, slots=True)
class CommandGuardDecision:
    """Command-owner decision after schema, authority, and lifecycle checks."""

    result_code: CommandResultCode
    event_type: str | None = None
    winner_key: str | None = None

    def __post_init__(self) -> None:
        """Keep applied and rejected plans structurally disjoint."""
        if type(self.result_code) is not CommandResultCode:
            raise TypeError("result_code must be a CommandResultCode")
        if self.result_code is CommandResultCode.APPLIED:
            _exact_text(self.event_type, "event_type")
        elif self.event_type is not None or self.winner_key is not None:
            raise RegisterInvariantError("a rejected decision cannot append an event or winner")
        if self.winner_key is not None:
            _exact_text(self.winner_key, "winner_key")


@dataclass(frozen=True, slots=True)
class CommandTransaction:
    """One exact command plus the owner decision to commit atomically."""

    envelope: CommandEnvelope[StrEnum]
    canonical_command: bytes
    command_fingerprint: str
    decision: CommandGuardDecision
    effect_intents: tuple[EffectIntent, ...] = ()
    evidence_refs: tuple[ImmutableReference, ...] = ()

    def __post_init__(self) -> None:
        """Verify command bytes, fingerprint, and planned effect ownership."""
        if type(self.canonical_command) is not bytes or not self.canonical_command:
            raise RegisterInvariantError("canonical_command must be non-empty exact bytes")
        _fingerprint(self.command_fingerprint, "command_fingerprint")
        actual = f"sha256:{sha256(self.canonical_command).hexdigest()}"
        if actual != self.command_fingerprint:
            raise RegisterInvariantError("canonical command bytes do not match fingerprint")
        if type(self.decision) is not CommandGuardDecision:
            raise TypeError("decision must be a CommandGuardDecision")
        if type(self.effect_intents) is not tuple or any(
            type(intent) is not EffectIntent for intent in self.effect_intents
        ):
            raise TypeError("effect_intents must be an exact tuple of EffectIntent values")
        if type(self.evidence_refs) is not tuple or any(
            type(reference) is not ImmutableReference for reference in self.evidence_refs
        ):
            raise TypeError("evidence_refs must be an exact tuple of ImmutableReference values")
        evidence_keys = tuple(
            (reference.ref_type.value, reference.ref_id, reference.fingerprint)
            for reference in self.evidence_refs
        )
        if evidence_keys != tuple(sorted(set(evidence_keys))):
            raise RegisterInvariantError("evidence_refs must be unique and exactly sorted")
        if self.decision.result_code is not CommandResultCode.APPLIED and self.effect_intents:
            raise RegisterInvariantError("a rejected transaction cannot append effect intents")
        intent_ids = tuple(intent.effect_intent_id for intent in self.effect_intents)
        if len(intent_ids) != len(set(intent_ids)):
            raise RegisterInvariantError("effect_intents must have unique identities")
        if any(
            intent.command_ref.ref_id != self.envelope.command_id for intent in self.effect_intents
        ):
            raise RegisterInvariantError("every effect intent must belong to the command")


@dataclass(frozen=True, slots=True)
class CommandSubmission:
    """Submission resolution plus the sole authoritative durable result."""

    resolution: CommandSubmissionResolutionCode
    result: CommandResult
    result_bytes: bytes

    def __post_init__(self) -> None:
        """Admit only resolutions that include an authoritative result."""
        if self.resolution not in {
            CommandSubmissionResolutionCode.RESULT_RECORDED,
            CommandSubmissionResolutionCode.EXACT_REPLAY,
        }:
            raise RegisterInvariantError("submission does not contain a durable result")
        if type(self.result) is not CommandResult:
            raise TypeError("result must be a CommandResult")
        if type(self.result_bytes) is not bytes or not self.result_bytes:
            raise RegisterInvariantError("result_bytes must be non-empty exact bytes")


@dataclass(frozen=True, slots=True)
class RegisterEvent:
    """One immutable authoritative event appended by an applied command."""

    event_ref: ImmutableReference
    command_id: str
    aggregate_ref: ImmutableReference
    event_type: str
    prior_version: int
    new_version: int
    recorded_at: str

    def __post_init__(self) -> None:
        """Require one exact monotonic aggregate version increment."""
        if self.event_ref.ref_type is not ReferenceType.EXECUTION_EVENT:
            raise RegisterInvariantError("event_ref must be an EXECUTION_EVENT reference")
        _exact_text(self.command_id, "command_id")
        _exact_text(self.event_type, "event_type")
        if type(self.prior_version) is not int or type(self.new_version) is not int:
            raise TypeError("event versions must be exact integers")
        if self.prior_version < 0 or self.new_version != self.prior_version + 1:
            raise RegisterInvariantError("event must increment aggregate version exactly once")
        _utc(self.recorded_at, "recorded_at")


@dataclass(frozen=True, slots=True)
class EffectClaim:
    """Renewable exclusive effect lease with a monotonic fencing token."""

    effect_intent_id: str
    claimant_id: str
    generation: int
    fencing_token: int
    claimed_at: str
    expires_at: str

    def __post_init__(self) -> None:
        """Reject malformed or non-forward claims."""
        _exact_text(self.effect_intent_id, "effect_intent_id")
        _exact_text(self.claimant_id, "claimant_id")
        if type(self.generation) is not int or type(self.fencing_token) is not int:
            raise TypeError("claim counters must be exact integers")
        if self.generation < 1 or self.fencing_token < 1:
            raise RegisterInvariantError("claim counters must be positive")
        if _utc(self.expires_at, "expires_at") <= _utc(self.claimed_at, "claimed_at"):
            raise RegisterInvariantError("claim expiry must follow claim time")


@dataclass(frozen=True, slots=True)
class EffectAttemptEvent:
    """One sanitized append-only effect attempt fact."""

    effect_intent_id: str
    attempt_number: int
    fencing_token: int
    event_code: str
    evidence_refs: tuple[ImmutableReference, ...]
    recorded_at: str

    def __post_init__(self) -> None:
        """Require positive counters and sanitized exact references."""
        _exact_text(self.effect_intent_id, "effect_intent_id")
        _exact_text(self.event_code, "event_code")
        if type(self.attempt_number) is not int or type(self.fencing_token) is not int:
            raise TypeError("attempt counters must be exact integers")
        if self.attempt_number < 1 or self.fencing_token < 1:
            raise RegisterInvariantError("attempt counters must be positive")
        if type(self.evidence_refs) is not tuple or any(
            type(reference) is not ImmutableReference for reference in self.evidence_refs
        ):
            raise TypeError("evidence_refs must be an exact tuple of ImmutableReference values")
        _utc(self.recorded_at, "recorded_at")


@dataclass(frozen=True, slots=True)
class ProjectionRow:
    """Disposable aggregate-version projection derived from register events."""

    aggregate_id: str
    version: int
    checkpoint: int
    source_event_fingerprint: str


@dataclass(frozen=True, slots=True)
class RegisterSnapshot:
    """Complete immutable state carried by a deterministic fake recovery export."""

    schema_version: int
    migration_set: tuple[str, ...]
    commands: tuple[CommandTransaction, ...]
    submissions: tuple[CommandSubmission, ...]
    events: tuple[RegisterEvent, ...]
    intents: tuple[EffectIntent, ...]
    claims: tuple[EffectClaim, ...]
    attempts: tuple[EffectAttemptEvent, ...]
    receipts: tuple[EffectReceipt, ...]
    policies: tuple[PolicyState, ...]
    projections: tuple[ProjectionRow, ...]
    winners: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class RecoveryPackage:
    """One closed recovery snapshot bound to an external digest."""

    snapshot: RegisterSnapshot
    external_digest: str

    def __post_init__(self) -> None:
        """Require a syntactically valid digest; restore proves its value."""
        if type(self.snapshot) is not RegisterSnapshot:
            raise TypeError("snapshot must be a RegisterSnapshot")
        _fingerprint(self.external_digest, "external_digest")


def _exact_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact string")
    if not value or value.strip() != value:
        raise RegisterInvariantError(f"{field_name} must be non-empty and whitespace-exact")
    return value


def _fingerprint(value: object, field_name: str) -> str:
    text = _exact_text(value, field_name)
    if len(text) != 71 or not text.startswith("sha256:"):
        raise RegisterInvariantError(f"{field_name} must be one sha256 fingerprint")
    try:
        bytes.fromhex(text[7:])
    except ValueError as error:
        raise RegisterInvariantError(f"{field_name} must be hexadecimal") from error
    return text


def _utc(value: object, field_name: str) -> datetime:
    text = _exact_text(value, field_name)
    if not text.endswith("Z"):
        raise RegisterInvariantError(f"{field_name} must be UTC")
    try:
        parsed = datetime.fromisoformat(f"{text[:-1]}+00:00")
    except ValueError as error:
        raise RegisterInvariantError(f"{field_name} is not a timestamp") from error
    if parsed.tzinfo != UTC:
        raise RegisterInvariantError(f"{field_name} must be UTC")
    return parsed


__all__ = [
    "CommandGuardDecision",
    "CommandIdentityConflict",
    "CommandSubmission",
    "CommandTransaction",
    "EffectAttemptEvent",
    "EffectClaim",
    "EffectClaimConflict",
    "PolicyDecisionState",
    "PolicyState",
    "ProjectionRow",
    "RecoveryDigestMismatch",
    "RecoveryPackage",
    "RegisterEvent",
    "RegisterInvariantError",
    "RegisterSnapshot",
    "StaleFencingToken",
]
