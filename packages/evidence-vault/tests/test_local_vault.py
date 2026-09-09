"""M4 immutable local-vault and recovery conformance tests."""

from hashlib import sha256
from multiprocessing import Queue, get_context
from pathlib import Path
from threading import Barrier, Event, Thread
from typing import Protocol

import pytest
from asklegal_evidence_vault import (
    ArtifactClass,
    ArtifactDescriptor,
    CorruptEvidence,
    EvidenceIntegrityIncident,
    ExactObjectReference,
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


class _ProcessBarrier(Protocol):
    def wait(self) -> int: ...


def _process_write(root: str, content: bytes, barrier: _ProcessBarrier, queue: Queue[str]) -> None:
    """One process-local write for the cross-process lock proof."""
    vault = LocalImmutableVault(Path(root), VaultName.PRIMARY)
    barrier.wait()
    try:
        receipt = vault.conditional_create("fixed/process.json", content, RETENTION)
    except VaultCollision:
        queue.put("collision")
    else:
        queue.put("created" if receipt.created else "adopted")


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


def test_resolve_current_returns_the_adapter_owned_exact_local_reference(tmp_path: Path) -> None:
    """Read-only key resolution never derives a version convention in its caller."""
    primary, _recovery = _vaults(tmp_path)
    key = "proof/current.json"
    assert primary.resolve_current(key) is None
    receipt = primary.conditional_create(key, b"exact", RETENTION)
    assert primary.resolve_current(key) == receipt.reference


def test_local_vault_two_instances_allow_one_divergent_writer_and_one_version(
    tmp_path: Path,
) -> None:
    """The key lock makes a fixed key single-assignment across separate local instances."""
    root = tmp_path / "shared"
    first = LocalImmutableVault(root, VaultName.PRIMARY)
    second = LocalImmutableVault(root, VaultName.PRIMARY)
    gate = Barrier(2)
    results: list[object] = []

    def write(vault: LocalImmutableVault, content: bytes) -> None:
        gate.wait()
        try:
            results.append(vault.conditional_create("fixed/item.json", content, RETENTION))
        except VaultCollision as error:
            results.append(error)

    one = Thread(target=write, args=(first, b"one"))
    two = Thread(target=write, args=(second, b"two"))
    one.start()
    two.start()
    one.join()
    two.join()
    assert sum(isinstance(result, VaultCollision) for result in results) == 1
    assert sum(not isinstance(result, VaultCollision) for result in results) == 1
    reference = first.resolve_current("fixed/item.json")
    assert reference is not None
    assert first.read_exact(reference) in {b"one", b"two"}


def test_local_vault_two_processes_allow_one_divergent_writer(tmp_path: Path) -> None:
    """The no-follow key lock serializes separate Python processes."""
    root = tmp_path / "process-shared"
    context = get_context("fork")
    barrier = context.Barrier(2)
    queue: Queue[str] = context.Queue()
    first = context.Process(target=_process_write, args=(str(root), b"one", barrier, queue))
    second = context.Process(target=_process_write, args=(str(root), b"two", barrier, queue))
    first.start()
    second.start()
    first.join(10)
    second.join(10)
    assert first.exitcode == second.exitcode == 0
    assert sorted((queue.get(timeout=2), queue.get(timeout=2))) == ["collision", "created"]


def test_local_vault_two_processes_adopt_identical_writer_once(tmp_path: Path) -> None:
    """Two processes writing identical evidence return one creator and one exact adoption."""
    root = tmp_path / "process-identical"
    context = get_context("fork")
    barrier = context.Barrier(2)
    queue: Queue[str] = context.Queue()
    first = context.Process(target=_process_write, args=(str(root), b"same", barrier, queue))
    second = context.Process(target=_process_write, args=(str(root), b"same", barrier, queue))
    first.start()
    second.start()
    first.join(10)
    second.join(10)
    assert first.exitcode == second.exitcode == 0
    assert sorted((queue.get(timeout=2), queue.get(timeout=2))) == ["adopted", "created"]
    resolved = LocalImmutableVault(root, VaultName.PRIMARY).resolve_current("fixed/process.json")
    assert resolved is not None


def test_destroy_and_create_same_key_are_one_serialized_transaction(tmp_path: Path) -> None:
    """A concurrent create waits for exact destruction, then creates a durable new version."""
    entered = Event()
    release = Event()
    created = Event()
    armed = Event()

    class GatedVault(LocalImmutableVault):
        def _retention_unlocked(self, reference: ExactObjectReference) -> RetentionProfile:
            if armed.is_set():
                entered.set()
                assert release.wait(2)
            return super()._retention_unlocked(reference)

    primary = GatedVault(tmp_path / "primary", VaultName.PRIMARY)
    receipt = primary.conditional_create("fixed/destroy.json", b"old", RETENTION)
    armed.set()

    destroyer = Thread(
        target=primary.destroy_exact,
        args=(receipt.reference,),
        kwargs={"authorized": True, "now": "2031-01-01T00:00:00Z"},
    )

    def write() -> None:
        primary.conditional_create("fixed/destroy.json", b"new", RETENTION)
        created.set()

    writer = Thread(target=write)
    destroyer.start()
    assert entered.wait(2)
    writer.start()
    assert created.wait(0.05) is False
    release.set()
    destroyer.join(2)
    writer.join(2)
    assert created.is_set()
    resolved = primary.resolve_current("fixed/destroy.json")
    assert resolved is not None
    assert primary.read_exact(resolved) == b"new"


def test_local_vault_rejects_retention_mismatch_and_partial_metadata(tmp_path: Path) -> None:
    """A replay never claims a requested retention when stored metadata differs or is partial."""
    primary, _recovery = _vaults(tmp_path)
    key = "fixed/retention.json"
    receipt = primary.conditional_create(key, b"exact", RETENTION)
    with pytest.raises(VaultCollision):
        primary.conditional_create(key, b"exact", RetentionProfile("other", "2031-01-01T00:00:00Z"))
    metadata = primary.root / "metadata" / key / f"{receipt.reference.version_id}.json"
    metadata.write_text("{}", encoding="utf-8")
    with pytest.raises(CorruptEvidence):
        primary.retention(receipt.reference)


@pytest.mark.parametrize("kind", ["missing-metadata", "extra-object", "extra-metadata"])
def test_resolve_current_rejects_partial_or_extra_retained_versions(
    tmp_path: Path, kind: str
) -> None:
    """Read-only recovery resolution accepts exactly one matching object and metadata leaf."""
    primary, _recovery = _vaults(tmp_path)
    key = "fixed/current.json"
    receipt = primary.conditional_create(key, b"exact", RETENTION)
    object_parent = primary.root / "objects" / key
    metadata_parent = primary.root / "metadata" / key
    if kind == "missing-metadata":
        (metadata_parent / f"{receipt.reference.version_id}.json").unlink()
    elif kind == "extra-object":
        (object_parent / "vextra").write_bytes(b"other")
    else:
        (metadata_parent / "vextra.json").write_text("{}", encoding="utf-8")

    with pytest.raises(CorruptEvidence):
        primary.resolve_current(key)


@pytest.mark.parametrize("key", ["alias/../actual/key.json", "", "a//b", "a\\b", "a/\x01b"])
def test_invalid_local_key_has_no_object_metadata_or_lock_side_effect(
    tmp_path: Path, key: str
) -> None:
    """Validation precedes lock/object/metadata creation for every unsafe key spelling."""
    primary, _recovery = _vaults(tmp_path)
    with pytest.raises((TypeError, ValueError)):
        primary.conditional_create(key, b"bytes", RETENTION)
    assert not any((primary.root / "objects").rglob("*"))
    assert not any((primary.root / "metadata").rglob("*"))
    assert not (primary.root / ".locks").exists()


def test_local_lock_root_symlink_is_rejected_without_escape(tmp_path: Path) -> None:
    """A hostile lock-root symlink cannot redirect advisory lock creation outside the vault."""
    primary, _recovery = _vaults(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    locks = primary.root / ".locks"
    locks.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="lock root"):
        primary.conditional_create("safe/key.json", b"bytes", RETENTION)
    assert list(outside.iterdir()) == []


def test_local_key_lock_symlink_is_rejected_without_escape(tmp_path: Path) -> None:
    """A pre-existing hashed per-key lock symlink cannot redirect a lock open."""
    primary, _recovery = _vaults(tmp_path)
    outside = tmp_path / "outside-lock"
    outside.mkdir()
    locks = primary.root / ".locks"
    locks.mkdir()
    digest = sha256(b"safe/key.json").hexdigest()
    (locks / f"{digest}.lock").symlink_to(outside / "target")
    with pytest.raises(OSError, match=r"Too many levels|File exists"):
        primary.conditional_create("safe/key.json", b"bytes", RETENTION)
    assert list(outside.iterdir()) == []


def test_constructor_rejects_object_and_metadata_root_symlink_escape(tmp_path: Path) -> None:
    """The vault never treats a symlinked store root as a contained directory."""
    root = tmp_path / "primary"
    outside = tmp_path / "outside"
    (outside / "objects").mkdir(parents=True)
    (outside / "metadata").mkdir()
    root.mkdir()
    (root / "objects").symlink_to(outside / "objects", target_is_directory=True)
    (root / "metadata").symlink_to(outside / "metadata", target_is_directory=True)

    with pytest.raises(ValueError, match="objects root"):
        LocalImmutableVault(root, VaultName.PRIMARY)

    assert not any((outside / "objects").iterdir())
    assert not any((outside / "metadata").iterdir())


def test_constructor_rejects_requested_vault_root_symlink_escape(tmp_path: Path) -> None:
    """The caller's named vault root is itself the containment boundary, never an alias."""
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="vault root"):
        LocalImmutableVault(alias, VaultName.PRIMARY)

    assert list(outside.iterdir()) == []


def test_local_vault_rejects_internal_object_and_metadata_key_aliases(tmp_path: Path) -> None:
    """A symlinked key component cannot alias a different immutable key within the root."""
    primary, _recovery = _vaults(tmp_path)
    receipt = primary.conditional_create("actual/key.json", b"same", RETENTION)
    (primary.root / "objects" / "alias").symlink_to(
        primary.root / "objects" / "actual", target_is_directory=True
    )
    (primary.root / "metadata" / "alias").symlink_to(
        primary.root / "metadata" / "actual", target_is_directory=True
    )

    with pytest.raises((CorruptEvidence, ValueError, VaultCollision)):
        primary.conditional_create("alias/key.json", b"same", RETENTION)
    with pytest.raises((CorruptEvidence, ValueError, VaultCollision)):
        primary.resolve_current("alias/key.json")
    assert primary.read_exact(receipt.reference) == b"same"


def test_local_retention_rejects_a_reference_from_the_other_vault(tmp_path: Path) -> None:
    """Retention is bound to the same exact vault identity as content reads."""
    primary, _recovery = _vaults(tmp_path)
    receipt = primary.conditional_create("fixed/retention.json", b"exact", RETENTION)
    foreign = ExactObjectReference(
        VaultName.RECOVERY,
        receipt.reference.logical_key,
        receipt.reference.version_id,
        receipt.reference.fingerprint,
        receipt.reference.byte_length,
    )

    with pytest.raises(ValueError, match="different vault"):
        primary.retention(foreign)


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
