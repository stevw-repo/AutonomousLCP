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
from typing import TYPE_CHECKING

from asklegal_application_runtime import (
    CredentialError,
    ServiceExitCode,
    run_v1_service,
)
from asklegal_durable_task import ConcurrencyOptions

from asklegal_acquisition_worker.v1_infrastructure import load_v1_infrastructure, readiness_gate
from asklegal_acquisition_worker.v1_pipeline import (
    acquire_endpoint,
    acquire_endpoints,
    acquire_gazette_window,
    acquire_inventory,
    acquire_rendered_discovery,
    acquire_source_cycle,
    build_activities,
)

if TYPE_CHECKING:
    from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure

_IDLE_POLL_SECONDS = 1.0
_LOGGER = logging.getLogger("asklegal_acquisition_worker.v1_service")


def _build_serve(
    infrastructure: V1AcquisitionInfrastructure,
    environment: Mapping[str, str],
) -> Callable[[asyncio.Event], Awaitable[None]]:
    """Bind one serve callable to this process's own infrastructure."""

    async def _serve(shutdown: asyncio.Event) -> None:
        """Serve the real task hub until systemd asks the process to stop."""
        activities = build_activities(infrastructure, environment)
        worker = infrastructure.scheduler.create_worker(concurrency_options=ConcurrencyOptions())
        worker.add_activity(activities.capture_endpoint)
        worker.add_activity(activities.capture_gazette_window)
        worker.add_activity(activities.capture_inventory)
        worker.add_activity(activities.capture_rendered_discovery)
        worker.add_activity(activities.plan_source_cycle)
        worker.add_activity(activities.capture_due_source)
        worker.add_activity(activities.assemble_source_cycle)
        worker.add_orchestrator(acquire_endpoint)
        worker.add_orchestrator(acquire_endpoints)
        worker.add_orchestrator(acquire_gazette_window)
        worker.add_orchestrator(acquire_inventory)
        worker.add_orchestrator(acquire_rendered_discovery)
        worker.add_orchestrator(acquire_source_cycle)
        worker.start()
        _LOGGER.info(
            "ACQUISITION_WORKER serving hub=%s vault=%s",
            infrastructure.scheduler.task_hub,
            infrastructure.primary_vault.vault_name.value,
        )
        try:
            await shutdown.wait()
        finally:
            _LOGGER.info("ACQUISITION_WORKER shutdown requested")
            await asyncio.to_thread(worker.stop)
            _LOGGER.info("ACQUISITION_WORKER stopped serving")

    return _serve


async def _run(environment: Mapping[str, str]) -> ServiceExitCode:
    try:
        infrastructure = load_v1_infrastructure(environment)
    except CredentialError as error:
        _LOGGER.critical("credentials unavailable: %s", error.code.value)
        return ServiceExitCode.NOT_READY
    return await run_v1_service(
        readiness_gate(infrastructure),
        _build_serve(infrastructure, environment),
        report_line=_LOGGER.info,
    )


def run() -> int:
    """Run the exact V1 service and return one closed process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return int(asyncio.run(_run(os.environ)))


if __name__ == "__main__":
    sys.exit(run())
