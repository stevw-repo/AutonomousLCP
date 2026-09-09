"""Exact owner-derived Gate C live release-accounting tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from asklegal_corpus import CorpusRelease, CorpusReleaseInput, freeze_corpus_release

from tools.hk_v1_admission_release_evidence import (
    SCOPES,
    LiveReleaseAccountingError,
    build_live_release_accounting,
    parse_live_release_accounting,
)


def _releases() -> tuple[CorpusRelease, ...]:
    return tuple(
        freeze_corpus_release(
            CorpusReleaseInput(
                scope,
                "2026-09-08T12:00:00+08:00",
                (f"evidence/{index}",),
                (f"validation/{index}",),
                zero_record_justification_refs=(f"zero/{index}",),
            ),
            (),
        )
        for index, scope in enumerate(SCOPES)
    )


def test_four_exact_corpus_releases_round_trip() -> None:
    """Accounting is derived from CorpusRelease bodies, not caller counts."""
    releases = _releases()
    content = build_live_release_accounting(
        releases,
        proposal_fingerprint="sha256:" + "1" * 64,
    )

    parsed = parse_live_release_accounting(content)

    assert parsed.total_record_count == 0
    assert len(parsed.release_fingerprints) == 4


def test_forged_release_fingerprint_never_builds_accounting() -> None:
    """A dataclass-shaped release with drifted owner fingerprint is rejected."""
    releases = list(_releases())
    releases[0] = replace(releases[0], release_fingerprint="sha256:" + "f" * 64)

    with pytest.raises(LiveReleaseAccountingError):
        build_live_release_accounting(
            tuple(releases),
            proposal_fingerprint="sha256:" + "1" * 64,
        )
