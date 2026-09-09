"""Task 7 application-owned EMBEDDING evidence issuance tests."""

from __future__ import annotations

from hashlib import sha256

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_promotion import ServingCapabilityProfile, load_serving_capability_profile
from asklegal_promotion_worker.proposal_evidence import (
    PromotionProposalEvidenceError,
    issue_embedding_provider_disabled_evidence,
)
from asklegal_reporting import verify_provider_disabled_semantic_capability


class _Reader:
    def __init__(self, raw: bytes) -> None:
        self.reference = ImmutableReference(
            ReferenceType.CAPABILITY_PROFILE,
            f"cap_{'1' * 48}",
            f"sha256:{sha256(raw).hexdigest()}",
        )
        self._raw = raw

    def read_exact(self, reference: ImmutableReference) -> bytes:
        assert reference == self.reference
        return self._raw


def _profile() -> ServingCapabilityProfile:
    embedding = {
        "allowed_environments": ["LOCAL_SYNTHETIC"],
        "api_contract": "2026-08-01",
        "cost_limit_microunits": 1000,
        "deployment_name": "synthetic-embedding-v1",
        "dimensions": 4,
        "encoding": "FLOAT32",
        "expires_at": "2099-01-01T00:00:00Z",
        "geography_class": "SYNTHETIC",
        "max_input_tokens": 2048,
        "metric": "cosine",
        "model_id": "synthetic-embedding-model-v1",
        "model_version": "1.0.0",
        "normalization": "UNIT_LENGTH",
        "profile_fingerprint": "",
        "profile_id": "",
        "provider": "AZURE_OPENAI",
        "resource_class": "SYNTHETIC",
        "stateful_features": False,
        "tokenizer": "synthetic-tokenizer-v1",
    }
    projection = dict(embedding)
    projection.pop("profile_fingerprint")
    projection.pop("profile_id")
    fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    embedding["profile_fingerprint"] = fingerprint
    embedding["profile_id"] = f"emp_{sha256(fingerprint.encode()).hexdigest()[:48]}"
    document = checked_json_value(
        {
            "backup_profile_ref": {
                "fingerprint": f"sha256:{'3' * 64}",
                "ref_id": f"cap_{'4' * 48}",
                "ref_type": "CAPABILITY_PROFILE",
            },
            "batch_size": 2,
            "dimensions": 4,
            "embedding": embedding,
            "environment": "LOCAL_SYNTHETIC",
            "expires_at": "2099-01-01T00:00:00Z",
            "fingerprint": "",
            "immutable": True,
            "index_prefix": "asklegal-local-synthetic-",
            "metric": "cosine",
            "namespace": "synthetic-v1",
            "pinecone_project_id": "synthetic-project-v1",
            "readback_page_size": 2,
            "provider_timeout_seconds": 60,
            "target_timeout_seconds": 60,
            "outage_behavior": "FAIL_CLOSED",
            "serving_metadata_keys": [
                "authority_note",
                "country",
                "jurisdiction",
                "source",
                "text",
                "type",
            ],
            "schema_id": "asklegal.hk-v1-serving-capability-profile",
            "schema_version": "1.0.0",
        }
    )
    assert type(document) is dict
    unsigned = dict(document)
    unsigned.pop("fingerprint")
    document["fingerprint"] = f"sha256:{sha256(canonicalize(unsigned)).hexdigest()}"
    return load_serving_capability_profile(_Reader(canonicalize(document)))


def _unissued_shell(source: ServingCapabilityProfile) -> ServingCapabilityProfile:
    value = object.__new__(ServingCapabilityProfile)
    for name in (
        "embedding",
        "pinecone_project_id",
        "index_prefix",
        "dimensions",
        "metric",
        "namespace",
        "batch_size",
        "readback_page_size",
        "provider_timeout_seconds",
        "target_timeout_seconds",
        "outage_behavior",
        "serving_metadata_keys",
        "backup_profile_ref",
        "expires_at",
        "environment",
        "fingerprint",
        "_witness",
    ):
        object.__setattr__(value, name, getattr(source, name))
    return value


def test_promotion_worker_issues_embedding_evidence_from_live_profile_authority() -> None:
    """Issued embedding identity survives exact stored-document verification."""
    loaded = _profile()
    profile_receipt, capability_evidence = issue_embedding_provider_disabled_evidence(
        loaded, "1997-12-31T00:00:00Z"
    )
    stored = {
        profile_receipt.logical_ref: profile_receipt.content,
        capability_evidence.logical_ref: capability_evidence.content,
    }

    verified = verify_provider_disabled_semantic_capability(
        "EMBEDDING",
        profile_receipt.logical_ref,
        stored[profile_receipt.logical_ref],
        capability_evidence.logical_ref,
        stored[capability_evidence.logical_ref],
        "1997-12-31T00:00:00Z",
    )

    assert verified.profile_fingerprint == loaded.embedding.profile_fingerprint
    assert verified.evidence_ref == capability_evidence.logical_ref
    assert verified.status == "PROVIDER_DISABLED_PREPARATION_ONLY"


def test_promotion_worker_rejects_unissued_same_type_profile_before_issuance() -> None:
    """A coherent public shell cannot mint PROMOTION_WORKER capability evidence."""
    unissued = _unissued_shell(_profile())

    with pytest.raises(
        PromotionProposalEvidenceError,
        match=r"^EMBEDDING_PROFILE_AUTHORITY_INVALID$",
    ):
        issue_embedding_provider_disabled_evidence(unissued, "1997-12-31T00:00:00Z")
