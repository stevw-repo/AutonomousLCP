"""Durable orchestration proof for the local Hong Kong V1 due cycle."""

from __future__ import annotations

from collections.abc import Callable, Generator
from copy import deepcopy
from hashlib import sha256
from typing import Never, cast

import pytest
from asklegal_acquisition_worker import hk_v1_due_cycle as due_cycle
from asklegal_acquisition_worker.acquisition_journal import AcquisitionCycleResult
from asklegal_acquisition_worker.hk_cases_acquisition import (
    YearShardDisposition,
    build_cases_acquisition_manifest,
)
from asklegal_acquisition_worker.hk_v1_due_cycle import DuePlanOutput, acquire_hk_v1_due_cycle
from asklegal_acquisition_worker.v1_pipeline import (
    AcquisitionPipelineError,
    acquire_resumable_source_cycle,
)
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import OrchestrationContext, TaskFailedError
from asklegal_reporting import (
    DueCycleKind,
    DueImmutableReference,
    HongKongV1DueCycleError,
    HongKongV1DueCycleInstruction,
    hk_v1_due_cycle_manifest_key,
    hk_v1_due_source_terminal_key,
    load_hk_v1_coverage_matrix,
)


class _RecordingContext:
    """Minimal replay driver that records only Durable activity facts."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def call_activity(self, name: str, *, input: object) -> object:  # noqa: A002
        self.calls.append((name, input))
        return object()

    def call_sub_orchestrator(
        self,
        name: str,
        *,
        input: object,  # noqa: A002 - mirror the Durable SDK keyword.
        instance_id: str | None = None,
        version: str | None = None,
    ) -> object:
        del name, input, instance_id, version
        return object()


class _ExplodingDict(dict[str, object]):
    """Hostile JSON-shaped mapping that raises during a normal parser operation."""

    def items(self) -> Never:
        raise _HostileOperationError


class _HostileOperationError(RuntimeError):
    """One ordinary hostile-value failure used by the parser pressure tests."""


class _ExplodingText(str):
    """Hostile string subclass that raises if a parser trusts equality."""

    __slots__ = ()
    __hash__ = str.__hash__

    def __eq__(self, value: object) -> bool:
        raise _HostileOperationError


class _EqualityLiar(str):
    """A text subclass whose comparisons falsely approve an invalid plan leaf."""

    __slots__ = ()
    __hash__ = str.__hash__

    def __eq__(self, value: object) -> bool:
        return True

    def __ne__(self, value: object) -> bool:
        return False


_PLAN_FUNCTION_NAME = "_plan"
_PLAN_BODY_FUNCTION_NAME = "_plan_body"
_REPLAY_RESOURCE_ACCESS = "orchestrator replay accessed an activity-owned resource"
type _PlanMutation = Callable[[DuePlanOutput], dict[str, object]]


def _fingerprint(character: str) -> str:
    return f"sha256:{character * 64}"


def _instruction(kind: DueCycleKind = DueCycleKind.DAILY_CURRENT_LAW) -> dict[str, str]:
    matrix = load_hk_v1_coverage_matrix()
    return {
        "cycle_id": f"hk-v1-{kind.value.lower()}-20260826",
        "cycle_kind": kind.value,
        "scheduled_at": "2026-08-26T00:00:00Z",
        "observation_cutoff": "2026-08-26T00:00:00Z",
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
    }


def _json_object(value: object) -> dict[str, JsonValue]:
    """Validate one test driver value at the same recursive JSON boundary as Durable input."""
    checked = checked_json_value(value)
    assert isinstance(checked, dict)
    return checked


def _last_input(context: _RecordingContext) -> dict[str, JsonValue]:
    """Return the latest Durable input after one test-side structural assertion."""
    return _json_object(context.calls[-1][1])


def _cases_instruction(cycle_id: str = "cyc_20260902_cases") -> dict[str, object]:
    return {
        "schema_id": "asklegal.cases-resumable-acquisition-instruction",
        "schema_version": "1.0.0",
        "source_family": "CASES",
        "cycle_id": cycle_id,
        "work_graph_ref": "opaque/graph",
    }


def _family_result(child: due_cycle.ScheduledFamilyChild, cutoff: str) -> bytes:
    """Build one valid non-success manifest for legacy orchestrator pressure tests."""
    cycle_id = child["cycle_id"]
    if child["source_family"] == "CASES":
        manifest = build_cases_acquisition_manifest(
            cycle_id=cycle_id,
            observation_cutoff=cutoff,
            year_dispositions=(
                YearShardDisposition(
                    1997,
                    "1997-07-01",
                    0,
                    0,
                    0,
                    0,
                    1,
                    AcquisitionCycleResult.INCOMPLETE_RETRYABLE,
                ),
            ),
            judgment_bundle_refs=(),
            discrepancy_refs=(),
            journal_head_fingerprint=_fingerprint("a"),
            runner_result=AcquisitionCycleResult.INCOMPLETE_RETRYABLE,
        )
        return canonicalize(checked_json_value(manifest.to_json()))
    legislation_cutoff = cast("str", child["instruction"]["observation_cutoff"])
    document: dict[str, object] = {
        "schema_id": "asklegal.legislation-acquisition-manifest",
        "schema_version": "1.0.0",
        "cycle_id": cycle_id,
        "observation_cutoff": legislation_cutoff,
        "scope_dispositions": [
            {
                "scope_id": scope_id,
                "required_item_count": 1,
                "verified_item_count": 0,
                "retryable_item_count": 1,
                "rejected_item_count": 0,
                "result": "INCOMPLETE_RETRYABLE",
            }
            for scope_id in (
                "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                "HK-LEG-ORDINANCES",
                "HK-LEG-SUBSIDIARY",
            )
        ],
        "verified_item_refs": [],
        "review_issue_refs": [],
        "journal_head_fingerprint": _fingerprint("b"),
        "source_register_fingerprint": _fingerprint("c"),
        "source_baseline_fingerprint": _fingerprint("d"),
        "work_plan_fingerprint": _fingerprint("e"),
        "result": "INCOMPLETE_RETRYABLE",
    }
    document["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(document))).hexdigest()
    )
    return canonicalize(checked_json_value(document))


def _family_receipt(instruction: dict[str, str]) -> dict[str, object]:
    key = f"poc/report/hk-v1-due-cycle/{instruction['cycle_id']}/family-acquisitions.json"
    fingerprint = f"sha256:{sha256(key.encode()).hexdigest()}"
    return {
        "cycle_id": instruction["cycle_id"],
        "evidence_reference": {
            "vault": "PRIMARY",
            "logical_key": key,
            "version_id": "v" + fingerprint.removeprefix("sha256:"),
            "fingerprint": fingerprint,
            "byte_length": 1,
        },
        "evidence_created": True,
    }


def _workflow(
    context: _RecordingContext, payload: object
) -> Generator[object, object, dict[str, object]]:
    """Hide already-covered family checkpoints from the legacy source-accounting tests."""
    inner = acquire_hk_v1_due_cycle(cast("OrchestrationContext", context), payload)
    task = next(inner)
    planned = yield task
    task = inner.send(planned)
    if type(payload) is not dict:
        return cast("dict[str, object]", task)
    instruction = HongKongV1DueCycleInstruction.from_json(
        checked_json_value(cast("object", payload))
    )
    children = due_cycle.scheduled_hk_v1_family_children(instruction)
    for child in children:
        task = inner.send(_family_result(child, instruction.observation_cutoff))
    task = inner.send(_family_receipt(cast("dict[str, str]", payload)))
    while True:
        try:
            result = yield task
            task = inner.send(result)
        except StopIteration as stopped:
            value = cast("dict[str, object]", stopped.value)
            value.pop("family_acquisition_evidence", None)
            return value
        except GeneratorExit:
            inner.close()
            raise
        except BaseException as error:  # noqa: BLE001 - faithfully proxy generator.throw.
            try:
                task = inner.throw(error)
            except StopIteration as stopped:
                value = cast("dict[str, object]", stopped.value)
                value.pop("family_acquisition_evidence", None)
                return value


def _plan(instruction: dict[str, str]) -> DuePlanOutput:
    """Use the checked-in static matrix/register projection as the plan fixture."""
    typed = HongKongV1DueCycleInstruction.from_json(instruction)
    plan_function = getattr(due_cycle, _PLAN_FUNCTION_NAME)
    plan_body_function = getattr(due_cycle, _PLAN_BODY_FUNCTION_NAME)
    return plan_body_function(plan_function(typed))


def _terminal_reference(cycle_id: str, source_id: str) -> dict[str, object]:
    logical_key = hk_v1_due_source_terminal_key(cycle_id, source_id)
    fingerprint = f"sha256:{sha256(logical_key.encode()).hexdigest()}"
    return {
        "vault": "PRIMARY",
        "logical_key": logical_key,
        "version_id": "v" + fingerprint.removeprefix("sha256:"),
        "fingerprint": fingerprint,
        "byte_length": 1,
    }


def _capture_result(
    instruction: dict[str, str], plan_fingerprint: str, source_id: str
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "plan_fingerprint": plan_fingerprint,
        "terminal_reference": _terminal_reference(instruction["cycle_id"], source_id),
        "payload_created": True,
        "attempt_created": True,
        "terminal_created": True,
    }


def _assembly_result(
    instruction: dict[str, str],
    plan_fingerprint: str,
    source_ids: list[str],
    *,
    release_blocking: bool = True,
    terminal_source_ids: list[str] | None = None,
) -> dict[str, object]:
    key = hk_v1_due_cycle_manifest_key(instruction["cycle_id"])
    manifest_fingerprint = f"sha256:{sha256(key.encode()).hexdigest()}"
    accepted_source_ids = source_ids if terminal_source_ids is None else terminal_source_ids
    missing_source_ids = sorted(set(source_ids).difference(accepted_source_ids))
    accounting_complete = not missing_source_ids
    disposition = "ACCOUNTED_WITH_GAPS" if accounting_complete else "INCOMPLETE_ACCOUNTING"
    manifest_reference = DueImmutableReference(
        "PRIMARY",
        key,
        "v" + manifest_fingerprint.removeprefix("sha256:"),
        manifest_fingerprint,
        1,
    )
    expected_predecessor = due_cycle.DueCyclePredecessorState(
        HongKongV1DueCycleInstruction.from_json(instruction),
        plan_fingerprint,
        None,
        manifest_reference,
        manifest_fingerprint,
    )
    return {
        "cycle_id": instruction["cycle_id"],
        "plan_fingerprint": plan_fingerprint,
        "manifest_reference": {
            "vault": "PRIMARY",
            "logical_key": key,
            "version_id": "v" + manifest_fingerprint.removeprefix("sha256:"),
            "fingerprint": manifest_fingerprint,
            "byte_length": 1,
        },
        "manifest_created": True,
        "predecessor_state_fingerprint": expected_predecessor.state_fingerprint,
        "predecessor_state_created": True,
        "complete_source_ids": [],
        "missing_source_ids": missing_source_ids,
        "duplicate_source_ids": [],
        "gap_source_ids": [],
        "failed_source_ids": accepted_source_ids,
        "accounting_complete": accounting_complete,
        "release_blocking": release_blocking,
        "disposition": disposition,
    }


def _task_names(context: _RecordingContext) -> list[str]:
    return [name for name, _input in context.calls if name != "record_hk_v1_family_acquisitions"]


def test_orchestrator_plans_captures_in_order_and_assembles_once() -> None:
    """A valid planned source set is checkpointed one capture at a time."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    assert _task_names(context) == ["plan_hk_v1_due_cycle"]

    next_task = workflow.send(plan)
    assert next_task is not None
    assert _task_names(context) == ["plan_hk_v1_due_cycle", "capture_hk_v1_due_source"]
    assert context.calls[-1][1] == {
        "instruction": instruction,
        "expected_plan_fingerprint": plan_fingerprint,
        "source_id": source_ids[0],
        "family_evidence_reference": _family_receipt(instruction)["evidence_reference"],
    }

    for source_id in source_ids[:-1]:
        next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_id))
        assert next_task is not None
        assert _last_input(context)["source_id"] == source_ids[source_ids.index(source_id) + 1]

    next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_ids[-1]))
    assert next_task is not None
    assert _task_names(context) == ["plan_hk_v1_due_cycle"] + ["capture_hk_v1_due_source"] * len(
        source_ids
    ) + ["assemble_hk_v1_due_cycle"]
    assert _last_input(context) == {
        "instruction": instruction,
        "expected_plan_fingerprint": plan_fingerprint,
        "terminal_references": [
            {
                "source_id": source_id,
                "reference": _terminal_reference(instruction["cycle_id"], source_id),
            }
            for source_id in source_ids
        ],
    }

    with pytest.raises(StopIteration) as stopped:
        workflow.send(_assembly_result(instruction, plan_fingerprint, source_ids))
    assert stopped.value.value == _assembly_result(instruction, plan_fingerprint, source_ids)


@pytest.mark.parametrize(
    "result",
    ["INCOMPLETE_RETRYABLE", "INCOMPLETE_TERMINAL"],
)
def test_resumable_cycle_orchestrator_delegates_once_to_the_shared_runner_activity(
    result: str,
) -> None:
    """Both future family adapters must enter one shared activity, not fork scheduler logic."""
    payload = _cases_instruction()
    context = _RecordingContext()
    workflow = acquire_resumable_source_cycle(cast("OrchestrationContext", context), payload)

    next(workflow)
    assert context.calls == [("run_resumable_acquisition", payload)]
    expected = {"result": result, "fingerprint": _fingerprint("a")}
    with pytest.raises(StopIteration) as stopped:
        workflow.send(expected)
    assert stopped.value.value == expected


def test_resumable_cycle_orchestrator_routes_exact_legislation_instruction() -> None:
    """Only the closed production instruction reaches the issued-window activity."""
    payload = {
        "source_family": "LEGISLATION",
        "cycle_id": "cyc_20260904_legislation",
        "observation_cutoff": "2026-09-04T00:00:00+00:00",
        "budget": {
            "maximum_starts": 100,
            "maximum_retained_bytes": 100_000_000_000,
            "maximum_elapsed_seconds": 60,
            "maximum_redirects": 1_000,
        },
    }
    context = _RecordingContext()
    workflow = acquire_resumable_source_cycle(cast("OrchestrationContext", context), payload)

    next(workflow)
    assert context.calls == [("run_legislation_acquisition", payload)]
    expected = b'{"result":"COMPLETE"}'
    with pytest.raises(StopIteration) as stopped:
        workflow.send(expected)
    assert stopped.value.value == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"source_family": "REGULATORY", "cycle_id": "cyc_20260904_regulatory"},
        {
            "source_family": "LEGISLATION",
            "cycle_id": "cyc_20260904_legislation",
            "work_graph_ref": "opaque/graph",
        },
        {
            "source_family": "CASES",
            "cycle_id": "cyc_20260904_cases",
            "observation_cutoff": "2026-09-04T00:00:00+00:00",
            "budget": {},
        },
        _cases_instruction("cyc_showcases_foreign"),
        _cases_instruction("not-a-cycle-cases"),
        _cases_instruction("cases"),
        {**_cases_instruction(), "unknown": True},
        {**_cases_instruction(), "source_family": "LEGISLATION"},
    ],
)
def test_resumable_cycle_orchestrator_rejects_unknown_or_mixed_family_payloads(
    payload: object,
) -> None:
    """Unknown or mixed family schemas stop before activity scheduling."""
    context = _RecordingContext()
    workflow = acquire_resumable_source_cycle(cast("OrchestrationContext", context), payload)

    with pytest.raises(
        AcquisitionPipelineError, match="RESUMABLE_SOURCE_CYCLE_INSTRUCTION_INVALID"
    ):
        next(workflow)
    assert context.calls == []


def test_orchestrator_records_closed_failure_without_exception_diagnostics() -> None:
    """A failed capture requests only the closed fallback payload."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    workflow.send(plan)
    next_task = workflow.throw(
        TaskFailedError("untrusted transport detail", RuntimeError("secret"))
    )
    assert next_task is not None
    assert _task_names(context) == [
        "plan_hk_v1_due_cycle",
        "capture_hk_v1_due_source",
        "record_hk_v1_due_source_failure",
    ]
    assert context.calls[-1][1] == {
        "instruction": instruction,
        "expected_plan_fingerprint": plan_fingerprint,
        "source_id": source_ids[0],
        "failure_code": "DUE_SOURCE_ACTIVITY_FAILED",
    }


def test_orchestrator_rejects_unknown_instruction_fields_before_activity() -> None:
    """The durable boundary cannot accept caller-controlled due-plan additions."""
    context = _RecordingContext()
    workflow = _workflow(context, _instruction() | {"transport": "forbidden"})

    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_INSTRUCTION_INVALID"):
        next(workflow)
    assert context.calls == []


def test_orchestrator_rejects_false_nonblocking_assembly_result() -> None:
    """A scheduler-safe result cannot downgrade a blocking due-source failure."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    workflow.send(plan)
    next_task: object | None = None
    for source_id in source_ids:
        next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_id))
    assert next_task is not None

    with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_ASSEMBLY_INVALID"):
        workflow.send(
            _assembly_result(
                instruction,
                plan_fingerprint,
                source_ids,
                release_blocking=False,
            )
        )


def test_orchestrator_omits_a_source_when_capture_and_failure_acknowledgements_fail() -> None:
    """No failed-task diagnostic may become an invented terminal reference."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    workflow.send(plan)
    next_task = workflow.send({"malformed": "capture acknowledgement"})
    assert next_task is not None
    assert _task_names(context)[-1] == "record_hk_v1_due_source_failure"
    next_task = workflow.throw(TaskFailedError("untrusted failure detail", RuntimeError("secret")))
    assert next_task is not None
    assert _task_names(context)[-1] == "capture_hk_v1_due_source"
    assert _last_input(context)["source_id"] == source_ids[1]

    for source_id in source_ids[1:]:
        next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_id))
    assert next_task is not None
    assembly_input = _last_input(context)
    assert assembly_input["terminal_references"] == [
        {
            "source_id": source_id,
            "reference": _terminal_reference(instruction["cycle_id"], source_id),
        }
        for source_id in source_ids[1:]
    ]

    with pytest.raises(StopIteration) as stopped:
        workflow.send(
            _assembly_result(
                instruction,
                plan_fingerprint,
                source_ids,
                terminal_source_ids=source_ids[1:],
            )
        )
    result = _json_object(stopped.value.value)
    assert result["missing_source_ids"] == [source_ids[0]]


@pytest.mark.parametrize(
    ("kind", "expected_count"),
    [
        (DueCycleKind.DAILY_CURRENT_LAW, 4),
        (DueCycleKind.WEEKLY_RELEASE, 6),
        (DueCycleKind.MONTHLY_CROSS_CHECK, 1),
        (DueCycleKind.FULL_PERIODIC, 7),
    ],
)
def test_orchestrator_accepts_only_the_exact_matrix_due_set(
    kind: DueCycleKind, expected_count: int
) -> None:
    """The plan acknowledgement cannot select a caller-defined subset or order."""
    instruction = _instruction(kind)
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    next_task = workflow.send(plan)
    assert next_task is not None
    assert len(source_ids) == expected_count
    assert _last_input(context)["source_id"] == source_ids[0]


@pytest.mark.parametrize(
    "mutation",
    [
        {"unknown": "forbidden"},
        {"source_ids": []},
        {"predecessor_fingerprint": _fingerprint("0")},
    ],
)
def test_orchestrator_rejects_malformed_plan_before_capture(mutation: dict[str, object]) -> None:
    """No capture is issued until the complete plan projection is verified."""
    instruction = _instruction()
    plan = _plan(instruction) | mutation
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_PLAN_INVALID"):
        workflow.send(plan)
    assert _task_names(context) == ["plan_hk_v1_due_cycle"]


def test_orchestrator_rejects_empty_cached_categories_for_accepted_terminals() -> None:
    """A manifest result must account for every accepted terminal exactly once."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    workflow.send(plan)
    next_task = None
    for source_id in source_ids:
        next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_id))
    assert next_task is not None
    malformed = _assembly_result(instruction, plan_fingerprint, source_ids)
    malformed["failed_source_ids"] = []
    malformed["disposition"] = "COMPLETE"
    with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_ASSEMBLY_INVALID"):
        workflow.send(malformed)


def test_orchestrator_preserves_activity_validated_complete_source_category() -> None:
    """The orchestrator does not erase the activity's cycle-local evidence decision."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    workflow.send(plan)
    next_task: object | None = None
    for source_id in source_ids:
        next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_id))
    assert next_task is not None
    malformed = _assembly_result(instruction, plan_fingerprint, source_ids)
    malformed["complete_source_ids"] = [source_ids[0]]
    malformed["failed_source_ids"] = source_ids[1:]
    with pytest.raises(StopIteration) as completed:
        workflow.send(malformed)
    assert completed.value.value["complete_source_ids"] == [source_ids[0]]


def test_orchestrator_rejects_plan_identity_and_source_projection_mutations() -> None:
    """Every claimed plan field is checked before the first source checkpoint."""
    instruction = _instruction()
    expected_plan = _plan(instruction)
    source_ids = expected_plan["source_ids"]
    malformed_plans = (
        expected_plan | {"schema_id": "wrong"},
        expected_plan | {"cycle_id": "other-cycle"},
        expected_plan | {"plan_fingerprint": _fingerprint("0")},
        expected_plan | {"source_ids": list(reversed(source_ids))},
        expected_plan | {"source_ids": source_ids[:-1]},
        expected_plan | {"source_ids": [source_ids[0], *source_ids]},
        expected_plan | {"instruction": instruction | {"scheduled_at": "2026-08-27T00:00:00Z"}},
    )
    for malformed_plan in malformed_plans:
        context = _RecordingContext()
        workflow = _workflow(context, instruction)
        next(workflow)
        with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_PLAN_INVALID"):
            workflow.send(malformed_plan)
        assert _task_names(context) == ["plan_hk_v1_due_cycle"]


def test_orchestrator_routes_every_malformed_capture_acknowledgement_to_closed_failure() -> None:
    """Only an exact primary terminal receipt is allowed to reach assembly."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    source_id = source_ids[0]
    valid = _capture_result(instruction, plan_fingerprint, source_id)
    valid_reference = valid["terminal_reference"]
    assert isinstance(valid_reference, dict)
    malformed_results: list[dict[str, object]] = [
        valid | {"source_id": source_ids[1]},
        valid | {"source_id": _EqualityLiar(source_id)},
        valid | {"plan_fingerprint": _fingerprint("0")},
        valid | {"payload_created": "true"},
        valid | {"unknown": "forbidden"},
        valid | {"terminal_reference": valid_reference | {"vault": "RECOVERY"}},
        valid | {"terminal_reference": valid_reference | {"logical_key": "wrong/key"}},
        valid | {"terminal_reference": valid_reference | {"version_id": "wrong"}},
        valid | {"terminal_reference": valid_reference | {"fingerprint": _fingerprint("0")}},
        valid | {"terminal_reference": valid_reference | {"byte_length": True}},
    ]
    for malformed_result in malformed_results:
        context = _RecordingContext()
        workflow = _workflow(context, instruction)
        next(workflow)
        workflow.send(plan)
        next_task = workflow.send(deepcopy(malformed_result))
        assert next_task is not None
        assert _task_names(context)[-1] == "record_hk_v1_due_source_failure"
        assert context.calls[-1][1] == {
            "instruction": instruction,
            "expected_plan_fingerprint": plan_fingerprint,
            "source_id": source_id,
            "failure_code": "DUE_SOURCE_ACTIVITY_FAILED",
        }


def test_orchestrator_rejects_malformed_assembly_cached_fields() -> None:
    """The final activity cannot turn retained terminal facts into a false result."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    base_result = _assembly_result(instruction, plan_fingerprint, source_ids)
    manifest_reference = base_result["manifest_reference"]
    predecessor_state_fingerprint = base_result["predecessor_state_fingerprint"]
    assert isinstance(manifest_reference, dict)
    assert isinstance(predecessor_state_fingerprint, str)
    malformed_results: list[dict[str, object]] = [
        base_result | {"unknown": "forbidden"},
        {key: value for key, value in base_result.items() if key != "predecessor_state_created"},
        base_result | {"predecessor_state_fingerprint": "not-a-fingerprint"},
        base_result
        | {"predecessor_state_fingerprint": _EqualityLiar(predecessor_state_fingerprint)},
        base_result | {"manifest_reference": manifest_reference | {"vault": "RECOVERY"}},
        base_result | {"missing_source_ids": [source_ids[0]]},
        base_result | {"accounting_complete": False},
        base_result | {"disposition": "COMPLETE"},
        base_result | {"release_blocking": False},
    ]
    for malformed_result in malformed_results:
        context = _RecordingContext()
        workflow = _workflow(context, instruction)
        next(workflow)
        workflow.send(plan)
        next_task: object | None = None
        for source_id in source_ids:
            next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_id))
        assert next_task is not None
        with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_ASSEMBLY_INVALID"):
            workflow.send(deepcopy(malformed_result))


def test_orchestrator_replay_reissues_identical_durable_inputs() -> None:
    """A replay has no clock, transport, or process-local payload contribution."""
    instruction = _instruction()
    plan = _plan(instruction)
    first = _RecordingContext()
    second = _RecordingContext()
    first_workflow = _workflow(first, instruction)
    second_workflow = _workflow(second, instruction)

    next(first_workflow)
    next(second_workflow)
    first_workflow.send(plan)
    second_workflow.send(plan)
    assert first.calls == second.calls


def test_orchestrator_replay_never_loads_policy_or_touches_filesystem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """History-contained plan facts continue without resource or filesystem access."""
    instruction = _instruction()
    plan = _plan(instruction)
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)

    def explode(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError(_REPLAY_RESOURCE_ACCESS)

    monkeypatch.setattr(due_cycle, "load_hk_v1_coverage_matrix", explode)
    monkeypatch.setattr(due_cycle, "_fixed_register_bundles", explode)
    monkeypatch.setattr(due_cycle.resources, "files", explode)
    monkeypatch.setattr(due_cycle, "TemporaryDirectory", explode)
    monkeypatch.setattr(due_cycle, "Path", explode)

    next_task = workflow.send(plan)
    assert next_task is not None
    assert _task_names(context) == ["plan_hk_v1_due_cycle", "capture_hk_v1_due_source"]


@pytest.mark.parametrize("hostile", [_ExplodingDict(), _ExplodingText("plan")])
def test_orchestrator_normalizes_hostile_plan_results_before_capture(hostile: object) -> None:
    """Ordinary container and equality exceptions cannot bypass the plan boundary."""
    instruction = _instruction()
    plan = _plan(instruction)
    result = hostile if isinstance(hostile, _ExplodingDict) else plan | {"schema_id": hostile}
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_PLAN_INVALID"):
        workflow.send(result)
    assert _task_names(context) == ["plan_hk_v1_due_cycle"]


def test_orchestrator_recovers_hostile_capture_and_failure_results_as_missing() -> None:
    """Both malformed acknowledgement paths leave a source missing and continue safely."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    workflow.send(plan)
    next_task = workflow.send(_ExplodingDict())
    assert next_task is not None
    assert _task_names(context)[-1] == "record_hk_v1_due_source_failure"
    next_task = workflow.send(_ExplodingDict())
    assert next_task is not None
    assert _task_names(context)[-1] == "capture_hk_v1_due_source"
    assert _last_input(context)["source_id"] == source_ids[1]

    for source_id in source_ids[1:]:
        next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_id))
    assert next_task is not None
    with pytest.raises(StopIteration) as stopped:
        workflow.send(
            _assembly_result(
                instruction,
                plan_fingerprint,
                source_ids,
                terminal_source_ids=source_ids[1:],
            )
        )
    assert _json_object(stopped.value.value)["missing_source_ids"] == [source_ids[0]]


def test_orchestrator_normalizes_hostile_assembly_result() -> None:
    """A hostile terminal summary cannot escape the closed assembly-result parser."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    workflow.send(plan)
    next_task: object | None = None
    for source_id in source_ids:
        next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_id))
    assert next_task is not None
    with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_ASSEMBLY_INVALID"):
        workflow.send(_ExplodingDict())


def test_orchestrator_normalizes_hostile_outer_instruction_before_activity() -> None:
    """A hostile control payload cannot escape the six-field instruction boundary."""
    context = _RecordingContext()
    workflow = _workflow(context, _ExplodingDict())

    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_INSTRUCTION_INVALID"):
        next(workflow)
    assert context.calls == []


_EQUALITY_LIAR_PLAN_MUTATIONS: tuple[_PlanMutation, ...] = (
    lambda plan: plan | {"schema_id": _EqualityLiar("wrong")},
    lambda plan: plan | {"schema_version": _EqualityLiar("wrong")},
    lambda plan: plan | {"instruction": plan["instruction"] | {"cycle_id": _EqualityLiar("wrong")}},
    lambda plan: (
        plan
        | {
            "registers": [
                plan["registers"][0] | {"register_id": _EqualityLiar("wrong")},
                *plan["registers"][1:],
            ]
        }
    ),
    lambda plan: plan | {"source_ids": [_EqualityLiar("wrong"), *plan["source_ids"][1:]]},
)


@pytest.mark.parametrize("mutate", _EQUALITY_LIAR_PLAN_MUTATIONS)
def test_orchestrator_rejects_equality_liar_plan_leaves_before_capture(
    mutate: _PlanMutation,
) -> None:
    """A checked JSON projection still rejects non-exact primitive subclasses."""
    instruction = _instruction()
    plan = _plan(instruction)
    malformed = mutate(plan)
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_PLAN_INVALID"):
        workflow.send(malformed)
    assert _task_names(context) == ["plan_hk_v1_due_cycle"]


def test_orchestrator_rejects_canonical_but_wrong_predecessor_fingerprint() -> None:
    """Assembly returns the exact predecessor state identity, not any valid digest."""
    instruction = _instruction()
    plan = _plan(instruction)
    source_ids = plan["source_ids"]
    plan_fingerprint = plan["plan_fingerprint"]
    context = _RecordingContext()
    workflow = _workflow(context, instruction)

    next(workflow)
    workflow.send(plan)
    next_task: object | None = None
    for source_id in source_ids:
        next_task = workflow.send(_capture_result(instruction, plan_fingerprint, source_id))
    assert next_task is not None
    malformed = _assembly_result(instruction, plan_fingerprint, source_ids) | {
        "predecessor_state_fingerprint": _fingerprint("d")
    }
    with pytest.raises(HongKongV1DueCycleError, match="DUE_ORCHESTRATOR_ASSEMBLY_INVALID"):
        workflow.send(malformed)
