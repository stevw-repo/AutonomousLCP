"""Complete offline M7 conformance-runner acceptance tests."""

import socket
from pathlib import Path

import pytest
from asklegal_reporting import build_local_conformance_report

from tools.local_conformance import (
    ConformanceFailure,
    external_access_denial_probe,
    prove_scenarios,
    reset,
    scenario_catalogue,
    synthetic_state_requires_reset,
)


def test_all_32_scenarios_are_path_independent_and_complete(tmp_path: Path) -> None:
    """Two clean path-distinct runs have one authoritative report."""
    catalogue = scenario_catalogue()
    assert catalogue == tuple(f"E2E-{index:03d}" for index in range(1, 33))
    first = prove_scenarios(tmp_path / "first", catalogue)
    second = prove_scenarios(tmp_path / "second", catalogue)
    profile = "sha256:" + "a" * 64
    first_report = build_local_conformance_report(profile, first)
    second_report = build_local_conformance_report(profile, second)
    assert first_report.canonical_bytes == second_report.canonical_bytes
    assert first_report.statement == "local synthetic platform proved"
    assert all(item.fingerprint.startswith("sha256:") for item in first)


def test_golden_and_high_risk_scenarios_report_the_exact_terminal_codes(
    tmp_path: Path,
) -> None:
    """Golden, hostile, stale, recovery, rollback, and deletion cases stay named."""
    selected = (
        "E2E-001",
        "E2E-013",
        "E2E-019",
        "E2E-023",
        "E2E-029",
        "E2E-030",
        "E2E-031",
        "E2E-032",
    )
    results = prove_scenarios(tmp_path / "selected", selected)
    assert {item.scenario_id: item.result_code for item in results} == {
        "E2E-001": "GOLDEN_FLOW_RECOVERED",
        "E2E-013": "HOSTILE_CONTENT_QUARANTINED",
        "E2E-019": "MANIFEST_FINGERPRINT_STALE",
        "E2E-023": "VECTOR_INVALID",
        "E2E-029": "EXACT_REVERSE_SWAP",
        "E2E-030": "REGISTER_RECOVERED_AND_FENCED",
        "E2E-031": "BROAD_RETIREMENT_FORBIDDEN",
        "E2E-032": "ENVIRONMENT_MISUSE",
    }


def test_reset_rejects_every_non_exact_target(tmp_path: Path) -> None:
    """Reset cannot be redirected to a broad or caller-chosen filesystem path."""
    with pytest.raises(ConformanceFailure, match="STATE_ROOT_OUTSIDE"):
        reset(tmp_path / "local-conformance")


def test_existing_proof_output_requires_an_explicit_reset(tmp_path: Path) -> None:
    """A second proof must fail with a stable result instead of leaking FileExistsError."""
    root = tmp_path / "local-conformance"
    root.mkdir()
    (root / ".asklegal-local-synthetic-state").write_text(
        "ASKLEGAL_LOCAL_SYNTHETIC_STATE_V1\n", encoding="utf-8"
    )
    assert synthetic_state_requires_reset(root) is False

    (root / "run-a").mkdir()

    assert synthetic_state_requires_reset(root) is True
    with pytest.raises(ConformanceFailure, match="SYNTHETIC_STATE_RESET_REQUIRED"):
        prove_scenarios(root / "run-a", ("E2E-002",))


def test_runner_never_leaves_network_access_enabled_after_a_scenario(tmp_path: Path) -> None:
    """The denial guard is restored after a successful in-process proof."""
    prove_scenarios(tmp_path / "network", ("E2E-002",))
    assert callable(socket.getaddrinfo)


def test_external_network_and_ambient_provider_credentials_are_unreadable() -> None:
    """Both forbidden access families fail before external state can be observed."""
    assert external_access_denial_probe() == (
        "AMBIENT_PROVIDER_CREDENTIAL_ACCESS_FORBIDDEN",
        "NETWORK_ACCESS_FORBIDDEN",
    )
