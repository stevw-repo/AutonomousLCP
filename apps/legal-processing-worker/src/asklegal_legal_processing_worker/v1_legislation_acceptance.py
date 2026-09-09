"""Retained, network-inert Hong Kong V1 legislation acceptance composition.

The module owns the narrow live bridge from exact acquired HKeL/GLD objects to
the source-neutral Legal Desk and corpus-release kernels.  It deliberately
supports one closed HKeL XML dialect; an unknown publisher shape is NOT_READY,
never repaired or guessed.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Never, Protocol

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import ServingRecordProfile
from asklegal_evidence_vault import ExactObjectReference, VaultName
from asklegal_legal_desks.hk_canonical_legislation import (
    BILINGUAL_ALIGNMENT_MAP_SCHEMA,
    CANONICAL_TREE_CONTRACT_VERSION,
    BilingualAlignmentMap,
    CanonicalLanguageTree,
    parse_bilingual_alignment_map,
    seal_canonical_language_tree,
)
from asklegal_legal_desks.hk_legislation_events import (
    HKLegislationEvent,
    HKLegislationEventKind,
    HKLegislationEventSource,
    HKLegislationEventTimeline,
    HKLegislationSourceContractReview,
    decide_hk_legislation_state,
)
from asklegal_legal_desks.hk_legislation_partition import (
    AlignedPartitionNode,
    BilingualPartitionExecution,
    BilingualPartitionRequest,
    BilingualPartitionResult,
    PartitionServingProfile,
    partition_canonical_bilingual_location,
    partition_serving_profile_fingerprint,
)
from asklegal_legal_desks.hk_legislation_records import (
    HKLegislationAuthorityNoteSeed,
    HKLegislationCandidateInput,
    HKLegislationServingPayload,
    HKLegislationTraceabilityReference,
    bind_hk_legislation_inventory_decision_authority,
    build_hk_legislation_candidate_set,
    canonical_hk_legislation_candidate_set,
)
from asklegal_management_register import LocalLegalIdentityRegister
from asklegal_management_register_ports import (
    LegalIdentityKind,
    LegalIdentityRequest,
    SearchRecordIdentityRequest,
)

from .hk_legislation_release import (
    HKLegislationAllocatedIdentitySet,
    HKLegislationRecordAllocation,
    HKLegislationScopeReleaseRequest,
    accept_hk_legislation_acquisition_manifest,
    build_hk_legislation_scope_release,
)

_SCOPES = (
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
)
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,159}$")
_UTC_OFFSET = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|\+00:00)$")


class LegislationAcceptanceError(RuntimeError):
    """One closed live-composition failure."""


class _PrimaryVault(Protocol):
    def read_exact(self, reference: ExactObjectReference) -> bytes: ...


@dataclass(frozen=True, slots=True)
class _Retained:
    reference: ExactObjectReference
    content: bytes


@dataclass(frozen=True, slots=True)
class _ParsedItem:
    scope: str
    inventory_item_id: str
    source_key: str
    en_xml: _Retained
    zh_xml: _Retained
    xsd: _Retained
    gld_pdf: _Retained
    gld_event: _Retained
    event: dict[str, JsonValue]


class _Utf8ByteCounter:
    def __init__(self, profile: PartitionServingProfile) -> None:
        self.profile_id = profile.profile_id
        self.profile_fingerprint = profile.profile_fingerprint
        self.tokenizer_id = profile.tokenizer_id

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))


def _fail(code: str) -> Never:
    raise LegislationAcceptanceError(code)


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _id(prefix: str, *parts: str) -> str:
    digest = sha256("\x1f".join(parts).encode()).hexdigest()[:48]
    return f"{prefix}_{digest}"


def _object(value: JsonValue | object, code: str) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    if not isinstance(parsed, dict):
        _fail(code)
    return parsed


def _text(value: JsonValue | object, code: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        _fail(code)
    return value


def _canonical_object(content: bytes, code: str) -> dict[str, JsonValue]:
    try:
        value = parse_json_bytes(content, max_bytes=16_777_216)
        if type(value) is not dict or canonicalize(value) != content:
            _fail(code)
    except LegislationAcceptanceError:
        raise
    except (TypeError, UnicodeError, ValueError) as error:
        raise LegislationAcceptanceError(code) from error
    else:
        return value


def _reference(value: object, code: str) -> ExactObjectReference:
    document = _object(value, code)
    if frozenset(document) != frozenset(
        {
            "logical_key",
            "version_id",
            "content_fingerprint",
            "body_length",
        }
    ):
        _fail(code)
    try:
        return ExactObjectReference(
            VaultName.PRIMARY,
            _text(document["logical_key"], code),
            _text(document["version_id"], code),
            _text(document["content_fingerprint"], code),
            document["body_length"] if type(document["body_length"]) is int else -1,
        )
    except (TypeError, ValueError) as error:
        raise LegislationAcceptanceError(code) from error


def _read(
    value: object,
    verified: dict[tuple[str, str, str, int], ExactObjectReference],
    vault: _PrimaryVault,
    code: str,
) -> _Retained:
    reference = _reference(value, code)
    key = (
        reference.logical_key,
        reference.version_id,
        reference.fingerprint,
        reference.byte_length,
    )
    if key not in verified:
        _fail("LEGISLATION_ACQUISITION_BINDING_INVALID")
    try:
        content = vault.read_exact(reference)
    except Exception as error:
        raise LegislationAcceptanceError(code) from error
    if len(content) != reference.byte_length or _fingerprint(content) != reference.fingerprint:
        _fail("LEGISLATION_ACQUISITION_OBJECT_DRIFT")
    return _Retained(reference, content)


def _verified_index(
    verified_inputs: Mapping[str, JsonValue], operation_id: str
) -> tuple[dict[tuple[str, str, str, int], ExactObjectReference], str, str]:
    document = dict(verified_inputs)
    if document.get("operation_id") != operation_id:
        _fail("LEGISLATION_VERIFIED_INPUTS_INVALID")
    command = _text(document.get("command_fingerprint"), "LEGISLATION_VERIFIED_INPUTS_INVALID")
    cutoff = _text(document.get("observation_cutoff"), "LEGISLATION_VERIFIED_INPUTS_INVALID")
    if _FINGERPRINT.fullmatch(command) is None or _UTC_OFFSET.fullmatch(cutoff) is None:
        _fail("LEGISLATION_VERIFIED_INPUTS_INVALID")
    families = document.get("families")
    if type(families) is not list:
        _fail("LEGISLATION_VERIFIED_INPUTS_INVALID")
    family_documents = [_object(item, "LEGISLATION_VERIFIED_INPUTS_INVALID") for item in families]
    matches = [item for item in family_documents if item.get("source_family") == "LEGISLATION"]
    if len(matches) != 1 or matches[0].get("result") != "COMPLETE":
        _fail("LEGISLATION_ACQUISITION_NOT_READY")
    raw = matches[0].get("verified_objects")
    if type(raw) is not list or not raw:
        _fail("LEGISLATION_ACQUISITION_NOT_READY")
    result: dict[tuple[str, str, str, int], ExactObjectReference] = {}
    for item in raw:
        reference = _reference(item, "LEGISLATION_VERIFIED_INPUTS_INVALID")
        key = (
            reference.logical_key,
            reference.version_id,
            reference.fingerprint,
            reference.byte_length,
        )
        if key in result:
            _fail("LEGISLATION_VERIFIED_INPUTS_INVALID")
        result[key] = reference
    return result, command, cutoff


def _source_bundle(
    verified: dict[tuple[str, str, str, int], ExactObjectReference],
    vault: _PrimaryVault,
    operation_id: str,
    cutoff: str,
) -> dict[str, JsonValue]:
    references = [
        reference
        for reference in verified.values()
        if reference.logical_key.endswith("/source-bundle.json")
    ]
    if len(references) != 1:
        _fail("LEGISLATION_SOURCE_BUNDLE_NOT_READY")
    matches: list[dict[str, JsonValue]] = []
    for reference in references:
        content = vault.read_exact(reference)
        if len(content) != reference.byte_length or _fingerprint(content) != reference.fingerprint:
            _fail("LEGISLATION_ACQUISITION_OBJECT_DRIFT")
        try:
            candidate = _canonical_object(content, "LEGISLATION_SOURCE_BUNDLE_INVALID")
        except LegislationAcceptanceError:
            continue
        if candidate.get("schema_id") == "asklegal.hk-v1-legislation-source-bundle/v1":
            matches.append(candidate)
    if len(matches) != 1:
        _fail("LEGISLATION_SOURCE_BUNDLE_NOT_READY")
    bundle = matches[0]
    if (
        frozenset(bundle)
        != frozenset({"schema_id", "schema_version", "operation_id", "observation_cutoff", "items"})
        or bundle.get("schema_version") != "1.0.0"
        or bundle.get("operation_id") != operation_id
        or bundle.get("observation_cutoff") != cutoff
    ):
        _fail("LEGISLATION_SOURCE_BUNDLE_INVALID")
    return bundle


def _parse_items(
    bundle: dict[str, JsonValue],
    verified: dict[tuple[str, str, str, int], ExactObjectReference],
    vault: _PrimaryVault,
) -> tuple[_ParsedItem, ...]:
    raw_items = bundle.get("items")
    if type(raw_items) is not list or len(raw_items) != len(_SCOPES):
        _fail("LEGISLATION_SOURCE_BUNDLE_INCOMPLETE")
    items: list[_ParsedItem] = []
    for raw in raw_items:
        item = _object(raw, "LEGISLATION_SOURCE_BUNDLE_INVALID")
        if frozenset(item) != frozenset(
            {
                "scope_id",
                "inventory_item_id",
                "source_key",
                "en_xml",
                "zh_hant_xml",
                "xsd",
                "gld_pdf",
                "gld_event",
            }
        ):
            _fail("LEGISLATION_SOURCE_BUNDLE_INVALID")
        scope = _text(item["scope_id"], "LEGISLATION_SOURCE_BUNDLE_INVALID")
        source_key = _text(item["source_key"], "LEGISLATION_SOURCE_BUNDLE_INVALID")
        parsed = _ParsedItem(
            scope,
            _text(item["inventory_item_id"], "LEGISLATION_SOURCE_BUNDLE_INVALID"),
            source_key,
            _read(item["en_xml"], verified, vault, "LEGISLATION_HKEL_XML_NOT_READY"),
            _read(item["zh_hant_xml"], verified, vault, "LEGISLATION_HKEL_XML_NOT_READY"),
            _read(item["xsd"], verified, vault, "LEGISLATION_HKEL_XSD_NOT_READY"),
            _read(item["gld_pdf"], verified, vault, "LEGISLATION_GLD_EVIDENCE_NOT_READY"),
            _read(item["gld_event"], verified, vault, "LEGISLATION_GLD_EVIDENCE_NOT_READY"),
            {},
        )
        event = _canonical_object(parsed.gld_event.content, "LEGISLATION_GLD_EVIDENCE_INVALID")
        if (
            frozenset(event)
            != frozenset(
                {
                    "schema_id",
                    "schema_version",
                    "source_key",
                    "gazette_id",
                    "publication_at",
                    "commencement_at",
                    "source_pdf_fingerprint",
                }
            )
            or event.get("schema_id") != "asklegal.hk-v1-gld-event-evidence/v1"
            or event.get("schema_version") != "1.0.0"
            or event.get("source_key") != source_key
            or event.get("source_pdf_fingerprint") != parsed.gld_pdf.reference.fingerprint
            or not parsed.gld_pdf.content.startswith(b"%PDF-")
        ):
            _fail("LEGISLATION_GLD_EVIDENCE_INVALID")
        items.append(replace(parsed, event=event))
    if tuple(sorted(item.scope for item in items)) != tuple(sorted(_SCOPES)):
        _fail("LEGISLATION_SOURCE_BUNDLE_INCOMPLETE")
    return tuple(sorted(items, key=lambda item: _SCOPES.index(item.scope)))


def _xml_root(content: bytes, xsd: bytes, language: str, source_key: str) -> ET.Element:
    try:
        schema = ET.fromstring(xsd)  # noqa: S314 -- retained, non-expanding stdlib parser.
        root = ET.fromstring(content)  # noqa: S314 -- retained, non-expanding stdlib parser.
    except ET.ParseError as error:
        code = "LEGISLATION_HKEL_XML_INVALID"
        raise LegislationAcceptanceError(code) from error
    if (
        schema.tag != "{http://www.w3.org/2001/XMLSchema}schema"
        or not any(
            child.tag == "{http://www.w3.org/2001/XMLSchema}element"
            and child.get("name") == "legislation"
            for child in schema
        )
        or root.tag != "legislation"
        or root.attrib != {"language": language, "source-key": source_key}
    ):
        _fail("LEGISLATION_HKEL_XML_INVALID")
    return root


def _xml_text(element: ET.Element | None, code: str) -> str:
    if element is None or len(element) or element.text is None:
        _fail(code)
    value = element.text
    if not value or value.strip() != value:
        _fail(code)
    return value


def _tree(  # noqa: PLR0913, PLR0917
    content: bytes,
    xsd: bytes,
    language: str,
    source_key: str,
    legal_item_id: str,
    location_id: str,
    source_fingerprint: str,
) -> CanonicalLanguageTree:
    root = _xml_root(content, xsd, language, source_key)
    title = _xml_text(root.find("title"), "LEGISLATION_HKEL_XML_INVALID")
    citation = _xml_text(root.find("citation"), "LEGISLATION_HKEL_XML_INVALID")
    provisions = root.findall("provision")
    expected_root_children = 3
    if len(root) != expected_root_children or len(provisions) != 1:
        _fail("LEGISLATION_HKEL_XML_UNSUPPORTED")
    provision = provisions[0]
    if frozenset(provision.attrib) != frozenset({"id", "locator", "heading"}):
        _fail("LEGISLATION_HKEL_XML_INVALID")
    paragraphs = provision.findall("paragraph")
    if len(provision) != len(paragraphs) or not paragraphs:
        _fail("LEGISLATION_HKEL_XML_UNSUPPORTED")
    prefix = "en" if language == "en" else "zh"
    item_ref: dict[str, JsonValue] = {
        "ref_type": "LEGAL_ITEM",
        "ref_id": legal_item_id,
        "fingerprint": source_fingerprint,
    }
    instrument_ref: dict[str, JsonValue] = {
        "ref_type": "LEGAL_LOCATION",
        "ref_id": _id("loc", source_key, "instrument"),
        "fingerprint": source_fingerprint,
    }
    location_ref: dict[str, JsonValue] = {
        "ref_type": "LEGAL_LOCATION",
        "ref_id": location_id,
        "fingerprint": source_fingerprint,
    }
    root_id = f"{prefix}_instrument"
    provision_id = f"{prefix}_provision"
    units: list[dict[str, JsonValue]] = [
        _unit(f"{prefix}_title", root_id, instrument_ref, "INSTRUMENT_TITLE", title, 0),
        _unit(f"{prefix}_citation", root_id, instrument_ref, "INSTRUMENT_CITATION", citation, 1),
        _unit(
            f"{prefix}_locator",
            provision_id,
            location_ref,
            "LOCATION_LOCATOR",
            _text(provision.get("locator"), "LEGISLATION_HKEL_XML_INVALID"),
            0,
        ),
        _unit(
            f"{prefix}_heading",
            provision_id,
            location_ref,
            "LOCATION_HEADING",
            _text(provision.get("heading"), "LEGISLATION_HKEL_XML_INVALID"),
            1,
        ),
    ]
    paragraph_ids: list[str] = []
    nodes: list[dict[str, JsonValue]] = [
        _node(
            root_id,
            instrument_ref,
            "INSTRUMENT",
            None,
            0,
            (f"{prefix}_title", f"{prefix}_citation"),
            (provision_id,),
        ),
        _node(
            provision_id,
            location_ref,
            "PROVISION",
            root_id,
            0,
            (f"{prefix}_locator", f"{prefix}_heading"),
            (),
        ),
    ]
    for index, paragraph in enumerate(paragraphs, start=1):
        if paragraph.attrib != {"id": f"p{index}"}:
            _fail("LEGISLATION_HKEL_XML_INVALID")
        node_id = f"{prefix}_paragraph_{index}"
        unit_id = f"{prefix}_body_{index}"
        paragraph_ids.append(node_id)
        units.append(
            _unit(
                unit_id,
                node_id,
                location_ref,
                "BODY_TEXT",
                _xml_text(paragraph, "LEGISLATION_HKEL_XML_INVALID"),
                0,
            )
        )
        nodes.append(
            _node(node_id, location_ref, "PARAGRAPH", provision_id, index - 1, (unit_id,), ())
        )
    nodes[1]["child_node_ids"] = checked_json_value(paragraph_ids)
    draft = _object(
        checked_json_value(
            {
                "source_format": "HKEL_XML_V1",
                "language": language,
                "legal_item_ref": item_ref,
                "root_node_id": root_id,
                "nodes": nodes,
                "source_units": units,
            }
        ),
        "LEGISLATION_HKEL_XML_INVALID",
    )
    return seal_canonical_language_tree(draft)


def _unit(  # noqa: PLR0913, PLR0917
    unit_id: str, node_id: str, location: dict[str, JsonValue], kind: str, content: str, order: int
) -> dict[str, JsonValue]:
    return {
        "source_unit_id": unit_id,
        "tree_node_id": node_id,
        "legal_location_ref": location,
        "unit_kind": kind,
        "content": content,
        "asset_ref": None,
        "source_order": order,
    }


def _node(  # noqa: PLR0913, PLR0917
    node_id: str,
    location: dict[str, JsonValue],
    kind: str,
    parent: str | None,
    order: int,
    units: tuple[str, ...],
    children: tuple[str, ...],
) -> dict[str, JsonValue]:
    return {
        "tree_node_id": node_id,
        "legal_location_ref": location,
        "structural_type": kind,
        "parent_node_id": parent,
        "sibling_order": order,
        "owned_source_unit_ids": list(units),
        "child_node_ids": list(children),
    }


def _alignment(
    en: CanonicalLanguageTree, zh: CanonicalLanguageTree, evidence: _Retained
) -> BilingualAlignmentMap:
    groups: list[dict[str, JsonValue]] = []
    pairs = (
        ("title", "INSTRUMENT_TITLE"),
        ("citation", "INSTRUMENT_CITATION"),
        ("locator", "LOCATION_LOCATOR"),
        ("heading", "LOCATION_HEADING"),
    )
    mapping_ref: dict[str, JsonValue] = {
        "ref_type": "BILINGUAL_MAPPING_EVIDENCE",
        "ref_id": _id("evi", evidence.reference.logical_key),
        "fingerprint": evidence.reference.fingerprint,
    }
    for name, kind in pairs:
        en_unit = next(unit for unit in en.source_units if unit.unit_kind == kind)
        zh_unit = next(unit for unit in zh.source_units if unit.unit_kind == kind)
        groups.append(
            {
                "alignment_group_id": f"align_{name}",
                "legal_location_ref": en_unit.legal_location_ref,
                "en_source_unit_ids": [en_unit.source_unit_id],
                "zh_hant_source_unit_ids": [zh_unit.source_unit_id],
                "mapping_evidence_ref": mapping_ref,
            }
        )
    en_body = [unit for unit in en.source_units if unit.unit_kind == "BODY_TEXT"]
    zh_body = [unit for unit in zh.source_units if unit.unit_kind == "BODY_TEXT"]
    if len(en_body) != len(zh_body):
        _fail("LEGISLATION_BILINGUAL_ALIGNMENT_INVALID")
    for index, (en_unit, zh_unit) in enumerate(zip(en_body, zh_body, strict=True), start=1):
        groups.append(
            {
                "alignment_group_id": f"align_body_{index}",
                "legal_location_ref": en_unit.legal_location_ref,
                "en_source_unit_ids": [en_unit.source_unit_id],
                "zh_hant_source_unit_ids": [zh_unit.source_unit_id],
                "mapping_evidence_ref": mapping_ref,
            }
        )
    document = _object(
        checked_json_value(
            {
                "$schema": BILINGUAL_ALIGNMENT_MAP_SCHEMA,
                "contract_version": CANONICAL_TREE_CONTRACT_VERSION,
                "legal_item_ref": en.legal_item_ref,
                "groups": groups,
            }
        ),
        "LEGISLATION_BILINGUAL_ALIGNMENT_INVALID",
    )
    return parse_bilingual_alignment_map(document, en_tree=en, zh_hant_tree=zh)


def _partition(
    en: CanonicalLanguageTree,
    zh: CanonicalLanguageTree,
    alignment: BilingualAlignmentMap,
    location_id: str,
) -> tuple[BilingualPartitionResult, PartitionServingProfile]:
    provisional = PartitionServingProfile(
        _id("srp", "hk-v1-legislation-serving"),
        "sha256:" + "0" * 64,
        "UTF8_BYTE_COUNT_1.0.0",
        100_000,
        1_000_000,
        "Hong Kong",
        "Hong Kong",
        "Legislation",
        "HKeL",
        "None",
    )
    profile = replace(
        provisional, profile_fingerprint=partition_serving_profile_fingerprint(provisional)
    )
    body_groups = tuple(
        group.alignment_group_id
        for group in alignment.groups
        if group.alignment_group_id.startswith("align_body_")
    )
    request = BilingualPartitionRequest(
        {
            "ref_type": "LEGAL_LOCATION",
            "ref_id": location_id,
            "fingerprint": next(
                group.legal_location_ref["fingerprint"]
                for group in alignment.groups
                if group.alignment_group_id == "align_locator"
            ),
        },
        en.fingerprint,
        zh.fingerprint,
        alignment.fingerprint,
        ("partition_provision",),
        (
            AlignedPartitionNode(
                partition_node_id="partition_provision",
                en_tree_node_id="en_provision",
                zh_hant_tree_node_id="zh_provision",
                primary_alignment_group_ids=body_groups,
                dependency_alignment_group_ids=(),
                child_partition_node_ids=(),
                source_contract_state="SUPPORTED",
                indivisible=False,
            ),
        ),
    )
    return partition_canonical_bilingual_location(
        BilingualPartitionExecution(request, profile, _Utf8ByteCounter(profile), en, zh, alignment)
    ), profile


def _atomic_create_or_match(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            _fail("LEGISLATION_RETAINED_OUTPUT_DRIFT")
        return
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.is_symlink():
        _fail("LEGISLATION_RETAINED_OUTPUT_INVALID")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    if path.read_bytes() != content:
        _fail("LEGISLATION_RETAINED_OUTPUT_DRIFT")


def _allocation_document(allocation: HKLegislationRecordAllocation) -> dict[str, JsonValue]:
    return {
        "legislation_scope_code": allocation.legislation_scope_code,
        "candidate_key": allocation.candidate_key,
        "search_record_id": allocation.search_record_id,
        "continuity": allocation.continuity,
        "predecessor_record_id": None,
        "predecessor_payload_fingerprint": None,
        "predecessor_record_fact": None,
    }


def _replay_existing(
    path: Path,
    *,
    operation_id: str,
    command_fingerprint: str,
    manifest_fingerprint: str,
    state_path: Path,
) -> dict[str, JsonValue] | None:
    if not path.exists():
        return None
    if (
        not path.is_file()
        or path.is_symlink()
        or not state_path.is_file()
        or state_path.is_symlink()
    ):
        _fail("LEGISLATION_RETAINED_OUTPUT_DRIFT")
    content = path.read_bytes()
    document = _canonical_object(content, "LEGISLATION_RETAINED_OUTPUT_DRIFT")
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    if (
        document.get("schema_id") != "asklegal.hk-v1-legislation-release-input/v1"
        or document.get("schema_version") != "1.0.0"
        or document.get("operation_id") != operation_id
        or document.get("command_fingerprint") != command_fingerprint
        or document.get("legislation_manifest_fingerprint") != manifest_fingerprint
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
        or type(document.get("artifacts")) is not list
    ):
        _fail("LEGISLATION_RETAINED_OUTPUT_DRIFT")
    raw_artifacts = document["artifacts"]
    if type(raw_artifacts) is not list:
        _fail("LEGISLATION_RETAINED_OUTPUT_DRIFT")
    for raw in raw_artifacts:
        artifact = _object(raw, "LEGISLATION_RETAINED_OUTPUT_DRIFT")
        relative = _text(artifact.get("path"), "LEGISLATION_RETAINED_OUTPUT_DRIFT")
        target = path.parent.joinpath(*relative.split("/"))
        body = target.read_bytes()
        if (
            type(artifact.get("byte_length")) is not int
            or len(body) != artifact["byte_length"]
            or _fingerprint(body) != artifact.get("fingerprint")
        ):
            _fail("LEGISLATION_RETAINED_OUTPUT_DRIFT")
    return {
        "schema_id": "asklegal.hk-v1-legislation-acceptance-result/v1",
        "schema_version": "1.0.0",
        "operation_id": operation_id,
        "result": "COMPLETE",
        "component_path": str(path),
        "component_fingerprint": _fingerprint(content),
    }


def prepare_hk_v1_legislation_acceptance_component(  # noqa: PLR0913, PLR0915
    operation_id: str,
    manifest: bytes,
    verified_inputs: Mapping[str, JsonValue],
    primary_vault: _PrimaryVault,
    *,
    state_root: Path,
    output_root: Path,
) -> dict[str, JsonValue]:
    """Build and retain exact three-scope legislation acceptance input."""
    if type(operation_id) is not str or _OPERATION.fullmatch(operation_id) is None:
        _fail("LEGISLATION_OPERATION_INVALID")
    if (
        not state_root.is_absolute()
        or not output_root.is_absolute()
        or state_root.is_symlink()
        or output_root.is_symlink()
    ):
        _fail("LEGISLATION_CONFIGURATION_INVALID")
    acquisition = accept_hk_legislation_acquisition_manifest(manifest)
    if not acquisition.changed:
        _fail("LEGISLATION_ACQUISITION_NO_CHANGE")
    verified, command_fingerprint, cutoff = _verified_index(verified_inputs, operation_id)
    acquisition_cutoff_z = (
        acquisition.observation_cutoff
        if acquisition.observation_cutoff.endswith("Z")
        else acquisition.observation_cutoff.removesuffix("+00:00") + "Z"
    )
    cutoff_z = cutoff if cutoff.endswith("Z") else cutoff.removesuffix("+00:00") + "Z"
    if acquisition_cutoff_z != cutoff_z:
        _fail("LEGISLATION_ACQUISITION_CUTOFF_DRIFT")
    bundle = _source_bundle(verified, primary_vault, operation_id, acquisition.observation_cutoff)
    parsed_items = _parse_items(bundle, verified, primary_vault)
    state_path = state_root / "legislation-identities.json"
    output_path = output_root / operation_id / "legislation-release-input.json"
    replayed = _replay_existing(
        output_path,
        operation_id=operation_id,
        command_fingerprint=command_fingerprint,
        manifest_fingerprint=acquisition.acquisition_manifest_fingerprint,
        state_path=state_path,
    )
    if replayed is not None:
        return replayed
    register = LocalLegalIdentityRegister(state_path)

    def issue(kind: LegalIdentityKind, key: str) -> str:
        return register.issue_identity(LegalIdentityRequest(kind, key)).identity_id

    scope_documents: list[JsonValue] = []
    artifacts: list[JsonValue] = []
    candidate_outputs: list[tuple[Path, bytes]] = []
    built_release_ids: list[tuple[str, str]] = []
    for item in parsed_items:
        legal_item_id = issue(LegalIdentityKind.LEGAL_ITEM, item.source_key)
        official_version_id = issue(
            LegalIdentityKind.OFFICIAL_VERSION,
            f"{item.source_key}:{item.en_xml.reference.fingerprint}:{item.zh_xml.reference.fingerprint}",
        )
        legal_location_id = issue(LegalIdentityKind.LEGAL_LOCATION, f"{item.source_key}:s1")
        combined_source_fingerprint = _fingerprint(
            item.en_xml.content + b"\0" + item.zh_xml.content
        )
        en_tree = _tree(
            item.en_xml.content,
            item.xsd.content,
            "en",
            item.source_key,
            legal_item_id,
            legal_location_id,
            combined_source_fingerprint,
        )
        zh_tree = _tree(
            item.zh_xml.content,
            item.xsd.content,
            "zh-Hant",
            item.source_key,
            legal_item_id,
            legal_location_id,
            combined_source_fingerprint,
        )
        alignment = _alignment(en_tree, zh_tree, item.gld_event)
        partition, partition_profile = _partition(en_tree, zh_tree, alignment, legal_location_id)
        evidence_ref = HKLegislationTraceabilityReference(
            "EVIDENCE",
            issue(LegalIdentityKind.EVIDENCE, item.gld_event.reference.logical_key),
            item.gld_event.reference.fingerprint,
        )
        events = (
            HKLegislationEvent(
                issue(LegalIdentityKind.LEGAL_STATUS_EVENT, f"{item.source_key}:publication"),
                f"{item.source_key}:publication",
                legal_location_id,
                official_version_id,
                HKLegislationEventKind.PUBLICATION,
                HKLegislationEventSource.GAZETTE,
                _text(item.event["publication_at"], "LEGISLATION_GLD_EVIDENCE_INVALID"),
                item.gld_event.reference.fingerprint,
                (),
                None,
            ),
            HKLegislationEvent(
                issue(LegalIdentityKind.LEGAL_STATUS_EVENT, f"{item.source_key}:commencement"),
                f"{item.source_key}:commencement",
                legal_location_id,
                official_version_id,
                HKLegislationEventKind.COMMENCEMENT,
                HKLegislationEventSource.GAZETTE,
                _text(item.event["commencement_at"], "LEGISLATION_GLD_EVIDENCE_INVALID"),
                item.gld_event.reference.fingerprint,
                (),
                None,
            ),
        )
        decision = decide_hk_legislation_state(
            HKLegislationEventTimeline(
                schema_id="asklegal.hk-legislation-event-timeline",
                schema_version="1.0.0",
                legal_location_id=legal_location_id,
                official_version_id=official_version_id,
                source_facts_complete=True,
                known_stale=False,
                source_contract_review=HKLegislationSourceContractReview.NOT_REQUIRED,
                events=events,
            ),
            cutoff_z,
        )
        decision_ref = HKLegislationTraceabilityReference(
            "DECISION",
            issue(LegalIdentityKind.DECISION, decision.decision_fingerprint),
            decision.decision_fingerprint,
        )
        candidate_input = HKLegislationCandidateInput(
            item.inventory_item_id,
            item.scope,
            legal_item_id,
            (official_version_id,),
            (legal_location_id,),
            decision,
            partition,
            HKLegislationServingPayload("Hong Kong", "Hong Kong", "Legislation", "HKeL", "None"),
            issue(LegalIdentityKind.ARTIFACT, combined_source_fingerprint),
            (evidence_ref,),
            HKLegislationAuthorityNoteSeed(_fingerprint(b"None"), decision_ref, ()),
        )
        candidate_input = replace(
            candidate_input,
            decision_authority=bind_hk_legislation_inventory_decision_authority(candidate_input),
        )
        candidate_set = build_hk_legislation_candidate_set(
            legislation_scope_code=item.scope,
            observation_cutoff=cutoff_z,
            inputs=(candidate_input,),
        )
        candidate_bytes = canonical_hk_legislation_candidate_set(candidate_set)
        issued_records = tuple(
            register.issue_search_record(
                SearchRecordIdentityRequest(
                    item.scope,
                    f"{item.inventory_item_id}:{draft.part_number}",
                    draft.serving_payload_fingerprint,
                )
            )
            for draft in candidate_set.drafts
        )
        if any(issued.continuity != "INITIAL" for issued in issued_records):
            _fail("LEGISLATION_PRIOR_RELEASE_NOT_READY")
        allocations = tuple(
            HKLegislationRecordAllocation(
                item.scope,
                draft.candidate_key,
                issued.search_record_id,
                "INITIAL",
                None,
                None,
                None,
            )
            for draft, issued in zip(candidate_set.drafts, issued_records, strict=True)
        )
        identity_set = HKLegislationAllocatedIdentitySet(item.scope, allocations, None, None)
        serving_profile = ServingRecordProfile(
            partition_profile.profile_id, "1.0.0", partition_profile.profile_fingerprint
        )
        release_evidence = (evidence_ref.ref_id,)
        release_validation = (
            issue(
                LegalIdentityKind.VALIDATION,
                f"{operation_id}:{item.scope}:{candidate_set.issuance_fingerprint}",
            ),
        )
        built = build_hk_legislation_scope_release(
            HKLegislationScopeReleaseRequest(
                candidate_set=candidate_set,
                allocated_identities=identity_set,
                serving_profile=serving_profile,
                release_evidence_refs=release_evidence,
                release_validation_refs=release_validation,
                prior_release=None,
                prior_traceability_entries=None,
                prior_inventory_outcomes=None,
                unchanged=False,
            )
        )
        built_release_ids.append((item.scope, built.release.release_id))
        relative = f"legislation/{item.scope}/candidate-set.json"
        candidate_outputs.append((output_root / operation_id / relative, candidate_bytes))
        artifacts.append(
            {
                "path": relative,
                "fingerprint": _fingerprint(candidate_bytes),
                "byte_length": len(candidate_bytes),
            }
        )
        scope_documents.append(
            {
                "scope_id": item.scope,
                "candidate_set_path": relative,
                "candidate_set_fingerprint": _fingerprint(candidate_bytes),
                "allocated_identities": {
                    "corpus_scope_id": item.scope,
                    "allocations": [_allocation_document(allocation) for allocation in allocations],
                    "lookup_revision_id": None,
                    "lookup_shard_id": None,
                },
                "serving_profile": {
                    "serving_record_profile_id": serving_profile.serving_record_profile_id,
                    "schema_version": serving_profile.schema_version,
                    "schema_fingerprint": serving_profile.schema_fingerprint,
                },
                "release_evidence_refs": list(release_evidence),
                "release_validation_refs": list(release_validation),
                "prior_release": None,
                "prior_traceability_entries": None,
                "prior_inventory_outcomes": None,
                "unchanged": False,
            }
        )
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1-legislation-release-input/v1",
        "schema_version": "1.0.0",
        "operation_id": operation_id,
        "command_fingerprint": command_fingerprint,
        "observation_cutoff": cutoff_z,
        "legislation_scopes": scope_documents,
        "legislation_target_key": "hk-v1-local",
        "legislation_lookup_input": {
            "lookup_revision_id": issue(LegalIdentityKind.TRACEABILITY_LOOKUP, operation_id),
            "manifest_schema_fingerprint": _fingerprint(
                b"asklegal.record-traceability-manifest/v1"
            ),
            "entry_schema_fingerprint": _fingerprint(b"asklegal.record-traceability-entry/v1"),
        },
        "legislation_lookup_shards": [
            {
                "release_scope_id": scope,
                "corpus_release_id": release_id,
                "lookup_shard_id": issue(
                    LegalIdentityKind.TRACEABILITY_SHARD,
                    f"{operation_id}:{scope}:{release_id}",
                ),
            }
            for scope, release_id in built_release_ids
        ],
        "legislation_manifest_fingerprint": acquisition.acquisition_manifest_fingerprint,
        "artifacts": artifacts,
    }
    output = canonicalize(
        checked_json_value(
            {**body, "fingerprint": _fingerprint(canonicalize(checked_json_value(body)))}
        )
    )
    register.commit()
    for path, content in candidate_outputs:
        _atomic_create_or_match(path, content)
    _atomic_create_or_match(output_path, output)
    return {
        "schema_id": "asklegal.hk-v1-legislation-acceptance-result/v1",
        "schema_version": "1.0.0",
        "operation_id": operation_id,
        "result": "COMPLETE",
        "component_path": str(output_path),
        "component_fingerprint": _fingerprint(output),
    }
