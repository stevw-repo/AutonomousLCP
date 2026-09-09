"""Immutable ADR 0084 Reconstruction Execution Report construction.

The report consumes one exact Plan execution and, on success, one independently
re-read ADR 0085 artifact. It emits canonical in-memory bytes only and grants no
record, publication, provider, or external-effect authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Never

from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.errors import ContractViolation
from asklegal_contracts.json_types import checked_json_value

from .hk_reconstruction_artifact import (
    ReconstructedConsolidationArtifact,
    ReconstructionArtifactBuildRequest,
    build_reconstructed_consolidation_artifact,
    validate_reconstructed_consolidation_artifact,
)
from .hk_reconstruction_execution import (
    HK_RECONSTRUCTION_EXECUTION_RULE_ID,
    ReconstructionPlanExecution,
    reconstruction_plan_execution_from_document,
)
from .model import RulebookError, RulebookErrorCode

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

RECONSTRUCTION_EXECUTION_REPORT_SCHEMA = (
    "https://contracts.asklegal.local/v1/hk-legislation-reconstruction-execution-report.schema.json"
)
RECONSTRUCTION_EXECUTION_REPORT_CONTRACT_VERSION = "1.0.0"
HK_RECONSTRUCTION_ARTIFACT_RULE_ID = "HKLEG-RECON-ARTIFACT-001"
HK_RECONSTRUCTION_REPORT_RULE_ID = "HKLEG-RECON-REPORT-001"
_SCHEMA = "schemas/reconstruction-execution-report.schema.json"
_PLAN_SCHEMA = "schemas/reconstruction-plan-validation.schema.json#/$defs/plan"
_EXECUTION_SCHEMA = "schemas/reconstruction-execution.schema.json#/$defs/execution_result"
_LANGUAGES = ("en", "zh-Hant")
_PLAN_CONTRACT_KEYS = {
    "source_rulebook": "source_rulebook",
    "operation_registry": "operation_registry",
    "source_interpretation": "source_interpretation",
    "source_tree": "tree",
    "renderer": "renderer",
    "identity": "identity",
    "traceability": "traceability",
    "execution": "execution",
}
_REPORT_CONTRACT_KEYS = frozenset(
    (
        *_PLAN_CONTRACT_KEYS,
        "alignment",
        "lineage",
        "artifact",
        "report",
    )
)
_SOURCE_CONTRACT_REVIEW_REASONS = frozenset(
    ("RECONSTRUCTION_RENDERER_UNSUPPORTED", "RECONSTRUCTION_STRUCTURE_UNSUPPORTED")
)
_REPORT_REASON_CODES = frozenset(
    {
        "RECONSTRUCTION_COMPLETE",
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
_MAX_MEMBER_BYTES = 8_000_000
_FROZEN_FIXTURE_COUNT = 2
_REPORT_ID = re.compile(r"^rex_[0-9a-f]{48}$")
_REFERENCE_ID_PATTERNS = {
    "RECONSTRUCTION_PLAN": re.compile(r"^rpl_[0-9a-f]{48}$"),
    "ENGINE_BUILD": re.compile(r"^eng_[0-9a-f]{48}$"),
    "OFFICIAL_VERSION": re.compile(r"^ofv_[0-9a-f]{48}$"),
    "LEGAL_STATUS_EVENT": re.compile(r"^lse_[0-9a-f]{48}$"),
    "LEGAL_LOCATION": re.compile(r"^loc_[0-9a-f]{48}$"),
    "ARTIFACT": re.compile(r"^art_[0-9a-f]{48}$"),
    "COVERAGE_GAP": re.compile(r"^cvg_[0-9a-f]{48}$"),
    "FALLBACK_SELECTION": re.compile(r"^fbs_[0-9a-f]{48}$"),
    "RECONSTRUCTED_CONSOLIDATION_ARTIFACT": re.compile(r"^rca_[0-9a-f]{48}$"),
}
_MEMBER_MEDIA_TYPES = {
    "manifest.json": "application/json",
    "trees/en.json": "application/json",
    "trees/zh-Hant.json": "application/json",
    "reconstructed-location-units.jsonl": "application/x-ndjson",
    "bilingual-alignment-map.json": "application/json",
    "dependency-closure-proof.json": "application/json",
    "source-unit-coverage-proof.json": "application/json",
}
_REPORT_CONTRACT_IDENTITIES = {
    "source_rulebook": "asklegal.hk-legislation.source-rulebook",
    "operation_registry": "asklegal.hk-legislation.reconstruction-operation-registry",
    "source_interpretation": "asklegal.hk-legislation.source-interpretation",
    "source_tree": "asklegal.hk-legislation.canonical-tree",
    "renderer": "asklegal.hk-legislation.renderer",
    "alignment": "asklegal.hk-legislation.bilingual-alignment",
    "identity": "asklegal.hk-legislation.identity",
    "lineage": "asklegal.hk-legislation.identity-lineage",
    "traceability": "asklegal.hk-legislation.traceability",
    "execution": "asklegal.hk-legislation.reconstruction-execution",
    "artifact": "asklegal.hk-legislation.reconstructed-consolidation-artifact",
    "report": "asklegal.hk-legislation.reconstruction-execution-report",
}
_SUCCESS_RULE_TRACE = (
    "HKLEG-RECON-PLAN-001",
    HK_RECONSTRUCTION_EXECUTION_RULE_ID,
    HK_RECONSTRUCTION_ARTIFACT_RULE_ID,
    HK_RECONSTRUCTION_REPORT_RULE_ID,
)
_FAILURE_RULE_TRACE = (
    "HKLEG-RECON-PLAN-001",
    HK_RECONSTRUCTION_EXECUTION_RULE_ID,
    HK_RECONSTRUCTION_REPORT_RULE_ID,
)
_BLOCK_REASON_CODES = frozenset(
    {
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
        "RECONSTRUCTION_FINAL_TREE_MISMATCH",
        "RECONSTRUCTION_SOURCE_UNIT_INVENTORY_MISMATCH",
        "RECONSTRUCTION_BILINGUAL_ALIGNMENT_MISMATCH",
    }
)

type RefSignature = tuple[str, str, str]


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


def _checked_object(value: object) -> dict[str, JsonValue]:
    result = checked_json_value(value)
    if not isinstance(result, dict):
        message = "expected JSON object"
        raise TypeError(message)
    return result


def _fingerprint(value: JsonValue) -> str:
    return f"sha256:{sha256(canonicalize(value)).hexdigest()}"


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


@dataclass(frozen=True, slots=True)
class ReconstructionReportBuildRequest:
    """Exact path-free authorities for one canonical execution Report."""

    package_root: Path
    reconstruction_execution_report_id: str
    plan: dict[str, JsonValue]
    execution: ReconstructionPlanExecution
    engine_build_ref: dict[str, JsonValue]
    contracts: dict[str, JsonValue]
    coverage_gap_ref: dict[str, JsonValue]
    artifact: ReconstructedConsolidationArtifact | None
    fallback_selection_ref: dict[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class ReconstructionExecutionReport:
    """One byte-reproducible immutable ADR 0084 Report."""

    reconstruction_execution_report_id: str
    fingerprint: str
    canonical_bytes: bytes

    def document(self) -> dict[str, JsonValue]:
        """Return the strict report document from its canonical bytes."""
        try:
            value = parse_json_bytes(self.canonical_bytes, max_bytes=8_000_000)
        except ContractViolation as error:
            raise RulebookError(
                RulebookErrorCode.CONTRACT_MISMATCH,
                "Report canonical bytes",
            ) from error
        return _object(value, "Report document")

    def report_ref(self) -> dict[str, JsonValue]:
        """Return the immutable externally stored Report reference."""
        return {
            "ref_type": "RECONSTRUCTION_EXECUTION_REPORT",
            "ref_id": self.reconstruction_execution_report_id,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class _ReportContext:
    request: ReconstructionReportBuildRequest
    plan_ref: dict[str, JsonValue]
    manifest: dict[str, JsonValue] | None


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


def _validate_report_contract_identities(document: dict[str, JsonValue]) -> None:
    contracts = _object(document.get("contracts"), "replay Report contracts")
    if frozenset(contracts) != frozenset(_REPORT_CONTRACT_IDENTITIES):
        _fail("replay Report contracts")
    for key, contract_id in _REPORT_CONTRACT_IDENTITIES.items():
        reference = _object(contracts.get(key), "replay Report contract")
        if reference.get("contract_id") != contract_id or reference.get("version") != "1.0.0":
            _fail("replay Report contract identity")


def _validate_reference_role(value: JsonValue | None, expected_type: str) -> RefSignature:
    reference = _object(value, f"replay {expected_type} reference")
    signature = _ref_signature(reference)
    pattern = _REFERENCE_ID_PATTERNS[expected_type]
    if signature[0] != expected_type or pattern.fullmatch(signature[1]) is None:
        _fail(f"replay {expected_type} reference identity")
    return signature


def _validate_report_reference_semantics(document: dict[str, JsonValue]) -> None:
    _validate_reference_role(document.get("reconstruction_plan_ref"), "RECONSTRUCTION_PLAN")
    _validate_reference_role(document.get("engine_build_ref"), "ENGINE_BUILD")
    base = _object(document.get("base_validation"), "replay base validation")
    _validate_reference_role(base.get("official_version_ref"), "OFFICIAL_VERSION")
    events = _object(document.get("event_chain_validation"), "replay event validation")
    for reference in _objects(events.get("event_refs"), "replay event references"):
        _validate_reference_role(reference, "LEGAL_STATUS_EVENT")
    dependency = _object(document.get("dependency_validation"), "replay dependency validation")
    for reference in _objects(
        dependency.get("affected_location_refs"),
        "replay affected locations",
    ):
        _validate_reference_role(reference, "LEGAL_LOCATION")
    bilingual = _object(document.get("bilingual_validation"), "replay bilingual validation")
    _validate_reference_role(bilingual.get("expected_alignment_map_ref"), "ARTIFACT")
    coverage = _object(document.get("coverage_consequence"), "replay coverage")
    _validate_reference_role(coverage.get("coverage_gap_ref"), "COVERAGE_GAP")
    fallback = coverage.get("fallback_selection_ref")
    if fallback is not None:
        _validate_reference_role(fallback, "FALLBACK_SELECTION")
    if document.get("processing_outcome") != "PASS":
        return
    output = _object(document.get("artifact_output"), "replay success output")
    _validate_reference_role(
        output.get("reconstructed_consolidation_artifact_ref"),
        "RECONSTRUCTED_CONSOLIDATION_ARTIFACT",
    )
    for key in (
        "manifest_ref",
        "en_final_tree_ref",
        "zh_hant_final_tree_ref",
        "canonical_bilingual_output_ref",
        "bilingual_alignment_map_ref",
        "dependency_closure_proof_ref",
        "source_unit_coverage_proof_ref",
    ):
        member = _object(output.get(key), "replay Report member reference")
        _validate_reference_role(
            member.get("reconstructed_consolidation_artifact_ref"),
            "RECONSTRUCTED_CONSOLIDATION_ARTIFACT",
        )


def _validate_report_accounting(document: dict[str, JsonValue]) -> None:
    events = _object(document.get("event_chain_validation"), "replay event validation")
    event_refs = _objects(events.get("event_refs"), "replay event references")
    results = _objects(document.get("language_results"), "replay language results")
    if (
        events.get("event_count") != len(event_refs)
        or tuple(result.get("language") for result in results) != _LANGUAGES
    ):
        _fail("replay Report accounting")
    operations = tuple(
        operation
        for result in results
        for operation in _objects(result.get("operation_results"), "replay operation results")
    )
    operation_ids = tuple(
        _text(operation.get("operation_instance_id"), "replay operation ID")
        for operation in operations
    )
    if events.get("operation_binding_count") != len(operations) or len(set(operation_ids)) != len(
        operation_ids
    ):
        _fail("replay Report operation accounting")


def _require_true_fields(
    value: dict[str, JsonValue],
    fields: tuple[str, ...],
    detail: str,
) -> None:
    if any(value.get(field) is not True for field in fields):
        _fail(detail)


def _member_binding(
    output: dict[str, JsonValue],
    key: str,
    role: str,
    path: str,
    artifact_signature: RefSignature,
) -> dict[str, JsonValue]:
    member = _object(output.get(key), "replay Report member")
    artifact = _object(
        member.get("reconstructed_consolidation_artifact_ref"),
        "replay Report member artifact",
    )
    if (
        member.get("role") != role
        or member.get("path") != path
        or member.get("media_type") != _MEMBER_MEDIA_TYPES[path]
        or _ref_signature(artifact) != artifact_signature
    ):
        _fail("replay Report member binding")
    return member


def _validate_success_members(document: dict[str, JsonValue]) -> None:
    output = _object(document.get("artifact_output"), "replay success output")
    artifact = _object(
        output.get("reconstructed_consolidation_artifact_ref"),
        "replay reconstructed artifact",
    )
    artifact_signature = _ref_signature(artifact)
    members = {
        "manifest_ref": _member_binding(
            output, "manifest_ref", "MANIFEST", "manifest.json", artifact_signature
        ),
        "en_final_tree_ref": _member_binding(
            output, "en_final_tree_ref", "TREE_EN", "trees/en.json", artifact_signature
        ),
        "zh_hant_final_tree_ref": _member_binding(
            output,
            "zh_hant_final_tree_ref",
            "TREE_ZH_HANT",
            "trees/zh-Hant.json",
            artifact_signature,
        ),
        "bilingual_alignment_map_ref": _member_binding(
            output,
            "bilingual_alignment_map_ref",
            "BILINGUAL_ALIGNMENT_MAP",
            "bilingual-alignment-map.json",
            artifact_signature,
        ),
        "dependency_closure_proof_ref": _member_binding(
            output,
            "dependency_closure_proof_ref",
            "DEPENDENCY_CLOSURE_PROOF",
            "dependency-closure-proof.json",
            artifact_signature,
        ),
    }
    _member_binding(
        output,
        "canonical_bilingual_output_ref",
        "RECONSTRUCTED_LOCATION_UNITS",
        "reconstructed-location-units.jsonl",
        artifact_signature,
    )
    _member_binding(
        output,
        "source_unit_coverage_proof_ref",
        "SOURCE_UNIT_COVERAGE_PROOF",
        "source-unit-coverage-proof.json",
        artifact_signature,
    )
    language_results = _objects(document.get("language_results"), "replay languages")
    for result, key in zip(
        language_results,
        ("en_final_tree_ref", "zh_hant_final_tree_ref"),
        strict=True,
    ):
        member = members[key]
        if result.get("final_tree_ref") != member or result.get(
            "final_tree_fingerprint"
        ) != member.get("fingerprint"):
            _fail("replay final tree binding")
    bilingual = _object(document.get("bilingual_validation"), "replay bilingual validation")
    alignment = members["bilingual_alignment_map_ref"]
    if bilingual.get("final_alignment_map_ref") != alignment or bilingual.get(
        "final_alignment_fingerprint"
    ) != alignment.get("fingerprint"):
        _fail("replay alignment binding")
    dependency = _object(document.get("dependency_validation"), "replay dependency validation")
    if dependency.get("artifact_dependency_proof_ref") != members["dependency_closure_proof_ref"]:
        _fail("replay dependency binding")


def _validate_success_traceability(document: dict[str, JsonValue]) -> None:
    output = _object(document.get("artifact_output"), "replay success output")
    dependency = _object(document.get("dependency_validation"), "replay dependency validation")
    affected = _objects(
        output.get("affected_legal_location_refs"),
        "replay affected locations",
    )
    dependency_affected = _objects(
        dependency.get("affected_location_refs"),
        "replay dependency locations",
    )
    if affected != dependency_affected or output.get(
        "affected_location_inventory_fingerprint"
    ) != _fingerprint(checked_json_value(list(affected))):
        _fail("replay affected-location binding")
    coverage = _object(document.get("coverage_consequence"), "replay coverage")
    binding = _checked_object(
        {
            "reconstruction_plan_ref": document["reconstruction_plan_ref"],
            "reconstructed_consolidation_artifact_ref": output[
                "reconstructed_consolidation_artifact_ref"
            ],
            "manifest_ref": output["manifest_ref"],
            "affected_legal_location_refs": list(affected),
            "contracts": document["contracts"],
            "coverage_gap_ref": coverage["coverage_gap_ref"],
        }
    )
    if output.get("traceability_binding_fingerprint") != _fingerprint(binding):
        _fail("replay traceability binding")


def _validate_success_report(document: dict[str, JsonValue]) -> None:
    base = _object(document.get("base_validation"), "replay base validation")
    events = _object(document.get("event_chain_validation"), "replay event validation")
    dependency = _object(document.get("dependency_validation"), "replay dependency validation")
    bilingual = _object(document.get("bilingual_validation"), "replay bilingual validation")
    languages = _objects(document.get("language_results"), "replay language results")
    coverage = _object(document.get("coverage_consequence"), "replay coverage")
    _require_true_fields(
        base,
        (
            "identity_match",
            "fingerprint_match",
            "version_match",
            "latest_eligible_base",
            "complete",
        ),
        "replay base validation",
    )
    _require_true_fields(
        events,
        ("complete", "ordered", "applicability_bound", "operations_bound"),
        "replay event validation",
    )
    _require_true_fields(
        dependency,
        ("complete", "ownership_complete", "overlap_absent", "independence_proved"),
        "replay dependency validation",
    )
    _require_true_fields(
        bilingual,
        ("complete", "legal_effect_bound"),
        "replay bilingual validation",
    )
    if any(
        result.get("processing_outcome") != "PASS"
        or result.get("complete_source_unit_coverage") is not True
        or result.get("final_tree_ref") is None
        or result.get("final_tree_fingerprint") is None
        or result.get("final_source_unit_inventory_fingerprint") is None
        for result in languages
    ):
        _fail("replay language result")
    operations = tuple(
        operation
        for result in languages
        for operation in _objects(result.get("operation_results"), "replay operations")
    )
    if any(
        operation.get("result") != "APPLIED" or operation.get("atomic_group_result") != "APPLIED"
        for operation in operations
    ):
        _fail("replay successful operation")
    if (
        document.get("source_contract_review_required") is not False
        or _strings(document.get("reason_codes"), "replay reasons") != ("RECONSTRUCTION_COMPLETE",)
        or _strings(document.get("rule_trace"), "replay rule trace") != _SUCCESS_RULE_TRACE
        or document.get("selection_consequence") != "RECONSTRUCTION"
        or coverage.get("disposition") != "ACTIVE_MISSING_CONSOLIDATION"
        or coverage.get("fallback_selection_ref") is not None
    ):
        _fail("replay successful Report consequence")
    _validate_success_members(document)
    _validate_success_traceability(document)


def _validate_failure_report(document: dict[str, JsonValue]) -> None:
    languages = _objects(document.get("language_results"), "replay failure languages")
    bilingual = _object(document.get("bilingual_validation"), "replay bilingual validation")
    dependency = _object(document.get("dependency_validation"), "replay dependency validation")
    coverage = _object(document.get("coverage_consequence"), "replay coverage")
    reasons = _strings(document.get("reason_codes"), "replay failure reasons")
    fallback = coverage.get("fallback_selection_ref")
    expected_selection = "FALLBACK" if fallback is not None else "NO_RECORD"
    if (
        len(reasons) != 1
        or document.get("processing_outcome") != "BLOCK"
        or reasons[0] not in _BLOCK_REASON_CODES
        or _strings(document.get("rule_trace"), "replay rule trace") != _FAILURE_RULE_TRACE
        or document.get("selection_consequence") != expected_selection
        or coverage.get("disposition") != "EXECUTION_FAILED"
        or dependency.get("artifact_dependency_proof_ref") is not None
        or bilingual.get("complete") is not False
        or bilingual.get("final_alignment_map_ref") is not None
        or bilingual.get("final_alignment_fingerprint") is not None
        or document.get("source_contract_review_required")
        is not (reasons[0] in _SOURCE_CONTRACT_REVIEW_REASONS)
        or any(
            result.get("processing_outcome") != "BLOCK"
            or result.get("complete_source_unit_coverage") is not False
            or result.get("final_tree_ref") is not None
            or result.get("final_tree_fingerprint") is not None
            or result.get("final_source_unit_inventory_fingerprint") is not None
            for result in languages
        )
    ):
        _fail("replay failed Report consequence")


def validate_reconstruction_execution_report(
    package_root: Path,
    report: object,
) -> ReconstructionExecutionReport:
    """Validate one canonical Report for replay without claiming source provenance."""
    if type(report) is not ReconstructionExecutionReport:
        _fail("replay Report type")
    report_id = report.reconstruction_execution_report_id
    fingerprint = report.fingerprint
    raw = report.canonical_bytes
    if (
        type(report_id) is not str
        or _REPORT_ID.fullmatch(report_id) is None
        or type(fingerprint) is not str
        or type(raw) is not bytes
        or not raw
        or len(raw) > _MAX_MEMBER_BYTES
        or _bytes_fingerprint(raw) != fingerprint
    ):
        _fail("replay Report envelope")
    document = _object(parse_json_bytes(raw, max_bytes=_MAX_MEMBER_BYTES), "replay Report")
    if canonicalize(checked_json_value(document)) != raw:
        _fail("replay Report canonical read-back")
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_schema(registry, document, _SCHEMA, "replay Report schema")
    if document.get("reconstruction_execution_report_id") != report_id:
        _fail("replay Report identity")
    _validate_report_contract_identities(document)
    _validate_report_reference_semantics(document)
    _validate_report_accounting(document)
    if document.get("processing_outcome") == "PASS":
        _validate_success_report(document)
    else:
        _validate_failure_report(document)
    return ReconstructionExecutionReport(report_id, fingerprint, bytes(raw))


def _validate_contracts(request: ReconstructionReportBuildRequest) -> None:
    if frozenset(request.contracts) != _REPORT_CONTRACT_KEYS:
        _fail("Report contracts")
    plan_contracts = _object(request.plan.get("contracts"), "Plan contracts")
    for report_key, plan_key in _PLAN_CONTRACT_KEYS.items():
        report_ref = _object(request.contracts.get(report_key), "Report contract")
        plan_contract = _object(plan_contracts.get(plan_key), "Plan contract")
        if _contract_signature(report_ref) != _contract_signature(plan_contract):
            _fail("shared Report contract")


def _build_context(request: ReconstructionReportBuildRequest) -> _ReportContext:
    registry = SchemaRegistry.from_contracts_root(request.package_root / "contracts")
    _validate_schema(registry, checked_json_value(request.plan), _PLAN_SCHEMA, "Report Plan")
    _validate_schema(
        registry,
        checked_json_value(request.execution.document()),
        _EXECUTION_SCHEMA,
        "Report execution",
    )
    _validate_contracts(request)
    plan_id = _text(request.plan.get("reconstruction_plan_id"), "Report Plan ID")
    plan_fingerprint = _fingerprint(request.plan)
    if (
        request.execution.reconstruction_plan_id != plan_id
        or request.execution.reconstruction_plan_fingerprint != plan_fingerprint
    ):
        _fail("Report execution authority")
    plan_ref: dict[str, JsonValue] = {
        "ref_type": "RECONSTRUCTION_PLAN",
        "ref_id": plan_id,
        "fingerprint": plan_fingerprint,
    }
    manifest: dict[str, JsonValue] | None = None
    if request.execution.processing_outcome == "PASS":
        if request.artifact is None or request.fallback_selection_ref is not None:
            _fail("successful Report output")
        manifest = validate_reconstructed_consolidation_artifact(
            request.package_root,
            request.artifact,
        )
        if _ref_signature(
            _object(manifest.get("reconstruction_plan_ref"), "artifact Plan reference")
        ) != _ref_signature(plan_ref) or _ref_signature(
            _object(manifest.get("coverage_gap_ref"), "artifact gap")
        ) != _ref_signature(request.coverage_gap_ref):
            _fail("Report artifact bindings")
    elif request.artifact is not None:
        _fail("failed Report artifact")
    return _ReportContext(request, plan_ref, manifest)


def _base_validation(plan: dict[str, JsonValue]) -> dict[str, JsonValue]:
    base = _object(plan.get("base"), "Report base")
    return _checked_object(
        {
            "official_version_ref": base["official_version_ref"],
            "canonical_bilingual_base_fingerprint": base["canonical_bilingual_base_fingerprint"],
            "source_version_date": base["source_version_date"],
            "evidence_class": base["evidence_class"],
            "identity_match": True,
            "fingerprint_match": True,
            "version_match": True,
            "latest_eligible_base": True,
            "complete": True,
        }
    )


def _event_validation(plan: dict[str, JsonValue]) -> dict[str, JsonValue]:
    events = _objects(plan.get("event_chain"), "Report event chain")
    operation_ids = tuple(
        operation_id
        for event in events
        for operation_id in _strings(event.get("operation_instance_ids"), "event operations")
    )
    return _checked_object(
        {
            "event_refs": [_object(event.get("event_ref"), "Report event") for event in events],
            "event_count": len(events),
            "operation_binding_count": len(operation_ids),
            "complete": True,
            "ordered": True,
            "applicability_bound": True,
            "operations_bound": True,
        }
    )


def _dependency_validation(context: _ReportContext) -> dict[str, JsonValue]:
    closure = _object(context.request.plan.get("dependency_closure"), "Report closure")
    artifact = context.request.artifact
    return _checked_object(
        {
            "affected_location_refs": context.request.plan["affected_legal_location_refs"],
            "closure_proof_fingerprint": closure["closure_proof_fingerprint"],
            "artifact_dependency_proof_ref": (
                artifact.member_ref("dependency-closure-proof.json")
                if artifact is not None
                else None
            ),
            "complete": True,
            "ownership_complete": True,
            "overlap_absent": True,
            "independence_proved": True,
        }
    )


def _result_documents(
    execution: ReconstructionPlanExecution,
    language: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        result.document() for result in execution.operation_results if result.language == language
    )


def _validate_operation_accounting(context: _ReportContext) -> None:
    streams = _objects(context.request.plan.get("language_streams"), "Report streams")
    if tuple(stream.get("language") for stream in streams) != _LANGUAGES:
        _fail("Report language order")
    for stream, language in zip(streams, _LANGUAGES, strict=True):
        planned = _objects(stream.get("operations"), "Report Plan operations")
        actual = _result_documents(context.request.execution, language)
        plan_signatures = tuple(
            (operation.get("operation_instance_id"), operation.get("operation_type_id"))
            for operation in planned
        )
        result_signatures = tuple(
            (result.get("operation_instance_id"), result.get("operation_type_id"))
            for result in actual
        )
        if plan_signatures != result_signatures:
            _fail("Report operation accounting")


def _language_results(context: _ReportContext) -> list[dict[str, JsonValue]]:
    streams = _objects(context.request.plan.get("language_streams"), "Report streams")
    artifact = context.request.artifact
    output: list[dict[str, JsonValue]] = []
    for index, (stream, language) in enumerate(zip(streams, _LANGUAGES, strict=True)):
        tree_path = "trees/en.json" if index == 0 else "trees/zh-Hant.json"
        output.append(
            _checked_object(
                {
                    "language": language,
                    "operation_results": list(
                        _result_documents(context.request.execution, language)
                    ),
                    "final_tree_ref": artifact.member_ref(tree_path) if artifact else None,
                    "final_tree_fingerprint": (
                        context.request.execution.provisional_language_tree_fingerprints[index]
                        if artifact
                        else None
                    ),
                    "final_source_unit_inventory_fingerprint": (
                        stream["expected_complete_source_unit_inventory_fingerprint"]
                        if artifact
                        else None
                    ),
                    "complete_source_unit_coverage": artifact is not None,
                    "processing_outcome": (
                        "PASS"
                        if context.request.execution.processing_outcome == "PASS"
                        else "BLOCK"
                    ),
                }
            )
        )
    return output


def _bilingual_validation(context: _ReportContext) -> dict[str, JsonValue]:
    streams = _objects(context.request.plan.get("language_streams"), "Report streams")
    expected_refs = tuple(
        _object(stream.get("expected_bilingual_alignment_map_ref"), "expected alignment")
        for stream in streams
    )
    if _ref_signature(expected_refs[0]) != _ref_signature(expected_refs[1]):
        _fail("Report expected alignment")
    artifact = context.request.artifact
    return _checked_object(
        {
            "expected_alignment_map_ref": expected_refs[0],
            "final_alignment_map_ref": (
                artifact.member_ref("bilingual-alignment-map.json") if artifact else None
            ),
            "final_alignment_fingerprint": (
                context.request.execution.provisional_bilingual_alignment_map_fingerprint
                if artifact
                else None
            ),
            "complete": artifact is not None,
            "legal_effect_bound": True,
        }
    )


def _artifact_output(context: _ReportContext) -> dict[str, JsonValue]:
    artifact = context.request.artifact
    if artifact is None:
        return {
            "record_output": "NONE",
            "reconstructed_artifact_count": 0,
            "artifact_refs": [],
        }
    affected = _objects(
        context.request.plan.get("affected_legal_location_refs"),
        "Report affected locations",
    )
    manifest_ref = artifact.member_ref("manifest.json")
    binding = _checked_object(
        {
            "reconstruction_plan_ref": context.plan_ref,
            "reconstructed_consolidation_artifact_ref": artifact.artifact_ref(),
            "manifest_ref": manifest_ref,
            "affected_legal_location_refs": list(affected),
            "contracts": context.request.contracts,
            "coverage_gap_ref": context.request.coverage_gap_ref,
        }
    )
    return {
        "reconstructed_consolidation_artifact_ref": artifact.artifact_ref(),
        "manifest_ref": manifest_ref,
        "en_final_tree_ref": artifact.member_ref("trees/en.json"),
        "zh_hant_final_tree_ref": artifact.member_ref("trees/zh-Hant.json"),
        "canonical_bilingual_output_ref": artifact.member_ref("reconstructed-location-units.jsonl"),
        "bilingual_alignment_map_ref": artifact.member_ref("bilingual-alignment-map.json"),
        "dependency_closure_proof_ref": artifact.member_ref("dependency-closure-proof.json"),
        "source_unit_coverage_proof_ref": artifact.member_ref("source-unit-coverage-proof.json"),
        "affected_legal_location_refs": list(affected),
        "affected_location_inventory_fingerprint": _fingerprint(checked_json_value(list(affected))),
        "traceability_binding_fingerprint": _fingerprint(binding),
        "record_output": "NONE",
    }


def _report_document(context: _ReportContext) -> dict[str, JsonValue]:
    request = context.request
    passed = request.execution.processing_outcome == "PASS"
    fallback = request.fallback_selection_ref
    return _checked_object(
        {
            "$schema": RECONSTRUCTION_EXECUTION_REPORT_SCHEMA,
            "contract_version": RECONSTRUCTION_EXECUTION_REPORT_CONTRACT_VERSION,
            "reconstruction_execution_report_id": request.reconstruction_execution_report_id,
            "reconstruction_plan_ref": context.plan_ref,
            "engine_build_ref": request.engine_build_ref,
            "contracts": request.contracts,
            "base_validation": _base_validation(request.plan),
            "event_chain_validation": _event_validation(request.plan),
            "dependency_validation": _dependency_validation(context),
            "language_results": _language_results(context),
            "bilingual_validation": _bilingual_validation(context),
            "processing_outcome": "PASS" if passed else "BLOCK",
            "source_contract_review_required": (
                request.execution.reason_code in _SOURCE_CONTRACT_REVIEW_REASONS
            ),
            "reason_codes": [
                "RECONSTRUCTION_COMPLETE" if passed else request.execution.reason_code
            ],
            "rule_trace": [
                "HKLEG-RECON-PLAN-001",
                HK_RECONSTRUCTION_EXECUTION_RULE_ID,
                *([HK_RECONSTRUCTION_ARTIFACT_RULE_ID] if passed else []),
                HK_RECONSTRUCTION_REPORT_RULE_ID,
            ],
            "artifact_output": _artifact_output(context),
            "coverage_consequence": {
                "coverage_gap_ref": request.coverage_gap_ref,
                "disposition": ("ACTIVE_MISSING_CONSOLIDATION" if passed else "EXECUTION_FAILED"),
                "matching_hkel_consolidation_required": True,
                "fallback_selection_ref": fallback,
            },
            "selection_consequence": (
                "RECONSTRUCTION" if passed else ("FALLBACK" if fallback else "NO_RECORD")
            ),
            "external_effects": "NONE",
        }
    )


def build_reconstruction_execution_report(
    request: ReconstructionReportBuildRequest,
) -> ReconstructionExecutionReport:
    """Build and validate one complete immutable execution Report."""
    context = _build_context(request)
    _validate_operation_accounting(context)
    document = _report_document(context)
    registry = SchemaRegistry.from_contracts_root(request.package_root / "contracts")
    _validate_schema(registry, document, _SCHEMA, "Reconstruction Execution Report")
    raw = canonicalize(checked_json_value(document))
    report = ReconstructionExecutionReport(
        request.reconstruction_execution_report_id,
        f"sha256:{sha256(raw).hexdigest()}",
        raw,
    )
    if canonicalize(checked_json_value(report.document())) != raw:
        _fail("Report canonical read-back")
    return validate_reconstruction_execution_report(request.package_root, report)


def _report_request_from_fixture_document(
    package_root: Path,
    document: dict[str, JsonValue],
) -> ReconstructionReportBuildRequest:
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_schema(registry, document, f"{_SCHEMA}#/$defs/report_request", "report request")
    plan = _object(document.get("plan"), "fixture Plan")
    execution = reconstruction_plan_execution_from_document(
        package_root,
        _object(document.get("execution"), "fixture execution"),
    )
    artifact_input = document.get("artifact_build")
    artifact: ReconstructedConsolidationArtifact | None = None
    if isinstance(artifact_input, dict):
        artifact = build_reconstructed_consolidation_artifact(
            ReconstructionArtifactBuildRequest(
                package_root=package_root,
                reconstructed_consolidation_artifact_id=_text(
                    artifact_input.get("reconstructed_consolidation_artifact_id"),
                    "fixture artifact ID",
                ),
                plan=plan,
                execution=execution,
                base_language_trees=_objects(
                    artifact_input.get("base_language_trees"),
                    "fixture base trees",
                ),
                coverage_gap_ref=_object(
                    artifact_input.get("coverage_gap_ref"),
                    "fixture artifact gap",
                ),
                identity_lineage_decision_ref=_object(
                    artifact_input.get("identity_lineage_decision_ref"),
                    "fixture lineage decision",
                ),
                operative_state_decision_ref=_object(
                    artifact_input.get("operative_state_decision_ref"),
                    "fixture operative decision",
                ),
                contracts=_object(artifact_input.get("contracts"), "fixture artifact contracts"),
                authority_note_template_contract_ref=_object(
                    artifact_input.get("authority_note_template_contract_ref"),
                    "fixture authority-note contract",
                ),
                lineage_links=_objects(
                    artifact_input.get("lineage_links"),
                    "fixture lineage links",
                ),
            )
        )
    fallback_value = document.get("fallback_selection_ref")
    fallback = _object(fallback_value, "fixture fallback") if fallback_value is not None else None
    return ReconstructionReportBuildRequest(
        package_root=package_root,
        reconstruction_execution_report_id=_text(
            document.get("reconstruction_execution_report_id"),
            "fixture Report ID",
        ),
        plan=plan,
        execution=execution,
        engine_build_ref=_object(document.get("engine_build_ref"), "fixture engine build"),
        contracts=_object(document.get("contracts"), "fixture Report contracts"),
        coverage_gap_ref=_object(document.get("coverage_gap_ref"), "fixture coverage gap"),
        artifact=artifact,
        fallback_selection_ref=fallback,
    )


def _read_package_object(path: Path) -> dict[str, JsonValue]:
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_MEMBER_BYTES:
        _fail("report package member bytes")
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX_MEMBER_BYTES)
    except ContractViolation as error:
        raise RulebookError(
            RulebookErrorCode.CONTRACT_MISMATCH,
            "report package member",
        ) from error
    return _object(value, "report package member")


def _safe_package_member(package_root: Path, relative: str) -> Path:
    member = PurePosixPath(relative)
    if (
        not relative
        or member.is_absolute()
        or member.as_posix() != relative
        or ".." in member.parts
    ):
        _fail("report package member path")
    path = package_root.joinpath(*member.parts)
    resolved_root = package_root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents or not path.is_file() or path.is_symlink():
        _fail("report package member path")
    return path


def _bytes_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _validate_package_declarations(
    package_root: Path,
    registry: SchemaRegistry,
) -> None:
    reasons = _read_package_object(
        package_root / "catalogues/reconstruction-report-reason-codes.json"
    )
    _validate_schema(
        registry,
        reasons,
        f"{_SCHEMA}#/$defs/reason_code_catalogue",
        "report reason catalogue",
    )
    declared = {
        _text(item.get("code"), "report reason")
        for item in _objects(reasons.get("reason_codes"), "report reasons")
    }
    if frozenset(declared) != _REPORT_REASON_CODES:
        raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "report reason catalogue")
    for rule_id, definition in (
        (HK_RECONSTRUCTION_ARTIFACT_RULE_ID, "artifact_rule"),
        (HK_RECONSTRUCTION_REPORT_RULE_ID, "report_rule"),
    ):
        rule = _read_package_object(package_root / f"rules/{rule_id}.json")
        _validate_schema(registry, rule, f"{_SCHEMA}#/$defs/{definition}", rule_id)


def _prove_report_fixture(
    package_root: Path,
    registry: SchemaRegistry,
    entry: dict[str, JsonValue],
) -> ReconstructionExecutionReport:
    fixture_id = _text(entry.get("fixture_id"), "report fixture ID")
    fixture_path = _safe_package_member(
        package_root,
        _text(entry.get("path"), "report fixture path"),
    )
    expected_path = _safe_package_member(
        package_root,
        _text(entry.get("expected_path"), "report expected path"),
    )
    if _bytes_fingerprint(fixture_path.read_bytes()) != entry.get(
        "fixture_fingerprint"
    ) or _bytes_fingerprint(expected_path.read_bytes()) != entry.get("expected_fingerprint"):
        raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, fixture_id)
    fixture = _read_package_object(fixture_path)
    _validate_schema(registry, fixture, f"{_SCHEMA}#/$defs/fixture", "report fixture")
    if fixture.get("fixture_id") != fixture_id:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, fixture_id)
    declaration = _object(fixture.get("expected_artifact"), "report expected declaration")
    if declaration.get("path") != entry.get("expected_path") or declaration.get(
        "fingerprint"
    ) != entry.get("expected_fingerprint"):
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "report expected artifact")
    input_document = _object(fixture.get("input"), "report fixture input")
    if _fingerprint(input_document) != fixture.get("input_fingerprint"):
        raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "report fixture input")
    report = build_reconstruction_execution_report(
        _report_request_from_fixture_document(package_root, input_document)
    )
    expected = _read_package_object(expected_path)
    _validate_schema(registry, expected, _SCHEMA, "expected report")
    if report.canonical_bytes != canonicalize(checked_json_value(expected)):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, f"expected {fixture_id}")
    return report


def prove_hk_reconstruction_report(
    package_root: Path,
) -> tuple[ReconstructionExecutionReport, ...]:
    """Rebuild every frozen artifact/Report fixture and compare exact bytes."""
    registry = SchemaRegistry.from_contracts_root(package_root / "contracts")
    _validate_package_declarations(package_root, registry)
    catalogue = _read_package_object(
        package_root / "catalogues/reconstruction-report-fixtures.json"
    )
    _validate_schema(
        registry,
        catalogue,
        f"{_SCHEMA}#/$defs/fixture_catalogue",
        "report fixture catalogue",
    )
    entries = _objects(catalogue.get("fixtures"), "report fixtures")
    if len(entries) != _FROZEN_FIXTURE_COUNT:
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "report fixtures")
    fixture_ids = tuple(_text(entry.get("fixture_id"), "report fixture ID") for entry in entries)
    if len(set(fixture_ids)) != len(fixture_ids):
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "duplicate report fixture")
    return tuple(_prove_report_fixture(package_root, registry, entry) for entry in entries)
