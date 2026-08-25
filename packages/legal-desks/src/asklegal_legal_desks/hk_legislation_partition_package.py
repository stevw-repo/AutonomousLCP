"""Frozen synthetic package proof for ADR 0021/0040 partitioning.

The fixtures begin with sealed source-neutral canonical trees.  They do not
claim authentic HKeL XML/XSD, PDF, tokenizer, or source admission.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Never

from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.errors import ContractViolation

from .hk_canonical_legislation import (
    parse_bilingual_alignment_map,
    parse_canonical_language_tree,
)
from .hk_legislation_partition import (
    BilingualPartitionBatchExecution,
    BilingualPartitionBatchResult,
    BilingualPartitionExecution,
    BilingualPartitionResult,
    ExactTokenCounter,
    PartitionServingProfile,
    bilingual_partition_request_from_document,
    partition_canonical_bilingual_location,
    partition_canonical_bilingual_locations,
    partition_serving_profile_from_document,
)
from .hk_partition_release_consequence import (
    PartitionReleaseConsequenceResult,
    decide_partition_failure_release,
    partition_release_request_from_document,
)
from .model import RulebookError, RulebookErrorCode

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

HK_LEGISLATION_PARTITION_RULE_ID = "HKLEG-RECON-ORP-001"
HK_LEGISLATION_PARTITION_SCHEMA = (
    "https://contracts.asklegal.local/v1/hk-legislation-partition.schema.json"
)
HK_LEGISLATION_PARTITION_CONTRACT_VERSION = "1.0.0"
_SCHEMA = "schemas/hk-legislation-partition.schema.json"
_CATALOGUE = "catalogues/reconstruction-overlong-partition-fixtures.json"
_REASONS = "catalogues/reconstruction-overlong-partition-reason-codes.json"
_RULE = "rules/HKLEG-RECON-ORP-001.json"
_TOKENIZER = "TEST_UTF8_BYTES_1.0.0"

type PartitionFixtureResult = (
    BilingualPartitionResult | BilingualPartitionBatchResult | PartitionReleaseConsequenceResult
)


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


def _text(value: JsonValue | None, detail: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(detail)
    return value


def _read(path: Path) -> dict[str, JsonValue]:
    raw = path.read_bytes()
    try:
        parsed = parse_json_bytes(raw, max_bytes=max(1, len(raw)))
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, path.name) from error
    return _object(parsed, path.name)


def _byte_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _safe_member(root: Path, relative: str) -> Path:
    member = PurePosixPath(relative)
    if member.is_absolute() or ".." in member.parts:
        _fail("unsafe partition package member")
    path = root.joinpath(*member.parts)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, relative) from error
    return path


def _validate(
    registry: SchemaRegistry,
    value: JsonValue,
    fragment: str,
    detail: str,
) -> None:
    try:
        registry.validate(value, f"{_SCHEMA}#/$defs/{fragment}")
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail) from error


class _Utf8ByteTokenCounter(ExactTokenCounter):
    """Exact synthetic tokenizer locked by the frozen fixture profile."""

    def __init__(self, profile: PartitionServingProfile) -> None:
        if profile.tokenizer_id != _TOKENIZER:
            _fail("partition fixture tokenizer")
        self.profile_id = profile.profile_id
        self.profile_fingerprint = profile.profile_fingerprint
        self.tokenizer_id = profile.tokenizer_id

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))


def _partition_execution(
    input_document: dict[str, JsonValue],
) -> BilingualPartitionExecution:
    en_tree = parse_canonical_language_tree(
        _object(input_document.get("en_tree"), "partition English tree")
    )
    zh_tree = parse_canonical_language_tree(
        _object(input_document.get("zh_hant_tree"), "partition Chinese tree")
    )
    alignment = parse_bilingual_alignment_map(
        _object(input_document.get("alignment_map"), "partition alignment"),
        en_tree=en_tree,
        zh_hant_tree=zh_tree,
    )
    request = bilingual_partition_request_from_document(
        _object(input_document.get("partition_request"), "partition request")
    )
    profile = partition_serving_profile_from_document(
        _object(input_document.get("serving_profile"), "partition serving profile")
    )
    return BilingualPartitionExecution(
        request,
        profile,
        _Utf8ByteTokenCounter(profile),
        en_tree,
        zh_tree,
        alignment,
    )


def evaluate_hk_legislation_partition(
    input_document: dict[str, JsonValue],
) -> BilingualPartitionResult:
    """Evaluate one exact source-neutral partition fixture without effects."""
    return partition_canonical_bilingual_location(_partition_execution(input_document))


def _evaluate_single_fixture_input(
    input_document: dict[str, JsonValue],
) -> BilingualPartitionResult | PartitionReleaseConsequenceResult:
    partition_result = evaluate_hk_legislation_partition(input_document)
    consequence_value = input_document.get("release_consequence")
    if consequence_value is None:
        return partition_result
    consequence = _object(consequence_value, "partition release consequence")
    return decide_partition_failure_release(
        partition_release_request_from_document(consequence, partition_result)
    )


def evaluate_hk_legislation_partition_batch(
    batch_document: dict[str, JsonValue],
) -> BilingualPartitionBatchResult:
    """Evaluate distinct Legal Locations without permitting combined parts."""
    locations = _objects(batch_document.get("locations"), "partition batch locations")
    return partition_canonical_bilingual_locations(
        BilingualPartitionBatchExecution(tuple(_partition_execution(item) for item in locations))
    )


def _validate_partition_inputs(
    registry: SchemaRegistry,
    input_documents: tuple[dict[str, JsonValue], ...],
) -> None:
    for input_document in input_documents:
        registry.validate(input_document["en_tree"], "schemas/canonical-language-tree.schema.json")
        registry.validate(
            input_document["zh_hant_tree"], "schemas/canonical-language-tree.schema.json"
        )
        registry.validate(
            input_document["alignment_map"], "schemas/bilingual-alignment-map.schema.json"
        )


def _evaluate_fixture_input(
    registry: SchemaRegistry,
    fixture: dict[str, JsonValue],
    fixture_id: str,
) -> PartitionFixtureResult:
    batch_value = fixture.get("batch_input")
    batch_document: dict[str, JsonValue] | None = None
    if batch_value is None:
        input_document = _object(fixture.get("input"), "partition input")
        _validate(registry, input_document, "input", f"input {fixture_id}")
        input_documents = (input_document,)
        fingerprinted_input = input_document
    else:
        batch_document = _object(batch_value, "partition batch input")
        _validate(registry, batch_document, "batch_input", f"input {fixture_id}")
        input_documents = _objects(batch_document.get("locations"), "partition batch locations")
        fingerprinted_input = batch_document
    _validate_partition_inputs(registry, input_documents)
    if _byte_fingerprint(canonicalize(fingerprinted_input)) != fixture.get("input_fingerprint"):
        raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, f"input {fixture_id}")
    if batch_document is None:
        first = _evaluate_single_fixture_input(input_documents[0])
        second = _evaluate_single_fixture_input(input_documents[0])
    else:
        first = evaluate_hk_legislation_partition_batch(batch_document)
        second = evaluate_hk_legislation_partition_batch(batch_document)
    if first.canonical_bytes != second.canonical_bytes or first.fingerprint != second.fingerprint:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"repeat {fixture_id}")
    return first


def _prove_partition_fixture(
    package_root: Path,
    registry: SchemaRegistry,
    entry: dict[str, JsonValue],
    seen: set[str],
) -> PartitionFixtureResult:
    fixture_id = _text(entry.get("fixture_id"), "partition fixture ID")
    if fixture_id in seen:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
    seen.add(fixture_id)
    fixture_path = _safe_member(package_root, _text(entry.get("path"), "fixture path"))
    expected_path = _safe_member(
        package_root,
        _text(entry.get("expected_path"), "expected path"),
    )
    if _byte_fingerprint(fixture_path.read_bytes()) != entry.get(
        "fixture_fingerprint"
    ) or _byte_fingerprint(expected_path.read_bytes()) != entry.get("expected_fingerprint"):
        raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
    fixture = _read(fixture_path)
    expected = _read(expected_path)
    _validate(registry, fixture, "fixture", fixture_id)
    first = _evaluate_fixture_input(registry, fixture, fixture_id)
    if isinstance(first, BilingualPartitionBatchResult):
        expected_fragment = "batch_result"
    elif isinstance(first, PartitionReleaseConsequenceResult):
        expected_fragment = "consequence_result"
    else:
        expected_fragment = "result"
    _validate(registry, expected, expected_fragment, f"expected {fixture_id}")
    if fixture.get("fixture_id") != fixture_id:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
    declaration = _object(fixture.get("expected_artifact"), "expected declaration")
    if declaration.get("path") != entry.get("expected_path") or declaration.get(
        "fingerprint"
    ) != entry.get("expected_fingerprint"):
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
    if first.canonical_bytes != canonicalize(expected):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
    return first


def prove_hk_legislation_partition(
    package_root: Path,
) -> tuple[PartitionFixtureResult, ...]:
    """Run and byte-check every frozen source-neutral partition fixture twice."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    for relative, fragment, detail in (
        (_REASONS, "reason_code_catalogue", "partition reason catalogue"),
        (_RULE, "rule", "partition rule"),
        (_CATALOGUE, "fixture_catalogue", "partition fixture catalogue"),
    ):
        _validate(registry, _read(package_root / relative), fragment, detail)
    catalogue = _read(package_root / _CATALOGUE)
    seen: set[str] = set()
    results = [
        _prove_partition_fixture(package_root, registry, entry, seen)
        for entry in _objects(catalogue.get("fixtures"), "partition fixtures")
    ]
    if not results:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "partition fixtures")
    return tuple(results)
