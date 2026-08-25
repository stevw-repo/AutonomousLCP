"""Source-neutral recursive Hong Kong legislation serving partitioning.

This module begins only after authentic-language trees and their official
bilingual alignment have been admitted.  It does not parse HKeL, select a
tokenizer, issue Search Record identities, or perform an external effect.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Never, Protocol

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_canonical_legislation import (
    BilingualAlignmentGroup,
    BilingualAlignmentMap,
    CanonicalLanguageTree,
    CanonicalSourceUnit,
    CanonicalTreeNode,
    render_canonical_bilingual_location,
)
from .model import RulebookError, RulebookErrorCode

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROFILE_ID = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")
_NODE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
_SUPPORTED_STATE = "SUPPORTED"
_UNKNOWN_STATE = "UNKNOWN"
_MIN_PARTITIONED_PARTS = 2
_MIN_BATCH_LOCATIONS = 2
_SIX_FIELDS = frozenset({"authority_note", "country", "jurisdiction", "source", "text", "type"})


class PartitionDisposition(StrEnum):
    """Closed effect-free result of one partition attempt."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


class PartitionReason(StrEnum):
    """Stable source-neutral ADR 0040 result codes."""

    BILINGUAL_ALIGNMENT_MISMATCH = "BILINGUAL_ALIGNMENT_MISMATCH"
    CANONICAL_PARTITION_DEFECT = "CANONICAL_PARTITION_DEFECT"
    PASS_PARTITIONED = "PASS_PARTITIONED"
    PASS_UNSPLIT = "PASS_UNSPLIT"
    SMALLEST_DEPENDENT_BRANCH_OVER_LIMIT = "SMALLEST_DEPENDENT_BRANCH_OVER_LIMIT"
    SOURCE_CONTRACT_REVIEW_REQUIRED = "SOURCE_CONTRACT_REVIEW_REQUIRED"
    SOURCE_LOCATION_OWNERSHIP_DEFECT = "SOURCE_LOCATION_OWNERSHIP_DEFECT"
    SOURCE_UNIT_COVERAGE_DEFECT = "SOURCE_UNIT_COVERAGE_DEFECT"


class PartitionBatchReason(StrEnum):
    """Stable result code for the cross-location non-merging boundary."""

    LOCATIONS_PROCESSED_SEPARATELY = "LOCATIONS_PROCESSED_SEPARATELY"


class ExactTokenCounter(Protocol):
    """One already pinned tokenizer implementation; estimates are forbidden."""

    profile_id: str
    profile_fingerprint: str
    tokenizer_id: str

    def count(self, text: str) -> int:
        """Count the exact final ``metadata.text`` with the pinned tokenizer."""
        ...


@dataclass(frozen=True, slots=True)
class PartitionServingProfile:
    """Exact serving and tokenizer limits used by one partition attempt."""

    profile_id: str
    profile_fingerprint: str
    tokenizer_id: str
    max_text_tokens: int
    max_metadata_bytes: int
    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str

    def document(self) -> dict[str, JsonValue]:
        """Return the exact result-affecting serving-profile document."""
        return _json_object(
            {
                "authority_note": self.authority_note,
                "country": self.country,
                "jurisdiction": self.jurisdiction,
                "material_type": self.material_type,
                "max_metadata_bytes": self.max_metadata_bytes,
                "max_text_tokens": self.max_text_tokens,
                "profile_fingerprint": self.profile_fingerprint,
                "profile_id": self.profile_id,
                "source": self.source,
                "tokenizer_id": self.tokenizer_id,
            }
        )


@dataclass(frozen=True, slots=True)
class AlignedPartitionNode:
    """One officially supported bilingual node in the recursive split tree."""

    partition_node_id: str
    en_tree_node_id: str
    zh_hant_tree_node_id: str
    primary_alignment_group_ids: tuple[str, ...]
    dependency_alignment_group_ids: tuple[str, ...]
    child_partition_node_ids: tuple[str, ...]
    source_contract_state: str = _SUPPORTED_STATE
    indivisible: bool = False

    def document(self) -> dict[str, JsonValue]:
        """Return the exact declared official bilingual partition node."""
        return _json_object(
            {
                "child_partition_node_ids": list(self.child_partition_node_ids),
                "dependency_alignment_group_ids": list(self.dependency_alignment_group_ids),
                "en_tree_node_id": self.en_tree_node_id,
                "indivisible": self.indivisible,
                "partition_node_id": self.partition_node_id,
                "primary_alignment_group_ids": list(self.primary_alignment_group_ids),
                "source_contract_state": self.source_contract_state,
                "zh_hant_tree_node_id": self.zh_hant_tree_node_id,
            }
        )


@dataclass(frozen=True, slots=True)
class BilingualPartitionRequest:
    """Complete exact input for one normal Legal Location only."""

    legal_location_ref: dict[str, JsonValue]
    en_tree_fingerprint: str
    zh_hant_tree_fingerprint: str
    alignment_map_fingerprint: str
    root_partition_node_ids: tuple[str, ...]
    nodes: tuple[AlignedPartitionNode, ...]

    def document(self) -> dict[str, JsonValue]:
        """Return the complete exact source-neutral partition request."""
        return _json_object(
            {
                "alignment_map_fingerprint": self.alignment_map_fingerprint,
                "en_tree_fingerprint": self.en_tree_fingerprint,
                "legal_location_ref": self.legal_location_ref,
                "nodes": [node.document() for node in self.nodes],
                "root_partition_node_ids": list(self.root_partition_node_ids),
                "zh_hant_tree_fingerprint": self.zh_hant_tree_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class BilingualPartitionExecution:
    """All immutable inputs needed for one effect-free partition attempt."""

    request: BilingualPartitionRequest
    profile: PartitionServingProfile
    token_counter: ExactTokenCounter
    en_tree: CanonicalLanguageTree
    zh_hant_tree: CanonicalLanguageTree
    alignment_map: BilingualAlignmentMap


@dataclass(frozen=True, slots=True)
class BilingualPartitionBatchExecution:
    """Two or more independently bound Legal Location partition attempts."""

    executions: tuple[BilingualPartitionExecution, ...]


@dataclass(frozen=True, slots=True)
class PartitionMeasurement:
    """Exact final payload measurements for one serving part."""

    text_tokens: int
    metadata_bytes: int
    text_limit: int
    metadata_limit: int

    @property
    def fits(self) -> bool:
        """Return whether both independent hard ceilings pass."""
        return self.text_tokens <= self.text_limit and self.metadata_bytes <= self.metadata_limit


@dataclass(frozen=True, slots=True)
class BilingualServingPart:
    """One effect-free final serving part, without a Search Record identity."""

    part_number: int
    total_parts: int
    primary_partition_node_ids: tuple[str, ...]
    primary_alignment_group_ids: tuple[str, ...]
    dependency_alignment_group_ids: tuple[str, ...]
    en_primary_source_unit_ids: tuple[str, ...]
    zh_hant_primary_source_unit_ids: tuple[str, ...]
    en_dependency_source_unit_ids: tuple[str, ...]
    zh_hant_dependency_source_unit_ids: tuple[str, ...]
    text: str
    text_fingerprint: str
    serving_payload_fingerprint: str
    measurement: PartitionMeasurement

    def document(self) -> dict[str, JsonValue]:
        """Return the closed deterministic serving-part proof document."""
        return _json_object(
            {
                "dependency_alignment_group_ids": list(self.dependency_alignment_group_ids),
                "en_dependency_source_unit_ids": list(self.en_dependency_source_unit_ids),
                "en_primary_source_unit_ids": list(self.en_primary_source_unit_ids),
                "measurement": {
                    "metadata_bytes": self.measurement.metadata_bytes,
                    "metadata_limit": self.measurement.metadata_limit,
                    "text_limit": self.measurement.text_limit,
                    "text_tokens": self.measurement.text_tokens,
                },
                "part_number": self.part_number,
                "primary_alignment_group_ids": list(self.primary_alignment_group_ids),
                "primary_partition_node_ids": list(self.primary_partition_node_ids),
                "serving_payload_fingerprint": self.serving_payload_fingerprint,
                "text": self.text,
                "text_fingerprint": self.text_fingerprint,
                "total_parts": self.total_parts,
                "zh_hant_dependency_source_unit_ids": list(self.zh_hant_dependency_source_unit_ids),
                "zh_hant_primary_source_unit_ids": list(self.zh_hant_primary_source_unit_ids),
            }
        )


@dataclass(frozen=True, slots=True)
class BilingualPartitionResult:
    """Canonical partition, proof, or fail-visible disposition."""

    disposition: PartitionDisposition
    reason: PartitionReason
    parts: tuple[BilingualServingPart, ...]
    quarantined_partition_node_ids: tuple[str, ...]
    coverage_gap_required: bool
    profile_id: str
    profile_fingerprint: str
    en_tree_fingerprint: str
    zh_hant_tree_fingerprint: str
    alignment_map_fingerprint: str
    canonical_bytes: bytes
    fingerprint: str

    def document(self) -> dict[str, JsonValue]:
        """Return the exact canonical result document."""
        return _json_object(
            {
                "alignment_map_fingerprint": self.alignment_map_fingerprint,
                "coverage_gap_required": self.coverage_gap_required,
                "disposition": self.disposition.value,
                "en_tree_fingerprint": self.en_tree_fingerprint,
                "external_effects": "NONE",
                "parts": [part.document() for part in self.parts],
                "profile_fingerprint": self.profile_fingerprint,
                "profile_id": self.profile_id,
                "quarantined_partition_node_ids": list(self.quarantined_partition_node_ids),
                "reason": self.reason.value,
                "search_record_output": "NONE",
                "zh_hant_tree_fingerprint": self.zh_hant_tree_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class PartitionedLegalLocation:
    """One exact Legal Location and its independently produced result."""

    legal_location_ref: dict[str, JsonValue]
    result: BilingualPartitionResult

    def document(self) -> dict[str, JsonValue]:
        """Return the location binding plus its complete partition result."""
        return _json_object(
            {
                "legal_location_ref": self.legal_location_ref,
                "partition_result": self.result.document(),
            }
        )


@dataclass(frozen=True, slots=True)
class BilingualPartitionBatchResult:
    """Fail-visible proof that Legal Locations were never combined."""

    disposition: PartitionDisposition
    reason: PartitionBatchReason
    location_results: tuple[PartitionedLegalLocation, ...]
    coverage_gap_required: bool
    parts: tuple[BilingualServingPart, ...]
    canonical_bytes: bytes
    fingerprint: str

    def document(self) -> dict[str, JsonValue]:
        """Return the exact batch proof with no cross-location serving part."""
        return _json_object(
            {
                "coverage_gap_required": self.coverage_gap_required,
                "cross_location_combination": "FORBIDDEN",
                "disposition": self.disposition.value,
                "external_effects": "NONE",
                "location_results": [item.document() for item in self.location_results],
                "parts": [],
                "reason": self.reason.value,
                "search_record_output": "NONE",
            }
        )


@dataclass(frozen=True, slots=True)
class _PartitionContext:
    request: BilingualPartitionRequest
    profile: PartitionServingProfile
    token_counter: ExactTokenCounter
    en_tree: CanonicalLanguageTree
    zh_tree: CanonicalLanguageTree
    alignment: BilingualAlignmentMap
    nodes: Mapping[str, AlignedPartitionNode]
    groups: Mapping[str, BilingualAlignmentGroup]
    group_order: Mapping[str, int]
    en_units: Mapping[str, CanonicalSourceUnit]
    zh_units: Mapping[str, CanonicalSourceUnit]


@dataclass(slots=True)
class _PartitionGraph:
    context: _PartitionContext
    location: tuple[str, str, str]
    en_nodes: Mapping[str, CanonicalTreeNode]
    zh_nodes: Mapping[str, CanonicalTreeNode]
    en_subtree_units: Mapping[str, frozenset[str]]
    zh_subtree_units: Mapping[str, frozenset[str]]
    visiting: set[str]
    visited: set[str]


@dataclass(frozen=True, slots=True)
class _LanguagePartInput:
    language: str
    title: str
    citation: str | None
    locator: str
    heading: str | None
    primary_text: str
    dependency_text: str | None
    part_number: int
    total_parts: int
    include_part_label: bool


@dataclass(frozen=True, slots=True)
class _PartitionResultSpec:
    disposition: PartitionDisposition
    reason: PartitionReason
    parts: tuple[BilingualServingPart, ...] = ()
    quarantined: tuple[str, ...] = ()
    coverage_gap_required: bool = False


class _PartitionSignal(Exception):
    """Internal fail-visible legal/processing result raised during graph proof."""

    def __init__(self, spec: _PartitionResultSpec) -> None:
        self.spec = spec
        super().__init__(spec.reason.value)


def _signal(
    disposition: PartitionDisposition,
    reason: PartitionReason,
    *,
    quarantined: tuple[str, ...] = (),
    coverage_gap_required: bool = False,
) -> Never:
    raise _PartitionSignal(
        _PartitionResultSpec(
            disposition,
            reason,
            quarantined=quarantined,
            coverage_gap_required=coverage_gap_required,
        )
    )


def _json_object(value: object) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    if not isinstance(parsed, dict):
        message = "expected JSON object"
        raise TypeError(message)
    return parsed


def _raw_fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _canonical_fingerprint(value: object) -> str:
    return _raw_fingerprint(canonicalize(checked_json_value(value)))


def _fail(detail: str) -> Never:
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail)


def partition_serving_profile_fingerprint(profile: PartitionServingProfile) -> str:
    """Fingerprint all result-affecting profile values except its claimed hash."""
    return _canonical_fingerprint(
        {
            "authority_note": profile.authority_note,
            "country": profile.country,
            "jurisdiction": profile.jurisdiction,
            "material_type": profile.material_type,
            "max_metadata_bytes": profile.max_metadata_bytes,
            "max_text_tokens": profile.max_text_tokens,
            "profile_id": profile.profile_id,
            "source": profile.source,
            "tokenizer_id": profile.tokenizer_id,
        }
    )


def _document_text(document: Mapping[str, JsonValue], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str):
        _fail(f"partition {key}")
    return value


def _document_integer(document: Mapping[str, JsonValue], key: str) -> int:
    value = document.get(key)
    if type(value) is not int:
        _fail(f"partition {key}")
    return value


def _document_strings(document: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _fail(f"partition {key}")
    return tuple(item for item in value if isinstance(item, str))


def partition_serving_profile_from_document(
    document: dict[str, JsonValue],
) -> PartitionServingProfile:
    """Parse one strict package-bound serving profile without repairing it."""
    expected = frozenset(
        {
            "authority_note",
            "country",
            "jurisdiction",
            "material_type",
            "max_metadata_bytes",
            "max_text_tokens",
            "profile_fingerprint",
            "profile_id",
            "source",
            "tokenizer_id",
        }
    )
    if frozenset(document) != expected:
        _fail("partition serving profile fields")
    return PartitionServingProfile(
        _document_text(document, "profile_id"),
        _document_text(document, "profile_fingerprint"),
        _document_text(document, "tokenizer_id"),
        _document_integer(document, "max_text_tokens"),
        _document_integer(document, "max_metadata_bytes"),
        _document_text(document, "country"),
        _document_text(document, "jurisdiction"),
        _document_text(document, "material_type"),
        _document_text(document, "source"),
        _document_text(document, "authority_note"),
    )


def bilingual_partition_request_from_document(
    document: dict[str, JsonValue],
) -> BilingualPartitionRequest:
    """Parse one strict package-bound bilingual partition request."""
    expected = frozenset(
        {
            "alignment_map_fingerprint",
            "en_tree_fingerprint",
            "legal_location_ref",
            "nodes",
            "root_partition_node_ids",
            "zh_hant_tree_fingerprint",
        }
    )
    if frozenset(document) != expected:
        _fail("partition request fields")
    legal_location_ref = document.get("legal_location_ref")
    raw_nodes = document.get("nodes")
    if not isinstance(legal_location_ref, dict) or not isinstance(raw_nodes, list):
        _fail("partition request")
    nodes: list[AlignedPartitionNode] = []
    node_fields = frozenset(
        {
            "child_partition_node_ids",
            "dependency_alignment_group_ids",
            "en_tree_node_id",
            "indivisible",
            "partition_node_id",
            "primary_alignment_group_ids",
            "source_contract_state",
            "zh_hant_tree_node_id",
        }
    )
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict) or frozenset(raw_node) != node_fields:
            _fail("partition node fields")
        indivisible = raw_node.get("indivisible")
        if type(indivisible) is not bool:
            _fail("partition indivisible")
        nodes.append(
            AlignedPartitionNode(
                _document_text(raw_node, "partition_node_id"),
                _document_text(raw_node, "en_tree_node_id"),
                _document_text(raw_node, "zh_hant_tree_node_id"),
                _document_strings(raw_node, "primary_alignment_group_ids"),
                _document_strings(raw_node, "dependency_alignment_group_ids"),
                _document_strings(raw_node, "child_partition_node_ids"),
                _document_text(raw_node, "source_contract_state"),
                indivisible,
            )
        )
    return BilingualPartitionRequest(
        legal_location_ref,
        _document_text(document, "en_tree_fingerprint"),
        _document_text(document, "zh_hant_tree_fingerprint"),
        _document_text(document, "alignment_map_fingerprint"),
        _document_strings(document, "root_partition_node_ids"),
        tuple(nodes),
    )


def _validate_profile(profile: PartitionServingProfile, counter: ExactTokenCounter) -> None:
    strings = (
        profile.profile_id,
        profile.profile_fingerprint,
        profile.tokenizer_id,
        profile.country,
        profile.jurisdiction,
        profile.material_type,
        profile.source,
        profile.authority_note,
    )
    if (
        type(profile) is not PartitionServingProfile
        or any(not item or item.strip() != item for item in strings)
        or _PROFILE_ID.fullmatch(profile.profile_id) is None
        or _FINGERPRINT.fullmatch(profile.profile_fingerprint) is None
        or profile.profile_fingerprint != partition_serving_profile_fingerprint(profile)
        or type(profile.max_text_tokens) is not int
        or type(profile.max_metadata_bytes) is not int
        or profile.max_text_tokens < 1
        or profile.max_metadata_bytes < 1
        or counter.profile_id != profile.profile_id
        or counter.profile_fingerprint != profile.profile_fingerprint
        or counter.tokenizer_id != profile.tokenizer_id
    ):
        _fail("partition serving profile")


def _ref_signature(reference: Mapping[str, JsonValue]) -> tuple[str, str, str]:
    ref_type = reference.get("ref_type")
    ref_id = reference.get("ref_id")
    fingerprint = reference.get("fingerprint")
    if (
        not isinstance(ref_type, str)
        or not isinstance(ref_id, str)
        or not isinstance(fingerprint, str)
    ):
        _fail("partition reference")
    return ref_type, ref_id, fingerprint


def _unit_text(unit: CanonicalSourceUnit) -> str:
    if unit.content is None:
        _fail("partition cannot render an asset")
    return unit.content


def _single_text_unit(
    tree: CanonicalLanguageTree,
    kind: str,
    location: tuple[str, str, str] | None = None,
    *,
    optional: bool = False,
) -> CanonicalSourceUnit | None:
    matches = [
        unit
        for unit in tree.source_units
        if unit.unit_kind == kind
        and (location is None or _ref_signature(unit.legal_location_ref) == location)
    ]
    expected = (0, 1) if optional else (1,)
    if len(matches) not in expected or any(unit.content is None for unit in matches):
        _fail(f"partition {kind}")
    return matches[0] if matches else None


def _validate_request(
    execution: BilingualPartitionExecution,
) -> tuple[_PartitionContext, _PartitionResultSpec | None]:
    request = execution.request
    profile = execution.profile
    token_counter = execution.token_counter
    en_tree = execution.en_tree
    zh_tree = execution.zh_hant_tree
    alignment = execution.alignment_map
    _validate_profile(profile, token_counter)
    location = _ref_signature(request.legal_location_ref)
    if (
        type(request) is not BilingualPartitionRequest
        or request.en_tree_fingerprint != en_tree.fingerprint
        or request.zh_hant_tree_fingerprint != zh_tree.fingerprint
        or request.alignment_map_fingerprint != alignment.fingerprint
        or en_tree.language != "en"
        or zh_tree.language != "zh-Hant"
        or _ref_signature(en_tree.legal_item_ref) != _ref_signature(zh_tree.legal_item_ref)
        or _ref_signature(en_tree.legal_item_ref) != _ref_signature(alignment.legal_item_ref)
    ):
        _fail("partition immutable binding")
    nodes = {node.partition_node_id: node for node in request.nodes}
    groups = {group.alignment_group_id: group for group in alignment.groups}
    if (
        not request.root_partition_node_ids
        or len(nodes) != len(request.nodes)
        or len(groups) != len(alignment.groups)
        or any(_NODE_ID.fullmatch(node_id) is None for node_id in nodes)
        or set(request.root_partition_node_ids) - set(nodes)
    ):
        _fail("partition inventory")
    context = _PartitionContext(
        request,
        profile,
        token_counter,
        en_tree,
        zh_tree,
        alignment,
        nodes,
        groups,
        {group.alignment_group_id: index for index, group in enumerate(alignment.groups)},
        {unit.source_unit_id: unit for unit in en_tree.source_units},
        {unit.source_unit_id: unit for unit in zh_tree.source_units},
    )
    try:
        _validate_partition_graph(context, location)
    except _PartitionSignal as signal:
        return context, signal.spec
    return context, None


def _validate_partition_node(graph: _PartitionGraph, node: AlignedPartitionNode) -> None:
    context = graph.context
    if (
        node.source_contract_state not in {_SUPPORTED_STATE, _UNKNOWN_STATE}
        or type(node.indivisible) is not bool
        or node.en_tree_node_id not in graph.en_nodes
        or node.zh_hant_tree_node_id not in graph.zh_nodes
        or len(node.primary_alignment_group_ids) != len(set(node.primary_alignment_group_ids))
        or len(node.dependency_alignment_group_ids) != len(set(node.dependency_alignment_group_ids))
        or set(node.primary_alignment_group_ids) & set(node.dependency_alignment_group_ids)
        or set(node.primary_alignment_group_ids) | set(node.dependency_alignment_group_ids)
        > set(context.groups)
    ):
        _fail("partition node")
    en_location = _ref_signature(graph.en_nodes[node.en_tree_node_id].legal_location_ref)
    zh_location = _ref_signature(graph.zh_nodes[node.zh_hant_tree_node_id].legal_location_ref)
    if graph.location not in (en_location, zh_location):
        _signal(
            PartitionDisposition.BLOCK,
            PartitionReason.SOURCE_LOCATION_OWNERSHIP_DEFECT,
        )
    if en_location != graph.location or zh_location != graph.location:
        _signal(
            PartitionDisposition.QUARANTINE,
            PartitionReason.BILINGUAL_ALIGNMENT_MISMATCH,
            quarantined=(node.partition_node_id,),
            coverage_gap_required=True,
        )
    _require_group_order(context, node.primary_alignment_group_ids)
    _require_group_order(context, node.dependency_alignment_group_ids)
    primary_en, primary_zh = _group_source_ids(context, node.primary_alignment_group_ids)
    if not set(primary_en).issubset(graph.en_subtree_units[node.en_tree_node_id]) or not set(
        primary_zh
    ).issubset(graph.zh_subtree_units[node.zh_hant_tree_node_id]):
        _signal(
            PartitionDisposition.QUARANTINE,
            PartitionReason.BILINGUAL_ALIGNMENT_MISMATCH,
            quarantined=(node.partition_node_id,),
            coverage_gap_required=True,
        )
    for group_id in (*node.primary_alignment_group_ids, *node.dependency_alignment_group_ids):
        if _ref_signature(context.groups[group_id].legal_location_ref) != graph.location:
            _signal(
                PartitionDisposition.BLOCK,
                PartitionReason.SOURCE_LOCATION_OWNERSHIP_DEFECT,
            )
    if len(node.child_partition_node_ids) != len(set(node.child_partition_node_ids)) or set(
        node.child_partition_node_ids
    ) - set(context.nodes):
        _fail("partition child inventory")


def _visit_partition_node(graph: _PartitionGraph, node_id: str) -> None:
    if node_id in graph.visiting or node_id in graph.visited:
        _fail("partition graph cycle or duplicate")
    graph.visiting.add(node_id)
    node = graph.context.nodes[node_id]
    _validate_partition_node(graph, node)
    for child_id in node.child_partition_node_ids:
        child = graph.context.nodes[child_id]
        if (
            graph.en_nodes[child.en_tree_node_id].parent_node_id != node.en_tree_node_id
            or graph.zh_nodes[child.zh_hant_tree_node_id].parent_node_id
            != node.zh_hant_tree_node_id
        ):
            _signal(
                PartitionDisposition.QUARANTINE,
                PartitionReason.BILINGUAL_ALIGNMENT_MISMATCH,
                quarantined=(child.partition_node_id,),
                coverage_gap_required=True,
            )
        _visit_partition_node(graph, child_id)
    if node.child_partition_node_ids:
        child_groups = tuple(
            group_id
            for child_id in node.child_partition_node_ids
            for group_id in graph.context.nodes[child_id].primary_alignment_group_ids
        )
        if child_groups != node.primary_alignment_group_ids:
            _signal(
                PartitionDisposition.BLOCK,
                PartitionReason.SOURCE_UNIT_COVERAGE_DEFECT,
            )
    graph.visiting.remove(node_id)
    graph.visited.add(node_id)


def _validate_partition_graph(context: _PartitionContext, location: tuple[str, str, str]) -> None:
    en_nodes = {node.tree_node_id: node for node in context.en_tree.nodes}
    zh_nodes = {node.tree_node_id: node for node in context.zh_tree.nodes}
    graph = _PartitionGraph(
        context,
        location,
        en_nodes,
        zh_nodes,
        _subtree_source_units(en_nodes),
        _subtree_source_units(zh_nodes),
        set(),
        set(),
    )
    for root_id in context.request.root_partition_node_ids:
        _visit_partition_node(graph, root_id)
    if graph.visited != set(context.nodes):
        _fail("orphan partition node")
    root_groups = tuple(
        group_id
        for root_id in context.request.root_partition_node_ids
        for group_id in context.nodes[root_id].primary_alignment_group_ids
    )
    expected_groups = tuple(
        group.alignment_group_id
        for group in context.alignment.groups
        if _ref_signature(group.legal_location_ref) == location
        and _group_is_partition_body(context, group)
    )
    if root_groups != expected_groups:
        _signal(
            PartitionDisposition.BLOCK,
            PartitionReason.SOURCE_UNIT_COVERAGE_DEFECT,
        )


def _subtree_source_units(
    nodes: Mapping[str, CanonicalTreeNode],
) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}

    def collect(node_id: str) -> frozenset[str]:
        cached = result.get(node_id)
        if cached is not None:
            return cached
        node = nodes[node_id]
        collected = frozenset(
            (
                *node.owned_source_unit_ids,
                *(unit_id for child_id in node.child_node_ids for unit_id in collect(child_id)),
            )
        )
        result[node_id] = collected
        return collected

    for node_id in nodes:
        collect(node_id)
    return result


def _require_group_order(context: _PartitionContext, group_ids: tuple[str, ...]) -> None:
    positions = tuple(context.group_order[group_id] for group_id in group_ids)
    if positions != tuple(sorted(positions)):
        _signal(
            PartitionDisposition.BLOCK,
            PartitionReason.SOURCE_UNIT_COVERAGE_DEFECT,
        )


def _group_is_partition_body(context: _PartitionContext, group: BilingualAlignmentGroup) -> bool:
    en_kinds = {context.en_units[unit_id].unit_kind for unit_id in group.en_source_unit_ids}
    zh_kinds = {context.zh_units[unit_id].unit_kind for unit_id in group.zh_hant_source_unit_ids}
    return bool(
        (en_kinds | zh_kinds) & {"BODY_TEXT", "STRUCTURAL_LABEL", "NOTE_TEXT", "TABLE_CELL"}
    ) and (en_kinds == zh_kinds)


def _group_source_ids(
    context: _PartitionContext, group_ids: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    en_ids = tuple(
        unit_id for group_id in group_ids for unit_id in context.groups[group_id].en_source_unit_ids
    )
    zh_ids = tuple(
        unit_id
        for group_id in group_ids
        for unit_id in context.groups[group_id].zh_hant_source_unit_ids
    )
    if len(en_ids) != len(set(en_ids)) or len(zh_ids) != len(set(zh_ids)):
        _signal(
            PartitionDisposition.BLOCK,
            PartitionReason.SOURCE_UNIT_COVERAGE_DEFECT,
        )
    return en_ids, zh_ids


def _ordered_union(context: _PartitionContext, groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(groups), key=context.group_order.__getitem__))


def _context_values(
    context: _PartitionContext,
) -> tuple[str, str | None, str, str | None, str, str | None, str, str | None]:
    location = _ref_signature(context.request.legal_location_ref)
    en_title = _single_text_unit(context.en_tree, "INSTRUMENT_TITLE")
    en_citation = _single_text_unit(context.en_tree, "INSTRUMENT_CITATION", optional=True)
    en_locator = _single_text_unit(context.en_tree, "LOCATION_LOCATOR", location)
    en_heading = _single_text_unit(context.en_tree, "LOCATION_HEADING", location, optional=True)
    zh_title = _single_text_unit(context.zh_tree, "INSTRUMENT_TITLE")
    zh_citation = _single_text_unit(context.zh_tree, "INSTRUMENT_CITATION", optional=True)
    zh_locator = _single_text_unit(context.zh_tree, "LOCATION_LOCATOR", location)
    zh_heading = _single_text_unit(context.zh_tree, "LOCATION_HEADING", location, optional=True)
    if en_title is None or en_locator is None or zh_title is None or zh_locator is None:
        _fail("partition location context")
    return (
        _unit_text(en_title),
        None if en_citation is None else _unit_text(en_citation),
        _unit_text(en_locator),
        None if en_heading is None else _unit_text(en_heading),
        _unit_text(zh_title),
        None if zh_citation is None else _unit_text(zh_citation),
        _unit_text(zh_locator),
        None if zh_heading is None else _unit_text(zh_heading),
    )


def _language_part(part: _LanguagePartInput) -> str:
    language = part.language
    title = part.title
    citation = part.citation
    locator = part.locator
    heading = part.heading
    primary_text = part.primary_text
    dependency_text = part.dependency_text
    part_number = part.part_number
    total_parts = part.total_parts
    include_part_label = part.include_part_label
    if language == "en":
        instrument = f"Instrument: {title}" + ("" if citation is None else f" ({citation})")
        lines = ["[English — Authentic Text]", instrument, f"Provision: {locator}"]
        if include_part_label:
            lines.append(f"Serving part: {part_number} of {total_parts}")
        if heading is not None:
            lines.append(f"Heading: {heading}")
        if dependency_text is not None:
            lines.extend(("Parent context (repeated):", dependency_text))
        lines.extend(("Text:", primary_text))
        return "\n".join(lines)
    instrument = f"法例\uff1a{title}" + ("" if citation is None else f"\uff08{citation}\uff09")
    lines = ["[繁體中文 — 真確文本]", instrument, f"條文\uff1a{locator}"]
    if include_part_label:
        lines.append(f"服務部分\uff1a第{part_number}部分\uff0c共{total_parts}部分")
    if heading is not None:
        lines.append(f"標題\uff1a{heading}")
    if dependency_text is not None:
        lines.extend(("上層脈絡\uff08重複\uff09\uff1a", dependency_text))
    lines.extend(("正文\uff1a", primary_text))
    return "\n".join(lines)


def _table_part_content(
    context: _PartitionContext,
    node_ids: tuple[str, ...],
    language: str,
    dependency_ids: tuple[str, ...],
) -> tuple[str, str] | None:
    units = context.en_units if language == "en" else context.zh_units
    primary_ids = tuple(
        unit_id
        for node_id in node_ids
        for group_id in context.nodes[node_id].primary_alignment_group_ids
        for unit_id in (
            context.groups[group_id].en_source_unit_ids
            if language == "en"
            else context.groups[group_id].zh_hant_source_unit_ids
        )
    )
    if not any(units[unit_id].unit_kind == "TABLE_CELL" for unit_id in primary_ids):
        return None
    headers = tuple(units[unit_id] for unit_id in dependency_ids)
    if not headers or any(unit.unit_kind != "TABLE_HEADER" for unit in headers):
        _fail("partition table headers")
    tree = context.en_tree if language == "en" else context.zh_tree
    tree_nodes = {node.tree_node_id: node for node in tree.nodes}
    row_blocks: list[str] = []
    fullwidth_colon = "\uff1a"
    for node_id in node_ids:
        partition_node = context.nodes[node_id]
        tree_node_id = (
            partition_node.en_tree_node_id
            if language == "en"
            else partition_node.zh_hant_tree_node_id
        )
        row = tree_nodes[tree_node_id]
        if row.structural_type != "TABLE_ROW":
            _fail("partition table row")
        row_group_ids = partition_node.primary_alignment_group_ids
        row_en_ids, row_zh_ids = _group_source_ids(context, row_group_ids)
        row_ids = row_en_ids if language == "en" else row_zh_ids
        cells = tuple(units[unit_id] for unit_id in row_ids)
        if len(cells) != len(headers) or any(unit.unit_kind != "TABLE_CELL" for unit in cells):
            _fail("partition table rectangular row")
        if language == "en":
            lines = [f"Row: {row.sibling_order}"]
            lines.extend(
                f"{_unit_text(header)}: {_unit_text(cell)}"
                for header, cell in zip(headers, cells, strict=True)
            )
        else:
            lines = [f"行{fullwidth_colon}{row.sibling_order}"]
            lines.extend(
                f"{_unit_text(header)}{fullwidth_colon}{_unit_text(cell)}"
                for header, cell in zip(headers, cells, strict=True)
            )
        row_blocks.append("\n".join(lines))
    if language == "en":
        primary_text = "[Table]\n" + "\n\n".join(row_blocks)
        dependency_text = "[Table headers]\n" + "\n".join(_unit_text(header) for header in headers)
    else:
        primary_text = "[表格]\n" + "\n\n".join(row_blocks)
        dependency_text = "[表格標題]\n" + "\n".join(_unit_text(header) for header in headers)
    return primary_text, dependency_text


def _render_part(
    context: _PartitionContext,
    node_ids: tuple[str, ...],
    part_number: int,
    total_parts: int,
    *,
    include_part_label: bool,
) -> BilingualServingPart:
    primary_groups = tuple(
        group_id
        for node_id in node_ids
        for group_id in context.nodes[node_id].primary_alignment_group_ids
    )
    dependencies = _ordered_union(
        context,
        tuple(
            group_id
            for node_id in node_ids
            for group_id in context.nodes[node_id].dependency_alignment_group_ids
            if group_id not in primary_groups
        ),
    )
    en_primary, zh_primary = _group_source_ids(context, primary_groups)
    en_dependencies, zh_dependencies = _group_source_ids(context, dependencies)
    values = _context_values(context)
    en_nodes = {node.tree_node_id: node for node in context.en_tree.nodes}
    zh_nodes = {node.tree_node_id: node for node in context.zh_tree.nodes}
    table_root = len(node_ids) == 1 and (
        en_nodes[context.nodes[node_ids[0]].en_tree_node_id].structural_type == "TABLE"
        and zh_nodes[context.nodes[node_ids[0]].zh_hant_tree_node_id].structural_type == "TABLE"
    )
    if table_root:
        text = render_canonical_bilingual_location(
            en_tree=context.en_tree,
            zh_hant_tree=context.zh_tree,
            alignment_map=context.alignment,
            legal_location_ref=context.request.legal_location_ref,
        ).text
    else:
        en_table = _table_part_content(context, node_ids, "en", en_dependencies)
        zh_table = _table_part_content(context, node_ids, "zh-Hant", zh_dependencies)
        if (en_table is None) != (zh_table is None):
            _fail("partition bilingual table content")
        en_primary_text = (
            "\n".join(_unit_text(context.en_units[item]) for item in en_primary)
            if en_table is None
            else en_table[0]
        )
        zh_primary_text = (
            "\n".join(_unit_text(context.zh_units[item]) for item in zh_primary)
            if zh_table is None
            else zh_table[0]
        )
        en_dependency_text = (
            None
            if not en_dependencies
            else (
                "\n".join(_unit_text(context.en_units[item]) for item in en_dependencies)
                if en_table is None
                else en_table[1]
            )
        )
        zh_dependency_text = (
            None
            if not zh_dependencies
            else (
                "\n".join(_unit_text(context.zh_units[item]) for item in zh_dependencies)
                if zh_table is None
                else zh_table[1]
            )
        )
        en_text = _language_part(
            _LanguagePartInput(
                "en",
                values[0],
                values[1],
                values[2],
                values[3],
                en_primary_text,
                en_dependency_text,
                part_number,
                total_parts,
                include_part_label,
            )
        )
        zh_text = _language_part(
            _LanguagePartInput(
                "zh-Hant",
                values[4],
                values[5],
                values[6],
                values[7],
                zh_primary_text,
                zh_dependency_text,
                part_number,
                total_parts,
                include_part_label,
            )
        )
        text = f"{en_text}\n\n{zh_text}"
    payload = {
        "authority_note": context.profile.authority_note,
        "country": context.profile.country,
        "jurisdiction": context.profile.jurisdiction,
        "source": context.profile.source,
        "text": text,
        "type": context.profile.material_type,
    }
    if frozenset(payload) != _SIX_FIELDS:
        _fail("partition serving payload")
    token_count = context.token_counter.count(text)
    if type(token_count) is not int or token_count < 0:
        _fail("tokenizer result")
    metadata_bytes = len(canonicalize(checked_json_value(payload)))
    return BilingualServingPart(
        part_number,
        total_parts,
        node_ids,
        primary_groups,
        dependencies,
        en_primary,
        zh_primary,
        en_dependencies,
        zh_dependencies,
        text,
        _raw_fingerprint(text.encode()),
        _canonical_fingerprint(payload),
        PartitionMeasurement(
            token_count,
            metadata_bytes,
            context.profile.max_text_tokens,
            context.profile.max_metadata_bytes,
        ),
    )


def _frontier_node(context: _PartitionContext, node_id: str) -> tuple[str, ...] | None:
    node = context.nodes[node_id]
    if node.source_contract_state == _UNKNOWN_STATE:
        return None
    candidate = _render_part(context, (node_id,), 1, 1, include_part_label=True)
    if candidate.measurement.fits:
        return (node_id,)
    if node.indivisible or not node.child_partition_node_ids:
        return None
    result: list[str] = []
    for child_id in node.child_partition_node_ids:
        child_frontier = _frontier_node(context, child_id)
        if child_frontier is None:
            return None
        result.extend(child_frontier)
    return tuple(result)


def _initial_frontier(context: _PartitionContext) -> tuple[str, ...] | None:
    result: list[str] = []
    for node_id in context.request.root_partition_node_ids:
        frontier = _frontier_node(context, node_id)
        if frontier is None:
            return None
        result.extend(frontier)
    return tuple(result)


def _partition_for_total(
    context: _PartitionContext,
    frontier: tuple[str, ...],
    total: int,
) -> tuple[BilingualServingPart, ...] | None:
    cache: dict[tuple[int, int], tuple[BilingualServingPart, ...] | None] = {}

    def solve(start: int, part_number: int) -> tuple[BilingualServingPart, ...] | None:
        key = (start, part_number)
        if key in cache:
            return cache[key]
        remaining_parts = total - part_number
        if part_number == total:
            ends = (len(frontier),)
        else:
            maximum_end = len(frontier) - remaining_parts
            ends = tuple(range(maximum_end, start, -1))
        for end in ends:
            if end <= start:
                continue
            part = _render_part(
                context,
                frontier[start:end],
                part_number,
                total,
                include_part_label=True,
            )
            if not part.measurement.fits:
                continue
            if part_number == total:
                if end == len(frontier):
                    cache[key] = (part,)
                    return cache[key]
                continue
            tail = solve(end, part_number + 1)
            if tail is not None:
                cache[key] = (part, *tail)
                return cache[key]
        cache[key] = None
        return None

    return solve(0, 1)


def _canonical_partition(
    context: _PartitionContext, frontier: tuple[str, ...]
) -> tuple[BilingualServingPart, ...] | None:
    for total in range(1, len(frontier) + 1):
        result = _partition_for_total(context, frontier, total)
        if result is not None:
            return result
    return None


def _refine_frontier(
    context: _PartitionContext, frontier: tuple[str, ...]
) -> tuple[str, ...] | None:
    total = len(frontier)
    changed = False
    result: list[str] = []
    for index, node_id in enumerate(frontier, start=1):
        standalone = _render_part(
            context,
            (node_id,),
            index,
            total,
            include_part_label=True,
        )
        node = context.nodes[node_id]
        if standalone.measurement.fits:
            result.append(node_id)
            continue
        if (
            node.source_contract_state != _SUPPORTED_STATE
            or node.indivisible
            or not node.child_partition_node_ids
        ):
            return None
        changed = True
        for child_id in node.child_partition_node_ids:
            child_frontier = _frontier_node(context, child_id)
            if child_frontier is None:
                return None
            result.extend(child_frontier)
    return tuple(result) if changed else None


def _validate_final_coverage(
    context: _PartitionContext, parts: tuple[BilingualServingPart, ...]
) -> bool:
    primary_groups = tuple(
        group_id for part in parts for group_id in part.primary_alignment_group_ids
    )
    expected_groups = tuple(
        group_id
        for root_id in context.request.root_partition_node_ids
        for group_id in context.nodes[root_id].primary_alignment_group_ids
    )
    en_ids = tuple(unit_id for part in parts for unit_id in part.en_primary_source_unit_ids)
    zh_ids = tuple(unit_id for part in parts for unit_id in part.zh_hant_primary_source_unit_ids)
    expected_en, expected_zh = _group_source_ids(context, expected_groups)
    return (
        primary_groups == expected_groups
        and en_ids == expected_en
        and zh_ids == expected_zh
        and len(en_ids) == len(set(en_ids))
        and len(zh_ids) == len(set(zh_ids))
        and all(part.part_number == index for index, part in enumerate(parts, start=1))
        and all(part.total_parts == len(parts) and part.measurement.fits for part in parts)
    )


def _result(
    context: _PartitionContext,
    spec: _PartitionResultSpec,
) -> BilingualPartitionResult:
    disposition = spec.disposition
    reason = spec.reason
    parts = spec.parts
    quarantined = spec.quarantined
    coverage_gap_required = spec.coverage_gap_required
    document = {
        "alignment_map_fingerprint": context.alignment.fingerprint,
        "coverage_gap_required": coverage_gap_required,
        "disposition": disposition.value,
        "en_tree_fingerprint": context.en_tree.fingerprint,
        "external_effects": "NONE",
        "parts": [part.document() for part in parts],
        "profile_fingerprint": context.profile.profile_fingerprint,
        "profile_id": context.profile.profile_id,
        "quarantined_partition_node_ids": list(quarantined),
        "reason": reason.value,
        "search_record_output": "NONE",
        "zh_hant_tree_fingerprint": context.zh_tree.fingerprint,
    }
    canonical_bytes = canonicalize(checked_json_value(document))
    return BilingualPartitionResult(
        disposition,
        reason,
        parts,
        quarantined,
        coverage_gap_required,
        context.profile.profile_id,
        context.profile.profile_fingerprint,
        context.en_tree.fingerprint,
        context.zh_tree.fingerprint,
        context.alignment.fingerprint,
        canonical_bytes,
        _raw_fingerprint(canonical_bytes),
    )


def _fit_result(
    context: _PartitionContext,
    ordinary_text: str,
    measurement: PartitionMeasurement,
) -> BilingualPartitionResult:
    root_ids = context.request.root_partition_node_ids
    part = _render_part(context, root_ids, 1, 1, include_part_label=False)
    if part.text != ordinary_text or part.measurement != measurement:
        return _result(
            context,
            _PartitionResultSpec(
                PartitionDisposition.BLOCK,
                PartitionReason.SOURCE_LOCATION_OWNERSHIP_DEFECT,
            ),
        )
    if not _validate_final_coverage(context, (part,)):
        return _result(
            context,
            _PartitionResultSpec(
                PartitionDisposition.BLOCK,
                PartitionReason.SOURCE_UNIT_COVERAGE_DEFECT,
            ),
        )
    return _result(
        context,
        _PartitionResultSpec(
            PartitionDisposition.PASS,
            PartitionReason.PASS_UNSPLIT,
            (part,),
        ),
    )


def _overlong_result(context: _PartitionContext) -> BilingualPartitionResult:
    frontier = _initial_frontier(context)
    while frontier is not None:
        parts = _canonical_partition(context, frontier)
        if parts is not None:
            if not _validate_final_coverage(context, parts):
                return _result(
                    context,
                    _PartitionResultSpec(
                        PartitionDisposition.BLOCK,
                        PartitionReason.SOURCE_UNIT_COVERAGE_DEFECT,
                    ),
                )
            if len(parts) < _MIN_PARTITIONED_PARTS:
                return _result(
                    context,
                    _PartitionResultSpec(
                        PartitionDisposition.BLOCK,
                        PartitionReason.CANONICAL_PARTITION_DEFECT,
                    ),
                )
            return _result(
                context,
                _PartitionResultSpec(
                    PartitionDisposition.PASS,
                    PartitionReason.PASS_PARTITIONED,
                    parts,
                ),
            )
        frontier = _refine_frontier(context, frontier)
    smallest = tuple(
        node.partition_node_id
        for node in context.nodes.values()
        if node.indivisible or not node.child_partition_node_ids
    )
    return _result(
        context,
        _PartitionResultSpec(
            PartitionDisposition.QUARANTINE,
            PartitionReason.SMALLEST_DEPENDENT_BRANCH_OVER_LIMIT,
            quarantined=smallest,
            coverage_gap_required=True,
        ),
    )


def partition_canonical_bilingual_location(
    execution: BilingualPartitionExecution,
) -> BilingualPartitionResult:
    """Render or recursively partition one exact bilingual Legal Location.

    The output is a deterministic candidate and proof only.  It never creates
    a Search Record, chooses a production tokenizer, or performs an effect.
    """
    context, graph_result = _validate_request(execution)
    if graph_result is not None:
        return _result(context, graph_result)
    request = execution.request
    profile = execution.profile
    token_counter = execution.token_counter
    en_tree = execution.en_tree
    zh_hant_tree = execution.zh_hant_tree
    alignment_map = execution.alignment_map
    if any(node.source_contract_state == _UNKNOWN_STATE for node in context.nodes.values()):
        unknown = tuple(
            node.partition_node_id
            for node in context.nodes.values()
            if node.source_contract_state == _UNKNOWN_STATE
        )
        return _result(
            context,
            _PartitionResultSpec(
                PartitionDisposition.BLOCK,
                PartitionReason.SOURCE_CONTRACT_REVIEW_REQUIRED,
                quarantined=unknown,
            ),
        )

    ordinary = render_canonical_bilingual_location(
        en_tree=en_tree,
        zh_hant_tree=zh_hant_tree,
        alignment_map=alignment_map,
        legal_location_ref=request.legal_location_ref,
    )
    payload = {
        "authority_note": profile.authority_note,
        "country": profile.country,
        "jurisdiction": profile.jurisdiction,
        "source": profile.source,
        "text": ordinary.text,
        "type": profile.material_type,
    }
    tokens = token_counter.count(ordinary.text)
    if type(tokens) is not int or tokens < 0:
        _fail("tokenizer result")
    ordinary_measurement = PartitionMeasurement(
        tokens,
        len(canonicalize(checked_json_value(payload))),
        profile.max_text_tokens,
        profile.max_metadata_bytes,
    )
    if ordinary_measurement.fits:
        return _fit_result(context, ordinary.text, ordinary_measurement)
    return _overlong_result(context)


def partition_canonical_bilingual_locations(
    execution: BilingualPartitionBatchExecution,
) -> BilingualPartitionBatchResult:
    """Partition distinct Legal Locations independently and forbid combination.

    The input order is preserved.  This boundary creates no serving record and
    exposes no aggregate serving parts; each returned result remains bound to
    exactly one requested Legal Location.
    """
    if (
        type(execution) is not BilingualPartitionBatchExecution
        or len(execution.executions) < _MIN_BATCH_LOCATIONS
    ):
        _fail("partition batch execution")
    locations = tuple(
        _ref_signature(item.request.legal_location_ref) for item in execution.executions
    )
    if len(locations) != len(set(locations)):
        _fail("partition batch distinct Legal Locations")
    location_results = tuple(
        PartitionedLegalLocation(
            item.request.legal_location_ref,
            partition_canonical_bilingual_location(item),
        )
        for item in execution.executions
    )
    dispositions = tuple(item.result.disposition for item in location_results)
    if PartitionDisposition.BLOCK in dispositions:
        disposition = PartitionDisposition.BLOCK
    elif PartitionDisposition.QUARANTINE in dispositions:
        disposition = PartitionDisposition.QUARANTINE
    else:
        disposition = PartitionDisposition.PASS
    provisional = BilingualPartitionBatchResult(
        disposition,
        PartitionBatchReason.LOCATIONS_PROCESSED_SEPARATELY,
        location_results,
        any(item.result.coverage_gap_required for item in location_results),
        (),
        b"",
        "",
    )
    canonical_bytes = canonicalize(provisional.document())
    return BilingualPartitionBatchResult(
        provisional.disposition,
        provisional.reason,
        provisional.location_results,
        provisional.coverage_gap_required,
        (),
        canonical_bytes,
        _raw_fingerprint(canonical_bytes),
    )
