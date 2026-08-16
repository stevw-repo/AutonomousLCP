"""Two-phase local M4 acquisition orchestration without external source access."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from asklegal_evidence_vault import (
    ArtifactClass,
    ArtifactDescriptor,
    EvidenceManifest,
    EvidencePackageReceipt,
    ExactObjectReference,
    LocalImmutableVault,
    ManifestLastPackageWriter,
    RetentionProfile,
)
from asklegal_management_register_ports import (
    AcquisitionObservationRecord,
    AcquisitionRegisterStore,
)
from asklegal_source_connectors import (
    AcquisitionArtifact,
    AcquisitionConsequence,
    ConnectorRequest,
    ObservationDisposition,
    ScraperResult,
    ScraperResultCode,
    SyntheticConnector,
    SyntheticPage,
    SyntheticResponse,
    WatcherResult,
    WatcherResultCode,
)


@dataclass(frozen=True, slots=True)
class PendingObservation:
    """Primary-committed observation awaiting independently verified recovery."""

    request: ConnectorRequest
    watcher: WatcherResult
    scraper: ScraperResult | None
    disposition: ObservationDisposition
    consequence: AcquisitionConsequence
    package_id: str
    snapshot_id: str
    issue_id: str
    input_fingerprint: str
    manifest: EvidenceManifest
    primary_manifest: ExactObjectReference
    writer: ManifestLastPackageWriter


class AcquisitionService:
    """M4 application service with no model, embedding, or promotion capability."""

    def __init__(
        self,
        connector: SyntheticConnector,
        primary: LocalImmutableVault,
        register: AcquisitionRegisterStore,
        retention: RetentionProfile,
    ) -> None:
        """Bind the worker only to synthetic source, primary vault, and register ports."""
        if type(connector) is not SyntheticConnector:
            raise TypeError("connector must be an exact SyntheticConnector")
        if type(primary) is not LocalImmutableVault:
            raise TypeError("primary must be an exact LocalImmutableVault")
        if type(retention) is not RetentionProfile:
            raise TypeError("retention must be an exact RetentionProfile")
        self.connector = connector
        self.primary = primary
        self.register = register
        self.retention = retention

    def prepare(
        self,
        request: ConnectorRequest,
        watcher_responses: tuple[SyntheticResponse, ...],
        scraper_attempts: tuple[tuple[SyntheticPage, ...], ...] = (),
    ) -> PendingObservation:
        """Observe, optionally capture, and write the complete primary manifest last."""
        watcher = self.connector.watch(request, watcher_responses)
        scraper: ScraperResult | None = None
        if watcher.code is WatcherResultCode.POSSIBLE_CHANGE:
            if not scraper_attempts:
                raise ValueError("POSSIBLE_CHANGE requires a bounded full-capture attempt")
            scraper = self.connector.scrape(request, scraper_attempts)
        disposition, consequence = _classify(watcher, scraper)
        fingerprint = _input_fingerprint(request, watcher_responses, scraper_attempts)
        package_id = _issued_id("pkg", f"{request.observation_id}:{fingerprint}")
        snapshot_id = (
            _issued_id("snp", request.observation_id)
            if disposition is ObservationDisposition.SNAPSHOT_PRESERVED
            else ""
        )
        issue_id = _issue_id(disposition, request.observation_id)
        artifacts = list(watcher.artifacts)
        if scraper is not None:
            artifacts.extend(scraper.artifacts)
        writer = ManifestLastPackageWriter(self.primary)
        for index, artifact in enumerate(artifacts, start=1):
            descriptor = _descriptor(request, artifact, index, self.retention)
            writer.stage_content(descriptor, artifact.response.body)
        manifest, primary_manifest = writer.commit_manifest(
            package_kind=(
                "source-snapshot"
                if disposition is ObservationDisposition.SNAPSHOT_PRESERVED
                else "acquisition-attempt"
            ),
            package_id=package_id,
            observation_id=request.observation_id,
            retention=self.retention,
        )
        return PendingObservation(
            request,
            watcher,
            scraper,
            disposition,
            consequence,
            package_id,
            snapshot_id,
            issue_id,
            fingerprint,
            manifest,
            primary_manifest,
            writer,
        )

    def record_after_recovery(
        self,
        pending: PendingObservation,
        evidence: EvidencePackageReceipt,
    ) -> AcquisitionObservationRecord:
        """Record an outcome only after exact primary and recovery manifests verify."""
        if type(pending) is not PendingObservation:
            raise TypeError("pending must be an exact PendingObservation")
        if type(evidence) is not EvidencePackageReceipt:
            raise TypeError("evidence must be an exact EvidencePackageReceipt")
        if evidence.manifest != pending.manifest:
            raise ValueError("recovery receipt does not bind the pending manifest")
        if evidence.primary_manifest != pending.primary_manifest:
            raise ValueError("recovery receipt does not bind the exact primary version")
        record = AcquisitionObservationRecord(
            observation_id=pending.request.observation_id,
            input_fingerprint=pending.input_fingerprint,
            source_id=pending.request.source_id,
            endpoint_id=pending.request.endpoint_id,
            observation_cutoff=pending.request.observation_cutoff,
            watcher_result=pending.watcher.code.value,
            scraper_result=None if pending.scraper is None else pending.scraper.code.value,
            disposition=pending.disposition.value,
            consequence=pending.consequence.value,
            evidence_package_id=pending.package_id,
            primary_manifest_version=evidence.primary_manifest.version_id,
            recovery_manifest_version=evidence.recovery_manifest.version_id,
            manifest_fingerprint=evidence.primary_manifest.fingerprint,
            source_snapshot_id=pending.snapshot_id,
            issue_id=pending.issue_id,
        )
        return self.register.record_observation(record)


def _classify(
    watcher: WatcherResult,
    scraper: ScraperResult | None,
) -> tuple[ObservationDisposition, AcquisitionConsequence]:
    if watcher.code is WatcherResultCode.SUPPORTED_NO_CHANGE:
        return ObservationDisposition.COMPLETE_NO_CHANGE, AcquisitionConsequence.NONE
    if watcher.code is WatcherResultCode.SOURCE_CONTRACT_CHANGED:
        return ObservationDisposition.SOURCE_CONTRACT_REVIEW, AcquisitionConsequence.NONE
    if watcher.code in {
        WatcherResultCode.SOURCE_UNAVAILABLE,
        WatcherResultCode.INCOMPLETE_OBSERVATION,
    }:
        return ObservationDisposition.COVERAGE_GAP, AcquisitionConsequence.NONE
    if watcher.code is WatcherResultCode.UNSAFE_RESPONSE:
        return ObservationDisposition.QUARANTINE, AcquisitionConsequence.NONE
    if scraper is None:
        raise ValueError("POSSIBLE_CHANGE requires one explicit Scraper result")
    if scraper.code is ScraperResultCode.SNAPSHOT_PRESERVED:
        return (
            ObservationDisposition.SNAPSHOT_PRESERVED,
            AcquisitionConsequence.LEGAL_PROCESSING_ELIGIBLE,
        )
    if scraper.code is ScraperResultCode.SUPPORTED_NO_CHANGE_AFTER_CAPTURE:
        return ObservationDisposition.COMPLETE_NO_CHANGE, AcquisitionConsequence.NONE
    if scraper.code is ScraperResultCode.SOURCE_CONTRACT_CHANGED:
        return ObservationDisposition.SOURCE_CONTRACT_REVIEW, AcquisitionConsequence.NONE
    if scraper.code is ScraperResultCode.UNSAFE_RESPONSE:
        return ObservationDisposition.QUARANTINE, AcquisitionConsequence.NONE
    return ObservationDisposition.COVERAGE_GAP, AcquisitionConsequence.NONE


def _descriptor(
    request: ConnectorRequest,
    artifact: AcquisitionArtifact,
    index: int,
    retention: RetentionProfile,
) -> ArtifactDescriptor:
    response = artifact.response
    artifact_class = (
        ArtifactClass.HOSTILE_ISOLATED
        if not artifact.classification.admitted
        else ArtifactClass.SOURCE_CONTENT
    )
    seed = f"{request.observation_id}:{artifact.role}:{index}"
    return ArtifactDescriptor(
        artifact_id=_issued_id("art", seed),
        artifact_version_id=_issued_id("evi", f"{seed}:{sha256(response.body).hexdigest()}"),
        artifact_class=artifact_class,
        source_id=request.source_id,
        observation_id=request.observation_id,
        observation_cutoff=request.observation_cutoff,
        acquired_at=request.observation_cutoff,
        acquisition_method=request.method.value,
        source_locator=f"https://{response.host}{response.path}",
        declared_media_type=response.media_type,
        detected_media_type=response.media_type,
        content_encoding=response.content_encoding,
        character_encoding=response.character_encoding,
        transport_metadata=(
            ("declared-length", str(response.declared_length)),
            ("status-code", str(response.status_code)),
        ),
        retention=retention,
    )


def _issue_id(disposition: ObservationDisposition, observation_id: str) -> str:
    prefixes = {
        ObservationDisposition.COVERAGE_GAP: "cgp",
        ObservationDisposition.QUARANTINE: "qua",
        ObservationDisposition.SOURCE_CONTRACT_REVIEW: "scr",
    }
    prefix = prefixes.get(disposition)
    return "" if prefix is None else _issued_id(prefix, observation_id)


def _issued_id(prefix: str, seed: str) -> str:
    return f"{prefix}_{sha256(seed.encode('utf-8')).hexdigest()[:48]}"


def _input_fingerprint(
    request: ConnectorRequest,
    watcher_responses: tuple[SyntheticResponse, ...],
    scraper_attempts: tuple[tuple[SyntheticPage, ...], ...],
) -> str:
    digest = sha256()
    for value in (
        request.pipeline_run_id,
        request.work_item_id,
        request.observation_id,
        request.observation_cutoff,
        request.source_id,
        request.source_version,
        request.endpoint_id,
        request.endpoint_version,
        request.rulebook_id,
        request.rulebook_version,
        request.method.value,
        request.previous_observation_id,
        request.previous_snapshot_id,
        request.prior_signal,
    ):
        digest.update(value.encode("utf-8"))
        digest.update(b"\x00")
    for response in watcher_responses:
        digest.update(response.body)
        digest.update(response.signal.encode("utf-8"))
    for attempt in scraper_attempts:
        for page in attempt:
            digest.update(page.response.body)
            digest.update(page.cursor.encode("utf-8"))
            digest.update(page.inventory_generation.encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"
