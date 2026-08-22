"""Fail-closed V1 PROMOTION_WORKER service process.

This is the continuous V1 entrypoint, not the local `--check` boundary. It loads
its own systemd credentials, composes only its own adapters, proves every declared
dependency once, and then runs its no-ingress worker loop until systemd sends
`SIGTERM`.

No effect handler is registered until the real worker can read one complete frozen
Promotion Manifest and atomically consume its exact named-human Approval. This
keeps the process observable and ready for local dependency diagnostics without
allowing the former arbitrary-record path or a deployment-wide write switch to
reach embeddings, Pinecone, backup, routing, rollback, or retirement effects.
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

from asklegal_promotion_worker.v1_infrastructure import load_v1_infrastructure, readiness_gate

if TYPE_CHECKING:
    from asklegal_promotion_worker.v1_infrastructure import V1PromotionInfrastructure

_LOGGER = logging.getLogger("asklegal_promotion_worker.v1_service")


def _build_serve(
    infrastructure: V1PromotionInfrastructure,
) -> Callable[[asyncio.Event], Awaitable[None]]:
    """Bind an inert serve loop while approved-manifest execution is unavailable."""

    async def _serve(shutdown: asyncio.Event) -> None:
        """Wait for shutdown without registering any external-effect entrypoint."""
        _LOGGER.warning(
            "PROMOTION_WORKER effects disabled hub=%s reason=APPROVED_MANIFEST_PATH_MISSING",
            infrastructure.scheduler.task_hub,
        )
        await shutdown.wait()
        _LOGGER.info("PROMOTION_WORKER stopped")

    return _serve


async def _run(environment: Mapping[str, str]) -> ServiceExitCode:
    try:
        infrastructure = load_v1_infrastructure(environment)
    except CredentialError as error:
        _LOGGER.critical("credentials unavailable: %s", error.code.value)
        return ServiceExitCode.NOT_READY
    return await run_v1_service(
        readiness_gate(infrastructure),
        _build_serve(infrastructure),
        report_line=_LOGGER.info,
    )


def run() -> int:
    """Run the exact V1 service and return one closed process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return int(asyncio.run(_run(os.environ)))


if __name__ == "__main__":
    sys.exit(run())
