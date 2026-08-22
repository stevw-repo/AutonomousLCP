"""Bounded, non-mutating V1 readiness probes and the exact destination table.

Only transport-level probes live here, because this package may not depend on an
infrastructure adapter. An adapter-backed check (SQL `SELECT 1`, a vault's
versioning and Object Lock read) is supplied by the owning application through
`CallableProbe`, which runs the blocking call off the event loop and converts
every failure into one `ReadinessProbeFailure` carrying no provider detail.

A transport probe proves that the exact declared destination accepts a
connection. It deliberately does not claim the service behind it is healthy:
the Durable Task emulator, the collector, and the egress proxies expose no
documented non-mutating health operation, and inventing one would be a false
readiness signal.
"""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from asklegal_application_runtime.readiness import DependencyCode, ReadinessProbeFailure

_TRANSPORT_TIMEOUT_MILLISECONDS = 5_000
_ADAPTER_TIMEOUT_MILLISECONDS = 15_000

V1_INTERNAL_CA_BUNDLE = Path("/etc/asklegal/tls/internal-ca.crt")
"""Root-owned read-only trust anchor for every internal V1 TLS listener."""

V1_LOGICAL_DESTINATIONS: dict[str, dict[DependencyCode, tuple[str, int]]] = {
    "ACQUISITION_WORKER": {
        DependencyCode.MANAGEMENT_REGISTER: ("sql-server", 1433),
        DependencyCode.TASK_SCHEDULER_GENERAL: ("dts-general", 8080),
        DependencyCode.PRIMARY_VAULT: ("vault-primary", 7070),
        DependencyCode.RECOVERY_VAULT: ("vault-recovery", 7070),
        DependencyCode.TELEMETRY: ("otel-collector", 4317),
        DependencyCode.SOURCE_EGRESS: ("egress-source", 3128),
    },
    "CONTROL_PLANE": {
        DependencyCode.MANAGEMENT_REGISTER: ("sql-server", 1433),
        DependencyCode.TASK_SCHEDULER_GENERAL: ("dts-general", 8080),
        # The control plane sequences all three stages, so it alone reaches a
        # second scheduler. The four workers still reach exactly one each.
        DependencyCode.TASK_SCHEDULER_PROMOTION: ("dts-promotion", 8080),
        DependencyCode.PRIMARY_VAULT: ("vault-primary", 7070),
        DependencyCode.TELEMETRY: ("otel-collector", 4317),
        DependencyCode.REVIEW_API: ("review-api", 8001),
    },
    "LEGAL_PROCESSING_WORKER": {
        DependencyCode.MANAGEMENT_REGISTER: ("sql-server", 1433),
        DependencyCode.TASK_SCHEDULER_GENERAL: ("dts-general", 8080),
        DependencyCode.PRIMARY_VAULT: ("vault-primary", 7070),
        DependencyCode.TELEMETRY: ("otel-collector", 4317),
        DependencyCode.MODEL_EGRESS: ("egress-model", 3128),
    },
    "PROMOTION_WORKER": {
        DependencyCode.MANAGEMENT_REGISTER: ("sql-server", 1433),
        DependencyCode.TASK_SCHEDULER_PROMOTION: ("dts-promotion", 8080),
        DependencyCode.PRIMARY_VAULT: ("vault-primary", 7070),
        DependencyCode.RECOVERY_VAULT: ("vault-recovery", 7070),
        DependencyCode.TELEMETRY: ("otel-collector", 4317),
        DependencyCode.PROMOTION_EGRESS: ("egress-promotion", 3128),
    },
    "REVIEW_API": {
        DependencyCode.MANAGEMENT_REGISTER: ("sql-server", 1433),
        DependencyCode.PRIMARY_VAULT: ("vault-primary", 7070),
        DependencyCode.TELEMETRY: ("otel-collector", 4317),
    },
}


def destination_for(application_code: str, dependency: DependencyCode) -> tuple[str, int]:
    """Return the exact declared host and port for one application dependency."""
    destinations = V1_LOGICAL_DESTINATIONS.get(application_code)
    if destinations is None or dependency not in destinations:
        raise ReadinessProbeFailure
    return destinations[dependency]


@dataclass(frozen=True, slots=True)
class TcpReachabilityProbe:
    """Prove that an exact private destination accepts one bounded connection."""

    dependency: DependencyCode
    host: str
    port: int
    timeout_milliseconds: int = _TRANSPORT_TIMEOUT_MILLISECONDS

    async def check(self) -> None:
        """Open and immediately close one connection without sending any payload."""
        try:
            _, writer = await asyncio.open_connection(self.host, self.port)
        except OSError, ValueError:
            raise ReadinessProbeFailure from None
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            raise ReadinessProbeFailure from None


@dataclass(frozen=True, slots=True)
class TlsReachabilityProbe:
    """Prove one bounded TLS handshake against an exact certificate and hostname."""

    dependency: DependencyCode
    host: str
    port: int
    ca_bundle: Path
    timeout_milliseconds: int = _TRANSPORT_TIMEOUT_MILLISECONDS

    async def check(self) -> None:
        """Complete a verified handshake; a hostname or trust failure is not ready."""
        try:
            context = ssl.create_default_context(cafile=str(self.ca_bundle))
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            _, writer = await asyncio.open_connection(
                self.host, self.port, ssl=context, server_hostname=self.host
            )
        except OSError, ValueError, ssl.SSLError:
            raise ReadinessProbeFailure from None
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            raise ReadinessProbeFailure from None


@dataclass(frozen=True, slots=True)
class CallableProbe:
    """Adapt one blocking non-mutating adapter check without leaking its error."""

    dependency: DependencyCode
    check_call: Callable[[], None] = field(repr=False)
    timeout_milliseconds: int = _ADAPTER_TIMEOUT_MILLISECONDS

    async def check(self) -> None:
        """Run the adapter check in a worker thread and normalize every failure."""
        try:
            await asyncio.to_thread(self.check_call)
        except Exception:  # noqa: BLE001
            raise ReadinessProbeFailure from None
