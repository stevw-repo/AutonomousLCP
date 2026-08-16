"""Small opaque payloads permitted in Durable Task history."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from asklegal_contracts import canonicalize

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

MAX_HISTORY_PAYLOAD_BYTES = 64 * 1024
MAX_OPAQUE_TOKEN_LENGTH = 160
REVIEW_EVENT_NAME = "register.review-event.v1"
WORKFLOW_NAME = "review_gate_orchestrator"

_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_FINGERPRINT_INVALID = "DURABLE_FINGERPRINT_INVALID"
_PAYLOAD_TOO_LARGE = "DURABLE_PAYLOAD_TOO_LARGE"
_TOKEN_INVALID = "DURABLE_TOKEN_INVALID"


class PayloadBoundaryViolation(ValueError):
    """One scheduler payload violates the closed local history boundary."""


class ReviewResolutionCode(StrEnum):
    """Closed outcomes from authoritative review-event resolution."""

    ACCEPTED = "ACCEPTED"
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    STALE_FINGERPRINT = "STALE_FINGERPRINT"
    UNKNOWN_EVENT = "UNKNOWN_EVENT"
    WRONG_EXECUTION = "WRONG_EXECUTION"


class WorkflowResultCode(StrEnum):
    """Closed terminal outcomes from the synthetic review-gate workflow."""

    EFFECT_RECORDED = "EFFECT_RECORDED"
    EVENT_LIMIT_REACHED = "EVENT_LIMIT_REACHED"
    VERSION_REJECTED = "VERSION_REJECTED"


@dataclass(frozen=True, slots=True)
class WorkflowInput:
    """Exact identity and command references admitted for one workflow."""

    execution_id: str
    workflow_version: str
    build_fingerprint: str
    configuration_fingerprint: str
    contract_fingerprint: str
    input_fingerprint: str
    effect_command_id: str
    effect_command_fingerprint: str

    def __post_init__(self) -> None:
        """Validate all opaque identity fields and the serialized ceiling."""
        _validate_token(self.execution_id)
        _validate_token(self.workflow_version)
        _validate_fingerprint(self.build_fingerprint)
        _validate_fingerprint(self.configuration_fingerprint)
        _validate_fingerprint(self.contract_fingerprint)
        _validate_fingerprint(self.input_fingerprint)
        _validate_token(self.effect_command_id)
        _validate_fingerprint(self.effect_command_fingerprint)
        validate_payload(self.to_json())

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed JSON representation used by the scheduler."""
        return {
            "build_fingerprint": self.build_fingerprint,
            "configuration_fingerprint": self.configuration_fingerprint,
            "contract_fingerprint": self.contract_fingerprint,
            "effect_command_fingerprint": self.effect_command_fingerprint,
            "effect_command_id": self.effect_command_id,
            "execution_id": self.execution_id,
            "input_fingerprint": self.input_fingerprint,
            "workflow_version": self.workflow_version,
        }


@dataclass(frozen=True, slots=True)
class ReviewEventRef:
    """Opaque Scheduler event that must be resolved through the register."""

    event_id: str
    event_fingerprint: str

    def __post_init__(self) -> None:
        """Validate the exact event reference."""
        _validate_token(self.event_id)
        _validate_fingerprint(self.event_fingerprint)
        validate_payload(self.to_json())

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed JSON representation used by the scheduler."""
        return {
            "event_fingerprint": self.event_fingerprint,
            "event_id": self.event_id,
        }


@dataclass(frozen=True, slots=True)
class ReviewEventRequest:
    """Activity request binding an event reference to one execution."""

    execution_id: str
    event_id: str
    event_fingerprint: str

    def __post_init__(self) -> None:
        """Validate the execution-bound event request."""
        _validate_token(self.execution_id)
        _validate_token(self.event_id)
        _validate_fingerprint(self.event_fingerprint)
        validate_payload(self.to_json())

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed JSON representation used by the scheduler."""
        return {
            "event_fingerprint": self.event_fingerprint,
            "event_id": self.event_id,
            "execution_id": self.execution_id,
        }


@dataclass(frozen=True, slots=True)
class ReviewResolution:
    """Closed authoritative outcome of resolving one event reference."""

    code: ReviewResolutionCode
    event_id: str

    def __post_init__(self) -> None:
        """Validate the closed event outcome."""
        _validate_token(self.event_id)
        validate_payload(self.to_json())

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed JSON representation used by the scheduler."""
        return {"code": self.code.value, "event_id": self.event_id}


@dataclass(frozen=True, slots=True)
class EffectRequest:
    """Exact authority that an idempotent effect activity must revalidate."""

    execution_id: str
    workflow_version: str
    build_fingerprint: str
    configuration_fingerprint: str
    contract_fingerprint: str
    input_fingerprint: str
    approval_event_id: str
    command_id: str
    command_fingerprint: str

    def __post_init__(self) -> None:
        """Validate the exact authority supplied to the effect."""
        _validate_token(self.execution_id)
        _validate_token(self.workflow_version)
        _validate_fingerprint(self.build_fingerprint)
        _validate_fingerprint(self.configuration_fingerprint)
        _validate_fingerprint(self.contract_fingerprint)
        _validate_fingerprint(self.input_fingerprint)
        _validate_token(self.approval_event_id)
        _validate_token(self.command_id)
        _validate_fingerprint(self.command_fingerprint)
        validate_payload(self.to_json())

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed JSON representation used by the scheduler."""
        return {
            "approval_event_id": self.approval_event_id,
            "build_fingerprint": self.build_fingerprint,
            "command_fingerprint": self.command_fingerprint,
            "command_id": self.command_id,
            "configuration_fingerprint": self.configuration_fingerprint,
            "contract_fingerprint": self.contract_fingerprint,
            "execution_id": self.execution_id,
            "input_fingerprint": self.input_fingerprint,
            "workflow_version": self.workflow_version,
        }


@dataclass(frozen=True, slots=True)
class EffectResult:
    """Immutable receipt returned for an original or replayed effect command."""

    receipt_id: str
    replayed: bool

    def __post_init__(self) -> None:
        """Validate the opaque effect receipt."""
        _validate_token(self.receipt_id)
        validate_payload(self.to_json())

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed JSON representation used by the scheduler."""
        return {"receipt_id": self.receipt_id, "replayed": self.replayed}


@dataclass(frozen=True, slots=True)
class WorkflowOutput:
    """Small closed terminal result from the synthetic workflow."""

    code: WorkflowResultCode
    accepted_event_id: str | None
    effect_receipt_id: str | None

    def __post_init__(self) -> None:
        """Validate the closed terminal result."""
        if self.accepted_event_id is not None:
            _validate_token(self.accepted_event_id)
        if self.effect_receipt_id is not None:
            _validate_token(self.effect_receipt_id)
        validate_payload(self.to_json())

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed JSON representation used by the scheduler."""
        return {
            "accepted_event_id": self.accepted_event_id,
            "code": self.code.value,
            "effect_receipt_id": self.effect_receipt_id,
        }


def validate_payload(value: JsonValue) -> None:
    """Enforce the repository's initial 64 KiB Scheduler payload ceiling."""
    if len(canonicalize(value)) > MAX_HISTORY_PAYLOAD_BYTES:
        raise PayloadBoundaryViolation(_PAYLOAD_TOO_LARGE)


def _validate_token(value: str) -> None:
    if len(value) > MAX_OPAQUE_TOKEN_LENGTH or _TOKEN_PATTERN.fullmatch(value) is None:
        raise PayloadBoundaryViolation(_TOKEN_INVALID)


def _validate_fingerprint(value: str) -> None:
    if _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise PayloadBoundaryViolation(_FINGERPRINT_INVALID)
