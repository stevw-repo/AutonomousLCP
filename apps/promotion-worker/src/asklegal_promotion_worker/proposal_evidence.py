"""Application-owned provider-disabled EMBEDDING evidence issuance."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha256
from typing import Never

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_promotion import (
    ProfileError,
    ServingCapabilityProfile,
    validate_serving_capability_profile_authority,
)
from asklegal_reporting import ProposalEvidenceArtifact, provider_disabled_profile_receipt_ref

_UTC_SECOND = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class PromotionProposalEvidenceError(RuntimeError):
    """One closed local embedding-evidence issuance failure."""


def issue_embedding_provider_disabled_evidence(
    serving_profile: ServingCapabilityProfile,
    observation_cutoff: str,
) -> tuple[ProposalEvidenceArtifact, ProposalEvidenceArtifact]:
    """Issue local EMBEDDING evidence only from live promotion profile authority."""
    try:
        validate_serving_capability_profile_authority(serving_profile)
    except (ProfileError, TypeError, ValueError) as error:
        _fail_from("EMBEDDING_PROFILE_AUTHORITY_INVALID", error)
    if not _whole_second_utc(observation_cutoff):
        _fail("EMBEDDING_PROFILE_AUTHORITY_INVALID")
    profile_fingerprint = serving_profile.embedding.profile_fingerprint
    profile_body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1-provider-disabled-profile-receipt/v1",
            "capability": "EMBEDDING",
            "issuer_application": "PROMOTION_WORKER",
            "profile_fingerprint": profile_fingerprint,
            "status": "PROVIDER_DISABLED_PREPARATION_ONLY",
        }
    )
    profile_content, profile_receipt_fingerprint = _seal(profile_body)
    profile_receipt = ProposalEvidenceArtifact(
        provider_disabled_profile_receipt_ref("EMBEDDING", profile_fingerprint),
        profile_receipt_fingerprint,
        profile_content,
    )
    capability_body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1-provider-disabled-capability-evidence/v1",
            "capability": "EMBEDDING",
            "application": "PROMOTION_WORKER",
            "role": "embedding_provider",
            "observation_cutoff": observation_cutoff,
            "profile_receipt_ref": profile_receipt.logical_ref,
            "profile_receipt_fingerprint": profile_receipt.fingerprint,
            "profile_fingerprint": profile_fingerprint,
            "status": "PROVIDER_DISABLED_PREPARATION_ONLY",
        }
    )
    evidence_content, evidence_fingerprint = _seal(capability_body)
    evidence_ref = (
        "proposal-readiness/capability-evidence/embedding/"
        f"{evidence_fingerprint.removeprefix('sha256:')}.json"
    )
    return profile_receipt, ProposalEvidenceArtifact(
        evidence_ref, evidence_fingerprint, evidence_content
    )


def _whole_second_utc(value: object) -> bool:
    if type(value) is not str or _UTC_SECOND.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        return False
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z") == value


def _seal(body: JsonValue) -> tuple[bytes, str]:
    if type(body) is not dict:  # pragma: no cover - checked literals are objects.
        _fail("EMBEDDING_PROFILE_AUTHORITY_INVALID")
    fingerprint = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    return canonicalize({**body, "fingerprint": fingerprint}), fingerprint


def _fail(code: str) -> Never:
    raise PromotionProposalEvidenceError(code)


def _fail_from(code: str, error: Exception) -> Never:
    raise PromotionProposalEvidenceError(code) from error
