"""Exact local adapters for API startup and boundary conformance tests."""

import hashlib
import hmac
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from asklegal_contracts import canonicalize, fingerprint
from asklegal_contracts.json_types import JsonValue


class LocalAdapterErrorCode(StrEnum):
    """Closed local-adapter outcomes."""

    COMMAND_ID_CONFLICT = "COMMAND_ID_CONFLICT"
    CONTINUATION_INVALID = "CONTINUATION_INVALID"
    DISABLED = "CAPABILITY_DISABLED"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    STALE_VERSION = "STALE_VERSION"


class LocalAdapterError(RuntimeError):
    """Safe local adapter error carrying only a closed code."""

    code: LocalAdapterErrorCode

    def __init__(self, code: LocalAdapterErrorCode) -> None:
        """Create one safe local-adapter failure."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """Authoritative local command result."""

    command_id: str
    resolution: str
    result_code: str
    authoritative_version: int
    result_ref: str


class LocalCommandRegister:
    """Idempotent command resolver with optimistic version checks."""

    _commands: dict[str, tuple[str, CommandOutcome]]
    _versions: dict[str, int]

    def __init__(self) -> None:
        """Create an empty deterministic command register."""
        self._commands = {}
        self._versions = {}

    def submit(
        self,
        *,
        command_id: str,
        target: str,
        expected_version: int,
        body: Mapping[str, JsonValue],
    ) -> CommandOutcome:
        """Resolve one command, replaying only byte-equivalent intent."""
        request_fingerprint = fingerprint(
            {
                "body": dict(body),
                "expected_version": expected_version,
                "target": target,
            }
        )
        prior = self._commands.get(command_id)
        if prior is not None:
            if prior[0] != request_fingerprint:
                raise LocalAdapterError(LocalAdapterErrorCode.COMMAND_ID_CONFLICT)
            return CommandOutcome(
                command_id=prior[1].command_id,
                resolution="EXACT_REPLAY",
                result_code=prior[1].result_code,
                authoritative_version=prior[1].authoritative_version,
                result_ref=prior[1].result_ref,
            )
        current = self._versions.get(target, 0)
        if expected_version != current:
            raise LocalAdapterError(LocalAdapterErrorCode.STALE_VERSION)
        version = current + 1
        self._versions[target] = version
        outcome = CommandOutcome(
            command_id=command_id,
            resolution="RESULT_RECORDED",
            result_code="APPLIED",
            authoritative_version=version,
            result_ref="cmr_" + hashlib.sha256(command_id.encode()).hexdigest()[:48],
        )
        self._commands[command_id] = (request_fingerprint, outcome)
        return outcome

    def check(self) -> bool:
        """Perform a non-mutating local readiness check."""
        return True


@dataclass(frozen=True, slots=True)
class PageCursor:
    """Server-held pagination state; the client receives only its opaque key."""

    snapshot: str
    filters: tuple[tuple[str, str], ...]
    sort: str
    subject: str
    offset: int
    expires_at: datetime


class LocalPaginationStore:
    """Stable, tamper-evident, server-held continuation tokens."""

    _secret: bytes
    _clock: Callable[[], datetime]
    _tokens: dict[str, PageCursor]

    def __init__(self, *, secret: bytes, clock: Callable[[], datetime] | None = None) -> None:
        """Create a token store with an injected secret and clock."""
        self._secret = secret
        self._clock = clock or (lambda: datetime.now(UTC))
        self._tokens = {}

    def issue(self, cursor: PageCursor) -> str:
        """Return the same opaque token for the same immutable cursor."""
        material: JsonValue = {
            "expires_at": cursor.expires_at.isoformat(),
            "filters": [list(item) for item in cursor.filters],
            "offset": cursor.offset,
            "snapshot": cursor.snapshot,
            "sort": cursor.sort,
            "subject": cursor.subject,
        }
        digest = hmac.new(self._secret, canonicalize(material), "sha256").hexdigest()
        token = "pgt_" + digest
        self._tokens[token] = cursor
        return token

    def resolve(
        self,
        token: str,
        *,
        snapshot: str,
        filters: tuple[tuple[str, str], ...],
        sort: str,
        subject: str,
    ) -> PageCursor:
        """Resolve only an unexpired token with all bindings unchanged."""
        cursor = self._tokens.get(token)
        if (
            cursor is None
            or cursor.expires_at <= self._clock()
            or cursor.snapshot != snapshot
            or cursor.filters != filters
            or cursor.sort != sort
            or cursor.subject != subject
        ):
            raise LocalAdapterError(LocalAdapterErrorCode.CONTINUATION_INVALID)
        return cursor

    def next_cursor(
        self,
        *,
        snapshot: str,
        filters: tuple[tuple[str, str], ...],
        sort: str,
        subject: str,
        offset: int,
    ) -> PageCursor:
        """Create one bounded cursor using the injected clock."""
        return PageCursor(
            snapshot=snapshot,
            filters=filters,
            sort=sort,
            subject=subject,
            offset=offset,
            expires_at=self._clock() + timedelta(minutes=15),
        )

    def advance(self, cursor: PageCursor, *, offset: int) -> PageCursor:
        """Advance one resolved cursor without changing its immutable bindings or expiry."""
        return replace(cursor, offset=offset)


@dataclass(frozen=True, slots=True)
class ProposalProjection:
    """One immutable review projection."""

    proposal_id: str
    manifest_fingerprint: str
    status: str
    title: str

    def to_json(self) -> dict[str, JsonValue]:
        """Return a closed JSON projection."""
        return {
            "manifest_fingerprint": self.manifest_fingerprint,
            "proposal_id": self.proposal_id,
            "status": self.status,
            "title": self.title,
        }


class LocalReviewProjectionStore:
    """Immutable proposal/evidence views for local boundary proofs."""

    snapshot: str = "projection-local-1"
    proposals: tuple[ProposalProjection, ...]
    evidence_reads: list[tuple[str, str]]

    def __init__(
        self,
        proposals: tuple[ProposalProjection, ...] | None = None,
        *,
        snapshot: str = "projection-local-1",
    ) -> None:
        """Create an immutable synthetic projection, optionally from frozen inputs."""
        if type(snapshot) is not str or not snapshot:
            raise TypeError("snapshot must be an exact non-empty string")
        supplied = proposals or tuple(
            ProposalProjection(
                proposal_id=f"proposal-{index}",
                manifest_fingerprint="sha256:" + f"{index:064x}",
                status="REVIEW_READY",
                title=f"Synthetic proposal {index}",
            )
            for index in range(1, 6)
        )
        if type(supplied) is not tuple or not supplied:
            raise TypeError("proposals must be a non-empty exact tuple")
        if any(type(item) is not ProposalProjection for item in supplied):
            raise TypeError("proposals must contain exact ProposalProjection values")
        if len({item.proposal_id for item in supplied}) != len(supplied):
            raise ValueError("proposal identities must be unique")
        self.snapshot = snapshot
        self.proposals = supplied
        self.evidence_reads = []

    def page(self, *, offset: int, limit: int) -> tuple[ProposalProjection, ...]:
        """Read one bounded page from a single immutable generation."""
        return self.proposals[offset : offset + limit]

    def get(self, proposal_id: str) -> ProposalProjection | None:
        """Read one proposal without exposing storage coordinates."""
        return next((item for item in self.proposals if item.proposal_id == proposal_id), None)

    def check(self) -> bool:
        """Perform a non-mutating local readiness check."""
        return True

    def record_evidence_read(self, *, subject: str, evidence_id: str) -> None:
        """Record a sanitized local audit fact without vault coordinates or body content."""
        self.evidence_reads.append((subject, evidence_id))


class DisabledEffectPort:
    """Fail-closed port used for every effect not authorized in M3."""

    name: str

    def __init__(self, name: str) -> None:
        """Create one named fail-closed effect port."""
        self.name = name

    def invoke(self, _request: Mapping[str, JsonValue]) -> None:
        """Reject rather than imply successful source/provider/production work."""
        raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)


def safe_mapping(value: JsonValue) -> dict[str, JsonValue]:
    """Require an exact JSON object for an application command body."""
    if type(value) is not dict:
        raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
    return dict(value)
