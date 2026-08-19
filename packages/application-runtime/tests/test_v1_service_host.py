"""Tests for the shared V1 service host and its bounded transport probes."""

from __future__ import annotations

import asyncio
import socket

import pytest
from asklegal_application_runtime import (
    V1_LOGICAL_DESTINATIONS,
    CallableProbe,
    DependencyCode,
    ProbeStatus,
    ReadinessProbeFailure,
    ServiceExitCode,
    TcpReachabilityProbe,
    V1ReadinessGate,
    destination_for,
    format_readiness,
    required_v1_dependencies,
    run_v1_service,
    unready_dependencies,
)

_LEAKY_ADAPTER_MESSAGE = "connection string with a password in it"
_SERVE_FAILURE_MESSAGE = "provider detail that must not escape"


class _AlwaysReady:
    def __init__(self, dependency: DependencyCode) -> None:
        self.dependency = dependency
        self.timeout_milliseconds = 100

    async def check(self) -> None:
        return


class _AlwaysFails:
    def __init__(self, dependency: DependencyCode) -> None:
        self.dependency = dependency
        self.timeout_milliseconds = 100

    async def check(self) -> None:
        raise ReadinessProbeFailure


def _gate(probe_type: type[_AlwaysReady | _AlwaysFails]) -> V1ReadinessGate:
    return V1ReadinessGate(
        "REVIEW_API",
        (
            _AlwaysReady(DependencyCode.MANAGEMENT_REGISTER),
            probe_type(DependencyCode.PRIMARY_VAULT),
            _AlwaysReady(DependencyCode.TELEMETRY),
        ),
    )


def test_service_serves_only_after_every_dependency_is_proved() -> None:
    """A ready gate reaches the serve callable exactly once."""
    served: list[str] = []

    async def serve(shutdown: asyncio.Event) -> None:
        served.append("started")
        shutdown.set()

    lines: list[str] = []
    result = asyncio.run(run_v1_service(_gate(_AlwaysReady), serve, report_line=lines.append))
    assert result is ServiceExitCode.OK
    assert served == ["started"]
    assert lines[0].startswith("REVIEW_API READY")


def test_service_never_starts_when_one_dependency_is_unproved() -> None:
    """Fail closed: an unready process must not begin serving and then break."""
    served: list[str] = []

    async def serve(_shutdown: asyncio.Event) -> None:  # pragma: no cover - must not run
        served.append("started")

    lines: list[str] = []
    result = asyncio.run(run_v1_service(_gate(_AlwaysFails), serve, report_line=lines.append))
    assert result is ServiceExitCode.NOT_READY
    assert served == []
    assert "PRIMARY_VAULT=FAILED" in lines[0]


def test_a_serve_failure_is_a_closed_exit_code_not_a_traceback() -> None:
    """A crash inside serve must not leak provider detail through the exit path."""

    async def serve(_shutdown: asyncio.Event) -> None:
        raise RuntimeError(_SERVE_FAILURE_MESSAGE)

    result = asyncio.run(run_v1_service(_gate(_AlwaysReady), serve, report_line=lambda _: None))
    assert result is ServiceExitCode.FAILED


def test_readiness_line_names_only_dependencies_and_states() -> None:
    """The journal line must carry no host, credential, or provider detail."""
    report = asyncio.run(_gate(_AlwaysFails).check())
    line = format_readiness(report)
    assert line == (
        "REVIEW_API NOT_READY MANAGEMENT_REGISTER=READY PRIMARY_VAULT=FAILED TELEMETRY=READY"
    )
    assert unready_dependencies(report) == ("PRIMARY_VAULT",)


def test_tcp_probe_reaches_a_listening_socket() -> None:
    """A bounded connect proves reachability without sending any payload."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    probe = TcpReachabilityProbe(DependencyCode.TELEMETRY, "127.0.0.1", port)
    try:
        asyncio.run(probe.check())
    finally:
        listener.close()


def test_tcp_probe_on_a_closed_port_is_a_normalized_failure() -> None:
    """A refused connection must surface as the one safe readiness failure."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    probe = TcpReachabilityProbe(DependencyCode.TELEMETRY, "127.0.0.1", port)
    with pytest.raises(ReadinessProbeFailure):
        asyncio.run(probe.check())


def test_callable_probe_hides_the_adapter_error() -> None:
    """An adapter failure must never reach the gate with its provider message."""

    def check() -> None:
        raise ValueError(_LEAKY_ADAPTER_MESSAGE)

    probe = CallableProbe(DependencyCode.MANAGEMENT_REGISTER, check)
    with pytest.raises(ReadinessProbeFailure) as raised:
        asyncio.run(probe.check())
    assert "password" not in str(raised.value)


def test_every_application_resolves_each_of_its_own_dependencies() -> None:
    """The destination table must cover exactly the accepted dependency sets."""
    for application_code, destinations in V1_LOGICAL_DESTINATIONS.items():
        expected = required_v1_dependencies(application_code)
        assert tuple(destinations) == expected
        for dependency in expected:
            host, port = destination_for(application_code, dependency)
            assert host
            assert 0 < port < 65536


def test_an_unknown_dependency_cannot_be_resolved() -> None:
    """Review has no scheduler; asking for one must fail rather than guess."""
    with pytest.raises(ReadinessProbeFailure):
        destination_for("REVIEW_API", DependencyCode.TASK_SCHEDULER_GENERAL)


def test_gate_reports_a_timeout_distinctly_from_a_failure() -> None:
    """A hung dependency is a different operational signal from a refusal."""

    class _Hangs:
        dependency = DependencyCode.TELEMETRY
        timeout_milliseconds = 10

        async def check(self) -> None:
            await asyncio.sleep(5)

    gate = V1ReadinessGate(
        "REVIEW_API",
        (
            _AlwaysReady(DependencyCode.MANAGEMENT_REGISTER),
            _AlwaysReady(DependencyCode.PRIMARY_VAULT),
            _Hangs(),
        ),
    )
    report = asyncio.run(gate.check())
    assert report.ready is False
    assert report.results[2].status is ProbeStatus.TIMED_OUT
