"""Canonical transferred capability receipts for control-plane tests."""

from __future__ import annotations

from hashlib import sha256

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

_MODEL_PROFILE_FINGERPRINT = "sha256:" + "d" * 64
_EMBEDDING_PROFILE_FINGERPRINT = "sha256:" + "e" * 64


def canonical_capability_artifacts(
    cutoff: str,
) -> tuple[dict[str, bytes], str, str, str, str]:
    """Provide exact transferred bytes; issuer authority is tested in each owner."""
    model_profile_ref, model_profile, model_evidence_ref, model_evidence = _artifacts(
        "MODEL",
        "LEGAL_PROCESSING_WORKER",
        "generative_llm_provider",
        _MODEL_PROFILE_FINGERPRINT,
        cutoff,
    )
    embedding_profile_ref, embedding_profile, embedding_evidence_ref, embedding_evidence = (
        _artifacts(
            "EMBEDDING",
            "PROMOTION_WORKER",
            "embedding_provider",
            _EMBEDDING_PROFILE_FINGERPRINT,
            cutoff,
        )
    )
    return (
        {
            model_profile_ref: model_profile,
            model_evidence_ref: model_evidence,
            embedding_profile_ref: embedding_profile,
            embedding_evidence_ref: embedding_evidence,
        },
        model_evidence_ref,
        embedding_evidence_ref,
        _MODEL_PROFILE_FINGERPRINT,
        _EMBEDDING_PROFILE_FINGERPRINT,
    )


def _artifacts(
    capability: str,
    application: str,
    role: str,
    profile_fingerprint: str,
    cutoff: str,
) -> tuple[str, bytes, str, bytes]:
    profile_body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1-provider-disabled-profile-receipt/v1",
            "capability": capability,
            "issuer_application": application,
            "profile_fingerprint": profile_fingerprint,
            "status": "PROVIDER_DISABLED_PREPARATION_ONLY",
        }
    )
    profile_content, profile_receipt_fingerprint = _seal(profile_body)
    profile_ref = (
        f"proposal-readiness/profile-receipts/{capability.lower()}/"
        f"{profile_fingerprint.removeprefix('sha256:')}.json"
    )
    evidence_body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1-provider-disabled-capability-evidence/v1",
            "capability": capability,
            "application": application,
            "role": role,
            "observation_cutoff": cutoff,
            "profile_receipt_ref": profile_ref,
            "profile_receipt_fingerprint": profile_receipt_fingerprint,
            "profile_fingerprint": profile_fingerprint,
            "status": "PROVIDER_DISABLED_PREPARATION_ONLY",
        }
    )
    evidence_content, evidence_fingerprint = _seal(evidence_body)
    evidence_ref = (
        f"proposal-readiness/capability-evidence/{capability.lower()}/"
        f"{evidence_fingerprint.removeprefix('sha256:')}.json"
    )
    return profile_ref, profile_content, evidence_ref, evidence_content


def _seal(body: object) -> tuple[bytes, str]:
    typed = checked_json_value(body)
    assert type(typed) is dict
    fingerprint = f"sha256:{sha256(canonicalize(typed)).hexdigest()}"
    return canonicalize({**typed, "fingerprint": fingerprint}), fingerprint
