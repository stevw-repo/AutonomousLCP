"""Bounded fail-closed V1 application readiness aggregation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

_MAX_PROBE_TIMEOUT_MILLISECONDS = 30_000
_APPLICATION_DEPENDENCIES = {
    "ACQUISITION_WORKER": (
        "MANAGEMENT_REGISTER",
        "TASK_SCHEDULER_GENERAL",
        "PRIMARY_VAULT",
        "RECOVERY_VAULT",
        "TELEMETRY",
        "SOURCE_EGRESS",
    ),
    "CONTROL_PLANE": (
        "MANAGEMENT_REGISTER",
        "TASK_SCHEDULER_GENERAL",
        "PRIMARY_VAULT",
        "TELEMETRY",
        "REVIEW_API",
    ),
    "LEGAL_PROCESSING_WORKER": (
        "MANAGEMENT_REGISTER",
        "TASK_SCHEDULER_GENERAL",
        "PRIMARY_VAULT",
        "TELEMETRY",
        "MODEL_EGRESS",
    ),
    "PROMOTION_WORKER": (
        "MANAGEMENT_REGISTER",
        "TASK_SCHEDULER_PROMOTION",
        "PRIMARY_VAULT",
        "RECOVERY_VAULT",
        "TELEMETRY",
        "PROMOTION_EGRESS",
    ),
    "REVIEW_API": (
        "MANAGEMENT_REGISTER",
        "PRIMARY_VAULT",
        "TELEMETRY",
    ),
}


class DependencyCode(StrEnum):
    """Closed local dependencies that may block one V1 application."""

    MANAGEMENT_REGISTER = "MANAGEMENT_REGISTER"
    MODEL_EGRESS = "MODEL_EGRESS"
    PRIMARY_VAULT = "PRIMARY_VAULT"
    PROMOTION_EGRESS = "PROMOTION_EGRESS"
    RECOVERY_VAULT = "RECOVERY_VAULT"
    REVIEW_API = "REVIEW_API"
    SOURCE_EGRESS = "SOURCE_EGRESS"
    TASK_SCHEDULER_GENERAL = "TASK_SCHEDULER_GENERAL"
    TASK_SCHEDULER_PROMOTION = "TASK_SCHEDULER_PROMOTION"
    TELEMETRY = "TELEMETRY"


class ProbeStatus(StrEnum):
    """Closed result of one non-mutating readiness probe."""

    FAILED = "FAILED"
    READY = "READY"
    TIMED_OUT = "TIMED_OUT"


class ReadinessErrorCode(StrEnum):
    """Safe construction failures for the exact readiness gate."""

    APPLICATION = "READINESS_APPLICATION_INVALID"
    PROBE = "READINESS_PROBE_INVALID"
    PROBE_SET = "READINESS_PROBE_SET_INVALID"


class ReadinessError(ValueError):
    """Readiness construction failure with no dependency payload or exception text."""

    code: ReadinessErrorCode

    def __init__(self, code: ReadinessErrorCode) -> None:
        """Create one closed readiness error."""
        self.code = code
        super().__init__(code.value)


class ReadinessProbeFailure(RuntimeError):
    """One adapter-normalized readiness failure with no provider detail."""

    def __init__(self) -> None:
        """Create the only failure a concrete probe may expose to the gate."""
        super().__init__("READINESS_PROBE_FAILED")


@runtime_checkable
class ReadinessProbe(Protocol):
    """One explicitly bounded, non-mutating dependency check."""

    dependency: DependencyCode
    timeout_milliseconds: int

    async def check(self) -> None:
        """Return only on success and otherwise raise a safe or provider error."""
        ...


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """One safe readiness result without provider or topology details."""

    dependency: DependencyCode
    status: ProbeStatus


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Complete ordered readiness outcome for one application."""

    application_code: str
    ready: bool
    results: tuple[ProbeResult, ...]


def required_v1_dependencies(application_code: str) -> tuple[DependencyCode, ...]:
    """Return the one closed readiness dependency set for an application."""
    values = _APPLICATION_DEPENDENCIES.get(application_code)
    if values is None:
        raise ReadinessError(ReadinessErrorCode.APPLICATION)
    return tuple(DependencyCode(value) for value in values)


class V1ReadinessGate:
    """Run every exact dependency probe once with a hard response deadline."""

    def __init__(self, application_code: str, probes: tuple[ReadinessProbe, ...]) -> None:
        """Reject missing, duplicate, extra, mutable, or unbounded probes."""
        expected = required_v1_dependencies(application_code)
        if type(probes) is not tuple:
            raise ReadinessError(ReadinessErrorCode.PROBE_SET)
        dependencies: list[DependencyCode] = []
        for probe in probes:
            if (
                not isinstance(probe, ReadinessProbe)
                or type(probe.dependency) is not DependencyCode
                or type(probe.timeout_milliseconds) is not int
                or not 1 <= probe.timeout_milliseconds <= _MAX_PROBE_TIMEOUT_MILLISECONDS
            ):
                raise ReadinessError(ReadinessErrorCode.PROBE)
            dependencies.append(probe.dependency)
        if tuple(dependencies) != expected or len(dependencies) != len(set(dependencies)):
            raise ReadinessError(ReadinessErrorCode.PROBE_SET)
        self._application_code = application_code
        self._probes = probes

    async def check(self) -> ReadinessReport:
        """Run all probes in stable order and fail closed without leaking errors."""
        results: list[ProbeResult] = []
        for probe in self._probes:
            try:
                async with asyncio.timeout(probe.timeout_milliseconds / 1_000):
                    await probe.check()
            except TimeoutError:
                status = ProbeStatus.TIMED_OUT
            except ReadinessProbeFailure:
                status = ProbeStatus.FAILED
            else:
                status = ProbeStatus.READY
            results.append(ProbeResult(probe.dependency, status))
        complete = tuple(results)
        return ReadinessReport(
            self._application_code,
            all(item.status is ProbeStatus.READY for item in complete),
            complete,
        )
