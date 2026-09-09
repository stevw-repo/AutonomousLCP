"""Immutable local acquisition journal and rebuildable checkpoint."""

from __future__ import annotations

import fcntl
import os
import re
import stat
import threading
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Never, Self, TypedDict, TypeIs
from urllib.parse import SplitResult, urlsplit, urlunsplit

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

_JOURNAL_CHILD = "acquisition-journals"
_ENTRIES_CHILD = "entries"
_CHECKPOINT_FILENAME = "checkpoint.json"
_LEASE_SUFFIX = ".acquisition-journal.lock"
_ENTRY_SCHEMA_ID = "asklegal.acquisition-journal-entry"
_CHECKPOINT_SCHEMA_ID = "asklegal.acquisition-checkpoint"
_CYCLE_PROFILE_SCHEMA_ID = "asklegal.acquisition-cycle-safety-profile"
_SCHEMA_VERSION = "1.0.0"
_ZERO_FINGERPRINT = "sha256:" + "0" * 64
_FINGERPRINT_LENGTH = 71
_MAX_ENTRY_BYTES = 131_072
_MAX_CHECKPOINT_BYTES = 16_777_216
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_ASCII_CONTROL_LIMIT = 32
_ASCII_DELETE = 127
_MAX_REDIRECTS = 20
_BATCH_ADDITION_LENGTH = 3
_ENTRY_NAME = re.compile(r"[0-9]{20}\.json", re.ASCII)
_CYCLE_ID = re.compile(r"cyc_[a-z0-9][a-z0-9_]{0,126}", re.ASCII)
_TOKEN = re.compile(r"[A-Z0-9][A-Z0-9_.-]{0,126}", re.ASCII)
_VERSION = re.compile(r"[A-Z0-9][A-Z0-9_.-]{0,126}", re.ASCII)
_WORK_ITEM_ID = re.compile(r"awi_[0-9a-f]{64}", re.ASCII)
_MEDIA_TYPE = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*", re.ASCII)


class AcquisitionJournalError(ValueError):
    """One closed journal contract or filesystem failure."""


class JournalTransition(StrEnum):
    """Closed acquisition work-item state transitions."""

    DISCOVERED = "DISCOVERED"
    CYCLE_SAFETY_PROFILE_BOUND = "CYCLE_SAFETY_PROFILE_BOUND"
    STARTED = "STARTED"
    TRANSPORT_STARTED = "TRANSPORT_STARTED"
    ADMISSION_FAILED_BEFORE_TRANSPORT = "ADMISSION_FAILED_BEFORE_TRANSPORT"
    CAPTURED_VERIFIED = "CAPTURED_VERIFIED"
    IMPORTED_CAPTURE_VERIFIED = "IMPORTED_CAPTURE_VERIFIED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    CONTRACT_REJECTED = "CONTRACT_REJECTED"
    AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    ELAPSED_BUDGET_EXHAUSTED = "ELAPSED_BUDGET_EXHAUSTED"
    TERMINAL_UNAVAILABLE = "TERMINAL_UNAVAILABLE"
    ACCOUNTED_EXCLUDED = "ACCOUNTED_EXCLUDED"


class AcquisitionCycleResult(StrEnum):
    """Closed final cycle results shared with later orchestration."""

    COMPLETE = "COMPLETE"
    NO_CHANGE = "NO_CHANGE"
    INCOMPLETE_RETRYABLE = "INCOMPLETE_RETRYABLE"
    INCOMPLETE_TERMINAL = "INCOMPLETE_TERMINAL"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    EVIDENCE_INTEGRITY_FAILURE = "EVIDENCE_INTEGRITY_FAILURE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


class AcquisitionFailureCode(StrEnum):
    """Closed sanitized request and evidence failure categories."""

    TIMEOUT = "TIMEOUT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    REDIRECT_REJECTED = "REDIRECT_REJECTED"
    BODY_TOO_LARGE = "BODY_TOO_LARGE"
    MEDIA_TYPE_REJECTED = "MEDIA_TYPE_REJECTED"
    EVIDENCE_INTEGRITY_FAILURE = "EVIDENCE_INTEGRITY_FAILURE"
    WORKER_INTERRUPTED = "WORKER_INTERRUPTED"


def _fail(code: str) -> Never:
    raise AcquisitionJournalError(code)


def _text(value: object, *, code: str, maximum: int = 1_024) -> str:
    if (
        not isinstance(value, str)
        or type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(
            ord(character) < _ASCII_CONTROL_LIMIT or ord(character) == _ASCII_DELETE
            for character in value
        )
    ):
        _fail(code)
    return value


def _integer(value: object, *, minimum: int, maximum: int, code: str) -> int:
    if not isinstance(value, int) or type(value) is not int or not minimum <= value <= maximum:
        _fail(code)
    return value


def _fingerprint_value(value: object, *, code: str) -> str:
    if (
        not isinstance(value, str)
        or type(value) is not str
        or len(value) != _FINGERPRINT_LENGTH
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        _fail(code)
    return value


def _timestamp(value: object, *, code: str) -> str:
    text = _text(value, code=code, maximum=40)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        _fail(code)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return text


def _timestamp_epoch_microseconds(value: object, *, code: str) -> int:
    text = _timestamp(value, code=code)
    parsed = datetime.fromisoformat(text).astimezone(UTC)
    elapsed = parsed - datetime(1970, 1, 1, tzinfo=UTC)
    return elapsed.days * 86_400 * 1_000_000 + elapsed.seconds * 1_000_000 + elapsed.microseconds


def _exact_mapping(value: JsonValue, keys: frozenset[str], *, code: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict) or type(value) is not dict or frozenset(value) != keys:
        _fail(code)
    return value


def _json_object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if not isinstance(checked, dict) or type(checked) is not dict:
        _fail("JOURNAL_ENTRY_INVALID")
    return checked


def _is_exact_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _fingerprint(body: object) -> str:
    return f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"


def _normalize_locator(value: object) -> str:
    locator = _text(value, code="WORK_ITEM_INVALID", maximum=4_096)
    try:
        parsed = urlsplit(locator)
        port = parsed.port
    except ValueError:
        _fail("WORK_ITEM_INVALID")
    if (
        parsed.scheme.lower() != "https"
        or parsed.scheme != parsed.scheme.lower()
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(ord(character) > _ASCII_DELETE for character in parsed.hostname)
        or port not in {None, 443}
        or not parsed.path.startswith("/")
        or any(part in {".", ".."} for part in parsed.path.split("/"))
    ):
        _fail("WORK_ITEM_INVALID")
    host = parsed.hostname.lower()
    authority = host if port is None else f"{host}:443"
    normalized = urlunsplit(SplitResult("https", authority, parsed.path, parsed.query, ""))
    if locator != normalized:
        _fail("WORK_ITEM_INVALID")
    return locator


@dataclass(frozen=True, slots=True)
class WorkItemIdentity:
    """Canonical immutable identity for one requestable acquisition unit."""

    work_item_id: str
    source_family: str
    source_role: str
    cycle_id: str
    observation_cutoff: str
    procedure_version: str
    locator: str
    stage: str
    parent_id: str
    media_type: str
    max_bytes: int

    def __post_init__(self) -> None:
        """Enforce the exact same fact and ID contract as JSON parsing."""
        body = _validated_work_item_body(self)
        expected = _work_item_id(body)
        if type(self.work_item_id) is not str or self.work_item_id != expected:
            _fail("WORK_ITEM_INVALID")

    @classmethod
    def issue(  # noqa: PLR0913 - the stable ID binds every listed request fact.
        cls,
        *,
        source_family: str,
        source_role: str,
        cycle_id: str,
        observation_cutoff: str,
        procedure_version: str,
        locator: str,
        stage: str,
        parent_id: str,
        media_type: str,
        max_bytes: int,
    ) -> Self:
        """Issue one stable ID from all normalized request facts."""
        provisional = {
            "source_family": source_family,
            "source_role": source_role,
            "cycle_id": cycle_id,
            "observation_cutoff": observation_cutoff,
            "procedure_version": procedure_version,
            "locator": locator,
            "stage": stage,
            "parent_id": parent_id,
            "media_type": media_type,
            "max_bytes": max_bytes,
        }
        body = _validated_work_item_mapping(checked_json_value(provisional))
        return cls(_work_item_id(body), **body)

    @classmethod
    def from_json(cls, value: JsonValue) -> Self:
        """Parse one closed work-item object and verify its derived ID."""
        document = _exact_mapping(
            value,
            frozenset(
                {
                    "work_item_id",
                    "source_family",
                    "source_role",
                    "cycle_id",
                    "observation_cutoff",
                    "procedure_version",
                    "locator",
                    "stage",
                    "parent_id",
                    "media_type",
                    "max_bytes",
                }
            ),
            code="WORK_ITEM_INVALID",
        )
        body = _validated_work_item_mapping(
            _json_object({key: member for key, member in document.items() if key != "work_item_id"})
        )
        return cls(_text(document["work_item_id"], code="WORK_ITEM_INVALID"), **body)

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed canonical JSON shape."""
        return _json_object({"work_item_id": self.work_item_id, **_work_item_body(self)})


class _WorkItemFacts(TypedDict):
    source_family: str
    source_role: str
    cycle_id: str
    observation_cutoff: str
    procedure_version: str
    locator: str
    stage: str
    parent_id: str
    media_type: str
    max_bytes: int


def _validated_work_item_body(item: WorkItemIdentity) -> _WorkItemFacts:
    try:
        return _validated_work_item_values(
            source_family=item.source_family,
            source_role=item.source_role,
            cycle_id=item.cycle_id,
            observation_cutoff=item.observation_cutoff,
            procedure_version=item.procedure_version,
            locator=item.locator,
            stage=item.stage,
            parent_id=item.parent_id,
            media_type=item.media_type,
            max_bytes=item.max_bytes,
        )
    except (AttributeError, TypeError, ValueError) as error:
        if isinstance(error, AcquisitionJournalError):
            raise
        msg = "WORK_ITEM_INVALID"
        raise AcquisitionJournalError(msg) from error


def _validated_work_item_mapping(value: JsonValue) -> _WorkItemFacts:
    document = _exact_mapping(
        value,
        frozenset(
            {
                "source_family",
                "source_role",
                "cycle_id",
                "observation_cutoff",
                "procedure_version",
                "locator",
                "stage",
                "parent_id",
                "media_type",
                "max_bytes",
            }
        ),
        code="WORK_ITEM_INVALID",
    )
    return _validated_work_item_values(
        source_family=document["source_family"],
        source_role=document["source_role"],
        cycle_id=document["cycle_id"],
        observation_cutoff=document["observation_cutoff"],
        procedure_version=document["procedure_version"],
        locator=document["locator"],
        stage=document["stage"],
        parent_id=document["parent_id"],
        media_type=document["media_type"],
        max_bytes=document["max_bytes"],
    )


def _validated_work_item_values(**values: object) -> _WorkItemFacts:
    family = _text(values["source_family"], code="WORK_ITEM_INVALID", maximum=32)
    if family not in {"CASES", "LEGISLATION"}:
        _fail("WORK_ITEM_INVALID")
    role = _text(values["source_role"], code="WORK_ITEM_INVALID", maximum=127)
    cycle_id = _text(values["cycle_id"], code="WORK_ITEM_INVALID", maximum=127)
    procedure = _text(values["procedure_version"], code="WORK_ITEM_INVALID", maximum=127)
    stage = _text(values["stage"], code="WORK_ITEM_INVALID", maximum=127)
    parent_id = _text(values["parent_id"], code="WORK_ITEM_INVALID", maximum=512)
    media_type = _text(values["media_type"], code="WORK_ITEM_INVALID", maximum=127)
    if (
        _TOKEN.fullmatch(role) is None
        or _CYCLE_ID.fullmatch(cycle_id) is None
        or _VERSION.fullmatch(procedure) is None
        or _TOKEN.fullmatch(stage) is None
        or _MEDIA_TYPE.fullmatch(media_type) is None
    ):
        _fail("WORK_ITEM_INVALID")
    return _WorkItemFacts(
        source_family=family,
        source_role=role,
        cycle_id=cycle_id,
        observation_cutoff=_timestamp(values["observation_cutoff"], code="WORK_ITEM_INVALID"),
        procedure_version=procedure,
        locator=_normalize_locator(values["locator"]),
        stage=stage,
        parent_id=parent_id,
        media_type=media_type,
        max_bytes=_integer(
            values["max_bytes"], minimum=1, maximum=1_073_741_824, code="WORK_ITEM_INVALID"
        ),
    )


def _work_item_body(item: WorkItemIdentity) -> _WorkItemFacts:
    return _WorkItemFacts(
        source_family=item.source_family,
        source_role=item.source_role,
        cycle_id=item.cycle_id,
        observation_cutoff=item.observation_cutoff,
        procedure_version=item.procedure_version,
        locator=item.locator,
        stage=item.stage,
        parent_id=item.parent_id,
        media_type=item.media_type,
        max_bytes=item.max_bytes,
    )


def _work_item_id(body: object) -> str:
    return f"awi_{sha256(canonicalize(checked_json_value(body))).hexdigest()}"


@dataclass(frozen=True, slots=True)
class DiscoveredPayload:
    """Discovery bound to the durable cycle-wide elapsed-budget origin."""

    cycle_started_at_epoch_us: int

    def __post_init__(self) -> None:
        """Validate the exact scheduler origin."""
        _integer(
            self.cycle_started_at_epoch_us,
            minimum=0,
            maximum=9_007_199_254_740_991,
            code="TRANSITION_PAYLOAD_INVALID",
        )

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact durable scheduler discovery shape."""
        return {"cycle_started_at_epoch_us": self.cycle_started_at_epoch_us}


@dataclass(frozen=True, slots=True)
class ElapsedBudgetExhaustedPayload:
    """One durable cycle-wide elapsed safety stop without replacing item disposition."""

    maximum_elapsed_seconds: int

    def __post_init__(self) -> None:
        """Bind the marker to the exact admitted elapsed ceiling."""
        _integer(
            self.maximum_elapsed_seconds,
            minimum=0,
            maximum=31_536_000,
            code="TRANSITION_PAYLOAD_INVALID",
        )

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact elapsed-budget marker payload."""
        return {"maximum_elapsed_seconds": self.maximum_elapsed_seconds}


@dataclass(frozen=True, slots=True)
class StartedPayload:
    """One exact request-attempt start."""

    attempt: int
    started_at_epoch_us: int
    host_not_before_epoch_us: int
    reserved_redirects: int

    def __post_init__(self) -> None:
        """Reject a non-positive or non-exact attempt number."""
        _integer(self.attempt, minimum=1, maximum=1_000_000, code="TRANSITION_PAYLOAD_INVALID")
        started = _integer(
            self.started_at_epoch_us,
            minimum=0,
            maximum=9_007_199_254_740_991,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        host_not_before = _integer(
            self.host_not_before_epoch_us,
            minimum=0,
            maximum=9_007_199_254_740_991,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _integer(
            self.reserved_redirects,
            minimum=0,
            maximum=_MAX_REDIRECTS,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        if host_not_before < started:
            _fail("TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact started payload."""
        return {
            "attempt": self.attempt,
            "started_at_epoch_us": self.started_at_epoch_us,
            "host_not_before_epoch_us": self.host_not_before_epoch_us,
            "reserved_redirects": self.reserved_redirects,
        }


@dataclass(frozen=True, slots=True)
class CycleSafetyProfilePayload:
    """Immutable cycle controls bound before any request starts."""

    schema_id: str
    schema_version: str
    maximum_starts: int
    maximum_retained_bytes: int
    maximum_elapsed_seconds: int
    maximum_redirects: int
    per_host_limit: int
    minimum_start_interval_ns: int
    maximum_attempts_per_item: int
    maximum_redirects_per_start: int
    cycle_started_at_epoch_us: int

    def __post_init__(self) -> None:
        """Reject profile drift primitives and invalid cycle origins."""
        if (
            type(self.schema_id) is not str
            or self.schema_id != _CYCLE_PROFILE_SCHEMA_ID
            or type(self.schema_version) is not str
            or self.schema_version != _SCHEMA_VERSION
        ):
            _fail("TRANSITION_PAYLOAD_INVALID")
        _integer(
            self.maximum_starts,
            minimum=0,
            maximum=1_000_000_000,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _integer(
            self.maximum_retained_bytes,
            minimum=0,
            maximum=1_152_921_504_606_846_976,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _integer(
            self.maximum_elapsed_seconds,
            minimum=0,
            maximum=31_536_000,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _integer(
            self.maximum_redirects,
            minimum=0,
            maximum=1_000_000_000,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _integer(
            self.per_host_limit,
            minimum=1,
            maximum=4,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _integer(
            self.minimum_start_interval_ns,
            minimum=0,
            maximum=86_400_000_000_000,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _integer(
            self.maximum_attempts_per_item,
            minimum=1,
            maximum=1_000_000,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _integer(
            self.maximum_redirects_per_start,
            minimum=0,
            maximum=_MAX_REDIRECTS,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _integer(
            self.cycle_started_at_epoch_us,
            minimum=0,
            maximum=9_007_199_254_740_991,
            code="TRANSITION_PAYLOAD_INVALID",
        )

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact versioned safety profile."""
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "maximum_starts": self.maximum_starts,
            "maximum_retained_bytes": self.maximum_retained_bytes,
            "maximum_elapsed_seconds": self.maximum_elapsed_seconds,
            "maximum_redirects": self.maximum_redirects,
            "per_host_limit": self.per_host_limit,
            "minimum_start_interval_ns": self.minimum_start_interval_ns,
            "maximum_attempts_per_item": self.maximum_attempts_per_item,
            "maximum_redirects_per_start": self.maximum_redirects_per_start,
            "cycle_started_at_epoch_us": self.cycle_started_at_epoch_us,
        }


@dataclass(frozen=True, slots=True)
class TransportStartedPayload:
    """Actual physical transport-start time observed by a worker and recorded by its coordinator."""

    attempt: int
    started_at_epoch_us: int
    host_not_before_epoch_us: int

    def __post_init__(self) -> None:
        """Bind one actual start and its exact host pacing deadline."""
        _integer(self.attempt, minimum=1, maximum=1_000_000, code="TRANSITION_PAYLOAD_INVALID")
        started = _integer(
            self.started_at_epoch_us,
            minimum=0,
            maximum=9_007_199_254_740_991,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        host_not_before = _integer(
            self.host_not_before_epoch_us,
            minimum=0,
            maximum=9_007_199_254_740_991,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        if host_not_before < started:
            _fail("TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact physical-start payload."""
        return {
            "attempt": self.attempt,
            "started_at_epoch_us": self.started_at_epoch_us,
            "host_not_before_epoch_us": self.host_not_before_epoch_us,
        }


@dataclass(frozen=True, slots=True)
class CapturedVerifiedPayload:
    """Verified retained-body facts for one completed request attempt."""

    attempt: int
    status: int
    media_type: str
    final_url: str
    redirect_chain: tuple[str, ...]
    body_length: int
    content_fingerprint: str
    object_ref: str
    read_back_verified: bool

    def __post_init__(self) -> None:
        """Validate every retained-body and read-back fact."""
        _integer(self.attempt, minimum=1, maximum=1_000_000, code="TRANSITION_PAYLOAD_INVALID")
        _integer(self.status, minimum=100, maximum=599, code="TRANSITION_PAYLOAD_INVALID")
        media_type = _text(self.media_type, code="TRANSITION_PAYLOAD_INVALID", maximum=127)
        if _MEDIA_TYPE.fullmatch(media_type) is None:
            _fail("TRANSITION_PAYLOAD_INVALID")
        _normalize_payload_url(self.final_url)
        redirect_chain: object = self.redirect_chain
        if not _is_exact_tuple(redirect_chain) or len(redirect_chain) > _MAX_REDIRECTS:
            _fail("TRANSITION_PAYLOAD_INVALID")
        for locator in redirect_chain:
            _normalize_payload_url(locator)
        _integer(
            self.body_length,
            minimum=1,
            maximum=1_073_741_824,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _fingerprint_value(self.content_fingerprint, code="TRANSITION_PAYLOAD_INVALID")
        _object_reference(self.object_ref)
        if type(self.read_back_verified) is not bool or not self.read_back_verified:
            _fail("TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact captured-and-verified payload."""
        return {
            "attempt": self.attempt,
            "status": self.status,
            "media_type": self.media_type,
            "final_url": self.final_url,
            "redirect_chain": list(self.redirect_chain),
            "body_length": self.body_length,
            "content_fingerprint": self.content_fingerprint,
            "object_ref": self.object_ref,
            "read_back_verified": self.read_back_verified,
        }


@dataclass(frozen=True, slots=True)
class ImportedCaptureVerifiedPayload:
    """Verified retained evidence imported without asserting a new request."""

    source_attempt_id: str
    source_report_fingerprint: str
    authority_manifest_fingerprint: str
    execution_authorization_fingerprint: str
    status: int
    media_type: str
    final_url: str
    body_length: int
    content_fingerprint: str
    object_ref: str
    read_back_verified: bool

    def __post_init__(self) -> None:
        """Validate every original report/object fact and successful read-back."""
        _text(self.source_attempt_id, code="TRANSITION_PAYLOAD_INVALID", maximum=255)
        _fingerprint_value(self.source_report_fingerprint, code="TRANSITION_PAYLOAD_INVALID")
        _fingerprint_value(self.authority_manifest_fingerprint, code="TRANSITION_PAYLOAD_INVALID")
        _fingerprint_value(
            self.execution_authorization_fingerprint, code="TRANSITION_PAYLOAD_INVALID"
        )
        _integer(self.status, minimum=100, maximum=599, code="TRANSITION_PAYLOAD_INVALID")
        media_type = _text(self.media_type, code="TRANSITION_PAYLOAD_INVALID", maximum=127)
        if _MEDIA_TYPE.fullmatch(media_type) is None:
            _fail("TRANSITION_PAYLOAD_INVALID")
        _normalize_payload_url(self.final_url)
        _integer(
            self.body_length,
            minimum=1,
            maximum=1_073_741_824,
            code="TRANSITION_PAYLOAD_INVALID",
        )
        _fingerprint_value(self.content_fingerprint, code="TRANSITION_PAYLOAD_INVALID")
        _object_reference(self.object_ref)
        if type(self.read_back_verified) is not bool or not self.read_back_verified:
            _fail("TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed offline-import payload."""
        return {
            "source_attempt_id": self.source_attempt_id,
            "source_report_fingerprint": self.source_report_fingerprint,
            "authority_manifest_fingerprint": self.authority_manifest_fingerprint,
            "execution_authorization_fingerprint": self.execution_authorization_fingerprint,
            "status": self.status,
            "media_type": self.media_type,
            "final_url": self.final_url,
            "body_length": self.body_length,
            "content_fingerprint": self.content_fingerprint,
            "object_ref": self.object_ref,
            "read_back_verified": self.read_back_verified,
        }


def _normalize_payload_url(value: object) -> str:
    try:
        return _normalize_locator(value)
    except AcquisitionJournalError as error:
        msg = "TRANSITION_PAYLOAD_INVALID"
        raise AcquisitionJournalError(msg) from error


def _object_reference(value: object) -> str:
    reference = _text(value, code="TRANSITION_PAYLOAD_INVALID", maximum=2_048)
    if (
        reference.startswith("/")
        or "\\" in reference
        or any(part in {"", ".", ".."} for part in reference.split("/"))
    ):
        _fail("TRANSITION_PAYLOAD_INVALID")
    return reference


def _failure_code(value: object) -> AcquisitionFailureCode:
    if not isinstance(value, AcquisitionFailureCode) or type(value) is not AcquisitionFailureCode:
        _fail("TRANSITION_PAYLOAD_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class RetryableFailurePayload:
    """One retryable attempt failure and its earliest next eligibility."""

    attempt: int
    failure_code: AcquisitionFailureCode
    retry_not_before: str

    def __post_init__(self) -> None:
        """Validate one retryable failure and retry time."""
        _integer(self.attempt, minimum=1, maximum=1_000_000, code="TRANSITION_PAYLOAD_INVALID")
        _failure_code(self.failure_code)
        _timestamp(self.retry_not_before, code="TRANSITION_PAYLOAD_INVALID")
        if self.failure_code in {
            AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED,
            AcquisitionFailureCode.EVIDENCE_INTEGRITY_FAILURE,
        }:
            _fail("TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact retryable-failure payload."""
        return {
            "attempt": self.attempt,
            "failure_code": self.failure_code.value,
            "retry_not_before": self.retry_not_before,
        }


@dataclass(frozen=True, slots=True)
class AdmissionFailedBeforeTransportPayload:
    """One proved marker-free admission failure and its earliest next eligibility."""

    attempt: int
    retry_not_before: str

    def __post_init__(self) -> None:
        """Validate exact attempt and retry-time primitives before lifecycle binding."""
        _integer(self.attempt, minimum=1, maximum=1_000_000, code="TRANSITION_PAYLOAD_INVALID")
        _timestamp(self.retry_not_before, code="TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact proved no-transport disposition payload."""
        return {
            "attempt": self.attempt,
            "retry_not_before": self.retry_not_before,
        }


@dataclass(frozen=True, slots=True)
class ContractRejectedPayload:
    """One fail-closed source-contract rejection."""

    attempt: int
    failure_code: AcquisitionFailureCode

    def __post_init__(self) -> None:
        """Require the sole contract-rejection failure category."""
        _integer(self.attempt, minimum=1, maximum=1_000_000, code="TRANSITION_PAYLOAD_INVALID")
        if _failure_code(self.failure_code) is not AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED:
            _fail("TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact contract-rejection payload."""
        return {"attempt": self.attempt, "failure_code": self.failure_code.value}


@dataclass(frozen=True, slots=True)
class AuthorizationRejectedPayload:
    """One exact attempt stopped by missing or invalid read authorization."""

    attempt: int

    def __post_init__(self) -> None:
        """Require one exact positive physical attempt."""
        _integer(self.attempt, minimum=1, maximum=1_000_000, code="TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact authorization-rejection payload."""
        return {"attempt": self.attempt}


@dataclass(frozen=True, slots=True)
class RetryExhaustedPayload:
    """Durable policy closure after the preceding retryable attempt used the ceiling."""

    attempt: int

    def __post_init__(self) -> None:
        """Bind exhaustion to the exact preceding physical attempt."""
        _integer(self.attempt, minimum=1, maximum=1_000_000, code="TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact retry-exhaustion payload without relabeling its failure."""
        return {"attempt": self.attempt}


@dataclass(frozen=True, slots=True)
class TerminalUnavailablePayload:
    """One non-retryable unavailable source result."""

    attempt: int
    failure_code: AcquisitionFailureCode

    def __post_init__(self) -> None:
        """Require one admitted terminal-unavailable category."""
        _integer(self.attempt, minimum=1, maximum=1_000_000, code="TRANSITION_PAYLOAD_INVALID")
        if _failure_code(self.failure_code) not in {
            AcquisitionFailureCode.SOURCE_UNAVAILABLE,
            AcquisitionFailureCode.TIMEOUT,
            AcquisitionFailureCode.RATE_LIMITED,
            AcquisitionFailureCode.EVIDENCE_INTEGRITY_FAILURE,
        }:
            _fail("TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact terminal-unavailable payload."""
        return {"attempt": self.attempt, "failure_code": self.failure_code.value}


@dataclass(frozen=True, slots=True)
class AccountedExcludedPayload:
    """One exact no-request exclusion reason."""

    reason_code: str

    def __post_init__(self) -> None:
        """Require one closed exclusion reason."""
        reason = _text(self.reason_code, code="TRANSITION_PAYLOAD_INVALID", maximum=127)
        if reason not in {
            "OUTSIDE_OBSERVATION_WINDOW",
            "OUTSIDE_V1_SCOPE",
            "DUPLICATE_OFFICIAL_IDENTITY",
            "SUPERSEDED_OFFICIAL_ARTIFACT",
            "SOURCE_RELATIONSHIP_RETAINED",
        }:
            _fail("TRANSITION_PAYLOAD_INVALID")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact accounted-exclusion payload."""
        return {"reason_code": self.reason_code}


type JournalPayload = (
    DiscoveredPayload
    | CycleSafetyProfilePayload
    | ElapsedBudgetExhaustedPayload
    | StartedPayload
    | TransportStartedPayload
    | AdmissionFailedBeforeTransportPayload
    | CapturedVerifiedPayload
    | ImportedCaptureVerifiedPayload
    | RetryableFailurePayload
    | ContractRejectedPayload
    | AuthorizationRejectedPayload
    | RetryExhaustedPayload
    | TerminalUnavailablePayload
    | AccountedExcludedPayload
)


_PAYLOAD_TYPES: dict[JournalTransition, type[JournalPayload]] = {
    JournalTransition.DISCOVERED: DiscoveredPayload,
    JournalTransition.CYCLE_SAFETY_PROFILE_BOUND: CycleSafetyProfilePayload,
    JournalTransition.ELAPSED_BUDGET_EXHAUSTED: ElapsedBudgetExhaustedPayload,
    JournalTransition.STARTED: StartedPayload,
    JournalTransition.TRANSPORT_STARTED: TransportStartedPayload,
    JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT: AdmissionFailedBeforeTransportPayload,
    JournalTransition.CAPTURED_VERIFIED: CapturedVerifiedPayload,
    JournalTransition.IMPORTED_CAPTURE_VERIFIED: ImportedCaptureVerifiedPayload,
    JournalTransition.RETRYABLE_FAILURE: RetryableFailurePayload,
    JournalTransition.CONTRACT_REJECTED: ContractRejectedPayload,
    JournalTransition.AUTHORIZATION_REJECTED: AuthorizationRejectedPayload,
    JournalTransition.RETRY_EXHAUSTED: RetryExhaustedPayload,
    JournalTransition.TERMINAL_UNAVAILABLE: TerminalUnavailablePayload,
    JournalTransition.ACCOUNTED_EXCLUDED: AccountedExcludedPayload,
}


def _payload_from_json(  # noqa: C901, PLR0911, PLR0912 - one closed decoder per transition.
    transition: JournalTransition, value: JsonValue
) -> JournalPayload:
    if transition is JournalTransition.DISCOVERED:
        document = _exact_mapping(
            value,
            frozenset({"cycle_started_at_epoch_us"}),
            code="JOURNAL_ENTRY_INVALID",
        )
        return DiscoveredPayload(
            _integer(
                document["cycle_started_at_epoch_us"],
                minimum=0,
                maximum=9_007_199_254_740_991,
                code="JOURNAL_ENTRY_INVALID",
            )
        )
    if transition is JournalTransition.CYCLE_SAFETY_PROFILE_BOUND:
        document = _exact_mapping(
            value,
            frozenset(
                {
                    "schema_id",
                    "schema_version",
                    "maximum_starts",
                    "maximum_retained_bytes",
                    "maximum_elapsed_seconds",
                    "maximum_redirects",
                    "per_host_limit",
                    "minimum_start_interval_ns",
                    "maximum_attempts_per_item",
                    "maximum_redirects_per_start",
                    "cycle_started_at_epoch_us",
                }
            ),
            code="JOURNAL_ENTRY_INVALID",
        )
        return CycleSafetyProfilePayload(
            schema_id=_text(document["schema_id"], code="JOURNAL_ENTRY_INVALID"),
            schema_version=_text(document["schema_version"], code="JOURNAL_ENTRY_INVALID"),
            maximum_starts=_integer(
                document["maximum_starts"],
                minimum=0,
                maximum=1_000_000_000,
                code="JOURNAL_ENTRY_INVALID",
            ),
            maximum_retained_bytes=_integer(
                document["maximum_retained_bytes"],
                minimum=0,
                maximum=1_152_921_504_606_846_976,
                code="JOURNAL_ENTRY_INVALID",
            ),
            maximum_elapsed_seconds=_integer(
                document["maximum_elapsed_seconds"],
                minimum=0,
                maximum=31_536_000,
                code="JOURNAL_ENTRY_INVALID",
            ),
            maximum_redirects=_integer(
                document["maximum_redirects"],
                minimum=0,
                maximum=1_000_000_000,
                code="JOURNAL_ENTRY_INVALID",
            ),
            per_host_limit=_integer(
                document["per_host_limit"],
                minimum=1,
                maximum=4,
                code="JOURNAL_ENTRY_INVALID",
            ),
            minimum_start_interval_ns=_integer(
                document["minimum_start_interval_ns"],
                minimum=0,
                maximum=86_400_000_000_000,
                code="JOURNAL_ENTRY_INVALID",
            ),
            maximum_attempts_per_item=_integer(
                document["maximum_attempts_per_item"],
                minimum=1,
                maximum=1_000_000,
                code="JOURNAL_ENTRY_INVALID",
            ),
            maximum_redirects_per_start=_integer(
                document["maximum_redirects_per_start"],
                minimum=0,
                maximum=_MAX_REDIRECTS,
                code="JOURNAL_ENTRY_INVALID",
            ),
            cycle_started_at_epoch_us=_integer(
                document["cycle_started_at_epoch_us"],
                minimum=0,
                maximum=9_007_199_254_740_991,
                code="JOURNAL_ENTRY_INVALID",
            ),
        )
    if transition is JournalTransition.ELAPSED_BUDGET_EXHAUSTED:
        document = _exact_mapping(
            value,
            frozenset({"maximum_elapsed_seconds"}),
            code="JOURNAL_ENTRY_INVALID",
        )
        return ElapsedBudgetExhaustedPayload(
            _integer(
                document["maximum_elapsed_seconds"],
                minimum=0,
                maximum=31_536_000,
                code="JOURNAL_ENTRY_INVALID",
            )
        )
    if transition is JournalTransition.STARTED:
        document = _exact_mapping(
            value,
            frozenset(
                {
                    "attempt",
                    "started_at_epoch_us",
                    "host_not_before_epoch_us",
                    "reserved_redirects",
                }
            ),
            code="JOURNAL_ENTRY_INVALID",
        )
        return StartedPayload(
            _integer(
                document["attempt"], minimum=1, maximum=1_000_000, code="JOURNAL_ENTRY_INVALID"
            ),
            _integer(
                document["started_at_epoch_us"],
                minimum=0,
                maximum=9_007_199_254_740_991,
                code="JOURNAL_ENTRY_INVALID",
            ),
            _integer(
                document["host_not_before_epoch_us"],
                minimum=0,
                maximum=9_007_199_254_740_991,
                code="JOURNAL_ENTRY_INVALID",
            ),
            _integer(
                document["reserved_redirects"],
                minimum=0,
                maximum=_MAX_REDIRECTS,
                code="JOURNAL_ENTRY_INVALID",
            ),
        )
    if transition is JournalTransition.TRANSPORT_STARTED:
        document = _exact_mapping(
            value,
            frozenset({"attempt", "started_at_epoch_us", "host_not_before_epoch_us"}),
            code="JOURNAL_ENTRY_INVALID",
        )
        return TransportStartedPayload(
            attempt=_integer(
                document["attempt"],
                minimum=1,
                maximum=1_000_000,
                code="JOURNAL_ENTRY_INVALID",
            ),
            started_at_epoch_us=_integer(
                document["started_at_epoch_us"],
                minimum=0,
                maximum=9_007_199_254_740_991,
                code="JOURNAL_ENTRY_INVALID",
            ),
            host_not_before_epoch_us=_integer(
                document["host_not_before_epoch_us"],
                minimum=0,
                maximum=9_007_199_254_740_991,
                code="JOURNAL_ENTRY_INVALID",
            ),
        )
    if transition is JournalTransition.CAPTURED_VERIFIED:
        document = _exact_mapping(
            value,
            frozenset(
                {
                    "attempt",
                    "status",
                    "media_type",
                    "final_url",
                    "redirect_chain",
                    "body_length",
                    "content_fingerprint",
                    "object_ref",
                    "read_back_verified",
                }
            ),
            code="JOURNAL_ENTRY_INVALID",
        )
        redirects = document["redirect_chain"]
        if not isinstance(redirects, list) or type(redirects) is not list:
            _fail("JOURNAL_ENTRY_INVALID")
        return CapturedVerifiedPayload(
            _integer(
                document["attempt"], minimum=1, maximum=1_000_000, code="JOURNAL_ENTRY_INVALID"
            ),
            _integer(document["status"], minimum=100, maximum=599, code="JOURNAL_ENTRY_INVALID"),
            _text(document["media_type"], code="JOURNAL_ENTRY_INVALID"),
            _text(document["final_url"], code="JOURNAL_ENTRY_INVALID", maximum=4_096),
            tuple(_text(item, code="JOURNAL_ENTRY_INVALID", maximum=4_096) for item in redirects),
            _integer(
                document["body_length"],
                minimum=1,
                maximum=1_073_741_824,
                code="JOURNAL_ENTRY_INVALID",
            ),
            _fingerprint_value(document["content_fingerprint"], code="JOURNAL_ENTRY_INVALID"),
            _text(document["object_ref"], code="JOURNAL_ENTRY_INVALID", maximum=2_048),
            _boolean(document["read_back_verified"], code="JOURNAL_ENTRY_INVALID"),
        )
    if transition is JournalTransition.IMPORTED_CAPTURE_VERIFIED:
        document = _exact_mapping(
            value,
            frozenset(
                {
                    "source_attempt_id",
                    "source_report_fingerprint",
                    "authority_manifest_fingerprint",
                    "execution_authorization_fingerprint",
                    "status",
                    "media_type",
                    "final_url",
                    "body_length",
                    "content_fingerprint",
                    "object_ref",
                    "read_back_verified",
                }
            ),
            code="JOURNAL_ENTRY_INVALID",
        )
        return ImportedCaptureVerifiedPayload(
            source_attempt_id=_text(
                document["source_attempt_id"], code="JOURNAL_ENTRY_INVALID", maximum=255
            ),
            source_report_fingerprint=_fingerprint_value(
                document["source_report_fingerprint"], code="JOURNAL_ENTRY_INVALID"
            ),
            authority_manifest_fingerprint=_fingerprint_value(
                document["authority_manifest_fingerprint"], code="JOURNAL_ENTRY_INVALID"
            ),
            execution_authorization_fingerprint=_fingerprint_value(
                document["execution_authorization_fingerprint"], code="JOURNAL_ENTRY_INVALID"
            ),
            status=_integer(
                document["status"], minimum=100, maximum=599, code="JOURNAL_ENTRY_INVALID"
            ),
            media_type=_text(document["media_type"], code="JOURNAL_ENTRY_INVALID"),
            final_url=_text(document["final_url"], code="JOURNAL_ENTRY_INVALID", maximum=4_096),
            body_length=_integer(
                document["body_length"],
                minimum=1,
                maximum=1_073_741_824,
                code="JOURNAL_ENTRY_INVALID",
            ),
            content_fingerprint=_fingerprint_value(
                document["content_fingerprint"], code="JOURNAL_ENTRY_INVALID"
            ),
            object_ref=_text(document["object_ref"], code="JOURNAL_ENTRY_INVALID", maximum=2_048),
            read_back_verified=_boolean(
                document["read_back_verified"], code="JOURNAL_ENTRY_INVALID"
            ),
        )
    if transition in {
        JournalTransition.RETRYABLE_FAILURE,
        JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
    }:
        expected_keys = (
            frozenset({"attempt", "failure_code", "retry_not_before"})
            if transition is JournalTransition.RETRYABLE_FAILURE
            else frozenset({"attempt", "retry_not_before"})
        )
        document = _exact_mapping(
            value,
            expected_keys,
            code="JOURNAL_ENTRY_INVALID",
        )
        attempt = _integer(
            document["attempt"], minimum=1, maximum=1_000_000, code="JOURNAL_ENTRY_INVALID"
        )
        retry_not_before = _text(document["retry_not_before"], code="JOURNAL_ENTRY_INVALID")
        if transition is JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT:
            return AdmissionFailedBeforeTransportPayload(attempt, retry_not_before)
        return RetryableFailurePayload(
            attempt,
            _failure_code_from_json(document["failure_code"]),
            retry_not_before,
        )
    if transition in {JournalTransition.CONTRACT_REJECTED, JournalTransition.TERMINAL_UNAVAILABLE}:
        document = _exact_mapping(
            value, frozenset({"attempt", "failure_code"}), code="JOURNAL_ENTRY_INVALID"
        )
        arguments = (
            _integer(
                document["attempt"], minimum=1, maximum=1_000_000, code="JOURNAL_ENTRY_INVALID"
            ),
            _failure_code_from_json(document["failure_code"]),
        )
        if transition is JournalTransition.CONTRACT_REJECTED:
            return ContractRejectedPayload(*arguments)
        return TerminalUnavailablePayload(*arguments)
    if transition in {
        JournalTransition.AUTHORIZATION_REJECTED,
        JournalTransition.RETRY_EXHAUSTED,
    }:
        document = _exact_mapping(
            value,
            frozenset({"attempt"}),
            code="JOURNAL_ENTRY_INVALID",
        )
        attempt = _integer(
            document["attempt"],
            minimum=1,
            maximum=1_000_000,
            code="JOURNAL_ENTRY_INVALID",
        )
        if transition is JournalTransition.AUTHORIZATION_REJECTED:
            return AuthorizationRejectedPayload(attempt)
        return RetryExhaustedPayload(attempt)
    document = _exact_mapping(value, frozenset({"reason_code"}), code="JOURNAL_ENTRY_INVALID")
    return AccountedExcludedPayload(_text(document["reason_code"], code="JOURNAL_ENTRY_INVALID"))


def _boolean(value: object, *, code: str) -> bool:
    if not isinstance(value, bool) or type(value) is not bool:
        _fail(code)
    return value


def _failure_code_from_json(value: object) -> AcquisitionFailureCode:
    try:
        if not isinstance(value, str) or type(value) is not str:
            _fail("JOURNAL_ENTRY_INVALID")
        return AcquisitionFailureCode(value)
    except ValueError as error:
        msg = "JOURNAL_ENTRY_INVALID"
        raise AcquisitionJournalError(msg) from error


def _rebuild_payload(transition: JournalTransition, payload: object) -> JournalPayload:
    expected = _PAYLOAD_TYPES[transition]
    if (
        not isinstance(
            payload,
            (
                DiscoveredPayload,
                CycleSafetyProfilePayload,
                ElapsedBudgetExhaustedPayload,
                StartedPayload,
                TransportStartedPayload,
                AdmissionFailedBeforeTransportPayload,
                CapturedVerifiedPayload,
                ImportedCaptureVerifiedPayload,
                RetryableFailurePayload,
                ContractRejectedPayload,
                AuthorizationRejectedPayload,
                RetryExhaustedPayload,
                TerminalUnavailablePayload,
                AccountedExcludedPayload,
            ),
        )
        or type(payload) is not expected
    ):
        _fail("TRANSITION_PAYLOAD_INVALID")
    try:
        return _payload_from_json(transition, checked_json_value(payload.to_json()))
    except (AttributeError, TypeError, ValueError) as error:
        if isinstance(error, AcquisitionJournalError):
            raise
        msg = "TRANSITION_PAYLOAD_INVALID"
        raise AcquisitionJournalError(msg) from error


@dataclass(frozen=True, slots=True)
class AcquisitionJournalEntry:
    """One immutable, predecessor-bound work-item transition."""

    sequence: int
    previous_entry_fingerprint: str
    work_item: WorkItemIdentity
    transition: JournalTransition
    payload: JournalPayload
    fingerprint: str

    def __post_init__(self) -> None:
        """Rebuild nested values and verify the entry self-fingerprint."""
        body = _validated_entry_body(self)
        if _fingerprint_value(self.fingerprint, code="JOURNAL_ENTRY_INVALID") != _fingerprint(body):
            _fail("JOURNAL_ENTRY_INVALID")

    @classmethod
    def issue(
        cls,
        *,
        sequence: int,
        previous_entry_fingerprint: str,
        work_item: WorkItemIdentity,
        transition: JournalTransition,
        payload: object,
    ) -> Self:
        """Issue one entry after rebuilding all object-originated values."""
        rebuilt_item = (
            WorkItemIdentity.from_json(work_item.to_json())
            if type(work_item) is WorkItemIdentity
            else _invalid_work_item()
        )
        if type(transition) is not JournalTransition:
            _fail("JOURNAL_ENTRY_INVALID")
        rebuilt_payload = _rebuild_payload(transition, payload)
        body = _entry_body_values(
            sequence,
            previous_entry_fingerprint,
            rebuilt_item,
            transition,
            rebuilt_payload,
        )
        return cls(
            sequence,
            previous_entry_fingerprint,
            rebuilt_item,
            transition,
            rebuilt_payload,
            _fingerprint(body),
        )

    @classmethod
    def from_json(cls, value: JsonValue) -> Self:
        """Parse one exact entry including nested object and self-fingerprint checks."""
        document = _exact_mapping(
            value,
            frozenset(
                {
                    "schema_id",
                    "schema_version",
                    "sequence",
                    "previous_entry_fingerprint",
                    "work_item",
                    "transition",
                    "payload",
                    "fingerprint",
                }
            ),
            code="JOURNAL_ENTRY_INVALID",
        )
        if (
            document["schema_id"] != _ENTRY_SCHEMA_ID
            or document["schema_version"] != _SCHEMA_VERSION
        ):
            _fail("JOURNAL_ENTRY_INVALID")
        try:
            transition_value = document["transition"]
            if type(transition_value) is not str:
                _fail("JOURNAL_ENTRY_INVALID")
            transition = JournalTransition(transition_value)
            return cls(
                _integer(
                    document["sequence"],
                    minimum=1,
                    maximum=9_999_999_999_999_999_999,
                    code="JOURNAL_ENTRY_INVALID",
                ),
                _fingerprint_value(
                    document["previous_entry_fingerprint"], code="JOURNAL_ENTRY_INVALID"
                ),
                WorkItemIdentity.from_json(document["work_item"]),
                transition,
                _payload_from_json(transition, document["payload"]),
                _fingerprint_value(document["fingerprint"], code="JOURNAL_ENTRY_INVALID"),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, AcquisitionJournalError):
                raise
            msg = "JOURNAL_ENTRY_INVALID"
            raise AcquisitionJournalError(msg) from error

    def to_json(self) -> dict[str, JsonValue]:
        """Return exact canonical entry JSON."""
        return _json_object({**_entry_body(self), "fingerprint": self.fingerprint})


def _invalid_work_item() -> WorkItemIdentity:
    _fail("WORK_ITEM_INVALID")


def _validated_entry_body(entry: AcquisitionJournalEntry) -> dict[str, object]:
    try:
        if (
            type(entry.work_item) is not WorkItemIdentity
            or type(entry.transition) is not JournalTransition
        ):
            _fail("JOURNAL_ENTRY_INVALID")
        item = WorkItemIdentity.from_json(entry.work_item.to_json())
        payload = _rebuild_payload(entry.transition, entry.payload)
        return _entry_body_values(
            entry.sequence,
            entry.previous_entry_fingerprint,
            item,
            entry.transition,
            payload,
        )
    except (AttributeError, TypeError, ValueError) as error:
        if isinstance(error, AcquisitionJournalError):
            raise
        msg = "JOURNAL_ENTRY_INVALID"
        raise AcquisitionJournalError(msg) from error


def _entry_body_values(
    sequence: object,
    previous: object,
    item: WorkItemIdentity,
    transition: JournalTransition,
    payload: JournalPayload,
) -> dict[str, object]:
    return {
        "schema_id": _ENTRY_SCHEMA_ID,
        "schema_version": _SCHEMA_VERSION,
        "sequence": _integer(
            sequence, minimum=1, maximum=9_999_999_999_999_999_999, code="JOURNAL_ENTRY_INVALID"
        ),
        "previous_entry_fingerprint": _fingerprint_value(previous, code="JOURNAL_ENTRY_INVALID"),
        "work_item": item.to_json(),
        "transition": transition.value,
        "payload": payload.to_json(),
    }


def _entry_body(entry: AcquisitionJournalEntry) -> dict[str, object]:
    return _entry_body_values(
        entry.sequence,
        entry.previous_entry_fingerprint,
        entry.work_item,
        entry.transition,
        entry.payload,
    )


@dataclass(frozen=True, slots=True)
class CheckpointItem:
    """Latest replay-derived state for one work item."""

    work_item_id: str
    latest_sequence: int
    transition: JournalTransition
    attempt_count: int
    object_ref: str | None
    retry_not_before: str | None

    def __post_init__(self) -> None:
        """Validate one exact replay-derived item state."""
        if type(self.work_item_id) is not str or _WORK_ITEM_ID.fullmatch(self.work_item_id) is None:
            _fail("CHECKPOINT_INVALID")
        _integer(
            self.latest_sequence,
            minimum=1,
            maximum=9_999_999_999_999_999_999,
            code="CHECKPOINT_INVALID",
        )
        if type(self.transition) is not JournalTransition:
            _fail("CHECKPOINT_INVALID")
        attempt_count = _integer(
            self.attempt_count,
            minimum=0,
            maximum=1_000_000,
            code="CHECKPOINT_INVALID",
        )
        unattempted = self.transition in {
            JournalTransition.DISCOVERED,
            JournalTransition.ACCOUNTED_EXCLUDED,
            JournalTransition.IMPORTED_CAPTURE_VERIFIED,
        }
        if (attempt_count == 0) != unattempted:
            _fail("CHECKPOINT_INVALID")
        if self.object_ref is not None:
            try:
                _object_reference(self.object_ref)
            except AcquisitionJournalError as error:
                msg = "CHECKPOINT_INVALID"
                raise AcquisitionJournalError(msg) from error
        if self.retry_not_before is not None:
            _timestamp(self.retry_not_before, code="CHECKPOINT_INVALID")
        if (self.object_ref is not None) != (
            self.transition
            in {
                JournalTransition.CAPTURED_VERIFIED,
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
            }
        ):
            _fail("CHECKPOINT_INVALID")
        if (self.retry_not_before is not None) != (
            self.transition
            in {
                JournalTransition.RETRYABLE_FAILURE,
                JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
            }
        ):
            _fail("CHECKPOINT_INVALID")

    @classmethod
    def from_json(cls, value: JsonValue) -> Self:
        """Parse one closed checkpoint-item object."""
        document = _exact_mapping(
            value,
            frozenset(
                {
                    "work_item_id",
                    "latest_sequence",
                    "transition",
                    "attempt_count",
                    "object_ref",
                    "retry_not_before",
                }
            ),
            code="CHECKPOINT_INVALID",
        )
        try:
            transition = document["transition"]
            if type(transition) is not str:
                _fail("CHECKPOINT_INVALID")
            return cls(
                _text(document["work_item_id"], code="CHECKPOINT_INVALID"),
                _integer(
                    document["latest_sequence"],
                    minimum=1,
                    maximum=9_999_999_999_999_999_999,
                    code="CHECKPOINT_INVALID",
                ),
                JournalTransition(transition),
                _integer(
                    document["attempt_count"],
                    minimum=0,
                    maximum=1_000_000,
                    code="CHECKPOINT_INVALID",
                ),
                _optional_text(document["object_ref"], code="CHECKPOINT_INVALID"),
                _optional_text(document["retry_not_before"], code="CHECKPOINT_INVALID"),
            )
        except (TypeError, ValueError) as error:
            if isinstance(error, AcquisitionJournalError):
                raise
            msg = "CHECKPOINT_INVALID"
            raise AcquisitionJournalError(msg) from error

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact checkpoint-item JSON shape."""
        return {
            "work_item_id": self.work_item_id,
            "latest_sequence": self.latest_sequence,
            "transition": self.transition.value,
            "attempt_count": self.attempt_count,
            "object_ref": self.object_ref,
            "retry_not_before": self.retry_not_before,
        }


def _optional_text(value: object, *, code: str) -> str | None:
    if value is None:
        return None
    return _text(value, code=code, maximum=2_048)


@dataclass(frozen=True, slots=True)
class AcquisitionCheckpoint:
    """Derived acceleration state that never grants journal authority."""

    cycle_id: str
    through_sequence: int
    journal_head_fingerprint: str
    items: tuple[CheckpointItem, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        """Verify exact item ordering and the checkpoint self-fingerprint."""
        body = _checkpoint_body_values(
            self.cycle_id,
            self.through_sequence,
            self.journal_head_fingerprint,
            self.items,
        )
        if _fingerprint_value(self.fingerprint, code="CHECKPOINT_INVALID") != _fingerprint(body):
            _fail("CHECKPOINT_INVALID")

    @classmethod
    def issue(
        cls,
        *,
        cycle_id: str,
        through_sequence: int,
        journal_head_fingerprint: str,
        items: tuple[CheckpointItem, ...],
    ) -> Self:
        """Issue one fingerprinted checkpoint from replay-derived state."""
        body = _checkpoint_body_values(cycle_id, through_sequence, journal_head_fingerprint, items)
        return cls(cycle_id, through_sequence, journal_head_fingerprint, items, _fingerprint(body))

    @classmethod
    def from_json(cls, value: JsonValue) -> Self:
        """Parse one closed checkpoint and verify its fingerprint."""
        document = _exact_mapping(
            value,
            frozenset(
                {
                    "schema_id",
                    "schema_version",
                    "cycle_id",
                    "through_sequence",
                    "journal_head_fingerprint",
                    "items",
                    "fingerprint",
                }
            ),
            code="CHECKPOINT_INVALID",
        )
        if (
            document["schema_id"] != _CHECKPOINT_SCHEMA_ID
            or document["schema_version"] != _SCHEMA_VERSION
        ):
            _fail("CHECKPOINT_INVALID")
        raw_items = document["items"]
        if not isinstance(raw_items, list) or type(raw_items) is not list:
            _fail("CHECKPOINT_INVALID")
        return cls(
            _text(document["cycle_id"], code="CHECKPOINT_INVALID"),
            _integer(
                document["through_sequence"],
                minimum=0,
                maximum=9_999_999_999_999_999_999,
                code="CHECKPOINT_INVALID",
            ),
            _fingerprint_value(document["journal_head_fingerprint"], code="CHECKPOINT_INVALID"),
            tuple(CheckpointItem.from_json(item) for item in raw_items),
            _fingerprint_value(document["fingerprint"], code="CHECKPOINT_INVALID"),
        )

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact checkpoint JSON shape."""
        return _json_object({**_checkpoint_body(self), "fingerprint": self.fingerprint})


@dataclass(frozen=True, slots=True)
class RetainedAcquisitionJournalSnapshot:
    """Replay-derived read-only view over one retained local cycle journal."""

    entries: tuple[AcquisitionJournalEntry, ...]
    checkpoint: AcquisitionCheckpoint
    last_progress_at: datetime | None


def _checkpoint_body_values(
    cycle_id: object,
    through_sequence: object,
    head: object,
    items: object,
) -> dict[str, object]:
    cycle = _text(cycle_id, code="CHECKPOINT_INVALID", maximum=127)
    if _CYCLE_ID.fullmatch(cycle) is None or not _is_exact_tuple(items):
        _fail("CHECKPOINT_INVALID")
    sequence = _integer(
        through_sequence, minimum=0, maximum=9_999_999_999_999_999_999, code="CHECKPOINT_INVALID"
    )
    fingerprint = _fingerprint_value(head, code="CHECKPOINT_INVALID")
    rebuilt: list[CheckpointItem] = []
    for item in items:
        if not _is_checkpoint_item(item):
            _fail("CHECKPOINT_INVALID")
        rebuilt.append(CheckpointItem.from_json(item.to_json()))
    if tuple(item.work_item_id for item in rebuilt) != tuple(
        sorted(item.work_item_id for item in rebuilt)
    ):
        _fail("CHECKPOINT_INVALID")
    if len({item.work_item_id for item in rebuilt}) != len(rebuilt):
        _fail("CHECKPOINT_INVALID")
    latest_sequences = tuple(item.latest_sequence for item in rebuilt)
    empty_journal = sequence == 0
    if (
        empty_journal != (fingerprint == _ZERO_FINGERPRINT)
        or empty_journal != (not rebuilt)
        or (rebuilt and max(latest_sequences) != sequence)
        or len(set(latest_sequences)) != len(latest_sequences)
    ):
        _fail("CHECKPOINT_INVALID")
    return {
        "schema_id": _CHECKPOINT_SCHEMA_ID,
        "schema_version": _SCHEMA_VERSION,
        "cycle_id": cycle,
        "through_sequence": sequence,
        "journal_head_fingerprint": fingerprint,
        "items": [item.to_json() for item in rebuilt],
    }


def _is_checkpoint_item(value: object) -> TypeIs[CheckpointItem]:
    return isinstance(value, CheckpointItem) and type(value) is CheckpointItem


def _checkpoint_body(checkpoint: AcquisitionCheckpoint) -> dict[str, object]:
    return _checkpoint_body_values(
        checkpoint.cycle_id,
        checkpoint.through_sequence,
        checkpoint.journal_head_fingerprint,
        checkpoint.items,
    )


@dataclass(slots=True)
class _ReplayItemState:
    work_item: WorkItemIdentity
    latest_sequence: int
    transition: JournalTransition
    attempt_count: int
    object_ref: str | None = None
    retry_not_before: str | None = None
    elapsed_budget_exhausted: bool = False
    transport_started_attempt: int | None = None
    physical_marker_required: bool = False
    pretransport_closed_attempt: int | None = None
    started_host_not_before_epoch_us: int | None = None


@dataclass(slots=True)
class _ReplayCycleMetadata:
    safety_profile_bound: bool = False
    cycle_started_at_epoch_us: int | None = None


_TERMINAL = frozenset(
    {
        JournalTransition.CAPTURED_VERIFIED,
        JournalTransition.IMPORTED_CAPTURE_VERIFIED,
        JournalTransition.CONTRACT_REJECTED,
        JournalTransition.AUTHORIZATION_REJECTED,
        JournalTransition.RETRY_EXHAUSTED,
        JournalTransition.TERMINAL_UNAVAILABLE,
        JournalTransition.ACCOUNTED_EXCLUDED,
    }
)


def _replay_states(
    entries: tuple[AcquisitionJournalEntry, ...], cycle_id: str
) -> dict[str, _ReplayItemState]:
    states: dict[str, _ReplayItemState] = {}
    metadata = _ReplayCycleMetadata()
    previous = _ZERO_FINGERPRINT
    for expected_sequence, entry in enumerate(entries, start=1):
        if (
            entry.sequence != expected_sequence
            or entry.previous_entry_fingerprint != previous
            or entry.work_item.cycle_id != cycle_id
        ):
            _fail("JOURNAL_REPLAY_INVALID")
        if entry.transition is JournalTransition.CYCLE_SAFETY_PROFILE_BOUND:
            _validate_cycle_safety_profile_binding(entries[: expected_sequence - 1], entry)
        prior = states.get(entry.work_item.work_item_id)
        _apply_transition(entry, prior, states, metadata)
        previous = entry.fingerprint
    return states


def _validate_cycle_safety_profile_binding(
    prefix: tuple[AcquisitionJournalEntry, ...],
    marker: AcquisitionJournalEntry,
) -> None:
    """Bind one profile to the exact modern discovery origin before any start."""
    payload = marker.payload
    if type(payload) is not CycleSafetyProfilePayload:
        _fail("JOURNAL_TRANSITION_INVALID")
    cycle_origins = {
        entry.payload.cycle_started_at_epoch_us
        for entry in prefix
        if entry.transition is JournalTransition.DISCOVERED
        and type(entry.payload) is DiscoveredPayload
    }
    if (
        not prefix
        or cycle_origins != {payload.cycle_started_at_epoch_us}
        or any(entry.transition is JournalTransition.STARTED for entry in prefix)
    ):
        _fail("JOURNAL_TRANSITION_INVALID")


def _apply_transition(  # noqa: C901, PLR0912, PLR0915 - one auditable lifecycle owner.
    entry: AcquisitionJournalEntry,
    prior: _ReplayItemState | None,
    states: dict[str, _ReplayItemState],
    metadata: _ReplayCycleMetadata,
) -> None:
    transition = entry.transition
    if transition is JournalTransition.DISCOVERED:
        if (
            prior is not None
            or type(entry.payload) is not DiscoveredPayload
            or (
                metadata.cycle_started_at_epoch_us is not None
                and entry.payload.cycle_started_at_epoch_us != metadata.cycle_started_at_epoch_us
            )
        ):
            _fail("JOURNAL_TRANSITION_INVALID")
        if metadata.cycle_started_at_epoch_us is None:
            metadata.cycle_started_at_epoch_us = entry.payload.cycle_started_at_epoch_us
        states[entry.work_item.work_item_id] = _ReplayItemState(
            entry.work_item, entry.sequence, transition, 0
        )
        return
    if transition is JournalTransition.CYCLE_SAFETY_PROFILE_BOUND:
        payload = entry.payload
        if (
            prior is None
            or metadata.safety_profile_bound
            or type(payload) is not CycleSafetyProfilePayload
        ):
            _fail("JOURNAL_TRANSITION_INVALID")
        metadata.safety_profile_bound = True
        prior.latest_sequence = entry.sequence
        return
    if transition is JournalTransition.ELAPSED_BUDGET_EXHAUSTED:
        if (
            prior is None
            or prior.elapsed_budget_exhausted
            or type(entry.payload) is not ElapsedBudgetExhaustedPayload
        ):
            _fail("JOURNAL_TRANSITION_INVALID")
        prior.latest_sequence = entry.sequence
        prior.elapsed_budget_exhausted = True
        return
    if transition is JournalTransition.TRANSPORT_STARTED:
        payload = entry.payload
        if (
            prior is None
            or prior.work_item != entry.work_item
            or prior.transition is not JournalTransition.STARTED
            or type(payload) is not TransportStartedPayload
            or payload.attempt != prior.attempt_count
            or prior.transport_started_attempt == payload.attempt
        ):
            _fail("JOURNAL_TRANSITION_INVALID")
        prior.latest_sequence = entry.sequence
        prior.transport_started_attempt = payload.attempt
        return
    if prior is None or prior.work_item != entry.work_item or prior.transition in _TERMINAL:
        _fail("JOURNAL_TRANSITION_INVALID")
    if transition is JournalTransition.IMPORTED_CAPTURE_VERIFIED:
        payload = entry.payload
        if (
            not metadata.safety_profile_bound
            or prior.transition is not JournalTransition.DISCOVERED
            or type(payload) is not ImportedCaptureVerifiedPayload
            or payload.media_type != entry.work_item.media_type
            or payload.body_length > entry.work_item.max_bytes
            or prior.attempt_count != 0
        ):
            _fail("JOURNAL_TRANSITION_INVALID")
        prior.object_ref = payload.object_ref
        prior.latest_sequence = entry.sequence
        prior.transition = transition
        return
    if transition is JournalTransition.STARTED:
        if not metadata.safety_profile_bound or prior.transition not in {
            JournalTransition.DISCOVERED,
            JournalTransition.RETRYABLE_FAILURE,
            JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
        }:
            _fail("JOURNAL_TRANSITION_INVALID")
        payload = entry.payload
        if not isinstance(payload, StartedPayload) or type(payload) is not StartedPayload:
            _fail("JOURNAL_TRANSITION_INVALID")
        if payload.attempt != prior.attempt_count + 1:
            _fail("JOURNAL_TRANSITION_INVALID")
        prior.attempt_count = payload.attempt
        prior.object_ref = None
        prior.retry_not_before = None
        prior.transport_started_attempt = None
        prior.physical_marker_required = True
        prior.pretransport_closed_attempt = None
        prior.started_host_not_before_epoch_us = payload.host_not_before_epoch_us
    elif transition is JournalTransition.ACCOUNTED_EXCLUDED:
        if prior.transition is not JournalTransition.DISCOVERED:
            _fail("JOURNAL_TRANSITION_INVALID")
    elif transition is JournalTransition.RETRY_EXHAUSTED:
        if prior.transition not in {
            JournalTransition.RETRYABLE_FAILURE,
            JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
        }:
            _fail("JOURNAL_TRANSITION_INVALID")
        payload = entry.payload
        if (
            not isinstance(payload, RetryExhaustedPayload)
            or type(payload) is not RetryExhaustedPayload
            or payload.attempt != prior.attempt_count
            or (
                prior.physical_marker_required
                and payload.attempt
                not in {prior.transport_started_attempt, prior.pretransport_closed_attempt}
            )
        ):
            _fail("JOURNAL_TRANSITION_INVALID")
        prior.retry_not_before = None
    else:
        if prior.transition is not JournalTransition.STARTED:
            _fail("JOURNAL_TRANSITION_INVALID")
        attempt = _outcome_attempt(entry.payload)
        if attempt != prior.attempt_count:
            _fail("JOURNAL_TRANSITION_INVALID")
        pretransport_interruption = (
            transition is JournalTransition.RETRYABLE_FAILURE
            and type(entry.payload) is RetryableFailurePayload
            and entry.payload.failure_code is AcquisitionFailureCode.WORKER_INTERRUPTED
        )
        marker_free_interruption = (
            pretransport_interruption and prior.transport_started_attempt != attempt
        )
        if (
            marker_free_interruption
            and prior.physical_marker_required
            and prior.started_host_not_before_epoch_us is not None
            and type(entry.payload) is RetryableFailurePayload
            and _timestamp_epoch_microseconds(
                entry.payload.retry_not_before,
                code="JOURNAL_TRANSITION_INVALID",
            )
            < prior.started_host_not_before_epoch_us
        ):
            _fail("JOURNAL_TRANSITION_INVALID")
        admission_failure = (
            entry.payload
            if transition is JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT
            and type(entry.payload) is AdmissionFailedBeforeTransportPayload
            else None
        )
        if admission_failure is not None and (
            not prior.physical_marker_required
            or prior.transport_started_attempt is not None
            or prior.started_host_not_before_epoch_us is None
            or _timestamp_epoch_microseconds(
                admission_failure.retry_not_before,
                code="JOURNAL_TRANSITION_INVALID",
            )
            < prior.started_host_not_before_epoch_us
        ):
            _fail("JOURNAL_TRANSITION_INVALID")
        if (
            prior.physical_marker_required
            and prior.transport_started_attempt != attempt
            and not pretransport_interruption
            and admission_failure is None
        ):
            _fail("JOURNAL_TRANSITION_INVALID")
        if transition is JournalTransition.CAPTURED_VERIFIED:
            payload = entry.payload
            if (
                not isinstance(payload, CapturedVerifiedPayload)
                or type(payload) is not CapturedVerifiedPayload
                or payload.media_type != entry.work_item.media_type
                or payload.body_length > entry.work_item.max_bytes
            ):
                _fail("JOURNAL_TRANSITION_INVALID")
            prior.object_ref = payload.object_ref
        elif transition is JournalTransition.RETRYABLE_FAILURE:
            payload = entry.payload
            if (
                not isinstance(payload, RetryableFailurePayload)
                or type(payload) is not RetryableFailurePayload
            ):
                _fail("JOURNAL_TRANSITION_INVALID")
            prior.retry_not_before = payload.retry_not_before
            prior.pretransport_closed_attempt = attempt if pretransport_interruption else None
        elif transition is JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT:
            payload = entry.payload
            if type(payload) is not AdmissionFailedBeforeTransportPayload:
                _fail("JOURNAL_TRANSITION_INVALID")
            prior.retry_not_before = payload.retry_not_before
            prior.pretransport_closed_attempt = attempt
    prior.latest_sequence = entry.sequence
    prior.transition = transition


def _outcome_attempt(payload: JournalPayload) -> int:
    if isinstance(
        payload,
        (
            CapturedVerifiedPayload,
            RetryableFailurePayload,
            AdmissionFailedBeforeTransportPayload,
            ContractRejectedPayload,
            AuthorizationRejectedPayload,
            RetryExhaustedPayload,
            TerminalUnavailablePayload,
        ),
    ):
        return payload.attempt
    _fail("JOURNAL_TRANSITION_INVALID")


def _derive_checkpoint(
    entries: tuple[AcquisitionJournalEntry, ...], cycle_id: str
) -> AcquisitionCheckpoint:
    states = _replay_states(entries, cycle_id)
    items = tuple(
        CheckpointItem(
            work_item_id=state.work_item.work_item_id,
            latest_sequence=state.latest_sequence,
            transition=state.transition,
            attempt_count=state.attempt_count,
            object_ref=state.object_ref,
            retry_not_before=state.retry_not_before,
        )
        for state in sorted(states.values(), key=lambda value: value.work_item.work_item_id)
    )
    return AcquisitionCheckpoint.issue(
        cycle_id=cycle_id,
        through_sequence=len(entries),
        journal_head_fingerprint=entries[-1].fingerprint if entries else _ZERO_FINGERPRINT,
        items=items,
    )


class LocalAcquisitionJournal:
    """Pinned-root, hash-chained local acquisition journal."""

    def __init__(self, cycle_state_root: object, cycle_id: object) -> None:
        """Create and pin the fixed journal directories without following aliases."""
        root = _validated_root_path(cycle_state_root)
        cycle = _text(cycle_id, code="JOURNAL_ROOT_INVALID", maximum=127)
        if _CYCLE_ID.fullmatch(cycle) is None:
            _fail("JOURNAL_ROOT_INVALID")
        state_fd = _walk_root(root, create=True)
        lease_fd: int | None = None
        journals_fd: int | None = None
        cycle_fd: int | None = None
        entries_fd: int | None = None
        try:
            lease_name = f".{cycle}{_LEASE_SUFFIX}"
            lease_fd = _open_cycle_lease(state_fd, lease_name)
            journals_fd = _ensure_private_child(state_fd, _JOURNAL_CHILD)
            cycle_fd = _ensure_private_child(journals_fd, cycle)
            entries_fd = _ensure_private_child(cycle_fd, _ENTRIES_CHILD)
            self._root = root
            self._cycle_id = cycle
            self._lease_name = lease_name
            self._state_identity = _directory_identity(state_fd)
            self._lease_identity = _regular_identity(lease_fd)
            self._journals_identity = _directory_identity(journals_fd)
            self._cycle_identity = _directory_identity(cycle_fd)
            self._entries_identity = _directory_identity(entries_fd)
            self._state_fd = state_fd
            self._lease_fd = lease_fd
            self._journals_fd = journals_fd
            self._cycle_fd = cycle_fd
            self._entries_fd = entries_fd
        except BaseException:
            for descriptor in (entries_fd, cycle_fd, journals_fd, lease_fd, state_fd):
                if descriptor is not None:
                    with suppress(OSError):
                        os.close(descriptor)
            raise
        self._lock = threading.Lock()
        self._closed = False

    @property
    def cycle_id(self) -> str:
        """Return the immutable cycle bound to this journal instance."""
        return self._cycle_id

    def close(self) -> None:
        """Idempotently release all pinned journal descriptors."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                os.close(self._entries_fd)
                os.close(self._cycle_fd)
                os.close(self._journals_fd)
                os.close(self._lease_fd)
                os.close(self._state_fd)
            except OSError as error:
                msg = "JOURNAL_IO"
                raise AcquisitionJournalError(msg) from error

    def __enter__(self) -> Self:
        """Return this pinned journal for explicit lifecycle ownership."""
        return self

    def __exit__(self, *_: object) -> None:
        """Release pinned descriptors at context exit."""
        self.close()

    def append(
        self,
        work_item: WorkItemIdentity,
        transition: JournalTransition,
        payload: object,
    ) -> AcquisitionJournalEntry:
        """Create exactly one next entry, fsync it, and verify read-back before return."""
        if type(work_item) is not WorkItemIdentity:
            _fail("WORK_ITEM_INVALID")
        try:
            item = WorkItemIdentity.from_json(work_item.to_json())
        except (AttributeError, TypeError, ValueError) as error:
            if isinstance(error, AcquisitionJournalError):
                raise
            msg = "WORK_ITEM_INVALID"
            raise AcquisitionJournalError(msg) from error
        if type(transition) is not JournalTransition:
            _fail("JOURNAL_ENTRY_INVALID")
        rebuilt_payload = _rebuild_payload(transition, payload)
        with self._locked():
            entries = self._replay_locked()
            entry = AcquisitionJournalEntry.issue(
                sequence=len(entries) + 1,
                previous_entry_fingerprint=(
                    entries[-1].fingerprint if entries else _ZERO_FINGERPRINT
                ),
                work_item=item,
                transition=transition,
                payload=rebuilt_payload,
            )
            try:
                _replay_states((*entries, entry), self._cycle_id)
            except AcquisitionJournalError as error:
                msg = "JOURNAL_TRANSITION_INVALID"
                raise AcquisitionJournalError(msg) from error
            self._verify_root()
            _write_exclusive_entry(self._entries_fd, entry)
            return entry

    def append_many(
        self,
        additions: tuple[tuple[WorkItemIdentity, JournalTransition, object], ...],
    ) -> tuple[AcquisitionJournalEntry, ...]:
        """Validate one ordered batch completely, then publish its entries in order."""
        if type(additions) is not tuple or not additions:
            _fail("JOURNAL_ENTRY_INVALID")
        rebuilt: list[tuple[WorkItemIdentity, JournalTransition, JournalPayload]] = []
        for addition in additions:
            if type(addition) is not tuple or len(addition) != _BATCH_ADDITION_LENGTH:
                _fail("JOURNAL_ENTRY_INVALID")
            work_item, transition, payload = addition
            if type(work_item) is not WorkItemIdentity:
                _fail("WORK_ITEM_INVALID")
            item = WorkItemIdentity.from_json(work_item.to_json())
            if type(transition) is not JournalTransition:
                _fail("JOURNAL_ENTRY_INVALID")
            rebuilt.append((item, transition, _rebuild_payload(transition, payload)))
        with self._locked():
            existing = self._replay_locked()
            previous = existing[-1].fingerprint if existing else _ZERO_FINGERPRINT
            issued: list[AcquisitionJournalEntry] = []
            for offset, (item, transition, payload) in enumerate(rebuilt, start=1):
                entry = AcquisitionJournalEntry.issue(
                    sequence=len(existing) + offset,
                    previous_entry_fingerprint=previous,
                    work_item=item,
                    transition=transition,
                    payload=payload,
                )
                issued.append(entry)
                previous = entry.fingerprint
            try:
                _replay_states((*existing, *issued), self._cycle_id)
            except AcquisitionJournalError as error:
                msg = "JOURNAL_TRANSITION_INVALID"
                raise AcquisitionJournalError(msg) from error
            self._verify_root()
            for entry in issued:
                _write_exclusive_entry(self._entries_fd, entry)
            return tuple(issued)

    def replay(self) -> tuple[AcquisitionJournalEntry, ...]:
        """Verify the complete journal chain and lifecycle before returning any state."""
        with self._locked():
            return self._replay_locked()

    def write_checkpoint(self) -> AcquisitionCheckpoint:
        """Atomically publish the exact current replay-derived checkpoint."""
        with self._locked():
            checkpoint = _derive_checkpoint(self._replay_locked(), self._cycle_id)
            self._verify_root()
            _write_checkpoint(self._cycle_fd, checkpoint)
            return checkpoint

    def load_checkpoint(self) -> AcquisitionCheckpoint:
        """Return a replay-exact checkpoint, rebuilding any missing or drifting copy."""
        with self._locked():
            expected = _derive_checkpoint(self._replay_locked(), self._cycle_id)
            self._verify_root()
            try:
                retained = _read_checkpoint(self._cycle_fd)
            except AcquisitionJournalError:
                retained = None
            if retained is None or retained != expected:
                self._verify_root()
                _write_checkpoint(self._cycle_fd, expected)
                return expected
            return retained

    def _replay_locked(self) -> tuple[AcquisitionJournalEntry, ...]:
        try:
            self._verify_root()
            names = os.listdir(self._entries_fd)  # noqa: PTH208 - fd-relative enumeration.
            if any(_ENTRY_NAME.fullmatch(name) is None for name in names):
                _fail("JOURNAL_REPLAY_INVALID")
            ordered = sorted(names)
            entries = tuple(
                _read_entry(self._entries_fd, name, expected_sequence=index)
                for index, name in enumerate(ordered, start=1)
            )
            _replay_states(entries, self._cycle_id)
        except AcquisitionJournalError as error:
            if str(error) == "JOURNAL_REPLAY_INVALID":
                raise
            msg = "JOURNAL_REPLAY_INVALID"
            raise AcquisitionJournalError(msg) from error
        except (OSError, TypeError, ValueError) as error:
            msg = "JOURNAL_REPLAY_INVALID"
            raise AcquisitionJournalError(msg) from error
        else:
            return entries

    def _verify_root(self) -> None:
        if (
            _directory_identity(self._state_fd) != self._state_identity
            or _regular_identity(self._lease_fd) != self._lease_identity
            or _directory_identity(self._journals_fd) != self._journals_identity
            or _directory_identity(self._cycle_fd) != self._cycle_identity
            or _directory_identity(self._entries_fd) != self._entries_identity
        ):
            _fail("JOURNAL_ROOT_INVALID")
        current = _walk_root(self._root, create=False)
        lease: int | None = None
        journals: int | None = None
        cycle: int | None = None
        entries: int | None = None
        try:
            if _directory_identity(current) != self._state_identity:
                _fail("JOURNAL_ROOT_INVALID")
            lease = _open_regular(self._state_fd, self._lease_name)
            journals = _open_directory(_JOURNAL_CHILD, parent_fd=self._state_fd)
            cycle = _open_directory(self._cycle_id, parent_fd=journals)
            entries = _open_directory(_ENTRIES_CHILD, parent_fd=cycle)
            if (
                _regular_identity(lease) != self._lease_identity
                or _directory_identity(journals) != self._journals_identity
                or _directory_identity(cycle) != self._cycle_identity
                or _directory_identity(entries) != self._entries_identity
            ):
                _fail("JOURNAL_ROOT_INVALID")
        finally:
            for descriptor in (entries, cycle, journals, lease, current):
                if descriptor is not None:
                    with suppress(OSError):
                        os.close(descriptor)

    @contextmanager
    def _locked(self) -> Generator[None]:
        """Hold the thread/process lock around one verified pinned root."""
        self._lock.acquire()
        flocked = False
        try:
            if self._closed:
                _fail("JOURNAL_CLOSED")
            self._verify_root()
            fcntl.flock(self._cycle_fd, fcntl.LOCK_EX)
            flocked = True
            self._verify_root()
            yield
        except OSError as error:
            msg = "JOURNAL_IO"
            raise AcquisitionJournalError(msg) from error
        finally:
            try:
                if flocked:
                    fcntl.flock(self._cycle_fd, fcntl.LOCK_UN)
            finally:
                self._lock.release()


def read_retained_acquisition_journal(
    cycle_state_root: object,
    cycle_id: object,
) -> RetainedAcquisitionJournalSnapshot:
    """Replay an existing journal under its shared cycle lock without mutating it."""
    root = _validated_root_path(cycle_state_root)
    cycle = _text(cycle_id, code="JOURNAL_ROOT_INVALID", maximum=127)
    if _CYCLE_ID.fullmatch(cycle) is None:
        _fail("JOURNAL_ROOT_INVALID")
    state_fd: int | None = None
    journals_fd: int | None = None
    cycle_fd: int | None = None
    entries_fd: int | None = None
    flocked = False
    try:
        state_fd = _walk_root(root, create=False)
        journals_fd = _open_directory(_JOURNAL_CHILD, parent_fd=state_fd)
        cycle_fd = _open_directory(cycle, parent_fd=journals_fd)
        entries_fd = _open_directory(_ENTRIES_CHILD, parent_fd=cycle_fd)
        fcntl.flock(cycle_fd, fcntl.LOCK_SH)
        flocked = True
        names = os.listdir(entries_fd)  # noqa: PTH208 - fd-relative enumeration.
        if any(_ENTRY_NAME.fullmatch(name) is None for name in names):
            _fail("JOURNAL_REPLAY_INVALID")
        ordered = sorted(names)
        entries = tuple(
            _read_entry(entries_fd, name, expected_sequence=index)
            for index, name in enumerate(ordered, start=1)
        )
        checkpoint = _derive_checkpoint(entries, cycle)
        if not ordered:
            last_progress_at = None
        else:
            details = os.stat(ordered[-1], dir_fd=entries_fd, follow_symlinks=False)
            if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                _fail("JOURNAL_REPLAY_INVALID")
            last_progress_at = (
                datetime(1970, 1, 1, tzinfo=UTC)
                + timedelta(microseconds=details.st_mtime_ns // 1_000)
            ).replace(microsecond=0)
        return RetainedAcquisitionJournalSnapshot(entries, checkpoint, last_progress_at)
    except AcquisitionJournalError:
        raise
    except (OSError, TypeError, ValueError) as error:
        msg = "JOURNAL_REPLAY_INVALID"
        raise AcquisitionJournalError(msg) from error
    finally:
        if flocked and cycle_fd is not None:
            with suppress(OSError):
                fcntl.flock(cycle_fd, fcntl.LOCK_UN)
        for descriptor in (entries_fd, cycle_fd, journals_fd, state_fd):
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)


def _validated_root_path(value: object) -> Path:
    if (
        not isinstance(value, Path)
        or type(value) is not type(Path())
        or not value.is_absolute()
        or value == Path(value.anchor)
        or any(part in {"", ".", ".."} for part in value.parts[1:])
    ):
        _fail("JOURNAL_ROOT_INVALID")
    return value


def _open_directory(name: str | Path, *, parent_fd: int | None = None) -> int:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
        details = os.fstat(descriptor)
        if not stat.S_ISDIR(details.st_mode):
            _fail("JOURNAL_ROOT_INVALID")
    except AcquisitionJournalError:
        raise
    except OSError as error:
        msg = "JOURNAL_ROOT_INVALID"
        raise AcquisitionJournalError(msg) from error
    else:
        return descriptor


def _walk_root(root: Path, *, create: bool) -> int:
    current = _open_directory(Path(root.anchor))
    try:
        for component in root.parts[1:]:
            try:
                next_fd = _open_directory(component, parent_fd=current)
            except AcquisitionJournalError:
                if not create:
                    raise
                try:
                    os.mkdir(component, _PRIVATE_DIRECTORY_MODE, dir_fd=current)
                    os.fsync(current)
                except FileExistsError:
                    pass
                except OSError as error:
                    msg = "JOURNAL_ROOT_INVALID"
                    raise AcquisitionJournalError(msg) from error
                next_fd = _open_directory(component, parent_fd=current)
            os.close(current)
            current = next_fd
        details = os.fstat(current)
        if details.st_uid != os.geteuid() or stat.S_IMODE(details.st_mode) & 0o022:
            _fail("JOURNAL_ROOT_INVALID")
    except BaseException:
        with suppress(OSError):
            os.close(current)
        raise
    else:
        return current


def _ensure_private_child(parent_fd: int, name: str) -> int:
    try:
        try:
            descriptor = _open_directory(name, parent_fd=parent_fd)
        except AcquisitionJournalError:
            try:
                os.mkdir(name, _PRIVATE_DIRECTORY_MODE, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except FileExistsError:
                pass
            descriptor = _open_directory(name, parent_fd=parent_fd)
        details = os.fstat(descriptor)
        if (
            details.st_uid != os.geteuid()
            or stat.S_IMODE(details.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            os.close(descriptor)
            _fail("JOURNAL_ROOT_INVALID")
    except AcquisitionJournalError:
        raise
    except OSError as error:
        msg = "JOURNAL_ROOT_INVALID"
        raise AcquisitionJournalError(msg) from error
    else:
        return descriptor


def _open_cycle_lease(state_fd: int, filename: str) -> int:
    descriptor: int | None = None
    created = False
    try:
        try:
            descriptor = os.open(
                filename,
                os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                _PRIVATE_FILE_MODE,
                dir_fd=state_fd,
            )
            created = True
        except FileExistsError:
            descriptor = _open_regular(state_fd, filename, writable=True)
        _verify_lease_file(descriptor)
        if created:
            os.fsync(descriptor)
            os.fsync(state_fd)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            msg = "JOURNAL_ALREADY_OPEN"
            raise AcquisitionJournalError(msg) from error
    except AcquisitionJournalError:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise
    except OSError as error:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        msg = "JOURNAL_ROOT_INVALID"
        raise AcquisitionJournalError(msg) from error
    else:
        return descriptor


def _open_regular(parent_fd: int, filename: str, *, writable: bool = False) -> int:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            filename,
            (os.O_RDWR if writable else os.O_RDONLY) | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
        _verify_lease_file(descriptor)
    except AcquisitionJournalError:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise
    except OSError as error:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        msg = "JOURNAL_ROOT_INVALID"
        raise AcquisitionJournalError(msg) from error
    else:
        return descriptor


def _verify_lease_file(descriptor: int) -> None:
    try:
        details = os.fstat(descriptor)
    except OSError as error:
        msg = "JOURNAL_ROOT_INVALID"
        raise AcquisitionJournalError(msg) from error
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or details.st_uid != os.geteuid()
        or stat.S_IMODE(details.st_mode) != _PRIVATE_FILE_MODE
        or details.st_size != 0
    ):
        _fail("JOURNAL_ROOT_INVALID")


def _directory_identity(descriptor: int) -> tuple[int, int, int]:
    try:
        details = os.fstat(descriptor)
    except OSError as error:
        msg = "JOURNAL_ROOT_INVALID"
        raise AcquisitionJournalError(msg) from error
    if not stat.S_ISDIR(details.st_mode):
        _fail("JOURNAL_ROOT_INVALID")
    return details.st_dev, details.st_ino, stat.S_IFMT(details.st_mode)


def _regular_identity(descriptor: int) -> tuple[int, int, int]:
    try:
        details = os.fstat(descriptor)
    except OSError as error:
        msg = "JOURNAL_ROOT_INVALID"
        raise AcquisitionJournalError(msg) from error
    if not stat.S_ISREG(details.st_mode):
        _fail("JOURNAL_ROOT_INVALID")
    return details.st_dev, details.st_ino, stat.S_IFMT(details.st_mode)


def _identity(descriptor: int) -> tuple[int, int]:
    try:
        details = os.fstat(descriptor)
    except OSError as error:
        msg = "JOURNAL_ROOT_INVALID"
        raise AcquisitionJournalError(msg) from error
    return details.st_dev, details.st_ino


def _read_bytes(directory_fd: int, filename: str, *, maximum: int) -> bytes:
    try:
        descriptor = os.open(
            filename,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=directory_fd,
        )
    except OSError as error:
        msg = "JOURNAL_FILE_INVALID"
        raise AcquisitionJournalError(msg) from error
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or not 0 < details.st_size <= maximum
        ):
            _fail("JOURNAL_FILE_INVALID")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if not content or len(content) > maximum:
            _fail("JOURNAL_FILE_INVALID")
    except OSError as error:
        msg = "JOURNAL_FILE_INVALID"
        raise AcquisitionJournalError(msg) from error
    else:
        return content
    finally:
        os.close(descriptor)


def _parse_entry(content: bytes) -> AcquisitionJournalEntry:
    try:
        entry = AcquisitionJournalEntry.from_json(
            parse_json_bytes(content, max_bytes=_MAX_ENTRY_BYTES)
        )
        if canonicalize(entry.to_json()) != content:
            _fail("JOURNAL_ENTRY_INVALID")
    except (TypeError, ValueError) as error:
        if isinstance(error, AcquisitionJournalError):
            raise
        msg = "JOURNAL_ENTRY_INVALID"
        raise AcquisitionJournalError(msg) from error
    else:
        return entry


def _read_entry(
    directory_fd: int, filename: str, *, expected_sequence: int
) -> AcquisitionJournalEntry:
    entry = _parse_entry(_read_bytes(directory_fd, filename, maximum=_MAX_ENTRY_BYTES))
    if filename != f"{expected_sequence:020d}.json" or entry.sequence != expected_sequence:
        _fail("JOURNAL_REPLAY_INVALID")
    return entry


def _write_all(descriptor: int, content: bytes) -> None:
    cursor = 0
    while cursor < len(content):
        written = os.write(descriptor, content[cursor:])
        if written <= 0:
            _fail("JOURNAL_IO")
        cursor += written


def _write_exclusive_entry(directory_fd: int, entry: AcquisitionJournalEntry) -> None:
    filename = f"{entry.sequence:020d}.json"
    content = canonicalize(entry.to_json())
    descriptor: int | None = None
    try:
        descriptor = os.open(
            filename,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
            dir_fd=directory_fd,
        )
        _write_all(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.fsync(directory_fd)
        retained = _read_entry(directory_fd, filename, expected_sequence=entry.sequence)
        if retained != entry or canonicalize(retained.to_json()) != content:
            _fail("JOURNAL_WRITE_VERIFY")
    except AcquisitionJournalError:
        raise
    except OSError as error:
        msg = "JOURNAL_IO"
        raise AcquisitionJournalError(msg) from error
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)


def _read_checkpoint(directory_fd: int) -> AcquisitionCheckpoint | None:
    try:
        content = _read_bytes(directory_fd, _CHECKPOINT_FILENAME, maximum=_MAX_CHECKPOINT_BYTES)
    except AcquisitionJournalError as error:
        if isinstance(error.__cause__, FileNotFoundError):
            return None
        raise
    try:
        checkpoint = AcquisitionCheckpoint.from_json(
            parse_json_bytes(content, max_bytes=_MAX_CHECKPOINT_BYTES)
        )
        if canonicalize(checkpoint.to_json()) != content:
            _fail("CHECKPOINT_INVALID")
    except (TypeError, ValueError) as error:
        if isinstance(error, AcquisitionJournalError):
            raise
        msg = "CHECKPOINT_INVALID"
        raise AcquisitionJournalError(msg) from error
    else:
        return checkpoint


def _write_checkpoint(directory_fd: int, checkpoint: AcquisitionCheckpoint) -> None:
    content = canonicalize(checkpoint.to_json())
    temporary = f".{_CHECKPOINT_FILENAME}.{token_hex(16)}.tmp"
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
            dir_fd=directory_fd,
        )
        identity = _identity(descriptor)
        _write_all(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(
            temporary, _CHECKPOINT_FILENAME, src_dir_fd=directory_fd, dst_dir_fd=directory_fd
        )
        os.fsync(directory_fd)
        retained = _read_checkpoint(directory_fd)
        if (
            retained is None
            or retained != checkpoint
            or canonicalize(retained.to_json()) != content
        ):
            _fail("CHECKPOINT_WRITE_VERIFY")
        identity = None
    except AcquisitionJournalError:
        raise
    except OSError as error:
        msg = "JOURNAL_IO"
        raise AcquisitionJournalError(msg) from error
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        if identity is not None:
            _remove_owned_temporary(directory_fd, temporary, identity)


def _remove_owned_temporary(directory_fd: int, filename: str, identity: tuple[int, int]) -> None:
    try:
        details = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        msg = "JOURNAL_IO"
        raise AcquisitionJournalError(msg) from error
    if stat.S_ISREG(details.st_mode) and (details.st_dev, details.st_ino) == identity:
        try:
            os.unlink(filename, dir_fd=directory_fd)
        except FileNotFoundError:
            return
        except OSError as error:
            msg = "JOURNAL_IO"
            raise AcquisitionJournalError(msg) from error
