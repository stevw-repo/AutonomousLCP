"""Deterministic ADR 0062 Hong Kong Case Proposition coverage accounting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from typing import TypeIs

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

HK_CASE_COVERAGE_LEDGER_RULE_ID = "HKCASE-PROP-COVERAGE-LEDGER-001"
HK_CASE_COVERAGE_LEDGER_CONTRACT_VERSION = "1.0.0"

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_IDENTITY_PATTERN = r"[a-z][a-z0-9_]{2,95}"
_ADOPTION_RANGE_COUNT = 2


class HKCaseLedgerErrorCode(StrEnum):
    """Closed malformed ledger request failures."""

    CONTRACT = "HK_CASE_LEDGER_CONTRACT_INVALID"
    IDENTITY = "HK_CASE_LEDGER_IDENTITY_INVALID"
    FINGERPRINT = "HK_CASE_LEDGER_FINGERPRINT_INVALID"


class HKCaseLedgerError(ValueError):
    """One fail-closed malformed ledger request."""

    code: HKCaseLedgerErrorCode

    def __init__(self, code: HKCaseLedgerErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKCaseOpinionRole(StrEnum):
    """Source-supported delivered-opinion roles."""

    AGREEMENT_ONLY = "AGREEMENT_ONLY"
    CONCURRENCE = "CONCURRENCE"
    COURT = "COURT"
    DISSENT = "DISSENT"
    JOINT = "JOINT"
    LEAD = "LEAD"
    OTHER = "OTHER"


class HKCaseCoverageUnitKind(StrEnum):
    """Exhaustive structural unit classes required by ADR 0062."""

    APPEARANCE = "APPEARANCE"
    APPENDIX = "APPENDIX"
    COVER = "COVER"
    DISPOSITION = "DISPOSITION"
    FOOTNOTE = "FOOTNOTE"
    HEADING = "HEADING"
    ORDER = "ORDER"
    PARAGRAPH = "PARAGRAPH"
    QUOTED_BLOCK = "QUOTED_BLOCK"
    SCHEDULE = "SCHEDULE"
    TABLE = "TABLE"


class HKCaseUnitResolution(StrEnum):
    """One exact final unit resolution state."""

    BLOCKED = "BLOCKED"
    QUARANTINED = "QUARANTINED"
    RESOLVED = "RESOLVED"


class HKCasePrimaryUse(StrEnum):
    """One exact primary use for a resolved unit."""

    CONTEXT_EVIDENCE = "CONTEXT_EVIDENCE"
    NON_PROPOSITIONAL = "NON_PROPOSITIONAL"
    PROPOSITION_EVIDENCE = "PROPOSITION_EVIDENCE"


class HKCaseNonPropositionalReason(StrEnum):
    """Closed minimum ADR 0062 non-propositional reason families."""

    AGREEMENT_ONLY_OPINION = "AGREEMENT_ONLY_OPINION"
    NON_MATERIAL_DISCUSSION = "NON_MATERIAL_DISCUSSION"
    OUTCOME_WITHOUT_LEGAL_ANSWER = "OUTCOME_WITHOUT_LEGAL_ANSWER"
    SOURCE_SCAFFOLDING = "SOURCE_SCAFFOLDING"
    TREATMENT_ONLY_REASONING = "TREATMENT_ONLY_REASONING"
    UNADOPTED_CITATION_OR_QUOTATION = "UNADOPTED_CITATION_OR_QUOTATION"
    UNADOPTED_PARTY_POSITION = "UNADOPTED_PARTY_POSITION"
    UNUSED_PROCEDURAL_OR_FACTUAL_NARRATIVE = "UNUSED_PROCEDURAL_OR_FACTUAL_NARRATIVE"


class HKCaseEvidenceRole(StrEnum):
    """Closed evidence roles within an accepted proposition."""

    ANSWER = "ANSWER"
    APPLICATION = "APPLICATION"
    ATTRIBUTION = "ATTRIBUTION"
    CONTEXT = "CONTEXT"
    ISSUE = "ISSUE"
    QUALIFICATION = "QUALIFICATION"
    QUOTATION = "QUOTATION"
    RESULT = "RESULT"
    SUPPLEMENTARY = "SUPPLEMENTARY"


class HKCaseDependencyKind(StrEnum):
    """Recorded context and cross-opinion adoption dependencies."""

    CONTEXT = "CONTEXT"
    CROSS_OPINION_ADOPTION = "CROSS_OPINION_ADOPTION"


class HKCaseCandidateOutcome(StrEnum):
    """Complete candidate disposition classes."""

    ACCEPTED = "ACCEPTED"
    BLOCKED = "BLOCKED"
    MERGED = "MERGED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    SPLIT = "SPLIT"


class HKCaseLedgerOutcome(StrEnum):
    """Exact deterministic ledger conclusions."""

    ACCOUNTED_WITH_QUARANTINE = "ACCOUNTED_WITH_QUARANTINE"
    BLOCKED = "BLOCKED"
    COMPLETE_NO_PROPOSITION = "COMPLETE_NO_PROPOSITION"
    COMPLETE_WITH_PROPOSITIONS = "COMPLETE_WITH_PROPOSITIONS"
    INVALID = "INVALID"
    STRUCTURE_VALID = "STRUCTURE_VALID"


class HKCaseLedgerReason(StrEnum):
    """Closed deterministic validation and conclusion reasons."""

    CANDIDATE_BLOCKED = "CANDIDATE_BLOCKED"
    CANDIDATE_QUARANTINED = "CANDIDATE_QUARANTINED"
    COMPLETE_NO_PROPOSITION = "COMPLETE_NO_PROPOSITION"
    COMPLETE_WITH_PROPOSITIONS = "COMPLETE_WITH_PROPOSITIONS"
    CROSS_OPINION_ADOPTION_INVALID = "CROSS_OPINION_ADOPTION_INVALID"
    DEPENDENCY_FINGERPRINT_MISMATCH = "DEPENDENCY_FINGERPRINT_MISMATCH"
    DEPENDENCY_UNKNOWN_PRIMARY = "DEPENDENCY_UNKNOWN_PRIMARY"
    DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
    DUPLICATE_PRIMARY_COVERAGE = "DUPLICATE_PRIMARY_COVERAGE"
    INVALID_NON_PROPOSITIONAL_REASON = "INVALID_NON_PROPOSITIONAL_REASON"
    INVALID_OPINION_OWNERSHIP = "INVALID_OPINION_OWNERSHIP"
    INVALID_PRIMARY_USE = "INVALID_PRIMARY_USE"
    INVALID_RESOLUTION = "INVALID_RESOLUTION"
    INVALID_SCREENING_HANDOFF = "INVALID_SCREENING_HANDOFF"
    MISSING_PRIMARY_COVERAGE = "MISSING_PRIMARY_COVERAGE"
    PRIMARY_COVERAGE_REORDERED = "PRIMARY_COVERAGE_REORDERED"
    SOURCE_SUPPORT_ABSENT = "SOURCE_SUPPORT_ABSENT"
    STRUCTURE_VALID = "STRUCTURE_VALID"
    UNIT_BLOCKED = "UNIT_BLOCKED"
    UNIT_QUARANTINED = "UNIT_QUARANTINED"


@dataclass(frozen=True, slots=True)
class HKCaseOpinion:
    """One delivered opinion and its exact judge attribution."""

    opinion_id: str
    role: HKCaseOpinionRole
    judge_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseCoverageUnit:
    """One ordered mapped part of the preserved original judgment."""

    unit_id: str
    opinion_id: str
    source_order: int
    kind: HKCaseCoverageUnitKind
    source_range_id: str
    text_fingerprint: str
    resolutions: tuple[HKCaseUnitResolution, ...]
    primary_uses: tuple[HKCasePrimaryUse, ...]
    evidence_roles: tuple[HKCaseEvidenceRole, ...]
    non_propositional_reason: HKCaseNonPropositionalReason | None
    citation_or_treatment_lead: bool
    screening_handoff_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseCoverageDependency:
    """One explicit reference to a unit's unique primary occurrence."""

    primary_unit_id: str
    primary_text_fingerprint: str
    kind: HKCaseDependencyKind
    adoption_range_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseCoverageSegment:
    """One opinion-owned primary unit sequence plus explicit dependencies."""

    segment_id: str
    opinion_id: str
    primary_unit_ids: tuple[str, ...]
    dependencies: tuple[HKCaseCoverageDependency, ...]


@dataclass(frozen=True, slots=True)
class HKCasePropositionCandidate:
    """One discovered candidate with a non-disappearing final outcome."""

    candidate_id: str
    outcome: HKCaseCandidateOutcome
    evidence_unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseCoverageLedgerRequest:
    """One exact source-neutral ledger accounting request."""

    judicial_decision_id: str
    official_version_id: str
    artifact_fingerprint: str
    parser_fingerprint: str
    rulebook_fingerprint: str
    cutoff: str
    source_support_available: bool
    source_support_refs: tuple[str, ...]
    semantic_resolution_complete: bool
    opinions: tuple[HKCaseOpinion, ...]
    units: tuple[HKCaseCoverageUnit, ...]
    segments: tuple[HKCaseCoverageSegment, ...]
    candidates: tuple[HKCasePropositionCandidate, ...]


@dataclass(frozen=True, slots=True)
class HKCaseCoverageLedgerResult:
    """One complete deterministic conclusion without a Search Record effect."""

    request_fingerprint: str
    outcome: HKCaseLedgerOutcome
    reasons: tuple[HKCaseLedgerReason, ...]
    opinion_count: int
    unit_count: int
    segment_count: int
    dependency_count: int
    resolved_unit_count: int
    quarantined_unit_count: int
    blocked_unit_count: int
    proposition_evidence_unit_count: int
    accepted_candidate_count: int
    screening_handoff_count: int
    search_records_created: int
    release_eligible: bool
    semantic_analysis_authorized: bool
    external_effects: str


def evaluate_hk_case_coverage_ledger(
    request: HKCaseCoverageLedgerRequest,
) -> HKCaseCoverageLedgerResult:
    """Account for every source unit and fail closed on any incomplete mapping."""
    request_document = hk_case_coverage_ledger_request_document(request)
    request_fingerprint = fingerprint(checked_json_value(request_document))
    reasons = _structural_reasons(request)
    resolution_counts = _resolution_counts(request.units)
    accepted_candidates = sum(
        item.outcome is HKCaseCandidateOutcome.ACCEPTED for item in request.candidates
    )
    proposition_units = sum(
        item.primary_uses == (HKCasePrimaryUse.PROPOSITION_EVIDENCE,) for item in request.units
    )
    if reasons:
        outcome = HKCaseLedgerOutcome.INVALID
    elif not request.source_support_available:
        outcome = HKCaseLedgerOutcome.BLOCKED
        reasons = (HKCaseLedgerReason.SOURCE_SUPPORT_ABSENT,)
    else:
        outcome, reasons = _semantic_outcome(
            request,
            resolution_counts=resolution_counts,
            accepted_candidates=accepted_candidates,
            proposition_units=proposition_units,
        )
    return HKCaseCoverageLedgerResult(
        request_fingerprint=request_fingerprint,
        outcome=outcome,
        reasons=reasons,
        opinion_count=len(request.opinions),
        unit_count=len(request.units),
        segment_count=len(request.segments),
        dependency_count=sum(len(item.dependencies) for item in request.segments),
        resolved_unit_count=resolution_counts[HKCaseUnitResolution.RESOLVED],
        quarantined_unit_count=resolution_counts[HKCaseUnitResolution.QUARANTINED],
        blocked_unit_count=resolution_counts[HKCaseUnitResolution.BLOCKED],
        proposition_evidence_unit_count=proposition_units,
        accepted_candidate_count=accepted_candidates,
        screening_handoff_count=len(
            {handoff for item in request.units for handoff in item.screening_handoff_ids}
        ),
        search_records_created=0,
        release_eligible=False,
        semantic_analysis_authorized=False,
        external_effects="NONE",
    )


def _structural_reasons(
    request: HKCaseCoverageLedgerRequest,
) -> tuple[HKCaseLedgerReason, ...]:
    reasons: set[HKCaseLedgerReason] = set()
    opinion_ids = tuple(item.opinion_id for item in request.opinions)
    unit_ids = tuple(item.unit_id for item in request.units)
    segment_ids = tuple(item.segment_id for item in request.segments)
    candidate_ids = tuple(item.candidate_id for item in request.candidates)
    if any(_duplicates(items) for items in (opinion_ids, unit_ids, segment_ids, candidate_ids)):
        reasons.add(HKCaseLedgerReason.DUPLICATE_IDENTITY)
    opinion_set = set(opinion_ids)
    if any(item.opinion_id not in opinion_set for item in (*request.units, *request.segments)):
        reasons.add(HKCaseLedgerReason.INVALID_OPINION_OWNERSHIP)
    if tuple(item.source_order for item in request.units) != tuple(
        range(1, len(request.units) + 1)
    ):
        reasons.add(HKCaseLedgerReason.PRIMARY_COVERAGE_REORDERED)
    reasons.update(_primary_coverage_reasons(request))
    reasons.update(_dependency_reasons(request))
    reasons.update(_unit_accounting_reasons(request.units))
    unit_set = set(unit_ids)
    if any(not set(item.evidence_unit_ids).issubset(unit_set) for item in request.candidates):
        reasons.add(HKCaseLedgerReason.MISSING_PRIMARY_COVERAGE)
    return tuple(sorted(reasons, key=str))


def _primary_coverage_reasons(
    request: HKCaseCoverageLedgerRequest,
) -> set[HKCaseLedgerReason]:
    reasons: set[HKCaseLedgerReason] = set()
    primary_ids = tuple(
        unit_id for segment in request.segments for unit_id in segment.primary_unit_ids
    )
    unit_ids = tuple(item.unit_id for item in request.units)
    if _duplicates(primary_ids):
        reasons.add(HKCaseLedgerReason.DUPLICATE_PRIMARY_COVERAGE)
    if set(unit_ids) - set(primary_ids) or set(primary_ids) - set(unit_ids):
        reasons.add(HKCaseLedgerReason.MISSING_PRIMARY_COVERAGE)
    source_order = {item.unit_id: item.source_order for item in request.units}
    if all(item in source_order for item in primary_ids) and tuple(
        source_order[item] for item in primary_ids
    ) != tuple(sorted(source_order[item] for item in primary_ids)):
        reasons.add(HKCaseLedgerReason.PRIMARY_COVERAGE_REORDERED)
    owner = {item.unit_id: item.opinion_id for item in request.units}
    if any(
        owner.get(unit_id) != segment.opinion_id
        for segment in request.segments
        for unit_id in segment.primary_unit_ids
    ):
        reasons.add(HKCaseLedgerReason.INVALID_OPINION_OWNERSHIP)
    return reasons


def _dependency_reasons(
    request: HKCaseCoverageLedgerRequest,
) -> set[HKCaseLedgerReason]:
    reasons: set[HKCaseLedgerReason] = set()
    units = {item.unit_id: item for item in request.units}
    for segment in request.segments:
        for dependency in segment.dependencies:
            primary = units.get(dependency.primary_unit_id)
            if primary is None:
                reasons.add(HKCaseLedgerReason.DEPENDENCY_UNKNOWN_PRIMARY)
                continue
            if primary.text_fingerprint != dependency.primary_text_fingerprint:
                reasons.add(HKCaseLedgerReason.DEPENDENCY_FINGERPRINT_MISMATCH)
            if dependency.kind is HKCaseDependencyKind.CROSS_OPINION_ADOPTION and (
                primary.opinion_id == segment.opinion_id
                or len(dependency.adoption_range_ids) != _ADOPTION_RANGE_COUNT
            ):
                reasons.add(HKCaseLedgerReason.CROSS_OPINION_ADOPTION_INVALID)
            if dependency.kind is HKCaseDependencyKind.CONTEXT and dependency.adoption_range_ids:
                reasons.add(HKCaseLedgerReason.CROSS_OPINION_ADOPTION_INVALID)
    return reasons


def _unit_accounting_reasons(
    units: tuple[HKCaseCoverageUnit, ...],
) -> set[HKCaseLedgerReason]:
    reasons: set[HKCaseLedgerReason] = set()
    for unit in units:
        if len(unit.resolutions) != 1:
            reasons.add(HKCaseLedgerReason.INVALID_RESOLUTION)
            continue
        if unit.resolutions[0] is HKCaseUnitResolution.RESOLVED and len(unit.primary_uses) != 1:
            reasons.add(HKCaseLedgerReason.INVALID_PRIMARY_USE)
        if unit.resolutions[0] is not HKCaseUnitResolution.RESOLVED and unit.primary_uses:
            reasons.add(HKCaseLedgerReason.INVALID_PRIMARY_USE)
        non_propositional = unit.primary_uses == (HKCasePrimaryUse.NON_PROPOSITIONAL,)
        if non_propositional is (unit.non_propositional_reason is None):
            reasons.add(HKCaseLedgerReason.INVALID_NON_PROPOSITIONAL_REASON)
        if unit.citation_or_treatment_lead and not unit.screening_handoff_ids:
            reasons.add(HKCaseLedgerReason.INVALID_SCREENING_HANDOFF)
    return reasons


def _semantic_outcome(
    request: HKCaseCoverageLedgerRequest,
    *,
    resolution_counts: dict[HKCaseUnitResolution, int],
    accepted_candidates: int,
    proposition_units: int,
) -> tuple[HKCaseLedgerOutcome, tuple[HKCaseLedgerReason, ...]]:
    if resolution_counts[HKCaseUnitResolution.BLOCKED] or any(
        item.outcome is HKCaseCandidateOutcome.BLOCKED for item in request.candidates
    ):
        reasons = [HKCaseLedgerReason.UNIT_BLOCKED]
        if any(item.outcome is HKCaseCandidateOutcome.BLOCKED for item in request.candidates):
            reasons.append(HKCaseLedgerReason.CANDIDATE_BLOCKED)
        return HKCaseLedgerOutcome.BLOCKED, tuple(reasons)
    if resolution_counts[HKCaseUnitResolution.QUARANTINED] or any(
        item.outcome is HKCaseCandidateOutcome.QUARANTINED for item in request.candidates
    ):
        reasons = [HKCaseLedgerReason.UNIT_QUARANTINED]
        if any(item.outcome is HKCaseCandidateOutcome.QUARANTINED for item in request.candidates):
            reasons.append(HKCaseLedgerReason.CANDIDATE_QUARANTINED)
        return HKCaseLedgerOutcome.ACCOUNTED_WITH_QUARANTINE, tuple(reasons)
    if not request.semantic_resolution_complete:
        return HKCaseLedgerOutcome.STRUCTURE_VALID, (HKCaseLedgerReason.STRUCTURE_VALID,)
    if accepted_candidates and proposition_units:
        return HKCaseLedgerOutcome.COMPLETE_WITH_PROPOSITIONS, (
            HKCaseLedgerReason.COMPLETE_WITH_PROPOSITIONS,
        )
    if not accepted_candidates and not proposition_units:
        return HKCaseLedgerOutcome.COMPLETE_NO_PROPOSITION, (
            HKCaseLedgerReason.COMPLETE_NO_PROPOSITION,
        )
    return HKCaseLedgerOutcome.INVALID, (HKCaseLedgerReason.INVALID_PRIMARY_USE,)


def _resolution_counts(
    units: tuple[HKCaseCoverageUnit, ...],
) -> dict[HKCaseUnitResolution, int]:
    return {
        state: sum(item.resolutions == (state,) for item in units) for state in HKCaseUnitResolution
    }


def hk_case_coverage_ledger_request_document(
    request: HKCaseCoverageLedgerRequest,
) -> dict[str, JsonValue]:
    """Return the canonical JSON-compatible request projection."""
    return {
        "schema_id": "asklegal.hk-cases.coverage-ledger-request",
        "schema_version": HK_CASE_COVERAGE_LEDGER_CONTRACT_VERSION,
        "rule_id": HK_CASE_COVERAGE_LEDGER_RULE_ID,
        "judicial_decision_id": request.judicial_decision_id,
        "official_version_id": request.official_version_id,
        "artifact_fingerprint": request.artifact_fingerprint,
        "parser_fingerprint": request.parser_fingerprint,
        "rulebook_fingerprint": request.rulebook_fingerprint,
        "cutoff": request.cutoff,
        "source_support_available": request.source_support_available,
        "source_support_refs": list(request.source_support_refs),
        "semantic_resolution_complete": request.semantic_resolution_complete,
        "opinions": [
            {
                "opinion_id": item.opinion_id,
                "role": item.role.value,
                "judge_ids": list(item.judge_ids),
            }
            for item in request.opinions
        ],
        "units": [
            {
                "unit_id": item.unit_id,
                "opinion_id": item.opinion_id,
                "source_order": item.source_order,
                "kind": item.kind.value,
                "source_range_id": item.source_range_id,
                "text_fingerprint": item.text_fingerprint,
                "resolutions": [value.value for value in item.resolutions],
                "primary_uses": [value.value for value in item.primary_uses],
                "evidence_roles": [value.value for value in item.evidence_roles],
                "non_propositional_reason": (
                    item.non_propositional_reason.value
                    if item.non_propositional_reason is not None
                    else None
                ),
                "citation_or_treatment_lead": item.citation_or_treatment_lead,
                "screening_handoff_ids": list(item.screening_handoff_ids),
            }
            for item in request.units
        ],
        "segments": [
            {
                "segment_id": item.segment_id,
                "opinion_id": item.opinion_id,
                "primary_unit_ids": list(item.primary_unit_ids),
                "dependencies": [
                    {
                        "primary_unit_id": value.primary_unit_id,
                        "primary_text_fingerprint": value.primary_text_fingerprint,
                        "kind": value.kind.value,
                        "adoption_range_ids": list(value.adoption_range_ids),
                    }
                    for value in item.dependencies
                ],
            }
            for item in request.segments
        ],
        "candidates": [
            {
                "candidate_id": item.candidate_id,
                "outcome": item.outcome.value,
                "evidence_unit_ids": list(item.evidence_unit_ids),
            }
            for item in request.candidates
        ],
    }


def hk_case_coverage_ledger_result_document(
    result: HKCaseCoverageLedgerResult,
) -> dict[str, JsonValue]:
    """Return one canonical JSON-compatible result projection."""
    return {
        "schema_id": "asklegal.hk-cases.coverage-ledger-result",
        "schema_version": HK_CASE_COVERAGE_LEDGER_CONTRACT_VERSION,
        "rule_id": HK_CASE_COVERAGE_LEDGER_RULE_ID,
        "request_fingerprint": result.request_fingerprint,
        "outcome": result.outcome.value,
        "reasons": [item.value for item in result.reasons],
        "opinion_count": result.opinion_count,
        "unit_count": result.unit_count,
        "segment_count": result.segment_count,
        "dependency_count": result.dependency_count,
        "resolved_unit_count": result.resolved_unit_count,
        "quarantined_unit_count": result.quarantined_unit_count,
        "blocked_unit_count": result.blocked_unit_count,
        "proposition_evidence_unit_count": result.proposition_evidence_unit_count,
        "accepted_candidate_count": result.accepted_candidate_count,
        "screening_handoff_count": result.screening_handoff_count,
        "search_records_created": result.search_records_created,
        "release_eligible": result.release_eligible,
        "semantic_analysis_authorized": result.semantic_analysis_authorized,
        "external_effects": result.external_effects,
    }


def hk_case_coverage_ledger_request_from_document(
    document: object,
) -> HKCaseCoverageLedgerRequest:
    """Strictly decode one request and reject unknown or malformed fields."""
    root = _object(document)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "judicial_decision_id",
            "official_version_id",
            "artifact_fingerprint",
            "parser_fingerprint",
            "rulebook_fingerprint",
            "cutoff",
            "source_support_available",
            "source_support_refs",
            "semantic_resolution_complete",
            "opinions",
            "units",
            "segments",
            "candidates",
        },
    )
    _constant(root["schema_id"], "asklegal.hk-cases.coverage-ledger-request")
    _constant(root["schema_version"], HK_CASE_COVERAGE_LEDGER_CONTRACT_VERSION)
    _constant(root["rule_id"], HK_CASE_COVERAGE_LEDGER_RULE_ID)
    return HKCaseCoverageLedgerRequest(
        _identity(root["judicial_decision_id"]),
        _identity(root["official_version_id"]),
        _fingerprint(root["artifact_fingerprint"]),
        _fingerprint(root["parser_fingerprint"]),
        _fingerprint(root["rulebook_fingerprint"]),
        _string(root["cutoff"]),
        _boolean(root["source_support_available"]),
        _identities(root["source_support_refs"]),
        _boolean(root["semantic_resolution_complete"]),
        tuple(_opinion(item) for item in _array(root["opinions"])),
        tuple(_unit(item) for item in _array(root["units"])),
        tuple(_segment(item) for item in _array(root["segments"])),
        tuple(_candidate(item) for item in _array(root["candidates"])),
    )


def _opinion(value: JsonValue) -> HKCaseOpinion:
    root = _object(value)
    _exact_keys(root, {"opinion_id", "role", "judge_ids"})
    return HKCaseOpinion(
        _identity(root["opinion_id"]),
        _enum(root["role"], HKCaseOpinionRole),
        _identities(root["judge_ids"]),
    )


def _unit(value: JsonValue) -> HKCaseCoverageUnit:
    root = _object(value)
    _exact_keys(
        root,
        {
            "unit_id",
            "opinion_id",
            "source_order",
            "kind",
            "source_range_id",
            "text_fingerprint",
            "resolutions",
            "primary_uses",
            "evidence_roles",
            "non_propositional_reason",
            "citation_or_treatment_lead",
            "screening_handoff_ids",
        },
    )
    reason = root["non_propositional_reason"]
    return HKCaseCoverageUnit(
        _identity(root["unit_id"]),
        _identity(root["opinion_id"]),
        _integer(root["source_order"]),
        _enum(root["kind"], HKCaseCoverageUnitKind),
        _identity(root["source_range_id"]),
        _fingerprint(root["text_fingerprint"]),
        tuple(_enum(item, HKCaseUnitResolution) for item in _array(root["resolutions"])),
        tuple(_enum(item, HKCasePrimaryUse) for item in _array(root["primary_uses"])),
        tuple(_enum(item, HKCaseEvidenceRole) for item in _array(root["evidence_roles"])),
        None if reason is None else _enum(reason, HKCaseNonPropositionalReason),
        _boolean(root["citation_or_treatment_lead"]),
        _identities(root["screening_handoff_ids"]),
    )


def _segment(value: JsonValue) -> HKCaseCoverageSegment:
    root = _object(value)
    _exact_keys(root, {"segment_id", "opinion_id", "primary_unit_ids", "dependencies"})
    return HKCaseCoverageSegment(
        _identity(root["segment_id"]),
        _identity(root["opinion_id"]),
        _identities(root["primary_unit_ids"]),
        tuple(_dependency(item) for item in _array(root["dependencies"])),
    )


def _dependency(value: JsonValue) -> HKCaseCoverageDependency:
    root = _object(value)
    _exact_keys(
        root,
        {"primary_unit_id", "primary_text_fingerprint", "kind", "adoption_range_ids"},
    )
    return HKCaseCoverageDependency(
        _identity(root["primary_unit_id"]),
        _fingerprint(root["primary_text_fingerprint"]),
        _enum(root["kind"], HKCaseDependencyKind),
        _identities(root["adoption_range_ids"]),
    )


def _candidate(value: JsonValue) -> HKCasePropositionCandidate:
    root = _object(value)
    _exact_keys(root, {"candidate_id", "outcome", "evidence_unit_ids"})
    return HKCasePropositionCandidate(
        _identity(root["candidate_id"]),
        _enum(root["outcome"], HKCaseCandidateOutcome),
        _identities(root["evidence_unit_ids"]),
    )


def _duplicates(values: tuple[str, ...]) -> bool:
    return len(values) != len(set(values))


def _is_object(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def _object(value: object) -> dict[str, JsonValue]:
    if not _is_object(value) or any(type(key) is not str for key in value):
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.CONTRACT)
    return {str(key): checked_json_value(item) for key, item in value.items()}


def _array(value: JsonValue) -> list[JsonValue]:
    if type(value) is not list:
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.CONTRACT)
    return value


def _exact_keys(root: dict[str, JsonValue], expected: set[str]) -> None:
    if set(root) != expected:
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.CONTRACT)


def _constant(value: JsonValue, expected: str) -> None:
    if value != expected:
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.CONTRACT)


def _string(value: JsonValue) -> str:
    if type(value) is not str or not value:
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.CONTRACT)
    return value


def _identity(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_IDENTITY_PATTERN, result) is None:
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.IDENTITY)
    return result


def _identities(value: JsonValue) -> tuple[str, ...]:
    return tuple(_identity(item) for item in _array(value))


def _fingerprint(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.FINGERPRINT)
    return result


def _integer(value: JsonValue) -> int:
    if type(value) is not int or value < 1:
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.CONTRACT)
    return value


def _boolean(value: JsonValue) -> bool:
    if type(value) is not bool:
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.CONTRACT)
    return value


def _enum[T: StrEnum](value: JsonValue, enum_type: type[T]) -> T:
    try:
        return enum_type(_string(value))
    except ValueError as error:
        raise HKCaseLedgerError(HKCaseLedgerErrorCode.CONTRACT) from error
