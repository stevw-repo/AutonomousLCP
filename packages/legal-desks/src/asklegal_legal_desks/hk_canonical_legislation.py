"""Canonical source-neutral Hong Kong legislation trees and ordinary rendering.

This module deliberately starts after source-format interpretation.  It does
not claim to parse authentic HKeL XML or reconcile an official copy.  A later
admitted source adapter may construct this closed representation only after its
own pinned XML/XSD and publication-specification checks pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, Never
from unicodedata import is_normalized

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .model import RulebookError, RulebookErrorCode

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

CANONICAL_LANGUAGE_TREE_SCHEMA = (
    "https://contracts.asklegal.local/v1/hk-legislation-canonical-language-tree.schema.json"
)
BILINGUAL_ALIGNMENT_MAP_SCHEMA = (
    "https://contracts.asklegal.local/v1/hk-legislation-bilingual-alignment-map.schema.json"
)
CANONICAL_TREE_CONTRACT_VERSION = "1.0.0"

type AuthenticLanguage = Literal["en", "zh-Hant"]
type RefSignature = tuple[str, str, str]

_LANGUAGES = ("en", "zh-Hant")
_REF_KEYS = frozenset(("ref_type", "ref_id", "fingerprint"))
_TREE_KEYS = frozenset(
    (
        "$schema",
        "contract_version",
        "source_format",
        "language",
        "legal_item_ref",
        "root_node_id",
        "nodes",
        "source_units",
    )
)
_TREE_DRAFT_KEYS = frozenset(
    ("source_format", "language", "legal_item_ref", "root_node_id", "nodes", "source_units")
)
_NODE_KEYS = frozenset(
    (
        "tree_node_id",
        "language",
        "legal_item_ref",
        "legal_location_ref",
        "structural_type",
        "parent_node_id",
        "sibling_order",
        "owned_source_unit_ids",
        "child_node_ids",
        "node_content_fingerprint",
        "subtree_fingerprint",
    )
)
_NODE_DRAFT_KEYS = frozenset(
    (
        "tree_node_id",
        "legal_location_ref",
        "structural_type",
        "parent_node_id",
        "sibling_order",
        "owned_source_unit_ids",
        "child_node_ids",
    )
)
_SOURCE_UNIT_KEYS = frozenset(
    (
        "source_unit_id",
        "language",
        "tree_node_id",
        "legal_item_ref",
        "legal_location_ref",
        "unit_kind",
        "content",
        "asset_ref",
        "source_order",
        "content_fingerprint",
    )
)
_SOURCE_UNIT_DRAFT_KEYS = frozenset(
    (
        "source_unit_id",
        "tree_node_id",
        "legal_location_ref",
        "unit_kind",
        "content",
        "asset_ref",
        "source_order",
    )
)
_ALIGNMENT_KEYS = frozenset(("$schema", "contract_version", "legal_item_ref", "groups"))
_ALIGNMENT_GROUP_KEYS = frozenset(
    (
        "alignment_group_id",
        "legal_location_ref",
        "en_source_unit_ids",
        "zh_hant_source_unit_ids",
        "mapping_evidence_ref",
    )
)
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_LOCAL_ID = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,127}")
_STRUCTURAL_TYPES = frozenset(
    {
        "INSTRUMENT",
        "PROVISION",
        "SUBSECTION",
        "PARAGRAPH",
        "SUBPARAGRAPH",
        "SCHEDULE",
        "SCHEDULE_ITEM",
        "TABLE",
        "TABLE_ROW",
        "TABLE_CELL",
        "FORM",
        "FORM_PART",
        "FORM_FIELD",
        "NOTE",
        "HEADING",
        "TEXT_BLOCK",
        "ASSET",
    }
)
_UNIT_KINDS = frozenset(
    {
        "INSTRUMENT_TITLE",
        "INSTRUMENT_CITATION",
        "LOCATION_LOCATOR",
        "LOCATION_HEADING",
        "BODY_TEXT",
        "STRUCTURAL_LABEL",
        "TABLE_HEADER",
        "TABLE_CELL",
        "FORM_LABEL",
        "FORM_CONTROL",
        "NOTE_TEXT",
        "CROSS_REFERENCE_MARKER",
        "ASSET_REFERENCE",
    }
)
_ORDINARY_STRUCTURAL_TYPES = frozenset(
    {"INSTRUMENT", "PROVISION", "SUBSECTION", "PARAGRAPH", "SUBPARAGRAPH", "HEADING", "TEXT_BLOCK"}
)
_ORDINARY_LOCATION_UNIT_KINDS = frozenset({"LOCATION_LOCATOR", "LOCATION_HEADING", "BODY_TEXT"})
_TEXTUAL_STRUCTURAL_TYPES = _ORDINARY_STRUCTURAL_TYPES | {"NOTE"}
_TEXTUAL_LOCATION_UNIT_KINDS = _ORDINARY_LOCATION_UNIT_KINDS | {
    "STRUCTURAL_LABEL",
    "NOTE_TEXT",
}
_TABLE_STRUCTURAL_TYPES = frozenset({"TABLE", "TABLE_ROW", "TABLE_CELL"})
_TABLE_LOCATION_UNIT_KINDS = frozenset(
    {"LOCATION_LOCATOR", "LOCATION_HEADING", "TABLE_HEADER", "TABLE_CELL"}
)
_MIN_TABLE_ROWS = 2


def _checked_object(value: object) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    if not isinstance(parsed, dict):
        message = "expected JSON object"
        raise TypeError(message)
    return parsed


@dataclass(frozen=True, slots=True)
class CanonicalSourceUnit:
    """One final authentic-language unit owned by exactly one tree node."""

    source_unit_id: str
    language: AuthenticLanguage
    tree_node_id: str
    legal_item_ref: dict[str, JsonValue]
    legal_location_ref: dict[str, JsonValue]
    unit_kind: str
    content: str | None
    asset_ref: dict[str, JsonValue] | None
    source_order: int
    content_fingerprint: str

    def document(self) -> dict[str, JsonValue]:
        """Return the closed source-unit representation."""
        return _checked_object(
            {
                "source_unit_id": self.source_unit_id,
                "language": self.language,
                "tree_node_id": self.tree_node_id,
                "legal_item_ref": self.legal_item_ref,
                "legal_location_ref": self.legal_location_ref,
                "unit_kind": self.unit_kind,
                "content": self.content,
                "asset_ref": self.asset_ref,
                "source_order": self.source_order,
                "content_fingerprint": self.content_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class CanonicalTreeNode:
    """One canonical artifact-local structural node."""

    tree_node_id: str
    language: AuthenticLanguage
    legal_item_ref: dict[str, JsonValue]
    legal_location_ref: dict[str, JsonValue]
    structural_type: str
    parent_node_id: str | None
    sibling_order: int
    owned_source_unit_ids: tuple[str, ...]
    child_node_ids: tuple[str, ...]
    node_content_fingerprint: str
    subtree_fingerprint: str

    def document(self) -> dict[str, JsonValue]:
        """Return the closed canonical-node representation."""
        return _checked_object(
            {
                "tree_node_id": self.tree_node_id,
                "language": self.language,
                "legal_item_ref": self.legal_item_ref,
                "legal_location_ref": self.legal_location_ref,
                "structural_type": self.structural_type,
                "parent_node_id": self.parent_node_id,
                "sibling_order": self.sibling_order,
                "owned_source_unit_ids": list(self.owned_source_unit_ids),
                "child_node_ids": list(self.child_node_ids),
                "node_content_fingerprint": self.node_content_fingerprint,
                "subtree_fingerprint": self.subtree_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class CanonicalLanguageTree:
    """One complete canonical tree plus its separate source-unit inventory."""

    source_format: str
    language: AuthenticLanguage
    legal_item_ref: dict[str, JsonValue]
    root_node_id: str
    nodes: tuple[CanonicalTreeNode, ...]
    source_units: tuple[CanonicalSourceUnit, ...]

    def document(self) -> dict[str, JsonValue]:
        """Return the complete sealed language-tree document."""
        return _checked_object(
            {
                "$schema": CANONICAL_LANGUAGE_TREE_SCHEMA,
                "contract_version": CANONICAL_TREE_CONTRACT_VERSION,
                "source_format": self.source_format,
                "language": self.language,
                "legal_item_ref": self.legal_item_ref,
                "root_node_id": self.root_node_id,
                "nodes": [node.document() for node in self.nodes],
                "source_units": [unit.document() for unit in self.source_units],
            }
        )

    @property
    def fingerprint(self) -> str:
        """Return the verified complete-tree fingerprint."""
        return _fingerprint(self.document())


@dataclass(frozen=True, slots=True)
class BilingualAlignmentGroup:
    """One official-evidence-bound, non-similarity bilingual unit group."""

    alignment_group_id: str
    legal_location_ref: dict[str, JsonValue]
    en_source_unit_ids: tuple[str, ...]
    zh_hant_source_unit_ids: tuple[str, ...]
    mapping_evidence_ref: dict[str, JsonValue]

    def document(self) -> dict[str, JsonValue]:
        """Return the closed alignment-group representation."""
        return _checked_object(
            {
                "alignment_group_id": self.alignment_group_id,
                "legal_location_ref": self.legal_location_ref,
                "en_source_unit_ids": list(self.en_source_unit_ids),
                "zh_hant_source_unit_ids": list(self.zh_hant_source_unit_ids),
                "mapping_evidence_ref": self.mapping_evidence_ref,
            }
        )


@dataclass(frozen=True, slots=True)
class BilingualAlignmentMap:
    """Complete bilingual ownership for two canonical authentic-language trees."""

    legal_item_ref: dict[str, JsonValue]
    groups: tuple[BilingualAlignmentGroup, ...]

    def document(self) -> dict[str, JsonValue]:
        """Return the complete bilingual alignment map."""
        return _checked_object(
            {
                "$schema": BILINGUAL_ALIGNMENT_MAP_SCHEMA,
                "contract_version": CANONICAL_TREE_CONTRACT_VERSION,
                "legal_item_ref": self.legal_item_ref,
                "groups": [group.document() for group in self.groups],
            }
        )

    @property
    def fingerprint(self) -> str:
        """Return the complete alignment-map fingerprint."""
        return _fingerprint(self.document())


@dataclass(frozen=True, slots=True)
class CanonicalBilingualRender:
    """Exact ordinary-location rendering; not a Search Record or admission result."""

    legal_location_ref: dict[str, JsonValue]
    text: str
    text_fingerprint: str
    source_unit_coverage_fingerprint: str
    alignment_map_fingerprint: str

    @property
    def utf8_bytes(self) -> bytes:
        """Return exact canonical UTF-8 renderer bytes."""
        return self.text.encode("utf-8")

    def document(self) -> dict[str, JsonValue]:
        """Return the effect-free render result."""
        return _checked_object(
            {
                "legal_location_ref": self.legal_location_ref,
                "text": self.text,
                "text_fingerprint": self.text_fingerprint,
                "source_unit_coverage_fingerprint": self.source_unit_coverage_fingerprint,
                "alignment_map_fingerprint": self.alignment_map_fingerprint,
                "search_record_output": "NONE",
                "external_effects": "NONE",
            }
        )


def _fail(detail: str) -> Never:
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail)


def _fingerprint(value: JsonValue) -> str:
    return f"sha256:{sha256(canonicalize(value)).hexdigest()}"


def _raw_fingerprint(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _object(value: JsonValue | None, detail: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        _fail(detail)
    return value


def _objects(value: JsonValue | None, detail: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        _fail(detail)
    return tuple(item for item in value if isinstance(item, dict))


def _strings(value: JsonValue | None, detail: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _fail(detail)
    result = tuple(item for item in value if isinstance(item, str))
    if (nonempty and not result) or len(set(result)) != len(result):
        _fail(detail)
    return result


def _text(value: JsonValue | None, detail: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(detail)
    return value


def _integer(value: JsonValue | None, detail: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(detail)
    return value


def _expect_keys(value: dict[str, JsonValue], keys: frozenset[str], detail: str) -> None:
    if frozenset(value) != keys:
        _fail(detail)


def _local_id(value: JsonValue | None, detail: str) -> str:
    result = _text(value, detail)
    if _LOCAL_ID.fullmatch(result) is None or "/" in result or "\\" in result:
        _fail(detail)
    return result


def _fingerprint_text(value: JsonValue | None, detail: str) -> str:
    result = _text(value, detail)
    if _FINGERPRINT.fullmatch(result) is None:
        _fail(detail)
    return result


def _reference(value: JsonValue | None, detail: str) -> dict[str, JsonValue]:
    result = _object(value, detail)
    _expect_keys(result, _REF_KEYS, detail)
    _local_id(result.get("ref_type"), detail)
    _local_id(result.get("ref_id"), detail)
    _fingerprint_text(result.get("fingerprint"), detail)
    return result


def _ref_signature(value: dict[str, JsonValue]) -> RefSignature:
    return (
        _text(value.get("ref_type"), "reference type"),
        _text(value.get("ref_id"), "reference ID"),
        _text(value.get("fingerprint"), "reference fingerprint"),
    )


def _language(value: JsonValue | None, detail: str) -> AuthenticLanguage:
    result = _text(value, detail)
    if result not in _LANGUAGES:
        _fail(detail)
    return "en" if result == "en" else "zh-Hant"


def _source_text(value: JsonValue | None, detail: str) -> str:
    result = _text(value, detail)
    if (
        not is_normalized("NFC", result)
        or "\r" in result
        or result.startswith("\n")
        or result.endswith("\n")
    ):
        _fail(detail)
    if any(line.endswith((" ", "\t")) for line in result.split("\n")):
        _fail(detail)
    return result


def _source_unit_fingerprint(content: str | None, asset_ref: dict[str, JsonValue] | None) -> str:
    projection = checked_json_value(
        {"content": content} if content is not None else {"asset_ref": asset_ref}
    )
    return _fingerprint(projection)


def _parse_source_unit(
    value: dict[str, JsonValue],
    *,
    language: AuthenticLanguage,
    legal_item_ref: dict[str, JsonValue],
    final: bool,
) -> CanonicalSourceUnit:
    _expect_keys(value, _SOURCE_UNIT_KEYS if final else _SOURCE_UNIT_DRAFT_KEYS, "source unit")
    unit_language = language if not final else _language(value.get("language"), "unit language")
    unit_item = (
        legal_item_ref if not final else _reference(value.get("legal_item_ref"), "unit item")
    )
    if unit_language != language or _ref_signature(unit_item) != _ref_signature(legal_item_ref):
        _fail("source-unit tree binding")
    unit_kind = _text(value.get("unit_kind"), "unit kind")
    if unit_kind not in _UNIT_KINDS:
        _fail("unit kind")
    raw_content = value.get("content")
    raw_asset = value.get("asset_ref")
    if (raw_content is None) == (raw_asset is None):
        _fail("source unit content or asset")
    content = _source_text(raw_content, "source content") if raw_content is not None else None
    asset_ref = _reference(raw_asset, "source asset") if raw_asset is not None else None
    if unit_kind == "ASSET_REFERENCE" and asset_ref is None:
        _fail("asset unit")
    if unit_kind != "ASSET_REFERENCE" and content is None:
        _fail("text unit")
    expected_fingerprint = _source_unit_fingerprint(content, asset_ref)
    supplied_fingerprint = (
        _fingerprint_text(value.get("content_fingerprint"), "unit fingerprint")
        if final
        else expected_fingerprint
    )
    if supplied_fingerprint != expected_fingerprint:
        _fail("source-unit fingerprint")
    return CanonicalSourceUnit(
        source_unit_id=_local_id(value.get("source_unit_id"), "source unit ID"),
        language=unit_language,
        tree_node_id=_local_id(value.get("tree_node_id"), "source unit node"),
        legal_item_ref=unit_item,
        legal_location_ref=_reference(value.get("legal_location_ref"), "unit location"),
        unit_kind=unit_kind,
        content=content,
        asset_ref=asset_ref,
        source_order=_integer(value.get("source_order"), "source order"),
        content_fingerprint=supplied_fingerprint,
    )


def _parse_node(
    value: dict[str, JsonValue],
    *,
    language: AuthenticLanguage,
    legal_item_ref: dict[str, JsonValue],
    final: bool,
) -> CanonicalTreeNode:
    _expect_keys(value, _NODE_KEYS if final else _NODE_DRAFT_KEYS, "tree node")
    node_language = language if not final else _language(value.get("language"), "node language")
    node_item = (
        legal_item_ref if not final else _reference(value.get("legal_item_ref"), "node item")
    )
    if node_language != language or _ref_signature(node_item) != _ref_signature(legal_item_ref):
        _fail("tree-node tree binding")
    parent = value.get("parent_node_id")
    if parent is not None:
        parent = _local_id(parent, "parent node")
    structural_type = _text(value.get("structural_type"), "structural type")
    if structural_type not in _STRUCTURAL_TYPES:
        _fail("structural type")
    return CanonicalTreeNode(
        tree_node_id=_local_id(value.get("tree_node_id"), "tree node ID"),
        language=node_language,
        legal_item_ref=node_item,
        legal_location_ref=_reference(value.get("legal_location_ref"), "node location"),
        structural_type=structural_type,
        parent_node_id=parent,
        sibling_order=_integer(value.get("sibling_order"), "sibling order"),
        owned_source_unit_ids=_strings(value.get("owned_source_unit_ids"), "owned units"),
        child_node_ids=_strings(value.get("child_node_ids"), "child nodes"),
        node_content_fingerprint=(
            _fingerprint_text(value.get("node_content_fingerprint"), "node content fingerprint")
            if final
            else ""
        ),
        subtree_fingerprint=(
            _fingerprint_text(value.get("subtree_fingerprint"), "subtree fingerprint")
            if final
            else ""
        ),
    )


def _validate_node_graph(
    nodes: tuple[CanonicalTreeNode, ...],
    units: tuple[CanonicalSourceUnit, ...],
    by_node: dict[str, CanonicalTreeNode],
    by_unit: dict[str, CanonicalSourceUnit],
) -> None:
    for node in nodes:
        if node.parent_node_id is not None and node.parent_node_id not in by_node:
            _fail("tree parent")
        actual_children = tuple(
            child.tree_node_id
            for child in sorted(
                (candidate for candidate in nodes if candidate.parent_node_id == node.tree_node_id),
                key=lambda candidate: candidate.sibling_order,
            )
        )
        if actual_children != node.child_node_ids:
            _fail("tree child inventory")
        if tuple(range(len(actual_children))) != tuple(
            by_node[item].sibling_order for item in actual_children
        ):
            _fail("sibling order")
        owned = tuple(
            unit.source_unit_id for unit in units if unit.tree_node_id == node.tree_node_id
        )
        if owned != node.owned_source_unit_ids:
            _fail("node source-unit ownership")
        if tuple(range(len(owned))) != tuple(by_unit[item].source_order for item in owned):
            _fail("source-unit order")
        for unit_id in owned:
            unit = by_unit[unit_id]
            if _ref_signature(unit.legal_location_ref) != _ref_signature(node.legal_location_ref):
                _fail("source-unit location ownership")


def _canonical_node_order(
    root_node_id: str,
    by_node: dict[str, CanonicalTreeNode],
) -> tuple[str, ...]:
    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting or node_id in ordered:
            _fail("tree cycle or duplicate")
        visiting.add(node_id)
        ordered.append(node_id)
        for child_id in by_node[node_id].child_node_ids:
            visit(child_id)
        visiting.remove(node_id)

    visit(root_node_id)
    return tuple(ordered)


def _validate_tree_graph(
    nodes: tuple[CanonicalTreeNode, ...],
    units: tuple[CanonicalSourceUnit, ...],
    root_node_id: str,
) -> tuple[dict[str, CanonicalTreeNode], dict[str, CanonicalSourceUnit]]:
    by_node = {node.tree_node_id: node for node in nodes}
    by_unit = {unit.source_unit_id: unit for unit in units}
    if not nodes or len(by_node) != len(nodes) or len(by_unit) != len(units):
        _fail("tree inventory")
    roots = [node for node in nodes if node.parent_node_id is None]
    if len(roots) != 1 or roots[0].tree_node_id != root_node_id:
        _fail("tree root")
    _validate_node_graph(nodes, units, by_node, by_unit)
    if any(unit.tree_node_id not in by_node for unit in units):
        _fail("orphan source unit")
    if _canonical_node_order(root_node_id, by_node) != tuple(node.tree_node_id for node in nodes):
        _fail("canonical tree order")
    if tuple(unit.source_unit_id for unit in units) != tuple(
        unit_id for node in nodes for unit_id in node.owned_source_unit_ids
    ):
        _fail("canonical source-unit order")
    return by_node, by_unit


def _node_fingerprints(
    node: CanonicalTreeNode,
    by_node: dict[str, CanonicalTreeNode],
    by_unit: dict[str, CanonicalSourceUnit],
    cache: dict[str, tuple[str, str]],
) -> tuple[str, str]:
    cached = cache.get(node.tree_node_id)
    if cached is not None:
        return cached
    content = _fingerprint(
        checked_json_value(
            {
                "tree_node_id": node.tree_node_id,
                "owned_source_units": [
                    {
                        "source_unit_id": unit_id,
                        "content_fingerprint": by_unit[unit_id].content_fingerprint,
                    }
                    for unit_id in node.owned_source_unit_ids
                ],
            }
        )
    )
    children = [
        {
            "tree_node_id": child_id,
            "subtree_fingerprint": _node_fingerprints(by_node[child_id], by_node, by_unit, cache)[
                1
            ],
        }
        for child_id in node.child_node_ids
    ]
    subtree = _fingerprint(
        checked_json_value(
            {
                "tree_node_id": node.tree_node_id,
                "legal_location_ref": node.legal_location_ref,
                "structural_type": node.structural_type,
                "parent_node_id": node.parent_node_id,
                "sibling_order": node.sibling_order,
                "node_content_fingerprint": content,
                "children": children,
            }
        )
    )
    cache[node.tree_node_id] = content, subtree
    return content, subtree


def _validate_or_seal_fingerprints(
    nodes: tuple[CanonicalTreeNode, ...],
    by_node: dict[str, CanonicalTreeNode],
    by_unit: dict[str, CanonicalSourceUnit],
    *,
    final: bool,
) -> tuple[CanonicalTreeNode, ...]:
    cache: dict[str, tuple[str, str]] = {}
    sealed: list[CanonicalTreeNode] = []
    for node in nodes:
        content, subtree = _node_fingerprints(node, by_node, by_unit, cache)
        if final and (
            node.node_content_fingerprint != content or node.subtree_fingerprint != subtree
        ):
            _fail("tree-node fingerprint")
        sealed.append(
            CanonicalTreeNode(
                tree_node_id=node.tree_node_id,
                language=node.language,
                legal_item_ref=node.legal_item_ref,
                legal_location_ref=node.legal_location_ref,
                structural_type=node.structural_type,
                parent_node_id=node.parent_node_id,
                sibling_order=node.sibling_order,
                owned_source_unit_ids=node.owned_source_unit_ids,
                child_node_ids=node.child_node_ids,
                node_content_fingerprint=content,
                subtree_fingerprint=subtree,
            )
        )
    return tuple(sealed)


@dataclass(frozen=True, slots=True)
class _TreeParts:
    source_format: str
    language: AuthenticLanguage
    legal_item_ref: dict[str, JsonValue]
    root_node_id: str
    nodes: tuple[CanonicalTreeNode, ...]
    units: tuple[CanonicalSourceUnit, ...]


def _tree_from_parts(parts: _TreeParts, *, final: bool) -> CanonicalLanguageTree:
    by_node, by_unit = _validate_tree_graph(parts.nodes, parts.units, parts.root_node_id)
    sealed_nodes = _validate_or_seal_fingerprints(parts.nodes, by_node, by_unit, final=final)
    return CanonicalLanguageTree(
        source_format=parts.source_format,
        language=parts.language,
        legal_item_ref=parts.legal_item_ref,
        root_node_id=parts.root_node_id,
        nodes=sealed_nodes,
        source_units=parts.units,
    )


def seal_canonical_language_tree(draft: dict[str, JsonValue]) -> CanonicalLanguageTree:
    """Seal one source-neutral draft with derived content and subtree hashes."""
    _expect_keys(draft, _TREE_DRAFT_KEYS, "canonical tree draft")
    source_format = _local_id(draft.get("source_format"), "source format")
    language = _language(draft.get("language"), "tree language")
    legal_item_ref = _reference(draft.get("legal_item_ref"), "legal item")
    root_node_id = _local_id(draft.get("root_node_id"), "root node")
    nodes = tuple(
        _parse_node(node, language=language, legal_item_ref=legal_item_ref, final=False)
        for node in _objects(draft.get("nodes"), "tree nodes")
    )
    units = tuple(
        _parse_source_unit(unit, language=language, legal_item_ref=legal_item_ref, final=False)
        for unit in _objects(draft.get("source_units"), "source units")
    )
    return _tree_from_parts(
        _TreeParts(source_format, language, legal_item_ref, root_node_id, nodes, units),
        final=False,
    )


def parse_canonical_language_tree(document: dict[str, JsonValue]) -> CanonicalLanguageTree:
    """Parse and independently verify one fully sealed canonical tree."""
    _expect_keys(document, _TREE_KEYS, "canonical language tree")
    if (
        document.get("$schema") != CANONICAL_LANGUAGE_TREE_SCHEMA
        or document.get("contract_version") != CANONICAL_TREE_CONTRACT_VERSION
    ):
        _fail("canonical tree contract")
    source_format = _local_id(document.get("source_format"), "source format")
    language = _language(document.get("language"), "tree language")
    legal_item_ref = _reference(document.get("legal_item_ref"), "legal item")
    root_node_id = _local_id(document.get("root_node_id"), "root node")
    nodes = tuple(
        _parse_node(node, language=language, legal_item_ref=legal_item_ref, final=True)
        for node in _objects(document.get("nodes"), "tree nodes")
    )
    units = tuple(
        _parse_source_unit(unit, language=language, legal_item_ref=legal_item_ref, final=True)
        for unit in _objects(document.get("source_units"), "source units")
    )
    return _tree_from_parts(
        _TreeParts(source_format, language, legal_item_ref, root_node_id, nodes, units),
        final=True,
    )


def canonical_language_tree_fingerprint(document: dict[str, JsonValue]) -> str:
    """Return the hash only after complete independent tree verification."""
    return parse_canonical_language_tree(document).fingerprint


def canonical_source_unit_inventory_fingerprint(
    document: dict[str, JsonValue],
) -> str:
    """Hash the verified complete ordered source-unit inventory of one tree."""
    tree = parse_canonical_language_tree(document)
    return _fingerprint([unit.document() for unit in tree.source_units])


def _parse_alignment_groups(document: dict[str, JsonValue]) -> tuple[BilingualAlignmentGroup, ...]:
    groups: list[BilingualAlignmentGroup] = []
    seen_group_ids: set[str] = set()
    for raw in _objects(document.get("groups"), "alignment groups"):
        _expect_keys(raw, _ALIGNMENT_GROUP_KEYS, "alignment group")
        group = BilingualAlignmentGroup(
            alignment_group_id=_local_id(raw.get("alignment_group_id"), "alignment group ID"),
            legal_location_ref=_reference(raw.get("legal_location_ref"), "alignment location"),
            en_source_unit_ids=_strings(
                raw.get("en_source_unit_ids"), "English group", nonempty=True
            ),
            zh_hant_source_unit_ids=_strings(
                raw.get("zh_hant_source_unit_ids"), "Chinese group", nonempty=True
            ),
            mapping_evidence_ref=_reference(raw.get("mapping_evidence_ref"), "mapping evidence"),
        )
        if group.alignment_group_id in seen_group_ids:
            _fail("duplicate alignment group")
        seen_group_ids.add(group.alignment_group_id)
        groups.append(group)
    if not groups:
        _fail("alignment groups")
    return tuple(groups)


def _validate_alignment_coverage(
    groups: tuple[BilingualAlignmentGroup, ...],
    en_tree: CanonicalLanguageTree,
    zh_hant_tree: CanonicalLanguageTree,
) -> None:
    en_units = {unit.source_unit_id: unit for unit in en_tree.source_units}
    zh_units = {unit.source_unit_id: unit for unit in zh_hant_tree.source_units}
    seen_en: list[str] = []
    seen_zh: list[str] = []
    for group in groups:
        if any(unit_id not in en_units for unit_id in group.en_source_unit_ids) or any(
            unit_id not in zh_units for unit_id in group.zh_hant_source_unit_ids
        ):
            _fail("alignment source unit")
        location = _ref_signature(group.legal_location_ref)
        if any(
            _ref_signature(en_units[item].legal_location_ref) != location
            for item in group.en_source_unit_ids
        ):
            _fail("English alignment location")
        if any(
            _ref_signature(zh_units[item].legal_location_ref) != location
            for item in group.zh_hant_source_unit_ids
        ):
            _fail("Chinese alignment location")
        seen_en.extend(group.en_source_unit_ids)
        seen_zh.extend(group.zh_hant_source_unit_ids)
    if tuple(seen_en) != tuple(en_units) or tuple(seen_zh) != tuple(zh_units):
        _fail("complete bilingual alignment coverage")


def parse_bilingual_alignment_map(
    document: dict[str, JsonValue],
    *,
    en_tree: CanonicalLanguageTree,
    zh_hant_tree: CanonicalLanguageTree,
) -> BilingualAlignmentMap:
    """Verify complete official-evidence-bound bilingual source-unit ownership."""
    _expect_keys(document, _ALIGNMENT_KEYS, "bilingual alignment map")
    if (
        document.get("$schema") != BILINGUAL_ALIGNMENT_MAP_SCHEMA
        or document.get("contract_version") != CANONICAL_TREE_CONTRACT_VERSION
    ):
        _fail("alignment contract")
    legal_item_ref = _reference(document.get("legal_item_ref"), "alignment legal item")
    item_signature = _ref_signature(legal_item_ref)
    if (
        en_tree.language != "en"
        or zh_hant_tree.language != "zh-Hant"
        or _ref_signature(en_tree.legal_item_ref) != item_signature
        or _ref_signature(zh_hant_tree.legal_item_ref) != item_signature
    ):
        _fail("alignment tree binding")
    groups = _parse_alignment_groups(document)
    _validate_alignment_coverage(groups, en_tree, zh_hant_tree)
    return BilingualAlignmentMap(legal_item_ref=legal_item_ref, groups=groups)


def _single_unit(tree: CanonicalLanguageTree, kind: str) -> CanonicalSourceUnit:
    matches = [unit for unit in tree.source_units if unit.unit_kind == kind]
    if len(matches) != 1 or matches[0].content is None:
        _fail(f"single {kind}")
    return matches[0]


def _optional_single_unit(
    tree: CanonicalLanguageTree,
    kind: str,
    location: RefSignature | None = None,
) -> CanonicalSourceUnit | None:
    matches = [
        unit
        for unit in tree.source_units
        if unit.unit_kind == kind
        and (location is None or _ref_signature(unit.legal_location_ref) == location)
    ]
    if len(matches) > 1 or (matches and matches[0].content is None):
        _fail(f"optional {kind}")
    return matches[0] if matches else None


def _unit_content(unit: CanonicalSourceUnit) -> str:
    if unit.content is None:
        _fail("ordinary renderer text content")
    return unit.content


def _table_row_units(
    nodes: dict[str, CanonicalTreeNode],
    units: dict[str, CanonicalSourceUnit],
    row: CanonicalTreeNode,
) -> tuple[CanonicalSourceUnit, ...]:
    if row.owned_source_unit_ids:
        _fail("table renderer row ownership")
    cells = [nodes.get(node_id) for node_id in row.child_node_ids]
    if not cells or any(
        cell is None
        or cell.structural_type != "TABLE_CELL"
        or len(cell.owned_source_unit_ids) != 1
        or cell.child_node_ids
        for cell in cells
    ):
        _fail("table renderer cells")
    return tuple(units[cell.owned_source_unit_ids[0]] for cell in cells if cell is not None)


def _render_table_row(
    language: AuthenticLanguage,
    row_number: int,
    headers: tuple[CanonicalSourceUnit, ...],
    cells: tuple[CanonicalSourceUnit, ...],
) -> str:
    if len(cells) != len(headers) or any(unit.unit_kind != "TABLE_CELL" for unit in cells):
        _fail("table renderer rectangular row")
    if language == "en":
        lines = [f"Row: {row_number}"]
        lines.extend(
            f"{_unit_content(header)}: {_unit_content(cell)}"
            for header, cell in zip(headers, cells, strict=True)
        )
        return "\n".join(lines)
    fullwidth_colon = "\uff1a"
    lines = [f"行{fullwidth_colon}{row_number}"]
    lines.extend(
        f"{_unit_content(header)}{fullwidth_colon}{_unit_content(cell)}"
        for header, cell in zip(headers, cells, strict=True)
    )
    return "\n".join(lines)


def _render_table_body(
    tree: CanonicalLanguageTree,
    location_nodes: list[CanonicalTreeNode],
    heading: CanonicalSourceUnit,
) -> str:
    nodes = {node.tree_node_id: node for node in location_nodes}
    units = {unit.source_unit_id: unit for unit in tree.source_units}
    tables = [node for node in location_nodes if node.structural_type == "TABLE"]
    if len(tables) != 1:
        _fail("table renderer root")
    table = tables[0]
    rows = [nodes.get(node_id) for node_id in table.child_node_ids]
    if len(rows) < _MIN_TABLE_ROWS or any(
        row is None or row.structural_type != "TABLE_ROW" for row in rows
    ):
        _fail("table renderer rows")
    verified_rows = tuple(row for row in rows if row is not None)
    header_units = _table_row_units(nodes, units, verified_rows[0])
    if any(unit.unit_kind != "TABLE_HEADER" for unit in header_units):
        _fail("table renderer headers")
    data_rows = verified_rows[1:]
    rendered_rows = [
        _render_table_row(
            tree.language,
            row_number,
            header_units,
            _table_row_units(nodes, units, row),
        )
        for row_number, row in enumerate(data_rows, start=1)
    ]
    title = _unit_content(heading)
    if tree.language == "en":
        return f"[Table]\nTitle: {title}\n\n" + "\n\n".join(rendered_rows)
    fullwidth_colon = "\uff1a"
    return f"[表格]\n標題{fullwidth_colon}{title}\n\n" + "\n\n".join(rendered_rows)


def _textual_location_content(
    location_nodes: list[CanonicalTreeNode],
    location_units: list[CanonicalSourceUnit],
) -> tuple[CanonicalSourceUnit, str | None, str]:
    if any(node.structural_type not in _TEXTUAL_STRUCTURAL_TYPES for node in location_nodes):
        _fail("ordinary renderer unsupported structure")
    if any(unit.unit_kind not in _TEXTUAL_LOCATION_UNIT_KINDS for unit in location_units):
        _fail("ordinary renderer unsupported source unit")
    locator = [unit for unit in location_units if unit.unit_kind == "LOCATION_LOCATOR"]
    heading = [unit for unit in location_units if unit.unit_kind == "LOCATION_HEADING"]
    body = [
        unit
        for unit in location_units
        if unit.unit_kind in {"BODY_TEXT", "STRUCTURAL_LABEL", "NOTE_TEXT"}
    ]
    if len(locator) != 1 or not body or len(heading) > 1:
        _fail("ordinary renderer location shape")
    heading_text = _unit_content(heading[0]) if heading else None
    return locator[0], heading_text, "\n".join(_unit_content(unit) for unit in body)


def _table_location_content(
    tree: CanonicalLanguageTree,
    location_nodes: list[CanonicalTreeNode],
    location_units: list[CanonicalSourceUnit],
) -> tuple[CanonicalSourceUnit, None, str]:
    if any(node.structural_type not in _TABLE_STRUCTURAL_TYPES for node in location_nodes):
        _fail("ordinary renderer unsupported structure")
    if any(unit.unit_kind not in _TABLE_LOCATION_UNIT_KINDS for unit in location_units):
        _fail("ordinary renderer unsupported source unit")
    locator = [unit for unit in location_units if unit.unit_kind == "LOCATION_LOCATOR"]
    heading = [unit for unit in location_units if unit.unit_kind == "LOCATION_HEADING"]
    table_content = [
        unit for unit in location_units if unit.unit_kind in {"TABLE_HEADER", "TABLE_CELL"}
    ]
    if len(locator) != 1 or len(heading) != 1 or not table_content:
        _fail("ordinary renderer location shape")
    return locator[0], None, _render_table_body(tree, location_nodes, heading[0])


def _render_language_location(
    tree: CanonicalLanguageTree,
    location_ref: dict[str, JsonValue],
) -> tuple[str, tuple[str, ...]]:
    location = _ref_signature(location_ref)
    location_nodes = [
        node for node in tree.nodes if _ref_signature(node.legal_location_ref) == location
    ]
    if not location_nodes:
        _fail("ordinary renderer unsupported structure")
    location_units = [
        unit for unit in tree.source_units if _ref_signature(unit.legal_location_ref) == location
    ]
    if not location_units:
        _fail("ordinary renderer unsupported source unit")
    table_location = all(node.structural_type in _TABLE_STRUCTURAL_TYPES for node in location_nodes)
    locator, heading_text, body_text = (
        _table_location_content(tree, location_nodes, location_units)
        if table_location
        else _textual_location_content(location_nodes, location_units)
    )
    title = _single_unit(tree, "INSTRUMENT_TITLE")
    citation = _optional_single_unit(tree, "INSTRUMENT_CITATION")
    required = [title, *([citation] if citation is not None else []), *location_units]
    if any(unit.content is None for unit in required):
        _fail("ordinary renderer text content")
    title_text = _unit_content(title)
    locator_text = _unit_content(locator)
    citation_text = _unit_content(citation) if citation is not None else None
    if tree.language == "en":
        instrument_line = f"Instrument: {title_text}"
        if citation_text is not None:
            instrument_line += f" ({citation_text})"
        lines = ["[English — Authentic Text]", instrument_line, f"Provision: {locator_text}"]
        if heading_text is not None:
            lines.append(f"Heading: {heading_text}")
        lines.extend(("Text:", body_text))
    else:
        fullwidth_colon = "\uff1a"
        instrument_line = f"法例{fullwidth_colon}{title_text}"
        if citation_text is not None:
            instrument_line += f"\uff08{citation_text}\uff09"
        lines = [
            "[繁體中文 — 真確文本]",
            instrument_line,
            f"條文{fullwidth_colon}{locator_text}",
        ]
        if heading_text is not None:
            lines.append(f"標題{fullwidth_colon}{heading_text}")
        lines.extend((f"正文{fullwidth_colon}", body_text))
    return "\n".join(lines), tuple(unit.source_unit_id for unit in required)


def render_canonical_bilingual_location(
    *,
    en_tree: CanonicalLanguageTree,
    zh_hant_tree: CanonicalLanguageTree,
    alignment_map: BilingualAlignmentMap,
    legal_location_ref: dict[str, JsonValue],
) -> CanonicalBilingualRender:
    """Render one supported textual bilingual Legal Location under ADR 0021.

    This function performs no source reconciliation, legal-status decision,
    partitioning, Search Record creation, embedding, or external effect.
    """
    item_signature = _ref_signature(en_tree.legal_item_ref)
    if (
        en_tree.language != "en"
        or zh_hant_tree.language != "zh-Hant"
        or _ref_signature(zh_hant_tree.legal_item_ref) != item_signature
        or _ref_signature(alignment_map.legal_item_ref) != item_signature
    ):
        _fail("bilingual render binding")
    en_text, en_ids = _render_language_location(en_tree, legal_location_ref)
    zh_text, zh_ids = _render_language_location(zh_hant_tree, legal_location_ref)
    covered_en = {item for group in alignment_map.groups for item in group.en_source_unit_ids}
    covered_zh = {item for group in alignment_map.groups for item in group.zh_hant_source_unit_ids}
    if not set(en_ids).issubset(covered_en) or not set(zh_ids).issubset(covered_zh):
        _fail("rendered bilingual coverage")
    text_value = f"{en_text}\n\n{zh_text}"
    if text_value.startswith("\n") or text_value.endswith("\n") or "\r" in text_value:
        _fail("canonical renderer bytes")
    coverage = _fingerprint(
        {"en_source_unit_ids": list(en_ids), "zh_hant_source_unit_ids": list(zh_ids)}
    )
    return CanonicalBilingualRender(
        legal_location_ref=legal_location_ref,
        text=text_value,
        text_fingerprint=_raw_fingerprint(text_value.encode("utf-8")),
        source_unit_coverage_fingerprint=coverage,
        alignment_map_fingerprint=alignment_map.fingerprint,
    )
