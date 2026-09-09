"""Focused proofs for the seven-credential predeployment rotation boundary."""

# pyright: reportPrivateUsage=false
# Test doubles intentionally keep their port methods compact and raise marker
# exceptions to prove sanitization and rollback behavior.
# ruff: noqa: D102, D107, EM101, FBT003, SLF001, TRY003

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_control_plane import vault_rotation as network_rotation
from asklegal_control_plane.bootstrap import VaultIdentityAdministrationPort
from asklegal_evidence_vault import S3AccessCredential, VaultName

from tools.hk_v1_host_reconcile import build_application_build_results
from tools.hk_v1_stage_vault_credential_rotation import (
    deployment_credential_names,
    stage_vault_credential_rotation,
)
from tools.hk_v1_vault_application_rotation import (
    AcceptanceReceipt,
    BootstrapIdentitySetAdapter,
    BoundReceipt,
    DualNetworkRotationAdapter,
    FlatSealedPredecessorInspector,
    HostCleanupReceipt,
    HostCredentialSetPort,
    HostRollbackReceipt,
    PreparedVaultApplicationRotation,
    ReconciledVersityIdentitySetAdapter,
    RotationBlocker,
    RotationState,
    TransactionalFlatHostCredentialSet,
    UnitReceipt,
    UnitStopReceipt,
    VaultApplicationRotationPlan,
    VaultCredentialAcceptancePort,
    _candidate_image_provenance,
    _terminal_replay_plan,
    complete_terminal_cleanup,
    execute_vault_application_rotation,
    main,
    parse_rotation_plan_bytes,
    parse_rotation_report_bytes,
    parse_succeeded_rotation_report_bytes,
    prepare_vault_application_rotation,
    production_adapter_blockers,
    retain_rotation_plan,
    rotation_plan_bytes,
    rotation_report_bytes,
)
from tools.hk_v1_vault_primary_root_rotation import (
    PrimaryVaultRootRotationReport,
    RootRotationState,
    root_rotation_report_bytes,
)

_ROTATION = "rot_" + "1" * 48
_SEALED = "sealed_" + "2" * 64
_IMAGE = "sha256:" + "3" * 64
_APPLICATION_NAMES = (
    "vault-primary-acquisition",
    "vault-primary-control",
    "vault-primary-processing",
    "vault-primary-promotion",
    "vault-primary-review",
    "vault-recovery-acquisition",
    "vault-recovery-promotion",
)
_ACCESS = {
    "vault-primary-acquisition": "asklegal-primary-acquisition",
    "vault-primary-control": "asklegal-primary-control",
    "vault-primary-processing": "asklegal-primary-processing",
    "vault-primary-promotion": "asklegal-primary-promotion",
    "vault-primary-review": "asklegal-primary-review",
    "vault-recovery-acquisition": "asklegal-recovery-acquisition",
    "vault-recovery-promotion": "asklegal-recovery-promotion",
}


def test_candidate_image_is_derived_from_current_source_bound_build_results(
    tmp_path: Path,
) -> None:
    """A stale source tree or caller-selected image ID cannot enter the plan."""
    root = (tmp_path / "workspace").resolve()
    (root / "apps").mkdir(parents=True)
    (root / "packages").mkdir()
    services = (
        "acquisition-worker",
        "control-plane",
        "legal-processing-worker",
        "promotion-worker",
        "review-api",
    )
    images: list[dict[str, object]] = []
    rows: list[tuple[str, str, str, str]] = []
    for index, service in enumerate(services, start=1):
        application = root / "apps" / service
        application.mkdir()
        (application / "pyproject.toml").write_text(f"name='{service}'\n")
        images.append({"artifact_id": service, "application_path": f"apps/{service}"})
        rows.append(
            (
                service,
                f"asklegal/{service}:hk-v1-candidate",
                "sha256:" + str(index) * 64,
                str(index) * 128,
            )
        )
    image_inputs: dict[str, object] = {"images": images}
    image_inputs_path = root / "image-inputs.json"
    image_inputs_path.write_text(json.dumps(image_inputs))
    build_path = root / "build-results.json"
    build_path.write_bytes(build_application_build_results(image_inputs, tuple(rows), root=root))

    image_id, fingerprint = _candidate_image_provenance(
        build_results_path=build_path,
        image_inputs_path=image_inputs_path,
        workspace_root=root,
    )
    assert image_id == "sha256:" + "2" * 64
    assert fingerprint == "sha256:" + sha256(build_path.read_bytes()).hexdigest()

    (root / "apps/control-plane/pyproject.toml").write_text("changed=true\n")
    with pytest.raises(Exception, match="APPLICATION_BUILD_RESULTS_INVALID"):
        _candidate_image_provenance(
            build_results_path=build_path,
            image_inputs_path=image_inputs_path,
            workspace_root=root,
        )


def _staging(tmp_path: Path, *, legacy_accesses: bool = False) -> Path:
    source = (tmp_path / "source").resolve()
    source.mkdir(mode=0o700)
    for name in deployment_credential_names():
        if name in _APPLICATION_NAMES:
            access = "legacy-" + name if legacy_accesses else _ACCESS[name]
            raw = json.dumps(
                {
                    "access_key_id": access,
                    "secret_access_key": "old-value-" + name,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        else:
            raw = ("opaque-" + name).encode()
        path = source / name
        path.write_bytes(raw)
        path.chmod(0o600)
    candidate = (tmp_path / "candidate").resolve()
    receipt = (tmp_path / "staging-receipt.json").resolve()
    generated = iter("new-value-" + name for name in _APPLICATION_NAMES)
    stage_vault_credential_rotation(
        source_root=source,
        candidate_root=candidate,
        receipt_path=receipt,
        rotation_id=_ROTATION,
        secret_factory=lambda: next(generated),
    )
    return receipt


class FakeHost(HostCredentialSetPort):
    """Exact call-recording transactional host double."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: str | None = None
        self.rollback_complete = True

    def inspect_predecessor(self, credential_names: tuple[str, ...]) -> str:
        assert credential_names == _APPLICATION_NAMES
        self.calls.append("inspect")
        return _SEALED

    def stage_candidate(
        self, plan: VaultApplicationRotationPlan, candidate_root: Path
    ) -> BoundReceipt:
        assert candidate_root.is_dir()
        self.calls.append("stage")
        if self.fail == "stage":
            raise RuntimeError("sensitive stage error")
        return BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)

    def stop_and_check(self, plan: VaultApplicationRotationPlan) -> UnitStopReceipt:
        self.calls.append("stop")
        if self.fail == "stop":
            raise RuntimeError("sensitive stop error")
        return UnitStopReceipt(plan.plan_fingerprint, plan.dependent_units, True)

    def switch_candidate(
        self, plan: VaultApplicationRotationPlan, staged: BoundReceipt
    ) -> BoundReceipt:
        assert staged.binding_ref == plan.candidate_binding_ref
        self.calls.append("switch")
        if self.fail == "switch":
            raise RuntimeError("sensitive switch error")
        return BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)

    def restart_and_check(
        self, plan: VaultApplicationRotationPlan, *, binding_ref: str
    ) -> UnitReceipt:
        suffix = "new" if binding_ref == plan.candidate_binding_ref else "old"
        self.calls.append("restart-" + suffix)
        healthy = self.fail != "restart-" + suffix
        return UnitReceipt(plan.plan_fingerprint, binding_ref, plan.dependent_units, healthy)

    def finalize_success(
        self, plan: VaultApplicationRotationPlan, switched: BoundReceipt
    ) -> HostCleanupReceipt:
        assert switched.binding_ref == plan.candidate_binding_ref
        self.calls.append("finalize")
        complete = self.fail != "finalize"
        return HostCleanupReceipt(plan.plan_fingerprint, complete, complete, complete)

    def record_acceptance(self, plan: VaultApplicationRotationPlan) -> BoundReceipt:
        self.calls.append("record-acceptance")
        return BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)

    def restore_predecessor(self, plan: VaultApplicationRotationPlan) -> HostRollbackReceipt:
        self.calls.append("restore")
        return HostRollbackReceipt(
            plan.plan_fingerprint,
            self.rollback_complete,
            self.rollback_complete,
            self.rollback_complete,
        )


class FakeIdentities:
    """Two-vault exact-set replacement double."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.candidate: object | None = None
        self.predecessor: object | None = None
        self.fail_candidate = False
        self.current = "old"

    def replace(
        self,
        credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    ) -> None:
        if credentials is self.candidate:
            self.calls.append("identity-new")
            self.current = "split" if self.fail_candidate else "new"
            if self.fail_candidate:
                raise RuntimeError("sensitive recovery-vault error")
        elif credentials is self.predecessor:
            self.calls.append("identity-old")
            self.current = "old"
        else:
            raise AssertionError("unbound credential set")


class FakeAuthenticator(VaultCredentialAcceptancePort):
    """Provider-classification double driven by current identity state."""

    def __init__(self, identities: FakeIdentities) -> None:
        self.identities = identities
        self.calls: list[str] = []

    def check(
        self,
        plan: VaultApplicationRotationPlan,
        *,
        binding_ref: str,
        credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    ) -> AcceptanceReceipt:
        is_new = credentials is self.identities.candidate
        self.calls.append("auth-new" if is_new else "auth-old")
        accepted = (
            plan.rotated_credential_names
            if (is_new and self.identities.current == "new")
            or (not is_new and self.identities.current == "old")
            else ()
        )
        rejected = () if accepted else plan.rotated_credential_names
        return AcceptanceReceipt(
            plan.plan_fingerprint,
            binding_ref,
            accepted,
            rejected,
        )


def _prepared(
    tmp_path: Path, *, legacy_accesses: bool = False
) -> tuple[PreparedVaultApplicationRotation, FakeHost, FakeIdentities, FakeAuthenticator]:
    host = FakeHost()
    prepared = prepare_vault_application_rotation(
        _staging(tmp_path, legacy_accesses=legacy_accesses),
        host=host,
        control_plane_candidate_image_id=_IMAGE,
    )
    identities = FakeIdentities()
    identities.candidate = prepared.credentials.candidate
    identities.predecessor = prepared.credentials.predecessor
    authenticator = FakeAuthenticator(identities)
    return prepared, host, identities, authenticator


def test_preparation_binds_exact_batch_and_names_production_blockers(tmp_path: Path) -> None:
    """Preparation consumes the receipt and names every missing live adapter."""
    prepared, host, _identities, _authenticator = _prepared(tmp_path, legacy_accesses=True)

    assert prepared.plan.sealed_credential_names == _APPLICATION_NAMES
    assert prepared.plan.rotated_credential_names == _APPLICATION_NAMES
    assert len(prepared.plan.dependent_units) == 5
    assert host.calls == ["inspect"]
    assert production_adapter_blockers(prepared) == (
        RotationBlocker.CANDIDATE_IMAGE_PROVENANCE_MISSING,
    )
    encoded = rotation_plan_bytes(prepared.plan)
    assert b"old-value" not in encoded
    assert b"new-value" not in encoded
    assert b"secret" not in encoded.lower()
    assert json.loads(encoded)["credential_units"] == [
        {
            "credential_name": name,
            "dependent_units": list(units),
        }
        for name, units in prepared.plan.credential_units
    ]
    assert parse_rotation_plan_bytes(encoded) == prepared.plan
    output = (tmp_path / "plan.json").resolve()
    assert retain_rotation_plan(output, prepared.plan) == encoded
    assert retain_rotation_plan(output, prepared.plan) == encoded
    assert output.stat().st_mode & 0o777 == 0o600
    binding = network_rotation._plan(output)
    assert binding.plan_fingerprint == prepared.plan.plan_fingerprint
    assert binding.control_plane_candidate_image_id == _IMAGE

    altered = json.loads(encoded)
    altered["unexpected"] = True
    output.write_bytes(canonicalize(checked_json_value(altered)))
    with pytest.raises(Exception, match="ROTATION_NETWORK_PLAN_INVALID"):
        network_rotation._plan(output)


def test_success_stops_apps_updates_both_vaults_switches_and_proves_rejection(
    tmp_path: Path,
) -> None:
    """The candidate becomes final only after exact auth and health evidence."""
    prepared, host, identities, authenticator = _prepared(tmp_path)

    report = execute_vault_application_rotation(
        prepared,
        host=host,
        identities=identities,
        authenticator=authenticator,
    )

    assert report.state is RotationState.SUCCEEDED
    assert report.complete
    assert host.calls == [
        "inspect",
        "stage",
        "stop",
        "switch",
        "restart-new",
        "record-acceptance",
        "finalize",
    ]
    assert identities.calls == ["identity-new"]
    assert authenticator.calls == ["auth-new", "auth-old"]
    encoded = rotation_report_bytes(report)
    assert b"old-value" not in encoded
    assert b"new-value" not in encoded
    assert b"secret" not in encoded.lower()
    assert parse_rotation_report_bytes(encoded) == report
    assert parse_succeeded_rotation_report_bytes(encoded) == report


def test_partial_identity_failure_rolls_both_vaults_and_host_back(tmp_path: Path) -> None:
    """A split provider update cannot be mistaken for a completed rotation."""
    prepared, host, identities, authenticator = _prepared(tmp_path)
    identities.fail_candidate = True

    report = execute_vault_application_rotation(
        prepared,
        host=host,
        identities=identities,
        authenticator=authenticator,
    )

    assert report.state is RotationState.ROLLED_BACK
    assert not report.complete
    assert report.blocker_codes == (RotationBlocker.IDENTITY_UPDATE_FAILED,)
    assert identities.calls == ["identity-new", "identity-old"]
    assert host.calls == ["inspect", "stage", "stop", "stop", "restore", "restart-old"]
    assert authenticator.calls == ["auth-old", "auth-new"]
    assert not report.plaintext_absent


def test_incomplete_rollback_is_blocked_not_reported_restored(tmp_path: Path) -> None:
    """Host restoration without exact readback remains visibly blocked."""
    prepared, host, identities, authenticator = _prepared(tmp_path)
    host.fail = "switch"
    host.rollback_complete = False

    report = execute_vault_application_rotation(
        prepared,
        host=host,
        identities=identities,
        authenticator=authenticator,
    )

    assert report.state is RotationState.BLOCKED
    assert report.blocker_codes == (
        RotationBlocker.ROLLBACK_NOT_PROVED,
        RotationBlocker.SEALED_SWITCH_FAILED,
    )
    assert not report.predecessor_restored


class FakeAdministrator(VaultIdentityAdministrationPort):
    """Existing bootstrap-port double for adapter composition."""

    def __init__(self) -> None:
        self.values: tuple[S3AccessCredential, ...] = ()
        self.calls: list[str] = []

    def provision(self, credentials: tuple[S3AccessCredential, ...]) -> None:
        self.calls.append("provision")
        self.values = credentials

    def readback(self, credentials: tuple[S3AccessCredential, ...]) -> tuple[str, ...]:
        self.calls.append("readback")
        assert credentials == self.values
        return tuple(item.reveal_for_client()[0] for item in credentials)


class FakeReconciledAdministrator(FakeAdministrator):
    """Existing signed transport double with exact delete behavior."""

    def __init__(self, values: tuple[S3AccessCredential, ...]) -> None:
        super().__init__()
        self.values = values

    def rotation_users(self) -> tuple[tuple[str, str, str], ...]:
        return tuple((*item.reveal_for_client(), "user") for item in self.values)

    def provision(self, credentials: tuple[S3AccessCredential, ...]) -> None:
        self.calls.append("provision")
        current = {item.reveal_for_client()[0]: item for item in self.values}
        current.update({item.reveal_for_client()[0]: item for item in credentials})
        self.values = tuple(current.values())

    def delete_rotation_user(self, access: str) -> None:
        self.values = tuple(item for item in self.values if item.reveal_for_client()[0] != access)
        self.calls.append("delete")


def test_bootstrap_identity_adapter_reuses_exact_existing_api(tmp_path: Path) -> None:
    """The supported identity step delegates to provision plus exact readback."""
    prepared, _host, _identities, _authenticator = _prepared(tmp_path)
    primary = FakeAdministrator()
    recovery = FakeAdministrator()
    adapter = BootstrapIdentitySetAdapter(
        ((VaultName.PRIMARY, primary), (VaultName.RECOVERY, recovery))
    )

    adapter.replace(prepared.credentials.candidate)

    assert primary.calls == ["provision", "readback"]
    assert recovery.calls == ["provision", "readback"]
    assert len(primary.values) == 5
    assert len(recovery.values) == 2

    report = execute_vault_application_rotation(
        prepared,
        host=FakeHost(),
        identities=adapter,
        authenticator=FakeAuthenticator(FakeIdentities()),
    )
    assert report.state is RotationState.BLOCKED
    assert report.blocker_codes == (RotationBlocker.CROSS_VAULT_IAM_RECONCILIATION_ADAPTER_MISSING,)


def test_reconciled_identity_adapter_deletes_only_bound_obsolete_users_and_rolls_back(
    tmp_path: Path,
) -> None:
    """Changed access IDs converge forward and backward through signed exact deletes."""
    prepared, _host, _identities, _authenticator = _prepared(tmp_path, legacy_accesses=True)
    primary = FakeReconciledAdministrator(prepared.credentials.predecessor[0][1])
    recovery = FakeReconciledAdministrator(prepared.credentials.predecessor[1][1])
    adapter = ReconciledVersityIdentitySetAdapter(
        ((VaultName.PRIMARY, primary), (VaultName.RECOVERY, recovery)),
        prepared.credentials.predecessor,
        prepared.credentials.candidate,
        plan=prepared.plan,
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
    )

    adapter.replace(prepared.credentials.candidate)
    assert primary.values == prepared.credentials.candidate[0][1]
    assert recovery.values == prepared.credentials.candidate[1][1]
    adapter.replace(prepared.credentials.predecessor)
    assert primary.values == prepared.credentials.predecessor[0][1]
    assert recovery.values == prepared.credentials.predecessor[1][1]
    assert primary.calls.count("delete") == 10
    assert recovery.calls.count("delete") == 4


def test_flat_sealed_inspector_reads_only_exact_opaque_files(tmp_path: Path) -> None:
    """The truthful production component binds but never decrypts the predecessor."""
    root = (tmp_path / "sealed").resolve()
    root.mkdir(mode=0o700)
    for name in _APPLICATION_NAMES:
        path = root / f"{name}.cred"
        path.write_bytes(("opaque-sealed-" + name).encode())
        path.chmod(0o400)

    first = FlatSealedPredecessorInspector(root).inspect_predecessor(_APPLICATION_NAMES)
    assert first.startswith("sealed_")
    changed = root / f"{_APPLICATION_NAMES[0]}.cred"
    changed.chmod(0o600)
    with pytest.raises(Exception, match="PREDECESSOR_SEALED_STATE_INVALID"):
        FlatSealedPredecessorInspector(root).inspect_predecessor(_APPLICATION_NAMES)


class FakeCommandRunner:
    """No-effect systemd-creds/systemctl double for the root host adapter."""

    def __init__(self) -> None:
        self.active = True
        self.calls: list[tuple[str, ...]] = []
        self.seal_calls = 0
        self.fail_seal_at: int | None = None

    def run(self, arguments: tuple[str, ...]) -> bool:
        self.calls.append(arguments)
        if arguments[:2] == ("/usr/bin/systemctl", "stop"):
            self.active = False
        elif arguments[:2] == ("/usr/bin/systemctl", "restart"):
            self.active = True
        return True

    def read(self, arguments: tuple[str, ...], *, max_bytes: int) -> bytes | None:
        self.calls.append(arguments)
        value = b"active\n" if self.active else b"inactive\n"
        assert len(value) <= max_bytes
        return value

    def seal(self, name: str, source_descriptor: int, output: Path) -> bool:
        assert name in _APPLICATION_NAMES
        assert source_descriptor >= 0
        self.calls.append(("/usr/bin/systemd-creds", "encrypt", f"--name={name}"))
        self.seal_calls += 1
        if self.seal_calls == self.fail_seal_at:
            return False
        output.write_bytes(b"opaque-candidate-sealed")
        output.chmod(0o400)
        return True


def _runtime_credentials(root: Path, prepared: PreparedVaultApplicationRotation) -> None:
    root.mkdir(mode=0o700)
    for name, units in prepared.plan.credential_units:
        service = units[0].removeprefix("asklegal-").removesuffix(".service")
        directory = root / service
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / name
        path.write_bytes((prepared.candidate_root / name).read_bytes())
        path.chmod(0o400)


def test_root_host_adapter_stages_switches_and_restores_with_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The concrete host adapter uses exact argv and retained predecessor blobs."""
    receipt = _staging(tmp_path)
    sealed = (tmp_path / "sealed").resolve()
    sealed.mkdir(mode=0o700)
    for name in _APPLICATION_NAMES:
        path = sealed / f"{name}.cred"
        path.write_bytes(("opaque-predecessor-" + name).encode())
        path.chmod(0o400)
    prepared = prepare_vault_application_rotation(
        receipt,
        host=FlatSealedPredecessorInspector(sealed),
        control_plane_candidate_image_id=_IMAGE,
    )
    state = (tmp_path / "state").resolve()
    state.mkdir(mode=0o700)
    runner = FakeCommandRunner()
    runtime = (tmp_path / "runtime").resolve()
    _runtime_credentials(runtime, prepared)
    monkeypatch.setattr("tools.hk_v1_vault_application_rotation.os.geteuid", lambda: 0)
    host = TransactionalFlatHostCredentialSet(
        sealed,
        state,
        prepared.plan,
        runner=runner,
        source_root=prepared.source_root,
        candidate_root=prepared.candidate_root,
        runtime_credential_root=runtime,
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
        host_owner_uid=tmp_path.stat().st_uid,
        staging_owner_uid=tmp_path.stat().st_uid,
    )

    staged = host.stage_candidate(prepared.plan, prepared.candidate_root)
    assert host.stop_and_check(prepared.plan).stopped
    assert host.switch_candidate(prepared.plan, staged).binding_ref == (
        prepared.plan.candidate_binding_ref
    )
    assert host.restart_and_check(
        prepared.plan, binding_ref=prepared.plan.candidate_binding_ref
    ).healthy
    rollback = host.restore_predecessor(prepared.plan)

    assert rollback.predecessor_active
    assert rollback.candidate_sealed_absent
    assert rollback.candidate_plaintext_absent
    assert b"opaque-predecessor" in (sealed / f"{_APPLICATION_NAMES[0]}.cred").read_bytes()
    assert (
        json.loads((state / prepared.plan.rotation_id / "state.json").read_bytes())["phase"]
        == "ROLLED_BACK"
    )
    assert all(call[0] in {"/usr/bin/systemd-creds", "/usr/bin/systemctl"} for call in runner.calls)


def _concrete_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    application_build_results_fingerprint: str | None = None,
) -> tuple[
    PreparedVaultApplicationRotation, TransactionalFlatHostCredentialSet, FakeCommandRunner, Path
]:
    receipt = _staging(tmp_path)
    sealed = (tmp_path / "sealed").resolve()
    sealed.mkdir(mode=0o700)
    for name in _APPLICATION_NAMES:
        path = sealed / f"{name}.cred"
        path.write_bytes(("opaque-predecessor-" + name).encode())
        path.chmod(0o400)
    prepared = prepare_vault_application_rotation(
        receipt,
        host=FlatSealedPredecessorInspector(sealed),
        control_plane_candidate_image_id=_IMAGE,
        application_build_results_fingerprint=application_build_results_fingerprint,
    )
    state = (tmp_path / "state").resolve()
    state.mkdir(mode=0o700)
    runner = FakeCommandRunner()
    runtime = (tmp_path / "runtime").resolve()
    _runtime_credentials(runtime, prepared)
    monkeypatch.setattr("tools.hk_v1_vault_application_rotation.os.geteuid", lambda: 0)
    host = TransactionalFlatHostCredentialSet(
        sealed,
        state,
        prepared.plan,
        runner=runner,
        source_root=prepared.source_root,
        candidate_root=prepared.candidate_root,
        runtime_credential_root=runtime,
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
        host_owner_uid=tmp_path.stat().st_uid,
        staging_owner_uid=tmp_path.stat().st_uid,
    )
    return prepared, host, runner, sealed


def test_candidate_substitution_after_plan_never_reaches_sealing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A same-mode post-plan credential replacement fails on its bound digest."""
    prepared, host, runner, _sealed = _concrete_host(tmp_path, monkeypatch)
    substituted = prepared.candidate_root / _APPLICATION_NAMES[0]
    substituted.write_bytes(b'{"access_key_id":"x","secret_access_key":"changed"}')
    substituted.chmod(0o600)

    with pytest.raises(Exception, match="CANDIDATE_PLAINTEXT_DRIFT"):
        host.stage_candidate(prepared.plan, prepared.candidate_root)
    assert runner.seal_calls == 0


def test_root_owner_and_pinned_directory_swap_fail_before_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong owner or post-construction path replacement cannot redirect writes."""
    prepared, host, runner, sealed = _concrete_host(tmp_path, monkeypatch)
    with pytest.raises(Exception, match="LIVE_ROTATION_PATH_INVALID"):
        TransactionalFlatHostCredentialSet(
            sealed,
            (tmp_path / "state").resolve(),
            prepared.plan,
            runner=runner,
            source_root=prepared.source_root,
            candidate_root=prepared.candidate_root,
            runtime_credential_root=(tmp_path / "runtime").resolve(),
            authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
            host_owner_uid=tmp_path.stat().st_uid + 1,
            staging_owner_uid=tmp_path.stat().st_uid,
        )

    moved = (tmp_path / "sealed-original").resolve()
    sealed.rename(moved)
    sealed.mkdir(mode=0o700)
    for name in _APPLICATION_NAMES:
        path = sealed / f"{name}.cred"
        path.write_bytes(b"redirected")
        path.chmod(0o400)
    with pytest.raises(Exception, match="LIVE_ROTATION_PATH_DRIFT"):
        host.stage_candidate(prepared.plan, prepared.candidate_root)
    assert runner.seal_calls == 0


def test_restart_reconstructs_exact_partial_and_complete_candidate_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Journal plus retained blobs prove both partial and complete crash states."""
    prepared, host, runner, sealed = _concrete_host(tmp_path, monkeypatch)
    staged = host.stage_candidate(prepared.plan, prepared.candidate_root)
    runner.fail_seal_at = 9
    with pytest.raises(Exception, match="CANDIDATE_PLAINTEXT_DRIFT"):
        host.switch_candidate(prepared.plan, staged)

    state = (tmp_path / "state").resolve()
    resumed = TransactionalFlatHostCredentialSet(
        sealed,
        state,
        prepared.plan,
        runner=runner,
        source_root=prepared.source_root,
        candidate_root=prepared.candidate_root,
        runtime_credential_root=(tmp_path / "runtime").resolve(),
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
        host_owner_uid=tmp_path.stat().st_uid,
        staging_owner_uid=tmp_path.stat().st_uid,
    )
    runner.fail_seal_at = None
    resumed.switch_candidate(prepared.plan, staged)
    TransactionalFlatHostCredentialSet(
        sealed,
        state,
        prepared.plan,
        runner=runner,
        source_root=prepared.source_root,
        candidate_root=prepared.candidate_root,
        runtime_credential_root=(tmp_path / "runtime").resolve(),
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
        host_owner_uid=tmp_path.stat().st_uid,
        staging_owner_uid=tmp_path.stat().st_uid,
    )


def test_failed_restore_preserves_candidate_sealed_and_plaintext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing old blob cannot trigger deletion of either candidate recovery set."""
    prepared, host, _runner, _sealed = _concrete_host(tmp_path, monkeypatch)
    host.stage_candidate(prepared.plan, prepared.candidate_root)
    work = (tmp_path / "state" / prepared.plan.rotation_id).resolve()
    (work / "predecessor" / f"{_APPLICATION_NAMES[0]}.cred").unlink()

    rollback = host.restore_predecessor(prepared.plan)

    assert not rollback.predecessor_active
    assert not rollback.candidate_sealed_absent
    assert not rollback.candidate_plaintext_absent
    assert (work / "candidate").is_dir()
    assert prepared.candidate_root.is_dir()


def test_replay_after_authentication_never_regresses_live_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A coordinator replay preserves its durable authentication proof."""
    prepared, host, _runner, _sealed = _concrete_host(tmp_path, monkeypatch)
    staged = host.stage_candidate(prepared.plan, prepared.candidate_root)
    assert host.stop_and_check(prepared.plan).stopped
    host.switch_candidate(prepared.plan, staged)
    assert host.restart_and_check(
        prepared.plan, binding_ref=prepared.plan.candidate_binding_ref
    ).healthy
    host.record_acceptance(prepared.plan)

    replayed = host.stage_candidate(prepared.plan, prepared.candidate_root)
    assert host.stop_and_check(prepared.plan).stopped
    host.switch_candidate(prepared.plan, replayed)
    assert host.restart_and_check(
        prepared.plan, binding_ref=prepared.plan.candidate_binding_ref
    ).healthy
    host.record_acceptance(prepared.plan)

    journal = json.loads(
        (tmp_path / "state" / prepared.plan.rotation_id / "state.json").read_bytes()
    )
    assert journal["phase"] == "AUTHENTICATION_PROVED"
    assert journal["acceptance_proved"] is True


def test_terminal_report_precedes_restartable_predecessor_retirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cleanup retains rollback blobs until the exact success report is durable."""
    prepared, host, runner, sealed = _concrete_host(tmp_path, monkeypatch)
    staged = host.stage_candidate(prepared.plan, prepared.candidate_root)
    host.stop_and_check(prepared.plan)
    switched = host.switch_candidate(prepared.plan, staged)
    host.restart_and_check(prepared.plan, binding_ref=prepared.plan.candidate_binding_ref)
    host.record_acceptance(prepared.plan)
    cleanup = host.finalize_success(prepared.plan, switched)
    predecessor = tmp_path / "state" / prepared.plan.rotation_id / "predecessor"
    assert cleanup.predecessor_plaintext_absent
    assert cleanup.candidate_plaintext_absent
    assert predecessor.is_dir()

    host = TransactionalFlatHostCredentialSet(
        sealed,
        (tmp_path / "state").resolve(),
        prepared.plan,
        runner=runner,
        source_root=prepared.source_root,
        candidate_root=prepared.candidate_root,
        runtime_credential_root=(tmp_path / "runtime").resolve(),
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
        host_owner_uid=tmp_path.stat().st_uid,
        staging_owner_uid=tmp_path.stat().st_uid,
    )
    report_path = (tmp_path / "state" / "rotation-report.json").resolve()
    first = predecessor / f"{_APPLICATION_NAMES[0]}.cred"
    first.unlink()
    report = complete_terminal_cleanup(
        plan=prepared.plan,
        host=host,
        report_path=report_path,
    )

    assert report.state is RotationState.SUCCEEDED
    assert parse_succeeded_rotation_report_bytes(report_path.read_bytes()) == report
    assert not predecessor.exists()
    journal = json.loads(
        (tmp_path / "state" / prepared.plan.rotation_id / "state.json").read_bytes()
    )
    assert journal["phase"] == "TERMINAL"


@pytest.mark.parametrize("target", ["plan", "source", "candidate"])
def test_dual_network_effect_revalidates_every_pinned_input(tmp_path: Path, target: str) -> None:
    """A post-construction pathname replacement never reaches the helper."""
    receipt = _staging(tmp_path)
    host = FakeHost()
    prepared = prepare_vault_application_rotation(
        receipt,
        host=host,
        control_plane_candidate_image_id=_IMAGE,
        application_build_results_fingerprint="sha256:" + "4" * 64,
    )
    plan_path = (tmp_path / "plan.json").resolve()
    retain_rotation_plan(plan_path, prepared.plan)
    runner = FakeCommandRunner()
    adapter = DualNetworkRotationAdapter(
        runner,
        prepared,
        plan_path=plan_path,
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
    )
    replaced = {
        "plan": plan_path,
        "source": prepared.source_root,
        "candidate": prepared.candidate_root,
    }[target]
    moved = replaced.with_name(replaced.name + "-original")
    replaced.rename(moved)
    if target == "plan":
        replaced.write_bytes(moved.read_bytes())
        replaced.chmod(0o600)
    else:
        replaced.mkdir(mode=0o700)
        for item in moved.iterdir():
            replacement = replaced / item.name
            replacement.write_bytes(item.read_bytes())
            replacement.chmod(0o600)

    with pytest.raises(Exception, match="ROTATION_NETWORK_INPUT_DRIFT"):
        adapter.replace(prepared.credentials.candidate)
    assert runner.calls == []


def test_runner_time_complete_path_swap_is_rejected_in_image(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-image fingerprint guard closes the post-validation runner window."""
    build_fingerprint = "sha256:" + "4" * 64
    receipt = _staging(tmp_path)
    prepared = prepare_vault_application_rotation(
        receipt,
        host=FakeHost(),
        control_plane_candidate_image_id=_IMAGE,
        application_build_results_fingerprint=build_fingerprint,
    )
    plan_path = (tmp_path / "plan.json").resolve()
    retain_rotation_plan(plan_path, prepared.plan)

    alternate_root = (tmp_path / "alternate").resolve()
    alternate_root.mkdir(mode=0o700)
    alternate = prepare_vault_application_rotation(
        _staging(alternate_root, legacy_accesses=True),
        host=FakeHost(),
        control_plane_candidate_image_id=_IMAGE,
        application_build_results_fingerprint=build_fingerprint,
    )
    alternate_plan = (tmp_path / "alternate-plan.json").resolve()
    retain_rotation_plan(alternate_plan, alternate.plan)
    effect_calls: list[str] = []

    def effect_attempt(*_args: object, **_kwargs: object) -> None:
        effect_calls.append("reconcile")

    monkeypatch.setattr(
        network_rotation,
        "reconcile",
        effect_attempt,
    )

    class RunnerTimeSwap:
        def run(self, arguments: tuple[str, ...]) -> bool:
            assert arguments
            raise AssertionError("unexpected run")

        def seal(self, name: str, source_descriptor: int, output: Path) -> bool:
            assert name
            assert source_descriptor >= 0
            assert output
            raise AssertionError("unexpected seal")

        def read(self, arguments: tuple[str, ...], *, max_bytes: int) -> bytes | None:
            assert arguments[1:3] == ("--action", "reconcile")
            for original, replacement in (
                (plan_path, alternate_plan),
                (prepared.source_root, alternate.source_root),
                (prepared.candidate_root, alternate.candidate_root),
            ):
                original.rename(original.with_name(original.name + "-authorized"))
                replacement.rename(original)
            helper_argv = [
                "reconcile",
                "--target",
                "candidate",
                "--plan",
                str(plan_path),
                "--authorized-plan-fingerprint",
                prepared.plan.plan_fingerprint,
                "--expected-control-plane-image-id",
                _IMAGE,
                "--predecessor-directory",
                str(prepared.source_root),
                "--candidate-directory",
                str(prepared.candidate_root),
                "--root-credential-directory",
                str(prepared.candidate_root),
            ]
            assert network_rotation.main(helper_argv) == 2
            captured = capsys.readouterr()
            assert captured.out == ""
            assert captured.err == "ROTATION_NETWORK_NOT_READY\n"
            assert max_bytes >= 1
            return None

    adapter = DualNetworkRotationAdapter(
        RunnerTimeSwap(),
        prepared,
        plan_path=plan_path,
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
    )
    with pytest.raises(Exception, match="ROTATION_NETWORK_PROVIDER_FAILED"):
        adapter.replace(prepared.credentials.candidate)
    assert effect_calls == []


def test_dual_network_uses_rotated_primary_root_from_candidate_snapshot(
    tmp_path: Path,
) -> None:
    """Application IAM work cannot reuse the rejected predecessor Primary root."""
    receipt = _staging(tmp_path)
    prepared = prepare_vault_application_rotation(
        receipt,
        host=FakeHost(),
        control_plane_candidate_image_id=_IMAGE,
        application_build_results_fingerprint="sha256:" + "4" * 64,
    )
    plan_path = (tmp_path / "plan.json").resolve()
    retain_rotation_plan(plan_path, prepared.plan)
    assert (prepared.source_root / "vault-primary-root-access").read_bytes() != (
        prepared.candidate_root / "vault-primary-root-access"
    ).read_bytes()

    class RootPathRunner(FakeCommandRunner):
        def read(self, arguments: tuple[str, ...], *, max_bytes: int) -> bytes | None:
            self.calls.append(arguments)
            root_index = arguments.index("--root-credential-directory")
            assert arguments[root_index + 1] == str(prepared.candidate_root)
            assert arguments[root_index + 1] != str(prepared.source_root)
            assert max_bytes >= 1
            return None

    runner = RootPathRunner()
    adapter = DualNetworkRotationAdapter(
        runner,
        prepared,
        plan_path=plan_path,
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
    )
    with pytest.raises(Exception, match="ROTATION_NETWORK_PROVIDER_FAILED"):
        adapter.replace(prepared.credentials.candidate)
    assert len(runner.calls) == 1


def test_plaintext_cleanup_replays_after_each_irreversible_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each deletion is pre-journaled and terminal replay needs no plaintext root."""
    build_fingerprint = "sha256:" + "4" * 64
    prepared, host, runner, sealed = _concrete_host(
        tmp_path,
        monkeypatch,
        application_build_results_fingerprint=build_fingerprint,
    )
    retain_rotation_plan((tmp_path / "plan.json").resolve(), prepared.plan)
    receipt = (tmp_path / "staging-receipt.json").resolve()
    staged = host.stage_candidate(prepared.plan, prepared.candidate_root)
    host.stop_and_check(prepared.plan)
    switched = host.switch_candidate(prepared.plan, staged)
    host.restart_and_check(prepared.plan, binding_ref=prepared.plan.candidate_binding_ref)
    host.record_acceptance(prepared.plan)
    original_remove = host._remove_exact_plaintext

    def crash_after_source(root: Path) -> bool:
        removed = original_remove(root)
        if root == prepared.source_root:
            raise RuntimeError("simulated crash")
        return removed

    monkeypatch.setattr(host, "_remove_exact_plaintext", crash_after_source)
    with pytest.raises(RuntimeError, match="simulated crash"):
        host.finalize_success(prepared.plan, switched)
    journal_path = tmp_path / "state" / prepared.plan.rotation_id / "state.json"
    assert json.loads(journal_path.read_bytes())["phase"] == "CLEANING_SOURCE"
    assert not prepared.source_root.exists()
    assert prepared.candidate_root.is_dir()

    resumed = TransactionalFlatHostCredentialSet(
        sealed,
        (tmp_path / "state").resolve(),
        prepared.plan,
        runner=runner,
        source_root=prepared.source_root,
        candidate_root=prepared.candidate_root,
        runtime_credential_root=(tmp_path / "runtime").resolve(),
        authorized_plan_fingerprint=prepared.plan.plan_fingerprint,
        host_owner_uid=tmp_path.stat().st_uid,
        staging_owner_uid=tmp_path.stat().st_uid,
    )
    resumed_remove = resumed._remove_exact_plaintext

    def crash_after_candidate(root: Path) -> bool:
        removed = resumed_remove(root)
        if root == prepared.candidate_root:
            raise RuntimeError("simulated crash")
        return removed

    monkeypatch.setattr(resumed, "_remove_exact_plaintext", crash_after_candidate)
    with pytest.raises(RuntimeError, match="simulated crash"):
        resumed.finalize_success(prepared.plan, switched)
    assert json.loads(journal_path.read_bytes())["phase"] == "CLEANING_CANDIDATE"
    assert not prepared.source_root.exists()
    assert not prepared.candidate_root.exists()

    replay_plan, replay_binding = _terminal_replay_plan(
        receipt,
        (tmp_path / "plan.json").resolve(),
        control_plane_candidate_image_id=_IMAGE,
        application_build_results_fingerprint=build_fingerprint,
    )
    assert replay_binding.source_root == prepared.source_root
    assert replay_binding.candidate_root == prepared.candidate_root
    terminal = TransactionalFlatHostCredentialSet(
        sealed,
        (tmp_path / "state").resolve(),
        replay_plan,
        runner=runner,
        source_root=replay_binding.source_root,
        candidate_root=replay_binding.candidate_root,
        runtime_credential_root=(tmp_path / "runtime").resolve(),
        authorized_plan_fingerprint=replay_plan.plan_fingerprint,
        host_owner_uid=tmp_path.stat().st_uid,
        staging_owner_uid=tmp_path.stat().st_uid,
    )
    report_path = (tmp_path / "state" / "rotation-report.json").resolve()
    report = complete_terminal_cleanup(
        plan=replay_plan,
        host=terminal,
        report_path=report_path,
    )
    assert report.state is RotationState.SUCCEEDED
    assert json.loads(journal_path.read_bytes())["phase"] == "TERMINAL"

    replayed_terminal = TransactionalFlatHostCredentialSet(
        sealed,
        (tmp_path / "state").resolve(),
        replay_plan,
        runner=runner,
        source_root=replay_binding.source_root,
        candidate_root=replay_binding.candidate_root,
        runtime_credential_root=(tmp_path / "runtime").resolve(),
        authorized_plan_fingerprint=replay_plan.plan_fingerprint,
        host_owner_uid=tmp_path.stat().st_uid,
        staging_owner_uid=tmp_path.stat().st_uid,
    )
    assert (
        complete_terminal_cleanup(
            plan=replay_plan,
            host=replayed_terminal,
            report_path=report_path,
        )
        == report
    )


def test_dual_network_helper_uses_exact_image_and_narrow_read_only_mounts() -> None:
    """The host wrapper never mounts either broad credential directory."""
    script = (
        Path(__file__).resolve().parents[2]
        / "infrastructure/poc/libexec/asklegal-vault-application-rotation-network"
    ).read_text()
    assert "/usr/bin/docker image inspect --format '{{.Id}}' \"$image_id\"" in script
    assert '--expected-control-plane-image-id "$image_id"' in script
    assert '--authorized-plan-fingerprint "$authorized_plan_fingerprint"' in script
    assert "src=${predecessor}/${name},dst=/run/rotation/predecessor/${name},readonly" in script
    assert "src=${candidate}/${name},dst=/run/rotation/candidate/${name},readonly" in script
    assert "src=${roots}/${name},dst=/run/rotation/roots/${name},readonly" in script
    assert "src=${predecessor},dst=/run/rotation/predecessor" not in script
    assert "src=${candidate},dst=/run/rotation/candidate" not in script
    assert (
        script.index("--network asklegal-vault-primary")
        < script.index("/usr/bin/docker network connect asklegal-vault-recovery")
        < script.index("/usr/bin/docker start --attach")
    )


def test_cli_retains_value_free_plan_and_explicit_not_ready_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The operator CLI has no execute mode and exits nonzero for missing adapters."""
    receipt = _staging(tmp_path)
    host = FakeHost()

    def inspector(_root: Path) -> FakeHost:
        return host

    monkeypatch.setattr(
        "tools.hk_v1_vault_application_rotation.FlatSealedPredecessorInspector",
        inspector,
    )

    def provenance(**_kwargs: object) -> tuple[str, str]:
        return _IMAGE, "sha256:" + "4" * 64

    monkeypatch.setattr(
        "tools.hk_v1_vault_application_rotation._candidate_image_provenance",
        provenance,
    )
    plan = (tmp_path / "plan.json").resolve()
    preflight = (tmp_path / "preflight.json").resolve()
    staged = json.loads(receipt.read_bytes())
    root_plan = (tmp_path / "root-plan.json").resolve()
    root_plan_body = {
        "application_build_results_fingerprint": "sha256:" + "4" * 64,
        "candidate_binding_ref": staged["candidate_binding_ref"],
        "candidate_runtime_configuration_ref": "runtimecfg_" + "8" * 64,
        "control_plane_candidate_image_id": _IMAGE,
        "credential_names": ["vault-primary-root-access", "vault-primary-root-secret"],
        "predecessor_binding_ref": staged["predecessor_binding_ref"],
        "predecessor_runtime_configuration_ref": "runtimecfg_" + "7" * 64,
        "predecessor_sealed_state_ref": "sealed_" + "6" * 64,
        "rotation_id": _ROTATION,
        "staging_receipt_fingerprint": staged["fingerprint"],
        "stopped_units": [
            "asklegal-acquisition-worker.service",
            "asklegal-control-plane.service",
            "asklegal-legal-processing-worker.service",
            "asklegal-promotion-worker.service",
            "asklegal-review-api.service",
            "asklegal-vault-bootstrap.service",
            "asklegal-vault-primary.service",
        ],
        "vault_data_state_ref": "vaultdata_" + "5" * 64,
    }
    root_plan_fingerprint = (
        "sha256:" + sha256(canonicalize(checked_json_value(root_plan_body))).hexdigest()
    )
    root_plan.write_bytes(
        canonicalize(
            checked_json_value(
                {
                    **root_plan_body,
                    "plan_fingerprint": root_plan_fingerprint,
                    "schema_id": "asklegal.hk-v1-primary-vault-root-rotation-plan",
                    "schema_version": "1.0.0",
                }
            )
        )
    )
    root_plan.chmod(0o600)
    root_report = (tmp_path / "root-report.json").resolve()
    root_report.write_bytes(
        root_rotation_report_bytes(
            PrimaryVaultRootRotationReport(
                plan_fingerprint=root_plan_fingerprint,
                staging_receipt_fingerprint=staged["fingerprint"],
                candidate_binding_ref=staged["candidate_binding_ref"],
                rotation_id=_ROTATION,
                state=RootRotationState.SUCCEEDED,
                complete=True,
                new_root_accepted=True,
                old_root_rejected=True,
                vault_data_preserved=True,
                docker_configuration_value_free=True,
                predecessor_restored=False,
                candidate_sealed_absent=False,
                staging_retained_for_application_rotation=True,
                blocker_codes=(),
            )
        )
    )
    root_report.chmod(0o600)

    assert (
        main(
            [
                "preflight",
                "--staging-receipt",
                str(receipt),
                "--primary-root-rotation-plan",
                str(root_plan),
                "--primary-root-rotation-report",
                str(root_report),
                "--sealed-root",
                str((tmp_path / "unused-sealed").resolve()),
                "--plan-output",
                str(plan),
                "--preflight-output",
                str(preflight),
                "--application-build-results",
                str((tmp_path / "build-results.json").resolve()),
                "--application-image-inputs",
                str((tmp_path / "image-inputs.json").resolve()),
                "--workspace-root",
                str(tmp_path.resolve()),
            ]
        )
        == 0
    )

    output = capsys.readouterr()
    assert not output.err
    assert json.loads(output.out)["state"] == "READY"
    assert parse_rotation_plan_bytes(plan.read_bytes()).rotation_id == _ROTATION
    assert preflight.stat().st_mode & 0o777 == 0o600
    assert b"old-value" not in plan.read_bytes() + preflight.read_bytes()
    assert b"new-value" not in plan.read_bytes() + preflight.read_bytes()


@pytest.mark.parametrize("operation", ["stage", "stop", "switch", "restart-new", "finalize"])
def test_each_host_failure_requires_proved_rollback(tmp_path: Path, operation: str) -> None:
    """Every pre-cleanup host failure takes the same exact rollback path."""
    prepared, host, identities, authenticator = _prepared(tmp_path)
    host.fail = operation

    report = execute_vault_application_rotation(
        prepared,
        host=host,
        identities=identities,
        authenticator=authenticator,
    )

    if operation == "stop":
        assert report.state is RotationState.BLOCKED
        assert RotationBlocker.ROLLBACK_NOT_PROVED in report.blocker_codes
        assert not report.predecessor_restored
    else:
        assert report.state is RotationState.ROLLED_BACK
        assert not report.complete
        assert report.predecessor_restored
    with pytest.raises(Exception, match="ROTATION_REPORT_NOT_SUCCEEDED"):
        parse_succeeded_rotation_report_bytes(rotation_report_bytes(report))
