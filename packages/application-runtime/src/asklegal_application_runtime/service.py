"""The exact V1 long-running service host shared by all five applications.

A V1 process is not the local `--check` entrypoint. It loads its own credentials,
composes only its own adapters, proves every declared dependency once through the
bounded readiness gate, and only then serves. A process that cannot prove its
dependencies exits fail-closed rather than starting and failing later under load.

Shutdown is cooperative: `SIGTERM` from systemd sets the shutdown event, the
serve callable is expected to stop accepting new work and finish what it holds,
and the host waits for it. No effect is performed here.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable
from enum import IntEnum

from asklegal_application_runtime.readiness import ProbeStatus, ReadinessReport, V1ReadinessGate

ServeCallable = Callable[[asyncio.Event], Awaitable[None]]


class ServiceExitCode(IntEnum):
    """Closed process exit codes; the value is the only thing a unit may observe."""

    OK = 0
    NOT_READY = 1
    FAILED = 2


def format_readiness(report: ReadinessReport) -> str:
    """Render one secret-free readiness line safe for the journal."""
    results = " ".join(
        f"{item.dependency.value}={item.status.value}" for item in report.results
    )
    verdict = "READY" if report.ready else "NOT_READY"
    return f"{report.application_code} {verdict} {results}"


async def run_v1_service(
    gate: V1ReadinessGate,
    serve: ServeCallable,
    *,
    report_line: Callable[[str], None],
) -> ServiceExitCode:
    """Prove readiness once, then serve until an ordinary shutdown signal arrives."""
    report = await gate.check()
    report_line(format_readiness(report))
    if not report.ready:
        return ServiceExitCode.NOT_READY
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    for received in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(received, shutdown.set)
        except (NotImplementedError, RuntimeError, ValueError):
            continue
        installed.append(received)
    try:
        await serve(shutdown)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        return ServiceExitCode.FAILED
    finally:
        for received in installed:
            loop.remove_signal_handler(received)
    return ServiceExitCode.OK


def unready_dependencies(report: ReadinessReport) -> tuple[str, ...]:
    """Return only the dependency codes that did not reach READY."""
    return tuple(
        item.dependency.value
        for item in report.results
        if item.status is not ProbeStatus.READY
    )
