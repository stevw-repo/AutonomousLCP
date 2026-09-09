"""Focused tests for the mutation-free Hong Kong V1 host reconcile planner."""

# pyright: reportArgumentType=false, reportPrivateUsage=false

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from tools.hk_v1_host_reconcile import (
    HostReconcileBlocker,
    HostReconcileMode,
    build_application_build_results,
    build_host_reconcile_plan,
    host_reconcile_plan_document,
    main,
)
from tools.hk_v1_rotate_credentials import (
    CredentialManifestEntry,
    build_credential_manifest,
    credential_rotation_plan_bytes,
    plan_rotation,
)
from tools.hk_v1_vault_application_rotation import (
    RotationState,
    VaultApplicationRotationPlan,
    VaultApplicationRotationReport,
    _fingerprint,
    _plan_body,
    rotation_plan_bytes,
    rotation_report_bytes,
)
from tools.v1_poc_collect_host_facts import (
    HKV1HostFacts,
    HostFactClass,
    HostFactClassOutcome,
    HostFactFailureCode,
    build_hk_v1_host_facts,
    write_host_facts_output,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _legacy_facts() -> dict[str, object]:
    networks = {
        "asklegal-register": "10.90.0.0/24",
        "asklegal-scheduler-general": "10.90.1.0/24",
        "asklegal-scheduler-promotion": "10.90.2.0/24",
        "asklegal-vault-primary": "10.90.3.0/24",
        "asklegal-vault-recovery": "10.90.4.0/24",
        "asklegal-review": "10.90.5.0/24",
        "asklegal-telemetry": "10.90.6.0/24",
        "asklegal-egress-source": "10.90.7.0/24",
        "asklegal-egress-model": "10.90.8.0/24",
        "asklegal-egress-promotion": "10.90.9.0/24",
    }
    return {
        "schema_version": 1,
        "source": "READ_ONLY_HOST_FACTS",
        "os": {"id": "ubuntu", "version_id": "24.04"},
        "architecture": "x86_64",
        "memory_bytes": 67_252_903_936,
        "physical_disks": [
            {"stable_id": "disk-poc-data", "size_bytes": 4_000_787_030_016},
            {"stable_id": "disk-poc-root", "size_bytes": 500_107_862_016},
            {"stable_id": "disk-poc-spare", "size_bytes": 500_107_862_016},
        ],
        "paths": [
            {
                "path": path,
                "real_path": path,
                "fs_type": "ext4",
                "physical_disk_id": "disk-poc-data",
                "symlink": False,
                "writable": True,
            }
            for path in (
                "/srv/asklegal/sql",
                "/srv/asklegal/vault-primary",
                "/srv/asklegal/vault-recovery",
            )
        ],
        "time": {"synchronized": True},
        "credentials": {
            "systemd_creds_available": True,
            "protection_mode": "TPM2_PLUS_HOST_KEY",
            "encrypted_blob_mode": "0400",
            "persistent_plaintext_credential_paths": [],
        },
        "firewall": {
            "nftables_available": True,
            "input_default": "DROP",
            "forward_default": "DROP",
            "direct_container_egress_default": "DROP",
            "public_tcp_ports": [],
        },
        "journal": {"storage": "PERSISTENT", "forward_secure_sealing": True},
        "container_runtime": {
            "name": "docker",
            "service_manager": "systemd",
            "docker_group_non_root_members": ["docpro"],
        },
        "host_packages": {
            "ca-certificates": "20260601~24.04.1",
            "containerd.io": "2.3.3-1~ubuntu.24.04~noble",
            "docker-ce": "5:29.7.2-1~ubuntu.24.04~noble",
            "docker-ce-cli": "5:29.7.2-1~ubuntu.24.04~noble",
            "e2fsprogs": "1.47.0-2.4~exp1ubuntu4.1",
            "nftables": "1.0.9-1ubuntu0.1",
            "systemd": "255.4-1ubuntu8.17",
            "systemd-timesyncd": "255.4-1ubuntu8.17",
            "util-linux": "2.39.3-9ubuntu6.6",
        },
        "private_subnets": {
            "declared": networks,
            "foreign": ["10.2.0.2/32", "172.17.0.1/16", "192.168.9.126/22"],
        },
        "containers": [
            {
                "health": "NONE",
                "image_id": image_id,
                "name": f"asklegal-{service_id}",
                "runtime_state": "running",
            }
            for service_id, image_id in (
                (
                    "acquisition-worker",
                    "sha256:7b7a682205619f4a7c7d62ade6ad032fee6a42b8241e8d8c1b01309d769acdce",
                ),
                (
                    "control-plane",
                    "sha256:228697a7bee8ddd326c40178a7b02d45ef1a49dadadf266af74ccbfe63a79a1f",
                ),
                (
                    "legal-processing-worker",
                    "sha256:517cc91afe52e3e6b0ed8ac2e11edd159b2626fab089633628c644aab7faf9ad",
                ),
                (
                    "promotion-worker",
                    "sha256:8ce6125c02ad4d2d1c63c62dac129c39fb5fb52be152321e6cff0988b48b0c04",
                ),
                (
                    "review-api",
                    "sha256:f9f2b1694f915bc6470c4ed3af04720f1dbb6813d6e179500c655248e6eb0189",
                ),
            )
        ],
    }


def _complete_envelope() -> HKV1HostFacts:
    return build_hk_v1_host_facts(
        legacy_facts=_legacy_facts(),
        outcomes=tuple(
            HostFactClassOutcome(fact_class=fact_class, collected=True, failure_code=None)
            for fact_class in HostFactClass
        ),
    )


def _build_results(path: Path) -> Path:
    image_inputs = json.loads(
        (REPOSITORY_ROOT / "infrastructure/poc/application_image_inputs.json").read_bytes()
    )
    rows = tuple(
        (
            str(item["artifact_id"]),
            f"asklegal/{item['artifact_id']}:hk-v1-candidate",
            "sha256:" + f"{index:x}" * 64,
            f"{index:x}" * 128,
        )
        for index, item in enumerate(image_inputs["images"], start=1)
    )
    path.write_bytes(build_application_build_results(image_inputs, rows, root=REPOSITORY_ROOT))
    return path


def _incomplete_envelope() -> HKV1HostFacts:
    return build_hk_v1_host_facts(
        legacy_facts=_legacy_facts(),
        outcomes=tuple(
            HostFactClassOutcome(
                fact_class=fact_class,
                collected=fact_class is not HostFactClass.CONTAINERS_IMAGES_HEALTH,
                failure_code=(
                    None
                    if fact_class is not HostFactClass.CONTAINERS_IMAGES_HEALTH
                    else HostFactFailureCode.NOT_FOUND
                ),
            )
            for fact_class in HostFactClass
        ),
    )


def test_plan_is_canonical_exact_and_never_authorizes_or_performs_mutation() -> None:
    """A repeated preflight is byte-stable and incapable of mutation."""
    first = build_host_reconcile_plan(REPOSITORY_ROOT, _complete_envelope())
    second = build_host_reconcile_plan(REPOSITORY_ROOT, _complete_envelope())

    assert first == second
    assert first.mode is HostReconcileMode.PLAN
    assert first.mutation_authorized is False
    assert first.mutations_performed == ()
    assert len(first.actions) == 6
    image_binding = first.application_image_inputs_fingerprint
    assert first.actions[:5] == (
        "001|BUILD_APPLICATION_IMAGE|service=acquisition-worker|context=apps/acquisition-worker|tag=asklegal/acquisition-worker:hk-v1-candidate|inputs="
        + image_binding,
        "002|BUILD_APPLICATION_IMAGE|service=control-plane|context=apps/control-plane|tag=asklegal/control-plane:hk-v1-candidate|inputs="
        + image_binding,
        "003|BUILD_APPLICATION_IMAGE|service=legal-processing-worker|context=apps/legal-processing-worker|tag=asklegal/legal-processing-worker:hk-v1-candidate|inputs="
        + image_binding,
        "004|BUILD_APPLICATION_IMAGE|service=promotion-worker|context=apps/promotion-worker|tag=asklegal/promotion-worker:hk-v1-candidate|inputs="
        + image_binding,
        "005|BUILD_APPLICATION_IMAGE|service=review-api|context=apps/review-api|tag=asklegal/review-api:hk-v1-candidate|inputs="
        + image_binding,
    )
    assert first.actions[-1] == (
        "006|RECOLLECT_HOST_FACTS|output=var/hk-v1/host/post-image-build.json|"
        "required=immutable-image-digests"
    )
    assert first.rollback.state == "CANDIDATE_IMAGES_NOT_ACTIVATED"
    preserve_review = (
        "001|PRESERVE_RUNNING_IMAGE|service=review-api|"
        "image_id=sha256:f9f2b1694f915bc6470c4ed3af04720f1dbb6813d6e179500c655248e6eb0189"
    )
    preserve_promotion = (
        "002|PRESERVE_RUNNING_IMAGE|service=promotion-worker|"
        "image_id=sha256:8ce6125c02ad4d2d1c63c62dac129c39fb5fb52be152321e6cff0988b48b0c04"
    )
    preserve_legal = (
        "003|PRESERVE_RUNNING_IMAGE|service=legal-processing-worker|"
        "image_id=sha256:517cc91afe52e3e6b0ed8ac2e11edd159b2626fab089633628c644aab7faf9ad"
    )
    preserve_control = (
        "004|PRESERVE_RUNNING_IMAGE|service=control-plane|"
        "image_id=sha256:228697a7bee8ddd326c40178a7b02d45ef1a49dadadf266af74ccbfe63a79a1f"
    )
    preserve_acquisition = (
        "005|PRESERVE_RUNNING_IMAGE|service=acquisition-worker|"
        "image_id=sha256:7b7a682205619f4a7c7d62ade6ad032fee6a42b8241e8d8c1b01309d769acdce"
    )
    assert first.rollback.actions == (
        preserve_review,
        preserve_promotion,
        preserve_legal,
        preserve_control,
        preserve_acquisition,
    )
    assert first.fingerprint.startswith("sha256:")
    assert first.fingerprint == second.fingerprint
    assert first.runtime_commands_fingerprint.startswith("sha256:")
    assert first.application_image_inputs_fingerprint.startswith("sha256:")
    assert len(first.targets) == len(set(first.targets))
    assert tuple(sorted(first.targets)) == first.targets
    assert "service:asklegal-control-plane.service" in first.targets
    assert "timer:asklegal-ordinary-observation.timer" in first.targets
    assert "network:asklegal-register" in first.targets
    assert "path:/srv/asklegal/sql" in first.targets
    assert "target:asklegal.target" in first.targets
    assert (
        "unit-source:infrastructure/poc/units/asklegal-control-plane.service->/etc/systemd/system/asklegal-control-plane.service"
        in first.targets
    )
    assert (
        "image-build:control-plane:asklegal/control-plane:hk-v1-candidate:apps/control-plane"
        in first.targets
    )
    assert (
        "bootstrap-helper-source:infrastructure/poc/libexec/asklegal-register-migrate->"
        "/usr/local/libexec/asklegal-register-migrate" in first.targets
    )
    assert (
        "bootstrap-helper-source:infrastructure/poc/libexec/asklegal-vault-bootstrap->"
        "/usr/local/libexec/asklegal-vault-bootstrap" in first.targets
    )
    assert (
        "bootstrap-helper-source:infrastructure/poc/libexec/asklegal-vault-application-rotation-network->"
        "/usr/local/libexec/asklegal-vault-application-rotation-network" in first.targets
    )
    assert (
        "migration-source:packages/management-register-adapter/migrations->"
        "/opt/asklegal/management-register/migrations" in first.targets
    )


def test_incomplete_snapshot_remains_fail_closed_with_no_proposed_actions() -> None:
    """Missing one required fact class cannot produce a mutation proposal."""
    plan = build_host_reconcile_plan(REPOSITORY_ROOT, _incomplete_envelope())

    assert HostReconcileBlocker.HOST_FACTS_INCOMPLETE in plan.blockers
    assert plan.actions == ()
    assert plan.rollback.state == "NOT_READY_INCOMPLETE_HOST_FACTS"
    assert plan.rollback.actions == ()


def test_exact_retained_build_results_advance_to_digest_pinned_deploy_phase(
    tmp_path: Path,
) -> None:
    """Replanning must consume retained build readback instead of rebuilding static tags forever."""
    plan = build_host_reconcile_plan(
        REPOSITORY_ROOT,
        _complete_envelope(),
        application_build_results=_build_results(tmp_path / "application-build-results.json"),
    )

    assert HostReconcileBlocker.APPLICATION_IMAGE_PINS_REQUIRED not in plan.blockers
    assert plan.application_build_results_fingerprint is not None
    assert plan.actions[0].startswith("001|PROVISION_RUNTIME_PATHS|")
    assert plan.actions[4].startswith("005|APPLY_HOST_FIREWALL|")
    replacements = [item for item in plan.actions if "|VERIFY_DIGEST_PINNED_CANDIDATE|" in item]
    assert len(replacements) == 5
    assert all("|candidate_tag=asklegal/" in item for item in replacements)
    assert all("|image_id=sha256:" in item for item in replacements)
    assert "|bindings=" in plan.actions[-3]
    assert plan.actions[-2] == (
        f"{len(plan.actions) - 1:03d}|RECOLLECT_HOST_FACTS|"
        "output=var/hk-v1/host/post-reconcile.json|required=all-11-fact-classes"
    )
    assert plan.actions[-1].startswith(f"{len(plan.actions):03d}|CONFIRM_HOST_FIREWALL|")
    assert plan.rollback.state == "ORDERED_REVERSIBLE_PLAN"
    assert plan.rollback.actions[7].startswith("008|RESTORE_HOST_FIREWALL|")


def test_build_results_must_bind_the_exact_application_input_fingerprint(tmp_path: Path) -> None:
    """A canonical but stale build result cannot supply deployable image identities."""
    path = _build_results(tmp_path / "application-build-results.json")
    document = json.loads(path.read_bytes())
    document["application_image_inputs_fingerprint"] = "sha256:" + "f" * 64
    unsigned = dict(document)
    unsigned.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:"
        + sha256(
            json.dumps(unsigned, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
    )
    path.write_bytes(
        json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
        + b"\n"
    )

    with pytest.raises(ValueError, match="HOST_RECONCILE_INPUT_INVALID"):
        build_host_reconcile_plan(
            REPOSITORY_ROOT,
            _complete_envelope(),
            application_build_results=path,
        )


def test_current_desired_state_exposes_blockers_instead_of_inventing_apply_actions() -> None:
    """Missing live prerequisites stay blockers rather than guessed operations."""
    plan = build_host_reconcile_plan(REPOSITORY_ROOT, _complete_envelope())

    assert plan.blockers == (
        HostReconcileBlocker.APPLICATION_IMAGE_PINS_REQUIRED,
        HostReconcileBlocker.CREDENTIAL_ROTATION_PLAN_REQUIRED,
        HostReconcileBlocker.HOST_FACTS_NONCONFORMING,
        HostReconcileBlocker.HOST_MUTATION_NOT_AUTHORIZED,
        HostReconcileBlocker.RECOVERY_PREFLIGHT_REPORT_REQUIRED,
    )
    assert "desired-service:prometheus" not in plan.targets
    assert "desired-service:grafana" not in plan.targets
    assert "credential:grafana-admin" not in plan.targets


def test_cli_defaults_to_plan_and_refuses_apply_before_reading_inputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI defaults to plan while an apply request fails before reading files."""
    facts_path = tmp_path / "facts.json"
    output = tmp_path / "plan.json"
    write_host_facts_output(_complete_envelope(), facts_path)

    assert main(["--facts", str(facts_path), "--output", str(output)]) == 0
    first = output.read_bytes()
    assert json.loads(first)["mode"] == "PLAN"
    assert json.loads(first)["mutations_performed"] == []
    assert main(["--mode", "plan", "--facts", str(facts_path), "--output", str(output)]) == 0
    assert output.read_bytes() == first
    assert "PLAN_ONLY" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        main(["--mode", "apply", "--facts", "/does/not/exist", "--output", str(output)])
    assert output.read_bytes() == first


def test_plan_document_round_trips_without_fingerprint_self_reference() -> None:
    """Keep the digest stable by excluding its own field from the signed projection."""
    plan = build_host_reconcile_plan(REPOSITORY_ROOT, _complete_envelope())
    document = host_reconcile_plan_document(plan)

    assert document["fingerprint"] == plan.fingerprint
    assert document["runtime_commands_fingerprint"] == plan.runtime_commands_fingerprint
    assert document["authority_required"] == [
        "EXACT_FINGERPRINTED_HOST_RECONCILE_PLAN",
        "SEPARATE_POST_APPLY_REBOOT_AUTHORITY",
    ]


def _credential_plan(path: Path) -> None:
    manifest = build_credential_manifest(
        (CredentialManifestEntry("sql-control", ("asklegal-control-plane.service",)),)
    )
    plan = plan_rotation(
        manifest,
        credential_name="sql-control",
        rotation_id="rot_" + "1" * 48,
        predecessor_binding_ref="binding_" + "2" * 48,
        candidate_binding_ref="binding_" + "3" * 48,
    )
    path.write_bytes(credential_rotation_plan_bytes(plan) + b"\n")


def _recovery_preflight(path: Path, *, status: str = "PREFLIGHT_READY") -> None:
    blockers = [] if status == "PREFLIGHT_READY" else ["SQL_INPUT_NOT_READY"]
    operation_id = "r_" + "4" * 32
    request_fingerprint = "sha256:" + "5" * 64
    token = sha256(f"{operation_id}|{request_fingerprint}".encode()).hexdigest()[:24]

    def opaque(*parts: str) -> str:
        return f"r_{sha256('|'.join(parts).encode()).hexdigest()[:32]}"

    document = {
        "assessment_fingerprint": None,
        "blockers": blockers,
        "live_recovery_proved": False,
        "local_contract_proved": False,
        "mode": "PREFLIGHT",
        "operation_id": operation_id,
        "request_fingerprint": request_fingerprint,
        "schema": "asklegal.hk-v1-local-recovery-result/v1",
        "status": status,
        "targets": {
            "scheduler_directory_name": f"asklegal-recovery-scheduler-{token}",
            "sql_database_identity": opaque(token, "sql-database"),
            "sql_database_name": f"asklegal_recovery_sql_{token}",
            "vault_directory_name": f"asklegal-recovery-vault-{token}",
            "vault_identity": opaque(token, "vault"),
        },
    }
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n")


def _batch_rotation(plan_path: Path, report_path: Path) -> VaultApplicationRotationPlan:
    names = (
        "vault-primary-acquisition",
        "vault-primary-control",
        "vault-primary-processing",
        "vault-primary-promotion",
        "vault-primary-review",
        "vault-recovery-acquisition",
        "vault-recovery-promotion",
    )
    units = (
        (names[0], ("asklegal-acquisition-worker.service",)),
        (names[1], ("asklegal-control-plane.service",)),
        (names[2], ("asklegal-legal-processing-worker.service",)),
        (names[3], ("asklegal-promotion-worker.service",)),
        (names[4], ("asklegal-review-api.service",)),
        (names[5], ("asklegal-acquisition-worker.service",)),
        (names[6], ("asklegal-promotion-worker.service",)),
    )
    dependent = (
        "asklegal-acquisition-worker.service",
        "asklegal-control-plane.service",
        "asklegal-legal-processing-worker.service",
        "asklegal-promotion-worker.service",
        "asklegal-review-api.service",
    )
    old = tuple((name, "1" * 64) for name in names)
    new = tuple((name, "2" * 64) for name in names)
    arguments = {
        "rotation_id": "rot_" + "3" * 48,
        "staging_receipt_fingerprint": "sha256:" + "4" * 64,
        "predecessor_binding_ref": "binding_" + "5" * 48,
        "candidate_binding_ref": "binding_" + "6" * 48,
        "predecessor_sealed_state_ref": "sealed_" + "7" * 64,
        "control_plane_candidate_image_id": "sha256:" + "8" * 64,
        "application_build_results_fingerprint": "sha256:" + "9" * 64,
        "predecessor_plaintext_sha256": old,
        "candidate_plaintext_sha256": new,
    }
    plan = VaultApplicationRotationPlan(
        **arguments,
        sealed_credential_names=names,
        rotated_credential_names=names,
        credential_units=units,
        dependent_units=dependent,
        plan_fingerprint=_fingerprint(_plan_body(**arguments)),
    )
    report = VaultApplicationRotationReport(
        plan_fingerprint=plan.plan_fingerprint,
        staging_receipt_fingerprint=plan.staging_receipt_fingerprint,
        candidate_binding_ref=plan.candidate_binding_ref,
        rotation_id=plan.rotation_id,
        state=RotationState.SUCCEEDED,
        complete=True,
        new_values_accepted=True,
        old_values_rejected=True,
        predecessor_restored=False,
        candidate_sealed_absent=False,
        plaintext_absent=True,
        blocker_codes=(),
    )
    plan_path.write_bytes(rotation_plan_bytes(plan))
    report_path.write_bytes(rotation_report_bytes(report))
    return plan


def test_succeeded_batch_rotation_report_clears_only_credential_execution_blocker(
    tmp_path: Path,
) -> None:
    """Deployment binds terminal evidence, not an unexecuted batch plan."""
    plan_path = tmp_path / "batch-plan.json"
    report_path = tmp_path / "batch-report.json"
    _batch_rotation(plan_path, report_path)

    plan = build_host_reconcile_plan(
        REPOSITORY_ROOT,
        _complete_envelope(),
        vault_application_rotation_plan=plan_path,
        vault_application_rotation_report=report_path,
    )
    report_fingerprint = "sha256:" + sha256(report_path.read_bytes()).hexdigest()
    assert plan.credential_rotation_plan_fingerprint == report_fingerprint
    assert (
        HostReconcileBlocker.CREDENTIAL_ROTATION_EXECUTION_AUTHORITY_REQUIRED not in plan.blockers
    )
    assert HostReconcileBlocker.CREDENTIAL_ROTATION_REPORT_INVALID not in plan.blockers
    assert f"credential-rotation-report:{report_fingerprint}" in plan.targets

    report = json.loads(report_path.read_bytes())
    report["candidate_binding_ref"] = "binding_" + "a" * 48
    report_path.write_bytes(json.dumps(report, sort_keys=True, separators=(",", ":")).encode())
    rejected = build_host_reconcile_plan(
        REPOSITORY_ROOT,
        _complete_envelope(),
        vault_application_rotation_plan=plan_path,
        vault_application_rotation_report=report_path,
    )
    assert HostReconcileBlocker.CREDENTIAL_ROTATION_REPORT_INVALID in rejected.blockers


def test_canonical_credential_and_recovery_inputs_replace_unavailable_adapter_claims(
    tmp_path: Path,
) -> None:
    """Existing local contracts become bound inputs with separate execution authority."""
    credential = tmp_path / "credential-plan.json"
    recovery = tmp_path / "recovery-preflight.json"
    _credential_plan(credential)
    _recovery_preflight(recovery)

    plan = build_host_reconcile_plan(
        REPOSITORY_ROOT,
        _complete_envelope(),
        credential_rotation_plan=credential,
        recovery_preflight_report=recovery,
    )
    without_inputs = build_host_reconcile_plan(REPOSITORY_ROOT, _complete_envelope())

    assert HostReconcileBlocker.CREDENTIAL_ROTATION_ADAPTER_UNAVAILABLE not in plan.blockers
    assert HostReconcileBlocker.RECOVERY_ADAPTER_UNAVAILABLE not in plan.blockers
    assert HostReconcileBlocker.CREDENTIAL_ROTATION_EXECUTION_AUTHORITY_REQUIRED in plan.blockers
    assert HostReconcileBlocker.RECOVERY_EXECUTION_AUTHORITY_REQUIRED in plan.blockers
    assert plan.credential_rotation_plan_fingerprint is not None
    assert plan.recovery_preflight_report_fingerprint is not None
    assert plan.credential_rotation_plan_fingerprint.startswith("sha256:")
    assert plan.recovery_preflight_report_fingerprint.startswith("sha256:")
    assert plan.fingerprint != without_inputs.fingerprint
    assert plan.authority_required == (
        "EXACT_FINGERPRINTED_HOST_RECONCILE_PLAN",
        "SEPARATE_POST_APPLY_REBOOT_AUTHORITY",
        "EXACT_CREDENTIAL_ROTATION_EXECUTION_AUTHORITY",
        "EXACT_LOCAL_RECOVERY_EXECUTION_AUTHORITY",
    )
    assert plan.actions
    assert plan.mutations_performed == ()


def test_invalid_and_not_ready_optional_inputs_are_distinct_inert_blockers(
    tmp_path: Path,
) -> None:
    """Malformed input and a valid negative preflight are never collapsed into no adapter."""
    credential = tmp_path / "credential-plan.json"
    recovery = tmp_path / "recovery-preflight.json"
    credential.write_text('{"not":"canonical"}', encoding="utf-8")
    _recovery_preflight(recovery, status="NOT_READY")

    plan = build_host_reconcile_plan(
        REPOSITORY_ROOT,
        _complete_envelope(),
        credential_rotation_plan=credential,
        recovery_preflight_report=recovery,
    )

    assert HostReconcileBlocker.CREDENTIAL_ROTATION_PLAN_INVALID in plan.blockers
    assert HostReconcileBlocker.RECOVERY_PREFLIGHT_NOT_READY in plan.blockers
    assert HostReconcileBlocker.RECOVERY_EXECUTION_AUTHORITY_REQUIRED not in plan.blockers
    assert plan.credential_rotation_plan_fingerprint is None
    assert plan.recovery_preflight_report_fingerprint is not None
    assert plan.recovery_preflight_report_fingerprint.startswith("sha256:")


def test_cli_binds_both_optional_artifacts_without_invoking_them(tmp_path: Path) -> None:
    """Optional CLI inputs alter only the canonical plan lineage and blockers."""
    facts = tmp_path / "facts.json"
    credential = tmp_path / "credential-plan.json"
    recovery = tmp_path / "recovery-preflight.json"
    output = tmp_path / "plan.json"
    write_host_facts_output(_complete_envelope(), facts)
    _credential_plan(credential)
    _recovery_preflight(recovery)

    assert (
        main(
            [
                "--facts",
                str(facts),
                "--credential-rotation-plan",
                str(credential),
                "--recovery-preflight-report",
                str(recovery),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    document = json.loads(output.read_bytes())
    assert document["credential_rotation_plan_fingerprint"].startswith("sha256:")
    assert document["recovery_preflight_report_fingerprint"].startswith("sha256:")
    assert document["actions"]
    assert document["mutations_performed"] == []
