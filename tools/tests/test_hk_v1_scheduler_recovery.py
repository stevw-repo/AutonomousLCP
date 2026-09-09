"""No-effect tests for the fixed Scheduler recovery helper boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from asklegal_evidence_vault import (
    ArtifactClass,
    ArtifactDescriptor,
    EvidenceManifest,
    EvidenceManifestEntry,
    EvidencePackageReceipt,
    ExactObjectReference,
    RecoveryCopyReceipt,
    RetentionProfile,
    VaultName,
)

from tools.hk_v1_recovery_proof import (
    LiveRecoveryExecutionError,
    LiveRecoveryStep,
    LocalRecoveryConfiguration,
    MigrationReadback,
    RecoveryEvidenceReference,
    RegisterFamilyReadback,
    SchedulerHubInventory,
    SchedulerRole,
    SealedCredentialReference,
    build_live_recovery_credential_manifest,
    build_live_recovery_plan,
    build_local_scheduler_snapshot,
    build_local_sql_snapshot,
    freeze_local_recovery_contract,
)
from tools.hk_v1_scheduler_recovery import (
    SchedulerLiveRecoveryPort,
    SchedulerRecoveryCommandResult,
    SubprocessSchedulerRecoveryCommandRunner,
)


def _id(number: int) -> str:
    return f"r_{number:032x}"


def _fp(number: int) -> str:
    return f"sha256:{number:064x}"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sealed(body: dict[str, object]) -> bytes:
    return (
        _canonical({**body, "fingerprint": f"sha256:{sha256(_canonical(body)).hexdigest()}"})
        + b"\n"
    )


def _reference(number: int) -> RecoveryEvidenceReference:
    return RecoveryEvidenceReference(_id(number), _fp(number))


def _fixture(tmp_path: Path) -> tuple[dict[str, object], tuple[SealedCredentialReference, ...]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    retention = RetentionProfile("proof", "2030-01-01T00:00:00Z")
    descriptor = ArtifactDescriptor(
        "art_" + "1" * 48,
        "evi_" + "2" * 48,
        ArtifactClass.SOURCE_CONTENT,
        "src_" + "3" * 48,
        "obs_" + "4" * 48,
        "2026-09-09T00:00:00Z",
        "2026-09-09T00:00:00Z",
        "GET",
        "https://synthetic.invalid/recovery",
        "application/json",
        "application/json",
        "identity",
        "utf-8",
        (("status-code", "200"),),
        retention,
    )
    primary = ExactObjectReference(VaultName.PRIMARY, "objects/one", "v" + "1" * 64, _fp(1), 1)
    recovery = ExactObjectReference(VaultName.RECOVERY, "objects/one", "v" + "2" * 64, _fp(1), 1)
    manifest = EvidenceManifest(
        "proof",
        "pkg_" + "5" * 48,
        descriptor.observation_id,
        (EvidenceManifestEntry(descriptor, primary),),
    )
    request = freeze_local_recovery_contract(
        (MigrationReadback("m_000001", _fp(2)),),
        (RegisterFamilyReadback("events", 1, _fp(3)),),
        _reference(4),
        _reference(5),
        _reference(6),
        _reference(7),
        EvidencePackageReceipt(
            manifest,
            ExactObjectReference(
                VaultName.PRIMARY, "packages/proof/manifest", "v" + "3" * 64, _fp(8), 1
            ),
            ExactObjectReference(
                VaultName.RECOVERY, "packages/proof/manifest", "v" + "4" * 64, _fp(8), 1
            ),
            (RecoveryCopyReceipt(primary, recovery),),
        ),
        _id(8),
        _id(9),
        (
            SchedulerHubInventory(SchedulerRole.GENERAL, (_id(10), _id(11))),
            SchedulerHubInventory(SchedulerRole.PROMOTION, (_id(12),)),
        ),
    )
    scheduler_root = tmp_path / "scheduler"
    scheduler_root.mkdir()
    for role, number in ((SchedulerRole.GENERAL, 20), (SchedulerRole.PROMOTION, 30)):
        checkpoint = f"{role.value} checkpoint".encode()
        stem = role.value.casefold()
        (scheduler_root / f"{stem}-checkpoint.bin").write_bytes(checkpoint)
        (scheduler_root / f"{stem}.json").write_bytes(
            build_local_scheduler_snapshot(request, role, _id(number), _id(number + 1), checkpoint)
        )
    sql = tmp_path / "sql.json"
    sql.write_bytes(build_local_sql_snapshot(request, _id(40)))
    for name in ("primary", "recovery", "workspace", "output"):
        (tmp_path / name).mkdir()
    configuration = LocalRecoveryConfiguration(
        _id(50),
        request.fingerprint,
        tmp_path / "workspace",
        sql,
        tmp_path / "primary",
        tmp_path / "recovery",
        scheduler_root,
        tmp_path / "output" / "result.json",
    )
    credentials = tuple(
        SealedCredentialReference(
            credential_id,
            f"/run/credentials/asklegal/{credential_id.casefold()}",
            _fp(index + 100),
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
    )
    plan = json.loads(
        build_live_recovery_plan(
            request,
            configuration,
            build_live_recovery_credential_manifest(configuration.operation_id, credentials),
        )
    )
    return cast("dict[str, object]", plan), credentials


@dataclass
class _Verifier:
    admitted: bool = True

    def verify(self, reference: SealedCredentialReference) -> bool:
        del reference
        return self.admitted


class _Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.exists = False
        self.drift = False

    def run(self, argv: tuple[str, ...]) -> SchedulerRecoveryCommandResult:
        self.calls.append(argv)
        values = dict(zip(argv[2::2], argv[3::2], strict=True))
        if argv[1] == "reconcile-readback" and not self.exists:
            return SchedulerRecoveryCommandResult(
                3,
                _sealed(
                    {
                        "direction": values["--direction"],
                        "plan_fingerprint": values["--plan-fingerprint"],
                        "replacement_instance_identity": values["--replacement-instance"],
                        "role": values["--role"],
                        "schema": "asklegal.hk-v1-scheduler-recovery-not-found/v1",
                    }
                ),
                b"",
            )
        self.exists = True
        body: dict[str, object] = {
            "checkpoint_fingerprint": values["--checkpoint-fingerprint"],
            "direction": values["--direction"],
            "effect_reconciliation_receipts": [{"evidence_id": _id(203), "fingerprint": _fp(203)}],
            "hubs": [_id(10), _id(11)] if values["--role"] == "GENERAL" else [_id(12)],
            "lost_instance_identity": values["--lost-instance"],
            "old_lineage_fence_receipt": {
                "evidence_id": _id(200),
                "fingerprint": _fp(200),
            },
            "old_lineage_identity": values["--old-lineage"],
            "old_lineage_resumption_denied_receipt": {
                "evidence_id": _id(202),
                "fingerprint": _fp(202),
            },
            "plan_fingerprint": values["--plan-fingerprint"],
            "recovery_lineage_identity": values["--recovery-lineage"],
            "replacement_instance_identity": values["--replacement-instance"],
            "replacement_start_result_receipt": {
                "evidence_id": _id(201),
                "fingerprint": _fp(201),
            },
            "request_fingerprint": values["--request-fingerprint"],
            "role": values["--role"],
            "schema": "asklegal.hk-v1-scheduler-recovery-readback/v1",
        }
        if self.drift:
            body["old_lineage_identity"] = _id(999)
        return SchedulerRecoveryCommandResult(0, _sealed(body), b"")


def test_scheduler_adapter_reconciles_then_executes_exact_leg(tmp_path: Path) -> None:
    """Target absence permits one effect and exact later reconciliation."""
    plan, credentials = _fixture(tmp_path)
    runner = _Runner()
    port = SchedulerLiveRecoveryPort(runner, credential_verifier=_Verifier())

    assert port.reconcile(LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD, plan, credentials) is None
    receipt = port.execute(LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD, plan, credentials)
    replay = port.reconcile(LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD, plan, credentials)

    assert receipt == replay
    assert receipt.step is LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD
    assert [call[1] for call in runner.calls] == [
        "reconcile-readback",
        "replace-and-readback",
        "reconcile-readback",
    ]


@pytest.mark.parametrize(
    "step",
    [
        LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD,
        LiveRecoveryStep.SCHEDULER_GENERAL_REVERSE,
        LiveRecoveryStep.SCHEDULER_PROMOTION_FORWARD,
        LiveRecoveryStep.SCHEDULER_PROMOTION_REVERSE,
    ],
)
def test_all_four_scheduler_replacement_legs_are_bound(
    tmp_path: Path, step: LiveRecoveryStep
) -> None:
    """General and Promotion forward/reverse legs all derive exact identities."""
    plan, credentials = _fixture(tmp_path)
    runner = _Runner()
    receipt = SchedulerLiveRecoveryPort(runner, credential_verifier=_Verifier()).execute(
        step, plan, credentials
    )
    assert receipt.step is step


def test_snapshot_and_credential_drift_stop_before_helper(tmp_path: Path) -> None:
    """Current retained inputs and sealed bytes must still match before any command."""
    plan, credentials = _fixture(tmp_path)
    runner = _Runner()
    checkpoint = tmp_path / "scheduler" / "general-checkpoint.bin"
    checkpoint.write_bytes(b"drift")
    port = SchedulerLiveRecoveryPort(runner, credential_verifier=_Verifier())
    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_SCHEDULER_RECOVERY_PLAN_INVALID"):
        port.execute(LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD, plan, credentials)
    assert runner.calls == []

    plan, credentials = _fixture(tmp_path / "second")
    runner = _Runner()
    port = SchedulerLiveRecoveryPort(runner, credential_verifier=_Verifier(admitted=False))
    with pytest.raises(
        LiveRecoveryExecutionError, match="LIVE_SCHEDULER_RECOVERY_CREDENTIAL_DRIFT"
    ):
        port.execute(LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD, plan, credentials)
    assert runner.calls == []


def test_helper_semantic_drift_is_rejected(tmp_path: Path) -> None:
    """A helper cannot substitute unrelated lineage in a syntactically valid receipt."""
    plan, credentials = _fixture(tmp_path)
    runner = _Runner()
    runner.drift = True
    with pytest.raises(
        LiveRecoveryExecutionError, match="LIVE_SCHEDULER_RECOVERY_READBACK_INVALID"
    ):
        SchedulerLiveRecoveryPort(runner, credential_verifier=_Verifier()).execute(
            LiveRecoveryStep.SCHEDULER_GENERAL_FORWARD, plan, credentials
        )


def test_subprocess_runner_rejects_nonprotocol_argv_without_process_call() -> None:
    """The concrete process runner has no shell or arbitrary-command surface."""
    runner = SubprocessSchedulerRecoveryCommandRunner()
    with pytest.raises(LiveRecoveryExecutionError, match="LIVE_SCHEDULER_RECOVERY_COMMAND_INVALID"):
        runner.run(("/bin/sh", "-c", "echo unsafe"))
