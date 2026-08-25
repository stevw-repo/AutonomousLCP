"""Fail-closed Review projections over registered immutable proposal receipts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol

from asklegal_application_runtime import (
    LocalAdapterError,
    LocalAdapterErrorCode,
    ProposalArtifactProjection,
    ProposalDecisionProjection,
    ProposalDetailProjection,
    ProposalProjection,
)
from asklegal_contracts import (
    ContractViolation,
    ProposalMemberBindings,
    ProposalMemberViolation,
    canonicalize,
    fingerprint,
    parse_json_bytes,
    validate_v1_proposal_members,
)
from asklegal_evidence_vault import (
    EvidenceError,
    ExactObjectReference,
    ImmutableVault,
    S3VaultError,
    VaultName,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue
    from asklegal_management_register import ReviewReadyProposalRow

from asklegal_management_register import RegisterProjectionError

_IDENTIFIER = re.compile(r"^(?:pmn|ppk)_[0-9a-f]{48}$")
_ISSUED_ID = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA_VERSION = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,9})?Z$"
)
_PREDICATE_PARTS = 3
_PROMOTION_EFFECT_BINDINGS = {
    "BACKUP_MUTATION": ("MANAGE_BACKUP", "BACKUP_STORE"),
    "EMBEDDING_PROVIDER_CALL": ("CALL_EMBEDDING_PROVIDER", "EMBEDDING_PROVIDER"),
    "PINECONE_MUTATION": ("MUTATE_PINECONE", "SERVING_TARGET"),
    "RELEASE_PUBLICATION": ("PUBLISH_RELEASE", "RELEASE_STORE"),
    "ROUTING_ACTIVATION": ("ACTIVATE_ROUTING", "ROUTING_TARGET"),
}
_PROMOTION_STOP_CONDITIONS = (
    "ATTEMPT_CEILING",
    "AUTHORITY_INVALID",
    "CANCELLATION_BEFORE_EFFECT",
    "CAPABILITY_INACTIVE",
    "DEADLINE",
    "POSTCONDITION_MET",
    "PRECONDITION_CHANGED",
)
_ROLE_PATHS = {
    "CHANGE_INVENTORY": "change-inventory/change-inventory.json",
    "CORPUS_RELEASES": "corpus-releases/releases.json",
    "COST_AND_CAPACITY": "cost-and-capacity/admission.json",
    "COVERAGE_STATUS": "coverage-status/coverage.json",
    "DESIRED_STATE_INVENTORIES": "desired-state-inventories/inventories.json",
    "PROMOTION_MANIFEST": "promotion-manifest/promotion-manifest.json",
    "RECORD_TRACEABILITY": "record-traceability/lookup.json",
    "RECOVERY_READINESS": "recovery-readiness/readiness.json",
    "REVIEW_REPORT": "review-report/report.json",
    "SERVING_STATE_DEFINITION": "serving-state-definition/definition.json",
    "VALIDATION": "validation/results.json",
}


class ProposalProjectionErrorCode(StrEnum):
    """Closed registered-proposal projection failures."""

    CANONICAL = "PROPOSAL_RECEIPT_NOT_CANONICAL"
    FIELDS = "PROPOSAL_RECEIPT_FIELDS_DRIFTED"
    FINGERPRINT = "PROPOSAL_RECEIPT_FINGERPRINT_MISMATCH"
    IDENTITY = "PROPOSAL_RECEIPT_IDENTITY_MISMATCH"
    INVENTORY = "PROPOSAL_RECEIPT_INVENTORY_MISMATCH"
    JSON = "PROPOSAL_RECEIPT_JSON_INVALID"
    PACKAGE = "PROPOSAL_PACKAGE_INVALID"
    READ = "PROPOSAL_PACKAGE_READ_FAILED"
    REFERENCE = "PROPOSAL_RECEIPT_REFERENCE_INVALID"
    SNAPSHOT = "PROPOSAL_PROJECTION_SNAPSHOT_INVALID"
    VALUE = "PROPOSAL_RECEIPT_VALUE_INVALID"
    VERSION = "PROPOSAL_RECEIPT_VERSION_INVALID"


class ProposalProjectionError(RuntimeError):
    """A registered proposal row is not one exact admitted receipt."""

    def __init__(self, code: ProposalProjectionErrorCode) -> None:
        """Create one safe closed projection failure."""
        self.code = code
        super().__init__(code.value)


class ReviewReadyProposalSource(Protocol):
    """Least-privilege read surface supplied by the Management Register adapter."""

    def review_ready_proposals(self) -> tuple[ReviewReadyProposalRow, ...]:
        """Return the immutable registered proposal rows in identity order."""
        ...


@dataclass(frozen=True, slots=True)
class _ProposalRoot:
    """Validated root facts safe to expose through the Review projection."""

    observation_cutoff: str
    valid_from: str
    valid_until: str
    validity_predicates: tuple[tuple[str, str, str], ...]
    base_serving_state_id: str
    base_serving_state_fingerprint: str
    candidate_serving_state_id: str
    candidate_serving_state_fingerprint: str


class RegisteredReviewProjectionStore:
    """Verify register event bytes before exposing one Review projection generation."""

    def __init__(self, source: ReviewReadyProposalSource, primary_vault: ImmutableVault) -> None:
        """Bind the dedicated register projection to exact Primary Vault reads."""
        if primary_vault.vault_name is not VaultName.PRIMARY:
            raise ProposalProjectionError(ProposalProjectionErrorCode.REFERENCE)
        self._source = source
        self._vault = primary_vault

    def load(self) -> tuple[str, tuple[ProposalProjection, ...]]:
        """Read and verify one internally consistent projection generation."""
        details = self._details()
        projections = tuple(item.proposal for item in details)
        identities = tuple(item.proposal_id for item in projections)
        if identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        snapshot = fingerprint(
            [
                {
                    "review_version": item.review_version,
                    "manifest_fingerprint": item.manifest_fingerprint,
                    "proposal_id": item.proposal_id,
                    "status": item.status,
                }
                for item in projections
            ]
        )
        return snapshot, projections

    def page(self, *, offset: int, limit: int) -> tuple[ProposalProjection, ...]:
        """Read one bounded page from a freshly verified generation."""
        _snapshot, proposals = self.load()
        return proposals[offset : offset + limit]

    def get(self, proposal_id: str) -> ProposalProjection | None:
        """Read one proposal only after re-verifying the complete projection."""
        detail = self.detail(proposal_id)
        return None if detail is None else detail.proposal

    def detail(self, proposal_id: str) -> ProposalDetailProjection | None:
        """Return one proposal only after re-reading every exact package byte."""
        details = self._details()
        identities = tuple(item.proposal.proposal_id for item in details)
        if identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        return next((item for item in details if item.proposal.proposal_id == proposal_id), None)

    def approved(self, approval_id: str) -> ProposalDetailProjection | None:
        """Find one approved decision only after re-reading the complete generation."""
        details = self._details()
        proposal_ids = tuple(item.proposal.proposal_id for item in details)
        if proposal_ids != tuple(sorted(proposal_ids)) or len(set(proposal_ids)) != len(
            proposal_ids
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        matches = tuple(
            item
            for item in details
            if item.decision is not None
            and item.decision.decision == "APPROVED"
            and item.decision.approval_id == approval_id
        )
        if len(matches) > 1:
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        return None if not matches else matches[0]

    def check(self) -> bool:
        """Normalize any SQL, shape, canonicalization, or fingerprint failure."""
        try:
            self.load()
        except ProposalProjectionError:
            return False
        except RegisterProjectionError:
            return False
        return True

    def record_evidence_read(self, *, subject: str, evidence_id: str) -> None:
        """Refuse the still-unimplemented durable Review evidence audit effect."""
        del subject, evidence_id
        raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)

    def _details(self) -> tuple[ProposalDetailProjection, ...]:
        return tuple(_detail(row, self._vault) for row in self._source.review_ready_proposals())


def _detail(row: ReviewReadyProposalRow, vault: ImmutableVault) -> ProposalDetailProjection:
    raw = _receipt_document(row)
    package_id = _identifier(raw, "package_id", "ppk")
    if package_id != row.proposal_package_id:
        raise ProposalProjectionError(ProposalProjectionErrorCode.IDENTITY)
    package_fingerprint = _sha256(raw, "package_fingerprint")
    promotion_manifest_id = _identifier(raw, "promotion_manifest_id", "pmn")
    promotion_fingerprint = _sha256(raw, "promotion_manifest_fingerprint")
    manifest_reference = _reference(
        raw.get("manifest_reference"),
        expected_key=f"proposal-packages/{package_id}/proposal-manifest.json",
        expected_fingerprint=package_fingerprint,
    )
    members = _member_references(raw.get("members"), package_id)
    traceability_shards = _traceability_references(raw.get("traceability_shards"), package_id)
    manifest_bytes = _read_exact(vault, manifest_reference)
    member_bytes = tuple(
        (role, path, reference, _read_exact(vault, reference)) for role, path, reference in members
    )
    traceability_shard_bytes = tuple(
        (path, reference, _read_exact(vault, reference)) for path, reference in traceability_shards
    )
    root = _validate_package_manifest(
        manifest_bytes,
        package_id=package_id,
        promotion_identity=(promotion_manifest_id, promotion_fingerprint),
        member_bytes=member_bytes,
        traceability_shard_bytes=traceability_shard_bytes,
    )
    decision = _decision_projection(
        row,
        root,
        promotion_manifest_id=promotion_manifest_id,
        promotion_fingerprint=promotion_fingerprint,
    )
    proposal = ProposalProjection(
        package_id,
        promotion_fingerprint,
        "REVIEW_READY" if decision is None else decision.decision,
        f"Registered proposal {package_id}",
        row.review_version,
    )
    return ProposalDetailProjection(
        proposal,
        package_fingerprint,
        promotion_manifest_id,
        root.observation_cutoff,
        root.valid_from,
        root.valid_until,
        root.validity_predicates,
        root.base_serving_state_id,
        root.base_serving_state_fingerprint,
        root.candidate_serving_state_id,
        root.candidate_serving_state_fingerprint,
        tuple(
            ProposalArtifactProjection(
                role,
                path,
                "application/json",
                reference.fingerprint,
                reference.byte_length,
            )
            for role, path, reference in members
        ),
        decision,
    )


def _decision_projection(
    row: ReviewReadyProposalRow,
    root: _ProposalRoot,
    *,
    promotion_manifest_id: str,
    promotion_fingerprint: str,
) -> ProposalDecisionProjection | None:
    value = _decision_document(row)
    if value is None:
        return None
    if _text(value, "valid_from") != root.valid_from:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    decision = _text(value, "decision")
    expected_event_type = {
        "APPROVED": "PROPOSAL_APPROVED",
        "REJECTED": "PROPOSAL_REJECTED",
    }.get(decision)
    if expected_event_type is None or row.decision_event_type != expected_event_type:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    manifest_ref = _artifact_reference(
        value.get("promotion_manifest_ref"),
        expected_type="PROMOTION_MANIFEST",
        id_prefix="pmn",
    )
    if manifest_ref != (promotion_manifest_id, promotion_fingerprint):
        raise ProposalProjectionError(ProposalProjectionErrorCode.IDENTITY)
    base_ref = _artifact_reference(
        value.get("expected_base_serving_state_ref"),
        expected_type="SERVING_STATE",
        id_prefix="srv",
    )
    if base_ref != (root.base_serving_state_id, root.base_serving_state_fingerprint):
        raise ProposalProjectionError(ProposalProjectionErrorCode.IDENTITY)
    reviewer_id, reviewer_fingerprint = _artifact_reference(
        value.get("reviewer_identity_ref"),
        expected_type="ACTOR",
        id_prefix="act",
    )
    authority_id, authority_fingerprint = _artifact_reference(
        value.get("authority_evidence_ref"),
        expected_type="EVIDENCE",
        id_prefix="evi",
    )
    if _contract_references(value.get("validity_condition_refs")) != root.validity_predicates:
        raise ProposalProjectionError(ProposalProjectionErrorCode.IDENTITY)
    approval_id = _exact_id(value, "approval_id", "apr")
    if approval_id != _stable_id("apr", promotion_manifest_id, promotion_fingerprint, decision):
        raise ProposalProjectionError(ProposalProjectionErrorCode.IDENTITY)
    return ProposalDecisionProjection(
        approval_id,
        decision,
        _text(value, "decision_time"),
        reviewer_id,
        reviewer_fingerprint,
        authority_id,
        authority_fingerprint,
        _text(value, "reason"),
        _decision_event_fingerprint(row),
    )


def _decision_document(row: ReviewReadyProposalRow) -> dict[str, JsonValue] | None:
    if row.decision_bytes is None:
        return None
    if row.decision_fingerprint is None or row.decision_event_type is None:
        raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
    if sha256(row.decision_bytes).digest() != row.decision_fingerprint:
        raise ProposalProjectionError(ProposalProjectionErrorCode.FINGERPRINT)
    try:
        value = parse_json_bytes(row.decision_bytes, max_bytes=1_000_000)
    except ContractViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    expected = {
        "approval_id",
        "authority_evidence_ref",
        "decision",
        "decision_time",
        "expected_base_serving_state_ref",
        "governance_policy_state",
        "immutable",
        "promotion_manifest_ref",
        "reason",
        "reviewer_identity_ref",
        "schema_id",
        "schema_version",
        "valid_from",
        "validity_condition_refs",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or canonicalize(value) != row.decision_bytes
        or value.get("schema_id") != "asklegal.approval-decision"
        or value.get("schema_version") != "1.1.0"
        or value.get("governance_policy_state") != "CONFIGURED"
        or value.get("immutable") is not True
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return value


def _decision_event_fingerprint(row: ReviewReadyProposalRow) -> str:
    if row.decision_fingerprint is None:
        raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
    return f"sha256:{row.decision_fingerprint.hex()}"


def _contract_references(value: JsonValue | None) -> tuple[tuple[str, str, str], ...]:
    if not isinstance(value, list):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    result: list[tuple[str, str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"contract_id", "fingerprint", "version"}:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        contract_id = _text(item, "contract_id")
        version = _text(item, "version")
        condition_fingerprint = _sha256(item, "fingerprint")
        if (
            re.fullmatch(
                r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)",
                version,
            )
            is None
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        result.append((contract_id, version, condition_fingerprint))
    return tuple(result)


def _receipt_document(row: ReviewReadyProposalRow) -> dict[str, JsonValue]:
    if row.authoritative_version != 1:
        raise ProposalProjectionError(ProposalProjectionErrorCode.VERSION)
    if sha256(row.receipt_bytes).digest() != row.receipt_fingerprint:
        raise ProposalProjectionError(ProposalProjectionErrorCode.FINGERPRINT)
    try:
        raw = parse_json_bytes(row.receipt_bytes, max_bytes=1_000_000)
    except ContractViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.JSON) from error
    if not isinstance(raw, dict) or canonicalize(raw) != row.receipt_bytes:
        raise ProposalProjectionError(ProposalProjectionErrorCode.CANONICAL)
    expected = {
        "manifest_reference",
        "members",
        "package_fingerprint",
        "package_id",
        "promotion_manifest_fingerprint",
        "promotion_manifest_id",
        "traceability_shards",
    }
    if set(raw) != expected:
        raise ProposalProjectionError(ProposalProjectionErrorCode.FIELDS)
    return raw


def _member_references(
    members: JsonValue | None,
    package_id: str,
) -> tuple[tuple[str, str, ExactObjectReference], ...]:
    if not isinstance(members, list) or len(members) != len(_ROLE_PATHS):
        raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
    observed_roles: list[str] = []
    result: list[tuple[str, str, ExactObjectReference]] = []
    for value in members:
        if not isinstance(value, dict) or set(value) != {"path", "reference", "role"}:
            raise ProposalProjectionError(ProposalProjectionErrorCode.FIELDS)
        role = _text(value, "role")
        path = _text(value, "path")
        if _ROLE_PATHS.get(role) != path:
            raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
        observed_roles.append(role)
        result.append(
            (
                role,
                path,
                _reference(
                    value.get("reference"),
                    expected_key=f"proposal-packages/{package_id}/members/{path}",
                ),
            )
        )
    if tuple(observed_roles) != tuple(sorted(_ROLE_PATHS)):
        raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
    return tuple(result)


def _traceability_references(
    shards: JsonValue | None,
    package_id: str,
) -> tuple[tuple[str, ExactObjectReference], ...]:
    if not isinstance(shards, list) or not shards:
        raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
    result: list[tuple[str, ExactObjectReference]] = []
    for value in shards:
        if not isinstance(value, dict) or set(value) != {"path", "reference"}:
            raise ProposalProjectionError(ProposalProjectionErrorCode.FIELDS)
        path = _text(value, "path")
        if re.fullmatch(r"entries/rts_[0-9a-f]{48}\.ndjson", path) is None:
            raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
        result.append(
            (
                path,
                _reference(
                    value.get("reference"),
                    expected_key=f"proposal-packages/{package_id}/traceability/{path}",
                    allow_empty=True,
                ),
            )
        )
    if tuple(path for path, _reference_value in result) != tuple(
        sorted({path for path, _reference_value in result})
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
    return tuple(result)


def _reference(
    value: JsonValue | None,
    *,
    expected_key: str,
    expected_fingerprint: str | None = None,
    allow_empty: bool = False,
) -> ExactObjectReference:
    expected = {"byte_length", "fingerprint", "logical_key", "vault", "version_id"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ProposalProjectionError(ProposalProjectionErrorCode.REFERENCE)
    byte_length = value.get("byte_length")
    minimum_length = 0 if allow_empty else 1
    if type(byte_length) is not int or byte_length < minimum_length:
        raise ProposalProjectionError(ProposalProjectionErrorCode.REFERENCE)
    if _text(value, "vault") != "PRIMARY" or _text(value, "logical_key") != expected_key:
        raise ProposalProjectionError(ProposalProjectionErrorCode.REFERENCE)
    version_id = _text(value, "version_id")
    observed_fingerprint = _sha256(value, "fingerprint")
    if expected_fingerprint is not None and observed_fingerprint != expected_fingerprint:
        raise ProposalProjectionError(ProposalProjectionErrorCode.REFERENCE)
    try:
        return ExactObjectReference(
            VaultName.PRIMARY,
            expected_key,
            version_id,
            observed_fingerprint,
            byte_length,
        )
    except (TypeError, ValueError) as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.REFERENCE) from error


def _read_exact(vault: ImmutableVault, reference: ExactObjectReference) -> bytes:
    try:
        content = vault.read_exact(reference)
    except (EvidenceError, S3VaultError, OSError, TypeError, ValueError) as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.READ) from error
    if (
        type(content) is not bytes
        or len(content) != reference.byte_length
        or f"sha256:{sha256(content).hexdigest()}" != reference.fingerprint
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.FINGERPRINT)
    return content


def _validate_package_manifest(
    content: bytes,
    *,
    package_id: str,
    promotion_identity: tuple[str, str],
    member_bytes: tuple[tuple[str, str, ExactObjectReference, bytes], ...],
    traceability_shard_bytes: tuple[tuple[str, ExactObjectReference, bytes], ...],
) -> _ProposalRoot:
    promotion_manifest_id, promotion_fingerprint = promotion_identity
    try:
        value = parse_json_bytes(content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
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
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    if (
        value.get("immutable") is not True
        or value.get("schema_id") != "asklegal.proposal-package-manifest"
        or value.get("schema_version") != "1.0.0"
        or value.get("status") != "REVIEW_READY"
        or _text(value, "proposal_package_id") != package_id
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    observation_cutoff = _text(value, "observation_cutoff")
    if _text(value, "created_at") != observation_cutoff:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    promotion_ref = _artifact_reference(
        value.get("promotion_manifest_ref"),
        expected_type="PROMOTION_MANIFEST",
        id_prefix="pmn",
    )
    if promotion_ref != (promotion_manifest_id, promotion_fingerprint):
        raise ProposalProjectionError(ProposalProjectionErrorCode.IDENTITY)
    base_id, base_fingerprint = _artifact_reference(
        value.get("base_serving_state_ref"),
        expected_type="SERVING_STATE",
        id_prefix="srv",
    )
    candidate_id, candidate_fingerprint = _artifact_reference(
        value.get("candidate_serving_state_ref"),
        expected_type="SERVING_STATE",
        id_prefix="srv",
    )
    _validate_package_inventory(value.get("artifact_inventory"), member_bytes)
    promotion_content = next(
        (
            content
            for role, _path, _reference, content in member_bytes
            if role == "PROMOTION_MANIFEST"
        ),
        None,
    )
    if promotion_content is None:
        raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
    promotion = promotion_facts_from_bytes(
        promotion_content,
        manifest_id=promotion_manifest_id,
        manifest_fingerprint=promotion_fingerprint,
    )
    if (
        promotion.base_serving_state_id != base_id
        or promotion.candidate_serving_state_id != candidate_id
        or promotion.candidate_serving_state_fingerprint != candidate_fingerprint
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.IDENTITY)
    _validate_proposal_member_semantics(
        member_bytes,
        ProposalMemberBindings(
            observation_cutoff,
            promotion_manifest_id,
            promotion_fingerprint,
            base_id,
            candidate_id,
            candidate_fingerprint,
        ),
        {path: content for path, _reference_value, content in traceability_shard_bytes},
    )
    report = next(
        (reference for role, _path, reference, _content in member_bytes if role == "REVIEW_REPORT"),
        None,
    )
    if report is None:
        raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
    report_ref = _artifact_reference(
        value.get("review_report_ref"),
        expected_type="ARTIFACT",
        id_prefix="art",
    )
    if report_ref[1] != report.fingerprint:
        raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
    return _ProposalRoot(
        observation_cutoff,
        promotion.valid_from,
        promotion.valid_until,
        promotion.validity_predicates,
        base_id,
        base_fingerprint,
        candidate_id,
        candidate_fingerprint,
    )


def _validate_proposal_member_semantics(
    members: tuple[tuple[str, str, ExactObjectReference, bytes], ...],
    bindings: ProposalMemberBindings,
    traceability_shards_by_path: Mapping[str, bytes],
) -> None:
    try:
        validate_v1_proposal_members(
            {role: content for role, _path, _reference, content in members},
            bindings,
            traceability_shards_by_path,
        )
    except ProposalMemberViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error


@dataclass(frozen=True, slots=True)
class _PromotionFacts:
    """Approval-relevant facts recovered from canonical executable manifest bytes."""

    base_serving_state_id: str
    candidate_serving_state_id: str
    candidate_serving_state_fingerprint: str
    valid_from: str
    valid_until: str
    validity_predicates: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class _PromotionActionBindings:
    candidate_serving_state_fingerprint: str
    desired_state_fingerprint: str
    embedding_profile_fingerprint: str
    valid_from: str
    valid_until: str


def promotion_facts_from_bytes(
    content: bytes,
    *,
    manifest_id: str,
    manifest_fingerprint: str,
) -> _PromotionFacts:
    """Independently recover Approval facts from one exact executable manifest."""
    try:
        value = parse_json_bytes(content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    expected = {
        "action_contract_version",
        "actions",
        "base_serving_state_id",
        "batch_size",
        "candidate_serving_state_fingerprint",
        "candidate_serving_state_id",
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
    actual_fingerprint = f"sha256:{sha256(content).hexdigest()}"
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or canonicalize(value) != content
        or actual_fingerprint != manifest_fingerprint
        or _stable_id("pmn", actual_fingerprint) != manifest_id
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    retirements = _string_sequence(value, "exact_retirement_target_ids")
    predicates = _predicate_sequence(value)
    valid_from = _text(value, "valid_from")
    valid_until = _text(value, "valid_until")
    fingerprints = tuple(
        _sha256(value, field)
        for field in (
            "candidate_serving_state_fingerprint",
            "coverage_fingerprint",
            "desired_state_fingerprint",
            "embedding_profile_fingerprint",
        )
    )
    batch_size = value.get("batch_size")
    if (
        len(retirements) != len(set(retirements))
        or not predicates
        or len(predicates) != len(set(predicates))
        or valid_from >= valid_until
        or type(batch_size) is not int
        or batch_size < 1
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    if _text(value, "action_contract_version") != "1.0.0":
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    _promotion_actions(
        value,
        _PromotionActionBindings(
            fingerprints[0],
            fingerprints[2],
            fingerprints[3],
            valid_from,
            valid_until,
        ),
    )
    for field in ("environment", "freeze_date", "jurisdiction", "project_id"):
        _text(value, field)
    base_id = _exact_id(value, "base_serving_state_id", "srv")
    candidate_id = _exact_id(value, "candidate_serving_state_id", "srv")
    _exact_id(value, "rollback_serving_state_id", "srv")
    return _PromotionFacts(
        base_id,
        candidate_id,
        fingerprints[0],
        valid_from,
        valid_until,
        predicates,
    )


def _promotion_actions(
    value: Mapping[str, JsonValue],
    bindings: _PromotionActionBindings,
) -> None:
    raw_actions = value.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    expected_fields = {
        "action_id",
        "attempt_ceiling",
        "capability_profile_ref",
        "compensation",
        "deadline",
        "destination_class",
        "effect_command_fingerprint",
        "effect_type",
        "expected_remote_precondition_ref",
        "input_refs",
        "owning_application",
        "permitted_checkpoint",
        "required_capability",
        "retry_class",
        "sequence",
        "stable_idempotency_key",
        "stop_conditions",
        "success_postcondition_ref",
    }
    action_ids: list[str] = []
    idempotency_keys: list[str] = []
    for expected_sequence, action in enumerate(raw_actions, start=1):
        if not isinstance(action, dict) or set(action) != expected_fields:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        if action.get("sequence") != expected_sequence:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        action_id = _text(action, "action_id")
        checkpoint = _text(action, "permitted_checkpoint")
        effect_type = _text(action, "effect_type")
        binding = _PROMOTION_EFFECT_BINDINGS.get(effect_type)
        if (
            _CODE.fullmatch(action_id) is None
            or _CODE.fullmatch(checkpoint) is None
            or binding is None
            or _text(action, "owning_application") != "PROMOTION_WORKER"
            or _text(action, "required_capability") != binding[0]
            or _text(action, "destination_class") != binding[1]
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        inputs = _promotion_references(action.get("input_refs"))
        capability = _promotion_reference(action.get("capability_profile_ref"))
        if (
            not inputs
            or capability[0] != "CAPABILITY_PROFILE"
            or not capability[1].startswith("cap_")
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        required_inputs = {
            "BACKUP_MUTATION": {("SERVING_STATE", bindings.candidate_serving_state_fingerprint)},
            "EMBEDDING_PROVIDER_CALL": {
                ("DESIRED_STATE_INVENTORY", bindings.desired_state_fingerprint),
                ("EMBEDDING_PROFILE", bindings.embedding_profile_fingerprint),
            },
            "PINECONE_MUTATION": {
                ("DESIRED_STATE_INVENTORY", bindings.desired_state_fingerprint),
                ("SERVING_STATE", bindings.candidate_serving_state_fingerprint),
            },
            "RELEASE_PUBLICATION": {
                ("DESIRED_STATE_INVENTORY", bindings.desired_state_fingerprint)
            },
            "ROUTING_ACTIVATION": {("SERVING_STATE", bindings.candidate_serving_state_fingerprint)},
        }[effect_type]
        if not required_inputs.issubset({(item[0], item[2]) for item in inputs}):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        _sha256(action, "effect_command_fingerprint")
        retry_class = _text(action, "retry_class")
        attempt_ceiling = action.get("attempt_ceiling")
        deadline = _text(action, "deadline")
        if (
            retry_class not in {"NEVER", "RECONCILE_BEFORE_RETRY", "SAFE_SAME_INTENT"}
            or type(attempt_ceiling) is not int
            or attempt_ceiling < 1
            or (retry_class == "NEVER" and attempt_ceiling != 1)
            or _UTC_TIMESTAMP.fullmatch(deadline) is None
            or not bindings.valid_from < deadline <= bindings.valid_until
            or action.get("stop_conditions") != list(_PROMOTION_STOP_CONDITIONS)
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        _promotion_contract_reference(action.get("expected_remote_precondition_ref"))
        _promotion_contract_reference(action.get("success_postcondition_ref"))
        _promotion_compensation(action.get("compensation"))
        action_ids.append(action_id)
        idempotency_keys.append(_text(action, "stable_idempotency_key"))
    if len(set(action_ids)) != len(action_ids) or len(set(idempotency_keys)) != len(
        idempotency_keys
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)


def _promotion_references(value: JsonValue | None) -> tuple[tuple[str, str, str], ...]:
    if not isinstance(value, list):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    result = tuple(_promotion_reference(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return result


def _promotion_reference(value: JsonValue | None) -> tuple[str, str, str]:
    if not isinstance(value, dict) or set(value) != {"fingerprint", "ref_id", "ref_type"}:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    ref_type = _text(value, "ref_type")
    ref_id = _text(value, "ref_id")
    if _CODE.fullmatch(ref_type) is None or _ISSUED_ID.fullmatch(ref_id) is None:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return ref_type, ref_id, _sha256(value, "fingerprint")


def _promotion_contract_reference(value: JsonValue | None) -> None:
    if not isinstance(value, dict) or set(value) != {"contract_id", "fingerprint", "version"}:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    _text(value, "contract_id")
    if _SCHEMA_VERSION.fullmatch(_text(value, "version")) is None:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    _sha256(value, "fingerprint")


def _promotion_compensation(value: JsonValue | None) -> None:
    if not isinstance(value, dict):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    mode = _text(value, "mode")
    if mode == "NO_COMPENSATION" and set(value) == {"mode"}:
        return
    if mode == "DECLARED_COMPENSATION" and set(value) == {"contract_ref", "mode"}:
        _promotion_contract_reference(value.get("contract_ref"))
        return
    raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)


def _string_sequence(document: Mapping[str, JsonValue], field: str) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list) or any(type(item) is not str or not item for item in value):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return tuple(item for item in value if type(item) is str)


def _predicate_sequence(
    document: Mapping[str, JsonValue],
) -> tuple[tuple[str, str, str], ...]:
    value = document.get("validity_predicates")
    if not isinstance(value, list):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    result: list[tuple[str, str, str]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != _PREDICATE_PARTS:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        predicate_id, predicate_version, predicate_fingerprint = item
        if (
            type(predicate_id) is not str
            or not predicate_id
            or type(predicate_version) is not str
            or re.fullmatch(
                r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", predicate_version
            )
            is None
            or type(predicate_fingerprint) is not str
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        if _FINGERPRINT.fullmatch(predicate_fingerprint) is None:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        result.append((predicate_id, predicate_version, predicate_fingerprint))
    return tuple(result)


def _exact_id(document: Mapping[str, JsonValue], field: str, prefix: str) -> str:
    value = _text(document, field)
    if re.fullmatch(rf"{prefix}_[0-9a-f]{{48}}", value) is None:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return value


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def _validate_package_inventory(
    value: JsonValue | None,
    members: tuple[tuple[str, str, ExactObjectReference, bytes], ...],
) -> None:
    if not isinstance(value, list) or len(value) != len(_ROLE_PATHS):
        raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
    observed_roles: list[str] = []
    for raw, member in zip(value, members, strict=True):
        role, path, reference, content = member
        if not isinstance(raw, dict) or set(raw) != {
            "byte_size",
            "fingerprint",
            "media_type",
            "path",
            "role",
        }:
            raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
        byte_size = raw.get("byte_size")
        if (
            _text(raw, "role") != role
            or _text(raw, "path") != path
            or _text(raw, "media_type") != "application/json"
            or type(byte_size) is not int
            or byte_size != len(content)
            or byte_size != reference.byte_length
            or _sha256(raw, "fingerprint") != reference.fingerprint
            or reference.fingerprint != f"sha256:{sha256(content).hexdigest()}"
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)
        observed_roles.append(role)
    if tuple(observed_roles) != tuple(sorted(_ROLE_PATHS)):
        raise ProposalProjectionError(ProposalProjectionErrorCode.INVENTORY)


def _artifact_reference(
    value: JsonValue | None,
    *,
    expected_type: str,
    id_prefix: str,
) -> tuple[str, str]:
    if not isinstance(value, dict) or set(value) != {"fingerprint", "ref_id", "ref_type"}:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    if _text(value, "ref_type") != expected_type:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    ref_id = _text(value, "ref_id")
    if re.fullmatch(rf"{id_prefix}_[0-9a-f]{{48}}", ref_id) is None:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return ref_id, _sha256(value, "fingerprint")


def _text(document: Mapping[str, JsonValue], field: str) -> str:
    value = document.get(field)
    if type(value) is not str or not value or value.strip() != value:
        raise ProposalProjectionError(ProposalProjectionErrorCode.VALUE)
    return value


def _identifier(document: Mapping[str, JsonValue], field: str, prefix: str) -> str:
    value = _text(document, field)
    if _IDENTIFIER.fullmatch(value) is None or not value.startswith(f"{prefix}_"):
        raise ProposalProjectionError(ProposalProjectionErrorCode.VALUE)
    return value


def _sha256(document: Mapping[str, JsonValue], field: str) -> str:
    value = _text(document, field)
    if _FINGERPRINT.fullmatch(value) is None:
        raise ProposalProjectionError(ProposalProjectionErrorCode.VALUE)
    return value
