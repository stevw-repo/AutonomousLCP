"""M6 manifest-last proposal-package preparation owned by the control plane."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

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

if TYPE_CHECKING:
    from asklegal_management_register import V1CommandResult

_PROPOSAL_SCHEMA = "schemas/promotion-domain.schema.json#/$defs/proposal_package_manifest"


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


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
