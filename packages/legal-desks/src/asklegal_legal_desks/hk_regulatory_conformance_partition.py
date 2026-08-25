"""ADR 0074/0075 exact-limit and official-partition conformance."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from re import fullmatch
from typing import Never, TypeIs

from asklegal_contracts import ContractViolation, canonicalize, fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_regulatory_english import (
    HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
    HKEX_ENGLISH_RECORD_RULE_ID,
    HKEXEnglishConstructionRequest,
    HKEXEnglishDisposition,
    HKEXEnglishReason,
    HKEXEnglishServingPart,
    construct_hkex_english_request,
    hkex_english_request_from_document,
)

HKEX_PARTITION_DECISION_RULE_ID = "HKREG-PARTITION-DECISION-001"
HKEX_PARTITION_DECISION_CONTRACT_VERSION = "1.0.0"
HKEX_PARTITION_DECISION_CASE_COUNT = 24

HKEX_PARTITION_MEASUREMENT_FIELDS = (
    "AUTHORITY_NOTE",
    "CONTEXT",
    "METADATA_COUNTRY",
    "METADATA_JURISDICTION",
    "METADATA_SOURCE",
    "METADATA_TYPE",
    "PRIMARY_PROJECTION",
    "REFERENCED_LOCATIONS",
)

_CASE_PATTERN = r"HKREG-DET-PAR-(0[0-1][0-9]|02[0-4])"
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_CONTRACT_BINDING_COUNT = 3
_UNLIMITED = 2_147_483_647
_MAX_REQUESTS = 2
_BRANCH_ISOLATION_COUNT = 2
_SYNTHETIC_PROFILE_ID = "synthetic-hkex-english-profile-1"
_SYNTHETIC_PROFILE_FINGERPRINT = f"sha256:{'a' * 64}"
_SYNTHETIC_TOKENIZER_ID = "synthetic-codepoint-counter-1"

_EXPECTED_PAIRS: dict[str, tuple[tuple[str, str], ...]] = {
    "HKREG-DET-PAR-001": (("HKREG-PAIR-038", "POSITIVE"),),
    "HKREG-DET-PAR-006": (("HKREG-PAIR-038", "NEAR_MISS"),),
    "HKREG-DET-PAR-016": (("HKREG-PAIR-039", "POSITIVE"),),
    "HKREG-DET-PAR-017": (("HKREG-PAIR-039", "NEAR_MISS"),),
    "HKREG-DET-PAR-022": (("HKREG-PAIR-040", "POSITIVE"),),
    "HKREG-DET-PAR-023": (("HKREG-PAIR-040", "NEAR_MISS"),),
}


class HKEXPartitionErrorCode(StrEnum):
    """Closed malformed permanent-case failures."""

    CONTRACT = "HKREG_PARTITION_CONTRACT_INVALID"
    IDENTITY = "HKREG_PARTITION_IDENTITY_INVALID"
    FINGERPRINT = "HKREG_PARTITION_FINGERPRINT_INVALID"


class HKEXPartitionError(ValueError):
    """One fail-closed permanent partition-case rejection."""

    code: HKEXPartitionErrorCode

    def __init__(self, code: HKEXPartitionErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKEXPartitionAssertionScope(StrEnum):
    """One orthogonal partition invariant selected without case identity."""

    EXACT_FIT = "EXACT_FIT"
    TOKEN_OVERFLOW = "TOKEN_OVERFLOW"
    METADATA_OVERFLOW = "METADATA_OVERFLOW"
    DUAL_OVERFLOW = "DUAL_OVERFLOW"
    MEASUREMENT_COMPLETENESS = "MEASUREMENT_COMPLETENESS"
    FINAL_LABELS = "FINAL_LABELS"
    CHILD_WHOLE = "CHILD_WHOLE"
    OVERSIZED_CHILD = "OVERSIZED_CHILD"
    LARGEST_FRONTIER = "LARGEST_FRONTIER"
    FEWEST_PARTS = "FEWEST_PARTS"
    EARLIEST_FULL = "EARLIEST_FULL"
    BRANCH_ISOLATION = "BRANCH_ISOLATION"
    FINAL_REMEASUREMENT = "FINAL_REMEASUREMENT"
    NORMAL_BOUNDARY = "NORMAL_BOUNDARY"
    UNRELATED_PACKING = "UNRELATED_PACKING"
    OFFICIAL_BOUNDARY = "OFFICIAL_BOUNDARY"
    ARBITRARY_PAGE = "ARBITRARY_PAGE"
    ARBITRARY_SENTENCE = "ARBITRARY_SENTENCE"
    ARBITRARY_SIZE = "ARBITRARY_SIZE"
    ARBITRARY_WINDOW = "ARBITRARY_WINDOW"
    CONTEXT_PRESERVATION = "CONTEXT_PRESERVATION"
    RECURSION = "RECURSION"
    INDIVISIBLE = "INDIVISIBLE"
    FIXED_METADATA = "FIXED_METADATA"


class HKEXPartitionCandidateCut(StrEnum):
    """Closed proposed cut bases, including the sole admissible basis."""

    NONE = "NONE"
    OFFICIAL_CHILD = "OFFICIAL_CHILD"
    CROSS_NORMAL_UNIT = "CROSS_NORMAL_UNIT"
    UNRELATED_PACKING = "UNRELATED_PACKING"
    PDF_PAGE = "PDF_PAGE"
    SENTENCE_OR_PUNCTUATION = "SENTENCE_OR_PUNCTUATION"
    WHITESPACE_TOKEN_OR_PREFERRED = "WHITESPACE_TOKEN_OR_PREFERRED"
    CHARACTER_VISUAL_OR_WINDOW = "CHARACTER_VISUAL_OR_WINDOW"
    REMOVE_CONTEXT = "REMOVE_CONTEXT"


class HKEXPartitionOutcome(StrEnum):
    """Effect-free permanent-case result."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


class HKEXPartitionReason(StrEnum):
    """Exact accepted partition consequences."""

    EXACT_FIT_UNSPLIT = "EXACT_FIT_UNSPLIT"
    TOKEN_OVERFLOW_PARTITIONED = "TOKEN_OVERFLOW_PARTITIONED"
    METADATA_OVERFLOW_PARTITIONED = "METADATA_OVERFLOW_PARTITIONED"
    DUAL_OVERFLOW_PARTITIONED = "DUAL_OVERFLOW_PARTITIONED"
    INCOMPLETE_MEASUREMENT_REJECTED = "INCOMPLETE_MEASUREMENT_REJECTED"
    LABEL_OVERFLOW_RECOMPUTED = "LABEL_OVERFLOW_RECOMPUTED"
    COMPLETE_CHILD_PRESERVED = "COMPLETE_CHILD_PRESERVED"
    OVERSIZED_CHILD_ONLY_REFINED = "OVERSIZED_CHILD_ONLY_REFINED"
    LARGEST_SAFE_FRONTIER_USED = "LARGEST_SAFE_FRONTIER_USED"
    FEWEST_PARTS_SELECTED = "FEWEST_PARTS_SELECTED"
    EARLIEST_FULL_SELECTED = "EARLIEST_FULL_SELECTED"
    BRANCH_DEPTHS_INDEPENDENT = "BRANCH_DEPTHS_INDEPENDENT"
    FINAL_LABELS_REMEASURED = "FINAL_LABELS_REMEASURED"
    CROSS_NORMAL_BOUNDARY_REJECTED = "CROSS_NORMAL_BOUNDARY_REJECTED"
    UNRELATED_PACKING_REJECTED = "UNRELATED_PACKING_REJECTED"
    OFFICIAL_BOUNDARY_PARTITIONED = "OFFICIAL_BOUNDARY_PARTITIONED"
    PDF_PAGE_CUT_REJECTED = "PDF_PAGE_CUT_REJECTED"
    SENTENCE_PUNCTUATION_CUT_REJECTED = "SENTENCE_PUNCTUATION_CUT_REJECTED"
    WHITESPACE_TOKEN_SIZE_CUT_REJECTED = "WHITESPACE_TOKEN_SIZE_CUT_REJECTED"
    CHARACTER_VISUAL_WINDOW_CUT_REJECTED = "CHARACTER_VISUAL_WINDOW_CUT_REJECTED"
    CONTEXT_REMOVAL_REJECTED = "CONTEXT_REMOVAL_REJECTED"
    RECURSIVE_OFFICIAL_PARTITIONED = "RECURSIVE_OFFICIAL_PARTITIONED"
    SMALLEST_COMPLETE_UNIT_QUARANTINED = "SMALLEST_COMPLETE_UNIT_QUARANTINED"
    FIXED_METADATA_OVER_LIMIT = "FIXED_METADATA_OVER_LIMIT"


@dataclass(frozen=True, slots=True)
class HKEXPartitionContractBinding:
    """One exact contract bound to a permanent case."""

    contract_id: str
    version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXPartitionPairMembership:
    """One exact high-risk pair role."""

    pair_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKEXPartitionEvidencePacket:
    """One proposal-safe synthetic fact packet."""

    slot_id: str
    state: str
    path: str
    role: str
    media_type: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXPartitionFacts:
    """Source-neutral requests plus independently declared proposal facts."""

    requests: tuple[HKEXEnglishConstructionRequest, ...]
    measurement_field_ids: tuple[str, ...]
    candidate_cut: HKEXPartitionCandidateCut
    candidate_official_boundary_proved: bool
    preliminary_part_count: int


@dataclass(frozen=True, slots=True)
class HKEXPartitionPartResult:
    """Exact final part identity, group, labels, and both measurements."""

    part_number: int
    total_parts: int
    record_unit_ids: tuple[str, ...]
    primary_source_unit_ids: tuple[str, ...]
    dependency_source_unit_ids: tuple[str, ...]
    text_fingerprint: str
    serving_payload_fingerprint: str
    text_tokens: int
    metadata_bytes: int
    text_limit: int
    metadata_limit: int
    fits: bool
    serving_label: str | None

    def document(self) -> dict[str, object]:
        """Return one strict JSON-compatible final part."""
        return {
            "part_number": self.part_number,
            "total_parts": self.total_parts,
            "record_unit_ids": list(self.record_unit_ids),
            "primary_source_unit_ids": list(self.primary_source_unit_ids),
            "dependency_source_unit_ids": list(self.dependency_source_unit_ids),
            "text_fingerprint": self.text_fingerprint,
            "serving_payload_fingerprint": self.serving_payload_fingerprint,
            "text_tokens": self.text_tokens,
            "metadata_bytes": self.metadata_bytes,
            "text_limit": self.text_limit,
            "metadata_limit": self.metadata_limit,
            "fits": self.fits,
            "serving_label": self.serving_label,
        }


@dataclass(frozen=True, slots=True)
class HKEXPartitionBranchResult:
    """One independently partitioned applicability branch."""

    branch_id: str
    root_record_unit_id: str
    disposition: str
    construction_reason: str
    unsplit_text_tokens: int
    unsplit_metadata_bytes: int
    text_limit: int
    metadata_limit: int
    parts: tuple[HKEXPartitionPartResult, ...]
    accounted_primary_source_unit_ids: tuple[str, ...]

    def document(self) -> dict[str, object]:
        """Return one exact branch result."""
        return {
            "branch_id": self.branch_id,
            "root_record_unit_id": self.root_record_unit_id,
            "disposition": self.disposition,
            "construction_reason": self.construction_reason,
            "unsplit_text_tokens": self.unsplit_text_tokens,
            "unsplit_metadata_bytes": self.unsplit_metadata_bytes,
            "text_limit": self.text_limit,
            "metadata_limit": self.metadata_limit,
            "parts": [part.document() for part in self.parts],
            "accounted_primary_source_unit_ids": list(self.accounted_primary_source_unit_ids),
        }


@dataclass(frozen=True, slots=True)
class HKEXPartitionDecision:
    """Complete deterministic partition consequence without serving authority."""

    outcome: HKEXPartitionOutcome
    reason: HKEXPartitionReason
    partition_required: bool
    measurement_complete: bool
    branch_results: tuple[HKEXPartitionBranchResult, ...]
    rejected_proposal_codes: tuple[str, ...]
    quarantined_branch_ids: tuple[str, ...]
    coverage_gap_ids: tuple[str, ...]

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return the exact effect-free result."""
        _text(case_id)
        return {
            "schema_id": "asklegal.hk-regulatory.partition-decision-result",
            "schema_version": HKEX_PARTITION_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_PARTITION_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "partition_required": self.partition_required,
            "measurement_complete": self.measurement_complete,
            "branch_results": [item.document() for item in self.branch_results],
            "rejected_proposal_codes": list(self.rejected_proposal_codes),
            "quarantined_branch_ids": list(self.quarantined_branch_ids),
            "coverage_gap_ids": list(self.coverage_gap_ids),
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "deployment_authorized": False,
            "external_effects": "NONE",
        }


@dataclass(frozen=True, slots=True)
class HKEXPartitionDecisionCase:
    """One strict decision-to-artifact partition conformance envelope."""

    case_id: str
    primary_coverage_cell_id: str
    pair_memberships: tuple[HKEXPartitionPairMembership, ...]
    assertion_scope: HKEXPartitionAssertionScope
    contract_bindings: tuple[HKEXPartitionContractBinding, ...]
    evidence_packet: HKEXPartitionEvidencePacket
    package_fingerprint: str
    title: str
    purpose: str
    expected_decision: HKEXPartitionDecision
    facts: HKEXPartitionFacts


@dataclass(frozen=True, slots=True)
class HKEXPartitionDecisionReport:
    """Complete expected-versus-observed partition report."""

    case_id: str
    assertion_scope: HKEXPartitionAssertionScope
    observed_decision: HKEXPartitionDecision
    expected_decision: HKEXPartitionDecision
    conformance_status: str

    def document(self) -> dict[str, object]:
        """Return one strict effect-free report."""
        return {
            "schema_id": "asklegal.hk-regulatory.partition-decision-report",
            "schema_version": HKEX_PARTITION_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_PARTITION_DECISION_RULE_ID,
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
    case_id: str
    primary_cell_id: str
    pairs: tuple[HKEXPartitionPairMembership, ...]
    scope: HKEXPartitionAssertionScope
    bindings: tuple[HKEXPartitionContractBinding, ...]
    package_fingerprint: str


class _SyntheticCodepointCounter:
    """Frozen fixture counter, explicitly not an admitted tokenizer."""

    profile_id = _SYNTHETIC_PROFILE_ID
    profile_fingerprint = _SYNTHETIC_PROFILE_FINGERPRINT
    tokenizer_id = _SYNTHETIC_TOKENIZER_ID

    def count(self, text: str) -> int:
        """Count Unicode code points exactly for synthetic cases."""
        return len(text)


def hkex_partition_decision_case_from_document(document: object) -> HKEXPartitionDecisionCase:
    """Strictly decode and fingerprint one permanent partition case."""
    root = _object(_checked(document))
    _exact_keys(root, _CASE_FIELDS)
    header = _case_header(root)
    _validate_declarations(root, header.bindings)
    facts = _facts(root["facts"])
    packet = _packet(root["evidence_packet"], facts)
    expected = _decision_from_document(root["expected_decision"], header.case_id)
    _validate_case_fingerprint(root)
    return HKEXPartitionDecisionCase(
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


def decide_hkex_partition_case(case: HKEXPartitionDecisionCase) -> HKEXPartitionDecision:
    """Run the accepted ADR 0073 partitioner from ordinary facts, never case ID."""
    if type(case) is not HKEXPartitionDecisionCase:
        _fail()
    facts = case.facts
    incomplete = _incomplete_measurement_decision(facts)
    if incomplete is not None:
        return incomplete
    rejected = _rejected_cut(facts.candidate_cut)
    if rejected is not None:
        reason, code = rejected
        return _terminal(HKEXPartitionOutcome.BLOCK, reason, rejected=(code,))
    _validate_candidate(facts)
    branches = tuple(_run_branch(request) for request in facts.requests)
    quarantined = tuple(
        item.branch_id for item in branches if item.disposition == HKEXEnglishDisposition.QUARANTINE
    )
    if quarantined:
        return _quarantine_decision(case.assertion_scope, facts, branches, quarantined)
    if any(item.disposition != HKEXEnglishDisposition.PASS for item in branches):
        _fail()
    reason = _passing_reason(case.assertion_scope, facts, branches)
    partition_required = any(len(item.parts) > 1 for item in branches)
    return HKEXPartitionDecision(
        outcome=HKEXPartitionOutcome.PASS,
        reason=reason,
        partition_required=partition_required,
        measurement_complete=True,
        branch_results=branches,
        rejected_proposal_codes=(),
        quarantined_branch_ids=(),
        coverage_gap_ids=(),
    )


def _incomplete_measurement_decision(
    facts: HKEXPartitionFacts,
) -> HKEXPartitionDecision | None:
    if facts.measurement_field_ids == HKEX_PARTITION_MEASUREMENT_FIELDS:
        return None
    missing = tuple(
        item
        for item in HKEX_PARTITION_MEASUREMENT_FIELDS
        if item not in facts.measurement_field_ids
    )
    return _terminal(
        HKEXPartitionOutcome.BLOCK,
        HKEXPartitionReason.INCOMPLETE_MEASUREMENT_REJECTED,
        rejected=tuple(f"MISSING_{item}" for item in missing),
        measurement_complete=False,
    )


def _validate_candidate(facts: HKEXPartitionFacts) -> None:
    official = facts.candidate_cut is HKEXPartitionCandidateCut.OFFICIAL_CHILD
    if official != facts.candidate_official_boundary_proved:
        _fail()


def _quarantine_decision(
    scope: HKEXPartitionAssertionScope,
    facts: HKEXPartitionFacts,
    branches: tuple[HKEXPartitionBranchResult, ...],
    quarantined: tuple[str, ...],
) -> HKEXPartitionDecision:
    fixed = tuple(_fixed_metadata_exceeds_limit(request) for request in facts.requests)
    if scope is HKEXPartitionAssertionScope.FIXED_METADATA and all(fixed):
        reason = HKEXPartitionReason.FIXED_METADATA_OVER_LIMIT
    elif scope is HKEXPartitionAssertionScope.INDIVISIBLE and not any(fixed):
        reason = HKEXPartitionReason.SMALLEST_COMPLETE_UNIT_QUARANTINED
    else:
        _fail()
    return HKEXPartitionDecision(
        outcome=HKEXPartitionOutcome.QUARANTINE,
        reason=reason,
        partition_required=True,
        measurement_complete=True,
        branch_results=branches,
        rejected_proposal_codes=(),
        quarantined_branch_ids=quarantined,
        coverage_gap_ids=tuple(f"HKREG-GAP:{item}" for item in quarantined),
    )


def run_hkex_partition_case(case: HKEXPartitionDecisionCase) -> HKEXPartitionDecisionReport:
    """Compare the fact-derived result with frozen complete truth."""
    observed = decide_hkex_partition_case(case)
    return HKEXPartitionDecisionReport(
        case.case_id,
        case.assertion_scope,
        observed,
        case.expected_decision,
        "PASS" if observed == case.expected_decision else "FAIL",
    )


def _run_branch(request: HKEXEnglishConstructionRequest) -> HKEXPartitionBranchResult:
    _validate_synthetic_request(request)
    proof = construct_hkex_english_request(request, _SyntheticCodepointCounter())
    if len(proof.record_results) != 1:
        _fail()
    record = proof.record_results[0]
    unsplit = _unlimited_part(request)
    parts = tuple(_part_result(part) for part in record.parts)
    return HKEXPartitionBranchResult(
        request.tree.branch_id,
        record.root_record_unit_id,
        record.disposition.value,
        record.reason.value,
        unsplit.measurement.text_tokens,
        unsplit.measurement.metadata_bytes,
        request.profile.max_text_tokens,
        request.profile.max_metadata_bytes,
        parts,
        record.accounted_primary_source_unit_ids,
    )


def _unlimited_part(request: HKEXEnglishConstructionRequest) -> HKEXEnglishServingPart:
    unlimited = HKEXEnglishConstructionRequest(
        request.tree,
        replace(
            request.profile,
            max_text_tokens=_UNLIMITED,
            max_metadata_bytes=_UNLIMITED,
        ),
        request.effective_context,
    )
    proof = construct_hkex_english_request(unlimited, _SyntheticCodepointCounter())
    if len(proof.record_results) != 1 or len(proof.record_results[0].parts) != 1:
        _fail()
    return proof.record_results[0].parts[0]


def _part_result(part: HKEXEnglishServingPart) -> HKEXPartitionPartResult:
    label = None
    if part.total_parts > 1:
        label = f"Serving part: {part.part_number} of {part.total_parts}"
        if label not in part.text:
            _fail()
    return HKEXPartitionPartResult(
        part.part_number,
        part.total_parts,
        part.record_unit_ids,
        part.primary_source_unit_ids,
        part.dependency_source_unit_ids,
        part.text_fingerprint,
        part.serving_payload_fingerprint,
        part.measurement.text_tokens,
        part.measurement.metadata_bytes,
        part.measurement.text_limit,
        part.measurement.metadata_limit,
        part.measurement.fits,
        label,
    )


def _passing_reason(
    scope: HKEXPartitionAssertionScope,
    facts: HKEXPartitionFacts,
    branches: tuple[HKEXPartitionBranchResult, ...],
) -> HKEXPartitionReason:
    validator = _PASSING_VALIDATORS.get(scope)
    if validator is None:
        _fail()
    validator(facts, branches)
    if any(not part.fits for branch in branches for part in branch.parts):
        _fail()
    return _PASSING_REASONS[scope]


def _validate_exact_fit(
    _facts: HKEXPartitionFacts, branches: tuple[HKEXPartitionBranchResult, ...]
) -> None:
    if len(branches) != 1 or _is_partitioned(branches):
        _fail()
    branch = branches[0]
    if branch.unsplit_text_tokens != branch.text_limit or (
        branch.unsplit_metadata_bytes != branch.metadata_limit
    ):
        _fail()


def _validate_token_overflow(
    _facts: HKEXPartitionFacts, branches: tuple[HKEXPartitionBranchResult, ...]
) -> None:
    if (
        not _is_partitioned(branches)
        or not _token_overflow(branches)
        or (_metadata_overflow(branches))
    ):
        _fail()


def _validate_metadata_overflow(
    _facts: HKEXPartitionFacts, branches: tuple[HKEXPartitionBranchResult, ...]
) -> None:
    if (
        not _is_partitioned(branches)
        or _token_overflow(branches)
        or not (_metadata_overflow(branches))
    ):
        _fail()


def _validate_dual_overflow(
    _facts: HKEXPartitionFacts, branches: tuple[HKEXPartitionBranchResult, ...]
) -> None:
    if (
        not _is_partitioned(branches)
        or not _token_overflow(branches)
        or not (_metadata_overflow(branches))
    ):
        _fail()


def _validate_partitioned(
    _facts: HKEXPartitionFacts, branches: tuple[HKEXPartitionBranchResult, ...]
) -> None:
    if not _is_partitioned(branches):
        _fail()


def _validate_final_labels(
    facts: HKEXPartitionFacts, branches: tuple[HKEXPartitionBranchResult, ...]
) -> None:
    _validate_partitioned(facts, branches)
    if facts.preliminary_part_count <= 0:
        _fail()


def _validate_branch_isolation(
    _facts: HKEXPartitionFacts, branches: tuple[HKEXPartitionBranchResult, ...]
) -> None:
    counts = {len(item.parts) for item in branches}
    if len(branches) != _BRANCH_ISOLATION_COUNT or len(counts) != _BRANCH_ISOLATION_COUNT:
        _fail()


def _is_partitioned(branches: tuple[HKEXPartitionBranchResult, ...]) -> bool:
    return any(len(item.parts) > 1 for item in branches)


def _token_overflow(branches: tuple[HKEXPartitionBranchResult, ...]) -> bool:
    return any(item.unsplit_text_tokens > item.text_limit for item in branches)


def _metadata_overflow(branches: tuple[HKEXPartitionBranchResult, ...]) -> bool:
    return any(item.unsplit_metadata_bytes > item.metadata_limit for item in branches)


type _PassingValidator = Callable[[HKEXPartitionFacts, tuple[HKEXPartitionBranchResult, ...]], None]

_PASSING_VALIDATORS: dict[HKEXPartitionAssertionScope, _PassingValidator] = {
    HKEXPartitionAssertionScope.EXACT_FIT: _validate_exact_fit,
    HKEXPartitionAssertionScope.TOKEN_OVERFLOW: _validate_token_overflow,
    HKEXPartitionAssertionScope.METADATA_OVERFLOW: _validate_metadata_overflow,
    HKEXPartitionAssertionScope.DUAL_OVERFLOW: _validate_dual_overflow,
    HKEXPartitionAssertionScope.FINAL_LABELS: _validate_final_labels,
    HKEXPartitionAssertionScope.CHILD_WHOLE: _validate_partitioned,
    HKEXPartitionAssertionScope.OVERSIZED_CHILD: _validate_partitioned,
    HKEXPartitionAssertionScope.LARGEST_FRONTIER: _validate_partitioned,
    HKEXPartitionAssertionScope.FEWEST_PARTS: _validate_partitioned,
    HKEXPartitionAssertionScope.EARLIEST_FULL: _validate_partitioned,
    HKEXPartitionAssertionScope.BRANCH_ISOLATION: _validate_branch_isolation,
    HKEXPartitionAssertionScope.FINAL_REMEASUREMENT: _validate_partitioned,
    HKEXPartitionAssertionScope.OFFICIAL_BOUNDARY: _validate_partitioned,
    HKEXPartitionAssertionScope.RECURSION: _validate_partitioned,
}


_PASSING_REASONS = {
    HKEXPartitionAssertionScope.EXACT_FIT: HKEXPartitionReason.EXACT_FIT_UNSPLIT,
    HKEXPartitionAssertionScope.TOKEN_OVERFLOW: HKEXPartitionReason.TOKEN_OVERFLOW_PARTITIONED,
    HKEXPartitionAssertionScope.METADATA_OVERFLOW: (
        HKEXPartitionReason.METADATA_OVERFLOW_PARTITIONED
    ),
    HKEXPartitionAssertionScope.DUAL_OVERFLOW: HKEXPartitionReason.DUAL_OVERFLOW_PARTITIONED,
    HKEXPartitionAssertionScope.FINAL_LABELS: HKEXPartitionReason.LABEL_OVERFLOW_RECOMPUTED,
    HKEXPartitionAssertionScope.CHILD_WHOLE: HKEXPartitionReason.COMPLETE_CHILD_PRESERVED,
    HKEXPartitionAssertionScope.OVERSIZED_CHILD: (HKEXPartitionReason.OVERSIZED_CHILD_ONLY_REFINED),
    HKEXPartitionAssertionScope.LARGEST_FRONTIER: (HKEXPartitionReason.LARGEST_SAFE_FRONTIER_USED),
    HKEXPartitionAssertionScope.FEWEST_PARTS: HKEXPartitionReason.FEWEST_PARTS_SELECTED,
    HKEXPartitionAssertionScope.EARLIEST_FULL: HKEXPartitionReason.EARLIEST_FULL_SELECTED,
    HKEXPartitionAssertionScope.BRANCH_ISOLATION: (HKEXPartitionReason.BRANCH_DEPTHS_INDEPENDENT),
    HKEXPartitionAssertionScope.FINAL_REMEASUREMENT: (HKEXPartitionReason.FINAL_LABELS_REMEASURED),
    HKEXPartitionAssertionScope.OFFICIAL_BOUNDARY: (
        HKEXPartitionReason.OFFICIAL_BOUNDARY_PARTITIONED
    ),
    HKEXPartitionAssertionScope.RECURSION: HKEXPartitionReason.RECURSIVE_OFFICIAL_PARTITIONED,
}


def _fixed_metadata_exceeds_limit(request: HKEXEnglishConstructionRequest) -> bool:
    profile = request.profile
    payload = checked_json_value(
        {
            "authority_note": profile.authority_note,
            "country": profile.country,
            "jurisdiction": profile.jurisdiction,
            "source": profile.source,
            "text": "",
            "type": profile.material_type,
        }
    )
    return len(canonicalize(payload)) > profile.max_metadata_bytes


def _rejected_cut(
    cut: HKEXPartitionCandidateCut,
) -> tuple[HKEXPartitionReason, str] | None:
    return {
        HKEXPartitionCandidateCut.CROSS_NORMAL_UNIT: (
            HKEXPartitionReason.CROSS_NORMAL_BOUNDARY_REJECTED,
            "CROSS_NORMAL_UNIT",
        ),
        HKEXPartitionCandidateCut.UNRELATED_PACKING: (
            HKEXPartitionReason.UNRELATED_PACKING_REJECTED,
            "UNRELATED_PACKING",
        ),
        HKEXPartitionCandidateCut.PDF_PAGE: (
            HKEXPartitionReason.PDF_PAGE_CUT_REJECTED,
            "PDF_PAGE",
        ),
        HKEXPartitionCandidateCut.SENTENCE_OR_PUNCTUATION: (
            HKEXPartitionReason.SENTENCE_PUNCTUATION_CUT_REJECTED,
            "SENTENCE_OR_PUNCTUATION",
        ),
        HKEXPartitionCandidateCut.WHITESPACE_TOKEN_OR_PREFERRED: (
            HKEXPartitionReason.WHITESPACE_TOKEN_SIZE_CUT_REJECTED,
            "WHITESPACE_TOKEN_OR_PREFERRED",
        ),
        HKEXPartitionCandidateCut.CHARACTER_VISUAL_OR_WINDOW: (
            HKEXPartitionReason.CHARACTER_VISUAL_WINDOW_CUT_REJECTED,
            "CHARACTER_VISUAL_OR_WINDOW",
        ),
        HKEXPartitionCandidateCut.REMOVE_CONTEXT: (
            HKEXPartitionReason.CONTEXT_REMOVAL_REJECTED,
            "REMOVE_CONTEXT",
        ),
    }.get(cut)


def _terminal(
    outcome: HKEXPartitionOutcome,
    reason: HKEXPartitionReason,
    *,
    rejected: tuple[str, ...],
    measurement_complete: bool = True,
) -> HKEXPartitionDecision:
    return HKEXPartitionDecision(
        outcome=outcome,
        reason=reason,
        partition_required=False,
        measurement_complete=measurement_complete,
        branch_results=(),
        rejected_proposal_codes=rejected,
        quarantined_branch_ids=(),
        coverage_gap_ids=(),
    )


def _validate_synthetic_request(request: HKEXEnglishConstructionRequest) -> None:
    profile = request.profile
    if (
        profile.profile_id != _SYNTHETIC_PROFILE_ID
        or profile.profile_fingerprint != _SYNTHETIC_PROFILE_FINGERPRINT
        or profile.tokenizer_id != _SYNTHETIC_TOKENIZER_ID
        or request.tree.source_rule_id != HKEX_ENGLISH_RECORD_RULE_ID
    ):
        _fail()


_FACT_FIELDS = {
    "requests",
    "measurement_field_ids",
    "candidate_cut",
    "candidate_official_boundary_proved",
    "preliminary_part_count",
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
    "partition_required",
    "measurement_complete",
    "branch_results",
    "rejected_proposal_codes",
    "quarantined_branch_ids",
    "coverage_gap_ids",
    "search_record_authorized",
    "embedding_authorized",
    "release_authorized",
    "serving_authorized",
    "deployment_authorized",
    "external_effects",
}


def _case_header(root: dict[str, JsonValue]) -> _CaseHeader:
    _constant(root["schema_id"], "asklegal.hk-regulatory.partition-decision-case")
    _constant(root["schema_version"], HKEX_PARTITION_DECISION_CONTRACT_VERSION)
    _constant(root["package_contract_version"], "1.0.0")
    case_id = _pattern(root["case_id"], _CASE_PATTERN)
    suffix = case_id.rsplit("-", maxsplit=1)[1]
    _constant(root["suite_layer"], "DECISION_TO_ARTIFACT")
    _constant(root["primary_checkpoint"], "PARTITIONING")
    _true(root["frozen"])
    _constant(root["synthetic_evidence_class"], "SYNTHETIC_NO_REAL_AUTHORITY")
    _constant(root["synthetic_cutoff"], "2026-08-24T00:00:00Z")
    _constant(root["scope_id"], "HKEX_CROSS_BOARD")
    _constant(root["prior_state"], "SYNTHETIC_ACCEPTED_PREDECESSOR")
    primary = _strings(root["primary_coverage_cell_ids"])
    if primary != (f"HKREG-COV-DPAR-{suffix}",):
        _fail(HKEXPartitionErrorCode.IDENTITY)
    bindings = _bindings(root["contract_bindings"])
    package_fingerprint = _fingerprint(root["package_fingerprint"])
    _validate_bindings(bindings, package_fingerprint)
    return _CaseHeader(
        case_id,
        primary[0],
        _pairs(root["pair_memberships"], case_id),
        _enum(root["assertion_scope"], HKEXPartitionAssertionScope),
        bindings,
        package_fingerprint,
    )


def _validate_declarations(
    root: dict[str, JsonValue], bindings: tuple[HKEXPartitionContractBinding, ...]
) -> None:
    _sorted_strings(root["secondary_coverage_cell_ids"])
    if _strings(root["declared_input_inventory"]) != ("partition-evidence",):
        _fail()
    if _strings(root["declared_reference_inventory"]) != tuple(
        item.contract_id for item in bindings
    ):
        _fail()
    if _strings(root["declared_expected_inventory"]) != ("PARTITION_DECISION_REPORT",):
        _fail()
    if _strings(root["required_result_dimensions"]) != (
        "BOTH_EXACT_LIMITS",
        "COVERAGE_GAP",
        "FINAL_LABELS",
        "OFFICIAL_STRUCTURE",
        "PARTITION_OPTIMIZATION",
        "PROCESSING",
        "QUARANTINE",
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


def _validate_case_fingerprint(root: dict[str, JsonValue]) -> None:
    case_fingerprint = _fingerprint(root["case_fingerprint"])
    projection = dict(root)
    projection.pop("case_fingerprint")
    if fingerprint(checked_json_value(projection)) != case_fingerprint:
        _fail(HKEXPartitionErrorCode.FINGERPRINT)


def _facts(value: JsonValue) -> HKEXPartitionFacts:
    root = _object(value)
    _exact_keys(root, _FACT_FIELDS)
    requests = tuple(hkex_english_request_from_document(item) for item in _array(root["requests"]))
    if not requests or len(requests) > _MAX_REQUESTS:
        _fail()
    result = HKEXPartitionFacts(
        requests,
        _strings(root["measurement_field_ids"], empty=True),
        _enum(root["candidate_cut"], HKEXPartitionCandidateCut),
        _boolean(root["candidate_official_boundary_proved"]),
        _nonnegative_integer(root["preliminary_part_count"]),
    )
    if result.measurement_field_ids != tuple(sorted(result.measurement_field_ids)):
        _fail()
    for request in requests:
        _validate_synthetic_request(request)
    return result


def _facts_document(facts: HKEXPartitionFacts) -> dict[str, object]:
    return {
        "requests": [request.document() for request in facts.requests],
        "measurement_field_ids": list(facts.measurement_field_ids),
        "candidate_cut": facts.candidate_cut.value,
        "candidate_official_boundary_proved": facts.candidate_official_boundary_proved,
        "preliminary_part_count": facts.preliminary_part_count,
    }


def _decision_from_document(value: JsonValue, case_id: str) -> HKEXPartitionDecision:
    root = _object(value)
    _exact_keys(root, _DECISION_FIELDS)
    _constant(root["schema_id"], "asklegal.hk-regulatory.partition-decision-result")
    _constant(root["schema_version"], HKEX_PARTITION_DECISION_CONTRACT_VERSION)
    _constant(root["rule_id"], HKEX_PARTITION_DECISION_RULE_ID)
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
    return HKEXPartitionDecision(
        _enum(root["outcome"], HKEXPartitionOutcome),
        _enum(root["reason"], HKEXPartitionReason),
        _boolean(root["partition_required"]),
        _boolean(root["measurement_complete"]),
        tuple(_branch_result(item) for item in _array(root["branch_results"])),
        _strings(root["rejected_proposal_codes"], empty=True),
        _strings(root["quarantined_branch_ids"], empty=True),
        _strings(root["coverage_gap_ids"], empty=True),
    )


def _branch_result(value: JsonValue) -> HKEXPartitionBranchResult:
    root = _object(value)
    _exact_keys(
        root,
        {
            "branch_id",
            "root_record_unit_id",
            "disposition",
            "construction_reason",
            "unsplit_text_tokens",
            "unsplit_metadata_bytes",
            "text_limit",
            "metadata_limit",
            "parts",
            "accounted_primary_source_unit_ids",
        },
    )
    return HKEXPartitionBranchResult(
        _text(root["branch_id"]),
        _text(root["root_record_unit_id"]),
        _enum(root["disposition"], HKEXEnglishDisposition).value,
        _enum(root["construction_reason"], HKEXEnglishReason).value,
        _nonnegative_integer(root["unsplit_text_tokens"]),
        _nonnegative_integer(root["unsplit_metadata_bytes"]),
        _positive_integer(root["text_limit"]),
        _positive_integer(root["metadata_limit"]),
        tuple(_part_result_from_document(item) for item in _array(root["parts"])),
        _strings(root["accounted_primary_source_unit_ids"], empty=True),
    )


def _part_result_from_document(value: JsonValue) -> HKEXPartitionPartResult:
    root = _object(value)
    _exact_keys(
        root,
        {
            "part_number",
            "total_parts",
            "record_unit_ids",
            "primary_source_unit_ids",
            "dependency_source_unit_ids",
            "text_fingerprint",
            "serving_payload_fingerprint",
            "text_tokens",
            "metadata_bytes",
            "text_limit",
            "metadata_limit",
            "fits",
            "serving_label",
        },
    )
    part_number = _positive_integer(root["part_number"])
    total_parts = _positive_integer(root["total_parts"])
    if part_number > total_parts:
        _fail()
    label = _nullable_text(root["serving_label"])
    expected_label = None if total_parts == 1 else f"Serving part: {part_number} of {total_parts}"
    if label != expected_label:
        _fail()
    return HKEXPartitionPartResult(
        part_number,
        total_parts,
        _strings(root["record_unit_ids"]),
        _strings(root["primary_source_unit_ids"]),
        _strings(root["dependency_source_unit_ids"], empty=True),
        _fingerprint(root["text_fingerprint"]),
        _fingerprint(root["serving_payload_fingerprint"]),
        _nonnegative_integer(root["text_tokens"]),
        _nonnegative_integer(root["metadata_bytes"]),
        _positive_integer(root["text_limit"]),
        _positive_integer(root["metadata_limit"]),
        _boolean(root["fits"]),
        label,
    )


def _bindings(value: JsonValue) -> tuple[HKEXPartitionContractBinding, ...]:
    results: list[HKEXPartitionContractBinding] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"contract_id", "version", "fingerprint"})
        results.append(
            HKEXPartitionContractBinding(
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
    bindings: tuple[HKEXPartitionContractBinding, ...], package_fingerprint: str
) -> None:
    seed = checked_json_value(
        {
            "contract_id": "asklegal.hk-regulatory.partition-decision-case",
            "contract_version": HKEX_PARTITION_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_PARTITION_DECISION_RULE_ID,
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
            "asklegal.hk-regulatory.partition-decision-case",
            HKEX_PARTITION_DECISION_CONTRACT_VERSION,
            fingerprint(seed),
        ),
        (
            "asklegal.hk-regulatory.english-record",
            HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            fingerprint(english_seed),
        ),
    )
    if tuple((item.contract_id, item.version, item.fingerprint) for item in bindings) != expected:
        _fail()


def _pairs(value: JsonValue, case_id: str) -> tuple[HKEXPartitionPairMembership, ...]:
    results: list[HKEXPartitionPairMembership] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"pair_id", "role"})
        pair_id = _pattern(root["pair_id"], r"HKREG-PAIR-0(38|39|40)")
        role = _text(root["role"])
        if role not in {"POSITIVE", "NEAR_MISS"}:
            _fail()
        results.append(HKEXPartitionPairMembership(pair_id, role))
    if tuple((item.pair_id, item.role) for item in results) != _EXPECTED_PAIRS.get(case_id, ()):
        _fail(HKEXPartitionErrorCode.IDENTITY)
    return tuple(results)


def _packet(value: JsonValue, facts: HKEXPartitionFacts) -> HKEXPartitionEvidencePacket:
    root = _object(value)
    _exact_keys(root, {"slot_id", "state", "path", "role", "media_type", "content_fingerprint"})
    packet = HKEXPartitionEvidencePacket(
        _text(root["slot_id"]),
        _text(root["state"]),
        _text(root["path"]),
        _text(root["role"]),
        _text(root["media_type"]),
        _fingerprint(root["content_fingerprint"]),
    )
    if (
        packet.slot_id != "partition-evidence"
        or packet.state != "AVAILABLE"
        or packet.role != "ORDINARY"
        or packet.media_type != "application/json"
    ):
        _fail()
    if packet.content_fingerprint != fingerprint(checked_json_value(_facts_document(facts))):
        _fail(HKEXPartitionErrorCode.FINGERPRINT)
    return packet


def _checked(value: object) -> JsonValue:
    try:
        return checked_json_value(value)
    except ContractViolation as error:
        raise HKEXPartitionError(HKEXPartitionErrorCode.CONTRACT) from error


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


def _nullable_text(value: JsonValue) -> str | None:
    return None if value is None else _text(value)


def _positive_integer(value: JsonValue) -> int:
    if type(value) is not int or value <= 0:
        _fail()
    return value


def _nonnegative_integer(value: JsonValue) -> int:
    if type(value) is not int or value < 0:
        _fail()
    return value


def _pattern(value: JsonValue, pattern: str) -> str:
    result = _text(value)
    if fullmatch(pattern, result) is None:
        _fail(HKEXPartitionErrorCode.IDENTITY)
    return result


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
        raise HKEXPartitionError(HKEXPartitionErrorCode.CONTRACT) from error


def _fingerprint(value: JsonValue) -> str:
    result = _text(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        _fail(HKEXPartitionErrorCode.FINGERPRINT)
    return result


def _boolean(value: JsonValue) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _constant(value: JsonValue, expected: object) -> None:
    if value != expected or type(value) is not type(expected):
        _fail()


def _true(value: JsonValue) -> None:
    if value is not True:
        _fail()


def _false(value: JsonValue) -> None:
    if value is not False:
        _fail()


def _fail(code: HKEXPartitionErrorCode = HKEXPartitionErrorCode.CONTRACT) -> Never:
    raise HKEXPartitionError(code)
