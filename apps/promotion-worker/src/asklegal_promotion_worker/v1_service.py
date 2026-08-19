"""Exact V1 PROMOTION_WORKER service process.

This is the continuous V1 entrypoint, not the local `--check` boundary. It loads
its own systemd credentials, composes only its own adapters, proves every declared
dependency once, and then runs its no-ingress worker loop until systemd sends
`SIGTERM`.

The worker now serves its real Durable Task hub. It registers one orchestration
and its two activities, then hands control to the scheduler's own worker loop,
which claims work, fences it, checkpoints each activity result, and replays from
that checkpoint rather than repeating an effect.

The effects are real: the activities embed through Azure OpenAI and write to the
Pinecone serving target, each through this application's own egress proxy. Writing
still requires `PROMOTION_WRITE_AUTHORIZED=true`; without it the worker runs the
orchestration and fails closed at the upsert rather than reaching a real index.
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

from asklegal_promotion_worker.v1_infrastructure import load_v1_infrastructure, readiness_gate
from asklegal_promotion_worker.v1_pipeline import (
    PromotionActivities,
    PromotionHandoff,
    promote_records,
)

if TYPE_CHECKING:
    from asklegal_promotion_worker.v1_infrastructure import V1PromotionInfrastructure

_ORCHESTRATION_VERSION = "1.0.0"
_HANDOFF_POLL_SECONDS = 10.0
_LOGGER = logging.getLogger("asklegal_promotion_worker.v1_service")


def _build_serve(
    infrastructure: V1PromotionInfrastructure,
    environment: Mapping[str, str],
) -> Callable[[asyncio.Event], Awaitable[None]]:
    """Bind one serve callable to this process's own infrastructure."""

    async def _serve(shutdown: asyncio.Event) -> None:
        """Serve the real task hub until systemd asks the process to stop."""
        activities = PromotionActivities(infrastructure, environment)
        worker = infrastructure.scheduler.create_worker(
            concurrency_options=ConcurrencyOptions()
        )
        worker.add_activity(activities.embed_records)
        worker.add_activity(activities.upsert_records)
        worker.add_orchestrator(promote_records)
        worker.start()
        _LOGGER.info(
            "PROMOTION_WORKER serving hub=%s index=%s writes=%s",
            infrastructure.scheduler.task_hub,
            activities.index,
            "AUTHORIZED" if activities.authorized else "REFUSED",
        )
        # The control plane cannot schedule on this hub, so it records promotion
        # intents in the register instead. Poll for them beside the hub worker.
        handoff = PromotionHandoff(infrastructure, activities)
        try:
            while not shutdown.is_set():
                try:
                    while await asyncio.to_thread(handoff.poll_once) is not None:
                        pass
                except OSError as error:
                    # A register blip must not kill the worker; the hub side is
                    # still serving and the next poll retries.
                    _LOGGER.warning("PROMOTION_WORKER handoff poll failed: %s", error)
                try:
                    async with asyncio.timeout(_HANDOFF_POLL_SECONDS):
                        await shutdown.wait()
                except TimeoutError:
                    continue
        finally:
            _LOGGER.info("PROMOTION_WORKER shutdown requested")
            await asyncio.to_thread(worker.stop)
            _LOGGER.info("PROMOTION_WORKER stopped serving")

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
