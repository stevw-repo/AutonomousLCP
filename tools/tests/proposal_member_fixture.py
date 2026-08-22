"""Deterministic semantically complete proposal members shared by local tests."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from asklegal_contracts import ProposalMemberBindings, canonicalize
from asklegal_contracts.json_types import checked_json_value


@dataclass(frozen=True, slots=True)
class ProposalMemberFixture:
    """One coherent eleven-member proposal and its root authority bindings."""

    contents: dict[str, bytes]
    bindings: ProposalMemberBindings
    coverage_manifest_id: str
    desired_state_inventory_id: str


def _canonical(value: object) -> bytes:
    return canonicalize(checked_json_value(value))


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def semantic_proposal_fixture(  # noqa: PLR0913
    *,
    digit: str = "1",
    observation_cutoff: str = "2026-08-22T00:00:00Z",
    valid_from: str | None = None,
    valid_until: str = "2026-08-23T00:00:00Z",
    base_serving_state_id: str | None = None,
    candidate_serving_state_id: str | None = None,
    candidate_serving_state_fingerprint: str | None = None,
    embedding_profile_fingerprint: str | None = None,
    validity_predicates: tuple[tuple[str, str, str], ...] | None = None,
    capability_enabled: bool = False,
) -> ProposalMemberFixture:
    """Build one small but semantically complete V1 proposal member set."""
    base_id = base_serving_state_id or "srv_" + "b" * 48
    candidate_id = candidate_serving_state_id or "srv_" + "c" * 48
    candidate_fingerprint = candidate_serving_state_fingerprint or "sha256:" + "c" * 64
    embedding_fingerprint = embedding_profile_fingerprint or "sha256:" + "f" * 64
    predicates = validity_predicates or (("configuration", "1.0.0", "sha256:" + "a" * 64),)
    effective_valid_from = valid_from or observation_cutoff
    scope_id = "rsc_" + digit * 48
    release_id = "rel_" + digit * 48
    record_id = "rec_" + digit * 48
    desired_id = "dsi_" + digit * 48
    desired_fingerprint = "sha256:" + digit * 64
    evidence_ref = "evi_" + digit * 48
    validation_ref = "val_" + digit * 48
    coverage = _canonical(
        {
            "observation_cutoff": observation_cutoff,
            "scopes": [
                {
                    "gap_refs": list[str](),
                    "last_verified_at": observation_cutoff,
                    "quarantine_refs": list[str](),
                    "scope_id": scope_id,
                    "source_failure_refs": list[str](),
                    "status": "CURRENT",
                    "warning": "NO_COVERAGE_WARNING",
                }
            ],
            "serving_state_id": candidate_id,
        }
    )
    coverage_fingerprint = _fingerprint(coverage)
    coverage_id = _stable_id("csm", candidate_id, coverage_fingerprint)
    promotion = _canonical(
        {
            "action_ids": ["BUILD_TARGET"],
            "base_serving_state_id": base_id,
            "batch_size": 1,
            "candidate_serving_state_fingerprint": candidate_fingerprint,
            "candidate_serving_state_id": candidate_id,
            "capability_enabled": capability_enabled,
            "coverage_fingerprint": coverage_fingerprint,
            "desired_state_fingerprint": desired_fingerprint,
            "embedding_profile_fingerprint": embedding_fingerprint,
            "environment": "dev",
            "exact_retirement_target_ids": list[str](),
            "freeze_date": observation_cutoff[:10].replace("-", ""),
            "jurisdiction": "hkg",
            "project_id": f"project{digit}",
            "rollback_serving_state_id": base_id,
            "valid_from": effective_valid_from,
            "valid_until": valid_until,
            "validity_predicates": [list(item) for item in predicates],
        }
    )
    promotion_fingerprint = _fingerprint(promotion)
    promotion_id = _stable_id("pmn", promotion_fingerprint)
    validation_evidence = [evidence_ref, validation_ref]
    contents = {
        "CHANGE_INVENTORY": _canonical(
            {
                "additions": [record_id],
                "carried_forward": list[str](),
                "observation_cutoff": observation_cutoff,
                "replacements": list[str](),
                "retirements": list[str](),
                "unchanged": list[str](),
                "withholdings": list[str](),
            }
        ),
        "CORPUS_RELEASES": _canonical(
            {
                "observation_cutoff": observation_cutoff,
                "releases": [
                    {
                        "evidence_refs": [evidence_ref],
                        "observation_cutoff": observation_cutoff,
                        "record_ids": [record_id],
                        "release_id": release_id,
                        "scope_id": scope_id,
                        "validation_refs": [validation_ref],
                    }
                ],
            }
        ),
        "COST_AND_CAPACITY": _canonical(
            {
                "batch_size": 1,
                "embedding_profile_fingerprint": embedding_fingerprint,
                "estimated_cost_microunits": 1,
                "record_count": 1,
                "result": "PASS",
            }
        ),
        "COVERAGE_STATUS": coverage,
        "DESIRED_STATE_INVENTORIES": _canonical(
            {
                "inventory_fingerprint": desired_fingerprint,
                "inventory_id": desired_id,
                "observation_cutoff": observation_cutoff,
                "record_ids": [record_id],
                "scope_releases": [[scope_id, release_id]],
            }
        ),
        "PROMOTION_MANIFEST": promotion,
        "RECORD_TRACEABILITY": _canonical(
            {
                "observation_cutoff": observation_cutoff,
                "records": [
                    {
                        "artifact_ref": "art_" + digit * 48,
                        "evidence_refs": [evidence_ref],
                        "record_id": record_id,
                        "release_id": release_id,
                        "scope_id": scope_id,
                        "serving_payload_fingerprint": "sha256:" + "9" * 64,
                    }
                ],
            }
        ),
        "RECOVERY_READINESS": _canonical(
            {
                "candidate_serving_state_id": candidate_id,
                "predecessor_retained": True,
                "rollback_serving_state_id": base_id,
                "two_copy_backup_required": True,
            }
        ),
        "REVIEW_REPORT": _canonical(
            {
                "coverage_fingerprint": coverage_fingerprint,
                "desired_state_fingerprint": desired_fingerprint,
                "record_count": 1,
                "result": "READY",
                "statement": "Complete deterministic proposal fixture.",
            }
        ),
        "SERVING_STATE_DEFINITION": _canonical(
            {
                "coverage_manifest_id": coverage_id,
                "desired_state_inventory_id": desired_id,
                "serving_state_fingerprint": candidate_fingerprint,
                "serving_state_id": candidate_id,
            }
        ),
        "VALIDATION": _canonical(
            {
                "checks": [
                    {
                        "check_id": check_id,
                        "evidence_refs": validation_evidence,
                        "result": "PASS",
                    }
                    for check_id in (
                        "EVIDENCE_BOUND",
                        "SCOPE_COMPLETE",
                        "TRACEABILITY_COMPLETE",
                    )
                ],
                "result": "PASS",
            }
        ),
    }
    return ProposalMemberFixture(
        contents,
        ProposalMemberBindings(
            observation_cutoff,
            promotion_id,
            promotion_fingerprint,
            base_id,
            candidate_id,
            candidate_fingerprint,
        ),
        coverage_id,
        desired_id,
    )
