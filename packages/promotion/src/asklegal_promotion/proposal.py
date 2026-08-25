"""Exact-version proposal-package reads shared by Control, Review, and Promotion."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import TYPE_CHECKING

from asklegal_contracts import (
    ContractViolation,
    ProposalMemberBindings,
    ProposalMemberViolation,
    canonicalize,
    parse_json_bytes,
    validate_v1_proposal_members,
)
from asklegal_corpus import (
    PROPOSAL_ROLE_PATHS,
    CorpusError,
    CorpusErrorCode,
    ProposalArtifact,
    ProposalPackage,
)
from asklegal_evidence_vault import ImmutableVault, VaultName

from .builder import verify_stored_proposal_package
from .model import PromotionError, StoredProposalPackage

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def read_stored_proposal_package(
    primary_vault: ImmutableVault,
    receipt: StoredProposalPackage,
) -> ProposalPackage:
    """Rebuild a complete package only from its portable exact-version receipt."""
    if primary_vault.vault_name is not VaultName.PRIMARY:
        raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "proposal vault")
    try:
        verify_stored_proposal_package(receipt)
    except PromotionError as error:
        raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "proposal receipt") from error
    manifest_bytes = primary_vault.read_exact(receipt.manifest_reference)
    if _fingerprint(manifest_bytes) != receipt.package_fingerprint:
        raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "proposal manifest")
    document = _manifest_document(manifest_bytes)
    package_id = _text(document, "proposal_package_id")
    observation_cutoff = _text(document, "observation_cutoff")
    promotion_ref = _object(document, "promotion_manifest_ref")
    base_ref = _object(document, "base_serving_state_ref")
    candidate_ref = _object(document, "candidate_serving_state_ref")
    if (
        package_id != receipt.package_id
        or _text(promotion_ref, "ref_id") != receipt.promotion_manifest_id
        or _text(promotion_ref, "fingerprint") != receipt.promotion_manifest_fingerprint
        or receipt.manifest_reference.logical_key != _manifest_key(package_id)
        or receipt.manifest_reference.fingerprint != receipt.package_fingerprint
    ):
        raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "proposal root binding")
    inventory = _inventory(document)
    if tuple(member.role for member in receipt.members) != tuple(sorted(PROPOSAL_ROLE_PATHS)):
        raise CorpusError(CorpusErrorCode.INVENTORY_MISMATCH, "proposal receipt members")
    artifacts: list[ProposalArtifact] = []
    for member in receipt.members:
        entry = inventory.get(member.path)
        if entry is None:
            raise CorpusError(CorpusErrorCode.INVENTORY_MISMATCH, member.path)
        content = primary_vault.read_exact(member.reference)
        media_type = _text(entry, "media_type")
        expected_fingerprint = _text(entry, "fingerprint")
        if (
            _text(entry, "role") != member.role
            or _integer(entry, "byte_size") != len(content)
            or expected_fingerprint != _fingerprint(content)
            or member.reference.logical_key != _member_key(package_id, member.path)
            or member.reference.fingerprint != expected_fingerprint
            or member.reference.byte_length != len(content)
        ):
            raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, member.path)
        artifacts.append(
            ProposalArtifact(
                member.role,
                member.path,
                media_type,
                content,
                expected_fingerprint,
            )
        )
    if set(inventory) != {member.path for member in receipt.members}:
        raise CorpusError(CorpusErrorCode.INVENTORY_MISMATCH, "proposal inventory")
    traceability_shards = {
        shard.path: primary_vault.read_exact(shard.reference)
        for shard in receipt.traceability_shards
    }
    _validate_proposal_member_semantics(
        artifacts,
        ProposalMemberBindings(
            observation_cutoff,
            receipt.promotion_manifest_id,
            receipt.promotion_manifest_fingerprint,
            _text(base_ref, "ref_id"),
            _text(candidate_ref, "ref_id"),
            _text(candidate_ref, "fingerprint"),
        ),
        traceability_shards,
    )
    return ProposalPackage(
        package_id,
        observation_cutoff,
        receipt.promotion_manifest_id,
        receipt.promotion_manifest_fingerprint,
        _text(base_ref, "ref_id"),
        _text(candidate_ref, "ref_id"),
        tuple(artifacts),
        manifest_bytes,
        receipt.package_fingerprint,
    )


def _validate_proposal_member_semantics(
    artifacts: list[ProposalArtifact],
    bindings: ProposalMemberBindings,
    traceability_shards_by_path: Mapping[str, bytes],
) -> None:
    try:
        validate_v1_proposal_members(
            {artifact.role: artifact.content for artifact in artifacts},
            bindings,
            traceability_shards_by_path,
        )
    except ProposalMemberViolation as error:
        raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "proposal semantics") from error


def _manifest_document(content: bytes) -> dict[str, JsonValue]:
    try:
        value = parse_json_bytes(content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "proposal root") from error
    expected = {
        "artifact_inventory",
        "base_serving_state_ref",
        "candidate_serving_state_ref",
        "created_at",
        "immutable",
        "observation_cutoff",
        "promotion_manifest_ref",
        "proposal_package_id",
        "review_report_ref",
        "schema_id",
        "schema_version",
        "status",
    }
    if not isinstance(value, dict) or set(value) != expected or canonicalize(value) != content:
        raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "proposal root")
    if (
        value.get("immutable") is not True
        or value.get("schema_id") != "asklegal.proposal-package-manifest"
        or value.get("schema_version") != "1.0.0"
        or value.get("status") != "REVIEW_READY"
    ):
        raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "proposal root")
    return value


def _member_key(package_id: str, member_path: str) -> str:
    return f"proposal-packages/{package_id}/members/{member_path}"


def _manifest_key(package_id: str) -> str:
    return f"proposal-packages/{package_id}/proposal-manifest.json"


def _text(document: Mapping[str, JsonValue], field: str) -> str:
    value = document.get(field)
    if type(value) is not str or not value:
        raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, field)
    return value


def _integer(document: Mapping[str, JsonValue], field: str) -> int:
    value = document.get(field)
    if type(value) is not int:
        raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, field)
    return value


def _object(document: Mapping[str, JsonValue], field: str) -> dict[str, JsonValue]:
    value = document.get(field)
    if not isinstance(value, dict):
        raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, field)
    return value


def _inventory(document: Mapping[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    value = document.get("artifact_inventory")
    if not isinstance(value, list):
        raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "artifact_inventory")
    result: dict[str, dict[str, JsonValue]] = {}
    for raw_entry in value:
        if not isinstance(raw_entry, dict):
            raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "artifact_inventory")
        path = _text(raw_entry, "path")
        if path in result:
            raise CorpusError(CorpusErrorCode.INVENTORY_MISMATCH, path)
        result[path] = raw_entry
    return result
