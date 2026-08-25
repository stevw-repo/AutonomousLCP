"""ADR 0074/0075 HKEX source-fact, membership, ownership, and language cases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch

from asklegal_contracts import ContractViolation, fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_regulatory_inventory import (
    HKEX_CONSOLIDATED_RULEBOOKS_SOURCE_ID,
    HKEX_FEES_RULES_SOURCE_ID,
    HKEX_GEM_SCOPE_ID,
    HKEX_MAIN_SCOPE_ID,
    HKEX_REGULATORY_FORMS_SOURCE_ID,
    HKEX_REGULATORY_SOURCE_IDS,
    HKEX_RULE_UPDATES_SOURCE_ID,
    HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
    HKEXMembership,
)

HKEX_SOURCE_DECISION_RULE_ID = "HKREG-SOURCE-DECISION-001"
HKEX_SOURCE_DECISION_CONTRACT_VERSION = "1.0.0"
HKEX_SOURCE_DECISION_CASE_COUNT = 62

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_CASE_PATTERN = r"HKREG-DEC-SRC-(0[0-5][0-9]|06[0-2])"
_MIN_CONTRACT_BINDINGS = 2
_BOARD_COUNT = 2
_SCOPE_IDS = (HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID)
_SOURCE_CASE_CONTRACT_FINGERPRINT = fingerprint(
    checked_json_value(
        {
            "contract_id": "asklegal.hk-regulatory.source-decision-case",
            "contract_version": HKEX_SOURCE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_SOURCE_DECISION_RULE_ID,
        }
    )
)

_EXPECTED_PAIR_MEMBERSHIPS = {
    "HKREG-DEC-SRC-001": ("HKREG-PAIR-001", "POSITIVE"),
    "HKREG-DEC-SRC-002": ("HKREG-PAIR-001", "NEAR_MISS"),
    "HKREG-DEC-SRC-003": ("HKREG-PAIR-002", "POSITIVE"),
    "HKREG-DEC-SRC-004": ("HKREG-PAIR-002", "NEAR_MISS"),
    "HKREG-DEC-SRC-005": ("HKREG-PAIR-003", "POSITIVE"),
    "HKREG-DEC-SRC-006": ("HKREG-PAIR-003", "NEAR_MISS"),
    "HKREG-DEC-SRC-007": ("HKREG-PAIR-004", "POSITIVE"),
    "HKREG-DEC-SRC-008": ("HKREG-PAIR-004", "NEAR_MISS"),
    "HKREG-DEC-SRC-009": ("HKREG-PAIR-005", "POSITIVE"),
    "HKREG-DEC-SRC-010": ("HKREG-PAIR-005", "NEAR_MISS"),
    "HKREG-DEC-SRC-011": ("HKREG-PAIR-006", "POSITIVE"),
    "HKREG-DEC-SRC-012": ("HKREG-PAIR-006", "NEAR_MISS"),
    "HKREG-DEC-SRC-015": ("HKREG-PAIR-007", "POSITIVE"),
    "HKREG-DEC-SRC-016": ("HKREG-PAIR-007", "NEAR_MISS"),
    "HKREG-DEC-SRC-018": ("HKREG-PAIR-008", "POSITIVE"),
    "HKREG-DEC-SRC-019": ("HKREG-PAIR-008", "NEAR_MISS"),
    "HKREG-DEC-SRC-020": ("HKREG-PAIR-009", "POSITIVE"),
    "HKREG-DEC-SRC-021": ("HKREG-PAIR-009", "NEAR_MISS"),
    "HKREG-DEC-SRC-027": ("HKREG-PAIR-010", "POSITIVE"),
    "HKREG-DEC-SRC-031": ("HKREG-PAIR-010", "NEAR_MISS"),
    "HKREG-DEC-SRC-028": ("HKREG-PAIR-011", "POSITIVE"),
    "HKREG-DEC-SRC-036": ("HKREG-PAIR-011", "NEAR_MISS"),
    "HKREG-DEC-SRC-044": ("HKREG-PAIR-012", "POSITIVE"),
    "HKREG-DEC-SRC-055": ("HKREG-PAIR-012", "NEAR_MISS"),
    "HKREG-DEC-SRC-046": ("HKREG-PAIR-013", "POSITIVE"),
    "HKREG-DEC-SRC-052": ("HKREG-PAIR-013", "NEAR_MISS"),
    "HKREG-DEC-SRC-056": ("HKREG-PAIR-014", "POSITIVE"),
    "HKREG-DEC-SRC-057": ("HKREG-PAIR-014", "NEAR_MISS"),
    "HKREG-DEC-SRC-058": ("HKREG-PAIR-015", "POSITIVE"),
    "HKREG-DEC-SRC-059": ("HKREG-PAIR-015", "NEAR_MISS"),
}

_SOURCE_FACT_AUTHORITY = {
    HKEX_RULEBOOK_CATALOGUE_SOURCE_ID: frozenset(
        {"TOP_LEVEL_PRODUCT_FAMILIES", "BOARD_ASSOCIATION", "CURRENT_LOCATORS"}
    ),
    HKEX_CONSOLIDATED_RULEBOOKS_SOURCE_ID: frozenset(
        {"PREVAILING_ENGLISH_WORDING", "CONTAINED_OFFICIAL_STRUCTURE"}
    ),
    HKEX_REGULATORY_FORMS_SOURCE_ID: frozenset(
        {"FORM_INVENTORY", "FORM_MEMBERSHIP", "FORM_BOARD", "FORM_ENGLISH_CONTENT"}
    ),
    HKEX_FEES_RULES_SOURCE_ID: frozenset(
        {"FEES_INVENTORY", "FEES_MEMBERSHIP", "FEES_BOARD", "FEES_ENGLISH_CONTENT"}
    ),
    HKEX_RULE_UPDATES_SOURCE_ID: frozenset(
        {
            "CHANGED_WORDS",
            "MAPPINGS",
            "STATED_DATES",
            "STATED_CONDITIONS",
            "TRANSITIONS",
            "WITHDRAWALS",
        }
    ),
}

_FACT_CODES: frozenset[str] = frozenset(
    code for codes in _SOURCE_FACT_AUTHORITY.values() for code in codes
) | frozenset(
    {
        "AMENDMENT_CAUSE",
        "COMPLETE_COMPONENT_INVENTORY",
        "EFFECTIVE_STATE",
        "EXTERNAL_TRIGGER_OCCURRENCE",
        "INDIVIDUAL_RULE_WORDING",
        "ORDINARY_RULE_WORDING",
        "PRESENT_COMPILED_TEXT",
        "PRESENT_EFFECT",
    }
)

_FACT_FIELD_NAMES = tuple(
    sorted(
        {
            "source_id",
            "claimed_fact_codes",
            "source_artifact_final",
            "due_source_ids",
            "complete_source_ids",
            "fresh_source_ids",
            "reconciled_source_ids",
            "single_view_completeness_inference",
            "optional_presentation_conflict",
            "source_contract_material_change",
            "final_update_present",
            "matching_current_product",
            "standing_approval_framework",
            "proposal_or_pending_document",
            "direct_approval_required",
            "direct_approval_present",
            "predecessor_exact_match",
            "no_alert_only",
            "observation_gap",
            "historical_investigation_only",
            "object_class",
            "express_inclusion",
            "express_exclusion",
            "assigned_evidence_only_use",
            "inclusion_evidence_missing",
            "inclusion_evidence_unreadable",
            "inclusion_evidence_conflicting",
            "supported_owner_scopes",
            "assigned_owner_scopes",
            "assigned_instance_count",
            "artifact_component_count",
            "artifact_shared_between_boards",
            "identical_wording_across_boards",
            "ownership_conflict",
            "official_parent_supported",
            "website_suggested_scope",
            "required_english_complete",
            "chinese_available",
            "chinese_state",
            "prohibited_source_repair",
            "optional_chinese_bounded_use",
        }
    )
)


class HKEXSourceDecisionErrorCode(StrEnum):
    """Closed malformed source-decision envelope failures."""

    CONTRACT = "HKREG_SOURCE_DECISION_CONTRACT_INVALID"
    IDENTITY = "HKREG_SOURCE_DECISION_IDENTITY_INVALID"
    FINGERPRINT = "HKREG_SOURCE_DECISION_FINGERPRINT_INVALID"


class HKEXSourceDecisionError(ValueError):
    """One fail-closed source-decision fixture rejection."""

    code: HKEXSourceDecisionErrorCode

    def __init__(self, code: HKEXSourceDecisionErrorCode) -> None:
        """Create one stable source-decision fixture error."""
        self.code = code
        super().__init__(code.value)


class HKEXSourceDecisionOutcome(StrEnum):
    """Processing outcome for one exact source or inventory boundary."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


class HKEXSourceDecisionReason(StrEnum):
    """Closed direct result branches in the 62-case checkpoint."""

    ASSIGNED_FACTS_ACCEPTED = "ASSIGNED_FACTS_ACCEPTED"
    OUT_OF_ROLE_FACT_REJECTED = "OUT_OF_ROLE_FACT_REJECTED"
    COMPLETE_UNION_ACCEPTED = "COMPLETE_UNION_ACCEPTED"
    UNIVERSE_INCOMPLETE = "UNIVERSE_INCOMPLETE"
    PRESENTATION_DISCREPANCY_PRESERVED = "PRESENTATION_DISCREPANCY_PRESERVED"
    SOURCE_CONTRACT_REVIEW_REQUIRED = "SOURCE_CONTRACT_REVIEW_REQUIRED"
    SOURCE_CONTRACT_ASSERTION_UNSUPPORTED = "SOURCE_CONTRACT_ASSERTION_UNSUPPORTED"
    APPROVAL_SATISFIED_BY_FINAL_PUBLICATION = "APPROVAL_SATISFIED_BY_FINAL_PUBLICATION"
    APPROVAL_NOT_PROVED = "APPROVAL_NOT_PROVED"
    DIRECT_APPROVAL_EVIDENCE_MISSING = "DIRECT_APPROVAL_EVIDENCE_MISSING"
    SUPPORTED_NO_CHANGE = "SUPPORTED_NO_CHANGE"
    NO_CHANGE_UNPROVED = "NO_CHANGE_UNPROVED"
    BOARD_SPECIFIC_GAP = "BOARD_SPECIFIC_GAP"
    SHARED_UNBOUNDED_GAP = "SHARED_UNBOUNDED_GAP"
    BOUNDED_HISTORICAL_GAP = "BOUNDED_HISTORICAL_GAP"
    RULE_COMPONENT_CLASSIFIED = "RULE_COMPONENT_CLASSIFIED"
    EXCLUDED_NON_RULE_CLASSIFIED = "EXCLUDED_NON_RULE_CLASSIFIED"
    EVIDENCE_ONLY_CLASSIFIED = "EVIDENCE_ONLY_CLASSIFIED"
    MEMBERSHIP_UNRESOLVED = "MEMBERSHIP_UNRESOLVED"
    OWNER_ASSIGNED = "OWNER_ASSIGNED"
    SHARED_ARTIFACT_INSTANCES_ASSIGNED = "SHARED_ARTIFACT_INSTANCES_ASSIGNED"
    MULTI_COMPONENTS_ACCOUNTED = "MULTI_COMPONENTS_ACCOUNTED"
    SEPARATE_IDENTITIES_REQUIRED = "SEPARATE_IDENTITIES_REQUIRED"
    PLACEMENT_DISCREPANCY_PRESERVED = "PLACEMENT_DISCREPANCY_PRESERVED"
    OWNER_MISSING = "OWNER_MISSING"
    OWNER_CONFLICT = "OWNER_CONFLICT"
    DOUBLE_OWNED_INSTANCE = "DOUBLE_OWNED_INSTANCE"
    ORPHAN_COMPONENT = "ORPHAN_COMPONENT"
    DUPLICATE_COMPONENT = "DUPLICATE_COMPONENT"
    CRITICAL_WRONG_BOARD = "CRITICAL_WRONG_BOARD"
    ENGLISH_COMPLETE_CHINESE_OPTIONAL = "ENGLISH_COMPLETE_CHINESE_OPTIONAL"
    REQUIRED_ENGLISH_MISSING = "REQUIRED_ENGLISH_MISSING"
    CHINESE_DISCREPANCY_NONBLOCKING = "CHINESE_DISCREPANCY_NONBLOCKING"
    CHINESE_ENGLISH_DEFECT_SIGNAL = "CHINESE_ENGLISH_DEFECT_SIGNAL"
    CHINESE_ONLY_NO_SERVING_CHANGE = "CHINESE_ONLY_NO_SERVING_CHANGE"
    PROHIBITED_SOURCE_REPAIR = "PROHIBITED_SOURCE_REPAIR"
    OPTIONAL_CHINESE_TRACEABILITY_ONLY = "OPTIONAL_CHINESE_TRACEABILITY_ONLY"


class HKEXSourceAssertionScope(StrEnum):
    """Orthogonal decision dimension selected by a permanent case."""

    FACT_AUTHORITY = "FACT_AUTHORITY"
    SOURCE_UNION = "SOURCE_UNION"
    SOURCE_CONTRACT = "SOURCE_CONTRACT"
    APPROVAL = "APPROVAL"
    NO_CHANGE = "NO_CHANGE"
    OUTAGE_SCOPE = "OUTAGE_SCOPE"
    HISTORICAL_INVESTIGATION = "HISTORICAL_INVESTIGATION"
    MEMBERSHIP = "MEMBERSHIP"
    OWNERSHIP = "OWNERSHIP"
    LANGUAGE = "LANGUAGE"


class HKEXObservationGap(StrEnum):
    """Exact bounded scope of one missing or unusable Observation."""

    NONE = "NONE"
    MAIN_ONLY = "MAIN_ONLY"
    GEM_ONLY = "GEM_ONLY"
    BOTH_SHARED_UNBOUNDED = "BOTH_SHARED_UNBOUNDED"
    BOUNDED_HISTORICAL = "BOUNDED_HISTORICAL"


class HKEXRegulatoryObjectClass(StrEnum):
    """Closed synthetic object classes without implied membership."""

    PRODUCT_FAMILY = "PRODUCT_FAMILY"
    CHAPTER = "CHAPTER"
    ORDINARY_RULE = "ORDINARY_RULE"
    INCORPORATED_NOTE = "INCORPORATED_NOTE"
    APPENDIX = "APPENDIX"
    PRACTICE_NOTE = "PRACTICE_NOTE"
    REGULATORY_FORM = "REGULATORY_FORM"
    FEES_RULE = "FEES_RULE"
    OTHER_COMPONENT = "OTHER_COMPONENT"
    GUIDANCE = "GUIDANCE"
    FAQ = "FAQ"
    CONSULTATION = "CONSULTATION"
    LISTING_DECISION = "LISTING_DECISION"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    TEMPLATE = "TEMPLATE"
    UPDATE_EVIDENCE = "UPDATE_EVIDENCE"
    APPROVAL_EVIDENCE = "APPROVAL_EVIDENCE"
    TRIGGER_EVIDENCE = "TRIGGER_EVIDENCE"
    SOURCE_BASIS_EVIDENCE = "SOURCE_BASIS_EVIDENCE"
    UNKNOWN = "UNKNOWN"


class HKEXChineseEvidenceState(StrEnum):
    """Optional Chinese evidence relationship to controlling English facts."""

    NONE = "NONE"
    HARMLESS_DIFFERENCE = "HARMLESS_DIFFERENCE"
    ENGLISH_DEFECT_SIGNAL = "ENGLISH_DEFECT_SIGNAL"
    CHINESE_ONLY_CHANGE = "CHINESE_ONLY_CHANGE"


class HKEXSourceEvidenceState(StrEnum):
    """Exact ADR 0074 state of the modeled source-evidence slot."""

    AVAILABLE = "AVAILABLE"
    INTENTIONALLY_ABSENT = "INTENTIONALLY_ABSENT"
    UNREADABLE = "UNREADABLE"


class HKEXSourceEvidenceRole(StrEnum):
    """Closed source-shaped evidence roles used by this checkpoint."""

    RULEBOOK_CATALOGUE = "RULEBOOK_CATALOGUE"
    CONSOLIDATED_RULEBOOK = "CONSOLIDATED_RULEBOOK"
    REGULATORY_FORMS = "REGULATORY_FORMS"
    FEES_RULES = "FEES_RULES"
    FINAL_RULE_UPDATE = "FINAL_RULE_UPDATE"
    COMPLETE_SOURCE_UNION = "COMPLETE_SOURCE_UNION"
    OPTIONAL_PRESENTATION = "OPTIONAL_PRESENTATION"
    SOURCE_CONTRACT = "SOURCE_CONTRACT"
    APPROVAL_EVIDENCE = "APPROVAL_EVIDENCE"
    SOURCE_OBSERVATIONS = "SOURCE_OBSERVATIONS"
    HISTORICAL_UPDATE = "HISTORICAL_UPDATE"
    MEMBERSHIP_EVIDENCE = "MEMBERSHIP_EVIDENCE"
    OWNERSHIP_EVIDENCE = "OWNERSHIP_EVIDENCE"
    ENGLISH_EVIDENCE = "ENGLISH_EVIDENCE"
    OPTIONAL_CHINESE = "OPTIONAL_CHINESE"


_EVIDENCE_ROLE_SOURCE_IDS = {
    HKEXSourceEvidenceRole.RULEBOOK_CATALOGUE: HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
    HKEXSourceEvidenceRole.CONSOLIDATED_RULEBOOK: HKEX_CONSOLIDATED_RULEBOOKS_SOURCE_ID,
    HKEXSourceEvidenceRole.REGULATORY_FORMS: HKEX_REGULATORY_FORMS_SOURCE_ID,
    HKEXSourceEvidenceRole.FEES_RULES: HKEX_FEES_RULES_SOURCE_ID,
    HKEXSourceEvidenceRole.FINAL_RULE_UPDATE: HKEX_RULE_UPDATES_SOURCE_ID,
}


@dataclass(frozen=True, slots=True)
class HKEXSourceContractBinding:
    """One exact contract bound into a source-decision case."""

    contract_id: str
    version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXSourceEvidencePacket:
    """One declared embedded source-shaped evidence packet."""

    slot_id: str
    state: HKEXSourceEvidenceState
    path: str
    role: HKEXSourceEvidenceRole
    media_type: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXSourcePairMembership:
    """One case's exact permanent pair role."""

    pair_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKEXSourceDecisionFacts:
    """Orthogonal source, inventory, ownership, and language facts."""

    source_id: str | None
    claimed_fact_codes: tuple[str, ...]
    source_artifact_final: bool
    due_source_ids: tuple[str, ...]
    complete_source_ids: tuple[str, ...]
    fresh_source_ids: tuple[str, ...]
    reconciled_source_ids: tuple[str, ...]
    single_view_completeness_inference: bool
    optional_presentation_conflict: bool
    source_contract_material_change: bool
    final_update_present: bool
    matching_current_product: bool
    standing_approval_framework: bool
    proposal_or_pending_document: bool
    direct_approval_required: bool
    direct_approval_present: bool
    predecessor_exact_match: bool
    no_alert_only: bool
    observation_gap: HKEXObservationGap
    historical_investigation_only: bool
    object_class: HKEXRegulatoryObjectClass
    express_inclusion: bool
    express_exclusion: bool
    assigned_evidence_only_use: bool
    inclusion_evidence_missing: bool
    inclusion_evidence_unreadable: bool
    inclusion_evidence_conflicting: bool
    supported_owner_scopes: tuple[str, ...]
    assigned_owner_scopes: tuple[str, ...]
    assigned_instance_count: int
    artifact_component_count: int
    artifact_shared_between_boards: bool
    identical_wording_across_boards: bool
    ownership_conflict: bool
    official_parent_supported: bool
    website_suggested_scope: str | None
    required_english_complete: bool
    chinese_available: bool
    chinese_state: HKEXChineseEvidenceState
    prohibited_source_repair: bool
    optional_chinese_bounded_use: bool

    def document(self) -> dict[str, object]:
        """Return the exact ordinary evidence packet content."""
        return {
            "source_id": self.source_id,
            "claimed_fact_codes": list(self.claimed_fact_codes),
            "source_artifact_final": self.source_artifact_final,
            "due_source_ids": list(self.due_source_ids),
            "complete_source_ids": list(self.complete_source_ids),
            "fresh_source_ids": list(self.fresh_source_ids),
            "reconciled_source_ids": list(self.reconciled_source_ids),
            "single_view_completeness_inference": (self.single_view_completeness_inference),
            "optional_presentation_conflict": self.optional_presentation_conflict,
            "source_contract_material_change": self.source_contract_material_change,
            "final_update_present": self.final_update_present,
            "matching_current_product": self.matching_current_product,
            "standing_approval_framework": self.standing_approval_framework,
            "proposal_or_pending_document": self.proposal_or_pending_document,
            "direct_approval_required": self.direct_approval_required,
            "direct_approval_present": self.direct_approval_present,
            "predecessor_exact_match": self.predecessor_exact_match,
            "no_alert_only": self.no_alert_only,
            "observation_gap": self.observation_gap.value,
            "historical_investigation_only": self.historical_investigation_only,
            "object_class": self.object_class.value,
            "express_inclusion": self.express_inclusion,
            "express_exclusion": self.express_exclusion,
            "assigned_evidence_only_use": self.assigned_evidence_only_use,
            "inclusion_evidence_missing": self.inclusion_evidence_missing,
            "inclusion_evidence_unreadable": self.inclusion_evidence_unreadable,
            "inclusion_evidence_conflicting": self.inclusion_evidence_conflicting,
            "supported_owner_scopes": list(self.supported_owner_scopes),
            "assigned_owner_scopes": list(self.assigned_owner_scopes),
            "assigned_instance_count": self.assigned_instance_count,
            "artifact_component_count": self.artifact_component_count,
            "artifact_shared_between_boards": self.artifact_shared_between_boards,
            "identical_wording_across_boards": self.identical_wording_across_boards,
            "ownership_conflict": self.ownership_conflict,
            "official_parent_supported": self.official_parent_supported,
            "website_suggested_scope": self.website_suggested_scope,
            "required_english_complete": self.required_english_complete,
            "chinese_available": self.chinese_available,
            "chinese_state": self.chinese_state.value,
            "prohibited_source_repair": self.prohibited_source_repair,
            "optional_chinese_bounded_use": self.optional_chinese_bounded_use,
        }


@dataclass(frozen=True, slots=True)
class HKEXSourceDecisionCase:
    """One strict evidence-to-decision conformance envelope."""

    case_id: str
    primary_coverage_cell_id: str
    pair_membership: HKEXSourcePairMembership | None
    assertion_scope: HKEXSourceAssertionScope
    contract_bindings: tuple[HKEXSourceContractBinding, ...]
    evidence_packet: HKEXSourceEvidencePacket
    package_fingerprint: str
    title: str
    purpose: str
    expected_decision: HKEXSourceDecision
    facts: HKEXSourceDecisionFacts


@dataclass(frozen=True, slots=True)
class HKEXSourceDecision:
    """One structured source decision with no serving or effect authority."""

    outcome: HKEXSourceDecisionOutcome
    reason: HKEXSourceDecisionReason
    accepted_fact_codes: tuple[str, ...]
    rejected_fact_codes: tuple[str, ...]
    membership: HKEXMembership | None
    owner_scope_ids: tuple[str, ...]
    component_instance_count: int
    blocked_scope_ids: tuple[str, ...]
    permitted_scope_ids: tuple[str, ...]
    source_contract_review_required: bool
    english_investigation_required: bool
    supported_no_change: bool

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return one closed evidence-to-decision result document."""
        _text(case_id)
        return {
            "schema_id": "asklegal.hk-regulatory.source-decision-result",
            "schema_version": HKEX_SOURCE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_SOURCE_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "accepted_fact_codes": list(self.accepted_fact_codes),
            "rejected_fact_codes": list(self.rejected_fact_codes),
            "membership": None if self.membership is None else self.membership.value,
            "owner_scope_ids": list(self.owner_scope_ids),
            "component_instance_count": self.component_instance_count,
            "blocked_scope_ids": list(self.blocked_scope_ids),
            "permitted_scope_ids": list(self.permitted_scope_ids),
            "source_contract_review_required": self.source_contract_review_required,
            "english_investigation_required": self.english_investigation_required,
            "supported_no_change": self.supported_no_change,
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "external_effects": "NONE",
        }


@dataclass(frozen=True, slots=True)
class HKEXSourceDecisionReport:
    """Complete expected-versus-observed source-decision report."""

    case_id: str
    assertion_scope: HKEXSourceAssertionScope
    observed_decision: HKEXSourceDecision
    expected_decision: HKEXSourceDecision
    conformance_status: str

    def document(self) -> dict[str, object]:
        """Return one closed report without granting downstream authority."""
        return {
            "schema_id": "asklegal.hk-regulatory.source-decision-report",
            "schema_version": HKEX_SOURCE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_SOURCE_DECISION_RULE_ID,
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
class _DecisionDetails:
    """Optional structured result dimensions for a source decision."""

    accepted: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    membership: HKEXMembership | None = None
    owners: tuple[str, ...] = ()
    instances: int = 0
    blocked: tuple[str, ...] = ()
    permitted: tuple[str, ...] = ()
    contract_review: bool = False
    english_investigation: bool = False
    no_change: bool = False


def hkex_source_decision_case_from_document(document: object) -> HKEXSourceDecisionCase:
    """Strictly decode and fingerprint one evidence-to-decision case."""
    root = _json_object(document)
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
            "pair_membership",
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
    case_id = _case_identity(root)
    suffix = case_id.rsplit("-", maxsplit=1)[1]
    contract_bindings = _contract_bindings(root["contract_bindings"])
    if len(contract_bindings) != _MIN_CONTRACT_BINDINGS:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    primary_cells = _json_strings(root["primary_coverage_cell_ids"])
    if primary_cells != (f"HKREG-COV-DSRC-{suffix}",):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.IDENTITY)
    _sorted_unique_strings(root["secondary_coverage_cell_ids"])
    pair_membership = _case_pair_membership(root["pair_membership"], case_id)
    declared_inputs = _json_strings(root["declared_input_inventory"])
    declared_references = _json_strings(root["declared_reference_inventory"])
    declared_expected = _json_strings(root["declared_expected_inventory"])
    scope = _json_enum(root["assertion_scope"], HKEXSourceAssertionScope)
    if _json_strings(root["required_result_dimensions"]) != (
        "AUTHORITY",
        "MEMBERSHIP",
        "OWNERSHIP",
        "PROCESSING",
        "SOURCE_FACTS",
    ):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    evidence_packet_fields = _safe_evidence_packet_fields(root["evidence_packet_fields"])
    _nonempty_sorted_strings(root["supporting_evidence_ranges"])
    _nonempty_sorted_strings(root["rule_trace"])
    _nonempty_sorted_strings(root["established_facts"])
    _sorted_unique_strings(root["unresolved_facts"])
    if _json_array(root["permitted_equivalent_results"]):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    _sorted_unique_strings(root["critical_error_codes"])
    package_fingerprint = _json_fingerprint(root["package_fingerprint"])
    _validate_required_bindings(contract_bindings, package_fingerprint)
    title = _text(root["title"])
    purpose = _text(root["purpose"])
    expected_decision = _expected_decision(root["expected_decision"], case_id=case_id)
    facts = _facts(root["facts"])
    evidence_packet = _evidence_packet(root["evidence_packet"], facts=facts)
    if declared_inputs != (evidence_packet.slot_id,):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    if declared_references != tuple(binding.contract_id for binding in contract_bindings):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    if declared_expected != ("SOURCE_DECISION_REPORT",):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    if evidence_packet_fields != _FACT_FIELD_NAMES:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    case_fingerprint = _json_fingerprint(root["case_fingerprint"])
    projection = dict(root)
    projection.pop("case_fingerprint")
    if fingerprint(checked_json_value(projection)) != case_fingerprint:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.FINGERPRINT)
    return HKEXSourceDecisionCase(
        case_id,
        primary_cells[0],
        pair_membership,
        scope,
        contract_bindings,
        evidence_packet,
        package_fingerprint,
        title,
        purpose,
        expected_decision,
        facts,
    )


def _case_identity(root: dict[str, JsonValue]) -> str:
    _constant(root["schema_id"], "asklegal.hk-regulatory.source-decision-case")
    _constant(root["schema_version"], HKEX_SOURCE_DECISION_CONTRACT_VERSION)
    _constant(root["package_contract_version"], "1.0.0")
    case_id = _pattern_text(root["case_id"], _CASE_PATTERN)
    _constant(root["suite_layer"], "EVIDENCE_TO_DECISION")
    _constant(root["primary_checkpoint"], "SOURCE_FACT_AUTHORITY")
    _true(root["frozen"])
    _constant(root["synthetic_evidence_class"], "SYNTHETIC_NO_REAL_AUTHORITY")
    _constant(root["synthetic_cutoff"], "2026-08-24T00:00:00Z")
    _constant(root["scope_id"], "HKEX_CROSS_BOARD")
    _constant(root["prior_state"], "SYNTHETIC_ACCEPTED_PREDECESSOR")
    return case_id


def decide_hkex_source_case(case: HKEXSourceDecisionCase) -> HKEXSourceDecision:
    """Derive one structured result from facts and assertion dimension, never ID."""
    if type(case) is not HKEXSourceDecisionCase:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    evaluators = {
        HKEXSourceAssertionScope.FACT_AUTHORITY: _decide_fact_authority,
        HKEXSourceAssertionScope.SOURCE_UNION: _decide_source_union,
        HKEXSourceAssertionScope.SOURCE_CONTRACT: _decide_source_contract,
        HKEXSourceAssertionScope.APPROVAL: _decide_approval,
        HKEXSourceAssertionScope.NO_CHANGE: _decide_no_change,
        HKEXSourceAssertionScope.OUTAGE_SCOPE: _decide_outage,
        HKEXSourceAssertionScope.HISTORICAL_INVESTIGATION: _decide_historical,
        HKEXSourceAssertionScope.MEMBERSHIP: _decide_membership,
        HKEXSourceAssertionScope.OWNERSHIP: _decide_ownership,
        HKEXSourceAssertionScope.LANGUAGE: _decide_language,
    }
    return evaluators[case.assertion_scope](case.facts)


def run_hkex_source_case(case: HKEXSourceDecisionCase) -> HKEXSourceDecisionReport:
    """Compare the complete fact-derived decision to separately frozen truth."""
    observed = decide_hkex_source_case(case)
    status = "PASS" if observed == case.expected_decision else "FAIL"
    return HKEXSourceDecisionReport(
        case_id=case.case_id,
        assertion_scope=case.assertion_scope,
        observed_decision=observed,
        expected_decision=case.expected_decision,
        conformance_status=status,
    )


def _decision(
    outcome: HKEXSourceDecisionOutcome,
    reason: HKEXSourceDecisionReason,
    details: _DecisionDetails | None = None,
) -> HKEXSourceDecision:
    resolved = _DecisionDetails() if details is None else details
    return HKEXSourceDecision(
        outcome=outcome,
        reason=reason,
        accepted_fact_codes=resolved.accepted,
        rejected_fact_codes=resolved.rejected,
        membership=resolved.membership,
        owner_scope_ids=resolved.owners,
        component_instance_count=resolved.instances,
        blocked_scope_ids=resolved.blocked,
        permitted_scope_ids=resolved.permitted,
        source_contract_review_required=resolved.contract_review,
        english_investigation_required=resolved.english_investigation,
        supported_no_change=resolved.no_change,
    )


def _decide_fact_authority(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    if facts.source_id not in _SOURCE_FACT_AUTHORITY:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.OUT_OF_ROLE_FACT_REJECTED,
            _DecisionDetails(rejected=facts.claimed_fact_codes),
        )
    allowed = _SOURCE_FACT_AUTHORITY[facts.source_id]
    accepted = tuple(code for code in facts.claimed_fact_codes if code in allowed)
    rejected = tuple(code for code in facts.claimed_fact_codes if code not in allowed)
    if facts.source_id == HKEX_RULE_UPDATES_SOURCE_ID and not facts.source_artifact_final:
        rejected = facts.claimed_fact_codes
        accepted = ()
    if rejected:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.OUT_OF_ROLE_FACT_REJECTED,
            _DecisionDetails(accepted=accepted, rejected=rejected),
        )
    return _decision(
        HKEXSourceDecisionOutcome.PASS,
        HKEXSourceDecisionReason.ASSIGNED_FACTS_ACCEPTED,
        _DecisionDetails(accepted=accepted),
    )


def _decide_source_union(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    complete = _all_due_sources_ready(facts) and not facts.single_view_completeness_inference
    if complete:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.COMPLETE_UNION_ACCEPTED,
        )
    return _decision(
        HKEXSourceDecisionOutcome.BLOCK,
        HKEXSourceDecisionReason.UNIVERSE_INCOMPLETE,
        _DecisionDetails(blocked=_SCOPE_IDS),
    )


def _decide_source_contract(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    if facts.source_contract_material_change:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.SOURCE_CONTRACT_REVIEW_REQUIRED,
            _DecisionDetails(blocked=_SCOPE_IDS, contract_review=True),
        )
    if facts.optional_presentation_conflict:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.PRESENTATION_DISCREPANCY_PRESERVED,
            _DecisionDetails(permitted=_SCOPE_IDS),
        )
    return _decision(
        HKEXSourceDecisionOutcome.BLOCK,
        HKEXSourceDecisionReason.SOURCE_CONTRACT_ASSERTION_UNSUPPORTED,
        _DecisionDetails(blocked=_SCOPE_IDS),
    )


def _decide_approval(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    if facts.direct_approval_required and not facts.direct_approval_present:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.DIRECT_APPROVAL_EVIDENCE_MISSING,
        )
    if facts.proposal_or_pending_document:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.APPROVAL_NOT_PROVED,
        )
    if (
        facts.final_update_present
        and facts.matching_current_product
        and facts.standing_approval_framework
    ):
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.APPROVAL_SATISFIED_BY_FINAL_PUBLICATION,
        )
    return _decision(
        HKEXSourceDecisionOutcome.BLOCK,
        HKEXSourceDecisionReason.APPROVAL_NOT_PROVED,
    )


def _decide_no_change(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    complete = (
        _all_due_sources_ready(facts)
        and facts.predecessor_exact_match
        and facts.observation_gap is HKEXObservationGap.NONE
        and not facts.no_alert_only
    )
    if complete:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.SUPPORTED_NO_CHANGE,
            _DecisionDetails(no_change=True),
        )
    return _decision(
        HKEXSourceDecisionOutcome.BLOCK,
        HKEXSourceDecisionReason.NO_CHANGE_UNPROVED,
        _outage_details(facts.observation_gap),
    )


def _all_due_sources_ready(facts: HKEXSourceDecisionFacts) -> bool:
    due = facts.due_source_ids
    return (
        due == HKEX_REGULATORY_SOURCE_IDS
        and facts.complete_source_ids == due
        and facts.fresh_source_ids == due
        and facts.reconciled_source_ids == due
    )


def _outage_details(gap: HKEXObservationGap) -> _DecisionDetails:
    if gap is HKEXObservationGap.MAIN_ONLY:
        return _DecisionDetails(
            blocked=(HKEX_MAIN_SCOPE_ID,),
            permitted=(HKEX_GEM_SCOPE_ID,),
        )
    if gap is HKEXObservationGap.GEM_ONLY:
        return _DecisionDetails(
            blocked=(HKEX_GEM_SCOPE_ID,),
            permitted=(HKEX_MAIN_SCOPE_ID,),
        )
    if gap is HKEXObservationGap.BOUNDED_HISTORICAL:
        return _DecisionDetails(permitted=_SCOPE_IDS)
    if gap is HKEXObservationGap.BOTH_SHARED_UNBOUNDED:
        return _DecisionDetails(blocked=_SCOPE_IDS)
    return _DecisionDetails()


def _decide_outage(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    if facts.observation_gap is HKEXObservationGap.MAIN_ONLY:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.BOARD_SPECIFIC_GAP,
            _DecisionDetails(
                blocked=(HKEX_MAIN_SCOPE_ID,),
                permitted=(HKEX_GEM_SCOPE_ID,),
            ),
        )
    if facts.observation_gap is HKEXObservationGap.GEM_ONLY:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.BOARD_SPECIFIC_GAP,
            _DecisionDetails(
                blocked=(HKEX_GEM_SCOPE_ID,),
                permitted=(HKEX_MAIN_SCOPE_ID,),
            ),
        )
    return _decision(
        HKEXSourceDecisionOutcome.BLOCK,
        HKEXSourceDecisionReason.SHARED_UNBOUNDED_GAP,
        _DecisionDetails(blocked=_SCOPE_IDS),
    )


def _decide_historical(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    if (
        facts.observation_gap is HKEXObservationGap.BOUNDED_HISTORICAL
        and facts.historical_investigation_only
    ):
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.BOUNDED_HISTORICAL_GAP,
            _DecisionDetails(permitted=_SCOPE_IDS),
        )
    return _decision(
        HKEXSourceDecisionOutcome.BLOCK,
        HKEXSourceDecisionReason.SHARED_UNBOUNDED_GAP,
        _DecisionDetails(blocked=_SCOPE_IDS),
    )


def _membership(facts: HKEXSourceDecisionFacts) -> HKEXMembership:
    if (
        facts.inclusion_evidence_missing
        or facts.inclusion_evidence_unreadable
        or facts.inclusion_evidence_conflicting
    ):
        return HKEXMembership.UNRESOLVED_MEMBERSHIP
    if facts.express_inclusion:
        return HKEXMembership.RULE_COMPONENT
    if facts.assigned_evidence_only_use:
        return HKEXMembership.EVIDENCE_ONLY
    if facts.express_exclusion:
        return HKEXMembership.EXCLUDED_NON_RULE
    return HKEXMembership.UNRESOLVED_MEMBERSHIP


def _decide_membership(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    membership = _membership(facts)
    if membership is HKEXMembership.RULE_COMPONENT:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.RULE_COMPONENT_CLASSIFIED,
            _DecisionDetails(
                membership=membership,
                owners=facts.supported_owner_scopes,
                instances=max(1, facts.artifact_component_count),
            ),
        )
    if membership is HKEXMembership.EXCLUDED_NON_RULE:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.EXCLUDED_NON_RULE_CLASSIFIED,
            _DecisionDetails(membership=membership),
        )
    if membership is HKEXMembership.EVIDENCE_ONLY:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.EVIDENCE_ONLY_CLASSIFIED,
            _DecisionDetails(membership=membership),
        )
    return _decision(
        HKEXSourceDecisionOutcome.QUARANTINE,
        HKEXSourceDecisionReason.MEMBERSHIP_UNRESOLVED,
        _DecisionDetails(membership=membership),
    )


def _decide_ownership(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    rejection = _ownership_rejection(facts)
    return _ownership_success(facts) if rejection is None else rejection


def _ownership_rejection(
    facts: HKEXSourceDecisionFacts,
) -> HKEXSourceDecision | None:
    supported = facts.supported_owner_scopes
    if facts.ownership_conflict:
        return _decision(
            HKEXSourceDecisionOutcome.QUARANTINE,
            HKEXSourceDecisionReason.OWNER_CONFLICT,
        )
    if not supported:
        return _decision(
            HKEXSourceDecisionOutcome.QUARANTINE,
            HKEXSourceDecisionReason.OWNER_MISSING,
        )
    if not facts.official_parent_supported:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.ORPHAN_COMPONENT,
        )
    return _ownership_assignment_rejection(facts)


def _ownership_assignment_rejection(
    facts: HKEXSourceDecisionFacts,
) -> HKEXSourceDecision | None:
    supported = facts.supported_owner_scopes
    assigned = facts.assigned_owner_scopes
    if not assigned or facts.assigned_instance_count == 0:
        return _decision(
            HKEXSourceDecisionOutcome.QUARANTINE,
            HKEXSourceDecisionReason.OWNER_MISSING,
        )
    if facts.assigned_instance_count > facts.artifact_component_count and len(supported) == 1:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.DUPLICATE_COMPONENT,
        )
    if not set(assigned).issubset(supported):
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.CRITICAL_WRONG_BOARD,
        )
    if len(supported) == _BOARD_COUNT and facts.assigned_instance_count == 1:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.DOUBLE_OWNED_INSTANCE,
        )
    return None


def _ownership_success(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    supported = facts.supported_owner_scopes
    assigned = facts.assigned_owner_scopes
    details = _DecisionDetails(
        owners=assigned,
        instances=facts.assigned_instance_count,
    )
    if facts.artifact_shared_between_boards:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.SHARED_ARTIFACT_INSTANCES_ASSIGNED,
            details,
        )
    if facts.identical_wording_across_boards:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.SEPARATE_IDENTITIES_REQUIRED,
            details,
        )
    if facts.artifact_component_count > 1:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.MULTI_COMPONENTS_ACCOUNTED,
            details,
        )
    if facts.website_suggested_scope is not None and facts.website_suggested_scope not in supported:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.PLACEMENT_DISCREPANCY_PRESERVED,
            details,
        )
    return _decision(
        HKEXSourceDecisionOutcome.PASS,
        HKEXSourceDecisionReason.OWNER_ASSIGNED,
        details,
    )


def _decide_language(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    if facts.prohibited_source_repair:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.PROHIBITED_SOURCE_REPAIR,
        )
    if not facts.required_english_complete:
        return _decision(
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.REQUIRED_ENGLISH_MISSING,
        )
    return _decide_optional_chinese(facts)


def _decide_optional_chinese(facts: HKEXSourceDecisionFacts) -> HKEXSourceDecision:
    if facts.chinese_state is HKEXChineseEvidenceState.ENGLISH_DEFECT_SIGNAL:
        return _decision(
            HKEXSourceDecisionOutcome.QUARANTINE,
            HKEXSourceDecisionReason.CHINESE_ENGLISH_DEFECT_SIGNAL,
            _DecisionDetails(english_investigation=True),
        )
    if facts.chinese_state is HKEXChineseEvidenceState.HARMLESS_DIFFERENCE:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.CHINESE_DISCREPANCY_NONBLOCKING,
        )
    if facts.chinese_state is HKEXChineseEvidenceState.CHINESE_ONLY_CHANGE:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.CHINESE_ONLY_NO_SERVING_CHANGE,
        )
    if facts.optional_chinese_bounded_use:
        return _decision(
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.OPTIONAL_CHINESE_TRACEABILITY_ONLY,
        )
    return _decision(
        HKEXSourceDecisionOutcome.PASS,
        HKEXSourceDecisionReason.ENGLISH_COMPLETE_CHINESE_OPTIONAL,
    )


def _facts(value: JsonValue) -> HKEXSourceDecisionFacts:
    root = _json_object(value)
    _exact_keys(root, set(_FACT_FIELD_NAMES))
    source_id = _optional_text(root["source_id"])
    if source_id is not None and source_id not in HKEX_REGULATORY_SOURCE_IDS:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    supported = _scope_ids(root["supported_owner_scopes"])
    assigned = _scope_ids(root["assigned_owner_scopes"])
    website_scope = _optional_text(root["website_suggested_scope"])
    if website_scope is not None and website_scope not in _SCOPE_IDS:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    claimed_fact_codes = _sorted_unique_strings(root["claimed_fact_codes"])
    if any(code not in _FACT_CODES for code in claimed_fact_codes):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    due_source_ids = _source_ids(root["due_source_ids"])
    complete_source_ids = _source_ids(root["complete_source_ids"])
    fresh_source_ids = _source_ids(root["fresh_source_ids"])
    reconciled_source_ids = _source_ids(root["reconciled_source_ids"])
    if any(
        not set(observed).issubset(due_source_ids)
        for observed in (complete_source_ids, fresh_source_ids, reconciled_source_ids)
    ):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    chinese_available = _boolean(root["chinese_available"])
    chinese_state = _json_enum(root["chinese_state"], HKEXChineseEvidenceState)
    optional_chinese_bounded_use = _boolean(root["optional_chinese_bounded_use"])
    if (chinese_state is not HKEXChineseEvidenceState.NONE and not chinese_available) or (
        optional_chinese_bounded_use and not chinese_available
    ):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return HKEXSourceDecisionFacts(
        source_id=source_id,
        claimed_fact_codes=claimed_fact_codes,
        source_artifact_final=_boolean(root["source_artifact_final"]),
        due_source_ids=due_source_ids,
        complete_source_ids=complete_source_ids,
        fresh_source_ids=fresh_source_ids,
        reconciled_source_ids=reconciled_source_ids,
        single_view_completeness_inference=_boolean(root["single_view_completeness_inference"]),
        optional_presentation_conflict=_boolean(root["optional_presentation_conflict"]),
        source_contract_material_change=_boolean(root["source_contract_material_change"]),
        final_update_present=_boolean(root["final_update_present"]),
        matching_current_product=_boolean(root["matching_current_product"]),
        standing_approval_framework=_boolean(root["standing_approval_framework"]),
        proposal_or_pending_document=_boolean(root["proposal_or_pending_document"]),
        direct_approval_required=_boolean(root["direct_approval_required"]),
        direct_approval_present=_boolean(root["direct_approval_present"]),
        predecessor_exact_match=_boolean(root["predecessor_exact_match"]),
        no_alert_only=_boolean(root["no_alert_only"]),
        observation_gap=_json_enum(root["observation_gap"], HKEXObservationGap),
        historical_investigation_only=_boolean(root["historical_investigation_only"]),
        object_class=_json_enum(root["object_class"], HKEXRegulatoryObjectClass),
        express_inclusion=_boolean(root["express_inclusion"]),
        express_exclusion=_boolean(root["express_exclusion"]),
        assigned_evidence_only_use=_boolean(root["assigned_evidence_only_use"]),
        inclusion_evidence_missing=_boolean(root["inclusion_evidence_missing"]),
        inclusion_evidence_unreadable=_boolean(root["inclusion_evidence_unreadable"]),
        inclusion_evidence_conflicting=_boolean(root["inclusion_evidence_conflicting"]),
        supported_owner_scopes=supported,
        assigned_owner_scopes=assigned,
        assigned_instance_count=_nonnegative_integer(root["assigned_instance_count"]),
        artifact_component_count=_nonnegative_integer(root["artifact_component_count"]),
        artifact_shared_between_boards=_boolean(root["artifact_shared_between_boards"]),
        identical_wording_across_boards=_boolean(root["identical_wording_across_boards"]),
        ownership_conflict=_boolean(root["ownership_conflict"]),
        official_parent_supported=_boolean(root["official_parent_supported"]),
        website_suggested_scope=website_scope,
        required_english_complete=_boolean(root["required_english_complete"]),
        chinese_available=chinese_available,
        chinese_state=chinese_state,
        prohibited_source_repair=_boolean(root["prohibited_source_repair"]),
        optional_chinese_bounded_use=optional_chinese_bounded_use,
    )


def _expected_decision(value: JsonValue, *, case_id: str) -> HKEXSourceDecision:
    root = _json_object(value)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "case_id",
            "outcome",
            "reason",
            "accepted_fact_codes",
            "rejected_fact_codes",
            "membership",
            "owner_scope_ids",
            "component_instance_count",
            "blocked_scope_ids",
            "permitted_scope_ids",
            "source_contract_review_required",
            "english_investigation_required",
            "supported_no_change",
            "search_record_authorized",
            "embedding_authorized",
            "release_authorized",
            "serving_authorized",
            "external_effects",
        },
    )
    _constant(root["schema_id"], "asklegal.hk-regulatory.source-decision-result")
    _constant(root["schema_version"], HKEX_SOURCE_DECISION_CONTRACT_VERSION)
    _constant(root["rule_id"], HKEX_SOURCE_DECISION_RULE_ID)
    _constant(root["case_id"], case_id)
    accepted = _sorted_unique_strings(root["accepted_fact_codes"])
    rejected = _sorted_unique_strings(root["rejected_fact_codes"])
    if set(accepted) & set(rejected) or any(
        code not in _FACT_CODES for code in (*accepted, *rejected)
    ):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    membership_value = root["membership"]
    membership = None if membership_value is None else _json_enum(membership_value, HKEXMembership)
    for field in (
        "search_record_authorized",
        "embedding_authorized",
        "release_authorized",
        "serving_authorized",
    ):
        if _boolean(root[field]):
            raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    _constant(root["external_effects"], "NONE")
    return HKEXSourceDecision(
        outcome=_json_enum(root["outcome"], HKEXSourceDecisionOutcome),
        reason=_json_enum(root["reason"], HKEXSourceDecisionReason),
        accepted_fact_codes=accepted,
        rejected_fact_codes=rejected,
        membership=membership,
        owner_scope_ids=_scope_ids(root["owner_scope_ids"]),
        component_instance_count=_nonnegative_integer(root["component_instance_count"]),
        blocked_scope_ids=_scope_ids(root["blocked_scope_ids"]),
        permitted_scope_ids=_scope_ids(root["permitted_scope_ids"]),
        source_contract_review_required=_boolean(root["source_contract_review_required"]),
        english_investigation_required=_boolean(root["english_investigation_required"]),
        supported_no_change=_boolean(root["supported_no_change"]),
    )


def _pair_membership(value: JsonValue) -> HKEXSourcePairMembership | None:
    if value is None:
        return None
    root = _json_object(value)
    _exact_keys(root, {"pair_id", "role"})
    pair_id = _pattern_text(root["pair_id"], r"HKREG-PAIR-0(0[1-9]|1[0-5])")
    role = _text(root["role"])
    if role not in {"POSITIVE", "NEAR_MISS"}:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return HKEXSourcePairMembership(pair_id, role)


def _case_pair_membership(
    value: JsonValue,
    case_id: str,
) -> HKEXSourcePairMembership | None:
    membership = _pair_membership(value)
    actual = None if membership is None else (membership.pair_id, membership.role)
    if actual != _EXPECTED_PAIR_MEMBERSHIPS.get(case_id):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.IDENTITY)
    return membership


def _contract_bindings(value: JsonValue) -> tuple[HKEXSourceContractBinding, ...]:
    bindings: list[HKEXSourceContractBinding] = []
    for item in _json_object_array(value):
        _exact_keys(item, {"contract_id", "version", "fingerprint"})
        bindings.append(
            HKEXSourceContractBinding(
                contract_id=_text(item["contract_id"]),
                version=_text(item["version"]),
                fingerprint=_json_fingerprint(item["fingerprint"]),
            )
        )
    if tuple(binding.contract_id for binding in bindings) != tuple(
        sorted({binding.contract_id for binding in bindings})
    ):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return tuple(bindings)


def _validate_required_bindings(
    bindings: tuple[HKEXSourceContractBinding, ...],
    package_fingerprint: str,
) -> None:
    if (
        tuple(binding.contract_id for binding in bindings)
        != (
            "asklegal.hk-regulatory.conformance-universe",
            "asklegal.hk-regulatory.source-decision-case",
        )
        or any(binding.version != "1.0.0" for binding in bindings)
        or bindings[0].fingerprint != package_fingerprint
        or bindings[1].fingerprint != _SOURCE_CASE_CONTRACT_FINGERPRINT
    ):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)


def _evidence_packet(
    value: JsonValue,
    *,
    facts: HKEXSourceDecisionFacts,
) -> HKEXSourceEvidencePacket:
    root = _json_object(value)
    _exact_keys(
        root,
        {
            "slot_id",
            "state",
            "path",
            "role",
            "media_type",
            "content_fingerprint",
        },
    )
    packet = HKEXSourceEvidencePacket(
        slot_id=_text(root["slot_id"]),
        state=_json_enum(root["state"], HKEXSourceEvidenceState),
        path=_text(root["path"]),
        role=_json_enum(root["role"], HKEXSourceEvidenceRole),
        media_type=_text(root["media_type"]),
        content_fingerprint=_json_fingerprint(root["content_fingerprint"]),
    )
    if (
        packet.slot_id != "source-evidence"
        or packet.media_type != "application/json"
        or not _safe_relative_path(packet.path)
        or packet.content_fingerprint != fingerprint(checked_json_value(facts.document()))
    ):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    role_source_id = _EVIDENCE_ROLE_SOURCE_IDS.get(packet.role)
    if (facts.source_id is None) != (role_source_id is None) or (
        facts.source_id is not None and facts.source_id != role_source_id
    ):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    if packet.state is HKEXSourceEvidenceState.INTENTIONALLY_ABSENT:
        if not facts.inclusion_evidence_missing:
            raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    elif (
        packet.state is HKEXSourceEvidenceState.UNREADABLE
        and not facts.inclusion_evidence_unreadable
    ):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return packet


def _safe_relative_path(path: str) -> bool:
    if path.startswith("/") or "\\" in path or "://" in path:
        return False
    segments = path.split("/")
    return bool(segments) and all(segment not in {"", ".", ".."} for segment in segments)


def _safe_evidence_packet_fields(value: JsonValue) -> tuple[str, ...]:
    fields = _sorted_unique_strings(value)
    forbidden = (
        "case_id",
        "title",
        "package_path",
        "coverage_cell",
        "pair_role",
        "expected_result",
        "adjudication",
        "critical_error",
    )
    if any(any(fragment in field.lower() for fragment in forbidden) for field in fields):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return fields


def _json_object(value: object) -> dict[str, JsonValue]:
    try:
        checked = checked_json_value(value)
    except ContractViolation as error:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT) from error
    if not isinstance(checked, dict):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return checked


def _json_object_array(value: JsonValue) -> tuple[dict[str, JsonValue], ...]:
    return tuple(_json_object(item) for item in _json_array(value))


def _json_array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return value


def _sorted_unique_strings(value: JsonValue) -> tuple[str, ...]:
    result = _json_strings(value)
    if result != tuple(sorted(set(result))):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return result


def _nonempty_sorted_strings(value: JsonValue) -> tuple[str, ...]:
    result = _sorted_unique_strings(value)
    if not result:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return result


def _json_strings(value: JsonValue) -> tuple[str, ...]:
    return tuple(_text(item) for item in _json_array(value))


def _scope_ids(value: JsonValue) -> tuple[str, ...]:
    result = _sorted_unique_strings(value)
    if any(item not in _SCOPE_IDS for item in result):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return result


def _source_ids(value: JsonValue) -> tuple[str, ...]:
    result = _sorted_unique_strings(value)
    if any(item not in HKEX_REGULATORY_SOURCE_IDS for item in result):
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return result


def _text(value: JsonValue) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return value


def _optional_text(value: JsonValue) -> str | None:
    return None if value is None else _text(value)


def _boolean(value: JsonValue) -> bool:
    if type(value) is not bool:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return value


def _nonnegative_integer(value: JsonValue) -> int:
    if type(value) is not int or value < 0:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
    return value


def _json_fingerprint(value: JsonValue) -> str:
    return _pattern_text(value, _FINGERPRINT_PATTERN)


def _pattern_text(value: JsonValue, pattern: str) -> str:
    text = _text(value)
    if fullmatch(pattern, text) is None:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.IDENTITY)
    return text


def _json_enum[E: StrEnum](value: JsonValue, enum_type: type[E]) -> E:
    text = _text(value)
    try:
        return enum_type(text)
    except ValueError as error:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT) from error


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)


def _constant(value: JsonValue, expected: str) -> None:
    if value != expected or type(value) is not str:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)


def _true(value: JsonValue) -> None:
    if value is not True:
        raise HKEXSourceDecisionError(HKEXSourceDecisionErrorCode.CONTRACT)
