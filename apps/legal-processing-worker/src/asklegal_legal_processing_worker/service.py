"""M5 legal-processing orchestration with exact evidence and activation guards."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from asklegal_legal_desks import (
    LoadedRulebook,
    ProcessingSubject,
    RulebookError,
    RulebookErrorCode,
    RulebookLifecycle,
    RuleEngine,
    RuleExecutionResult,
)
from asklegal_management_register_ports import (
    AcquisitionObservationRecord,
    LegalProcessingRecord,
    LegalProcessingRegisterStore,
)
from asklegal_processing import (
    AdmittedSemanticDecision,
    CandidateArtifact,
    SemanticTaskGate,
    SemanticTaskRequest,
    SemanticTaskRunner,
    render_candidate,
)

if TYPE_CHECKING:
    from asklegal_evidence_vault import EvidencePackageReceipt


class LegalProcessingService:
    """Consume only M4-eligible evidence under one active exact package."""

    def __init__(
        self,
        lifecycle: RulebookLifecycle,
        register: LegalProcessingRegisterStore,
        semantic_runner: SemanticTaskRunner,
    ) -> None:
        """Bind authority, persistence, and the sole semantic runner."""
        self._engine = RuleEngine(lifecycle)
        self._register = register
        self._semantic_gate = SemanticTaskGate(semantic_runner)

    @staticmethod
    def _validate_evidence(
        acquisition: AcquisitionObservationRecord,
        receipt: EvidencePackageReceipt,
        subject: ProcessingSubject,
        package: LoadedRulebook,
    ) -> None:
        if (
            acquisition.disposition != "SNAPSHOT_PRESERVED"
            or acquisition.consequence != "LEGAL_PROCESSING_ELIGIBLE"
            or not acquisition.source_snapshot_id
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "M4 eligibility")
        if (
            receipt.manifest.package_id != acquisition.evidence_package_id
            or receipt.manifest.observation_id != acquisition.observation_id
            or receipt.primary_manifest.version_id != acquisition.primary_manifest_version
            or receipt.recovery_manifest.version_id != acquisition.recovery_manifest_version
            or receipt.primary_manifest.fingerprint != acquisition.manifest_fingerprint
        ):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "M4 evidence receipt")
        if (
            subject.observation_id != acquisition.observation_id
            or subject.source_snapshot_id != acquisition.source_snapshot_id
            or acquisition.source_id not in {source.source_id for source in package.sources}
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "processing subject")
        artifact_ids = {entry.descriptor.artifact_id for entry in receipt.manifest.entries}
        if not set(subject.evidence_refs).issubset(artifact_ids):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "unpreserved evidence")

    def process(
        self,
        acquisition: AcquisitionObservationRecord,
        receipt: EvidencePackageReceipt,
        package: LoadedRulebook,
        subject: ProcessingSubject,
        *,
        semantic_requests: tuple[SemanticTaskRequest, SemanticTaskRequest] | None = None,
        now: str,
    ) -> tuple[RuleExecutionResult, CandidateArtifact | None, LegalProcessingRecord]:
        """Produce and record one exact local M5 result."""
        self._validate_evidence(acquisition, receipt, subject, package)
        semantic: AdmittedSemanticDecision | None = None
        effective_subject = subject
        if semantic_requests is not None:
            try:
                primary_profile = next(
                    item
                    for item in package.semantic_profiles
                    if item.profile_id == semantic_requests[0].profile_id
                )
                challenge_profile = next(
                    item
                    for item in package.semantic_profiles
                    if item.profile_id == semantic_requests[1].profile_id
                )
            except StopIteration as error:
                raise RulebookError(
                    RulebookErrorCode.PACKAGE_NOT_ACTIVE,
                    "semantic profile",
                ) from error
            semantic = self._semantic_gate.decide(
                (primary_profile, challenge_profile),
                semantic_requests,
                environment=package.manifest.environment,
                now=now,
            )
            effective_subject = replace(subject, facts=(*subject.facts, *semantic.admitted_fields))
        result = self._engine.execute(package, effective_subject)
        candidate = render_candidate(result, semantic)
        record = LegalProcessingRecord(
            result.result_id,
            subject.input_fingerprint,
            acquisition.observation_id,
            acquisition.source_snapshot_id,
            package.manifest.package_id,
            package.manifest.package_fingerprint,
            result.rule_id,
            result.disposition.value if result.disposition else "BLOCK",
            result.reason_code,
            result.failure_code or "",
            result.evidence_refs,
            candidate.artifact_id if candidate else "",
            candidate.fingerprint if candidate else "",
            semantic.primary.output_fingerprint if semantic else "",
            result.next_action,
        )
        recorded = self._register.record_processing_result(record)
        return result, candidate, recorded
