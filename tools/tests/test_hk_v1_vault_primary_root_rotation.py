"""Adversarial no-effect proofs for the Primary Versity root transaction."""

# Compact compound assertions keep each full proof readable.
# ruff: noqa: D103, PT018

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.hk_v1_stage_vault_credential_rotation import (
    deployment_credential_names,
    stage_vault_credential_rotation,
)
from tools.hk_v1_vault_primary_root_rotation import (
    PreparedPrimaryVaultRootRotation,
    PrimaryVaultRootRotationError,
    PrimaryVaultRootRotationPlan,
    RootHostReceipt,
    RootProbeReceipt,
    RootRollbackReceipt,
    RootRotationBlocker,
    RootRotationState,
    TransactionalPrimaryRootHost,
    exclusive_root_rotation_execution,
    execute_primary_vault_root_rotation,
    parse_root_rotation_plan_bytes,
    parse_succeeded_root_rotation_report_bytes,
    prepare_primary_vault_root_rotation,
    retain_root_rotation_plan,
    root_rotation_plan_bytes,
    root_rotation_report_bytes,
    validate_root_report_for_application_rotation,
)

_ROTATION = "rot_" + "a" * 48
_IMAGE = "sha256:" + "b" * 64
_BUILD = "sha256:" + "c" * 64
_ROOT_NAMES = ("vault-primary-root-access", "vault-primary-root-secret")
_APPLICATIONS = {
    "vault-primary-acquisition": "asklegal-primary-acquisition",
    "vault-primary-control": "asklegal-primary-control",
    "vault-primary-processing": "asklegal-primary-processing",
    "vault-primary-promotion": "asklegal-primary-promotion",
    "vault-primary-review": "asklegal-primary-review",
    "vault-recovery-acquisition": "asklegal-recovery-acquisition",
    "vault-recovery-promotion": "asklegal-recovery-promotion",
}


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir(mode=0o700, parents=True)
    for name in deployment_credential_names():
        if name in _APPLICATIONS:
            raw = json.dumps(
                {
                    "access_key_id": _APPLICATIONS[name],
                    "secret_access_key": "old-application-secret-" + name,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        elif name == _ROOT_NAMES[0]:
            raw = b"old-primary-root-access-never-print"
        elif name == _ROOT_NAMES[1]:
            raw = b"old-primary-root-secret-never-print"
        else:
            raw = ("opaque-" + name).encode()
        path = source / name
        path.write_bytes(raw)
        path.chmod(0o600)
    return source.resolve()


def _prepared(
    tmp_path: Path, *, missing_predecessor_helper: bool = False
) -> tuple[PreparedPrimaryVaultRootRotation, Path]:
    source = _source(tmp_path)
    candidate = (tmp_path / "candidate").resolve()
    receipt = (tmp_path / "staging.json").resolve()
    secrets = iter(f"new-application-secret-{index}" for index in range(7))
    stage_vault_credential_rotation(
        source_root=source,
        candidate_root=candidate,
        receipt_path=receipt,
        rotation_id=_ROTATION,
        secret_factory=lambda: next(secrets),
        root_access_factory=lambda: "new-primary-root-access-never-print",
        root_secret_factory=lambda: "new-primary-root-secret-never-print",
    )
    sealed = tmp_path / "sealed"
    sealed.mkdir(mode=0o700)
    for name in _ROOT_NAMES:
        path = sealed / f"{name}.cred"
        path.write_bytes(("sealed-predecessor-" + name).encode())
        path.chmod(0o400)
    vault = (tmp_path / "vault").resolve()
    (vault / "objects").mkdir(parents=True)
    (vault / "objects/evidence").write_bytes(b"preserved-evidence")
    runtime = (tmp_path / "runtime").resolve()
    runtime.mkdir()
    destinations = (runtime / "vault-primary.sh", runtime / "root-network")
    for index, path in enumerate(destinations):
        if missing_predecessor_helper and index == 1:
            continue
        path.write_bytes(f"predecessor-runtime-{index}".encode())
        path.chmod(0o755)
    prepared = prepare_primary_vault_root_rotation(
        receipt,
        sealed_root=sealed.resolve(),
        vault_data_root=vault,
        control_plane_candidate_image_id=_IMAGE,
        application_build_results_fingerprint=_BUILD,
        workspace_root=Path(__file__).resolve().parents[2],
        runtime_destinations=destinations,
    )
    return prepared, receipt


class _Host:
    def __init__(self, prepared: PreparedPrimaryVaultRootRotation, fail: str = "") -> None:
        self.prepared = prepared
        self.fail = fail
        self.active = prepared.plan.predecessor_binding_ref
        self.calls: list[str] = []

    def stage_candidate(self, plan: PrimaryVaultRootRotationPlan, root: Path) -> bool:
        assert plan == self.prepared.plan
        assert root == self.prepared.candidate_root
        self.calls.append("stage")
        return self.fail != "stage"

    def stop_and_check(self, plan: PrimaryVaultRootRotationPlan) -> bool:
        assert plan == self.prepared.plan
        self.calls.append("stop")
        return self.fail != "stop"

    def switch_candidate(self, plan: PrimaryVaultRootRotationPlan) -> bool:
        assert plan == self.prepared.plan
        self.calls.append("switch")
        if self.fail == "switch":
            return False
        self.active = self.prepared.plan.candidate_binding_ref
        return True

    def restart_and_check(
        self, plan: PrimaryVaultRootRotationPlan, *, binding_ref: str
    ) -> RootHostReceipt:
        assert plan == self.prepared.plan
        self.calls.append(
            "restart-"
            + ("new" if binding_ref == self.prepared.plan.candidate_binding_ref else "old")
        )
        healthy = (
            self.fail not in {"restart-new", "restart-and-restore"}
            or binding_ref != self.prepared.plan.candidate_binding_ref
        )
        data = (
            "vaultdata_" + "d" * 64
            if self.fail == "data" and binding_ref == self.prepared.plan.candidate_binding_ref
            else self.prepared.plan.vault_data_state_ref
        )
        config = not (
            self.fail == "config" and binding_ref == self.prepared.plan.candidate_binding_ref
        )
        return RootHostReceipt(
            self.prepared.plan.plan_fingerprint, binding_ref, healthy, data, config
        )

    def record_acceptance(self, plan: PrimaryVaultRootRotationPlan) -> bool:
        assert plan == self.prepared.plan
        self.calls.append("record")
        return self.fail != "record"

    def restore_predecessor(self, plan: PrimaryVaultRootRotationPlan) -> RootRollbackReceipt:
        assert plan == self.prepared.plan
        self.calls.append("restore")
        self.active = self.prepared.plan.predecessor_binding_ref
        proved = self.fail not in {"restore", "restart-and-restore"}
        return RootRollbackReceipt(self.prepared.plan.plan_fingerprint, proved, proved)


class _Probe:
    def __init__(self, host: _Host, fail: str = "") -> None:
        self.host = host
        self.fail = fail

    def check(self, plan: PrimaryVaultRootRotationPlan, *, binding_ref: str) -> RootProbeReceipt:
        assert plan == self.host.prepared.plan
        accepted = binding_ref == self.host.active
        if self.fail == "new" and binding_ref == self.host.prepared.plan.candidate_binding_ref:
            accepted = False
        if self.fail == "old" and binding_ref == self.host.prepared.plan.predecessor_binding_ref:
            accepted = True
        return RootProbeReceipt(self.host.prepared.plan.plan_fingerprint, binding_ref, accepted)


class _SealRunner:
    def run(self, arguments: tuple[str, ...]) -> bool:
        assert arguments
        return True

    def read(self, arguments: tuple[str, ...], *, max_bytes: int) -> bytes | None:
        assert arguments
        assert max_bytes > 0
        return None

    def seal(self, name: str, source_descriptor: int, output: Path) -> bool:
        output.write_bytes(b"sealed-" + name.encode() + b"-" + os.read(source_descriptor, 4096))
        return True


def test_plan_binds_both_changed_root_parts_image_and_complete_vault_tree(tmp_path: Path) -> None:
    prepared, _receipt = _prepared(tmp_path)
    plan = prepared.plan
    assert plan.credential_names == _ROOT_NAMES
    assert plan.control_plane_candidate_image_id == _IMAGE
    assert parse_root_rotation_plan_bytes(root_rotation_plan_bytes(plan)) == plan
    retained = root_rotation_plan_bytes(plan)
    assert b"plaintext_sha256" not in retained
    for value in (
        *prepared.pairs.predecessor.reveal_for_client(),
        *prepared.pairs.candidate.reveal_for_client(),
    ):
        assert value.encode() not in retained


def test_success_proves_new_acceptance_old_rejection_data_and_docker_safety(tmp_path: Path) -> None:
    prepared, receipt = _prepared(tmp_path)
    host = _Host(prepared)
    report = execute_primary_vault_root_rotation(prepared, host=host, probe=_Probe(host))
    assert report.state is RootRotationState.SUCCEEDED
    assert report.complete
    assert report.new_root_accepted and report.old_root_rejected
    assert report.vault_data_preserved and report.docker_configuration_value_free
    assert host.calls == ["stage", "stop", "switch", "restart-new", "record"]
    raw = root_rotation_report_bytes(report)
    assert parse_succeeded_root_rotation_report_bytes(raw) == report
    plan_path = (tmp_path / "root-plan.json").resolve()
    report_path = (tmp_path / "root-report.json").resolve()
    retain_root_rotation_plan(plan_path, prepared.plan)
    report_path.write_bytes(raw)
    report_path.chmod(0o600)
    assert validate_root_report_for_application_rotation(
        report_path,
        plan_path,
        receipt,
        control_plane_candidate_image_id=_IMAGE,
        application_build_results_fingerprint=_BUILD,
    ).startswith("sha256:")
    plan_path.chmod(0o644)
    with pytest.raises(PrimaryVaultRootRotationError, match="EVIDENCE_INVALID"):
        validate_root_report_for_application_rotation(
            report_path,
            plan_path,
            receipt,
            control_plane_candidate_image_id=_IMAGE,
            application_build_results_fingerprint=_BUILD,
        )
    for value in (
        *prepared.pairs.predecessor.reveal_for_client(),
        *prepared.pairs.candidate.reveal_for_client(),
    ):
        assert value.encode() not in raw


@pytest.mark.parametrize(
    ("failure", "blocker"),
    [
        ("stage", RootRotationBlocker.CANDIDATE_SEAL_FAILED),
        ("switch", RootRotationBlocker.SEALED_SWITCH_FAILED),
        ("restart-new", RootRotationBlocker.DEPENDENT_UNIT_FAILURE),
        ("data", RootRotationBlocker.VAULT_DATA_DRIFT),
        ("config", RootRotationBlocker.DOCKER_CONFIGURATION_EXPOSED),
        ("record", RootRotationBlocker.RECEIPT_MISMATCH),
    ],
)
def test_every_failure_restores_old_root_and_proves_new_rejection(
    tmp_path: Path, failure: str, blocker: RootRotationBlocker
) -> None:
    prepared, _receipt = _prepared(tmp_path)
    host = _Host(prepared, failure)
    report = execute_primary_vault_root_rotation(prepared, host=host, probe=_Probe(host))
    assert report.state is RootRotationState.ROLLED_BACK
    assert blocker in report.blocker_codes
    assert report.predecessor_restored and report.candidate_sealed_absent
    assert report.vault_data_preserved and report.docker_configuration_value_free
    with pytest.raises(PrimaryVaultRootRotationError, match="NOT_SUCCEEDED"):
        parse_succeeded_root_rotation_report_bytes(root_rotation_report_bytes(report))


def test_unproved_rollback_is_never_reported_as_restored(tmp_path: Path) -> None:
    prepared, _receipt = _prepared(tmp_path)
    host = _Host(prepared, "restart-and-restore")
    report = execute_primary_vault_root_rotation(prepared, host=host, probe=_Probe(host))
    assert report.state is RootRotationState.BLOCKED
    assert RootRotationBlocker.ROLLBACK_NOT_PROVED in report.blocker_codes
    assert not report.predecessor_restored


def test_failure_to_stop_cannot_claim_rollback_was_proved(tmp_path: Path) -> None:
    prepared, _receipt = _prepared(tmp_path)
    host = _Host(prepared, "stop")
    report = execute_primary_vault_root_rotation(prepared, host=host, probe=_Probe(host))
    assert report.state is RootRotationState.BLOCKED
    assert report.blocker_codes == (
        RootRotationBlocker.DEPENDENT_UNIT_FAILURE,
        RootRotationBlocker.ROLLBACK_NOT_PROVED,
    )
    assert not report.predecessor_restored


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("complete", 1),
        ("unexpected", True),
        ("schema_version", "2.0.0"),
    ],
)
def test_success_report_parser_rejects_wrong_types_extra_fields_and_versions(
    tmp_path: Path, field: str, value: object
) -> None:
    prepared, _receipt = _prepared(tmp_path)
    host = _Host(prepared)
    document = json.loads(
        root_rotation_report_bytes(
            execute_primary_vault_root_rotation(prepared, host=host, probe=_Probe(host))
        )
    )
    document[field] = value
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(PrimaryVaultRootRotationError, match="REPORT_INVALID"):
        parse_succeeded_root_rotation_report_bytes(raw)


def test_application_cross_binding_rejects_other_staging_receipt(tmp_path: Path) -> None:
    prepared, _receipt = _prepared(tmp_path / "one")
    other, other_receipt = _prepared(tmp_path / "two")
    raw = root_rotation_report_bytes(
        execute_primary_vault_root_rotation(
            prepared, host=(host := _Host(prepared)), probe=_Probe(host)
        )
    )
    assert prepared.plan.staging_receipt_fingerprint != other.plan.staging_receipt_fingerprint
    report_path = (tmp_path / "report.json").resolve()
    plan_path = (tmp_path / "plan.json").resolve()
    report_path.write_bytes(raw)
    report_path.chmod(0o600)
    retain_root_rotation_plan(plan_path, prepared.plan)
    with pytest.raises(PrimaryVaultRootRotationError, match="REPORT_DRIFT"):
        validate_root_report_for_application_rotation(
            report_path,
            plan_path,
            other_receipt,
            control_plane_candidate_image_id=_IMAGE,
            application_build_results_fingerprint=_BUILD,
        )


def test_retained_plan_resumes_after_candidate_sealed_and_runtime_activation(
    tmp_path: Path,
) -> None:
    prepared, receipt = _prepared(tmp_path)
    for index, name in enumerate(_ROOT_NAMES):
        active = tmp_path / "sealed" / f"{name}.cred"
        active.chmod(0o600)
        active.write_bytes(f"sealed-candidate-{index}".encode())
        active.chmod(0o400)
    for source, destination in zip(
        prepared.runtime_sources, prepared.runtime_destinations, strict=True
    ):
        destination.write_bytes(source.read_bytes())
        destination.chmod(0o755)
    resumed = prepare_primary_vault_root_rotation(
        receipt,
        sealed_root=(tmp_path / "sealed").resolve(),
        vault_data_root=prepared.vault_data_root,
        control_plane_candidate_image_id=_IMAGE,
        application_build_results_fingerprint=_BUILD,
        retained_plan=prepared.plan,
        workspace_root=Path(__file__).resolve().parents[2],
        runtime_destinations=prepared.runtime_destinations,
    )
    assert resumed.plan == prepared.plan


def test_concrete_transaction_switches_and_restores_runtime_files_with_root_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, _receipt = _prepared(tmp_path)
    monkeypatch.setattr(
        "tools.hk_v1_vault_primary_root_rotation.os.geteuid",
        lambda: 0,
    )
    state = (tmp_path / "state").resolve()
    runtime_credentials = (tmp_path / "runtime-credentials").resolve()
    state.mkdir(mode=0o700)
    runtime_credentials.mkdir(mode=0o700)
    host = TransactionalPrimaryRootHost(
        (tmp_path / "sealed").resolve(),
        state,
        runtime_credentials,
        prepared,
        runner=_SealRunner(),
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
    )
    assert host.stage_candidate(prepared.plan, prepared.candidate_root)
    assert host.switch_candidate(prepared.plan)
    for source, destination in zip(
        prepared.runtime_sources, prepared.runtime_destinations, strict=True
    ):
        assert destination.read_bytes() == source.read_bytes()
        assert destination.stat().st_mode & 0o777 == 0o755
    resumed_host = TransactionalPrimaryRootHost(
        (tmp_path / "sealed").resolve(),
        state,
        runtime_credentials,
        prepared,
        runner=_SealRunner(),
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
    )
    assert resumed_host.stage_candidate(prepared.plan, prepared.candidate_root)
    assert resumed_host.switch_candidate(prepared.plan)
    rollback = resumed_host.restore_predecessor(prepared.plan)
    assert rollback.predecessor_active and rollback.candidate_sealed_absent
    assert tuple(path.read_bytes() for path in prepared.runtime_destinations) == tuple(
        path.read_bytes() for path in prepared.runtime_sources
    )


def test_absent_predecessor_helper_stays_hardened_for_rollback_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, _receipt = _prepared(tmp_path, missing_predecessor_helper=True)
    monkeypatch.setattr(
        "tools.hk_v1_vault_primary_root_rotation.os.geteuid",
        lambda: 0,
    )
    state = (tmp_path / "state").resolve()
    runtime_credentials = (tmp_path / "runtime-credentials").resolve()
    state.mkdir(mode=0o700)
    runtime_credentials.mkdir(mode=0o700)
    host = TransactionalPrimaryRootHost(
        (tmp_path / "sealed").resolve(),
        state,
        runtime_credentials,
        prepared,
        runner=_SealRunner(),
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
    )
    assert host.stage_candidate(prepared.plan, prepared.candidate_root)
    assert host.switch_candidate(prepared.plan)
    rollback = host.restore_predecessor(prepared.plan)
    staged_helper = (
        state
        / f"{prepared.plan.rotation_id}-primary-root"
        / "runtime-candidate"
        / "primary-root-network-helper"
    )
    assert rollback.predecessor_active and rollback.candidate_sealed_absent
    assert prepared.runtime_destinations[1].read_bytes() == prepared.runtime_sources[1].read_bytes()
    assert staged_helper.is_file() and staged_helper.stat().st_mode & 0o777 == 0o755


def test_execution_lock_rejects_same_transaction_concurrency(tmp_path: Path) -> None:
    state = (tmp_path / "state").resolve()
    state.mkdir(mode=0o700)
    with (
        exclusive_root_rotation_execution(state),
        pytest.raises(PrimaryVaultRootRotationError, match="ALREADY_RUNNING"),
        exclusive_root_rotation_execution(state),
    ):
        pytest.fail("concurrent execution lock unexpectedly acquired")


def test_current_host_missing_candidate_runtime_directory_does_not_block_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, _receipt = _prepared(tmp_path)
    monkeypatch.setattr(
        "tools.hk_v1_vault_primary_root_rotation.os.geteuid",
        lambda: 0,
    )
    state = (tmp_path / "state").resolve()
    state.mkdir(mode=0o700)
    candidate_created_runtime = (tmp_path / "not-created-yet" / "vault-primary").resolve()
    assert not candidate_created_runtime.exists()
    host = TransactionalPrimaryRootHost(
        (tmp_path / "sealed").resolve(),
        state,
        candidate_created_runtime,
        prepared,
        runner=_SealRunner(),
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
    )
    assert host.stage_candidate(prepared.plan, prepared.candidate_root)
    assert not candidate_created_runtime.exists()


def test_network_wrapper_mounts_only_exact_bound_files_and_never_environment_values() -> None:
    script = (
        Path(__file__).resolve().parents[2]
        / "infrastructure/poc/libexec/asklegal-vault-primary-root-rotation-network"
    ).read_text()
    assert "snapshot_names=(embedding-provider" in script
    assert "vault-primary-root-access vault-primary-root-secret" in script
    assert "application_names=(vault-primary-acquisition" in script
    assert "dst=/run/rotation/snapshot/${name},readonly" in script
    assert "dst=/run/rotation/applications/${name},readonly" in script
    assert '--expected-control-plane-image-id "$image_id"' in script
    assert '"--control-plane-image-id"' in script
    assert "/etc/asklegal/deployment-images" not in script
    assert " -e " not in script
