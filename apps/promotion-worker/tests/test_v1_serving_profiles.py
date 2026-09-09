"""Task 8 exact two-family proposal and serving-profile preflight tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_promotion import (
    HKV1TargetMember,
    PromotionError,
    PromotionErrorCode,
    verify_hk_v1_target_membership,
)

_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)


def proposal_fixture(
    *,
    model_profile_fingerprint: str = "sha256:" + "2" * 64,
    embedding_profile_fingerprint: str = "sha256:" + "3" * 64,
) -> bytes:
    """Return one canonical frozen two-family proposal for promotion tests."""
    body = {
        "schema_id": "asklegal.hk-v1-two-family-proposal-manifest/v1",
        "status": "FROZEN_PROPOSAL_READY_FOR_REVIEW",
        "observation_cutoff": "2026-09-06T00:00:00Z",
        "included_material_families": ["CASES", "LEGISLATION"],
        "scope_ids": list(_SCOPES),
        "explicit_exclusions": ["HKEX_REGULATORY_POST_V1", "HK-PRINCIPLES"],
        "coverage_report_fingerprint": "sha256:" + "1" * 64,
        "acquisition_manifests": [],
        "prepared_batches": [],
        "model_profile_fingerprint": model_profile_fingerprint,
        "embedding_profile_fingerprint": embedding_profile_fingerprint,
        "model_capability_evidence_ref": "model/evidence.json",
        "embedding_capability_evidence_ref": "embedding/evidence.json",
        "model_invocation_count": 0,
        "embedding_invocation_count": 0,
        "release_state": "WITHHELD_PENDING_NAMED_HUMAN_REVIEW",
        "completeness_fingerprint": "sha256:" + "4" * 64,
    }
    fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
    return canonicalize(checked_json_value({**body, "fingerprint": fingerprint}))


def _members() -> tuple[HKV1TargetMember, ...]:
    return tuple(
        HKV1TargetMember(
            f"rec-{index}",
            scope,
            "CASES" if scope.startswith("HK-CASE") else "LEGISLATION",
        )
        for index, scope in enumerate(_SCOPES, start=1)
    )


def test_exact_two_family_membership_is_bound_to_the_frozen_proposal() -> None:
    """Removing a scope or adding an unapproved record must fail target preflight."""
    result = verify_hk_v1_target_membership(
        proposal_fixture(), _members(), tuple(item.record_id for item in _members())
    )

    assert result.scope_ids == _SCOPES
    assert result.material_families == ("CASES", "LEGISLATION")
    assert result.proposal_fingerprint.startswith("sha256:")


@pytest.mark.parametrize("mutation", ["HKEX", "MISSING_SCOPE", "UNKNOWN_RECORD", "DUPLICATE"])
def test_current_hkex_or_inexact_membership_is_rejected_before_effects(mutation: str) -> None:
    """Current HKEX and every incomplete or ambiguous target composition are forbidden."""
    members = list(_members())
    expected = tuple(item.record_id for item in members)
    if mutation == "HKEX":
        members[-1] = HKV1TargetMember("rec-4", "HKEX_REGULATORY_POST_V1", "REGULATORY")
    elif mutation == "MISSING_SCOPE":
        members = members[:1]
        expected = expected[:1]
    elif mutation == "UNKNOWN_RECORD":
        members[-1] = replace(members[-1], record_id="rec-not-approved")
    else:
        members[-1] = replace(members[-1], record_id=members[0].record_id)

    with pytest.raises(PromotionError) as failure:
        verify_hk_v1_target_membership(proposal_fixture(), tuple(members), expected)

    assert failure.value.code is PromotionErrorCode.INVENTORY_MISMATCH


def test_historical_hkex_vocabulary_outside_members_does_not_change_target_scope() -> None:
    """The explicit post-V1 exclusion remains reviewable without becoming a member."""
    result = verify_hk_v1_target_membership(
        proposal_fixture(), _members(), tuple(item.record_id for item in _members())
    )

    assert "HKEX_REGULATORY_POST_V1" in result.explicit_exclusions
    assert all("HKEX" not in item.scope_id for item in result.members)


@pytest.mark.parametrize("omitted_scope", _SCOPES[1:])
def test_each_legislation_scope_requires_a_member_or_explicit_zero_record_disposition(
    omitted_scope: str,
) -> None:
    """A two-family label cannot hide one absent Legislation scope."""
    members = tuple(item for item in _members() if item.scope_id != omitted_scope)
    expected = tuple(item.record_id for item in members)

    with pytest.raises(PromotionError) as failure:
        verify_hk_v1_target_membership(proposal_fixture(), members, expected)

    assert failure.value.code is PromotionErrorCode.INVENTORY_MISMATCH
    admitted = verify_hk_v1_target_membership(
        proposal_fixture(),
        members,
        expected,
        zero_record_scope_ids=(omitted_scope,),
    )
    assert admitted.zero_record_scope_ids == (omitted_scope,)
