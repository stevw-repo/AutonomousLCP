"""Source-neutral Hong Kong legislation candidate records and accounting."""

from __future__ import annotations

import re
import weakref
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Never, TypeIs

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_legislation_events import HKLegislationDisposition, HKLegislationEventDecision
from .hk_legislation_partition import (
    BilingualPartitionResult,
    BilingualServingPart,
    PartitionDisposition,
    PartitionMeasurement,
    PartitionReason,
)

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_ISSUED = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")
_LEGAL_ITEM = re.compile(r"^lit_[0-9a-f]{48}$")
_OFFICIAL_VERSION = re.compile(r"^ofv_[0-9a-f]{48}$")
_LEGAL_LOCATION = re.compile(r"^loc_[0-9a-f]{48}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_SCOPE = re.compile(r"^HK-LEG-(?:ORDINANCES|SUBSIDIARY|CONSTITUTIONAL-AND-OTHER-INSTRUMENTS)$")
_BINDING_AUTHORITY_MISSING = "BINDING_AUTHORITY_MISSING"
_RETAINED_REF_SIZE = 3
_RETAINED_DRAFT_SIZE = 24
_RETAINED_OUTCOME_SIZE = 6


class HKLegislationRecordErrorCode(StrEnum):
    """Closed source-neutral candidate construction failures."""

    DECISION_INVALID = "HK_LEGISLATION_RECORD_DECISION_INVALID"
    INVENTORY_ACCOUNTING_INVALID = "HK_LEGISLATION_RECORD_INVENTORY_ACCOUNTING_INVALID"
    BILINGUAL_PARTITION_REQUIRED = "HK_LEGISLATION_RECORD_BILINGUAL_PARTITION_REQUIRED"
    PARTITION_NOT_SERVABLE = "HK_LEGISLATION_RECORD_PARTITION_NOT_SERVABLE"
    TRACEABILITY_SEED_INVALID = "HK_LEGISLATION_RECORD_TRACEABILITY_SEED_INVALID"
    CANDIDATE_ISSUANCE_INVALID = "HK_LEGISLATION_RECORD_CANDIDATE_ISSUANCE_INVALID"


class HKLegislationRecordError(ValueError):
    """One exact candidate/accounting rejection."""

    def __init__(self, code: HKLegislationRecordErrorCode) -> None:
        """Create one stable closed candidate/accounting error."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HKLegislationTraceabilityReference:
    """Desk-owned primitive reference; it is not a corpus dependency."""

    ref_type: str
    ref_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKLegislationAuthorityNoteSeed:
    """Desk-owned proof for the six-field authority note."""

    rendered_value_fingerprint: str
    decision_ref: HKLegislationTraceabilityReference
    supporting_evidence_refs: tuple[HKLegislationTraceabilityReference, ...]


@dataclass(frozen=True, slots=True)
class HKLegislationServingPayload:
    """The non-identity five fixed serving fields plus per-part text."""

    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKLegislationInventoryDecisionAuthority:
    """Desk-issued proof binding one inventory identity to one legal decision."""

    inventory_item_id: str
    legislation_scope_code: str
    legal_item_id: str
    official_version_ids: tuple[str, ...]
    legal_location_ids: tuple[str, ...]
    decision_fingerprint: str
    evidence_refs: tuple[HKLegislationTraceabilityReference, ...]
    binding_fingerprint: str = dataclass_field(init=False, default="", repr=False)

    def assert_desk_issued(self) -> None:
        """Reject caller-constructed or mutated authority."""
        snapshot = _authority_fingerprint(self)
        issued = _DECISION_AUTHORITY_ISSUANCE.get(id(self))
        if (
            issued is None
            or issued.reference() is not self
            or issued.fingerprint != snapshot
            or self.binding_fingerprint != snapshot
        ):
            _fail(HKLegislationRecordErrorCode.DECISION_INVALID)


@dataclass(frozen=True, slots=True)
class _IssuedDecisionAuthority:
    reference: weakref.ReferenceType[object]
    fingerprint: str


_DECISION_AUTHORITY_ISSUANCE: dict[int, _IssuedDecisionAuthority] = {}


@dataclass(frozen=True, slots=True)
class HKLegislationCandidateInput:
    """One already-decided source-neutral inventory member."""

    inventory_item_id: str
    legislation_scope_code: str
    legal_item_id: str
    official_version_ids: tuple[str, ...]
    legal_location_ids: tuple[str, ...]
    event_decision: HKLegislationEventDecision
    partition_result: BilingualPartitionResult | None
    serving_payload: HKLegislationServingPayload
    artifact_ref: str
    evidence_refs: tuple[HKLegislationTraceabilityReference, ...]
    authority_note_evidence: HKLegislationAuthorityNoteSeed
    decision_authority: HKLegislationInventoryDecisionAuthority | None = None


@dataclass(frozen=True, slots=True)
class HKLegislationRecordDraft:
    """One immutable draft. ``candidate_key`` is intentionally not a ``rec_`` ID."""

    candidate_key: str
    inventory_item_id: str
    legislation_scope_code: str
    text: str
    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str
    artifact_ref: str
    evidence_refs: tuple[HKLegislationTraceabilityReference, ...]
    legal_item_id: str
    official_version_ids: tuple[str, ...]
    legal_location_ids: tuple[str, ...]
    authority_note_evidence: HKLegislationAuthorityNoteSeed
    serving_profile_id: str
    serving_payload_fingerprint: str
    partition_fingerprint: str
    partition_profile_fingerprint: str
    decision_fingerprint: str
    part_number: int
    total_parts: int


@dataclass(frozen=True, slots=True)
class HKLegislationInventoryOutcome:
    """One exact terminal accounting outcome for one input inventory member."""

    inventory_item_id: str
    legal_disposition: HKLegislationDisposition
    outcome_kind: Literal["EMITTED", "WAITING_ROOM", "EVIDENCE_ONLY", "HISTORICAL", "QUARANTINE"]
    reason_code: str
    draft_keys: tuple[str, ...]
    supporting_refs: tuple[HKLegislationTraceabilityReference, ...]


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKLegislationCandidateSet:
    """Complete source-neutral accounting for exactly one legislation scope."""

    legislation_scope_code: str
    observation_cutoff: str
    drafts: tuple[HKLegislationRecordDraft, ...]
    outcomes: tuple[HKLegislationInventoryOutcome, ...]
    issuance_fingerprint: str = dataclass_field(init=False, default="", repr=False)

    def assert_desk_issued(self) -> None:
        """Require an exact current projection produced by this Desk factory."""
        _issued_candidate_set_snapshot(self)


@dataclass(frozen=True, slots=True)
class _IssuedCandidateSet:
    reference: weakref.ReferenceType[object]
    snapshot: str
    detached: HKLegislationCandidateSet


_CANDIDATE_SET_ISSUANCE: dict[int, _IssuedCandidateSet] = {}


def _fail(code: HKLegislationRecordErrorCode) -> Never:
    raise HKLegislationRecordError(code)


def _fingerprint(value: object) -> str:
    return "sha256:" + sha256(canonicalize(checked_json_value(value))).hexdigest()


def _authority_fingerprint(value: HKLegislationInventoryDecisionAuthority) -> str:
    try:
        return _fingerprint(
            {
                "decision_fingerprint": value.decision_fingerprint,
                "evidence_refs": [
                    [item.ref_type, item.ref_id, item.fingerprint] for item in value.evidence_refs
                ],
                "inventory_item_id": value.inventory_item_id,
                "legal_item_id": value.legal_item_id,
                "legal_location_ids": list(value.legal_location_ids),
                "legislation_scope_code": value.legislation_scope_code,
                "official_version_ids": list(value.official_version_ids),
            }
        )
    except AttributeError, TypeError, UnicodeError, ValueError:
        _fail(HKLegislationRecordErrorCode.DECISION_INVALID)


def bind_hk_legislation_inventory_decision_authority(
    value: HKLegislationCandidateInput,
) -> HKLegislationInventoryDecisionAuthority:
    """Issue authority only after replaying exact identity, decision, and evidence facts."""
    snapshot = _validate_snapshot(_snapshot_complete_input(value), value.legislation_scope_code)
    decision = snapshot.event_decision
    seed = snapshot.authority_note_evidence
    if (
        snapshot.decision_authority is not None
        or seed.decision_ref.ref_type != "DECISION"
        or seed.decision_ref.fingerprint != decision.decision_fingerprint
    ):
        _fail(HKLegislationRecordErrorCode.DECISION_INVALID)
    result = HKLegislationInventoryDecisionAuthority(
        snapshot.inventory_item_id,
        snapshot.legislation_scope_code,
        snapshot.legal_item_id,
        snapshot.official_version_ids,
        snapshot.legal_location_ids,
        decision.decision_fingerprint,
        snapshot.evidence_refs,
    )
    fingerprint = _authority_fingerprint(result)
    object.__setattr__(result, "binding_fingerprint", fingerprint)
    _DECISION_AUTHORITY_ISSUANCE[id(result)] = _IssuedDecisionAuthority(
        weakref.ref(result), fingerprint
    )
    return result


def _exact_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _copy_ref(value: object) -> HKLegislationTraceabilityReference:
    if type(value) is not HKLegislationTraceabilityReference:
        _fail(HKLegislationRecordErrorCode.TRACEABILITY_SEED_INVALID)
    return HKLegislationTraceabilityReference(value.ref_type, value.ref_id, value.fingerprint)


def _valid_ref(value: object) -> HKLegislationTraceabilityReference:
    copied = _copy_ref(value)
    if (
        type(copied.ref_type) is not str
        or not copied.ref_type
        or _ISSUED.fullmatch(copied.ref_id) is None
        or _FINGERPRINT.fullmatch(copied.fingerprint) is None
    ):
        _fail(HKLegislationRecordErrorCode.TRACEABILITY_SEED_INVALID)
    return copied


def _copy_seed(value: object) -> HKLegislationAuthorityNoteSeed:
    if (
        type(value) is not HKLegislationAuthorityNoteSeed
        or type(value.supporting_evidence_refs) is not tuple
    ):
        _fail(HKLegislationRecordErrorCode.TRACEABILITY_SEED_INVALID)
    return HKLegislationAuthorityNoteSeed(
        value.rendered_value_fingerprint,
        _copy_ref(value.decision_ref),
        tuple(_copy_ref(item) for item in value.supporting_evidence_refs),
    )


def _seed(value: object, note: str) -> HKLegislationAuthorityNoteSeed:
    copied = _copy_seed(value)
    if _FINGERPRINT.fullmatch(copied.rendered_value_fingerprint) is None:
        _fail(HKLegislationRecordErrorCode.TRACEABILITY_SEED_INVALID)
    decision = _valid_ref(copied.decision_ref)
    evidence = tuple(_valid_ref(item) for item in copied.supporting_evidence_refs)
    if evidence != tuple(
        sorted(set(evidence), key=lambda item: (item.ref_type, item.ref_id, item.fingerprint))
    ):
        _fail(HKLegislationRecordErrorCode.TRACEABILITY_SEED_INVALID)
    if copied.rendered_value_fingerprint != "sha256:" + sha256(note.encode()).hexdigest() or (
        note == "None"
    ) != (not evidence):
        _fail(HKLegislationRecordErrorCode.TRACEABILITY_SEED_INVALID)
    return HKLegislationAuthorityNoteSeed(copied.rendered_value_fingerprint, decision, evidence)


def _copy_partition(value: BilingualPartitionResult | None) -> BilingualPartitionResult | None:
    if value is None:
        return None
    if type(value) is not BilingualPartitionResult or type(value.parts) is not tuple:
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    parts: list[BilingualServingPart] = []
    for part in value.parts:
        if (
            type(part) is not BilingualServingPart
            or type(part.measurement) is not PartitionMeasurement
        ):
            _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
        tuples = (
            part.primary_partition_node_ids,
            part.primary_alignment_group_ids,
            part.dependency_alignment_group_ids,
            part.en_primary_source_unit_ids,
            part.zh_hant_primary_source_unit_ids,
            part.en_dependency_source_unit_ids,
            part.zh_hant_dependency_source_unit_ids,
        )
        if any(type(field) is not tuple for field in tuples):
            _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
        parts.append(
            BilingualServingPart(
                part.part_number,
                part.total_parts,
                tuple(part.primary_partition_node_ids),
                tuple(part.primary_alignment_group_ids),
                tuple(part.dependency_alignment_group_ids),
                tuple(part.en_primary_source_unit_ids),
                tuple(part.zh_hant_primary_source_unit_ids),
                tuple(part.en_dependency_source_unit_ids),
                tuple(part.zh_hant_dependency_source_unit_ids),
                part.text,
                part.text_fingerprint,
                part.serving_payload_fingerprint,
                PartitionMeasurement(
                    part.measurement.text_tokens,
                    part.measurement.metadata_bytes,
                    part.measurement.text_limit,
                    part.measurement.metadata_limit,
                ),
            )
        )
    if (
        type(value.quarantined_partition_node_ids) is not tuple
        or type(value.canonical_bytes) is not bytes
    ):
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    return BilingualPartitionResult(
        value.disposition,
        value.reason,
        tuple(parts),
        tuple(value.quarantined_partition_node_ids),
        value.coverage_gap_required,
        value.profile_id,
        value.profile_fingerprint,
        value.en_tree_fingerprint,
        value.zh_hant_tree_fingerprint,
        value.alignment_map_fingerprint,
        bytes(value.canonical_bytes),
        value.fingerprint,
    )


def _snapshot_complete_input(value: object) -> HKLegislationCandidateInput:
    """Copy every primitive/container before a Task 3 or partition validation call."""
    if (
        type(value) is not HKLegislationCandidateInput
        or type(value.official_version_ids) is not tuple
        or type(value.legal_location_ids) is not tuple
        or type(value.serving_payload) is not HKLegislationServingPayload
        or type(value.evidence_refs) is not tuple
        or (
            value.decision_authority is not None
            and type(value.decision_authority) is not HKLegislationInventoryDecisionAuthority
        )
    ):
        _fail(HKLegislationRecordErrorCode.INVENTORY_ACCOUNTING_INVALID)
    payload = HKLegislationServingPayload(
        value.serving_payload.country,
        value.serving_payload.jurisdiction,
        value.serving_payload.material_type,
        value.serving_payload.source,
        value.serving_payload.authority_note,
    )
    return HKLegislationCandidateInput(
        value.inventory_item_id,
        value.legislation_scope_code,
        value.legal_item_id,
        tuple(value.official_version_ids),
        tuple(value.legal_location_ids),
        value.event_decision,
        _copy_partition(value.partition_result),
        payload,
        value.artifact_ref,
        tuple(_copy_ref(item) for item in value.evidence_refs),
        _copy_seed(value.authority_note_evidence),
        value.decision_authority,
    )


def _validate_snapshot(
    value: HKLegislationCandidateInput, scope: str
) -> HKLegislationCandidateInput:
    if (
        type(value.inventory_item_id) is not str
        or not value.inventory_item_id
        or type(value.legislation_scope_code) is not str
        or type(value.legal_item_id) is not str
        or value.legislation_scope_code != scope
        or _LEGAL_ITEM.fullmatch(value.legal_item_id) is None
        or value.official_version_ids != tuple(sorted(set(value.official_version_ids)))
        or not value.official_version_ids
        or value.legal_location_ids != tuple(sorted(set(value.legal_location_ids)))
        or not value.legal_location_ids
        or any(
            type(item) is not str or _OFFICIAL_VERSION.fullmatch(item) is None
            for item in value.official_version_ids
        )
        or any(
            type(item) is not str or _LEGAL_LOCATION.fullmatch(item) is None
            for item in value.legal_location_ids
        )
        or type(value.artifact_ref) is not str
        or _ISSUED.fullmatch(value.artifact_ref) is None
        or any(
            type(getattr(value.serving_payload, field)) is not str
            or not getattr(value.serving_payload, field)
            for field in ("country", "jurisdiction", "material_type", "source", "authority_note")
        )
    ):
        _fail(HKLegislationRecordErrorCode.INVENTORY_ACCOUNTING_INVALID)
    if type(value.event_decision) is not HKLegislationEventDecision:
        _fail(HKLegislationRecordErrorCode.DECISION_INVALID)
    try:
        value.event_decision.assert_factory_issued()
    except Exception as error:
        raise HKLegislationRecordError(HKLegislationRecordErrorCode.DECISION_INVALID) from error
    decision = value.event_decision
    if (
        decision.legal_location_id not in value.legal_location_ids
        or decision.official_version_id not in value.official_version_ids
    ):
        _fail(HKLegislationRecordErrorCode.DECISION_INVALID)
    refs = tuple(_valid_ref(item) for item in value.evidence_refs)
    if not refs or refs != tuple(
        sorted(set(refs), key=lambda item: (item.ref_type, item.ref_id, item.fingerprint))
    ):
        _fail(HKLegislationRecordErrorCode.TRACEABILITY_SEED_INVALID)
    return HKLegislationCandidateInput(
        value.inventory_item_id,
        scope,
        value.legal_item_id,
        value.official_version_ids,
        value.legal_location_ids,
        decision,
        value.partition_result,
        value.serving_payload,
        value.artifact_ref,
        refs,
        _seed(value.authority_note_evidence, value.serving_payload.authority_note),
        value.decision_authority,
    )


def validate_hk_legislation_partition_for_record_candidate(
    value: HKLegislationCandidateInput,
) -> BilingualPartitionResult:
    """Semantically replay a supplied partition before any future record emission."""
    if (
        type(value) is not HKLegislationCandidateInput
        or type(value.serving_payload) is not HKLegislationServingPayload
        or any(
            type(getattr(value.serving_payload, field)) is not str
            for field in ("authority_note", "country", "jurisdiction", "material_type", "source")
        )
        or any(
            not getattr(value.serving_payload, field)
            or getattr(value.serving_payload, field).strip()
            != getattr(value.serving_payload, field)
            for field in ("authority_note", "country", "jurisdiction", "material_type", "source")
        )
    ):
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    partition = value.partition_result
    if type(partition) is not BilingualPartitionResult:
        _fail(HKLegislationRecordErrorCode.BILINGUAL_PARTITION_REQUIRED)
    if (
        type(partition.disposition) is not PartitionDisposition
        or type(partition.reason) is not PartitionReason
        or type(partition.parts) is not tuple
        or type(partition.quarantined_partition_node_ids) is not tuple
        or type(partition.coverage_gap_required) is not bool
        or type(partition.profile_id) is not str
        or type(partition.profile_fingerprint) is not str
        or type(partition.en_tree_fingerprint) is not str
        or type(partition.zh_hant_tree_fingerprint) is not str
        or type(partition.alignment_map_fingerprint) is not str
        or type(partition.canonical_bytes) is not bytes
        or type(partition.fingerprint) is not str
        or any(type(node_id) is not str for node_id in partition.quarantined_partition_node_ids)
        or any(
            _FINGERPRINT.fullmatch(fingerprint) is None
            for fingerprint in (
                partition.profile_fingerprint,
                partition.en_tree_fingerprint,
                partition.zh_hant_tree_fingerprint,
                partition.alignment_map_fingerprint,
                partition.fingerprint,
            )
        )
    ):
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    if partition.disposition is not PartitionDisposition.PASS:
        return partition
    if not partition.parts:
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    try:
        _seed(value.authority_note_evidence, value.serving_payload.authority_note)
    except HKLegislationRecordError, UnicodeError, ValueError, TypeError:
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    for number, part in enumerate(partition.parts, start=1):
        _validate_part_for_record_candidate(value, part, number, len(partition.parts))
    try:
        expected = canonicalize(checked_json_value(partition.document()))
    except UnicodeError, ValueError, TypeError:
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    if (
        partition.canonical_bytes != expected
        or partition.fingerprint != "sha256:" + sha256(expected).hexdigest()
        or _ISSUED.fullmatch(partition.profile_id) is None
    ):
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    return partition


def _validate_part_for_record_candidate(
    value: HKLegislationCandidateInput,
    part: BilingualServingPart,
    number: int,
    total_parts: int,
) -> None:
    if (
        type(part) is not BilingualServingPart
        or type(part.part_number) is not int
        or type(part.total_parts) is not int
        or type(part.text) is not str
        or type(part.text_fingerprint) is not str
        or type(part.serving_payload_fingerprint) is not str
        or type(part.measurement) is not PartitionMeasurement
        or any(
            type(measurement) is not int
            for measurement in (
                part.measurement.text_tokens,
                part.measurement.metadata_bytes,
                part.measurement.text_limit,
                part.measurement.metadata_limit,
            )
        )
    ):
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    if not part.text or part.text.strip() != part.text:
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    try:
        serving_payload_bytes = canonicalize(
            checked_json_value(
                {
                    "authority_note": value.serving_payload.authority_note,
                    "country": value.serving_payload.country,
                    "jurisdiction": value.serving_payload.jurisdiction,
                    "source": value.serving_payload.source,
                    "text": part.text,
                    "type": value.serving_payload.material_type,
                }
            )
        )
    except UnicodeError, ValueError, TypeError:
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)
    if (
        part.part_number != number
        or part.total_parts != total_parts
        or not part.en_primary_source_unit_ids
        or not part.zh_hant_primary_source_unit_ids
        or any(
            type(container) is not tuple
            for container in (
                part.primary_partition_node_ids,
                part.primary_alignment_group_ids,
                part.dependency_alignment_group_ids,
                part.en_primary_source_unit_ids,
                part.zh_hant_primary_source_unit_ids,
                part.en_dependency_source_unit_ids,
                part.zh_hant_dependency_source_unit_ids,
            )
        )
        or any(
            type(item) is not str
            for item in (
                *part.primary_partition_node_ids,
                *part.primary_alignment_group_ids,
                *part.dependency_alignment_group_ids,
                *part.en_primary_source_unit_ids,
                *part.zh_hant_primary_source_unit_ids,
                *part.en_dependency_source_unit_ids,
                *part.zh_hant_dependency_source_unit_ids,
            )
        )
        or not part.measurement.fits
        or part.measurement.text_tokens < 0
        or part.measurement.metadata_bytes < 0
        or part.measurement.text_limit <= 0
        or part.measurement.metadata_limit <= 0
        or part.measurement.metadata_bytes != len(serving_payload_bytes)
        or part.text_fingerprint != "sha256:" + sha256(part.text.encode()).hexdigest()
        or _FINGERPRINT.fullmatch(part.serving_payload_fingerprint) is None
        or part.serving_payload_fingerprint != "sha256:" + sha256(serving_payload_bytes).hexdigest()
    ):
        _fail(HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE)


def _outcome_for(
    item: HKLegislationCandidateInput,
) -> tuple[tuple[HKLegislationRecordDraft, ...], HKLegislationInventoryOutcome]:
    decision = item.event_decision
    if decision.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT:
        authority = item.decision_authority
        if authority is None:
            return (), HKLegislationInventoryOutcome(
                item.inventory_item_id,
                HKLegislationDisposition.QUARANTINE,
                "QUARANTINE",
                _BINDING_AUTHORITY_MISSING,
                (),
                item.evidence_refs,
            )
        _validate_inventory_decision_authority(item, authority)
        partition = validate_hk_legislation_partition_for_record_candidate(item)
        if partition.disposition is not PartitionDisposition.PASS:
            return (), HKLegislationInventoryOutcome(
                item.inventory_item_id,
                HKLegislationDisposition.QUARANTINE,
                "QUARANTINE",
                partition.reason.value,
                (),
                item.evidence_refs,
            )
        drafts = tuple(_draft_for_part(item, partition, part) for part in partition.parts)
        return drafts, HKLegislationInventoryOutcome(
            item.inventory_item_id,
            HKLegislationDisposition.SEARCHABLE_CURRENT,
            "EMITTED",
            decision.reason_code,
            tuple(draft.candidate_key for draft in drafts),
            item.evidence_refs,
        )
    if item.partition_result is not None:
        _fail(HKLegislationRecordErrorCode.BILINGUAL_PARTITION_REQUIRED)
    disposition = decision.legal_disposition
    kinds: dict[
        HKLegislationDisposition,
        Literal["WAITING_ROOM", "EVIDENCE_ONLY", "HISTORICAL", "QUARANTINE"],
    ] = {
        HKLegislationDisposition.WAITING_ROOM: "WAITING_ROOM",
        HKLegislationDisposition.EVIDENCE_ONLY: "EVIDENCE_ONLY",
        HKLegislationDisposition.HISTORICAL: "HISTORICAL",
        HKLegislationDisposition.QUARANTINE: "QUARANTINE",
    }
    if disposition is None or disposition not in kinds:
        _fail(HKLegislationRecordErrorCode.DECISION_INVALID)
    return (), HKLegislationInventoryOutcome(
        item.inventory_item_id,
        disposition,
        kinds[disposition],
        item.event_decision.reason_code,
        (),
        item.evidence_refs,
    )


def _validate_inventory_decision_authority(
    item: HKLegislationCandidateInput,
    authority: HKLegislationInventoryDecisionAuthority,
) -> None:
    if type(authority) is not HKLegislationInventoryDecisionAuthority:
        _fail(HKLegislationRecordErrorCode.DECISION_INVALID)
    authority.assert_desk_issued()
    if (
        authority.inventory_item_id != item.inventory_item_id
        or authority.legislation_scope_code != item.legislation_scope_code
        or authority.legal_item_id != item.legal_item_id
        or authority.official_version_ids != item.official_version_ids
        or authority.legal_location_ids != item.legal_location_ids
        or authority.decision_fingerprint != item.event_decision.decision_fingerprint
        or authority.evidence_refs != item.evidence_refs
    ):
        _fail(HKLegislationRecordErrorCode.DECISION_INVALID)


def _draft_for_part(
    item: HKLegislationCandidateInput,
    partition: BilingualPartitionResult,
    part: BilingualServingPart,
) -> HKLegislationRecordDraft:
    key = (
        "candidate_"
        + sha256(
            chr(31)
            .join(
                (
                    item.inventory_item_id,
                    item.event_decision.decision_fingerprint,
                    partition.fingerprint,
                    str(part.part_number),
                    str(part.total_parts),
                )
            )
            .encode()
        ).hexdigest()[:48]
    )
    return HKLegislationRecordDraft(
        key,
        item.inventory_item_id,
        item.legislation_scope_code,
        part.text,
        item.serving_payload.country,
        item.serving_payload.jurisdiction,
        item.serving_payload.material_type,
        item.serving_payload.source,
        item.serving_payload.authority_note,
        item.artifact_ref,
        item.evidence_refs,
        item.legal_item_id,
        item.official_version_ids,
        item.legal_location_ids,
        item.authority_note_evidence,
        partition.profile_id,
        part.serving_payload_fingerprint,
        partition.fingerprint,
        partition.profile_fingerprint,
        item.event_decision.decision_fingerprint,
        part.part_number,
        part.total_parts,
    )


def _candidate_set_fingerprint(value: HKLegislationCandidateSet) -> str:
    document = {
        "scope": value.legislation_scope_code,
        "cutoff": value.observation_cutoff,
        "drafts": [
            [
                draft.candidate_key,
                draft.inventory_item_id,
                draft.legislation_scope_code,
                draft.text,
                draft.country,
                draft.jurisdiction,
                draft.material_type,
                draft.source,
                draft.authority_note,
                draft.artifact_ref,
                [[ref.ref_type, ref.ref_id, ref.fingerprint] for ref in draft.evidence_refs],
                draft.legal_item_id,
                list(draft.official_version_ids),
                list(draft.legal_location_ids),
                draft.authority_note_evidence.rendered_value_fingerprint,
                [
                    draft.authority_note_evidence.decision_ref.ref_type,
                    draft.authority_note_evidence.decision_ref.ref_id,
                    draft.authority_note_evidence.decision_ref.fingerprint,
                ],
                [
                    [ref.ref_type, ref.ref_id, ref.fingerprint]
                    for ref in draft.authority_note_evidence.supporting_evidence_refs
                ],
                draft.serving_profile_id,
                draft.serving_payload_fingerprint,
                draft.partition_fingerprint,
                draft.partition_profile_fingerprint,
                draft.decision_fingerprint,
                draft.part_number,
                draft.total_parts,
            ]
            for draft in value.drafts
        ],
        "outcomes": [
            [
                outcome.inventory_item_id,
                outcome.legal_disposition.value,
                outcome.outcome_kind,
                outcome.reason_code,
                list(outcome.draft_keys),
                [[ref.ref_type, ref.ref_id, ref.fingerprint] for ref in outcome.supporting_refs],
            ]
            for outcome in value.outcomes
        ],
    }
    try:
        return _fingerprint(document)
    except UnicodeError, ValueError, TypeError:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)


def _capture_issuance_ref(value: object) -> HKLegislationTraceabilityReference:
    if (
        type(value) is not HKLegislationTraceabilityReference
        or type(value.ref_type) is not str
        or type(value.ref_id) is not str
        or type(value.fingerprint) is not str
    ):
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return HKLegislationTraceabilityReference(value.ref_type, value.ref_id, value.fingerprint)


def _capture_issuance_seed(value: object) -> HKLegislationAuthorityNoteSeed:
    if (
        type(value) is not HKLegislationAuthorityNoteSeed
        or type(value.rendered_value_fingerprint) is not str
        or type(value.supporting_evidence_refs) is not tuple
    ):
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return HKLegislationAuthorityNoteSeed(
        value.rendered_value_fingerprint,
        _capture_issuance_ref(value.decision_ref),
        tuple(_capture_issuance_ref(item) for item in value.supporting_evidence_refs),
    )


def _capture_issuance_draft(value: object) -> HKLegislationRecordDraft:
    if (
        type(value) is not HKLegislationRecordDraft
        or type(value.evidence_refs) is not tuple
        or type(value.official_version_ids) is not tuple
        or type(value.legal_location_ids) is not tuple
        or any(
            type(item) is not str
            for item in (
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
                value.legal_item_id,
                value.serving_profile_id,
                value.serving_payload_fingerprint,
                value.partition_fingerprint,
                value.partition_profile_fingerprint,
                value.decision_fingerprint,
                *value.official_version_ids,
                *value.legal_location_ids,
            )
        )
        or any(type(item) is not int for item in (value.part_number, value.total_parts))
    ):
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    captured = HKLegislationRecordDraft(
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
        tuple(_capture_issuance_ref(item) for item in value.evidence_refs),
        value.legal_item_id,
        tuple(value.official_version_ids),
        tuple(value.legal_location_ids),
        _capture_issuance_seed(value.authority_note_evidence),
        value.serving_profile_id,
        value.serving_payload_fingerprint,
        value.partition_fingerprint,
        value.partition_profile_fingerprint,
        value.decision_fingerprint,
        value.part_number,
        value.total_parts,
    )
    return _detach_draft(captured)


def _capture_issuance_outcome(value: object) -> HKLegislationInventoryOutcome:
    if (
        type(value) is not HKLegislationInventoryOutcome
        or type(value.legal_disposition) is not HKLegislationDisposition
        or type(value.outcome_kind) is not str
        or type(value.reason_code) is not str
        or type(value.inventory_item_id) is not str
        or type(value.draft_keys) is not tuple
        or type(value.supporting_refs) is not tuple
        or any(type(item) is not str for item in value.draft_keys)
    ):
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    captured = HKLegislationInventoryOutcome(
        value.inventory_item_id,
        value.legal_disposition,
        value.outcome_kind,
        value.reason_code,
        tuple(value.draft_keys),
        tuple(_capture_issuance_ref(item) for item in value.supporting_refs),
    )
    return _detach_outcome(captured)


def _capture_candidate_set(value: object) -> HKLegislationCandidateSet:
    if (
        type(value) is not HKLegislationCandidateSet
        or type(value.legislation_scope_code) is not str
        or type(value.observation_cutoff) is not str
        or type(value.drafts) is not tuple
        or type(value.outcomes) is not tuple
    ):
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return HKLegislationCandidateSet(
        value.legislation_scope_code,
        value.observation_cutoff,
        tuple(_capture_issuance_draft(item) for item in value.drafts),
        tuple(_capture_issuance_outcome(item) for item in value.outcomes),
    )


def _detach_draft(value: HKLegislationRecordDraft) -> HKLegislationRecordDraft:
    if type(value) is not HKLegislationRecordDraft:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    seed = _seed(value.authority_note_evidence, value.authority_note)
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
        tuple(_valid_ref(reference) for reference in value.evidence_refs),
        value.legal_item_id,
        tuple(value.official_version_ids),
        tuple(value.legal_location_ids),
        seed,
        value.serving_profile_id,
        value.serving_payload_fingerprint,
        value.partition_fingerprint,
        value.partition_profile_fingerprint,
        value.decision_fingerprint,
        value.part_number,
        value.total_parts,
    )


def _detach_outcome(value: HKLegislationInventoryOutcome) -> HKLegislationInventoryOutcome:
    if type(value) is not HKLegislationInventoryOutcome:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return HKLegislationInventoryOutcome(
        value.inventory_item_id,
        value.legal_disposition,
        value.outcome_kind,
        value.reason_code,
        tuple(value.draft_keys),
        tuple(_valid_ref(reference) for reference in value.supporting_refs),
    )


def _issue_candidate_set(
    scope: str,
    cutoff: str,
    drafts: tuple[HKLegislationRecordDraft, ...],
    outcomes: tuple[HKLegislationInventoryOutcome, ...],
) -> HKLegislationCandidateSet:
    detached = _capture_candidate_set(HKLegislationCandidateSet(scope, cutoff, drafts, outcomes))
    result = _capture_candidate_set(detached)
    snapshot = _candidate_set_fingerprint(detached)
    object.__setattr__(result, "issuance_fingerprint", snapshot)
    _CANDIDATE_SET_ISSUANCE[id(result)] = _IssuedCandidateSet(
        weakref.ref(result), snapshot, detached
    )
    return result


def _issued_candidate_set_snapshot(value: object) -> HKLegislationCandidateSet:
    if type(value) is not HKLegislationCandidateSet:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    issued = _CANDIDATE_SET_ISSUANCE.get(id(value))
    if issued is None or issued.reference() is not value:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    if type(value.issuance_fingerprint) is not str:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    issuance_fingerprint = value.issuance_fingerprint
    try:
        live = _capture_candidate_set(value)
    except HKLegislationRecordError:
        raise
    except UnicodeError, ValueError, TypeError:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    if (
        issuance_fingerprint != issued.snapshot
        or _candidate_set_fingerprint(live) != issued.snapshot
        or live != issued.detached
    ):
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return issued.detached


def replay_hk_legislation_candidate_set(value: object) -> HKLegislationCandidateSet:
    """Verify and detach a complete Desk issuance for an application boundary."""
    snapshot = _issued_candidate_set_snapshot(value)
    return _issue_candidate_set(
        snapshot.legislation_scope_code,
        snapshot.observation_cutoff,
        snapshot.drafts,
        snapshot.outcomes,
    )


def canonical_hk_legislation_candidate_set(value: HKLegislationCandidateSet) -> bytes:
    """Serialize one issued candidate snapshot for restart-safe retained replay."""
    snapshot = _issued_candidate_set_snapshot(value)
    body = _candidate_set_document(snapshot)
    return canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-legislation-candidate-set/v1",
                **body,
                "issuance_fingerprint": _candidate_set_fingerprint(snapshot),
            }
        )
    )


def hk_legislation_candidate_set_from_bytes(content: bytes) -> HKLegislationCandidateSet:
    """Strictly decode, fingerprint-check, and freshly issue one retained snapshot."""
    try:
        value = parse_json_bytes(content, max_bytes=16_777_216)
        if (
            type(value) is not dict
            or frozenset(value)
            != frozenset(
                {
                    "schema_id",
                    "scope",
                    "cutoff",
                    "drafts",
                    "outcomes",
                    "issuance_fingerprint",
                }
            )
            or value.get("schema_id") != "asklegal.hk-legislation-candidate-set/v1"
            or canonicalize(value) != content
        ):
            _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
        scope = _retained_text(value.get("scope"))
        cutoff = _retained_text(value.get("cutoff"))
        drafts_value = value.get("drafts")
        outcomes_value = value.get("outcomes")
        if type(drafts_value) is not list or type(outcomes_value) is not list:
            _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
        candidate = HKLegislationCandidateSet(
            scope,
            cutoff,
            tuple(_retained_draft(item) for item in drafts_value),
            tuple(_retained_outcome(item) for item in outcomes_value),
        )
        if value.get("issuance_fingerprint") != _candidate_set_fingerprint(candidate):
            _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
        return _issue_candidate_set(scope, cutoff, candidate.drafts, candidate.outcomes)
    except HKLegislationRecordError:
        raise
    except (AttributeError, TypeError, UnicodeError, ValueError) as error:
        raise HKLegislationRecordError(
            HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID
        ) from error


def _candidate_set_document(value: HKLegislationCandidateSet) -> dict[str, JsonValue]:
    document = {
        "scope": value.legislation_scope_code,
        "cutoff": value.observation_cutoff,
        "drafts": [
            [
                draft.candidate_key,
                draft.inventory_item_id,
                draft.legislation_scope_code,
                draft.text,
                draft.country,
                draft.jurisdiction,
                draft.material_type,
                draft.source,
                draft.authority_note,
                draft.artifact_ref,
                [[ref.ref_type, ref.ref_id, ref.fingerprint] for ref in draft.evidence_refs],
                draft.legal_item_id,
                list(draft.official_version_ids),
                list(draft.legal_location_ids),
                draft.authority_note_evidence.rendered_value_fingerprint,
                [
                    draft.authority_note_evidence.decision_ref.ref_type,
                    draft.authority_note_evidence.decision_ref.ref_id,
                    draft.authority_note_evidence.decision_ref.fingerprint,
                ],
                [
                    [ref.ref_type, ref.ref_id, ref.fingerprint]
                    for ref in draft.authority_note_evidence.supporting_evidence_refs
                ],
                draft.serving_profile_id,
                draft.serving_payload_fingerprint,
                draft.partition_fingerprint,
                draft.partition_profile_fingerprint,
                draft.decision_fingerprint,
                draft.part_number,
                draft.total_parts,
            ]
            for draft in value.drafts
        ],
        "outcomes": [
            [
                outcome.inventory_item_id,
                outcome.legal_disposition.value,
                outcome.outcome_kind,
                outcome.reason_code,
                list(outcome.draft_keys),
                [[ref.ref_type, ref.ref_id, ref.fingerprint] for ref in outcome.supporting_refs],
            ]
            for outcome in value.outcomes
        ],
    }
    result = checked_json_value(document)
    if type(result) is not dict:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return result


def _retained_text(value: JsonValue | None) -> str:
    if type(value) is not str:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return value


def _retained_strings(value: JsonValue) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return tuple(item for item in value if type(item) is str)


def _retained_ref(value: JsonValue) -> HKLegislationTraceabilityReference:
    if type(value) is not list or len(value) != _RETAINED_REF_SIZE:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return HKLegislationTraceabilityReference(
        _retained_text(value[0]), _retained_text(value[1]), _retained_text(value[2])
    )


def _retained_refs(value: JsonValue) -> tuple[HKLegislationTraceabilityReference, ...]:
    if type(value) is not list:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return tuple(_retained_ref(item) for item in value)


def _retained_integer(value: JsonValue) -> int:
    if type(value) is not int:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return value


def _retained_draft(value: JsonValue) -> HKLegislationRecordDraft:
    if type(value) is not list or len(value) != _RETAINED_DRAFT_SIZE:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return HKLegislationRecordDraft(
        _retained_text(value[0]),
        _retained_text(value[1]),
        _retained_text(value[2]),
        _retained_text(value[3]),
        _retained_text(value[4]),
        _retained_text(value[5]),
        _retained_text(value[6]),
        _retained_text(value[7]),
        _retained_text(value[8]),
        _retained_text(value[9]),
        _retained_refs(value[10]),
        _retained_text(value[11]),
        _retained_strings(value[12]),
        _retained_strings(value[13]),
        HKLegislationAuthorityNoteSeed(
            _retained_text(value[14]),
            _retained_ref(value[15]),
            _retained_refs(value[16]),
        ),
        _retained_text(value[17]),
        _retained_text(value[18]),
        _retained_text(value[19]),
        _retained_text(value[20]),
        _retained_text(value[21]),
        _retained_integer(value[22]),
        _retained_integer(value[23]),
    )


def _retained_outcome(value: JsonValue) -> HKLegislationInventoryOutcome:
    if type(value) is not list or len(value) != _RETAINED_OUTCOME_SIZE:
        _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)
    return HKLegislationInventoryOutcome(
        _retained_text(value[0]),
        HKLegislationDisposition(_retained_text(value[1])),
        _retained_outcome_kind(value[2]),
        _retained_text(value[3]),
        _retained_strings(value[4]),
        _retained_refs(value[5]),
    )


def _retained_outcome_kind(
    value: JsonValue,
) -> Literal["EMITTED", "WAITING_ROOM", "EVIDENCE_ONLY", "HISTORICAL", "QUARANTINE"]:
    text = _retained_text(value)
    if text == "EMITTED":
        return "EMITTED"
    if text == "WAITING_ROOM":
        return "WAITING_ROOM"
    if text == "EVIDENCE_ONLY":
        return "EVIDENCE_ONLY"
    if text == "HISTORICAL":
        return "HISTORICAL"
    if text == "QUARANTINE":
        return "QUARANTINE"
    _fail(HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID)


def build_hk_legislation_candidate_set(
    *, legislation_scope_code: str, observation_cutoff: str, inputs: object
) -> HKLegislationCandidateSet:
    """Build complete local accounting without authentic admission or identity issuance."""
    try:
        if (
            type(legislation_scope_code) is not str
            or type(observation_cutoff) is not str
            or _SCOPE.fullmatch(legislation_scope_code) is None
            or _UTC.fullmatch(observation_cutoff) is None
            or not _exact_object_tuple(inputs)
        ):
            _fail(HKLegislationRecordErrorCode.INVENTORY_ACCOUNTING_INVALID)
        snapshots = tuple(_snapshot_complete_input(item) for item in inputs)
        validated = tuple(
            _validate_snapshot(item, str(legislation_scope_code)) for item in snapshots
        )
        item_ids = tuple(item.inventory_item_id for item in validated)
        if not validated or len(item_ids) != len(set(item_ids)):
            _fail(HKLegislationRecordErrorCode.INVENTORY_ACCOUNTING_INVALID)
        drafts: list[HKLegislationRecordDraft] = []
        outcomes: list[HKLegislationInventoryOutcome] = []
        for item in validated:
            created, outcome = _outcome_for(item)
            drafts.extend(created)
            outcomes.append(outcome)
        if (
            len(outcomes) != len(validated)
            or len({outcome.inventory_item_id for outcome in outcomes}) != len(validated)
            or len({draft.candidate_key for draft in drafts}) != len(drafts)
        ):
            _fail(HKLegislationRecordErrorCode.INVENTORY_ACCOUNTING_INVALID)
        return _issue_candidate_set(
            str(legislation_scope_code), str(observation_cutoff), tuple(drafts), tuple(outcomes)
        )
    except HKLegislationRecordError:
        raise
    except Exception as error:
        raise HKLegislationRecordError(
            HKLegislationRecordErrorCode.INVENTORY_ACCOUNTING_INVALID
        ) from error
