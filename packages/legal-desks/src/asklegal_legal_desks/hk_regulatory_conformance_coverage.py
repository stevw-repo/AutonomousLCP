"""ADR 0074/0075 English source-unit coverage and board-readiness conformance."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from typing import Never, TypeIs

from asklegal_contracts import ContractViolation, fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_regulatory_english import (
    HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
    HKEX_ENGLISH_RECORD_RULE_ID,
    HKEXEnglishConstructionRequest,
    HKEXEnglishDisposition,
    HKEXSourceUnitRole,
    construct_hkex_english_request,
    hkex_english_request_from_document,
)
from .hk_regulatory_inventory import HKEX_SCOPE_IDS, HKEXBranchState

HKEX_COVERAGE_DECISION_RULE_ID = "HKREG-COVERAGE-DECISION-001"
HKEX_COVERAGE_DECISION_CONTRACT_VERSION = "1.0.0"
HKEX_COVERAGE_DECISION_CASE_COUNT = 20

_CASE_PATTERN = r"HKREG-DET-COV-(0[0-1][0-9]|020)"
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_CONTRACT_BINDING_COUNT = 3
_MAX_REQUESTS = 8
_SYNTHETIC_PROFILE_ID = "synthetic-hkex-english-profile-1"
_SYNTHETIC_PROFILE_FINGERPRINT = f"sha256:{'a' * 64}"
_SYNTHETIC_TOKENIZER_ID = "synthetic-codepoint-counter-1"

_EXPECTED_PAIRS: dict[str, tuple[tuple[str, str], ...]] = {
    "HKREG-DET-COV-001": (
        ("HKREG-PAIR-041", "POSITIVE"),
        ("HKREG-PAIR-042", "POSITIVE"),
    ),
    "HKREG-DET-COV-007": (("HKREG-PAIR-043", "POSITIVE"),),
    "HKREG-DET-COV-008": (("HKREG-PAIR-041", "NEAR_MISS"),),
    "HKREG-DET-COV-009": (("HKREG-PAIR-042", "NEAR_MISS"),),
    "HKREG-DET-COV-010": (("HKREG-PAIR-043", "NEAR_MISS"),),
    "HKREG-DET-COV-015": (("HKREG-PAIR-044", "POSITIVE"),),
    "HKREG-DET-COV-016": (("HKREG-PAIR-044", "NEAR_MISS"),),
    "HKREG-DET-COV-017": (("HKREG-PAIR-045", "POSITIVE"),),
    "HKREG-DET-COV-018": (("HKREG-PAIR-045", "NEAR_MISS"),),
}


class HKEXCoverageErrorCode(StrEnum):
    """Closed malformed permanent coverage-case failures."""

    CONTRACT = "HKREG_COVERAGE_CONTRACT_INVALID"
    IDENTITY = "HKREG_COVERAGE_IDENTITY_INVALID"
    FINGERPRINT = "HKREG_COVERAGE_FINGERPRINT_INVALID"


class HKEXCoverageError(ValueError):
    """One fail-closed permanent coverage-case rejection."""

    code: HKEXCoverageErrorCode

    def __init__(self, code: HKEXCoverageErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKEXCoverageAssertionScope(StrEnum):
    """One orthogonal source-unit or readiness invariant."""

    PRIMARY_OWNERSHIP = "PRIMARY_OWNERSHIP"
    BLOCKED_REQUIRED = "BLOCKED_REQUIRED"
    REPEATED_DEPENDENCY = "REPEATED_DEPENDENCY"
    EXPLICIT_CLASSIFICATION = "EXPLICIT_CLASSIFICATION"
    COMPLEX_ELEMENTS = "COMPLEX_ELEMENTS"
    NONCURRENT_OUTCOMES = "NONCURRENT_OUTCOMES"
    ORDER_AND_BOARD = "ORDER_AND_BOARD"
    MISSING_UNIT = "MISSING_UNIT"
    DUPLICATE_PRIMARY = "DUPLICATE_PRIMARY"
    REORDERED_PRIMARY = "REORDERED_PRIMARY"
    ORPHAN_OUTPUT = "ORPHAN_OUTPUT"
    WRONG_BOARD = "WRONG_BOARD"
    DEPENDENCY_BINDING = "DEPENDENCY_BINDING"
    SOURCE_FIDELITY = "SOURCE_FIDELITY"
    BOARD_READY = "BOARD_READY"
    QUARANTINED_CURRENT = "QUARANTINED_CURRENT"
    BOARD_ISOLATION = "BOARD_ISOLATION"
    SHARED_GAP = "SHARED_GAP"
    WEAK_PROXY = "WEAK_PROXY"
    ZERO_OUTPUT = "ZERO_OUTPUT"


class HKEXCoverageUnitOutcome(StrEnum):
    """One explicit source-unit accounting role or non-serving outcome."""

    PRIMARY = "PRIMARY"
    BLOCKED = "BLOCKED"
    QUARANTINED = "QUARANTINED"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    PRESENTATION_ONLY = "PRESENTATION_ONLY"
    WAITING_ROOM = "WAITING_ROOM"
    HISTORY = "HISTORY"
    EXCLUDED = "EXCLUDED"


class HKEXCoverageFidelity(StrEnum):
    """Closed relationship between declared output and exact source meaning."""

    EXACT = "EXACT"
    TRANSLATED = "TRANSLATED"
    SUMMARIZED = "SUMMARIZED"
    CORRECTED = "CORRECTED"
    INVENTED = "INVENTED"
    DROPPED = "DROPPED"


class HKEXCoverageOutcome(StrEnum):
    """Effect-free coverage checkpoint outcome."""

    PASS = "PASS"
    INVALID = "INVALID"
    COMPLETE_NOT_READY = "COMPLETE_NOT_READY"


class HKEXCoverageReason(StrEnum):
    """Exact accepted coverage and readiness consequences."""

    COMPLETE_PRIMARY_OWNERSHIP = "COMPLETE_PRIMARY_OWNERSHIP"
    REQUIRED_UNIT_EXPLICITLY_BLOCKED = "REQUIRED_UNIT_EXPLICITLY_BLOCKED"
    DEPENDENCY_REPETITION_ACCOUNTED = "DEPENDENCY_REPETITION_ACCOUNTED"
    CLASSIFICATIONS_ACCOUNTED = "CLASSIFICATIONS_ACCOUNTED"
    COMPLEX_ELEMENTS_ACCOUNTED = "COMPLEX_ELEMENTS_ACCOUNTED"
    NONCURRENT_OUTCOMES_ACCOUNTED = "NONCURRENT_OUTCOMES_ACCOUNTED"
    ORDER_AND_BOARD_PROVED = "ORDER_AND_BOARD_PROVED"
    MISSING_SOURCE_UNIT = "MISSING_SOURCE_UNIT"
    DUPLICATE_PRIMARY_OWNER = "DUPLICATE_PRIMARY_OWNER"
    SOURCE_ORDER_CHANGED = "SOURCE_ORDER_CHANGED"
    ORPHANED_OUTPUT = "ORPHANED_OUTPUT"
    WRONG_BOARD_OWNER = "WRONG_BOARD_OWNER"
    DEPENDENCY_BINDING_INCOMPLETE = "DEPENDENCY_BINDING_INCOMPLETE"
    SOURCE_FIDELITY_CHANGED = "SOURCE_FIDELITY_CHANGED"
    BOARD_READY_FOR_LATER_GATES = "BOARD_READY_FOR_LATER_GATES"
    COMPLETE_BUT_BOARD_NOT_READY = "COMPLETE_BUT_BOARD_NOT_READY"
    BOARDS_INDEPENDENT = "BOARDS_INDEPENDENT"
    SHARED_GAP_BLOCKS_BOTH = "SHARED_GAP_BLOCKS_BOTH"
    WEAK_PROXY_REJECTED = "WEAK_PROXY_REJECTED"
    VALID_ZERO_OUTPUT = "VALID_ZERO_OUTPUT"


@dataclass(frozen=True, slots=True)
class HKEXCoverageContractBinding:
    """One exact contract bound to a permanent case."""

    contract_id: str
    version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXCoveragePairMembership:
    """One exact high-risk pair role."""

    pair_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKEXCoverageEvidencePacket:
    """One proposal-safe synthetic fact packet."""

    slot_id: str
    state: str
    path: str
    role: str
    media_type: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXCoverageDependencyUse:
    """One labelled non-primary dependency occurrence."""

    consumer_record_id: str
    label: str
    owner_record_id: str
    source_fingerprint: str

    def document(self) -> dict[str, object]:
        """Return one strict JSON-compatible dependency use."""
        return {
            "consumer_record_id": self.consumer_record_id,
            "label": self.label,
            "owner_record_id": self.owner_record_id,
            "source_fingerprint": self.source_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HKEXCoverageUnitAccounting:
    """One declared exact unit accounting entry."""

    unit_key: str
    scope_id: str
    source_order: int
    outcome: HKEXCoverageUnitOutcome
    primary_owner_record_ids: tuple[str, ...]
    dependency_uses: tuple[HKEXCoverageDependencyUse, ...]
    fidelity: HKEXCoverageFidelity

    def document(self) -> dict[str, object]:
        """Return one strict JSON-compatible unit entry."""
        return {
            "unit_key": self.unit_key,
            "scope_id": self.scope_id,
            "source_order": self.source_order,
            "outcome": self.outcome.value,
            "primary_owner_record_ids": list(self.primary_owner_record_ids),
            "dependency_uses": [item.document() for item in self.dependency_uses],
            "fidelity": self.fidelity.value,
        }


@dataclass(frozen=True, slots=True)
class HKEXCoverageExcludedUnit:
    """One explicitly excluded non-rule unit outside an English branch tree."""

    unit_key: str
    scope_id: str
    source_order: int

    def document(self) -> dict[str, object]:
        """Return one strict JSON-compatible excluded unit."""
        return {
            "unit_key": self.unit_key,
            "scope_id": self.scope_id,
            "source_order": self.source_order,
        }


@dataclass(frozen=True, slots=True)
class HKEXCoverageFacts:
    """Source-neutral accepted requests and independently declared accounting."""

    requests: tuple[HKEXEnglishConstructionRequest, ...]
    declared_units: tuple[HKEXCoverageUnitAccounting, ...]
    excluded_units: tuple[HKEXCoverageExcludedUnit, ...]
    shared_unbounded_gap: bool
    weak_proxy_checks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKEXCoverageBoardResult:
    """One independently evaluated Main Board or GEM result."""

    scope_id: str
    inventory_bounded: bool
    coverage_complete: bool
    required_current_unit_count: int
    ready_current_unit_count: int
    blocked_or_quarantined_unit_count: int
    search_record_candidate_count: int
    later_gate_candidate_ready: bool

    def document(self) -> dict[str, object]:
        """Return one strict JSON-compatible board result."""
        return {
            "scope_id": self.scope_id,
            "inventory_bounded": self.inventory_bounded,
            "coverage_complete": self.coverage_complete,
            "required_current_unit_count": self.required_current_unit_count,
            "ready_current_unit_count": self.ready_current_unit_count,
            "blocked_or_quarantined_unit_count": self.blocked_or_quarantined_unit_count,
            "search_record_candidate_count": self.search_record_candidate_count,
            "later_gate_candidate_ready": self.later_gate_candidate_ready,
        }


@dataclass(frozen=True, slots=True)
class HKEXCoverageDecision:
    """Complete deterministic accounting consequence without serving authority."""

    outcome: HKEXCoverageOutcome
    reason: HKEXCoverageReason
    coverage_complete: bool
    source_fidelity_valid: bool
    source_order_valid: bool
    board_ownership_valid: bool
    dependency_accounting_valid: bool
    total_source_unit_count: int
    primary_owned_unit_count: int
    non_serving_unit_count: int
    board_results: tuple[HKEXCoverageBoardResult, ...]
    violation_codes: tuple[str, ...]

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return the exact effect-free result."""
        _text(case_id)
        return {
            "schema_id": "asklegal.hk-regulatory.coverage-decision-result",
            "schema_version": HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_COVERAGE_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "coverage_complete": self.coverage_complete,
            "source_fidelity_valid": self.source_fidelity_valid,
            "source_order_valid": self.source_order_valid,
            "board_ownership_valid": self.board_ownership_valid,
            "dependency_accounting_valid": self.dependency_accounting_valid,
            "total_source_unit_count": self.total_source_unit_count,
            "primary_owned_unit_count": self.primary_owned_unit_count,
            "non_serving_unit_count": self.non_serving_unit_count,
            "board_results": [item.document() for item in self.board_results],
            "violation_codes": list(self.violation_codes),
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "deployment_authorized": False,
            "external_effects": "NONE",
        }


@dataclass(frozen=True, slots=True)
class HKEXCoverageDecisionCase:
    """One strict source-unit coverage conformance envelope."""

    case_id: str
    primary_coverage_cell_id: str
    pair_memberships: tuple[HKEXCoveragePairMembership, ...]
    assertion_scope: HKEXCoverageAssertionScope
    contract_bindings: tuple[HKEXCoverageContractBinding, ...]
    evidence_packet: HKEXCoverageEvidencePacket
    package_fingerprint: str
    title: str
    purpose: str
    expected_decision: HKEXCoverageDecision
    facts: HKEXCoverageFacts


@dataclass(frozen=True, slots=True)
class HKEXCoverageDecisionReport:
    """Complete expected-versus-observed coverage report."""

    case_id: str
    assertion_scope: HKEXCoverageAssertionScope
    observed_decision: HKEXCoverageDecision
    expected_decision: HKEXCoverageDecision
    conformance_status: str

    def document(self) -> dict[str, object]:
        """Return one strict effect-free report."""
        return {
            "schema_id": "asklegal.hk-regulatory.coverage-decision-report",
            "schema_version": HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_COVERAGE_DECISION_RULE_ID,
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
class _CanonicalUnit:
    unit_key: str
    scope_id: str
    source_order: int
    outcome: HKEXCoverageUnitOutcome
    owners: tuple[str, ...]
    dependencies: tuple[HKEXCoverageDependencyUse, ...]
    kind: str


@dataclass(frozen=True, slots=True)
class _CoverageViolations:
    missing: tuple[str, ...]
    orphan: tuple[str, ...]
    duplicate_keys: tuple[str, ...]
    duplicate_primary: tuple[str, ...]
    wrong_board: tuple[str, ...]
    wrong_role: tuple[str, ...]
    wrong_owner: tuple[str, ...]
    wrong_dependency: tuple[str, ...]
    wrong_fidelity: tuple[str, ...]
    order_valid: bool
    shared_gap: bool


@dataclass(frozen=True, slots=True)
class _CoverageEvaluation:
    canonical: tuple[_CanonicalUnit, ...]
    declared: tuple[HKEXCoverageUnitAccounting, ...]
    boards: tuple[HKEXCoverageBoardResult, ...]
    violation_codes: tuple[str, ...]
    facts: HKEXCoverageFacts

    @property
    def clean(self) -> bool:
        """Return whether no violation exists."""
        return not self.violation_codes

    @property
    def primary(self) -> tuple[HKEXCoverageUnitAccounting, ...]:
        """Return declared primary-unit entries."""
        return tuple(
            item for item in self.declared if item.outcome is HKEXCoverageUnitOutcome.PRIMARY
        )

    @property
    def nonserving(self) -> tuple[HKEXCoverageUnitAccounting, ...]:
        """Return declared explicit non-serving entries."""
        return tuple(
            item for item in self.declared if item.outcome is not HKEXCoverageUnitOutcome.PRIMARY
        )


@dataclass(frozen=True, slots=True)
class _CaseHeader:
    case_id: str
    primary_cell_id: str
    pairs: tuple[HKEXCoveragePairMembership, ...]
    scope: HKEXCoverageAssertionScope
    bindings: tuple[HKEXCoverageContractBinding, ...]
    package_fingerprint: str


class _SyntheticCodepointCounter:
    profile_id = _SYNTHETIC_PROFILE_ID
    profile_fingerprint = _SYNTHETIC_PROFILE_FINGERPRINT
    tokenizer_id = _SYNTHETIC_TOKENIZER_ID

    def count(self, text: str) -> int:
        return len(text)


def hkex_coverage_decision_case_from_document(document: object) -> HKEXCoverageDecisionCase:
    """Strictly decode and fingerprint one permanent coverage case."""
    root = _object(_checked(document))
    _exact_keys(root, _CASE_FIELDS)
    header = _case_header(root)
    _validate_declarations(root, header.bindings)
    facts = _facts(root["facts"])
    packet = _packet(root["evidence_packet"], facts)
    expected = _decision_from_document(root["expected_decision"], header.case_id)
    _validate_case_fingerprint(root)
    return HKEXCoverageDecisionCase(
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


def decide_hkex_coverage_case(case: HKEXCoverageDecisionCase) -> HKEXCoverageDecision:
    """Evaluate accepted ADR 0073 proofs and declared accounting, never case ID."""
    if type(case) is not HKEXCoverageDecisionCase:
        _fail()
    canonical = _canonical_units(case.facts)
    declared = case.facts.declared_units
    canonical_by_key = {item.unit_key: item for item in canonical}
    declared_by_key = {item.unit_key: item for item in declared}
    duplicate_keys = _duplicates(item.unit_key for item in declared)
    missing = tuple(key for key in canonical_by_key if key not in declared_by_key)
    orphan = tuple(key for key in declared_by_key if key not in canonical_by_key)
    duplicate_primary = tuple(
        item.unit_key
        for item in declared
        if item.outcome is HKEXCoverageUnitOutcome.PRIMARY
        and len(item.primary_owner_record_ids) != 1
    )
    wrong_board = tuple(
        key
        for key in canonical_by_key.keys() & declared_by_key.keys()
        if canonical_by_key[key].scope_id != declared_by_key[key].scope_id
    )
    wrong_role = tuple(
        key
        for key in canonical_by_key.keys() & declared_by_key.keys()
        if not _role_matches(canonical_by_key[key].outcome, declared_by_key[key].outcome)
    )
    wrong_owner = tuple(
        key
        for key in canonical_by_key.keys() & declared_by_key.keys()
        if declared_by_key[key].outcome is HKEXCoverageUnitOutcome.PRIMARY
        and canonical_by_key[key].owners != declared_by_key[key].primary_owner_record_ids
    )
    wrong_dependency = tuple(
        key
        for key in canonical_by_key.keys() & declared_by_key.keys()
        if canonical_by_key[key].dependencies != declared_by_key[key].dependency_uses
    )
    wrong_fidelity = tuple(
        item.unit_key for item in declared if item.fidelity is not HKEXCoverageFidelity.EXACT
    )
    expected_primary_order = tuple(
        item.unit_key for item in canonical if item.outcome is HKEXCoverageUnitOutcome.PRIMARY
    )
    declared_primary_order = tuple(
        item.unit_key for item in declared if item.outcome is HKEXCoverageUnitOutcome.PRIMARY
    )
    order_valid = expected_primary_order == declared_primary_order
    violations = _violation_codes(
        _CoverageViolations(
            missing,
            orphan,
            duplicate_keys,
            duplicate_primary,
            wrong_board,
            wrong_role,
            wrong_owner,
            wrong_dependency,
            wrong_fidelity,
            order_valid,
            case.facts.shared_unbounded_gap,
        )
    )
    board_results = _board_results(canonical, declared_by_key, violations, case.facts)
    metrics = {
        "coverage_complete": all(item.coverage_complete for item in board_results),
        "source_fidelity_valid": not wrong_fidelity,
        "source_order_valid": order_valid,
        "board_ownership_valid": not wrong_board,
        "dependency_accounting_valid": not wrong_dependency,
        "total_source_unit_count": len(canonical),
        "primary_owned_unit_count": sum(
            item.outcome is HKEXCoverageUnitOutcome.PRIMARY
            and len(item.primary_owner_record_ids) == 1
            for item in declared
        ),
        "non_serving_unit_count": sum(
            item.outcome is not HKEXCoverageUnitOutcome.PRIMARY for item in declared
        ),
    }
    outcome, reason = _scope_result(
        case.assertion_scope,
        _CoverageEvaluation(canonical, declared, board_results, violations, case.facts),
    )
    return HKEXCoverageDecision(
        outcome,
        reason,
        bool(metrics["coverage_complete"]),
        bool(metrics["source_fidelity_valid"]),
        bool(metrics["source_order_valid"]),
        bool(metrics["board_ownership_valid"]),
        bool(metrics["dependency_accounting_valid"]),
        int(metrics["total_source_unit_count"]),
        int(metrics["primary_owned_unit_count"]),
        int(metrics["non_serving_unit_count"]),
        board_results,
        violations,
    )


def run_hkex_coverage_case(case: HKEXCoverageDecisionCase) -> HKEXCoverageDecisionReport:
    """Compare the fact-derived result with complete frozen truth."""
    observed = decide_hkex_coverage_case(case)
    return HKEXCoverageDecisionReport(
        case.case_id,
        case.assertion_scope,
        observed,
        case.expected_decision,
        "PASS" if observed == case.expected_decision else "FAIL",
    )


def canonical_hkex_coverage_units(
    requests: tuple[HKEXEnglishConstructionRequest, ...],
    excluded_units: tuple[HKEXCoverageExcludedUnit, ...] = (),
) -> tuple[HKEXCoverageUnitAccounting, ...]:
    """Expose canonical fixture accounting derived from accepted construction proofs."""
    facts = HKEXCoverageFacts(
        requests=requests,
        declared_units=(),
        excluded_units=excluded_units,
        shared_unbounded_gap=False,
        weak_proxy_checks=(),
    )
    return tuple(
        HKEXCoverageUnitAccounting(
            item.unit_key,
            item.scope_id,
            item.source_order,
            item.outcome,
            item.owners,
            item.dependencies,
            HKEXCoverageFidelity.EXACT,
        )
        for item in _canonical_units(facts)
    )


def _canonical_units(facts: HKEXCoverageFacts) -> tuple[_CanonicalUnit, ...]:
    results: list[_CanonicalUnit] = []
    seen: set[str] = set()
    for request in facts.requests:
        for item in _canonical_request_units(request):
            if item.unit_key in seen:
                _fail()
            seen.add(item.unit_key)
            results.append(item)
    for excluded in facts.excluded_units:
        if excluded.unit_key in seen:
            _fail()
        seen.add(excluded.unit_key)
        results.append(
            _CanonicalUnit(
                excluded.unit_key,
                excluded.scope_id,
                excluded.source_order,
                HKEXCoverageUnitOutcome.EXCLUDED,
                (),
                (),
                "EXCLUDED_NON_RULE",
            )
        )
    return tuple(results)


def _canonical_request_units(
    request: HKEXEnglishConstructionRequest,
) -> tuple[_CanonicalUnit, ...]:
    _validate_synthetic_request(request)
    proof = construct_hkex_english_request(request, _SyntheticCodepointCounter())
    tree = request.tree
    owner_by_unit: dict[str, str] = {}
    disposition_by_unit: dict[str, HKEXEnglishDisposition] = {}
    dependency_consumers: dict[str, set[str]] = {}
    for record in proof.record_results:
        record_key = f"{tree.tree_id}:{record.root_record_unit_id}"
        for unit_id in record.accounted_primary_source_unit_ids:
            if record.disposition is HKEXEnglishDisposition.PASS:
                if unit_id in owner_by_unit:
                    _fail()
                owner_by_unit[unit_id] = record_key
            disposition_by_unit[unit_id] = record.disposition
        for part in record.parts:
            for unit_id in part.dependency_source_unit_ids:
                dependency_consumers.setdefault(unit_id, set()).add(record_key)
    return tuple(
        _canonical_source_unit(
            request,
            unit.source_unit_id,
            owner_by_unit,
            disposition_by_unit,
            dependency_consumers,
        )
        for unit in tree.source_units
    )


def _canonical_source_unit(
    request: HKEXEnglishConstructionRequest,
    unit_id: str,
    owners_by_unit: dict[str, str],
    dispositions_by_unit: dict[str, HKEXEnglishDisposition],
    dependency_consumers: dict[str, set[str]],
) -> _CanonicalUnit:
    tree = request.tree
    unit = next(item for item in tree.source_units if item.source_unit_id == unit_id)
    key = f"{tree.tree_id}:{unit_id}"
    outcome = _canonical_outcome(tree.branch_state, unit.role, dispositions_by_unit.get(unit_id))
    owners = (owners_by_unit[unit_id],) if unit_id in owners_by_unit else ()
    owner = owners[0] if owners else f"CLASSIFICATION:{outcome.value}:{key}"
    dependencies = tuple(
        HKEXCoverageDependencyUse(
            consumer,
            f"Governing context: {unit_id}",
            owner,
            unit.content_fingerprint,
        )
        for consumer in sorted(dependency_consumers.get(unit_id, ()), key=str.encode)
    )
    return _CanonicalUnit(
        key,
        tree.scope_id,
        unit.source_order,
        outcome,
        owners,
        dependencies,
        unit.kind.value,
    )


def _canonical_outcome(
    state: HKEXBranchState,
    role: HKEXSourceUnitRole,
    disposition: HKEXEnglishDisposition | None,
) -> HKEXCoverageUnitOutcome:
    outcome: HKEXCoverageUnitOutcome | None = None
    if state in {HKEXBranchState.CURRENT, HKEXBranchState.TRANSITIONAL_CURRENT}:
        if role is HKEXSourceUnitRole.CONTEXT_ONLY:
            outcome = HKEXCoverageUnitOutcome.CONTEXT_ONLY
        elif role is HKEXSourceUnitRole.PRESENTATION_ONLY:
            outcome = HKEXCoverageUnitOutcome.PRESENTATION_ONLY
        elif disposition is HKEXEnglishDisposition.PASS:
            outcome = HKEXCoverageUnitOutcome.PRIMARY
        elif disposition is HKEXEnglishDisposition.QUARANTINE:
            outcome = HKEXCoverageUnitOutcome.QUARANTINED
    elif state in {
        HKEXBranchState.FUTURE_FIXED_DATE,
        HKEXBranchState.FUTURE_CONDITIONAL,
    }:
        outcome = HKEXCoverageUnitOutcome.WAITING_ROOM
    elif state in {HKEXBranchState.SUPERSEDED, HKEXBranchState.WITHDRAWN}:
        outcome = HKEXCoverageUnitOutcome.HISTORY
    elif state is HKEXBranchState.UNKNOWN:
        outcome = HKEXCoverageUnitOutcome.QUARANTINED
    return outcome if outcome is not None else _fail()


def _role_matches(canonical: HKEXCoverageUnitOutcome, declared: HKEXCoverageUnitOutcome) -> bool:
    if canonical is HKEXCoverageUnitOutcome.QUARANTINED:
        return declared in {HKEXCoverageUnitOutcome.QUARANTINED, HKEXCoverageUnitOutcome.BLOCKED}
    return canonical is declared


def _violation_codes(facts: _CoverageViolations) -> tuple[str, ...]:
    values: list[str] = []
    groups = (
        ("MISSING_SOURCE_UNIT", facts.missing),
        ("ORPHAN_OUTPUT", facts.orphan),
        ("DUPLICATE_UNIT_ENTRY", facts.duplicate_keys),
        ("DUPLICATE_PRIMARY_OWNER", facts.duplicate_primary),
        ("WRONG_BOARD_OWNER", facts.wrong_board),
        ("WRONG_ACCOUNTING_ROLE", facts.wrong_role),
        ("WRONG_PRIMARY_OWNER", facts.wrong_owner),
        ("DEPENDENCY_BINDING_INCOMPLETE", facts.wrong_dependency),
        ("SOURCE_FIDELITY_CHANGED", facts.wrong_fidelity),
    )
    for code, members in groups:
        if members:
            values.append(code)
    if not facts.order_valid:
        values.append("SOURCE_ORDER_CHANGED")
    if facts.shared_gap:
        values.append("SHARED_UNBOUNDED_GAP")
    return tuple(values)


def _board_results(
    canonical: tuple[_CanonicalUnit, ...],
    declared: dict[str, HKEXCoverageUnitAccounting],
    violations: tuple[str, ...],
    facts: HKEXCoverageFacts,
) -> tuple[HKEXCoverageBoardResult, ...]:
    scopes = sorted({item.scope_id for item in canonical}, key=str.encode)
    results: list[HKEXCoverageBoardResult] = []
    global_invalid = bool(violations) and violations != ("SHARED_UNBOUNDED_GAP",)
    for scope in scopes:
        units = tuple(item for item in canonical if item.scope_id == scope)
        declared_units = tuple(
            declared[item.unit_key] for item in units if item.unit_key in declared
        )
        bounded = not facts.shared_unbounded_gap
        complete = bounded and not global_invalid and len(declared_units) == len(units)
        current = tuple(
            item
            for item in units
            if item.outcome
            in {
                HKEXCoverageUnitOutcome.PRIMARY,
                HKEXCoverageUnitOutcome.QUARANTINED,
            }
        )
        ready = sum(
            item.outcome is HKEXCoverageUnitOutcome.PRIMARY
            and len(item.primary_owner_record_ids) == 1
            for item in declared_units
        )
        blocked = sum(
            item.outcome
            in {
                HKEXCoverageUnitOutcome.BLOCKED,
                HKEXCoverageUnitOutcome.QUARANTINED,
            }
            for item in declared_units
        )
        owners = {
            owner
            for item in declared_units
            if item.outcome is HKEXCoverageUnitOutcome.PRIMARY
            for owner in item.primary_owner_record_ids
        }
        results.append(
            HKEXCoverageBoardResult(
                scope,
                bounded,
                complete,
                len(current),
                ready,
                blocked,
                len(owners),
                complete and blocked == 0,
            )
        )
    return tuple(results)


def _has_outcome(evaluation: _CoverageEvaluation, *outcomes: HKEXCoverageUnitOutcome) -> bool:
    return set(outcomes).issubset({item.outcome for item in evaluation.declared})


def _has_violation(evaluation: _CoverageEvaluation, code: str) -> bool:
    return code in evaluation.violation_codes


def _complex_accounted(evaluation: _CoverageEvaluation) -> bool:
    required = {
        "TABLE_HEADER",
        "TABLE_ROW",
        "TABLE_NOTE",
        "FORM_INSTRUCTION",
        "FORM_LABEL",
        "FORM_CONTROL",
    }
    return evaluation.clean and required.issubset({item.kind for item in evaluation.canonical})


def _mixed_board_readiness(evaluation: _CoverageEvaluation) -> bool:
    states = tuple(item.later_gate_candidate_ready for item in evaluation.boards)
    return evaluation.clean and len(states) == len(HKEX_SCOPE_IDS) and states.count(True) == 1


def _weak_proxy_rejected(evaluation: _CoverageEvaluation) -> bool:
    return _has_violation(
        evaluation, "MISSING_SOURCE_UNIT"
    ) and evaluation.facts.weak_proxy_checks == (
        "PARSER_SUCCESS",
        "PDF_PAGE_COUNT_MATCH",
        "RECORD_COUNT_MATCH",
        "TEXT_PRESENCE_MATCH",
    )


type _CoverageValidator = Callable[[_CoverageEvaluation], bool]

_SCOPE_VALIDATORS: dict[HKEXCoverageAssertionScope, _CoverageValidator] = {
    HKEXCoverageAssertionScope.PRIMARY_OWNERSHIP: lambda item: item.clean and bool(item.primary),
    HKEXCoverageAssertionScope.BLOCKED_REQUIRED: lambda item: (
        item.clean and _has_outcome(item, HKEXCoverageUnitOutcome.BLOCKED)
    ),
    HKEXCoverageAssertionScope.REPEATED_DEPENDENCY: lambda item: (
        item.clean
        and any(
            unit.outcome is HKEXCoverageUnitOutcome.PRIMARY and unit.dependency_uses
            for unit in item.declared
        )
    ),
    HKEXCoverageAssertionScope.EXPLICIT_CLASSIFICATION: lambda item: (
        item.clean
        and _has_outcome(
            item, HKEXCoverageUnitOutcome.CONTEXT_ONLY, HKEXCoverageUnitOutcome.PRESENTATION_ONLY
        )
    ),
    HKEXCoverageAssertionScope.COMPLEX_ELEMENTS: _complex_accounted,
    HKEXCoverageAssertionScope.NONCURRENT_OUTCOMES: lambda item: (
        item.clean
        and _has_outcome(
            item,
            HKEXCoverageUnitOutcome.WAITING_ROOM,
            HKEXCoverageUnitOutcome.HISTORY,
            HKEXCoverageUnitOutcome.QUARANTINED,
            HKEXCoverageUnitOutcome.EXCLUDED,
        )
    ),
    HKEXCoverageAssertionScope.ORDER_AND_BOARD: lambda item: item.clean and bool(item.primary),
    HKEXCoverageAssertionScope.MISSING_UNIT: lambda item: _has_violation(
        item, "MISSING_SOURCE_UNIT"
    ),
    HKEXCoverageAssertionScope.DUPLICATE_PRIMARY: lambda item: _has_violation(
        item, "DUPLICATE_PRIMARY_OWNER"
    ),
    HKEXCoverageAssertionScope.REORDERED_PRIMARY: lambda item: _has_violation(
        item, "SOURCE_ORDER_CHANGED"
    ),
    HKEXCoverageAssertionScope.ORPHAN_OUTPUT: lambda item: _has_violation(item, "ORPHAN_OUTPUT"),
    HKEXCoverageAssertionScope.WRONG_BOARD: lambda item: _has_violation(item, "WRONG_BOARD_OWNER"),
    HKEXCoverageAssertionScope.DEPENDENCY_BINDING: lambda item: _has_violation(
        item, "DEPENDENCY_BINDING_INCOMPLETE"
    ),
    HKEXCoverageAssertionScope.SOURCE_FIDELITY: lambda item: _has_violation(
        item, "SOURCE_FIDELITY_CHANGED"
    ),
    HKEXCoverageAssertionScope.BOARD_READY: lambda item: (
        item.clean
        and bool(item.boards)
        and all(board.later_gate_candidate_ready for board in item.boards)
    ),
    HKEXCoverageAssertionScope.QUARANTINED_CURRENT: lambda item: (
        item.clean
        and any(
            board.coverage_complete and not board.later_gate_candidate_ready
            for board in item.boards
        )
    ),
    HKEXCoverageAssertionScope.BOARD_ISOLATION: _mixed_board_readiness,
    HKEXCoverageAssertionScope.SHARED_GAP: lambda item: (
        item.facts.shared_unbounded_gap
        and bool(item.boards)
        and not any(board.later_gate_candidate_ready for board in item.boards)
    ),
    HKEXCoverageAssertionScope.WEAK_PROXY: _weak_proxy_rejected,
    HKEXCoverageAssertionScope.ZERO_OUTPUT: lambda item: (
        item.clean and not item.primary and bool(item.nonserving)
    ),
}

_SCOPE_RESULTS = {
    HKEXCoverageAssertionScope.PRIMARY_OWNERSHIP: (
        HKEXCoverageOutcome.PASS,
        HKEXCoverageReason.COMPLETE_PRIMARY_OWNERSHIP,
    ),
    HKEXCoverageAssertionScope.BLOCKED_REQUIRED: (
        HKEXCoverageOutcome.COMPLETE_NOT_READY,
        HKEXCoverageReason.REQUIRED_UNIT_EXPLICITLY_BLOCKED,
    ),
    HKEXCoverageAssertionScope.REPEATED_DEPENDENCY: (
        HKEXCoverageOutcome.PASS,
        HKEXCoverageReason.DEPENDENCY_REPETITION_ACCOUNTED,
    ),
    HKEXCoverageAssertionScope.EXPLICIT_CLASSIFICATION: (
        HKEXCoverageOutcome.PASS,
        HKEXCoverageReason.CLASSIFICATIONS_ACCOUNTED,
    ),
    HKEXCoverageAssertionScope.COMPLEX_ELEMENTS: (
        HKEXCoverageOutcome.PASS,
        HKEXCoverageReason.COMPLEX_ELEMENTS_ACCOUNTED,
    ),
    HKEXCoverageAssertionScope.NONCURRENT_OUTCOMES: (
        HKEXCoverageOutcome.PASS,
        HKEXCoverageReason.NONCURRENT_OUTCOMES_ACCOUNTED,
    ),
    HKEXCoverageAssertionScope.ORDER_AND_BOARD: (
        HKEXCoverageOutcome.PASS,
        HKEXCoverageReason.ORDER_AND_BOARD_PROVED,
    ),
    HKEXCoverageAssertionScope.MISSING_UNIT: (
        HKEXCoverageOutcome.INVALID,
        HKEXCoverageReason.MISSING_SOURCE_UNIT,
    ),
    HKEXCoverageAssertionScope.DUPLICATE_PRIMARY: (
        HKEXCoverageOutcome.INVALID,
        HKEXCoverageReason.DUPLICATE_PRIMARY_OWNER,
    ),
    HKEXCoverageAssertionScope.REORDERED_PRIMARY: (
        HKEXCoverageOutcome.INVALID,
        HKEXCoverageReason.SOURCE_ORDER_CHANGED,
    ),
    HKEXCoverageAssertionScope.ORPHAN_OUTPUT: (
        HKEXCoverageOutcome.INVALID,
        HKEXCoverageReason.ORPHANED_OUTPUT,
    ),
    HKEXCoverageAssertionScope.WRONG_BOARD: (
        HKEXCoverageOutcome.INVALID,
        HKEXCoverageReason.WRONG_BOARD_OWNER,
    ),
    HKEXCoverageAssertionScope.DEPENDENCY_BINDING: (
        HKEXCoverageOutcome.INVALID,
        HKEXCoverageReason.DEPENDENCY_BINDING_INCOMPLETE,
    ),
    HKEXCoverageAssertionScope.SOURCE_FIDELITY: (
        HKEXCoverageOutcome.INVALID,
        HKEXCoverageReason.SOURCE_FIDELITY_CHANGED,
    ),
    HKEXCoverageAssertionScope.BOARD_READY: (
        HKEXCoverageOutcome.PASS,
        HKEXCoverageReason.BOARD_READY_FOR_LATER_GATES,
    ),
    HKEXCoverageAssertionScope.QUARANTINED_CURRENT: (
        HKEXCoverageOutcome.COMPLETE_NOT_READY,
        HKEXCoverageReason.COMPLETE_BUT_BOARD_NOT_READY,
    ),
    HKEXCoverageAssertionScope.BOARD_ISOLATION: (
        HKEXCoverageOutcome.PASS,
        HKEXCoverageReason.BOARDS_INDEPENDENT,
    ),
    HKEXCoverageAssertionScope.SHARED_GAP: (
        HKEXCoverageOutcome.COMPLETE_NOT_READY,
        HKEXCoverageReason.SHARED_GAP_BLOCKS_BOTH,
    ),
    HKEXCoverageAssertionScope.WEAK_PROXY: (
        HKEXCoverageOutcome.INVALID,
        HKEXCoverageReason.WEAK_PROXY_REJECTED,
    ),
    HKEXCoverageAssertionScope.ZERO_OUTPUT: (
        HKEXCoverageOutcome.PASS,
        HKEXCoverageReason.VALID_ZERO_OUTPUT,
    ),
}


def _scope_result(
    scope: HKEXCoverageAssertionScope,
    evaluation: _CoverageEvaluation,
) -> tuple[HKEXCoverageOutcome, HKEXCoverageReason]:
    validator = _SCOPE_VALIDATORS.get(scope)
    result = _SCOPE_RESULTS.get(scope)
    if validator is None or result is None or not validator(evaluation):
        _fail()
    return result


_FACT_FIELDS = {
    "requests",
    "declared_units",
    "excluded_units",
    "shared_unbounded_gap",
    "weak_proxy_checks",
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
    "coverage_complete",
    "source_fidelity_valid",
    "source_order_valid",
    "board_ownership_valid",
    "dependency_accounting_valid",
    "total_source_unit_count",
    "primary_owned_unit_count",
    "non_serving_unit_count",
    "board_results",
    "violation_codes",
    "search_record_authorized",
    "embedding_authorized",
    "release_authorized",
    "serving_authorized",
    "deployment_authorized",
    "external_effects",
}


def _case_header(root: dict[str, JsonValue]) -> _CaseHeader:
    _constant(root["schema_id"], "asklegal.hk-regulatory.coverage-decision-case")
    _constant(root["schema_version"], HKEX_COVERAGE_DECISION_CONTRACT_VERSION)
    _constant(root["package_contract_version"], "1.0.0")
    case_id = _pattern(root["case_id"], _CASE_PATTERN)
    suffix = case_id.rsplit("-", maxsplit=1)[1]
    _constant(root["suite_layer"], "DECISION_TO_ARTIFACT")
    _constant(root["primary_checkpoint"], "SOURCE_UNIT_COVERAGE")
    _true(root["frozen"])
    _constant(root["synthetic_evidence_class"], "SYNTHETIC_NO_REAL_AUTHORITY")
    _constant(root["synthetic_cutoff"], "2026-08-24T00:00:00Z")
    _constant(root["scope_id"], "HKEX_CROSS_BOARD")
    _constant(root["prior_state"], "SYNTHETIC_ACCEPTED_PREDECESSOR")
    primary = _strings(root["primary_coverage_cell_ids"])
    if primary != (f"HKREG-COV-DCOV-{suffix}",):
        _fail(HKEXCoverageErrorCode.IDENTITY)
    bindings = _bindings(root["contract_bindings"])
    package_fingerprint = _fingerprint(root["package_fingerprint"])
    _validate_bindings(bindings, package_fingerprint)
    return _CaseHeader(
        case_id,
        primary[0],
        _pairs(root["pair_memberships"], case_id),
        _enum(root["assertion_scope"], HKEXCoverageAssertionScope),
        bindings,
        package_fingerprint,
    )


def _validate_declarations(
    root: dict[str, JsonValue], bindings: tuple[HKEXCoverageContractBinding, ...]
) -> None:
    if _strings(root["secondary_coverage_cell_ids"], empty=True):
        _fail()
    if _strings(root["declared_input_inventory"]) != ("coverage-evidence",):
        _fail()
    if _strings(root["declared_reference_inventory"]) != tuple(
        item.contract_id for item in bindings
    ):
        _fail()
    if _strings(root["declared_expected_inventory"]) != ("COVERAGE_DECISION_REPORT",):
        _fail()
    if _strings(root["required_result_dimensions"]) != (
        "BOARD_READINESS",
        "DEPENDENCY_ACCOUNTING",
        "FORBIDDEN_EFFECTS",
        "SOURCE_FIDELITY",
        "SOURCE_ORDER",
        "SOURCE_UNIT_ACCOUNTING",
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


def _facts(value: JsonValue) -> HKEXCoverageFacts:
    root = _object(value)
    _exact_keys(root, _FACT_FIELDS)
    requests = tuple(hkex_english_request_from_document(item) for item in _array(root["requests"]))
    if not requests or len(requests) > _MAX_REQUESTS:
        _fail()
    declared = tuple(_unit_accounting(item) for item in _array(root["declared_units"]))
    excluded = tuple(_excluded_unit(item) for item in _array(root["excluded_units"]))
    proxies = _strings(root["weak_proxy_checks"], empty=True)
    if proxies != tuple(sorted(proxies)):
        _fail()
    facts = HKEXCoverageFacts(
        requests, declared, excluded, _boolean(root["shared_unbounded_gap"]), proxies
    )
    for request in requests:
        _validate_synthetic_request(request)
    return facts


def _unit_accounting(value: JsonValue) -> HKEXCoverageUnitAccounting:
    root = _object(value)
    _exact_keys(
        root,
        {
            "unit_key",
            "scope_id",
            "source_order",
            "outcome",
            "primary_owner_record_ids",
            "dependency_uses",
            "fidelity",
        },
    )
    scope = _text(root["scope_id"])
    if scope not in HKEX_SCOPE_IDS:
        _fail()
    return HKEXCoverageUnitAccounting(
        _text(root["unit_key"]),
        scope,
        _nonnegative_integer(root["source_order"]),
        _enum(root["outcome"], HKEXCoverageUnitOutcome),
        _strings(root["primary_owner_record_ids"], empty=True),
        tuple(_dependency(item) for item in _array(root["dependency_uses"])),
        _enum(root["fidelity"], HKEXCoverageFidelity),
    )


def _dependency(value: JsonValue) -> HKEXCoverageDependencyUse:
    root = _object(value)
    _exact_keys(root, {"consumer_record_id", "label", "owner_record_id", "source_fingerprint"})
    return HKEXCoverageDependencyUse(
        _text(root["consumer_record_id"]),
        _text(root["label"]),
        _text(root["owner_record_id"]),
        _fingerprint(root["source_fingerprint"]),
    )


def _excluded_unit(value: JsonValue) -> HKEXCoverageExcludedUnit:
    root = _object(value)
    _exact_keys(root, {"unit_key", "scope_id", "source_order"})
    scope = _text(root["scope_id"])
    if scope not in HKEX_SCOPE_IDS:
        _fail()
    return HKEXCoverageExcludedUnit(
        _text(root["unit_key"]), scope, _nonnegative_integer(root["source_order"])
    )


def _decision_from_document(value: JsonValue, case_id: str) -> HKEXCoverageDecision:
    root = _object(value)
    _exact_keys(root, _DECISION_FIELDS)
    _constant(root["schema_id"], "asklegal.hk-regulatory.coverage-decision-result")
    _constant(root["schema_version"], HKEX_COVERAGE_DECISION_CONTRACT_VERSION)
    _constant(root["rule_id"], HKEX_COVERAGE_DECISION_RULE_ID)
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
    return HKEXCoverageDecision(
        _enum(root["outcome"], HKEXCoverageOutcome),
        _enum(root["reason"], HKEXCoverageReason),
        _boolean(root["coverage_complete"]),
        _boolean(root["source_fidelity_valid"]),
        _boolean(root["source_order_valid"]),
        _boolean(root["board_ownership_valid"]),
        _boolean(root["dependency_accounting_valid"]),
        _nonnegative_integer(root["total_source_unit_count"]),
        _nonnegative_integer(root["primary_owned_unit_count"]),
        _nonnegative_integer(root["non_serving_unit_count"]),
        tuple(_board_result(item) for item in _array(root["board_results"])),
        _strings(root["violation_codes"], empty=True),
    )


def _board_result(value: JsonValue) -> HKEXCoverageBoardResult:
    root = _object(value)
    _exact_keys(
        root,
        {
            "scope_id",
            "inventory_bounded",
            "coverage_complete",
            "required_current_unit_count",
            "ready_current_unit_count",
            "blocked_or_quarantined_unit_count",
            "search_record_candidate_count",
            "later_gate_candidate_ready",
        },
    )
    scope = _text(root["scope_id"])
    if scope not in HKEX_SCOPE_IDS:
        _fail()
    return HKEXCoverageBoardResult(
        scope,
        _boolean(root["inventory_bounded"]),
        _boolean(root["coverage_complete"]),
        _nonnegative_integer(root["required_current_unit_count"]),
        _nonnegative_integer(root["ready_current_unit_count"]),
        _nonnegative_integer(root["blocked_or_quarantined_unit_count"]),
        _nonnegative_integer(root["search_record_candidate_count"]),
        _boolean(root["later_gate_candidate_ready"]),
    )


def _bindings(value: JsonValue) -> tuple[HKEXCoverageContractBinding, ...]:
    results: list[HKEXCoverageContractBinding] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"contract_id", "version", "fingerprint"})
        results.append(
            HKEXCoverageContractBinding(
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
    bindings: tuple[HKEXCoverageContractBinding, ...], package_fingerprint: str
) -> None:
    coverage_seed = checked_json_value(
        {
            "contract_id": "asklegal.hk-regulatory.coverage-decision-case",
            "contract_version": HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_COVERAGE_DECISION_RULE_ID,
        }
    )
    english_seed = checked_json_value(
        {
            "contract_id": "asklegal.hk-regulatory.english-record",
            "contract_version": HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            "rule_id": HKEX_ENGLISH_RECORD_RULE_ID,
        }
    )
    expected = (
        ("asklegal.hk-regulatory.conformance-universe", "1.0.0", package_fingerprint),
        (
            "asklegal.hk-regulatory.coverage-decision-case",
            HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
            fingerprint(coverage_seed),
        ),
        (
            "asklegal.hk-regulatory.english-record",
            HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            fingerprint(english_seed),
        ),
    )
    if tuple((item.contract_id, item.version, item.fingerprint) for item in bindings) != expected:
        _fail()


def _pairs(value: JsonValue, case_id: str) -> tuple[HKEXCoveragePairMembership, ...]:
    results: list[HKEXCoveragePairMembership] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"pair_id", "role"})
        pair_id = _pattern(root["pair_id"], r"HKREG-PAIR-0(41|42|43|44|45)")
        role = _text(root["role"])
        if role not in {"POSITIVE", "NEAR_MISS"}:
            _fail()
        results.append(HKEXCoveragePairMembership(pair_id, role))
    if tuple((item.pair_id, item.role) for item in results) != _EXPECTED_PAIRS.get(case_id, ()):
        _fail(HKEXCoverageErrorCode.IDENTITY)
    return tuple(results)


def _packet(value: JsonValue, facts: HKEXCoverageFacts) -> HKEXCoverageEvidencePacket:
    root = _object(value)
    _exact_keys(root, {"slot_id", "state", "path", "role", "media_type", "content_fingerprint"})
    packet = HKEXCoverageEvidencePacket(
        _text(root["slot_id"]),
        _text(root["state"]),
        _text(root["path"]),
        _text(root["role"]),
        _text(root["media_type"]),
        _fingerprint(root["content_fingerprint"]),
    )
    if (packet.slot_id, packet.state, packet.role, packet.media_type) != (
        "coverage-evidence",
        "AVAILABLE",
        "ORDINARY",
        "application/json",
    ):
        _fail()
    if packet.content_fingerprint != fingerprint(checked_json_value(_facts_document(facts))):
        _fail(HKEXCoverageErrorCode.FINGERPRINT)
    return packet


def _facts_document(facts: HKEXCoverageFacts) -> dict[str, object]:
    return {
        "requests": [item.document() for item in facts.requests],
        "declared_units": [item.document() for item in facts.declared_units],
        "excluded_units": [item.document() for item in facts.excluded_units],
        "shared_unbounded_gap": facts.shared_unbounded_gap,
        "weak_proxy_checks": list(facts.weak_proxy_checks),
    }


def _validate_case_fingerprint(root: dict[str, JsonValue]) -> None:
    actual = _fingerprint(root["case_fingerprint"])
    projection = dict(root)
    projection.pop("case_fingerprint")
    if fingerprint(checked_json_value(projection)) != actual:
        _fail(HKEXCoverageErrorCode.FINGERPRINT)


def _validate_synthetic_request(request: HKEXEnglishConstructionRequest) -> None:
    profile = request.profile
    if (
        profile.profile_id,
        profile.profile_fingerprint,
        profile.tokenizer_id,
        request.tree.source_rule_id,
    ) != (
        _SYNTHETIC_PROFILE_ID,
        _SYNTHETIC_PROFILE_FINGERPRINT,
        _SYNTHETIC_TOKENIZER_ID,
        HKEX_ENGLISH_RECORD_RULE_ID,
    ):
        _fail()


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
    except ContractViolation as error:
        raise HKEXCoverageError(HKEXCoverageErrorCode.CONTRACT) from error


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
    if not isinstance(value, str) or not value:
        _fail()
    return value


def _pattern(value: JsonValue, pattern: str) -> str:
    text = _text(value)
    if fullmatch(pattern, text) is None:
        _fail(HKEXCoverageErrorCode.IDENTITY)
    return text


def _fingerprint(value: JsonValue) -> str:
    text = _text(value)
    if fullmatch(_FINGERPRINT_PATTERN, text) is None:
        _fail(HKEXCoverageErrorCode.FINGERPRINT)
    return text


def _strings(value: JsonValue, *, empty: bool = False) -> tuple[str, ...]:
    result = tuple(_text(item) for item in _array(value))
    if (not result and not empty) or len(result) != len(set(result)):
        _fail()
    return result


def _sorted_strings(value: JsonValue) -> tuple[str, ...]:
    result = _strings(value, empty=True)
    if result != tuple(sorted(result, key=str.encode)):
        _fail()
    return result


def _nonempty_sorted(value: JsonValue) -> tuple[str, ...]:
    result = _sorted_strings(value)
    if not result:
        _fail()
    return result


def _boolean(value: JsonValue) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _true(value: JsonValue) -> None:
    if _boolean(value) is not True:
        _fail()


def _false(value: JsonValue) -> None:
    if _boolean(value) is not False:
        _fail()


def _nonnegative_integer(value: JsonValue) -> int:
    if type(value) is not int or value < 0:
        _fail()
    return value


def _constant(value: JsonValue, expected: JsonValue) -> None:
    if value != expected:
        _fail()


def _enum[T: StrEnum](value: JsonValue, cls: type[T]) -> T:
    try:
        return cls(_text(value))
    except ValueError as error:
        raise HKEXCoverageError(HKEXCoverageErrorCode.CONTRACT) from error


def _fail(code: HKEXCoverageErrorCode = HKEXCoverageErrorCode.CONTRACT) -> Never:
    raise HKEXCoverageError(code)


def is_hkex_coverage_error(error: BaseException) -> TypeIs[HKEXCoverageError]:
    """Narrow one exception for strict API adapters."""
    return isinstance(error, HKEXCoverageError)
