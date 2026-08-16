"""Pure fingerprint, manifest, embedding-request, and target-name construction."""

from __future__ import annotations

import re
from hashlib import sha256

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .model import (
    EmbeddingProfile,
    EmbeddingProfileInput,
    EmbeddingRequest,
    EmbeddingRequestInput,
    PromotionError,
    PromotionErrorCode,
    PromotionManifest,
    PromotionPlan,
)

_INDEX_NAME_LIMIT = 40
_PROJECT_INDEX_NAME_LIMIT = 52


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _embedding_profile_body(profile: EmbeddingProfile) -> dict[str, object]:
    return {
        "allowed_environments": list(profile.allowed_environments),
        "api_contract": profile.api_contract,
        "cost_limit_microunits": profile.cost_limit_microunits,
        "deployment_name": profile.deployment_name,
        "dimensions": profile.dimensions,
        "encoding": profile.encoding,
        "expires_at": profile.expires_at,
        "geography_class": profile.geography_class,
        "max_input_tokens": profile.max_input_tokens,
        "metric": profile.metric,
        "model_id": profile.model_id,
        "model_version": profile.model_version,
        "normalization": profile.normalization,
        "provider": profile.provider,
        "resource_class": profile.resource_class,
        "stateful_features": profile.stateful_features,
        "tokenizer": profile.tokenizer,
    }


def verify_embedding_profile(profile: EmbeddingProfile) -> None:
    """Reject a profile whose issued identity or fingerprint does not match its fields."""
    fingerprint = _fingerprint(canonicalize(checked_json_value(_embedding_profile_body(profile))))
    if profile.profile_fingerprint != fingerprint or profile.profile_id != _stable_id(
        "emp", fingerprint
    ):
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "profile fingerprint")


def freeze_embedding_profile(inputs: EmbeddingProfileInput) -> EmbeddingProfile:
    """Issue one fingerprinted immutable embedding profile."""
    provisional = EmbeddingProfile(
        "",
        "",
        inputs.provider,
        inputs.resource_class,
        inputs.geography_class,
        inputs.deployment_name,
        inputs.model_id,
        inputs.model_version,
        inputs.api_contract,
        inputs.tokenizer,
        inputs.dimensions,
        inputs.encoding,
        inputs.normalization,
        inputs.metric,
        inputs.max_input_tokens,
        inputs.cost_limit_microunits,
        inputs.expires_at,
        inputs.allowed_environments,
        inputs.stateful_features,
    )
    fingerprint = _fingerprint(
        canonicalize(checked_json_value(_embedding_profile_body(provisional)))
    )
    return EmbeddingProfile(
        _stable_id("emp", fingerprint),
        fingerprint,
        provisional.provider,
        provisional.resource_class,
        provisional.geography_class,
        provisional.deployment_name,
        provisional.model_id,
        provisional.model_version,
        provisional.api_contract,
        provisional.tokenizer,
        provisional.dimensions,
        provisional.encoding,
        provisional.normalization,
        provisional.metric,
        provisional.max_input_tokens,
        provisional.cost_limit_microunits,
        provisional.expires_at,
        provisional.allowed_environments,
        provisional.stateful_features,
    )


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def _manifest_body(plan: PromotionPlan) -> dict[str, object]:
    return {
        "action_ids": list(plan.action_ids),
        "base_serving_state_id": plan.base_serving_state_id,
        "batch_size": plan.batch_size,
        "candidate_serving_state_fingerprint": plan.candidate_serving_state_fingerprint,
        "candidate_serving_state_id": plan.candidate_serving_state_id,
        "capability_enabled": plan.capability_enabled,
        "coverage_fingerprint": plan.coverage_status.fingerprint,
        "desired_state_fingerprint": plan.desired_state.inventory_fingerprint,
        "embedding_profile_fingerprint": plan.embedding_profile.profile_fingerprint,
        "environment": plan.environment,
        "exact_retirement_target_ids": list(plan.exact_retirement_target_ids),
        "freeze_date": plan.freeze_date,
        "jurisdiction": plan.jurisdiction,
        "project_id": plan.project_id,
        "rollback_serving_state_id": plan.rollback_serving_state_id,
        "valid_from": plan.valid_from,
        "valid_until": plan.valid_until,
        "validity_predicates": [list(item) for item in plan.validity_predicates],
    }


def freeze_promotion_manifest(plan: PromotionPlan) -> PromotionManifest:
    """Freeze one complete manifest without authorizing its effects."""
    if (
        plan.batch_size < 1
        or not plan.validity_predicates
        or len(plan.validity_predicates) != len(set(plan.validity_predicates))
        or not plan.action_ids
        or len(plan.action_ids) != len(set(plan.action_ids))
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "manifest inputs")
    body = _manifest_body(plan)
    fingerprint = _fingerprint(canonicalize(checked_json_value(body)))
    return PromotionManifest(
        _stable_id("pmn", fingerprint),
        fingerprint,
        plan.environment,
        plan.jurisdiction,
        plan.freeze_date,
        plan.valid_from,
        plan.valid_until,
        plan.base_serving_state_id,
        plan.candidate_serving_state_id,
        plan.candidate_serving_state_fingerprint,
        plan.rollback_serving_state_id,
        plan.desired_state,
        plan.coverage_status,
        plan.embedding_profile,
        plan.validity_predicates,
        plan.batch_size,
        plan.project_id,
        plan.action_ids,
        plan.exact_retirement_target_ids,
        plan.capability_enabled,
    )


def verify_promotion_manifest(manifest: PromotionManifest) -> None:
    """Reject any object whose fields drifted from its frozen fingerprint."""
    body = _manifest_body(
        PromotionPlan(
            manifest.environment,
            manifest.jurisdiction,
            manifest.freeze_date,
            manifest.valid_from,
            manifest.valid_until,
            manifest.base_serving_state_id,
            manifest.candidate_serving_state_id,
            manifest.candidate_serving_state_fingerprint,
            manifest.rollback_serving_state_id,
            manifest.desired_state,
            manifest.coverage_status,
            manifest.embedding_profile,
            manifest.validity_predicates,
            manifest.batch_size,
            manifest.project_id,
            manifest.action_ids,
            manifest.exact_retirement_target_ids,
            manifest.capability_enabled,
        )
    )
    if _fingerprint(canonicalize(checked_json_value(body))) != manifest.fingerprint:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT)


def pinecone_index_name(
    environment: str,
    jurisdiction: str,
    freeze_date: str,
    state_fingerprint: str,
    project_id: str,
) -> str:
    """Apply the accepted exact final Pinecone naming contract."""
    if (
        environment not in {"dev", "stg", "prd"}
        or re.fullmatch(r"[a-z0-9]{3}", jurisdiction) is None
        or re.fullmatch(r"[0-9]{8}", freeze_date) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", state_fingerprint) is None
    ):
        raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID)
    name = f"asklegal-{environment}-{jurisdiction}-{freeze_date}-{state_fingerprint[7:19]}"
    if (
        len(name) > _INDEX_NAME_LIMIT
        or len(f"{name}-{project_id}") > _PROJECT_INDEX_NAME_LIMIT
        or re.fullmatch(r"[a-z0-9-]+", name) is None
    ):
        raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID)
    return name


def embedding_request(
    inputs: EmbeddingRequestInput,
    profile: EmbeddingProfile,
) -> EmbeddingRequest:
    """Bind only exact metadata.text bytes and the complete profile."""
    if not inputs.text:
        raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "empty text")
    text_bytes = inputs.text.encode()
    text_fingerprint = _fingerprint(text_bytes)
    token_count = len(text_bytes)
    if token_count > profile.max_input_tokens:
        raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "oversized text")
    cache_key = _fingerprint((text_fingerprint + profile.profile_fingerprint).encode())
    request_id = _stable_id(
        "emr",
        inputs.record_id,
        inputs.serving_payload_fingerprint,
        cache_key,
        inputs.batch_id,
        str(inputs.position),
    )
    return EmbeddingRequest(
        request_id,
        inputs.record_id,
        inputs.serving_payload_fingerprint,
        inputs.text,
        text_fingerprint,
        token_count,
        profile.profile_id,
        inputs.batch_id,
        inputs.position,
        cache_key,
    )
