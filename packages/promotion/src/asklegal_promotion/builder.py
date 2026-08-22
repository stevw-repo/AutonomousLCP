"""Pure fingerprint, manifest, embedding-request, and target-name construction."""

from __future__ import annotations

import re
from hashlib import sha256

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import PROPOSAL_ROLE_PATHS, verify_v1_coverage_release_gate
from asklegal_evidence_vault import ExactObjectReference, VaultName

from .model import (
    EmbeddingProfile,
    EmbeddingProfileInput,
    EmbeddingRequest,
    EmbeddingRequestInput,
    PromotionApprovalSnapshot,
    PromotionError,
    PromotionErrorCode,
    PromotionManifest,
    PromotionPlan,
    ProposalMemberReceipt,
    StoredProposalPackage,
    TargetRecord,
)

_INDEX_NAME_LIMIT = 40
_PROJECT_INDEX_NAME_LIMIT = 52
_PREDICATE_PARTS = 3

SERVING_METADATA_KEYS = (
    "authority_note",
    "country",
    "jurisdiction",
    "source",
    "text",
    "type",
)
"""The exact closed property set of the serving payload, in canonical order."""

_SERVING_METADATA_LIMIT = 40_000
"""The target rejects a metadata object above 40 KB. Refusing beats truncating a warning."""


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _canonical(value: object) -> bytes:
    return canonicalize(checked_json_value(value))


def serving_metadata(record: TargetRecord) -> dict[str, str]:
    """Build exactly the six-property serving payload one record must carry.

    Built from the contract rather than from the caller, so a field the caller
    forgot is a refused write rather than a record that lands without it.
    """
    payload = {
        "authority_note": record.authority_note,
        "country": record.country,
        "jurisdiction": record.jurisdiction,
        "source": record.source,
        "text": record.metadata_text,
        "type": record.material_type,
    }
    empty = sorted(key for key, value in payload.items() if not value)
    if empty:
        message = f"record {record.record_id} carries no {', '.join(empty)}"
        raise PromotionError(PromotionErrorCode.SERVING_PAYLOAD_INVALID, message)
    encoded = _canonical(payload)
    if len(encoded) > _SERVING_METADATA_LIMIT:
        message = (
            f"record {record.record_id} payload is {len(encoded)} bytes, "
            f"over the {_SERVING_METADATA_LIMIT} limit"
        )
        raise PromotionError(PromotionErrorCode.SERVING_PAYLOAD_INVALID, message)
    return payload


def serving_metadata_fingerprint(payload: dict[str, str]) -> str:
    """Fingerprint exactly the six-field payload, as the corpus release does.

    The same bytes over the same closed key set, so a fingerprint computed here
    equals the `serving_payload_fingerprint` the approved release carries.
    """
    if set(payload) != set(SERVING_METADATA_KEYS):
        message = f"payload keys {sorted(payload)} are not the six serving fields"
        raise PromotionError(PromotionErrorCode.SERVING_PAYLOAD_INVALID, message)
    return _fingerprint(_canonical(dict(payload)))


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


def freeze_v1_promotion_manifest(plan: PromotionPlan) -> PromotionManifest:
    """Freeze a V1 promotion only after exact source-cycle release eligibility."""
    verify_v1_coverage_release_gate(plan.coverage_status)
    return freeze_promotion_manifest(plan)


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


def promotion_manifest_bytes(manifest: PromotionManifest) -> bytes:
    """Render the exact canonical bytes whose fingerprint identifies the manifest."""
    verify_promotion_manifest(manifest)
    plan = PromotionPlan(
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
    return canonicalize(checked_json_value(_manifest_body(plan)))


def promotion_approval_snapshot_from_bytes(
    content: bytes,
    *,
    expected_manifest_id: str,
    expected_fingerprint: str,
) -> PromotionApprovalSnapshot:
    """Recover only exact Approval facts from one canonical executable manifest."""
    try:
        document = parse_json_bytes(content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise PromotionError(
            PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest JSON"
        ) from error
    expected_fields = {
        "action_ids",
        "base_serving_state_id",
        "batch_size",
        "candidate_serving_state_fingerprint",
        "candidate_serving_state_id",
        "capability_enabled",
        "coverage_fingerprint",
        "desired_state_fingerprint",
        "embedding_profile_fingerprint",
        "environment",
        "exact_retirement_target_ids",
        "freeze_date",
        "jurisdiction",
        "project_id",
        "rollback_serving_state_id",
        "valid_from",
        "valid_until",
        "validity_predicates",
    }
    if not isinstance(document, dict) or set(document) != expected_fields:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest fields")
    if canonicalize(document) != content:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest canonical")
    actual_fingerprint = _fingerprint(content)
    if (
        actual_fingerprint != expected_fingerprint
        or _stable_id("pmn", actual_fingerprint) != expected_manifest_id
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest identity")

    action_ids = _json_string_sequence(document, "action_ids")
    retirements = _json_string_sequence(document, "exact_retirement_target_ids")
    predicates = _json_predicates(document)
    valid_from = _json_text(document, "valid_from")
    valid_until = _json_text(document, "valid_until")
    fingerprints = (
        _json_text(document, "candidate_serving_state_fingerprint"),
        _json_text(document, "coverage_fingerprint"),
        _json_text(document, "desired_state_fingerprint"),
        _json_text(document, "embedding_profile_fingerprint"),
    )
    if (
        not action_ids
        or len(action_ids) != len(set(action_ids))
        or len(retirements) != len(set(retirements))
        or not predicates
        or len(predicates) != len(set(predicates))
        or valid_from >= valid_until
        or any(re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None for value in fingerprints)
        or _json_integer(document, "batch_size") < 1
        or type(document.get("capability_enabled")) is not bool
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "promotion manifest values")
    for field in (
        "environment",
        "freeze_date",
        "jurisdiction",
        "project_id",
        "rollback_serving_state_id",
    ):
        _json_text(document, field)
    return PromotionApprovalSnapshot(
        expected_manifest_id,
        expected_fingerprint,
        _json_text(document, "base_serving_state_id"),
        _json_text(document, "candidate_serving_state_id"),
        valid_from,
        valid_until,
        predicates,
    )


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


def _object_reference_document(reference: ExactObjectReference) -> dict[str, object]:
    return {
        "byte_length": reference.byte_length,
        "fingerprint": reference.fingerprint,
        "logical_key": reference.logical_key,
        "vault": reference.vault.value,
        "version_id": reference.version_id,
    }


def proposal_receipt_document(receipt: StoredProposalPackage) -> dict[str, object]:
    """Render the closed Management Register value for one stored proposal."""
    return {
        "manifest_reference": _object_reference_document(receipt.manifest_reference),
        "members": [
            {
                "path": member.path,
                "reference": _object_reference_document(member.reference),
                "role": member.role,
            }
            for member in receipt.members
        ],
        "package_fingerprint": receipt.package_fingerprint,
        "package_id": receipt.package_id,
        "promotion_manifest_fingerprint": receipt.promotion_manifest_fingerprint,
        "promotion_manifest_id": receipt.promotion_manifest_id,
    }


def proposal_receipt_fingerprint(receipt: StoredProposalPackage) -> str:
    """Fingerprint the complete portable receipt without its claimed fingerprint."""
    return _fingerprint(canonicalize(checked_json_value(proposal_receipt_document(receipt))))


def verify_stored_proposal_package(receipt: StoredProposalPackage) -> None:
    """Reject role, vault, or receipt-fingerprint drift before any package read."""
    if (
        tuple(member.role for member in receipt.members) != tuple(sorted(PROPOSAL_ROLE_PATHS))
        or any(
            PROPOSAL_ROLE_PATHS.get(member.role) != member.path
            or member.reference.vault is not VaultName.PRIMARY
            for member in receipt.members
        )
        or receipt.manifest_reference.vault is not VaultName.PRIMARY
        or proposal_receipt_fingerprint(receipt) != receipt.receipt_fingerprint
    ):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal receipt")


def stored_proposal_package_from_bytes(content: bytes) -> StoredProposalPackage:
    """Parse one canonical registered receipt into exact vault references."""
    document = parse_json_bytes(content, max_bytes=1_000_000)
    expected = {
        "manifest_reference",
        "members",
        "package_fingerprint",
        "package_id",
        "promotion_manifest_fingerprint",
        "promotion_manifest_id",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal document")
    if canonicalize(document) != content:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal canonical bytes")
    raw_members = document.get("members")
    if not isinstance(raw_members, list):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal members")
    members = tuple(_proposal_member(value) for value in raw_members)
    provisional = StoredProposalPackage(
        _json_text(document, "package_id"),
        _json_text(document, "package_fingerprint"),
        _json_text(document, "promotion_manifest_id"),
        _json_text(document, "promotion_manifest_fingerprint"),
        members,
        _object_reference(document.get("manifest_reference")),
        _fingerprint(content),
    )
    verify_stored_proposal_package(provisional)
    return provisional


def _proposal_member(value: JsonValue) -> ProposalMemberReceipt:
    if not isinstance(value, dict) or set(value) != {"path", "reference", "role"}:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal member")
    return ProposalMemberReceipt(
        _json_text(value, "role"),
        _json_text(value, "path"),
        _object_reference(value.get("reference")),
    )


def _object_reference(value: JsonValue | None) -> ExactObjectReference:
    expected = {"byte_length", "fingerprint", "logical_key", "vault", "version_id"}
    if not isinstance(value, dict) or set(value) != expected:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "stored proposal reference")
    try:
        return ExactObjectReference(
            VaultName(_json_text(value, "vault")),
            _json_text(value, "logical_key"),
            _json_text(value, "version_id"),
            _json_text(value, "fingerprint"),
            _json_integer(value, "byte_length"),
        )
    except (TypeError, ValueError) as error:
        raise PromotionError(
            PromotionErrorCode.MANIFEST_DRIFT,
            "stored proposal reference",
        ) from error


def _json_text(document: dict[str, JsonValue], field: str) -> str:
    value = document.get(field)
    if type(value) is not str or not value:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, field)
    return value


def _json_integer(document: dict[str, JsonValue], field: str) -> int:
    value = document.get(field)
    if type(value) is not int:
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, field)
    return value


def _json_string_sequence(document: dict[str, JsonValue], field: str) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list) or any(type(item) is not str or not item for item in value):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, field)
    return tuple(item for item in value if type(item) is str)


def _json_predicates(document: dict[str, JsonValue]) -> tuple[tuple[str, str, str], ...]:
    value = document.get("validity_predicates")
    if not isinstance(value, list):
        raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "validity_predicates")
    result: list[tuple[str, str, str]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != _PREDICATE_PARTS
            or any(type(part) is not str or not part for part in item)
        ):
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "validity_predicates")
        first, second, third = item
        if type(first) is str and type(second) is str and type(third) is str:
            result.append((first, second, third))
    return tuple(result)
