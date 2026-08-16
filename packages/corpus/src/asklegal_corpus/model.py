"""Immutable M6 corpus, coverage, and frozen-proposal values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CorpusErrorCode(StrEnum):
    """Closed fail-visible construction failures."""

    COVERAGE_INCOMPLETE = "COVERAGE_INCOMPLETE"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"
    INVENTORY_MISMATCH = "INVENTORY_MISMATCH"
    PROPOSAL_NOT_FROZEN = "PROPOSAL_NOT_FROZEN"
    RELEASE_SCOPE_MISMATCH = "RELEASE_SCOPE_MISMATCH"
    ZERO_RECORD_UNJUSTIFIED = "ZERO_RECORD_UNJUSTIFIED"


class CorpusError(RuntimeError):
    """One exact corpus-construction failure."""

    def __init__(self, code: CorpusErrorCode, detail: str = "") -> None:
        """Create one closed corpus failure."""
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail


class CoverageState(StrEnum):
    """Closed coverage states from contract 1.1.0."""

    CURRENT = "CURRENT"
    KNOWN_GAP = "KNOWN_GAP"
    NOT_READY = "NOT_READY"
    WITHHELD = "WITHHELD"


class CoverageWarning(StrEnum):
    """Closed user-facing warning codes."""

    KNOWN_GAP = "COVERAGE_KNOWN_GAP"
    NOT_READY = "COVERAGE_NOT_READY"
    WITHHELD = "COVERAGE_WITHHELD"
    NONE = "NO_COVERAGE_WARNING"


@dataclass(frozen=True, slots=True)
class ServingRecord:
    """One exact six-field immutable search record."""

    record_id: str
    text: str
    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str
    artifact_ref: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReleaseRecordEntry:
    """One record selected into a complete scoped release."""

    record: ServingRecord
    serving_payload_fingerprint: str


@dataclass(frozen=True, slots=True)
class CorpusRelease:
    """One immutable complete snapshot of one Release Scope."""

    release_id: str
    scope_id: str
    observation_cutoff: str
    records: tuple[ReleaseRecordEntry, ...]
    evidence_refs: tuple[str, ...]
    validation_refs: tuple[str, ...]
    withholding_refs: tuple[str, ...]
    zero_record_justification_refs: tuple[str, ...]
    records_fingerprint: str
    release_fingerprint: str


@dataclass(frozen=True, slots=True)
class FlattenedRecord:
    """One desired serving record and its owning release."""

    record_id: str
    content_fingerprint: str
    scope_id: str
    release_id: str
    record: ServingRecord


@dataclass(frozen=True, slots=True)
class DesiredStateInventory:
    """Complete exact serving target composition."""

    inventory_id: str
    target_key: str
    observation_cutoff: str
    scope_releases: tuple[tuple[str, str], ...]
    records: tuple[FlattenedRecord, ...]
    records_fingerprint: str
    inventory_fingerprint: str


@dataclass(frozen=True, slots=True)
class CoverageScopeStatus:
    """One fully accounted Release Scope status."""

    scope_id: str
    status: CoverageState
    last_verified_at: str
    gap_refs: tuple[str, ...]
    quarantine_refs: tuple[str, ...]
    source_failure_refs: tuple[str, ...]
    warning: CoverageWarning


@dataclass(frozen=True, slots=True)
class CoverageStatusManifest:
    """Complete coverage state bound into one Serving State."""

    manifest_id: str
    serving_state_id: str
    observation_cutoff: str
    scopes: tuple[CoverageScopeStatus, ...]
    canonical_bytes: bytes
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ProposalArtifact:
    """One exact frozen proposal-package member."""

    role: str
    path: str
    media_type: str
    content: bytes
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ProposalPackage:
    """Manifest-last review package; report bytes are never authority."""

    package_id: str
    observation_cutoff: str
    promotion_manifest_id: str
    promotion_manifest_fingerprint: str
    base_serving_state_id: str
    candidate_serving_state_id: str
    artifacts: tuple[ProposalArtifact, ...]
    manifest_bytes: bytes
    fingerprint: str
    status: str = "REVIEW_READY"


@dataclass(frozen=True, slots=True)
class CorpusReleaseInput:
    """Complete non-record inputs for one Corpus Release freeze."""

    scope_id: str
    observation_cutoff: str
    evidence_refs: tuple[str, ...]
    validation_refs: tuple[str, ...]
    withholding_refs: tuple[str, ...] = ()
    zero_record_justification_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProposalPackageInput:
    """Exact authority bindings for one proposal-package freeze."""

    observation_cutoff: str
    promotion_manifest_id: str
    promotion_manifest_fingerprint: str
    base_serving_state_id: str
    base_serving_state_fingerprint: str
    candidate_serving_state_id: str
    candidate_serving_state_fingerprint: str
