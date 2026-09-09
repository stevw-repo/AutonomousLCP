"""Build one complete retained local Review package for integration tests."""

from __future__ import annotations

import argparse
import runpy
from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import cast

from asklegal_application_runtime import HKV1ScopeDispositionProjection, ProposalArtifactProjection
from asklegal_contracts import (
    ProposalMemberBindings,
    canonicalize,
    validate_v1_proposal_members,
)
from asklegal_contracts.json_types import checked_json_value
from asklegal_promotion import (
    PromotionManifest,
    PromotionPlan,
    freeze_v1_promotion_manifest,
    pinecone_index_name,
    promotion_manifest_bytes,
)
from asklegal_review_api.registered_proposals import (
    freeze_hk_v1_review_readiness,
    hk_v1_local_review_evidence_fingerprint,
    hk_v1_review_readiness_bytes,
)

_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
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


@dataclass(frozen=True, slots=True)
class LocalReviewFixture:
    """Stable identities emitted with one complete test package."""

    proposal_id: str
    promotion_manifest_id: str
    promotion_manifest_fingerprint: str
    task7_proposal_fingerprint: str
    readiness_fingerprint: str


@dataclass(frozen=True, slots=True)
class _FixtureOptions:
    extra_limitations: tuple[str, ...] = ()
    readiness_target_members: tuple[tuple[str, str, str], ...] | None = None
    live_profile: tuple[PromotionManifest, str, str, str] | None = None
    records_are_replacements: bool = False
    addition_record_ids: tuple[str, ...] = ()
    manifest_factory_name: str = "task8_v1_manifest_fixture"


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def _task7_proposal(
    embedding_profile_fingerprint: str,
    observation_cutoff: str,
) -> tuple[bytes, str]:
    model_fingerprint = "sha256:" + "6" * 64
    acquisitions = [
        {
            "journal_head_fingerprint": "sha256:" + "2" * 64,
            "manifest_fingerprint": "sha256:" + "1" * 64,
            "material_family": "CASES",
        },
        {
            "journal_head_fingerprint": "sha256:" + "4" * 64,
            "manifest_fingerprint": "sha256:" + "3" * 64,
            "material_family": "LEGISLATION",
        },
    ]
    prepared: list[dict[str, str]] = []
    for index, scope in enumerate(_SCOPES, start=1):
        family = "CASES" if scope.startswith("HK-CASE-") else "LEGISLATION"
        acquisition = acquisitions[0 if family == "CASES" else 1]
        prepared.append(
            {
                "acquisition_manifest_fingerprint": str(acquisition["manifest_fingerprint"]),
                "artifact_document_fingerprint": "sha256:" + f"{index + 4:x}" * 64,
                "artifact_fingerprint": "sha256:" + f"{index + 8:x}" * 64,
                "artifact_ref": f"prepared-batches/{family.lower()}/{scope.lower()}.json",
                "evidence_set_fingerprint": "sha256:" + f"{index:x}" * 64,
                "journal_head_fingerprint": str(acquisition["journal_head_fingerprint"]),
                "material_family": family,
                "scope_id": scope,
                "semantic_profile_fingerprint": model_fingerprint,
            }
        )
    completeness = checked_json_value(
        {
            "observation_cutoff": observation_cutoff,
            "included_material_families": ["CASES", "LEGISLATION"],
            "scope_ids": list(_SCOPES),
            "acquisition_manifests": acquisitions,
            "prepared_batches": prepared,
            "model_profile_fingerprint": model_fingerprint,
            "embedding_profile_fingerprint": embedding_profile_fingerprint,
        }
    )
    body: dict[str, object] = {
        "acquisition_manifests": acquisitions,
        "completeness_fingerprint": _fingerprint(canonicalize(completeness)),
        "coverage_report_fingerprint": "sha256:" + "a" * 64,
        "embedding_capability_evidence_ref": "capability/embedding.json",
        "embedding_invocation_count": 0,
        "embedding_profile_fingerprint": embedding_profile_fingerprint,
        "explicit_exclusions": ["HKEX_REGULATORY_POST_V1", "HK-PRINCIPLES"],
        "included_material_families": ["CASES", "LEGISLATION"],
        "model_capability_evidence_ref": "capability/model.json",
        "model_invocation_count": 0,
        "model_profile_fingerprint": model_fingerprint,
        "observation_cutoff": observation_cutoff,
        "prepared_batches": prepared,
        "release_state": "WITHHELD_PENDING_NAMED_HUMAN_REVIEW",
        "schema_id": "asklegal.hk-v1-two-family-proposal-manifest/v1",
        "scope_ids": list(_SCOPES),
        "status": "FROZEN_PROPOSAL_READY_FOR_REVIEW",
    }
    task7_fingerprint = _fingerprint(canonicalize(checked_json_value(body)))
    return (
        canonicalize(checked_json_value({**body, "fingerprint": task7_fingerprint})),
        task7_fingerprint,
    )


def _numbered_id(prefix: str, number: int) -> str:
    digit = f"{number:x}"
    return f"{prefix}_{digit * 48}"


def _semantic_member_material(
    manifest: PromotionManifest,
    *,
    records_are_replacements: bool = False,
    addition_record_ids: tuple[str, ...] = (),
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """Build all non-manifest members and exact traceability shards."""
    observation_cutoff = manifest.desired_state.observation_cutoff
    records_by_scope = {
        scope: tuple(item for item in manifest.desired_state.records if item.scope_id == scope)
        for scope, _release_id in manifest.desired_state.scope_releases
    }
    releases: list[dict[str, object]] = []
    validation_refs: list[str] = []
    evidence_refs: list[str] = []
    for index, (scope, release_id) in enumerate(
        manifest.desired_state.scope_releases,
        start=1,
    ):
        scoped = records_by_scope[scope]
        scoped_evidence = sorted(
            {evidence for item in scoped for evidence in item.record.evidence_refs}
            or {_numbered_id("evi", index + 4)}
        )
        validation_ref = _numbered_id("val", index)
        evidence_refs.extend(scoped_evidence)
        validation_refs.append(validation_ref)
        releases.append(
            {
                "evidence_refs": scoped_evidence,
                "observation_cutoff": observation_cutoff,
                "record_ids": [item.record_id for item in scoped],
                "release_id": release_id,
                "scope_id": scope,
                "validation_refs": [validation_ref],
            }
        )
    profile_id = _numbered_id("srp", 3)
    shards: dict[str, bytes] = {}
    descriptors: list[dict[str, object]] = []
    for index, (scope, release_id) in enumerate(
        manifest.desired_state.scope_releases,
        start=1,
    ):
        shard_id = _numbered_id("rts", index)
        shard_path = f"entries/{shard_id}.ndjson"
        entries: list[bytes] = []
        for record_index, item in enumerate(records_by_scope[scope], start=1):
            evidence_references = [
                {
                    "fingerprint": "sha256:" + "5" * 64,
                    "ref_id": evidence,
                    "ref_type": "EVIDENCE",
                }
                for evidence in item.record.evidence_refs
            ]
            entries.append(
                canonicalize(
                    checked_json_value(
                        {
                            "authority_note_evidence": {
                                "decision_ref": {
                                    "fingerprint": "sha256:" + "4" * 64,
                                    "ref_id": _numbered_id("dec", record_index),
                                    "ref_type": "DECISION",
                                },
                                "rendered_value_fingerprint": _fingerprint(
                                    item.record.authority_note.encode()
                                ),
                                "supporting_evidence_refs": evidence_references,
                            },
                            "corpus_release_id": item.release_id,
                            "display_citation_ids": [],
                            "evidence_refs": evidence_references,
                            "grouping_ids": [],
                            "legal_item_id": _numbered_id("lit", record_index),
                            "legal_location_ids": [_numbered_id("loc", record_index)],
                            "official_version_ids": [_numbered_id("ofv", record_index)],
                            "release_scope_id": item.scope_id,
                            "search_record_id": item.record_id,
                            "serving_payload_fingerprint": item.content_fingerprint,
                            "serving_record_profile_id": profile_id,
                        }
                    )
                )
            )
        shard_content = b"" if not entries else b"\n".join(entries) + b"\n"
        shards[shard_path] = shard_content
        descriptors.append(
            {
                "artifact_fingerprint": _fingerprint(shard_content),
                "corpus_release_id": release_id,
                "entry_count": len(entries),
                "lookup_shard_id": shard_id,
                "media_type": "application/x-ndjson",
                "path": shard_path,
                "release_scope_id": scope,
            }
        )
    all_evidence = sorted(set(evidence_refs) | set(validation_refs))
    all_record_ids = [item.record_id for item in manifest.desired_state.records]
    additions = list(addition_record_ids) if records_are_replacements else all_record_ids
    if len(set(additions)) != len(additions) or not set(additions).issubset(all_record_ids):
        message = "fixture addition record identities must be exact desired-state members"
        raise ValueError(message)
    replacements = (
        [record_id for record_id in all_record_ids if record_id not in set(additions)]
        if records_are_replacements
        else []
    )
    contents = {
        "CHANGE_INVENTORY": canonicalize(
            checked_json_value(
                {
                    "additions": additions,
                    "carried_forward": [],
                    "observation_cutoff": observation_cutoff,
                    "replacements": replacements,
                    "retirements": [],
                    "unchanged": [],
                    "withholdings": [],
                }
            )
        ),
        "CORPUS_RELEASES": canonicalize(
            checked_json_value({"observation_cutoff": observation_cutoff, "releases": releases})
        ),
        "COST_AND_CAPACITY": canonicalize(
            checked_json_value(
                {
                    "batch_size": manifest.batch_size,
                    "embedding_profile_fingerprint": (
                        manifest.embedding_profile.profile_fingerprint
                    ),
                    "estimated_cost_microunits": len(manifest.desired_state.records),
                    "record_count": len(manifest.desired_state.records),
                    "result": "PASS",
                }
            )
        ),
        "COVERAGE_STATUS": manifest.coverage_status.canonical_bytes,
        "DESIRED_STATE_INVENTORIES": canonicalize(
            checked_json_value(
                {
                    "inventory_fingerprint": manifest.desired_state.inventory_fingerprint,
                    "inventory_id": manifest.desired_state.inventory_id,
                    "observation_cutoff": observation_cutoff,
                    "records_fingerprint": manifest.desired_state.records_fingerprint,
                    "records": [
                        {
                            "artifact_ref": item.record.artifact_ref,
                            "authority_note": item.record.authority_note,
                            "country": item.record.country,
                            "evidence_refs": list(item.record.evidence_refs),
                            "jurisdiction": item.record.jurisdiction,
                            "material_type": item.record.material_type,
                            "record_id": item.record_id,
                            "release_id": item.release_id,
                            "scope_id": item.scope_id,
                            "serving_payload_fingerprint": item.content_fingerprint,
                            "source": item.record.source,
                            "text": item.record.text,
                        }
                        for item in manifest.desired_state.records
                    ],
                    "scope_releases": [
                        list(item) for item in manifest.desired_state.scope_releases
                    ],
                    "target_key": manifest.desired_state.target_key,
                }
            )
        ),
        "RECORD_TRACEABILITY": canonicalize(
            checked_json_value(
                {
                    "entry_schema_fingerprint": "sha256:" + "2" * 64,
                    "entry_schema_id": "asklegal.record-traceability-entry",
                    "entry_schema_version": "1.0.0",
                    "lookup_revision_id": _numbered_id("rtl", 9),
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
                    "shards": descriptors,
                    "total_entry_count": len(manifest.desired_state.records),
                }
            )
        ),
        "RECOVERY_READINESS": canonicalize(
            checked_json_value(
                {
                    "candidate_serving_state_id": manifest.candidate_serving_state_id,
                    "predecessor_retained": True,
                    "rollback_serving_state_id": manifest.rollback_serving_state_id,
                    "two_copy_backup_required": True,
                }
            )
        ),
        "REVIEW_REPORT": canonicalize(
            checked_json_value(
                {
                    "coverage_fingerprint": manifest.coverage_status.fingerprint,
                    "desired_state_fingerprint": manifest.desired_state.inventory_fingerprint,
                    "record_count": len(manifest.desired_state.records),
                    "result": "READY",
                    "statement": "Complete deterministic Hong Kong V1 proposal fixture.",
                }
            )
        ),
        "SERVING_STATE_DEFINITION": canonicalize(
            checked_json_value(
                {
                    "coverage_manifest_id": manifest.coverage_status.manifest_id,
                    "desired_state_inventory_id": manifest.desired_state.inventory_id,
                    "serving_state_fingerprint": (manifest.candidate_serving_state_fingerprint),
                    "serving_state_id": manifest.candidate_serving_state_id,
                }
            )
        ),
        "VALIDATION": canonicalize(
            checked_json_value(
                {
                    "checks": [
                        {
                            "check_id": check_id,
                            "evidence_refs": all_evidence,
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
            )
        ),
    }
    return contents, shards


def _write_review_fixture(
    root: Path,
    repository_root: Path,
    options: _FixtureOptions,
) -> LocalReviewFixture:
    """Write all fourteen exact local Review inputs beneath one temporary root."""
    namespace = runpy.run_path(
        str(repository_root / "apps/promotion-worker/tests/test_m6_promotion.py")
    )
    manifest_factory = cast(
        "Callable[[], PromotionManifest]", namespace[options.manifest_factory_name]
    )
    plan_factory = cast(
        "Callable[[PromotionManifest], PromotionPlan]", namespace["task8_plan_from_manifest"]
    )
    live_profile = options.live_profile
    base = live_profile[0] if live_profile is not None else manifest_factory()
    serving_profile_fingerprint = (
        live_profile[1] if live_profile is not None else "sha256:" + "8" * 64
    )
    target_namespace = live_profile[2] if live_profile is not None else "synthetic-v1"
    backup_profile_fingerprint = (
        live_profile[3] if live_profile is not None else "sha256:" + "3" * 64
    )
    observation_cutoff = base.desired_state.observation_cutoff
    task7_content, task7_fingerprint = _task7_proposal(
        base.embedding_profile.profile_fingerprint,
        observation_cutoff,
    )
    target_members = options.readiness_target_members or tuple(
        (
            item.record_id,
            item.scope_id,
            "CASES" if item.scope_id == _SCOPES[0] else "LEGISLATION",
        )
        for item in base.desired_state.records
    )
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
            for scope in _SCOPES
        ),
        (
            "Cases begin on 1997-07-01.",
            "HKEX Regulatory Materials and Principles are outside V1.",
            *options.extra_limitations,
        ),
        "evaluation/model.json",
        "evaluation/retrieval.json",
        "sha256:" + "6" * 64,
        base.embedding_profile.profile_fingerprint,
        serving_profile_fingerprint,
        target_namespace,
        backup_profile_fingerprint,
        target_members,
        (_SCOPES[1], _SCOPES[3]),
        pinecone_index_name(
            base.environment,
            base.jurisdiction,
            base.freeze_date,
            base.candidate_serving_state_fingerprint,
            base.project_id,
        ),
        "backup/native.json",
        "backup/recovery.json",
        base.rollback_serving_state_id,
        task7_fingerprint,
    )
    readiness_content = hk_v1_review_readiness_bytes(readiness)
    contents, shards = _semantic_member_material(
        base,
        records_are_replacements=options.records_are_replacements,
        addition_record_ids=options.addition_record_ids,
    )
    declarations = tuple(
        ProposalArtifactProjection(
            role,
            _ROLE_PATHS[role],
            "application/json",
            _fingerprint(contents[role]),
            len(contents[role]),
        )
        for role in sorted(contents)
    )
    evidence_fingerprint = hk_v1_local_review_evidence_fingerprint(
        declarations,
        task7_fingerprint,
        readiness.fingerprint,
        observation_cutoff=observation_cutoff,
        title="Hong Kong V1 Cases and Legislation proposal",
        base_serving_state_fingerprint="sha256:" + "a" * 64,
    )
    predicates = tuple(
        sorted(
            {
                *base.validity_predicates,
                ("HK_V1_REVIEW_EVIDENCE", "1.0.0", evidence_fingerprint),
                ("HK_V1_REVIEW_READINESS", "1.0.0", readiness.fingerprint),
                ("HK_V1_TWO_FAMILY_PROPOSAL", "1.0.0", task7_fingerprint),
            }
        )
    )
    manifest = freeze_v1_promotion_manifest(
        replace(plan_factory(base), validity_predicates=predicates)
    )
    contents["PROMOTION_MANIFEST"] = promotion_manifest_bytes(manifest)
    artifacts = tuple(
        ProposalArtifactProjection(
            role,
            _ROLE_PATHS[role],
            "application/json",
            _fingerprint(contents[role]),
            len(contents[role]),
        )
        for role in sorted(contents)
    )
    proposal_id = _stable_id("ppk", manifest.fingerprint, evidence_fingerprint)
    unsigned_package: dict[str, object] = {
        "artifacts": [
            {
                "byte_length": item.byte_length,
                "fingerprint": item.fingerprint,
                "media_type": item.media_type,
                "path": item.path,
                "role": item.role,
            }
            for item in artifacts
        ],
        "base_serving_state_fingerprint": "sha256:" + "a" * 64,
        "base_serving_state_id": manifest.base_serving_state_id,
        "candidate_serving_state_fingerprint": manifest.candidate_serving_state_fingerprint,
        "candidate_serving_state_id": manifest.candidate_serving_state_id,
        "observation_cutoff": observation_cutoff,
        "promotion_manifest_fingerprint": manifest.fingerprint,
        "promotion_manifest_id": manifest.manifest_id,
        "proposal_id": proposal_id,
        "schema_id": "asklegal.hk-v1-local-review-package/v1",
        "title": "Hong Kong V1 Cases and Legislation proposal",
        "valid_from": manifest.valid_from,
        "valid_until": manifest.valid_until,
        "validity_predicates": [
            {"contract_id": item[0], "version": item[1], "fingerprint": item[2]}
            for item in predicates
        ],
    }
    package_fingerprint = _fingerprint(canonicalize(checked_json_value(unsigned_package)))
    root.mkdir(parents=True, exist_ok=True)
    root.joinpath("hk-v1-two-family-proposal.json").write_bytes(task7_content)
    root.joinpath("hk-v1-review-readiness.json").write_bytes(readiness_content)
    root.joinpath("hk-v1-review-package.json").write_bytes(
        canonicalize(
            checked_json_value({**unsigned_package, "package_fingerprint": package_fingerprint})
        )
    )
    for artifact in artifacts:
        path = root / artifact.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents[artifact.role])
    for shard_path, shard_content in shards.items():
        path = root / "record-traceability" / shard_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(shard_content)
    validate_v1_proposal_members(
        contents,
        ProposalMemberBindings(
            observation_cutoff,
            manifest.manifest_id,
            manifest.fingerprint,
            manifest.base_serving_state_id,
            manifest.candidate_serving_state_id,
            manifest.candidate_serving_state_fingerprint,
        ),
        shards,
    )
    return LocalReviewFixture(
        proposal_id,
        manifest.manifest_id,
        manifest.fingerprint,
        task7_fingerprint,
        readiness.fingerprint,
    )


def write_task8_local_review_fixture(
    root: Path,
    repository_root: Path,
    *,
    extra_limitations: tuple[str, ...] = (),
    readiness_target_members: tuple[tuple[str, str, str], ...] | None = None,
    live_profile: tuple[PromotionManifest, str, str, str] | None = None,
) -> LocalReviewFixture:
    """Write the standard exact local Review fixture beneath one temporary root."""
    return _write_review_fixture(
        root,
        repository_root,
        _FixtureOptions(extra_limitations, readiness_target_members, live_profile),
    )


def write_task8_interview_review_fixture(
    root: Path,
    repository_root: Path,
) -> LocalReviewFixture:
    """Write the demo variant with new Case B plus two predecessor replacements."""
    return _write_review_fixture(
        root,
        repository_root,
        _FixtureOptions(
            records_are_replacements=True,
            addition_record_ids=("rec_" + "3" * 48,),
            manifest_factory_name="task8_interview_v1_manifest_fixture",
        ),
    )


def main() -> int:
    """Regenerate the checked-in deterministic Review fixture tree."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    write_task8_local_review_fixture(arguments.output, arguments.repository_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
