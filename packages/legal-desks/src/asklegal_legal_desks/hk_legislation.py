"""Offline conformance for partial Hong Kong Legislation baseline rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal
from unicodedata import normalize

from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.errors import ContractViolation
from asklegal_contracts.json_types import checked_json_value

from .model import RulebookError, RulebookErrorCode

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

HK_BASELINE_INVENTORY_RULE_ID = "HKLEG-BASE-INV-001"
HK_BASELINE_OBSERVATION_RULE_ID = "HKLEG-BASE-OBS-001"
HK_BASELINE_EVIDENCE_RULE_ID = "HKLEG-BASE-EVID-001"
HK_BASELINE_STATE_RULE_ID = "HKLEG-BASE-STATE-001"
HK_BASELINE_LIMIT_RULE_ID = "HKLEG-BASE-LIMIT-001"
HK_BASELINE_IDENTITY_RULE_ID = "HKLEG-BASE-ID-001"
HK_BASELINE_DISPOSITION_RULE_ID = "HKLEG-BASE-DISP-001"
HK_BASELINE_RECORD_RULE_ID = "HKLEG-BASE-REC-001"
HK_BASELINE_RELEASE_ACCOUNTING_RULE_ID = "HKLEG-BASE-REL-001"
HK_BASELINE_REVIEW_RULE_ID = "HKLEG-BASE-REVIEW-001"
HK_BASELINE_HISTORY_RULE_ID = "HKLEG-BASE-HIST-001"
HK_BASELINE_CHANGE_RULE_ID = "HKLEG-BASE-CHANGE-001"
HK_CURRENT_OBSERVATION_RULE_IDS = (
    "HKLEG-CURRENT-OBS-001",
    "HKLEG-CURRENT-OBS-002",
    "HKLEG-CURRENT-OBS-003",
)
HK_CURRENT_EVIDENCE_RULE_IDS = (
    "HKLEG-CURRENT-EVID-001",
    "HKLEG-CURRENT-EVID-002",
    "HKLEG-CURRENT-EVID-003",
    "HKLEG-CURRENT-EVID-004",
)
HK_CURRENT_DIFFERENCE_RULE_IDS = ("HKLEG-CURRENT-DIFF-001", "HKLEG-CURRENT-DIFF-002")
HK_CURRENT_CAUSE_RULE_IDS = ("HKLEG-CURRENT-CAUSE-001", "HKLEG-CURRENT-CAUSE-002")
HK_CURRENT_COMMENCEMENT_RULE_ID = "HKLEG-CURRENT-COMMENCEMENT-001"
HK_CURRENT_CESSATION_RULE_ID = "HKLEG-CURRENT-CESSATION-001"
HK_CURRENT_PUBLICATION_RULE_ID = "HKLEG-CURRENT-PUBLICATION-001"
HK_CURRENT_TEXT_EVENT_RULE_ID = "HKLEG-CURRENT-TEXT-EVENT-001"
HK_CURRENT_EVENT_RULE_ID = "HKLEG-CURRENT-EVENT-001"
HK_CURRENT_DISPOSITION_RULE_ID = "HKLEG-CURRENT-DISP-001"
HK_CURRENT_RECORD_RULE_ID = "HKLEG-CURRENT-REC-001"
HK_CURRENT_RELEASE_ACCOUNTING_RULE_ID = "HKLEG-CURRENT-REL-001"
HK_RECONSTRUCTION_PLAN_SEMANTIC_RULE_ID = "HKLEG-RECON-PLAN-SEMANTIC-001"
HK_RECONSTRUCTION_PLAN_RULE_ID = "HKLEG-RECON-PLAN-001"
HK_CURRENT_INVENTORY_SOURCE_ID = "HK-LEG-HKEL-CURRENT-INVENTORY"
HK_GAZETTE_SOURCE_ID = "HK-LEG-GLD-EGAZETTE"
HK_CURRENT_DATA_SOURCE_ID = "HK-LEG-HKEL-CURRENT-DATA"
HK_VERIFIED_COPIES_SOURCE_ID = "HK-LEG-HKEL-VERIFIED-COPIES"
HK_ASSISTED_COPIES_SOURCE_ID = "HK-LEG-HKEL-ASSISTED-COPIES"
HK_PAST_DATA_SOURCE_ID = "HK-LEG-HKEL-PAST-DATA"
HK_EDITORIAL_RECORDS_SOURCE_ID = "HK-LEG-HKEL-EDITORIAL-RECORDS"
HK_PUBLICATION_SPECIFICATIONS_SOURCE_ID = "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS"
HK_BASIC_LAW_PORTAL_SOURCE_ID = "HK-LEG-BASIC-LAW-PORTAL"
HK_NPC_NATIONAL_LAWS_SOURCE_ID = "HK-LEG-NPC-NATIONAL-LAWS-DATABASE"
HK_NPCSC_MATERIALS_SOURCE_ID = "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS"
HK_ORDINANCES_SCOPE_ID = "rsc_fa928755a873dbf8df5f4f2d333b672cd1d935af9bf99b95"
HK_SUBSIDIARY_SCOPE_ID = "rsc_1cdf5a558e8286dadf84f819de1d48168d455cd457fcf30e"
HK_CONSTITUTIONAL_SCOPE_ID = "rsc_4708261daa351aa91a1511674b94bced0a9c2eaa817770ea"

_SCHEMA = "schemas/baseline-inventory.schema.json"
_OBSERVATION_SCHEMA = "schemas/baseline-observation.schema.json"
_EVIDENCE_SCHEMA = "schemas/baseline-evidence.schema.json"
_STATE_SCHEMA = "schemas/baseline-state.schema.json"
_LIMIT_SCHEMA = "schemas/baseline-limit.schema.json"
_IDENTITY_SCHEMA = "schemas/baseline-identity.schema.json"
_DISPOSITION_SCHEMA = "schemas/baseline-disposition.schema.json"
_RECORD_SCHEMA = "schemas/baseline-record.schema.json"
_RELEASE_ACCOUNTING_SCHEMA = "schemas/baseline-release-accounting.schema.json"
_REVIEW_SCHEMA = "schemas/baseline-review.schema.json"
_HISTORY_SCHEMA = "schemas/baseline-history.schema.json"
_CHANGE_SCHEMA = "schemas/baseline-change.schema.json"
_CURRENT_OBSERVATION_SCHEMA = "schemas/current-observation.schema.json"
_CURRENT_EVIDENCE_SCHEMA = "schemas/current-evidence.schema.json"
_CURRENT_DIFFERENCE_SCHEMA = "schemas/current-difference.schema.json"
_CURRENT_CAUSE_SCHEMA = "schemas/current-cause.schema.json"
_CURRENT_COMMENCEMENT_SCHEMA = "schemas/current-commencement.schema.json"
_CURRENT_CESSATION_SCHEMA = "schemas/current-cessation.schema.json"
_CURRENT_PUBLICATION_SCHEMA = "schemas/current-publication.schema.json"
_CURRENT_TEXT_EVENT_SCHEMA = "schemas/current-text-event.schema.json"
_CURRENT_EVENT_SCHEMA = "schemas/current-event.schema.json"
_CURRENT_DISPOSITION_SCHEMA = "schemas/current-disposition.schema.json"
_CURRENT_RECORD_SCHEMA = "schemas/current-record.schema.json"
_CURRENT_RELEASE_SCHEMA = "schemas/current-release-accounting.schema.json"
_RECONSTRUCTION_PLAN_SEMANTIC_SCHEMA = "schemas/reconstruction-plan-semantic.schema.json"
_RECONSTRUCTION_PLAN_SCHEMA = "schemas/reconstruction-plan-validation.schema.json"
_MAX_BYTES = 2_000_000
_SCOPE_BY_NATURE = {
    "ORDINANCE": HK_ORDINANCES_SCOPE_ID,
    "SUBSIDIARY_LEGISLATION": HK_SUBSIDIARY_SCOPE_ID,
    "CONSTITUTIONAL_OR_OTHER_INSTRUMENT": HK_CONSTITUTIONAL_SCOPE_ID,
}
_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_INVENTORY_ACCOUNTED",
        "HKLEG_BASE_INVENTORY_OBJECT_OR_RESOURCE_UNACCOUNTED",
        "HKLEG_BASE_INVENTORY_OWNERSHIP_AMBIGUOUS",
        "HKLEG_BASE_INVENTORY_SCOPE_MISASSIGNED",
    }
)
_OBSERVATION_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_OBSERVATION_FROZEN",
        "HKLEG_BASE_OBSERVATION_REQUIRED_SOURCE_UNAVAILABLE",
        "HKLEG_BASE_OBSERVATION_CUTOFF_MIXED",
        "HKLEG_BASE_OBSERVATION_LOCK_MISMATCH",
        "HKLEG_BASE_OBSERVATION_POST_CUTOFF_CHANGE",
    }
)
_REQUIRED_OBSERVATION_SOURCES = frozenset({HK_CURRENT_INVENTORY_SOURCE_ID, HK_GAZETTE_SOURCE_ID})
_EVIDENCE_SOURCE_IDS = frozenset(
    {
        HK_CURRENT_DATA_SOURCE_ID,
        HK_VERIFIED_COPIES_SOURCE_ID,
        HK_ASSISTED_COPIES_SOURCE_ID,
        HK_PAST_DATA_SOURCE_ID,
    }
)
_EVIDENCE_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_EVIDENCE_RECONCILED",
        "HKLEG_BASE_EVIDENCE_REQUIRED_ARTIFACT_MISSING",
        "HKLEG_BASE_EVIDENCE_VERSION_OR_CONTENT_CONFLICT",
        "HKLEG_BASE_EVIDENCE_HISTORICAL_SUBSTITUTION_FORBIDDEN",
    }
)
_REQUIRED_EVIDENCE_ROLES = frozenset(
    {"EN_CURRENT_XML", "ZH_HANT_CURRENT_XML", "EN_OFFICIAL_COPY", "ZH_HANT_OFFICIAL_COPY"}
)
_STATE_SOURCE_IDS = frozenset(
    {
        HK_CURRENT_INVENTORY_SOURCE_ID,
        HK_CURRENT_DATA_SOURCE_ID,
        HK_GAZETTE_SOURCE_ID,
        HK_EDITORIAL_RECORDS_SOURCE_ID,
        HK_PUBLICATION_SPECIFICATIONS_SOURCE_ID,
        HK_BASIC_LAW_PORTAL_SOURCE_ID,
        HK_NPC_NATIONAL_LAWS_SOURCE_ID,
        HK_NPCSC_MATERIALS_SOURCE_ID,
    }
)
_STATE_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_STATE_PRESENT_OPERATIVE_ESTABLISHED",
        "HKLEG_BASE_STATE_REQUIRED_SIGNAL_MISSING",
        "HKLEG_BASE_STATE_STATUS_OR_STRUCTURE_AMBIGUOUS",
        "HKLEG_BASE_STATE_ACCEPTED_SIGNAL_CONFLICT",
        "HKLEG_BASE_STATE_SOURCE_SEMANTICS_UNKNOWN",
        "HKLEG_BASE_STATE_OPERATIVE_EFFECT_NOT_PROVED",
        "HKLEG_BASE_STATE_RULEBOOK_SUPPORT_MISSING",
    }
)
_LIMIT_ASSERTION_CODES = frozenset(
    {
        "HISTORICAL_LEGAL_EVENT",
        "HISTORICAL_EFFECTIVE_DATE",
        "IDENTITY_OR_CONTINUITY_RELATIONSHIP",
        "COMPLETE_HISTORICAL_EVENT_CHAIN",
    }
)
_LIMIT_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_LIMIT_PRESENT_STATE_ONLY",
        "HKLEG_BASE_LIMIT_HISTORICAL_EVENT_FORBIDDEN",
        "HKLEG_BASE_LIMIT_EFFECTIVE_DATE_FORBIDDEN",
        "HKLEG_BASE_LIMIT_CONTINUITY_FORBIDDEN",
        "HKLEG_BASE_LIMIT_COMPLETE_HISTORY_FORBIDDEN",
    }
)
_IDENTITY_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_ID_GREENFIELD_ALLOCATION_REQUESTED",
        "HKLEG_BASE_ID_NON_REGISTER_IDENTITY_FORBIDDEN",
        "HKLEG_BASE_ID_UNPROVED_RELATIONSHIP_FORBIDDEN",
        "HKLEG_BASE_ID_DUPLICATE_OR_CONTINUITY_AMBIGUOUS",
    }
)
_IDENTITY_LAYERS = ("LEGAL_ITEM", "OFFICIAL_VERSION", "LEGAL_LOCATION", "SEARCH_RECORD")
_DISPOSITION_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_DISP_SEARCHABLE_CURRENT_SUPPORTED",
        "HKLEG_BASE_DISP_WAITING_ROOM_SUPPORTED",
        "HKLEG_BASE_DISP_EVIDENCE_ONLY_SUPPORTED",
        "HKLEG_BASE_DISP_HISTORICAL_SUPPORTED",
        "HKLEG_BASE_DISP_QUARANTINE_REQUIRED",
        "HKLEG_BASE_DISP_CURRENT_CONSOLIDATION_GAP",
        "HKLEG_BASE_DISP_SINGLE_SIGNAL_INSUFFICIENT",
    }
)
_PRIMARY_DISPOSITIONS = (
    "SEARCHABLE_CURRENT",
    "WAITING_ROOM",
    "EVIDENCE_ONLY",
    "HISTORICAL",
    "QUARANTINE",
)
_RECORD_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_REC_CANDIDATE_CREATED",
        "HKLEG_BASE_REC_NON_SEARCHABLE_EXCLUDED",
        "HKLEG_BASE_REC_LEGACY_ID_FORBIDDEN",
        "HKLEG_BASE_REC_BILINGUAL_CONTENT_INCOMPLETE",
        "HKLEG_BASE_REC_RENDERING_NON_CANONICAL",
        "HKLEG_BASE_REC_AUTHORITY_NOTE_UNAPPROVED",
    }
)
_SYNTHETIC_RECORD_PROFILE = {
    "country": "Hong Kong",
    "jurisdiction": "Hong Kong",
    "type": "Legislation",
    "source": "HKeL",
}
_RELEASE_ACCOUNTING_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_REL_INITIAL_RELEASE_ACCOUNTED",
        "HKLEG_BASE_REL_OBJECT_OR_LOCATION_UNACCOUNTED",
        "HKLEG_BASE_REL_RESULT_ACCOUNTING_INCONSISTENT",
        "HKLEG_BASE_REL_PREDECESSOR_FORBIDDEN",
        "HKLEG_BASE_REL_REFERENCE_UNACCOUNTED",
        "HKLEG_BASE_REL_COMPLETENESS_UNRESOLVED",
    }
)
_REVIEW_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_REVIEW_TARGETED_INVESTIGATION_OPENED",
        "HKLEG_BASE_REVIEW_NO_MATERIAL_UNCERTAINTY",
        "HKLEG_BASE_REVIEW_BROAD_HISTORY_FORBIDDEN",
        "HKLEG_BASE_REVIEW_SOURCE_NOT_PERMITTED",
        "HKLEG_BASE_REVIEW_FACT_SCOPE_MISMATCH",
    }
)
_REVIEW_SOURCE_IDS = frozenset(
    {
        "HK-LEG-HKEL-PAST-INVENTORY",
        HK_PAST_DATA_SOURCE_ID,
        "HK-LEG-OFFICIAL-GAZETTE-ARCHIVE",
        "HK-LEG-HKEL-GAZETTE-BACKCAPTURE",
    }
)
_REVIEW_FACT_BY_TRIGGER = {
    "POSSIBLE_DUPLICATE_OR_CONTINUITY": "IDENTITY_OR_CONTINUITY",
    "PARTIAL_OR_UNCLEAR_PRESENT_STATUS": "PRESENT_OPERATIVE_STATUS",
    "UNPROVED_OWNERSHIP_REPLACEMENT_OR_CESSATION": "OWNERSHIP_REPLACEMENT_OR_CESSATION",
    "ACCEPTED_SOURCE_CONFLICT": "SOURCE_CONFLICT_RESOLUTION",
    "RULEBOOK_REQUIRES_EARLIER_ARTIFACT": "EARLIER_ARTIFACT_FACT",
}
_HISTORY_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_HIST_PERMITTED_FACT_ESTABLISHED",
        "HKLEG_BASE_HIST_CURRENT_EVIDENCE_SUBSTITUTION_FORBIDDEN",
        "HKLEG_BASE_HIST_SIMILARITY_ONLY_FORBIDDEN",
        "HKLEG_BASE_HIST_REQUESTED_EVIDENCE_UNAVAILABLE",
        "HKLEG_BASE_HIST_EVIDENCE_CONFLICT",
        "HKLEG_BASE_HIST_EVIDENCE_INSUFFICIENT",
    }
)
_HISTORY_DISCOVERY_ONLY_SOURCES = frozenset(
    {"HK-LEG-HKEL-PAST-INVENTORY", "HK-LEG-HKEL-GAZETTE-BACKCAPTURE"}
)
_CHANGE_REASON_CODES = frozenset(
    {
        "HKLEG_BASE_CHANGE_NO_POST_CUTOFF_CHANGE",
        "HKLEG_BASE_CHANGE_REFREEZE_SELECTED",
        "HKLEG_BASE_CHANGE_FINISH_THEN_UPDATE_SELECTED",
        "HKLEG_BASE_CHANGE_FROZEN_PACKAGE_NOT_PRESERVED",
        "HKLEG_BASE_CHANGE_NEW_OBSERVATION_NOT_SEPARATE",
        "HKLEG_BASE_CHANGE_MIXED_CUTOFF_FORBIDDEN",
        "HKLEG_BASE_CHANGE_LATER_CURRENCY_CLAIM_FORBIDDEN",
    }
)
_CURRENT_OBSERVATION_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_OBS_SUPPORTED_NO_CHANGE",
        "HKLEG_CURRENT_OBS_AFFECTED_WORK_OPENED",
        "HKLEG_CURRENT_OBS_AFFECTED_WORK_DEDUPLICATED",
        "HKLEG_CURRENT_OBS_RELEASE_BLOCKING_OBSERVATION_UNAVAILABLE",
        "HKLEG_CURRENT_OBS_AFFECTED_WORK_OBSERVATION_UNAVAILABLE",
    }
)
_CURRENT_EVIDENCE_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_EVID_COMPLETE_VERIFIED_BUNDLE",
        "HKLEG_CURRENT_EVID_COMPLETE_ASSISTED_BUNDLE",
        "HKLEG_CURRENT_EVID_VERIFIED_PREFERRED_SAME_VERSION",
        "HKLEG_CURRENT_EVID_COPY_SOURCE_NOT_ADMITTED",
        "HKLEG_CURRENT_EVID_AFFECTED_EVIDENCE_UNAVAILABLE",
        "HKLEG_CURRENT_EVID_BILINGUAL_VERSION_CONFLICT",
        "HKLEG_CURRENT_EVID_XML_COPY_CONFLICT",
        "HKLEG_CURRENT_EVID_STRUCTURE_OR_IDENTITY_CONFLICT",
    }
)
_CURRENT_DIFFERENCE_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_DIFF_OBSERVABLE_DIFFERENCE_CLASSIFIED",
        "HKLEG_CURRENT_DIFF_EXACT_UNCHANGED_REUSE_ELIGIBLE",
        "HKLEG_CURRENT_DIFF_CONTINUING_SUPPORT_NOT_PROVED",
        "HKLEG_CURRENT_DIFF_INITIAL_BASELINE_REQUIRED",
    }
)
_CURRENT_CAUSE_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_CAUSE_GAZETTE_EVENT_PROVED",
        "HKLEG_CURRENT_CAUSE_EDITORIAL_RECORD_PROVED",
        "HKLEG_CURRENT_CAUSE_TECHNICAL_REPUBLICATION_PROVED",
        "HKLEG_CURRENT_CAUSE_SOURCE_CONTRACT_REVIEW_REQUIRED",
        "HKLEG_CURRENT_CAUSE_ACCEPTED_CAUSE_UNAVAILABLE",
        "HKLEG_CURRENT_CAUSE_EVIDENCE_CONFLICT",
    }
)
_CURRENT_COMMENCEMENT_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_COMMENCEMENT_DEFAULT_OPERATIVE_PROVED",
        "HKLEG_CURRENT_COMMENCEMENT_FIXED_DATE_OPERATIVE_PROVED",
        "HKLEG_CURRENT_COMMENCEMENT_FIXED_DATE_PENDING",
        "HKLEG_CURRENT_COMMENCEMENT_APPOINTED_DATE_OPERATIVE_PROVED",
        "HKLEG_CURRENT_COMMENCEMENT_APPOINTED_DATE_PENDING",
        "HKLEG_CURRENT_COMMENCEMENT_CONDITIONAL_EVENT_OPERATIVE_PROVED",
        "HKLEG_CURRENT_COMMENCEMENT_CONDITIONAL_EVENT_PENDING",
        "HKLEG_CURRENT_COMMENCEMENT_PARTIAL_OPERATIVE_PROVED",
        "HKLEG_CURRENT_COMMENCEMENT_PARTIAL_PENDING",
        "HKLEG_CURRENT_COMMENCEMENT_EVIDENCE_INCOMPLETE",
        "HKLEG_CURRENT_COMMENCEMENT_EVIDENCE_CONFLICT",
        "HKLEG_CURRENT_COMMENCEMENT_AFFECTED_SET_INVALID",
    }
)
_CURRENT_CESSATION_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_CESSATION_REPEAL_OPERATIVE_PROVED",
        "HKLEG_CURRENT_CESSATION_REPEAL_PENDING",
        "HKLEG_CURRENT_CESSATION_REVOCATION_OPERATIVE_PROVED",
        "HKLEG_CURRENT_CESSATION_REVOCATION_PENDING",
        "HKLEG_CURRENT_CESSATION_EXPIRY_OPERATIVE_PROVED",
        "HKLEG_CURRENT_CESSATION_EXPIRY_PENDING",
        "HKLEG_CURRENT_CESSATION_REVIVAL_OPERATIVE_PROVED",
        "HKLEG_CURRENT_CESSATION_REVIVAL_PENDING",
        "HKLEG_CURRENT_CESSATION_REVIVAL_CONTINUITY_UNPROVED",
        "HKLEG_CURRENT_CESSATION_EVIDENCE_INCOMPLETE",
        "HKLEG_CURRENT_CESSATION_EVIDENCE_CONFLICT",
        "HKLEG_CURRENT_CESSATION_AFFECTED_STATE_INVALID",
    }
)
_CURRENT_PUBLICATION_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_PUBLICATION_ORDINANCE_ENACTMENT_PROVED",
        "HKLEG_CURRENT_PUBLICATION_SUBSIDIARY_LEGISLATION_PROVED",
        "HKLEG_CURRENT_PUBLICATION_NOTICE_PROVED",
        "HKLEG_CURRENT_PUBLICATION_LEGAL_SUPPLEMENT_3_INVENTORY_ONLY",
        "HKLEG_CURRENT_PUBLICATION_OTHER_SUPPLEMENT_DISCOVERY_ONLY",
        "HKLEG_CURRENT_PUBLICATION_EVIDENCE_INCOMPLETE",
        "HKLEG_CURRENT_PUBLICATION_BILINGUAL_EVIDENCE_INCOMPLETE",
        "HKLEG_CURRENT_PUBLICATION_SOURCE_CLASS_CONFLICT",
        "HKLEG_CURRENT_PUBLICATION_AFTER_CUTOFF",
        "HKLEG_CURRENT_PUBLICATION_EVIDENCE_CONFLICT",
    }
)
_CURRENT_TEXT_EVENT_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_TEXT_EVENT_AMENDMENT_CURRENT_BUNDLE_AVAILABLE",
        "HKLEG_CURRENT_TEXT_EVENT_AMENDMENT_CONSOLIDATION_MISSING",
        "HKLEG_CURRENT_TEXT_EVENT_AMENDMENT_PENDING",
        "HKLEG_CURRENT_TEXT_EVENT_EXPRESS_CORRECTION_CURRENT_BUNDLE_AVAILABLE",
        "HKLEG_CURRENT_TEXT_EVENT_EXPRESS_CORRECTION_CONSOLIDATION_MISSING",
        "HKLEG_CURRENT_TEXT_EVENT_EXPRESS_CORRECTION_PENDING",
        "HKLEG_CURRENT_TEXT_EVENT_EDITORIAL_CURRENT_BUNDLE_AVAILABLE",
        "HKLEG_CURRENT_TEXT_EVENT_EDITORIAL_CONSOLIDATION_MISSING",
        "HKLEG_CURRENT_TEXT_EVENT_EDITORIAL_PENDING",
        "HKLEG_CURRENT_TEXT_EVENT_EVIDENCE_INCOMPLETE",
        "HKLEG_CURRENT_TEXT_EVENT_OPERATION_MAPPING_INCOMPLETE",
        "HKLEG_CURRENT_TEXT_EVENT_BILINGUAL_OPERATION_CONFLICT",
        "HKLEG_CURRENT_TEXT_EVENT_RESULTING_TEXT_CONFLICT",
        "HKLEG_CURRENT_TEXT_EVENT_EVIDENCE_CONFLICT",
        "HKLEG_CURRENT_TEXT_EVENT_AFFECTED_SET_INVALID",
    }
)
_CURRENT_EVENT_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_EVENT_PROVED_CONSOLIDATION_MISSING",
        "HKLEG_CURRENT_EVENT_CURRENT_CONSOLIDATION_AVAILABLE",
        "HKLEG_CURRENT_EVENT_EVIDENCE_INCOMPLETE",
        "HKLEG_CURRENT_EVENT_EVIDENCE_CONFLICT",
        "HKLEG_CURRENT_EVENT_AFFECTED_SET_UNBOUNDED",
    }
)
_CURRENT_DISPOSITION_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_DISP_SEARCHABLE_CURRENT_SUPPORTED",
        "HKLEG_CURRENT_DISP_WAITING_ROOM_SUPPORTED",
        "HKLEG_CURRENT_DISP_EVIDENCE_ONLY_SUPPORTED",
        "HKLEG_CURRENT_DISP_HISTORICAL_SUPPORTED",
        "HKLEG_CURRENT_DISP_QUARANTINE_REQUIRED",
        "HKLEG_CURRENT_DISP_UPSTREAM_BLOCKED",
        "HKLEG_CURRENT_DISP_SINGLE_SIGNAL_INSUFFICIENT",
    }
)
_CURRENT_RECORD_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_REC_EXACT_RECORD_REUSED",
        "HKLEG_CURRENT_REC_CHANGED_RECORD_CREATED",
        "HKLEG_CURRENT_REC_NON_SEARCHABLE_EXCLUDED",
        "HKLEG_CURRENT_REC_CONTINUING_SUPPORT_MISSING",
        "HKLEG_CURRENT_REC_PREDECESSOR_REQUIRED",
        "HKLEG_CURRENT_REC_EXACT_REUSE_REQUIRED",
        "HKLEG_CURRENT_REC_IMMUTABLE_ID_MUTATION",
        "HKLEG_CURRENT_REC_NEW_ID_REQUIRED",
    }
)
_CURRENT_RELEASE_REASON_CODES = frozenset(
    {
        "HKLEG_CURRENT_REL_RELEASE_ACCOUNTED",
        "HKLEG_CURRENT_REL_PREDECESSOR_REQUIRED",
        "HKLEG_CURRENT_REL_REFERENCE_UNACCOUNTED",
        "HKLEG_CURRENT_REL_DUPLICATE_LOCATION",
        "HKLEG_CURRENT_REL_RESULT_ACCOUNTING_INCONSISTENT",
        "HKLEG_CURRENT_REL_COMPLETENESS_UNRESOLVED",
    }
)
_RECONSTRUCTION_PLAN_SEMANTIC_REASON_CODES = frozenset(
    {
        "HKLEG_RECON_PLAN_SEMANTIC_CANDIDATE_CONFIRMED",
        "HKLEG_RECON_PLAN_SEMANTIC_PROFILE_NOT_ADMITTED",
        "HKLEG_RECON_PLAN_SEMANTIC_DECISION_RESULT_MISSING",
        "HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_RESULT_MISSING",
        "HKLEG_RECON_PLAN_SEMANTIC_DECISION_CONTRACT_INVALID",
        "HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_CONTRACT_INVALID",
        "HKLEG_RECON_PLAN_SEMANTIC_EVIDENCE_BINDING_INCOMPLETE",
        "HKLEG_RECON_PLAN_SEMANTIC_UNSUPPORTED_OPERATION",
        "HKLEG_RECON_PLAN_SEMANTIC_FINAL_TEXT_OVERREACH",
        "HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_OBJECTION",
        "HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_UNRESOLVED",
        "HKLEG_RECON_PLAN_SEMANTIC_RESULT_CONFLICT",
        "HKLEG_RECON_PLAN_SEMANTIC_DETERMINISTIC_PRECHECK_FAILED",
    }
)
_RECONSTRUCTION_PLAN_REASON_CODES = frozenset(
    {
        "HKLEG_RECON_PLAN_VALIDATED",
        "HKLEG_RECON_PLAN_CANDIDATE_MISSING",
        "HKLEG_RECON_PLAN_CONTRACT_INVALID",
        "HKLEG_RECON_PLAN_UNKNOWN_OPERATION",
        "HKLEG_RECON_PLAN_SEMANTIC_CANDIDATE_MISMATCH",
        "HKLEG_RECON_PLAN_LEGAL_DESK_DECISION_NOT_ACCEPTED",
        "HKLEG_RECON_PLAN_BASE_NOT_LATEST_ELIGIBLE",
        "HKLEG_RECON_PLAN_CHAIN_INCOMPLETE",
        "HKLEG_RECON_PLAN_EVENT_ORDER_UNRESOLVED",
        "HKLEG_RECON_PLAN_APPLICABILITY_UNRESOLVED",
        "HKLEG_RECON_PLAN_DEPENDENCY_CLOSURE_INCOMPLETE",
        "HKLEG_RECON_PLAN_OVERLAP",
        "HKLEG_RECON_PLAN_SOURCE_UNIT_OWNERSHIP_INCOMPLETE",
        "HKLEG_RECON_PLAN_LANGUAGE_EVIDENCE_INCOMPLETE",
        "HKLEG_RECON_PLAN_BILINGUAL_RESULT_MISMATCH",
        "HKLEG_RECON_PLAN_OPERATION_INVENTORY_INVALID",
        "HKLEG_RECON_PLAN_OPERATION_EVENT_BINDING_INCOMPLETE",
        "HKLEG_RECON_PLAN_ATOMIC_GROUP_INCOMPLETE",
        "HKLEG_RECON_PLAN_UNDECLARED_INPUT",
        "HKLEG_RECON_PLAN_DETERMINISTIC_REVALIDATION_FAILED",
    }
)
_RECONSTRUCTION_OPERATION_IDS = frozenset(f"HKRECON-OP-{index:03d}" for index in range(1, 9))
_RECONSTRUCTION_SELECTOR_BY_OPERATION = {
    "HKRECON-OP-001": "EXACT_TEXT_RANGE",
    "HKRECON-OP-002": "CLOSED_SCOPE_OCCURRENCES",
    "HKRECON-OP-003": "PARENT_ORDER_POSITION",
    "HKRECON-OP-004": "COMPLETE_NODE",
    "HKRECON-OP-005": "COMPLETE_NODE",
    "HKRECON-OP-006": "COMPLETE_NODE",
    "HKRECON-OP-007": "NEW_PARENT_ORDER",
    "HKRECON-OP-008": "CLOSED_STRUCTURED_REGION",
}
_AUTHENTIC_LANGUAGE_COUNT = 2
_EXPECTED_OBSERVATION_LOCKS = {
    "rulebook_version": "2026-08-17.1",
    "rulebook_fingerprint": "sha256:" + "a" * 64,
    "release_scope_registry_fingerprint": "sha256:" + "b" * 64,
    "publication_specification_version": "SYNTHETIC_HKEL_SPEC_1",
    "publication_specification_fingerprint": "sha256:" + "c" * 64,
}


@dataclass(frozen=True, slots=True)
class BaselineInventoryDecision:
    """One deterministic, disposition-neutral inventory checkpoint decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_codes: tuple[str, ...]
    accounted_object_ids: tuple[str, ...]
    unresolved_object_ids: tuple[str, ...]
    affected_scope_ids: tuple[str, ...]
    scope_inventory_results: tuple[tuple[str, Literal["COMPLETE", "INCOMPLETE"]], ...]

    def document(self) -> dict[str, JsonValue]:
        """Return the strict decision-contract representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_INVENTORY_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": list(self.reason_codes),
            "rule_trace": [HK_BASELINE_INVENTORY_RULE_ID],
            "accounted_object_ids": list(self.accounted_object_ids),
            "unresolved_object_ids": list(self.unresolved_object_ids),
            "affected_scope_ids": list(self.affected_scope_ids),
            "scope_inventory_results": [
                {"scope_id": scope_id, "result": result}
                for scope_id, result in self.scope_inventory_results
            ],
            "record_output": "NONE",
        }


@dataclass(frozen=True, slots=True)
class BaselineObservationDecision:
    """One deterministic freeze-or-block decision for a synthetic baseline cutoff."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    frozen_cutoff: str | None
    frozen_source_observation_ids: tuple[str, ...]
    unresolved_source_ids: tuple[str, ...]
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict observation-decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_OBSERVATION_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_OBSERVATION_RULE_ID],
            "frozen_cutoff": self.frozen_cutoff,
            "frozen_source_observation_ids": list(self.frozen_source_observation_ids),
            "unresolved_source_ids": list(self.unresolved_source_ids),
            "affected_scope_ids": checked_json_value(
                sorted(_SCOPE_BY_NATURE.values(), key=str.encode)
            ),
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineEvidenceDecision:
    """One deterministic bilingual current-evidence gate decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    evidence_mode: Literal["VERIFIED", "ASSISTED", "MIXED", "NONE"]
    accepted_artifact_ids: tuple[str, ...]
    unresolved_evidence_roles: tuple[str, ...]
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict evidence-decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_EVIDENCE_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_EVIDENCE_RULE_ID],
            "evidence_mode": self.evidence_mode,
            "accepted_artifact_ids": list(self.accepted_artifact_ids),
            "unresolved_evidence_roles": list(self.unresolved_evidence_roles),
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineStateDecision:
    """One deterministic present-operative-state checkpoint decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    source_contract_review_required: bool
    reason_code: str
    present_state: Literal["OPERATIVE_CURRENT", "UNRESOLVED"]
    historical_assertion_scope: Literal["PENDING_LIMIT_RULE", "NONE"]
    conflicting_source_ids: tuple[str, ...]
    unresolved_source_ids: tuple[str, ...]
    unresolved_fact_codes: tuple[str, ...]
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict present-state decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_STATE_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": self.source_contract_review_required,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_STATE_RULE_ID],
            "present_state": self.present_state,
            "historical_assertion_scope": self.historical_assertion_scope,
            "conflicting_source_ids": list(self.conflicting_source_ids),
            "unresolved_source_ids": list(self.unresolved_source_ids),
            "unresolved_fact_codes": list(self.unresolved_fact_codes),
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineLimitDecision:
    """One deterministic guard against unsupported historical assertions."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK"]
    reason_code: str
    historical_assertion_scope: Literal["PRESENT_STATE_ONLY", "NONE"]
    rejected_assertion_codes: tuple[str, ...]
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict assertion-limit decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_LIMIT_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_LIMIT_RULE_ID],
            "historical_assertion_scope": self.historical_assertion_scope,
            "rejected_assertion_codes": list(self.rejected_assertion_codes),
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineIdentityDecision:
    """One deterministic request for register-owned greenfield identities."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    reason_code: str
    identity_layers: tuple[str, ...]
    preserved_aliases: tuple[tuple[str, str], ...]
    rejected_relationship_codes: tuple[str, ...]
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict identity-decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_IDENTITY_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_IDENTITY_RULE_ID],
            "identity_effects": [
                {"identity_layer": layer, "action": "ALLOCATE_NEW_OPAQUE"}
                for layer in self.identity_layers
            ],
            "preserved_aliases": [
                {"alias_type": alias_type, "value": value}
                for alias_type, value in self.preserved_aliases
            ],
            "rejected_relationship_codes": list(self.rejected_relationship_codes),
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineDispositionDecision:
    """One exact primary-disposition decision or explicit blocked result."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: str
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict disposition-decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_DISPOSITION_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_DISPOSITION_RULE_ID],
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineRecordDecision:
    """One exact candidate-serving-record construction decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: str
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    candidate_record: dict[str, JsonValue] | None
    serving_payload_fingerprint: str | None
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict candidate-record decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_RECORD_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_RECORD_RULE_ID],
            "candidate_record": self.candidate_record,
            "serving_payload_fingerprint": self.serving_payload_fingerprint,
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "CANDIDATE" if self.candidate_record is not None else "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineReleaseAccountingDecision:
    """One complete-accounting decision for an initial baseline release."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    accounted_object_ids: tuple[str, ...]
    accounted_location_ids: tuple[str, ...]
    unresolved_ids: tuple[str, ...]
    release_accounting_fingerprint: str | None
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict initial-release-accounting decision."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_RELEASE_ACCOUNTING_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_RELEASE_ACCOUNTING_RULE_ID],
            "initial_baseline": True,
            "predecessor_release_id": None,
            "accounted_object_ids": list(self.accounted_object_ids),
            "accounted_location_ids": list(self.accounted_location_ids),
            "unresolved_ids": list(self.unresolved_ids),
            "release_accounting_fingerprint": self.release_accounting_fingerprint,
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineReviewDecision:
    """One bounded targeted-review opening decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK"]
    reason_code: str
    review_task: dict[str, JsonValue] | None
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict targeted-review decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_REVIEW_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_REVIEW_RULE_ID],
            "review_task": self.review_task,
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineHistoryDecision:
    """One fact-bounded historical-evidence decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    established_fact_code: str | None
    affected_object_ids: tuple[str, ...]
    unaffected_work_may_continue: bool
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict bounded-history decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_HISTORY_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_HISTORY_RULE_ID],
            "established_fact_code": self.established_fact_code,
            "affected_object_ids": list(self.affected_object_ids),
            "unaffected_work_may_continue": self.unaffected_work_may_continue,
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class BaselineChangeDecision:
    """One post-cutoff change decision for an open frozen baseline."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK"]
    reason_code: str
    baseline_action: str
    preserved_cutoff: str | None
    new_observation_status: str
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict post-cutoff change decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_BASELINE_CHANGE_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_BASELINE_CHANGE_RULE_ID],
            "baseline_action": self.baseline_action,
            "preserved_cutoff": self.preserved_cutoff,
            "new_observation_status": self.new_observation_status,
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class CurrentObservationDecision:
    """One ordinary-update observation routing decision."""

    fixture_id: str
    rule_id: str
    processing_outcome: Literal["PASS", "BLOCK"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    workflow_result: str
    affected_object_ids: tuple[str, ...]
    work_deduplication: str
    release_choice_required: bool
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict current-observation decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": self.rule_id,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [self.rule_id],
            "workflow_result": self.workflow_result,
            "affected_object_ids": list(self.affected_object_ids),
            "work_deduplication": self.work_deduplication,
            "reuse_existing_corpus_release": self.rule_id == HK_CURRENT_OBSERVATION_RULE_IDS[0],
            "release_choice_required": self.release_choice_required,
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class CurrentEvidenceDecision:
    """One ordinary-update bilingual evidence decision."""

    fixture_id: str
    rule_trace: tuple[str, ...]
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    evidence_class: str | None
    selected_version: str | None
    affected_object_ids: tuple[str, ...]
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict current-evidence decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": self.rule_trace[-1],
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": list(self.rule_trace),
            "evidence_class": self.evidence_class,
            "selected_version": self.selected_version,
            "affected_object_ids": list(self.affected_object_ids),
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class CurrentDifferenceDecision:
    """One observable ordinary-update bundle-difference decision."""

    fixture_id: str
    rule_id: str
    processing_outcome: Literal["PASS", "BLOCK"]
    reason_code: str
    difference_class: str | None
    record_selection: str
    identity_or_status_inference: Literal["NONE"]
    affected_object_id: str
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict current-difference decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": self.rule_id,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [self.rule_id],
            "difference_class": self.difference_class,
            "record_selection": self.record_selection,
            "identity_or_status_inference": self.identity_or_status_inference,
            "affected_object_ids": [self.affected_object_id],
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class CurrentCauseDecision:
    """One evidence-bound ordinary-update change-cause decision."""

    fixture_id: str
    rule_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    reason_code: str
    cause_class: str | None
    source_contract_review_required: bool
    affected_object_id: str
    affected_scope_id: str
    affected_location_ids: tuple[str, ...]
    publication_date: str | None
    effective_date: str | None
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict current-cause decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": self.rule_id,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": "NONE",
            "source_contract_review_required": self.source_contract_review_required,
            "reason_codes": [self.reason_code],
            "rule_trace": [self.rule_id],
            "cause_class": self.cause_class,
            "affected_object_ids": [self.affected_object_id],
            "affected_scope_ids": [self.affected_scope_id],
            "affected_location_ids": list(self.affected_location_ids),
            "publication_date": self.publication_date,
            "effective_date": self.effective_date,
            "identity_or_status_inference": "NONE",
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class CurrentCommencementDecision:
    """One evidence-bound commencement and operative-location decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "WAITING_ROOM", "QUARANTINE"]
    reason_code: str
    event_fact_output: Literal["NONE", "LEGAL_STATUS_EVENT"]
    commencement_mode: str
    operative_state: Literal["OPERATIVE", "NOT_YET_OPERATIVE", "PARTIALLY_OPERATIVE", "UNRESOLVED"]
    affected_object_id: str
    affected_scope_id: str
    publication_date: str | None
    effective_date: str | None
    operative_provision_fingerprint: str
    event_evidence_fingerprints: tuple[str, ...]
    event_operative_at_cutoff: bool | None
    affected_location_ids: tuple[str, ...]
    operative_location_ids: tuple[str, ...]
    pending_location_ids: tuple[str, ...]
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict current-commencement decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_CURRENT_COMMENCEMENT_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_CURRENT_COMMENCEMENT_RULE_ID],
            "event_fact_output": self.event_fact_output,
            "commencement_mode": self.commencement_mode,
            "operative_state": self.operative_state,
            "affected_object_ids": [self.affected_object_id],
            "affected_scope_ids": [self.affected_scope_id],
            "publication_date": self.publication_date,
            "effective_date": self.effective_date,
            "operative_provision_fingerprint": self.operative_provision_fingerprint,
            "event_evidence_fingerprints": list(self.event_evidence_fingerprints),
            "event_operative_at_cutoff": self.event_operative_at_cutoff,
            "affected_location_ids": list(self.affected_location_ids),
            "operative_location_ids": list(self.operative_location_ids),
            "pending_location_ids": list(self.pending_location_ids),
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class _CurrentCommencementContext:
    fixture_id: str
    cutoff: str
    commencement_mode: str
    controlling_notice_state: str
    event_evidence_complete: bool
    event_evidence_authentic: bool
    event_evidence_conflicts: bool
    condition_exact: bool
    condition_satisfied_at_cutoff: bool
    affected_object_id: str
    affected_scope_id: str
    publication_date: str | None
    effective_date: str | None
    operative_provision_fingerprint: str
    event_evidence_fingerprints: tuple[str, ...]
    all_location_ids: tuple[str, ...]
    affected_location_ids: tuple[str, ...]
    pre_event_operative_location_ids: tuple[str, ...]
    affected_location_scope: str


@dataclass(frozen=True, slots=True)
class _CurrentCommencementResult:
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "WAITING_ROOM", "QUARANTINE"]
    reason_code: str
    event_fact_output: Literal["NONE", "LEGAL_STATUS_EVENT"]
    operative_state: Literal["OPERATIVE", "NOT_YET_OPERATIVE", "PARTIALLY_OPERATIVE", "UNRESOLVED"]
    event_operative_at_cutoff: bool | None
    operative_location_ids: tuple[str, ...]
    pending_location_ids: tuple[str, ...]
    next_action: str


def _current_commencement_decision(
    context: _CurrentCommencementContext,
    result: _CurrentCommencementResult,
) -> CurrentCommencementDecision:
    return CurrentCommencementDecision(
        fixture_id=context.fixture_id,
        processing_outcome=result.processing_outcome,
        legal_disposition=result.legal_disposition,
        reason_code=result.reason_code,
        event_fact_output=result.event_fact_output,
        commencement_mode=context.commencement_mode,
        operative_state=result.operative_state,
        affected_object_id=context.affected_object_id,
        affected_scope_id=context.affected_scope_id,
        publication_date=context.publication_date,
        effective_date=context.effective_date,
        operative_provision_fingerprint=context.operative_provision_fingerprint,
        event_evidence_fingerprints=context.event_evidence_fingerprints,
        event_operative_at_cutoff=result.event_operative_at_cutoff,
        affected_location_ids=context.affected_location_ids,
        operative_location_ids=result.operative_location_ids,
        pending_location_ids=result.pending_location_ids,
        next_action=result.next_action,
    )


@dataclass(frozen=True, slots=True)
class CurrentCessationDecision:
    """One exact repeal, revocation, expiry, or revival decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "HISTORICAL", "QUARANTINE"]
    reason_code: str
    event_fact_output: Literal["NONE", "LEGAL_STATUS_EVENT"]
    event_type: str
    status_effect: Literal["CEASED", "REVIVED", "PENDING", "UNRESOLVED"]
    identity_effect: Literal["NONE", "PRESERVE_EXISTING_IDENTITIES", "REVIVAL_CONTINUITY_PROVED"]
    affected_object_id: str
    affected_scope_id: str
    effective_date: str | None
    operative_provision_fingerprint: str
    event_evidence_fingerprints: tuple[str, ...]
    prior_event_history_fingerprint: str
    event_history_action: Literal["APPEND_EVENT", "PRESERVE_UNCHANGED"]
    event_operative_at_cutoff: bool | None
    affected_location_ids: tuple[str, ...]
    post_event_operative_location_ids: tuple[str, ...]
    post_event_ceased_location_ids: tuple[str, ...]
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict cessation/revival decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_CURRENT_CESSATION_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_CURRENT_CESSATION_RULE_ID],
            "event_fact_output": self.event_fact_output,
            "event_type": self.event_type,
            "status_effect": self.status_effect,
            "identity_effect": self.identity_effect,
            "affected_object_ids": [self.affected_object_id],
            "affected_scope_ids": [self.affected_scope_id],
            "effective_date": self.effective_date,
            "operative_provision_fingerprint": self.operative_provision_fingerprint,
            "event_evidence_fingerprints": list(self.event_evidence_fingerprints),
            "prior_event_history_fingerprint": self.prior_event_history_fingerprint,
            "event_history_action": self.event_history_action,
            "event_operative_at_cutoff": self.event_operative_at_cutoff,
            "affected_location_ids": list(self.affected_location_ids),
            "post_event_operative_location_ids": list(self.post_event_operative_location_ids),
            "post_event_ceased_location_ids": list(self.post_event_ceased_location_ids),
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class _CurrentCessationContext:
    fixture_id: str
    cutoff: str
    event_type: str
    controlling_notice_state: str
    event_evidence_complete: bool
    event_evidence_authentic: bool
    event_evidence_conflicts: bool
    revival_continuity_proved: bool
    affected_object_id: str
    affected_scope_id: str
    effective_date: str | None
    operative_provision_fingerprint: str
    event_evidence_fingerprints: tuple[str, ...]
    prior_event_history_fingerprint: str
    all_location_ids: tuple[str, ...]
    affected_location_ids: tuple[str, ...]
    pre_event_operative_location_ids: tuple[str, ...]
    pre_event_ceased_location_ids: tuple[str, ...]
    affected_location_scope: str


@dataclass(frozen=True, slots=True)
class _CurrentCessationResult:
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "HISTORICAL", "QUARANTINE"]
    reason_code: str
    event_fact_output: Literal["NONE", "LEGAL_STATUS_EVENT"]
    status_effect: Literal["CEASED", "REVIVED", "PENDING", "UNRESOLVED"]
    identity_effect: Literal["NONE", "PRESERVE_EXISTING_IDENTITIES", "REVIVAL_CONTINUITY_PROVED"]
    event_history_action: Literal["APPEND_EVENT", "PRESERVE_UNCHANGED"]
    event_operative_at_cutoff: bool | None
    post_event_operative_location_ids: tuple[str, ...]
    post_event_ceased_location_ids: tuple[str, ...]
    next_action: str


def _current_cessation_decision(
    context: _CurrentCessationContext,
    result: _CurrentCessationResult,
) -> CurrentCessationDecision:
    return CurrentCessationDecision(
        fixture_id=context.fixture_id,
        processing_outcome=result.processing_outcome,
        legal_disposition=result.legal_disposition,
        reason_code=result.reason_code,
        event_fact_output=result.event_fact_output,
        event_type=context.event_type,
        status_effect=result.status_effect,
        identity_effect=result.identity_effect,
        affected_object_id=context.affected_object_id,
        affected_scope_id=context.affected_scope_id,
        effective_date=context.effective_date,
        operative_provision_fingerprint=context.operative_provision_fingerprint,
        event_evidence_fingerprints=context.event_evidence_fingerprints,
        prior_event_history_fingerprint=context.prior_event_history_fingerprint,
        event_history_action=result.event_history_action,
        event_operative_at_cutoff=result.event_operative_at_cutoff,
        affected_location_ids=context.affected_location_ids,
        post_event_operative_location_ids=result.post_event_operative_location_ids,
        post_event_ceased_location_ids=result.post_event_ceased_location_ids,
        next_action=result.next_action,
    )


@dataclass(frozen=True, slots=True)
class CurrentPublicationDecision:
    """One exact Gazette publication/enactment classification decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "EVIDENCE_ONLY", "QUARANTINE"]
    reason_code: str
    publication_fact_output: str
    source_id: str
    gazette_issue_kind: str
    gazette_material_class: str
    publication_claim: str
    subject_reference: str
    issue_id: str
    supplement_or_notice_id: str
    instrument_or_notice_number: str
    publication_date: str | None
    artifact_fingerprint: str
    source_metadata_fingerprint: str
    english_material_fingerprint: str | None
    traditional_chinese_material_fingerprint: str | None
    enabling_authority_fingerprint: str | None
    publication_history_action: Literal[
        "APPEND_PUBLICATION_EVENT", "RETAIN_INVENTORY_OBSERVATION", "PRESERVE_UNCHANGED"
    ]
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict publication decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_CURRENT_PUBLICATION_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_CURRENT_PUBLICATION_RULE_ID],
            "publication_fact_output": self.publication_fact_output,
            "source_id": self.source_id,
            "gazette_issue_kind": self.gazette_issue_kind,
            "gazette_material_class": self.gazette_material_class,
            "publication_claim": self.publication_claim,
            "subject_reference": self.subject_reference,
            "issue_id": self.issue_id,
            "supplement_or_notice_id": self.supplement_or_notice_id,
            "instrument_or_notice_number": self.instrument_or_notice_number,
            "publication_date": self.publication_date,
            "artifact_fingerprint": self.artifact_fingerprint,
            "source_metadata_fingerprint": self.source_metadata_fingerprint,
            "english_material_fingerprint": self.english_material_fingerprint,
            "traditional_chinese_material_fingerprint": (
                self.traditional_chinese_material_fingerprint
            ),
            "enabling_authority_fingerprint": self.enabling_authority_fingerprint,
            "publication_history_action": self.publication_history_action,
            "commencement_output": "NONE",
            "legal_effect_output": "NONE",
            "identity_output": "NONE",
            "continuity_inference": "NONE",
            "official_version_output": "NONE",
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class _CurrentPublicationContext:
    fixture_id: str
    cutoff: str
    source_id: str
    gazette_issue_kind: str
    gazette_material_class: str
    publication_claim: str
    subject_reference: str
    issue_id: str
    supplement_or_notice_id: str
    instrument_or_notice_number: str
    publication_date: str | None
    artifact_fingerprint: str
    source_metadata_fingerprint: str
    english_material_fingerprint: str | None
    traditional_chinese_material_fingerprint: str | None
    enabling_authority_fingerprint: str | None
    evidence_complete: bool
    evidence_authentic: bool
    evidence_conflicts: bool
    bilingual_material_complete: bool
    claim_matches_material_class: bool


@dataclass(frozen=True, slots=True)
class _CurrentPublicationResult:
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "EVIDENCE_ONLY", "QUARANTINE"]
    reason_code: str
    publication_fact_output: str
    publication_history_action: Literal[
        "APPEND_PUBLICATION_EVENT", "RETAIN_INVENTORY_OBSERVATION", "PRESERVE_UNCHANGED"
    ]
    next_action: str


def _current_publication_decision(
    context: _CurrentPublicationContext,
    result: _CurrentPublicationResult,
) -> CurrentPublicationDecision:
    return CurrentPublicationDecision(
        fixture_id=context.fixture_id,
        processing_outcome=result.processing_outcome,
        legal_disposition=result.legal_disposition,
        reason_code=result.reason_code,
        publication_fact_output=result.publication_fact_output,
        source_id=context.source_id,
        gazette_issue_kind=context.gazette_issue_kind,
        gazette_material_class=context.gazette_material_class,
        publication_claim=context.publication_claim,
        subject_reference=context.subject_reference,
        issue_id=context.issue_id,
        supplement_or_notice_id=context.supplement_or_notice_id,
        instrument_or_notice_number=context.instrument_or_notice_number,
        publication_date=context.publication_date,
        artifact_fingerprint=context.artifact_fingerprint,
        source_metadata_fingerprint=context.source_metadata_fingerprint,
        english_material_fingerprint=context.english_material_fingerprint,
        traditional_chinese_material_fingerprint=(context.traditional_chinese_material_fingerprint),
        enabling_authority_fingerprint=context.enabling_authority_fingerprint,
        publication_history_action=result.publication_history_action,
        next_action=result.next_action,
    )


@dataclass(frozen=True, slots=True)
class CurrentTextEventDecision:
    """One exact amendment, correction, or editorial-event routing decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "WAITING_ROOM", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    event_fact_output: Literal["NONE", "LEGAL_STATUS_EVENT"]
    event_type: str
    selection_result: str
    affected_object_id: str
    source_event_object_id: str
    affected_scope_id: str
    cause_source_id: str
    publication_date: str | None
    effective_date: str | None
    event_instrument_fingerprint: str
    event_evidence_fingerprints: tuple[str, ...]
    operation_set_fingerprint: str
    event_operative_at_cutoff: bool | None
    affected_location_ids: tuple[str, ...]
    affected_location_scope: str
    prior_event_history_fingerprint: str
    event_history_action: Literal["APPEND_EVENT", "PRESERVE_UNCHANGED"]
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict text-changing-event decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_CURRENT_TEXT_EVENT_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_CURRENT_TEXT_EVENT_RULE_ID],
            "event_fact_output": self.event_fact_output,
            "event_type": self.event_type,
            "selection_result": self.selection_result,
            "affected_object_ids": [self.affected_object_id],
            "source_event_object_id": self.source_event_object_id,
            "affected_scope_ids": [self.affected_scope_id],
            "cause_source_id": self.cause_source_id,
            "publication_date": self.publication_date,
            "effective_date": self.effective_date,
            "event_instrument_fingerprint": self.event_instrument_fingerprint,
            "event_evidence_fingerprints": list(self.event_evidence_fingerprints),
            "operation_set_fingerprint": self.operation_set_fingerprint,
            "event_operative_at_cutoff": self.event_operative_at_cutoff,
            "affected_location_ids": list(self.affected_location_ids),
            "affected_location_scope": self.affected_location_scope,
            "prior_event_history_fingerprint": self.prior_event_history_fingerprint,
            "event_history_action": self.event_history_action,
            "identity_or_continuity_inference": "NONE",
            "official_version_output": "NONE",
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class _CurrentTextEventContext:
    fixture_id: str
    cutoff: str
    event_type: str
    affected_object_id: str
    source_event_object_id: str
    affected_scope_id: str
    cause_source_id: str
    publication_date: str | None
    effective_date: str | None
    event_instrument_fingerprint: str
    event_evidence_fingerprints: tuple[str, ...]
    event_evidence_complete: bool
    event_evidence_authentic: bool
    event_evidence_conflicts: bool
    operation_set_fingerprint: str
    operation_mapping_complete: bool
    bilingual_operations_aligned: bool
    event_operative_at_cutoff: bool
    all_location_ids: tuple[str, ...]
    affected_location_ids: tuple[str, ...]
    affected_location_scope: str
    matching_resulting_hkel_bundle_available: bool
    resulting_bundle_reflects_event: bool
    prior_event_history_fingerprint: str


@dataclass(frozen=True, slots=True)
class _CurrentTextEventResult:
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "WAITING_ROOM", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    event_fact_output: Literal["NONE", "LEGAL_STATUS_EVENT"]
    selection_result: str
    event_operative_at_cutoff: bool | None
    event_history_action: Literal["APPEND_EVENT", "PRESERVE_UNCHANGED"]
    next_action: str


def _current_text_event_decision(
    context: _CurrentTextEventContext,
    result: _CurrentTextEventResult,
) -> CurrentTextEventDecision:
    return CurrentTextEventDecision(
        fixture_id=context.fixture_id,
        processing_outcome=result.processing_outcome,
        legal_disposition=result.legal_disposition,
        coverage_effect=result.coverage_effect,
        reason_code=result.reason_code,
        event_fact_output=result.event_fact_output,
        event_type=context.event_type,
        selection_result=result.selection_result,
        affected_object_id=context.affected_object_id,
        source_event_object_id=context.source_event_object_id,
        affected_scope_id=context.affected_scope_id,
        cause_source_id=context.cause_source_id,
        publication_date=context.publication_date,
        effective_date=context.effective_date,
        event_instrument_fingerprint=context.event_instrument_fingerprint,
        event_evidence_fingerprints=context.event_evidence_fingerprints,
        operation_set_fingerprint=context.operation_set_fingerprint,
        event_operative_at_cutoff=result.event_operative_at_cutoff,
        affected_location_ids=context.affected_location_ids,
        affected_location_scope=context.affected_location_scope,
        prior_event_history_fingerprint=context.prior_event_history_fingerprint,
        event_history_action=result.event_history_action,
        next_action=result.next_action,
    )


@dataclass(frozen=True, slots=True)
class ReconstructionPlanSemanticDecision:
    """One bounded decision/challenge result before executable Plan validation."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "QUARANTINE"]
    reason_code: str
    candidate_output: Literal["NONE", "UNTRUSTED_STRUCTURED_PLAN_CANDIDATE"]
    challenge_outcome: str
    evidence_bundle_fingerprint: str
    operation_registry_fingerprint: str
    plan_contract_fingerprint: str
    decision_profile_fingerprint: str | None
    challenge_profile_fingerprint: str | None
    decision_result_fingerprint: str | None
    challenge_result_fingerprint: str | None
    candidate_mapping_fingerprint: str | None
    deterministic_precheck_result: Literal["PASS", "FAIL", "NOT_PERFORMED"]
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict pre-Plan semantic gate representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_RECONSTRUCTION_PLAN_SEMANTIC_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": "COVERAGE_GAP",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_RECONSTRUCTION_PLAN_SEMANTIC_RULE_ID],
            "decision_task": "RECONSTRUCTION_PLAN_DECISION",
            "challenge_task": "RECONSTRUCTION_PLAN_CHALLENGE",
            "candidate_output": self.candidate_output,
            "challenge_outcome": self.challenge_outcome,
            "evidence_bundle_fingerprint": self.evidence_bundle_fingerprint,
            "operation_registry_fingerprint": self.operation_registry_fingerprint,
            "plan_contract_fingerprint": self.plan_contract_fingerprint,
            "decision_profile_fingerprint": self.decision_profile_fingerprint,
            "challenge_profile_fingerprint": self.challenge_profile_fingerprint,
            "decision_result_fingerprint": self.decision_result_fingerprint,
            "challenge_result_fingerprint": self.challenge_result_fingerprint,
            "candidate_mapping_fingerprint": self.candidate_mapping_fingerprint,
            "deterministic_precheck_result": self.deterministic_precheck_result,
            "executable_plan_output": "NONE",
            "reconstructed_text_output": "NONE",
            "operation_execution": "NONE",
            "record_output": "NONE",
            "external_effects": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class _ReconstructionPlanSemanticContext:
    fixture_id: str
    evidence_bundle_fingerprint: str
    operation_registry_fingerprint: str
    plan_contract_fingerprint: str
    decision_profile_fingerprint: str | None
    challenge_profile_fingerprint: str | None
    decision_result_fingerprint: str | None
    challenge_result_fingerprint: str | None
    candidate_mapping_fingerprint: str | None
    task_profiles_admitted: bool
    decision_result_contract_valid: bool
    challenge_result_contract_valid: bool
    decision_evidence_bindings_complete: bool
    challenge_evidence_bindings_complete: bool
    candidate_operations_closed_registry_only: bool
    candidate_source_spans_complete: bool
    candidate_contains_final_text: bool
    challenge_outcome: str
    semantic_result_conflicts: bool
    event_chain_mapping_complete: bool
    applicability_mapping_complete: bool
    dependency_mapping_complete: bool
    bilingual_stream_mapping_complete: bool
    deterministic_prechecks_passed: bool


@dataclass(frozen=True, slots=True)
class _ReconstructionPlanSemanticResult:
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "QUARANTINE"]
    reason_code: str
    candidate_output: Literal["NONE", "UNTRUSTED_STRUCTURED_PLAN_CANDIDATE"]
    deterministic_precheck_result: Literal["PASS", "FAIL", "NOT_PERFORMED"]
    next_action: str


def _reconstruction_plan_semantic_decision(
    context: _ReconstructionPlanSemanticContext,
    result: _ReconstructionPlanSemanticResult,
) -> ReconstructionPlanSemanticDecision:
    return ReconstructionPlanSemanticDecision(
        fixture_id=context.fixture_id,
        processing_outcome=result.processing_outcome,
        legal_disposition=result.legal_disposition,
        reason_code=result.reason_code,
        candidate_output=result.candidate_output,
        challenge_outcome=context.challenge_outcome,
        evidence_bundle_fingerprint=context.evidence_bundle_fingerprint,
        operation_registry_fingerprint=context.operation_registry_fingerprint,
        plan_contract_fingerprint=context.plan_contract_fingerprint,
        decision_profile_fingerprint=context.decision_profile_fingerprint,
        challenge_profile_fingerprint=context.challenge_profile_fingerprint,
        decision_result_fingerprint=context.decision_result_fingerprint,
        challenge_result_fingerprint=context.challenge_result_fingerprint,
        candidate_mapping_fingerprint=context.candidate_mapping_fingerprint,
        deterministic_precheck_result=result.deterministic_precheck_result,
        next_action=result.next_action,
    )


@dataclass(frozen=True, slots=True)
class ReconstructionPlanValidationDecision:
    """One deterministic validation result for an exact ADR 0084 Plan."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "QUARANTINE"]
    source_contract_review_required: bool
    reason_code: str
    candidate_plan_fingerprint: str | None
    plan_validation_result: Literal["VALIDATED", "NONE"]
    validated_reconstruction_plan_id: str | None
    validated_reconstruction_plan_fingerprint: str | None
    validated_operation_count: int
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict effect-free Plan-validation decision."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_RECONSTRUCTION_PLAN_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": "COVERAGE_GAP",
            "source_contract_review_required": self.source_contract_review_required,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_RECONSTRUCTION_PLAN_RULE_ID],
            "candidate_plan_fingerprint": self.candidate_plan_fingerprint,
            "plan_validation_result": self.plan_validation_result,
            "validated_reconstruction_plan_id": self.validated_reconstruction_plan_id,
            "validated_reconstruction_plan_fingerprint": (
                self.validated_reconstruction_plan_fingerprint
            ),
            "validated_operation_count": self.validated_operation_count,
            "operation_execution": "NONE",
            "reconstructed_text_output": "NONE",
            "record_output": "NONE",
            "external_effects": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class _ReconstructionPlanContext:
    fixture_id: str
    semantic_candidate_fingerprint: str
    plan_semantic_candidate_fingerprint: str
    accepted_legal_desk_decision_ref: dict[str, JsonValue]
    legal_desk_decision_accepted: bool
    latest_eligible_base_proved: bool
    event_chain_complete: bool
    event_order_proved: bool
    applicability_exact: bool
    dependency_closure_complete: bool
    no_overlapping_plan: bool
    source_unit_ownership_complete: bool
    authentic_language_evidence_complete: bool
    bilingual_alignment_complete: bool
    operation_event_bindings_complete: bool
    atomic_groups_dependency_closed: bool
    undeclared_input_detected: bool
    deterministic_revalidation_passed: bool
    declared_evidence_refs: tuple[dict[str, JsonValue], ...]
    candidate_plan: dict[str, JsonValue] | None
    candidate_plan_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class _ReconstructionPlanResult:
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: Literal["NOT_APPLICABLE", "QUARANTINE"]
    source_contract_review_required: bool
    reason_code: str
    plan_validation_result: Literal["VALIDATED", "NONE"]
    validated_reconstruction_plan_id: str | None
    validated_reconstruction_plan_fingerprint: str | None
    validated_operation_count: int
    next_action: str


def _reconstruction_plan_validation_decision(
    context: _ReconstructionPlanContext,
    result: _ReconstructionPlanResult,
) -> ReconstructionPlanValidationDecision:
    return ReconstructionPlanValidationDecision(
        fixture_id=context.fixture_id,
        processing_outcome=result.processing_outcome,
        legal_disposition=result.legal_disposition,
        source_contract_review_required=result.source_contract_review_required,
        reason_code=result.reason_code,
        candidate_plan_fingerprint=context.candidate_plan_fingerprint,
        plan_validation_result=result.plan_validation_result,
        validated_reconstruction_plan_id=result.validated_reconstruction_plan_id,
        validated_reconstruction_plan_fingerprint=(
            result.validated_reconstruction_plan_fingerprint
        ),
        validated_operation_count=result.validated_operation_count,
        next_action=result.next_action,
    )


@dataclass(frozen=True, slots=True)
class CurrentEventDecision:
    """One operative-event and missing-consolidation routing decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    event_fact_output: Literal["NONE", "LEGAL_STATUS_EVENT"]
    selection_result: str
    affected_object_id: str
    affected_scope_id: str
    affected_location_ids: tuple[str, ...]
    affected_location_scope: str
    effective_date: str | None
    base_evidence_class: str | None
    base_version_date: str | None
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict current-event decision representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_CURRENT_EVENT_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_CURRENT_EVENT_RULE_ID],
            "event_fact_output": self.event_fact_output,
            "selection_result": self.selection_result,
            "affected_object_ids": [self.affected_object_id],
            "affected_scope_ids": [self.affected_scope_id],
            "affected_location_ids": list(self.affected_location_ids),
            "affected_location_scope": self.affected_location_scope,
            "effective_date": self.effective_date,
            "base_evidence_class": self.base_evidence_class,
            "base_version_date": self.base_version_date,
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class CurrentDispositionDecision:
    """One ordinary-update primary-disposition decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: str
    reason_code: str
    affected_object_id: str
    affected_scope_id: str
    affected_location_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict ordinary current-disposition representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_CURRENT_DISPOSITION_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_CURRENT_DISPOSITION_RULE_ID],
            "affected_object_ids": [self.affected_object_id],
            "affected_scope_ids": [self.affected_scope_id],
            "affected_location_ids": [self.affected_location_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class CurrentRecordDecision:
    """One exact ordinary-update record reuse or creation decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    legal_disposition: str
    reason_code: str
    record_action: Literal["REUSED", "CREATED", "NONE"]
    candidate_record: dict[str, JsonValue] | None
    serving_payload_fingerprint: str | None
    predecessor_record_id: str | None
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict ordinary current-record representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_CURRENT_RECORD_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": self.legal_disposition,
            "coverage_effect": "NONE",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_CURRENT_RECORD_RULE_ID],
            "record_action": self.record_action,
            "candidate_record": self.candidate_record,
            "serving_payload_fingerprint": self.serving_payload_fingerprint,
            "predecessor_record_id": self.predecessor_record_id,
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": (
                "REUSED"
                if self.record_action == "REUSED"
                else "CANDIDATE"
                if self.record_action == "CREATED"
                else "NONE"
            ),
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class CurrentReleaseAccountingDecision:
    """One complete ordinary-update release-accounting decision."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    predecessor_release_id: str | None
    accounted_object_ids: tuple[str, ...]
    accounted_location_ids: tuple[str, ...]
    unresolved_ids: tuple[str, ...]
    release_accounting_fingerprint: str | None
    affected_scope_id: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict ordinary current-release accounting representation."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_CURRENT_RELEASE_ACCOUNTING_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": self.coverage_effect,
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_CURRENT_RELEASE_ACCOUNTING_RULE_ID],
            "initial_baseline": False,
            "predecessor_release_id": self.predecessor_release_id,
            "accounted_object_ids": list(self.accounted_object_ids),
            "accounted_location_ids": list(self.accounted_location_ids),
            "unresolved_ids": list(self.unresolved_ids),
            "release_accounting_fingerprint": self.release_accounting_fingerprint,
            "affected_scope_ids": [self.affected_scope_id],
            "record_output": "NONE",
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class _InventoryData:
    object_scope: dict[str, str]
    object_resources: dict[str, set[str]]
    claims_by_object: dict[str, list[tuple[str, set[str]]]]


def _read_json(path: Path) -> dict[str, JsonValue]:
    try:
        raw = path.read_bytes()
        value = parse_json_bytes(raw, max_bytes=_MAX_BYTES)
    except (OSError, ValueError) as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, path.name) from error
    if not isinstance(value, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, path.name)
    return value


def _text(value: JsonValue | None, label: str) -> str:
    if type(value) is not str or not value:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _objects(value: JsonValue | None, label: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return tuple(item for item in value if isinstance(item, dict))


def _texts(value: JsonValue | None, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    result = tuple(_text(item, label) for item in value)
    if len(result) != len(set(result)):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return result


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _validate(
    registry: SchemaRegistry,
    value: JsonValue,
    definition: str,
    *,
    schema: str = _SCHEMA,
) -> None:
    try:
        registry.validate(value, f"{schema}#/$defs/{definition}")
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, definition) from error


def _safe_member(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        not relative
        or relative.startswith("/")
        or "\\" in relative
        or ".." in pure.parts
        or pure.as_posix() != relative
    ):
        raise RulebookError(RulebookErrorCode.PATH_INVALID, relative)
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, relative)
    return path


def _validate_closed_catalogues(root: Path, registry: SchemaRegistry) -> None:
    source_codes = _read_json(root / "catalogues/baseline-inventory-source-codes.json")
    reason_codes = _read_json(root / "catalogues/baseline-inventory-reason-codes.json")
    _validate(registry, source_codes, "source_code_catalogue")
    _validate(registry, reason_codes, "reason_code_catalogue")

    declared_sources = {
        _text(item.get("code"), "source code")
        for item in _objects(source_codes.get("source_codes"), "source_codes")
    }
    bindings = {
        _text(item.get("legal_nature"), "legal_nature"): _text(item.get("scope_id"), "scope_id")
        for item in _objects(source_codes.get("legal_nature_scope_bindings"), "bindings")
    }
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if (
        declared_sources != {HK_CURRENT_INVENTORY_SOURCE_ID}
        or bindings != _SCOPE_BY_NATURE
        or frozenset(declared_reasons) != _REASON_CODES
    ):
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline inventory catalogue")


def _validate_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-INV-001.json")
    _validate(registry, rule, "rule")
    if (
        rule.get("rule_id") != HK_BASELINE_INVENTORY_RULE_ID
        or rule.get("source_id") != HK_CURRENT_INVENTORY_SOURCE_ID
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "OWNERSHIP_AMBIGUOUS",
            "OBJECT_OR_RESOURCE_UNACCOUNTED",
            "SCOPE_MISASSIGNED",
            "ACCOUNTED",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline inventory rule")


def _validate_observation_catalogues(root: Path, registry: SchemaRegistry) -> None:
    source_codes = _read_json(root / "catalogues/baseline-observation-source-codes.json")
    reason_codes = _read_json(root / "catalogues/baseline-observation-reason-codes.json")
    _validate(
        registry,
        source_codes,
        "source_code_catalogue",
        schema=_OBSERVATION_SCHEMA,
    )
    _validate(
        registry,
        reason_codes,
        "reason_code_catalogue",
        schema=_OBSERVATION_SCHEMA,
    )
    declared_sources = {
        _text(item.get("code"), "source code")
        for item in _objects(source_codes.get("source_codes"), "source_codes")
    }
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if (
        frozenset(declared_sources) != _REQUIRED_OBSERVATION_SOURCES
        or frozenset(declared_reasons) != _OBSERVATION_REASON_CODES
    ):
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline observation catalogue")


def _validate_observation_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-OBS-001.json")
    _validate(registry, rule, "rule", schema=_OBSERVATION_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_OBSERVATION_RULE_ID
        or frozenset(_texts(rule.get("required_source_ids"), "required_source_ids"))
        != _REQUIRED_OBSERVATION_SOURCES
        or rule.get("expected_locks") != _EXPECTED_OBSERVATION_LOCKS
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "REQUIRED_SOURCE_UNAVAILABLE",
            "CUTOFF_MIXED",
            "LOCK_MISMATCH",
            "POST_CUTOFF_CHANGE",
            "FROZEN",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline observation rule")


def _validate_evidence_catalogues(root: Path, registry: SchemaRegistry) -> None:
    source_codes = _read_json(root / "catalogues/baseline-evidence-source-codes.json")
    reason_codes = _read_json(root / "catalogues/baseline-evidence-reason-codes.json")
    _validate(registry, source_codes, "source_code_catalogue", schema=_EVIDENCE_SCHEMA)
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_EVIDENCE_SCHEMA)
    declared_sources = {
        _text(item.get("code"), "source code")
        for item in _objects(source_codes.get("source_codes"), "source_codes")
    }
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if (
        frozenset(declared_sources) != _EVIDENCE_SOURCE_IDS
        or frozenset(declared_reasons) != _EVIDENCE_REASON_CODES
    ):
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline evidence catalogue")


def _validate_evidence_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-EVID-001.json")
    _validate(registry, rule, "rule", schema=_EVIDENCE_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_EVIDENCE_RULE_ID
        or frozenset(_texts(rule.get("required_evidence_roles"), "required_evidence_roles"))
        != _REQUIRED_EVIDENCE_ROLES
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "HISTORICAL_SUBSTITUTION_FORBIDDEN",
            "REQUIRED_ARTIFACT_MISSING",
            "VERSION_OR_CONTENT_CONFLICT",
            "EVIDENCE_RECONCILED",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline evidence rule")


def _validate_state_catalogues(root: Path, registry: SchemaRegistry) -> None:
    source_codes = _read_json(root / "catalogues/baseline-state-source-codes.json")
    reason_codes = _read_json(root / "catalogues/baseline-state-reason-codes.json")
    _validate(registry, source_codes, "source_code_catalogue", schema=_STATE_SCHEMA)
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_STATE_SCHEMA)
    declared_sources = {
        _text(item.get("code"), "source code")
        for item in _objects(source_codes.get("source_codes"), "source_codes")
    }
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if (
        frozenset(declared_sources) != _STATE_SOURCE_IDS
        or frozenset(declared_reasons) != _STATE_REASON_CODES
    ):
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline state catalogue")


def _validate_state_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-STATE-001.json")
    _validate(registry, rule, "rule", schema=_STATE_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_STATE_RULE_ID
        or _texts(rule.get("predecessor_rule_ids"), "predecessor_rule_ids")
        != (HK_BASELINE_INVENTORY_RULE_ID, HK_BASELINE_EVIDENCE_RULE_ID)
        or frozenset(_texts(rule.get("accepted_signal_source_ids"), "accepted_signal_source_ids"))
        != _STATE_SOURCE_IDS
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "SOURCE_SEMANTICS_UNKNOWN",
            "REQUIRED_SIGNAL_MISSING",
            "ACCEPTED_SIGNAL_CONFLICT",
            "STATUS_OR_STRUCTURE_AMBIGUOUS",
            "OPERATIVE_EFFECT_NOT_PROVED",
            "RULEBOOK_SUPPORT_MISSING",
            "PRESENT_OPERATIVE_STATE_ESTABLISHED",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline state rule")


def _validate_limit_catalogues(root: Path, registry: SchemaRegistry) -> None:
    assertion_codes = _read_json(root / "catalogues/baseline-limit-assertion-codes.json")
    reason_codes = _read_json(root / "catalogues/baseline-limit-reason-codes.json")
    _validate(registry, assertion_codes, "assertion_code_catalogue", schema=_LIMIT_SCHEMA)
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_LIMIT_SCHEMA)
    declared_assertions = {
        _text(item.get("code"), "assertion code")
        for item in _objects(assertion_codes.get("assertion_codes"), "assertion_codes")
    }
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if (
        frozenset(declared_assertions) != _LIMIT_ASSERTION_CODES
        or frozenset(declared_reasons) != _LIMIT_REASON_CODES
    ):
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline limit catalogue")


def _validate_limit_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-LIMIT-001.json")
    _validate(registry, rule, "rule", schema=_LIMIT_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_LIMIT_RULE_ID
        or rule.get("predecessor_rule_id") != HK_BASELINE_STATE_RULE_ID
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "HISTORICAL_EVENT_FORBIDDEN",
            "EFFECTIVE_DATE_FORBIDDEN",
            "CONTINUITY_FORBIDDEN",
            "COMPLETE_HISTORY_FORBIDDEN",
            "PRESENT_STATE_ONLY",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline limit rule")


def _validate_identity_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/baseline-identity-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_IDENTITY_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _IDENTITY_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline identity catalogue")


def _validate_identity_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-ID-001.json")
    _validate(registry, rule, "rule", schema=_IDENTITY_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_IDENTITY_RULE_ID
        or rule.get("predecessor_rule_id") != HK_BASELINE_LIMIT_RULE_ID
        or _texts(rule.get("allocation_layers"), "allocation_layers") != _IDENTITY_LAYERS
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "DUPLICATE_OR_CONTINUITY_AMBIGUOUS",
            "UNPROVED_RELATIONSHIP_FORBIDDEN",
            "NON_REGISTER_IDENTITY_FORBIDDEN",
            "GREENFIELD_ALLOCATION_REQUESTED",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline identity rule")


def _validate_disposition_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/baseline-disposition-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_DISPOSITION_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _DISPOSITION_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline disposition catalogue")


def _validate_disposition_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-DISP-001.json")
    _validate(registry, rule, "rule", schema=_DISPOSITION_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_DISPOSITION_RULE_ID
        or rule.get("predecessor_rule_id") != HK_BASELINE_IDENTITY_RULE_ID
        or _texts(rule.get("primary_dispositions"), "primary_dispositions") != _PRIMARY_DISPOSITIONS
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "CURRENT_CONSOLIDATION_GAP",
            "SINGLE_SIGNAL_INSUFFICIENT",
            "QUARANTINE_REQUIRED",
            "SEARCHABLE_CURRENT",
            "WAITING_ROOM",
            "EVIDENCE_ONLY",
            "HISTORICAL",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline disposition rule")


def _validate_record_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/baseline-record-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_RECORD_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _RECORD_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline record catalogue")


def _validate_record_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-REC-001.json")
    _validate(registry, rule, "rule", schema=_RECORD_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_RECORD_RULE_ID
        or rule.get("predecessor_rule_id") != HK_BASELINE_DISPOSITION_RULE_ID
        or rule.get("metadata_profile") != _SYNTHETIC_RECORD_PROFILE
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "NON_SEARCHABLE_EXCLUDED",
            "LEGACY_ID_FORBIDDEN",
            "BILINGUAL_CONTENT_INCOMPLETE",
            "RENDERING_NON_CANONICAL",
            "AUTHORITY_NOTE_UNAPPROVED",
            "CANDIDATE_CREATED",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline record rule")


def _validate_release_accounting_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/baseline-release-accounting-reason-codes.json")
    _validate(
        registry,
        reason_codes,
        "reason_code_catalogue",
        schema=_RELEASE_ACCOUNTING_SCHEMA,
    )
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _RELEASE_ACCOUNTING_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline release accounting catalogue")


def _validate_release_accounting_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-REL-001.json")
    _validate(registry, rule, "rule", schema=_RELEASE_ACCOUNTING_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_RELEASE_ACCOUNTING_RULE_ID
        or rule.get("predecessor_rule_id") != HK_BASELINE_RECORD_RULE_ID
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "PREDECESSOR_FORBIDDEN",
            "OBJECT_OR_LOCATION_UNACCOUNTED",
            "RESULT_ACCOUNTING_INCONSISTENT",
            "REFERENCE_UNACCOUNTED",
            "COMPLETENESS_UNRESOLVED",
            "INITIAL_RELEASE_ACCOUNTED",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline release accounting rule")


def _validate_review_catalogues(root: Path, registry: SchemaRegistry) -> None:
    source_codes = _read_json(root / "catalogues/baseline-review-source-codes.json")
    reason_codes = _read_json(root / "catalogues/baseline-review-reason-codes.json")
    _validate(registry, source_codes, "source_code_catalogue", schema=_REVIEW_SCHEMA)
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_REVIEW_SCHEMA)
    declared_sources = {
        _text(item.get("code"), "source code")
        for item in _objects(source_codes.get("source_codes"), "source_codes")
    }
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if (
        frozenset(declared_sources) != _REVIEW_SOURCE_IDS
        or frozenset(declared_reasons) != _REVIEW_REASON_CODES
    ):
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline review catalogues")


def _validate_review_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-REVIEW-001.json")
    _validate(registry, rule, "rule", schema=_REVIEW_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_REVIEW_RULE_ID
        or frozenset(_texts(rule.get("permitted_source_ids"), "permitted_source_ids"))
        != _REVIEW_SOURCE_IDS
        or rule.get("trigger_fact_bindings") != _REVIEW_FACT_BY_TRIGGER
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "NO_MATERIAL_UNCERTAINTY",
            "BROAD_HISTORY_FORBIDDEN",
            "SOURCE_NOT_PERMITTED",
            "FACT_SCOPE_MISMATCH",
            "TARGETED_INVESTIGATION_OPENED",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline review rule")


def _validate_history_catalogues(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/baseline-history-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_HISTORY_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _HISTORY_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline history catalogue")


def _validate_history_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-HIST-001.json")
    _validate(registry, rule, "rule", schema=_HISTORY_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_HISTORY_RULE_ID
        or rule.get("predecessor_rule_id") != HK_BASELINE_REVIEW_RULE_ID
        or frozenset(_texts(rule.get("permitted_source_ids"), "permitted_source_ids"))
        != _REVIEW_SOURCE_IDS
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "CURRENT_EVIDENCE_SUBSTITUTION_FORBIDDEN",
            "REQUESTED_EVIDENCE_UNAVAILABLE",
            "SIMILARITY_ONLY_FORBIDDEN",
            "EVIDENCE_CONFLICT",
            "EVIDENCE_INSUFFICIENT",
            "PERMITTED_FACT_ESTABLISHED",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline history rule")


def _validate_change_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/baseline-change-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_CHANGE_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CHANGE_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "baseline change catalogue")


def _validate_change_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / "rules/HKLEG-BASE-CHANGE-001.json")
    _validate(registry, rule, "rule", schema=_CHANGE_SCHEMA)
    if (
        rule.get("rule_id") != HK_BASELINE_CHANGE_RULE_ID
        or _texts(rule.get("permitted_strategies"), "permitted_strategies")
        != ("ABANDON_AND_REFREEZE", "FINISH_ORIGINAL_THEN_UPDATE")
        or _texts(rule.get("branch_precedence"), "branch_precedence")
        != (
            "NO_POST_CUTOFF_CHANGE",
            "FROZEN_PACKAGE_NOT_PRESERVED",
            "NEW_OBSERVATION_NOT_SEPARATE",
            "MIXED_CUTOFF_FORBIDDEN",
            "LATER_CURRENCY_CLAIM_FORBIDDEN",
            "REFREEZE_SELECTED",
            "FINISH_THEN_UPDATE_SELECTED",
        )
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "baseline change rule")


def _validate_current_observation_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-observation-reason-codes.json")
    _validate(
        registry,
        reason_codes,
        "reason_code_catalogue",
        schema=_CURRENT_OBSERVATION_SCHEMA,
    )
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_OBSERVATION_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current observation catalogue")


def _validate_current_observation_rules(root: Path, registry: SchemaRegistry) -> None:
    rules = tuple(
        _read_json(root / f"rules/{rule_id}.json") for rule_id in HK_CURRENT_OBSERVATION_RULE_IDS
    )
    for rule in rules:
        _validate(registry, rule, "rule", schema=_CURRENT_OBSERVATION_SCHEMA)
    if tuple(_text(rule.get("rule_id"), "rule_id") for rule in rules) != (
        HK_CURRENT_OBSERVATION_RULE_IDS
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current observation rules")


def _validate_current_evidence_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-evidence-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_CURRENT_EVIDENCE_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_EVIDENCE_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current evidence catalogue")


def _validate_current_evidence_rules(root: Path, registry: SchemaRegistry) -> None:
    rules = tuple(
        _read_json(root / f"rules/{rule_id}.json") for rule_id in HK_CURRENT_EVIDENCE_RULE_IDS
    )
    for rule in rules:
        _validate(registry, rule, "rule", schema=_CURRENT_EVIDENCE_SCHEMA)
    if tuple(_text(rule.get("rule_id"), "rule_id") for rule in rules) != (
        HK_CURRENT_EVIDENCE_RULE_IDS
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current evidence rules")


def _validate_current_difference_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-difference-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_CURRENT_DIFFERENCE_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_DIFFERENCE_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current difference catalogue")


def _validate_current_difference_rules(root: Path, registry: SchemaRegistry) -> None:
    rules = tuple(
        _read_json(root / f"rules/{rule_id}.json") for rule_id in HK_CURRENT_DIFFERENCE_RULE_IDS
    )
    for rule in rules:
        _validate(registry, rule, "rule", schema=_CURRENT_DIFFERENCE_SCHEMA)
    if tuple(_text(rule.get("rule_id"), "rule_id") for rule in rules) != (
        HK_CURRENT_DIFFERENCE_RULE_IDS
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current difference rules")


def _validate_current_cause_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-cause-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_CURRENT_CAUSE_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_CAUSE_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current cause catalogue")


def _validate_current_cause_rules(root: Path, registry: SchemaRegistry) -> None:
    rules = tuple(
        _read_json(root / f"rules/{rule_id}.json") for rule_id in HK_CURRENT_CAUSE_RULE_IDS
    )
    for rule in rules:
        _validate(registry, rule, "rule", schema=_CURRENT_CAUSE_SCHEMA)
    if tuple(_text(rule.get("rule_id"), "rule_id") for rule in rules) != (
        HK_CURRENT_CAUSE_RULE_IDS
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current cause rules")


def _validate_current_commencement_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-commencement-reason-codes.json")
    _validate(
        registry,
        reason_codes,
        "reason_code_catalogue",
        schema=_CURRENT_COMMENCEMENT_SCHEMA,
    )
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_COMMENCEMENT_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current commencement catalogue")


def _validate_current_commencement_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / f"rules/{HK_CURRENT_COMMENCEMENT_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_CURRENT_COMMENCEMENT_SCHEMA)
    if rule.get("rule_id") != HK_CURRENT_COMMENCEMENT_RULE_ID:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current commencement rule")


def _validate_current_cessation_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-cessation-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_CURRENT_CESSATION_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_CESSATION_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current cessation catalogue")


def _validate_current_cessation_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / f"rules/{HK_CURRENT_CESSATION_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_CURRENT_CESSATION_SCHEMA)
    if rule.get("rule_id") != HK_CURRENT_CESSATION_RULE_ID:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current cessation rule")


def _validate_current_publication_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-publication-reason-codes.json")
    _validate(
        registry,
        reason_codes,
        "reason_code_catalogue",
        schema=_CURRENT_PUBLICATION_SCHEMA,
    )
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_PUBLICATION_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current publication catalogue")


def _validate_current_publication_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / f"rules/{HK_CURRENT_PUBLICATION_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_CURRENT_PUBLICATION_SCHEMA)
    if rule.get("rule_id") != HK_CURRENT_PUBLICATION_RULE_ID:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current publication rule")


def _validate_current_text_event_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-text-event-reason-codes.json")
    _validate(
        registry,
        reason_codes,
        "reason_code_catalogue",
        schema=_CURRENT_TEXT_EVENT_SCHEMA,
    )
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_TEXT_EVENT_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current text event catalogue")


def _validate_current_text_event_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / f"rules/{HK_CURRENT_TEXT_EVENT_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_CURRENT_TEXT_EVENT_SCHEMA)
    if rule.get("rule_id") != HK_CURRENT_TEXT_EVENT_RULE_ID:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current text event rule")


def _validate_current_event_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-event-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_CURRENT_EVENT_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_EVENT_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current event catalogue")


def _validate_current_event_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / f"rules/{HK_CURRENT_EVENT_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_CURRENT_EVENT_SCHEMA)
    if rule.get("rule_id") != HK_CURRENT_EVENT_RULE_ID:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current event rule")


def _validate_current_disposition_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-disposition-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_CURRENT_DISPOSITION_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_DISPOSITION_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current disposition catalogue")


def _validate_current_disposition_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / f"rules/{HK_CURRENT_DISPOSITION_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_CURRENT_DISPOSITION_SCHEMA)
    if rule.get("rule_id") != HK_CURRENT_DISPOSITION_RULE_ID:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current disposition rule")


def _validate_current_record_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-record-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_CURRENT_RECORD_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_RECORD_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current record catalogue")


def _validate_current_record_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / f"rules/{HK_CURRENT_RECORD_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_CURRENT_RECORD_SCHEMA)
    if rule.get("rule_id") != HK_CURRENT_RECORD_RULE_ID:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current record rule")


def _validate_current_release_catalogue(root: Path, registry: SchemaRegistry) -> None:
    reason_codes = _read_json(root / "catalogues/current-release-accounting-reason-codes.json")
    _validate(registry, reason_codes, "reason_code_catalogue", schema=_CURRENT_RELEASE_SCHEMA)
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _CURRENT_RELEASE_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "current release catalogue")


def _validate_current_release_rule(root: Path, registry: SchemaRegistry) -> None:
    rule = _read_json(root / f"rules/{HK_CURRENT_RELEASE_ACCOUNTING_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_CURRENT_RELEASE_SCHEMA)
    if rule.get("rule_id") != HK_CURRENT_RELEASE_ACCOUNTING_RULE_ID:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "current release rule")


def _validate_reconstruction_plan_semantic_catalogue(
    root: Path,
    registry: SchemaRegistry,
) -> None:
    reason_codes = _read_json(root / "catalogues/reconstruction-plan-semantic-reason-codes.json")
    _validate(
        registry,
        reason_codes,
        "reason_code_catalogue",
        schema=_RECONSTRUCTION_PLAN_SEMANTIC_SCHEMA,
    )
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _RECONSTRUCTION_PLAN_SEMANTIC_REASON_CODES:
        raise RulebookError(
            RulebookErrorCode.UNKNOWN_CODE,
            "reconstruction plan semantic catalogue",
        )


def _validate_reconstruction_plan_semantic_rule(
    root: Path,
    registry: SchemaRegistry,
) -> None:
    rule = _read_json(root / f"rules/{HK_RECONSTRUCTION_PLAN_SEMANTIC_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_RECONSTRUCTION_PLAN_SEMANTIC_SCHEMA)
    if rule.get("rule_id") != HK_RECONSTRUCTION_PLAN_SEMANTIC_RULE_ID:
        raise RulebookError(
            RulebookErrorCode.CONTRACT_MISMATCH,
            "reconstruction plan semantic rule",
        )


def _validate_reconstruction_plan_catalogue(
    root: Path,
    registry: SchemaRegistry,
) -> None:
    reason_codes = _read_json(root / "catalogues/reconstruction-plan-validation-reason-codes.json")
    _validate(
        registry,
        reason_codes,
        "reason_code_catalogue",
        schema=_RECONSTRUCTION_PLAN_SCHEMA,
    )
    declared_reasons = {
        _text(item.get("code"), "reason code")
        for item in _objects(reason_codes.get("reason_codes"), "reason_codes")
    }
    if frozenset(declared_reasons) != _RECONSTRUCTION_PLAN_REASON_CODES:
        raise RulebookError(
            RulebookErrorCode.UNKNOWN_CODE,
            "reconstruction plan validation catalogue",
        )


def _validate_reconstruction_plan_rule(
    root: Path,
    registry: SchemaRegistry,
) -> None:
    rule = _read_json(root / f"rules/{HK_RECONSTRUCTION_PLAN_RULE_ID}.json")
    _validate(registry, rule, "rule", schema=_RECONSTRUCTION_PLAN_SCHEMA)
    if rule.get("rule_id") != HK_RECONSTRUCTION_PLAN_RULE_ID:
        raise RulebookError(
            RulebookErrorCode.CONTRACT_MISMATCH,
            "reconstruction plan validation rule",
        )


def _timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label) from error
    if parsed.tzinfo is None:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return parsed


def _evaluate_hk_baseline_observation(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineObservationDecision:
    cutoff = _text(input_document.get("cutoff"), "cutoff")
    locks = input_document.get("locks")
    if not isinstance(locks, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "locks")
    observations = _objects(input_document.get("source_observations"), "source_observations")
    by_source: dict[str, dict[str, JsonValue]] = {}
    for observation in observations:
        source_id = _text(observation.get("source_id"), "source_id")
        if source_id in by_source:
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "duplicate source")
        by_source[source_id] = observation

    missing = set(_REQUIRED_OBSERVATION_SOURCES).difference(by_source)
    unavailable = {
        source_id
        for source_id in _REQUIRED_OBSERVATION_SOURCES.intersection(by_source)
        if by_source[source_id].get("complete") is not True
        or by_source[source_id].get("freshness") != "FRESH"
    }
    unresolved = missing | unavailable
    if unresolved:
        return BaselineObservationDecision(
            fixture_id,
            "BLOCK",
            "COVERAGE_GAP",
            "HKLEG_BASE_OBSERVATION_REQUIRED_SOURCE_UNAVAILABLE",
            None,
            (),
            tuple(sorted(unresolved, key=str.encode)),
            "COMPLETE_REQUIRED_OBSERVATIONS",
        )

    if any(observation.get("cutoff") != cutoff for observation in observations):
        return BaselineObservationDecision(
            fixture_id,
            "BLOCK",
            "NONE",
            "HKLEG_BASE_OBSERVATION_CUTOFF_MIXED",
            None,
            (),
            (),
            "REFREEZE_SINGLE_CUTOFF",
        )
    if locks != _EXPECTED_OBSERVATION_LOCKS:
        return BaselineObservationDecision(
            fixture_id,
            "BLOCK",
            "NONE",
            "HKLEG_BASE_OBSERVATION_LOCK_MISMATCH",
            None,
            (),
            (),
            "USE_EXACT_PACKAGE_LOCKS",
        )
    changed_sources = {
        source_id
        for source_id, observation in by_source.items()
        if observation.get("change_observed_at") is not None
        and _timestamp(_text(observation.get("change_observed_at"), "change_observed_at"), "change")
        > _timestamp(cutoff, "cutoff")
    }
    if changed_sources:
        return BaselineObservationDecision(
            fixture_id,
            "BLOCK",
            "NONE",
            "HKLEG_BASE_OBSERVATION_POST_CUTOFF_CHANGE",
            cutoff,
            (),
            tuple(sorted(changed_sources, key=str.encode)),
            "REFREEZE_OR_FINISH_THEN_RUN_UPDATE",
        )
    return BaselineObservationDecision(
        fixture_id,
        "PASS",
        "NONE",
        "HKLEG_BASE_OBSERVATION_FROZEN",
        cutoff,
        tuple(
            sorted(
                (_text(item.get("observation_id"), "observation_id") for item in observations),
                key=str.encode,
            )
        ),
        (),
        "RUN_HKLEG_BASE_INV_001",
    )


def _evidence_role(artifact: dict[str, JsonValue]) -> str | None:
    representation = artifact.get("representation")
    language = artifact.get("language")
    if representation == "CURRENT_XML" and language == "en":
        return "EN_CURRENT_XML"
    if representation == "CURRENT_XML" and language == "zh-Hant":
        return "ZH_HANT_CURRENT_XML"
    if representation == "OFFICIAL_COPY" and language == "en":
        return "EN_OFFICIAL_COPY"
    if representation == "OFFICIAL_COPY" and language == "zh-Hant":
        return "ZH_HANT_OFFICIAL_COPY"
    return None


def _evaluate_hk_baseline_evidence(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineEvidenceDecision:
    """Require matching bilingual current XML and official HKeL copies."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    official_version_id = _text(input_document.get("official_version_id"), "official_version_id")
    artifacts = _objects(input_document.get("artifacts"), "artifacts")
    by_role: dict[str, dict[str, JsonValue]] = {}
    historical_present = False
    for artifact in artifacts:
        if artifact.get("source_id") == HK_PAST_DATA_SOURCE_ID:
            historical_present = True
            continue
        role = _evidence_role(artifact)
        if role is None or role in by_role:
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "evidence role")
        by_role[role] = artifact

    missing_roles = _REQUIRED_EVIDENCE_ROLES.difference(by_role)
    if historical_present and missing_roles:
        return BaselineEvidenceDecision(
            fixture_id,
            "BLOCK",
            "COVERAGE_GAP",
            "HKLEG_BASE_EVIDENCE_HISTORICAL_SUBSTITUTION_FORBIDDEN",
            "NONE",
            (),
            tuple(sorted(missing_roles, key=str.encode)),
            scope_id,
            "REJECT_HISTORICAL_SUBSTITUTION",
        )
    if missing_roles:
        return BaselineEvidenceDecision(
            fixture_id,
            "BLOCK",
            "COVERAGE_GAP",
            "HKLEG_BASE_EVIDENCE_REQUIRED_ARTIFACT_MISSING",
            "NONE",
            (),
            tuple(sorted(missing_roles, key=str.encode)),
            scope_id,
            "COMPLETE_CURRENT_BILINGUAL_EVIDENCE",
        )

    required_artifacts = tuple(by_role[role] for role in sorted(by_role, key=str.encode))
    if any(
        artifact.get("version_id") != official_version_id
        or artifact.get("reconciliation") != "MATCH"
        for artifact in required_artifacts
    ):
        return BaselineEvidenceDecision(
            fixture_id,
            "QUARANTINE",
            "NONE",
            "HKLEG_BASE_EVIDENCE_VERSION_OR_CONTENT_CONFLICT",
            "NONE",
            (),
            (),
            scope_id,
            "QUARANTINE_EVIDENCE_CONFLICT",
        )

    copy_statuses = {
        _text(artifact.get("copy_status"), "copy_status")
        for role, artifact in by_role.items()
        if role.endswith("OFFICIAL_COPY")
    }
    if copy_statuses == {"VERIFIED"}:
        evidence_mode: Literal["VERIFIED", "ASSISTED", "MIXED"] = "VERIFIED"
    elif copy_statuses == {"ASSISTED"}:
        evidence_mode = "ASSISTED"
    else:
        evidence_mode = "MIXED"
    return BaselineEvidenceDecision(
        fixture_id,
        "PASS",
        "NONE",
        "HKLEG_BASE_EVIDENCE_RECONCILED",
        evidence_mode,
        tuple(
            sorted(
                (_text(artifact.get("artifact_id"), "artifact_id") for artifact in artifacts),
                key=str.encode,
            )
        ),
        (),
        scope_id,
        "RUN_HKLEG_BASE_STATE_001",
    )


@dataclass(frozen=True, slots=True)
class _StateData:
    scope_id: str
    official_version_id: str
    facts: dict[str, JsonValue]
    support: dict[str, JsonValue]
    unresolved_sources: tuple[str, ...]
    conflicting_sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _StateResult:
    outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    next_action: str
    source_contract_review_required: bool = False
    conflicting_source_ids: tuple[str, ...] = ()
    unresolved_source_ids: tuple[str, ...] = ()
    unresolved_fact_codes: tuple[str, ...] = ()


def _parse_state_input(input_document: dict[str, JsonValue]) -> _StateData:
    predecessors = _objects(input_document.get("predecessor_results"), "predecessor_results")
    predecessor_results = tuple(
        (_text(item.get("rule_id"), "predecessor rule_id"), item.get("processing_outcome"))
        for item in predecessors
    )
    expected_results = (
        (HK_BASELINE_INVENTORY_RULE_ID, "PASS"),
        (HK_BASELINE_EVIDENCE_RULE_ID, "PASS"),
    )
    if predecessor_results != expected_results:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "state predecessors")
    facts = input_document.get("state_facts")
    support = input_document.get("rulebook_support")
    if not isinstance(facts, dict) or not isinstance(support, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "state facts")
    return _StateData(
        _text(input_document.get("scope_id"), "scope_id"),
        _text(input_document.get("official_version_id"), "official_version_id"),
        facts,
        support,
        tuple(
            sorted(
                _texts(input_document.get("unresolved_source_ids"), "unresolved_source_ids"),
                key=str.encode,
            )
        ),
        tuple(
            sorted(
                _texts(input_document.get("conflicting_source_ids"), "conflicting_source_ids"),
                key=str.encode,
            )
        ),
    )


def _state_status_fields(data: _StateData) -> dict[str, JsonValue]:
    return {
        "ITEM_STATUS": data.facts.get("item_status"),
        "PROVISION_STATUS": data.facts.get("provision_status"),
        "STRUCTURE_STATUS": data.facts.get("structure_status"),
        "STATUS_LOCATION_MAPPING": data.facts.get("status_mapping"),
    }


def _state_unknown_semantics(data: _StateData) -> _StateResult | None:
    if data.facts.get("semantics_status") != "UNKNOWN":
        return None
    return _StateResult(
        "BLOCK",
        "COVERAGE_GAP",
        "HKLEG_BASE_STATE_SOURCE_SEMANTICS_UNKNOWN",
        "OPEN_SOURCE_CONTRACT_REVIEW",
        source_contract_review_required=True,
        unresolved_source_ids=data.unresolved_sources,
        unresolved_fact_codes=("SOURCE_SEMANTICS",),
    )


def _state_missing_signals(data: _StateData) -> _StateResult | None:
    missing = {code for code, value in _state_status_fields(data).items() if value == "MISSING"}
    if data.facts.get("accepted_signal_set_complete") is not True:
        missing.add("ACCEPTED_SIGNAL_SET")
    if not missing:
        return None
    return _StateResult(
        "BLOCK",
        "COVERAGE_GAP",
        "HKLEG_BASE_STATE_REQUIRED_SIGNAL_MISSING",
        "COMPLETE_REQUIRED_STATE_SIGNALS",
        unresolved_source_ids=data.unresolved_sources,
        unresolved_fact_codes=tuple(sorted(missing, key=str.encode)),
    )


def _state_conflict(data: _StateData) -> _StateResult | None:
    conflict_facts: set[str] = set()
    conflicting_sources = data.conflicting_sources
    if conflicting_sources:
        conflict_facts.add("ACCEPTED_SIGNAL_CONFLICT")
    if data.facts.get("commencement_support") == "CONFLICTING":
        conflict_facts.add("COMMENCEMENT_SUPPORT")
    if data.facts.get("status_version_id") != data.official_version_id:
        conflict_facts.add("OFFICIAL_VERSION")
        conflicting_sources = tuple(
            sorted({*conflicting_sources, HK_CURRENT_DATA_SOURCE_ID}, key=str.encode)
        )
    if not conflict_facts:
        return None
    return _StateResult(
        "QUARANTINE",
        "NONE",
        "HKLEG_BASE_STATE_ACCEPTED_SIGNAL_CONFLICT",
        "QUARANTINE_PRESENT_STATE_CONFLICT",
        conflicting_source_ids=conflicting_sources,
        unresolved_fact_codes=tuple(sorted(conflict_facts, key=str.encode)),
    )


def _state_ambiguity(data: _StateData) -> _StateResult | None:
    ambiguous = {
        code
        for code, value in _state_status_fields(data).items()
        if value in {"PARTIAL", "AMBIGUOUS"}
    }
    if not ambiguous:
        return None
    return _StateResult(
        "QUARANTINE",
        "NONE",
        "HKLEG_BASE_STATE_STATUS_OR_STRUCTURE_AMBIGUOUS",
        "OPEN_TARGETED_STATE_REVIEW",
        unresolved_fact_codes=tuple(sorted(ambiguous, key=str.encode)),
    )


def _state_unproved_effect(data: _StateData) -> _StateResult | None:
    if data.facts.get("commencement_support") == "PROVED":
        return None
    return _StateResult(
        "BLOCK",
        "NONE",
        "HKLEG_BASE_STATE_OPERATIVE_EFFECT_NOT_PROVED",
        "OPEN_TARGETED_COMMENCEMENT_REVIEW",
        unresolved_fact_codes=("COMMENCEMENT_SUPPORT",),
    )


def _state_missing_rule_support(data: _StateData) -> _StateResult | None:
    missing = tuple(
        code
        for code, supported in (
            ("RULEBOOK_OWNERSHIP", data.support.get("ownership_supported")),
            ("RULEBOOK_DISPOSITION", data.support.get("operative_disposition_supported")),
        )
        if supported is not True
    )
    if not missing:
        return None
    return _StateResult(
        "BLOCK",
        "COVERAGE_GAP",
        "HKLEG_BASE_STATE_RULEBOOK_SUPPORT_MISSING",
        "COMPLETE_RULEBOOK_STATE_SUPPORT",
        unresolved_fact_codes=missing,
    )


def _state_established(data: _StateData) -> _StateResult:
    expected = {
        "ITEM_STATUS": "CURRENT",
        "PROVISION_STATUS": "OPERATIVE",
        "STRUCTURE_STATUS": "COMPLETE",
        "STATUS_LOCATION_MAPPING": "COMPLETE",
    }
    if _state_status_fields(data) != expected:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "unsupported state facts")
    return _StateResult(
        "PASS",
        "NONE",
        "HKLEG_BASE_STATE_PRESENT_OPERATIVE_ESTABLISHED",
        "RUN_HKLEG_BASE_LIMIT_001",
    )


def _state_decision(
    fixture_id: str, data: _StateData, result: _StateResult
) -> BaselineStateDecision:
    passed = result.outcome == "PASS"
    return BaselineStateDecision(
        fixture_id,
        result.outcome,
        result.coverage_effect,
        result.source_contract_review_required,
        result.reason_code,
        "OPERATIVE_CURRENT" if passed else "UNRESOLVED",
        "PENDING_LIMIT_RULE" if passed else "NONE",
        result.conflicting_source_ids,
        result.unresolved_source_ids,
        result.unresolved_fact_codes,
        data.scope_id,
        result.next_action,
    )


def _evaluate_hk_baseline_state(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineStateDecision:
    """Establish only a complete, unambiguous present operative state."""
    data = _parse_state_input(input_document)
    checks = (
        _state_unknown_semantics,
        _state_missing_signals,
        _state_conflict,
        _state_ambiguity,
        _state_unproved_effect,
        _state_missing_rule_support,
    )
    result = next((candidate for check in checks if (candidate := check(data)) is not None), None)
    return _state_decision(fixture_id, data, result or _state_established(data))


def _evaluate_hk_baseline_limit(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineLimitDecision:
    """Reject every historical assertion not proved by the present-state path."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    predecessor = input_document.get("predecessor_result")
    expected_predecessor: dict[str, JsonValue] = {
        "rule_id": HK_BASELINE_STATE_RULE_ID,
        "processing_outcome": "PASS",
        "present_state": "OPERATIVE_CURRENT",
        "historical_assertion_scope": "PENDING_LIMIT_RULE",
    }
    if predecessor != expected_predecessor:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "limit predecessor")
    assertions = _texts(
        input_document.get("proposed_historical_assertion_codes"),
        "proposed_historical_assertion_codes",
    )
    precedence = (
        ("HISTORICAL_LEGAL_EVENT", "HKLEG_BASE_LIMIT_HISTORICAL_EVENT_FORBIDDEN"),
        ("HISTORICAL_EFFECTIVE_DATE", "HKLEG_BASE_LIMIT_EFFECTIVE_DATE_FORBIDDEN"),
        ("IDENTITY_OR_CONTINUITY_RELATIONSHIP", "HKLEG_BASE_LIMIT_CONTINUITY_FORBIDDEN"),
        ("COMPLETE_HISTORICAL_EVENT_CHAIN", "HKLEG_BASE_LIMIT_COMPLETE_HISTORY_FORBIDDEN"),
    )
    rejected = next((code for code, _ in precedence if code in assertions), None)
    if rejected is None:
        return BaselineLimitDecision(
            fixture_id,
            "PASS",
            "HKLEG_BASE_LIMIT_PRESENT_STATE_ONLY",
            "PRESENT_STATE_ONLY",
            (),
            scope_id,
            "RUN_HKLEG_BASE_ID_001",
        )
    reason = next(reason_code for code, reason_code in precedence if code == rejected)
    return BaselineLimitDecision(
        fixture_id,
        "BLOCK",
        reason,
        "NONE",
        tuple(sorted(assertions, key=str.encode)),
        scope_id,
        "REMOVE_UNSUPPORTED_HISTORICAL_ASSERTIONS",
    )


def _evaluate_hk_baseline_identity(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineIdentityDecision:
    """Request opaque identities without importing source or legacy identity semantics."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    expected_predecessor: dict[str, JsonValue] = {
        "rule_id": HK_BASELINE_LIMIT_RULE_ID,
        "processing_outcome": "PASS",
        "historical_assertion_scope": "PRESENT_STATE_ONLY",
    }
    if input_document.get("predecessor_result") != expected_predecessor:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "identity predecessor")
    aliases = tuple(
        sorted(
            (
                (_text(alias.get("alias_type"), "alias_type"), _text(alias.get("value"), "alias"))
                for alias in _objects(input_document.get("aliases"), "aliases")
            ),
            key=lambda alias: (alias[0].encode(), alias[1].encode()),
        )
    )
    relationships = tuple(
        sorted(
            _texts(input_document.get("proposed_relationship_codes"), "relationships"),
            key=str.encode,
        )
    )
    if input_document.get("identity_ambiguity") != "CLEAR":
        return BaselineIdentityDecision(
            fixture_id,
            "QUARANTINE",
            "HKLEG_BASE_ID_DUPLICATE_OR_CONTINUITY_AMBIGUOUS",
            (),
            aliases,
            relationships,
            scope_id,
            "RUN_HKLEG_BASE_REVIEW_001",
        )
    if relationships:
        return BaselineIdentityDecision(
            fixture_id,
            "BLOCK",
            "HKLEG_BASE_ID_UNPROVED_RELATIONSHIP_FORBIDDEN",
            (),
            aliases,
            relationships,
            scope_id,
            "REMOVE_UNPROVED_RELATIONSHIPS",
        )
    if input_document.get("authoritative_identity_basis") != "REGISTER_ALLOCATION":
        return BaselineIdentityDecision(
            fixture_id,
            "BLOCK",
            "HKLEG_BASE_ID_NON_REGISTER_IDENTITY_FORBIDDEN",
            (),
            aliases,
            (),
            scope_id,
            "USE_REGISTER_ALLOCATION_ONLY",
        )
    return BaselineIdentityDecision(
        fixture_id,
        "PASS",
        "HKLEG_BASE_ID_GREENFIELD_ALLOCATION_REQUESTED",
        _IDENTITY_LAYERS,
        aliases,
        (),
        scope_id,
        "RUN_HKLEG_BASE_DISP_001",
    )


def _evaluate_hk_baseline_disposition(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineDispositionDecision:
    """Assign one supported disposition without promoting a single source signal."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    basis = _text(input_document.get("disposition_basis"), "disposition_basis")
    identity_checkpoint = _text(input_document.get("identity_checkpoint"), "identity_checkpoint")
    if basis == "OPERATIVE_EVENT_WITHOUT_CURRENT_CONSOLIDATION":
        if identity_checkpoint != "NOT_APPLICABLE_TO_BLOCKED_PATH":
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "disposition identity")
        return BaselineDispositionDecision(
            fixture_id,
            "BLOCK",
            "NOT_APPLICABLE",
            "COVERAGE_GAP",
            "HKLEG_BASE_DISP_CURRENT_CONSOLIDATION_GAP",
            scope_id,
            "APPLY_HKLEG_CURRENT_EVENT_001",
        )
    if basis == "UNSUPPORTED_SIGNAL_ONLY":
        if identity_checkpoint != "NOT_APPLICABLE_TO_BLOCKED_PATH":
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "disposition identity")
        return BaselineDispositionDecision(
            fixture_id,
            "BLOCK",
            "NOT_APPLICABLE",
            "NONE",
            "HKLEG_BASE_DISP_SINGLE_SIGNAL_INSUFFICIENT",
            scope_id,
            "COMPLETE_LEGAL_TESTS",
        )
    if basis == "UNRESOLVED_MATERIAL_FACT":
        if identity_checkpoint != "IDENTITY_UNRESOLVED":
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "disposition identity")
        return BaselineDispositionDecision(
            fixture_id,
            "QUARANTINE",
            "QUARANTINE",
            "NONE",
            "HKLEG_BASE_DISP_QUARANTINE_REQUIRED",
            scope_id,
            "PRESERVE_QUARANTINE",
        )
    if identity_checkpoint != "GREENFIELD_ALLOCATION_REQUESTED":
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "disposition identity")
    supported = {
        "PRESENT_OPERATIVE_SUPPORTED": (
            "SEARCHABLE_CURRENT",
            "HKLEG_BASE_DISP_SEARCHABLE_CURRENT_SUPPORTED",
            "RUN_HKLEG_BASE_REC_001",
        ),
        "VALIDLY_ENACTED_NOT_OPERATIVE": (
            "WAITING_ROOM",
            "HKLEG_BASE_DISP_WAITING_ROOM_SUPPORTED",
            "PRESERVE_NON_SEARCHABLE_ACCOUNTING",
        ),
        "PRESENT_EFFECT_REPRESENTED_ELSEWHERE": (
            "EVIDENCE_ONLY",
            "HKLEG_BASE_DISP_EVIDENCE_ONLY_SUPPORTED",
            "PRESERVE_NON_SEARCHABLE_ACCOUNTING",
        ),
        "CEASED_OR_SUPERSEDED_PROVED": (
            "HISTORICAL",
            "HKLEG_BASE_DISP_HISTORICAL_SUPPORTED",
            "PRESERVE_NON_SEARCHABLE_ACCOUNTING",
        ),
    }
    try:
        disposition, reason, next_action = supported[basis]
    except KeyError as error:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, basis) from error
    return BaselineDispositionDecision(
        fixture_id,
        "PASS",
        disposition,
        "NONE",
        reason,
        scope_id,
        next_action,
    )


def _record_text_values(content: dict[str, JsonValue]) -> tuple[str, ...]:
    values: list[str] = []
    for language in ("english", "traditional_chinese"):
        block = content.get(language)
        if not isinstance(block, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, language)
        values.extend(
            _text(block.get(field), f"{language}.{field}")
            for field in ("instrument_title", "citation", "locator", "text")
        )
        heading = block.get("heading")
        if heading is not None:
            values.append(_text(heading, f"{language}.heading"))
    return tuple(values)


def _canonical_source_text(values: tuple[str, ...]) -> bool:
    return all(
        normalize("NFC", value) == value
        and "\r" not in value
        and value == value.strip("\n")
        and all(line == line.rstrip(" ") for line in value.split("\n"))
        for value in values
    )


def _render_bilingual_record(content: dict[str, JsonValue]) -> str:
    english = content.get("english")
    chinese = content.get("traditional_chinese")
    if not isinstance(english, dict) or not isinstance(chinese, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "bilingual content")
    full_colon = "\uff1a"
    full_open = "\uff08"
    full_close = "\uff09"
    english_lines = [
        "[English — Authentic Text]",
        (
            f"Instrument: {_text(english.get('instrument_title'), 'english title')} "
            f"({_text(english.get('citation'), 'english citation')})"
        ),
        f"Provision: {_text(english.get('locator'), 'english locator')}",
    ]
    if english.get("heading") is not None:
        english_lines.append(f"Heading: {_text(english.get('heading'), 'english heading')}")
    english_lines.extend(("Text:", _text(english.get("text"), "english text")))
    chinese_lines = [
        "[繁體中文 — 真確文本]",
        (
            f"法例{full_colon}{_text(chinese.get('instrument_title'), 'chinese title')}"
            f"{full_open}{_text(chinese.get('citation'), 'chinese citation')}{full_close}"
        ),
        f"條文{full_colon}{_text(chinese.get('locator'), 'chinese locator')}",
    ]
    if chinese.get("heading") is not None:
        chinese_lines.append(f"標題{full_colon}{_text(chinese.get('heading'), 'chinese heading')}")
    chinese_lines.extend((f"正文{full_colon}", _text(chinese.get("text"), "chinese text")))
    return "\n".join(english_lines) + "\n\n" + "\n".join(chinese_lines)


def _evaluate_hk_baseline_record(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineRecordDecision:
    """Construct one exact six-field bilingual candidate or emit no record."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    disposition = _text(input_document.get("legal_disposition"), "legal_disposition")
    if disposition != "SEARCHABLE_CURRENT":
        return BaselineRecordDecision(
            fixture_id,
            "PASS",
            disposition,
            "NONE",
            "HKLEG_BASE_REC_NON_SEARCHABLE_EXCLUDED",
            None,
            None,
            scope_id,
            "PRESERVE_NON_SEARCHABLE_ACCOUNTING",
        )
    if input_document.get("identity_origin") != "REGISTER_ALLOCATED":
        return BaselineRecordDecision(
            fixture_id,
            "BLOCK",
            disposition,
            "NONE",
            "HKLEG_BASE_REC_LEGACY_ID_FORBIDDEN",
            None,
            None,
            scope_id,
            "REQUEST_NEW_REGISTER_IDENTITY",
        )
    if input_document.get("bilingual_alignment") != "COMPLETE":
        return BaselineRecordDecision(
            fixture_id,
            "BLOCK",
            disposition,
            "COVERAGE_GAP",
            "HKLEG_BASE_REC_BILINGUAL_CONTENT_INCOMPLETE",
            None,
            None,
            scope_id,
            "COMPLETE_BILINGUAL_CONTENT",
        )
    content = input_document.get("content")
    if not isinstance(content, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "content")
    if input_document.get("renderer_conformance") != "EXACT" or not _canonical_source_text(
        _record_text_values(content)
    ):
        return BaselineRecordDecision(
            fixture_id,
            "QUARANTINE",
            disposition,
            "NONE",
            "HKLEG_BASE_REC_RENDERING_NON_CANONICAL",
            None,
            None,
            scope_id,
            "QUARANTINE_RENDERING",
        )
    authority_note = _text(input_document.get("authority_note"), "authority_note")
    if input_document.get("authority_note_approved") is not True or authority_note != "None":
        return BaselineRecordDecision(
            fixture_id,
            "BLOCK",
            disposition,
            "NONE",
            "HKLEG_BASE_REC_AUTHORITY_NOTE_UNAPPROVED",
            None,
            None,
            scope_id,
            "USE_APPROVED_AUTHORITY_NOTE",
        )
    metadata: dict[str, JsonValue] = {
        "text": _render_bilingual_record(content),
        **_SYNTHETIC_RECORD_PROFILE,
        "authority_note": authority_note,
    }
    candidate: dict[str, JsonValue] = {
        "id": _text(input_document.get("search_record_id"), "search_record_id"),
        "metadata": metadata,
    }
    return BaselineRecordDecision(
        fixture_id,
        "PASS",
        disposition,
        "NONE",
        "HKLEG_BASE_REC_CANDIDATE_CREATED",
        candidate,
        _fingerprint(canonicalize(checked_json_value(metadata))),
        scope_id,
        "RUN_HKLEG_BASE_REL_001",
    )


@dataclass(frozen=True, slots=True)
class _ReleaseAccountingData:
    scope_id: str
    expected_object_ids: set[str]
    expected_location_ids: set[str]
    expected_coverage_gap_ids: set[str]
    expected_quarantine_ids: set[str]
    expected_investigation_ids: set[str]
    entries: tuple[dict[str, JsonValue], ...]
    predecessor_release_id: JsonValue | None
    unresolved_completeness_gap_ids: tuple[str, ...]


def _parse_release_accounting(input_document: dict[str, JsonValue]) -> _ReleaseAccountingData:
    expected = input_document.get("expected_accounting")
    if not isinstance(expected, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "expected accounting")
    return _ReleaseAccountingData(
        _text(input_document.get("scope_id"), "scope_id"),
        set(_texts(expected.get("object_ids"), "object_ids")),
        set(_texts(expected.get("location_ids"), "location_ids")),
        set(_texts(expected.get("coverage_gap_ids"), "coverage_gap_ids")),
        set(_texts(expected.get("quarantine_ids"), "quarantine_ids")),
        set(_texts(expected.get("investigation_ids"), "investigation_ids")),
        _objects(input_document.get("accounting_entries"), "accounting_entries"),
        input_document.get("predecessor_release_id"),
        _texts(
            input_document.get("unresolved_completeness_gap_ids"),
            "unresolved_completeness_gap_ids",
        ),
    )


def _release_accounting_block(
    fixture_id: str,
    data: _ReleaseAccountingData,
    reason_code: str,
    unresolved_ids: set[str] | tuple[str, ...],
    next_action: str,
) -> BaselineReleaseAccountingDecision:
    return BaselineReleaseAccountingDecision(
        fixture_id,
        "BLOCK",
        "COVERAGE_GAP",
        reason_code,
        (),
        (),
        tuple(sorted(unresolved_ids, key=str.encode)),
        None,
        data.scope_id,
        next_action,
    )


def _entry_reference_union(entries: tuple[dict[str, JsonValue], ...], field: str) -> set[str]:
    result: set[str] = set()
    for entry in entries:
        result.update(_texts(entry.get(field), field))
    return result


def _evaluate_hk_baseline_release_accounting(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineReleaseAccountingDecision:
    """Require total initial-release accounting without sealing a release."""
    data = _parse_release_accounting(input_document)
    if data.predecessor_release_id is not None:
        return _release_accounting_block(
            fixture_id,
            data,
            "HKLEG_BASE_REL_PREDECESSOR_FORBIDDEN",
            (_text(data.predecessor_release_id, "predecessor_release_id"),),
            "REMOVE_BASELINE_PREDECESSOR",
        )
    entry_objects = [_text(entry.get("object_id"), "object_id") for entry in data.entries]
    entry_locations = [_text(entry.get("location_id"), "location_id") for entry in data.entries]
    duplicate_locations = {
        location_id for location_id in entry_locations if entry_locations.count(location_id) > 1
    }
    unresolved_inventory = (
        data.expected_object_ids.symmetric_difference(entry_objects)
        | data.expected_location_ids.symmetric_difference(entry_locations)
        | duplicate_locations
    )
    if unresolved_inventory:
        return _release_accounting_block(
            fixture_id,
            data,
            "HKLEG_BASE_REL_OBJECT_OR_LOCATION_UNACCOUNTED",
            unresolved_inventory,
            "COMPLETE_OBJECT_AND_LOCATION_ACCOUNTING",
        )
    inconsistent_locations: set[str] = set()
    for entry in data.entries:
        disposition = _text(entry.get("legal_disposition"), "legal_disposition")
        record_id = entry.get("record_id")
        quarantine_ids = _texts(entry.get("quarantine_ids"), "quarantine_ids")
        if (disposition == "SEARCHABLE_CURRENT") != (record_id is not None) or (
            disposition == "QUARANTINE"
        ) != bool(quarantine_ids):
            inconsistent_locations.add(_text(entry.get("location_id"), "location_id"))
    if inconsistent_locations:
        return _release_accounting_block(
            fixture_id,
            data,
            "HKLEG_BASE_REL_RESULT_ACCOUNTING_INCONSISTENT",
            inconsistent_locations,
            "RECONCILE_DISPOSITIONS_AND_OUTPUTS",
        )
    reference_drift = (
        data.expected_coverage_gap_ids.symmetric_difference(
            _entry_reference_union(data.entries, "coverage_gap_ids")
        )
        | data.expected_quarantine_ids.symmetric_difference(
            _entry_reference_union(data.entries, "quarantine_ids")
        )
        | data.expected_investigation_ids.symmetric_difference(
            _entry_reference_union(data.entries, "investigation_ids")
        )
    )
    if reference_drift:
        return _release_accounting_block(
            fixture_id,
            data,
            "HKLEG_BASE_REL_REFERENCE_UNACCOUNTED",
            reference_drift,
            "COMPLETE_REFERENCE_ACCOUNTING",
        )
    if data.unresolved_completeness_gap_ids:
        return _release_accounting_block(
            fixture_id,
            data,
            "HKLEG_BASE_REL_COMPLETENESS_UNRESOLVED",
            data.unresolved_completeness_gap_ids,
            "RESOLVE_COMPLETENESS_GAPS",
        )
    return BaselineReleaseAccountingDecision(
        fixture_id,
        "PASS",
        "NONE",
        "HKLEG_BASE_REL_INITIAL_RELEASE_ACCOUNTED",
        tuple(sorted(data.expected_object_ids, key=str.encode)),
        tuple(sorted(data.expected_location_ids, key=str.encode)),
        (),
        _fingerprint(canonicalize(checked_json_value(input_document))),
        data.scope_id,
        "BUILD_CANDIDATE_CORPUS_RELEASE",
    )


def _review_block(
    fixture_id: str,
    scope_id: str,
    reason_code: str,
    next_action: str,
) -> BaselineReviewDecision:
    return BaselineReviewDecision(
        fixture_id,
        "BLOCK",
        reason_code,
        None,
        scope_id,
        next_action,
    )


def _evaluate_hk_baseline_review(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineReviewDecision:
    """Open only one bounded historical investigation for a material question."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    trigger = _text(input_document.get("trigger"), "trigger")
    if trigger == "NO_MATERIAL_UNCERTAINTY":
        return _review_block(
            fixture_id,
            scope_id,
            "HKLEG_BASE_REVIEW_NO_MATERIAL_UNCERTAINTY",
            "CONTINUE_CLEAR_BASELINE",
        )
    if input_document.get("investigation_scope") != "TARGETED":
        return _review_block(
            fixture_id,
            scope_id,
            "HKLEG_BASE_REVIEW_BROAD_HISTORY_FORBIDDEN",
            "NARROW_INVESTIGATION",
        )
    requested_sources = _texts(input_document.get("requested_source_ids"), "requested sources")
    if not set(requested_sources).issubset(_REVIEW_SOURCE_IDS):
        return _review_block(
            fixture_id,
            scope_id,
            "HKLEG_BASE_REVIEW_SOURCE_NOT_PERMITTED",
            "USE_REGISTERED_HISTORICAL_SOURCES",
        )
    permitted_facts = _texts(input_document.get("permitted_fact_codes"), "permitted facts")
    expected_fact = _REVIEW_FACT_BY_TRIGGER.get(trigger)
    if expected_fact is None or permitted_facts != (expected_fact,):
        return _review_block(
            fixture_id,
            scope_id,
            "HKLEG_BASE_REVIEW_FACT_SCOPE_MISMATCH",
            "ALIGN_FACT_SCOPE",
        )
    review_task: dict[str, JsonValue] = {
        "review_task_id": _text(input_document.get("review_task_id"), "review_task_id"),
        "trigger": trigger,
        "question": _text(input_document.get("question"), "question"),
        "affected_object_ids": list(
            _texts(input_document.get("affected_object_ids"), "affected_object_ids")
        ),
        "requested_source_ids": list(requested_sources),
        "permitted_fact_codes": list(permitted_facts),
        "stopping_condition": _text(input_document.get("stopping_condition"), "stopping_condition"),
        "responsible_legal_desk": _text(
            input_document.get("responsible_legal_desk"), "responsible_legal_desk"
        ),
    }
    return BaselineReviewDecision(
        fixture_id,
        "PASS",
        "HKLEG_BASE_REVIEW_TARGETED_INVESTIGATION_OPENED",
        review_task,
        scope_id,
        "RUN_HKLEG_BASE_HIST_001",
    )


@dataclass(frozen=True, slots=True)
class _HistoryContext:
    fixture_id: str
    scope_id: str
    affected_object_ids: tuple[str, ...]
    scope_completeness_impossible: bool


@dataclass(frozen=True, slots=True)
class _HistoryResult:
    outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    coverage_effect: Literal["NONE", "COVERAGE_GAP"]
    reason_code: str
    established_fact_code: str | None
    next_action: str


def _history_decision(
    context: _HistoryContext,
    result: _HistoryResult,
) -> BaselineHistoryDecision:
    return BaselineHistoryDecision(
        context.fixture_id,
        result.outcome,
        result.coverage_effect,
        result.reason_code,
        result.established_fact_code,
        context.affected_object_ids,
        not context.scope_completeness_impossible,
        context.scope_id,
        result.next_action,
    )


def _evaluate_hk_baseline_history(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineHistoryDecision:
    """Use historical evidence only for the exact fact authorized by Review."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    context = _HistoryContext(
        fixture_id,
        scope_id,
        _texts(input_document.get("affected_object_ids"), "affected_object_ids"),
        input_document.get("scope_completeness_impossible") is True,
    )
    review_task = input_document.get("review_task")
    evidence = input_document.get("historical_evidence")
    if not isinstance(review_task, dict) or not isinstance(evidence, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "history input")
    requested_sources = _texts(review_task.get("requested_source_ids"), "requested sources")
    permitted_fact = _text(review_task.get("permitted_fact_code"), "permitted fact")
    source_id = _text(evidence.get("source_id"), "source_id")
    if source_id not in requested_sources:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "unrequested history source")
    if (
        input_document.get("attempted_current_evidence_substitution") is True
        or input_document.get("attempted_reconstruction") is True
    ):
        return _history_decision(
            context,
            _HistoryResult(
                "BLOCK",
                "NONE",
                "HKLEG_BASE_HIST_CURRENT_EVIDENCE_SUBSTITUTION_FORBIDDEN",
                None,
                "USE_CURRENT_EVIDENCE_OR_SEPARATE_RECONSTRUCTION_PATH",
            ),
        )
    if evidence.get("availability") != "AVAILABLE":
        return _history_decision(
            context,
            _HistoryResult(
                "BLOCK",
                "COVERAGE_GAP",
                "HKLEG_BASE_HIST_REQUESTED_EVIDENCE_UNAVAILABLE",
                None,
                "BLOCK_AFFECTED_DECISION",
            ),
        )
    evidence_result = _text(evidence.get("evidence_result"), "evidence_result")
    if evidence_result == "SIMILARITY_ONLY" or evidence.get("proof_basis") == "SIMILARITY_ONLY":
        return _history_decision(
            context,
            _HistoryResult(
                "BLOCK",
                "NONE",
                "HKLEG_BASE_HIST_SIMILARITY_ONLY_FORBIDDEN",
                None,
                "REQUIRE_EXPLICIT_OFFICIAL_EVIDENCE",
            ),
        )
    if evidence_result == "CONFLICT":
        return _history_decision(
            context,
            _HistoryResult(
                "QUARANTINE",
                "NONE",
                "HKLEG_BASE_HIST_EVIDENCE_CONFLICT",
                None,
                "QUARANTINE_AFFECTED_DECISION",
            ),
        )
    proposed_fact = _text(input_document.get("proposed_fact_code"), "proposed_fact_code")
    if (
        evidence_result != "PROVES_PERMITTED_FACT"
        or proposed_fact != permitted_fact
        or source_id in _HISTORY_DISCOVERY_ONLY_SOURCES
    ):
        return _history_decision(
            context,
            _HistoryResult(
                "BLOCK",
                "NONE",
                "HKLEG_BASE_HIST_EVIDENCE_INSUFFICIENT",
                None,
                "BLOCK_AFFECTED_DECISION",
            ),
        )
    return _history_decision(
        context,
        _HistoryResult(
            "PASS",
            "NONE",
            "HKLEG_BASE_HIST_PERMITTED_FACT_ESTABLISHED",
            proposed_fact,
            "RESUME_BASELINE_DECISION",
        ),
    )


@dataclass(frozen=True, slots=True)
class _ChangeContext:
    fixture_id: str
    scope_id: str
    cutoff: str


@dataclass(frozen=True, slots=True)
class _ChangeResult:
    outcome: Literal["PASS", "BLOCK"]
    reason_code: str
    baseline_action: str
    preserved_cutoff: str | None
    observation_status: str
    next_action: str


def _change_decision(
    context: _ChangeContext,
    result: _ChangeResult,
) -> BaselineChangeDecision:
    return BaselineChangeDecision(
        context.fixture_id,
        result.outcome,
        result.reason_code,
        result.baseline_action,
        result.preserved_cutoff,
        result.observation_status,
        context.scope_id,
        result.next_action,
    )


def _evaluate_hk_baseline_change(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineChangeDecision:
    """Keep post-cutoff changes separate from one frozen baseline."""
    context = _ChangeContext(
        fixture_id,
        _text(input_document.get("scope_id"), "scope_id"),
        _text(input_document.get("cutoff"), "cutoff"),
    )
    if input_document.get("post_cutoff_change_observed") is not True:
        result = _ChangeResult(
            "PASS",
            "HKLEG_BASE_CHANGE_NO_POST_CUTOFF_CHANGE",
            "CONTINUE_ORIGINAL",
            context.cutoff,
            "NOT_APPLICABLE",
            "CONTINUE_ORIGINAL_BASELINE",
        )
    elif input_document.get("frozen_package_preserved") is not True:
        result = _ChangeResult(
            "BLOCK",
            "HKLEG_BASE_CHANGE_FROZEN_PACKAGE_NOT_PRESERVED",
            "BLOCKED",
            None,
            "NONE",
            "RESTORE_FROZEN_PACKAGE",
        )
    elif input_document.get("new_observation_recorded_separately") is not True:
        result = _ChangeResult(
            "BLOCK",
            "HKLEG_BASE_CHANGE_NEW_OBSERVATION_NOT_SEPARATE",
            "BLOCKED",
            context.cutoff,
            "NONE",
            "RECORD_SEPARATE_OBSERVATION",
        )
    elif (strategy := _text(input_document.get("selected_strategy"), "selected_strategy")) == (
        "SILENTLY_MIX"
    ):
        result = _ChangeResult(
            "BLOCK",
            "HKLEG_BASE_CHANGE_MIXED_CUTOFF_FORBIDDEN",
            "BLOCKED",
            context.cutoff,
            "RECORDED_SEPARATELY",
            "SELECT_PERMITTED_STRATEGY",
        )
    elif input_document.get("later_currency_claimed_before_update") is True:
        result = _ChangeResult(
            "BLOCK",
            "HKLEG_BASE_CHANGE_LATER_CURRENCY_CLAIM_FORBIDDEN",
            "BLOCKED",
            context.cutoff,
            "RECORDED_SEPARATELY",
            "REMOVE_UNSUPPORTED_LATER_CURRENCY_CLAIM",
        )
    elif strategy == "ABANDON_AND_REFREEZE":
        result = _ChangeResult(
            "PASS",
            "HKLEG_BASE_CHANGE_REFREEZE_SELECTED",
            "ABANDON_AND_REFREEZE",
            context.cutoff,
            "RECORDED_SEPARATELY",
            "REFREEZE_AT_LATER_CUTOFF",
        )
    elif strategy == "FINISH_ORIGINAL_THEN_UPDATE":
        result = _ChangeResult(
            "PASS",
            "HKLEG_BASE_CHANGE_FINISH_THEN_UPDATE_SELECTED",
            "FINISH_ORIGINAL_THEN_UPDATE",
            context.cutoff,
            "RECORDED_SEPARATELY",
            "FINISH_ORIGINAL_THEN_RUN_UPDATE",
        )
    else:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, strategy)
    return _change_decision(context, result)


def _evaluate_hk_current_observation(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentObservationDecision:
    """Route one complete ordinary-update observation set without legal inference."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    observations = _objects(input_document.get("due_observations"), "due_observations")
    unavailable = tuple(
        observation
        for observation in observations
        if observation.get("status") != "COMPLETE" or observation.get("fresh") is not True
    )
    unavailable_objects = tuple(
        sorted(
            {
                object_id
                for observation in unavailable
                for object_id in _texts(
                    observation.get("affected_object_ids"), "affected_object_ids"
                )
            },
            key=str.encode,
        )
    )
    if any(
        observation.get("dependency_scope") == "RELEASE_BLOCKING" for observation in unavailable
    ):
        return CurrentObservationDecision(
            fixture_id,
            HK_CURRENT_OBSERVATION_RULE_IDS[2],
            "BLOCK",
            "COVERAGE_GAP",
            "HKLEG_CURRENT_OBS_RELEASE_BLOCKING_OBSERVATION_UNAVAILABLE",
            "OBSERVATION_UNAVAILABLE",
            unavailable_objects,
            work_deduplication="NOT_APPLICABLE",
            release_choice_required=True,
            affected_scope_id=scope_id,
            next_action="SELECT_EXPLICIT_UNAVAILABLE_SCOPE_OUTCOME",
        )
    if unavailable:
        return CurrentObservationDecision(
            fixture_id,
            HK_CURRENT_OBSERVATION_RULE_IDS[2],
            "BLOCK",
            "NONE",
            "HKLEG_CURRENT_OBS_AFFECTED_WORK_OBSERVATION_UNAVAILABLE",
            "AFFECTED_WORK_BLOCKED",
            unavailable_objects,
            work_deduplication="NOT_APPLICABLE",
            release_choice_required=False,
            affected_scope_id=scope_id,
            next_action="BLOCK_DEPENDENT_AFFECTED_WORK",
        )
    affected_objects = tuple(
        sorted(
            {
                object_id
                for observation in observations
                if observation.get("changed") is True
                for object_id in _texts(
                    observation.get("affected_object_ids"), "affected_object_ids"
                )
            },
            key=str.encode,
        )
    )
    affected = bool(affected_objects) or any(
        input_document.get(signal) is True
        for signal in ("unmatched_gazette_event", "editorial_or_spec_signal", "urgent_signal_open")
    )
    if input_document.get("current_inventory_matches_predecessor") is not True:
        affected = True
    if not affected:
        return CurrentObservationDecision(
            fixture_id,
            HK_CURRENT_OBSERVATION_RULE_IDS[0],
            "PASS",
            "NONE",
            "HKLEG_CURRENT_OBS_SUPPORTED_NO_CHANGE",
            "SUPPORTED_NO_CHANGE",
            (),
            work_deduplication="NOT_APPLICABLE",
            release_choice_required=False,
            affected_scope_id=scope_id,
            next_action="REUSE_EXISTING_CORPUS_RELEASE",
        )
    work_key_value = input_document.get("detected_work_key")
    work_key = _text(work_key_value, "detected_work_key")
    open_work_keys = _texts(input_document.get("open_work_keys"), "open_work_keys")
    duplicate = work_key in open_work_keys
    return CurrentObservationDecision(
        fixture_id,
        HK_CURRENT_OBSERVATION_RULE_IDS[1],
        "PASS",
        "NONE",
        (
            "HKLEG_CURRENT_OBS_AFFECTED_WORK_DEDUPLICATED"
            if duplicate
            else "HKLEG_CURRENT_OBS_AFFECTED_WORK_OPENED"
        ),
        "AFFECTED_ACQUISITION_REQUIRED",
        affected_objects,
        work_deduplication="DEDUPLICATED_EXISTING" if duplicate else "OPENED_NEW",
        release_choice_required=False,
        affected_scope_id=scope_id,
        next_action="ACQUIRE_COMPLETE_AFFECTED_ARTIFACTS",
    )


def _evaluate_hk_current_evidence(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentEvidenceDecision:
    """Select only a complete latest applicable official bilingual HKeL bundle."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    affected_objects = _texts(input_document.get("affected_object_ids"), "affected_object_ids")
    version_order = _texts(input_document.get("applicable_version_order"), "version order")
    selected_version = version_order[-1]
    candidates = tuple(
        bundle
        for bundle in _objects(input_document.get("candidate_bundles"), "candidate_bundles")
        if bundle.get("version") == selected_version
    )
    official = tuple(bundle for bundle in candidates if bundle.get("official_hkel") is True)
    if candidates and not official:
        return CurrentEvidenceDecision(
            fixture_id,
            (HK_CURRENT_EVIDENCE_RULE_IDS[1],),
            "BLOCK",
            "NONE",
            "HKLEG_CURRENT_EVID_COPY_SOURCE_NOT_ADMITTED",
            None,
            None,
            affected_objects,
            scope_id,
            "ACQUIRE_OFFICIAL_HKEL_BUNDLE",
        )
    required_flags = (
        "en_xml_present",
        "zh_hant_xml_present",
        "en_copy_present",
        "zh_hant_copy_present",
        "required_assets_complete",
        "source_capture_complete",
    )
    if not official or not any(
        all(bundle.get(flag) is True for flag in required_flags) for bundle in official
    ):
        coverage_effect: Literal["NONE", "COVERAGE_GAP"] = (
            "COVERAGE_GAP" if input_document.get("current_law_coverage_depends") is True else "NONE"
        )
        return CurrentEvidenceDecision(
            fixture_id,
            (HK_CURRENT_EVIDENCE_RULE_IDS[0], HK_CURRENT_EVIDENCE_RULE_IDS[2]),
            "BLOCK",
            coverage_effect,
            "HKLEG_CURRENT_EVID_AFFECTED_EVIDENCE_UNAVAILABLE",
            None,
            None,
            affected_objects,
            scope_id,
            "RESOLVE_AFFECTED_EVIDENCE_GAP",
        )
    if not any(bundle.get("bilingual_version_match") is True for bundle in official):
        return CurrentEvidenceDecision(
            fixture_id,
            (HK_CURRENT_EVIDENCE_RULE_IDS[0], HK_CURRENT_EVIDENCE_RULE_IDS[3]),
            "QUARANTINE",
            "NONE",
            "HKLEG_CURRENT_EVID_BILINGUAL_VERSION_CONFLICT",
            None,
            selected_version,
            affected_objects,
            scope_id,
            "QUARANTINE_AFFECTED_EVIDENCE",
        )
    aligned = tuple(bundle for bundle in official if bundle.get("bilingual_version_match") is True)
    if not any(bundle.get("xml_copy_content_match") is True for bundle in aligned):
        reason = "HKLEG_CURRENT_EVID_XML_COPY_CONFLICT"
    elif not any(
        bundle.get("structure_reconciled") is True
        and bundle.get("identity_reconciled") is True
        and bundle.get("evidence_label_present") is True
        for bundle in aligned
    ):
        reason = "HKLEG_CURRENT_EVID_STRUCTURE_OR_IDENTITY_CONFLICT"
    else:
        valid = tuple(
            bundle
            for bundle in aligned
            if bundle.get("xml_copy_content_match") is True
            and bundle.get("structure_reconciled") is True
            and bundle.get("identity_reconciled") is True
            and bundle.get("evidence_label_present") is True
        )
        classes = {_text(bundle.get("evidence_class"), "evidence_class") for bundle in valid}
        selected_class = "VERIFIED" if "VERIFIED" in classes else "ASSISTED"
        if classes == {"VERIFIED", "ASSISTED"}:
            reason = "HKLEG_CURRENT_EVID_VERIFIED_PREFERRED_SAME_VERSION"
        elif selected_class == "VERIFIED":
            reason = "HKLEG_CURRENT_EVID_COMPLETE_VERIFIED_BUNDLE"
        else:
            reason = "HKLEG_CURRENT_EVID_COMPLETE_ASSISTED_BUNDLE"
        return CurrentEvidenceDecision(
            fixture_id,
            (HK_CURRENT_EVIDENCE_RULE_IDS[0], HK_CURRENT_EVIDENCE_RULE_IDS[1]),
            "PASS",
            "NONE",
            reason,
            selected_class,
            selected_version,
            affected_objects,
            scope_id,
            "RUN_HKLEG_CURRENT_DIFF_001",
        )
    return CurrentEvidenceDecision(
        fixture_id,
        (HK_CURRENT_EVIDENCE_RULE_IDS[0], HK_CURRENT_EVIDENCE_RULE_IDS[3]),
        "QUARANTINE",
        "NONE",
        reason,
        None,
        selected_version,
        affected_objects,
        scope_id,
        "QUARANTINE_AFFECTED_EVIDENCE",
    )


def _evaluate_hk_current_difference(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentDifferenceDecision:
    """Classify observable accepted-bundle differences without legal inference."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    object_id = _text(input_document.get("object_id"), "object_id")
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    predecessor_fields = (
        "predecessor_bundle_fingerprint",
        "predecessor_payload_fingerprint",
        "predecessor_structure_fingerprint",
        "predecessor_location_id",
    )
    predecessor_present = input_document.get("predecessor_object_present") is True
    predecessor_values = tuple(input_document.get(field) for field in predecessor_fields)
    if (predecessor_present and any(value is None for value in predecessor_values)) or (
        not predecessor_present and any(value is not None for value in predecessor_values)
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "predecessor object")
    if input_document.get("predecessor_release_present") is not True:
        if predecessor_present:
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "predecessor release")
        return CurrentDifferenceDecision(
            fixture_id,
            HK_CURRENT_DIFFERENCE_RULE_IDS[0],
            "BLOCK",
            "HKLEG_CURRENT_DIFF_INITIAL_BASELINE_REQUIRED",
            None,
            "NONE",
            "NONE",
            object_id,
            scope_id,
            "RUN_HKLEG_BASE_OBS_001",
        )
    if not predecessor_present:
        difference_class = "OBJECT_ADDED"
    else:
        changed = tuple(
            difference_class
            for current_field, predecessor_field, difference_class in (
                (
                    "current_payload_fingerprint",
                    "predecessor_payload_fingerprint",
                    "PAYLOAD_CHANGED",
                ),
                (
                    "current_structure_fingerprint",
                    "predecessor_structure_fingerprint",
                    "STRUCTURE_CHANGED",
                ),
                ("current_location_id", "predecessor_location_id", "LOCATION_REFERENCE_CHANGED"),
            )
            if input_document.get(current_field) != input_document.get(predecessor_field)
        )
        if len(changed) > 1:
            difference_class = "MULTIPLE_OBSERVABLE_DIFFERENCES"
        elif changed:
            difference_class = changed[0]
        elif input_document.get("current_bundle_fingerprint") != input_document.get(
            "predecessor_bundle_fingerprint"
        ):
            difference_class = "EVIDENCE_BUNDLE_CHANGED"
        else:
            difference_class = "EXACT_UNCHANGED"
    if difference_class != "EXACT_UNCHANGED":
        return CurrentDifferenceDecision(
            fixture_id,
            HK_CURRENT_DIFFERENCE_RULE_IDS[0],
            "PASS",
            "HKLEG_CURRENT_DIFF_OBSERVABLE_DIFFERENCE_CLASSIFIED",
            difference_class,
            "REBUILD_REQUIRED",
            "NONE",
            object_id,
            scope_id,
            "RUN_HKLEG_CURRENT_CAUSE_001",
        )
    continuing_support = input_document.get("continuing_support_proved") is True
    return CurrentDifferenceDecision(
        fixture_id,
        HK_CURRENT_DIFFERENCE_RULE_IDS[1],
        "PASS" if continuing_support else "BLOCK",
        (
            "HKLEG_CURRENT_DIFF_EXACT_UNCHANGED_REUSE_ELIGIBLE"
            if continuing_support
            else "HKLEG_CURRENT_DIFF_CONTINUING_SUPPORT_NOT_PROVED"
        ),
        "EXACT_UNCHANGED",
        "REUSE_ELIGIBLE" if continuing_support else "NONE",
        "NONE",
        object_id,
        scope_id,
        (
            "RUN_HKLEG_CURRENT_RELEASE_ACCOUNTING_001"
            if continuing_support
            else "RESOLVE_CONTINUING_SUPPORT"
        ),
    )


def _evaluate_hk_current_cause(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentCauseDecision:
    """Bind a material observable change to accepted cause evidence or quarantine it."""
    object_id = _text(input_document.get("object_id"), "object_id")
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    locations = _texts(input_document.get("affected_location_ids"), "affected_location_ids")
    publication_date_value = input_document.get("publication_date")
    effective_date_value = input_document.get("effective_date")
    publication_date = publication_date_value if isinstance(publication_date_value, str) else None
    effective_date = effective_date_value if isinstance(effective_date_value, str) else None
    if input_document.get("source_contract_changed") is True:
        return CurrentCauseDecision(
            fixture_id=fixture_id,
            rule_id=HK_CURRENT_CAUSE_RULE_IDS[0],
            processing_outcome="BLOCK",
            reason_code="HKLEG_CURRENT_CAUSE_SOURCE_CONTRACT_REVIEW_REQUIRED",
            cause_class=None,
            source_contract_review_required=True,
            affected_object_id=object_id,
            affected_scope_id=scope_id,
            affected_location_ids=locations,
            publication_date=publication_date,
            effective_date=effective_date,
            next_action="OPEN_SOURCE_CONTRACT_REVIEW",
        )
    technical = input_document.get("technical_republication")
    if not isinstance(technical, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "technical_republication")
    technical_exact = all(value is True for value in technical.values())
    cause_type_value = input_document.get("cause_type")
    cause_type = cause_type_value if isinstance(cause_type_value, str) else None
    if cause_type == "TECHNICAL_REPUBLICATION" and technical_exact:
        return CurrentCauseDecision(
            fixture_id=fixture_id,
            rule_id=HK_CURRENT_CAUSE_RULE_IDS[0],
            processing_outcome="PASS",
            reason_code="HKLEG_CURRENT_CAUSE_TECHNICAL_REPUBLICATION_PROVED",
            cause_class="NON_SERVING_TECHNICAL_REPUBLICATION",
            source_contract_review_required=False,
            affected_object_id=object_id,
            affected_scope_id=scope_id,
            affected_location_ids=locations,
            publication_date=publication_date,
            effective_date=effective_date,
            next_action="RUN_HKLEG_CURRENT_REL_001",
        )
    accepted_causes = {
        "GAZETTE_EVENT": (HK_GAZETTE_SOURCE_ID, "HKLEG_CURRENT_CAUSE_GAZETTE_EVENT_PROVED"),
        "EDITORIAL_RECORD": (
            HK_EDITORIAL_RECORDS_SOURCE_ID,
            "HKLEG_CURRENT_CAUSE_EDITORIAL_RECORD_PROVED",
        ),
    }
    cause_binding = accepted_causes.get(cause_type or "")
    evidence_fingerprints = _texts(
        input_document.get("cause_evidence_fingerprints"), "cause_evidence_fingerprints"
    )
    complete = (
        cause_binding is not None
        and input_document.get("cause_source_id") == cause_binding[0]
        and input_document.get("cause_evidence_complete") is True
        and publication_date is not None
        and effective_date is not None
        and bool(evidence_fingerprints)
    )
    matches = input_document.get("cause_matches_after_bundle") is True
    if complete and matches and cause_binding is not None:
        return CurrentCauseDecision(
            fixture_id=fixture_id,
            rule_id=HK_CURRENT_CAUSE_RULE_IDS[0],
            processing_outcome="PASS",
            reason_code=cause_binding[1],
            cause_class=cause_type,
            source_contract_review_required=False,
            affected_object_id=object_id,
            affected_scope_id=scope_id,
            affected_location_ids=locations,
            publication_date=publication_date,
            effective_date=effective_date,
            next_action="RUN_HKLEG_CURRENT_DISP_001",
        )
    conflict = input_document.get("cause_evidence_conflicts") is True or (complete and not matches)
    return CurrentCauseDecision(
        fixture_id=fixture_id,
        rule_id=HK_CURRENT_CAUSE_RULE_IDS[1],
        processing_outcome="QUARANTINE",
        reason_code=(
            "HKLEG_CURRENT_CAUSE_EVIDENCE_CONFLICT"
            if conflict
            else "HKLEG_CURRENT_CAUSE_ACCEPTED_CAUSE_UNAVAILABLE"
        ),
        cause_class=None,
        source_contract_review_required=False,
        affected_object_id=object_id,
        affected_scope_id=scope_id,
        affected_location_ids=locations,
        publication_date=publication_date,
        effective_date=effective_date,
        next_action="QUARANTINE_UNEXPLAINED_CHANGE",
    )


def _parse_current_commencement_input(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> _CurrentCommencementContext:
    publication_value = input_document.get("publication_date")
    effective_value = input_document.get("effective_date")
    return _CurrentCommencementContext(
        fixture_id=fixture_id,
        cutoff=_text(input_document.get("cutoff"), "cutoff"),
        commencement_mode=_text(input_document.get("commencement_mode"), "commencement_mode"),
        controlling_notice_state=_text(
            input_document.get("controlling_notice_state"), "notice state"
        ),
        event_evidence_complete=input_document.get("event_evidence_complete") is True,
        event_evidence_authentic=input_document.get("event_evidence_authentic") is True,
        event_evidence_conflicts=input_document.get("event_evidence_conflicts") is True,
        condition_exact=input_document.get("condition_exact") is True,
        condition_satisfied_at_cutoff=(input_document.get("condition_satisfied_at_cutoff") is True),
        affected_object_id=_text(input_document.get("object_id"), "object_id"),
        affected_scope_id=_text(input_document.get("scope_id"), "scope_id"),
        publication_date=(publication_value if isinstance(publication_value, str) else None),
        effective_date=(effective_value if isinstance(effective_value, str) else None),
        operative_provision_fingerprint=_text(
            input_document.get("operative_provision_fingerprint"),
            "operative provision fingerprint",
        ),
        event_evidence_fingerprints=_texts(
            input_document.get("event_evidence_fingerprints"),
            "event evidence fingerprints",
        ),
        all_location_ids=_texts(input_document.get("all_location_ids"), "all location ids"),
        affected_location_ids=_texts(
            input_document.get("affected_location_ids"), "affected location ids"
        ),
        pre_event_operative_location_ids=_texts(
            input_document.get("pre_event_operative_location_ids"),
            "pre-event operative location ids",
        ),
        affected_location_scope=_text(
            input_document.get("affected_location_scope"), "affected location scope"
        ),
    )


def _current_commencement_precondition(
    context: _CurrentCommencementContext,
) -> _CurrentCommencementResult | None:
    unresolved = _CurrentCommencementResult(
        "BLOCK",
        "NOT_APPLICABLE",
        "HKLEG_CURRENT_COMMENCEMENT_EVIDENCE_INCOMPLETE",
        "NONE",
        "UNRESOLVED",
        None,
        (),
        (),
        "RESOLVE_COMMENCEMENT_EVIDENCE",
    )
    if context.event_evidence_conflicts or context.controlling_notice_state == "UNRESOLVED":
        return _CurrentCommencementResult(
            "QUARANTINE",
            "QUARANTINE",
            "HKLEG_CURRENT_COMMENCEMENT_EVIDENCE_CONFLICT",
            "NONE",
            "UNRESOLVED",
            None,
            (),
            (),
            "QUARANTINE_COMMENCEMENT_EVIDENCE",
        )
    needs_date = context.commencement_mode != "CONDITIONAL_EVENT" or (
        context.condition_satisfied_at_cutoff
    )
    notice_valid = context.commencement_mode != "APPOINTED_DATE" or (
        context.controlling_notice_state in {"CURRENT", "AMENDED_CURRENT"}
    )
    condition_valid = context.commencement_mode != "CONDITIONAL_EVENT" or (context.condition_exact)
    evidence_complete = (
        context.event_evidence_complete
        and context.event_evidence_authentic
        and context.publication_date is not None
        and bool(context.event_evidence_fingerprints)
        and (not needs_date or context.effective_date is not None)
        and notice_valid
        and condition_valid
    )
    if not evidence_complete:
        return unresolved
    all_set = frozenset(context.all_location_ids)
    affected_set = frozenset(context.affected_location_ids)
    pre_event_set = frozenset(context.pre_event_operative_location_ids)
    partial_valid = (
        context.commencement_mode == "PARTIAL"
        and context.affected_location_scope == "EXACT_LOCATIONS"
        and bool(affected_set)
        and affected_set < all_set
        and pre_event_set <= all_set
        and affected_set.isdisjoint(pre_event_set)
    )
    whole_valid = (
        context.commencement_mode != "PARTIAL"
        and context.affected_location_scope == "WHOLE_INSTRUMENT"
        and affected_set == all_set
        and not pre_event_set
    )
    if not context.all_location_ids or not (partial_valid or whole_valid):
        return _CurrentCommencementResult(
            "QUARANTINE",
            "QUARANTINE",
            "HKLEG_CURRENT_COMMENCEMENT_AFFECTED_SET_INVALID",
            "NONE",
            "UNRESOLVED",
            None,
            (),
            (),
            "QUARANTINE_AFFECTED_SET",
        )
    if context.publication_date is None:
        return unresolved
    timing_invalid = _timestamp(context.publication_date, "publication date") > _timestamp(
        context.cutoff, "cutoff"
    ) or (
        context.commencement_mode == "DEFAULT_ON_PUBLICATION"
        and context.effective_date != context.publication_date
    )
    return unresolved if timing_invalid else None


def _current_commencement_result(
    context: _CurrentCommencementContext,
) -> _CurrentCommencementResult:
    cutoff = _timestamp(context.cutoff, "cutoff")
    effective_at_cutoff = (
        context.effective_date is not None
        and _timestamp(context.effective_date, "effective date") <= cutoff
    )
    operative = effective_at_cutoff and (
        context.commencement_mode != "CONDITIONAL_EVENT" or context.condition_satisfied_at_cutoff
    )
    operative_reasons = {
        "DEFAULT_ON_PUBLICATION": "HKLEG_CURRENT_COMMENCEMENT_DEFAULT_OPERATIVE_PROVED",
        "FIXED_DATE": "HKLEG_CURRENT_COMMENCEMENT_FIXED_DATE_OPERATIVE_PROVED",
        "APPOINTED_DATE": "HKLEG_CURRENT_COMMENCEMENT_APPOINTED_DATE_OPERATIVE_PROVED",
        "CONDITIONAL_EVENT": "HKLEG_CURRENT_COMMENCEMENT_CONDITIONAL_EVENT_OPERATIVE_PROVED",
        "PARTIAL": "HKLEG_CURRENT_COMMENCEMENT_PARTIAL_OPERATIVE_PROVED",
    }
    pending_reasons = {
        "FIXED_DATE": "HKLEG_CURRENT_COMMENCEMENT_FIXED_DATE_PENDING",
        "APPOINTED_DATE": "HKLEG_CURRENT_COMMENCEMENT_APPOINTED_DATE_PENDING",
        "CONDITIONAL_EVENT": "HKLEG_CURRENT_COMMENCEMENT_CONDITIONAL_EVENT_PENDING",
        "PARTIAL": "HKLEG_CURRENT_COMMENCEMENT_PARTIAL_PENDING",
    }
    pre_event = frozenset(context.pre_event_operative_location_ids)
    affected = frozenset(context.affected_location_ids)
    operative_set = pre_event | affected if operative else pre_event
    operative_locations = tuple(
        location for location in context.all_location_ids if location in operative_set
    )
    pending_locations = tuple(
        location for location in context.all_location_ids if location not in operative_set
    )
    if operative:
        state: Literal["OPERATIVE", "PARTIALLY_OPERATIVE"] = (
            "PARTIALLY_OPERATIVE" if pending_locations else "OPERATIVE"
        )
        return _CurrentCommencementResult(
            processing_outcome="PASS",
            legal_disposition="NOT_APPLICABLE",
            reason_code=operative_reasons[context.commencement_mode],
            event_fact_output="LEGAL_STATUS_EVENT",
            operative_state=state,
            event_operative_at_cutoff=True,
            operative_location_ids=operative_locations,
            pending_location_ids=pending_locations,
            next_action=(
                "SPLIT_OPERATIVE_AND_WAITING_LOCATIONS"
                if pending_locations
                else "RUN_HKLEG_CURRENT_EVENT_001"
            ),
        )
    return _CurrentCommencementResult(
        processing_outcome="PASS",
        legal_disposition="WAITING_ROOM",
        reason_code=pending_reasons[context.commencement_mode],
        event_fact_output="LEGAL_STATUS_EVENT",
        operative_state=("PARTIALLY_OPERATIVE" if operative_locations else "NOT_YET_OPERATIVE"),
        event_operative_at_cutoff=False,
        operative_location_ids=operative_locations,
        pending_location_ids=pending_locations,
        next_action=(
            "SPLIT_OPERATIVE_AND_WAITING_LOCATIONS"
            if operative_locations
            else "ASSIGN_WAITING_ROOM"
        ),
    )


def _evaluate_hk_current_commencement(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentCommencementDecision:
    """Establish commencement only from exact retained operative evidence."""
    context = _parse_current_commencement_input(fixture_id, input_document)
    result = _current_commencement_precondition(context)
    return _current_commencement_decision(
        context,
        result if result is not None else _current_commencement_result(context),
    )


def _parse_current_cessation_input(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> _CurrentCessationContext:
    effective_value = input_document.get("effective_date")
    return _CurrentCessationContext(
        fixture_id=fixture_id,
        cutoff=_text(input_document.get("cutoff"), "cutoff"),
        event_type=_text(input_document.get("event_type"), "event type"),
        controlling_notice_state=_text(
            input_document.get("controlling_notice_state"), "notice state"
        ),
        event_evidence_complete=input_document.get("event_evidence_complete") is True,
        event_evidence_authentic=input_document.get("event_evidence_authentic") is True,
        event_evidence_conflicts=input_document.get("event_evidence_conflicts") is True,
        revival_continuity_proved=(input_document.get("revival_continuity_proved") is True),
        affected_object_id=_text(input_document.get("object_id"), "object id"),
        affected_scope_id=_text(input_document.get("scope_id"), "scope id"),
        effective_date=(effective_value if isinstance(effective_value, str) else None),
        operative_provision_fingerprint=_text(
            input_document.get("operative_provision_fingerprint"),
            "operative provision fingerprint",
        ),
        event_evidence_fingerprints=_texts(
            input_document.get("event_evidence_fingerprints"),
            "event evidence fingerprints",
        ),
        prior_event_history_fingerprint=_text(
            input_document.get("prior_event_history_fingerprint"),
            "prior event history fingerprint",
        ),
        all_location_ids=_texts(input_document.get("all_location_ids"), "all locations"),
        affected_location_ids=_texts(
            input_document.get("affected_location_ids"), "affected locations"
        ),
        pre_event_operative_location_ids=_texts(
            input_document.get("pre_event_operative_location_ids"),
            "pre-event operative locations",
        ),
        pre_event_ceased_location_ids=_texts(
            input_document.get("pre_event_ceased_location_ids"),
            "pre-event ceased locations",
        ),
        affected_location_scope=_text(
            input_document.get("affected_location_scope"), "affected location scope"
        ),
    )


def _current_cessation_precondition(
    context: _CurrentCessationContext,
) -> _CurrentCessationResult | None:
    if context.event_evidence_conflicts or context.controlling_notice_state == "UNRESOLVED":
        return _CurrentCessationResult(
            "QUARANTINE",
            "QUARANTINE",
            "HKLEG_CURRENT_CESSATION_EVIDENCE_CONFLICT",
            "NONE",
            "UNRESOLVED",
            "NONE",
            "PRESERVE_UNCHANGED",
            None,
            (),
            (),
            "QUARANTINE_CESSATION_EVIDENCE",
        )
    notice_valid = context.event_type != "REVOCATION" or (
        context.controlling_notice_state in {"CURRENT", "AMENDED_CURRENT"}
    )
    complete = (
        context.event_evidence_complete
        and context.event_evidence_authentic
        and bool(context.event_evidence_fingerprints)
        and context.effective_date is not None
        and notice_valid
    )
    if not complete:
        return _CurrentCessationResult(
            "BLOCK",
            "NOT_APPLICABLE",
            "HKLEG_CURRENT_CESSATION_EVIDENCE_INCOMPLETE",
            "NONE",
            "UNRESOLVED",
            "NONE",
            "PRESERVE_UNCHANGED",
            None,
            (),
            (),
            "RESOLVE_CESSATION_EVIDENCE",
        )
    if context.event_type == "REVIVAL" and not context.revival_continuity_proved:
        return _CurrentCessationResult(
            "QUARANTINE",
            "QUARANTINE",
            "HKLEG_CURRENT_CESSATION_REVIVAL_CONTINUITY_UNPROVED",
            "NONE",
            "UNRESOLVED",
            "NONE",
            "PRESERVE_UNCHANGED",
            None,
            (),
            (),
            "QUARANTINE_REVIVAL_CONTINUITY",
        )
    all_set = frozenset(context.all_location_ids)
    operative_set = frozenset(context.pre_event_operative_location_ids)
    ceased_set = frozenset(context.pre_event_ceased_location_ids)
    affected_set = frozenset(context.affected_location_ids)
    partition_valid = (
        bool(all_set)
        and operative_set.isdisjoint(ceased_set)
        and operative_set | ceased_set == all_set
    )
    scope_valid = (
        context.affected_location_scope == "WHOLE_INSTRUMENT" and affected_set == all_set
    ) or (
        context.affected_location_scope == "EXACT_LOCATIONS"
        and bool(affected_set)
        and affected_set < all_set
    )
    source_state = ceased_set if context.event_type == "REVIVAL" else operative_set
    if not partition_valid or not scope_valid or not affected_set <= source_state:
        return _CurrentCessationResult(
            "QUARANTINE",
            "QUARANTINE",
            "HKLEG_CURRENT_CESSATION_AFFECTED_STATE_INVALID",
            "NONE",
            "UNRESOLVED",
            "NONE",
            "PRESERVE_UNCHANGED",
            None,
            (),
            (),
            "QUARANTINE_AFFECTED_STATE",
        )
    return None


def _current_cessation_result(context: _CurrentCessationContext) -> _CurrentCessationResult:
    if context.effective_date is None:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "effective date")
    effective = _timestamp(context.effective_date, "effective date")
    operative_at_cutoff = effective <= _timestamp(context.cutoff, "cutoff")
    operative_before = frozenset(context.pre_event_operative_location_ids)
    ceased_before = frozenset(context.pre_event_ceased_location_ids)
    affected = frozenset(context.affected_location_ids)
    pending_reasons = {
        "REPEAL": "HKLEG_CURRENT_CESSATION_REPEAL_PENDING",
        "REVOCATION": "HKLEG_CURRENT_CESSATION_REVOCATION_PENDING",
        "EXPIRY": "HKLEG_CURRENT_CESSATION_EXPIRY_PENDING",
        "REVIVAL": "HKLEG_CURRENT_CESSATION_REVIVAL_PENDING",
    }
    operative_reasons = {
        "REPEAL": "HKLEG_CURRENT_CESSATION_REPEAL_OPERATIVE_PROVED",
        "REVOCATION": "HKLEG_CURRENT_CESSATION_REVOCATION_OPERATIVE_PROVED",
        "EXPIRY": "HKLEG_CURRENT_CESSATION_EXPIRY_OPERATIVE_PROVED",
        "REVIVAL": "HKLEG_CURRENT_CESSATION_REVIVAL_OPERATIVE_PROVED",
    }
    if not operative_at_cutoff:
        return _CurrentCessationResult(
            processing_outcome="PASS",
            legal_disposition=("HISTORICAL" if not operative_before else "NOT_APPLICABLE"),
            reason_code=pending_reasons[context.event_type],
            event_fact_output="LEGAL_STATUS_EVENT",
            status_effect="PENDING",
            identity_effect=(
                "REVIVAL_CONTINUITY_PROVED"
                if context.event_type == "REVIVAL"
                else "PRESERVE_EXISTING_IDENTITIES"
            ),
            event_history_action="APPEND_EVENT",
            event_operative_at_cutoff=False,
            post_event_operative_location_ids=context.pre_event_operative_location_ids,
            post_event_ceased_location_ids=context.pre_event_ceased_location_ids,
            next_action="KEEP_PRE_EVENT_STATE",
        )
    revival = context.event_type == "REVIVAL"
    operative_after = operative_before | affected if revival else operative_before - affected
    ceased_after = ceased_before - affected if revival else ceased_before | affected
    operative_locations = tuple(
        location for location in context.all_location_ids if location in operative_after
    )
    ceased_locations = tuple(
        location for location in context.all_location_ids if location in ceased_after
    )
    return _CurrentCessationResult(
        processing_outcome="PASS",
        legal_disposition=("HISTORICAL" if not operative_locations else "NOT_APPLICABLE"),
        reason_code=operative_reasons[context.event_type],
        event_fact_output="LEGAL_STATUS_EVENT",
        status_effect=("REVIVED" if revival else "CEASED"),
        identity_effect=(
            "REVIVAL_CONTINUITY_PROVED" if revival else "PRESERVE_EXISTING_IDENTITIES"
        ),
        event_history_action="APPEND_EVENT",
        event_operative_at_cutoff=True,
        post_event_operative_location_ids=operative_locations,
        post_event_ceased_location_ids=ceased_locations,
        next_action=(
            "RUN_HKLEG_CURRENT_EVENT_001"
            if revival
            else (
                "SPLIT_CURRENT_AND_HISTORICAL_LOCATIONS"
                if operative_locations
                else "ASSIGN_HISTORICAL"
            )
        ),
    )


def _evaluate_hk_current_cessation(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentCessationDecision:
    """Apply exact cessation or revival facts without inventing identities."""
    context = _parse_current_cessation_input(fixture_id, input_document)
    result = _current_cessation_precondition(context)
    return _current_cessation_decision(
        context,
        result if result is not None else _current_cessation_result(context),
    )


def _parse_current_publication_input(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> _CurrentPublicationContext:
    publication_value = input_document.get("publication_date")
    english_value = input_document.get("english_material_fingerprint")
    chinese_value = input_document.get("traditional_chinese_material_fingerprint")
    authority_value = input_document.get("enabling_authority_fingerprint")
    return _CurrentPublicationContext(
        fixture_id=fixture_id,
        cutoff=_text(input_document.get("cutoff"), "cutoff"),
        source_id=_text(input_document.get("source_id"), "source id"),
        gazette_issue_kind=_text(input_document.get("gazette_issue_kind"), "issue kind"),
        gazette_material_class=_text(
            input_document.get("gazette_material_class"), "material class"
        ),
        publication_claim=_text(input_document.get("publication_claim"), "publication claim"),
        subject_reference=_text(input_document.get("subject_reference"), "subject reference"),
        issue_id=_text(input_document.get("issue_id"), "issue id"),
        supplement_or_notice_id=_text(
            input_document.get("supplement_or_notice_id"), "supplement or notice id"
        ),
        instrument_or_notice_number=_text(
            input_document.get("instrument_or_notice_number"), "instrument or notice number"
        ),
        publication_date=(publication_value if isinstance(publication_value, str) else None),
        artifact_fingerprint=_text(
            input_document.get("artifact_fingerprint"), "artifact fingerprint"
        ),
        source_metadata_fingerprint=_text(
            input_document.get("source_metadata_fingerprint"), "source metadata fingerprint"
        ),
        english_material_fingerprint=(english_value if isinstance(english_value, str) else None),
        traditional_chinese_material_fingerprint=(
            chinese_value if isinstance(chinese_value, str) else None
        ),
        enabling_authority_fingerprint=(
            authority_value if isinstance(authority_value, str) else None
        ),
        evidence_complete=input_document.get("evidence_complete") is True,
        evidence_authentic=input_document.get("evidence_authentic") is True,
        evidence_conflicts=input_document.get("evidence_conflicts") is True,
        bilingual_material_complete=(input_document.get("bilingual_material_complete") is True),
        claim_matches_material_class=(input_document.get("claim_matches_material_class") is True),
    )


def _publication_failure(
    *,
    outcome: Literal["BLOCK", "QUARANTINE"],
    reason: str,
    next_action: str,
) -> _CurrentPublicationResult:
    return _CurrentPublicationResult(
        processing_outcome=outcome,
        legal_disposition=("QUARANTINE" if outcome == "QUARANTINE" else "NOT_APPLICABLE"),
        reason_code=reason,
        publication_fact_output="NONE",
        publication_history_action="PRESERVE_UNCHANGED",
        next_action=next_action,
    )


def _current_publication_evidence_precondition(
    context: _CurrentPublicationContext,
) -> _CurrentPublicationResult | None:
    if context.evidence_conflicts or context.source_id != HK_GAZETTE_SOURCE_ID:
        return _publication_failure(
            outcome="QUARANTINE",
            reason="HKLEG_CURRENT_PUBLICATION_EVIDENCE_CONFLICT",
            next_action="QUARANTINE_PUBLICATION_EVIDENCE",
        )
    if (
        not context.evidence_complete
        or not context.evidence_authentic
        or context.publication_date is None
    ):
        return _publication_failure(
            outcome="BLOCK",
            reason="HKLEG_CURRENT_PUBLICATION_EVIDENCE_INCOMPLETE",
            next_action="RESOLVE_PUBLICATION_EVIDENCE",
        )
    full_text_class = context.gazette_material_class in {
        "LEGAL_SUPPLEMENT_1",
        "LEGAL_SUPPLEMENT_2",
        "MAIN_GAZETTE_NOTICE",
    }
    bilingual_complete = (
        context.bilingual_material_complete
        and context.english_material_fingerprint is not None
        and context.traditional_chinese_material_fingerprint is not None
    )
    if full_text_class and not bilingual_complete:
        return _publication_failure(
            outcome="BLOCK",
            reason="HKLEG_CURRENT_PUBLICATION_BILINGUAL_EVIDENCE_INCOMPLETE",
            next_action="RESOLVE_BILINGUAL_PUBLICATION_EVIDENCE",
        )
    return None


def _current_publication_class_precondition(
    context: _CurrentPublicationContext,
) -> _CurrentPublicationResult | None:
    accepted_claims = {
        "LEGAL_SUPPLEMENT_1": frozenset({"ORDINANCE_ENACTMENT"}),
        "LEGAL_SUPPLEMENT_2": frozenset({"SUBSIDIARY_LEGISLATION", "LEGAL_NOTICE"}),
        "MAIN_GAZETTE_NOTICE": frozenset({"LEGAL_NOTICE"}),
        "LEGAL_SUPPLEMENT_3": frozenset({"BILL_INVENTORY"}),
        "OTHER_SUPPLEMENT": frozenset({"OTHER_DISCOVERY"}),
    }
    if (
        not context.claim_matches_material_class
        or context.publication_claim
        not in accepted_claims.get(context.gazette_material_class, frozenset())
    ):
        return _publication_failure(
            outcome="QUARANTINE",
            reason="HKLEG_CURRENT_PUBLICATION_SOURCE_CLASS_CONFLICT",
            next_action="QUARANTINE_PUBLICATION_CLASSIFICATION",
        )
    if (
        context.gazette_material_class == "MAIN_GAZETTE_NOTICE"
        and context.enabling_authority_fingerprint is None
    ):
        return _publication_failure(
            outcome="BLOCK",
            reason="HKLEG_CURRENT_PUBLICATION_EVIDENCE_INCOMPLETE",
            next_action="RESOLVE_PUBLICATION_EVIDENCE",
        )
    if context.publication_date is None:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "publication date")
    if _timestamp(context.publication_date, "publication date") > _timestamp(
        context.cutoff, "cutoff"
    ):
        return _publication_failure(
            outcome="BLOCK",
            reason="HKLEG_CURRENT_PUBLICATION_AFTER_CUTOFF",
            next_action="WAIT_FOR_PUBLICATION_CUTOFF",
        )
    return None


def _current_publication_result(
    context: _CurrentPublicationContext,
) -> _CurrentPublicationResult:
    if context.publication_claim == "ORDINANCE_ENACTMENT":
        return _CurrentPublicationResult(
            "PASS",
            "NOT_APPLICABLE",
            "HKLEG_CURRENT_PUBLICATION_ORDINANCE_ENACTMENT_PROVED",
            "ORDINANCE_ENACTMENT_AND_PUBLICATION",
            "APPEND_PUBLICATION_EVENT",
            "ROUTE_NEW_ITEM_TO_IDENTITY_AND_EVIDENCE",
        )
    if context.publication_claim == "SUBSIDIARY_LEGISLATION":
        return _CurrentPublicationResult(
            "PASS",
            "NOT_APPLICABLE",
            "HKLEG_CURRENT_PUBLICATION_SUBSIDIARY_LEGISLATION_PROVED",
            "SUBSIDIARY_LEGISLATION_PUBLICATION",
            "APPEND_PUBLICATION_EVENT",
            "ROUTE_NEW_ITEM_TO_IDENTITY_AND_EVIDENCE",
        )
    if context.publication_claim == "LEGAL_NOTICE":
        return _CurrentPublicationResult(
            "PASS",
            "EVIDENCE_ONLY",
            "HKLEG_CURRENT_PUBLICATION_NOTICE_PROVED",
            "NOTICE_PUBLICATION",
            "APPEND_PUBLICATION_EVENT",
            "RUN_FACT_SPECIFIC_NOTICE_EVENT_RULE",
        )
    if context.publication_claim == "BILL_INVENTORY":
        return _CurrentPublicationResult(
            "PASS",
            "EVIDENCE_ONLY",
            "HKLEG_CURRENT_PUBLICATION_LEGAL_SUPPLEMENT_3_INVENTORY_ONLY",
            "EXCLUDED_BILL_INVENTORY",
            "RETAIN_INVENTORY_OBSERVATION",
            "ACCOUNT_EXCLUDED_LEGAL_SUPPLEMENT_3",
        )
    return _CurrentPublicationResult(
        "PASS",
        "EVIDENCE_ONLY",
        "HKLEG_CURRENT_PUBLICATION_OTHER_SUPPLEMENT_DISCOVERY_ONLY",
        "DISCOVERY_ONLY",
        "RETAIN_INVENTORY_OBSERVATION",
        "RETAIN_DISCOVERY_ONLY",
    )


def _evaluate_hk_current_publication(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentPublicationDecision:
    """Classify publication without inferring commencement, identity, or text."""
    context = _parse_current_publication_input(fixture_id, input_document)
    evidence_result = _current_publication_evidence_precondition(context)
    result = (
        evidence_result
        if evidence_result is not None
        else _current_publication_class_precondition(context)
    )
    return _current_publication_decision(
        context,
        result if result is not None else _current_publication_result(context),
    )


def _parse_current_text_event_input(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> _CurrentTextEventContext:
    publication_value = input_document.get("publication_date")
    effective_value = input_document.get("effective_date")
    return _CurrentTextEventContext(
        fixture_id=fixture_id,
        cutoff=_text(input_document.get("cutoff"), "cutoff"),
        event_type=_text(input_document.get("event_type"), "event type"),
        affected_object_id=_text(input_document.get("affected_object_id"), "affected object"),
        source_event_object_id=_text(
            input_document.get("source_event_object_id"), "source event object"
        ),
        affected_scope_id=_text(input_document.get("scope_id"), "scope id"),
        cause_source_id=_text(input_document.get("cause_source_id"), "cause source id"),
        publication_date=(publication_value if isinstance(publication_value, str) else None),
        effective_date=(effective_value if isinstance(effective_value, str) else None),
        event_instrument_fingerprint=_text(
            input_document.get("event_instrument_fingerprint"),
            "event instrument fingerprint",
        ),
        event_evidence_fingerprints=_texts(
            input_document.get("event_evidence_fingerprints"),
            "event evidence fingerprints",
        ),
        event_evidence_complete=input_document.get("event_evidence_complete") is True,
        event_evidence_authentic=input_document.get("event_evidence_authentic") is True,
        event_evidence_conflicts=input_document.get("event_evidence_conflicts") is True,
        operation_set_fingerprint=_text(
            input_document.get("operation_set_fingerprint"), "operation set fingerprint"
        ),
        operation_mapping_complete=input_document.get("operation_mapping_complete") is True,
        bilingual_operations_aligned=(input_document.get("bilingual_operations_aligned") is True),
        event_operative_at_cutoff=(input_document.get("event_operative_at_cutoff") is True),
        all_location_ids=_texts(input_document.get("all_location_ids"), "all locations"),
        affected_location_ids=_texts(
            input_document.get("affected_location_ids"), "affected locations"
        ),
        affected_location_scope=_text(
            input_document.get("affected_location_scope"), "affected location scope"
        ),
        matching_resulting_hkel_bundle_available=(
            input_document.get("matching_resulting_hkel_bundle_available") is True
        ),
        resulting_bundle_reflects_event=(
            input_document.get("resulting_bundle_reflects_event") is True
        ),
        prior_event_history_fingerprint=_text(
            input_document.get("prior_event_history_fingerprint"),
            "prior event history fingerprint",
        ),
    )


def _text_event_failure(
    *,
    outcome: Literal["BLOCK", "QUARANTINE"],
    reason: str,
    next_action: str,
) -> _CurrentTextEventResult:
    return _CurrentTextEventResult(
        processing_outcome=outcome,
        legal_disposition=("QUARANTINE" if outcome == "QUARANTINE" else "NOT_APPLICABLE"),
        coverage_effect="NONE",
        reason_code=reason,
        event_fact_output="NONE",
        selection_result="UNRESOLVED",
        event_operative_at_cutoff=None,
        event_history_action="PRESERVE_UNCHANGED",
        next_action=next_action,
    )


def _current_text_event_evidence_precondition(
    context: _CurrentTextEventContext,
) -> _CurrentTextEventResult | None:
    expected_source = {
        "AMENDMENT": HK_GAZETTE_SOURCE_ID,
        "EXPRESS_CORRECTION": HK_GAZETTE_SOURCE_ID,
        "EDITORIAL_AMENDMENT": HK_EDITORIAL_RECORDS_SOURCE_ID,
    }[context.event_type]
    if (
        context.event_evidence_conflicts
        or context.cause_source_id != expected_source
        or context.source_event_object_id == context.affected_object_id
    ):
        return _text_event_failure(
            outcome="QUARANTINE",
            reason="HKLEG_CURRENT_TEXT_EVENT_EVIDENCE_CONFLICT",
            next_action="QUARANTINE_TEXT_EVENT_EVIDENCE",
        )
    complete = (
        context.event_evidence_complete
        and context.event_evidence_authentic
        and context.publication_date is not None
        and context.effective_date is not None
        and bool(context.event_evidence_fingerprints)
    )
    if not complete:
        return _text_event_failure(
            outcome="BLOCK",
            reason="HKLEG_CURRENT_TEXT_EVENT_EVIDENCE_INCOMPLETE",
            next_action="RESOLVE_TEXT_EVENT_EVIDENCE",
        )
    if not context.operation_mapping_complete:
        return _text_event_failure(
            outcome="BLOCK",
            reason="HKLEG_CURRENT_TEXT_EVENT_OPERATION_MAPPING_INCOMPLETE",
            next_action="COMPLETE_OPERATION_MAPPING",
        )
    if not context.bilingual_operations_aligned:
        return _text_event_failure(
            outcome="QUARANTINE",
            reason="HKLEG_CURRENT_TEXT_EVENT_BILINGUAL_OPERATION_CONFLICT",
            next_action="QUARANTINE_BILINGUAL_OPERATION_CONFLICT",
        )
    return None


def _current_text_event_location_timing_precondition(
    context: _CurrentTextEventContext,
) -> _CurrentTextEventResult | None:
    all_set = frozenset(context.all_location_ids)
    affected_set = frozenset(context.affected_location_ids)
    location_set_valid = bool(all_set) and (
        (context.affected_location_scope == "WHOLE_INSTRUMENT" and affected_set == all_set)
        or (
            context.affected_location_scope == "EXACT_LOCATIONS"
            and bool(affected_set)
            and affected_set < all_set
        )
    )
    if not location_set_valid:
        return _text_event_failure(
            outcome="QUARANTINE",
            reason="HKLEG_CURRENT_TEXT_EVENT_AFFECTED_SET_INVALID",
            next_action="QUARANTINE_AFFECTED_SET",
        )
    if context.publication_date is None or context.effective_date is None:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "text event dates")
    published_by_cutoff = _timestamp(context.publication_date, "publication date") <= _timestamp(
        context.cutoff, "cutoff"
    )
    computed_operative = _timestamp(context.effective_date, "effective date") <= _timestamp(
        context.cutoff, "cutoff"
    )
    if not published_by_cutoff:
        return _text_event_failure(
            outcome="BLOCK",
            reason="HKLEG_CURRENT_TEXT_EVENT_EVIDENCE_INCOMPLETE",
            next_action="RESOLVE_TEXT_EVENT_EVIDENCE",
        )
    if computed_operative != context.event_operative_at_cutoff or (
        not context.matching_resulting_hkel_bundle_available
        and context.resulting_bundle_reflects_event
    ):
        return _text_event_failure(
            outcome="QUARANTINE",
            reason="HKLEG_CURRENT_TEXT_EVENT_EVIDENCE_CONFLICT",
            next_action="QUARANTINE_TEXT_EVENT_EVIDENCE",
        )
    return None


def _current_text_event_precondition(
    context: _CurrentTextEventContext,
) -> _CurrentTextEventResult | None:
    evidence_result = _current_text_event_evidence_precondition(context)
    return (
        evidence_result
        if evidence_result is not None
        else _current_text_event_location_timing_precondition(context)
    )


def _current_text_event_result(context: _CurrentTextEventContext) -> _CurrentTextEventResult:
    pending_reasons = {
        "AMENDMENT": "HKLEG_CURRENT_TEXT_EVENT_AMENDMENT_PENDING",
        "EXPRESS_CORRECTION": "HKLEG_CURRENT_TEXT_EVENT_EXPRESS_CORRECTION_PENDING",
        "EDITORIAL_AMENDMENT": "HKLEG_CURRENT_TEXT_EVENT_EDITORIAL_PENDING",
    }
    available_reasons = {
        "AMENDMENT": "HKLEG_CURRENT_TEXT_EVENT_AMENDMENT_CURRENT_BUNDLE_AVAILABLE",
        "EXPRESS_CORRECTION": (
            "HKLEG_CURRENT_TEXT_EVENT_EXPRESS_CORRECTION_CURRENT_BUNDLE_AVAILABLE"
        ),
        "EDITORIAL_AMENDMENT": "HKLEG_CURRENT_TEXT_EVENT_EDITORIAL_CURRENT_BUNDLE_AVAILABLE",
    }
    missing_reasons = {
        "AMENDMENT": "HKLEG_CURRENT_TEXT_EVENT_AMENDMENT_CONSOLIDATION_MISSING",
        "EXPRESS_CORRECTION": ("HKLEG_CURRENT_TEXT_EVENT_EXPRESS_CORRECTION_CONSOLIDATION_MISSING"),
        "EDITORIAL_AMENDMENT": "HKLEG_CURRENT_TEXT_EVENT_EDITORIAL_CONSOLIDATION_MISSING",
    }
    if not context.event_operative_at_cutoff:
        return _CurrentTextEventResult(
            processing_outcome="PASS",
            legal_disposition="WAITING_ROOM",
            coverage_effect="NONE",
            reason_code=pending_reasons[context.event_type],
            event_fact_output="LEGAL_STATUS_EVENT",
            selection_result="KEEP_PRE_EVENT_TEXT",
            event_operative_at_cutoff=False,
            event_history_action="APPEND_EVENT",
            next_action="KEEP_PRE_EVENT_TEXT",
        )
    if context.matching_resulting_hkel_bundle_available:
        if not context.resulting_bundle_reflects_event:
            return _text_event_failure(
                outcome="QUARANTINE",
                reason="HKLEG_CURRENT_TEXT_EVENT_RESULTING_TEXT_CONFLICT",
                next_action="QUARANTINE_RESULTING_TEXT",
            )
        return _CurrentTextEventResult(
            processing_outcome="PASS",
            legal_disposition="NOT_APPLICABLE",
            coverage_effect="NONE",
            reason_code=available_reasons[context.event_type],
            event_fact_output="LEGAL_STATUS_EVENT",
            selection_result="ORDINARY_CURRENT_BUNDLE_REQUIRED",
            event_operative_at_cutoff=True,
            event_history_action="APPEND_EVENT",
            next_action="RUN_HKLEG_CURRENT_EVID_001",
        )
    return _CurrentTextEventResult(
        processing_outcome="PASS",
        legal_disposition="NOT_APPLICABLE",
        coverage_effect="COVERAGE_GAP",
        reason_code=missing_reasons[context.event_type],
        event_fact_output="LEGAL_STATUS_EVENT",
        selection_result="MISSING_CONSOLIDATION_EVENT_ROUTING_REQUIRED",
        event_operative_at_cutoff=True,
        event_history_action="APPEND_EVENT",
        next_action="RUN_HKLEG_CURRENT_EVENT_001",
    )


def _evaluate_hk_current_text_event(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentTextEventDecision:
    """Route exact text-changing events without constructing resulting text."""
    context = _parse_current_text_event_input(fixture_id, input_document)
    result = _current_text_event_precondition(context)
    return _current_text_event_decision(
        context,
        result if result is not None else _current_text_event_result(context),
    )


def _nullable_fingerprint(input_document: dict[str, JsonValue], field: str) -> str | None:
    value = input_document.get(field)
    return value if isinstance(value, str) else None


def _parse_reconstruction_plan_semantic_input(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> _ReconstructionPlanSemanticContext:
    return _ReconstructionPlanSemanticContext(
        fixture_id=fixture_id,
        evidence_bundle_fingerprint=_text(
            input_document.get("evidence_bundle_fingerprint"), "evidence bundle fingerprint"
        ),
        operation_registry_fingerprint=_text(
            input_document.get("operation_registry_fingerprint"),
            "operation registry fingerprint",
        ),
        plan_contract_fingerprint=_text(
            input_document.get("plan_contract_fingerprint"), "plan contract fingerprint"
        ),
        decision_profile_fingerprint=_nullable_fingerprint(
            input_document, "decision_profile_fingerprint"
        ),
        challenge_profile_fingerprint=_nullable_fingerprint(
            input_document, "challenge_profile_fingerprint"
        ),
        decision_result_fingerprint=_nullable_fingerprint(
            input_document, "decision_result_fingerprint"
        ),
        challenge_result_fingerprint=_nullable_fingerprint(
            input_document, "challenge_result_fingerprint"
        ),
        candidate_mapping_fingerprint=_nullable_fingerprint(
            input_document, "candidate_mapping_fingerprint"
        ),
        task_profiles_admitted=input_document.get("task_profiles_admitted") is True,
        decision_result_contract_valid=(
            input_document.get("decision_result_contract_valid") is True
        ),
        challenge_result_contract_valid=(
            input_document.get("challenge_result_contract_valid") is True
        ),
        decision_evidence_bindings_complete=(
            input_document.get("decision_evidence_bindings_complete") is True
        ),
        challenge_evidence_bindings_complete=(
            input_document.get("challenge_evidence_bindings_complete") is True
        ),
        candidate_operations_closed_registry_only=(
            input_document.get("candidate_operations_closed_registry_only") is True
        ),
        candidate_source_spans_complete=(
            input_document.get("candidate_source_spans_complete") is True
        ),
        candidate_contains_final_text=(input_document.get("candidate_contains_final_text") is True),
        challenge_outcome=_text(input_document.get("challenge_outcome"), "challenge outcome"),
        semantic_result_conflicts=input_document.get("semantic_result_conflicts") is True,
        event_chain_mapping_complete=(input_document.get("event_chain_mapping_complete") is True),
        applicability_mapping_complete=(
            input_document.get("applicability_mapping_complete") is True
        ),
        dependency_mapping_complete=(input_document.get("dependency_mapping_complete") is True),
        bilingual_stream_mapping_complete=(
            input_document.get("bilingual_stream_mapping_complete") is True
        ),
        deterministic_prechecks_passed=(
            input_document.get("deterministic_prechecks_passed") is True
        ),
    )


def _semantic_plan_failure(
    *,
    outcome: Literal["BLOCK", "QUARANTINE"],
    reason: str,
    next_action: str,
    precheck_result: Literal["FAIL", "NOT_PERFORMED"] = "NOT_PERFORMED",
) -> _ReconstructionPlanSemanticResult:
    return _ReconstructionPlanSemanticResult(
        processing_outcome=outcome,
        legal_disposition=("QUARANTINE" if outcome == "QUARANTINE" else "NOT_APPLICABLE"),
        reason_code=reason,
        candidate_output="NONE",
        deterministic_precheck_result=precheck_result,
        next_action=next_action,
    )


def _semantic_plan_profile_precondition(
    context: _ReconstructionPlanSemanticContext,
) -> _ReconstructionPlanSemanticResult | None:
    if (
        not context.task_profiles_admitted
        or context.decision_profile_fingerprint is None
        or context.challenge_profile_fingerprint is None
    ):
        return _semantic_plan_failure(
            outcome="BLOCK",
            reason="HKLEG_RECON_PLAN_SEMANTIC_PROFILE_NOT_ADMITTED",
            next_action="ADMIT_RECONSTRUCTION_PLAN_TASK_PROFILES",
        )
    if context.decision_result_fingerprint is None:
        return _semantic_plan_failure(
            outcome="BLOCK",
            reason="HKLEG_RECON_PLAN_SEMANTIC_DECISION_RESULT_MISSING",
            next_action="OBTAIN_RECONSTRUCTION_PLAN_DECISION_RESULT",
        )
    if context.challenge_result_fingerprint is None:
        return _semantic_plan_failure(
            outcome="BLOCK",
            reason="HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_RESULT_MISSING",
            next_action="OBTAIN_RECONSTRUCTION_PLAN_CHALLENGE_RESULT",
        )
    return None


def _semantic_plan_contract_precondition(
    context: _ReconstructionPlanSemanticContext,
) -> _ReconstructionPlanSemanticResult | None:
    if context.semantic_result_conflicts:
        return _semantic_plan_failure(
            outcome="QUARANTINE",
            reason="HKLEG_RECON_PLAN_SEMANTIC_RESULT_CONFLICT",
            next_action="QUARANTINE_RECONSTRUCTION_PLAN_SEMANTIC_RESULTS",
        )
    if not context.decision_result_contract_valid or context.candidate_mapping_fingerprint is None:
        return _semantic_plan_failure(
            outcome="BLOCK",
            reason="HKLEG_RECON_PLAN_SEMANTIC_DECISION_CONTRACT_INVALID",
            next_action="REJECT_INVALID_RECONSTRUCTION_PLAN_DECISION",
        )
    if not context.challenge_result_contract_valid:
        return _semantic_plan_failure(
            outcome="BLOCK",
            reason="HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_CONTRACT_INVALID",
            next_action="REJECT_INVALID_RECONSTRUCTION_PLAN_CHALLENGE",
        )
    if (
        not context.decision_evidence_bindings_complete
        or not context.challenge_evidence_bindings_complete
        or not context.candidate_source_spans_complete
    ):
        return _semantic_plan_failure(
            outcome="BLOCK",
            reason="HKLEG_RECON_PLAN_SEMANTIC_EVIDENCE_BINDING_INCOMPLETE",
            next_action="COMPLETE_RECONSTRUCTION_PLAN_EVIDENCE_BINDINGS",
        )
    return None


def _semantic_plan_authority_precondition(
    context: _ReconstructionPlanSemanticContext,
) -> _ReconstructionPlanSemanticResult | None:
    if not context.candidate_operations_closed_registry_only:
        return _semantic_plan_failure(
            outcome="BLOCK",
            reason="HKLEG_RECON_PLAN_SEMANTIC_UNSUPPORTED_OPERATION",
            next_action="USE_FALLBACK_FOR_UNSUPPORTED_RECONSTRUCTION_OPERATION",
        )
    if context.candidate_contains_final_text:
        return _semantic_plan_failure(
            outcome="QUARANTINE",
            reason="HKLEG_RECON_PLAN_SEMANTIC_FINAL_TEXT_OVERREACH",
            next_action="QUARANTINE_MODEL_FINAL_TEXT_OVERREACH",
        )
    if context.challenge_outcome == "OBJECTION":
        return _semantic_plan_failure(
            outcome="BLOCK",
            reason="HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_OBJECTION",
            next_action="REVISE_RECONSTRUCTION_CANDIDATE_OR_USE_FALLBACK",
        )
    if context.challenge_outcome == "UNRESOLVED":
        return _semantic_plan_failure(
            outcome="QUARANTINE",
            reason="HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_UNRESOLVED",
            next_action="ROUTE_EXCEPTIONAL_RECONSTRUCTION_PLAN_TO_LEGAL_DESK",
        )
    return None


def _semantic_plan_deterministic_result(
    context: _ReconstructionPlanSemanticContext,
) -> _ReconstructionPlanSemanticResult:
    complete = (
        context.event_chain_mapping_complete
        and context.applicability_mapping_complete
        and context.dependency_mapping_complete
        and context.bilingual_stream_mapping_complete
        and context.deterministic_prechecks_passed
    )
    if not complete:
        return _semantic_plan_failure(
            outcome="BLOCK",
            reason="HKLEG_RECON_PLAN_SEMANTIC_DETERMINISTIC_PRECHECK_FAILED",
            next_action="USE_FALLBACK_AFTER_RECONSTRUCTION_PRECHECK_FAILURE",
            precheck_result="FAIL",
        )
    return _ReconstructionPlanSemanticResult(
        processing_outcome="PASS",
        legal_disposition="NOT_APPLICABLE",
        reason_code="HKLEG_RECON_PLAN_SEMANTIC_CANDIDATE_CONFIRMED",
        candidate_output="UNTRUSTED_STRUCTURED_PLAN_CANDIDATE",
        deterministic_precheck_result="PASS",
        next_action="RUN_DETERMINISTIC_RECONSTRUCTION_PLAN_VALIDATION",
    )


def _evaluate_reconstruction_plan_semantic(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> ReconstructionPlanSemanticDecision:
    """Gate semantic decision/challenge outputs before any executable Plan exists."""
    context = _parse_reconstruction_plan_semantic_input(fixture_id, input_document)
    result = _semantic_plan_profile_precondition(context)
    if result is None:
        result = _semantic_plan_contract_precondition(context)
    if result is None:
        result = _semantic_plan_authority_precondition(context)
    if result is None:
        result = _semantic_plan_deterministic_result(context)
    return _reconstruction_plan_semantic_decision(context, result)


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _ref_signature(reference: dict[str, JsonValue]) -> tuple[str, str, str]:
    return (
        _text(reference.get("ref_type"), "reference type"),
        _text(reference.get("ref_id"), "reference id"),
        _text(reference.get("fingerprint"), "reference fingerprint"),
    )


def _ref_signatures(
    value: JsonValue | None,
    label: str,
) -> tuple[tuple[str, str, str], ...]:
    return tuple(_ref_signature(item) for item in _objects(value, label))


def _sorted_unique_signatures(signatures: tuple[tuple[str, str, str], ...]) -> bool:
    return len(signatures) == len(set(signatures)) and signatures == tuple(sorted(signatures))


def _artifact_signatures(value: JsonValue) -> frozenset[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()

    def visit(item: JsonValue) -> None:
        if isinstance(item, dict):
            if item.get("ref_type") == "ARTIFACT":
                found.add(_ref_signature(item))
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return frozenset(found)


def _candidate_unknown_operation(plan: dict[str, JsonValue]) -> bool:
    streams = plan.get("language_streams")
    if not isinstance(streams, list):
        return False
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        operations = stream.get("operations")
        if not isinstance(operations, list):
            continue
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            operation_type = operation.get("operation_type_id")
            if isinstance(operation_type, str) and operation_type not in (
                _RECONSTRUCTION_OPERATION_IDS
            ):
                return True
    return False


def _parse_reconstruction_plan_input(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> _ReconstructionPlanContext:
    candidate_value = input_document.get("candidate_plan")
    candidate_plan = candidate_value if isinstance(candidate_value, dict) else None
    candidate_fingerprint = (
        _fingerprint(canonicalize(checked_json_value(candidate_plan)))
        if candidate_plan is not None
        else None
    )
    return _ReconstructionPlanContext(
        fixture_id=fixture_id,
        semantic_candidate_fingerprint=_text(
            input_document.get("semantic_candidate_fingerprint"),
            "semantic candidate fingerprint",
        ),
        plan_semantic_candidate_fingerprint=_text(
            input_document.get("plan_semantic_candidate_fingerprint"),
            "plan semantic candidate fingerprint",
        ),
        accepted_legal_desk_decision_ref=_object(
            input_document.get("accepted_legal_desk_decision_ref"),
            "accepted legal desk decision reference",
        ),
        legal_desk_decision_accepted=input_document.get("legal_desk_decision_accepted") is True,
        latest_eligible_base_proved=input_document.get("latest_eligible_base_proved") is True,
        event_chain_complete=input_document.get("event_chain_complete") is True,
        event_order_proved=input_document.get("event_order_proved") is True,
        applicability_exact=input_document.get("applicability_exact") is True,
        dependency_closure_complete=(input_document.get("dependency_closure_complete") is True),
        no_overlapping_plan=input_document.get("no_overlapping_plan") is True,
        source_unit_ownership_complete=(
            input_document.get("source_unit_ownership_complete") is True
        ),
        authentic_language_evidence_complete=(
            input_document.get("authentic_language_evidence_complete") is True
        ),
        bilingual_alignment_complete=(input_document.get("bilingual_alignment_complete") is True),
        operation_event_bindings_complete=(
            input_document.get("operation_event_bindings_complete") is True
        ),
        atomic_groups_dependency_closed=(
            input_document.get("atomic_groups_dependency_closed") is True
        ),
        undeclared_input_detected=input_document.get("undeclared_input_detected") is True,
        deterministic_revalidation_passed=(
            input_document.get("deterministic_revalidation_passed") is True
        ),
        declared_evidence_refs=_objects(
            input_document.get("declared_evidence_refs"),
            "declared evidence references",
        ),
        candidate_plan=candidate_plan,
        candidate_plan_fingerprint=candidate_fingerprint,
    )


def _reconstruction_plan_failure(
    reason_code: str,
    next_action: str,
    *,
    outcome: Literal["BLOCK", "QUARANTINE"] = "BLOCK",
    source_contract_review_required: bool = False,
) -> _ReconstructionPlanResult:
    return _ReconstructionPlanResult(
        processing_outcome=outcome,
        legal_disposition="QUARANTINE" if outcome == "QUARANTINE" else "NOT_APPLICABLE",
        source_contract_review_required=source_contract_review_required,
        reason_code=reason_code,
        plan_validation_result="NONE",
        validated_reconstruction_plan_id=None,
        validated_reconstruction_plan_fingerprint=None,
        validated_operation_count=0,
        next_action=next_action,
    )


def _plan_dependency_closure_valid(plan: dict[str, JsonValue]) -> bool:
    affected = _ref_signatures(
        plan.get("affected_legal_location_refs"),
        "affected legal locations",
    )
    closure = _object(plan.get("dependency_closure"), "dependency closure")
    primary = _ref_signatures(
        closure.get("primary_affected_location_refs"),
        "primary affected locations",
    )
    governing = _ref_signatures(
        closure.get("governing_context_location_refs"),
        "governing context locations",
    )
    dependent = _ref_signatures(
        closure.get("dependent_location_refs"),
        "dependent locations",
    )
    independent = _ref_signatures(
        closure.get("independent_sibling_boundary_refs"),
        "independent sibling boundaries",
    )
    closure_sets = (set(primary), set(governing), set(dependent))
    union = closure_sets[0] | closure_sets[1] | closure_sets[2]
    disjoint = not (
        closure_sets[0] & closure_sets[1]
        or closure_sets[0] & closure_sets[2]
        or closure_sets[1] & closure_sets[2]
    )
    return (
        _sorted_unique_signatures(affected)
        and all(_sorted_unique_signatures(values) for values in (primary, governing, dependent))
        and _sorted_unique_signatures(independent)
        and union == set(affected)
        and disjoint
        and not (set(independent) & union)
    )


def _plan_streams_and_operations(
    plan: dict[str, JsonValue],
) -> tuple[
    tuple[dict[str, JsonValue], dict[str, JsonValue]],
    tuple[tuple[str, dict[str, JsonValue]], ...],
]:
    streams = _objects(plan.get("language_streams"), "language streams")
    if len(streams) != _AUTHENTIC_LANGUAGE_COUNT:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "language streams")
    operations: list[tuple[str, dict[str, JsonValue]]] = []
    for stream in streams:
        language = _text(stream.get("language"), "language")
        operations.extend(
            (language, operation) for operation in _objects(stream.get("operations"), "operations")
        )
    return (streams[0], streams[1]), tuple(operations)


def _plan_language_streams_valid(plan: dict[str, JsonValue]) -> bool:
    streams, _ = _plan_streams_and_operations(plan)
    if tuple(_text(stream.get("language"), "language") for stream in streams) != (
        "en",
        "zh-Hant",
    ):
        return False
    base = _object(plan.get("base"), "base")
    base_refs = {
        "en": _ref_signature(_object(base.get("en_tree_ref"), "English base tree")),
        "zh-Hant": _ref_signature(
            _object(base.get("zh_hant_tree_ref"), "Traditional Chinese base tree")
        ),
    }
    changed = 0
    for stream in streams:
        language = _text(stream.get("language"), "language")
        effect = _text(stream.get("language_effect"), "language effect")
        operations = _objects(stream.get("operations"), "operations")
        unchanged_evidence = _objects(
            stream.get("unchanged_language_evidence_refs"),
            "unchanged language evidence",
        )
        if (
            _ref_signature(_object(stream.get("base_language_tree_ref"), "base language tree"))
            != base_refs[language]
        ):
            return False
        base_fingerprint = _text(
            stream.get("base_language_tree_fingerprint"),
            "base language tree fingerprint",
        )
        if base_fingerprint != base_refs[language][2]:
            return False
        if effect == "CHANGED":
            changed += 1
            if not operations or unchanged_evidence:
                return False
        elif (
            effect != "UNCHANGED"
            or operations
            or not unchanged_evidence
            or stream.get("expected_final_language_tree_fingerprint") != base_fingerprint
        ):
            return False
    return changed >= 1


def _plan_bilingual_alignment_valid(plan: dict[str, JsonValue]) -> bool:
    streams, _ = _plan_streams_and_operations(plan)
    maps = tuple(
        _ref_signature(
            _object(
                stream.get("expected_bilingual_alignment_map_ref"),
                "bilingual alignment map",
            )
        )
        for stream in streams
    )
    return maps[0] == maps[1]


def _plan_operation_inventory_valid(plan: dict[str, JsonValue]) -> bool:
    streams, operations = _plan_streams_and_operations(plan)
    operation_ids: list[str] = []
    affected = set(_ref_signatures(plan.get("affected_legal_location_refs"), "affected locations"))
    for stream in streams:
        sequence = tuple(
            operation.get("sequence")
            for operation in _objects(stream.get("operations"), "operations")
        )
        if sequence != tuple(range(len(sequence))):
            return False
    for _, operation in operations:
        operation_id = _text(operation.get("operation_instance_id"), "operation id")
        operation_type = _text(operation.get("operation_type_id"), "operation type")
        selector = _object(operation.get("target_selector"), "target selector")
        if (
            operation_type not in _RECONSTRUCTION_OPERATION_IDS
            or selector.get("selector_kind")
            != _RECONSTRUCTION_SELECTOR_BY_OPERATION[operation_type]
            or not set(
                _ref_signatures(
                    operation.get("dependency_location_refs"),
                    "operation dependency locations",
                )
            ).issubset(affected)
        ):
            return False
        operation_ids.append(operation_id)
    if len(operation_ids) != len(set(operation_ids)):
        return False
    registry = _object(
        _object(plan.get("contracts"), "contracts").get("operation_registry"),
        "operation registry contract",
    )
    return (
        registry.get("contract_id") == "asklegal.hk-legislation.reconstruction-operation-registry"
        and registry.get("version") == "1.0.0"
    )


_TEXT_EVENT_ROLES = frozenset(
    {
        "TEXT_AMENDMENT",
        "EDITORIAL_AMENDMENT",
        "TEXT_AMENDMENT_WITH_EFFECT",
        "EDITORIAL_AMENDMENT_WITH_EFFECT",
    }
)
_EFFECT_EVENT_ROLES = frozenset(
    {
        "TEXT_AMENDMENT_WITH_EFFECT",
        "EDITORIAL_AMENDMENT_WITH_EFFECT",
        "COMMENCEMENT_OR_EFFECT",
        "APPLICABILITY_OR_TRANSITION",
    }
)
_EFFECT_ONLY_EVENT_ROLES = frozenset({"COMMENCEMENT_OR_EFFECT", "APPLICABILITY_OR_TRANSITION"})


def _plan_event_inventory(
    events: tuple[dict[str, JsonValue], ...],
    operation_ids: set[str],
) -> (
    tuple[
        dict[tuple[str, str, str], dict[str, JsonValue]],
        set[tuple[str, str, str]],
    ]
    | None
):
    if tuple(event.get("sequence") for event in events) != tuple(range(len(events))):
        return None
    event_by_ref = {
        _ref_signature(_object(event.get("event_ref"), "event reference")): event
        for event in events
    }
    if len(event_by_ref) != len(events):
        return None
    declared_operation_ids: set[str] = set()
    effect_only_refs: set[tuple[str, str, str]] = set()
    for event_ref, event in event_by_ref.items():
        role = _text(event.get("event_role"), "event role")
        ids = set(_texts(event.get("operation_instance_ids"), "event operation ids"))
        declared_operation_ids.update(ids)
        if (role in _TEXT_EVENT_ROLES) != bool(ids):
            return None
        if role in _EFFECT_ONLY_EVENT_ROLES:
            effect_only_refs.add(event_ref)
    if declared_operation_ids != operation_ids:
        return None
    return event_by_ref, effect_only_refs


def _event_source_units(
    events: tuple[dict[str, JsonValue], ...],
) -> dict[str, set[tuple[str, str, str]]]:
    result: dict[str, set[tuple[str, str, str]]] = {
        "en": set(),
        "zh-Hant": set(),
    }
    for event in events:
        source_units = _object(
            event.get("authentic_language_source_unit_refs"),
            "event source units",
        )
        for language, signatures in result.items():
            signatures.update(_ref_signatures(source_units.get(language), "event source units"))
    return result


def _one_operation_event_binding_valid(
    language: str,
    operation: dict[str, JsonValue],
    event_by_ref: dict[tuple[str, str, str], dict[str, JsonValue]],
    source_units_by_language: dict[str, set[tuple[str, str, str]]],
) -> tuple[bool, set[tuple[str, str, str]]]:
    operation_id = _text(operation.get("operation_instance_id"), "operation id")
    amendment_ref = _ref_signature(_object(operation.get("amendment_event_ref"), "amendment event"))
    amendment_event = event_by_ref.get(amendment_ref)
    amendment_valid = (
        amendment_event is not None
        and _text(amendment_event.get("event_role"), "amendment event role") in _TEXT_EVENT_ROLES
        and operation_id
        in _texts(
            amendment_event.get("operation_instance_ids"),
            "amendment event operation ids",
        )
    )
    effect_refs = set(
        _ref_signatures(operation.get("effect_event_refs"), "effect event references")
    )
    effects_valid = bool(effect_refs) and all(
        effect_ref in event_by_ref
        and _text(event_by_ref[effect_ref].get("event_role"), "effect event role")
        in _EFFECT_EVENT_ROLES
        for effect_ref in effect_refs
    )
    source_units_valid = set(
        _ref_signatures(operation.get("source_unit_refs"), "operation source units")
    ).issubset(source_units_by_language[language])
    return amendment_valid and effects_valid and source_units_valid, effect_refs


def _plan_event_bindings_valid(plan: dict[str, JsonValue]) -> bool:
    _, operations = _plan_streams_and_operations(plan)
    events = _objects(plan.get("event_chain"), "event chain")
    operation_ids = {
        _text(operation.get("operation_instance_id"), "operation id") for _, operation in operations
    }
    inventory = _plan_event_inventory(events, operation_ids)
    if inventory is None:
        return False
    event_by_ref, effect_only_refs = inventory
    source_units_by_language = _event_source_units(events)
    referenced_effects: set[tuple[str, str, str]] = set()
    for language, operation in operations:
        valid, effect_refs = _one_operation_event_binding_valid(
            language,
            operation,
            event_by_ref,
            source_units_by_language,
        )
        if not valid:
            return False
        referenced_effects.update(effect_refs)
    return effect_only_refs.issubset(referenced_effects)


def _plan_source_unit_ownership_valid(
    plan: dict[str, JsonValue],
    declared_evidence_refs: tuple[dict[str, JsonValue], ...],
) -> bool:
    declared = frozenset(_ref_signature(item) for item in declared_evidence_refs)
    plan_inventory = frozenset(
        _ref_signatures(plan.get("evidence_refs"), "plan evidence references")
    )
    if declared != plan_inventory or _artifact_signatures(plan) != declared:
        return False
    closure = _object(plan.get("dependency_closure"), "dependency closure")
    closure_units = _object(
        closure.get("authentic_language_source_unit_refs"),
        "closure source units",
    )
    streams, operations = _plan_streams_and_operations(plan)
    for language in ("en", "zh-Hant"):
        owned = set(_ref_signatures(closure_units.get(language), "closure source units"))
        if not owned:
            return False
        for operation_language, operation in operations:
            if operation_language == language and not set(
                _ref_signatures(operation.get("source_unit_refs"), "operation source units")
            ).issubset(owned):
                return False
    return all(
        _sorted_unique_signatures(
            _ref_signatures(stream.get("unchanged_language_evidence_refs"), "unchanged evidence")
        )
        for stream in streams
    )


def _plan_candidate_contract_result(
    context: _ReconstructionPlanContext,
    registry: SchemaRegistry,
) -> _ReconstructionPlanResult | None:
    plan = context.candidate_plan
    if plan is None:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_CANDIDATE_MISSING",
            "OBTAIN_COMPLETE_RECONSTRUCTION_PLAN_CANDIDATE",
        )
    if _candidate_unknown_operation(plan):
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_UNKNOWN_OPERATION",
            "OPEN_RECONSTRUCTION_SOURCE_CONTRACT_REVIEW",
            source_contract_review_required=True,
        )
    try:
        _validate(registry, plan, "plan", schema=_RECONSTRUCTION_PLAN_SCHEMA)
    except RulebookError:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_CONTRACT_INVALID",
            "REJECT_INVALID_RECONSTRUCTION_PLAN_CONTRACT",
        )
    if context.semantic_candidate_fingerprint != context.plan_semantic_candidate_fingerprint:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_SEMANTIC_CANDIDATE_MISMATCH",
            "RECONCILE_RECONSTRUCTION_SEMANTIC_CANDIDATE",
        )
    return None


def _plan_authority_result(
    context: _ReconstructionPlanContext,
    plan: dict[str, JsonValue],
) -> _ReconstructionPlanResult | None:
    if not context.legal_desk_decision_accepted or _ref_signature(
        _object(plan.get("decision_ref"), "Plan decision reference")
    ) != _ref_signature(context.accepted_legal_desk_decision_ref):
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_LEGAL_DESK_DECISION_NOT_ACCEPTED",
            "OBTAIN_ACCEPTED_LEGAL_DESK_PLAN_DECISION",
        )
    if not context.latest_eligible_base_proved:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_BASE_NOT_LATEST_ELIGIBLE",
            "SELECT_LATEST_ELIGIBLE_HKEL_BASE",
        )
    if not context.event_chain_complete:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_CHAIN_INCOMPLETE",
            "COMPLETE_RECONSTRUCTION_EVENT_CHAIN",
        )
    if not context.event_order_proved:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_EVENT_ORDER_UNRESOLVED",
            "RESOLVE_RECONSTRUCTION_EVENT_ORDER",
        )
    if not context.applicability_exact:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_APPLICABILITY_UNRESOLVED",
            "RESOLVE_RECONSTRUCTION_APPLICABILITY",
        )
    return None


def _plan_closure_result(
    context: _ReconstructionPlanContext,
    plan: dict[str, JsonValue],
) -> _ReconstructionPlanResult | None:
    if not context.dependency_closure_complete or not _plan_dependency_closure_valid(plan):
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_DEPENDENCY_CLOSURE_INCOMPLETE",
            "COMPLETE_RECONSTRUCTION_DEPENDENCY_CLOSURE",
        )
    if not context.no_overlapping_plan:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_OVERLAP",
            "RECONCILE_OVERLAPPING_RECONSTRUCTION_PLAN",
        )
    if not context.source_unit_ownership_complete or not _plan_source_unit_ownership_valid(
        plan,
        context.declared_evidence_refs,
    ):
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_SOURCE_UNIT_OWNERSHIP_INCOMPLETE",
            "COMPLETE_RECONSTRUCTION_SOURCE_UNIT_OWNERSHIP",
        )
    if not context.authentic_language_evidence_complete or not _plan_language_streams_valid(plan):
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_LANGUAGE_EVIDENCE_INCOMPLETE",
            "COMPLETE_AUTHENTIC_LANGUAGE_EVIDENCE",
        )
    if not context.bilingual_alignment_complete or not _plan_bilingual_alignment_valid(plan):
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_BILINGUAL_RESULT_MISMATCH",
            "QUARANTINE_RECONSTRUCTION_BILINGUAL_MISMATCH",
            outcome="QUARANTINE",
        )
    return None


def _plan_operation_result(
    context: _ReconstructionPlanContext,
    plan: dict[str, JsonValue],
) -> _ReconstructionPlanResult | None:
    if not _plan_operation_inventory_valid(plan):
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_OPERATION_INVENTORY_INVALID",
            "CORRECT_RECONSTRUCTION_OPERATION_INVENTORY",
        )
    if not context.operation_event_bindings_complete or not _plan_event_bindings_valid(plan):
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_OPERATION_EVENT_BINDING_INCOMPLETE",
            "COMPLETE_RECONSTRUCTION_OPERATION_EVENT_BINDINGS",
        )
    if not context.atomic_groups_dependency_closed:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_ATOMIC_GROUP_INCOMPLETE",
            "COMPLETE_RECONSTRUCTION_ATOMIC_GROUP",
        )
    if context.undeclared_input_detected:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_UNDECLARED_INPUT",
            "REMOVE_UNDECLARED_RECONSTRUCTION_INPUT",
        )
    if not context.deterministic_revalidation_passed:
        return _reconstruction_plan_failure(
            "HKLEG_RECON_PLAN_DETERMINISTIC_REVALIDATION_FAILED",
            "USE_FALLBACK_AFTER_RECONSTRUCTION_REVALIDATION_FAILURE",
        )
    return None


def _validated_plan_result(
    context: _ReconstructionPlanContext,
    plan: dict[str, JsonValue],
) -> _ReconstructionPlanResult:
    _, operations = _plan_streams_and_operations(plan)
    return _ReconstructionPlanResult(
        processing_outcome="PASS",
        legal_disposition="NOT_APPLICABLE",
        source_contract_review_required=False,
        reason_code="HKLEG_RECON_PLAN_VALIDATED",
        plan_validation_result="VALIDATED",
        validated_reconstruction_plan_id=_text(
            plan.get("reconstruction_plan_id"),
            "reconstruction Plan ID",
        ),
        validated_reconstruction_plan_fingerprint=context.candidate_plan_fingerprint,
        validated_operation_count=len(operations),
        next_action="CHECK_RECONSTRUCTION_CAPABILITY_AND_EXECUTE_PLAN",
    )


def _evaluate_reconstruction_plan_validation(
    fixture_id: str,
    input_document: dict[str, JsonValue],
    registry: SchemaRegistry,
) -> ReconstructionPlanValidationDecision:
    """Validate a complete ADR 0084 Plan without executing any operation."""
    context = _parse_reconstruction_plan_input(fixture_id, input_document)
    result = _plan_candidate_contract_result(context, registry)
    plan = context.candidate_plan
    if result is None and plan is not None:
        result = _plan_authority_result(context, plan)
    if result is None and plan is not None:
        result = _plan_closure_result(context, plan)
    if result is None and plan is not None:
        result = _plan_operation_result(context, plan)
    if result is None and plan is not None:
        result = _validated_plan_result(context, plan)
    if result is None:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "Plan validation result")
    return _reconstruction_plan_validation_decision(context, result)


def _evaluate_hk_current_event(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentEventDecision:
    """Route a proved operative event without constructing or serving text."""
    object_id = _text(input_document.get("object_id"), "object_id")
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    locations = _texts(input_document.get("affected_location_ids"), "affected_location_ids")
    location_scope = _text(input_document.get("affected_location_scope"), "location scope")
    effective_value = input_document.get("effective_date")
    effective_date = effective_value if isinstance(effective_value, str) else None
    base_class_value = input_document.get("base_evidence_class")
    base_class = base_class_value if isinstance(base_class_value, str) else None
    base_date_value = input_document.get("base_version_date")
    base_date = base_date_value if isinstance(base_date_value, str) else None
    base_available = input_document.get("valid_latest_hkel_base_available") is True
    if base_available != (base_class is not None and base_date is not None):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "base evidence")
    if input_document.get("matching_current_consolidation_available") is True:
        return CurrentEventDecision(
            fixture_id=fixture_id,
            processing_outcome="BLOCK",
            coverage_effect="NONE",
            reason_code="HKLEG_CURRENT_EVENT_CURRENT_CONSOLIDATION_AVAILABLE",
            event_fact_output="NONE",
            selection_result="ORDINARY_CURRENT_BUNDLE_REQUIRED",
            affected_object_id=object_id,
            affected_scope_id=scope_id,
            affected_location_ids=locations,
            affected_location_scope=location_scope,
            effective_date=effective_date,
            base_evidence_class=base_class,
            base_version_date=base_date,
            next_action="RUN_HKLEG_CURRENT_EVID_001",
        )
    fingerprints = _texts(
        input_document.get("event_evidence_fingerprints"), "event_evidence_fingerprints"
    )
    conflict = input_document.get("event_evidence_conflicts") is True
    complete = (
        input_document.get("event_evidence_complete") is True
        and input_document.get("event_evidence_authentic") is True
        and input_document.get("event_operative_at_cutoff") is True
        and effective_date is not None
        and bool(fingerprints)
    )
    if conflict:
        outcome: Literal["BLOCK", "QUARANTINE"] = "QUARANTINE"
        reason = "HKLEG_CURRENT_EVENT_EVIDENCE_CONFLICT"
        next_action = "QUARANTINE_EVENT_EVIDENCE"
    elif not complete:
        outcome = "BLOCK"
        reason = "HKLEG_CURRENT_EVENT_EVIDENCE_INCOMPLETE"
        next_action = "RESOLVE_EVENT_EVIDENCE"
    elif location_scope == "UNBOUNDED":
        outcome = "QUARANTINE"
        reason = "HKLEG_CURRENT_EVENT_AFFECTED_SET_UNBOUNDED"
        next_action = "QUARANTINE_AFFECTED_SET"
    else:
        reconstruction_ready = (
            input_document.get("reconstruction_capability_state")
            == "ACTIVE_FOR_CANDIDATE_PROCESSING"
            and input_document.get("reconstruction_exact_eligibility_proved") is True
        )
        if reconstruction_ready:
            selection = "RECONSTRUCTION_PLAN_REQUIRED"
            next_action = "BUILD_RECONSTRUCTION_PLAN"
        elif base_available:
            selection = "KNOWN_STALE_ANALYTICAL_CARRY_FORWARD_REQUIRED"
            next_action = "BUILD_KNOWN_STALE_CANDIDATE"
        else:
            selection = "NO_RECORD_COVERAGE_GAP"
            next_action = "ACCOUNT_NO_RECORD_COVERAGE_GAP"
        return CurrentEventDecision(
            fixture_id=fixture_id,
            processing_outcome="PASS",
            coverage_effect="COVERAGE_GAP",
            reason_code="HKLEG_CURRENT_EVENT_PROVED_CONSOLIDATION_MISSING",
            event_fact_output="LEGAL_STATUS_EVENT",
            selection_result=selection,
            affected_object_id=object_id,
            affected_scope_id=scope_id,
            affected_location_ids=locations,
            affected_location_scope=location_scope,
            effective_date=effective_date,
            base_evidence_class=base_class,
            base_version_date=base_date,
            next_action=next_action,
        )
    return CurrentEventDecision(
        fixture_id=fixture_id,
        processing_outcome=outcome,
        coverage_effect="NONE",
        reason_code=reason,
        event_fact_output="NONE",
        selection_result="NONE",
        affected_object_id=object_id,
        affected_scope_id=scope_id,
        affected_location_ids=locations,
        affected_location_scope=location_scope,
        effective_date=effective_date,
        base_evidence_class=base_class,
        base_version_date=base_date,
        next_action=next_action,
    )


def _evaluate_hk_current_disposition(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentDispositionDecision:
    """Assign one ordinary disposition only after exact upstream checkpoints."""
    object_id = _text(input_document.get("object_id"), "object_id")
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    location_id = _text(input_document.get("location_id"), "location_id")
    upstream = _text(input_document.get("upstream_checkpoint"), "upstream_checkpoint")
    basis = _text(input_document.get("disposition_basis"), "disposition_basis")
    coverage_complete = input_document.get("status_coverage_complete") is True

    if upstream == "BLOCK":
        return CurrentDispositionDecision(
            fixture_id,
            "BLOCK",
            "NOT_APPLICABLE",
            "HKLEG_CURRENT_DISP_UPSTREAM_BLOCKED",
            object_id,
            scope_id,
            location_id,
            "RESOLVE_UPSTREAM_CHECKPOINT",
        )
    if upstream == "QUARANTINE" or not coverage_complete or basis == "UNRESOLVED_MATERIAL_FACT":
        return CurrentDispositionDecision(
            fixture_id,
            "QUARANTINE",
            "QUARANTINE",
            "HKLEG_CURRENT_DISP_QUARANTINE_REQUIRED",
            object_id,
            scope_id,
            location_id,
            "PRESERVE_QUARANTINE",
        )
    if basis == "UNSUPPORTED_SIGNAL_ONLY":
        return CurrentDispositionDecision(
            fixture_id,
            "BLOCK",
            "NOT_APPLICABLE",
            "HKLEG_CURRENT_DISP_SINGLE_SIGNAL_INSUFFICIENT",
            object_id,
            scope_id,
            location_id,
            "COMPLETE_LEGAL_TESTS",
        )
    supported = {
        "PRESENT_OPERATIVE_SUPPORTED": (
            "SEARCHABLE_CURRENT",
            "HKLEG_CURRENT_DISP_SEARCHABLE_CURRENT_SUPPORTED",
            "RUN_HKLEG_CURRENT_REC_001",
        ),
        "VALIDLY_MADE_NOT_PROVED_OPERATIVE": (
            "WAITING_ROOM",
            "HKLEG_CURRENT_DISP_WAITING_ROOM_SUPPORTED",
            "PRESERVE_NON_SEARCHABLE_ACCOUNTING",
        ),
        "PRESENT_EFFECT_REPRESENTED_ELSEWHERE": (
            "EVIDENCE_ONLY",
            "HKLEG_CURRENT_DISP_EVIDENCE_ONLY_SUPPORTED",
            "PRESERVE_NON_SEARCHABLE_ACCOUNTING",
        ),
        "ENDED_OR_SUPERSEDED_PROVED": (
            "HISTORICAL",
            "HKLEG_CURRENT_DISP_HISTORICAL_SUPPORTED",
            "PRESERVE_NON_SEARCHABLE_ACCOUNTING",
        ),
    }
    try:
        disposition, reason, next_action = supported[basis]
    except KeyError as error:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, basis) from error
    return CurrentDispositionDecision(
        fixture_id,
        "PASS",
        disposition,
        reason,
        object_id,
        scope_id,
        location_id,
        next_action,
    )


def _evaluate_exact_current_record(
    fixture_id: str,
    scope_id: str,
    predecessor: dict[str, JsonValue],
    candidate_id: str,
    predecessor_metadata: dict[str, JsonValue],
) -> CurrentRecordDecision:
    predecessor_id = _text(predecessor.get("id"), "predecessor id")
    if candidate_id != predecessor_id:
        return CurrentRecordDecision(
            fixture_id,
            "BLOCK",
            "SEARCHABLE_CURRENT",
            "HKLEG_CURRENT_REC_EXACT_REUSE_REQUIRED",
            "NONE",
            None,
            None,
            predecessor_id,
            scope_id,
            "REUSE_PREDECESSOR_RECORD_ID",
        )
    return CurrentRecordDecision(
        fixture_id,
        "PASS",
        "SEARCHABLE_CURRENT",
        "HKLEG_CURRENT_REC_EXACT_RECORD_REUSED",
        "REUSED",
        predecessor,
        _fingerprint(canonicalize(checked_json_value(predecessor_metadata))),
        predecessor_id,
        scope_id,
        "RUN_HKLEG_CURRENT_REL_001",
    )


def _evaluate_changed_current_record(
    fixture_id: str,
    scope_id: str,
    input_document: dict[str, JsonValue],
    predecessor: dict[str, JsonValue],
    candidate: dict[str, JsonValue],
) -> CurrentRecordDecision:
    predecessor_id = _text(predecessor.get("id"), "predecessor id")
    candidate_id = _text(candidate.get("id"), "candidate id")
    candidate_metadata = candidate.get("metadata")
    if not isinstance(candidate_metadata, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "candidate metadata")
    if candidate_id == predecessor_id:
        return CurrentRecordDecision(
            fixture_id,
            "QUARANTINE",
            "SEARCHABLE_CURRENT",
            "HKLEG_CURRENT_REC_IMMUTABLE_ID_MUTATION",
            "NONE",
            None,
            None,
            predecessor_id,
            scope_id,
            "QUARANTINE_IDENTITY_MUTATION",
        )
    if input_document.get("new_identity_register_allocated") is not True:
        return CurrentRecordDecision(
            fixture_id,
            "BLOCK",
            "SEARCHABLE_CURRENT",
            "HKLEG_CURRENT_REC_NEW_ID_REQUIRED",
            "NONE",
            None,
            None,
            predecessor_id,
            scope_id,
            "REQUEST_NEW_REGISTER_IDENTITY",
        )
    return CurrentRecordDecision(
        fixture_id,
        "PASS",
        "SEARCHABLE_CURRENT",
        "HKLEG_CURRENT_REC_CHANGED_RECORD_CREATED",
        "CREATED",
        candidate,
        _fingerprint(canonicalize(checked_json_value(candidate_metadata))),
        predecessor_id,
        scope_id,
        "RUN_HKLEG_CURRENT_REL_001",
    )


def _evaluate_hk_current_record(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentRecordDecision:
    """Reuse exact bytes or require a new immutable Register-issued identity."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    disposition = _text(input_document.get("legal_disposition"), "legal_disposition")
    predecessor_value = input_document.get("predecessor_record")
    candidate_value = input_document.get("candidate_record")
    predecessor = predecessor_value if isinstance(predecessor_value, dict) else None
    candidate = candidate_value if isinstance(candidate_value, dict) else None

    if disposition != "SEARCHABLE_CURRENT":
        return CurrentRecordDecision(
            fixture_id,
            "PASS",
            disposition,
            "HKLEG_CURRENT_REC_NON_SEARCHABLE_EXCLUDED",
            "NONE",
            None,
            None,
            None,
            scope_id,
            "PRESERVE_NON_SEARCHABLE_ACCOUNTING",
        )
    if input_document.get("continuing_legal_support") is not True:
        return CurrentRecordDecision(
            fixture_id,
            "BLOCK",
            disposition,
            "HKLEG_CURRENT_REC_CONTINUING_SUPPORT_MISSING",
            "NONE",
            None,
            None,
            None,
            scope_id,
            "COMPLETE_LEGAL_SUPPORT",
        )
    if predecessor is None:
        return CurrentRecordDecision(
            fixture_id,
            "BLOCK",
            disposition,
            "HKLEG_CURRENT_REC_PREDECESSOR_REQUIRED",
            "NONE",
            None,
            None,
            None,
            scope_id,
            "OPEN_INITIAL_BASELINE",
        )
    if candidate is None:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "candidate record")
    candidate_id = _text(candidate.get("id"), "candidate id")
    predecessor_metadata = predecessor.get("metadata")
    candidate_metadata = candidate.get("metadata")
    if not isinstance(predecessor_metadata, dict) or not isinstance(candidate_metadata, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "record metadata")
    if canonicalize(checked_json_value(predecessor_metadata)) == canonicalize(
        checked_json_value(candidate_metadata)
    ):
        return _evaluate_exact_current_record(
            fixture_id, scope_id, predecessor, candidate_id, predecessor_metadata
        )
    return _evaluate_changed_current_record(
        fixture_id,
        scope_id,
        input_document,
        predecessor,
        candidate,
    )


_CURRENT_RELEASE_REFERENCE_FIELDS = (
    "object_ids",
    "location_ids",
    "event_ids",
    "selected_record_ids",
    "retired_record_ids",
    "coverage_gap_ids",
    "quarantine_ids",
)


def _current_release_block(
    fixture_id: str,
    input_document: dict[str, JsonValue],
    reason_code: str,
    unresolved_ids: set[str] | tuple[str, ...],
    next_action: str,
) -> CurrentReleaseAccountingDecision:
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    predecessor_value = input_document.get("predecessor_release_id")
    predecessor_release_id = predecessor_value if isinstance(predecessor_value, str) else None
    return CurrentReleaseAccountingDecision(
        fixture_id,
        "BLOCK",
        "COVERAGE_GAP",
        reason_code,
        predecessor_release_id,
        (),
        (),
        tuple(sorted(unresolved_ids, key=str.encode)),
        None,
        scope_id,
        next_action,
    )


def _evaluate_hk_current_release_accounting(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> CurrentReleaseAccountingDecision:
    """Require complete ordinary-update accounting without building a release."""
    scope_id = _text(input_document.get("scope_id"), "scope_id")
    predecessor_value = input_document.get("predecessor_release_id")
    predecessor_id = predecessor_value if isinstance(predecessor_value, str) else None
    expected = input_document.get("expected_accounting")
    actual = input_document.get("actual_accounting")
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "release accounting")
    if predecessor_id is None:
        return _current_release_block(
            fixture_id,
            input_document,
            "HKLEG_CURRENT_REL_PREDECESSOR_REQUIRED",
            (),
            "OPEN_INITIAL_BASELINE",
        )
    duplicate_ids = set(_texts(input_document.get("duplicate_location_ids"), "duplicates"))
    if duplicate_ids:
        return _current_release_block(
            fixture_id,
            input_document,
            "HKLEG_CURRENT_REL_DUPLICATE_LOCATION",
            duplicate_ids,
            "REMOVE_DUPLICATE_LOCATION_ACCOUNTING",
        )
    reference_drift: set[str] = set()
    for field in _CURRENT_RELEASE_REFERENCE_FIELDS:
        reference_drift.update(
            set(_texts(expected.get(field), field)).symmetric_difference(
                _texts(actual.get(field), field)
            )
        )
    if reference_drift:
        return _current_release_block(
            fixture_id,
            input_document,
            "HKLEG_CURRENT_REL_REFERENCE_UNACCOUNTED",
            reference_drift,
            "COMPLETE_REFERENCE_ACCOUNTING",
        )
    if input_document.get("entry_consistency_proved") is not True:
        return _current_release_block(
            fixture_id,
            input_document,
            "HKLEG_CURRENT_REL_RESULT_ACCOUNTING_INCONSISTENT",
            (),
            "RECONCILE_DISPOSITIONS_AND_OUTPUTS",
        )
    unresolved = _texts(input_document.get("unresolved_completeness_ids"), "unresolved")
    if unresolved:
        return _current_release_block(
            fixture_id,
            input_document,
            "HKLEG_CURRENT_REL_COMPLETENESS_UNRESOLVED",
            unresolved,
            "RESOLVE_COMPLETENESS_GAPS",
        )
    object_ids = tuple(sorted(_texts(expected.get("object_ids"), "object_ids"), key=str.encode))
    location_ids = tuple(
        sorted(_texts(expected.get("location_ids"), "location_ids"), key=str.encode)
    )
    coverage_effect: Literal["NONE", "COVERAGE_GAP"] = (
        "COVERAGE_GAP" if _texts(expected.get("coverage_gap_ids"), "coverage_gap_ids") else "NONE"
    )
    return CurrentReleaseAccountingDecision(
        fixture_id,
        "PASS",
        coverage_effect,
        "HKLEG_CURRENT_REL_RELEASE_ACCOUNTED",
        predecessor_id,
        object_ids,
        location_ids,
        (),
        _fingerprint(canonicalize(checked_json_value(input_document))),
        scope_id,
        "BUILD_CANDIDATE_CORPUS_RELEASE",
    )


def _parse_inventory_input(input_document: dict[str, JsonValue]) -> _InventoryData:
    source = input_document["source_observation"]
    if not isinstance(source, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "source_observation")
    objects = _objects(input_document.get("observed_legal_objects"), "observed_legal_objects")
    claims = _objects(input_document.get("accounting_claims"), "accounting_claims")

    object_scope: dict[str, str] = {}
    object_resources: dict[str, set[str]] = {}
    for item in objects:
        object_id = _text(item.get("legal_object_id"), "legal_object_id")
        nature = _text(item.get("legal_nature"), "legal_nature")
        if object_id in object_scope or nature not in _SCOPE_BY_NATURE:
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "observed legal object")
        object_scope[object_id] = _SCOPE_BY_NATURE[nature]
        resources = _objects(item.get("resources"), "resources")
        resource_ids = {_text(resource.get("resource_id"), "resource_id") for resource in resources}
        if not resource_ids or len(resource_ids) != len(resources):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "resources")
        object_resources[object_id] = resource_ids

    claims_by_object: dict[str, list[tuple[str, set[str]]]] = {}
    for claim in claims:
        object_id = _text(claim.get("legal_object_id"), "claim legal_object_id")
        claim_scope = _text(claim.get("scope_id"), "claim scope_id")
        claimed_resources = set(_texts(claim.get("resource_ids"), "claim resource_ids"))
        claims_by_object.setdefault(object_id, []).append((claim_scope, claimed_resources))
    return _InventoryData(
        object_scope,
        object_resources,
        claims_by_object,
    )


def _inventory_issues(
    data: _InventoryData,
) -> tuple[set[str], set[str], set[str]]:
    duplicate_ids = {
        object_id
        for object_id, object_claims in data.claims_by_object.items()
        if len(object_claims) > 1
    }
    unaccounted_ids = {
        object_id
        for object_id, required_resources in data.object_resources.items()
        if len(data.claims_by_object.get(object_id, ())) != 1
        or data.claims_by_object[object_id][0][1] != required_resources
    }
    unaccounted_ids.update(set(data.claims_by_object).difference(data.object_scope))
    misassigned_ids = {
        object_id
        for object_id, expected_scope in data.object_scope.items()
        if len(data.claims_by_object.get(object_id, ())) == 1
        and data.claims_by_object[object_id][0][0] != expected_scope
    }
    return duplicate_ids, unaccounted_ids, misassigned_ids


def _affected_scopes(data: _InventoryData, object_ids: set[str]) -> set[str]:
    affected = {
        data.object_scope.get(object_id, HK_ORDINANCES_SCOPE_ID) for object_id in object_ids
    }
    for object_id in object_ids:
        affected.update(scope_id for scope_id, _ in data.claims_by_object.get(object_id, ()))
    return affected


def _evaluate_hk_baseline_inventory(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> BaselineInventoryDecision:
    """Evaluate exact accounting without making a legal-status decision."""
    data = _parse_inventory_input(input_document)
    all_scope_ids = tuple(_SCOPE_BY_NATURE.values())
    accounted: set[str] = set()
    unresolved: set[str] = set()
    affected: set[str] = set()
    reason: str
    outcome: Literal["PASS", "BLOCK", "QUARANTINE"]

    duplicate_ids, unaccounted_ids, misassigned_ids = _inventory_issues(data)
    if duplicate_ids:
        reason = "HKLEG_BASE_INVENTORY_OWNERSHIP_AMBIGUOUS"
        outcome = "QUARANTINE"
        unresolved.update(duplicate_ids)
        affected.update(_affected_scopes(data, duplicate_ids))
    elif unaccounted_ids:
        reason = "HKLEG_BASE_INVENTORY_OBJECT_OR_RESOURCE_UNACCOUNTED"
        outcome = "BLOCK"
        unresolved.update(unaccounted_ids)
        affected.update(_affected_scopes(data, unaccounted_ids))
    elif misassigned_ids:
        reason = "HKLEG_BASE_INVENTORY_SCOPE_MISASSIGNED"
        outcome = "BLOCK"
        unresolved.update(misassigned_ids)
        affected.update(_affected_scopes(data, misassigned_ids))
    else:
        reason = "HKLEG_BASE_INVENTORY_ACCOUNTED"
        outcome = "PASS"
        accounted.update(data.object_scope)
        affected.update(data.object_scope.values())

    incomplete_scopes = affected if outcome != "PASS" else set[str]()
    scope_results: tuple[tuple[str, Literal["COMPLETE", "INCOMPLETE"]], ...] = tuple(
        (scope_id, "INCOMPLETE" if scope_id in incomplete_scopes else "COMPLETE")
        for scope_id in all_scope_ids
        if scope_id in affected
    )
    return BaselineInventoryDecision(
        fixture_id=fixture_id,
        processing_outcome=outcome,
        coverage_effect="NONE" if outcome == "PASS" else "COVERAGE_GAP",
        reason_codes=(reason,),
        accounted_object_ids=tuple(sorted(accounted, key=str.encode)),
        unresolved_object_ids=tuple(sorted(unresolved, key=str.encode)),
        affected_scope_ids=tuple(sorted(affected, key=str.encode)),
        scope_inventory_results=scope_results,
    )


def prove_hk_baseline_inventory(package_root: Path) -> tuple[BaselineInventoryDecision, ...]:
    """Run every frozen partial fixture and require exact expected decision bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_closed_catalogues(package_root, registry)
    _validate_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-inventory-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue")

    decisions: list[BaselineInventoryDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture")
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input")
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision")
        decision = _evaluate_hk_baseline_inventory(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "fixtures")
    return tuple(decisions)


def prove_hk_baseline_observation(package_root: Path) -> tuple[BaselineObservationDecision, ...]:
    """Run every frozen observation fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_observation_catalogues(package_root, registry)
    _validate_observation_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-observation-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_OBSERVATION_SCHEMA)

    decisions: list[BaselineObservationDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_OBSERVATION_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_OBSERVATION_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_OBSERVATION_SCHEMA)
        decision = _evaluate_hk_baseline_observation(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "observation fixtures")
    return tuple(decisions)


def prove_hk_baseline_evidence(package_root: Path) -> tuple[BaselineEvidenceDecision, ...]:
    """Run every frozen evidence fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_evidence_catalogues(package_root, registry)
    _validate_evidence_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-evidence-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_EVIDENCE_SCHEMA)

    decisions: list[BaselineEvidenceDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_EVIDENCE_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_EVIDENCE_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_EVIDENCE_SCHEMA)
        decision = _evaluate_hk_baseline_evidence(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "evidence fixtures")
    return tuple(decisions)


def prove_hk_baseline_state(package_root: Path) -> tuple[BaselineStateDecision, ...]:
    """Run every frozen present-state fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_state_catalogues(package_root, registry)
    _validate_state_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-state-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_STATE_SCHEMA)

    decisions: list[BaselineStateDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_STATE_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_STATE_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_STATE_SCHEMA)
        decision = _evaluate_hk_baseline_state(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "state fixtures")
    return tuple(decisions)


def prove_hk_baseline_limit(package_root: Path) -> tuple[BaselineLimitDecision, ...]:
    """Run every frozen assertion-limit fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_limit_catalogues(package_root, registry)
    _validate_limit_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-limit-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_LIMIT_SCHEMA)

    decisions: list[BaselineLimitDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_LIMIT_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_LIMIT_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_LIMIT_SCHEMA)
        decision = _evaluate_hk_baseline_limit(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "limit fixtures")
    return tuple(decisions)


def prove_hk_baseline_identity(package_root: Path) -> tuple[BaselineIdentityDecision, ...]:
    """Run every frozen identity fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_identity_catalogue(package_root, registry)
    _validate_identity_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-identity-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_IDENTITY_SCHEMA)

    decisions: list[BaselineIdentityDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_IDENTITY_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_IDENTITY_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_IDENTITY_SCHEMA)
        decision = _evaluate_hk_baseline_identity(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "identity fixtures")
    return tuple(decisions)


def prove_hk_baseline_disposition(
    package_root: Path,
) -> tuple[BaselineDispositionDecision, ...]:
    """Run every frozen disposition fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_disposition_catalogue(package_root, registry)
    _validate_disposition_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-disposition-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_DISPOSITION_SCHEMA)

    decisions: list[BaselineDispositionDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_DISPOSITION_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_DISPOSITION_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_DISPOSITION_SCHEMA)
        decision = _evaluate_hk_baseline_disposition(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "disposition fixtures")
    return tuple(decisions)


def prove_hk_baseline_record(package_root: Path) -> tuple[BaselineRecordDecision, ...]:
    """Run every frozen candidate-record fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_record_catalogue(package_root, registry)
    _validate_record_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-record-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_RECORD_SCHEMA)

    decisions: list[BaselineRecordDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_RECORD_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_RECORD_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_RECORD_SCHEMA)
        decision = _evaluate_hk_baseline_record(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "record fixtures")
    return tuple(decisions)


def prove_hk_baseline_release_accounting(
    package_root: Path,
) -> tuple[BaselineReleaseAccountingDecision, ...]:
    """Run every frozen initial-release-accounting fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_release_accounting_catalogue(package_root, registry)
    _validate_release_accounting_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-release-accounting-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_RELEASE_ACCOUNTING_SCHEMA)

    decisions: list[BaselineReleaseAccountingDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_RELEASE_ACCOUNTING_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_RELEASE_ACCOUNTING_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_RELEASE_ACCOUNTING_SCHEMA)
        decision = _evaluate_hk_baseline_release_accounting(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "release accounting fixtures")
    return tuple(decisions)


def prove_hk_baseline_review(package_root: Path) -> tuple[BaselineReviewDecision, ...]:
    """Run every frozen targeted-review fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_review_catalogues(package_root, registry)
    _validate_review_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-review-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_REVIEW_SCHEMA)

    decisions: list[BaselineReviewDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_REVIEW_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_REVIEW_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_REVIEW_SCHEMA)
        decision = _evaluate_hk_baseline_review(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "review fixtures")
    return tuple(decisions)


def prove_hk_baseline_history(package_root: Path) -> tuple[BaselineHistoryDecision, ...]:
    """Run every frozen bounded-history fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_history_catalogues(package_root, registry)
    _validate_history_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-history-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_HISTORY_SCHEMA)

    decisions: list[BaselineHistoryDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_HISTORY_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_HISTORY_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_HISTORY_SCHEMA)
        decision = _evaluate_hk_baseline_history(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "history fixtures")
    return tuple(decisions)


def prove_hk_baseline_change(package_root: Path) -> tuple[BaselineChangeDecision, ...]:
    """Run every frozen post-cutoff-change fixture and require exact expected bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_change_catalogue(package_root, registry)
    _validate_change_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/baseline-change-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CHANGE_SCHEMA)

    decisions: list[BaselineChangeDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CHANGE_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CHANGE_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CHANGE_SCHEMA)
        decision = _evaluate_hk_baseline_change(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "change fixtures")
    return tuple(decisions)


def prove_hk_current_observation(package_root: Path) -> tuple[CurrentObservationDecision, ...]:
    """Run every frozen ordinary current-observation fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_observation_catalogue(package_root, registry)
    _validate_current_observation_rules(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-observation-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_OBSERVATION_SCHEMA)

    decisions: list[CurrentObservationDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_OBSERVATION_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_OBSERVATION_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_OBSERVATION_SCHEMA)
        decision = _evaluate_hk_current_observation(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current observation fixtures")
    return tuple(decisions)


def prove_hk_current_evidence(package_root: Path) -> tuple[CurrentEvidenceDecision, ...]:
    """Run every frozen ordinary current-evidence fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_evidence_catalogue(package_root, registry)
    _validate_current_evidence_rules(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-evidence-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_EVIDENCE_SCHEMA)

    decisions: list[CurrentEvidenceDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_EVIDENCE_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_EVIDENCE_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_EVIDENCE_SCHEMA)
        decision = _evaluate_hk_current_evidence(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current evidence fixtures")
    return tuple(decisions)


def prove_hk_current_difference(package_root: Path) -> tuple[CurrentDifferenceDecision, ...]:
    """Run every frozen ordinary accepted-bundle difference fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_difference_catalogue(package_root, registry)
    _validate_current_difference_rules(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-difference-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_DIFFERENCE_SCHEMA)

    decisions: list[CurrentDifferenceDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_DIFFERENCE_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_DIFFERENCE_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_DIFFERENCE_SCHEMA)
        decision = _evaluate_hk_current_difference(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current difference fixtures")
    return tuple(decisions)


def prove_hk_current_cause(package_root: Path) -> tuple[CurrentCauseDecision, ...]:
    """Run every frozen ordinary change-cause fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_cause_catalogue(package_root, registry)
    _validate_current_cause_rules(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-cause-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_CAUSE_SCHEMA)

    decisions: list[CurrentCauseDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_CAUSE_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_CAUSE_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_CAUSE_SCHEMA)
        decision = _evaluate_hk_current_cause(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current cause fixtures")
    return tuple(decisions)


def prove_hk_current_commencement(
    package_root: Path,
) -> tuple[CurrentCommencementDecision, ...]:
    """Run every frozen commencement/legal-effect fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_commencement_catalogue(package_root, registry)
    _validate_current_commencement_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-commencement-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_COMMENCEMENT_SCHEMA)

    decisions: list[CurrentCommencementDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_COMMENCEMENT_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_COMMENCEMENT_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_COMMENCEMENT_SCHEMA)
        decision = _evaluate_hk_current_commencement(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current commencement fixtures")
    return tuple(decisions)


def prove_hk_current_cessation(package_root: Path) -> tuple[CurrentCessationDecision, ...]:
    """Run every frozen cessation/revival fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_cessation_catalogue(package_root, registry)
    _validate_current_cessation_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-cessation-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_CESSATION_SCHEMA)

    decisions: list[CurrentCessationDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_CESSATION_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_CESSATION_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_CESSATION_SCHEMA)
        decision = _evaluate_hk_current_cessation(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current cessation fixtures")
    return tuple(decisions)


def prove_hk_current_publication(
    package_root: Path,
) -> tuple[CurrentPublicationDecision, ...]:
    """Run every frozen Gazette publication/enactment fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_publication_catalogue(package_root, registry)
    _validate_current_publication_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-publication-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_PUBLICATION_SCHEMA)

    decisions: list[CurrentPublicationDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_PUBLICATION_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_PUBLICATION_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_PUBLICATION_SCHEMA)
        decision = _evaluate_hk_current_publication(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current publication fixtures")
    return tuple(decisions)


def prove_hk_current_text_event(package_root: Path) -> tuple[CurrentTextEventDecision, ...]:
    """Run every frozen amendment/correction/editorial fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_text_event_catalogue(package_root, registry)
    _validate_current_text_event_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-text-event-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_TEXT_EVENT_SCHEMA)

    decisions: list[CurrentTextEventDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_TEXT_EVENT_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_TEXT_EVENT_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_TEXT_EVENT_SCHEMA)
        decision = _evaluate_hk_current_text_event(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current text event fixtures")
    return tuple(decisions)


def prove_hk_reconstruction_plan_semantic(
    package_root: Path,
) -> tuple[ReconstructionPlanSemanticDecision, ...]:
    """Run every frozen pre-Plan semantic decision/challenge fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_reconstruction_plan_semantic_catalogue(package_root, registry)
    _validate_reconstruction_plan_semantic_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/reconstruction-plan-semantic-fixtures.json")
    _validate(
        registry,
        catalogue,
        "fixture_catalogue",
        schema=_RECONSTRUCTION_PLAN_SEMANTIC_SCHEMA,
    )

    decisions: list[ReconstructionPlanSemanticDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_RECONSTRUCTION_PLAN_SEMANTIC_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_RECONSTRUCTION_PLAN_SEMANTIC_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_RECONSTRUCTION_PLAN_SEMANTIC_SCHEMA)
        decision = _evaluate_reconstruction_plan_semantic(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(
            RulebookErrorCode.INVENTORY_MISMATCH,
            "reconstruction plan semantic fixtures",
        )
    return tuple(decisions)


def prove_hk_reconstruction_plan_validation(
    package_root: Path,
) -> tuple[ReconstructionPlanValidationDecision, ...]:
    """Run every frozen complete-Plan validation fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_reconstruction_plan_catalogue(package_root, registry)
    _validate_reconstruction_plan_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/reconstruction-plan-validation-fixtures.json")
    _validate(
        registry,
        catalogue,
        "fixture_catalogue",
        schema=_RECONSTRUCTION_PLAN_SCHEMA,
    )

    decisions: list[ReconstructionPlanValidationDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root,
            _text(raw_entry.get("expected_path"), "expected path"),
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_RECONSTRUCTION_PLAN_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_RECONSTRUCTION_PLAN_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_RECONSTRUCTION_PLAN_SCHEMA)
        decision = _evaluate_reconstruction_plan_validation(
            fixture_id,
            input_value,
            registry,
        )
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(
            RulebookErrorCode.INVENTORY_MISMATCH,
            "reconstruction plan validation fixtures",
        )
    return tuple(decisions)


def prove_hk_current_event(package_root: Path) -> tuple[CurrentEventDecision, ...]:
    """Run every frozen proved-event/missing-consolidation fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_event_catalogue(package_root, registry)
    _validate_current_event_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-event-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_EVENT_SCHEMA)

    decisions: list[CurrentEventDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_EVENT_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_EVENT_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_EVENT_SCHEMA)
        decision = _evaluate_hk_current_event(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current event fixtures")
    return tuple(decisions)


def prove_hk_current_disposition(package_root: Path) -> tuple[CurrentDispositionDecision, ...]:
    """Run every frozen ordinary current-disposition fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_disposition_catalogue(package_root, registry)
    _validate_current_disposition_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-disposition-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_DISPOSITION_SCHEMA)

    decisions: list[CurrentDispositionDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_DISPOSITION_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_DISPOSITION_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_DISPOSITION_SCHEMA)
        decision = _evaluate_hk_current_disposition(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current disposition fixtures")
    return tuple(decisions)


def prove_hk_current_record(package_root: Path) -> tuple[CurrentRecordDecision, ...]:
    """Run every frozen ordinary current-record fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_record_catalogue(package_root, registry)
    _validate_current_record_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-record-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_RECORD_SCHEMA)

    decisions: list[CurrentRecordDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_RECORD_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_RECORD_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_RECORD_SCHEMA)
        decision = _evaluate_hk_current_record(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current record fixtures")
    return tuple(decisions)


def prove_hk_current_release_accounting(
    package_root: Path,
) -> tuple[CurrentReleaseAccountingDecision, ...]:
    """Run every frozen ordinary current-release accounting fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_current_release_catalogue(package_root, registry)
    _validate_current_release_rule(package_root, registry)
    catalogue = _read_json(package_root / "catalogues/current-release-accounting-fixtures.json")
    _validate(registry, catalogue, "fixture_catalogue", schema=_CURRENT_RELEASE_SCHEMA)

    decisions: list[CurrentReleaseAccountingDecision] = []
    seen: set[str] = set()
    for raw_entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(raw_entry.get("fixture_id"), "fixture_id")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(raw_entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(raw_entry.get("expected_path"), "expected path")
        )
        if _fingerprint(fixture_path.read_bytes()) != raw_entry.get(
            "fixture_fingerprint"
        ) or _fingerprint(expected_path.read_bytes()) != raw_entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read_json(fixture_path)
        _validate(registry, fixture, "fixture", schema=_CURRENT_RELEASE_SCHEMA)
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        expected_declaration = fixture.get("expected_artifact")
        if not isinstance(expected_declaration, dict) or (
            expected_declaration.get("path") != raw_entry.get("expected_path")
            or expected_declaration.get("fingerprint") != raw_entry.get("expected_fingerprint")
        ):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_value = fixture.get("input")
        if not isinstance(input_value, dict):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "fixture input")
        _validate(registry, input_value, "input", schema=_CURRENT_RELEASE_SCHEMA)
        if _fingerprint(canonicalize(checked_json_value(input_value))) != fixture.get(
            "input_fingerprint"
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        expected = _read_json(expected_path)
        _validate(registry, expected, "decision", schema=_CURRENT_RELEASE_SCHEMA)
        decision = _evaluate_hk_current_release_accounting(fixture_id, input_value)
        if canonicalize(checked_json_value(decision.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(decision)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "current release fixtures")
    return tuple(decisions)


def prove_hk_baseline_ordered_path(
    package_root: Path,
) -> tuple[str, str, str, str, str, str, str, str, str]:
    """Prove the ordered path through complete initial-release accounting."""
    observation_decisions = prove_hk_baseline_observation(package_root)
    inventory_decisions = prove_hk_baseline_inventory(package_root)
    evidence_decisions = prove_hk_baseline_evidence(package_root)
    state_decisions = prove_hk_baseline_state(package_root)
    limit_decisions = prove_hk_baseline_limit(package_root)
    identity_decisions = prove_hk_baseline_identity(package_root)
    disposition_decisions = prove_hk_baseline_disposition(package_root)
    record_decisions = prove_hk_baseline_record(package_root)
    release_accounting_decisions = prove_hk_baseline_release_accounting(package_root)
    passing_observations = tuple(
        decision for decision in observation_decisions if decision.processing_outcome == "PASS"
    )
    passing_inventories = tuple(
        decision for decision in inventory_decisions if decision.processing_outcome == "PASS"
    )
    golden_evidence = tuple(
        decision
        for decision in evidence_decisions
        if decision.fixture_id == "HKLEG-BASE-EVID-FIX-001"
    )
    golden_state = tuple(
        decision
        for decision in state_decisions
        if decision.fixture_id == "HKLEG-BASE-STATE-FIX-001"
    )
    golden_limit = tuple(
        decision
        for decision in limit_decisions
        if decision.fixture_id == "HKLEG-BASE-LIMIT-FIX-001"
    )
    golden_identity = tuple(
        decision
        for decision in identity_decisions
        if decision.fixture_id == "HKLEG-BASE-ID-FIX-001"
    )
    golden_disposition = tuple(
        decision
        for decision in disposition_decisions
        if decision.fixture_id == "HKLEG-BASE-DISP-FIX-001"
    )
    golden_record = tuple(
        decision for decision in record_decisions if decision.fixture_id == "HKLEG-BASE-REC-FIX-001"
    )
    golden_release_accounting = tuple(
        decision
        for decision in release_accounting_decisions
        if decision.fixture_id == "HKLEG-BASE-REL-FIX-001"
    )
    if (
        len(passing_observations) != 1
        or passing_observations[0].next_action != "RUN_HKLEG_BASE_INV_001"
        or len(passing_inventories) != 1
        or len(golden_evidence) != 1
        or golden_evidence[0].processing_outcome != "PASS"
        or golden_evidence[0].next_action != "RUN_HKLEG_BASE_STATE_001"
        or len(golden_state) != 1
        or golden_state[0].processing_outcome != "PASS"
        or golden_state[0].next_action != "RUN_HKLEG_BASE_LIMIT_001"
        or len(golden_limit) != 1
        or golden_limit[0].processing_outcome != "PASS"
        or golden_limit[0].next_action != "RUN_HKLEG_BASE_ID_001"
        or len(golden_identity) != 1
        or golden_identity[0].processing_outcome != "PASS"
        or golden_identity[0].next_action != "RUN_HKLEG_BASE_DISP_001"
        or len(golden_disposition) != 1
        or golden_disposition[0].processing_outcome != "PASS"
        or golden_disposition[0].legal_disposition != "SEARCHABLE_CURRENT"
        or golden_disposition[0].next_action != "RUN_HKLEG_BASE_REC_001"
        or len(golden_record) != 1
        or golden_record[0].processing_outcome != "PASS"
        or golden_record[0].candidate_record is None
        or golden_record[0].next_action != "RUN_HKLEG_BASE_REL_001"
        or len(golden_release_accounting) != 1
        or golden_release_accounting[0].processing_outcome != "PASS"
        or golden_release_accounting[0].release_accounting_fingerprint is None
        or golden_release_accounting[0].next_action != "BUILD_CANDIDATE_CORPUS_RELEASE"
    ):
        raise RulebookError(RulebookErrorCode.AMBIGUOUS, "baseline ordered path")
    return (
        HK_BASELINE_OBSERVATION_RULE_ID,
        HK_BASELINE_INVENTORY_RULE_ID,
        HK_BASELINE_EVIDENCE_RULE_ID,
        HK_BASELINE_STATE_RULE_ID,
        HK_BASELINE_LIMIT_RULE_ID,
        HK_BASELINE_IDENTITY_RULE_ID,
        HK_BASELINE_DISPOSITION_RULE_ID,
        HK_BASELINE_RECORD_RULE_ID,
        HK_BASELINE_RELEASE_ACCOUNTING_RULE_ID,
    )
