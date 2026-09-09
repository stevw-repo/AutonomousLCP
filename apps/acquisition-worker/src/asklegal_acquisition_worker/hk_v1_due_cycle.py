"""Local-only, immutable Hong Kong V1 due-source capture activities.

The current checked-in Matrix does not admit any of these source roles.  This
module therefore deliberately has no connector or transport dependency: it
persists a complete account of each unproved observation instead of pretending
that an endpoint-free run acquired legal material.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import TYPE_CHECKING, Never, Protocol, TypedDict, cast
from weakref import ReferenceType, ref
from zoneinfo import ZoneInfo

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import TaskFailedError
from asklegal_evidence_vault import (
    ExactObjectReference,
    ImmutableVault,
    RetentionProfile,
    VaultCollision,
    VaultName,
    VaultWriteReceipt,
)
from asklegal_reporting import (
    DueChangeStatus,
    DueCycleKind,
    DueImmutableReference,
    DueRegisterBundle,
    DueSourceRegister,
    DueTerminalOutcome,
    DueTerminalReportReference,
    HongKongV1DueCycleError,
    HongKongV1DueCycleInstruction,
    HongKongV1DueCyclePlan,
    HongKongV1DueRequirement,
    HongKongV1DueTerminal,
    IssuedDueResultBinding,
    build_hk_v1_due_cycle_report,
    build_hk_v1_due_result_manifest,
    build_hk_v1_due_terminal,
    build_hk_v1_due_terminal_from_result_binding,
    derive_hk_v1_due_cycle_plan,
    hk_v1_due_cycle_manifest_key,
    hk_v1_due_family_acquisition_key,
    hk_v1_due_source_payload_key,
    hk_v1_due_source_result_manifest_key,
    hk_v1_due_source_terminal_key,
    load_hk_v1_coverage_matrix,
    parse_hk_v1_due_cycle_report,
    parse_hk_v1_due_register_bundle,
    parse_hk_v1_due_terminal,
)
from asklegal_reporting.hk_v1_due_cycle import (
    _register_validated_acquisition_due_result_binding,  # pyright: ignore[reportPrivateUsage]
)
from asklegal_source_connectors import (
    load_hk_cases_source_register,
    load_hk_legislation_source_register,
)

from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    CapturedVerifiedPayload,
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
)
from asklegal_acquisition_worker.hk_cases_acquisition import CasesAcquisitionManifest
from asklegal_acquisition_worker.hk_legislation_acquisition import (
    LegislationAcquisitionManifest,
    LegislationVerifiedItem,
)
from asklegal_acquisition_worker.hk_v1_due_predecessor import (
    DueCyclePredecessorConflict,
    DueCyclePredecessorState,
    DueCyclePredecessorStore,
    DueCyclePredecessorWriteReceipt,
)
from asklegal_acquisition_worker.source_admission_adapter import (
    AuthenticDueSourceAdapter,
    AuthenticDueSourceCapture,
)
from asklegal_acquisition_worker.source_role_evidence import SourceRoleDisposition

if TYPE_CHECKING:
    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

_RETENTION = RetentionProfile("hk-v1-due-cycle", "2099-12-31T00:00:00Z")
_CAPTURE_INPUT_INVALID = "DUE_CAPTURE_INPUT_INVALID"
_SOURCE_ADAPTER_INVALID = "DUE_SOURCE_ADAPTER_INVALID"
_SOURCE_ADAPTER_REQUIRED = "DUE_SOURCE_ADAPTER_REQUIRED"
_SOURCE_NOT_DUE = "DUE_SOURCE_NOT_DUE"
_PLAN_FINGERPRINT_MISMATCH = "DUE_PLAN_FINGERPRINT_MISMATCH"
_PAYLOAD_READBACK_INVALID = "DUE_PAYLOAD_READBACK_INVALID"
_ATTEMPT_READBACK_INVALID = "DUE_ATTEMPT_READBACK_INVALID"
_TERMINAL_READBACK_INVALID = "DUE_TERMINAL_READBACK_INVALID"
_FAILURE_INPUT_INVALID = "DUE_FAILURE_INPUT_INVALID"
_ASSEMBLY_INPUT_INVALID = "DUE_ASSEMBLY_INPUT_INVALID"
_MANIFEST_READBACK_INVALID = "DUE_MANIFEST_READBACK_INVALID"
_RETAINED_PROOF_INVALID = "DUE_RETAINED_BINDING_PROOF_INVALID"
_SOURCE_ACTIVITY_FAILED = "DUE_SOURCE_ACTIVITY_FAILED"
_PREDECESSOR_STATE_INVALID = "DUE_PREDECESSOR_STATE_INVALID"
_PREDECESSOR_STATE_CONFLICT = "DUE_PREDECESSOR_STATE_CONFLICT"
_ORCHESTRATOR_PLAN_INVALID = "DUE_ORCHESTRATOR_PLAN_INVALID"
_ORCHESTRATOR_CAPTURE_INVALID = "DUE_ORCHESTRATOR_CAPTURE_INVALID"
_ORCHESTRATOR_ASSEMBLY_INVALID = "DUE_ORCHESTRATOR_ASSEMBLY_INVALID"
_ORCHESTRATOR_FAMILY_RESULT_INVALID = "DUE_ORCHESTRATOR_FAMILY_RESULT_INVALID"
_FAMILY_EVIDENCE_INVALID = "DUE_FAMILY_EVIDENCE_INVALID"
_FAMILY_ORCHESTRATOR = "acquire_resumable_source_cycle"
_FAMILY_ORCHESTRATOR_VERSION = "1.0.0"
_FAMILY_EVIDENCE_SCHEMA = "asklegal.hk-v1.scheduled-family-acquisitions"
_FAMILY_EVIDENCE_VERSION = "1.0.0"
_FAMILY_COUNT = 2
_HONG_KONG = ZoneInfo("Asia/Hong_Kong")
_SHA256_FINGERPRINT_LENGTH = 71
_REGISTER_FILES = (
    "hk_legislation_source_register.json",
    "hk_cases_source_register.json",
)
_ADAPTER_SOURCE_IDS = frozenset(
    {
        "HK-CASE-HKLII-DISCOVERY",
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
        "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
    }
)
_CURRENT_FAMILY_SOURCE_IDS: dict[str, frozenset[str]] = {
    "CASES": frozenset(
        {
            "HK-CASE-HKLII-DISCOVERY",
            "HK-CASE-JUDICIARY-LRS-INVENTORY",
        }
    ),
    "LEGISLATION": frozenset(
        {
            "HK-LEG-BASIC-LAW-PORTAL",
            "HK-LEG-GLD-EGAZETTE",
            "HK-LEG-HKEL-CURRENT-DATA",
            "HK-LEG-HKEL-CURRENT-INVENTORY",
            "HK-LEG-HKEL-EDITORIAL-RECORDS",
            "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        }
    ),
}
_ADAPTER_REQUIREMENTS: dict[str, tuple[str, str]] = {
    "HK-CASE-HKLII-DISCOVERY": ("CASES", "asklegal.hk-v1.hk-case-hklii-discovery.result.v1"),
    "HK-CASE-JUDICIARY-LRS-INVENTORY": (
        "CASES",
        "asklegal.hk-v1.hk-case-judiciary-lrs-inventory.result.v1",
    ),
    "HK-LEG-BASIC-LAW-PORTAL": ("LEGISLATION", "asklegal.hk-v1.hk-leg-basic-law-portal.result.v1"),
    "HK-LEG-GLD-EGAZETTE": ("LEGISLATION", "asklegal.hk-v1.hk-leg-gld-egazette.result.v1"),
    "HK-LEG-HKEL-CURRENT-INVENTORY": (
        "LEGISLATION",
        "asklegal.hk-v1.hk-leg-hkel-current-inventory.result.v1",
    ),
    "HK-LEG-HKEL-EDITORIAL-RECORDS": (
        "LEGISLATION",
        "asklegal.hk-v1.hk-leg-hkel-editorial-records.result.v1",
    ),
    "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS": (
        "LEGISLATION",
        "asklegal.hk-v1.hk-leg-hkel-publication-specifications.result.v1",
    ),
    "HK-LEG-NPC-NATIONAL-LAWS-DATABASE": (
        "LEGISLATION",
        "asklegal.hk-v1.hk-leg-npc-national-laws-database.result.v1",
    ),
    "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS": (
        "LEGISLATION",
        "asklegal.hk-v1.hk-leg-npc-npcsc-official-materials.result.v1",
    ),
}


def _due_fail(code: str) -> Never:
    raise HongKongV1DueCycleError(code)


def _due_fail_from(code: str, error: Exception) -> Never:
    raise HongKongV1DueCycleError(code) from error


def _orchestrator_parse_fail(code: str, error: Exception) -> Never:
    """Preserve only this parser's own exact closed failure; normalize all other errors."""
    if type(error) is HongKongV1DueCycleError and error.args == (code,):
        raise error
    _due_fail_from(code, error)


class _FamilyRegisterSource(Protocol):
    """The common identity view returned by all three strict family parsers."""

    @property
    def source_id(self) -> str: ...


class _FamilyRegister(Protocol):
    """The common register identity view returned by all three family parsers."""

    @property
    def register_id(self) -> str: ...

    @property
    def register_version(self) -> str: ...

    @property
    def fingerprint(self) -> str: ...

    @property
    def sources(self) -> tuple[_FamilyRegisterSource, ...]: ...


class DueRegisterSourceOutput(TypedDict):
    """Durable primitive projection for one source within one fixed register."""

    source_id: str
    source_version: str
    endpoint_ids: list[str]
    operational_state: str
    blockers: list[str]


class DueRegisterOutput(TypedDict):
    """Durable primitive projection for one fixed source register."""

    register_id: str
    register_version: str
    register_fingerprint: str
    sources: list[DueRegisterSourceOutput]


class DueRequirementOutput(TypedDict):
    """Durable primitive projection for one Matrix-derived due requirement."""

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


class DuePlanOutput(TypedDict):
    """Scheduler-safe plan projection with no caller-owned policy facts."""

    schema_id: str
    schema_version: str
    cycle_id: str
    cycle_kind: str
    instruction: dict[str, str]
    plan_fingerprint: str
    requirements_fingerprint: str
    registers: list[DueRegisterOutput]
    predecessor_fingerprint: str | None
    requirements: list[DueRequirementOutput]
    source_ids: list[str]


@dataclass(frozen=True, slots=True)
class _DueReceiptSnapshot:
    """Worker-owned receipt facts, never passed back into a vault adapter."""

    reference: ExactObjectReference
    created: bool


@dataclass(frozen=True, slots=True, weakref_slot=True)
class _RetainedBindingProof:
    """Private evidence that one exact retained payload and attempt were rebuilt."""

    binding_id: int


@dataclass(frozen=True, slots=True)
class _DueSourceOutcomeFacts:
    """Closed source terminal counts and outcome reconstructed from a payload."""

    outcome: DueTerminalOutcome
    change_status: DueChangeStatus
    failure_codes: tuple[str, ...]
    expected_count: int
    retained_count: int
    not_published_count: int
    gap_count: int
    failed_count: int
    evidence_kind: str = "NONE"


_UNADMITTED_FACTS = _DueSourceOutcomeFacts(
    DueTerminalOutcome.INCOMPLETE_OBSERVATION,
    DueChangeStatus.NOT_PROVED,
    (),
    0,
    0,
    0,
    0,
    0,
)
_FAILED_FACTS = _DueSourceOutcomeFacts(
    DueTerminalOutcome.FAILED,
    DueChangeStatus.NOT_PROVED,
    (_SOURCE_ACTIVITY_FAILED,),
    1,
    0,
    0,
    0,
    1,
)


_RetainedProofRegistration = tuple[
    ReferenceType[IssuedDueResultBinding], ReferenceType[_RetainedBindingProof], bytes
]
_RETAINED_BINDING_PROOFS: dict[int, _RetainedProofRegistration] = {}
_RETAINED_PROOF_BINDING_IDS: dict[int, int] = {}
_ReconstructedBindingRegistration = tuple[ReferenceType[IssuedDueResultBinding], bytes]
_RECONSTRUCTED_ATTEMPT_BINDINGS: dict[int, _ReconstructedBindingRegistration] = {}
_RETAINED_BINDING_LOCK = Lock()


def _fixed_register_bundles() -> tuple[DueRegisterBundle, ...]:
    """Load only repository-owned resources and prove each family loader accepts it."""
    root = resources.files("asklegal_source_connectors")
    resources_by_loader = (
        ("hk_legislation_source_register.json", load_hk_legislation_source_register),
        ("hk_cases_source_register.json", load_hk_cases_source_register),
    )
    bundles: list[DueRegisterBundle] = []
    for filename, loader in resources_by_loader:
        bundles.append(_bundle_from_resource_snapshot(root.joinpath(filename), filename, loader))
    return tuple(bundles)


def _bundle_from_resource_snapshot(
    resource: Traversable, filename: str, loader: Callable[[Path], _FamilyRegister]
) -> DueRegisterBundle:
    """Validate and project exactly one owned register byte snapshot."""
    try:
        content = resource.read_bytes()
        if type(content) is not bytes:
            _due_fail("DUE_REGISTER_RESOURCE_INVALID")
        bundle = parse_hk_v1_due_register_bundle(content)
        with TemporaryDirectory(prefix="asklegal-hk-v1-register-") as temporary_root:
            path = Path(temporary_root, filename)
            path.write_bytes(content)
            family_register = loader(path)
        _assert_family_register_matches_bundle(family_register, bundle)
    except (AttributeError, OSError, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        _due_fail_from("DUE_REGISTER_RESOURCE_INVALID", error)
    else:
        return bundle


def _assert_family_register_matches_bundle(
    family_register: _FamilyRegister, bundle: DueRegisterBundle
) -> None:
    """Use each strict family parser result as a same-snapshot identity witness."""
    try:
        register_id = family_register.register_id
        register_version = family_register.register_version
        fingerprint = family_register.fingerprint
        sources = family_register.sources
        source_ids = tuple(source.source_id for source in sources)
    except (AttributeError, TypeError, ValueError) as error:
        _due_fail_from("DUE_REGISTER_RESOURCE_INVALID", error)
    if (
        type(register_id) is not str
        or type(register_version) is not str
        or type(fingerprint) is not str
        or type(sources) is not tuple
        or (register_id, register_version, fingerprint)
        != (bundle.register_id, bundle.register_version, bundle.register_fingerprint)
        or source_ids != tuple(source.source_id for source in bundle.sources)
    ):
        _due_fail("DUE_REGISTER_RESOURCE_INVALID")


def _reference(value: ExactObjectReference) -> DueImmutableReference:
    return DueImmutableReference(
        value.vault.value, value.logical_key, value.version_id, value.fingerprint, value.byte_length
    )


def _reference_body(value: ExactObjectReference) -> dict[str, JsonValue]:
    """Return only a rebuilt immutable-reference projection to activity callers."""
    reference = _reference(value)
    return {
        "vault": reference.vault,
        "logical_key": reference.logical_key,
        "version_id": reference.version_id,
        "fingerprint": reference.fingerprint,
        "byte_length": reference.byte_length,
    }


def _read_due_reference(
    vault: ImmutableVault,
    reference: DueImmutableReference,
    code: str,
) -> bytes:
    """Read an input reference only after rebuilding exact primitive vault facts."""
    try:
        request = ExactObjectReference(
            VaultName(reference.vault),
            reference.logical_key,
            reference.version_id,
            reference.fingerprint,
            reference.byte_length,
        )
        content = vault.read_exact(request)
    except Exception as error:
        raise HongKongV1DueCycleError(code) from error
    if (
        type(content) is not bytes
        or f"sha256:{sha256(content).hexdigest()}" != reference.fingerprint
        or len(content) != reference.byte_length
    ):
        raise HongKongV1DueCycleError(code)
    return content


def _due_reference_from_document(value: object, code: str) -> DueImmutableReference:
    """Rebuild a retained nested immutable reference from canonical JSON only."""
    try:
        document = checked_json_value(value)
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(code) from error
    if not isinstance(document, dict) or frozenset(document) != frozenset(
        {"vault", "logical_key", "version_id", "fingerprint", "byte_length"}
    ):
        raise HongKongV1DueCycleError(code)
    vault = document["vault"]
    logical_key = document["logical_key"]
    version_id = document["version_id"]
    fingerprint = document["fingerprint"]
    byte_length = document["byte_length"]
    if (
        type(vault) is not str
        or type(logical_key) is not str
        or type(version_id) is not str
        or type(fingerprint) is not str
        or type(byte_length) is not int
    ):
        raise HongKongV1DueCycleError(code)
    try:
        return DueImmutableReference(vault, logical_key, version_id, fingerprint, byte_length)
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(code) from error


def _plan(
    instruction: HongKongV1DueCycleInstruction, predecessor_fingerprint: str | None = None
) -> HongKongV1DueCyclePlan:
    return derive_hk_v1_due_cycle_plan(
        instruction,
        load_hk_v1_coverage_matrix(),
        _fixed_register_bundles(),
        predecessor_fingerprint,
    )


def _same_instruction(
    left: HongKongV1DueCycleInstruction, right: HongKongV1DueCycleInstruction
) -> bool:
    """Compare every strict instruction primitive without accepting a partial replay."""
    return (
        left.cycle_id == right.cycle_id
        and left.cycle_kind is right.cycle_kind
        and left.scheduled_at == right.scheduled_at
        and left.observation_cutoff == right.observation_cutoff
        and left.matrix_revision == right.matrix_revision
        and left.matrix_fingerprint == right.matrix_fingerprint
    )


def _rebuild_predecessor_state(value: object) -> DueCyclePredecessorState:
    """Rebuild every retained-state primitive before it influences a plan."""
    if type(value) is not DueCyclePredecessorState:
        _due_fail(_PREDECESSOR_STATE_INVALID)
    try:
        rebuilt = DueCyclePredecessorState(
            value.instruction,
            value.plan_fingerprint,
            value.predecessor_fingerprint,
            value.manifest_reference,
            value.report_fingerprint,
        )
        if type(value.state_fingerprint) is not str or (
            value.state_fingerprint != rebuilt.state_fingerprint
        ):
            _due_fail(_PREDECESSOR_STATE_INVALID)
    except HongKongV1DueCycleError as error:
        _due_fail_from(_PREDECESSOR_STATE_INVALID, error)
    except (AttributeError, TypeError, ValueError) as error:
        _due_fail_from(_PREDECESSOR_STATE_INVALID, error)
    return rebuilt


def _rebuild_predecessor_receipt(value: object) -> DueCyclePredecessorWriteReceipt:
    """Reject a foreign CAS acknowledgement before reporting cycle-state publication."""
    if type(value) is not DueCyclePredecessorWriteReceipt:
        _due_fail(_PREDECESSOR_STATE_INVALID)
    try:
        state = _rebuild_predecessor_state(value.state)
        if type(value.created) is not bool:
            _due_fail(_PREDECESSOR_STATE_INVALID)
        return DueCyclePredecessorWriteReceipt(state, value.created)
    except (AttributeError, TypeError, ValueError) as error:
        _due_fail_from(_PREDECESSOR_STATE_INVALID, error)


def _resolve_predecessor_plan(
    store: DueCyclePredecessorStore, instruction: HongKongV1DueCycleInstruction
) -> HongKongV1DueCyclePlan:
    """Derive only from the current retained state, including exact same-cycle replay."""
    try:
        loaded = store.load(instruction.cycle_kind)
    except Exception as error:  # noqa: BLE001 - store implementations are an untrusted port.
        _due_fail_from(_PREDECESSOR_STATE_INVALID, error)
    state = None if loaded is None else _rebuild_predecessor_state(loaded)
    if state is None:
        return _plan(instruction)
    if state.instruction.cycle_kind is not instruction.cycle_kind:
        _due_fail(_PREDECESSOR_STATE_INVALID)
    stored_instruction = state.instruction
    if stored_instruction.cycle_id == instruction.cycle_id:
        if not _same_instruction(stored_instruction, instruction):
            _due_fail(_PREDECESSOR_STATE_INVALID)
        plan = _plan(instruction, state.predecessor_fingerprint)
        if plan.plan_fingerprint != state.plan_fingerprint:
            _due_fail(_PREDECESSOR_STATE_INVALID)
        return plan
    if (
        instruction.scheduled_at <= stored_instruction.scheduled_at
        or instruction.observation_cutoff <= stored_instruction.observation_cutoff
    ):
        _due_fail(_PREDECESSOR_STATE_INVALID)
    return _plan(instruction, state.state_fingerprint)


def _plan_body(plan: HongKongV1DueCyclePlan) -> DuePlanOutput:
    """Detach the complete activity-derived plan needed by deterministic replay."""
    return {
        "schema_id": "asklegal.hk-v1-due-cycle-plan",
        "schema_version": "1.0.0",
        "cycle_id": plan.instruction.cycle_id,
        "cycle_kind": plan.instruction.cycle_kind.value,
        "instruction": {
            "cycle_id": plan.instruction.cycle_id,
            "cycle_kind": plan.instruction.cycle_kind.value,
            "scheduled_at": plan.instruction.scheduled_at,
            "observation_cutoff": plan.instruction.observation_cutoff,
            "matrix_revision": plan.instruction.matrix_revision,
            "matrix_fingerprint": plan.instruction.matrix_fingerprint,
        },
        "plan_fingerprint": plan.plan_fingerprint,
        "requirements_fingerprint": plan.requirements_fingerprint,
        "registers": [
            {
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
            for register in plan.registers
        ],
        "predecessor_fingerprint": plan.predecessor_fingerprint,
        "requirements": [
            {
                "material_family": requirement.material_family,
                "source_id": requirement.source_id,
                "source_version": requirement.source_version,
                "cadence": requirement.cadence,
                "outage_impact": requirement.outage_impact,
                "register_id": requirement.register_id,
                "register_version": requirement.register_version,
                "register_fingerprint": requirement.register_fingerprint,
                "matrix_policy_fingerprint": requirement.matrix_policy_fingerprint,
                "policy_conflict": requirement.policy_conflict,
                "result_schema": requirement.result_schema,
                "technical_state": requirement.technical_state,
                "rights_state": requirement.rights_state,
            }
            for requirement in plan.requirements
        ],
        "source_ids": [requirement.source_id for requirement in plan.requirements],
    }


def _capture_input(
    value: object,
) -> tuple[HongKongV1DueCycleInstruction, str, str, DueImmutableReference | None]:
    try:
        document = checked_json_value(value)
        if not isinstance(document, dict) or frozenset(document) not in {
            frozenset({"instruction", "expected_plan_fingerprint", "source_id"}),
            frozenset(
                {
                    "instruction",
                    "expected_plan_fingerprint",
                    "source_id",
                    "family_evidence_reference",
                }
            ),
        }:
            raise HongKongV1DueCycleError(_CAPTURE_INPUT_INVALID)
        instruction = HongKongV1DueCycleInstruction.from_json(document["instruction"])
        plan_fingerprint: JsonValue = document["expected_plan_fingerprint"]
        source_id: JsonValue = document["source_id"]
        if type(plan_fingerprint) is not str or type(source_id) is not str:
            raise HongKongV1DueCycleError(_CAPTURE_INPUT_INVALID)
        family_reference = (
            None
            if "family_evidence_reference" not in document
            else _due_reference_from_document(
                document["family_evidence_reference"], _CAPTURE_INPUT_INVALID
            )
        )
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(_CAPTURE_INPUT_INVALID) from error
    else:
        return instruction, plan_fingerprint, source_id, family_reference


def _failure_input(value: object) -> tuple[HongKongV1DueCycleInstruction, str, str]:
    """Accept only the closed failure-recording activity input."""
    try:
        document = checked_json_value(value)
        if not isinstance(document, dict) or frozenset(document) != frozenset(
            {"instruction", "expected_plan_fingerprint", "source_id", "failure_code"}
        ):
            raise HongKongV1DueCycleError(_FAILURE_INPUT_INVALID)
        instruction = HongKongV1DueCycleInstruction.from_json(document["instruction"])
        fingerprint: JsonValue = document["expected_plan_fingerprint"]
        source_id: JsonValue = document["source_id"]
        failure_code: JsonValue = document["failure_code"]
        if (
            type(fingerprint) is not str
            or type(source_id) is not str
            or type(failure_code) is not str
            or failure_code != _SOURCE_ACTIVITY_FAILED
        ):
            raise HongKongV1DueCycleError(_FAILURE_INPUT_INVALID)
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(_FAILURE_INPUT_INVALID) from error
    return instruction, fingerprint, source_id


def _assembly_input(
    value: object,
) -> tuple[HongKongV1DueCycleInstruction, str, tuple[DueTerminalReportReference, ...]]:
    """Accept terminal references only; policy and terminal contents are reloaded."""
    try:
        document = checked_json_value(value)
        if not isinstance(document, dict) or frozenset(document) != frozenset(
            {"instruction", "expected_plan_fingerprint", "terminal_references"}
        ):
            raise HongKongV1DueCycleError(_ASSEMBLY_INPUT_INVALID)
        instruction = HongKongV1DueCycleInstruction.from_json(document["instruction"])
        fingerprint: JsonValue = document["expected_plan_fingerprint"]
        raw_references: JsonValue = document["terminal_references"]
        if type(fingerprint) is not str or not isinstance(raw_references, list):
            raise HongKongV1DueCycleError(_ASSEMBLY_INPUT_INVALID)
        references: list[DueTerminalReportReference] = []
        for item in raw_references:
            if not isinstance(item, dict) or frozenset(item) != frozenset(
                {"source_id", "reference"}
            ):
                raise HongKongV1DueCycleError(_ASSEMBLY_INPUT_INVALID)
            source_id = item["source_id"]
            raw_reference = item["reference"]
            if (
                type(source_id) is not str
                or not isinstance(raw_reference, dict)
                or frozenset(raw_reference)
                != frozenset({"vault", "logical_key", "version_id", "fingerprint", "byte_length"})
            ):
                raise HongKongV1DueCycleError(_ASSEMBLY_INPUT_INVALID)
            vault = raw_reference["vault"]
            logical_key = raw_reference["logical_key"]
            version_id = raw_reference["version_id"]
            reference_fingerprint = raw_reference["fingerprint"]
            byte_length = raw_reference["byte_length"]
            if (
                type(vault) is not str
                or type(logical_key) is not str
                or type(version_id) is not str
                or type(reference_fingerprint) is not str
                or type(byte_length) is not int
            ):
                raise HongKongV1DueCycleError(_ASSEMBLY_INPUT_INVALID)
            references.append(
                DueTerminalReportReference(
                    source_id,
                    DueImmutableReference(
                        vault,
                        logical_key,
                        version_id,
                        reference_fingerprint,
                        byte_length,
                    ),
                )
            )
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(_ASSEMBLY_INPUT_INVALID) from error
    return instruction, fingerprint, tuple(references)


def _requirement_for(plan: HongKongV1DueCyclePlan, source_id: str) -> HongKongV1DueRequirement:
    if source_id not in _ADAPTER_SOURCE_IDS:
        raise HongKongV1DueCycleError(_SOURCE_ADAPTER_INVALID)
    matches = tuple(item for item in plan.requirements if item.source_id == source_id)
    if len(matches) != 1:
        raise HongKongV1DueCycleError(_SOURCE_NOT_DUE)
    requirement = matches[0]
    expected = _ADAPTER_REQUIREMENTS.get(source_id)
    if expected is None or (requirement.material_family, requirement.result_schema) != expected:
        raise HongKongV1DueCycleError(_SOURCE_ADAPTER_INVALID)
    return requirement


def _receipt_snapshot(
    receipt: object, expected_key: str, expected_content: bytes, code: str
) -> _DueReceiptSnapshot:
    """Rebuild a private exact receipt snapshot before any vault callback."""
    try:
        if type(receipt) is not VaultWriteReceipt:
            _due_fail(code)
        created = receipt.created
        read_back_verified = receipt.read_back_verified
        retention = receipt.retention
        original = receipt.reference
        if type(created) is not bool or read_back_verified is not True:
            _due_fail(code)
        if type(retention) is not RetentionProfile:
            _due_fail(code)
        retained_retention = RetentionProfile(
            retention.profile_id, retention.retain_until, retention.legal_hold
        )
        if retained_retention != _RETENTION:
            _due_fail(code)
        if type(original) is not ExactObjectReference:
            _due_fail(code)
        reference = ExactObjectReference(
            original.vault,
            original.logical_key,
            original.version_id,
            original.fingerprint,
            original.byte_length,
        )
        fingerprint = f"sha256:{sha256(expected_content).hexdigest()}"
        if (
            reference.vault is not VaultName.PRIMARY
            or reference.logical_key != expected_key
            or reference.fingerprint != fingerprint
            or reference.byte_length != len(expected_content)
        ):
            _due_fail(code)
    except (AttributeError, TypeError, ValueError) as error:
        if isinstance(error, HongKongV1DueCycleError):
            raise
        raise HongKongV1DueCycleError(code) from error
    else:
        return _DueReceiptSnapshot(reference, created)


def _read_exact_snapshot(vault: ImmutableVault, snapshot: _DueReceiptSnapshot, code: str) -> bytes:
    """Pass a disposable clone to the vault and retain only worker-owned facts."""
    reference = snapshot.reference
    try:
        request = ExactObjectReference(
            reference.vault,
            reference.logical_key,
            reference.version_id,
            reference.fingerprint,
            reference.byte_length,
        )
        content = vault.read_exact(request)
    except Exception as error:
        raise HongKongV1DueCycleError(code) from error
    if type(content) is not bytes:
        raise HongKongV1DueCycleError(code)
    return content


def _resolved_due_payload_snapshot(
    vault: ImmutableVault,
    payload_key: str,
    normal_payload: bytes,
    failed_payload: bytes,
) -> tuple[bool, _DueReceiptSnapshot] | None:
    """Classify one adapter-resolved payload only after exact policy and byte verification."""
    try:
        original = vault.resolve_current(payload_key)
    except Exception as error:
        raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID) from error
    if original is None:
        return None
    if (
        type(original) is not ExactObjectReference
        or original.vault is not VaultName.PRIMARY
        or original.logical_key != payload_key
    ):
        raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
    try:
        reference = ExactObjectReference(
            original.vault,
            original.logical_key,
            original.version_id,
            original.fingerprint,
            original.byte_length,
        )
        retention_request = ExactObjectReference(
            reference.vault,
            reference.logical_key,
            reference.version_id,
            reference.fingerprint,
            reference.byte_length,
        )
        raw_retention = vault.retention(retention_request)
        if retention_request != reference:
            _due_fail(_PAYLOAD_READBACK_INVALID)
        if type(raw_retention) is not RetentionProfile:
            _due_fail(_PAYLOAD_READBACK_INVALID)
        retained_retention = RetentionProfile(
            raw_retention.profile_id,
            raw_retention.retain_until,
            raw_retention.legal_hold,
        )
    except Exception as error:
        raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID) from error
    if retained_retention != _RETENTION:
        raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
    snapshot = _DueReceiptSnapshot(reference, created=False)
    retained_payload = _read_exact_snapshot(vault, snapshot, _PAYLOAD_READBACK_INVALID)
    if retained_payload == normal_payload:
        return True, snapshot
    if retained_payload == failed_payload:
        return False, snapshot
    raise VaultCollision(payload_key)


def _capture_request_body(
    instruction: HongKongV1DueCycleInstruction, plan_fingerprint: str, source_id: str
) -> dict[str, object]:
    """Rebuild a closed capture input without carrying retained object identity."""
    return {
        "instruction": {
            "cycle_id": instruction.cycle_id,
            "cycle_kind": instruction.cycle_kind.value,
            "scheduled_at": instruction.scheduled_at,
            "observation_cutoff": instruction.observation_cutoff,
            "matrix_revision": instruction.matrix_revision,
            "matrix_fingerprint": instruction.matrix_fingerprint,
        },
        "expected_plan_fingerprint": plan_fingerprint,
        "source_id": source_id,
    }


def _persist_due_failure_chain(
    vault: ImmutableVault,
    plan: HongKongV1DueCyclePlan,
    requirement: HongKongV1DueRequirement,
    payload: bytes,
    payload_receipt_snapshot: _DueReceiptSnapshot,
) -> dict[str, object]:
    """Create or replay the deterministic FAILED payload, attempt, and terminal chain."""
    source_id = requirement.source_id
    payload_key = hk_v1_due_source_payload_key(plan.instruction.cycle_id, source_id)
    if (
        payload_receipt_snapshot.reference.vault is not VaultName.PRIMARY
        or payload_receipt_snapshot.reference.logical_key != payload_key
    ):
        raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
    retained_payload = _read_exact_snapshot(
        vault, payload_receipt_snapshot, _PAYLOAD_READBACK_INVALID
    )
    if retained_payload != payload:
        raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
    payload_reference = _reference(payload_receipt_snapshot.reference)
    payload_binding = _binding_from_retained_failed_payload(
        retained_payload, plan, requirement, payload_reference
    )
    attempt, _ = build_hk_v1_due_result_manifest(payload_binding)
    attempt_key = hk_v1_due_source_result_manifest_key(plan.instruction.cycle_id, source_id)
    attempt_receipt = _conditional_create(vault, attempt_key, attempt, _ATTEMPT_READBACK_INVALID)
    attempt_snapshot = _receipt_snapshot(
        attempt_receipt, attempt_key, attempt, _ATTEMPT_READBACK_INVALID
    )
    retained_attempt = _read_exact_snapshot(vault, attempt_snapshot, _ATTEMPT_READBACK_INVALID)
    binding = _binding_from_retained_attempt(retained_attempt, payload_binding)
    binding = _consume_retained_binding_proof(binding, _retained_binding_proof(binding))
    terminal = build_hk_v1_due_terminal_from_result_binding(
        binding, _reference(attempt_snapshot.reference)
    )
    terminal_bytes, terminal_fingerprint = build_hk_v1_due_terminal(terminal)
    terminal_key = hk_v1_due_source_terminal_key(plan.instruction.cycle_id, source_id)
    terminal_receipt = _conditional_create(
        vault, terminal_key, terminal_bytes, _TERMINAL_READBACK_INVALID
    )
    terminal_snapshot = _receipt_snapshot(
        terminal_receipt, terminal_key, terminal_bytes, _TERMINAL_READBACK_INVALID
    )
    read_back = _read_exact_snapshot(vault, terminal_snapshot, _TERMINAL_READBACK_INVALID)
    try:
        parsed = parse_hk_v1_due_terminal(read_back)
        parsed_bytes, parsed_fingerprint = build_hk_v1_due_terminal(parsed)
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(_TERMINAL_READBACK_INVALID) from error
    if (
        read_back != terminal_bytes
        or parsed_bytes != terminal_bytes
        or parsed_fingerprint != terminal_fingerprint
        or parsed.result_fingerprint != payload_reference.fingerprint
        or parsed.attempt_manifest != _reference(attempt_snapshot.reference)
    ):
        raise HongKongV1DueCycleError(_TERMINAL_READBACK_INVALID)
    return {
        "source_id": source_id,
        "plan_fingerprint": plan.plan_fingerprint,
        "terminal_reference": _reference_body(terminal_snapshot.reference),
        "payload_created": payload_receipt_snapshot.created,
        "attempt_created": attempt_snapshot.created,
        "terminal_created": terminal_snapshot.created,
    }


def _conditional_create(
    vault: ImmutableVault, logical_key: str, content: bytes, code: str
) -> VaultWriteReceipt:
    """Create one fixed object while preserving only an exact collision outcome."""
    try:
        return vault.conditional_create(logical_key, content, _RETENTION)
    except VaultCollision:
        raise
    except Exception as error:
        raise HongKongV1DueCycleError(code) from error


def _registered_blockers(
    plan: HongKongV1DueCyclePlan, requirement: HongKongV1DueRequirement
) -> tuple[str, ...]:
    for register in plan.registers:
        for source in register.sources:
            if source.source_id == requirement.source_id:
                return source.blockers
    raise HongKongV1DueCycleError(_SOURCE_ADAPTER_INVALID)


def _unadmitted_codes(requirement: HongKongV1DueRequirement) -> tuple[str, ...]:
    codes: set[str] = set()
    if requirement.technical_state != "ADMITTED":
        codes.add("SOURCE_TECHNICAL_ADMISSION_MISSING")
    if requirement.rights_state != "ADMITTED":
        codes.add("SOURCE_RIGHTS_ADMISSION_MISSING")
    if requirement.policy_conflict is not None:
        codes.add(requirement.policy_conflict)
    return tuple(sorted(codes))


def _unadmitted_payload(
    plan: HongKongV1DueCyclePlan, requirement: HongKongV1DueRequirement
) -> bytes:
    return _source_payload(
        plan,
        requirement,
        _DueSourceOutcomeFacts(
            _UNADMITTED_FACTS.outcome,
            _UNADMITTED_FACTS.change_status,
            _unadmitted_codes(requirement),
            _UNADMITTED_FACTS.expected_count,
            _UNADMITTED_FACTS.retained_count,
            _UNADMITTED_FACTS.not_published_count,
            _UNADMITTED_FACTS.gap_count,
            _UNADMITTED_FACTS.failed_count,
        ),
    )


def _failed_payload(plan: HongKongV1DueCyclePlan, requirement: HongKongV1DueRequirement) -> bytes:
    """Record one closed accounting failure without diagnostics."""
    return _source_payload(plan, requirement, _FAILED_FACTS)


def _source_payload(
    plan: HongKongV1DueCyclePlan,
    requirement: HongKongV1DueRequirement,
    facts: _DueSourceOutcomeFacts,
) -> bytes:
    document: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1-due-source-payload",
        "schema_version": "1.0.0",
        "cycle_id": plan.instruction.cycle_id,
        "plan_fingerprint": plan.plan_fingerprint,
        "source_id": requirement.source_id,
        "outcome": facts.outcome.value,
        "change_status": facts.change_status.value,
        "failure_codes": list(facts.failure_codes),
        "registered_blockers": list(_registered_blockers(plan, requirement)),
        "expected_count": facts.expected_count,
        "retained_count": facts.retained_count,
        "not_published_count": facts.not_published_count,
        "gap_count": facts.gap_count,
        "failed_count": facts.failed_count,
    }
    if facts.evidence_kind != "NONE":
        document["evidence_kind"] = facts.evidence_kind
    return canonicalize(checked_json_value(document))


def _binding_from_retained_payload(
    content: bytes,
    plan: HongKongV1DueCyclePlan,
    requirement: HongKongV1DueRequirement,
    reference: DueImmutableReference,
) -> IssuedDueResultBinding:
    """Strictly replay the fixed unadmitted adapter result from retained bytes."""
    return _binding_from_retained_source_payload(
        content,
        plan,
        requirement,
        reference,
        _DueSourceOutcomeFacts(
            _UNADMITTED_FACTS.outcome,
            _UNADMITTED_FACTS.change_status,
            _unadmitted_codes(requirement),
            _UNADMITTED_FACTS.expected_count,
            _UNADMITTED_FACTS.retained_count,
            _UNADMITTED_FACTS.not_published_count,
            _UNADMITTED_FACTS.gap_count,
            _UNADMITTED_FACTS.failed_count,
        ),
    )


def _binding_from_retained_failed_payload(
    content: bytes,
    plan: HongKongV1DueCyclePlan,
    requirement: HongKongV1DueRequirement,
    reference: DueImmutableReference,
) -> IssuedDueResultBinding:
    return _binding_from_retained_source_payload(
        content,
        plan,
        requirement,
        reference,
        _FAILED_FACTS,
    )


def _binding_from_retained_authentic_payload(  # noqa: PLR0913, PLR0917
    content: bytes,
    plan: HongKongV1DueCyclePlan,
    requirement: HongKongV1DueRequirement,
    reference: DueImmutableReference,
    facts: _DueSourceOutcomeFacts,
    evidence_reference: DueImmutableReference | None,
) -> IssuedDueResultBinding:
    """Rebuild one authentic source assertion only from its exact retained bytes."""
    return _binding_from_retained_source_payload(
        content,
        plan,
        requirement,
        reference,
        facts,
        evidence_reference,
    )


def _authentic_facts(capture: AuthenticDueSourceCapture) -> _DueSourceOutcomeFacts:
    """Copy the exact adapter result into the private closed accounting type."""
    return _DueSourceOutcomeFacts(
        capture.outcome,
        capture.change_status,
        capture.failure_codes,
        capture.expected_count,
        capture.retained_count,
        capture.not_published_count,
        capture.gap_count,
        capture.failed_count,
        capture.evidence_kind,
    )


def _source_evidence_key(cycle_id: str, source_id: str) -> str:
    """Place one source manifest beside its fixed payload/attempt/terminal chain."""
    payload_key = hk_v1_due_source_payload_key(cycle_id, source_id)
    if not payload_key.endswith("/payload.json"):
        raise HongKongV1DueCycleError(_SOURCE_ADAPTER_INVALID)
    return payload_key.removesuffix("payload.json") + "evidence.json"


def _binding_from_retained_source_payload(  # noqa: PLR0913, PLR0917
    content: bytes,
    plan: HongKongV1DueCyclePlan,
    requirement: HongKongV1DueRequirement,
    reference: DueImmutableReference,
    facts: _DueSourceOutcomeFacts,
    evidence_reference: DueImmutableReference | None = None,
) -> IssuedDueResultBinding:
    """Rebuild one closed source result from exact retained adapter bytes."""
    try:
        document = parse_json_bytes(content, max_bytes=65_536)
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID) from error
    if canonicalize(checked_json_value(document)) != content or content != _source_payload(
        plan,
        requirement,
        facts,
    ):
        raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
    return IssuedDueResultBinding(
        plan.instruction.cycle_id,
        plan.plan_fingerprint,
        plan.instruction.matrix_fingerprint,
        requirement,
        plan.instruction.observation_cutoff,
        requirement.result_schema,
        "1.0.0",
        reference,
        evidence_reference,
        facts.outcome,
        facts.change_status,
        facts.failure_codes,
        facts.expected_count,
        facts.retained_count,
        facts.not_published_count,
        facts.gap_count,
        facts.failed_count,
        _registered_blockers(plan, requirement),
        facts.evidence_kind,
    )


def _binding_from_retained_attempt(
    content: bytes, binding: IssuedDueResultBinding
) -> IssuedDueResultBinding:
    """Parse/rebuild the persisted attempt before it may receive issuance authority."""
    try:
        document = parse_json_bytes(content, max_bytes=65_536)
        expected, _ = build_hk_v1_due_result_manifest(binding)
    except (TypeError, ValueError, HongKongV1DueCycleError) as error:
        raise HongKongV1DueCycleError(_ATTEMPT_READBACK_INVALID) from error
    if canonicalize(checked_json_value(document)) != content or content != expected:
        raise HongKongV1DueCycleError(_ATTEMPT_READBACK_INVALID)
    rebuilt = IssuedDueResultBinding(
        binding.cycle_id,
        binding.plan_fingerprint,
        binding.matrix_fingerprint,
        binding.requirement,
        binding.observation_cutoff,
        binding.result_schema,
        binding.result_schema_version,
        binding.payload_reference,
        binding.evidence_reference,
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
    binding_id = id(rebuilt)

    def cleanup(dead: ReferenceType[IssuedDueResultBinding]) -> None:
        with _RETAINED_BINDING_LOCK:
            current = _RECONSTRUCTED_ATTEMPT_BINDINGS.get(binding_id)
            if current is not None and current[0] is dead:
                del _RECONSTRUCTED_ATTEMPT_BINDINGS[binding_id]

    with _RETAINED_BINDING_LOCK:
        _RECONSTRUCTED_ATTEMPT_BINDINGS[binding_id] = (ref(rebuilt, cleanup), expected)
    return rebuilt


def _retained_binding_proof(
    binding: IssuedDueResultBinding,
) -> _RetainedBindingProof:
    """Mint a worker-private proof only after exact payload/attempt reconstruction."""
    try:
        snapshot, _ = build_hk_v1_due_result_manifest(binding)
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(_RETAINED_PROOF_INVALID) from error
    binding_id = id(binding)
    with _RETAINED_BINDING_LOCK:
        reconstructed = _RECONSTRUCTED_ATTEMPT_BINDINGS.pop(binding_id, None)
        if (
            reconstructed is None
            or reconstructed[0]() is not binding
            or reconstructed[1] != snapshot
        ):
            raise HongKongV1DueCycleError(_RETAINED_PROOF_INVALID)
        proof = _RetainedBindingProof(binding_id)
        proof_id = id(proof)

    def cleanup_binding(dead: ReferenceType[IssuedDueResultBinding]) -> None:
        with _RETAINED_BINDING_LOCK:
            current = _RETAINED_BINDING_PROOFS.get(binding_id)
            if current is not None and current[0] is dead:
                del _RETAINED_BINDING_PROOFS[binding_id]
                retained_proof = current[1]()
                if retained_proof is not None:
                    _RETAINED_PROOF_BINDING_IDS.pop(proof_id, None)

    def cleanup_proof(dead: ReferenceType[_RetainedBindingProof]) -> None:
        with _RETAINED_BINDING_LOCK:
            current = _RETAINED_BINDING_PROOFS.get(binding_id)
            if current is not None and current[1] is dead:
                del _RETAINED_BINDING_PROOFS[binding_id]
            _RETAINED_PROOF_BINDING_IDS.pop(proof_id, None)

    with _RETAINED_BINDING_LOCK:
        _RETAINED_BINDING_PROOFS[binding_id] = (
            ref(binding, cleanup_binding),
            ref(proof, cleanup_proof),
            snapshot,
        )
        _RETAINED_PROOF_BINDING_IDS[proof_id] = binding_id
    return proof


def _consume_retained_binding_proof(
    binding: IssuedDueResultBinding, proof: _RetainedBindingProof
) -> IssuedDueResultBinding:
    """Consume an exact private retained-read proof at the sole registrar gateway."""
    with _RETAINED_BINDING_LOCK:
        binding_id = _RETAINED_PROOF_BINDING_IDS.pop(id(proof), None)
        registration = (
            None if binding_id is None else _RETAINED_BINDING_PROOFS.pop(binding_id, None)
        )
    if type(proof) is not _RetainedBindingProof:
        raise HongKongV1DueCycleError(_RETAINED_PROOF_INVALID)
    if type(binding) is not IssuedDueResultBinding:
        raise HongKongV1DueCycleError(_RETAINED_PROOF_INVALID)
    if (
        registration is None
        or binding_id is None
        or proof.binding_id != binding_id
        or proof.binding_id != id(binding)
        or registration[0]() is not binding
        or registration[1]() is not proof
    ):
        raise HongKongV1DueCycleError(_RETAINED_PROOF_INVALID)
    try:
        snapshot, _ = build_hk_v1_due_result_manifest(binding)
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(_RETAINED_PROOF_INVALID) from error
    if snapshot != registration[2]:
        raise HongKongV1DueCycleError(_RETAINED_PROOF_INVALID)
    registered = _register_validated_acquisition_due_result_binding(binding)
    if type(registered) is not IssuedDueResultBinding or registered is not binding:
        raise HongKongV1DueCycleError(_SOURCE_ADAPTER_INVALID)
    return registered


def _replay_terminal_artifact(  # noqa: C901
    vault: ImmutableVault,
    plan: HongKongV1DueCyclePlan,
    report_reference: DueTerminalReportReference,
) -> tuple[
    DueTerminalReportReference,
    bytes,
    bytes,
    IssuedDueResultBinding,
    HongKongV1DueTerminal,
]:
    """Rebuild one terminal through terminal -> attempt -> payload on retained bytes."""
    source_id = report_reference.source_id
    requirement = _requirement_for(plan, source_id)
    reference = report_reference.reference
    if (
        reference.vault != VaultName.PRIMARY.value
        or reference.logical_key
        != hk_v1_due_source_terminal_key(plan.instruction.cycle_id, source_id)
    ):
        raise HongKongV1DueCycleError(_TERMINAL_READBACK_INVALID)
    terminal_content = _read_due_reference(vault, reference, _TERMINAL_READBACK_INVALID)
    try:
        parsed_terminal = parse_hk_v1_due_terminal(terminal_content)
        terminal_bytes, _ = build_hk_v1_due_terminal(parsed_terminal)
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(_TERMINAL_READBACK_INVALID) from error
    if (
        terminal_bytes != terminal_content
        or parsed_terminal.requirement != requirement
        or parsed_terminal.cycle_id != plan.instruction.cycle_id
        or parsed_terminal.plan_fingerprint != plan.plan_fingerprint
        or parsed_terminal.matrix_fingerprint != plan.instruction.matrix_fingerprint
        or parsed_terminal.observation_cutoff != plan.instruction.observation_cutoff
        or parsed_terminal.attempt_manifest is None
    ):
        raise HongKongV1DueCycleError(_TERMINAL_READBACK_INVALID)
    attempt_reference = parsed_terminal.attempt_manifest
    if (
        attempt_reference.vault != VaultName.PRIMARY.value
        or attempt_reference.logical_key
        != hk_v1_due_source_result_manifest_key(plan.instruction.cycle_id, source_id)
    ):
        raise HongKongV1DueCycleError(_ATTEMPT_READBACK_INVALID)
    attempt_content = _read_due_reference(vault, attempt_reference, _ATTEMPT_READBACK_INVALID)
    try:
        attempt_document = parse_json_bytes(attempt_content, max_bytes=65_536)
        if not isinstance(attempt_document, dict):
            raise HongKongV1DueCycleError(_ATTEMPT_READBACK_INVALID)
        payload_reference = _due_reference_from_document(
            attempt_document.get("payload_reference"), _ATTEMPT_READBACK_INVALID
        )
        raw_evidence_reference = attempt_document.get("evidence_reference")
        evidence_reference = (
            None
            if raw_evidence_reference is None
            else _due_reference_from_document(raw_evidence_reference, _ATTEMPT_READBACK_INVALID)
        )
    except (TypeError, ValueError) as error:
        raise HongKongV1DueCycleError(_ATTEMPT_READBACK_INVALID) from error
    if (
        payload_reference.vault != VaultName.PRIMARY.value
        or payload_reference.logical_key
        != hk_v1_due_source_payload_key(plan.instruction.cycle_id, source_id)
        or payload_reference.fingerprint != parsed_terminal.result_fingerprint
    ):
        raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
    payload_content = _read_due_reference(vault, payload_reference, _PAYLOAD_READBACK_INVALID)
    if evidence_reference is None:
        if parsed_terminal.evidence_fingerprint is not None:
            raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
    else:
        if (
            evidence_reference.vault != VaultName.PRIMARY.value
            or evidence_reference.logical_key
            != _source_evidence_key(plan.instruction.cycle_id, source_id)
            or evidence_reference.fingerprint != parsed_terminal.evidence_fingerprint
        ):
            raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
        _read_due_reference(vault, evidence_reference, _PAYLOAD_READBACK_INVALID)
    facts = _DueSourceOutcomeFacts(
        parsed_terminal.outcome,
        parsed_terminal.change_status,
        parsed_terminal.failure_codes,
        parsed_terminal.expected_count,
        parsed_terminal.retained_count,
        parsed_terminal.not_published_count,
        parsed_terminal.gap_count,
        parsed_terminal.failed_count,
        parsed_terminal.evidence_kind,
    )
    binding = _binding_from_retained_authentic_payload(
        payload_content,
        plan,
        requirement,
        payload_reference,
        facts,
        evidence_reference,
    )
    binding = _binding_from_retained_attempt(attempt_content, binding)
    binding = _consume_retained_binding_proof(binding, _retained_binding_proof(binding))
    rebuilt_terminal = build_hk_v1_due_terminal_from_result_binding(binding, attempt_reference)
    rebuilt_terminal_bytes, _ = build_hk_v1_due_terminal(rebuilt_terminal)
    if rebuilt_terminal_bytes != terminal_content:
        raise HongKongV1DueCycleError(_TERMINAL_READBACK_INVALID)
    return report_reference, terminal_content, attempt_content, binding, rebuilt_terminal


class ScheduledFamilyChild(TypedDict):
    """One deterministic child identity and exact family instruction."""

    source_family: str
    cycle_id: str
    journal_ref: str
    instruction: dict[str, JsonValue]


class ScheduledFamilyResult(TypedDict):
    """Strict family manifest facts retained under the root due cycle."""

    source_family: str
    cycle_id: str
    journal_ref: str
    manifest_fingerprint: str
    journal_head_fingerprint: str
    result: str


class ScheduledFamilyRetentionInput(ScheduledFamilyResult):
    """A validated child summary plus canonical bytes crossing one local activity."""

    manifest_content: str


class _FamilyManifestCandidate(TypedDict):
    summary: ScheduledFamilyResult
    content: bytes


def _scheduled_family_cycle_id(
    instruction: HongKongV1DueCycleInstruction, source_family: str
) -> str:
    """Derive one stable journal-compatible identity from the complete root schedule."""
    slot_day = datetime.fromisoformat(instruction.scheduled_at).astimezone(_HONG_KONG)
    identity = {
        "root_instruction": _instruction_body(instruction),
        "source_family": source_family,
    }
    digest = sha256(canonicalize(checked_json_value(identity))).hexdigest()[:16]
    return f"cyc_{slot_day:%Y%m%d}_{digest}_{source_family.lower()}"


def scheduled_hk_v1_family_children(
    instruction: HongKongV1DueCycleInstruction,
) -> tuple[ScheduledFamilyChild, ScheduledFamilyChild]:
    """Return the only two family children permitted beneath one V1 due cycle."""
    cases_cycle_id = _scheduled_family_cycle_id(instruction, "CASES")
    legislation_cycle_id = _scheduled_family_cycle_id(instruction, "LEGISLATION")
    cases_mode = (
        "full_reconciliation"
        if instruction.cycle_kind is DueCycleKind.FULL_PERIODIC
        else "daily_current_law"
    )
    legislation_cutoff = datetime.fromisoformat(instruction.observation_cutoff).isoformat(
        timespec="seconds"
    )
    cases_cutoff = (
        datetime.fromisoformat(instruction.observation_cutoff)
        .astimezone(UTC)
        .strftime("%Y%m%dT%H%M%SZ")
    )
    cases_instruction: dict[str, JsonValue] = {
        "schema_id": "asklegal.cases-resumable-acquisition-instruction",
        "schema_version": "1.0.0",
        "source_family": "CASES",
        "cycle_id": cases_cycle_id,
        "work_graph_ref": (f"hk-v1-schedule/{cases_cycle_id}/{cases_mode}/cases/{cases_cutoff}"),
    }
    legislation_instruction: dict[str, JsonValue] = {
        "source_family": "LEGISLATION",
        "cycle_id": legislation_cycle_id,
        "observation_cutoff": legislation_cutoff,
        "budget": {
            "maximum_starts": 100,
            "maximum_retained_bytes": 100_000_000_000,
            "maximum_elapsed_seconds": 3_600,
            "maximum_redirects": 1_000,
        },
    }
    return (
        {
            "source_family": "CASES",
            "cycle_id": cases_cycle_id,
            "journal_ref": f"acquisition-journals/{cases_cycle_id}",
            "instruction": cases_instruction,
        },
        {
            "source_family": "LEGISLATION",
            "cycle_id": legislation_cycle_id,
            "journal_ref": f"acquisition-journals/{legislation_cycle_id}",
            "instruction": legislation_instruction,
        },
    )


def _scheduled_family_result(
    raw: object,
    child: ScheduledFamilyChild,
    instruction: HongKongV1DueCycleInstruction,
) -> ScheduledFamilyResult:
    """Rebuild one exact canonical child manifest before retaining any claim about it."""
    try:
        if type(raw) is not bytes or not raw:
            _due_fail(_ORCHESTRATOR_FAMILY_RESULT_INVALID)
        document = parse_json_bytes(raw, max_bytes=32_000_000)
        if child["source_family"] == "CASES":
            manifest = CasesAcquisitionManifest.from_json(document)
        elif child["source_family"] == "LEGISLATION":
            manifest = LegislationAcquisitionManifest.from_json(document)
        else:
            _due_fail(_ORCHESTRATOR_FAMILY_RESULT_INVALID)
        canonical = canonicalize(manifest.to_json())
        expected_cutoff = (
            instruction.observation_cutoff
            if child["source_family"] == "CASES"
            else child["instruction"]["observation_cutoff"]
        )
        if (
            canonical != raw
            or manifest.cycle_id != child["cycle_id"]
            or manifest.observation_cutoff != expected_cutoff
        ):
            _due_fail(_ORCHESTRATOR_FAMILY_RESULT_INVALID)
        return {
            "source_family": child["source_family"],
            "cycle_id": child["cycle_id"],
            "journal_ref": child["journal_ref"],
            "manifest_fingerprint": manifest.fingerprint,
            "journal_head_fingerprint": manifest.journal_head_fingerprint,
            "result": manifest.result.value,
        }
    except Exception as error:  # noqa: BLE001 - Durable child output is hostile input.
        _orchestrator_parse_fail(_ORCHESTRATOR_FAMILY_RESULT_INVALID, error)


def _family_evidence_key(cycle_id: str) -> str:
    return hk_v1_due_family_acquisition_key(cycle_id)


def _family_manifest_key(root_cycle_id: str, source_family: str) -> str:
    """Return the fixed Primary key for one canonical child manifest."""
    if source_family not in {"CASES", "LEGISLATION"}:
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    return (
        f"poc/report/hk-v1-due-cycle/{root_cycle_id}/family-manifests/{source_family.lower()}.json"
    )


_JOURNAL_SUCCESS = frozenset(
    {JournalTransition.CAPTURED_VERIFIED, JournalTransition.IMPORTED_CAPTURE_VERIFIED}
)
_JOURNAL_RETRYABLE = frozenset(
    {
        JournalTransition.DISCOVERED,
        JournalTransition.STARTED,
        JournalTransition.TRANSPORT_STARTED,
        JournalTransition.RETRYABLE_FAILURE,
        JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
    }
)


def _journal_role(source_family: str, source_role: str) -> str:
    return source_role.replace("_", "-") if source_family == "LEGISLATION" else source_role


def _verify_journal_object(
    vault: ImmutableVault,
    source_adapter: AuthenticDueSourceAdapter | None,
    object_ref: str,
    content_fingerprint: str,
    byte_length: int,
) -> None:
    """Re-prove one terminal object through Primary or the retained-import adapter."""
    try:
        reference = vault.resolve_current(object_ref)
        body = vault.read_exact(reference) if reference is not None else None
    except Exception:  # noqa: BLE001 - both evidence ports are hostile boundaries.
        body = None
    if (
        type(body) is bytes
        and len(body) == byte_length
        and f"sha256:{sha256(body).hexdigest()}" == content_fingerprint
    ):
        return
    verify = getattr(source_adapter, "verify_retained_object", None)
    try:
        verified = (
            verify(object_ref, content_fingerprint, byte_length) if callable(verify) else False
        )
    except Exception as error:  # noqa: BLE001 - retained evidence is an untrusted port.
        _due_fail_from(_FAMILY_EVIDENCE_INVALID, error)
    if verified is not True:
        _due_fail(_FAMILY_EVIDENCE_INVALID)


def _verify_family_journal(  # noqa: C901, PLR0912, PLR0915
    vault: ImmutableVault,
    acquisition_state_root: Path | None,
    source_adapter: AuthenticDueSourceAdapter | None,
    source_family: str,
    manifest: CasesAcquisitionManifest | LegislationAcquisitionManifest,
) -> None:
    """Replay the named child journal and bind its exact terminal objects to the manifest."""
    if manifest.result not in {AcquisitionCycleResult.COMPLETE, AcquisitionCycleResult.NO_CHANGE}:
        return
    if acquisition_state_root is None:
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    cycle_path = acquisition_state_root / "acquisition-journals" / manifest.cycle_id
    if cycle_path.is_symlink() or not cycle_path.is_dir():
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    try:
        with LocalAcquisitionJournal(acquisition_state_root, manifest.cycle_id) as journal:
            entries = journal.replay()
            checkpoint = journal.load_checkpoint()
    except Exception as error:  # noqa: BLE001 - local journal filesystem is hostile evidence.
        _due_fail_from(_FAMILY_EVIDENCE_INVALID, error)
    if (
        not entries
        or checkpoint.journal_head_fingerprint != manifest.journal_head_fingerprint
        or entries[-1].fingerprint != manifest.journal_head_fingerprint
    ):
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    latest = {entry.work_item.work_item_id: entry for entry in entries}
    terminal_entries = tuple(
        latest[item.work_item_id]
        for item in checkpoint.items
        if item.transition is not JournalTransition.ACCOUNTED_EXCLUDED
    )
    for disposition in manifest.source_dispositions:
        role_entries = tuple(
            entry
            for entry in terminal_entries
            if _journal_role(source_family, entry.work_item.source_role) == disposition.source_id
        )
        verified_count = sum(entry.transition in _JOURNAL_SUCCESS for entry in role_entries)
        retryable_count = sum(entry.transition in _JOURNAL_RETRYABLE for entry in role_entries)
        rejected_count = len(role_entries) - verified_count - retryable_count
        if (
            len(role_entries) != disposition.required_item_count
            or verified_count != disposition.verified_item_count
            or retryable_count != disposition.retryable_item_count
            or rejected_count != disposition.rejected_item_count
        ):
            _due_fail(_FAMILY_EVIDENCE_INVALID)
    expected_roles = {item.source_id for item in manifest.source_dispositions}
    journal_roles = {
        _journal_role(source_family, entry.work_item.source_role) for entry in terminal_entries
    }
    if manifest.source_dispositions and journal_roles != expected_roles:
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    possible_legislation_refs: set[str] = set()
    for entry in terminal_entries:
        if entry.transition not in _JOURNAL_SUCCESS:
            continue
        payload = entry.payload
        if (
            type(payload) is CapturedVerifiedPayload
            or type(payload) is ImportedCaptureVerifiedPayload
        ):
            verified_payload = payload
        else:
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        _verify_journal_object(
            vault,
            source_adapter,
            verified_payload.object_ref,
            verified_payload.content_fingerprint,
            verified_payload.body_length,
        )
        if type(manifest) is LegislationAcquisitionManifest:
            stable_key = entry.work_item.parent_id
            with suppress(TypeError, ValueError):
                possible_legislation_refs.add(
                    LegislationVerifiedItem.issue(
                        stable_key,
                        verified_payload.object_ref,
                        verified_payload.content_fingerprint,
                    ).reference
                )
    if type(manifest) is LegislationAcquisitionManifest:
        if not set(manifest.verified_item_refs).issubset(possible_legislation_refs):
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        return
    if type(manifest) is not CasesAcquisitionManifest:
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    cases_manifest = manifest
    for bundle_ref in cases_manifest.judgment_bundle_refs:
        try:
            reference = vault.resolve_current(bundle_ref)
            bundle = vault.read_exact(reference) if reference is not None else None
        except Exception as error:  # noqa: BLE001 - bundle read-back is an evidence boundary.
            _due_fail_from(_FAMILY_EVIDENCE_INVALID, error)
        if type(bundle) is not bytes or not bundle_ref.endswith(
            f"/{sha256(bundle).hexdigest()}.json"
        ):
            _due_fail(_FAMILY_EVIDENCE_INVALID)


def _due_reference_body(reference: DueImmutableReference) -> dict[str, JsonValue]:
    """Serialize only a reference rebuilt by this worker's strict boundary."""
    return {
        "vault": reference.vault,
        "logical_key": reference.logical_key,
        "version_id": reference.version_id,
        "fingerprint": reference.fingerprint,
        "byte_length": reference.byte_length,
    }


def _current_family_capture(  # noqa: C901, PLR0912, PLR0913, PLR0917
    vault: ImmutableVault,
    acquisition_state_root: Path | None,
    source_adapter: AuthenticDueSourceAdapter | None,
    instruction: HongKongV1DueCycleInstruction,
    plan: HongKongV1DueCyclePlan,
    source_id: str,
    family_reference: DueImmutableReference,
) -> AuthenticDueSourceCapture:
    """Derive one role terminal only from this cycle's retained family manifests."""
    if (
        family_reference.vault != VaultName.PRIMARY.value
        or family_reference.logical_key != _family_evidence_key(instruction.cycle_id)
    ):
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    content = _read_due_reference(vault, family_reference, _FAMILY_EVIDENCE_INVALID)
    try:
        document = parse_json_bytes(content, max_bytes=32_000_000)
    except (TypeError, ValueError) as error:
        _due_fail_from(_FAMILY_EVIDENCE_INVALID, error)
    if (
        type(document) is not dict
        or set(document)
        != {
            "schema_id",
            "schema_version",
            "root_instruction",
            "root_plan_fingerprint",
            "children",
        }
        or document["schema_id"] != _FAMILY_EVIDENCE_SCHEMA
        or document["schema_version"] != _FAMILY_EVIDENCE_VERSION
        or document["root_instruction"] != _instruction_body(instruction)
        or document["root_plan_fingerprint"] != plan.plan_fingerprint
        or canonicalize(checked_json_value(document)) != content
    ):
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    raw_children = document["children"]
    if type(raw_children) is not list or len(raw_children) != _FAMILY_COUNT:
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    expected_children = scheduled_hk_v1_family_children(instruction)
    matched_family: str | None = None
    matched_manifest: DueImmutableReference | None = None
    matched_summary: ScheduledFamilyResult | None = None
    matched_disposition: SourceRoleDisposition | None = None
    for raw_child, expected in zip(raw_children, expected_children, strict=True):
        if type(raw_child) is not dict or set(raw_child) != {
            "source_family",
            "cycle_id",
            "journal_ref",
            "manifest_fingerprint",
            "journal_head_fingerprint",
            "result",
            "manifest_reference",
        }:
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        manifest_reference = _due_reference_from_document(
            raw_child["manifest_reference"], _FAMILY_EVIDENCE_INVALID
        )
        if (
            manifest_reference.vault != VaultName.PRIMARY.value
            or manifest_reference.logical_key
            != _family_manifest_key(instruction.cycle_id, expected["source_family"])
        ):
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        manifest_content = _read_due_reference(vault, manifest_reference, _FAMILY_EVIDENCE_INVALID)
        summary = _scheduled_family_result(manifest_content, expected, instruction)
        supplied_summary: ScheduledFamilyResult = {
            "source_family": _orchestrator_exact_text(raw_child["source_family"]),
            "cycle_id": _orchestrator_exact_text(raw_child["cycle_id"]),
            "journal_ref": _orchestrator_exact_text(raw_child["journal_ref"]),
            "manifest_fingerprint": _orchestrator_exact_text(raw_child["manifest_fingerprint"]),
            "journal_head_fingerprint": _orchestrator_exact_text(
                raw_child["journal_head_fingerprint"]
            ),
            "result": _orchestrator_exact_text(raw_child["result"]),
        }
        if supplied_summary != summary:
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        family = summary["source_family"]
        if source_id in _CURRENT_FAMILY_SOURCE_IDS[family]:
            if matched_family is not None:
                _due_fail(_FAMILY_EVIDENCE_INVALID)
            matched_family = family
            matched_manifest = manifest_reference
            matched_summary = summary
            try:
                manifest_document = parse_json_bytes(manifest_content, max_bytes=32_000_000)
                manifest = (
                    CasesAcquisitionManifest.from_json(manifest_document)
                    if family == "CASES"
                    else LegislationAcquisitionManifest.from_json(manifest_document)
                )
            except (TypeError, ValueError) as error:
                _due_fail_from(_FAMILY_EVIDENCE_INVALID, error)
            _verify_family_journal(
                vault,
                acquisition_state_root,
                source_adapter,
                family,
                manifest,
            )
            matched_disposition = next(
                (item for item in manifest.source_dispositions if item.source_id == source_id),
                None,
            )
    if matched_family is None or matched_manifest is None or matched_summary is None:
        _due_fail(_SOURCE_ADAPTER_INVALID)
    family_result = matched_summary["result"]
    if (
        family_result in {"COMPLETE", "NO_CHANGE"}
        and matched_disposition is not None
        and matched_disposition.result
        in {AcquisitionCycleResult.COMPLETE, AcquisitionCycleResult.NO_CHANGE}
    ):
        change = (
            DueChangeStatus.NO_CHANGE
            if family_result == "NO_CHANGE"
            else (
                DueChangeStatus.BASELINE
                if plan.predecessor_fingerprint is None
                else DueChangeStatus.CHANGED
            )
        )
        evidence = canonicalize(
            checked_json_value(
                {
                    "schema_id": "asklegal.hk-v1.current-family-source-evidence",
                    "schema_version": "1.0.0",
                    "cycle_id": instruction.cycle_id,
                    "observation_cutoff": instruction.observation_cutoff,
                    "plan_fingerprint": plan.plan_fingerprint,
                    "source_id": source_id,
                    "source_family": matched_family,
                    "family_result": family_result,
                    "source_disposition": matched_disposition.to_json(),
                    "family_evidence_reference": _due_reference_body(family_reference),
                    "family_manifest_reference": _due_reference_body(matched_manifest),
                    "family_manifest_fingerprint": matched_summary["manifest_fingerprint"],
                    "journal_head_fingerprint": matched_summary["journal_head_fingerprint"],
                }
            )
        )
        return AuthenticDueSourceCapture(
            source_id,
            DueTerminalOutcome.COMPLETE,
            change,
            (),
            matched_disposition.required_item_count,
            matched_disposition.verified_item_count,
            0,
            0,
            0,
            evidence,
            "CURRENT_FAMILY_ROLE_PROOF",
        )
    if matched_disposition is None:
        return AuthenticDueSourceCapture(
            source_id,
            DueTerminalOutcome.INCOMPLETE_OBSERVATION,
            DueChangeStatus.NOT_PROVED,
            ("FAMILY_SOURCE_ROLE_EVIDENCE_MISSING",),
            0,
            0,
            0,
            0,
            0,
            None,
        )
    return AuthenticDueSourceCapture(
        source_id,
        DueTerminalOutcome.INCOMPLETE_OBSERVATION,
        DueChangeStatus.NOT_PROVED,
        (
            f"FAMILY_SOURCE_ROLE_{matched_disposition.result.value}"
            if family_result in {"COMPLETE", "NO_CHANGE"}
            else f"FAMILY_ACQUISITION_{family_result}",
        ),
        matched_disposition.required_item_count,
        matched_disposition.verified_item_count,
        matched_disposition.retryable_item_count + matched_disposition.rejected_item_count,
        0,
        0,
        None,
    )


def _family_manifest_candidate(
    raw_child: object,
    expected: ScheduledFamilyChild,
    instruction: HongKongV1DueCycleInstruction,
) -> _FamilyManifestCandidate:
    fields = {
        "source_family",
        "cycle_id",
        "journal_ref",
        "manifest_fingerprint",
        "journal_head_fingerprint",
        "result",
        "manifest_content",
    }
    try:
        child = checked_json_value(raw_child)
    except ValueError as error:
        _due_fail_from(_FAMILY_EVIDENCE_INVALID, error)
    if type(child) is not dict or set(child) != fields:
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    if any(type(item) is not str or not item for item in child.values()):
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    raw_content = child["manifest_content"]
    if type(raw_content) is not str:
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    try:
        manifest_content = raw_content.encode("utf-8")
    except UnicodeEncodeError as error:
        _due_fail_from(_FAMILY_EVIDENCE_INVALID, error)
    summary = _scheduled_family_result(manifest_content, expected, instruction)
    supplied_summary: ScheduledFamilyResult = {
        "source_family": _orchestrator_exact_text(child["source_family"]),
        "cycle_id": _orchestrator_exact_text(child["cycle_id"]),
        "journal_ref": _orchestrator_exact_text(child["journal_ref"]),
        "manifest_fingerprint": _orchestrator_exact_text(child["manifest_fingerprint"]),
        "journal_head_fingerprint": _orchestrator_exact_text(child["journal_head_fingerprint"]),
        "result": _orchestrator_exact_text(child["result"]),
    }
    if supplied_summary != summary:
        _due_fail(_FAMILY_EVIDENCE_INVALID)
    return {"summary": summary, "content": manifest_content}


def _family_evidence_document(
    value: object,
) -> tuple[HongKongV1DueCycleInstruction, str, tuple[_FamilyManifestCandidate, ...]]:
    """Validate and canonicalize the exact two-child retained-evidence request."""
    try:
        document = checked_json_value(value)
        if type(document) is not dict or set(document) != {
            "instruction",
            "expected_plan_fingerprint",
            "children",
        }:
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        instruction = HongKongV1DueCycleInstruction.from_json(document["instruction"])
        expected_plan_fingerprint = document["expected_plan_fingerprint"]
        if (
            type(expected_plan_fingerprint) is not str
            or not expected_plan_fingerprint.startswith("sha256:")
            or len(expected_plan_fingerprint) != _SHA256_FINGERPRINT_LENGTH
        ):
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        raw_children = document["children"]
        if type(raw_children) is not list or len(raw_children) != _FAMILY_COUNT:
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        candidates: list[_FamilyManifestCandidate] = []
        expected_children = scheduled_hk_v1_family_children(instruction)
        for raw_child, expected in zip(raw_children, expected_children, strict=True):
            candidates.append(_family_manifest_candidate(raw_child, expected, instruction))
        return instruction, expected_plan_fingerprint, tuple(candidates)
    except Exception as error:  # noqa: BLE001 - activity payload is an untrusted boundary.
        _orchestrator_parse_fail(_FAMILY_EVIDENCE_INVALID, error)


class HongKongV1DueCycleActivities:
    """Own fixed-resource planning and local immutable unadmitted terminals."""

    def __init__(
        self,
        vault: ImmutableVault,
        predecessor_store: object,
        *,
        source_adapter: AuthenticDueSourceAdapter | None = None,
    ) -> None:
        """Bind an explicit primary vault and mandatory retained-state authority."""
        if vault.vault_name is not VaultName.PRIMARY:
            code = "DUE_CYCLE_PRIMARY_VAULT_REQUIRED"
            raise ValueError(code)
        if predecessor_store is None:
            code = "DUE_CYCLE_PREDECESSOR_STORE_REQUIRED"
            raise ValueError(code)
        try:
            load: object = getattr(predecessor_store, "load")  # noqa: B009 - dynamic port check.
            compare_and_set: object = getattr(  # noqa: B009 - dynamic port check.
                predecessor_store, "compare_and_set"
            )
            usable_store = callable(load) and callable(compare_and_set)
        except Exception as error:
            code = "DUE_CYCLE_PREDECESSOR_STORE_REQUIRED"
            raise ValueError(code) from error
        if not usable_store:
            code = "DUE_CYCLE_PREDECESSOR_STORE_REQUIRED"
            raise ValueError(code)
        if source_adapter is not None:
            try:
                capture = source_adapter.capture
            except Exception as error:
                raise ValueError(_SOURCE_ADAPTER_REQUIRED) from error
            if not callable(capture):
                raise ValueError(_SOURCE_ADAPTER_REQUIRED)
        self._vault = vault
        self._predecessor_store = cast("DueCyclePredecessorStore", predecessor_store)
        self._source_adapter = source_adapter
        raw_state_root = getattr(predecessor_store, "acquisition_state_root", None)
        if isinstance(raw_state_root, Path) and type(raw_state_root) is type(Path()):
            if not raw_state_root.is_absolute():
                code = "DUE_CYCLE_PREDECESSOR_STORE_REQUIRED"
                raise ValueError(code)
            self._acquisition_state_root: Path | None = raw_state_root
        else:
            self._acquisition_state_root = None

    def plan_hk_v1_due_cycle(self, _context: ActivityContext, value: object) -> DuePlanOutput:
        """Dispatch the exact derived plan through Durable Task's activity boundary."""
        return self._plan_hk_v1_due_cycle(value)

    def _plan_hk_v1_due_cycle(self, value: object) -> DuePlanOutput:
        """Return the exact derived plan without accepting register injection."""
        return _plan_body(
            _resolve_predecessor_plan(
                self._predecessor_store, HongKongV1DueCycleInstruction.from_json(value)
            )
        )

    def capture_hk_v1_due_source(
        self, _context: ActivityContext, value: object
    ) -> dict[str, object]:
        """Dispatch one due source capture through Durable Task's activity boundary."""
        return self._capture_hk_v1_due_source(value)

    def _capture_hk_v1_due_source(  # noqa: C901, PLR0915
        self, value: object
    ) -> dict[str, object]:
        """Dispatch one exact adapter result, or preserve the fixed unadmitted fallback."""
        instruction, expected_plan_fingerprint, source_id, family_reference = _capture_input(value)
        plan = _resolve_predecessor_plan(self._predecessor_store, instruction)
        if expected_plan_fingerprint != plan.plan_fingerprint:
            raise HongKongV1DueCycleError(_PLAN_FINGERPRINT_MISMATCH)
        requirement = _requirement_for(plan, source_id)
        authentic: AuthenticDueSourceCapture | None = None
        if family_reference is not None:
            authentic = _current_family_capture(
                self._vault,
                self._acquisition_state_root,
                self._source_adapter,
                instruction,
                plan,
                source_id,
                family_reference,
            )
        elif self._source_adapter is not None:
            try:
                candidate = self._source_adapter.capture(
                    source_id=source_id,
                    observation_cutoff=instruction.observation_cutoff,
                )
            except Exception as error:
                raise HongKongV1DueCycleError(_SOURCE_ADAPTER_INVALID) from error
            if candidate is not None:
                if (
                    type(candidate) is not AuthenticDueSourceCapture
                    or candidate.source_id != source_id
                ):
                    raise HongKongV1DueCycleError(_SOURCE_ADAPTER_INVALID)
                authentic = candidate
        facts = None if authentic is None else _authentic_facts(authentic)
        # A read-back-verified authentic result is the cycle-local technical
        # proof.  Static Matrix/register limitations remain serialized on the
        # terminal, but do not erase work that this cycle demonstrably did.
        payload = (
            _unadmitted_payload(plan, requirement)
            if facts is None
            else _source_payload(plan, requirement, facts)
        )
        evidence_reference: DueImmutableReference | None = None
        evidence_created: bool | None = None
        if authentic is not None and authentic.evidence_bytes is not None:
            evidence_key = _source_evidence_key(instruction.cycle_id, source_id)
            evidence_receipt = _conditional_create(
                self._vault,
                evidence_key,
                authentic.evidence_bytes,
                _PAYLOAD_READBACK_INVALID,
            )
            evidence_snapshot = _receipt_snapshot(
                evidence_receipt,
                evidence_key,
                authentic.evidence_bytes,
                _PAYLOAD_READBACK_INVALID,
            )
            retained_evidence = _read_exact_snapshot(
                self._vault, evidence_snapshot, _PAYLOAD_READBACK_INVALID
            )
            if retained_evidence != authentic.evidence_bytes:
                raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
            evidence_reference = _reference(evidence_snapshot.reference)
            evidence_created = evidence_snapshot.created
        payload_key = hk_v1_due_source_payload_key(instruction.cycle_id, source_id)
        payload_receipt = _conditional_create(
            self._vault, payload_key, payload, _PAYLOAD_READBACK_INVALID
        )
        payload_receipt_snapshot = _receipt_snapshot(
            payload_receipt, payload_key, payload, _PAYLOAD_READBACK_INVALID
        )
        retained_payload = _read_exact_snapshot(
            self._vault, payload_receipt_snapshot, _PAYLOAD_READBACK_INVALID
        )
        if retained_payload != payload:
            raise HongKongV1DueCycleError(_PAYLOAD_READBACK_INVALID)
        payload_reference = _reference(payload_receipt_snapshot.reference)
        payload_binding = (
            _binding_from_retained_payload(retained_payload, plan, requirement, payload_reference)
            if facts is None
            else _binding_from_retained_authentic_payload(
                retained_payload,
                plan,
                requirement,
                payload_reference,
                facts,
                evidence_reference,
            )
        )
        attempt, _attempt_fingerprint = build_hk_v1_due_result_manifest(payload_binding)
        attempt_key = hk_v1_due_source_result_manifest_key(instruction.cycle_id, source_id)
        attempt_receipt = _conditional_create(
            self._vault, attempt_key, attempt, _ATTEMPT_READBACK_INVALID
        )
        attempt_receipt_snapshot = _receipt_snapshot(
            attempt_receipt, attempt_key, attempt, _ATTEMPT_READBACK_INVALID
        )
        retained_attempt = _read_exact_snapshot(
            self._vault, attempt_receipt_snapshot, _ATTEMPT_READBACK_INVALID
        )
        binding = _binding_from_retained_attempt(retained_attempt, payload_binding)
        binding = _consume_retained_binding_proof(binding, _retained_binding_proof(binding))
        terminal = build_hk_v1_due_terminal_from_result_binding(
            binding, _reference(attempt_receipt_snapshot.reference)
        )
        terminal_bytes, terminal_fingerprint = build_hk_v1_due_terminal(terminal)
        terminal_key = hk_v1_due_source_terminal_key(instruction.cycle_id, source_id)
        terminal_receipt = _conditional_create(
            self._vault, terminal_key, terminal_bytes, _TERMINAL_READBACK_INVALID
        )
        terminal_receipt_snapshot = _receipt_snapshot(
            terminal_receipt, terminal_key, terminal_bytes, _TERMINAL_READBACK_INVALID
        )
        read_back = _read_exact_snapshot(
            self._vault, terminal_receipt_snapshot, _TERMINAL_READBACK_INVALID
        )
        try:
            parsed = parse_hk_v1_due_terminal(read_back)
            parsed_bytes, parsed_fingerprint = build_hk_v1_due_terminal(parsed)
        except (TypeError, ValueError) as error:
            raise HongKongV1DueCycleError(_TERMINAL_READBACK_INVALID) from error
        if (
            read_back != terminal_bytes
            or parsed_bytes != terminal_bytes
            or parsed_fingerprint != terminal_fingerprint
            or parsed.result_fingerprint != payload_reference.fingerprint
            or parsed.attempt_manifest != _reference(attempt_receipt_snapshot.reference)
        ):
            raise HongKongV1DueCycleError(_TERMINAL_READBACK_INVALID)
        result: dict[str, object] = {
            "source_id": source_id,
            "plan_fingerprint": plan.plan_fingerprint,
            "terminal_reference": {
                "vault": terminal_receipt_snapshot.reference.vault.value,
                "logical_key": terminal_receipt_snapshot.reference.logical_key,
                "version_id": terminal_receipt_snapshot.reference.version_id,
                "fingerprint": terminal_receipt_snapshot.reference.fingerprint,
                "byte_length": terminal_receipt_snapshot.reference.byte_length,
            },
            "payload_created": payload_receipt_snapshot.created,
            "attempt_created": attempt_receipt_snapshot.created,
            "terminal_created": terminal_receipt_snapshot.created,
        }
        if evidence_created is not None:
            result["evidence_created"] = evidence_created
        return result

    def record_hk_v1_due_source_failure(
        self, _context: ActivityContext, value: object
    ) -> dict[str, object]:
        """Dispatch one due capture failure through Durable Task's activity boundary."""
        return self._record_hk_v1_due_source_failure(value)

    def _record_hk_v1_due_source_failure(self, value: object) -> dict[str, object]:
        """Durably account for one failed source activity without retaining diagnostics."""
        instruction, expected_plan_fingerprint, source_id = _failure_input(value)
        plan = _resolve_predecessor_plan(self._predecessor_store, instruction)
        if expected_plan_fingerprint != plan.plan_fingerprint:
            raise HongKongV1DueCycleError(_PLAN_FINGERPRINT_MISMATCH)
        requirement = _requirement_for(plan, source_id)
        payload_key = hk_v1_due_source_payload_key(instruction.cycle_id, source_id)
        normal_payload = _unadmitted_payload(plan, requirement)
        payload = _failed_payload(plan, requirement)
        resolved = _resolved_due_payload_snapshot(self._vault, payload_key, normal_payload, payload)
        if resolved is not None and resolved[0]:
            return self._capture_hk_v1_due_source(
                _capture_request_body(instruction, expected_plan_fingerprint, source_id)
            )
        payload_receipt_snapshot = None if resolved is None else resolved[1]
        if payload_receipt_snapshot is None:
            try:
                payload_receipt = _conditional_create(
                    self._vault, payload_key, payload, _PAYLOAD_READBACK_INVALID
                )
            except VaultCollision:
                concurrent = _resolved_due_payload_snapshot(
                    self._vault, payload_key, normal_payload, payload
                )
                if concurrent is None:
                    raise
                if concurrent[0]:
                    return self._capture_hk_v1_due_source(
                        _capture_request_body(instruction, expected_plan_fingerprint, source_id)
                    )
                payload_receipt_snapshot = concurrent[1]
            else:
                payload_receipt_snapshot = _receipt_snapshot(
                    payload_receipt, payload_key, payload, _PAYLOAD_READBACK_INVALID
                )
        return _persist_due_failure_chain(
            self._vault,
            plan,
            requirement,
            payload,
            payload_receipt_snapshot,
        )

    def record_hk_v1_family_acquisitions(
        self, _context: ActivityContext, value: object
    ) -> dict[str, object]:
        """Retain and read back both exact child-manifest identities under the root cycle."""
        instruction, expected_plan_fingerprint, candidates = _family_evidence_document(value)
        plan = _resolve_predecessor_plan(self._predecessor_store, instruction)
        if plan.plan_fingerprint != expected_plan_fingerprint:
            _due_fail(_PLAN_FINGERPRINT_MISMATCH)
        children: list[dict[str, JsonValue]] = []
        for candidate in candidates:
            summary = candidate["summary"]
            manifest_content = candidate["content"]
            manifest_document = parse_json_bytes(manifest_content, max_bytes=32_000_000)
            manifest = (
                CasesAcquisitionManifest.from_json(manifest_document)
                if summary["source_family"] == "CASES"
                else LegislationAcquisitionManifest.from_json(manifest_document)
            )
            _verify_family_journal(
                self._vault,
                self._acquisition_state_root,
                self._source_adapter,
                summary["source_family"],
                manifest,
            )
            manifest_key = _family_manifest_key(instruction.cycle_id, summary["source_family"])
            manifest_receipt = _conditional_create(
                self._vault,
                manifest_key,
                manifest_content,
                _FAMILY_EVIDENCE_INVALID,
            )
            manifest_snapshot = _receipt_snapshot(
                manifest_receipt,
                manifest_key,
                manifest_content,
                _FAMILY_EVIDENCE_INVALID,
            )
            if (
                _read_exact_snapshot(self._vault, manifest_snapshot, _FAMILY_EVIDENCE_INVALID)
                != manifest_content
            ):
                _due_fail(_FAMILY_EVIDENCE_INVALID)
            retained_child: dict[str, JsonValue] = {
                "source_family": summary["source_family"],
                "cycle_id": summary["cycle_id"],
                "journal_ref": summary["journal_ref"],
                "manifest_fingerprint": summary["manifest_fingerprint"],
                "journal_head_fingerprint": summary["journal_head_fingerprint"],
                "result": summary["result"],
                "manifest_reference": _reference_body(manifest_snapshot.reference),
            }
            children.append(retained_child)
        content = canonicalize(
            checked_json_value(
                {
                    "schema_id": _FAMILY_EVIDENCE_SCHEMA,
                    "schema_version": _FAMILY_EVIDENCE_VERSION,
                    "root_instruction": _instruction_body(instruction),
                    "root_plan_fingerprint": expected_plan_fingerprint,
                    "children": children,
                }
            )
        )
        key = _family_evidence_key(instruction.cycle_id)
        receipt = _conditional_create(self._vault, key, content, _FAMILY_EVIDENCE_INVALID)
        snapshot = _receipt_snapshot(receipt, key, content, _FAMILY_EVIDENCE_INVALID)
        if _read_exact_snapshot(self._vault, snapshot, _FAMILY_EVIDENCE_INVALID) != content:
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        return {
            "cycle_id": instruction.cycle_id,
            "evidence_reference": _reference_body(snapshot.reference),
            "evidence_created": snapshot.created,
        }

    def assemble_hk_v1_due_cycle(
        self, _context: ActivityContext, value: object
    ) -> dict[str, object]:
        """Dispatch the final due cycle assembly through Durable Task's activity boundary."""
        return self._assemble_hk_v1_due_cycle(value)

    def _assemble_hk_v1_due_cycle(self, value: object) -> dict[str, object]:
        """Rebuild source terminals, then persist the final immutable cycle manifest last."""
        instruction, expected_plan_fingerprint, references = _assembly_input(value)
        plan = _resolve_predecessor_plan(self._predecessor_store, instruction)
        if expected_plan_fingerprint != plan.plan_fingerprint:
            raise HongKongV1DueCycleError(_PLAN_FINGERPRINT_MISMATCH)
        replayed = tuple(
            _replay_terminal_artifact(self._vault, plan, reference) for reference in references
        )
        artifacts = tuple(
            (reference, terminal, attempt, binding)
            for reference, terminal, attempt, binding, _issued_terminal in replayed
        )
        terminal_pairs = tuple(
            (reference, issued_terminal)
            for reference, _terminal, _attempt, _binding, issued_terminal in replayed
        )
        try:
            report = build_hk_v1_due_cycle_report(plan, terminal_pairs)
        except (TypeError, ValueError) as error:
            raise HongKongV1DueCycleError(_ASSEMBLY_INPUT_INVALID) from error
        manifest_key = hk_v1_due_cycle_manifest_key(instruction.cycle_id)
        receipt = _conditional_create(
            self._vault, manifest_key, report.canonical_bytes, _MANIFEST_READBACK_INVALID
        )
        snapshot = _receipt_snapshot(
            receipt,
            manifest_key,
            report.canonical_bytes,
            _MANIFEST_READBACK_INVALID,
        )
        retained = _read_exact_snapshot(self._vault, snapshot, _MANIFEST_READBACK_INVALID)
        if retained != report.canonical_bytes:
            raise HongKongV1DueCycleError(_MANIFEST_READBACK_INVALID)
        try:
            parsed = parse_hk_v1_due_cycle_report(retained, plan, artifacts)
        except (TypeError, ValueError) as error:
            raise HongKongV1DueCycleError(_MANIFEST_READBACK_INVALID) from error
        if (
            parsed.canonical_bytes != report.canonical_bytes
            or parsed.fingerprint != report.fingerprint
            or parsed != report
        ):
            raise HongKongV1DueCycleError(_MANIFEST_READBACK_INVALID)
        state = DueCyclePredecessorState(
            instruction,
            plan.plan_fingerprint,
            plan.predecessor_fingerprint,
            _reference(snapshot.reference),
            parsed.fingerprint,
        )
        try:
            raw_predecessor_receipt = self._predecessor_store.compare_and_set(
                plan.predecessor_fingerprint, state
            )
        except DueCyclePredecessorConflict as error:
            _due_fail_from(_PREDECESSOR_STATE_CONFLICT, error)
        except Exception as error:  # noqa: BLE001 - store implementations are an untrusted port.
            _due_fail_from(_PREDECESSOR_STATE_INVALID, error)
        predecessor_receipt = _rebuild_predecessor_receipt(raw_predecessor_receipt)
        if predecessor_receipt.state.state_fingerprint != state.state_fingerprint:
            _due_fail(_PREDECESSOR_STATE_INVALID)
        return {
            "cycle_id": instruction.cycle_id,
            "plan_fingerprint": plan.plan_fingerprint,
            "manifest_reference": _reference_body(snapshot.reference),
            "manifest_created": snapshot.created,
            "predecessor_state_fingerprint": predecessor_receipt.state.state_fingerprint,
            "predecessor_state_created": predecessor_receipt.created,
            "complete_source_ids": list(parsed.complete_source_ids),
            "missing_source_ids": list(parsed.missing_source_ids),
            "duplicate_source_ids": list(parsed.duplicate_source_ids),
            "gap_source_ids": list(parsed.gap_source_ids),
            "failed_source_ids": list(parsed.failed_source_ids),
            "accounting_complete": parsed.accounting_complete,
            "release_blocking": parsed.release_blocking,
            "disposition": parsed.disposition,
        }


class _DueCycleWorker(Protocol):
    """The only scheduler registration surface owned by this due-cycle module."""

    def add_activity(self, fn: Callable[..., object]) -> str:
        """Register one acquisition-owned activity."""
        ...

    def add_orchestrator(self, fn: Callable[..., object]) -> str:
        """Register one acquisition-owned orchestrator."""
        ...


def register_hk_v1_due_cycle_handlers(
    worker: _DueCycleWorker,
    activities: HongKongV1DueCycleActivities,
) -> None:
    """Register the one canonical due-cycle protocol without legacy aliases."""
    if type(activities) is not HongKongV1DueCycleActivities:
        code = "DUE_CYCLE_ACTIVITIES_REQUIRED"
        raise ValueError(code)
    worker.add_activity(activities.plan_hk_v1_due_cycle)
    worker.add_activity(activities.capture_hk_v1_due_source)
    worker.add_activity(activities.record_hk_v1_due_source_failure)
    worker.add_activity(activities.record_hk_v1_family_acquisitions)
    worker.add_activity(activities.assemble_hk_v1_due_cycle)
    worker.add_orchestrator(acquire_hk_v1_due_cycle)


def _instruction_body(instruction: HongKongV1DueCycleInstruction) -> dict[str, str]:
    """Rebuild the six control-owned instruction leaves for one Durable input."""
    return {
        "cycle_id": instruction.cycle_id,
        "cycle_kind": instruction.cycle_kind.value,
        "scheduled_at": instruction.scheduled_at,
        "observation_cutoff": instruction.observation_cutoff,
        "matrix_revision": instruction.matrix_revision,
        "matrix_fingerprint": instruction.matrix_fingerprint,
    }


def _orchestrator_instruction(payload: object) -> HongKongV1DueCycleInstruction:
    """Parse the outer Durable payload without leaking ordinary hostile-container errors."""
    try:
        return HongKongV1DueCycleInstruction.from_json(payload)
    except Exception as error:  # noqa: BLE001 - hostile Durable instruction parser boundary.
        _orchestrator_parse_fail("CYCLE_INSTRUCTION_INVALID", error)


def _orchestrator_family_evidence_result(
    value: object, instruction: HongKongV1DueCycleInstruction
) -> dict[str, object]:
    """Accept only the exact retained two-family evidence receipt for this root cycle."""
    try:
        document = checked_json_value(value)
        if type(document) is not dict or set(document) != {
            "cycle_id",
            "evidence_reference",
            "evidence_created",
        }:
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        reference = _due_reference_from_document(
            document["evidence_reference"], _FAMILY_EVIDENCE_INVALID
        )
        if (
            document["cycle_id"] != instruction.cycle_id
            or type(document["evidence_created"]) is not bool
            or reference.vault != VaultName.PRIMARY.value
            or reference.logical_key != _family_evidence_key(instruction.cycle_id)
        ):
            _due_fail(_FAMILY_EVIDENCE_INVALID)
        return {
            "cycle_id": instruction.cycle_id,
            "evidence_reference": {
                "vault": reference.vault,
                "logical_key": reference.logical_key,
                "version_id": reference.version_id,
                "fingerprint": reference.fingerprint,
                "byte_length": reference.byte_length,
            },
            "evidence_created": document["evidence_created"],
        }
    except Exception as error:  # noqa: BLE001 - Durable activity result is hostile input.
        _orchestrator_parse_fail(_FAMILY_EVIDENCE_INVALID, error)


def _orchestrator_exact_text(value: object) -> str:
    """Accept a JSON text leaf only after excluding comparison-overriding subclasses."""
    if type(value) is not str:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    return value


def _orchestrator_exact_object(value: object, fields: frozenset[str]) -> dict[str, JsonValue]:
    """Copy a projection object only after its keys have exact built-in text identities."""
    if type(value) is not dict:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    document = cast("dict[str, JsonValue]", value)
    if any(type(key) is not str for key in document):
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    if frozenset(document) != fields:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    return document


def _orchestrator_exact_text_list(value: object) -> tuple[str, ...]:
    """Copy an exact JSON text list before a reporting contract can inspect it."""
    if type(value) is not list:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    values = cast("list[object]", value)
    return tuple(_orchestrator_exact_text(item) for item in values)


def _orchestrator_register_source(value: object) -> DueSourceRegister:
    """Rebuild one exact register source without resource or policy lookup."""
    document = _orchestrator_exact_object(
        value,
        frozenset(
            {
                "source_id",
                "source_version",
                "endpoint_ids",
                "operational_state",
                "blockers",
            }
        ),
    )
    return DueSourceRegister(
        _orchestrator_exact_text(document["source_id"]),
        _orchestrator_exact_text(document["source_version"]),
        _orchestrator_exact_text_list(document["endpoint_ids"]),
        _orchestrator_exact_text(document["operational_state"]),
        _orchestrator_exact_text_list(document["blockers"]),
    )


def _orchestrator_register(value: object) -> DueRegisterBundle:
    """Rebuild one activity-derived register projection without resolving a resource."""
    document = _orchestrator_exact_object(
        value,
        frozenset({"register_id", "register_version", "register_fingerprint", "sources"}),
    )
    raw_sources = document["sources"]
    if type(raw_sources) is not list:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    sources = tuple(_orchestrator_register_source(raw_source) for raw_source in raw_sources)
    return DueRegisterBundle(
        _orchestrator_exact_text(document["register_id"]),
        _orchestrator_exact_text(document["register_version"]),
        _orchestrator_exact_text(document["register_fingerprint"]),
        sources,
    )


def _orchestrator_requirement(value: object) -> HongKongV1DueRequirement:
    """Rebuild one exact Matrix-derived requirement from scheduler history."""
    document = _orchestrator_exact_object(
        value,
        frozenset(
            {
                "material_family",
                "source_id",
                "source_version",
                "cadence",
                "outage_impact",
                "register_id",
                "register_version",
                "register_fingerprint",
                "matrix_policy_fingerprint",
                "policy_conflict",
                "result_schema",
                "technical_state",
                "rights_state",
            }
        ),
    )
    policy_conflict = document["policy_conflict"]
    if policy_conflict is not None and type(policy_conflict) is not str:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    return HongKongV1DueRequirement(
        _orchestrator_exact_text(document["material_family"]),
        _orchestrator_exact_text(document["source_id"]),
        _orchestrator_exact_text(document["source_version"]),
        _orchestrator_exact_text(document["cadence"]),
        _orchestrator_exact_text(document["outage_impact"]),
        _orchestrator_exact_text(document["register_id"]),
        _orchestrator_exact_text(document["register_version"]),
        _orchestrator_exact_text(document["register_fingerprint"]),
        _orchestrator_exact_text(document["matrix_policy_fingerprint"]),
        policy_conflict,
        _orchestrator_exact_text(document["result_schema"]),
        _orchestrator_exact_text(document["technical_state"]),
        _orchestrator_exact_text(document["rights_state"]),
    )


def _orchestrator_plan_projection(
    value: object,
    instruction: HongKongV1DueCycleInstruction,
) -> HongKongV1DueCyclePlan:
    """Rebuild a self-validating plan only from deterministic Durable history facts."""
    document = _orchestrator_exact_object(
        checked_json_value(value),
        frozenset(
            {
                "schema_id",
                "schema_version",
                "cycle_id",
                "cycle_kind",
                "instruction",
                "plan_fingerprint",
                "requirements_fingerprint",
                "registers",
                "predecessor_fingerprint",
                "requirements",
                "source_ids",
            }
        ),
    )
    raw_instruction = _orchestrator_exact_object(
        document["instruction"],
        frozenset(
            {
                "cycle_id",
                "cycle_kind",
                "scheduled_at",
                "observation_cutoff",
                "matrix_revision",
                "matrix_fingerprint",
            }
        ),
    )
    instruction_body = {
        key: _orchestrator_exact_text(raw_instruction[key])
        for key in (
            "cycle_id",
            "cycle_kind",
            "scheduled_at",
            "observation_cutoff",
            "matrix_revision",
            "matrix_fingerprint",
        )
    }
    raw_registers = document["registers"]
    if type(raw_registers) is not list:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    registers = tuple(_orchestrator_register(raw_register) for raw_register in raw_registers)
    raw_requirements = document["requirements"]
    if type(raw_requirements) is not list:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    requirements = tuple(
        _orchestrator_requirement(raw_requirement) for raw_requirement in raw_requirements
    )
    raw_source_ids = document["source_ids"]
    if type(raw_source_ids) is not list:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    predecessor = document["predecessor_fingerprint"]
    if predecessor is not None and type(predecessor) is not str:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    projected_instruction = HongKongV1DueCycleInstruction.from_json(instruction_body)
    if projected_instruction != instruction:
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    if (
        _orchestrator_exact_text(document["schema_id"]) != "asklegal.hk-v1-due-cycle-plan"
        or _orchestrator_exact_text(document["schema_version"]) != "1.0.0"
        or _orchestrator_exact_text(document["cycle_id"]) != instruction.cycle_id
        or _orchestrator_exact_text(document["cycle_kind"]) != instruction.cycle_kind.value
    ):
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    plan = HongKongV1DueCyclePlan(
        projected_instruction,
        registers,
        predecessor,
        requirements,
        _orchestrator_exact_text(document["requirements_fingerprint"]),
        _orchestrator_exact_text(document["plan_fingerprint"]),
    )
    source_ids = _orchestrator_exact_text_list(raw_source_ids)
    if source_ids != tuple(requirement.source_id for requirement in plan.requirements):
        _due_fail(_ORCHESTRATOR_PLAN_INVALID)
    return plan


def _orchestrator_plan(
    value: object, instruction: HongKongV1DueCycleInstruction
) -> HongKongV1DueCyclePlan:
    """Accept only a self-validating, activity-derived replay projection."""
    try:
        plan = _orchestrator_plan_projection(value, instruction)
    except Exception as error:  # noqa: BLE001 - hostile Durable result parser boundary.
        _orchestrator_parse_fail(_ORCHESTRATOR_PLAN_INVALID, error)
    return plan


def _orchestrator_reference(
    value: object,
    *,
    expected_key: str,
    code: str,
) -> dict[str, object]:
    """Rebuild one exact primary-vault reference before passing it to another task."""
    reference = _due_reference_from_document(value, code)
    if reference.vault != VaultName.PRIMARY.value or reference.logical_key != expected_key:
        _due_fail(code)
    if reference.version_id.startswith("v") and reference.version_id != (
        "v" + reference.fingerprint.removeprefix("sha256:")
    ):
        _due_fail(code)
    return {
        "vault": reference.vault,
        "logical_key": reference.logical_key,
        "version_id": reference.version_id,
        "fingerprint": reference.fingerprint,
        "byte_length": reference.byte_length,
    }


def _orchestrator_capture_result(
    value: object,
    instruction: HongKongV1DueCycleInstruction,
    plan_fingerprint: str,
    source_id: str,
) -> dict[str, object]:
    """Parse a terminal acknowledgement without accepting adapter diagnostics."""
    try:
        document = checked_json_value(value)
        if not isinstance(document, dict) or frozenset(document) != frozenset(
            {
                "source_id",
                "plan_fingerprint",
                "terminal_reference",
                "payload_created",
                "attempt_created",
                "terminal_created",
            }
        ):
            _due_fail(_ORCHESTRATOR_CAPTURE_INVALID)
        result_source_id = document["source_id"]
        result_fingerprint = document["plan_fingerprint"]
        created_fields = (
            document["payload_created"],
            document["attempt_created"],
            document["terminal_created"],
        )
        if (
            type(result_source_id) is not str
            or type(result_fingerprint) is not str
            or result_source_id != source_id
            or result_fingerprint != plan_fingerprint
            or any(type(created) is not bool for created in created_fields)
        ):
            _due_fail(_ORCHESTRATOR_CAPTURE_INVALID)
        reference = _orchestrator_reference(
            document["terminal_reference"],
            expected_key=hk_v1_due_source_terminal_key(instruction.cycle_id, source_id),
            code=_ORCHESTRATOR_CAPTURE_INVALID,
        )
    except Exception as error:  # noqa: BLE001 - hostile Durable result parser boundary.
        _orchestrator_parse_fail(_ORCHESTRATOR_CAPTURE_INVALID, error)
    return {"source_id": source_id, "reference": reference}


def _orchestrator_source_ids(value: object, source_ids: tuple[str, ...], code: str) -> list[str]:
    """Copy one report category only when it is a sorted subset of the due plan."""
    if not isinstance(value, list):
        _due_fail(code)
    raw_values = cast("list[object]", value)
    parsed: list[str] = []
    for item in raw_values:
        if type(item) is not str:
            _due_fail(code)
        parsed.append(item)
    if (
        parsed != sorted(parsed)
        or len(set(parsed)) != len(parsed)
        or not set(parsed) <= set(source_ids)
    ):
        _due_fail(code)
    return parsed


def _orchestrator_predecessor_fingerprint(
    plan: HongKongV1DueCyclePlan,
    manifest_reference: dict[str, object],
) -> str:
    """Derive the one state identity bound to this trusted plan and manifest receipt."""
    reference = _due_reference_from_document(manifest_reference, _ORCHESTRATOR_ASSEMBLY_INVALID)
    state = DueCyclePredecessorState(
        plan.instruction,
        plan.plan_fingerprint,
        plan.predecessor_fingerprint,
        reference,
        reference.fingerprint,
    )
    return state.state_fingerprint


def _orchestrator_assembly_result(
    value: object,
    plan: HongKongV1DueCyclePlan,
    terminal_source_ids: tuple[str, ...],
) -> dict[str, object]:
    """Expose only a fully reconstructed scheduler-safe manifest result."""
    expected_fields = frozenset(
        {
            "cycle_id",
            "plan_fingerprint",
            "manifest_reference",
            "manifest_created",
            "predecessor_state_fingerprint",
            "predecessor_state_created",
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
    instruction = plan.instruction
    plan_fingerprint = plan.plan_fingerprint
    source_ids = tuple(requirement.source_id for requirement in plan.requirements)
    try:
        document = checked_json_value(value)
        if not isinstance(document, dict) or frozenset(document) != expected_fields:
            _due_fail(_ORCHESTRATOR_ASSEMBLY_INVALID)
        cycle_id = document["cycle_id"]
        result_fingerprint = document["plan_fingerprint"]
        predecessor_fingerprint = document["predecessor_state_fingerprint"]
        manifest_created = document["manifest_created"]
        predecessor_created = document["predecessor_state_created"]
        accounting_complete = document["accounting_complete"]
        release_blocking = document["release_blocking"]
        disposition = document["disposition"]
        if (
            type(cycle_id) is not str
            or type(result_fingerprint) is not str
            or type(predecessor_fingerprint) is not str
            or cycle_id != instruction.cycle_id
            or result_fingerprint != plan_fingerprint
            or type(manifest_created) is not bool
            or type(predecessor_created) is not bool
            or type(accounting_complete) is not bool
            or type(release_blocking) is not bool
            or type(disposition) is not str
            or disposition not in {"COMPLETE", "ACCOUNTED_WITH_GAPS", "INCOMPLETE_ACCOUNTING"}
        ):
            _due_fail(_ORCHESTRATOR_ASSEMBLY_INVALID)
        if not (
            predecessor_fingerprint.startswith("sha256:")
            and len(predecessor_fingerprint) == _SHA256_FINGERPRINT_LENGTH
            and all(character in "0123456789abcdef" for character in predecessor_fingerprint[7:])
        ):
            _due_fail(_ORCHESTRATOR_ASSEMBLY_INVALID)
        references = _orchestrator_reference(
            document["manifest_reference"],
            expected_key=hk_v1_due_cycle_manifest_key(instruction.cycle_id),
            code=_ORCHESTRATOR_ASSEMBLY_INVALID,
        )
        if predecessor_fingerprint != _orchestrator_predecessor_fingerprint(plan, references):
            _due_fail(_ORCHESTRATOR_ASSEMBLY_INVALID)
        categories: dict[str, list[str]] = {
            key: _orchestrator_source_ids(document[key], source_ids, _ORCHESTRATOR_ASSEMBLY_INVALID)
            for key in (
                "complete_source_ids",
                "missing_source_ids",
                "duplicate_source_ids",
                "gap_source_ids",
                "failed_source_ids",
            )
        }
        accepted_sources = set[str](terminal_source_ids)
        if (
            len(accepted_sources) != len(terminal_source_ids)
            or any(source_id not in source_ids for source_id in terminal_source_ids)
            or terminal_source_ids
            != tuple(source_id for source_id in source_ids if source_id in accepted_sources)
        ):
            _due_fail(_ORCHESTRATOR_ASSEMBLY_INVALID)
        expected_missing = sorted(set(source_ids).difference(accepted_sources))
        terminal_categories = (
            set(categories["complete_source_ids"]),
            set(categories["gap_source_ids"]),
            set(categories["failed_source_ids"]),
        )
        if (
            categories["missing_source_ids"] != expected_missing
            or categories["duplicate_source_ids"]
            or any(
                not set(categories[key]) <= accepted_sources
                for key in ("complete_source_ids", "gap_source_ids", "failed_source_ids")
            )
            or terminal_categories[0] & terminal_categories[1]
            or terminal_categories[0] & terminal_categories[2]
            or terminal_categories[1] & terminal_categories[2]
            or set().union(*terminal_categories) != accepted_sources
            or accounting_complete is not (not expected_missing)
        ):
            _due_fail(_ORCHESTRATOR_ASSEMBLY_INVALID)
        expected_disposition = (
            "INCOMPLETE_ACCOUNTING"
            if not accounting_complete
            else "ACCOUNTED_WITH_GAPS"
            if categories["gap_source_ids"] or categories["failed_source_ids"]
            else "COMPLETE"
        )
        if disposition != expected_disposition:
            _due_fail(_ORCHESTRATOR_ASSEMBLY_INVALID)
        requirements = {requirement.source_id: requirement for requirement in plan.requirements}
        problem_source_ids = set[str]().union(
            categories["missing_source_ids"],
            categories["duplicate_source_ids"],
            categories["gap_source_ids"],
            categories["failed_source_ids"],
        )
        expected_release_blocking = any(
            requirements[source_id].outage_impact != "NONBLOCKING"
            for source_id in problem_source_ids
        )
        if release_blocking is not expected_release_blocking:
            _due_fail(_ORCHESTRATOR_ASSEMBLY_INVALID)
    except Exception as error:  # noqa: BLE001 - hostile Durable result parser boundary.
        _orchestrator_parse_fail(_ORCHESTRATOR_ASSEMBLY_INVALID, error)
    return {
        "cycle_id": instruction.cycle_id,
        "plan_fingerprint": plan_fingerprint,
        "manifest_reference": references,
        "manifest_created": manifest_created,
        "predecessor_state_fingerprint": predecessor_fingerprint,
        "predecessor_state_created": predecessor_created,
        **categories,
        "accounting_complete": accounting_complete,
        "release_blocking": release_blocking,
        "disposition": disposition,
    }


def acquire_hk_v1_due_cycle(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, dict[str, object]]:
    """Checkpoint one closed due plan, its terminal chain, and its final manifest."""
    instruction = _orchestrator_instruction(payload)
    instruction_body = _instruction_body(instruction)
    planned = yield context.call_activity("plan_hk_v1_due_cycle", input=instruction_body)
    plan = _orchestrator_plan(planned, instruction)
    plan_fingerprint = plan.plan_fingerprint
    family_results: list[ScheduledFamilyRetentionInput] = []
    for child in scheduled_hk_v1_family_children(instruction):
        raw_family_result = yield context.call_sub_orchestrator(
            _FAMILY_ORCHESTRATOR,
            input=child["instruction"],
            instance_id=child["cycle_id"],
            version=_FAMILY_ORCHESTRATOR_VERSION,
        )
        summary = _scheduled_family_result(raw_family_result, child, instruction)
        if type(raw_family_result) is not bytes:
            _due_fail(_ORCHESTRATOR_FAMILY_RESULT_INVALID)
        family_results.append(
            {
                **summary,
                "manifest_content": raw_family_result.decode("utf-8"),
            }
        )
    raw_family_evidence = yield context.call_activity(
        "record_hk_v1_family_acquisitions",
        input={
            "instruction": instruction_body,
            "expected_plan_fingerprint": plan_fingerprint,
            "children": family_results,
        },
    )
    family_evidence = _orchestrator_family_evidence_result(raw_family_evidence, instruction)
    family_evidence_reference = family_evidence["evidence_reference"]
    source_ids = tuple(requirement.source_id for requirement in plan.requirements)
    terminal_references: list[dict[str, object]] = []
    terminal_source_ids: list[str] = []
    for source_id in source_ids:
        capture_payload = {
            "instruction": instruction_body,
            "expected_plan_fingerprint": plan_fingerprint,
            "source_id": source_id,
            "family_evidence_reference": family_evidence_reference,
        }
        try:
            capture_result = yield context.call_activity(
                "capture_hk_v1_due_source", input=capture_payload
            )
            reference = _orchestrator_capture_result(
                capture_result, instruction, plan_fingerprint, source_id
            )
        except TaskFailedError, HongKongV1DueCycleError:
            failure_payload = {
                "instruction": instruction_body,
                "expected_plan_fingerprint": plan_fingerprint,
                "source_id": source_id,
                "failure_code": _SOURCE_ACTIVITY_FAILED,
            }
            try:
                failure_result = yield context.call_activity(
                    "record_hk_v1_due_source_failure", input=failure_payload
                )
                reference = _orchestrator_capture_result(
                    failure_result, instruction, plan_fingerprint, source_id
                )
            except TaskFailedError, HongKongV1DueCycleError:
                continue
        terminal_references.append(reference)
        terminal_source_ids.append(source_id)
    assembly_payload = {
        "instruction": instruction_body,
        "expected_plan_fingerprint": plan_fingerprint,
        "terminal_references": terminal_references,
    }
    assembled = yield context.call_activity("assemble_hk_v1_due_cycle", input=assembly_payload)
    result = _orchestrator_assembly_result(
        assembled,
        plan,
        tuple(terminal_source_ids),
    )
    result["family_acquisition_evidence"] = family_evidence
    return result
