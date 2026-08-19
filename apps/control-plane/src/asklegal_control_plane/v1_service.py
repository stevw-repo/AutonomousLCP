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

import uvicorn
from asklegal_application_runtime import CredentialError, ServiceExitCode, run_v1_service

from asklegal_control_plane.api import create_app, local_dependencies
from asklegal_control_plane.v1_infrastructure import load_v1_infrastructure, readiness_gate

_LISTEN_ADDRESS = "0.0.0.0"  # noqa: S104 - container-only listener on a private network
_LISTEN_PORT = 8000
_SHUTDOWN_GRACE_SECONDS = 30
_LOGGER = logging.getLogger("asklegal_control_plane.v1_service")


async def _serve(shutdown: asyncio.Event) -> None:
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
    server.install_signal_handlers = lambda: None
    serving = asyncio.create_task(server.serve())
    waiting = asyncio.create_task(shutdown.wait())
    # Waiting only on `shutdown` hides a server that failed to start: the task holds
    # the exception, the event never fires, and the process stays up serving nothing.
    finished, _ = await asyncio.wait({serving, waiting}, return_when=asyncio.FIRST_COMPLETED)
    if serving in finished:
        waiting.cancel()
        await serving
        return
    _LOGGER.info("CONTROL_PLANE shutdown requested")
    server.should_exit = True
    await serving


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
