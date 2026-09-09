"""Pure Hong Kong V1 due-source cycle policy and canonical report contracts.

This module deliberately knows no connector, vault, application, or endpoint.
The acquisition worker supplies the checked-in Matrix and register facts, then
uses these immutable contracts to derive every periodic source role.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Never
from weakref import ReferenceType, ref

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

from asklegal_reporting.hk_v1_coverage import (
    CoverageMatrixRow,
    FamilyAcquisitionCoverage,
    HongKongV1CoverageMatrix,
    is_hk_v1_coverage_matrix_issued,
    is_hk_v1_coverage_matrix_policy_approved,
)


class HongKongV1DueCycleError(ValueError):
    """One closed due-cycle policy or canonical-report error."""


@dataclass(frozen=True, slots=True)
class TwoFamilyAcquisitionProjection:
    """The two exact complete acquisition facts allowed to reach proposal assembly."""

    observation_cutoff: str
    acquisitions: tuple[FamilyAcquisitionCoverage, ...]


class DueCycleKind(StrEnum):
    """The only recurring V1 source cycles."""

    DAILY_CURRENT_LAW = "DAILY_CURRENT_LAW"
    WEEKLY_RELEASE = "WEEKLY_RELEASE"
    MONTHLY_CROSS_CHECK = "MONTHLY_CROSS_CHECK"
    FULL_PERIODIC = "FULL_PERIODIC"


_V1_INCLUDED_MATERIAL_FAMILIES = frozenset({"LEGISLATION", "CASES"})
_V1_CURRENT_REGISTER_IDS = frozenset(
    {
        "hcr_000000000000000000000000000000000000000000000001",
        "hsr_000000000000000000000000000000000000000000000001",
    }
)
_HISTORICAL_REGISTER_COUNT = 3
_PAIR_LENGTH = 2
_TERMINAL_ARTIFACT_LENGTH = 4
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,159}$")
_OPERATING_STATES = frozenset({"CONFIGURED", "PARTIALLY_CONFIGURED", "BLOCKED", "OUT_OF_SCOPE_V1"})
_MATERIAL_FAMILIES = frozenset({"LEGISLATION", "CASES", "REGULATORY"})
_OUTAGE_IMPACTS = frozenset({"RELEASE_BLOCKING", "AFFECTED_WORK_BLOCKING", "NONBLOCKING"})
_LOCAL_VAULTS = frozenset({"PRIMARY", "RECOVERY"})
_DUE_LOCAL_VERSION = re.compile(r"^v[0-9a-f]{64}$")
_DUE_S3_VERSION = re.compile(r"^s3v_[A-Za-z0-9_-]{1,684}$")
_MAX_S3_PROVIDER_VERSION_BYTES = 512
_FIRST_PRINTABLE_CODEPOINT = 0x20
_KEY_HEX_CHUNK_BYTES = 56
_ADMISSION_STATES = frozenset({"ADMITTED", "NOT_ADMITTED"})
_TWO_FAMILY_LEGISLATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "cycle_id",
        "observation_cutoff",
        "scope_dispositions",
        "verified_item_refs",
        "review_issue_refs",
        "journal_head_fingerprint",
        "source_register_fingerprint",
        "source_baseline_fingerprint",
        "work_plan_fingerprint",
        "result",
        "fingerprint",
    }
)
_TWO_FAMILY_SCOPE_FIELDS = frozenset(
    {
        "scope_id",
        "required_item_count",
        "verified_item_count",
        "retryable_item_count",
        "rejected_item_count",
        "result",
    }
)
_TWO_FAMILY_CASES_FIELDS = frozenset(
    {
        "cycle_id",
        "discrepancy_refs",
        "earliest_decision_date",
        "fingerprint",
        "journal_head_fingerprint",
        "judgment_bundle_refs",
        "observation_cutoff",
        "result",
        "year_dispositions",
    }
)
_TWO_FAMILY_YEAR_FIELDS = frozenset(
    {
        "discovered_judgments",
        "final_page",
        "first_in_scope_date",
        "result",
        "retryable_items",
        "verified_judgments",
        "verified_listing_pages",
        "year",
    }
)
_TWO_FAMILY_LEGISLATION_SCOPES = (
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_TWO_FAMILY_EARLIEST_CASE_YEAR = 1997
_TWO_FAMILY_EARLIEST_CASE_DATE = datetime(1997, 7, 1, tzinfo=UTC)
_TWO_FAMILY_LEGISLATION_CYCLE = re.compile(r"^cyc_[A-Za-z0-9_-]{3,123}$")
_TWO_FAMILY_LEGISLATION_CUTOFF = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00$"
)
_TWO_FAMILY_LEGISLATION_REF = re.compile(
    r"^legislation-item/[a-z0-9][a-z0-9._-]{2,159}/[0-9a-f]{64}$"
)
_TWO_FAMILY_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,1023}$")
_REGISTER_SCHEMAS: dict[str, tuple[frozenset[str], frozenset[str], tuple[str, ...]]] = {
    "https://contracts.asklegal.local/v1/hk-legislation-source-register.schema.json": (
        frozenset(
            {
                "schema_id",
                "schema_version",
                "register_id",
                "register_version",
                "effective_date",
                "status",
                "fingerprint",
                "authorization",
                "legal_clearance",
                "rights_evidence",
                "sources",
                "endpoints",
            }
        ),
        frozenset(
            {
                "source_id",
                "registered_source_id",
                "version",
                "endpoint_ids",
                "rights_state",
                "operational_state",
                "outage_impact",
                "rights_evidence_ids",
                "blockers",
            }
        ),
        (
            "HK-LEG-HKEL-CURRENT-INVENTORY",
            "HK-LEG-HKEL-CURRENT-DATA",
            "HK-LEG-HKEL-VERIFIED-COPIES",
            "HK-LEG-HKEL-ASSISTED-COPIES",
            "HK-LEG-HKEL-PAST-INVENTORY",
            "HK-LEG-HKEL-PAST-DATA",
            "HK-LEG-HKEL-EDITORIAL-RECORDS",
            "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
            "HK-LEG-GLD-EGAZETTE",
            "HK-LEG-OFFICIAL-GAZETTE-ARCHIVE",
            "HK-LEG-HKEL-GAZETTE-BACKCAPTURE",
            "HK-LEG-BASIC-LAW-PORTAL",
            "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
            "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
        ),
    ),
    "https://contracts.asklegal.local/v1/hk-cases-source-register.schema.json": (
        frozenset(
            {
                "schema_id",
                "schema_version",
                "register_id",
                "register_version",
                "effective_date",
                "status",
                "fingerprint",
                "access_boundary",
                "sources",
                "endpoints",
            }
        ),
        frozenset(
            {
                "source_id",
                "registered_source_id",
                "version",
                "endpoint_ids",
                "rights_state",
                "operational_state",
                "outage_impact",
                "fact_authority",
                "completeness_authority",
                "blockers",
            }
        ),
        (
            "HK-CASE-COURT-REGISTRY",
            "HK-CASE-HKLII-DISCOVERY",
            "HK-CASE-JUDICIARY-JUDGMENT",
            "HK-CASE-JUDICIARY-LIBRARY",
            "HK-CASE-JUDICIARY-LRS-INVENTORY",
            "HK-CASE-JUDICIARY-TRANSLATION",
            "HK-CASE-PRIVY-COUNCIL",
        ),
    ),
    "https://contracts.asklegal.local/v1/hk-regulatory-source-register.schema.json": (
        frozenset(
            {
                "schema_id",
                "schema_version",
                "register_id",
                "register_version",
                "effective_date",
                "status",
                "fingerprint",
                "access_boundary",
                "sources",
                "endpoints",
            }
        ),
        frozenset(
            {
                "source_id",
                "registered_source_id",
                "version",
                "source_policy_owner",
                "endpoint_ids",
                "rights_state",
                "operational_state",
                "outage_consequence",
                "fact_authority",
                "completeness_authority",
                "blockers",
            }
        ),
        (
            "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
            "HK-REG-HKEX-FEES-RULES",
            "HK-REG-HKEX-REGULATORY-FORMS",
            "HK-REG-HKEX-RULE-UPDATES",
            "HK-REG-HKEX-RULEBOOK-CATALOGUE",
        ),
    ),
}
_DUE_CADENCES = frozenset(
    {
        "DAILY_AND_COMPLETE_AT_CYCLE_CUTOFF",
        "DAILY_AND_COMPLETE_WITHIN_24_HOURS_OF_CUTOFF",
        "DAILY_DISCOVERY",
        "DAILY_INVENTORY_AND_ON_CHANGE_ACQUISITION",
        "DAILY_SIGNAL_AND_ON_CHANGE_ACQUISITION",
        "WEEKLY",
        "WEEKLY_AND_EVENT_TRIGGERED",
        "MONTHLY_AND_EVENT_TRIGGERED",
        "MONTHLY_EVENT_TRIGGERED_AND_ON_DEMAND",
    }
)


class DueTerminalOutcome(StrEnum):
    """Acquisition terminal state, separate from legal or release conclusions."""

    COMPLETE = "COMPLETE"
    INCOMPLETE_OBSERVATION = "INCOMPLETE_OBSERVATION"
    FAILED = "FAILED"
    GAP = "GAP"


class DueChangeStatus(StrEnum):
    """Closed source change status attached to every terminal."""

    BASELINE = "BASELINE"
    NO_CHANGE = "NO_CHANGE"
    CHANGED = "CHANGED"
    NOT_PROVED = "NOT_PROVED"


@dataclass(frozen=True, slots=True)
class DueSourceRegister:
    """One source role as supplied by one verified checked-in register."""

    source_id: str
    source_version: str
    endpoint_ids: tuple[str, ...]
    operational_state: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject a forged register-source primitive projection."""
        _validate_source_register(self)


def _validate_source_register(source: DueSourceRegister) -> None:
    _identity(source.source_id, "REGISTER_BUNDLE_INVALID")
    _exact_text(source.source_version, "REGISTER_BUNDLE_INVALID")
    _validate_sorted_text_tuple(source.endpoint_ids, "REGISTER_BUNDLE_INVALID")
    if (
        type(source.operational_state) is not str
        or source.operational_state not in _OPERATING_STATES
    ):
        _fail("REGISTER_BUNDLE_INVALID")
    _validate_sorted_text_tuple(source.blockers, "REGISTER_BUNDLE_INVALID")
    if source.operational_state == "CONFIGURED":
        if not source.endpoint_ids or source.blockers:
            _fail("REGISTER_BUNDLE_INVALID")
    elif not source.blockers:
        _fail("REGISTER_BUNDLE_INVALID")


def _validate_sorted_text_tuple(value: tuple[object, ...], code: str) -> None:
    """Validate leaves before any operation that needs equality, hashing, or order."""
    if type(value) is not tuple:
        _fail(code)
    validated: list[str] = []
    for item in value:
        _exact_text(item, code)
        if type(item) is not str:
            _fail(code)
        validated.append(item)
    if value != tuple(sorted(set(validated))):
        _fail(code)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class DueRegisterBundle:
    """The identifying facts of one Matrix-owning source register."""

    register_id: str
    register_version: str
    register_fingerprint: str
    sources: tuple[DueSourceRegister, ...]

    def __post_init__(self) -> None:
        """Validate all primitive bundle facts before they influence a plan."""
        _validate_register_bundle(self)


_IssuedRegisterRegistration = tuple[ReferenceType[DueRegisterBundle], bytes]
_ISSUED_REGISTERS: dict[int, _IssuedRegisterRegistration] = {}


def parse_hk_v1_due_register_bundle(content: bytes) -> DueRegisterBundle:
    """Project one fingerprint-verified checked-in Hong Kong source register."""
    try:
        document = parse_json_bytes(content, max_bytes=1_000_000)
        if not isinstance(document, dict):
            _fail("REGISTER_BUNDLE_INVALID")
        schema_id = _json_text_with_code(document, "schema_id", "REGISTER_BUNDLE_INVALID")
        schema = _REGISTER_SCHEMAS.get(schema_id)
        if schema is None:
            _fail("REGISTER_BUNDLE_INVALID")
        expected, source_fields, source_order = schema
        if frozenset(document) != expected:
            _fail("REGISTER_BUNDLE_INVALID")
        declared = _json_text_with_code(document, "fingerprint", "REGISTER_BUNDLE_INVALID")
        unsigned = dict(document)
        del unsigned["fingerprint"]
        if declared != _fingerprint(unsigned):
            _fail("REGISTER_BUNDLE_INVALID")
        sources_value = document["sources"]
        if not isinstance(sources_value, list):
            _fail("REGISTER_BUNDLE_INVALID")
        sources = tuple(
            _register_source_from_document(value, source_fields) for value in sources_value
        )
        if tuple(source.source_id for source in sources) != source_order:
            _fail("REGISTER_BUNDLE_INVALID")
        bundle = DueRegisterBundle(
            _json_text_with_code(document, "register_id", "REGISTER_BUNDLE_INVALID"),
            _json_text_with_code(document, "register_version", "REGISTER_BUNDLE_INVALID"),
            declared,
            sources,
        )
    except (ContractViolation, KeyError, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        code = "REGISTER_BUNDLE_INVALID"
        raise HongKongV1DueCycleError(code) from error
    return _issue_register_bundle(bundle)


def _register_source_from_document(
    value: JsonValue,
    expected_fields: frozenset[str],
) -> DueSourceRegister:
    if not isinstance(value, dict) or frozenset(value) != expected_fields:
        _fail("REGISTER_BUNDLE_INVALID")
    return DueSourceRegister(
        _json_text_with_code(value, "source_id", "REGISTER_BUNDLE_INVALID"),
        _json_text_with_code(value, "version", "REGISTER_BUNDLE_INVALID"),
        _json_text_tuple_with_code(value, "endpoint_ids", "REGISTER_BUNDLE_INVALID"),
        _json_text_with_code(value, "operational_state", "REGISTER_BUNDLE_INVALID"),
        _json_text_tuple_with_code(value, "blockers", "REGISTER_BUNDLE_INVALID"),
    )


def _issue_register_bundle(bundle: DueRegisterBundle) -> DueRegisterBundle:
    bundle_id = id(bundle)

    def cleanup(dead: ReferenceType[DueRegisterBundle]) -> None:
        current = _ISSUED_REGISTERS.get(bundle_id)
        if current is not None and current[0] is dead:
            del _ISSUED_REGISTERS[bundle_id]

    issued_reference = ref(bundle, cleanup)
    _ISSUED_REGISTERS[bundle_id] = (issued_reference, _register_bundle_snapshot(bundle))
    return bundle


def _assert_issued_register_bundle(bundle: object) -> DueRegisterBundle:
    if type(bundle) is not DueRegisterBundle:
        _fail("REGISTER_BUNDLE_PROVENANCE_INVALID")
    _validate_register_bundle(bundle)
    registration = _ISSUED_REGISTERS.get(id(bundle))
    if registration is None or registration[0]() is not bundle:
        _fail("REGISTER_BUNDLE_PROVENANCE_INVALID")
    if registration[1] != _register_bundle_snapshot(bundle):
        _fail("REGISTER_BUNDLE_PROVENANCE_INVALID")
    return bundle


def _register_bundle_snapshot(bundle: DueRegisterBundle) -> bytes:
    return canonicalize(checked_json_value(_register_body(bundle)))


def _validate_register_bundle(bundle: DueRegisterBundle) -> None:
    _identity(bundle.register_id, "REGISTER_BUNDLE_INVALID")
    _exact_text(bundle.register_version, "REGISTER_BUNDLE_INVALID")
    _fingerprint_text(bundle.register_fingerprint, "REGISTER_BUNDLE_INVALID")
    if type(bundle.sources) is not tuple or not bundle.sources:
        _fail("REGISTER_BUNDLE_INVALID")
    if any(type(source) is not DueSourceRegister for source in bundle.sources):
        _fail("REGISTER_BUNDLE_INVALID")
    for source in bundle.sources:
        _validate_source_register(source)
    if len({source.source_id for source in bundle.sources}) != len(bundle.sources):
        _fail("REGISTER_BUNDLE_INVALID")


@dataclass(frozen=True, slots=True)
class HongKongV1DueCycleInstruction:
    """Closed control-to-acquisition instruction with no due-list or priors."""

    cycle_id: str
    cycle_kind: DueCycleKind
    scheduled_at: str
    observation_cutoff: str
    matrix_revision: str
    matrix_fingerprint: str

    def __post_init__(self) -> None:
        """Validate direct construction as strictly as the JSON boundary."""
        if type(self.cycle_kind) is not DueCycleKind:
            _fail("CYCLE_KIND_INVALID")
        _identity(self.cycle_id, "CYCLE_INSTRUCTION_INVALID")
        _utc(self.scheduled_at, "CYCLE_INSTRUCTION_INVALID")
        _utc(self.observation_cutoff, "CYCLE_INSTRUCTION_INVALID")
        _exact_text(self.matrix_revision, "CYCLE_INSTRUCTION_INVALID")
        _fingerprint_text(self.matrix_fingerprint, "CYCLE_INSTRUCTION_INVALID")

    @classmethod
    def from_json(cls, value: object) -> HongKongV1DueCycleInstruction:
        """Parse only the exact control-owned instruction projection."""
        document = _object(value, "CYCLE_INSTRUCTION_INVALID")
        if frozenset(document) != frozenset(
            {
                "cycle_id",
                "cycle_kind",
                "scheduled_at",
                "observation_cutoff",
                "matrix_revision",
                "matrix_fingerprint",
            }
        ):
            _fail("CYCLE_INSTRUCTION_INVALID")
        try:
            return cls(
                _text(document, "cycle_id"),
                DueCycleKind(_text(document, "cycle_kind")),
                _text(document, "scheduled_at"),
                _text(document, "observation_cutoff"),
                _text(document, "matrix_revision"),
                _text(document, "matrix_fingerprint"),
            )
        except ValueError as error:
            code = "CYCLE_INSTRUCTION_INVALID"
            raise HongKongV1DueCycleError(code) from error


@dataclass(frozen=True, slots=True)
class HongKongV1DueRequirement:
    """One Matrix-derived source-role requirement, including a visible conflict."""

    material_family: str
    source_id: str
    source_version: str
    cadence: str
    outage_impact: str
    register_id: str
    register_version: str
    register_fingerprint: str
    matrix_policy_fingerprint: str
    policy_conflict: str | None
    result_schema: str
    technical_state: str
    rights_state: str

    def __post_init__(self) -> None:
        """Keep direct requirements as strict as derived requirements."""
        for value in (self.material_family, self.source_version, self.cadence, self.outage_impact):
            _exact_text(value, "DUE_REQUIREMENT_INVALID")
        for value in (self.source_id, self.register_id):
            _identity(value, "DUE_REQUIREMENT_INVALID")
        _exact_text(self.register_version, "DUE_REQUIREMENT_INVALID")
        if (
            self.material_family not in _MATERIAL_FAMILIES
            or self.cadence not in _DUE_CADENCES
            or self.outage_impact not in _OUTAGE_IMPACTS
        ):
            _fail("DUE_REQUIREMENT_INVALID")
        for value in (
            self.register_fingerprint,
            self.matrix_policy_fingerprint,
        ):
            _fingerprint_text(value, "DUE_REQUIREMENT_INVALID")
        if self.policy_conflict is not None and type(self.policy_conflict) is not str:
            _fail("DUE_REQUIREMENT_INVALID")
        if self.policy_conflict not in {None, "SOURCE_ROLE_POLICY_CONFLICT"}:
            _fail("DUE_REQUIREMENT_INVALID")
        _exact_text(self.result_schema, "DUE_REQUIREMENT_INVALID")
        if self.result_schema != _expected_result_schema(self.source_id):
            _fail("DUE_REQUIREMENT_INVALID")
        if type(self.technical_state) is not str or type(self.rights_state) is not str:
            _fail("DUE_REQUIREMENT_INVALID")
        if (
            self.technical_state not in _ADMISSION_STATES
            or self.rights_state not in _ADMISSION_STATES
        ):
            _fail("DUE_REQUIREMENT_INVALID")


def _rebuild_instruction(
    value: object,
    code: str,
) -> HongKongV1DueCycleInstruction:
    """Replay every control instruction leaf before it can control a plan."""
    if type(value) is not HongKongV1DueCycleInstruction:
        _fail(code)
    try:
        return HongKongV1DueCycleInstruction(
            value.cycle_id,
            value.cycle_kind,
            value.scheduled_at,
            value.observation_cutoff,
            value.matrix_revision,
            value.matrix_fingerprint,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(code) from error


def _rebuild_requirement(
    value: object,
    code: str,
) -> HongKongV1DueRequirement:
    """Replay every Matrix-derived requirement leaf before any trust boundary."""
    if type(value) is not HongKongV1DueRequirement:
        _fail(code)
    try:
        return HongKongV1DueRequirement(
            value.material_family,
            value.source_id,
            value.source_version,
            value.cadence,
            value.outage_impact,
            value.register_id,
            value.register_version,
            value.register_fingerprint,
            value.matrix_policy_fingerprint,
            value.policy_conflict,
            value.result_schema,
            value.technical_state,
            value.rights_state,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(code) from error


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HongKongV1DueCyclePlan:
    """Immutable matrix/register-derived plan for exactly one instruction."""

    instruction: HongKongV1DueCycleInstruction
    registers: tuple[DueRegisterBundle, ...]
    predecessor_fingerprint: str | None
    requirements: tuple[HongKongV1DueRequirement, ...]
    requirements_fingerprint: str
    plan_fingerprint: str

    def __post_init__(self) -> None:
        """Reject direct plan construction that is not self-consistent."""
        instruction, registers, requirements = _validate_plan_shape(self)
        _validate_plan_requirement_links(registers, requirements)
        expected = _plan_fingerprint(
            instruction,
            registers,
            self.requirements_fingerprint,
            self.predecessor_fingerprint,
        )
        if self.plan_fingerprint != expected:
            _fail("CYCLE_PLAN_INPUT_INVALID")


_IssuedPlanRegistration = tuple[ReferenceType[HongKongV1DueCyclePlan], bytes]
_ISSUED_PLANS: dict[int, _IssuedPlanRegistration] = {}
_PlanSnapshotRegistration = tuple[ReferenceType[HongKongV1DueCyclePlan], bytes]
_CYCLE_PLAN_SNAPSHOTS: dict[int, _PlanSnapshotRegistration] = {}


def _issued_plan_snapshot(plan: HongKongV1DueCyclePlan) -> bytes:
    return canonicalize(
        checked_json_value(
            {
                "instruction": _instruction_body(plan.instruction),
                "registers": [_register_body(register) for register in plan.registers],
                "predecessor_fingerprint": plan.predecessor_fingerprint,
                "requirements": [
                    _requirement_body(requirement) for requirement in plan.requirements
                ],
                "requirements_fingerprint": plan.requirements_fingerprint,
                "plan_fingerprint": plan.plan_fingerprint,
            }
        )
    )


def _issue_plan(plan: HongKongV1DueCyclePlan) -> HongKongV1DueCyclePlan:
    plan_id = id(plan)

    def cleanup(dead: ReferenceType[HongKongV1DueCyclePlan]) -> None:
        current = _ISSUED_PLANS.get(plan_id)
        if current is not None and current[0] is dead:
            del _ISSUED_PLANS[plan_id]

    _ISSUED_PLANS[plan_id] = (ref(plan, cleanup), _issued_plan_snapshot(plan))
    return plan


def _remember_cycle_plan_snapshot(
    plan: HongKongV1DueCyclePlan,
) -> HongKongV1DueCyclePlan:
    """Mark a private reconstructed plan copy for cycle-only consumption."""
    plan_id = id(plan)

    def cleanup(dead: ReferenceType[HongKongV1DueCyclePlan]) -> None:
        current = _CYCLE_PLAN_SNAPSHOTS.get(plan_id)
        if current is not None and current[0] is dead:
            del _CYCLE_PLAN_SNAPSHOTS[plan_id]

    _CYCLE_PLAN_SNAPSHOTS[plan_id] = (ref(plan, cleanup), _issued_plan_snapshot(plan))
    return plan


def _validate_plan_shape(
    plan: HongKongV1DueCyclePlan,
) -> tuple[
    HongKongV1DueCycleInstruction,
    tuple[DueRegisterBundle, ...],
    tuple[HongKongV1DueRequirement, ...],
]:
    instruction = _rebuild_instruction(plan.instruction, "CYCLE_PLAN_INPUT_INVALID")
    _validate_registers(
        plan.registers,
        current=len(plan.registers) == len(_V1_CURRENT_REGISTER_IDS),
    )
    if plan.registers != tuple(sorted(plan.registers, key=lambda item: item.register_id)):
        _fail("CYCLE_PLAN_INPUT_INVALID")
    if plan.predecessor_fingerprint is not None:
        _fingerprint_text(plan.predecessor_fingerprint, "CYCLE_PLAN_INPUT_INVALID")
    if type(plan.requirements) is not tuple or not plan.requirements:
        _fail("CYCLE_PLAN_INPUT_INVALID")
    requirements = tuple(
        _rebuild_requirement(item, "CYCLE_PLAN_INPUT_INVALID") for item in plan.requirements
    )
    if requirements != tuple(sorted(requirements, key=lambda item: item.source_id)):
        _fail("CYCLE_PLAN_INPUT_INVALID")
    if len({item.source_id for item in requirements}) != len(requirements):
        _fail("CYCLE_PLAN_INPUT_INVALID")
    _fingerprint_text(plan.requirements_fingerprint, "CYCLE_PLAN_INPUT_INVALID")
    _fingerprint_text(plan.plan_fingerprint, "CYCLE_PLAN_INPUT_INVALID")
    if plan.requirements_fingerprint != _fingerprint(
        [_requirement_body(item, "CYCLE_PLAN_INPUT_INVALID") for item in requirements]
    ):
        _fail("CYCLE_PLAN_INPUT_INVALID")
    return instruction, plan.registers, requirements


def _validate_plan_requirement_links(
    registers: tuple[DueRegisterBundle, ...],
    requirements: tuple[HongKongV1DueRequirement, ...],
) -> None:
    sources = _register_sources(registers)
    for requirement in requirements:
        register_source = sources.get(requirement.source_id)
        if register_source is None:
            _fail("CYCLE_PLAN_INPUT_INVALID")
        register, source = register_source
        if (
            requirement.source_version != source.source_version
            or requirement.register_id != register.register_id
            or requirement.register_version != register.register_version
            or requirement.register_fingerprint != register.register_fingerprint
        ):
            _fail("CYCLE_PLAN_INPUT_INVALID")


def derive_hk_v1_due_cycle_plan(
    instruction: HongKongV1DueCycleInstruction,
    matrix: HongKongV1CoverageMatrix,
    registers: tuple[DueRegisterBundle, ...],
    predecessor_fingerprint: str | None = None,
) -> HongKongV1DueCyclePlan:
    """Derive the frozen 4/6/1/7 two-family periodic role set from Matrix facts only."""
    if type(registers) is not tuple:
        _fail("REGISTER_BUNDLE_INVALID")
    for register in registers:
        _assert_issued_register_bundle(register)
    canonical_registers = _canonical_registers(registers)
    instruction = _validate_plan_inputs(
        instruction, matrix, canonical_registers, predecessor_fingerprint
    )
    included_material_families = frozenset(matrix.included_material_families)
    by_source = _register_sources(canonical_registers)
    rows_by_source: dict[str, list[CoverageMatrixRow]] = {}
    for row in matrix.rows:
        if row.material_family in included_material_families and _is_due_cadence(
            row.cadence, instruction.cycle_kind
        ):
            rows_by_source.setdefault(row.source_id, []).append(row)
    requirements = [
        _requirement(source_id, rows, by_source) for source_id, rows in rows_by_source.items()
    ]
    ordered = tuple(sorted(requirements, key=lambda item: item.source_id))
    expected_counts = {
        DueCycleKind.DAILY_CURRENT_LAW: 4,
        DueCycleKind.WEEKLY_RELEASE: 6,
        DueCycleKind.MONTHLY_CROSS_CHECK: 1,
        DueCycleKind.FULL_PERIODIC: 7,
    }
    if len(ordered) != expected_counts[instruction.cycle_kind]:
        _fail("DUE_SOURCE_SET_INVALID")
    requirement_fingerprint = _fingerprint([_requirement_body(item) for item in ordered])
    plan_fingerprint = _plan_fingerprint(
        instruction, canonical_registers, requirement_fingerprint, predecessor_fingerprint
    )
    return _issue_plan(
        HongKongV1DueCyclePlan(
            instruction,
            canonical_registers,
            predecessor_fingerprint,
            ordered,
            requirement_fingerprint,
            plan_fingerprint,
        )
    )


def _validate_plan_inputs(
    instruction: object,
    matrix: object,
    registers: tuple[DueRegisterBundle, ...],
    predecessor_fingerprint: object,
) -> HongKongV1DueCycleInstruction:
    if type(matrix) is not HongKongV1CoverageMatrix:
        _fail("CYCLE_PLAN_INPUT_INVALID")
    rebuilt_instruction = _rebuild_instruction(instruction, "CYCLE_PLAN_INPUT_INVALID")
    if not is_hk_v1_coverage_matrix_issued(matrix):
        _fail("MATRIX_PROVENANCE_INVALID")
    if not is_hk_v1_coverage_matrix_policy_approved(matrix):
        _fail("MATRIX_POLICY_INVALID")
    if frozenset(matrix.included_material_families) != _V1_INCLUDED_MATERIAL_FAMILIES:
        _fail("MATRIX_POLICY_INVALID")
    if (
        rebuilt_instruction.matrix_revision != matrix.revision
        or rebuilt_instruction.matrix_fingerprint != matrix.fingerprint
    ):
        _fail("MATRIX_POLICY_INVALID")
    _validate_registers(registers, current=True)
    for register in registers:
        _assert_issued_register_bundle(register)
    if predecessor_fingerprint is not None:
        _fingerprint_text(predecessor_fingerprint, "CYCLE_PLAN_INPUT_INVALID")
    return rebuilt_instruction


def _register_sources(
    registers: tuple[DueRegisterBundle, ...],
) -> dict[str, tuple[DueRegisterBundle, DueSourceRegister]]:
    by_source: dict[str, tuple[DueRegisterBundle, DueSourceRegister]] = {}
    for bundle in registers:
        if type(bundle) is not DueRegisterBundle:
            _fail("REGISTER_BUNDLE_INVALID")
        for source in bundle.sources:
            if type(source) is not DueSourceRegister or source.source_id in by_source:
                _fail("REGISTER_BUNDLE_INVALID")
            by_source[source.source_id] = (bundle, source)
    return by_source


def _validate_registers(registers: tuple[DueRegisterBundle, ...], *, current: bool = False) -> None:
    if len(registers) not in {len(_V1_CURRENT_REGISTER_IDS), _HISTORICAL_REGISTER_COUNT}:
        _fail("REGISTER_BUNDLE_INVALID")
    if any(type(item) is not DueRegisterBundle for item in registers):
        _fail("REGISTER_BUNDLE_INVALID")
    for register in registers:
        _validate_register_bundle(register)
    register_ids = {item.register_id for item in registers}
    if len(register_ids) != len(registers):
        _fail("REGISTER_BUNDLE_INVALID")
    if current and frozenset(register_ids) != _V1_CURRENT_REGISTER_IDS:
        _fail("REGISTER_BUNDLE_INVALID")


def _canonical_registers(
    registers: tuple[DueRegisterBundle, ...],
) -> tuple[DueRegisterBundle, ...]:
    return tuple(sorted(registers, key=lambda item: item.register_id))


def _plan_fingerprint(
    instruction: HongKongV1DueCycleInstruction,
    registers: tuple[DueRegisterBundle, ...],
    requirements_fingerprint: str,
    predecessor_fingerprint: str | None,
) -> str:
    return _fingerprint(
        {
            "instruction": _instruction_body(instruction),
            "registers": [
                {
                    "register_id": item.register_id,
                    "register_version": item.register_version,
                    "register_fingerprint": item.register_fingerprint,
                }
                for item in sorted(registers, key=lambda item: item.register_id)
            ],
            "requirements_fingerprint": requirements_fingerprint,
            "predecessor_fingerprint": predecessor_fingerprint,
        }
    )


def _requirement(
    source_id: str,
    rows: list[CoverageMatrixRow],
    by_source: dict[str, tuple[DueRegisterBundle, DueSourceRegister]],
) -> HongKongV1DueRequirement:
    shared_facts = {
        (
            row.material_family,
            row.cadence,
            row.outage_consequence,
            row.fact_authority,
            row.owner,
            row.earliest_boundary,
            row.cutoff_rule,
            row.technical_state,
            row.rights_state,
            row.exclusion_code,
        )
        for row in rows
    }
    if len(shared_facts) != 1:
        _fail("MATRIX_ROLE_POLICY_CONFLICT")
    register = by_source.get(source_id)
    if register is None:
        _fail("SOURCE_ROLE_REGISTER_MISSING")
    bundle, source = register
    (
        material_family,
        cadence,
        outage_impact,
        _fact_authority,
        _owner,
        _earliest_boundary,
        _cutoff_rule,
        technical_state,
        rights_state,
        _exclusion_code,
    ) = next(iter(shared_facts))
    conflict = (
        "SOURCE_ROLE_POLICY_CONFLICT" if source.operational_state == "OUT_OF_SCOPE_V1" else None
    )
    matrix_policy_fingerprint = _fingerprint(
        {
            "rows": [
                {
                    "scope_id": row.scope_id,
                    "source_id": row.source_id,
                    "material_family": row.material_family,
                    "cadence": row.cadence,
                    "outage_impact": row.outage_consequence,
                    "fact_authority": row.fact_authority,
                    "owner": row.owner,
                    "earliest_boundary": row.earliest_boundary,
                    "cutoff_rule": row.cutoff_rule,
                    "technical_state": row.technical_state,
                    "rights_state": row.rights_state,
                    "exclusion_code": row.exclusion_code,
                    "limitation_text": row.limitation_text,
                }
                for row in sorted(rows, key=lambda item: item.scope_id)
            ],
        }
    )
    return HongKongV1DueRequirement(
        material_family,
        source_id,
        source.source_version,
        cadence,
        outage_impact,
        bundle.register_id,
        bundle.register_version,
        bundle.register_fingerprint,
        matrix_policy_fingerprint,
        conflict,
        _expected_result_schema(source_id),
        technical_state,
        rights_state,
    )


def _expected_result_schema(source_id: str) -> str:
    return f"asklegal.hk-v1.{source_id.lower()}.result.v1"


def _is_due_cadence(cadence: str, kind: DueCycleKind) -> bool:
    daily_cadences = frozenset(
        {
            "DAILY_AND_COMPLETE_AT_CYCLE_CUTOFF",
            "DAILY_AND_COMPLETE_WITHIN_24_HOURS_OF_CUTOFF",
            "DAILY_DISCOVERY",
            "DAILY_INVENTORY_AND_ON_CHANGE_ACQUISITION",
            "DAILY_SIGNAL_AND_ON_CHANGE_ACQUISITION",
        }
    )
    weekly_cadences = frozenset({"WEEKLY", "WEEKLY_AND_EVENT_TRIGGERED"})
    monthly_cadences = frozenset(
        {"MONTHLY_AND_EVENT_TRIGGERED", "MONTHLY_EVENT_TRIGGERED_AND_ON_DEMAND"}
    )
    daily = cadence in daily_cadences
    weekly = cadence in weekly_cadences
    monthly = cadence in monthly_cadences
    if kind is DueCycleKind.DAILY_CURRENT_LAW:
        return daily
    if kind is DueCycleKind.WEEKLY_RELEASE:
        return daily or weekly
    if kind is DueCycleKind.MONTHLY_CROSS_CHECK:
        return monthly
    return daily or weekly or monthly


def _instruction_body(
    value: HongKongV1DueCycleInstruction,
    code: str = "CYCLE_INSTRUCTION_INVALID",
) -> dict[str, str]:
    value = _rebuild_instruction(value, code)
    return {
        "cycle_id": value.cycle_id,
        "cycle_kind": value.cycle_kind.value,
        "scheduled_at": value.scheduled_at,
        "observation_cutoff": value.observation_cutoff,
        "matrix_revision": value.matrix_revision,
        "matrix_fingerprint": value.matrix_fingerprint,
    }


def _requirement_body(
    value: HongKongV1DueRequirement,
    code: str = "DUE_REQUIREMENT_INVALID",
) -> dict[str, object]:
    value = _rebuild_requirement(value, code)
    return {
        "material_family": value.material_family,
        "source_id": value.source_id,
        "source_version": value.source_version,
        "cadence": value.cadence,
        "outage_impact": value.outage_impact,
        "register_id": value.register_id,
        "register_version": value.register_version,
        "register_fingerprint": value.register_fingerprint,
        "matrix_policy_fingerprint": value.matrix_policy_fingerprint,
        "policy_conflict": value.policy_conflict,
        "result_schema": value.result_schema,
        "technical_state": value.technical_state,
        "rights_state": value.rights_state,
    }


def _fingerprint(value: object) -> str:
    return f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"


def _object(value: object, code: str) -> dict[str, JsonValue]:
    try:
        document = checked_json_value(value)
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(code) from error
    if not isinstance(document, dict):
        _fail(code)
    return document


def _text(document: dict[str, JsonValue], key: str) -> str:
    value = document.get(key)
    if type(value) is not str:
        _fail("CYCLE_INSTRUCTION_INVALID")
    return value


def _exact_text(value: object, code: str) -> None:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        _fail(code)


def _identity(value: object, code: str) -> None:
    _exact_text(value, code)
    if type(value) is not str or _IDENTITY.fullmatch(value) is None:
        _fail(code)


def _fingerprint_text(value: object, code: str) -> None:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        _fail(code)


def _utc(value: object, code: str) -> None:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        _fail(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise HongKongV1DueCycleError(code) from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail(code)


def _fail(code: str) -> Never:
    raise HongKongV1DueCycleError(code)


@dataclass(frozen=True, slots=True)
class DueImmutableReference:
    """Exact immutable artifact reference used only after worker read-back."""

    vault: str
    logical_key: str
    version_id: str
    fingerprint: str
    byte_length: int

    def __post_init__(self) -> None:
        """Require a complete immutable identity rather than a receipt claim."""
        for value in (self.vault, self.logical_key, self.version_id):
            _exact_text(value, "DUE_REFERENCE_INVALID")
        if self.vault not in _LOCAL_VAULTS:
            _fail("DUE_REFERENCE_INVALID")
        if _DUE_LOCAL_VERSION.fullmatch(self.version_id) is None and not _is_canonical_s3_version(
            self.version_id
        ):
            _fail("DUE_REFERENCE_INVALID")
        if any(
            not part or re.fullmatch(r"[a-z0-9._-]+", part) is None
            for part in self.logical_key.split("/")
        ):
            _fail("DUE_REFERENCE_INVALID")
        _fingerprint_text(self.fingerprint, "DUE_REFERENCE_INVALID")
        if type(self.byte_length) is not int or self.byte_length < 0:
            _fail("DUE_REFERENCE_INVALID")


def _is_canonical_s3_version(value: str) -> bool:
    """Mirror the vault's closed serialized S3 version grammar without importing it."""
    match = _DUE_S3_VERSION.fullmatch(value)
    if match is None:
        return False
    payload = value.removeprefix("s3v_")
    try:
        decoded = base64.urlsafe_b64decode(payload + ("=" * (-len(payload) % 4)))
        provider_version = decoded.decode("utf-8", errors="strict")
    except UnicodeDecodeError, ValueError:
        return False
    return (
        bool(provider_version)
        and len(decoded) <= _MAX_S3_PROVIDER_VERSION_BYTES
        and all(ord(character) >= _FIRST_PRINTABLE_CODEPOINT for character in provider_version)
        and base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") == payload
    )


@dataclass(frozen=True, slots=True)
class DueTerminalReportReference:
    """Exact retained terminal-report object paired with its source role."""

    source_id: str
    reference: DueImmutableReference

    def __post_init__(self) -> None:
        """Reject detached or non-immutable terminal-report identities."""
        _identity(self.source_id, "DUE_REFERENCE_INVALID")
        if type(self.reference) is not DueImmutableReference:
            _fail("DUE_REFERENCE_INVALID")
        _rebuild_immutable_reference(self.reference, "DUE_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HongKongV1DueTerminal:
    """One complete worker-owned source-role terminal bound to an immutable plan."""

    cycle_id: str
    plan_fingerprint: str
    matrix_fingerprint: str
    requirement: HongKongV1DueRequirement
    observation_cutoff: str
    result_schema: str
    result_fingerprint: str
    attempt_manifest: DueImmutableReference | None
    evidence_fingerprint: str | None
    outcome: DueTerminalOutcome
    change_status: DueChangeStatus
    failure_codes: tuple[str, ...]
    expected_count: int
    retained_count: int
    not_published_count: int
    gap_count: int
    failed_count: int
    registered_blockers: tuple[str, ...] = ()
    result_schema_version: str = "1.0.0"
    evidence_kind: str = "NONE"

    def __post_init__(self) -> None:
        """Keep completion, change, and terminal counts mutually consistent."""
        _validate_terminal_shape(self)
        _validate_terminal_counts(self)
        _validate_terminal_consequence(self)


def _validate_terminal_shape(terminal: HongKongV1DueTerminal) -> None:
    _identity(terminal.cycle_id, "DUE_TERMINAL_INVALID")
    for value in (
        terminal.plan_fingerprint,
        terminal.matrix_fingerprint,
        terminal.result_fingerprint,
    ):
        _fingerprint_text(value, "DUE_TERMINAL_INVALID")
    _utc(terminal.observation_cutoff, "DUE_TERMINAL_INVALID")
    _exact_text(terminal.result_schema, "DUE_TERMINAL_INVALID")
    if type(terminal.result_schema_version) is not str or terminal.result_schema_version != "1.0.0":
        _fail("DUE_TERMINAL_INVALID")
    if terminal.evidence_fingerprint is not None:
        _fingerprint_text(terminal.evidence_fingerprint, "DUE_TERMINAL_INVALID")
    if terminal.evidence_kind not in {
        "NONE",
        "AUTHENTIC_SOURCE_EVIDENCE",
        "CURRENT_FAMILY_ROLE_PROOF",
    }:
        _fail("DUE_TERMINAL_INVALID")
    if terminal.attempt_manifest is not None:
        _rebuild_immutable_reference(terminal.attempt_manifest, "DUE_TERMINAL_INVALID")
    requirement = _rebuild_requirement(terminal.requirement, "DUE_TERMINAL_INVALID")
    if terminal.result_schema != requirement.result_schema:
        _fail("DUE_TERMINAL_INVALID")
    if (
        type(terminal.outcome) is not DueTerminalOutcome
        or type(terminal.change_status) is not DueChangeStatus
    ):
        _fail("DUE_TERMINAL_INVALID")
    _validate_terminal_reason_codes(terminal)


def _validate_terminal_reason_codes(terminal: HongKongV1DueTerminal) -> None:
    if type(terminal.failure_codes) is not tuple:
        _fail("DUE_TERMINAL_INVALID")
    for failure_code in terminal.failure_codes:
        _exact_text(failure_code, "DUE_TERMINAL_INVALID")
    if terminal.failure_codes != tuple(sorted(set(terminal.failure_codes))):
        _fail("DUE_TERMINAL_INVALID")
    if type(terminal.registered_blockers) is not tuple:
        _fail("DUE_TERMINAL_INVALID")
    for blocker in terminal.registered_blockers:
        _exact_text(blocker, "DUE_TERMINAL_INVALID")
    if terminal.registered_blockers != tuple(sorted(set(terminal.registered_blockers))):
        _fail("DUE_TERMINAL_INVALID")


def _validate_terminal_counts(terminal: HongKongV1DueTerminal) -> None:
    counts = (
        terminal.expected_count,
        terminal.retained_count,
        terminal.not_published_count,
        terminal.gap_count,
        terminal.failed_count,
    )
    if any(type(count) is not int or count < 0 for count in counts):
        _fail("DUE_TERMINAL_INVALID")
    if (
        terminal.retained_count
        + terminal.not_published_count
        + terminal.gap_count
        + terminal.failed_count
        != terminal.expected_count
    ):
        _fail("DUE_TERMINAL_INVALID")


def build_hk_v1_due_terminal(terminal: HongKongV1DueTerminal) -> tuple[bytes, str]:
    """Return canonical terminal bytes and their content fingerprint."""
    try:
        rebuilt = _assert_terminal(terminal, "DUE_TERMINAL_INVALID")
        body = canonicalize(checked_json_value(_terminal_body(rebuilt)))
        return body, f"sha256:{sha256(body).hexdigest()}"
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        code = "DUE_TERMINAL_INVALID"
        raise HongKongV1DueCycleError(code) from error


_IssuedTerminalRegistration = tuple[ReferenceType[HongKongV1DueTerminal], bytes]
_ISSUED_TERMINALS: dict[int, _IssuedTerminalRegistration] = {}
_TerminalSnapshotRegistration = tuple[ReferenceType[HongKongV1DueTerminal], bytes]
_CYCLE_TERMINAL_SNAPSHOTS: dict[int, _TerminalSnapshotRegistration] = {}


@dataclass(frozen=True, slots=True, weakref_slot=True)
class IssuedDueResultBinding:
    """Adapter-owned, snapshot-issued source result; reporting cannot mint it."""

    cycle_id: str
    plan_fingerprint: str
    matrix_fingerprint: str
    requirement: HongKongV1DueRequirement
    observation_cutoff: str
    result_schema: str
    result_schema_version: str
    payload_reference: DueImmutableReference
    evidence_reference: DueImmutableReference | None
    outcome: DueTerminalOutcome
    change_status: DueChangeStatus
    failure_codes: tuple[str, ...]
    expected_count: int
    retained_count: int
    not_published_count: int
    gap_count: int
    failed_count: int
    registered_blockers: tuple[str, ...]
    evidence_kind: str = "NONE"

    def __post_init__(self) -> None:
        """Validate every adapter assertion before any future issuer may register it."""
        try:
            requirement = _rebuild_requirement(self.requirement, "DUE_RESULT_BINDING_INVALID")
            payload_reference = _rebuild_immutable_reference(
                self.payload_reference, "DUE_RESULT_BINDING_INVALID"
            )
            evidence_reference = (
                None
                if self.evidence_reference is None
                else _rebuild_immutable_reference(
                    self.evidence_reference, "DUE_RESULT_BINDING_INVALID"
                )
            )
            validation_attempt = DueImmutableReference(
                payload_reference.vault,
                hk_v1_due_source_result_manifest_key(self.cycle_id, requirement.source_id),
                payload_reference.version_id,
                payload_reference.fingerprint,
                payload_reference.byte_length,
            )
            terminal = HongKongV1DueTerminal(
                self.cycle_id,
                self.plan_fingerprint,
                self.matrix_fingerprint,
                requirement,
                self.observation_cutoff,
                self.result_schema,
                payload_reference.fingerprint,
                validation_attempt,
                None if evidence_reference is None else evidence_reference.fingerprint,
                self.outcome,
                self.change_status,
                self.failure_codes,
                self.expected_count,
                self.retained_count,
                self.not_published_count,
                self.gap_count,
                self.failed_count,
                self.registered_blockers,
                self.result_schema_version,
                self.evidence_kind,
            )
            if terminal.result_schema != requirement.result_schema:
                _fail("DUE_RESULT_BINDING_INVALID")
            if payload_reference.logical_key != hk_v1_due_source_payload_key(
                self.cycle_id, requirement.source_id
            ):
                _fail("DUE_RESULT_BINDING_INVALID")
        except (AttributeError, TypeError, ValueError) as error:
            code = "DUE_RESULT_BINDING_INVALID"
            raise HongKongV1DueCycleError(code) from error


_IssuedBindingRegistration = tuple[ReferenceType[IssuedDueResultBinding], bytes, bool]
_ISSUED_RESULT_BINDINGS: dict[int, _IssuedBindingRegistration] = {}


def _register_validated_acquisition_due_result_binding(  # pyright: ignore[reportUnusedFunction]
    binding: IssuedDueResultBinding,
) -> IssuedDueResultBinding:
    """Record one worker-rebuilt production binding for terminal conversion.

    This deliberately remains module-private.  The acquisition worker is the
    sole owner of the call after it has persisted and exactly re-read its
    payload; reporting never accepts raw JSON as an issuance request.
    """
    rebuilt = _rebuild_result_binding(binding, "DUE_RESULT_BINDING_INVALID")
    binding_id = id(binding)

    def cleanup(dead: ReferenceType[IssuedDueResultBinding]) -> None:
        current = _ISSUED_RESULT_BINDINGS.get(binding_id)
        if current is not None and current[0] is dead:
            del _ISSUED_RESULT_BINDINGS[binding_id]

    _ISSUED_RESULT_BINDINGS[binding_id] = (
        ref(binding, cleanup),
        build_hk_v1_due_result_manifest(rebuilt)[0],
        False,
    )
    return binding


def _rebuild_result_binding(
    binding: object,
    code: str,
) -> IssuedDueResultBinding:
    """Replay every adapter assertion before registry or terminal conversion use."""
    if type(binding) is not IssuedDueResultBinding:
        _fail(code)
    try:
        requirement = _rebuild_requirement(binding.requirement, code)
        payload_reference = _rebuild_immutable_reference(binding.payload_reference, code)
        evidence_reference = (
            None
            if binding.evidence_reference is None
            else _rebuild_immutable_reference(binding.evidence_reference, code)
        )
        return IssuedDueResultBinding(
            binding.cycle_id,
            binding.plan_fingerprint,
            binding.matrix_fingerprint,
            requirement,
            binding.observation_cutoff,
            binding.result_schema,
            binding.result_schema_version,
            payload_reference,
            evidence_reference,
            binding.outcome,
            binding.change_status,
            binding.failure_codes,
            binding.expected_count,
            binding.retained_count,
            binding.not_published_count,
            binding.gap_count,
            binding.failed_count,
            binding.registered_blockers,
            binding.evidence_kind,
        )
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise HongKongV1DueCycleError(code) from error
        raise HongKongV1DueCycleError(code) from error


def _binding_snapshot(binding: IssuedDueResultBinding) -> bytes:
    rebuilt = _rebuild_result_binding(binding, "DUE_RESULT_BINDING_PROVENANCE_INVALID")
    return canonicalize(checked_json_value(_binding_body(rebuilt)))


def issue_test_only_due_result_binding(binding: IssuedDueResultBinding) -> IssuedDueResultBinding:
    """Test hook only; cycle consumption explicitly rejects these bindings."""
    binding_id = id(binding)

    def cleanup(dead: ReferenceType[IssuedDueResultBinding]) -> None:
        current = _ISSUED_RESULT_BINDINGS.get(binding_id)
        if current is not None and current[0] is dead:
            del _ISSUED_RESULT_BINDINGS[binding_id]

    _ISSUED_RESULT_BINDINGS[binding_id] = (ref(binding, cleanup), _binding_snapshot(binding), True)
    return binding


def _assert_production_binding(binding: object) -> IssuedDueResultBinding:
    if type(binding) is not IssuedDueResultBinding:
        _fail("DUE_RESULT_BINDING_PROVENANCE_INVALID")
    try:
        rebuilt = _rebuild_result_binding(binding, "DUE_RESULT_BINDING_PROVENANCE_INVALID")
        registration = _ISSUED_RESULT_BINDINGS.get(id(binding))
        if (
            registration is None
            or registration[0]() is not binding
            or registration[2]
            or registration[1] != build_hk_v1_due_result_manifest(rebuilt)[0]
        ):
            _fail("DUE_RESULT_BINDING_PROVENANCE_INVALID")
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        code = "DUE_RESULT_BINDING_PROVENANCE_INVALID"
        raise HongKongV1DueCycleError(code) from error
    else:
        return rebuilt


def _binding_body(binding: IssuedDueResultBinding) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_id": "asklegal.hk-v1-source-result-manifest",
        "schema_version": "1.0.0",
        "cycle_id": binding.cycle_id,
        "plan_fingerprint": binding.plan_fingerprint,
        "matrix_fingerprint": binding.matrix_fingerprint,
        "requirement": _requirement_body(binding.requirement),
        "observation_cutoff": binding.observation_cutoff,
        "result_schema": binding.result_schema,
        "result_schema_version": binding.result_schema_version,
        "payload_reference": _reference_body(binding.payload_reference),
        "evidence_reference": None
        if binding.evidence_reference is None
        else _reference_body(binding.evidence_reference),
        "outcome": binding.outcome.value,
        "change_status": binding.change_status.value,
        "failure_codes": list(binding.failure_codes),
        "expected_count": binding.expected_count,
        "retained_count": binding.retained_count,
        "not_published_count": binding.not_published_count,
        "gap_count": binding.gap_count,
        "failed_count": binding.failed_count,
        "registered_blockers": list(binding.registered_blockers),
    }
    if binding.evidence_kind != "NONE":
        body["evidence_kind"] = binding.evidence_kind
    return body


def build_hk_v1_due_result_manifest(binding: IssuedDueResultBinding) -> tuple[bytes, str]:
    """Serialize a validated adapter binding without granting issuance authority."""
    try:
        rebuilt = _rebuild_result_binding(binding, "DUE_RESULT_BINDING_INVALID")
        content = canonicalize(checked_json_value(_binding_body(rebuilt)))
        return content, _bytes_fingerprint(content)
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        code = "DUE_RESULT_BINDING_INVALID"
        raise HongKongV1DueCycleError(code) from error


def build_hk_v1_due_terminal_from_result_binding(
    binding: object,
    attempt_reference: object,
) -> HongKongV1DueTerminal:
    """Convert only a currently issued production adapter result into a terminal."""
    try:
        issued = _assert_production_binding(binding)
        terminal = _build_hk_v1_due_terminal_from_binding_snapshot(issued, attempt_reference)
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        code = "DUE_TERMINAL_INVALID"
        raise HongKongV1DueCycleError(code) from error
    return _issue_terminal(terminal)


def _build_hk_v1_due_terminal_from_binding_snapshot(
    issued: IssuedDueResultBinding,
    attempt_reference: object,
) -> HongKongV1DueTerminal:
    """Build a terminal from an already reconstructed, provenance-checked binding."""
    try:
        attempt = _rebuild_immutable_reference(attempt_reference, "DUE_TERMINAL_INVALID")
        manifest = _binding_snapshot(issued)
        if (
            attempt.fingerprint != _bytes_fingerprint(manifest)
            or attempt.byte_length != len(manifest)
            or attempt.logical_key
            != hk_v1_due_source_result_manifest_key(issued.cycle_id, issued.requirement.source_id)
        ):
            _fail("DUE_TERMINAL_INVALID")
        terminal = HongKongV1DueTerminal(
            issued.cycle_id,
            issued.plan_fingerprint,
            issued.matrix_fingerprint,
            issued.requirement,
            issued.observation_cutoff,
            issued.result_schema,
            issued.payload_reference.fingerprint,
            attempt,
            None if issued.evidence_reference is None else issued.evidence_reference.fingerprint,
            issued.outcome,
            issued.change_status,
            issued.failure_codes,
            issued.expected_count,
            issued.retained_count,
            issued.not_published_count,
            issued.gap_count,
            issued.failed_count,
            issued.registered_blockers,
            issued.result_schema_version,
            issued.evidence_kind,
        )
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        code = "DUE_TERMINAL_INVALID"
        raise HongKongV1DueCycleError(code) from error
    return terminal


def _issue_terminal(terminal: HongKongV1DueTerminal) -> HongKongV1DueTerminal:
    terminal_id = id(terminal)

    def cleanup(dead: ReferenceType[HongKongV1DueTerminal]) -> None:
        current = _ISSUED_TERMINALS.get(terminal_id)
        if current is not None and current[0] is dead:
            del _ISSUED_TERMINALS[terminal_id]

    issued_reference = ref(terminal, cleanup)
    _ISSUED_TERMINALS[terminal_id] = (issued_reference, build_hk_v1_due_terminal(terminal)[0])
    return terminal


def _remember_cycle_terminal_snapshot(
    terminal: HongKongV1DueTerminal,
) -> HongKongV1DueTerminal:
    """Mark a private reconstructed terminal copy for cycle-only consumption."""
    terminal_id = id(terminal)

    def cleanup(dead: ReferenceType[HongKongV1DueTerminal]) -> None:
        current = _CYCLE_TERMINAL_SNAPSHOTS.get(terminal_id)
        if current is not None and current[0] is dead:
            del _CYCLE_TERMINAL_SNAPSHOTS[terminal_id]

    _CYCLE_TERMINAL_SNAPSHOTS[terminal_id] = (
        ref(terminal, cleanup),
        build_hk_v1_due_terminal(terminal)[0],
    )
    return terminal


def _assert_issued_terminal(terminal: object) -> HongKongV1DueTerminal:
    rebuilt = _assert_terminal(terminal, "DUE_TERMINAL_PROVENANCE_INVALID")
    if type(terminal) is not HongKongV1DueTerminal:
        _fail("DUE_TERMINAL_PROVENANCE_INVALID")
    registration = _ISSUED_TERMINALS.get(id(terminal))
    if registration is None or registration[0]() is not terminal:
        _fail("DUE_TERMINAL_PROVENANCE_INVALID")
    if registration[1] != build_hk_v1_due_terminal(rebuilt)[0]:
        _fail("DUE_TERMINAL_PROVENANCE_INVALID")
    return _remember_cycle_terminal_snapshot(rebuilt)


def _assert_cycle_terminal_snapshot(terminal: object) -> HongKongV1DueTerminal:
    """Rebuild a private terminal snapshot before every report-level use."""
    if type(terminal) is not HongKongV1DueTerminal:
        _fail("DUE_TERMINAL_PROVENANCE_INVALID")
    rebuilt = _assert_terminal(terminal, "DUE_TERMINAL_PROVENANCE_INVALID")
    registration = _CYCLE_TERMINAL_SNAPSHOTS.get(id(terminal))
    if registration is None or registration[0]() is not terminal:
        _fail("DUE_TERMINAL_PROVENANCE_INVALID")
    if registration[1] != build_hk_v1_due_terminal(rebuilt)[0]:
        _fail("DUE_TERMINAL_PROVENANCE_INVALID")
    return _remember_cycle_terminal_snapshot(rebuilt)


def parse_hk_v1_due_terminal(content: bytes) -> HongKongV1DueTerminal:
    """Parse and byte-verify a terminal that was retained by the worker."""
    try:
        document = parse_json_bytes(content, max_bytes=65_536)
        if (
            not isinstance(document, dict)
            or document.get("schema_id") != "asklegal.hk-v1-source-terminal"
        ):
            _fail("DUE_TERMINAL_INVALID")
        terminal = _terminal_from_document(document)
        if build_hk_v1_due_terminal(terminal)[0] != content:
            _fail("DUE_TERMINAL_INVALID")
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        code = "DUE_TERMINAL_INVALID"
        raise HongKongV1DueCycleError(code) from error
    else:
        return terminal


def _terminal_body(terminal: HongKongV1DueTerminal) -> dict[str, object]:
    reference = terminal.attempt_manifest
    body: dict[str, object] = {
        "schema_id": "asklegal.hk-v1-source-terminal",
        "schema_version": "1.0.0",
        "cycle_id": terminal.cycle_id,
        "plan_fingerprint": terminal.plan_fingerprint,
        "matrix_fingerprint": terminal.matrix_fingerprint,
        "requirement": _requirement_body(terminal.requirement),
        "observation_cutoff": terminal.observation_cutoff,
        "result_schema": terminal.result_schema,
        "result_schema_version": terminal.result_schema_version,
        "result_fingerprint": terminal.result_fingerprint,
        "outcome": terminal.outcome.value,
        "change_status": terminal.change_status.value,
        "failure_codes": list(terminal.failure_codes),
        "expected_count": terminal.expected_count,
        "retained_count": terminal.retained_count,
        "not_published_count": terminal.not_published_count,
        "gap_count": terminal.gap_count,
        "failed_count": terminal.failed_count,
        "registered_blockers": list(terminal.registered_blockers),
        "evidence_fingerprint": terminal.evidence_fingerprint,
        "attempt_manifest": None
        if reference is None
        else {
            "vault": reference.vault,
            "logical_key": reference.logical_key,
            "version_id": reference.version_id,
            "fingerprint": reference.fingerprint,
            "byte_length": reference.byte_length,
        },
    }
    if terminal.evidence_kind != "NONE":
        body["evidence_kind"] = terminal.evidence_kind
    return body


def _terminal_from_document(document: dict[str, JsonValue]) -> HongKongV1DueTerminal:
    try:
        raw_requirement = document["requirement"]
        if not isinstance(raw_requirement, dict):
            _fail("DUE_TERMINAL_INVALID")
        requirement = HongKongV1DueRequirement(
            _json_text(raw_requirement, "material_family"),
            _json_text(raw_requirement, "source_id"),
            _json_text(raw_requirement, "source_version"),
            _json_text(raw_requirement, "cadence"),
            _json_text(raw_requirement, "outage_impact"),
            _json_text(raw_requirement, "register_id"),
            _json_text(raw_requirement, "register_version"),
            _json_text(raw_requirement, "register_fingerprint"),
            _json_text(raw_requirement, "matrix_policy_fingerprint"),
            _json_optional_text(raw_requirement, "policy_conflict"),
            _json_text(raw_requirement, "result_schema"),
            _json_text(raw_requirement, "technical_state"),
            _json_text(raw_requirement, "rights_state"),
        )
        raw_reference = document["attempt_manifest"]
        reference = None
        if raw_reference is not None:
            if not isinstance(raw_reference, dict):
                _fail("DUE_TERMINAL_INVALID")
            reference = DueImmutableReference(
                _json_text(raw_reference, "vault"),
                _json_text(raw_reference, "logical_key"),
                _json_text(raw_reference, "version_id"),
                _json_text(raw_reference, "fingerprint"),
                _json_count(raw_reference, "byte_length"),
            )
        return HongKongV1DueTerminal(
            _json_text(document, "cycle_id"),
            _json_text(document, "plan_fingerprint"),
            _json_text(document, "matrix_fingerprint"),
            requirement,
            _json_text(document, "observation_cutoff"),
            _json_text(document, "result_schema"),
            # Parsed below as the terminal's final versioned field.
            _json_text(document, "result_fingerprint"),
            reference,
            _json_optional_text(document, "evidence_fingerprint"),
            DueTerminalOutcome(_json_text(document, "outcome")),
            DueChangeStatus(_json_text(document, "change_status")),
            _json_text_tuple(document, "failure_codes"),
            _json_count(document, "expected_count"),
            _json_count(document, "retained_count"),
            _json_count(document, "not_published_count"),
            _json_count(document, "gap_count"),
            _json_count(document, "failed_count"),
            _json_text_tuple(document, "registered_blockers"),
            _json_text(document, "result_schema_version"),
            _json_optional_text(document, "evidence_kind") or "NONE",
        )
    except (KeyError, TypeError, ValueError) as error:
        code = "DUE_TERMINAL_INVALID"
        raise HongKongV1DueCycleError(code) from error


def _validate_terminal_consequence(terminal: HongKongV1DueTerminal) -> None:
    if terminal.outcome is DueTerminalOutcome.COMPLETE:
        _validate_complete_terminal(terminal)
    elif terminal.outcome is DueTerminalOutcome.GAP:
        _validate_gap_terminal(terminal)
    elif terminal.outcome is DueTerminalOutcome.FAILED:
        _validate_failed_terminal(terminal)
    else:
        _validate_incomplete_terminal(terminal)


def _validate_complete_terminal(terminal: HongKongV1DueTerminal) -> None:
    if (
        terminal.change_status is DueChangeStatus.NOT_PROVED
        or terminal.failure_codes
        or terminal.gap_count
        or terminal.failed_count
        or terminal.attempt_manifest is None
        or terminal.evidence_fingerprint is None
        or terminal.attempt_manifest.logical_key
        != hk_v1_due_source_result_manifest_key(terminal.cycle_id, terminal.requirement.source_id)
    ):
        _fail("DUE_TERMINAL_INVALID")


def _validate_gap_terminal(terminal: HongKongV1DueTerminal) -> None:
    if (
        terminal.change_status is not DueChangeStatus.NOT_PROVED
        or terminal.failure_codes
        or terminal.gap_count == 0
        or terminal.failed_count != 0
    ):
        _fail("DUE_TERMINAL_INVALID")


def _validate_failed_terminal(terminal: HongKongV1DueTerminal) -> None:
    if (
        terminal.change_status is not DueChangeStatus.NOT_PROVED
        or not terminal.failure_codes
        or terminal.gap_count != 0
        or terminal.failed_count == 0
    ):
        _fail("DUE_TERMINAL_INVALID")


def _validate_incomplete_terminal(terminal: HongKongV1DueTerminal) -> None:
    if (
        terminal.change_status is not DueChangeStatus.NOT_PROVED
        or not terminal.failure_codes
        or terminal.gap_count != 0
        or terminal.failed_count != 0
    ):
        _fail("DUE_TERMINAL_INVALID")


def _json_text(document: dict[str, JsonValue], field: str) -> str:
    value = document.get(field)
    if type(value) is not str:
        _fail("DUE_TERMINAL_INVALID")
    return value


def _json_text_with_code(document: dict[str, JsonValue], field: str, code: str) -> str:
    value = document.get(field)
    if type(value) is not str:
        _fail(code)
    return value


def _json_optional_text(document: dict[str, JsonValue], field: str) -> str | None:
    value = document.get(field)
    if value is None:
        return None
    if type(value) is not str:
        _fail("DUE_TERMINAL_INVALID")
    return value


def _json_count(document: dict[str, JsonValue], field: str) -> int:
    value = document.get(field)
    if type(value) is not int:
        _fail("DUE_TERMINAL_INVALID")
    return value


def _json_text_tuple(document: dict[str, JsonValue], field: str) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        _fail("DUE_TERMINAL_INVALID")
    return tuple(item for item in value if type(item) is str)


def _json_text_tuple_with_code(
    document: dict[str, JsonValue], field: str, code: str
) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        _fail(code)
    return tuple(item for item in value if type(item) is str)


@dataclass(frozen=True, slots=True)
class HongKongV1DueCycleReport:
    """Canonical all-role accounting for one immutable periodic plan."""

    plan: HongKongV1DueCyclePlan
    terminals: tuple[HongKongV1DueTerminal, ...]
    terminal_report_references: tuple[DueTerminalReportReference, ...]
    complete_source_ids: tuple[str, ...]
    missing_source_ids: tuple[str, ...]
    duplicate_source_ids: tuple[str, ...]
    gap_source_ids: tuple[str, ...]
    failed_source_ids: tuple[str, ...]
    accounting_complete: bool
    release_blocking: bool
    disposition: str
    canonical_bytes: bytes
    fingerprint: str

    def __post_init__(self) -> None:
        """Store only rebuilt private snapshots before checking cached report facts."""
        plan = _assert_cycle_plan_snapshot(self.plan)
        if type(self.terminals) is not tuple or type(self.terminal_report_references) is not tuple:
            _fail("DUE_CYCLE_INVALID")
        if any(type(item) is not HongKongV1DueTerminal for item in self.terminals):
            _fail("DUE_CYCLE_INVALID")
        if any(
            type(item) is not DueTerminalReportReference for item in self.terminal_report_references
        ):
            _fail("DUE_CYCLE_INVALID")
        if len(self.terminals) != len(self.terminal_report_references):
            _fail("DUE_CYCLE_INVALID")
        expected = {item.source_id: item for item in plan.requirements}
        pairs = tuple(
            _assert_terminal_binding(
                plan,
                reference,
                terminal,
                expected,
                terminal_is_cycle_snapshot=True,
            )
            for reference, terminal in zip(
                self.terminal_report_references, self.terminals, strict=True
            )
        )
        references = tuple(item[0] for item in pairs)
        terminals = tuple(item[1] for item in pairs)
        if references != tuple(sorted(references, key=_terminal_reference_sort_key)):
            _fail("DUE_CYCLE_INVALID")
        object.__setattr__(self, "plan", plan)
        object.__setattr__(self, "terminals", terminals)
        object.__setattr__(self, "terminal_report_references", references)
        _validate_cycle_report_fields(self)


def _validate_cycle_report_fields(report: HongKongV1DueCycleReport) -> None:
    cached_source_fields = (
        "complete_source_ids",
        "missing_source_ids",
        "duplicate_source_ids",
        "gap_source_ids",
        "failed_source_ids",
    )
    _validate_cached_source_ids(report.complete_source_ids)
    _validate_cached_source_ids(report.missing_source_ids)
    _validate_cached_source_ids(report.duplicate_source_ids)
    _validate_cached_source_ids(report.gap_source_ids)
    _validate_cached_source_ids(report.failed_source_ids)
    if type(report.disposition) is not str:
        _fail("DUE_CYCLE_INVALID")
    if report.disposition not in {
        "COMPLETE",
        "ACCOUNTED_WITH_GAPS",
        "INCOMPLETE_ACCOUNTING",
    }:
        _fail("DUE_CYCLE_INVALID")
    if (
        type(report.accounting_complete) is not bool
        or type(report.release_blocking) is not bool
        or type(report.canonical_bytes) is not bytes
    ):
        _fail("DUE_CYCLE_INVALID")
    _fingerprint_text(report.fingerprint, "DUE_CYCLE_INVALID")
    rebuilt = _cycle_body(report.plan, report.terminal_report_references, report.terminals)
    body = canonicalize(checked_json_value(rebuilt))
    if report.canonical_bytes != body or report.fingerprint != _bytes_fingerprint(body):
        _fail("DUE_CYCLE_INVALID")
    for field in cached_source_fields:
        if getattr(report, field) != _report_source_ids(rebuilt, field):
            _fail("DUE_CYCLE_INVALID")
    if (
        report.accounting_complete is not rebuilt["accounting_complete"]
        or report.release_blocking is not rebuilt["release_blocking"]
        or report.disposition != rebuilt["disposition"]
    ):
        _fail("DUE_CYCLE_INVALID")


def _validate_cached_source_ids(value: tuple[str, ...]) -> None:
    """Reject equality/hash lookalikes before any report-accounting comparison."""
    if type(value) is not tuple:
        _fail("DUE_CYCLE_INVALID")
    for source_id in value:
        if type(source_id) is not str:
            _fail("DUE_CYCLE_INVALID")
        _identity(source_id, "DUE_CYCLE_INVALID")


def _report_source_ids(body: dict[str, object], field: str) -> tuple[str, ...]:
    return _json_text_tuple(_object(body, "DUE_CYCLE_INVALID"), field)


def build_hk_v1_due_cycle_report(
    plan: HongKongV1DueCyclePlan,
    terminal_reports: tuple[tuple[DueTerminalReportReference, HongKongV1DueTerminal], ...],
) -> HongKongV1DueCycleReport:
    """Rebuild a cycle only from exact terminal artifacts and their references."""
    try:
        plan = _cycle_plan_snapshot(plan)
        if type(terminal_reports) is not tuple:
            _fail("DUE_CYCLE_INVALID")
        if any(type(item) is not tuple or len(item) != _PAIR_LENGTH for item in terminal_reports):
            _fail("DUE_CYCLE_INVALID")
        references = tuple(item[0] for item in terminal_reports)
        terminals = tuple(item[1] for item in terminal_reports)
        if any(type(item) is not DueTerminalReportReference for item in references) or any(
            type(item) is not HongKongV1DueTerminal for item in terminals
        ):
            _fail("DUE_CYCLE_INVALID")
        expected = {item.source_id: item for item in plan.requirements}
        normalized_pairs = tuple(
            _assert_terminal_binding(plan, reference, terminal, expected)
            for reference, terminal in terminal_reports
        )
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        code = "DUE_CYCLE_INVALID"
        raise HongKongV1DueCycleError(code) from error
    references = tuple(item[0] for item in normalized_pairs)
    terminals = tuple(item[1] for item in normalized_pairs)
    counts: dict[str, int] = {}
    for _reference, terminal in normalized_pairs:
        counts[terminal.requirement.source_id] = counts.get(terminal.requirement.source_id, 0) + 1
    missing = tuple(sorted(set(expected).difference(counts)))
    duplicate = tuple(sorted(source_id for source_id, count in counts.items() if count != 1))
    gap = tuple(sorted({item.requirement.source_id for item in terminals if item.gap_count > 0}))
    failed = tuple(
        sorted(
            {
                item.requirement.source_id
                for item in terminals
                if item.failed_count > 0
                or item.outcome is DueTerminalOutcome.INCOMPLETE_OBSERVATION
            }
        )
    )
    complete_ids = tuple(
        sorted(
            {
                item.requirement.source_id
                for item in terminals
                if item.outcome is DueTerminalOutcome.COMPLETE
            }
        )
    )
    complete = not missing and not duplicate
    release_blocking = _release_blocking(expected, missing, duplicate, gap, failed)
    ordered_pairs = tuple(
        sorted(
            zip(references, terminals, strict=True),
            key=lambda item: _terminal_reference_sort_key(item[0]),
        )
    )
    ordered_references = tuple(item[0] for item in ordered_pairs)
    ordered_terminals = tuple(item[1] for item in ordered_pairs)
    disposition = _overall_disposition(accounting_complete=complete, gap=gap, failed=failed)
    cycle_body = _cycle_body(plan, ordered_references, ordered_terminals)
    body = canonicalize(checked_json_value(cycle_body))
    return HongKongV1DueCycleReport(
        plan,
        ordered_terminals,
        ordered_references,
        complete_ids,
        missing,
        duplicate,
        gap,
        failed,
        complete,
        release_blocking,
        disposition,
        body,
        _bytes_fingerprint(body),
    )


def parse_hk_v1_due_cycle_report(
    content: bytes,
    plan: HongKongV1DueCyclePlan,
    terminal_artifacts: tuple[tuple[object, ...], ...],
) -> HongKongV1DueCycleReport:
    """Parse a cycle only when every retained terminal artifact re-verifies."""
    plan = _cycle_plan_snapshot(plan)
    if type(content) is not bytes or type(terminal_artifacts) is not tuple:
        _fail("DUE_CYCLE_INVALID")
    try:
        document = parse_json_bytes(content, max_bytes=1_000_000)
        if not isinstance(document, dict):
            _fail("DUE_CYCLE_INVALID")
        expected_fields = frozenset(
            {
                "schema_id",
                "schema_version",
                "cycle_id",
                "cycle_kind",
                "scheduled_at",
                "observation_cutoff",
                "matrix",
                "registers",
                "requirements_fingerprint",
                "requirements",
                "predecessor_fingerprint",
                "plan_fingerprint",
                "source_reports",
                "complete_source_ids",
                "missing_source_ids",
                "duplicate_source_ids",
                "gap_source_ids",
                "failed_source_ids",
                "accounting_complete",
                "release_blocking",
                "disposition",
            }
        )
        if frozenset(document) != expected_fields:
            _fail("DUE_CYCLE_INVALID")
        supplied = _terminal_artifact_bindings(terminal_artifacts)
        report = build_hk_v1_due_cycle_report(plan, supplied)
        if report.canonical_bytes != content:
            _fail("DUE_CYCLE_INVALID")
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        code = "DUE_CYCLE_INVALID"
        raise HongKongV1DueCycleError(code) from error
    else:
        return report


def _assert_terminal_binding(
    plan: HongKongV1DueCyclePlan,
    report_reference: DueTerminalReportReference,
    terminal: HongKongV1DueTerminal,
    expected: dict[str, HongKongV1DueRequirement],
    *,
    terminal_is_cycle_snapshot: bool = False,
) -> tuple[DueTerminalReportReference, HongKongV1DueTerminal]:
    # Reconstruct direct values so object.__setattr__ and custom equality cannot lie.
    terminal = (
        _assert_cycle_terminal_snapshot(terminal)
        if terminal_is_cycle_snapshot
        else _assert_issued_terminal(terminal)
    )
    report_reference = _rebuild_terminal_report_reference(report_reference, "DUE_CYCLE_INVALID")
    source_id = terminal.requirement.source_id
    if report_reference.source_id != source_id or expected.get(source_id) != terminal.requirement:
        _fail("DUE_CYCLE_INVALID")
    if (
        terminal.cycle_id != plan.instruction.cycle_id
        or terminal.plan_fingerprint != plan.plan_fingerprint
        or terminal.matrix_fingerprint != plan.instruction.matrix_fingerprint
        or terminal.observation_cutoff != plan.instruction.observation_cutoff
    ):
        _fail("DUE_CYCLE_INVALID")
    _register, source = _register_sources(plan.registers)[source_id]
    if terminal.registered_blockers != source.blockers:
        _fail("DUE_CYCLE_INVALID")
    if terminal.outcome is DueTerminalOutcome.COMPLETE and (
        terminal.evidence_kind == "NONE"
        and (
            terminal.requirement.technical_state != "ADMITTED"
            or terminal.requirement.rights_state != "ADMITTED"
            or source.operational_state != "CONFIGURED"
            or not source.endpoint_ids
            or source.blockers
        )
    ):
        _fail("DUE_CYCLE_INVALID")
    terminal_bytes, terminal_fingerprint = build_hk_v1_due_terminal(terminal)
    reference = _rebuild_immutable_reference(report_reference.reference, "DUE_CYCLE_INVALID")
    if (
        reference.fingerprint != terminal_fingerprint
        or reference.byte_length != len(terminal_bytes)
        or reference.logical_key
        != hk_v1_due_source_terminal_key(plan.instruction.cycle_id, source_id)
    ):
        _fail("DUE_CYCLE_INVALID")
    return report_reference, terminal


def _terminal_artifact_bindings(
    terminal_artifacts: tuple[tuple[object, ...], ...],
) -> tuple[tuple[DueTerminalReportReference, HongKongV1DueTerminal], ...]:
    bindings: list[tuple[DueTerminalReportReference, HongKongV1DueTerminal]] = []
    for artifact in terminal_artifacts:
        if len(artifact) != _TERMINAL_ARTIFACT_LENGTH:
            _fail("DUE_CYCLE_INVALID")
        reference, content, result_manifest, result_binding = artifact
        if (
            type(reference) is not DueTerminalReportReference
            or type(content) is not bytes
            or type(result_manifest) is not bytes
        ):
            _fail("DUE_CYCLE_INVALID")
        if reference.reference.fingerprint != _bytes_fingerprint(
            content
        ) or reference.reference.byte_length != len(content):
            _fail("DUE_CYCLE_INVALID")
        parsed = parse_hk_v1_due_terminal(content)
        if parsed.attempt_manifest is None:
            _fail("DUE_CYCLE_INVALID")
        binding = _assert_production_binding(result_binding)
        issued = _issue_terminal(
            _build_hk_v1_due_terminal_from_binding_snapshot(binding, parsed.attempt_manifest)
        )
        if result_manifest != canonicalize(checked_json_value(_binding_body(binding))):
            _fail("DUE_CYCLE_INVALID")
        if build_hk_v1_due_terminal(issued)[0] != content:
            _fail("DUE_CYCLE_INVALID")
        bindings.append((reference, issued))
    return tuple(bindings)


def _cycle_body(
    plan: HongKongV1DueCyclePlan,
    references: tuple[DueTerminalReportReference, ...],
    terminals: tuple[HongKongV1DueTerminal, ...],
) -> dict[str, object]:
    expected = {item.source_id: item for item in plan.requirements}
    pairs = tuple(zip(references, terminals, strict=True))
    seen_source_ids = tuple(item.requirement.source_id for item in terminals)
    missing = tuple(sorted(set(expected).difference(seen_source_ids)))
    duplicate = tuple(
        sorted(
            source_id
            for source_id in expected
            if seen_source_ids.count(source_id) != 1 and source_id not in missing
        )
    )
    gap = tuple(sorted({item.requirement.source_id for item in terminals if item.gap_count > 0}))
    failed = tuple(
        sorted(
            {
                item.requirement.source_id
                for item in terminals
                if item.failed_count > 0
                or item.outcome is DueTerminalOutcome.INCOMPLETE_OBSERVATION
            }
        )
    )
    complete_ids = tuple(
        sorted(
            {
                item.requirement.source_id
                for item in terminals
                if item.outcome is DueTerminalOutcome.COMPLETE
            }
        )
    )
    accounting_complete = not missing and not duplicate
    release_blocking = _release_blocking(expected, missing, duplicate, gap, failed)
    return {
        "schema_id": "asklegal.hk-v1-source-cycle-manifest",
        "schema_version": "1.0.0",
        "cycle_id": plan.instruction.cycle_id,
        "cycle_kind": plan.instruction.cycle_kind.value,
        "scheduled_at": plan.instruction.scheduled_at,
        "observation_cutoff": plan.instruction.observation_cutoff,
        "matrix": {
            "revision": plan.instruction.matrix_revision,
            "fingerprint": plan.instruction.matrix_fingerprint,
        },
        "registers": [_register_body(item) for item in plan.registers],
        "requirements_fingerprint": plan.requirements_fingerprint,
        "requirements": [_requirement_body(item) for item in plan.requirements],
        "predecessor_fingerprint": plan.predecessor_fingerprint,
        "plan_fingerprint": plan.plan_fingerprint,
        "source_reports": [
            {
                "source_id": reference.source_id,
                "reference": _reference_body(reference.reference),
                "terminal_fingerprint": build_hk_v1_due_terminal(terminal)[1],
            }
            for reference, terminal in pairs
        ],
        "complete_source_ids": list(complete_ids),
        "missing_source_ids": list(missing),
        "duplicate_source_ids": list(duplicate),
        "gap_source_ids": list(gap),
        "failed_source_ids": list(failed),
        "accounting_complete": accounting_complete,
        "release_blocking": release_blocking,
        "disposition": _overall_disposition(
            accounting_complete=accounting_complete,
            gap=gap,
            failed=failed,
        ),
    }


def _release_blocking(
    expected: dict[str, HongKongV1DueRequirement],
    missing: tuple[str, ...],
    duplicate: tuple[str, ...],
    gap: tuple[str, ...],
    failed: tuple[str, ...],
) -> bool:
    problem_source_ids = frozenset((*missing, *duplicate, *gap, *failed))
    return any(
        expected[source_id].outage_impact != "NONBLOCKING" for source_id in problem_source_ids
    )


def _overall_disposition(
    *,
    accounting_complete: bool,
    gap: tuple[str, ...],
    failed: tuple[str, ...],
) -> str:
    if not accounting_complete:
        return "INCOMPLETE_ACCOUNTING"
    if gap or failed:
        return "ACCOUNTED_WITH_GAPS"
    return "COMPLETE"


def _reference_body(reference: DueImmutableReference) -> dict[str, JsonValue]:
    return {
        "vault": reference.vault,
        "logical_key": reference.logical_key,
        "version_id": reference.version_id,
        "fingerprint": reference.fingerprint,
        "byte_length": reference.byte_length,
    }


def _register_body(register: DueRegisterBundle) -> dict[str, object]:
    return {
        "register_id": register.register_id,
        "register_version": register.register_version,
        "register_fingerprint": register.register_fingerprint,
        "sources": [
            {
                "source_id": source.source_id,
                "source_version": source.source_version,
                "endpoint_ids": list(source.endpoint_ids),
                "operational_state": source.operational_state,
                "blockers": list(source.blockers),
            }
            for source in register.sources
        ],
    }


def hk_v1_due_source_payload_key(cycle_id: str, source_id: str) -> str:
    """Return the reversible exact fixed key for one source payload object."""
    return _due_source_key(cycle_id, source_id, "payload.json")


def hk_v1_due_source_result_manifest_key(cycle_id: str, source_id: str) -> str:
    """Return the reversible exact fixed key for one source result manifest."""
    return _due_source_key(cycle_id, source_id, "attempt.json")


def hk_v1_due_source_terminal_key(cycle_id: str, source_id: str) -> str:
    """Return the reversible exact fixed key for one source terminal report."""
    return _due_source_key(cycle_id, source_id, "terminal.json")


def hk_v1_due_cycle_manifest_key(cycle_id: str) -> str:
    """Return the reversible exact fixed key for one cycle manifest."""
    return _due_key(cycle_id, None, "manifest.json")


def hk_v1_due_family_acquisition_key(cycle_id: str) -> str:
    """Return the exact retained two-family child-acquisition receipt key."""
    _identity(cycle_id, "DUE_REFERENCE_INVALID")
    return f"poc/report/hk-v1-due-cycle/{cycle_id}/family-acquisitions.json"


def _due_source_key(cycle_id: str, source_id: str, filename: str) -> str:
    return _due_key(cycle_id, source_id, filename)


def _due_key(cycle_id: str, source_id: str | None, filename: str) -> str:
    _identity(cycle_id, "DUE_REFERENCE_INVALID")
    if source_id is not None:
        _identity(source_id, "DUE_REFERENCE_INVALID")
    parts = ["hk-v1", "due-cycles", "cycle", *_due_key_identity_parts(cycle_id)]
    if source_id is not None:
        parts.extend(("source", *_due_key_identity_parts(source_id)))
    parts.append(filename)
    key = "/".join(parts)
    _validate_due_key(key, filename, cycle_id, source_id)
    return key


def _due_key_identity_parts(value: str) -> tuple[str, ...]:
    raw = value.encode("utf-8")
    hex_value = raw.hex()
    chunks = tuple(
        f"hex-{hex_value[index : index + (_KEY_HEX_CHUNK_BYTES * 2)]}"
        for index in range(0, len(hex_value), _KEY_HEX_CHUNK_BYTES * 2)
    )
    return (f"sha256-{_key_digest(value)}", *chunks)


def _key_digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _validate_due_key(
    key: object,
    filename: str,
    cycle_id: str,
    source_id: str | None,
) -> None:
    """Reconstruct both identities and prove their stored digest before use."""
    if type(key) is not str or type(filename) is not str:
        _fail("DUE_REFERENCE_INVALID")
    segments = key.split("/")
    if segments[:3] != ["hk-v1", "due-cycles", "cycle"]:
        _fail("DUE_REFERENCE_INVALID")
    cursor = 3
    rebuilt_cycle, cursor = _reconstruct_due_key_identity(segments, cursor)
    rebuilt_source: str | None = None
    if source_id is not None:
        if cursor >= len(segments) or segments[cursor] != "source":
            _fail("DUE_REFERENCE_INVALID")
        rebuilt_source, cursor = _reconstruct_due_key_identity(segments, cursor + 1)
    if cursor != len(segments) - 1 or segments[cursor] != filename:
        _fail("DUE_REFERENCE_INVALID")
    if rebuilt_cycle != cycle_id or rebuilt_source != source_id:
        _fail("DUE_REFERENCE_INVALID")


def _reconstruct_due_key_identity(segments: list[str], cursor: int) -> tuple[str, int]:
    if cursor >= len(segments) or not segments[cursor].startswith("sha256-"):
        _fail("DUE_REFERENCE_INVALID")
    digest = segments[cursor].removeprefix("sha256-")
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        _fail("DUE_REFERENCE_INVALID")
    cursor += 1
    chunks: list[str] = []
    while cursor < len(segments) and segments[cursor].startswith("hex-"):
        chunk = segments[cursor].removeprefix("hex-")
        if (
            not chunk
            or len(chunk) > _KEY_HEX_CHUNK_BYTES * 2
            or re.fullmatch(r"[0-9a-f]+", chunk) is None
        ):
            _fail("DUE_REFERENCE_INVALID")
        chunks.append(chunk)
        cursor += 1
    if not chunks:
        _fail("DUE_REFERENCE_INVALID")
    try:
        raw = bytes.fromhex("".join(chunks))
        value = raw.decode("utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError) as error:
        code = "DUE_REFERENCE_INVALID"
        raise HongKongV1DueCycleError(code) from error
    _identity(value, "DUE_REFERENCE_INVALID")
    if _key_digest(value) != digest:
        _fail("DUE_REFERENCE_INVALID")
    return value, cursor


def _terminal_reference_sort_key(
    reference: DueTerminalReportReference,
) -> tuple[str, str, str, str, str, int]:
    rebuilt = _rebuild_terminal_report_reference(reference, "DUE_CYCLE_INVALID")
    immutable = rebuilt.reference
    return (
        rebuilt.source_id,
        immutable.vault,
        immutable.logical_key,
        immutable.version_id,
        immutable.fingerprint,
        immutable.byte_length,
    )


def _bytes_fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _rebuild_immutable_reference(
    reference: object,
    code: str,
) -> DueImmutableReference:
    if type(reference) is not DueImmutableReference:
        _fail(code)
    try:
        rebuilt = DueImmutableReference(
            reference.vault,
            reference.logical_key,
            reference.version_id,
            reference.fingerprint,
            reference.byte_length,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(code) from error
    if rebuilt != reference:
        _fail(code)
    return rebuilt


def _rebuild_terminal_report_reference(
    reference: object,
    code: str,
) -> DueTerminalReportReference:
    if type(reference) is not DueTerminalReportReference:
        _fail(code)
    try:
        immutable = _rebuild_immutable_reference(reference.reference, code)
        rebuilt = DueTerminalReportReference(reference.source_id, immutable)
    except (AttributeError, TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(code) from error
    if rebuilt != reference:
        _fail(code)
    return rebuilt


def _assert_terminal(terminal: object, code: str) -> HongKongV1DueTerminal:
    if type(terminal) is not HongKongV1DueTerminal:
        _fail(code)
    try:
        requirement = _rebuild_requirement(terminal.requirement, code)
        attempt = terminal.attempt_manifest
        attempt_copy = None
        if attempt is not None:
            attempt_copy = _rebuild_immutable_reference(attempt, code)
        rebuilt = HongKongV1DueTerminal(
            terminal.cycle_id,
            terminal.plan_fingerprint,
            terminal.matrix_fingerprint,
            requirement,
            terminal.observation_cutoff,
            terminal.result_schema,
            terminal.result_fingerprint,
            attempt_copy,
            terminal.evidence_fingerprint,
            terminal.outcome,
            terminal.change_status,
            terminal.failure_codes,
            terminal.expected_count,
            terminal.retained_count,
            terminal.not_published_count,
            terminal.gap_count,
            terminal.failed_count,
            terminal.registered_blockers,
            terminal.result_schema_version,
            terminal.evidence_kind,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(code) from error
    if rebuilt != terminal:
        _fail(code)
    return rebuilt


def _assert_plan(plan: object, code: str) -> HongKongV1DueCyclePlan:
    if type(plan) is not HongKongV1DueCyclePlan:
        _fail(code)
    try:
        instruction = _rebuild_instruction(plan.instruction, code)
        registers = tuple(
            DueRegisterBundle(
                register.register_id,
                register.register_version,
                register.register_fingerprint,
                tuple(
                    DueSourceRegister(
                        source.source_id,
                        source.source_version,
                        source.endpoint_ids,
                        source.operational_state,
                        source.blockers,
                    )
                    for source in register.sources
                ),
            )
            for register in plan.registers
        )
        requirements = tuple(
            _rebuild_requirement(requirement, code) for requirement in plan.requirements
        )
        rebuilt = HongKongV1DueCyclePlan(
            instruction,
            registers,
            plan.predecessor_fingerprint,
            requirements,
            plan.requirements_fingerprint,
            plan.plan_fingerprint,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(code) from error
    if rebuilt != plan:
        _fail(code)
    return rebuilt


def _assert_issued_plan(plan: object) -> HongKongV1DueCyclePlan:
    if type(plan) is not HongKongV1DueCyclePlan:
        _fail("CYCLE_PLAN_PROVENANCE_INVALID")
    rebuilt = _assert_plan(plan, "CYCLE_PLAN_PROVENANCE_INVALID")
    registration = _ISSUED_PLANS.get(id(plan))
    if registration is None or registration[0]() is not plan:
        _fail("CYCLE_PLAN_PROVENANCE_INVALID")
    if registration[1] != _issued_plan_snapshot(rebuilt):
        _fail("CYCLE_PLAN_PROVENANCE_INVALID")
    return _remember_cycle_plan_snapshot(rebuilt)


def _assert_cycle_plan_snapshot(plan: object) -> HongKongV1DueCyclePlan:
    """Rebuild a private plan snapshot before every report-level use."""
    if type(plan) is not HongKongV1DueCyclePlan:
        _fail("CYCLE_PLAN_PROVENANCE_INVALID")
    rebuilt = _assert_plan(plan, "CYCLE_PLAN_PROVENANCE_INVALID")
    registration = _CYCLE_PLAN_SNAPSHOTS.get(id(plan))
    if registration is None or registration[0]() is not plan:
        _fail("CYCLE_PLAN_PROVENANCE_INVALID")
    if registration[1] != _issued_plan_snapshot(rebuilt):
        _fail("CYCLE_PLAN_PROVENANCE_INVALID")
    return _remember_cycle_plan_snapshot(rebuilt)


def _cycle_plan_snapshot(plan: object) -> HongKongV1DueCyclePlan:
    """Accept an issued original or an already verified private plan snapshot."""
    if type(plan) is not HongKongV1DueCyclePlan:
        _fail("CYCLE_PLAN_PROVENANCE_INVALID")
    registration = _CYCLE_PLAN_SNAPSHOTS.get(id(plan))
    if registration is not None and registration[0]() is plan:
        return _assert_cycle_plan_snapshot(plan)
    return _assert_issued_plan(plan)


def project_hk_v1_two_family_acquisition(
    legislation_manifest: bytes | None,
    cases_manifest: bytes | None,
    accepted_observation_cutoff: str,
) -> TwoFamilyAcquisitionProjection:
    """Admit only two complete, self-fingerprinted manifests at one UTC cutoff."""
    if legislation_manifest is None or cases_manifest is None:
        _two_family_fail("HK_V1_TWO_FAMILY_PROPOSAL_INCOMPLETE")
    cutoff = _two_family_cutoff(accepted_observation_cutoff)
    legislation = parse_hk_v1_legislation_acquisition_manifest(legislation_manifest)
    cases = parse_hk_v1_cases_acquisition_manifest(cases_manifest)
    if (
        legislation.observation_cutoff != cases.observation_cutoff
        or cutoff != cases.observation_cutoff
    ):
        _two_family_fail("HK_V1_TWO_FAMILY_CUTOFF_MISMATCH")
    return TwoFamilyAcquisitionProjection(cutoff, (cases, legislation))


def parse_hk_v1_legislation_acquisition_manifest(  # noqa: C901 - producer parity boundary.
    content: bytes,
) -> FamilyAcquisitionCoverage:
    """Strictly project one producer-canonical successful Legislation manifest."""
    document = _two_family_document(content, _TWO_FAMILY_LEGISLATION_FIELDS)
    if (
        document["schema_id"] != "asklegal.legislation-acquisition-manifest"
        or document["schema_version"] != "1.0.0"
    ):
        _two_family_invalid()
    _two_family_manifest_fingerprint(document)
    result = _two_family_text(document["result"])
    if result not in {"COMPLETE", "NO_CHANGE"}:
        _two_family_fail("HK_V1_TWO_FAMILY_ACQUISITION_INCOMPLETE")
    cycle_id = _two_family_text(document["cycle_id"])
    raw_cutoff = _two_family_text(document["observation_cutoff"])
    if (
        _TWO_FAMILY_LEGISLATION_CYCLE.fullmatch(cycle_id) is None
        or _TWO_FAMILY_LEGISLATION_CUTOFF.fullmatch(raw_cutoff) is None
    ):
        _two_family_invalid()
    for name in (
        "journal_head_fingerprint",
        "source_register_fingerprint",
        "source_baseline_fingerprint",
        "work_plan_fingerprint",
    ):
        _two_family_fingerprint(document[name])
    raw_scopes = document["scope_dispositions"]
    if type(raw_scopes) is not list:
        _two_family_invalid()
    scope_ids: list[str] = []
    retryable_count = 0
    for raw_scope in raw_scopes:
        if type(raw_scope) is not dict or frozenset(raw_scope) != _TWO_FAMILY_SCOPE_FIELDS:
            _two_family_invalid()
        required = _two_family_int(raw_scope["required_item_count"])
        verified = _two_family_int(raw_scope["verified_item_count"])
        retryable = _two_family_int(raw_scope["retryable_item_count"])
        rejected = _two_family_int(raw_scope["rejected_item_count"])
        if (
            required < 1
            or verified + retryable + rejected != required
            or verified != required
            or retryable != 0
            or rejected != 0
            or raw_scope["result"] != result
        ):
            _two_family_fail("HK_V1_TWO_FAMILY_ACQUISITION_INCOMPLETE")
        scope_ids.append(_two_family_text(raw_scope["scope_id"]))
        retryable_count += retryable
    if tuple(scope_ids) != _TWO_FAMILY_LEGISLATION_SCOPES:
        _two_family_invalid()
    verified_refs = _two_family_texts(document["verified_item_refs"], required=True)
    if any(_TWO_FAMILY_LEGISLATION_REF.fullmatch(value) is None for value in verified_refs):
        _two_family_invalid()
    reviews = _two_family_texts(document["review_issue_refs"], required=False)
    if any(_TWO_FAMILY_REFERENCE.fullmatch(value) is None for value in reviews):
        _two_family_invalid()
    return FamilyAcquisitionCoverage(
        material_family="LEGISLATION",
        cycle_id=cycle_id,
        observation_cutoff=_two_family_cutoff(raw_cutoff),
        scope_ids=tuple(scope_ids),
        manifest_fingerprint=_two_family_fingerprint(document["fingerprint"]),
        journal_head_fingerprint=_two_family_fingerprint(document["journal_head_fingerprint"]),
        retryable_count=retryable_count,
        review_issue_refs=reviews,
        verified_evidence_refs=verified_refs,
    )


def parse_hk_v1_cases_acquisition_manifest(content: bytes) -> FamilyAcquisitionCoverage:
    """Strictly project one producer-canonical successful Cases manifest."""
    document = _two_family_document(content, _TWO_FAMILY_CASES_FIELDS)
    _two_family_manifest_fingerprint(document)
    result = _two_family_text(document["result"])
    if result not in {"COMPLETE", "NO_CHANGE"}:
        _two_family_fail("HK_V1_TWO_FAMILY_ACQUISITION_INCOMPLETE")
    if _two_family_text(document["earliest_decision_date"]) != "1997-07-01":
        _two_family_invalid()
    cutoff = _two_family_cutoff(_two_family_text(document["observation_cutoff"]), require_z=True)
    cutoff_value = datetime.fromisoformat(f"{cutoff[:-1]}+00:00")
    if cutoff_value < _TWO_FAMILY_EARLIEST_CASE_DATE:
        _two_family_invalid()
    raw_years = document["year_dispositions"]
    if type(raw_years) is not list or not raw_years or len(raw_years) != int(cutoff[:4]) - 1996:
        _two_family_invalid()
    verified_total = 0
    retryable_total = 0
    for expected_year, raw_year in zip(
        range(_TWO_FAMILY_EARLIEST_CASE_YEAR, int(cutoff[:4]) + 1),
        raw_years,
        strict=True,
    ):
        if type(raw_year) is not dict or frozenset(raw_year) != _TWO_FAMILY_YEAR_FIELDS:
            _two_family_invalid()
        year = _two_family_int(raw_year["year"])
        final_page = _two_family_int(raw_year["final_page"])
        verified_pages = _two_family_int(raw_year["verified_listing_pages"])
        discovered = _two_family_int(raw_year["discovered_judgments"])
        verified = _two_family_int(raw_year["verified_judgments"])
        retryable = _two_family_int(raw_year["retryable_items"])
        first_date = "1997-07-01" if year == _TWO_FAMILY_EARLIEST_CASE_YEAR else f"{year:04d}-01-01"
        if (
            year != expected_year
            or raw_year["first_in_scope_date"] != first_date
            or raw_year["result"] != "COMPLETE"
            or final_page < 1
            or verified_pages != final_page
            or discovered != verified
            or retryable != 0
        ):
            _two_family_fail("HK_V1_TWO_FAMILY_ACQUISITION_INCOMPLETE")
        verified_total += verified
        retryable_total += retryable
    bundle_refs = _two_family_ordered_texts(
        document["judgment_bundle_refs"], required=False, unique=True
    )
    if len(bundle_refs) != verified_total or any(
        re.fullmatch(r"cases/judgment-bundles/sha256/[0-9a-f]{64}\.json", value) is None
        for value in bundle_refs
    ):
        _two_family_invalid()
    reviews = _two_family_ordered_texts(document["discrepancy_refs"], required=False, unique=False)
    return FamilyAcquisitionCoverage(
        material_family="CASES",
        cycle_id=_two_family_text(document["cycle_id"]),
        observation_cutoff=cutoff,
        scope_ids=("HK-CASE-BINDING-POST-1997",),
        manifest_fingerprint=_two_family_fingerprint(document["fingerprint"]),
        journal_head_fingerprint=_two_family_fingerprint(document["journal_head_fingerprint"]),
        retryable_count=retryable_total,
        review_issue_refs=reviews,
        verified_evidence_refs=bundle_refs,
    )


def _two_family_document(content: bytes, fields: frozenset[str]) -> dict[str, JsonValue]:
    if type(content) is not bytes or not content:
        _two_family_invalid()
    try:
        value = parse_json_bytes(content, max_bytes=4_194_304)
    except ContractViolation as error:
        _two_family_fail_from("HK_V1_TWO_FAMILY_ACQUISITION_INVALID", error)
    accepted_fields = {fields, fields | {"source_dispositions"}}
    if (
        type(value) is not dict
        or frozenset(value) not in accepted_fields
        or canonicalize(value) != content
        or ("source_dispositions" in value and type(value["source_dispositions"]) is not list)
    ):
        _two_family_invalid()
    return value


def _two_family_manifest_fingerprint(document: dict[str, JsonValue]) -> str:
    fingerprint = _two_family_fingerprint(document["fingerprint"])
    unsigned = {key: value for key, value in document.items() if key != "fingerprint"}
    if fingerprint != f"sha256:{sha256(canonicalize(unsigned)).hexdigest()}":
        _two_family_invalid()
    return fingerprint


def _two_family_cutoff(value: object, *, require_z: bool = False) -> str:
    text = _two_family_text(value)
    if require_z and not text.endswith("Z"):
        _two_family_invalid()
    try:
        parsed = datetime.fromisoformat(
            text.removesuffix("Z") + ("+00:00" if text.endswith("Z") else "")
        )
    except ValueError as error:
        _two_family_fail_from("HK_V1_TWO_FAMILY_ACQUISITION_INVALID", error)
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != UTC.utcoffset(parsed)
        or parsed.microsecond != 0
    ):
        _two_family_invalid()
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _two_family_text(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        _two_family_invalid()
    return value


def _two_family_fingerprint(value: object) -> str:
    text = _two_family_text(value)
    if _FINGERPRINT.fullmatch(text) is None:
        _two_family_invalid()
    return text


def _two_family_int(value: object) -> int:
    if type(value) is not int or value < 0:
        _two_family_invalid()
    return value


def _two_family_texts(value: object, *, required: bool) -> tuple[str, ...]:
    try:
        typed = checked_json_value(value)
    except ValueError:
        _two_family_invalid()
    if type(typed) is not list:
        _two_family_invalid()
    result = tuple(_two_family_text(item) for item in typed)
    if (required and not result) or result != tuple(sorted(set(result))):
        _two_family_invalid()
    return result


def _two_family_ordered_texts(value: object, *, required: bool, unique: bool) -> tuple[str, ...]:
    try:
        typed = checked_json_value(value)
    except ValueError:
        _two_family_invalid()
    if type(typed) is not list:
        _two_family_invalid()
    result = tuple(_two_family_text(item) for item in typed)
    if (required and not result) or (unique and len(set(result)) != len(result)):
        _two_family_invalid()
    return result


def _two_family_invalid() -> Never:
    _two_family_fail("HK_V1_TWO_FAMILY_ACQUISITION_INVALID")


def _two_family_fail(code: str) -> Never:
    raise ValueError(code)


def _two_family_fail_from(code: str, error: Exception) -> Never:
    raise ValueError(code) from error
