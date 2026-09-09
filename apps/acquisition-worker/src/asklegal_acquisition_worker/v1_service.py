"""Exact V1 ACQUISITION_WORKER service process.

This is the continuous V1 entrypoint, not the local `--check` boundary. It loads
its own systemd credentials, composes only its own adapters, proves every declared
dependency once, and then runs its no-ingress worker loop until systemd sends
`SIGTERM`.

The loop is deliberately conservative. It claims at most one unit of work per
iteration, stops accepting new work the moment shutdown is requested, and lets the
in-flight claim finish under its existing fence rather than abandoning it. No
external effect is performed here: the worker's effect ports remain the disabled
local adapters until their own admission gates pass.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from asklegal_application_runtime import (
    ConfigurationError,
    CredentialError,
    ServiceExitCode,
    run_v1_service,
)
from asklegal_durable_task import ConcurrencyOptions

from asklegal_acquisition_worker.hk_v1_due_cycle import (
    HongKongV1DueCycleActivities,
    register_hk_v1_due_cycle_handlers,
)
from asklegal_acquisition_worker.hk_v1_due_predecessor import LocalDueCyclePredecessorStore
from asklegal_acquisition_worker.source_admission_adapter import (
    RetainedSourceAdmissionAdapter,
    known_v1_retained_source_adapter,
)
from asklegal_acquisition_worker.v1_infrastructure import load_v1_infrastructure, readiness_gate
from asklegal_acquisition_worker.v1_pipeline import (
    AcquisitionActivities,
    acquire_endpoint,
    acquire_endpoints,
    acquire_gazette_window,
    acquire_hkel_evidence,
    acquire_inventory,
    acquire_rendered_discovery,
    acquire_resumable_source_cycle,
    build_activities,
)

if TYPE_CHECKING:
    from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure

_IDLE_POLL_SECONDS = 1.0
_LOGGER = logging.getLogger("asklegal_acquisition_worker.v1_service")


def _lifecycle_info(message: str, *arguments: object) -> None:
    """Emit best-effort lifecycle diagnostics without turning logging into a cleanup dependency."""
    try:
        _LOGGER.info(message, *arguments)
    except Exception:  # noqa: BLE001 - a logging adapter cannot prevent worker cleanup.
        return


def _lifecycle_critical(message: str, *arguments: object) -> None:
    """Emit a best-effort critical lifecycle diagnostic without changing exit semantics."""
    try:
        _LOGGER.critical(message, *arguments)
    except Exception:  # noqa: BLE001 - a logging adapter cannot replace a closed lifecycle result.
        return


def _close_due_cycle_predecessor_store(store: LocalDueCyclePredecessorStore) -> bool:
    """Release the service-owned pinned state root without leaking filesystem detail."""
    try:
        store.close()
    except Exception:  # noqa: BLE001 - state-store release is one closed local lifecycle boundary.
        _lifecycle_critical("due-cycle state close failed: DUE_PREDECESSOR_NOT_READY")
        return False
    return True


def _build_serve(
    infrastructure: V1AcquisitionInfrastructure,
    environment: Mapping[str, str],
    predecessor_store: LocalDueCyclePredecessorStore,
    production_activities: AcquisitionActivities | None = None,
    source_adapter: RetainedSourceAdmissionAdapter | None = None,
) -> Callable[[asyncio.Event], Awaitable[None]]:
    """Bind one serve callable to this process's own infrastructure."""

    async def _serve(shutdown: asyncio.Event) -> None:
        """Serve the real task hub until systemd asks the process to stop."""
        due_activities = HongKongV1DueCycleActivities(
            infrastructure.primary_vault,
            predecessor_store,
            source_adapter=source_adapter,
        )
        worker = infrastructure.scheduler.create_worker(concurrency_options=ConcurrencyOptions())
        register_hk_v1_due_cycle_handlers(worker, due_activities)
        activities = production_activities or build_activities(infrastructure, environment)
        worker.add_activity(activities.capture_endpoint)
        worker.add_activity(activities.capture_gazette_window)
        worker.add_activity(activities.capture_inventory)
        worker.add_activity(activities.plan_hkel_evidence)
        worker.add_activity(activities.capture_hkel_evidence)
        worker.add_activity(activities.capture_rendered_discovery)
        worker.add_activity(activities.run_resumable_acquisition)
        legislation_activity = getattr(activities, "run_legislation_acquisition", None)
        if callable(legislation_activity):
            worker.add_activity(legislation_activity)
        worker.add_orchestrator(acquire_endpoint)
        worker.add_orchestrator(acquire_endpoints)
        worker.add_orchestrator(acquire_gazette_window)
        worker.add_orchestrator(acquire_inventory)
        worker.add_orchestrator(acquire_hkel_evidence)
        worker.add_orchestrator(acquire_rendered_discovery)
        # Tasks 5 and 6 bind their family-specific transport/work-graph activity to this
        # one shared orchestrator name; Task 3 deliberately does not migrate either adapter.
        worker.add_orchestrator(acquire_resumable_source_cycle)
        worker.start()
        cancelled = False
        try:
            _lifecycle_info(
                "ACQUISITION_WORKER serving hub=%s vault=%s",
                infrastructure.scheduler.task_hub,
                infrastructure.primary_vault.vault_name.value,
            )
            await shutdown.wait()
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            # The shutdown event prevents new work and the worker has no in-flight service
            # coroutine here, so synchronous stop avoids the pinned local runtime's broken
            # default-executor teardown path.
            try:
                worker.stop()
            except Exception:
                _lifecycle_critical("ACQUISITION_WORKER stop failed")
                if not cancelled:
                    raise
            _lifecycle_info("ACQUISITION_WORKER stopped serving")

    return _serve


async def _run(  # noqa: C901, PLR0911 - one closed startup and cleanup boundary.
    environment: Mapping[str, str],
) -> ServiceExitCode:
    try:
        infrastructure = load_v1_infrastructure(environment)
    except (ConfigurationError, CredentialError) as error:
        _lifecycle_critical("service configuration unavailable: %s", error.code.value)
        return ServiceExitCode.NOT_READY
    try:
        production_activities = build_activities(infrastructure, environment)
        if (
            production_activities.production_cases_configured is not True
            or production_activities.production_legislation_configured is not True
        ):
            production_activities = None
    except Exception:  # noqa: BLE001 - every worker-local family port is a startup authority.
        production_activities = None
    if production_activities is None:
        _lifecycle_critical("scheduled family inputs unavailable: FAMILY_INPUTS_NOT_READY")
        return ServiceExitCode.NOT_READY
    source_root_value = environment.get("ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT")
    if type(source_root_value) is not str or not source_root_value:
        _lifecycle_critical("source admission unavailable: SOURCE_ADMISSION_NOT_READY")
        return ServiceExitCode.NOT_READY
    try:
        source_adapter = known_v1_retained_source_adapter(Path(source_root_value))
    except OSError, ValueError:
        _lifecycle_critical("source admission unavailable: SOURCE_ADMISSION_NOT_READY")
        return ServiceExitCode.NOT_READY
    try:
        predecessor_store = LocalDueCyclePredecessorStore(infrastructure.due_cycle_state_root)
    except Exception:  # noqa: BLE001 - state-store construction is one closed local readiness boundary.
        _lifecycle_critical("due-cycle state unavailable: DUE_PREDECESSOR_NOT_READY")
        return ServiceExitCode.NOT_READY
    try:
        result = await run_v1_service(
            readiness_gate(infrastructure),
            _build_serve(
                infrastructure,
                environment,
                predecessor_store,
                production_activities,
                source_adapter,
            ),
            report_line=_lifecycle_info,
        )
    except asyncio.CancelledError:
        _close_due_cycle_predecessor_store(predecessor_store)
        raise
    except Exception:  # noqa: BLE001 - service-host failure cannot bypass local state release.
        _close_due_cycle_predecessor_store(predecessor_store)
        return ServiceExitCode.FAILED
    if not _close_due_cycle_predecessor_store(predecessor_store):
        return ServiceExitCode.FAILED
    return result


def run() -> int:
    """Run the exact V1 service and return one closed process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return int(asyncio.run(_run(os.environ)))


if __name__ == "__main__":
    sys.exit(run())
