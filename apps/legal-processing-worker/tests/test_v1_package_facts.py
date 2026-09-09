"""Focused owning package-fact composition over both generated family outputs."""

from __future__ import annotations

import runpy
from hashlib import sha256
from pathlib import Path

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_corpus import ServingRecordProfile
from asklegal_evidence_vault import ExactObjectReference, VaultName
from asklegal_legal_processing_worker.v1_cases_acceptance import (
    VerifiedCaseJudgment,
    admit_case_semantic_outputs,
    persist_case_release_component,
    prepare_case_release_component,
)
from asklegal_legal_processing_worker.v1_legislation_acceptance import (
    prepare_hk_v1_legislation_acceptance_component,
)
from asklegal_legal_processing_worker.v1_package_facts import (
    prepare_hk_v1_package_fact_components,
)
from asklegal_management_register import LocalLegalIdentityRegister

_ROOT = Path(__file__).parents[3]
_CASE = runpy.run_path(str(Path(__file__).with_name("test_v1_cases_acceptance.py")))
_LEG = runpy.run_path(str(Path(__file__).with_name("test_v1_legislation_acceptance.py")))
_PROP = runpy.run_path(str(_ROOT / "packages/legal-desks/tests/test_hk_case_proposition.py"))


def _write(root: Path, relative: str, value: object) -> None:
    path = root.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonicalize(checked_json_value(value)))


def test_exact_retained_facts_create_or_match_package_components(tmp_path: Path) -> None:
    """Actual two-family releases bind exact proposal-time facts and lookup IDs."""
    operation = "op_acceptance_fixture"
    command = "sha256:" + "9" * 64
    cutoff = "2026-09-08T00:00:00Z"
    processed = (tmp_path / "processed").resolve()
    state = (tmp_path / "state").resolve()
    manifest, verified, vault = _LEG["_fixture"]()
    prepare_hk_v1_legislation_acceptance_component(
        operation,
        manifest,
        verified,
        vault,
        state_root=state,
        output_root=processed,
    )
    work, decision, challenge = _CASE["_semantic_documents"]()
    admission = admit_case_semantic_outputs(work, decision, challenge)
    bundle = _PROP["_bundle"]()
    body = canonicalize({"case": "fixture"})
    capture = ExactObjectReference(
        VaultName.PRIMARY,
        "cases/source/fixture",
        "v" + "1" * 64,
        "sha256:" + sha256(body).hexdigest(),
        len(body),
    )
    judgment = VerifiedCaseJudgment("sha256:" + "a" * 64, capture, capture, body, bundle)
    treatment = canonicalize(
        {
            "schema_id": "asklegal.hk-case-later-treatment-proof/v1",
            "schema_version": "1.0.0",
            "judicial_decision_id": work.pair.decision.semantic_task.judicial_decision_id,
            "complete_whole_judgment_reading": True,
            "examined_paragraph_refs": sorted(work.pair.paragraph_refs),
            "treatment_lead_refs": [],
            "unresolved_facts": [],
        }
    )
    case = prepare_case_release_component(
        judgment,
        admission,
        decision,
        challenge,
        treatment,
        cutoff,
        ServingRecordProfile("srp_case_v1", "1.0.0", "sha256:" + "b" * 64),
        LocalLegalIdentityRegister((state / "case-identities.json").resolve()),
    )
    operation_root = processed / operation
    persist_case_release_component(operation_root, operation, command, "sha256:" + "a" * 64, case)
    facts = (tmp_path / "facts").resolve()
    common = {"observation_cutoff": cutoff}
    _write(
        facts,
        "hk-v1-review-package.json",
        {
            **common,
            "title": "HK V1",
            "base_serving_state_id": "srv_" + "1" * 48,
            "base_serving_state_fingerprint": "sha256:" + "1" * 64,
        },
    )
    _write(
        facts,
        "hk-v1-review-readiness.json",
        {
            **common,
            "rollback_state_id": "srv_" + "1" * 48,
            "target_namespace": "hk-v1-local",
            "target_name": "hk-v1-target",
            "embedding_profile_fingerprint": "sha256:" + "2" * 64,
            "model_profile_fingerprint": "sha256:" + "3" * 64,
            "serving_profile_fingerprint": "sha256:" + "4" * 64,
            "backup_profile_fingerprint": "sha256:" + "5" * 64,
            "model_evaluation_ref": "evaluation/model.json",
            "retrieval_evaluation_ref": "evaluation/retrieval.json",
            "native_backup_ref": "backup/native.json",
            "recovery_backup_ref": "backup/recovery.json",
            "limitations": [],
        },
    )
    _write(facts, "hk-v1-two-family-proposal.json", common)
    _write(facts, "coverage-status/coverage.json", common)
    _write(
        facts,
        "promotion-manifest/promotion-manifest.json",
        {
            **common,
            "base_serving_state_id": "srv_" + "1" * 48,
            "rollback_serving_state_id": "srv_" + "1" * 48,
            "target_namespace": "hk-v1-local",
            "target_name": "hk-v1-target",
            "embedding_profile_fingerprint": "sha256:" + "2" * 64,
        },
    )
    _write(facts, "cost-and-capacity/admission.json", {"estimated_cost_microunits": 1})
    _write(facts, "review-report/report.json", {"statement": "Ready for retained review."})
    _write(
        facts,
        "record-traceability/lookup.json",
        {
            "manifest_schema_fingerprint": "sha256:" + "6" * 64,
            "entry_schema_fingerprint": "sha256:" + "7" * 64,
        },
    )
    for relative in (
        "evaluation/model.json",
        "evaluation/retrieval.json",
        "backup/native.json",
        "backup/recovery.json",
    ):
        _write(facts, relative, {"retained": relative})
    request = {
        "operation_id": operation,
        "command_fingerprint": command,
        "observation_cutoff": cutoff,
    }

    prepare_hk_v1_package_fact_components(operation, request, operation_root, facts, state)
    prepare_hk_v1_package_fact_components(operation, request, operation_root, facts, state)

    assert (operation_root / "package-traceability-input.json").is_file()
    assert (operation_root / "package-policy-facts.json").is_file()
