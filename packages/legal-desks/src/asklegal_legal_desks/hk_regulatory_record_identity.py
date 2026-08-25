"""HKEX candidate traceability and immutable Search Record identity consequences."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from re import fullmatch
from typing import TypeIs

from .hk_regulatory_english import (
    HKEXEnglishConstructionRequest,
    HKEXEnglishServingPart,
    HKEXExactTokenCounter,
    HKEXReferencedLocation,
    HKEXSourceUnitRole,
    construct_hkex_english_request,
    hkex_english_request_from_document,
)

HKEX_RECORD_IDENTITY_RULE_ID = "HKREG-RECORD-IDENTITY-001"
HKEX_RECORD_IDENTITY_CONTRACT_VERSION = "1.0.0"
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_SEARCH_RECORD_PATTERN = r"rec_[0-9a-f]{48}"
_LEGAL_ITEM_PATTERN = r"lit_[0-9a-f]{48}"
_OFFICIAL_VERSION_PATTERN = r"ofv_[0-9a-f]{48}"
_LEGAL_LOCATION_PATTERN = r"loc_[0-9a-f]{48}"
_ISSUED_ID_PATTERN = r"[a-z][a-z0-9]{2,15}_[0-9a-f]{48}"


class HKEXRecordIdentityErrorCode(StrEnum):
    """Closed malformed identity and traceability request failures."""

    CONTRACT = "HKREG_RECORD_IDENTITY_CONTRACT_INVALID"
    EVIDENCE = "HKREG_RECORD_IDENTITY_EVIDENCE_INVALID"
    IDENTITY = "HKREG_RECORD_IDENTITY_STATE_INVALID"
    TRACEABILITY = "HKREG_RECORD_TRACEABILITY_INVALID"


class HKEXRecordIdentityError(ValueError):
    """One fail-closed identity or traceability contract rejection."""

    code: HKEXRecordIdentityErrorCode

    def __init__(self, code: HKEXRecordIdentityErrorCode) -> None:
        """Create one stable contract error."""
        self.code = code
        super().__init__(code.value)


class HKEXRecordChange(StrEnum):
    """Closed claimed change family relative to the prior selected payload."""

    INITIAL = "INITIAL"
    SIX_FIELD_UNCHANGED = "SIX_FIELD_UNCHANGED"
    TRACEABILITY_ONLY = "TRACEABILITY_ONLY"
    PRIMARY_TEXT_CHANGED = "PRIMARY_TEXT_CHANGED"
    APPLICABILITY_CONTEXT_CHANGED = "APPLICABILITY_CONTEXT_CHANGED"
    GOVERNING_CONTEXT_CHANGED = "GOVERNING_CONTEXT_CHANGED"
    REFERENCED_LOCATION_CHANGED = "REFERENCED_LOCATION_CHANGED"
    STRUCTURED_PROJECTION_CHANGED = "STRUCTURED_PROJECTION_CHANGED"
    PARTITION_CHANGED = "PARTITION_CHANGED"
    AUTHORITY_NOTE_CHANGED = "AUTHORITY_NOTE_CHANGED"
    REINSTATEMENT = "REINSTATEMENT"


class HKEXRecordIdentityConsequence(StrEnum):
    """Exact register/selection action without allocating an identity."""

    PRESERVE_SELECTED = "PRESERVE_SELECTED"
    RESELECT_PRESERVED = "RESELECT_PRESERVED"
    REQUIRE_NEW_FORWARD_SUCCESSOR = "REQUIRE_NEW_FORWARD_SUCCESSOR"
    REQUIRE_NEW_INITIAL = "REQUIRE_NEW_INITIAL"
    BLOCK = "BLOCK"


class HKEXRecordIdentityReason(StrEnum):
    """Stable reasons for identity and selection consequences."""

    EXACT_SELECTED_PAYLOAD_PRESERVED = "EXACT_SELECTED_PAYLOAD_PRESERVED"
    EXACT_PRESERVED_PAYLOAD_RESELECTED = "EXACT_PRESERVED_PAYLOAD_RESELECTED"
    UNSEEN_INITIAL_PAYLOAD_REQUIRES_ID = "UNSEEN_INITIAL_PAYLOAD_REQUIRES_ID"
    UNSEEN_CHANGED_PAYLOAD_REQUIRES_SUCCESSOR = "UNSEEN_CHANGED_PAYLOAD_REQUIRES_SUCCESSOR"
    CURRENT_LEGAL_SUPPORT_NOT_PROVED = "CURRENT_LEGAL_SUPPORT_NOT_PROVED"
    CONSTRUCTION_NOT_CURRENT_CANDIDATE = "CONSTRUCTION_NOT_CURRENT_CANDIDATE"
    DECLARED_CHANGE_CONFLICTS_WITH_PAYLOAD = "DECLARED_CHANGE_CONFLICTS_WITH_PAYLOAD"
    REQUIRED_EXACT_PRESERVED_PAYLOAD_MISSING = "REQUIRED_EXACT_PRESERVED_PAYLOAD_MISSING"


class HKEXTraceabilityReferenceType(StrEnum):
    """Closed compact reference types admitted by this material boundary."""

    ARTIFACT = "ARTIFACT"
    DECISION = "DECISION"
    EVIDENCE = "EVIDENCE"
    RULEBOOK = "RULEBOOK"
    SOURCE_SNAPSHOT = "SOURCE_SNAPSHOT"


@dataclass(frozen=True, slots=True)
class HKEXTraceabilityReference:
    """One exact typed immutable reference for the shared ADR 0078 lookup."""

    ref_type: HKEXTraceabilityReferenceType
    ref_id: str
    fingerprint: str

    def __post_init__(self) -> None:
        """Validate closed type, register-issued identity, and exact digest."""
        _enum(self.ref_type, HKEXTraceabilityReferenceType)
        _pattern(self.ref_id, _ISSUED_ID_PATTERN, HKEXRecordIdentityErrorCode.EVIDENCE)
        _fingerprint(self.fingerprint)


@dataclass(frozen=True, slots=True)
class HKEXExistingSearchRecord:
    """One preserved immutable Search Record available for exact reuse."""

    search_record_id: str
    serving_payload_fingerprint: str
    scope_id: str
    legal_item_id: str
    currently_selected: bool

    def __post_init__(self) -> None:
        """Validate one existing identity without inferring it from aliases."""
        _pattern(
            self.search_record_id,
            _SEARCH_RECORD_PATTERN,
            HKEXRecordIdentityErrorCode.IDENTITY,
        )
        _fingerprint(self.serving_payload_fingerprint)
        _text(self.scope_id)
        _pattern(
            self.legal_item_id,
            _LEGAL_ITEM_PATTERN,
            HKEXRecordIdentityErrorCode.IDENTITY,
        )
        if type(self.currently_selected) is not bool:
            raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)


@dataclass(frozen=True, slots=True)
class HKEXSourceTraceBinding:
    """One exact source-unit pointer carried into the traceability seed."""

    source_unit_id: str
    role: HKEXSourceUnitRole
    source_range: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXRecordTraceabilitySeed:
    """Complete material-specific inputs for one future ADR 0078 entry."""

    serving_payload_fingerprint: str
    serving_record_profile_id: str
    tree_fingerprint: str
    source_rule_id: str
    source_artifact_fingerprints: tuple[str, ...]
    legal_item_id: str
    official_version_ids: tuple[str, ...]
    legal_location_ids: tuple[str, ...]
    primary_source_units: tuple[HKEXSourceTraceBinding, ...]
    dependency_source_units: tuple[HKEXSourceTraceBinding, ...]
    referenced_locations: tuple[HKEXReferencedLocation, ...]
    evidence_refs: tuple[HKEXTraceabilityReference, ...]
    authority_note_fingerprint: str
    authority_note_decision_ref: HKEXTraceabilityReference
    authority_note_supporting_refs: tuple[HKEXTraceabilityReference, ...]
    identity_decision_evidence_fingerprint: str
    legal_desk_actor: str
    root_record_unit_id: str
    part_number: int
    total_parts: int


@dataclass(frozen=True, slots=True)
class HKEXRecordIdentityRequest:
    """One exact constructed part plus issued-identity and support facts."""

    decision_id: str
    construction: HKEXEnglishConstructionRequest
    root_record_unit_id: str
    part_number: int
    legal_item_id: str
    official_version_ids: tuple[str, ...]
    legal_location_ids: tuple[str, ...]
    evidence_refs: tuple[HKEXTraceabilityReference, ...]
    authority_note_decision_ref: HKEXTraceabilityReference
    authority_note_supporting_refs: tuple[HKEXTraceabilityReference, ...]
    current_legal_support: bool
    existing_records: tuple[HKEXExistingSearchRecord, ...]
    predecessor_search_record_ids: tuple[str, ...]
    change: HKEXRecordChange
    decision_evidence_fingerprint: str
    legal_desk_actor: str

    def __post_init__(self) -> None:
        """Validate complete identities, evidence, ordering, and prior state."""
        _validate_request(self)

    def document(self) -> dict[str, object]:
        """Return the exact JSON-compatible identity/traceability request."""
        return {
            "decision_id": self.decision_id,
            "construction": self.construction.document(),
            "root_record_unit_id": self.root_record_unit_id,
            "part_number": self.part_number,
            "legal_item_id": self.legal_item_id,
            "official_version_ids": list(self.official_version_ids),
            "legal_location_ids": list(self.legal_location_ids),
            "evidence_refs": [_reference_document(item) for item in self.evidence_refs],
            "authority_note_decision_ref": _reference_document(self.authority_note_decision_ref),
            "authority_note_supporting_refs": [
                _reference_document(item) for item in self.authority_note_supporting_refs
            ],
            "current_legal_support": self.current_legal_support,
            "existing_records": [
                {
                    "search_record_id": record.search_record_id,
                    "serving_payload_fingerprint": record.serving_payload_fingerprint,
                    "scope_id": record.scope_id,
                    "legal_item_id": record.legal_item_id,
                    "currently_selected": record.currently_selected,
                }
                for record in self.existing_records
            ],
            "predecessor_search_record_ids": list(self.predecessor_search_record_ids),
            "change": self.change.value,
            "decision_evidence_fingerprint": self.decision_evidence_fingerprint,
            "legal_desk_actor": self.legal_desk_actor,
        }


@dataclass(frozen=True, slots=True)
class HKEXRecordIdentityDecision:
    """One deterministic identity consequence with no allocation or serving."""

    decision_id: str
    consequence: HKEXRecordIdentityConsequence
    reason: HKEXRecordIdentityReason
    selected_search_record_id: str | None
    predecessor_search_record_ids: tuple[str, ...]
    candidate_serving_payload_fingerprint: str | None
    traceability_seed: HKEXRecordTraceabilitySeed | None
    current_legal_support: bool
    identity_decision_complete: bool
    register_allocation_required: bool
    selection_event_required: bool
    search_record_authorized: bool = False
    serving_ready: bool = False

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return one canonical conformance result without issuing an identity."""
        _text(case_id)
        return {
            "case_id": case_id,
            "contract_version": HKEX_RECORD_IDENTITY_CONTRACT_VERSION,
            "rule_id": HKEX_RECORD_IDENTITY_RULE_ID,
            "decision_id": self.decision_id,
            "consequence": self.consequence.value,
            "reason": self.reason.value,
            "selected_search_record_id": self.selected_search_record_id,
            "predecessor_search_record_ids": list(self.predecessor_search_record_ids),
            "candidate_serving_payload_fingerprint": (self.candidate_serving_payload_fingerprint),
            "traceability_seed": (
                None
                if self.traceability_seed is None
                else _traceability_seed_document(self.traceability_seed)
            ),
            "current_legal_support": self.current_legal_support,
            "identity_decision_complete": self.identity_decision_complete,
            "register_allocation_required": self.register_allocation_required,
            "selection_event_required": self.selection_event_required,
            "search_record_authorized": self.search_record_authorized,
            "serving_ready": self.serving_ready,
        }


def hkex_record_identity_request_from_document(
    document: object,
) -> HKEXRecordIdentityRequest:
    """Strictly decode one source-neutral identity and traceability request."""
    value = _json_object(document)
    _exact_keys(
        value,
        {
            "decision_id",
            "construction",
            "root_record_unit_id",
            "part_number",
            "legal_item_id",
            "official_version_ids",
            "legal_location_ids",
            "evidence_refs",
            "authority_note_decision_ref",
            "authority_note_supporting_refs",
            "current_legal_support",
            "existing_records",
            "predecessor_search_record_ids",
            "change",
            "decision_evidence_fingerprint",
            "legal_desk_actor",
        },
    )
    return HKEXRecordIdentityRequest(
        decision_id=_json_text(value["decision_id"]),
        construction=hkex_english_request_from_document(value["construction"]),
        root_record_unit_id=_json_text(value["root_record_unit_id"]),
        part_number=_json_integer(value["part_number"]),
        legal_item_id=_json_text(value["legal_item_id"]),
        official_version_ids=_json_strings(value["official_version_ids"]),
        legal_location_ids=_json_strings(value["legal_location_ids"]),
        evidence_refs=tuple(
            _reference_from_document(item) for item in _json_object_array(value["evidence_refs"])
        ),
        authority_note_decision_ref=_reference_from_document(
            _json_object(value["authority_note_decision_ref"])
        ),
        authority_note_supporting_refs=tuple(
            _reference_from_document(item)
            for item in _json_object_array(value["authority_note_supporting_refs"])
        ),
        current_legal_support=_json_boolean(value["current_legal_support"]),
        existing_records=tuple(
            _existing_from_document(item) for item in _json_object_array(value["existing_records"])
        ),
        predecessor_search_record_ids=_json_strings(value["predecessor_search_record_ids"]),
        change=_json_enum(value["change"], HKEXRecordChange),
        decision_evidence_fingerprint=_json_text(value["decision_evidence_fingerprint"]),
        legal_desk_actor=_json_text(value["legal_desk_actor"]),
    )


def decide_hkex_record_identity(
    request: HKEXRecordIdentityRequest,
    token_counter: HKEXExactTokenCounter,
) -> HKEXRecordIdentityDecision:
    """Decide exact reuse/new-ID consequence and build one traceability seed."""
    if type(request) is not HKEXRecordIdentityRequest:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    coverage = construct_hkex_english_request(request.construction, token_counter)
    part = _select_part(request, coverage.record_results)
    if part is None:
        return _blocked(
            request,
            HKEXRecordIdentityReason.CONSTRUCTION_NOT_CURRENT_CANDIDATE,
        )
    seed = _traceability_seed(request, part)
    exact = tuple(
        record
        for record in request.existing_records
        if record.serving_payload_fingerprint == part.serving_payload_fingerprint
    )
    if len(exact) > 1:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)
    if not request.current_legal_support:
        return _blocked(
            request,
            HKEXRecordIdentityReason.CURRENT_LEGAL_SUPPORT_NOT_PROVED,
            payload_fingerprint=part.serving_payload_fingerprint,
            seed=seed,
        )
    if exact:
        return _existing_decision(request, exact[0], part, seed)
    return _unseen_decision(request, part, seed)


def _existing_decision(
    request: HKEXRecordIdentityRequest,
    exact: HKEXExistingSearchRecord,
    part: HKEXEnglishServingPart,
    seed: HKEXRecordTraceabilitySeed,
) -> HKEXRecordIdentityDecision:
    if request.change in _PAYLOAD_CHANGES:
        return _blocked(
            request,
            HKEXRecordIdentityReason.DECLARED_CHANGE_CONFLICTS_WITH_PAYLOAD,
            payload_fingerprint=part.serving_payload_fingerprint,
            seed=seed,
        )
    consequence = (
        HKEXRecordIdentityConsequence.PRESERVE_SELECTED
        if exact.currently_selected
        else HKEXRecordIdentityConsequence.RESELECT_PRESERVED
    )
    reason = (
        HKEXRecordIdentityReason.EXACT_SELECTED_PAYLOAD_PRESERVED
        if exact.currently_selected
        else HKEXRecordIdentityReason.EXACT_PRESERVED_PAYLOAD_RESELECTED
    )
    return HKEXRecordIdentityDecision(
        decision_id=request.decision_id,
        consequence=consequence,
        reason=reason,
        selected_search_record_id=exact.search_record_id,
        predecessor_search_record_ids=(),
        candidate_serving_payload_fingerprint=part.serving_payload_fingerprint,
        traceability_seed=seed,
        current_legal_support=True,
        identity_decision_complete=True,
        register_allocation_required=False,
        selection_event_required=not exact.currently_selected,
    )


def _unseen_decision(
    request: HKEXRecordIdentityRequest,
    part: HKEXEnglishServingPart,
    seed: HKEXRecordTraceabilitySeed,
) -> HKEXRecordIdentityDecision:
    if request.change in {
        HKEXRecordChange.SIX_FIELD_UNCHANGED,
        HKEXRecordChange.TRACEABILITY_ONLY,
        HKEXRecordChange.REINSTATEMENT,
    }:
        return _blocked(
            request,
            HKEXRecordIdentityReason.REQUIRED_EXACT_PRESERVED_PAYLOAD_MISSING,
            payload_fingerprint=part.serving_payload_fingerprint,
            seed=seed,
        )
    initial = request.change is HKEXRecordChange.INITIAL
    return HKEXRecordIdentityDecision(
        decision_id=request.decision_id,
        consequence=(
            HKEXRecordIdentityConsequence.REQUIRE_NEW_INITIAL
            if initial
            else HKEXRecordIdentityConsequence.REQUIRE_NEW_FORWARD_SUCCESSOR
        ),
        reason=(
            HKEXRecordIdentityReason.UNSEEN_INITIAL_PAYLOAD_REQUIRES_ID
            if initial
            else HKEXRecordIdentityReason.UNSEEN_CHANGED_PAYLOAD_REQUIRES_SUCCESSOR
        ),
        selected_search_record_id=None,
        predecessor_search_record_ids=request.predecessor_search_record_ids,
        candidate_serving_payload_fingerprint=part.serving_payload_fingerprint,
        traceability_seed=seed,
        current_legal_support=True,
        identity_decision_complete=True,
        register_allocation_required=True,
        selection_event_required=True,
    )


def _blocked(
    request: HKEXRecordIdentityRequest,
    reason: HKEXRecordIdentityReason,
    *,
    payload_fingerprint: str | None = None,
    seed: HKEXRecordTraceabilitySeed | None = None,
) -> HKEXRecordIdentityDecision:
    return HKEXRecordIdentityDecision(
        decision_id=request.decision_id,
        consequence=HKEXRecordIdentityConsequence.BLOCK,
        reason=reason,
        selected_search_record_id=None,
        predecessor_search_record_ids=(),
        candidate_serving_payload_fingerprint=payload_fingerprint,
        traceability_seed=seed,
        current_legal_support=request.current_legal_support,
        identity_decision_complete=False,
        register_allocation_required=False,
        selection_event_required=False,
    )


def _select_part(
    request: HKEXRecordIdentityRequest, results: tuple[object, ...]
) -> HKEXEnglishServingPart | None:
    for result in results:
        root_id = getattr(result, "root_record_unit_id", None)
        if root_id != request.root_record_unit_id:
            continue
        parts = getattr(result, "parts", ())
        for part in parts:
            if isinstance(part, HKEXEnglishServingPart) and part.part_number == request.part_number:
                return part
    return None


def _traceability_seed(
    request: HKEXRecordIdentityRequest,
    part: HKEXEnglishServingPart,
) -> HKEXRecordTraceabilitySeed:
    tree = request.construction.tree
    sources = {unit.source_unit_id: unit for unit in tree.source_units}
    records = {unit.record_unit_id: unit for unit in tree.record_units}
    references = tuple(
        reference
        for record_id in part.record_unit_ids
        for reference in records[record_id].referenced_locations
    )
    if len(references) != len(set(references)):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.TRACEABILITY)
    return HKEXRecordTraceabilitySeed(
        serving_payload_fingerprint=part.serving_payload_fingerprint,
        serving_record_profile_id=request.construction.profile.profile_id,
        tree_fingerprint=tree.fingerprint,
        source_rule_id=tree.source_rule_id,
        source_artifact_fingerprints=tree.source_artifact_fingerprints,
        legal_item_id=request.legal_item_id,
        official_version_ids=request.official_version_ids,
        legal_location_ids=request.legal_location_ids,
        primary_source_units=tuple(
            _source_binding(sources[source_id]) for source_id in part.primary_source_unit_ids
        ),
        dependency_source_units=tuple(
            _source_binding(sources[source_id]) for source_id in part.dependency_source_unit_ids
        ),
        referenced_locations=references,
        evidence_refs=request.evidence_refs,
        authority_note_fingerprint=_raw_fingerprint(
            request.construction.profile.authority_note.encode()
        ),
        authority_note_decision_ref=request.authority_note_decision_ref,
        authority_note_supporting_refs=request.authority_note_supporting_refs,
        identity_decision_evidence_fingerprint=request.decision_evidence_fingerprint,
        legal_desk_actor=request.legal_desk_actor,
        root_record_unit_id=request.root_record_unit_id,
        part_number=part.part_number,
        total_parts=part.total_parts,
    )


def _source_binding(unit: object) -> HKEXSourceTraceBinding:
    source_unit_id = getattr(unit, "source_unit_id", None)
    role = getattr(unit, "role", None)
    source_range = getattr(unit, "source_range", None)
    content_fingerprint = getattr(unit, "content_fingerprint", None)
    if (
        type(source_unit_id) is not str
        or type(role) is not HKEXSourceUnitRole
        or type(source_range) is not str
        or type(content_fingerprint) is not str
    ):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.TRACEABILITY)
    return HKEXSourceTraceBinding(
        source_unit_id,
        role,
        source_range,
        content_fingerprint,
    )


_PAYLOAD_CHANGES = frozenset(
    {
        HKEXRecordChange.PRIMARY_TEXT_CHANGED,
        HKEXRecordChange.APPLICABILITY_CONTEXT_CHANGED,
        HKEXRecordChange.GOVERNING_CONTEXT_CHANGED,
        HKEXRecordChange.REFERENCED_LOCATION_CHANGED,
        HKEXRecordChange.STRUCTURED_PROJECTION_CHANGED,
        HKEXRecordChange.PARTITION_CHANGED,
        HKEXRecordChange.AUTHORITY_NOTE_CHANGED,
    }
)


def _validate_request(request: HKEXRecordIdentityRequest) -> None:
    _text(request.decision_id)
    if type(request.construction) is not HKEXEnglishConstructionRequest:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    _text(request.root_record_unit_id)
    if request.root_record_unit_id not in request.construction.tree.root_record_unit_ids:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    if type(request.part_number) is not int or request.part_number < 1:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    _pattern(
        request.legal_item_id,
        _LEGAL_ITEM_PATTERN,
        HKEXRecordIdentityErrorCode.IDENTITY,
    )
    _sorted_ids(request.official_version_ids, _OFFICIAL_VERSION_PATTERN)
    _sorted_ids(request.legal_location_ids, _LEGAL_LOCATION_PATTERN)
    _sorted_references(request.evidence_refs, required=True)
    if type(request.authority_note_decision_ref) is not HKEXTraceabilityReference or (
        request.authority_note_decision_ref.ref_type is not HKEXTraceabilityReferenceType.DECISION
    ):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.EVIDENCE)
    _sorted_references(request.authority_note_supporting_refs, required=False)
    if type(request.current_legal_support) is not bool:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    _enum(request.change, HKEXRecordChange)
    _fingerprint(request.decision_evidence_fingerprint)
    _text(request.legal_desk_actor)
    _validate_existing(request)


def _validate_existing(request: HKEXRecordIdentityRequest) -> None:
    if type(request.existing_records) is not tuple:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)
    if any(type(record) is not HKEXExistingSearchRecord for record in request.existing_records):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)
    record_ids = tuple(record.search_record_id for record in request.existing_records)
    if record_ids != tuple(sorted(set(record_ids), key=str.encode)):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)
    if any(
        record.scope_id != request.construction.tree.scope_id
        or record.legal_item_id != request.legal_item_id
        for record in request.existing_records
    ):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)
    if sum(record.currently_selected for record in request.existing_records) > 1:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)
    _sorted_ids(request.predecessor_search_record_ids, _SEARCH_RECORD_PATTERN, empty=True)
    existing_ids = set(record_ids)
    if not set(request.predecessor_search_record_ids).issubset(existing_ids):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)
    initial = request.change is HKEXRecordChange.INITIAL
    if initial != (not request.predecessor_search_record_ids):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)
    if initial and request.existing_records:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)


def _sorted_references(values: tuple[HKEXTraceabilityReference, ...], *, required: bool) -> None:
    if type(values) is not tuple or (required and not values):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.EVIDENCE)
    if any(type(item) is not HKEXTraceabilityReference for item in values):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.EVIDENCE)
    keys = tuple((item.ref_type.value, item.ref_id, item.fingerprint) for item in values)
    if keys != tuple(sorted(set(keys))):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.EVIDENCE)


def _sorted_ids(values: tuple[str, ...], pattern: str, *, empty: bool = False) -> None:
    if (
        type(values) is not tuple
        or (not empty and not values)
        or values != tuple(sorted(set(values), key=str.encode))
    ):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.IDENTITY)
    for value in values:
        _pattern(value, pattern, HKEXRecordIdentityErrorCode.IDENTITY)


def _pattern(value: object, pattern: str, code: HKEXRecordIdentityErrorCode) -> str:
    if type(value) is not str or fullmatch(pattern, value) is None:
        raise HKEXRecordIdentityError(code)
    return value


def _fingerprint(value: object) -> str:
    return _pattern(
        value,
        _FINGERPRINT_PATTERN,
        HKEXRecordIdentityErrorCode.EVIDENCE,
    )


def _raw_fingerprint(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    return value


def _enum[E: StrEnum](value: object, expected: type[E]) -> E:
    if type(value) is not expected:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    return value


def _reference_document(reference: HKEXTraceabilityReference) -> dict[str, object]:
    return {
        "ref_type": reference.ref_type.value,
        "ref_id": reference.ref_id,
        "fingerprint": reference.fingerprint,
    }


def _source_binding_document(binding: HKEXSourceTraceBinding) -> dict[str, object]:
    return {
        "source_unit_id": binding.source_unit_id,
        "role": binding.role.value,
        "source_range": binding.source_range,
        "content_fingerprint": binding.content_fingerprint,
    }


def _traceability_seed_document(seed: HKEXRecordTraceabilitySeed) -> dict[str, object]:
    return {
        "serving_payload_fingerprint": seed.serving_payload_fingerprint,
        "serving_record_profile_id": seed.serving_record_profile_id,
        "tree_fingerprint": seed.tree_fingerprint,
        "source_rule_id": seed.source_rule_id,
        "source_artifact_fingerprints": list(seed.source_artifact_fingerprints),
        "legal_item_id": seed.legal_item_id,
        "official_version_ids": list(seed.official_version_ids),
        "legal_location_ids": list(seed.legal_location_ids),
        "primary_source_units": [
            _source_binding_document(item) for item in seed.primary_source_units
        ],
        "dependency_source_units": [
            _source_binding_document(item) for item in seed.dependency_source_units
        ],
        "referenced_locations": [
            {"locator": item.locator, "official_heading": item.official_heading}
            for item in seed.referenced_locations
        ],
        "evidence_refs": [_reference_document(item) for item in seed.evidence_refs],
        "authority_note_fingerprint": seed.authority_note_fingerprint,
        "authority_note_decision_ref": _reference_document(seed.authority_note_decision_ref),
        "authority_note_supporting_refs": [
            _reference_document(item) for item in seed.authority_note_supporting_refs
        ],
        "identity_decision_evidence_fingerprint": (seed.identity_decision_evidence_fingerprint),
        "legal_desk_actor": seed.legal_desk_actor,
        "root_record_unit_id": seed.root_record_unit_id,
        "part_number": seed.part_number,
        "total_parts": seed.total_parts,
    }


def _reference_from_document(value: dict[str, object]) -> HKEXTraceabilityReference:
    _exact_keys(value, {"ref_type", "ref_id", "fingerprint"})
    return HKEXTraceabilityReference(
        ref_type=_json_enum(value["ref_type"], HKEXTraceabilityReferenceType),
        ref_id=_json_text(value["ref_id"]),
        fingerprint=_json_text(value["fingerprint"]),
    )


def _existing_from_document(value: dict[str, object]) -> HKEXExistingSearchRecord:
    _exact_keys(
        value,
        {
            "search_record_id",
            "serving_payload_fingerprint",
            "scope_id",
            "legal_item_id",
            "currently_selected",
        },
    )
    return HKEXExistingSearchRecord(
        search_record_id=_json_text(value["search_record_id"]),
        serving_payload_fingerprint=_json_text(value["serving_payload_fingerprint"]),
        scope_id=_json_text(value["scope_id"]),
        legal_item_id=_json_text(value["legal_item_id"]),
        currently_selected=_json_boolean(value["currently_selected"]),
    )


def _json_object(value: object) -> dict[str, object]:
    if not _is_object_dict(value) or any(type(key) is not str for key in value):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    return {str(key): item for key, item in value.items()}


def _json_object_array(value: object) -> tuple[dict[str, object], ...]:
    if not _is_object_list(value):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    return tuple(_json_object(item) for item in value)


def _is_object_dict(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return isinstance(value, list)


def _exact_keys(value: dict[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)


def _json_text(value: object) -> str:
    return _text(value)


def _json_strings(value: object) -> tuple[str, ...]:
    if not _is_object_list(value):
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    return tuple(_json_text(item) for item in value)


def _json_integer(value: object) -> int:
    if type(value) is not int:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    return value


def _json_boolean(value: object) -> bool:
    if type(value) is not bool:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT)
    return value


def _json_enum[E: StrEnum](value: object, expected: type[E]) -> E:
    text = _json_text(value)
    try:
        return expected(text)
    except ValueError as error:
        raise HKEXRecordIdentityError(HKEXRecordIdentityErrorCode.CONTRACT) from error
