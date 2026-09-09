"""Closed policy tests for the role-aware HKEX candidate executor."""

from __future__ import annotations

import copy

import pytest

from tools import hk_v1_source_admission as admission
from tools.hk_v1_hkex_policy import (
    execution_policy,
    execution_policy_fingerprint,
    raw_location_consumption_ceiling,
    recognized_execution_policy,
)

_EXPECTED = {
    "fees_pdfs_per_board": 32,
    "followed_redirect_hop_starts": 512,
    "form_nodes_per_board": 256,
    "form_pdfs_per_board": 256,
    "logical_request_starts": 3_168,
    "minimum_physical_start_interval_seconds": 0.25,
    "name": "HKEX_ROLE_AWARE_2.0.0",
    "one_html_response_bytes": 16_777_216,
    "one_pdf_response_bytes": 67_108_864,
    "physical_request_starts": 3_680,
    "raw_location_admission_octets": 8_192,
    "raw_location_discarded_lookahead_octets": 1,
    "raw_location_retained_prefix_octets": 8_193,
    "redirect_events_globally": 1_024,
    "redirect_events_per_forms_attempt": 2,
    "retained_response_bytes": 68_719_476_736,
    "static_registered_requests": 32,
    "total_elapsed_observation_seconds": 3_600,
    "unique_dynamic_html_requests": 512,
    "unique_dynamic_pdf_requests": 2_624,
    "update_containers_per_board": 64,
    "update_pages_per_board": 1_024,
    "update_pdfs_per_board": 1_024,
}


def test_hkex_role_aware_policy_is_exact_and_fingerprint_bound() -> None:
    """The canonical policy binds every reviewed limit and its derived ceiling."""
    policy = execution_policy()

    assert policy == _EXPECTED
    assert raw_location_consumption_ceiling(policy) == 8_194
    assert recognized_execution_policy(policy, execution_policy_fingerprint()) == (
        "HKEX_ROLE_AWARE_2.0.0"
    )


@pytest.mark.parametrize("field", tuple(_EXPECTED))
def test_every_hkex_policy_field_is_independently_bound(field: str) -> None:
    """Changing any top-level fact must leave the closed recognized set."""
    policy = copy.deepcopy(_EXPECTED)
    value = policy[field]
    if type(value) is int:
        policy[field] = value + 1
    elif type(value) is float:
        policy[field] = value + 1.0
    else:
        assert type(value) is str
        policy[field] = value + "-forged"

    assert recognized_execution_policy(policy, execution_policy_fingerprint()) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("raw_location_admission_octets", 8_193),
        ("raw_location_retained_prefix_octets", 8_192),
        ("raw_location_discarded_lookahead_octets", 0),
    ],
)
def test_raw_location_policy_values_are_not_interchangeable(field: str, value: int) -> None:
    """The transport ceiling cannot replace any independent Location policy field."""
    policy = copy.deepcopy(_EXPECTED)
    policy[field] = value

    with pytest.raises(ValueError, match="HKEX_EXECUTION_POLICY_INVALID"):
        raw_location_consumption_ceiling(policy)


def test_current_hkex_execution_binding_includes_only_the_hkex_policy() -> None:
    """Current HKEX authorization must bind its own policy, unlike literal history."""

    def binding(*, policy_bound: bool | None = None, policy_fingerprint: str | None = None) -> str:
        return admission._execution_binding_fingerprint(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            authority_manifest_fingerprint="sha256:" + "1" * 64,
            source_family="HKEX",
            source_ids=("HK-REG-HKEX-FEES-RULES",),
            observation_cutoff="2026-09-02T00:00:00+08:00",
            allowed_urls=("https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",),
            register_identity=("hrr_test", "2026-09-01.2", "sha256:" + "2" * 64),
            historical_replay=False,
            policy_bound=policy_bound,
            policy_fingerprint=policy_fingerprint,
        )

    current = binding()
    explicit = binding(
        policy_fingerprint=execution_policy_fingerprint(),
    )
    historical_shape = binding(policy_bound=False)

    assert current == explicit
    assert current != historical_shape
