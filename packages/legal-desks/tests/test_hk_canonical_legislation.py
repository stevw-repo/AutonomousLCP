"""Conformance checks for the source-neutral Hong Kong canonical tree."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from asklegal_contracts import SchemaRegistry, canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_legal_desks.hk_canonical_legislation import (
    BILINGUAL_ALIGNMENT_MAP_SCHEMA,
    CANONICAL_TREE_CONTRACT_VERSION,
    BilingualAlignmentMap,
    CanonicalLanguageTree,
    canonical_language_tree_fingerprint,
    parse_bilingual_alignment_map,
    parse_canonical_language_tree,
    render_canonical_bilingual_location,
    seal_canonical_language_tree,
)
from asklegal_legal_desks.hk_legislation_partition import (
    AlignedPartitionNode,
    BilingualPartitionBatchExecution,
    BilingualPartitionExecution,
    BilingualPartitionRequest,
    BilingualPartitionResult,
    PartitionDisposition,
    PartitionReason,
    PartitionServingProfile,
    partition_canonical_bilingual_location,
    partition_canonical_bilingual_locations,
    partition_serving_profile_fingerprint,
)
from asklegal_legal_desks.hk_partition_release_consequence import (
    PartitionReleaseChoice,
    PartitionReleaseConsequenceRequest,
    decide_partition_failure_release,
)
from asklegal_legal_desks.model import RulebookError

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = (
    REPOSITORY_ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package"
)


def _json(value: object) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    assert isinstance(parsed, dict)
    return parsed


def _array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _ref(ref_type: str, ref_id: str, fingerprint: str = SHA_A) -> dict[str, JsonValue]:
    return _json({"ref_type": ref_type, "ref_id": ref_id, "fingerprint": fingerprint})


def _unit(
    identity: tuple[str, str],
    location: dict[str, JsonValue],
    text: tuple[str, str],
    order: int,
) -> dict[str, JsonValue]:
    unit_id, node_id = identity
    kind, content = text
    return _json(
        {
            "source_unit_id": unit_id,
            "tree_node_id": node_id,
            "legal_location_ref": location,
            "unit_kind": kind,
            "content": content,
            "asset_ref": None,
            "source_order": order,
        }
    )


def _node(
    identity: tuple[str, dict[str, JsonValue]],
    structure: tuple[str, str | None],
    order: int,
    ownership: tuple[list[str], list[str]],
) -> dict[str, JsonValue]:
    node_id, location = identity
    structural_type, parent = structure
    units, children = ownership
    return _json(
        {
            "tree_node_id": node_id,
            "legal_location_ref": location,
            "structural_type": structural_type,
            "parent_node_id": parent,
            "sibling_order": order,
            "owned_source_unit_ids": units,
            "child_node_ids": children,
        }
    )


def _tree(
    language: str,
    *,
    unsupported: bool = False,
    body_multiplier: int = 1,
    third_paragraph: bool = False,
    statutory_note: bool = False,
) -> CanonicalLanguageTree:
    item = _ref("LEGAL_ITEM", "li_sample", SHA_A)
    instrument = _ref("LEGAL_LOCATION", "ll_instrument", SHA_B)
    provision = _ref("LEGAL_LOCATION", "ll_section_2", SHA_C)
    prefix = "en" if language == "en" else "zh"
    title = "Sample Ordinance" if language == "en" else "示例條例"
    citation = "Cap. 999" if language == "en" else "第999章"
    locator = "section 2" if language == "en" else "第2條"
    heading = "Application" if language == "en" else "適用範圍"
    first = (
        "(1) This Ordinance applies to every specified person."
        if language == "en"
        else "(1) 本條例適用於每名指明人士。"
    )
    second = (
        "(2) A person must keep the record." if language == "en" else "(2) 任何人須備存該紀錄。"
    )
    third = (
        "(3) The record must remain available."
        if language == "en"
        else "(3) 該紀錄須保持可供查閱。"
    )
    first = " ".join(first for _index in range(body_multiplier))
    second = " ".join(second for _index in range(body_multiplier))
    third = " ".join(third for _index in range(body_multiplier))
    root_id = f"{prefix}_instrument"
    provision_id = f"{prefix}_section_2"
    paragraph_1_id = f"{prefix}_paragraph_1"
    paragraph_2_id = f"{prefix}_paragraph_2"
    paragraph_3_id = f"{prefix}_paragraph_3"
    note_1_id = f"{prefix}_note_1"
    units = [
        _unit((f"{prefix}_title", root_id), instrument, ("INSTRUMENT_TITLE", title), 0),
        _unit(
            (f"{prefix}_citation", root_id),
            instrument,
            ("INSTRUMENT_CITATION", citation),
            1,
        ),
        _unit(
            (f"{prefix}_locator", provision_id),
            provision,
            ("LOCATION_LOCATOR", locator),
            0,
        ),
        _unit(
            (f"{prefix}_heading", provision_id),
            provision,
            ("LOCATION_HEADING", heading),
            1,
        ),
        _unit((f"{prefix}_body_1", paragraph_1_id), provision, ("BODY_TEXT", first), 0),
        _unit((f"{prefix}_body_2", paragraph_2_id), provision, ("BODY_TEXT", second), 0),
    ]
    if third_paragraph:
        units.append(
            _unit((f"{prefix}_body_3", paragraph_3_id), provision, ("BODY_TEXT", third), 0)
        )
    if statutory_note:
        note_marker = "*" if language == "en" else "※"
        note_body = (
            "* Statutory note attached to paragraph (1)."
            if language == "en"
            else "※ 附於第(1)款的法定註釋。"
        )
        units.insert(
            5,
            _unit(
                (f"{prefix}_note_marker_1", note_1_id),
                provision,
                ("STRUCTURAL_LABEL", note_marker),
                0,
            ),
        )
        units.insert(
            6,
            _unit(
                (f"{prefix}_note_body_1", note_1_id),
                provision,
                ("NOTE_TEXT", note_body),
                1,
            ),
        )
    paragraph_ids = [paragraph_1_id, paragraph_2_id]
    if third_paragraph:
        paragraph_ids.append(paragraph_3_id)
    nodes = [
        _node(
            (root_id, instrument),
            ("INSTRUMENT", None),
            0,
            ([f"{prefix}_title", f"{prefix}_citation"], [provision_id]),
        ),
        _node(
            (provision_id, provision),
            ("TABLE" if unsupported else "PROVISION", root_id),
            0,
            (
                [f"{prefix}_locator", f"{prefix}_heading"],
                paragraph_ids,
            ),
        ),
        _node(
            (paragraph_1_id, provision),
            ("PARAGRAPH", provision_id),
            0,
            ([f"{prefix}_body_1"], [note_1_id] if statutory_note else []),
        ),
        _node(
            (paragraph_2_id, provision),
            ("PARAGRAPH", provision_id),
            1,
            ([f"{prefix}_body_2"], []),
        ),
    ]
    if statutory_note:
        nodes.insert(
            3,
            _node(
                (note_1_id, provision),
                ("NOTE", paragraph_1_id),
                0,
                ([f"{prefix}_note_marker_1", f"{prefix}_note_body_1"], []),
            ),
        )
    if third_paragraph:
        nodes.append(
            _node(
                (paragraph_3_id, provision),
                ("PARAGRAPH", provision_id),
                2,
                ([f"{prefix}_body_3"], []),
            )
        )
    return seal_canonical_language_tree(
        _json(
            {
                "source_format": "SYNTHETIC_CANONICAL_INPUT",
                "language": language,
                "legal_item_ref": item,
                "root_node_id": root_id,
                "nodes": nodes,
                "source_units": units,
            }
        )
    )


def _relocated_tree(
    tree: CanonicalLanguageTree,
    location_ref: dict[str, JsonValue],
) -> CanonicalLanguageTree:
    document = tree.document()
    draft = _json(
        {
            "source_format": document["source_format"],
            "language": document["language"],
            "legal_item_ref": document["legal_item_ref"],
            "root_node_id": document["root_node_id"],
            "nodes": [
                {
                    key: value
                    for key, value in _object(node).items()
                    if key
                    not in {
                        "language",
                        "legal_item_ref",
                        "node_content_fingerprint",
                        "subtree_fingerprint",
                    }
                }
                for node in _array(document["nodes"])
            ],
            "source_units": [
                {
                    key: value
                    for key, value in _object(unit).items()
                    if key not in {"language", "legal_item_ref", "content_fingerprint"}
                }
                for unit in _array(document["source_units"])
            ],
        }
    )
    for member_name in ("nodes", "source_units"):
        for member in _array(draft[member_name]):
            member_object = _object(member)
            current = _object(member_object["legal_location_ref"])
            if current["ref_id"] == "ll_section_2":
                member_object["legal_location_ref"] = location_ref
    return seal_canonical_language_tree(draft)


def _alignment(
    en_tree: CanonicalLanguageTree,
    zh_tree: CanonicalLanguageTree,
    *,
    combined_body: bool = True,
) -> BilingualAlignmentMap:
    instrument = next(
        unit.legal_location_ref
        for unit in en_tree.source_units
        if unit.unit_kind == "INSTRUMENT_TITLE"
    )
    provision = next(
        unit.legal_location_ref
        for unit in en_tree.source_units
        if unit.unit_kind == "LOCATION_LOCATOR"
    )
    evidence = _ref("BILINGUAL_MAPPING_EVIDENCE", "map_sample", SHA_A)
    has_third = any(unit.source_unit_id == "en_body_3" for unit in en_tree.source_units)
    has_note = any(unit.source_unit_id == "en_note_body_1" for unit in en_tree.source_units)
    groups = [
        {
            "alignment_group_id": "align_title",
            "legal_location_ref": instrument,
            "en_source_unit_ids": ["en_title"],
            "zh_hant_source_unit_ids": ["zh_title"],
            "mapping_evidence_ref": evidence,
        },
        {
            "alignment_group_id": "align_citation",
            "legal_location_ref": instrument,
            "en_source_unit_ids": ["en_citation"],
            "zh_hant_source_unit_ids": ["zh_citation"],
            "mapping_evidence_ref": evidence,
        },
        {
            "alignment_group_id": "align_locator",
            "legal_location_ref": provision,
            "en_source_unit_ids": ["en_locator"],
            "zh_hant_source_unit_ids": ["zh_locator"],
            "mapping_evidence_ref": evidence,
        },
        {
            "alignment_group_id": "align_heading",
            "legal_location_ref": provision,
            "en_source_unit_ids": ["en_heading"],
            "zh_hant_source_unit_ids": ["zh_heading"],
            "mapping_evidence_ref": evidence,
        },
    ]
    if combined_body:
        en_body_ids = ["en_body_1", "en_body_2"]
        zh_body_ids = ["zh_body_1", "zh_body_2"]
        if has_note:
            en_body_ids[1:1] = ["en_note_marker_1", "en_note_body_1"]
            zh_body_ids[1:1] = ["zh_note_marker_1", "zh_note_body_1"]
        if has_third:
            en_body_ids.append("en_body_3")
            zh_body_ids.append("zh_body_3")
        groups.append(
            {
                "alignment_group_id": "align_body_many_many",
                "legal_location_ref": provision,
                "en_source_unit_ids": en_body_ids,
                "zh_hant_source_unit_ids": zh_body_ids,
                "mapping_evidence_ref": evidence,
            }
        )
    else:
        groups.extend(
            [
                {
                    "alignment_group_id": "align_body_1",
                    "legal_location_ref": provision,
                    "en_source_unit_ids": ["en_body_1"],
                    "zh_hant_source_unit_ids": ["zh_body_1"],
                    "mapping_evidence_ref": evidence,
                },
                {
                    "alignment_group_id": "align_body_2",
                    "legal_location_ref": provision,
                    "en_source_unit_ids": ["en_body_2"],
                    "zh_hant_source_unit_ids": ["zh_body_2"],
                    "mapping_evidence_ref": evidence,
                },
            ]
        )
        if has_third:
            groups.append(
                {
                    "alignment_group_id": "align_body_3",
                    "legal_location_ref": provision,
                    "en_source_unit_ids": ["en_body_3"],
                    "zh_hant_source_unit_ids": ["zh_body_3"],
                    "mapping_evidence_ref": evidence,
                }
            )
    if has_note and not combined_body:
        groups.insert(
            5,
            {
                "alignment_group_id": "align_note_1",
                "legal_location_ref": provision,
                "en_source_unit_ids": ["en_note_marker_1", "en_note_body_1"],
                "zh_hant_source_unit_ids": ["zh_note_marker_1", "zh_note_body_1"],
                "mapping_evidence_ref": evidence,
            },
        )
    return parse_bilingual_alignment_map(
        _json(
            {
                "$schema": BILINGUAL_ALIGNMENT_MAP_SCHEMA,
                "contract_version": CANONICAL_TREE_CONTRACT_VERSION,
                "legal_item_ref": en_tree.legal_item_ref,
                "groups": groups,
            }
        ),
        en_tree=en_tree,
        zh_hant_tree=zh_tree,
    )


def test_ordinary_bilingual_location_renders_exact_accepted_bytes() -> None:
    en_tree = _tree("en")
    zh_tree = _tree("zh-Hant")
    alignment = _alignment(en_tree, zh_tree)

    result = render_canonical_bilingual_location(
        en_tree=en_tree,
        zh_hant_tree=zh_tree,
        alignment_map=alignment,
        legal_location_ref=_ref("LEGAL_LOCATION", "ll_section_2", SHA_C),
    )

    assert result.text == (
        "[English — Authentic Text]\n"
        "Instrument: Sample Ordinance (Cap. 999)\n"
        "Provision: section 2\n"
        "Heading: Application\n"
        "Text:\n"
        "(1) This Ordinance applies to every specified person.\n"
        "(2) A person must keep the record.\n\n"
        "[繁體中文 — 真確文本]\n"
        "法例\uff1a示例條例\uff08第999章\uff09\n"
        "條文\uff1a第2條\n"
        "標題\uff1a適用範圍\n"
        "正文\uff1a\n"
        "(1) 本條例適用於每名指明人士。\n"
        "(2) 任何人須備存該紀錄。"
    )
    assert result.utf8_bytes == result.text.encode("utf-8")
    assert result.document()["search_record_output"] == "NONE"
    assert result.document()["external_effects"] == "NONE"


def test_tree_round_trip_and_render_are_byte_reproducible() -> None:
    en_tree = _tree("en")
    zh_tree = _tree("zh-Hant")
    parsed_en = parse_canonical_language_tree(en_tree.document())
    parsed_zh = parse_canonical_language_tree(zh_tree.document())
    first_map = _alignment(parsed_en, parsed_zh)
    second_map = _alignment(parsed_en, parsed_zh)
    location = _ref("LEGAL_LOCATION", "ll_section_2", SHA_C)

    first = render_canonical_bilingual_location(
        en_tree=parsed_en,
        zh_hant_tree=parsed_zh,
        alignment_map=first_map,
        legal_location_ref=location,
    )
    second = render_canonical_bilingual_location(
        en_tree=parsed_en,
        zh_hant_tree=parsed_zh,
        alignment_map=second_map,
        legal_location_ref=location,
    )

    assert canonicalize(checked_json_value(first.document())) == canonicalize(
        checked_json_value(second.document())
    )
    assert canonical_language_tree_fingerprint(en_tree.document()) == en_tree.fingerprint


def test_package_schemas_accept_the_exact_runtime_documents() -> None:
    en_tree = _tree("en")
    zh_tree = _tree("zh-Hant")
    alignment = _alignment(en_tree, zh_tree)
    registry = SchemaRegistry.from_contracts_root(PACKAGE_ROOT / "contracts")

    registry.validate(en_tree.document(), "schemas/canonical-language-tree.schema.json")
    registry.validate(zh_tree.document(), "schemas/canonical-language-tree.schema.json")
    registry.validate(alignment.document(), "schemas/bilingual-alignment-map.schema.json")


def test_parser_rejects_tampered_content_and_subtree_fingerprints() -> None:
    tree = _tree("en")
    content_tamper = deepcopy(tree.document())
    units = _array(content_tamper["source_units"])
    assert isinstance(units[4], dict)
    units[4]["content"] = "altered"
    with pytest.raises(RulebookError):
        parse_canonical_language_tree(content_tamper)

    structure_tamper = deepcopy(tree.document())
    nodes = _array(structure_tamper["nodes"])
    assert isinstance(nodes[3], dict)
    nodes[3]["sibling_order"] = 0
    with pytest.raises(RulebookError):
        parse_canonical_language_tree(structure_tamper)


def test_tree_rejects_orphan_duplicate_and_noncanonical_source_units() -> None:
    tree = _tree("en").document()
    orphan = deepcopy(tree)
    units = _array(orphan["source_units"])
    assert isinstance(units[-1], dict)
    units[-1]["tree_node_id"] = "unknown_node"
    with pytest.raises(RulebookError):
        parse_canonical_language_tree(orphan)

    reordered = deepcopy(tree)
    reordered_units = _array(reordered["source_units"])
    reordered_units[-1], reordered_units[-2] = reordered_units[-2], reordered_units[-1]
    with pytest.raises(RulebookError):
        parse_canonical_language_tree(reordered)


def test_alignment_requires_complete_ordered_exact_once_coverage() -> None:
    en_tree = _tree("en")
    zh_tree = _tree("zh-Hant")
    valid = _alignment(en_tree, zh_tree).document()
    groups = _array(valid["groups"])
    assert isinstance(groups[-1], dict)
    groups[-1]["en_source_unit_ids"] = ["en_body_1"]

    with pytest.raises(RulebookError):
        parse_bilingual_alignment_map(valid, en_tree=en_tree, zh_hant_tree=zh_tree)


def test_renderer_fails_closed_for_structured_content_without_mapping() -> None:
    en_tree = _tree("en", unsupported=True)
    zh_tree = _tree("zh-Hant", unsupported=True)
    alignment = _alignment(en_tree, zh_tree)

    with pytest.raises(RulebookError, match="ordinary renderer unsupported structure"):
        render_canonical_bilingual_location(
            en_tree=en_tree,
            zh_hant_tree=zh_tree,
            alignment_map=alignment,
            legal_location_ref=_ref("LEGAL_LOCATION", "ll_section_2", SHA_C),
        )


def test_sealer_rejects_non_nfc_or_trailing_space_instead_of_repairing_source() -> None:
    valid = _tree("en").document()
    draft = _json(
        {
            "source_format": valid["source_format"],
            "language": valid["language"],
            "legal_item_ref": valid["legal_item_ref"],
            "root_node_id": valid["root_node_id"],
            "nodes": [
                {
                    key: value
                    for key, value in _object(node).items()
                    if key
                    not in {
                        "language",
                        "legal_item_ref",
                        "node_content_fingerprint",
                        "subtree_fingerprint",
                    }
                }
                for node in _array(valid["nodes"])
            ],
            "source_units": [
                {
                    key: value
                    for key, value in _object(unit).items()
                    if key not in {"language", "legal_item_ref", "content_fingerprint"}
                }
                for unit in _array(valid["source_units"])
            ],
        }
    )
    units = _array(draft["source_units"])
    assert isinstance(units[0], dict)
    units[0]["content"] = "Cafe\u0301"
    with pytest.raises(RulebookError):
        seal_canonical_language_tree(draft)

    units[0]["content"] = "Sample Ordinance "
    with pytest.raises(RulebookError):
        seal_canonical_language_tree(draft)


class _ByteTokenCounter:
    """Exact deterministic test tokenizer: one token per UTF-8 byte."""

    def __init__(self, profile: PartitionServingProfile) -> None:
        self.profile_id = profile.profile_id
        self.profile_fingerprint = profile.profile_fingerprint
        self.tokenizer_id = profile.tokenizer_id

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))


def _partition_profile(
    *, max_tokens: int = 100_000, max_metadata_bytes: int = 100_000
) -> PartitionServingProfile:
    provisional = PartitionServingProfile(
        "psp_" + "1" * 48,
        "sha256:" + "0" * 64,
        "TEST_UTF8_BYTES_1.0.0",
        max_tokens,
        max_metadata_bytes,
        "Hong Kong",
        "Hong Kong",
        "legislation",
        "Hong Kong e-Legislation",
        "None",
    )
    return replace(
        provisional,
        profile_fingerprint=partition_serving_profile_fingerprint(provisional),
    )


@dataclass(frozen=True, slots=True)
class _PartitionRequestOptions:
    dependencies: bool = False
    unknown: bool = False
    indivisible: bool = False


def _partition_request(
    en_tree: CanonicalLanguageTree,
    zh_tree: CanonicalLanguageTree,
    alignment: BilingualAlignmentMap,
    options: _PartitionRequestOptions | None = None,
) -> BilingualPartitionRequest:
    options = options or _PartitionRequestOptions()
    primary_groups = tuple(
        group.alignment_group_id
        for group in alignment.groups
        if group.alignment_group_id.startswith(("align_body", "align_note"))
    )
    if primary_groups == ("align_body_many_many",):
        nodes = (
            AlignedPartitionNode(
                "partition_section",
                "en_section_2",
                "zh_section_2",
                primary_groups,
                (),
                (),
                "UNKNOWN" if options.unknown else "SUPPORTED",
                options.indivisible,
            ),
        )
    else:
        paragraph_group_ids = [
            [group_id] for group_id in primary_groups if group_id.startswith("align_body_")
        ]
        if "align_note_1" in primary_groups:
            paragraph_group_ids[0].append("align_note_1")
        child_ids = tuple(
            f"partition_paragraph_{index}" for index in range(1, len(paragraph_group_ids) + 1)
        )
        node_list = [
            AlignedPartitionNode(
                "partition_section",
                "en_section_2",
                "zh_section_2",
                primary_groups,
                (),
                child_ids,
                "UNKNOWN" if options.unknown else "SUPPORTED",
                options.indivisible,
            )
        ]
        node_list.extend(
            AlignedPartitionNode(
                f"partition_paragraph_{index}",
                f"en_paragraph_{index}",
                f"zh_paragraph_{index}",
                tuple(group_ids),
                ("align_heading",) if options.dependencies and index > 1 else (),
                (),
            )
            for index, group_ids in enumerate(paragraph_group_ids, start=1)
        )
        nodes = tuple(node_list)
    return BilingualPartitionRequest(
        next(
            group.legal_location_ref
            for group in alignment.groups
            if group.alignment_group_id == "align_locator"
        ),
        en_tree.fingerprint,
        zh_tree.fingerprint,
        alignment.fingerprint,
        ("partition_section",),
        nodes,
    )


@dataclass(frozen=True, slots=True)
class _PartitionScenario:
    combined_body: bool = False
    dependencies: bool = False
    unknown: bool = False
    indivisible: bool = False
    body_multiplier: int = 1
    third_paragraph: bool = False
    statutory_note: bool = False


def _partition_result(
    profile: PartitionServingProfile,
    scenario: _PartitionScenario | None = None,
) -> BilingualPartitionResult:
    scenario = scenario or _PartitionScenario()
    en_tree = _tree(
        "en",
        body_multiplier=scenario.body_multiplier,
        third_paragraph=scenario.third_paragraph,
        statutory_note=scenario.statutory_note,
    )
    zh_tree = _tree(
        "zh-Hant",
        body_multiplier=scenario.body_multiplier,
        third_paragraph=scenario.third_paragraph,
        statutory_note=scenario.statutory_note,
    )
    alignment = _alignment(en_tree, zh_tree, combined_body=scenario.combined_body)
    request = _partition_request(
        en_tree,
        zh_tree,
        alignment,
        _PartitionRequestOptions(
            scenario.dependencies,
            scenario.unknown,
            scenario.indivisible,
        ),
    )
    return partition_canonical_bilingual_location(
        BilingualPartitionExecution(
            request,
            profile,
            _ByteTokenCounter(profile),
            en_tree,
            zh_tree,
            alignment,
        )
    )


def _nested_partition_material() -> tuple[
    CanonicalLanguageTree,
    CanonicalLanguageTree,
    BilingualAlignmentMap,
    BilingualPartitionRequest,
]:
    item = _ref("LEGAL_ITEM", "li_nested", SHA_A)
    instrument = _ref("LEGAL_LOCATION", "ll_nested_instrument", SHA_B)
    provision = _ref("LEGAL_LOCATION", "ll_nested_section", SHA_C)

    def tree(language: str) -> CanonicalLanguageTree:
        prefix = "en" if language == "en" else "zh"
        title = "Nested Ordinance" if language == "en" else "嵌套條例"
        citation = "Cap. 998" if language == "en" else "第998章"
        locator = "section 3" if language == "en" else "第3條"
        heading = "Nested units" if language == "en" else "嵌套單元"
        body_1a = (
            "(a) First complete official subparagraph. " * 4
            if language == "en"
            else "(a) 第一個完整官方分段。" * 4
        ).strip()
        body_1b = (
            "(b) Second complete official subparagraph. " * 4
            if language == "en"
            else "(b) 第二個完整官方分段。" * 4
        ).strip()
        body_2 = "(2) Separate sibling." if language == "en" else "(2) 獨立的同級單元。"
        root = f"{prefix}_nested_instrument"
        section = f"{prefix}_nested_section"
        paragraph_1 = f"{prefix}_nested_paragraph_1"
        subparagraph_1a = f"{prefix}_nested_subparagraph_1a"
        subparagraph_1b = f"{prefix}_nested_subparagraph_1b"
        paragraph_2 = f"{prefix}_nested_paragraph_2"
        units = [
            _unit((f"{prefix}_nested_title", root), instrument, ("INSTRUMENT_TITLE", title), 0),
            _unit(
                (f"{prefix}_nested_citation", root),
                instrument,
                ("INSTRUMENT_CITATION", citation),
                1,
            ),
            _unit(
                (f"{prefix}_nested_locator", section),
                provision,
                ("LOCATION_LOCATOR", locator),
                0,
            ),
            _unit(
                (f"{prefix}_nested_heading", section),
                provision,
                ("LOCATION_HEADING", heading),
                1,
            ),
            _unit(
                (f"{prefix}_nested_body_1a", subparagraph_1a),
                provision,
                ("BODY_TEXT", body_1a),
                0,
            ),
            _unit(
                (f"{prefix}_nested_body_1b", subparagraph_1b),
                provision,
                ("BODY_TEXT", body_1b),
                0,
            ),
            _unit(
                (f"{prefix}_nested_body_2", paragraph_2),
                provision,
                ("BODY_TEXT", body_2),
                0,
            ),
        ]
        nodes = [
            _node(
                (root, instrument),
                ("INSTRUMENT", None),
                0,
                (
                    [f"{prefix}_nested_title", f"{prefix}_nested_citation"],
                    [section],
                ),
            ),
            _node(
                (section, provision),
                ("PROVISION", root),
                0,
                (
                    [f"{prefix}_nested_locator", f"{prefix}_nested_heading"],
                    [paragraph_1, paragraph_2],
                ),
            ),
            _node(
                (paragraph_1, provision),
                ("PARAGRAPH", section),
                0,
                (
                    [],
                    [subparagraph_1a, subparagraph_1b],
                ),
            ),
            _node(
                (subparagraph_1a, provision),
                ("SUBPARAGRAPH", paragraph_1),
                0,
                (
                    [f"{prefix}_nested_body_1a"],
                    [],
                ),
            ),
            _node(
                (subparagraph_1b, provision),
                ("SUBPARAGRAPH", paragraph_1),
                1,
                (
                    [f"{prefix}_nested_body_1b"],
                    [],
                ),
            ),
            _node(
                (paragraph_2, provision),
                ("PARAGRAPH", section),
                1,
                (
                    [f"{prefix}_nested_body_2"],
                    [],
                ),
            ),
        ]
        return seal_canonical_language_tree(
            _json(
                {
                    "source_format": "SYNTHETIC_CANONICAL_INPUT",
                    "language": language,
                    "legal_item_ref": item,
                    "root_node_id": root,
                    "nodes": nodes,
                    "source_units": units,
                }
            )
        )

    en_tree = tree("en")
    zh_tree = tree("zh-Hant")
    evidence = _ref("BILINGUAL_MAPPING_EVIDENCE", "map_nested", SHA_A)
    groups = [
        ("align_nested_title", instrument, "nested_title"),
        ("align_nested_citation", instrument, "nested_citation"),
        ("align_nested_locator", provision, "nested_locator"),
        ("align_nested_heading", provision, "nested_heading"),
        ("align_nested_body_1a", provision, "nested_body_1a"),
        ("align_nested_body_1b", provision, "nested_body_1b"),
        ("align_nested_body_2", provision, "nested_body_2"),
    ]
    alignment = parse_bilingual_alignment_map(
        _json(
            {
                "$schema": BILINGUAL_ALIGNMENT_MAP_SCHEMA,
                "contract_version": CANONICAL_TREE_CONTRACT_VERSION,
                "legal_item_ref": item,
                "groups": [
                    {
                        "alignment_group_id": group_id,
                        "legal_location_ref": location,
                        "en_source_unit_ids": [f"en_{suffix}"],
                        "zh_hant_source_unit_ids": [f"zh_{suffix}"],
                        "mapping_evidence_ref": evidence,
                    }
                    for group_id, location, suffix in groups
                ],
            }
        ),
        en_tree=en_tree,
        zh_hant_tree=zh_tree,
    )
    body_groups = (
        "align_nested_body_1a",
        "align_nested_body_1b",
        "align_nested_body_2",
    )
    nodes = (
        AlignedPartitionNode(
            "nested_section",
            "en_nested_section",
            "zh_nested_section",
            body_groups,
            (),
            ("nested_paragraph_1", "nested_paragraph_2"),
        ),
        AlignedPartitionNode(
            "nested_paragraph_1",
            "en_nested_paragraph_1",
            "zh_nested_paragraph_1",
            body_groups[:2],
            (),
            ("nested_subparagraph_1a", "nested_subparagraph_1b"),
        ),
        AlignedPartitionNode(
            "nested_subparagraph_1a",
            "en_nested_subparagraph_1a",
            "zh_nested_subparagraph_1a",
            (body_groups[0],),
            (),
            (),
        ),
        AlignedPartitionNode(
            "nested_subparagraph_1b",
            "en_nested_subparagraph_1b",
            "zh_nested_subparagraph_1b",
            (body_groups[1],),
            (),
            (),
        ),
        AlignedPartitionNode(
            "nested_paragraph_2",
            "en_nested_paragraph_2",
            "zh_nested_paragraph_2",
            (body_groups[2],),
            (),
            (),
        ),
    )
    request = BilingualPartitionRequest(
        provision,
        en_tree.fingerprint,
        zh_tree.fingerprint,
        alignment.fingerprint,
        ("nested_section",),
        nodes,
    )
    return en_tree, zh_tree, alignment, request


def _table_partition_material() -> tuple[
    CanonicalLanguageTree,
    CanonicalLanguageTree,
    BilingualAlignmentMap,
    BilingualPartitionRequest,
]:
    item = _ref("LEGAL_ITEM", "li_table", SHA_A)
    instrument = _ref("LEGAL_LOCATION", "ll_table_instrument", SHA_B)
    table_location = _ref("LEGAL_LOCATION", "ll_table_fees", SHA_C)

    def tree(language: str) -> CanonicalLanguageTree:
        prefix = "en" if language == "en" else "zh"
        title = "Fees Ordinance" if language == "en" else "費用條例"
        citation = "Cap. 997" if language == "en" else "第997章"
        locator = "Schedule 1, table 1" if language == "en" else "附表1表1"
        heading = "Licence fees" if language == "en" else "牌照費"
        headers = ("Item", "Fee > Amount") if language == "en" else ("項目", "費用 > 款額")
        if language == "en":
            row_values = (
                ("1", "$1,000 " + "annual licence fee " * 8),
                ("2", "$500 " + "limited licence fee " * 8),
            )
        else:
            row_values = (
                ("1", "$1,000 " + "每年牌照費 " * 8),
                ("2", "$500 " + "有限牌照費 " * 8),
            )
        row_values = tuple((item, value.strip()) for item, value in row_values)
        root = f"{prefix}_table_instrument"
        table = f"{prefix}_table"
        header_row = f"{prefix}_table_header_row"
        row_1 = f"{prefix}_table_row_1"
        row_2 = f"{prefix}_table_row_2"
        header_cells = tuple(f"{prefix}_table_header_{index}" for index in range(1, 3))
        row_1_cells = tuple(f"{prefix}_table_row_1_cell_{index}" for index in range(1, 3))
        row_2_cells = tuple(f"{prefix}_table_row_2_cell_{index}" for index in range(1, 3))
        units = [
            _unit((f"{prefix}_table_title", root), instrument, ("INSTRUMENT_TITLE", title), 0),
            _unit(
                (f"{prefix}_table_citation", root),
                instrument,
                ("INSTRUMENT_CITATION", citation),
                1,
            ),
            _unit(
                (f"{prefix}_table_locator", table),
                table_location,
                ("LOCATION_LOCATOR", locator),
                0,
            ),
            _unit(
                (f"{prefix}_table_heading", table),
                table_location,
                ("LOCATION_HEADING", heading),
                1,
            ),
            *(
                _unit(
                    (f"{prefix}_table_header_unit_{index}", header_cells[index - 1]),
                    table_location,
                    ("TABLE_HEADER", header),
                    0,
                )
                for index, header in enumerate(headers, start=1)
            ),
            *(
                _unit(
                    (f"{prefix}_table_row_1_unit_{index}", row_1_cells[index - 1]),
                    table_location,
                    ("TABLE_CELL", value),
                    0,
                )
                for index, value in enumerate(row_values[0], start=1)
            ),
            *(
                _unit(
                    (f"{prefix}_table_row_2_unit_{index}", row_2_cells[index - 1]),
                    table_location,
                    ("TABLE_CELL", value),
                    0,
                )
                for index, value in enumerate(row_values[1], start=1)
            ),
        ]
        nodes = [
            _node(
                (root, instrument),
                ("INSTRUMENT", None),
                0,
                ([f"{prefix}_table_title", f"{prefix}_table_citation"], [table]),
            ),
            _node(
                (table, table_location),
                ("TABLE", root),
                0,
                (
                    [f"{prefix}_table_locator", f"{prefix}_table_heading"],
                    [header_row, row_1, row_2],
                ),
            ),
            _node((header_row, table_location), ("TABLE_ROW", table), 0, ([], list(header_cells))),
            *(
                _node(
                    (cell, table_location),
                    ("TABLE_CELL", header_row),
                    index - 1,
                    ([f"{prefix}_table_header_unit_{index}"], []),
                )
                for index, cell in enumerate(header_cells, start=1)
            ),
            _node((row_1, table_location), ("TABLE_ROW", table), 1, ([], list(row_1_cells))),
            *(
                _node(
                    (cell, table_location),
                    ("TABLE_CELL", row_1),
                    index - 1,
                    ([f"{prefix}_table_row_1_unit_{index}"], []),
                )
                for index, cell in enumerate(row_1_cells, start=1)
            ),
            _node((row_2, table_location), ("TABLE_ROW", table), 2, ([], list(row_2_cells))),
            *(
                _node(
                    (cell, table_location),
                    ("TABLE_CELL", row_2),
                    index - 1,
                    ([f"{prefix}_table_row_2_unit_{index}"], []),
                )
                for index, cell in enumerate(row_2_cells, start=1)
            ),
        ]
        return seal_canonical_language_tree(
            _json(
                {
                    "source_format": "SYNTHETIC_CANONICAL_INPUT",
                    "language": language,
                    "legal_item_ref": item,
                    "root_node_id": root,
                    "nodes": nodes,
                    "source_units": units,
                }
            )
        )

    en_tree = tree("en")
    zh_tree = tree("zh-Hant")
    evidence = _ref("BILINGUAL_MAPPING_EVIDENCE", "map_table", SHA_A)
    alignment_groups = (
        ("align_table_title", instrument, ("table_title",)),
        ("align_table_citation", instrument, ("table_citation",)),
        ("align_table_locator", table_location, ("table_locator",)),
        ("align_table_heading", table_location, ("table_heading",)),
        (
            "align_table_headers",
            table_location,
            ("table_header_unit_1", "table_header_unit_2"),
        ),
        (
            "align_table_row_1",
            table_location,
            ("table_row_1_unit_1", "table_row_1_unit_2"),
        ),
        (
            "align_table_row_2",
            table_location,
            ("table_row_2_unit_1", "table_row_2_unit_2"),
        ),
    )
    alignment = parse_bilingual_alignment_map(
        _json(
            {
                "$schema": BILINGUAL_ALIGNMENT_MAP_SCHEMA,
                "contract_version": CANONICAL_TREE_CONTRACT_VERSION,
                "legal_item_ref": item,
                "groups": [
                    {
                        "alignment_group_id": group_id,
                        "legal_location_ref": location,
                        "en_source_unit_ids": [f"en_{suffix}" for suffix in suffixes],
                        "zh_hant_source_unit_ids": [f"zh_{suffix}" for suffix in suffixes],
                        "mapping_evidence_ref": evidence,
                    }
                    for group_id, location, suffixes in alignment_groups
                ],
            }
        ),
        en_tree=en_tree,
        zh_hant_tree=zh_tree,
    )
    nodes = (
        AlignedPartitionNode(
            "partition_table",
            "en_table",
            "zh_table",
            ("align_table_row_1", "align_table_row_2"),
            ("align_table_headers",),
            ("partition_table_row_1", "partition_table_row_2"),
        ),
        AlignedPartitionNode(
            "partition_table_row_1",
            "en_table_row_1",
            "zh_table_row_1",
            ("align_table_row_1",),
            ("align_table_headers",),
            (),
            indivisible=True,
        ),
        AlignedPartitionNode(
            "partition_table_row_2",
            "en_table_row_2",
            "zh_table_row_2",
            ("align_table_row_2",),
            ("align_table_headers",),
            (),
            indivisible=True,
        ),
    )
    request = BilingualPartitionRequest(
        table_location,
        en_tree.fingerprint,
        zh_tree.fingerprint,
        alignment.fingerprint,
        ("partition_table",),
        nodes,
    )
    return en_tree, zh_tree, alignment, request


def _largest_partitioning_token_limit(*, dependencies: bool = False) -> int:
    body_multiplier = 4 if dependencies else 1
    unsplit = _partition_result(
        _partition_profile(), _PartitionScenario(body_multiplier=body_multiplier)
    )
    maximum = unsplit.parts[0].measurement.text_tokens
    for limit in range(maximum - 1, 0, -1):
        result = _partition_result(
            _partition_profile(max_tokens=limit),
            _PartitionScenario(
                dependencies=dependencies,
                body_multiplier=body_multiplier,
            ),
        )
        if result.reason is PartitionReason.PASS_PARTITIONED:
            return limit
    message = "fixture has no valid partitioning token limit"
    raise AssertionError(message)


def test_partition_keeps_one_complete_bilingual_location_when_both_limits_fit() -> None:
    result = _partition_result(_partition_profile())

    assert result.disposition is PartitionDisposition.PASS
    assert result.reason is PartitionReason.PASS_UNSPLIT
    assert len(result.parts) == 1
    assert "Serving part:" not in result.parts[0].text
    assert "服務部分" not in result.parts[0].text
    assert result.parts[0].measurement.fits


def test_distinct_short_legal_locations_are_processed_separately_and_never_merged() -> None:
    profile = _partition_profile()
    first_en = _tree("en")
    first_zh = _tree("zh-Hant")
    second_location = _ref("LEGAL_LOCATION", "ll_section_3", SHA_B)
    second_en = _relocated_tree(first_en, second_location)
    second_zh = _relocated_tree(first_zh, second_location)
    first_alignment = _alignment(first_en, first_zh, combined_body=False)
    second_alignment = _alignment(second_en, second_zh, combined_body=False)

    def execution(
        en_tree: CanonicalLanguageTree,
        zh_tree: CanonicalLanguageTree,
        alignment: BilingualAlignmentMap,
    ) -> BilingualPartitionExecution:
        return BilingualPartitionExecution(
            _partition_request(en_tree, zh_tree, alignment),
            profile,
            _ByteTokenCounter(profile),
            en_tree,
            zh_tree,
            alignment,
        )

    first = execution(first_en, first_zh, first_alignment)
    second = execution(second_en, second_zh, second_alignment)
    result = partition_canonical_bilingual_locations(
        BilingualPartitionBatchExecution((first, second))
    )

    assert result.disposition is PartitionDisposition.PASS
    assert result.reason.value == "LOCATIONS_PROCESSED_SEPARATELY"
    assert result.parts == ()
    assert tuple(item.legal_location_ref["ref_id"] for item in result.location_results) == (
        "ll_section_2",
        "ll_section_3",
    )
    assert all(
        item.result.reason is PartitionReason.PASS_UNSPLIT and len(item.result.parts) == 1
        for item in result.location_results
    )
    assert result.document()["cross_location_combination"] == "FORBIDDEN"

    with pytest.raises(RulebookError, match="distinct Legal Locations"):
        partition_canonical_bilingual_locations(BilingualPartitionBatchExecution((first, first)))


def test_partition_descends_to_official_aligned_children_and_revalidates_labels() -> None:
    limit = _largest_partitioning_token_limit()
    result = _partition_result(_partition_profile(max_tokens=limit))

    assert result.disposition is PartitionDisposition.PASS
    assert result.reason is PartitionReason.PASS_PARTITIONED
    assert tuple(part.primary_partition_node_ids for part in result.parts) == (
        ("partition_paragraph_1",),
        ("partition_paragraph_2",),
    )
    assert all(part.total_parts == 2 and part.measurement.fits for part in result.parts)
    assert "Serving part: 1 of 2" in result.parts[0].text
    assert "服務部分\uff1a第2部分\uff0c共2部分" in result.parts[1].text


def test_partition_uses_minimum_parts_then_fills_the_earliest_part() -> None:
    unsplit = _partition_result(_partition_profile(), _PartitionScenario(third_paragraph=True))
    maximum = unsplit.parts[0].measurement.text_tokens
    selected = None
    for limit in range(maximum - 1, 0, -1):
        candidate = _partition_result(
            _partition_profile(max_tokens=limit),
            _PartitionScenario(third_paragraph=True),
        )
        if candidate.reason is PartitionReason.PASS_PARTITIONED and tuple(
            len(part.primary_partition_node_ids) for part in candidate.parts
        ) == (2, 1):
            selected = candidate
            break

    assert selected is not None
    assert len(selected.parts) == 2
    assert selected.parts[0].primary_partition_node_ids == (
        "partition_paragraph_1",
        "partition_paragraph_2",
    )
    assert selected.parts[1].primary_partition_node_ids == ("partition_paragraph_3",)


def test_partition_recurses_past_an_oversized_paragraph_to_subparagraphs() -> None:
    en_tree, zh_tree, alignment, request = _nested_partition_material()
    wide_profile = _partition_profile()
    wide = partition_canonical_bilingual_location(
        BilingualPartitionExecution(
            request,
            wide_profile,
            _ByteTokenCounter(wide_profile),
            en_tree,
            zh_tree,
            alignment,
        )
    )
    selected = None
    for limit in range(wide.parts[0].measurement.text_tokens - 1, 0, -1):
        profile = _partition_profile(max_tokens=limit)
        candidate = partition_canonical_bilingual_location(
            BilingualPartitionExecution(
                request,
                profile,
                _ByteTokenCounter(profile),
                en_tree,
                zh_tree,
                alignment,
            )
        )
        primary_nodes = tuple(
            node_id for part in candidate.parts for node_id in part.primary_partition_node_ids
        )
        if candidate.reason is PartitionReason.PASS_PARTITIONED and (
            "nested_subparagraph_1a" in primary_nodes and "nested_subparagraph_1b" in primary_nodes
        ):
            selected = candidate
            break

    assert selected is not None
    selected_nodes = tuple(
        node_id for part in selected.parts for node_id in part.primary_partition_node_ids
    )
    assert "nested_paragraph_1" not in selected_nodes
    assert selected_nodes == (
        "nested_subparagraph_1a",
        "nested_subparagraph_1b",
        "nested_paragraph_2",
    )


def test_table_renderer_preserves_header_paths_row_order_and_bilingual_scaffolding() -> None:
    en_tree, zh_tree, alignment, request = _table_partition_material()

    rendered = render_canonical_bilingual_location(
        en_tree=en_tree,
        zh_hant_tree=zh_tree,
        alignment_map=alignment,
        legal_location_ref=request.legal_location_ref,
    )

    assert "[Table]\nTitle: Licence fees" in rendered.text
    assert "Row: 1\nItem: 1\nFee > Amount: $1,000" in rendered.text
    assert "Row: 2\nItem: 2\nFee > Amount: $500" in rendered.text
    assert "[表格]\n標題\uff1a牌照費" in rendered.text
    assert "行\uff1a1\n項目\uff1a1\n費用 > 款額\uff1a$1,000" in rendered.text


def test_table_partition_repeats_headers_and_never_splits_an_indivisible_row() -> None:
    en_tree, zh_tree, alignment, request = _table_partition_material()
    wide_profile = _partition_profile()
    wide = partition_canonical_bilingual_location(
        BilingualPartitionExecution(
            request,
            wide_profile,
            _ByteTokenCounter(wide_profile),
            en_tree,
            zh_tree,
            alignment,
        )
    )
    assert wide.reason is PartitionReason.PASS_UNSPLIT

    selected = None
    for limit in range(wide.parts[0].measurement.text_tokens - 1, 0, -1):
        profile = _partition_profile(max_tokens=limit)
        candidate = partition_canonical_bilingual_location(
            BilingualPartitionExecution(
                request,
                profile,
                _ByteTokenCounter(profile),
                en_tree,
                zh_tree,
                alignment,
            )
        )
        if candidate.reason is PartitionReason.PASS_PARTITIONED:
            selected = candidate
            break

    assert selected is not None
    assert tuple(part.primary_partition_node_ids for part in selected.parts) == (
        ("partition_table_row_1",),
        ("partition_table_row_2",),
    )
    assert all(
        part.dependency_alignment_group_ids == ("align_table_headers",)
        and part.en_dependency_source_unit_ids
        == ("en_table_header_unit_1", "en_table_header_unit_2")
        and "Parent context (repeated):\n[Table headers]" in part.text
        and "上層脈絡\uff08重複\uff09\uff1a\n[表格標題]" in part.text
        for part in selected.parts
    )
    tiny_profile = _partition_profile(max_tokens=1)
    tiny = partition_canonical_bilingual_location(
        BilingualPartitionExecution(
            request,
            tiny_profile,
            _ByteTokenCounter(tiny_profile),
            en_tree,
            zh_tree,
            alignment,
        )
    )
    assert tiny.reason is PartitionReason.SMALLEST_DEPENDENT_BRANCH_OVER_LIMIT
    assert tiny.quarantined_partition_node_ids == (
        "partition_table_row_1",
        "partition_table_row_2",
    )


def test_partition_measures_complete_metadata_independently_from_embedding_text() -> None:
    unsplit = _partition_result(_partition_profile())
    maximum = unsplit.parts[0].measurement.metadata_bytes
    selected = None
    selected_limit = 0
    for limit in range(maximum - 1, 0, -1):
        candidate = _partition_result(
            _partition_profile(max_tokens=100_000, max_metadata_bytes=limit)
        )
        if candidate.reason is PartitionReason.PASS_PARTITIONED:
            selected = candidate
            selected_limit = limit
            break

    assert selected is not None
    assert all(part.measurement.metadata_bytes <= selected_limit for part in selected.parts)
    assert all(part.measurement.text_tokens < 100_000 for part in selected.parts)


def test_required_parent_context_is_repeated_bilingually_and_measured() -> None:
    limit = _largest_partitioning_token_limit(dependencies=True)
    result = _partition_result(
        _partition_profile(max_tokens=limit),
        _PartitionScenario(dependencies=True, body_multiplier=4),
    )

    assert result.reason is PartitionReason.PASS_PARTITIONED
    second = result.parts[-1]
    assert second.dependency_alignment_group_ids == ("align_heading",)
    assert "Parent context (repeated):" in second.text
    assert "上層脈絡\uff08重複\uff09\uff1a" in second.text
    assert second.en_dependency_source_unit_ids == ("en_heading",)
    assert second.zh_hant_dependency_source_unit_ids == ("zh_heading",)


def test_statutory_note_stays_with_the_affected_unit_and_is_never_stranded() -> None:
    scenario = _PartitionScenario(statutory_note=True)
    unsplit = _partition_result(_partition_profile(), scenario)
    selected = None
    for limit in range(unsplit.parts[0].measurement.text_tokens - 1, 0, -1):
        candidate = _partition_result(_partition_profile(max_tokens=limit), scenario)
        if candidate.reason is PartitionReason.PASS_PARTITIONED:
            selected = candidate
            break

    assert selected is not None
    note_parts = [
        part for part in selected.parts if "align_note_1" in part.primary_alignment_group_ids
    ]
    assert len(note_parts) == 1
    note_part = note_parts[0]
    assert note_part.primary_partition_node_ids == ("partition_paragraph_1",)
    assert note_part.primary_alignment_group_ids == ("align_body_1", "align_note_1")
    assert note_part.en_primary_source_unit_ids == (
        "en_body_1",
        "en_note_marker_1",
        "en_note_body_1",
    )
    assert note_part.zh_hant_primary_source_unit_ids == (
        "zh_body_1",
        "zh_note_marker_1",
        "zh_note_body_1",
    )
    assert all(
        "en_note_marker_1" not in part.en_primary_source_unit_ids
        and "en_note_body_1" not in part.en_primary_source_unit_ids
        for part in selected.parts
        if part is not note_part
    )


def test_indivisible_non_one_to_one_group_over_limit_quarantines_without_cutting() -> None:
    result = _partition_result(
        _partition_profile(max_tokens=1, max_metadata_bytes=100_000),
        _PartitionScenario(combined_body=True, indivisible=True),
    )

    assert result.disposition is PartitionDisposition.QUARANTINE
    assert result.reason is PartitionReason.SMALLEST_DEPENDENT_BRANCH_OVER_LIMIT
    assert result.parts == ()
    assert result.coverage_gap_required is True
    assert result.quarantined_partition_node_ids == ("partition_section",)


def _partition_release_request(
    partition_result: BilingualPartitionResult,
    decision: PartitionReleaseChoice,
    *,
    affirmative_record_change_proved: bool = False,
) -> PartitionReleaseConsequenceRequest:
    previous_release = _ref("CORPUS_RELEASE", "rel_previous", SHA_A)
    withholding_release: dict[str, JsonValue] | None = _ref(
        "CORPUS_RELEASE", "rel_withholding", SHA_B
    )
    selected_release: dict[str, JsonValue] | None = None
    continued = False
    misleading = False
    withholding_supported = False
    warning = "Coverage gap: the new Official Version is not safely partitionable."
    if decision is PartitionReleaseChoice.CARRY_FORWARD_LAST_APPROVED_RELEASE:
        selected_release = previous_release
        continued = True
        withholding_release = None
    elif decision is PartitionReleaseChoice.CREATE_WITHHOLDING_RELEASE:
        selected_release = withholding_release
        misleading = True
        withholding_supported = True
        warning = None
    else:
        withholding_release = None
    return PartitionReleaseConsequenceRequest(
        partition_result,
        partition_result.fingerprint,
        _ref("OFFICIAL_VERSION", "ov_new", SHA_B),
        _ref("OFFICIAL_VERSION", "ov_previous", SHA_A),
        previous_release,
        _ref("SERVING_TARGET", "target_previous", SHA_C),
        decision,
        _ref("LEGAL_DESK_DECISION", "decision_partition", SHA_A),
        _ref("DECISION_EVIDENCE", "evidence_partition", SHA_B),
        _ref("AUDIT_HISTORY", "audit_partition", SHA_A),
        _ref("COVERAGE_GAP", "gap_partition", SHA_C),
        "The new Official Version cannot be partitioned within the admitted ceilings.",
        "hk-legislation-legal-desk",
        "2026-08-20T00:00:00Z",
        "2026-08-24T00:00:00Z",
        "2026-08-31T00:00:00Z",
        continued,
        affirmative_record_change_proved,
        misleading,
        withholding_supported,
        selected_release,
        withholding_release,
        warning,
    )


def test_unsafe_new_version_requires_one_explicit_effect_free_release_consequence() -> None:
    unsafe = _partition_result(
        _partition_profile(max_tokens=1),
        _PartitionScenario(combined_body=True, indivisible=True),
    )

    carry = decide_partition_failure_release(
        _partition_release_request(
            unsafe,
            PartitionReleaseChoice.CARRY_FORWARD_LAST_APPROVED_RELEASE,
        )
    )
    withhold = decide_partition_failure_release(
        _partition_release_request(
            unsafe,
            PartitionReleaseChoice.CREATE_WITHHOLDING_RELEASE,
        )
    )
    no_rebuild = decide_partition_failure_release(
        _partition_release_request(
            unsafe,
            PartitionReleaseChoice.NO_JURISDICTION_REBUILD,
        )
    )

    assert carry.release_action == "SELECT_LAST_APPROVED_WITH_WARNING"
    assert carry.routing_action == "BUILD_EXPLICIT_CARRY_FORWARD_TARGET_AFTER_APPROVAL"
    assert carry.approval_required is True
    assert withhold.release_action == "CREATE_COMPLETE_WITHHOLDING_RELEASE"
    assert withhold.approval_required is True
    assert no_rebuild.release_action == "NO_NEW_DESIRED_STATE"
    assert no_rebuild.routing_action == "RETAIN_PREVIOUS_VERIFIED_TARGET"
    assert all(
        result.coverage_gap_required
        and result.parts == ()
        and result.document()["predecessor_retirement"] == "FORBIDDEN"
        and result.document()["external_effects"] == "NONE"
        for result in (carry, withhold, no_rebuild)
    )

    with pytest.raises(RulebookError, match="no-rebuild decision"):
        decide_partition_failure_release(
            replace(
                _partition_release_request(
                    unsafe,
                    PartitionReleaseChoice.NO_JURISDICTION_REBUILD,
                ),
                warning=None,
            )
        )

    with pytest.raises(RulebookError, match="carry-forward decision"):
        decide_partition_failure_release(
            _partition_release_request(
                unsafe,
                PartitionReleaseChoice.CARRY_FORWARD_LAST_APPROVED_RELEASE,
                affirmative_record_change_proved=True,
            )
        )


def test_unknown_source_structure_blocks_instead_of_becoming_a_split_boundary() -> None:
    result = _partition_result(_partition_profile(), _PartitionScenario(unknown=True))

    assert result.disposition is PartitionDisposition.BLOCK
    assert result.reason is PartitionReason.SOURCE_CONTRACT_REVIEW_REQUIRED
    assert result.parts == ()


def test_text_bound_to_the_wrong_legal_location_blocks_even_when_it_fits() -> None:
    profile = _partition_profile()
    en_tree = _tree("en")
    zh_tree = _tree("zh-Hant")
    alignment = _alignment(en_tree, zh_tree, combined_body=False)
    request = _partition_request(en_tree, zh_tree, alignment)

    result = partition_canonical_bilingual_location(
        BilingualPartitionExecution(
            replace(
                request,
                legal_location_ref=_ref("LEGAL_LOCATION", "ll_section_3", SHA_B),
            ),
            profile,
            _ByteTokenCounter(profile),
            en_tree,
            zh_tree,
            alignment,
        )
    )

    assert result.disposition is PartitionDisposition.BLOCK
    assert result.reason is PartitionReason.SOURCE_LOCATION_OWNERSHIP_DEFECT
    assert result.parts == ()
    assert result.coverage_gap_required is False


def test_partition_profile_or_bilingual_primary_inventory_drift_fails_closed() -> None:
    profile = _partition_profile()
    with pytest.raises(RulebookError, match="partition serving profile"):
        _partition_result(replace(profile, max_text_tokens=profile.max_text_tokens - 1))

    en_tree = _tree("en")
    zh_tree = _tree("zh-Hant")
    alignment = _alignment(en_tree, zh_tree, combined_body=False)
    request = _partition_request(en_tree, zh_tree, alignment)
    bad_root = replace(request.nodes[0], primary_alignment_group_ids=("align_body_1",))
    missing = partition_canonical_bilingual_location(
        BilingualPartitionExecution(
            replace(request, nodes=(bad_root, *request.nodes[1:])),
            profile,
            _ByteTokenCounter(profile),
            en_tree,
            zh_tree,
            alignment,
        )
    )
    assert missing.disposition is PartitionDisposition.BLOCK
    assert missing.reason is PartitionReason.SOURCE_UNIT_COVERAGE_DEFECT

    reordered_root = replace(
        request.nodes[0],
        primary_alignment_group_ids=("align_body_2", "align_body_1"),
    )
    reordered = partition_canonical_bilingual_location(
        BilingualPartitionExecution(
            replace(request, nodes=(reordered_root, *request.nodes[1:])),
            profile,
            _ByteTokenCounter(profile),
            en_tree,
            zh_tree,
            alignment,
        )
    )
    assert reordered.disposition is PartitionDisposition.BLOCK
    assert reordered.reason is PartitionReason.SOURCE_UNIT_COVERAGE_DEFECT

    wrong_language_boundary = replace(request.nodes[1], en_tree_node_id="en_paragraph_2")
    mismatch = partition_canonical_bilingual_location(
        BilingualPartitionExecution(
            replace(
                request,
                nodes=(request.nodes[0], wrong_language_boundary, *request.nodes[2:]),
            ),
            profile,
            _ByteTokenCounter(profile),
            en_tree,
            zh_tree,
            alignment,
        )
    )
    assert mismatch.disposition is PartitionDisposition.QUARANTINE
    assert mismatch.reason is PartitionReason.BILINGUAL_ALIGNMENT_MISMATCH
    assert mismatch.coverage_gap_required is True


def test_partition_output_and_source_coverage_proof_are_byte_reproducible() -> None:
    limit = _largest_partitioning_token_limit()
    profile = _partition_profile(max_tokens=limit)
    first = _partition_result(profile)
    second = _partition_result(profile)

    assert first.canonical_bytes == second.canonical_bytes
    assert first.fingerprint == second.fingerprint
    assert tuple(
        unit_id for part in first.parts for unit_id in part.en_primary_source_unit_ids
    ) == ("en_body_1", "en_body_2")
    assert tuple(
        unit_id for part in first.parts for unit_id in part.zh_hant_primary_source_unit_ids
    ) == ("zh_body_1", "zh_body_2")
