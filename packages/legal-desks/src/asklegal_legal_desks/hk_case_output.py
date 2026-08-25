"""Deterministic ADR 0060-0063 Hong Kong Case Proposition output validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from re import fullmatch
from typing import Protocol, TypeIs

from asklegal_contracts import canonicalize, fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_case_coverage_ledger import (
    HKCaseCandidateOutcome,
    HKCaseEvidenceRole,
    HKCaseOpinionRole,
)

HK_CASE_OUTPUT_RULE_ID = "HKCASE-PROP-OUTPUT-CONFORMANCE-001"
HK_CASE_OUTPUT_CONTRACT_VERSION = "1.0.0"
HK_CASE_OUTPUT_RENDERER_ID = "HKCASE-ADR0060-LABELLED-1.0.0"

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_IDENTITY_PATTERN = r"[a-z][a-z0-9_]{2,95}"
_CODE_PATTERN = r"[A-Z][A-Z0-9_]{2,95}"
_MIN_SPLIT_TARGETS = 2
_REQUIRED_EVIDENCE_ROLES = frozenset(
    {
        HKCaseEvidenceRole.ANSWER,
        HKCaseEvidenceRole.APPLICATION,
        HKCaseEvidenceRole.ATTRIBUTION,
        HKCaseEvidenceRole.CONTEXT,
        HKCaseEvidenceRole.ISSUE,
        HKCaseEvidenceRole.QUALIFICATION,
        HKCaseEvidenceRole.QUOTATION,
        HKCaseEvidenceRole.RESULT,
    }
)


class HKCaseOutputErrorCode(StrEnum):
    """Closed malformed output-contract request failures."""

    CONTRACT = "HK_CASE_OUTPUT_CONTRACT_INVALID"
    FINGERPRINT = "HK_CASE_OUTPUT_FINGERPRINT_INVALID"
    IDENTITY = "HK_CASE_OUTPUT_IDENTITY_INVALID"


class HKCaseOutputError(ValueError):
    """One fail-closed malformed output request."""

    code: HKCaseOutputErrorCode

    def __init__(self, code: HKCaseOutputErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKCaseOutputOutcome(StrEnum):
    """Exact deterministic output-validation conclusions."""

    BLOCKED = "BLOCKED"
    INVALID = "INVALID"
    QUARANTINED_OVER_LIMIT = "QUARANTINED_OVER_LIMIT"
    QUARANTINED_UNRESOLVED = "QUARANTINED_UNRESOLVED"
    VALID_OUTPUT = "VALID_OUTPUT"
    VALID_ZERO_OUTPUT = "VALID_ZERO_OUTPUT"


class HKCaseOutputReason(StrEnum):
    """Closed reasons for deterministic output conclusions."""

    CANDIDATE_ACCOUNTING_INVALID = "CANDIDATE_ACCOUNTING_INVALID"
    CANDIDATE_BLOCKED = "CANDIDATE_BLOCKED"
    CANDIDATE_QUARANTINED = "CANDIDATE_QUARANTINED"
    DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
    EVIDENCE_ROLE_INCOMPLETE = "EVIDENCE_ROLE_INCOMPLETE"
    EVIDENCE_ROLE_OR_RANGE_INVALID = "EVIDENCE_ROLE_OR_RANGE_INVALID"
    LIMIT_MEASUREMENT_INVALID = "LIMIT_MEASUREMENT_INVALID"
    OUTPUT_INVENTORY_INVALID = "OUTPUT_INVENTORY_INVALID"
    OUTPUT_VALID = "OUTPUT_VALID"
    OVER_LIMIT_UNACCOUNTED = "OVER_LIMIT_UNACCOUNTED"
    PAYLOAD_INVALID = "PAYLOAD_INVALID"
    QUOTATION_MISMATCH = "QUOTATION_MISMATCH"
    RENDERER_MISMATCH = "RENDERER_MISMATCH"
    SOURCE_MAP_INVALID = "SOURCE_MAP_INVALID"
    SOURCE_MAP_UNAVAILABLE = "SOURCE_MAP_UNAVAILABLE"
    TRACEABILITY_INVALID = "TRACEABILITY_INVALID"
    VALID_OVER_LIMIT_QUARANTINE = "VALID_OVER_LIMIT_QUARANTINE"
    ZERO_OUTPUT_VALID = "ZERO_OUTPUT_VALID"


class HKCaseTokenCounter(Protocol):
    """Pinned deterministic tokenizer boundary used only for measurement."""

    @property
    def profile_fingerprint(self) -> str:
        """Return the exact tokenizer-profile fingerprint."""
        ...

    def count(self, text: str) -> int:
        """Measure one exact rendered text."""
        ...


@dataclass(frozen=True, slots=True)
class HKCaseCodepointTokenCounter:
    """Synthetic deterministic counter; never an admitted production tokenizer."""

    profile_fingerprint: str

    def count(self, text: str) -> int:
        """Count Unicode code points for reproducible source-neutral fixtures."""
        return len(text)


@dataclass(frozen=True, slots=True)
class HKCaseSourceUnitText:
    """One unique ordered source unit with preserved exact text."""

    unit_id: str
    source_order: int
    exact_text: str


@dataclass(frozen=True, slots=True)
class HKCaseSourceRange:
    """One UTF-8 byte range within a preserved source unit."""

    range_id: str
    unit_id: str
    start_byte: int
    end_byte: int
    exact_text_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseOutputCandidate:
    """One discovered candidate with exactly one final disposition."""

    candidate_id: str
    outcome: HKCaseCandidateOutcome
    proposition_ids: tuple[str, ...]
    related_candidate_ids: tuple[str, ...]
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class HKCasePropositionEvidenceLink:
    """One exact proposition evidence role and preserved range."""

    role: HKCaseEvidenceRole
    range_id: str


@dataclass(frozen=True, slots=True)
class HKCaseQuotation:
    """One proposed verbatim quotation bound to a preserved range."""

    range_id: str
    exact_text: str


@dataclass(frozen=True, slots=True)
class HKCaseOutputProposition:
    """One accepted source-faithful proposition ready for deterministic rendering."""

    proposition_id: str
    candidate_id: str
    case_name: str
    official_citation: str
    court: str
    decision_date: str
    opinion_label: str
    authority_role: HKCaseOpinionRole
    legal_issue: str
    derived_statement: str
    material_context: str | None
    qualifications: str | None
    application_and_result: str
    evidence_links: tuple[HKCasePropositionEvidenceLink, ...]
    quotations: tuple[HKCaseQuotation, ...]
    authority_note: str
    boundary_indivisible: bool
    coverage_gap_id: str | None


@dataclass(frozen=True, slots=True)
class HKCaseProposedServingRecord:
    """One proposed exact six-field payload plus traceability and measurements."""

    record_id: str
    proposition_id: str
    ledger_fingerprint: str
    renderer_proposition_id: str
    text: str
    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str
    text_token_count: int
    payload_byte_count: int
    payload_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseOutputRequest:
    """One exact source-neutral candidate/evidence/rendering validation request."""

    judicial_decision_id: str
    official_version_id: str
    ledger_fingerprint: str
    renderer_id: str
    tokenizer_profile_fingerprint: str
    max_text_tokens: int
    max_payload_bytes: int
    source_map_available: bool
    discovered_candidate_ids: tuple[str, ...]
    candidates: tuple[HKCaseOutputCandidate, ...]
    source_units: tuple[HKCaseSourceUnitText, ...]
    source_ranges: tuple[HKCaseSourceRange, ...]
    propositions: tuple[HKCaseOutputProposition, ...]
    ledger_proposition_ids: tuple[str, ...]
    proposed_records: tuple[HKCaseProposedServingRecord, ...]


@dataclass(frozen=True, slots=True)
class HKCaseCandidateOutcomeCount:
    """One exact final candidate-outcome count."""

    outcome: HKCaseCandidateOutcome
    count: int


@dataclass(frozen=True, slots=True)
class HKCaseOutputResult:
    """One deterministic result with no release or external authority."""

    request_fingerprint: str
    outcome: HKCaseOutputOutcome
    reasons: tuple[HKCaseOutputReason, ...]
    discovered_candidate_count: int
    final_candidate_count: int
    candidate_outcome_counts: tuple[HKCaseCandidateOutcomeCount, ...]
    source_unit_count: int
    source_range_count: int
    proposition_count: int
    evidence_link_count: int
    validated_record_count: int
    validated_payload_fingerprints: tuple[str, ...]
    measured_text_token_counts: tuple[int, ...]
    measured_payload_byte_counts: tuple[int, ...]
    coverage_gap_ids: tuple[str, ...]
    search_records_created: int
    release_eligible: bool
    semantic_analysis_authorized: bool
    external_effects: str


@dataclass(frozen=True, slots=True)
class _OutputDecision:
    outcome: HKCaseOutputOutcome
    reasons: set[HKCaseOutputReason]
    measurements: dict[str, tuple[int, int, str]] | None


def render_hk_case_proposition(proposition: HKCaseOutputProposition) -> str:
    """Render ADR 0060's stable labelled layout with omission-only optional sections."""
    lines = [
        f"Case: {proposition.case_name} - {proposition.official_citation}",
        f"Court and decision date: {proposition.court} - {proposition.decision_date}",
        (
            "Opinion and authority role: "
            f"{proposition.opinion_label} - {proposition.authority_role.value}"
        ),
        f"Legal issue: {proposition.legal_issue}",
        f"Proposition - derived statement: {proposition.derived_statement}",
    ]
    if proposition.material_context is not None:
        lines.append(f"Material context: {proposition.material_context}")
    if proposition.qualifications is not None:
        lines.append(f"Qualifications or exceptions: {proposition.qualifications}")
    lines.extend(
        (
            f"Application and relevant result: {proposition.application_and_result}",
            "Exact judgment support:",
        )
    )
    lines.extend(f"[{item.range_id}] {item.exact_text}" for item in proposition.quotations)
    return "\n".join(lines)


def hk_case_serving_payload_document(
    *,
    text: str,
    authority_note: str,
) -> dict[str, JsonValue]:
    """Return the exact six-field case payload in canonical field semantics."""
    return {
        "text": text,
        "country": "Hong Kong",
        "jurisdiction": "Hong Kong",
        "type": "case",
        "source": "Hong Kong Judiciary",
        "authority_note": authority_note,
    }


def build_hk_case_proposed_serving_record(
    *,
    record_id: str,
    proposition: HKCaseOutputProposition,
    ledger_fingerprint: str,
    counter: HKCaseTokenCounter,
) -> HKCaseProposedServingRecord:
    """Build exact synthetic proposed bytes for deterministic conformance fixtures."""
    text = render_hk_case_proposition(proposition)
    payload = hk_case_serving_payload_document(
        text=text,
        authority_note=proposition.authority_note,
    )
    checked = checked_json_value(payload)
    return HKCaseProposedServingRecord(
        record_id=record_id,
        proposition_id=proposition.proposition_id,
        ledger_fingerprint=ledger_fingerprint,
        renderer_proposition_id=proposition.proposition_id,
        text=text,
        country="Hong Kong",
        jurisdiction="Hong Kong",
        material_type="case",
        source="Hong Kong Judiciary",
        authority_note=proposition.authority_note,
        text_token_count=counter.count(text),
        payload_byte_count=len(canonicalize(checked)),
        payload_fingerprint=fingerprint(checked),
    )


def evaluate_hk_case_output(
    request: HKCaseOutputRequest,
    *,
    counter: HKCaseTokenCounter,
) -> HKCaseOutputResult:
    """Validate candidate accounting, exact evidence, rendering, limits, and output."""
    request_document = hk_case_output_request_document(request)
    request_fingerprint = fingerprint(checked_json_value(request_document))
    outcome_counts = tuple(
        HKCaseCandidateOutcomeCount(
            outcome,
            sum(item.outcome is outcome for item in request.candidates),
        )
        for outcome in HKCaseCandidateOutcome
    )
    decision = _decide_output(request, counter=counter)
    return _result(request, request_fingerprint, outcome_counts, decision)


def _decide_output(
    request: HKCaseOutputRequest,
    *,
    counter: HKCaseTokenCounter,
) -> _OutputDecision:
    errors = _identity_and_candidate_errors(request)
    if counter.profile_fingerprint != request.tokenizer_profile_fingerprint:
        errors.add(HKCaseOutputReason.LIMIT_MEASUREMENT_INVALID)
    if errors:
        return _OutputDecision(HKCaseOutputOutcome.INVALID, errors, None)
    if not request.source_map_available:
        return _OutputDecision(
            HKCaseOutputOutcome.BLOCKED,
            {HKCaseOutputReason.SOURCE_MAP_UNAVAILABLE},
            None,
        )
    return _decide_supported_output(request, counter=counter)


def _decide_supported_output(
    request: HKCaseOutputRequest,
    *,
    counter: HKCaseTokenCounter,
) -> _OutputDecision:
    source_texts, source_errors = _validated_source_ranges(request)
    errors = set(source_errors)
    errors.update(_proposition_errors(request, source_texts))
    if errors:
        return _OutputDecision(HKCaseOutputOutcome.INVALID, errors, None)

    measurements = _measure_propositions(request, counter=counter)
    over_limit_ids = {
        proposition_id
        for proposition_id, (token_count, byte_count, _) in measurements.items()
        if token_count > request.max_text_tokens or byte_count > request.max_payload_bytes
    }
    over_limit = [item for item in request.propositions if item.proposition_id in over_limit_ids]
    if any(not item.boundary_indivisible or item.coverage_gap_id is None for item in over_limit):
        errors.add(HKCaseOutputReason.OVER_LIMIT_UNACCOUNTED)
    if any(
        item.boundary_indivisible or item.coverage_gap_id is not None
        for item in request.propositions
        if item.proposition_id not in over_limit_ids
    ):
        errors.add(HKCaseOutputReason.LIMIT_MEASUREMENT_INVALID)
    errors.update(_record_errors(request, measurements, over_limit_ids))
    if errors:
        return _OutputDecision(HKCaseOutputOutcome.INVALID, errors, measurements)
    if over_limit:
        return _OutputDecision(
            HKCaseOutputOutcome.QUARANTINED_OVER_LIMIT,
            {HKCaseOutputReason.VALID_OVER_LIMIT_QUARANTINE},
            measurements,
        )
    return _decide_within_limit_output(request, measurements=measurements)


def _decide_within_limit_output(
    request: HKCaseOutputRequest,
    *,
    measurements: dict[str, tuple[int, int, str]],
) -> _OutputDecision:
    if any(item.outcome is HKCaseCandidateOutcome.BLOCKED for item in request.candidates):
        return _OutputDecision(
            HKCaseOutputOutcome.BLOCKED,
            {HKCaseOutputReason.CANDIDATE_BLOCKED},
            measurements,
        )
    if any(item.outcome is HKCaseCandidateOutcome.QUARANTINED for item in request.candidates):
        return _OutputDecision(
            HKCaseOutputOutcome.QUARANTINED_UNRESOLVED,
            {HKCaseOutputReason.CANDIDATE_QUARANTINED},
            measurements,
        )
    if not request.propositions:
        return _OutputDecision(
            HKCaseOutputOutcome.VALID_ZERO_OUTPUT,
            {HKCaseOutputReason.ZERO_OUTPUT_VALID},
            measurements,
        )
    return _OutputDecision(
        HKCaseOutputOutcome.VALID_OUTPUT,
        {HKCaseOutputReason.OUTPUT_VALID},
        measurements,
    )


def _identity_and_candidate_errors(
    request: HKCaseOutputRequest,
) -> set[HKCaseOutputReason]:
    errors: set[HKCaseOutputReason] = set()
    identities = (
        request.discovered_candidate_ids,
        tuple(item.candidate_id for item in request.candidates),
        tuple(item.unit_id for item in request.source_units),
        tuple(item.range_id for item in request.source_ranges),
        tuple(item.proposition_id for item in request.propositions),
        tuple(item.record_id for item in request.proposed_records),
    )
    if any(_duplicates(items) for items in identities):
        errors.add(HKCaseOutputReason.DUPLICATE_IDENTITY)
    candidate_ids = {item.candidate_id for item in request.candidates}
    if candidate_ids != set(request.discovered_candidate_ids):
        errors.add(HKCaseOutputReason.CANDIDATE_ACCOUNTING_INVALID)
    for item in request.candidates:
        related = set(item.related_candidate_ids)
        if (
            not related.issubset(candidate_ids)
            or item.candidate_id in related
            or _duplicates(item.related_candidate_ids)
        ):
            errors.add(HKCaseOutputReason.CANDIDATE_ACCOUNTING_INVALID)
        if not _candidate_shape_valid(item):
            errors.add(HKCaseOutputReason.CANDIDATE_ACCOUNTING_INVALID)
    accepted_proposition_ids = tuple(
        proposition_id
        for item in request.candidates
        if item.outcome is HKCaseCandidateOutcome.ACCEPTED
        for proposition_id in item.proposition_ids
    )
    if _duplicates(accepted_proposition_ids) or set(accepted_proposition_ids) != {
        item.proposition_id for item in request.propositions
    }:
        errors.add(HKCaseOutputReason.CANDIDATE_ACCOUNTING_INVALID)
    if tuple(item.source_order for item in request.source_units) != tuple(
        range(1, len(request.source_units) + 1)
    ):
        errors.add(HKCaseOutputReason.SOURCE_MAP_INVALID)
    return errors


def _candidate_shape_valid(candidate: HKCaseOutputCandidate) -> bool:
    if candidate.outcome is HKCaseCandidateOutcome.ACCEPTED:
        return (
            len(candidate.proposition_ids) == 1
            and not candidate.related_candidate_ids
            and candidate.reason_code is None
        )
    if candidate.outcome is HKCaseCandidateOutcome.REJECTED:
        return (
            not candidate.proposition_ids
            and not candidate.related_candidate_ids
            and candidate.reason_code is not None
        )
    if candidate.outcome is HKCaseCandidateOutcome.MERGED:
        return (
            not candidate.proposition_ids
            and len(candidate.related_candidate_ids) == 1
            and candidate.reason_code is not None
        )
    if candidate.outcome is HKCaseCandidateOutcome.SPLIT:
        return (
            not candidate.proposition_ids
            and len(candidate.related_candidate_ids) >= _MIN_SPLIT_TARGETS
            and candidate.reason_code is not None
        )
    return (
        not candidate.proposition_ids
        and not candidate.related_candidate_ids
        and candidate.reason_code is not None
    )


def _validated_source_ranges(
    request: HKCaseOutputRequest,
) -> tuple[dict[str, str], set[HKCaseOutputReason]]:
    errors: set[HKCaseOutputReason] = set()
    units = {item.unit_id: item for item in request.source_units}
    unit_order = {item.unit_id: item.source_order for item in request.source_units}
    source_texts: dict[str, str] = {}
    expected_order: list[tuple[int, int, int, str]] = []
    for item in request.source_ranges:
        unit = units.get(item.unit_id)
        if unit is None or item.start_byte < 0 or item.end_byte <= item.start_byte:
            errors.add(HKCaseOutputReason.SOURCE_MAP_INVALID)
            continue
        raw = unit.exact_text.encode("utf-8")
        if item.end_byte > len(raw):
            errors.add(HKCaseOutputReason.SOURCE_MAP_INVALID)
            continue
        try:
            exact_text = raw[item.start_byte : item.end_byte].decode("utf-8")
        except UnicodeDecodeError:
            errors.add(HKCaseOutputReason.SOURCE_MAP_INVALID)
            continue
        if _raw_fingerprint(exact_text.encode("utf-8")) != item.exact_text_fingerprint:
            errors.add(HKCaseOutputReason.SOURCE_MAP_INVALID)
        source_texts[item.range_id] = exact_text
        expected_order.append(
            (unit_order[item.unit_id], item.start_byte, item.end_byte, item.range_id)
        )
    if expected_order != sorted(expected_order):
        errors.add(HKCaseOutputReason.SOURCE_MAP_INVALID)
    return source_texts, errors


def _proposition_errors(
    request: HKCaseOutputRequest,
    source_texts: dict[str, str],
) -> set[HKCaseOutputReason]:
    errors: set[HKCaseOutputReason] = set()
    accepted_by_proposition = {
        item.proposition_ids[0]: item.candidate_id
        for item in request.candidates
        if item.outcome is HKCaseCandidateOutcome.ACCEPTED and len(item.proposition_ids) == 1
    }
    proposition_ids = tuple(item.proposition_id for item in request.propositions)
    if request.ledger_proposition_ids != proposition_ids:
        errors.add(HKCaseOutputReason.TRACEABILITY_INVALID)
    for item in request.propositions:
        if accepted_by_proposition.get(item.proposition_id) != item.candidate_id:
            errors.add(HKCaseOutputReason.TRACEABILITY_INVALID)
        links = tuple((link.role, link.range_id) for link in item.evidence_links)
        if _duplicates(links):
            errors.add(HKCaseOutputReason.EVIDENCE_ROLE_OR_RANGE_INVALID)
        roles = {link.role for link in item.evidence_links}
        if not _REQUIRED_EVIDENCE_ROLES.issubset(roles):
            errors.add(HKCaseOutputReason.EVIDENCE_ROLE_INCOMPLETE)
        if any(link.range_id not in source_texts for link in item.evidence_links):
            errors.add(HKCaseOutputReason.EVIDENCE_ROLE_OR_RANGE_INVALID)
        quotation_link_ids = tuple(
            link.range_id
            for link in item.evidence_links
            if link.role is HKCaseEvidenceRole.QUOTATION
        )
        quotation_ids = tuple(value.range_id for value in item.quotations)
        if not quotation_ids or quotation_link_ids != quotation_ids:
            errors.add(HKCaseOutputReason.EVIDENCE_ROLE_OR_RANGE_INVALID)
        if any(source_texts.get(value.range_id) != value.exact_text for value in item.quotations):
            errors.add(HKCaseOutputReason.QUOTATION_MISMATCH)
    return errors


def _measure_propositions(
    request: HKCaseOutputRequest,
    *,
    counter: HKCaseTokenCounter,
) -> dict[str, tuple[int, int, str]]:
    result: dict[str, tuple[int, int, str]] = {}
    for item in request.propositions:
        text = render_hk_case_proposition(item)
        payload = checked_json_value(
            hk_case_serving_payload_document(text=text, authority_note=item.authority_note)
        )
        result[item.proposition_id] = (
            counter.count(text),
            len(canonicalize(payload)),
            fingerprint(payload),
        )
    return result


def _record_errors(
    request: HKCaseOutputRequest,
    measurements: dict[str, tuple[int, int, str]],
    over_limit_ids: set[str],
) -> set[HKCaseOutputReason]:
    errors: set[HKCaseOutputReason] = set()
    proposition_by_id = {item.proposition_id: item for item in request.propositions}
    required_records = set(proposition_by_id) - over_limit_ids
    actual_records = {item.proposition_id for item in request.proposed_records}
    if actual_records != required_records or len(actual_records) != len(request.proposed_records):
        errors.add(HKCaseOutputReason.OUTPUT_INVENTORY_INVALID)
    for item in request.proposed_records:
        proposition = proposition_by_id.get(item.proposition_id)
        measurement = measurements.get(item.proposition_id)
        if proposition is None or measurement is None:
            errors.add(HKCaseOutputReason.TRACEABILITY_INVALID)
            continue
        if (
            item.ledger_fingerprint != request.ledger_fingerprint
            or item.renderer_proposition_id != item.proposition_id
        ):
            errors.add(HKCaseOutputReason.TRACEABILITY_INVALID)
        expected_text = render_hk_case_proposition(proposition)
        if item.text != expected_text:
            errors.add(HKCaseOutputReason.RENDERER_MISMATCH)
        if (
            item.country != "Hong Kong"
            or item.jurisdiction != "Hong Kong"
            or item.material_type != "case"
            or item.source != "Hong Kong Judiciary"
            or item.authority_note != proposition.authority_note
        ):
            errors.add(HKCaseOutputReason.PAYLOAD_INVALID)
        token_count, byte_count, payload_fingerprint = measurement
        if (
            item.text_token_count != token_count
            or item.payload_byte_count != byte_count
            or item.payload_fingerprint != payload_fingerprint
        ):
            errors.add(HKCaseOutputReason.LIMIT_MEASUREMENT_INVALID)
    return errors


def _result(
    request: HKCaseOutputRequest,
    request_fingerprint: str,
    outcome_counts: tuple[HKCaseCandidateOutcomeCount, ...],
    decision: _OutputDecision,
) -> HKCaseOutputResult:
    measured = decision.measurements or {}
    validated_records = (
        request.proposed_records
        if decision.measurements is not None
        and decision.outcome
        in {
            HKCaseOutputOutcome.BLOCKED,
            HKCaseOutputOutcome.QUARANTINED_UNRESOLVED,
            HKCaseOutputOutcome.VALID_OUTPUT,
            HKCaseOutputOutcome.VALID_ZERO_OUTPUT,
        }
        else ()
    )
    return HKCaseOutputResult(
        request_fingerprint=request_fingerprint,
        outcome=decision.outcome,
        reasons=tuple(sorted(decision.reasons, key=str)),
        discovered_candidate_count=len(request.discovered_candidate_ids),
        final_candidate_count=len(request.candidates),
        candidate_outcome_counts=outcome_counts,
        source_unit_count=len(request.source_units),
        source_range_count=len(request.source_ranges),
        proposition_count=len(request.propositions),
        evidence_link_count=sum(len(item.evidence_links) for item in request.propositions),
        validated_record_count=len(validated_records),
        validated_payload_fingerprints=tuple(
            item.payload_fingerprint for item in validated_records
        ),
        measured_text_token_counts=tuple(
            measured[item.proposition_id][0]
            for item in request.propositions
            if item.proposition_id in measured
        ),
        measured_payload_byte_counts=tuple(
            measured[item.proposition_id][1]
            for item in request.propositions
            if item.proposition_id in measured
        ),
        coverage_gap_ids=tuple(
            item.coverage_gap_id
            for item in request.propositions
            if item.coverage_gap_id is not None
        ),
        search_records_created=0,
        release_eligible=False,
        semantic_analysis_authorized=False,
        external_effects="NONE",
    )


def hk_case_output_request_document(request: HKCaseOutputRequest) -> dict[str, JsonValue]:
    """Return the canonical JSON-compatible request projection."""
    return {
        "schema_id": "asklegal.hk-cases.output-request",
        "schema_version": HK_CASE_OUTPUT_CONTRACT_VERSION,
        "rule_id": HK_CASE_OUTPUT_RULE_ID,
        "judicial_decision_id": request.judicial_decision_id,
        "official_version_id": request.official_version_id,
        "ledger_fingerprint": request.ledger_fingerprint,
        "renderer_id": request.renderer_id,
        "tokenizer_profile_fingerprint": request.tokenizer_profile_fingerprint,
        "max_text_tokens": request.max_text_tokens,
        "max_payload_bytes": request.max_payload_bytes,
        "source_map_available": request.source_map_available,
        "discovered_candidate_ids": list(request.discovered_candidate_ids),
        "candidates": [
            {
                "candidate_id": item.candidate_id,
                "outcome": item.outcome.value,
                "proposition_ids": list(item.proposition_ids),
                "related_candidate_ids": list(item.related_candidate_ids),
                "reason_code": item.reason_code,
            }
            for item in request.candidates
        ],
        "source_units": [
            {
                "unit_id": item.unit_id,
                "source_order": item.source_order,
                "exact_text": item.exact_text,
            }
            for item in request.source_units
        ],
        "source_ranges": [
            {
                "range_id": item.range_id,
                "unit_id": item.unit_id,
                "start_byte": item.start_byte,
                "end_byte": item.end_byte,
                "exact_text_fingerprint": item.exact_text_fingerprint,
            }
            for item in request.source_ranges
        ],
        "propositions": [_proposition_document(item) for item in request.propositions],
        "ledger_proposition_ids": list(request.ledger_proposition_ids),
        "proposed_records": [_record_document(item) for item in request.proposed_records],
    }


def _proposition_document(item: HKCaseOutputProposition) -> dict[str, JsonValue]:
    return {
        "proposition_id": item.proposition_id,
        "candidate_id": item.candidate_id,
        "case_name": item.case_name,
        "official_citation": item.official_citation,
        "court": item.court,
        "decision_date": item.decision_date,
        "opinion_label": item.opinion_label,
        "authority_role": item.authority_role.value,
        "legal_issue": item.legal_issue,
        "derived_statement": item.derived_statement,
        "material_context": item.material_context,
        "qualifications": item.qualifications,
        "application_and_result": item.application_and_result,
        "evidence_links": [
            {"role": link.role.value, "range_id": link.range_id} for link in item.evidence_links
        ],
        "quotations": [
            {"range_id": quotation.range_id, "exact_text": quotation.exact_text}
            for quotation in item.quotations
        ],
        "authority_note": item.authority_note,
        "boundary_indivisible": item.boundary_indivisible,
        "coverage_gap_id": item.coverage_gap_id,
    }


def _record_document(item: HKCaseProposedServingRecord) -> dict[str, JsonValue]:
    return {
        "record_id": item.record_id,
        "proposition_id": item.proposition_id,
        "ledger_fingerprint": item.ledger_fingerprint,
        "renderer_proposition_id": item.renderer_proposition_id,
        "text": item.text,
        "country": item.country,
        "jurisdiction": item.jurisdiction,
        "type": item.material_type,
        "source": item.source,
        "authority_note": item.authority_note,
        "text_token_count": item.text_token_count,
        "payload_byte_count": item.payload_byte_count,
        "payload_fingerprint": item.payload_fingerprint,
    }


def hk_case_output_result_document(result: HKCaseOutputResult) -> dict[str, JsonValue]:
    """Return one canonical JSON-compatible result projection."""
    return {
        "schema_id": "asklegal.hk-cases.output-result",
        "schema_version": HK_CASE_OUTPUT_CONTRACT_VERSION,
        "rule_id": HK_CASE_OUTPUT_RULE_ID,
        "request_fingerprint": result.request_fingerprint,
        "outcome": result.outcome.value,
        "reasons": [item.value for item in result.reasons],
        "discovered_candidate_count": result.discovered_candidate_count,
        "final_candidate_count": result.final_candidate_count,
        "candidate_outcome_counts": [
            {"outcome": item.outcome.value, "count": item.count}
            for item in result.candidate_outcome_counts
        ],
        "source_unit_count": result.source_unit_count,
        "source_range_count": result.source_range_count,
        "proposition_count": result.proposition_count,
        "evidence_link_count": result.evidence_link_count,
        "validated_record_count": result.validated_record_count,
        "validated_payload_fingerprints": list(result.validated_payload_fingerprints),
        "measured_text_token_counts": list(result.measured_text_token_counts),
        "measured_payload_byte_counts": list(result.measured_payload_byte_counts),
        "coverage_gap_ids": list(result.coverage_gap_ids),
        "search_records_created": result.search_records_created,
        "release_eligible": result.release_eligible,
        "semantic_analysis_authorized": result.semantic_analysis_authorized,
        "external_effects": result.external_effects,
    }


def hk_case_output_request_from_document(document: object) -> HKCaseOutputRequest:
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
            "ledger_fingerprint",
            "renderer_id",
            "tokenizer_profile_fingerprint",
            "max_text_tokens",
            "max_payload_bytes",
            "source_map_available",
            "discovered_candidate_ids",
            "candidates",
            "source_units",
            "source_ranges",
            "propositions",
            "ledger_proposition_ids",
            "proposed_records",
        },
    )
    _constant(root["schema_id"], "asklegal.hk-cases.output-request")
    _constant(root["schema_version"], HK_CASE_OUTPUT_CONTRACT_VERSION)
    _constant(root["rule_id"], HK_CASE_OUTPUT_RULE_ID)
    return HKCaseOutputRequest(
        _identity(root["judicial_decision_id"]),
        _identity(root["official_version_id"]),
        _fingerprint(root["ledger_fingerprint"]),
        _constant_text(root["renderer_id"], HK_CASE_OUTPUT_RENDERER_ID),
        _fingerprint(root["tokenizer_profile_fingerprint"]),
        _positive_integer(root["max_text_tokens"]),
        _positive_integer(root["max_payload_bytes"]),
        _boolean(root["source_map_available"]),
        _identities(root["discovered_candidate_ids"]),
        tuple(_candidate(item) for item in _array(root["candidates"])),
        tuple(_source_unit(item) for item in _array(root["source_units"])),
        tuple(_source_range(item) for item in _array(root["source_ranges"])),
        tuple(_proposition(item) for item in _array(root["propositions"])),
        _identities(root["ledger_proposition_ids"]),
        tuple(_record(item) for item in _array(root["proposed_records"])),
    )


def _candidate(value: JsonValue) -> HKCaseOutputCandidate:
    root = _object(value)
    _exact_keys(
        root,
        {
            "candidate_id",
            "outcome",
            "proposition_ids",
            "related_candidate_ids",
            "reason_code",
        },
    )
    return HKCaseOutputCandidate(
        _identity(root["candidate_id"]),
        _enum(root["outcome"], HKCaseCandidateOutcome),
        _identities(root["proposition_ids"]),
        _identities(root["related_candidate_ids"]),
        _optional_code(root["reason_code"]),
    )


def _source_unit(value: JsonValue) -> HKCaseSourceUnitText:
    root = _object(value)
    _exact_keys(root, {"unit_id", "source_order", "exact_text"})
    return HKCaseSourceUnitText(
        _identity(root["unit_id"]),
        _positive_integer(root["source_order"]),
        _string(root["exact_text"]),
    )


def _source_range(value: JsonValue) -> HKCaseSourceRange:
    root = _object(value)
    _exact_keys(
        root,
        {"range_id", "unit_id", "start_byte", "end_byte", "exact_text_fingerprint"},
    )
    return HKCaseSourceRange(
        _identity(root["range_id"]),
        _identity(root["unit_id"]),
        _nonnegative_integer(root["start_byte"]),
        _positive_integer(root["end_byte"]),
        _fingerprint(root["exact_text_fingerprint"]),
    )


def _proposition(value: JsonValue) -> HKCaseOutputProposition:
    root = _object(value)
    _exact_keys(
        root,
        {
            "proposition_id",
            "candidate_id",
            "case_name",
            "official_citation",
            "court",
            "decision_date",
            "opinion_label",
            "authority_role",
            "legal_issue",
            "derived_statement",
            "material_context",
            "qualifications",
            "application_and_result",
            "evidence_links",
            "quotations",
            "authority_note",
            "boundary_indivisible",
            "coverage_gap_id",
        },
    )
    return HKCaseOutputProposition(
        _identity(root["proposition_id"]),
        _identity(root["candidate_id"]),
        _string(root["case_name"]),
        _string(root["official_citation"]),
        _string(root["court"]),
        _string(root["decision_date"]),
        _string(root["opinion_label"]),
        _enum(root["authority_role"], HKCaseOpinionRole),
        _string(root["legal_issue"]),
        _string(root["derived_statement"]),
        _optional_string(root["material_context"]),
        _optional_string(root["qualifications"]),
        _string(root["application_and_result"]),
        tuple(_evidence_link(item) for item in _array(root["evidence_links"])),
        tuple(_quotation(item) for item in _array(root["quotations"])),
        _string(root["authority_note"]),
        _boolean(root["boundary_indivisible"]),
        _optional_identity(root["coverage_gap_id"]),
    )


def _evidence_link(value: JsonValue) -> HKCasePropositionEvidenceLink:
    root = _object(value)
    _exact_keys(root, {"role", "range_id"})
    return HKCasePropositionEvidenceLink(
        _enum(root["role"], HKCaseEvidenceRole),
        _identity(root["range_id"]),
    )


def _quotation(value: JsonValue) -> HKCaseQuotation:
    root = _object(value)
    _exact_keys(root, {"range_id", "exact_text"})
    return HKCaseQuotation(_identity(root["range_id"]), _string(root["exact_text"]))


def _record(value: JsonValue) -> HKCaseProposedServingRecord:
    root = _object(value)
    _exact_keys(
        root,
        {
            "record_id",
            "proposition_id",
            "ledger_fingerprint",
            "renderer_proposition_id",
            "text",
            "country",
            "jurisdiction",
            "type",
            "source",
            "authority_note",
            "text_token_count",
            "payload_byte_count",
            "payload_fingerprint",
        },
    )
    return HKCaseProposedServingRecord(
        _identity(root["record_id"]),
        _identity(root["proposition_id"]),
        _fingerprint(root["ledger_fingerprint"]),
        _identity(root["renderer_proposition_id"]),
        _string(root["text"]),
        _string(root["country"]),
        _string(root["jurisdiction"]),
        _string(root["type"]),
        _string(root["source"]),
        _string(root["authority_note"]),
        _nonnegative_integer(root["text_token_count"]),
        _positive_integer(root["payload_byte_count"]),
        _fingerprint(root["payload_fingerprint"]),
    )


def _duplicates[T](values: tuple[T, ...]) -> bool:
    return len(values) != len(set(values))


def _raw_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _is_object(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def _object(value: object) -> dict[str, JsonValue]:
    if not _is_object(value) or any(type(key) is not str for key in value):
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT)
    return {str(key): checked_json_value(item) for key, item in value.items()}


def _array(value: JsonValue) -> list[JsonValue]:
    if type(value) is not list:
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT)
    return value


def _exact_keys(root: dict[str, JsonValue], expected: set[str]) -> None:
    if set(root) != expected:
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT)


def _constant(value: JsonValue, expected: str) -> None:
    if value != expected:
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT)


def _constant_text(value: JsonValue, expected: str) -> str:
    _constant(value, expected)
    return expected


def _string(value: JsonValue) -> str:
    if type(value) is not str or not value:
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT)
    return value


def _optional_string(value: JsonValue) -> str | None:
    return None if value is None else _string(value)


def _identity(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_IDENTITY_PATTERN, result) is None:
        raise HKCaseOutputError(HKCaseOutputErrorCode.IDENTITY)
    return result


def _optional_identity(value: JsonValue) -> str | None:
    return None if value is None else _identity(value)


def _identities(value: JsonValue) -> tuple[str, ...]:
    return tuple(_identity(item) for item in _array(value))


def _optional_code(value: JsonValue) -> str | None:
    if value is None:
        return None
    result = _string(value)
    if fullmatch(_CODE_PATTERN, result) is None:
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT)
    return result


def _fingerprint(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        raise HKCaseOutputError(HKCaseOutputErrorCode.FINGERPRINT)
    return result


def _positive_integer(value: JsonValue) -> int:
    if type(value) is not int or value < 1:
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT)
    return value


def _nonnegative_integer(value: JsonValue) -> int:
    if type(value) is not int or value < 0:
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT)
    return value


def _boolean(value: JsonValue) -> bool:
    if type(value) is not bool:
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT)
    return value


def _enum[T: StrEnum](value: JsonValue, enum_type: type[T]) -> T:
    try:
        return enum_type(_string(value))
    except ValueError as error:
        raise HKCaseOutputError(HKCaseOutputErrorCode.CONTRACT) from error
