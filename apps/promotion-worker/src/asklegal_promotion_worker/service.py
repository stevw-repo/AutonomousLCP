"""M6 Approval-bound replacement-target promotion orchestration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock

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
    OutcomeUnknown,
    PromotionError,
    PromotionErrorCode,
    PromotionExecutionResult,
    PromotionManifest,
    RoutingPort,
    ServingTargetPort,
    TargetDefinition,
    TargetRecord,
    embedding_request,
    pinecone_index_name,
    verify_embedding_profile,
    verify_promotion_manifest,
)


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


@dataclass(frozen=True, slots=True)
class PromotionDependencies:
    """All injected M6 state and effect boundaries."""

    approvals: ApprovalRegisterStore
    embeddings: EmbeddingPort
    targets: ServingTargetPort
    backups: BackupPort
    routing: RoutingPort
    coverage: CoveragePort


@dataclass(frozen=True, slots=True)
class PromotionExecutionContext:
    """Current execution facts that must match the frozen manifest."""

    base_serving_state_id: str
    predicates: tuple[tuple[str, str], ...]
    at: str


class PromotionService:
    """Execute only one exact approved manifest through local injected ports."""

    def __init__(self, dependencies: PromotionDependencies) -> None:
        """Create an orchestrator from explicit injected boundaries."""
        self._dependencies = dependencies
        self._lock = RLock()
        self._running: set[str] = set()
        self._results: dict[str, PromotionExecutionResult] = {}

    def execute(
        self,
        manifest: PromotionManifest,
        approval_id: str,
        execution_lineage_id: str,
        context: PromotionExecutionContext,
    ) -> PromotionExecutionResult:
        """Build, verify, back up, cut over, and verify one replacement state."""
        verify_promotion_manifest(manifest)
        if not manifest.capability_enabled:
            raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "capability disabled")
        existing = self._results.get(execution_lineage_id)
        if existing is not None:
            if existing.manifest_id != manifest.manifest_id:
                raise PromotionError(PromotionErrorCode.MANIFEST_DRIFT, "lineage reuse")
            return existing
        with self._lock:
            if manifest.manifest_id in self._running:
                raise PromotionError(PromotionErrorCode.OVERLAPPING_EXECUTION)
            self._running.add(manifest.manifest_id)
        try:
            return self._execute(
                manifest,
                approval_id,
                execution_lineage_id,
                context,
            )
        finally:
            with self._lock:
                self._running.discard(manifest.manifest_id)

    def _execute(
        self,
        manifest: PromotionManifest,
        approval_id: str,
        execution_lineage_id: str,
        context: PromotionExecutionContext,
    ) -> PromotionExecutionResult:
        if context.base_serving_state_id != manifest.base_serving_state_id:
            raise PromotionError(PromotionErrorCode.BASE_STATE_DRIFT)
        requests, estimated_cost = self._prepare_requests(
            manifest, execution_lineage_id, context.at
        )
        profile = manifest.embedding_profile
        snapshot = ManifestSnapshot(
            manifest.manifest_id,
            manifest.fingerprint,
            manifest.base_serving_state_id,
            manifest.valid_from,
            manifest.valid_until,
            manifest.validity_predicates,
        )
        self._dependencies.approvals.consume(
            approval_id,
            execution_lineage_id,
            snapshot,
            ApprovalConsumption(
                context.base_serving_state_id,
                context.predicates,
                context.at,
            ),
        )
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
            manifest.candidate_serving_state_fingerprint,
            profile.dimensions,
            profile.metric,
            "default",
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
        routing_receipt = self._dependencies.routing.activate(
            manifest.base_serving_state_id,
            manifest.candidate_serving_state_id,
        )
        rollback_receipt = ""
        state = "EXECUTION_SUCCEEDED"
        try:
            self._dependencies.routing.verify_post_cutover(manifest.candidate_serving_state_id)
        except PromotionError as error:
            rollback_receipt = self._dependencies.routing.rollback(
                manifest.candidate_serving_state_id,
                manifest.rollback_serving_state_id,
            )
            state = "EXECUTION_ROLLED_BACK"
            if error.code is not PromotionErrorCode.POST_CUTOVER_FAILED:
                raise
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

    def _verified_backup(self, manifest: PromotionManifest, target_name: str) -> BackupVerification:
        """Require independent exact native and recovery verification."""
        result = self._dependencies.backups.create_and_verify(
            target_name,
            manifest.desired_state.inventory_fingerprint,
        )
        if not result.native_verified or not result.recovery_verified:
            raise PromotionError(PromotionErrorCode.BACKUP_FAILED, "verification")
        return result

    @staticmethod
    def _prepare_requests(
        manifest: PromotionManifest, execution_lineage_id: str, at: str
    ) -> tuple[tuple[EmbeddingRequest, ...], int]:
        """Validate the profile and freeze all exact provider requests."""
        profile = manifest.embedding_profile
        verify_embedding_profile(profile)
        if (
            profile.provider != "LOCAL_FAKE"
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
            )
            for index, item in enumerate(manifest.desired_state.records)
        )
        estimated_cost = sum(request.token_count for request in requests)
        if estimated_cost > profile.cost_limit_microunits:
            raise PromotionError(PromotionErrorCode.COST_LIMIT_EXCEEDED)
        return requests, estimated_cost

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
        verify_promotion_manifest(manifest)
        active_candidate_name = pinecone_index_name(
            manifest.environment,
            manifest.jurisdiction,
            manifest.freeze_date,
            manifest.candidate_serving_state_fingerprint,
            manifest.project_id,
        )
        if target_name not in manifest.exact_retirement_target_ids or (
            target_name == active_candidate_name
            and self._dependencies.routing.active_state_id == manifest.candidate_serving_state_id
        ):
            raise PromotionError(PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN)
        return self._dependencies.targets.delete_exact(target_name, target_name)
