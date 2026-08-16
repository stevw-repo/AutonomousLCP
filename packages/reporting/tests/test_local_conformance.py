"""M7 deterministic report contract tests."""

import pytest
from asklegal_reporting import ScenarioResult, build_local_conformance_report


def _results() -> tuple[ScenarioResult, ...]:
    return tuple(
        ScenarioResult(
            f"E2E-{index:03d}",
            "EXPECTED_RESULT_PROVED",
            "Synthetic boundary behaved exactly as declared.",
            (f"art_{index:048x}",),
            1,
            0,
        )
        for index in range(1, 33)
    )


def test_complete_report_is_byte_reproducible() -> None:
    profile = "sha256:" + "a" * 64
    first = build_local_conformance_report(profile, _results())
    second = build_local_conformance_report(profile, tuple(reversed(_results())))
    assert first == second
    assert first.statement == "local synthetic platform proved"
    assert len(first.scenarios) == 32


def test_incomplete_or_drifted_report_fails_closed() -> None:
    with pytest.raises(ValueError, match="every scenario"):
        build_local_conformance_report("sha256:" + "a" * 64, _results()[:-1])
    with pytest.raises(ValueError, match="drift"):
        ScenarioResult(
            "E2E-001",
            "PASS",
            "summary",
            (),
            0,
            0,
            "sha256:" + "f" * 64,
        )
