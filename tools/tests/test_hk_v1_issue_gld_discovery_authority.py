"""Focused no-effect tests for GLD discovery-authority issuance."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from asklegal_acquisition_worker.gld_operator import preflight_gld_operator
from asklegal_evidence_vault import LocalImmutableVault, VaultName

from tools.hk_v1_issue_gld_discovery_authority import (
    GldDiscoveryAuthorityError,
    issue_gld_discovery_authority,
    write_exact,
)

_CYCLE = "cyc_" + "1" * 64
_CUTOFF = "2026-09-09T11:00:00+00:00"


def _times() -> tuple[str, str]:
    now = datetime.now(UTC).replace(microsecond=0)
    return (
        now.isoformat(),
        now.replace(year=now.year + 1).isoformat(),
    )


def test_issued_authority_passes_owning_exact_preflight(tmp_path: Path) -> None:
    """The issued receipt is exactly the one the GLD operator admits."""
    authorized_at, expires_at = _times()
    raw = issue_gld_discovery_authority(
        cycle_id=_CYCLE,
        observation_cutoff=_CUTOFF,
        named_authorizer="Task 10 standing authority",
        authorized_at=authorized_at,
        expires_at=expires_at,
    )
    authority = (tmp_path / "authority.json").resolve()
    authority.write_bytes(raw)
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    report = preflight_gld_operator(
        {
            "ASKLEGAL_HK_V1_GLD_OPERATOR_MODE": "DISCOVER_CONTRACT",
            "ASKLEGAL_HK_V1_GLD_CHALLENGE_AUTHORITY_RECEIPT": str(authority),
            "ASKLEGAL_HK_V1_GLD_START_DATE": "2026-09-09",
        },
        cycle_id=_CYCLE,
        observation_cutoff=_CUTOFF,
        vault=vault,
    )
    assert report.authority_admitted
    assert report.observation_executable
    assert report.blocker_code == "NONE"


def test_authority_rejects_expired_or_malformed_cycle() -> None:
    """A stale receipt or caller-shaped lineage cannot be issued."""
    with pytest.raises(GldDiscoveryAuthorityError):
        issue_gld_discovery_authority(
            cycle_id="cyc_invalid",
            observation_cutoff=_CUTOFF,
            named_authorizer="Task 10 standing authority",
            authorized_at="2026-09-08T00:00:00+00:00",
            expires_at="2026-09-08T01:00:00+00:00",
        )


def test_existing_authority_drift_is_not_overwritten(tmp_path: Path) -> None:
    """A retained authority is immutable across operator restart."""
    authorized_at, expires_at = _times()
    raw = issue_gld_discovery_authority(
        cycle_id=_CYCLE,
        observation_cutoff=_CUTOFF,
        named_authorizer="Task 10 standing authority",
        authorized_at=authorized_at,
        expires_at=expires_at,
    )
    output = (tmp_path / "authority.json").resolve()
    write_exact(output, raw)
    output.write_bytes(raw + b"\n")
    with pytest.raises(GldDiscoveryAuthorityError, match="OUTPUT_DRIFT"):
        write_exact(output, raw)
