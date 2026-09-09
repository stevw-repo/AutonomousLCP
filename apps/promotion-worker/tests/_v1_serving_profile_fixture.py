"""Loader-issued deterministic serving-profile fixture for Task 8 tests."""

from hashlib import sha256

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_promotion import ServingCapabilityProfile, load_serving_capability_profile


class _Reader:
    def __init__(self, raw: bytes) -> None:
        self.reference = ImmutableReference(
            ReferenceType.CAPABILITY_PROFILE,
            "cap_" + "1" * 48,
            "sha256:" + sha256(raw).hexdigest(),
        )
        self._raw = raw

    def read_exact(self, reference: ImmutableReference) -> bytes:
        assert reference == self.reference
        return self._raw


def exact_serving_profile() -> ServingCapabilityProfile:
    embedding = {
        "allowed_environments": ["dev"],
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
        "tokenizer": "SYNTHETIC_EXACT_V1",
    }
    projection = dict(embedding)
    projection.pop("profile_fingerprint")
    projection.pop("profile_id")
    fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(projection))).hexdigest()
    embedding["profile_fingerprint"] = fingerprint
    embedding["profile_id"] = "emp_" + sha256(fingerprint.encode()).hexdigest()[:48]
    document = {
        "backup_profile_ref": {
            "fingerprint": "sha256:" + "3" * 64,
            "ref_id": "cap_" + "4" * 48,
            "ref_type": "CAPABILITY_PROFILE",
        },
        "batch_size": 2,
        "dimensions": 4,
        "embedding": embedding,
        "environment": "dev",
        "expires_at": "2099-01-01T00:00:00Z",
        "fingerprint": "",
        "immutable": True,
        "index_prefix": "asklegal-dev-",
        "metric": "cosine",
        "namespace": "synthetic-v1",
        "pinecone_project_id": "proj1",
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
    outer = dict(document)
    outer.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(outer))).hexdigest()
    )
    return load_serving_capability_profile(_Reader(canonicalize(checked_json_value(document))))
