"""Exact V1 CONTROL_PLANE service process.

This is the continuous V1 entrypoint, not the local `--check` boundary. It loads
its own systemd credentials, composes only its own adapters, proves every declared
dependency once, and then serves on its exact private listener until systemd sends
`SIGTERM`. It performs no external effect of its own.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Mapping
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING

import uvicorn
from asklegal_application_runtime import CredentialError, ServiceExitCode, run_v1_service
from asklegal_durable_task import ConcurrencyOptions, V1SchedulerSettings
from asklegal_reporting import (
    is_hk_v1_coverage_matrix_policy_approved,
    load_hk_v1_coverage_matrix,
)

from asklegal_control_plane.api import create_app, local_dependencies
from asklegal_control_plane.v1_acceptance import (
    AcceptanceConfiguration,
    AcceptanceCoordinatorError,
    LocalAcceptanceActivities,
    run_hk_v1_acceptance_cycle,
)
from asklegal_control_plane.v1_infrastructure import load_v1_infrastructure, readiness_gate
from asklegal_control_plane.v1_maintenance import (
    LocalMaintenanceActivities,
    MaintenanceConfiguration,
)
from asklegal_control_plane.v1_pipeline import (
    ControlActivities,
    observe_source_endpoint,
    run_hk_v1_due_cycle,
)
from asklegal_control_plane.v1_schedule import (
    LiveScheduleError,
    run_hk_v1_audit_archive,
    run_hk_v1_recovery_verification,
    run_hk_v1_telemetry_retention,
)

if TYPE_CHECKING:
    from asklegal_control_plane.v1_infrastructure import V1ControlInfrastructure

_LISTEN_ADDRESS = "0.0.0.0"  # noqa: S104 - container-only listener on a private network
_LISTEN_PORT = 8000
_SHUTDOWN_GRACE_SECONDS = 30
_LOGGER = logging.getLogger("asklegal_control_plane.v1_service")


async def _serve_with(
    infrastructure: V1ControlInfrastructure,
    shutdown: asyncio.Event,
    *,
    maintenance_configuration: MaintenanceConfiguration | None = None,
    acceptance_configuration: AcceptanceConfiguration | None = None,
) -> None:
    """Run the ASGI server until cooperative shutdown completes."""
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(local_dependencies()),
            host=_LISTEN_ADDRESS,
            port=_LISTEN_PORT,
            log_level="info",
            timeout_graceful_shutdown=_SHUTDOWN_GRACE_SECONDS,
            access_log=False,
        )
    )
    # The control plane both serves its API and sequences the other stages, so it
    # runs a scheduler worker beside the ASGI server on its own hub.
    scheduler = V1SchedulerSettings.for_application("CONTROL_PLANE")
    due_matrix = load_hk_v1_coverage_matrix()
    if not is_hk_v1_coverage_matrix_policy_approved(due_matrix):
        code = "HK_V1_DUE_MATRIX_INVALID"
        raise RuntimeError(code)
    worker = scheduler.create_worker(concurrency_options=ConcurrencyOptions())
    activities = ControlActivities(infrastructure, due_matrix)
    maintenance_configuration = (
        maintenance_configuration or MaintenanceConfiguration.from_environment(os.environ)
    )
    acceptance_configuration = acceptance_configuration or AcceptanceConfiguration.from_environment(
        os.environ
    )
    maintenance = LocalMaintenanceActivities(maintenance_configuration, due_matrix)
    acceptance = LocalAcceptanceActivities(
        acceptance_configuration, due_matrix, infrastructure.primary_vault
    )
    for activity in (
        activities.start_acquisition,
        activities.start_analysis,
        activities.start_hk_v1_due_cycle,
        maintenance.perform_hk_v1_audit_archive,
        maintenance.perform_hk_v1_recovery_verification,
        maintenance.perform_hk_v1_telemetry_retention,
        acceptance.start_hk_v1_acceptance_acquisition,
        acceptance.start_hk_v1_acceptance_legal_processing,
        acceptance.continue_hk_v1_due_acceptance,
    ):
        worker.add_activity(activity)
    for orchestrator in (
        observe_source_endpoint,
        run_hk_v1_due_cycle,
        run_hk_v1_audit_archive,
        run_hk_v1_recovery_verification,
        run_hk_v1_telemetry_retention,
        run_hk_v1_acceptance_cycle,
    ):
        worker.add_orchestrator(orchestrator)
    worker.start()
    serving: asyncio.Task[None] | None = None
    waiting: asyncio.Task[bool] | None = None
    try:
        _lifecycle_info("CONTROL_PLANE serving hub=%s", scheduler.task_hub)
        serving = asyncio.create_task(server.serve())
        waiting = asyncio.create_task(shutdown.wait())
        # Waiting only on `shutdown` hides a server that failed to start: the task holds
        # the exception, the event never fires, and the process stays up serving nothing.
        finished, _ = await asyncio.wait({serving, waiting}, return_when=asyncio.FIRST_COMPLETED)
        if serving in finished:
            await serving
            return
        _lifecycle_info("CONTROL_PLANE shutdown requested")
        server.should_exit = True
        await serving
    finally:
        # This pinned local runtime can hang while creating an asyncio.to_thread executor
        # during shutdown; no concurrent service work remains here, so stop synchronously.
        server.should_exit = True
        cancelled = isinstance(sys.exception(), asyncio.CancelledError)
        stop_error: Exception | None = None
        try:
            worker.stop()
        except Exception as error:  # noqa: BLE001 - worker adapters are a hostile lifecycle boundary.
            stop_error = error
            _lifecycle_critical("CONTROL_PLANE worker stop failed")
        if waiting is not None and not waiting.done():
            waiting.cancel()
        if waiting is not None:
            with suppress(asyncio.CancelledError, Exception):
                await waiting
        if serving is not None and not serving.done():
            with suppress(asyncio.CancelledError, Exception):
                await serving
        if stop_error is not None and not cancelled:
            raise stop_error


def _lifecycle_info(message: str, *args: object) -> None:
    """Keep lifecycle logging non-authoritative for cleanup ownership."""
    try:
        _LOGGER.info(message, *args)
    except Exception:  # noqa: BLE001 - logging adapters are outside lifecycle authority.
        return


def _lifecycle_critical(message: str, *args: object) -> None:
    """Keep failed-lifecycle reporting from replacing the real shutdown outcome."""
    try:
        _LOGGER.critical(message, *args)
    except Exception:  # noqa: BLE001 - logging adapters are outside lifecycle authority.
        return


async def _run(environment: Mapping[str, str]) -> ServiceExitCode:
    try:
        infrastructure = load_v1_infrastructure(environment)
        maintenance_configuration = MaintenanceConfiguration.from_environment(environment)
        acceptance_configuration = AcceptanceConfiguration.from_environment(environment)
    except (CredentialError, LiveScheduleError, AcceptanceCoordinatorError) as error:
        code = error.code.value if isinstance(error, CredentialError) else str(error)
        _LOGGER.critical("configuration unavailable: %s", code)
        return ServiceExitCode.NOT_READY
    return await run_v1_service(
        readiness_gate(infrastructure),
        partial(
            _serve_with,
            infrastructure,
            maintenance_configuration=maintenance_configuration,
            acceptance_configuration=acceptance_configuration,
        ),
        report_line=_LOGGER.info,
    )


def run() -> int:
    """Run the exact V1 service and return one closed process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return int(asyncio.run(_run(os.environ)))


if __name__ == "__main__":
    sys.exit(run())
