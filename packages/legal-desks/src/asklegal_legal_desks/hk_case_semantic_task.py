"""Source-neutral ADR 0065/0066 Hong Kong Case semantic-task preflight."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
from re import fullmatch

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .hk_case_coverage_ledger import HKCaseOpinionRole

HK_CASE_SEMANTIC_TASK_CONTRACT_VERSION = "1.0.0"
HK_CASE_SEMANTIC_TASK_RULE_ID = "HKCASE-PROP-SEMANTIC-TASK-PREFLIGHT-001"

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_IDENTITY_PATTERN = r"[a-z][a-z0-9_]{2,95}"
_CODE_PATTERN = r"[A-Z][A-Z0-9_]{2,95}"


class HKCaseSemanticTaskErrorCode(StrEnum):
    """Closed malformed semantic-task request failures."""

    CONTRACT = "HK_CASE_SEMANTIC_TASK_CONTRACT_INVALID"
    FINGERPRINT = "HK_CASE_SEMANTIC_TASK_FINGERPRINT_INVALID"
    IDENTITY = "HK_CASE_SEMANTIC_TASK_IDENTITY_INVALID"


class HKCaseSemanticTaskError(ValueError):
    """One fail-closed malformed semantic-task request."""

    code: HKCaseSemanticTaskErrorCode

    def __init__(self, code: HKCaseSemanticTaskErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKCaseSemanticTaskFamily(StrEnum):
    """The two stable ADR 0066 task-family identities."""

    ANALYSIS = "hk-case-proposition-analysis/v1"
    CHALLENGE = "hk-case-proposition-challenge/v1"


class HKCaseSemanticRequestKind(StrEnum):
    """The eight closed request kinds."""

    COVERAGE_PACKET_CHALLENGE = "COVERAGE_PACKET_CHALLENGE"
    EVIDENCE_PACKET = "EVIDENCE_PACKET"
    FINAL_TARGETED_CHALLENGE = "FINAL_TARGETED_CHALLENGE"
    FULL_JUDGMENT = "FULL_JUDGMENT"
    FULL_JUDGMENT_CHALLENGE = "FULL_JUDGMENT_CHALLENGE"
    JUDGMENT_INTEGRATION = "JUDGMENT_INTEGRATION"
    JUDGMENT_RESULT_CHALLENGE = "JUDGMENT_RESULT_CHALLENGE"
    TARGETED_REANALYSIS = "TARGETED_REANALYSIS"


class HKCaseOriginalLanguage(StrEnum):
    """Source-supported original-language classifications."""

    ENGLISH = "ENGLISH"
    MIXED = "MIXED"
    TRADITIONAL_CHINESE = "TRADITIONAL_CHINESE"


class HKCaseSemanticTaskOutcome(StrEnum):
    """Deterministic preflight conclusions."""

    BLOCKED = "BLOCKED"
    INVALID = "INVALID"
    VALID_REQUEST = "VALID_REQUEST"


class HKCaseSemanticTaskReason(StrEnum):
    """Closed preflight reasons."""

    ASSIGNED_PRIMARY_UNITS_INVALID = "ASSIGNED_PRIMARY_UNITS_INVALID"
    COMPLETE_COVERAGE_REQUIRED = "COMPLETE_COVERAGE_REQUIRED"
    CONSTRAINT_BOUNDARY_INVALID = "CONSTRAINT_BOUNDARY_INVALID"
    DEPENDENCY_PACKET_INVALID = "DEPENDENCY_PACKET_INVALID"
    DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
    EVIDENCE_RANGE_INVALID = "EVIDENCE_RANGE_INVALID"
    OPINION_OR_UNIT_MANIFEST_INVALID = "OPINION_OR_UNIT_MANIFEST_INVALID"
    PRIOR_STAGE_BINDING_INVALID = "PRIOR_STAGE_BINDING_INVALID"
    SOURCE_EVIDENCE_UNAVAILABLE = "SOURCE_EVIDENCE_UNAVAILABLE"
    TASK_KIND_MISMATCH = "TASK_KIND_MISMATCH"
    VALID_REQUEST = "VALID_REQUEST"
    WORKFLOW_BINDING_INVALID = "WORKFLOW_BINDING_INVALID"


@dataclass(frozen=True, slots=True)
class HKCaseSemanticWorkflowComponent:
    """One exact result-affecting workflow component."""

    component_role: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseSemanticOpinionManifest:
    """One source-supported delivered opinion."""

    opinion_id: str
    source_order: int
    role: HKCaseOpinionRole
    judge_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticUnitManifest:
    """One unit in the complete ordered judgment manifest."""

    unit_id: str
    opinion_id: str
    source_order: int
    primary: bool
    text_fingerprint: str
    required_dependency_unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseSemanticSuppliedUnit:
    """Exact original-language text supplied to this bounded request."""

    unit_id: str
    exact_text: str


@dataclass(frozen=True, slots=True)
class HKCaseSemanticEvidenceRange:
    """One UTF-8 byte range within a supplied unit."""

    range_id: str
    unit_id: str
    start_byte: int
    end_byte: int
    exact_text_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseSemanticDependency:
    """One assigned unit's exact dependency on a primary unit."""

    assigned_unit_id: str
    dependency_unit_id: str
    dependency_text_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseSemanticTaskRequest:
    """One complete evidence-bound analysis or challenge request."""

    task_family: HKCaseSemanticTaskFamily
    request_kind: HKCaseSemanticRequestKind
    execution_id: str
    attempt_id: str
    packet_id: str | None
    judgment_work_id: str
    workflow_components: tuple[HKCaseSemanticWorkflowComponent, ...]
    judicial_decision_id: str
    official_version_id: str
    artifact_fingerprint: str
    source_snapshot_fingerprint: str
    cutoff: str
    court: str
    decision_date: str
    citation: str
    original_language: HKCaseOriginalLanguage
    opinions: tuple[HKCaseSemanticOpinionManifest, ...]
    units: tuple[HKCaseSemanticUnitManifest, ...]
    assigned_primary_unit_ids: tuple[str, ...]
    supplied_units: tuple[HKCaseSemanticSuppliedUnit, ...]
    evidence_ranges: tuple[HKCaseSemanticEvidenceRange, ...]
    dependencies: tuple[HKCaseSemanticDependency, ...]
    allowed_object_ids: tuple[str, ...]
    required_evidence_role_codes: tuple[str, ...]
    output_budget_bytes: int
    validated_proposal_fingerprint: str | None
    reconciled_objection_fingerprint: str | None
    source_text_is_instruction: bool
    external_tools_permitted: bool
    hidden_reference_included: bool
    confidence_score_requested: bool
    source_evidence_available: bool


@dataclass(frozen=True, slots=True)
class HKCaseSemanticTaskResult:
    """One preflight result with no provider or downstream authority."""

    request_fingerprint: str
    outcome: HKCaseSemanticTaskOutcome
    reasons: tuple[HKCaseSemanticTaskReason, ...]
    opinion_count: int
    unit_count: int
    primary_unit_count: int
    assigned_primary_unit_count: int
    supplied_unit_count: int
    evidence_range_count: int
    dependency_count: int
    complete_judgment_assignment: bool
    provider_call_authorized: bool
    semantic_result_accepted: bool
    search_records_created: int
    release_eligible: bool
    external_effects: str


_ANALYSIS_KINDS = frozenset(
    {
        HKCaseSemanticRequestKind.EVIDENCE_PACKET,
        HKCaseSemanticRequestKind.FULL_JUDGMENT,
        HKCaseSemanticRequestKind.JUDGMENT_INTEGRATION,
        HKCaseSemanticRequestKind.TARGETED_REANALYSIS,
    }
)
_CHALLENGE_KINDS = frozenset(
    {
        HKCaseSemanticRequestKind.COVERAGE_PACKET_CHALLENGE,
        HKCaseSemanticRequestKind.FINAL_TARGETED_CHALLENGE,
        HKCaseSemanticRequestKind.FULL_JUDGMENT_CHALLENGE,
        HKCaseSemanticRequestKind.JUDGMENT_RESULT_CHALLENGE,
    }
)
_PACKET_KINDS = frozenset(
    {
        HKCaseSemanticRequestKind.COVERAGE_PACKET_CHALLENGE,
        HKCaseSemanticRequestKind.EVIDENCE_PACKET,
    }
)
_COMPLETE_JUDGMENT_KINDS = frozenset(
    {
        HKCaseSemanticRequestKind.FULL_JUDGMENT,
        HKCaseSemanticRequestKind.FULL_JUDGMENT_CHALLENGE,
        HKCaseSemanticRequestKind.JUDGMENT_INTEGRATION,
        HKCaseSemanticRequestKind.JUDGMENT_RESULT_CHALLENGE,
    }
)
_REQUIRED_WORKFLOW_ROLES = frozenset(
    {
        "COVERAGE_LEDGER",
        "MODEL_SETTINGS",
        "OUTPUT_SCHEMA",
        "PARSER_PROFILE",
        "PROCESSING_BUILD",
        "PROMPT",
        "SEGMENTATION_CONTRACT",
        "SOURCE_RULEBOOK",
        "STRUCTURE_CONTRACT",
        "VALIDATOR",
    }
)
_REQUIRED_EVIDENCE_ROLE_CODES = frozenset(
    {
        "ANSWER",
        "APPLICATION",
        "ATTRIBUTION",
        "CONTEXT",
        "ISSUE",
        "QUALIFICATION",
        "QUOTATION",
        "RESULT",
    }
)


def evaluate_hk_case_semantic_task_request(
    request: HKCaseSemanticTaskRequest,
) -> HKCaseSemanticTaskResult:
    """Validate a complete task envelope without authorizing or making a call."""
    request_fingerprint = fingerprint(
        checked_json_value(hk_case_semantic_task_request_document(request))
    )
    reasons = _request_errors(request)
    primary_ids = tuple(item.unit_id for item in request.units if item.primary)
    complete_assignment = request.assigned_primary_unit_ids == primary_ids
    if reasons:
        outcome = HKCaseSemanticTaskOutcome.INVALID
    elif not request.source_evidence_available:
        outcome = HKCaseSemanticTaskOutcome.BLOCKED
        reasons = {HKCaseSemanticTaskReason.SOURCE_EVIDENCE_UNAVAILABLE}
    else:
        outcome = HKCaseSemanticTaskOutcome.VALID_REQUEST
        reasons = {HKCaseSemanticTaskReason.VALID_REQUEST}
    return HKCaseSemanticTaskResult(
        request_fingerprint=request_fingerprint,
        outcome=outcome,
        reasons=tuple(sorted(reasons, key=str)),
        opinion_count=len(request.opinions),
        unit_count=len(request.units),
        primary_unit_count=len(primary_ids),
        assigned_primary_unit_count=len(request.assigned_primary_unit_ids),
        supplied_unit_count=len(request.supplied_units),
        evidence_range_count=len(request.evidence_ranges),
        dependency_count=len(request.dependencies),
        complete_judgment_assignment=complete_assignment,
        provider_call_authorized=False,
        semantic_result_accepted=False,
        search_records_created=0,
        release_eligible=False,
        external_effects="NONE",
    )


def _request_errors(request: HKCaseSemanticTaskRequest) -> set[HKCaseSemanticTaskReason]:
    errors: set[HKCaseSemanticTaskReason] = set()
    checks = (
        (_scalar_bindings_valid(request), HKCaseSemanticTaskReason.WORKFLOW_BINDING_INVALID),
        (_task_kind_valid(request), HKCaseSemanticTaskReason.TASK_KIND_MISMATCH),
        (_workflow_valid(request), HKCaseSemanticTaskReason.WORKFLOW_BINDING_INVALID),
        (_manifest_valid(request), HKCaseSemanticTaskReason.OPINION_OR_UNIT_MANIFEST_INVALID),
        (_assignment_valid(request), HKCaseSemanticTaskReason.ASSIGNED_PRIMARY_UNITS_INVALID),
        (_supplied_evidence_valid(request), HKCaseSemanticTaskReason.EVIDENCE_RANGE_INVALID),
        (_dependencies_valid(request), HKCaseSemanticTaskReason.DEPENDENCY_PACKET_INVALID),
        (_prior_stage_valid(request), HKCaseSemanticTaskReason.PRIOR_STAGE_BINDING_INVALID),
        (_constraints_valid(request), HKCaseSemanticTaskReason.CONSTRAINT_BOUNDARY_INVALID),
    )
    errors.update(reason for valid, reason in checks if not valid)
    if request.request_kind in _COMPLETE_JUDGMENT_KINDS and not _complete_assignment(request):
        errors.add(HKCaseSemanticTaskReason.COMPLETE_COVERAGE_REQUIRED)
    if _has_duplicate_identity(request):
        errors.add(HKCaseSemanticTaskReason.DUPLICATE_IDENTITY)
    return errors


def _scalar_bindings_valid(request: HKCaseSemanticTaskRequest) -> bool:
    identities = (
        request.execution_id,
        request.attempt_id,
        request.judgment_work_id,
        request.judicial_decision_id,
        request.official_version_id,
    )
    fingerprints = (request.artifact_fingerprint, request.source_snapshot_fingerprint)
    try:
        date.fromisoformat(request.cutoff)
        date.fromisoformat(request.decision_date)
    except ValueError:
        return False
    return (
        all(fullmatch(_IDENTITY_PATTERN, item) is not None for item in identities)
        and (
            request.packet_id is None or fullmatch(_IDENTITY_PATTERN, request.packet_id) is not None
        )
        and all(fullmatch(_FINGERPRINT_PATTERN, item) is not None for item in fingerprints)
        and bool(request.court)
        and bool(request.citation)
        and request.output_budget_bytes > 0
    )


def _task_kind_valid(request: HKCaseSemanticTaskRequest) -> bool:
    if request.task_family is HKCaseSemanticTaskFamily.ANALYSIS:
        return request.request_kind in _ANALYSIS_KINDS
    return request.request_kind in _CHALLENGE_KINDS


def _workflow_valid(request: HKCaseSemanticTaskRequest) -> bool:
    roles = tuple(item.component_role for item in request.workflow_components)
    return (
        set(roles) == set(_REQUIRED_WORKFLOW_ROLES)
        and not _duplicates(roles)
        and all(
            fullmatch(_FINGERPRINT_PATTERN, item.fingerprint) is not None
            for item in request.workflow_components
        )
    )


def _manifest_valid(request: HKCaseSemanticTaskRequest) -> bool:
    opinion_ids = {item.opinion_id for item in request.opinions}
    unit_ids = {item.unit_id for item in request.units}
    return (
        bool(request.opinions)
        and bool(request.units)
        and tuple(item.source_order for item in request.opinions)
        == tuple(range(1, len(request.opinions) + 1))
        and tuple(item.source_order for item in request.units)
        == tuple(range(1, len(request.units) + 1))
        and all(item.opinion_id in opinion_ids for item in request.units)
        and all(item.judge_ids for item in request.opinions)
        and all(
            fullmatch(_FINGERPRINT_PATTERN, item.text_fingerprint) is not None
            and set(item.required_dependency_unit_ids).issubset(unit_ids)
            and item.unit_id not in item.required_dependency_unit_ids
            for item in request.units
        )
    )


def _assignment_valid(request: HKCaseSemanticTaskRequest) -> bool:
    primary_ids = tuple(item.unit_id for item in request.units if item.primary)
    assigned = request.assigned_primary_unit_ids
    expected_order = tuple(item for item in primary_ids if item in set(assigned))
    packet_shape_valid = (
        request.packet_id is not None
        if request.request_kind in _PACKET_KINDS
        else request.packet_id is None
    )
    return bool(assigned) and assigned == expected_order and packet_shape_valid


def _supplied_evidence_valid(request: HKCaseSemanticTaskRequest) -> bool:
    units_by_id = {item.unit_id: item for item in request.units}
    supplied = {item.unit_id: item for item in request.supplied_units}
    required_supplied_ids = set(request.assigned_primary_unit_ids) | {
        item.dependency_unit_id for item in request.dependencies
    }
    if set(supplied) != required_supplied_ids or not supplied:
        return False
    for unit_id, item in supplied.items():
        manifest = units_by_id.get(unit_id)
        if (
            manifest is None
            or _raw_fingerprint(item.exact_text.encode("utf-8")) != manifest.text_fingerprint
        ):
            return False
    ranges_by_unit: dict[str, list[HKCaseSemanticEvidenceRange]] = {}
    for item in request.evidence_ranges:
        unit = supplied.get(item.unit_id)
        if unit is None or not _range_valid(unit.exact_text, item):
            return False
        ranges_by_unit.setdefault(item.unit_id, []).append(item)
    return all(unit_id in ranges_by_unit for unit_id in required_supplied_ids)


def _range_valid(text: str, item: HKCaseSemanticEvidenceRange) -> bool:
    raw = text.encode("utf-8")
    if item.start_byte < 0 or item.end_byte <= item.start_byte or item.end_byte > len(raw):
        return False
    try:
        selected = raw[item.start_byte : item.end_byte].decode("utf-8")
    except UnicodeDecodeError:
        return False
    return _raw_fingerprint(selected.encode("utf-8")) == item.exact_text_fingerprint


def _dependencies_valid(request: HKCaseSemanticTaskRequest) -> bool:
    units_by_id = {item.unit_id: item for item in request.units}
    dependencies = {
        (item.assigned_unit_id, item.dependency_unit_id): item for item in request.dependencies
    }
    for assigned_id in request.assigned_primary_unit_ids:
        assigned = units_by_id.get(assigned_id)
        if assigned is None:
            return False
        for dependency_id in assigned.required_dependency_unit_ids:
            if dependency_id in request.assigned_primary_unit_ids:
                continue
            dependency = dependencies.get((assigned_id, dependency_id))
            dependency_unit = units_by_id.get(dependency_id)
            if (
                dependency is None
                or dependency_unit is None
                or dependency.dependency_text_fingerprint != dependency_unit.text_fingerprint
            ):
                return False
    return all(
        item.assigned_unit_id in request.assigned_primary_unit_ids
        and item.dependency_unit_id in units_by_id
        and item.dependency_unit_id
        in units_by_id[item.assigned_unit_id].required_dependency_unit_ids
        for item in request.dependencies
    )


def _prior_stage_valid(request: HKCaseSemanticTaskRequest) -> bool:
    proposal_required = request.task_family is HKCaseSemanticTaskFamily.CHALLENGE or (
        request.request_kind
        in {
            HKCaseSemanticRequestKind.JUDGMENT_INTEGRATION,
            HKCaseSemanticRequestKind.TARGETED_REANALYSIS,
        }
    )
    objection_required = request.request_kind in {
        HKCaseSemanticRequestKind.FINAL_TARGETED_CHALLENGE,
        HKCaseSemanticRequestKind.TARGETED_REANALYSIS,
    }
    return (request.validated_proposal_fingerprint is not None) == proposal_required and (
        request.reconciled_objection_fingerprint is not None
    ) == objection_required


def _constraints_valid(request: HKCaseSemanticTaskRequest) -> bool:
    return (
        not request.source_text_is_instruction
        and not request.external_tools_permitted
        and not request.hidden_reference_included
        and not request.confidence_score_requested
        and set(request.required_evidence_role_codes) == set(_REQUIRED_EVIDENCE_ROLE_CODES)
        and not _duplicates(request.required_evidence_role_codes)
        and set(request.allowed_object_ids)
        == {item.unit_id for item in request.supplied_units}
        | {item.range_id for item in request.evidence_ranges}
        and not _duplicates(request.allowed_object_ids)
    )


def _complete_assignment(request: HKCaseSemanticTaskRequest) -> bool:
    return request.assigned_primary_unit_ids == tuple(
        item.unit_id for item in request.units if item.primary
    )


def _has_duplicate_identity(request: HKCaseSemanticTaskRequest) -> bool:
    groups: tuple[tuple[object, ...], ...] = (
        tuple(item.component_role for item in request.workflow_components),
        tuple(item.opinion_id for item in request.opinions),
        tuple(item.unit_id for item in request.units),
        request.assigned_primary_unit_ids,
        tuple(item.unit_id for item in request.supplied_units),
        tuple(item.range_id for item in request.evidence_ranges),
        tuple((item.assigned_unit_id, item.dependency_unit_id) for item in request.dependencies),
    )
    return any(_duplicates(group) for group in groups) or any(
        _duplicates(item.judge_ids) for item in request.opinions
    )


def hk_case_semantic_task_request_document(
    request: HKCaseSemanticTaskRequest,
) -> dict[str, JsonValue]:
    """Return the canonical JSON-compatible request projection."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-task-request",
        "schema_version": HK_CASE_SEMANTIC_TASK_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_TASK_RULE_ID,
        "task_family": request.task_family.value,
        "request_kind": request.request_kind.value,
        "execution_id": request.execution_id,
        "attempt_id": request.attempt_id,
        "packet_id": request.packet_id,
        "judgment_work_id": request.judgment_work_id,
        "workflow_components": [
            {"component_role": item.component_role, "fingerprint": item.fingerprint}
            for item in request.workflow_components
        ],
        "judicial_decision_id": request.judicial_decision_id,
        "official_version_id": request.official_version_id,
        "artifact_fingerprint": request.artifact_fingerprint,
        "source_snapshot_fingerprint": request.source_snapshot_fingerprint,
        "cutoff": request.cutoff,
        "court": request.court,
        "decision_date": request.decision_date,
        "citation": request.citation,
        "original_language": request.original_language.value,
        "opinions": [
            {
                "opinion_id": item.opinion_id,
                "source_order": item.source_order,
                "role": item.role.value,
                "judge_ids": list(item.judge_ids),
            }
            for item in request.opinions
        ],
        "units": [
            {
                "unit_id": item.unit_id,
                "opinion_id": item.opinion_id,
                "source_order": item.source_order,
                "primary": item.primary,
                "text_fingerprint": item.text_fingerprint,
                "required_dependency_unit_ids": list(item.required_dependency_unit_ids),
            }
            for item in request.units
        ],
        "assigned_primary_unit_ids": list(request.assigned_primary_unit_ids),
        "supplied_units": [
            {"unit_id": item.unit_id, "exact_text": item.exact_text}
            for item in request.supplied_units
        ],
        "evidence_ranges": [
            {
                "range_id": item.range_id,
                "unit_id": item.unit_id,
                "start_byte": item.start_byte,
                "end_byte": item.end_byte,
                "exact_text_fingerprint": item.exact_text_fingerprint,
            }
            for item in request.evidence_ranges
        ],
        "dependencies": [
            {
                "assigned_unit_id": item.assigned_unit_id,
                "dependency_unit_id": item.dependency_unit_id,
                "dependency_text_fingerprint": item.dependency_text_fingerprint,
            }
            for item in request.dependencies
        ],
        "allowed_object_ids": list(request.allowed_object_ids),
        "required_evidence_role_codes": list(request.required_evidence_role_codes),
        "output_budget_bytes": request.output_budget_bytes,
        "validated_proposal_fingerprint": request.validated_proposal_fingerprint,
        "reconciled_objection_fingerprint": request.reconciled_objection_fingerprint,
        "source_text_is_instruction": request.source_text_is_instruction,
        "external_tools_permitted": request.external_tools_permitted,
        "hidden_reference_included": request.hidden_reference_included,
        "confidence_score_requested": request.confidence_score_requested,
        "source_evidence_available": request.source_evidence_available,
    }


def hk_case_semantic_task_result_document(
    result: HKCaseSemanticTaskResult,
) -> dict[str, JsonValue]:
    """Return one canonical JSON-compatible preflight result."""
    return {
        "schema_id": "asklegal.hk-cases.semantic-task-result",
        "schema_version": HK_CASE_SEMANTIC_TASK_CONTRACT_VERSION,
        "rule_id": HK_CASE_SEMANTIC_TASK_RULE_ID,
        "request_fingerprint": result.request_fingerprint,
        "outcome": result.outcome.value,
        "reasons": [item.value for item in result.reasons],
        "opinion_count": result.opinion_count,
        "unit_count": result.unit_count,
        "primary_unit_count": result.primary_unit_count,
        "assigned_primary_unit_count": result.assigned_primary_unit_count,
        "supplied_unit_count": result.supplied_unit_count,
        "evidence_range_count": result.evidence_range_count,
        "dependency_count": result.dependency_count,
        "complete_judgment_assignment": result.complete_judgment_assignment,
        "provider_call_authorized": result.provider_call_authorized,
        "semantic_result_accepted": result.semantic_result_accepted,
        "search_records_created": result.search_records_created,
        "release_eligible": result.release_eligible,
        "external_effects": result.external_effects,
    }


def hk_case_semantic_task_request_from_document(document: object) -> HKCaseSemanticTaskRequest:
    """Strictly decode one request and reject unknown or malformed fields."""
    root = _object(document)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "task_family",
            "request_kind",
            "execution_id",
            "attempt_id",
            "packet_id",
            "judgment_work_id",
            "workflow_components",
            "judicial_decision_id",
            "official_version_id",
            "artifact_fingerprint",
            "source_snapshot_fingerprint",
            "cutoff",
            "court",
            "decision_date",
            "citation",
            "original_language",
            "opinions",
            "units",
            "assigned_primary_unit_ids",
            "supplied_units",
            "evidence_ranges",
            "dependencies",
            "allowed_object_ids",
            "required_evidence_role_codes",
            "output_budget_bytes",
            "validated_proposal_fingerprint",
            "reconciled_objection_fingerprint",
            "source_text_is_instruction",
            "external_tools_permitted",
            "hidden_reference_included",
            "confidence_score_requested",
            "source_evidence_available",
        },
    )
    _constant(root["schema_id"], "asklegal.hk-cases.semantic-task-request")
    _constant(root["schema_version"], HK_CASE_SEMANTIC_TASK_CONTRACT_VERSION)
    _constant(root["rule_id"], HK_CASE_SEMANTIC_TASK_RULE_ID)
    return HKCaseSemanticTaskRequest(
        task_family=_enum(root["task_family"], HKCaseSemanticTaskFamily),
        request_kind=_enum(root["request_kind"], HKCaseSemanticRequestKind),
        execution_id=_identity(root["execution_id"]),
        attempt_id=_identity(root["attempt_id"]),
        packet_id=_optional_identity(root["packet_id"]),
        judgment_work_id=_identity(root["judgment_work_id"]),
        workflow_components=tuple(
            _workflow_component(item) for item in _array(root["workflow_components"])
        ),
        judicial_decision_id=_identity(root["judicial_decision_id"]),
        official_version_id=_identity(root["official_version_id"]),
        artifact_fingerprint=_fingerprint(root["artifact_fingerprint"]),
        source_snapshot_fingerprint=_fingerprint(root["source_snapshot_fingerprint"]),
        cutoff=_string(root["cutoff"]),
        court=_string(root["court"]),
        decision_date=_string(root["decision_date"]),
        citation=_string(root["citation"]),
        original_language=_enum(root["original_language"], HKCaseOriginalLanguage),
        opinions=tuple(_opinion(item) for item in _array(root["opinions"])),
        units=tuple(_unit(item) for item in _array(root["units"])),
        assigned_primary_unit_ids=_identities(root["assigned_primary_unit_ids"]),
        supplied_units=tuple(_supplied_unit(item) for item in _array(root["supplied_units"])),
        evidence_ranges=tuple(_evidence_range(item) for item in _array(root["evidence_ranges"])),
        dependencies=tuple(_dependency(item) for item in _array(root["dependencies"])),
        allowed_object_ids=_identities(root["allowed_object_ids"]),
        required_evidence_role_codes=_codes(root["required_evidence_role_codes"]),
        output_budget_bytes=_positive_integer(root["output_budget_bytes"]),
        validated_proposal_fingerprint=_optional_fingerprint(
            root["validated_proposal_fingerprint"]
        ),
        reconciled_objection_fingerprint=_optional_fingerprint(
            root["reconciled_objection_fingerprint"]
        ),
        source_text_is_instruction=_boolean(root["source_text_is_instruction"]),
        external_tools_permitted=_boolean(root["external_tools_permitted"]),
        hidden_reference_included=_boolean(root["hidden_reference_included"]),
        confidence_score_requested=_boolean(root["confidence_score_requested"]),
        source_evidence_available=_boolean(root["source_evidence_available"]),
    )


def _workflow_component(value: JsonValue) -> HKCaseSemanticWorkflowComponent:
    root = _object(value)
    _exact_keys(root, {"component_role", "fingerprint"})
    return HKCaseSemanticWorkflowComponent(
        _code(root["component_role"]),
        _fingerprint(root["fingerprint"]),
    )


def _opinion(value: JsonValue) -> HKCaseSemanticOpinionManifest:
    root = _object(value)
    _exact_keys(root, {"opinion_id", "source_order", "role", "judge_ids"})
    return HKCaseSemanticOpinionManifest(
        _identity(root["opinion_id"]),
        _positive_integer(root["source_order"]),
        _enum(root["role"], HKCaseOpinionRole),
        _identities(root["judge_ids"]),
    )


def _unit(value: JsonValue) -> HKCaseSemanticUnitManifest:
    root = _object(value)
    _exact_keys(
        root,
        {
            "unit_id",
            "opinion_id",
            "source_order",
            "primary",
            "text_fingerprint",
            "required_dependency_unit_ids",
        },
    )
    return HKCaseSemanticUnitManifest(
        _identity(root["unit_id"]),
        _identity(root["opinion_id"]),
        _positive_integer(root["source_order"]),
        _boolean(root["primary"]),
        _fingerprint(root["text_fingerprint"]),
        _identities(root["required_dependency_unit_ids"]),
    )


def _supplied_unit(value: JsonValue) -> HKCaseSemanticSuppliedUnit:
    root = _object(value)
    _exact_keys(root, {"unit_id", "exact_text"})
    return HKCaseSemanticSuppliedUnit(
        _identity(root["unit_id"]),
        _string(root["exact_text"]),
    )


def _evidence_range(value: JsonValue) -> HKCaseSemanticEvidenceRange:
    root = _object(value)
    _exact_keys(
        root,
        {"range_id", "unit_id", "start_byte", "end_byte", "exact_text_fingerprint"},
    )
    return HKCaseSemanticEvidenceRange(
        _identity(root["range_id"]),
        _identity(root["unit_id"]),
        _nonnegative_integer(root["start_byte"]),
        _positive_integer(root["end_byte"]),
        _fingerprint(root["exact_text_fingerprint"]),
    )


def _dependency(value: JsonValue) -> HKCaseSemanticDependency:
    root = _object(value)
    _exact_keys(
        root,
        {"assigned_unit_id", "dependency_unit_id", "dependency_text_fingerprint"},
    )
    return HKCaseSemanticDependency(
        _identity(root["assigned_unit_id"]),
        _identity(root["dependency_unit_id"]),
        _fingerprint(root["dependency_text_fingerprint"]),
    )


def _object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if not isinstance(checked, dict):
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT)
    return checked


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT)
    return value


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT)


def _string(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT)
    return value


def _identity(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_IDENTITY_PATTERN, result) is None:
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.IDENTITY)
    return result


def _identities(value: JsonValue) -> tuple[str, ...]:
    return tuple(_identity(item) for item in _array(value))


def _code(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_CODE_PATTERN, result) is None:
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT)
    return result


def _codes(value: JsonValue) -> tuple[str, ...]:
    return tuple(_code(item) for item in _array(value))


def _fingerprint(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.FINGERPRINT)
    return result


def _optional_fingerprint(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _fingerprint(value)


def _optional_identity(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _identity(value)


def _positive_integer(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT)
    return value


def _nonnegative_integer(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT)
    return value


def _boolean(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT)
    return value


def _constant(value: JsonValue, expected: str) -> None:
    if value != expected:
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT)


def _enum[T: StrEnum](value: JsonValue, enum_type: type[T]) -> T:
    raw = _string(value)
    try:
        return enum_type(raw)
    except ValueError:
        raise HKCaseSemanticTaskError(HKCaseSemanticTaskErrorCode.CONTRACT) from None


def _raw_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _duplicates(values: tuple[object, ...]) -> bool:
    return len(set(values)) != len(values)
