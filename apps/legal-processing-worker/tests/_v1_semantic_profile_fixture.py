"""Exact issued semantic-profile fixture for Task 7 worker tests."""

from hashlib import sha256

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_legal_desks import GenerativeTask
from asklegal_processing import (
    SemanticProfileSet,
    load_semantic_profile_set,
    semantic_prompt_fingerprint,
)


class _Reader:
    """Read one immutable synthetic profile document by exact reference."""

    def __init__(self, raw: bytes) -> None:
        self.reference = ImmutableReference(
            ReferenceType.WORKFLOW_PROFILE,
            f"wap_{'1' * 48}",
            f"sha256:{sha256(raw).hexdigest()}",
        )
        self._raw = raw

    def read_exact(self, reference: ImmutableReference) -> bytes:
        """Return bytes only for the issued exact reference."""
        assert reference == self.reference
        return self._raw


def exact_semantic_profile_bytes() -> bytes:
    """Return one deterministic complete canonical semantic profile document."""
    profiles = [
        {
            "allowed_environments": ["LOCAL_SYNTHETIC"],
            "api_contract": "2026-08-01",
            "content_filter_policy": "STRICT",
            "data_handling_profile": "NO_TRAINING",
            "deployment_name": "synthetic-semantic-v1",
            "evaluator_id": "synthetic-evaluator-v1",
            "evidence_budget_bytes": 2048,
            "expires_at": "2099-01-01T00:00:00Z",
            "geography_class": "SYNTHETIC",
            "input_schema": "asklegal.semantic-task-request/1.0.0",
            "max_output_tokens": 128,
            "model_id": "synthetic-model-v1",
            "model_version": "1.0.0",
            "output_schema": "asklegal.semantic-decision/1.0.0",
            "profile_id": f"semantic-profile-{index}",
            "prompt_fingerprint": semantic_prompt_fingerprint(),
            "provider": "AZURE_OPENAI",
            "resource_class": "SYNTHETIC",
            "retry_policy": "bounded-v1",
            "stateful_features": False,
            "task": task.value,
            "threshold_basis_points": 9000,
            "tokenizer": "o200k_base",
        }
        for index, task in enumerate(GenerativeTask, start=1)
    ]
    document = {
        "billing_denominator_tokens": 1_000_000,
        "billing_rounding_rule": "PER_REQUEST_PER_DIRECTION_CEILING",
        "budget_profiles": [
            {
                "input_cost_microunits_per_million": 1,
                "max_input_tokens": 1024,
                "output_cost_microunits_per_million": 2,
                "profile_id": profile["profile_id"],
            }
            for profile in profiles
        ],
        "cost_limit_microunits": 1000,
        "environment": "LOCAL_SYNTHETIC",
        "expires_at": "2099-01-01T00:00:00Z",
        "fingerprint": "",
        "immutable": True,
        "profiles": profiles,
        "quota_limit_tokens": 4096,
        "request_quota": 64,
        "retry_profile": {
            "attempt_ceiling": 2,
            "backoff_seconds": [1],
            "timeout_seconds": 30,
        },
        "revision": "1.0.0",
        "schema_id": "asklegal.hk-v1-semantic-profile-set",
        "schema_version": "1.1.0",
        "tokenizer_specifications": [
            {
                "distribution_fingerprint": (
                    "sha256:d186a5c60c6a0213f04a7a802264083dea1bbde92a2d4c7069e1a56630aef830"
                ),
                "distribution_name": "tiktoken",
                "distribution_version": "0.12.0",
                "encoding_resource_fingerprint": (
                    "sha256:446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
                ),
                "tokenizer_id": "o200k_base",
            }
        ],
    }
    projection = dict(document)
    projection.pop("fingerprint")
    document["fingerprint"] = (
        f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    )
    return canonicalize(checked_json_value(document))


def exact_semantic_profiles() -> SemanticProfileSet:
    """Issue one deterministic complete provider-disabled semantic profile set."""
    return load_semantic_profile_set(_Reader(exact_semantic_profile_bytes()))
