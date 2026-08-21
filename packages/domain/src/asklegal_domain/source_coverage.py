"""Closed source-observation coverage and outage-impact vocabulary."""

from enum import StrEnum


class SourceOutageImpact(StrEnum):
    """The accepted scope of a failed or incomplete source observation."""

    RELEASE_BLOCKING = "RELEASE_BLOCKING"
    AFFECTED_WORK_BLOCKING = "AFFECTED_WORK_BLOCKING"
    NONBLOCKING = "NONBLOCKING"


class SourceCoverageOutcomeCode(StrEnum):
    """Normalized closed outcomes that a source-coverage report can account."""

    COMPLETE = "COMPLETE"
    PARTIAL_CAPTURE = "PARTIAL_CAPTURE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    INCOMPLETE_OBSERVATION = "INCOMPLETE_OBSERVATION"
    UNSAFE_RESPONSE = "UNSAFE_RESPONSE"


class SourceCoverageDisposition(StrEnum):
    """The deterministic M4 consequence of one normalized source outcome."""

    COMPLETE = "COMPLETE"
    COVERAGE_GAP = "COVERAGE_GAP"
    SOURCE_CONTRACT_REVIEW = "SOURCE_CONTRACT_REVIEW"
    QUARANTINE = "QUARANTINE"
