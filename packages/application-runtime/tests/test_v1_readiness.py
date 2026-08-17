"""Offline proofs for exact bounded V1 readiness aggregation."""

import asyncio
from dataclasses import dataclass

import pytest
from asklegal_application_runtime import (
    DependencyCode,
    ProbeStatus,
    ReadinessError,
    ReadinessErrorCode,
    ReadinessProbeFailure,
    V1ReadinessGate,
    required_v1_dependencies,
)


@dataclass(frozen=True, slots=True)
class _Probe:
    dependency: DependencyCode
    timeout_milliseconds: int = 100
    outcome: str = "READY"

    async def check(self) -> None:
        if self.outcome == "FAIL":
            raise ReadinessProbeFailure
        if self.outcome == "TIMEOUT":
            await asyncio.sleep(1)


def _probes(application_code: str) -> tuple[_Probe, ...]:
    return tuple(_Probe(dependency) for dependency in required_v1_dependencies(application_code))


@pytest.mark.parametrize(
    "application_code",
    [
        "ACQUISITION_WORKER",
        "CONTROL_PLANE",
        "LEGAL_PROCESSING_WORKER",
        "PROMOTION_WORKER",
        "REVIEW_API",
    ],
)
def test_all_five_applications_require_their_complete_exact_dependency_set(
    application_code: str,
) -> None:
    """Become ready only after every dependency succeeds in stable order."""
    gate = V1ReadinessGate(application_code, _probes(application_code))
    report = asyncio.run(gate.check())

    assert report.application_code == application_code
    assert report.ready is True
    assert tuple(item.dependency for item in report.results) == required_v1_dependencies(
        application_code
    )
    assert all(item.status is ProbeStatus.READY for item in report.results)


def test_failure_and_timeout_are_safe_complete_and_fail_closed() -> None:
    """Continue the complete check but expose no provider exception detail."""
    probes = list(_probes("REVIEW_API"))
    probes[0] = _Probe(DependencyCode.MANAGEMENT_REGISTER, outcome="FAIL")
    probes[1] = _Probe(DependencyCode.PRIMARY_VAULT, timeout_milliseconds=1, outcome="TIMEOUT")
    report = asyncio.run(V1ReadinessGate("REVIEW_API", tuple(probes)).check())

    assert report.ready is False
    assert tuple(item.status for item in report.results) == (
        ProbeStatus.FAILED,
        ProbeStatus.TIMED_OUT,
        ProbeStatus.READY,
    )
    assert "READINESS_PROBE_FAILED" not in repr(report)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered", "unbounded"])
def test_incomplete_or_unbounded_probe_inventory_is_rejected(mutation: str) -> None:
    """Do not silently weaken or reorder the application's dependency gate."""
    probes = list(_probes("CONTROL_PLANE"))
    if mutation == "missing":
        probes.pop()
    elif mutation == "duplicate":
        probes[-1] = probes[0]
    elif mutation == "reordered":
        probes[0], probes[1] = probes[1], probes[0]
    else:
        probes[0] = _Probe(DependencyCode.MANAGEMENT_REGISTER, timeout_milliseconds=0)

    with pytest.raises(ReadinessError) as error:
        V1ReadinessGate("CONTROL_PLANE", tuple(probes))

    assert error.value.code in {ReadinessErrorCode.PROBE, ReadinessErrorCode.PROBE_SET}


def test_unknown_application_is_rejected() -> None:
    """Never infer a readiness dependency set for an unknown process."""
    with pytest.raises(ReadinessError) as error:
        required_v1_dependencies("UNKNOWN")
    assert error.value.code is ReadinessErrorCode.APPLICATION
