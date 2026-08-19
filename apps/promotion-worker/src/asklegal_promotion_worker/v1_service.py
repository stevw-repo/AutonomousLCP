"""Exact V1 PROMOTION_WORKER service process.

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
from collections.abc import Mapping

from asklegal_application_runtime import (
    CredentialError,
    ServiceExitCode,
    WorkerResultCode,
    run_v1_service,
)

from asklegal_promotion_worker.runtime import create_runtime
from asklegal_promotion_worker.v1_infrastructure import load_v1_infrastructure, readiness_gate

_IDLE_POLL_SECONDS = 1.0
_LOGGER = logging.getLogger("asklegal_promotion_worker.v1_service")


async def _serve(shutdown: asyncio.Event) -> None:
    """Claim bounded work until shutdown, then drain the current claim exactly once."""
    runtime = create_runtime()
    while not shutdown.is_set():
        result = await asyncio.to_thread(runtime.run_once, lambda _lease: None)
        if result is WorkerResultCode.NO_WORK:
            try:
                async with asyncio.timeout(_IDLE_POLL_SECONDS):
                    await shutdown.wait()
            except TimeoutError:
                continue
    _LOGGER.info("PROMOTION_WORKER shutdown requested")
    if runtime.shutdown() is WorkerResultCode.INTERRUPTED:
        _LOGGER.info("PROMOTION_WORKER interrupted one in-flight claim")


async def _run(environment: Mapping[str, str]) -> ServiceExitCode:
    try:
        infrastructure = load_v1_infrastructure(environment)
    except CredentialError as error:
        _LOGGER.critical("credentials unavailable: %s", error.code.value)
        return ServiceExitCode.NOT_READY
    return await run_v1_service(readiness_gate(infrastructure), _serve, report_line=_LOGGER.info)


def run() -> int:
    """Run the exact V1 service and return one closed process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return int(asyncio.run(_run(os.environ)))


if __name__ == "__main__":
    sys.exit(run())
