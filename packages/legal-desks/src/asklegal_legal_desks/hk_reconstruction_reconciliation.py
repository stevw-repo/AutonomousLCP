"""Deterministic ADR 0086 later-HKeL reconciliation decisions.

The gate records source-neutral monitoring and comparison consequences.  It
does not acquire HKeL, mutate a reconstruction artifact, build a Search Record,
approve a release, or perform an external effect.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal, Never

from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.errors import ContractViolation
from asklegal_contracts.json_types import checked_json_value

from .model import RulebookError, RulebookErrorCode

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

HK_RECONSTRUCTION_RECONCILIATION_RULE_ID = "HKLEG-RECON-RECONCILE-001"
RECONSTRUCTION_RECONCILIATION_SCHEMA = (
    "https://contracts.asklegal.local/v1/hk-legislation-reconstruction-reconciliation.schema.json"
)
RECONSTRUCTION_RECONCILIATION_CONTRACT_VERSION = "1.0.0"
_SCHEMA = "schemas/reconstruction-reconciliation.schema.json"
_CATALOGUE = "catalogues/reconstruction-reconciliation-fixtures.json"
_REASONS = "catalogues/reconstruction-reconciliation-reason-codes.json"
_RULE = "rules/HKLEG-RECON-RECONCILE-001.json"

type Outcome = Literal["PASS", "BLOCK", "QUARANTINE"]
type MonitoringState = Literal[
    "AWAITING_HKEL_CONSOLIDATION",
    "HKEL_CANDIDATE_OBSERVED",
    "COMPARISON_DEFERRED",
    "MATCH_CONFIRMED",
    "MISMATCH_CONFIRMED",
    "SUPERSEDED_BY_HKEL",
    "SUSPENDED_PENDING_REVALIDATION",
    "REVALIDATED",
]
_MONITORING_STATES: dict[str, MonitoringState] = {
    "AWAITING_HKEL_CONSOLIDATION": "AWAITING_HKEL_CONSOLIDATION",
    "HKEL_CANDIDATE_OBSERVED": "HKEL_CANDIDATE_OBSERVED",
    "COMPARISON_DEFERRED": "COMPARISON_DEFERRED",
    "MATCH_CONFIRMED": "MATCH_CONFIRMED",
    "MISMATCH_CONFIRMED": "MISMATCH_CONFIRMED",
    "SUPERSEDED_BY_HKEL": "SUPERSEDED_BY_HKEL",
    "SUSPENDED_PENDING_REVALIDATION": "SUSPENDED_PENDING_REVALIDATION",
    "REVALIDATED": "REVALIDATED",
}


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
class ReconstructionReconciliationDecision:
    """One append-only monitoring transition consequence."""

    fixture_id: str
    processing_outcome: Outcome
    reason_code: str
    prior_state: MonitoringState
    next_state: MonitoringState
    comparison_class: str
    accounted_location_ids: tuple[str, ...]
    mismatch_attribution_classes: tuple[str, ...]
    suspension_scope: str
    serving_consequence: str
    coverage_gap_consequence: str
    next_action: str

    def document(self) -> dict[str, JsonValue]:
        """Return the strict effect-free reconciliation decision."""
        return {
            "fixture_id": self.fixture_id,
            "rule_id": HK_RECONSTRUCTION_RECONCILIATION_RULE_ID,
            "processing_outcome": self.processing_outcome,
            "legal_disposition": "NOT_APPLICABLE",
            "coverage_effect": "COVERAGE_GAP",
            "source_contract_review_required": False,
            "reason_codes": [self.reason_code],
            "rule_trace": [HK_RECONSTRUCTION_RECONCILIATION_RULE_ID],
            "prior_monitoring_state": self.prior_state,
            "next_monitoring_state": self.next_state,
            "comparison_class": self.comparison_class,
            "accounted_location_ids": list(self.accounted_location_ids),
            "mismatch_attribution_classes": list(self.mismatch_attribution_classes),
            "suspension_scope": self.suspension_scope,
            "serving_consequence": self.serving_consequence,
            "coverage_gap_consequence": self.coverage_gap_consequence,
            "artifact_mutation": "NONE",
            "record_output": "NONE",
            "external_effects": "NONE",
            "next_action": self.next_action,
        }


def _monitoring_state(value: JsonValue | None) -> MonitoringState:
    if isinstance(value, str) and (state := _MONITORING_STATES.get(value)) is not None:
        return state
    _fail("monitoring state")


def _comparison_inventory(
    input_document: dict[str, JsonValue],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    required = tuple(
        sorted(
            _strings(
                input_document.get("reconstructed_location_ids"),
                "reconstructed locations",
            ),
            key=str.encode,
        )
    )
    comparisons = _objects(input_document.get("comparison_results"), "comparison results")
    accounted = tuple(
        sorted(
            (_text(item.get("location_id"), "comparison location") for item in comparisons),
            key=str.encode,
        )
    )
    classes = tuple(_text(item.get("comparison_class"), "comparison class") for item in comparisons)
    attributions = tuple(
        sorted(
            {
                code
                for item in comparisons
                for code in _strings(item.get("attribution_classes"), "attributions")
            },
            key=str.encode,
        )
    )
    if len(accounted) != len(set(accounted)):
        _fail("duplicate comparison location")
    return required, accounted, (*classes, *attributions)


def _comparison_result(
    input_document: dict[str, JsonValue],
) -> tuple[str, tuple[str, ...], tuple[str, ...], bool]:
    required, accounted, mixed = _comparison_inventory(input_document)
    comparisons = _objects(input_document.get("comparison_results"), "comparison results")
    classes = tuple(_text(item.get("comparison_class"), "comparison class") for item in comparisons)
    attributions = tuple(
        sorted(
            {
                code
                for item in comparisons
                for code in _strings(item.get("attribution_classes"), "attributions")
            },
            key=str.encode,
        )
    )
    complete = (
        required == accounted and input_document.get("complete_comparison_accounting") is True
    )
    if "MATERIAL_MISMATCH" in classes:
        result = "MATERIAL_MISMATCH"
    elif classes and all(value == "EXACT_CANONICAL_MATCH" for value in classes):
        result = "EXACT_CANONICAL_MATCH"
    elif classes and all(
        value in {"EXACT_CANONICAL_MATCH", "PRESENTATION_ONLY_MATCH"} for value in classes
    ):
        result = "PRESENTATION_ONLY_MATCH"
    else:
        result = "NONE"
    _ = mixed
    return result, accounted, attributions, complete


@dataclass(frozen=True, slots=True)
class _Consequence:
    outcome: Outcome
    reason: str
    next_state: MonitoringState
    comparison: str
    suspension_scope: str
    serving: str
    gap: str
    next_action: str


def _default_consequence() -> _Consequence:
    return _Consequence(
        "PASS",
        "HKLEG_RECON_RECONCILE_UNCHANGED_SIGNAL",
        "AWAITING_HKEL_CONSOLIDATION",
        "NONE",
        "NONE",
        "RETAIN_ELIGIBLE_RECONSTRUCTION",
        "RETAIN_ACTIVE",
        "CONTINUE_LIGHTWEIGHT_MONITORING",
    )


def _valid_candidate_consequence(
    input_document: dict[str, JsonValue],
    comparison: str,
    attributions: tuple[str, ...],
    *,
    complete: bool,
) -> _Consequence:
    if not complete:
        return _Consequence(
            "BLOCK",
            "HKLEG_RECON_RECONCILE_LOCATION_ACCOUNTING_INCOMPLETE",
            "HKEL_CANDIDATE_OBSERVED",
            comparison,
            "NONE",
            "ORDINARY_HKEL_CANDIDATE_NOT_YET_APPROVED",
            "RETAIN_ACTIVE",
            "COMPLETE_COMPARISON_LOCATION_ACCOUNTING",
        )
    if input_document.get("common_basis") == "NOT_ISOLATABLE":
        return _Consequence(
            "PASS",
            "HKLEG_RECON_RECONCILE_COMPARISON_NOT_ISOLATABLE",
            "COMPARISON_DEFERRED",
            "COMPARISON_NOT_ISOLATABLE",
            "NONE",
            "SELECT_ORDINARY_HKEL_WHEN_APPROVED",
            "RETAIN_ACTIVE",
            "PRESERVE_DEFERRED_COMPARISON_EVIDENCE",
        )
    if comparison == "MATERIAL_MISMATCH":
        if not attributions:
            _fail("material mismatch attribution")
        return _Consequence(
            "QUARANTINE",
            "HKLEG_RECON_RECONCILE_MATERIAL_MISMATCH",
            "MISMATCH_CONFIRMED",
            comparison,
            _text(input_document.get("declared_impact_scope"), "impact scope"),
            "SELECT_ORDINARY_HKEL_WHEN_APPROVED",
            "RETAIN_ACTIVE",
            "SUSPEND_AND_REPROCESS_COMPLETE_IMPACT_SET",
        )
    if comparison in {"EXACT_CANONICAL_MATCH", "PRESENTATION_ONLY_MATCH"}:
        return _Consequence(
            "PASS",
            "HKLEG_RECON_RECONCILE_MATCH_CONFIRMED",
            "MATCH_CONFIRMED",
            comparison,
            "NONE",
            "SELECT_ORDINARY_HKEL_WHEN_APPROVED",
            "RETAIN_ACTIVE",
            "BUILD_COMPLETE_ORDINARY_HKEL_RELEASE",
        )
    _fail("valid HKeL comparison result")


def _noncomparison_consequence(input_document: dict[str, JsonValue]) -> _Consequence:
    if input_document.get("revalidation_complete") is True:
        return replace(
            _default_consequence(),
            reason="HKLEG_RECON_RECONCILE_COMPONENT_REVALIDATED",
            next_state="REVALIDATED",
            next_action="REPROCESS_COMPLETE_IMPACT_SET",
        )
    if input_document.get("reconstruction_integrity_defect") is True:
        return _Consequence(
            "QUARANTINE",
            "HKLEG_RECON_RECONCILE_COMPONENT_SUSPENDED",
            "SUSPENDED_PENDING_REVALIDATION",
            "NONE",
            _text(input_document.get("declared_impact_scope"), "impact scope"),
            "SELECT_VALIDATED_FALLBACK_OR_NO_RECORD",
            "RETAIN_ACTIVE",
            "REPROCESS_DECLARED_IMPACT_SET",
        )
    candidate_state = input_document.get("hkel_candidate_state")
    if candidate_state == "VALIDATION_RUNNING":
        return replace(
            _default_consequence(),
            reason="HKLEG_RECON_RECONCILE_CANDIDATE_OBSERVED",
            next_state="HKEL_CANDIDATE_OBSERVED",
            next_action="COMPLETE_BOUNDED_HKEL_VALIDATION",
        )
    if candidate_state == "INVALID":
        return replace(
            _default_consequence(),
            outcome="BLOCK",
            reason="HKLEG_RECON_RECONCILE_HKEL_CANDIDATE_INVALID",
            comparison="HKEL_CANDIDATE_INVALID",
            next_action="RETAIN_GAP_AND_CONTINUE_MONITORING",
        )
    return _default_consequence()


def evaluate_reconstruction_reconciliation(
    fixture_id: str,
    input_document: dict[str, JsonValue],
) -> ReconstructionReconciliationDecision:
    """Apply valid-HKeL-first monitoring, comparison, and suspension rules."""
    prior = _monitoring_state(input_document.get("current_monitoring_state"))
    required = tuple(
        sorted(
            _strings(input_document.get("reconstructed_location_ids"), "locations"),
            key=str.encode,
        )
    )
    comparison, accounted, attributions, complete = _comparison_result(input_document)
    consequence = (
        _valid_candidate_consequence(
            input_document,
            comparison,
            attributions,
            complete=complete,
        )
        if input_document.get("hkel_candidate_state") == "VALID"
        else _noncomparison_consequence(input_document)
    )
    if (
        input_document.get("hkel_candidate_state") == "VALID"
        and input_document.get("ordinary_hkel_selection") == "SELECTED_APPROVED"
    ):
        consequence = replace(
            consequence,
            next_state="SUPERSEDED_BY_HKEL",
            serving="ORDINARY_HKEL_SELECTED",
            gap="RESOLVE_AFTER_COMPLETE_RECONCILIATION",
            next_action="PRESERVE_RECONSTRUCTION_AND_SERVING_HISTORY",
        )

    return ReconstructionReconciliationDecision(
        fixture_id,
        consequence.outcome,
        consequence.reason,
        prior,
        consequence.next_state,
        consequence.comparison,
        accounted or required,
        attributions,
        consequence.suspension_scope,
        consequence.serving,
        consequence.gap,
        consequence.next_action,
    )


def prove_hk_reconstruction_reconciliation(
    package_root: Path,
) -> tuple[ReconstructionReconciliationDecision, ...]:
    """Run every frozen later-HKeL reconciliation fixture exactly."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    for relative, fragment, detail in (
        (_REASONS, "reason_code_catalogue", "reconciliation reason catalogue"),
        (_RULE, "rule", "reconciliation rule"),
        (_CATALOGUE, "fixture_catalogue", "reconciliation fixture catalogue"),
    ):
        _validate(registry, _read(package_root / relative), fragment, detail)
    catalogue = _read(package_root / _CATALOGUE)
    decisions: list[ReconstructionReconciliationDecision] = []
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
        result = evaluate_reconstruction_reconciliation(fixture_id, input_document)
        if canonicalize(checked_json_value(result.document())) != canonicalize(
            checked_json_value(expected)
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
        decisions.append(result)
    if not decisions:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "reconciliation fixtures")
    return tuple(decisions)
