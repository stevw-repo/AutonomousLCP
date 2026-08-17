"""M4 immutable local-vault and recovery conformance tests."""

from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_evidence_vault import (
    ArtifactClass,
    ArtifactDescriptor,
    CorruptEvidence,
    EvidenceIntegrityIncident,
    LocalImmutableVault,
    ManifestLastPackageWriter,
    PackageIncomplete,
    RecoveryCopier,
    RetentionBlocked,
    RetentionProfile,
    TwoVaultEvidenceReader,
    VaultCollision,
    VaultName,
    content_logical_key,
    s3_provider_version_id,
    s3_version_reference,
)

RETENTION = RetentionProfile("source-evidence", "2030-01-01T00:00:00Z")


def test_s3_provider_version_reference_is_canonical_reversible_and_distinct() -> None:
    """Preserve an opaque provider version without confusing it with the local fake ID."""
    provider = "3/L4kqtJlcpXroDTDmJ+rmspXd3dIbrHY+MTRCxf3vjVBH40Nr8X8gdRQBpUMLUo"
    reference = s3_version_reference(provider)
    assert reference.startswith("s3v_")
    assert "+" not in reference
    assert "/" not in reference
    assert "=" not in reference
    assert s3_provider_version_id(reference) == provider

    with pytest.raises(ValueError, match="not an S3 provider"):
        s3_provider_version_id("v" + "0" * 64)
    with pytest.raises(ValueError, match="outside the exact safe boundary"):
        s3_version_reference("line\nbreak")


def _vaults(tmp_path: Path) -> tuple[LocalImmutableVault, LocalImmutableVault]:
    return (
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        LocalImmutableVault(tmp_path / "recovery", VaultName.RECOVERY),
    )


def _descriptor(index: int = 1, *, hold: bool = False) -> ArtifactDescriptor:
    digit = f"{index:048x}"
    return ArtifactDescriptor(
        artifact_id=f"art_{digit}",
        artifact_version_id=f"evi_{digit}",
        artifact_class=ArtifactClass.SOURCE_CONTENT,
        source_id=f"src_{'1' * 48}",
        observation_id=f"obs_{'2' * 48}",
        observation_cutoff="2026-08-16T00:00:00Z",
        acquired_at="2026-08-16T00:00:00Z",
        acquisition_method="GET",
        source_locator="https://synthetic.invalid/source",
        declared_media_type="application/json",
        detected_media_type="application/json",
        content_encoding="identity",
        character_encoding="utf-8",
        transport_metadata=(("status-code", "200"),),
        retention=RetentionProfile(
            "source-evidence",
            "2026-08-17T00:00:00Z",
            legal_hold=hold,
        ),
    )


def test_conditional_create_replays_only_exact_bytes_and_exact_version(tmp_path: Path) -> None:
    primary, _recovery = _vaults(tmp_path)
    content = b'{"source":"synthetic"}'
    key = content_logical_key("sha256:" + sha256(content).hexdigest())
    first = primary.conditional_create(key, content, RETENTION)
    replay = primary.conditional_create(key, content, RETENTION)
    assert first.created is True
    assert replay.created is False
    assert replay.reference == first.reference
    assert primary.read_exact(first.reference) == content

    with pytest.raises(VaultCollision):
        primary.conditional_create(key, b"different", RETENTION)


def test_manifest_is_invisible_until_written_last_and_requires_recovery(tmp_path: Path) -> None:
    primary, recovery = _vaults(tmp_path)
    writer = ManifestLastPackageWriter(primary)
    writer.stage_content(_descriptor(), b"exact source bytes")
    assert writer.committed is False
    with pytest.raises(PackageIncomplete):
        writer.finalize_recovery(RecoveryCopier(primary, recovery), RETENTION)

    manifest, primary_manifest = writer.commit_manifest(
        package_kind="source-snapshot",
        package_id=f"pkg_{'3' * 48}",
        observation_id=f"obs_{'2' * 48}",
        retention=RETENTION,
    )
    assert writer.committed is True
    assert primary.read_exact(primary_manifest).startswith(b'{"entries"')
    complete = writer.finalize_recovery(RecoveryCopier(primary, recovery), RETENTION)
    assert complete.manifest == manifest
    assert recovery.read_exact(complete.recovery_manifest) == primary.read_exact(primary_manifest)
    assert len(complete.copies) == 1


def test_lost_ack_restart_adopts_only_verified_existing_versions(tmp_path: Path) -> None:
    primary, recovery = _vaults(tmp_path)
    writer = ManifestLastPackageWriter(primary)
    first = writer.stage_content(_descriptor(), b"restartable")
    restarted = writer.restart()
    replay = restarted.stage_content(_descriptor(), b"restartable")
    assert replay == first
    restarted.commit_manifest(
        package_kind="source-snapshot",
        package_id=f"pkg_{'3' * 48}",
        observation_id=f"obs_{'2' * 48}",
        retention=RETENTION,
    )
    complete = restarted.restart().finalize_recovery(
        RecoveryCopier(primary, recovery),
        RETENTION,
    )
    assert len(complete.copies) == 1


def test_corrupt_primary_and_recovery_never_fall_back_or_choose_a_copy(tmp_path: Path) -> None:
    primary, recovery = _vaults(tmp_path)
    content = b"immutable"
    key = content_logical_key("sha256:" + sha256(content).hexdigest())
    primary_receipt = primary.conditional_create(key, content, RETENTION)
    copy = RecoveryCopier(primary, recovery).copy_exact(primary_receipt.reference, RETENTION)

    primary.inject_corruption(primary_receipt.reference, b"corrupt-primary")
    with pytest.raises(CorruptEvidence):
        primary.read_exact(primary_receipt.reference)
    assert recovery.read_exact(copy.recovery) == content
    reader = TwoVaultEvidenceReader(primary, recovery)
    with pytest.raises(EvidenceIntegrityIncident, match="was not substituted"):
        reader.read(
            copy,
            required_use="LEGAL_PROCESSING",
            artifact_class=ArtifactClass.SOURCE_CONTENT,
            accessed_at="2026-08-16T00:00:00Z",
        )

    recovery.inject_corruption(copy.recovery, b"corrupt-recovery")
    with pytest.raises(CorruptEvidence):
        recovery.read_exact(copy.recovery)
    with pytest.raises(EvidenceIntegrityIncident, match="disagree"):
        reader.read(
            copy,
            required_use="LEGAL_PROCESSING",
            artifact_class=ArtifactClass.SOURCE_CONTENT,
            accessed_at="2026-08-16T00:00:00Z",
        )
    with pytest.raises(CorruptEvidence):
        RecoveryCopier(primary, recovery).copy_exact(primary_receipt.reference, RETENTION)


def test_retention_hold_and_exact_authorization_block_deletion(tmp_path: Path) -> None:
    primary, _recovery = _vaults(tmp_path)
    descriptor = _descriptor(hold=True)
    writer = ManifestLastPackageWriter(primary)
    entry = writer.stage_content(descriptor, b"held")
    with pytest.raises(RetentionBlocked):
        primary.destroy_exact(
            entry.primary,
            authorized=True,
            now="2031-01-01T00:00:00Z",
        )

    unheld = primary.conditional_create(
        content_logical_key("sha256:" + sha256(b"other").hexdigest()),
        b"other",
        RetentionProfile("short", "2026-01-01T00:00:00Z"),
    )
    with pytest.raises(RetentionBlocked):
        primary.destroy_exact(
            unheld.reference,
            authorized=False,
            now="2031-01-01T00:00:00Z",
        )
    primary.destroy_exact(
        unheld.reference,
        authorized=True,
        now="2031-01-01T00:00:00Z",
    )
    assert primary.exists_exact(unheld.reference) is False
