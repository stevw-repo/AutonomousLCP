"""Human and machine-verifiable reporting boundary."""

from asklegal_reporting.local_conformance import (
    LocalConformanceReport,
    ScenarioResult,
    build_local_conformance_report,
)

PACKAGE_ROLE: str = "reporting"

__all__ = [
    "PACKAGE_ROLE",
    "LocalConformanceReport",
    "ScenarioResult",
    "build_local_conformance_report",
]
