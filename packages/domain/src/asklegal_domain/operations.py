"""Strict immutable command and external-effect domain objects."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Never

from .lifecycles import DomainInvariantError

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")
_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_TIMESTAMP_PATTERN = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>0[1-9]|1[0-2])-(?P<day>[0-2][0-9]|3[01])"
    r"T(?P<hour>[01][0-9]|2[0-3]):(?P<minute>[0-5][0-9]):(?P<second>[0-5][0-9])"
    r"(?:\.(?P<fraction>[0-9]{1,9}))?Z$",
)


def _raise_invariant(message: str) -> Never:
    raise DomainInvariantError(message)


def _raise_type(message: str) -> Never:
    raise TypeError(message)


def _validate_exact_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        _raise_type(f"{field_name} must be an exact string")
    if not value or value.strip() != value:
        _raise_invariant(f"{field_name} must be non-empty and whitespace-exact")
    return value


def _validate_pattern(value: object, field_name: str, pattern: re.Pattern[str]) -> None:
    text = _validate_exact_text(value, field_name)
    if pattern.fullmatch(text) is None:
        _raise_invariant(f"{field_name} has an invalid closed contract form")


def _validate_exact_integer(value: object, field_name: str, *, minimum: int) -> None:
    if type(value) is not int:
        _raise_type(f"{field_name} must be an exact integer")
    if value < minimum:
        _raise_invariant(f"{field_name} must be at least {minimum}")


def _parse_timestamp(value: object, field_name: str) -> datetime:
    text = _validate_exact_text(value, field_name)
    match = _TIMESTAMP_PATTERN.fullmatch(text)
    if match is None:
        _raise_invariant(f"{field_name} must be a canonical UTC timestamp")
    fraction = (match.group("fraction") or "").ljust(6, "0")[:6]
    try:
        return datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second")),
            int(fraction or "0"),
            tzinfo=UTC,
        )
    except ValueError as error:
        message = f"{field_name} must be a real canonical UTC timestamp"
        raise DomainInvariantError(message) from error


def _command_code_value(value: object) -> str:
    if not isinstance(value, StrEnum):
        _raise_type("command_type must be a closed StrEnum member")
    return value.value


class ReferenceType(StrEnum):
    """Closed cross-cutting immutable-reference kinds."""

    ACTOR = "ACTOR"
    AGGREGATE = "AGGREGATE"
    APPROVAL = "APPROVAL"
    ARTIFACT = "ARTIFACT"
    ATTESTATION = "ATTESTATION"
    BUILD = "BUILD"
    CAPABILITY_PROFILE = "CAPABILITY_PROFILE"
    CARRY_FORWARD_SELECTION = "CARRY_FORWARD_SELECTION"
    COMMAND = "COMMAND"
    COMMAND_RESULT = "COMMAND_RESULT"
    CONFIGURATION = "CONFIGURATION"
    CONTRACT = "CONTRACT"
    CONTRACT_SET = "CONTRACT_SET"
    CORPUS_RELEASE = "CORPUS_RELEASE"
    COVERAGE_GAP = "COVERAGE_GAP"
    DECISION = "DECISION"
    DESIRED_STATE_INVENTORY = "DESIRED_STATE_INVENTORY"
    EFFECT_INTENT = "EFFECT_INTENT"
    EFFECT_RECEIPT = "EFFECT_RECEIPT"
    EMBEDDING_PROFILE = "EMBEDDING_PROFILE"
    EMBEDDING_REQUEST = "EMBEDDING_REQUEST"
    EMBEDDING_RECEIPT = "EMBEDDING_RECEIPT"
    EVIDENCE = "EVIDENCE"
    EXECUTION_EVENT = "EXECUTION_EVENT"
    EXECUTION_LINEAGE = "EXECUTION_LINEAGE"
    LEGAL_ITEM = "LEGAL_ITEM"
    LEGAL_LOCATION = "LEGAL_LOCATION"
    LEGAL_STATUS_EVENT = "LEGAL_STATUS_EVENT"
    OBSERVATION = "OBSERVATION"
    OFFICIAL_VERSION = "OFFICIAL_VERSION"
    PINECONE_INDEX_GENERATION = "PINECONE_INDEX_GENERATION"
    POLICY_PROFILE = "POLICY_PROFILE"
    PROMOTION_MANIFEST = "PROMOTION_MANIFEST"
    PROPOSAL_PACKAGE = "PROPOSAL_PACKAGE"
    QUARANTINE = "QUARANTINE"
    QUERY_CONTRACT = "QUERY_CONTRACT"
    RECORD_TRACEABILITY_LOOKUP = "RECORD_TRACEABILITY_LOOKUP"
    RELEASE_SCOPE = "RELEASE_SCOPE"
    RELEASE_SCOPE_REGISTRY = "RELEASE_SCOPE_REGISTRY"
    ROUTING_CONFIGURATION = "ROUTING_CONFIGURATION"
    RULEBOOK = "RULEBOOK"
    SEARCH_RECORD = "SEARCH_RECORD"
    SERVING_STATE = "SERVING_STATE"
    SOURCE = "SOURCE"
    SOURCE_ENDPOINT = "SOURCE_ENDPOINT"
    SOURCE_SNAPSHOT = "SOURCE_SNAPSHOT"
    VALIDATION = "VALIDATION"
    WORKFLOW_PROFILE = "WORKFLOW_PROFILE"
    WORK_ITEM = "WORK_ITEM"


class ExpectedVersion(StrEnum):
    """Explicit absent-aggregate concurrency state."""

    ABSENT = "ABSENT"


_REFERENCE_PREFIXES: dict[ReferenceType, frozenset[str]] = {
    ReferenceType.ACTOR: frozenset({"act"}),
    ReferenceType.BUILD: frozenset({"bld"}),
    ReferenceType.CAPABILITY_PROFILE: frozenset({"cap"}),
    ReferenceType.COMMAND: frozenset({"cmd"}),
    ReferenceType.COMMAND_RESULT: frozenset({"cmr"}),
    ReferenceType.CONFIGURATION: frozenset({"cfg"}),
    ReferenceType.CONTRACT_SET: frozenset({"cst"}),
    ReferenceType.EFFECT_INTENT: frozenset({"efi"}),
    ReferenceType.EFFECT_RECEIPT: frozenset({"efr"}),
    ReferenceType.EMBEDDING_PROFILE: frozenset({"emp"}),
    ReferenceType.EMBEDDING_REQUEST: frozenset({"emr"}),
    ReferenceType.EMBEDDING_RECEIPT: frozenset({"emc"}),
    ReferenceType.EVIDENCE: frozenset({"evi"}),
    ReferenceType.EXECUTION_LINEAGE: frozenset({"exe"}),
    ReferenceType.POLICY_PROFILE: frozenset({"pol"}),
    ReferenceType.PROPOSAL_PACKAGE: frozenset({"ppk"}),
    ReferenceType.WORKFLOW_PROFILE: frozenset({"wap"}),
    ReferenceType.WORK_ITEM: frozenset({"wki"}),
}


class CommandResultCode(StrEnum):
    """Authoritative durable outcomes from one command transaction."""

    APPLIED = "APPLIED"
    REJECTED_CAPABILITY = "REJECTED_CAPABILITY"
    REJECTED_CONFLICT = "REJECTED_CONFLICT"
    REJECTED_EXPIRED = "REJECTED_EXPIRED"
    REJECTED_INVALID_INPUT = "REJECTED_INVALID_INPUT"
    REJECTED_INVALID_STATE = "REJECTED_INVALID_STATE"
    REJECTED_STALE_VERSION = "REJECTED_STALE_VERSION"
    REJECTED_UNAUTHORIZED = "REJECTED_UNAUTHORIZED"


class CommandSubmissionResolutionCode(StrEnum):
    """Non-persisted intake/transport resolution for a command submission."""

    COMMAND_ID_CONFLICT = "COMMAND_ID_CONFLICT"
    EXACT_REPLAY = "EXACT_REPLAY"
    INDETERMINATE = "INDETERMINATE"
    RESULT_RECORDED = "RESULT_RECORDED"


class EffectType(StrEnum):
    """Closed external-effect families."""

    BACKUP_MUTATION = "BACKUP_MUTATION"
    EMBEDDING_PROVIDER_CALL = "EMBEDDING_PROVIDER_CALL"
    EVIDENCE_WRITE = "EVIDENCE_WRITE"
    GENERATIVE_LLM_CALL = "GENERATIVE_LLM_CALL"
    PINECONE_MUTATION = "PINECONE_MUTATION"
    RELEASE_PUBLICATION = "RELEASE_PUBLICATION"
    ROUTING_ACTIVATION = "ROUTING_ACTIVATION"
    SOURCE_CAPTURE = "SOURCE_CAPTURE"


class ApplicationCode(StrEnum):
    """Closed application ownership boundary."""

    ACQUISITION_WORKER = "ACQUISITION_WORKER"
    CONTROL_PLANE = "CONTROL_PLANE"
    LEGAL_PROCESSING_WORKER = "LEGAL_PROCESSING_WORKER"
    PROMOTION_WORKER = "PROMOTION_WORKER"
    REVIEW_APPLICATION = "REVIEW_APPLICATION"


class EffectCapability(StrEnum):
    """Capabilities that can authorize an external effect."""

    ACTIVATE_ROUTING = "ACTIVATE_ROUTING"
    CALL_EMBEDDING_PROVIDER = "CALL_EMBEDDING_PROVIDER"
    CALL_GENERATIVE_LLM = "CALL_GENERATIVE_LLM"
    CAPTURE_SOURCE = "CAPTURE_SOURCE"
    MANAGE_BACKUP = "MANAGE_BACKUP"
    MUTATE_PINECONE = "MUTATE_PINECONE"
    PUBLISH_RELEASE = "PUBLISH_RELEASE"
    WRITE_EVIDENCE = "WRITE_EVIDENCE"


class DestinationClass(StrEnum):
    """Sanitized destination classes; coordinates remain adapter-private."""

    BACKUP_STORE = "BACKUP_STORE"
    EMBEDDING_PROVIDER = "EMBEDDING_PROVIDER"
    EVIDENCE_VAULT = "EVIDENCE_VAULT"
    MODEL_PROVIDER = "MODEL_PROVIDER"
    RELEASE_STORE = "RELEASE_STORE"
    ROUTING_TARGET = "ROUTING_TARGET"
    SERVING_TARGET = "SERVING_TARGET"
    SOURCE_SYSTEM = "SOURCE_SYSTEM"


class RetryClass(StrEnum):
    """Closed retry behavior for an exact effect intent."""

    NEVER = "NEVER"
    RECONCILE_BEFORE_RETRY = "RECONCILE_BEFORE_RETRY"
    SAFE_SAME_INTENT = "SAFE_SAME_INTENT"


class StopCondition(StrEnum):
    """Closed reasons an intent may no longer start another attempt."""

    ATTEMPT_CEILING = "ATTEMPT_CEILING"
    AUTHORITY_INVALID = "AUTHORITY_INVALID"
    CANCELLATION_BEFORE_EFFECT = "CANCELLATION_BEFORE_EFFECT"
    CAPABILITY_INACTIVE = "CAPABILITY_INACTIVE"
    DEADLINE = "DEADLINE"
    POSTCONDITION_MET = "POSTCONDITION_MET"
    PRECONDITION_CHANGED = "PRECONDITION_CHANGED"


class EffectReceiptStatus(StrEnum):
    """Closed terminal outcomes for one effect intent."""

    CANCELLED_BEFORE_EFFECT = "CANCELLED_BEFORE_EFFECT"
    FAILED_FINAL = "FAILED_FINAL"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    SUCCEEDED = "SUCCEEDED"


_EFFECT_BINDINGS: dict[
    EffectType,
    tuple[frozenset[ApplicationCode], EffectCapability, DestinationClass],
] = {
    EffectType.BACKUP_MUTATION: (
        frozenset({ApplicationCode.PROMOTION_WORKER}),
        EffectCapability.MANAGE_BACKUP,
        DestinationClass.BACKUP_STORE,
    ),
    EffectType.EMBEDDING_PROVIDER_CALL: (
        frozenset({ApplicationCode.PROMOTION_WORKER}),
        EffectCapability.CALL_EMBEDDING_PROVIDER,
        DestinationClass.EMBEDDING_PROVIDER,
    ),
    EffectType.EVIDENCE_WRITE: (
        frozenset(ApplicationCode),
        EffectCapability.WRITE_EVIDENCE,
        DestinationClass.EVIDENCE_VAULT,
    ),
    EffectType.GENERATIVE_LLM_CALL: (
        frozenset({ApplicationCode.LEGAL_PROCESSING_WORKER}),
        EffectCapability.CALL_GENERATIVE_LLM,
        DestinationClass.MODEL_PROVIDER,
    ),
    EffectType.PINECONE_MUTATION: (
        frozenset({ApplicationCode.PROMOTION_WORKER}),
        EffectCapability.MUTATE_PINECONE,
        DestinationClass.SERVING_TARGET,
    ),
    EffectType.RELEASE_PUBLICATION: (
        frozenset({ApplicationCode.PROMOTION_WORKER}),
        EffectCapability.PUBLISH_RELEASE,
        DestinationClass.RELEASE_STORE,
    ),
    EffectType.ROUTING_ACTIVATION: (
        frozenset({ApplicationCode.PROMOTION_WORKER}),
        EffectCapability.ACTIVATE_ROUTING,
        DestinationClass.ROUTING_TARGET,
    ),
    EffectType.SOURCE_CAPTURE: (
        frozenset({ApplicationCode.ACQUISITION_WORKER}),
        EffectCapability.CAPTURE_SOURCE,
        DestinationClass.SOURCE_SYSTEM,
    ),
}


class FailureCode(StrEnum):
    """Closed cross-cutting failure codes admitted in effect receipts."""

    FAILURE_CAPABILITY_DISABLED = "FAILURE_CAPABILITY_DISABLED"
    FAILURE_DUPLICATE_ID = "FAILURE_DUPLICATE_ID"
    FAILURE_EXTERNAL_EFFECT = "FAILURE_EXTERNAL_EFFECT"
    FAILURE_FINGERPRINT_MISMATCH = "FAILURE_FINGERPRINT_MISMATCH"
    FAILURE_FORBIDDEN_TRANSITION = "FAILURE_FORBIDDEN_TRANSITION"
    FAILURE_ID_COLLISION = "FAILURE_ID_COLLISION"
    FAILURE_INVENTORY_MISMATCH = "FAILURE_INVENTORY_MISMATCH"
    FAILURE_LINEAGE_CYCLE = "FAILURE_LINEAGE_CYCLE"
    FAILURE_MALFORMED_JSON = "FAILURE_MALFORMED_JSON"
    FAILURE_NON_CANONICAL = "FAILURE_NON_CANONICAL"
    FAILURE_PATH_ESCAPE = "FAILURE_PATH_ESCAPE"
    FAILURE_POLICY_UNDECIDED = "FAILURE_POLICY_UNDECIDED"
    FAILURE_REFERENCE_MISSING = "FAILURE_REFERENCE_MISSING"
    FAILURE_REPRODUCIBILITY = "FAILURE_REPRODUCIBILITY"
    FAILURE_RETRY_INPUT_CHANGED = "FAILURE_RETRY_INPUT_CHANGED"
    FAILURE_SCHEMA_INVALID = "FAILURE_SCHEMA_INVALID"
    FAILURE_UNKNOWN_CODE = "FAILURE_UNKNOWN_CODE"


@dataclass(frozen=True, slots=True)
class ImmutableReference:
    """One exact typed identity-and-fingerprint reference."""

    ref_type: ReferenceType
    ref_id: str
    fingerprint: str

    def __post_init__(self) -> None:
        """Reject unknown reference kinds and malformed exact bindings."""
        if type(self.ref_type) is not ReferenceType:
            _raise_type("ref_type must be a ReferenceType member")
        _validate_pattern(self.ref_id, "ref_id", _ID_PATTERN)
        _validate_pattern(self.fingerprint, "fingerprint", _FINGERPRINT_PATTERN)
        expected_prefixes = _REFERENCE_PREFIXES.get(self.ref_type)
        if expected_prefixes is not None and self.ref_id[:3] not in expected_prefixes:
            _raise_invariant("ref_id prefix does not match ref_type")


@dataclass(frozen=True, slots=True)
class ContractReference:
    """One exact versioned contract reference."""

    contract_id: str
    version: str
    fingerprint: str

    def __post_init__(self) -> None:
        """Reject floating, malformed, or non-fingerprinted contracts."""
        _validate_exact_text(self.contract_id, "contract_id")
        _validate_pattern(self.version, "version", _VERSION_PATTERN)
        _validate_pattern(self.fingerprint, "fingerprint", _FINGERPRINT_PATTERN)


def _reference_key(reference: ImmutableReference) -> tuple[str, str, str]:
    return (reference.ref_type.value, reference.ref_id, reference.fingerprint)


def _validate_references(
    value: tuple[ImmutableReference, ...],
    field_name: str,
    *,
    minimum: int = 0,
    allowed_types: frozenset[ReferenceType] | None = None,
) -> None:
    if type(value) is not tuple or any(type(item) is not ImmutableReference for item in value):
        _raise_type(f"{field_name} must be an exact tuple of ImmutableReference values")
    if len(value) < minimum:
        _raise_invariant(f"{field_name} must contain at least {minimum} reference(s)")
    references = value
    if allowed_types is not None and any(
        reference.ref_type not in allowed_types for reference in references
    ):
        _raise_invariant(f"{field_name} contains a forbidden reference type")
    keys = tuple(_reference_key(reference) for reference in references)
    if len(set(keys)) != len(keys):
        _raise_invariant(f"{field_name} must not contain duplicate references")
    if keys != tuple(sorted(keys)):
        _raise_invariant(f"{field_name} must be sorted by exact reference identity")


def _validate_reference(
    value: object,
    field_name: str,
    *,
    allowed_types: frozenset[ReferenceType] | None = None,
) -> None:
    if type(value) is not ImmutableReference:
        _raise_type(f"{field_name} must be an ImmutableReference")
    if allowed_types is not None and value.ref_type not in allowed_types:
        _raise_invariant(f"{field_name} has a forbidden reference type")


def _validate_contract_reference(value: object, field_name: str) -> None:
    if type(value) is not ContractReference:
        _raise_type(f"{field_name} must be a ContractReference")


def _validate_expected_version(value: object, field_name: str) -> None:
    if type(value) is ExpectedVersion:
        return
    _validate_exact_integer(value, field_name, minimum=0)


@dataclass(frozen=True, slots=True)
class CommandPayload:
    """Descriptor binding a command-specific object to its exact contract."""

    payload_contract_ref: ContractReference
    payload_object_ref: ImmutableReference

    def __post_init__(self) -> None:
        """Require the exact contract and immutable object binding."""
        _validate_contract_reference(self.payload_contract_ref, "payload_contract_ref")
        _validate_reference(self.payload_object_ref, "payload_object_ref")


@dataclass(frozen=True, slots=True)
class CommandEnvelope[CommandCodeT: StrEnum]:
    """One immutable idempotent command submitted to an aggregate owner."""

    command_id: str
    command_type: CommandCodeT
    contract_version: str
    target_ref: ImmutableReference
    expected_version: int | ExpectedVersion
    actor_ref: ImmutableReference
    authority_ref: ImmutableReference
    causation_ref: ImmutableReference
    correlation_id: str
    execution_lineage_ref: ImmutableReference | None
    input_refs: tuple[ImmutableReference, ...]
    policy_profile_refs: tuple[ImmutableReference, ...]
    configuration_ref: ImmutableReference
    contract_set_ref: ImmutableReference
    build_ref: ImmutableReference
    submitted_at: str
    expires_at: str
    payload: CommandPayload

    def __post_init__(self) -> None:
        """Reject malformed, floating, mutable, or unbounded command inputs."""
        _validate_pattern(self.command_id, "command_id", re.compile(r"^cmd_[0-9a-f]{48}$"))
        _validate_pattern(
            _command_code_value(self.command_type),
            "command_type",
            _CODE_PATTERN,
        )
        _validate_pattern(self.contract_version, "contract_version", _VERSION_PATTERN)
        _validate_reference(self.target_ref, "target_ref")
        _validate_expected_version(self.expected_version, "expected_version")
        _validate_reference(
            self.actor_ref,
            "actor_ref",
            allowed_types=frozenset({ReferenceType.ACTOR}),
        )
        _validate_reference(
            self.authority_ref,
            "authority_ref",
            allowed_types=frozenset({ReferenceType.EVIDENCE}),
        )
        _validate_reference(self.causation_ref, "causation_ref")
        _validate_pattern(self.correlation_id, "correlation_id", re.compile(r"^run_[0-9a-f]{48}$"))
        if self.execution_lineage_ref is not None:
            _validate_reference(
                self.execution_lineage_ref,
                "execution_lineage_ref",
                allowed_types=frozenset({ReferenceType.EXECUTION_LINEAGE}),
            )
        _validate_references(self.input_refs, "input_refs")
        _validate_references(
            self.policy_profile_refs,
            "policy_profile_refs",
            minimum=1,
            allowed_types=frozenset(
                {
                    ReferenceType.CAPABILITY_PROFILE,
                    ReferenceType.POLICY_PROFILE,
                    ReferenceType.WORKFLOW_PROFILE,
                },
            ),
        )
        _validate_reference(
            self.configuration_ref,
            "configuration_ref",
            allowed_types=frozenset({ReferenceType.CONFIGURATION}),
        )
        _validate_reference(
            self.contract_set_ref,
            "contract_set_ref",
            allowed_types=frozenset({ReferenceType.CONTRACT_SET}),
        )
        _validate_reference(
            self.build_ref,
            "build_ref",
            allowed_types=frozenset({ReferenceType.BUILD}),
        )
        submitted_at = _parse_timestamp(self.submitted_at, "submitted_at")
        expires_at = _parse_timestamp(self.expires_at, "expires_at")
        if expires_at <= submitted_at:
            _raise_invariant("expires_at must be later than submitted_at")
        if type(self.payload) is not CommandPayload:
            _raise_type("payload must be a CommandPayload")


@dataclass(frozen=True, slots=True)
class CommandResult:
    """One immutable authoritative business result for a command identity."""

    command_result_id: str
    command_ref: ImmutableReference
    recorded_at: str
    result_code: CommandResultCode
    authoritative_version: int | ExpectedVersion
    event_refs: tuple[ImmutableReference, ...]
    effect_intent_refs: tuple[ImmutableReference, ...]
    evidence_refs: tuple[ImmutableReference, ...]

    def __post_init__(self) -> None:
        """Keep durable applied and rejected outcomes structurally disjoint."""
        _validate_pattern(
            self.command_result_id,
            "command_result_id",
            re.compile(r"^cmr_[0-9a-f]{48}$"),
        )
        _validate_reference(
            self.command_ref,
            "command_ref",
            allowed_types=frozenset({ReferenceType.COMMAND}),
        )
        _parse_timestamp(self.recorded_at, "recorded_at")
        if type(self.result_code) is not CommandResultCode:
            _raise_type("result_code must be a CommandResultCode member")
        _validate_expected_version(self.authoritative_version, "authoritative_version")
        _validate_references(self.event_refs, "event_refs")
        _validate_references(
            self.effect_intent_refs,
            "effect_intent_refs",
            allowed_types=frozenset({ReferenceType.EFFECT_INTENT}),
        )
        _validate_references(self.evidence_refs, "evidence_refs")
        if self.result_code is CommandResultCode.APPLIED:
            _validate_exact_integer(
                self.authoritative_version,
                "authoritative_version",
                minimum=1,
            )
            if not self.event_refs:
                _raise_invariant(
                    "an applied CommandResult must contain at least one event reference",
                )
        elif self.event_refs or self.effect_intent_refs:
            _raise_invariant("a rejected CommandResult cannot declare events or effect intents")


@dataclass(frozen=True, slots=True)
class NoCompensation:
    """Explicit declaration that an effect has no compensation operation."""


@dataclass(frozen=True, slots=True)
class DeclaredCompensation:
    """Exact predeclared compensation contract."""

    contract_ref: ContractReference

    def __post_init__(self) -> None:
        """Require one exact predeclared compensation contract."""
        _validate_contract_reference(self.contract_ref, "contract_ref")


@dataclass(frozen=True, slots=True)
class EffectIntent:
    """Immutable authority to attempt one exact external effect."""

    effect_intent_id: str
    created_at: str
    effect_type: EffectType
    owning_application: ApplicationCode
    aggregate_ref: ImmutableReference
    command_ref: ImmutableReference
    execution_lineage_ref: ImmutableReference
    permitted_checkpoint: str
    input_refs: tuple[ImmutableReference, ...]
    effect_command_fingerprint: str
    required_capability: EffectCapability
    capability_profile_ref: ImmutableReference
    destination_class: DestinationClass
    stable_idempotency_key: str
    retry_class: RetryClass
    attempt_ceiling: int
    deadline: str
    stop_conditions: tuple[StopCondition, ...]
    expected_remote_precondition_ref: ContractReference
    success_postcondition_ref: ContractReference
    compensation: NoCompensation | DeclaredCompensation

    def __post_init__(self) -> None:
        """Validate exact authority, inputs, retry behavior, and postcondition."""
        self._validate_identity_and_authority()
        self._validate_retry_and_completion()

    def _validate_identity_and_authority(self) -> None:
        """Validate the effect identity, owner, lineage, capability, and inputs."""
        _validate_pattern(
            self.effect_intent_id,
            "effect_intent_id",
            re.compile(r"^efi_[0-9a-f]{48}$"),
        )
        _parse_timestamp(self.created_at, "created_at")
        if type(self.effect_type) is not EffectType:
            _raise_type("effect_type must be an EffectType member")
        if type(self.owning_application) is not ApplicationCode:
            _raise_type("owning_application must be an ApplicationCode member")
        _validate_reference(self.aggregate_ref, "aggregate_ref")
        _validate_reference(
            self.command_ref,
            "command_ref",
            allowed_types=frozenset({ReferenceType.COMMAND}),
        )
        _validate_reference(
            self.execution_lineage_ref,
            "execution_lineage_ref",
            allowed_types=frozenset({ReferenceType.EXECUTION_LINEAGE}),
        )
        _validate_pattern(self.permitted_checkpoint, "permitted_checkpoint", _CODE_PATTERN)
        _validate_references(self.input_refs, "input_refs", minimum=1)
        _validate_pattern(
            self.effect_command_fingerprint,
            "effect_command_fingerprint",
            _FINGERPRINT_PATTERN,
        )
        if type(self.required_capability) is not EffectCapability:
            _raise_type("required_capability must be an EffectCapability member")
        _validate_reference(
            self.capability_profile_ref,
            "capability_profile_ref",
            allowed_types=frozenset({ReferenceType.CAPABILITY_PROFILE}),
        )
        if type(self.destination_class) is not DestinationClass:
            _raise_type("destination_class must be a DestinationClass member")
        allowed_owners, required_capability, destination_class = _EFFECT_BINDINGS[self.effect_type]
        if self.owning_application not in allowed_owners:
            _raise_invariant("effect_type has the wrong owning_application")
        if self.required_capability is not required_capability:
            _raise_invariant("effect_type has the wrong required_capability")
        if self.destination_class is not destination_class:
            _raise_invariant("effect_type has the wrong destination_class")
        _validate_exact_text(self.stable_idempotency_key, "stable_idempotency_key")

    def _validate_retry_and_completion(self) -> None:
        """Validate retry limits, deadline, stop conditions, and compensation."""
        created_at = _parse_timestamp(self.created_at, "created_at")
        if type(self.retry_class) is not RetryClass:
            _raise_type("retry_class must be a RetryClass member")
        _validate_exact_integer(self.attempt_ceiling, "attempt_ceiling", minimum=1)
        deadline = _parse_timestamp(self.deadline, "deadline")
        if deadline <= created_at:
            _raise_invariant("deadline must be later than created_at")
        if type(self.stop_conditions) is not tuple:
            _raise_type("stop_conditions must be an exact tuple")
        if not self.stop_conditions:
            _raise_invariant("stop_conditions must not be empty")
        if any(type(condition) is not StopCondition for condition in self.stop_conditions):
            _raise_type("stop_conditions must contain only StopCondition members")
        stop_values = tuple(condition.value for condition in self.stop_conditions)
        if len(set(stop_values)) != len(stop_values):
            _raise_invariant("stop_conditions must not contain duplicates")
        if stop_values != tuple(sorted(stop_values)):
            _raise_invariant("stop_conditions must be sorted")
        _validate_contract_reference(
            self.expected_remote_precondition_ref,
            "expected_remote_precondition_ref",
        )
        _validate_contract_reference(
            self.success_postcondition_ref,
            "success_postcondition_ref",
        )
        if type(self.compensation) not in {NoCompensation, DeclaredCompensation}:
            _raise_type("compensation must be explicit and predeclared")


@dataclass(frozen=True, slots=True)
class EffectSuccessDetail:
    """Sanitized proof of a verified successful effect."""

    remote_identity: str
    remote_version: str
    provider_request_id: str
    response_fingerprint: str
    postcondition_evidence_refs: tuple[ImmutableReference, ...]

    def __post_init__(self) -> None:
        """Require sanitized remote identity and postcondition evidence."""
        _validate_exact_text(self.remote_identity, "remote_identity")
        _validate_exact_text(self.remote_version, "remote_version")
        _validate_exact_text(self.provider_request_id, "provider_request_id")
        _validate_pattern(self.response_fingerprint, "response_fingerprint", _FINGERPRINT_PATTERN)
        _validate_references(
            self.postcondition_evidence_refs,
            "postcondition_evidence_refs",
            minimum=1,
        )


@dataclass(frozen=True, slots=True)
class EffectFinalFailureDetail:
    """Sanitized proof that no permitted attempt remains."""

    failure_code: FailureCode
    failure_evidence_refs: tuple[ImmutableReference, ...]

    def __post_init__(self) -> None:
        """Require a closed failure code and exact evidence."""
        if type(self.failure_code) is not FailureCode:
            _raise_type("failure_code must be a FailureCode member")
        _validate_references(self.failure_evidence_refs, "failure_evidence_refs", minimum=1)


@dataclass(frozen=True, slots=True)
class EffectCancelledDetail:
    """Proof that cancellation happened before the effect began."""

    cancellation_evidence_refs: tuple[ImmutableReference, ...]

    def __post_init__(self) -> None:
        """Require evidence that cancellation preceded the effect."""
        _validate_references(
            self.cancellation_evidence_refs,
            "cancellation_evidence_refs",
            minimum=1,
        )


@dataclass(frozen=True, slots=True)
class EffectUnknownDetail:
    """Evidence requiring reconciliation of an ambiguous remote outcome."""

    failure_code: FailureCode
    reconciliation_evidence_refs: tuple[ImmutableReference, ...]

    def __post_init__(self) -> None:
        """Require a closed failure and evidence for reconciliation."""
        if type(self.failure_code) is not FailureCode:
            _raise_type("failure_code must be a FailureCode member")
        _validate_references(
            self.reconciliation_evidence_refs,
            "reconciliation_evidence_refs",
            minimum=1,
        )


type EffectReceiptDetail = (
    EffectSuccessDetail | EffectFinalFailureDetail | EffectCancelledDetail | EffectUnknownDetail
)


@dataclass(frozen=True, slots=True)
class EffectReceipt:
    """Exactly one terminal sanitized receipt selected for an effect intent."""

    effect_receipt_id: str
    effect_intent_ref: ImmutableReference
    command_ref: ImmutableReference
    execution_lineage_ref: ImmutableReference
    terminal_status: EffectReceiptStatus
    attempt_count: int
    observed_at: str
    evidence_refs: tuple[ImmutableReference, ...]
    detail: EffectReceiptDetail

    def __post_init__(self) -> None:
        """Require one terminal status with its exact sanitized detail type."""
        _validate_pattern(
            self.effect_receipt_id,
            "effect_receipt_id",
            re.compile(r"^efr_[0-9a-f]{48}$"),
        )
        _validate_reference(
            self.effect_intent_ref,
            "effect_intent_ref",
            allowed_types=frozenset({ReferenceType.EFFECT_INTENT}),
        )
        _validate_reference(
            self.command_ref,
            "command_ref",
            allowed_types=frozenset({ReferenceType.COMMAND}),
        )
        _validate_reference(
            self.execution_lineage_ref,
            "execution_lineage_ref",
            allowed_types=frozenset({ReferenceType.EXECUTION_LINEAGE}),
        )
        if type(self.terminal_status) is not EffectReceiptStatus:
            _raise_type("terminal_status must be an EffectReceiptStatus member")
        _validate_exact_integer(self.attempt_count, "attempt_count", minimum=0)
        _parse_timestamp(self.observed_at, "observed_at")
        _validate_references(self.evidence_refs, "evidence_refs", minimum=1)
        expected_detail_type = {
            EffectReceiptStatus.SUCCEEDED: EffectSuccessDetail,
            EffectReceiptStatus.FAILED_FINAL: EffectFinalFailureDetail,
            EffectReceiptStatus.CANCELLED_BEFORE_EFFECT: EffectCancelledDetail,
            EffectReceiptStatus.OUTCOME_UNKNOWN: EffectUnknownDetail,
        }[self.terminal_status]
        if type(self.detail) is not expected_detail_type:
            _raise_invariant("terminal_status and receipt detail type must match exactly")
        if self.terminal_status is EffectReceiptStatus.CANCELLED_BEFORE_EFFECT:
            if self.attempt_count != 0:
                _raise_invariant("cancel-before-effect must have zero attempts")
        elif self.attempt_count < 1:
            _raise_invariant("an attempted effect receipt must record at least one attempt")


__all__ = [
    "ApplicationCode",
    "CommandEnvelope",
    "CommandPayload",
    "CommandResult",
    "CommandResultCode",
    "CommandSubmissionResolutionCode",
    "ContractReference",
    "DeclaredCompensation",
    "DestinationClass",
    "EffectCancelledDetail",
    "EffectCapability",
    "EffectFinalFailureDetail",
    "EffectIntent",
    "EffectReceipt",
    "EffectReceiptDetail",
    "EffectReceiptStatus",
    "EffectSuccessDetail",
    "EffectType",
    "EffectUnknownDetail",
    "ExpectedVersion",
    "FailureCode",
    "ImmutableReference",
    "NoCompensation",
    "ReferenceType",
    "RetryClass",
    "StopCondition",
]
