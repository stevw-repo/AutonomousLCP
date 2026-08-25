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
    TRACEABILITY_INCOMPLETE = "TRACEABILITY_INCOMPLETE"
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
class TraceabilityReference:
    """One exact typed immutable reference in a traceability entry."""

    ref_type: str
    ref_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AuthorityNoteEvidence:
    """Structured proof of the selected six-field authority-note value."""

    rendered_value_fingerprint: str
    decision_ref: TraceabilityReference
    supporting_evidence_refs: tuple[TraceabilityReference, ...]


@dataclass(frozen=True, slots=True)
class TraceabilityEntry:
    """One exact ADR 0078 Search Record traceability entry."""

    search_record_id: str
    serving_payload_fingerprint: str
    serving_record_profile_id: str
    legal_item_id: str
    official_version_ids: tuple[str, ...]
    legal_location_ids: tuple[str, ...]
    release_scope_id: str
    corpus_release_id: str
    evidence_refs: tuple[TraceabilityReference, ...]
    authority_note_evidence: AuthorityNoteEvidence
    grouping_ids: tuple[str, ...] = ()
    display_citation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ServingRecordProfile:
    """One exact serving-record schema profile used by a lookup revision."""

    serving_record_profile_id: str
    schema_version: str
    schema_fingerprint: str


@dataclass(frozen=True, slots=True)
class TraceabilityScopeShardInput:
    """Register-issued identity for one required Release-Scope shard."""

    release_scope_id: str
    corpus_release_id: str
    lookup_shard_id: str


@dataclass(frozen=True, slots=True)
class TraceabilityShard:
    """One immutable canonical NDJSON Release-Scope shard."""

    release_scope_id: str
    corpus_release_id: str
    lookup_shard_id: str
    path: str
    content: bytes
    entry_count: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class RecordTraceabilityLookup:
    """One complete immutable ADR 0078 lookup revision package."""

    lookup_revision_id: str
    desired_state_inventory_id: str
    profiles: tuple[ServingRecordProfile, ...]
    shards: tuple[TraceabilityShard, ...]
    total_entry_count: int
    manifest_bytes: bytes
    fingerprint: str


@dataclass(frozen=True, slots=True)
class RecordTraceabilityLookupInput:
    """Exact register and schema identities for one lookup freeze."""

    lookup_revision_id: str
    manifest_schema_fingerprint: str
    entry_schema_fingerprint: str


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
class SourceCoverageCycleBinding:
    """Exact acquired source-cycle result bound into V1 coverage authority."""

    vault: str
    logical_key: str
    version_id: str
    fingerprint: str
    byte_length: int
    observation_cutoff: str
    accounting_complete: bool
    release_blocking: bool
    missing_source_ids: tuple[str, ...]
    duplicate_source_ids: tuple[str, ...]
    gap_source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoverageStatusManifest:
    """Complete coverage state bound into one Serving State."""

    manifest_id: str
    serving_state_id: str
    observation_cutoff: str
    scopes: tuple[CoverageScopeStatus, ...]
    source_cycle: SourceCoverageCycleBinding | None
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
