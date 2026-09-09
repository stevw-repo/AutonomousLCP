"""M6 Approval-bound replacement-target promotion orchestration."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from hashlib import sha256
from threading import RLock
from typing import Protocol

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import EffectType, ImmutableReference
from asklegal_management_register import ServingStateVerificationError
from asklegal_management_register_ports import (
    ApprovalConsumption,
    ApprovalRegisterStore,
    ManifestSnapshot,
)
from asklegal_promotion import (
    BackupPort,
    BackupVerification,
    CoveragePort,
    EmbeddingPort,
    EmbeddingRequest,
    EmbeddingRequestInput,
    EmbeddingTokenCounter,
    HKV1TargetComposition,
    OutcomeUnknown,
    ProfileError,
    PromotionError,
    PromotionErrorCode,
    PromotionExecutionResult,
    PromotionManifest,
    RoutingPort,
    ServingCapabilityProfile,
    ServingStateCandidate,
    ServingStatePort,
    ServingTargetPort,
    TargetDefinition,
    TargetRecord,
    embedding_request,
    pinecone_index_name,
    target_state_fingerprint,
    validate_serving_capability_profile_authority,
    verify_embedding_profile,
    verify_generic_promotion_manifest,
    verify_hk_v1_approved_package,
    verify_promotion_manifest,
)

from asklegal_promotion_worker.real_effects import V1RealEffectActivation


class HKV1ApprovedPackageSource(Protocol):
    """Reread the exact proposal/readiness bytes named by one Approval."""

    def approved_package(self, approval_id: str) -> tuple[bytes, bytes]:
        """Return retained Task 7 proposal and Task 8 readiness bytes."""
        ...


class HKV1LocalApprovalStore(ApprovalRegisterStore, HKV1ApprovedPackageSource, Protocol):
    """One shared local store for Approval state and its frozen package bytes."""

    def get(self, approval_id: str) -> object:
        """Read one retained Approval projection before composing real effects."""
        ...


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def _uses_v1_serving_state(manifest: PromotionManifest) -> bool:
    """V1 has no Ask.Legal routing authority in its immutable action list."""
    effects = tuple(action.effect_type for action in manifest.actions)
    return EffectType.ROUTING_ACTIVATION not in effects


def _execution_input_fingerprint(
    manifest: PromotionManifest,
    approval_id: str,
    execution_lineage_id: str,
    context: PromotionExecutionContext,
) -> str:
    document = checked_json_value(
        {
            "approval_id": approval_id,
            "base_serving_state_id": context.base_serving_state_id,
            "execution_lineage_id": execution_lineage_id,
            "manifest_fingerprint": manifest.fingerprint,
            "manifest_id": manifest.manifest_id,
            "predicates": [list(item) for item in context.predicates],
            "time": context.at,
        }
    )
    return f"sha256:{sha256(canonicalize(document)).hexdigest()}"


def _hk_v1_execution_input_fingerprint(  # noqa: PLR0913, PLR0917 - exact input set.
    manifest: PromotionManifest,
    proposal_content: bytes,
    composition: HKV1TargetComposition,
    approval_id: str,
    execution_lineage_id: str,
    context: PromotionExecutionContext,
) -> str:
    document = checked_json_value(
        {
            "base": _execution_input_fingerprint(
                manifest, approval_id, execution_lineage_id, context
            ),
            "members": [
                {
                    "family": item.material_family,
                    "record_id": item.record_id,
                    "scope_id": item.scope_id,
                }
                for item in composition.members
            ],
            "proposal_bytes_fingerprint": f"sha256:{sha256(proposal_content).hexdigest()}",
            "proposal_fingerprint": composition.proposal_fingerprint,
            "zero_record_scope_ids": list(composition.zero_record_scope_ids),
        }
    )
    return f"sha256:{sha256(canonicalize(document)).hexdigest()}"


@dataclass(frozen=True, slots=True)
class PromotionDependencies:
    """All injected M6 state and effect boundaries."""

    approvals: ApprovalRegisterStore
    embeddings: EmbeddingPort
    token_counter: EmbeddingTokenCounter
    targets: ServingTargetPort
    backups: BackupPort
    routing: RoutingPort
    coverage: CoveragePort
    serving_states: ServingStatePort | None = None
    serving_profile: ServingCapabilityProfile | None = None
    backup_profile_ref: ImmutableReference | None = None
    real_effect_authority: object | None = None
    approved_package_source: HKV1ApprovedPackageSource | None = None


@dataclass(frozen=True, slots=True)
class PromotionExecutionContext:
    """Current execution facts that must match the frozen manifest."""

    base_serving_state_id: str
    predicates: tuple[tuple[str, str, str], ...]
    at: str


class PromotionService:
    """Execute only one exact approved manifest through local injected ports."""

    def __init__(self, dependencies: PromotionDependencies) -> None:
        """Create an orchestrator from explicit injected boundaries."""
        self._dependencies = dependencies
        self._lock = RLock()
        self._running: set[str] = set()
        self._results: dict[str, PromotionExecutionResult] = {}
        self._result_input_fingerprints: dict[str, str] = {}

    def execute(
        self,
        manifest: PromotionManifest,
        approval_id: str,
        execution_lineage_id: str,
        context: PromotionExecutionContext,
        *,
        execution_input_fingerprint: str | None = None,
    ) -> PromotionExecutionResult:
        """Build, verify, back up, cut over, and verify one replacement state."""
        if _uses_v1_serving_state(manifest):
            verify_promotion_manifest(manifest)
        else:
            verify_generic_promotion_manifest(manifest)
        input_fingerprint = execution_input_fingerprint or _execution_input_fingerprint(
            manifest,
            approval_id,
            execution_lineage_id,
            context,
        )
        existing = self._results.get(execution_lineage_id)
        if existing is not None:
            if (
                existing.manifest_id != manifest.manifest_id
                or self._result_input_fingerprints.get(execution_lineage_id) != input_fingerprint
            ):
                raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "lineage reuse")
            return existing
        with self._lock:
            if manifest.manifest_id in self._running:
                raise PromotionError(PromotionErrorCode.OVERLAPPING_EXECUTION)
            self._running.add(manifest.manifest_id)
        try:
            result = self._execute(
                manifest,
                approval_id,
                execution_lineage_id,
                context,
            )
            self._result_input_fingerprints[execution_lineage_id] = input_fingerprint
            return result
        finally:
            with self._lock:
                self._running.discard(manifest.manifest_id)

    def execute_hk_v1(
        self,
        manifest: PromotionManifest,
        approval_id: str,
        execution_lineage_id: str,
        context: PromotionExecutionContext,
    ) -> tuple[HKV1TargetComposition, PromotionExecutionResult]:
        """Execute only a manifest explicitly bound to the exact Task 7 proposal."""
        verify_promotion_manifest(manifest)
        source = self._dependencies.approved_package_source
        if source is None:
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "approved package source")
        proposal_content, readiness_content = source.approved_package(approval_id)
        try:
            composition = verify_hk_v1_approved_package(
                proposal_content,
                readiness_content,
                tuple(item.record_id for item in manifest.desired_state.records),
            )
        except PromotionError as error:
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "approved package") from error
        if any(
            member.record_id != record.record_id or member.scope_id != record.scope_id
            for member, record in zip(
                composition.members,
                manifest.desired_state.records,
                strict=True,
            )
        ):
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "approved record scope")
        binding = (
            "HK_V1_TWO_FAMILY_PROPOSAL",
            "1.0.0",
            composition.proposal_fingerprint,
        )
        if (
            binding not in manifest.validity_predicates
            or (
                "HK_V1_REVIEW_READINESS",
                "1.0.0",
                composition.review_readiness_fingerprint,
            )
            not in manifest.validity_predicates
            or composition.embedding_profile_fingerprint
            != manifest.embedding_profile.profile_fingerprint
        ):
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "proposal binding")
        target_name = pinecone_index_name(
            manifest.environment,
            manifest.jurisdiction,
            manifest.freeze_date,
            manifest.candidate_serving_state_fingerprint,
            manifest.project_id,
        )
        serving = self._dependencies.serving_profile
        if target_name != composition.target_name:
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "approved target")
        if serving is not None and (
            composition.serving_profile_fingerprint != serving.fingerprint
            or composition.target_namespace != serving.namespace
            or composition.backup_profile_fingerprint != serving.backup_profile_ref.fingerprint
        ):
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "approved serving profile")
        task8_fingerprint = _hk_v1_execution_input_fingerprint(
            manifest,
            proposal_content,
            composition,
            approval_id,
            execution_lineage_id,
            context,
        )
        return composition, self.execute(
            manifest,
            approval_id,
            execution_lineage_id,
            context,
            execution_input_fingerprint=task8_fingerprint,
        )

    def _execute(  # noqa: C901 - exact pre-effect gates stay visible in one sequence.
        self,
        manifest: PromotionManifest,
        approval_id: str,
        execution_lineage_id: str,
        context: PromotionExecutionContext,
    ) -> PromotionExecutionResult:
        if context.base_serving_state_id != manifest.base_serving_state_id:
            raise PromotionError(PromotionErrorCode.BASE_STATE_DRIFT)
        profile = manifest.embedding_profile
        serving_profile = self._admitted_serving_profile(manifest)
        requests, estimated_cost = self._prepare_requests(
            manifest, execution_lineage_id, context.at
        )
        self._validate_real_effect_facts(
            manifest,
            serving_profile,
            approval_id,
            execution_lineage_id,
        )
        snapshot = ManifestSnapshot(
            manifest.manifest_id,
            manifest.fingerprint,
            manifest.base_serving_state_id,
            manifest.valid_from,
            manifest.valid_until,
            manifest.validity_predicates,
        )
        consumed_approval = self._dependencies.approvals.consume(
            approval_id,
            execution_lineage_id,
            snapshot,
            ApprovalConsumption(
                context.base_serving_state_id,
                context.predicates,
                context.at,
            ),
        )
        if serving_profile is not None:
            activation = self._dependencies.real_effect_authority
            if type(activation) is not V1RealEffectActivation:
                raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "real effect activation")
            activation.activate(consumed_approval)
        self._dependencies.coverage.load_for_activation(
            manifest.candidate_serving_state_id,
            manifest.coverage_status.fingerprint,
        )
        target_name = pinecone_index_name(
            manifest.environment,
            manifest.jurisdiction,
            manifest.freeze_date,
            manifest.candidate_serving_state_fingerprint,
            manifest.project_id,
        )
        target_definition = TargetDefinition(
            target_name,
            target_state_fingerprint(
                target_name,
                profile.dimensions,
                profile.metric,
                "default" if serving_profile is None else serving_profile.namespace,
            ),
            profile.dimensions,
            profile.metric,
            "default" if serving_profile is None else serving_profile.namespace,
        )
        self._dependencies.targets.create(target_definition)
        if self._dependencies.targets.describe(target_name) != target_definition:
            raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "target definition")
        receipts: list[str] = []
        expected_target_records: list[TargetRecord] = []
        for start in range(0, len(requests), manifest.batch_size):
            batch_requests = requests[start : start + manifest.batch_size]
            batch_records: list[TargetRecord] = []
            for request, desired in zip(
                batch_requests,
                manifest.desired_state.records[start : start + manifest.batch_size],
                strict=True,
            ):
                embedded = self._dependencies.embeddings.embed(profile, request)
                if (
                    type(embedded.receipt.input_tokens) is not int
                    or embedded.receipt.input_tokens != request.token_count
                ):
                    raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "token accounting")
                if (
                    embedded.receipt.dimensions != profile.dimensions
                    or len(embedded.values) != profile.dimensions
                    or any(not math.isfinite(value) for value in embedded.values)
                ):
                    raise PromotionError(PromotionErrorCode.VECTOR_INVALID)
                receipts.append(embedded.receipt.receipt_id)
                target_record = TargetRecord(
                    desired.record_id,
                    desired.content_fingerprint,
                    embedded.values,
                    desired.record.text,
                    desired.record.country,
                    desired.record.jurisdiction,
                    desired.record.material_type,
                    desired.record.source,
                    desired.record.authority_note,
                )
                batch_records.append(target_record)
                expected_target_records.append(target_record)
            exact_batch = tuple(batch_records)
            try:
                self._dependencies.targets.upsert_batch(target_name, exact_batch)
            except OutcomeUnknown:
                actual = {
                    item.record_id: item
                    for item in self._dependencies.targets.enumerate(target_name)
                }
                if any(actual.get(item.record_id) != item for item in exact_batch):
                    raise PromotionError(PromotionErrorCode.LOST_ACK_UNRECONCILED) from None
        self._verify_inventory(manifest, target_name, tuple(expected_target_records))
        self._dependencies.targets.verify_queries(
            target_name,
            tuple(item.record_id for item in expected_target_records),
        )
        backup_verification = self._verified_backup(manifest, target_name)
        routing_receipt, rollback_receipt, state = self._activate_and_verify(
            manifest, approval_id, execution_lineage_id, target_name
        )
        result = PromotionExecutionResult(
            execution_lineage_id,
            manifest.manifest_id,
            target_name,
            state,
            tuple(receipts),
            backup_verification.native_backup_receipt_ref,
            backup_verification.recovery_receipt_ref,
            routing_receipt,
            rollback_receipt,
            estimated_cost,
        )
        self._results[execution_lineage_id] = result
        return result

    def _v1_serving_states(self) -> ServingStatePort:
        """Return the required V1 Register State boundary, never a routing fallback."""
        if self._dependencies.serving_states is None:
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "V1 Serving State port")
        return self._dependencies.serving_states

    def _activate_and_verify(
        self,
        manifest: PromotionManifest,
        approval_id: str,
        execution_lineage_id: str,
        target_name: str,
    ) -> tuple[str, str, str]:
        """Use only Serving State for V1; retain generic routing for legacy manifests."""
        if not _uses_v1_serving_state(manifest):
            receipt = self._dependencies.routing.activate(
                manifest.base_serving_state_id, manifest.candidate_serving_state_id
            )
            try:
                self._dependencies.routing.verify_post_cutover(manifest.candidate_serving_state_id)
            except PromotionError as error:
                rollback = self._dependencies.routing.rollback(
                    manifest.candidate_serving_state_id, manifest.rollback_serving_state_id
                )
                if error.code is not PromotionErrorCode.POST_CUTOVER_FAILED:
                    raise
                return receipt, rollback, "EXECUTION_ROLLED_BACK"
            return receipt, "", "EXECUTION_SUCCEEDED"
        candidate = ServingStateCandidate(
            manifest.candidate_serving_state_id,
            manifest.candidate_serving_state_fingerprint,
            manifest.rollback_serving_state_id,
            target_name,
            manifest.desired_state.inventory_fingerprint,
            manifest.coverage_status.fingerprint,
            manifest.embedding_profile.profile_id,
            manifest.embedding_profile.profile_fingerprint,
            approval_id,
            execution_lineage_id,
        )
        state = self._v1_serving_states()
        activation = self._dependencies.real_effect_authority
        if type(activation) is V1RealEffectActivation:
            activation.require_current()
        receipt = state.activate(manifest.base_serving_state_id, candidate).receipt_id
        try:
            state.verify(manifest.candidate_serving_state_id)
        except (PromotionError, ServingStateVerificationError) as error:
            rollback = state.rollback(candidate, receipt).receipt_id
            if (
                isinstance(error, PromotionError)
                and error.code is not PromotionErrorCode.POST_CUTOVER_FAILED
            ):
                raise
            return receipt, rollback, "EXECUTION_ROLLED_BACK"
        return receipt, "", "EXECUTION_SUCCEEDED"

    def _verified_backup(self, manifest: PromotionManifest, target_name: str) -> BackupVerification:
        """Require independent exact native and recovery verification."""
        result = self._dependencies.backups.create_and_verify(
            target_name,
            manifest.desired_state.inventory_fingerprint,
            self._dependencies.backup_profile_ref,
        )
        if not result.native_verified or not result.recovery_verified:
            raise PromotionError(PromotionErrorCode.BACKUP_FAILED, "verification")
        return result

    def _prepare_requests(
        self, manifest: PromotionManifest, execution_lineage_id: str, at: str
    ) -> tuple[tuple[EmbeddingRequest, ...], int]:
        """Validate the profile and freeze all exact provider requests."""
        profile = manifest.embedding_profile
        verify_embedding_profile(profile)
        if (
            profile.provider not in {"LOCAL_FAKE", "AZURE_OPENAI"}
            or manifest.environment not in profile.allowed_environments
            or profile.stateful_features
            or profile.expires_at <= at
            or profile.dimensions < 1
        ):
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID)
        requests = tuple(
            embedding_request(
                EmbeddingRequestInput(
                    item.record_id,
                    item.content_fingerprint,
                    item.record.text,
                    _stable_id("art", execution_lineage_id, str(index // manifest.batch_size)),
                    index % manifest.batch_size,
                ),
                profile,
                self._dependencies.token_counter,
            )
            for index, item in enumerate(manifest.desired_state.records)
        )
        estimated_cost = sum(request.token_count for request in requests)
        if estimated_cost > profile.cost_limit_microunits:
            raise PromotionError(PromotionErrorCode.COST_LIMIT_EXCEEDED)
        return requests, estimated_cost

    def _admitted_serving_profile(
        self, manifest: PromotionManifest
    ) -> ServingCapabilityProfile | None:
        """Require loader authority for Azure while preserving local M6 fakes."""
        profile = manifest.embedding_profile
        if profile.provider == "LOCAL_FAKE":
            return None
        serving = self._dependencies.serving_profile
        if serving is None:
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "serving profile missing")
        try:
            validate_serving_capability_profile_authority(serving)
            serving.validate()
        except (ProfileError, TypeError, ValueError) as error:
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "serving profile") from error
        if (
            serving.embedding != profile
            or serving.environment != manifest.environment
            or serving.batch_size != manifest.batch_size
            or serving.pinecone_project_id != manifest.project_id
        ):
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "serving profile drift")
        return serving

    def _validate_real_effect_facts(
        self,
        manifest: PromotionManifest,
        serving: ServingCapabilityProfile | None,
        approval_id: str,
        execution_lineage_id: str,
    ) -> None:
        """Reread every real adapter, target, backup, and authority binding pre-consume."""
        if serving is None:
            return
        target_name = pinecone_index_name(
            manifest.environment,
            manifest.jurisdiction,
            manifest.freeze_date,
            manifest.candidate_serving_state_fingerprint,
            manifest.project_id,
        )
        authority = self._dependencies.real_effect_authority
        if (
            getattr(self._dependencies.embeddings, "serving_profile_fingerprint", None)
            != serving.fingerprint
            or getattr(self._dependencies.embeddings, "deployment_name", None)
            != serving.embedding.deployment_name
            or getattr(self._dependencies.embeddings, "api_contract", None)
            != serving.embedding.api_contract
            or getattr(self._dependencies.embeddings, "timeout_seconds", None)
            != serving.provider_timeout_seconds
            or getattr(self._dependencies.targets, "target_name", None) != target_name
            or getattr(self._dependencies.targets, "namespace", None) != serving.namespace
            or getattr(self._dependencies.targets, "project_id", None)
            != serving.pinecone_project_id
            or getattr(self._dependencies.targets, "page_size", None) != serving.readback_page_size
            or getattr(self._dependencies.targets, "timeout_seconds", None)
            != serving.target_timeout_seconds
            or self._dependencies.backup_profile_ref != serving.backup_profile_ref
            or getattr(self._dependencies.backups, "backup_profile_ref", None)
            != serving.backup_profile_ref
            or getattr(authority, "approval_id", None) != approval_id
            or getattr(authority, "execution_lineage_id", None) != execution_lineage_id
            or getattr(authority, "serving_profile_fingerprint", None) != serving.fingerprint
        ):
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "real effect facts drift")

    def _verify_inventory(
        self,
        manifest: PromotionManifest,
        target_name: str,
        expected_records: tuple[TargetRecord, ...],
    ) -> None:
        actual = self._dependencies.targets.enumerate(target_name)
        expected = manifest.desired_state.records
        actual_ids = {item.record_id for item in actual}
        expected_ids = {item.record_id for item in expected}
        if actual_ids - expected_ids:
            raise PromotionError(PromotionErrorCode.UNKNOWN_REMOTE_RECORD)
        if actual_ids != expected_ids:
            raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH)
        expected_by_id = {item.record_id: item for item in expected_records}
        if any(item != expected_by_id[item.record_id] for item in actual):
            raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH)

    def retire_exact(self, manifest: PromotionManifest, target_name: str) -> str:
        """Retire only one exact manifest-declared inactive target."""
        if _uses_v1_serving_state(manifest):
            verify_promotion_manifest(manifest)
        else:
            verify_generic_promotion_manifest(manifest)
        active_candidate_name = pinecone_index_name(
            manifest.environment,
            manifest.jurisdiction,
            manifest.freeze_date,
            manifest.candidate_serving_state_fingerprint,
            manifest.project_id,
        )
        if _uses_v1_serving_state(manifest):
            if self._dependencies.serving_states is None:
                raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "V1 Serving State port")
            active_state_id = self._dependencies.serving_states.active_state_id
        else:
            active_state_id = self._dependencies.routing.active_state_id
        if target_name not in manifest.exact_retirement_target_ids or (
            target_name == active_candidate_name
            and active_state_id == manifest.candidate_serving_state_id
        ):
            raise PromotionError(PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN)
        return self._dependencies.targets.delete_exact(target_name, target_name)


def compose_hk_v1_local_promotion_service(
    dependencies: PromotionDependencies,
    approvals: HKV1LocalApprovalStore,
) -> PromotionService:
    """Bind promotion to the same retained Approval/package store Review wrote."""
    return PromotionService(
        replace(
            dependencies,
            approvals=approvals,
            approved_package_source=approvals,
        )
    )
