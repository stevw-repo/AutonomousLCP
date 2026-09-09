"""Local-only CONTROL_PLANE handoff proof for the Hong Kong V1 due cycle."""

from __future__ import annotations

import json
import logging
from _collections_abc import dict_items
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast

import asklegal_reporting.hk_v1_coverage as coverage
import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_control_plane import v1_pipeline
from asklegal_control_plane.v1_infrastructure import V1ControlInfrastructure
from asklegal_control_plane.v1_pipeline import ControlActivities
from asklegal_durable_task import ActivityContext, OrchestrationContext, OrchestrationStatus
from asklegal_reporting import (
    HongKongV1CoverageMatrix,
    hk_v1_due_cycle_manifest_key,
    hk_v1_due_family_acquisition_key,
    load_hk_v1_coverage_matrix,
)
from durabletask import worker as durable_worker
from durabletask.serialization import JsonDataConverter

_MATRIX_PATH = Path(coverage.__file__).with_name("hk_v1_coverage_matrix.json")


def _count_preserving_npc_swap_matrix(tmp_path: Path) -> HongKongV1CoverageMatrix:
    """Load a validly resealed Matrix that swaps Basic Law for one dormant NPC role."""
    document = parse_json_bytes(_MATRIX_PATH.read_bytes(), max_bytes=1_000_000)
    assert isinstance(document, dict)
    rows = document["rows"]
    assert isinstance(rows, list)
    changed: set[str] = set()
    for row in rows:
        assert isinstance(row, dict)
        source_id = row["source_id"]
        if source_id == "HK-LEG-BASIC-LAW-PORTAL":
            row["cadence"] = "EXCLUDED_FROM_V1"
            changed.add("HK-LEG-BASIC-LAW-PORTAL")
        elif source_id == "HK-LEG-NPC-NATIONAL-LAWS-DATABASE":
            row["cadence"] = "MONTHLY_AND_EVENT_TRIGGERED"
            changed.add("HK-LEG-NPC-NATIONAL-LAWS-DATABASE")
    assert changed == {
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
    }
    unsigned = dict(document)
    del unsigned["fingerprint"]
    document["fingerprint"] = f"sha256:{sha256(canonicalize(unsigned)).hexdigest()}"
    path = tmp_path / "control-count-preserving-npc-swap.json"
    path.write_bytes(canonicalize(document))
    return load_hk_v1_coverage_matrix(path)


@dataclass
class _CompletedState:
    runtime_status: OrchestrationStatus
    serialized_output: str
    failure_details: None = None


class _RecordingClient:
    def __init__(self, result: str, body: str | None = None) -> None:
        self._result = result
        self._body = _result_body() if body is None else body
        self.schedule_calls: list[tuple[object, object, object, object]] = []
        self.wait_calls: list[object] = []

    def schedule_new_orchestration(
        self,
        orchestration: object,
        *,
        input: object,  # noqa: A002 - mirrors the pinned Durable Task SDK keyword.
        instance_id: object,
        version: object,
    ) -> str:
        self.schedule_calls.append((orchestration, input, instance_id, version))
        return self._result

    def wait_for_orchestration_completion(self, instance_id: object, *, timeout: object) -> object:
        self.wait_calls.append((instance_id, timeout))
        return _CompletedState(OrchestrationStatus.COMPLETED, self._body)


class _RecordingScheduler:
    scheduler_service = "dts-general"
    task_hub = "acquisition"

    def __init__(self, client: _RecordingClient) -> None:
        self._client = client
        self.default_versions: list[object] = []

    def create_client(self, *, default_version: object) -> _RecordingClient:
        self.default_versions.append(default_version)
        return self._client


class _ExplodingList(list[object]):
    """A hostile subclass that must never be traversed at the Control boundary."""

    def __iter__(self) -> Iterator[object]:
        message = "untrusted list traversal"
        raise RuntimeError(message)


class _ExplodingDict(dict[str, object]):
    """A hostile mapping whose recursive traversal must not leak implementation detail."""

    def items(self) -> dict_items[str, object]:
        message = "untrusted mapping traversal"
        raise RuntimeError(message)


class _RouteLiar(str):
    """A route leaf that would claim the admitted route if equality were trusted."""

    __slots__ = ()
    __hash__ = str.__hash__

    def __eq__(self, _other: object) -> bool:
        return True

    def __ne__(self, _other: object) -> bool:
        return False


class _OrchestrationContext:
    """Minimal deterministic context retaining all calls made by the orchestrator."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def call_activity(self, name: object, *, input: object) -> object:  # noqa: A002
        self.calls.append((name, input))
        return object()


class _SdkRegistry(Protocol):
    """The narrow installed-SDK registry shape needed for its private dispatch harness."""

    def add_activity(self, fn: object) -> object: ...


class _SdkActivityExecutor(Protocol):
    """The installed-SDK dispatcher shape used to prove two-argument activity invocation."""

    def __init__(
        self, registry: _SdkRegistry, logger: logging.Logger, converter: JsonDataConverter
    ) -> None: ...

    def execute(
        self, orchestration_id: str, name: str, task_id: int, encoded_input: str
    ) -> str | None: ...


class _ExplodingRouteScheduler:
    """A scheduler configuration adapter that faults while projecting its route."""

    @property
    def scheduler_service(self) -> object:
        message = "untrusted scheduler route"
        raise RuntimeError(message)

    @property
    def task_hub(self) -> object:
        return "acquisition"


class _InterruptingRouteScheduler:
    """A BaseException must remain authoritative rather than being normalized away."""

    @property
    def scheduler_service(self) -> object:
        raise KeyboardInterrupt

    @property
    def task_hub(self) -> object:
        return "acquisition"


def _patch_acquisition_scheduler(
    monkeypatch: pytest.MonkeyPatch, scheduler: _RecordingScheduler
) -> None:
    def factory(application: str) -> _RecordingScheduler:
        assert application == "ACQUISITION_WORKER"
        return scheduler

    monkeypatch.setattr(v1_pipeline.V1SchedulerSettings, "for_application", factory)


def _instruction() -> dict[str, str]:
    matrix = load_hk_v1_coverage_matrix()
    return {
        "cycle_id": "hk-v1-full-control-20260826",
        "cycle_kind": "FULL_PERIODIC",
        "scheduled_at": "2026-08-26T00:00:00Z",
        "observation_cutoff": "2026-08-26T00:00:00Z",
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
    }


def test_control_due_composition_uses_only_matrix_revision_hk_v1_003() -> None:
    """The scheduler boundary cannot retain the superseded NPC-active revision."""
    assert _instruction()["matrix_revision"] == "HK-V1-003"


def test_control_due_composition_rejects_resealed_npc_policy_before_client_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exact revision with a count-preserving policy swap has no client authority."""
    matrix = _count_preserving_npc_swap_matrix(tmp_path)
    instruction = _instruction()
    instruction["matrix_revision"] = matrix.revision
    instruction["matrix_fingerprint"] = matrix.fingerprint
    client = _RecordingClient(instruction["cycle_id"])
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_MATRIX_INVALID"):
        ControlActivities(cast("V1ControlInfrastructure", object()), matrix).start_hk_v1_due_cycle(
            ActivityContext("control-due", 1), instruction
        )

    assert scheduler.default_versions == []
    assert client.schedule_calls == []


def _due_source_ids() -> list[str]:
    due_cadences = {
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
    return sorted(
        {row.source_id for row in load_hk_v1_coverage_matrix().rows if row.cadence in due_cadences}
    )


def test_control_current_due_universe_excludes_hkex() -> None:
    """Control reconciles acknowledgements against the issued two-family policy only."""
    assert len(_due_source_ids()) == 7
    assert all(not source_id.startswith("HK-REG-HKEX-") for source_id in _due_source_ids())


def _result_body() -> str:
    cycle_id = _instruction()["cycle_id"]
    return json.dumps(
        {
            "cycle_id": cycle_id,
            "plan_fingerprint": "sha256:" + "a" * 64,
            "manifest_reference": {
                "vault": "PRIMARY",
                "logical_key": hk_v1_due_cycle_manifest_key(cycle_id),
                "version_id": "v" + "b" * 64,
                "fingerprint": "sha256:" + "b" * 64,
                "byte_length": 1,
            },
            "manifest_created": True,
            "family_acquisition_evidence": {
                "cycle_id": cycle_id,
                "evidence_reference": {
                    "vault": "PRIMARY",
                    "logical_key": hk_v1_due_family_acquisition_key(cycle_id),
                    "version_id": "v" + "d" * 64,
                    "fingerprint": "sha256:" + "d" * 64,
                    "byte_length": 2,
                },
                "evidence_created": True,
            },
            "predecessor_state_fingerprint": "sha256:" + "c" * 64,
            "predecessor_state_created": True,
            "complete_source_ids": [],
            "missing_source_ids": [],
            "duplicate_source_ids": [],
            "gap_source_ids": [],
            "failed_source_ids": _due_source_ids(),
            "accounting_complete": True,
            "release_blocking": True,
            "disposition": "ACCOUNTED_WITH_GAPS",
        }
    )


def _successful_result() -> dict[str, object]:
    body = cast("dict[str, object]", json.loads(_result_body()))
    body["complete_source_ids"] = _due_source_ids()
    body["failed_source_ids"] = []
    body["release_blocking"] = False
    body["disposition"] = "COMPLETE"
    return body


def _acceptance_result() -> dict[str, object]:
    return {
        "schema_id": "asklegal.hk-v1.acceptance-cycle-result",
        "schema_version": "1.0.0",
        "kind": "UPDATE",
        "operation_id": "cyc_" + "e" * 48,
        "command_fingerprint": "sha256:" + "f" * 64,
        "observation_cutoff": _instruction()["observation_cutoff"],
        "families": ["CASES", "LEGISLATION"],
        "scope_ids": [
            "HK-CASE-BINDING-POST-1997",
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
            "HK-LEG-ORDINANCES",
            "HK-LEG-SUBSIDIARY",
        ],
        "result": "NO_CHANGE",
        "blocker_codes": [],
        "proposal_reference": None,
    }


def test_due_control_activity_schedules_only_the_exact_acquisition_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local exception names one target, one version, one ID, and detached six-field input."""
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"])
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)
    activities = ControlActivities(
        cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
    )

    result = activities.start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)

    assert scheduler.default_versions == ["1.0.0"]
    assert client.schedule_calls == [
        ("acquire_hk_v1_due_cycle", instruction, instruction["cycle_id"], "1.0.0")
    ]
    assert client.wait_calls == [(instruction["cycle_id"], 900)]
    assert result["cycle_id"] == instruction["cycle_id"]
    assert (
        result["family_acquisition_evidence"]
        == json.loads(_result_body())["family_acquisition_evidence"]
    )


def test_due_control_rebuilds_route_before_client_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A str subclass cannot route a due cycle merely by lying about equality."""
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"])
    scheduler = _RecordingScheduler(client)
    scheduler.scheduler_service = _RouteLiar("promotion")
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_ROUTING_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)

    assert scheduler.default_versions == []
    assert client.schedule_calls == []


@pytest.mark.parametrize("route_field", ["scheduler_service", "task_hub"])
def test_due_control_rejects_each_wrong_scheduler_route_before_client_creation(
    monkeypatch: pytest.MonkeyPatch, route_field: str
) -> None:
    """Both the scheduler service and hub are exact target authority, not advisory metadata."""
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"])
    scheduler = _RecordingScheduler(client)
    setattr(scheduler, route_field, "wrong-route")
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_ROUTING_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)

    assert scheduler.default_versions == []
    assert client.schedule_calls == []


@pytest.mark.parametrize("version", ["2.0.0", _RouteLiar("1.0.0")])
def test_due_control_rejects_each_wrong_or_subclassed_version_before_client_creation(
    monkeypatch: pytest.MonkeyPatch, version: object
) -> None:
    """The local exception has one exact version as well as one exact scheduler destination."""
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"])
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)
    monkeypatch.setattr(v1_pipeline, "_VERSION", version)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_ROUTING_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)

    assert scheduler.default_versions == []
    assert client.schedule_calls == []


def test_due_control_rejects_a_wrong_scheduler_instance_ack_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request is never silently adopted because the scheduler returned another instance."""
    instruction = _instruction()
    client = _RecordingClient("another-due-cycle")
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_INSTANCE_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)

    assert client.wait_calls == []


@pytest.mark.parametrize(
    ("scheduler", "exception"),
    [
        (_ExplodingRouteScheduler(), v1_pipeline.ControlPipelineError),
        (_InterruptingRouteScheduler(), KeyboardInterrupt),
    ],
)
def test_due_control_normalizes_ordinary_route_errors_but_preserves_base_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    scheduler: object,
    exception: type[BaseException],
) -> None:
    """The route boundary is closed for ordinary adapter faults without swallowing cancellation."""
    _patch_acquisition_scheduler(monkeypatch, cast("_RecordingScheduler", scheduler))

    with pytest.raises(exception):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), _instruction())


@pytest.mark.parametrize("hostile_value", [_ExplodingList(), _ExplodingDict()])
def test_due_control_normalizes_hostile_recursive_result_values(
    hostile_value: object,
) -> None:
    """Nested hostile containers fail closed before any recursive operation can invoke them."""
    body = json.loads(_result_body())
    body["failed_source_ids"] = hostile_value
    instruction = v1_pipeline._detached_due_instruction(_instruction())  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    matrix = v1_pipeline._due_matrix_snapshot(load_hk_v1_coverage_matrix())  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_RESULT_INVALID"):
        v1_pipeline._due_result(body, instruction, matrix)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001


def test_due_control_normalizes_hostile_nested_mapping_before_traversal() -> None:
    """An exploding nested reference cannot escape as a raw adapter/runtime exception."""
    body = json.loads(_result_body())
    body["manifest_reference"] = _ExplodingDict(body["manifest_reference"])
    instruction = v1_pipeline._detached_due_instruction(_instruction())  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    matrix = v1_pipeline._due_matrix_snapshot(load_hk_v1_coverage_matrix())  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_RESULT_INVALID"):
        v1_pipeline._due_result(body, instruction, matrix)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001


def test_due_control_detaches_the_canonical_scheduled_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller mutation after dispatch cannot alter the six-field scheduler instruction."""
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"])
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)
    activities = ControlActivities(
        cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
    )

    activities.start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)
    scheduled = client.schedule_calls[0][1]
    instruction["cycle_id"] = "mutated-control-cycle"

    assert scheduled == {
        "cycle_id": "hk-v1-full-control-20260826",
        "cycle_kind": "FULL_PERIODIC",
        "scheduled_at": "2026-08-26T00:00:00Z",
        "observation_cutoff": "2026-08-26T00:00:00Z",
        "matrix_revision": load_hk_v1_coverage_matrix().revision,
        "matrix_fingerprint": load_hk_v1_coverage_matrix().fingerprint,
    }
    assert scheduled is not instruction


def test_due_control_orchestrator_calls_once_and_rebuilds_the_returned_result() -> None:
    """The deterministic boundary owns one activity call and returns no caller-owned result."""
    context = _OrchestrationContext()
    instruction = _instruction()
    workflow = v1_pipeline.run_hk_v1_due_cycle(cast("OrchestrationContext", context), instruction)
    task = next(workflow)
    body = json.loads(_result_body())

    with pytest.raises(StopIteration) as completed:
        workflow.send(body)
    result = cast("dict[str, object]", completed.value.value)
    body["cycle_id"] = "mutated-control-cycle"

    assert task is not None
    assert context.calls == [
        (
            "start_hk_v1_due_cycle",
            {
                "cycle_id": "hk-v1-full-control-20260826",
                "cycle_kind": "FULL_PERIODIC",
                "scheduled_at": "2026-08-26T00:00:00Z",
                "observation_cutoff": "2026-08-26T00:00:00Z",
                "matrix_revision": load_hk_v1_coverage_matrix().revision,
                "matrix_fingerprint": load_hk_v1_coverage_matrix().fingerprint,
            },
        )
    ]
    assert result["cycle_id"] == "hk-v1-full-control-20260826"


def test_successful_due_cycle_continues_into_exact_acceptance_activity() -> None:
    """Ordinary successful observation cannot terminate before the Legal decision boundary."""
    context = _OrchestrationContext()
    instruction = _instruction()
    workflow = v1_pipeline.run_hk_v1_due_cycle(cast("OrchestrationContext", context), instruction)
    next(workflow)
    continuation_task = workflow.send(_successful_result())

    with pytest.raises(StopIteration) as completed:
        workflow.send(_acceptance_result())

    assert continuation_task is not None
    assert [name for name, _payload in context.calls] == [
        "start_hk_v1_due_cycle",
        "continue_hk_v1_due_acceptance",
    ]
    continuation = cast("dict[str, object]", context.calls[1][1])
    assert continuation["instruction"] == instruction
    assert continuation["due_result"] == _successful_result()
    assert cast("dict[str, object]", completed.value.value)["acceptance"] == _acceptance_result()


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "subclass_leaf", "subclass_container", "nested_container"]
)
def test_due_control_rejects_untrusted_instruction_shapes_before_dispatch(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    """No malformed, extra, or subclass-owned instruction can reach the acquisition scheduler."""
    instruction: object = _instruction()
    if mutation == "missing":
        cast("dict[str, object]", instruction).pop("cycle_id")
    elif mutation == "extra":
        cast("dict[str, object]", instruction)["unexpected"] = "value"
    elif mutation == "subclass_leaf":
        cast("dict[str, object]", instruction)["cycle_id"] = _RouteLiar("not-a-cycle")
    elif mutation == "subclass_container":
        instruction = _ExplodingDict(cast("dict[str, object]", instruction))
    else:
        cast("dict[str, object]", instruction)["cycle_id"] = _ExplodingList()
    client = _RecordingClient(_instruction()["cycle_id"])
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_INSTRUCTION_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)

    assert client.schedule_calls == []


@pytest.mark.parametrize("mutation", ["missing", "extra", "subclass_leaf", "subclass_container"])
def test_due_control_orchestrator_strictly_rebuilds_all_returned_shapes(mutation: str) -> None:
    """The deterministic return path does not trust any activity-owned dict, leaf, or list."""
    body: object = json.loads(_result_body())
    if mutation == "missing":
        cast("dict[str, object]", body).pop("release_blocking")
    elif mutation == "extra":
        cast("dict[str, object]", body)["unexpected"] = "value"
    elif mutation == "subclass_leaf":
        cast("dict[str, object]", body)["cycle_id"] = _RouteLiar(_instruction()["cycle_id"])
    else:
        cast("dict[str, object]", body)["failed_source_ids"] = _ExplodingList()

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_RESULT_INVALID"):
        v1_pipeline._due_orchestrator_result(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            body,
            v1_pipeline._detached_due_instruction(_instruction()),  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        )


def test_due_control_slice_never_imports_worker_code_or_enables_a_timer() -> None:
    """The local seam remains control-only; it is absent from all host/timer entrypoints."""
    pipeline_source = Path(v1_pipeline.__file__).read_text(encoding="utf-8")
    service_source = (
        Path(v1_pipeline.__file__).with_name("v1_service.py").read_text(encoding="utf-8")
    )
    repository_root = Path(v1_pipeline.__file__).parents[4]
    host_sources = (
        repository_root / "infrastructure/poc/service_runtime_commands.json",
        repository_root / "tools/v1_poc_render_units.py",
    )

    for source in (pipeline_source, service_source):
        assert "asklegal_acquisition_worker" not in source
        assert "asklegal_source_connectors" not in source
        assert "create_timer" not in source
    for host_source in host_sources:
        assert "hk_v1_due" not in host_source.read_text(encoding="utf-8")


def test_installed_durable_activity_executor_reaches_the_closed_due_parser() -> None:
    """The installed SDK invokes the activity as `(ActivityContext, payload)`, not payload-only."""
    registry_attribute = "_Registry"
    executor_attribute = "_ActivityExecutor"
    registry_type = cast("type[_SdkRegistry]", getattr(durable_worker, registry_attribute))
    executor_type = cast("type[_SdkActivityExecutor]", getattr(durable_worker, executor_attribute))
    registry = registry_type()
    activities = ControlActivities(
        cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
    )
    registry.add_activity(activities.start_hk_v1_due_cycle)
    executor = executor_type(registry, logging.getLogger("control-due-sdk"), JsonDataConverter())

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_INSTRUCTION_INVALID"):
        executor.execute("control-due-sdk", "start_hk_v1_due_cycle", 1, "{}")


def test_due_control_rejects_false_complete_for_current_not_admitted_universe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A current Matrix result cannot omit every due source and still claim COMPLETE."""
    body = json.loads(_result_body())
    body["failed_source_ids"] = []
    body["release_blocking"] = False
    body["disposition"] = "COMPLETE"
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"], json.dumps(body))
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_RESULT_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)


def test_due_control_revalidates_an_issued_matrix_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-construction matrix mutation must prevent scheduling."""
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"])
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)
    matrix = load_hk_v1_coverage_matrix()
    activities = ControlActivities(cast("V1ControlInfrastructure", object()), matrix)
    object.__setattr__(matrix, "fingerprint", "sha256:" + "d" * 64)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_MATRIX_INVALID"):
        activities.start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)
    assert client.schedule_calls == []


def test_due_control_rejects_duplicate_scheduler_json_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bounded result boundary rejects duplicate keys before reconciliation."""
    instruction = _instruction()
    body = _result_body().replace(
        '"cycle_id": "hk-v1-full-control-20260826",',
        '"cycle_id": "hk-v1-full-control-20260826", "cycle_id": "other",',
    )
    client = _RecordingClient(instruction["cycle_id"], body)
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_RESULT_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("failed_source_ids", ["UNKNOWN-SOURCE"]),
        ("failed_source_ids", list(reversed(_due_source_ids()))),
        ("failed_source_ids", [_due_source_ids()[0], _due_source_ids()[0]]),
        ("accounting_complete", False),
        ("disposition", "COMPLETE"),
        ("release_blocking", False),
    ],
)
def test_due_control_rejects_hostile_category_or_derived_result_field(
    monkeypatch: pytest.MonkeyPatch, field: str, replacement: object
) -> None:
    """Closed accounting, category, disposition, and release claims cannot be repaired."""
    body = json.loads(_result_body())
    body[field] = replacement
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"], json.dumps(body))
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_RESULT_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)


@pytest.mark.parametrize(
    ("reference_field", "replacement"),
    [("vault", "RECOVERY"), ("logical_key", "wrong"), ("fingerprint", "sha256:" + "z" * 64)],
)
def test_due_control_rejects_wrong_manifest_reference(
    monkeypatch: pytest.MonkeyPatch, reference_field: str, replacement: object
) -> None:
    """Only the exact PRIMARY fixed-key immutable receipt is accepted."""
    body = json.loads(_result_body())
    body["manifest_reference"][reference_field] = replacement
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"], json.dumps(body))
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_RESULT_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)


@pytest.mark.parametrize(
    ("reference_field", "replacement"),
    [
        ("vault", "RECOVERY"),
        ("logical_key", "wrong"),
        ("fingerprint", "sha256:" + "z" * 64),
    ],
)
def test_due_control_rejects_wrong_family_acquisition_evidence_reference(
    monkeypatch: pytest.MonkeyPatch, reference_field: str, replacement: object
) -> None:
    """Control accepts only the root-bound Primary-vault family evidence receipt."""
    body = json.loads(_result_body())
    body["family_acquisition_evidence"]["evidence_reference"][reference_field] = replacement
    instruction = _instruction()
    client = _RecordingClient(instruction["cycle_id"], json.dumps(body))
    scheduler = _RecordingScheduler(client)
    _patch_acquisition_scheduler(monkeypatch, scheduler)

    with pytest.raises(v1_pipeline.ControlPipelineError, match="HK_V1_DUE_RESULT_INVALID"):
        ControlActivities(
            cast("V1ControlInfrastructure", object()), load_hk_v1_coverage_matrix()
        ).start_hk_v1_due_cycle(ActivityContext("control-due", 1), instruction)
