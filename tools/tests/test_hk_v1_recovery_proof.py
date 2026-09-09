"""Offline contract tests for the provider-neutral Hong Kong V1 recovery kernel."""

from __future__ import annotations

import json
from copy import copy, deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

import pytest
from asklegal_durable_task import V1SchedulerSettings
from asklegal_evidence_vault import (
    ArtifactClass,
    ArtifactDescriptor,
    EvidenceManifest,
    EvidenceManifestEntry,
    EvidencePackageReceipt,
    ExactObjectReference,
    LocalImmutableVault,
    ManifestLastPackageWriter,
    RecoveryCopier,
    RecoveryCopyReceipt,
    RetentionProfile,
    VaultName,
)
from asklegal_management_register_ports import InMemoryManagementRegister

from tools.hk_v1_recovery_proof import (
    FilesystemSchedulerRecoveryAdapter,
    FilesystemSQLRecoveryAdapter,
    FilesystemVaultRecoveryAdapter,
    HKV1RecoveryContractAssessment,
    ImmutableVaultLiveRecoveryPort,
    LeastPrivilegeProbe,
    LeastPrivilegeProbeKind,
    LeastPrivilegeProbeResult,
    LiveRecoveryAcknowledgementLost,
    LiveRecoveryExecutionAdapters,
    LiveRecoveryExecutionError,
    LiveRecoveryStep,
    LiveRecoveryStepReceipt,
    LocalRecoveryAdapters,
    LocalRecoveryConfiguration,
    LocalRecoveryMode,
    LocalRecoveryStatus,
    MigrationReadback,
    RecoveryBlockerCode,
    RecoveryContractRequest,
    RecoveryDimensionResult,
    RecoveryEvidenceReference,
    RecoveryProofError,
    RecoveryProofErrorCode,
    RecoveryResultCode,
    RegisterFamilyReadback,
    SchedulerHubInventory,
    SchedulerRecoveryMode,
    SchedulerReplacementLeg,
    SchedulerReplacementObservation,
    SchedulerRole,
    SealedCredentialReference,
    SQLRestoreObservation,
    VaultRestoredObject,
    VaultRestoreObservation,
    assess_local_recovery_contract,
    build_live_recovery_credential_manifest,
    build_live_recovery_plan,
    build_live_recovery_request,
    build_local_scheduler_snapshot,
    build_local_sql_snapshot,
    derive_local_recovery_targets,
    execute_live_recovery,
    freeze_local_recovery_contract,
    load_live_recovery_request,
    main,
    run_local_recovery,
)
from tools.hk_v1_sql_recovery import (
    SQLBackupPathBinding,
    build_sql_backup_path_manifest,
)

SqlChange = Literal[
    "backup",
    "duplicate_family",
    "duplicate_ledger_receipt",
    "external_digest",
    "family_count",
    "missing_family",
    "missing_probe",
    "negative_read",
    "projection",
    "restored_receipt",
    "same_database",
    "source_family",
    "source_migration",
    "source_receipt",
    "truncated_migrations",
]
VaultChange = Literal[
    "clean_room_collision",
    "corrupt_hash",
    "duplicate_objects",
    "duplicate_target_version",
    "extra_duplicate",
    "missing_object",
    "unregistered_version",
    "wrong_length",
    "wrong_source_version",
]
SchedulerChange = Literal[
    "cross_role",
    "duplicate_fence_receipt",
    "empty_effect_receipts",
    "history_copied",
    "history_resumed",
    "hub_drift",
    "reverse_instance_drift",
    "reverse_lineage_drift",
    "same_lineage",
]


def _opaque(number: int) -> str:
    return f"r_{number:032x}"


def _fingerprint(number: int) -> str:
    return f"sha256:{number:064x}"


def _reference(number: int) -> RecoveryEvidenceReference:
    return RecoveryEvidenceReference(_opaque(number), _fingerprint(number))


def _descriptor(retention: RetentionProfile) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        artifact_id="art_" + "1" * 48,
        artifact_version_id="evi_" + "2" * 48,
        artifact_class=ArtifactClass.SOURCE_CONTENT,
        source_id="src_" + "3" * 48,
        observation_id="obs_" + "4" * 48,
        observation_cutoff="2026-08-27T00:00:00Z",
        acquired_at="2026-08-27T00:00:00Z",
        acquisition_method="GET",
        source_locator="https://synthetic.invalid/proof",
        declared_media_type="application/json",
        detected_media_type="application/json",
        content_encoding="identity",
        character_encoding="utf-8",
        transport_metadata=(("status-code", "200"),),
        retention=retention,
    )


def _receipt() -> EvidencePackageReceipt:
    retention = RetentionProfile("proof", "2030-01-01T00:00:00Z")
    descriptor = _descriptor(retention)
    primary = ExactObjectReference(
        VaultName.PRIMARY, "objects/one.json", "v" + "1" * 64, _fingerprint(1), 10
    )
    recovery = ExactObjectReference(
        VaultName.RECOVERY, "objects/one.json", "v" + "2" * 64, _fingerprint(1), 10
    )
    manifest = EvidenceManifest(
        "proof", "pkg_" + "5" * 48, "obs_" + "4" * 48, (EvidenceManifestEntry(descriptor, primary),)
    )
    primary_manifest = ExactObjectReference(
        VaultName.PRIMARY, "packages/proof/manifest.json", "v" + "3" * 64, _fingerprint(3), 20
    )
    recovery_manifest = ExactObjectReference(
        VaultName.RECOVERY, "packages/proof/manifest.json", "v" + "4" * 64, _fingerprint(3), 20
    )
    return EvidencePackageReceipt(
        manifest, primary_manifest, recovery_manifest, (RecoveryCopyReceipt(primary, recovery),)
    )


def _request() -> RecoveryContractRequest:
    return freeze_local_recovery_contract(
        migration_prefix=(
            MigrationReadback("m_000001", _fingerprint(1)),
            MigrationReadback("m_000002", _fingerprint(2)),
        ),
        register_families=(
            RegisterFamilyReadback("commands", 3, _fingerprint(3)),
            RegisterFamilyReadback("events", 4, _fingerprint(4)),
        ),
        sql_backup_reference=_reference(15),
        external_ledger_digest_reference=_reference(19),
        source_ledger_verification_receipt=_reference(20),
        restored_ledger_verification_receipt=_reference(21),
        vault_package_receipt=_receipt(),
        primary_vault_identity=_opaque(10),
        recovery_vault_identity=_opaque(11),
        scheduler_hubs=(
            SchedulerHubInventory(SchedulerRole.GENERAL, (_opaque(12), _opaque(13))),
            SchedulerHubInventory(SchedulerRole.PROMOTION, (_opaque(14),)),
        ),
    )


def _sql(request: RecoveryContractRequest) -> SQLRestoreObservation:
    return SQLRestoreObservation(
        request_fingerprint=request.fingerprint,
        backup_reference=_reference(15),
        source_database_identity=_opaque(16),
        restored_database_identity=_opaque(17),
        source_migrations=request.migration_prefix,
        restored_migrations=request.migration_prefix,
        source_families=request.register_families,
        restored_families=request.register_families,
        projection_rebuild_fingerprint=request.projection_rebuild_fingerprint,
        external_ledger_digest_reference=request.external_ledger_digest_reference,
        source_ledger_verification_receipt=request.source_ledger_verification_receipt,
        restored_ledger_verification_receipt=request.restored_ledger_verification_receipt,
        least_privilege_probes=(
            LeastPrivilegeProbe(LeastPrivilegeProbeKind.READ, LeastPrivilegeProbeResult.ALLOWED),
            LeastPrivilegeProbe(
                LeastPrivilegeProbeKind.PROCEDURE_EXECUTE, LeastPrivilegeProbeResult.ALLOWED
            ),
            LeastPrivilegeProbe(
                LeastPrivilegeProbeKind.DIRECT_DML, LeastPrivilegeProbeResult.DENIED
            ),
            LeastPrivilegeProbe(
                LeastPrivilegeProbeKind.CROSS_ROLE, LeastPrivilegeProbeResult.DENIED
            ),
        ),
    )


def _vault(request: RecoveryContractRequest) -> VaultRestoreObservation:
    return VaultRestoreObservation(
        request_fingerprint=request.fingerprint,
        clean_room_target_identity=_opaque(21),
        restored_objects=tuple(
            VaultRestoredObject(
                item.logical_key,
                item.version_id,
                item.fingerprint,
                item.byte_length,
                _opaque(21),
                _opaque(24 + index),
                item.fingerprint,
                item.byte_length,
            )
            for index, item in enumerate(
                (
                    *tuple(copy.recovery for copy in request.vault_package_receipt.copies),
                    request.vault_package_receipt.recovery_manifest,
                )
            )
        ),
    )


def _leg(role: SchedulerRole, hubs: tuple[str, ...], start: int) -> SchedulerReplacementLeg:
    return SchedulerReplacementLeg(
        role,
        hubs,
        _opaque(start),
        _opaque(start + 1),
        _opaque(start + 2),
        _opaque(start + 3),
        _reference(start + 4),
        _reference(start + 5),
        (_reference(start + 6), _reference(start + 7)),
        _reference(start + 8),
        _reference(start + 9),
        SchedulerRecoveryMode.REPLACEMENT_FROM_SAFE_CHECKPOINT,
    )


def _scheduler(
    request: RecoveryContractRequest, role: SchedulerRole, start: int
) -> SchedulerReplacementObservation:
    hubs = next(item.hubs for item in request.scheduler_hubs if item.role is role)
    forward = _leg(role, hubs, start)
    reverse = replace(
        _leg(role, hubs, start + 20),
        lost_instance_identity=forward.replacement_instance_identity,
        old_lineage_identity=forward.recovery_lineage_identity,
    )
    return SchedulerReplacementObservation(role, forward, reverse)


def _complete_assessment() -> HKV1RecoveryContractAssessment:
    request = _request()
    return assess_local_recovery_contract(
        request,
        _sql(request),
        _vault(request),
        (
            _scheduler(request, SchedulerRole.GENERAL, 30),
            _scheduler(request, SchedulerRole.PROMOTION, 80),
        ),
    )


def _mutate_sql(change: SqlChange, value: SQLRestoreObservation) -> SQLRestoreObservation:  # noqa: C901, PLR0911, PLR0912
    if change == "same_database":
        return replace(value, restored_database_identity=value.source_database_identity)
    if change == "truncated_migrations":
        return replace(value, restored_migrations=value.restored_migrations[:1])
    if change == "missing_family":
        return replace(value, restored_families=value.restored_families[:-1])
    if change == "duplicate_family":
        return replace(value, restored_families=(value.restored_families[0],) * 2)
    if change == "family_count":
        return replace(
            value,
            restored_families=(
                replace(value.restored_families[0], row_count=99),
                value.restored_families[1],
            ),
        )
    if change == "projection":
        return replace(value, projection_rebuild_fingerprint=_fingerprint(99))
    if change == "duplicate_ledger_receipt":
        return replace(value, restored_ledger_verification_receipt=_reference(19))
    if change == "missing_probe":
        return replace(value, least_privilege_probes=value.least_privilege_probes[:-1])
    if change == "negative_read":
        return replace(
            value,
            least_privilege_probes=(
                replace(value.least_privilege_probes[0], result=LeastPrivilegeProbeResult.DENIED),
                *value.least_privilege_probes[1:],
            ),
        )
    if change == "backup":
        return replace(value, backup_reference=_reference(99))
    if change == "source_migration":
        return replace(
            value,
            source_migrations=(
                MigrationReadback("m_000001", _fingerprint(99)),
                value.source_migrations[1],
            ),
        )
    if change == "source_family":
        return replace(
            value,
            source_families=(
                replace(value.source_families[0], content_fingerprint=_fingerprint(99)),
                value.source_families[1],
            ),
        )
    if change == "external_digest":
        return replace(value, external_ledger_digest_reference=_reference(99))
    if change == "source_receipt":
        return replace(value, source_ledger_verification_receipt=_reference(99))
    if change == "restored_receipt":
        return replace(value, restored_ledger_verification_receipt=_reference(99))
    raise AssertionError(change)


def _mutate_vault(  # noqa: PLR0911
    change: VaultChange,
    request: RecoveryContractRequest,
    value: VaultRestoreObservation,
) -> VaultRestoreObservation:
    if change == "missing_object":
        return replace(value, restored_objects=value.restored_objects[:-1])
    if change == "duplicate_objects":
        return replace(value, restored_objects=(value.restored_objects[0],) * 2)
    if change == "corrupt_hash":
        return replace(
            value,
            restored_objects=(
                replace(value.restored_objects[0], reread_fingerprint=_fingerprint(99)),
                value.restored_objects[1],
            ),
        )
    if change == "wrong_source_version":
        return replace(
            value,
            restored_objects=(
                replace(value.restored_objects[0], source_version=_opaque(99)),
                value.restored_objects[1],
            ),
        )
    if change == "clean_room_collision":
        return replace(value, clean_room_target_identity=request.primary_vault_identity)
    if change == "wrong_length":
        return replace(
            value,
            restored_objects=(
                replace(value.restored_objects[0], reread_byte_length=999),
                value.restored_objects[1],
            ),
        )
    if change == "extra_duplicate":
        return replace(value, restored_objects=(*value.restored_objects, value.restored_objects[0]))
    if change == "unregistered_version":
        return replace(
            value,
            restored_objects=(
                replace(value.restored_objects[0], source_version="v" + "f" * 64),
                *value.restored_objects[1:],
            ),
        )
    if change == "duplicate_target_version":
        return replace(
            value,
            restored_objects=(
                replace(
                    value.restored_objects[0],
                    target_version=value.restored_objects[1].target_version,
                ),
                *value.restored_objects[1:],
            ),
        )
    raise AssertionError(change)


def _mutate_scheduler(  # noqa: PLR0911
    change: SchedulerChange, value: SchedulerReplacementObservation
) -> SchedulerReplacementObservation:
    if change == "same_lineage":
        return replace(
            value,
            forward=replace(
                value.forward, old_lineage_identity=value.forward.recovery_lineage_identity
            ),
        )
    if change == "duplicate_fence_receipt":
        return replace(
            value,
            forward=replace(
                value.forward, old_lineage_fence_receipt=value.forward.safe_checkpoint_reference
            ),
        )
    if change == "empty_effect_receipts":
        return replace(value, forward=replace(value.forward, effect_reconciliation_receipts=()))
    if change == "history_resumed":
        return replace(
            value, forward=replace(value.forward, mode=SchedulerRecoveryMode.HISTORY_RESUMED)
        )
    if change == "reverse_instance_drift":
        return replace(
            value,
            reverse=replace(
                value.reverse, lost_instance_identity=value.forward.lost_instance_identity
            ),
        )
    if change == "hub_drift":
        return replace(value, forward=replace(value.forward, hubs=(_opaque(999),)))
    if change == "cross_role":
        return replace(value, forward=replace(value.forward, role=SchedulerRole.PROMOTION))
    if change == "history_copied":
        return replace(
            value, forward=replace(value.forward, mode=SchedulerRecoveryMode.HISTORY_COPIED)
        )
    if change == "reverse_lineage_drift":
        return replace(value, reverse=replace(value.reverse, old_lineage_identity=_opaque(999)))
    raise AssertionError(change)


def test_missing_module_red_is_replaced_by_a_callable_assessor() -> None:
    """Removing the assessor would make this contract suite fail at import time."""
    assert callable(assess_local_recovery_contract)


def test_complete_scripted_observations_issue_only_local_contract_proof() -> None:
    """Changing any complete dimension to implicit success must not pass this proof."""
    assessment = _complete_assessment()
    assert assessment.result_code is RecoveryResultCode.LOCAL_RECOVERY_CONTRACT_PROVED
    assert (assessment.sql_result, assessment.vault_result, assessment.scheduler_result) == (
        RecoveryDimensionResult.PROVED,
    ) * 3
    assert assessment.contract_proved is True
    assert assessment.gate_f_eligible is False
    assert assessment.blockers == (
        RecoveryBlockerCode.SCHEDULER_REPLACEMENT_UNRUN,
        RecoveryBlockerCode.SQL_ENGINE_RESTORE_UNRUN,
        RecoveryBlockerCode.VAULT_CLEAN_ROOM_RESTORE_UNRUN,
    )


@pytest.mark.parametrize(
    "change",
    [
        "same_database",
        "truncated_migrations",
        "missing_family",
        "duplicate_family",
        "family_count",
        "projection",
        "duplicate_ledger_receipt",
        "missing_probe",
        "negative_read",
    ],
)
def test_sql_drift_or_incomplete_readback_is_withheld(change: SqlChange) -> None:
    """Removing any independent SQL readback assertion must withhold the SQL dimension."""
    request = _request()
    assessment = assess_local_recovery_contract(
        request,
        _mutate_sql(change, _sql(request)),
        _vault(request),
        (
            _scheduler(request, SchedulerRole.GENERAL, 30),
            _scheduler(request, SchedulerRole.PROMOTION, 80),
        ),
    )
    assert assessment.sql_result is RecoveryDimensionResult.WITHHELD
    assert RecoveryBlockerCode.SQL_RESTORE_READBACK_FAILED in assessment.blockers
    assert assessment.contract_proved is False


@pytest.mark.parametrize(
    "change",
    [
        "missing_object",
        "duplicate_objects",
        "corrupt_hash",
        "wrong_source_version",
        "clean_room_collision",
        "wrong_length",
    ],
)
def test_vault_inventory_or_exact_version_drift_is_withheld(change: VaultChange) -> None:
    """Replacing vault readback with a copy-only or incomplete claim must not prove it."""
    request = _request()
    assessment = assess_local_recovery_contract(
        request,
        _sql(request),
        _mutate_vault(change, request, _vault(request)),
        (
            _scheduler(request, SchedulerRole.GENERAL, 30),
            _scheduler(request, SchedulerRole.PROMOTION, 80),
        ),
    )
    assert assessment.vault_result is RecoveryDimensionResult.WITHHELD
    assert RecoveryBlockerCode.VAULT_RESTORE_READBACK_FAILED in assessment.blockers


@pytest.mark.parametrize(
    "change",
    [
        "extra_duplicate",
        "missing_object",
        "unregistered_version",
        "duplicate_target_version",
    ],
)
def test_receipt_derived_vault_manifest_and_exact_versions_cannot_drift(
    change: VaultChange,
) -> None:
    """A receipt-derived inventory must include every exact recovery version once."""
    request = _request()
    assessment = assess_local_recovery_contract(
        request,
        _sql(request),
        _mutate_vault(change, request, _vault(request)),
        (
            _scheduler(request, SchedulerRole.GENERAL, 30),
            _scheduler(request, SchedulerRole.PROMOTION, 80),
        ),
    )
    assert assessment.vault_result is RecoveryDimensionResult.WITHHELD
    assert RecoveryBlockerCode.VAULT_RESTORE_READBACK_FAILED in assessment.blockers


@pytest.mark.parametrize(
    "change",
    [
        "backup",
        "source_migration",
        "source_family",
        "external_digest",
        "source_receipt",
        "restored_receipt",
    ],
)
def test_sql_frozen_backup_source_and_ledger_facts_cannot_drift(change: SqlChange) -> None:
    """A source-side or ledger substitution cannot borrow a matching restored readback."""
    request = _request()
    assessment = assess_local_recovery_contract(
        request,
        _mutate_sql(change, _sql(request)),
        _vault(request),
        (
            _scheduler(request, SchedulerRole.GENERAL, 30),
            _scheduler(request, SchedulerRole.PROMOTION, 80),
        ),
    )
    assert assessment.sql_result is RecoveryDimensionResult.WITHHELD
    assert RecoveryBlockerCode.SQL_RESTORE_READBACK_FAILED in assessment.blockers


def test_receipt_input_is_not_relabelled_as_a_local_vault_or_scheduler_drill(
    tmp_path: Path,
) -> None:
    """Current deterministic fakes are semantic fixtures, never operational recovery evidence."""
    register = InMemoryManagementRegister()
    package = register.export_recovery(("000001",))
    restored_register = InMemoryManagementRegister()
    restored_register.restore_recovery(package)
    assert (
        restored_register.export_recovery(("000001",)).snapshot.projections
        == package.snapshot.projections
    )

    retention = RetentionProfile("proof", "2030-01-01T00:00:00Z")
    primary = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    recovery = LocalImmutableVault(tmp_path / "recovery", VaultName.RECOVERY)
    writer = ManifestLastPackageWriter(primary)
    writer.stage_content(_descriptor(retention), b"semantic fixture")
    writer.commit_manifest(
        package_kind="proof",
        package_id="pkg_" + "5" * 48,
        observation_id="obs_" + "4" * 48,
        retention=retention,
    )
    receipt = writer.finalize_recovery(RecoveryCopier(primary, recovery), retention)
    for copied in receipt.copies:
        assert recovery.read_exact(copied.recovery) == primary.read_exact(copied.primary)
    assert recovery.read_exact(receipt.recovery_manifest) == primary.read_exact(
        receipt.primary_manifest
    )
    request = freeze_local_recovery_contract(
        (MigrationReadback("m_000001", _fingerprint(1)),),
        (RegisterFamilyReadback("events", 1, _fingerprint(2)),),
        _reference(3),
        _reference(4),
        _reference(5),
        _reference(6),
        receipt,
        _opaque(7),
        _opaque(8),
        (
            SchedulerHubInventory(SchedulerRole.GENERAL, (_opaque(9),)),
            SchedulerHubInventory(SchedulerRole.PROMOTION, (_opaque(10),)),
        ),
    )
    assert request.vault_package_receipt is receipt

    control = V1SchedulerSettings.for_application("CONTROL_PLANE")
    promotion = V1SchedulerSettings.for_application("PROMOTION_WORKER")
    assert (control.scheduler_service, control.task_hub, control.loss_result) == (
        "dts-general",
        "control",
        "REPLACEMENT_FROM_SAFE_CHECKPOINT",
    )
    assert (promotion.scheduler_service, promotion.task_hub, promotion.loss_result) == (
        "dts-promotion",
        "promotion",
        "REPLACEMENT_FROM_SAFE_CHECKPOINT",
    )
    with pytest.raises(RecoveryProofError) as rejected:
        freeze_local_recovery_contract(
            (MigrationReadback("m_000001", _fingerprint(1)),),
            (RegisterFamilyReadback("events", 1, _fingerprint(2)),),
            _reference(3),
            _reference(4),
            _reference(5),
            _reference(6),
            cast("EvidencePackageReceipt", primary),
            _opaque(7),
            _opaque(8),
            (
                SchedulerHubInventory(SchedulerRole.GENERAL, (_opaque(9),)),
                SchedulerHubInventory(SchedulerRole.PROMOTION, (_opaque(10),)),
            ),
        )
    assert rejected.value.code is RecoveryProofErrorCode.INPUT_INVALID


def test_scheduler_identity_reuse_has_its_own_independence_blocker() -> None:
    """Allowing a lost scheduler to be its own replacement would erase the loss drill."""
    request = _request()
    general = _scheduler(request, SchedulerRole.GENERAL, 30)
    assessment = assess_local_recovery_contract(
        request,
        _sql(request),
        _vault(request),
        (
            replace(
                general,
                forward=replace(
                    general.forward,
                    replacement_instance_identity=general.forward.lost_instance_identity,
                ),
            ),
            _scheduler(request, SchedulerRole.PROMOTION, 80),
        ),
    )
    assert RecoveryBlockerCode.SCHEDULER_NOT_INDEPENDENT in assessment.blockers
    assert assessment.scheduler_result is RecoveryDimensionResult.WITHHELD


def test_duplicate_scheduler_receipt_is_not_misclassified_as_identity_reuse() -> None:
    """Collapsing receipts must fail replacement evidence, not instance independence."""
    request = _request()
    general = _scheduler(request, SchedulerRole.GENERAL, 30)
    duplicate_receipt = replace(
        general,
        forward=replace(
            general.forward,
            replacement_start_result_receipt=general.forward.safe_checkpoint_reference,
        ),
    )
    assessment = assess_local_recovery_contract(
        request,
        _sql(request),
        _vault(request),
        (duplicate_receipt, _scheduler(request, SchedulerRole.PROMOTION, 80)),
    )

    assert RecoveryBlockerCode.SCHEDULER_REPLACEMENT_FAILED in assessment.blockers
    assert RecoveryBlockerCode.SCHEDULER_NOT_INDEPENDENT not in assessment.blockers


def test_cross_leg_duplicate_receipt_is_not_misclassified_as_identity_reuse() -> None:
    """Reusing an evidence receipt across legs is not scheduler-instance reuse."""
    request = _request()
    general = _scheduler(request, SchedulerRole.GENERAL, 30)
    duplicate_receipt = replace(
        general,
        reverse=replace(
            general.reverse,
            safe_checkpoint_reference=general.forward.safe_checkpoint_reference,
        ),
    )
    assessment = assess_local_recovery_contract(
        request,
        _sql(request),
        _vault(request),
        (duplicate_receipt, _scheduler(request, SchedulerRole.PROMOTION, 80)),
    )

    assert RecoveryBlockerCode.SCHEDULER_REPLACEMENT_FAILED in assessment.blockers
    assert RecoveryBlockerCode.SCHEDULER_NOT_INDEPENDENT not in assessment.blockers


@pytest.mark.parametrize(
    "change",
    [
        "same_lineage",
        "duplicate_fence_receipt",
        "empty_effect_receipts",
        "history_resumed",
        "reverse_instance_drift",
        "hub_drift",
    ],
)
def test_scheduler_relationship_drift_is_withheld(change: SchedulerChange) -> None:
    """Breaking same-role forward/reverse replacement must not be treated as failover proof."""
    request = _request()
    assessment = assess_local_recovery_contract(
        request,
        _sql(request),
        _vault(request),
        (
            _mutate_scheduler(change, _scheduler(request, SchedulerRole.GENERAL, 30)),
            _scheduler(request, SchedulerRole.PROMOTION, 80),
        ),
    )
    assert assessment.scheduler_result is RecoveryDimensionResult.WITHHELD
    assert RecoveryBlockerCode.SCHEDULER_REPLACEMENT_FAILED in assessment.blockers


@pytest.mark.parametrize(
    "change",
    ["cross_role", "history_copied", "reverse_lineage_drift"],
)
def test_scheduler_cross_role_history_and_reverse_proofs_are_exact(
    change: SchedulerChange,
) -> None:
    """Cross-role, copied-history, missing denial, and reverse-lineage drift all withhold."""
    request = _request()
    assessment = assess_local_recovery_contract(
        request,
        _sql(request),
        _vault(request),
        (
            _mutate_scheduler(change, _scheduler(request, SchedulerRole.GENERAL, 30)),
            _scheduler(request, SchedulerRole.PROMOTION, 80),
        ),
    )
    assert assessment.scheduler_result is RecoveryDimensionResult.WITHHELD
    assert RecoveryBlockerCode.SCHEDULER_REPLACEMENT_FAILED in assessment.blockers


def test_scheduler_missing_old_resumption_denial_withholds() -> None:
    """A missing old-lineage denial receipt cannot be reconstructed from other receipts."""
    request = _request()
    general = _scheduler(request, SchedulerRole.GENERAL, 30)
    object.__setattr__(general.forward, "old_lineage_resumption_denied_receipt", None)
    assessment = assess_local_recovery_contract(
        request,
        _sql(request),
        _vault(request),
        (general, _scheduler(request, SchedulerRole.PROMOTION, 80)),
    )
    assert RecoveryBlockerCode.SCHEDULER_REPLACEMENT_FAILED in assessment.blockers


def test_one_role_cannot_stand_for_both_scheduler_roles() -> None:
    """Dropping promotion evidence must retain a specific missing-role blocker."""
    request = _request()
    assessment = assess_local_recovery_contract(
        request, _sql(request), _vault(request), (_scheduler(request, SchedulerRole.GENERAL, 30),)
    )
    assert RecoveryBlockerCode.SCHEDULER_ROLE_MISSING in assessment.blockers
    assert assessment.scheduler_result is RecoveryDimensionResult.WITHHELD


def test_reconstructed_request_cannot_mint_assessment() -> None:
    """Removing issuance tracking would let a copied frozen request masquerade as frozen input."""
    request = _request()
    with pytest.raises(RecoveryProofError) as raised:
        assess_local_recovery_contract(
            replace(request),
            _sql(request),
            _vault(request),
            (
                _scheduler(request, SchedulerRole.GENERAL, 30),
                _scheduler(request, SchedulerRole.PROMOTION, 80),
            ),
        )
    assert raised.value.code is RecoveryProofErrorCode.INPUT_INVALID
    assert raised.value.args == (RecoveryProofErrorCode.INPUT_INVALID.value,)


def test_copy_and_deepcopy_of_frozen_request_cannot_mint_assessment() -> None:
    """Copying a request must not recreate its process-local issuance witness."""
    request = _request()
    for reconstructed in (copy(request), deepcopy(request)):
        with pytest.raises(RecoveryProofError) as raised:
            assess_local_recovery_contract(
                reconstructed,
                _sql(request),
                _vault(request),
                (
                    _scheduler(request, SchedulerRole.GENERAL, 30),
                    _scheduler(request, SchedulerRole.PROMOTION, 80),
                ),
            )
        assert raised.value.code is RecoveryProofErrorCode.INPUT_INVALID


def test_ordinary_mutation_failure_is_cause_free_and_sanitized() -> None:
    """An ordinary hostile value must not leak its message, cause, or context."""
    request = _request()
    object.__setattr__(request, "vault_package_receipt", RuntimeError("secret evidence payload"))
    with pytest.raises(RecoveryProofError) as raised:
        assess_local_recovery_contract(
            request,
            _sql(_request()),
            _vault(_request()),
            (_scheduler(_request(), SchedulerRole.GENERAL, 30),),
        )
    assert raised.value.code is RecoveryProofErrorCode.INPUT_INVALID
    assert raised.value.args == (RecoveryProofErrorCode.INPUT_INVALID.value,)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_refingerprinted_frozen_receipt_cannot_mint_an_assessment() -> None:
    """Changing one recovery-manifest fingerprint after freezing invalidates the request."""
    request = _request()
    object.__setattr__(
        request.vault_package_receipt.recovery_manifest, "fingerprint", _fingerprint(99)
    )
    with pytest.raises(RecoveryProofError) as raised:
        assess_local_recovery_contract(
            request,
            _sql(_request()),
            _vault(_request()),
            (_scheduler(_request(), SchedulerRole.GENERAL, 30),),
        )
    assert raised.value.code is RecoveryProofErrorCode.INPUT_INVALID


def test_scalar_base_exception_remains_visible() -> None:
    """A BaseException in an observation scalar must never be normalized to withholding."""
    request = _request()
    sql = _sql(request)
    object.__setattr__(sql, "source_database_identity", SystemExit(7))
    with pytest.raises(SystemExit):
        assess_local_recovery_contract(
            request,
            sql,
            _vault(request),
            (
                _scheduler(request, SchedulerRole.GENERAL, 30),
                _scheduler(request, SchedulerRole.PROMOTION, 80),
            ),
        )


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(7)])
def test_class_valued_base_exceptions_remain_visible(failure: BaseException) -> None:
    """Class-valued non-Exception failures must not become withheld evidence."""
    request = _request()
    with pytest.raises(type(failure)):
        assess_local_recovery_contract(
            request,
            cast("SQLRestoreObservation", failure),
            _vault(request),
            (
                _scheduler(request, SchedulerRole.GENERAL, 30),
                _scheduler(request, SchedulerRole.PROMOTION, 80),
            ),
        )


def test_custom_class_valued_base_exception_remains_visible() -> None:
    """A custom non-Exception control flow object must stay observable at the boundary."""

    class StopRecovery(BaseException):
        pass

    request = _request()
    with pytest.raises(StopRecovery):
        assess_local_recovery_contract(
            request,
            _sql(request),
            cast("VaultRestoreObservation", StopRecovery()),
            (
                _scheduler(request, SchedulerRole.GENERAL, 30),
                _scheduler(request, SchedulerRole.PROMOTION, 80),
            ),
        )


def test_tuple_class_valued_base_exception_remains_visible() -> None:
    """A Scheduler tuple member carrying SystemExit must not become a withheld leg."""
    request = _request()
    with pytest.raises(SystemExit):
        assess_local_recovery_contract(
            request,
            _sql(request),
            _vault(request),
            cast("tuple[SchedulerReplacementObservation, ...]", (SystemExit(7),)),
        )


class _StopRecovery(BaseException):
    """Non-Exception control flow used to prove public field polarity."""


def _nested_failure_inputs(  # noqa: C901, PLR0912
    position: str, failure: BaseException
) -> tuple[
    RecoveryContractRequest,
    SQLRestoreObservation,
    VaultRestoreObservation,
    tuple[SchedulerReplacementObservation, ...],
]:
    request = _request()
    sql = _sql(request)
    vault = _vault(request)
    schedulers = (
        _scheduler(request, SchedulerRole.GENERAL, 30),
        _scheduler(request, SchedulerRole.PROMOTION, 80),
    )
    general = schedulers[0]
    forward = general.forward
    row = vault.restored_objects[0]
    if position == "request_migration_tuple":
        object.__setattr__(request, "migration_prefix", failure)
    elif position == "request_receipt":
        object.__setattr__(request, "vault_package_receipt", failure)
    elif position == "receipt_manifest_reference":
        object.__setattr__(request.vault_package_receipt, "recovery_manifest", failure)
    elif position == "receipt_reference_fingerprint":
        object.__setattr__(request.vault_package_receipt.recovery_manifest, "fingerprint", failure)
    elif position == "sql_backup_reference":
        object.__setattr__(sql, "backup_reference", failure)
    elif position == "sql_reference_fingerprint":
        object.__setattr__(sql.backup_reference, "fingerprint", failure)
    elif position == "probe_kind":
        object.__setattr__(sql.least_privilege_probes[0], "kind", failure)
    elif position == "probe_result":
        object.__setattr__(sql.least_privilege_probes[0], "result", failure)
    elif position == "vault_source_key":
        object.__setattr__(row, "source_logical_key", failure)
    elif position == "vault_source_version":
        object.__setattr__(row, "source_version", failure)
    elif position == "vault_target_identity":
        object.__setattr__(row, "target_identity", failure)
    elif position == "vault_target_version":
        object.__setattr__(row, "target_version", failure)
    elif position == "scheduler_observation_role":
        object.__setattr__(general, "role", failure)
    elif position == "scheduler_leg_role":
        object.__setattr__(forward, "role", failure)
    elif position == "scheduler_leg_hubs":
        object.__setattr__(forward, "hubs", failure)
    elif position == "scheduler_leg_mode":
        object.__setattr__(forward, "mode", failure)
    elif position == "scheduler_receipt":
        object.__setattr__(forward, "safe_checkpoint_reference", failure)
    elif position == "scheduler_receipt_fingerprint":
        object.__setattr__(forward.safe_checkpoint_reference, "fingerprint", failure)
    else:
        raise AssertionError(position)
    return request, sql, vault, schedulers


_NESTED_FIELD_POSITIONS = (
    "request_migration_tuple",
    "request_receipt",
    "receipt_manifest_reference",
    "receipt_reference_fingerprint",
    "sql_backup_reference",
    "sql_reference_fingerprint",
    "probe_kind",
    "probe_result",
    "vault_source_key",
    "vault_source_version",
    "vault_target_identity",
    "vault_target_version",
    "scheduler_observation_role",
    "scheduler_leg_role",
    "scheduler_leg_hubs",
    "scheduler_leg_mode",
    "scheduler_receipt",
    "scheduler_receipt_fingerprint",
)


@pytest.mark.parametrize("position", _NESTED_FIELD_POSITIONS)
@pytest.mark.parametrize("failure", [SystemExit(7), KeyboardInterrupt(), _StopRecovery()])
def test_all_nested_public_field_categories_keep_non_exception_control_flow_visible(
    position: str, failure: BaseException
) -> None:
    """Every nested enum, class, scalar, tuple, and reference has identical polarity."""
    inputs = _nested_failure_inputs(position, failure)
    with pytest.raises(type(failure)):
        assess_local_recovery_contract(*inputs)


@pytest.mark.parametrize("position", _NESTED_FIELD_POSITIONS)
def test_all_nested_public_field_categories_close_ordinary_exceptions(
    position: str,
) -> None:
    """An ordinary exception value never becomes a quiet withheld assessment or leaks details."""
    inputs = _nested_failure_inputs(position, RuntimeError("secret nested failure"))
    with pytest.raises(RecoveryProofError) as raised:
        assess_local_recovery_contract(*inputs)
    assert raised.value.code is RecoveryProofErrorCode.INPUT_INVALID
    assert "secret nested failure" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_class_valued_ordinary_exception_is_a_cause_free_closed_error() -> None:
    """A RuntimeError value cannot silently turn a malformed observation into withholding."""
    request = _request()
    with pytest.raises(RecoveryProofError) as raised:
        assess_local_recovery_contract(
            request,
            cast("SQLRestoreObservation", RuntimeError("secret raw message")),
            _vault(request),
            (
                _scheduler(request, SchedulerRole.GENERAL, 30),
                _scheduler(request, SchedulerRole.PROMOTION, 80),
            ),
        )
    assert raised.value.code is RecoveryProofErrorCode.INPUT_INVALID
    assert "secret raw message" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_terminal_assessment_cannot_be_directly_constructed_or_replaced() -> None:
    """Exposing a terminal constructor would allow false local-proof claims."""
    with pytest.raises(RecoveryProofError) as direct:
        HKV1RecoveryContractAssessment()
    assert direct.value.code is RecoveryProofErrorCode.ISSUER_REQUIRED
    with pytest.raises(RecoveryProofError) as copied:
        replace(_complete_assessment())
    assert copied.value.code is RecoveryProofErrorCode.ISSUER_REQUIRED


def test_secret_shaped_and_hostile_values_are_sanitized() -> None:
    """Accepting free text or evaluating a hostile subclass would broaden evidence inputs."""
    with pytest.raises(RecoveryProofError) as secret:
        RecoveryEvidenceReference("https://example.invalid/token", _fingerprint(1))
    assert secret.value.code is RecoveryProofErrorCode.INPUT_INVALID
    with pytest.raises(TypeError):

        class ExplosiveReference(RecoveryEvidenceReference):  # pyright: ignore[reportUnusedClass]
            def __getattribute__(self, name: str) -> object:
                raise RuntimeError(name)


def test_base_exceptions_remain_visible() -> None:
    """Catching BaseException would hide an operator interrupt during validation."""
    request = _request()
    object.__setattr__(request, "migration_prefix", KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        assess_local_recovery_contract(
            request,
            _sql(_request()),
            _vault(_request()),
            (_scheduler(_request(), SchedulerRole.GENERAL, 30),),
        )


def test_repeat_assessment_is_byte_stable() -> None:
    """Changing canonicalization or caller-owned values would change repeated output."""
    first = _complete_assessment()
    second = _complete_assessment()
    assert first.canonical_bytes == second.canonical_bytes
    assert first.fingerprint == second.fingerprint


def test_public_reference_constructor_closes_an_ordinary_exception_value() -> None:
    """A public value constructor must never expose its private traversal signal."""
    with pytest.raises(RecoveryProofError) as raised:
        RecoveryEvidenceReference(
            cast("str", RuntimeError("secret constructor payload")), _fingerprint(1)
        )

    assert raised.value.code is RecoveryProofErrorCode.INPUT_INVALID
    assert "secret constructor payload" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


_CONSTRUCTOR_FAILURE_POSITIONS = (
    "reference_scalar",
    "migration_scalar",
    "family_scalar",
    "hub_scalar",
    "hub_tuple_member",
    "probe_scalar",
    "sql_scalar",
    "sql_migration_member",
    "sql_family_member",
    "sql_probe_member",
    "vault_object_scalar",
    "vault_observation_scalar",
    "vault_observation_member",
    "scheduler_leg_scalar",
    "scheduler_hub_member",
    "scheduler_receipt_member",
    "scheduler_observation_scalar",
    "request_scalar",
    "request_migration_member",
    "request_family_member",
    "request_hub_member",
)


def _construct_with_failure(position: str, failure: BaseException) -> object:  # noqa: C901, PLR0911, PLR0912
    request = _request()
    sql = _sql(request)
    vault = _vault(request)
    scheduler = _scheduler(request, SchedulerRole.GENERAL, 30)
    if position == "reference_scalar":
        return RecoveryEvidenceReference(cast("str", failure), _fingerprint(1))
    if position == "migration_scalar":
        return MigrationReadback(cast("str", failure), _fingerprint(1))
    if position == "family_scalar":
        return RegisterFamilyReadback(cast("str", failure), 1, _fingerprint(1))
    if position == "hub_scalar":
        return SchedulerHubInventory(cast("SchedulerRole", failure), (_opaque(1),))
    if position == "hub_tuple_member":
        return SchedulerHubInventory(SchedulerRole.GENERAL, (cast("str", failure),))
    if position == "probe_scalar":
        return LeastPrivilegeProbe(
            cast("LeastPrivilegeProbeKind", failure), LeastPrivilegeProbeResult.ALLOWED
        )
    if position == "sql_scalar":
        return replace(sql, request_fingerprint=cast("str", failure))
    if position == "sql_migration_member":
        return replace(sql, source_migrations=(cast("MigrationReadback", failure),))
    if position == "sql_family_member":
        return replace(sql, restored_families=(cast("RegisterFamilyReadback", failure),))
    if position == "sql_probe_member":
        return replace(sql, least_privilege_probes=(cast("LeastPrivilegeProbe", failure),))
    if position == "vault_object_scalar":
        return replace(vault.restored_objects[0], source_version=cast("str", failure))
    if position == "vault_observation_scalar":
        return replace(vault, request_fingerprint=cast("str", failure))
    if position == "vault_observation_member":
        return replace(vault, restored_objects=(cast("VaultRestoredObject", failure),))
    if position == "scheduler_leg_scalar":
        return replace(scheduler.forward, role=cast("SchedulerRole", failure))
    if position == "scheduler_hub_member":
        return replace(scheduler.forward, hubs=(cast("str", failure),))
    if position == "scheduler_receipt_member":
        return replace(
            scheduler.forward,
            effect_reconciliation_receipts=(cast("RecoveryEvidenceReference", failure),),
        )
    if position == "scheduler_observation_scalar":
        return replace(scheduler, role=cast("SchedulerRole", failure))
    if position == "request_scalar":
        return replace(request, primary_vault_identity=cast("str", failure))
    if position == "request_migration_member":
        return replace(request, migration_prefix=(cast("MigrationReadback", failure),))
    if position == "request_family_member":
        return replace(request, register_families=(cast("RegisterFamilyReadback", failure),))
    if position == "request_hub_member":
        return replace(request, scheduler_hubs=(cast("SchedulerHubInventory", failure),))
    raise AssertionError(position)


@pytest.mark.parametrize("position", _CONSTRUCTOR_FAILURE_POSITIONS)
def test_every_public_value_constructor_closes_ordinary_exception_values(position: str) -> None:
    """No direct or tuple-member ordinary exception may escape a public constructor."""
    with pytest.raises(RecoveryProofError) as raised:
        _construct_with_failure(position, RuntimeError("secret constructor payload"))

    assert raised.value.code is RecoveryProofErrorCode.INPUT_INVALID
    assert "secret constructor payload" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert type(raised.value).__name__ != "_EmbeddedOrdinaryFailure"


@pytest.mark.parametrize("position", _CONSTRUCTOR_FAILURE_POSITIONS)
@pytest.mark.parametrize("failure_type", [SystemExit, KeyboardInterrupt, _StopRecovery])
def test_every_public_value_constructor_preserves_non_exception_base_exceptions(
    position: str, failure_type: type[BaseException]
) -> None:
    """Every direct and tuple-member control-flow value retains its public polarity."""
    failure = failure_type()
    with pytest.raises(failure_type):
        _construct_with_failure(position, failure)


@pytest.mark.parametrize("receipt_member", ["entry", "copy"])
def test_receipt_tuple_member_base_exception_is_visible_before_field_access(
    receipt_member: str,
) -> None:
    """A receipt member carrying control flow must not be converted from AttributeError."""
    request = _request()
    if receipt_member == "entry":
        object.__setattr__(request.vault_package_receipt.manifest, "entries", (SystemExit(7),))
    else:
        object.__setattr__(request.vault_package_receipt, "copies", (SystemExit(7),))

    with pytest.raises(SystemExit):
        assess_local_recovery_contract(
            request,
            _sql(_request()),
            _vault(_request()),
            (_scheduler(_request(), SchedulerRole.GENERAL, 30),),
        )


@pytest.mark.parametrize("receipt_member", ["entry", "copy"])
def test_receipt_tuple_member_ordinary_exception_is_closed_before_field_access(
    receipt_member: str,
) -> None:
    """An ordinary receipt-member failure must close without leaking its private signal."""
    request = _request()
    failure = RuntimeError("secret receipt-member payload")
    if receipt_member == "entry":
        object.__setattr__(request.vault_package_receipt.manifest, "entries", (failure,))
    else:
        object.__setattr__(request.vault_package_receipt, "copies", (failure,))

    with pytest.raises(RecoveryProofError) as raised:
        assess_local_recovery_contract(
            request,
            _sql(_request()),
            _vault(_request()),
            (_scheduler(_request(), SchedulerRole.GENERAL, 30),),
        )
    assert raised.value.code is RecoveryProofErrorCode.INPUT_INVALID
    assert "secret receipt-member payload" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert type(raised.value).__name__ != "_EmbeddedOrdinaryFailure"


def _local_request_and_configuration(
    tmp_path: Path,
) -> tuple[RecoveryContractRequest, LocalRecoveryConfiguration]:
    primary_root = tmp_path / "primary"
    recovery_root = tmp_path / "recovery"
    primary = LocalImmutableVault(primary_root, VaultName.PRIMARY)
    recovery = LocalImmutableVault(recovery_root, VaultName.RECOVERY)
    retention = RetentionProfile("proof", "2030-01-01T00:00:00Z")
    writer = ManifestLastPackageWriter(primary)
    writer.stage_content(_descriptor(retention), b"retained recovery input")
    writer.commit_manifest(
        package_kind="proof",
        package_id="pkg_" + "5" * 48,
        observation_id="obs_" + "4" * 48,
        retention=retention,
    )
    receipt = writer.finalize_recovery(RecoveryCopier(primary, recovery), retention)
    request = freeze_local_recovery_contract(
        (MigrationReadback("m_000001", _fingerprint(1)),),
        (RegisterFamilyReadback("events", 1, _fingerprint(2)),),
        _reference(3),
        _reference(4),
        _reference(5),
        _reference(6),
        receipt,
        _opaque(7),
        _opaque(8),
        (
            SchedulerHubInventory(SchedulerRole.GENERAL, (_opaque(9),)),
            SchedulerHubInventory(SchedulerRole.PROMOTION, (_opaque(10),)),
        ),
    )
    sql_snapshot = tmp_path / "sql-backup.json"
    sql_snapshot.write_bytes(build_local_sql_snapshot(request, _opaque(11)))
    scheduler_root = tmp_path / "scheduler-input"
    scheduler_root.mkdir()
    for role, number in ((SchedulerRole.GENERAL, 20), (SchedulerRole.PROMOTION, 30)):
        checkpoint = f"{role.value} retained checkpoint".encode()
        stem = role.value.lower()
        (scheduler_root / f"{stem}-checkpoint.bin").write_bytes(checkpoint)
        (scheduler_root / f"{stem}.json").write_bytes(
            build_local_scheduler_snapshot(
                request,
                role,
                _opaque(number),
                _opaque(number + 1),
                checkpoint,
            )
        )
    workspace = tmp_path / "disposable"
    workspace.mkdir()
    output_root = tmp_path / "results"
    output_root.mkdir()
    configuration = LocalRecoveryConfiguration(
        _opaque(40),
        request.fingerprint,
        workspace,
        sql_snapshot,
        primary_root,
        recovery_root,
        scheduler_root,
        output_root / "recovery.json",
    )
    return request, configuration


def _local_adapters() -> LocalRecoveryAdapters:
    return LocalRecoveryAdapters(
        FilesystemSQLRecoveryAdapter(),
        FilesystemVaultRecoveryAdapter(),
        FilesystemSchedulerRecoveryAdapter(),
    )


def test_preflight_is_default_read_only_and_exposes_only_generated_targets(
    tmp_path: Path,
) -> None:
    """Default invocation validates explicit inputs without creating disposable state."""
    _request_value, configuration = _local_request_and_configuration(tmp_path)

    first = run_local_recovery(configuration)
    second = run_local_recovery(configuration)

    assert first.status is LocalRecoveryStatus.PREFLIGHT_READY
    assert first.mode is LocalRecoveryMode.PREFLIGHT
    assert first.canonical_bytes == second.canonical_bytes
    assert first.live_recovery_proved is False
    assert tuple(configuration.workspace_root.iterdir()) == ()
    targets = derive_local_recovery_targets(configuration)
    assert targets.sql_database_name.startswith("asklegal_recovery_sql_")
    assert targets.vault_directory_name.startswith("asklegal-recovery-vault-")
    assert targets.scheduler_directory_name.startswith("asklegal-recovery-scheduler-")


def test_execution_requires_explicit_authority_and_all_composed_ports(
    tmp_path: Path,
) -> None:
    """Neither an omitted authority nor omitted ports may create local state."""
    request, configuration = _local_request_and_configuration(tmp_path)

    unauthorized = run_local_recovery(
        configuration,
        mode=LocalRecoveryMode.EXECUTE_LOCAL_PROTOTYPE,
        request=request,
        adapters=_local_adapters(),
    )
    uncomposed = run_local_recovery(
        configuration,
        mode=LocalRecoveryMode.EXECUTE_LOCAL_PROTOTYPE,
        execution_authorized=True,
    )

    assert unauthorized.status is LocalRecoveryStatus.NOT_READY
    assert unauthorized.blockers == ("EXECUTION_AUTHORITY_REQUIRED",)
    assert uncomposed.blockers == ("EXECUTION_ADAPTERS_NOT_COMPOSED",)
    assert tuple(configuration.workspace_root.iterdir()) == ()


def test_local_filesystem_restore_readback_and_two_role_replay_are_restart_safe(
    tmp_path: Path,
) -> None:
    """Contained adapters reread every local result and adopt only exact repeat bytes."""
    request, configuration = _local_request_and_configuration(tmp_path)

    first = run_local_recovery(
        configuration,
        mode=LocalRecoveryMode.EXECUTE_LOCAL_PROTOTYPE,
        execution_authorized=True,
        request=request,
        adapters=_local_adapters(),
    )
    second = run_local_recovery(
        configuration,
        mode=LocalRecoveryMode.EXECUTE_LOCAL_PROTOTYPE,
        execution_authorized=True,
        request=request,
        adapters=_local_adapters(),
    )

    assert first.status is LocalRecoveryStatus.LOCAL_PROTOTYPE_PROVED
    assert first.local_contract_proved is True
    assert first.live_recovery_proved is False
    assert first.blockers == (
        RecoveryBlockerCode.SCHEDULER_REPLACEMENT_UNRUN.value,
        RecoveryBlockerCode.SQL_ENGINE_RESTORE_UNRUN.value,
        RecoveryBlockerCode.VAULT_CLEAN_ROOM_RESTORE_UNRUN.value,
    )
    assert second.canonical_bytes == first.canonical_bytes
    targets = derive_local_recovery_targets(configuration)
    assert sorted(path.name for path in configuration.workspace_root.iterdir()) == sorted(
        (
            targets.scheduler_directory_name,
            targets.sql_database_name,
            targets.vault_directory_name,
        )
    )
    scheduler_files = configuration.workspace_root / targets.scheduler_directory_name
    assert sorted(path.name for path in scheduler_files.iterdir()) == [
        "general-forward.json",
        "general-reverse.json",
        "promotion-forward.json",
        "promotion-reverse.json",
    ]


def test_scheduler_replacement_identities_bind_the_exact_operation(
    tmp_path: Path,
) -> None:
    """Two operations over one request cannot reuse replacement lineages or receipts."""
    request, first_configuration = _local_request_and_configuration(tmp_path)
    second_configuration = replace(first_configuration, operation_id=_opaque(41))
    adapter = FilesystemSchedulerRecoveryAdapter()

    first = adapter.replace_and_replay(
        request,
        first_configuration,
        derive_local_recovery_targets(first_configuration),
    )
    second = adapter.replace_and_replay(
        request,
        second_configuration,
        derive_local_recovery_targets(second_configuration),
    )

    assert first[0].forward.replacement_instance_identity != (
        second[0].forward.replacement_instance_identity
    )
    assert first[0].forward.recovery_lineage_identity != second[0].forward.recovery_lineage_identity
    assert first[0].forward.safe_checkpoint_reference != second[0].forward.safe_checkpoint_reference


def test_adapters_reject_caller_selected_disposable_target_names(tmp_path: Path) -> None:
    """Direct adapter use cannot bypass deterministic target-name generation."""
    request, configuration = _local_request_and_configuration(tmp_path)
    targets = replace(
        derive_local_recovery_targets(configuration),
        sql_database_name="caller-selected-target",
    )

    with pytest.raises(ValueError, match="LOCAL_RECOVERY_TARGET_INVALID"):
        FilesystemSQLRecoveryAdapter().restore_and_readback(request, configuration, targets)

    assert not (configuration.workspace_root / "caller-selected-target").exists()


def test_checkpoint_or_snapshot_drift_withholds_without_claiming_local_proof(
    tmp_path: Path,
) -> None:
    """A changed retained checkpoint cannot be replayed under its prior fingerprint."""
    request, configuration = _local_request_and_configuration(tmp_path)
    (configuration.scheduler_snapshot_root / "general-checkpoint.bin").write_bytes(b"drift")

    result = run_local_recovery(
        configuration,
        mode=LocalRecoveryMode.EXECUTE_LOCAL_PROTOTYPE,
        execution_authorized=True,
        request=request,
        adapters=_local_adapters(),
    )

    assert result.status is LocalRecoveryStatus.NOT_READY
    assert result.local_contract_proved is False
    assert result.live_recovery_proved is False
    assert result.blockers == ("LOCAL_RECOVERY_INPUT_INVALID",)


def test_missing_or_symlinked_local_input_fails_preflight_before_target_creation(
    tmp_path: Path,
) -> None:
    """Absent and aliased inputs remain exact NOT_READY facts without effects."""
    _request_value, configuration = _local_request_and_configuration(tmp_path)
    configuration.sql_snapshot_path.unlink()
    configuration.sql_snapshot_path.symlink_to(tmp_path / "missing")

    result = run_local_recovery(configuration)

    assert result.status is LocalRecoveryStatus.NOT_READY
    assert result.blockers == ("SQL_INPUT_NOT_READY",)
    assert tuple(configuration.workspace_root.iterdir()) == ()


def test_noncanonical_or_semantically_drifted_input_never_reports_preflight_ready(
    tmp_path: Path,
) -> None:
    """Path existence alone cannot turn an unvalidated snapshot into readiness."""
    _request_value, configuration = _local_request_and_configuration(tmp_path)
    parsed = json.loads(configuration.sql_snapshot_path.read_bytes())
    parsed["request_fingerprint"] = _fingerprint(999)
    configuration.sql_snapshot_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

    result = run_local_recovery(configuration)

    assert result.status is LocalRecoveryStatus.NOT_READY
    assert result.blockers == ("LOCAL_RECOVERY_INPUT_INVALID",)
    assert tuple(configuration.workspace_root.iterdir()) == ()


def test_cli_defaults_to_preflight_and_execution_stays_uncomposed_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI writes canonical preflight output but never invents live adapters."""
    _request_value, configuration = _local_request_and_configuration(tmp_path)
    arguments = [
        "recovery",
        "--operation-id",
        configuration.operation_id,
        "--request-fingerprint",
        configuration.request_fingerprint,
        "--workspace-root",
        str(configuration.workspace_root),
        "--sql-snapshot",
        str(configuration.sql_snapshot_path),
        "--primary-vault-root",
        str(configuration.primary_vault_root),
        "--recovery-vault-root",
        str(configuration.recovery_vault_root),
        "--scheduler-snapshot-root",
        str(configuration.scheduler_snapshot_root),
        "--output",
        str(configuration.output_path),
    ]
    monkeypatch.setattr("sys.argv", arguments)
    main()

    raw = configuration.output_path.read_bytes()
    document = json.loads(raw)
    assert raw == json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    assert document["status"] == LocalRecoveryStatus.PREFLIGHT_READY.value
    assert capsys.readouterr().out == "PREFLIGHT_READY\n"

    monkeypatch.setattr(
        "sys.argv",
        [
            *arguments,
            "--mode",
            LocalRecoveryMode.EXECUTE_LOCAL_PROTOTYPE.value,
            "--authorize-local-execution",
        ],
    )
    with pytest.raises(SystemExit) as unavailable:
        main()
    document = json.loads(configuration.output_path.read_bytes())
    assert unavailable.value.code == 2
    assert document["status"] == LocalRecoveryStatus.NOT_READY.value
    assert document["blockers"] == ["EXECUTION_ADAPTERS_NOT_COMPOSED"]
    assert tuple(configuration.workspace_root.iterdir()) == ()


def _live_credentials(operation_id: str) -> bytes:
    return build_live_recovery_credential_manifest(
        operation_id,
        tuple(
            SealedCredentialReference(
                credential_id,
                f"/run/credentials/asklegal/{credential_id.casefold()}",
                _fingerprint(index + 700),
            )
            for index, credential_id in enumerate(
                (
                    "PRIMARY_VAULT_RECOVERY_READER",
                    "RECOVERY_VAULT_RECOVERY_READER",
                    "SCHEDULER_GENERAL_RECOVERY_ADMIN",
                    "SCHEDULER_PROMOTION_RECOVERY_ADMIN",
                    "SQL_SERVER_RECOVERY_ADMIN",
                )
            )
        ),
    )


def _sealed_document(body: dict[str, object]) -> bytes:
    unsigned = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    document = {**body, "fingerprint": f"sha256:{sha256(unsigned).hexdigest()}"}
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _live_authority(plan_bytes: bytes) -> bytes:
    plan = json.loads(plan_bytes)
    return _sealed_document(
        {
            "authority_id": "user-recovery-drill-001",
            "authorized_steps": [step.value for step in LiveRecoveryStep],
            "operation_id": plan["operation_id"],
            "plan_fingerprint": plan["fingerprint"],
            "schema": "asklegal.hk-v1-live-recovery-authority/v1",
            "targets_fingerprint": plan["targets_fingerprint"],
        }
    )


class _LiveRecoveryPort:
    def __init__(self, lost_ack_step: LiveRecoveryStep | None = None) -> None:
        self.calls: list[tuple[str, LiveRecoveryStep]] = []
        self.completed: dict[LiveRecoveryStep, LiveRecoveryStepReceipt] = {}
        self.lost_ack_step = lost_ack_step
        self.lost = False

    def reconcile(
        self,
        step: LiveRecoveryStep,
        plan: object,
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt | None:
        assert len(credentials) == 5
        del plan
        self.calls.append(("reconcile", step))
        return self.completed.get(step)

    def execute(
        self,
        step: LiveRecoveryStep,
        plan: object,
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt:
        assert len(credentials) == 5
        assert type(plan) is dict
        raw_steps = cast("list[dict[str, object]]", plan["steps"])
        target = next(item["target_identity"] for item in raw_steps if item["step"] == step.value)
        assert type(target) is str
        effect = f"sha256:{sha256(step.value.encode()).hexdigest()}"
        receipt = LiveRecoveryStepReceipt(
            step,
            cast("str", plan["fingerprint"]),
            target,
            effect,
            effect,
        )
        self.calls.append(("execute", step))
        self.completed[step] = receipt
        if step is self.lost_ack_step and not self.lost:
            self.lost = True
            raise LiveRecoveryAcknowledgementLost
        return receipt


def _live_plan_inputs(
    tmp_path: Path,
) -> tuple[bytes, bytes, Path]:
    request, configuration = _local_request_and_configuration(tmp_path)
    credentials = _live_credentials(configuration.operation_id)
    plan = build_live_recovery_plan(request, configuration, credentials)
    state_root = tmp_path / "live-recovery-state"
    state_root.mkdir()
    return plan, credentials, state_root


def test_live_recovery_request_survives_process_restart_exactly(tmp_path: Path) -> None:
    """A canonical retained request can reissue the guarded contract after restart."""
    request, configuration = _local_request_and_configuration(tmp_path)
    raw = build_live_recovery_request(request)

    reconstructed = load_live_recovery_request(raw)
    credentials = _live_credentials(configuration.operation_id)

    assert reconstructed is not request
    assert reconstructed.fingerprint == request.fingerprint
    assert build_live_recovery_request(reconstructed) == raw
    assert build_live_recovery_plan(reconstructed, configuration, credentials) == (
        build_live_recovery_plan(request, configuration, credentials)
    )


def test_live_recovery_request_rejects_receipt_or_outer_drift(tmp_path: Path) -> None:
    """Neither a resealed vault ref nor an unsealed outer change can reissue a request."""
    request, _configuration = _local_request_and_configuration(tmp_path)
    raw = build_live_recovery_request(request)
    unsealed = json.loads(raw)
    unsealed["request_fingerprint"] = _fingerprint(999)
    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_RECOVERY_REQUEST_INVALID"):
        load_live_recovery_request(
            json.dumps(unsealed, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )

    resealed = json.loads(raw)
    resealed["vault_package_receipt"]["copies"][0]["recovery"]["fingerprint"] = _fingerprint(998)
    unsigned = dict(resealed)
    unsigned.pop("fingerprint")
    unsigned_bytes = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    resealed["fingerprint"] = f"sha256:{sha256(unsigned_bytes).hexdigest()}"
    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_RECOVERY_REQUEST_INVALID"):
        load_live_recovery_request(
            json.dumps(resealed, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )


def test_live_plan_cli_consumes_retained_request_without_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """PLAN_LIVE freezes exact paths and references but never calls an effect port."""
    request, configuration = _local_request_and_configuration(tmp_path)
    request_path = tmp_path / "live-request.json"
    credential_path = tmp_path / "live-credentials.json"
    mapping_path = tmp_path / "sql-backup-paths.json"
    request_path.write_bytes(build_live_recovery_request(request))
    credential_path.write_bytes(_live_credentials(configuration.operation_id))
    mapping_path.write_bytes(
        build_sql_backup_path_manifest(
            (
                SQLBackupPathBinding(
                    request.sql_backup_reference.evidence_id,
                    request.sql_backup_reference.fingerprint,
                    "/var/opt/mssql/backup/asklegal-operational.bak",
                ),
            )
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "recovery",
            "--operation-id",
            configuration.operation_id,
            "--request-fingerprint",
            configuration.request_fingerprint,
            "--workspace-root",
            str(configuration.workspace_root),
            "--sql-snapshot",
            str(configuration.sql_snapshot_path),
            "--primary-vault-root",
            str(configuration.primary_vault_root),
            "--recovery-vault-root",
            str(configuration.recovery_vault_root),
            "--scheduler-snapshot-root",
            str(configuration.scheduler_snapshot_root),
            "--output",
            str(configuration.output_path),
            "--mode",
            LocalRecoveryMode.PLAN_LIVE.value,
            "--live-request",
            str(request_path),
            "--live-credential-manifest",
            str(credential_path),
            "--sql-backup-path-manifest",
            str(mapping_path),
        ],
    )

    main()

    plan = json.loads(configuration.output_path.read_bytes())
    assert plan["schema"] == "asklegal.hk-v1-live-recovery-plan/v1"
    assert plan["request_fingerprint"] == request.fingerprint
    assert tuple(configuration.workspace_root.iterdir()) == ()
    assert capsys.readouterr().out == "LIVE_RECOVERY_PLAN_READY\n"


def test_live_plan_is_exact_reference_only_and_deterministic(tmp_path: Path) -> None:
    """Planning binds every retained input and sealed credential ref without effects."""
    request, configuration = _local_request_and_configuration(tmp_path)
    credentials = _live_credentials(configuration.operation_id)
    first = build_live_recovery_plan(request, configuration, credentials)
    second = build_live_recovery_plan(request, configuration, credentials)

    assert first == second
    document = json.loads(first)
    assert document["schema"] == "asklegal.hk-v1-live-recovery-plan/v1"
    assert [item["step"] for item in document["steps"]] == [step.value for step in LiveRecoveryStep]
    assert b"secret" not in first
    assert b"/run/credentials/" not in first
    assert tuple(configuration.workspace_root.iterdir()) == ()


def test_live_plan_binds_exact_sql_backup_path_manifest_without_exposing_path(
    tmp_path: Path,
) -> None:
    """Detached authority covers the mapping bytes while the plan omits its host path."""
    request, configuration = _local_request_and_configuration(tmp_path)
    credentials = _live_credentials(configuration.operation_id)
    mapping = build_sql_backup_path_manifest(
        (
            SQLBackupPathBinding(
                request.sql_backup_reference.evidence_id,
                request.sql_backup_reference.fingerprint,
                "/var/opt/mssql/backup/asklegal-operational.bak",
            ),
        )
    )

    plan = build_live_recovery_plan(
        request,
        configuration,
        credentials,
        sql_backup_path_manifest=mapping,
    )
    document = json.loads(plan)

    canonical_mapping = json.dumps(
        json.loads(mapping), sort_keys=True, separators=(",", ":")
    ).encode()
    assert document["sql"]["backup_path_manifest_fingerprint"] == (
        f"sha256:{sha256(canonical_mapping).hexdigest()}"
    )
    assert b"/var/opt/mssql/backup" not in plan
    assert b"/run/credentials/" not in plan


def test_live_execution_requires_exact_detached_authority_before_effect(
    tmp_path: Path,
) -> None:
    """A missing or drifted authority cannot reach even read-only reconciliation."""
    plan, credentials, state_root = _live_plan_inputs(tmp_path)
    port = _LiveRecoveryPort()
    adapters = LiveRecoveryExecutionAdapters(port, port, port)

    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_RECOVERY_AUTHORITY_INVALID"):
        execute_live_recovery(plan, b"{}\n", credentials, state_root, adapters)

    assert port.calls == []
    assert tuple(state_root.iterdir()) == ()


def test_live_execution_rejects_credential_reference_drift_before_effect(
    tmp_path: Path,
) -> None:
    """A replaced sealed file fingerprint invalidates the already-authorized plan."""
    plan, credentials, state_root = _live_plan_inputs(tmp_path)
    values = json.loads(credentials)["credentials"]
    values[0]["fingerprint"] = _fingerprint(999)
    drifted = build_live_recovery_credential_manifest(
        cast("str", json.loads(credentials)["operation_id"]),
        tuple(
            SealedCredentialReference(
                item["credential_id"], item["sealed_path"], item["fingerprint"]
            )
            for item in values
        ),
    )
    port = _LiveRecoveryPort()

    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_RECOVERY_CREDENTIAL_INPUT_DRIFT"):
        execute_live_recovery(
            plan,
            _live_authority(plan),
            drifted,
            state_root,
            LiveRecoveryExecutionAdapters(port, port, port),
        )

    assert port.calls == []


def test_live_execution_replays_all_receipts_without_repeating_effects(tmp_path: Path) -> None:
    """Seven exact receipts survive restart and make the second execution read-only."""
    plan, credentials, state_root = _live_plan_inputs(tmp_path)
    port = _LiveRecoveryPort()
    adapters = LiveRecoveryExecutionAdapters(port, port, port)

    first = execute_live_recovery(plan, _live_authority(plan), credentials, state_root, adapters)
    call_count = len(port.calls)
    second = execute_live_recovery(plan, _live_authority(plan), credentials, state_root, adapters)

    assert first.live_recovery_proved is True
    assert len(first.receipts) == len(LiveRecoveryStep)
    assert second.canonical_bytes == first.canonical_bytes
    assert len(port.calls) == call_count


def test_lost_ack_is_reconciled_before_any_effect_retry(tmp_path: Path) -> None:
    """An ambiguous SQL acknowledgement adopts exact readback on restart."""
    plan, credentials, state_root = _live_plan_inputs(tmp_path)
    port = _LiveRecoveryPort(LiveRecoveryStep.SQL_RESTORE_READBACK)
    adapters = LiveRecoveryExecutionAdapters(port, port, port)

    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_RECOVERY_ACKNOWLEDGEMENT_LOST"):
        execute_live_recovery(plan, _live_authority(plan), credentials, state_root, adapters)
    result = execute_live_recovery(plan, _live_authority(plan), credentials, state_root, adapters)

    sql_executes = [
        call for call in port.calls if call == ("execute", LiveRecoveryStep.SQL_RESTORE_READBACK)
    ]
    assert len(sql_executes) == 1
    assert result.live_recovery_proved is True


def test_real_immutable_vault_port_reads_both_vaults_into_distinct_clean_rooms(
    tmp_path: Path,
) -> None:
    """The live vault port uses exact-version readers and verifies isolated bytes."""
    request, configuration = _local_request_and_configuration(tmp_path)
    credentials = _live_credentials(configuration.operation_id)
    plan_bytes = build_live_recovery_plan(request, configuration, credentials)
    plan = json.loads(plan_bytes)
    clean_room = tmp_path / "clean-room"
    clean_room.mkdir()
    port = ImmutableVaultLiveRecoveryPort(
        LocalImmutableVault(configuration.primary_vault_root, VaultName.PRIMARY),
        LocalImmutableVault(configuration.recovery_vault_root, VaultName.RECOVERY),
        clean_room,
    )
    references = tuple(
        SealedCredentialReference(
            value["credential_id"], value["sealed_path"], value["fingerprint"]
        )
        for value in json.loads(credentials)["credentials"]
    )

    primary = port.execute(LiveRecoveryStep.PRIMARY_VAULT_CLEAN_ROOM_READBACK, plan, references)
    recovery = port.execute(LiveRecoveryStep.RECOVERY_VAULT_CLEAN_ROOM_READBACK, plan, references)

    assert primary.effect_fingerprint == recovery.effect_fingerprint
    assert primary.target_identity != recovery.target_identity
    assert (
        port.reconcile(LiveRecoveryStep.PRIMARY_VAULT_CLEAN_ROOM_READBACK, plan, references)
        == primary
    )


def test_live_cli_requires_detached_authority_and_composed_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit live mode cannot reuse the prototype boolean authority switch."""
    request, configuration = _local_request_and_configuration(tmp_path)
    credentials = _live_credentials(configuration.operation_id)
    plan = build_live_recovery_plan(request, configuration, credentials)
    plan_path = tmp_path / "live-plan.json"
    credential_path = tmp_path / "live-credentials.json"
    authority_path = tmp_path / "live-authority.json"
    state_root = tmp_path / "live-state"
    state_root.mkdir()
    plan_path.write_bytes(plan)
    credential_path.write_bytes(credentials)
    authority_path.write_bytes(_live_authority(plan))
    arguments = [
        "recovery",
        "--operation-id",
        configuration.operation_id,
        "--request-fingerprint",
        configuration.request_fingerprint,
        "--workspace-root",
        str(configuration.workspace_root),
        "--sql-snapshot",
        str(configuration.sql_snapshot_path),
        "--primary-vault-root",
        str(configuration.primary_vault_root),
        "--recovery-vault-root",
        str(configuration.recovery_vault_root),
        "--scheduler-snapshot-root",
        str(configuration.scheduler_snapshot_root),
        "--output",
        str(configuration.output_path),
        "--mode",
        LocalRecoveryMode.EXECUTE_LIVE.value,
        "--live-plan",
        str(plan_path),
        "--live-credential-manifest",
        str(credential_path),
        "--live-state-root",
        str(state_root),
        "--authorize-local-execution",
    ]
    port = _LiveRecoveryPort()

    monkeypatch.setattr("sys.argv", arguments)
    with pytest.raises(SystemExit) as missing:
        main(live_adapters=LiveRecoveryExecutionAdapters(port, port, port))
    assert missing.value.code == 2
    assert port.calls == []

    monkeypatch.setattr("sys.argv", [*arguments, "--live-authority", str(authority_path)])
    main(live_adapters=LiveRecoveryExecutionAdapters(port, port, port))
    result = json.loads(configuration.output_path.read_bytes())
    assert result["live_recovery_proved"] is True
    assert len(port.calls) == len(LiveRecoveryStep) * 2


def test_live_cli_retains_exact_not_ready_when_default_helper_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing privileged host capability must stop before any live port is used."""
    request, configuration = _local_request_and_configuration(tmp_path)
    credentials = _live_credentials(configuration.operation_id)
    plan = build_live_recovery_plan(request, configuration, credentials)
    plan_path = tmp_path / "live-plan.json"
    credential_path = tmp_path / "live-credentials.json"
    authority_path = tmp_path / "live-authority.json"
    state_root = tmp_path / "live-state"
    state_root.mkdir()
    plan_path.write_bytes(plan)
    credential_path.write_bytes(credentials)
    authority_path.write_bytes(_live_authority(plan))

    def unavailable(*_arguments: object) -> LiveRecoveryExecutionAdapters:
        message = "LIVE_RECOVERY_PRIVILEGED_HELPER_NOT_READY"
        raise LiveRecoveryExecutionError(message)

    monkeypatch.setattr("tools.hk_v1_recovery_proof._compose_live_adapters", unavailable)
    monkeypatch.setattr(
        "sys.argv",
        [
            "recovery",
            "--operation-id",
            configuration.operation_id,
            "--request-fingerprint",
            configuration.request_fingerprint,
            "--workspace-root",
            str(configuration.workspace_root),
            "--sql-snapshot",
            str(configuration.sql_snapshot_path),
            "--primary-vault-root",
            str(configuration.primary_vault_root),
            "--recovery-vault-root",
            str(configuration.recovery_vault_root),
            "--scheduler-snapshot-root",
            str(configuration.scheduler_snapshot_root),
            "--output",
            str(configuration.output_path),
            "--mode",
            LocalRecoveryMode.EXECUTE_LIVE.value,
            "--live-plan",
            str(plan_path),
            "--live-authority",
            str(authority_path),
            "--live-credential-manifest",
            str(credential_path),
            "--live-state-root",
            str(state_root),
        ],
    )

    with pytest.raises(SystemExit) as stopped:
        main()

    result = json.loads(configuration.output_path.read_bytes())
    assert stopped.value.code == 2
    assert result["mode"] == LocalRecoveryMode.EXECUTE_LIVE.value
    assert result["status"] == LocalRecoveryStatus.NOT_READY.value
    assert result["blockers"] == ["LIVE_RECOVERY_PRIVILEGED_HELPER_NOT_READY"]
    assert capsys.readouterr().out == "NOT_READY\n"


def test_recovery_cli_help_describes_live_plan_and_execution_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Operator help must not describe the live-capable CLI as local-only."""
    monkeypatch.setattr("sys.argv", ["recovery", "--help"])

    with pytest.raises(SystemExit) as stopped:
        main()

    help_text = capsys.readouterr().out
    normalized_help = " ".join(help_text.split())
    assert stopped.value.code == 0
    assert "PLAN_LIVE freezes seven steps" in normalized_help
    assert "EXECUTE_LIVE requires matching detached authority" in normalized_help
    assert "neither performs nor reports a SQL restore" not in normalized_help
