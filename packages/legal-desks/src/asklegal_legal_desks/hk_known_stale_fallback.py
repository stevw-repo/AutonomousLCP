"""Deterministic ADR 0079/0081 known-stale fallback selection.

This module selects only an exact, previously accepted official HKeL version
for warned analytical carry-forward.  It never changes source text, constructs
a Search Record, resolves a Coverage Gap, or performs an external effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal, Never

from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.errors import ContractViolation
from asklegal_contracts.json_types import checked_json_value

from .model import RulebookError, RulebookErrorCode

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

HK_KNOWN_STALE_FALLBACK_RULE_ID = "HKLEG-KNOWN-STALE-FALLBACK-001"
KNOWN_STALE_FALLBACK_SCHEMA = (
    "https://contracts.asklegal.local/v1/hk-legislation-known-stale-fallback.schema.json"
)
KNOWN_STALE_FALLBACK_CONTRACT_VERSION = "1.0.0"
_SCHEMA = "schemas/known-stale-fallback.schema.json"
_SCOPE_ID = "rsc_fa928755a873dbf8df5f4f2d333b672cd1d935af9bf99b95"
_CATALOGUE = "catalogues/known-stale-fallback-fixtures.json"
_REASONS = "catalogues/known-stale-fallback-reason-codes.json"
_RULE = "rules/HKLEG-KNOWN-STALE-FALLBACK-001.json"


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
    return tuple(item for item in value if isinstance(item, str))


def _text(value: JsonValue | None, detail: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(detail)
    return value


def _fingerprint(value: JsonValue) -> str:
    return f"sha256:{sha256(canonicalize(value)).hexdigest()}"


def _byte_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _read(path: Path) -> dict[str, JsonValue]:
    raw = path.read_bytes()
    try:
        value = parse_json_bytes(raw, max_bytes=max(len(raw), 1))
    except ContractViolation as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, path.name) from error
    return _object(value, path.name)


def _safe_member(root: Path, relative: str) -> Path:
    member = PurePosixPath(relative)
    if member.is_absolute() or ".." in member.parts:
        _fail("unsafe package member")
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


@dataclass(frozen=True, slots=True)
class KnownStaleFallbackDecision:
    """One exact carry-forward selection or fail-closed result."""

    fixture_id: str
    processing_outcome: Literal["PASS", "BLOCK", "QUARANTINE"]
    reason_code: str
    selection_result: Literal["KNOWN_STALE_ANALYTICAL_CARRY_FORWARD", "NO_RECORD"]
    coverage_gap_ref: dict[str, JsonValue]
    affected_location_ids: tuple[str, ...]
    warning_scope: Literal["EXACT", "BOUNDED_PARENT", "NONE"]
    fallback_selection: dict[str, JsonValue] | None
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict source-neutral decision document."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_KNOWN_STALE_FALLBACK_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": "COVERAGE_GAP",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_KNOWN_STALE_FALLBACK_RULE_ID],
            "selection_result": self.selection_result,
            "coverage_gap_ref": self.coverage_gap_ref,
            "affected_scope_ids": [_SCOPE_ID],
            "affected_location_ids": list(self.affected_location_ids),
            "warning_scope": self.warning_scope,
            "fallback_selection": self.fallback_selection,
            "official_version_output": "NONE",
            "record_output": "NONE",
            "external_effects": "NONE",
            "next_action": self.next_action,
        }

    def selection_ref(self) -> dict[str, JsonValue] | None:
        """Return a Report-compatible immutable selection reference."""
        if self.fallback_selection is None:
            return None
        return {
            "ref_type": "KNOWN_STALE_FALLBACK_SELECTION",
            "ref_id": _text(self.fallback_selection.get("selection_id"), "selection ID"),
            "fingerprint": _text(
                self.fallback_selection.get("fingerprint"), "selection fingerprint"
            ),
        }


def _candidate_version(candidate: dict[str, JsonValue]) -> str:
    return _text(candidate.get("version_date"), "candidate version date")


def _candidate_eligible(candidate: dict[str, JsonValue]) -> bool:
    required = (
        "accepted",
        "independently_verifiable",
        "integrity_valid",
        "bilingual_complete",
        "xml_copy_reconciled",
        "source_text_unchanged",
    )
    return candidate.get("applicable") is True and all(
        candidate.get(name) is True for name in required
    )


def _latest_applicable(
    candidates: tuple[dict[str, JsonValue], ...],
) -> tuple[dict[str, JsonValue] | None, str | None]:
    applicable = tuple(candidate for candidate in candidates if candidate.get("applicable") is True)
    if not applicable:
        return None, None
    latest_date = max(_candidate_version(candidate) for candidate in applicable)
    latest = tuple(
        candidate for candidate in applicable if _candidate_version(candidate) == latest_date
    )
    official_ids = {
        _text(
            _object(candidate.get("official_version_ref"), "official version ref").get("ref_id"),
            "official version ID",
        )
        for candidate in latest
    }
    if len(official_ids) != 1:
        return None, "HKLEG_KNOWN_STALE_LATEST_VERSION_CONFLICT"
    eligible = tuple(candidate for candidate in latest if _candidate_eligible(candidate))
    if not eligible:
        return None, "HKLEG_KNOWN_STALE_LATEST_APPLICABLE_TEXT_INVALID"
    verified = tuple(
        candidate for candidate in eligible if candidate.get("evidence_class") == "VERIFIED"
    )
    return (verified or eligible)[0], None


def _selection(
    input_document: dict[str, JsonValue], candidate: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    text_fingerprints = _object(candidate.get("source_text_fingerprints"), "source text")
    document: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-legislation-known-stale-fallback-selection",
        "schema_version": KNOWN_STALE_FALLBACK_CONTRACT_VERSION,
        "selection_id": _text(input_document.get("selection_id"), "selection ID"),
        "serving_mode": "KNOWN_STALE_ANALYTICAL_CARRY_FORWARD",
        "object_id": _text(input_document.get("object_id"), "object ID"),
        "scope_id": _SCOPE_ID,
        "cutoff": _text(input_document.get("cutoff"), "cutoff"),
        "coverage_gap_ref": _object(input_document.get("coverage_gap_ref"), "Coverage Gap"),
        "selected_official_version_ref": _object(
            candidate.get("official_version_ref"), "official version ref"
        ),
        "base_version_date": _candidate_version(candidate),
        "base_evidence_class": _text(candidate.get("evidence_class"), "evidence class"),
        "source_text_fingerprints": text_fingerprints,
        "affected_location_ids": list(
            _strings(input_document.get("affected_location_ids"), "affected locations")
        ),
        "warning_scope": _text(input_document.get("affected_location_scope"), "warning scope"),
        "authority_note_template_id": "HKLEG-KNOWN-STALE-WARNING-1.0.0",
        "source_text_action": "REUSE_BYTE_EXACT_SOURCE_TEXT",
        "reconstruction_disposition": _text(
            input_document.get("reconstruction_disposition"), "reconstruction disposition"
        ),
    }
    document["fingerprint"] = _fingerprint(checked_json_value(document))
    return document


def _warning_scope(value: JsonValue | None) -> Literal["EXACT", "BOUNDED_PARENT", "NONE"]:
    if value == "EXACT":
        return "EXACT"
    if value == "BOUNDED_PARENT":
        return "BOUNDED_PARENT"
    return "NONE"


def evaluate_known_stale_fallback(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> KnownStaleFallbackDecision:
    """Select the newest exact eligible HKeL base, or fail closed."""
    coverage_gap = _object(input_document.get("coverage_gap_ref"), "Coverage Gap")
    locations = tuple(
        sorted(
            _strings(input_document.get("affected_location_ids"), "affected locations"),
            key=str.encode,
        )
    )

    def decision(
        outcome: Literal["PASS", "BLOCK", "QUARANTINE"],
        reason: str,
        next_action: str,
        *,
        selection: dict[str, JsonValue] | None = None,
    ) -> KnownStaleFallbackDecision:
        warning_scope = (
            _warning_scope(input_document.get("affected_location_scope"))
            if selection is not None
            else "NONE"
        )
        return KnownStaleFallbackDecision(
            fixture_id,
            outcome,
            reason,
            "KNOWN_STALE_ANALYTICAL_CARRY_FORWARD" if selection is not None else "NO_RECORD",
            coverage_gap,
            locations,
            warning_scope,
            selection,
            next_action,
        )

    event_incomplete = (
        input_document.get("event_evidence_complete") is not True
        or input_document.get("event_evidence_authentic") is not True
        or input_document.get("event_operative_at_cutoff") is not True
    )
    checks: tuple[tuple[bool, Literal["BLOCK", "QUARANTINE"], str, str], ...] = (
        (
            input_document.get("matching_current_consolidation_available") is True,
            "BLOCK",
            "HKLEG_KNOWN_STALE_CURRENT_CONSOLIDATION_AVAILABLE",
            "USE_ORDINARY_CURRENT_HKEL_PATH",
        ),
        (
            input_document.get("reconstruction_disposition") == "ELIGIBLE",
            "BLOCK",
            "HKLEG_KNOWN_STALE_RECONSTRUCTION_ELIGIBLE",
            "SELECT_RECONSTRUCTED_CONSOLIDATION",
        ),
        (
            event_incomplete,
            "BLOCK",
            "HKLEG_KNOWN_STALE_EVENT_EVIDENCE_INCOMPLETE",
            "COMPLETE_OPERATIVE_EVENT_EVIDENCE",
        ),
        (
            input_document.get("event_evidence_conflicts") is True,
            "QUARANTINE",
            "HKLEG_KNOWN_STALE_EVENT_EVIDENCE_CONFLICT",
            "QUARANTINE_EVENT_EVIDENCE",
        ),
        (
            input_document.get("affected_location_scope") == "UNBOUNDED",
            "QUARANTINE",
            "HKLEG_KNOWN_STALE_AFFECTED_SET_UNBOUNDED",
            "PROVE_SMALLEST_COMPLETE_PARENT_SET",
        ),
        (
            input_document.get("identity_mapping_proved") is not True,
            "QUARANTINE",
            "HKLEG_KNOWN_STALE_IDENTITY_MAPPING_UNPROVED",
            "RESOLVE_IDENTITY_AND_PREDECESSOR_MAPPING",
        ),
        (
            input_document.get("release_accounting_complete") is not True,
            "BLOCK",
            "HKLEG_KNOWN_STALE_RELEASE_ACCOUNTING_INCOMPLETE",
            "COMPLETE_AFFECTED_AND_UNAFFECTED_ACCOUNTING",
        ),
    )
    failed = next((check for check in checks if check[0]), None)
    if failed is not None:
        return decision(failed[1], failed[2], failed[3])

    candidate, error_reason = _latest_applicable(
        _objects(input_document.get("candidate_versions"), "candidate versions")
    )
    if error_reason is not None:
        outcome: Literal["PASS", "BLOCK", "QUARANTINE"] = "QUARANTINE"
        reason = error_reason
        next_action = "QUARANTINE_PRIOR_HKEL_TEXT"
        selection = None
    elif candidate is None:
        outcome = "PASS"
        reason = "HKLEG_KNOWN_STALE_NO_VALID_APPLICABLE_TEXT"
        next_action = "ACCOUNT_NO_RECORD_COVERAGE_GAP"
        selection = None
    else:
        outcome = "PASS"
        evidence_class = _text(candidate.get("evidence_class"), "evidence class")
        reason = (
            "HKLEG_KNOWN_STALE_VERIFIED_TEXT_SELECTED"
            if evidence_class == "VERIFIED"
            else "HKLEG_KNOWN_STALE_NEWER_ASSISTED_TEXT_SELECTED"
        )
        next_action = "BUILD_WARNED_ANALYTICAL_RECORD_CANDIDATE"
        selection = _selection(input_document, candidate)
    return decision(outcome, reason, next_action, selection=selection)


def prove_hk_known_stale_fallback(
    package_root: Path,
) -> tuple[KnownStaleFallbackDecision, ...]:
    """Run every frozen ADR 0079/0081 fallback fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    for relative, fragment, detail in (
        (_REASONS, "reason_code_catalogue", "fallback reason catalogue"),
        (_RULE, "rule", "fallback rule"),
        (_CATALOGUE, "fixture_catalogue", "fallback fixture catalogue"),
    ):
        _validate(registry, _read(package_root / relative), fragment, detail)
    catalogue = _read(package_root / _CATALOGUE)
    decisions: list[KnownStaleFallbackDecision] = []
    seen: set[str] = set()
    for entry in _objects(catalogue.get("fixtures"), "fixtures"):
        fixture_id = _text(entry.get("fixture_id"), "fixture ID")
        if fixture_id in seen:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate fixture")
        seen.add(fixture_id)
        fixture_path = _safe_member(package_root, _text(entry.get("path"), "fixture path"))
        expected_path = _safe_member(
            package_root, _text(entry.get("expected_path"), "expected path")
        )
        if _byte_fingerprint(fixture_path.read_bytes()) != entry.get(
            "fixture_fingerprint"
        ) or _byte_fingerprint(expected_path.read_bytes()) != entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
        fixture = _read(fixture_path)
        expected = _read(expected_path)
        _validate(registry, fixture, "fixture", fixture_id)
        _validate(registry, expected, "decision", f"expected {fixture_id}")
        if fixture.get("fixture_id") != fixture_id:
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
        declaration = _object(fixture.get("expected_artifact"), "expected declaration")
        if declaration.get("path") != entry.get("expected_path") or declaration.get(
            "fingerprint"
        ) != entry.get("expected_fingerprint"):
            raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "expected artifact")
        input_document = _object(fixture.get("input"), "fixture input")
        _validate(registry, input_document, "input", f"input {fixture_id}")
        if _fingerprint(checked_json_value(input_document)) != fixture.get("input_fingerprint"):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "fixture input")
        result = evaluate_known_stale_fallback(fixture_id, input_document)
        if canonicalize(checked_json_value(result.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(result)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "fallback fixtures")
    return tuple(decisions)
