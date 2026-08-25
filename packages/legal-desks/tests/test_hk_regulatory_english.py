"""Source-neutral ADR 0073 English rendering and coverage conformance."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import NotRequired, Required, TypedDict, TypeIs, Unpack

import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue
from asklegal_legal_desks import (
    HKEX_ENGLISH_RECORD_RULE_ID,
    HKEX_MAIN_SCOPE_ID,
    HKEXBranchState,
    HKEXComponentClass,
    HKEXEnglishConstructionRequest,
    HKEXEnglishDisposition,
    HKEXEnglishError,
    HKEXEnglishErrorCode,
    HKEXEnglishReason,
    HKEXEnglishRecordUnit,
    HKEXEnglishServingProfile,
    HKEXEnglishSourceTree,
    HKEXEnglishSourceUnit,
    HKEXEnglishUnitKind,
    HKEXReferencedLocation,
    HKEXSourceContractState,
    HKEXSourceUnitRole,
    construct_hkex_english_branch,
    construct_hkex_english_request,
    hkex_english_request_from_document,
)
from jsonschema import Draft202012Validator

FINGERPRINT = f"sha256:{'a' * 64}"
PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)


class _UnitOptions(TypedDict):
    parent: Required[str | None]
    children: NotRequired[tuple[str, ...]]
    kind: NotRequired[HKEXEnglishUnitKind]
    role: NotRequired[HKEXSourceUnitRole]
    dependencies: NotRequired[tuple[str, ...]]
    meaning_bearing: NotRequired[bool]


class _RecordOptions(TypedDict, total=False):
    dependencies: tuple[str, ...]
    children: tuple[str, ...]
    references: tuple[HKEXReferencedLocation, ...]
    state: HKEXSourceContractState
    indivisible: bool


class _TreeOptions(TypedDict, total=False):
    state: HKEXBranchState
    component_class: HKEXComponentClass
    source_units: tuple[HKEXEnglishSourceUnit, ...] | None
    records: tuple[HKEXEnglishRecordUnit, ...] | None
    roots: tuple[str, ...]
    heading: str | None


class ExactCharacterCounter:
    """Pinned deterministic counter used only by source-neutral conformance."""

    profile_id = "synthetic-hkex-profile-1"
    profile_fingerprint = FINGERPRINT
    tokenizer_id = "synthetic-codepoint-counter-1"

    def count(self, text: str) -> int:
        """Count Unicode code points exactly for the frozen synthetic profile."""
        return len(text)


class FrozenFixtureCounter:
    """Counter bound to the exact explicitly non-admitted fixture profile."""

    def __init__(self, profile_id: str, profile_fingerprint: str, tokenizer_id: str) -> None:
        """Bind the three exact fixture profile identifiers."""
        self.profile_id = profile_id
        self.profile_fingerprint = profile_fingerprint
        self.tokenizer_id = tokenizer_id

    def count(self, text: str) -> int:
        """Apply the fixture's declared exact codepoint rule."""
        return len(text)


def _profile(
    *,
    max_text_tokens: int = 100_000,
    max_metadata_bytes: int = 100_000,
    authority_note: str = "None",
) -> HKEXEnglishServingProfile:
    return HKEXEnglishServingProfile(
        profile_id=ExactCharacterCounter.profile_id,
        profile_fingerprint=ExactCharacterCounter.profile_fingerprint,
        tokenizer_id=ExactCharacterCounter.tokenizer_id,
        max_text_tokens=max_text_tokens,
        max_metadata_bytes=max_metadata_bytes,
        country="Hong Kong",
        jurisdiction="Hong Kong",
        material_type="regulatory_material",
        source="Hong Kong Exchanges and Clearing Limited",
        authority_note=authority_note,
    )


def _unit(
    unit_id: str,
    order: int,
    text: str,
    **options: Unpack[_UnitOptions],
) -> HKEXEnglishSourceUnit:
    return HKEXEnglishSourceUnit(
        source_unit_id=unit_id,
        parent_source_unit_id=options["parent"],
        child_source_unit_ids=options.get("children", ()),
        source_order=order,
        kind=options.get("kind", HKEXEnglishUnitKind.BODY_TEXT),
        role=options.get("role", HKEXSourceUnitRole.PRIMARY),
        text=text,
        source_range=f"artifact#range-{order}",
        required_context_unit_ids=options.get("dependencies", ()),
        meaning_bearing=options.get("meaning_bearing", True),
        content_fingerprint=f"sha256:{sha256(text.encode()).hexdigest()}",
    )


def _record(
    record_id: str,
    primary: tuple[str, ...],
    **options: Unpack[_RecordOptions],
) -> HKEXEnglishRecordUnit:
    return HKEXEnglishRecordUnit(
        record_unit_id=record_id,
        primary_source_unit_ids=primary,
        dependency_source_unit_ids=options.get("dependencies", ()),
        referenced_locations=options.get("references", ()),
        child_record_unit_ids=options.get("children", ()),
        source_contract_state=options.get("state", HKEXSourceContractState.SUPPORTED),
        indivisible=options.get("indivisible", False),
    )


def _tree(
    **options: Unpack[_TreeOptions],
) -> HKEXEnglishSourceTree:
    state = options.get("state", HKEXBranchState.CURRENT)
    component_class = options.get("component_class", HKEXComponentClass.ORDINARY_RULE)
    source_units = options.get("source_units")
    records = options.get("records")
    roots = options.get("roots", ("record-root",))
    heading = options.get("heading", "General obligations")
    if source_units is None:
        source_units = (
            _unit(
                "context",
                0,
                "Rule 2 — General obligations",
                parent=None,
                children=("rule-a",),
                kind=HKEXEnglishUnitKind.HEADING,
                role=HKEXSourceUnitRole.CONTEXT_ONLY,
            ),
            _unit(
                "rule-a",
                1,
                "2.01 An issuer must comply with the Exchange Listing Rules.",
                parent="context",
                dependencies=("context",),
            ),
        )
    if records is None:
        records = (_record("record-root", ("rule-a",), dependencies=("context",)),)
    return HKEXEnglishSourceTree(
        tree_id="tree-main-2.01-current",
        component_id="component-main-2.01",
        scope_id=HKEX_MAIN_SCOPE_ID,
        branch_id="branch-main-2.01-current",
        branch_state=state,
        component_class=component_class,
        component_label="Main Board Listing Rules, Chapter 2",
        location_label="Rule 2.01",
        official_heading=heading,
        root_source_unit_id="context",
        source_units=source_units,
        root_record_unit_ids=roots,
        record_units=records,
        source_rule_id=HKEX_ENGLISH_RECORD_RULE_ID,
        source_artifact_fingerprints=(FINGERPRINT,),
    )


def _partition_tree(
    texts: tuple[str, ...],
    *,
    child_grandchildren: tuple[str, ...] = (),
    unknown_root: bool = False,
) -> HKEXEnglishSourceTree:
    child_ids = tuple(f"unit-{index}" for index in range(1, len(texts) + 1))
    source_units = [
        _unit(
            "context",
            0,
            "Rule 9 — Partition context",
            parent=None,
            children=child_ids,
            kind=HKEXEnglishUnitKind.HEADING,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
        )
    ]
    source_units.extend(
        _unit(
            unit_id,
            index,
            text,
            parent="context",
            dependencies=("context",),
        )
        for index, (unit_id, text) in enumerate(zip(child_ids, texts, strict=True), start=1)
    )
    child_records = tuple(
        _record(
            f"record-{unit_id}",
            (unit_id,),
            dependencies=("context",),
            children=(child_grandchildren if index == 1 else ()),
            indivisible=index != 1 or not child_grandchildren,
        )
        for index, unit_id in enumerate(child_ids, start=1)
    )
    root = _record(
        "record-root",
        child_ids,
        dependencies=("context",),
        children=tuple(item.record_unit_id for item in child_records),
        state=(
            HKEXSourceContractState.UNKNOWN if unknown_root else HKEXSourceContractState.SUPPORTED
        ),
    )
    return _tree(
        source_units=tuple(source_units),
        records=(root, *child_records),
        heading=None,
    )


def test_current_whole_rule_renders_exact_six_field_candidate_without_authority() -> None:
    result = construct_hkex_english_branch(
        _tree(), _profile(), ExactCharacterCounter(), effective_context=None
    )

    assert result.disposition is HKEXEnglishDisposition.PASS
    assert result.reason is HKEXEnglishReason.PASS_UNSPLIT
    assert result.primary_source_unit_ids == ("rule-a",)
    assert result.context_only_source_unit_ids == ("context",)
    assert result.presentation_only_source_unit_ids == ()
    assert result.primary_accounting_complete
    assert result.serving_candidate_ready
    assert not result.search_record_authorized
    assert not result.serving_ready
    part = result.record_results[0].parts[0]
    assert part.text == (
        "Context:\n"
        "Material: HKEX Listing Rule — non-statutory exchange regulatory rule\n"
        "Market: Main Board\n"
        "Component: Main Board Listing Rules, Chapter 2\n"
        "Location: Rule 2.01\n"
        "Official heading: General obligations\n\n"
        "Required governing context:\n"
        "Rule 2 — General obligations\n\n"
        "English rule text — prevailing language:\n"
        "2.01 An issuer must comply with the Exchange Listing Rules."
    )
    assert "authority_note" not in part.text
    assert part.measurement.text_tokens == len(part.text)
    assert part.measurement.fits


def test_transitional_context_is_required_but_ordinary_current_forbids_it() -> None:
    transitional = construct_hkex_english_branch(
        _tree(state=HKEXBranchState.TRANSITIONAL_CURRENT),
        _profile(),
        ExactCharacterCounter(),
        effective_context="Applies to issuers admitted before 1 January 2026",
    )

    assert "Effective context: Applies to issuers admitted before 1 January 2026" in (
        transitional.record_results[0].parts[0].text
    )
    with pytest.raises(HKEXEnglishError) as missing:
        construct_hkex_english_branch(
            _tree(state=HKEXBranchState.TRANSITIONAL_CURRENT),
            _profile(),
            ExactCharacterCounter(),
            effective_context=None,
        )
    assert missing.value.code is HKEXEnglishErrorCode.CONTRACT
    with pytest.raises(HKEXEnglishError):
        construct_hkex_english_branch(
            _tree(),
            _profile(),
            ExactCharacterCounter(),
            effective_context="generic current prose",
        )


@pytest.mark.parametrize(
    ("state", "disposition", "reason"),
    [
        (
            HKEXBranchState.FUTURE_FIXED_DATE,
            HKEXEnglishDisposition.WAITING_ROOM,
            HKEXEnglishReason.FUTURE_BRANCH_ACCOUNTED,
        ),
        (
            HKEXBranchState.FUTURE_CONDITIONAL,
            HKEXEnglishDisposition.WAITING_ROOM,
            HKEXEnglishReason.FUTURE_BRANCH_ACCOUNTED,
        ),
        (
            HKEXBranchState.SUPERSEDED,
            HKEXEnglishDisposition.HISTORICAL,
            HKEXEnglishReason.HISTORICAL_BRANCH_ACCOUNTED,
        ),
        (
            HKEXBranchState.WITHDRAWN,
            HKEXEnglishDisposition.HISTORICAL,
            HKEXEnglishReason.HISTORICAL_BRANCH_ACCOUNTED,
        ),
        (
            HKEXBranchState.UNKNOWN,
            HKEXEnglishDisposition.QUARANTINE,
            HKEXEnglishReason.UNKNOWN_BRANCH_QUARANTINED,
        ),
    ],
)
def test_noncurrent_branches_are_completely_accounted_without_rendering(
    state: HKEXBranchState,
    disposition: HKEXEnglishDisposition,
    reason: HKEXEnglishReason,
) -> None:
    result = construct_hkex_english_branch(
        _tree(state=state), _profile(), ExactCharacterCounter(), effective_context=None
    )

    assert result.disposition is disposition
    assert result.reason is reason
    assert result.record_results == ()
    assert result.primary_accounting_complete
    assert not result.serving_candidate_ready


def test_unknown_source_boundary_quarantines_even_when_unsplit_payload_fits() -> None:
    result = construct_hkex_english_branch(
        _partition_tree(("9.01 Complete short rule.",), unknown_root=True),
        _profile(),
        ExactCharacterCounter(),
        effective_context=None,
    )

    assert result.disposition is HKEXEnglishDisposition.QUARANTINE
    assert result.reason is HKEXEnglishReason.SOURCE_BOUNDARY_UNKNOWN
    assert result.record_results[0].parts == ()
    assert not result.serving_candidate_ready


def test_required_context_is_transitively_closed_and_helpful_overlap_is_rejected() -> None:
    source_units = (
        _unit(
            "context",
            0,
            "Rule 3 — Scope",
            parent=None,
            children=("local-scope", "rule-a", "background"),
            kind=HKEXEnglishUnitKind.HEADING,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
        ),
        _unit(
            "local-scope",
            1,
            "This rule applies to new applicants.",
            parent="context",
            kind=HKEXEnglishUnitKind.SCOPE_TEXT,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
            dependencies=("context",),
        ),
        _unit(
            "rule-a",
            2,
            "3.01 A new applicant must provide the declaration.",
            parent="context",
            dependencies=("local-scope",),
        ),
        _unit(
            "background",
            3,
            "Helpful but non-governing background.",
            parent="context",
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
        ),
    )
    valid = _tree(
        source_units=source_units,
        records=(
            _record(
                "record-root",
                ("rule-a",),
                dependencies=("context", "local-scope"),
            ),
        ),
    )
    rendered = (
        construct_hkex_english_branch(
            valid, _profile(), ExactCharacterCounter(), effective_context=None
        )
        .record_results[0]
        .parts[0]
        .text
    )

    assert "Rule 3 — Scope\nThis rule applies to new applicants." in rendered
    assert "Helpful but non-governing background" not in rendered
    with pytest.raises(HKEXEnglishError) as extra:
        _tree(
            source_units=source_units,
            records=(
                _record(
                    "record-root",
                    ("rule-a",),
                    dependencies=("context", "local-scope", "background"),
                ),
            ),
        )
    assert extra.value.code is HKEXEnglishErrorCode.COVERAGE


def test_cross_reference_renders_locator_and_heading_without_target_text() -> None:
    reference = HKEXReferencedLocation("Rule 10.01", "Definitions")
    tree = _tree(
        records=(
            _record(
                "record-root",
                ("rule-a",),
                dependencies=("context",),
                references=(reference,),
            ),
        )
    )
    text = (
        construct_hkex_english_branch(
            tree, _profile(), ExactCharacterCounter(), effective_context=None
        )
        .record_results[0]
        .parts[0]
        .text
    )

    assert "Referenced locations:\n- Rule 10.01 — Definitions" in text
    assert "target rule text" not in text


def test_table_requires_complete_header_and_row_dependency_closure() -> None:
    sources = (
        _unit(
            "context",
            0,
            "Table 1",
            parent=None,
            children=("header", "row"),
            kind=HKEXEnglishUnitKind.TABLE_CAPTION,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
        ),
        _unit(
            "header",
            1,
            "Category | Minimum amount",
            parent="context",
            kind=HKEXEnglishUnitKind.TABLE_HEADER,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
            dependencies=("context",),
        ),
        _unit(
            "row",
            2,
            "Category A | HK$1,000,000",
            parent="context",
            kind=HKEXEnglishUnitKind.TABLE_ROW,
            dependencies=("header",),
        ),
    )
    valid = _tree(
        component_class=HKEXComponentClass.TABLE,
        source_units=sources,
        records=(
            _record(
                "record-root",
                ("row",),
                dependencies=("context", "header"),
            ),
        ),
    )
    assert construct_hkex_english_branch(
        valid, _profile(), ExactCharacterCounter(), effective_context=None
    ).serving_candidate_ready
    with pytest.raises(HKEXEnglishError):
        _tree(
            component_class=HKEXComponentClass.TABLE,
            source_units=sources,
            records=(
                _record(
                    "record-root",
                    ("row",),
                    dependencies=("context",),
                ),
            ),
        )


def test_fee_record_requires_category_amount_basis_and_timing() -> None:
    kinds = (
        HKEXEnglishUnitKind.FEE_CATEGORY,
        HKEXEnglishUnitKind.FEE_AMOUNT,
        HKEXEnglishUnitKind.FEE_BASIS,
        HKEXEnglishUnitKind.FEE_TIMING,
    )
    ids = ("category", "amount", "basis", "timing")
    sources = (
        _unit(
            "context",
            0,
            "Fees Rule 1",
            parent=None,
            children=ids,
            kind=HKEXEnglishUnitKind.HEADING,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
        ),
        *(
            _unit(
                unit_id,
                index,
                text,
                parent="context",
                kind=kind,
                dependencies=("context",) if index == 1 else (),
            )
            for index, (unit_id, kind, text) in enumerate(
                zip(
                    ids,
                    kinds,
                    ("New listing", "HK$100,000", "per application", "on submission"),
                    strict=True,
                ),
                start=1,
            )
        ),
    )
    valid = _tree(
        component_class=HKEXComponentClass.FEES_RULE,
        source_units=sources,
        records=(_record("record-root", ids, dependencies=("context",)),),
    )

    assert construct_hkex_english_branch(
        valid, _profile(), ExactCharacterCounter(), effective_context=None
    ).serving_candidate_ready
    with pytest.raises(HKEXEnglishError):
        _tree(
            component_class=HKEXComponentClass.FEES_RULE,
            source_units=sources,
            records=(_record("record-root", ids[:-1], dependencies=("context",)),),
        )


def test_form_uses_closed_markers_and_never_creates_one_record_per_blank() -> None:
    sources = (
        _unit(
            "context",
            0,
            "Form A — Declaration",
            parent=None,
            children=("instruction", "label", "blank", "signature"),
            kind=HKEXEnglishUnitKind.HEADING,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
        ),
        _unit(
            "instruction",
            1,
            "Complete this declaration in full.",
            parent="context",
            kind=HKEXEnglishUnitKind.FORM_INSTRUCTION,
            dependencies=("context",),
        ),
        _unit(
            "label",
            2,
            "Name of issuer:",
            parent="context",
            kind=HKEXEnglishUnitKind.FORM_LABEL,
        ),
        _unit(
            "blank",
            3,
            "[BLANK FIELD]",
            parent="context",
            kind=HKEXEnglishUnitKind.FORM_CONTROL,
        ),
        _unit(
            "signature",
            4,
            "[SIGNATURE]",
            parent="context",
            kind=HKEXEnglishUnitKind.FORM_CONTROL,
        ),
    )
    valid = _tree(
        component_class=HKEXComponentClass.REGULATORY_FORM,
        source_units=sources,
        records=(
            _record(
                "record-root",
                ("instruction", "label", "blank", "signature"),
                dependencies=("context",),
                indivisible=True,
            ),
        ),
    )
    text = (
        construct_hkex_english_branch(
            valid, _profile(), ExactCharacterCounter(), effective_context=None
        )
        .record_results[0]
        .parts[0]
        .text
    )

    assert "[BLANK FIELD]" in text
    assert "[SIGNATURE]" in text
    with pytest.raises(HKEXEnglishError) as invented:
        _unit(
            "completed-value",
            1,
            "Ask Legal Limited",
            parent=None,
            kind=HKEXEnglishUnitKind.FORM_CONTROL,
        )
    assert invented.value.code is HKEXEnglishErrorCode.CONTRACT


def test_presentation_only_change_does_not_change_canonical_serving_payload() -> None:
    base = _tree()
    presentation = _unit(
        "page-furniture",
        2,
        "Page 1 of 10",
        parent="context",
        kind=HKEXEnglishUnitKind.PRESENTATION,
        role=HKEXSourceUnitRole.PRESENTATION_ONLY,
        meaning_bearing=False,
    )
    changed_root = replace(
        base.source_units[0],
        child_source_unit_ids=("rule-a", "page-furniture"),
    )
    with_presentation = replace(
        base,
        source_units=(changed_root, base.source_units[1], presentation),
    )
    changed_presentation = replace(
        presentation,
        text="Page 2 of 10",
        content_fingerprint=f"sha256:{sha256(b'Page 2 of 10').hexdigest()}",
    )
    reflowed = replace(
        with_presentation,
        source_units=(changed_root, base.source_units[1], changed_presentation),
    )

    first = construct_hkex_english_branch(
        with_presentation, _profile(), ExactCharacterCounter(), effective_context=None
    )
    second = construct_hkex_english_branch(
        reflowed, _profile(), ExactCharacterCounter(), effective_context=None
    )
    assert first.record_results[0].parts[0].serving_payload_fingerprint == (
        second.record_results[0].parts[0].serving_payload_fingerprint
    )
    assert first.tree_fingerprint != second.tree_fingerprint
    assert first.presentation_only_source_unit_ids == ("page-furniture",)


def test_graph_rejects_reordered_primary_ownership_or_shared_child() -> None:
    tree = _partition_tree(("9.01 First.", "9.02 Second."))
    root = tree.record_units[0]
    with pytest.raises(HKEXEnglishError) as reordered:
        replace(
            tree,
            record_units=(
                replace(root, primary_source_unit_ids=("unit-2", "unit-1")),
                *tree.record_units[1:],
            ),
        )
    assert reordered.value.code is HKEXEnglishErrorCode.COVERAGE

    child_one = tree.record_units[1]
    child_two = tree.record_units[2]
    with pytest.raises(HKEXEnglishError) as shared:
        replace(
            tree,
            record_units=(
                root,
                replace(child_one, child_record_unit_ids=("record-unit-2",), indivisible=False),
                child_two,
            ),
        )
    assert shared.value.code is HKEXEnglishErrorCode.STRUCTURE


def test_distinct_normal_roots_are_never_packed_together() -> None:
    source_units = (
        _unit(
            "context",
            0,
            "Chapter 11",
            parent=None,
            children=("rule-a", "rule-b"),
            kind=HKEXEnglishUnitKind.HEADING,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
        ),
        _unit("rule-a", 1, "11.01 First independent rule.", parent="context"),
        _unit("rule-b", 2, "11.02 Second independent rule.", parent="context"),
    )
    tree = _tree(
        source_units=source_units,
        records=(
            _record("record-a", ("rule-a",), indivisible=True),
            _record("record-b", ("rule-b",), indivisible=True),
        ),
        roots=("record-a", "record-b"),
    )
    result = construct_hkex_english_branch(
        tree, _profile(), ExactCharacterCounter(), effective_context=None
    )

    assert len(result.record_results) == 2
    assert tuple(item.root_record_unit_id for item in result.record_results) == (
        "record-a",
        "record-b",
    )
    assert all(len(item.parts) == 1 for item in result.record_results)


def test_recursive_partition_uses_minimum_parts_and_earliest_full_order() -> None:
    tree = _partition_tree(
        (
            "9.01 " + "A" * 80,
            "9.02 " + "B" * 80,
            "9.03 " + "C" * 80,
        )
    )
    unsplit = (
        construct_hkex_english_branch(
            tree, _profile(), ExactCharacterCounter(), effective_context=None
        )
        .record_results[0]
        .parts[0]
    )
    child_one = (
        construct_hkex_english_branch(
            _partition_tree(("9.01 " + "A" * 80,)),
            _profile(),
            ExactCharacterCounter(),
            effective_context=None,
        )
        .record_results[0]
        .parts[0]
    )
    limit = child_one.measurement.text_tokens + 120
    assert limit < unsplit.measurement.text_tokens

    result = construct_hkex_english_branch(
        tree,
        _profile(max_text_tokens=limit),
        ExactCharacterCounter(),
        effective_context=None,
    )

    assert result.reason is HKEXEnglishReason.PASS_PARTITIONED
    parts = result.record_results[0].parts
    assert len(parts) == 2
    assert parts[0].record_unit_ids == ("record-unit-1", "record-unit-2")
    assert parts[1].record_unit_ids == ("record-unit-3",)
    assert "Serving part: 1 of 2" in parts[0].text
    assert all(part.measurement.fits for part in parts)


def test_token_only_and_metadata_only_overflow_reach_same_official_partition() -> None:
    tree = _partition_tree(("9.01 " + "A" * 100, "9.02 " + "B" * 100))
    large = (
        construct_hkex_english_branch(
            tree, _profile(), ExactCharacterCounter(), effective_context=None
        )
        .record_results[0]
        .parts[0]
    )
    token_result = construct_hkex_english_branch(
        tree,
        _profile(max_text_tokens=large.measurement.text_tokens - 1),
        ExactCharacterCounter(),
        effective_context=None,
    )
    metadata_result = construct_hkex_english_branch(
        tree,
        _profile(max_metadata_bytes=large.measurement.metadata_bytes - 1),
        ExactCharacterCounter(),
        effective_context=None,
    )

    assert token_result.reason is HKEXEnglishReason.PASS_PARTITIONED
    assert metadata_result.reason is HKEXEnglishReason.PASS_PARTITIONED
    assert tuple(part.primary_source_unit_ids for part in token_result.record_results[0].parts) == (
        ("unit-1",),
        ("unit-2",),
    )
    assert tuple(
        part.primary_source_unit_ids for part in metadata_result.record_results[0].parts
    ) == (("unit-1",), ("unit-2",))


def test_indivisible_overlong_and_fixed_metadata_overflow_quarantine() -> None:
    indivisible = _partition_tree(("9.01 " + "A" * 500,))
    result = construct_hkex_english_branch(
        indivisible,
        _profile(max_text_tokens=100),
        ExactCharacterCounter(),
        effective_context=None,
    )
    fixed = construct_hkex_english_branch(
        _partition_tree(("9.01 A", "9.02 B")),
        _profile(max_metadata_bytes=1, authority_note="Mandatory authority note"),
        ExactCharacterCounter(),
        effective_context=None,
    )

    assert result.reason is HKEXEnglishReason.SMALLEST_COMPLETE_UNIT_OVER_LIMIT
    assert result.record_results[0].parts == ()
    assert fixed.reason is HKEXEnglishReason.SMALLEST_COMPLETE_UNIT_OVER_LIMIT
    assert not fixed.serving_candidate_ready


def test_counter_profile_drift_and_noncanonical_source_text_fail_closed() -> None:
    class WrongCounter(ExactCharacterCounter):
        tokenizer_id = "different-tokenizer"

    with pytest.raises(HKEXEnglishError):
        construct_hkex_english_branch(_tree(), _profile(), WrongCounter(), effective_context=None)
    with pytest.raises(HKEXEnglishError) as whitespace:
        _unit("bad", 0, "trailing space ", parent=None)
    assert whitespace.value.code is HKEXEnglishErrorCode.CONTRACT


def test_clean_construction_is_byte_and_fingerprint_reproducible() -> None:
    first = construct_hkex_english_branch(
        _tree(), _profile(), ExactCharacterCounter(), effective_context=None
    )
    second = construct_hkex_english_branch(
        _tree(), _profile(), ExactCharacterCounter(), effective_context=None
    )

    assert first == second
    assert first.tree_fingerprint == second.tree_fingerprint
    assert first.record_results[0].parts[0].text_fingerprint == (
        second.record_results[0].parts[0].text_fingerprint
    )


def test_strict_request_round_trip_and_result_projection_reject_contract_drift() -> None:
    request = HKEXEnglishConstructionRequest(_tree(), _profile(), None)
    document = request.document()
    parsed = hkex_english_request_from_document(document)
    result = construct_hkex_english_request(parsed, ExactCharacterCounter())
    projected = result.document(case_id="HKREG-ENGLISH-DIRECT-001")

    assert parsed == request
    assert projected["case_id"] == "HKREG-ENGLISH-DIRECT-001"
    assert projected["rule_id"] == HKEX_ENGLISH_RECORD_RULE_ID
    assert projected["search_record_authorized"] is False
    assert projected["serving_ready"] is False
    with pytest.raises(HKEXEnglishError):
        hkex_english_request_from_document({**document, "extra": "forbidden"})
    tree_value = document["tree"]
    assert _is_object_dict(tree_value)
    tree: dict[str, object] = {}
    for key, value in tree_value.items():
        assert isinstance(key, str)
        tree[key] = value
    tree["component_class"] = "MODEL_SUMMARY"
    with pytest.raises(HKEXEnglishError):
        hkex_english_request_from_document({**document, "tree": tree})


def test_frozen_english_record_fixture_reproduces_all_exact_results() -> None:
    fixture = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "fixtures/deterministic/HKREG-ENGLISH-RECORD-FIX-001.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    expected = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "expected/english-record/HKREG-ENGLISH-RECORD-FIX-001.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    request_schema = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "contracts/schemas/hkex-english-record-request.schema.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    result_schema = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "contracts/schemas/hkex-english-record-result.schema.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator.check_schema(result_schema)
    tokenizer = _json_object(fixture["synthetic_tokenizer"])
    assert tokenizer["admitted_for_real_records"] is False
    counter = FrozenFixtureCounter(
        _json_text(tokenizer["profile_id"]),
        _json_text(tokenizer["profile_fingerprint"]),
        _json_text(tokenizer["tokenizer_id"]),
    )
    fixture_cases = _json_array(fixture["cases"])
    expected_cases = _json_array(expected["cases"])
    assert len(fixture_cases) == 8
    actual: list[dict[str, object]] = []
    for raw_case in fixture_cases:
        case = _json_object(raw_case)
        request_document = _json_object(case["request"])
        result_document = construct_hkex_english_request(
            hkex_english_request_from_document(request_document), counter
        ).document(case_id=_json_text(case["case_id"]))
        actual.append(result_document)

    assert actual == [_json_object(item) for item in expected_cases]


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    result: dict[str, JsonValue] = {}
    for key, item in value.items():
        assert isinstance(key, str)
        result[key] = item
    return result


def _json_array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _json_text(value: JsonValue) -> str:
    assert isinstance(value, str)
    assert value
    return value


def _is_object_dict(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)
