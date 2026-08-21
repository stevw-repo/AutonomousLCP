"""Human and machine-verifiable reporting boundary."""

from asklegal_reporting.local_conformance import (
    LocalConformanceReport,
    ScenarioResult,
    build_local_conformance_report,
)
from asklegal_reporting.source_coverage import (
    SourceCoverageCycleReport,
    SourceCoverageObservation,
    SourceCoverageReport,
    SourceCoverageRequirement,
    build_source_coverage_cycle_report,
    build_source_coverage_report,
    parse_source_coverage_report,
)

PACKAGE_ROLE: str = "reporting"

__all__ = [
    "PACKAGE_ROLE",
    "LocalConformanceReport",
    "ScenarioResult",
    "SourceCoverageCycleReport",
    "SourceCoverageObservation",
    "SourceCoverageReport",
    "SourceCoverageRequirement",
    "build_local_conformance_report",
    "build_source_coverage_cycle_report",
    "build_source_coverage_report",
    "parse_source_coverage_report",
]
