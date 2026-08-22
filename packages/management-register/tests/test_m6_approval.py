"""M6 named-human governance and single-consumption proofs."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from asklegal_management_register_ports import (
    ApprovalConsumption,
    ApprovalError,
    ApprovalErrorCode,
    ApprovalState,
    InMemoryApprovalRegister,
    ManifestSnapshot,
    ReviewerPrincipal,
)

_NOW = "2026-08-16T00:00:00Z"
_LATER = "2026-08-16T01:00:00Z"
_ROLES = frozenset({"PipelineAdministrator"})


def _manifest(identity: str = "1") -> ManifestSnapshot:
    return ManifestSnapshot(
        "pmn_" + identity * 48,
        "sha256:" + identity * 64,
        "srv_" + "a" * 48,
        "2026-08-15T00:00:00Z",
        "2026-08-17T00:00:00Z",
        (("configuration", "1.0.0", "sha256:" + "c" * 64),),
    )


def _principal(*, delegated: bool = True, roles: frozenset[str] = _ROLES) -> ReviewerPrincipal:
    return ReviewerPrincipal("person-1", delegated, roles)


def _register() -> InMemoryApprovalRegister:
    return InMemoryApprovalRegister({"person-1": _ROLES})


def _approve(
    register: InMemoryApprovalRegister, manifest: ManifestSnapshot | None = None
) -> tuple[ManifestSnapshot, str]:
    selected = manifest or _manifest()
    projection = register.decide(
        _principal(), selected, decision="APPROVED", reason="Reviewed", decision_time=_NOW
    )
    return selected, projection.decision.approval_id


def _context(manifest: ManifestSnapshot) -> ApprovalConsumption:
    return ApprovalConsumption(
        manifest.expected_base_serving_state_id,
        manifest.validity_predicates,
        _LATER,
    )


def test_named_delegated_administrator_and_reason_are_mandatory() -> None:
    """Application tokens, self-asserted roles, and empty reasons never decide."""
    register = _register()
    manifest = _manifest()
    for principal in (
        _principal(delegated=False),
        _principal(roles=frozenset()),
        ReviewerPrincipal("unassigned", delegated_human=True, roles=_ROLES),
    ):
        with pytest.raises(ApprovalError) as denied:
            register.decide(
                principal,
                manifest,
                decision="APPROVED",
                reason="Reviewed",
                decision_time=_NOW,
            )
        assert denied.value.code is ApprovalErrorCode.UNAUTHORIZED_PRINCIPAL
    with pytest.raises(ApprovalError) as no_reason:
        register.decide(_principal(), manifest, decision="APPROVED", reason=" ", decision_time=_NOW)
    assert no_reason.value.code is ApprovalErrorCode.REASON_REQUIRED


def test_comment_decision_rejection_and_revocation_are_fingerprint_bound() -> None:
    """Review facts are immutable named-human records over one exact manifest."""
    register = _register()
    manifest = _manifest()
    comment = register.comment(
        _principal(), manifest, section="DIFF", reason="Checked change", recorded_at=_NOW
    )
    assert comment.manifest_fingerprint == manifest.fingerprint
    rejected = register.decide(
        _principal(), manifest, decision="REJECTED", reason="Bad diff", decision_time=_NOW
    )
    assert rejected.state is ApprovalState.REJECTED

    other_register = _register()
    _, approval_id = _approve(other_register, _manifest("2"))
    revoked = other_register.revoke(_principal(), approval_id, reason="Withdrawn", at=_LATER)
    assert revoked.state is ApprovalState.REVOKED
    with pytest.raises(ApprovalError) as unusable:
        other_register.consume(
            approval_id, "lin_" + "1" * 48, _manifest("2"), _context(_manifest("2"))
        )
    assert unusable.value.code is ApprovalErrorCode.APPROVAL_REVOKED


def test_consumption_rechecks_role_manifest_base_predicates_and_validity() -> None:
    """Any material current-fact drift makes the Approval unusable."""
    register = _register()
    manifest, approval_id = _approve(register)
    register.set_roles("person-1", frozenset())
    with pytest.raises(ApprovalError) as removed:
        register.consume(approval_id, "lin_" + "1" * 48, manifest, _context(manifest))
    assert removed.value.code is ApprovalErrorCode.AUTHORITY_REMOVED

    drift_register = _register()
    manifest, approval_id = _approve(drift_register)
    drifted = ManifestSnapshot(
        manifest.manifest_id,
        "sha256:" + "f" * 64,
        manifest.expected_base_serving_state_id,
        manifest.valid_from,
        manifest.valid_until,
        manifest.validity_predicates,
    )
    with pytest.raises(ApprovalError) as drift:
        drift_register.consume(approval_id, "lin_" + "2" * 48, drifted, _context(drifted))
    assert drift.value.code is ApprovalErrorCode.MANIFEST_DRIFT

    invalid_register = _register()
    manifest, approval_id = _approve(invalid_register)
    wrong_base = ApprovalConsumption("srv_" + "b" * 48, manifest.validity_predicates, _LATER)
    with pytest.raises(ApprovalError) as invalid:
        invalid_register.consume(approval_id, "lin_" + "3" * 48, manifest, wrong_base)
    assert invalid.value.code is ApprovalErrorCode.MANIFEST_INVALID
    assert invalid_register.get(approval_id).state is ApprovalState.INVALIDATED


def test_consumption_is_single_use_but_same_lineage_replays_exactly() -> None:
    """One winner consumes; restart of that same lineage reads the same result."""
    register = _register()
    manifest, approval_id = _approve(register)
    first = register.consume(approval_id, "lin_" + "1" * 48, manifest, _context(manifest))
    replay = register.consume(approval_id, "lin_" + "1" * 48, manifest, _context(manifest))
    assert replay == first
    with pytest.raises(ApprovalError) as consumed:
        register.consume(approval_id, "lin_" + "2" * 48, manifest, _context(manifest))
    assert consumed.value.code is ApprovalErrorCode.APPROVAL_CONSUMED


def test_concurrent_distinct_lineages_have_exactly_one_consumer() -> None:
    """The register serializes competing execution lineages atomically."""
    register = _register()
    manifest, approval_id = _approve(register)

    def consume(lineage: str) -> str:
        try:
            register.consume(approval_id, lineage, manifest, _context(manifest))
        except ApprovalError as error:
            return error.code.value
        else:
            return "SUCCESS"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(consume, ("lin_" + "1" * 48, "lin_" + "2" * 48)))
    assert sorted(outcomes) == ["APPROVAL_CONSUMED", "SUCCESS"]
