"""Task 7 verified Legislation batch preparation tests."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import asklegal_legal_processing_worker.v1_infrastructure as infrastructure_module
import asklegal_legal_processing_worker.v1_pipeline as pipeline_module
import pytest
from _v1_semantic_profile_fixture import exact_semantic_profiles
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_processing import SemanticProfileSet
from asklegal_reporting import verify_provider_disabled_semantic_capability

_ACQUISITION_FP = "sha256:" + "a" * 64
_HEAD_FP = "sha256:" + "b" * 64


def test_verified_legislation_batch_is_stored_under_exact_evidence_and_profile(
    tmp_path: Path,
) -> None:
    """Mutation caught: profile/evidence drift can otherwise overwrite prepared work."""
    evidence_body = canonicalize(
        checked_json_value(
            {
                "language": "en",
                "subject_id": "cap-1-section-2",
                "text": "The inert verified section text.",
            }
        )
    )
    evidence_fingerprint = f"sha256:{sha256(evidence_body).hexdigest()}"
    text_fingerprint = f"sha256:{sha256(b'The inert verified section text.').hexdigest()}"
    evidence_type = pipeline_module.VerifiedBatchEvidence
    input_type = pipeline_module.VerifiedBatchInput
    store_type = infrastructure_module.LocalVerifiedBatchStore
    prepare = pipeline_module.prepare_verified_batch
    semantic_profiles = exact_semantic_profiles()
    request = input_type(
        material_family="LEGISLATION",
        scope_id="HK-LEG-ORDINANCES",
        batch_id="legislation-cap-1",
        observation_cutoff="1997-12-31T00:00:00Z",
        acquisition_manifest_fingerprint=_ACQUISITION_FP,
        journal_head_fingerprint=_HEAD_FP,
        semantic_profiles=semantic_profiles,
        evidence_items=(
            evidence_type(
                evidence_ref="evidence/legislation/cap-1-section-2",
                content=evidence_body,
                fingerprint=evidence_fingerprint,
            ),
        ),
    )
    store = store_type(tmp_path / "prepared")

    prepared = prepare(request, store)
    restarted = prepare(request, store_type(tmp_path / "prepared"))
    document = parse_json_bytes(prepared.content, max_bytes=1_000_000)
    assert type(document) is dict
    unsigned = dict(document)
    embedded_fingerprint = unsigned.pop("fingerprint")
    assert embedded_fingerprint == f"sha256:{sha256(canonicalize(unsigned)).hexdigest()}"
    assert prepared.artifact_fingerprint == f"sha256:{sha256(prepared.content).hexdigest()}"
    model_requests = document["model_requests"]
    assert type(model_requests) is list
    first_request = model_requests[0]
    assert type(first_request) is dict

    assert restarted == prepared
    assert document == {
        "acquisition_manifest_fingerprint": _ACQUISITION_FP,
        "batch_id": "legislation-cap-1",
        "capability_evidence_ref": prepared.capability_evidence_ref,
        "evidence_items": [
            {
                "evidence_ref": "evidence/legislation/cap-1-section-2",
                "fingerprint": evidence_fingerprint,
                "language": "en",
                "subject_id": "cap-1-section-2",
                "text_fingerprint": text_fingerprint,
            }
        ],
        "evidence_set_fingerprint": prepared.evidence_set_fingerprint,
        "fingerprint": embedded_fingerprint,
        "journal_head_fingerprint": _HEAD_FP,
        "material_family": "LEGISLATION",
        "model_requests": [
            {
                "evidence_fingerprint": evidence_fingerprint,
                "evidence_ref": "evidence/legislation/cap-1-section-2",
                "request_id": first_request["request_id"],
                "semantic_profile_fingerprint": semantic_profiles.fingerprint,
                "subject_id": "cap-1-section-2",
            }
        ],
        "observation_cutoff": "1997-12-31T00:00:00Z",
        "provider_invocation_count": 0,
        "release_state": "WITHHELD_PENDING_TWO_FAMILY_RECONCILIATION",
        "schema_id": "asklegal.hk-v1-prepared-verified-batch/v1",
        "scope_id": "HK-LEG-ORDINANCES",
        "semantic_profile_fingerprint": semantic_profiles.fingerprint,
    }
    assert prepared.evidence_set_fingerprint.removeprefix("sha256:") in prepared.artifact_ref
    assert semantic_profiles.fingerprint.removeprefix("sha256:") in prepared.artifact_ref
    assert (
        store.read_exact(prepared.artifact_ref, prepared.artifact_fingerprint) == prepared.content
    )
    assert prepared.provider_invocation_count == 0
    assert prepared.release_state == "WITHHELD_PENDING_TWO_FAMILY_RECONCILIATION"
    profile_receipt = parse_json_bytes(
        store.read_exact(prepared.semantic_profile_receipt_ref),
        max_bytes=100_000,
    )
    capability_evidence = parse_json_bytes(
        store.read_exact(prepared.capability_evidence_ref),
        max_bytes=100_000,
    )
    assert type(profile_receipt) is dict
    assert type(capability_evidence) is dict
    assert profile_receipt["profile_fingerprint"] == semantic_profiles.fingerprint
    assert profile_receipt["status"] == "PROVIDER_DISABLED_PREPARATION_ONLY"
    assert capability_evidence["profile_receipt_ref"] == prepared.semantic_profile_receipt_ref
    assert capability_evidence["observation_cutoff"] == "1997-12-31T00:00:00Z"
    assert capability_evidence["status"] == "PROVIDER_DISABLED_PREPARATION_ONLY"
    verified_capability = verify_provider_disabled_semantic_capability(
        "MODEL",
        prepared.semantic_profile_receipt_ref,
        store.read_exact(prepared.semantic_profile_receipt_ref),
        prepared.capability_evidence_ref,
        store.read_exact(prepared.capability_evidence_ref),
        "1997-12-31T00:00:00Z",
    )
    assert verified_capability.profile_fingerprint == semantic_profiles.fingerprint


def test_verified_batch_rejects_a_forged_profile_identity_before_storage() -> None:
    """Mutation caught: a caller-chosen fingerprint cannot stand in for an exact profile."""
    evidence_body = canonicalize(
        checked_json_value({"language": "en", "subject_id": "cap-1", "text": "Evidence."})
    )

    class _Store:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def store_exact(self, logical_key: str, content: bytes, fingerprint: str) -> bytes:
            del content, fingerprint
            self.calls.append(logical_key)
            return b""

    request = pipeline_module.VerifiedBatchInput(
        material_family="LEGISLATION",
        scope_id="HK-LEG-ORDINANCES",
        batch_id="legislation-cap-1",
        observation_cutoff="1997-12-31T00:00:00Z",
        acquisition_manifest_fingerprint=_ACQUISITION_FP,
        journal_head_fingerprint=_HEAD_FP,
        semantic_profiles=object.__new__(SemanticProfileSet),
        evidence_items=(
            pipeline_module.VerifiedBatchEvidence(
                evidence_ref="evidence/legislation/cap-1",
                content=evidence_body,
                fingerprint=f"sha256:{sha256(evidence_body).hexdigest()}",
            ),
        ),
    )
    store = _Store()

    with pytest.raises(
        pipeline_module.ProcessingPipelineError,
        match=r"^VERIFIED_BATCH_PROFILE_INVALID$",
    ):
        pipeline_module.prepare_verified_batch(request, store)

    assert store.calls == []
