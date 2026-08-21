"""Source coverage reporting and release-blocking accounting tests."""

from dataclasses import replace

import pytest
from asklegal_domain import SourceCoverageDisposition, SourceCoverageOutcomeCode, SourceOutageImpact
from asklegal_reporting import (
    SourceCoverageObservation,
    SourceCoverageRequirement,
    build_source_coverage_cycle_report,
    build_source_coverage_report,
    parse_source_coverage_report,
)

_GLD = "HK-LEG-GLD-EGAZETTE"
_HKEL = "HK-LEG-HKEL-GAZETTE-BACKCAPTURE"
_ENDPOINT = "sep_000000000000000000000000000000000000000000000041"


def _observation(
    *,
    source_id: str = _HKEL,
    outcome: SourceCoverageOutcomeCode = SourceCoverageOutcomeCode.COMPLETE,
    impact: SourceOutageImpact = SourceOutageImpact.NONBLOCKING,
) -> SourceCoverageObservation:
    if outcome is SourceCoverageOutcomeCode.COMPLETE:
        return SourceCoverageObservation(
            source_id,
            "1.0.0",
            (_ENDPOINT,),
            "01/01/2026..31/01/2026:en",
            "2026-01-31T23:59:59Z",
            outcome,
            impact,
            (),
            1,
            1,
            0,
            0,
            "poc/source/gazette-listing/report",
        )
    if outcome is SourceCoverageOutcomeCode.PARTIAL_CAPTURE:
        return SourceCoverageObservation(
            source_id,
            "1.0.0",
            (_ENDPOINT,),
            "01/01/2026..31/01/2026:en",
            "2026-01-31T23:59:59Z",
            outcome,
            impact,
            ("NOT_PUBLISHED",),
            1,
            0,
            1,
            0,
            "poc/source/gazette-listing/report",
        )
    return SourceCoverageObservation(
        source_id,
        "1.0.0",
        (_ENDPOINT,),
        "01/01/2026..31/01/2026:en",
        "2026-01-31T23:59:59Z",
        outcome,
        impact,
        (outcome.value,),
        0,
        0,
        0,
        0,
        "",
    )


def test_complete_source_report_is_reproducible_and_clear() -> None:
    first = build_source_coverage_report(_observation())
    second = build_source_coverage_report(_observation())

    assert first == second
    assert first.disposition is SourceCoverageDisposition.COMPLETE
    assert first.release_blocking is False
    assert first.affected_work_blocking is False
    assert first.fingerprint.startswith("sha256:")
    assert b'"observation_manifest_ref":' in first.canonical_bytes
    assert b'"listing_manifest_ref":' not in first.canonical_bytes


def test_exact_source_report_round_trips_and_rejects_tampering() -> None:
    report = build_source_coverage_report(_observation())

    assert parse_source_coverage_report(report.canonical_bytes) == report

    changed_consequence = report.canonical_bytes.replace(
        b'"release_blocking":false',
        b'"release_blocking":true',
    )
    with pytest.raises(ValueError, match="consequence or canonical bytes drifted"):
        parse_source_coverage_report(changed_consequence)
    with pytest.raises(ValueError, match="canonical bytes drifted"):
        parse_source_coverage_report(report.canonical_bytes + b"\n")


def test_hkel_backcapture_gap_is_visible_but_not_release_blocking() -> None:
    report = build_source_coverage_report(
        _observation(outcome=SourceCoverageOutcomeCode.PARTIAL_CAPTURE)
    )

    assert report.disposition is SourceCoverageDisposition.COVERAGE_GAP
    assert report.release_blocking is False
    assert report.affected_work_blocking is False


def test_partial_release_required_gld_report_blocks() -> None:
    report = build_source_coverage_report(
        _observation(
            source_id=_GLD,
            outcome=SourceCoverageOutcomeCode.PARTIAL_CAPTURE,
            impact=SourceOutageImpact.RELEASE_BLOCKING,
        )
    )

    assert report.disposition is SourceCoverageDisposition.COVERAGE_GAP
    assert report.release_blocking is True


@pytest.mark.parametrize(
    ("outcome", "disposition"),
    [
        (
            SourceCoverageOutcomeCode.SOURCE_CONTRACT_CHANGED,
            SourceCoverageDisposition.SOURCE_CONTRACT_REVIEW,
        ),
        (
            SourceCoverageOutcomeCode.UNSAFE_RESPONSE,
            SourceCoverageDisposition.QUARANTINE,
        ),
        (
            SourceCoverageOutcomeCode.INCOMPLETE_OBSERVATION,
            SourceCoverageDisposition.COVERAGE_GAP,
        ),
    ],
)
def test_failure_class_is_preserved_in_the_report(
    outcome: SourceCoverageOutcomeCode,
    disposition: SourceCoverageDisposition,
) -> None:
    report = build_source_coverage_report(_observation(outcome=outcome))

    assert report.disposition is disposition
    assert report.observation.failure_codes == (outcome.value,)


def test_report_rejects_counts_that_hide_partial_capture() -> None:
    with pytest.raises(ValueError, match="counts disagree"):
        replace(
            _observation(),
            outcome=SourceCoverageOutcomeCode.PARTIAL_CAPTURE,
            failure_codes=("NOT_PUBLISHED",),
        )

    with pytest.raises(ValueError, match="cannot claim"):
        replace(
            _observation(outcome=SourceCoverageOutcomeCode.SOURCE_UNAVAILABLE),
            listed=1,
        )


def test_cycle_blocks_missing_or_partial_release_required_source() -> None:
    requirements = (
        SourceCoverageRequirement(_GLD, "1.0.0", SourceOutageImpact.RELEASE_BLOCKING),
        SourceCoverageRequirement(_HKEL, "1.0.0", SourceOutageImpact.NONBLOCKING),
    )
    hkel_gap = build_source_coverage_report(
        _observation(outcome=SourceCoverageOutcomeCode.PARTIAL_CAPTURE)
    )
    missing_gld = build_source_coverage_cycle_report(
        "2026-01-31T23:59:59Z",
        requirements,
        (hkel_gap,),
    )

    assert missing_gld.accounting_complete is False
    assert missing_gld.missing_source_ids == (_GLD,)
    assert missing_gld.release_blocking is True

    gld_gap = build_source_coverage_report(
        _observation(
            source_id=_GLD,
            outcome=SourceCoverageOutcomeCode.PARTIAL_CAPTURE,
            impact=SourceOutageImpact.RELEASE_BLOCKING,
        )
    )
    complete_accounting = build_source_coverage_cycle_report(
        "2026-01-31T23:59:59Z",
        requirements,
        (hkel_gap, gld_gap),
    )

    assert complete_accounting.accounting_complete is True
    assert complete_accounting.gap_source_ids == (_GLD, _HKEL)
    assert complete_accounting.release_blocking is True


def test_nonblocking_gap_does_not_override_a_complete_required_source() -> None:
    requirements = (
        SourceCoverageRequirement(_GLD, "1.0.0", SourceOutageImpact.RELEASE_BLOCKING),
        SourceCoverageRequirement(_HKEL, "1.0.0", SourceOutageImpact.NONBLOCKING),
    )
    gld_complete = build_source_coverage_report(
        _observation(source_id=_GLD, impact=SourceOutageImpact.RELEASE_BLOCKING)
    )
    hkel_gap = build_source_coverage_report(
        _observation(outcome=SourceCoverageOutcomeCode.PARTIAL_CAPTURE)
    )

    cycle = build_source_coverage_cycle_report(
        "2026-01-31T23:59:59Z",
        requirements,
        (hkel_gap, gld_complete),
    )

    assert cycle.accounting_complete is True
    assert cycle.gap_source_ids == (_HKEL,)
    assert cycle.release_blocking is False


def test_duplicate_report_blocks_ambiguous_cycle_accounting() -> None:
    requirement = (SourceCoverageRequirement(_HKEL, "1.0.0", SourceOutageImpact.NONBLOCKING),)
    report = build_source_coverage_report(_observation())

    cycle = build_source_coverage_cycle_report(
        "2026-01-31T23:59:59Z",
        requirement,
        (report, report),
    )

    assert cycle.duplicate_source_ids == (_HKEL,)
    assert cycle.accounting_complete is False
    assert cycle.release_blocking is True
