"""Immutable ADR 0085 reconstructed-consolidation artifact construction.

This module consumes only a successful effect-free canonical Plan execution.
It builds the eleven fixed package members in memory and emits no Execution
Report, Search Record, provider request, filesystem write, or external effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Never

from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.errors import ContractViolation
from asklegal_contracts.json_types import checked_json_value

from .hk_canonical_legislation import (
    CanonicalLanguageTree,
    CanonicalSourceUnit,
    CanonicalTreeNode,
    canonical_source_unit_inventory_fingerprint,
    parse_bilingual_alignment_map,
    parse_canonical_language_tree,
)
from .hk_reconstruction_execution import ReconstructionPlanExecution
from .model import RulebookError, RulebookErrorCode

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

RECONSTRUCTED_ARTIFACT_SCHEMA = (
    "https://contracts.asklegal.local/v1/"
    "hk-legislation-reconstructed-consolidation-artifact.schema.json"
)
RECONSTRUCTED_ARTIFACT_CONTRACT_VERSION = "1.0.0"
_SCHEMA = "schemas/reconstructed-consolidation-artifact.schema.json"
_PLAN_SCHEMA = "schemas/reconstruction-plan-validation.schema.json#/$defs/plan"
_EXECUTION_SCHEMA = "schemas/reconstruction-execution.schema.json#/$defs/execution_result"
_LANGUAGES = ("en", "zh-Hant")
_JSON_MEDIA = "application/json"
_JSONL_MEDIA = "application/x-ndjson"
_MAX_MEMBER_BYTES = 8_000_000
_FILE_ROLES = {
    "trees/en.json": ("TREE_EN", _JSON_MEDIA),
    "trees/zh-Hant.json": ("TREE_ZH_HANT", _JSON_MEDIA),
    "source-units/en.jsonl": ("SOURCE_UNITS_EN", _JSONL_MEDIA),
    "source-units/zh-Hant.jsonl": ("SOURCE_UNITS_ZH_HANT", _JSONL_MEDIA),
    "reconstructed-location-units.jsonl": ("RECONSTRUCTED_LOCATION_UNITS", _JSONL_MEDIA),
    "bilingual-alignment-map.json": ("BILINGUAL_ALIGNMENT_MAP", _JSON_MEDIA),
    "dependency-closure-proof.json": ("DEPENDENCY_CLOSURE_PROOF", _JSON_MEDIA),
    "source-unit-coverage-proof.json": ("SOURCE_UNIT_COVERAGE_PROOF", _JSON_MEDIA),
    "derivation-map.json": ("DERIVATION_MAP", _JSON_MEDIA),
    "identity-lineage-result.json": ("IDENTITY_LINEAGE_RESULT", _JSON_MEDIA),
}
_SHARED_CONTRACT_KEYS = {
    "source_rulebook": "source_rulebook",
    "operation_registry": "operation_registry",
    "source_tree": "tree",
    "renderer": "renderer",
    "identity": "identity",
    "traceability": "traceability",
}

type RefSignature = tuple[str, str, str]
type AuthenticLanguage = Literal["en", "zh-Hant"]


def _fail(detail: str) -> Never:
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail)


def _object(value: JsonValue | None, detail: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        _fail(detail)
    return value


def _objects(value: JsonValue | None, detail: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        _fail(detail)
    return tuple(item for item in value if isinstance(item, dict))


def _strings(value: JsonValue | None, detail: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _fail(detail)
    result = tuple(item for item in value if isinstance(item, str))
    if len(result) != len(set(result)):
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


def _checked_object(value: object) -> dict[str, JsonValue]:
    result = checked_json_value(value)
    if not isinstance(result, dict):
        message = "expected JSON object"
        raise TypeError(message)
    return result


def _fingerprint(value: JsonValue) -> str:
    return f"sha256:{sha256(canonicalize(value)).hexdigest()}"


def _raw_fingerprint(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _json_bytes(value: JsonValue) -> bytes:
    return canonicalize(value)


def _jsonl_bytes(rows: tuple[dict[str, JsonValue], ...]) -> bytes:
    if not rows:
        _fail("empty JSONL member")
    return b"".join(canonicalize(checked_json_value(row)) + b"\n" for row in rows)


def _ref_signature(value: dict[str, JsonValue]) -> RefSignature:
    return (
        _text(value.get("ref_type"), "reference type"),
        _text(value.get("ref_id"), "reference ID"),
        _text(value.get("fingerprint"), "reference fingerprint"),
    )


def _contract_signature(value: dict[str, JsonValue]) -> RefSignature:
    return (
        _text(value.get("contract_id"), "contract ID"),
        _text(value.get("version"), "contract version"),
        _text(value.get("fingerprint"), "contract fingerprint"),
    )


def _sorted_refs(values: tuple[dict[str, JsonValue], ...]) -> list[dict[str, JsonValue]]:
    return sorted(values, key=_ref_signature)


@dataclass(frozen=True, slots=True)
class ReconstructionArtifactBuildRequest:
    """Exact authority and canonical inputs for one in-memory artifact build."""

    package_root: Path
    reconstructed_consolidation_artifact_id: str
    plan: dict[str, JsonValue]
    execution: ReconstructionPlanExecution
    base_language_trees: tuple[dict[str, JsonValue], ...]
    coverage_gap_ref: dict[str, JsonValue]
    identity_lineage_decision_ref: dict[str, JsonValue]
    operative_state_decision_ref: dict[str, JsonValue]
    contracts: dict[str, JsonValue]
    authority_note_template_contract_ref: dict[str, JsonValue]
    lineage_links: tuple[dict[str, JsonValue], ...]


@dataclass(frozen=True, slots=True)
class ReconstructedConsolidationArtifact:
    """One complete immutable in-memory eleven-file ADR 0085 package."""

    reconstructed_consolidation_artifact_id: str
    root_fingerprint: str
    inventory: tuple[dict[str, JsonValue], ...]
    files: tuple[tuple[str, bytes], ...]

    def file_bytes(self, path: str) -> bytes:
        """Return one exact member without filesystem discovery."""
        matches = [raw for member, raw in self.files if member == path]
        if len(matches) != 1:
            _fail("artifact member")
        return matches[0]

    def artifact_ref(self) -> dict[str, JsonValue]:
        """Return the root-fingerprint-bound immutable artifact reference."""
        return {
            "ref_type": "RECONSTRUCTED_CONSOLIDATION_ARTIFACT",
            "ref_id": self.reconstructed_consolidation_artifact_id,
            "fingerprint": self.root_fingerprint,
        }

    def member_ref(self, path: str) -> dict[str, JsonValue]:
        """Return one exact package-member reference bound to the root artifact."""
        matches = [entry for entry in self.inventory if entry.get("path") == path]
        if len(matches) != 1:
            _fail("artifact member reference")
        entry = matches[0]
        return {
            "reconstructed_consolidation_artifact_ref": self.artifact_ref(),
            "role": entry["role"],
            "path": entry["path"],
            "media_type": entry["media_type"],
            "byte_size": entry["byte_size"],
            "fingerprint": entry["fingerprint"],
        }

    def document(self) -> dict[str, JsonValue]:
        """Return a byte-free package result projection."""
        return {
            "reconstructed_consolidation_artifact_ref": self.artifact_ref(),
            "root_fingerprint": self.root_fingerprint,
            "inventory": list(self.inventory),
            "files": {path: _raw_fingerprint(raw) for path, raw in self.files},
            "report_output": "NONE",
            "record_output": "NONE",
            "external_effects": "NONE",
        }


@dataclass(frozen=True, slots=True)
class _BuildContext:
    request: ReconstructionArtifactBuildRequest
    plan_ref: dict[str, JsonValue]
    base_trees: tuple[CanonicalLanguageTree, ...]
    final_trees: tuple[CanonicalLanguageTree, ...]
    alignment: dict[str, JsonValue]
    operations: dict[str, dict[str, JsonValue]]
    operation_results: dict[str, tuple[dict[str, JsonValue], ...]]


def _validate_schema(
    registry: SchemaRegistry,
    value: JsonValue,
    schema: str,
    detail: str,
) -> None:
    try:
        registry.validate(value, schema)
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail) from error


def _plan_operations(plan: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    result: dict[str, dict[str, JsonValue]] = {}
    for stream in _objects(plan.get("language_streams"), "Plan language streams"):
        for operation in _objects(stream.get("operations"), "Plan operations"):
            operation_id = _text(operation.get("operation_instance_id"), "operation ID")
            if operation_id in result:
                _fail("duplicate Plan operation")
            result[operation_id] = operation
    return result


def _operation_result_documents(
    execution: ReconstructionPlanExecution,
) -> dict[str, tuple[dict[str, JsonValue], ...]]:
    result: dict[str, list[dict[str, JsonValue]]] = {language: [] for language in _LANGUAGES}
    for operation in execution.operation_results:
        result[operation.language].append(operation.document())
    return {language: tuple(result[language]) for language in _LANGUAGES}


def _build_context(request: ReconstructionArtifactBuildRequest) -> _BuildContext:
    registry = SchemaRegistry.from_contracts_root(request.package_root / "contracts")
    _validate_schema(registry, checked_json_value(request.plan), _PLAN_SCHEMA, "artifact Plan")
    _validate_schema(
        registry,
        checked_json_value(request.execution.document()),
        _EXECUTION_SCHEMA,
        "artifact execution",
    )
    plan_id = _text(request.plan.get("reconstruction_plan_id"), "Plan ID")
    plan_fingerprint = _fingerprint(request.plan)
    if (
        request.execution.processing_outcome != "PASS"
        or request.execution.reconstruction_plan_id != plan_id
        or request.execution.reconstruction_plan_fingerprint != plan_fingerprint
        or len(request.base_language_trees) != len(_LANGUAGES)
        or len(request.execution.provisional_language_trees) != len(_LANGUAGES)
    ):
        _fail("artifact execution authority")
    base_trees = tuple(
        parse_canonical_language_tree(document) for document in request.base_language_trees
    )
    final_trees = tuple(
        parse_canonical_language_tree(document)
        for document in request.execution.provisional_language_trees
    )
    if (
        tuple(tree.language for tree in base_trees) != _LANGUAGES
        or tuple(tree.language for tree in final_trees) != _LANGUAGES
    ):
        _fail("artifact languages")
    alignment_document = request.execution.provisional_bilingual_alignment_map
    if alignment_document is None:
        _fail("artifact alignment")
    alignment = parse_bilingual_alignment_map(
        alignment_document,
        en_tree=final_trees[0],
        zh_hant_tree=final_trees[1],
    ).document()
    plan_ref: dict[str, JsonValue] = {
        "ref_type": "RECONSTRUCTION_PLAN",
        "ref_id": plan_id,
        "fingerprint": plan_fingerprint,
    }
    return _BuildContext(
        request,
        plan_ref,
        base_trees,
        final_trees,
        alignment,
        _plan_operations(request.plan),
        _operation_result_documents(request.execution),
    )


def _operation_unit_map(
    results: tuple[dict[str, JsonValue], ...],
) -> dict[str, tuple[str, ...]]:
    mutable: dict[str, list[str]] = {}
    for result in results:
        if result.get("result") != "APPLIED":
            _fail("non-applied successful operation")
        operation_id = _text(result.get("operation_instance_id"), "operation result ID")
        for unit_id in _strings(
            result.get("matched_source_unit_ids"),
            "matched source-unit IDs",
        ):
            mutable.setdefault(unit_id, []).append(operation_id)
    return {unit_id: tuple(operation_ids) for unit_id, operation_ids in mutable.items()}


def _operation_sources(
    operation_ids: tuple[str, ...],
    operations: dict[str, dict[str, JsonValue]],
) -> list[dict[str, JsonValue]]:
    by_signature: dict[RefSignature, dict[str, JsonValue]] = {}
    for operation_id in operation_ids:
        operation = operations.get(operation_id)
        if operation is None:
            _fail("operation source ownership")
        for ref in _objects(operation.get("source_unit_refs"), "operation source refs"):
            by_signature[_ref_signature(ref)] = ref
    return [by_signature[key] for key in sorted(by_signature)]


@dataclass(frozen=True, slots=True)
class _LanguageDerivationContext:
    language: str
    base_units: dict[str, CanonicalSourceUnit]
    build: _BuildContext


def _derivation_entry(
    state: _LanguageDerivationContext,
    index: int,
    unit: CanonicalSourceUnit,
    operation_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    base = state.base_units.get(unit.source_unit_id)
    entry_id = f"der_{state.language.replace('-', '_')}_{index:06d}"
    if operation_ids:
        primary = operation_ids[-1]
        result = next(
            item
            for item in state.build.operation_results[state.language]
            if item.get("operation_instance_id") == primary
        )
        return _checked_object(
            {
                "derivation_entry_id": entry_id,
                "language": state.language,
                "source_unit_id": unit.source_unit_id,
                "tree_node_id": unit.tree_node_id,
                "derivation_class": "OPERATION_RESULT_UNIT",
                "base_source_unit_id": base.source_unit_id if base is not None else None,
                "primary_operation_instance_id": primary,
                "prior_operation_instance_ids": list(operation_ids[:-1]),
                "amendment_source_unit_refs": _operation_sources(
                    operation_ids,
                    state.build.operations,
                ),
                "before_state_fingerprint": result.get("actual_before_state_fingerprint"),
                "final_content_fingerprint": unit.content_fingerprint,
            }
        )
    if base is None or base.document() != unit.document():
        _fail("unaccounted final source unit")
    return _checked_object(
        {
            "derivation_entry_id": entry_id,
            "language": state.language,
            "source_unit_id": unit.source_unit_id,
            "tree_node_id": unit.tree_node_id,
            "derivation_class": "UNCHANGED_BASE_UNIT",
            "base_source_unit_id": unit.source_unit_id,
            "primary_operation_instance_id": None,
            "prior_operation_instance_ids": [],
            "amendment_source_unit_refs": [],
            "before_state_fingerprint": unit.content_fingerprint,
            "final_content_fingerprint": unit.content_fingerprint,
        }
    )


def _ancestor_ids(tree: CanonicalLanguageTree, node_id: str) -> tuple[str, ...]:
    by_id = {node.tree_node_id: node for node in tree.nodes}
    result: list[str] = []
    current = by_id.get(node_id)
    while current is not None:
        result.append(current.tree_node_id)
        current = by_id.get(current.parent_node_id or "")
    return tuple(result)


def _impacted_nodes(
    base: CanonicalLanguageTree,
    final: CanonicalLanguageTree,
    operation_unit_map: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    mutable: dict[str, list[str]] = {}
    for tree in (base, final):
        units = {unit.source_unit_id: unit for unit in tree.source_units}
        for unit_id, operation_ids in operation_unit_map.items():
            unit = units.get(unit_id)
            if unit is None:
                continue
            for node_id in _ancestor_ids(tree, unit.tree_node_id):
                bucket = mutable.setdefault(node_id, [])
                for operation_id in operation_ids:
                    if operation_id not in bucket:
                        bucket.append(operation_id)
    return {node_id: tuple(operation_ids) for node_id, operation_ids in mutable.items()}


def _structural_derivations(
    language: str,
    base: CanonicalLanguageTree,
    final: CanonicalLanguageTree,
    operation_unit_map: dict[str, tuple[str, ...]],
) -> tuple[dict[str, JsonValue], ...]:
    base_nodes = {node.tree_node_id: node for node in base.nodes}
    impacted = _impacted_nodes(base, final, operation_unit_map)
    rows: list[dict[str, JsonValue]] = []
    for node in final.nodes:
        operation_ids = impacted.get(node.tree_node_id, ())
        base_node = base_nodes.get(node.tree_node_id)
        if not operation_ids and (base_node is None or base_node.document() != node.document()):
            _fail("unaccounted final structure")
        rows.append(
            _checked_object(
                {
                    "language": language,
                    "tree_node_id": node.tree_node_id,
                    "derivation_class": (
                        "OPERATION_RESULT_NODE" if operation_ids else "UNCHANGED_BASE_NODE"
                    ),
                    "base_tree_node_id": base_node.tree_node_id if base_node else None,
                    "primary_operation_instance_id": operation_ids[-1] if operation_ids else None,
                    "prior_operation_instance_ids": list(operation_ids[:-1]),
                    "final_subtree_fingerprint": node.subtree_fingerprint,
                }
            )
        )
    return tuple(rows)


def _language_derivation(
    context: _BuildContext,
    language_index: int,
) -> tuple[
    tuple[dict[str, JsonValue], ...],
    tuple[dict[str, JsonValue], ...],
    dict[str, tuple[str, ...]],
]:
    language = _LANGUAGES[language_index]
    base = context.base_trees[language_index]
    final = context.final_trees[language_index]
    operation_map = _operation_unit_map(context.operation_results[language])
    base_units = {unit.source_unit_id: unit for unit in base.source_units}
    state = _LanguageDerivationContext(language, base_units, context)
    entries = tuple(
        _derivation_entry(state, index, unit, operation_map.get(unit.source_unit_id, ()))
        for index, unit in enumerate(final.source_units)
    )
    structures = _structural_derivations(language, base, final, operation_map)
    return entries, structures, operation_map


def _source_unit_rows(
    tree: CanonicalLanguageTree,
    derivations: tuple[dict[str, JsonValue], ...],
) -> tuple[dict[str, JsonValue], ...]:
    if len(tree.source_units) != len(derivations):
        _fail("source-unit derivation inventory")
    return tuple(
        _checked_object(
            {
                "source_unit": unit.document(),
                "derivation_entry_id": derivation["derivation_entry_id"],
            }
        )
        for unit, derivation in zip(tree.source_units, derivations, strict=True)
    )


def _closure_categories(
    plan: dict[str, JsonValue],
) -> tuple[
    tuple[dict[str, JsonValue], ...],
    tuple[dict[str, JsonValue], ...],
    tuple[dict[str, JsonValue], ...],
    tuple[dict[str, JsonValue], ...],
]:
    closure = _object(plan.get("dependency_closure"), "artifact dependency closure")
    return (
        _objects(closure.get("primary_affected_location_refs"), "primary locations"),
        _objects(closure.get("governing_context_location_refs"), "governing locations"),
        _objects(closure.get("dependent_location_refs"), "dependent locations"),
        _objects(closure.get("independent_sibling_boundary_refs"), "independent locations"),
    )


def _location_projection(
    tree: CanonicalLanguageTree,
    signature: RefSignature,
) -> tuple[tuple[CanonicalTreeNode, ...], tuple[CanonicalSourceUnit, ...], str]:
    nodes = tuple(
        node for node in tree.nodes if _ref_signature(node.legal_location_ref) == signature
    )
    units = tuple(
        unit for unit in tree.source_units if _ref_signature(unit.legal_location_ref) == signature
    )
    if not nodes or not units:
        _fail("artifact location language coverage")
    document = checked_json_value(
        {
            "nodes": [node.document() for node in nodes],
            "source_units": [unit.document() for unit in units],
        }
    )
    return nodes, units, _fingerprint(document)


def _location_rows(context: _BuildContext) -> tuple[dict[str, JsonValue], ...]:
    categories = _closure_categories(context.request.plan)
    roles = (
        "PRIMARY_AFFECTED_CONTENT",
        "REQUIRED_GOVERNING_CONTEXT",
        "DEPENDENT_REBUILT_CONTENT",
        "PROVEN_INDEPENDENT_BOUNDARY",
    )
    by_signature: dict[RefSignature, tuple[dict[str, JsonValue], str]] = {}
    for refs, role in zip(categories, roles, strict=True):
        for ref in refs:
            signature = _ref_signature(ref)
            if signature in by_signature:
                _fail("overlapping artifact location role")
            by_signature[signature] = (ref, role)
    en_order = {node.tree_node_id: index for index, node in enumerate(context.final_trees[0].nodes)}
    alignment_groups = _objects(context.alignment.get("groups"), "alignment groups")
    rows: list[dict[str, JsonValue]] = []
    for signature, (ref, role) in by_signature.items():
        en_present = any(
            _ref_signature(node.legal_location_ref) == signature
            for node in context.final_trees[0].nodes
        )
        zh_present = any(
            _ref_signature(node.legal_location_ref) == signature
            for node in context.final_trees[1].nodes
        )
        if en_present != zh_present:
            _fail("artifact bilingual location survival")
        if not en_present:
            continue
        en_nodes, en_units, en_fingerprint = _location_projection(context.final_trees[0], signature)
        zh_nodes, zh_units, zh_fingerprint = _location_projection(context.final_trees[1], signature)
        group_ids = [
            _text(group.get("alignment_group_id"), "alignment group ID")
            for group in alignment_groups
            if _ref_signature(_object(group.get("legal_location_ref"), "alignment location"))
            == signature
        ]
        if not group_ids:
            _fail("artifact location alignment")
        rows.append(
            _checked_object(
                {
                    "legal_item_ref": context.request.plan["legal_item_ref"],
                    "legal_location_ref": ref,
                    "applicability_decision_ref": context.request.plan[
                        "applicability_decision_ref"
                    ],
                    "operative_state_decision_ref": context.request.operative_state_decision_ref,
                    "en_tree_node_ids": [node.tree_node_id for node in en_nodes],
                    "en_source_unit_ids": [unit.source_unit_id for unit in en_units],
                    "zh_hant_tree_node_ids": [node.tree_node_id for node in zh_nodes],
                    "zh_hant_source_unit_ids": [unit.source_unit_id for unit in zh_units],
                    "bilingual_alignment_group_ids": group_ids,
                    "governing_location_refs": _sorted_refs(categories[1]),
                    "dependent_location_refs": _sorted_refs(categories[2]),
                    "source_order": min(en_order[node.tree_node_id] for node in en_nodes),
                    "structural_role": en_nodes[0].structural_type,
                    "en_location_fingerprint": en_fingerprint,
                    "zh_hant_location_fingerprint": zh_fingerprint,
                    "location_role": role,
                }
            )
        )
    rows.sort(key=lambda row: _integer(row.get("source_order"), "location source order"))
    return tuple(rows)


def _dependency_proof(
    context: _BuildContext,
    location_rows: tuple[dict[str, JsonValue], ...],
) -> dict[str, JsonValue]:
    categories = _closure_categories(context.request.plan)
    closure = _object(context.request.plan.get("dependency_closure"), "dependency closure")
    artifact_refs = tuple(
        _object(row.get("legal_location_ref"), "artifact location") for row in location_rows
    )
    expected = {_ref_signature(ref) for refs in categories for ref in refs}
    actual = {_ref_signature(ref) for ref in artifact_refs}
    by_signature = {_ref_signature(ref): ref for refs in categories for ref in refs}
    ended = expected - actual
    if actual - expected or actual & ended or actual | ended != expected:
        _fail("artifact dependency inventory")
    return _checked_object(
        {
            "$schema": "asklegal://contracts/hk-legislation/reconstruction-artifact/dependency-closure-proof/1.0.0",
            "contract_version": "1.0.0",
            "reconstruction_plan_ref": context.plan_ref,
            "primary_affected_location_refs": _sorted_refs(categories[0]),
            "governing_context_location_refs": _sorted_refs(categories[1]),
            "dependent_location_refs": _sorted_refs(categories[2]),
            "independent_sibling_boundary_refs": _sorted_refs(categories[3]),
            "artifact_location_refs": _sorted_refs(artifact_refs),
            "ended_location_refs": _sorted_refs(tuple(by_signature[key] for key in ended)),
            "dependency_rule": closure["dependency_rule"],
            "plan_closure_proof_fingerprint": closure["closure_proof_fingerprint"],
            "complete": True,
            "duplicate_free": True,
            "overlap_absent": True,
            "independent_boundaries_proved": True,
        }
    )


def _language_coverage(
    context: _BuildContext,
    language_index: int,
    operation_map: dict[str, tuple[str, ...]],
) -> dict[str, JsonValue]:
    language = _LANGUAGES[language_index]
    base = context.base_trees[language_index]
    final = context.final_trees[language_index]
    base_ids = {unit.source_unit_id for unit in base.source_units}
    final_ids = {unit.source_unit_id for unit in final.source_units}
    operation_ids = set(operation_map)
    unchanged = final_ids - operation_ids
    deleted = base_ids - final_ids
    if not deleted <= operation_ids or final_ids != unchanged | (final_ids & operation_ids):
        _fail("artifact source-unit coverage")
    ownership: list[dict[str, JsonValue]] = []
    for result in context.operation_results[language]:
        operation_id = _text(result.get("operation_instance_id"), "coverage operation")
        matched = set(_strings(result.get("matched_source_unit_ids"), "coverage units"))
        ownership.append(
            _checked_object(
                {
                    "operation_instance_id": operation_id,
                    "final_source_unit_ids": sorted(matched & final_ids),
                    "deleted_base_source_unit_ids": sorted(matched & deleted),
                }
            )
        )
    return _checked_object(
        {
            "language": language,
            "final_source_unit_ids": [unit.source_unit_id for unit in final.source_units],
            "final_source_unit_inventory_fingerprint": (
                canonical_source_unit_inventory_fingerprint(final.document())
            ),
            "unchanged_base_source_unit_ids": sorted(unchanged),
            "operation_result_source_unit_ids": sorted(final_ids & operation_ids),
            "deleted_base_source_unit_ids": sorted(deleted),
            "operation_ownership": ownership,
            "complete": True,
            "duplicate_free": True,
            "exact_once_primary_ownership": True,
        }
    )


def _source_unit_coverage_proof(
    context: _BuildContext,
    operation_maps: tuple[dict[str, tuple[str, ...]], ...],
) -> dict[str, JsonValue]:
    return _checked_object(
        {
            "$schema": "asklegal://contracts/hk-legislation/reconstruction-artifact/source-unit-coverage-proof/1.0.0",
            "contract_version": "1.0.0",
            "reconstruction_plan_ref": context.plan_ref,
            "languages": [
                _language_coverage(context, index, operation_maps[index]) for index in range(2)
            ],
            "repeated_serving_dependencies_primary_only": True,
            "all_deletions_accounted": True,
        }
    )


def _identity_result(context: _BuildContext) -> dict[str, JsonValue]:
    base_locations = {
        _ref_signature(node.legal_location_ref): node.legal_location_ref
        for tree in context.base_trees
        for node in tree.nodes
    }
    final_locations = {
        _ref_signature(node.legal_location_ref): node.legal_location_ref
        for tree in context.final_trees
        for node in tree.nodes
    }
    base_units = {unit.source_unit_id for tree in context.base_trees for unit in tree.source_units}
    final_units = {
        unit.source_unit_id for tree in context.final_trees for unit in tree.source_units
    }
    retained_locations = base_locations.keys() & final_locations.keys()
    new_locations = final_locations.keys() - base_locations.keys()
    ended_locations = base_locations.keys() - final_locations.keys()
    operation_ids = set(context.operations)
    predecessor_links: set[RefSignature] = set()
    successor_links: set[RefSignature] = set()
    for link in context.request.lineage_links:
        if _text(link.get("operation_instance_id"), "lineage operation") not in operation_ids:
            _fail("lineage operation")
        predecessor = link.get("predecessor_ref")
        successor = link.get("successor_ref")
        if isinstance(predecessor, dict):
            predecessor_links.add(_ref_signature(predecessor))
        if isinstance(successor, dict):
            successor_links.add(_ref_signature(successor))
    if not ended_locations <= predecessor_links or not new_locations <= successor_links:
        _fail("lineage location accounting")
    return _checked_object(
        {
            "$schema": "asklegal://contracts/hk-legislation/reconstruction-artifact/identity-lineage-result/1.0.0",
            "contract_version": "1.0.0",
            "legal_item_ref": context.request.plan["legal_item_ref"],
            "identity_lineage_decision_ref": context.request.identity_lineage_decision_ref,
            "retained_location_refs": _sorted_refs(
                tuple(base_locations[key] for key in retained_locations)
            ),
            "new_location_refs": _sorted_refs(tuple(final_locations[key] for key in new_locations)),
            "ended_location_refs": _sorted_refs(
                tuple(base_locations[key] for key in ended_locations)
            ),
            "retained_source_unit_ids": sorted(base_units & final_units),
            "new_source_unit_ids": sorted(final_units - base_units),
            "ended_source_unit_ids": sorted(base_units - final_units),
            "lineage_links": list(context.request.lineage_links),
            "acyclic": True,
            "plan_inventory_reconciled": True,
        }
    )


def _validate_contracts(context: _BuildContext) -> None:
    plan_contracts = _object(context.request.plan.get("contracts"), "Plan contracts")
    artifact_contracts = context.request.contracts
    if frozenset(artifact_contracts) != frozenset(
        (*_SHARED_CONTRACT_KEYS, "alignment", "lineage", "artifact")
    ):
        _fail("artifact contracts")
    for artifact_key, plan_key in _SHARED_CONTRACT_KEYS.items():
        if _contract_signature(
            _object(artifact_contracts.get(artifact_key), "artifact contract")
        ) != _contract_signature(_object(plan_contracts.get(plan_key), "Plan contract")):
            _fail("shared artifact contract")


def _file_entry(path: str, raw: bytes) -> dict[str, JsonValue]:
    role, media_type = _FILE_ROLES[path]
    return {
        "role": role,
        "path": path,
        "media_type": media_type,
        "byte_size": len(raw),
        "fingerprint": _raw_fingerprint(raw),
    }


def _manifest(
    context: _BuildContext,
    file_entries: tuple[dict[str, JsonValue], ...],
) -> dict[str, JsonValue]:
    base = _object(context.request.plan.get("base"), "artifact Plan base")
    return _checked_object(
        {
            "$schema": RECONSTRUCTED_ARTIFACT_SCHEMA,
            "contract_version": RECONSTRUCTED_ARTIFACT_CONTRACT_VERSION,
            "reconstructed_consolidation_artifact_id": (
                context.request.reconstructed_consolidation_artifact_id
            ),
            "artifact_class": "RECONSTRUCTED_CONSOLIDATION",
            "jurisdiction": "HK",
            "material": "legislation",
            "observation_cutoff": context.request.plan["observation_cutoff"],
            "legal_item_ref": context.request.plan["legal_item_ref"],
            "reconstruction_plan_ref": context.plan_ref,
            "base_official_version_ref": base["official_version_ref"],
            "base_evidence_class": base["evidence_class"],
            "applicability_decision_ref": context.request.plan["applicability_decision_ref"],
            "coverage_gap_ref": context.request.coverage_gap_ref,
            "identity_lineage_decision_ref": context.request.identity_lineage_decision_ref,
            "contracts": context.request.contracts,
            "files": list(file_entries),
            "serving_requirements": {
                "serving_mode": "RECONSTRUCTED_CONSOLIDATION",
                "authority_note_template_contract_ref": (
                    context.request.authority_note_template_contract_ref
                ),
                "ordinary_legislation_renderer_required": True,
                "ordinary_legislation_partitioning_required": True,
                "separate_material_type_forbidden": True,
                "separate_index_or_namespace_forbidden": True,
                "traceability_lookup_required": True,
            },
        }
    )


def _validate_members(
    registry: SchemaRegistry,
    documents: dict[str, JsonValue | tuple[dict[str, JsonValue], ...]],
) -> None:
    definitions = {
        "dependency-closure-proof.json": "dependency_closure_proof",
        "source-unit-coverage-proof.json": "source_unit_coverage_proof",
        "derivation-map.json": "derivation_map",
        "identity-lineage-result.json": "identity_lineage_result",
    }
    for path, definition in definitions.items():
        value = documents[path]
        if not isinstance(value, dict):
            _fail("artifact member document")
        _validate_schema(registry, value, f"{_SCHEMA}#/$defs/{definition}", path)
    for path, definition in (
        ("source-units/en.jsonl", "source_unit_row"),
        ("source-units/zh-Hant.jsonl", "source_unit_row"),
        ("reconstructed-location-units.jsonl", "location_row"),
    ):
        value = documents[path]
        if not isinstance(value, tuple):
            _fail("artifact JSONL rows")
        for row in value:
            _validate_schema(registry, row, f"{_SCHEMA}#/$defs/{definition}", path)


def _parse_canonical_json(raw: bytes, detail: str) -> dict[str, JsonValue]:
    if not raw or len(raw) > _MAX_MEMBER_BYTES:
        _fail(detail)
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX_MEMBER_BYTES)
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail) from error
    result = _object(value, detail)
    if canonicalize(checked_json_value(result)) != raw:
        _fail(detail)
    return result


def _parse_canonical_jsonl(
    raw: bytes,
    detail: str,
) -> tuple[dict[str, JsonValue], ...]:
    if not raw or len(raw) > _MAX_MEMBER_BYTES or not raw.endswith(b"\n"):
        _fail(detail)
    lines = raw[:-1].split(b"\n")
    if not lines or any(not line for line in lines):
        _fail(detail)
    rows: list[dict[str, JsonValue]] = []
    for line in lines:
        try:
            value = parse_json_bytes(line, max_bytes=_MAX_MEMBER_BYTES)
        except ContractViolation as error:
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail) from error
        row = _object(value, detail)
        if canonicalize(checked_json_value(row)) != line:
            _fail(detail)
        rows.append(row)
    return tuple(rows)


type ArtifactMemberDocuments = dict[
    str,
    dict[str, JsonValue] | tuple[dict[str, JsonValue], ...],
]


def _document_object(
    documents: ArtifactMemberDocuments,
    path: str,
    detail: str,
) -> dict[str, JsonValue]:
    value = documents.get(path)
    if not isinstance(value, dict):
        _fail(detail)
    return value


def _document_rows(
    documents: ArtifactMemberDocuments,
    path: str,
    detail: str,
) -> tuple[dict[str, JsonValue], ...]:
    value = documents.get(path)
    if not isinstance(value, tuple):
        _fail(detail)
    return value


def _validate_artifact_trees_sources(
    documents: ArtifactMemberDocuments,
) -> tuple[CanonicalLanguageTree, CanonicalLanguageTree]:
    trees = (
        parse_canonical_language_tree(
            _document_object(documents, "trees/en.json", "English artifact tree")
        ),
        parse_canonical_language_tree(
            _document_object(documents, "trees/zh-Hant.json", "Chinese artifact tree")
        ),
    )
    if tuple(tree.language for tree in trees) != _LANGUAGES:
        _fail("artifact tree languages")
    paths = ("source-units/en.jsonl", "source-units/zh-Hant.jsonl")
    for tree, path in zip(trees, paths, strict=True):
        rows = _document_rows(documents, path, "artifact source-unit rows")
        if tuple(_object(row.get("source_unit"), "artifact source unit") for row in rows) != (
            tuple(unit.document() for unit in tree.source_units)
        ):
            _fail("artifact source-unit tree equality")
    return trees


def _validate_artifact_proofs(
    documents: ArtifactMemberDocuments,
    plan_ref: dict[str, JsonValue],
    trees: tuple[CanonicalLanguageTree, CanonicalLanguageTree],
) -> None:
    proof_documents = tuple(
        _document_object(documents, path, "artifact proof")
        for path in (
            "dependency-closure-proof.json",
            "source-unit-coverage-proof.json",
            "derivation-map.json",
        )
    )
    if any(
        _ref_signature(_object(document.get("reconstruction_plan_ref"), "member Plan"))
        != _ref_signature(plan_ref)
        for document in proof_documents
    ):
        _fail("artifact member Plan binding")
    coverage_languages = _objects(
        proof_documents[1].get("languages"),
        "artifact coverage languages",
    )
    if tuple(item.get("language") for item in coverage_languages) != _LANGUAGES:
        _fail("artifact coverage language order")
    for tree, coverage in zip(trees, coverage_languages, strict=True):
        unit_ids = tuple(_strings(coverage.get("final_source_unit_ids"), "coverage units"))
        if unit_ids != tuple(unit.source_unit_id for unit in tree.source_units):
            _fail("artifact source-unit coverage equality")
        if coverage.get("final_source_unit_inventory_fingerprint") != (
            canonical_source_unit_inventory_fingerprint(tree.document())
        ):
            _fail("artifact source-unit coverage equality")


def _validate_artifact_derivations(
    documents: ArtifactMemberDocuments,
    trees: tuple[CanonicalLanguageTree, CanonicalLanguageTree],
) -> None:
    derivation = _document_object(documents, "derivation-map.json", "artifact derivation map")
    entries = _objects(derivation.get("entries"), "artifact derivation entries")
    structures = _objects(
        derivation.get("structural_derivations"),
        "artifact structural derivations",
    )
    if {(entry.get("language"), entry.get("source_unit_id")) for entry in entries} != {
        (tree.language, unit.source_unit_id) for tree in trees for unit in tree.source_units
    }:
        _fail("artifact derivation source-unit inventory")
    if {(entry.get("language"), entry.get("tree_node_id")) for entry in structures} != {
        (tree.language, node.tree_node_id) for tree in trees for node in tree.nodes
    }:
        _fail("artifact structural derivation inventory")


def _validate_artifact_locations(
    documents: ArtifactMemberDocuments,
    alignment: dict[str, JsonValue],
) -> None:
    dependency = _document_object(
        documents,
        "dependency-closure-proof.json",
        "artifact dependency proof",
    )
    rows = _document_rows(
        documents,
        "reconstructed-location-units.jsonl",
        "artifact location rows",
    )
    actual = {
        _ref_signature(_object(row.get("legal_location_ref"), "artifact location")) for row in rows
    }
    expected = {
        _ref_signature(ref)
        for ref in _objects(dependency.get("artifact_location_refs"), "artifact locations")
    }
    if actual != expected:
        _fail("artifact location dependency equality")
    ended = {
        _ref_signature(ref)
        for ref in _objects(dependency.get("ended_location_refs"), "ended locations")
    }
    closure = {
        _ref_signature(ref)
        for key in (
            "primary_affected_location_refs",
            "governing_context_location_refs",
            "dependent_location_refs",
            "independent_sibling_boundary_refs",
        )
        for ref in _objects(dependency.get(key), "dependency category")
    }
    identity = _document_object(
        documents,
        "identity-lineage-result.json",
        "artifact identity result",
    )
    identity_ended = {
        _ref_signature(ref)
        for ref in _objects(identity.get("ended_location_refs"), "identity ended locations")
    }
    if actual & ended or actual | ended != closure or ended != identity_ended:
        _fail("artifact ended-location accounting")
    group_ids = {
        _text(group.get("alignment_group_id"), "alignment group")
        for group in _objects(alignment.get("groups"), "alignment groups")
    }
    if any(
        not set(_strings(row.get("bilingual_alignment_group_ids"), "location alignment"))
        <= group_ids
        for row in rows
    ):
        _fail("artifact location alignment equality")


def _validate_artifact_semantics(documents: ArtifactMemberDocuments) -> None:
    manifest = _document_object(documents, "manifest.json", "artifact manifest")
    plan_ref = _object(manifest.get("reconstruction_plan_ref"), "artifact Plan reference")
    trees = _validate_artifact_trees_sources(documents)
    alignment = parse_bilingual_alignment_map(
        _document_object(documents, "bilingual-alignment-map.json", "artifact alignment"),
        en_tree=trees[0],
        zh_hant_tree=trees[1],
    ).document()
    _validate_artifact_proofs(documents, plan_ref, trees)
    _validate_artifact_derivations(documents, trees)
    _validate_artifact_locations(documents, alignment)


def validate_reconstructed_consolidation_artifact(
    package_root: Path,
    artifact: ReconstructedConsolidationArtifact,
) -> dict[str, JsonValue]:
    """Re-read and validate every in-memory member before later consumption."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    file_map = dict(artifact.files)
    expected_paths = {"manifest.json", *_FILE_ROLES}
    if len(file_map) != len(artifact.files) or set(file_map) != expected_paths:
        _fail("artifact file inventory")
    expected_inventory: list[dict[str, JsonValue]] = []
    for path, raw in file_map.items():
        if path == "manifest.json":
            entry = {
                "role": "MANIFEST",
                "path": path,
                "media_type": _JSON_MEDIA,
                "byte_size": len(raw),
                "fingerprint": _raw_fingerprint(raw),
            }
        else:
            entry = _file_entry(path, raw)
        expected_inventory.append(_checked_object(entry))
    expected_inventory.sort(key=lambda entry: (str(entry["role"]), str(entry["path"])))
    if tuple(expected_inventory) != artifact.inventory:
        _fail("artifact inventory bytes")
    if _fingerprint(checked_json_value(expected_inventory)) != artifact.root_fingerprint:
        _fail("artifact root fingerprint")
    _validate_schema(
        registry,
        checked_json_value(artifact.document()),
        f"{_SCHEMA}#/$defs/package_result",
        "artifact package result",
    )
    documents: ArtifactMemberDocuments = {}
    for path, raw in file_map.items():
        documents[path] = (
            _parse_canonical_jsonl(raw, path)
            if _FILE_ROLES.get(path, ("", ""))[1] == _JSONL_MEDIA
            else _parse_canonical_json(raw, path)
        )
    manifest = _document_object(documents, "manifest.json", "artifact manifest")
    _validate_schema(registry, manifest, f"{_SCHEMA}#/$defs/manifest", "artifact manifest")
    if manifest.get("reconstructed_consolidation_artifact_id") != (
        artifact.reconstructed_consolidation_artifact_id
    ):
        _fail("artifact identity")
    if tuple(_objects(manifest.get("files"), "manifest files")) != tuple(
        entry for entry in expected_inventory if entry["role"] != "MANIFEST"
    ):
        _fail("artifact manifest inventory")
    _validate_members(
        registry, {path: value for path, value in documents.items() if path != "manifest.json"}
    )
    _validate_artifact_semantics(documents)
    return manifest


def build_reconstructed_consolidation_artifact(
    request: ReconstructionArtifactBuildRequest,
) -> ReconstructedConsolidationArtifact:
    """Build and validate one complete in-memory ADR 0085 package."""
    context = _build_context(request)
    _validate_contracts(context)
    language_derivations = tuple(_language_derivation(context, index) for index in range(2))
    derivation_entries = tuple(entry for language in language_derivations for entry in language[0])
    structural_derivations = tuple(
        entry for language in language_derivations for entry in language[1]
    )
    operation_maps = tuple(language[2] for language in language_derivations)
    source_rows = tuple(
        _source_unit_rows(context.final_trees[index], language_derivations[index][0])
        for index in range(2)
    )
    location_rows = _location_rows(context)
    documents: dict[str, JsonValue | tuple[dict[str, JsonValue], ...]] = {
        "trees/en.json": context.final_trees[0].document(),
        "trees/zh-Hant.json": context.final_trees[1].document(),
        "source-units/en.jsonl": source_rows[0],
        "source-units/zh-Hant.jsonl": source_rows[1],
        "reconstructed-location-units.jsonl": location_rows,
        "bilingual-alignment-map.json": context.alignment,
        "dependency-closure-proof.json": _dependency_proof(context, location_rows),
        "source-unit-coverage-proof.json": _source_unit_coverage_proof(
            context,
            operation_maps,
        ),
        "derivation-map.json": _checked_object(
            {
                "$schema": "asklegal://contracts/hk-legislation/reconstruction-artifact/derivation-map/1.0.0",
                "contract_version": "1.0.0",
                "reconstruction_plan_ref": context.plan_ref,
                "entries": list(derivation_entries),
                "structural_derivations": list(structural_derivations),
                "complete": True,
                "generated_derivation_forbidden": True,
            }
        ),
        "identity-lineage-result.json": _identity_result(context),
    }
    registry = SchemaRegistry.from_contracts_root(request.package_root / "contracts")
    _validate_members(registry, documents)
    file_bytes: dict[str, bytes] = {}
    for path, value in documents.items():
        file_bytes[path] = _jsonl_bytes(value) if isinstance(value, tuple) else _json_bytes(value)
    entries = tuple(
        sorted(
            (_file_entry(path, raw) for path, raw in file_bytes.items()),
            key=lambda entry: (_text(entry.get("role"), "file role"), entry["path"]),
        )
    )
    manifest = _manifest(context, entries)
    _validate_schema(registry, manifest, f"{_SCHEMA}#/$defs/manifest", "artifact manifest")
    file_bytes["manifest.json"] = _json_bytes(manifest)
    manifest_entry = _checked_object(
        {
            "role": "MANIFEST",
            "path": "manifest.json",
            "media_type": _JSON_MEDIA,
            "byte_size": len(file_bytes["manifest.json"]),
            "fingerprint": _raw_fingerprint(file_bytes["manifest.json"]),
        }
    )
    inventory = tuple(
        sorted(
            (manifest_entry, *entries),
            key=lambda entry: (_text(entry.get("role"), "inventory role"), entry["path"]),
        )
    )
    root_fingerprint = _fingerprint(checked_json_value(list(inventory)))
    artifact = ReconstructedConsolidationArtifact(
        request.reconstructed_consolidation_artifact_id,
        root_fingerprint,
        inventory,
        tuple(sorted(file_bytes.items())),
    )
    _validate_schema(
        registry,
        checked_json_value(artifact.document()),
        f"{_SCHEMA}#/$defs/package_result",
        "artifact package result",
    )
    validate_reconstructed_consolidation_artifact(request.package_root, artifact)
    return artifact
