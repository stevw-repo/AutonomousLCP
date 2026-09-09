"""Fail-closed Review projections over registered immutable proposal receipts."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from asklegal_application_runtime import (
    HKV1ReviewReadinessProjection,
    HKV1ScopeDispositionProjection,
    LocalAdapterError,
    LocalAdapterErrorCode,
    ProposalArtifactProjection,
    ProposalDecisionProjection,
    ProposalDetailProjection,
    ProposalProjection,
    exclusive_local_state_lock,
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
from asklegal_contracts.json_types import checked_json_value
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
_EVIDENCE_AUDIT_SCHEMA = "asklegal.local-review-evidence-read-ledger/v1"
_EVIDENCE_AUDIT_ENTRY_SCHEMA = "asklegal.local-review-evidence-read/v1"
_ZERO_FINGERPRINT = "sha256:" + "0" * 64
_MAX_EVIDENCE_AUDIT_BYTES = 5_000_000
_PREDICATE_PARTS = 3
_HK_V1_FAMILY_COUNT = 2
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
_HK_V1_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_HK_V1_SCOPE_FAMILIES = {
    "HK-CASE-BINDING-POST-1997": "CASES",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS": "LEGISLATION",
    "HK-LEG-ORDINANCES": "LEGISLATION",
    "HK-LEG-SUBSIDIARY": "LEGISLATION",
}


def freeze_hk_v1_review_readiness(  # noqa: PLR0913, PLR0917 - exact review contract.
    scope_dispositions: tuple[HKV1ScopeDispositionProjection, ...],
    limitations: tuple[str, ...],
    model_evaluation_ref: str,
    retrieval_evaluation_ref: str,
    model_profile_fingerprint: str,
    embedding_profile_fingerprint: str,
    serving_profile_fingerprint: str,
    target_namespace: str,
    backup_profile_fingerprint: str,
    target_members: tuple[tuple[str, str, str], ...],
    zero_record_scope_ids: tuple[str, ...],
    target_name: str,
    native_backup_ref: str,
    recovery_backup_ref: str,
    rollback_state_id: str,
    proposal_fingerprint: str,
) -> HKV1ReviewReadinessProjection:
    """Freeze every fact the local named human must see before Approval."""
    retryable_count = sum(item.retryable_count for item in scope_dispositions)
    body = {
        "scope_dispositions": [
            {
                "scope_id": item.scope_id,
                "result": item.result,
                "retryable_count": item.retryable_count,
            }
            for item in scope_dispositions
        ],
        "limitations": list(limitations),
        "retryable_count": retryable_count,
        "model_evaluation_ref": model_evaluation_ref,
        "retrieval_evaluation_ref": retrieval_evaluation_ref,
        "model_profile_fingerprint": model_profile_fingerprint,
        "embedding_profile_fingerprint": embedding_profile_fingerprint,
        "serving_profile_fingerprint": serving_profile_fingerprint,
        "target_namespace": target_namespace,
        "backup_profile_fingerprint": backup_profile_fingerprint,
        "target_members": [
            {"record_id": record_id, "scope_id": scope_id, "material_family": family}
            for record_id, scope_id, family in target_members
        ],
        "zero_record_scope_ids": list(zero_record_scope_ids),
        "target_name": target_name,
        "native_backup_ref": native_backup_ref,
        "recovery_backup_ref": recovery_backup_ref,
        "rollback_state_id": rollback_state_id,
        "proposal_fingerprint": proposal_fingerprint,
    }
    projection = HKV1ReviewReadinessProjection(
        scope_dispositions,
        limitations,
        retryable_count,
        model_evaluation_ref,
        retrieval_evaluation_ref,
        model_profile_fingerprint,
        embedding_profile_fingerprint,
        serving_profile_fingerprint,
        target_namespace,
        backup_profile_fingerprint,
        target_members,
        zero_record_scope_ids,
        target_name,
        native_backup_ref,
        recovery_backup_ref,
        rollback_state_id,
        proposal_fingerprint,
        f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}",
    )
    validate_hk_v1_review_readiness(projection, proposal_fingerprint)
    return projection


def validate_hk_v1_review_readiness(
    value: HKV1ReviewReadinessProjection,
    proposal_fingerprint: str,
) -> None:
    """Reject incomplete, retryable, forged, or proposal-drifted Review facts."""
    if type(value) is not HKV1ReviewReadinessProjection:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    try:
        body = {
            "scope_dispositions": [
                {
                    "scope_id": item.scope_id,
                    "result": item.result,
                    "retryable_count": item.retryable_count,
                }
                for item in value.scope_dispositions
                if type(item) is HKV1ScopeDispositionProjection
            ],
            "limitations": list(value.limitations),
            "retryable_count": value.retryable_count,
            "model_evaluation_ref": value.model_evaluation_ref,
            "retrieval_evaluation_ref": value.retrieval_evaluation_ref,
            "model_profile_fingerprint": value.model_profile_fingerprint,
            "embedding_profile_fingerprint": value.embedding_profile_fingerprint,
            "serving_profile_fingerprint": value.serving_profile_fingerprint,
            "target_namespace": value.target_namespace,
            "backup_profile_fingerprint": value.backup_profile_fingerprint,
            "target_members": [
                {"record_id": record_id, "scope_id": scope_id, "material_family": family}
                for record_id, scope_id, family in value.target_members
            ],
            "zero_record_scope_ids": list(value.zero_record_scope_ids),
            "target_name": value.target_name,
            "native_backup_ref": value.native_backup_ref,
            "recovery_backup_ref": value.recovery_backup_ref,
            "rollback_state_id": value.rollback_state_id,
            "proposal_fingerprint": value.proposal_fingerprint,
        }
        expected = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
    except (AttributeError, TypeError, ValueError) as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    texts = (
        *value.limitations,
        value.model_evaluation_ref,
        value.retrieval_evaluation_ref,
        value.target_name,
        value.native_backup_ref,
        value.recovery_backup_ref,
        value.rollback_state_id,
    )
    results = {item.scope_id: item.result for item in value.scope_dispositions}
    zero_scopes = set(value.zero_record_scope_ids)
    member_ids = tuple(record_id for record_id, _scope_id, _family in value.target_members)
    member_scopes = tuple(scope_id for _record_id, scope_id, _family in value.target_members)
    if (
        len(value.scope_dispositions) != len(_HK_V1_SCOPES)
        or tuple(item.scope_id for item in value.scope_dispositions) != _HK_V1_SCOPES
        or any(item.result not in {"COMPLETE", "NO_CHANGE"} for item in value.scope_dispositions)
        or any(
            type(item.retryable_count) is not int or item.retryable_count != 0
            for item in value.scope_dispositions
        )
        or type(value.retryable_count) is not int
        or value.retryable_count != 0
        or not value.limitations
        or any(type(item) is not str or not item or item.strip() != item for item in texts)
        or _FINGERPRINT.fullmatch(value.model_profile_fingerprint) is None
        or _FINGERPRINT.fullmatch(value.embedding_profile_fingerprint) is None
        or _FINGERPRINT.fullmatch(value.serving_profile_fingerprint) is None
        or _FINGERPRINT.fullmatch(value.backup_profile_fingerprint) is None
        or not value.target_namespace
        or not value.target_members
        or tuple(sorted(member_ids)) != member_ids
        or len(set(member_ids)) != len(member_ids)
        or any(re.fullmatch(r"rec_[0-9a-f]{48}", record_id) is None for record_id in member_ids)
        or any(
            _HK_V1_SCOPE_FAMILIES.get(scope_id) != family
            for _record_id, scope_id, family in value.target_members
        )
        or tuple(sorted(value.zero_record_scope_ids)) != value.zero_record_scope_ids
        or set(value.zero_record_scope_ids)
        & {scope_id for _record_id, scope_id, _family in value.target_members}
        or set(member_scopes) | set(value.zero_record_scope_ids) != set(_HK_V1_SCOPES)
        or any(
            results.get(scope_id) != ("NO_CHANGE" if scope_id in zero_scopes else "COMPLETE")
            for scope_id in _HK_V1_SCOPES
        )
        or value.proposal_fingerprint != proposal_fingerprint
        or _FINGERPRINT.fullmatch(proposal_fingerprint) is None
        or value.fingerprint != expected
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)


def hk_v1_review_readiness_bytes(value: HKV1ReviewReadinessProjection) -> bytes:
    """Serialize one already verified Task 8 readiness artifact canonically."""
    validate_hk_v1_review_readiness(value, value.proposal_fingerprint)
    return canonicalize(
        checked_json_value(
            {
                "embedding_profile_fingerprint": value.embedding_profile_fingerprint,
                "serving_profile_fingerprint": value.serving_profile_fingerprint,
                "target_namespace": value.target_namespace,
                "backup_profile_fingerprint": value.backup_profile_fingerprint,
                "target_members": [
                    {"record_id": record_id, "scope_id": scope_id, "material_family": family}
                    for record_id, scope_id, family in value.target_members
                ],
                "zero_record_scope_ids": list(value.zero_record_scope_ids),
                "fingerprint": value.fingerprint,
                "limitations": list(value.limitations),
                "model_evaluation_ref": value.model_evaluation_ref,
                "model_profile_fingerprint": value.model_profile_fingerprint,
                "native_backup_ref": value.native_backup_ref,
                "proposal_fingerprint": value.proposal_fingerprint,
                "recovery_backup_ref": value.recovery_backup_ref,
                "retrieval_evaluation_ref": value.retrieval_evaluation_ref,
                "retryable_count": value.retryable_count,
                "rollback_state_id": value.rollback_state_id,
                "schema_id": "asklegal.hk-v1-review-readiness/v1",
                "scope_dispositions": [
                    {
                        "result": item.result,
                        "retryable_count": item.retryable_count,
                        "scope_id": item.scope_id,
                    }
                    for item in value.scope_dispositions
                ],
                "target_name": value.target_name,
            }
        )
    )


def _parse_hk_v1_review_readiness(
    content: bytes,
    proposal_fingerprint: str,
) -> HKV1ReviewReadinessProjection:
    try:
        value = parse_json_bytes(content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    expected = {
        "backup_profile_fingerprint",
        "embedding_profile_fingerprint",
        "fingerprint",
        "limitations",
        "model_evaluation_ref",
        "model_profile_fingerprint",
        "native_backup_ref",
        "proposal_fingerprint",
        "recovery_backup_ref",
        "retrieval_evaluation_ref",
        "retryable_count",
        "rollback_state_id",
        "schema_id",
        "scope_dispositions",
        "serving_profile_fingerprint",
        "target_members",
        "target_name",
        "target_namespace",
        "zero_record_scope_ids",
    }
    if not isinstance(value, dict) or set(value) != expected or canonicalize(value) != content:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    scopes = value.get("scope_dispositions")
    limitations = value.get("limitations")
    members = value.get("target_members")
    zero_scopes = value.get("zero_record_scope_ids")
    if (
        not isinstance(scopes, list)
        or not isinstance(limitations, list)
        or not isinstance(members, list)
        or not isinstance(zero_scopes, list)
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    try:
        dispositions = tuple(
            HKV1ScopeDispositionProjection(
                _text(item, "scope_id"),
                _text(item, "result"),
                _integer(item, "retryable_count"),
            )
            for item in scopes
            if isinstance(item, dict) and set(item) == {"result", "retryable_count", "scope_id"}
        )
        projection = freeze_hk_v1_review_readiness(
            dispositions,
            tuple(item for item in limitations if type(item) is str),
            _text(value, "model_evaluation_ref"),
            _text(value, "retrieval_evaluation_ref"),
            _sha256(value, "model_profile_fingerprint"),
            _sha256(value, "embedding_profile_fingerprint"),
            _sha256(value, "serving_profile_fingerprint"),
            _text(value, "target_namespace"),
            _sha256(value, "backup_profile_fingerprint"),
            tuple(
                (
                    _text(item, "record_id"),
                    _text(item, "scope_id"),
                    _text(item, "material_family"),
                )
                for item in members
                if isinstance(item, dict)
                and set(item) == {"material_family", "record_id", "scope_id"}
            ),
            tuple(item for item in zero_scopes if type(item) is str),
            _text(value, "target_name"),
            _text(value, "native_backup_ref"),
            _text(value, "recovery_backup_ref"),
            _text(value, "rollback_state_id"),
            proposal_fingerprint,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    if (
        value.get("schema_id") != "asklegal.hk-v1-review-readiness/v1"
        or value.get("proposal_fingerprint") != proposal_fingerprint
        or value.get("retryable_count") != projection.retryable_count
        or value.get("fingerprint") != projection.fingerprint
        or hk_v1_review_readiness_bytes(projection) != content
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return projection


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


class RegisteredHKV1ReadinessSource(Protocol):
    """Register projection mapping one proposal to its retained Task 8 artifact."""

    def readiness_reference(
        self,
        proposal_package_id: str,
        proposal_fingerprint: str,
    ) -> ExactObjectReference | None:
        """Return the exact Primary-vault reference registered for this proposal."""
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

    def __init__(
        self,
        source: ReviewReadyProposalSource,
        primary_vault: ImmutableVault,
        readiness_source: RegisteredHKV1ReadinessSource | None = None,
    ) -> None:
        """Bind the dedicated register projection to exact Primary Vault reads."""
        if primary_vault.vault_name is not VaultName.PRIMARY:
            raise ProposalProjectionError(ProposalProjectionErrorCode.REFERENCE)
        self._source = source
        self._vault = primary_vault
        self._readiness_source = readiness_source

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
        return tuple(
            _detail(row, self._vault, self._readiness_source)
            for row in self._source.review_ready_proposals()
        )


class RegisteredLocalReviewProjectionStore:
    """Local projection derived only from exact frozen pipeline artifacts."""

    def __init__(
        self,
        task7_proposal: bytes | None,
        readiness_artifact: bytes | None,
        review_package: bytes | None,
        artifact_reader: Callable[[str], bytes],
        snapshot_reader: Callable[[], tuple[bytes, bytes, bytes, Callable[[str], bytes]] | None]
        | None = None,
    ) -> None:
        """Retain one exact package, or wait safely for the first complete package."""
        complete = (
            task7_proposal is not None
            and readiness_artifact is not None
            and review_package is not None
        )
        if not complete and any(
            value is not None for value in (task7_proposal, readiness_artifact, review_package)
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        self._task7_proposal: bytes | None = None
        self._readiness_artifact: bytes | None = None
        self._review_package: bytes | None = None
        self._artifact_reader = artifact_reader
        self._snapshot_reader = snapshot_reader
        self._evidence_audit_path: Path | None = None
        self._proposal_fingerprint: str | None = None
        self._detail: ProposalDetailProjection | None = None
        self._evidence_reads, self._evidence_audit_fingerprint = self._load_evidence_audit()
        if complete:
            if task7_proposal is None or readiness_artifact is None or review_package is None:
                raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
            self._adopt_snapshot(
                (task7_proposal, readiness_artifact, review_package),
                artifact_reader,
            )
        else:
            self._refresh()

    def bind_evidence_audit(self, path: Path) -> None:
        """Bind one retained audit ledger before this projection is served."""
        if (
            not path.is_absolute()
            or path.is_symlink()
            or self._evidence_audit_path is not None
            or self._evidence_reads
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        self._evidence_audit_path = path
        self._evidence_reads, self._evidence_audit_fingerprint = self._load_evidence_audit()

    @property
    def evidence_reads(self) -> list[tuple[str, str]]:
        """Expose the sanitized local evidence-read ledger."""
        return self._evidence_reads

    def retained_package(self) -> tuple[bytes, bytes]:
        """Reread and return the two exact immutable package artifacts."""
        self._refresh()
        if self._task7_proposal is None or self._readiness_artifact is None:
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        proposal = self._task7_proposal
        readiness = self._readiness_artifact
        fingerprint = _task7_proposal_fingerprint(proposal)
        _parse_hk_v1_review_readiness(readiness, fingerprint)
        return proposal, readiness

    def _details(self) -> tuple[ProposalDetailProjection, ...]:
        self._refresh()
        if (
            self._task7_proposal is None
            or self._readiness_artifact is None
            or self._review_package is None
            or self._detail is None
        ):
            return ()
        proposal_fingerprint = _task7_proposal_fingerprint(self._task7_proposal)
        readiness = _parse_hk_v1_review_readiness(self._readiness_artifact, proposal_fingerprint)
        detail = _parse_local_review_package(
            self._review_package,
            task7_proposal=self._task7_proposal,
            readiness=readiness,
            artifact_reader=self._artifact_reader,
        )
        if detail != self._detail:
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        return (detail,)

    def _refresh(self) -> None:
        """Adopt one newly retained, fully verified package without process restart."""
        if self._snapshot_reader is None:
            return
        try:
            snapshot = self._snapshot_reader()
        except (OSError, RuntimeError, ValueError) as error:
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT) from error
        if snapshot is None:
            if self._task7_proposal is not None:
                raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
            return
        task7, readiness_content, review_package, artifact_reader = snapshot
        if self._task7_proposal is not None and (
            task7 != self._task7_proposal
            or readiness_content != self._readiness_artifact
            or review_package != self._review_package
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        self._adopt_snapshot(
            (task7, readiness_content, review_package),
            artifact_reader,
        )

    def _adopt_snapshot(
        self,
        snapshot: tuple[bytes, bytes, bytes],
        artifact_reader: Callable[[str], bytes],
    ) -> None:
        """Validate all package bytes before making a new generation visible."""
        task7, readiness_content, review_package = snapshot
        proposal = _task7_proposal_facts(task7)
        readiness = _parse_hk_v1_review_readiness(readiness_content, proposal.fingerprint)
        _validate_readiness_against_proposal(readiness, proposal)
        detail = _parse_local_review_package(
            review_package,
            task7_proposal=task7,
            readiness=readiness,
            artifact_reader=artifact_reader,
        )
        self._task7_proposal = bytes(task7)
        self._readiness_artifact = bytes(readiness_content)
        self._review_package = bytes(review_package)
        self._artifact_reader = artifact_reader
        self._proposal_fingerprint = proposal.fingerprint
        self._detail = detail

    def load(self) -> tuple[str, tuple[ProposalProjection, ...]]:
        """Verify retained bytes before returning the local generation."""
        details = self._details()
        proposals = tuple(item.proposal for item in details)
        return fingerprint(
            [
                {
                    "manifest_fingerprint": item.manifest_fingerprint,
                    "proposal_id": item.proposal_id,
                    "review_version": item.review_version,
                    "status": item.status,
                }
                for item in proposals
            ]
        ), proposals

    def page(self, *, offset: int, limit: int) -> tuple[ProposalProjection, ...]:
        """Verify retained bytes before returning a bounded page."""
        _snapshot, proposals = self.load()
        return proposals[offset : offset + limit]

    def get(self, proposal_id: str) -> ProposalProjection | None:
        """Verify retained bytes before returning one summary."""
        detail = self.detail(proposal_id)
        return None if detail is None else detail.proposal

    def detail(self, proposal_id: str) -> ProposalDetailProjection | None:
        """Return one detail reconstructed from the retained Task 8 bytes."""
        return next(
            (item for item in self._details() if item.proposal.proposal_id == proposal_id),
            None,
        )

    def check(self) -> bool:
        """Report whether both retained local artifacts still verify exactly."""
        try:
            self._details()
        except ProposalProjectionError:
            return False
        return True

    def record_evidence_read(self, *, subject: str, evidence_id: str) -> None:
        """Append and read back one sanitized evidence-read fact durably."""
        if (
            type(subject) is not str
            or not subject
            or any(character.isspace() for character in subject)
            or _ISSUED_ID.fullmatch(evidence_id) is None
            or not evidence_id.startswith("evi_")
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        if self._evidence_audit_path is None:
            self._evidence_reads.append((subject, evidence_id))
            return
        path = self._evidence_audit_path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with exclusive_local_state_lock(path):
            current_fingerprint = (
                f"sha256:{sha256(path.read_bytes()).hexdigest()}" if path.is_file() else None
            )
            if path.is_symlink() or current_fingerprint != self._evidence_audit_fingerprint:
                raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
            sequence = len(self._evidence_reads) + 1
            previous = self._previous_fingerprint(sequence)
            entries = [
                self._evidence_entry(index, row[0], row[1], self._previous_fingerprint(index))
                for index, row in enumerate(self._evidence_reads, start=1)
            ]
            entries.append(self._evidence_entry(sequence, subject, evidence_id, previous))
            content = canonicalize(
                checked_json_value({"entries": entries, "schema_id": _EVIDENCE_AUDIT_SCHEMA})
            )
            temporary = path.with_suffix(".tmp")
            if temporary.is_symlink():
                raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
            temporary.write_bytes(content)
            temporary.chmod(0o600)
            temporary.replace(path)
            if path.is_symlink() or path.read_bytes() != content:
                raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
            self._evidence_reads.append((subject, evidence_id))
            self._evidence_audit_fingerprint = f"sha256:{sha256(content).hexdigest()}"

    def _previous_fingerprint(self, sequence: int) -> str:
        if sequence == 1:
            return _ZERO_FINGERPRINT
        subject, evidence_id = self._evidence_reads[sequence - 2]
        return self._evidence_entry_fingerprint(
            sequence - 1,
            subject,
            evidence_id,
            previous=self._previous_fingerprint(sequence - 1),
        )

    @staticmethod
    def _evidence_entry_fingerprint(
        sequence: int,
        subject: str,
        evidence_id: str,
        *,
        previous: str | None,
    ) -> str:
        prior = _ZERO_FINGERPRINT if previous is None else previous
        body = checked_json_value(
            {
                "evidence_id": evidence_id,
                "previous_entry_fingerprint": prior,
                "schema_id": _EVIDENCE_AUDIT_ENTRY_SCHEMA,
                "sequence": sequence,
                "subject": subject,
            }
        )
        return f"sha256:{sha256(canonicalize(body)).hexdigest()}"

    @classmethod
    def _evidence_entry(
        cls,
        sequence: int,
        subject: str,
        evidence_id: str,
        previous: str,
    ) -> dict[str, JsonValue]:
        return {
            "entry_fingerprint": cls._evidence_entry_fingerprint(
                sequence, subject, evidence_id, previous=previous
            ),
            "evidence_id": evidence_id,
            "previous_entry_fingerprint": previous,
            "schema_id": _EVIDENCE_AUDIT_ENTRY_SCHEMA,
            "sequence": sequence,
            "subject": subject,
        }

    def _load_evidence_audit(self) -> tuple[list[tuple[str, str]], str | None]:
        path = self._evidence_audit_path
        if path is None or not path.exists():
            return [], None
        if path.is_symlink() or not path.is_file():
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        content = path.read_bytes()
        if not content or len(content) > _MAX_EVIDENCE_AUDIT_BYTES:
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        try:
            value = parse_json_bytes(content, max_bytes=_MAX_EVIDENCE_AUDIT_BYTES)
        except ContractViolation as error:
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT) from error
        if (
            not isinstance(value, dict)
            or set(value) != {"entries", "schema_id"}
            or value.get("schema_id") != _EVIDENCE_AUDIT_SCHEMA
            or canonicalize(value) != content
            or not isinstance(value.get("entries"), list)
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        rows: list[tuple[str, str]] = []
        previous = _ZERO_FINGERPRINT
        for sequence, raw in enumerate(cast("list[JsonValue]", value["entries"]), start=1):
            if not isinstance(raw, dict):
                raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
            subject = raw.get("subject")
            evidence_id = raw.get("evidence_id")
            if (
                set(raw)
                != {
                    "entry_fingerprint",
                    "evidence_id",
                    "previous_entry_fingerprint",
                    "schema_id",
                    "sequence",
                    "subject",
                }
                or raw.get("schema_id") != _EVIDENCE_AUDIT_ENTRY_SCHEMA
                or raw.get("sequence") != sequence
                or raw.get("previous_entry_fingerprint") != previous
                or type(subject) is not str
                or not subject
                or any(character.isspace() for character in subject)
                or type(evidence_id) is not str
                or not evidence_id.startswith("evi_")
                or _ISSUED_ID.fullmatch(evidence_id) is None
            ):
                raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
            expected = self._evidence_entry_fingerprint(
                sequence, subject, evidence_id, previous=previous
            )
            if raw.get("entry_fingerprint") != expected:
                raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
            rows.append((subject, evidence_id))
            previous = expected
        return rows, f"sha256:{sha256(content).hexdigest()}"

    def _active_artifact_reader(self) -> Callable[[str], bytes]:
        """Return the reader for one freshly verified active generation."""
        self._refresh()
        if self._detail is None:
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        return self._artifact_reader

    def read_evidence(self, evidence_id: str) -> bytes:
        """Return the exact retained traceability row that binds one evidence ID."""
        artifact_reader = self._active_artifact_reader()
        lookup_content = artifact_reader(_ROLE_PATHS["RECORD_TRACEABILITY"])
        lookup = parse_json_bytes(lookup_content, max_bytes=2_000_000)
        if not isinstance(lookup, dict) or not isinstance(lookup.get("shards"), list):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        shards = cast("list[JsonValue]", lookup["shards"])
        matches: list[bytes] = []
        for raw_shard_value in shards:
            if not isinstance(raw_shard_value, dict):
                raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
            raw_shard = cast("dict[str, JsonValue]", raw_shard_value)
            if not isinstance(raw_shard.get("path"), str):
                raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
            shard = artifact_reader(f"record-traceability/{raw_shard['path']}")
            for line in shard.splitlines(keepends=True):
                if not line.strip():
                    continue
                row = parse_json_bytes(line.rstrip(b"\r\n"), max_bytes=1_000_000)
                if not isinstance(row, dict) or not isinstance(row.get("evidence_refs"), list):
                    raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
                references = cast("list[JsonValue]", row["evidence_refs"])
                if any(
                    isinstance(reference, dict) and reference.get("ref_id") == evidence_id
                    for reference in references
                ):
                    matches.append(line)
        if len(matches) != 1:
            raise ProposalProjectionError(ProposalProjectionErrorCode.SNAPSHOT)
        return matches[0]


def _parse_local_review_package(  # noqa: C901, PLR0915 - one complete local trust boundary.
    content: bytes,
    *,
    task7_proposal: bytes,
    readiness: HKV1ReviewReadinessProjection,
    artifact_reader: Callable[[str], bytes],
) -> ProposalDetailProjection:
    """Recover the Review surface from one exact explicit pipeline package."""
    try:
        value = parse_json_bytes(content, max_bytes=2_000_000)
    except ContractViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    expected = {
        "artifacts",
        "base_serving_state_fingerprint",
        "base_serving_state_id",
        "candidate_serving_state_fingerprint",
        "candidate_serving_state_id",
        "observation_cutoff",
        "package_fingerprint",
        "promotion_manifest_fingerprint",
        "promotion_manifest_id",
        "proposal_id",
        "schema_id",
        "title",
        "valid_from",
        "valid_until",
        "validity_predicates",
    }
    if not isinstance(value, dict) or set(value) != expected or canonicalize(value) != content:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    proposal_facts = _task7_proposal_facts(task7_proposal)
    artifacts_value = value.get("artifacts")
    predicates_value = value.get("validity_predicates")
    if not isinstance(artifacts_value, list) or not isinstance(predicates_value, list):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    artifacts: list[ProposalArtifactProjection] = []
    for item in artifacts_value:
        if not isinstance(item, dict) or set(item) != {
            "byte_length",
            "fingerprint",
            "media_type",
            "path",
            "role",
        }:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        byte_length = _integer(item, "byte_length")
        if byte_length <= 0:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        artifacts.append(
            ProposalArtifactProjection(
                _text(item, "role"),
                _text(item, "path"),
                _text(item, "media_type"),
                _sha256(item, "fingerprint"),
                byte_length,
            )
        )
    predicates = _contract_references(predicates_value)
    observation_cutoff = _text(value, "observation_cutoff")
    valid_from = _text(value, "valid_from")
    valid_until = _text(value, "valid_until")
    if (
        value.get("schema_id") != "asklegal.hk-v1-local-review-package/v1"
        or observation_cutoff != proposal_facts.observation_cutoff
        or tuple(sorted(predicates)) != predicates
        or len(set(predicates)) != len(predicates)
        or valid_from >= valid_until
        or tuple(item.role for item in artifacts) != tuple(sorted(_ROLE_PATHS))
        or tuple(item.path for item in artifacts)
        != tuple(_ROLE_PATHS[item.role] for item in artifacts)
        or any(item.media_type != "application/json" for item in artifacts)
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    contents: dict[str, bytes] = {}
    for artifact in artifacts:
        try:
            artifact_content = artifact_reader(artifact.path)
            artifact_value = parse_json_bytes(artifact_content, max_bytes=1_000_000)
        except (ContractViolation, OSError, RuntimeError, TypeError, ValueError) as error:
            raise ProposalProjectionError(ProposalProjectionErrorCode.READ) from error
        if (
            type(artifact_content) is not bytes
            or len(artifact_content) != artifact.byte_length
            or f"sha256:{sha256(artifact_content).hexdigest()}" != artifact.fingerprint
            or not isinstance(artifact_value, dict)
            or canonicalize(artifact_value) != artifact_content
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.FINGERPRINT)
        contents[artifact.role] = artifact_content
    title = _text(value, "title")
    base_fingerprint = _sha256(value, "base_serving_state_fingerprint")
    evidence_fingerprint = hk_v1_local_review_evidence_fingerprint(
        artifacts,
        proposal_facts.fingerprint,
        readiness.fingerprint,
        observation_cutoff=observation_cutoff,
        title=title,
        base_serving_state_fingerprint=base_fingerprint,
    )
    required = {
        ("HK_V1_REVIEW_EVIDENCE", "1.0.0", evidence_fingerprint),
        ("HK_V1_REVIEW_READINESS", "1.0.0", readiness.fingerprint),
        ("HK_V1_TWO_FAMILY_PROPOSAL", "1.0.0", proposal_facts.fingerprint),
    }
    promotion_fingerprint = _sha256(value, "promotion_manifest_fingerprint")
    promotion_id = _identifier(value, "promotion_manifest_id", "pmn")
    promotion = promotion_facts_from_bytes(
        contents["PROMOTION_MANIFEST"],
        manifest_id=promotion_id,
        manifest_fingerprint=promotion_fingerprint,
    )
    unsigned = dict(value)
    observed_package_fingerprint = unsigned.pop("package_fingerprint", None)
    computed_package_fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(unsigned))).hexdigest()}"
    )
    base_id = _exact_id(value, "base_serving_state_id", "srv")
    candidate_id = _exact_id(value, "candidate_serving_state_id", "srv")
    candidate_fingerprint = _sha256(value, "candidate_serving_state_fingerprint")
    traceability_shards = _local_traceability_shards(
        contents["RECORD_TRACEABILITY"],
        artifact_reader,
    )
    try:
        validate_v1_proposal_members(
            contents,
            ProposalMemberBindings(
                observation_cutoff,
                promotion_id,
                promotion_fingerprint,
                base_id,
                candidate_id,
                candidate_fingerprint,
            ),
            traceability_shards,
        )
    except ProposalMemberViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    _validate_readiness_against_desired_state(
        readiness,
        contents["DESIRED_STATE_INVENTORIES"],
    )
    if (
        not required.issubset(predicates)
        or observed_package_fingerprint != computed_package_fingerprint
        or _identifier(value, "proposal_id", "ppk")
        != _stable_id("ppk", promotion_fingerprint, evidence_fingerprint)
        or promotion.validity_predicates != predicates
        or promotion.valid_from != valid_from
        or promotion.valid_until != valid_until
        or promotion.base_serving_state_id != base_id
        or promotion.candidate_serving_state_id != candidate_id
        or promotion.candidate_serving_state_fingerprint != candidate_fingerprint
        or promotion.rollback_serving_state_id != readiness.rollback_state_id
        or promotion.embedding_profile_fingerprint != readiness.embedding_profile_fingerprint
        or promotion.target_name != readiness.target_name
        or promotion.effect_types
        != (
            "EMBEDDING_PROVIDER_CALL",
            "PINECONE_MUTATION",
            "BACKUP_MUTATION",
            "RELEASE_PUBLICATION",
        )
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return ProposalDetailProjection(
        ProposalProjection(
            _identifier(value, "proposal_id", "ppk"),
            promotion_fingerprint,
            "REVIEW_READY",
            title,
            0,
        ),
        computed_package_fingerprint,
        promotion_id,
        observation_cutoff,
        valid_from,
        valid_until,
        predicates,
        base_id,
        base_fingerprint,
        candidate_id,
        candidate_fingerprint,
        tuple(artifacts),
        hk_v1_readiness=readiness,
    )


def _local_traceability_shards(
    manifest_content: bytes,
    artifact_reader: Callable[[str], bytes],
) -> dict[str, bytes]:
    """Read each exact NDJSON shard declared by the verified traceability member."""
    try:
        manifest = parse_json_bytes(manifest_content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    raw_shards = manifest.get("shards") if isinstance(manifest, dict) else None
    if not isinstance(raw_shards, list) or not raw_shards:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    paths: list[str] = []
    shards: dict[str, bytes] = {}
    for item in raw_shards:
        if not isinstance(item, dict):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        path = item.get("path")
        if type(path) is not str or re.fullmatch(r"entries/rts_[0-9a-f]{48}\.ndjson", path) is None:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        paths.append(path)
        try:
            shards[path] = artifact_reader(f"record-traceability/{path}")
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise ProposalProjectionError(ProposalProjectionErrorCode.READ) from error
    if tuple(paths) != tuple(sorted(set(paths))):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return shards


@dataclass(frozen=True, slots=True)
class _Task7ProposalFacts:
    fingerprint: str
    observation_cutoff: str
    model_profile_fingerprint: str
    embedding_profile_fingerprint: str


def _task7_proposal_facts(  # noqa: C901 - exact Task 7 contract stays visible.
    content: bytes,
) -> _Task7ProposalFacts:
    """Recompute the exact frozen two-family proposal identity from retained bytes."""
    try:
        value = parse_json_bytes(content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    expected = {
        "acquisition_manifests",
        "completeness_fingerprint",
        "coverage_report_fingerprint",
        "embedding_capability_evidence_ref",
        "embedding_invocation_count",
        "embedding_profile_fingerprint",
        "explicit_exclusions",
        "fingerprint",
        "included_material_families",
        "model_capability_evidence_ref",
        "model_invocation_count",
        "model_profile_fingerprint",
        "observation_cutoff",
        "prepared_batches",
        "release_state",
        "schema_id",
        "scope_ids",
        "status",
    }
    if not isinstance(value, dict) or set(value) != expected or canonicalize(value) != content:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    unsigned = dict(value)
    observed = unsigned.pop("fingerprint", None)
    computed = f"sha256:{sha256(canonicalize(checked_json_value(unsigned))).hexdigest()}"
    exclusions = value.get("explicit_exclusions")
    acquisitions = value.get("acquisition_manifests")
    batches = value.get("prepared_batches")
    observation_cutoff = value.get("observation_cutoff")
    model_fingerprint = value.get("model_profile_fingerprint")
    embedding_fingerprint = value.get("embedding_profile_fingerprint")
    if (
        observed != computed
        or value.get("schema_id") != "asklegal.hk-v1-two-family-proposal-manifest/v1"
        or value.get("status") != "FROZEN_PROPOSAL_READY_FOR_REVIEW"
        or value.get("included_material_families") != ["CASES", "LEGISLATION"]
        or value.get("scope_ids") != list(_HK_V1_SCOPES)
        or exclusions != ["HKEX_REGULATORY_POST_V1", "HK-PRINCIPLES"]
        or type(observation_cutoff) is not str
        or _UTC_TIMESTAMP.fullmatch(observation_cutoff) is None
        or type(model_fingerprint) is not str
        or _FINGERPRINT.fullmatch(model_fingerprint) is None
        or type(embedding_fingerprint) is not str
        or _FINGERPRINT.fullmatch(embedding_fingerprint) is None
        or value.get("model_invocation_count") != 0
        or value.get("embedding_invocation_count") != 0
        or value.get("release_state") != "WITHHELD_PENDING_NAMED_HUMAN_REVIEW"
        or type(value.get("model_capability_evidence_ref")) is not str
        or not value.get("model_capability_evidence_ref")
        or type(value.get("embedding_capability_evidence_ref")) is not str
        or not value.get("embedding_capability_evidence_ref")
        or not isinstance(acquisitions, list)
        or not isinstance(batches, list)
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    acquisition_rows: list[dict[str, str]] = []
    acquisition_by_family: dict[str, tuple[str, str]] = {}
    for item in acquisitions:
        if not isinstance(item, dict) or set(item) != {
            "journal_head_fingerprint",
            "manifest_fingerprint",
            "material_family",
        }:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        family = _text(item, "material_family")
        manifest_fingerprint = _sha256(item, "manifest_fingerprint")
        journal_fingerprint = _sha256(item, "journal_head_fingerprint")
        acquisition_rows.append(
            {
                "material_family": family,
                "manifest_fingerprint": manifest_fingerprint,
                "journal_head_fingerprint": journal_fingerprint,
            }
        )
        acquisition_by_family[family] = (manifest_fingerprint, journal_fingerprint)
    if (
        tuple(item["material_family"] for item in acquisition_rows) != ("CASES", "LEGISLATION")
        or len(acquisition_by_family) != _HK_V1_FAMILY_COUNT
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    prepared_rows: list[dict[str, str]] = []
    expected_batch_fields = {
        "acquisition_manifest_fingerprint",
        "artifact_document_fingerprint",
        "artifact_fingerprint",
        "artifact_ref",
        "evidence_set_fingerprint",
        "journal_head_fingerprint",
        "material_family",
        "scope_id",
        "semantic_profile_fingerprint",
    }
    for item in batches:
        if not isinstance(item, dict) or set(item) != expected_batch_fields:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        scope_id = _text(item, "scope_id")
        family = _text(item, "material_family")
        expected_family = "CASES" if scope_id.startswith("HK-CASE-") else "LEGISLATION"
        acquisition = acquisition_by_family.get(family)
        row = {
            "material_family": family,
            "scope_id": scope_id,
            "acquisition_manifest_fingerprint": _sha256(item, "acquisition_manifest_fingerprint"),
            "journal_head_fingerprint": _sha256(item, "journal_head_fingerprint"),
            "evidence_set_fingerprint": _sha256(item, "evidence_set_fingerprint"),
            "semantic_profile_fingerprint": _sha256(item, "semantic_profile_fingerprint"),
            "artifact_ref": _text(item, "artifact_ref"),
            "artifact_document_fingerprint": _sha256(item, "artifact_document_fingerprint"),
            "artifact_fingerprint": _sha256(item, "artifact_fingerprint"),
        }
        if (
            family != expected_family
            or acquisition is None
            or (row["acquisition_manifest_fingerprint"], row["journal_head_fingerprint"])
            != acquisition
            or row["semantic_profile_fingerprint"] != model_fingerprint
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        prepared_rows.append(row)
    if tuple(item["scope_id"] for item in prepared_rows) != _HK_V1_SCOPES:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    completeness = checked_json_value(
        {
            "observation_cutoff": observation_cutoff,
            "included_material_families": ["CASES", "LEGISLATION"],
            "scope_ids": list(_HK_V1_SCOPES),
            "acquisition_manifests": acquisition_rows,
            "prepared_batches": prepared_rows,
            "model_profile_fingerprint": model_fingerprint,
            "embedding_profile_fingerprint": embedding_fingerprint,
        }
    )
    if value.get("completeness_fingerprint") != (
        f"sha256:{sha256(canonicalize(completeness)).hexdigest()}"
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return _Task7ProposalFacts(
        computed,
        observation_cutoff,
        model_fingerprint,
        embedding_fingerprint,
    )


def _task7_proposal_fingerprint(content: bytes) -> str:
    """Compatibility helper returning the exact verified Task 7 identity."""
    return _task7_proposal_facts(content).fingerprint


def _validate_readiness_against_proposal(
    readiness: HKV1ReviewReadinessProjection,
    proposal: _Task7ProposalFacts,
) -> None:
    if (
        readiness.proposal_fingerprint != proposal.fingerprint
        or readiness.model_profile_fingerprint != proposal.model_profile_fingerprint
        or readiness.embedding_profile_fingerprint != proposal.embedding_profile_fingerprint
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)


def _validate_readiness_against_desired_state(
    readiness: HKV1ReviewReadinessProjection,
    content: bytes,
) -> None:
    """Require the human-visible target inventory to equal the verified DSI member."""
    try:
        value = parse_json_bytes(content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE) from error
    records = value.get("records") if isinstance(value, dict) else None
    if not isinstance(records, list):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    desired_members: list[tuple[str, str, str]] = []
    for item in records:
        if not isinstance(item, dict):
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        scope_id = _text(item, "scope_id")
        family = _HK_V1_SCOPE_FAMILIES.get(scope_id)
        if family is None:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        desired_members.append((_text(item, "record_id"), scope_id, family))
    member_scopes = {scope_id for _record_id, scope_id, _family in desired_members}
    desired_zero_scopes = tuple(sorted(set(_HK_V1_SCOPES) - member_scopes))
    if (
        tuple(desired_members) != readiness.target_members
        or desired_zero_scopes != readiness.zero_record_scope_ids
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)


def hk_v1_local_review_evidence_fingerprint(  # noqa: PLR0913 - exact root fact set.
    artifacts: tuple[ProposalArtifactProjection, ...] | list[ProposalArtifactProjection],
    task7_proposal_fingerprint: str,
    readiness_fingerprint: str,
    *,
    observation_cutoff: str,
    title: str,
    base_serving_state_fingerprint: str,
) -> str:
    """Bind every non-executable reviewed artifact without a manifest hash cycle."""
    document = checked_json_value(
        {
            "artifacts": [
                {
                    "byte_length": item.byte_length,
                    "fingerprint": item.fingerprint,
                    "media_type": item.media_type,
                    "path": item.path,
                    "role": item.role,
                }
                for item in artifacts
                if item.role != "PROMOTION_MANIFEST"
            ],
            "base_serving_state_fingerprint": base_serving_state_fingerprint,
            "observation_cutoff": observation_cutoff,
            "readiness_fingerprint": readiness_fingerprint,
            "task7_proposal_fingerprint": task7_proposal_fingerprint,
            "title": title,
        }
    )
    return f"sha256:{sha256(canonicalize(document)).hexdigest()}"


def _detail(
    row: ReviewReadyProposalRow,
    vault: ImmutableVault,
    readiness_source: RegisteredHKV1ReadinessSource | None,
) -> ProposalDetailProjection:
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
    bindings = tuple(
        item
        for item in root.validity_predicates
        if item[0] == "HK_V1_TWO_FAMILY_PROPOSAL" and item[1] == "1.0.0"
    )
    readiness = None
    if bindings:
        if len(bindings) != 1 or readiness_source is None:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        readiness_reference = readiness_source.readiness_reference(package_id, bindings[0][2])
        if readiness_reference is None:
            raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
        expected_key = f"proposal-packages/{package_id}/task-8/review-readiness.json"
        if (
            readiness_reference.vault is not VaultName.PRIMARY
            or readiness_reference.logical_key != expected_key
        ):
            raise ProposalProjectionError(ProposalProjectionErrorCode.REFERENCE)
        readiness = _parse_hk_v1_review_readiness(
            _read_exact(vault, readiness_reference), bindings[0][2]
        )
    decision = _decision_projection(
        row,
        root,
        promotion_manifest_id=promotion_manifest_id,
        promotion_fingerprint=promotion_fingerprint,
        readiness=readiness,
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
        readiness,
    )


def _decision_projection(
    row: ReviewReadyProposalRow,
    root: _ProposalRoot,
    *,
    promotion_manifest_id: str,
    promotion_fingerprint: str,
    readiness: HKV1ReviewReadinessProjection | None,
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
    observed_readiness = value.get("review_readiness_fingerprint")
    if (readiness is None and observed_readiness is not None) or (
        readiness is not None and observed_readiness != readiness.fingerprint
    ):
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
    if not isinstance(value, dict):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
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
    if "review_readiness_fingerprint" in value:
        expected.add("review_readiness_fingerprint")
    if (
        set(value) != expected
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
    rollback_serving_state_id: str
    embedding_profile_fingerprint: str
    target_name: str
    valid_from: str
    valid_until: str
    validity_predicates: tuple[tuple[str, str, str], ...]
    effect_types: tuple[str, ...]


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
    effect_types = _promotion_actions(
        value,
        _PromotionActionBindings(
            fingerprints[0],
            fingerprints[2],
            fingerprints[3],
            valid_from,
            valid_until,
        ),
    )
    environment = _text(value, "environment")
    freeze_date = _text(value, "freeze_date")
    jurisdiction = _text(value, "jurisdiction")
    project_id = _text(value, "project_id")
    if (
        jurisdiction != "hkg"
        or re.fullmatch(r"[a-z0-9-]+", environment) is None
        or re.fullmatch(r"[0-9]{8}", freeze_date) is None
        or re.fullmatch(r"[a-z0-9-]+", project_id) is None
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    base_id = _exact_id(value, "base_serving_state_id", "srv")
    candidate_id = _exact_id(value, "candidate_serving_state_id", "srv")
    rollback_id = _exact_id(value, "rollback_serving_state_id", "srv")
    return _PromotionFacts(
        base_id,
        candidate_id,
        fingerprints[0],
        rollback_id,
        fingerprints[3],
        f"asklegal-{environment}-{jurisdiction}-{freeze_date}-{fingerprints[0][7:19]}",
        valid_from,
        valid_until,
        predicates,
        effect_types,
    )


def _promotion_actions(
    value: Mapping[str, JsonValue],
    bindings: _PromotionActionBindings,
) -> tuple[str, ...]:
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
    effect_types: list[str] = []
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
        effect_types.append(effect_type)
    if len(set(action_ids)) != len(action_ids) or len(set(idempotency_keys)) != len(
        idempotency_keys
    ):
        raise ProposalProjectionError(ProposalProjectionErrorCode.PACKAGE)
    return tuple(effect_types)


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


def _integer(document: Mapping[str, JsonValue], field: str) -> int:
    value = document.get(field)
    if type(value) is not int:
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
