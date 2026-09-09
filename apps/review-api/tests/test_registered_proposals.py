"""Registered immutable proposal projection proofs."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_application_runtime import HKV1ScopeDispositionProjection
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import (
    ExactObjectReference,
    LocalImmutableVault,
    RetentionProfile,
    VaultName,
)
from asklegal_management_register import ReviewReadyProposalRow
from asklegal_review_api.registered_proposals import (
    ProposalProjectionError,
    ProposalProjectionErrorCode,
    RegisteredReviewProjectionStore,
    freeze_hk_v1_review_readiness,
    hk_v1_review_readiness_bytes,
    promotion_facts_from_bytes,
)

from tools.tests.proposal_member_fixture import semantic_proposal_fixture

_ROLE_PATHS = {
    "CHANGE_INVENTORY": "change-inventory/change-inventory.json",
    "CORPUS_RELEASES": "corpus-releases/releases.json",
    "COST_AND_CAPACITY": "cost-and-capacity/admission.json",
    "COVERAGE_STATUS": "coverage-status/coverage.json",
    "DESIRED_STATE_INVENTORIES": "desired-state-inventories/inventories.json",
    "PROMOTION_MANIFEST": "promotion-manifest/promotion-manifest.json",
    "RECORD_TRACEABILITY": "record-traceability/lookup.json",
    "RECOVERY_READINESS": "recovery-readiness/readiness.json",
    "REVIEW_REPORT": "review-report/report.json",
    "SERVING_STATE_DEFINITION": "serving-state-definition/definition.json",
    "VALIDATION": "validation/results.json",
}
_RETENTION = RetentionProfile("proposal-v1", "2036-01-01T00:00:00Z")


class Rows:
    """Deterministic least-privilege proposal source."""

    def __init__(self, rows: tuple[ReviewReadyProposalRow, ...]) -> None:
        """Freeze the rows returned on every read."""
        self.rows = rows

    def review_ready_proposals(self) -> tuple[ReviewReadyProposalRow, ...]:
        """Return the configured immutable rows."""
        return self.rows


class ReadinessRefs:
    """Register-projected exact retained Task 8 readiness references."""

    def __init__(self, references: dict[str, ExactObjectReference]) -> None:
        self.references = references

    def readiness_reference(
        self, proposal_package_id: str, proposal_fingerprint: str
    ) -> ExactObjectReference | None:
        del proposal_fingerprint
        return self.references.get(proposal_package_id)


@pytest.mark.parametrize("drift", ["CAPABILITY", "INPUT", "COMPENSATION", "SEQUENCE"])
def test_review_independently_rejects_action_authority_drift(drift: str) -> None:
    """Review does not rely on Control's manifest-action validation."""
    fixture = semantic_proposal_fixture()
    document = parse_json_bytes(fixture.contents["PROMOTION_MANIFEST"], max_bytes=1_000_000)
    assert isinstance(document, dict)
    actions = document["actions"]
    assert isinstance(actions, list)
    action = actions[0]
    assert isinstance(action, dict)
    if drift == "CAPABILITY":
        action["required_capability"] = "MANAGE_BACKUP"
    elif drift == "INPUT":
        inputs = action["input_refs"]
        assert isinstance(inputs, list)
        action["input_refs"] = inputs[:1]
    elif drift == "COMPENSATION":
        action["compensation"] = {"mode": "IMPROVISED"}
    else:
        action["sequence"] = 2
    content = canonicalize(document)
    manifest_fingerprint = f"sha256:{sha256(content).hexdigest()}"
    manifest_id = "pmn_" + sha256(manifest_fingerprint.encode()).hexdigest()[:48]

    with pytest.raises(ProposalProjectionError) as error:
        promotion_facts_from_bytes(
            content,
            manifest_id=manifest_id,
            manifest_fingerprint=manifest_fingerprint,
        )

    assert error.value.code is ProposalProjectionErrorCode.PACKAGE


def _reference(reference: ExactObjectReference) -> dict[str, JsonValue]:
    return {
        "byte_length": reference.byte_length,
        "fingerprint": reference.fingerprint,
        "logical_key": reference.logical_key,
        "vault": reference.vault.value,
        "version_id": reference.version_id,
    }


def _store_proposal(
    vault: LocalImmutableVault,
    digit: str,
    *,
    invalid_inventory: bool = False,
    semantic_placeholder: bool = False,
    two_family: bool = False,
) -> tuple[ReviewReadyProposalRow, tuple[ExactObjectReference, ...]]:
    package_id = "ppk_" + digit * 48
    fixture = semantic_proposal_fixture(
        digit=digit,
        observation_cutoff="2026-08-21T12:00:00Z",
        valid_from="2026-08-21T00:00:00Z",
        valid_until="2026-08-22T00:00:00Z",
        base_serving_state_id="srv_" + "a" * 48,
        candidate_serving_state_id="srv_" + "b" * 48,
        candidate_serving_state_fingerprint="sha256:" + "b" * 64,
        embedding_profile_fingerprint="sha256:" + "e" * 64,
        validity_predicates=(
            (
                ("HK_V1_TWO_FAMILY_PROPOSAL", "1.0.0", "sha256:" + "d" * 64),
                ("configuration", "1.0.0", "sha256:" + "f" * 64),
            )
            if two_family
            else (("configuration", "1.0.0", "sha256:" + "f" * 64),)
        ),
    )
    promotion_manifest_id = fixture.bindings.promotion_manifest_id
    member_rows: list[dict[str, JsonValue]] = []
    inventory: list[dict[str, JsonValue]] = []
    references: list[ExactObjectReference] = []
    for role, path in sorted(_ROLE_PATHS.items()):
        content = (
            canonicalize(checked_json_value({"role": role}))
            if semantic_placeholder and role == "CHANGE_INVENTORY"
            else fixture.contents[role]
        )
        reference = vault.conditional_create(
            f"proposal-packages/{package_id}/members/{path}",
            content,
            _RETENTION,
        ).reference
        references.append(reference)
        member_rows.append({"path": path, "reference": _reference(reference), "role": role})
        inventory.append(
            {
                "byte_size": len(content),
                "fingerprint": (
                    "sha256:" + "f" * 64
                    if invalid_inventory and role == "CHANGE_INVENTORY"
                    else reference.fingerprint
                ),
                "media_type": "application/json",
                "path": path,
                "role": role,
            }
        )
    roles = tuple(sorted(_ROLE_PATHS))
    promotion_reference = references[roles.index("PROMOTION_MANIFEST")]
    review_reference = references[roles.index("REVIEW_REPORT")]
    manifest_bytes = canonicalize(
        checked_json_value(
            {
                "artifact_inventory": inventory,
                "base_serving_state_ref": {
                    "fingerprint": "sha256:" + "a" * 64,
                    "ref_id": "srv_" + "a" * 48,
                    "ref_type": "SERVING_STATE",
                },
                "candidate_serving_state_ref": {
                    "fingerprint": "sha256:" + "b" * 64,
                    "ref_id": "srv_" + "b" * 48,
                    "ref_type": "SERVING_STATE",
                },
                "created_at": "2026-08-21T12:00:00Z",
                "immutable": True,
                "observation_cutoff": "2026-08-21T12:00:00Z",
                "promotion_manifest_ref": {
                    "fingerprint": promotion_reference.fingerprint,
                    "ref_id": promotion_manifest_id,
                    "ref_type": "PROMOTION_MANIFEST",
                },
                "proposal_package_id": package_id,
                "review_report_ref": {
                    "fingerprint": review_reference.fingerprint,
                    "ref_id": "art_" + digit * 48,
                    "ref_type": "ARTIFACT",
                },
                "schema_id": "asklegal.proposal-package-manifest",
                "schema_version": "1.0.0",
                "status": "REVIEW_READY",
            }
        )
    )
    manifest_reference = vault.conditional_create(
        f"proposal-packages/{package_id}/proposal-manifest.json",
        manifest_bytes,
        _RETENTION,
    ).reference
    traceability_rows: list[dict[str, JsonValue]] = []
    traceability_references: list[ExactObjectReference] = []
    for path in sorted(fixture.traceability_shards):
        reference = vault.conditional_create(
            f"proposal-packages/{package_id}/traceability/{path}",
            fixture.traceability_shards[path],
            _RETENTION,
        ).reference
        traceability_references.append(reference)
        traceability_rows.append({"path": path, "reference": _reference(reference)})
    receipt = canonicalize(
        checked_json_value(
            {
                "manifest_reference": _reference(manifest_reference),
                "members": member_rows,
                "package_fingerprint": manifest_reference.fingerprint,
                "package_id": package_id,
                "promotion_manifest_fingerprint": promotion_reference.fingerprint,
                "promotion_manifest_id": promotion_manifest_id,
                "traceability_shards": traceability_rows,
            }
        )
    )
    row = ReviewReadyProposalRow(
        package_id,
        receipt,
        sha256(receipt).digest(),
        1,
        "2026-08-21T12:00:00",
    )
    return row, (manifest_reference, *references, *traceability_references)


def _with_decision(
    row: ReviewReadyProposalRow,
    *,
    decision: str = "APPROVED",
) -> ReviewReadyProposalRow:
    receipt = parse_json_bytes(row.receipt_bytes, max_bytes=1_000_000)
    assert isinstance(receipt, dict)
    promotion_manifest_id = receipt["promotion_manifest_id"]
    promotion_fingerprint = receipt["promotion_manifest_fingerprint"]
    assert isinstance(promotion_manifest_id, str)
    assert isinstance(promotion_fingerprint, str)
    approval_id = (
        "apr_"
        + sha256(
            chr(31).join((promotion_manifest_id, promotion_fingerprint, decision)).encode()
        ).hexdigest()[:48]
    )
    content = canonicalize(
        checked_json_value(
            {
                "approval_id": approval_id,
                "authority_evidence_ref": {
                    "fingerprint": "sha256:" + "2" * 64,
                    "ref_id": "evi_" + "2" * 48,
                    "ref_type": "EVIDENCE",
                },
                "decision": decision,
                "decision_time": "2026-08-21T12:01:00Z",
                "expected_base_serving_state_ref": {
                    "fingerprint": "sha256:" + "a" * 64,
                    "ref_id": "srv_" + "a" * 48,
                    "ref_type": "SERVING_STATE",
                },
                "governance_policy_state": "CONFIGURED",
                "immutable": True,
                "promotion_manifest_ref": {
                    "fingerprint": promotion_fingerprint,
                    "ref_id": promotion_manifest_id,
                    "ref_type": "PROMOTION_MANIFEST",
                },
                "reason": "Reviewed complete immutable proposal",
                "reviewer_identity_ref": {
                    "fingerprint": "sha256:" + "1" * 64,
                    "ref_id": "act_" + "1" * 48,
                    "ref_type": "ACTOR",
                },
                "schema_id": "asklegal.approval-decision",
                "schema_version": "1.1.0",
                "valid_from": "2026-08-21T00:00:00Z",
                "validity_condition_refs": [
                    {
                        "contract_id": "configuration",
                        "fingerprint": "sha256:" + "f" * 64,
                        "version": "1.0.0",
                    }
                ],
            }
        )
    )
    return replace(
        row,
        decision_bytes=content,
        decision_fingerprint=sha256(content).digest(),
        review_version=1,
        decision_event_type=(
            "PROPOSAL_APPROVED" if decision == "APPROVED" else "PROPOSAL_REJECTED"
        ),
        decision_at="2026-08-21T12:01:00",
    )


def test_registered_projection_rereads_complete_package_and_has_stable_generation(
    tmp_path: Path,
) -> None:
    """Only one canonical fully re-read package becomes Review-visible."""
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    row, _references = _store_proposal(vault, "1")
    store = RegisteredReviewProjectionStore(Rows((row,)), vault)

    snapshot, proposals = store.load()
    detail = store.detail(row.proposal_package_id)

    assert snapshot.startswith("sha256:")
    assert proposals[0].proposal_id == row.proposal_package_id
    assert proposals[0].status == "REVIEW_READY"
    assert detail is not None
    assert detail.package_fingerprint.startswith("sha256:")
    assert detail.observation_cutoff == "2026-08-21T12:00:00Z"
    assert detail.base_serving_state_id == "srv_" + "a" * 48
    assert detail.candidate_serving_state_id == "srv_" + "b" * 48
    assert tuple(item.role for item in detail.artifacts) == tuple(sorted(_ROLE_PATHS))
    assert all(item.media_type == "application/json" for item in detail.artifacts)
    assert all(item.byte_length > 0 for item in detail.artifacts)
    assert store.load() == (snapshot, proposals)
    assert store.check() is True


def test_two_family_registered_projection_requires_retained_readiness_readback(
    tmp_path: Path,
) -> None:
    """A registered two-family proposal is invisible without its exact Task 8 artifact."""
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    row, _references = _store_proposal(vault, "a", two_family=True)
    with pytest.raises(ProposalProjectionError):
        RegisteredReviewProjectionStore(Rows((row,)), vault).load()
    readiness = freeze_hk_v1_review_readiness(
        tuple(
            HKV1ScopeDispositionProjection(
                scope,
                "NO_CHANGE"
                if scope
                in {
                    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                    "HK-LEG-SUBSIDIARY",
                }
                else "COMPLETE",
                0,
            )
            for scope in (
                "HK-CASE-BINDING-POST-1997",
                "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                "HK-LEG-ORDINANCES",
                "HK-LEG-SUBSIDIARY",
            )
        ),
        ("Cases begin on 1997-07-01.", "HKEX is outside V1."),
        "task-8/evaluation/model.json",
        "task-8/evaluation/retrieval.json",
        "sha256:" + "6" * 64,
        "sha256:" + "7" * 64,
        "sha256:" + "8" * 64,
        "synthetic-v1",
        "sha256:" + "3" * 64,
        (
            ("rec_" + "1" * 48, "HK-CASE-BINDING-POST-1997", "CASES"),
            ("rec_" + "2" * 48, "HK-LEG-ORDINANCES", "LEGISLATION"),
        ),
        (
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
            "HK-LEG-SUBSIDIARY",
        ),
        "asklegal-dev-hkg-20260906-candidate001",
        "task-8/backup/native.json",
        "task-8/backup/recovery.json",
        "srv_" + "8" * 48,
        "sha256:" + "d" * 64,
    )
    reference = vault.conditional_create(
        f"proposal-packages/{row.proposal_package_id}/task-8/review-readiness.json",
        hk_v1_review_readiness_bytes(readiness),
        _RETENTION,
    ).reference
    store = RegisteredReviewProjectionStore(
        Rows((row,)), vault, ReadinessRefs({row.proposal_package_id: reference})
    )

    detail = store.detail(row.proposal_package_id)

    assert detail is not None
    assert detail.hk_v1_readiness == readiness


def test_registered_projection_fails_closed_on_receipt_or_register_drift(
    tmp_path: Path,
) -> None:
    """Fingerprint, canonical form, identity, and version drift stay invisible."""
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    row, _references = _store_proposal(vault, "2")
    bad_hash = replace(row, receipt_fingerprint=b"x" * 32)
    noncanonical = replace(
        row,
        receipt_bytes=row.receipt_bytes + b"\n",
        receipt_fingerprint=sha256(row.receipt_bytes + b"\n").digest(),
    )
    wrong_identity = replace(row, proposal_package_id="ppk_" + "3" * 48)

    assert RegisteredReviewProjectionStore(Rows((bad_hash,)), vault).check() is False
    assert RegisteredReviewProjectionStore(Rows((noncanonical,)), vault).check() is False
    assert (
        RegisteredReviewProjectionStore(
            Rows((replace(row, authoritative_version=2),)), vault
        ).check()
        is False
    )
    assert RegisteredReviewProjectionStore(Rows((wrong_identity,)), vault).check() is False


def test_registered_projection_rejects_member_or_root_inventory_tamper(tmp_path: Path) -> None:
    """Changed bytes and a self-consistent but false root inventory both fail closed."""
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    row, references = _store_proposal(vault, "4")
    vault.inject_corruption(references[1], b"changed")
    store = RegisteredReviewProjectionStore(Rows((row,)), vault)

    assert store.check() is False
    with pytest.raises(ProposalProjectionError, match=ProposalProjectionErrorCode.READ.value):
        store.load()

    other_vault = LocalImmutableVault(tmp_path / "other-primary", VaultName.PRIMARY)
    invalid_row, _other_references = _store_proposal(other_vault, "5", invalid_inventory=True)
    invalid = RegisteredReviewProjectionStore(Rows((invalid_row,)), other_vault)
    assert invalid.check() is False
    with pytest.raises(ProposalProjectionError, match=ProposalProjectionErrorCode.INVENTORY.value):
        invalid.load()

    semantic_vault = LocalImmutableVault(tmp_path / "semantic-primary", VaultName.PRIMARY)
    semantic_row, _semantic_references = _store_proposal(
        semantic_vault,
        "9",
        semantic_placeholder=True,
    )
    semantic = RegisteredReviewProjectionStore(Rows((semantic_row,)), semantic_vault)
    assert semantic.check() is False
    with pytest.raises(ProposalProjectionError, match=ProposalProjectionErrorCode.PACKAGE.value):
        semantic.load()


def test_registered_projection_independently_rereads_traceability_shards(
    tmp_path: Path,
) -> None:
    """Review refuses a valid root and members when one transitive shard is corrupt."""
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    row, references = _store_proposal(vault, "3")
    vault.inject_corruption(references[-1], b"changed")
    store = RegisteredReviewProjectionStore(Rows((row,)), vault)

    assert store.check() is False
    with pytest.raises(ProposalProjectionError, match=ProposalProjectionErrorCode.READ.value):
        store.load()


def test_registered_projection_rejects_duplicate_or_out_of_order_rows(tmp_path: Path) -> None:
    """A non-exact register generation cannot produce unstable pagination."""
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    higher, _higher_references = _store_proposal(vault, "7")
    lower, _lower_references = _store_proposal(vault, "6")

    assert RegisteredReviewProjectionStore(Rows((higher, higher)), vault).check() is False
    assert RegisteredReviewProjectionStore(Rows((higher, lower)), vault).check() is False


def test_registered_projection_reconstructs_and_verifies_named_human_decision(
    tmp_path: Path,
) -> None:
    """Restarted Review exposes only a fully bound canonical Approval decision."""
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    ready, _references = _store_proposal(vault, "8")
    row = _with_decision(ready)
    store = RegisteredReviewProjectionStore(Rows((row,)), vault)

    _snapshot, proposals = store.load()
    detail = store.detail(row.proposal_package_id)

    assert proposals[0].status == "APPROVED"
    assert proposals[0].review_version == 1
    assert detail is not None
    assert detail.decision is not None
    assert detail.decision.decision == "APPROVED"
    assert detail.decision.approval_id.startswith("apr_")
    assert detail.decision.reviewer_identity_id == "act_" + "1" * 48
    assert detail.decision.authority_evidence_id == "evi_" + "2" * 48
    assert store.approved(detail.decision.approval_id) == detail
    assert store.approved("apr_" + "0" * 48) is None

    rejected = _with_decision(ready, decision="REJECTED")
    rejected_store = RegisteredReviewProjectionStore(Rows((rejected,)), vault)
    rejected_detail = rejected_store.detail(row.proposal_package_id)
    assert rejected_detail is not None
    assert rejected_detail.decision is not None
    assert rejected_store.approved(rejected_detail.decision.approval_id) is None

    tampered = replace(row, decision_fingerprint=b"x" * 32)
    assert RegisteredReviewProjectionStore(Rows((tampered,)), vault).check() is False


def test_registered_projection_requires_the_primary_vault(tmp_path: Path) -> None:
    """Review cannot silently read proposal bytes from the recovery boundary."""
    recovery = LocalImmutableVault(tmp_path / "recovery", VaultName.RECOVERY)
    with pytest.raises(ProposalProjectionError, match=ProposalProjectionErrorCode.REFERENCE.value):
        RegisteredReviewProjectionStore(Rows(()), recovery)
