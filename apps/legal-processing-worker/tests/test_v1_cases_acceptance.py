"""Focused retained Judiciary-to-Case judgment composition tests."""

from __future__ import annotations

import runpy
from hashlib import sha256
from pathlib import Path
from typing import TypeIs

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import ServingRecordProfile
from asklegal_evidence_vault import ExactObjectReference, VaultName
from asklegal_legal_desks.hk_case_judgment import HKCaseJudgmentBundle
from asklegal_legal_desks.hk_case_proposition import (
    HKCaseAdmittedSemanticDecision,
    HKCasePropositionRequestPair,
    bind_hk_case_proposition_challenge,
)
from asklegal_legal_desks.model import SemanticTaskProfile
from asklegal_legal_processing_worker.v1_cases_acceptance import (
    CasesAcceptanceError,
    PreparedCaseSemanticWork,
    VerifiedCaseJudgment,
    admit_case_semantic_outputs,
    load_verified_case_judgments,
    persist_case_release_component,
    prepare_case_release_component,
)
from asklegal_management_register import LocalLegalIdentityRegister

_ROOT = Path(__file__).parents[3]
_PROPOSITION_HELPERS = runpy.run_path(
    str(_ROOT / "packages/legal-desks/tests/test_hk_case_proposition.py")
)


def _is_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _semantic_profile(value: object) -> SemanticTaskProfile:
    assert type(value) is SemanticTaskProfile
    return value


class _Vault:
    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = bodies

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        body = self.bodies.get(logical_key)
        if body is None:
            return None
        return ExactObjectReference(
            VaultName.PRIMARY,
            logical_key,
            "v" + sha256(logical_key.encode()).hexdigest(),
            "sha256:" + sha256(body).hexdigest(),
            len(body),
        )

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        body = self.bodies[reference.logical_key]
        assert len(body) == reference.byte_length
        assert "sha256:" + sha256(body).hexdigest() == reference.fingerprint
        return body


def _manifest(bundle_ref: str) -> bytes:
    body: dict[str, JsonValue] = {
        "cycle_id": "cyc_cases_positive",
        "discrepancy_refs": [],
        "earliest_decision_date": "1997-07-01",
        "journal_head_fingerprint": "sha256:" + "a" * 64,
        "judgment_bundle_refs": [bundle_ref],
        "observation_cutoff": "1997-12-31T00:00:00Z",
        "result": "COMPLETE",
        "year_dispositions": [
            {
                "discovered_judgments": 1,
                "final_page": 1,
                "first_in_scope_date": "1997-07-01",
                "result": "COMPLETE",
                "retryable_items": 0,
                "verified_judgments": 1,
                "verified_listing_pages": 1,
                "year": 1997,
            }
        ],
    }
    return canonicalize(
        checked_json_value(
            {
                **body,
                "fingerprint": "sha256:" + sha256(canonicalize(body)).hexdigest(),
            }
        )
    )


def _inputs(html: bytes | None = None) -> tuple[bytes, _Vault]:
    source = (
        html
        or b"""<!doctype html><html lang="en"><head><title>HKSAR v Chan</title></head>
    <body><h1>HKSAR v Chan</h1><div>Court of Appeal of the High Court</div>
    <div>Date of Judgment: 31/12/1997</div><div>Coram: Chan PJ</div>
    <div>[1997] HKCA 12</div><div>CACC 12/1997</div>
    <p id="para-1">[1] The appeal concerns the proper construction of section 1.</p>
    <p id="para-2">[2] The appeal is dismissed.</p></body></html>"""
    )
    capture_ref = "objects/judgment-12"
    capture_fp = "sha256:" + sha256(source).hexdigest()
    bundle = canonicalize(
        {
            "capture": {
                "body_length": len(source),
                "content_fingerprint": capture_fp,
                "object_ref": capture_ref,
                "work_item_id": "awi_" + "1" * 64,
            },
            "judgment_node_key": "judgment-dis-12",
            "occurrences": [
                {
                    "dis_id": 12,
                    "listing_node_key": "judiciary-year-1997-page-1",
                    "occurrence_key": "judiciary-occurrence-12",
                    "presentation": {
                        "disposition": "PRESENTATION_LOCATOR_RETAINED",
                        "url": "https://legalref.judiciary.hk/lrs/common/ju/ju_frame.jsp?DIS=12",
                    },
                    "relationships": [
                        {
                            "disposition": "SOURCE_RELATIONSHIP_RETAINED",
                            "kind": kind,
                            "relationship_node_key": f"relationship-{kind.lower()}",
                            "work_item_id": f"awi_{index:064x}",
                        }
                        for index, kind in enumerate(
                            (
                                "CORRECTION_ARTIFACT",
                                "REISSUE_ARTIFACT",
                                "LANGUAGE",
                                "TRANSLATION_ARTIFACT",
                                "LISTING_ALIAS",
                                "PROCEEDING_IDENTITY",
                            ),
                            start=2,
                        )
                    ],
                }
            ],
            "schema_id": "asklegal.hk-case-judgment-bundle/v1",
        }
    )
    bundle_ref = "cases/judgment-bundles/sha256/" + sha256(bundle).hexdigest() + ".json"
    return _manifest(bundle_ref), _Vault({bundle_ref: bundle, capture_ref: source})


def test_retained_wrapper_and_raw_html_become_source_neutral_judgment() -> None:
    """The live adapter reads both immutable layers and uses the Desk loader."""
    manifest, vault = _inputs()

    result = load_verified_case_judgments(manifest, vault)

    assert len(result) == 1
    item = result[0]
    assert item.bundle.judgment is not None
    assert item.bundle.judgment.case_name == "HKSAR v Chan"
    assert item.bundle.judgment.court_id == "CA"
    assert item.bundle.judgment.decision_date == "1997-12-31"
    assert item.bundle.judgment.neutral_citations == ("[1997] HKCA 12",)
    assert [paragraph.text for paragraph in item.bundle.judgment.opinions[0].paragraphs] == [
        "The appeal concerns the proper construction of section 1.",
        "The appeal is dismissed.",
    ]
    assert item.capture_reference.logical_key == "objects/judgment-12"


def test_raw_html_parser_fails_closed_on_missing_source_metadata() -> None:
    """Visible text alone cannot manufacture a court, date, or case identity."""
    manifest, vault = _inputs(b"<html><p>[1] text only</p></html>")

    with pytest.raises(CasesAcceptanceError, match="CASES_SOURCE_BODY_INVALID"):
        load_verified_case_judgments(manifest, vault)


def _semantic_documents() -> tuple[PreparedCaseSemanticWork, bytes, bytes]:
    bundle_factory = _PROPOSITION_HELPERS["_bundle"]
    profile_factory = _PROPOSITION_HELPERS["_profiles"]
    build_factory = _PROPOSITION_HELPERS["_build"]
    admitted_factory = _PROPOSITION_HELPERS["_admitted"]
    assert callable(bundle_factory)
    assert callable(profile_factory)
    assert callable(build_factory)
    assert callable(admitted_factory)
    bundle = bundle_factory()
    profiles = profile_factory()
    assert type(bundle) is HKCaseJudgmentBundle
    assert _is_object_tuple(profiles)
    assert len(profiles) == 2
    profile_pair = (_semantic_profile(profiles[0]), _semantic_profile(profiles[1]))
    pair = build_factory(bundle, profile_pair)
    assert type(pair) is HKCasePropositionRequestPair
    admitted = admitted_factory(pair)
    assert type(admitted) is HKCaseAdmittedSemanticDecision
    decision = canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-case-proposition-decision-output/v1",
                "schema_version": "1.0.0",
                "request_id": admitted.request_id,
                "complete_reading": admitted.complete_reading,
                "proposal_fingerprint": admitted.proposal_fingerprint,
                "propositions": [
                    {
                        "proposition_id": item.proposition_id,
                        "candidate_id": item.candidate_id,
                        "proposition_text": item.proposition_text,
                        "text_mode": item.text_mode,
                        "court_id": item.court_id,
                        "opinion_id": item.opinion_id,
                        "judge_names": list(item.judge_names),
                        "qualification_texts": list(item.qualification_texts),
                        "exception_texts": list(item.exception_texts),
                        "support_paragraph_refs": list(item.support_paragraph_refs),
                        "support_fingerprint": item.support_fingerprint,
                        "authority_role": item.authority_role.value,
                        "legal_issue": item.legal_issue,
                        "material_context": item.material_context,
                        "result_context": item.result_context,
                        "quotation_paragraph_refs": list(item.quotation_paragraph_refs),
                        "evidence_links": [
                            {"role": link.role.value, "paragraph_ref": link.paragraph_ref}
                            for link in item.evidence_links
                        ],
                    }
                    for item in admitted.propositions
                ],
                "unit_resolutions": [
                    {
                        "paragraph_ref": item.paragraph_ref,
                        "resolution": item.resolution.value,
                        "primary_use": item.primary_use.value,
                        "evidence_roles": [role.value for role in item.evidence_roles],
                        "non_propositional_reason": (
                            None
                            if item.non_propositional_reason is None
                            else item.non_propositional_reason.value
                        ),
                        "citation_or_treatment_lead": item.citation_or_treatment_lead,
                        "screening_handoff_ids": list(item.screening_handoff_ids),
                    }
                    for item in admitted.unit_resolutions
                ],
            }
        )
    )
    challenge_request = bind_hk_case_proposition_challenge(
        pair.challenge,
        admitted.proposal_fingerprint,
        pair.decision.authorities,
    )
    challenge = canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-case-proposition-challenge-output/v1",
                "schema_version": "1.0.0",
                "request_id": challenge_request.request_id,
                "proposal_fingerprint": admitted.proposal_fingerprint,
                "challenge_code": "PASS",
                "supporting_evidence_refs": list(challenge_request.evidence_refs),
                "unresolved_facts": [],
            }
        )
    )
    return PreparedCaseSemanticWork(pair), decision, challenge


def test_strict_semantic_outputs_feed_existing_desk_admission() -> None:
    """Complete decision and challenge bytes are admitted only through the Desk kernel."""
    work, decision, challenge = _semantic_documents()

    result = admit_case_semantic_outputs(work, decision, challenge)

    assert result.propositions
    assert result.ledger_result.accepted_candidate_count == 1


def test_semantic_extra_field_and_foreign_citation_fail_closed() -> None:
    """The adapter never repairs a malformed model answer or foreign evidence reference."""
    work, decision, challenge = _semantic_documents()
    document = __import__("json").loads(decision)
    document["extra"] = "forbidden"
    with pytest.raises(CasesAcceptanceError, match="CASES_SEMANTIC_DECISION_INVALID"):
        admit_case_semantic_outputs(work, canonicalize(document), challenge)
    challenge_document = __import__("json").loads(challenge)
    challenge_document["supporting_evidence_refs"] = ["evidence/foreign"]
    with pytest.raises(CasesAcceptanceError, match="CASES_SEMANTIC_CHALLENGE_INVALID"):
        admit_case_semantic_outputs(work, decision, canonicalize(challenge_document))


def test_positive_case_release_uses_restart_safe_register_identities(tmp_path: Path) -> None:
    """Admitted records are rebound to create-or-match Register identities."""
    work, decision, challenge = _semantic_documents()
    admission = admit_case_semantic_outputs(work, decision, challenge)
    bundle_factory = _PROPOSITION_HELPERS["_bundle"]
    assert callable(bundle_factory)
    bundle = bundle_factory()
    assert type(bundle) is HKCaseJudgmentBundle
    body = canonicalize({"normalized": "fixture"})
    capture = ExactObjectReference(
        VaultName.PRIMARY,
        "cases/source/fixture",
        "v" + "1" * 64,
        "sha256:" + sha256(body).hexdigest(),
        len(body),
    )
    judgment = VerifiedCaseJudgment(
        "sha256:" + "a" * 64,
        capture,
        capture,
        body,
        bundle,
    )
    treatment = canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-case-later-treatment-proof/v1",
                "schema_version": "1.0.0",
                "judicial_decision_id": work.pair.decision.semantic_task.judicial_decision_id,
                "complete_whole_judgment_reading": True,
                "examined_paragraph_refs": sorted(work.pair.paragraph_refs),
                "treatment_lead_refs": sorted(
                    item.paragraph_ref
                    for item in admission.admitted_decision.unit_resolutions
                    if item.citation_or_treatment_lead
                ),
                "unresolved_facts": [],
            }
        )
    )
    profile = ServingRecordProfile("srp_case_v1", "1.0.0", "sha256:" + "b" * 64)
    path = (tmp_path / "legal-identities.json").resolve()

    first = prepare_case_release_component(
        judgment,
        admission,
        decision,
        challenge,
        treatment,
        "2026-08-01T00:00:00Z",
        profile,
        LocalLegalIdentityRegister(path),
    )
    replay = prepare_case_release_component(
        judgment,
        admission,
        decision,
        challenge,
        treatment,
        "2026-08-01T00:00:00Z",
        profile,
        LocalLegalIdentityRegister(path),
    )

    assert first == replay
    assert first.request.candidates[0].proposed_record.record_id.startswith("rec_")
    assert first.bindings[0].legal_item_id.startswith("lit_")
    retained = persist_case_release_component(
        (tmp_path / "processed" / "op_case").resolve(),
        "op_case",
        "sha256:" + "d" * 64,
        judgment.acquisition_manifest_fingerprint,
        first,
    )
    assert b'"schema_id":"asklegal.hk-v1-case-release-input/v1"' in retained.read_bytes()
    assert (
        persist_case_release_component(
            retained.parent,
            "op_case",
            "sha256:" + "d" * 64,
            judgment.acquisition_manifest_fingerprint,
            replay,
        )
        == retained
    )


def test_treatment_lead_cannot_be_silently_released(tmp_path: Path) -> None:
    """An identified later-treatment lead needs the typed downstream decision path."""
    work, decision, challenge = _semantic_documents()
    admission = admit_case_semantic_outputs(work, decision, challenge)
    bundle_factory = _PROPOSITION_HELPERS["_bundle"]
    assert callable(bundle_factory)
    bundle = bundle_factory()
    assert type(bundle) is HKCaseJudgmentBundle
    capture = ExactObjectReference(
        VaultName.PRIMARY,
        "cases/source/fixture",
        "v" + "1" * 64,
        "sha256:" + "c" * 64,
        1,
    )
    judgment = VerifiedCaseJudgment("sha256:" + "a" * 64, capture, capture, b"x", bundle)
    treatment = canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-case-later-treatment-proof/v1",
                "schema_version": "1.0.0",
                "judicial_decision_id": work.pair.decision.semantic_task.judicial_decision_id,
                "complete_whole_judgment_reading": True,
                "examined_paragraph_refs": sorted(work.pair.paragraph_refs),
                "treatment_lead_refs": [work.pair.paragraph_refs[0]],
                "unresolved_facts": [],
            }
        )
    )
    profile = ServingRecordProfile("srp_case_v1", "1.0.0", "sha256:" + "b" * 64)

    with pytest.raises(CasesAcceptanceError, match="CASES_RELEASE_COMPONENT_INVALID"):
        prepare_case_release_component(
            judgment,
            admission,
            decision,
            challenge,
            treatment,
            "2026-08-01T00:00:00Z",
            profile,
            LocalLegalIdentityRegister((tmp_path / "ids.json").resolve()),
        )
