"""ADR 0074/0075 HKEX canonical-rendering conformance artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from typing import Never, TypeIs
from unicodedata import normalize

from asklegal_contracts import ContractViolation, canonicalize, fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_regulatory_inventory import HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID

HKEX_RENDERING_DECISION_RULE_ID = "HKREG-RENDERING-DECISION-001"
HKEX_RENDERING_DECISION_CONTRACT_VERSION = "1.0.0"
HKEX_RENDERING_DECISION_CASE_COUNT = 35

_CASE_PATTERN = r"HKREG-DET-RND-(0[0-2][0-9]|03[0-5])"
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_CONTRACT_BINDING_COUNT = 2
_FORM_STRUCTURE_ELEMENT_THRESHOLD = 2
_EXPECTED_PAIRS: dict[str, tuple[tuple[str, str], ...]] = {
    "HKREG-DET-RND-005": (("HKREG-PAIR-032", "POSITIVE"),),
    "HKREG-DET-RND-006": (("HKREG-PAIR-032", "NEAR_MISS"),),
    "HKREG-DET-RND-014": (("HKREG-PAIR-057", "POSITIVE"),),
    "HKREG-DET-RND-015": (("HKREG-PAIR-057", "NEAR_MISS"),),
    "HKREG-DET-RND-017": (("HKREG-PAIR-033", "POSITIVE"),),
    "HKREG-DET-RND-018": (("HKREG-PAIR-033", "NEAR_MISS"),),
    "HKREG-DET-RND-020": (("HKREG-PAIR-034", "POSITIVE"),),
    "HKREG-DET-RND-021": (("HKREG-PAIR-034", "NEAR_MISS"),),
    "HKREG-DET-RND-022": (("HKREG-PAIR-035", "POSITIVE"),),
    "HKREG-DET-RND-023": (("HKREG-PAIR-035", "NEAR_MISS"),),
    "HKREG-DET-RND-024": (("HKREG-PAIR-036", "POSITIVE"),),
    "HKREG-DET-RND-025": (("HKREG-PAIR-036", "NEAR_MISS"),),
    "HKREG-DET-RND-029": (("HKREG-PAIR-037", "POSITIVE"),),
    "HKREG-DET-RND-030": (("HKREG-PAIR-037", "NEAR_MISS"),),
}


class HKEXRenderingErrorCode(StrEnum):
    """Closed malformed rendering-case envelope failures."""

    CONTRACT = "HKREG_RENDERING_CONTRACT_INVALID"
    IDENTITY = "HKREG_RENDERING_IDENTITY_INVALID"
    FINGERPRINT = "HKREG_RENDERING_FINGERPRINT_INVALID"


class HKEXRenderingError(ValueError):
    """One fail-closed permanent rendering-case rejection."""

    code: HKEXRenderingErrorCode

    def __init__(self, code: HKEXRenderingErrorCode) -> None:
        """Create one stable fail-closed error."""
        self.code = code
        super().__init__(code.value)


class HKEXRenderingAssertionScope(StrEnum):
    """Closed artifact dimension, never a case-identity switch."""

    ORDINARY = "ORDINARY"
    TABLE = "TABLE"
    FEE = "FEE"
    FORM = "FORM"
    LANGUAGE = "LANGUAGE"
    UNCERTAINTY = "UNCERTAINTY"
    AUTHORITY_NOTE = "AUTHORITY_NOTE"


class HKEXRenderingProjectionKind(StrEnum):
    """Closed source-faithful canonical projection families."""

    ORDINARY = "ORDINARY"
    TABLE = "TABLE"
    FEE = "FEE"
    FORM = "FORM"


class HKEXRenderingOutcome(StrEnum):
    """Effect-free artifact result."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


class HKEXRenderingReason(StrEnum):
    """Exact permanent canonical-rendering result reasons."""

    CANONICAL_RENDERED = "CANONICAL_RENDERED"
    BOARD_ISOLATION_PRESERVED = "BOARD_ISOLATION_PRESERVED"
    OFFICIAL_HEADING_INCLUDED = "OFFICIAL_HEADING_INCLUDED"
    OFFICIAL_HEADING_OMITTED = "OFFICIAL_HEADING_OMITTED"
    EFFECTIVE_CONTEXT_INCLUDED = "EFFECTIVE_CONTEXT_INCLUDED"
    EFFECTIVE_CONTEXT_OMITTED = "EFFECTIVE_CONTEXT_OMITTED"
    GOVERNING_CONTEXT_INCLUDED = "GOVERNING_CONTEXT_INCLUDED"
    GOVERNING_CONTEXT_OMITTED = "GOVERNING_CONTEXT_OMITTED"
    REFERENCE_RENDERED = "REFERENCE_RENDERED"
    REFERENCE_OMITTED = "REFERENCE_OMITTED"
    SOURCE_FIDELITY_PRESERVED = "SOURCE_FIDELITY_PRESERVED"
    CANONICAL_NORMALIZED = "CANONICAL_NORMALIZED"
    FORBIDDEN_CONTENT_EXCLUDED = "FORBIDDEN_CONTENT_EXCLUDED"
    AUTHORITY_NONE_SEPARATE = "AUTHORITY_NONE_SEPARATE"
    AUTHORITY_WARNING_SEPARATE = "AUTHORITY_WARNING_SEPARATE"
    COMPLETE_MEASUREMENT = "COMPLETE_MEASUREMENT"
    TABLE_COMPLETE = "TABLE_COMPLETE"
    TABLE_INCOMPLETE = "TABLE_INCOMPLETE"
    TABLE_SPAN_PRESERVED = "TABLE_SPAN_PRESERVED"
    PRESENTATION_CHANGE_STABLE = "PRESENTATION_CHANGE_STABLE"
    MATERIAL_TABLE_CHANGE = "MATERIAL_TABLE_CHANGE"
    FEE_COMPLETE = "FEE_COMPLETE"
    FEE_INCOMPLETE = "FEE_INCOMPLETE"
    FORM_COMPLETE = "FORM_COMPLETE"
    PRESENTATION_CONTROL_OMITTED = "PRESENTATION_CONTROL_OMITTED"
    FORM_STRUCTURE_COMPLETE = "FORM_STRUCTURE_COMPLETE"
    NEUTRAL_MARKERS_PRESERVED = "NEUTRAL_MARKERS_PRESERVED"
    FORM_FRAGMENTATION_REJECTED = "FORM_FRAGMENTATION_REJECTED"
    ENGLISH_ONLY_SERVING = "ENGLISH_ONLY_SERVING"
    CHINESE_SERVING_REJECTED = "CHINESE_SERVING_REJECTED"
    SOURCE_AMBIGUITY_QUARANTINED = "SOURCE_AMBIGUITY_QUARANTINED"
    TRANSITION_WARNING_SEPARATE = "TRANSITION_WARNING_SEPARATE"
    MARKET_WARNING_SEPARATE = "MARKET_WARNING_SEPARATE"
    SOURCE_WARNING_SEPARATE = "SOURCE_WARNING_SEPARATE"
    REPRESENTATION_WARNING_SEPARATE = "REPRESENTATION_WARNING_SEPARATE"


class HKEXRenderingIdentityConsequence(StrEnum):
    """Six-field identity consequence without allocating a record ID."""

    NOT_EVALUATED = "NOT_EVALUATED"
    PRESERVE_EXISTING = "PRESERVE_EXISTING"
    NEW_RECORD_REQUIRED = "NEW_RECORD_REQUIRED"


class HKEXRenderingVectorResponsibility(StrEnum):
    """Candidate vector consequence without embedding authority."""

    NONE = "NONE"
    ONE_ENGLISH_TEXT = "ONE_ENGLISH_TEXT"


@dataclass(frozen=True, slots=True)
class HKEXRenderingContractBinding:
    """One exact contract bound into a permanent rendering case."""

    contract_id: str
    version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXRenderingPairMembership:
    """One permanent case's exact high-risk pair role."""

    pair_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKEXRenderingEvidencePacket:
    """One proposal-safe synthetic rendering fact packet."""

    slot_id: str
    state: str
    path: str
    role: str
    media_type: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXRenderingReference:
    """One exact referenced-location label without target text."""

    locator: str
    official_heading: str | None

    def document(self) -> dict[str, object]:
        """Return one JSON-compatible referenced location."""
        return {"locator": self.locator, "official_heading": self.official_heading}


@dataclass(frozen=True, slots=True)
class HKEXRenderingFacts:
    """Orthogonal source-fidelity and canonical-projection facts."""

    scope_id: str
    component_label: str
    location_label: str
    official_heading: str | None
    effective_context: str | None
    dependency_lines: tuple[str, ...]
    references: tuple[HKEXRenderingReference, ...]
    primary_lines: tuple[str, ...]
    projection_kind: HKEXRenderingProjectionKind
    required_element_ids: tuple[str, ...]
    present_element_ids: tuple[str, ...]
    presentation_only_element_ids: tuple[str, ...]
    forbidden_element_ids: tuple[str, ...]
    optional_chinese_evidence_present: bool
    chinese_text_inserted: bool
    chinese_duplicate_requested: bool
    parallel_vector_requested: bool
    source_ambiguity: bool
    presentation_only_change: bool
    material_projection_change: bool
    authority_note: str
    tokenizer_id: str
    tokenizer_fingerprint: str
    max_text_tokens: int
    max_metadata_bytes: int


@dataclass(frozen=True, slots=True)
class HKEXRenderingDecision:
    """One complete deterministic artifact result without serving authority."""

    outcome: HKEXRenderingOutcome
    reason: HKEXRenderingReason
    canonical_text: str | None
    authority_note: str | None
    embedding_input: str | None
    text_tokens: int | None
    metadata_bytes: int | None
    text_limit: int | None
    metadata_limit: int | None
    fits: bool | None
    omitted_element_ids: tuple[str, ...]
    rejected_element_ids: tuple[str, ...]
    quarantined_element_ids: tuple[str, ...]
    identity_consequence: HKEXRenderingIdentityConsequence
    vector_responsibility: HKEXRenderingVectorResponsibility

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return one exact artifact decision with every effect denied."""
        _text(case_id)
        return {
            "schema_id": "asklegal.hk-regulatory.rendering-decision-result",
            "schema_version": HKEX_RENDERING_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_RENDERING_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "canonical_text": self.canonical_text,
            "authority_note": self.authority_note,
            "embedding_input": self.embedding_input,
            "text_tokens": self.text_tokens,
            "metadata_bytes": self.metadata_bytes,
            "text_limit": self.text_limit,
            "metadata_limit": self.metadata_limit,
            "fits": self.fits,
            "omitted_element_ids": list(self.omitted_element_ids),
            "rejected_element_ids": list(self.rejected_element_ids),
            "quarantined_element_ids": list(self.quarantined_element_ids),
            "identity_consequence": self.identity_consequence.value,
            "vector_responsibility": self.vector_responsibility.value,
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "external_effects": "NONE",
        }


@dataclass(frozen=True, slots=True)
class HKEXRenderingDecisionCase:
    """One strict decision-to-artifact conformance envelope."""

    case_id: str
    primary_coverage_cell_id: str
    pair_memberships: tuple[HKEXRenderingPairMembership, ...]
    assertion_scope: HKEXRenderingAssertionScope
    contract_bindings: tuple[HKEXRenderingContractBinding, ...]
    evidence_packet: HKEXRenderingEvidencePacket
    package_fingerprint: str
    title: str
    purpose: str
    expected_decision: HKEXRenderingDecision
    facts: HKEXRenderingFacts


@dataclass(frozen=True, slots=True)
class HKEXRenderingDecisionReport:
    """Complete expected-versus-observed rendering report."""

    case_id: str
    assertion_scope: HKEXRenderingAssertionScope
    observed_decision: HKEXRenderingDecision
    expected_decision: HKEXRenderingDecision
    conformance_status: str

    def document(self) -> dict[str, object]:
        """Return one exact effect-free conformance report."""
        return {
            "schema_id": "asklegal.hk-regulatory.rendering-decision-report",
            "schema_version": HKEX_RENDERING_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_RENDERING_DECISION_RULE_ID,
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
    pairs: tuple[HKEXRenderingPairMembership, ...]
    scope: HKEXRenderingAssertionScope
    bindings: tuple[HKEXRenderingContractBinding, ...]
    package_fingerprint: str


def hkex_rendering_decision_case_from_document(document: object) -> HKEXRenderingDecisionCase:
    """Strictly decode and fingerprint one permanent rendering case."""
    root = _object(_checked(document))
    _exact_keys(root, _CASE_FIELDS)
    header = _case_header(root)
    _validate_declarations(root, header.bindings)
    facts = _facts(root["facts"])
    packet = _packet(root["evidence_packet"], facts)
    expected = _decision_from_document(root["expected_decision"], header.case_id)
    _validate_case_fingerprint(root)
    return HKEXRenderingDecisionCase(
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


def decide_hkex_rendering_case(case: HKEXRenderingDecisionCase) -> HKEXRenderingDecision:
    """Derive one artifact from source-shaped facts and scope, never case ID."""
    if type(case) is not HKEXRenderingDecisionCase:
        _fail()
    facts = case.facts
    if facts.source_ambiguity:
        return _terminal(
            HKEXRenderingOutcome.QUARANTINE,
            HKEXRenderingReason.SOURCE_AMBIGUITY_QUARANTINED,
            quarantined=facts.present_element_ids,
        )
    if (
        facts.chinese_text_inserted
        or facts.chinese_duplicate_requested
        or facts.parallel_vector_requested
    ):
        return _terminal(
            HKEXRenderingOutcome.BLOCK,
            HKEXRenderingReason.CHINESE_SERVING_REJECTED,
            rejected=(
                "chinese-text" if facts.chinese_text_inserted else "",
                "chinese-duplicate" if facts.chinese_duplicate_requested else "",
                "parallel-vector" if facts.parallel_vector_requested else "",
            ),
        )
    missing = tuple(
        item for item in facts.required_element_ids if item not in facts.present_element_ids
    )
    if missing:
        reasons = {
            HKEXRenderingProjectionKind.TABLE: HKEXRenderingReason.TABLE_INCOMPLETE,
            HKEXRenderingProjectionKind.FEE: HKEXRenderingReason.FEE_INCOMPLETE,
            HKEXRenderingProjectionKind.FORM: HKEXRenderingReason.FORM_FRAGMENTATION_REJECTED,
        }
        return _terminal(
            HKEXRenderingOutcome.BLOCK,
            reasons.get(facts.projection_kind, HKEXRenderingReason.SOURCE_FIDELITY_PRESERVED),
            rejected=missing,
        )
    text = _render(facts)
    reason = _reason(case.assertion_scope, facts)
    payload = checked_json_value(
        {
            "authority_note": facts.authority_note,
            "country": "Hong Kong",
            "jurisdiction": "Hong Kong",
            "source": "HKEX",
            "text": text,
            "type": "regulatory_material",
        }
    )
    identity = HKEXRenderingIdentityConsequence.NOT_EVALUATED
    if facts.material_projection_change or (
        case.assertion_scope is HKEXRenderingAssertionScope.AUTHORITY_NOTE
        and facts.authority_note != "None"
    ):
        identity = HKEXRenderingIdentityConsequence.NEW_RECORD_REQUIRED
    elif facts.presentation_only_change or facts.optional_chinese_evidence_present:
        identity = HKEXRenderingIdentityConsequence.PRESERVE_EXISTING
    text_tokens = len(text)
    metadata_bytes = len(canonicalize(payload))
    return HKEXRenderingDecision(
        HKEXRenderingOutcome.PASS,
        reason,
        text,
        facts.authority_note,
        text,
        text_tokens,
        metadata_bytes,
        facts.max_text_tokens,
        facts.max_metadata_bytes,
        text_tokens <= facts.max_text_tokens and metadata_bytes <= facts.max_metadata_bytes,
        facts.presentation_only_element_ids,
        facts.forbidden_element_ids,
        (),
        identity,
        HKEXRenderingVectorResponsibility.ONE_ENGLISH_TEXT,
    )


def run_hkex_rendering_case(case: HKEXRenderingDecisionCase) -> HKEXRenderingDecisionReport:
    """Compare fact-derived artifact bytes with independently frozen truth."""
    observed = decide_hkex_rendering_case(case)
    return HKEXRenderingDecisionReport(
        case.case_id,
        case.assertion_scope,
        observed,
        case.expected_decision,
        "PASS" if observed == case.expected_decision else "FAIL",
    )


def _terminal(
    outcome: HKEXRenderingOutcome,
    reason: HKEXRenderingReason,
    *,
    rejected: tuple[str, ...] = (),
    quarantined: tuple[str, ...] = (),
) -> HKEXRenderingDecision:
    return HKEXRenderingDecision(
        outcome,
        reason,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        (),
        tuple(item for item in rejected if item),
        quarantined,
        HKEXRenderingIdentityConsequence.NOT_EVALUATED,
        HKEXRenderingVectorResponsibility.NONE,
    )


def _reason(scope: HKEXRenderingAssertionScope, facts: HKEXRenderingFacts) -> HKEXRenderingReason:
    resolvers = {
        HKEXRenderingAssertionScope.ORDINARY: _ordinary_reason,
        HKEXRenderingAssertionScope.TABLE: _table_reason,
        HKEXRenderingAssertionScope.FEE: _fee_reason,
        HKEXRenderingAssertionScope.FORM: _form_reason,
        HKEXRenderingAssertionScope.LANGUAGE: _language_reason,
        HKEXRenderingAssertionScope.UNCERTAINTY: _ordinary_reason,
        HKEXRenderingAssertionScope.AUTHORITY_NOTE: _authority_scope_reason,
    }
    return resolvers[scope](facts)


def _ordinary_reason(facts: HKEXRenderingFacts) -> HKEXRenderingReason:
    markers = set(facts.present_element_ids)
    candidates = (
        (bool(facts.forbidden_element_ids), HKEXRenderingReason.FORBIDDEN_CONTENT_EXCLUDED),
        ("complete-measurement" in markers, HKEXRenderingReason.COMPLETE_MEASUREMENT),
        ("canonical-normalization" in markers, HKEXRenderingReason.CANONICAL_NORMALIZED),
        ("source-fidelity" in markers, HKEXRenderingReason.SOURCE_FIDELITY_PRESERVED),
        ("reference-explicitly-absent" in markers, HKEXRenderingReason.REFERENCE_OMITTED),
        (
            "dependency-explicitly-absent" in markers,
            HKEXRenderingReason.GOVERNING_CONTEXT_OMITTED,
        ),
        (
            "effective-context-explicitly-absent" in markers,
            HKEXRenderingReason.EFFECTIVE_CONTEXT_OMITTED,
        ),
        ("heading-explicitly-absent" in markers, HKEXRenderingReason.OFFICIAL_HEADING_OMITTED),
        (facts.presentation_only_change, HKEXRenderingReason.PRESENTATION_CHANGE_STABLE),
        (facts.effective_context is not None, HKEXRenderingReason.EFFECTIVE_CONTEXT_INCLUDED),
        (bool(facts.dependency_lines), HKEXRenderingReason.GOVERNING_CONTEXT_INCLUDED),
        (bool(facts.references), HKEXRenderingReason.REFERENCE_RENDERED),
        (facts.official_heading is not None, HKEXRenderingReason.OFFICIAL_HEADING_INCLUDED),
        (facts.scope_id == HKEX_GEM_SCOPE_ID, HKEXRenderingReason.BOARD_ISOLATION_PRESERVED),
    )
    return next(
        (reason for condition, reason in candidates if condition),
        HKEXRenderingReason.CANONICAL_RENDERED,
    )


def _fee_reason(_facts: HKEXRenderingFacts) -> HKEXRenderingReason:
    return HKEXRenderingReason.FEE_COMPLETE


def _language_reason(_facts: HKEXRenderingFacts) -> HKEXRenderingReason:
    return HKEXRenderingReason.ENGLISH_ONLY_SERVING


def _authority_scope_reason(facts: HKEXRenderingFacts) -> HKEXRenderingReason:
    return _authority_reason(facts.authority_note)


def _table_reason(facts: HKEXRenderingFacts) -> HKEXRenderingReason:
    if facts.presentation_only_change:
        return HKEXRenderingReason.PRESENTATION_CHANGE_STABLE
    if facts.material_projection_change:
        return HKEXRenderingReason.MATERIAL_TABLE_CHANGE
    if "row-span" in facts.required_element_ids:
        return HKEXRenderingReason.TABLE_SPAN_PRESERVED
    return HKEXRenderingReason.TABLE_COMPLETE


def _form_reason(facts: HKEXRenderingFacts) -> HKEXRenderingReason:
    if facts.presentation_only_element_ids:
        return HKEXRenderingReason.PRESENTATION_CONTROL_OMITTED
    if "neutral-marker" in facts.required_element_ids:
        return HKEXRenderingReason.NEUTRAL_MARKERS_PRESERVED
    if len(facts.required_element_ids) > _FORM_STRUCTURE_ELEMENT_THRESHOLD:
        return HKEXRenderingReason.FORM_STRUCTURE_COMPLETE
    return HKEXRenderingReason.FORM_COMPLETE


def _authority_reason(authority_note: str) -> HKEXRenderingReason:
    prefixes = (
        ("Effective-date limitation:", HKEXRenderingReason.TRANSITION_WARNING_SEPARATE),
        ("Market-scope limitation:", HKEXRenderingReason.MARKET_WARNING_SEPARATE),
        ("Source limitation:", HKEXRenderingReason.SOURCE_WARNING_SEPARATE),
        ("Representation limitation:", HKEXRenderingReason.REPRESENTATION_WARNING_SEPARATE),
    )
    if authority_note == "None":
        return HKEXRenderingReason.AUTHORITY_NONE_SEPARATE
    return next(
        (reason for prefix, reason in prefixes if authority_note.startswith(prefix)),
        HKEXRenderingReason.AUTHORITY_WARNING_SEPARATE,
    )


def _render(facts: HKEXRenderingFacts) -> str:
    market = "Main Board" if facts.scope_id == HKEX_MAIN_SCOPE_ID else "GEM"
    lines = [
        "Context:",
        "Material: HKEX Listing Rule — non-statutory exchange regulatory rule",
        f"Market: {market}",
        f"Component: {_canonical_line(facts.component_label)}",
        f"Location: {_canonical_line(facts.location_label)}",
    ]
    if facts.official_heading is not None:
        lines.append(f"Official heading: {_canonical_line(facts.official_heading)}")
    if facts.effective_context is not None:
        lines.append(f"Effective context: {_canonical_line(facts.effective_context)}")
    blocks = ["\n".join(lines)]
    if facts.dependency_lines:
        blocks.append(
            "Required governing context:\n"
            + "\n".join(_canonical_line(item) for item in facts.dependency_lines)
        )
    if facts.references:
        blocks.append(
            "Referenced locations:\n"
            + "\n".join(
                f"- {_canonical_line(item.locator)}"
                + (
                    f" — {_canonical_line(item.official_heading)}"
                    if item.official_heading is not None
                    else ""
                )
                for item in facts.references
            )
        )
    blocks.append(
        "English rule text — prevailing language:\n"
        + "\n".join(_canonical_line(item) for item in facts.primary_lines)
    )
    return "\n\n".join(blocks)


def _canonical_line(value: str) -> str:
    converted = normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip() for line in converted.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    result = "\n".join(lines)
    if not result:
        _fail()
    return result


_FACT_FIELDS = {
    "scope_id",
    "component_label",
    "location_label",
    "official_heading",
    "effective_context",
    "dependency_lines",
    "references",
    "primary_lines",
    "projection_kind",
    "required_element_ids",
    "present_element_ids",
    "presentation_only_element_ids",
    "forbidden_element_ids",
    "optional_chinese_evidence_present",
    "chinese_text_inserted",
    "chinese_duplicate_requested",
    "parallel_vector_requested",
    "source_ambiguity",
    "presentation_only_change",
    "material_projection_change",
    "authority_note",
    "tokenizer_id",
    "tokenizer_fingerprint",
    "max_text_tokens",
    "max_metadata_bytes",
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
    "canonical_text",
    "authority_note",
    "embedding_input",
    "text_tokens",
    "metadata_bytes",
    "text_limit",
    "metadata_limit",
    "fits",
    "omitted_element_ids",
    "rejected_element_ids",
    "quarantined_element_ids",
    "identity_consequence",
    "vector_responsibility",
    "search_record_authorized",
    "embedding_authorized",
    "release_authorized",
    "serving_authorized",
    "external_effects",
}


def _case_header(root: dict[str, JsonValue]) -> _CaseHeader:
    _constant(root["schema_id"], "asklegal.hk-regulatory.rendering-decision-case")
    _constant(root["schema_version"], HKEX_RENDERING_DECISION_CONTRACT_VERSION)
    _constant(root["package_contract_version"], "1.0.0")
    case_id = _pattern(root["case_id"], _CASE_PATTERN)
    suffix = case_id.rsplit("-", maxsplit=1)[1]
    _constant(root["suite_layer"], "DECISION_TO_ARTIFACT")
    _constant(root["primary_checkpoint"], "CANONICAL_RENDERING")
    _true(root["frozen"])
    _constant(root["synthetic_evidence_class"], "SYNTHETIC_NO_REAL_AUTHORITY")
    _constant(root["synthetic_cutoff"], "2026-08-24T00:00:00Z")
    _constant(root["scope_id"], "HKEX_CROSS_BOARD")
    _constant(root["prior_state"], "SYNTHETIC_ACCEPTED_PREDECESSOR")
    primary = _strings(root["primary_coverage_cell_ids"])
    if primary != (f"HKREG-COV-DRND-{suffix}",):
        _fail(HKEXRenderingErrorCode.IDENTITY)
    bindings = _bindings(root["contract_bindings"])
    package_fingerprint = _fingerprint(root["package_fingerprint"])
    _validate_bindings(bindings, package_fingerprint)
    return _CaseHeader(
        case_id,
        primary[0],
        _pairs(root["pair_memberships"], case_id),
        _enum(root["assertion_scope"], HKEXRenderingAssertionScope),
        bindings,
        package_fingerprint,
    )


def _validate_declarations(
    root: dict[str, JsonValue], bindings: tuple[HKEXRenderingContractBinding, ...]
) -> None:
    _sorted_strings(root["secondary_coverage_cell_ids"])
    if _strings(root["declared_input_inventory"]) != ("rendering-evidence",):
        _fail()
    if _strings(root["declared_reference_inventory"]) != tuple(
        item.contract_id for item in bindings
    ):
        _fail()
    if _strings(root["declared_expected_inventory"]) != ("RENDERING_DECISION_REPORT",):
        _fail()
    if _strings(root["required_result_dimensions"]) != (
        "AUTHORITY_NOTE",
        "CANONICAL_BYTES",
        "IDENTITY_CONSEQUENCE",
        "MEASUREMENT",
        "PROCESSING",
        "SOURCE_FIDELITY",
        "VECTOR_RESPONSIBILITY",
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
        _fail(HKEXRenderingErrorCode.FINGERPRINT)


def _facts(value: JsonValue) -> HKEXRenderingFacts:
    root = _object(value)
    _exact_keys(root, _FACT_FIELDS)
    scope_id = _text(root["scope_id"])
    if scope_id not in {HKEX_MAIN_SCOPE_ID, HKEX_GEM_SCOPE_ID}:
        _fail()
    result = HKEXRenderingFacts(
        scope_id,
        _text(root["component_label"]),
        _text(root["location_label"]),
        _nullable_text(root["official_heading"]),
        _nullable_text(root["effective_context"]),
        _strings(root["dependency_lines"], empty=True),
        tuple(_reference(item) for item in _array(root["references"])),
        _strings(root["primary_lines"]),
        _enum(root["projection_kind"], HKEXRenderingProjectionKind),
        _strings(root["required_element_ids"], empty=True),
        _strings(root["present_element_ids"], empty=True),
        _strings(root["presentation_only_element_ids"], empty=True),
        _strings(root["forbidden_element_ids"], empty=True),
        _boolean(root["optional_chinese_evidence_present"]),
        _boolean(root["chinese_text_inserted"]),
        _boolean(root["chinese_duplicate_requested"]),
        _boolean(root["parallel_vector_requested"]),
        _boolean(root["source_ambiguity"]),
        _boolean(root["presentation_only_change"]),
        _boolean(root["material_projection_change"]),
        _text(root["authority_note"]),
        _text(root["tokenizer_id"]),
        _fingerprint(root["tokenizer_fingerprint"]),
        _positive_integer(root["max_text_tokens"]),
        _positive_integer(root["max_metadata_bytes"]),
    )
    if set(result.presentation_only_element_ids).difference(result.present_element_ids):
        _fail()
    if set(result.forbidden_element_ids).difference(result.present_element_ids):
        _fail()
    return result


def _reference(value: JsonValue) -> HKEXRenderingReference:
    root = _object(value)
    _exact_keys(root, {"locator", "official_heading"})
    return HKEXRenderingReference(_text(root["locator"]), _nullable_text(root["official_heading"]))


def _facts_document(facts: HKEXRenderingFacts) -> dict[str, object]:
    return {
        "scope_id": facts.scope_id,
        "component_label": facts.component_label,
        "location_label": facts.location_label,
        "official_heading": facts.official_heading,
        "effective_context": facts.effective_context,
        "dependency_lines": list(facts.dependency_lines),
        "references": [item.document() for item in facts.references],
        "primary_lines": list(facts.primary_lines),
        "projection_kind": facts.projection_kind.value,
        "required_element_ids": list(facts.required_element_ids),
        "present_element_ids": list(facts.present_element_ids),
        "presentation_only_element_ids": list(facts.presentation_only_element_ids),
        "forbidden_element_ids": list(facts.forbidden_element_ids),
        "optional_chinese_evidence_present": facts.optional_chinese_evidence_present,
        "chinese_text_inserted": facts.chinese_text_inserted,
        "chinese_duplicate_requested": facts.chinese_duplicate_requested,
        "parallel_vector_requested": facts.parallel_vector_requested,
        "source_ambiguity": facts.source_ambiguity,
        "presentation_only_change": facts.presentation_only_change,
        "material_projection_change": facts.material_projection_change,
        "authority_note": facts.authority_note,
        "tokenizer_id": facts.tokenizer_id,
        "tokenizer_fingerprint": facts.tokenizer_fingerprint,
        "max_text_tokens": facts.max_text_tokens,
        "max_metadata_bytes": facts.max_metadata_bytes,
    }


def _decision_from_document(value: JsonValue, case_id: str) -> HKEXRenderingDecision:
    root = _object(value)
    _exact_keys(root, _DECISION_FIELDS)
    _constant(root["schema_id"], "asklegal.hk-regulatory.rendering-decision-result")
    _constant(root["schema_version"], HKEX_RENDERING_DECISION_CONTRACT_VERSION)
    _constant(root["rule_id"], HKEX_RENDERING_DECISION_RULE_ID)
    _constant(root["case_id"], case_id)
    for key in (
        "search_record_authorized",
        "embedding_authorized",
        "release_authorized",
        "serving_authorized",
    ):
        _false(root[key])
    _constant(root["external_effects"], "NONE")
    return HKEXRenderingDecision(
        _enum(root["outcome"], HKEXRenderingOutcome),
        _enum(root["reason"], HKEXRenderingReason),
        _nullable_text(root["canonical_text"]),
        _nullable_text(root["authority_note"]),
        _nullable_text(root["embedding_input"]),
        _nullable_integer(root["text_tokens"]),
        _nullable_integer(root["metadata_bytes"]),
        _nullable_integer(root["text_limit"]),
        _nullable_integer(root["metadata_limit"]),
        _nullable_boolean(root["fits"]),
        _strings(root["omitted_element_ids"], empty=True),
        _strings(root["rejected_element_ids"], empty=True),
        _strings(root["quarantined_element_ids"], empty=True),
        _enum(root["identity_consequence"], HKEXRenderingIdentityConsequence),
        _enum(root["vector_responsibility"], HKEXRenderingVectorResponsibility),
    )


def _bindings(value: JsonValue) -> tuple[HKEXRenderingContractBinding, ...]:
    results: list[HKEXRenderingContractBinding] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"contract_id", "version", "fingerprint"})
        results.append(
            HKEXRenderingContractBinding(
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
    bindings: tuple[HKEXRenderingContractBinding, ...], package_fingerprint: str
) -> None:
    seed = checked_json_value(
        {
            "contract_id": "asklegal.hk-regulatory.rendering-decision-case",
            "contract_version": HKEX_RENDERING_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_RENDERING_DECISION_RULE_ID,
        }
    )
    expected = (
        ("asklegal.hk-regulatory.conformance-universe", "1.0.0", package_fingerprint),
        ("asklegal.hk-regulatory.rendering-decision-case", "1.0.0", fingerprint(seed)),
    )
    if tuple((item.contract_id, item.version, item.fingerprint) for item in bindings) != expected:
        _fail()


def _pairs(value: JsonValue, case_id: str) -> tuple[HKEXRenderingPairMembership, ...]:
    results: list[HKEXRenderingPairMembership] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"pair_id", "role"})
        pair_id = _pattern(root["pair_id"], r"HKREG-PAIR-0(3[2-7]|57)")
        role = _text(root["role"])
        if role not in {"POSITIVE", "NEAR_MISS"}:
            _fail()
        results.append(HKEXRenderingPairMembership(pair_id, role))
    if tuple((item.pair_id, item.role) for item in results) != _EXPECTED_PAIRS.get(case_id, ()):
        _fail(HKEXRenderingErrorCode.IDENTITY)
    return tuple(results)


def _packet(value: JsonValue, facts: HKEXRenderingFacts) -> HKEXRenderingEvidencePacket:
    root = _object(value)
    _exact_keys(root, {"slot_id", "state", "path", "role", "media_type", "content_fingerprint"})
    packet = HKEXRenderingEvidencePacket(
        _text(root["slot_id"]),
        _text(root["state"]),
        _text(root["path"]),
        _text(root["role"]),
        _text(root["media_type"]),
        _fingerprint(root["content_fingerprint"]),
    )
    if (
        packet.slot_id != "rendering-evidence"
        or packet.state != "AVAILABLE"
        or packet.role != "ORDINARY"
        or packet.media_type != "application/json"
    ):
        _fail()
    if packet.content_fingerprint != fingerprint(checked_json_value(_facts_document(facts))):
        _fail(HKEXRenderingErrorCode.FINGERPRINT)
    return packet


def _checked(value: object) -> JsonValue:
    try:
        return checked_json_value(value)
    except ContractViolation as error:
        raise HKEXRenderingError(HKEXRenderingErrorCode.CONTRACT) from error


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


def _nullable_integer(value: JsonValue) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        _fail()
    return value


def _positive_integer(value: JsonValue) -> int:
    if type(value) is not int or value <= 0:
        _fail()
    return value


def _nullable_boolean(value: JsonValue) -> bool | None:
    return None if value is None else _boolean(value)


def _pattern(value: JsonValue, pattern: str) -> str:
    result = _text(value)
    if fullmatch(pattern, result) is None:
        _fail(HKEXRenderingErrorCode.IDENTITY)
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
        raise HKEXRenderingError(HKEXRenderingErrorCode.CONTRACT) from error


def _fingerprint(value: JsonValue) -> str:
    result = _text(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        _fail(HKEXRenderingErrorCode.FINGERPRINT)
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


def _fail(code: HKEXRenderingErrorCode = HKEXRenderingErrorCode.CONTRACT) -> Never:
    raise HKEXRenderingError(code)
