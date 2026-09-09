"""Transactional conformance for canonical Hong Kong reconstruction execution."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

import asklegal_legal_desks.hk_reconstruction_report as reconstruction_report_module
import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_legal_desks import ReconstructionPlanValidationDecision
from asklegal_legal_desks.hk_canonical_legislation import (
    BILINGUAL_ALIGNMENT_MAP_SCHEMA,
    CANONICAL_TREE_CONTRACT_VERSION,
    canonical_source_unit_inventory_fingerprint,
    parse_canonical_language_tree,
    seal_canonical_language_tree,
)
from asklegal_legal_desks.hk_reconstruction_artifact import (
    ReconstructionArtifactBuildRequest,
    build_reconstructed_consolidation_artifact,
    validate_reconstructed_consolidation_artifact,
)
from asklegal_legal_desks.hk_reconstruction_execution import (
    ReconstructionExecutionRequest,
    ReconstructionPlanExecution,
    execute_validated_reconstruction_plan,
    reconstruction_deleted_state_fingerprints,
    reconstruction_state_fingerprints,
    reconstruction_tree_fingerprint,
)
from asklegal_legal_desks.hk_reconstruction_report import (
    ReconstructionReportBuildRequest,
    build_reconstruction_execution_report,
)
from asklegal_legal_desks.model import RulebookError

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package"
PLAN_FIXTURE = PACKAGE_ROOT / "fixtures/deterministic/HKLEG-RECON-PLAN-VAL-FIX-001.json"
RENDERER_DECLARATION = PACKAGE_ROOT / "renderers/canonical-ordinary-bilingual-renderer.json"
SHA_ZERO = "sha256:" + "0" * 64
LEGAL_ITEM = {
    "ref_type": "LEGAL_ITEM",
    "ref_id": "li_reconstruction_test",
    "fingerprint": "sha256:" + "1" * 64,
}


@dataclass(frozen=True, slots=True)
class _Spec:
    ordinal: int
    location: dict[str, JsonValue]
    parent: int | None
    order: int
    label: str
    content: str
    structural_type: str = "PROVISION"
    units: str = "DEFAULT"


def _object(value: JsonValue | None) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _objects(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return [item for item in value if isinstance(item, dict)]


def _array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _path_object(
    document: dict[str, JsonValue],
    path: tuple[str | int, ...],
) -> dict[str, JsonValue]:
    current: JsonValue = document
    for segment in path:
        if isinstance(segment, str):
            current = _object(current)[segment]
        else:
            current = _array(current)[segment]
    return _object(current)


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _sha(value: object) -> str:
    return f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"


def _bytes_sha(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _json_object(value: object) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    assert isinstance(parsed, dict)
    return parsed


def _ref(
    ref_type: str, prefix: str, ordinal: int, fingerprint: str | None = None
) -> dict[str, JsonValue]:
    return {
        "ref_type": ref_type,
        "ref_id": f"{prefix}_{ordinal:048x}",
        "fingerprint": fingerprint or f"sha256:{ordinal:064x}",
    }


def _location(ordinal: int) -> dict[str, JsonValue]:
    return _ref("LEGAL_LOCATION", "loc", ordinal)


def _node_id(language: str, ordinal: int) -> str:
    del language
    return f"node_{ordinal:024x}"


def _unit_id(language: str, ordinal: int, role: str) -> str:
    prefix = "en" if language == "en" else "zh"
    return f"{prefix}_unit_{ordinal:024x}_{role}"


def _source_artifact(ordinal: int, payload: object) -> dict[str, JsonValue]:
    payload_object = _json_object(payload)
    return _json_object(
        {
            "ref": _ref("ARTIFACT", "art", ordinal, _sha(payload_object)),
            "payload": payload_object,
        }
    )


def _tree(
    language: str, specs: list[_Spec], *, source_format: str = "SYNTHETIC_BASE"
) -> dict[str, JsonValue]:
    nodes: list[dict[str, JsonValue]] = []
    units: list[dict[str, JsonValue]] = []
    by_parent: dict[int, list[_Spec]] = {}
    for spec in specs:
        if spec.parent is not None:
            by_parent.setdefault(spec.parent, []).append(spec)
    for spec in specs:
        node_id = _node_id(language, spec.ordinal)
        unit_specs: list[tuple[str, str, str]]
        if spec.units == "INSTRUMENT":
            unit_specs = [("title", "INSTRUMENT_TITLE", spec.content)]
        elif spec.units == "TEXT_ONLY":
            unit_specs = [("body", "BODY_TEXT", spec.content)]
        else:
            unit_specs = [
                ("label", "STRUCTURAL_LABEL", spec.label),
                ("body", "BODY_TEXT", spec.content),
            ]
        owned: list[str] = []
        for order, (role, kind, content) in enumerate(unit_specs):
            unit_id = _unit_id(language, spec.ordinal, role)
            owned.append(unit_id)
            units.append(
                {
                    "source_unit_id": unit_id,
                    "tree_node_id": node_id,
                    "legal_location_ref": spec.location,
                    "unit_kind": kind,
                    "content": content,
                    "asset_ref": None,
                    "source_order": order,
                }
            )
        children = sorted(by_parent.get(spec.ordinal, []), key=lambda item: item.order)
        nodes.append(
            _json_object(
                {
                    "tree_node_id": node_id,
                    "legal_location_ref": spec.location,
                    "structural_type": spec.structural_type,
                    "parent_node_id": (
                        _node_id(language, spec.parent) if spec.parent is not None else None
                    ),
                    "sibling_order": spec.order,
                    "owned_source_unit_ids": owned,
                    "child_node_ids": [_node_id(language, child.ordinal) for child in children],
                }
            )
        )
    return seal_canonical_language_tree(
        _json_object(
            {
                "source_format": source_format,
                "language": language,
                "legal_item_ref": LEGAL_ITEM,
                "root_node_id": _node_id(language, specs[0].ordinal),
                "nodes": nodes,
                "source_units": units,
            }
        )
    ).document()


def _root(language: str) -> _Spec:
    return _Spec(
        1,
        _location(1),
        None,
        0,
        "",
        f"Reconstruction Test {language}",
        "INSTRUMENT",
        "INSTRUMENT",
    )


def _state(
    tree: dict[str, JsonValue], language: str, ordinals: tuple[int, ...]
) -> tuple[str, str, str]:
    return reconstruction_state_fingerprints(
        tree, tuple(_node_id(language, ordinal) for ordinal in ordinals)
    )


def _operation_state(
    tree: dict[str, JsonValue], language: str, ordinals: tuple[int, ...]
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    structure, content, ownership = _state(tree, language, ordinals)
    parsed = parse_canonical_language_tree(tree)
    selected = {_node_id(language, ordinal) for ordinal in ordinals}
    locations: list[JsonValue] = []
    seen: set[tuple[str, str, str]] = set()
    for node in parsed.nodes:
        if node.tree_node_id not in selected:
            continue
        location = node.legal_location_ref
        signature = (
            _text(location["ref_type"]),
            _text(location["ref_id"]),
            _text(location["fingerprint"]),
        )
        if signature not in seen:
            locations.append(location)
            seen.add(signature)
    return (
        _json_object(
            {
                "expected_target_count": len(ordinals),
                "location_refs": locations,
                "structure_fingerprint": structure,
                "content_fingerprint": content,
            }
        ),
        _json_object(
            {
                "location_refs": locations,
                "structure_fingerprint": structure,
                "source_unit_ownership_fingerprint": ownership,
                "content_fingerprint": content,
            }
        ),
    )


def _selector(
    kind: str,
    location: dict[str, JsonValue],
    language: str,
    node_ordinal: int,
    structural_position: str,
) -> dict[str, JsonValue]:
    return _json_object(
        {
            "selector_kind": kind,
            "legal_location_ref": location,
            "tree_node_id": _node_id(language, node_ordinal),
            "structural_position": structural_position,
            "anchor_fingerprint": "sha256:" + "a" * 64,
        }
    )


def _renderer_ref() -> dict[str, JsonValue]:
    raw = RENDERER_DECLARATION.read_bytes()
    declaration = _object(parse_json_bytes(raw, max_bytes=100_000))
    return {
        "contract_id": declaration["renderer_id"],
        "version": declaration["version"],
        "fingerprint": _bytes_sha(raw),
    }


def _contract_ref(contract_id: str, ordinal: int) -> dict[str, JsonValue]:
    return {
        "contract_id": contract_id,
        "version": "1.0.0",
        "fingerprint": f"sha256:{ordinal:064x}",
    }


def _replacement_scenario(
    operation_type: str,
    language: str,
    language_ordinal: int,
    *,
    unsupported_op008: bool,
) -> tuple[
    dict[str, JsonValue],
    dict[str, JsonValue],
    dict[str, JsonValue],
    list[dict[str, JsonValue]],
]:
    loc_a, loc_b = _location(2), _location(3)
    base = _tree(
        language,
        [
            _root(language),
            _Spec(2, loc_a, 1, 0, "1", f"before-{language}"),
            _Spec(3, loc_b, 2, 0, "(a)", f"child-{language}"),
        ],
    )
    if operation_type == "HKRECON-OP-005":
        fragment_spec = _Spec(4, loc_a, None, 0, "1", f"after-{language}")
    else:
        fragment_spec = _Spec(
            4,
            loc_a,
            None,
            0,
            "",
            f"region-{language}",
            "TABLE" if unsupported_op008 else "TEXT_BLOCK",
            "TEXT_ONLY",
        )
    fragment = _tree(language, [fragment_spec], source_format="SYNTHETIC_AMENDMENT_FRAGMENT")
    final = _tree(language, [_root(language), replace(fragment_spec, parent=1)])
    source = _source_artifact(
        language_ordinal * 100 + 1,
        {"payload_kind": "CANONICAL_TREE_FRAGMENT", "tree": fragment},
    )
    before, _ = _operation_state(base, language, (2, 3))
    _, after = _operation_state(final, language, (4,))
    parameter_name = (
        "replacement_node_source_unit_refs"
        if operation_type == "HKRECON-OP-005"
        else "replacement_region_source_unit_refs"
    )
    parameters: dict[str, JsonValue] = {parameter_name: [source["ref"]]}
    if operation_type == "HKRECON-OP-008":
        parameters["renderer_contract_ref"] = _renderer_ref()
    return (
        base,
        final,
        _json_object(
            {
                "source_unit_refs": [source["ref"]],
                "target_selector": _selector(
                    "COMPLETE_NODE"
                    if operation_type == "HKRECON-OP-005"
                    else "CLOSED_STRUCTURED_REGION",
                    loc_a,
                    language,
                    2,
                    "COMPLETE_NODE" if operation_type == "HKRECON-OP-005" else "REGION",
                ),
                "before_state": before,
                "parameters": parameters,
                "expected_after_state": after,
            }
        ),
        [source],
    )


def _scenario(
    operation_type: str,
    language: str,
    language_ordinal: int,
    *,
    unsupported_op008: bool = False,
) -> tuple[
    dict[str, JsonValue],
    dict[str, JsonValue],
    dict[str, JsonValue],
    list[dict[str, JsonValue]],
]:
    loc_root, loc_a, loc_b, loc_c = (_location(index) for index in range(1, 5))
    source_base = language_ordinal * 100

    if operation_type == "HKRECON-OP-001":
        base = _tree(
            language,
            [_root(language), _Spec(2, loc_a, 1, 0, "1", f"old-{language}")],
        )
        final = _tree(
            language,
            [_root(language), _Spec(2, loc_a, 1, 0, "1", f"new-{language}")],
        )
        old = _source_artifact(
            source_base + 1, {"payload_kind": "TEXT", "content": f"old-{language}"}
        )
        new = _source_artifact(
            source_base + 2, {"payload_kind": "TEXT", "content": f"new-{language}"}
        )
        before, _ = _operation_state(base, language, (2,))
        _, after = _operation_state(final, language, (2,))
        return (
            base,
            final,
            _json_object(
                {
                    "source_unit_refs": [_object(old["ref"]), _object(new["ref"])],
                    "target_selector": _selector(
                        "EXACT_TEXT_RANGE", loc_a, language, 2, "EXACT_RANGE"
                    ),
                    "before_state": before,
                    "parameters": {
                        "old_text_source_unit_ref": old["ref"],
                        "replacement_source_unit_ref": new["ref"],
                        "exact_range_fingerprint": _sha(f"old-{language}"),
                    },
                    "expected_after_state": after,
                }
            ),
            [old, new],
        )

    if operation_type == "HKRECON-OP-002":
        base_specs = [
            _root(language),
            _Spec(2, loc_a, 1, 0, "1", f"old-{language}-a"),
            _Spec(3, loc_b, 1, 1, "2", f"old-{language}-b"),
        ]
        final_specs = [
            _root(language),
            _Spec(2, loc_a, 1, 0, "1", f"new-{language}-a"),
            _Spec(3, loc_b, 1, 1, "2", f"new-{language}-b"),
        ]
        base, final = _tree(language, base_specs), _tree(language, final_specs)
        old = _source_artifact(
            source_base + 1, {"payload_kind": "TEXT", "content": f"old-{language}"}
        )
        new = _source_artifact(
            source_base + 2, {"payload_kind": "TEXT", "content": f"new-{language}"}
        )
        before, _ = _operation_state(base, language, (2, 3))
        _, after = _operation_state(final, language, (2, 3))
        return (
            base,
            final,
            _json_object(
                {
                    "source_unit_refs": [old["ref"], new["ref"]],
                    "target_selector": _selector(
                        "CLOSED_SCOPE_OCCURRENCES", loc_a, language, 2, "CLOSED_SCOPE"
                    ),
                    "before_state": before,
                    "parameters": {
                        "old_phrase_source_unit_ref": old["ref"],
                        "replacement_source_unit_ref": new["ref"],
                        "closed_scope_location_refs": [loc_a, loc_b],
                        "expected_match_location_refs": [loc_a, loc_b],
                        "exclusion_location_refs": [],
                    },
                    "expected_after_state": after,
                }
            ),
            [old, new],
        )

    if operation_type == "HKRECON-OP-003":
        base = _tree(
            language,
            [_root(language), _Spec(2, loc_a, 1, 0, "1", f"one-{language}")],
        )
        fragment = _tree(
            language,
            [_Spec(3, loc_b, None, 0, "2", f"two-{language}")],
            source_format="SYNTHETIC_AMENDMENT_FRAGMENT",
        )
        final = _tree(
            language,
            [
                _root(language),
                _Spec(2, loc_a, 1, 0, "1", f"one-{language}"),
                _Spec(3, loc_b, 1, 1, "2", f"two-{language}"),
            ],
        )
        source = _source_artifact(
            source_base + 1,
            {"payload_kind": "CANONICAL_TREE_FRAGMENT", "tree": fragment},
        )
        before, _ = _operation_state(base, language, (2,))
        _, after = _operation_state(final, language, (3,))
        return (
            base,
            final,
            _json_object(
                {
                    "source_unit_refs": [source["ref"]],
                    "target_selector": _selector(
                        "PARENT_ORDER_POSITION", loc_a, language, 2, "AFTER"
                    ),
                    "before_state": before,
                    "parameters": {
                        "new_node_source_unit_refs": [source["ref"]],
                        "parent_location_ref": loc_root,
                        "insertion_anchor": "AFTER",
                    },
                    "expected_after_state": after,
                }
            ),
            [source],
        )

    if operation_type == "HKRECON-OP-004":
        base = _tree(
            language,
            [_root(language), _Spec(2, loc_a, 1, 0, "1", f"remove-{language}")],
        )
        final = _tree(language, [_root(language)])
        removed_ids = [
            _unit_id(language, 2, "label"),
            _unit_id(language, 2, "body"),
        ]
        source = _source_artifact(
            source_base + 1,
            {"payload_kind": "SOURCE_UNIT_REMOVAL", "source_unit_ids": removed_ids},
        )
        before, _ = _operation_state(base, language, (2,))
        deleted = reconstruction_deleted_state_fingerprints((loc_a,))
        return (
            base,
            final,
            _json_object(
                {
                    "source_unit_refs": [source["ref"]],
                    "target_selector": _selector(
                        "COMPLETE_NODE", loc_a, language, 2, "COMPLETE_NODE"
                    ),
                    "before_state": before,
                    "parameters": {"removed_node_source_unit_refs": [source["ref"]]},
                    "expected_after_state": {
                        "location_refs": [loc_a],
                        "structure_fingerprint": deleted[0],
                        "source_unit_ownership_fingerprint": deleted[2],
                        "content_fingerprint": deleted[1],
                    },
                }
            ),
            [source],
        )

    if operation_type in ("HKRECON-OP-005", "HKRECON-OP-008"):
        return _replacement_scenario(
            operation_type,
            language,
            language_ordinal,
            unsupported_op008=unsupported_op008,
        )

    if operation_type == "HKRECON-OP-006":
        base = _tree(
            language,
            [_root(language), _Spec(2, loc_a, 1, 0, "1", f"same-{language}")],
        )
        final = _tree(
            language,
            [_root(language), _Spec(2, loc_a, 1, 0, "1A", f"same-{language}")],
        )
        source = _source_artifact(source_base + 1, {"payload_kind": "TEXT", "content": "1A"})
        before, _ = _operation_state(base, language, (2,))
        _, after = _operation_state(final, language, (2,))
        result = (
            base,
            final,
            _json_object(
                {
                    "source_unit_refs": [source["ref"]],
                    "target_selector": _selector(
                        "COMPLETE_NODE", loc_a, language, 2, "COMPLETE_NODE"
                    ),
                    "before_state": before,
                    "parameters": {
                        "label_source_unit_refs": [source["ref"]],
                        "cross_reference_repairs": [],
                    },
                    "expected_after_state": after,
                }
            ),
            [source],
        )

    elif operation_type == "HKRECON-OP-007":
        base = _tree(
            language,
            [
                _root(language),
                _Spec(2, loc_a, 1, 0, "A", "A"),
                _Spec(4, loc_c, 2, 0, "1", f"move-{language}"),
                _Spec(3, loc_b, 1, 1, "B", "B"),
            ],
        )
        final = _tree(
            language,
            [
                _root(language),
                _Spec(2, loc_a, 1, 0, "A", "A"),
                _Spec(3, loc_b, 1, 1, "B", "B"),
                _Spec(4, loc_c, 3, 0, "1", f"move-{language}"),
            ],
        )
        moved_ids = [_unit_id(language, 4, "label"), _unit_id(language, 4, "body")]
        source = _source_artifact(
            source_base + 1,
            {"payload_kind": "MOVE_AUTHORITY", "source_unit_ids": moved_ids},
        )
        before, _ = _operation_state(base, language, (4,))
        _, after = _operation_state(final, language, (4,))
        result = (
            base,
            final,
            _json_object(
                {
                    "source_unit_refs": [source["ref"]],
                    "target_selector": _selector("NEW_PARENT_ORDER", loc_b, language, 3, "INSIDE"),
                    "before_state": before,
                    "parameters": {
                        "moved_node_ref": loc_c,
                        "new_parent_ref": loc_b,
                        "new_position": "FIRST_CHILD",
                    },
                    "expected_after_state": after,
                }
            ),
            [source],
        )

    else:
        raise AssertionError(operation_type)
    return result


def _alignment(final_trees: tuple[dict[str, JsonValue], ...]) -> dict[str, JsonValue]:
    en = parse_canonical_language_tree(final_trees[0])
    zh = parse_canonical_language_tree(final_trees[1])
    assert len(en.source_units) == len(zh.source_units)
    evidence = _ref("BILINGUAL_MAPPING_EVIDENCE", "map", 1)
    groups: list[dict[str, JsonValue]] = []
    for index, (en_unit, zh_unit) in enumerate(
        zip(en.source_units, zh.source_units, strict=True), 1
    ):
        assert en_unit.legal_location_ref == zh_unit.legal_location_ref
        groups.append(
            {
                "alignment_group_id": f"align_{index:04d}",
                "legal_location_ref": en_unit.legal_location_ref,
                "en_source_unit_ids": [en_unit.source_unit_id],
                "zh_hant_source_unit_ids": [zh_unit.source_unit_id],
                "mapping_evidence_ref": evidence,
            }
        )
    return _json_object(
        {
            "$schema": BILINGUAL_ALIGNMENT_MAP_SCHEMA,
            "contract_version": CANONICAL_TREE_CONTRACT_VERSION,
            "legal_item_ref": LEGAL_ITEM,
            "groups": groups,
        }
    )


def _bind_execution_closure(
    plan: dict[str, JsonValue],
    streams: list[dict[str, JsonValue]],
    final_trees: list[dict[str, JsonValue]],
) -> None:
    canonical_locations = {
        _text(_object(node.get("legal_location_ref"))["ref_id"]): _object(
            node.get("legal_location_ref")
        )
        for node in _objects(final_trees[0].get("nodes"))
    }
    primary_by_signature: dict[tuple[str, str, str], dict[str, JsonValue]] = {}
    governing_by_signature: dict[tuple[str, str, str], dict[str, JsonValue]] = {}
    for stream in streams:
        for operation in _objects(stream.get("operations")):
            selector_ref = _object(
                _object(operation.get("target_selector")).get("legal_location_ref")
            )
            location_refs = [
                selector_ref,
                *_objects(_object(operation.get("before_state")).get("location_refs")),
                *_objects(_object(operation.get("expected_after_state")).get("location_refs")),
            ]
            for ref in location_refs:
                primary_by_signature[
                    (_text(ref["ref_type"]), _text(ref["ref_id"]), _text(ref["fingerprint"]))
                ] = ref
            normalized_dependencies = [
                canonical_locations.get(_text(ref.get("ref_id")), ref)
                for ref in _objects(operation.get("dependency_location_refs"))
            ]
            operation["dependency_location_refs"] = checked_json_value(normalized_dependencies)
            for ref in normalized_dependencies:
                signature = (
                    _text(ref["ref_type"]),
                    _text(ref["ref_id"]),
                    _text(ref["fingerprint"]),
                )
                governing_by_signature[signature] = ref
    for signature in primary_by_signature:
        governing_by_signature.pop(signature, None)
    primary_refs = [primary_by_signature[key] for key in sorted(primary_by_signature)]
    governing_refs = [governing_by_signature[key] for key in sorted(governing_by_signature)]
    plan["affected_legal_location_refs"] = checked_json_value(
        sorted((*primary_refs, *governing_refs), key=lambda ref: _text(ref["ref_id"]))
    )
    closure = _object(plan.get("dependency_closure"))
    closure["primary_affected_location_refs"] = checked_json_value(primary_refs)
    closure["governing_context_location_refs"] = checked_json_value(governing_refs)
    closure["dependent_location_refs"] = []
    closure["independent_sibling_boundary_refs"] = []
    closure_projection = dict(closure)
    closure_projection.pop("closure_proof_fingerprint")
    closure["closure_proof_fingerprint"] = _sha(closure_projection)
    _objects(plan.get("event_chain"))[0]["affected_location_refs"] = checked_json_value(
        primary_refs
    )


def _execution_input(
    operation_type: str, *, unsupported_op008: bool = False
) -> tuple[
    dict[str, JsonValue],
    ReconstructionPlanValidationDecision,
    tuple[dict[str, JsonValue], ...],
    tuple[dict[str, JsonValue], ...],
    dict[str, JsonValue],
]:
    fixture = parse_json_bytes(PLAN_FIXTURE.read_bytes(), max_bytes=2_000_000)
    fixture_input = _object(_object(fixture).get("input"))
    plan = deepcopy(_object(fixture_input.get("candidate_plan")))
    streams = _objects(plan.get("language_streams"))
    language_inputs: list[dict[str, JsonValue]] = []
    all_artifacts: list[dict[str, JsonValue]] = []
    operation_ids: list[str] = []
    event_sources: dict[str, JsonValue] = {}
    final_trees: list[dict[str, JsonValue]] = []
    for index, (language, stream) in enumerate(zip(("en", "zh-Hant"), streams, strict=True), 1):
        base_tree, final_tree, partial, artifacts = _scenario(
            operation_type,
            language,
            index,
            unsupported_op008=unsupported_op008,
        )
        operation = deepcopy(_objects(stream.get("operations"))[0])
        operation_id = f"rop_{index:048x}"
        operation["operation_instance_id"] = operation_id
        operation["operation_type_id"] = operation_type
        operation.update(partial)
        stream["operations"] = [operation]
        stream["language_effect"] = "CHANGED"
        base_fingerprint = reconstruction_tree_fingerprint(base_tree)
        _object(stream.get("base_language_tree_ref"))["fingerprint"] = base_fingerprint
        stream["base_language_tree_fingerprint"] = base_fingerprint
        base_tree_ref = deepcopy(_object(stream.get("base_language_tree_ref")))
        stream["expected_final_language_tree_fingerprint"] = reconstruction_tree_fingerprint(
            final_tree
        )
        stream["expected_complete_source_unit_inventory_fingerprint"] = (
            canonical_source_unit_inventory_fingerprint(final_tree)
        )
        language_inputs.append(
            _json_object(
                {"language": language, "base_tree_ref": base_tree_ref, "base_tree": base_tree}
            )
        )
        final_trees.append(final_tree)
        all_artifacts.extend(artifacts)
        operation_ids.append(operation_id)
        event_sources[language] = checked_json_value(operation["source_unit_refs"])
    alignment = _alignment(tuple(final_trees))
    alignment_ref = _ref("ARTIFACT", "art", 9999, _sha(alignment))
    for stream in streams:
        stream["expected_bilingual_alignment_map_ref"] = alignment_ref
    _bind_execution_closure(plan, streams, final_trees)
    event = _objects(plan.get("event_chain"))[0]
    event["operation_instance_ids"] = checked_json_value(operation_ids)
    event["authentic_language_source_unit_refs"] = event_sources
    return (
        plan,
        _decision(plan, 2),
        tuple(language_inputs),
        tuple(all_artifacts),
        alignment,
    )


def _decision(
    plan: dict[str, JsonValue],
    operation_count: int,
    fixture_id: str = "HKLEG-RECON-EXEC-FIX-001",
) -> ReconstructionPlanValidationDecision:
    plan_fingerprint = _sha(plan)
    return ReconstructionPlanValidationDecision(
        fixture_id=fixture_id,
        processing_outcome="PASS",
        legal_disposition="NOT_APPLICABLE",
        source_contract_review_required=False,
        reason_code="HKLEG_RECON_PLAN_VALIDATED",
        candidate_plan_fingerprint=plan_fingerprint,
        plan_validation_result="VALIDATED",
        validated_reconstruction_plan_id=_text(plan["reconstruction_plan_id"]),
        validated_reconstruction_plan_fingerprint=plan_fingerprint,
        validated_operation_count=operation_count,
        next_action="CHECK_RECONSTRUCTION_CAPABILITY_AND_EXECUTE_PLAN",
    )


def _execute(
    plan: dict[str, JsonValue],
    decision: ReconstructionPlanValidationDecision,
    language_inputs: tuple[dict[str, JsonValue], ...],
    artifacts: tuple[dict[str, JsonValue], ...],
    alignment: dict[str, JsonValue],
) -> ReconstructionPlanExecution:
    return execute_validated_reconstruction_plan(
        ReconstructionExecutionRequest(
            package_root=PACKAGE_ROOT,
            plan=plan,
            validation_decision=decision,
            language_inputs=language_inputs,
            source_artifacts=artifacts,
            bilingual_alignment_map=alignment,
            execution_mode="OFFLINE_SYNTHETIC_CONFORMANCE",
        )
    )


@pytest.mark.parametrize("operation_ordinal", range(1, 9))
def test_all_closed_operations_execute_on_canonical_trees_without_effect(
    operation_ordinal: int,
) -> None:
    operation_type = f"HKRECON-OP-{operation_ordinal:03d}"
    plan, decision, language_inputs, artifacts, alignment = _execution_input(operation_type)

    result = _execute(plan, decision, language_inputs, artifacts, alignment)

    assert result.processing_outcome == "PASS"
    assert len(result.operation_results) == 2
    assert {item.operation_type_id for item in result.operation_results} == {operation_type}
    assert {item.result for item in result.operation_results} == {"APPLIED"}
    assert all(item.matched_source_unit_ids for item in result.operation_results)
    assert all(
        not source_id.startswith("art_")
        for item in result.operation_results
        for source_id in item.matched_source_unit_ids
    )
    assert len(result.provisional_language_trees) == 2
    assert all(
        parse_canonical_language_tree(tree).fingerprint == fingerprint
        for tree, fingerprint in zip(
            result.provisional_language_trees,
            result.provisional_language_tree_fingerprints,
            strict=True,
        )
    )
    assert result.provisional_bilingual_alignment_map == alignment
    document = result.document()
    assert document["execution_report_output"] == "NONE"
    assert document["reconstructed_artifact_output"] == "NONE"
    assert document["record_output"] == "NONE"
    assert document["external_effects"] == "NONE"


@pytest.mark.parametrize("operation_type", ["HKRECON-OP-001", "HKRECON-OP-002", "HKRECON-OP-006"])
def test_text_operations_preserve_final_source_unit_identity(operation_type: str) -> None:
    plan, decision, language_inputs, artifacts, alignment = _execution_input(operation_type)
    result = _execute(plan, decision, language_inputs, artifacts, alignment)

    for input_item, final_tree in zip(
        language_inputs, result.provisional_language_trees, strict=True
    ):
        before = parse_canonical_language_tree(_object(input_item["base_tree"]))
        after = parse_canonical_language_tree(final_tree)
        assert {unit.source_unit_id for unit in before.source_units} == {
            unit.source_unit_id for unit in after.source_units
        }


def test_second_language_failure_rolls_back_complete_plan() -> None:
    plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-001")
    zh_operation = _objects(_objects(plan.get("language_streams"))[1].get("operations"))[0]
    _object(zh_operation.get("before_state"))["content_fingerprint"] = SHA_ZERO
    later_operation = deepcopy(zh_operation)
    later_operation["sequence"] = 1
    later_operation["operation_instance_id"] = f"rop_{3:048x}"
    _objects(plan.get("language_streams"))[1]["operations"] = [zh_operation, later_operation]
    event = _objects(plan.get("event_chain"))[0]
    event["operation_instance_ids"] = checked_json_value(
        [f"rop_{1:048x}", f"rop_{2:048x}", f"rop_{3:048x}"]
    )
    decision = _decision(plan, 3)

    result = _execute(plan, decision, language_inputs, artifacts, alignment)

    assert result.processing_outcome == "BLOCK"
    assert result.reason_code == "RECONSTRUCTION_BEFORE_STATE_MISMATCH"
    assert [item.result for item in result.operation_results] == [
        "APPLIED",
        "FAILED_PRECONDITION",
        "NOT_RUN_AFTER_ATOMIC_FAILURE",
    ]
    assert result.operation_results[0].atomic_group_result == "ROLLED_BACK"
    assert result.provisional_language_trees == ()
    assert result.provisional_bilingual_alignment_map is None


def test_execution_rejects_unvalidated_plan_and_undeclared_input() -> None:
    plan, decision, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-001")
    invalid_decision = replace(decision, validated_reconstruction_plan_fingerprint=SHA_ZERO)
    with pytest.raises(RulebookError):
        _execute(plan, invalid_decision, language_inputs, artifacts, alignment)

    extra = _source_artifact(999, {"payload_kind": "TEXT", "content": "undeclared"})
    with pytest.raises(RulebookError):
        _execute(plan, decision, language_inputs, (*artifacts, extra), alignment)

    malformed_artifacts = deepcopy(artifacts)
    _object(malformed_artifacts[0].get("payload"))["unexpected"] = "FORBIDDEN"
    with pytest.raises(RulebookError):
        _execute(plan, decision, language_inputs, malformed_artifacts, alignment)


def test_execution_is_input_immutable_and_byte_reproducible() -> None:
    plan, decision, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-008")
    originals = deepcopy((plan, language_inputs, artifacts, alignment))

    first = _execute(plan, decision, language_inputs, artifacts, alignment)
    second = _execute(plan, decision, language_inputs, artifacts, alignment)

    assert canonicalize(checked_json_value(first.document())) == canonicalize(
        checked_json_value(second.document())
    )
    assert (plan, language_inputs, artifacts, alignment) == originals


def test_final_tree_or_source_inventory_mismatch_rolls_back() -> None:
    plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-006")
    streams = _objects(plan.get("language_streams"))
    streams[1]["expected_final_language_tree_fingerprint"] = SHA_ZERO
    result = _execute(plan, _decision(plan, 2), language_inputs, artifacts, alignment)
    assert result.reason_code == "RECONSTRUCTION_FINAL_TREE_MISMATCH"
    assert {item.atomic_group_result for item in result.operation_results} == {"ROLLED_BACK"}

    plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-006")
    _objects(plan.get("language_streams"))[1][
        "expected_complete_source_unit_inventory_fingerprint"
    ] = SHA_ZERO
    result = _execute(plan, _decision(plan, 2), language_inputs, artifacts, alignment)
    assert result.reason_code == "RECONSTRUCTION_SOURCE_UNIT_INVENTORY_MISMATCH"


def test_incomplete_bilingual_alignment_rolls_back_applied_operations() -> None:
    plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-003")
    groups = _array(alignment["groups"])
    groups.pop()
    alignment_ref = _ref("ARTIFACT", "art", 9999, _sha(alignment))
    for stream in _objects(plan.get("language_streams")):
        stream["expected_bilingual_alignment_map_ref"] = alignment_ref

    result = _execute(plan, _decision(plan, 2), language_inputs, artifacts, alignment)

    assert result.processing_outcome == "BLOCK"
    assert result.reason_code == "RECONSTRUCTION_BILINGUAL_ALIGNMENT_MISMATCH"
    assert {item.atomic_group_result for item in result.operation_results} == {"ROLLED_BACK"}


def test_op008_rejects_structure_the_frozen_renderer_cannot_represent() -> None:
    plan, decision, language_inputs, artifacts, alignment = _execution_input(
        "HKRECON-OP-008", unsupported_op008=True
    )

    result = _execute(plan, decision, language_inputs, artifacts, alignment)

    assert result.processing_outcome == "BLOCK"
    assert result.reason_code == "RECONSTRUCTION_RENDERER_UNSUPPORTED"
    assert result.operation_results[0].result == "FAILED_PRECONDITION"
    assert result.operation_results[1].result == "NOT_RUN_AFTER_ATOMIC_FAILURE"


def test_base_tree_identity_and_canonical_fingerprints_are_enforced() -> None:
    plan, decision, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-003")
    changed_inputs = deepcopy(language_inputs)
    _object(changed_inputs[0].get("base_tree_ref"))["ref_id"] = f"art_{999:048x}"
    with pytest.raises(RulebookError):
        _execute(plan, decision, changed_inputs, artifacts, alignment)

    changed_inputs = deepcopy(language_inputs)
    tree = _object(changed_inputs[0].get("base_tree"))
    units = _array(tree["source_units"])
    assert isinstance(units[0], dict)
    units[0]["content"] = "tampered"
    with pytest.raises(RulebookError):
        _execute(plan, decision, changed_inputs, artifacts, alignment)


def test_plan_cannot_modify_a_declared_independent_boundary() -> None:
    plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-001")
    closure = _object(plan.get("dependency_closure"))
    target_ref = _objects(closure.get("primary_affected_location_refs"))[0]
    closure["independent_sibling_boundary_refs"] = [target_ref]

    with pytest.raises(RulebookError):
        _execute(plan, _decision(plan, 2), language_inputs, artifacts, alignment)


def frozen_execution_fixture_documents(
    fixture_index: int,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """Build one deterministic package fixture and its exact expected result."""
    fixture_id = f"HKLEG-RECON-EXEC-FIX-{fixture_index:03d}"
    if fixture_index in range(1, 9):
        operation_type = f"HKRECON-OP-{fixture_index:03d}"
        title = f"Canonical execution passes for {operation_type}"
        plan, decision, language_inputs, artifacts, alignment = _execution_input(operation_type)
        decision = replace(decision, fixture_id=fixture_id)
    elif fixture_index == 9:
        title = "A second-language before-state failure rolls back the complete Plan"
        plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-001")
        zh_stream = _objects(plan.get("language_streams"))[1]
        zh_operation = _objects(zh_stream.get("operations"))[0]
        _object(zh_operation.get("before_state"))["content_fingerprint"] = SHA_ZERO
        later_operation = deepcopy(zh_operation)
        later_operation["sequence"] = 1
        later_operation["operation_instance_id"] = f"rop_{3:048x}"
        zh_stream["operations"] = [zh_operation, later_operation]
        event = _objects(plan.get("event_chain"))[0]
        event["operation_instance_ids"] = checked_json_value(
            [f"rop_{1:048x}", f"rop_{2:048x}", f"rop_{3:048x}"]
        )
        decision = _decision(plan, 3, fixture_id)
    elif fixture_index == 10:
        title = "A final canonical tree mismatch rolls back applied operations"
        plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-006")
        _objects(plan.get("language_streams"))[1]["expected_final_language_tree_fingerprint"] = (
            SHA_ZERO
        )
        decision = _decision(plan, 2, fixture_id)
    elif fixture_index == 11:
        title = "A final source-unit inventory mismatch rolls back applied operations"
        plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-006")
        _objects(plan.get("language_streams"))[1][
            "expected_complete_source_unit_inventory_fingerprint"
        ] = SHA_ZERO
        decision = _decision(plan, 2, fixture_id)
    elif fixture_index == 12:
        title = "An incomplete final bilingual alignment rolls back applied operations"
        plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-003")
        _array(alignment["groups"]).pop()
        alignment_ref = _ref("ARTIFACT", "art", 9999, _sha(alignment))
        for stream in _objects(plan.get("language_streams")):
            stream["expected_bilingual_alignment_map_ref"] = alignment_ref
        decision = _decision(plan, 2, fixture_id)
    elif fixture_index == 13:
        title = "OP008 rejects a structure outside the frozen renderer contract"
        plan, decision, language_inputs, artifacts, alignment = _execution_input(
            "HKRECON-OP-008",
            unsupported_op008=True,
        )
        decision = replace(decision, fixture_id=fixture_id)
    else:
        message = f"unknown reconstruction execution fixture {fixture_index}"
        raise ValueError(message)

    request = ReconstructionExecutionRequest(
        package_root=PACKAGE_ROOT,
        plan=plan,
        validation_decision=decision,
        language_inputs=language_inputs,
        source_artifacts=artifacts,
        bilingual_alignment_map=alignment,
        execution_mode="OFFLINE_SYNTHETIC_CONFORMANCE",
    )
    request_document = request.document()
    result = execute_validated_reconstruction_plan(request).document()
    expected_path = f"expected/reconstruction-execution/{fixture_id}.json"
    fixture = _json_object(
        {
            "fixture_id": fixture_id,
            "title": title,
            "synthetic": True,
            "status": "FROZEN_PARTIAL",
            "input_fingerprint": _sha(request_document),
            "input": request_document,
            "expected_artifact": {
                "path": expected_path,
                "fingerprint": SHA_ZERO,
            },
        }
    )
    return fixture, result


def _artifact_request(operation_type: str) -> ReconstructionArtifactBuildRequest:
    plan, decision, language_inputs, artifacts, alignment = _execution_input(operation_type)
    execution = _execute(plan, decision, language_inputs, artifacts, alignment)
    plan_contracts = _object(plan.get("contracts"))
    contracts = {
        "source_rulebook": plan_contracts["source_rulebook"],
        "operation_registry": plan_contracts["operation_registry"],
        "source_tree": plan_contracts["tree"],
        "renderer": plan_contracts["renderer"],
        "alignment": _contract_ref("asklegal.hk-legislation.bilingual-alignment", 21),
        "identity": plan_contracts["identity"],
        "lineage": _contract_ref("asklegal.hk-legislation.identity-lineage", 22),
        "traceability": plan_contracts["traceability"],
        "artifact": _contract_ref(
            "asklegal.hk-legislation.reconstructed-consolidation-artifact",
            23,
        ),
    }
    base_trees = tuple(
        _object(language_input.get("base_tree")) for language_input in language_inputs
    )
    base_locations = {
        _text(_object(node.get("legal_location_ref"))["ref_id"]): _object(
            node.get("legal_location_ref")
        )
        for node in _objects(base_trees[0].get("nodes"))
    }
    final_tree = _objects(execution.document().get("provisional_language_trees"))[0]
    final_locations = {
        _text(_object(node.get("legal_location_ref"))["ref_id"]): _object(
            node.get("legal_location_ref")
        )
        for node in _objects(final_tree.get("nodes"))
    }
    new_refs = [final_locations[key] for key in sorted(final_locations.keys() - base_locations)]
    ended_refs = [base_locations[key] for key in sorted(base_locations.keys() - final_locations)]
    operation_id = _text(
        _objects(_objects(plan.get("language_streams"))[0].get("operations"))[0][
            "operation_instance_id"
        ]
    )
    decision_ref = _ref("DECISION", "ldd", 91)
    evidence = _objects(plan.get("evidence_refs"))[0]
    lineage_links: list[dict[str, JsonValue]] = []
    if new_refs and ended_refs:
        lineage_links.extend(
            _json_object(
                {
                    "link_type": "REPLACEMENT",
                    "predecessor_ref": predecessor,
                    "successor_ref": successor,
                    "operation_instance_id": operation_id,
                    "decision_ref": decision_ref,
                    "evidence_refs": [evidence],
                }
            )
            for predecessor, successor in zip(ended_refs, new_refs, strict=True)
        )
    else:
        lineage_links.extend(
            _json_object(
                {
                    "link_type": "INSERTION",
                    "predecessor_ref": None,
                    "successor_ref": successor,
                    "operation_instance_id": operation_id,
                    "decision_ref": decision_ref,
                    "evidence_refs": [evidence],
                }
            )
            for successor in new_refs
        )
        lineage_links.extend(
            _json_object(
                {
                    "link_type": "REMOVAL",
                    "predecessor_ref": predecessor,
                    "successor_ref": None,
                    "operation_instance_id": operation_id,
                    "decision_ref": decision_ref,
                    "evidence_refs": [evidence],
                }
            )
            for predecessor in ended_refs
        )
    return ReconstructionArtifactBuildRequest(
        package_root=PACKAGE_ROOT,
        reconstructed_consolidation_artifact_id=f"rca_{1:048x}",
        plan=plan,
        execution=execution,
        base_language_trees=base_trees,
        coverage_gap_ref=_ref("COVERAGE_GAP", "cvg", 1),
        identity_lineage_decision_ref=decision_ref,
        operative_state_decision_ref=_ref("DECISION", "ldd", 92),
        contracts=_json_object(contracts),
        authority_note_template_contract_ref=_contract_ref(
            "asklegal.hk-legislation.reconstruction-authority-note",
            24,
        ),
        lineage_links=tuple(lineage_links),
    )


def test_successful_execution_builds_complete_immutable_eleven_file_artifact() -> None:
    request = _artifact_request("HKRECON-OP-001")

    first = build_reconstructed_consolidation_artifact(request)
    second = build_reconstructed_consolidation_artifact(request)

    assert first == second
    assert len(first.inventory) == 11
    assert len(first.files) == 11
    assert {path for path, _ in first.files} == {
        "manifest.json",
        "trees/en.json",
        "trees/zh-Hant.json",
        "source-units/en.jsonl",
        "source-units/zh-Hant.jsonl",
        "reconstructed-location-units.jsonl",
        "bilingual-alignment-map.json",
        "dependency-closure-proof.json",
        "source-unit-coverage-proof.json",
        "derivation-map.json",
        "identity-lineage-result.json",
    }
    manifest = _object(parse_json_bytes(first.file_bytes("manifest.json"), max_bytes=1_000_000))
    assert "root_fingerprint" not in manifest
    assert "reconstruction_execution_report_id" not in manifest
    assert manifest["reconstructed_consolidation_artifact_id"] == f"rca_{1:048x}"
    assert len(_array(manifest["files"])) == 10
    assert first.document()["report_output"] == "NONE"
    assert first.document()["record_output"] == "NONE"
    assert first.document()["external_effects"] == "NONE"


@pytest.mark.parametrize(
    "operation_type",
    [f"HKRECON-OP-{index:03d}" for index in range(1, 9)],
)
def test_every_registered_operation_builds_a_complete_artifact(operation_type: str) -> None:
    artifact = build_reconstructed_consolidation_artifact(_artifact_request(operation_type))

    assert len(artifact.files) == 11
    assert artifact.document()["external_effects"] == "NONE"


def test_artifact_rejects_contract_drift_before_emitting_package() -> None:
    request = _artifact_request("HKRECON-OP-001")
    contracts = deepcopy(request.contracts)
    _object(contracts.get("renderer"))["fingerprint"] = SHA_ZERO

    with pytest.raises(RulebookError):
        build_reconstructed_consolidation_artifact(replace(request, contracts=contracts))


def _report_contracts(
    plan: dict[str, JsonValue],
    artifact_contracts: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    plan_contracts = _object(plan.get("contracts"))
    return _json_object(
        {
            "source_rulebook": plan_contracts["source_rulebook"],
            "operation_registry": plan_contracts["operation_registry"],
            "source_interpretation": plan_contracts["source_interpretation"],
            "source_tree": plan_contracts["tree"],
            "renderer": plan_contracts["renderer"],
            "alignment": artifact_contracts["alignment"],
            "identity": plan_contracts["identity"],
            "lineage": artifact_contracts["lineage"],
            "traceability": plan_contracts["traceability"],
            "execution": plan_contracts["execution"],
            "artifact": artifact_contracts["artifact"],
            "report": _contract_ref(
                "asklegal.hk-legislation.reconstruction-execution-report",
                25,
            ),
        }
    )


def _successful_report_request() -> ReconstructionReportBuildRequest:
    artifact_request = _artifact_request("HKRECON-OP-001")
    artifact = build_reconstructed_consolidation_artifact(artifact_request)
    return ReconstructionReportBuildRequest(
        package_root=PACKAGE_ROOT,
        reconstruction_execution_report_id=f"rex_{1:048x}",
        plan=artifact_request.plan,
        execution=artifact_request.execution,
        engine_build_ref=_ref("ENGINE_BUILD", "eng", 1),
        contracts=_report_contracts(artifact_request.plan, artifact_request.contracts),
        coverage_gap_ref=artifact_request.coverage_gap_ref,
        artifact=artifact,
    )


def _blocked_report_request() -> ReconstructionReportBuildRequest:
    plan, _, language_inputs, artifacts, alignment = _execution_input("HKRECON-OP-006")
    _objects(plan.get("language_streams"))[1]["expected_final_language_tree_fingerprint"] = SHA_ZERO
    execution = _execute(plan, _decision(plan, 2), language_inputs, artifacts, alignment)
    assert execution.processing_outcome == "BLOCK"
    artifact_contracts = _artifact_request("HKRECON-OP-001").contracts
    return ReconstructionReportBuildRequest(
        package_root=PACKAGE_ROOT,
        reconstruction_execution_report_id=f"rex_{2:048x}",
        plan=plan,
        execution=execution,
        engine_build_ref=_ref("ENGINE_BUILD", "eng", 1),
        contracts=_report_contracts(plan, artifact_contracts),
        coverage_gap_ref=_ref("COVERAGE_GAP", "cvg", 2),
        artifact=None,
    )


def test_artifact_readback_rejects_tampered_member_bytes() -> None:
    request = _artifact_request("HKRECON-OP-001")
    artifact = build_reconstructed_consolidation_artifact(request)
    files = tuple(
        (path, raw + b" ") if path == "trees/en.json" else (path, raw)
        for path, raw in artifact.files
    )

    with pytest.raises(RulebookError):
        validate_reconstructed_consolidation_artifact(
            PACKAGE_ROOT,
            replace(artifact, files=files),
        )


def test_successful_execution_report_is_complete_reproducible_and_effect_free() -> None:
    request = _successful_report_request()

    first = build_reconstruction_execution_report(request)
    second = build_reconstruction_execution_report(request)
    document = first.document()

    assert first == second
    assert document["processing_outcome"] == "PASS"
    assert document["reason_codes"] == ["RECONSTRUCTION_COMPLETE"]
    assert document["selection_consequence"] == "RECONSTRUCTION"
    assert document["external_effects"] == "NONE"
    assert _object(document["artifact_output"])["record_output"] == "NONE"
    assert len(_objects(document["language_results"])) == 2
    assert first.report_ref()["fingerprint"] == _bytes_sha(first.canonical_bytes)


@pytest.mark.parametrize(
    "mutation",
    [
        "artifact_record_output",
        "source_contract_review",
        "base_validation",
        "bilingual_validation",
        "coverage_disposition",
        "report_contract",
        "dependency_validation",
        "language_coverage",
        "event_count",
        "affected_inventory",
    ],
)
def test_report_replay_validation_rejects_forged_success_coherence(mutation: str) -> None:
    report = build_reconstruction_execution_report(_successful_report_request())
    document = report.document()
    if mutation == "artifact_record_output":
        _object(document["artifact_output"])["record_output"] = "FORGED"
    elif mutation == "source_contract_review":
        document["source_contract_review_required"] = True
    elif mutation == "base_validation":
        _object(document["base_validation"])["complete"] = False
    elif mutation == "bilingual_validation":
        _object(document["bilingual_validation"])["legal_effect_bound"] = False
    elif mutation == "coverage_disposition":
        _object(document["coverage_consequence"])["disposition"] = "EXECUTION_FAILED"
    elif mutation == "report_contract":
        contracts = _object(document["contracts"])
        _object(contracts["report"])["contract_id"] = "asklegal.forged-report"
    elif mutation == "dependency_validation":
        _object(document["dependency_validation"])["ownership_complete"] = False
    elif mutation == "language_coverage":
        _objects(document["language_results"])[0]["complete_source_unit_coverage"] = False
    elif mutation == "event_count":
        _object(document["event_chain_validation"])["event_count"] = 99
    else:
        _object(document["artifact_output"])["affected_location_inventory_fingerprint"] = SHA_ZERO
    raw = canonicalize(checked_json_value(document))
    forged = reconstruction_report_module.ReconstructionExecutionReport(
        report.reconstruction_execution_report_id,
        _bytes_sha(raw),
        raw,
    )

    with pytest.raises(RulebookError):
        reconstruction_report_module.validate_reconstruction_execution_report(
            PACKAGE_ROOT,
            forged,
        )


def test_report_replay_validation_rejects_official_version_role_relabel() -> None:
    report = build_reconstruction_execution_report(_successful_report_request())
    document = report.document()
    base = _object(document["base_validation"])
    official_version = _object(base["official_version_ref"])
    official_version["ref_type"] = "ENGINE_BUILD"
    raw = canonicalize(checked_json_value(document))
    forged = reconstruction_report_module.ReconstructionExecutionReport(
        report.reconstruction_execution_report_id,
        _bytes_sha(raw),
        raw,
    )

    with pytest.raises(RulebookError):
        reconstruction_report_module.validate_reconstruction_execution_report(
            PACKAGE_ROOT,
            forged,
        )


@pytest.mark.parametrize(
    ("request_kind", "path", "field", "value"),
    [
        ("success", ("base_validation", "official_version_ref"), "ref_id", "eng_" + "1" * 48),
        ("success", ("engine_build_ref",), "ref_type", "OFFICIAL_VERSION"),
        ("success", ("engine_build_ref",), "ref_id", "ofv_" + "1" * 48),
        ("success", ("event_chain_validation", "event_refs", 0), "ref_type", "ARTIFACT"),
        ("success", ("event_chain_validation", "event_refs", 0), "ref_id", "art_" + "1" * 48),
        (
            "blocked",
            ("dependency_validation", "affected_location_refs", 0),
            "ref_type",
            "OFFICIAL_VERSION",
        ),
        (
            "blocked",
            ("dependency_validation", "affected_location_refs", 0),
            "ref_id",
            "ofv_" + "1" * 48,
        ),
        (
            "success",
            ("bilingual_validation", "expected_alignment_map_ref"),
            "ref_type",
            "LEGAL_ITEM",
        ),
        (
            "success",
            ("bilingual_validation", "expected_alignment_map_ref"),
            "ref_id",
            "lit_" + "1" * 48,
        ),
        (
            "blocked",
            ("coverage_consequence", "coverage_gap_ref"),
            "ref_type",
            "LEGAL_LOCATION",
        ),
        (
            "blocked",
            ("coverage_consequence", "coverage_gap_ref"),
            "ref_id",
            "loc_" + "1" * 48,
        ),
        (
            "fallback",
            ("coverage_consequence", "fallback_selection_ref"),
            "ref_type",
            "COVERAGE_GAP",
        ),
        (
            "fallback",
            ("coverage_consequence", "fallback_selection_ref"),
            "ref_id",
            "cvg_" + "1" * 48,
        ),
        (
            "success",
            ("artifact_output", "manifest_ref"),
            "media_type",
            "application/x-ndjson",
        ),
        (
            "success",
            ("artifact_output", "reconstructed_consolidation_artifact_ref"),
            "ref_type",
            "ARTIFACT",
        ),
        (
            "success",
            ("artifact_output", "en_final_tree_ref"),
            "role",
            "SOURCE_UNITS_EN",
        ),
        (
            "success",
            ("artifact_output", "dependency_closure_proof_ref"),
            "role",
            "DERIVATION_MAP",
        ),
        (
            "success",
            ("artifact_output", "source_unit_coverage_proof_ref"),
            "role",
            "IDENTITY_LINEAGE_RESULT",
        ),
        (
            "success",
            ("contracts", "lineage"),
            "contract_id",
            "asklegal.hk-legislation.bilingual-alignment",
        ),
    ],
)
def test_report_replay_validation_rejects_reference_role_and_identity_aliases(
    request_kind: str,
    path: tuple[str | int, ...],
    field: str,
    value: str,
) -> None:
    request = _successful_report_request()
    if request_kind == "blocked":
        request = _blocked_report_request()
    elif request_kind == "fallback":
        request = replace(
            _blocked_report_request(),
            fallback_selection_ref=_ref("FALLBACK_SELECTION", "fbs", 1),
        )
    report = build_reconstruction_execution_report(request)
    document = report.document()
    _path_object(document, path)[field] = value
    raw = canonicalize(checked_json_value(document))
    forged = reconstruction_report_module.ReconstructionExecutionReport(
        report.reconstruction_execution_report_id,
        _bytes_sha(raw),
        raw,
    )

    with pytest.raises(RulebookError):
        reconstruction_report_module.validate_reconstruction_execution_report(
            PACKAGE_ROOT,
            forged,
        )


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        ("QUARANTINE", "RECONSTRUCTION_FINAL_TREE_MISMATCH"),
        ("BLOCK", "RECONSTRUCTION_COMPLETE"),
        ("BLOCK", "RECONSTRUCTION_OPERATION_APPLIED"),
    ],
)
def test_report_replay_validation_rejects_unsupported_outcome_reason_mapping(
    outcome: str,
    reason: str,
) -> None:
    report = build_reconstruction_execution_report(_blocked_report_request())
    document = report.document()
    document["processing_outcome"] = outcome
    document["reason_codes"] = [reason]
    raw = canonicalize(checked_json_value(document))
    forged = reconstruction_report_module.ReconstructionExecutionReport(
        report.reconstruction_execution_report_id,
        _bytes_sha(raw),
        raw,
    )

    with pytest.raises(RulebookError):
        reconstruction_report_module.validate_reconstruction_execution_report(
            PACKAGE_ROOT,
            forged,
        )


def test_report_replay_validation_preserves_process_control_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = build_reconstruction_execution_report(_successful_report_request())

    def interrupt(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise KeyboardInterrupt

    monkeypatch.setattr(reconstruction_report_module, "_validate_schema", interrupt)

    with pytest.raises(KeyboardInterrupt):
        reconstruction_report_module.validate_reconstruction_execution_report(
            PACKAGE_ROOT,
            report,
        )


def test_blocked_execution_report_accounts_for_every_operation_and_emits_no_artifact() -> None:
    request = _blocked_report_request()

    report = build_reconstruction_execution_report(request).document()

    assert report["processing_outcome"] == "BLOCK"
    assert report["selection_consequence"] == "NO_RECORD"
    assert report["reason_codes"] == ["RECONSTRUCTION_FINAL_TREE_MISMATCH"]
    output = _object(report["artifact_output"])
    assert output == {
        "record_output": "NONE",
        "reconstructed_artifact_count": 0,
        "artifact_refs": [],
    }
    language_results = _objects(report["language_results"])
    assert sum(len(_objects(result["operation_results"])) for result in language_results) == 2


def test_blocked_execution_report_requires_separate_fallback_reference() -> None:
    request = replace(
        _blocked_report_request(),
        fallback_selection_ref=_ref("FALLBACK_SELECTION", "fbs", 1),
    )

    report = build_reconstruction_execution_report(request).document()

    assert report["selection_consequence"] == "FALLBACK"
    assert _object(report["coverage_consequence"])["fallback_selection_ref"] == (
        request.fallback_selection_ref
    )


def test_report_rejects_tampered_artifact_and_incomplete_operation_accounting() -> None:
    request = _successful_report_request()
    assert request.artifact is not None
    tampered_files = tuple(
        (path, raw + b" ") if path == "manifest.json" else (path, raw)
        for path, raw in request.artifact.files
    )
    with pytest.raises(RulebookError):
        build_reconstruction_execution_report(
            replace(request, artifact=replace(request.artifact, files=tampered_files))
        )

    incomplete_execution = replace(
        request.execution,
        operation_results=request.execution.operation_results[:-1],
    )
    with pytest.raises(RulebookError):
        build_reconstruction_execution_report(replace(request, execution=incomplete_execution))


def frozen_report_fixture_documents(
    fixture_index: int,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """Build one frozen combined artifact/Report fixture and exact Report."""
    fixture_id = f"HKLEG-RECON-REPORT-FIX-{fixture_index:03d}"
    artifact_build: dict[str, JsonValue] | None
    if fixture_index == 1:
        title = "Successful execution builds an exact artifact and PASS Report"
        artifact_request = _artifact_request("HKRECON-OP-001")
        artifact = build_reconstructed_consolidation_artifact(artifact_request)
        report_request = ReconstructionReportBuildRequest(
            package_root=PACKAGE_ROOT,
            reconstruction_execution_report_id=f"rex_{1:048x}",
            plan=artifact_request.plan,
            execution=artifact_request.execution,
            engine_build_ref=_ref("ENGINE_BUILD", "eng", 1),
            contracts=_report_contracts(artifact_request.plan, artifact_request.contracts),
            coverage_gap_ref=artifact_request.coverage_gap_ref,
            artifact=artifact,
        )
        artifact_build = _json_object(
            {
                "reconstructed_consolidation_artifact_id": (
                    artifact_request.reconstructed_consolidation_artifact_id
                ),
                "base_language_trees": list(artifact_request.base_language_trees),
                "coverage_gap_ref": artifact_request.coverage_gap_ref,
                "identity_lineage_decision_ref": (artifact_request.identity_lineage_decision_ref),
                "operative_state_decision_ref": (artifact_request.operative_state_decision_ref),
                "contracts": artifact_request.contracts,
                "authority_note_template_contract_ref": (
                    artifact_request.authority_note_template_contract_ref
                ),
                "lineage_links": list(artifact_request.lineage_links),
            }
        )
    elif fixture_index == 2:
        title = "A failed final tree emits a complete no-artifact BLOCK Report"
        report_request = _blocked_report_request()
        artifact_build = None
    else:
        message = f"unknown reconstruction Report fixture {fixture_index}"
        raise ValueError(message)
    input_document = _json_object(
        {
            "reconstruction_execution_report_id": (
                report_request.reconstruction_execution_report_id
            ),
            "plan": report_request.plan,
            "execution": report_request.execution.document(),
            "engine_build_ref": report_request.engine_build_ref,
            "contracts": report_request.contracts,
            "coverage_gap_ref": report_request.coverage_gap_ref,
            "artifact_build": artifact_build,
            "fallback_selection_ref": report_request.fallback_selection_ref,
        }
    )
    expected_path = f"expected/reconstruction-report/{fixture_id}.json"
    fixture = _json_object(
        {
            "fixture_id": fixture_id,
            "title": title,
            "synthetic": True,
            "status": "FROZEN_PARTIAL",
            "input_fingerprint": _sha(input_document),
            "input": input_document,
            "expected_artifact": {"path": expected_path, "fingerprint": SHA_ZERO},
        }
    )
    expected = build_reconstruction_execution_report(report_request).document()
    return fixture, expected
