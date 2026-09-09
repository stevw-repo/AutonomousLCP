"""Exact V1 LEGAL_PROCESSING_WORKER service process.

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

from asklegal_legal_processing_worker.v1_infrastructure import (
    load_v1_infrastructure,
    readiness_gate,
)
from asklegal_legal_processing_worker.v1_pipeline import (
    ProcessingActivities,
    ProcessingPipelineError,
    analyse_stored_evidence,
    build_live_activities,
    process_cases_batch,
    process_legislation_batch,
    run_hk_v1_acceptance_legal_processing,
)

if TYPE_CHECKING:
    from asklegal_legal_processing_worker.v1_infrastructure import (
        V1LegalProcessingInfrastructure,
    )

_LOGGER = logging.getLogger("asklegal_legal_processing_worker.v1_service")


def build_serve(
    infrastructure: V1LegalProcessingInfrastructure,
    activities: ProcessingActivities,
) -> Callable[[asyncio.Event], Awaitable[None]]:
    """Bind one serve callable to this process's own infrastructure."""

    async def _serve(shutdown: asyncio.Event) -> None:
        """Serve the real task hub until systemd asks the process to stop."""
        worker = infrastructure.scheduler.create_worker(concurrency_options=ConcurrencyOptions())
        worker.add_activity(activities.read_evidence)
        worker.add_activity(activities.analyse_evidence)
        worker.add_activity(activities.prepare_cases_batch)
        worker.add_activity(activities.prepare_legislation_batch)
        worker.add_activity(activities.accept_legislation_manifest)
        worker.add_activity(activities.prepare_hk_v1_acceptance_inputs)
        worker.add_activity(activities.start_hk_v1_acceptance_legal_processing)
        worker.add_orchestrator(analyse_stored_evidence)
        worker.add_orchestrator(process_cases_batch)
        worker.add_orchestrator(process_legislation_batch)
        worker.add_orchestrator(run_hk_v1_acceptance_legal_processing)
        worker.start()
        _LOGGER.info(
            "LEGAL_PROCESSING_WORKER serving hub=%s deployment=%s",
            infrastructure.scheduler.task_hub,
            activities.deployment,
        )
        try:
            await shutdown.wait()
        finally:
            _LOGGER.info("LEGAL_PROCESSING_WORKER shutdown requested")
            await asyncio.to_thread(worker.stop)
            _LOGGER.info("LEGAL_PROCESSING_WORKER stopped serving")

    return _serve


async def run_with_environment(environment: Mapping[str, str]) -> ServiceExitCode:
    """Compose local authority before any readiness probe or worker starts."""
    try:
        infrastructure = load_v1_infrastructure(environment)
        activities = build_live_activities(infrastructure, environment)
    except CredentialError as error:
        _LOGGER.critical("credentials unavailable: %s", error.code.value)
        return ServiceExitCode.NOT_READY
    except ProcessingPipelineError as error:
        _LOGGER.critical("live semantic composition unavailable: %s", error)
        return ServiceExitCode.NOT_READY
    return await run_v1_service(
        readiness_gate(infrastructure),
        build_serve(infrastructure, activities),
        report_line=_LOGGER.info,
    )


def run() -> int:
    """Run the exact V1 service and return one closed process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return int(asyncio.run(run_with_environment(os.environ)))


if __name__ == "__main__":
    sys.exit(run())
