"""CONTROL_PLANE due-cycle worker composition and cleanup proof."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from hashlib import sha256
from pathlib import Path
from types import FunctionType, MethodType, SimpleNamespace
from typing import cast

import asklegal_reporting.hk_v1_coverage as coverage
import pytest
from asklegal_application_runtime import ServiceExitCode
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_control_plane import v1_service
from asklegal_control_plane.v1_acceptance import AcceptanceCoordinatorError
from asklegal_control_plane.v1_infrastructure import V1ControlInfrastructure
from asklegal_reporting import HongKongV1CoverageMatrix, load_hk_v1_coverage_matrix

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
    path = tmp_path / "service-count-preserving-npc-swap.json"
    path.write_bytes(canonicalize(document))
    return load_hk_v1_coverage_matrix(path)


class _Worker:
    def __init__(
        self,
        *,
        start_error: BaseException | None = None,
        stop_error: Exception | None = None,
    ) -> None:
        self.start_error = start_error
        self.stop_error = stop_error
        self.activities: list[object] = []
        self.orchestrators: list[object] = []
        self.start_calls = 0
        self.stop_calls = 0

    def add_activity(self, activity: object) -> str:
        self.activities.append(activity)
        return "activity"

    def add_orchestrator(self, orchestrator: object) -> str:
        self.orchestrators.append(orchestrator)
        return "orchestrator"

    def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error

    def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error


class _Scheduler:
    task_hub = "control"

    def __init__(self, worker: _Worker) -> None:
        self.worker = worker

    def create_worker(self, *, concurrency_options: object) -> _Worker:
        del concurrency_options
        return self.worker


class _Server:
    def __init__(self, _config: object) -> None:
        self._should_exit = False
        self._exit = asyncio.Event()

    @property
    def should_exit(self) -> bool:
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        self._should_exit = value
        if value:
            self._exit.set()

    async def serve(self) -> None:
        await self._exit.wait()


class _OldMatrix:
    revision = "HK-V1-001"


def _infrastructure() -> V1ControlInfrastructure:
    return cast("V1ControlInfrastructure", SimpleNamespace(primary_vault=object()))


def _patch_control_service(monkeypatch: pytest.MonkeyPatch, worker: _Worker) -> None:
    scheduler = _Scheduler(worker)

    def factory(application: str) -> _Scheduler:
        assert application == "CONTROL_PLANE"
        return scheduler

    monkeypatch.setattr(v1_service.V1SchedulerSettings, "for_application", factory)
    monkeypatch.setattr(v1_service, "load_hk_v1_coverage_matrix", load_hk_v1_coverage_matrix)
    monkeypatch.setattr(v1_service.uvicorn, "Server", _Server)
    monkeypatch.setenv(
        "ASKLEGAL_HK_V1_ACCEPTANCE_CUTOFF_ROOT",
        str(Path.cwd()),
    )


def _handler_name(value: object) -> str:
    if isinstance(value, FunctionType):
        return value.__name__
    if isinstance(value, MethodType):
        return value.__name__
    message = "handler shape"
    raise AssertionError(message)


def test_due_cycle_service_registers_exact_handlers_then_stops_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control worker owns the three activity/two orchestrator sequence exactly once."""
    worker = _Worker()
    _patch_control_service(monkeypatch, worker)
    shutdown = asyncio.Event()
    shutdown.set()

    asyncio.run(
        v1_service._serve_with(_infrastructure(), shutdown)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    )

    assert [_handler_name(activity) for activity in worker.activities] == [
        "start_acquisition",
        "start_analysis",
        "start_hk_v1_due_cycle",
        "perform_hk_v1_audit_archive",
        "perform_hk_v1_recovery_verification",
        "perform_hk_v1_telemetry_retention",
        "start_hk_v1_acceptance_acquisition",
        "start_hk_v1_acceptance_legal_processing",
        "continue_hk_v1_due_acceptance",
    ]
    assert [_handler_name(orchestrator) for orchestrator in worker.orchestrators] == [
        "observe_source_endpoint",
        "run_hk_v1_due_cycle",
        "run_hk_v1_audit_archive",
        "run_hk_v1_recovery_verification",
        "run_hk_v1_telemetry_retention",
        "run_hk_v1_acceptance_cycle",
    ]
    assert worker.start_calls == 1
    assert worker.stop_calls == 1


def test_acceptance_cutoff_root_is_required_before_worker_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service cannot silently infer where frozen acceptance inputs reside."""
    worker = _Worker()
    _patch_control_service(monkeypatch, worker)
    monkeypatch.delenv("ASKLEGAL_HK_V1_ACCEPTANCE_CUTOFF_ROOT")

    with pytest.raises(
        AcceptanceCoordinatorError,
        match="HK_V1_ACCEPTANCE_CONFIGURATION_INVALID",
    ):
        asyncio.run(
            v1_service._serve_with(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                _infrastructure(),
                asyncio.Event(),
            )
        )

    assert worker.start_calls == 0


def test_missing_acceptance_configuration_returns_not_ready_before_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A missing setting or directory closes before readiness or worker composition."""
    probes = 0

    def load_infrastructure(_environment: object) -> object:
        return object()

    def probe(_infrastructure: object) -> object:
        nonlocal probes
        probes += 1
        return object()

    monkeypatch.setattr(v1_service, "load_v1_infrastructure", load_infrastructure)
    monkeypatch.setattr(v1_service, "readiness_gate", probe)

    environments: tuple[dict[str, str], ...] = (
        {},
        {"ASKLEGAL_HK_V1_ACCEPTANCE_CUTOFF_ROOT": str(tmp_path / "absent-acceptance-cutoff-root")},
    )
    results = [
        asyncio.run(v1_service._run(environment))  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        for environment in environments
    ]

    assert results == [ServiceExitCode.NOT_READY, ServiceExitCode.NOT_READY]
    assert probes == 0


def test_due_cycle_service_rejects_superseded_matrix_revision_before_worker_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only HK-V1-002 may enter the control service composition boundary."""
    worker = _Worker()
    _patch_control_service(monkeypatch, worker)

    def policy_approved(_matrix: object) -> bool:
        return False

    def activities(_infrastructure: object, _matrix: object) -> SimpleNamespace:
        return SimpleNamespace(
            start_acquisition=object(),
            start_analysis=object(),
            start_hk_v1_due_cycle=object(),
        )

    monkeypatch.setattr(v1_service, "load_hk_v1_coverage_matrix", _OldMatrix)
    monkeypatch.setattr(v1_service, "is_hk_v1_coverage_matrix_policy_approved", policy_approved)
    monkeypatch.setattr(v1_service, "ControlActivities", activities)
    shutdown = asyncio.Event()
    shutdown.set()

    with pytest.raises(RuntimeError, match="HK_V1_DUE_MATRIX_INVALID"):
        asyncio.run(
            v1_service._serve_with(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                _infrastructure(), shutdown
            )
        )
    assert worker.start_calls == 0


def test_due_cycle_service_rejects_resealed_npc_policy_before_worker_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A self-consistent HK-V1-002 fingerprint cannot replace the approved policy."""
    worker = _Worker()
    _patch_control_service(monkeypatch, worker)
    matrix = _count_preserving_npc_swap_matrix(tmp_path)

    def load_swapped_matrix() -> HongKongV1CoverageMatrix:
        return matrix

    monkeypatch.setattr(v1_service, "load_hk_v1_coverage_matrix", load_swapped_matrix)
    shutdown = asyncio.Event()
    shutdown.set()

    with pytest.raises(RuntimeError, match="HK_V1_DUE_MATRIX_INVALID"):
        asyncio.run(
            v1_service._serve_with(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                _infrastructure(), shutdown
            )
        )

    assert worker.start_calls == 0


def test_due_cycle_service_does_not_stop_after_start_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a successfully started control worker enters cleanup ownership."""
    worker = _Worker(start_error=RuntimeError("start failed"))
    _patch_control_service(monkeypatch, worker)

    with pytest.raises(RuntimeError, match="start failed"):
        asyncio.run(
            v1_service._serve_with(_infrastructure(), asyncio.Event())  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        )
    assert worker.start_calls == 1
    assert worker.stop_calls == 0


def test_due_cycle_service_stops_after_post_start_task_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every post-start creation fault still reaches the one stop owner."""
    worker = _Worker()
    _patch_control_service(monkeypatch, worker)

    def fail_create_task(coroutine: Coroutine[object, object, object]) -> object:
        coroutine.close()
        message = "create task failed"
        raise RuntimeError(message)

    monkeypatch.setattr(v1_service.asyncio, "create_task", fail_create_task)
    with pytest.raises(RuntimeError, match="create task failed"):
        asyncio.run(
            v1_service._serve_with(_infrastructure(), asyncio.Event())  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        )
    assert worker.start_calls == 1
    assert worker.stop_calls == 1


def test_due_cycle_service_reports_stop_failure_after_server_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-cancel shutdown keeps the worker-stop failure visible after cleanup."""
    worker = _Worker(stop_error=RuntimeError("stop failed"))
    _patch_control_service(monkeypatch, worker)
    shutdown = asyncio.Event()
    shutdown.set()

    with pytest.raises(RuntimeError, match="stop failed"):
        asyncio.run(
            v1_service._serve_with(_infrastructure(), shutdown)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        )
    assert worker.stop_calls == 1


def test_due_cycle_service_preserves_cancellation_when_stop_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation remains authoritative even if the post-start worker stop fails."""
    worker = _Worker(stop_error=RuntimeError("stop failed"))
    _patch_control_service(monkeypatch, worker)

    async def cancel_running_service() -> None:
        task = asyncio.create_task(
            v1_service._serve_with(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                _infrastructure(), asyncio.Event()
            )
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_running_service())
    assert worker.stop_calls == 1
