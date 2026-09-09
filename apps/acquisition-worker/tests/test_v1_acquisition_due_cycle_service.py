"""Service-facing registration proof for the Hong Kong V1 due cycle."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MethodType
from typing import Literal, Never, cast

import pytest
from asklegal_acquisition_worker import v1_service
from asklegal_acquisition_worker.hk_v1_due_cycle import (
    HongKongV1DueCycleActivities,
    HongKongV1DueCycleError,
    acquire_hk_v1_due_cycle,
    register_hk_v1_due_cycle_handlers,
)
from asklegal_acquisition_worker.hk_v1_due_predecessor import LocalDueCyclePredecessorStore
from asklegal_acquisition_worker.v1_infrastructure import (
    V1AcquisitionInfrastructure,
    load_v1_infrastructure,
)
from asklegal_application_runtime import ConfigurationError, ConfigurationErrorCode, ServiceExitCode
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import LocalImmutableVault, VaultName


class _RecordingWorker:
    """A narrow scheduler-boundary double retaining actual registered handlers."""

    def __init__(self) -> None:
        self.activities: list[Callable[..., object]] = []
        self.orchestrators: list[Callable[..., object]] = []

    def add_activity(self, fn: Callable[..., object]) -> str:
        self.activities.append(fn)
        return fn.__name__

    def add_orchestrator(self, fn: Callable[..., object]) -> str:
        self.orchestrators.append(fn)
        return fn.__name__


class _ExplodingEnvironment(dict[str, str]):
    """Hostile mapping whose configuration lookup fails before it yields a path."""

    def get(self, _key: object, _default: object = None) -> Never:
        message = "untrusted environment lookup"
        raise RuntimeError(message)


class _ServiceStore:
    """Lifecycle-observable local-state port used below the service boundary."""

    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1

    def load(self, _kind: object) -> None:
        return None

    def compare_and_set(self, _expected: object, _state: object) -> Never:
        message = "the service registration path must not publish cycle state"
        raise AssertionError(message)


class _ServiceWorker:
    """A worker double that exposes registration and lifecycle side effects together."""

    def __init__(self) -> None:
        self.activities: list[Callable[..., object]] = []
        self.orchestrators: list[Callable[..., object]] = []
        self.started = False
        self.stop_calls = 0

    def add_activity(self, fn: Callable[..., object]) -> str:
        self.activities.append(fn)
        return fn.__name__

    def add_orchestrator(self, fn: Callable[..., object]) -> str:
        self.orchestrators.append(fn)
        return fn.__name__

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stop_calls += 1


class _ServiceScheduler:
    """The scheduler factory surface used by the process host."""

    def __init__(self, worker: _ServiceWorker) -> None:
        self._worker = worker
        self.task_hub = "acquisition"

    def create_worker(self, *, concurrency_options: object) -> _ServiceWorker:
        del concurrency_options
        return self._worker


class _ExplodingTaskHubScheduler:
    """A scheduler whose post-start diagnostic projection is hostile."""

    def __init__(self, worker: _ServiceWorker) -> None:
        self._worker = worker

    @property
    def task_hub(self) -> Never:
        message = "untrusted post-start task-hub projection"
        raise RuntimeError(message)

    def create_worker(self, *, concurrency_options: object) -> _ServiceWorker:
        del concurrency_options
        return self._worker


class _LegacyActivities:
    """Unrelated live activities that remain registered beside the replacement cycle."""

    production_cases_configured = True
    production_legislation_configured = True

    def capture_endpoint(self) -> None: ...

    def capture_gazette_window(self) -> None: ...

    def capture_inventory(self) -> None: ...

    def plan_hkel_evidence(self) -> None: ...

    def capture_hkel_evidence(self) -> None: ...

    def capture_rendered_discovery(self) -> None: ...

    def run_resumable_acquisition(self) -> None: ...

    def run_legislation_acquisition(self) -> None: ...


class _ConfiguredLegislationInputs:
    """Concrete-shaped port used while exercising default Cases composition."""

    @staticmethod
    def load(_cycle_id: str, _observation_cutoff: str) -> Never:
        message = "registration must not execute a scheduled child"
        raise AssertionError(message)


class _NoEffectVault:
    """A vault whose operational methods explode if service registration touches storage."""

    vault_name = VaultName.PRIMARY

    def __getattr__(self, name: str) -> Never:
        message = f"unexpected vault effect: {name}"
        raise AssertionError(message)


class _PostStartExplodingVaultName:
    """A vault whose post-start diagnostic projection is hostile."""

    def __init__(self, worker: _ServiceWorker) -> None:
        self._worker = worker

    @property
    def vault_name(self) -> VaultName:
        if not self._worker.started:
            return VaultName.PRIMARY
        message = "untrusted post-start vault-name projection"
        raise RuntimeError(message)


@dataclass
class _TestInfrastructure:
    due_cycle_state_root: Path
    primary_vault: object
    scheduler: object
    source_egress_proxy_credential: object = None


def _infrastructure(
    *,
    due_cycle_state_root: Path,
    primary_vault: object = None,
    scheduler: object = None,
) -> _TestInfrastructure:
    """Build a typed test-only view of the service composition surface."""
    return _TestInfrastructure(due_cycle_state_root, primary_vault, scheduler)


def _as_production_infrastructure(value: _TestInfrastructure) -> V1AcquisitionInfrastructure:
    """Cross the test double boundary at one explicit, reviewed adapter point."""
    return cast("V1AcquisitionInfrastructure", value)


def _load_test_infrastructure(
    value: _TestInfrastructure,
) -> Callable[[Mapping[str, str]], V1AcquisitionInfrastructure]:
    production_value = _as_production_infrastructure(value)

    def load(_environment: Mapping[str, str]) -> V1AcquisitionInfrastructure:
        return production_value

    return load


def _store_factory(store: _ServiceStore) -> Callable[[Path], LocalDueCyclePredecessorStore]:
    def make(_root: Path) -> LocalDueCyclePredecessorStore:
        return cast("LocalDueCyclePredecessorStore", store)

    return make


def _readiness(_infrastructure: V1AcquisitionInfrastructure) -> object:
    return object()


def _legacy_activities(*_arguments: object) -> _LegacyActivities:
    return _LegacyActivities()


def _source_environment(root: Path) -> dict[str, str]:
    """Supply the explicit retained source root required by live composition tests."""
    root.mkdir(exist_ok=True)
    return {"ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT": str(root)}


def _configured_legislation_inputs(*_a: object, **_k: object) -> _ConfiguredLegislationInputs:
    return _ConfiguredLegislationInputs()


def _run_service_until_shutdown(
    _gate: object,
    serve: Callable[[asyncio.Event], Awaitable[None]],
    *,
    report_line: Callable[[str], None],
) -> Awaitable[ServiceExitCode]:
    """Run one host serve callable through its normal cooperative-shutdown branch."""
    del report_line

    async def run() -> ServiceExitCode:
        shutdown = asyncio.Event()
        shutdown.set()
        await serve(shutdown)
        return ServiceExitCode.OK

    return run()


def test_due_cycle_registrar_binds_the_exact_owned_handler_set_once(tmp_path: Path) -> None:
    """Replacing any handler, order, or owner makes V1 due cycles unschedulable or ambiguous."""
    store = LocalDueCyclePredecessorStore(tmp_path / "state")
    try:
        activities = HongKongV1DueCycleActivities(
            LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY), store
        )
        worker = _RecordingWorker()

        register_hk_v1_due_cycle_handlers(worker, activities)

        assert [handler.__name__ for handler in worker.activities] == [
            "plan_hk_v1_due_cycle",
            "capture_hk_v1_due_source",
            "record_hk_v1_due_source_failure",
            "record_hk_v1_family_acquisitions",
            "assemble_hk_v1_due_cycle",
        ]
        assert all(
            isinstance(handler, MethodType) and handler.__self__ is activities
            for handler in worker.activities
        )
        assert worker.orchestrators == [acquire_hk_v1_due_cycle]
        assert len({id(handler) for handler in worker.activities + worker.orchestrators}) == 6
    finally:
        store.close()


def test_due_cycle_registered_handlers_accept_the_real_sdk_dispatch_shape(tmp_path: Path) -> None:
    """The worker dispatches each registered activity with context plus payload."""
    store = LocalDueCyclePredecessorStore(tmp_path / "state")
    try:
        activities = HongKongV1DueCycleActivities(
            LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY), store
        )
        worker = _RecordingWorker()
        register_hk_v1_due_cycle_handlers(worker, activities)
        context = ActivityContext("hk-v1-due-dispatch", 1)

        for handler in worker.activities:
            with pytest.raises(HongKongV1DueCycleError):
                handler(context, {})
    finally:
        store.close()


def _write_credential(directory: Path, name: str, content: bytes) -> None:
    """Create one exact non-secret test credential file for composition only."""
    target = directory / name
    target.write_bytes(content)
    target.chmod(0o400)


def _infrastructure_environment(credential_root: Path) -> dict[str, str]:
    """Build the complete non-secret acquisition configuration fixture."""
    credential_root.mkdir()
    _write_credential(credential_root, "sql-acquisition", b"synthetic-password")
    vault_credential = b'{"access_key_id":"synthetic-access","secret_access_key":"synthetic"}'
    _write_credential(credential_root, "vault-primary-acquisition", vault_credential)
    _write_credential(credential_root, "vault-recovery-acquisition", vault_credential)
    _write_credential(credential_root, "source-egress-proxy", b"http://proxy.invalid:3128")
    return {"CREDENTIALS_DIRECTORY": str(credential_root)}


@pytest.mark.parametrize(
    "state_root",
    [
        None,
        "",
        "relative/state",
        " /var/asklegal-state",
        "/var/asklegal-state ",
        "/var/asklegal\x00state",
        "/var/./asklegal-state",
        "/var//asklegal-state",
        "/var\\asklegal-state",
        "/",
        "/var/asklegal-state/..",
    ],
)
def test_infrastructure_rejects_implicit_or_unsafe_due_cycle_state_roots(
    tmp_path: Path, state_root: str | None
) -> None:
    """An inferred, aliased, or non-canonical state authority could fork cycle continuity."""
    environment = _infrastructure_environment(tmp_path / "credentials")
    if state_root is not None:
        environment["ASKLEGAL_HK_V1_DUE_STATE_ROOT"] = state_root

    with pytest.raises(ConfigurationError, match="CONFIGURATION_INVALID"):
        load_v1_infrastructure(environment)


def test_infrastructure_normalizes_hostile_due_state_configuration_lookup() -> None:
    """A configuration adapter fault must not leak implementation detail from startup."""
    with pytest.raises(ConfigurationError, match="CONFIGURATION_INVALID"):
        load_v1_infrastructure(_ExplodingEnvironment())


def test_service_reports_not_ready_when_due_state_configuration_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad local continuity authority must not become a generic failed process start."""

    def invalid_configuration(_environment: object) -> Never:
        raise ConfigurationError(ConfigurationErrorCode.INVALID)

    monkeypatch.setattr(v1_service, "load_v1_infrastructure", invalid_configuration)
    monkeypatch.setattr(v1_service.os, "environ", {})

    assert v1_service.run() == ServiceExitCode.NOT_READY


def test_service_normalizes_an_ordinary_due_state_store_construction_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A local filesystem adapter error must not escape process startup or reach worker start."""
    infrastructure = _infrastructure(due_cycle_state_root=tmp_path / "due-state")

    def fail_store_construction(_root: Path) -> Never:
        message = "untrusted filesystem adapter error"
        raise RuntimeError(message)

    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", fail_store_construction)
    monkeypatch.setattr(
        v1_service.os,
        "environ",
        _source_environment(tmp_path / "source-admission"),
    )

    assert v1_service.run() == ServiceExitCode.NOT_READY


def test_service_composes_retained_source_admission_before_worker_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The continuous due-cycle owner receives the production source adapter."""
    store = _ServiceStore()
    worker = _ServiceWorker()
    infrastructure = _infrastructure(
        due_cycle_state_root=tmp_path / "due-state",
        primary_vault=LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY),
        scheduler=_ServiceScheduler(worker),
    )
    source_root = tmp_path / "source-admission"
    source_root.mkdir()

    class SourceAdapter:
        @staticmethod
        def capture(*, source_id: str, observation_cutoff: str) -> None:
            del source_id, observation_cutoff

    sentinel = SourceAdapter()
    observed_roots: list[Path] = []

    def retained_adapter(root: Path) -> object:
        observed_roots.append(root)
        return sentinel

    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", _store_factory(store))
    monkeypatch.setattr(v1_service, "build_activities", _legacy_activities)
    monkeypatch.setattr(v1_service, "known_v1_retained_source_adapter", retained_adapter)
    monkeypatch.setattr(v1_service, "readiness_gate", _readiness)
    monkeypatch.setattr(v1_service, "run_v1_service", _run_service_until_shutdown)

    result = asyncio.run(
        v1_service._run(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            {"ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT": str(source_root)}
        )
    )

    assert result is ServiceExitCode.OK
    assert observed_roots == [source_root]
    capture = next(
        item for item in worker.activities if item.__name__ == "capture_hk_v1_due_source"
    )
    bound_capture = cast("MethodType", capture)
    owner = cast("HongKongV1DueCycleActivities", bound_capture.__self__)
    assert owner._source_adapter is sentinel  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001


def test_missing_source_admission_root_stops_before_state_or_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A production-shaped family composition cannot silently use UNADMITTED fallback."""
    infrastructure = _infrastructure(due_cycle_state_root=tmp_path / "due-state")

    def unexpected_store(_root: Path) -> Never:
        message = "source admission must precede state and worker construction"
        raise AssertionError(message)

    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(v1_service, "build_activities", _legacy_activities)
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", unexpected_store)

    assert asyncio.run(v1_service._run({})) is ServiceExitCode.NOT_READY  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001


@pytest.mark.parametrize("stage", ["CONFIGURATION", "STORE", "READINESS"])
def test_hostile_lifecycle_logger_cannot_replace_a_not_ready_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: Literal["CONFIGURATION", "STORE", "READINESS"],
) -> None:
    """Pre-worker rejection stays closed even when its configured logger adapter faults."""
    store = _ServiceStore()
    infrastructure = _infrastructure(due_cycle_state_root=tmp_path / "due-state")

    def invalid_configuration(_environment: object) -> Never:
        raise ConfigurationError(ConfigurationErrorCode.INVALID)

    def fail_store_construction(_root: Path) -> Never:
        message = "untrusted filesystem adapter error"
        raise RuntimeError(message)

    def fail_critical(_message: object, *_arguments: object) -> Never:
        message = "untrusted critical logger failure"
        raise RuntimeError(message)

    def fail_info(_message: object, *_arguments: object) -> Never:
        message = "untrusted readiness logger failure"
        raise RuntimeError(message)

    async def rejected_host(
        _gate: object,
        _serve: Callable[[asyncio.Event], Awaitable[None]],
        *,
        report_line: Callable[[str], None],
    ) -> ServiceExitCode:
        report_line("ACQUISITION_WORKER NOT_READY")
        return ServiceExitCode.NOT_READY

    if stage == "CONFIGURATION":
        monkeypatch.setattr(v1_service, "load_v1_infrastructure", invalid_configuration)
        monkeypatch.setattr(v1_service._LOGGER, "critical", fail_critical)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - hostile pre-worker logger regression.
    else:
        monkeypatch.setattr(
            v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
        )
        monkeypatch.setattr(v1_service, "build_activities", _legacy_activities)
        if stage == "STORE":
            monkeypatch.setattr(
                v1_service, "LocalDueCyclePredecessorStore", fail_store_construction
            )
            monkeypatch.setattr(v1_service._LOGGER, "critical", fail_critical)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - hostile pre-worker logger regression.
        else:
            monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", _store_factory(store))
            monkeypatch.setattr(v1_service, "readiness_gate", _readiness)
            monkeypatch.setattr(v1_service, "run_v1_service", rejected_host)
            monkeypatch.setattr(v1_service._LOGGER, "info", fail_info)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - hostile shared-host report logger regression.

    environment = _source_environment(tmp_path / "source-admission")
    assert asyncio.run(v1_service._run(environment)) == ServiceExitCode.NOT_READY  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - test exercises closed pre-worker result handling.
    assert store.close_calls == (1 if stage == "READINESS" else 0)


def test_service_preserves_cancellation_when_due_state_store_close_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancellation remains the caller-visible result even if local state cleanup cannot finish."""
    store = _ServiceStore()
    infrastructure = _infrastructure(due_cycle_state_root=tmp_path / "due-state")

    def failing_close() -> None:
        store.close_calls += 1
        message = "untrusted close failure"
        raise RuntimeError(message)

    def failing_critical(_message: object, *_arguments: object) -> Never:
        message = "untrusted close critical logger failure"
        raise RuntimeError(message)

    async def cancelled_host(
        _gate: object,
        _serve: Callable[[asyncio.Event], Awaitable[None]],
        *,
        report_line: Callable[[str], None],
    ) -> Never:
        del report_line
        raise asyncio.CancelledError

    async def observe_cancellation() -> None:
        with pytest.raises(asyncio.CancelledError):
            await v1_service._run(_source_environment(tmp_path / "source-admission"))  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - test observes the cancellation contract.

    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", _store_factory(store))
    monkeypatch.setattr(v1_service, "build_activities", _legacy_activities)
    monkeypatch.setattr(store, "close", failing_close)
    monkeypatch.setattr(v1_service, "readiness_gate", _readiness)
    monkeypatch.setattr(v1_service, "run_v1_service", cancelled_host)
    monkeypatch.setattr(v1_service._LOGGER, "critical", failing_critical)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - compound hostile close logging regression.

    asyncio.run(observe_cancellation())
    assert store.close_calls == 1


@pytest.mark.parametrize(
    ("failure_stage", "expected_exit", "expected_started", "expected_stops"),
    [
        ("READINESS", ServiceExitCode.NOT_READY, False, 0),
        ("CREATE", ServiceExitCode.FAILED, False, 0),
        ("REGISTER", ServiceExitCode.FAILED, False, 0),
        ("LEGACY", ServiceExitCode.NOT_READY, False, 0),
        ("START", ServiceExitCode.FAILED, False, 0),
        ("STOP", ServiceExitCode.FAILED, True, 1),
    ],
)
def test_service_lifecycle_failures_close_state_once_and_stop_only_started_workers(  # noqa: C901, PLR0913, PLR0917 - one explicit lifecycle matrix.
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: Literal["READINESS", "CREATE", "REGISTER", "LEGACY", "START", "STOP"],
    expected_exit: ServiceExitCode,
    expected_started: bool,  # noqa: FBT001 - literal lifecycle expectation, not production API.
    expected_stops: int,
) -> None:
    """Every pre-start and post-start failure has one closed state-release outcome."""
    store = _ServiceStore()
    worker = _ServiceWorker()
    infrastructure = _infrastructure(
        due_cycle_state_root=tmp_path / "due-state",
        primary_vault=_NoEffectVault(),
        scheduler=_ServiceScheduler(worker),
    )

    async def host(
        _gate: object,
        serve: Callable[[asyncio.Event], Awaitable[None]],
        *,
        report_line: Callable[[str], None],
    ) -> ServiceExitCode:
        del report_line
        if failure_stage == "READINESS":
            return ServiceExitCode.NOT_READY
        shutdown = asyncio.Event()
        shutdown.set()
        try:
            await serve(shutdown)
        except Exception:  # noqa: BLE001 - host test doubles model every ordinary startup failure.
            return ServiceExitCode.FAILED
        return ServiceExitCode.OK

    if failure_stage == "CREATE":

        def fail_create(*, concurrency_options: object) -> Never:
            del concurrency_options
            message = "untrusted worker construction failure"
            raise RuntimeError(message)

        monkeypatch.setattr(infrastructure.scheduler, "create_worker", fail_create)
    if failure_stage == "REGISTER":

        def fail_registration(_worker: object, _activities: object) -> Never:
            message = "untrusted registration failure"
            raise RuntimeError(message)

        monkeypatch.setattr(v1_service, "register_hk_v1_due_cycle_handlers", fail_registration)
    if failure_stage == "LEGACY":

        def fail_legacy(*_arguments: object) -> Never:
            message = "untrusted legacy composition failure"
            raise RuntimeError(message)

        monkeypatch.setattr(v1_service, "build_activities", fail_legacy)
    else:
        monkeypatch.setattr(v1_service, "build_activities", _legacy_activities)
    if failure_stage == "START":

        def fail_start() -> Never:
            message = "untrusted worker start failure"
            raise RuntimeError(message)

        monkeypatch.setattr(worker, "start", fail_start)
    if failure_stage == "STOP":

        def fail_stop() -> None:
            worker.stop_calls += 1
            message = "untrusted worker stop failure"
            raise RuntimeError(message)

        monkeypatch.setattr(worker, "stop", fail_stop)

    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", _store_factory(store))
    monkeypatch.setattr(v1_service, "readiness_gate", _readiness)
    monkeypatch.setattr(v1_service, "run_v1_service", host)
    monkeypatch.setattr(
        v1_service.os,
        "environ",
        _source_environment(tmp_path / "source-admission"),
    )

    assert v1_service.run() == expected_exit
    assert store.close_calls == (0 if failure_stage == "LEGACY" else 1)
    assert worker.started is expected_started
    assert worker.stop_calls == expected_stops


@pytest.mark.parametrize(
    ("close_mode", "expected_exit"),
    [("CLEAN", ServiceExitCode.OK), ("FAIL", ServiceExitCode.FAILED)],
)
def test_service_registers_only_the_new_due_cycle_and_closes_its_store_on_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    close_mode: Literal["CLEAN", "FAIL"],
    expected_exit: ServiceExitCode,
) -> None:
    """A live worker must have one unambiguous due-cycle owner and close failures stay closed."""
    store = _ServiceStore()
    worker = _ServiceWorker()
    primary_vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    infrastructure = _infrastructure(
        due_cycle_state_root=tmp_path / "due-state",
        primary_vault=primary_vault,
        scheduler=_ServiceScheduler(worker),
    )
    registered_roots: list[Path] = []

    def make_store(root: Path) -> _ServiceStore:
        registered_roots.append(root)
        return store

    if close_mode == "FAIL":
        original_close = store.close

        def failing_close() -> None:
            original_close()
            message = "untrusted close failure"
            raise RuntimeError(message)

        monkeypatch.setattr(store, "close", failing_close)

    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(v1_service, "readiness_gate", _readiness)
    monkeypatch.setattr(v1_service, "build_activities", _legacy_activities)
    monkeypatch.setattr(v1_service, "run_v1_service", _run_service_until_shutdown)
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", make_store)
    monkeypatch.setattr(
        v1_service.os,
        "environ",
        _source_environment(tmp_path / "source-admission"),
    )
    assert v1_service.run() == expected_exit
    assert registered_roots == [tmp_path / "due-state"]
    assert store.close_calls == 1
    assert worker.started is True
    assert worker.stop_calls == 1
    activity_names = [handler.__name__ for handler in worker.activities]
    orchestrator_names = [handler.__name__ for handler in worker.orchestrators]
    assert activity_names.count("plan_hk_v1_due_cycle") == 1
    assert activity_names.count("capture_hk_v1_due_source") == 1
    assert activity_names.count("record_hk_v1_due_source_failure") == 1
    assert activity_names.count("assemble_hk_v1_due_cycle") == 1
    assert activity_names.count("run_resumable_acquisition") == 1
    assert orchestrator_names.count("acquire_hk_v1_due_cycle") == 1
    handler_names = activity_names + orchestrator_names
    assert "plan_source_cycle" not in handler_names
    assert "capture_due_source" not in handler_names
    assert "assemble_source_cycle" not in handler_names
    assert "acquire_source_cycle" not in handler_names


def test_default_cases_configuration_reaches_worker_creation_without_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit retained Cases inputs replace the former permanent None composition."""
    store = _ServiceStore()
    worker = _ServiceWorker()
    primary_vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)

    class Credential:
        @staticmethod
        def reveal() -> bytes:
            return b"http://proxy.invalid:3128"

    infrastructure = _infrastructure(
        due_cycle_state_root=tmp_path / "due-state",
        primary_vault=primary_vault,
        scheduler=_ServiceScheduler(worker),
    )
    infrastructure.source_egress_proxy_credential = Credential()
    source_root = Path(__file__).resolve().parents[3] / "var/hk-v1/source-admission"
    retained_report = (
        source_root / "judiciary-attempt-p/attempts/judiciary-live-baseline-20260831w/report.json"
    )
    if not retained_report.is_file():
        pytest.skip("explicit retained Judiciary Task 7 report is absent in this checkout")
    form = tmp_path / "current-advanced-search-form.html"
    form.write_bytes(b"<html><form id='advanced-search'></form></html>")
    form_fingerprint = tmp_path / "current-advanced-search-form.sha256"
    form_fingerprint.write_text(f"sha256:{sha256(form.read_bytes()).hexdigest()}\n")
    environment = {
        "ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT": str(source_root),
        "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM": str(form),
        "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM_FINGERPRINT": str(form_fingerprint),
    }

    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", _store_factory(store))
    monkeypatch.setattr(v1_service, "readiness_gate", _readiness)
    monkeypatch.setattr(v1_service, "run_v1_service", _run_service_until_shutdown)
    monkeypatch.setattr(
        "asklegal_acquisition_worker.v1_pipeline.LocalLegislationProductionInputs",
        _configured_legislation_inputs,
    )

    result = asyncio.run(v1_service._run(environment))  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

    assert result is ServiceExitCode.OK
    assert worker.started is True
    assert worker.stop_calls == 1
    assert store.close_calls == 1
    assert "run_resumable_acquisition" in [activity.__name__ for activity in worker.activities]


@pytest.mark.parametrize("failure", ["MISSING", "DRIFT"])
def test_default_cases_configuration_fails_before_state_worker_or_vault_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Literal["MISSING", "DRIFT"]
) -> None:
    """Missing or digest-drifted form authority is pre-worker NOT_READY and effect free."""
    worker = _ServiceWorker()
    primary_vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)

    class Credential:
        @staticmethod
        def reveal() -> bytes:
            return b"http://proxy.invalid:3128"

    infrastructure = _infrastructure(
        due_cycle_state_root=tmp_path / "due-state",
        primary_vault=primary_vault,
        scheduler=_ServiceScheduler(worker),
    )
    infrastructure.source_egress_proxy_credential = Credential()
    source_root = Path(__file__).resolve().parents[3] / "var/hk-v1/source-admission"
    form = tmp_path / "current-form.html"
    fingerprint = tmp_path / "current-form.sha256"
    if failure == "DRIFT":
        form.write_bytes(b"retained form")
        fingerprint.write_text("sha256:" + "0" * 64 + "\n")
    environment = {
        "ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT": str(source_root),
        "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM": str(form),
        "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM_FINGERPRINT": str(fingerprint),
    }
    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(
        "asklegal_acquisition_worker.v1_pipeline.LocalLegislationProductionInputs",
        _configured_legislation_inputs,
    )

    result = asyncio.run(v1_service._run(environment))  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

    assert result is ServiceExitCode.NOT_READY
    assert worker.started is False
    assert worker.stop_calls == 0
    assert not (tmp_path / "due-state").exists()
    assert list((tmp_path / "vault" / "objects").rglob("*")) == []


@pytest.mark.parametrize("projection", ["TASK_HUB", "VAULT_NAME"])
def test_post_start_diagnostic_projection_failure_stops_worker_and_closes_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    projection: Literal["TASK_HUB", "VAULT_NAME"],
) -> None:
    """Post-start diagnostics are inside stop ownership and never leak raw adapter detail."""
    store = _ServiceStore()
    worker = _ServiceWorker()
    scheduler: object = _ServiceScheduler(worker)
    primary_vault: object = _NoEffectVault()
    if projection == "TASK_HUB":
        scheduler = _ExplodingTaskHubScheduler(worker)
        raw_detail = "untrusted post-start task-hub projection"
    else:
        primary_vault = _PostStartExplodingVaultName(worker)
        raw_detail = "untrusted post-start vault-name projection"
    infrastructure = _infrastructure(
        due_cycle_state_root=tmp_path / "due-state",
        primary_vault=primary_vault,
        scheduler=scheduler,
    )

    async def host(
        _gate: object,
        serve: Callable[[asyncio.Event], Awaitable[None]],
        *,
        report_line: Callable[[str], None],
    ) -> ServiceExitCode:
        del report_line
        shutdown = asyncio.Event()
        shutdown.set()
        try:
            await serve(shutdown)
        except Exception:  # noqa: BLE001 - the process host normalizes one arbitrary post-start fault.
            return ServiceExitCode.FAILED
        return ServiceExitCode.OK

    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", _store_factory(store))
    monkeypatch.setattr(v1_service, "readiness_gate", _readiness)
    monkeypatch.setattr(v1_service, "build_activities", _legacy_activities)
    monkeypatch.setattr(v1_service, "run_v1_service", host)

    with caplog.at_level("INFO", logger="asklegal_acquisition_worker.v1_service"):
        result = asyncio.run(
            v1_service._run(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                _source_environment(tmp_path / "source-admission")
            )
        )

    assert result == ServiceExitCode.FAILED
    assert worker.started is True
    assert worker.stop_calls == 1
    assert store.close_calls == 1
    assert raw_detail not in caplog.text


def test_post_start_lifecycle_logger_fault_does_not_block_worker_or_store_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hostile logging adapter is non-authoritative once the worker has started."""
    store = _ServiceStore()
    worker = _ServiceWorker()
    infrastructure = _infrastructure(
        due_cycle_state_root=tmp_path / "due-state",
        primary_vault=_NoEffectVault(),
        scheduler=_ServiceScheduler(worker),
    )

    def fail_info(_message: object, *_arguments: object) -> Never:
        message = "untrusted lifecycle logger fault"
        raise RuntimeError(message)

    monkeypatch.setattr(
        v1_service, "load_v1_infrastructure", _load_test_infrastructure(infrastructure)
    )
    monkeypatch.setattr(v1_service, "LocalDueCyclePredecessorStore", _store_factory(store))
    monkeypatch.setattr(v1_service, "readiness_gate", _readiness)
    monkeypatch.setattr(v1_service, "build_activities", _legacy_activities)
    monkeypatch.setattr(v1_service, "run_v1_service", _run_service_until_shutdown)
    monkeypatch.setattr(v1_service._LOGGER, "info", fail_info)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - hostile logger boundary regression.

    environment = _source_environment(tmp_path / "source-admission")
    assert asyncio.run(v1_service._run(environment)) == ServiceExitCode.OK  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - test exercises the process cleanup boundary.
    assert worker.started is True
    assert worker.stop_calls == 1
    assert store.close_calls == 1


def test_serve_preserves_cancellation_when_started_worker_stop_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stop fault must not relabel a caller cancellation as an ordinary service failure."""
    store = _ServiceStore()
    worker = _ServiceWorker()
    infrastructure = _infrastructure(
        due_cycle_state_root=Path.cwd() / "var" / "asklegal-test-due-state",
        primary_vault=_NoEffectVault(),
        scheduler=_ServiceScheduler(worker),
    )

    def failing_stop() -> None:
        worker.stop_calls += 1
        message = "untrusted worker stop failure"
        raise RuntimeError(message)

    def failing_critical(_message: object, *_arguments: object) -> Never:
        message = "untrusted stop critical logger failure"
        raise RuntimeError(message)

    async def cancel_started_serve() -> None:
        serve = v1_service._build_serve(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - direct cancellation boundary.
            _as_production_infrastructure(infrastructure),
            {},
            cast("LocalDueCyclePredecessorStore", store),
        )

        async def invoke() -> None:
            await serve(asyncio.Event())

        task = asyncio.create_task(invoke())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    monkeypatch.setattr(v1_service, "build_activities", _legacy_activities)
    monkeypatch.setattr(worker, "stop", failing_stop)
    monkeypatch.setattr(v1_service._LOGGER, "critical", failing_critical)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 - compound hostile stop logging regression.

    asyncio.run(cancel_started_serve())
    assert worker.started is True
    assert worker.stop_calls == 1


def test_infrastructure_derives_one_fixed_acquisition_journal_root(tmp_path: Path) -> None:
    """A second configuration coordinate could fork journal authority from due-cycle state."""
    environment = _infrastructure_environment(tmp_path / "credentials")
    environment["ASKLEGAL_HK_V1_DUE_STATE_ROOT"] = str(tmp_path / "cycle-state")

    infrastructure = load_v1_infrastructure(environment)

    assert infrastructure.acquisition_journal_root == (
        tmp_path / "cycle-state" / "acquisition-journals"
    )
