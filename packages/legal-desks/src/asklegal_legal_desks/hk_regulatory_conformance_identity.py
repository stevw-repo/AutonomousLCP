"""ADR 0074/0075 Search Record identity, lineage, and traceability conformance."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from typing import Never, TypeIs

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_regulatory_continuity import (
    HKEX_COMPONENT_CONTINUITY_CONTRACT_VERSION,
    HKEX_COMPONENT_CONTINUITY_RULE_ID,
    HKEXComponentContinuityDecision,
    HKEXComponentContinuityRequest,
    HKEXComponentLineageType,
    HKEXContinuitySupport,
    HKEXIdentityConsequence,
    decide_hkex_component_continuity,
    hkex_component_continuity_request_from_document,
)
from .hk_regulatory_english import (
    HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
    HKEX_ENGLISH_RECORD_RULE_ID,
    HKEXSourceUnitRole,
)
from .hk_regulatory_inventory import HKEX_SCOPE_IDS
from .hk_regulatory_record_identity import (
    HKEX_RECORD_IDENTITY_CONTRACT_VERSION,
    HKEX_RECORD_IDENTITY_RULE_ID,
    HKEXRecordChange,
    HKEXRecordIdentityConsequence,
    HKEXRecordIdentityDecision,
    HKEXRecordIdentityRequest,
    decide_hkex_record_identity,
    hkex_record_identity_request_from_document,
)

HKEX_IDENTITY_DECISION_RULE_ID = "HKREG-IDENTITY-DECISION-001"
HKEX_IDENTITY_DECISION_CONTRACT_VERSION = "1.0.0"
HKEX_IDENTITY_DECISION_CASE_COUNT = 24

_CASE_PATTERN = r"HKREG-DET-IDN-(0[0-1][0-9]|02[0-4])"
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_RECORD_PATTERN = r"rec_[0-9a-f]{48}"
_LOCATION_PATTERN = r"loc_[0-9a-f]{48}"
_CONTRACT_BINDING_COUNT = 5
_MAX_REQUESTS = 8
_BOARD_PAIR_COUNT = 2
_BRANCHING_MEMBER_MINIMUM = 2
_SYNTHETIC_PROFILE_ID = "synthetic-hkex-english-profile-1"
_SYNTHETIC_PROFILE_FINGERPRINT = f"sha256:{'a' * 64}"
_SYNTHETIC_TOKENIZER_ID = "synthetic-codepoint-counter-1"

_EXPECTED_PAIRS: dict[str, tuple[tuple[str, str], ...]] = {
    "HKREG-DET-IDN-002": (("HKREG-PAIR-046", "POSITIVE"),),
    "HKREG-DET-IDN-004": (
        ("HKREG-PAIR-046", "NEAR_MISS"),
        ("HKREG-PAIR-048", "NEAR_MISS"),
    ),
    "HKREG-DET-IDN-010": (("HKREG-PAIR-047", "NEAR_MISS"),),
    "HKREG-DET-IDN-011": (("HKREG-PAIR-048", "POSITIVE"),),
    "HKREG-DET-IDN-014": (("HKREG-PAIR-047", "POSITIVE"),),
    "HKREG-DET-IDN-022": (("HKREG-PAIR-049", "POSITIVE"),),
    "HKREG-DET-IDN-023": (("HKREG-PAIR-049", "NEAR_MISS"),),
}


class HKEXIdentityDecisionErrorCode(StrEnum):
    """Closed malformed permanent identity-case failures."""

    CONTRACT = "HKREG_IDENTITY_DECISION_CONTRACT_INVALID"
    IDENTITY = "HKREG_IDENTITY_DECISION_IDENTITY_INVALID"
    FINGERPRINT = "HKREG_IDENTITY_DECISION_FINGERPRINT_INVALID"


class HKEXIdentityDecisionError(ValueError):
    """One fail-closed permanent identity-case rejection."""

    code: HKEXIdentityDecisionErrorCode

    def __init__(self, code: HKEXIdentityDecisionErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKEXIdentityAssertionScope(StrEnum):
    """One orthogonal immutable-record, lookup, or lineage invariant."""

    BOARD_SEPARATION = "BOARD_SEPARATION"
    EXACT_REUSE = "EXACT_REUSE"
    RESELECTION = "RESELECTION"
    PRIMARY_TEXT_CHANGE = "PRIMARY_TEXT_CHANGE"
    APPLICABILITY_CHANGE = "APPLICABILITY_CHANGE"
    GOVERNING_DEPENDENCY_CHANGE = "GOVERNING_DEPENDENCY_CHANGE"
    REFERENCED_LOCATION_CHANGE = "REFERENCED_LOCATION_CHANGE"
    STRUCTURED_PROJECTION_CHANGE = "STRUCTURED_PROJECTION_CHANGE"
    PARTITION_CHANGE = "PARTITION_CHANGE"
    AUTHORITY_NOTE_CHANGE = "AUTHORITY_NOTE_CHANGE"
    URL_MOVE = "URL_MOVE"
    PAGE_REFLOW = "PAGE_REFLOW"
    OPTIONAL_CHINESE_CHANGE = "OPTIONAL_CHINESE_CHANGE"
    TRACEABILITY_ONLY = "TRACEABILITY_ONLY"
    CHINESE_DEFECT = "CHINESE_DEFECT"
    LOOKUP_VALID = "LOOKUP_VALID"
    LOOKUP_INCOMPLETE = "LOOKUP_INCOMPLETE"
    LOOKUP_WRONG_OWNER = "LOOKUP_WRONG_OWNER"
    LINEAGE_ONE_TO_ONE = "LINEAGE_ONE_TO_ONE"
    LINEAGE_SPLIT_MERGE = "LINEAGE_SPLIT_MERGE"
    LINEAGE_CYCLE = "LINEAGE_CYCLE"
    PROVED_CONTINUITY = "PROVED_CONTINUITY"
    SIMILARITY_ONLY = "SIMILARITY_ONLY"
    LOOKUP_FINGERPRINT_MISMATCH = "LOOKUP_FINGERPRINT_MISMATCH"


class HKEXIdentityDecisionOutcome(StrEnum):
    """Effect-free identity checkpoint outcome."""

    PASS = "PASS"
    REQUIRE_NEW_RECORD = "REQUIRE_NEW_RECORD"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


class HKEXIdentityDecisionReason(StrEnum):
    """Exact accepted consequence for each permanent invariant."""

    SEPARATE_BOARD_IDENTITIES = "SEPARATE_BOARD_IDENTITIES"
    EXACT_RECORD_REUSED = "EXACT_RECORD_REUSED"
    PRESERVED_RECORD_RESELECTED = "PRESERVED_RECORD_RESELECTED"
    PRIMARY_TEXT_SUCCESSOR_REQUIRED = "PRIMARY_TEXT_SUCCESSOR_REQUIRED"
    APPLICABILITY_SUCCESSOR_REQUIRED = "APPLICABILITY_SUCCESSOR_REQUIRED"
    GOVERNING_DEPENDENCY_SUCCESSOR_REQUIRED = "GOVERNING_DEPENDENCY_SUCCESSOR_REQUIRED"
    REFERENCED_LOCATION_SUCCESSOR_REQUIRED = "REFERENCED_LOCATION_SUCCESSOR_REQUIRED"
    STRUCTURED_PROJECTION_SUCCESSOR_REQUIRED = "STRUCTURED_PROJECTION_SUCCESSOR_REQUIRED"
    PARTITION_SUCCESSORS_REQUIRED = "PARTITION_SUCCESSORS_REQUIRED"
    AUTHORITY_NOTE_SUCCESSOR_REQUIRED = "AUTHORITY_NOTE_SUCCESSOR_REQUIRED"
    URL_MOVE_REUSES_RECORD = "URL_MOVE_REUSES_RECORD"
    PAGE_REFLOW_REUSES_RECORD = "PAGE_REFLOW_REUSES_RECORD"
    OPTIONAL_CHINESE_CHANGE_REUSES_RECORD = "OPTIONAL_CHINESE_CHANGE_REUSES_RECORD"
    TRACEABILITY_REVISION_ONLY = "TRACEABILITY_REVISION_ONLY"
    ENGLISH_SUPPORT_BLOCKED = "ENGLISH_SUPPORT_BLOCKED"
    LOOKUP_ENTRY_VALID = "LOOKUP_ENTRY_VALID"
    LOOKUP_INCOMPLETE = "LOOKUP_INCOMPLETE"
    LOOKUP_OWNERSHIP_MISMATCH = "LOOKUP_OWNERSHIP_MISMATCH"
    ONE_TO_ONE_LINEAGE_VALID = "ONE_TO_ONE_LINEAGE_VALID"
    SPLIT_MERGE_LINEAGE_VALID = "SPLIT_MERGE_LINEAGE_VALID"
    LINEAGE_REJECTED = "LINEAGE_REJECTED"
    OFFICIAL_CONTINUITY_PROVED = "OFFICIAL_CONTINUITY_PROVED"
    SIMILARITY_CONTINUITY_QUARANTINED = "SIMILARITY_CONTINUITY_QUARANTINED"
    LOOKUP_FINGERPRINT_MISMATCH = "LOOKUP_FINGERPRINT_MISMATCH"


class HKEXIdentityRecordAction(StrEnum):
    """Register/selection consequence without issuing or mutating an ID."""

    SEPARATE_INITIALS = "SEPARATE_INITIALS"
    REUSE = "REUSE"
    RESELECT = "RESELECT"
    REQUIRE_NEW = "REQUIRE_NEW"
    NO_ID_CHANGE = "NO_ID_CHANGE"
    VALIDATE_ONLY = "VALIDATE_ONLY"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


class HKEXIdentityTraceabilityAction(StrEnum):
    """Traceability consequence independent of Search Record identity."""

    NONE = "NONE"
    REVISE = "REVISE"
    VALIDATE = "VALIDATE"
    BLOCK = "BLOCK"


class HKEXSearchRecordLineageType(StrEnum):
    """Closed forward immutable Search Record lineage cardinalities."""

    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"


@dataclass(frozen=True, slots=True)
class HKEXIdentityContractBinding:
    """One exact contract bound to a permanent case."""

    contract_id: str
    version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXIdentityPairMembership:
    """One exact high-risk pair role."""

    pair_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKEXIdentityEvidencePacket:
    """One proposal-safe synthetic fact packet."""

    slot_id: str
    state: str
    path: str
    role: str
    media_type: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXIdentityLookupRecord:
    """One desired record or one immutable lookup entry."""

    search_record_id: str
    scope_id: str
    legal_location_ids: tuple[str, ...]
    serving_payload_fingerprint: str
    rendered_fingerprint: str
    authority_note_fingerprint: str
    evidence_fingerprint: str

    def document(self) -> dict[str, object]:
        """Return one strict JSON-compatible lookup record."""
        return {
            "search_record_id": self.search_record_id,
            "scope_id": self.scope_id,
            "legal_location_ids": list(self.legal_location_ids),
            "serving_payload_fingerprint": self.serving_payload_fingerprint,
            "rendered_fingerprint": self.rendered_fingerprint,
            "authority_note_fingerprint": self.authority_note_fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HKEXSearchRecordLineage:
    """One typed forward edge group with complete evidence."""

    lineage_type: HKEXSearchRecordLineageType
    predecessor_ids: tuple[str, ...]
    successor_ids: tuple[str, ...]
    evidence_fingerprint: str

    def document(self) -> dict[str, object]:
        """Return one strict JSON-compatible lineage edge."""
        return {
            "lineage_type": self.lineage_type.value,
            "predecessor_ids": list(self.predecessor_ids),
            "successor_ids": list(self.successor_ids),
            "evidence_fingerprint": self.evidence_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HKEXIdentityFacts:
    """Source-neutral immutable-record, lookup, and lineage facts."""

    identity_requests: tuple[HKEXRecordIdentityRequest, ...]
    desired_records: tuple[HKEXIdentityLookupRecord, ...]
    lookup_entries: tuple[HKEXIdentityLookupRecord, ...]
    lineage_edges: tuple[HKEXSearchRecordLineage, ...]
    existing_record_ids: tuple[str, ...]
    proposed_record_ids: tuple[str, ...]
    continuity_request: HKEXComponentContinuityRequest | None
    presentation_only_change: bool
    traceability_changed: bool
    optional_chinese_changed: bool
    optional_chinese_defect: bool
    cached_embedding_text_contract_match: bool


@dataclass(frozen=True, slots=True)
class HKEXIdentityDecision:
    """Complete effect-free identity/lookup/lineage consequence."""

    outcome: HKEXIdentityDecisionOutcome
    reason: HKEXIdentityDecisionReason
    record_action: HKEXIdentityRecordAction
    traceability_action: HKEXIdentityTraceabilityAction
    identity_consequences: tuple[str, ...]
    selected_search_record_ids: tuple[str, ...]
    predecessor_search_record_ids: tuple[str, ...]
    register_allocation_count: int
    board_separation_valid: bool
    lookup_valid: bool
    lineage_valid: bool
    traceability_revision_required: bool
    cached_embedding_reuse_permitted: bool
    quarantine_required: bool
    violation_codes: tuple[str, ...]

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return one strict effect-free identity decision."""
        _text(case_id)
        return {
            "schema_id": "asklegal.hk-regulatory.identity-decision-result",
            "schema_version": HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_IDENTITY_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "record_action": self.record_action.value,
            "traceability_action": self.traceability_action.value,
            "identity_consequences": list(self.identity_consequences),
            "selected_search_record_ids": list(self.selected_search_record_ids),
            "predecessor_search_record_ids": list(self.predecessor_search_record_ids),
            "register_allocation_count": self.register_allocation_count,
            "board_separation_valid": self.board_separation_valid,
            "lookup_valid": self.lookup_valid,
            "lineage_valid": self.lineage_valid,
            "traceability_revision_required": self.traceability_revision_required,
            "cached_embedding_reuse_permitted": self.cached_embedding_reuse_permitted,
            "quarantine_required": self.quarantine_required,
            "violation_codes": list(self.violation_codes),
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "deployment_authorized": False,
            "external_effects": "NONE",
        }


@dataclass(frozen=True, slots=True)
class HKEXIdentityDecisionCase:
    """One strict immutable-identity conformance envelope."""

    case_id: str
    primary_coverage_cell_id: str
    pair_memberships: tuple[HKEXIdentityPairMembership, ...]
    assertion_scope: HKEXIdentityAssertionScope
    contract_bindings: tuple[HKEXIdentityContractBinding, ...]
    evidence_packet: HKEXIdentityEvidencePacket
    package_fingerprint: str
    title: str
    purpose: str
    expected_decision: HKEXIdentityDecision
    facts: HKEXIdentityFacts


@dataclass(frozen=True, slots=True)
class HKEXIdentityDecisionReport:
    """Complete expected-versus-observed identity report."""

    case_id: str
    assertion_scope: HKEXIdentityAssertionScope
    observed_decision: HKEXIdentityDecision
    expected_decision: HKEXIdentityDecision
    conformance_status: str

    def document(self) -> dict[str, object]:
        """Return one strict effect-free conformance report."""
        return {
            "schema_id": "asklegal.hk-regulatory.identity-decision-report",
            "schema_version": HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_IDENTITY_DECISION_RULE_ID,
            "case_id": self.case_id,
            "assertion_scope": self.assertion_scope.value,
            "observed_decision": self.observed_decision.document(case_id=self.case_id),
            "expected_decision": self.expected_decision.document(case_id=self.case_id),
            "conformance_status": self.conformance_status,
            "source_authorized": False,
            "provider_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "deployment_authorized": False,
            "external_effects": "NONE",
        }


@dataclass(frozen=True, slots=True)
class _IdentityEvaluation:
    decisions: tuple[HKEXRecordIdentityDecision, ...]
    continuity: HKEXComponentContinuityDecision | None
    lookup_violations: tuple[str, ...]
    lineage_violations: tuple[str, ...]
    board_separation_valid: bool
    facts: HKEXIdentityFacts

    @property
    def violations(self) -> tuple[str, ...]:
        return tuple(sorted((*self.lookup_violations, *self.lineage_violations)))


@dataclass(frozen=True, slots=True)
class _CaseHeader:
    case_id: str
    primary_cell_id: str
    pairs: tuple[HKEXIdentityPairMembership, ...]
    scope: HKEXIdentityAssertionScope
    bindings: tuple[HKEXIdentityContractBinding, ...]
    package_fingerprint: str


class _SyntheticCodepointCounter:
    profile_id = _SYNTHETIC_PROFILE_ID
    profile_fingerprint = _SYNTHETIC_PROFILE_FINGERPRINT
    tokenizer_id = _SYNTHETIC_TOKENIZER_ID

    def count(self, text: str) -> int:
        return len(text)


def hkex_identity_decision_case_from_document(document: object) -> HKEXIdentityDecisionCase:
    """Strictly decode and fingerprint one permanent identity case."""
    root = _object(_checked(document))
    _exact_keys(root, _CASE_FIELDS)
    header = _case_header(root)
    _validate_declarations(root, header.bindings)
    facts = _facts(root["facts"])
    packet = _packet(root["evidence_packet"], facts)
    expected = _decision_from_document(root["expected_decision"], header.case_id)
    _validate_case_fingerprint(root)
    return HKEXIdentityDecisionCase(
        header.case_id,
        header.primary_cell_id,
        header.pairs,
        header.scope,
        header.bindings,
        packet,
        header.package_fingerprint,
        _text(root["title"]),
        _text(root["purpose"]),
        expected,
        facts,
    )


def decide_hkex_identity_case(case: HKEXIdentityDecisionCase) -> HKEXIdentityDecision:
    """Evaluate accepted identity/continuity contracts and immutable state, never case ID."""
    if type(case) is not HKEXIdentityDecisionCase:
        _fail()
    decisions = tuple(
        decide_hkex_record_identity(request, _SyntheticCodepointCounter())
        for request in case.facts.identity_requests
    )
    continuity = (
        None
        if case.facts.continuity_request is None
        else decide_hkex_component_continuity(case.facts.continuity_request)
    )
    lookup_violations = _lookup_violations(case.facts)
    lineage_violations = _lineage_violations(case.facts)
    board_separation = _board_separation(decisions, case.facts)
    evaluation = _IdentityEvaluation(
        decisions,
        continuity,
        lookup_violations,
        lineage_violations,
        board_separation,
        case.facts,
    )
    outcome, reason, action, traceability = _scope_result(case.assertion_scope, evaluation)
    selected = tuple(
        sorted(
            (
                item.selected_search_record_id
                for item in decisions
                if item.selected_search_record_id is not None
            ),
            key=str.encode,
        )
    )
    predecessors = tuple(
        sorted(
            {record_id for item in decisions for record_id in item.predecessor_search_record_ids},
            key=str.encode,
        )
    )
    return HKEXIdentityDecision(
        outcome,
        reason,
        action,
        traceability,
        tuple(item.consequence.value for item in decisions),
        selected,
        predecessors,
        sum(item.register_allocation_required for item in decisions),
        board_separation,
        not lookup_violations,
        not lineage_violations,
        traceability is HKEXIdentityTraceabilityAction.REVISE,
        case.assertion_scope is HKEXIdentityAssertionScope.AUTHORITY_NOTE_CHANGE
        and case.facts.cached_embedding_text_contract_match,
        outcome is HKEXIdentityDecisionOutcome.QUARANTINE,
        evaluation.violations,
    )


def run_hkex_identity_case(case: HKEXIdentityDecisionCase) -> HKEXIdentityDecisionReport:
    """Compare the fact-derived result with complete independently frozen truth."""
    observed = decide_hkex_identity_case(case)
    return HKEXIdentityDecisionReport(
        case.case_id,
        case.assertion_scope,
        observed,
        case.expected_decision,
        "PASS" if observed == case.expected_decision else "FAIL",
    )


def _board_separation(
    decisions: tuple[HKEXRecordIdentityDecision, ...], facts: HKEXIdentityFacts
) -> bool:
    if len(decisions) != _BOARD_PAIR_COUNT or len(facts.identity_requests) != _BOARD_PAIR_COUNT:
        return False
    payloads = tuple(item.candidate_serving_payload_fingerprint for item in decisions)
    wordings = tuple(
        tuple(
            unit.text
            for unit in request.construction.tree.source_units
            if unit.role is HKEXSourceUnitRole.PRIMARY
        )
        for request in facts.identity_requests
    )
    scopes = tuple(item.construction.tree.scope_id for item in facts.identity_requests)
    locations = tuple(item.legal_location_ids for item in facts.identity_requests)
    return (
        payloads[0] is not None
        and payloads[1] is not None
        and wordings[0] == wordings[1]
        and len(set(scopes)) == _BOARD_PAIR_COUNT
        and len(set(locations)) == _BOARD_PAIR_COUNT
        and all(
            item.consequence is HKEXRecordIdentityConsequence.REQUIRE_NEW_INITIAL
            for item in decisions
        )
    )


def _lookup_violations(facts: HKEXIdentityFacts) -> tuple[str, ...]:
    desired = facts.desired_records
    entries = facts.lookup_entries
    violations: list[str] = []
    desired_ids = tuple(item.search_record_id for item in desired)
    entry_ids = tuple(item.search_record_id for item in entries)
    if _duplicates(desired_ids) or _duplicates(entry_ids):
        violations.append("LOOKUP_DUPLICATE")
    desired_by_id = {item.search_record_id: item for item in desired}
    entries_by_id = {item.search_record_id: item for item in entries}
    if set(desired_by_id) - set(entries_by_id):
        violations.append("LOOKUP_MISSING")
    if set(entries_by_id) - set(desired_by_id):
        violations.append("LOOKUP_ORPHAN")
    for record_id in desired_by_id.keys() & entries_by_id.keys():
        expected = desired_by_id[record_id]
        observed = entries_by_id[record_id]
        if expected.scope_id != observed.scope_id or (
            expected.legal_location_ids != observed.legal_location_ids
        ):
            violations.append("LOOKUP_OWNERSHIP_MISMATCH")
        elif expected != observed:
            violations.append("LOOKUP_FINGERPRINT_MISMATCH")
    return tuple(sorted(set(violations)))


def _lineage_cardinality_violations(edge: HKEXSearchRecordLineage) -> list[str]:
    expected = {
        HKEXSearchRecordLineageType.ONE_TO_ONE: (1, 1),
        HKEXSearchRecordLineageType.ONE_TO_MANY: (1, None),
        HKEXSearchRecordLineageType.MANY_TO_ONE: (None, 1),
    }[edge.lineage_type]
    predecessor_count, successor_count = expected
    violations: list[str] = []
    if predecessor_count is not None and len(edge.predecessor_ids) != predecessor_count:
        violations.append("LINEAGE_CARDINALITY")
    if successor_count is not None and len(edge.successor_ids) != successor_count:
        violations.append("LINEAGE_CARDINALITY")
    if edge.lineage_type is HKEXSearchRecordLineageType.ONE_TO_MANY and (
        len(edge.successor_ids) < _BRANCHING_MEMBER_MINIMUM
    ):
        violations.append("LINEAGE_CARDINALITY")
    if edge.lineage_type is HKEXSearchRecordLineageType.MANY_TO_ONE and (
        len(edge.predecessor_ids) < _BRANCHING_MEMBER_MINIMUM
    ):
        violations.append("LINEAGE_CARDINALITY")
    return violations


def _lineage_membership_violations(
    edge: HKEXSearchRecordLineage,
    *,
    existing_record_ids: tuple[str, ...],
    proposed_record_ids: tuple[str, ...],
) -> list[str]:
    violations: list[str] = []
    if set(edge.predecessor_ids) & set(edge.successor_ids):
        violations.append("LINEAGE_SELF_OR_BACKWARD")
    if not set(edge.predecessor_ids).issubset(existing_record_ids):
        violations.append("LINEAGE_UNKNOWN_PREDECESSOR")
    if not set(edge.successor_ids).issubset(proposed_record_ids):
        violations.append("LINEAGE_UNKNOWN_SUCCESSOR")
    return violations


def _lineage_violations(facts: HKEXIdentityFacts) -> tuple[str, ...]:
    violations: list[str] = []
    if _duplicates(facts.existing_record_ids) or _duplicates(facts.proposed_record_ids):
        violations.append("RECORD_ID_DUPLICATE")
    if set(facts.existing_record_ids) & set(facts.proposed_record_ids):
        violations.append("RECORD_ID_COLLISION")
    adjacency: dict[str, set[str]] = {}
    for edge in facts.lineage_edges:
        violations.extend(_lineage_cardinality_violations(edge))
        violations.extend(
            _lineage_membership_violations(
                edge,
                existing_record_ids=facts.existing_record_ids,
                proposed_record_ids=facts.proposed_record_ids,
            )
        )
        for predecessor in edge.predecessor_ids:
            adjacency.setdefault(predecessor, set()).update(edge.successor_ids)
    if _has_cycle(adjacency):
        violations.append("LINEAGE_CYCLE")
    return tuple(sorted(set(violations)))


def _has_cycle(adjacency: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for successor in adjacency.get(node, ()):
            if visit(successor):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in adjacency)


def _single_consequence(
    evaluation: _IdentityEvaluation, consequence: HKEXRecordIdentityConsequence
) -> bool:
    return len(evaluation.decisions) == 1 and evaluation.decisions[0].consequence is consequence


def _changed(evaluation: _IdentityEvaluation, change: HKEXRecordChange, *, count: int = 1) -> bool:
    return (
        len(evaluation.decisions) == count
        and len(evaluation.facts.identity_requests) == count
        and all(item.change is change for item in evaluation.facts.identity_requests)
        and all(
            item.consequence is HKEXRecordIdentityConsequence.REQUIRE_NEW_FORWARD_SUCCESSOR
            for item in evaluation.decisions
        )
    )


def _lookup_exact(evaluation: _IdentityEvaluation) -> bool:
    return (
        bool(evaluation.facts.desired_records)
        and not evaluation.lookup_violations
        and evaluation.facts.desired_records == evaluation.facts.lookup_entries
    )


def _lineage_types(
    evaluation: _IdentityEvaluation, expected: tuple[HKEXSearchRecordLineageType, ...]
) -> bool:
    return (
        not evaluation.lineage_violations
        and tuple(item.lineage_type for item in evaluation.facts.lineage_edges) == expected
    )


_ScopeResult = tuple[
    HKEXIdentityDecisionOutcome,
    HKEXIdentityDecisionReason,
    HKEXIdentityRecordAction,
    HKEXIdentityTraceabilityAction,
]
_ScopeValidator = Callable[[_IdentityEvaluation], bool]


_SCOPE_RESULTS: dict[HKEXIdentityAssertionScope, _ScopeResult] = {
    HKEXIdentityAssertionScope.BOARD_SEPARATION: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.SEPARATE_BOARD_IDENTITIES,
        HKEXIdentityRecordAction.SEPARATE_INITIALS,
        HKEXIdentityTraceabilityAction.VALIDATE,
    ),
    HKEXIdentityAssertionScope.EXACT_REUSE: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.EXACT_RECORD_REUSED,
        HKEXIdentityRecordAction.REUSE,
        HKEXIdentityTraceabilityAction.NONE,
    ),
    HKEXIdentityAssertionScope.RESELECTION: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.PRESERVED_RECORD_RESELECTED,
        HKEXIdentityRecordAction.RESELECT,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.PRIMARY_TEXT_CHANGE: (
        HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
        HKEXIdentityDecisionReason.PRIMARY_TEXT_SUCCESSOR_REQUIRED,
        HKEXIdentityRecordAction.REQUIRE_NEW,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.APPLICABILITY_CHANGE: (
        HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
        HKEXIdentityDecisionReason.APPLICABILITY_SUCCESSOR_REQUIRED,
        HKEXIdentityRecordAction.REQUIRE_NEW,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.GOVERNING_DEPENDENCY_CHANGE: (
        HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
        HKEXIdentityDecisionReason.GOVERNING_DEPENDENCY_SUCCESSOR_REQUIRED,
        HKEXIdentityRecordAction.REQUIRE_NEW,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.REFERENCED_LOCATION_CHANGE: (
        HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
        HKEXIdentityDecisionReason.REFERENCED_LOCATION_SUCCESSOR_REQUIRED,
        HKEXIdentityRecordAction.REQUIRE_NEW,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.STRUCTURED_PROJECTION_CHANGE: (
        HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
        HKEXIdentityDecisionReason.STRUCTURED_PROJECTION_SUCCESSOR_REQUIRED,
        HKEXIdentityRecordAction.REQUIRE_NEW,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.PARTITION_CHANGE: (
        HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
        HKEXIdentityDecisionReason.PARTITION_SUCCESSORS_REQUIRED,
        HKEXIdentityRecordAction.REQUIRE_NEW,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.AUTHORITY_NOTE_CHANGE: (
        HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
        HKEXIdentityDecisionReason.AUTHORITY_NOTE_SUCCESSOR_REQUIRED,
        HKEXIdentityRecordAction.REQUIRE_NEW,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.URL_MOVE: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.URL_MOVE_REUSES_RECORD,
        HKEXIdentityRecordAction.REUSE,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.PAGE_REFLOW: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.PAGE_REFLOW_REUSES_RECORD,
        HKEXIdentityRecordAction.REUSE,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.OPTIONAL_CHINESE_CHANGE: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.OPTIONAL_CHINESE_CHANGE_REUSES_RECORD,
        HKEXIdentityRecordAction.REUSE,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.TRACEABILITY_ONLY: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.TRACEABILITY_REVISION_ONLY,
        HKEXIdentityRecordAction.NO_ID_CHANGE,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.CHINESE_DEFECT: (
        HKEXIdentityDecisionOutcome.BLOCK,
        HKEXIdentityDecisionReason.ENGLISH_SUPPORT_BLOCKED,
        HKEXIdentityRecordAction.BLOCK,
        HKEXIdentityTraceabilityAction.BLOCK,
    ),
    HKEXIdentityAssertionScope.LOOKUP_VALID: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.LOOKUP_ENTRY_VALID,
        HKEXIdentityRecordAction.VALIDATE_ONLY,
        HKEXIdentityTraceabilityAction.VALIDATE,
    ),
    HKEXIdentityAssertionScope.LOOKUP_INCOMPLETE: (
        HKEXIdentityDecisionOutcome.BLOCK,
        HKEXIdentityDecisionReason.LOOKUP_INCOMPLETE,
        HKEXIdentityRecordAction.BLOCK,
        HKEXIdentityTraceabilityAction.BLOCK,
    ),
    HKEXIdentityAssertionScope.LOOKUP_WRONG_OWNER: (
        HKEXIdentityDecisionOutcome.BLOCK,
        HKEXIdentityDecisionReason.LOOKUP_OWNERSHIP_MISMATCH,
        HKEXIdentityRecordAction.BLOCK,
        HKEXIdentityTraceabilityAction.BLOCK,
    ),
    HKEXIdentityAssertionScope.LINEAGE_ONE_TO_ONE: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.ONE_TO_ONE_LINEAGE_VALID,
        HKEXIdentityRecordAction.VALIDATE_ONLY,
        HKEXIdentityTraceabilityAction.VALIDATE,
    ),
    HKEXIdentityAssertionScope.LINEAGE_SPLIT_MERGE: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.SPLIT_MERGE_LINEAGE_VALID,
        HKEXIdentityRecordAction.VALIDATE_ONLY,
        HKEXIdentityTraceabilityAction.VALIDATE,
    ),
    HKEXIdentityAssertionScope.LINEAGE_CYCLE: (
        HKEXIdentityDecisionOutcome.BLOCK,
        HKEXIdentityDecisionReason.LINEAGE_REJECTED,
        HKEXIdentityRecordAction.BLOCK,
        HKEXIdentityTraceabilityAction.BLOCK,
    ),
    HKEXIdentityAssertionScope.PROVED_CONTINUITY: (
        HKEXIdentityDecisionOutcome.PASS,
        HKEXIdentityDecisionReason.OFFICIAL_CONTINUITY_PROVED,
        HKEXIdentityRecordAction.NO_ID_CHANGE,
        HKEXIdentityTraceabilityAction.REVISE,
    ),
    HKEXIdentityAssertionScope.SIMILARITY_ONLY: (
        HKEXIdentityDecisionOutcome.QUARANTINE,
        HKEXIdentityDecisionReason.SIMILARITY_CONTINUITY_QUARANTINED,
        HKEXIdentityRecordAction.QUARANTINE,
        HKEXIdentityTraceabilityAction.BLOCK,
    ),
    HKEXIdentityAssertionScope.LOOKUP_FINGERPRINT_MISMATCH: (
        HKEXIdentityDecisionOutcome.BLOCK,
        HKEXIdentityDecisionReason.LOOKUP_FINGERPRINT_MISMATCH,
        HKEXIdentityRecordAction.BLOCK,
        HKEXIdentityTraceabilityAction.BLOCK,
    ),
}


_SCOPE_VALIDATORS: dict[HKEXIdentityAssertionScope, _ScopeValidator] = {
    HKEXIdentityAssertionScope.BOARD_SEPARATION: lambda item: item.board_separation_valid,
    HKEXIdentityAssertionScope.EXACT_REUSE: lambda item: _single_consequence(
        item, HKEXRecordIdentityConsequence.PRESERVE_SELECTED
    ),
    HKEXIdentityAssertionScope.RESELECTION: lambda item: (
        _single_consequence(item, HKEXRecordIdentityConsequence.RESELECT_PRESERVED)
        and not item.decisions[0].predecessor_search_record_ids
    ),
    HKEXIdentityAssertionScope.PRIMARY_TEXT_CHANGE: lambda item: _changed(
        item, HKEXRecordChange.PRIMARY_TEXT_CHANGED
    ),
    HKEXIdentityAssertionScope.APPLICABILITY_CHANGE: lambda item: _changed(
        item, HKEXRecordChange.APPLICABILITY_CONTEXT_CHANGED
    ),
    HKEXIdentityAssertionScope.GOVERNING_DEPENDENCY_CHANGE: lambda item: _changed(
        item, HKEXRecordChange.GOVERNING_CONTEXT_CHANGED
    ),
    HKEXIdentityAssertionScope.REFERENCED_LOCATION_CHANGE: lambda item: _changed(
        item, HKEXRecordChange.REFERENCED_LOCATION_CHANGED
    ),
    HKEXIdentityAssertionScope.STRUCTURED_PROJECTION_CHANGE: lambda item: _changed(
        item, HKEXRecordChange.STRUCTURED_PROJECTION_CHANGED
    ),
    HKEXIdentityAssertionScope.PARTITION_CHANGE: lambda item: _changed(
        item, HKEXRecordChange.PARTITION_CHANGED, count=2
    ),
    HKEXIdentityAssertionScope.AUTHORITY_NOTE_CHANGE: lambda item: (
        _changed(item, HKEXRecordChange.AUTHORITY_NOTE_CHANGED)
        and item.facts.cached_embedding_text_contract_match
    ),
    HKEXIdentityAssertionScope.URL_MOVE: lambda item: (
        _single_consequence(item, HKEXRecordIdentityConsequence.PRESERVE_SELECTED)
        and item.facts.traceability_changed
    ),
    HKEXIdentityAssertionScope.PAGE_REFLOW: lambda item: (
        _single_consequence(item, HKEXRecordIdentityConsequence.PRESERVE_SELECTED)
        and item.facts.presentation_only_change
    ),
    HKEXIdentityAssertionScope.OPTIONAL_CHINESE_CHANGE: lambda item: (
        _single_consequence(item, HKEXRecordIdentityConsequence.PRESERVE_SELECTED)
        and item.facts.optional_chinese_changed
        and not item.facts.optional_chinese_defect
    ),
    HKEXIdentityAssertionScope.TRACEABILITY_ONLY: lambda item: (
        _single_consequence(item, HKEXRecordIdentityConsequence.PRESERVE_SELECTED)
        and item.facts.traceability_changed
    ),
    HKEXIdentityAssertionScope.CHINESE_DEFECT: lambda item: (
        _single_consequence(item, HKEXRecordIdentityConsequence.BLOCK)
        and item.facts.optional_chinese_defect
    ),
    HKEXIdentityAssertionScope.LOOKUP_VALID: _lookup_exact,
    HKEXIdentityAssertionScope.LOOKUP_INCOMPLETE: lambda item: bool(
        set(item.lookup_violations) & {"LOOKUP_MISSING", "LOOKUP_DUPLICATE", "LOOKUP_ORPHAN"}
    ),
    HKEXIdentityAssertionScope.LOOKUP_WRONG_OWNER: lambda item: (
        item.lookup_violations == ("LOOKUP_OWNERSHIP_MISMATCH",)
    ),
    HKEXIdentityAssertionScope.LINEAGE_ONE_TO_ONE: lambda item: _lineage_types(
        item, (HKEXSearchRecordLineageType.ONE_TO_ONE,)
    ),
    HKEXIdentityAssertionScope.LINEAGE_SPLIT_MERGE: lambda item: _lineage_types(
        item, (HKEXSearchRecordLineageType.ONE_TO_MANY, HKEXSearchRecordLineageType.MANY_TO_ONE)
    ),
    HKEXIdentityAssertionScope.LINEAGE_CYCLE: lambda item: (
        "LINEAGE_CYCLE" in item.lineage_violations
        or "RECORD_ID_COLLISION" in item.lineage_violations
    ),
    HKEXIdentityAssertionScope.PROVED_CONTINUITY: lambda item: (
        item.continuity is not None
        and item.continuity.identity_consequence is HKEXIdentityConsequence.PRESERVE_EXISTING
        and item.continuity.lineage_type is HKEXComponentLineageType.RENUMBER
    ),
    HKEXIdentityAssertionScope.SIMILARITY_ONLY: lambda item: (
        item.continuity is not None
        and item.continuity.identity_consequence is HKEXIdentityConsequence.QUARANTINE
        and item.facts.continuity_request is not None
        and item.facts.continuity_request.support is HKEXContinuitySupport.SIMILARITY_OR_ALIAS_ONLY
    ),
    HKEXIdentityAssertionScope.LOOKUP_FINGERPRINT_MISMATCH: lambda item: (
        item.lookup_violations == ("LOOKUP_FINGERPRINT_MISMATCH",)
    ),
}


def _scope_result(
    scope: HKEXIdentityAssertionScope, evaluation: _IdentityEvaluation
) -> _ScopeResult:
    if not _SCOPE_VALIDATORS[scope](evaluation):
        _fail(HKEXIdentityDecisionErrorCode.IDENTITY)
    return _SCOPE_RESULTS[scope]


_FACT_FIELDS = {
    "identity_requests",
    "desired_records",
    "lookup_entries",
    "lineage_edges",
    "existing_record_ids",
    "proposed_record_ids",
    "continuity_request",
    "presentation_only_change",
    "traceability_changed",
    "optional_chinese_changed",
    "optional_chinese_defect",
    "cached_embedding_text_contract_match",
}

_CASE_FIELDS = {
    "schema_id",
    "schema_version",
    "package_contract_version",
    "case_id",
    "suite_layer",
    "primary_checkpoint",
    "frozen",
    "synthetic_evidence_class",
    "contract_bindings",
    "synthetic_cutoff",
    "scope_id",
    "prior_state",
    "primary_coverage_cell_ids",
    "secondary_coverage_cell_ids",
    "pair_memberships",
    "declared_input_inventory",
    "declared_reference_inventory",
    "declared_expected_inventory",
    "assertion_scope",
    "required_result_dimensions",
    "evidence_packet_fields",
    "supporting_evidence_ranges",
    "rule_trace",
    "established_facts",
    "unresolved_facts",
    "permitted_equivalent_results",
    "critical_error_codes",
    "package_fingerprint",
    "title",
    "purpose",
    "expected_decision",
    "evidence_packet",
    "facts",
    "case_fingerprint",
}

_DECISION_FIELDS = {
    "schema_id",
    "schema_version",
    "rule_id",
    "case_id",
    "outcome",
    "reason",
    "record_action",
    "traceability_action",
    "identity_consequences",
    "selected_search_record_ids",
    "predecessor_search_record_ids",
    "register_allocation_count",
    "board_separation_valid",
    "lookup_valid",
    "lineage_valid",
    "traceability_revision_required",
    "cached_embedding_reuse_permitted",
    "quarantine_required",
    "violation_codes",
    "search_record_authorized",
    "embedding_authorized",
    "release_authorized",
    "serving_authorized",
    "deployment_authorized",
    "external_effects",
}


def _case_header(root: dict[str, JsonValue]) -> _CaseHeader:
    _constant(root["schema_id"], "asklegal.hk-regulatory.identity-decision-case")
    _constant(root["schema_version"], HKEX_IDENTITY_DECISION_CONTRACT_VERSION)
    _constant(root["package_contract_version"], "1.0.0")
    case_id = _pattern(root["case_id"], _CASE_PATTERN)
    suffix = case_id.rsplit("-", maxsplit=1)[1]
    _constant(root["suite_layer"], "DECISION_TO_ARTIFACT")
    _constant(root["primary_checkpoint"], "IDENTITY_LINEAGE")
    _true(root["frozen"])
    _constant(root["synthetic_evidence_class"], "SYNTHETIC_NO_REAL_AUTHORITY")
    _constant(root["synthetic_cutoff"], "2026-08-24T00:00:00Z")
    _constant(root["scope_id"], "HKEX_CROSS_BOARD")
    _constant(root["prior_state"], "SYNTHETIC_ACCEPTED_PREDECESSOR")
    primary = _strings(root["primary_coverage_cell_ids"])
    if primary != (f"HKREG-COV-DIDN-{suffix}",):
        _fail(HKEXIdentityDecisionErrorCode.IDENTITY)
    bindings = _bindings(root["contract_bindings"])
    package_fingerprint = _fingerprint(root["package_fingerprint"])
    _validate_bindings(bindings, package_fingerprint)
    return _CaseHeader(
        case_id,
        primary[0],
        _pairs(root["pair_memberships"], case_id),
        _enum(root["assertion_scope"], HKEXIdentityAssertionScope),
        bindings,
        package_fingerprint,
    )


def _validate_declarations(
    root: dict[str, JsonValue], bindings: tuple[HKEXIdentityContractBinding, ...]
) -> None:
    if _strings(root["secondary_coverage_cell_ids"], empty=True):
        _fail()
    if _strings(root["declared_input_inventory"]) != ("identity-evidence",):
        _fail()
    if _strings(root["declared_reference_inventory"]) != tuple(
        item.contract_id for item in bindings
    ):
        _fail()
    if _strings(root["declared_expected_inventory"]) != ("IDENTITY_DECISION_REPORT",):
        _fail()
    if _strings(root["required_result_dimensions"]) != (
        "BOARD_OWNERSHIP",
        "FORBIDDEN_EFFECTS",
        "IMMUTABLE_IDENTITY",
        "LINEAGE",
        "TRACEABILITY_LOOKUP",
    ):
        _fail()
    if _strings(root["evidence_packet_fields"]) != tuple(sorted(_FACT_FIELDS)):
        _fail()
    _nonempty_sorted(root["supporting_evidence_ranges"])
    _nonempty_sorted(root["rule_trace"])
    _nonempty_sorted(root["established_facts"])
    _sorted_strings(root["unresolved_facts"])
    if _array(root["permitted_equivalent_results"]):
        _fail()
    _sorted_strings(root["critical_error_codes"])


def _facts(value: JsonValue) -> HKEXIdentityFacts:
    root = _object(value)
    _exact_keys(root, _FACT_FIELDS)
    requests = tuple(
        hkex_record_identity_request_from_document(item)
        for item in _array(root["identity_requests"])
    )
    if len(requests) > _MAX_REQUESTS:
        _fail()
    for request in requests:
        profile = request.construction.profile
        if (profile.profile_id, profile.profile_fingerprint, profile.tokenizer_id) != (
            _SYNTHETIC_PROFILE_ID,
            _SYNTHETIC_PROFILE_FINGERPRINT,
            _SYNTHETIC_TOKENIZER_ID,
        ):
            _fail()
    desired = tuple(_lookup_record(item) for item in _array(root["desired_records"]))
    lookup = tuple(_lookup_record(item) for item in _array(root["lookup_entries"]))
    lineage = tuple(_lineage(item) for item in _array(root["lineage_edges"]))
    continuity_raw = root["continuity_request"]
    continuity = (
        None
        if continuity_raw is None
        else hkex_component_continuity_request_from_document(_object(continuity_raw))
    )
    return HKEXIdentityFacts(
        requests,
        desired,
        lookup,
        lineage,
        _record_ids(root["existing_record_ids"]),
        _record_ids(root["proposed_record_ids"]),
        continuity,
        _boolean(root["presentation_only_change"]),
        _boolean(root["traceability_changed"]),
        _boolean(root["optional_chinese_changed"]),
        _boolean(root["optional_chinese_defect"]),
        _boolean(root["cached_embedding_text_contract_match"]),
    )


def _lookup_record(value: JsonValue) -> HKEXIdentityLookupRecord:
    root = _object(value)
    _exact_keys(
        root,
        {
            "search_record_id",
            "scope_id",
            "legal_location_ids",
            "serving_payload_fingerprint",
            "rendered_fingerprint",
            "authority_note_fingerprint",
            "evidence_fingerprint",
        },
    )
    scope = _text(root["scope_id"])
    if scope not in HKEX_SCOPE_IDS:
        _fail()
    locations = _strings(root["legal_location_ids"])
    for location in locations:
        if fullmatch(_LOCATION_PATTERN, location) is None:
            _fail(HKEXIdentityDecisionErrorCode.IDENTITY)
    return HKEXIdentityLookupRecord(
        _pattern(root["search_record_id"], _RECORD_PATTERN),
        scope,
        locations,
        _fingerprint(root["serving_payload_fingerprint"]),
        _fingerprint(root["rendered_fingerprint"]),
        _fingerprint(root["authority_note_fingerprint"]),
        _fingerprint(root["evidence_fingerprint"]),
    )


def _lineage(value: JsonValue) -> HKEXSearchRecordLineage:
    root = _object(value)
    _exact_keys(root, {"lineage_type", "predecessor_ids", "successor_ids", "evidence_fingerprint"})
    return HKEXSearchRecordLineage(
        _enum(root["lineage_type"], HKEXSearchRecordLineageType),
        _record_ids(root["predecessor_ids"]),
        _record_ids(root["successor_ids"]),
        _fingerprint(root["evidence_fingerprint"]),
    )


def _decision_from_document(value: JsonValue, case_id: str) -> HKEXIdentityDecision:
    root = _object(value)
    _exact_keys(root, _DECISION_FIELDS)
    _constant(root["schema_id"], "asklegal.hk-regulatory.identity-decision-result")
    _constant(root["schema_version"], HKEX_IDENTITY_DECISION_CONTRACT_VERSION)
    _constant(root["rule_id"], HKEX_IDENTITY_DECISION_RULE_ID)
    _constant(root["case_id"], case_id)
    for key in (
        "search_record_authorized",
        "embedding_authorized",
        "release_authorized",
        "serving_authorized",
        "deployment_authorized",
    ):
        _false(root[key])
    _constant(root["external_effects"], "NONE")
    return HKEXIdentityDecision(
        _enum(root["outcome"], HKEXIdentityDecisionOutcome),
        _enum(root["reason"], HKEXIdentityDecisionReason),
        _enum(root["record_action"], HKEXIdentityRecordAction),
        _enum(root["traceability_action"], HKEXIdentityTraceabilityAction),
        tuple(_text(item) for item in _array(root["identity_consequences"])),
        _record_ids(root["selected_search_record_ids"]),
        _record_ids(root["predecessor_search_record_ids"]),
        _nonnegative_integer(root["register_allocation_count"]),
        _boolean(root["board_separation_valid"]),
        _boolean(root["lookup_valid"]),
        _boolean(root["lineage_valid"]),
        _boolean(root["traceability_revision_required"]),
        _boolean(root["cached_embedding_reuse_permitted"]),
        _boolean(root["quarantine_required"]),
        _strings(root["violation_codes"], empty=True),
    )


def _bindings(value: JsonValue) -> tuple[HKEXIdentityContractBinding, ...]:
    results: list[HKEXIdentityContractBinding] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"contract_id", "version", "fingerprint"})
        results.append(
            HKEXIdentityContractBinding(
                _text(root["contract_id"]),
                _text(root["version"]),
                _fingerprint(root["fingerprint"]),
            )
        )
    if (
        len(results) != _CONTRACT_BINDING_COUNT
        or len({item.contract_id for item in results}) != _CONTRACT_BINDING_COUNT
    ):
        _fail()
    return tuple(results)


def _validate_bindings(
    bindings: tuple[HKEXIdentityContractBinding, ...], package_fingerprint: str
) -> None:
    def seed(contract_id: str, version: str, rule_id: str) -> str:
        return fingerprint(
            checked_json_value(
                {"contract_id": contract_id, "contract_version": version, "rule_id": rule_id}
            )
        )

    expected = (
        ("asklegal.hk-regulatory.conformance-universe", "1.0.0", package_fingerprint),
        (
            "asklegal.hk-regulatory.english-record",
            HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            seed(
                "asklegal.hk-regulatory.english-record",
                HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
                HKEX_ENGLISH_RECORD_RULE_ID,
            ),
        ),
        (
            "asklegal.hk-regulatory.record-identity",
            HKEX_RECORD_IDENTITY_CONTRACT_VERSION,
            seed(
                "asklegal.hk-regulatory.record-identity",
                HKEX_RECORD_IDENTITY_CONTRACT_VERSION,
                HKEX_RECORD_IDENTITY_RULE_ID,
            ),
        ),
        (
            "asklegal.hk-regulatory.component-continuity",
            HKEX_COMPONENT_CONTINUITY_CONTRACT_VERSION,
            seed(
                "asklegal.hk-regulatory.component-continuity",
                HKEX_COMPONENT_CONTINUITY_CONTRACT_VERSION,
                HKEX_COMPONENT_CONTINUITY_RULE_ID,
            ),
        ),
        (
            "asklegal.hk-regulatory.identity-decision-case",
            HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
            seed(
                "asklegal.hk-regulatory.identity-decision-case",
                HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
                HKEX_IDENTITY_DECISION_RULE_ID,
            ),
        ),
    )
    if tuple((item.contract_id, item.version, item.fingerprint) for item in bindings) != expected:
        _fail()


def _pairs(value: JsonValue, case_id: str) -> tuple[HKEXIdentityPairMembership, ...]:
    results: list[HKEXIdentityPairMembership] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"pair_id", "role"})
        pair_id = _pattern(root["pair_id"], r"HKREG-PAIR-0(46|47|48|49)")
        role = _text(root["role"])
        if role not in {"POSITIVE", "NEAR_MISS"}:
            _fail()
        results.append(HKEXIdentityPairMembership(pair_id, role))
    if tuple((item.pair_id, item.role) for item in results) != _EXPECTED_PAIRS.get(case_id, ()):
        _fail(HKEXIdentityDecisionErrorCode.IDENTITY)
    return tuple(results)


def _packet(value: JsonValue, facts: HKEXIdentityFacts) -> HKEXIdentityEvidencePacket:
    root = _object(value)
    _exact_keys(root, {"slot_id", "state", "path", "role", "media_type", "content_fingerprint"})
    packet = HKEXIdentityEvidencePacket(
        _text(root["slot_id"]),
        _text(root["state"]),
        _text(root["path"]),
        _text(root["role"]),
        _text(root["media_type"]),
        _fingerprint(root["content_fingerprint"]),
    )
    if (packet.slot_id, packet.state, packet.role, packet.media_type) != (
        "identity-evidence",
        "AVAILABLE",
        "ORDINARY",
        "application/json",
    ):
        _fail()
    if packet.content_fingerprint != fingerprint(checked_json_value(_facts_document(facts))):
        _fail(HKEXIdentityDecisionErrorCode.FINGERPRINT)
    return packet


def _facts_document(facts: HKEXIdentityFacts) -> dict[str, object]:
    return {
        "identity_requests": [item.document() for item in facts.identity_requests],
        "desired_records": [item.document() for item in facts.desired_records],
        "lookup_entries": [item.document() for item in facts.lookup_entries],
        "lineage_edges": [item.document() for item in facts.lineage_edges],
        "existing_record_ids": list(facts.existing_record_ids),
        "proposed_record_ids": list(facts.proposed_record_ids),
        "continuity_request": None
        if facts.continuity_request is None
        else _continuity_document(facts.continuity_request),
        "presentation_only_change": facts.presentation_only_change,
        "traceability_changed": facts.traceability_changed,
        "optional_chinese_changed": facts.optional_chinese_changed,
        "optional_chinese_defect": facts.optional_chinese_defect,
        "cached_embedding_text_contract_match": facts.cached_embedding_text_contract_match,
    }


def _continuity_document(request: HKEXComponentContinuityRequest) -> dict[str, object]:
    return {
        "decision_id": request.decision_id,
        "cutoff": request.cutoff,
        "event": request.event.value,
        "support": request.support.value,
        "predecessors": [
            {
                "component_id": item.component_id,
                "scope_id": item.scope_id,
                "legal_location_id": item.legal_location_id,
                "aliases": list(item.aliases),
                "evidence_refs": list(item.evidence_refs),
            }
            for item in request.predecessors
        ],
        "candidates": [
            {
                "candidate_id": item.candidate_id,
                "scope_id": item.scope_id,
                "observed_locator": item.observed_locator,
                "aliases": list(item.aliases),
                "evidence_refs": list(item.evidence_refs),
            }
            for item in request.candidates
        ],
        "source_rule_id": request.source_rule_id,
        "evidence_refs": list(request.evidence_refs),
        "evidence_fingerprint": request.evidence_fingerprint,
        "legal_desk_actor": request.legal_desk_actor,
    }


def _validate_case_fingerprint(root: dict[str, JsonValue]) -> None:
    actual = _fingerprint(root["case_fingerprint"])
    projection = dict(root)
    projection.pop("case_fingerprint")
    if fingerprint(checked_json_value(projection)) != actual:
        _fail(HKEXIdentityDecisionErrorCode.FINGERPRINT)


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return tuple(duplicates)


def _checked(value: object) -> JsonValue:
    try:
        return checked_json_value(value)
    except (TypeError, ValueError) as error:
        raise HKEXIdentityDecisionError(HKEXIdentityDecisionErrorCode.CONTRACT) from error


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        _fail()
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        _fail()
    return value


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        _fail()


def _text(value: JsonValue) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        _fail()
    return value


def _pattern(value: JsonValue, pattern: str) -> str:
    text = _text(value)
    if fullmatch(pattern, text) is None:
        _fail(HKEXIdentityDecisionErrorCode.IDENTITY)
    return text


def _fingerprint(value: JsonValue) -> str:
    text = _text(value)
    if fullmatch(_FINGERPRINT_PATTERN, text) is None:
        _fail(HKEXIdentityDecisionErrorCode.FINGERPRINT)
    return text


def _strings(value: JsonValue, *, empty: bool = False) -> tuple[str, ...]:
    values = tuple(_text(item) for item in _array(value))
    if (not empty and not values) or len(set(values)) != len(values):
        _fail()
    return values


def _record_ids(value: JsonValue) -> tuple[str, ...]:
    values = _strings(value, empty=True)
    for item in values:
        if fullmatch(_RECORD_PATTERN, item) is None:
            _fail(HKEXIdentityDecisionErrorCode.IDENTITY)
    return values


def _sorted_strings(value: JsonValue) -> tuple[str, ...]:
    values = _strings(value, empty=True)
    if values != tuple(sorted(values)):
        _fail()
    return values


def _nonempty_sorted(value: JsonValue) -> tuple[str, ...]:
    values = _strings(value)
    if values != tuple(sorted(values)):
        _fail()
    return values


def _boolean(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        _fail()
    return value


def _true(value: JsonValue) -> None:
    if _boolean(value) is not True:
        _fail()


def _false(value: JsonValue) -> None:
    if _boolean(value) is not False:
        _fail()


def _nonnegative_integer(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail()
    return value


def _constant(value: JsonValue, expected: JsonValue) -> None:
    if value != expected or type(value) is not type(expected):
        _fail()


def _enum[T: StrEnum](value: JsonValue, cls: type[T]) -> T:
    try:
        return cls(_text(value))
    except ValueError as error:
        raise HKEXIdentityDecisionError(HKEXIdentityDecisionErrorCode.CONTRACT) from error


def _fail(code: HKEXIdentityDecisionErrorCode = HKEXIdentityDecisionErrorCode.CONTRACT) -> Never:
    raise HKEXIdentityDecisionError(code)


def is_hkex_identity_decision_error(error: BaseException) -> TypeIs[HKEXIdentityDecisionError]:
    """Return whether one failure is the strict permanent identity error."""
    return isinstance(error, HKEXIdentityDecisionError)
