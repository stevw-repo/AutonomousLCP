"""Task 7 two-family proposal-readiness composition tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import TYPE_CHECKING

import asklegal_control_plane.proposal as proposal_module
import asklegal_control_plane.v1_pipeline as pipeline_module
import pytest
from _task7_capability_fixture import canonical_capability_artifacts
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_reporting import load_hk_v1_coverage_matrix

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_FP_A = "sha256:" + "a" * 64
_FP_B = "sha256:" + "b" * 64
_FP_C = "sha256:" + "c" * 64
_FP_F = "sha256:" + "f" * 64
_CUTOFF = "1997-12-31T00:00:00Z"
_LEG_CUTOFF = "1997-12-31T00:00:00+00:00"
(
    _ISSUED_CAPABILITY_DOCUMENTS,
    _MODEL_CAPABILITY_REF,
    _EMBEDDING_CAPABILITY_REF,
    _FP_D,
    _FP_E,
) = canonical_capability_artifacts(_CUTOFF)
_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)


class _RecordingEffect:
    def __init__(self) -> None:
        self.requests: list[bytes] = []

    def invoke(self, payload: bytes) -> bytes:
        self.requests.append(payload)
        return b"forbidden"


class _CurrentHeads:
    """Mutable trusted-state fake used to prove proposal-time rereads."""

    def __init__(self) -> None:
        self.values = {"LEGISLATION": _FP_A, "CASES": _FP_B}

    def read_current(self, material_family: str) -> str:
        return self.values[material_family]


class _EvidenceStore:
    """Read-only exact local artifact store used by proposal composition tests."""

    def __init__(self, documents: dict[str, bytes] | None = None) -> None:
        self.documents = {} if documents is None else documents
        self.reads: list[str] = []

    def read_exact(self, logical_ref: str) -> bytes:
        self.reads.append(logical_ref)
        return self.documents[logical_ref]


def _seal(body: object) -> bytes:
    document = checked_json_value(body)
    assert type(document) is dict
    document["fingerprint"] = f"sha256:{sha256(canonicalize(document)).hexdigest()}"
    return canonicalize(document)


def _json_object(content: bytes) -> dict[str, JsonValue]:
    document = parse_json_bytes(content, max_bytes=1_000_000)
    assert type(document) is dict
    return document


def _json_list(value: JsonValue) -> list[JsonValue]:
    assert type(value) is list
    return value


def _legislation_manifest(
    *, result: str = "COMPLETE", cutoff: str = _LEG_CUTOFF, cycle_id: str = "cyc_legislation_1997"
) -> bytes:
    retryable = 0 if result == "COMPLETE" else 1
    verified = 1 - retryable
    return _seal(
        {
            "schema_id": "asklegal.legislation-acquisition-manifest",
            "schema_version": "1.0.0",
            "cycle_id": cycle_id,
            "observation_cutoff": cutoff,
            "scope_dispositions": [
                {
                    "scope_id": scope_id,
                    "required_item_count": 1,
                    "verified_item_count": verified,
                    "retryable_item_count": retryable,
                    "rejected_item_count": 0,
                    "result": result,
                }
                for scope_id in _SCOPES[1:]
            ],
            "verified_item_refs": ["legislation-item/cap1/" + "1" * 64],
            "review_issue_refs": ["review/legislation/structural-issue"],
            "journal_head_fingerprint": _FP_A,
            "source_register_fingerprint": _FP_C,
            "source_baseline_fingerprint": _FP_D,
            "work_plan_fingerprint": _FP_E,
            "result": result,
        }
    )


def _cases_manifest(*, cutoff: str = _CUTOFF) -> bytes:
    years: list[JsonValue] = [
        {
            "discovered_judgments": 2 if year == 1997 else 0,
            "final_page": 1,
            "first_in_scope_date": "1997-07-01" if year == 1997 else f"{year:04d}-01-01",
            "result": "COMPLETE",
            "retryable_items": 0,
            "verified_judgments": 2 if year == 1997 else 0,
            "verified_listing_pages": 1,
            "year": year,
        }
        for year in range(1997, int(cutoff[:4]) + 1)
    ]
    return _seal(
        {
            "cycle_id": "cyc_cases_1997",
            "discrepancy_refs": ["review/cases/name-discrepancy"],
            "earliest_decision_date": "1997-07-01",
            "journal_head_fingerprint": _FP_B,
            "judgment_bundle_refs": (
                []
                if int(cutoff[:4]) < 1997
                else [
                    "cases/judgment-bundles/sha256/" + "2" * 64 + ".json",
                    "cases/judgment-bundles/sha256/" + "3" * 64 + ".json",
                ]
            ),
            "observation_cutoff": cutoff,
            "result": "COMPLETE",
            "year_dispositions": years,
        }
    )


def _semantic_fixture() -> tuple[dict[str, bytes], str, str]:
    return (
        dict(_ISSUED_CAPABILITY_DOCUMENTS),
        _MODEL_CAPABILITY_REF,
        _EMBEDDING_CAPABILITY_REF,
    )


def _prepared_fixture() -> tuple[
    tuple[proposal_module.PreparedBatchBinding, ...], dict[str, bytes]
]:
    binding_type = proposal_module.PreparedBatchBinding
    legislation_fingerprint = _json_object(_legislation_manifest())["fingerprint"]
    cases_fingerprint = _json_object(_cases_manifest())["fingerprint"]
    assert type(legislation_fingerprint) is str
    assert type(cases_fingerprint) is str
    bindings: list[proposal_module.PreparedBatchBinding] = []
    documents: dict[str, bytes] = {}
    for index, scope_id in enumerate(_SCOPES, start=1):
        family = "CASES" if scope_id.startswith("HK-CASE") else "LEGISLATION"
        evidence_refs = (
            (
                "cases/judgment-bundles/sha256/" + "2" * 64 + ".json",
                "cases/judgment-bundles/sha256/" + "3" * 64 + ".json",
            )
            if family == "CASES"
            else ("legislation-item/cap1/" + "1" * 64,)
        )
        fingerprint_facts = [
            {"evidence_ref": evidence_ref, "fingerprint": _FP_C} for evidence_ref in evidence_refs
        ]
        evidence_set_fingerprint = (
            "sha256:" + sha256(canonicalize(checked_json_value(fingerprint_facts))).hexdigest()
        )
        request_facts = [
            {
                "evidence_fingerprint": _FP_C,
                "evidence_ref": evidence_ref,
                "semantic_profile_fingerprint": _FP_D,
                "subject_id": f"subject-{index}-{item_index}",
            }
            for item_index, evidence_ref in enumerate(evidence_refs, start=1)
        ]
        batch_id = f"batch-{index}"
        body = {
            "schema_id": "asklegal.hk-v1-prepared-verified-batch/v1",
            "material_family": family,
            "scope_id": scope_id,
            "batch_id": batch_id,
            "observation_cutoff": _CUTOFF,
            "acquisition_manifest_fingerprint": (
                cases_fingerprint if family == "CASES" else legislation_fingerprint
            ),
            "journal_head_fingerprint": _FP_B if family == "CASES" else _FP_A,
            "semantic_profile_fingerprint": _FP_D,
            "capability_evidence_ref": _semantic_fixture()[1],
            "evidence_set_fingerprint": evidence_set_fingerprint,
            "evidence_items": [
                {
                    "evidence_ref": evidence_ref,
                    "fingerprint": _FP_C,
                    "language": "en",
                    "subject_id": f"subject-{index}-{item_index}",
                    "text_fingerprint": _FP_A,
                }
                for item_index, evidence_ref in enumerate(evidence_refs, start=1)
            ],
            "model_requests": [
                {
                    **facts,
                    "request_id": (
                        "request-" + sha256(canonicalize(checked_json_value(facts))).hexdigest()
                    ),
                }
                for facts in request_facts
            ],
            "provider_invocation_count": 0,
            "release_state": "WITHHELD_PENDING_TWO_FAMILY_RECONCILIATION",
        }
        content = _seal(body)
        artifact_ref = "/".join(
            (
                "prepared-batches",
                family.lower(),
                scope_id.lower(),
                batch_id,
                evidence_set_fingerprint.removeprefix("sha256:"),
                f"{_FP_D.removeprefix('sha256:')}.json",
            )
        )
        artifact_fingerprint = f"sha256:{sha256(content).hexdigest()}"
        bindings.append(
            binding_type(
                material_family=family,
                scope_id=scope_id,
                observation_cutoff=_CUTOFF,
                acquisition_manifest_fingerprint=(
                    cases_fingerprint if family == "CASES" else legislation_fingerprint
                ),
                journal_head_fingerprint=_FP_B if family == "CASES" else _FP_A,
                evidence_set_fingerprint=evidence_set_fingerprint,
                semantic_profile_fingerprint=_FP_D,
                artifact_ref=artifact_ref,
                artifact_fingerprint=artifact_fingerprint,
            )
        )
        documents[artifact_ref] = content
    return tuple(bindings), documents


def _bindings() -> tuple[proposal_module.PreparedBatchBinding, ...]:
    return _prepared_fixture()[0]


def _prepared_documents() -> dict[str, bytes]:
    return _prepared_fixture()[1]


def _all_documents() -> dict[str, bytes]:
    semantic, _model_ref, _embedding_ref = _semantic_fixture()
    return {**semantic, **_prepared_documents()}


def _request() -> proposal_module.TwoFamilyProposalRequest:
    request_type = proposal_module.TwoFamilyProposalRequest
    legislation = _legislation_manifest()
    cases = _cases_manifest()
    request = request_type(
        accepted_observation_cutoff=_CUTOFF,
        legislation_manifest=legislation,
        cases_manifest=cases,
        expected_legislation_journal_head=_FP_A,
        expected_cases_journal_head=_FP_B,
        prepared_batches=_bindings(),
        model_profile_fingerprint=_FP_D,
        embedding_profile_fingerprint=_FP_E,
        model_capability_evidence_ref=_semantic_fixture()[1],
        embedding_capability_evidence_ref=_semantic_fixture()[2],
    )

    def manifest_fingerprint(value: bytes) -> str:
        document = _json_object(value)
        fingerprint = document["fingerprint"]
        assert type(fingerprint) is str
        return fingerprint

    assert all(
        item.acquisition_manifest_fingerprint
        == (
            manifest_fingerprint(cases)
            if item.material_family == "CASES"
            else manifest_fingerprint(legislation)
        )
        for item in request.prepared_batches
    )
    return request


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("LEGISLATION_ONLY", "HK_V1_TWO_FAMILY_PROPOSAL_INCOMPLETE"),
        ("CASES_ONLY", "HK_V1_TWO_FAMILY_PROPOSAL_INCOMPLETE"),
        ("INCOMPLETE_RETRYABLE", "HK_V1_TWO_FAMILY_ACQUISITION_INCOMPLETE"),
        ("STALE_JOURNAL_HEAD", "HK_V1_TWO_FAMILY_JOURNAL_HEAD_STALE"),
        ("MISMATCHED_CUTOFF", "HK_V1_TWO_FAMILY_CUTOFF_MISMATCH"),
    ],
)
def test_partial_stale_or_mismatched_input_is_rejected_before_semantic_effects(
    mutation: str, expected_code: str
) -> None:
    """Mutation caught: a partial or stale family can otherwise freeze a proposal."""
    model = _RecordingEffect()
    embedding = _RecordingEffect()
    service_type = pipeline_module.TwoFamilyProposalReadinessService
    service = service_type(
        load_hk_v1_coverage_matrix(),
        _CurrentHeads(),
        _EvidenceStore(_all_documents()),
        model,
        embedding,
    )
    request = _request()
    if mutation == "LEGISLATION_ONLY":
        request = replace(request, cases_manifest=None)
    elif mutation == "CASES_ONLY":
        request = replace(request, legislation_manifest=None)
    elif mutation == "INCOMPLETE_RETRYABLE":
        request = replace(request, legislation_manifest=_legislation_manifest(result=mutation))
    elif mutation == "STALE_JOURNAL_HEAD":
        request = replace(request, expected_cases_journal_head=_FP_C)
    else:
        request = replace(request, cases_manifest=_cases_manifest(cutoff="1998-01-01T00:00:00Z"))

    with pytest.raises(ValueError, match=f"^{expected_code}$"):
        service.prepare(request)

    assert model.requests == []
    assert embedding.requests == []


def test_complete_two_family_input_freezes_one_exact_hkex_free_completeness_manifest() -> None:
    """Mutation caught: HKEX or a missing required scope can otherwise enter completeness."""
    model = _RecordingEffect()
    embedding = _RecordingEffect()
    service_type = pipeline_module.TwoFamilyProposalReadinessService
    service = service_type(
        load_hk_v1_coverage_matrix(),
        _CurrentHeads(),
        _EvidenceStore(_all_documents()),
        model,
        embedding,
    )

    manifest = service.prepare(_request())
    restarted = service.prepare(_request())
    document = _json_object(manifest.content)
    completeness = _json_object(manifest.completeness_content)
    coverage = _json_object(manifest.coverage_report.content)

    assert restarted == manifest
    assert document["status"] == "FROZEN_PROPOSAL_READY_FOR_REVIEW"
    assert document["scope_ids"] == list(_SCOPES)
    assert completeness["scope_ids"] == list(_SCOPES)
    assert completeness["included_material_families"] == ["CASES", "LEGISLATION"]
    assert b"HKEX" not in manifest.completeness_content
    assert b"HK-PRINCIPLES" not in manifest.completeness_content
    coverage_exclusions = _json_list(coverage["explicit_exclusions"])
    coverage_capabilities = _json_list(coverage["capabilities"])
    assert "HKEX_REGULATORY_POST_V1" in coverage_exclusions
    assert "HK-PRINCIPLES" in coverage_exclusions
    assert [
        item["profile_fingerprint"] for item in coverage_capabilities if type(item) is dict
    ] == [_FP_E, _FP_D]
    assert manifest.completeness_fingerprint == (
        "sha256:" + sha256(manifest.completeness_content).hexdigest()
    )
    assert document["model_invocation_count"] == 0
    assert document["embedding_invocation_count"] == 0
    assert document["release_state"] == "WITHHELD_PENDING_NAMED_HUMAN_REVIEW"
    assert model.requests == []
    assert embedding.requests == []

    partial = replace(_request(), prepared_batches=_bindings()[:-1])
    with pytest.raises(ValueError, match=r"^HK_V1_TWO_FAMILY_PREPARED_BATCH_INVALID$"):
        service.prepare(partial)


def test_proposal_rereads_authoritative_heads_after_request_creation_before_effects() -> None:
    """Mutation caught: matching caller and manifest H1 values cannot hide current H2."""
    model = _RecordingEffect()
    embedding = _RecordingEffect()
    heads = _CurrentHeads()
    request = _request()
    heads.values["CASES"] = _FP_C
    evidence = _EvidenceStore(_all_documents())
    service = pipeline_module.TwoFamilyProposalReadinessService(
        load_hk_v1_coverage_matrix(), heads, evidence, model, embedding
    )

    with pytest.raises(ValueError, match=r"^HK_V1_TWO_FAMILY_JOURNAL_HEAD_STALE$"):
        service.prepare(request)

    assert model.requests == []
    assert embedding.requests == []
    assert evidence.reads == []


def test_prepared_batch_metadata_without_readback_artifact_is_rejected_before_effects() -> None:
    """Mutation caught: hash-shaped direct bindings cannot substitute for stored bytes."""
    model = _RecordingEffect()
    embedding = _RecordingEffect()
    service = pipeline_module.TwoFamilyProposalReadinessService(
        load_hk_v1_coverage_matrix(),
        _CurrentHeads(),
        _EvidenceStore(_semantic_fixture()[0]),
        model,
        embedding,
    )

    with pytest.raises(ValueError, match=r"^HK_V1_TWO_FAMILY_PREPARED_BATCH_READ_FAILED$"):
        service.prepare(_request())

    assert model.requests == []
    assert embedding.requests == []


@pytest.mark.parametrize("mutation", ["ABSENT", "ORDER_MISMATCH"])
def test_prepared_evidence_refs_must_match_the_admitted_acquisition_manifest(
    mutation: str,
) -> None:
    """Mutation caught: hash-clean prepared evidence can be unrelated to acquisition."""
    request = _request()
    documents = _all_documents()
    bindings = list(request.prepared_batches)
    target = bindings[0]
    body = _json_object(documents[target.artifact_ref])
    body.pop("fingerprint")
    evidence_items = _json_list(body["evidence_items"])
    model_requests = _json_list(body["model_requests"])
    if mutation == "ORDER_MISMATCH":
        evidence_items.reverse()
        model_requests.reverse()
    else:
        evidence = evidence_items[0]
        model_request = model_requests[0]
        assert type(evidence) is dict
        assert type(model_request) is dict
        forged_ref = "cases/judgment-bundles/sha256/" + "9" * 64 + ".json"
        evidence["evidence_ref"] = forged_ref
        model_request["evidence_ref"] = forged_ref
        request_facts = {
            "evidence_fingerprint": model_request["evidence_fingerprint"],
            "evidence_ref": forged_ref,
            "semantic_profile_fingerprint": model_request["semantic_profile_fingerprint"],
            "subject_id": model_request["subject_id"],
        }
        model_request["request_id"] = (
            "request-" + sha256(canonicalize(checked_json_value(request_facts))).hexdigest()
        )
    fingerprint_facts = [
        {"evidence_ref": evidence["evidence_ref"], "fingerprint": evidence["fingerprint"]}
        for evidence in evidence_items
        if type(evidence) is dict
    ]
    evidence_set_fingerprint = (
        "sha256:" + sha256(canonicalize(checked_json_value(fingerprint_facts))).hexdigest()
    )
    body["evidence_set_fingerprint"] = evidence_set_fingerprint
    content = _seal(body)
    artifact_ref = "/".join(
        (
            "prepared-batches",
            "cases",
            target.scope_id.lower(),
            str(body["batch_id"]),
            evidence_set_fingerprint.removeprefix("sha256:"),
            f"{_FP_D.removeprefix('sha256:')}.json",
        )
    )
    documents[artifact_ref] = content
    bindings[0] = replace(
        target,
        evidence_set_fingerprint=evidence_set_fingerprint,
        artifact_ref=artifact_ref,
        artifact_fingerprint=f"sha256:{sha256(content).hexdigest()}",
    )
    request = replace(request, prepared_batches=tuple(bindings))
    model = _RecordingEffect()
    embedding = _RecordingEffect()
    service = pipeline_module.TwoFamilyProposalReadinessService(
        load_hk_v1_coverage_matrix(),
        _CurrentHeads(),
        _EvidenceStore(documents),
        model,
        embedding,
    )

    with pytest.raises(ValueError, match=r"^HK_V1_TWO_FAMILY_PREPARED_BATCH_INVALID$"):
        service.prepare(request)

    assert model.requests == []
    assert embedding.requests == []


@pytest.mark.parametrize(
    "mutation",
    [
        "FORGED_FINGERPRINT",
        "MISSING_EMBEDDED_FINGERPRINT",
        "FORGED_EMBEDDED_FINGERPRINT",
        "PATH_MISMATCH",
        "EFFECTFUL",
        "RELEASED",
        "HKEX_SCOPE",
        "PRINCIPLES_SCOPE",
        "SHARED_WITH_WRONG_SCOPE",
    ],
)
def test_hostile_prepared_batch_artifacts_are_rejected_before_effects(mutation: str) -> None:
    """Mutation caught: stored bytes must prove every prepared-batch binding."""
    request = _request()
    documents = _all_documents()
    bindings = list(request.prepared_batches)
    target = bindings[0]
    if mutation == "FORGED_FINGERPRINT":
        bindings[0] = replace(target, artifact_fingerprint=_FP_F)
    elif mutation == "PATH_MISMATCH":
        moved = f"{target.artifact_ref}.moved"
        documents[moved] = documents[target.artifact_ref]
        bindings[0] = replace(target, artifact_ref=moved)
    elif mutation == "SHARED_WITH_WRONG_SCOPE":
        other = bindings[1]
        bindings[0] = replace(
            target,
            artifact_ref=other.artifact_ref,
            artifact_fingerprint=other.artifact_fingerprint,
        )
    else:
        body = _json_object(documents[target.artifact_ref])
        if mutation == "MISSING_EMBEDDED_FINGERPRINT":
            body.pop("fingerprint")
            content = canonicalize(body)
        elif mutation == "FORGED_EMBEDDED_FINGERPRINT":
            body["fingerprint"] = _FP_F
            content = canonicalize(body)
        else:
            body.pop("fingerprint")
            if mutation == "EFFECTFUL":
                body["provider_invocation_count"] = 1
            elif mutation == "RELEASED":
                body["release_state"] = "RELEASED"
            elif mutation == "HKEX_SCOPE":
                body["scope_id"] = "HKEX_REGULATORY_POST_V1"
            else:
                body["scope_id"] = "HK-PRINCIPLES"
            content = _seal(body)
        documents[target.artifact_ref] = content
        bindings[0] = replace(
            target,
            artifact_fingerprint=f"sha256:{sha256(content).hexdigest()}",
        )
    request = replace(request, prepared_batches=tuple(bindings))
    model = _RecordingEffect()
    embedding = _RecordingEffect()
    service = pipeline_module.TwoFamilyProposalReadinessService(
        load_hk_v1_coverage_matrix(),
        _CurrentHeads(),
        _EvidenceStore(documents),
        model,
        embedding,
    )

    with pytest.raises(ValueError, match=r"^HK_V1_TWO_FAMILY_PREPARED_BATCH_INVALID$"):
        service.prepare(request)

    assert model.requests == []
    assert embedding.requests == []


@pytest.mark.parametrize("mutation", ["PRE_V1_EMPTY", "EMPTY_CASES", "INVALID_LEG_CYCLE"])
def test_proposal_rejects_manifest_shapes_the_producers_cannot_issue(mutation: str) -> None:
    """Mutation caught: weaker reporting parsers cannot admit producer-impossible manifests."""
    request = _request()
    if mutation == "PRE_V1_EMPTY":
        request = replace(
            request,
            accepted_observation_cutoff="1996-12-31T00:00:00Z",
            legislation_manifest=_legislation_manifest(cutoff="1996-12-31T00:00:00+00:00"),
            cases_manifest=_cases_manifest(cutoff="1996-12-31T00:00:00Z"),
        )
    elif mutation == "EMPTY_CASES":
        cases = _json_object(_cases_manifest())
        cases["year_dispositions"] = []
        cases.pop("fingerprint")
        request = replace(request, cases_manifest=_seal(cases))
    else:
        request = replace(request, legislation_manifest=_legislation_manifest(cycle_id="not-cycle"))
    model = _RecordingEffect()
    embedding = _RecordingEffect()
    service = pipeline_module.TwoFamilyProposalReadinessService(
        load_hk_v1_coverage_matrix(),
        _CurrentHeads(),
        _EvidenceStore(_all_documents()),
        model,
        embedding,
    )

    with pytest.raises(ValueError, match=r"^HK_V1_TWO_FAMILY_ACQUISITION_INVALID$"):
        service.prepare(request)

    assert model.requests == []
    assert embedding.requests == []


def test_profile_fingerprints_and_capability_refs_without_stored_receipts_are_rejected() -> None:
    """Mutation caught: caller syntax cannot establish model or embedding capability evidence."""
    model = _RecordingEffect()
    embedding = _RecordingEffect()
    service = pipeline_module.TwoFamilyProposalReadinessService(
        load_hk_v1_coverage_matrix(),
        _CurrentHeads(),
        _EvidenceStore(_prepared_documents()),
        model,
        embedding,
    )

    with pytest.raises(ValueError, match=r"^HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_READ_FAILED$"):
        service.prepare(_request())

    assert model.requests == []
    assert embedding.requests == []


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("FABRICATED_PROFILE", "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_READ_FAILED"),
        ("FABRICATED_EVIDENCE_REF", "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_READ_FAILED"),
        ("PROFILE_FINGERPRINT", "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_INVALID"),
        ("PROFILE_STATUS", "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_INVALID"),
        ("CAPABILITY_KIND", "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_INVALID"),
        ("CAPABILITY_STATUS", "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_INVALID"),
        ("CAPABILITY_PROFILE", "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_INVALID"),
        ("CAPABILITY_PATH", "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_INVALID"),
    ],
)
def test_hostile_semantic_receipts_are_rejected_before_effects(
    mutation: str, expected_code: str
) -> None:
    """Mutation caught: syntax-shaped semantic evidence cannot establish capability."""
    request = _request()
    documents = _all_documents()
    model_profile_ref = (
        f"proposal-readiness/profile-receipts/model/{_FP_D.removeprefix('sha256:')}.json"
    )
    model_evidence_ref = request.model_capability_evidence_ref
    if mutation == "FABRICATED_PROFILE":
        request = replace(request, model_profile_fingerprint=_FP_F)
    elif mutation == "FABRICATED_EVIDENCE_REF":
        request = replace(
            request,
            model_capability_evidence_ref=(
                "proposal-readiness/capability-evidence/model/" + "f" * 64 + ".json"
            ),
        )
    elif mutation == "PROFILE_FINGERPRINT":
        body = _json_object(documents[model_profile_ref])
        body["fingerprint"] = _FP_F
        documents[model_profile_ref] = canonicalize(body)
    elif mutation == "PROFILE_STATUS":
        body = _json_object(documents[model_profile_ref])
        body.pop("fingerprint")
        body["status"] = "ENABLED"
        documents[model_profile_ref] = _seal(body)
    elif mutation == "CAPABILITY_PATH":
        request = replace(
            request,
            model_capability_evidence_ref=request.embedding_capability_evidence_ref,
        )
    else:
        body = _json_object(documents[model_evidence_ref])
        body.pop("fingerprint")
        if mutation == "CAPABILITY_KIND":
            body["capability"] = "EMBEDDING"
        elif mutation == "CAPABILITY_STATUS":
            body["status"] = "ENABLED"
        else:
            body["profile_fingerprint"] = _FP_F
        documents[model_evidence_ref] = _seal(body)
    model = _RecordingEffect()
    embedding = _RecordingEffect()
    service = pipeline_module.TwoFamilyProposalReadinessService(
        load_hk_v1_coverage_matrix(),
        _CurrentHeads(),
        _EvidenceStore(documents),
        model,
        embedding,
    )

    with pytest.raises(ValueError, match=f"^{expected_code}$"):
        service.prepare(request)

    assert model.requests == []
    assert embedding.requests == []
