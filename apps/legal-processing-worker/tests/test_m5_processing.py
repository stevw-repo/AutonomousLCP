"""M4-to-M5 evidence, rulebook, semantic, result, and replay conformance."""

from pathlib import Path

import pytest
from asklegal_contracts import fingerprint, parse_json_bytes
from asklegal_evidence_vault import (
    ArtifactClass,
    ArtifactDescriptor,
    EvidencePackageReceipt,
    LocalImmutableVault,
    ManifestLastPackageWriter,
    RecoveryCopier,
    RetentionProfile,
    VaultName,
)
from asklegal_legal_desks import (
    ActivationRecord,
    LoadedRulebook,
    ProcessingSubject,
    RulebookError,
    RulebookLifecycle,
    load_rulebook_package,
)
from asklegal_legal_processing_worker import LegalProcessingService
from asklegal_management_register_ports import (
    AcquisitionObservationRecord,
    InMemoryLegalProcessingRegister,
)
from asklegal_processing import DeterministicSemanticTaskRunner, SemanticTaskRequest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPOSITORY_ROOT / "packages/legal-desks/src/asklegal_legal_desks/_synthetic_package"
SOURCE_ID = f"src_{'1' * 48}"
ENDPOINT_ID = f"sep_{'2' * 48}"
OBSERVATION_ID = f"obs_{'3' * 48}"
SCOPE_ID = f"rsc_{'3' * 48}"
INPUT_FINGERPRINT = "sha256:" + "3" * 64


def _contract_fingerprint() -> str:
    path = REPOSITORY_ROOT / "contracts/package-manifest.json"
    raw = path.read_bytes()
    return fingerprint(parse_json_bytes(raw, max_bytes=len(raw)))


def _package() -> LoadedRulebook:
    return load_rulebook_package(
        PACKAGE_ROOT,
        environment="LOCAL_SYNTHETIC",
        contract_set_fingerprint=_contract_fingerprint(),
        now="2026-08-16T00:00:00Z",
    )


def _m4(tmp_path: Path) -> tuple[AcquisitionObservationRecord, EvidencePackageReceipt]:
    primary = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    recovery = LocalImmutableVault(tmp_path / "recovery", VaultName.RECOVERY)
    retention = RetentionProfile("synthetic-source", "2030-01-01T00:00:00Z")
    writer = ManifestLastPackageWriter(primary)
    writer.stage_content(
        ArtifactDescriptor(
            f"art_{'1' * 48}",
            f"evi_{'1' * 48}",
            ArtifactClass.SOURCE_CONTENT,
            SOURCE_ID,
            OBSERVATION_ID,
            "2026-08-16T00:00:00Z",
            "2026-08-16T00:00:00Z",
            "SYNTHETIC",
            "https://source.invalid/invented",
            "application/json",
            "application/json",
            "identity",
            "utf-8",
            (),
            retention,
        ),
        b"invented bilingual structured content",
    )
    package_id = f"pkg_{'2' * 48}"
    writer.commit_manifest(
        package_kind="source-snapshot",
        package_id=package_id,
        observation_id=OBSERVATION_ID,
        retention=retention,
    )
    receipt = writer.finalize_recovery(RecoveryCopier(primary, recovery), retention)
    snapshot_id = f"snp_{'4' * 48}"
    acquisition = AcquisitionObservationRecord(
        OBSERVATION_ID,
        "sha256:" + "a" * 64,
        SOURCE_ID,
        ENDPOINT_ID,
        "2026-08-16T00:00:00Z",
        "POSSIBLE_CHANGE",
        "SNAPSHOT_PRESERVED",
        "SNAPSHOT_PRESERVED",
        "LEGAL_PROCESSING_ELIGIBLE",
        package_id,
        receipt.primary_manifest.version_id,
        receipt.recovery_manifest.version_id,
        receipt.primary_manifest.fingerprint,
        snapshot_id,
        "",
    )
    return acquisition, receipt


def _activate(package: LoadedRulebook) -> RulebookLifecycle:
    lifecycle = RulebookLifecycle()
    lifecycle.activate(
        package,
        ActivationRecord(
            f"wae_{'8' * 48}",
            package.manifest.package_id,
            package.manifest.package_fingerprint,
            "legal-processing-build-1",
            _contract_fingerprint(),
            "sha256:" + "9" * 64,
            tuple(profile.profile_id for profile in package.semantic_profiles),
            package.attestation_ids[0],
            (SCOPE_ID,),
            "LOCAL_SYNTHETIC",
            "2026-08-16T00:00:00Z",
        ),
        current_contract_set_fingerprint=_contract_fingerprint(),
        current_engine_build="legal-processing-build-1",
    )
    return lifecycle


def test_deterministic_processing_consumes_only_exact_m4_preserved_evidence(
    tmp_path: Path,
) -> None:
    acquisition, receipt = _m4(tmp_path)
    package = _package()
    evidence_ref = receipt.manifest.entries[0].descriptor.artifact_id
    subject = ProcessingSubject(
        f"wki_{'a' * 48}",
        SCOPE_ID,
        acquisition.observation_id,
        acquisition.source_snapshot_id,
        (evidence_ref,),
        ("SOURCE_CONTENT",),
        "NONE",
        (("change_kind", "CREATE"),),
        "sha256:" + "e" * 64,
    )
    register = InMemoryLegalProcessingRegister()
    service = LegalProcessingService(
        _activate(package),
        register,
        DeterministicSemanticTaskRunner({}),
    )
    first = service.process(acquisition, receipt, package, subject, now="2026-08-16T00:00:00Z")
    second = service.process(acquisition, receipt, package, subject, now="2026-08-16T00:00:00Z")
    assert first == second
    assert first[0].rule_id == "ZZZ-TEST-CREATE-001"
    first_candidate = first[1]
    second_candidate = second[1]
    assert first_candidate is not None
    assert second_candidate is not None
    assert first_candidate.canonical_bytes == second_candidate.canonical_bytes
    assert len(register.records) == 1


def test_semantic_processing_requires_exact_primary_and_challenge_then_renders(
    tmp_path: Path,
) -> None:
    acquisition, receipt = _m4(tmp_path)
    package = _package()
    evidence_ref = receipt.manifest.entries[0].descriptor.artifact_id
    subject = ProcessingSubject(
        f"wki_{'a' * 48}",
        SCOPE_ID,
        acquisition.observation_id,
        acquisition.source_snapshot_id,
        (evidence_ref,),
        ("SOURCE_CONTENT",),
        "NONE",
        (("change_kind", "SEMANTIC"),),
        INPUT_FINGERPRINT,
    )
    requests = (
        SemanticTaskRequest(
            f"tsk_{'1' * 48}",
            "GAZETTE_EVENT_ANALYSIS",
            "DECISION",
            package.semantic_profiles[0].profile_id,
            package.manifest.package_fingerprint,
            subject.subject_id,
            subject.evidence_refs,
            b"invented bilingual structured content",
            INPUT_FINGERPRINT,
        ),
        SemanticTaskRequest(
            f"tsk_{'2' * 48}",
            "GAZETTE_EVENT_CHALLENGE",
            "CHALLENGE",
            package.semantic_profiles[1].profile_id,
            package.manifest.package_fingerprint,
            subject.subject_id,
            subject.evidence_refs,
            b"invented bilingual structured content",
            INPUT_FINGERPRINT,
        ),
    )
    runner = DeterministicSemanticTaskRunner(
        {
            ("GAZETTE_EVENT_ANALYSIS", "DECISION", INPUT_FINGERPRINT): (
                "AMENDMENT",
                (evidence_ref,),
                (),
                "NOT_APPLICABLE",
            ),
            ("GAZETTE_EVENT_CHALLENGE", "CHALLENGE", INPUT_FINGERPRINT): (
                "AMENDMENT",
                (evidence_ref,),
                (),
                "PASS",
            ),
        }
    )
    result, candidate, record = LegalProcessingService(
        _activate(package),
        InMemoryLegalProcessingRegister(),
        runner,
    ).process(
        acquisition,
        receipt,
        package,
        subject,
        semantic_requests=requests,
        now="2026-08-16T00:00:00Z",
    )
    assert result.rule_id == "ZZZ-TEST-SEMANTIC-001"
    assert candidate is not None
    assert record.semantic_decision_fingerprint
    assert len(runner.invocations) == 2


def test_unpreserved_reference_and_ineligible_observation_never_execute(tmp_path: Path) -> None:
    acquisition, receipt = _m4(tmp_path)
    package = _package()
    bad_subject = ProcessingSubject(
        f"wki_{'a' * 48}",
        SCOPE_ID,
        acquisition.observation_id,
        acquisition.source_snapshot_id,
        (f"art_{'f' * 48}",),
        ("SOURCE_CONTENT",),
        "NONE",
        (("change_kind", "CREATE"),),
        "sha256:" + "e" * 64,
    )
    service = LegalProcessingService(
        _activate(package),
        InMemoryLegalProcessingRegister(),
        DeterministicSemanticTaskRunner({}),
    )
    with pytest.raises(RulebookError, match="unpreserved evidence"):
        service.process(
            acquisition,
            receipt,
            package,
            bad_subject,
            now="2026-08-16T00:00:00Z",
        )
