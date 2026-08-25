"""ADR 0074/0075 HKEX effective-state and transition conformance cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from re import fullmatch
from typing import Never, TypeIs

from asklegal_contracts import ContractViolation, fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_regulatory_effective_state import (
    HKEXEffectiveStateDecision,
    HKEXEffectiveStateError,
    HKEXEffectiveStateRequest,
    HKEXServingChoice,
    decide_hkex_effective_state,
    hkex_effective_state_request_from_document,
)
from .hk_regulatory_inventory import (
    HKEXApplicabilityBranch,
    HKEXBranchState,
    HKEXComponentState,
    HKEXMaterialDisposition,
    HKEXMembership,
    HKEXProcessingOutcome,
    derive_hkex_component_state,
)

HKEX_STATE_DECISION_RULE_ID = "HKREG-STATE-DECISION-001"
HKEX_STATE_DECISION_CONTRACT_VERSION = "1.0.0"
HKEX_STATE_DECISION_CASE_COUNT = 51

_CASE_PATTERN = r"HKREG-DEC-STA-(0[0-4][0-9]|05[01])"
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_MIN_BRANCH_SET = 2
_CONTRACT_BINDING_COUNT = 2
_EXPECTED_PAIR_MEMBERSHIPS: dict[str, tuple[tuple[str, str], ...]] = {
    "HKREG-DEC-STA-004": (("HKREG-PAIR-021", "POSITIVE"),),
    "HKREG-DEC-STA-006": (("HKREG-PAIR-024", "POSITIVE"),),
    "HKREG-DEC-STA-011": (("HKREG-PAIR-016", "POSITIVE"),),
    "HKREG-DEC-STA-018": (("HKREG-PAIR-017", "NEAR_MISS"),),
    "HKREG-DEC-STA-019": (
        ("HKREG-PAIR-017", "POSITIVE"),
        ("HKREG-PAIR-018", "POSITIVE"),
    ),
    "HKREG-DEC-STA-020": (("HKREG-PAIR-018", "NEAR_MISS"),),
    "HKREG-DEC-STA-026": (("HKREG-PAIR-019", "NEAR_MISS"),),
    "HKREG-DEC-STA-027": (
        ("HKREG-PAIR-019", "POSITIVE"),
        ("HKREG-PAIR-020", "POSITIVE"),
    ),
    "HKREG-DEC-STA-028": (("HKREG-PAIR-020", "NEAR_MISS"),),
    "HKREG-DEC-STA-029": (("HKREG-PAIR-021", "NEAR_MISS"),),
    "HKREG-DEC-STA-036": (("HKREG-PAIR-016", "NEAR_MISS"),),
    "HKREG-DEC-STA-037": (("HKREG-PAIR-022", "NEAR_MISS"),),
    "HKREG-DEC-STA-038": (("HKREG-PAIR-022", "POSITIVE"),),
    "HKREG-DEC-STA-040": (("HKREG-PAIR-023", "POSITIVE"),),
    "HKREG-DEC-STA-042": (("HKREG-PAIR-023", "NEAR_MISS"),),
    "HKREG-DEC-STA-045": (("HKREG-PAIR-024", "NEAR_MISS"),),
}


class HKEXStateDecisionErrorCode(StrEnum):
    """Closed malformed state-case envelope failures."""

    CONTRACT = "HKREG_STATE_DECISION_CONTRACT_INVALID"
    IDENTITY = "HKREG_STATE_DECISION_IDENTITY_INVALID"
    FINGERPRINT = "HKREG_STATE_DECISION_FINGERPRINT_INVALID"


class HKEXStateDecisionError(ValueError):
    """One fail-closed state-case rejection."""

    code: HKEXStateDecisionErrorCode

    def __init__(self, code: HKEXStateDecisionErrorCode) -> None:
        """Create one stable fail-closed error."""
        self.code = code
        super().__init__(code.value)


class HKEXStateAssertionScope(StrEnum):
    """Orthogonal decision dimension selected by facts, never case identity."""

    ATOMIC_STATE = "ATOMIC_STATE"
    COMPONENT_SUMMARY = "COMPONENT_SUMMARY"
    BRANCH_SET = "BRANCH_SET"
    RECORD_RESPONSIBILITY = "RECORD_RESPONSIBILITY"
    EFFECTIVE_ORDER = "EFFECTIVE_ORDER"
    SOURCE_FAILURE = "SOURCE_FAILURE"
    DOWNSTREAM_GATE = "DOWNSTREAM_GATE"
    UNKNOWN_REPAIR = "UNKNOWN_REPAIR"


class HKEXStateConformanceOutcome(StrEnum):
    """Terminal processing result for the permanent checkpoint."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


class HKEXStateDecisionReason(StrEnum):
    """Closed wrapper reasons beyond the atomic ADR 0071 reason."""

    ATOMIC_STATE_DECIDED = "ATOMIC_STATE_DECIDED"
    NON_RULE_NOT_APPLICABLE = "NON_RULE_NOT_APPLICABLE"
    COMPONENT_SUMMARIZED = "COMPONENT_SUMMARIZED"
    COMPLETE_BRANCH_SET_PRESERVED = "COMPLETE_BRANCH_SET_PRESERVED"
    SEPARATE_COMPLETE_RECORDS_REQUIRED = "SEPARATE_COMPLETE_RECORDS_REQUIRED"
    ONE_LIMITED_RECORD_ELIGIBLE = "ONE_LIMITED_RECORD_ELIGIBLE"
    EFFECTIVE_FACT_ORDER_APPLIED = "EFFECTIVE_FACT_ORDER_APPLIED"
    LAST_APPROVED_CARRY_FORWARD = "LAST_APPROVED_CARRY_FORWARD"
    AFFECTED_RECORDS_WITHHELD = "AFFECTED_RECORDS_WITHHELD"
    NO_NEW_TARGET = "NO_NEW_TARGET"
    OTHER_REQUIRED_GATE_FAILED = "OTHER_REQUIRED_GATE_FAILED"
    UNKNOWN_REPAIR_REJECTED = "UNKNOWN_REPAIR_REJECTED"


class HKEXRecordResponsibility(StrEnum):
    """Exact record consequence for concurrent applicability branches."""

    NONE = "NONE"
    SEPARATE_COMPLETE_RECORDS = "SEPARATE_COMPLETE_RECORDS"
    ONE_LIMITED_RECORD_ELIGIBLE = "ONE_LIMITED_RECORD_ELIGIBLE"


class HKEXWordingRelationship(StrEnum):
    """Only the distinction required for ADR 0075 cases 037 and 038."""

    NOT_EVALUATED = "NOT_EVALUATED"
    MATERIAL_DIFFERENCE = "MATERIAL_DIFFERENCE"
    SAME_WORDING = "SAME_WORDING"


class HKEXRepairAttempt(StrEnum):
    """Prohibited attempts to turn an unknown result into a current result."""

    NONE = "NONE"
    AUTHORITY_NOTE = "AUTHORITY_NOTE"
    CONFIDENCE = "CONFIDENCE"
    PROSE = "PROSE"


class HKEXUnsupportedRetirementBasis(StrEnum):
    """Non-authoritative continuity or retirement suggestions."""

    NONE = "NONE"
    SIMILARITY_REUSED_NUMBER_OR_HIGHER_UPDATE = "SIMILARITY_REUSED_NUMBER_OR_HIGHER_UPDATE"


@dataclass(frozen=True, slots=True)
class HKEXStateContractBinding:
    """One exact contract bound into a permanent case."""

    contract_id: str
    version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXStateEvidencePacket:
    """One embedded proposal-safe synthetic evidence packet."""

    slot_id: str
    state: str
    path: str
    role: str
    media_type: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXStatePairMembership:
    """One case's role in a permanent high-risk distinction pair."""

    pair_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKEXEffectiveOrderFact:
    """One supported effective fact independent of publisher update number."""

    branch_id: str
    supported_effective_at: str
    update_number: int

    def document(self) -> dict[str, object]:
        """Return the canonical JSON-compatible order fact."""
        return {
            "branch_id": self.branch_id,
            "supported_effective_at": self.supported_effective_at,
            "update_number": self.update_number,
        }


@dataclass(frozen=True, slots=True)
class HKEXCarryForwardSupport:
    """Complete ADR 0005 last-approved carry-forward metadata."""

    last_approved_status: str
    last_verified_at: str
    coverage_gap_id: str
    warning_code: str
    next_due_at: str | None
    support_ref: str

    def document(self) -> dict[str, object]:
        """Return the canonical JSON-compatible support object."""
        return {
            "last_approved_status": self.last_approved_status,
            "last_verified_at": self.last_verified_at,
            "coverage_gap_id": self.coverage_gap_id,
            "warning_code": self.warning_code,
            "next_due_at": self.next_due_at,
            "support_ref": self.support_ref,
        }


@dataclass(frozen=True, slots=True)
class HKEXStateDecisionFacts:
    """Orthogonal branch, component, record, outage, and gate facts."""

    membership: HKEXMembership
    branches: tuple[HKEXEffectiveStateRequest, ...]
    complete_branch_set: bool
    wording_relationship: HKEXWordingRelationship
    limitation_metadata_complete: bool
    effective_order_facts: tuple[HKEXEffectiveOrderFact, ...]
    carry_forward_support: HKEXCarryForwardSupport | None
    other_required_gates_passed: bool
    repair_attempt: HKEXRepairAttempt
    unsupported_retirement_basis: HKEXUnsupportedRetirementBasis


@dataclass(frozen=True, slots=True)
class HKEXStateBranchDecision:
    """One retained atomic ADR 0071 branch decision."""

    branch_id: str
    state: HKEXBranchState
    disposition: HKEXMaterialDisposition
    processing_outcome: HKEXProcessingOutcome
    reason: str
    applicability_context: str | None

    def document(self) -> dict[str, object]:
        """Return the canonical JSON-compatible branch result."""
        return {
            "branch_id": self.branch_id,
            "state": self.state.value,
            "disposition": self.disposition.value,
            "processing_outcome": self.processing_outcome.value,
            "reason": self.reason,
            "applicability_context": self.applicability_context,
        }


@dataclass(frozen=True, slots=True)
class HKEXStateDecision:
    """One complete state checkpoint result without serving authority."""

    outcome: HKEXStateConformanceOutcome
    reason: HKEXStateDecisionReason
    not_applicable: bool
    branch_decisions: tuple[HKEXStateBranchDecision, ...]
    component_state: HKEXComponentState | None
    record_responsibility: HKEXRecordResponsibility
    ordered_branch_ids: tuple[str, ...]
    source_failure_choice: HKEXServingChoice
    carry_forward_support: HKEXCarryForwardSupport | None
    rebuild_target_authorized: bool
    repair_rejected: bool

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return the exact result document for one permanent case."""
        _text(case_id)
        return {
            "schema_id": "asklegal.hk-regulatory.state-decision-result",
            "schema_version": HKEX_STATE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_STATE_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "not_applicable": self.not_applicable,
            "branch_decisions": [item.document() for item in self.branch_decisions],
            "component_state": (
                None if self.component_state is None else self.component_state.value
            ),
            "record_responsibility": self.record_responsibility.value,
            "ordered_branch_ids": list(self.ordered_branch_ids),
            "source_failure_choice": self.source_failure_choice.value,
            "carry_forward_support": (
                None
                if self.carry_forward_support is None
                else self.carry_forward_support.document()
            ),
            "rebuild_target_authorized": self.rebuild_target_authorized,
            "repair_rejected": self.repair_rejected,
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "external_effects": "NONE",
        }


@dataclass(frozen=True, slots=True)
class HKEXStateDecisionCase:
    """One strict evidence-to-decision conformance envelope."""

    case_id: str
    primary_coverage_cell_id: str
    pair_memberships: tuple[HKEXStatePairMembership, ...]
    assertion_scope: HKEXStateAssertionScope
    contract_bindings: tuple[HKEXStateContractBinding, ...]
    evidence_packet: HKEXStateEvidencePacket
    package_fingerprint: str
    title: str
    purpose: str
    expected_decision: HKEXStateDecision
    facts: HKEXStateDecisionFacts


@dataclass(frozen=True, slots=True)
class HKEXStateDecisionReport:
    """Complete expected-versus-observed state decision report."""

    case_id: str
    assertion_scope: HKEXStateAssertionScope
    observed_decision: HKEXStateDecision
    expected_decision: HKEXStateDecision
    conformance_status: str

    def document(self) -> dict[str, object]:
        """Return the exact report without external authority."""
        return {
            "schema_id": "asklegal.hk-regulatory.state-decision-report",
            "schema_version": HKEX_STATE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_STATE_DECISION_RULE_ID,
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
class _CaseHeader:
    """Validated identity and binding fields used by the case decoder."""

    case_id: str
    primary_cell_id: str
    pairs: tuple[HKEXStatePairMembership, ...]
    scope: HKEXStateAssertionScope
    bindings: tuple[HKEXStateContractBinding, ...]
    package_fingerprint: str


@dataclass(frozen=True, slots=True)
class _DecisionDetails:
    """Optional structured dimensions for one wrapper decision."""

    branches: tuple[HKEXStateBranchDecision, ...] = ()
    not_applicable: bool = False
    component_state: HKEXComponentState | None = None
    responsibility: HKEXRecordResponsibility = HKEXRecordResponsibility.NONE
    ordered: tuple[str, ...] = ()
    source_failure_choice: HKEXServingChoice = HKEXServingChoice.NONE
    support: HKEXCarryForwardSupport | None = None
    repair_rejected: bool = False


def hkex_state_decision_case_from_document(document: object) -> HKEXStateDecisionCase:
    """Strictly decode and fingerprint one effective-state conformance case."""
    root = _object(_checked(document))
    _exact_keys(
        root,
        {
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
        },
    )
    header = _case_header(root)
    _validate_case_declarations(root, header.bindings)
    title = _text(root["title"])
    purpose = _text(root["purpose"])
    expected = _decision_from_document(root["expected_decision"], header.case_id)
    facts = _facts(root["facts"])
    packet = _packet(root["evidence_packet"], facts)
    _validate_case_fingerprint(root)
    return HKEXStateDecisionCase(
        header.case_id,
        header.primary_cell_id,
        header.pairs,
        header.scope,
        header.bindings,
        packet,
        header.package_fingerprint,
        title,
        purpose,
        expected,
        facts,
    )


def _case_header(root: dict[str, JsonValue]) -> _CaseHeader:
    _constant(root["schema_id"], "asklegal.hk-regulatory.state-decision-case")
    _constant(root["schema_version"], HKEX_STATE_DECISION_CONTRACT_VERSION)
    _constant(root["package_contract_version"], "1.0.0")
    case_id = _pattern(root["case_id"], _CASE_PATTERN)
    suffix = case_id.rsplit("-", maxsplit=1)[1]
    _constant(root["suite_layer"], "EVIDENCE_TO_DECISION")
    _constant(root["primary_checkpoint"], "EFFECTIVE_STATE")
    _true(root["frozen"])
    _constant(root["synthetic_evidence_class"], "SYNTHETIC_NO_REAL_AUTHORITY")
    _constant(root["synthetic_cutoff"], "2026-08-24T00:00:00Z")
    _constant(root["scope_id"], "HKEX_CROSS_BOARD")
    _constant(root["prior_state"], "SYNTHETIC_ACCEPTED_PREDECESSOR")
    bindings = _bindings(root["contract_bindings"])
    primary = _strings(root["primary_coverage_cell_ids"])
    if primary != (f"HKREG-COV-DSTA-{suffix}",):
        _fail(HKEXStateDecisionErrorCode.IDENTITY)
    pairs = _pairs(root["pair_memberships"], case_id)
    scope = _enum(root["assertion_scope"], HKEXStateAssertionScope)
    package_fingerprint = _fingerprint(root["package_fingerprint"])
    _validate_bindings(bindings, package_fingerprint)
    return _CaseHeader(case_id, primary[0], pairs, scope, bindings, package_fingerprint)


def _validate_case_declarations(
    root: dict[str, JsonValue],
    bindings: tuple[HKEXStateContractBinding, ...],
) -> None:
    _sorted_strings(root["secondary_coverage_cell_ids"])
    if _strings(root["declared_input_inventory"]) != ("state-evidence",):
        _fail()
    references = _strings(root["declared_reference_inventory"])
    if references != tuple(binding.contract_id for binding in bindings):
        _fail()
    if _strings(root["declared_expected_inventory"]) != ("STATE_DECISION_REPORT",):
        _fail()
    if _strings(root["required_result_dimensions"]) != (
        "APPLICABILITY",
        "BRANCH_STATE",
        "COMPONENT_STATE",
        "PROCESSING",
        "RECORD_RESPONSIBILITY",
        "SOURCE_FAILURE",
    ):
        _fail()
    expected_fields = tuple(sorted(_FACT_FIELDS))
    if _strings(root["evidence_packet_fields"]) != expected_fields:
        _fail()
    _nonempty_sorted(root["supporting_evidence_ranges"])
    _nonempty_sorted(root["rule_trace"])
    _nonempty_sorted(root["established_facts"])
    _sorted_strings(root["unresolved_facts"])
    if _array(root["permitted_equivalent_results"]):
        _fail()
    _sorted_strings(root["critical_error_codes"])


def _validate_case_fingerprint(root: dict[str, JsonValue]) -> None:
    case_fingerprint = _fingerprint(root["case_fingerprint"])
    projection = dict(root)
    projection.pop("case_fingerprint")
    if fingerprint(checked_json_value(projection)) != case_fingerprint:
        _fail(HKEXStateDecisionErrorCode.FINGERPRINT)


def decide_hkex_state_case(case: HKEXStateDecisionCase) -> HKEXStateDecision:
    """Derive a complete result from declared facts and scope, never case ID."""
    if type(case) is not HKEXStateDecisionCase:
        _fail()
    evaluators = {
        HKEXStateAssertionScope.ATOMIC_STATE: _decide_atomic,
        HKEXStateAssertionScope.COMPONENT_SUMMARY: _decide_component,
        HKEXStateAssertionScope.BRANCH_SET: _decide_branch_set,
        HKEXStateAssertionScope.RECORD_RESPONSIBILITY: _decide_record_responsibility,
        HKEXStateAssertionScope.EFFECTIVE_ORDER: _decide_effective_order,
        HKEXStateAssertionScope.SOURCE_FAILURE: _decide_source_failure,
        HKEXStateAssertionScope.DOWNSTREAM_GATE: _decide_downstream_gate,
        HKEXStateAssertionScope.UNKNOWN_REPAIR: _decide_unknown_repair,
    }
    return evaluators[case.assertion_scope](case.facts)


def run_hkex_state_case(case: HKEXStateDecisionCase) -> HKEXStateDecisionReport:
    """Compare the complete derived result with independently frozen truth."""
    observed = decide_hkex_state_case(case)
    return HKEXStateDecisionReport(
        case.case_id,
        case.assertion_scope,
        observed,
        case.expected_decision,
        "PASS" if observed == case.expected_decision else "FAIL",
    )


def _branch(request: HKEXEffectiveStateRequest) -> HKEXStateBranchDecision:
    decision = decide_hkex_effective_state(request)
    return _branch_from_kernel(decision, request.applicability_context)


def _branch_from_kernel(
    decision: HKEXEffectiveStateDecision,
    context: str | None,
) -> HKEXStateBranchDecision:
    return HKEXStateBranchDecision(
        decision.branch_id,
        decision.state,
        decision.disposition,
        decision.processing_outcome,
        decision.reason.value,
        context,
    )


def _base_decision(
    outcome: HKEXStateConformanceOutcome,
    reason: HKEXStateDecisionReason,
    details: _DecisionDetails | None = None,
) -> HKEXStateDecision:
    resolved = _DecisionDetails() if details is None else details
    return HKEXStateDecision(
        outcome=outcome,
        reason=reason,
        not_applicable=resolved.not_applicable,
        branch_decisions=resolved.branches,
        component_state=resolved.component_state,
        record_responsibility=resolved.responsibility,
        ordered_branch_ids=resolved.ordered,
        source_failure_choice=resolved.source_failure_choice,
        carry_forward_support=resolved.support,
        rebuild_target_authorized=False,
        repair_rejected=resolved.repair_rejected,
    )


def _outcome(branches: tuple[HKEXStateBranchDecision, ...]) -> HKEXStateConformanceOutcome:
    if any(item.processing_outcome is HKEXProcessingOutcome.QUARANTINE for item in branches):
        return HKEXStateConformanceOutcome.QUARANTINE
    if any(item.processing_outcome is HKEXProcessingOutcome.BLOCK for item in branches):
        return HKEXStateConformanceOutcome.BLOCK
    return HKEXStateConformanceOutcome.PASS


def _decide_atomic(facts: HKEXStateDecisionFacts) -> HKEXStateDecision:
    if facts.membership is not HKEXMembership.RULE_COMPONENT:
        if facts.membership is HKEXMembership.EXCLUDED_NON_RULE and not facts.branches:
            return _base_decision(
                HKEXStateConformanceOutcome.PASS,
                HKEXStateDecisionReason.NON_RULE_NOT_APPLICABLE,
                _DecisionDetails(not_applicable=True),
            )
        _fail()
    if len(facts.branches) != 1:
        _fail()
    branches = (_branch(facts.branches[0]),)
    return _base_decision(
        _outcome(branches),
        HKEXStateDecisionReason.ATOMIC_STATE_DECIDED,
        _DecisionDetails(
            branches=branches,
            source_failure_choice=facts.branches[0].source_failure_choice,
        ),
    )


def _decide_component(facts: HKEXStateDecisionFacts) -> HKEXStateDecision:
    if facts.membership is not HKEXMembership.RULE_COMPONENT or not facts.complete_branch_set:
        _fail()
    branches = tuple(_branch(request) for request in facts.branches)
    summary = derive_hkex_component_state(
        tuple(
            HKEXApplicabilityBranch(item.branch_id, item.state, (f"decision:{item.branch_id}",))
            for item in branches
        )
    )
    outcome = (
        HKEXStateConformanceOutcome.QUARANTINE
        if summary is HKEXComponentState.UNKNOWN
        else HKEXStateConformanceOutcome.PASS
    )
    return _base_decision(
        outcome,
        HKEXStateDecisionReason.COMPONENT_SUMMARIZED,
        _DecisionDetails(branches=branches, component_state=summary),
    )


def _decide_branch_set(facts: HKEXStateDecisionFacts) -> HKEXStateDecision:
    if not facts.complete_branch_set or len(facts.branches) < _MIN_BRANCH_SET:
        _fail()
    branches = tuple(_branch(request) for request in facts.branches)
    return _base_decision(
        _outcome(branches),
        HKEXStateDecisionReason.COMPLETE_BRANCH_SET_PRESERVED,
        _DecisionDetails(branches=branches),
    )


def _decide_record_responsibility(facts: HKEXStateDecisionFacts) -> HKEXStateDecision:
    branches = tuple(_branch(request) for request in facts.branches)
    if facts.wording_relationship is HKEXWordingRelationship.MATERIAL_DIFFERENCE:
        if len(branches) < _MIN_BRANCH_SET:
            _fail()
        responsibility = HKEXRecordResponsibility.SEPARATE_COMPLETE_RECORDS
        reason = HKEXStateDecisionReason.SEPARATE_COMPLETE_RECORDS_REQUIRED
    elif (
        facts.wording_relationship is HKEXWordingRelationship.SAME_WORDING
        and facts.limitation_metadata_complete
        and len(branches) == 1
        and branches[0].applicability_context is not None
    ):
        responsibility = HKEXRecordResponsibility.ONE_LIMITED_RECORD_ELIGIBLE
        reason = HKEXStateDecisionReason.ONE_LIMITED_RECORD_ELIGIBLE
    else:
        _fail()
    return _base_decision(
        _outcome(branches),
        reason,
        _DecisionDetails(branches=branches, responsibility=responsibility),
    )


def _decide_effective_order(facts: HKEXStateDecisionFacts) -> HKEXStateDecision:
    branches = tuple(_branch(request) for request in facts.branches)
    if len(facts.effective_order_facts) != len(branches) or not branches:
        _fail()
    branch_ids = {item.branch_id for item in branches}
    if {item.branch_id for item in facts.effective_order_facts} != branch_ids:
        _fail()
    ordered = tuple(
        item.branch_id
        for item in sorted(
            facts.effective_order_facts,
            key=lambda item: (_instant(item.supported_effective_at), item.branch_id),
        )
    )
    return _base_decision(
        _outcome(branches),
        HKEXStateDecisionReason.EFFECTIVE_FACT_ORDER_APPLIED,
        _DecisionDetails(branches=branches, ordered=ordered),
    )


def _decide_source_failure(facts: HKEXStateDecisionFacts) -> HKEXStateDecision:
    if len(facts.branches) != 1:
        _fail()
    request = facts.branches[0]
    branch = _branch(request)
    choice = request.source_failure_choice
    if choice is HKEXServingChoice.CARRY_FORWARD_LAST_APPROVED:
        if facts.carry_forward_support is None:
            _fail()
        return _base_decision(
            HKEXStateConformanceOutcome.PASS,
            HKEXStateDecisionReason.LAST_APPROVED_CARRY_FORWARD,
            _DecisionDetails(
                branches=(branch,),
                source_failure_choice=choice,
                support=facts.carry_forward_support,
            ),
        )
    if facts.carry_forward_support is not None:
        _fail()
    if choice is HKEXServingChoice.WITHHOLD:
        reason = HKEXStateDecisionReason.AFFECTED_RECORDS_WITHHELD
    elif choice is HKEXServingChoice.NO_REBUILD:
        reason = HKEXStateDecisionReason.NO_NEW_TARGET
    else:
        _fail()
    return _base_decision(
        HKEXStateConformanceOutcome.BLOCK,
        reason,
        _DecisionDetails(branches=(branch,), source_failure_choice=choice),
    )


def _decide_downstream_gate(facts: HKEXStateDecisionFacts) -> HKEXStateDecision:
    if len(facts.branches) != 1 or facts.other_required_gates_passed:
        _fail()
    branch = _branch(facts.branches[0])
    if branch.state is not HKEXBranchState.CURRENT:
        _fail()
    return _base_decision(
        HKEXStateConformanceOutcome.BLOCK,
        HKEXStateDecisionReason.OTHER_REQUIRED_GATE_FAILED,
        _DecisionDetails(branches=(branch,)),
    )


def _decide_unknown_repair(facts: HKEXStateDecisionFacts) -> HKEXStateDecision:
    if len(facts.branches) != 1 or facts.repair_attempt is HKEXRepairAttempt.NONE:
        _fail()
    branch = _branch(facts.branches[0])
    if branch.state is not HKEXBranchState.UNKNOWN:
        _fail()
    return _base_decision(
        HKEXStateConformanceOutcome.QUARANTINE,
        HKEXStateDecisionReason.UNKNOWN_REPAIR_REJECTED,
        _DecisionDetails(branches=(branch,), repair_rejected=True),
    )


_FACT_FIELDS = {
    "membership",
    "branches",
    "complete_branch_set",
    "wording_relationship",
    "limitation_metadata_complete",
    "effective_order_facts",
    "carry_forward_support",
    "other_required_gates_passed",
    "repair_attempt",
    "unsupported_retirement_basis",
}


def _facts(value: JsonValue) -> HKEXStateDecisionFacts:
    root = _object(value)
    _exact_keys(root, _FACT_FIELDS)
    branches: list[HKEXEffectiveStateRequest] = []
    for item in _array(root["branches"]):
        try:
            branches.append(hkex_effective_state_request_from_document(item))
        except HKEXEffectiveStateError as error:
            raise HKEXStateDecisionError(HKEXStateDecisionErrorCode.CONTRACT) from error
    order = tuple(_order_fact(item) for item in _array(root["effective_order_facts"]))
    if len({item.branch_id for item in order}) != len(order):
        _fail()
    support_value = root["carry_forward_support"]
    support = None if support_value is None else _carry_support(support_value)
    result = HKEXStateDecisionFacts(
        _enum(root["membership"], HKEXMembership),
        tuple(branches),
        _boolean(root["complete_branch_set"]),
        _enum(root["wording_relationship"], HKEXWordingRelationship),
        _boolean(root["limitation_metadata_complete"]),
        order,
        support,
        _boolean(root["other_required_gates_passed"]),
        _enum(root["repair_attempt"], HKEXRepairAttempt),
        _enum(root["unsupported_retirement_basis"], HKEXUnsupportedRetirementBasis),
    )
    if result.membership is not HKEXMembership.RULE_COMPONENT and result.branches:
        _fail()
    return result


def _order_fact(value: JsonValue) -> HKEXEffectiveOrderFact:
    root = _object(value)
    _exact_keys(root, {"branch_id", "supported_effective_at", "update_number"})
    result = HKEXEffectiveOrderFact(
        _text(root["branch_id"]),
        _text(root["supported_effective_at"]),
        _integer(root["update_number"]),
    )
    _instant(result.supported_effective_at)
    return result


def _carry_support(value: JsonValue) -> HKEXCarryForwardSupport:
    root = _object(value)
    _exact_keys(
        root,
        {
            "last_approved_status",
            "last_verified_at",
            "coverage_gap_id",
            "warning_code",
            "next_due_at",
            "support_ref",
        },
    )
    next_due = root["next_due_at"]
    if next_due is not None:
        next_due = _text(next_due)
        _instant(next_due)
    result = HKEXCarryForwardSupport(
        _text(root["last_approved_status"]),
        _text(root["last_verified_at"]),
        _text(root["coverage_gap_id"]),
        _text(root["warning_code"]),
        next_due,
        _text(root["support_ref"]),
    )
    _instant(result.last_verified_at)
    return result


def _decision_from_document(value: JsonValue, case_id: str) -> HKEXStateDecision:
    root = _object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "case_id",
            "outcome",
            "reason",
            "not_applicable",
            "branch_decisions",
            "component_state",
            "record_responsibility",
            "ordered_branch_ids",
            "source_failure_choice",
            "carry_forward_support",
            "rebuild_target_authorized",
            "repair_rejected",
            "search_record_authorized",
            "embedding_authorized",
            "release_authorized",
            "serving_authorized",
            "external_effects",
        },
    )
    _constant(root["schema_id"], "asklegal.hk-regulatory.state-decision-result")
    _constant(root["schema_version"], HKEX_STATE_DECISION_CONTRACT_VERSION)
    _constant(root["rule_id"], HKEX_STATE_DECISION_RULE_ID)
    _constant(root["case_id"], case_id)
    for key in (
        "rebuild_target_authorized",
        "search_record_authorized",
        "embedding_authorized",
        "release_authorized",
        "serving_authorized",
    ):
        _false(root[key])
    _constant(root["external_effects"], "NONE")
    component = root["component_state"]
    support = root["carry_forward_support"]
    return HKEXStateDecision(
        outcome=_enum(root["outcome"], HKEXStateConformanceOutcome),
        reason=_enum(root["reason"], HKEXStateDecisionReason),
        not_applicable=_boolean(root["not_applicable"]),
        branch_decisions=tuple(_branch_decision(item) for item in _array(root["branch_decisions"])),
        component_state=(None if component is None else _enum(component, HKEXComponentState)),
        record_responsibility=_enum(root["record_responsibility"], HKEXRecordResponsibility),
        ordered_branch_ids=_strings(root["ordered_branch_ids"], empty=True),
        source_failure_choice=_enum(root["source_failure_choice"], HKEXServingChoice),
        carry_forward_support=(None if support is None else _carry_support(support)),
        rebuild_target_authorized=False,
        repair_rejected=_boolean(root["repair_rejected"]),
    )


def _branch_decision(value: JsonValue) -> HKEXStateBranchDecision:
    root = _object(value)
    _exact_keys(
        root,
        {
            "branch_id",
            "state",
            "disposition",
            "processing_outcome",
            "reason",
            "applicability_context",
        },
    )
    context = root["applicability_context"]
    return HKEXStateBranchDecision(
        _text(root["branch_id"]),
        _enum(root["state"], HKEXBranchState),
        _enum(root["disposition"], HKEXMaterialDisposition),
        _enum(root["processing_outcome"], HKEXProcessingOutcome),
        _text(root["reason"]),
        None if context is None else _text(context),
    )


def _bindings(value: JsonValue) -> tuple[HKEXStateContractBinding, ...]:
    results: list[HKEXStateContractBinding] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"contract_id", "version", "fingerprint"})
        results.append(
            HKEXStateContractBinding(
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
    bindings: tuple[HKEXStateContractBinding, ...],
    package_fingerprint: str,
) -> None:
    expected_seed = checked_json_value(
        {
            "contract_id": "asklegal.hk-regulatory.state-decision-case",
            "contract_version": HKEX_STATE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_STATE_DECISION_RULE_ID,
        }
    )
    expected = (
        ("asklegal.hk-regulatory.conformance-universe", "1.0.0", package_fingerprint),
        ("asklegal.hk-regulatory.state-decision-case", "1.0.0", fingerprint(expected_seed)),
    )
    observed = tuple((item.contract_id, item.version, item.fingerprint) for item in bindings)
    if observed != expected:
        _fail()


def _pairs(value: JsonValue, case_id: str) -> tuple[HKEXStatePairMembership, ...]:
    results: list[HKEXStatePairMembership] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"pair_id", "role"})
        pair_id = _pattern(root["pair_id"], r"HKREG-PAIR-0(1[6-9]|2[0-4])")
        role = _text(root["role"])
        if role not in {"POSITIVE", "NEAR_MISS"}:
            _fail()
        results.append(HKEXStatePairMembership(pair_id, role))
    observed = tuple((item.pair_id, item.role) for item in results)
    if observed != _EXPECTED_PAIR_MEMBERSHIPS.get(case_id, ()):
        _fail(HKEXStateDecisionErrorCode.IDENTITY)
    return tuple(results)


def _packet(value: JsonValue, facts: HKEXStateDecisionFacts) -> HKEXStateEvidencePacket:
    root = _object(value)
    _exact_keys(root, {"slot_id", "state", "path", "role", "media_type", "content_fingerprint"})
    result = HKEXStateEvidencePacket(
        _text(root["slot_id"]),
        _text(root["state"]),
        _text(root["path"]),
        _text(root["role"]),
        _text(root["media_type"]),
        _fingerprint(root["content_fingerprint"]),
    )
    if (
        result.slot_id != "state-evidence"
        or result.state != "AVAILABLE"
        or result.role != "ORDINARY"
    ):
        _fail()
    if result.media_type != "application/json":
        _fail()
    if result.content_fingerprint != fingerprint(checked_json_value(_facts_document(facts))):
        _fail(HKEXStateDecisionErrorCode.FINGERPRINT)
    return result


def _facts_document(facts: HKEXStateDecisionFacts) -> dict[str, object]:
    return {
        "membership": facts.membership.value,
        "branches": [_request_document(item) for item in facts.branches],
        "complete_branch_set": facts.complete_branch_set,
        "wording_relationship": facts.wording_relationship.value,
        "limitation_metadata_complete": facts.limitation_metadata_complete,
        "effective_order_facts": [item.document() for item in facts.effective_order_facts],
        "carry_forward_support": (
            None if facts.carry_forward_support is None else facts.carry_forward_support.document()
        ),
        "other_required_gates_passed": facts.other_required_gates_passed,
        "repair_attempt": facts.repair_attempt.value,
        "unsupported_retirement_basis": facts.unsupported_retirement_basis.value,
    }


def _request_document(request: HKEXEffectiveStateRequest) -> dict[str, object]:
    return {
        "decision_id": request.decision_id,
        "branch_id": request.branch_id,
        "component_id": request.component_id,
        "scope_id": request.scope_id,
        "legal_location_id": request.legal_location_id,
        "cutoff": request.cutoff,
        "update_part_id": request.update_part_id,
        "update_source_ranges": list(request.update_source_ranges),
        "current_product_ranges": list(request.current_product_ranges),
        "basis": request.basis.value,
        "finality": request.finality.value,
        "effective_at": request.effective_at,
        "condition_operator": None
        if request.condition_operator is None
        else request.condition_operator.value,
        "conditions": [
            {
                "condition_id": item.condition_id,
                "registered_source_id": item.registered_source_id,
                "state": item.state.value,
                "evidence_refs": list(item.evidence_refs),
            }
            for item in request.conditions
        ],
        "transition_state": request.transition_state.value,
        "applicability_context": request.applicability_context,
        "retirement_evidence": request.retirement_evidence.value,
        "predecessor_branch_id": request.predecessor_branch_id,
        "successor_branch_ids": list(request.successor_branch_ids),
        "current_product_reconciliation": request.current_product_reconciliation.value,
        "uncertainty_codes": [item.value for item in request.uncertainty_codes],
        "source_failure_impact": request.source_failure_impact.value,
        "source_failure_choice": request.source_failure_choice.value,
        "source_rule_id": request.source_rule_id,
        "evidence_refs": list(request.evidence_refs),
        "evidence_fingerprint": request.evidence_fingerprint,
    }


def _checked(value: object) -> JsonValue:
    try:
        return checked_json_value(value)
    except ContractViolation as error:
        raise HKEXStateDecisionError(HKEXStateDecisionErrorCode.CONTRACT) from error


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not _is_json_object(value):
        _fail()
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    if not _is_json_array(value):
        _fail()
    return value


def _is_json_object(value: object) -> TypeIs[dict[str, JsonValue]]:
    return isinstance(value, dict)


def _is_json_array(value: object) -> TypeIs[list[JsonValue]]:
    return isinstance(value, list)


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        _fail()


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        _fail()
    return value


def _pattern(value: JsonValue, pattern: str) -> str:
    text = _text(value)
    if fullmatch(pattern, text) is None:
        _fail(HKEXStateDecisionErrorCode.IDENTITY)
    return text


def _strings(value: JsonValue, *, empty: bool = False) -> tuple[str, ...]:
    result = tuple(_text(item) for item in _array(value))
    if (not empty and not result) or len(result) != len(set(result)):
        _fail()
    return result


def _sorted_strings(value: JsonValue) -> tuple[str, ...]:
    result = _strings(value, empty=True)
    if result != tuple(sorted(result)):
        _fail()
    return result


def _nonempty_sorted(value: JsonValue) -> tuple[str, ...]:
    result = _strings(value)
    if result != tuple(sorted(result)):
        _fail()
    return result


def _enum[E: StrEnum](value: JsonValue, enum_type: type[E]) -> E:
    text = _text(value)
    try:
        return enum_type(text)
    except ValueError as error:
        raise HKEXStateDecisionError(HKEXStateDecisionErrorCode.CONTRACT) from error


def _fingerprint(value: JsonValue) -> str:
    text = _text(value)
    if fullmatch(_FINGERPRINT_PATTERN, text) is None:
        _fail(HKEXStateDecisionErrorCode.FINGERPRINT)
    return text


def _boolean(value: JsonValue) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _integer(value: JsonValue) -> int:
    if type(value) is not int or value < 0:
        _fail()
    return value


def _instant(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise HKEXStateDecisionError(HKEXStateDecisionErrorCode.CONTRACT) from error
    if result.tzinfo is None or result.utcoffset() is None:
        _fail()
    return result


def _constant(value: JsonValue, expected: object) -> None:
    if value != expected or type(value) is not type(expected):
        _fail()


def _true(value: JsonValue) -> None:
    if value is not True:
        _fail()


def _false(value: JsonValue) -> None:
    if value is not False:
        _fail()


def _fail(
    code: HKEXStateDecisionErrorCode = HKEXStateDecisionErrorCode.CONTRACT,
) -> Never:
    raise HKEXStateDecisionError(code)
