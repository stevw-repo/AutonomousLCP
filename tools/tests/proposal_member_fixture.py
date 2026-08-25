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
    traceability_shards: dict[str, bytes]
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
    include_empty_scope: bool = False,
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
    empty_scope_id = "rsc_" + "0" * 48
    empty_release_id = "rel_" + "0" * 48
    scope_releases = [(scope_id, release_id)]
    if include_empty_scope:
        scope_releases.append((empty_scope_id, empty_release_id))
    scope_releases.sort()
    coverage_scopes = [
        {
            "gap_refs": list[str](),
            "last_verified_at": observation_cutoff,
            "quarantine_refs": list[str](),
            "scope_id": selected_scope_id,
            "source_failure_refs": list[str](),
            "status": "CURRENT",
            "warning": "NO_COVERAGE_WARNING",
        }
        for selected_scope_id, _selected_release_id in scope_releases
    ]
    coverage = _canonical(
        {
            "observation_cutoff": observation_cutoff,
            "scopes": coverage_scopes,
            "serving_state_id": candidate_id,
        }
    )
    coverage_fingerprint = _fingerprint(coverage)
    coverage_id = _stable_id("csm", candidate_id, coverage_fingerprint)
    promotion = _canonical(
        {
            "action_contract_version": "1.0.0",
            "actions": [
                {
                    "action_id": "BUILD_TARGET",
                    "attempt_ceiling": 3,
                    "capability_profile_ref": {
                        "fingerprint": "sha256:" + "7" * 64,
                        "ref_id": "cap_" + digit * 48,
                        "ref_type": "CAPABILITY_PROFILE",
                    },
                    "compensation": {"mode": "NO_COMPENSATION"},
                    "deadline": valid_until,
                    "destination_class": "SERVING_TARGET",
                    "effect_command_fingerprint": "sha256:" + "8" * 64,
                    "effect_type": "PINECONE_MUTATION",
                    "expected_remote_precondition_ref": {
                        "contract_id": "asklegal.pinecone-target-absent",
                        "fingerprint": "sha256:" + "a" * 64,
                        "version": "1.0.0",
                    },
                    "input_refs": [
                        {
                            "fingerprint": desired_fingerprint,
                            "ref_id": desired_id,
                            "ref_type": "DESIRED_STATE_INVENTORY",
                        },
                        {
                            "fingerprint": candidate_fingerprint,
                            "ref_id": candidate_id,
                            "ref_type": "SERVING_STATE",
                        },
                    ],
                    "owning_application": "PROMOTION_WORKER",
                    "permitted_checkpoint": "BUILD_REPLACEMENT_TARGET",
                    "required_capability": "MUTATE_PINECONE",
                    "retry_class": "RECONCILE_BEFORE_RETRY",
                    "sequence": 1,
                    "stable_idempotency_key": f"promotion-{digit}-build-target",
                    "stop_conditions": [
                        "ATTEMPT_CEILING",
                        "AUTHORITY_INVALID",
                        "CANCELLATION_BEFORE_EFFECT",
                        "CAPABILITY_INACTIVE",
                        "DEADLINE",
                        "POSTCONDITION_MET",
                        "PRECONDITION_CHANGED",
                    ],
                    "success_postcondition_ref": {
                        "contract_id": "asklegal.pinecone-target-exact",
                        "fingerprint": "sha256:" + "b" * 64,
                        "version": "1.0.0",
                    },
                }
            ],
            "base_serving_state_id": base_id,
            "batch_size": 1,
            "candidate_serving_state_fingerprint": candidate_fingerprint,
            "candidate_serving_state_id": candidate_id,
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
    serving_payload_fingerprint = "sha256:" + "9" * 64
    profile_id = "srp_" + digit * 48
    shard_id = "rts_" + digit * 48
    shard_path = f"entries/{shard_id}.ndjson"
    traceability_entry = _canonical(
        {
            "authority_note_evidence": {
                "decision_ref": {
                    "fingerprint": "sha256:" + "4" * 64,
                    "ref_id": "dec_" + digit * 48,
                    "ref_type": "DECISION",
                },
                "rendered_value_fingerprint": _fingerprint(b"None"),
                "supporting_evidence_refs": list[object](),
            },
            "corpus_release_id": release_id,
            "display_citation_ids": list[str](),
            "evidence_refs": [
                {
                    "fingerprint": "sha256:" + "5" * 64,
                    "ref_id": evidence_ref,
                    "ref_type": "EVIDENCE",
                }
            ],
            "grouping_ids": list[str](),
            "legal_item_id": "lit_" + digit * 48,
            "legal_location_ids": ["loc_" + digit * 48],
            "official_version_ids": ["ofv_" + digit * 48],
            "release_scope_id": scope_id,
            "search_record_id": record_id,
            "serving_payload_fingerprint": serving_payload_fingerprint,
            "serving_record_profile_id": profile_id,
        }
    )
    traceability_shards = {shard_path: traceability_entry + b"\n"}
    shard_descriptors = [
        {
            "artifact_fingerprint": _fingerprint(traceability_shards[shard_path]),
            "corpus_release_id": release_id,
            "entry_count": 1,
            "lookup_shard_id": shard_id,
            "media_type": "application/x-ndjson",
            "path": shard_path,
            "release_scope_id": scope_id,
        }
    ]
    if include_empty_scope:
        empty_shard_id = "rts_" + "0" * 48
        empty_shard_path = f"entries/{empty_shard_id}.ndjson"
        traceability_shards[empty_shard_path] = b""
        shard_descriptors.append(
            {
                "artifact_fingerprint": _fingerprint(b""),
                "corpus_release_id": empty_release_id,
                "entry_count": 0,
                "lookup_shard_id": empty_shard_id,
                "media_type": "application/x-ndjson",
                "path": empty_shard_path,
                "release_scope_id": empty_scope_id,
            }
        )
    shard_descriptors.sort(key=lambda item: str(item["release_scope_id"]))
    traceability_manifest = _canonical(
        {
            "entry_schema_fingerprint": "sha256:" + "2" * 64,
            "entry_schema_id": "asklegal.record-traceability-entry",
            "entry_schema_version": "1.0.0",
            "lookup_revision_id": "rtl_" + digit * 48,
            "manifest_schema_fingerprint": "sha256:" + "3" * 64,
            "schema_id": "asklegal.record-traceability-lookup-manifest",
            "schema_version": "1.0.0",
            "serving_record_profiles": [
                {
                    "schema_fingerprint": "sha256:" + "6" * 64,
                    "schema_version": "1.0.0",
                    "serving_record_profile_id": profile_id,
                }
            ],
            "shards": shard_descriptors,
            "total_entry_count": 1,
        }
    )
    release_rows: list[dict[str, object]] = [
        {
            "evidence_refs": [evidence_ref],
            "observation_cutoff": observation_cutoff,
            "record_ids": [record_id],
            "release_id": release_id,
            "scope_id": scope_id,
            "validation_refs": [validation_ref],
        }
    ]
    if include_empty_scope:
        release_rows.append(
            {
                "evidence_refs": [evidence_ref],
                "observation_cutoff": observation_cutoff,
                "record_ids": list[str](),
                "release_id": empty_release_id,
                "scope_id": empty_scope_id,
                "validation_refs": [validation_ref],
            }
        )
    release_rows.sort(key=lambda item: str(item["scope_id"]))
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
                "releases": release_rows,
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
                "records": [
                    {
                        "record_id": record_id,
                        "release_id": release_id,
                        "scope_id": scope_id,
                        "serving_payload_fingerprint": serving_payload_fingerprint,
                    }
                ],
                "scope_releases": [list(item) for item in scope_releases],
            }
        ),
        "PROMOTION_MANIFEST": promotion,
        "RECORD_TRACEABILITY": traceability_manifest,
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
        traceability_shards,
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
