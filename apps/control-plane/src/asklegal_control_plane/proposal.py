"""M6 manifest-last proposal-package preparation owned by the control plane."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Never, Protocol

from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import (
    CorpusError,
    CorpusErrorCode,
    ProposalPackage,
    ProposalPackageInput,
    freeze_proposal_package,
)
from asklegal_evidence_vault import (
    ImmutableVault,
    RetentionProfile,
    VaultName,
)
from asklegal_management_register import RegisterEventCommand
from asklegal_promotion import (
    PromotionError,
    ProposalMemberReceipt,
    StoredProposalPackage,
    TraceabilityShardReceipt,
    promotion_approval_snapshot_from_bytes,
    proposal_receipt_document,
    proposal_receipt_fingerprint,
    read_stored_proposal_package,
)
from asklegal_reporting import (
    ExactProposalArtifactReceipt,
    HongKongV1TwoFamilyCoverageReport,
    PreparedBatchArtifact,
    ProposalEvidenceError,
    VerifiedSemanticCapability,
    build_hk_v1_two_family_coverage_report,
    parse_prepared_batch_artifact,
    project_hk_v1_two_family_acquisition,
    provider_disabled_profile_receipt_ref,
    verify_provider_disabled_semantic_capability,
)

if TYPE_CHECKING:
    from asklegal_management_register import V1CommandResult
    from asklegal_reporting.hk_v1_coverage import HongKongV1CoverageMatrix

_PROPOSAL_SCHEMA = "schemas/promotion-domain.schema.json#/$defs/proposal_package_manifest"
_HK_V1_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_HK_V1_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


@dataclass(frozen=True, slots=True)
class PreparedBatchBinding:
    """One deterministic local parse/model-request preparation artifact."""

    material_family: str
    scope_id: str
    observation_cutoff: str
    acquisition_manifest_fingerprint: str
    journal_head_fingerprint: str
    evidence_set_fingerprint: str
    semantic_profile_fingerprint: str
    artifact_ref: str
    artifact_fingerprint: str


class ProposalEvidenceReader(Protocol):
    """Read one exact immutable local proposal-input artifact."""

    def read_exact(self, logical_ref: str) -> bytes:
        """Return bytes for the exact logical reference or fail."""
        ...


class CurrentAcquisitionJournalHeadReader(Protocol):
    """Read the authoritative current head for each proposal family."""

    def read_current(self, material_family: str) -> str:
        """Return the current durable head for the exact material family."""
        ...


@dataclass(frozen=True, slots=True)
class TwoFamilyProposalRequest:
    """Complete inputs required before freezing the two-family V1 proposal."""

    accepted_observation_cutoff: str
    legislation_manifest: bytes | None
    cases_manifest: bytes | None
    expected_legislation_journal_head: str
    expected_cases_journal_head: str
    prepared_batches: tuple[PreparedBatchBinding, ...]
    model_profile_fingerprint: str
    embedding_profile_fingerprint: str
    model_capability_evidence_ref: str
    embedding_capability_evidence_ref: str


@dataclass(frozen=True, slots=True)
class HongKongV1TwoFamilyProposalManifest:
    """One frozen, provider-disabled proposal-readiness artifact."""

    observation_cutoff: str
    scope_ids: tuple[str, ...]
    included_material_families: tuple[str, ...]
    explicit_exclusions: tuple[str, ...]
    coverage_report: HongKongV1TwoFamilyCoverageReport
    coverage_report_fingerprint: str
    completeness_content: bytes
    completeness_fingerprint: str
    content: bytes
    fingerprint: str


def freeze_hk_v1_two_family_proposal(
    request: TwoFamilyProposalRequest,
    matrix: HongKongV1CoverageMatrix,
    current_head_reader: CurrentAcquisitionJournalHeadReader,
    evidence_reader: ProposalEvidenceReader,
) -> HongKongV1TwoFamilyProposalManifest:
    """Freeze only a four-scope proposal with complete reconciled acquisition facts."""
    if type(request) is not TwoFamilyProposalRequest:
        _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_PROPOSAL_INVALID")
    projected = project_hk_v1_two_family_acquisition(
        request.legislation_manifest,
        request.cases_manifest,
        request.accepted_observation_cutoff,
    )
    acquisitions = {item.material_family: item for item in projected.acquisitions}
    if not callable(getattr(current_head_reader, "read_current", None)):
        _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_JOURNAL_HEAD_INVALID")
    try:
        heads = {
            family: current_head_reader.read_current(family) for family in ("CASES", "LEGISLATION")
        }
    except Exception as error:
        message = "HK_V1_TWO_FAMILY_JOURNAL_HEAD_UNAVAILABLE"
        raise ValueError(message) from error
    if set(heads) != {"CASES", "LEGISLATION"} or any(
        type(value) is not str or _HK_V1_FINGERPRINT.fullmatch(value) is None
        for value in heads.values()
    ):
        _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_JOURNAL_HEAD_INVALID")
    if (
        heads["LEGISLATION"] != acquisitions["LEGISLATION"].journal_head_fingerprint
        or heads["CASES"] != acquisitions["CASES"].journal_head_fingerprint
        or request.expected_legislation_journal_head != heads["LEGISLATION"]
        or request.expected_cases_journal_head != heads["CASES"]
    ):
        _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_JOURNAL_HEAD_STALE")
    _validate_hk_v1_semantic_request(request)
    verified_capabilities = _verified_semantic_capabilities(request, evidence_reader)
    model_capability = verified_capabilities[1]
    batches = _validate_hk_v1_prepared_batches(
        request, acquisitions, evidence_reader, model_capability
    )
    coverage = build_hk_v1_two_family_coverage_report(
        matrix, projected.acquisitions, verified_capabilities
    )
    completeness_body = checked_json_value(
        {
            "observation_cutoff": projected.observation_cutoff,
            "included_material_families": list(coverage.included_material_families),
            "scope_ids": list(_HK_V1_SCOPES),
            "acquisition_manifests": [
                {
                    "material_family": item.material_family,
                    "manifest_fingerprint": item.manifest_fingerprint,
                    "journal_head_fingerprint": item.journal_head_fingerprint,
                }
                for item in projected.acquisitions
            ],
            "prepared_batches": [_prepared_batch_document(item) for item in batches],
            "model_profile_fingerprint": request.model_profile_fingerprint,
            "embedding_profile_fingerprint": request.embedding_profile_fingerprint,
        }
    )
    completeness_content = canonicalize(completeness_body)
    completeness_fingerprint = _fingerprint(completeness_content)
    body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1-two-family-proposal-manifest/v1",
            "status": "FROZEN_PROPOSAL_READY_FOR_REVIEW",
            "observation_cutoff": projected.observation_cutoff,
            "included_material_families": list(coverage.included_material_families),
            "scope_ids": list(_HK_V1_SCOPES),
            "explicit_exclusions": list(coverage.explicit_exclusions),
            "coverage_report_fingerprint": coverage.fingerprint,
            "acquisition_manifests": [
                {
                    "material_family": item.material_family,
                    "manifest_fingerprint": item.manifest_fingerprint,
                    "journal_head_fingerprint": item.journal_head_fingerprint,
                }
                for item in projected.acquisitions
            ],
            "prepared_batches": [_prepared_batch_document(item) for item in batches],
            "model_profile_fingerprint": request.model_profile_fingerprint,
            "embedding_profile_fingerprint": request.embedding_profile_fingerprint,
            "model_capability_evidence_ref": request.model_capability_evidence_ref,
            "embedding_capability_evidence_ref": request.embedding_capability_evidence_ref,
            "model_invocation_count": 0,
            "embedding_invocation_count": 0,
            "release_state": "WITHHELD_PENDING_NAMED_HUMAN_REVIEW",
            "completeness_fingerprint": completeness_fingerprint,
        }
    )
    fingerprint = _fingerprint(canonicalize(body))
    if type(body) is not dict:  # pragma: no cover - checked literal is an object.
        _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_PROPOSAL_INVALID")
    content = canonicalize({**body, "fingerprint": fingerprint})
    return HongKongV1TwoFamilyProposalManifest(
        observation_cutoff=projected.observation_cutoff,
        scope_ids=_HK_V1_SCOPES,
        included_material_families=coverage.included_material_families,
        explicit_exclusions=coverage.explicit_exclusions,
        coverage_report=coverage,
        coverage_report_fingerprint=coverage.fingerprint,
        completeness_content=completeness_content,
        completeness_fingerprint=completeness_fingerprint,
        content=content,
        fingerprint=fingerprint,
    )


def _validate_hk_v1_semantic_request(request: TwoFamilyProposalRequest) -> None:
    for value in (
        request.model_profile_fingerprint,
        request.embedding_profile_fingerprint,
        request.expected_legislation_journal_head,
        request.expected_cases_journal_head,
    ):
        if type(value) is not str or _HK_V1_FINGERPRINT.fullmatch(value) is None:
            _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_PROPOSAL_INVALID")
    if any(
        type(value) is not str or not value or value != value.strip()
        for value in (
            request.model_capability_evidence_ref,
            request.embedding_capability_evidence_ref,
        )
    ):
        _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_PROPOSAL_INVALID")


def _verified_semantic_capabilities(
    request: TwoFamilyProposalRequest,
    evidence_reader: ProposalEvidenceReader,
) -> tuple[VerifiedSemanticCapability, VerifiedSemanticCapability]:
    verified: list[VerifiedSemanticCapability] = []
    for capability, profile_fingerprint, evidence_ref in (
        (
            "EMBEDDING",
            request.embedding_profile_fingerprint,
            request.embedding_capability_evidence_ref,
        ),
        ("MODEL", request.model_profile_fingerprint, request.model_capability_evidence_ref),
    ):
        profile_ref = provider_disabled_profile_receipt_ref(capability, profile_fingerprint)
        try:
            profile_content = evidence_reader.read_exact(profile_ref)
            evidence_content = evidence_reader.read_exact(evidence_ref)
        except Exception as error:
            message = "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_READ_FAILED"
            raise ValueError(message) from error
        try:
            item = verify_provider_disabled_semantic_capability(
                capability,
                profile_ref,
                profile_content,
                evidence_ref,
                evidence_content,
                request.accepted_observation_cutoff,
            )
        except ProposalEvidenceError as error:
            message = "HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_INVALID"
            raise ValueError(message) from error
        if item.profile_fingerprint != profile_fingerprint:
            _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_SEMANTIC_EVIDENCE_INVALID")
        verified.append(item)
    return verified[0], verified[1]


def _validate_hk_v1_prepared_batches(
    request: TwoFamilyProposalRequest,
    acquisitions: Mapping[str, object],
    evidence_reader: ProposalEvidenceReader,
    model_capability: VerifiedSemanticCapability,
) -> tuple[PreparedBatchArtifact, ...]:
    if (
        type(request.prepared_batches) is not tuple
        or len(request.prepared_batches) != len(_HK_V1_SCOPES)
        or any(type(item) is not PreparedBatchBinding for item in request.prepared_batches)
    ):
        _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_PREPARED_BATCH_INVALID")
    bindings = tuple(sorted(request.prepared_batches, key=lambda item: item.scope_id))
    if tuple(item.scope_id for item in bindings) != _HK_V1_SCOPES:
        _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_PREPARED_BATCH_INVALID")
    batches: list[PreparedBatchArtifact] = []
    for item in bindings:
        family = "CASES" if item.scope_id.startswith("HK-CASE-") else "LEGISLATION"
        acquisition = acquisitions[family]
        manifest_fingerprint = getattr(acquisition, "manifest_fingerprint", None)
        journal_head = getattr(acquisition, "journal_head_fingerprint", None)
        evidence_refs = getattr(acquisition, "verified_evidence_refs", None)
        try:
            content = evidence_reader.read_exact(item.artifact_ref)
        except Exception as error:
            message = "HK_V1_TWO_FAMILY_PREPARED_BATCH_READ_FAILED"
            raise ValueError(message) from error
        try:
            prepared = parse_prepared_batch_artifact(
                ExactProposalArtifactReceipt(item.artifact_ref, item.artifact_fingerprint),
                content,
            )
        except ProposalEvidenceError as error:
            message = "HK_V1_TWO_FAMILY_PREPARED_BATCH_INVALID"
            raise ValueError(message) from error
        if (
            prepared.material_family != family
            or prepared.scope_id != item.scope_id
            or prepared.observation_cutoff != request.accepted_observation_cutoff
            or prepared.acquisition_manifest_fingerprint != manifest_fingerprint
            or prepared.journal_head_fingerprint != journal_head
            or prepared.evidence_refs != evidence_refs
            or prepared.evidence_set_fingerprint != item.evidence_set_fingerprint
            or prepared.semantic_profile_fingerprint != request.model_profile_fingerprint
            or prepared.semantic_profile_fingerprint != item.semantic_profile_fingerprint
            or prepared.capability_evidence_ref != model_capability.evidence_ref
            or prepared.receipt.fingerprint != item.artifact_fingerprint
        ):
            _hk_v1_proposal_fail("HK_V1_TWO_FAMILY_PREPARED_BATCH_INVALID")
        batches.append(prepared)
    return tuple(batches)


def _prepared_batch_document(item: PreparedBatchArtifact) -> dict[str, JsonValue]:
    return {
        "material_family": item.material_family,
        "scope_id": item.scope_id,
        "acquisition_manifest_fingerprint": item.acquisition_manifest_fingerprint,
        "journal_head_fingerprint": item.journal_head_fingerprint,
        "evidence_set_fingerprint": item.evidence_set_fingerprint,
        "semantic_profile_fingerprint": item.semantic_profile_fingerprint,
        "artifact_ref": item.receipt.logical_ref,
        "artifact_document_fingerprint": item.fingerprint,
        "artifact_fingerprint": item.receipt.fingerprint,
    }


def _hk_v1_proposal_fail(code: str) -> Never:
    raise ValueError(code)


class ProposalEventRegister(Protocol):
    """Exact no-effect Management Register command used by proposal preparation."""

    def record_event(self, command: RegisterEventCommand) -> V1CommandResult:
        """Commit one event through the generic command protocol."""
        ...


class ProposalPreparationService:
    """Validate, freeze, store, and read back immutable local proposal packages."""

    def __init__(self, contracts_root: Path) -> None:
        """Load the closed repository schema registry and an empty local store."""
        self._schemas = SchemaRegistry.from_contracts_root(contracts_root)
        self._packages: dict[str, ProposalPackage] = {}

    def prepare(
        self,
        contents_by_role: Mapping[str, bytes],
        inputs: ProposalPackageInput,
        traceability_shards_by_path: Mapping[str, bytes],
    ) -> ProposalPackage:
        """Commit a schema-valid proposal root only after every member is frozen."""
        package = freeze_proposal_package(contents_by_role, inputs, traceability_shards_by_path)
        value = parse_json_bytes(package.manifest_bytes, max_bytes=1_000_000)
        self._schemas.validate(
            value,
            _PROPOSAL_SCHEMA,
        )
        existing = self._packages.get(package.package_id)
        if existing is not None and existing != package:
            raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "package collision")
        self._packages[package.package_id] = package
        if self.read(package.package_id) != package:
            raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "read-back")
        return package

    def read(self, package_id: str) -> ProposalPackage:
        """Read back one exact immutable proposal package."""
        try:
            return self._packages[package_id]
        except KeyError as error:
            raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN) from error


class VaultProposalPreparationService:
    """Persist complete proposal members and expose only a verified manifest receipt."""

    def __init__(
        self,
        contracts_root: Path,
        primary_vault: ImmutableVault,
        retention: RetentionProfile,
    ) -> None:
        """Bind the effect-free builder to the exact Primary Vault boundary."""
        if primary_vault.vault_name is not VaultName.PRIMARY:
            message = "proposal packages require the Primary Vault"
            raise ValueError(message)
        self._schemas = SchemaRegistry.from_contracts_root(contracts_root)
        self._vault = primary_vault
        self._retention = retention

    def prepare(
        self,
        contents_by_role: Mapping[str, bytes],
        inputs: ProposalPackageInput,
        traceability_shards_by_path: Mapping[str, bytes],
    ) -> StoredProposalPackage:
        """Write members first, commit the root last, then verify every exact version."""
        package = freeze_proposal_package(contents_by_role, inputs, traceability_shards_by_path)
        self._validate_manifest(package.manifest_bytes)
        members: list[ProposalMemberReceipt] = []
        traceability_shards: tuple[TraceabilityShardReceipt, ...] = ()
        for artifact in package.artifacts:
            if artifact.role == "RECORD_TRACEABILITY":
                traceability_shards = tuple(
                    TraceabilityShardReceipt(
                        path,
                        self._vault.conditional_create(
                            self._traceability_shard_key(package.package_id, path),
                            traceability_shards_by_path[path],
                            self._retention,
                        ).reference,
                    )
                    for path in sorted(traceability_shards_by_path)
                )
            members.append(
                ProposalMemberReceipt(
                    artifact.role,
                    artifact.path,
                    self._vault.conditional_create(
                        self._member_key(package.package_id, artifact.path),
                        artifact.content,
                        self._retention,
                    ).reference,
                )
            )
        frozen_members = tuple(members)
        manifest_reference = self._vault.conditional_create(
            self._manifest_key(package.package_id),
            package.manifest_bytes,
            self._retention,
        ).reference
        provisional = StoredProposalPackage(
            package.package_id,
            package.fingerprint,
            package.promotion_manifest_id,
            package.promotion_manifest_fingerprint,
            frozen_members,
            traceability_shards,
            manifest_reference,
            "",
        )
        receipt = StoredProposalPackage(
            provisional.package_id,
            provisional.package_fingerprint,
            provisional.promotion_manifest_id,
            provisional.promotion_manifest_fingerprint,
            provisional.members,
            provisional.traceability_shards,
            provisional.manifest_reference,
            proposal_receipt_fingerprint(provisional),
        )
        if self.read(receipt) != package:
            raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "proposal read-back")
        return receipt

    def read(self, receipt: StoredProposalPackage) -> ProposalPackage:
        """Rebuild one package only from its exact portable vault receipt."""
        package = read_stored_proposal_package(self._vault, receipt)
        self._validate_manifest(package.manifest_bytes)
        return package

    def _validate_manifest(self, content: bytes) -> dict[str, JsonValue]:
        value = parse_json_bytes(content, max_bytes=1_000_000)
        self._schemas.validate(value, _PROPOSAL_SCHEMA)
        if not isinstance(value, dict):
            raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "proposal root")
        return value

    @staticmethod
    def _member_key(package_id: str, member_path: str) -> str:
        return f"proposal-packages/{package_id}/members/{member_path}"

    @staticmethod
    def _manifest_key(package_id: str) -> str:
        return f"proposal-packages/{package_id}/proposal-manifest.json"

    @staticmethod
    def _traceability_shard_key(package_id: str, path: str) -> str:
        return f"proposal-packages/{package_id}/traceability/{path}"


class ProposalRegistrationService:
    """Register only a completely re-read stored proposal as `REVIEW_READY`."""

    def __init__(
        self,
        packages: VaultProposalPreparationService,
        register: ProposalEventRegister,
    ) -> None:
        """Bind exact immutable package reads to the no-effect command boundary."""
        self._packages = packages
        self._register = register

    def register(
        self,
        receipt: StoredProposalPackage,
        *,
        command_id: str,
        expires_at: str,
    ) -> V1CommandResult:
        """Reverify every package byte before recording its portable receipt."""
        package = self._packages.read(receipt)
        if package.fingerprint != receipt.package_fingerprint:
            raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "proposal registration")
        promotion_member = next(
            artifact for artifact in package.artifacts if artifact.role == "PROMOTION_MANIFEST"
        )
        try:
            snapshot = promotion_approval_snapshot_from_bytes(
                promotion_member.content,
                expected_manifest_id=receipt.promotion_manifest_id,
                expected_fingerprint=receipt.promotion_manifest_fingerprint,
            )
        except PromotionError as error:
            raise CorpusError(
                CorpusErrorCode.FINGERPRINT_MISMATCH, "executable promotion manifest"
            ) from error
        if (
            snapshot.expected_base_serving_state_id != package.base_serving_state_id
            or snapshot.candidate_serving_state_id != package.candidate_serving_state_id
        ):
            raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "proposal serving states")
        event_bytes = canonicalize(checked_json_value(proposal_receipt_document(receipt)))
        if _fingerprint(event_bytes) != receipt.receipt_fingerprint:
            raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "proposal receipt")
        command_bytes = canonicalize(
            checked_json_value(
                {
                    "action": "REGISTER_REVIEW_READY_PROPOSAL",
                    "proposal_package_id": receipt.package_id,
                    "receipt_fingerprint": receipt.receipt_fingerprint,
                }
            )
        )
        result = self._register.record_event(
            RegisterEventCommand(
                owning_application="CONTROL_PLANE",
                command_id=command_id,
                command_bytes=command_bytes,
                target_id=receipt.package_id,
                expected_version=None,
                expected_absent=True,
                expires_at=expires_at,
                winner_key=f"review-ready:{receipt.package_id}",
                event_id=f"evt_{sha256(event_bytes).hexdigest()[:48]}",
                event_type="PROPOSAL_REVIEW_READY",
                event_bytes=event_bytes,
            )
        )
        if result.result_code != "APPLIED" or result.authoritative_version != 1:
            raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, result.result_code)
        return result
