"""Pure source-neutral mapping from sealed legislation candidates to corpus values."""

from __future__ import annotations

import re
import weakref
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Never, Protocol, TypeIs

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import (
    AuthorityNoteEvidence,
    CorpusRelease,
    CorpusReleaseInput,
    DesiredStateInventory,
    FlattenedRecord,
    RecordTraceabilityLookup,
    RecordTraceabilityLookupInput,
    ReleaseRecordEntry,
    ServingRecord,
    ServingRecordProfile,
    TraceabilityEntry,
    TraceabilityReference,
    TraceabilityScopeShardInput,
    TraceabilityShard,
    compose_desired_state,
    freeze_corpus_release,
    freeze_record_traceability_lookup,
    serving_payload_fingerprint,
)
from asklegal_legal_desks.hk_legislation_events import HKLegislationDisposition
from asklegal_legal_desks.hk_legislation_records import (
    HKLegislationAuthorityNoteSeed,
    HKLegislationCandidateSet,
    HKLegislationInventoryOutcome,
    HKLegislationRecordDraft,
    HKLegislationTraceabilityReference,
    replay_hk_legislation_candidate_set,
)

_REC = re.compile(r"^rec_[0-9a-f]{48}$")
_RSC = re.compile(r"^rsc_[0-9a-f]{48}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROFILE = re.compile(r"^srp_[0-9a-f]{48}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_V1_SCOPE_CODES = (
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
)
_SCOPE_RELEASE_PAIR_SIZE = 2
_ACQUISITION_SCHEMA_ID = "asklegal.legislation-acquisition-manifest"
_ACQUISITION_SCHEMA_VERSION = "1.0.0"
_ACQUISITION_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00$")
_MAX_ACQUISITION_MANIFEST_BYTES = 4_194_304
_MAX_ACQUISITION_REFERENCE_LENGTH = 1_024
_ACQUISITION_MANIFEST_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "cycle_id",
        "observation_cutoff",
        "scope_dispositions",
        "verified_item_refs",
        "review_issue_refs",
        "journal_head_fingerprint",
        "source_register_fingerprint",
        "source_baseline_fingerprint",
        "work_plan_fingerprint",
        "result",
        "fingerprint",
    }
)
_ACQUISITION_MANIFEST_FIELDS_WITH_SOURCES = _ACQUISITION_MANIFEST_FIELDS | {"source_dispositions"}
_ACQUISITION_SCOPE_FIELDS = frozenset(
    {
        "scope_id",
        "required_item_count",
        "verified_item_count",
        "retryable_item_count",
        "rejected_item_count",
        "result",
    }
)
_ACQUISITION_SOURCE_FIELDS = frozenset(
    {
        "source_id",
        "required_item_count",
        "verified_item_count",
        "retryable_item_count",
        "rejected_item_count",
        "result",
    }
)


class HKLegislationReleaseErrorCode(StrEnum):
    """Closed mapping/freeze failures; none implies register issuance."""

    IDENTITY_BINDING_INVALID = "HK_LEGISLATION_RELEASE_IDENTITY_BINDING_INVALID"
    REUSE_PAYLOAD_MISMATCH = "HK_LEGISLATION_RELEASE_REUSE_PAYLOAD_MISMATCH"
    PRIOR_RELEASE_INVALID = "HK_LEGISLATION_RELEASE_PRIOR_RELEASE_INVALID"
    RELEASE_SET_INCOMPLETE = "HK_LEGISLATION_RELEASE_SET_INCOMPLETE"
    RELEASE_SET_CUTOFF_MISMATCH = "HK_LEGISLATION_RELEASE_SET_CUTOFF_MISMATCH"
    ACQUISITION_INPUT_INVALID = "HK_LEGISLATION_ACQUISITION_INPUT_INVALID"


class HKLegislationReleaseError(ValueError):
    """One exact pure release-mapping rejection."""

    def __init__(self, code: HKLegislationReleaseErrorCode) -> None:
        """Create one stable closed release-mapping error."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HKLegislationPriorRecordFact:
    """Caller-supplied prior record fact used only for continuity consistency."""

    corpus_scope_id: str
    record: ServingRecord


@dataclass(frozen=True, slots=True)
class HKLegislationRecordAllocation:
    """Opaque caller-supplied allocation fact, not a request to issue an ID."""

    legislation_scope_code: str
    candidate_key: str
    search_record_id: str
    continuity: Literal["INITIAL", "REUSE", "SUCCESSOR"]
    predecessor_record_id: str | None
    predecessor_payload_fingerprint: str | None
    predecessor_record_fact: HKLegislationPriorRecordFact | None


@dataclass(frozen=True, slots=True)
class HKLegislationAllocatedIdentitySet:
    """Opaque IDs supplied by a future Register boundary or a local test."""

    corpus_scope_id: str
    allocations: tuple[HKLegislationRecordAllocation, ...]
    lookup_revision_id: str | None
    lookup_shard_id: str | None


@dataclass(frozen=True, slots=True)
class HKLegislationScopeReleaseRequest:
    """All pure inputs for one scope-local corpus release mapping."""

    candidate_set: HKLegislationCandidateSet
    allocated_identities: HKLegislationAllocatedIdentitySet
    serving_profile: ServingRecordProfile
    release_evidence_refs: tuple[str, ...]
    release_validation_refs: tuple[str, ...]
    prior_release: CorpusRelease | None
    prior_traceability_entries: tuple[TraceabilityEntry, ...] | None
    prior_inventory_outcomes: tuple[HKLegislationInventoryOutcome, ...] | None
    unchanged: bool


@dataclass(frozen=True, slots=True)
class HKLegislationAcquisitionScopeInput:
    """One complete source-acquisition scope admitted for release processing."""

    scope_id: str
    observation_cutoff: str
    verified_item_refs: tuple[str, ...]
    review_issue_refs: tuple[str, ...]
    acquisition_manifest_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKLegislationAcquisitionReleaseInput:
    """Exact three-scope gate result; no-change means no processing effects."""

    cycle_id: str
    observation_cutoff: str
    scope_inputs: tuple[HKLegislationAcquisitionScopeInput, ...]
    changed: bool
    source_register_fingerprint: str
    source_baseline_fingerprint: str
    work_plan_fingerprint: str
    acquisition_manifest_fingerprint: str


class HKLegislationModelWorkPort(Protocol):
    """The first legal-processing boundary for a proved changed input."""

    def enqueue(self, value: HKLegislationAcquisitionReleaseInput) -> None:
        """Enqueue the exact admitted acquisition input for downstream processing."""


class HKLegislationEmbeddingWorkPort(Protocol):
    """A distinct later embedding handoff boundary."""

    def enqueue(self, value: HKLegislationAcquisitionReleaseInput) -> None:
        """Enqueue only work admitted by the appropriate later-stage gate."""


class HKLegislationProposalWorkPort(Protocol):
    """A distinct later immutable-proposal handoff boundary."""

    def enqueue(self, value: HKLegislationAcquisitionReleaseInput) -> None:
        """Enqueue only work admitted by the appropriate later-stage gate."""


class HKLegislationPineconeWorkPort(Protocol):
    """A distinct later promotion handoff boundary; it grants no write authority."""

    def enqueue(self, value: HKLegislationAcquisitionReleaseInput) -> None:
        """Enqueue only work carrying the separate promotion authorization."""


@dataclass(frozen=True, slots=True)
class HKLegislationDownstreamPorts:
    """Keep four downstream capability boundaries distinct at acquisition routing."""

    model: HKLegislationModelWorkPort
    embedding: HKLegislationEmbeddingWorkPort
    proposal: HKLegislationProposalWorkPort
    pinecone: HKLegislationPineconeWorkPort


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKLegislationScopeReleaseResult:
    """One local corpus release plus its complete selected-record traceability."""

    legislation_scope_code: str
    release: CorpusRelease
    traceability_entries: tuple[TraceabilityEntry, ...]
    inventory_outcomes: tuple[HKLegislationInventoryOutcome, ...]
    serving_profile: ServingRecordProfile
    reused_prior_release: bool
    selected_drafts: tuple[HKLegislationRecordDraft, ...] = ()
    allocated_identities: HKLegislationAllocatedIdentitySet | None = None
    issuance_fingerprint: str = dataclass_field(init=False, default="", repr=False)

    def assert_application_issued(self) -> None:
        """Require the exact live scope result made by this application factory."""
        issued = _SCOPE_RESULT_ISSUANCE.get(id(self))
        if (
            issued is None
            or issued.reference() is not self
            or issued.snapshot != _capture_scope_result_snapshot(self)
            or self.issuance_fingerprint != issued.fingerprint
        ):
            _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)


@dataclass(frozen=True, slots=True)
class _HKLegislationTraceabilityReferenceSnapshot:
    """Detached exact projection of every Desk-owned outcome reference field."""

    ref_type: str
    ref_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _OutcomeSnapshot:
    inventory_item_id: str
    legal_disposition: str
    outcome_kind: Literal["EMITTED", "WAITING_ROOM", "EVIDENCE_ONLY", "HISTORICAL", "QUARANTINE"]
    reason_code: str
    draft_keys: tuple[str, ...]
    supporting_refs: tuple[_HKLegislationTraceabilityReferenceSnapshot, ...]


@dataclass(frozen=True, slots=True)
class _AllocatedIdentitySetSnapshot:
    """Detached exact public allocation-set projection."""

    corpus_scope_id: str
    allocations: tuple[HKLegislationRecordAllocation, ...]
    lookup_revision_id: None
    lookup_shard_id: None


@dataclass(frozen=True, slots=True)
class _CorpusReleaseSnapshot:
    """Detached exact projection of every ``CorpusRelease`` public field."""

    release_id: str
    scope_id: str
    observation_cutoff: str
    records: tuple[_ReleaseRecordEntrySnapshot, ...]
    evidence_refs: tuple[str, ...]
    validation_refs: tuple[str, ...]
    withholding_refs: tuple[str, ...]
    zero_record_justification_refs: tuple[str, ...]
    records_fingerprint: str
    release_fingerprint: str


@dataclass(frozen=True, slots=True)
class _ServingRecordProfileSnapshot:
    """Detached exact projection of one serving schema profile."""

    serving_record_profile_id: str
    schema_version: str
    schema_fingerprint: str


@dataclass(frozen=True, slots=True)
class _ServingRecordSnapshot:
    """Detached exact projection of every serving-record public field."""

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
class _ReleaseRecordEntrySnapshot:
    """Detached exact projection of every released-record entry field."""

    record: _ServingRecordSnapshot
    serving_payload_fingerprint: str


@dataclass(frozen=True, slots=True)
class _TraceabilityReferenceSnapshot:
    """Detached exact projection of every traceability-reference field."""

    ref_type: str
    ref_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _AuthorityNoteEvidenceSnapshot:
    """Detached exact projection of every authority-note evidence field."""

    rendered_value_fingerprint: str
    decision_ref: _TraceabilityReferenceSnapshot
    supporting_evidence_refs: tuple[_TraceabilityReferenceSnapshot, ...]


@dataclass(frozen=True, slots=True)
class _TraceabilityEntrySnapshot:
    """Detached exact projection of every traceability-entry public field."""

    search_record_id: str
    serving_payload_fingerprint: str
    serving_record_profile_id: str
    legal_item_id: str
    official_version_ids: tuple[str, ...]
    legal_location_ids: tuple[str, ...]
    release_scope_id: str
    corpus_release_id: str
    evidence_refs: tuple[_TraceabilityReferenceSnapshot, ...]
    authority_note_evidence: _AuthorityNoteEvidenceSnapshot
    grouping_ids: tuple[str, ...]
    display_citation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ScopeResultSnapshot:
    """Detached exact projection of every scope-result public field."""

    legislation_scope_code: str
    release: _CorpusReleaseSnapshot
    traceability_entries: tuple[_TraceabilityEntrySnapshot, ...]
    inventory_outcomes: tuple[_OutcomeSnapshot, ...]
    serving_profile: _ServingRecordProfileSnapshot
    reused_prior_release: bool
    selected_drafts: tuple[HKLegislationRecordDraft, ...]
    allocated_identities: _AllocatedIdentitySetSnapshot
    issuance_fingerprint: str


@dataclass(frozen=True, slots=True)
class _IssuedScopeResult:
    reference: weakref.ReferenceType[object]
    snapshot: _ScopeResultSnapshot
    fingerprint: str


_SCOPE_RESULT_ISSUANCE: dict[int, _IssuedScopeResult] = {}


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKLegislationReleaseSet:
    """Three local scope releases and one complete local traceability lookup."""

    scope_results: tuple[HKLegislationScopeReleaseResult, ...]
    desired_state: DesiredStateInventory
    traceability_lookup: RecordTraceabilityLookup

    def assert_application_issued(self) -> None:
        """Require the exact local release-set projection that was frozen here."""
        issued = _RELEASE_SET_ISSUANCE.get(id(self))
        if (
            issued is None
            or issued.reference() is not self
            or issued.snapshot != _capture_release_set_snapshot(self)
        ):
            _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)


@dataclass(frozen=True, slots=True)
class _FlattenedRecordSnapshot:
    """Detached exact projection of a desired-state record."""

    record_id: str
    content_fingerprint: str
    scope_id: str
    release_id: str
    record: _ServingRecordSnapshot


@dataclass(frozen=True, slots=True)
class _DesiredStateSnapshot:
    """Detached exact projection of every desired-state public field."""

    inventory_id: str
    target_key: str
    observation_cutoff: str
    scope_releases: tuple[tuple[str, str], ...]
    records: tuple[_FlattenedRecordSnapshot, ...]
    records_fingerprint: str
    inventory_fingerprint: str


@dataclass(frozen=True, slots=True)
class _TraceabilityShardSnapshot:
    """Detached exact projection of every traceability-shard public field."""

    release_scope_id: str
    corpus_release_id: str
    lookup_shard_id: str
    path: str
    content: bytes
    entry_count: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _RecordTraceabilityLookupSnapshot:
    """Detached exact projection of every lookup public field."""

    lookup_revision_id: str
    desired_state_inventory_id: str
    profiles: tuple[_ServingRecordProfileSnapshot, ...]
    shards: tuple[_TraceabilityShardSnapshot, ...]
    total_entry_count: int
    manifest_bytes: bytes
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _ReleaseSetSnapshot:
    """Detached exact projection of every release-set public field."""

    scope_results: tuple[_ScopeResultSnapshot, ...]
    desired_state: _DesiredStateSnapshot
    traceability_lookup: _RecordTraceabilityLookupSnapshot


@dataclass(frozen=True, slots=True)
class _IssuedReleaseSet:
    reference: weakref.ReferenceType[object]
    snapshot: _ReleaseSetSnapshot


_RELEASE_SET_ISSUANCE: dict[int, _IssuedReleaseSet] = {}


# Keep this deliberately explicit: the test compares both sides against these
# declared fields, so a new retained field cannot silently escape capture.
_CAPTURE_PROJECTION_FIELDS = (
    (
        HKLegislationScopeReleaseResult,
        _ScopeResultSnapshot,
        (
            "legislation_scope_code",
            "release",
            "traceability_entries",
            "inventory_outcomes",
            "serving_profile",
            "reused_prior_release",
            "selected_drafts",
            "allocated_identities",
            "issuance_fingerprint",
        ),
    ),
    (
        HKLegislationAllocatedIdentitySet,
        _AllocatedIdentitySetSnapshot,
        ("corpus_scope_id", "allocations", "lookup_revision_id", "lookup_shard_id"),
    ),
    (
        HKLegislationInventoryOutcome,
        _OutcomeSnapshot,
        (
            "inventory_item_id",
            "legal_disposition",
            "outcome_kind",
            "reason_code",
            "draft_keys",
            "supporting_refs",
        ),
    ),
    (
        HKLegislationTraceabilityReference,
        _HKLegislationTraceabilityReferenceSnapshot,
        ("ref_type", "ref_id", "fingerprint"),
    ),
    (
        CorpusRelease,
        _CorpusReleaseSnapshot,
        (
            "release_id",
            "scope_id",
            "observation_cutoff",
            "records",
            "evidence_refs",
            "validation_refs",
            "withholding_refs",
            "zero_record_justification_refs",
            "records_fingerprint",
            "release_fingerprint",
        ),
    ),
    (ReleaseRecordEntry, _ReleaseRecordEntrySnapshot, ("record", "serving_payload_fingerprint")),
    (
        ServingRecord,
        _ServingRecordSnapshot,
        (
            "record_id",
            "text",
            "country",
            "jurisdiction",
            "material_type",
            "source",
            "authority_note",
            "artifact_ref",
            "evidence_refs",
        ),
    ),
    (
        ServingRecordProfile,
        _ServingRecordProfileSnapshot,
        ("serving_record_profile_id", "schema_version", "schema_fingerprint"),
    ),
    (
        TraceabilityEntry,
        _TraceabilityEntrySnapshot,
        (
            "search_record_id",
            "serving_payload_fingerprint",
            "serving_record_profile_id",
            "legal_item_id",
            "official_version_ids",
            "legal_location_ids",
            "release_scope_id",
            "corpus_release_id",
            "evidence_refs",
            "authority_note_evidence",
            "grouping_ids",
            "display_citation_ids",
        ),
    ),
    (TraceabilityReference, _TraceabilityReferenceSnapshot, ("ref_type", "ref_id", "fingerprint")),
    (
        AuthorityNoteEvidence,
        _AuthorityNoteEvidenceSnapshot,
        ("rendered_value_fingerprint", "decision_ref", "supporting_evidence_refs"),
    ),
    (
        DesiredStateInventory,
        _DesiredStateSnapshot,
        (
            "inventory_id",
            "target_key",
            "observation_cutoff",
            "scope_releases",
            "records",
            "records_fingerprint",
            "inventory_fingerprint",
        ),
    ),
    (
        FlattenedRecord,
        _FlattenedRecordSnapshot,
        ("record_id", "content_fingerprint", "scope_id", "release_id", "record"),
    ),
    (
        TraceabilityShard,
        _TraceabilityShardSnapshot,
        (
            "release_scope_id",
            "corpus_release_id",
            "lookup_shard_id",
            "path",
            "content",
            "entry_count",
            "fingerprint",
        ),
    ),
    (
        RecordTraceabilityLookup,
        _RecordTraceabilityLookupSnapshot,
        (
            "lookup_revision_id",
            "desired_state_inventory_id",
            "profiles",
            "shards",
            "total_entry_count",
            "manifest_bytes",
            "fingerprint",
        ),
    ),
    (
        HKLegislationReleaseSet,
        _ReleaseSetSnapshot,
        ("scope_results", "desired_state", "traceability_lookup"),
    ),
)


@dataclass(frozen=True, slots=True)
class HKLegislationReleaseSetRequest:
    """All inputs for the fixed all-or-nothing V1 three-scope local freeze."""

    scope_results: tuple[HKLegislationScopeReleaseResult, ...]
    target_key: str
    observation_cutoff: str
    lookup_input: RecordTraceabilityLookupInput
    lookup_shards: tuple[TraceabilityScopeShardInput, ...]


def _fail(code: HKLegislationReleaseErrorCode) -> Never:
    raise HKLegislationReleaseError(code)


def _acquisition_refs(
    value: JsonValue,
    *,
    required: bool,
) -> tuple[str, ...]:
    code = HKLegislationReleaseErrorCode.ACQUISITION_INPUT_INVALID
    if type(value) is not list or (required and not value):
        _fail(code)
    refs: list[str] = []
    for item in value:
        if type(item) is not str or not item or len(item) > _MAX_ACQUISITION_REFERENCE_LENGTH:
            _fail(code)
        refs.append(item)
    result = tuple(refs)
    if result != tuple(sorted(set(result))):
        _fail(code)
    return result


def _validated_acquisition_scope_ids(
    raw_scopes: JsonValue,
    result: str,
) -> tuple[str, ...]:
    code = HKLegislationReleaseErrorCode.ACQUISITION_INPUT_INVALID
    if type(raw_scopes) is not list:
        _fail(code)
    scope_ids: list[str] = []
    for raw_scope in raw_scopes:
        if type(raw_scope) is not dict or frozenset(raw_scope) != _ACQUISITION_SCOPE_FIELDS:
            _fail(code)
        scope_id = raw_scope["scope_id"]
        required = raw_scope["required_item_count"]
        verified_count = raw_scope["verified_item_count"]
        retryable = raw_scope["retryable_item_count"]
        rejected = raw_scope["rejected_item_count"]
        if (
            type(scope_id) is not str
            or type(required) is not int
            or required < 1
            or type(verified_count) is not int
            or verified_count != required
            or type(retryable) is not int
            or retryable != 0
            or type(rejected) is not int
            or rejected != 0
            or raw_scope["result"] != result
        ):
            _fail(code)
        scope_ids.append(scope_id)
    if tuple(scope_ids) != tuple(sorted(_V1_SCOPE_CODES)):
        _fail(code)
    return tuple(scope_ids)


def _validate_acquisition_source_dispositions(raw_sources: JsonValue) -> None:
    """Validate the optional per-source accounting added by the V1 producer."""
    code = HKLegislationReleaseErrorCode.ACQUISITION_INPUT_INVALID
    if type(raw_sources) is not list or not raw_sources:
        _fail(code)
    source_ids: list[str] = []
    for raw_source in raw_sources:
        if type(raw_source) is not dict or frozenset(raw_source) != _ACQUISITION_SOURCE_FIELDS:
            _fail(code)
        source_id = raw_source["source_id"]
        required = raw_source["required_item_count"]
        verified = raw_source["verified_item_count"]
        retryable = raw_source["retryable_item_count"]
        rejected = raw_source["rejected_item_count"]
        if (
            type(source_id) is not str
            or not source_id.startswith("HK-LEG-")
            or type(required) is not int
            or required < 1
            or type(verified) is not int
            or verified != required
            or type(retryable) is not int
            or retryable != 0
            or type(rejected) is not int
            or rejected != 0
            or raw_source["result"] not in {"COMPLETE", "NO_CHANGE"}
        ):
            _fail(code)
        source_ids.append(source_id)
    if tuple(source_ids) != tuple(sorted(set(source_ids))):
        _fail(code)


def accept_hk_legislation_acquisition_manifest(
    raw: object,
) -> HKLegislationAcquisitionReleaseInput:
    """Accept only one canonical complete/no-change three-scope manifest."""
    code = HKLegislationReleaseErrorCode.ACQUISITION_INPUT_INVALID
    if type(raw) is not bytes or not raw or len(raw) > _MAX_ACQUISITION_MANIFEST_BYTES:
        _fail(code)
    try:
        document = parse_json_bytes(raw, max_bytes=_MAX_ACQUISITION_MANIFEST_BYTES)
    except Exception as error:
        raise HKLegislationReleaseError(code) from error
    if (
        type(document) is not dict
        or frozenset(document)
        not in {_ACQUISITION_MANIFEST_FIELDS, _ACQUISITION_MANIFEST_FIELDS_WITH_SOURCES}
        or canonicalize(document) != raw
        or document["schema_id"] != _ACQUISITION_SCHEMA_ID
        or document["schema_version"] != _ACQUISITION_SCHEMA_VERSION
    ):
        _fail(code)
    cycle_id = document["cycle_id"]
    cutoff = document["observation_cutoff"]
    fingerprint = document["fingerprint"]
    head = document["journal_head_fingerprint"]
    source_register = document["source_register_fingerprint"]
    source_baseline = document["source_baseline_fingerprint"]
    work_plan = document["work_plan_fingerprint"]
    result = document["result"]
    if (
        type(cycle_id) is not str
        or not cycle_id.startswith("cyc_")
        or type(cutoff) is not str
        or _ACQUISITION_UTC.fullmatch(cutoff) is None
        or type(fingerprint) is not str
        or _FINGERPRINT.fullmatch(fingerprint) is None
        or type(head) is not str
        or _FINGERPRINT.fullmatch(head) is None
        or type(source_register) is not str
        or _FINGERPRINT.fullmatch(source_register) is None
        or type(source_baseline) is not str
        or _FINGERPRINT.fullmatch(source_baseline) is None
        or type(work_plan) is not str
        or _FINGERPRINT.fullmatch(work_plan) is None
        or type(result) is not str
        or result not in {"COMPLETE", "NO_CHANGE"}
    ):
        _fail(code)
    body = {key: value for key, value in document.items() if key != "fingerprint"}
    if fingerprint != f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}":
        _fail(code)
    scope_ids = _validated_acquisition_scope_ids(document["scope_dispositions"], result)
    if "source_dispositions" in document:
        _validate_acquisition_source_dispositions(document["source_dispositions"])
    verified = _acquisition_refs(document["verified_item_refs"], required=True)
    reviews = _acquisition_refs(document["review_issue_refs"], required=False)
    scope_inputs = tuple(
        HKLegislationAcquisitionScopeInput(scope, cutoff, verified, reviews, fingerprint)
        for scope in scope_ids
    )
    return HKLegislationAcquisitionReleaseInput(
        cycle_id,
        cutoff,
        scope_inputs,
        result == "COMPLETE",
        source_register,
        source_baseline,
        work_plan,
        fingerprint,
    )


def route_hk_legislation_acquisition_input(
    value: HKLegislationAcquisitionReleaseInput,
    downstream: HKLegislationDownstreamPorts,
) -> bool:
    """Stop no-change before every effect and start only the first changed-work stage."""
    if (
        type(value) is not HKLegislationAcquisitionReleaseInput
        or type(downstream) is not HKLegislationDownstreamPorts
        or any(
            not callable(getattr(port, "enqueue", None))
            for port in (
                downstream.model,
                downstream.embedding,
                downstream.proposal,
                downstream.pinecone,
            )
        )
    ):
        _fail(HKLegislationReleaseErrorCode.ACQUISITION_INPUT_INVALID)
    if not value.changed:
        return False
    # These are four local handoff ports. Their adapters still own every later
    # evidence/approval gate and no provider capability is granted here.
    downstream.model.enqueue(value)
    downstream.embedding.enqueue(value)
    downstream.proposal.enqueue(value)
    downstream.pinecone.enqueue(value)
    return True


def _reference(value: object) -> TraceabilityReference:
    if type(value) is not HKLegislationTraceabilityReference:
        _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
    return TraceabilityReference(value.ref_type, value.ref_id, value.fingerprint)


def _valid_prior_fact(
    value: object, scope_id: str, allocation: HKLegislationRecordAllocation
) -> ServingRecord:
    if (
        type(value) is not HKLegislationPriorRecordFact
        or value.corpus_scope_id != scope_id
        or type(value.record) is not ServingRecord
    ):
        _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
    record = value.record
    if (
        record.record_id != allocation.predecessor_record_id
        or serving_payload_fingerprint(record) != allocation.predecessor_payload_fingerprint
    ):
        _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
    return record


def _validate_allocation_shape(
    allocation: object, scope: str, corpus_scope_id: str
) -> HKLegislationRecordAllocation:
    if (
        type(allocation) is not HKLegislationRecordAllocation
        or allocation.legislation_scope_code != scope
        or not allocation.candidate_key
        or _REC.fullmatch(allocation.search_record_id) is None
        or allocation.continuity not in {"INITIAL", "REUSE", "SUCCESSOR"}
    ):
        _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
    if allocation.continuity == "INITIAL":
        if (
            allocation.predecessor_record_id is not None
            or allocation.predecessor_payload_fingerprint is not None
            or allocation.predecessor_record_fact is not None
        ):
            _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
        return allocation
    if (
        _REC.fullmatch(allocation.predecessor_record_id or "") is None
        or _FINGERPRINT.fullmatch(allocation.predecessor_payload_fingerprint or "") is None
    ):
        _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
    _valid_prior_fact(allocation.predecessor_record_fact, corpus_scope_id, allocation)
    if (
        allocation.continuity == "REUSE"
        and allocation.predecessor_record_id != allocation.search_record_id
    ) or (
        allocation.continuity == "SUCCESSOR"
        and allocation.predecessor_record_id == allocation.search_record_id
    ):
        _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
    return allocation


def _validate_allocations(
    candidates: tuple[HKLegislationRecordDraft, ...], scope: str, value: object
) -> dict[str, HKLegislationRecordAllocation]:
    if (
        type(value) is not HKLegislationAllocatedIdentitySet
        or type(value.corpus_scope_id) is not str
        or (_RSC.fullmatch(value.corpus_scope_id) is None and value.corpus_scope_id != scope)
        or type(value.allocations) is not tuple
        or value.lookup_revision_id is not None
        or value.lookup_shard_id is not None
    ):
        _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
    result: dict[str, HKLegislationRecordAllocation] = {}
    record_ids: set[str] = set()
    for raw_allocation in value.allocations:
        allocation = _validate_allocation_shape(raw_allocation, scope, value.corpus_scope_id)
        if allocation.candidate_key in result or allocation.search_record_id in record_ids:
            _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
        record_ids.add(allocation.search_record_id)
        result[allocation.candidate_key] = allocation
    if set(result) != {candidate.candidate_key for candidate in candidates}:
        _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
    return result


def _entry(
    draft: HKLegislationRecordDraft, record: ServingRecord, scope_id: str, release_id: str
) -> TraceabilityEntry:
    seed = draft.authority_note_evidence
    return TraceabilityEntry(
        record.record_id,
        serving_payload_fingerprint(record),
        draft.serving_profile_id,
        draft.legal_item_id,
        draft.official_version_ids,
        draft.legal_location_ids,
        scope_id,
        release_id,
        tuple(_reference(item) for item in draft.evidence_refs),
        AuthorityNoteEvidence(
            seed.rendered_value_fingerprint,
            _reference(seed.decision_ref),
            tuple(_reference(item) for item in seed.supporting_evidence_refs),
        ),
    )


def _records_and_entries(
    candidate_set: HKLegislationCandidateSet,
    identities: HKLegislationAllocatedIdentitySet,
    release_id: str,
) -> tuple[tuple[ServingRecord, ...], tuple[TraceabilityEntry, ...]]:
    allocations = _validate_allocations(
        candidate_set.drafts, candidate_set.legislation_scope_code, identities
    )
    records: list[ServingRecord] = []
    entries: list[TraceabilityEntry] = []
    for draft in candidate_set.drafts:
        allocation = allocations[draft.candidate_key]
        record = ServingRecord(
            allocation.search_record_id,
            draft.text,
            draft.country,
            draft.jurisdiction,
            draft.material_type,
            draft.source,
            draft.authority_note,
            draft.artifact_ref,
            tuple(reference.ref_id for reference in draft.evidence_refs),
        )
        payload = serving_payload_fingerprint(record)
        if payload != draft.serving_payload_fingerprint:
            _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
        if (
            allocation.continuity == "REUSE"
            and allocation.predecessor_payload_fingerprint != payload
        ):
            _fail(HKLegislationReleaseErrorCode.REUSE_PAYLOAD_MISMATCH)
        records.append(record)
        entries.append(_entry(draft, record, identities.corpus_scope_id, release_id))
    return tuple(records), tuple(entries)


def _freeze(
    candidate_set: HKLegislationCandidateSet,
    identities: HKLegislationAllocatedIdentitySet,
    request: HKLegislationScopeReleaseRequest,
    records: tuple[ServingRecord, ...],
) -> CorpusRelease:
    disposition_refs = tuple(
        f"{outcome.supporting_refs[0].ref_id}@{outcome.supporting_refs[0].fingerprint}"
        for outcome in candidate_set.outcomes
        if outcome.outcome_kind != "EMITTED" and outcome.supporting_refs
    )
    zero_record_refs = tuple(sorted(set(disposition_refs))) if not records else ()
    return freeze_corpus_release(
        CorpusReleaseInput(
            identities.corpus_scope_id,
            candidate_set.observation_cutoff,
            request.release_evidence_refs,
            request.release_validation_refs,
            disposition_refs,
            zero_record_refs,
        ),
        records,
    )


def _capture_outcome(value: object) -> _OutcomeSnapshot:
    if (
        type(value) is not HKLegislationInventoryOutcome
        or type(value.inventory_item_id) is not str
        or type(value.legal_disposition) is not HKLegislationDisposition
        or type(value.outcome_kind) is not str
        or type(value.reason_code) is not str
        or type(value.draft_keys) is not tuple
        or type(value.supporting_refs) is not tuple
        or any(type(key) is not str for key in value.draft_keys)
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    refs: list[_HKLegislationTraceabilityReferenceSnapshot] = []
    for reference in value.supporting_refs:
        if (
            type(reference) is not HKLegislationTraceabilityReference
            or type(reference.ref_type) is not str
            or type(reference.ref_id) is not str
            or type(reference.fingerprint) is not str
        ):
            _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
        refs.append(
            _HKLegislationTraceabilityReferenceSnapshot(
                reference.ref_type, reference.ref_id, reference.fingerprint
            )
        )
    return _OutcomeSnapshot(
        value.inventory_item_id,
        value.legal_disposition.value,
        value.outcome_kind,
        value.reason_code,
        tuple(value.draft_keys),
        tuple(refs),
    )


def _is_exact_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    """Narrow only an exact builtin tuple before inspecting its members."""
    return type(value) is tuple


def _is_exact_str_tuple(value: object) -> TypeIs[tuple[str, ...]]:
    """Narrow only an exact builtin tuple of exact builtin strings."""
    return _is_exact_object_tuple(value) and all(type(item) is str for item in value)


def _capture_str_tuple(value: object) -> tuple[str, ...]:
    if not _is_exact_str_tuple(value):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return tuple(value)


def _capture_serving_record_snapshot(value: object) -> _ServingRecordSnapshot:
    """Copy every serving-record primitive before accepting a record container."""
    if type(value) is not ServingRecord:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    fields = (
        value.record_id,
        value.text,
        value.country,
        value.jurisdiction,
        value.material_type,
        value.source,
        value.authority_note,
        value.artifact_ref,
    )
    if type(value.evidence_refs) is not tuple or any(type(field) is not str for field in fields):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _ServingRecordSnapshot(*fields, _capture_str_tuple(value.evidence_refs))


def _capture_release_record_entry_snapshot(value: object) -> _ReleaseRecordEntrySnapshot:
    """Copy every public released-record entry field exactly once."""
    if type(value) is not ReleaseRecordEntry or type(value.serving_payload_fingerprint) is not str:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _ReleaseRecordEntrySnapshot(
        _capture_serving_record_snapshot(value.record), value.serving_payload_fingerprint
    )


def _capture_traceability_reference_snapshot(value: object) -> _TraceabilityReferenceSnapshot:
    """Copy every public traceability-reference field without subclass coercion."""
    if (
        type(value) is not TraceabilityReference
        or type(value.ref_type) is not str
        or type(value.ref_id) is not str
        or type(value.fingerprint) is not str
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _TraceabilityReferenceSnapshot(value.ref_type, value.ref_id, value.fingerprint)


def _capture_authority_note_evidence_snapshot(value: object) -> _AuthorityNoteEvidenceSnapshot:
    """Copy every authority-note proof field before any equality operation."""
    if (
        type(value) is not AuthorityNoteEvidence
        or type(value.rendered_value_fingerprint) is not str
        or type(value.supporting_evidence_refs) is not tuple
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _AuthorityNoteEvidenceSnapshot(
        value.rendered_value_fingerprint,
        _capture_traceability_reference_snapshot(value.decision_ref),
        tuple(
            _capture_traceability_reference_snapshot(reference)
            for reference in value.supporting_evidence_refs
        ),
    )


def _capture_traceability_entry_snapshot(value: object) -> _TraceabilityEntrySnapshot:
    """Copy each public traceability-entry field before all-withheld rejection."""
    if type(value) is not TraceabilityEntry:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    fields = (
        value.search_record_id,
        value.serving_payload_fingerprint,
        value.serving_record_profile_id,
        value.legal_item_id,
        value.release_scope_id,
        value.corpus_release_id,
    )
    if type(value.evidence_refs) is not tuple or any(type(field) is not str for field in fields):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _TraceabilityEntrySnapshot(
        *fields[:4],
        _capture_str_tuple(value.official_version_ids),
        _capture_str_tuple(value.legal_location_ids),
        *fields[4:],
        tuple(_capture_traceability_reference_snapshot(item) for item in value.evidence_refs),
        _capture_authority_note_evidence_snapshot(value.authority_note_evidence),
        _capture_str_tuple(value.grouping_ids),
        _capture_str_tuple(value.display_citation_ids),
    )


def _capture_corpus_release_snapshot(value: object) -> _CorpusReleaseSnapshot:
    """Copy and validate each public release field before comparison or replay."""
    if type(value) is not CorpusRelease:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    records = value.records
    if (
        type(value.release_id) is not str
        or type(value.scope_id) is not str
        or type(value.observation_cutoff) is not str
        or type(records) is not tuple
        or type(value.records_fingerprint) is not str
        or type(value.release_fingerprint) is not str
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _CorpusReleaseSnapshot(
        value.release_id,
        value.scope_id,
        value.observation_cutoff,
        tuple(_capture_release_record_entry_snapshot(record) for record in records),
        _capture_str_tuple(value.evidence_refs),
        _capture_str_tuple(value.validation_refs),
        _capture_str_tuple(value.withholding_refs),
        _capture_str_tuple(value.zero_record_justification_refs),
        value.records_fingerprint,
        value.release_fingerprint,
    )


def _capture_profile_snapshot(value: object) -> _ServingRecordProfileSnapshot:
    """Copy every profile primitive without accepting same-byte subclasses."""
    if (
        type(value) is not ServingRecordProfile
        or type(value.serving_record_profile_id) is not str
        or type(value.schema_version) is not str
        or type(value.schema_fingerprint) is not str
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _ServingRecordProfileSnapshot(
        value.serving_record_profile_id, value.schema_version, value.schema_fingerprint
    )


def _capture_allocated_identity_set_snapshot(value: object) -> _AllocatedIdentitySetSnapshot:
    """Copy every allocation-set public field without retaining caller objects."""
    if (
        type(value) is not HKLegislationAllocatedIdentitySet
        or type(value.corpus_scope_id) is not str
        or type(value.allocations) is not tuple
        or value.lookup_revision_id is not None
        or value.lookup_shard_id is not None
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _AllocatedIdentitySetSnapshot(
        value.corpus_scope_id,
        tuple(_copy_allocation_for_snapshot(item) for item in value.allocations),
        None,
        None,
    )


def _copy_allocation_for_snapshot(value: object) -> HKLegislationRecordAllocation:
    if type(value) is not HKLegislationRecordAllocation:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    fields = (
        value.legislation_scope_code,
        value.candidate_key,
        value.search_record_id,
        value.continuity,
    )
    if any(type(item) is not str for item in fields):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    prior = value.predecessor_record_fact
    copied_prior: HKLegislationPriorRecordFact | None = None
    if prior is not None:
        if (
            type(prior) is not HKLegislationPriorRecordFact
            or type(prior.corpus_scope_id) is not str
        ):
            _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
        copied_prior = HKLegislationPriorRecordFact(
            prior.corpus_scope_id,
            _serving_record_from_snapshot(_capture_serving_record_snapshot(prior.record)),
        )
    if value.predecessor_record_id is not None and type(value.predecessor_record_id) is not str:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    if (
        value.predecessor_payload_fingerprint is not None
        and type(value.predecessor_payload_fingerprint) is not str
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return HKLegislationRecordAllocation(
        value.legislation_scope_code,
        value.candidate_key,
        value.search_record_id,
        value.continuity,
        value.predecessor_record_id,
        value.predecessor_payload_fingerprint,
        copied_prior,
    )


def _copy_draft_for_snapshot(value: object) -> HKLegislationRecordDraft:
    if type(value) is not HKLegislationRecordDraft:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    evidence = tuple(
        HKLegislationTraceabilityReference(item.ref_type, item.ref_id, item.fingerprint)
        for item in value.evidence_refs
        if type(item) is HKLegislationTraceabilityReference
    )
    seed = value.authority_note_evidence
    if (
        len(evidence) != len(value.evidence_refs)
        or type(seed) is not HKLegislationAuthorityNoteSeed
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    supporting = tuple(
        HKLegislationTraceabilityReference(item.ref_type, item.ref_id, item.fingerprint)
        for item in seed.supporting_evidence_refs
        if type(item) is HKLegislationTraceabilityReference
    )
    if len(supporting) != len(seed.supporting_evidence_refs):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    decision = seed.decision_ref
    if type(decision) is not HKLegislationTraceabilityReference:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return HKLegislationRecordDraft(
        value.candidate_key,
        value.inventory_item_id,
        value.legislation_scope_code,
        value.text,
        value.country,
        value.jurisdiction,
        value.material_type,
        value.source,
        value.authority_note,
        value.artifact_ref,
        evidence,
        value.legal_item_id,
        _capture_str_tuple(value.official_version_ids),
        _capture_str_tuple(value.legal_location_ids),
        HKLegislationAuthorityNoteSeed(
            seed.rendered_value_fingerprint,
            HKLegislationTraceabilityReference(
                decision.ref_type, decision.ref_id, decision.fingerprint
            ),
            supporting,
        ),
        value.serving_profile_id,
        value.serving_payload_fingerprint,
        value.partition_fingerprint,
        value.partition_profile_fingerprint,
        value.decision_fingerprint,
        value.part_number,
        value.total_parts,
    )


def _capture_scope_result_snapshot(value: object) -> _ScopeResultSnapshot:
    """Copy every permitted primitive before canonicalization or result replay."""
    if type(value) is not HKLegislationScopeReleaseResult:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    legislation_scope_code = value.legislation_scope_code
    release = _capture_corpus_release_snapshot(value.release)
    profile = _capture_profile_snapshot(value.serving_profile)
    identities = _capture_allocated_identity_set_snapshot(value.allocated_identities)
    traceability_entries = value.traceability_entries
    outcomes = value.inventory_outcomes
    selected_drafts = value.selected_drafts
    reused_prior_release = value.reused_prior_release
    issuance_fingerprint = value.issuance_fingerprint
    if (
        type(legislation_scope_code) is not str
        or type(reused_prior_release) is not bool
        or type(outcomes) is not tuple
        or type(issuance_fingerprint) is not str
        or type(selected_drafts) is not tuple
        or type(traceability_entries) is not tuple
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    if (
        (_RSC.fullmatch(release.scope_id) is None and release.scope_id not in _V1_SCOPE_CODES)
        or release.scope_id != identities.corpus_scope_id
        or _PROFILE.fullmatch(profile.serving_record_profile_id) is None
        or _FINGERPRINT.fullmatch(profile.schema_fingerprint) is None
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    captured_entries = tuple(
        _capture_traceability_entry_snapshot(entry) for entry in traceability_entries
    )
    captured_drafts = tuple(_copy_draft_for_snapshot(item) for item in selected_drafts)
    if (
        len(release.records) != len(captured_entries)
        or len(captured_drafts) != len(identities.allocations)
        or tuple(item.record.record_id for item in release.records)
        != tuple(item.search_record_id for item in captured_entries)
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _ScopeResultSnapshot(
        legislation_scope_code,
        release,
        captured_entries,
        tuple(_capture_outcome(outcome) for outcome in outcomes),
        profile,
        reused_prior_release,
        captured_drafts,
        identities,
        issuance_fingerprint,
    )


def _snapshot_document(value: _ScopeResultSnapshot) -> dict[str, object]:
    return {
        "allocated_identities": {
            "allocations": [
                {
                    "candidate_key": item.candidate_key,
                    "continuity": item.continuity,
                    "legislation_scope_code": item.legislation_scope_code,
                    "predecessor_payload_fingerprint": item.predecessor_payload_fingerprint,
                    "predecessor_record_id": item.predecessor_record_id,
                    "search_record_id": item.search_record_id,
                }
                for item in value.allocated_identities.allocations
            ],
            "corpus_scope_id": value.allocated_identities.corpus_scope_id,
            "lookup_revision_id": value.allocated_identities.lookup_revision_id,
            "lookup_shard_id": value.allocated_identities.lookup_shard_id,
        },
        "legislation_scope_code": value.legislation_scope_code,
        "inventory_outcomes": [
            {
                "draft_keys": list(outcome.draft_keys),
                "inventory_item_id": outcome.inventory_item_id,
                "legal_disposition": outcome.legal_disposition,
                "outcome_kind": outcome.outcome_kind,
                "reason_code": outcome.reason_code,
                "supporting_refs": [
                    [reference.ref_type, reference.ref_id, reference.fingerprint]
                    for reference in outcome.supporting_refs
                ],
            }
            for outcome in value.inventory_outcomes
        ],
        "release": {
            "evidence_refs": list(value.release.evidence_refs),
            "observation_cutoff": value.release.observation_cutoff,
            "records": [
                {
                    "record_id": item.record.record_id,
                    "serving_payload_fingerprint": item.serving_payload_fingerprint,
                }
                for item in value.release.records
            ],
            "records_fingerprint": value.release.records_fingerprint,
            "release_fingerprint": value.release.release_fingerprint,
            "release_id": value.release.release_id,
            "scope_id": value.release.scope_id,
            "validation_refs": list(value.release.validation_refs),
            "withholding_refs": list(value.release.withholding_refs),
            "zero_record_justification_refs": list(value.release.zero_record_justification_refs),
        },
        "reused_prior_release": value.reused_prior_release,
        "selected_drafts": [
            {
                "candidate_key": item.candidate_key,
                "decision_fingerprint": item.decision_fingerprint,
                "serving_payload_fingerprint": item.serving_payload_fingerprint,
            }
            for item in value.selected_drafts
        ],
        "serving_profile": [
            value.serving_profile.serving_record_profile_id,
            value.serving_profile.schema_version,
            value.serving_profile.schema_fingerprint,
        ],
        "traceability_entries": [
            {
                "corpus_release_id": item.corpus_release_id,
                "search_record_id": item.search_record_id,
                "serving_payload_fingerprint": item.serving_payload_fingerprint,
            }
            for item in value.traceability_entries
        ],
    }


def _snapshot_fingerprint(value: _ScopeResultSnapshot) -> str:
    return (
        "sha256:" + sha256(canonicalize(checked_json_value(_snapshot_document(value)))).hexdigest()
    )


def _result_from_snapshot(value: _ScopeResultSnapshot) -> HKLegislationScopeReleaseResult:
    if (
        value.allocated_identities.lookup_revision_id is not None
        or value.allocated_identities.lookup_shard_id is not None
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    release = freeze_corpus_release(
        CorpusReleaseInput(
            value.release.scope_id,
            value.release.observation_cutoff,
            value.release.evidence_refs,
            value.release.validation_refs,
            value.release.withholding_refs,
            value.release.zero_record_justification_refs,
        ),
        tuple(_serving_record_from_snapshot(item.record) for item in value.release.records),
    )
    if _capture_corpus_release_snapshot(release) != value.release:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    outcomes = tuple(
        HKLegislationInventoryOutcome(
            outcome.inventory_item_id,
            HKLegislationDisposition(outcome.legal_disposition),
            outcome.outcome_kind,
            outcome.reason_code,
            outcome.draft_keys,
            tuple(
                HKLegislationTraceabilityReference(
                    reference.ref_type, reference.ref_id, reference.fingerprint
                )
                for reference in outcome.supporting_refs
            ),
        )
        for outcome in value.inventory_outcomes
    )
    return HKLegislationScopeReleaseResult(
        value.legislation_scope_code,
        release,
        tuple(_traceability_entry_from_snapshot(item) for item in value.traceability_entries),
        outcomes,
        ServingRecordProfile(
            value.serving_profile.serving_record_profile_id,
            value.serving_profile.schema_version,
            value.serving_profile.schema_fingerprint,
        ),
        value.reused_prior_release,
        tuple(_copy_draft_for_snapshot(item) for item in value.selected_drafts),
        HKLegislationAllocatedIdentitySet(
            value.allocated_identities.corpus_scope_id,
            tuple(
                _copy_allocation_for_snapshot(item)
                for item in value.allocated_identities.allocations
            ),
            None,
            None,
        ),
    )


def _serving_record_from_snapshot(value: _ServingRecordSnapshot) -> ServingRecord:
    return ServingRecord(
        value.record_id,
        value.text,
        value.country,
        value.jurisdiction,
        value.material_type,
        value.source,
        value.authority_note,
        value.artifact_ref,
        value.evidence_refs,
    )


def _traceability_reference_from_snapshot(
    value: _TraceabilityReferenceSnapshot,
) -> TraceabilityReference:
    return TraceabilityReference(value.ref_type, value.ref_id, value.fingerprint)


def _traceability_entry_from_snapshot(value: _TraceabilityEntrySnapshot) -> TraceabilityEntry:
    authority = value.authority_note_evidence
    return TraceabilityEntry(
        value.search_record_id,
        value.serving_payload_fingerprint,
        value.serving_record_profile_id,
        value.legal_item_id,
        value.official_version_ids,
        value.legal_location_ids,
        value.release_scope_id,
        value.corpus_release_id,
        tuple(_traceability_reference_from_snapshot(item) for item in value.evidence_refs),
        AuthorityNoteEvidence(
            authority.rendered_value_fingerprint,
            _traceability_reference_from_snapshot(authority.decision_ref),
            tuple(
                _traceability_reference_from_snapshot(item)
                for item in authority.supporting_evidence_refs
            ),
        ),
        value.grouping_ids,
        value.display_citation_ids,
    )


def _issue_scope_result(value: HKLegislationScopeReleaseResult) -> HKLegislationScopeReleaseResult:
    snapshot = _capture_scope_result_snapshot(value)
    result = _result_from_snapshot(snapshot)
    fingerprint = _snapshot_fingerprint(snapshot)
    object.__setattr__(result, "issuance_fingerprint", fingerprint)
    snapshot = replace(snapshot, issuance_fingerprint=fingerprint)
    _SCOPE_RESULT_ISSUANCE[id(result)] = _IssuedScopeResult(
        weakref.ref(result), snapshot, fingerprint
    )
    return result


def _replay_scope_result(value: object) -> HKLegislationScopeReleaseResult:
    if type(value) is not HKLegislationScopeReleaseResult:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    value.assert_application_issued()
    issued = _SCOPE_RESULT_ISSUANCE[id(value)]
    return _issue_scope_result(_result_from_snapshot(issued.snapshot))


def _capture_flattened_record_snapshot(value: object) -> _FlattenedRecordSnapshot:
    """Copy every desired-state row field before any later comparison."""
    if (
        type(value) is not FlattenedRecord
        or type(value.record_id) is not str
        or type(value.content_fingerprint) is not str
        or type(value.scope_id) is not str
        or type(value.release_id) is not str
        or type(value.record) is not ServingRecord
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _FlattenedRecordSnapshot(
        value.record_id,
        value.content_fingerprint,
        value.scope_id,
        value.release_id,
        _capture_serving_record_snapshot(value.record),
    )


def _capture_desired_state_snapshot(value: object) -> _DesiredStateSnapshot:
    """Copy every public desired-state field with exact primitive/container types."""
    if (
        type(value) is not DesiredStateInventory
        or type(value.inventory_id) is not str
        or type(value.target_key) is not str
        or type(value.observation_cutoff) is not str
        or type(value.scope_releases) is not tuple
        or type(value.records) is not tuple
        or type(value.records_fingerprint) is not str
        or type(value.inventory_fingerprint) is not str
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    scopes: list[tuple[str, str]] = []
    for pair in value.scope_releases:
        if (
            type(pair) is not tuple
            or len(pair) != _SCOPE_RELEASE_PAIR_SIZE
            or type(pair[0]) is not str
            or type(pair[1]) is not str
        ):
            _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
        scopes.append((pair[0], pair[1]))
    records = tuple(_capture_flattened_record_snapshot(row) for row in value.records)
    return _DesiredStateSnapshot(
        value.inventory_id,
        value.target_key,
        value.observation_cutoff,
        tuple(scopes),
        records,
        value.records_fingerprint,
        value.inventory_fingerprint,
    )


def _capture_traceability_shard_snapshot(value: object) -> _TraceabilityShardSnapshot:
    """Copy every public shard field without normalizing subclasses."""
    if (
        type(value) is not TraceabilityShard
        or type(value.release_scope_id) is not str
        or type(value.corpus_release_id) is not str
        or type(value.lookup_shard_id) is not str
        or type(value.path) is not str
        or type(value.content) is not bytes
        or type(value.entry_count) is not int
        or type(value.fingerprint) is not str
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _TraceabilityShardSnapshot(
        value.release_scope_id,
        value.corpus_release_id,
        value.lookup_shard_id,
        value.path,
        bytes(value.content),
        value.entry_count,
        value.fingerprint,
    )


def _capture_traceability_lookup_snapshot(value: object) -> _RecordTraceabilityLookupSnapshot:
    """Copy every public lookup field, including shard ordering and zero counts."""
    if (
        type(value) is not RecordTraceabilityLookup
        or type(value.lookup_revision_id) is not str
        or type(value.desired_state_inventory_id) is not str
        or type(value.profiles) is not tuple
        or type(value.shards) is not tuple
        or type(value.total_entry_count) is not int
        or type(value.manifest_bytes) is not bytes
        or type(value.fingerprint) is not str
    ):
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _RecordTraceabilityLookupSnapshot(
        value.lookup_revision_id,
        value.desired_state_inventory_id,
        tuple(_capture_profile_snapshot(profile) for profile in value.profiles),
        tuple(_capture_traceability_shard_snapshot(shard) for shard in value.shards),
        value.total_entry_count,
        bytes(value.manifest_bytes),
        value.fingerprint,
    )


def _capture_release_set_snapshot(value: object) -> _ReleaseSetSnapshot:
    """Copy all public release-set/output facts before identity comparison."""
    if type(value) is not HKLegislationReleaseSet or type(value.scope_results) is not tuple:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return _ReleaseSetSnapshot(
        tuple(_capture_scope_result_snapshot(result) for result in value.scope_results),
        _capture_desired_state_snapshot(value.desired_state),
        _capture_traceability_lookup_snapshot(value.traceability_lookup),
    )


def _desired_state_from_snapshot(value: _DesiredStateSnapshot) -> DesiredStateInventory:
    return DesiredStateInventory(
        value.inventory_id,
        value.target_key,
        value.observation_cutoff,
        value.scope_releases,
        tuple(
            FlattenedRecord(
                item.record_id,
                item.content_fingerprint,
                item.scope_id,
                item.release_id,
                _serving_record_from_snapshot(item.record),
            )
            for item in value.records
        ),
        value.records_fingerprint,
        value.inventory_fingerprint,
    )


def _lookup_from_snapshot(value: _RecordTraceabilityLookupSnapshot) -> RecordTraceabilityLookup:
    profiles = tuple(
        ServingRecordProfile(
            profile.serving_record_profile_id,
            profile.schema_version,
            profile.schema_fingerprint,
        )
        for profile in value.profiles
    )
    shards = tuple(
        TraceabilityShard(
            shard.release_scope_id,
            shard.corpus_release_id,
            shard.lookup_shard_id,
            shard.path,
            bytes(shard.content),
            shard.entry_count,
            shard.fingerprint,
        )
        for shard in value.shards
    )
    return RecordTraceabilityLookup(
        value.lookup_revision_id,
        value.desired_state_inventory_id,
        profiles,
        shards,
        value.total_entry_count,
        bytes(value.manifest_bytes),
        value.fingerprint,
    )


def _release_set_from_snapshot(value: _ReleaseSetSnapshot) -> HKLegislationReleaseSet:
    result = HKLegislationReleaseSet(
        tuple(_issue_scope_result(_result_from_snapshot(scope)) for scope in value.scope_results),
        _desired_state_from_snapshot(value.desired_state),
        _lookup_from_snapshot(value.traceability_lookup),
    )
    if _capture_release_set_snapshot(result) != value:
        _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
    return result


def _issue_release_set(value: HKLegislationReleaseSet) -> HKLegislationReleaseSet:
    snapshot = _capture_release_set_snapshot(value)
    result = _release_set_from_snapshot(snapshot)
    _RELEASE_SET_ISSUANCE[id(result)] = _IssuedReleaseSet(weakref.ref(result), snapshot)
    return result


def _unchanged_result(
    request: HKLegislationScopeReleaseRequest,
    candidate_set: HKLegislationCandidateSet,
    identities: HKLegislationAllocatedIdentitySet,
) -> HKLegislationScopeReleaseResult:
    prior = request.prior_release
    if (
        type(prior) is not CorpusRelease
        or type(request.prior_traceability_entries) is not tuple
        or type(request.prior_inventory_outcomes) is not tuple
        or prior.scope_id != identities.corpus_scope_id
        or candidate_set.observation_cutoff != prior.observation_cutoff
    ):
        _fail(HKLegislationReleaseErrorCode.PRIOR_RELEASE_INVALID)
    records, proposed_entries = _records_and_entries(candidate_set, identities, prior.release_id)
    projected = _freeze(candidate_set, identities, request, records)
    if (
        projected != prior
        or records != tuple(entry.record for entry in prior.records)
        or proposed_entries != request.prior_traceability_entries
        or candidate_set.outcomes != request.prior_inventory_outcomes
    ):
        _fail(HKLegislationReleaseErrorCode.PRIOR_RELEASE_INVALID)
    return _issue_scope_result(
        HKLegislationScopeReleaseResult(
            candidate_set.legislation_scope_code,
            prior,
            proposed_entries,
            candidate_set.outcomes,
            request.serving_profile,
            reused_prior_release=True,
            selected_drafts=candidate_set.drafts,
            allocated_identities=identities,
        )
    )


def build_hk_legislation_scope_release(
    request: HKLegislationScopeReleaseRequest,
) -> HKLegislationScopeReleaseResult:
    """Map one sealed candidate set without external access or identity issuance."""
    try:
        if (
            type(request) is not HKLegislationScopeReleaseRequest
            or type(request.candidate_set) is not HKLegislationCandidateSet
            or type(request.serving_profile) is not ServingRecordProfile
            or type(request.release_evidence_refs) is not tuple
            or type(request.release_validation_refs) is not tuple
            or not request.release_evidence_refs
            or not request.release_validation_refs
        ):
            _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
        candidate_set = replay_hk_legislation_candidate_set(request.candidate_set)
        identities = request.allocated_identities
        if any(
            draft.serving_profile_id != request.serving_profile.serving_record_profile_id
            for draft in candidate_set.drafts
        ):
            _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
        if request.prior_release is not None and not request.unchanged:
            _fail(HKLegislationReleaseErrorCode.PRIOR_RELEASE_INVALID)
        if request.unchanged:
            return _unchanged_result(request, candidate_set, identities)
        records, preliminary_entries = _records_and_entries(candidate_set, identities, "")
        release = _freeze(candidate_set, identities, request, records)
        entries = tuple(
            _entry(draft, record, identities.corpus_scope_id, release.release_id)
            for draft, record in zip(candidate_set.drafts, records, strict=True)
        )
        if preliminary_entries and not entries:
            _fail(HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID)
        return _issue_scope_result(
            HKLegislationScopeReleaseResult(
                candidate_set.legislation_scope_code,
                release,
                entries,
                candidate_set.outcomes,
                request.serving_profile,
                reused_prior_release=False,
                selected_drafts=candidate_set.drafts,
                allocated_identities=identities,
            )
        )
    except HKLegislationReleaseError:
        raise
    except Exception as error:
        raise HKLegislationReleaseError(
            HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID
        ) from error


def freeze_hk_legislation_release_set(
    request: HKLegislationReleaseSetRequest,
) -> HKLegislationReleaseSet:
    """Freeze the fixed V1 three-scope desired state and traceability lookup."""
    try:
        if (
            type(request) is not HKLegislationReleaseSetRequest
            or type(request.scope_results) is not tuple
        ):
            _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
        if _UTC.fullmatch(request.observation_cutoff) is None:
            _fail(HKLegislationReleaseErrorCode.RELEASE_SET_CUTOFF_MISMATCH)
        replayed_results = tuple(_replay_scope_result(result) for result in request.scope_results)
        if (
            len(replayed_results) != len(_V1_SCOPE_CODES)
            or any(
                type(result) is not HKLegislationScopeReleaseResult for result in replayed_results
            )
            or tuple(result.legislation_scope_code for result in replayed_results)
            != _V1_SCOPE_CODES
        ):
            _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
        if any(
            result.release.observation_cutoff != request.observation_cutoff
            for result in replayed_results
        ):
            _fail(HKLegislationReleaseErrorCode.RELEASE_SET_CUTOFF_MISMATCH)
        profiles: dict[str, ServingRecordProfile] = {}
        for result in replayed_results:
            profile = result.serving_profile
            if (
                type(profile) is not ServingRecordProfile
                or type(profile.serving_record_profile_id) is not str
                or _PROFILE.fullmatch(profile.serving_record_profile_id) is None
                or any(
                    entry.serving_record_profile_id != profile.serving_record_profile_id
                    for entry in result.traceability_entries
                )
            ):
                _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
            existing = profiles.get(profile.serving_record_profile_id)
            if existing is not None and existing != profile:
                _fail(HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE)
            profiles[profile.serving_record_profile_id] = profile
        releases = tuple(result.release for result in replayed_results)
        desired = compose_desired_state(
            tuple(release.scope_id for release in releases),
            releases,
            target_key=request.target_key,
            observation_cutoff=request.observation_cutoff,
        )
        entries = tuple(
            entry for result in replayed_results for entry in result.traceability_entries
        )
        used_profile_ids = {entry.serving_record_profile_id for entry in entries}
        lookup = freeze_record_traceability_lookup(
            request.lookup_input,
            desired,
            entries,
            tuple(
                profile
                for profile_id, profile in profiles.items()
                if profile_id in used_profile_ids
            ),
            request.lookup_shards,
        )
        return _issue_release_set(HKLegislationReleaseSet(replayed_results, desired, lookup))
    except HKLegislationReleaseError:
        raise
    except Exception as error:
        raise HKLegislationReleaseError(
            HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE
        ) from error
