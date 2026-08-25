"""ADR 0074/0075 HKEX record-boundary and dependency conformance cases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from typing import Never, TypeIs

from asklegal_contracts import ContractViolation, fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_regulatory_english import HKEXComponentClass, HKEXSourceContractState
from .hk_regulatory_inventory import HKEX_SCOPE_IDS

HKEX_BOUNDARY_DECISION_RULE_ID = "HKREG-BOUNDARY-DECISION-001"
HKEX_BOUNDARY_DECISION_CONTRACT_VERSION = "1.0.0"
HKEX_BOUNDARY_DECISION_CASE_COUNT = 30

_CASE_PATTERN = r"HKREG-DEC-BND-(0[0-2][0-9]|030)"
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_CONTRACT_BINDING_COUNT = 2
_EXPECTED_PAIRS: dict[str, tuple[tuple[str, str], ...]] = {
    "HKREG-DEC-BND-002": (("HKREG-PAIR-025", "POSITIVE"),),
    "HKREG-DEC-BND-003": (("HKREG-PAIR-025", "NEAR_MISS"),),
    "HKREG-DEC-BND-005": (("HKREG-PAIR-026", "POSITIVE"),),
    "HKREG-DEC-BND-006": (("HKREG-PAIR-026", "NEAR_MISS"),),
    "HKREG-DEC-BND-008": (("HKREG-PAIR-027", "POSITIVE"),),
    "HKREG-DEC-BND-009": (("HKREG-PAIR-027", "NEAR_MISS"),),
    "HKREG-DEC-BND-011": (("HKREG-PAIR-028", "POSITIVE"),),
    "HKREG-DEC-BND-012": (("HKREG-PAIR-028", "NEAR_MISS"),),
    "HKREG-DEC-BND-018": (("HKREG-PAIR-029", "POSITIVE"),),
    "HKREG-DEC-BND-019": (("HKREG-PAIR-029", "NEAR_MISS"),),
    "HKREG-DEC-BND-021": (("HKREG-PAIR-030", "POSITIVE"),),
    "HKREG-DEC-BND-022": (("HKREG-PAIR-030", "NEAR_MISS"),),
    "HKREG-DEC-BND-027": (("HKREG-PAIR-031", "POSITIVE"),),
    "HKREG-DEC-BND-028": (("HKREG-PAIR-031", "NEAR_MISS"),),
}


class HKEXBoundaryDecisionErrorCode(StrEnum):
    """Closed malformed boundary-case envelope failures."""

    CONTRACT = "HKREG_BOUNDARY_DECISION_CONTRACT_INVALID"
    IDENTITY = "HKREG_BOUNDARY_DECISION_IDENTITY_INVALID"
    FINGERPRINT = "HKREG_BOUNDARY_DECISION_FINGERPRINT_INVALID"


class HKEXBoundaryDecisionError(ValueError):
    """One fail-closed boundary-case rejection."""

    code: HKEXBoundaryDecisionErrorCode

    def __init__(self, code: HKEXBoundaryDecisionErrorCode) -> None:
        """Create one stable fail-closed error."""
        self.code = code
        super().__init__(code.value)


class HKEXBoundaryAssertionScope(StrEnum):
    """Orthogonal boundary fact dimension, never a case identity switch."""

    NORMAL_UNIT = "NORMAL_UNIT"
    GOVERNING_DEPENDENCY = "GOVERNING_DEPENDENCY"
    DEFINITION = "DEFINITION"
    LEGAL_STRUCTURE = "LEGAL_STRUCTURE"
    CROSS_REFERENCE = "CROSS_REFERENCE"


class HKEXBoundaryOutcome(StrEnum):
    """Terminal effect-free processing outcome."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


class HKEXBoundaryReason(StrEnum):
    """Closed record-boundary and dependency reasons."""

    ONE_COMPLETE_NORMAL_UNIT = "ONE_COMPLETE_NORMAL_UNIT"
    INDEPENDENT_CHILDREN_SELECTED = "INDEPENDENT_CHILDREN_SELECTED"
    INSEPARABLE_GROUP_PRESERVED = "INSEPARABLE_GROUP_PRESERVED"
    REQUIRED_DEPENDENCIES_PRESERVED = "REQUIRED_DEPENDENCIES_PRESERVED"
    UNSAFE_CHILD_BOUNDARY_REJECTED = "UNSAFE_CHILD_BOUNDARY_REJECTED"
    NOTE_OWNER_PRESERVED = "NOTE_OWNER_PRESERVED"
    NOTE_OWNERSHIP_REJECTED = "NOTE_OWNERSHIP_REJECTED"
    TERM_DEFINITIONS_SELECTED = "TERM_DEFINITIONS_SELECTED"
    GLOBAL_DEFINITION_SELECTED = "GLOBAL_DEFINITION_SELECTED"
    GLOBAL_DEFINITION_DUPLICATION_REJECTED = "GLOBAL_DEFINITION_DUPLICATION_REJECTED"
    PRESENTATION_IDENTITY_REJECTED = "PRESENTATION_IDENTITY_REJECTED"
    SOURCE_STRUCTURE_REVIEW_REQUIRED = "SOURCE_STRUCTURE_REVIEW_REQUIRED"
    BACKGROUND_EXCLUDED = "BACKGROUND_EXCLUDED"
    DEPENDENCY_OWNER_LINKED = "DEPENDENCY_OWNER_LINKED"
    CROSS_REFERENCE_PRESERVED = "CROSS_REFERENCE_PRESERVED"
    RECURSIVE_TARGET_COPY_REJECTED = "RECURSIVE_TARGET_COPY_REJECTED"
    REFERENCE_CHAIN_PRESERVED = "REFERENCE_CHAIN_PRESERVED"
    TARGET_RESOLUTION_REQUIRED = "TARGET_RESOLUTION_REQUIRED"
    CROSS_BOARD_REFERENCE_PRESERVED = "CROSS_BOARD_REFERENCE_PRESERVED"
    RELATIONSHIP_REVISION_ONLY = "RELATIONSHIP_REVISION_ONLY"
    COMPLETE_UNIT_OVER_LIMIT = "COMPLETE_UNIT_OVER_LIMIT"
    UNRELATED_PACKING_REJECTED = "UNRELATED_PACKING_REJECTED"


class HKEXRecordUnitKind(StrEnum):
    """Exact normal responsibility kind selected before rendering."""

    NORMAL = "NORMAL"
    INSEPARABLE_GROUP = "INSEPARABLE_GROUP"
    DEFINITION = "DEFINITION"
    APPENDIX = "APPENDIX"
    PRACTICE_NOTE = "PRACTICE_NOTE"
    PARENT_FALLBACK = "PARENT_FALLBACK"


class HKEXDefinitionScope(StrEnum):
    """Definition ownership relevant to normal-unit selection."""

    NONE = "NONE"
    TERM_COLLECTION = "TERM_COLLECTION"
    GLOBAL = "GLOBAL"
    LOCAL = "LOCAL"


class HKEXLegalLocationBasis(StrEnum):
    """Whether one proposed location is legal structure or presentation."""

    PROVED_LEGAL_STRUCTURE = "PROVED_LEGAL_STRUCTURE"
    PRESENTATION_ONLY = "PRESENTATION_ONLY"


class HKEXReferenceResolution(StrEnum):
    """Exact target-resolution state preserved outside target text."""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class HKEXBoundaryContractBinding:
    """One exact contract bound into a permanent boundary case."""

    contract_id: str
    version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXBoundaryEvidencePacket:
    """One embedded proposal-safe synthetic fact packet."""

    slot_id: str
    state: str
    path: str
    role: str
    media_type: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXBoundaryPairMembership:
    """One case's exact permanent high-risk pair role."""

    pair_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKEXDependencyOwner:
    """One repeated dependency's exact primary owner and fingerprint."""

    source_unit_id: str
    owner_record_unit_id: str
    content_fingerprint: str

    def document(self) -> dict[str, object]:
        """Return the exact JSON-compatible dependency owner."""
        return {
            "source_unit_id": self.source_unit_id,
            "owner_record_unit_id": self.owner_record_unit_id,
            "content_fingerprint": self.content_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HKEXBoundaryReferenceFact:
    """One source-supported referring relationship without target text."""

    referring_unit_id: str
    referring_words: str
    referring_scope_id: str
    target_locator: str
    target_heading: str | None
    target_scope_id: str
    target_resolved: bool
    target_text_copied: bool
    target_content_changed: bool
    referring_payload_changed: bool


@dataclass(frozen=True, slots=True)
class HKEXBoundaryFacts:
    """Orthogonal source structure, dependency, definition, and reference facts."""

    component_class: HKEXComponentClass
    source_contract_state: HKEXSourceContractState
    parent_unit_id: str
    child_unit_ids: tuple[str, ...]
    independent_child_ids: tuple[str, ...]
    selected_primary_unit_ids: tuple[str, ...]
    inseparable_logic: bool
    required_dependency_ids: tuple[str, ...]
    proposed_dependency_ids: tuple[str, ...]
    background_unit_ids: tuple[str, ...]
    qualification_unit_ids: tuple[str, ...]
    note_owner_unit_id: str | None
    proposed_note_owner_unit_id: str | None
    definition_scope: HKEXDefinitionScope
    definition_term_unit_ids: tuple[str, ...]
    global_scope_unit_id: str | None
    duplicate_global_definition: bool
    legal_location_basis: HKEXLegalLocationBasis
    dependency_owners: tuple[HKEXDependencyOwner, ...]
    references: tuple[HKEXBoundaryReferenceFact, ...]
    complete_unit_fits_hard_limits: bool
    unrelated_unit_packed: bool


@dataclass(frozen=True, slots=True)
class HKEXRecordResponsibilityDecision:
    """One complete primary unit and its exact minimum dependency closure."""

    record_unit_id: str
    kind: HKEXRecordUnitKind
    primary_source_unit_ids: tuple[str, ...]
    dependency_source_unit_ids: tuple[str, ...]

    def document(self) -> dict[str, object]:
        """Return the exact JSON-compatible responsibility."""
        return {
            "record_unit_id": self.record_unit_id,
            "kind": self.kind.value,
            "primary_source_unit_ids": list(self.primary_source_unit_ids),
            "dependency_source_unit_ids": list(self.dependency_source_unit_ids),
        }


@dataclass(frozen=True, slots=True)
class HKEXReferenceDecision:
    """One preserved relationship with no recursively copied target text."""

    referring_unit_id: str
    referring_words: str
    referring_scope_id: str
    target_locator: str
    target_heading: str | None
    target_scope_id: str
    resolution: HKEXReferenceResolution
    target_text_included: bool

    def document(self) -> dict[str, object]:
        """Return the exact JSON-compatible relationship."""
        return {
            "referring_unit_id": self.referring_unit_id,
            "referring_words": self.referring_words,
            "referring_scope_id": self.referring_scope_id,
            "target_locator": self.target_locator,
            "target_heading": self.target_heading,
            "target_scope_id": self.target_scope_id,
            "resolution": self.resolution.value,
            "target_text_included": self.target_text_included,
        }


@dataclass(frozen=True, slots=True)
class HKEXBoundaryDecision:
    """One complete boundary result without Search Record authority."""

    outcome: HKEXBoundaryOutcome
    reason: HKEXBoundaryReason
    responsibilities: tuple[HKEXRecordResponsibilityDecision, ...]
    dependency_owners: tuple[HKEXDependencyOwner, ...]
    references: tuple[HKEXReferenceDecision, ...]
    excluded_background_unit_ids: tuple[str, ...]
    quarantined_unit_ids: tuple[str, ...]
    rejected_candidate: bool
    source_contract_review_required: bool
    quarantined_branch: bool
    presentation_identity_rejected: bool
    relationship_revision_only: bool
    referring_payload_change_required: bool

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return one exact result with every external authority denied."""
        _text(case_id)
        return {
            "schema_id": "asklegal.hk-regulatory.boundary-decision-result",
            "schema_version": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_BOUNDARY_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "responsibilities": [item.document() for item in self.responsibilities],
            "dependency_owners": [item.document() for item in self.dependency_owners],
            "references": [item.document() for item in self.references],
            "excluded_background_unit_ids": list(self.excluded_background_unit_ids),
            "quarantined_unit_ids": list(self.quarantined_unit_ids),
            "rejected_candidate": self.rejected_candidate,
            "source_contract_review_required": self.source_contract_review_required,
            "quarantined_branch": self.quarantined_branch,
            "presentation_identity_rejected": self.presentation_identity_rejected,
            "relationship_revision_only": self.relationship_revision_only,
            "referring_payload_change_required": self.referring_payload_change_required,
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "external_effects": "NONE",
        }


@dataclass(frozen=True, slots=True)
class HKEXBoundaryDecisionCase:
    """One strict evidence-to-decision conformance envelope."""

    case_id: str
    primary_coverage_cell_id: str
    pair_memberships: tuple[HKEXBoundaryPairMembership, ...]
    assertion_scope: HKEXBoundaryAssertionScope
    contract_bindings: tuple[HKEXBoundaryContractBinding, ...]
    evidence_packet: HKEXBoundaryEvidencePacket
    package_fingerprint: str
    title: str
    purpose: str
    expected_decision: HKEXBoundaryDecision
    facts: HKEXBoundaryFacts


@dataclass(frozen=True, slots=True)
class HKEXBoundaryDecisionReport:
    """Complete expected-versus-observed boundary decision report."""

    case_id: str
    assertion_scope: HKEXBoundaryAssertionScope
    observed_decision: HKEXBoundaryDecision
    expected_decision: HKEXBoundaryDecision
    conformance_status: str

    def document(self) -> dict[str, object]:
        """Return the exact effect-free conformance report."""
        return {
            "schema_id": "asklegal.hk-regulatory.boundary-decision-report",
            "schema_version": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_BOUNDARY_DECISION_RULE_ID,
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
    pairs: tuple[HKEXBoundaryPairMembership, ...]
    scope: HKEXBoundaryAssertionScope
    bindings: tuple[HKEXBoundaryContractBinding, ...]
    package_fingerprint: str


@dataclass(frozen=True, slots=True)
class _DecisionDetails:
    responsibilities: tuple[HKEXRecordResponsibilityDecision, ...] = ()
    dependency_owners: tuple[HKEXDependencyOwner, ...] = ()
    references: tuple[HKEXReferenceDecision, ...] = ()
    excluded_background: tuple[str, ...] = ()
    quarantined_units: tuple[str, ...] = ()
    rejected: bool = False
    contract_review: bool = False
    quarantined: bool = False
    presentation_rejected: bool = False
    relationship_only: bool = False
    payload_change: bool = False


def hkex_boundary_decision_case_from_document(document: object) -> HKEXBoundaryDecisionCase:
    """Strictly decode and fingerprint one permanent boundary case."""
    root = _object(_checked(document))
    _exact_keys(root, _CASE_FIELDS)
    header = _case_header(root)
    _validate_declarations(root, header.bindings)
    facts = _facts(root["facts"])
    packet = _packet(root["evidence_packet"], facts)
    expected = _decision_from_document(root["expected_decision"], header.case_id)
    _validate_case_fingerprint(root)
    return HKEXBoundaryDecisionCase(
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


def decide_hkex_boundary_case(case: HKEXBoundaryDecisionCase) -> HKEXBoundaryDecision:
    """Derive the complete boundary result from facts and scope, never case ID."""
    if type(case) is not HKEXBoundaryDecisionCase:
        _fail()
    evaluators = {
        HKEXBoundaryAssertionScope.NORMAL_UNIT: _decide_normal_unit,
        HKEXBoundaryAssertionScope.GOVERNING_DEPENDENCY: _decide_dependency,
        HKEXBoundaryAssertionScope.DEFINITION: _decide_definition,
        HKEXBoundaryAssertionScope.LEGAL_STRUCTURE: _decide_legal_structure,
        HKEXBoundaryAssertionScope.CROSS_REFERENCE: _decide_cross_reference,
    }
    return evaluators[case.assertion_scope](case.facts)


def run_hkex_boundary_case(case: HKEXBoundaryDecisionCase) -> HKEXBoundaryDecisionReport:
    """Compare a complete fact-derived result with independently frozen truth."""
    observed = decide_hkex_boundary_case(case)
    return HKEXBoundaryDecisionReport(
        case.case_id,
        case.assertion_scope,
        observed,
        case.expected_decision,
        "PASS" if observed == case.expected_decision else "FAIL",
    )


def _decision(
    outcome: HKEXBoundaryOutcome,
    reason: HKEXBoundaryReason,
    details: _DecisionDetails | None = None,
) -> HKEXBoundaryDecision:
    resolved = _DecisionDetails() if details is None else details
    return HKEXBoundaryDecision(
        outcome,
        reason,
        resolved.responsibilities,
        resolved.dependency_owners,
        resolved.references,
        resolved.excluded_background,
        resolved.quarantined_units,
        resolved.rejected,
        resolved.contract_review,
        resolved.quarantined,
        resolved.presentation_rejected,
        resolved.relationship_only,
        resolved.payload_change,
    )


def _responsibility(
    unit_id: str,
    kind: HKEXRecordUnitKind,
    primary: tuple[str, ...],
    dependencies: tuple[str, ...] = (),
) -> HKEXRecordResponsibilityDecision:
    return HKEXRecordResponsibilityDecision(unit_id, kind, primary, dependencies)


def _decide_normal_unit(facts: HKEXBoundaryFacts) -> HKEXBoundaryDecision:
    if facts.source_contract_state is HKEXSourceContractState.UNKNOWN:
        return _decision(
            HKEXBoundaryOutcome.QUARANTINE,
            HKEXBoundaryReason.SOURCE_STRUCTURE_REVIEW_REQUIRED,
            _DecisionDetails(
                contract_review=True,
                quarantined=True,
                quarantined_units=(facts.parent_unit_id,),
            ),
        )
    if facts.unrelated_unit_packed:
        responsibilities = tuple(
            _responsibility(f"record-{unit}", HKEXRecordUnitKind.NORMAL, (unit,))
            for unit in facts.selected_primary_unit_ids
        )
        return _decision(
            HKEXBoundaryOutcome.BLOCK,
            HKEXBoundaryReason.UNRELATED_PACKING_REJECTED,
            _DecisionDetails(responsibilities=responsibilities, rejected=True),
        )
    if not facts.complete_unit_fits_hard_limits:
        return _decision(
            HKEXBoundaryOutcome.QUARANTINE,
            HKEXBoundaryReason.COMPLETE_UNIT_OVER_LIMIT,
            _DecisionDetails(
                quarantined=True,
                quarantined_units=(facts.parent_unit_id,),
            ),
        )
    if facts.independent_child_ids:
        if set(facts.independent_child_ids) != set(facts.selected_primary_unit_ids):
            _fail()
        responsibilities = tuple(
            _responsibility(f"record-{unit}", _normal_kind(facts), (unit,))
            for unit in facts.independent_child_ids
        )
        return _decision(
            HKEXBoundaryOutcome.PASS,
            HKEXBoundaryReason.INDEPENDENT_CHILDREN_SELECTED,
            _DecisionDetails(responsibilities=responsibilities),
        )
    if facts.inseparable_logic or facts.child_unit_ids:
        if set(facts.selected_primary_unit_ids) != {
            facts.parent_unit_id,
            *facts.child_unit_ids,
        }:
            _fail()
        responsibility = _responsibility(
            f"record-{facts.parent_unit_id}",
            HKEXRecordUnitKind.INSEPARABLE_GROUP,
            facts.selected_primary_unit_ids,
        )
        return _decision(
            HKEXBoundaryOutcome.PASS,
            HKEXBoundaryReason.INSEPARABLE_GROUP_PRESERVED,
            _DecisionDetails(responsibilities=(responsibility,)),
        )
    if facts.selected_primary_unit_ids != (facts.parent_unit_id,):
        _fail()
    responsibility = _responsibility(
        f"record-{facts.parent_unit_id}",
        _normal_kind(facts),
        facts.selected_primary_unit_ids,
    )
    return _decision(
        HKEXBoundaryOutcome.PASS,
        HKEXBoundaryReason.ONE_COMPLETE_NORMAL_UNIT,
        _DecisionDetails(responsibilities=(responsibility,)),
    )


def _normal_kind(facts: HKEXBoundaryFacts) -> HKEXRecordUnitKind:
    if facts.component_class is HKEXComponentClass.APPENDIX:
        return HKEXRecordUnitKind.APPENDIX
    if facts.component_class is HKEXComponentClass.PRACTICE_NOTE:
        return HKEXRecordUnitKind.PRACTICE_NOTE
    return HKEXRecordUnitKind.NORMAL


def _decide_dependency(facts: HKEXBoundaryFacts) -> HKEXBoundaryDecision:
    required = set(facts.required_dependency_ids)
    proposed = set(facts.proposed_dependency_ids)
    if proposed.intersection(facts.background_unit_ids):
        _fail()
    if facts.note_owner_unit_id is not None:
        return _decide_note(facts)
    if required.difference(proposed):
        responsibility = _responsibility(
            f"record-{facts.parent_unit_id}",
            HKEXRecordUnitKind.PARENT_FALLBACK,
            (facts.parent_unit_id, *facts.child_unit_ids),
        )
        return _decision(
            HKEXBoundaryOutcome.BLOCK,
            HKEXBoundaryReason.UNSAFE_CHILD_BOUNDARY_REJECTED,
            _DecisionDetails(responsibilities=(responsibility,), rejected=True),
        )
    if facts.background_unit_ids and not required:
        responsibility = _responsibility(
            f"record-{facts.selected_primary_unit_ids[0]}",
            HKEXRecordUnitKind.NORMAL,
            facts.selected_primary_unit_ids,
        )
        return _decision(
            HKEXBoundaryOutcome.PASS,
            HKEXBoundaryReason.BACKGROUND_EXCLUDED,
            _DecisionDetails(
                responsibilities=(responsibility,),
                excluded_background=facts.background_unit_ids,
            ),
        )
    responsibility = _responsibility(
        f"record-{facts.selected_primary_unit_ids[0]}",
        HKEXRecordUnitKind.NORMAL,
        facts.selected_primary_unit_ids,
        facts.proposed_dependency_ids,
    )
    if facts.dependency_owners:
        return _decision(
            HKEXBoundaryOutcome.PASS,
            HKEXBoundaryReason.DEPENDENCY_OWNER_LINKED,
            _DecisionDetails(
                responsibilities=(responsibility,),
                dependency_owners=facts.dependency_owners,
            ),
        )
    return _decision(
        HKEXBoundaryOutcome.PASS,
        HKEXBoundaryReason.REQUIRED_DEPENDENCIES_PRESERVED,
        _DecisionDetails(responsibilities=(responsibility,)),
    )


def _decide_note(facts: HKEXBoundaryFacts) -> HKEXBoundaryDecision:
    owner = facts.note_owner_unit_id
    if owner is None:
        _fail()
    if facts.proposed_note_owner_unit_id != owner:
        return _decision(
            HKEXBoundaryOutcome.BLOCK,
            HKEXBoundaryReason.NOTE_OWNERSHIP_REJECTED,
            _DecisionDetails(rejected=True),
        )
    primary = tuple(dict.fromkeys((*facts.selected_primary_unit_ids, owner)))
    responsibility = _responsibility(f"record-{owner}", HKEXRecordUnitKind.NORMAL, primary)
    return _decision(
        HKEXBoundaryOutcome.PASS,
        HKEXBoundaryReason.NOTE_OWNER_PRESERVED,
        _DecisionDetails(responsibilities=(responsibility,)),
    )


def _decide_definition(facts: HKEXBoundaryFacts) -> HKEXBoundaryDecision:
    if facts.definition_scope is HKEXDefinitionScope.TERM_COLLECTION:
        if not facts.definition_term_unit_ids or facts.global_scope_unit_id is None:
            _fail()
        responsibilities = tuple(
            _responsibility(
                f"record-{term}",
                HKEXRecordUnitKind.DEFINITION,
                (term,),
                (facts.global_scope_unit_id,),
            )
            for term in facts.definition_term_unit_ids
        )
        return _decision(
            HKEXBoundaryOutcome.PASS,
            HKEXBoundaryReason.TERM_DEFINITIONS_SELECTED,
            _DecisionDetails(responsibilities=responsibilities),
        )
    if facts.definition_scope is HKEXDefinitionScope.GLOBAL:
        if facts.duplicate_global_definition:
            return _decision(
                HKEXBoundaryOutcome.BLOCK,
                HKEXBoundaryReason.GLOBAL_DEFINITION_DUPLICATION_REJECTED,
                _DecisionDetails(rejected=True),
            )
        responsibility = _responsibility(
            f"record-{facts.parent_unit_id}",
            HKEXRecordUnitKind.DEFINITION,
            (facts.parent_unit_id,),
        )
        return _decision(
            HKEXBoundaryOutcome.PASS,
            HKEXBoundaryReason.GLOBAL_DEFINITION_SELECTED,
            _DecisionDetails(responsibilities=(responsibility,)),
        )
    if facts.definition_scope is HKEXDefinitionScope.LOCAL:
        return _decide_dependency(facts)
    return _fail()


def _decide_legal_structure(facts: HKEXBoundaryFacts) -> HKEXBoundaryDecision:
    if facts.source_contract_state is HKEXSourceContractState.UNKNOWN:
        return _decision(
            HKEXBoundaryOutcome.QUARANTINE,
            HKEXBoundaryReason.SOURCE_STRUCTURE_REVIEW_REQUIRED,
            _DecisionDetails(
                contract_review=True,
                quarantined=True,
                quarantined_units=(facts.parent_unit_id,),
            ),
        )
    if facts.legal_location_basis is HKEXLegalLocationBasis.PRESENTATION_ONLY:
        return _decision(
            HKEXBoundaryOutcome.BLOCK,
            HKEXBoundaryReason.PRESENTATION_IDENTITY_REJECTED,
            _DecisionDetails(rejected=True, presentation_rejected=True),
        )
    return _fail()


def _decide_cross_reference(facts: HKEXBoundaryFacts) -> HKEXBoundaryDecision:
    if not facts.references:
        _fail()
    references = tuple(_reference(item) for item in facts.references)
    if any(item.target_text_copied for item in facts.references):
        return _decision(
            HKEXBoundaryOutcome.BLOCK,
            HKEXBoundaryReason.RECURSIVE_TARGET_COPY_REJECTED,
            _DecisionDetails(references=references, rejected=True),
        )
    if any(not item.target_resolved for item in facts.references):
        return _decision(
            HKEXBoundaryOutcome.QUARANTINE,
            HKEXBoundaryReason.TARGET_RESOLUTION_REQUIRED,
            _DecisionDetails(
                references=references,
                contract_review=True,
                quarantined=True,
                quarantined_units=tuple(
                    dict.fromkeys(item.referring_unit_id for item in facts.references)
                ),
            ),
        )
    if any(item.target_scope_id != item.referring_scope_id for item in facts.references):
        reason = HKEXBoundaryReason.CROSS_BOARD_REFERENCE_PRESERVED
    elif len(facts.references) > 1:
        reason = HKEXBoundaryReason.REFERENCE_CHAIN_PRESERVED
    elif any(
        item.target_content_changed and not item.referring_payload_changed
        for item in facts.references
    ):
        return _decision(
            HKEXBoundaryOutcome.PASS,
            HKEXBoundaryReason.RELATIONSHIP_REVISION_ONLY,
            _DecisionDetails(references=references, relationship_only=True),
        )
    else:
        reason = HKEXBoundaryReason.CROSS_REFERENCE_PRESERVED
    return _decision(
        HKEXBoundaryOutcome.PASS,
        reason,
        _DecisionDetails(references=references),
    )


def _reference(fact: HKEXBoundaryReferenceFact) -> HKEXReferenceDecision:
    return HKEXReferenceDecision(
        referring_unit_id=fact.referring_unit_id,
        referring_words=fact.referring_words,
        referring_scope_id=fact.referring_scope_id,
        target_locator=fact.target_locator,
        target_heading=fact.target_heading,
        target_scope_id=fact.target_scope_id,
        resolution=(
            HKEXReferenceResolution.RESOLVED
            if fact.target_resolved
            else HKEXReferenceResolution.UNRESOLVED
        ),
        target_text_included=False,
    )


_FACT_FIELDS = {
    "component_class",
    "source_contract_state",
    "parent_unit_id",
    "child_unit_ids",
    "independent_child_ids",
    "selected_primary_unit_ids",
    "inseparable_logic",
    "required_dependency_ids",
    "proposed_dependency_ids",
    "background_unit_ids",
    "qualification_unit_ids",
    "note_owner_unit_id",
    "proposed_note_owner_unit_id",
    "definition_scope",
    "definition_term_unit_ids",
    "global_scope_unit_id",
    "duplicate_global_definition",
    "legal_location_basis",
    "dependency_owners",
    "references",
    "complete_unit_fits_hard_limits",
    "unrelated_unit_packed",
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


def _case_header(root: dict[str, JsonValue]) -> _CaseHeader:
    _constant(root["schema_id"], "asklegal.hk-regulatory.boundary-decision-case")
    _constant(root["schema_version"], HKEX_BOUNDARY_DECISION_CONTRACT_VERSION)
    _constant(root["package_contract_version"], "1.0.0")
    case_id = _pattern(root["case_id"], _CASE_PATTERN)
    suffix = case_id.rsplit("-", maxsplit=1)[1]
    _constant(root["suite_layer"], "EVIDENCE_TO_DECISION")
    _constant(root["primary_checkpoint"], "RECORD_BOUNDARY")
    _true(root["frozen"])
    _constant(root["synthetic_evidence_class"], "SYNTHETIC_NO_REAL_AUTHORITY")
    _constant(root["synthetic_cutoff"], "2026-08-24T00:00:00Z")
    _constant(root["scope_id"], "HKEX_CROSS_BOARD")
    _constant(root["prior_state"], "SYNTHETIC_ACCEPTED_PREDECESSOR")
    primary = _strings(root["primary_coverage_cell_ids"])
    if primary != (f"HKREG-COV-DBND-{suffix}",):
        _fail(HKEXBoundaryDecisionErrorCode.IDENTITY)
    bindings = _bindings(root["contract_bindings"])
    package_fingerprint = _fingerprint(root["package_fingerprint"])
    _validate_bindings(bindings, package_fingerprint)
    return _CaseHeader(
        case_id,
        primary[0],
        _pairs(root["pair_memberships"], case_id),
        _enum(root["assertion_scope"], HKEXBoundaryAssertionScope),
        bindings,
        package_fingerprint,
    )


def _validate_declarations(
    root: dict[str, JsonValue], bindings: tuple[HKEXBoundaryContractBinding, ...]
) -> None:
    _sorted_strings(root["secondary_coverage_cell_ids"])
    if _strings(root["declared_input_inventory"]) != ("boundary-evidence",):
        _fail()
    if _strings(root["declared_reference_inventory"]) != tuple(
        item.contract_id for item in bindings
    ):
        _fail()
    if _strings(root["declared_expected_inventory"]) != ("BOUNDARY_DECISION_REPORT",):
        _fail()
    if _strings(root["required_result_dimensions"]) != (
        "CROSS_REFERENCE",
        "DEPENDENCY_CLOSURE",
        "LEGAL_LOCATION",
        "PROCESSING",
        "RECORD_RESPONSIBILITY",
        "SOURCE_STRUCTURE",
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
        _fail(HKEXBoundaryDecisionErrorCode.FINGERPRINT)


def _facts(value: JsonValue) -> HKEXBoundaryFacts:
    root = _object(value)
    _exact_keys(root, _FACT_FIELDS)
    result = HKEXBoundaryFacts(
        _enum(root["component_class"], HKEXComponentClass),
        _enum(root["source_contract_state"], HKEXSourceContractState),
        _text(root["parent_unit_id"]),
        _strings(root["child_unit_ids"], empty=True),
        _strings(root["independent_child_ids"], empty=True),
        _strings(root["selected_primary_unit_ids"], empty=True),
        _boolean(root["inseparable_logic"]),
        _strings(root["required_dependency_ids"], empty=True),
        _strings(root["proposed_dependency_ids"], empty=True),
        _strings(root["background_unit_ids"], empty=True),
        _strings(root["qualification_unit_ids"], empty=True),
        _nullable_text(root["note_owner_unit_id"]),
        _nullable_text(root["proposed_note_owner_unit_id"]),
        _enum(root["definition_scope"], HKEXDefinitionScope),
        _strings(root["definition_term_unit_ids"], empty=True),
        _nullable_text(root["global_scope_unit_id"]),
        _boolean(root["duplicate_global_definition"]),
        _enum(root["legal_location_basis"], HKEXLegalLocationBasis),
        tuple(_dependency_owner(item) for item in _array(root["dependency_owners"])),
        tuple(_reference_fact(item) for item in _array(root["references"])),
        _boolean(root["complete_unit_fits_hard_limits"]),
        _boolean(root["unrelated_unit_packed"]),
    )
    _validate_facts(result)
    return result


def _validate_facts(facts: HKEXBoundaryFacts) -> None:
    children = set(facts.child_unit_ids)
    if not set(facts.independent_child_ids).issubset(children):
        _fail()
    if set(facts.qualification_unit_ids).difference(
        {*facts.required_dependency_ids, *facts.selected_primary_unit_ids}
    ):
        _fail()
    if len({item.source_unit_id for item in facts.dependency_owners}) != len(
        facts.dependency_owners
    ):
        _fail()
    if len(
        {
            (item.referring_unit_id, item.target_scope_id, item.target_locator)
            for item in facts.references
        }
    ) != len(facts.references):
        _fail()


def _dependency_owner(value: JsonValue) -> HKEXDependencyOwner:
    root = _object(value)
    _exact_keys(root, {"source_unit_id", "owner_record_unit_id", "content_fingerprint"})
    return HKEXDependencyOwner(
        _text(root["source_unit_id"]),
        _text(root["owner_record_unit_id"]),
        _fingerprint(root["content_fingerprint"]),
    )


def _reference_fact(value: JsonValue) -> HKEXBoundaryReferenceFact:
    root = _object(value)
    _exact_keys(
        root,
        {
            "referring_unit_id",
            "referring_words",
            "referring_scope_id",
            "target_locator",
            "target_heading",
            "target_scope_id",
            "target_resolved",
            "target_text_copied",
            "target_content_changed",
            "referring_payload_changed",
        },
    )
    referring_scope_id = _text(root["referring_scope_id"])
    target_scope_id = _text(root["target_scope_id"])
    if referring_scope_id not in HKEX_SCOPE_IDS or target_scope_id not in HKEX_SCOPE_IDS:
        _fail()
    return HKEXBoundaryReferenceFact(
        _text(root["referring_unit_id"]),
        _text(root["referring_words"]),
        referring_scope_id,
        _text(root["target_locator"]),
        _nullable_text(root["target_heading"]),
        target_scope_id,
        _boolean(root["target_resolved"]),
        _boolean(root["target_text_copied"]),
        _boolean(root["target_content_changed"]),
        _boolean(root["referring_payload_changed"]),
    )


def _decision_from_document(value: JsonValue, case_id: str) -> HKEXBoundaryDecision:
    root = _object(value)
    _exact_keys(root, _DECISION_FIELDS)
    _constant(root["schema_id"], "asklegal.hk-regulatory.boundary-decision-result")
    _constant(root["schema_version"], HKEX_BOUNDARY_DECISION_CONTRACT_VERSION)
    _constant(root["rule_id"], HKEX_BOUNDARY_DECISION_RULE_ID)
    _constant(root["case_id"], case_id)
    for key in (
        "search_record_authorized",
        "embedding_authorized",
        "release_authorized",
        "serving_authorized",
    ):
        _false(root[key])
    _constant(root["external_effects"], "NONE")
    return HKEXBoundaryDecision(
        _enum(root["outcome"], HKEXBoundaryOutcome),
        _enum(root["reason"], HKEXBoundaryReason),
        tuple(_responsibility_from_document(item) for item in _array(root["responsibilities"])),
        tuple(_dependency_owner(item) for item in _array(root["dependency_owners"])),
        tuple(_reference_from_document(item) for item in _array(root["references"])),
        _strings(root["excluded_background_unit_ids"], empty=True),
        _strings(root["quarantined_unit_ids"], empty=True),
        _boolean(root["rejected_candidate"]),
        _boolean(root["source_contract_review_required"]),
        _boolean(root["quarantined_branch"]),
        _boolean(root["presentation_identity_rejected"]),
        _boolean(root["relationship_revision_only"]),
        _boolean(root["referring_payload_change_required"]),
    )


_DECISION_FIELDS = {
    "schema_id",
    "schema_version",
    "rule_id",
    "case_id",
    "outcome",
    "reason",
    "responsibilities",
    "dependency_owners",
    "references",
    "excluded_background_unit_ids",
    "quarantined_unit_ids",
    "rejected_candidate",
    "source_contract_review_required",
    "quarantined_branch",
    "presentation_identity_rejected",
    "relationship_revision_only",
    "referring_payload_change_required",
    "search_record_authorized",
    "embedding_authorized",
    "release_authorized",
    "serving_authorized",
    "external_effects",
}


def _responsibility_from_document(value: JsonValue) -> HKEXRecordResponsibilityDecision:
    root = _object(value)
    _exact_keys(
        root,
        {"record_unit_id", "kind", "primary_source_unit_ids", "dependency_source_unit_ids"},
    )
    return HKEXRecordResponsibilityDecision(
        _text(root["record_unit_id"]),
        _enum(root["kind"], HKEXRecordUnitKind),
        _strings(root["primary_source_unit_ids"]),
        _strings(root["dependency_source_unit_ids"], empty=True),
    )


def _reference_from_document(value: JsonValue) -> HKEXReferenceDecision:
    root = _object(value)
    _exact_keys(
        root,
        {
            "referring_unit_id",
            "referring_words",
            "referring_scope_id",
            "target_locator",
            "target_heading",
            "target_scope_id",
            "resolution",
            "target_text_included",
        },
    )
    referring_scope_id = _text(root["referring_scope_id"])
    target_scope_id = _text(root["target_scope_id"])
    if referring_scope_id not in HKEX_SCOPE_IDS or target_scope_id not in HKEX_SCOPE_IDS:
        _fail()
    return HKEXReferenceDecision(
        _text(root["referring_unit_id"]),
        _text(root["referring_words"]),
        referring_scope_id,
        _text(root["target_locator"]),
        _nullable_text(root["target_heading"]),
        target_scope_id,
        _enum(root["resolution"], HKEXReferenceResolution),
        _boolean(root["target_text_included"]),
    )


def _bindings(value: JsonValue) -> tuple[HKEXBoundaryContractBinding, ...]:
    results: list[HKEXBoundaryContractBinding] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"contract_id", "version", "fingerprint"})
        results.append(
            HKEXBoundaryContractBinding(
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
    bindings: tuple[HKEXBoundaryContractBinding, ...], package_fingerprint: str
) -> None:
    seed = checked_json_value(
        {
            "contract_id": "asklegal.hk-regulatory.boundary-decision-case",
            "contract_version": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_BOUNDARY_DECISION_RULE_ID,
        }
    )
    expected = (
        ("asklegal.hk-regulatory.conformance-universe", "1.0.0", package_fingerprint),
        ("asklegal.hk-regulatory.boundary-decision-case", "1.0.0", fingerprint(seed)),
    )
    if tuple((item.contract_id, item.version, item.fingerprint) for item in bindings) != expected:
        _fail()


def _pairs(value: JsonValue, case_id: str) -> tuple[HKEXBoundaryPairMembership, ...]:
    results: list[HKEXBoundaryPairMembership] = []
    for item in _array(value):
        root = _object(item)
        _exact_keys(root, {"pair_id", "role"})
        pair_id = _pattern(root["pair_id"], r"HKREG-PAIR-0(2[5-9]|3[01])")
        role = _text(root["role"])
        if role not in {"POSITIVE", "NEAR_MISS"}:
            _fail()
        results.append(HKEXBoundaryPairMembership(pair_id, role))
    if tuple((item.pair_id, item.role) for item in results) != _EXPECTED_PAIRS.get(case_id, ()):
        _fail(HKEXBoundaryDecisionErrorCode.IDENTITY)
    return tuple(results)


def _packet(value: JsonValue, facts: HKEXBoundaryFacts) -> HKEXBoundaryEvidencePacket:
    root = _object(value)
    _exact_keys(root, {"slot_id", "state", "path", "role", "media_type", "content_fingerprint"})
    packet = HKEXBoundaryEvidencePacket(
        _text(root["slot_id"]),
        _text(root["state"]),
        _text(root["path"]),
        _text(root["role"]),
        _text(root["media_type"]),
        _fingerprint(root["content_fingerprint"]),
    )
    if (
        packet.slot_id != "boundary-evidence"
        or packet.state != "AVAILABLE"
        or packet.role != "ORDINARY"
        or packet.media_type != "application/json"
    ):
        _fail()
    if packet.content_fingerprint != fingerprint(checked_json_value(_facts_document(facts))):
        _fail(HKEXBoundaryDecisionErrorCode.FINGERPRINT)
    return packet


def _facts_document(facts: HKEXBoundaryFacts) -> dict[str, object]:
    return {
        "component_class": facts.component_class.value,
        "source_contract_state": facts.source_contract_state.value,
        "parent_unit_id": facts.parent_unit_id,
        "child_unit_ids": list(facts.child_unit_ids),
        "independent_child_ids": list(facts.independent_child_ids),
        "selected_primary_unit_ids": list(facts.selected_primary_unit_ids),
        "inseparable_logic": facts.inseparable_logic,
        "required_dependency_ids": list(facts.required_dependency_ids),
        "proposed_dependency_ids": list(facts.proposed_dependency_ids),
        "background_unit_ids": list(facts.background_unit_ids),
        "qualification_unit_ids": list(facts.qualification_unit_ids),
        "note_owner_unit_id": facts.note_owner_unit_id,
        "proposed_note_owner_unit_id": facts.proposed_note_owner_unit_id,
        "definition_scope": facts.definition_scope.value,
        "definition_term_unit_ids": list(facts.definition_term_unit_ids),
        "global_scope_unit_id": facts.global_scope_unit_id,
        "duplicate_global_definition": facts.duplicate_global_definition,
        "legal_location_basis": facts.legal_location_basis.value,
        "dependency_owners": [item.document() for item in facts.dependency_owners],
        "references": [_reference_fact_document(item) for item in facts.references],
        "complete_unit_fits_hard_limits": facts.complete_unit_fits_hard_limits,
        "unrelated_unit_packed": facts.unrelated_unit_packed,
    }


def _reference_fact_document(fact: HKEXBoundaryReferenceFact) -> dict[str, object]:
    return {
        "referring_unit_id": fact.referring_unit_id,
        "referring_words": fact.referring_words,
        "referring_scope_id": fact.referring_scope_id,
        "target_locator": fact.target_locator,
        "target_heading": fact.target_heading,
        "target_scope_id": fact.target_scope_id,
        "target_resolved": fact.target_resolved,
        "target_text_copied": fact.target_text_copied,
        "target_content_changed": fact.target_content_changed,
        "referring_payload_changed": fact.referring_payload_changed,
    }


def _checked(value: object) -> JsonValue:
    try:
        return checked_json_value(value)
    except ContractViolation as error:
        raise HKEXBoundaryDecisionError(HKEXBoundaryDecisionErrorCode.CONTRACT) from error


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


def _pattern(value: JsonValue, pattern: str) -> str:
    result = _text(value)
    if fullmatch(pattern, result) is None:
        _fail(HKEXBoundaryDecisionErrorCode.IDENTITY)
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
        raise HKEXBoundaryDecisionError(HKEXBoundaryDecisionErrorCode.CONTRACT) from error


def _fingerprint(value: JsonValue) -> str:
    result = _text(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        _fail(HKEXBoundaryDecisionErrorCode.FINGERPRINT)
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


def _fail(
    code: HKEXBoundaryDecisionErrorCode = HKEXBoundaryDecisionErrorCode.CONTRACT,
) -> Never:
    raise HKEXBoundaryDecisionError(code)
