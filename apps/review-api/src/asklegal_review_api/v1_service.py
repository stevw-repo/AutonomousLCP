"""Exact V1 REVIEW_API service process.

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
from pathlib import Path

import uvicorn
from asklegal_application_runtime import CredentialError, ServiceExitCode, run_v1_service

from asklegal_review_api.api import create_app, local_dependencies
from asklegal_review_api.v1_infrastructure import load_v1_infrastructure, readiness_gate

_LISTEN_ADDRESS = "0.0.0.0"  # noqa: S104 - container-only listener on a private network
_LISTEN_PORT = 8001
_SHUTDOWN_GRACE_SECONDS = 30
_LOGGER = logging.getLogger("asklegal_review_api.v1_service")

# Review is the one V1 application with an inbound listener, and the accepted
# topology puts it behind the internal certificate authority: CONTROL_PLANE proves
# it with a verified TLS handshake, not a bare connect. Serving plain HTTP here
# would leave that dependency permanently unprovable, so the issued server
# material is required rather than optional.
_TLS_CERTIFICATE = Path("/etc/asklegal/tls/review-api/tls.crt")
_TLS_PRIVATE_KEY = Path("/etc/asklegal/tls/review-api/tls.key")


def _server_material_present() -> bool:
    """Report whether this service can read its own issued server material."""
    return all(path.is_file() and os.access(path, os.R_OK)
               for path in (_TLS_CERTIFICATE, _TLS_PRIVATE_KEY))


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
            ssl_certfile=str(_TLS_CERTIFICATE),
            ssl_keyfile=str(_TLS_PRIVATE_KEY),
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
    _LOGGER.info("REVIEW_API shutdown requested")
    server.should_exit = True
    await serving


async def _run(environment: Mapping[str, str]) -> ServiceExitCode:
    try:
        infrastructure = load_v1_infrastructure(environment)
    except CredentialError as error:
        _LOGGER.critical("credentials unavailable: %s", error.code.value)
        return ServiceExitCode.NOT_READY
    if not _server_material_present():
        _LOGGER.critical("server material unavailable: TLS_MATERIAL_UNREADABLE")
        return ServiceExitCode.NOT_READY
    return await run_v1_service(readiness_gate(infrastructure), _serve, report_line=_LOGGER.info)


def run() -> int:
    """Run the exact V1 service and return one closed process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return int(asyncio.run(_run(os.environ)))


if __name__ == "__main__":
    sys.exit(run())
