"""Canonical source-observation and complete-cycle coverage reports."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Never

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import (
    SourceCoverageDisposition,
    SourceCoverageOutcomeCode,
    SourceOutageImpact,
)


def _raise_type(message: str) -> Never:
    raise TypeError(message)


def _raise_value(message: str) -> Never:
    raise ValueError(message)


def _text(value: object, field: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        _raise_type(f"{field} must be an exact string")
    if value.strip() != value or (not value and not allow_empty):
        _raise_value(f"{field} must be whitespace-exact and non-empty")
    return value


def _string_tuple(
    value: tuple[object, ...],
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        _raise_type(f"{field} must be an exact tuple")
    result = tuple(_text(item, field) for item in value)
    if (not result and not allow_empty) or result != tuple(sorted(set(result))):
        _raise_value(f"{field} must be sorted, unique, and complete")
    return result


def _count(value: object, field: str) -> int:
    if type(value) is not int:
        _raise_type(f"{field} must be an exact integer")
    if value < 0:
        _raise_value(f"{field} must be non-negative")
    return value


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _validate_enumerated_observation(observation: SourceCoverageObservation) -> None:
    if not observation.observation_manifest_ref:
        _raise_value("enumerated outcomes require the exact observation manifest")
    if observation.retained + observation.not_published + observation.failed != observation.listed:
        _raise_value("artifact outcomes must account for every listed source member")
    incomplete = observation.not_published + observation.failed
    if (observation.outcome is SourceCoverageOutcomeCode.COMPLETE) != (incomplete == 0):
        _raise_value("outcome and completeness counts disagree")


def _validate_failed_enumeration(observation: SourceCoverageObservation) -> None:
    if (
        any(
            (
                observation.listed,
                observation.retained,
                observation.not_published,
                observation.failed,
            )
        )
        or observation.observation_manifest_ref
    ):
        _raise_value("failed enumeration cannot claim listing or artifact completeness")


@dataclass(frozen=True, slots=True)
class SourceCoverageObservation:
    """One exact source result plus the outage policy active for that result."""

    source_id: str
    source_version: str
    endpoint_ids: tuple[str, ...]
    observation_key: str
    observation_cutoff: str
    outcome: SourceCoverageOutcomeCode
    outage_impact: SourceOutageImpact
    failure_codes: tuple[str, ...]
    listed: int
    retained: int
    not_published: int
    failed: int
    observation_manifest_ref: str

    def __post_init__(self) -> None:
        """Reject any count or reference shape that could hide partial capture."""
        for field in ("source_id", "source_version", "observation_key", "observation_cutoff"):
            _text(getattr(self, field), field)
        _string_tuple(self.endpoint_ids, "endpoint_ids")
        _string_tuple(self.failure_codes, "failure_codes", allow_empty=True)
        if type(self.outcome) is not SourceCoverageOutcomeCode:
            _raise_type("outcome must be an exact SourceCoverageOutcomeCode")
        if type(self.outage_impact) is not SourceOutageImpact:
            _raise_type("outage_impact must be an exact SourceOutageImpact")
        for field in ("listed", "retained", "not_published", "failed"):
            _count(getattr(self, field), field)
        _text(self.observation_manifest_ref, "observation_manifest_ref", allow_empty=True)
        if self.observation_manifest_ref:
            _validate_enumerated_observation(self)
        else:
            if self.outcome in {
                SourceCoverageOutcomeCode.COMPLETE,
                SourceCoverageOutcomeCode.PARTIAL_CAPTURE,
            }:
                _raise_value("complete and partial outcomes require the exact observation manifest")
            _validate_failed_enumeration(self)
        if (self.outcome is SourceCoverageOutcomeCode.COMPLETE) == bool(self.failure_codes):
            _raise_value("failure codes must be absent exactly for a complete outcome")


@dataclass(frozen=True, slots=True)
class SourceCoverageReport:
    """One immutable source report with deterministic blocking consequences."""

    observation: SourceCoverageObservation
    disposition: SourceCoverageDisposition
    release_blocking: bool
    affected_work_blocking: bool
    canonical_bytes: bytes
    fingerprint: str


_DISPOSITION_BY_OUTCOME = {
    SourceCoverageOutcomeCode.COMPLETE: SourceCoverageDisposition.COMPLETE,
    SourceCoverageOutcomeCode.PARTIAL_CAPTURE: SourceCoverageDisposition.COVERAGE_GAP,
    SourceCoverageOutcomeCode.SOURCE_UNAVAILABLE: SourceCoverageDisposition.COVERAGE_GAP,
    SourceCoverageOutcomeCode.INCOMPLETE_OBSERVATION: SourceCoverageDisposition.COVERAGE_GAP,
    SourceCoverageOutcomeCode.SOURCE_CONTRACT_CHANGED: (
        SourceCoverageDisposition.SOURCE_CONTRACT_REVIEW
    ),
    SourceCoverageOutcomeCode.UNSAFE_RESPONSE: SourceCoverageDisposition.QUARANTINE,
}


def build_source_coverage_report(
    observation: SourceCoverageObservation,
) -> SourceCoverageReport:
    """Freeze one report without turning a nonblocking source into release authority."""
    if type(observation) is not SourceCoverageObservation:
        _raise_type("observation must be an exact SourceCoverageObservation")
    disposition = _DISPOSITION_BY_OUTCOME[observation.outcome]
    incomplete = disposition is not SourceCoverageDisposition.COMPLETE
    release_blocking = incomplete and (
        observation.outage_impact is SourceOutageImpact.RELEASE_BLOCKING
    )
    affected_work_blocking = incomplete and (
        observation.outage_impact is SourceOutageImpact.AFFECTED_WORK_BLOCKING
    )
    body = canonicalize(
        checked_json_value(
            {
                "affected_work_blocking": affected_work_blocking,
                "disposition": disposition.value,
                "endpoint_ids": list(observation.endpoint_ids),
                "failed": observation.failed,
                "failure_codes": list(observation.failure_codes),
                "listed": observation.listed,
                "observation_manifest_ref": observation.observation_manifest_ref,
                "not_published": observation.not_published,
                "observation_cutoff": observation.observation_cutoff,
                "observation_key": observation.observation_key,
                "outage_impact": observation.outage_impact.value,
                "outcome": observation.outcome.value,
                "release_blocking": release_blocking,
                "retained": observation.retained,
                "schema_id": "asklegal.source-coverage-report",
                "schema_version": "1.0.0",
                "source_id": observation.source_id,
                "source_version": observation.source_version,
            }
        )
    )
    return SourceCoverageReport(
        observation,
        disposition,
        release_blocking,
        affected_work_blocking,
        body,
        _fingerprint(body),
    )


_SOURCE_COVERAGE_REPORT_KEYS = frozenset(
    {
        "affected_work_blocking",
        "disposition",
        "endpoint_ids",
        "failed",
        "failure_codes",
        "listed",
        "observation_manifest_ref",
        "not_published",
        "observation_cutoff",
        "observation_key",
        "outage_impact",
        "outcome",
        "release_blocking",
        "retained",
        "schema_id",
        "schema_version",
        "source_id",
        "source_version",
    }
)


def parse_source_coverage_report(content: bytes) -> SourceCoverageReport:
    """Rebuild and byte-verify one exact canonical source-coverage report."""
    if type(content) is not bytes:
        _raise_type("source coverage report content must be exact bytes")
    document = parse_json_bytes(content, max_bytes=65_536)
    if not isinstance(document, dict) or frozenset(document) != _SOURCE_COVERAGE_REPORT_KEYS:
        _raise_value("source coverage report has unknown or missing fields")
    if document.get("schema_id") != "asklegal.source-coverage-report":
        _raise_value("source coverage report schema_id is unavailable")
    if document.get("schema_version") != "1.0.0":
        _raise_value("source coverage report schema_version is unavailable")
    observation = SourceCoverageObservation(
        source_id=_json_text(document, "source_id"),
        source_version=_json_text(document, "source_version"),
        endpoint_ids=_json_strings(document, "endpoint_ids"),
        observation_key=_json_text(document, "observation_key"),
        observation_cutoff=_json_text(document, "observation_cutoff"),
        outcome=SourceCoverageOutcomeCode(_json_text(document, "outcome")),
        outage_impact=SourceOutageImpact(_json_text(document, "outage_impact")),
        failure_codes=_json_strings(document, "failure_codes", allow_empty=True),
        listed=_json_count(document, "listed"),
        retained=_json_count(document, "retained"),
        not_published=_json_count(document, "not_published"),
        failed=_json_count(document, "failed"),
        observation_manifest_ref=_json_text(
            document,
            "observation_manifest_ref",
            allow_empty=True,
        ),
    )
    report = build_source_coverage_report(observation)
    if (
        document.get("disposition") != report.disposition.value
        or document.get("release_blocking") is not report.release_blocking
        or document.get("affected_work_blocking") is not report.affected_work_blocking
        or report.canonical_bytes != content
    ):
        _raise_value("source coverage report consequence or canonical bytes drifted")
    return report


def _json_text(
    document: dict[str, JsonValue],
    field: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = document.get(field)
    if type(value) is not str or (not value and not allow_empty):
        _raise_type(f"{field} must be an exact JSON string")
    return value


def _json_strings(
    document: dict[str, JsonValue],
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        _raise_type(f"{field} must be an exact JSON string array")
    result = tuple(item for item in value if type(item) is str)
    if not result and not allow_empty:
        _raise_value(f"{field} must not be empty")
    return result


def _json_count(document: dict[str, JsonValue], field: str) -> int:
    value = document.get(field)
    if type(value) is not int or value < 0:
        _raise_type(f"{field} must be an exact non-negative JSON integer")
    return value


@dataclass(frozen=True, slots=True)
class SourceCoverageRequirement:
    """One exact source policy expected in a complete observation cycle."""

    source_id: str
    source_version: str
    outage_impact: SourceOutageImpact

    def __post_init__(self) -> None:
        """Keep cycle requirements exact and policy-bound."""
        _text(self.source_id, "source_id")
        _text(self.source_version, "source_version")
        if type(self.outage_impact) is not SourceOutageImpact:
            _raise_type("outage_impact must be an exact SourceOutageImpact")


@dataclass(frozen=True, slots=True)
class SourceCoverageCycleReport:
    """Complete accounting over one exact due-source requirement set."""

    observation_cutoff: str
    requirements: tuple[SourceCoverageRequirement, ...]
    reports: tuple[SourceCoverageReport, ...]
    missing_source_ids: tuple[str, ...]
    duplicate_source_ids: tuple[str, ...]
    gap_source_ids: tuple[str, ...]
    accounting_complete: bool
    release_blocking: bool
    canonical_bytes: bytes
    fingerprint: str


def build_source_coverage_cycle_report(
    observation_cutoff: str,
    requirements: tuple[SourceCoverageRequirement, ...],
    reports: tuple[SourceCoverageReport, ...],
) -> SourceCoverageCycleReport:
    """Account every due source and apply its exact outage consequence."""
    cutoff = _text(observation_cutoff, "observation_cutoff")
    if type(requirements) is not tuple or any(
        type(item) is not SourceCoverageRequirement for item in requirements
    ):
        _raise_type("requirements must be an exact tuple of SourceCoverageRequirement")
    if type(reports) is not tuple or any(
        type(item) is not SourceCoverageReport for item in reports
    ):
        _raise_type("reports must be an exact tuple of SourceCoverageReport")
    ordered_requirements = tuple(sorted(requirements, key=lambda item: item.source_id))
    requirement_by_id = {item.source_id: item for item in ordered_requirements}
    if len(requirement_by_id) != len(ordered_requirements):
        _raise_value("coverage requirements must name every source exactly once")
    counts: dict[str, int] = {}
    for report in reports:
        source_id = report.observation.source_id
        requirement = requirement_by_id.get(source_id)
        if requirement is None:
            _raise_value("coverage report names a source outside the due requirement set")
        if (
            report.observation.source_version != requirement.source_version
            or report.observation.outage_impact is not requirement.outage_impact
        ):
            _raise_value("coverage report source policy drifted from the due requirement")
        counts[source_id] = counts.get(source_id, 0) + 1
    missing = tuple(sorted(set(requirement_by_id).difference(counts)))
    duplicate = tuple(sorted(source_id for source_id, count in counts.items() if count != 1))
    gaps = tuple(
        sorted(
            set(missing).union(
                report.observation.source_id
                for report in reports
                if report.disposition is not SourceCoverageDisposition.COMPLETE
            )
        )
    )
    accounting_complete = not missing and not duplicate
    release_blocking = (
        bool(duplicate)
        or any(
            requirement_by_id[source_id].outage_impact is SourceOutageImpact.RELEASE_BLOCKING
            for source_id in missing
        )
        or any(report.release_blocking for report in reports)
    )
    ordered_reports = tuple(
        sorted(reports, key=lambda item: (item.observation.source_id, item.fingerprint))
    )
    body = canonicalize(
        checked_json_value(
            {
                "accounting_complete": accounting_complete,
                "duplicate_source_ids": list(duplicate),
                "gap_source_ids": list(gaps),
                "missing_source_ids": list(missing),
                "observation_cutoff": cutoff,
                "release_blocking": release_blocking,
                "requirements": [
                    {
                        "outage_impact": item.outage_impact.value,
                        "source_id": item.source_id,
                        "source_version": item.source_version,
                    }
                    for item in ordered_requirements
                ],
                "schema_id": "asklegal.source-coverage-cycle-report",
                "schema_version": "1.0.0",
                "source_reports": [
                    {
                        "fingerprint": item.fingerprint,
                        "source_id": item.observation.source_id,
                    }
                    for item in ordered_reports
                ],
            }
        )
    )
    return SourceCoverageCycleReport(
        cutoff,
        ordered_requirements,
        ordered_reports,
        missing,
        duplicate,
        gaps,
        accounting_complete,
        release_blocking,
        body,
        _fingerprint(body),
    )
