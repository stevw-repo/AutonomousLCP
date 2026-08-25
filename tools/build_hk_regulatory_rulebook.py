"""Mechanically rebuild the honest NOT_READY HKEX Regulatory package manifest."""

from __future__ import annotations

import json
import re
from base64 import b64encode
from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import NotRequired, Required, TypedDict, Unpack
from unicodedata import normalize

import rfc8785
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_BOUNDARY_DECISION_CASE_COUNT,
    HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
    HKEX_BOUNDARY_DECISION_RULE_ID,
    HKEX_CONFORMANCE_CASE_COUNT,
    HKEX_CONFORMANCE_COVERAGE_CELL_COUNT,
    HKEX_CONFORMANCE_PAIR_COUNT,
    HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
    HKEX_CONSOLIDATED_RULEBOOKS_SOURCE_ID,
    HKEX_COVERAGE_DECISION_CASE_COUNT,
    HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
    HKEX_COVERAGE_DECISION_RULE_ID,
    HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
    HKEX_ENGLISH_RECORD_RULE_ID,
    HKEX_FEES_RULES_SOURCE_ID,
    HKEX_GEM_SCOPE_ID,
    HKEX_IDENTITY_DECISION_CASE_COUNT,
    HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
    HKEX_IDENTITY_DECISION_RULE_ID,
    HKEX_MAIN_SCOPE_ID,
    HKEX_PACKAGE_INTEGRITY_CASE_COUNT,
    HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION,
    HKEX_PACKAGE_INTEGRITY_RULE_ID,
    HKEX_PARTITION_DECISION_CASE_COUNT,
    HKEX_PARTITION_DECISION_CONTRACT_VERSION,
    HKEX_PARTITION_DECISION_RULE_ID,
    HKEX_PARTITION_MEASUREMENT_FIELDS,
    HKEX_RECORD_IDENTITY_CONTRACT_VERSION,
    HKEX_RECORD_IDENTITY_RULE_ID,
    HKEX_REGULATORY_FORMS_SOURCE_ID,
    HKEX_REGULATORY_SOURCE_IDS,
    HKEX_RENDERING_DECISION_CASE_COUNT,
    HKEX_RENDERING_DECISION_CONTRACT_VERSION,
    HKEX_RENDERING_DECISION_RULE_ID,
    HKEX_RULE_UPDATES_SOURCE_ID,
    HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
    HKEX_SCOPE_IDS,
    HKEX_SOURCE_DECISION_CASE_COUNT,
    HKEX_SOURCE_DECISION_CONTRACT_VERSION,
    HKEX_SOURCE_DECISION_RULE_ID,
    HKEX_STATE_DECISION_CASE_COUNT,
    HKEX_STATE_DECISION_CONTRACT_VERSION,
    HKEX_STATE_DECISION_RULE_ID,
    HKEXBoundaryAssertionScope,
    HKEXBoundaryOutcome,
    HKEXBoundaryReason,
    HKEXBranchState,
    HKEXChineseEvidenceState,
    HKEXComponentClass,
    HKEXComponentContinuityRequest,
    HKEXContinuityEvent,
    HKEXContinuitySupport,
    HKEXCoverageAssertionScope,
    HKEXCoverageExcludedUnit,
    HKEXCoverageFidelity,
    HKEXCoverageOutcome,
    HKEXCoverageReason,
    HKEXCoverageUnitAccounting,
    HKEXCoverageUnitOutcome,
    HKEXDefinitionScope,
    HKEXEnglishConstructionRequest,
    HKEXEnglishDisposition,
    HKEXEnglishReason,
    HKEXEnglishRecordUnit,
    HKEXEnglishServingProfile,
    HKEXEnglishSourceTree,
    HKEXEnglishSourceUnit,
    HKEXEnglishUnitKind,
    HKEXExistingComponentIdentity,
    HKEXExistingSearchRecord,
    HKEXIdentityAssertionScope,
    HKEXIdentityDecisionOutcome,
    HKEXIdentityDecisionReason,
    HKEXIdentityLookupRecord,
    HKEXLegalLocationBasis,
    HKEXMembership,
    HKEXObservationGap,
    HKEXObservedComponentCandidate,
    HKEXPackageAssertionScope,
    HKEXPackageIntegrityOutcome,
    HKEXPackageIntegrityReason,
    HKEXPartitionAssertionScope,
    HKEXPartitionCandidateCut,
    HKEXPartitionOutcome,
    HKEXPartitionReason,
    HKEXRecordChange,
    HKEXRecordIdentityRequest,
    HKEXRecordResponsibility,
    HKEXRecordUnitKind,
    HKEXRegulatoryObjectClass,
    HKEXRenderingAssertionScope,
    HKEXRenderingIdentityConsequence,
    HKEXRenderingOutcome,
    HKEXRenderingProjectionKind,
    HKEXRenderingReason,
    HKEXRenderingVectorResponsibility,
    HKEXRepairAttempt,
    HKEXSearchRecordLineage,
    HKEXSearchRecordLineageType,
    HKEXSourceAssertionScope,
    HKEXSourceContractState,
    HKEXSourceDecision,
    HKEXSourceDecisionOutcome,
    HKEXSourceDecisionReason,
    HKEXSourceEvidenceRole,
    HKEXSourceEvidenceState,
    HKEXSourceUnitRole,
    HKEXStateAssertionScope,
    HKEXStateConformanceOutcome,
    HKEXStateDecisionReason,
    HKEXTraceabilityReference,
    HKEXTraceabilityReferenceType,
    HKEXUnsupportedRetirementBasis,
    HKEXWordingRelationship,
    canonical_hkex_coverage_units,
    construct_hkex_english_request,
    decide_hkex_coverage_case,
    decide_hkex_identity_case,
    decide_hkex_partition_case,
    decide_hkex_record_identity,
    hkex_boundary_decision_case_from_document,
    hkex_coverage_decision_case_from_document,
    hkex_identity_decision_case_from_document,
    hkex_package_integrity_case_from_document,
    hkex_partition_decision_case_from_document,
    hkex_record_identity_request_from_document,
    hkex_rendering_decision_case_from_document,
    hkex_source_decision_case_from_document,
    hkex_state_decision_case_from_document,
    run_hkex_boundary_case,
    run_hkex_coverage_case,
    run_hkex_identity_case,
    run_hkex_package_integrity_case,
    run_hkex_partition_case,
    run_hkex_rendering_case,
    run_hkex_source_case,
    run_hkex_state_case,
    validate_hkex_conformance_universe,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_regulatory_package"

ROLES = {
    "attestations": "ATTESTATION",
    "catalogues": "CATALOGUE",
    "contracts": "CONTRACT",
    "evaluations": "EVALUATION",
    "expected": "EXPECTED_ARTIFACT",
    "profiles": "PROFILE",
    "renderers": "RENDERER",
    "rules": "RULES",
    "scopes": "SCOPE_REGISTRY",
    "sources": "SOURCE_UNIVERSE",
}

BLOCKERS: list[JsonValue] = [
    "HKREG_BASELINE_UNBUILT",
    "HKREG_COMPONENT_INVENTORY_UNBUILT",
    "HKREG_CONFORMANCE_SUITE_UNADMITTED",
    "HKREG_EFFECTIVE_STATE_REAL_EVIDENCE_UNADMITTED",
    "HKREG_ENDPOINT_CONTRACTS_UNADMITTED",
    "HKREG_ENGLISH_RECORD_WORKFLOW_UNADMITTED",
    "HKREG_MODEL_PROFILES_UNADMITTED",
    "HKREG_NAMED_OWNER_ATTESTATION_MISSING",
    "HKREG_REAL_SOURCE_BYTES_MISSING",
    "HKREG_RECORD_IDENTITY_REAL_EVIDENCE_UNADMITTED",
    "HKREG_RETRIEVAL_EVALUATION_UNADMITTED",
]

_SYNTHETIC_PROFILE_FINGERPRINT = f"sha256:{'a' * 64}"
_SYNTHETIC_SOURCE_FINGERPRINT = f"sha256:{'b' * 64}"
_COVERAGE_REORDER_MEMBER_COUNT = 2


class _SyntheticCodepointCounter:
    """Frozen source-neutral fixture counter; never an admitted tokenizer."""

    profile_id = "synthetic-hkex-english-profile-1"
    profile_fingerprint = _SYNTHETIC_PROFILE_FINGERPRINT
    tokenizer_id = "synthetic-codepoint-counter-1"

    def count(self, text: str) -> int:
        return len(text)


class _EnglishUnitOptions(TypedDict):
    parent: Required[str | None]
    children: NotRequired[tuple[str, ...]]
    role: NotRequired[HKEXSourceUnitRole]
    kind: NotRequired[HKEXEnglishUnitKind]
    dependencies: NotRequired[tuple[str, ...]]
    meaning_bearing: NotRequired[bool]


class _EnglishRecordOptions(TypedDict, total=False):
    dependencies: tuple[str, ...]
    children: tuple[str, ...]
    state: HKEXSourceContractState
    indivisible: bool


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _json_object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if not isinstance(checked, dict):
        raise TypeError
    return checked


def _json_array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError
    return value


def _json_integer_value(value: JsonValue) -> int:
    if type(value) is not int:
        raise TypeError
    return value


def _mutable_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError
    return value


def _role(path: str) -> str:
    if path.startswith("fixtures/"):
        return "DETERMINISTIC_FIXTURE"
    return ROLES[path.split("/", maxsplit=1)[0]]


def build_effective_state_catalogue() -> dict[str, JsonValue]:
    """Bind the one frozen source-neutral ADR 0071 fixture/result pair."""
    fixture_path = "fixtures/deterministic/HKREG-EFFECTIVE-STATE-FIX-001.json"
    expected_path = "expected/effective-state/HKREG-EFFECTIVE-STATE-FIX-001.json"
    return {
        "catalogue_id": "asklegal.hk-regulatory.effective-state.fixtures",
        "version": "1.0.0",
        "status": "FROZEN_PARTIAL",
        "accepted_complete_real_source_universe": False,
        "synthetic_case_count": 22,
        "fixtures": [
            {
                "fixture_id": "HKREG-EFFECTIVE-STATE-FIX-001",
                "path": fixture_path,
                "fixture_fingerprint": _fingerprint((PACKAGE_ROOT / fixture_path).read_bytes()),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint((PACKAGE_ROOT / expected_path).read_bytes()),
            }
        ],
    }


def build_component_continuity_catalogue() -> dict[str, JsonValue]:
    """Bind the frozen source-neutral component continuity fixture/result pair."""
    fixture_path = "fixtures/deterministic/HKREG-CONTINUITY-FIX-001.json"
    expected_path = "expected/component-continuity/HKREG-CONTINUITY-FIX-001.json"
    return {
        "catalogue_id": "asklegal.hk-regulatory.component-continuity.fixtures",
        "version": "1.0.0",
        "status": "FROZEN_PARTIAL",
        "accepted_complete_real_source_universe": False,
        "synthetic_case_count": 15,
        "fixtures": [
            {
                "fixture_id": "HKREG-CONTINUITY-FIX-001",
                "path": fixture_path,
                "fixture_fingerprint": _fingerprint((PACKAGE_ROOT / fixture_path).read_bytes()),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint((PACKAGE_ROOT / expected_path).read_bytes()),
            }
        ],
    }


def _english_profile(
    *,
    max_text_tokens: int = 100_000,
    max_metadata_bytes: int = 100_000,
    authority_note: str = "None",
) -> HKEXEnglishServingProfile:
    return HKEXEnglishServingProfile(
        profile_id=_SyntheticCodepointCounter.profile_id,
        profile_fingerprint=_SyntheticCodepointCounter.profile_fingerprint,
        tokenizer_id=_SyntheticCodepointCounter.tokenizer_id,
        max_text_tokens=max_text_tokens,
        max_metadata_bytes=max_metadata_bytes,
        country="Hong Kong",
        jurisdiction="Hong Kong",
        material_type="regulatory_material",
        source="Hong Kong Exchanges and Clearing Limited",
        authority_note=authority_note,
    )


def _english_unit(
    unit_id: str,
    order: int,
    text: str,
    **options: Unpack[_EnglishUnitOptions],
) -> HKEXEnglishSourceUnit:
    return HKEXEnglishSourceUnit(
        source_unit_id=unit_id,
        parent_source_unit_id=options["parent"],
        child_source_unit_ids=options.get("children", ()),
        source_order=order,
        kind=options.get("kind", HKEXEnglishUnitKind.BODY_TEXT),
        role=options.get("role", HKEXSourceUnitRole.PRIMARY),
        text=text,
        source_range=f"synthetic-hkex-artifact#range-{order}",
        required_context_unit_ids=options.get("dependencies", ()),
        meaning_bearing=options.get("meaning_bearing", True),
        content_fingerprint=_fingerprint(text.encode()),
    )


def _english_record(
    record_id: str,
    primary: tuple[str, ...],
    **options: Unpack[_EnglishRecordOptions],
) -> HKEXEnglishRecordUnit:
    return HKEXEnglishRecordUnit(
        record_unit_id=record_id,
        primary_source_unit_ids=primary,
        dependency_source_unit_ids=options.get("dependencies", ()),
        referenced_locations=(),
        child_record_unit_ids=options.get("children", ()),
        source_contract_state=options.get("state", HKEXSourceContractState.SUPPORTED),
        indivisible=options.get("indivisible", False),
    )


def _english_tree(
    state: HKEXBranchState,
    *,
    source_contract_state: HKEXSourceContractState = HKEXSourceContractState.SUPPORTED,
    partition: bool = False,
    branch_suffix: str = "",
) -> HKEXEnglishSourceTree:
    if partition:
        primary_ids = ("unit-a", "unit-b", "unit-c")
        source_units = (
            _english_unit(
                "context",
                0,
                "Rule 9 — Synthetic partition fixture",
                parent=None,
                children=primary_ids,
                role=HKEXSourceUnitRole.CONTEXT_ONLY,
                kind=HKEXEnglishUnitKind.HEADING,
            ),
            *(
                _english_unit(
                    unit_id,
                    index,
                    f"9.0{index} " + marker * 120,
                    parent="context",
                    dependencies=("context",),
                )
                for index, (unit_id, marker) in enumerate(
                    zip(primary_ids, ("A", "B", "C"), strict=True), start=1
                )
            ),
        )
        children = tuple(f"record-{unit_id}" for unit_id in primary_ids)
        records = (
            _english_record(
                "record-root",
                primary_ids,
                dependencies=("context",),
                children=children,
                state=source_contract_state,
            ),
            *(
                _english_record(
                    record_id,
                    (unit_id,),
                    dependencies=("context",),
                    indivisible=True,
                )
                for record_id, unit_id in zip(children, primary_ids, strict=True)
            ),
        )
    else:
        source_units = (
            _english_unit(
                "context",
                0,
                "Rule 2 — Synthetic ordinary fixture",
                parent=None,
                children=("rule-a",),
                role=HKEXSourceUnitRole.CONTEXT_ONLY,
                kind=HKEXEnglishUnitKind.HEADING,
            ),
            _english_unit(
                "rule-a",
                1,
                "2.01 An issuer must comply with the Exchange Listing Rules.",
                parent="context",
                dependencies=("context",),
            ),
        )
        records = (
            _english_record(
                "record-root",
                ("rule-a",),
                dependencies=("context",),
                state=source_contract_state,
                indivisible=True,
            ),
        )
    return HKEXEnglishSourceTree(
        tree_id=f"synthetic-tree-{state.value.lower()}{branch_suffix}",
        component_id="synthetic-component-main-2.01",
        scope_id=HKEX_MAIN_SCOPE_ID,
        branch_id=f"synthetic-branch-{state.value.lower()}{branch_suffix}",
        branch_state=state,
        component_class=HKEXComponentClass.ORDINARY_RULE,
        component_label="Synthetic Main Board Listing Rules",
        location_label="Rule 2.01" if not partition else "Rule 9",
        official_heading="Synthetic conformance fixture",
        root_source_unit_id="context",
        source_units=source_units,
        root_record_unit_ids=("record-root",),
        record_units=records,
        source_rule_id=HKEX_ENGLISH_RECORD_RULE_ID,
        source_artifact_fingerprints=(_SYNTHETIC_SOURCE_FINGERPRINT,),
    )


def _nested_partition_tree(*, branch_suffix: str = "-nested") -> HKEXEnglishSourceTree:
    primary_ids = ("unit-a", "unit-b1", "unit-b2", "unit-c")
    source_units = (
        _english_unit(
            "context",
            0,
            "Rule 10 — Synthetic recursive partition fixture",
            parent=None,
            children=primary_ids,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
            kind=HKEXEnglishUnitKind.HEADING,
        ),
        *(
            _english_unit(
                unit_id,
                index,
                f"10.0{index} " + marker * 120,
                parent="context",
                dependencies=("context",),
            )
            for index, (unit_id, marker) in enumerate(
                zip(primary_ids, ("A", "B", "D", "C"), strict=True), start=1
            )
        ),
    )
    records = (
        _english_record(
            "record-root",
            primary_ids,
            dependencies=("context",),
            children=("record-a", "record-b", "record-c"),
        ),
        _english_record(
            "record-a",
            ("unit-a",),
            dependencies=("context",),
            indivisible=True,
        ),
        _english_record(
            "record-b",
            ("unit-b1", "unit-b2"),
            dependencies=("context",),
            children=("record-b1", "record-b2"),
        ),
        _english_record(
            "record-b1",
            ("unit-b1",),
            dependencies=("context",),
            indivisible=True,
        ),
        _english_record(
            "record-b2",
            ("unit-b2",),
            dependencies=("context",),
            indivisible=True,
        ),
        _english_record(
            "record-c",
            ("unit-c",),
            dependencies=("context",),
            indivisible=True,
        ),
    )
    return HKEXEnglishSourceTree(
        tree_id=f"synthetic-tree-current{branch_suffix}",
        component_id="synthetic-component-main-10",
        scope_id=HKEX_MAIN_SCOPE_ID,
        branch_id=f"synthetic-branch-current{branch_suffix}",
        branch_state=HKEXBranchState.CURRENT,
        component_class=HKEXComponentClass.ORDINARY_RULE,
        component_label="Synthetic Main Board Listing Rules",
        location_label="Rule 10",
        official_heading="Synthetic recursive partition fixture",
        root_source_unit_id="context",
        source_units=source_units,
        root_record_unit_ids=("record-root",),
        record_units=records,
        source_rule_id=HKEX_ENGLISH_RECORD_RULE_ID,
        source_artifact_fingerprints=(_SYNTHETIC_SOURCE_FINGERPRINT,),
    )


def _coverage_board_tree(
    tree: HKEXEnglishSourceTree,
    *,
    scope_id: str,
    suffix: str,
) -> HKEXEnglishSourceTree:
    """Give one valid source-neutral tree an independent board identity."""
    return replace(
        tree,
        tree_id=f"{tree.tree_id}{suffix}",
        component_id=f"{tree.component_id}{suffix}",
        scope_id=scope_id,
        branch_id=f"{tree.branch_id}{suffix}",
    )


def _coverage_classification_tree() -> HKEXEnglishSourceTree:
    """Build current primary, context-only, and presentation-only units."""
    source_units = (
        _english_unit(
            "context",
            0,
            "Appendix 1 — Synthetic classification fixture",
            parent=None,
            children=("rule", "layout"),
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
            kind=HKEXEnglishUnitKind.HEADING,
        ),
        _english_unit(
            "rule",
            1,
            "1.01 An issuer must retain the required record.",
            parent="context",
            dependencies=("context",),
        ),
        _english_unit(
            "layout",
            2,
            "----",
            parent="context",
            role=HKEXSourceUnitRole.PRESENTATION_ONLY,
            kind=HKEXEnglishUnitKind.PRESENTATION,
            meaning_bearing=False,
        ),
    )
    return HKEXEnglishSourceTree(
        tree_id="synthetic-tree-coverage-classification",
        component_id="synthetic-component-main-classification",
        scope_id=HKEX_MAIN_SCOPE_ID,
        branch_id="synthetic-branch-current-classification",
        branch_state=HKEXBranchState.CURRENT,
        component_class=HKEXComponentClass.APPENDIX,
        component_label="Synthetic Main Board classification fixture",
        location_label="Appendix 1",
        official_heading="Synthetic classification fixture",
        root_source_unit_id="context",
        source_units=source_units,
        root_record_unit_ids=("record-rule",),
        record_units=(
            _english_record(
                "record-rule",
                ("rule",),
                dependencies=("context",),
                indivisible=True,
            ),
        ),
        source_rule_id=HKEX_ENGLISH_RECORD_RULE_ID,
        source_artifact_fingerprints=(_SYNTHETIC_SOURCE_FINGERPRINT,),
    )


def _coverage_dependency_tree() -> HKEXEnglishSourceTree:
    """Build one primary governing unit reused as labelled dependency."""
    source_units = (
        _english_unit(
            "context",
            0,
            "Appendix 2 — Synthetic dependency fixture",
            parent=None,
            children=("governing", "rule"),
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
            kind=HKEXEnglishUnitKind.HEADING,
        ),
        _english_unit(
            "governing",
            1,
            "2.01 This Appendix applies to every listed issuer.",
            parent="context",
            dependencies=("context",),
        ),
        _english_unit(
            "rule",
            2,
            "2.02 An issuer must publish the specified notice.",
            parent="context",
            dependencies=("context", "governing"),
        ),
    )
    return HKEXEnglishSourceTree(
        tree_id="synthetic-tree-coverage-dependency",
        component_id="synthetic-component-main-dependency",
        scope_id=HKEX_MAIN_SCOPE_ID,
        branch_id="synthetic-branch-current-dependency",
        branch_state=HKEXBranchState.CURRENT,
        component_class=HKEXComponentClass.APPENDIX,
        component_label="Synthetic Main Board dependency fixture",
        location_label="Appendix 2",
        official_heading="Synthetic dependency fixture",
        root_source_unit_id="context",
        source_units=source_units,
        root_record_unit_ids=("record-governing", "record-rule"),
        record_units=(
            _english_record(
                "record-governing",
                ("governing",),
                dependencies=("context",),
                indivisible=True,
            ),
            _english_record(
                "record-rule",
                ("rule",),
                dependencies=("context", "governing"),
                indivisible=True,
            ),
        ),
        source_rule_id=HKEX_ENGLISH_RECORD_RULE_ID,
        source_artifact_fingerprints=(_SYNTHETIC_SOURCE_FINGERPRINT,),
    )


def _coverage_complex_tree() -> HKEXEnglishSourceTree:
    """Build complete table and Form semantic/presentation accounting."""
    specifications = (
        ("body", HKEXEnglishUnitKind.BODY_TEXT, "3.01 Complete every applicable item."),
        ("table-header", HKEXEnglishUnitKind.TABLE_HEADER, "Category | Requirement"),
        ("table-row", HKEXEnglishUnitKind.TABLE_ROW, "A | Publish a notice"),
        ("table-note", HKEXEnglishUnitKind.TABLE_NOTE, "Note: Category A is mandatory."),
        ("form-instruction", HKEXEnglishUnitKind.FORM_INSTRUCTION, "Complete Part I."),
        ("form-label", HKEXEnglishUnitKind.FORM_LABEL, "Issuer name"),
        ("form-control", HKEXEnglishUnitKind.FORM_CONTROL, "[CHECKBOX]"),
    )
    primary_ids = tuple(item[0] for item in specifications)
    source_units = (
        _english_unit(
            "context",
            0,
            "Appendix 3 — Synthetic table and Form fixture",
            parent=None,
            children=(*primary_ids, "layout"),
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
            kind=HKEXEnglishUnitKind.HEADING,
        ),
        *(
            _english_unit(
                unit_id,
                index,
                text,
                parent="context",
                dependencies=("context",),
                kind=kind,
            )
            for index, (unit_id, kind, text) in enumerate(specifications, start=1)
        ),
        _english_unit(
            "layout",
            len(specifications) + 1,
            "________________",
            parent="context",
            role=HKEXSourceUnitRole.PRESENTATION_ONLY,
            kind=HKEXEnglishUnitKind.PRESENTATION,
            meaning_bearing=False,
        ),
    )
    return HKEXEnglishSourceTree(
        tree_id="synthetic-tree-coverage-complex",
        component_id="synthetic-component-main-complex",
        scope_id=HKEX_MAIN_SCOPE_ID,
        branch_id="synthetic-branch-current-complex",
        branch_state=HKEXBranchState.CURRENT,
        component_class=HKEXComponentClass.APPENDIX,
        component_label="Synthetic Main Board complex fixture",
        location_label="Appendix 3",
        official_heading="Synthetic table and Form fixture",
        root_source_unit_id="context",
        source_units=source_units,
        root_record_unit_ids=("record-complex",),
        record_units=(
            _english_record(
                "record-complex",
                primary_ids,
                dependencies=("context",),
                indivisible=True,
            ),
        ),
        source_rule_id=HKEX_ENGLISH_RECORD_RULE_ID,
        source_artifact_fingerprints=(_SYNTHETIC_SOURCE_FINGERPRINT,),
    )


def _english_cases() -> tuple[tuple[str, HKEXEnglishConstructionRequest], ...]:
    ordinary = HKEXEnglishConstructionRequest(
        _english_tree(HKEXBranchState.CURRENT), _english_profile(), None
    )
    partition_tree = _english_tree(HKEXBranchState.CURRENT, partition=True)
    full_part = (
        construct_hkex_english_request(
            HKEXEnglishConstructionRequest(partition_tree, _english_profile(), None),
            _SyntheticCodepointCounter(),
        )
        .record_results[0]
        .parts[0]
    )
    return (
        ("HKREG-ENGLISH-CASE-001", ordinary),
        (
            "HKREG-ENGLISH-CASE-002",
            HKEXEnglishConstructionRequest(
                _english_tree(HKEXBranchState.TRANSITIONAL_CURRENT),
                _english_profile(),
                "Applies to synthetic pre-2026 issuers",
            ),
        ),
        (
            "HKREG-ENGLISH-CASE-003",
            HKEXEnglishConstructionRequest(
                _english_tree(HKEXBranchState.FUTURE_FIXED_DATE),
                _english_profile(),
                None,
            ),
        ),
        (
            "HKREG-ENGLISH-CASE-004",
            HKEXEnglishConstructionRequest(
                _english_tree(HKEXBranchState.SUPERSEDED), _english_profile(), None
            ),
        ),
        (
            "HKREG-ENGLISH-CASE-005",
            HKEXEnglishConstructionRequest(
                _english_tree(HKEXBranchState.UNKNOWN), _english_profile(), None
            ),
        ),
        (
            "HKREG-ENGLISH-CASE-006",
            HKEXEnglishConstructionRequest(
                partition_tree,
                _english_profile(max_text_tokens=full_part.measurement.text_tokens - 1),
                None,
            ),
        ),
        (
            "HKREG-ENGLISH-CASE-007",
            HKEXEnglishConstructionRequest(
                _english_tree(HKEXBranchState.CURRENT),
                _english_profile(max_text_tokens=1),
                None,
            ),
        ),
        (
            "HKREG-ENGLISH-CASE-008",
            HKEXEnglishConstructionRequest(
                _english_tree(
                    HKEXBranchState.CURRENT,
                    source_contract_state=HKEXSourceContractState.UNKNOWN,
                ),
                _english_profile(),
                None,
            ),
        ),
    )


def build_english_record_fixture() -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """Build eight frozen source-neutral ADR 0073 request/result cases."""
    cases = _english_cases()
    fixture = _json_object(
        {
            "fixture_id": "HKREG-ENGLISH-RECORD-FIX-001",
            "contract_version": HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            "synthetic_tokenizer": {
                "profile_id": _SyntheticCodepointCounter.profile_id,
                "profile_fingerprint": _SyntheticCodepointCounter.profile_fingerprint,
                "tokenizer_id": _SyntheticCodepointCounter.tokenizer_id,
                "admitted_for_real_records": False,
            },
            "cases": [
                {"case_id": case_id, "request": request.document()} for case_id, request in cases
            ],
        }
    )
    expected = _json_object(
        {
            "fixture_id": "HKREG-ENGLISH-RECORD-FIX-001",
            "contract_version": HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            "cases": [
                construct_hkex_english_request(request, _SyntheticCodepointCounter()).document(
                    case_id=case_id
                )
                for case_id, request in cases
            ],
        }
    )
    return fixture, expected


def build_english_record_catalogue() -> dict[str, JsonValue]:
    """Bind the frozen source-neutral English request/result pair."""
    fixture_path = "fixtures/deterministic/HKREG-ENGLISH-RECORD-FIX-001.json"
    expected_path = "expected/english-record/HKREG-ENGLISH-RECORD-FIX-001.json"
    return {
        "catalogue_id": "asklegal.hk-regulatory.english-record.fixtures",
        "version": "1.0.0",
        "status": "FROZEN_PARTIAL",
        "accepted_complete_real_source_universe": False,
        "synthetic_case_count": 8,
        "fixtures": [
            {
                "fixture_id": "HKREG-ENGLISH-RECORD-FIX-001",
                "path": fixture_path,
                "fixture_fingerprint": _fingerprint((PACKAGE_ROOT / fixture_path).read_bytes()),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint((PACKAGE_ROOT / expected_path).read_bytes()),
            }
        ],
    }


_LEGAL_ITEM_ID = f"lit_{'1' * 48}"
_OFFICIAL_VERSION_ID = f"ofv_{'2' * 48}"
_LEGAL_LOCATION_ID = f"loc_{'3' * 48}"
_FIRST_RECORD_ID = f"rec_{'4' * 48}"
_SECOND_RECORD_ID = f"rec_{'5' * 48}"
_OTHER_PAYLOAD_FINGERPRINT = f"sha256:{'9' * 64}"


class _IdentityRequestOptions(TypedDict, total=False):
    change: Required[HKEXRecordChange]
    existing_records: tuple[HKEXExistingSearchRecord, ...]
    predecessor_ids: tuple[str, ...]
    current_legal_support: bool


def _identity_ref(
    ref_type: HKEXTraceabilityReferenceType,
    digit: str,
) -> HKEXTraceabilityReference:
    return HKEXTraceabilityReference(
        ref_type=ref_type,
        ref_id=f"evd_{digit * 48}",
        fingerprint=f"sha256:{digit * 64}",
    )


def _identity_existing(
    record_id: str,
    payload_fingerprint: str,
    *,
    selected: bool,
) -> HKEXExistingSearchRecord:
    return HKEXExistingSearchRecord(
        search_record_id=record_id,
        serving_payload_fingerprint=payload_fingerprint,
        scope_id=HKEX_MAIN_SCOPE_ID,
        legal_item_id=_LEGAL_ITEM_ID,
        currently_selected=selected,
    )


def _identity_request(
    case_number: int,
    construction: HKEXEnglishConstructionRequest,
    **options: Unpack[_IdentityRequestOptions],
) -> HKEXRecordIdentityRequest:
    return HKEXRecordIdentityRequest(
        decision_id=f"synthetic-hkex-record-identity-decision-{case_number:03d}",
        construction=construction,
        root_record_unit_id="record-root",
        part_number=1,
        legal_item_id=_LEGAL_ITEM_ID,
        official_version_ids=(_OFFICIAL_VERSION_ID,),
        legal_location_ids=(_LEGAL_LOCATION_ID,),
        evidence_refs=(_identity_ref(HKEXTraceabilityReferenceType.SOURCE_SNAPSHOT, "6"),),
        authority_note_decision_ref=_identity_ref(HKEXTraceabilityReferenceType.DECISION, "7"),
        authority_note_supporting_refs=(),
        current_legal_support=options.get("current_legal_support", True),
        existing_records=options.get("existing_records", ()),
        predecessor_search_record_ids=options.get("predecessor_ids", ()),
        change=options["change"],
        decision_evidence_fingerprint=_SYNTHETIC_PROFILE_FINGERPRINT,
        legal_desk_actor="synthetic-hk-regulatory-legal-desk",
    )


def _identity_cases() -> tuple[tuple[str, HKEXRecordIdentityRequest], ...]:
    ordinary = HKEXEnglishConstructionRequest(
        _english_tree(HKEXBranchState.CURRENT), _english_profile(), None
    )
    ordinary_payload = (
        construct_hkex_english_request(ordinary, _SyntheticCodepointCounter())
        .record_results[0]
        .parts[0]
        .serving_payload_fingerprint
    )
    selected = _identity_existing(_FIRST_RECORD_ID, ordinary_payload, selected=True)
    older = _identity_existing(_FIRST_RECORD_ID, ordinary_payload, selected=False)
    other_current = _identity_existing(_SECOND_RECORD_ID, _OTHER_PAYLOAD_FINGERPRINT, selected=True)
    transitional = HKEXEnglishConstructionRequest(
        _english_tree(HKEXBranchState.TRANSITIONAL_CURRENT),
        _english_profile(),
        "Applies to synthetic pre-2026 issuers",
    )
    future = HKEXEnglishConstructionRequest(
        _english_tree(HKEXBranchState.FUTURE_FIXED_DATE), _english_profile(), None
    )
    return (
        (
            "HKREG-RECORD-IDENTITY-CASE-001",
            _identity_request(1, ordinary, change=HKEXRecordChange.INITIAL),
        ),
        (
            "HKREG-RECORD-IDENTITY-CASE-002",
            _identity_request(
                2,
                ordinary,
                change=HKEXRecordChange.SIX_FIELD_UNCHANGED,
                existing_records=(selected,),
                predecessor_ids=(_FIRST_RECORD_ID,),
            ),
        ),
        (
            "HKREG-RECORD-IDENTITY-CASE-003",
            _identity_request(
                3,
                ordinary,
                change=HKEXRecordChange.REINSTATEMENT,
                existing_records=(older, other_current),
                predecessor_ids=(_SECOND_RECORD_ID,),
            ),
        ),
        (
            "HKREG-RECORD-IDENTITY-CASE-004",
            _identity_request(
                4,
                transitional,
                change=HKEXRecordChange.APPLICABILITY_CONTEXT_CHANGED,
                existing_records=(
                    _identity_existing(_FIRST_RECORD_ID, _OTHER_PAYLOAD_FINGERPRINT, selected=True),
                ),
                predecessor_ids=(_FIRST_RECORD_ID,),
            ),
        ),
        (
            "HKREG-RECORD-IDENTITY-CASE-005",
            _identity_request(
                5,
                ordinary,
                change=HKEXRecordChange.AUTHORITY_NOTE_CHANGED,
                existing_records=(selected,),
                predecessor_ids=(_FIRST_RECORD_ID,),
            ),
        ),
        (
            "HKREG-RECORD-IDENTITY-CASE-006",
            _identity_request(
                6,
                ordinary,
                change=HKEXRecordChange.INITIAL,
                current_legal_support=False,
            ),
        ),
        (
            "HKREG-RECORD-IDENTITY-CASE-007",
            _identity_request(7, future, change=HKEXRecordChange.INITIAL),
        ),
        (
            "HKREG-RECORD-IDENTITY-CASE-008",
            _identity_request(
                8,
                ordinary,
                change=HKEXRecordChange.TRACEABILITY_ONLY,
                existing_records=(
                    _identity_existing(_FIRST_RECORD_ID, _OTHER_PAYLOAD_FINGERPRINT, selected=True),
                ),
                predecessor_ids=(_FIRST_RECORD_ID,),
            ),
        ),
    )


def build_record_identity_fixture() -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """Build eight frozen source-neutral ADR 0011/0073 request/result cases."""
    cases = _identity_cases()
    fixture = _json_object(
        {
            "fixture_id": "HKREG-RECORD-IDENTITY-FIX-001",
            "contract_version": HKEX_RECORD_IDENTITY_CONTRACT_VERSION,
            "synthetic_tokenizer": {
                "profile_id": _SyntheticCodepointCounter.profile_id,
                "profile_fingerprint": _SyntheticCodepointCounter.profile_fingerprint,
                "tokenizer_id": _SyntheticCodepointCounter.tokenizer_id,
                "admitted_for_real_records": False,
            },
            "cases": [
                {"case_id": case_id, "request": request.document()} for case_id, request in cases
            ],
        }
    )
    expected = _json_object(
        {
            "fixture_id": "HKREG-RECORD-IDENTITY-FIX-001",
            "contract_version": HKEX_RECORD_IDENTITY_CONTRACT_VERSION,
            "cases": [
                decide_hkex_record_identity(
                    hkex_record_identity_request_from_document(request.document()),
                    _SyntheticCodepointCounter(),
                ).document(case_id=case_id)
                for case_id, request in cases
            ],
        }
    )
    return fixture, expected


def build_record_identity_catalogue() -> dict[str, JsonValue]:
    """Bind the frozen source-neutral identity/traceability request/result pair."""
    fixture_path = "fixtures/deterministic/HKREG-RECORD-IDENTITY-FIX-001.json"
    expected_path = "expected/record-identity/HKREG-RECORD-IDENTITY-FIX-001.json"
    return {
        "catalogue_id": "asklegal.hk-regulatory.record-identity.fixtures",
        "version": "1.0.0",
        "status": "FROZEN_PARTIAL",
        "accepted_complete_real_source_universe": False,
        "synthetic_case_count": 8,
        "fixtures": [
            {
                "fixture_id": "HKREG-RECORD-IDENTITY-FIX-001",
                "path": fixture_path,
                "fixture_fingerprint": _fingerprint((PACKAGE_ROOT / fixture_path).read_bytes()),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint((PACKAGE_ROOT / expected_path).read_bytes()),
            }
        ],
    }


def _identity_schema_defs() -> dict[str, JsonValue]:
    return _json_object(
        {
            "fingerprint": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "issued_id": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9]{2,15}_[0-9a-f]{48}$",
            },
            "reference": {
                "type": "object",
                "additionalProperties": False,
                "required": ["ref_type", "ref_id", "fingerprint"],
                "properties": {
                    "ref_type": {
                        "enum": [
                            "ARTIFACT",
                            "DECISION",
                            "EVIDENCE",
                            "RULEBOOK",
                            "SOURCE_SNAPSHOT",
                        ]
                    },
                    "ref_id": {"$ref": "#/$defs/issued_id"},
                    "fingerprint": {"$ref": "#/$defs/fingerprint"},
                },
            },
        }
    )


def _prefix_english_schema_refs(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [_prefix_english_schema_refs(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str) and item.startswith("#/$defs/"):
                result[key] = item.replace("#/$defs/", "#/$defs/english_", 1)
            else:
                result[key] = _prefix_english_schema_refs(item)
        return result
    return value


def build_record_identity_request_schema() -> dict[str, JsonValue]:
    """Build the strict request schema with the exact English contract embedded."""
    construction = dict(
        _json_object(
            json.loads(
                (
                    PACKAGE_ROOT / "contracts/schemas/hkex-english-record-request.schema.json"
                ).read_text(encoding="utf-8")
            )
        )
    )
    for key in ("$schema", "$id", "title"):
        construction.pop(key, None)
    english_defs = _json_object(construction.pop("$defs"))
    prefixed_construction = _json_object(_prefix_english_schema_refs(construction))
    defs = _identity_schema_defs()
    for name in sorted(english_defs, key=str.encode):
        defs[f"english_{name}"] = _prefix_english_schema_refs(english_defs[name])
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-record-identity-request.schema.json",
            "title": "HKEX Search Record identity and traceability request",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "decision_id",
                "construction",
                "root_record_unit_id",
                "part_number",
                "legal_item_id",
                "official_version_ids",
                "legal_location_ids",
                "evidence_refs",
                "authority_note_decision_ref",
                "authority_note_supporting_refs",
                "current_legal_support",
                "existing_records",
                "predecessor_search_record_ids",
                "change",
                "decision_evidence_fingerprint",
                "legal_desk_actor",
            ],
            "$defs": defs,
            "properties": {
                "decision_id": {"type": "string", "minLength": 1},
                "construction": prefixed_construction,
                "root_record_unit_id": {"type": "string", "minLength": 1},
                "part_number": {"type": "integer", "minimum": 1},
                "legal_item_id": {
                    "type": "string",
                    "pattern": "^lit_[0-9a-f]{48}$",
                },
                "official_version_ids": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^ofv_[0-9a-f]{48}$",
                    },
                },
                "legal_location_ids": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^loc_[0-9a-f]{48}$",
                    },
                },
                "evidence_refs": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"$ref": "#/$defs/reference"},
                },
                "authority_note_decision_ref": {
                    "allOf": [
                        {"$ref": "#/$defs/reference"},
                        {
                            "type": "object",
                            "properties": {"ref_type": {"const": "DECISION"}},
                        },
                    ]
                },
                "authority_note_supporting_refs": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"$ref": "#/$defs/reference"},
                },
                "current_legal_support": {"type": "boolean"},
                "existing_records": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "search_record_id",
                            "serving_payload_fingerprint",
                            "scope_id",
                            "legal_item_id",
                            "currently_selected",
                        ],
                        "properties": {
                            "search_record_id": {
                                "type": "string",
                                "pattern": "^rec_[0-9a-f]{48}$",
                            },
                            "serving_payload_fingerprint": {"$ref": "#/$defs/fingerprint"},
                            "scope_id": {"type": "string", "minLength": 1},
                            "legal_item_id": {
                                "type": "string",
                                "pattern": "^lit_[0-9a-f]{48}$",
                            },
                            "currently_selected": {"type": "boolean"},
                        },
                    },
                },
                "predecessor_search_record_ids": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^rec_[0-9a-f]{48}$",
                    },
                },
                "change": {
                    "enum": [
                        "INITIAL",
                        "SIX_FIELD_UNCHANGED",
                        "TRACEABILITY_ONLY",
                        "PRIMARY_TEXT_CHANGED",
                        "APPLICABILITY_CONTEXT_CHANGED",
                        "GOVERNING_CONTEXT_CHANGED",
                        "REFERENCED_LOCATION_CHANGED",
                        "STRUCTURED_PROJECTION_CHANGED",
                        "PARTITION_CHANGED",
                        "AUTHORITY_NOTE_CHANGED",
                        "REINSTATEMENT",
                    ]
                },
                "decision_evidence_fingerprint": {"$ref": "#/$defs/fingerprint"},
                "legal_desk_actor": {"type": "string", "minLength": 1},
            },
        }
    )


def build_record_identity_result_schema() -> dict[str, JsonValue]:
    """Build the strict source-neutral identity decision result schema."""
    defs = _identity_schema_defs()
    defs.update(
        _json_object(
            {
                "source_binding": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "source_unit_id",
                        "role",
                        "source_range",
                        "content_fingerprint",
                    ],
                    "properties": {
                        "source_unit_id": {"type": "string", "minLength": 1},
                        "role": {"enum": ["PRIMARY", "CONTEXT_ONLY", "PRESENTATION_ONLY"]},
                        "source_range": {"type": "string", "minLength": 1},
                        "content_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    },
                },
                "referenced_location": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["locator", "official_heading"],
                    "properties": {
                        "locator": {"type": "string", "minLength": 1},
                        "official_heading": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "null"},
                            ]
                        },
                    },
                },
                "traceability_seed": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "serving_payload_fingerprint",
                        "serving_record_profile_id",
                        "tree_fingerprint",
                        "source_rule_id",
                        "source_artifact_fingerprints",
                        "legal_item_id",
                        "official_version_ids",
                        "legal_location_ids",
                        "primary_source_units",
                        "dependency_source_units",
                        "referenced_locations",
                        "evidence_refs",
                        "authority_note_fingerprint",
                        "authority_note_decision_ref",
                        "authority_note_supporting_refs",
                        "identity_decision_evidence_fingerprint",
                        "legal_desk_actor",
                        "root_record_unit_id",
                        "part_number",
                        "total_parts",
                    ],
                    "properties": {
                        "serving_payload_fingerprint": {"$ref": "#/$defs/fingerprint"},
                        "serving_record_profile_id": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "tree_fingerprint": {"$ref": "#/$defs/fingerprint"},
                        "source_rule_id": {"type": "string", "minLength": 1},
                        "source_artifact_fingerprints": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"$ref": "#/$defs/fingerprint"},
                        },
                        "legal_item_id": {
                            "type": "string",
                            "pattern": "^lit_[0-9a-f]{48}$",
                        },
                        "official_version_ids": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {
                                "type": "string",
                                "pattern": "^ofv_[0-9a-f]{48}$",
                            },
                        },
                        "legal_location_ids": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {
                                "type": "string",
                                "pattern": "^loc_[0-9a-f]{48}$",
                            },
                        },
                        "primary_source_units": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"$ref": "#/$defs/source_binding"},
                        },
                        "dependency_source_units": {
                            "type": "array",
                            "items": {"$ref": "#/$defs/source_binding"},
                        },
                        "referenced_locations": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"$ref": "#/$defs/referenced_location"},
                        },
                        "evidence_refs": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"$ref": "#/$defs/reference"},
                        },
                        "authority_note_fingerprint": {"$ref": "#/$defs/fingerprint"},
                        "authority_note_decision_ref": {
                            "allOf": [
                                {"$ref": "#/$defs/reference"},
                                {
                                    "type": "object",
                                    "properties": {"ref_type": {"const": "DECISION"}},
                                },
                            ]
                        },
                        "authority_note_supporting_refs": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"$ref": "#/$defs/reference"},
                        },
                        "identity_decision_evidence_fingerprint": {"$ref": "#/$defs/fingerprint"},
                        "legal_desk_actor": {"type": "string", "minLength": 1},
                        "root_record_unit_id": {"type": "string", "minLength": 1},
                        "part_number": {"type": "integer", "minimum": 1},
                        "total_parts": {"type": "integer", "minimum": 1},
                    },
                },
            }
        )
    )
    return _record_identity_result_schema_document(defs)


_CONFORMANCE_DESIGN_PATH = ROOT / "docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md"
_CONFORMANCE_GROUPS = (
    (
        "### A.",
        "### B.",
        "EVIDENCE_TO_DECISION",
        "SOURCE_FACT_AUTHORITY",
        "HKREG-DEC-SRC",
        "HKREG-COV-DSRC",
        62,
    ),
    (
        "### B.",
        "### C.",
        "EVIDENCE_TO_DECISION",
        "EFFECTIVE_STATE",
        "HKREG-DEC-STA",
        "HKREG-COV-DSTA",
        51,
    ),
    (
        "### C.",
        "### D.",
        "EVIDENCE_TO_DECISION",
        "RECORD_BOUNDARY",
        "HKREG-DEC-BND",
        "HKREG-COV-DBND",
        30,
    ),
    (
        "### D.",
        "### E.",
        "DECISION_TO_ARTIFACT",
        "CANONICAL_RENDERING",
        "HKREG-DET-RND",
        "HKREG-COV-DRND",
        35,
    ),
    (
        "### E.",
        "### F.",
        "DECISION_TO_ARTIFACT",
        "PARTITIONING",
        "HKREG-DET-PAR",
        "HKREG-COV-DPAR",
        24,
    ),
    (
        "### F.",
        "### G.",
        "DECISION_TO_ARTIFACT",
        "SOURCE_UNIT_COVERAGE",
        "HKREG-DET-COV",
        "HKREG-COV-DCOV",
        20,
    ),
    (
        "### G.",
        "### H.",
        "DECISION_TO_ARTIFACT",
        "RECORD_IDENTITY",
        "HKREG-DET-IDN",
        "HKREG-COV-DIDN",
        24,
    ),
    (
        "### H.",
        "## Initial exact catalogue arithmetic",
        "DECISION_TO_ARTIFACT",
        "PACKAGE_INTEGRITY",
        "HKREG-DET-PKG",
        "HKREG-COV-DPKG",
        38,
    ),
)
_CONFORMANCE_ROW_PATTERN = re.compile(
    r"^\| (?P<suffix>\d{3}) \| (?P<pair>.*?) \| "
    r"(?P<scenario>.*?) \| (?P<result>.*?) \|$"
)
_CONFORMANCE_PAIR_PATTERN = re.compile(r"P(?P<ordinal>\d{3}) (?P<role>[+-])")


class _ConformanceBuildError(RuntimeError):
    """The accepted ADR 0075 design rows no longer compile exactly."""


def _conformance_section(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    end_index = text.find(end, start_index + len(start))
    if start_index < 0 or end_index < 0:
        raise _ConformanceBuildError
    return text[start_index:end_index]


def _conformance_memberships(
    pair_cell: str,
    case_id: str,
    pair_members: dict[str, dict[str, str]],
) -> list[JsonValue]:
    matches = tuple(_CONFORMANCE_PAIR_PATTERN.finditer(pair_cell))
    rendered = "; ".join(match.group(0) for match in matches)
    if rendered != pair_cell:
        raise _ConformanceBuildError
    memberships: list[JsonValue] = []
    for match in matches:
        pair_id = f"HKREG-PAIR-{match.group('ordinal')}"
        role = "POSITIVE" if match.group("role") == "+" else "NEAR_MISS"
        roles = pair_members.setdefault(pair_id, {})
        if role in roles:
            raise _ConformanceBuildError
        roles[role] = case_id
        memberships.append({"pair_id": pair_id, "role": role})
    return memberships


def build_conformance_universe() -> dict[str, JsonValue]:
    """Compile the accepted 284-row design into one closed identity universe."""
    raw = _CONFORMANCE_DESIGN_PATH.read_bytes()
    text = raw.decode("utf-8")
    cases: list[JsonValue] = []
    checkpoint_counts: list[JsonValue] = []
    pair_members: dict[str, dict[str, str]] = {}
    for start, end, layer, checkpoint, case_ns, coverage_ns, count in _CONFORMANCE_GROUPS:
        rows = [
            match
            for line in _conformance_section(text, start, end).splitlines()
            if (match := _CONFORMANCE_ROW_PATTERN.fullmatch(line)) is not None
        ]
        if len(rows) != count:
            raise _ConformanceBuildError
        checkpoint_counts.append(
            {
                "checkpoint": checkpoint,
                "layer": layer,
                "case_namespace": case_ns,
                "coverage_namespace": coverage_ns,
                "direct_case_count": count,
            }
        )
        for ordinal, row in enumerate(rows, start=1):
            suffix = row.group("suffix")
            if suffix != f"{ordinal:03d}":
                raise _ConformanceBuildError
            case_id = f"{case_ns}-{suffix}"
            cases.append(
                {
                    "case_id": case_id,
                    "coverage_cell_id": f"{coverage_ns}-{suffix}",
                    "layer": layer,
                    "primary_checkpoint": checkpoint,
                    "synthetic_scenario": row.group("scenario"),
                    "exact_required_result": row.group("result"),
                    "pair_memberships": _conformance_memberships(
                        row.group("pair"), case_id, pair_members
                    ),
                }
            )
    pair_index: list[JsonValue] = []
    for ordinal in range(1, HKEX_CONFORMANCE_PAIR_COUNT + 1):
        pair_id = f"HKREG-PAIR-{ordinal:03d}"
        roles = pair_members.get(pair_id)
        if roles is None or set(roles) != {"POSITIVE", "NEAR_MISS"}:
            raise _ConformanceBuildError
        pair_index.append(
            {
                "pair_id": pair_id,
                "positive_case_id": roles["POSITIVE"],
                "near_miss_case_id": roles["NEAR_MISS"],
            }
        )
    document = _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.conformance-universe",
            "schema_version": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
            "catalogue_id": "hk-regulatory-initial",
            "catalogue_version": "1.0.0",
            "status": "FROZEN_EXECUTABLE_CASE_UNIVERSE",
            "design_source_path": ("docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md"),
            "design_source_fingerprint": _fingerprint(raw),
            "required_case_count": HKEX_CONFORMANCE_CASE_COUNT,
            "required_coverage_cell_count": HKEX_CONFORMANCE_COVERAGE_CELL_COUNT,
            "required_pair_count": HKEX_CONFORMANCE_PAIR_COUNT,
            "checkpoint_counts": checkpoint_counts,
            "cases": cases,
            "pair_index": pair_index,
            "case_packages_complete": True,
            "conformance_ready": False,
            "activation_authorized": False,
            "external_effects": "NONE",
        }
    )
    proof = validate_hkex_conformance_universe(document)
    if (
        proof.case_count != HKEX_CONFORMANCE_CASE_COUNT
        or proof.coverage_cell_count != HKEX_CONFORMANCE_COVERAGE_CELL_COUNT
        or proof.pair_count != HKEX_CONFORMANCE_PAIR_COUNT
    ):
        raise _ConformanceBuildError
    return document


def build_conformance_universe_schema() -> dict[str, JsonValue]:
    """Build the closed JSON schema for the frozen conformance universe."""
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-conformance-universe.schema.json",
            "title": "HKEX Regulatory initial conformance universe",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_id",
                "schema_version",
                "catalogue_id",
                "catalogue_version",
                "status",
                "design_source_path",
                "design_source_fingerprint",
                "required_case_count",
                "required_coverage_cell_count",
                "required_pair_count",
                "checkpoint_counts",
                "cases",
                "pair_index",
                "case_packages_complete",
                "conformance_ready",
                "activation_authorized",
                "external_effects",
            ],
            "$defs": {
                "nonempty": {"type": "string", "minLength": 1},
                "pair_membership": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["pair_id", "role"],
                    "properties": {
                        "pair_id": {
                            "type": "string",
                            "pattern": "^HKREG-PAIR-\\d{3}$",
                        },
                        "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
                    },
                },
            },
            "properties": {
                "schema_id": {"const": "asklegal.hk-regulatory.conformance-universe"},
                "schema_version": {"const": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION},
                "catalogue_id": {"const": "hk-regulatory-initial"},
                "catalogue_version": {"const": "1.0.0"},
                "status": {"const": "FROZEN_EXECUTABLE_CASE_UNIVERSE"},
                "design_source_path": {
                    "const": "docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md"
                },
                "design_source_fingerprint": {
                    "type": "string",
                    "pattern": "^sha256:[0-9a-f]{64}$",
                },
                "required_case_count": {"const": HKEX_CONFORMANCE_CASE_COUNT},
                "required_coverage_cell_count": {"const": HKEX_CONFORMANCE_COVERAGE_CELL_COUNT},
                "required_pair_count": {"const": HKEX_CONFORMANCE_PAIR_COUNT},
                "checkpoint_counts": {
                    "type": "array",
                    "minItems": 8,
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "checkpoint",
                            "layer",
                            "case_namespace",
                            "coverage_namespace",
                            "direct_case_count",
                        ],
                        "properties": {
                            "checkpoint": {
                                "enum": [
                                    "SOURCE_FACT_AUTHORITY",
                                    "EFFECTIVE_STATE",
                                    "RECORD_BOUNDARY",
                                    "CANONICAL_RENDERING",
                                    "PARTITIONING",
                                    "SOURCE_UNIT_COVERAGE",
                                    "RECORD_IDENTITY",
                                    "PACKAGE_INTEGRITY",
                                ]
                            },
                            "layer": {
                                "enum": [
                                    "EVIDENCE_TO_DECISION",
                                    "DECISION_TO_ARTIFACT",
                                ]
                            },
                            "case_namespace": {"$ref": "#/$defs/nonempty"},
                            "coverage_namespace": {"$ref": "#/$defs/nonempty"},
                            "direct_case_count": {"type": "integer", "minimum": 1},
                        },
                    },
                },
                "cases": {
                    "type": "array",
                    "minItems": HKEX_CONFORMANCE_CASE_COUNT,
                    "maxItems": HKEX_CONFORMANCE_CASE_COUNT,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "case_id",
                            "coverage_cell_id",
                            "layer",
                            "primary_checkpoint",
                            "synthetic_scenario",
                            "exact_required_result",
                            "pair_memberships",
                        ],
                        "properties": {
                            "case_id": {
                                "type": "string",
                                "pattern": (
                                    "^HKREG-(DEC-(SRC|STA|BND)|DET-(RND|PAR|COV|IDN|PKG))-\\d{3}$"
                                ),
                            },
                            "coverage_cell_id": {
                                "type": "string",
                                "pattern": (
                                    "^HKREG-COV-(DSRC|DSTA|DBND|DRND|DPAR|DCOV|DIDN|DPKG)-\\d{3}$"
                                ),
                            },
                            "layer": {
                                "enum": [
                                    "EVIDENCE_TO_DECISION",
                                    "DECISION_TO_ARTIFACT",
                                ]
                            },
                            "primary_checkpoint": {
                                "enum": [
                                    "SOURCE_FACT_AUTHORITY",
                                    "EFFECTIVE_STATE",
                                    "RECORD_BOUNDARY",
                                    "CANONICAL_RENDERING",
                                    "PARTITIONING",
                                    "SOURCE_UNIT_COVERAGE",
                                    "RECORD_IDENTITY",
                                    "PACKAGE_INTEGRITY",
                                ]
                            },
                            "synthetic_scenario": {"$ref": "#/$defs/nonempty"},
                            "exact_required_result": {"$ref": "#/$defs/nonempty"},
                            "pair_memberships": {
                                "type": "array",
                                "uniqueItems": True,
                                "items": {"$ref": "#/$defs/pair_membership"},
                            },
                        },
                    },
                },
                "pair_index": {
                    "type": "array",
                    "minItems": HKEX_CONFORMANCE_PAIR_COUNT,
                    "maxItems": HKEX_CONFORMANCE_PAIR_COUNT,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "pair_id",
                            "positive_case_id",
                            "near_miss_case_id",
                        ],
                        "properties": {
                            "pair_id": {
                                "type": "string",
                                "pattern": "^HKREG-PAIR-\\d{3}$",
                            },
                            "positive_case_id": {"$ref": "#/$defs/nonempty"},
                            "near_miss_case_id": {"$ref": "#/$defs/nonempty"},
                        },
                    },
                },
                "case_packages_complete": {"const": True},
                "conformance_ready": {"const": False},
                "activation_authorized": {"const": False},
                "external_effects": {"const": "NONE"},
            },
        }
    )


def build_conformance_universe_rule() -> dict[str, JsonValue]:
    """Declare the complete executable case universe without admission authority."""
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory-conformance-universe-rule",
            "schema_version": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
            "rule_id": "HKREG-CONFORMANCE-UNIVERSE-001",
            "status": "SOURCE_NEUTRAL_CONFORMANCE_UNIVERSE",
            "accepted_adrs": ["0074", "0075"],
            "input_schema": "contracts/schemas/hkex-conformance-universe.schema.json",
            "catalogue": "catalogues/conformance-universe.json",
            "required_case_count": HKEX_CONFORMANCE_CASE_COUNT,
            "required_primary_coverage_cell_count": HKEX_CONFORMANCE_COVERAGE_CELL_COUNT,
            "required_high_risk_pair_count": HKEX_CONFORMANCE_PAIR_COUNT,
            "evidence_to_decision_case_count": 143,
            "decision_to_artifact_case_count": 141,
            "directory_discovery_forbidden": True,
            "case_combination_or_omission_forbidden": True,
            "executable_case_packages_complete": True,
            "conformance_ready": False,
            "activation_authority": False,
            "external_effects": "NONE",
        }
    )


@dataclass(frozen=True, slots=True)
class _SourceExpectedDetails:
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


@dataclass(frozen=True, slots=True)
class _SourceCaseSpec:
    scope: HKEXSourceAssertionScope
    role: HKEXSourceEvidenceRole
    facts: dict[str, JsonValue]
    expected: HKEXSourceDecision
    state: HKEXSourceEvidenceState = HKEXSourceEvidenceState.AVAILABLE


def _source_expected(
    outcome: HKEXSourceDecisionOutcome,
    reason: HKEXSourceDecisionReason,
    details: _SourceExpectedDetails | None = None,
) -> HKEXSourceDecision:
    resolved = _SourceExpectedDetails() if details is None else details
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


def _source_facts(**overrides: object) -> dict[str, JsonValue]:
    values: dict[str, object] = {
        "source_id": None,
        "claimed_fact_codes": [],
        "source_artifact_final": True,
        "due_source_ids": [],
        "complete_source_ids": [],
        "fresh_source_ids": [],
        "reconciled_source_ids": [],
        "single_view_completeness_inference": False,
        "optional_presentation_conflict": False,
        "source_contract_material_change": False,
        "final_update_present": False,
        "matching_current_product": False,
        "standing_approval_framework": False,
        "proposal_or_pending_document": False,
        "direct_approval_required": False,
        "direct_approval_present": False,
        "predecessor_exact_match": False,
        "no_alert_only": False,
        "observation_gap": HKEXObservationGap.NONE.value,
        "historical_investigation_only": False,
        "object_class": HKEXRegulatoryObjectClass.UNKNOWN.value,
        "express_inclusion": False,
        "express_exclusion": False,
        "assigned_evidence_only_use": False,
        "inclusion_evidence_missing": False,
        "inclusion_evidence_unreadable": False,
        "inclusion_evidence_conflicting": False,
        "supported_owner_scopes": [],
        "assigned_owner_scopes": [],
        "assigned_instance_count": 0,
        "artifact_component_count": 0,
        "artifact_shared_between_boards": False,
        "identical_wording_across_boards": False,
        "ownership_conflict": False,
        "official_parent_supported": True,
        "website_suggested_scope": None,
        "required_english_complete": True,
        "chinese_available": False,
        "chinese_state": HKEXChineseEvidenceState.NONE.value,
        "prohibited_source_repair": False,
        "optional_chinese_bounded_use": False,
    }
    if not set(overrides).issubset(values):
        raise _ConformanceBuildError
    values.update(overrides)
    return _json_object(values)


def _fact_authority_spec(
    source_id: str,
    role: HKEXSourceEvidenceRole,
    fact_codes: tuple[str, ...],
    *,
    accepted: bool,
) -> _SourceCaseSpec:
    codes = tuple(sorted(fact_codes))
    expected = _source_expected(
        HKEXSourceDecisionOutcome.PASS if accepted else HKEXSourceDecisionOutcome.BLOCK,
        (
            HKEXSourceDecisionReason.ASSIGNED_FACTS_ACCEPTED
            if accepted
            else HKEXSourceDecisionReason.OUT_OF_ROLE_FACT_REJECTED
        ),
        _SourceExpectedDetails(
            accepted=codes if accepted else (),
            rejected=() if accepted else codes,
        ),
    )
    return _SourceCaseSpec(
        scope=HKEXSourceAssertionScope.FACT_AUTHORITY,
        role=role,
        facts=_source_facts(source_id=source_id, claimed_fact_codes=list(codes)),
        expected=expected,
    )


def _source_authority_specs() -> tuple[_SourceCaseSpec, ...]:
    return (
        _fact_authority_spec(
            HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
            HKEXSourceEvidenceRole.RULEBOOK_CATALOGUE,
            ("TOP_LEVEL_PRODUCT_FAMILIES", "BOARD_ASSOCIATION", "CURRENT_LOCATORS"),
            accepted=True,
        ),
        _fact_authority_spec(
            HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
            HKEXSourceEvidenceRole.RULEBOOK_CATALOGUE,
            ("INDIVIDUAL_RULE_WORDING", "EFFECTIVE_STATE", "COMPLETE_COMPONENT_INVENTORY"),
            accepted=False,
        ),
        _fact_authority_spec(
            HKEX_CONSOLIDATED_RULEBOOKS_SOURCE_ID,
            HKEXSourceEvidenceRole.CONSOLIDATED_RULEBOOK,
            ("PREVAILING_ENGLISH_WORDING", "CONTAINED_OFFICIAL_STRUCTURE"),
            accepted=True,
        ),
        _fact_authority_spec(
            HKEX_CONSOLIDATED_RULEBOOKS_SOURCE_ID,
            HKEXSourceEvidenceRole.CONSOLIDATED_RULEBOOK,
            ("FORM_INVENTORY", "FEES_INVENTORY", "AMENDMENT_CAUSE", "EXTERNAL_TRIGGER_OCCURRENCE"),
            accepted=False,
        ),
        _fact_authority_spec(
            HKEX_REGULATORY_FORMS_SOURCE_ID,
            HKEXSourceEvidenceRole.REGULATORY_FORMS,
            ("FORM_INVENTORY", "FORM_MEMBERSHIP", "FORM_BOARD", "FORM_ENGLISH_CONTENT"),
            accepted=True,
        ),
        _fact_authority_spec(
            HKEX_REGULATORY_FORMS_SOURCE_ID,
            HKEXSourceEvidenceRole.REGULATORY_FORMS,
            (
                "ORDINARY_RULE_WORDING",
                "FEES_INVENTORY",
                "AMENDMENT_CAUSE",
                "EXTERNAL_TRIGGER_OCCURRENCE",
            ),
            accepted=False,
        ),
        _fact_authority_spec(
            HKEX_FEES_RULES_SOURCE_ID,
            HKEXSourceEvidenceRole.FEES_RULES,
            ("FEES_INVENTORY", "FEES_MEMBERSHIP", "FEES_BOARD", "FEES_ENGLISH_CONTENT"),
            accepted=True,
        ),
        _fact_authority_spec(
            HKEX_FEES_RULES_SOURCE_ID,
            HKEXSourceEvidenceRole.FEES_RULES,
            (
                "ORDINARY_RULE_WORDING",
                "FORM_INVENTORY",
                "AMENDMENT_CAUSE",
                "EXTERNAL_TRIGGER_OCCURRENCE",
            ),
            accepted=False,
        ),
        _fact_authority_spec(
            HKEX_RULE_UPDATES_SOURCE_ID,
            HKEXSourceEvidenceRole.FINAL_RULE_UPDATE,
            (
                "CHANGED_WORDS",
                "MAPPINGS",
                "STATED_DATES",
                "STATED_CONDITIONS",
                "TRANSITIONS",
                "WITHDRAWALS",
            ),
            accepted=True,
        ),
        _fact_authority_spec(
            HKEX_RULE_UPDATES_SOURCE_ID,
            HKEXSourceEvidenceRole.FINAL_RULE_UPDATE,
            ("EXTERNAL_TRIGGER_OCCURRENCE", "PRESENT_COMPILED_TEXT", "PRESENT_EFFECT"),
            accepted=False,
        ),
    )


def _all_source_lists() -> dict[str, object]:
    source_ids: object = list(HKEX_REGULATORY_SOURCE_IDS)
    return {
        "due_source_ids": source_ids,
        "complete_source_ids": list(HKEX_REGULATORY_SOURCE_IDS),
        "fresh_source_ids": list(HKEX_REGULATORY_SOURCE_IDS),
        "reconciled_source_ids": list(HKEX_REGULATORY_SOURCE_IDS),
    }


def _source_control_specs() -> tuple[_SourceCaseSpec, ...]:
    all_sources = _all_source_lists()
    only_catalogue = [HKEX_RULEBOOK_CATALOGUE_SOURCE_ID]
    stale_fresh = [
        source_id
        for source_id in HKEX_REGULATORY_SOURCE_IDS
        if source_id != HKEX_RULE_UPDATES_SOURCE_ID
    ]
    both_scopes = (HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID)
    return (
        _SourceCaseSpec(
            HKEXSourceAssertionScope.SOURCE_UNION,
            HKEXSourceEvidenceRole.COMPLETE_SOURCE_UNION,
            _source_facts(**all_sources),
            _source_expected(
                HKEXSourceDecisionOutcome.PASS,
                HKEXSourceDecisionReason.COMPLETE_UNION_ACCEPTED,
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.SOURCE_UNION,
            HKEXSourceEvidenceRole.COMPLETE_SOURCE_UNION,
            _source_facts(
                due_source_ids=list(HKEX_REGULATORY_SOURCE_IDS),
                complete_source_ids=only_catalogue,
                fresh_source_ids=only_catalogue,
                reconciled_source_ids=only_catalogue,
                single_view_completeness_inference=True,
            ),
            _source_expected(
                HKEXSourceDecisionOutcome.BLOCK,
                HKEXSourceDecisionReason.UNIVERSE_INCOMPLETE,
                _SourceExpectedDetails(blocked=both_scopes),
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.SOURCE_CONTRACT,
            HKEXSourceEvidenceRole.OPTIONAL_PRESENTATION,
            _source_facts(optional_presentation_conflict=True),
            _source_expected(
                HKEXSourceDecisionOutcome.PASS,
                HKEXSourceDecisionReason.PRESENTATION_DISCREPANCY_PRESERVED,
                _SourceExpectedDetails(permitted=both_scopes),
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.SOURCE_CONTRACT,
            HKEXSourceEvidenceRole.SOURCE_CONTRACT,
            _source_facts(source_contract_material_change=True),
            _source_expected(
                HKEXSourceDecisionOutcome.BLOCK,
                HKEXSourceDecisionReason.SOURCE_CONTRACT_REVIEW_REQUIRED,
                _SourceExpectedDetails(blocked=both_scopes, contract_review=True),
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.APPROVAL,
            HKEXSourceEvidenceRole.APPROVAL_EVIDENCE,
            _source_facts(
                final_update_present=True,
                matching_current_product=True,
                standing_approval_framework=True,
            ),
            _source_expected(
                HKEXSourceDecisionOutcome.PASS,
                HKEXSourceDecisionReason.APPROVAL_SATISFIED_BY_FINAL_PUBLICATION,
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.APPROVAL,
            HKEXSourceEvidenceRole.APPROVAL_EVIDENCE,
            _source_facts(
                standing_approval_framework=True,
                proposal_or_pending_document=True,
            ),
            _source_expected(
                HKEXSourceDecisionOutcome.BLOCK,
                HKEXSourceDecisionReason.APPROVAL_NOT_PROVED,
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.APPROVAL,
            HKEXSourceEvidenceRole.APPROVAL_EVIDENCE,
            _source_facts(direct_approval_required=True),
            _source_expected(
                HKEXSourceDecisionOutcome.BLOCK,
                HKEXSourceDecisionReason.DIRECT_APPROVAL_EVIDENCE_MISSING,
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.NO_CHANGE,
            HKEXSourceEvidenceRole.SOURCE_OBSERVATIONS,
            _source_facts(**all_sources, predecessor_exact_match=True),
            _source_expected(
                HKEXSourceDecisionOutcome.PASS,
                HKEXSourceDecisionReason.SUPPORTED_NO_CHANGE,
                _SourceExpectedDetails(no_change=True),
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.NO_CHANGE,
            HKEXSourceEvidenceRole.SOURCE_OBSERVATIONS,
            _source_facts(
                **{**all_sources, "fresh_source_ids": stale_fresh},
                predecessor_exact_match=True,
                no_alert_only=True,
                observation_gap=HKEXObservationGap.BOTH_SHARED_UNBOUNDED.value,
            ),
            _source_expected(
                HKEXSourceDecisionOutcome.BLOCK,
                HKEXSourceDecisionReason.NO_CHANGE_UNPROVED,
                _SourceExpectedDetails(blocked=both_scopes),
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.OUTAGE_SCOPE,
            HKEXSourceEvidenceRole.SOURCE_OBSERVATIONS,
            _source_facts(observation_gap=HKEXObservationGap.MAIN_ONLY.value),
            _source_expected(
                HKEXSourceDecisionOutcome.BLOCK,
                HKEXSourceDecisionReason.BOARD_SPECIFIC_GAP,
                _SourceExpectedDetails(
                    blocked=(HKEX_MAIN_SCOPE_ID,),
                    permitted=(HKEX_GEM_SCOPE_ID,),
                ),
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.OUTAGE_SCOPE,
            HKEXSourceEvidenceRole.SOURCE_OBSERVATIONS,
            _source_facts(observation_gap=HKEXObservationGap.BOTH_SHARED_UNBOUNDED.value),
            _source_expected(
                HKEXSourceDecisionOutcome.BLOCK,
                HKEXSourceDecisionReason.SHARED_UNBOUNDED_GAP,
                _SourceExpectedDetails(blocked=both_scopes),
            ),
        ),
        _SourceCaseSpec(
            HKEXSourceAssertionScope.HISTORICAL_INVESTIGATION,
            HKEXSourceEvidenceRole.HISTORICAL_UPDATE,
            _source_facts(
                observation_gap=HKEXObservationGap.BOUNDED_HISTORICAL.value,
                historical_investigation_only=True,
            ),
            _source_expected(
                HKEXSourceDecisionOutcome.BLOCK,
                HKEXSourceDecisionReason.BOUNDED_HISTORICAL_GAP,
                _SourceExpectedDetails(permitted=both_scopes),
            ),
        ),
    )


def _membership_spec(
    object_class: HKEXRegulatoryObjectClass,
    membership: HKEXMembership,
    *,
    conflict: bool = False,
    missing: bool = False,
) -> _SourceCaseSpec:
    included = membership is HKEXMembership.RULE_COMPONENT
    excluded = membership is HKEXMembership.EXCLUDED_NON_RULE
    evidence_only = membership is HKEXMembership.EVIDENCE_ONLY
    unresolved = membership is HKEXMembership.UNRESOLVED_MEMBERSHIP
    facts = _source_facts(
        object_class=object_class.value,
        express_inclusion=included,
        express_exclusion=excluded,
        assigned_evidence_only_use=evidence_only,
        inclusion_evidence_missing=missing,
        inclusion_evidence_conflicting=conflict,
        supported_owner_scopes=[HKEX_MAIN_SCOPE_ID] if included else [],
        artifact_component_count=1 if included else 0,
    )
    reason = {
        HKEXMembership.RULE_COMPONENT: HKEXSourceDecisionReason.RULE_COMPONENT_CLASSIFIED,
        HKEXMembership.EXCLUDED_NON_RULE: (HKEXSourceDecisionReason.EXCLUDED_NON_RULE_CLASSIFIED),
        HKEXMembership.EVIDENCE_ONLY: HKEXSourceDecisionReason.EVIDENCE_ONLY_CLASSIFIED,
        HKEXMembership.UNRESOLVED_MEMBERSHIP: (HKEXSourceDecisionReason.MEMBERSHIP_UNRESOLVED),
    }[membership]
    expected = _source_expected(
        HKEXSourceDecisionOutcome.QUARANTINE if unresolved else HKEXSourceDecisionOutcome.PASS,
        reason,
        _SourceExpectedDetails(
            membership=membership,
            owners=(HKEX_MAIN_SCOPE_ID,) if included else (),
            instances=1 if included else 0,
        ),
    )
    return _SourceCaseSpec(
        HKEXSourceAssertionScope.MEMBERSHIP,
        HKEXSourceEvidenceRole.MEMBERSHIP_EVIDENCE,
        facts,
        expected,
        (
            HKEXSourceEvidenceState.INTENTIONALLY_ABSENT
            if missing
            else HKEXSourceEvidenceState.AVAILABLE
        ),
    )


def _source_membership_specs() -> tuple[_SourceCaseSpec, ...]:
    included = (
        HKEXRegulatoryObjectClass.CHAPTER,
        HKEXRegulatoryObjectClass.ORDINARY_RULE,
        HKEXRegulatoryObjectClass.INCORPORATED_NOTE,
        HKEXRegulatoryObjectClass.APPENDIX,
        HKEXRegulatoryObjectClass.PRACTICE_NOTE,
        HKEXRegulatoryObjectClass.REGULATORY_FORM,
        HKEXRegulatoryObjectClass.FEES_RULE,
        HKEXRegulatoryObjectClass.OTHER_COMPONENT,
    )
    excluded = (
        HKEXRegulatoryObjectClass.GUIDANCE,
        HKEXRegulatoryObjectClass.FAQ,
        HKEXRegulatoryObjectClass.CONSULTATION,
        HKEXRegulatoryObjectClass.LISTING_DECISION,
        HKEXRegulatoryObjectClass.ANNOUNCEMENT,
        HKEXRegulatoryObjectClass.TEMPLATE,
    )
    evidence_only = (
        HKEXRegulatoryObjectClass.UPDATE_EVIDENCE,
        HKEXRegulatoryObjectClass.APPROVAL_EVIDENCE,
        HKEXRegulatoryObjectClass.TRIGGER_EVIDENCE,
        HKEXRegulatoryObjectClass.SOURCE_BASIS_EVIDENCE,
    )
    return (
        *(_membership_spec(item, HKEXMembership.RULE_COMPONENT) for item in included),
        *(_membership_spec(item, HKEXMembership.EXCLUDED_NON_RULE) for item in excluded),
        *(_membership_spec(item, HKEXMembership.EVIDENCE_ONLY) for item in evidence_only),
        _membership_spec(
            HKEXRegulatoryObjectClass.UNKNOWN,
            HKEXMembership.UNRESOLVED_MEMBERSHIP,
        ),
        _membership_spec(
            HKEXRegulatoryObjectClass.OTHER_COMPONENT,
            HKEXMembership.UNRESOLVED_MEMBERSHIP,
            conflict=True,
        ),
        _membership_spec(
            HKEXRegulatoryObjectClass.OTHER_COMPONENT,
            HKEXMembership.UNRESOLVED_MEMBERSHIP,
            missing=True,
        ),
    )


def _ownership_spec(
    facts: dict[str, JsonValue],
    outcome: HKEXSourceDecisionOutcome,
    reason: HKEXSourceDecisionReason,
    details: _SourceExpectedDetails | None = None,
) -> _SourceCaseSpec:
    return _SourceCaseSpec(
        HKEXSourceAssertionScope.OWNERSHIP,
        HKEXSourceEvidenceRole.OWNERSHIP_EVIDENCE,
        facts,
        _source_expected(outcome, reason, details),
    )


def _source_ownership_specs() -> tuple[_SourceCaseSpec, ...]:
    main = [HKEX_MAIN_SCOPE_ID]
    gem = [HKEX_GEM_SCOPE_ID]
    both = [HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]
    return (
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=main,
                assigned_owner_scopes=main,
                assigned_instance_count=1,
                artifact_component_count=1,
            ),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.OWNER_ASSIGNED,
            _SourceExpectedDetails(owners=(HKEX_MAIN_SCOPE_ID,), instances=1),
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=gem,
                assigned_owner_scopes=gem,
                assigned_instance_count=1,
                artifact_component_count=1,
            ),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.OWNER_ASSIGNED,
            _SourceExpectedDetails(owners=(HKEX_GEM_SCOPE_ID,), instances=1),
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=both,
                assigned_owner_scopes=both,
                assigned_instance_count=2,
                artifact_component_count=1,
                artifact_shared_between_boards=True,
            ),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.SHARED_ARTIFACT_INSTANCES_ASSIGNED,
            _SourceExpectedDetails(
                owners=(HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID),
                instances=2,
            ),
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=main,
                assigned_owner_scopes=main,
                assigned_instance_count=3,
                artifact_component_count=3,
            ),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.MULTI_COMPONENTS_ACCOUNTED,
            _SourceExpectedDetails(owners=(HKEX_MAIN_SCOPE_ID,), instances=3),
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=both,
                assigned_owner_scopes=both,
                assigned_instance_count=2,
                artifact_component_count=2,
                identical_wording_across_boards=True,
            ),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.SEPARATE_IDENTITIES_REQUIRED,
            _SourceExpectedDetails(
                owners=(HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID),
                instances=2,
            ),
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=main,
                assigned_owner_scopes=main,
                assigned_instance_count=1,
                artifact_component_count=1,
                website_suggested_scope=HKEX_GEM_SCOPE_ID,
            ),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.PLACEMENT_DISCREPANCY_PRESERVED,
            _SourceExpectedDetails(owners=(HKEX_MAIN_SCOPE_ID,), instances=1),
        ),
        _ownership_spec(
            _source_facts(),
            HKEXSourceDecisionOutcome.QUARANTINE,
            HKEXSourceDecisionReason.OWNER_MISSING,
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=both,
                ownership_conflict=True,
            ),
            HKEXSourceDecisionOutcome.QUARANTINE,
            HKEXSourceDecisionReason.OWNER_CONFLICT,
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=both,
                assigned_owner_scopes=both,
                assigned_instance_count=1,
                artifact_component_count=1,
            ),
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.DOUBLE_OWNED_INSTANCE,
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=main,
                assigned_owner_scopes=main,
                assigned_instance_count=1,
                artifact_component_count=1,
                official_parent_supported=False,
            ),
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.ORPHAN_COMPONENT,
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=main,
                assigned_owner_scopes=main,
                assigned_instance_count=2,
                artifact_component_count=1,
            ),
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.DUPLICATE_COMPONENT,
        ),
        _ownership_spec(
            _source_facts(
                supported_owner_scopes=main,
                assigned_owner_scopes=gem,
                assigned_instance_count=1,
                artifact_component_count=1,
            ),
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.CRITICAL_WRONG_BOARD,
        ),
    )


def _language_spec(
    facts: dict[str, JsonValue],
    outcome: HKEXSourceDecisionOutcome,
    reason: HKEXSourceDecisionReason,
    details: _SourceExpectedDetails | None = None,
    *,
    role: HKEXSourceEvidenceRole = HKEXSourceEvidenceRole.ENGLISH_EVIDENCE,
) -> _SourceCaseSpec:
    return _SourceCaseSpec(
        HKEXSourceAssertionScope.LANGUAGE,
        role,
        facts,
        _source_expected(outcome, reason, details),
    )


def _source_language_specs() -> tuple[_SourceCaseSpec, ...]:
    return (
        _language_spec(
            _source_facts(required_english_complete=True),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.ENGLISH_COMPLETE_CHINESE_OPTIONAL,
        ),
        _language_spec(
            _source_facts(required_english_complete=False, chinese_available=True),
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.REQUIRED_ENGLISH_MISSING,
        ),
        _language_spec(
            _source_facts(
                chinese_available=True,
                chinese_state=HKEXChineseEvidenceState.HARMLESS_DIFFERENCE.value,
            ),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.CHINESE_DISCREPANCY_NONBLOCKING,
            role=HKEXSourceEvidenceRole.OPTIONAL_CHINESE,
        ),
        _language_spec(
            _source_facts(
                chinese_available=True,
                chinese_state=HKEXChineseEvidenceState.ENGLISH_DEFECT_SIGNAL.value,
            ),
            HKEXSourceDecisionOutcome.QUARANTINE,
            HKEXSourceDecisionReason.CHINESE_ENGLISH_DEFECT_SIGNAL,
            _SourceExpectedDetails(english_investigation=True),
            role=HKEXSourceEvidenceRole.OPTIONAL_CHINESE,
        ),
        _language_spec(
            _source_facts(
                chinese_available=True,
                chinese_state=HKEXChineseEvidenceState.CHINESE_ONLY_CHANGE.value,
            ),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.CHINESE_ONLY_NO_SERVING_CHANGE,
            role=HKEXSourceEvidenceRole.OPTIONAL_CHINESE,
        ),
        _language_spec(
            _source_facts(
                required_english_complete=False,
                chinese_available=True,
                prohibited_source_repair=True,
            ),
            HKEXSourceDecisionOutcome.BLOCK,
            HKEXSourceDecisionReason.PROHIBITED_SOURCE_REPAIR,
            role=HKEXSourceEvidenceRole.OPTIONAL_CHINESE,
        ),
        _language_spec(
            _source_facts(
                chinese_available=True,
                optional_chinese_bounded_use=True,
            ),
            HKEXSourceDecisionOutcome.PASS,
            HKEXSourceDecisionReason.OPTIONAL_CHINESE_TRACEABILITY_ONLY,
            role=HKEXSourceEvidenceRole.OPTIONAL_CHINESE,
        ),
    )


def _source_case_specs() -> tuple[_SourceCaseSpec, ...]:
    specs = (
        *_source_authority_specs(),
        *_source_control_specs(),
        *_source_membership_specs(),
        *_source_ownership_specs(),
        *_source_language_specs(),
    )
    if len(specs) != HKEX_SOURCE_DECISION_CASE_COUNT:
        raise _ConformanceBuildError
    return specs


def _single_pair_membership(universe_case: dict[str, JsonValue]) -> JsonValue:
    memberships = _json_array(universe_case["pair_memberships"])
    if not memberships:
        return None
    if len(memberships) != 1:
        raise _ConformanceBuildError
    return deepcopy(_json_object(memberships[0]))


def _source_case_contract_bindings(
    *,
    universe_fingerprint: str,
) -> tuple[list[JsonValue], str]:
    seed = _json_object(
        {
            "contract_id": "asklegal.hk-regulatory.source-decision-case",
            "contract_version": HKEX_SOURCE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_SOURCE_DECISION_RULE_ID,
        }
    )
    contract_fingerprint = _fingerprint(rfc8785.dumps(seed))
    bindings: list[JsonValue] = [
        {
            "contract_id": "asklegal.hk-regulatory.conformance-universe",
            "version": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
            "fingerprint": universe_fingerprint,
        },
        {
            "contract_id": "asklegal.hk-regulatory.source-decision-case",
            "version": HKEX_SOURCE_DECISION_CONTRACT_VERSION,
            "fingerprint": contract_fingerprint,
        },
    ]
    return bindings, contract_fingerprint


def build_source_decision_cases() -> tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...]:
    """Build all 62 direct evidence-to-decision cases and frozen reports."""
    universe = build_conformance_universe()
    universe_cases = tuple(
        _json_object(item)
        for item in _json_array(universe["cases"])[:HKEX_SOURCE_DECISION_CASE_COUNT]
    )
    specs = _source_case_specs()
    universe_fingerprint = _fingerprint(rfc8785.dumps(universe))
    bindings, _ = _source_case_contract_bindings(universe_fingerprint=universe_fingerprint)
    results: list[tuple[dict[str, JsonValue], dict[str, JsonValue]]] = []
    for universe_case, spec in zip(universe_cases, specs, strict=True):
        case_id = str(universe_case["case_id"])
        facts = deepcopy(spec.facts)
        evidence_packet: dict[str, JsonValue] = {
            "slot_id": "source-evidence",
            "state": spec.state.value,
            "path": f"input/{case_id}-source-evidence.json",
            "role": spec.role.value,
            "media_type": "application/json",
            "content_fingerprint": _fingerprint(rfc8785.dumps(facts)),
        }
        unresolved: list[JsonValue] = []
        if spec.expected.outcome is not HKEXSourceDecisionOutcome.PASS:
            unresolved = [spec.expected.reason.value]
        critical: list[JsonValue] = []
        if case_id in {
            "HKREG-DEC-SRC-052",
            "HKREG-DEC-SRC-055",
            "HKREG-DEC-SRC-057",
            "HKREG-DEC-SRC-059",
            "HKREG-DEC-SRC-061",
        }:
            critical = [spec.expected.reason.value]
        fixture = _json_object(
            {
                "schema_id": "asklegal.hk-regulatory.source-decision-case",
                "schema_version": HKEX_SOURCE_DECISION_CONTRACT_VERSION,
                "package_contract_version": "1.0.0",
                "case_id": case_id,
                "suite_layer": "EVIDENCE_TO_DECISION",
                "primary_checkpoint": "SOURCE_FACT_AUTHORITY",
                "frozen": True,
                "synthetic_evidence_class": "SYNTHETIC_NO_REAL_AUTHORITY",
                "contract_bindings": deepcopy(bindings),
                "synthetic_cutoff": "2026-08-24T00:00:00Z",
                "scope_id": "HKEX_CROSS_BOARD",
                "prior_state": "SYNTHETIC_ACCEPTED_PREDECESSOR",
                "primary_coverage_cell_ids": [universe_case["coverage_cell_id"]],
                "secondary_coverage_cell_ids": [],
                "pair_membership": _single_pair_membership(universe_case),
                "declared_input_inventory": ["source-evidence"],
                "declared_reference_inventory": [
                    "asklegal.hk-regulatory.conformance-universe",
                    "asklegal.hk-regulatory.source-decision-case",
                ],
                "declared_expected_inventory": ["SOURCE_DECISION_REPORT"],
                "assertion_scope": spec.scope.value,
                "required_result_dimensions": [
                    "AUTHORITY",
                    "MEMBERSHIP",
                    "OWNERSHIP",
                    "PROCESSING",
                    "SOURCE_FACTS",
                ],
                "evidence_packet_fields": sorted(facts),
                "supporting_evidence_ranges": [f"input/{case_id}-source-evidence.json#facts"],
                "rule_trace": [HKEX_SOURCE_DECISION_RULE_ID],
                "established_facts": ["SYNTHETIC_FACT_PACKET_DECLARED"],
                "unresolved_facts": unresolved,
                "permitted_equivalent_results": [],
                "critical_error_codes": critical,
                "package_fingerprint": universe_fingerprint,
                "title": universe_case["synthetic_scenario"],
                "purpose": universe_case["exact_required_result"],
                "expected_decision": checked_json_value(spec.expected.document(case_id=case_id)),
                "evidence_packet": evidence_packet,
                "facts": facts,
                "case_fingerprint": "PENDING",
            }
        )
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        parsed = hkex_source_decision_case_from_document(fixture)
        report = _json_object(run_hkex_source_case(parsed).document())
        if report["conformance_status"] != "PASS":
            failure = f"{parsed.case_id}:{spec.expected.reason.value}"
            raise _ConformanceBuildError(failure)
        results.append((_json_object(fixture), report))
    if len(results) != HKEX_SOURCE_DECISION_CASE_COUNT:
        raise _ConformanceBuildError
    return tuple(results)


def build_source_decision_catalogue(
    cases: tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...],
) -> dict[str, JsonValue]:
    """Bind all 62 exact source-decision case packets and reports."""
    entries: list[JsonValue] = []
    for fixture, report in cases:
        case_id = str(fixture["case_id"])
        fixture_path = f"fixtures/conformance/source-decision/{case_id}.json"
        expected_path = f"expected/conformance/source-decision/{case_id}.json"
        expected_decision = _json_object(fixture["expected_decision"])
        entries.append(
            {
                "case_id": case_id,
                "primary_coverage_cell_id": _json_array(fixture["primary_coverage_cell_ids"])[0],
                "pair_membership": fixture["pair_membership"],
                "assertion_scope": fixture["assertion_scope"],
                "expected_outcome": expected_decision["outcome"],
                "expected_reason": expected_decision["reason"],
                "fixture_path": fixture_path,
                "fixture_fingerprint": _fingerprint(
                    (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode()
                ),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint(
                    (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
                ),
            }
        )
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.source-decision-catalogue",
            "schema_version": HKEX_SOURCE_DECISION_CONTRACT_VERSION,
            "catalogue_id": "hk-regulatory-source-decision",
            "catalogue_version": "1.0.0",
            "status": "FROZEN_EXECUTABLE_CHECKPOINT",
            "case_count": HKEX_SOURCE_DECISION_CASE_COUNT,
            "primary_coverage_cell_count": HKEX_SOURCE_DECISION_CASE_COUNT,
            "high_risk_pair_ids": [f"HKREG-PAIR-{ordinal:03d}" for ordinal in range(1, 16)],
            "entries": entries,
            "checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "activation_authorized": False,
            "external_effects": "NONE",
        }
    )


def _source_decision_schema() -> dict[str, JsonValue]:
    string_array = {
        "type": "array",
        "uniqueItems": True,
        "items": {"type": "string", "minLength": 1},
    }
    scope_array = {
        "type": "array",
        "uniqueItems": True,
        "items": {"enum": [HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]},
    }
    return _closed_schema(
        [
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
        ],
        _json_object(
            {
                "schema_id": {"const": "asklegal.hk-regulatory.source-decision-result"},
                "schema_version": {"const": HKEX_SOURCE_DECISION_CONTRACT_VERSION},
                "rule_id": {"const": HKEX_SOURCE_DECISION_RULE_ID},
                "case_id": {
                    "type": "string",
                    "pattern": "^HKREG-DEC-SRC-(0[0-5][0-9]|06[0-2])$",
                },
                "outcome": {"enum": [item.value for item in HKEXSourceDecisionOutcome]},
                "reason": {"enum": [item.value for item in HKEXSourceDecisionReason]},
                "accepted_fact_codes": string_array,
                "rejected_fact_codes": string_array,
                "membership": {"enum": [None, *(item.value for item in HKEXMembership)]},
                "owner_scope_ids": scope_array,
                "component_instance_count": {"type": "integer", "minimum": 0},
                "blocked_scope_ids": scope_array,
                "permitted_scope_ids": scope_array,
                "source_contract_review_required": {"type": "boolean"},
                "english_investigation_required": {"type": "boolean"},
                "supported_no_change": {"type": "boolean"},
                "search_record_authorized": {"const": False},
                "embedding_authorized": {"const": False},
                "release_authorized": {"const": False},
                "serving_authorized": {"const": False},
                "external_effects": {"const": "NONE"},
            }
        ),
    )


def _source_facts_schema() -> dict[str, JsonValue]:
    source_array = {
        "type": "array",
        "uniqueItems": True,
        "items": {"enum": list(HKEX_REGULATORY_SOURCE_IDS)},
    }
    scope_array = {
        "type": "array",
        "uniqueItems": True,
        "items": {"enum": [HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]},
    }
    boolean_fields = {
        name: {"type": "boolean"}
        for name in (
            "source_artifact_final",
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
            "historical_investigation_only",
            "express_inclusion",
            "express_exclusion",
            "assigned_evidence_only_use",
            "inclusion_evidence_missing",
            "inclusion_evidence_unreadable",
            "inclusion_evidence_conflicting",
            "artifact_shared_between_boards",
            "identical_wording_across_boards",
            "ownership_conflict",
            "official_parent_supported",
            "required_english_complete",
            "chinese_available",
            "prohibited_source_repair",
            "optional_chinese_bounded_use",
        )
    }
    properties: dict[str, object] = {
        "source_id": {"enum": [None, *HKEX_REGULATORY_SOURCE_IDS]},
        "claimed_fact_codes": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "due_source_ids": source_array,
        "complete_source_ids": source_array,
        "fresh_source_ids": source_array,
        "reconciled_source_ids": source_array,
        "observation_gap": {"enum": [item.value for item in HKEXObservationGap]},
        "object_class": {"enum": [item.value for item in HKEXRegulatoryObjectClass]},
        "supported_owner_scopes": scope_array,
        "assigned_owner_scopes": scope_array,
        "assigned_instance_count": {"type": "integer", "minimum": 0},
        "artifact_component_count": {"type": "integer", "minimum": 0},
        "website_suggested_scope": {"enum": [None, HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]},
        "chinese_state": {"enum": [item.value for item in HKEXChineseEvidenceState]},
        **boolean_fields,
    }
    required = sorted(properties)
    return _closed_schema(required, _json_object(properties))


def build_source_decision_case_schema() -> dict[str, JsonValue]:
    """Build the strict ADR 0074 envelope for all 62 source cases."""
    fingerprint_schema = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    nonempty = {"type": "string", "minLength": 1}
    string_array = {
        "type": "array",
        "uniqueItems": True,
        "items": nonempty,
    }
    binding = _closed_schema(
        ["contract_id", "version", "fingerprint"],
        _json_object(
            {
                "contract_id": nonempty,
                "version": nonempty,
                "fingerprint": fingerprint_schema,
            }
        ),
    )
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": {
                    "type": "string",
                    "pattern": "^HKREG-PAIR-0(0[1-9]|1[0-5])$",
                },
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    evidence_packet = _closed_schema(
        ["slot_id", "state", "path", "role", "media_type", "content_fingerprint"],
        _json_object(
            {
                "slot_id": {"const": "source-evidence"},
                "state": {"enum": [item.value for item in HKEXSourceEvidenceState]},
                "path": nonempty,
                "role": {"enum": [item.value for item in HKEXSourceEvidenceRole]},
                "media_type": {"const": "application/json"},
                "content_fingerprint": fingerprint_schema,
            }
        ),
    )
    required = [
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
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.source-decision-case"},
            "schema_version": {"const": HKEX_SOURCE_DECISION_CONTRACT_VERSION},
            "package_contract_version": {"const": "1.0.0"},
            "case_id": {
                "type": "string",
                "pattern": "^HKREG-DEC-SRC-(0[0-5][0-9]|06[0-2])$",
            },
            "suite_layer": {"const": "EVIDENCE_TO_DECISION"},
            "primary_checkpoint": {"const": "SOURCE_FACT_AUTHORITY"},
            "frozen": {"const": True},
            "synthetic_evidence_class": {"const": "SYNTHETIC_NO_REAL_AUTHORITY"},
            "contract_bindings": {
                "type": "array",
                "minItems": 2,
                "uniqueItems": True,
                "items": binding,
            },
            "synthetic_cutoff": {"const": "2026-08-24T00:00:00Z"},
            "scope_id": {"const": "HKEX_CROSS_BOARD"},
            "prior_state": {"const": "SYNTHETIC_ACCEPTED_PREDECESSOR"},
            "primary_coverage_cell_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": {
                    "type": "string",
                    "pattern": "^HKREG-COV-DSRC-(0[0-5][0-9]|06[0-2])$",
                },
            },
            "secondary_coverage_cell_ids": string_array,
            "pair_membership": {"oneOf": [{"type": "null"}, pair]},
            "declared_input_inventory": {
                "type": "array",
                "prefixItems": [{"const": "source-evidence"}],
                "minItems": 1,
                "maxItems": 1,
            },
            "declared_reference_inventory": {
                "type": "array",
                "minItems": 2,
                "uniqueItems": True,
                "items": nonempty,
            },
            "declared_expected_inventory": {
                "type": "array",
                "prefixItems": [{"const": "SOURCE_DECISION_REPORT"}],
                "minItems": 1,
                "maxItems": 1,
            },
            "assertion_scope": {"enum": [item.value for item in HKEXSourceAssertionScope]},
            "required_result_dimensions": string_array,
            "evidence_packet_fields": string_array,
            "supporting_evidence_ranges": string_array,
            "rule_trace": string_array,
            "established_facts": string_array,
            "unresolved_facts": string_array,
            "permitted_equivalent_results": {"type": "array", "maxItems": 0},
            "critical_error_codes": string_array,
            "package_fingerprint": fingerprint_schema,
            "title": nonempty,
            "purpose": nonempty,
            "expected_decision": _source_decision_schema(),
            "evidence_packet": evidence_packet,
            "facts": _source_facts_schema(),
            "case_fingerprint": fingerprint_schema,
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-source-decision-case.schema.json",
            "title": "HKEX source evidence-to-decision conformance case",
            **_closed_schema(required, properties),
        }
    )


def build_source_decision_report_schema() -> dict[str, JsonValue]:
    """Build the strict full-decision conformance report schema."""
    required = [
        "schema_id",
        "schema_version",
        "rule_id",
        "case_id",
        "assertion_scope",
        "observed_decision",
        "expected_decision",
        "conformance_status",
        "source_authorized",
        "provider_authorized",
        "release_authorized",
        "serving_authorized",
        "deployment_authorized",
        "external_effects",
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.source-decision-report"},
            "schema_version": {"const": HKEX_SOURCE_DECISION_CONTRACT_VERSION},
            "rule_id": {"const": HKEX_SOURCE_DECISION_RULE_ID},
            "case_id": {
                "type": "string",
                "pattern": "^HKREG-DEC-SRC-(0[0-5][0-9]|06[0-2])$",
            },
            "assertion_scope": {"enum": [item.value for item in HKEXSourceAssertionScope]},
            "observed_decision": _source_decision_schema(),
            "expected_decision": _source_decision_schema(),
            "conformance_status": {"enum": ["PASS", "FAIL"]},
            "source_authorized": {"const": False},
            "provider_authorized": {"const": False},
            "release_authorized": {"const": False},
            "serving_authorized": {"const": False},
            "deployment_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-source-decision-report.schema.json",
            "title": "HKEX source decision conformance report",
            **_closed_schema(required, properties),
        }
    )


def build_source_decision_catalogue_schema() -> dict[str, JsonValue]:
    """Build the strict 62-entry executable-checkpoint catalogue schema."""
    fingerprint_schema = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    entry = _closed_schema(
        [
            "case_id",
            "primary_coverage_cell_id",
            "pair_membership",
            "assertion_scope",
            "expected_outcome",
            "expected_reason",
            "fixture_path",
            "fixture_fingerprint",
            "expected_path",
            "expected_fingerprint",
        ],
        _json_object(
            {
                "case_id": {"type": "string", "minLength": 1},
                "primary_coverage_cell_id": {"type": "string", "minLength": 1},
                "pair_membership": {
                    "oneOf": [
                        {"type": "null"},
                        _closed_schema(
                            ["pair_id", "role"],
                            _json_object(
                                {
                                    "pair_id": {"type": "string", "minLength": 1},
                                    "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
                                }
                            ),
                        ),
                    ]
                },
                "assertion_scope": {"enum": [item.value for item in HKEXSourceAssertionScope]},
                "expected_outcome": {"enum": [item.value for item in HKEXSourceDecisionOutcome]},
                "expected_reason": {"enum": [item.value for item in HKEXSourceDecisionReason]},
                "fixture_path": {"type": "string", "minLength": 1},
                "fixture_fingerprint": fingerprint_schema,
                "expected_path": {"type": "string", "minLength": 1},
                "expected_fingerprint": fingerprint_schema,
            }
        ),
    )
    required = [
        "schema_id",
        "schema_version",
        "catalogue_id",
        "catalogue_version",
        "status",
        "case_count",
        "primary_coverage_cell_count",
        "high_risk_pair_ids",
        "entries",
        "checkpoint_complete",
        "full_conformance_suite_complete",
        "activation_authorized",
        "external_effects",
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.source-decision-catalogue"},
            "schema_version": {"const": HKEX_SOURCE_DECISION_CONTRACT_VERSION},
            "catalogue_id": {"const": "hk-regulatory-source-decision"},
            "catalogue_version": {"const": "1.0.0"},
            "status": {"const": "FROZEN_EXECUTABLE_CHECKPOINT"},
            "case_count": {"const": HKEX_SOURCE_DECISION_CASE_COUNT},
            "primary_coverage_cell_count": {"const": HKEX_SOURCE_DECISION_CASE_COUNT},
            "high_risk_pair_ids": {
                "type": "array",
                "minItems": 15,
                "maxItems": 15,
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
            },
            "entries": {
                "type": "array",
                "minItems": HKEX_SOURCE_DECISION_CASE_COUNT,
                "maxItems": HKEX_SOURCE_DECISION_CASE_COUNT,
                "items": entry,
            },
            "checkpoint_complete": {"const": True},
            "full_conformance_suite_complete": {"const": False},
            "activation_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-source-decision-catalogue.schema.json",
            "title": "HKEX source-decision executable checkpoint catalogue",
            **_closed_schema(required, properties),
        }
    )


_PACKAGE_INTEGRITY_SCOPES = (
    HKEXPackageAssertionScope.COMPLETE_PACKAGE,
    HKEXPackageAssertionScope.CLOSED_SCHEMA,
    HKEXPackageAssertionScope.ARTIFACT_HASH,
    HKEXPackageAssertionScope.DECLARED_ACCESS,
    HKEXPackageAssertionScope.REQUIRED_FILE,
    HKEXPackageAssertionScope.ABSOLUTE_PATH,
    HKEXPackageAssertionScope.NORMALIZED_PATH,
    HKEXPackageAssertionScope.SYMLINK,
    HKEXPackageAssertionScope.REMOTE_RESOURCE,
    HKEXPackageAssertionScope.EXPLICIT_INVENTORY,
    HKEXPackageAssertionScope.AVAILABLE_INPUT,
    HKEXPackageAssertionScope.AVAILABLE_INPUT,
    HKEXPackageAssertionScope.DELIBERATE_ABSENCE,
    HKEXPackageAssertionScope.DELIBERATE_ABSENCE,
    HKEXPackageAssertionScope.UNREADABLE_INPUT,
    HKEXPackageAssertionScope.AVAILABLE_FACT_CONDITION,
    HKEXPackageAssertionScope.EXACT_OUTPUT,
    HKEXPackageAssertionScope.EXACT_OUTPUT,
    HKEXPackageAssertionScope.ZERO_OUTPUT,
    HKEXPackageAssertionScope.ZERO_OUTPUT,
    HKEXPackageAssertionScope.NOT_APPLICABLE_OUTPUT,
    HKEXPackageAssertionScope.NOT_APPLICABLE_OUTPUT,
    HKEXPackageAssertionScope.MATRIX_COMPLETENESS,
    HKEXPackageAssertionScope.MATRIX_COMPLETENESS,
    HKEXPackageAssertionScope.PAIR_COMPLETENESS,
    HKEXPackageAssertionScope.PAIR_COMPLETENESS,
    HKEXPackageAssertionScope.PROPOSAL_ISOLATION,
    HKEXPackageAssertionScope.IMMUTABLE_FINGERPRINT,
    HKEXPackageAssertionScope.REPRODUCIBILITY,
    HKEXPackageAssertionScope.REPRODUCIBILITY,
    HKEXPackageAssertionScope.HOSTILE_SOURCE_TEXT,
    HKEXPackageAssertionScope.HOSTILE_SOURCE_TEXT,
    HKEXPackageAssertionScope.LOCAL_CAPABILITY_DENIAL,
    HKEXPackageAssertionScope.EXTERNAL_CAPABILITY_DENIAL,
    HKEXPackageAssertionScope.AUTHORITY_CONTAINMENT,
    HKEXPackageAssertionScope.ATTESTATION_COMPATIBILITY,
    HKEXPackageAssertionScope.ATTESTATION_COMPATIBILITY,
    HKEXPackageAssertionScope.MEDIA_AND_PERMISSION,
)

_PACKAGE_INTEGRITY_EXPECTED = (
    (HKEXPackageIntegrityOutcome.ACCEPTED, HKEXPackageIntegrityReason.PACKAGE_VALID),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.CLOSED_SCHEMA_VIOLATION,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.ARTIFACT_HASH_MISMATCH,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.UNDECLARED_FILE_ACCESS,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.REQUIRED_FILE_ABSENT,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.PATH_CONTAINMENT_INVALID,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.PATH_CONTAINMENT_INVALID,
    ),
    (HKEXPackageIntegrityOutcome.REJECTED, HKEXPackageIntegrityReason.SYMLINK_FORBIDDEN),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.REMOTE_RESOURCE_FORBIDDEN,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.DYNAMIC_DISCOVERY_FORBIDDEN,
    ),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.INPUT_AVAILABLE_ADMITTED,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.INPUT_AVAILABLE_INVALID,
    ),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.DELIBERATE_ABSENCE_ADMITTED,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.INPUT_AVAILABLE_INVALID,
    ),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.UNREADABLE_CONDITION_ADMITTED,
    ),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.AVAILABLE_FACT_CONDITION_ADMITTED,
    ),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.EXACT_ARTIFACT_MATCHED,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.EXPECTED_EXACT_INVALID,
    ),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.ZERO_OUTPUT_PROVED,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.ZERO_OUTPUT_PROOF_INVALID,
    ),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.NOT_APPLICABLE_PROVED,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.NOT_APPLICABLE_INVALID,
    ),
    (HKEXPackageIntegrityOutcome.ACCEPTED, HKEXPackageIntegrityReason.MATRIX_COMPLETE),
    (HKEXPackageIntegrityOutcome.REJECTED, HKEXPackageIntegrityReason.MATRIX_INCOMPLETE),
    (HKEXPackageIntegrityOutcome.ACCEPTED, HKEXPackageIntegrityReason.PAIR_COMPLETE),
    (HKEXPackageIntegrityOutcome.REJECTED, HKEXPackageIntegrityReason.PAIR_INCOMPLETE),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.PROPOSAL_PACKET_CLEAN,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.FINGERPRINT_OR_TRUTH_MUTATION,
    ),
    (HKEXPackageIntegrityOutcome.ACCEPTED, HKEXPackageIntegrityReason.REPRODUCIBLE),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.REPRODUCIBILITY_FAILURE,
    ),
    (HKEXPackageIntegrityOutcome.ACCEPTED, HKEXPackageIntegrityReason.HOSTILE_TEXT_INERT),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.HOSTILE_INPUT_CONTROL_BREACH,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.FORBIDDEN_CAPABILITY_ATTEMPT,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.FORBIDDEN_CAPABILITY_ATTEMPT,
    ),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.PACKAGE_VALIDITY_ONLY,
    ),
    (
        HKEXPackageIntegrityOutcome.ACCEPTED,
        HKEXPackageIntegrityReason.BUILD_COMPATIBILITY_ONLY,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.ATTESTATION_MISMATCH,
    ),
    (
        HKEXPackageIntegrityOutcome.REJECTED,
        HKEXPackageIntegrityReason.MEDIA_OR_PERMISSION_INVALID,
    ),
)


def _virtual_artifact(
    path: str,
    role: str,
    value: JsonValue,
    *,
    required: bool,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    raw = rfc8785.dumps(value)
    declared: dict[str, JsonValue] = {
        "path": path,
        "role": role,
        "media_type": "application/json",
        "fingerprint": _fingerprint(raw),
        "required": required,
    }
    virtual: dict[str, JsonValue] = {
        "path": path,
        "media_type": "application/json",
        "content_base64": b64encode(raw).decode("ascii"),
        "node_type": "REGULAR_FILE",
        "content_class": "NORMAL",
        "readable": True,
        "schema_valid": True,
        "canonical_bytes": True,
    }
    return declared, virtual


def _package_integrity_matrix(universe: dict[str, JsonValue]) -> dict[str, JsonValue]:
    cases = [_json_object(item) for item in _json_array(universe["cases"])]
    pairs = [_json_object(item) for item in _json_array(universe["pair_index"])]
    if len(cases) != HKEX_CONFORMANCE_CASE_COUNT or len(pairs) != HKEX_CONFORMANCE_PAIR_COUNT:
        raise _ConformanceBuildError
    return {
        "required_cell_ids": [item["coverage_cell_id"] for item in cases],
        "executable_case_ids": [item["case_id"] for item in cases],
        "primary_coverage": [
            {"cell_id": item["coverage_cell_id"], "case_id": item["case_id"]} for item in cases
        ],
        "required_rule_ids": [
            "HKREG-CONFORMANCE-UNIVERSE-001",
            HKEX_PACKAGE_INTEGRITY_RULE_ID,
        ],
        "covered_rule_ids": [
            "HKREG-CONFORMANCE-UNIVERSE-001",
            HKEX_PACKAGE_INTEGRITY_RULE_ID,
        ],
        "required_result_branches": [item.value for item in HKEXPackageIntegrityReason],
        "covered_result_branches": [item.value for item in HKEXPackageIntegrityReason],
        "required_pair_ids": [item["pair_id"] for item in pairs],
        "pairs": [
            {
                "pair_id": item["pair_id"],
                "members": [
                    {"case_id": item["positive_case_id"], "role": "POSITIVE"},
                    {"case_id": item["near_miss_case_id"], "role": "NEAR_MISS"},
                ],
            }
            for item in pairs
        ],
    }


def _base_package_integrity_facts(universe: dict[str, JsonValue]) -> dict[str, JsonValue]:
    artifact_specs = (
        ("manifest.json", "PACKAGE_ROOT", {"schema_id": "synthetic-package", "version": "1"}, True),
        ("catalogues/matrix.json", "CATALOGUE", {"cells": 284, "pairs": 57}, True),
        (
            "cases/case.json",
            "CASE_DOCUMENT",
            {"frozen": True, "layer": "DECISION_TO_ARTIFACT"},
            True,
        ),
        ("inputs/source.json", "SOURCE_EVIDENCE", {"text": "ordinary synthetic evidence"}, True),
        ("expected/result.json", "EXPECTED_ARTIFACT", {"result": "synthetic expected"}, False),
    )
    declared: list[JsonValue] = []
    virtual: list[JsonValue] = []
    for path, role, value, required in artifact_specs:
        declaration, artifact = _virtual_artifact(
            path, role, _json_object(value), required=required
        )
        declared.append(declaration)
        virtual.append(artifact)
    expected_fingerprint = _json_object(declared[-1])["fingerprint"]
    binding_names = (
        "architecture-tests",
        "dependency-lock",
        "processing-build",
        "reproducibility-report",
        "result-set",
        "rulebook",
        "runner",
        "suite",
    )
    bindings = [
        {"name": name, "fingerprint": f"sha256:{ordinal:064x}"}
        for ordinal, name in enumerate(binding_names, start=1)
    ]
    stable_run = [f"sha256:{ordinal:064x}" for ordinal in range(101, 107)]
    return _json_object(
        {
            "closed_schema_violations": [],
            "declared_artifacts": declared,
            "virtual_artifacts": virtual,
            "runner_access_paths": [item[0] for item in artifact_specs],
            "discovery_methods": ["EXPLICIT_INVENTORY"],
            "input_slots": [
                {
                    "slot_id": "source-evidence",
                    "state": "AVAILABLE",
                    "path": "inputs/source.json",
                    "fact_condition": "ORDINARY",
                }
            ],
            "expected_artifacts": [
                {
                    "role": "CASE_EXECUTION_REPORT",
                    "state": "EXACT",
                    "path": "expected/result.json",
                    "expected_fingerprint": expected_fingerprint,
                    "zero_count": None,
                    "checkpoint_applicable": True,
                    "matrix_proves_nonapplicable": False,
                    "implementation_completed": True,
                }
            ],
            "matrix": _package_integrity_matrix(universe),
            "proposal_packet_fields": [
                "evidence_fingerprint",
                "source_text",
                "task_contract",
            ],
            "fingerprint_scope": "EXCLUDES_SELF",
            "expected_truth_mutated": False,
            "run_output_fingerprints": [stable_run, stable_run],
            "source_instruction_present": False,
            "source_instruction_effects": [],
            "attempted_capabilities": [],
            "external_state_mutated": False,
            "authority_claims": [],
            "attestation": {
                "complete": True,
                "compatibility_only": True,
                "current_bindings": bindings,
                "attested_bindings": bindings,
            },
        }
    )


def _replace_path(facts: dict[str, JsonValue], old: str, new: str) -> None:
    for collection_name in ("declared_artifacts", "virtual_artifacts"):
        for item in _json_array(facts[collection_name]):
            artifact = _mutable_object(item)
            if artifact["path"] == old:
                artifact["path"] = new
    facts["runner_access_paths"] = [
        new if item == old else item for item in _json_array(facts["runner_access_paths"])
    ]
    for item in _json_array(facts["input_slots"]):
        slot = _json_object(item)
        if slot["path"] == old:
            slot["path"] = new


def _remove_virtual(facts: dict[str, JsonValue], path: str) -> None:
    facts["virtual_artifacts"] = [
        item
        for item in _json_array(facts["virtual_artifacts"])
        if _mutable_object(item)["path"] != path
    ]


def _declaration(facts: dict[str, JsonValue], path: str) -> dict[str, JsonValue]:
    return next(
        item
        for value in _json_array(facts["declared_artifacts"])
        if (item := _mutable_object(value))["path"] == path
    )


def _virtual(facts: dict[str, JsonValue], path: str) -> dict[str, JsonValue]:
    return next(
        item
        for value in _json_array(facts["virtual_artifacts"])
        if (item := _mutable_object(value))["path"] == path
    )


def _expected(facts: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return _mutable_object(_json_array(facts["expected_artifacts"])[0])


def _mutate_package_preflight(case: str, facts: dict[str, JsonValue]) -> bool:
    if case == "002":
        facts["closed_schema_violations"] = ["root.unknown_property"]
    elif case == "003":
        _declaration(facts, "inputs/source.json")["fingerprint"] = f"sha256:{'0' * 64}"
    elif case == "004":
        _json_array(facts["runner_access_paths"]).append("private/undeclared.json")
    elif case == "005":
        _remove_virtual(facts, "catalogues/matrix.json")
    elif case == "006":
        _replace_path(facts, "inputs/source.json", "/synthetic/source.json")
    elif case == "007":
        _replace_path(facts, "inputs/source.json", "inputs//source.json")
    elif case == "008":
        _virtual(facts, "inputs/source.json")["node_type"] = "SYMLINK"
    elif case == "009":
        _replace_path(facts, "inputs/source.json", "https://example.invalid/source.json")
    elif case == "010":
        facts["discovery_methods"] = ["GLOB"]
    else:
        return False
    return True


def _mutate_package_inputs(case: str, facts: dict[str, JsonValue]) -> bool:
    if case in {"012", "013", "014"}:
        _remove_virtual(facts, "inputs/source.json")
        _declaration(facts, "inputs/source.json")["required"] = False
        slot = _mutable_object(_json_array(facts["input_slots"])[0])
        slot["state"] = "INTENTIONALLY_ABSENT" if case == "013" else "AVAILABLE"
    elif case == "015":
        raw = b"\x00unsupported-synthetic-bytes"
        declaration = _declaration(facts, "inputs/source.json")
        declaration["fingerprint"] = _fingerprint(raw)
        artifact = _virtual(facts, "inputs/source.json")
        artifact["content_base64"] = b64encode(raw).decode("ascii")
        artifact["content_class"] = "CORRUPT_OR_UNSUPPORTED"
        artifact["schema_valid"] = False
        artifact["canonical_bytes"] = False
        _mutable_object(_json_array(facts["input_slots"])[0])["state"] = "UNREADABLE"
    elif case == "016":
        _mutable_object(_json_array(facts["input_slots"])[0])["fact_condition"] = "STALE"
    else:
        return False
    return True


def _mutate_package_outputs(case: str, facts: dict[str, JsonValue]) -> bool:
    if case == "018":
        raw = rfc8785.dumps(_json_object({"result": "byte-different synthetic output"}))
        _declaration(facts, "expected/result.json")["fingerprint"] = _fingerprint(raw)
        _virtual(facts, "expected/result.json")["content_base64"] = b64encode(raw).decode("ascii")
    elif case in {"019", "020"}:
        _remove_virtual(facts, "expected/result.json")
        expected = _expected(facts)
        expected["state"] = "NONE"
        expected["path"] = None
        expected["expected_fingerprint"] = None
        expected["zero_count"] = 0 if case == "019" else None
    elif case in {"021", "022"}:
        _remove_virtual(facts, "expected/result.json")
        expected = _expected(facts)
        expected["state"] = "NOT_APPLICABLE"
        expected["path"] = None
        expected["expected_fingerprint"] = None
        expected["checkpoint_applicable"] = case == "022"
        expected["matrix_proves_nonapplicable"] = True
        expected["implementation_completed"] = case == "021"
    else:
        return False
    return True


def _mutate_package_matrix_and_isolation(case: str, facts: dict[str, JsonValue]) -> bool:
    if case == "024":
        matrix = _mutable_object(facts["matrix"])
        _json_array(matrix["primary_coverage"]).pop()
    elif case == "026":
        matrix = _mutable_object(facts["matrix"])
        pair = next(
            item
            for value in _json_array(matrix["pairs"])
            if (item := _mutable_object(value))["pair_id"] == "HKREG-PAIR-054"
        )
        _json_array(pair["members"]).pop()
    elif case == "028":
        facts["fingerprint_scope"] = "INCLUDES_SELF"
    elif case == "030":
        runs = _json_array(facts["run_output_fingerprints"])
        _json_array(runs[1])[0] = f"sha256:{999:064x}"
    elif case == "031":
        facts["source_instruction_present"] = True
    elif case == "032":
        facts["source_instruction_present"] = True
        facts["source_instruction_effects"] = ["RUNNER_PATH_CHANGED"]
    else:
        return False
    return True


def _mutate_package_authority(case: str, facts: dict[str, JsonValue]) -> bool:
    if case == "033":
        facts["attempted_capabilities"] = ["SOURCE"]
    elif case == "034":
        facts["attempted_capabilities"] = ["AZURE"]
    elif case == "035":
        facts["authority_claims"] = ["PACKAGE_VALIDITY"]
    elif case == "036":
        facts["authority_claims"] = ["BUILD_COMPATIBILITY"]
    elif case == "037":
        facts["authority_claims"] = ["BUILD_COMPATIBILITY"]
        attestation = _mutable_object(facts["attestation"])
        binding = _mutable_object(_json_array(attestation["attested_bindings"])[0])
        binding["fingerprint"] = f"sha256:{999:064x}"
    elif case == "038":
        artifact = _virtual(facts, "inputs/source.json")
        artifact["media_type"] = "text/plain"
        artifact["readable"] = False
    else:
        return False
    return True


def _mutate_package_integrity_facts(suffix: int, facts: dict[str, JsonValue]) -> None:
    case = f"{suffix:03d}"
    for mutate in (
        _mutate_package_preflight,
        _mutate_package_inputs,
        _mutate_package_outputs,
        _mutate_package_matrix_and_isolation,
        _mutate_package_authority,
    ):
        if mutate(case, facts):
            return


def build_package_integrity_cases() -> tuple[
    tuple[dict[str, JsonValue], dict[str, JsonValue]], ...
]:
    """Build all 38 executable package-integrity cases and expected reports."""
    universe = build_conformance_universe()
    universe_cases = [
        _json_object(item)
        for item in _json_array(universe["cases"])[-HKEX_PACKAGE_INTEGRITY_CASE_COUNT:]
    ]
    pair_memberships = {
        item["case_id"]: _json_array(item["pair_memberships"]) for item in universe_cases
    }
    package_fingerprint = _fingerprint(rfc8785.dumps(universe))
    contract_seed = _json_object(
        {
            "contract_id": "asklegal.hk-regulatory.package-integrity-case",
            "contract_version": HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION,
            "rule_id": HKEX_PACKAGE_INTEGRITY_RULE_ID,
        }
    )
    contract_fingerprint = _fingerprint(rfc8785.dumps(contract_seed))
    results: list[tuple[dict[str, JsonValue], dict[str, JsonValue]]] = []
    for suffix, (universe_case, scope, expected) in enumerate(
        zip(
            universe_cases,
            _PACKAGE_INTEGRITY_SCOPES,
            _PACKAGE_INTEGRITY_EXPECTED,
            strict=True,
        ),
        start=1,
    ):
        facts = deepcopy(_base_package_integrity_facts(universe))
        _mutate_package_integrity_facts(suffix, facts)
        memberships = pair_memberships[universe_case["case_id"]]
        pair_membership: JsonValue = None
        if memberships:
            if len(memberships) != 1:
                raise _ConformanceBuildError
            pair_membership = deepcopy(_json_object(memberships[0]))
        fixture: dict[str, JsonValue] = {
            "schema_id": "asklegal.hk-regulatory.package-integrity-case",
            "schema_version": HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION,
            "package_contract_version": "1.0.0",
            "case_id": universe_case["case_id"],
            "suite_layer": "DECISION_TO_ARTIFACT",
            "primary_checkpoint": "PACKAGE_INTEGRITY",
            "frozen": True,
            "synthetic_evidence_class": "SYNTHETIC_NO_REAL_AUTHORITY",
            "contract_bindings": [
                {
                    "contract_id": "asklegal.hk-regulatory.conformance-universe",
                    "version": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
                    "fingerprint": package_fingerprint,
                },
                {
                    "contract_id": "asklegal.hk-regulatory.package-integrity-case",
                    "version": HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION,
                    "fingerprint": contract_fingerprint,
                },
            ],
            "synthetic_cutoff": "2026-08-24T00:00:00Z",
            "scope_id": "HKEX_CROSS_BOARD",
            "prior_state": "NO_LIVE_STATE",
            "primary_coverage_cell_ids": [universe_case["coverage_cell_id"]],
            "secondary_coverage_cell_ids": [],
            "pair_membership": pair_membership,
            "declared_input_inventory": ["source-evidence"],
            "declared_reference_inventory": [
                "asklegal.hk-regulatory.conformance-universe",
                "asklegal.hk-regulatory.package-integrity-case",
            ],
            "declared_expected_inventory": ["CASE_EXECUTION_REPORT"],
            "required_result_dimensions": [
                "AUTHORITY",
                "FORBIDDEN_EFFECTS",
                "PACKAGE_INTEGRITY",
            ],
            "assertion_scope": scope.value,
            "package_fingerprint": package_fingerprint,
            "title": universe_case["synthetic_scenario"],
            "purpose": universe_case["exact_required_result"],
            "expected_outcome": expected[0].value,
            "expected_reason": expected[1].value,
            "facts": facts,
            "case_fingerprint": "PENDING",
        }
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        parsed = hkex_package_integrity_case_from_document(fixture)
        report = _json_object(run_hkex_package_integrity_case(parsed).document())
        if report["conformance_status"] != "PASS":
            failure = f"{parsed.case_id}:{report['observed_reason']}"
            raise _ConformanceBuildError(failure)
        results.append((_json_object(fixture), report))
    if len(results) != HKEX_PACKAGE_INTEGRITY_CASE_COUNT:
        raise _ConformanceBuildError
    return tuple(results)


def build_package_integrity_catalogue(
    cases: tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...],
) -> dict[str, JsonValue]:
    """Bind every executable package-integrity fixture and expected report."""
    entries: list[JsonValue] = []
    for fixture, report in cases:
        case_id = str(fixture["case_id"])
        fixture_path = f"fixtures/conformance/package-integrity/{case_id}.json"
        expected_path = f"expected/conformance/package-integrity/{case_id}.json"
        entries.append(
            {
                "case_id": case_id,
                "primary_coverage_cell_id": _json_array(fixture["primary_coverage_cell_ids"])[0],
                "pair_membership": fixture["pair_membership"],
                "assertion_scope": fixture["assertion_scope"],
                "expected_outcome": fixture["expected_outcome"],
                "expected_reason": fixture["expected_reason"],
                "fixture_path": fixture_path,
                "fixture_fingerprint": _fingerprint(
                    (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode()
                ),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint(
                    (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
                ),
            }
        )
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.package-integrity-catalogue",
            "schema_version": HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION,
            "catalogue_id": "hk-regulatory-package-integrity",
            "catalogue_version": "1.0.0",
            "status": "FROZEN_EXECUTABLE_CHECKPOINT",
            "case_count": HKEX_PACKAGE_INTEGRITY_CASE_COUNT,
            "primary_coverage_cell_count": HKEX_PACKAGE_INTEGRITY_CASE_COUNT,
            "high_risk_pair_ids": [f"HKREG-PAIR-{ordinal:03d}" for ordinal in range(50, 57)],
            "entries": entries,
            "checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "activation_authorized": False,
            "external_effects": "NONE",
        }
    )


def _closed_schema(required: list[str], properties: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return _json_object(
        {
            "type": "object",
            "additionalProperties": False,
            "required": required,
            "properties": properties,
        }
    )


def build_package_integrity_case_schema() -> dict[str, JsonValue]:
    """Build the closed common-envelope schema for the 38 executable cases."""
    fingerprint_schema: dict[str, JsonValue] = {
        "type": "string",
        "pattern": "^sha256:[0-9a-f]{64}$",
    }
    nonempty: dict[str, JsonValue] = {"type": "string", "minLength": 1}
    string_array: dict[str, JsonValue] = {"type": "array", "items": nonempty}
    binding = _closed_schema(
        ["contract_id", "version", "fingerprint"],
        {
            "contract_id": nonempty,
            "version": nonempty,
            "fingerprint": fingerprint_schema,
        },
    )
    pair_membership = _closed_schema(
        ["pair_id", "role"],
        {
            "pair_id": {"type": "string", "pattern": "^HKREG-PAIR-05[0-6]$"},
            "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
        },
    )
    declared_artifact = _closed_schema(
        ["path", "role", "media_type", "fingerprint", "required"],
        {
            "path": nonempty,
            "role": nonempty,
            "media_type": nonempty,
            "fingerprint": fingerprint_schema,
            "required": {"type": "boolean"},
        },
    )
    virtual_artifact = _closed_schema(
        [
            "path",
            "media_type",
            "content_base64",
            "node_type",
            "content_class",
            "readable",
            "schema_valid",
            "canonical_bytes",
        ],
        {
            "path": nonempty,
            "media_type": nonempty,
            "content_base64": nonempty,
            "node_type": {"enum": ["REGULAR_FILE", "SYMLINK"]},
            "content_class": {"enum": ["NORMAL", "CORRUPT_OR_UNSUPPORTED"]},
            "readable": {"type": "boolean"},
            "schema_valid": {"type": "boolean"},
            "canonical_bytes": {"type": "boolean"},
        },
    )
    input_slot = _closed_schema(
        ["slot_id", "state", "path", "fact_condition"],
        {
            "slot_id": nonempty,
            "state": {"enum": ["AVAILABLE", "INTENTIONALLY_ABSENT", "UNREADABLE"]},
            "path": {"oneOf": [nonempty, {"type": "null"}]},
            "fact_condition": {
                "enum": [
                    "ORDINARY",
                    "STALE",
                    "CONFLICTING",
                    "WRONG_BOARD",
                    "DIFFERENT_VERSION",
                ]
            },
        },
    )
    expected_artifact = _closed_schema(
        [
            "role",
            "state",
            "path",
            "expected_fingerprint",
            "zero_count",
            "checkpoint_applicable",
            "matrix_proves_nonapplicable",
            "implementation_completed",
        ],
        {
            "role": nonempty,
            "state": {"enum": ["EXACT", "NONE", "NOT_APPLICABLE"]},
            "path": {"oneOf": [nonempty, {"type": "null"}]},
            "expected_fingerprint": {"oneOf": [fingerprint_schema, {"type": "null"}]},
            "zero_count": {
                "oneOf": [
                    {"type": "integer", "minimum": 0},
                    {"type": "null"},
                ]
            },
            "checkpoint_applicable": {"type": "boolean"},
            "matrix_proves_nonapplicable": {"type": "boolean"},
            "implementation_completed": {"type": "boolean"},
        },
    )
    primary_coverage = _closed_schema(
        ["cell_id", "case_id"],
        {"cell_id": nonempty, "case_id": nonempty},
    )
    pair_member = _closed_schema(
        ["case_id", "role"],
        {
            "case_id": nonempty,
            "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
        },
    )
    pair_definition = _closed_schema(
        ["pair_id", "members"],
        {
            "pair_id": {"type": "string", "pattern": r"^HKREG-PAIR-\d{3}$"},
            "members": {"type": "array", "items": pair_member},
        },
    )
    matrix = _closed_schema(
        [
            "required_cell_ids",
            "executable_case_ids",
            "primary_coverage",
            "required_rule_ids",
            "covered_rule_ids",
            "required_result_branches",
            "covered_result_branches",
            "required_pair_ids",
            "pairs",
        ],
        {
            "required_cell_ids": string_array,
            "executable_case_ids": string_array,
            "primary_coverage": {"type": "array", "items": primary_coverage},
            "required_rule_ids": string_array,
            "covered_rule_ids": string_array,
            "required_result_branches": string_array,
            "covered_result_branches": string_array,
            "required_pair_ids": string_array,
            "pairs": {"type": "array", "items": pair_definition},
        },
    )
    attestation_binding = _closed_schema(
        ["name", "fingerprint"],
        {"name": nonempty, "fingerprint": fingerprint_schema},
    )
    attestation = _closed_schema(
        ["complete", "compatibility_only", "current_bindings", "attested_bindings"],
        {
            "complete": {"type": "boolean"},
            "compatibility_only": {"type": "boolean"},
            "current_bindings": {"type": "array", "items": attestation_binding},
            "attested_bindings": {"type": "array", "items": attestation_binding},
        },
    )
    facts = _closed_schema(
        [
            "closed_schema_violations",
            "declared_artifacts",
            "virtual_artifacts",
            "runner_access_paths",
            "discovery_methods",
            "input_slots",
            "expected_artifacts",
            "matrix",
            "proposal_packet_fields",
            "fingerprint_scope",
            "expected_truth_mutated",
            "run_output_fingerprints",
            "source_instruction_present",
            "source_instruction_effects",
            "attempted_capabilities",
            "external_state_mutated",
            "authority_claims",
            "attestation",
        ],
        {
            "closed_schema_violations": string_array,
            "declared_artifacts": {"type": "array", "items": declared_artifact},
            "virtual_artifacts": {"type": "array", "items": virtual_artifact},
            "runner_access_paths": string_array,
            "discovery_methods": {
                "type": "array",
                "items": {
                    "enum": [
                        "EXPLICIT_INVENTORY",
                        "GLOB",
                        "RANGE",
                        "FILENAME_CONVENTION",
                        "DIRECTORY_SCAN",
                    ]
                },
            },
            "input_slots": {"type": "array", "items": input_slot},
            "expected_artifacts": {"type": "array", "items": expected_artifact},
            "matrix": matrix,
            "proposal_packet_fields": string_array,
            "fingerprint_scope": {"enum": ["EXCLUDES_SELF", "INCLUDES_SELF"]},
            "expected_truth_mutated": {"type": "boolean"},
            "run_output_fingerprints": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": fingerprint_schema,
                },
            },
            "source_instruction_present": {"type": "boolean"},
            "source_instruction_effects": string_array,
            "attempted_capabilities": {
                "type": "array",
                "items": {
                    "enum": [
                        "SOURCE",
                        "GENERATIVE_MODEL",
                        "EMBEDDING",
                        "NETWORK",
                        "CREDENTIAL",
                        "AZURE",
                        "PINECONE",
                        "BACKUP",
                        "ROUTING",
                        "PROMOTION",
                        "PRODUCTION_STORE",
                        "UNDECLARED_FILE",
                        "LIVE_STATE",
                    ]
                },
            },
            "external_state_mutated": {"type": "boolean"},
            "authority_claims": string_array,
            "attestation": attestation,
        },
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-package-integrity-case.schema.json",
            "title": "HKEX package-integrity conformance case",
            **_closed_schema(
                [
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
                    "required_result_dimensions",
                    "assertion_scope",
                    "package_fingerprint",
                    "title",
                    "purpose",
                    "expected_outcome",
                    "expected_reason",
                    "facts",
                    "case_fingerprint",
                ],
                {
                    "schema_id": {"const": "asklegal.hk-regulatory.package-integrity-case"},
                    "schema_version": {"const": HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION},
                    "package_contract_version": {"const": "1.0.0"},
                    "case_id": {
                        "type": "string",
                        "pattern": "^HKREG-DET-PKG-(0[0-2][0-9]|03[0-8])$",
                    },
                    "suite_layer": {"const": "DECISION_TO_ARTIFACT"},
                    "primary_checkpoint": {"const": "PACKAGE_INTEGRITY"},
                    "frozen": {"const": True},
                    "synthetic_evidence_class": {"const": "SYNTHETIC_NO_REAL_AUTHORITY"},
                    "contract_bindings": {
                        "type": "array",
                        "minItems": 2,
                        "items": binding,
                    },
                    "synthetic_cutoff": {"const": "2026-08-24T00:00:00Z"},
                    "scope_id": {"const": "HKEX_CROSS_BOARD"},
                    "prior_state": {"const": "NO_LIVE_STATE"},
                    "primary_coverage_cell_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 1,
                        "items": {
                            "type": "string",
                            "pattern": "^HKREG-COV-DPKG-(0[0-2][0-9]|03[0-8])$",
                        },
                    },
                    "secondary_coverage_cell_ids": string_array,
                    "pair_membership": {"oneOf": [pair_membership, {"type": "null"}]},
                    "declared_input_inventory": string_array,
                    "declared_reference_inventory": string_array,
                    "declared_expected_inventory": string_array,
                    "required_result_dimensions": string_array,
                    "assertion_scope": {"enum": [item.value for item in HKEXPackageAssertionScope]},
                    "package_fingerprint": fingerprint_schema,
                    "title": nonempty,
                    "purpose": nonempty,
                    "expected_outcome": {
                        "enum": [item.value for item in HKEXPackageIntegrityOutcome]
                    },
                    "expected_reason": {
                        "enum": [item.value for item in HKEXPackageIntegrityReason]
                    },
                    "facts": facts,
                    "case_fingerprint": fingerprint_schema,
                },
            ),
        }
    )


def build_package_integrity_report_schema() -> dict[str, JsonValue]:
    """Build the closed deterministic execution-report schema."""
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-package-integrity-report.schema.json",
            "title": "HKEX package-integrity conformance report",
            **_closed_schema(
                [
                    "schema_id",
                    "schema_version",
                    "rule_id",
                    "case_id",
                    "assertion_scope",
                    "observed_outcome",
                    "observed_reason",
                    "expected_outcome",
                    "expected_reason",
                    "conformance_status",
                    "package_valid",
                    "external_state_mutated",
                    "authority_grants",
                    "source_authorized",
                    "provider_authorized",
                    "release_authorized",
                    "serving_authorized",
                    "deployment_authorized",
                    "external_effects",
                ],
                {
                    "schema_id": {"const": "asklegal.hk-regulatory.package-integrity-report"},
                    "schema_version": {"const": HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION},
                    "rule_id": {"const": HKEX_PACKAGE_INTEGRITY_RULE_ID},
                    "case_id": {
                        "type": "string",
                        "pattern": "^HKREG-DET-PKG-(0[0-2][0-9]|03[0-8])$",
                    },
                    "assertion_scope": {"enum": [item.value for item in HKEXPackageAssertionScope]},
                    "observed_outcome": {
                        "enum": [item.value for item in HKEXPackageIntegrityOutcome]
                    },
                    "observed_reason": {
                        "enum": [item.value for item in HKEXPackageIntegrityReason]
                    },
                    "expected_outcome": {
                        "enum": [item.value for item in HKEXPackageIntegrityOutcome]
                    },
                    "expected_reason": {
                        "enum": [item.value for item in HKEXPackageIntegrityReason]
                    },
                    "conformance_status": {"enum": ["PASS", "FAIL"]},
                    "package_valid": {"type": "boolean"},
                    "external_state_mutated": {"type": "boolean"},
                    "authority_grants": {"type": "array", "items": {"type": "string"}},
                    "source_authorized": {"const": False},
                    "provider_authorized": {"const": False},
                    "release_authorized": {"const": False},
                    "serving_authorized": {"const": False},
                    "deployment_authorized": {"const": False},
                    "external_effects": {"const": "NONE"},
                },
            ),
        }
    )


def build_package_integrity_catalogue_schema() -> dict[str, JsonValue]:
    """Build the closed catalogue binding schema for this complete checkpoint."""
    nonempty: dict[str, JsonValue] = {"type": "string", "minLength": 1}
    fingerprint_schema: dict[str, JsonValue] = {
        "type": "string",
        "pattern": "^sha256:[0-9a-f]{64}$",
    }
    entry = _closed_schema(
        [
            "case_id",
            "primary_coverage_cell_id",
            "pair_membership",
            "assertion_scope",
            "expected_outcome",
            "expected_reason",
            "fixture_path",
            "fixture_fingerprint",
            "expected_path",
            "expected_fingerprint",
        ],
        {
            "case_id": nonempty,
            "primary_coverage_cell_id": nonempty,
            "pair_membership": {
                "oneOf": [
                    _closed_schema(
                        ["pair_id", "role"],
                        {"pair_id": nonempty, "role": {"enum": ["POSITIVE", "NEAR_MISS"]}},
                    ),
                    {"type": "null"},
                ]
            },
            "assertion_scope": {"enum": [item.value for item in HKEXPackageAssertionScope]},
            "expected_outcome": {"enum": [item.value for item in HKEXPackageIntegrityOutcome]},
            "expected_reason": {"enum": [item.value for item in HKEXPackageIntegrityReason]},
            "fixture_path": nonempty,
            "fixture_fingerprint": fingerprint_schema,
            "expected_path": nonempty,
            "expected_fingerprint": fingerprint_schema,
        },
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-package-integrity-catalogue.schema.json",
            "title": "HKEX package-integrity executable checkpoint catalogue",
            **_closed_schema(
                [
                    "schema_id",
                    "schema_version",
                    "catalogue_id",
                    "catalogue_version",
                    "status",
                    "case_count",
                    "primary_coverage_cell_count",
                    "high_risk_pair_ids",
                    "entries",
                    "checkpoint_complete",
                    "full_conformance_suite_complete",
                    "activation_authorized",
                    "external_effects",
                ],
                {
                    "schema_id": {"const": "asklegal.hk-regulatory.package-integrity-catalogue"},
                    "schema_version": {"const": HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION},
                    "catalogue_id": {"const": "hk-regulatory-package-integrity"},
                    "catalogue_version": {"const": "1.0.0"},
                    "status": {"const": "FROZEN_EXECUTABLE_CHECKPOINT"},
                    "case_count": {"const": HKEX_PACKAGE_INTEGRITY_CASE_COUNT},
                    "primary_coverage_cell_count": {"const": HKEX_PACKAGE_INTEGRITY_CASE_COUNT},
                    "high_risk_pair_ids": {
                        "type": "array",
                        "minItems": 7,
                        "maxItems": 7,
                        "items": nonempty,
                    },
                    "entries": {
                        "type": "array",
                        "minItems": HKEX_PACKAGE_INTEGRITY_CASE_COUNT,
                        "maxItems": HKEX_PACKAGE_INTEGRITY_CASE_COUNT,
                        "items": entry,
                    },
                    "checkpoint_complete": {"const": True},
                    "full_conformance_suite_complete": {"const": False},
                    "activation_authorized": {"const": False},
                    "external_effects": {"const": "NONE"},
                },
            ),
        }
    )


def _record_identity_result_schema_document(
    defs: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-record-identity-result.schema.json",
            "title": "HKEX Search Record identity and traceability decision",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "case_id",
                "contract_version",
                "rule_id",
                "decision_id",
                "consequence",
                "reason",
                "selected_search_record_id",
                "predecessor_search_record_ids",
                "candidate_serving_payload_fingerprint",
                "traceability_seed",
                "current_legal_support",
                "identity_decision_complete",
                "register_allocation_required",
                "selection_event_required",
                "search_record_authorized",
                "serving_ready",
            ],
            "$defs": defs,
            "properties": {
                "case_id": {"type": "string", "minLength": 1},
                "contract_version": {"const": HKEX_RECORD_IDENTITY_CONTRACT_VERSION},
                "rule_id": {"const": HKEX_RECORD_IDENTITY_RULE_ID},
                "decision_id": {"type": "string", "minLength": 1},
                "consequence": {
                    "enum": [
                        "PRESERVE_SELECTED",
                        "RESELECT_PRESERVED",
                        "REQUIRE_NEW_FORWARD_SUCCESSOR",
                        "REQUIRE_NEW_INITIAL",
                        "BLOCK",
                    ]
                },
                "reason": {
                    "enum": [
                        "EXACT_SELECTED_PAYLOAD_PRESERVED",
                        "EXACT_PRESERVED_PAYLOAD_RESELECTED",
                        "UNSEEN_INITIAL_PAYLOAD_REQUIRES_ID",
                        "UNSEEN_CHANGED_PAYLOAD_REQUIRES_SUCCESSOR",
                        "CURRENT_LEGAL_SUPPORT_NOT_PROVED",
                        "CONSTRUCTION_NOT_CURRENT_CANDIDATE",
                        "DECLARED_CHANGE_CONFLICTS_WITH_PAYLOAD",
                        "REQUIRED_EXACT_PRESERVED_PAYLOAD_MISSING",
                    ]
                },
                "selected_search_record_id": {
                    "oneOf": [
                        {
                            "type": "string",
                            "pattern": "^rec_[0-9a-f]{48}$",
                        },
                        {"type": "null"},
                    ]
                },
                "predecessor_search_record_ids": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "pattern": "^rec_[0-9a-f]{48}$",
                    },
                },
                "candidate_serving_payload_fingerprint": {
                    "oneOf": [
                        {"$ref": "#/$defs/fingerprint"},
                        {"type": "null"},
                    ]
                },
                "traceability_seed": {
                    "oneOf": [
                        {"$ref": "#/$defs/traceability_seed"},
                        {"type": "null"},
                    ]
                },
                "current_legal_support": {"type": "boolean"},
                "identity_decision_complete": {"type": "boolean"},
                "register_allocation_required": {"type": "boolean"},
                "selection_event_required": {"type": "boolean"},
                "search_record_authorized": {"const": False},
                "serving_ready": {"const": False},
            },
        }
    )


@dataclass(frozen=True, slots=True)
class _StateCaseSpec:
    """Independent facts and complete reference truth for one permanent row."""

    scope: HKEXStateAssertionScope
    facts: dict[str, JsonValue]
    expected: dict[str, JsonValue]


def _state_condition(
    condition_id: str,
    state: str,
) -> dict[str, JsonValue]:
    return {
        "condition_id": condition_id,
        "registered_source_id": f"registered-source-{condition_id}",
        "state": state,
        "evidence_refs": [f"evidence-{condition_id}"],
    }


def _state_request(  # noqa: PLR0913
    branch_id: str,
    *,
    cutoff: str = "2026-08-24T00:00:00+08:00",
    basis: str = "ORDINARY",
    effective_at: str | None = None,
    condition_operator: str | None = None,
    conditions: list[JsonValue] | None = None,
    transition_state: str = "ORDINARY",
    applicability_context: str | None = None,
    retirement_evidence: str = "NONE",
    predecessor_branch_id: str | None = None,
    successor_branch_ids: list[JsonValue] | None = None,
    reconciliation: str = "MATCH",
    uncertainty_codes: list[JsonValue] | None = None,
    source_failure_impact: str = "NONE",
    source_failure_choice: str = "NONE",
) -> dict[str, JsonValue]:
    """Build one strict source-neutral ADR 0071 request document."""
    return {
        "decision_id": f"decision-{branch_id}",
        "branch_id": branch_id,
        "component_id": "component-conformance",
        "scope_id": HKEX_MAIN_SCOPE_ID,
        "legal_location_id": f"location-{branch_id}",
        "cutoff": cutoff,
        "update_part_id": f"update-part-{branch_id}",
        "update_source_ranges": [f"evidence-update#{branch_id}"],
        "current_product_ranges": [f"evidence-current#{branch_id}"],
        "basis": basis,
        "finality": "FINAL_PUBLICATION_APPROVAL_INFERRED",
        "effective_at": effective_at,
        "condition_operator": condition_operator,
        "conditions": [] if conditions is None else conditions,
        "transition_state": transition_state,
        "applicability_context": applicability_context,
        "retirement_evidence": retirement_evidence,
        "predecessor_branch_id": predecessor_branch_id,
        "successor_branch_ids": [] if successor_branch_ids is None else successor_branch_ids,
        "current_product_reconciliation": reconciliation,
        "uncertainty_codes": [] if uncertainty_codes is None else uncertainty_codes,
        "source_failure_impact": source_failure_impact,
        "source_failure_choice": source_failure_choice,
        "source_rule_id": "HKREG-EFFECTIVE-STATE-001",
        "evidence_refs": [f"evidence-current-{branch_id}", f"evidence-update-{branch_id}"],
        "evidence_fingerprint": _SYNTHETIC_SOURCE_FINGERPRINT,
    }


def _state_facts(  # noqa: PLR0913
    branches: list[JsonValue],
    *,
    membership: str = "RULE_COMPONENT",
    complete_branch_set: bool = False,
    wording_relationship: str = "NOT_EVALUATED",
    limitation_metadata_complete: bool = False,
    effective_order_facts: list[JsonValue] | None = None,
    carry_forward_support: JsonValue = None,
    other_required_gates_passed: bool = True,
    repair_attempt: str = "NONE",
    unsupported_retirement_basis: str = "NONE",
) -> dict[str, JsonValue]:
    """Build one closed fact packet for the conformance wrapper."""
    return {
        "membership": membership,
        "branches": branches,
        "complete_branch_set": complete_branch_set,
        "wording_relationship": wording_relationship,
        "limitation_metadata_complete": limitation_metadata_complete,
        "effective_order_facts": ([] if effective_order_facts is None else effective_order_facts),
        "carry_forward_support": carry_forward_support,
        "other_required_gates_passed": other_required_gates_passed,
        "repair_attempt": repair_attempt,
        "unsupported_retirement_basis": unsupported_retirement_basis,
    }


def _state_branch_expected(
    branch_id: str,
    state: str,
    reason: str,
    *,
    applicability_context: str | None = None,
) -> dict[str, JsonValue]:
    """Return one explicit reference branch result independent of the runner."""
    if state in {"CURRENT", "TRANSITIONAL_CURRENT"}:
        disposition = "SEARCHABLE_CURRENT_RULE_COMPONENT"
        processing = "PASS"
    elif state in {"FUTURE_FIXED_DATE", "FUTURE_CONDITIONAL"}:
        disposition = "REGULATORY_WAITING_ROOM"
        processing = "PASS"
    elif state in {"SUPERSEDED", "WITHDRAWN"}:
        disposition = "HISTORICAL"
        processing = "PASS"
    elif state == "UNKNOWN":
        disposition = "QUARANTINE"
        processing = "QUARANTINE"
    else:
        raise _ConformanceBuildError(state)
    return {
        "branch_id": branch_id,
        "state": state,
        "disposition": disposition,
        "processing_outcome": processing,
        "reason": reason,
        "applicability_context": applicability_context,
    }


def _state_expected(  # noqa: PLR0913
    outcome: str,
    reason: str,
    branches: list[dict[str, JsonValue]] | None = None,
    *,
    not_applicable: bool = False,
    component_state: JsonValue = None,
    record_responsibility: str = "NONE",
    ordered_branch_ids: list[JsonValue] | None = None,
    source_failure_choice: str = "NONE",
    carry_forward_support: JsonValue = None,
    repair_rejected: bool = False,
) -> dict[str, JsonValue]:
    """Build the complete independently declared result body."""
    return {
        "outcome": outcome,
        "reason": reason,
        "not_applicable": not_applicable,
        "branch_decisions": (
            [] if branches is None else [checked_json_value(item) for item in branches]
        ),
        "component_state": component_state,
        "record_responsibility": record_responsibility,
        "ordered_branch_ids": [] if ordered_branch_ids is None else ordered_branch_ids,
        "source_failure_choice": source_failure_choice,
        "carry_forward_support": carry_forward_support,
        "rebuild_target_authorized": False,
        "repair_rejected": repair_rejected,
        "search_record_authorized": False,
        "embedding_authorized": False,
        "release_authorized": False,
        "serving_authorized": False,
        "external_effects": "NONE",
    }


def _atomic_spec(
    request: dict[str, JsonValue],
    state: str,
    branch_reason: str,
    *,
    outcome: str | None = None,
    facts_changes: dict[str, JsonValue] | None = None,
) -> _StateCaseSpec:
    """Build one atomic-state spec with explicit reference truth."""
    resolved_outcome = "QUARANTINE" if state == "UNKNOWN" and outcome is None else outcome or "PASS"
    facts = _state_facts([request])
    if facts_changes:
        facts.update(facts_changes)
    return _StateCaseSpec(
        HKEXStateAssertionScope.ATOMIC_STATE,
        facts,
        _state_expected(
            resolved_outcome,
            "ATOMIC_STATE_DECIDED",
            [
                _state_branch_expected(
                    str(request["branch_id"]),
                    state,
                    branch_reason,
                    applicability_context=(
                        None
                        if request["applicability_context"] is None
                        else str(request["applicability_context"])
                    ),
                )
            ],
            source_failure_choice=str(request["source_failure_choice"]),
        ),
    )


def _component_spec(
    requests: list[dict[str, JsonValue]],
    states: list[tuple[str, str]],
    component_state: str,
) -> _StateCaseSpec:
    branches = [
        _state_branch_expected(
            str(request["branch_id"]),
            state,
            reason,
            applicability_context=(
                None
                if request["applicability_context"] is None
                else str(request["applicability_context"])
            ),
        )
        for request, (state, reason) in zip(requests, states, strict=True)
    ]
    return _StateCaseSpec(
        HKEXStateAssertionScope.COMPONENT_SUMMARY,
        _state_facts(list(requests), complete_branch_set=True),
        _state_expected(
            "QUARANTINE" if component_state == "UNKNOWN" else "PASS",
            "COMPONENT_SUMMARIZED",
            branches,
            component_state=component_state,
        ),
    )


def _state_case_specs() -> tuple[_StateCaseSpec, ...]:  # noqa: PLR0915
    """Declare all 51 permanent state rows without selecting by case ID."""
    current_reason = "CURRENT_PRODUCT_MATCHED"
    transition_reason = "TRANSITIONAL_CURRENT_PRODUCT_MATCHED"
    future_fixed_reason = "FUTURE_FIXED_DATE_PENDING"
    future_conditional_reason = "FUTURE_CONDITION_PROVED_UNMET"
    unknown_fact_reason = "UNRESOLVED_LEGAL_STATE_FACT"
    condition_unknown_reason = "CONDITION_EVIDENCE_UNRESOLVED"

    def current(branch: str) -> dict[str, JsonValue]:
        return _state_request(branch)

    def limited(branch: str) -> dict[str, JsonValue]:
        return _state_request(
            branch,
            transition_state="MATERIALLY_LIMITED_CURRENT",
            applicability_context="Transactions entered before 2026-08-01",
        )

    def future_fixed(branch: str) -> dict[str, JsonValue]:
        return _state_request(branch, basis="FIXED_DATE", effective_at="2026-09-01")

    def future_conditional(branch: str) -> dict[str, JsonValue]:
        return _state_request(
            branch,
            basis="CONDITIONAL",
            condition_operator="ALL_OF",
            conditions=[_state_condition(f"condition-{branch}", "NOT_OCCURRED_FRESH")],
        )

    def complete_successor(branch: str) -> dict[str, JsonValue]:
        return _state_request(
            branch,
            transition_state="PROVED_ENDED",
            retirement_evidence="COMPLETE_SUCCESSOR",
            successor_branch_ids=[f"successor-{branch}"],
        )

    def withdrawn(branch: str) -> dict[str, JsonValue]:
        return _state_request(
            branch,
            transition_state="PROVED_ENDED",
            retirement_evidence="OFFICIAL_WITHDRAWAL_NO_SUCCESSOR",
        )

    r001 = current("branch-001")
    r002 = limited("branch-002")
    r003 = future_fixed("branch-003")
    r004 = future_conditional("branch-004")
    r005 = complete_successor("branch-005")
    r006 = withdrawn("branch-006")
    r007 = _state_request("branch-007", reconciliation="CONFLICT")
    r009 = current("branch-009")
    r010 = limited("branch-010")
    r011a = current("branch-011-predecessor")
    r011b = future_fixed("branch-011-amendment")
    r012 = future_fixed("branch-012")
    r013 = future_conditional("branch-013")
    r014a = complete_successor("branch-014-a")
    r014b = complete_successor("branch-014-b")
    r015a = withdrawn("branch-015-a")
    r015b = withdrawn("branch-015-b")
    r016a = current("branch-016-current")
    r016b = _state_request("branch-016-unknown", uncertainty_codes=["CONFLICTING_EFFECTIVE_FACTS"])
    r017a = future_fixed("branch-017-fixed")
    r017b = future_conditional("branch-017-conditional")
    r018 = _state_request(
        "branch-018",
        cutoff="2026-08-23T23:59:59+08:00",
        basis="FIXED_DATE",
        effective_at="2026-08-24T00:00:00+08:00",
    )
    r019 = _state_request(
        "branch-019",
        basis="FIXED_DATE",
        effective_at="2026-08-24T00:00:00+08:00",
    )
    r020 = _state_request(
        "branch-020",
        basis="FIXED_DATE",
        effective_at="2026-08-20",
        reconciliation="CONFLICT",
    )
    r021 = future_fixed("branch-021")
    r022 = _state_request("branch-022", uncertainty_codes=["EFFECTIVE_TIME_AMBIGUOUS"])
    r023 = _state_request(
        "branch-023",
        cutoff="2026-08-24T06:00:00+08:00",
        basis="FIXED_DATE",
        effective_at="2026-08-23T18:00:00-04:00",
    )
    r024a = _state_request("branch-024-a", basis="FIXED_DATE", effective_at="2026-08-20")
    r024b = future_fixed("branch-024-b")
    r024c = _state_request("branch-024-c", basis="FIXED_DATE", effective_at="2026-10-01")
    r025a = future_fixed("branch-025-fixed")
    r025b = future_conditional("branch-025-conditional")
    r026 = _state_request(
        "branch-026",
        basis="CONDITIONAL",
        condition_operator="ALL_OF",
        conditions=[_state_condition("external-trigger-026", "UNRESOLVED")],
    )
    r027 = _state_request(
        "branch-027",
        basis="CONDITIONAL",
        condition_operator="ALL_OF",
        conditions=[_state_condition("external-trigger-027", "OCCURRED")],
    )
    r028 = _state_request(
        "branch-028",
        basis="CONDITIONAL",
        condition_operator="ALL_OF",
        conditions=[_state_condition("external-trigger-028", "OCCURRED")],
        reconciliation="CONFLICT",
    )
    r029 = _state_request(
        "branch-029",
        basis="CONDITIONAL",
        condition_operator="ALL_OF",
        conditions=[_state_condition("stale-trigger-029", "UNRESOLVED")],
    )
    r030 = _state_request(
        "branch-030",
        basis="CONDITIONAL",
        condition_operator="ALL_OF",
        conditions=[
            _state_condition("all-a-030", "OCCURRED"),
            _state_condition("all-b-030", "OCCURRED"),
        ],
    )
    r031 = _state_request(
        "branch-031",
        basis="CONDITIONAL",
        condition_operator="ALL_OF",
        conditions=[
            _state_condition("all-a-031", "OCCURRED"),
            _state_condition("all-b-031", "NOT_OCCURRED_FRESH"),
        ],
    )
    r032 = _state_request(
        "branch-032",
        basis="CONDITIONAL",
        condition_operator="ALL_OF",
        conditions=[
            _state_condition("all-a-032", "OCCURRED"),
            _state_condition("all-b-032", "UNRESOLVED"),
        ],
    )
    r033 = _state_request(
        "branch-033",
        basis="CONDITIONAL",
        condition_operator="ANY_OF",
        conditions=[
            _state_condition("any-a-033", "UNRESOLVED"),
            _state_condition("any-b-033", "OCCURRED"),
        ],
    )
    r034 = _state_request(
        "branch-034",
        basis="CONDITIONAL",
        condition_operator="ANY_OF",
        conditions=[
            _state_condition("any-a-034", "NOT_OCCURRED_FRESH"),
            _state_condition("any-b-034", "NOT_OCCURRED_FRESH"),
        ],
    )
    r035 = _state_request(
        "branch-035",
        basis="CONDITIONAL",
        condition_operator="ANY_OF",
        conditions=[
            _state_condition("any-a-035", "NOT_OCCURRED_FRESH"),
            _state_condition("any-b-035", "UNRESOLVED"),
        ],
    )
    r036a = limited("branch-036-old")
    r036b = _state_request(
        "branch-036-new",
        transition_state="MATERIALLY_LIMITED_CURRENT",
        applicability_context="Transactions entered on or after 2026-08-01",
    )
    r037a = limited("branch-037-old")
    r037b = _state_request(
        "branch-037-new",
        transition_state="MATERIALLY_LIMITED_CURRENT",
        applicability_context="Transactions entered on or after 2026-08-01",
    )
    r038 = limited("branch-038")
    r039 = limited("branch-039")
    r040 = complete_successor("branch-040")
    r041 = withdrawn("branch-041")
    r042 = _state_request(
        "branch-042",
        retirement_evidence="PARTIAL_SUCCESSOR",
        successor_branch_ids=["successor-branch-042"],
        applicability_context="Former applications not covered by the successor",
    )
    r043a = _state_request("branch-043-a", basis="FIXED_DATE", effective_at="2026-08-01")
    r043b = _state_request("branch-043-b", basis="FIXED_DATE", effective_at="2026-08-10")
    r043c = _state_request("branch-043-c", basis="FIXED_DATE", effective_at="2026-08-05")
    r044 = _state_request("branch-044", uncertainty_codes=["BRANCH_COLLISION_OR_GAP"])
    r045 = _state_request("branch-045", retirement_evidence="DISAPPEARANCE_ONLY")
    r046 = _state_request("branch-046", transition_state="PROVED_ENDED")
    r047 = _state_request(
        "branch-047",
        source_failure_impact="COULD_CHANGE_CURRENT",
        source_failure_choice="CARRY_FORWARD_LAST_APPROVED",
    )
    r048 = _state_request(
        "branch-048",
        source_failure_impact="COULD_CHANGE_CURRENT",
        source_failure_choice="WITHHOLD",
    )
    r049 = _state_request(
        "branch-049",
        source_failure_impact="COULD_CHANGE_CURRENT",
        source_failure_choice="NO_REBUILD",
    )
    r050 = current("branch-050")
    r051 = _state_request("branch-051", reconciliation="CONFLICT")

    support: dict[str, JsonValue] = {
        "last_approved_status": "APPROVED_CURRENT",
        "last_verified_at": "2026-08-23T18:00:00+08:00",
        "coverage_gap_id": "coverage-gap-047",
        "warning_code": "LAST_APPROVED_NOT_FRESH",
        "next_due_at": "2026-08-24T06:00:00+08:00",
        "support_ref": "evidence:last-approved-047",
    }
    specs = (
        _atomic_spec(r001, "CURRENT", current_reason),
        _atomic_spec(r002, "TRANSITIONAL_CURRENT", transition_reason),
        _atomic_spec(r003, "FUTURE_FIXED_DATE", future_fixed_reason),
        _atomic_spec(r004, "FUTURE_CONDITIONAL", future_conditional_reason),
        _atomic_spec(r005, "SUPERSEDED", "COMPLETE_SUCCESSOR_PROVED"),
        _atomic_spec(r006, "WITHDRAWN", "WITHDRAWAL_WITHOUT_SUCCESSOR_PROVED"),
        _atomic_spec(r007, "UNKNOWN", "CURRENT_PRODUCT_CONFLICT"),
        _StateCaseSpec(
            HKEXStateAssertionScope.ATOMIC_STATE,
            _state_facts([], membership="EXCLUDED_NON_RULE"),
            _state_expected("PASS", "NON_RULE_NOT_APPLICABLE", not_applicable=True),
        ),
        _component_spec([r009], [("CURRENT", current_reason)], "CURRENT"),
        _component_spec(
            [r010],
            [("TRANSITIONAL_CURRENT", transition_reason)],
            "TRANSITIONAL_CURRENT",
        ),
        _component_spec(
            [r011a, r011b],
            [("CURRENT", current_reason), ("FUTURE_FIXED_DATE", future_fixed_reason)],
            "CURRENT",
        ),
        _component_spec([r012], [("FUTURE_FIXED_DATE", future_fixed_reason)], "FUTURE_FIXED_DATE"),
        _component_spec(
            [r013],
            [("FUTURE_CONDITIONAL", future_conditional_reason)],
            "FUTURE_CONDITIONAL",
        ),
        _component_spec(
            [r014a, r014b],
            [("SUPERSEDED", "COMPLETE_SUCCESSOR_PROVED")] * 2,
            "SUPERSEDED",
        ),
        _component_spec(
            [r015a, r015b],
            [("WITHDRAWN", "WITHDRAWAL_WITHOUT_SUCCESSOR_PROVED")] * 2,
            "WITHDRAWN",
        ),
        _component_spec(
            [r016a, r016b],
            [("CURRENT", current_reason), ("UNKNOWN", unknown_fact_reason)],
            "UNKNOWN",
        ),
        _component_spec(
            [r017a, r017b],
            [
                ("FUTURE_FIXED_DATE", future_fixed_reason),
                ("FUTURE_CONDITIONAL", future_conditional_reason),
            ],
            "UNKNOWN",
        ),
        _atomic_spec(r018, "FUTURE_FIXED_DATE", future_fixed_reason),
        _atomic_spec(r019, "CURRENT", current_reason),
        _atomic_spec(r020, "UNKNOWN", "CURRENT_PRODUCT_CONFLICT"),
        _atomic_spec(r021, "FUTURE_FIXED_DATE", future_fixed_reason),
        _atomic_spec(r022, "UNKNOWN", unknown_fact_reason),
        _atomic_spec(r023, "CURRENT", current_reason),
        _StateCaseSpec(
            HKEXStateAssertionScope.BRANCH_SET,
            _state_facts([r024a, r024b, r024c], complete_branch_set=True),
            _state_expected(
                "PASS",
                "COMPLETE_BRANCH_SET_PRESERVED",
                [
                    _state_branch_expected("branch-024-a", "CURRENT", current_reason),
                    _state_branch_expected(
                        "branch-024-b", "FUTURE_FIXED_DATE", future_fixed_reason
                    ),
                    _state_branch_expected(
                        "branch-024-c", "FUTURE_FIXED_DATE", future_fixed_reason
                    ),
                ],
            ),
        ),
        _StateCaseSpec(
            HKEXStateAssertionScope.BRANCH_SET,
            _state_facts([r025a, r025b], complete_branch_set=True),
            _state_expected(
                "PASS",
                "COMPLETE_BRANCH_SET_PRESERVED",
                [
                    _state_branch_expected(
                        "branch-025-fixed", "FUTURE_FIXED_DATE", future_fixed_reason
                    ),
                    _state_branch_expected(
                        "branch-025-conditional",
                        "FUTURE_CONDITIONAL",
                        future_conditional_reason,
                    ),
                ],
            ),
        ),
        _atomic_spec(r026, "UNKNOWN", condition_unknown_reason),
        _atomic_spec(r027, "CURRENT", current_reason),
        _atomic_spec(r028, "UNKNOWN", "CURRENT_PRODUCT_CONFLICT"),
        _atomic_spec(r029, "UNKNOWN", condition_unknown_reason),
        _atomic_spec(r030, "CURRENT", current_reason),
        _atomic_spec(r031, "FUTURE_CONDITIONAL", future_conditional_reason),
        _atomic_spec(r032, "UNKNOWN", condition_unknown_reason),
        _atomic_spec(r033, "CURRENT", current_reason),
        _atomic_spec(r034, "FUTURE_CONDITIONAL", future_conditional_reason),
        _atomic_spec(r035, "UNKNOWN", condition_unknown_reason),
        _component_spec(
            [r036a, r036b],
            [("TRANSITIONAL_CURRENT", transition_reason)] * 2,
            "TRANSITIONAL_CURRENT",
        ),
        _StateCaseSpec(
            HKEXStateAssertionScope.RECORD_RESPONSIBILITY,
            _state_facts([r037a, r037b], wording_relationship="MATERIAL_DIFFERENCE"),
            _state_expected(
                "PASS",
                "SEPARATE_COMPLETE_RECORDS_REQUIRED",
                [
                    _state_branch_expected(
                        "branch-037-old",
                        "TRANSITIONAL_CURRENT",
                        transition_reason,
                        applicability_context="Transactions entered before 2026-08-01",
                    ),
                    _state_branch_expected(
                        "branch-037-new",
                        "TRANSITIONAL_CURRENT",
                        transition_reason,
                        applicability_context="Transactions entered on or after 2026-08-01",
                    ),
                ],
                record_responsibility="SEPARATE_COMPLETE_RECORDS",
            ),
        ),
        _StateCaseSpec(
            HKEXStateAssertionScope.RECORD_RESPONSIBILITY,
            _state_facts(
                [r038],
                wording_relationship="SAME_WORDING",
                limitation_metadata_complete=True,
            ),
            _state_expected(
                "PASS",
                "ONE_LIMITED_RECORD_ELIGIBLE",
                [
                    _state_branch_expected(
                        "branch-038",
                        "TRANSITIONAL_CURRENT",
                        transition_reason,
                        applicability_context="Transactions entered before 2026-08-01",
                    )
                ],
                record_responsibility="ONE_LIMITED_RECORD_ELIGIBLE",
            ),
        ),
        _atomic_spec(r039, "TRANSITIONAL_CURRENT", transition_reason),
        _atomic_spec(r040, "SUPERSEDED", "COMPLETE_SUCCESSOR_PROVED"),
        _atomic_spec(r041, "WITHDRAWN", "WITHDRAWAL_WITHOUT_SUCCESSOR_PROVED"),
        _atomic_spec(r042, "TRANSITIONAL_CURRENT", transition_reason),
        _StateCaseSpec(
            HKEXStateAssertionScope.EFFECTIVE_ORDER,
            _state_facts(
                [r043a, r043b, r043c],
                effective_order_facts=[
                    {
                        "branch_id": "branch-043-a",
                        "supported_effective_at": "2026-08-01T00:00:00+08:00",
                        "update_number": 200,
                    },
                    {
                        "branch_id": "branch-043-b",
                        "supported_effective_at": "2026-08-10T00:00:00+08:00",
                        "update_number": 100,
                    },
                    {
                        "branch_id": "branch-043-c",
                        "supported_effective_at": "2026-08-05T00:00:00+08:00",
                        "update_number": 300,
                    },
                ],
            ),
            _state_expected(
                "PASS",
                "EFFECTIVE_FACT_ORDER_APPLIED",
                [
                    _state_branch_expected("branch-043-a", "CURRENT", current_reason),
                    _state_branch_expected("branch-043-b", "CURRENT", current_reason),
                    _state_branch_expected("branch-043-c", "CURRENT", current_reason),
                ],
                ordered_branch_ids=["branch-043-a", "branch-043-c", "branch-043-b"],
            ),
        ),
        _atomic_spec(r044, "UNKNOWN", unknown_fact_reason),
        _atomic_spec(r045, "UNKNOWN", "RETIREMENT_EVIDENCE_INSUFFICIENT"),
        _atomic_spec(
            r046,
            "UNKNOWN",
            "TRANSITION_END_UNRESOLVED",
            facts_changes={
                "unsupported_retirement_basis": ("SIMILARITY_REUSED_NUMBER_OR_HIGHER_UPDATE")
            },
        ),
        _StateCaseSpec(
            HKEXStateAssertionScope.SOURCE_FAILURE,
            _state_facts([r047], carry_forward_support=support),
            _state_expected(
                "PASS",
                "LAST_APPROVED_CARRY_FORWARD",
                [
                    _state_branch_expected(
                        "branch-047", "UNKNOWN", "SOURCE_FAILURE_COULD_CHANGE_CURRENT"
                    )
                ],
                source_failure_choice="CARRY_FORWARD_LAST_APPROVED",
                carry_forward_support=support,
            ),
        ),
        _StateCaseSpec(
            HKEXStateAssertionScope.SOURCE_FAILURE,
            _state_facts([r048]),
            _state_expected(
                "BLOCK",
                "AFFECTED_RECORDS_WITHHELD",
                [
                    _state_branch_expected(
                        "branch-048", "UNKNOWN", "SOURCE_FAILURE_COULD_CHANGE_CURRENT"
                    )
                ],
                source_failure_choice="WITHHOLD",
            ),
        ),
        _StateCaseSpec(
            HKEXStateAssertionScope.SOURCE_FAILURE,
            _state_facts([r049]),
            _state_expected(
                "BLOCK",
                "NO_NEW_TARGET",
                [
                    _state_branch_expected(
                        "branch-049", "UNKNOWN", "SOURCE_FAILURE_COULD_CHANGE_CURRENT"
                    )
                ],
                source_failure_choice="NO_REBUILD",
            ),
        ),
        _StateCaseSpec(
            HKEXStateAssertionScope.DOWNSTREAM_GATE,
            _state_facts([r050], other_required_gates_passed=False),
            _state_expected(
                "BLOCK",
                "OTHER_REQUIRED_GATE_FAILED",
                [_state_branch_expected("branch-050", "CURRENT", current_reason)],
            ),
        ),
        _StateCaseSpec(
            HKEXStateAssertionScope.UNKNOWN_REPAIR,
            _state_facts([r051], repair_attempt="AUTHORITY_NOTE"),
            _state_expected(
                "QUARANTINE",
                "UNKNOWN_REPAIR_REJECTED",
                [_state_branch_expected("branch-051", "UNKNOWN", "CURRENT_PRODUCT_CONFLICT")],
                repair_rejected=True,
            ),
        ),
    )
    if len(specs) != HKEX_STATE_DECISION_CASE_COUNT:
        raise _ConformanceBuildError
    return specs


def _state_contract_bindings(
    universe_fingerprint: str,
) -> list[JsonValue]:
    seed = _json_object(
        {
            "contract_id": "asklegal.hk-regulatory.state-decision-case",
            "contract_version": HKEX_STATE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_STATE_DECISION_RULE_ID,
        }
    )
    return [
        {
            "contract_id": "asklegal.hk-regulatory.conformance-universe",
            "version": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
            "fingerprint": universe_fingerprint,
        },
        {
            "contract_id": "asklegal.hk-regulatory.state-decision-case",
            "version": HKEX_STATE_DECISION_CONTRACT_VERSION,
            "fingerprint": _fingerprint(rfc8785.dumps(seed)),
        },
    ]


def _state_expected_document(
    case_id: str,
    expected: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.state-decision-result",
            "schema_version": HKEX_STATE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_STATE_DECISION_RULE_ID,
            "case_id": case_id,
            **deepcopy(expected),
        }
    )


def build_state_decision_cases() -> tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...]:
    """Build all 51 permanent effective-state cases and frozen reports."""
    universe = build_conformance_universe()
    all_cases = _json_array(universe["cases"])
    start = HKEX_SOURCE_DECISION_CASE_COUNT
    universe_cases = tuple(
        _json_object(item) for item in all_cases[start : start + HKEX_STATE_DECISION_CASE_COUNT]
    )
    specs = _state_case_specs()
    universe_fingerprint = _fingerprint(rfc8785.dumps(universe))
    bindings = _state_contract_bindings(universe_fingerprint)
    results: list[tuple[dict[str, JsonValue], dict[str, JsonValue]]] = []
    for universe_case, spec in zip(universe_cases, specs, strict=True):
        case_id = str(universe_case["case_id"])
        facts = deepcopy(spec.facts)
        expected = _state_expected_document(case_id, spec.expected)
        fixture = _json_object(
            {
                "schema_id": "asklegal.hk-regulatory.state-decision-case",
                "schema_version": HKEX_STATE_DECISION_CONTRACT_VERSION,
                "package_contract_version": "1.0.0",
                "case_id": case_id,
                "suite_layer": "EVIDENCE_TO_DECISION",
                "primary_checkpoint": "EFFECTIVE_STATE",
                "frozen": True,
                "synthetic_evidence_class": "SYNTHETIC_NO_REAL_AUTHORITY",
                "contract_bindings": deepcopy(bindings),
                "synthetic_cutoff": "2026-08-24T00:00:00Z",
                "scope_id": "HKEX_CROSS_BOARD",
                "prior_state": "SYNTHETIC_ACCEPTED_PREDECESSOR",
                "primary_coverage_cell_ids": [universe_case["coverage_cell_id"]],
                "secondary_coverage_cell_ids": [],
                "pair_memberships": deepcopy(universe_case["pair_memberships"]),
                "declared_input_inventory": ["state-evidence"],
                "declared_reference_inventory": [
                    "asklegal.hk-regulatory.conformance-universe",
                    "asklegal.hk-regulatory.state-decision-case",
                ],
                "declared_expected_inventory": ["STATE_DECISION_REPORT"],
                "assertion_scope": spec.scope.value,
                "required_result_dimensions": [
                    "APPLICABILITY",
                    "BRANCH_STATE",
                    "COMPONENT_STATE",
                    "PROCESSING",
                    "RECORD_RESPONSIBILITY",
                    "SOURCE_FAILURE",
                ],
                "evidence_packet_fields": sorted(facts),
                "supporting_evidence_ranges": [f"input/{case_id}-state-evidence.json#facts"],
                "rule_trace": [
                    "HKREG-EFFECTIVE-STATE-001",
                    HKEX_STATE_DECISION_RULE_ID,
                ],
                "established_facts": ["SYNTHETIC_STATE_FACT_PACKET_DECLARED"],
                "unresolved_facts": (
                    [str(spec.expected["reason"])]
                    if spec.expected["outcome"] in {"BLOCK", "QUARANTINE"}
                    else []
                ),
                "permitted_equivalent_results": [],
                "critical_error_codes": (
                    [str(spec.expected["reason"])]
                    if case_id
                    in {
                        "HKREG-DEC-STA-020",
                        "HKREG-DEC-STA-028",
                        "HKREG-DEC-STA-044",
                        "HKREG-DEC-STA-045",
                        "HKREG-DEC-STA-046",
                        "HKREG-DEC-STA-051",
                    }
                    else []
                ),
                "package_fingerprint": universe_fingerprint,
                "title": universe_case["synthetic_scenario"],
                "purpose": universe_case["exact_required_result"],
                "expected_decision": expected,
                "evidence_packet": {
                    "slot_id": "state-evidence",
                    "state": "AVAILABLE",
                    "path": f"input/{case_id}-state-evidence.json",
                    "role": "ORDINARY",
                    "media_type": "application/json",
                    "content_fingerprint": _fingerprint(rfc8785.dumps(facts)),
                },
                "facts": facts,
                "case_fingerprint": "PENDING",
            }
        )
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        parsed = hkex_state_decision_case_from_document(fixture)
        report = _json_object(run_hkex_state_case(parsed).document())
        if report["conformance_status"] != "PASS":
            failure = f"{case_id}:{spec.expected['reason']}"
            raise _ConformanceBuildError(failure)
        results.append((fixture, report))
    if len(results) != HKEX_STATE_DECISION_CASE_COUNT:
        raise _ConformanceBuildError
    return tuple(results)


def build_state_decision_catalogue(
    cases: tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...],
) -> dict[str, JsonValue]:
    """Bind all 51 exact state case packets and reports."""
    entries: list[JsonValue] = []
    pair_ids: set[str] = set()
    for fixture, report in cases:
        case_id = str(fixture["case_id"])
        fixture_path = f"fixtures/conformance/state-decision/{case_id}.json"
        expected_path = f"expected/conformance/state-decision/{case_id}.json"
        expected = _json_object(fixture["expected_decision"])
        memberships = deepcopy(_json_array(fixture["pair_memberships"]))
        for membership in memberships:
            pair_ids.add(str(_json_object(membership)["pair_id"]))
        entries.append(
            {
                "case_id": case_id,
                "primary_coverage_cell_id": _json_array(fixture["primary_coverage_cell_ids"])[0],
                "pair_memberships": memberships,
                "assertion_scope": fixture["assertion_scope"],
                "expected_outcome": expected["outcome"],
                "expected_reason": expected["reason"],
                "fixture_path": fixture_path,
                "fixture_fingerprint": _fingerprint(
                    (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode()
                ),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint(
                    (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
                ),
            }
        )
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.state-decision-catalogue",
            "schema_version": HKEX_STATE_DECISION_CONTRACT_VERSION,
            "catalogue_id": "hk-regulatory-state-decision",
            "catalogue_version": "1.0.0",
            "status": "FROZEN_EXECUTABLE_CHECKPOINT",
            "case_count": HKEX_STATE_DECISION_CASE_COUNT,
            "primary_coverage_cell_count": HKEX_STATE_DECISION_CASE_COUNT,
            "high_risk_pair_ids": sorted(pair_ids),
            "entries": entries,
            "checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "activation_authorized": False,
            "external_effects": "NONE",
        }
    )


def _state_request_schema() -> dict[str, JsonValue]:
    nonempty = {"type": "string", "minLength": 1}
    string_array = {
        "type": "array",
        "uniqueItems": True,
        "items": nonempty,
    }
    condition = _closed_schema(
        ["condition_id", "registered_source_id", "state", "evidence_refs"],
        _json_object(
            {
                "condition_id": nonempty,
                "registered_source_id": nonempty,
                "state": {"enum": ["OCCURRED", "NOT_OCCURRED_FRESH", "UNRESOLVED"]},
                "evidence_refs": string_array,
            }
        ),
    )
    properties: dict[str, object] = {
        "decision_id": nonempty,
        "branch_id": nonempty,
        "component_id": nonempty,
        "scope_id": {"enum": [HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]},
        "legal_location_id": nonempty,
        "cutoff": {"type": "string", "format": "date-time"},
        "update_part_id": nonempty,
        "update_source_ranges": string_array,
        "current_product_ranges": string_array,
        "basis": {"enum": ["ORDINARY", "FIXED_DATE", "CONDITIONAL"]},
        "finality": {
            "enum": [
                "FINAL_PUBLICATION_APPROVAL_INFERRED",
                "FINAL_DIRECT_APPROVAL_PROVED",
                "CONSULTATION_OR_PROPOSAL",
                "APPROVAL_PENDING",
                "DIRECT_APPROVAL_REQUIRED_MISSING",
                "CONFLICTING",
            ]
        },
        "effective_at": {"type": ["string", "null"]},
        "condition_operator": {"enum": [None, "ALL_OF", "ANY_OF"]},
        "conditions": {"type": "array", "uniqueItems": True, "items": condition},
        "transition_state": {"enum": ["ORDINARY", "MATERIALLY_LIMITED_CURRENT", "PROVED_ENDED"]},
        "applicability_context": {"type": ["string", "null"]},
        "retirement_evidence": {
            "enum": [
                "NONE",
                "COMPLETE_SUCCESSOR",
                "PARTIAL_SUCCESSOR",
                "OFFICIAL_WITHDRAWAL_NO_SUCCESSOR",
                "DISAPPEARANCE_ONLY",
                "CONFLICTING",
            ]
        },
        "predecessor_branch_id": {"type": ["string", "null"]},
        "successor_branch_ids": string_array,
        "current_product_reconciliation": {
            "enum": ["MATCH", "CONFLICT", "MISSING_STALE_OR_INCOMPLETE", "NOT_YET_REQUIRED"]
        },
        "uncertainty_codes": string_array,
        "source_failure_impact": {"enum": ["NONE", "COULD_CHANGE_CURRENT"]},
        "source_failure_choice": {
            "enum": ["NONE", "CARRY_FORWARD_LAST_APPROVED", "WITHHOLD", "NO_REBUILD"]
        },
        "source_rule_id": {"const": "HKREG-EFFECTIVE-STATE-001"},
        "evidence_refs": string_array,
        "evidence_fingerprint": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    }
    return _closed_schema(sorted(properties), _json_object(properties))


def _state_carry_schema() -> dict[str, JsonValue]:
    nonempty = {"type": "string", "minLength": 1}
    return _closed_schema(
        [
            "last_approved_status",
            "last_verified_at",
            "coverage_gap_id",
            "warning_code",
            "next_due_at",
            "support_ref",
        ],
        _json_object(
            {
                "last_approved_status": nonempty,
                "last_verified_at": {"type": "string", "format": "date-time"},
                "coverage_gap_id": nonempty,
                "warning_code": nonempty,
                "next_due_at": {"type": ["string", "null"]},
                "support_ref": nonempty,
            }
        ),
    )


def _state_result_schema() -> dict[str, JsonValue]:
    branch = _closed_schema(
        [
            "branch_id",
            "state",
            "disposition",
            "processing_outcome",
            "reason",
            "applicability_context",
        ],
        _json_object(
            {
                "branch_id": {"type": "string", "minLength": 1},
                "state": {
                    "enum": [
                        "CURRENT",
                        "TRANSITIONAL_CURRENT",
                        "FUTURE_FIXED_DATE",
                        "FUTURE_CONDITIONAL",
                        "SUPERSEDED",
                        "WITHDRAWN",
                        "UNKNOWN",
                    ]
                },
                "disposition": {
                    "enum": [
                        "SEARCHABLE_CURRENT_RULE_COMPONENT",
                        "REGULATORY_WAITING_ROOM",
                        "HISTORICAL",
                        "QUARANTINE",
                    ]
                },
                "processing_outcome": {"enum": ["PASS", "BLOCK", "QUARANTINE"]},
                "reason": {"type": "string", "minLength": 1},
                "applicability_context": {"type": ["string", "null"]},
            }
        ),
    )
    required = [
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
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.state-decision-result"},
            "schema_version": {"const": HKEX_STATE_DECISION_CONTRACT_VERSION},
            "rule_id": {"const": HKEX_STATE_DECISION_RULE_ID},
            "case_id": {"type": "string", "pattern": "^HKREG-DEC-STA-(0[0-4][0-9]|05[01])$"},
            "outcome": {"enum": [item.value for item in HKEXStateConformanceOutcome]},
            "reason": {"enum": [item.value for item in HKEXStateDecisionReason]},
            "not_applicable": {"type": "boolean"},
            "branch_decisions": {"type": "array", "uniqueItems": True, "items": branch},
            "component_state": {
                "enum": [
                    None,
                    "CURRENT",
                    "TRANSITIONAL_CURRENT",
                    "FUTURE_FIXED_DATE",
                    "FUTURE_CONDITIONAL",
                    "SUPERSEDED",
                    "WITHDRAWN",
                    "UNKNOWN",
                ]
            },
            "record_responsibility": {"enum": [item.value for item in HKEXRecordResponsibility]},
            "ordered_branch_ids": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
            },
            "source_failure_choice": {
                "enum": ["NONE", "CARRY_FORWARD_LAST_APPROVED", "WITHHOLD", "NO_REBUILD"]
            },
            "carry_forward_support": {"oneOf": [{"type": "null"}, _state_carry_schema()]},
            "rebuild_target_authorized": {"const": False},
            "repair_rejected": {"type": "boolean"},
            "search_record_authorized": {"const": False},
            "embedding_authorized": {"const": False},
            "release_authorized": {"const": False},
            "serving_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _closed_schema(required, properties)


def _state_facts_schema() -> dict[str, JsonValue]:
    order_fact = _closed_schema(
        ["branch_id", "supported_effective_at", "update_number"],
        _json_object(
            {
                "branch_id": {"type": "string", "minLength": 1},
                "supported_effective_at": {"type": "string", "format": "date-time"},
                "update_number": {"type": "integer", "minimum": 0},
            }
        ),
    )
    return _closed_schema(
        sorted(
            [
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
            ]
        ),
        _json_object(
            {
                "membership": {"enum": [item.value for item in HKEXMembership]},
                "branches": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": _state_request_schema(),
                },
                "complete_branch_set": {"type": "boolean"},
                "wording_relationship": {"enum": [item.value for item in HKEXWordingRelationship]},
                "limitation_metadata_complete": {"type": "boolean"},
                "effective_order_facts": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": order_fact,
                },
                "carry_forward_support": {"oneOf": [{"type": "null"}, _state_carry_schema()]},
                "other_required_gates_passed": {"type": "boolean"},
                "repair_attempt": {"enum": [item.value for item in HKEXRepairAttempt]},
                "unsupported_retirement_basis": {
                    "enum": [item.value for item in HKEXUnsupportedRetirementBasis]
                },
            }
        ),
    )


def build_state_decision_case_schema() -> dict[str, JsonValue]:
    """Build the strict ADR 0074 envelope schema for all 51 state cases."""
    nonempty = {"type": "string", "minLength": 1}
    fp = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    string_array = {"type": "array", "uniqueItems": True, "items": nonempty}
    binding = _closed_schema(
        ["contract_id", "version", "fingerprint"],
        _json_object({"contract_id": nonempty, "version": nonempty, "fingerprint": fp}),
    )
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": {"type": "string", "pattern": "^HKREG-PAIR-0(1[6-9]|2[0-4])$"},
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    packet = _closed_schema(
        ["slot_id", "state", "path", "role", "media_type", "content_fingerprint"],
        _json_object(
            {
                "slot_id": {"const": "state-evidence"},
                "state": {"const": "AVAILABLE"},
                "path": nonempty,
                "role": {"const": "ORDINARY"},
                "media_type": {"const": "application/json"},
                "content_fingerprint": fp,
            }
        ),
    )
    required = [
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
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.state-decision-case"},
            "schema_version": {"const": HKEX_STATE_DECISION_CONTRACT_VERSION},
            "package_contract_version": {"const": "1.0.0"},
            "case_id": {"type": "string", "pattern": "^HKREG-DEC-STA-(0[0-4][0-9]|05[01])$"},
            "suite_layer": {"const": "EVIDENCE_TO_DECISION"},
            "primary_checkpoint": {"const": "EFFECTIVE_STATE"},
            "frozen": {"const": True},
            "synthetic_evidence_class": {"const": "SYNTHETIC_NO_REAL_AUTHORITY"},
            "contract_bindings": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "uniqueItems": True,
                "items": binding,
            },
            "synthetic_cutoff": {"const": "2026-08-24T00:00:00Z"},
            "scope_id": {"const": "HKEX_CROSS_BOARD"},
            "prior_state": {"const": "SYNTHETIC_ACCEPTED_PREDECESSOR"},
            "primary_coverage_cell_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": {"type": "string", "pattern": "^HKREG-COV-DSTA-(0[0-4][0-9]|05[01])$"},
            },
            "secondary_coverage_cell_ids": string_array,
            "pair_memberships": {
                "type": "array",
                "maxItems": 2,
                "uniqueItems": True,
                "items": pair,
            },
            "declared_input_inventory": {"const": ["state-evidence"]},
            "declared_reference_inventory": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "uniqueItems": True,
                "items": nonempty,
            },
            "declared_expected_inventory": {"const": ["STATE_DECISION_REPORT"]},
            "assertion_scope": {"enum": [item.value for item in HKEXStateAssertionScope]},
            "required_result_dimensions": string_array,
            "evidence_packet_fields": string_array,
            "supporting_evidence_ranges": string_array,
            "rule_trace": string_array,
            "established_facts": string_array,
            "unresolved_facts": string_array,
            "permitted_equivalent_results": {"type": "array", "maxItems": 0},
            "critical_error_codes": string_array,
            "package_fingerprint": fp,
            "title": nonempty,
            "purpose": nonempty,
            "expected_decision": _state_result_schema(),
            "evidence_packet": packet,
            "facts": _state_facts_schema(),
            "case_fingerprint": fp,
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-state-decision-case.schema.json",
            "title": "HKEX effective-state evidence-to-decision conformance case",
            **_closed_schema(required, properties),
        }
    )


def build_state_decision_report_schema() -> dict[str, JsonValue]:
    """Build the strict complete state decision report schema."""
    required = [
        "schema_id",
        "schema_version",
        "rule_id",
        "case_id",
        "assertion_scope",
        "observed_decision",
        "expected_decision",
        "conformance_status",
        "source_authorized",
        "provider_authorized",
        "release_authorized",
        "serving_authorized",
        "deployment_authorized",
        "external_effects",
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.state-decision-report"},
            "schema_version": {"const": HKEX_STATE_DECISION_CONTRACT_VERSION},
            "rule_id": {"const": HKEX_STATE_DECISION_RULE_ID},
            "case_id": {"type": "string", "pattern": "^HKREG-DEC-STA-(0[0-4][0-9]|05[01])$"},
            "assertion_scope": {"enum": [item.value for item in HKEXStateAssertionScope]},
            "observed_decision": _state_result_schema(),
            "expected_decision": _state_result_schema(),
            "conformance_status": {"enum": ["PASS", "FAIL"]},
            "source_authorized": {"const": False},
            "provider_authorized": {"const": False},
            "release_authorized": {"const": False},
            "serving_authorized": {"const": False},
            "deployment_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-state-decision-report.schema.json",
            "title": "HKEX effective-state decision conformance report",
            **_closed_schema(required, properties),
        }
    )


def build_state_decision_catalogue_schema() -> dict[str, JsonValue]:
    """Build the strict 51-entry executable checkpoint catalogue schema."""
    nonempty = {"type": "string", "minLength": 1}
    fp = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object({"pair_id": nonempty, "role": {"enum": ["POSITIVE", "NEAR_MISS"]}}),
    )
    entry = _closed_schema(
        [
            "case_id",
            "primary_coverage_cell_id",
            "pair_memberships",
            "assertion_scope",
            "expected_outcome",
            "expected_reason",
            "fixture_path",
            "fixture_fingerprint",
            "expected_path",
            "expected_fingerprint",
        ],
        _json_object(
            {
                "case_id": nonempty,
                "primary_coverage_cell_id": nonempty,
                "pair_memberships": {
                    "type": "array",
                    "maxItems": 2,
                    "uniqueItems": True,
                    "items": pair,
                },
                "assertion_scope": {"enum": [item.value for item in HKEXStateAssertionScope]},
                "expected_outcome": {"enum": [item.value for item in HKEXStateConformanceOutcome]},
                "expected_reason": {"enum": [item.value for item in HKEXStateDecisionReason]},
                "fixture_path": nonempty,
                "fixture_fingerprint": fp,
                "expected_path": nonempty,
                "expected_fingerprint": fp,
            }
        ),
    )
    required = [
        "schema_id",
        "schema_version",
        "catalogue_id",
        "catalogue_version",
        "status",
        "case_count",
        "primary_coverage_cell_count",
        "high_risk_pair_ids",
        "entries",
        "checkpoint_complete",
        "full_conformance_suite_complete",
        "activation_authorized",
        "external_effects",
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.state-decision-catalogue"},
            "schema_version": {"const": HKEX_STATE_DECISION_CONTRACT_VERSION},
            "catalogue_id": {"const": "hk-regulatory-state-decision"},
            "catalogue_version": {"const": "1.0.0"},
            "status": {"const": "FROZEN_EXECUTABLE_CHECKPOINT"},
            "case_count": {"const": HKEX_STATE_DECISION_CASE_COUNT},
            "primary_coverage_cell_count": {"const": HKEX_STATE_DECISION_CASE_COUNT},
            "high_risk_pair_ids": {
                "type": "array",
                "minItems": 9,
                "maxItems": 9,
                "uniqueItems": True,
                "items": nonempty,
            },
            "entries": {
                "type": "array",
                "minItems": HKEX_STATE_DECISION_CASE_COUNT,
                "maxItems": HKEX_STATE_DECISION_CASE_COUNT,
                "items": entry,
            },
            "checkpoint_complete": {"const": True},
            "full_conformance_suite_complete": {"const": False},
            "activation_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-state-decision-catalogue.schema.json",
            "title": "HKEX effective-state executable checkpoint catalogue",
            **_closed_schema(required, properties),
        }
    )


def build_state_decision_rule() -> dict[str, JsonValue]:
    """Declare the exact bounded authority of the 51-case checkpoint."""
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory-state-decision-rule",
            "schema_version": HKEX_STATE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_STATE_DECISION_RULE_ID,
            "status": "SOURCE_NEUTRAL_EXECUTABLE_CHECKPOINT",
            "accepted_adrs": ["0005", "0071", "0074", "0075"],
            "case_schema": "contracts/schemas/hkex-state-decision-case.schema.json",
            "report_schema": "contracts/schemas/hkex-state-decision-report.schema.json",
            "catalogue_schema": "contracts/schemas/hkex-state-decision-catalogue.schema.json",
            "catalogue": "catalogues/state-decision-cases.json",
            "required_case_count": HKEX_STATE_DECISION_CASE_COUNT,
            "required_primary_coverage_cell_count": HKEX_STATE_DECISION_CASE_COUNT,
            "required_high_risk_pairs": [f"HKREG-PAIR-{ordinal:03d}" for ordinal in range(16, 25)],
            "complete_structured_decision_match_required": True,
            "case_id_switching_forbidden": True,
            "state_decision_checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "source_authority": False,
            "activation_authority": False,
            "external_effects": "NONE",
        }
    )


def build_source_decision_rule() -> dict[str, JsonValue]:
    """Declare the exact bounded authority of the 62-case checkpoint."""
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory-source-decision-rule",
            "schema_version": HKEX_SOURCE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_SOURCE_DECISION_RULE_ID,
            "status": "SOURCE_NEUTRAL_EXECUTABLE_CHECKPOINT",
            "accepted_adrs": ["0069", "0070", "0072", "0074", "0075"],
            "case_schema": "contracts/schemas/hkex-source-decision-case.schema.json",
            "report_schema": "contracts/schemas/hkex-source-decision-report.schema.json",
            "catalogue_schema": ("contracts/schemas/hkex-source-decision-catalogue.schema.json"),
            "catalogue": "catalogues/source-decision-cases.json",
            "required_case_count": HKEX_SOURCE_DECISION_CASE_COUNT,
            "required_primary_coverage_cell_count": HKEX_SOURCE_DECISION_CASE_COUNT,
            "required_high_risk_pairs": [f"HKREG-PAIR-{ordinal:03d}" for ordinal in range(1, 16)],
            "complete_structured_decision_match_required": True,
            "case_id_switching_forbidden": True,
            "source_decision_checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "source_authority": False,
            "activation_authority": False,
            "external_effects": "NONE",
        }
    )


@dataclass(frozen=True, slots=True)
class _BoundaryCaseSpec:
    scope: HKEXBoundaryAssertionScope
    facts: dict[str, JsonValue]
    expected: dict[str, JsonValue]


class _BoundaryReferenceOptions(TypedDict, total=False):
    heading: str | None
    referring_scope_id: str
    scope_id: str
    resolved: bool
    copied: bool
    target_changed: bool
    referring_changed: bool


class _BoundaryExpectedOptions(TypedDict, total=False):
    responsibilities: list[JsonValue]
    dependency_owners: list[JsonValue]
    references: list[JsonValue]
    excluded_background_unit_ids: list[str]
    quarantined_unit_ids: list[str]
    rejected: bool
    contract_review: bool
    quarantined: bool
    presentation_rejected: bool
    relationship_only: bool
    payload_change: bool


def _boundary_facts(**overrides: JsonValue) -> dict[str, JsonValue]:
    facts = _json_object(
        {
            "component_class": HKEXComponentClass.ORDINARY_RULE.value,
            "source_contract_state": HKEXSourceContractState.SUPPORTED.value,
            "parent_unit_id": "rule",
            "child_unit_ids": [],
            "independent_child_ids": [],
            "selected_primary_unit_ids": ["rule"],
            "inseparable_logic": False,
            "required_dependency_ids": [],
            "proposed_dependency_ids": [],
            "background_unit_ids": [],
            "qualification_unit_ids": [],
            "note_owner_unit_id": None,
            "proposed_note_owner_unit_id": None,
            "definition_scope": HKEXDefinitionScope.NONE.value,
            "definition_term_unit_ids": [],
            "global_scope_unit_id": None,
            "duplicate_global_definition": False,
            "legal_location_basis": HKEXLegalLocationBasis.PROVED_LEGAL_STRUCTURE.value,
            "dependency_owners": [],
            "references": [],
            "complete_unit_fits_hard_limits": True,
            "unrelated_unit_packed": False,
        }
    )
    unknown = set(overrides).difference(facts)
    if unknown:
        raise _ConformanceBuildError(str(sorted(unknown)))
    facts.update(overrides)
    return facts


def _boundary_responsibility(
    record_unit_id: str,
    kind: HKEXRecordUnitKind,
    primary: list[str],
    dependencies: list[str] | None = None,
) -> JsonValue:
    return _json_object(
        {
            "record_unit_id": record_unit_id,
            "kind": kind.value,
            "primary_source_unit_ids": primary,
            "dependency_source_unit_ids": [] if dependencies is None else dependencies,
        }
    )


def _boundary_reference_fact(
    referring: str,
    locator: str,
    **options: Unpack[_BoundaryReferenceOptions],
) -> JsonValue:
    heading = options.get("heading")
    referring_scope_id = options.get("referring_scope_id", HKEX_MAIN_SCOPE_ID)
    scope_id = options.get("scope_id", HKEX_MAIN_SCOPE_ID)
    return {
        "referring_unit_id": referring,
        "referring_words": f"see {locator}",
        "referring_scope_id": referring_scope_id,
        "target_locator": locator,
        "target_heading": heading,
        "target_scope_id": scope_id,
        "target_resolved": options.get("resolved", True),
        "target_text_copied": options.get("copied", False),
        "target_content_changed": options.get("target_changed", False),
        "referring_payload_changed": options.get("referring_changed", False),
    }


def _boundary_reference_expected(
    referring: str,
    locator: str,
    **options: Unpack[_BoundaryReferenceOptions],
) -> JsonValue:
    heading = options.get("heading")
    referring_scope_id = options.get("referring_scope_id", HKEX_MAIN_SCOPE_ID)
    scope_id = options.get("scope_id", HKEX_MAIN_SCOPE_ID)
    resolved = options.get("resolved", True)
    return {
        "referring_unit_id": referring,
        "referring_words": f"see {locator}",
        "referring_scope_id": referring_scope_id,
        "target_locator": locator,
        "target_heading": heading,
        "target_scope_id": scope_id,
        "resolution": "RESOLVED" if resolved else "UNRESOLVED",
        "target_text_included": False,
    }


def _boundary_expected(
    outcome: HKEXBoundaryOutcome,
    reason: HKEXBoundaryReason,
    **options: Unpack[_BoundaryExpectedOptions],
) -> dict[str, JsonValue]:
    return _json_object(
        {
            "outcome": outcome.value,
            "reason": reason.value,
            "responsibilities": options.get("responsibilities", []),
            "dependency_owners": options.get("dependency_owners", []),
            "references": options.get("references", []),
            "excluded_background_unit_ids": options.get("excluded_background_unit_ids", []),
            "quarantined_unit_ids": options.get("quarantined_unit_ids", []),
            "rejected_candidate": options.get("rejected", False),
            "source_contract_review_required": options.get("contract_review", False),
            "quarantined_branch": options.get("quarantined", False),
            "presentation_identity_rejected": options.get("presentation_rejected", False),
            "relationship_revision_only": options.get("relationship_only", False),
            "referring_payload_change_required": options.get("payload_change", False),
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "external_effects": "NONE",
        }
    )


def _boundary_normal_specs() -> tuple[_BoundaryCaseSpec, ...]:
    normal = HKEXBoundaryAssertionScope.NORMAL_UNIT
    return (
        _BoundaryCaseSpec(
            normal,
            _boundary_facts(parent_unit_id="whole-rule", selected_primary_unit_ids=["whole-rule"]),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.ONE_COMPLETE_NORMAL_UNIT,
                responsibilities=[
                    _boundary_responsibility(
                        "record-whole-rule", HKEXRecordUnitKind.NORMAL, ["whole-rule"]
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            normal,
            _boundary_facts(
                parent_unit_id="rule-2",
                child_unit_ids=["subrule-2-1", "subrule-2-2"],
                independent_child_ids=["subrule-2-1", "subrule-2-2"],
                selected_primary_unit_ids=["subrule-2-1", "subrule-2-2"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.INDEPENDENT_CHILDREN_SELECTED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-subrule-2-1", HKEXRecordUnitKind.NORMAL, ["subrule-2-1"]
                    ),
                    _boundary_responsibility(
                        "record-subrule-2-2", HKEXRecordUnitKind.NORMAL, ["subrule-2-2"]
                    ),
                ],
            ),
        ),
        _BoundaryCaseSpec(
            normal,
            _boundary_facts(
                parent_unit_id="rule-3",
                child_unit_ids=["limb-3-a", "limb-3-b"],
                selected_primary_unit_ids=["rule-3", "limb-3-a", "limb-3-b"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.INSEPARABLE_GROUP_PRESERVED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-rule-3",
                        HKEXRecordUnitKind.INSEPARABLE_GROUP,
                        ["rule-3", "limb-3-a", "limb-3-b"],
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            normal,
            _boundary_facts(
                parent_unit_id="rule-4",
                child_unit_ids=["alternative-4-a", "alternative-4-b"],
                selected_primary_unit_ids=["rule-4", "alternative-4-a", "alternative-4-b"],
                inseparable_logic=True,
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.INSEPARABLE_GROUP_PRESERVED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-rule-4",
                        HKEXRecordUnitKind.INSEPARABLE_GROUP,
                        ["rule-4", "alternative-4-a", "alternative-4-b"],
                    )
                ],
            ),
        ),
    )


def _boundary_dependency_specs() -> tuple[_BoundaryCaseSpec, ...]:
    dependency = HKEXBoundaryAssertionScope.GOVERNING_DEPENDENCY
    owner: JsonValue = {
        "source_unit_id": "shared-dependency-20",
        "owner_record_unit_id": "record-shared-dependency-20",
        "content_fingerprint": f"sha256:{'2' * 64}",
    }
    return (
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="rule-5",
                child_unit_ids=["child-5"],
                selected_primary_unit_ids=["child-5"],
                required_dependency_ids=["lead-in-5"],
                proposed_dependency_ids=["lead-in-5"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.REQUIRED_DEPENDENCIES_PRESERVED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-child-5", HKEXRecordUnitKind.NORMAL, ["child-5"], ["lead-in-5"]
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="rule-6",
                child_unit_ids=["child-6"],
                selected_primary_unit_ids=["child-6"],
                required_dependency_ids=["lead-in-6"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.BLOCK,
                HKEXBoundaryReason.UNSAFE_CHILD_BOUNDARY_REJECTED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-rule-6",
                        HKEXRecordUnitKind.PARENT_FALLBACK,
                        ["rule-6", "child-6"],
                    )
                ],
                rejected=True,
            ),
        ),
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="obligation-7",
                selected_primary_unit_ids=["obligation-7"],
                required_dependency_ids=["qualification-7"],
                proposed_dependency_ids=["qualification-7"],
                qualification_unit_ids=["qualification-7"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.REQUIRED_DEPENDENCIES_PRESERVED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-obligation-7",
                        HKEXRecordUnitKind.NORMAL,
                        ["obligation-7"],
                        ["qualification-7"],
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="rule-8",
                selected_primary_unit_ids=["rule-8", "note-8"],
                note_owner_unit_id="rule-8",
                proposed_note_owner_unit_id="rule-8",
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.NOTE_OWNER_PRESERVED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-rule-8", HKEXRecordUnitKind.NORMAL, ["rule-8", "note-8"]
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="rule-9",
                selected_primary_unit_ids=["rule-9", "note-9"],
                note_owner_unit_id="rule-9",
                proposed_note_owner_unit_id="rule-elsewhere",
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.BLOCK,
                HKEXBoundaryReason.NOTE_OWNERSHIP_REJECTED,
                rejected=True,
            ),
        ),
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="branch-18",
                child_unit_ids=["child-18"],
                selected_primary_unit_ids=["child-18"],
                required_dependency_ids=["governing-context-18"],
                proposed_dependency_ids=["governing-context-18"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.REQUIRED_DEPENDENCIES_PRESERVED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-child-18",
                        HKEXRecordUnitKind.NORMAL,
                        ["child-18"],
                        ["governing-context-18"],
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="rule-19",
                selected_primary_unit_ids=["rule-19"],
                background_unit_ids=["helpful-background-19"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.BACKGROUND_EXCLUDED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-rule-19", HKEXRecordUnitKind.NORMAL, ["rule-19"]
                    )
                ],
                excluded_background_unit_ids=["helpful-background-19"],
            ),
        ),
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="rule-20",
                selected_primary_unit_ids=["rule-20"],
                required_dependency_ids=["shared-dependency-20"],
                proposed_dependency_ids=["shared-dependency-20"],
                dependency_owners=[owner],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.DEPENDENCY_OWNER_LINKED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-rule-20",
                        HKEXRecordUnitKind.NORMAL,
                        ["rule-20"],
                        ["shared-dependency-20"],
                    )
                ],
                dependency_owners=[owner],
            ),
        ),
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="parent-28",
                child_unit_ids=["dependent-child-28"],
                selected_primary_unit_ids=["dependent-child-28"],
                required_dependency_ids=["parent-28"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.BLOCK,
                HKEXBoundaryReason.UNSAFE_CHILD_BOUNDARY_REJECTED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-parent-28",
                        HKEXRecordUnitKind.PARENT_FALLBACK,
                        ["parent-28", "dependent-child-28"],
                    )
                ],
                rejected=True,
            ),
        ),
    )


def _boundary_definition_and_structure_specs() -> tuple[_BoundaryCaseSpec, ...]:
    definition = HKEXBoundaryAssertionScope.DEFINITION
    legal = HKEXBoundaryAssertionScope.LEGAL_STRUCTURE
    normal = HKEXBoundaryAssertionScope.NORMAL_UNIT
    return (
        _BoundaryCaseSpec(
            definition,
            _boundary_facts(
                component_class=HKEXComponentClass.DEFINITION_RULE.value,
                parent_unit_id="definitions-10",
                selected_primary_unit_ids=["definitions-10"],
                definition_scope=HKEXDefinitionScope.TERM_COLLECTION.value,
                definition_term_unit_ids=["term-10-a", "term-10-b"],
                global_scope_unit_id="definition-scope-10",
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.TERM_DEFINITIONS_SELECTED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-term-10-a",
                        HKEXRecordUnitKind.DEFINITION,
                        ["term-10-a"],
                        ["definition-scope-10"],
                    ),
                    _boundary_responsibility(
                        "record-term-10-b",
                        HKEXRecordUnitKind.DEFINITION,
                        ["term-10-b"],
                        ["definition-scope-10"],
                    ),
                ],
            ),
        ),
        _BoundaryCaseSpec(
            definition,
            _boundary_facts(
                component_class=HKEXComponentClass.DEFINITION_RULE.value,
                parent_unit_id="global-definition-11",
                selected_primary_unit_ids=["global-definition-11"],
                definition_scope=HKEXDefinitionScope.GLOBAL.value,
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.GLOBAL_DEFINITION_SELECTED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-global-definition-11",
                        HKEXRecordUnitKind.DEFINITION,
                        ["global-definition-11"],
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            definition,
            _boundary_facts(
                component_class=HKEXComponentClass.DEFINITION_RULE.value,
                parent_unit_id="global-definition-12",
                selected_primary_unit_ids=["global-definition-12"],
                definition_scope=HKEXDefinitionScope.GLOBAL.value,
                duplicate_global_definition=True,
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.BLOCK,
                HKEXBoundaryReason.GLOBAL_DEFINITION_DUPLICATION_REJECTED,
                rejected=True,
            ),
        ),
        _BoundaryCaseSpec(
            definition,
            _boundary_facts(
                component_class=HKEXComponentClass.DEFINITION_RULE.value,
                parent_unit_id="branch-13",
                selected_primary_unit_ids=["branch-13"],
                definition_scope=HKEXDefinitionScope.LOCAL.value,
                required_dependency_ids=["local-definition-13"],
                proposed_dependency_ids=["local-definition-13"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.REQUIRED_DEPENDENCIES_PRESERVED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-branch-13",
                        HKEXRecordUnitKind.NORMAL,
                        ["branch-13"],
                        ["local-definition-13"],
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            normal,
            _boundary_facts(
                component_class=HKEXComponentClass.APPENDIX.value,
                parent_unit_id="appendix-paragraph-14",
                selected_primary_unit_ids=["appendix-paragraph-14"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.ONE_COMPLETE_NORMAL_UNIT,
                responsibilities=[
                    _boundary_responsibility(
                        "record-appendix-paragraph-14",
                        HKEXRecordUnitKind.APPENDIX,
                        ["appendix-paragraph-14"],
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            normal,
            _boundary_facts(
                component_class=HKEXComponentClass.PRACTICE_NOTE.value,
                parent_unit_id="practice-note-paragraph-15",
                selected_primary_unit_ids=["practice-note-paragraph-15"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.ONE_COMPLETE_NORMAL_UNIT,
                responsibilities=[
                    _boundary_responsibility(
                        "record-practice-note-paragraph-15",
                        HKEXRecordUnitKind.PRACTICE_NOTE,
                        ["practice-note-paragraph-15"],
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            legal,
            _boundary_facts(
                parent_unit_id="presentation-location-16",
                selected_primary_unit_ids=["presentation-location-16"],
                legal_location_basis=HKEXLegalLocationBasis.PRESENTATION_ONLY.value,
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.BLOCK,
                HKEXBoundaryReason.PRESENTATION_IDENTITY_REJECTED,
                rejected=True,
                presentation_rejected=True,
            ),
        ),
        _BoundaryCaseSpec(
            legal,
            _boundary_facts(
                parent_unit_id="ambiguous-structure-17",
                selected_primary_unit_ids=["ambiguous-structure-17"],
                source_contract_state=HKEXSourceContractState.UNKNOWN.value,
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.QUARANTINE,
                HKEXBoundaryReason.SOURCE_STRUCTURE_REVIEW_REQUIRED,
                contract_review=True,
                quarantined=True,
                quarantined_unit_ids=["ambiguous-structure-17"],
            ),
        ),
    )


def _boundary_reference_specs() -> tuple[_BoundaryCaseSpec, ...]:
    scope = HKEXBoundaryAssertionScope.CROSS_REFERENCE
    a_to_b = _boundary_reference_fact("unit-23-a", "rule-23-b", heading="Rule B")
    b_to_c = _boundary_reference_fact("unit-23-b", "rule-23-c", heading="Rule C")
    return (
        _BoundaryCaseSpec(
            scope,
            _boundary_facts(
                references=[
                    _boundary_reference_fact("unit-21", "rule-21-target", heading="Target rule")
                ]
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.CROSS_REFERENCE_PRESERVED,
                references=[
                    _boundary_reference_expected("unit-21", "rule-21-target", heading="Target rule")
                ],
            ),
        ),
        _BoundaryCaseSpec(
            scope,
            _boundary_facts(
                references=[
                    _boundary_reference_fact(
                        "unit-22", "rule-22-target", heading="Target rule", copied=True
                    )
                ]
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.BLOCK,
                HKEXBoundaryReason.RECURSIVE_TARGET_COPY_REJECTED,
                references=[
                    _boundary_reference_expected("unit-22", "rule-22-target", heading="Target rule")
                ],
                rejected=True,
            ),
        ),
        _BoundaryCaseSpec(
            scope,
            _boundary_facts(references=[a_to_b, b_to_c]),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.REFERENCE_CHAIN_PRESERVED,
                references=[
                    _boundary_reference_expected("unit-23-a", "rule-23-b", heading="Rule B"),
                    _boundary_reference_expected("unit-23-b", "rule-23-c", heading="Rule C"),
                ],
            ),
        ),
        _BoundaryCaseSpec(
            scope,
            _boundary_facts(
                references=[
                    _boundary_reference_fact(
                        "unit-24", "missing-rule-24", heading="Missing rule", resolved=False
                    )
                ]
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.QUARANTINE,
                HKEXBoundaryReason.TARGET_RESOLUTION_REQUIRED,
                references=[
                    _boundary_reference_expected(
                        "unit-24", "missing-rule-24", heading="Missing rule", resolved=False
                    )
                ],
                contract_review=True,
                quarantined=True,
                quarantined_unit_ids=["unit-24"],
            ),
        ),
        _BoundaryCaseSpec(
            scope,
            _boundary_facts(
                references=[
                    _boundary_reference_fact(
                        "main-unit-25",
                        "gem-rule-25",
                        heading="GEM target",
                        scope_id=HKEX_GEM_SCOPE_ID,
                    )
                ]
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.CROSS_BOARD_REFERENCE_PRESERVED,
                references=[
                    _boundary_reference_expected(
                        "main-unit-25",
                        "gem-rule-25",
                        heading="GEM target",
                        scope_id=HKEX_GEM_SCOPE_ID,
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            scope,
            _boundary_facts(
                references=[
                    _boundary_reference_fact(
                        "unit-26",
                        "rule-26-target",
                        heading="Changed target",
                        target_changed=True,
                    )
                ]
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.RELATIONSHIP_REVISION_ONLY,
                references=[
                    _boundary_reference_expected(
                        "unit-26", "rule-26-target", heading="Changed target"
                    )
                ],
                relationship_only=True,
            ),
        ),
    )


def _boundary_limit_specs() -> tuple[_BoundaryCaseSpec, ...]:
    normal = HKEXBoundaryAssertionScope.NORMAL_UNIT
    dependency = HKEXBoundaryAssertionScope.GOVERNING_DEPENDENCY
    return (
        _BoundaryCaseSpec(
            normal,
            _boundary_facts(
                parent_unit_id="rule-27",
                child_unit_ids=["independent-child-27"],
                independent_child_ids=["independent-child-27"],
                selected_primary_unit_ids=["independent-child-27"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.PASS,
                HKEXBoundaryReason.INDEPENDENT_CHILDREN_SELECTED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-independent-child-27",
                        HKEXRecordUnitKind.NORMAL,
                        ["independent-child-27"],
                    )
                ],
            ),
        ),
        _BoundaryCaseSpec(
            dependency,
            _boundary_facts(
                parent_unit_id="parent-28",
                child_unit_ids=["dependent-child-28"],
                selected_primary_unit_ids=["dependent-child-28"],
                required_dependency_ids=["parent-28"],
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.BLOCK,
                HKEXBoundaryReason.UNSAFE_CHILD_BOUNDARY_REJECTED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-parent-28",
                        HKEXRecordUnitKind.PARENT_FALLBACK,
                        ["parent-28", "dependent-child-28"],
                    )
                ],
                rejected=True,
            ),
        ),
        _BoundaryCaseSpec(
            normal,
            _boundary_facts(
                parent_unit_id="complete-unit-29",
                selected_primary_unit_ids=["complete-unit-29"],
                complete_unit_fits_hard_limits=False,
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.QUARANTINE,
                HKEXBoundaryReason.COMPLETE_UNIT_OVER_LIMIT,
                quarantined=True,
                quarantined_unit_ids=["complete-unit-29"],
            ),
        ),
        _BoundaryCaseSpec(
            normal,
            _boundary_facts(
                parent_unit_id="unrelated-a-30",
                selected_primary_unit_ids=["unrelated-a-30", "unrelated-b-30"],
                unrelated_unit_packed=True,
            ),
            _boundary_expected(
                HKEXBoundaryOutcome.BLOCK,
                HKEXBoundaryReason.UNRELATED_PACKING_REJECTED,
                responsibilities=[
                    _boundary_responsibility(
                        "record-unrelated-a-30",
                        HKEXRecordUnitKind.NORMAL,
                        ["unrelated-a-30"],
                    ),
                    _boundary_responsibility(
                        "record-unrelated-b-30",
                        HKEXRecordUnitKind.NORMAL,
                        ["unrelated-b-30"],
                    ),
                ],
                rejected=True,
            ),
        ),
    )


def _boundary_case_specs() -> tuple[_BoundaryCaseSpec, ...]:
    specs = (
        *_boundary_normal_specs(),
        *_boundary_dependency_specs()[:5],
        *_boundary_definition_and_structure_specs(),
        *_boundary_dependency_specs()[5:8],
        *_boundary_reference_specs(),
        *_boundary_limit_specs(),
    )
    if len(specs) != HKEX_BOUNDARY_DECISION_CASE_COUNT:
        raise _ConformanceBuildError
    return specs


def _boundary_contract_bindings(universe_fingerprint: str) -> list[JsonValue]:
    seed = _json_object(
        {
            "contract_id": "asklegal.hk-regulatory.boundary-decision-case",
            "contract_version": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_BOUNDARY_DECISION_RULE_ID,
        }
    )
    return [
        {
            "contract_id": "asklegal.hk-regulatory.conformance-universe",
            "version": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
            "fingerprint": universe_fingerprint,
        },
        {
            "contract_id": "asklegal.hk-regulatory.boundary-decision-case",
            "version": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
            "fingerprint": _fingerprint(rfc8785.dumps(seed)),
        },
    ]


def _boundary_expected_document(
    case_id: str, expected: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.boundary-decision-result",
            "schema_version": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_BOUNDARY_DECISION_RULE_ID,
            "case_id": case_id,
            **deepcopy(expected),
        }
    )


def build_boundary_decision_cases() -> tuple[
    tuple[dict[str, JsonValue], dict[str, JsonValue]], ...
]:
    """Build all 30 permanent record-boundary cases and frozen reports."""
    universe = build_conformance_universe()
    all_cases = _json_array(universe["cases"])
    start = HKEX_SOURCE_DECISION_CASE_COUNT + HKEX_STATE_DECISION_CASE_COUNT
    universe_cases = tuple(
        _json_object(item) for item in all_cases[start : start + HKEX_BOUNDARY_DECISION_CASE_COUNT]
    )
    specs = _boundary_case_specs()
    universe_fingerprint = _fingerprint(rfc8785.dumps(universe))
    bindings = _boundary_contract_bindings(universe_fingerprint)
    results: list[tuple[dict[str, JsonValue], dict[str, JsonValue]]] = []
    for universe_case, spec in zip(universe_cases, specs, strict=True):
        case_id = str(universe_case["case_id"])
        facts = deepcopy(spec.facts)
        expected = _boundary_expected_document(case_id, spec.expected)
        fixture = _json_object(
            {
                "schema_id": "asklegal.hk-regulatory.boundary-decision-case",
                "schema_version": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
                "package_contract_version": "1.0.0",
                "case_id": case_id,
                "suite_layer": "EVIDENCE_TO_DECISION",
                "primary_checkpoint": "RECORD_BOUNDARY",
                "frozen": True,
                "synthetic_evidence_class": "SYNTHETIC_NO_REAL_AUTHORITY",
                "contract_bindings": deepcopy(bindings),
                "synthetic_cutoff": "2026-08-24T00:00:00Z",
                "scope_id": "HKEX_CROSS_BOARD",
                "prior_state": "SYNTHETIC_ACCEPTED_PREDECESSOR",
                "primary_coverage_cell_ids": [universe_case["coverage_cell_id"]],
                "secondary_coverage_cell_ids": [],
                "pair_memberships": deepcopy(universe_case["pair_memberships"]),
                "declared_input_inventory": ["boundary-evidence"],
                "declared_reference_inventory": [
                    "asklegal.hk-regulatory.conformance-universe",
                    "asklegal.hk-regulatory.boundary-decision-case",
                ],
                "declared_expected_inventory": ["BOUNDARY_DECISION_REPORT"],
                "assertion_scope": spec.scope.value,
                "required_result_dimensions": [
                    "CROSS_REFERENCE",
                    "DEPENDENCY_CLOSURE",
                    "LEGAL_LOCATION",
                    "PROCESSING",
                    "RECORD_RESPONSIBILITY",
                    "SOURCE_STRUCTURE",
                ],
                "evidence_packet_fields": sorted(facts),
                "supporting_evidence_ranges": [f"input/{case_id}-boundary-evidence.json#facts"],
                "rule_trace": [
                    HKEX_BOUNDARY_DECISION_RULE_ID,
                    "HKREG-ENGLISH-RECORD-001",
                ],
                "established_facts": ["SYNTHETIC_BOUNDARY_FACT_PACKET_DECLARED"],
                "unresolved_facts": (
                    [str(spec.expected["reason"])]
                    if spec.expected["outcome"] in {"BLOCK", "QUARANTINE"}
                    else []
                ),
                "permitted_equivalent_results": [],
                "critical_error_codes": (
                    [str(spec.expected["reason"])]
                    if spec.expected["outcome"] in {"BLOCK", "QUARANTINE"}
                    else []
                ),
                "package_fingerprint": universe_fingerprint,
                "title": universe_case["synthetic_scenario"],
                "purpose": universe_case["exact_required_result"],
                "expected_decision": expected,
                "evidence_packet": {
                    "slot_id": "boundary-evidence",
                    "state": "AVAILABLE",
                    "path": f"input/{case_id}-boundary-evidence.json",
                    "role": "ORDINARY",
                    "media_type": "application/json",
                    "content_fingerprint": _fingerprint(rfc8785.dumps(facts)),
                },
                "facts": facts,
                "case_fingerprint": "PENDING",
            }
        )
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        parsed = hkex_boundary_decision_case_from_document(fixture)
        report = _json_object(run_hkex_boundary_case(parsed).document())
        if report["conformance_status"] != "PASS":
            failure = f"{case_id}:{spec.expected['reason']}"
            raise _ConformanceBuildError(failure)
        results.append((fixture, report))
    if len(results) != HKEX_BOUNDARY_DECISION_CASE_COUNT:
        raise _ConformanceBuildError
    return tuple(results)


def build_boundary_decision_catalogue(
    cases: tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...],
) -> dict[str, JsonValue]:
    """Bind all 30 exact boundary fact packets and reports."""
    entries: list[JsonValue] = []
    pair_ids: set[str] = set()
    for fixture, report in cases:
        case_id = str(fixture["case_id"])
        fixture_path = f"fixtures/conformance/boundary-decision/{case_id}.json"
        expected_path = f"expected/conformance/boundary-decision/{case_id}.json"
        expected = _json_object(fixture["expected_decision"])
        memberships = deepcopy(_json_array(fixture["pair_memberships"]))
        for membership in memberships:
            pair_ids.add(str(_json_object(membership)["pair_id"]))
        fixture_bytes = (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode()
        report_bytes = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
        entries.append(
            {
                "case_id": case_id,
                "primary_coverage_cell_id": _json_array(fixture["primary_coverage_cell_ids"])[0],
                "pair_memberships": memberships,
                "assertion_scope": fixture["assertion_scope"],
                "expected_outcome": expected["outcome"],
                "expected_reason": expected["reason"],
                "fixture_path": fixture_path,
                "fixture_fingerprint": _fingerprint(fixture_bytes),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint(report_bytes),
            }
        )
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.boundary-decision-catalogue",
            "schema_version": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
            "catalogue_id": "hk-regulatory-boundary-decision",
            "catalogue_version": "1.0.0",
            "status": "FROZEN_EXECUTABLE_CHECKPOINT",
            "case_count": HKEX_BOUNDARY_DECISION_CASE_COUNT,
            "primary_coverage_cell_count": HKEX_BOUNDARY_DECISION_CASE_COUNT,
            "high_risk_pair_ids": sorted(pair_ids),
            "entries": entries,
            "checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "activation_authorized": False,
            "external_effects": "NONE",
        }
    )


def _boundary_responsibility_schema() -> dict[str, JsonValue]:
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    return _closed_schema(
        [
            "record_unit_id",
            "kind",
            "primary_source_unit_ids",
            "dependency_source_unit_ids",
        ],
        _json_object(
            {
                "record_unit_id": nonempty,
                "kind": {"enum": [item.value for item in HKEXRecordUnitKind]},
                "primary_source_unit_ids": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": nonempty,
                },
                "dependency_source_unit_ids": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": nonempty,
                },
            }
        ),
    )


def _boundary_owner_schema() -> dict[str, JsonValue]:
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    return _closed_schema(
        ["source_unit_id", "owner_record_unit_id", "content_fingerprint"],
        _json_object(
            {
                "source_unit_id": nonempty,
                "owner_record_unit_id": nonempty,
                "content_fingerprint": {
                    "type": "string",
                    "pattern": "^sha256:[0-9a-f]{64}$",
                },
            }
        ),
    )


def _boundary_reference_result_schema() -> dict[str, JsonValue]:
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    return _closed_schema(
        [
            "referring_unit_id",
            "referring_words",
            "referring_scope_id",
            "target_locator",
            "target_heading",
            "target_scope_id",
            "resolution",
            "target_text_included",
        ],
        _json_object(
            {
                "referring_unit_id": nonempty,
                "referring_words": nonempty,
                "referring_scope_id": {"enum": [HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]},
                "target_locator": nonempty,
                "target_heading": {"oneOf": [nonempty, {"type": "null"}]},
                "target_scope_id": {"enum": [HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]},
                "resolution": {"enum": ["RESOLVED", "UNRESOLVED"]},
                "target_text_included": {"const": False},
            }
        ),
    )


def _boundary_result_schema() -> dict[str, JsonValue]:
    required = [
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
    ]
    boolean: JsonValue = {"type": "boolean"}
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.boundary-decision-result"},
            "schema_version": {"const": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION},
            "rule_id": {"const": HKEX_BOUNDARY_DECISION_RULE_ID},
            "case_id": {
                "type": "string",
                "pattern": "^HKREG-DEC-BND-(0[0-2][0-9]|030)$",
            },
            "outcome": {"enum": [item.value for item in HKEXBoundaryOutcome]},
            "reason": {"enum": [item.value for item in HKEXBoundaryReason]},
            "responsibilities": {
                "type": "array",
                "items": _boundary_responsibility_schema(),
            },
            "dependency_owners": {"type": "array", "items": _boundary_owner_schema()},
            "references": {
                "type": "array",
                "items": _boundary_reference_result_schema(),
            },
            "excluded_background_unit_ids": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
            },
            "quarantined_unit_ids": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
            },
            "rejected_candidate": boolean,
            "source_contract_review_required": boolean,
            "quarantined_branch": boolean,
            "presentation_identity_rejected": boolean,
            "relationship_revision_only": boolean,
            "referring_payload_change_required": boolean,
            "search_record_authorized": {"const": False},
            "embedding_authorized": {"const": False},
            "release_authorized": {"const": False},
            "serving_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _closed_schema(required, properties)


def _boundary_facts_schema() -> dict[str, JsonValue]:
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    strings: JsonValue = {
        "type": "array",
        "uniqueItems": True,
        "items": nonempty,
    }
    reference_fact = _closed_schema(
        [
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
        ],
        _json_object(
            {
                "referring_unit_id": nonempty,
                "referring_words": nonempty,
                "referring_scope_id": {"enum": [HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]},
                "target_locator": nonempty,
                "target_heading": {"oneOf": [nonempty, {"type": "null"}]},
                "target_scope_id": {"enum": [HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]},
                "target_resolved": {"type": "boolean"},
                "target_text_copied": {"type": "boolean"},
                "target_content_changed": {"type": "boolean"},
                "referring_payload_changed": {"type": "boolean"},
            }
        ),
    )
    required = [
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
    ]
    nullable = {"oneOf": [nonempty, {"type": "null"}]}
    properties = _json_object(
        {
            "component_class": {"enum": [item.value for item in HKEXComponentClass]},
            "source_contract_state": {"enum": [item.value for item in HKEXSourceContractState]},
            "parent_unit_id": nonempty,
            "child_unit_ids": strings,
            "independent_child_ids": strings,
            "selected_primary_unit_ids": strings,
            "inseparable_logic": {"type": "boolean"},
            "required_dependency_ids": strings,
            "proposed_dependency_ids": strings,
            "background_unit_ids": strings,
            "qualification_unit_ids": strings,
            "note_owner_unit_id": nullable,
            "proposed_note_owner_unit_id": nullable,
            "definition_scope": {"enum": [item.value for item in HKEXDefinitionScope]},
            "definition_term_unit_ids": strings,
            "global_scope_unit_id": nullable,
            "duplicate_global_definition": {"type": "boolean"},
            "legal_location_basis": {"enum": [item.value for item in HKEXLegalLocationBasis]},
            "dependency_owners": {"type": "array", "items": _boundary_owner_schema()},
            "references": {"type": "array", "items": reference_fact},
            "complete_unit_fits_hard_limits": {"type": "boolean"},
            "unrelated_unit_packed": {"type": "boolean"},
        }
    )
    return _closed_schema(required, properties)


def build_boundary_decision_case_schema() -> dict[str, JsonValue]:
    """Build the strict common envelope for all 30 boundary cases."""
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    fingerprint_schema: JsonValue = {
        "type": "string",
        "pattern": "^sha256:[0-9a-f]{64}$",
    }
    string_array: JsonValue = {"type": "array", "uniqueItems": True, "items": nonempty}
    binding = _closed_schema(
        ["contract_id", "version", "fingerprint"],
        _json_object(
            {
                "contract_id": nonempty,
                "version": nonempty,
                "fingerprint": fingerprint_schema,
            }
        ),
    )
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": {"type": "string", "pattern": "^HKREG-PAIR-0(2[5-9]|3[01])$"},
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    packet = _closed_schema(
        ["slot_id", "state", "path", "role", "media_type", "content_fingerprint"],
        _json_object(
            {
                "slot_id": {"const": "boundary-evidence"},
                "state": {"const": "AVAILABLE"},
                "path": nonempty,
                "role": {"const": "ORDINARY"},
                "media_type": {"const": "application/json"},
                "content_fingerprint": fingerprint_schema,
            }
        ),
    )
    required = [
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
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.boundary-decision-case"},
            "schema_version": {"const": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION},
            "package_contract_version": {"const": "1.0.0"},
            "case_id": {
                "type": "string",
                "pattern": "^HKREG-DEC-BND-(0[0-2][0-9]|030)$",
            },
            "suite_layer": {"const": "EVIDENCE_TO_DECISION"},
            "primary_checkpoint": {"const": "RECORD_BOUNDARY"},
            "frozen": {"const": True},
            "synthetic_evidence_class": {"const": "SYNTHETIC_NO_REAL_AUTHORITY"},
            "contract_bindings": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": binding,
            },
            "synthetic_cutoff": {"const": "2026-08-24T00:00:00Z"},
            "scope_id": {"const": "HKEX_CROSS_BOARD"},
            "prior_state": {"const": "SYNTHETIC_ACCEPTED_PREDECESSOR"},
            "primary_coverage_cell_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": nonempty,
            },
            "secondary_coverage_cell_ids": string_array,
            "pair_memberships": {
                "type": "array",
                "maxItems": 1,
                "uniqueItems": True,
                "items": pair,
            },
            "declared_input_inventory": {"const": ["boundary-evidence"]},
            "declared_reference_inventory": {
                "const": [
                    "asklegal.hk-regulatory.conformance-universe",
                    "asklegal.hk-regulatory.boundary-decision-case",
                ]
            },
            "declared_expected_inventory": {"const": ["BOUNDARY_DECISION_REPORT"]},
            "assertion_scope": {"enum": [item.value for item in HKEXBoundaryAssertionScope]},
            "required_result_dimensions": {
                "const": [
                    "CROSS_REFERENCE",
                    "DEPENDENCY_CLOSURE",
                    "LEGAL_LOCATION",
                    "PROCESSING",
                    "RECORD_RESPONSIBILITY",
                    "SOURCE_STRUCTURE",
                ]
            },
            "evidence_packet_fields": string_array,
            "supporting_evidence_ranges": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": nonempty,
            },
            "rule_trace": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": nonempty,
            },
            "established_facts": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": nonempty,
            },
            "unresolved_facts": string_array,
            "permitted_equivalent_results": {"const": []},
            "critical_error_codes": string_array,
            "package_fingerprint": fingerprint_schema,
            "title": nonempty,
            "purpose": nonempty,
            "expected_decision": _boundary_result_schema(),
            "evidence_packet": packet,
            "facts": _boundary_facts_schema(),
            "case_fingerprint": fingerprint_schema,
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-boundary-decision-case.schema.json",
            "title": "HKEX record-boundary decision conformance case",
            **_closed_schema(required, properties),
        }
    )


def build_boundary_decision_report_schema() -> dict[str, JsonValue]:
    """Build the exact effect-free boundary report schema."""
    required = [
        "schema_id",
        "schema_version",
        "rule_id",
        "case_id",
        "assertion_scope",
        "observed_decision",
        "expected_decision",
        "conformance_status",
        "source_authorized",
        "provider_authorized",
        "release_authorized",
        "serving_authorized",
        "deployment_authorized",
        "external_effects",
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.boundary-decision-report"},
            "schema_version": {"const": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION},
            "rule_id": {"const": HKEX_BOUNDARY_DECISION_RULE_ID},
            "case_id": {
                "type": "string",
                "pattern": "^HKREG-DEC-BND-(0[0-2][0-9]|030)$",
            },
            "assertion_scope": {"enum": [item.value for item in HKEXBoundaryAssertionScope]},
            "observed_decision": _boundary_result_schema(),
            "expected_decision": _boundary_result_schema(),
            "conformance_status": {"enum": ["PASS", "FAIL"]},
            "source_authorized": {"const": False},
            "provider_authorized": {"const": False},
            "release_authorized": {"const": False},
            "serving_authorized": {"const": False},
            "deployment_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-boundary-decision-report.schema.json",
            "title": "HKEX record-boundary decision conformance report",
            **_closed_schema(required, properties),
        }
    )


def build_boundary_decision_catalogue_schema() -> dict[str, JsonValue]:
    """Build the strict 30-entry boundary checkpoint catalogue schema."""
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    fingerprint_schema: JsonValue = {
        "type": "string",
        "pattern": "^sha256:[0-9a-f]{64}$",
    }
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": nonempty,
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    entry = _closed_schema(
        [
            "case_id",
            "primary_coverage_cell_id",
            "pair_memberships",
            "assertion_scope",
            "expected_outcome",
            "expected_reason",
            "fixture_path",
            "fixture_fingerprint",
            "expected_path",
            "expected_fingerprint",
        ],
        _json_object(
            {
                "case_id": nonempty,
                "primary_coverage_cell_id": nonempty,
                "pair_memberships": {
                    "type": "array",
                    "maxItems": 1,
                    "uniqueItems": True,
                    "items": pair,
                },
                "assertion_scope": {"enum": [item.value for item in HKEXBoundaryAssertionScope]},
                "expected_outcome": {"enum": [item.value for item in HKEXBoundaryOutcome]},
                "expected_reason": {"enum": [item.value for item in HKEXBoundaryReason]},
                "fixture_path": nonempty,
                "fixture_fingerprint": fingerprint_schema,
                "expected_path": nonempty,
                "expected_fingerprint": fingerprint_schema,
            }
        ),
    )
    required = [
        "schema_id",
        "schema_version",
        "catalogue_id",
        "catalogue_version",
        "status",
        "case_count",
        "primary_coverage_cell_count",
        "high_risk_pair_ids",
        "entries",
        "checkpoint_complete",
        "full_conformance_suite_complete",
        "activation_authorized",
        "external_effects",
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.boundary-decision-catalogue"},
            "schema_version": {"const": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION},
            "catalogue_id": {"const": "hk-regulatory-boundary-decision"},
            "catalogue_version": {"const": "1.0.0"},
            "status": {"const": "FROZEN_EXECUTABLE_CHECKPOINT"},
            "case_count": {"const": HKEX_BOUNDARY_DECISION_CASE_COUNT},
            "primary_coverage_cell_count": {"const": HKEX_BOUNDARY_DECISION_CASE_COUNT},
            "high_risk_pair_ids": {
                "type": "array",
                "minItems": 7,
                "maxItems": 7,
                "uniqueItems": True,
                "items": nonempty,
            },
            "entries": {
                "type": "array",
                "minItems": HKEX_BOUNDARY_DECISION_CASE_COUNT,
                "maxItems": HKEX_BOUNDARY_DECISION_CASE_COUNT,
                "items": entry,
            },
            "checkpoint_complete": {"const": True},
            "full_conformance_suite_complete": {"const": False},
            "activation_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-boundary-decision-catalogue.schema.json",
            "title": "HKEX record-boundary executable checkpoint catalogue",
            **_closed_schema(required, properties),
        }
    )


def build_boundary_decision_rule() -> dict[str, JsonValue]:
    """Declare the exact bounded authority of the 30-case checkpoint."""
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory-boundary-decision-rule",
            "schema_version": HKEX_BOUNDARY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_BOUNDARY_DECISION_RULE_ID,
            "status": "SOURCE_NEUTRAL_EXECUTABLE_CHECKPOINT",
            "accepted_adrs": ["0005", "0072", "0073", "0074", "0075"],
            "case_schema": "contracts/schemas/hkex-boundary-decision-case.schema.json",
            "report_schema": "contracts/schemas/hkex-boundary-decision-report.schema.json",
            "catalogue_schema": ("contracts/schemas/hkex-boundary-decision-catalogue.schema.json"),
            "catalogue": "catalogues/boundary-decision-cases.json",
            "required_case_count": HKEX_BOUNDARY_DECISION_CASE_COUNT,
            "required_primary_coverage_cell_count": HKEX_BOUNDARY_DECISION_CASE_COUNT,
            "required_high_risk_pairs": [f"HKREG-PAIR-{ordinal:03d}" for ordinal in range(25, 32)],
            "complete_structured_decision_match_required": True,
            "case_id_switching_forbidden": True,
            "boundary_decision_checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "source_authority": False,
            "activation_authority": False,
            "external_effects": "NONE",
        }
    )


@dataclass(frozen=True, slots=True)
class _RenderingCaseSpec:
    scope: HKEXRenderingAssertionScope
    facts: dict[str, JsonValue]
    expected: dict[str, JsonValue]


class _RenderingTerminalOptions(TypedDict, total=False):
    rejected: list[str]
    quarantined: list[str]


def _rendering_facts(**overrides: JsonValue) -> dict[str, JsonValue]:
    facts = _json_object(
        {
            "scope_id": HKEX_MAIN_SCOPE_ID,
            "component_label": "Synthetic Main Board Listing Rules",
            "location_label": "Rule 2.01",
            "official_heading": None,
            "effective_context": None,
            "dependency_lines": [],
            "references": [],
            "primary_lines": ["2.01 An issuer must comply with the Listing Rules."],
            "projection_kind": HKEXRenderingProjectionKind.ORDINARY.value,
            "required_element_ids": [],
            "present_element_ids": ["primary"],
            "presentation_only_element_ids": [],
            "forbidden_element_ids": [],
            "optional_chinese_evidence_present": False,
            "chinese_text_inserted": False,
            "chinese_duplicate_requested": False,
            "parallel_vector_requested": False,
            "source_ambiguity": False,
            "presentation_only_change": False,
            "material_projection_change": False,
            "authority_note": "None",
            "tokenizer_id": "synthetic-codepoint-counter-1",
            "tokenizer_fingerprint": _SYNTHETIC_PROFILE_FINGERPRINT,
            "max_text_tokens": 10_000,
            "max_metadata_bytes": 20_000,
        }
    )
    unknown = set(overrides).difference(facts)
    if unknown:
        raise _ConformanceBuildError(str(sorted(unknown)))
    facts.update(overrides)
    return facts


def _rendering_line(value: str) -> str:
    converted = normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip() for line in converted.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        raise _ConformanceBuildError
    return "\n".join(lines)


def _rendering_text(facts: dict[str, JsonValue]) -> str:
    scope_id = str(facts["scope_id"])
    market = "Main Board" if scope_id == HKEX_MAIN_SCOPE_ID else "GEM"
    lines = [
        "Context:",
        "Material: HKEX Listing Rule — non-statutory exchange regulatory rule",
        f"Market: {market}",
        f"Component: {_rendering_line(str(facts['component_label']))}",
        f"Location: {_rendering_line(str(facts['location_label']))}",
    ]
    heading = facts["official_heading"]
    if isinstance(heading, str):
        lines.append(f"Official heading: {_rendering_line(heading)}")
    effective = facts["effective_context"]
    if isinstance(effective, str):
        lines.append(f"Effective context: {_rendering_line(effective)}")
    blocks = ["\n".join(lines)]
    dependencies = [str(item) for item in _json_array(facts["dependency_lines"])]
    if dependencies:
        blocks.append(
            "Required governing context:\n"
            + "\n".join(_rendering_line(item) for item in dependencies)
        )
    references = [_json_object(item) for item in _json_array(facts["references"])]
    if references:
        reference_lines: list[str] = []
        for item in references:
            label = f"- {_rendering_line(str(item['locator']))}"
            reference_heading = item["official_heading"]
            if isinstance(reference_heading, str):
                label += f" — {_rendering_line(reference_heading)}"
            reference_lines.append(label)
        blocks.append("Referenced locations:\n" + "\n".join(reference_lines))
    primary = [str(item) for item in _json_array(facts["primary_lines"])]
    blocks.append(
        "English rule text — prevailing language:\n"
        + "\n".join(_rendering_line(item) for item in primary)
    )
    return "\n\n".join(blocks)


def _rendering_pass_expected(
    reason: HKEXRenderingReason, facts: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    text = _rendering_text(facts)
    authority_note = str(facts["authority_note"])
    max_text_tokens = _json_integer_value(facts["max_text_tokens"])
    max_metadata_bytes = _json_integer_value(facts["max_metadata_bytes"])
    payload = checked_json_value(
        {
            "authority_note": authority_note,
            "country": "Hong Kong",
            "jurisdiction": "Hong Kong",
            "source": "HKEX",
            "text": text,
            "type": "regulatory_material",
        }
    )
    assertion_scope = _rendering_scope_for_reason(reason)
    identity = HKEXRenderingIdentityConsequence.NOT_EVALUATED
    if bool(facts["material_projection_change"]) or (
        assertion_scope is HKEXRenderingAssertionScope.AUTHORITY_NOTE and authority_note != "None"
    ):
        identity = HKEXRenderingIdentityConsequence.NEW_RECORD_REQUIRED
    elif bool(facts["presentation_only_change"]) or bool(
        facts["optional_chinese_evidence_present"]
    ):
        identity = HKEXRenderingIdentityConsequence.PRESERVE_EXISTING
    return _json_object(
        {
            "outcome": HKEXRenderingOutcome.PASS.value,
            "reason": reason.value,
            "canonical_text": text,
            "authority_note": authority_note,
            "embedding_input": text,
            "text_tokens": len(text),
            "metadata_bytes": len(canonicalize(payload)),
            "text_limit": max_text_tokens,
            "metadata_limit": max_metadata_bytes,
            "fits": len(text) <= max_text_tokens
            and len(canonicalize(payload)) <= max_metadata_bytes,
            "omitted_element_ids": deepcopy(_json_array(facts["presentation_only_element_ids"])),
            "rejected_element_ids": deepcopy(_json_array(facts["forbidden_element_ids"])),
            "quarantined_element_ids": [],
            "identity_consequence": identity.value,
            "vector_responsibility": HKEXRenderingVectorResponsibility.ONE_ENGLISH_TEXT.value,
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "external_effects": "NONE",
        }
    )


def _rendering_scope_for_reason(reason: HKEXRenderingReason) -> HKEXRenderingAssertionScope:
    authority_reasons = {
        HKEXRenderingReason.AUTHORITY_NONE_SEPARATE,
        HKEXRenderingReason.AUTHORITY_WARNING_SEPARATE,
        HKEXRenderingReason.TRANSITION_WARNING_SEPARATE,
        HKEXRenderingReason.MARKET_WARNING_SEPARATE,
        HKEXRenderingReason.SOURCE_WARNING_SEPARATE,
        HKEXRenderingReason.REPRESENTATION_WARNING_SEPARATE,
    }
    return (
        HKEXRenderingAssertionScope.AUTHORITY_NOTE
        if reason in authority_reasons
        else HKEXRenderingAssertionScope.ORDINARY
    )


def _rendering_terminal_expected(
    outcome: HKEXRenderingOutcome,
    reason: HKEXRenderingReason,
    **options: Unpack[_RenderingTerminalOptions],
) -> dict[str, JsonValue]:
    return _json_object(
        {
            "outcome": outcome.value,
            "reason": reason.value,
            "canonical_text": None,
            "authority_note": None,
            "embedding_input": None,
            "text_tokens": None,
            "metadata_bytes": None,
            "text_limit": None,
            "metadata_limit": None,
            "fits": None,
            "omitted_element_ids": [],
            "rejected_element_ids": options.get("rejected", []),
            "quarantined_element_ids": options.get("quarantined", []),
            "identity_consequence": HKEXRenderingIdentityConsequence.NOT_EVALUATED.value,
            "vector_responsibility": HKEXRenderingVectorResponsibility.NONE.value,
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "external_effects": "NONE",
        }
    )


def _rendering_ordinary_specs() -> tuple[_RenderingCaseSpec, ...]:
    ordinary = HKEXRenderingAssertionScope.ORDINARY
    reference: JsonValue = {"locator": "Rule 3.01", "official_heading": "Qualifications"}
    cases: list[tuple[dict[str, JsonValue], HKEXRenderingReason]] = [
        (_rendering_facts(), HKEXRenderingReason.CANONICAL_RENDERED),
        (
            _rendering_facts(
                scope_id=HKEX_GEM_SCOPE_ID,
                component_label="Synthetic GEM Listing Rules",
            ),
            HKEXRenderingReason.BOARD_ISOLATION_PRESERVED,
        ),
        (
            _rendering_facts(official_heading="Continuing obligations"),
            HKEXRenderingReason.OFFICIAL_HEADING_INCLUDED,
        ),
        (
            _rendering_facts(present_element_ids=["heading-explicitly-absent", "primary"]),
            HKEXRenderingReason.OFFICIAL_HEADING_OMITTED,
        ),
        (
            _rendering_facts(effective_context="Applies to issuers listed before 1 January 2027"),
            HKEXRenderingReason.EFFECTIVE_CONTEXT_INCLUDED,
        ),
        (
            _rendering_facts(
                present_element_ids=["effective-context-explicitly-absent", "primary"]
            ),
            HKEXRenderingReason.EFFECTIVE_CONTEXT_OMITTED,
        ),
        (
            _rendering_facts(
                official_heading="Synthetic conformance fixture",
                dependency_lines=["Rule 2 — Synthetic ordinary fixture"],
                primary_lines=["2.01 An issuer must comply with the Exchange Listing Rules."],
            ),
            HKEXRenderingReason.GOVERNING_CONTEXT_INCLUDED,
        ),
        (
            _rendering_facts(present_element_ids=["dependency-explicitly-absent", "primary"]),
            HKEXRenderingReason.GOVERNING_CONTEXT_OMITTED,
        ),
        (_rendering_facts(references=[reference]), HKEXRenderingReason.REFERENCE_RENDERED),
        (
            _rendering_facts(present_element_ids=["primary", "reference-explicitly-absent"]),
            HKEXRenderingReason.REFERENCE_OMITTED,
        ),
        (
            _rendering_facts(
                primary_lines=["(1) An issuer MUST retain numbering; punctuation — exactly."],
                present_element_ids=["primary", "source-fidelity"],
            ),
            HKEXRenderingReason.SOURCE_FIDELITY_PRESERVED,
        ),
        (
            _rendering_facts(
                primary_lines=["Cafe\u0301 rule\r\nline two"],
                present_element_ids=["canonical-normalization", "primary"],
            ),
            HKEXRenderingReason.CANONICAL_NORMALIZED,
        ),
        (
            _rendering_facts(
                present_element_ids=["primary", "source-url", "web-control"],
                forbidden_element_ids=["source-url", "web-control"],
            ),
            HKEXRenderingReason.FORBIDDEN_CONTENT_EXCLUDED,
        ),
    ]
    return tuple(
        _RenderingCaseSpec(ordinary, facts, _rendering_pass_expected(reason, facts))
        for facts, reason in cases
    )


def _rendering_authority_specs() -> tuple[_RenderingCaseSpec, ...]:
    scope = HKEXRenderingAssertionScope.AUTHORITY_NOTE
    notes = (
        ("None", HKEXRenderingReason.AUTHORITY_NONE_SEPARATE),
        (
            "Approved warning: effective date depends on the stated transition.",
            HKEXRenderingReason.AUTHORITY_WARNING_SEPARATE,
        ),
    )
    return tuple(
        _RenderingCaseSpec(
            scope,
            (facts := _rendering_facts(authority_note=note)),
            _rendering_pass_expected(reason, facts),
        )
        for note, reason in notes
    )


def _rendering_measurement_specs() -> tuple[_RenderingCaseSpec, ...]:
    facts = _rendering_facts(
        present_element_ids=["complete-measurement", "primary"],
        authority_note="Approved measurement warning.",
    )
    return (
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.ORDINARY,
            facts,
            _rendering_pass_expected(HKEXRenderingReason.COMPLETE_MEASUREMENT, facts),
        ),
    )


def _rendering_table_specs() -> tuple[_RenderingCaseSpec, ...]:
    table_lines: list[JsonValue] = [
        "Table: Application fees",
        "Columns: Category | Amount | Unit",
        "Row 1: New applicant | HK$1,000 | per application",
        "Note: Amount is payable on submission.",
    ]
    complete = _rendering_facts(
        component_label="Synthetic Fees Table",
        location_label="Table 1",
        projection_kind=HKEXRenderingProjectionKind.TABLE.value,
        primary_lines=table_lines,
        required_element_ids=["caption", "header", "note", "row", "span", "unit"],
        present_element_ids=["caption", "header", "note", "row", "span", "unit"],
    )
    incomplete = _rendering_facts(
        projection_kind=HKEXRenderingProjectionKind.TABLE.value,
        primary_lines=["Row 1: HK$1,000"],
        required_element_ids=["header", "row", "unit"],
        present_element_ids=["row"],
    )
    span = _rendering_facts(
        projection_kind=HKEXRenderingProjectionKind.TABLE.value,
        primary_lines=[
            "Columns: Class | Category | Amount",
            "Span Class A -> Category 1: HK$100",
            "Span Class A -> Category 2: HK$200",
        ],
        required_element_ids=["header", "row-span", "rows"],
        present_element_ids=["header", "row-span", "rows"],
    )
    presentation = _rendering_facts(
        projection_kind=HKEXRenderingProjectionKind.TABLE.value,
        primary_lines=table_lines,
        required_element_ids=["caption", "header", "note", "row", "unit"],
        present_element_ids=["caption", "header", "note", "page-wrap", "row", "unit"],
        presentation_only_element_ids=["page-wrap"],
        presentation_only_change=True,
    )
    material = _rendering_facts(
        projection_kind=HKEXRenderingProjectionKind.TABLE.value,
        primary_lines=[
            *table_lines[:-2],
            "Row 1: New applicant | HK$1,100 | per application",
            table_lines[-1],
        ],
        required_element_ids=["caption", "header", "note", "row", "unit"],
        present_element_ids=["caption", "header", "note", "row", "unit"],
        material_projection_change=True,
    )
    return (
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.TABLE,
            complete,
            _rendering_pass_expected(HKEXRenderingReason.TABLE_COMPLETE, complete),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.TABLE,
            incomplete,
            _rendering_terminal_expected(
                HKEXRenderingOutcome.BLOCK,
                HKEXRenderingReason.TABLE_INCOMPLETE,
                rejected=["header", "unit"],
            ),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.TABLE,
            span,
            _rendering_pass_expected(HKEXRenderingReason.TABLE_SPAN_PRESERVED, span),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.TABLE,
            presentation,
            _rendering_pass_expected(HKEXRenderingReason.PRESENTATION_CHANGE_STABLE, presentation),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.TABLE,
            material,
            _rendering_pass_expected(HKEXRenderingReason.MATERIAL_TABLE_CHANGE, material),
        ),
    )


def _rendering_fee_specs() -> tuple[_RenderingCaseSpec, ...]:
    complete = _rendering_facts(
        component_label="Synthetic Fees Rules",
        location_label="Fee 2",
        projection_kind=HKEXRenderingProjectionKind.FEE.value,
        primary_lines=[
            "Fee category: Annual listing fee",
            "Amount: HK$5,000",
            "Basis: per listed class",
            "Timing: payable on 1 January",
            "Activation: while the class remains listed",
            "Note: No pro-rating applies.",
        ],
        required_element_ids=["activation", "amount", "basis", "currency", "note", "timing"],
        present_element_ids=["activation", "amount", "basis", "currency", "note", "timing"],
    )
    incomplete = _rendering_facts(
        projection_kind=HKEXRenderingProjectionKind.FEE.value,
        primary_lines=["Amount: 5,000"],
        required_element_ids=["amount", "basis", "currency", "note", "timing"],
        present_element_ids=["amount"],
    )
    return (
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.FEE,
            complete,
            _rendering_pass_expected(HKEXRenderingReason.FEE_COMPLETE, complete),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.FEE,
            incomplete,
            _rendering_terminal_expected(
                HKEXRenderingOutcome.BLOCK,
                HKEXRenderingReason.FEE_INCOMPLETE,
                rejected=["basis", "currency", "note", "timing"],
            ),
        ),
    )


def _rendering_form_specs() -> tuple[_RenderingCaseSpec, ...]:
    complete = _rendering_facts(
        component_label="Synthetic Regulatory Form",
        location_label="Form A — Part 1",
        projection_kind=HKEXRenderingProjectionKind.FORM.value,
        primary_lines=[
            "Instruction: Select the applicable category.",
            "Selection: [SELECTION CONTROL]",
            "Declaration: The applicant confirms the information is correct.",
            "Signature: [BLANK FIELD]",
        ],
        required_element_ids=["declaration", "selection"],
        present_element_ids=["declaration", "selection"],
    )
    presentation = _rendering_facts(
        projection_kind=HKEXRenderingProjectionKind.FORM.value,
        primary_lines=["Instruction: Complete the applicant name."],
        present_element_ids=["instruction", "web-blank"],
        presentation_only_element_ids=["web-blank"],
    )
    structure = _rendering_facts(
        projection_kind=HKEXRenderingProjectionKind.FORM.value,
        primary_lines=[
            "Part 2 — Certification",
            "Instruction: Complete every connected field.",
            "Declaration: The issuer certifies compliance.",
            "Signature: [BLANK FIELD]",
        ],
        required_element_ids=["declaration", "field-group", "instruction", "part", "signature"],
        present_element_ids=["declaration", "field-group", "instruction", "part", "signature"],
    )
    neutral = _rendering_facts(
        projection_kind=HKEXRenderingProjectionKind.FORM.value,
        primary_lines=["Applicant: [BLANK FIELD]", "Choice: [SELECTION CONTROL]"],
        required_element_ids=["neutral-marker"],
        present_element_ids=["neutral-marker"],
    )
    fragmented = _rendering_facts(
        projection_kind=HKEXRenderingProjectionKind.FORM.value,
        primary_lines=["[BLANK FIELD]"],
        required_element_ids=["field-group", "instruction"],
        present_element_ids=["blank-field"],
    )
    return (
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.FORM,
            complete,
            _rendering_pass_expected(HKEXRenderingReason.FORM_COMPLETE, complete),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.FORM,
            presentation,
            _rendering_pass_expected(
                HKEXRenderingReason.PRESENTATION_CONTROL_OMITTED, presentation
            ),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.FORM,
            structure,
            _rendering_pass_expected(HKEXRenderingReason.FORM_STRUCTURE_COMPLETE, structure),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.FORM,
            neutral,
            _rendering_pass_expected(HKEXRenderingReason.NEUTRAL_MARKERS_PRESERVED, neutral),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.FORM,
            fragmented,
            _rendering_terminal_expected(
                HKEXRenderingOutcome.BLOCK,
                HKEXRenderingReason.FORM_FRAGMENTATION_REJECTED,
                rejected=["field-group", "instruction"],
            ),
        ),
    )


def _rendering_language_and_uncertainty_specs() -> tuple[_RenderingCaseSpec, ...]:
    english = _rendering_facts(optional_chinese_evidence_present=True)
    chinese = _rendering_facts(
        chinese_text_inserted=True,
        chinese_duplicate_requested=True,
        parallel_vector_requested=True,
    )
    ambiguous = _rendering_facts(
        source_ambiguity=True,
        present_element_ids=["ambiguous-branch"],
    )
    return (
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.LANGUAGE,
            english,
            _rendering_pass_expected(HKEXRenderingReason.ENGLISH_ONLY_SERVING, english),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.LANGUAGE,
            chinese,
            _rendering_terminal_expected(
                HKEXRenderingOutcome.BLOCK,
                HKEXRenderingReason.CHINESE_SERVING_REJECTED,
                rejected=["chinese-text", "chinese-duplicate", "parallel-vector"],
            ),
        ),
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.UNCERTAINTY,
            ambiguous,
            _rendering_terminal_expected(
                HKEXRenderingOutcome.QUARANTINE,
                HKEXRenderingReason.SOURCE_AMBIGUITY_QUARANTINED,
                quarantined=["ambiguous-branch"],
            ),
        ),
    )


def _rendering_controlled_warning_specs() -> tuple[_RenderingCaseSpec, ...]:
    notes = (
        (
            "Effective-date limitation: applies only during the stated transition.",
            HKEXRenderingReason.TRANSITION_WARNING_SEPARATE,
        ),
        (
            "Market-scope limitation: Main Board scope only.",
            HKEXRenderingReason.MARKET_WARNING_SEPARATE,
        ),
        (
            "Source limitation: official representation remains under review.",
            HKEXRenderingReason.SOURCE_WARNING_SEPARATE,
        ),
        (
            "Representation limitation: one referenced location remains unresolved.",
            HKEXRenderingReason.REPRESENTATION_WARNING_SEPARATE,
        ),
    )
    return tuple(
        _RenderingCaseSpec(
            HKEXRenderingAssertionScope.AUTHORITY_NOTE,
            (facts := _rendering_facts(authority_note=note)),
            _rendering_pass_expected(reason, facts),
        )
        for note, reason in notes
    )


def _rendering_case_specs() -> tuple[_RenderingCaseSpec, ...]:
    specs = (
        *_rendering_ordinary_specs(),
        *_rendering_authority_specs(),
        *_rendering_measurement_specs(),
        *_rendering_table_specs(),
        *_rendering_fee_specs(),
        *_rendering_form_specs(),
        *_rendering_language_and_uncertainty_specs(),
        *_rendering_controlled_warning_specs(),
    )
    if len(specs) != HKEX_RENDERING_DECISION_CASE_COUNT:
        raise _ConformanceBuildError(str(len(specs)))
    return specs


def _rendering_contract_bindings(universe_fingerprint: str) -> list[JsonValue]:
    seed = _json_object(
        {
            "contract_id": "asklegal.hk-regulatory.rendering-decision-case",
            "contract_version": HKEX_RENDERING_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_RENDERING_DECISION_RULE_ID,
        }
    )
    return [
        {
            "contract_id": "asklegal.hk-regulatory.conformance-universe",
            "version": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
            "fingerprint": universe_fingerprint,
        },
        {
            "contract_id": "asklegal.hk-regulatory.rendering-decision-case",
            "version": HKEX_RENDERING_DECISION_CONTRACT_VERSION,
            "fingerprint": _fingerprint(rfc8785.dumps(seed)),
        },
    ]


def _rendering_expected_document(
    case_id: str, expected: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.rendering-decision-result",
            "schema_version": HKEX_RENDERING_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_RENDERING_DECISION_RULE_ID,
            "case_id": case_id,
            **deepcopy(expected),
        }
    )


def build_rendering_decision_cases() -> tuple[
    tuple[dict[str, JsonValue], dict[str, JsonValue]], ...
]:
    """Build all 35 permanent canonical-rendering cases and frozen reports."""
    universe = build_conformance_universe()
    all_cases = _json_array(universe["cases"])
    start = (
        HKEX_SOURCE_DECISION_CASE_COUNT
        + HKEX_STATE_DECISION_CASE_COUNT
        + HKEX_BOUNDARY_DECISION_CASE_COUNT
    )
    universe_cases = tuple(
        _json_object(item) for item in all_cases[start : start + HKEX_RENDERING_DECISION_CASE_COUNT]
    )
    specs = _rendering_case_specs()
    universe_fingerprint = _fingerprint(rfc8785.dumps(universe))
    bindings = _rendering_contract_bindings(universe_fingerprint)
    results: list[tuple[dict[str, JsonValue], dict[str, JsonValue]]] = []
    for universe_case, spec in zip(universe_cases, specs, strict=True):
        case_id = str(universe_case["case_id"])
        facts = deepcopy(spec.facts)
        expected = _rendering_expected_document(case_id, spec.expected)
        fixture = _json_object(
            {
                "schema_id": "asklegal.hk-regulatory.rendering-decision-case",
                "schema_version": HKEX_RENDERING_DECISION_CONTRACT_VERSION,
                "package_contract_version": "1.0.0",
                "case_id": case_id,
                "suite_layer": "DECISION_TO_ARTIFACT",
                "primary_checkpoint": "CANONICAL_RENDERING",
                "frozen": True,
                "synthetic_evidence_class": "SYNTHETIC_NO_REAL_AUTHORITY",
                "contract_bindings": deepcopy(bindings),
                "synthetic_cutoff": "2026-08-24T00:00:00Z",
                "scope_id": "HKEX_CROSS_BOARD",
                "prior_state": "SYNTHETIC_ACCEPTED_PREDECESSOR",
                "primary_coverage_cell_ids": [universe_case["coverage_cell_id"]],
                "secondary_coverage_cell_ids": [],
                "pair_memberships": deepcopy(universe_case["pair_memberships"]),
                "declared_input_inventory": ["rendering-evidence"],
                "declared_reference_inventory": [
                    "asklegal.hk-regulatory.conformance-universe",
                    "asklegal.hk-regulatory.rendering-decision-case",
                ],
                "declared_expected_inventory": ["RENDERING_DECISION_REPORT"],
                "assertion_scope": spec.scope.value,
                "required_result_dimensions": [
                    "AUTHORITY_NOTE",
                    "CANONICAL_BYTES",
                    "IDENTITY_CONSEQUENCE",
                    "MEASUREMENT",
                    "PROCESSING",
                    "SOURCE_FIDELITY",
                    "VECTOR_RESPONSIBILITY",
                ],
                "evidence_packet_fields": sorted(facts),
                "supporting_evidence_ranges": [f"input/{case_id}-rendering-evidence.json#facts"],
                "rule_trace": ["HKREG-ENGLISH-RECORD-001", HKEX_RENDERING_DECISION_RULE_ID],
                "established_facts": ["SYNTHETIC_RENDERING_FACT_PACKET_DECLARED"],
                "unresolved_facts": (
                    [str(spec.expected["reason"])]
                    if spec.expected["outcome"] in {"BLOCK", "QUARANTINE"}
                    else []
                ),
                "permitted_equivalent_results": [],
                "critical_error_codes": (
                    [str(spec.expected["reason"])]
                    if spec.expected["outcome"] in {"BLOCK", "QUARANTINE"}
                    else []
                ),
                "package_fingerprint": universe_fingerprint,
                "title": universe_case["synthetic_scenario"],
                "purpose": universe_case["exact_required_result"],
                "expected_decision": expected,
                "evidence_packet": {
                    "slot_id": "rendering-evidence",
                    "state": "AVAILABLE",
                    "path": f"input/{case_id}-rendering-evidence.json",
                    "role": "ORDINARY",
                    "media_type": "application/json",
                    "content_fingerprint": _fingerprint(rfc8785.dumps(facts)),
                },
                "facts": facts,
                "case_fingerprint": "PENDING",
            }
        )
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        parsed = hkex_rendering_decision_case_from_document(fixture)
        report = _json_object(run_hkex_rendering_case(parsed).document())
        if report["conformance_status"] != "PASS":
            failure = f"{case_id}:{spec.expected['reason']}"
            raise _ConformanceBuildError(failure)
        results.append((fixture, report))
    if len(results) != HKEX_RENDERING_DECISION_CASE_COUNT:
        raise _ConformanceBuildError
    return tuple(results)


def build_rendering_decision_catalogue(
    cases: tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...],
) -> dict[str, JsonValue]:
    """Bind all 35 exact rendering fact packets and reports."""
    entries: list[JsonValue] = []
    pair_ids: set[str] = set()
    for fixture, report in cases:
        case_id = str(fixture["case_id"])
        fixture_path = f"fixtures/conformance/rendering-decision/{case_id}.json"
        expected_path = f"expected/conformance/rendering-decision/{case_id}.json"
        expected = _json_object(fixture["expected_decision"])
        memberships = deepcopy(_json_array(fixture["pair_memberships"]))
        for membership in memberships:
            pair_ids.add(str(_json_object(membership)["pair_id"]))
        fixture_bytes = (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode()
        report_bytes = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
        entries.append(
            {
                "case_id": case_id,
                "primary_coverage_cell_id": _json_array(fixture["primary_coverage_cell_ids"])[0],
                "pair_memberships": memberships,
                "assertion_scope": fixture["assertion_scope"],
                "expected_outcome": expected["outcome"],
                "expected_reason": expected["reason"],
                "fixture_path": fixture_path,
                "fixture_fingerprint": _fingerprint(fixture_bytes),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint(report_bytes),
            }
        )
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.rendering-decision-catalogue",
            "schema_version": HKEX_RENDERING_DECISION_CONTRACT_VERSION,
            "catalogue_id": "hk-regulatory-rendering-decision",
            "catalogue_version": "1.0.0",
            "status": "FROZEN_EXECUTABLE_CHECKPOINT",
            "case_count": HKEX_RENDERING_DECISION_CASE_COUNT,
            "primary_coverage_cell_count": HKEX_RENDERING_DECISION_CASE_COUNT,
            "high_risk_pair_ids": sorted(pair_ids),
            "entries": entries,
            "checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "activation_authorized": False,
            "external_effects": "NONE",
        }
    )


def _rendering_reference_schema() -> dict[str, JsonValue]:
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    return _closed_schema(
        ["locator", "official_heading"],
        _json_object(
            {
                "locator": nonempty,
                "official_heading": {"oneOf": [nonempty, {"type": "null"}]},
            }
        ),
    )


def _rendering_result_schema() -> dict[str, JsonValue]:
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    string_array: JsonValue = {
        "type": "array",
        "uniqueItems": True,
        "items": nonempty,
    }
    nullable_text: JsonValue = {"oneOf": [nonempty, {"type": "null"}]}
    nullable_count: JsonValue = {"oneOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]}
    required = [
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
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.rendering-decision-result"},
            "schema_version": {"const": HKEX_RENDERING_DECISION_CONTRACT_VERSION},
            "rule_id": {"const": HKEX_RENDERING_DECISION_RULE_ID},
            "case_id": {
                "type": "string",
                "pattern": "^HKREG-DET-RND-(0[0-2][0-9]|03[0-5])$",
            },
            "outcome": {"enum": [item.value for item in HKEXRenderingOutcome]},
            "reason": {"enum": [item.value for item in HKEXRenderingReason]},
            "canonical_text": nullable_text,
            "authority_note": nullable_text,
            "embedding_input": nullable_text,
            "text_tokens": nullable_count,
            "metadata_bytes": nullable_count,
            "text_limit": nullable_count,
            "metadata_limit": nullable_count,
            "fits": {"oneOf": [{"type": "boolean"}, {"type": "null"}]},
            "omitted_element_ids": string_array,
            "rejected_element_ids": string_array,
            "quarantined_element_ids": string_array,
            "identity_consequence": {
                "enum": [item.value for item in HKEXRenderingIdentityConsequence]
            },
            "vector_responsibility": {
                "enum": [item.value for item in HKEXRenderingVectorResponsibility]
            },
            "search_record_authorized": {"const": False},
            "embedding_authorized": {"const": False},
            "release_authorized": {"const": False},
            "serving_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _closed_schema(required, properties)


def _rendering_facts_schema() -> dict[str, JsonValue]:
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    strings: JsonValue = {
        "type": "array",
        "uniqueItems": True,
        "items": nonempty,
    }
    required = [
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
    ]
    nullable_text = {"oneOf": [nonempty, {"type": "null"}]}
    boolean = {"type": "boolean"}
    properties = _json_object(
        {
            "scope_id": {"enum": [HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID]},
            "component_label": nonempty,
            "location_label": nonempty,
            "official_heading": nullable_text,
            "effective_context": nullable_text,
            "dependency_lines": strings,
            "references": {"type": "array", "items": _rendering_reference_schema()},
            "primary_lines": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": nonempty,
            },
            "projection_kind": {"enum": [item.value for item in HKEXRenderingProjectionKind]},
            "required_element_ids": strings,
            "present_element_ids": strings,
            "presentation_only_element_ids": strings,
            "forbidden_element_ids": strings,
            "optional_chinese_evidence_present": boolean,
            "chinese_text_inserted": boolean,
            "chinese_duplicate_requested": boolean,
            "parallel_vector_requested": boolean,
            "source_ambiguity": boolean,
            "presentation_only_change": boolean,
            "material_projection_change": boolean,
            "authority_note": nonempty,
            "tokenizer_id": nonempty,
            "tokenizer_fingerprint": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "max_text_tokens": {"type": "integer", "minimum": 1},
            "max_metadata_bytes": {"type": "integer", "minimum": 1},
        }
    )
    return _closed_schema(required, properties)


def build_rendering_decision_case_schema() -> dict[str, JsonValue]:
    """Build the strict common envelope for all 35 rendering cases."""
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    fingerprint_schema: JsonValue = {
        "type": "string",
        "pattern": "^sha256:[0-9a-f]{64}$",
    }
    string_array: JsonValue = {"type": "array", "uniqueItems": True, "items": nonempty}
    binding = _closed_schema(
        ["contract_id", "version", "fingerprint"],
        _json_object(
            {
                "contract_id": nonempty,
                "version": nonempty,
                "fingerprint": fingerprint_schema,
            }
        ),
    )
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": {"type": "string", "pattern": "^HKREG-PAIR-0(3[2-7]|57)$"},
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    packet = _closed_schema(
        ["slot_id", "state", "path", "role", "media_type", "content_fingerprint"],
        _json_object(
            {
                "slot_id": {"const": "rendering-evidence"},
                "state": {"const": "AVAILABLE"},
                "path": nonempty,
                "role": {"const": "ORDINARY"},
                "media_type": {"const": "application/json"},
                "content_fingerprint": fingerprint_schema,
            }
        ),
    )
    required = [
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
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.rendering-decision-case"},
            "schema_version": {"const": HKEX_RENDERING_DECISION_CONTRACT_VERSION},
            "package_contract_version": {"const": "1.0.0"},
            "case_id": {
                "type": "string",
                "pattern": "^HKREG-DET-RND-(0[0-2][0-9]|03[0-5])$",
            },
            "suite_layer": {"const": "DECISION_TO_ARTIFACT"},
            "primary_checkpoint": {"const": "CANONICAL_RENDERING"},
            "frozen": {"const": True},
            "synthetic_evidence_class": {"const": "SYNTHETIC_NO_REAL_AUTHORITY"},
            "contract_bindings": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": binding,
            },
            "synthetic_cutoff": {"const": "2026-08-24T00:00:00Z"},
            "scope_id": {"const": "HKEX_CROSS_BOARD"},
            "prior_state": {"const": "SYNTHETIC_ACCEPTED_PREDECESSOR"},
            "primary_coverage_cell_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": nonempty,
            },
            "secondary_coverage_cell_ids": string_array,
            "pair_memberships": {
                "type": "array",
                "maxItems": 1,
                "uniqueItems": True,
                "items": pair,
            },
            "declared_input_inventory": {"const": ["rendering-evidence"]},
            "declared_reference_inventory": {
                "const": [
                    "asklegal.hk-regulatory.conformance-universe",
                    "asklegal.hk-regulatory.rendering-decision-case",
                ]
            },
            "declared_expected_inventory": {"const": ["RENDERING_DECISION_REPORT"]},
            "assertion_scope": {"enum": [item.value for item in HKEXRenderingAssertionScope]},
            "required_result_dimensions": {
                "const": [
                    "AUTHORITY_NOTE",
                    "CANONICAL_BYTES",
                    "IDENTITY_CONSEQUENCE",
                    "MEASUREMENT",
                    "PROCESSING",
                    "SOURCE_FIDELITY",
                    "VECTOR_RESPONSIBILITY",
                ]
            },
            "evidence_packet_fields": string_array,
            "supporting_evidence_ranges": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": nonempty,
            },
            "rule_trace": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": nonempty,
            },
            "established_facts": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": nonempty,
            },
            "unresolved_facts": string_array,
            "permitted_equivalent_results": {"const": []},
            "critical_error_codes": string_array,
            "package_fingerprint": fingerprint_schema,
            "title": nonempty,
            "purpose": nonempty,
            "expected_decision": _rendering_result_schema(),
            "evidence_packet": packet,
            "facts": _rendering_facts_schema(),
            "case_fingerprint": fingerprint_schema,
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-rendering-decision-case.schema.json",
            "title": "HKEX canonical-rendering conformance case",
            **_closed_schema(required, properties),
        }
    )


def build_rendering_decision_report_schema() -> dict[str, JsonValue]:
    """Build the exact effect-free rendering report schema."""
    required = [
        "schema_id",
        "schema_version",
        "rule_id",
        "case_id",
        "assertion_scope",
        "observed_decision",
        "expected_decision",
        "conformance_status",
        "source_authorized",
        "provider_authorized",
        "release_authorized",
        "serving_authorized",
        "deployment_authorized",
        "external_effects",
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.rendering-decision-report"},
            "schema_version": {"const": HKEX_RENDERING_DECISION_CONTRACT_VERSION},
            "rule_id": {"const": HKEX_RENDERING_DECISION_RULE_ID},
            "case_id": {
                "type": "string",
                "pattern": "^HKREG-DET-RND-(0[0-2][0-9]|03[0-5])$",
            },
            "assertion_scope": {"enum": [item.value for item in HKEXRenderingAssertionScope]},
            "observed_decision": _rendering_result_schema(),
            "expected_decision": _rendering_result_schema(),
            "conformance_status": {"enum": ["PASS", "FAIL"]},
            "source_authorized": {"const": False},
            "provider_authorized": {"const": False},
            "release_authorized": {"const": False},
            "serving_authorized": {"const": False},
            "deployment_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-rendering-decision-report.schema.json",
            "title": "HKEX canonical-rendering conformance report",
            **_closed_schema(required, properties),
        }
    )


def build_rendering_decision_catalogue_schema() -> dict[str, JsonValue]:
    """Build the strict 35-entry rendering checkpoint catalogue schema."""
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    fingerprint_schema: JsonValue = {
        "type": "string",
        "pattern": "^sha256:[0-9a-f]{64}$",
    }
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": nonempty,
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    entry = _closed_schema(
        [
            "case_id",
            "primary_coverage_cell_id",
            "pair_memberships",
            "assertion_scope",
            "expected_outcome",
            "expected_reason",
            "fixture_path",
            "fixture_fingerprint",
            "expected_path",
            "expected_fingerprint",
        ],
        _json_object(
            {
                "case_id": nonempty,
                "primary_coverage_cell_id": nonempty,
                "pair_memberships": {
                    "type": "array",
                    "maxItems": 1,
                    "uniqueItems": True,
                    "items": pair,
                },
                "assertion_scope": {"enum": [item.value for item in HKEXRenderingAssertionScope]},
                "expected_outcome": {"enum": [item.value for item in HKEXRenderingOutcome]},
                "expected_reason": {"enum": [item.value for item in HKEXRenderingReason]},
                "fixture_path": nonempty,
                "fixture_fingerprint": fingerprint_schema,
                "expected_path": nonempty,
                "expected_fingerprint": fingerprint_schema,
            }
        ),
    )
    required = [
        "schema_id",
        "schema_version",
        "catalogue_id",
        "catalogue_version",
        "status",
        "case_count",
        "primary_coverage_cell_count",
        "high_risk_pair_ids",
        "entries",
        "checkpoint_complete",
        "full_conformance_suite_complete",
        "activation_authorized",
        "external_effects",
    ]
    properties = _json_object(
        {
            "schema_id": {"const": "asklegal.hk-regulatory.rendering-decision-catalogue"},
            "schema_version": {"const": HKEX_RENDERING_DECISION_CONTRACT_VERSION},
            "catalogue_id": {"const": "hk-regulatory-rendering-decision"},
            "catalogue_version": {"const": "1.0.0"},
            "status": {"const": "FROZEN_EXECUTABLE_CHECKPOINT"},
            "case_count": {"const": HKEX_RENDERING_DECISION_CASE_COUNT},
            "primary_coverage_cell_count": {"const": HKEX_RENDERING_DECISION_CASE_COUNT},
            "high_risk_pair_ids": {
                "type": "array",
                "minItems": 7,
                "maxItems": 7,
                "uniqueItems": True,
                "items": nonempty,
            },
            "entries": {
                "type": "array",
                "minItems": HKEX_RENDERING_DECISION_CASE_COUNT,
                "maxItems": HKEX_RENDERING_DECISION_CASE_COUNT,
                "items": entry,
            },
            "checkpoint_complete": {"const": True},
            "full_conformance_suite_complete": {"const": False},
            "activation_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-rendering-decision-catalogue.schema.json",
            "title": "HKEX canonical-rendering executable checkpoint catalogue",
            **_closed_schema(required, properties),
        }
    )


def build_rendering_decision_rule() -> dict[str, JsonValue]:
    """Declare the exact bounded authority of the 35-case checkpoint."""
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory-rendering-decision-rule",
            "schema_version": HKEX_RENDERING_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_RENDERING_DECISION_RULE_ID,
            "status": "SOURCE_NEUTRAL_EXECUTABLE_CHECKPOINT",
            "accepted_adrs": ["0011", "0050", "0073", "0074", "0075"],
            "case_schema": "contracts/schemas/hkex-rendering-decision-case.schema.json",
            "report_schema": "contracts/schemas/hkex-rendering-decision-report.schema.json",
            "catalogue_schema": ("contracts/schemas/hkex-rendering-decision-catalogue.schema.json"),
            "catalogue": "catalogues/rendering-decision-cases.json",
            "required_case_count": HKEX_RENDERING_DECISION_CASE_COUNT,
            "required_primary_coverage_cell_count": HKEX_RENDERING_DECISION_CASE_COUNT,
            "required_high_risk_pairs": [
                "HKREG-PAIR-032",
                "HKREG-PAIR-033",
                "HKREG-PAIR-034",
                "HKREG-PAIR-035",
                "HKREG-PAIR-036",
                "HKREG-PAIR-037",
                "HKREG-PAIR-057",
            ],
            "complete_structured_decision_match_required": True,
            "case_id_switching_forbidden": True,
            "rendering_decision_checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "source_authority": False,
            "activation_authority": False,
            "external_effects": "NONE",
        }
    )


@dataclass(frozen=True, slots=True)
class _PartitionCaseSpec:
    scope: HKEXPartitionAssertionScope
    facts: dict[str, JsonValue]
    expected_outcome: HKEXPartitionOutcome
    expected_reason: HKEXPartitionReason


def _partition_request(
    tree: HKEXEnglishSourceTree,
    *,
    max_text_tokens: int = 100_000,
    max_metadata_bytes: int = 100_000,
    authority_note: str = "None",
) -> HKEXEnglishConstructionRequest:
    return HKEXEnglishConstructionRequest(
        tree,
        _english_profile(
            max_text_tokens=max_text_tokens,
            max_metadata_bytes=max_metadata_bytes,
            authority_note=authority_note,
        ),
        None,
    )


def _partition_facts(
    requests: tuple[HKEXEnglishConstructionRequest, ...],
    *,
    cut: HKEXPartitionCandidateCut = HKEXPartitionCandidateCut.NONE,
    official_boundary: bool = False,
    measurement_fields: tuple[str, ...] = HKEX_PARTITION_MEASUREMENT_FIELDS,
    preliminary_part_count: int = 0,
) -> dict[str, JsonValue]:
    return _json_object(
        {
            "requests": [request.document() for request in requests],
            "measurement_field_ids": list(measurement_fields),
            "candidate_cut": cut.value,
            "candidate_official_boundary_proved": official_boundary,
            "preliminary_part_count": preliminary_part_count,
        }
    )


def _partition_case_specs() -> tuple[_PartitionCaseSpec, ...]:
    flat = _english_tree(HKEXBranchState.CURRENT, partition=True)
    ordinary = _partition_request(_english_tree(HKEXBranchState.CURRENT))
    unlimited = _partition_request(flat)
    unsplit = (
        construct_hkex_english_request(unlimited, _SyntheticCodepointCounter())
        .record_results[0]
        .parts[0]
    )
    exact = _partition_request(
        flat,
        max_text_tokens=unsplit.measurement.text_tokens,
        max_metadata_bytes=unsplit.measurement.metadata_bytes,
    )
    token_only = _partition_request(flat, max_text_tokens=600, max_metadata_bytes=1_000)
    metadata_only = _partition_request(flat, max_text_tokens=1_000, max_metadata_bytes=876)
    dual = _partition_request(flat, max_text_tokens=600, max_metadata_bytes=800)
    label_recomputed = _partition_request(flat, max_text_tokens=580)
    two_parts = _partition_request(flat, max_text_tokens=600)
    three_parts = _partition_request(
        _english_tree(HKEXBranchState.CURRENT, partition=True, branch_suffix="-deep"),
        max_text_tokens=550,
    )
    nested_refined = _partition_request(_nested_partition_tree(), max_text_tokens=600)
    nested_largest = _partition_request(
        _nested_partition_tree(branch_suffix="-largest"), max_text_tokens=700
    )
    indivisible = _partition_request(
        _english_tree(HKEXBranchState.CURRENT, partition=True, branch_suffix="-indivisible"),
        max_text_tokens=450,
    )
    fixed_metadata = _partition_request(
        _english_tree(HKEXBranchState.CURRENT, partition=True, branch_suffix="-fixed-metadata"),
        max_metadata_bytes=200,
        authority_note="Source limitation: " + "M" * 600,
    )
    complete = HKEX_PARTITION_MEASUREMENT_FIELDS
    incomplete = tuple(item for item in complete if item != "AUTHORITY_NOTE")

    def spec(
        scope: HKEXPartitionAssertionScope,
        requests: tuple[HKEXEnglishConstructionRequest, ...],
        outcome: HKEXPartitionOutcome,
        reason: HKEXPartitionReason,
        **options: JsonValue,
    ) -> _PartitionCaseSpec:
        return _PartitionCaseSpec(
            scope,
            _partition_facts(
                requests,
                cut=HKEXPartitionCandidateCut(str(options.get("cut", "NONE"))),
                official_boundary=bool(options.get("official_boundary", False)),
                measurement_fields=tuple(
                    str(item)
                    for item in _json_array(options.get("measurement_fields", list(complete)))
                ),
                preliminary_part_count=_json_integer_value(
                    options.get("preliminary_part_count", 0)
                ),
            ),
            outcome,
            reason,
        )

    return (
        spec(
            HKEXPartitionAssertionScope.EXACT_FIT,
            (exact,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.EXACT_FIT_UNSPLIT,
        ),
        spec(
            HKEXPartitionAssertionScope.TOKEN_OVERFLOW,
            (token_only,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.TOKEN_OVERFLOW_PARTITIONED,
        ),
        spec(
            HKEXPartitionAssertionScope.METADATA_OVERFLOW,
            (metadata_only,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.METADATA_OVERFLOW_PARTITIONED,
        ),
        spec(
            HKEXPartitionAssertionScope.DUAL_OVERFLOW,
            (dual,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.DUAL_OVERFLOW_PARTITIONED,
        ),
        spec(
            HKEXPartitionAssertionScope.MEASUREMENT_COMPLETENESS,
            (ordinary,),
            HKEXPartitionOutcome.BLOCK,
            HKEXPartitionReason.INCOMPLETE_MEASUREMENT_REJECTED,
            measurement_fields=list(incomplete),
        ),
        spec(
            HKEXPartitionAssertionScope.FINAL_LABELS,
            (label_recomputed,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.LABEL_OVERFLOW_RECOMPUTED,
            preliminary_part_count=2,
        ),
        spec(
            HKEXPartitionAssertionScope.CHILD_WHOLE,
            (two_parts,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.COMPLETE_CHILD_PRESERVED,
        ),
        spec(
            HKEXPartitionAssertionScope.OVERSIZED_CHILD,
            (nested_refined,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.OVERSIZED_CHILD_ONLY_REFINED,
        ),
        spec(
            HKEXPartitionAssertionScope.LARGEST_FRONTIER,
            (nested_largest,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.LARGEST_SAFE_FRONTIER_USED,
        ),
        spec(
            HKEXPartitionAssertionScope.FEWEST_PARTS,
            (two_parts,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.FEWEST_PARTS_SELECTED,
        ),
        spec(
            HKEXPartitionAssertionScope.EARLIEST_FULL,
            (two_parts,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.EARLIEST_FULL_SELECTED,
        ),
        spec(
            HKEXPartitionAssertionScope.BRANCH_ISOLATION,
            (two_parts, three_parts),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.BRANCH_DEPTHS_INDEPENDENT,
        ),
        spec(
            HKEXPartitionAssertionScope.FINAL_REMEASUREMENT,
            (two_parts,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.FINAL_LABELS_REMEASURED,
        ),
        spec(
            HKEXPartitionAssertionScope.NORMAL_BOUNDARY,
            (ordinary,),
            HKEXPartitionOutcome.BLOCK,
            HKEXPartitionReason.CROSS_NORMAL_BOUNDARY_REJECTED,
            cut=HKEXPartitionCandidateCut.CROSS_NORMAL_UNIT.value,
        ),
        spec(
            HKEXPartitionAssertionScope.UNRELATED_PACKING,
            (ordinary,),
            HKEXPartitionOutcome.BLOCK,
            HKEXPartitionReason.UNRELATED_PACKING_REJECTED,
            cut=HKEXPartitionCandidateCut.UNRELATED_PACKING.value,
        ),
        spec(
            HKEXPartitionAssertionScope.OFFICIAL_BOUNDARY,
            (two_parts,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.OFFICIAL_BOUNDARY_PARTITIONED,
            cut=HKEXPartitionCandidateCut.OFFICIAL_CHILD.value,
            official_boundary=True,
        ),
        spec(
            HKEXPartitionAssertionScope.ARBITRARY_PAGE,
            (ordinary,),
            HKEXPartitionOutcome.BLOCK,
            HKEXPartitionReason.PDF_PAGE_CUT_REJECTED,
            cut=HKEXPartitionCandidateCut.PDF_PAGE.value,
        ),
        spec(
            HKEXPartitionAssertionScope.ARBITRARY_SENTENCE,
            (ordinary,),
            HKEXPartitionOutcome.BLOCK,
            HKEXPartitionReason.SENTENCE_PUNCTUATION_CUT_REJECTED,
            cut=HKEXPartitionCandidateCut.SENTENCE_OR_PUNCTUATION.value,
        ),
        spec(
            HKEXPartitionAssertionScope.ARBITRARY_SIZE,
            (ordinary,),
            HKEXPartitionOutcome.BLOCK,
            HKEXPartitionReason.WHITESPACE_TOKEN_SIZE_CUT_REJECTED,
            cut=HKEXPartitionCandidateCut.WHITESPACE_TOKEN_OR_PREFERRED.value,
        ),
        spec(
            HKEXPartitionAssertionScope.ARBITRARY_WINDOW,
            (ordinary,),
            HKEXPartitionOutcome.BLOCK,
            HKEXPartitionReason.CHARACTER_VISUAL_WINDOW_CUT_REJECTED,
            cut=HKEXPartitionCandidateCut.CHARACTER_VISUAL_OR_WINDOW.value,
        ),
        spec(
            HKEXPartitionAssertionScope.CONTEXT_PRESERVATION,
            (ordinary,),
            HKEXPartitionOutcome.BLOCK,
            HKEXPartitionReason.CONTEXT_REMOVAL_REJECTED,
            cut=HKEXPartitionCandidateCut.REMOVE_CONTEXT.value,
        ),
        spec(
            HKEXPartitionAssertionScope.RECURSION,
            (nested_refined,),
            HKEXPartitionOutcome.PASS,
            HKEXPartitionReason.RECURSIVE_OFFICIAL_PARTITIONED,
            cut=HKEXPartitionCandidateCut.OFFICIAL_CHILD.value,
            official_boundary=True,
        ),
        spec(
            HKEXPartitionAssertionScope.INDIVISIBLE,
            (indivisible,),
            HKEXPartitionOutcome.QUARANTINE,
            HKEXPartitionReason.SMALLEST_COMPLETE_UNIT_QUARANTINED,
            cut=HKEXPartitionCandidateCut.OFFICIAL_CHILD.value,
            official_boundary=True,
        ),
        spec(
            HKEXPartitionAssertionScope.FIXED_METADATA,
            (fixed_metadata,),
            HKEXPartitionOutcome.QUARANTINE,
            HKEXPartitionReason.FIXED_METADATA_OVER_LIMIT,
            cut=HKEXPartitionCandidateCut.OFFICIAL_CHILD.value,
            official_boundary=True,
        ),
    )


def _partition_contract_bindings(universe_fingerprint: str) -> list[JsonValue]:
    partition_seed = checked_json_value(
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
    return [
        {
            "contract_id": "asklegal.hk-regulatory.conformance-universe",
            "version": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
            "fingerprint": universe_fingerprint,
        },
        {
            "contract_id": "asklegal.hk-regulatory.partition-decision-case",
            "version": HKEX_PARTITION_DECISION_CONTRACT_VERSION,
            "fingerprint": _fingerprint(rfc8785.dumps(partition_seed)),
        },
        {
            "contract_id": "asklegal.hk-regulatory.english-record",
            "version": HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            "fingerprint": _fingerprint(rfc8785.dumps(english_seed)),
        },
    ]


def _partition_seed_expected(case_id: str, spec: _PartitionCaseSpec) -> dict[str, JsonValue]:
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.partition-decision-result",
            "schema_version": HKEX_PARTITION_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_PARTITION_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": spec.expected_outcome.value,
            "reason": spec.expected_reason.value,
            "partition_required": False,
            "measurement_complete": True,
            "branch_results": [],
            "rejected_proposal_codes": [],
            "quarantined_branch_ids": [],
            "coverage_gap_ids": [],
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "deployment_authorized": False,
            "external_effects": "NONE",
        }
    )


def build_partition_decision_cases() -> tuple[
    tuple[dict[str, JsonValue], dict[str, JsonValue]], ...
]:
    """Build all 24 permanent exact-limit and official-partition cases."""
    universe = build_conformance_universe()
    universe_cases = tuple(
        _json_object(item)
        for item in _json_array(universe["cases"])
        if str(_json_object(item)["case_id"]).startswith("HKREG-DET-PAR-")
    )
    specs = _partition_case_specs()
    if len(universe_cases) != HKEX_PARTITION_DECISION_CASE_COUNT or len(specs) != (
        HKEX_PARTITION_DECISION_CASE_COUNT
    ):
        raise _ConformanceBuildError
    universe_fingerprint = _fingerprint(rfc8785.dumps(universe))
    bindings = _partition_contract_bindings(universe_fingerprint)
    results: list[tuple[dict[str, JsonValue], dict[str, JsonValue]]] = []
    for universe_case, spec in zip(universe_cases, specs, strict=True):
        case_id = str(universe_case["case_id"])
        facts = deepcopy(spec.facts)
        expected = _partition_seed_expected(case_id, spec)
        fixture = _json_object(
            {
                "schema_id": "asklegal.hk-regulatory.partition-decision-case",
                "schema_version": HKEX_PARTITION_DECISION_CONTRACT_VERSION,
                "package_contract_version": "1.0.0",
                "case_id": case_id,
                "suite_layer": "DECISION_TO_ARTIFACT",
                "primary_checkpoint": "PARTITIONING",
                "frozen": True,
                "synthetic_evidence_class": "SYNTHETIC_NO_REAL_AUTHORITY",
                "contract_bindings": deepcopy(bindings),
                "synthetic_cutoff": "2026-08-24T00:00:00Z",
                "scope_id": "HKEX_CROSS_BOARD",
                "prior_state": "SYNTHETIC_ACCEPTED_PREDECESSOR",
                "primary_coverage_cell_ids": [universe_case["coverage_cell_id"]],
                "secondary_coverage_cell_ids": [],
                "pair_memberships": deepcopy(_json_array(universe_case["pair_memberships"])),
                "declared_input_inventory": ["partition-evidence"],
                "declared_reference_inventory": [
                    "asklegal.hk-regulatory.conformance-universe",
                    "asklegal.hk-regulatory.partition-decision-case",
                    "asklegal.hk-regulatory.english-record",
                ],
                "declared_expected_inventory": ["PARTITION_DECISION_REPORT"],
                "assertion_scope": spec.scope.value,
                "required_result_dimensions": [
                    "BOTH_EXACT_LIMITS",
                    "COVERAGE_GAP",
                    "FINAL_LABELS",
                    "OFFICIAL_STRUCTURE",
                    "PARTITION_OPTIMIZATION",
                    "PROCESSING",
                    "QUARANTINE",
                ],
                "evidence_packet_fields": sorted(facts),
                "supporting_evidence_ranges": [f"input/{case_id}-partition-evidence.json#facts"],
                "rule_trace": [HKEX_ENGLISH_RECORD_RULE_ID, HKEX_PARTITION_DECISION_RULE_ID],
                "established_facts": ["SYNTHETIC_PARTITION_FACT_PACKET_DECLARED"],
                "unresolved_facts": (
                    [spec.expected_reason.value]
                    if spec.expected_outcome is not HKEXPartitionOutcome.PASS
                    else []
                ),
                "permitted_equivalent_results": [],
                "critical_error_codes": (
                    [spec.expected_reason.value]
                    if spec.expected_outcome is HKEXPartitionOutcome.QUARANTINE
                    else []
                ),
                "package_fingerprint": universe_fingerprint,
                "title": universe_case["synthetic_scenario"],
                "purpose": universe_case["exact_required_result"],
                "expected_decision": expected,
                "evidence_packet": {
                    "slot_id": "partition-evidence",
                    "state": "AVAILABLE",
                    "path": f"input/{case_id}-partition-evidence.json",
                    "role": "ORDINARY",
                    "media_type": "application/json",
                    "content_fingerprint": _fingerprint(rfc8785.dumps(facts)),
                },
                "facts": facts,
                "case_fingerprint": "PENDING",
            }
        )
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        seeded = hkex_partition_decision_case_from_document(fixture)
        observed = decide_hkex_partition_case(seeded)
        if observed.outcome is not spec.expected_outcome or observed.reason is not (
            spec.expected_reason
        ):
            raise _ConformanceBuildError(case_id)
        fixture["expected_decision"] = checked_json_value(observed.document(case_id=case_id))
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        parsed = hkex_partition_decision_case_from_document(fixture)
        report = _json_object(run_hkex_partition_case(parsed).document())
        if report["conformance_status"] != "PASS":
            raise _ConformanceBuildError(case_id)
        results.append((fixture, report))
    return tuple(results)


def build_partition_decision_catalogue(
    cases: tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...],
) -> dict[str, JsonValue]:
    """Bind all 24 exact partition fact packets and reports."""
    entries: list[JsonValue] = []
    for fixture, report in cases:
        case_id = str(fixture["case_id"])
        fixture_path = f"fixtures/conformance/partition-decision/{case_id}.json"
        expected_path = f"expected/conformance/partition-decision/{case_id}.json"
        expected = _json_object(fixture["expected_decision"])
        entries.append(
            {
                "case_id": case_id,
                "primary_coverage_cell_id": _json_array(fixture["primary_coverage_cell_ids"])[0],
                "pair_memberships": deepcopy(_json_array(fixture["pair_memberships"])),
                "assertion_scope": fixture["assertion_scope"],
                "expected_outcome": expected["outcome"],
                "expected_reason": expected["reason"],
                "fixture_path": fixture_path,
                "fixture_fingerprint": _fingerprint(
                    (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode()
                ),
                "expected_path": expected_path,
                "expected_fingerprint": _fingerprint(
                    (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
                ),
            }
        )
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.partition-decision-catalogue",
            "schema_version": HKEX_PARTITION_DECISION_CONTRACT_VERSION,
            "catalogue_id": "hk-regulatory-partition-decision",
            "catalogue_version": "1.0.0",
            "status": "FROZEN_EXECUTABLE_CHECKPOINT",
            "case_count": HKEX_PARTITION_DECISION_CASE_COUNT,
            "primary_coverage_cell_count": HKEX_PARTITION_DECISION_CASE_COUNT,
            "high_risk_pair_ids": [
                "HKREG-PAIR-038",
                "HKREG-PAIR-039",
                "HKREG-PAIR-040",
            ],
            "entries": entries,
            "checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "activation_authorized": False,
            "external_effects": "NONE",
        }
    )


def _partition_part_schema() -> dict[str, JsonValue]:
    fingerprint_schema = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    strings = {
        "type": "array",
        "uniqueItems": True,
        "items": {"type": "string", "minLength": 1},
    }
    return _closed_schema(
        [
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
        ],
        _json_object(
            {
                "part_number": {"type": "integer", "minimum": 1},
                "total_parts": {"type": "integer", "minimum": 1},
                "record_unit_ids": {**strings, "minItems": 1},
                "primary_source_unit_ids": {**strings, "minItems": 1},
                "dependency_source_unit_ids": strings,
                "text_fingerprint": fingerprint_schema,
                "serving_payload_fingerprint": fingerprint_schema,
                "text_tokens": {"type": "integer", "minimum": 0},
                "metadata_bytes": {"type": "integer", "minimum": 0},
                "text_limit": {"type": "integer", "minimum": 1},
                "metadata_limit": {"type": "integer", "minimum": 1},
                "fits": {"type": "boolean"},
                "serving_label": {"oneOf": [{"type": "null"}, {"type": "string", "minLength": 1}]},
            }
        ),
    )


def _partition_result_schema() -> dict[str, JsonValue]:
    strings = {
        "type": "array",
        "uniqueItems": True,
        "items": {"type": "string", "minLength": 1},
    }
    branch = _closed_schema(
        [
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
        ],
        _json_object(
            {
                "branch_id": {"type": "string", "minLength": 1},
                "root_record_unit_id": {"type": "string", "minLength": 1},
                "disposition": {"enum": [item.value for item in HKEXEnglishDisposition]},
                "construction_reason": {"enum": [item.value for item in HKEXEnglishReason]},
                "unsplit_text_tokens": {"type": "integer", "minimum": 0},
                "unsplit_metadata_bytes": {"type": "integer", "minimum": 0},
                "text_limit": {"type": "integer", "minimum": 1},
                "metadata_limit": {"type": "integer", "minimum": 1},
                "parts": {"type": "array", "items": _partition_part_schema()},
                "accounted_primary_source_unit_ids": strings,
            }
        ),
    )
    return _closed_schema(
        [
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
        ],
        _json_object(
            {
                "schema_id": {"const": "asklegal.hk-regulatory.partition-decision-result"},
                "schema_version": {"const": HKEX_PARTITION_DECISION_CONTRACT_VERSION},
                "rule_id": {"const": HKEX_PARTITION_DECISION_RULE_ID},
                "case_id": {
                    "type": "string",
                    "pattern": "^HKREG-DET-PAR-(0[0-1][0-9]|02[0-4])$",
                },
                "outcome": {"enum": [item.value for item in HKEXPartitionOutcome]},
                "reason": {"enum": [item.value for item in HKEXPartitionReason]},
                "partition_required": {"type": "boolean"},
                "measurement_complete": {"type": "boolean"},
                "branch_results": {
                    "type": "array",
                    "maxItems": 2,
                    "uniqueItems": True,
                    "items": branch,
                },
                "rejected_proposal_codes": strings,
                "quarantined_branch_ids": strings,
                "coverage_gap_ids": strings,
                "search_record_authorized": {"const": False},
                "embedding_authorized": {"const": False},
                "release_authorized": {"const": False},
                "serving_authorized": {"const": False},
                "deployment_authorized": {"const": False},
                "external_effects": {"const": "NONE"},
            }
        ),
    )


def _partition_embedded_request_schema() -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    request = dict(
        _json_object(
            json.loads(
                (
                    PACKAGE_ROOT / "contracts/schemas/hkex-english-record-request.schema.json"
                ).read_text(encoding="utf-8")
            )
        )
    )
    for key in ("$schema", "$id", "title"):
        request.pop(key, None)
    english_defs = _json_object(request.pop("$defs"))
    prefixed = _json_object(_prefix_english_schema_refs(request))
    defs: dict[str, JsonValue] = {}
    for name in sorted(english_defs, key=str.encode):
        defs[f"english_{name}"] = _prefix_english_schema_refs(english_defs[name])
    return prefixed, defs


def build_partition_decision_case_schema() -> dict[str, JsonValue]:
    """Build the strict common envelope for all 24 partition cases."""
    fingerprint_schema = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    nonempty = {"type": "string", "minLength": 1}
    string_array = {
        "type": "array",
        "uniqueItems": True,
        "items": nonempty,
    }
    request, defs = _partition_embedded_request_schema()
    binding = _closed_schema(
        ["contract_id", "version", "fingerprint"],
        _json_object(
            {
                "contract_id": nonempty,
                "version": nonempty,
                "fingerprint": fingerprint_schema,
            }
        ),
    )
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": {"pattern": "^HKREG-PAIR-0(38|39|40)$", "type": "string"},
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    packet = _closed_schema(
        ["slot_id", "state", "path", "role", "media_type", "content_fingerprint"],
        _json_object(
            {
                "slot_id": {"const": "partition-evidence"},
                "state": {"const": "AVAILABLE"},
                "path": nonempty,
                "role": {"const": "ORDINARY"},
                "media_type": {"const": "application/json"},
                "content_fingerprint": fingerprint_schema,
            }
        ),
    )
    facts = _closed_schema(
        [
            "requests",
            "measurement_field_ids",
            "candidate_cut",
            "candidate_official_boundary_proved",
            "preliminary_part_count",
        ],
        _json_object(
            {
                "requests": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 2,
                    "items": request,
                },
                "measurement_field_ids": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"enum": list(HKEX_PARTITION_MEASUREMENT_FIELDS)},
                },
                "candidate_cut": {"enum": [item.value for item in HKEXPartitionCandidateCut]},
                "candidate_official_boundary_proved": {"type": "boolean"},
                "preliminary_part_count": {"type": "integer", "minimum": 0},
            }
        ),
    )
    required = [
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
    ]
    properties: dict[str, object] = {
        "schema_id": {"const": "asklegal.hk-regulatory.partition-decision-case"},
        "schema_version": {"const": HKEX_PARTITION_DECISION_CONTRACT_VERSION},
        "package_contract_version": {"const": "1.0.0"},
        "case_id": {"type": "string", "pattern": "^HKREG-DET-PAR-(0[0-1][0-9]|02[0-4])$"},
        "suite_layer": {"const": "DECISION_TO_ARTIFACT"},
        "primary_checkpoint": {"const": "PARTITIONING"},
        "frozen": {"const": True},
        "synthetic_evidence_class": {"const": "SYNTHETIC_NO_REAL_AUTHORITY"},
        "contract_bindings": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": binding,
        },
        "synthetic_cutoff": {"const": "2026-08-24T00:00:00Z"},
        "scope_id": {"const": "HKEX_CROSS_BOARD"},
        "prior_state": {"const": "SYNTHETIC_ACCEPTED_PREDECESSOR"},
        "primary_coverage_cell_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {"type": "string", "pattern": "^HKREG-COV-DPAR-0[0-2][0-9]$"},
        },
        "secondary_coverage_cell_ids": {"const": []},
        "pair_memberships": {
            "type": "array",
            "maxItems": 1,
            "uniqueItems": True,
            "items": pair,
        },
        "declared_input_inventory": {"const": ["partition-evidence"]},
        "declared_reference_inventory": {
            "const": [
                "asklegal.hk-regulatory.conformance-universe",
                "asklegal.hk-regulatory.partition-decision-case",
                "asklegal.hk-regulatory.english-record",
            ]
        },
        "declared_expected_inventory": {"const": ["PARTITION_DECISION_REPORT"]},
        "assertion_scope": {"enum": [item.value for item in HKEXPartitionAssertionScope]},
        "required_result_dimensions": {
            "const": [
                "BOTH_EXACT_LIMITS",
                "COVERAGE_GAP",
                "FINAL_LABELS",
                "OFFICIAL_STRUCTURE",
                "PARTITION_OPTIMIZATION",
                "PROCESSING",
                "QUARANTINE",
            ]
        },
        "evidence_packet_fields": {
            "const": sorted(
                {
                    "requests",
                    "measurement_field_ids",
                    "candidate_cut",
                    "candidate_official_boundary_proved",
                    "preliminary_part_count",
                }
            )
        },
        "supporting_evidence_ranges": {**string_array, "minItems": 1},
        "rule_trace": {**string_array, "minItems": 1},
        "established_facts": {**string_array, "minItems": 1},
        "unresolved_facts": string_array,
        "permitted_equivalent_results": {"const": []},
        "critical_error_codes": string_array,
        "package_fingerprint": fingerprint_schema,
        "title": nonempty,
        "purpose": nonempty,
        "expected_decision": _partition_result_schema(),
        "evidence_packet": packet,
        "facts": facts,
        "case_fingerprint": fingerprint_schema,
    }
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-partition-decision-case.schema.json",
            "title": "HKEX exact-limit and official-partition conformance case",
            "$defs": defs,
            **_closed_schema(required, _json_object(properties)),
        }
    )


def build_partition_decision_report_schema() -> dict[str, JsonValue]:
    """Build the exact effect-free partition report schema."""
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-partition-decision-report.schema.json",
            "title": "HKEX exact-limit and official-partition conformance report",
            **_closed_schema(
                [
                    "schema_id",
                    "schema_version",
                    "rule_id",
                    "case_id",
                    "assertion_scope",
                    "observed_decision",
                    "expected_decision",
                    "conformance_status",
                    "source_authorized",
                    "provider_authorized",
                    "release_authorized",
                    "serving_authorized",
                    "deployment_authorized",
                    "external_effects",
                ],
                _json_object(
                    {
                        "schema_id": {"const": "asklegal.hk-regulatory.partition-decision-report"},
                        "schema_version": {"const": HKEX_PARTITION_DECISION_CONTRACT_VERSION},
                        "rule_id": {"const": HKEX_PARTITION_DECISION_RULE_ID},
                        "case_id": {
                            "type": "string",
                            "pattern": "^HKREG-DET-PAR-(0[0-1][0-9]|02[0-4])$",
                        },
                        "assertion_scope": {
                            "enum": [item.value for item in HKEXPartitionAssertionScope]
                        },
                        "observed_decision": _partition_result_schema(),
                        "expected_decision": _partition_result_schema(),
                        "conformance_status": {"enum": ["PASS", "FAIL"]},
                        "source_authorized": {"const": False},
                        "provider_authorized": {"const": False},
                        "release_authorized": {"const": False},
                        "serving_authorized": {"const": False},
                        "deployment_authorized": {"const": False},
                        "external_effects": {"const": "NONE"},
                    }
                ),
            ),
        }
    )


def build_partition_decision_catalogue_schema() -> dict[str, JsonValue]:
    """Build the strict 24-entry partition checkpoint catalogue schema."""
    nonempty: JsonValue = {"type": "string", "minLength": 1}
    fingerprint_schema: JsonValue = {
        "type": "string",
        "pattern": "^sha256:[0-9a-f]{64}$",
    }
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": {"type": "string", "pattern": "^HKREG-PAIR-0(38|39|40)$"},
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    entry = _closed_schema(
        [
            "case_id",
            "primary_coverage_cell_id",
            "pair_memberships",
            "assertion_scope",
            "expected_outcome",
            "expected_reason",
            "fixture_path",
            "fixture_fingerprint",
            "expected_path",
            "expected_fingerprint",
        ],
        _json_object(
            {
                "case_id": nonempty,
                "primary_coverage_cell_id": nonempty,
                "pair_memberships": {
                    "type": "array",
                    "maxItems": 1,
                    "uniqueItems": True,
                    "items": pair,
                },
                "assertion_scope": {"enum": [item.value for item in HKEXPartitionAssertionScope]},
                "expected_outcome": {"enum": [item.value for item in HKEXPartitionOutcome]},
                "expected_reason": {"enum": [item.value for item in HKEXPartitionReason]},
                "fixture_path": nonempty,
                "fixture_fingerprint": fingerprint_schema,
                "expected_path": nonempty,
                "expected_fingerprint": fingerprint_schema,
            }
        ),
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-partition-decision-catalogue.schema.json",
            "title": "HKEX exact-limit and official-partition executable catalogue",
            **_closed_schema(
                [
                    "schema_id",
                    "schema_version",
                    "catalogue_id",
                    "catalogue_version",
                    "status",
                    "case_count",
                    "primary_coverage_cell_count",
                    "high_risk_pair_ids",
                    "entries",
                    "checkpoint_complete",
                    "full_conformance_suite_complete",
                    "activation_authorized",
                    "external_effects",
                ],
                _json_object(
                    {
                        "schema_id": {
                            "const": "asklegal.hk-regulatory.partition-decision-catalogue"
                        },
                        "schema_version": {"const": HKEX_PARTITION_DECISION_CONTRACT_VERSION},
                        "catalogue_id": {"const": "hk-regulatory-partition-decision"},
                        "catalogue_version": {"const": "1.0.0"},
                        "status": {"const": "FROZEN_EXECUTABLE_CHECKPOINT"},
                        "case_count": {"const": HKEX_PARTITION_DECISION_CASE_COUNT},
                        "primary_coverage_cell_count": {
                            "const": HKEX_PARTITION_DECISION_CASE_COUNT
                        },
                        "high_risk_pair_ids": {
                            "const": [
                                "HKREG-PAIR-038",
                                "HKREG-PAIR-039",
                                "HKREG-PAIR-040",
                            ]
                        },
                        "entries": {
                            "type": "array",
                            "minItems": HKEX_PARTITION_DECISION_CASE_COUNT,
                            "maxItems": HKEX_PARTITION_DECISION_CASE_COUNT,
                            "items": entry,
                        },
                        "checkpoint_complete": {"const": True},
                        "full_conformance_suite_complete": {"const": False},
                        "activation_authorized": {"const": False},
                        "external_effects": {"const": "NONE"},
                    }
                ),
            ),
        }
    )


def build_partition_decision_rule() -> dict[str, JsonValue]:
    """Declare the exact bounded authority of the 24-case checkpoint."""
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory-partition-decision-rule",
            "schema_version": HKEX_PARTITION_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_PARTITION_DECISION_RULE_ID,
            "status": "SOURCE_NEUTRAL_EXECUTABLE_CHECKPOINT",
            "accepted_adrs": ["0040", "0050", "0073", "0074", "0075"],
            "case_schema": "contracts/schemas/hkex-partition-decision-case.schema.json",
            "report_schema": "contracts/schemas/hkex-partition-decision-report.schema.json",
            "catalogue_schema": "contracts/schemas/hkex-partition-decision-catalogue.schema.json",
            "catalogue": "catalogues/partition-decision-cases.json",
            "required_case_count": HKEX_PARTITION_DECISION_CASE_COUNT,
            "required_primary_coverage_cell_count": HKEX_PARTITION_DECISION_CASE_COUNT,
            "required_high_risk_pairs": [
                "HKREG-PAIR-038",
                "HKREG-PAIR-039",
                "HKREG-PAIR-040",
            ],
            "accepted_partitioner_rule_id": HKEX_ENGLISH_RECORD_RULE_ID,
            "complete_structured_decision_match_required": True,
            "case_id_switching_forbidden": True,
            "partition_decision_checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "source_authority": False,
            "activation_authority": False,
            "external_effects": "NONE",
        }
    )


@dataclass(frozen=True, slots=True)
class _CoverageCaseSpec:
    scope: HKEXCoverageAssertionScope
    facts: dict[str, JsonValue]
    expected_outcome: HKEXCoverageOutcome
    expected_reason: HKEXCoverageReason


def _coverage_request(
    tree: HKEXEnglishSourceTree,
    *,
    max_text_tokens: int = 100_000,
) -> HKEXEnglishConstructionRequest:
    return HKEXEnglishConstructionRequest(
        tree,
        _english_profile(max_text_tokens=max_text_tokens),
        None,
    )


def _coverage_facts(
    requests: tuple[HKEXEnglishConstructionRequest, ...],
    *,
    declared: tuple[HKEXCoverageUnitAccounting, ...] | None = None,
    excluded: tuple[HKEXCoverageExcludedUnit, ...] = (),
    shared_gap: bool = False,
    proxies: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    accounting = canonical_hkex_coverage_units(requests, excluded) if declared is None else declared
    return _json_object(
        {
            "requests": [item.document() for item in requests],
            "declared_units": [item.document() for item in accounting],
            "excluded_units": [item.document() for item in excluded],
            "shared_unbounded_gap": shared_gap,
            "weak_proxy_checks": list(proxies),
        }
    )


def _replace_first_primary(
    units: tuple[HKEXCoverageUnitAccounting, ...],
    **changes: object,
) -> tuple[HKEXCoverageUnitAccounting, ...]:
    results = list(units)
    index = next(
        index
        for index, item in enumerate(results)
        if item.outcome is HKEXCoverageUnitOutcome.PRIMARY
    )
    results[index] = replace(results[index], **changes)
    return tuple(results)


def _swap_first_primary_units(
    units: tuple[HKEXCoverageUnitAccounting, ...],
) -> tuple[HKEXCoverageUnitAccounting, ...]:
    results = list(units)
    indexes = [
        index
        for index, item in enumerate(results)
        if item.outcome is HKEXCoverageUnitOutcome.PRIMARY
    ][:_COVERAGE_REORDER_MEMBER_COUNT]
    if len(indexes) != _COVERAGE_REORDER_MEMBER_COUNT:
        raise _ConformanceBuildError
    first, second = indexes
    results[first], results[second] = results[second], results[first]
    return tuple(results)


def _coverage_case_specs() -> tuple[_CoverageCaseSpec, ...]:
    main = _coverage_request(
        _coverage_board_tree(
            _english_tree(HKEXBranchState.CURRENT, partition=True),
            scope_id=HKEX_MAIN_SCOPE_ID,
            suffix="-coverage-main",
        )
    )
    gem = _coverage_request(
        _coverage_board_tree(
            _english_tree(HKEXBranchState.CURRENT, partition=True),
            scope_id=HKEX_GEM_SCOPE_ID,
            suffix="-coverage-gem",
        )
    )
    both = (main, gem)
    both_units = canonical_hkex_coverage_units(both)
    blocked = _coverage_request(
        _coverage_board_tree(
            _english_tree(HKEXBranchState.CURRENT),
            scope_id=HKEX_MAIN_SCOPE_ID,
            suffix="-coverage-blocked",
        ),
        max_text_tokens=1,
    )
    blocked_units = canonical_hkex_coverage_units((blocked,))
    explicitly_blocked = tuple(
        replace(item, outcome=HKEXCoverageUnitOutcome.BLOCKED)
        if item.outcome is HKEXCoverageUnitOutcome.QUARANTINED
        else item
        for item in blocked_units
    )
    dependency = _coverage_request(_coverage_dependency_tree())
    dependency_units = canonical_hkex_coverage_units((dependency,))
    classification = _coverage_request(_coverage_classification_tree())
    complex_request = _coverage_request(_coverage_complex_tree())
    excluded = (
        HKEXCoverageExcludedUnit(
            "synthetic-excluded-main-guidance",
            HKEX_MAIN_SCOPE_ID,
            100,
        ),
    )
    noncurrent = tuple(
        _coverage_request(
            _coverage_board_tree(
                _english_tree(state),
                scope_id=HKEX_MAIN_SCOPE_ID,
                suffix=f"-coverage-{state.value.lower()}",
            )
        )
        for state in (
            HKEXBranchState.FUTURE_FIXED_DATE,
            HKEXBranchState.SUPERSEDED,
            HKEXBranchState.WITHDRAWN,
            HKEXBranchState.UNKNOWN,
        )
    )
    no_output = (noncurrent[0], noncurrent[1], noncurrent[3])

    missing = tuple(
        item
        for item in both_units
        if item
        is not next(unit for unit in both_units if unit.outcome is HKEXCoverageUnitOutcome.PRIMARY)
    )
    duplicated = _replace_first_primary(
        both_units,
        primary_owner_record_ids=(
            "synthetic-duplicate-owner-a",
            "synthetic-duplicate-owner-b",
        ),
    )
    reordered = _swap_first_primary_units(both_units)
    orphaned = (
        *both_units,
        HKEXCoverageUnitAccounting(
            "synthetic-orphan-output",
            HKEX_MAIN_SCOPE_ID,
            999,
            HKEXCoverageUnitOutcome.PRIMARY,
            ("synthetic-orphan-record",),
            (),
            HKEXCoverageFidelity.EXACT,
        ),
    )
    wrong_board = _replace_first_primary(both_units, scope_id=HKEX_GEM_SCOPE_ID)
    dependency_target = next(
        item
        for item in dependency_units
        if item.outcome is HKEXCoverageUnitOutcome.PRIMARY and item.dependency_uses
    )
    bad_dependency = replace(
        dependency_target,
        dependency_uses=(
            replace(
                dependency_target.dependency_uses[0],
                label="Unlabelled repeated text",
                owner_record_id="unknown-owner",
                source_fingerprint=f"sha256:{'c' * 64}",
            ),
        ),
    )
    incomplete_dependency = tuple(
        bad_dependency if item.unit_key == bad_dependency.unit_key else item
        for item in dependency_units
    )
    altered = _replace_first_primary(
        both_units,
        fidelity=HKEXCoverageFidelity.SUMMARIZED,
    )
    main_blocked = _coverage_request(
        _coverage_board_tree(
            _english_tree(HKEXBranchState.CURRENT),
            scope_id=HKEX_MAIN_SCOPE_ID,
            suffix="-coverage-main-bounded-failure",
        ),
        max_text_tokens=1,
    )
    gem_ready = _coverage_request(
        _coverage_board_tree(
            _english_tree(HKEXBranchState.CURRENT),
            scope_id=HKEX_GEM_SCOPE_ID,
            suffix="-coverage-gem-independent",
        )
    )
    mixed_requests = (main_blocked, gem_ready)
    mixed_units = tuple(
        replace(item, outcome=HKEXCoverageUnitOutcome.BLOCKED)
        if item.outcome is HKEXCoverageUnitOutcome.QUARANTINED
        else item
        for item in canonical_hkex_coverage_units(mixed_requests)
    )
    proxies = (
        "PARSER_SUCCESS",
        "PDF_PAGE_COUNT_MATCH",
        "RECORD_COUNT_MATCH",
        "TEXT_PRESENCE_MATCH",
    )

    def spec(
        scope: HKEXCoverageAssertionScope,
        facts: dict[str, JsonValue],
        outcome: HKEXCoverageOutcome,
        reason: HKEXCoverageReason,
    ) -> _CoverageCaseSpec:
        return _CoverageCaseSpec(scope, facts, outcome, reason)

    return (
        spec(
            HKEXCoverageAssertionScope.PRIMARY_OWNERSHIP,
            _coverage_facts(both),
            HKEXCoverageOutcome.PASS,
            HKEXCoverageReason.COMPLETE_PRIMARY_OWNERSHIP,
        ),
        spec(
            HKEXCoverageAssertionScope.BLOCKED_REQUIRED,
            _coverage_facts((blocked,), declared=explicitly_blocked),
            HKEXCoverageOutcome.COMPLETE_NOT_READY,
            HKEXCoverageReason.REQUIRED_UNIT_EXPLICITLY_BLOCKED,
        ),
        spec(
            HKEXCoverageAssertionScope.REPEATED_DEPENDENCY,
            _coverage_facts((dependency,)),
            HKEXCoverageOutcome.PASS,
            HKEXCoverageReason.DEPENDENCY_REPETITION_ACCOUNTED,
        ),
        spec(
            HKEXCoverageAssertionScope.EXPLICIT_CLASSIFICATION,
            _coverage_facts((classification,)),
            HKEXCoverageOutcome.PASS,
            HKEXCoverageReason.CLASSIFICATIONS_ACCOUNTED,
        ),
        spec(
            HKEXCoverageAssertionScope.COMPLEX_ELEMENTS,
            _coverage_facts((complex_request,)),
            HKEXCoverageOutcome.PASS,
            HKEXCoverageReason.COMPLEX_ELEMENTS_ACCOUNTED,
        ),
        spec(
            HKEXCoverageAssertionScope.NONCURRENT_OUTCOMES,
            _coverage_facts(noncurrent, excluded=excluded),
            HKEXCoverageOutcome.PASS,
            HKEXCoverageReason.NONCURRENT_OUTCOMES_ACCOUNTED,
        ),
        spec(
            HKEXCoverageAssertionScope.ORDER_AND_BOARD,
            _coverage_facts(both),
            HKEXCoverageOutcome.PASS,
            HKEXCoverageReason.ORDER_AND_BOARD_PROVED,
        ),
        spec(
            HKEXCoverageAssertionScope.MISSING_UNIT,
            _coverage_facts(both, declared=missing),
            HKEXCoverageOutcome.INVALID,
            HKEXCoverageReason.MISSING_SOURCE_UNIT,
        ),
        spec(
            HKEXCoverageAssertionScope.DUPLICATE_PRIMARY,
            _coverage_facts(both, declared=duplicated),
            HKEXCoverageOutcome.INVALID,
            HKEXCoverageReason.DUPLICATE_PRIMARY_OWNER,
        ),
        spec(
            HKEXCoverageAssertionScope.REORDERED_PRIMARY,
            _coverage_facts(both, declared=reordered),
            HKEXCoverageOutcome.INVALID,
            HKEXCoverageReason.SOURCE_ORDER_CHANGED,
        ),
        spec(
            HKEXCoverageAssertionScope.ORPHAN_OUTPUT,
            _coverage_facts(both, declared=orphaned),
            HKEXCoverageOutcome.INVALID,
            HKEXCoverageReason.ORPHANED_OUTPUT,
        ),
        spec(
            HKEXCoverageAssertionScope.WRONG_BOARD,
            _coverage_facts(both, declared=wrong_board),
            HKEXCoverageOutcome.INVALID,
            HKEXCoverageReason.WRONG_BOARD_OWNER,
        ),
        spec(
            HKEXCoverageAssertionScope.DEPENDENCY_BINDING,
            _coverage_facts((dependency,), declared=incomplete_dependency),
            HKEXCoverageOutcome.INVALID,
            HKEXCoverageReason.DEPENDENCY_BINDING_INCOMPLETE,
        ),
        spec(
            HKEXCoverageAssertionScope.SOURCE_FIDELITY,
            _coverage_facts(both, declared=altered),
            HKEXCoverageOutcome.INVALID,
            HKEXCoverageReason.SOURCE_FIDELITY_CHANGED,
        ),
        spec(
            HKEXCoverageAssertionScope.BOARD_READY,
            _coverage_facts(both),
            HKEXCoverageOutcome.PASS,
            HKEXCoverageReason.BOARD_READY_FOR_LATER_GATES,
        ),
        spec(
            HKEXCoverageAssertionScope.QUARANTINED_CURRENT,
            _coverage_facts((blocked,)),
            HKEXCoverageOutcome.COMPLETE_NOT_READY,
            HKEXCoverageReason.COMPLETE_BUT_BOARD_NOT_READY,
        ),
        spec(
            HKEXCoverageAssertionScope.BOARD_ISOLATION,
            _coverage_facts(mixed_requests, declared=mixed_units),
            HKEXCoverageOutcome.PASS,
            HKEXCoverageReason.BOARDS_INDEPENDENT,
        ),
        spec(
            HKEXCoverageAssertionScope.SHARED_GAP,
            _coverage_facts(both, shared_gap=True),
            HKEXCoverageOutcome.COMPLETE_NOT_READY,
            HKEXCoverageReason.SHARED_GAP_BLOCKS_BOTH,
        ),
        spec(
            HKEXCoverageAssertionScope.WEAK_PROXY,
            _coverage_facts(both, declared=missing, proxies=proxies),
            HKEXCoverageOutcome.INVALID,
            HKEXCoverageReason.WEAK_PROXY_REJECTED,
        ),
        spec(
            HKEXCoverageAssertionScope.ZERO_OUTPUT,
            _coverage_facts(no_output, excluded=excluded),
            HKEXCoverageOutcome.PASS,
            HKEXCoverageReason.VALID_ZERO_OUTPUT,
        ),
    )


def _coverage_contract_bindings(universe_fingerprint: str) -> list[JsonValue]:
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
    return [
        {
            "contract_id": "asklegal.hk-regulatory.conformance-universe",
            "version": HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION,
            "fingerprint": universe_fingerprint,
        },
        {
            "contract_id": "asklegal.hk-regulatory.coverage-decision-case",
            "version": HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
            "fingerprint": _fingerprint(rfc8785.dumps(coverage_seed)),
        },
        {
            "contract_id": "asklegal.hk-regulatory.english-record",
            "version": HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            "fingerprint": _fingerprint(rfc8785.dumps(english_seed)),
        },
    ]


def _coverage_seed_expected(case_id: str, spec: _CoverageCaseSpec) -> dict[str, JsonValue]:
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.coverage-decision-result",
            "schema_version": HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_COVERAGE_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": spec.expected_outcome.value,
            "reason": spec.expected_reason.value,
            "coverage_complete": False,
            "source_fidelity_valid": False,
            "source_order_valid": False,
            "board_ownership_valid": False,
            "dependency_accounting_valid": False,
            "total_source_unit_count": 0,
            "primary_owned_unit_count": 0,
            "non_serving_unit_count": 0,
            "board_results": [],
            "violation_codes": [],
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "deployment_authorized": False,
            "external_effects": "NONE",
        }
    )


def build_coverage_decision_cases() -> tuple[
    tuple[dict[str, JsonValue], dict[str, JsonValue]], ...
]:
    """Build all 20 permanent source-unit coverage/readiness cases."""
    universe = build_conformance_universe()
    universe_cases = tuple(
        _json_object(item)
        for item in _json_array(universe["cases"])
        if str(_json_object(item)["case_id"]).startswith("HKREG-DET-COV-")
    )
    specs = _coverage_case_specs()
    if len(universe_cases) != HKEX_COVERAGE_DECISION_CASE_COUNT or len(specs) != (
        HKEX_COVERAGE_DECISION_CASE_COUNT
    ):
        raise _ConformanceBuildError
    universe_fingerprint = _fingerprint(rfc8785.dumps(universe))
    bindings = _coverage_contract_bindings(universe_fingerprint)
    results: list[tuple[dict[str, JsonValue], dict[str, JsonValue]]] = []
    for universe_case, spec in zip(universe_cases, specs, strict=True):
        case_id = str(universe_case["case_id"])
        facts = deepcopy(spec.facts)
        fixture = _json_object(
            {
                "schema_id": "asklegal.hk-regulatory.coverage-decision-case",
                "schema_version": HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
                "package_contract_version": "1.0.0",
                "case_id": case_id,
                "suite_layer": "DECISION_TO_ARTIFACT",
                "primary_checkpoint": "SOURCE_UNIT_COVERAGE",
                "frozen": True,
                "synthetic_evidence_class": "SYNTHETIC_NO_REAL_AUTHORITY",
                "contract_bindings": deepcopy(bindings),
                "synthetic_cutoff": "2026-08-24T00:00:00Z",
                "scope_id": "HKEX_CROSS_BOARD",
                "prior_state": "SYNTHETIC_ACCEPTED_PREDECESSOR",
                "primary_coverage_cell_ids": [universe_case["coverage_cell_id"]],
                "secondary_coverage_cell_ids": [],
                "pair_memberships": deepcopy(_json_array(universe_case["pair_memberships"])),
                "declared_input_inventory": ["coverage-evidence"],
                "declared_reference_inventory": [
                    "asklegal.hk-regulatory.conformance-universe",
                    "asklegal.hk-regulatory.coverage-decision-case",
                    "asklegal.hk-regulatory.english-record",
                ],
                "declared_expected_inventory": ["COVERAGE_DECISION_REPORT"],
                "assertion_scope": spec.scope.value,
                "required_result_dimensions": [
                    "BOARD_READINESS",
                    "DEPENDENCY_ACCOUNTING",
                    "FORBIDDEN_EFFECTS",
                    "SOURCE_FIDELITY",
                    "SOURCE_ORDER",
                    "SOURCE_UNIT_ACCOUNTING",
                ],
                "evidence_packet_fields": sorted(facts),
                "supporting_evidence_ranges": [f"input/{case_id}-coverage-evidence.json#facts"],
                "rule_trace": sorted([HKEX_ENGLISH_RECORD_RULE_ID, HKEX_COVERAGE_DECISION_RULE_ID]),
                "established_facts": ["SYNTHETIC_COVERAGE_FACT_PACKET_DECLARED"],
                "unresolved_facts": (
                    [spec.expected_reason.value]
                    if spec.expected_outcome is not HKEXCoverageOutcome.PASS
                    else []
                ),
                "permitted_equivalent_results": [],
                "critical_error_codes": (
                    [spec.expected_reason.value]
                    if spec.expected_outcome is HKEXCoverageOutcome.INVALID
                    else []
                ),
                "package_fingerprint": universe_fingerprint,
                "title": universe_case["synthetic_scenario"],
                "purpose": universe_case["exact_required_result"],
                "expected_decision": _coverage_seed_expected(case_id, spec),
                "evidence_packet": {
                    "slot_id": "coverage-evidence",
                    "state": "AVAILABLE",
                    "path": f"input/{case_id}-coverage-evidence.json",
                    "role": "ORDINARY",
                    "media_type": "application/json",
                    "content_fingerprint": _fingerprint(rfc8785.dumps(facts)),
                },
                "facts": facts,
                "case_fingerprint": "PENDING",
            }
        )
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        seeded = hkex_coverage_decision_case_from_document(fixture)
        observed = decide_hkex_coverage_case(seeded)
        if observed.outcome is not spec.expected_outcome or observed.reason is not (
            spec.expected_reason
        ):
            raise _ConformanceBuildError(case_id)
        fixture["expected_decision"] = checked_json_value(observed.document(case_id=case_id))
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        parsed = hkex_coverage_decision_case_from_document(fixture)
        report = _json_object(run_hkex_coverage_case(parsed).document())
        if report["conformance_status"] != "PASS":
            raise _ConformanceBuildError(case_id)
        results.append((fixture, report))
    return tuple(results)


def build_coverage_decision_catalogue(
    cases: tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...],
) -> dict[str, JsonValue]:
    """Bind all 20 exact coverage fact packets and reports."""
    entries: list[JsonValue] = []
    for fixture, report in cases:
        case_id = str(fixture["case_id"])
        expected = _json_object(fixture["expected_decision"])
        entries.append(
            {
                "case_id": case_id,
                "primary_coverage_cell_id": _json_array(fixture["primary_coverage_cell_ids"])[0],
                "pair_memberships": fixture["pair_memberships"],
                "assertion_scope": fixture["assertion_scope"],
                "expected_outcome": expected["outcome"],
                "expected_reason": expected["reason"],
                "fixture_path": f"fixtures/conformance/coverage-decision/{case_id}.json",
                "fixture_fingerprint": _fingerprint(
                    (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode()
                ),
                "expected_path": f"expected/conformance/coverage-decision/{case_id}.json",
                "expected_fingerprint": _fingerprint(
                    (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
                ),
            }
        )
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.coverage-decision-catalogue",
            "schema_version": HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
            "catalogue_id": "hk-regulatory-coverage-decision",
            "catalogue_version": "1.0.0",
            "status": "FROZEN_EXECUTABLE_CHECKPOINT",
            "case_count": HKEX_COVERAGE_DECISION_CASE_COUNT,
            "primary_coverage_cell_count": HKEX_COVERAGE_DECISION_CASE_COUNT,
            "high_risk_pair_ids": [
                "HKREG-PAIR-041",
                "HKREG-PAIR-042",
                "HKREG-PAIR-043",
                "HKREG-PAIR-044",
                "HKREG-PAIR-045",
            ],
            "entries": entries,
            "checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "activation_authorized": False,
            "external_effects": "NONE",
        }
    )


def _coverage_dependency_schema() -> dict[str, JsonValue]:
    return _closed_schema(
        ["consumer_record_id", "label", "owner_record_id", "source_fingerprint"],
        _json_object(
            {
                "consumer_record_id": {"type": "string", "minLength": 1},
                "label": {"type": "string", "minLength": 1},
                "owner_record_id": {"type": "string", "minLength": 1},
                "source_fingerprint": {
                    "type": "string",
                    "pattern": "^sha256:[0-9a-f]{64}$",
                },
            }
        ),
    )


def _coverage_unit_schema() -> dict[str, JsonValue]:
    nonempty = {"type": "string", "minLength": 1}
    return _closed_schema(
        [
            "unit_key",
            "scope_id",
            "source_order",
            "outcome",
            "primary_owner_record_ids",
            "dependency_uses",
            "fidelity",
        ],
        _json_object(
            {
                "unit_key": nonempty,
                "scope_id": {"enum": sorted(HKEX_SCOPE_IDS)},
                "source_order": {"type": "integer", "minimum": 0},
                "outcome": {"enum": [item.value for item in HKEXCoverageUnitOutcome]},
                "primary_owner_record_ids": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": nonempty,
                },
                "dependency_uses": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": _coverage_dependency_schema(),
                },
                "fidelity": {"enum": [item.value for item in HKEXCoverageFidelity]},
            }
        ),
    )


def _coverage_board_result_schema() -> dict[str, JsonValue]:
    integer = {"type": "integer", "minimum": 0}
    return _closed_schema(
        [
            "scope_id",
            "inventory_bounded",
            "coverage_complete",
            "required_current_unit_count",
            "ready_current_unit_count",
            "blocked_or_quarantined_unit_count",
            "search_record_candidate_count",
            "later_gate_candidate_ready",
        ],
        _json_object(
            {
                "scope_id": {"enum": sorted(HKEX_SCOPE_IDS)},
                "inventory_bounded": {"type": "boolean"},
                "coverage_complete": {"type": "boolean"},
                "required_current_unit_count": integer,
                "ready_current_unit_count": integer,
                "blocked_or_quarantined_unit_count": integer,
                "search_record_candidate_count": integer,
                "later_gate_candidate_ready": {"type": "boolean"},
            }
        ),
    )


def _coverage_result_schema() -> dict[str, JsonValue]:
    integer = {"type": "integer", "minimum": 0}
    strings = {
        "type": "array",
        "uniqueItems": True,
        "items": {"type": "string", "minLength": 1},
    }
    return _closed_schema(
        [
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
        ],
        _json_object(
            {
                "schema_id": {"const": "asklegal.hk-regulatory.coverage-decision-result"},
                "schema_version": {"const": HKEX_COVERAGE_DECISION_CONTRACT_VERSION},
                "rule_id": {"const": HKEX_COVERAGE_DECISION_RULE_ID},
                "case_id": {
                    "type": "string",
                    "pattern": "^HKREG-DET-COV-(0[0-1][0-9]|020)$",
                },
                "outcome": {"enum": [item.value for item in HKEXCoverageOutcome]},
                "reason": {"enum": [item.value for item in HKEXCoverageReason]},
                "coverage_complete": {"type": "boolean"},
                "source_fidelity_valid": {"type": "boolean"},
                "source_order_valid": {"type": "boolean"},
                "board_ownership_valid": {"type": "boolean"},
                "dependency_accounting_valid": {"type": "boolean"},
                "total_source_unit_count": integer,
                "primary_owned_unit_count": integer,
                "non_serving_unit_count": integer,
                "board_results": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 2,
                    "uniqueItems": True,
                    "items": _coverage_board_result_schema(),
                },
                "violation_codes": strings,
                "search_record_authorized": {"const": False},
                "embedding_authorized": {"const": False},
                "release_authorized": {"const": False},
                "serving_authorized": {"const": False},
                "deployment_authorized": {"const": False},
                "external_effects": {"const": "NONE"},
            }
        ),
    )


def build_coverage_decision_case_schema() -> dict[str, JsonValue]:
    """Build the strict common envelope for all 20 coverage cases."""
    fingerprint_schema = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    nonempty = {"type": "string", "minLength": 1}
    string_array = {"type": "array", "uniqueItems": True, "items": nonempty}
    request, defs = _partition_embedded_request_schema()
    binding = _closed_schema(
        ["contract_id", "version", "fingerprint"],
        _json_object(
            {
                "contract_id": nonempty,
                "version": nonempty,
                "fingerprint": fingerprint_schema,
            }
        ),
    )
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": {"type": "string", "pattern": "^HKREG-PAIR-0(41|42|43|44|45)$"},
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    excluded = _closed_schema(
        ["unit_key", "scope_id", "source_order"],
        _json_object(
            {
                "unit_key": nonempty,
                "scope_id": {"enum": sorted(HKEX_SCOPE_IDS)},
                "source_order": {"type": "integer", "minimum": 0},
            }
        ),
    )
    facts = _closed_schema(
        [
            "requests",
            "declared_units",
            "excluded_units",
            "shared_unbounded_gap",
            "weak_proxy_checks",
        ],
        _json_object(
            {
                "requests": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 8,
                    "items": request,
                },
                "declared_units": {"type": "array", "items": _coverage_unit_schema()},
                "excluded_units": {"type": "array", "uniqueItems": True, "items": excluded},
                "shared_unbounded_gap": {"type": "boolean"},
                "weak_proxy_checks": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {
                        "enum": [
                            "PARSER_SUCCESS",
                            "PDF_PAGE_COUNT_MATCH",
                            "RECORD_COUNT_MATCH",
                            "TEXT_PRESENCE_MATCH",
                        ]
                    },
                },
            }
        ),
    )
    packet = _closed_schema(
        ["slot_id", "state", "path", "role", "media_type", "content_fingerprint"],
        _json_object(
            {
                "slot_id": {"const": "coverage-evidence"},
                "state": {"const": "AVAILABLE"},
                "path": nonempty,
                "role": {"const": "ORDINARY"},
                "media_type": {"const": "application/json"},
                "content_fingerprint": fingerprint_schema,
            }
        ),
    )
    required = [
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
    ]
    properties: dict[str, object] = {
        "schema_id": {"const": "asklegal.hk-regulatory.coverage-decision-case"},
        "schema_version": {"const": HKEX_COVERAGE_DECISION_CONTRACT_VERSION},
        "package_contract_version": {"const": "1.0.0"},
        "case_id": {"type": "string", "pattern": "^HKREG-DET-COV-(0[0-1][0-9]|020)$"},
        "suite_layer": {"const": "DECISION_TO_ARTIFACT"},
        "primary_checkpoint": {"const": "SOURCE_UNIT_COVERAGE"},
        "frozen": {"const": True},
        "synthetic_evidence_class": {"const": "SYNTHETIC_NO_REAL_AUTHORITY"},
        "contract_bindings": {"type": "array", "minItems": 3, "maxItems": 3, "items": binding},
        "synthetic_cutoff": {"const": "2026-08-24T00:00:00Z"},
        "scope_id": {"const": "HKEX_CROSS_BOARD"},
        "prior_state": {"const": "SYNTHETIC_ACCEPTED_PREDECESSOR"},
        "primary_coverage_cell_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {"type": "string", "pattern": "^HKREG-COV-DCOV-(0[0-1][0-9]|020)$"},
        },
        "secondary_coverage_cell_ids": {"const": []},
        "pair_memberships": {"type": "array", "maxItems": 2, "uniqueItems": True, "items": pair},
        "declared_input_inventory": {"const": ["coverage-evidence"]},
        "declared_reference_inventory": {
            "const": [
                "asklegal.hk-regulatory.conformance-universe",
                "asklegal.hk-regulatory.coverage-decision-case",
                "asklegal.hk-regulatory.english-record",
            ]
        },
        "declared_expected_inventory": {"const": ["COVERAGE_DECISION_REPORT"]},
        "assertion_scope": {"enum": [item.value for item in HKEXCoverageAssertionScope]},
        "required_result_dimensions": {
            "const": [
                "BOARD_READINESS",
                "DEPENDENCY_ACCOUNTING",
                "FORBIDDEN_EFFECTS",
                "SOURCE_FIDELITY",
                "SOURCE_ORDER",
                "SOURCE_UNIT_ACCOUNTING",
            ]
        },
        "evidence_packet_fields": {
            "const": [
                "declared_units",
                "excluded_units",
                "requests",
                "shared_unbounded_gap",
                "weak_proxy_checks",
            ]
        },
        "supporting_evidence_ranges": {**string_array, "minItems": 1},
        "rule_trace": {**string_array, "minItems": 1},
        "established_facts": {**string_array, "minItems": 1},
        "unresolved_facts": string_array,
        "permitted_equivalent_results": {"const": []},
        "critical_error_codes": string_array,
        "package_fingerprint": fingerprint_schema,
        "title": nonempty,
        "purpose": nonempty,
        "expected_decision": _coverage_result_schema(),
        "evidence_packet": packet,
        "facts": facts,
        "case_fingerprint": fingerprint_schema,
    }
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-coverage-decision-case.schema.json",
            "title": "HKEX source-unit coverage and board-readiness conformance case",
            "$defs": defs,
            **_closed_schema(required, _json_object(properties)),
        }
    )


def build_coverage_decision_report_schema() -> dict[str, JsonValue]:
    """Build the exact effect-free coverage report schema."""
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-coverage-decision-report.schema.json",
            "title": "HKEX source-unit coverage and board-readiness conformance report",
            **_closed_schema(
                [
                    "schema_id",
                    "schema_version",
                    "rule_id",
                    "case_id",
                    "assertion_scope",
                    "observed_decision",
                    "expected_decision",
                    "conformance_status",
                    "source_authorized",
                    "provider_authorized",
                    "release_authorized",
                    "serving_authorized",
                    "deployment_authorized",
                    "external_effects",
                ],
                _json_object(
                    {
                        "schema_id": {"const": "asklegal.hk-regulatory.coverage-decision-report"},
                        "schema_version": {"const": HKEX_COVERAGE_DECISION_CONTRACT_VERSION},
                        "rule_id": {"const": HKEX_COVERAGE_DECISION_RULE_ID},
                        "case_id": {
                            "type": "string",
                            "pattern": "^HKREG-DET-COV-(0[0-1][0-9]|020)$",
                        },
                        "assertion_scope": {
                            "enum": [item.value for item in HKEXCoverageAssertionScope]
                        },
                        "observed_decision": _coverage_result_schema(),
                        "expected_decision": _coverage_result_schema(),
                        "conformance_status": {"enum": ["PASS", "FAIL"]},
                        "source_authorized": {"const": False},
                        "provider_authorized": {"const": False},
                        "release_authorized": {"const": False},
                        "serving_authorized": {"const": False},
                        "deployment_authorized": {"const": False},
                        "external_effects": {"const": "NONE"},
                    }
                ),
            ),
        }
    )


def build_coverage_decision_catalogue_schema() -> dict[str, JsonValue]:
    """Build the strict 20-entry coverage checkpoint catalogue schema."""
    nonempty = {"type": "string", "minLength": 1}
    fingerprint_schema = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    pair = _closed_schema(
        ["pair_id", "role"],
        _json_object(
            {
                "pair_id": {"type": "string", "pattern": "^HKREG-PAIR-0(41|42|43|44|45)$"},
                "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
            }
        ),
    )
    entry = _closed_schema(
        [
            "case_id",
            "primary_coverage_cell_id",
            "pair_memberships",
            "assertion_scope",
            "expected_outcome",
            "expected_reason",
            "fixture_path",
            "fixture_fingerprint",
            "expected_path",
            "expected_fingerprint",
        ],
        _json_object(
            {
                "case_id": nonempty,
                "primary_coverage_cell_id": nonempty,
                "pair_memberships": {
                    "type": "array",
                    "maxItems": 2,
                    "uniqueItems": True,
                    "items": pair,
                },
                "assertion_scope": {"enum": [item.value for item in HKEXCoverageAssertionScope]},
                "expected_outcome": {"enum": [item.value for item in HKEXCoverageOutcome]},
                "expected_reason": {"enum": [item.value for item in HKEXCoverageReason]},
                "fixture_path": nonempty,
                "fixture_fingerprint": fingerprint_schema,
                "expected_path": nonempty,
                "expected_fingerprint": fingerprint_schema,
            }
        ),
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-coverage-decision-catalogue.schema.json",
            "title": "HKEX source-unit coverage executable catalogue",
            **_closed_schema(
                [
                    "schema_id",
                    "schema_version",
                    "catalogue_id",
                    "catalogue_version",
                    "status",
                    "case_count",
                    "primary_coverage_cell_count",
                    "high_risk_pair_ids",
                    "entries",
                    "checkpoint_complete",
                    "full_conformance_suite_complete",
                    "activation_authorized",
                    "external_effects",
                ],
                _json_object(
                    {
                        "schema_id": {
                            "const": "asklegal.hk-regulatory.coverage-decision-catalogue"
                        },
                        "schema_version": {"const": HKEX_COVERAGE_DECISION_CONTRACT_VERSION},
                        "catalogue_id": {"const": "hk-regulatory-coverage-decision"},
                        "catalogue_version": {"const": "1.0.0"},
                        "status": {"const": "FROZEN_EXECUTABLE_CHECKPOINT"},
                        "case_count": {"const": HKEX_COVERAGE_DECISION_CASE_COUNT},
                        "primary_coverage_cell_count": {"const": HKEX_COVERAGE_DECISION_CASE_COUNT},
                        "high_risk_pair_ids": {
                            "const": [
                                "HKREG-PAIR-041",
                                "HKREG-PAIR-042",
                                "HKREG-PAIR-043",
                                "HKREG-PAIR-044",
                                "HKREG-PAIR-045",
                            ]
                        },
                        "entries": {
                            "type": "array",
                            "minItems": HKEX_COVERAGE_DECISION_CASE_COUNT,
                            "maxItems": HKEX_COVERAGE_DECISION_CASE_COUNT,
                            "items": entry,
                        },
                        "checkpoint_complete": {"const": True},
                        "full_conformance_suite_complete": {"const": False},
                        "activation_authorized": {"const": False},
                        "external_effects": {"const": "NONE"},
                    }
                ),
            ),
        }
    )


def build_coverage_decision_rule() -> dict[str, JsonValue]:
    """Declare the exact bounded authority of the 20-case checkpoint."""
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory-coverage-decision-rule",
            "schema_version": HKEX_COVERAGE_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_COVERAGE_DECISION_RULE_ID,
            "status": "SOURCE_NEUTRAL_EXECUTABLE_CHECKPOINT",
            "accepted_adrs": ["0011", "0050", "0069", "0073", "0074", "0075"],
            "case_schema": "contracts/schemas/hkex-coverage-decision-case.schema.json",
            "report_schema": "contracts/schemas/hkex-coverage-decision-report.schema.json",
            "catalogue_schema": "contracts/schemas/hkex-coverage-decision-catalogue.schema.json",
            "catalogue": "catalogues/coverage-decision-cases.json",
            "required_case_count": HKEX_COVERAGE_DECISION_CASE_COUNT,
            "required_primary_coverage_cell_count": HKEX_COVERAGE_DECISION_CASE_COUNT,
            "required_high_risk_pairs": [
                "HKREG-PAIR-041",
                "HKREG-PAIR-042",
                "HKREG-PAIR-043",
                "HKREG-PAIR-044",
                "HKREG-PAIR-045",
            ],
            "accepted_coverage_rule_id": HKEX_ENGLISH_RECORD_RULE_ID,
            "complete_structured_decision_match_required": True,
            "case_id_switching_forbidden": True,
            "coverage_decision_checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "source_authority": False,
            "activation_authority": False,
            "external_effects": "NONE",
        }
    )


@dataclass(frozen=True, slots=True)
class _IdentityDecisionCaseSpec:
    scope: HKEXIdentityAssertionScope
    facts: dict[str, JsonValue]
    expected_outcome: HKEXIdentityDecisionOutcome
    expected_reason: HKEXIdentityDecisionReason


_THIRD_RECORD_ID = f"rec_{'6' * 48}"
_FOURTH_RECORD_ID = f"rec_{'7' * 48}"
_FIFTH_RECORD_ID = f"rec_{'8' * 48}"
_GEM_LEGAL_ITEM_ID = f"lit_{'a' * 48}"
_GEM_LEGAL_LOCATION_ID = f"loc_{'b' * 48}"


def _identity_construction(
    marker: str = "",
    *,
    scope_id: str = HKEX_MAIN_SCOPE_ID,
    authority_note: str = "None",
    transitional: bool = False,
    partition: bool = False,
) -> HKEXEnglishConstructionRequest:
    state = HKEXBranchState.TRANSITIONAL_CURRENT if transitional else HKEXBranchState.CURRENT
    tree = _english_tree(state, partition=partition, branch_suffix=f"-identity-{marker}")
    if marker and not partition:
        units = list(tree.source_units)
        target = units[-1]
        changed_text = f"{target.text} [{marker}]"
        units[-1] = replace(
            target,
            text=changed_text,
            content_fingerprint=_fingerprint(changed_text.encode()),
        )
        tree = replace(tree, source_units=tuple(units))
    if scope_id != tree.scope_id:
        tree = replace(
            tree,
            tree_id=f"{tree.tree_id}-gem",
            component_id="synthetic-component-gem-2.01",
            scope_id=scope_id,
            branch_id=f"{tree.branch_id}-gem",
        )
    profile = _english_profile(authority_note=authority_note)
    effective_context = "Applies to synthetic pre-2026 issuers" if transitional else None
    if partition:
        full = (
            construct_hkex_english_request(
                HKEXEnglishConstructionRequest(tree, profile, effective_context),
                _SyntheticCodepointCounter(),
            )
            .record_results[0]
            .parts[0]
        )
        profile = _english_profile(
            max_text_tokens=full.measurement.text_tokens - 1,
            authority_note=authority_note,
        )
    return HKEXEnglishConstructionRequest(tree, profile, effective_context)


def _permanent_existing(
    record_id: str,
    payload_fingerprint: str,
    *,
    scope_id: str = HKEX_MAIN_SCOPE_ID,
    legal_item_id: str = _LEGAL_ITEM_ID,
    selected: bool = True,
) -> HKEXExistingSearchRecord:
    return HKEXExistingSearchRecord(
        record_id,
        payload_fingerprint,
        scope_id,
        legal_item_id,
        selected,
    )


def _permanent_identity_request(  # noqa: PLR0913
    case_number: int,
    construction: HKEXEnglishConstructionRequest,
    change: HKEXRecordChange,
    *,
    part_number: int = 1,
    legal_item_id: str = _LEGAL_ITEM_ID,
    legal_location_id: str = _LEGAL_LOCATION_ID,
    existing_records: tuple[HKEXExistingSearchRecord, ...] = (),
    predecessor_ids: tuple[str, ...] = (),
    current_legal_support: bool = True,
) -> HKEXRecordIdentityRequest:
    return HKEXRecordIdentityRequest(
        decision_id=f"synthetic-hkex-permanent-identity-{case_number:03d}-{part_number}",
        construction=construction,
        root_record_unit_id="record-root",
        part_number=part_number,
        legal_item_id=legal_item_id,
        official_version_ids=(_OFFICIAL_VERSION_ID,),
        legal_location_ids=(legal_location_id,),
        evidence_refs=(_identity_ref(HKEXTraceabilityReferenceType.SOURCE_SNAPSHOT, "6"),),
        authority_note_decision_ref=_identity_ref(HKEXTraceabilityReferenceType.DECISION, "7"),
        authority_note_supporting_refs=(),
        current_legal_support=current_legal_support,
        existing_records=existing_records,
        predecessor_search_record_ids=predecessor_ids,
        change=change,
        decision_evidence_fingerprint=_SYNTHETIC_PROFILE_FINGERPRINT,
        legal_desk_actor="synthetic-hk-regulatory-legal-desk",
    )


def _identity_lookup(  # noqa: PLR0913
    record_id: str,
    *,
    scope_id: str = HKEX_MAIN_SCOPE_ID,
    legal_location_id: str = _LEGAL_LOCATION_ID,
    payload_digit: str = "1",
    rendered_digit: str = "2",
    authority_digit: str = "3",
    evidence_digit: str = "4",
) -> HKEXIdentityLookupRecord:
    return HKEXIdentityLookupRecord(
        record_id,
        scope_id,
        (legal_location_id,),
        f"sha256:{payload_digit * 64}",
        f"sha256:{rendered_digit * 64}",
        f"sha256:{authority_digit * 64}",
        f"sha256:{evidence_digit * 64}",
    )


def _identity_continuity(support: HKEXContinuitySupport) -> HKEXComponentContinuityRequest:
    return HKEXComponentContinuityRequest(
        decision_id=f"synthetic-identity-continuity-{support.value.lower()}",
        cutoff="2026-08-24T00:00:00Z",
        event=HKEXContinuityEvent.RENUMBERED,
        support=support,
        predecessors=(
            HKEXExistingComponentIdentity(
                "synthetic-component-main-old",
                HKEX_MAIN_SCOPE_ID,
                "synthetic-location-main-old",
                ("Rule 2.01",),
                ("evidence-old",),
            ),
        ),
        candidates=(
            HKEXObservedComponentCandidate(
                "synthetic-candidate-main-renumbered",
                HKEX_MAIN_SCOPE_ID,
                "Rule 2.02",
                ("Rule 2.01", "Rule 2.02"),
                ("evidence-new",),
            ),
        ),
        source_rule_id="HKREG-COMPONENT-CONTINUITY-001",
        evidence_refs=("official-renumbering-notice",),
        evidence_fingerprint=f"sha256:{'d' * 64}",
        legal_desk_actor="synthetic-hk-regulatory-legal-desk",
    )


def _continuity_document(request: HKEXComponentContinuityRequest) -> dict[str, JsonValue]:
    return _json_object(
        {
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
    )


def _identity_facts(  # noqa: PLR0913
    *,
    requests: tuple[HKEXRecordIdentityRequest, ...] = (),
    desired: tuple[HKEXIdentityLookupRecord, ...] = (),
    lookup: tuple[HKEXIdentityLookupRecord, ...] = (),
    lineage: tuple[HKEXSearchRecordLineage, ...] = (),
    existing_ids: tuple[str, ...] = (),
    proposed_ids: tuple[str, ...] = (),
    continuity: HKEXComponentContinuityRequest | None = None,
    presentation_only_change: bool = False,
    traceability_changed: bool = False,
    optional_chinese_changed: bool = False,
    optional_chinese_defect: bool = False,
    cached_embedding_match: bool = False,
) -> dict[str, JsonValue]:
    return _json_object(
        {
            "identity_requests": [item.document() for item in requests],
            "desired_records": [item.document() for item in desired],
            "lookup_entries": [item.document() for item in lookup],
            "lineage_edges": [item.document() for item in lineage],
            "existing_record_ids": list(existing_ids),
            "proposed_record_ids": list(proposed_ids),
            "continuity_request": None if continuity is None else _continuity_document(continuity),
            "presentation_only_change": presentation_only_change,
            "traceability_changed": traceability_changed,
            "optional_chinese_changed": optional_chinese_changed,
            "optional_chinese_defect": optional_chinese_defect,
            "cached_embedding_text_contract_match": cached_embedding_match,
        }
    )


def _identity_decision_case_specs() -> tuple[_IdentityDecisionCaseSpec, ...]:
    ordinary = _identity_construction()
    ordinary_payload = (
        construct_hkex_english_request(ordinary, _SyntheticCodepointCounter())
        .record_results[0]
        .parts[0]
        .serving_payload_fingerprint
    )
    selected = _permanent_existing(_FIRST_RECORD_ID, ordinary_payload)
    older = _permanent_existing(_FIRST_RECORD_ID, ordinary_payload, selected=False)
    other_current = _permanent_existing(_SECOND_RECORD_ID, _OTHER_PAYLOAD_FINGERPRINT)
    gem = _identity_construction(scope_id=HKEX_GEM_SCOPE_ID)
    partition = _identity_construction("partition", partition=True)
    desired = _identity_lookup(_FIRST_RECORD_ID)
    wrong_owner = replace(
        desired,
        scope_id=HKEX_GEM_SCOPE_ID,
        legal_location_ids=(_GEM_LEGAL_LOCATION_ID,),
    )
    mismatched = replace(desired, rendered_fingerprint=f"sha256:{'9' * 64}")
    split = HKEXSearchRecordLineage(
        HKEXSearchRecordLineageType.ONE_TO_MANY,
        (_FIRST_RECORD_ID,),
        (_THIRD_RECORD_ID, _FOURTH_RECORD_ID),
        f"sha256:{'5' * 64}",
    )
    merge = HKEXSearchRecordLineage(
        HKEXSearchRecordLineageType.MANY_TO_ONE,
        (_FIRST_RECORD_ID, _SECOND_RECORD_ID),
        (_FIFTH_RECORD_ID,),
        f"sha256:{'6' * 64}",
    )

    def changed(number: int, change: HKEXRecordChange) -> HKEXRecordIdentityRequest:
        construction = _identity_construction(
            f"change-{number}",
            transitional=(change is HKEXRecordChange.APPLICABILITY_CONTEXT_CHANGED),
        )
        return _permanent_identity_request(
            number,
            construction,
            change,
            existing_records=(_permanent_existing(_FIRST_RECORD_ID, _OTHER_PAYLOAD_FINGERPRINT),),
            predecessor_ids=(_FIRST_RECORD_ID,),
        )

    def spec(
        scope: HKEXIdentityAssertionScope,
        facts: dict[str, JsonValue],
        outcome: HKEXIdentityDecisionOutcome,
        reason: HKEXIdentityDecisionReason,
    ) -> _IdentityDecisionCaseSpec:
        return _IdentityDecisionCaseSpec(scope, facts, outcome, reason)

    return (
        spec(
            HKEXIdentityAssertionScope.BOARD_SEPARATION,
            _identity_facts(
                requests=(
                    _permanent_identity_request(1, ordinary, HKEXRecordChange.INITIAL),
                    _permanent_identity_request(
                        1,
                        gem,
                        HKEXRecordChange.INITIAL,
                        legal_item_id=_GEM_LEGAL_ITEM_ID,
                        legal_location_id=_GEM_LEGAL_LOCATION_ID,
                    ),
                )
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.SEPARATE_BOARD_IDENTITIES,
        ),
        spec(
            HKEXIdentityAssertionScope.EXACT_REUSE,
            _identity_facts(
                requests=(
                    _permanent_identity_request(
                        2,
                        ordinary,
                        HKEXRecordChange.SIX_FIELD_UNCHANGED,
                        existing_records=(selected,),
                        predecessor_ids=(_FIRST_RECORD_ID,),
                    ),
                )
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.EXACT_RECORD_REUSED,
        ),
        spec(
            HKEXIdentityAssertionScope.RESELECTION,
            _identity_facts(
                requests=(
                    _permanent_identity_request(
                        3,
                        ordinary,
                        HKEXRecordChange.REINSTATEMENT,
                        existing_records=(older, other_current),
                        predecessor_ids=(_SECOND_RECORD_ID,),
                    ),
                ),
                traceability_changed=True,
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.PRESERVED_RECORD_RESELECTED,
        ),
        spec(
            HKEXIdentityAssertionScope.PRIMARY_TEXT_CHANGE,
            _identity_facts(requests=(changed(4, HKEXRecordChange.PRIMARY_TEXT_CHANGED),)),
            HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
            HKEXIdentityDecisionReason.PRIMARY_TEXT_SUCCESSOR_REQUIRED,
        ),
        spec(
            HKEXIdentityAssertionScope.APPLICABILITY_CHANGE,
            _identity_facts(requests=(changed(5, HKEXRecordChange.APPLICABILITY_CONTEXT_CHANGED),)),
            HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
            HKEXIdentityDecisionReason.APPLICABILITY_SUCCESSOR_REQUIRED,
        ),
        spec(
            HKEXIdentityAssertionScope.GOVERNING_DEPENDENCY_CHANGE,
            _identity_facts(requests=(changed(6, HKEXRecordChange.GOVERNING_CONTEXT_CHANGED),)),
            HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
            HKEXIdentityDecisionReason.GOVERNING_DEPENDENCY_SUCCESSOR_REQUIRED,
        ),
        spec(
            HKEXIdentityAssertionScope.REFERENCED_LOCATION_CHANGE,
            _identity_facts(requests=(changed(7, HKEXRecordChange.REFERENCED_LOCATION_CHANGED),)),
            HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
            HKEXIdentityDecisionReason.REFERENCED_LOCATION_SUCCESSOR_REQUIRED,
        ),
        spec(
            HKEXIdentityAssertionScope.STRUCTURED_PROJECTION_CHANGE,
            _identity_facts(requests=(changed(8, HKEXRecordChange.STRUCTURED_PROJECTION_CHANGED),)),
            HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
            HKEXIdentityDecisionReason.STRUCTURED_PROJECTION_SUCCESSOR_REQUIRED,
        ),
        spec(
            HKEXIdentityAssertionScope.PARTITION_CHANGE,
            _identity_facts(
                requests=tuple(
                    _permanent_identity_request(
                        9,
                        partition,
                        HKEXRecordChange.PARTITION_CHANGED,
                        part_number=part,
                        existing_records=(
                            _permanent_existing(record_id, _OTHER_PAYLOAD_FINGERPRINT),
                        ),
                        predecessor_ids=(record_id,),
                    )
                    for part, record_id in ((1, _FIRST_RECORD_ID), (2, _SECOND_RECORD_ID))
                )
            ),
            HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
            HKEXIdentityDecisionReason.PARTITION_SUCCESSORS_REQUIRED,
        ),
        spec(
            HKEXIdentityAssertionScope.AUTHORITY_NOTE_CHANGE,
            _identity_facts(
                requests=(
                    _permanent_identity_request(
                        10,
                        _identity_construction(authority_note="Synthetic current authority note."),
                        HKEXRecordChange.AUTHORITY_NOTE_CHANGED,
                        existing_records=(
                            _permanent_existing(_FIRST_RECORD_ID, _OTHER_PAYLOAD_FINGERPRINT),
                        ),
                        predecessor_ids=(_FIRST_RECORD_ID,),
                    ),
                ),
                cached_embedding_match=True,
            ),
            HKEXIdentityDecisionOutcome.REQUIRE_NEW_RECORD,
            HKEXIdentityDecisionReason.AUTHORITY_NOTE_SUCCESSOR_REQUIRED,
        ),
        spec(
            HKEXIdentityAssertionScope.URL_MOVE,
            _identity_facts(
                requests=(
                    _permanent_identity_request(
                        11,
                        ordinary,
                        HKEXRecordChange.TRACEABILITY_ONLY,
                        existing_records=(selected,),
                        predecessor_ids=(_FIRST_RECORD_ID,),
                    ),
                ),
                traceability_changed=True,
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.URL_MOVE_REUSES_RECORD,
        ),
        spec(
            HKEXIdentityAssertionScope.PAGE_REFLOW,
            _identity_facts(
                requests=(
                    _permanent_identity_request(
                        12,
                        ordinary,
                        HKEXRecordChange.TRACEABILITY_ONLY,
                        existing_records=(selected,),
                        predecessor_ids=(_FIRST_RECORD_ID,),
                    ),
                ),
                presentation_only_change=True,
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.PAGE_REFLOW_REUSES_RECORD,
        ),
        spec(
            HKEXIdentityAssertionScope.OPTIONAL_CHINESE_CHANGE,
            _identity_facts(
                requests=(
                    _permanent_identity_request(
                        13,
                        ordinary,
                        HKEXRecordChange.TRACEABILITY_ONLY,
                        existing_records=(selected,),
                        predecessor_ids=(_FIRST_RECORD_ID,),
                    ),
                ),
                optional_chinese_changed=True,
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.OPTIONAL_CHINESE_CHANGE_REUSES_RECORD,
        ),
        spec(
            HKEXIdentityAssertionScope.TRACEABILITY_ONLY,
            _identity_facts(
                requests=(
                    _permanent_identity_request(
                        14,
                        ordinary,
                        HKEXRecordChange.TRACEABILITY_ONLY,
                        existing_records=(selected,),
                        predecessor_ids=(_FIRST_RECORD_ID,),
                    ),
                ),
                traceability_changed=True,
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.TRACEABILITY_REVISION_ONLY,
        ),
        spec(
            HKEXIdentityAssertionScope.CHINESE_DEFECT,
            _identity_facts(
                requests=(
                    _permanent_identity_request(
                        15, ordinary, HKEXRecordChange.INITIAL, current_legal_support=False
                    ),
                ),
                optional_chinese_changed=True,
                optional_chinese_defect=True,
            ),
            HKEXIdentityDecisionOutcome.BLOCK,
            HKEXIdentityDecisionReason.ENGLISH_SUPPORT_BLOCKED,
        ),
        spec(
            HKEXIdentityAssertionScope.LOOKUP_VALID,
            _identity_facts(desired=(desired,), lookup=(desired,)),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.LOOKUP_ENTRY_VALID,
        ),
        spec(
            HKEXIdentityAssertionScope.LOOKUP_INCOMPLETE,
            _identity_facts(
                desired=(desired, _identity_lookup(_SECOND_RECORD_ID, payload_digit="5")),
                lookup=(desired, desired, _identity_lookup(_THIRD_RECORD_ID, payload_digit="6")),
            ),
            HKEXIdentityDecisionOutcome.BLOCK,
            HKEXIdentityDecisionReason.LOOKUP_INCOMPLETE,
        ),
        spec(
            HKEXIdentityAssertionScope.LOOKUP_WRONG_OWNER,
            _identity_facts(desired=(desired,), lookup=(wrong_owner,)),
            HKEXIdentityDecisionOutcome.BLOCK,
            HKEXIdentityDecisionReason.LOOKUP_OWNERSHIP_MISMATCH,
        ),
        spec(
            HKEXIdentityAssertionScope.LINEAGE_ONE_TO_ONE,
            _identity_facts(
                lineage=(
                    HKEXSearchRecordLineage(
                        HKEXSearchRecordLineageType.ONE_TO_ONE,
                        (_FIRST_RECORD_ID,),
                        (_THIRD_RECORD_ID,),
                        f"sha256:{'5' * 64}",
                    ),
                ),
                existing_ids=(_FIRST_RECORD_ID,),
                proposed_ids=(_THIRD_RECORD_ID,),
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.ONE_TO_ONE_LINEAGE_VALID,
        ),
        spec(
            HKEXIdentityAssertionScope.LINEAGE_SPLIT_MERGE,
            _identity_facts(
                lineage=(split, merge),
                existing_ids=(_FIRST_RECORD_ID, _SECOND_RECORD_ID),
                proposed_ids=(_THIRD_RECORD_ID, _FOURTH_RECORD_ID, _FIFTH_RECORD_ID),
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.SPLIT_MERGE_LINEAGE_VALID,
        ),
        spec(
            HKEXIdentityAssertionScope.LINEAGE_CYCLE,
            _identity_facts(
                lineage=(
                    HKEXSearchRecordLineage(
                        HKEXSearchRecordLineageType.ONE_TO_ONE,
                        (_FIRST_RECORD_ID,),
                        (_SECOND_RECORD_ID,),
                        f"sha256:{'7' * 64}",
                    ),
                    HKEXSearchRecordLineage(
                        HKEXSearchRecordLineageType.ONE_TO_ONE,
                        (_SECOND_RECORD_ID,),
                        (_FIRST_RECORD_ID,),
                        f"sha256:{'8' * 64}",
                    ),
                ),
                existing_ids=(_FIRST_RECORD_ID, _SECOND_RECORD_ID),
                proposed_ids=(_FIRST_RECORD_ID, _SECOND_RECORD_ID),
            ),
            HKEXIdentityDecisionOutcome.BLOCK,
            HKEXIdentityDecisionReason.LINEAGE_REJECTED,
        ),
        spec(
            HKEXIdentityAssertionScope.PROVED_CONTINUITY,
            _identity_facts(
                continuity=_identity_continuity(HKEXContinuitySupport.PROVED),
                traceability_changed=True,
            ),
            HKEXIdentityDecisionOutcome.PASS,
            HKEXIdentityDecisionReason.OFFICIAL_CONTINUITY_PROVED,
        ),
        spec(
            HKEXIdentityAssertionScope.SIMILARITY_ONLY,
            _identity_facts(
                continuity=_identity_continuity(HKEXContinuitySupport.SIMILARITY_OR_ALIAS_ONLY)
            ),
            HKEXIdentityDecisionOutcome.QUARANTINE,
            HKEXIdentityDecisionReason.SIMILARITY_CONTINUITY_QUARANTINED,
        ),
        spec(
            HKEXIdentityAssertionScope.LOOKUP_FINGERPRINT_MISMATCH,
            _identity_facts(desired=(desired,), lookup=(mismatched,)),
            HKEXIdentityDecisionOutcome.BLOCK,
            HKEXIdentityDecisionReason.LOOKUP_FINGERPRINT_MISMATCH,
        ),
    )


def _identity_contract_bindings(universe_fingerprint: str) -> list[JsonValue]:
    def binding(contract_id: str, version: str, rule_id: str) -> JsonValue:
        seed = _json_object(
            {"contract_id": contract_id, "contract_version": version, "rule_id": rule_id}
        )
        return {
            "contract_id": contract_id,
            "version": version,
            "fingerprint": _fingerprint(rfc8785.dumps(seed)),
        }

    return [
        {
            "contract_id": "asklegal.hk-regulatory.conformance-universe",
            "version": "1.0.0",
            "fingerprint": universe_fingerprint,
        },
        binding(
            "asklegal.hk-regulatory.english-record",
            HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            HKEX_ENGLISH_RECORD_RULE_ID,
        ),
        binding(
            "asklegal.hk-regulatory.record-identity",
            HKEX_RECORD_IDENTITY_CONTRACT_VERSION,
            HKEX_RECORD_IDENTITY_RULE_ID,
        ),
        binding(
            "asklegal.hk-regulatory.component-continuity", "1.0.0", "HKREG-COMPONENT-CONTINUITY-001"
        ),
        binding(
            "asklegal.hk-regulatory.identity-decision-case",
            HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
            HKEX_IDENTITY_DECISION_RULE_ID,
        ),
    ]


def _identity_seed_expected(case_id: str, spec: _IdentityDecisionCaseSpec) -> dict[str, JsonValue]:
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.identity-decision-result",
            "schema_version": HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_IDENTITY_DECISION_RULE_ID,
            "case_id": case_id,
            "outcome": spec.expected_outcome.value,
            "reason": spec.expected_reason.value,
            "record_action": "BLOCK",
            "traceability_action": "BLOCK",
            "identity_consequences": [],
            "selected_search_record_ids": [],
            "predecessor_search_record_ids": [],
            "register_allocation_count": 0,
            "board_separation_valid": False,
            "lookup_valid": True,
            "lineage_valid": True,
            "traceability_revision_required": False,
            "cached_embedding_reuse_permitted": False,
            "quarantine_required": False,
            "violation_codes": [],
            "search_record_authorized": False,
            "embedding_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "deployment_authorized": False,
            "external_effects": "NONE",
        }
    )


def build_identity_decision_cases() -> tuple[
    tuple[dict[str, JsonValue], dict[str, JsonValue]], ...
]:
    """Build all 24 permanent immutable identity/lineage/traceability cases."""
    universe = build_conformance_universe()
    universe_cases = tuple(
        _json_object(item)
        for item in _json_array(universe["cases"])
        if str(_json_object(item)["case_id"]).startswith("HKREG-DET-IDN-")
    )
    specs = _identity_decision_case_specs()
    if (
        len(universe_cases) != HKEX_IDENTITY_DECISION_CASE_COUNT
        or len(specs) != HKEX_IDENTITY_DECISION_CASE_COUNT
    ):
        raise _ConformanceBuildError
    universe_fingerprint = _fingerprint(rfc8785.dumps(universe))
    bindings = _identity_contract_bindings(universe_fingerprint)
    results: list[tuple[dict[str, JsonValue], dict[str, JsonValue]]] = []
    for universe_case, spec in zip(universe_cases, specs, strict=True):
        case_id = str(universe_case["case_id"])
        facts = deepcopy(spec.facts)
        fixture = _json_object(
            {
                "schema_id": "asklegal.hk-regulatory.identity-decision-case",
                "schema_version": HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
                "package_contract_version": "1.0.0",
                "case_id": case_id,
                "suite_layer": "DECISION_TO_ARTIFACT",
                "primary_checkpoint": "IDENTITY_LINEAGE",
                "frozen": True,
                "synthetic_evidence_class": "SYNTHETIC_NO_REAL_AUTHORITY",
                "contract_bindings": deepcopy(bindings),
                "synthetic_cutoff": "2026-08-24T00:00:00Z",
                "scope_id": "HKEX_CROSS_BOARD",
                "prior_state": "SYNTHETIC_ACCEPTED_PREDECESSOR",
                "primary_coverage_cell_ids": [universe_case["coverage_cell_id"]],
                "secondary_coverage_cell_ids": [],
                "pair_memberships": deepcopy(_json_array(universe_case["pair_memberships"])),
                "declared_input_inventory": ["identity-evidence"],
                "declared_reference_inventory": [
                    str(_json_object(item)["contract_id"]) for item in bindings
                ],
                "declared_expected_inventory": ["IDENTITY_DECISION_REPORT"],
                "assertion_scope": spec.scope.value,
                "required_result_dimensions": [
                    "BOARD_OWNERSHIP",
                    "FORBIDDEN_EFFECTS",
                    "IMMUTABLE_IDENTITY",
                    "LINEAGE",
                    "TRACEABILITY_LOOKUP",
                ],
                "evidence_packet_fields": sorted(facts),
                "supporting_evidence_ranges": [f"input/{case_id}-identity-evidence.json#facts"],
                "rule_trace": sorted(
                    [
                        "HKREG-COMPONENT-CONTINUITY-001",
                        HKEX_ENGLISH_RECORD_RULE_ID,
                        HKEX_IDENTITY_DECISION_RULE_ID,
                        HKEX_RECORD_IDENTITY_RULE_ID,
                    ]
                ),
                "established_facts": ["SYNTHETIC_IDENTITY_FACT_PACKET_DECLARED"],
                "unresolved_facts": [spec.expected_reason.value]
                if spec.expected_outcome
                in {HKEXIdentityDecisionOutcome.BLOCK, HKEXIdentityDecisionOutcome.QUARANTINE}
                else [],
                "permitted_equivalent_results": [],
                "critical_error_codes": [spec.expected_reason.value]
                if spec.expected_outcome is HKEXIdentityDecisionOutcome.BLOCK
                else [],
                "package_fingerprint": universe_fingerprint,
                "title": universe_case["synthetic_scenario"],
                "purpose": universe_case["exact_required_result"],
                "expected_decision": _identity_seed_expected(case_id, spec),
                "evidence_packet": {
                    "slot_id": "identity-evidence",
                    "state": "AVAILABLE",
                    "path": f"input/{case_id}-identity-evidence.json",
                    "role": "ORDINARY",
                    "media_type": "application/json",
                    "content_fingerprint": _fingerprint(rfc8785.dumps(facts)),
                },
                "facts": facts,
                "case_fingerprint": "PENDING",
            }
        )
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        seeded = hkex_identity_decision_case_from_document(fixture)
        try:
            observed = decide_hkex_identity_case(seeded)
        except ValueError as error:
            raise _ConformanceBuildError(case_id) from error
        if (
            observed.outcome is not spec.expected_outcome
            or observed.reason is not spec.expected_reason
        ):
            raise _ConformanceBuildError(case_id)
        fixture["expected_decision"] = checked_json_value(observed.document(case_id=case_id))
        projection = dict(fixture)
        projection.pop("case_fingerprint")
        fixture["case_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
        parsed = hkex_identity_decision_case_from_document(fixture)
        report = _json_object(run_hkex_identity_case(parsed).document())
        if report["conformance_status"] != "PASS":
            raise _ConformanceBuildError(case_id)
        results.append((fixture, report))
    return tuple(results)


def build_identity_decision_catalogue(
    cases: tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...],
) -> dict[str, JsonValue]:
    """Bind all 24 exact identity fact packets and reports."""
    entries: list[JsonValue] = []
    for fixture, report in cases:
        case_id = str(fixture["case_id"])
        expected = _json_object(fixture["expected_decision"])
        entries.append(
            {
                "case_id": case_id,
                "primary_coverage_cell_id": _json_array(fixture["primary_coverage_cell_ids"])[0],
                "pair_memberships": fixture["pair_memberships"],
                "assertion_scope": fixture["assertion_scope"],
                "expected_outcome": expected["outcome"],
                "expected_reason": expected["reason"],
                "fixture_path": f"fixtures/conformance/identity-decision/{case_id}.json",
                "fixture_fingerprint": _fingerprint(
                    (json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode()
                ),
                "expected_path": f"expected/conformance/identity-decision/{case_id}.json",
                "expected_fingerprint": _fingerprint(
                    (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode()
                ),
            }
        )
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory.identity-decision-catalogue",
            "schema_version": HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
            "catalogue_id": "hk-regulatory-identity-decision",
            "catalogue_version": "1.0.0",
            "status": "FROZEN_EXECUTABLE_CHECKPOINT",
            "case_count": HKEX_IDENTITY_DECISION_CASE_COUNT,
            "primary_coverage_cell_count": HKEX_IDENTITY_DECISION_CASE_COUNT,
            "high_risk_pair_ids": [f"HKREG-PAIR-{number:03d}" for number in range(46, 50)],
            "entries": entries,
            "checkpoint_complete": True,
            "full_conformance_suite_complete": False,
            "activation_authorized": False,
            "external_effects": "NONE",
        }
    )


def _identity_decision_schema() -> dict[str, JsonValue]:
    return _json_object(
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
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
            ],
            "properties": {
                "schema_id": {"const": "asklegal.hk-regulatory.identity-decision-result"},
                "schema_version": {"const": HKEX_IDENTITY_DECISION_CONTRACT_VERSION},
                "rule_id": {"const": HKEX_IDENTITY_DECISION_RULE_ID},
                "case_id": {"type": "string", "pattern": "^HKREG-DET-IDN-(0[0-1][0-9]|02[0-4])$"},
                "outcome": {"enum": [item.value for item in HKEXIdentityDecisionOutcome]},
                "reason": {"enum": [item.value for item in HKEXIdentityDecisionReason]},
                "record_action": {
                    "enum": [
                        "SEPARATE_INITIALS",
                        "REUSE",
                        "RESELECT",
                        "REQUIRE_NEW",
                        "NO_ID_CHANGE",
                        "VALIDATE_ONLY",
                        "BLOCK",
                        "QUARANTINE",
                    ]
                },
                "traceability_action": {"enum": ["NONE", "REVISE", "VALIDATE", "BLOCK"]},
                "identity_consequences": {"type": "array", "items": {"type": "string"}},
                "selected_search_record_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": "^rec_[0-9a-f]{48}$"},
                    "uniqueItems": True,
                },
                "predecessor_search_record_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": "^rec_[0-9a-f]{48}$"},
                    "uniqueItems": True,
                },
                "register_allocation_count": {"type": "integer", "minimum": 0},
                "board_separation_valid": {"type": "boolean"},
                "lookup_valid": {"type": "boolean"},
                "lineage_valid": {"type": "boolean"},
                "traceability_revision_required": {"type": "boolean"},
                "cached_embedding_reuse_permitted": {"type": "boolean"},
                "quarantine_required": {"type": "boolean"},
                "violation_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                },
                "search_record_authorized": {"const": False},
                "embedding_authorized": {"const": False},
                "release_authorized": {"const": False},
                "serving_authorized": {"const": False},
                "deployment_authorized": {"const": False},
                "external_effects": {"const": "NONE"},
            },
        }
    )


def build_identity_decision_case_schema() -> dict[str, JsonValue]:
    """Build the closed schema for one identity conformance case."""
    base = _json_object(build_coverage_decision_case_schema())
    properties = _json_object(base["properties"])
    fingerprint_schema: dict[str, JsonValue] = {
        "type": "string",
        "pattern": "^sha256:[0-9a-f]{64}$",
    }
    record_id_schema: dict[str, JsonValue] = {
        "type": "string",
        "pattern": "^rec_[0-9a-f]{48}$",
    }
    lookup_record: dict[str, JsonValue] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "search_record_id",
            "scope_id",
            "legal_location_ids",
            "serving_payload_fingerprint",
            "rendered_fingerprint",
            "authority_note_fingerprint",
            "evidence_fingerprint",
        ],
        "properties": {
            "search_record_id": record_id_schema,
            "scope_id": {"enum": list(HKEX_SCOPE_IDS)},
            "legal_location_ids": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "string", "pattern": "^loc_[0-9a-f]{48}$"},
            },
            "serving_payload_fingerprint": fingerprint_schema,
            "rendered_fingerprint": fingerprint_schema,
            "authority_note_fingerprint": fingerprint_schema,
            "evidence_fingerprint": fingerprint_schema,
        },
    }
    record_ids: dict[str, JsonValue] = {
        "type": "array",
        "uniqueItems": True,
        "items": record_id_schema,
    }
    properties.update(
        _json_object(
            {
                "schema_id": {"const": "asklegal.hk-regulatory.identity-decision-case"},
                "schema_version": {"const": HKEX_IDENTITY_DECISION_CONTRACT_VERSION},
                "case_id": {"type": "string", "pattern": "^HKREG-DET-IDN-(0[0-1][0-9]|02[0-4])$"},
                "primary_checkpoint": {"const": "IDENTITY_LINEAGE"},
                "contract_bindings": {
                    "type": "array",
                    "minItems": 5,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["contract_id", "version", "fingerprint"],
                        "properties": {
                            "contract_id": {"type": "string", "minLength": 1},
                            "version": {"const": "1.0.0"},
                            "fingerprint": fingerprint_schema,
                        },
                    },
                },
                "primary_coverage_cell_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {
                        "type": "string",
                        "pattern": "^HKREG-COV-DIDN-(0[0-1][0-9]|02[0-4])$",
                    },
                },
                "pair_memberships": {
                    "type": "array",
                    "maxItems": 2,
                    "uniqueItems": True,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["pair_id", "role"],
                        "properties": {
                            "pair_id": {"type": "string", "pattern": "^HKREG-PAIR-0(46|47|48|49)$"},
                            "role": {"enum": ["POSITIVE", "NEAR_MISS"]},
                        },
                    },
                },
                "declared_input_inventory": {"const": ["identity-evidence"]},
                "declared_reference_inventory": {
                    "const": [
                        "asklegal.hk-regulatory.conformance-universe",
                        "asklegal.hk-regulatory.english-record",
                        "asklegal.hk-regulatory.record-identity",
                        "asklegal.hk-regulatory.component-continuity",
                        "asklegal.hk-regulatory.identity-decision-case",
                    ]
                },
                "declared_expected_inventory": {"const": ["IDENTITY_DECISION_REPORT"]},
                "assertion_scope": {"enum": [item.value for item in HKEXIdentityAssertionScope]},
                "required_result_dimensions": {
                    "const": [
                        "BOARD_OWNERSHIP",
                        "FORBIDDEN_EFFECTS",
                        "IMMUTABLE_IDENTITY",
                        "LINEAGE",
                        "TRACEABILITY_LOOKUP",
                    ]
                },
                "evidence_packet_fields": {
                    "const": sorted(
                        {
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
                    )
                },
                "expected_decision": _identity_decision_schema(),
                "evidence_packet": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "slot_id",
                        "state",
                        "path",
                        "role",
                        "media_type",
                        "content_fingerprint",
                    ],
                    "properties": {
                        "slot_id": {"const": "identity-evidence"},
                        "state": {"const": "AVAILABLE"},
                        "path": {"type": "string", "minLength": 1},
                        "role": {"const": "ORDINARY"},
                        "media_type": {"const": "application/json"},
                        "content_fingerprint": fingerprint_schema,
                    },
                },
                "facts": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
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
                    ],
                    "properties": {
                        "identity_requests": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {"type": "object"},
                        },
                        "desired_records": {"type": "array", "items": lookup_record},
                        "lookup_entries": {"type": "array", "items": lookup_record},
                        "lineage_edges": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "lineage_type",
                                    "predecessor_ids",
                                    "successor_ids",
                                    "evidence_fingerprint",
                                ],
                                "properties": {
                                    "lineage_type": {
                                        "enum": [item.value for item in HKEXSearchRecordLineageType]
                                    },
                                    "predecessor_ids": record_ids,
                                    "successor_ids": record_ids,
                                    "evidence_fingerprint": fingerprint_schema,
                                },
                            },
                        },
                        "existing_record_ids": record_ids,
                        "proposed_record_ids": record_ids,
                        "continuity_request": {"oneOf": [{"type": "object"}, {"type": "null"}]},
                        "presentation_only_change": {"type": "boolean"},
                        "traceability_changed": {"type": "boolean"},
                        "optional_chinese_changed": {"type": "boolean"},
                        "optional_chinese_defect": {"type": "boolean"},
                        "cached_embedding_text_contract_match": {"type": "boolean"},
                    },
                },
            }
        )
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-identity-decision-case.schema.json",
            "title": "HKEX permanent identity decision case",
            "type": "object",
            "additionalProperties": False,
            "required": base["required"],
            "properties": properties,
        }
    )


def build_identity_decision_report_schema() -> dict[str, JsonValue]:
    """Build the closed report schema for one identity case."""
    decision = _identity_decision_schema()
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-identity-decision-report.schema.json",
            "title": "HKEX permanent identity decision report",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_id",
                "schema_version",
                "rule_id",
                "case_id",
                "assertion_scope",
                "observed_decision",
                "expected_decision",
                "conformance_status",
                "source_authorized",
                "provider_authorized",
                "release_authorized",
                "serving_authorized",
                "deployment_authorized",
                "external_effects",
            ],
            "properties": {
                "schema_id": {"const": "asklegal.hk-regulatory.identity-decision-report"},
                "schema_version": {"const": HKEX_IDENTITY_DECISION_CONTRACT_VERSION},
                "rule_id": {"const": HKEX_IDENTITY_DECISION_RULE_ID},
                "case_id": {"type": "string", "pattern": "^HKREG-DET-IDN-(0[0-1][0-9]|02[0-4])$"},
                "assertion_scope": {"enum": [item.value for item in HKEXIdentityAssertionScope]},
                "observed_decision": decision,
                "expected_decision": decision,
                "conformance_status": {"const": "PASS"},
                "source_authorized": {"const": False},
                "provider_authorized": {"const": False},
                "release_authorized": {"const": False},
                "serving_authorized": {"const": False},
                "deployment_authorized": {"const": False},
                "external_effects": {"const": "NONE"},
            },
        }
    )


def build_identity_decision_catalogue_schema() -> dict[str, JsonValue]:
    """Build the closed catalogue schema for all 24 identity cases."""
    entry = _json_object(
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "case_id",
                "primary_coverage_cell_id",
                "pair_memberships",
                "assertion_scope",
                "expected_outcome",
                "expected_reason",
                "fixture_path",
                "fixture_fingerprint",
                "expected_path",
                "expected_fingerprint",
            ],
            "properties": {
                "case_id": {"type": "string", "pattern": "^HKREG-DET-IDN-(0[0-1][0-9]|02[0-4])$"},
                "primary_coverage_cell_id": {
                    "type": "string",
                    "pattern": "^HKREG-COV-DIDN-(0[0-1][0-9]|02[0-4])$",
                },
                "pair_memberships": {"type": "array"},
                "assertion_scope": {"enum": [item.value for item in HKEXIdentityAssertionScope]},
                "expected_outcome": {"enum": [item.value for item in HKEXIdentityDecisionOutcome]},
                "expected_reason": {"enum": [item.value for item in HKEXIdentityDecisionReason]},
                "fixture_path": {
                    "type": "string",
                    "pattern": (
                        "^fixtures/conformance/identity-decision/HKREG-DET-IDN-\\d{3}\\.json$"
                    ),
                },
                "fixture_fingerprint": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                "expected_path": {
                    "type": "string",
                    "pattern": (
                        "^expected/conformance/identity-decision/HKREG-DET-IDN-\\d{3}\\.json$"
                    ),
                },
                "expected_fingerprint": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            },
        }
    )
    return _json_object(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ask.legal/schemas/hkex-identity-decision-catalogue.schema.json",
            "title": "HKEX permanent identity decision catalogue",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_id",
                "schema_version",
                "catalogue_id",
                "catalogue_version",
                "status",
                "case_count",
                "primary_coverage_cell_count",
                "high_risk_pair_ids",
                "entries",
                "checkpoint_complete",
                "full_conformance_suite_complete",
                "activation_authorized",
                "external_effects",
            ],
            "properties": {
                "schema_id": {"const": "asklegal.hk-regulatory.identity-decision-catalogue"},
                "schema_version": {"const": HKEX_IDENTITY_DECISION_CONTRACT_VERSION},
                "catalogue_id": {"const": "hk-regulatory-identity-decision"},
                "catalogue_version": {"const": "1.0.0"},
                "status": {"const": "FROZEN_EXECUTABLE_CHECKPOINT"},
                "case_count": {"const": HKEX_IDENTITY_DECISION_CASE_COUNT},
                "primary_coverage_cell_count": {"const": HKEX_IDENTITY_DECISION_CASE_COUNT},
                "high_risk_pair_ids": {
                    "const": [f"HKREG-PAIR-{number:03d}" for number in range(46, 50)]
                },
                "entries": {
                    "type": "array",
                    "minItems": HKEX_IDENTITY_DECISION_CASE_COUNT,
                    "maxItems": HKEX_IDENTITY_DECISION_CASE_COUNT,
                    "items": entry,
                },
                "checkpoint_complete": {"const": True},
                "full_conformance_suite_complete": {"const": False},
                "activation_authorized": {"const": False},
                "external_effects": {"const": "NONE"},
            },
        }
    )


def build_identity_decision_rule() -> dict[str, JsonValue]:
    """Declare the exact bounded authority of the final 24-case checkpoint."""
    return _json_object(
        {
            "schema_id": "asklegal.hk-regulatory-identity-decision-rule",
            "schema_version": HKEX_IDENTITY_DECISION_CONTRACT_VERSION,
            "rule_id": HKEX_IDENTITY_DECISION_RULE_ID,
            "status": "SOURCE_NEUTRAL_EXECUTABLE_CHECKPOINT",
            "accepted_adrs": ["0011", "0050", "0069", "0073", "0074", "0075", "0078"],
            "case_schema": "contracts/schemas/hkex-identity-decision-case.schema.json",
            "report_schema": "contracts/schemas/hkex-identity-decision-report.schema.json",
            "catalogue_schema": "contracts/schemas/hkex-identity-decision-catalogue.schema.json",
            "catalogue": "catalogues/identity-decision-cases.json",
            "required_case_count": HKEX_IDENTITY_DECISION_CASE_COUNT,
            "required_primary_coverage_cell_count": HKEX_IDENTITY_DECISION_CASE_COUNT,
            "required_high_risk_pairs": [f"HKREG-PAIR-{number:03d}" for number in range(46, 50)],
            "accepted_record_identity_rule_id": HKEX_RECORD_IDENTITY_RULE_ID,
            "accepted_component_continuity_rule_id": "HKREG-COMPONENT-CONTINUITY-001",
            "complete_structured_decision_match_required": True,
            "case_id_switching_forbidden": True,
            "identity_decision_checkpoint_complete": True,
            "full_conformance_case_universe_executable": True,
            "conformance_admission_complete": False,
            "source_authority": False,
            "activation_authority": False,
            "external_effects": "NONE",
        }
    )


def build_manifest() -> dict[str, JsonValue]:
    """Build the exact two-scope package root without activation authority."""
    files: list[JsonValue] = []
    for path in sorted(PACKAGE_ROOT.rglob("*"), key=lambda item: item.as_posix().encode()):
        if not path.is_file() or path.name == "package.json":
            continue
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        raw = path.read_bytes()
        files.append(
            {
                "byte_size": len(raw),
                "fingerprint": _fingerprint(raw),
                "path": relative,
                "role": _role(relative),
            }
        )
    contract_manifest = json.loads((ROOT / "contracts/package-manifest.json").read_text())
    contract_fingerprint = _fingerprint(rfc8785.dumps(contract_manifest))
    scope_readiness: list[JsonValue] = [
        {
            "scope_id": "rsc_000000000000000000000000000000000000000000000301",
            "state": "NOT_READY",
        },
        {
            "scope_id": "rsc_000000000000000000000000000000000000000000000302",
            "state": "NOT_READY",
        },
    ]
    document: dict[str, JsonValue] = {
        "schema_id": "asklegal.executable-source-rulebook-package",
        "schema_version": "1.0.0",
        "package_id": "rbp_5d8c04afcd2b48269373b2363ea82b1230d1a7be8ad43841",
        "package_version": "0.14.0",
        "package_fingerprint": "PENDING",
        "jurisdiction": "HK",
        "environment": "PRODUCTION",
        "material_family": "REGULATORY_MATERIALS",
        "legal_desk_owner": "UNASSIGNED_HONG_KONG_REGULATORY_MATERIALS_LEGAL_DESK",
        "effective_cutoff": "2026-08-24T00:00:00Z",
        "predecessor": None,
        "contract_locks": [contract_fingerprint],
        "code_locks": ["asklegal-legal-desks==0.1.0", "asklegal-processing==0.1.0"],
        "source_universe_fingerprint": _fingerprint(
            (PACKAGE_ROOT / "sources/source-universe.json").read_bytes()
        ),
        "scope_readiness": scope_readiness,
        "unresolved_policy_codes": BLOCKERS,
        "impact_declaration": (
            "SOURCE_NEUTRAL_FIVE_ROLE_TWO_SCOPE_COMPONENT_INVENTORY_ACCOUNTING_"
            "APPLICABILITY_BRANCH_EFFECTIVE_STATE_AND_COMPONENT_CONTINUITY_"
            "ENGLISH_TREE_RENDER_PARTITION_COVERAGE_RECORD_IDENTITY_TRACEABILITY_"
            "COMPLETE_284_CASE_57_PAIR_UNIVERSE_IDENTITY_AND_COMPLETE_38_CASE_"
            "PACKAGE_INTEGRITY_AND_62_CASE_SOURCE_AUTHORITY_MEMBERSHIP_OWNERSHIP_"
            "LANGUAGE_AND_51_CASE_EFFECTIVE_STATE_TRANSITION_AND_30_CASE_"
            "RECORD_BOUNDARY_DEPENDENCY_CROSS_REFERENCE_EXECUTABLE_CHECKPOINTS_"
            "AND_35_CASE_CANONICAL_RENDERING_TABLE_FEE_FORM_EXECUTABLE_"
            "AND_24_CASE_EXACT_LIMIT_OFFICIAL_PARTITION_EXECUTABLE_CHECKPOINTS_"
            "AND_20_CASE_SOURCE_UNIT_COVERAGE_BOARD_READINESS_AND_24_CASE_"
            "IDENTITY_LINEAGE_TRACEABILITY_EXECUTABLE_CHECKPOINTS_COMPLETE_"
            "CASE_UNIVERSE_ENDPOINT_"
            "REAL_SOURCE_REGISTER_ALLOCATION_"
            "SEARCH_RECORD_OR_ACTIVATION_CLAIM"
        ),
        "minimum_engine_version": "1.0.0",
        "files": files,
    }
    projection = dict(document)
    projection.pop("package_fingerprint")
    document["package_fingerprint"] = _fingerprint(rfc8785.dumps(checked_json_value(projection)))
    return document


def main() -> None:  # noqa: PLR0915
    """Write stable display bytes; authority is the canonical fingerprint."""
    fixture, expected = build_english_record_fixture()
    fixture_path = PACKAGE_ROOT / "fixtures/deterministic/HKREG-ENGLISH-RECORD-FIX-001.json"
    expected_path = PACKAGE_ROOT / "expected/english-record/HKREG-ENGLISH-RECORD-FIX-001.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    expected_path.write_text(
        json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    identity_fixture, identity_expected = build_record_identity_fixture()
    identity_fixture_path = (
        PACKAGE_ROOT / "fixtures/deterministic/HKREG-RECORD-IDENTITY-FIX-001.json"
    )
    identity_expected_path = (
        PACKAGE_ROOT / "expected/record-identity/HKREG-RECORD-IDENTITY-FIX-001.json"
    )
    identity_fixture_path.parent.mkdir(parents=True, exist_ok=True)
    identity_expected_path.parent.mkdir(parents=True, exist_ok=True)
    identity_fixture_path.write_text(
        json.dumps(identity_fixture, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    identity_expected_path.write_text(
        json.dumps(identity_expected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    package_integrity_cases = build_package_integrity_cases()
    package_fixture_root = PACKAGE_ROOT / "fixtures/conformance/package-integrity"
    package_expected_root = PACKAGE_ROOT / "expected/conformance/package-integrity"
    package_fixture_root.mkdir(parents=True, exist_ok=True)
    package_expected_root.mkdir(parents=True, exist_ok=True)
    for fixture_document, expected_document in package_integrity_cases:
        case_id = str(fixture_document["case_id"])
        (package_fixture_root / f"{case_id}.json").write_text(
            json.dumps(fixture_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (package_expected_root / f"{case_id}.json").write_text(
            json.dumps(expected_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    source_decision_cases = build_source_decision_cases()
    source_fixture_root = PACKAGE_ROOT / "fixtures/conformance/source-decision"
    source_expected_root = PACKAGE_ROOT / "expected/conformance/source-decision"
    source_fixture_root.mkdir(parents=True, exist_ok=True)
    source_expected_root.mkdir(parents=True, exist_ok=True)
    for fixture_document, expected_document in source_decision_cases:
        case_id = str(fixture_document["case_id"])
        (source_fixture_root / f"{case_id}.json").write_text(
            json.dumps(fixture_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (source_expected_root / f"{case_id}.json").write_text(
            json.dumps(expected_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    state_decision_cases = build_state_decision_cases()
    state_fixture_root = PACKAGE_ROOT / "fixtures/conformance/state-decision"
    state_expected_root = PACKAGE_ROOT / "expected/conformance/state-decision"
    state_fixture_root.mkdir(parents=True, exist_ok=True)
    state_expected_root.mkdir(parents=True, exist_ok=True)
    for fixture_document, expected_document in state_decision_cases:
        case_id = str(fixture_document["case_id"])
        (state_fixture_root / f"{case_id}.json").write_text(
            json.dumps(fixture_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (state_expected_root / f"{case_id}.json").write_text(
            json.dumps(expected_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    boundary_decision_cases = build_boundary_decision_cases()
    boundary_fixture_root = PACKAGE_ROOT / "fixtures/conformance/boundary-decision"
    boundary_expected_root = PACKAGE_ROOT / "expected/conformance/boundary-decision"
    boundary_fixture_root.mkdir(parents=True, exist_ok=True)
    boundary_expected_root.mkdir(parents=True, exist_ok=True)
    for fixture_document, expected_document in boundary_decision_cases:
        case_id = str(fixture_document["case_id"])
        (boundary_fixture_root / f"{case_id}.json").write_text(
            json.dumps(fixture_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (boundary_expected_root / f"{case_id}.json").write_text(
            json.dumps(expected_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    rendering_decision_cases = build_rendering_decision_cases()
    rendering_fixture_root = PACKAGE_ROOT / "fixtures/conformance/rendering-decision"
    rendering_expected_root = PACKAGE_ROOT / "expected/conformance/rendering-decision"
    rendering_fixture_root.mkdir(parents=True, exist_ok=True)
    rendering_expected_root.mkdir(parents=True, exist_ok=True)
    for fixture_document, expected_document in rendering_decision_cases:
        case_id = str(fixture_document["case_id"])
        (rendering_fixture_root / f"{case_id}.json").write_text(
            json.dumps(fixture_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (rendering_expected_root / f"{case_id}.json").write_text(
            json.dumps(expected_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    partition_decision_cases = build_partition_decision_cases()
    partition_fixture_root = PACKAGE_ROOT / "fixtures/conformance/partition-decision"
    partition_expected_root = PACKAGE_ROOT / "expected/conformance/partition-decision"
    partition_fixture_root.mkdir(parents=True, exist_ok=True)
    partition_expected_root.mkdir(parents=True, exist_ok=True)
    for fixture_document, expected_document in partition_decision_cases:
        case_id = str(fixture_document["case_id"])
        (partition_fixture_root / f"{case_id}.json").write_text(
            json.dumps(fixture_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (partition_expected_root / f"{case_id}.json").write_text(
            json.dumps(expected_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    coverage_decision_cases = build_coverage_decision_cases()
    coverage_fixture_root = PACKAGE_ROOT / "fixtures/conformance/coverage-decision"
    coverage_expected_root = PACKAGE_ROOT / "expected/conformance/coverage-decision"
    coverage_fixture_root.mkdir(parents=True, exist_ok=True)
    coverage_expected_root.mkdir(parents=True, exist_ok=True)
    for fixture_document, expected_document in coverage_decision_cases:
        case_id = str(fixture_document["case_id"])
        (coverage_fixture_root / f"{case_id}.json").write_text(
            json.dumps(fixture_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (coverage_expected_root / f"{case_id}.json").write_text(
            json.dumps(expected_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    identity_decision_cases = build_identity_decision_cases()
    identity_fixture_root = PACKAGE_ROOT / "fixtures/conformance/identity-decision"
    identity_expected_root = PACKAGE_ROOT / "expected/conformance/identity-decision"
    identity_fixture_root.mkdir(parents=True, exist_ok=True)
    identity_expected_root.mkdir(parents=True, exist_ok=True)
    for fixture_document, expected_document in identity_decision_cases:
        case_id = str(fixture_document["case_id"])
        (identity_fixture_root / f"{case_id}.json").write_text(
            json.dumps(fixture_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (identity_expected_root / f"{case_id}.json").write_text(
            json.dumps(expected_document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    schema_root = PACKAGE_ROOT / "contracts/schemas"
    (schema_root / "hkex-record-identity-request.schema.json").write_text(
        json.dumps(build_record_identity_request_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-record-identity-result.schema.json").write_text(
        json.dumps(build_record_identity_result_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-conformance-universe.schema.json").write_text(
        json.dumps(build_conformance_universe_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-package-integrity-case.schema.json").write_text(
        json.dumps(build_package_integrity_case_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-package-integrity-report.schema.json").write_text(
        json.dumps(build_package_integrity_report_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-package-integrity-catalogue.schema.json").write_text(
        json.dumps(build_package_integrity_catalogue_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-source-decision-case.schema.json").write_text(
        json.dumps(build_source_decision_case_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-source-decision-report.schema.json").write_text(
        json.dumps(build_source_decision_report_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-source-decision-catalogue.schema.json").write_text(
        json.dumps(build_source_decision_catalogue_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-state-decision-case.schema.json").write_text(
        json.dumps(build_state_decision_case_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-state-decision-report.schema.json").write_text(
        json.dumps(build_state_decision_report_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-state-decision-catalogue.schema.json").write_text(
        json.dumps(build_state_decision_catalogue_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-boundary-decision-case.schema.json").write_text(
        json.dumps(build_boundary_decision_case_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-boundary-decision-report.schema.json").write_text(
        json.dumps(build_boundary_decision_report_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-boundary-decision-catalogue.schema.json").write_text(
        json.dumps(build_boundary_decision_catalogue_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-rendering-decision-case.schema.json").write_text(
        json.dumps(build_rendering_decision_case_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-rendering-decision-report.schema.json").write_text(
        json.dumps(build_rendering_decision_report_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-rendering-decision-catalogue.schema.json").write_text(
        json.dumps(build_rendering_decision_catalogue_schema(), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-partition-decision-case.schema.json").write_text(
        json.dumps(build_partition_decision_case_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-partition-decision-report.schema.json").write_text(
        json.dumps(build_partition_decision_report_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-partition-decision-catalogue.schema.json").write_text(
        json.dumps(build_partition_decision_catalogue_schema(), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-coverage-decision-case.schema.json").write_text(
        json.dumps(build_coverage_decision_case_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-coverage-decision-report.schema.json").write_text(
        json.dumps(build_coverage_decision_report_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-coverage-decision-catalogue.schema.json").write_text(
        json.dumps(build_coverage_decision_catalogue_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-identity-decision-case.schema.json").write_text(
        json.dumps(build_identity_decision_case_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-identity-decision-report.schema.json").write_text(
        json.dumps(build_identity_decision_report_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (schema_root / "hkex-identity-decision-catalogue.schema.json").write_text(
        json.dumps(build_identity_decision_catalogue_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/component-continuity-fixtures.json").write_text(
        json.dumps(build_component_continuity_catalogue(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/effective-state-fixtures.json").write_text(
        json.dumps(build_effective_state_catalogue(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/english-record-fixtures.json").write_text(
        json.dumps(build_english_record_catalogue(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/record-identity-fixtures.json").write_text(
        json.dumps(build_record_identity_catalogue(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/conformance-universe.json").write_text(
        json.dumps(build_conformance_universe(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/package-integrity-cases.json").write_text(
        json.dumps(
            build_package_integrity_catalogue(package_integrity_cases),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/source-decision-cases.json").write_text(
        json.dumps(
            build_source_decision_catalogue(source_decision_cases),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/state-decision-cases.json").write_text(
        json.dumps(
            build_state_decision_catalogue(state_decision_cases),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/boundary-decision-cases.json").write_text(
        json.dumps(
            build_boundary_decision_catalogue(boundary_decision_cases),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/rendering-decision-cases.json").write_text(
        json.dumps(
            build_rendering_decision_catalogue(rendering_decision_cases),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/partition-decision-cases.json").write_text(
        json.dumps(
            build_partition_decision_catalogue(partition_decision_cases),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/coverage-decision-cases.json").write_text(
        json.dumps(
            build_coverage_decision_catalogue(coverage_decision_cases),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "catalogues/identity-decision-cases.json").write_text(
        json.dumps(
            build_identity_decision_catalogue(identity_decision_cases),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "rules/HKREG-SOURCE-DECISION-001.json").write_text(
        json.dumps(build_source_decision_rule(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "rules/HKREG-CONFORMANCE-UNIVERSE-001.json").write_text(
        json.dumps(build_conformance_universe_rule(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "rules/HKREG-STATE-DECISION-001.json").write_text(
        json.dumps(build_state_decision_rule(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "rules/HKREG-BOUNDARY-DECISION-001.json").write_text(
        json.dumps(build_boundary_decision_rule(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "rules/HKREG-RENDERING-DECISION-001.json").write_text(
        json.dumps(build_rendering_decision_rule(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "rules/HKREG-PARTITION-DECISION-001.json").write_text(
        json.dumps(build_partition_decision_rule(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "rules/HKREG-COVERAGE-DECISION-001.json").write_text(
        json.dumps(build_coverage_decision_rule(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "rules/HKREG-IDENTITY-DECISION-001.json").write_text(
        json.dumps(build_identity_decision_rule(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PACKAGE_ROOT / "package.json").write_text(
        json.dumps(build_manifest(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
