"""Effect-safe source observation orchestration for the V1 CONTROL_PLANE.

The control plane sequences acquisition and legal processing on the shared general
scheduler destination. It deliberately has no route to the promotion hub and no
activity that can turn an analysis decision into a serving record. Promotion begins
only from a separately frozen proposal and exact human Approval; that command-bound
path is not yet installed in the real V1 service, so production effects remain
closed.

Each stage is an activity, because scheduling another orchestration and waiting on
it is an effect. The orchestrator holds no client and no clock.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Never, Protocol, TypeGuard, cast

from asklegal_contracts import ContractViolation, parse_json_bytes
from asklegal_durable_task import OrchestrationStatus, V1SchedulerSettings
from asklegal_reporting import (
    DueImmutableReference,
    HongKongV1CoverageMatrix,
    HongKongV1DueCycleError,
    HongKongV1DueCycleInstruction,
    hk_v1_due_cycle_manifest_key,
    hk_v1_due_family_acquisition_key,
    is_hk_v1_coverage_matrix_policy_approved,
)

from asklegal_control_plane.proposal import (
    CurrentAcquisitionJournalHeadReader,
    HongKongV1TwoFamilyProposalManifest,
    ProposalEvidenceReader,
    TwoFamilyProposalRequest,
    freeze_hk_v1_two_family_proposal,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from asklegal_contracts.json_types import JsonValue
    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

    from asklegal_control_plane.v1_infrastructure import V1ControlInfrastructure

_LOGGER = logging.getLogger("asklegal_control_plane.v1_pipeline")
_VERSION = "1.0.0"
_STAGE_TIMEOUT_SECONDS = 900
_MAX_DUE_RESULT_BYTES = 64 * 1024
SOURCE_OBSERVATION_ACTIVITIES = ("start_acquisition", "start_analysis")
HK_V1_DUE_ACTIVITY = "start_hk_v1_due_cycle"
HK_V1_DUE_ACCEPTANCE_ACTIVITY = "continue_hk_v1_due_acceptance"
_DUE_ORCHESTRATION = "acquire_hk_v1_due_cycle"
_DUE_RESULT_FIELDS = frozenset(
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
        "family_acquisition_evidence",
    }
)
_DUE_INSTRUCTION_FIELDS = frozenset(
    {
        "cycle_id",
        "cycle_kind",
        "scheduled_at",
        "observation_cutoff",
        "matrix_revision",
        "matrix_fingerprint",
    }
)
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_V1_INCLUDED_MATERIAL_FAMILIES = frozenset({"LEGISLATION", "CASES"})
_ACCEPTANCE_RESULT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "kind",
        "operation_id",
        "command_fingerprint",
        "observation_cutoff",
        "families",
        "scope_ids",
        "result",
        "blocker_codes",
        "proposal_reference",
    }
)
_ACCEPTANCE_FAMILIES = ("CASES", "LEGISLATION")
_ACCEPTANCE_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)


class ControlPipelineError(RuntimeError):
    """One exact control-plane orchestration failure, safe to log."""


class DisabledProposalSemanticEffect(Protocol):
    """A deliberately dormant model or embedding boundary for Task 7 proof."""

    def invoke(self, payload: bytes) -> bytes:
        """Remain unused until later capability admission explicitly enables it."""
        ...


class TwoFamilyProposalReadinessService:
    """Freeze complete proposal inputs while keeping semantic providers untouched."""

    def __init__(
        self,
        matrix: HongKongV1CoverageMatrix,
        current_heads: CurrentAcquisitionJournalHeadReader,
        evidence_reader: ProposalEvidenceReader,
        model_effect: DisabledProposalSemanticEffect,
        embedding_effect: DisabledProposalSemanticEffect,
    ) -> None:
        """Bind the exact Matrix and prove both future effect ports are callable."""
        if (
            not callable(getattr(current_heads, "read_current", None))
            or not callable(getattr(evidence_reader, "read_exact", None))
            or not callable(getattr(model_effect, "invoke", None))
            or not callable(getattr(embedding_effect, "invoke", None))
        ):
            _control_fail("HK_V1_TWO_FAMILY_SEMANTIC_BOUNDARY_INVALID")
        self._matrix = matrix
        self._current_heads = current_heads
        self._evidence_reader = evidence_reader
        self._model_effect = model_effect
        self._embedding_effect = embedding_effect

    def prepare(self, request: TwoFamilyProposalRequest) -> HongKongV1TwoFamilyProposalManifest:
        """Validate and freeze without invoking either provider-facing effect port."""
        # Keeping these bound and deliberately unused makes effect denial observable
        # without granting this proposal-readiness slice provider authority.
        if not callable(self._model_effect.invoke) or not callable(self._embedding_effect.invoke):
            _control_fail("HK_V1_TWO_FAMILY_SEMANTIC_BOUNDARY_INVALID")
        return freeze_hk_v1_two_family_proposal(
            request, self._matrix, self._current_heads, self._evidence_reader
        )


@dataclass(frozen=True, slots=True)
class _DueMatrixRow:
    material_family: str
    source_id: str
    cadence: str
    technical_state: str
    rights_state: str
    outage_consequence: str


@dataclass(frozen=True, slots=True)
class _DueMatrixSnapshot:
    revision: str
    fingerprint: str
    included_material_families: tuple[str, ...]
    rows: tuple[_DueMatrixRow, ...]


@dataclass(frozen=True, slots=True)
class _DueSchedulerRoute:
    """A detached exact scheduler destination validated before client creation."""

    scheduler_service: str
    task_hub: str
    version: str


@dataclass(frozen=True, slots=True)
class _DueResultProjection:
    """One rebuilt acquisition acknowledgement before Matrix-derived reconciliation."""

    cycle_id: str
    plan_fingerprint: str
    reference: DueImmutableReference
    manifest_created: bool
    predecessor_fingerprint: str
    predecessor_state_created: bool
    family_reference: DueImmutableReference
    family_evidence_created: bool
    categories: dict[str, set[str]]
    accounting_complete: bool
    release_blocking: bool
    disposition: str


def _run_stage(application: str, orchestration: str, payload: object) -> JsonValue:
    """Schedule one orchestration on another application's hub and await it."""
    settings = V1SchedulerSettings.for_application(application)
    client = settings.create_client(default_version=_VERSION)
    instance = client.schedule_new_orchestration(orchestration, input=payload)
    state = client.wait_for_orchestration_completion(instance, timeout=_STAGE_TIMEOUT_SECONDS)
    if state is None or state.runtime_status is not OrchestrationStatus.COMPLETED:
        detail = "no terminal state"
        if state is not None and state.failure_details is not None:
            detail = state.failure_details.message[:300]
        message = f"{application}/{orchestration} did not complete: {detail}"
        raise ControlPipelineError(message)
    if type(state.serialized_output) is not str or not state.serialized_output:
        message = f"{application}/{orchestration} returned no output"
        raise ControlPipelineError(message)
    return _parse_scheduler_result(state.serialized_output)


class ControlActivities:
    """The control plane's two observation effects, bound to one infrastructure."""

    def __init__(
        self, infrastructure: V1ControlInfrastructure, due_matrix: HongKongV1CoverageMatrix
    ) -> None:
        """Hold the infrastructure this application is allowed to act through."""
        _assert_due_matrix(due_matrix)
        self._infrastructure = infrastructure
        self._due_matrix = due_matrix

    def start_acquisition(self, _context: ActivityContext, payload: object) -> object:
        """Run one capture on the acquisition hub and return its evidence reference."""
        result = _run_stage("ACQUISITION_WORKER", "acquire_endpoint", payload)
        if isinstance(result, dict):
            _LOGGER.info(
                "CONTROL_PLANE acquired %s bytes from %s",
                result.get("byte_length"),
                result.get("source_id"),
            )
        return result

    def start_analysis(self, _context: ActivityContext, payload: object) -> object:
        """Run one analysis on the legal-processing hub and return its decision."""
        result = _run_stage("LEGAL_PROCESSING_WORKER", "analyse_stored_evidence", payload)
        if isinstance(result, dict):
            _LOGGER.info("CONTROL_PLANE analysed to %s", result.get("decision_code"))
        return result

    def start_hk_v1_due_cycle(
        self, _context: ActivityContext, payload: object
    ) -> dict[str, object]:
        """Use the reversible local exception to schedule one exact acquisition due cycle."""
        try:
            matrix = _due_matrix_snapshot(self._due_matrix)
            instruction = _due_instruction(payload, matrix)
            instruction_body = _due_instruction_body(instruction)
            matrix = _due_matrix_snapshot(self._due_matrix)
            if instruction.matrix_fingerprint != matrix.fingerprint:
                _control_fail("HK_V1_DUE_MATRIX_INVALID")
            settings, route = _due_scheduler_route()
            client = settings.create_client(default_version=route.version)
            instance_id = client.schedule_new_orchestration(
                _DUE_ORCHESTRATION,
                input=instruction_body,
                instance_id=instruction.cycle_id,
                version=route.version,
            )
            if type(instance_id) is not str or instance_id != instruction.cycle_id:
                _control_fail("HK_V1_DUE_INSTANCE_INVALID")
            state = client.wait_for_orchestration_completion(
                instruction.cycle_id, timeout=_STAGE_TIMEOUT_SECONDS
            )
            if (
                state is None
                or state.runtime_status is not OrchestrationStatus.COMPLETED
                or type(state.serialized_output) is not str
                or not state.serialized_output
            ):
                _due_result_invalid()
            result = _parse_scheduler_result(state.serialized_output)
            matrix = _due_matrix_snapshot(self._due_matrix)
            return _due_result(result, instruction, matrix)
        except ControlPipelineError:
            raise
        except Exception as error:  # noqa: BLE001 - scheduler is an untrusted effect boundary.
            _control_fail_from("HK_V1_DUE_DISPATCH_INVALID", error)


def _due_instruction(payload: object, matrix: _DueMatrixSnapshot) -> HongKongV1DueCycleInstruction:
    """Rebuild the detached six-field Control payload against the issued Matrix."""
    instruction = _rebuild_due_instruction(payload)
    if (
        instruction.matrix_revision != matrix.revision
        or instruction.matrix_fingerprint != matrix.fingerprint
    ):
        _control_fail("HK_V1_DUE_MATRIX_INVALID")
    return instruction


def _rebuild_due_instruction(payload: object) -> HongKongV1DueCycleInstruction:
    """Detach exact six-field primitives before the shared due-contract parser may inspect them."""
    document = _due_instruction_object(payload)
    try:
        parsed = HongKongV1DueCycleInstruction.from_json(document)
        return HongKongV1DueCycleInstruction(
            parsed.cycle_id,
            parsed.cycle_kind,
            parsed.scheduled_at,
            parsed.observation_cutoff,
            parsed.matrix_revision,
            parsed.matrix_fingerprint,
        )
    except Exception as error:  # noqa: BLE001 - the contract parser is a closed hostile boundary.
        _control_fail_from("HK_V1_DUE_INSTRUCTION_INVALID", error)


def _due_instruction_object(value: object) -> dict[str, str]:
    """Copy one exact instruction object before membership, equality, or parser traversal."""
    if type(value) is not dict:
        _control_fail("HK_V1_DUE_INSTRUCTION_INVALID")
    try:
        raw_document = cast("dict[object, object]", value)
        document: dict[str, str] = {}
        for key, item in raw_document.items():
            if type(key) is not str or type(item) is not str:
                _control_fail("HK_V1_DUE_INSTRUCTION_INVALID")
            document[key] = item
        if frozenset(document) != _DUE_INSTRUCTION_FIELDS:
            _control_fail("HK_V1_DUE_INSTRUCTION_INVALID")
    except ControlPipelineError:
        raise
    except Exception as error:  # noqa: BLE001 - only exact builtin values may reach the parser.
        _control_fail_from("HK_V1_DUE_INSTRUCTION_INVALID", error)
    else:
        return document


def _due_instruction_body(instruction: HongKongV1DueCycleInstruction) -> dict[str, str]:
    """Return only a new exact six-field scheduler payload."""
    return {
        "cycle_id": instruction.cycle_id,
        "cycle_kind": instruction.cycle_kind.value,
        "scheduled_at": instruction.scheduled_at,
        "observation_cutoff": instruction.observation_cutoff,
        "matrix_revision": instruction.matrix_revision,
        "matrix_fingerprint": instruction.matrix_fingerprint,
    }


def _due_scheduler_route() -> tuple[V1SchedulerSettings, _DueSchedulerRoute]:
    """Validate and detach the one admitted acquisition destination before creating a client."""
    try:
        settings = V1SchedulerSettings.for_application("ACQUISITION_WORKER")
        scheduler_service = settings.scheduler_service
        task_hub = settings.task_hub
    except Exception as error:  # noqa: BLE001 - scheduler configuration is an adapter boundary.
        _control_fail_from("HK_V1_DUE_ROUTING_INVALID", error)
    if (
        type(scheduler_service) is not str
        or type(task_hub) is not str
        or type(_VERSION) is not str
        or _VERSION != "1.0.0"
    ):
        _control_fail("HK_V1_DUE_ROUTING_INVALID")
    route = _DueSchedulerRoute(scheduler_service, task_hub, _VERSION)
    if route.scheduler_service != "dts-general" or route.task_hub != "acquisition":
        _control_fail("HK_V1_DUE_ROUTING_INVALID")
    return settings, route


def _due_result(
    value: object,
    instruction: HongKongV1DueCycleInstruction,
    matrix: _DueMatrixSnapshot,
) -> dict[str, object]:
    """Rebuild the exact fourteen-field acquisition acknowledgement before Control returns it."""
    try:
        document = _due_object(value)
        if frozenset(document) != _DUE_RESULT_FIELDS:
            _due_result_invalid()
        cycle_id = _due_text(document["cycle_id"])
        plan_fingerprint = _due_fingerprint(document["plan_fingerprint"])
        predecessor_fingerprint = _due_fingerprint(document["predecessor_state_fingerprint"])
        manifest_created = _due_bool(document["manifest_created"])
        predecessor_state_created = _due_bool(document["predecessor_state_created"])
        accounting_complete = _due_bool(document["accounting_complete"])
        release_blocking = _due_bool(document["release_blocking"])
        disposition = _due_text(document["disposition"])
        if cycle_id != instruction.cycle_id:
            _due_result_invalid()
        raw_reference = _due_object(document["manifest_reference"])
        if frozenset(raw_reference) != frozenset(
            {
                "vault",
                "logical_key",
                "version_id",
                "fingerprint",
                "byte_length",
            }
        ):
            _due_result_invalid()
        reference = DueImmutableReference(
            _due_text(raw_reference["vault"]),
            _due_text(raw_reference["logical_key"]),
            _due_text(raw_reference["version_id"]),
            _due_fingerprint(raw_reference["fingerprint"]),
            _due_nonnegative_int(raw_reference["byte_length"]),
        )
        if reference.vault != "PRIMARY" or reference.logical_key != hk_v1_due_cycle_manifest_key(
            cycle_id
        ):
            _due_result_invalid()
        family_reference, family_evidence_created = _due_family_evidence(
            document["family_acquisition_evidence"], cycle_id
        )
        categories: dict[str, set[str]] = {}
        for field in _DUE_SOURCE_ID_FIELDS:
            categories[field] = _due_source_ids(document[field])
    except ControlPipelineError:
        raise
    except Exception as error:  # noqa: BLE001 - the acquisition result is an untrusted boundary.
        _control_fail_from("HK_V1_DUE_RESULT_INVALID", error)
    return _reconcile_due_result(
        instruction,
        matrix,
        _DueResultProjection(
            cycle_id,
            plan_fingerprint,
            reference,
            manifest_created,
            predecessor_fingerprint,
            predecessor_state_created,
            family_reference,
            family_evidence_created,
            categories,
            accounting_complete,
            release_blocking,
            disposition,
        ),
    )


def _reconcile_due_result(
    instruction: HongKongV1DueCycleInstruction,
    matrix: _DueMatrixSnapshot,
    result: _DueResultProjection,
) -> dict[str, object]:
    """Verify the Matrix-derived accounting consequences after exact primitive reconstruction."""
    try:
        universe, impacts, unadmitted = _due_universe(instruction, matrix)
        accepted_ids: set[str] = set(result.categories["complete_source_ids"])
        accepted_ids.update(result.categories["gap_source_ids"])
        accepted_ids.update(result.categories["failed_source_ids"])
        missing_ids = result.categories["missing_source_ids"]
        all_categories = tuple(result.categories.values())
        if (
            any(
                all_categories[left].intersection(all_categories[right])
                for left in range(len(all_categories))
                for right in range(left + 1, len(all_categories))
            )
            or result.categories["duplicate_source_ids"]
            or missing_ids != universe.difference(accepted_ids)
            or accepted_ids.union(missing_ids) != universe
            or not accepted_ids.intersection(unadmitted) <= result.categories["failed_source_ids"]
        ):
            _due_result_invalid()
        problem_ids: set[str] = set(result.categories["missing_source_ids"])
        problem_ids.update(result.categories["duplicate_source_ids"])
        problem_ids.update(result.categories["gap_source_ids"])
        problem_ids.update(result.categories["failed_source_ids"])
        if result.accounting_complete is not (
            not result.categories["missing_source_ids"]
            and not result.categories["duplicate_source_ids"]
        ) or result.disposition != (
            "INCOMPLETE_ACCOUNTING"
            if not result.accounting_complete
            else "ACCOUNTED_WITH_GAPS"
            if result.categories["gap_source_ids"] or result.categories["failed_source_ids"]
            else "COMPLETE"
        ):
            _due_result_invalid()
        if result.release_blocking is not any(
            impacts[source_id] != "NONBLOCKING" for source_id in problem_ids
        ):
            _due_result_invalid()
        return {
            "cycle_id": result.cycle_id,
            "plan_fingerprint": result.plan_fingerprint,
            "manifest_reference": {
                "vault": result.reference.vault,
                "logical_key": result.reference.logical_key,
                "version_id": result.reference.version_id,
                "fingerprint": result.reference.fingerprint,
                "byte_length": result.reference.byte_length,
            },
            "manifest_created": result.manifest_created,
            "predecessor_state_fingerprint": result.predecessor_fingerprint,
            "predecessor_state_created": result.predecessor_state_created,
            "family_acquisition_evidence": {
                "cycle_id": result.cycle_id,
                "evidence_reference": {
                    "vault": result.family_reference.vault,
                    "logical_key": result.family_reference.logical_key,
                    "version_id": result.family_reference.version_id,
                    "fingerprint": result.family_reference.fingerprint,
                    "byte_length": result.family_reference.byte_length,
                },
                "evidence_created": result.family_evidence_created,
            },
            **{field: sorted(values) for field, values in result.categories.items()},
            "accounting_complete": result.accounting_complete,
            "release_blocking": result.release_blocking,
            "disposition": result.disposition,
        }
    except ControlPipelineError:
        raise
    except Exception as error:  # noqa: BLE001 - Matrix reconciliation is a trust boundary.
        _control_fail_from("HK_V1_DUE_RESULT_INVALID", error)


def _due_source_ids(value: object) -> set[str]:
    """Rebuild one sorted unique source-ID category without equality-liar values."""
    if not _is_exact_list(value):
        _category_invalid()
    copied = _copy_due_json(value)
    if not _is_exact_list(copied):
        _category_invalid()
    source_ids: list[str] = []
    for item in copied:
        if type(item) is not str:
            _category_invalid()
        source_ids.append(item)
    if source_ids != sorted(source_ids) or len(source_ids) != len(set(source_ids)):
        _category_invalid()
    return set(source_ids)


def _due_family_evidence(value: object, cycle_id: str) -> tuple[DueImmutableReference, bool]:
    document = _due_object(value)
    if (
        frozenset(document) != frozenset({"cycle_id", "evidence_reference", "evidence_created"})
        or document["cycle_id"] != cycle_id
    ):
        _due_result_invalid()
    raw_reference = _due_object(document["evidence_reference"])
    if frozenset(raw_reference) != frozenset(
        {"vault", "logical_key", "version_id", "fingerprint", "byte_length"}
    ):
        _due_result_invalid()
    reference = DueImmutableReference(
        _due_text(raw_reference["vault"]),
        _due_text(raw_reference["logical_key"]),
        _due_text(raw_reference["version_id"]),
        _due_fingerprint(raw_reference["fingerprint"]),
        _due_nonnegative_int(raw_reference["byte_length"]),
    )
    created = _due_bool(document["evidence_created"])
    if reference.vault != "PRIMARY" or reference.logical_key != hk_v1_due_family_acquisition_key(
        cycle_id
    ):
        _due_result_invalid()
    return reference, created


_DUE_SOURCE_ID_FIELDS = (
    "complete_source_ids",
    "missing_source_ids",
    "duplicate_source_ids",
    "gap_source_ids",
    "failed_source_ids",
)


def _due_object(value: object) -> dict[str, object]:
    """Copy one exact built-in object, excluding custom mapping/equality behaviour."""
    if not _is_exact_dict(value):
        _due_result_invalid()
    copied = _copy_due_json(value)
    if not _is_exact_dict(copied):
        _due_result_invalid()
    document: dict[str, object] = {}
    for key, item in copied.items():
        if type(key) is not str:
            _due_result_invalid()
        document[key] = item
    return document


def _copy_due_json(value: object) -> object:
    """Recursively detach only exact builtin JSON shapes before any untrusted operation."""
    if type(value) is dict:
        raw_document = cast("dict[object, object]", value)
        copied: dict[str, object] = {}
        for key, item in raw_document.items():
            if type(key) is not str:
                _due_result_invalid()
            copied[key] = _copy_due_json(item)
        return copied
    if type(value) is list:
        raw_items = cast("list[object]", value)
        return [_copy_due_json(item) for item in raw_items]
    if value is None or type(value) in (bool, int, float, str):
        return value
    _due_result_invalid()
    raise AssertionError


def _is_exact_dict(value: object) -> TypeGuard[dict[object, object]]:
    """Recognize only the builtin mapping before traversal."""
    return type(value) is dict


def _is_exact_list(value: object) -> TypeGuard[list[object]]:
    """Recognize only the builtin list before traversal."""
    return type(value) is list


def _due_text(value: object) -> str:
    """Return an exact built-in text value."""
    if type(value) is not str:
        _due_result_invalid()
    return value


def _due_fingerprint(value: object) -> str:
    """Return a closed fingerprint value."""
    text = _due_text(value)
    if _FINGERPRINT.fullmatch(text) is None:
        _due_result_invalid()
    return text


def _due_bool(value: object) -> bool:
    """Return an exact built-in boolean, never an integer alias."""
    if type(value) is not bool:
        _due_result_invalid()
    return value


def _due_nonnegative_int(value: object) -> int:
    """Return an exact non-negative built-in integer."""
    if type(value) is not int or value < 0:
        _due_result_invalid()
    return value


def _due_result_invalid() -> Never:
    """Raise the one safe outcome for an untrusted acquisition acknowledgement."""
    _control_fail("HK_V1_DUE_RESULT_INVALID")


def _category_invalid() -> Never:
    """Raise an internal category failure that is normalized at the result boundary."""
    code = "category"
    raise ValueError(code)


def _control_fail(code: str) -> Never:
    """Raise one safe control error without embedding a literal at the call site."""
    raise ControlPipelineError(code)


def _control_fail_from(code: str, error: Exception) -> Never:
    """Normalize a hostile boundary error without exposing its detail."""
    raise ControlPipelineError(code) from error


def _assert_due_matrix(matrix: HongKongV1CoverageMatrix) -> None:
    """Recheck exact repository-approved Matrix policy at each trust boundary."""
    if not is_hk_v1_coverage_matrix_policy_approved(matrix):
        _control_fail("HK_V1_DUE_MATRIX_INVALID")


def _due_matrix_snapshot(matrix: HongKongV1CoverageMatrix) -> _DueMatrixSnapshot:
    """Revalidate and reconstruct the injected issued Matrix without new file authority."""
    _assert_due_matrix(matrix)
    if (
        type(matrix.included_material_families) is not tuple
        or frozenset(matrix.included_material_families) != _V1_INCLUDED_MATERIAL_FAMILIES
    ):
        _control_fail("HK_V1_DUE_MATRIX_INVALID")
    rows: list[_DueMatrixRow] = []
    for row in matrix.rows:
        if any(
            type(value) is not str
            for value in (
                row.material_family,
                row.source_id,
                row.cadence,
                row.technical_state,
                row.rights_state,
                row.outage_consequence,
            )
        ):
            _control_fail("HK_V1_DUE_MATRIX_INVALID")
        rows.append(
            _DueMatrixRow(
                row.material_family,
                row.source_id,
                row.cadence,
                row.technical_state,
                row.rights_state,
                row.outage_consequence,
            )
        )
    return _DueMatrixSnapshot(
        matrix.revision,
        matrix.fingerprint,
        matrix.included_material_families,
        tuple(rows),
    )


def _due_universe(
    instruction: HongKongV1DueCycleInstruction,
    matrix: _DueMatrixSnapshot,
) -> tuple[set[str], dict[str, str], set[str]]:
    """Derive the exact cycle source universe and its closed Matrix consequences."""
    source_rows: dict[str, list[_DueMatrixRow]] = {}
    included_material_families = frozenset(matrix.included_material_families)
    for row in matrix.rows:
        if row.material_family in included_material_families and _is_due_cadence(
            row.cadence, instruction.cycle_kind.value
        ):
            source_rows.setdefault(row.source_id, []).append(row)
    universe = set(source_rows)
    impacts: dict[str, str] = {}
    unadmitted: set[str] = set()
    for source_id, rows in source_rows.items():
        consequences = {row.outage_consequence for row in rows}
        if len(consequences) != 1:
            _due_result_invalid()
        impacts[source_id] = next(iter(consequences))
        if any(row.technical_state != "ADMITTED" or row.rights_state != "ADMITTED" for row in rows):
            unadmitted.add(source_id)
    return universe, impacts, unadmitted


def _is_due_cadence(cadence: str, cycle_kind: str) -> bool:
    """Mirror the issued due-plan cadence projection without importing acquisition code."""
    daily = cadence in {
        "DAILY_AND_COMPLETE_AT_CYCLE_CUTOFF",
        "DAILY_AND_COMPLETE_WITHIN_24_HOURS_OF_CUTOFF",
        "DAILY_DISCOVERY",
        "DAILY_INVENTORY_AND_ON_CHANGE_ACQUISITION",
        "DAILY_SIGNAL_AND_ON_CHANGE_ACQUISITION",
    }
    weekly = cadence in {"WEEKLY", "WEEKLY_AND_EVENT_TRIGGERED"}
    monthly = cadence in {"MONTHLY_AND_EVENT_TRIGGERED", "MONTHLY_EVENT_TRIGGERED_AND_ON_DEMAND"}
    if cycle_kind == "DAILY_CURRENT_LAW":
        return daily
    if cycle_kind == "WEEKLY_RELEASE":
        return daily or weekly
    if cycle_kind == "MONTHLY_CROSS_CHECK":
        return monthly
    return daily or weekly or monthly


def _parse_scheduler_result(serialized: str) -> JsonValue:
    """Parse a bounded scheduler JSON result with duplicate-key rejection."""
    try:
        return parse_json_bytes(serialized.encode("utf-8"), max_bytes=_MAX_DUE_RESULT_BYTES)
    except (ContractViolation, UnicodeEncodeError) as error:
        _control_fail_from("HK_V1_DUE_RESULT_INVALID", error)


def observe_source_endpoint(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Acquire and analyse one endpoint without requesting a serving effect."""
    evidence = yield context.call_activity(SOURCE_OBSERVATION_ACTIVITIES[0], input=payload)
    decision = yield context.call_activity(SOURCE_OBSERVATION_ACTIVITIES[1], input=evidence)
    return observation_result(evidence, decision)


def run_hk_v1_due_cycle(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, dict[str, object]]:
    """Deterministically request one local-only due-cycle scheduling activity."""
    instruction = _detached_due_instruction(payload)
    value = yield context.call_activity(
        HK_V1_DUE_ACTIVITY, input=_due_instruction_body(instruction)
    )
    result = _due_orchestrator_result(value, instruction)
    if (
        result["accounting_complete"] is not True
        or result["release_blocking"] is not False
        or result["disposition"] != "COMPLETE"
    ):
        return result
    acceptance_value = yield context.call_activity(
        HK_V1_DUE_ACCEPTANCE_ACTIVITY,
        input={"instruction": _due_instruction_body(instruction), "due_result": result},
    )
    acceptance = _due_acceptance_result(acceptance_value)
    if acceptance["observation_cutoff"] != instruction.observation_cutoff:
        _control_fail("HK_V1_DUE_ACCEPTANCE_RESULT_INVALID")
    return {**result, "acceptance": acceptance}


def rebuild_hk_v1_due_handoff(
    instruction_payload: object, due_result: object
) -> tuple[HongKongV1DueCycleInstruction, dict[str, object]]:
    """Rebuild the exact persisted due instruction/result pair at the activity boundary."""
    instruction = _detached_due_instruction(instruction_payload)
    return instruction, _due_orchestrator_result(due_result, instruction)


def _due_acceptance_result(value: object) -> dict[str, object]:
    """Rebuild the exact acceptance activity result before returning due-cycle success."""
    document = _due_object(value)
    if frozenset(document) != _ACCEPTANCE_RESULT_FIELDS:
        _control_fail("HK_V1_DUE_ACCEPTANCE_RESULT_INVALID")
    result = _due_text(document["result"])
    blockers = _due_text_list(document["blocker_codes"])
    proposal = document["proposal_reference"]
    if (
        document["schema_id"] != "asklegal.hk-v1.acceptance-cycle-result"
        or document["schema_version"] != _VERSION
        or document["kind"] not in {"BASELINE", "UPDATE"}
        or not _due_text(document["operation_id"]).startswith("cyc_")
        or _FINGERPRINT.fullmatch(_due_text(document["command_fingerprint"])) is None
        or _due_text(document["observation_cutoff"]) == ""
        or tuple(_due_text_list(document["families"])) != _ACCEPTANCE_FAMILIES
        or tuple(_due_text_list(document["scope_ids"])) != _ACCEPTANCE_SCOPES
        or result not in {"NO_CHANGE", "NOT_READY", "PROPOSAL_READY"}
        or (result == "NO_CHANGE" and (blockers or proposal is not None))
        or (result == "NOT_READY" and (not blockers or proposal is not None))
        or (result == "PROPOSAL_READY" and (blockers or not _valid_due_proposal(proposal)))
    ):
        _control_fail("HK_V1_DUE_ACCEPTANCE_RESULT_INVALID")
    return document


def _due_text_list(value: object) -> list[str]:
    if not _is_exact_list(value):
        _control_fail("HK_V1_DUE_ACCEPTANCE_RESULT_INVALID")
    items: list[str] = []
    for item in value:
        text = _due_text(item)
        if not text:
            _control_fail("HK_V1_DUE_ACCEPTANCE_RESULT_INVALID")
        items.append(text)
    return items


def _valid_due_proposal(value: object) -> bool:
    try:
        document = _due_object(value)
        return (
            frozenset(document)
            == frozenset({"vault", "logical_key", "version_id", "fingerprint", "byte_length"})
            and document["vault"] == "PRIMARY"
            and bool(_due_text(document["logical_key"]))
            and bool(_due_text(document["version_id"]))
            and _FINGERPRINT.fullmatch(_due_text(document["fingerprint"])) is not None
            and _due_nonnegative_int(document["byte_length"]) > 0
        )
    except ControlPipelineError:
        return False


def _due_orchestrator_result(
    value: object, instruction: HongKongV1DueCycleInstruction
) -> dict[str, object]:
    """Rebuild all result fields that a deterministic orchestrator can bind itself."""
    try:
        return _due_orchestrator_result_unchecked(value, instruction)
    except ControlPipelineError:
        raise
    except Exception as error:  # noqa: BLE001 - activity delivery is an untrusted boundary.
        _control_fail_from("HK_V1_DUE_RESULT_INVALID", error)


def _due_orchestrator_result_unchecked(
    value: object, instruction: HongKongV1DueCycleInstruction
) -> dict[str, object]:
    """Apply the deterministic post-activity reconstruction after boundary normalization."""
    document = _due_object(value)
    if frozenset(document) != _DUE_RESULT_FIELDS:
        _due_result_invalid()
    try:
        cycle_id = _due_text(document["cycle_id"])
        plan_fingerprint = _due_fingerprint(document["plan_fingerprint"])
        predecessor_fingerprint = _due_fingerprint(document["predecessor_state_fingerprint"])
        manifest_created = _due_bool(document["manifest_created"])
        predecessor_created = _due_bool(document["predecessor_state_created"])
        accounting_complete = _due_bool(document["accounting_complete"])
        release_blocking = _due_bool(document["release_blocking"])
        disposition = _due_text(document["disposition"])
        if cycle_id != instruction.cycle_id:
            _due_result_invalid()
        raw_reference = _due_object(document["manifest_reference"])
        if frozenset(raw_reference) != frozenset(
            {"vault", "logical_key", "version_id", "fingerprint", "byte_length"}
        ):
            _due_result_invalid()
        reference = DueImmutableReference(
            _due_text(raw_reference["vault"]),
            _due_text(raw_reference["logical_key"]),
            _due_text(raw_reference["version_id"]),
            _due_fingerprint(raw_reference["fingerprint"]),
            _due_nonnegative_int(raw_reference["byte_length"]),
        )
        if reference.vault != "PRIMARY" or reference.logical_key != hk_v1_due_cycle_manifest_key(
            cycle_id
        ):
            _due_result_invalid()
        family_reference, family_evidence_created = _due_family_evidence(
            document["family_acquisition_evidence"], cycle_id
        )
        categories: dict[str, set[str]] = {}
        for field in _DUE_SOURCE_ID_FIELDS:
            categories[field] = _due_source_ids(document[field])
    except (TypeError, ValueError, HongKongV1DueCycleError) as error:
        _control_fail_from("HK_V1_DUE_RESULT_INVALID", error)
    values = tuple(categories.values())
    if (
        any(
            values[left].intersection(values[right])
            for left in range(len(values))
            for right in range(left + 1, len(values))
        )
        or categories["duplicate_source_ids"]
    ):
        _due_result_invalid()
    if accounting_complete is not (not categories["missing_source_ids"]):
        _due_result_invalid()
    expected_disposition = (
        "INCOMPLETE_ACCOUNTING"
        if not accounting_complete
        else "ACCOUNTED_WITH_GAPS"
        if categories["gap_source_ids"] or categories["failed_source_ids"]
        else "COMPLETE"
    )
    if disposition != expected_disposition:
        _due_result_invalid()
    return {
        "cycle_id": cycle_id,
        "plan_fingerprint": plan_fingerprint,
        "manifest_reference": {
            "vault": reference.vault,
            "logical_key": reference.logical_key,
            "version_id": reference.version_id,
            "fingerprint": reference.fingerprint,
            "byte_length": reference.byte_length,
        },
        "manifest_created": manifest_created,
        "predecessor_state_fingerprint": predecessor_fingerprint,
        "predecessor_state_created": predecessor_created,
        "family_acquisition_evidence": {
            "cycle_id": cycle_id,
            "evidence_reference": {
                "vault": family_reference.vault,
                "logical_key": family_reference.logical_key,
                "version_id": family_reference.version_id,
                "fingerprint": family_reference.fingerprint,
                "byte_length": family_reference.byte_length,
            },
            "evidence_created": family_evidence_created,
        },
        **{field: sorted(source_ids) for field, source_ids in categories.items()},
        "accounting_complete": accounting_complete,
        "release_blocking": release_blocking,
        "disposition": disposition,
    }


def _detached_due_instruction(payload: object) -> HongKongV1DueCycleInstruction:
    """Parse and rebuild a control payload without consulting runtime Matrix state."""
    return _rebuild_due_instruction(payload)


def observation_result(evidence: object, decision: object) -> dict[str, object]:
    """Close observation without manufacturing a release or promotion request."""
    return {
        "evidence": evidence,
        "decision": decision,
        "promotion_state": "NOT_REQUESTED",
    }
