"""Deterministic HKEX component continuity and identity consequences."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from typing import TypeIs

from .hk_regulatory_inventory import HKEX_SCOPE_IDS, HKEXProcessingOutcome

HKEX_COMPONENT_CONTINUITY_RULE_ID = "HKREG-COMPONENT-CONTINUITY-001"
HKEX_COMPONENT_CONTINUITY_CONTRACT_VERSION = "1.0.0"
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_MINIMUM_BRANCHING_COMPONENTS = 2


class HKEXContinuityErrorCode(StrEnum):
    """Closed malformed-contract failures."""

    CONTRACT = "HKREG_COMPONENT_CONTINUITY_CONTRACT_INVALID"
    EVIDENCE = "HKREG_COMPONENT_CONTINUITY_EVIDENCE_INVALID"


class HKEXContinuityError(ValueError):
    """One continuity request that cannot safely be interpreted."""

    code: HKEXContinuityErrorCode

    def __init__(self, code: HKEXContinuityErrorCode) -> None:
        """Create one stable fail-closed error."""
        self.code = code
        super().__init__(code.value)


class HKEXContinuityEvent(StrEnum):
    """Exact observed comparison event, never inferred from an alias alone."""

    UNCHANGED = "UNCHANGED"
    URL_MOVED = "URL_MOVED"
    RENAMED = "RENAMED"
    RENUMBERED = "RENUMBERED"
    STRUCTURALLY_MOVED = "STRUCTURALLY_MOVED"
    TEXT_CORRECTED = "TEXT_CORRECTED"
    REPLACED = "REPLACED"
    SPLIT = "SPLIT"
    MERGED = "MERGED"
    BOARD_TRANSFERRED = "BOARD_TRANSFERRED"
    OFFICIALLY_WITHDRAWN = "OFFICIALLY_WITHDRAWN"
    DISAPPEARED = "DISAPPEARED"
    REAPPEARED = "REAPPEARED"
    NEW_COMPONENT = "NEW_COMPONENT"


class HKEXContinuitySupport(StrEnum):
    """Strength of permitted official continuity evidence."""

    PROVED = "PROVED"
    AMBIGUOUS = "AMBIGUOUS"
    SIMILARITY_OR_ALIAS_ONLY = "SIMILARITY_OR_ALIAS_ONLY"
    MISSING_OR_CONFLICTING = "MISSING_OR_CONFLICTING"


class HKEXIdentityConsequence(StrEnum):
    """Management-Register identity action implied by one proved event."""

    PRESERVE_EXISTING = "PRESERVE_EXISTING"
    PRESERVE_HISTORICAL = "PRESERVE_HISTORICAL"
    RESELECT_EXISTING = "RESELECT_EXISTING"
    REQUIRE_NEW_UNRELATED = "REQUIRE_NEW_UNRELATED"
    REQUIRE_NEW_ONE_TO_ONE = "REQUIRE_NEW_ONE_TO_ONE"
    REQUIRE_NEW_ONE_TO_MANY = "REQUIRE_NEW_ONE_TO_MANY"
    REQUIRE_NEW_MANY_TO_ONE = "REQUIRE_NEW_MANY_TO_ONE"
    QUARANTINE = "QUARANTINE"


class HKEXComponentLineageType(StrEnum):
    """Typed acyclic relationship required after register allocation."""

    NONE = "NONE"
    RENAME = "RENAME"
    RENUMBER = "RENUMBER"
    STRUCTURAL_MOVE = "STRUCTURAL_MOVE"
    CORRECTION = "CORRECTION"
    REPLACEMENT = "REPLACEMENT"
    SPLIT = "SPLIT"
    MERGE = "MERGE"
    TRANSFER = "TRANSFER"
    WITHDRAWAL = "WITHDRAWAL"
    REINSTATEMENT = "REINSTATEMENT"


class HKEXContinuityReason(StrEnum):
    """Stable terminal explanation codes."""

    EXACT_NO_CHANGE = "EXACT_NO_CHANGE"
    PRESENTATION_ALIAS_CHANGED = "PRESENTATION_ALIAS_CHANGED"
    SAME_COMPONENT_RENAMED = "SAME_COMPONENT_RENAMED"
    SAME_LOCATION_RENUMBERED = "SAME_LOCATION_RENUMBERED"
    SAME_COMPONENT_STRUCTURALLY_MOVED = "SAME_COMPONENT_STRUCTURALLY_MOVED"
    SAME_COMPONENT_TEXT_CORRECTED = "SAME_COMPONENT_TEXT_CORRECTED"
    DISTINCT_REPLACEMENT_REQUIRES_NEW_ID = "DISTINCT_REPLACEMENT_REQUIRES_NEW_ID"
    SPLIT_REQUIRES_ONE_TO_MANY_IDS = "SPLIT_REQUIRES_ONE_TO_MANY_IDS"
    MERGE_REQUIRES_MANY_TO_ONE_ID = "MERGE_REQUIRES_MANY_TO_ONE_ID"
    BOARD_TRANSFER_REQUIRES_NEW_OWNER_ID = "BOARD_TRANSFER_REQUIRES_NEW_OWNER_ID"
    OFFICIAL_WITHDRAWAL_PRESERVES_HISTORY = "OFFICIAL_WITHDRAWAL_PRESERVES_HISTORY"
    DISAPPEARANCE_PROVES_NO_RETIREMENT = "DISAPPEARANCE_PROVES_NO_RETIREMENT"
    REAPPEARANCE_RESELECTS_PROVED_ID = "REAPPEARANCE_RESELECTS_PROVED_ID"
    NEW_COMPONENT_REQUIRES_REGISTER_ID = "NEW_COMPONENT_REQUIRES_REGISTER_ID"
    CONTINUITY_EVIDENCE_UNRESOLVED = "CONTINUITY_EVIDENCE_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class HKEXExistingComponentIdentity:
    """One already issued component and Legal Location identity."""

    component_id: str
    scope_id: str
    legal_location_id: str
    aliases: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate one immutable predecessor reference."""
        _text(self.component_id)
        _scope(self.scope_id)
        _text(self.legal_location_id)
        _strings(self.aliases)
        _strings(self.evidence_refs)


@dataclass(frozen=True, slots=True)
class HKEXObservedComponentCandidate:
    """One decision-local current observation before permanent ID allocation."""

    candidate_id: str
    scope_id: str
    observed_locator: str
    aliases: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate one current candidate without treating its aliases as ID."""
        _text(self.candidate_id)
        _scope(self.scope_id)
        _text(self.observed_locator)
        _strings(self.aliases)
        _strings(self.evidence_refs)


@dataclass(frozen=True, slots=True)
class HKEXComponentContinuityRequest:
    """One predecessor/current comparison under one exact Source Rulebook rule."""

    decision_id: str
    cutoff: str
    event: HKEXContinuityEvent
    support: HKEXContinuitySupport
    predecessors: tuple[HKEXExistingComponentIdentity, ...]
    candidates: tuple[HKEXObservedComponentCandidate, ...]
    source_rule_id: str
    evidence_refs: tuple[str, ...]
    evidence_fingerprint: str
    legal_desk_actor: str

    def __post_init__(self) -> None:
        """Reject invalid event cardinality, board ownership, or evidence."""
        _validate_request(self)


@dataclass(frozen=True, slots=True)
class HKEXComponentContinuityDecision:
    """One identity consequence with no ID issuance or serving effect."""

    decision_id: str
    cutoff: str
    event: HKEXContinuityEvent
    identity_consequence: HKEXIdentityConsequence
    lineage_type: HKEXComponentLineageType
    processing_outcome: HKEXProcessingOutcome
    reason: HKEXContinuityReason
    preserved_component_ids: tuple[str, ...]
    ended_component_ids: tuple[str, ...]
    candidate_ids_requiring_allocation: tuple[str, ...]
    evidence_fingerprint: str
    source_rule_id: str
    continuity_decision_complete: bool
    inventory_admission_ready: bool
    search_record_authorized: bool = False
    serving_ready: bool = False

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return the exact effect-free conformance projection."""
        _text(case_id)
        return {
            "case_id": case_id,
            "identity_consequence": self.identity_consequence.value,
            "lineage_type": self.lineage_type.value,
            "processing_outcome": self.processing_outcome.value,
            "reason": self.reason.value,
            "preserved_component_ids": list(self.preserved_component_ids),
            "ended_component_ids": list(self.ended_component_ids),
            "candidate_ids_requiring_allocation": list(self.candidate_ids_requiring_allocation),
            "continuity_decision_complete": self.continuity_decision_complete,
            "inventory_admission_ready": self.inventory_admission_ready,
            "search_record_authorized": self.search_record_authorized,
            "serving_ready": self.serving_ready,
        }


def hkex_component_continuity_request_from_document(
    document: object,
) -> HKEXComponentContinuityRequest:
    """Strictly decode one JSON-compatible comparison without repair."""
    value = _document(document)
    _exact_keys(
        value,
        {
            "decision_id",
            "cutoff",
            "event",
            "support",
            "predecessors",
            "candidates",
            "source_rule_id",
            "evidence_refs",
            "evidence_fingerprint",
            "legal_desk_actor",
        },
    )
    return HKEXComponentContinuityRequest(
        decision_id=_json_text(value["decision_id"]),
        cutoff=_json_text(value["cutoff"]),
        event=_json_enum(value["event"], HKEXContinuityEvent),
        support=_json_enum(value["support"], HKEXContinuitySupport),
        predecessors=_json_predecessors(value["predecessors"]),
        candidates=_json_candidates(value["candidates"]),
        source_rule_id=_json_text(value["source_rule_id"]),
        evidence_refs=_json_strings(value["evidence_refs"]),
        evidence_fingerprint=_json_text(value["evidence_fingerprint"]),
        legal_desk_actor=_json_text(value["legal_desk_actor"]),
    )


def decide_hkex_component_continuity(
    request: HKEXComponentContinuityRequest,
) -> HKEXComponentContinuityDecision:
    """Apply exact identity consequences without allocating or reusing an ID."""
    if type(request) is not HKEXComponentContinuityRequest:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
    if request.support is not HKEXContinuitySupport.PROVED:
        return _decision(
            request,
            HKEXIdentityConsequence.QUARANTINE,
            HKEXComponentLineageType.NONE,
            HKEXContinuityReason.CONTINUITY_EVIDENCE_UNRESOLVED,
        )
    consequence, lineage, reason = _proved_result(request.event)
    return _decision(request, consequence, lineage, reason)


def _proved_result(
    event: HKEXContinuityEvent,
) -> tuple[HKEXIdentityConsequence, HKEXComponentLineageType, HKEXContinuityReason]:
    return {
        HKEXContinuityEvent.UNCHANGED: (
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.NONE,
            HKEXContinuityReason.EXACT_NO_CHANGE,
        ),
        HKEXContinuityEvent.URL_MOVED: (
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.NONE,
            HKEXContinuityReason.PRESENTATION_ALIAS_CHANGED,
        ),
        HKEXContinuityEvent.RENAMED: (
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.RENAME,
            HKEXContinuityReason.SAME_COMPONENT_RENAMED,
        ),
        HKEXContinuityEvent.RENUMBERED: (
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.RENUMBER,
            HKEXContinuityReason.SAME_LOCATION_RENUMBERED,
        ),
        HKEXContinuityEvent.STRUCTURALLY_MOVED: (
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.STRUCTURAL_MOVE,
            HKEXContinuityReason.SAME_COMPONENT_STRUCTURALLY_MOVED,
        ),
        HKEXContinuityEvent.TEXT_CORRECTED: (
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.CORRECTION,
            HKEXContinuityReason.SAME_COMPONENT_TEXT_CORRECTED,
        ),
        HKEXContinuityEvent.REPLACED: (
            HKEXIdentityConsequence.REQUIRE_NEW_ONE_TO_ONE,
            HKEXComponentLineageType.REPLACEMENT,
            HKEXContinuityReason.DISTINCT_REPLACEMENT_REQUIRES_NEW_ID,
        ),
        HKEXContinuityEvent.SPLIT: (
            HKEXIdentityConsequence.REQUIRE_NEW_ONE_TO_MANY,
            HKEXComponentLineageType.SPLIT,
            HKEXContinuityReason.SPLIT_REQUIRES_ONE_TO_MANY_IDS,
        ),
        HKEXContinuityEvent.MERGED: (
            HKEXIdentityConsequence.REQUIRE_NEW_MANY_TO_ONE,
            HKEXComponentLineageType.MERGE,
            HKEXContinuityReason.MERGE_REQUIRES_MANY_TO_ONE_ID,
        ),
        HKEXContinuityEvent.BOARD_TRANSFERRED: (
            HKEXIdentityConsequence.REQUIRE_NEW_ONE_TO_ONE,
            HKEXComponentLineageType.TRANSFER,
            HKEXContinuityReason.BOARD_TRANSFER_REQUIRES_NEW_OWNER_ID,
        ),
        HKEXContinuityEvent.OFFICIALLY_WITHDRAWN: (
            HKEXIdentityConsequence.PRESERVE_HISTORICAL,
            HKEXComponentLineageType.WITHDRAWAL,
            HKEXContinuityReason.OFFICIAL_WITHDRAWAL_PRESERVES_HISTORY,
        ),
        HKEXContinuityEvent.DISAPPEARED: (
            HKEXIdentityConsequence.QUARANTINE,
            HKEXComponentLineageType.NONE,
            HKEXContinuityReason.DISAPPEARANCE_PROVES_NO_RETIREMENT,
        ),
        HKEXContinuityEvent.REAPPEARED: (
            HKEXIdentityConsequence.RESELECT_EXISTING,
            HKEXComponentLineageType.REINSTATEMENT,
            HKEXContinuityReason.REAPPEARANCE_RESELECTS_PROVED_ID,
        ),
        HKEXContinuityEvent.NEW_COMPONENT: (
            HKEXIdentityConsequence.REQUIRE_NEW_UNRELATED,
            HKEXComponentLineageType.NONE,
            HKEXContinuityReason.NEW_COMPONENT_REQUIRES_REGISTER_ID,
        ),
    }[event]


def _decision(
    request: HKEXComponentContinuityRequest,
    consequence: HKEXIdentityConsequence,
    lineage: HKEXComponentLineageType,
    reason: HKEXContinuityReason,
) -> HKEXComponentContinuityDecision:
    quarantined = consequence is HKEXIdentityConsequence.QUARANTINE
    allocates = consequence in {
        HKEXIdentityConsequence.REQUIRE_NEW_UNRELATED,
        HKEXIdentityConsequence.REQUIRE_NEW_ONE_TO_ONE,
        HKEXIdentityConsequence.REQUIRE_NEW_ONE_TO_MANY,
        HKEXIdentityConsequence.REQUIRE_NEW_MANY_TO_ONE,
    }
    preserves = consequence in {
        HKEXIdentityConsequence.PRESERVE_EXISTING,
        HKEXIdentityConsequence.PRESERVE_HISTORICAL,
        HKEXIdentityConsequence.RESELECT_EXISTING,
        HKEXIdentityConsequence.QUARANTINE,
    }
    ends = request.event in {
        HKEXContinuityEvent.REPLACED,
        HKEXContinuityEvent.SPLIT,
        HKEXContinuityEvent.MERGED,
        HKEXContinuityEvent.BOARD_TRANSFERRED,
        HKEXContinuityEvent.OFFICIALLY_WITHDRAWN,
    }
    return HKEXComponentContinuityDecision(
        decision_id=request.decision_id,
        cutoff=request.cutoff,
        event=request.event,
        identity_consequence=consequence,
        lineage_type=lineage,
        processing_outcome=(
            HKEXProcessingOutcome.QUARANTINE if quarantined else HKEXProcessingOutcome.PASS
        ),
        reason=reason,
        preserved_component_ids=(
            tuple(item.component_id for item in request.predecessors) if preserves else ()
        ),
        ended_component_ids=(
            tuple(item.component_id for item in request.predecessors) if ends else ()
        ),
        candidate_ids_requiring_allocation=(
            tuple(item.candidate_id for item in request.candidates) if allocates else ()
        ),
        evidence_fingerprint=request.evidence_fingerprint,
        source_rule_id=request.source_rule_id,
        continuity_decision_complete=not quarantined,
        inventory_admission_ready=not quarantined and not allocates,
    )


def _validate_request(request: HKEXComponentContinuityRequest) -> None:
    _text(request.decision_id)
    _text(request.cutoff)
    if type(request.event) is not HKEXContinuityEvent:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
    if type(request.support) is not HKEXContinuitySupport:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
    _objects(request.predecessors, HKEXExistingComponentIdentity, "component_id")
    _objects(request.candidates, HKEXObservedComponentCandidate, "candidate_id")
    _text(request.source_rule_id)
    _strings(request.evidence_refs)
    _text(request.legal_desk_actor)
    if fullmatch(_FINGERPRINT_PATTERN, request.evidence_fingerprint) is None:
        raise HKEXContinuityError(HKEXContinuityErrorCode.EVIDENCE)
    _validate_cardinality(request)
    _validate_board_relationship(request)


def _validate_cardinality(request: HKEXComponentContinuityRequest) -> None:
    predecessor_count = len(request.predecessors)
    candidate_count = len(request.candidates)
    expected = {
        HKEXContinuityEvent.UNCHANGED: (1, 1),
        HKEXContinuityEvent.URL_MOVED: (1, 1),
        HKEXContinuityEvent.RENAMED: (1, 1),
        HKEXContinuityEvent.RENUMBERED: (1, 1),
        HKEXContinuityEvent.STRUCTURALLY_MOVED: (1, 1),
        HKEXContinuityEvent.TEXT_CORRECTED: (1, 1),
        HKEXContinuityEvent.REPLACED: (1, 1),
        HKEXContinuityEvent.BOARD_TRANSFERRED: (1, 1),
        HKEXContinuityEvent.REAPPEARED: (1, 1),
        HKEXContinuityEvent.OFFICIALLY_WITHDRAWN: (1, 0),
        HKEXContinuityEvent.DISAPPEARED: (1, 0),
        HKEXContinuityEvent.NEW_COMPONENT: (0, 1),
    }
    if request.event is HKEXContinuityEvent.SPLIT:
        valid = predecessor_count == 1 and candidate_count >= _MINIMUM_BRANCHING_COMPONENTS
    elif request.event is HKEXContinuityEvent.MERGED:
        valid = predecessor_count >= _MINIMUM_BRANCHING_COMPONENTS and candidate_count == 1
    else:
        valid = (predecessor_count, candidate_count) == expected[request.event]
    if not valid:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)


def _validate_board_relationship(request: HKEXComponentContinuityRequest) -> None:
    predecessor_scopes = {item.scope_id for item in request.predecessors}
    candidate_scopes = {item.scope_id for item in request.candidates}
    if len(predecessor_scopes) > 1 or len(candidate_scopes) > 1:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
    if request.event is HKEXContinuityEvent.BOARD_TRANSFERRED:
        valid = predecessor_scopes != candidate_scopes
    elif predecessor_scopes and candidate_scopes:
        valid = predecessor_scopes == candidate_scopes
    else:
        valid = True
    if not valid:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)


def _objects[T: object](values: tuple[T, ...], expected: type[T], field: str) -> None:
    if type(values) is not tuple:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
    identities: list[str] = []
    for value in values:
        if type(value) is not expected:
            raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
        identity = getattr(value, field, None)
        if type(identity) is not str:
            raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
        identities.append(identity)
    if len(identities) != len(set(identities)):
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)


def _scope(value: str) -> str:
    if value not in HKEX_SCOPE_IDS:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
    return value


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
    return value


def _strings(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple or not values or len(values) != len(set(values)):
        raise HKEXContinuityError(HKEXContinuityErrorCode.EVIDENCE)
    for value in values:
        _text(value)
    return values


def _document(value: object) -> dict[str, object]:
    if not _is_object_dict(value):
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
    result: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
        result[key] = item
    return result


def _exact_keys(value: dict[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)


def _json_text(value: object) -> str:
    return _text(value)


def _json_array(value: object) -> tuple[object, ...]:
    if not _is_object_list(value):
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT)
    return tuple(value)


def _json_strings(value: object) -> tuple[str, ...]:
    result = tuple(_json_text(item) for item in _json_array(value))
    return _strings(result)


def _json_enum[E: StrEnum](value: object, enum_type: type[E]) -> E:
    text = _json_text(value)
    try:
        return enum_type(text)
    except ValueError as error:
        raise HKEXContinuityError(HKEXContinuityErrorCode.CONTRACT) from error


def _json_predecessors(value: object) -> tuple[HKEXExistingComponentIdentity, ...]:
    result: list[HKEXExistingComponentIdentity] = []
    for item in _json_array(value):
        raw = _document(item)
        _exact_keys(
            raw,
            {"component_id", "scope_id", "legal_location_id", "aliases", "evidence_refs"},
        )
        result.append(
            HKEXExistingComponentIdentity(
                component_id=_json_text(raw["component_id"]),
                scope_id=_json_text(raw["scope_id"]),
                legal_location_id=_json_text(raw["legal_location_id"]),
                aliases=_json_strings(raw["aliases"]),
                evidence_refs=_json_strings(raw["evidence_refs"]),
            )
        )
    return tuple(result)


def _json_candidates(value: object) -> tuple[HKEXObservedComponentCandidate, ...]:
    result: list[HKEXObservedComponentCandidate] = []
    for item in _json_array(value):
        raw = _document(item)
        _exact_keys(
            raw,
            {"candidate_id", "scope_id", "observed_locator", "aliases", "evidence_refs"},
        )
        result.append(
            HKEXObservedComponentCandidate(
                candidate_id=_json_text(raw["candidate_id"]),
                scope_id=_json_text(raw["scope_id"]),
                observed_locator=_json_text(raw["observed_locator"]),
                aliases=_json_strings(raw["aliases"]),
                evidence_refs=_json_strings(raw["evidence_refs"]),
            )
        )
    return tuple(result)


def _is_object_dict(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return isinstance(value, list)
