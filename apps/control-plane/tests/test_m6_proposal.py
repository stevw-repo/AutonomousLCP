"""M6 control-plane manifest-last proposal preparation proof."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_control_plane import (
    ProposalPreparationService,
    ProposalRegistrationService,
    VaultProposalPreparationService,
)
from asklegal_corpus import PROPOSAL_ROLE_PATHS, CorpusError, ProposalPackageInput
from asklegal_evidence_vault import (
    CorruptEvidence,
    LocalImmutableVault,
    RetentionProfile,
    VaultName,
    VaultWriteReceipt,
)
from asklegal_management_register import RegisterEventCommand, V1CommandResult
from asklegal_promotion import stored_proposal_package_from_bytes

from tools.tests.proposal_member_fixture import semantic_proposal_fixture


class RecordingVault(LocalImmutableVault):
    """Local vault that exposes only the write order for manifest-last proof."""

    def __init__(self, root: Path) -> None:
        super().__init__(root, VaultName.PRIMARY)
        self.writes: list[str] = []

    def conditional_create(
        self,
        logical_key: str,
        content: bytes,
        retention: RetentionProfile,
    ) -> VaultWriteReceipt:
        self.writes.append(logical_key)
        return super().conditional_create(logical_key, content, retention)


class RecordingRegister:
    """Capture the exact no-effect event the control plane submits."""

    def __init__(self) -> None:
        self.call: tuple[object, ...] | None = None

    def record_event(self, command: RegisterEventCommand) -> V1CommandResult:
        self.call = (
            command.owning_application,
            command.command_id,
            command.command_bytes,
            command.target_id,
            command.expected_version,
            command.expected_absent,
            command.expires_at,
            command.winner_key,
            command.event_id,
            command.event_type,
            command.event_bytes,
        )
        return V1CommandResult(
            command_id=command.command_id,
            result_code="APPLIED",
            authoritative_version=1,
            result_bytes=b'{"result":"APPLIED"}',
            replayed=False,
        )


def _contents() -> dict[str, bytes]:
    return semantic_proposal_fixture(
        observation_cutoff="2026-08-16T00:00:00Z",
        valid_until="2026-08-17T00:00:00Z",
        base_serving_state_id="srv_" + "2" * 48,
        candidate_serving_state_id="srv_" + "3" * 48,
        candidate_serving_state_fingerprint="sha256:" + "c" * 64,
        embedding_profile_fingerprint="sha256:" + "f" * 64,
        validity_predicates=(("configuration", "1.0.0", "sha256:" + "a" * 64),),
    ).contents


def _traceability_shards() -> dict[str, bytes]:
    return semantic_proposal_fixture(
        observation_cutoff="2026-08-16T00:00:00Z",
        valid_until="2026-08-17T00:00:00Z",
        base_serving_state_id="srv_" + "2" * 48,
        candidate_serving_state_id="srv_" + "3" * 48,
        candidate_serving_state_fingerprint="sha256:" + "c" * 64,
        embedding_profile_fingerprint="sha256:" + "f" * 64,
        validity_predicates=(("configuration", "1.0.0", "sha256:" + "a" * 64),),
    ).traceability_shards


def _inputs(contents: dict[str, bytes]) -> ProposalPackageInput:
    promotion_fingerprint = "sha256:" + sha256(contents["PROMOTION_MANIFEST"]).hexdigest()
    return ProposalPackageInput(
        "2026-08-16T00:00:00Z",
        "pmn_" + sha256(promotion_fingerprint.encode()).hexdigest()[:48],
        promotion_fingerprint,
        "srv_" + "2" * 48,
        "sha256:" + "b" * 64,
        "srv_" + "3" * 48,
        "sha256:" + "c" * 64,
    )


def test_control_plane_prepares_and_reads_back_one_exact_proposal() -> None:
    """Only the control service commits the schema-valid root after all members."""
    contents = _contents()
    inputs = _inputs(contents)
    service = ProposalPreparationService(Path(__file__).parents[3] / "contracts")
    package = service.prepare(contents, inputs, _traceability_shards())
    assert service.read(package.package_id) == package
    assert service.prepare(contents, inputs, _traceability_shards()) == package


def test_vault_receipt_survives_restart_and_replays_exactly(tmp_path: Path) -> None:
    """Review can read one proposal from exact versions without process memory."""
    contents = _contents()
    inputs = _inputs(contents)
    vault = RecordingVault(tmp_path / "primary")
    retention = RetentionProfile("proposal-v1", "2036-01-01T00:00:00Z")
    first = VaultProposalPreparationService(
        Path(__file__).parents[3] / "contracts",
        vault,
        retention,
    )

    receipt = first.prepare(contents, inputs, _traceability_shards())
    restarted = VaultProposalPreparationService(
        Path(__file__).parents[3] / "contracts",
        vault,
        retention,
    )

    expected = ProposalPreparationService(Path(__file__).parents[3] / "contracts").prepare(
        contents, inputs, _traceability_shards()
    )
    assert restarted.read(receipt) == expected
    assert restarted.prepare(contents, inputs, _traceability_shards()) == receipt
    assert receipt.manifest_reference.logical_key.endswith("/proposal-manifest.json")
    assert tuple(member.role for member in receipt.members) == tuple(sorted(PROPOSAL_ROLE_PATHS))
    assert vault.writes[-1].endswith("/proposal-manifest.json")


def test_vault_receipt_or_member_corruption_fails_closed(tmp_path: Path) -> None:
    """Neither changed register facts nor changed retained bytes can be reviewed."""
    contents = _contents()
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    service = VaultProposalPreparationService(
        Path(__file__).parents[3] / "contracts",
        vault,
        RetentionProfile("proposal-v1", "2036-01-01T00:00:00Z"),
    )
    receipt = service.prepare(contents, _inputs(contents), _traceability_shards())

    with pytest.raises(CorpusError, match="proposal receipt"):
        service.read(replace(receipt, receipt_fingerprint="sha256:" + "0" * 64))

    vault.inject_corruption(receipt.members[0].reference, b"changed")
    with pytest.raises(CorruptEvidence):
        service.read(receipt)


def test_vault_receipt_reads_zero_entry_shard_and_rejects_transitive_corruption(
    tmp_path: Path,
) -> None:
    """Control commits and rereads every declared shard, including zero bytes."""
    fixture = semantic_proposal_fixture(
        observation_cutoff="2026-08-16T00:00:00Z",
        valid_until="2026-08-17T00:00:00Z",
        base_serving_state_id="srv_" + "2" * 48,
        candidate_serving_state_id="srv_" + "3" * 48,
        candidate_serving_state_fingerprint="sha256:" + "c" * 64,
        embedding_profile_fingerprint="sha256:" + "f" * 64,
        validity_predicates=(("configuration", "1.0.0", "sha256:" + "a" * 64),),
        include_empty_scope=True,
    )
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    service = VaultProposalPreparationService(
        Path(__file__).parents[3] / "contracts",
        vault,
        RetentionProfile("proposal-v1", "2036-01-01T00:00:00Z"),
    )
    receipt = service.prepare(
        fixture.contents,
        _inputs(fixture.contents),
        fixture.traceability_shards,
    )
    empty = next(shard for shard in receipt.traceability_shards if shard.reference.byte_length == 0)

    assert service.read(receipt).package_id == receipt.package_id
    vault.inject_corruption(empty.reference, b"changed")
    with pytest.raises(CorruptEvidence):
        service.read(receipt)


def test_vault_read_rejects_correctly_hashed_semantic_placeholder(tmp_path: Path) -> None:
    """A complete byte inventory cannot admit a meaningless proposal member."""
    contents = _contents()
    contents["CHANGE_INVENTORY"] = b'{"role":"CHANGE_INVENTORY"}'
    service = VaultProposalPreparationService(
        Path(__file__).parents[3] / "contracts",
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        RetentionProfile("proposal-v1", "2036-01-01T00:00:00Z"),
    )

    with pytest.raises(CorpusError, match="proposal semantics"):
        service.prepare(contents, _inputs(contents), _traceability_shards())


def test_only_a_fully_reread_vault_receipt_becomes_review_ready(tmp_path: Path) -> None:
    """Registration is an effect-free atomic event after complete byte verification."""
    contents = _contents()
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    packages = VaultProposalPreparationService(
        Path(__file__).parents[3] / "contracts",
        vault,
        RetentionProfile("proposal-v1", "2036-01-01T00:00:00Z"),
    )
    receipt = packages.prepare(contents, _inputs(contents), _traceability_shards())
    register = RecordingRegister()

    result = ProposalRegistrationService(packages, register).register(
        receipt,
        command_id="cmd_" + "1" * 48,
        expires_at="2026-08-22T00:00:00Z",
    )

    assert result.result_code == "APPLIED"
    assert register.call is not None
    assert register.call[0] == "CONTROL_PLANE"
    assert register.call[3] == receipt.package_id
    assert register.call[5] is True
    assert register.call[9] == "PROPOSAL_REVIEW_READY"
    event_bytes = register.call[10]
    assert isinstance(event_bytes, bytes)
    assert sha256(event_bytes).hexdigest() == receipt.receipt_fingerprint.removeprefix("sha256:")
    assert stored_proposal_package_from_bytes(event_bytes) == receipt
