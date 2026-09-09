"""Typed restart-safe identity and Search Record continuity boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol


class LegalIdentityKind(StrEnum):
    """Closed V1 legal identity families shared by Cases and Legislation."""

    LEGAL_ITEM = "LEGAL_ITEM"
    OFFICIAL_VERSION = "OFFICIAL_VERSION"
    LEGAL_LOCATION = "LEGAL_LOCATION"
    LEGAL_STATUS_EVENT = "LEGAL_STATUS_EVENT"
    DECISION = "DECISION"
    ARTIFACT = "ARTIFACT"
    EVIDENCE = "EVIDENCE"
    VALIDATION = "VALIDATION"
    TRACEABILITY_LOOKUP = "TRACEABILITY_LOOKUP"
    TRACEABILITY_SHARD = "TRACEABILITY_SHARD"


@dataclass(frozen=True, slots=True)
class LegalIdentityRequest:
    """One stable domain identity key, free of source body data."""

    kind: LegalIdentityKind
    natural_key: str


@dataclass(frozen=True, slots=True)
class IssuedLegalIdentity:
    """One create-or-match opaque identity."""

    request: LegalIdentityRequest
    identity_id: str


@dataclass(frozen=True, slots=True)
class SearchRecordIdentityRequest:
    """One stable serving slot and its current exact payload."""

    scope_code: str
    natural_key: str
    serving_payload_fingerprint: str


@dataclass(frozen=True, slots=True)
class IssuedSearchRecordIdentity:
    """A new, reused, or successor Search Record allocation."""

    request: SearchRecordIdentityRequest
    search_record_id: str
    continuity: Literal["INITIAL", "REUSE", "SUCCESSOR"]
    predecessor_record_id: str | None
    predecessor_payload_fingerprint: str | None


class LegalIdentityRegister(Protocol):
    """Small shared Management Register port used by both legal families."""

    def issue_identity(self, request: LegalIdentityRequest) -> IssuedLegalIdentity:
        """Create or replay one stable opaque legal identity."""
        ...

    def issue_search_record(
        self, request: SearchRecordIdentityRequest
    ) -> IssuedSearchRecordIdentity:
        """Allocate or replay one Search Record continuity decision."""
        ...

    def commit(self) -> None:
        """Durably retain and read back all issued facts."""
        ...
