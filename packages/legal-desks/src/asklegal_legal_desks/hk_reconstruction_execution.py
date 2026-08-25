"""Transactional execution of validated Hong Kong reconstruction Plans.

The executor mutates only private copies of verified canonical source trees.
It emits provisional canonical trees and a verified provisional bilingual
alignment map, never a Report, reconstructed artifact, Search Record, or
external effect.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal, Never

from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.errors import ContractViolation
from asklegal_contracts.json_types import checked_json_value

from .hk_canonical_legislation import (
    BilingualAlignmentMap,
    CanonicalLanguageTree,
    canonical_source_unit_inventory_fingerprint,
    parse_bilingual_alignment_map,
    parse_canonical_language_tree,
    seal_canonical_language_tree,
)
from .hk_legislation import ReconstructionPlanValidationDecision
from .model import RulebookError, RulebookErrorCode

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_PLAN_SCHEMA = "schemas/reconstruction-plan-validation.schema.json#/$defs/plan"
_TREE_SCHEMA = "schemas/canonical-language-tree.schema.json"
_ALIGNMENT_SCHEMA = "schemas/bilingual-alignment-map.schema.json"
RECONSTRUCTION_EXECUTION_SCHEMA = (
    "https://contracts.asklegal.local/v1/hk-legislation-reconstruction-execution.schema.json"
)
HK_RECONSTRUCTION_EXECUTION_RULE_ID = "HKLEG-RECON-EXEC-001"
_EXECUTION_SCHEMA = "schemas/reconstruction-execution.schema.json"
_OPERATION_IDS = frozenset(f"HKRECON-OP-{index:03d}" for index in range(1, 9))
_LANGUAGES = ("en", "zh-Hant")
_OFFLINE_EXECUTION_MODE = "OFFLINE_SYNTHETIC_CONFORMANCE"
_SOURCE_ARTIFACT_KEYS = frozenset(("ref", "payload"))
_LABEL_UNIT_KINDS = frozenset(("STRUCTURAL_LABEL", "LOCATION_LOCATOR", "LOCATION_HEADING"))
_RENDERER_PATH = Path("renderers/canonical-ordinary-bilingual-renderer.json")
_MAX_MEMBER_BYTES = 8_000_000
_FROZEN_FIXTURE_COUNT = 13
_EXECUTION_REASON_CODES = frozenset(
    {
        "RECONSTRUCTION_OPERATIONS_PROVISIONALLY_COMPLETE",
        "RECONSTRUCTION_OPERATION_APPLIED",
        "UNSUPPORTED_RECONSTRUCTION_OPERATION",
        "RECONSTRUCTION_UNDECLARED_INPUT",
        "RECONSTRUCTION_SOURCE_UNIT_KIND_MISMATCH",
        "RECONSTRUCTION_DEPENDENCY_CLOSURE_INCOMPLETE",
        "RECONSTRUCTION_STRUCTURE_UNSUPPORTED",
        "RECONSTRUCTION_SOURCE_UNIT_OWNERSHIP_MISMATCH",
        "RECONSTRUCTION_TARGET_NOT_EXACT",
        "RECONSTRUCTION_BEFORE_STATE_MISMATCH",
        "RECONSTRUCTION_AFTER_STATE_MISMATCH",
        "RECONSTRUCTION_RENDERER_UNSUPPORTED",
        "RECONSTRUCTION_CANONICAL_TREE_INVALID",
        "RECONSTRUCTION_NOT_RUN_AFTER_ATOMIC_FAILURE",
        "RECONSTRUCTION_FINAL_TREE_MISMATCH",
        "RECONSTRUCTION_SOURCE_UNIT_INVENTORY_MISMATCH",
        "RECONSTRUCTION_BILINGUAL_ALIGNMENT_MISMATCH",
    }
)

type AuthenticLanguage = Literal["en", "zh-Hant"]
type RefSignature = tuple[str, str, str]
type OperationResultCode = Literal[
    "APPLIED",
    "FAILED_PRECONDITION",
    "FAILED_EXECUTION",
    "NOT_RUN_AFTER_ATOMIC_FAILURE",
]
type AtomicGroupResultCode = Literal["APPLIED", "FAILED", "ROLLED_BACK", "NOT_RUN"]


def _authentic_language(value: JsonValue | None) -> AuthenticLanguage:
    if value == "en":
        return "en"
    if value == "zh-Hant":
        return "zh-Hant"
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "result language")


def _operation_result_code(value: JsonValue | None) -> OperationResultCode:
    if value == "APPLIED":
        return "APPLIED"
    if value == "FAILED_PRECONDITION":
        return "FAILED_PRECONDITION"
    if value == "FAILED_EXECUTION":
        return "FAILED_EXECUTION"
    if value == "NOT_RUN_AFTER_ATOMIC_FAILURE":
        return "NOT_RUN_AFTER_ATOMIC_FAILURE"
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "result code")


def _atomic_result_code(value: JsonValue | None) -> AtomicGroupResultCode:
    if value == "APPLIED":
        return "APPLIED"
    if value == "FAILED":
        return "FAILED"
    if value == "ROLLED_BACK":
        return "ROLLED_BACK"
    if value == "NOT_RUN":
        return "NOT_RUN"
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "atomic result")


def _execution_outcome(value: JsonValue | None) -> Literal["PASS", "BLOCK"]:
    if value == "PASS":
        return "PASS"
    if value == "BLOCK":
        return "BLOCK"
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "execution outcome")


def _execution_mode_value(
    value: JsonValue | None,
) -> Literal["OFFLINE_SYNTHETIC_CONFORMANCE"]:
    if value == "OFFLINE_SYNTHETIC_CONFORMANCE":
        return "OFFLINE_SYNTHETIC_CONFORMANCE"
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "execution mode")


def _optional_text(value: JsonValue | None, detail: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail)


def _checked_object(value: object) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    if not isinstance(parsed, dict):
        message = "expected JSON object"
        raise TypeError(message)
    return parsed


@dataclass(frozen=True, slots=True)
class ReconstructionOperationResult:
    """One exact provisional operation result in Plan order."""

    language: AuthenticLanguage
    operation_instance_id: str
    operation_type_id: str
    atomic_group_id: str
    result: OperationResultCode
    actual_target_count: int
    matched_location_ids: tuple[str, ...]
    matched_source_unit_ids: tuple[str, ...]
    actual_before_state_fingerprint: str | None
    actual_after_state_fingerprint: str | None
    provisional_output_tree_fingerprint: str | None
    reason_codes: tuple[str, ...]
    atomic_group_result: AtomicGroupResultCode

    def document(self) -> dict[str, JsonValue]:
        """Return the closed operation-result projection."""
        return {
            "language": self.language,
            "operation_instance_id": self.operation_instance_id,
            "operation_type_id": self.operation_type_id,
            "atomic_group_id": self.atomic_group_id,
            "result": self.result,
            "actual_target_count": self.actual_target_count,
            "matched_location_ids": list(self.matched_location_ids),
            "matched_source_unit_ids": list(self.matched_source_unit_ids),
            "actual_before_state_fingerprint": self.actual_before_state_fingerprint,
            "actual_after_state_fingerprint": self.actual_after_state_fingerprint,
            "provisional_output_tree_fingerprint": self.provisional_output_tree_fingerprint,
            "reason_codes": list(self.reason_codes),
            "atomic_group_result": self.atomic_group_result,
        }


@dataclass(frozen=True, slots=True)
class ReconstructionPlanExecution:
    """Effect-free provisional execution result for one exact validated Plan."""

    processing_outcome: Literal["PASS", "BLOCK"]
    reason_code: str
    reconstruction_plan_id: str
    reconstruction_plan_fingerprint: str
    execution_mode: Literal["OFFLINE_SYNTHETIC_CONFORMANCE"]
    operation_results: tuple[ReconstructionOperationResult, ...]
    provisional_language_trees: tuple[dict[str, JsonValue], ...]
    provisional_language_tree_fingerprints: tuple[str, ...]
    provisional_bilingual_alignment_map: dict[str, JsonValue] | None
    provisional_bilingual_alignment_map_fingerprint: str | None

    def document(self) -> dict[str, JsonValue]:
        """Return a strict non-Report, non-artifact execution representation."""
        return {
            "rule_id": HK_RECONSTRUCTION_EXECUTION_RULE_ID,
            "rule_trace": ["HKLEG-RECON-PLAN-001", HK_RECONSTRUCTION_EXECUTION_RULE_ID],
            "processing_outcome": self.processing_outcome,
            "reason_codes": [self.reason_code],
            "reconstruction_plan_id": self.reconstruction_plan_id,
            "reconstruction_plan_fingerprint": self.reconstruction_plan_fingerprint,
            "execution_mode": self.execution_mode,
            "operation_results": [result.document() for result in self.operation_results],
            "provisional_language_trees": list(self.provisional_language_trees),
            "provisional_language_tree_fingerprints": list(
                self.provisional_language_tree_fingerprints
            ),
            "provisional_bilingual_alignment_map": self.provisional_bilingual_alignment_map,
            "provisional_bilingual_alignment_map_fingerprint": (
                self.provisional_bilingual_alignment_map_fingerprint
            ),
            "execution_report_output": "NONE",
            "reconstructed_artifact_output": "NONE",
            "record_output": "NONE",
            "external_effects": "NONE",
            "next_action": (
                "BUILD_AND_VALIDATE_RECONSTRUCTION_ARTIFACT_AND_REPORT"
                if self.processing_outcome == "PASS"
                else "SELECT_VALIDATED_FALLBACK_OR_NO_RECORD"
            ),
        }


def reconstruction_plan_execution_from_document(
    package_root: Path,
    document: dict[str, JsonValue],
) -> ReconstructionPlanExecution:
    """Parse one closed provisional execution result after full schema validation."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    try:
        registry.validate(
            checked_json_value(document),
            f"{_EXECUTION_SCHEMA}#/$defs/execution_result",
        )
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "execution result") from error
    operation_results = tuple(
        ReconstructionOperationResult(
            language=_authentic_language(item.get("language")),
            operation_instance_id=_text(item.get("operation_instance_id"), "operation ID"),
            operation_type_id=_text(item.get("operation_type_id"), "operation type"),
            atomic_group_id=_text(item.get("atomic_group_id"), "atomic group"),
            result=_operation_result_code(item.get("result")),
            actual_target_count=_integer(item.get("actual_target_count"), "target count"),
            matched_location_ids=_strings(item.get("matched_location_ids"), "location IDs"),
            matched_source_unit_ids=_strings(
                item.get("matched_source_unit_ids"),
                "source-unit IDs",
            ),
            actual_before_state_fingerprint=_optional_text(
                item.get("actual_before_state_fingerprint"),
                "before-state fingerprint",
            ),
            actual_after_state_fingerprint=_optional_text(
                item.get("actual_after_state_fingerprint"),
                "after-state fingerprint",
            ),
            provisional_output_tree_fingerprint=_optional_text(
                item.get("provisional_output_tree_fingerprint"),
                "provisional tree fingerprint",
            ),
            reason_codes=_strings(item.get("reason_codes"), "operation reasons"),
            atomic_group_result=_atomic_result_code(item.get("atomic_group_result")),
        )
        for item in _objects(document.get("operation_results"), "operation results")
    )
    return ReconstructionPlanExecution(
        processing_outcome=_execution_outcome(document.get("processing_outcome")),
        reason_code=_strings(document.get("reason_codes"), "execution reasons")[0],
        reconstruction_plan_id=_text(document.get("reconstruction_plan_id"), "Plan ID"),
        reconstruction_plan_fingerprint=_text(
            document.get("reconstruction_plan_fingerprint"),
            "Plan fingerprint",
        ),
        execution_mode=_execution_mode_value(document.get("execution_mode")),
        operation_results=operation_results,
        provisional_language_trees=_objects(
            document.get("provisional_language_trees"),
            "provisional trees",
        ),
        provisional_language_tree_fingerprints=_strings(
            document.get("provisional_language_tree_fingerprints"),
            "provisional tree fingerprints",
        ),
        provisional_bilingual_alignment_map=(
            _object(document.get("provisional_bilingual_alignment_map"), "alignment")
            if document.get("provisional_bilingual_alignment_map") is not None
            else None
        ),
        provisional_bilingual_alignment_map_fingerprint=_optional_text(
            document.get("provisional_bilingual_alignment_map_fingerprint"),
            "alignment fingerprint",
        ),
    )


@dataclass(frozen=True, slots=True)
class ReconstructionExecutionRequest:
    """Closed inputs for one offline deterministic Plan execution attempt."""

    package_root: Path
    plan: dict[str, JsonValue]
    validation_decision: ReconstructionPlanValidationDecision
    language_inputs: tuple[dict[str, JsonValue], ...]
    source_artifacts: tuple[dict[str, JsonValue], ...]
    bilingual_alignment_map: dict[str, JsonValue]
    execution_mode: Literal["OFFLINE_SYNTHETIC_CONFORMANCE"]

    def document(self) -> dict[str, JsonValue]:
        """Return the path-free strict request consumed by the executor."""
        return {
            "$schema": RECONSTRUCTION_EXECUTION_SCHEMA,
            "contract_version": "1.0.0",
            "execution_mode": self.execution_mode,
            "plan": self.plan,
            "validation_decision": self.validation_decision.document(),
            "language_inputs": list(self.language_inputs),
            "source_artifacts": list(self.source_artifacts),
            "bilingual_alignment_map": self.bilingual_alignment_map,
        }


@dataclass(slots=True)
class _Unit:
    source_unit_id: str
    tree_node_id: str
    legal_location_ref: dict[str, JsonValue]
    unit_kind: str
    content: str | None
    asset_ref: dict[str, JsonValue] | None
    source_order: int

    def draft(self) -> dict[str, JsonValue]:
        return _checked_object(
            {
                "source_unit_id": self.source_unit_id,
                "tree_node_id": self.tree_node_id,
                "legal_location_ref": self.legal_location_ref,
                "unit_kind": self.unit_kind,
                "content": self.content,
                "asset_ref": self.asset_ref,
                "source_order": self.source_order,
            }
        )


@dataclass(slots=True)
class _Node:
    tree_node_id: str
    legal_location_ref: dict[str, JsonValue]
    structural_type: str
    parent_node_id: str | None
    sibling_order: int
    owned_source_unit_ids: list[str]
    child_node_ids: list[str]

    def draft(self) -> dict[str, JsonValue]:
        return _checked_object(
            {
                "tree_node_id": self.tree_node_id,
                "legal_location_ref": self.legal_location_ref,
                "structural_type": self.structural_type,
                "parent_node_id": self.parent_node_id,
                "sibling_order": self.sibling_order,
                "owned_source_unit_ids": self.owned_source_unit_ids,
                "child_node_ids": self.child_node_ids,
            }
        )


@dataclass(slots=True)
class _Tree:
    source_format: str
    language: AuthenticLanguage
    legal_item_ref: dict[str, JsonValue]
    root_node_id: str
    nodes: list[_Node]
    units: list[_Unit]

    @classmethod
    def from_canonical(cls, tree: CanonicalLanguageTree) -> _Tree:
        """Create one private mutable copy of a verified canonical tree."""
        return cls(
            source_format=tree.source_format,
            language=tree.language,
            legal_item_ref=deepcopy(tree.legal_item_ref),
            root_node_id=tree.root_node_id,
            nodes=[
                _Node(
                    node.tree_node_id,
                    deepcopy(node.legal_location_ref),
                    node.structural_type,
                    node.parent_node_id,
                    node.sibling_order,
                    list(node.owned_source_unit_ids),
                    list(node.child_node_ids),
                )
                for node in tree.nodes
            ],
            units=[
                _Unit(
                    unit.source_unit_id,
                    unit.tree_node_id,
                    deepcopy(unit.legal_location_ref),
                    unit.unit_kind,
                    unit.content,
                    deepcopy(unit.asset_ref),
                    unit.source_order,
                )
                for unit in tree.source_units
            ],
        )

    def _refresh_order(self) -> None:
        """Refresh child inventories and canonical node/source-unit ordering."""
        self.nodes, self.units = _canonical_mutable_inventory(
            self.nodes, self.units, self.root_node_id
        )

    def seal(self) -> CanonicalLanguageTree:
        """Revalidate and seal the complete provisional tree."""
        self._refresh_order()
        return seal_canonical_language_tree(
            _checked_object(
                {
                    "source_format": self.source_format,
                    "language": self.language,
                    "legal_item_ref": self.legal_item_ref,
                    "root_node_id": self.root_node_id,
                    "nodes": [node.draft() for node in self.nodes],
                    "source_units": [unit.draft() for unit in self.units],
                }
            )
        )


def _parent_groups(nodes: list[_Node]) -> dict[str | None, list[_Node]]:
    groups: dict[str | None, list[_Node]] = {}
    for node in nodes:
        groups.setdefault(node.parent_node_id, []).append(node)
    for siblings in groups.values():
        siblings.sort(key=lambda item: (item.sibling_order, item.tree_node_id))
        if [item.sibling_order for item in siblings] != list(range(len(siblings))):
            _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED")
    return groups


def _preorder_mutable_nodes(
    root_node_id: str,
    nodes: list[_Node],
    groups: dict[str | None, list[_Node]],
) -> list[_Node]:
    by_node = {node.tree_node_id: node for node in nodes}
    roots = groups.get(None, [])
    if (
        len(by_node) != len(nodes)
        or root_node_id not in by_node
        or len(roots) != 1
        or roots[0].tree_node_id != root_node_id
    ):
        _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED")
    for node in nodes:
        node.child_node_ids = [child.tree_node_id for child in groups.get(node.tree_node_id, [])]
    ordered: list[_Node] = []
    visiting: set[str] = set()

    def visit(node: _Node) -> None:
        if node.tree_node_id in visiting or any(
            item.tree_node_id == node.tree_node_id for item in ordered
        ):
            _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED", (node,))
        visiting.add(node.tree_node_id)
        ordered.append(node)
        for child_id in node.child_node_ids:
            visit(by_node[child_id])
        visiting.remove(node.tree_node_id)

    visit(by_node[root_node_id])
    if len(ordered) != len(nodes):
        _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED")
    return ordered


def _preorder_mutable_units(nodes: list[_Node], units: list[_Unit]) -> list[_Unit]:
    by_unit = {unit.source_unit_id: unit for unit in units}
    if len(by_unit) != len(units):
        _fail_precondition("RECONSTRUCTION_SOURCE_UNIT_OWNERSHIP_MISMATCH")
    ordered: list[_Unit] = []
    for node in nodes:
        owned = [by_unit[unit_id] for unit_id in node.owned_source_unit_ids if unit_id in by_unit]
        if (
            len(owned) != len(node.owned_source_unit_ids)
            or any(unit.tree_node_id != node.tree_node_id for unit in owned)
            or [unit.source_order for unit in owned] != list(range(len(owned)))
        ):
            _fail_precondition("RECONSTRUCTION_SOURCE_UNIT_OWNERSHIP_MISMATCH", (node,))
        ordered.extend(owned)
    if len(ordered) != len(units):
        _fail_precondition("RECONSTRUCTION_SOURCE_UNIT_OWNERSHIP_MISMATCH")
    return ordered


def _canonical_mutable_inventory(
    nodes: list[_Node], units: list[_Unit], root_node_id: str
) -> tuple[list[_Node], list[_Unit]]:
    ordered_nodes = _preorder_mutable_nodes(root_node_id, nodes, _parent_groups(nodes))
    return ordered_nodes, _preorder_mutable_units(ordered_nodes, units)


@dataclass(frozen=True, slots=True)
class _AppliedOperation:
    target_node_ids: tuple[str, ...]
    matched_location_ids: tuple[str, ...]
    matched_source_unit_ids: tuple[str, ...]
    before_content_fingerprint: str
    after_content_fingerprint: str


class _PreconditionFailure(Exception):
    def __init__(self, reason_code: str, target_node_ids: tuple[str, ...] = ()) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.target_node_ids = target_node_ids


@dataclass(frozen=True, slots=True)
class _RendererContract:
    reference: RefSignature
    supported_structural_types: frozenset[str]
    supported_unit_kinds: frozenset[str]


@dataclass(frozen=True, slots=True)
class _ExecutionContext:
    inventory: dict[RefSignature, dict[str, JsonValue]]
    renderer: _RendererContract


def _target_ids(targets: tuple[_Node, ...]) -> tuple[str, ...]:
    return tuple(target.tree_node_id for target in targets)


def _fail_precondition(reason_code: str, targets: tuple[_Node, ...] = ()) -> Never:
    raise _PreconditionFailure(reason_code, _target_ids(targets))


def _fingerprint(value: JsonValue) -> str:
    return f"sha256:{sha256(canonicalize(value)).hexdigest()}"


def _bytes_fingerprint(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def reconstruction_tree_fingerprint(tree: dict[str, JsonValue]) -> str:
    """Fingerprint one independently verified canonical language tree."""
    return parse_canonical_language_tree(tree).fingerprint


def reconstruction_state_fingerprints(
    tree: dict[str, JsonValue], tree_node_ids: tuple[str, ...]
) -> tuple[str, str, str]:
    """Return exact structure, content, and ownership hashes for selected nodes."""
    mutable = _Tree.from_canonical(parse_canonical_language_tree(tree))
    selected = tuple(_node_by_id(mutable, node_id) for node_id in tree_node_ids)
    return _state_fingerprints(mutable, selected)


def reconstruction_deleted_state_fingerprints(
    location_refs: tuple[dict[str, JsonValue], ...],
) -> tuple[str, str, str]:
    """Return structure/content/ownership hashes for one deletion tombstone."""
    tombstone: dict[str, JsonValue] = {
        "deleted_location_refs": [checked_json_value(ref) for ref in location_refs]
    }
    fingerprint = _fingerprint(tombstone)
    return fingerprint, fingerprint, fingerprint


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _objects(value: JsonValue | None, label: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return tuple(item for item in value if isinstance(item, dict))


def _strings(value: JsonValue | None, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    result = tuple(item for item in value if isinstance(item, str))
    if len(result) != len(set(result)):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return result


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _integer(value: JsonValue | None, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _expect_keys(value: dict[str, JsonValue], expected: frozenset[str], label: str) -> None:
    if frozenset(value) != expected:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)


def _ref_signature(value: dict[str, JsonValue]) -> RefSignature:
    return (
        _text(value.get("ref_type"), "reference type"),
        _text(value.get("ref_id"), "reference ID"),
        _text(value.get("fingerprint"), "reference fingerprint"),
    )


def _ref_id(value: dict[str, JsonValue]) -> str:
    return _ref_signature(value)[1]


def _same_ref(left: dict[str, JsonValue], right: dict[str, JsonValue]) -> bool:
    return _ref_signature(left) == _ref_signature(right)


def _contract_signature(value: dict[str, JsonValue]) -> RefSignature:
    return (
        _text(value.get("contract_id"), "contract ID"),
        _text(value.get("version"), "contract version"),
        _text(value.get("fingerprint"), "contract fingerprint"),
    )


def _node_by_id(tree: _Tree, node_id: str) -> _Node:
    matches = [node for node in tree.nodes if node.tree_node_id == node_id]
    if len(matches) != 1:
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", tuple(matches))
    return matches[0]


def _unit_by_id(tree: _Tree, unit_id: str) -> _Unit:
    matches = [unit for unit in tree.units if unit.source_unit_id == unit_id]
    if len(matches) != 1:
        _fail_precondition("RECONSTRUCTION_SOURCE_UNIT_OWNERSHIP_MISMATCH")
    return matches[0]


def _unit_text(unit: _Unit) -> str:
    if unit.content is None:
        _fail_precondition("RECONSTRUCTION_SOURCE_UNIT_KIND_MISMATCH")
    return unit.content


def _nodes_by_location(tree: _Tree, refs: tuple[dict[str, JsonValue], ...]) -> tuple[_Node, ...]:
    signatures = {_ref_signature(ref) for ref in refs}
    return tuple(
        node for node in tree.nodes if _ref_signature(node.legal_location_ref) in signatures
    )


def _descendants(tree: _Tree, root: _Node) -> tuple[_Node, ...]:
    selected = {root.tree_node_id}
    changed = True
    while changed:
        changed = False
        for node in tree.nodes:
            if node.parent_node_id in selected and node.tree_node_id not in selected:
                selected.add(node.tree_node_id)
                changed = True
    return tuple(node for node in tree.nodes if node.tree_node_id in selected)


def _selected_units(tree: _Tree, nodes: tuple[_Node, ...]) -> tuple[_Unit, ...]:
    node_ids = {node.tree_node_id for node in nodes}
    return tuple(unit for unit in tree.units if unit.tree_node_id in node_ids)


def _structure_projection(node: _Node) -> dict[str, JsonValue]:
    return _checked_object(
        {
            "tree_node_id": node.tree_node_id,
            "legal_location_ref": node.legal_location_ref,
            "structural_type": node.structural_type,
            "parent_node_id": node.parent_node_id,
            "sibling_order": node.sibling_order,
            "child_node_ids": node.child_node_ids,
        }
    )


def _content_projection(tree: _Tree, node: _Node) -> dict[str, JsonValue]:
    return _checked_object(
        {
            "tree_node_id": node.tree_node_id,
            "source_units": [
                {
                    "source_unit_id": unit.source_unit_id,
                    "unit_kind": unit.unit_kind,
                    "content": unit.content,
                    "asset_ref": unit.asset_ref,
                }
                for unit in (_unit_by_id(tree, unit_id) for unit_id in node.owned_source_unit_ids)
            ],
        }
    )


def _ownership_projection(tree: _Tree, node: _Node) -> dict[str, JsonValue]:
    return _checked_object(
        {
            "tree_node_id": node.tree_node_id,
            "owned_source_units": [
                {
                    "source_unit_id": unit.source_unit_id,
                    "tree_node_id": unit.tree_node_id,
                    "legal_location_ref": unit.legal_location_ref,
                    "source_order": unit.source_order,
                }
                for unit in (_unit_by_id(tree, unit_id) for unit_id in node.owned_source_unit_ids)
            ],
        }
    )


def _state_fingerprints(tree: _Tree, nodes: tuple[_Node, ...]) -> tuple[str, str, str]:
    node_ids = {node.tree_node_id for node in nodes}
    ordered = tuple(node for node in tree.nodes if node.tree_node_id in node_ids)
    if len(ordered) != len(node_ids):
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", nodes)
    return (
        _fingerprint([_structure_projection(node) for node in ordered]),
        _fingerprint([_content_projection(tree, node) for node in ordered]),
        _fingerprint([_ownership_projection(tree, node) for node in ordered]),
    )


def _tree_fingerprint(tree: _Tree) -> str:
    return tree.seal().fingerprint


def _source_inventory(
    raw_artifacts: tuple[dict[str, JsonValue], ...],
) -> dict[RefSignature, dict[str, JsonValue]]:
    result: dict[RefSignature, dict[str, JsonValue]] = {}
    for artifact in raw_artifacts:
        _expect_keys(artifact, _SOURCE_ARTIFACT_KEYS, "source artifact")
        ref = _object(artifact.get("ref"), "source artifact reference")
        payload = _object(artifact.get("payload"), "source artifact payload")
        signature = _ref_signature(ref)
        if signature in result or signature[2] != _fingerprint(payload):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "source artifact")
        result[signature] = payload
    return result


def _payload(context: _ExecutionContext, ref: dict[str, JsonValue]) -> dict[str, JsonValue]:
    try:
        return context.inventory[_ref_signature(ref)]
    except KeyError as error:
        reason = "RECONSTRUCTION_UNDECLARED_INPUT"
        raise _PreconditionFailure(reason) from error


def _text_payload(context: _ExecutionContext, ref: dict[str, JsonValue]) -> str:
    payload = _payload(context, ref)
    _expect_keys(payload, frozenset(("payload_kind", "content")), "text payload")
    if payload.get("payload_kind") != "TEXT":
        _fail_precondition("RECONSTRUCTION_SOURCE_UNIT_KIND_MISMATCH")
    return _text(payload.get("content"), "source text")


def _inventory_payload(
    context: _ExecutionContext,
    refs: tuple[dict[str, JsonValue], ...],
    payload_kind: str,
) -> tuple[str, ...]:
    result: list[str] = []
    for ref in refs:
        payload = _payload(context, ref)
        _expect_keys(
            payload,
            frozenset(("payload_kind", "source_unit_ids")),
            "source-unit inventory payload",
        )
        if payload.get("payload_kind") != payload_kind:
            _fail_precondition("RECONSTRUCTION_SOURCE_UNIT_KIND_MISMATCH")
        result.extend(_strings(payload.get("source_unit_ids"), "source-unit IDs"))
    if not result or len(result) != len(set(result)):
        _fail_precondition("RECONSTRUCTION_DEPENDENCY_CLOSURE_INCOMPLETE")
    return tuple(result)


def _fragment_payload(
    tree: _Tree,
    context: _ExecutionContext,
    refs: tuple[dict[str, JsonValue], ...],
) -> _Tree:
    if len(refs) != 1:
        _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED")
    payload = _payload(context, refs[0])
    _expect_keys(payload, frozenset(("payload_kind", "tree")), "tree fragment payload")
    if payload.get("payload_kind") != "CANONICAL_TREE_FRAGMENT":
        _fail_precondition("RECONSTRUCTION_SOURCE_UNIT_KIND_MISMATCH")
    fragment = _Tree.from_canonical(
        parse_canonical_language_tree(_object(payload.get("tree"), "canonical tree fragment"))
    )
    if fragment.language != tree.language or not _same_ref(
        fragment.legal_item_ref, tree.legal_item_ref
    ):
        _fail_precondition("RECONSTRUCTION_SOURCE_UNIT_KIND_MISMATCH")
    return fragment


def _selector(operation: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return _object(operation.get("target_selector"), "target selector")


def _parameters(operation: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return _object(operation.get("parameters"), "operation parameters")


def _before_state(operation: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return _object(operation.get("before_state"), "before state")


def _after_state(operation: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return _object(operation.get("expected_after_state"), "after state")


def _location_ids(nodes: tuple[_Node, ...]) -> tuple[str, ...]:
    return tuple(sorted({_ref_id(node.legal_location_ref) for node in nodes}))


def _validate_before_state(
    tree: _Tree, operation: dict[str, JsonValue], targets: tuple[_Node, ...]
) -> str:
    before = _before_state(operation)
    expected_locations = {
        _ref_signature(ref) for ref in _objects(before.get("location_refs"), "before locations")
    }
    structure, content, _ = _state_fingerprints(tree, targets)
    actual_locations = {_ref_signature(node.legal_location_ref) for node in targets}
    if (
        len(targets) != _integer(before.get("expected_target_count"), "target count")
        or actual_locations != expected_locations
        or structure != before.get("structure_fingerprint")
        or content != before.get("content_fingerprint")
    ):
        _fail_precondition("RECONSTRUCTION_BEFORE_STATE_MISMATCH", targets)
    return content


def _validate_after_state(
    tree: _Tree, operation: dict[str, JsonValue], targets: tuple[_Node, ...]
) -> str:
    after = _after_state(operation)
    expected_locations = {
        _ref_signature(ref) for ref in _objects(after.get("location_refs"), "after locations")
    }
    structure, content, ownership = _state_fingerprints(tree, targets)
    actual_locations = {_ref_signature(node.legal_location_ref) for node in targets}
    if (
        actual_locations != expected_locations
        or structure != after.get("structure_fingerprint")
        or content != after.get("content_fingerprint")
        or ownership != after.get("source_unit_ownership_fingerprint")
    ):
        _fail_precondition("RECONSTRUCTION_AFTER_STATE_MISMATCH", targets)
    return content


def _reindex_siblings(tree: _Tree, parent_id: str | None) -> None:
    siblings = sorted(
        (node for node in tree.nodes if node.parent_node_id == parent_id),
        key=lambda node: (node.sibling_order, node.tree_node_id),
    )
    for index, node in enumerate(siblings):
        node.sibling_order = index


def _insertion_position(
    tree: _Tree, anchor: _Node, insertion_anchor: str
) -> tuple[str | None, int]:
    if insertion_anchor == "BEFORE":
        return anchor.parent_node_id, anchor.sibling_order
    if insertion_anchor == "AFTER":
        return anchor.parent_node_id, anchor.sibling_order + 1
    if insertion_anchor == "FIRST_CHILD":
        return anchor.tree_node_id, 0
    if insertion_anchor == "LAST_CHILD":
        count = sum(node.parent_node_id == anchor.tree_node_id for node in tree.nodes)
        return anchor.tree_node_id, count
    _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED")


def _insert_fragment(
    tree: _Tree, fragment: _Tree, parent_id: str | None, position: int
) -> tuple[_Node, ...]:
    existing_node_ids = {node.tree_node_id for node in tree.nodes}
    existing_unit_ids = {unit.source_unit_id for unit in tree.units}
    fragment_node_ids = {node.tree_node_id for node in fragment.nodes}
    fragment_unit_ids = {unit.source_unit_id for unit in fragment.units}
    if existing_node_ids & fragment_node_ids or existing_unit_ids & fragment_unit_ids:
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT")
    root = _node_by_id(fragment, fragment.root_node_id)
    for sibling in tree.nodes:
        if sibling.parent_node_id == parent_id and sibling.sibling_order >= position:
            sibling.sibling_order += 1
    root.parent_node_id = parent_id
    root.sibling_order = position
    inserted_ids = tuple(node.tree_node_id for node in fragment.nodes)
    tree.nodes.extend(fragment.nodes)
    tree.units.extend(fragment.units)
    _reindex_siblings(tree, parent_id)
    tree.seal()
    return tuple(_node_by_id(tree, node_id) for node_id in inserted_ids)


def _applied(
    targets: tuple[_Node, ...],
    source_unit_ids: tuple[str, ...],
    before: str,
    after: str,
) -> _AppliedOperation:
    return _AppliedOperation(
        _target_ids(targets), _location_ids(targets), source_unit_ids, before, after
    )


def _apply_op001(
    tree: _Tree, operation: dict[str, JsonValue], context: _ExecutionContext
) -> _AppliedOperation:
    target = _node_by_id(tree, _text(_selector(operation).get("tree_node_id"), "target node"))
    targets = (target,)
    before = _validate_before_state(tree, operation, targets)
    parameters = _parameters(operation)
    old = _text_payload(context, _object(parameters.get("old_text_source_unit_ref"), "old text"))
    new = _text_payload(
        context, _object(parameters.get("replacement_source_unit_ref"), "replacement text")
    )
    candidates = [
        unit
        for unit in (_unit_by_id(tree, unit_id) for unit_id in target.owned_source_unit_ids)
        if unit.content is not None and old in unit.content
    ]
    if (
        len(candidates) != 1
        or candidates[0].content is None
        or candidates[0].content.count(old) != 1
        or parameters.get("exact_range_fingerprint") != _fingerprint(old)
    ):
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", targets)
    candidates[0].content = candidates[0].content.replace(old, new, 1)
    after = _validate_after_state(tree, operation, targets)
    return _applied(targets, (candidates[0].source_unit_id,), before, after)


def _apply_op002(
    tree: _Tree, operation: dict[str, JsonValue], context: _ExecutionContext
) -> _AppliedOperation:
    parameters = _parameters(operation)
    old = _text_payload(
        context, _object(parameters.get("old_phrase_source_unit_ref"), "old phrase")
    )
    new = _text_payload(
        context, _object(parameters.get("replacement_source_unit_ref"), "replacement phrase")
    )
    scope = _objects(parameters.get("closed_scope_location_refs"), "closed scope")
    excluded = {
        _ref_signature(ref)
        for ref in _objects(parameters.get("exclusion_location_refs"), "exclusions")
    }
    candidates: list[tuple[_Node, _Unit]] = []
    for node in _nodes_by_location(tree, scope):
        if _ref_signature(node.legal_location_ref) in excluded:
            continue
        matches = [
            unit
            for unit in (_unit_by_id(tree, item) for item in node.owned_source_unit_ids)
            if unit.content is not None and old in unit.content
        ]
        if len(matches) > 1 or (matches and _unit_text(matches[0]).count(old) != 1):
            _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", (node,))
        if matches:
            candidates.append((node, matches[0]))
    targets = tuple(node for node, _ in candidates)
    expected = {
        _ref_signature(ref)
        for ref in _objects(parameters.get("expected_match_location_refs"), "expected matches")
    }
    if {_ref_signature(node.legal_location_ref) for node in targets} != expected:
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", targets)
    before = _validate_before_state(tree, operation, targets)
    for _, unit in candidates:
        unit.content = _unit_text(unit).replace(old, new, 1)
    after = _validate_after_state(tree, operation, targets)
    return _applied(
        targets,
        tuple(unit.source_unit_id for _, unit in candidates),
        before,
        after,
    )


def _apply_op003(
    tree: _Tree, operation: dict[str, JsonValue], context: _ExecutionContext
) -> _AppliedOperation:
    anchor = _node_by_id(tree, _text(_selector(operation).get("tree_node_id"), "target node"))
    before = _validate_before_state(tree, operation, (anchor,))
    parameters = _parameters(operation)
    parent_ref = _object(parameters.get("parent_location_ref"), "parent location")
    insertion_anchor = _text(parameters.get("insertion_anchor"), "insertion anchor")
    parent = (
        anchor
        if insertion_anchor in ("FIRST_CHILD", "LAST_CHILD")
        else _node_by_id(tree, anchor.parent_node_id or "")
    )
    if not _same_ref(parent.legal_location_ref, parent_ref):
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", (anchor,))
    fragment = _fragment_payload(
        tree,
        context,
        _objects(parameters.get("new_node_source_unit_refs"), "new node units"),
    )
    parent_id, position = _insertion_position(tree, anchor, insertion_anchor)
    inserted = _insert_fragment(tree, fragment, parent_id, position)
    after = _validate_after_state(tree, operation, inserted)
    return _applied(
        inserted,
        tuple(unit.source_unit_id for unit in _selected_units(tree, inserted)),
        before,
        after,
    )


def _apply_op004(
    tree: _Tree, operation: dict[str, JsonValue], context: _ExecutionContext
) -> _AppliedOperation:
    target = _node_by_id(tree, _text(_selector(operation).get("tree_node_id"), "target node"))
    if target.tree_node_id == tree.root_node_id:
        _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED", (target,))
    removed = _descendants(tree, target)
    before = _validate_before_state(tree, operation, removed)
    actual_unit_ids = tuple(unit.source_unit_id for unit in _selected_units(tree, removed))
    declared_unit_ids = _inventory_payload(
        context,
        _objects(_parameters(operation).get("removed_node_source_unit_refs"), "removed units"),
        "SOURCE_UNIT_REMOVAL",
    )
    if set(actual_unit_ids) != set(declared_unit_ids):
        _fail_precondition("RECONSTRUCTION_DEPENDENCY_CLOSURE_INCOMPLETE", removed)
    removed_ids = {node.tree_node_id for node in removed}
    parent_id = target.parent_node_id
    tree.nodes = [node for node in tree.nodes if node.tree_node_id not in removed_ids]
    tree.units = [unit for unit in tree.units if unit.tree_node_id not in removed_ids]
    _reindex_siblings(tree, parent_id)
    tree.seal()
    after_contract = _after_state(operation)
    removed_refs = tuple(node.legal_location_ref for node in removed)
    structure, content, ownership = reconstruction_deleted_state_fingerprints(removed_refs)
    if (
        {_ref_signature(ref) for ref in _objects(after_contract.get("location_refs"), "after")}
        != {_ref_signature(ref) for ref in removed_refs}
        or after_contract.get("structure_fingerprint") != structure
        or after_contract.get("content_fingerprint") != content
        or after_contract.get("source_unit_ownership_fingerprint") != ownership
    ):
        _fail_precondition("RECONSTRUCTION_AFTER_STATE_MISMATCH", removed)
    return _applied(removed, actual_unit_ids, before, content)


def _replace_complete_node(
    tree: _Tree,
    operation: dict[str, JsonValue],
    context: _ExecutionContext,
    parameter_name: str,
    *,
    renderer_guard: bool = False,
) -> _AppliedOperation:
    target = _node_by_id(tree, _text(_selector(operation).get("tree_node_id"), "target node"))
    if target.tree_node_id == tree.root_node_id:
        _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED", (target,))
    old_subtree = _descendants(tree, target)
    old_source_unit_ids = tuple(unit.source_unit_id for unit in _selected_units(tree, old_subtree))
    before = _validate_before_state(tree, operation, old_subtree)
    fragment = _fragment_payload(
        tree,
        context,
        _objects(_parameters(operation).get(parameter_name), "replacement node units"),
    )
    if renderer_guard:
        contract = _object(_parameters(operation).get("renderer_contract_ref"), "renderer contract")
        if (
            _contract_signature(contract) != context.renderer.reference
            or any(
                node.structural_type not in context.renderer.supported_structural_types
                for node in fragment.nodes
            )
            or any(
                unit.unit_kind not in context.renderer.supported_unit_kinds
                for unit in fragment.units
            )
        ):
            _fail_precondition("RECONSTRUCTION_RENDERER_UNSUPPORTED", old_subtree)
    removed_ids = {node.tree_node_id for node in old_subtree}
    parent_id = target.parent_node_id
    position = target.sibling_order
    tree.nodes = [node for node in tree.nodes if node.tree_node_id not in removed_ids]
    tree.units = [unit for unit in tree.units if unit.tree_node_id not in removed_ids]
    inserted = _insert_fragment(tree, fragment, parent_id, position)
    after = _validate_after_state(tree, operation, inserted)
    return _applied(
        inserted,
        (
            *old_source_unit_ids,
            *(unit.source_unit_id for unit in _selected_units(tree, inserted)),
        ),
        before,
        after,
    )


def _apply_op005(
    tree: _Tree, operation: dict[str, JsonValue], context: _ExecutionContext
) -> _AppliedOperation:
    return _replace_complete_node(tree, operation, context, "replacement_node_source_unit_refs")


def _apply_op006(
    tree: _Tree, operation: dict[str, JsonValue], context: _ExecutionContext
) -> _AppliedOperation:
    target = _node_by_id(tree, _text(_selector(operation).get("tree_node_id"), "target node"))
    targets = (target,)
    before = _validate_before_state(tree, operation, targets)
    parameters = _parameters(operation)
    if parameters.get("cross_reference_repairs") != []:
        _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED", targets)
    refs = _objects(parameters.get("label_source_unit_refs"), "label units")
    if len(refs) != 1:
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", targets)
    units = [
        unit
        for unit in (_unit_by_id(tree, unit_id) for unit_id in target.owned_source_unit_ids)
        if unit.unit_kind in _LABEL_UNIT_KINDS and unit.content is not None
    ]
    if len(units) != 1:
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", targets)
    units[0].content = _text_payload(context, refs[0])
    after = _validate_after_state(tree, operation, targets)
    return _applied(targets, (units[0].source_unit_id,), before, after)


def _apply_op007(
    tree: _Tree, operation: dict[str, JsonValue], context: _ExecutionContext
) -> _AppliedOperation:
    parameters = _parameters(operation)
    moved_ref = _object(parameters.get("moved_node_ref"), "moved node")
    matches = _nodes_by_location(tree, (moved_ref,))
    if len(matches) != 1:
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", matches)
    moved = matches[0]
    if moved.tree_node_id == tree.root_node_id:
        _fail_precondition("RECONSTRUCTION_STRUCTURE_UNSUPPORTED", (moved,))
    subtree = _descendants(tree, moved)
    before = _validate_before_state(tree, operation, subtree)
    actual_unit_ids = tuple(unit.source_unit_id for unit in _selected_units(tree, subtree))
    authority_ids = _inventory_payload(
        context,
        _objects(operation.get("source_unit_refs"), "move source units"),
        "MOVE_AUTHORITY",
    )
    if set(authority_ids) != set(actual_unit_ids):
        _fail_precondition("RECONSTRUCTION_DEPENDENCY_CLOSURE_INCOMPLETE", subtree)
    anchor = _node_by_id(tree, _text(_selector(operation).get("tree_node_id"), "move anchor"))
    if anchor.tree_node_id in {node.tree_node_id for node in subtree}:
        _fail_precondition("RECONSTRUCTION_DEPENDENCY_CLOSURE_INCOMPLETE", subtree)
    new_parent_ref = _object(parameters.get("new_parent_ref"), "new parent")
    position_name = _text(parameters.get("new_position"), "new position")
    parent = (
        anchor
        if position_name in ("FIRST_CHILD", "LAST_CHILD")
        else _node_by_id(tree, anchor.parent_node_id or "")
    )
    if not _same_ref(parent.legal_location_ref, new_parent_ref):
        _fail_precondition("RECONSTRUCTION_TARGET_NOT_EXACT", subtree)
    old_parent = moved.parent_node_id
    old_siblings = sorted(
        (
            node
            for node in tree.nodes
            if node.parent_node_id == old_parent and node.tree_node_id != moved.tree_node_id
        ),
        key=lambda node: node.sibling_order,
    )
    for index, sibling in enumerate(old_siblings):
        sibling.sibling_order = index
    new_parent_id, new_position = _insertion_position(tree, anchor, position_name)
    subtree_ids = {node.tree_node_id for node in subtree}
    for sibling in tree.nodes:
        if (
            sibling.tree_node_id not in subtree_ids
            and sibling.parent_node_id == new_parent_id
            and sibling.sibling_order >= new_position
        ):
            sibling.sibling_order += 1
    moved.parent_node_id = new_parent_id
    moved.sibling_order = new_position
    _reindex_siblings(tree, old_parent)
    _reindex_siblings(tree, new_parent_id)
    tree.seal()
    moved_subtree = tuple(_node_by_id(tree, node.tree_node_id) for node in subtree)
    after = _validate_after_state(tree, operation, moved_subtree)
    return _applied(moved_subtree, actual_unit_ids, before, after)


def _apply_op008(
    tree: _Tree, operation: dict[str, JsonValue], context: _ExecutionContext
) -> _AppliedOperation:
    return _replace_complete_node(
        tree,
        operation,
        context,
        "replacement_region_source_unit_refs",
        renderer_guard=True,
    )


type _OperationHandler = Callable[
    [_Tree, dict[str, JsonValue], _ExecutionContext], _AppliedOperation
]

_OPERATION_HANDLERS: dict[str, _OperationHandler] = {
    "HKRECON-OP-001": _apply_op001,
    "HKRECON-OP-002": _apply_op002,
    "HKRECON-OP-003": _apply_op003,
    "HKRECON-OP-004": _apply_op004,
    "HKRECON-OP-005": _apply_op005,
    "HKRECON-OP-006": _apply_op006,
    "HKRECON-OP-007": _apply_op007,
    "HKRECON-OP-008": _apply_op008,
}


def _apply_operation(
    tree: _Tree, operation: dict[str, JsonValue], context: _ExecutionContext
) -> _AppliedOperation:
    operation_type = _text(operation.get("operation_type_id"), "operation type")
    handler = _OPERATION_HANDLERS.get(operation_type)
    if handler is None:
        _fail_precondition("UNSUPPORTED_RECONSTRUCTION_OPERATION")
    result = handler(tree, operation, context)
    try:
        tree.seal()
    except RulebookError as error:
        reason = "RECONSTRUCTION_CANONICAL_TREE_INVALID"
        raise _PreconditionFailure(reason, result.target_node_ids) from error
    return result


def _not_run_result(
    language: AuthenticLanguage, operation: dict[str, JsonValue]
) -> ReconstructionOperationResult:
    return ReconstructionOperationResult(
        language=language,
        operation_instance_id=_text(operation.get("operation_instance_id"), "operation ID"),
        operation_type_id=_text(operation.get("operation_type_id"), "operation type"),
        atomic_group_id=_text(operation.get("atomic_group_id"), "atomic group"),
        result="NOT_RUN_AFTER_ATOMIC_FAILURE",
        actual_target_count=0,
        matched_location_ids=(),
        matched_source_unit_ids=(),
        actual_before_state_fingerprint=None,
        actual_after_state_fingerprint=None,
        provisional_output_tree_fingerprint=None,
        reason_codes=("RECONSTRUCTION_NOT_RUN_AFTER_ATOMIC_FAILURE",),
        atomic_group_result="NOT_RUN",
    )


def _operation_result(
    language: AuthenticLanguage,
    operation: dict[str, JsonValue],
    applied: _AppliedOperation,
    tree: _Tree,
) -> ReconstructionOperationResult:
    return ReconstructionOperationResult(
        language=language,
        operation_instance_id=_text(operation.get("operation_instance_id"), "operation ID"),
        operation_type_id=_text(operation.get("operation_type_id"), "operation type"),
        atomic_group_id=_text(operation.get("atomic_group_id"), "atomic group"),
        result="APPLIED",
        actual_target_count=len(applied.target_node_ids),
        matched_location_ids=applied.matched_location_ids,
        matched_source_unit_ids=applied.matched_source_unit_ids,
        actual_before_state_fingerprint=applied.before_content_fingerprint,
        actual_after_state_fingerprint=applied.after_content_fingerprint,
        provisional_output_tree_fingerprint=_tree_fingerprint(tree),
        reason_codes=("RECONSTRUCTION_OPERATION_APPLIED",),
        atomic_group_result="APPLIED",
    )


def _failed_result(
    language: AuthenticLanguage,
    operation: dict[str, JsonValue],
    failure: _PreconditionFailure,
    before_tree: _Tree,
) -> ReconstructionOperationResult:
    target_set = set(failure.target_node_ids)
    targets = tuple(node for node in before_tree.nodes if node.tree_node_id in target_set)
    before = _state_fingerprints(before_tree, targets)[1] if targets else None
    return ReconstructionOperationResult(
        language=language,
        operation_instance_id=_text(operation.get("operation_instance_id"), "operation ID"),
        operation_type_id=_text(operation.get("operation_type_id"), "operation type"),
        atomic_group_id=_text(operation.get("atomic_group_id"), "atomic group"),
        result="FAILED_PRECONDITION",
        actual_target_count=len(targets),
        matched_location_ids=_location_ids(targets),
        matched_source_unit_ids=(),
        actual_before_state_fingerprint=before,
        actual_after_state_fingerprint=None,
        provisional_output_tree_fingerprint=None,
        reason_codes=(failure.reason_code,),
        atomic_group_result="FAILED",
    )


def _validate_execution_authority(
    plan: dict[str, JsonValue], decision: ReconstructionPlanValidationDecision
) -> tuple[str, str]:
    plan_id = _text(plan.get("reconstruction_plan_id"), "Plan ID")
    plan_fingerprint = _fingerprint(plan)
    if (
        decision.processing_outcome != "PASS"
        or decision.plan_validation_result != "VALIDATED"
        or decision.reason_code != "HKLEG_RECON_PLAN_VALIDATED"
        or decision.candidate_plan_fingerprint != plan_fingerprint
        or decision.validated_reconstruction_plan_id != plan_id
        or decision.validated_reconstruction_plan_fingerprint != plan_fingerprint
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "Plan validation decision")
    return plan_id, plan_fingerprint


def _renderer_contract(package_root: Path) -> _RendererContract:
    raw = (package_root / _RENDERER_PATH).read_bytes()
    document = _object(parse_json_bytes(raw, max_bytes=100_000), "renderer declaration")
    if (
        document.get("status") != "FROZEN_PARTIAL_CONFORMANCE"
        or document.get("scope_activation_authority") != "NONE"
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "renderer declaration")
    reference: RefSignature = (
        _text(document.get("renderer_id"), "renderer ID"),
        _text(document.get("version"), "renderer version"),
        _bytes_fingerprint(raw),
    )
    supported = frozenset(
        _strings(document.get("supported_structural_types"), "renderer structures")
    )
    supported_units = frozenset(
        _strings(document.get("supported_location_unit_kinds"), "renderer source units")
    )
    if not supported or not supported_units:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "renderer structures")
    return _RendererContract(reference, supported, supported_units)


def _execution_registry(request: ReconstructionExecutionRequest) -> SchemaRegistry:
    registry = SchemaRegistry.from_contracts_root(request.package_root / "contracts")
    try:
        registry.validate(
            checked_json_value(request.document()),
            f"{_EXECUTION_SCHEMA}#/$defs/execution_request",
        )
        registry.validate(checked_json_value(request.plan), _PLAN_SCHEMA)
        registry.validate(checked_json_value(request.bilingual_alignment_map), _ALIGNMENT_SCHEMA)
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "execution contract") from error
    return registry


def reconstruction_execution_request_from_document(
    package_root: Path,
    document: dict[str, JsonValue],
) -> ReconstructionExecutionRequest:
    """Parse one closed path-free execution request after schema validation."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    try:
        registry.validate(
            checked_json_value(document),
            f"{_EXECUTION_SCHEMA}#/$defs/execution_request",
        )
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "execution request") from error
    decision = _object(document.get("validation_decision"), "validation decision")
    reason_codes = _strings(decision.get("reason_codes"), "validation reason codes")
    if reason_codes != ("HKLEG_RECON_PLAN_VALIDATED",):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "validation reason codes")
    validation_decision = ReconstructionPlanValidationDecision(
        fixture_id=_text(decision.get("fixture_id"), "validation fixture ID"),
        processing_outcome="PASS",
        legal_disposition="NOT_APPLICABLE",
        source_contract_review_required=False,
        reason_code=reason_codes[0],
        candidate_plan_fingerprint=_text(
            decision.get("candidate_plan_fingerprint"),
            "candidate Plan fingerprint",
        ),
        plan_validation_result="VALIDATED",
        validated_reconstruction_plan_id=_text(
            decision.get("validated_reconstruction_plan_id"),
            "validated Plan ID",
        ),
        validated_reconstruction_plan_fingerprint=_text(
            decision.get("validated_reconstruction_plan_fingerprint"),
            "validated Plan fingerprint",
        ),
        validated_operation_count=_integer(
            decision.get("validated_operation_count"),
            "validated operation count",
        ),
        next_action="CHECK_RECONSTRUCTION_CAPABILITY_AND_EXECUTE_PLAN",
    )
    return ReconstructionExecutionRequest(
        package_root=package_root,
        plan=_object(document.get("plan"), "Plan"),
        validation_decision=validation_decision,
        language_inputs=_objects(document.get("language_inputs"), "language inputs"),
        source_artifacts=_objects(document.get("source_artifacts"), "source artifacts"),
        bilingual_alignment_map=_object(
            document.get("bilingual_alignment_map"),
            "bilingual alignment map",
        ),
        execution_mode="OFFLINE_SYNTHETIC_CONFORMANCE",
    )


def _language_inputs(
    request: ReconstructionExecutionRequest,
) -> dict[str, dict[str, JsonValue]]:
    result: dict[str, dict[str, JsonValue]] = {}
    for item in request.language_inputs:
        _expect_keys(item, frozenset(("language", "base_tree_ref", "base_tree")), "language input")
        language = _text(item.get("language"), "input language")
        if language in result:
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "input language")
        result[language] = item
    if tuple(result) != _LANGUAGES:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "input languages")
    return result


def _parse_execution_stream(
    registry: SchemaRegistry,
    stream: dict[str, JsonValue],
    input_item: dict[str, JsonValue],
) -> tuple[_Tree, tuple[dict[str, JsonValue], ...]]:
    language = _text(stream.get("language"), "stream language")
    document = _object(input_item.get("base_tree"), "base tree")
    try:
        registry.validate(checked_json_value(document), _TREE_SCHEMA)
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "base tree schema") from error
    canonical = parse_canonical_language_tree(document)
    tree = _Tree.from_canonical(canonical)
    base_ref = _object(stream.get("base_language_tree_ref"), "base tree reference")
    input_ref = _object(input_item.get("base_tree_ref"), "input base tree")
    if (
        tree.language != language
        or not _same_ref(input_ref, base_ref)
        or _ref_signature(base_ref)[2] != canonical.fingerprint
        or stream.get("base_language_tree_fingerprint") != canonical.fingerprint
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "base tree fingerprint")
    return tree, _objects(stream.get("operations"), "Plan operations")


def _execution_streams(
    request: ReconstructionExecutionRequest,
    registry: SchemaRegistry,
) -> tuple[tuple[_Tree, tuple[dict[str, JsonValue], ...]], ...]:
    streams = _objects(request.plan.get("language_streams"), "Plan language streams")
    if tuple(_text(stream.get("language"), "stream language") for stream in streams) != _LANGUAGES:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "Plan languages")
    inputs = _language_inputs(request)
    return tuple(
        _parse_execution_stream(
            registry,
            stream,
            inputs[_text(stream.get("language"), "stream language")],
        )
        for stream in streams
    )


def _validate_source_inventory(
    request: ReconstructionExecutionRequest,
    parsed: tuple[tuple[_Tree, tuple[dict[str, JsonValue], ...]], ...],
) -> dict[RefSignature, dict[str, JsonValue]]:
    inventory = _source_inventory(request.source_artifacts)
    declared = {
        _ref_signature(ref)
        for _, operations in parsed
        for operation in operations
        for ref in _objects(operation.get("source_unit_refs"), "operation source units")
    }
    if declared != set(inventory):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "declared source inventory")
    return inventory


def _reference_set(
    document: dict[str, JsonValue],
    key: str,
) -> set[RefSignature]:
    return {_ref_signature(ref) for ref in _objects(document.get(key), f"Plan {key}")}


def _validate_plan_operation_closure(
    plan: dict[str, JsonValue],
    parsed: tuple[tuple[_Tree, tuple[dict[str, JsonValue], ...]], ...],
) -> None:
    closure = _object(plan.get("dependency_closure"), "Plan dependency closure")
    primary = _reference_set(closure, "primary_affected_location_refs")
    governing = _reference_set(closure, "governing_context_location_refs")
    dependent = _reference_set(closure, "dependent_location_refs")
    independent = _reference_set(closure, "independent_sibling_boundary_refs")
    affected = {
        _ref_signature(ref)
        for ref in _objects(
            plan.get("affected_legal_location_refs"),
            "Plan affected locations",
        )
    }
    closure_sets = (primary, governing, dependent)
    if (
        not primary
        or primary | governing | dependent != affected
        or any(
            left & right
            for index, left in enumerate(closure_sets)
            for right in closure_sets[index + 1 :]
        )
        or affected & independent
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "Plan dependency closure")
    for _, operations in parsed:
        for operation in operations:
            selector = _selector(operation)
            operation_locations = {
                _ref_signature(_object(selector.get("legal_location_ref"), "selector location")),
                *(
                    _ref_signature(ref)
                    for ref in _objects(
                        _before_state(operation).get("location_refs"),
                        "before locations",
                    )
                ),
                *(
                    _ref_signature(ref)
                    for ref in _objects(
                        _after_state(operation).get("location_refs"),
                        "after locations",
                    )
                ),
                *(
                    _ref_signature(ref)
                    for ref in _objects(
                        operation.get("dependency_location_refs"),
                        "operation dependency locations",
                    )
                ),
            }
            if not operation_locations <= affected or operation_locations & independent:
                raise RulebookError(
                    RulebookErrorCode.CONTRACT_MISMATCH,
                    "operation dependency closure",
                )


def _validate_plan_and_inputs(
    request: ReconstructionExecutionRequest,
) -> tuple[
    str,
    str,
    tuple[tuple[_Tree, tuple[dict[str, JsonValue], ...]], ...],
    _ExecutionContext,
]:
    registry = _execution_registry(request)
    plan_id, plan_fingerprint = _validate_execution_authority(
        request.plan, request.validation_decision
    )
    parsed = _execution_streams(request, registry)
    _validate_plan_operation_closure(request.plan, parsed)
    if request.validation_decision.validated_operation_count != sum(
        len(operations) for _, operations in parsed
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "validated operation count")
    inventory = _validate_source_inventory(request, parsed)
    return (
        plan_id,
        plan_fingerprint,
        parsed,
        _ExecutionContext(inventory, _renderer_contract(request.package_root)),
    )


def _blocked_execution(
    *,
    reason_code: str,
    plan_id: str,
    plan_fingerprint: str,
    execution_mode: Literal["OFFLINE_SYNTHETIC_CONFORMANCE"],
    results: tuple[ReconstructionOperationResult, ...],
) -> ReconstructionPlanExecution:
    rolled_back = tuple(
        replace(result, atomic_group_result="ROLLED_BACK") if result.result == "APPLIED" else result
        for result in results
    )
    return ReconstructionPlanExecution(
        "BLOCK",
        reason_code,
        plan_id,
        plan_fingerprint,
        execution_mode,
        rolled_back,
        (),
        (),
        None,
        None,
    )


def _run_operations(
    parsed: tuple[tuple[_Tree, tuple[dict[str, JsonValue], ...]], ...],
    context: _ExecutionContext,
) -> tuple[tuple[ReconstructionOperationResult, ...], str | None]:
    results: list[ReconstructionOperationResult] = []
    failure_reason: str | None = None
    for tree, operations in parsed:
        for operation in operations:
            if failure_reason is not None:
                results.append(_not_run_result(tree.language, operation))
                continue
            if _text(operation.get("operation_type_id"), "operation type") not in _OPERATION_IDS:
                failure = _PreconditionFailure("UNSUPPORTED_RECONSTRUCTION_OPERATION")
                results.append(_failed_result(tree.language, operation, failure, tree))
                failure_reason = failure.reason_code
                continue
            before_tree = _Tree.from_canonical(tree.seal())
            try:
                applied = _apply_operation(tree, operation, context)
                results.append(_operation_result(tree.language, operation, applied, tree))
            except _PreconditionFailure as failure:
                results.append(_failed_result(tree.language, operation, failure, before_tree))
                failure_reason = failure.reason_code
    return tuple(results), failure_reason


def _final_tree_failure_reason(
    final_trees: tuple[CanonicalLanguageTree, ...],
    streams: tuple[dict[str, JsonValue], ...],
) -> str | None:
    for tree, stream in zip(final_trees, streams, strict=True):
        document = tree.document()
        if tree.fingerprint != stream.get("expected_final_language_tree_fingerprint"):
            return "RECONSTRUCTION_FINAL_TREE_MISMATCH"
        if canonical_source_unit_inventory_fingerprint(document) != stream.get(
            "expected_complete_source_unit_inventory_fingerprint"
        ):
            return "RECONSTRUCTION_SOURCE_UNIT_INVENTORY_MISMATCH"
    return None


def _validated_final_alignment(
    request: ReconstructionExecutionRequest,
    final_trees: tuple[CanonicalLanguageTree, ...],
    streams: tuple[dict[str, JsonValue], ...],
) -> BilingualAlignmentMap | None:
    try:
        alignment = parse_bilingual_alignment_map(
            request.bilingual_alignment_map,
            en_tree=final_trees[0],
            zh_hant_tree=final_trees[1],
        )
    except RulebookError:
        return None
    alignment_refs = tuple(
        _object(stream.get("expected_bilingual_alignment_map_ref"), "alignment reference")
        for stream in streams
    )
    if (
        not _same_ref(alignment_refs[0], alignment_refs[1])
        or _ref_signature(alignment_refs[0])[2] != alignment.fingerprint
    ):
        return None
    return alignment


def execute_validated_reconstruction_plan(
    request: ReconstructionExecutionRequest,
) -> ReconstructionPlanExecution:
    """Execute one validated Plan transactionally without issuing Report/artifact IDs."""
    if request.execution_mode != _OFFLINE_EXECUTION_MODE:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "execution mode")
    plan_id, plan_fingerprint, parsed, context = _validate_plan_and_inputs(request)
    results, failure_reason = _run_operations(parsed, context)
    if failure_reason is not None:
        return _blocked_execution(
            reason_code=failure_reason,
            plan_id=plan_id,
            plan_fingerprint=plan_fingerprint,
            execution_mode=request.execution_mode,
            results=results,
        )
    final_trees = tuple(tree.seal() for tree, _ in parsed)
    streams = _objects(request.plan.get("language_streams"), "Plan language streams")
    final_failure = _final_tree_failure_reason(final_trees, streams)
    if final_failure is not None:
        return _blocked_execution(
            reason_code=final_failure,
            plan_id=plan_id,
            plan_fingerprint=plan_fingerprint,
            execution_mode=request.execution_mode,
            results=results,
        )
    alignment = _validated_final_alignment(request, final_trees, streams)
    if alignment is None:
        return _blocked_execution(
            reason_code="RECONSTRUCTION_BILINGUAL_ALIGNMENT_MISMATCH",
            plan_id=plan_id,
            plan_fingerprint=plan_fingerprint,
            execution_mode=request.execution_mode,
            results=results,
        )
    return ReconstructionPlanExecution(
        "PASS",
        "RECONSTRUCTION_OPERATIONS_PROVISIONALLY_COMPLETE",
        plan_id,
        plan_fingerprint,
        request.execution_mode,
        results,
        tuple(tree.document() for tree in final_trees),
        tuple(tree.fingerprint for tree in final_trees),
        alignment.document(),
        alignment.fingerprint,
    )


def _read_package_object(path: Path) -> dict[str, JsonValue]:
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_MEMBER_BYTES:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "package member bytes")
    return _object(parse_json_bytes(raw, max_bytes=_MAX_MEMBER_BYTES), "package member")


def _safe_package_member(package_root: Path, relative: str) -> Path:
    member = PurePosixPath(relative)
    if (
        not relative
        or member.is_absolute()
        or member.as_posix() != relative
        or ".." in member.parts
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "package member path")
    path = package_root.joinpath(*member.parts)
    resolved_root = package_root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents or not path.is_file() or path.is_symlink():
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "package member path")
    return path


def _validate_execution_document(
    registry: SchemaRegistry,
    document: dict[str, JsonValue],
    definition: str,
    label: str,
) -> None:
    try:
        registry.validate(
            checked_json_value(document),
            f"{_EXECUTION_SCHEMA}#/$defs/{definition}",
        )
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label) from error


def _validate_execution_package_declarations(
    package_root: Path,
    registry: SchemaRegistry,
) -> None:
    reasons = _read_package_object(
        package_root / "catalogues/reconstruction-execution-reason-codes.json"
    )
    _validate_execution_document(registry, reasons, "reason_code_catalogue", "reason catalogue")
    declared = {
        _text(item.get("code"), "execution reason code")
        for item in _objects(reasons.get("reason_codes"), "execution reason codes")
    }
    if frozenset(declared) != _EXECUTION_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "execution reason catalogue")
    rule = _read_package_object(package_root / f"rules/{HK_RECONSTRUCTION_EXECUTION_RULE_ID}.json")
    _validate_execution_document(registry, rule, "rule", "execution rule")
    if rule.get("rule_id") != HK_RECONSTRUCTION_EXECUTION_RULE_ID:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "execution rule")


def _execution_fixture_paths(
    package_root: Path,
    entry: dict[str, JsonValue],
) -> tuple[str, Path, Path]:
    fixture_id = _text(entry.get("fixture_id"), "execution fixture ID")
    fixture_path = _safe_package_member(
        package_root,
        _text(entry.get("path"), "execution fixture path"),
    )
    expected_path = _safe_package_member(
        package_root,
        _text(entry.get("expected_path"), "execution expected path"),
    )
    if _bytes_fingerprint(fixture_path.read_bytes()) != entry.get(
        "fixture_fingerprint"
    ) or _bytes_fingerprint(expected_path.read_bytes()) != entry.get("expected_fingerprint"):
        raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
    return fixture_id, fixture_path, expected_path


def _prove_execution_fixture(
    package_root: Path,
    registry: SchemaRegistry,
    entry: dict[str, JsonValue],
) -> ReconstructionPlanExecution:
    fixture_id, fixture_path, expected_path = _execution_fixture_paths(package_root, entry)
    fixture = _read_package_object(fixture_path)
    _validate_execution_document(registry, fixture, "fixture", "execution fixture")
    if fixture.get("fixture_id") != fixture_id:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
    declaration = _object(fixture.get("expected_artifact"), "expected artifact")
    if declaration.get("path") != entry.get("expected_path") or declaration.get(
        "fingerprint"
    ) != entry.get("expected_fingerprint"):
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
    request_document = _object(fixture.get("input"), "execution fixture input")
    if _fingerprint(request_document) != fixture.get("input_fingerprint"):
        raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "execution fixture input")
    request = reconstruction_execution_request_from_document(package_root, request_document)
    if request.validation_decision.fixture_id != fixture_id:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "validation authority")
    result = execute_validated_reconstruction_plan(request)
    result_document = result.document()
    _validate_execution_document(registry, result_document, "execution_result", "execution result")
    expected = _read_package_object(expected_path)
    _validate_execution_document(registry, expected, "execution_result", "expected execution")
    if canonicalize(checked_json_value(result_document)) != canonicalize(
        checked_json_value(expected)
    ):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
    return result


def prove_hk_reconstruction_execution(
    package_root: Path,
) -> tuple[ReconstructionPlanExecution, ...]:
    """Re-execute every frozen canonical Plan-execution fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_execution_package_declarations(package_root, registry)
    catalogue = _read_package_object(
        package_root / "catalogues/reconstruction-execution-fixtures.json"
    )
    _validate_execution_document(registry, catalogue, "fixture_catalogue", "fixture catalogue")
    results: list[ReconstructionPlanExecution] = []
    seen: set[str] = set()
    for entry in _objects(catalogue.get("fixtures"), "execution fixtures"):
        fixture_id = _text(entry.get("fixture_id"), "execution fixture ID")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        results.append(_prove_execution_fixture(package_root, registry, entry))
    if len(results) != _FROZEN_FIXTURE_COUNT:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "execution fixtures")
    return tuple(results)
