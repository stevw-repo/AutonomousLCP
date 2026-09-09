"""Focused authority and restart tests for the closed host-plan executor."""

# pyright: reportPrivateUsage=false
# ruff: noqa: SLF001

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

import tools.hk_v1_host_apply as host_apply
from tools.hk_v1_host_apply import (
    CanonicalHostFactsReadback,
    HostApplyCommandResult,
    HostApplyError,
    apply_host_plan,
    load_host_apply_state,
    main,
)
from tools.v1_poc_build_images import workspace_source_fingerprint


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )


def _fingerprint(value: object) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


_SERVICES = (
    "acquisition-worker",
    "control-plane",
    "legal-processing-worker",
    "promotion-worker",
    "review-api",
)


class _SyntheticCrash(RuntimeError):
    """Simulate abrupt process loss after one retained phase."""


def _plan(path: Path, *, actions: bool = True, incomplete: bool = False) -> bytes:
    for relative in (
        ".python-version",
        "infrastructure/poc/images/Dockerfile",
        "pyproject.toml",
        "tools/v1_poc_build_images.py",
        "uv.lock",
    ):
        source = path.parent / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(relative + "\n", encoding="utf-8")
    (path.parent / "apps").mkdir(exist_ok=True)
    (path.parent / "packages").mkdir(exist_ok=True)
    image_inputs_document = {
        "images": [
            {"application_path": f"apps/{service}", "artifact_id": service} for service in _SERVICES
        ]
    }
    image_inputs = _fingerprint(
        {
            "application_image_inputs": image_inputs_document,
            "workspace_source_fingerprint": workspace_source_fingerprint(path.parent),
        }
    )
    inputs_path = path.parent / "infrastructure/poc/application_image_inputs.json"
    inputs_path.parent.mkdir(parents=True, exist_ok=True)
    inputs_path.write_bytes(_canonical(image_inputs_document) + b"\n")
    rows = [
        f"{index:03d}|BUILD_APPLICATION_IMAGE|service={service}|context=apps/{service}|"
        f"tag=asklegal/{service}:hk-v1-candidate|inputs={image_inputs}"
        for index, service in enumerate(_SERVICES, start=1)
    ]
    rows.append(
        "006|RECOLLECT_HOST_FACTS|output=var/hk-v1/host/post-image-build.json|"
        "required=immutable-image-digests"
    )
    rollback = [
        f"{index:03d}|PRESERVE_RUNNING_IMAGE|service={service}|image_id=sha256:{index}"
        + str(index) * 63
        for index, service in enumerate(reversed(_SERVICES), start=1)
    ]
    body = {
        "actions": rows if actions else [],
        "application_build_results_fingerprint": None,
        "application_image_inputs_fingerprint": image_inputs,
        "authority_required": [
            "EXACT_FINGERPRINTED_HOST_RECONCILE_PLAN",
            "SEPARATE_POST_APPLY_REBOOT_AUTHORITY",
        ],
        "blockers": (
            ["HOST_FACTS_INCOMPLETE", "HOST_MUTATION_NOT_AUTHORIZED"]
            if incomplete
            else ["APPLICATION_IMAGE_PINS_REQUIRED", "HOST_MUTATION_NOT_AUTHORIZED"]
        ),
        "credential_rotation_plan_fingerprint": None,
        "desired_topology_fingerprint": "sha256:" + "2" * 64,
        "host_facts_fingerprint": "sha256:" + "3" * 64,
        "mode": "PLAN",
        "mutation_authorized": False,
        "mutations_performed": [],
        "recovery_preflight_report_fingerprint": None,
        "rollback": {
            "actions": rollback if actions else [],
            "state": "CANDIDATE_IMAGES_NOT_ACTIVATED",
        },
        "runtime_commands_fingerprint": "sha256:" + "4" * 64,
        "schema_version": 1,
        "systemd_inputs_fingerprint": "sha256:" + "5" * 64,
        "targets": [
            f"image-build:{service}:asklegal/{service}:hk-v1-candidate:apps/{service}"
            for service in _SERVICES
        ],
    }
    document = {**body, "fingerprint": _fingerprint(body)}
    content = _canonical(document) + b"\n"
    path.write_bytes(content)
    return content


def _deployment_plan(path: Path) -> bytes:
    for relative in (
        ".python-version",
        "infrastructure/poc/images/Dockerfile",
        "pyproject.toml",
        "tools/v1_poc_build_images.py",
        "uv.lock",
    ):
        source = path.parent / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(relative + "\n", encoding="utf-8")
    (path.parent / "apps").mkdir(exist_ok=True)
    (path.parent / "packages").mkdir(exist_ok=True)
    image_inputs_document = {
        "images": [
            {"application_path": f"apps/{service}", "artifact_id": service} for service in _SERVICES
        ]
    }
    image_inputs = _fingerprint(
        {
            "application_image_inputs": image_inputs_document,
            "workspace_source_fingerprint": workspace_source_fingerprint(path.parent),
        }
    )
    inputs_path = path.parent / "infrastructure/poc/application_image_inputs.json"
    inputs_path.parent.mkdir(parents=True, exist_ok=True)
    inputs_path.write_bytes(_canonical(image_inputs_document) + b"\n")
    helper = path.parent / "infrastructure/poc/provisioning/90-host-apply.sh"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    images = {
        service: "sha256:" + f"{index:x}" * 64 for index, service in enumerate(_SERVICES, start=1)
    }
    credential_report = "sha256:" + "d" * 64
    actions = [
        "001|PROVISION_RUNTIME_PATHS|source=infrastructure/poc/provisioning/30-identities.sh",
        (
            "002|STAGE_RUNTIME_CONFIGURATION|unit_source=infrastructure/poc/units|"
            "config_destination=/etc/asklegal|helper_source=infrastructure/poc/libexec|"
            "helper_destination=/usr/local/libexec|"
            "migration_source=packages/management-register-adapter/migrations|"
            "migration_destination=/opt/asklegal/management-register/migrations"
        ),
        "003|INSTALL_SYSTEMD_UNITS|source=infrastructure/poc/units|destination=/etc/systemd/system",
        "004|RECONCILE_NETWORKS|unit=asklegal-networks.service|source=infrastructure/poc/systemd_unit_inputs.json",
        "005|APPLY_HOST_FIREWALL|source=infrastructure/poc/provisioning/60-firewall.sh|deadman_seconds=900",
        *[
            f"{index + 5:03d}|VERIFY_DIGEST_PINNED_CANDIDATE|service={service}|"
            f"unit=asklegal-{service}.service|"
            f"candidate_tag=asklegal/{service}:hk-v1-candidate|image_id={images[service]}"
            for index, service in enumerate(_SERVICES, start=1)
        ],
        (
            "011|ENABLE_START_TARGET_AND_TIMERS|target=asklegal.target|"
            "source=infrastructure/poc/systemd_unit_inputs.json|bindings="
            + ",".join(f"{service}@{images[service]}" for service in _SERVICES)
        ),
        "012|RECOLLECT_HOST_FACTS|output=var/hk-v1/host/post-reconcile.json|required=all-11-fact-classes",
        "013|CONFIRM_HOST_FIREWALL|source=post-reconcile-host-facts|marker=/run/asklegal-firewall-confirmed",
    ]
    rollback = [
        *[
            f"{index:03d}|RESTORE_PREDECESSOR_SERVICE_IMAGE|service={service}|"
            "runtime_state=running|"
            f"image_id=sha256:{9 - index}" + f"{9 - index}" * 63
            for index, service in enumerate(reversed(_SERVICES), start=1)
        ],
        "006|RESTORE_RUNTIME_CONFIGURATION|source=state-owned-predecessor-snapshot",
        "007|RESTORE_NETWORK_SET|source=retained-host-facts",
        "008|RESTORE_HOST_FIREWALL|source=state-owned-predecessor-snapshot",
        "009|RESTORE_SYSTEMD_UNIT_BYTES|source=state-owned-predecessor-snapshot",
        "010|RECOLLECT_HOST_FACTS|output=var/hk-v1/host/post-rollback.json|required=all-11-fact-classes",
    ]
    build_results_body = {
        "application_image_inputs_fingerprint": image_inputs,
        "images": [
            {
                "application_path": f"apps/{service}",
                "image_id": images[service],
                "installed_tree_sha512": f"{index:x}" * 128,
                "service_id": service,
                "tag": f"asklegal/{service}:hk-v1-candidate",
            }
            for index, service in enumerate(_SERVICES, start=1)
        ],
        "schema_id": "asklegal.hk-v1-application-build-results/v1",
        "schema_version": "1.0.0",
    }
    build_results = (
        _canonical({**build_results_body, "fingerprint": _fingerprint(build_results_body)}) + b"\n"
    )
    build_results_path = path.parent / "var/hk-v1/host/application-build-results.json"
    build_results_path.parent.mkdir(parents=True, exist_ok=True)
    build_results_path.write_bytes(build_results)
    body = {
        "actions": actions,
        "application_build_results_fingerprint": ("sha256:" + sha256(build_results).hexdigest()),
        "application_image_inputs_fingerprint": image_inputs,
        "authority_required": [
            "EXACT_FINGERPRINTED_HOST_RECONCILE_PLAN",
            "SEPARATE_POST_APPLY_REBOOT_AUTHORITY",
        ],
        "blockers": ["HOST_MUTATION_NOT_AUTHORIZED"],
        "credential_rotation_plan_fingerprint": credential_report,
        "desired_topology_fingerprint": "sha256:" + "2" * 64,
        "host_facts_fingerprint": "sha256:" + "3" * 64,
        "mode": "PLAN",
        "mutation_authorized": False,
        "mutations_performed": [],
        "recovery_preflight_report_fingerprint": "sha256:" + "6" * 64,
        "rollback": {"actions": rollback, "state": "ORDERED_REVERSIBLE_PLAN"},
        "runtime_commands_fingerprint": "sha256:" + "4" * 64,
        "schema_version": 1,
        "systemd_inputs_fingerprint": "sha256:" + "5" * 64,
        "targets": sorted(
            [
                *[f"image-replacement:{service}:{images[service]}" for service in _SERVICES],
                f"credential-rotation-report:{credential_report}",
            ]
        ),
    }
    content = _canonical({**body, "fingerprint": _fingerprint(body)}) + b"\n"
    path.write_bytes(content)
    return content


def _authority(path: Path, plan_content: bytes, repository: Path, state_root: Path) -> None:
    plan = cast("dict[str, object]", json.loads(plan_content))
    body = {
        "actions": plan["actions"],
        "authority_id": "auth_" + "a" * 48,
        "decision": "AUTHORIZED",
        "plan_fingerprint": plan["fingerprint"],
        "repository_root": str(repository),
        "schema_id": "asklegal.hk-v1-host-apply-authority/v1",
        "schema_version": "1.0.0",
        "state_root": str(state_root),
        "targets": plan["targets"],
    }
    path.write_bytes(_canonical({**body, "fingerprint": _fingerprint(body)}))


def test_only_deployment_requires_terminal_credential_report_target(tmp_path: Path) -> None:
    """Phase one may build, but phase two refuses absent terminal rotation evidence."""
    build_path = tmp_path / "build-plan.json"
    _plan(build_path)
    assert host_apply._parse_plan(build_path).actions

    deployment_path = tmp_path / "deployment-plan.json"
    content = _deployment_plan(deployment_path)
    assert host_apply._parse_plan(deployment_path).actions
    document = cast("dict[str, object]", json.loads(content))
    body = {key: value for key, value in document.items() if key != "fingerprint"}
    body["credential_rotation_plan_fingerprint"] = None
    body["targets"] = [
        target
        for target in cast("list[str]", body["targets"])
        if not target.startswith("credential-rotation-report:")
    ]
    deployment_path.write_bytes(_canonical({**body, "fingerprint": _fingerprint(body)}) + b"\n")
    with pytest.raises(HostApplyError, match="HOST_APPLY_PLAN_NOT_ACTIONABLE"):
        host_apply._parse_plan(deployment_path)


@dataclass
class _Runner:
    fail_build: bool = False
    crash_collect: bool = False
    crash_deploy_call: int | None = None
    fail_deploy_call: int | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], *, cwd: Path) -> HostApplyCommandResult:
        assert cwd.is_absolute()
        self.calls.append(argv)
        if len(argv) > 1 and argv[1].endswith("90-host-apply.sh"):
            deployment_calls = sum(
                1 for call in self.calls if len(call) > 1 and call[1].endswith("90-host-apply.sh")
            )
            if deployment_calls == self.crash_deploy_call:
                raise _SyntheticCrash
            if deployment_calls == self.fail_deploy_call:
                return HostApplyCommandResult(1, "", "apply failed")
            return HostApplyCommandResult(0, "APPLIED\n", "")
        if argv[2:4] == ("tools.v1_poc_build_images", "--tag-suffix"):
            if self.fail_build:
                return HostApplyCommandResult(1, "", "build failed")
            lines_by_service = {
                f"{service} asklegal/{service}:hk-v1-candidate sha256:{index}"
                + str(index) * 63
                + " "
                + "b" * 128
                for index, service in enumerate(_SERVICES, start=1)
            }
            lines = [
                next(line for line in lines_by_service if line.startswith(f"{service} "))
                for service in (
                    "control-plane",
                    "review-api",
                    "acquisition-worker",
                    "legal-processing-worker",
                    "promotion-worker",
                )
            ]
            return HostApplyCommandResult(0, "\n".join(lines) + "\n", "")
        if len(argv) > 2 and argv[2] == "tools.v1_poc_collect_host_facts":
            if self.crash_collect:
                self.crash_collect = False
                raise _SyntheticCrash
            return HostApplyCommandResult(0, "PASS READ_ONLY_HOST_FACTS_WRITTEN\n", "")
        if argv[:3] == ("/usr/bin/docker", "container", "inspect"):
            service = next(reversed(argv)).removeprefix("asklegal-")
            index = tuple(reversed(_SERVICES)).index(service) + 1
            return HostApplyCommandResult(0, "sha256:" + str(index) * 64 + "\n", "")
        raise AssertionError(argv)


class _Readback:
    def fingerprint(self, path: Path) -> str:
        assert path.name in {"post-image-build.json", "post-reconcile.json", "post-rollback.json"}
        return "sha256:" + "c" * 64

    def firewall_ready(self, path: Path) -> bool:
        assert path.name == "post-reconcile.json"
        return True

    def deployment_ready(self, path: Path, expected_images: tuple[tuple[str, str], ...]) -> bool:
        assert path.name == "post-reconcile.json"
        assert tuple(service for service, _image in expected_images) == _SERVICES
        return True

    def deployment_manifest_ready(self, expected_images: tuple[tuple[str, str], ...]) -> bool:
        assert tuple(service for service, _image in expected_images) == _SERVICES
        return True

    def bootstrap_ready(self) -> bool:
        return True

    def rollback_ready(
        self,
        path: Path,
        expected_images: tuple[tuple[str, str | None, str | None], ...],
    ) -> bool:
        assert path.name == "post-rollback.json"
        assert tuple(service for service, _image, _state in expected_images) == _SERVICES
        return True


class _MismatchedDeploymentReadback(_Readback):
    def deployment_ready(self, path: Path, expected_images: tuple[tuple[str, str], ...]) -> bool:
        assert path.name == "post-reconcile.json"
        assert tuple(service for service, _image in expected_images) == _SERVICES
        return False


class _MismatchedRollbackReadback(_Readback):
    def rollback_ready(
        self,
        path: Path,
        expected_images: tuple[tuple[str, str | None, str | None], ...],
    ) -> bool:
        assert path.name == "post-rollback.json"
        assert tuple(service for service, _image, _state in expected_images) == _SERVICES
        return False


def test_rejects_incomplete_or_zero_action_plan_before_runner_or_state(tmp_path: Path) -> None:
    """An incomplete/non-actionable plan cannot become an apply request."""
    for suffix, actions, incomplete in (("empty", False, False), ("incomplete", True, True)):
        plan_path = tmp_path / f"{suffix}.json"
        content = _plan(plan_path, actions=actions, incomplete=incomplete)
        state_root = tmp_path / f"state-{suffix}"
        authority = tmp_path / f"authority-{suffix}.json"
        _authority(authority, content, tmp_path, state_root)
        runner = _Runner()

        with pytest.raises(HostApplyError, match="HOST_APPLY_PLAN_NOT_ACTIONABLE"):
            apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())

        assert runner.calls == []
        assert not state_root.exists()


def test_authority_must_bind_exact_plan_actions_targets_and_roots(tmp_path: Path) -> None:
    """A self-consistent but stale authority reaches no command or journal write."""
    plan_path = tmp_path / "plan.json"
    content = _plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    document["targets"] = []
    unsigned = dict(document)
    unsigned.pop("fingerprint")
    document["fingerprint"] = _fingerprint(unsigned)
    authority.write_bytes(_canonical(document))
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_AUTHORITY_INVALID"):
        apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())

    assert runner.calls == []
    assert not state_root.exists()


def test_image_phase_runs_fixed_argv_retains_receipts_and_replays(tmp_path: Path) -> None:
    """The current build/recollect phase stops truthfully for a new digest-bound plan."""
    plan_path = tmp_path / "plan.json"
    content = _plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    runner = _Runner()

    first = apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())
    replay = apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())
    report = cast("dict[str, object]", json.loads(first))

    assert replay == first
    assert len(runner.calls) == 2
    assert runner.calls[0] == (
        str(tmp_path / ".venv/bin/python"),
        "-m",
        "tools.v1_poc_build_images",
        "--tag-suffix",
        "hk-v1-candidate",
    )
    assert runner.calls[1][:4] == (
        str(tmp_path / ".venv/bin/python"),
        "-m",
        "tools.v1_poc_collect_host_facts",
        "--acknowledge-read-only-host-inspection",
    )
    assert report["result"] == "PHASE_COMPLETE_REPLAN_REQUIRED"
    assert report["complete"] is False
    assert report["rollback_complete"] is False
    assert len(cast("list[object]", report["step_receipts"])) == 6
    assert report["recollected_host_facts_fingerprint"] == "sha256:" + "c" * 64
    assert report["recollected_host_facts_path"] == str(
        tmp_path / "var/hk-v1/host/post-image-build.json"
    )
    build_results_path = tmp_path / "var/hk-v1/host/application-build-results.json"
    assert report["application_build_results_path"] == str(build_results_path)
    assert report["application_build_results_fingerprint"] == (
        "sha256:" + sha256(build_results_path.read_bytes()).hexdigest()
    )
    assert report["reboot_performed"] is False


def test_failed_build_executes_only_exact_preservation_readbacks(tmp_path: Path) -> None:
    """A build failure verifies every declared running predecessor and stops."""
    plan_path = tmp_path / "plan.json"
    content = _plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    runner = _Runner(fail_build=True)

    report_bytes = apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())
    report = cast("dict[str, object]", json.loads(report_bytes))

    assert report["result"] == "FAILED_ROLLED_BACK"
    assert report["complete"] is False
    assert len(runner.calls) == 6
    assert all(call[:3] == ("/usr/bin/docker", "container", "inspect") for call in runner.calls[1:])
    assert tuple(call[-1] for call in runner.calls[1:]) == tuple(
        f"asklegal-{service}" for service in reversed(_SERVICES)
    )
    assert report["rollback_complete"] is True


def test_phase_replay_rejects_tampered_retained_build_results(tmp_path: Path) -> None:
    """The next plan cannot consume altered image IDs under a retained seal."""
    plan_path = tmp_path / "plan.json"
    content = _plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    runner = _Runner()
    apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())
    result_path = tmp_path / "var/hk-v1/host/application-build-results.json"
    document = cast("dict[str, object]", json.loads(result_path.read_bytes()))
    images = cast("list[dict[str, object]]", document["images"])
    images[0]["image_id"] = "sha256:" + "f" * 64
    result_path.write_bytes(_canonical(document) + b"\n")

    with pytest.raises(HostApplyError, match="HOST_APPLY_BUILD_READBACK_INVALID"):
        apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())


def test_action_injection_is_rejected_even_when_plan_is_refingerprinted(tmp_path: Path) -> None:
    """No planner field can become a shell, glob, or arbitrary argv fragment."""
    plan_path = tmp_path / "plan.json"
    content = _plan(plan_path)
    document = cast("dict[str, object]", json.loads(content))
    actions = cast("list[str]", document["actions"])
    actions[0] = actions[0].replace("apps/acquisition-worker", "apps/*;id")
    unsigned = dict(document)
    unsigned.pop("fingerprint")
    document["fingerprint"] = _fingerprint(unsigned)
    plan_path.write_bytes(_canonical(document) + b"\n")
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, plan_path.read_bytes(), tmp_path, state_root)
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_ACTION_INVALID"):
        apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())

    assert runner.calls == []
    assert not state_root.exists()


def test_phase_two_rejects_a_refingerprinted_mutable_application_tag(tmp_path: Path) -> None:
    """Neither a fresh plan seal nor authority can turn a mutable tag into an activation input."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    document = cast("dict[str, object]", json.loads(content))
    actions = cast("list[str]", document["actions"])
    actions[5] = actions[5].replace(":hk-v1-candidate", ":v1")
    unsigned = dict(document)
    unsigned.pop("fingerprint")
    document["fingerprint"] = _fingerprint(unsigned)
    plan_path.write_bytes(_canonical(document) + b"\n")
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, plan_path.read_bytes(), tmp_path, state_root)
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_ACTION_INVALID"):
        apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())

    assert runner.calls == []
    assert not state_root.exists()


def test_workspace_source_drift_rejects_authorized_build_before_command(tmp_path: Path) -> None:
    """An authority for older wheel-producing source cannot build changed application code."""
    plan_path = tmp_path / "plan.json"
    content = _plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    source = tmp_path / "apps/control-plane/src/asklegal_control_plane/main.py"
    source.parent.mkdir(parents=True)
    source.write_text("changed after authority\n", encoding="utf-8")
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_BUILD_INPUT_INVALID"):
        apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())

    assert runner.calls == []
    assert not state_root.exists()


def test_cli_requires_explicit_execute_before_reading_or_writing(tmp_path: Path) -> None:
    """Omitting --execute cannot inspect authority or create retained state."""
    state_root = tmp_path / "state"

    assert (
        main(
            [
                "--plan",
                str(tmp_path / "missing-plan.json"),
                "--authority",
                str(tmp_path / "missing-authority.json"),
                "--repository-root",
                str(tmp_path),
                "--state-root",
                str(state_root),
            ]
        )
        == 2
    )
    assert not state_root.exists()


def test_restart_after_build_resumes_at_recollection_without_rebuild(tmp_path: Path) -> None:
    """A crash after the retained build receipts reuses the exact phase lineage."""
    plan_path = tmp_path / "plan.json"
    content = _plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    crashing = _Runner(crash_collect=True)

    with pytest.raises(_SyntheticCrash):
        apply_host_plan(plan_path, authority, tmp_path, state_root, crashing, _Readback())

    resumed = _Runner()
    result = apply_host_plan(plan_path, authority, tmp_path, state_root, resumed, _Readback())
    document = cast("dict[str, object]", json.loads(result))
    assert document["result"] == "PHASE_COMPLETE_REPLAN_REQUIRED"
    assert len(resumed.calls) == 1
    assert resumed.calls[0][2] == "tools.v1_poc_collect_host_facts"


def test_deployment_phase_executes_frozen_actions_and_resumes_after_each_receipt(
    tmp_path: Path,
) -> None:
    """A crash cannot replay already retained host mutations or claim a reboot."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    crashing = _Runner(crash_deploy_call=3)

    with pytest.raises(_SyntheticCrash):
        apply_host_plan(plan_path, authority, tmp_path, state_root, crashing, _Readback())

    resumed = _Runner()
    result = apply_host_plan(plan_path, authority, tmp_path, state_root, resumed, _Readback())
    document = cast("dict[str, object]", json.loads(result))
    assert document["result"] == "COMPLETE"
    assert document["complete"] is True
    assert document["v1_admitted"] is False
    assert document["admission_limitations"] == []
    assert document["reboot_performed"] is False
    assert len(cast("list[object]", document["step_receipts"])) == 13
    assert len(resumed.calls) == 11
    assert all(
        call[0] == "/usr/bin/bash" and call[1].endswith("90-host-apply.sh")
        for call in (*resumed.calls[:-2], resumed.calls[-1])
    )
    assert resumed.calls[-2][2] == "tools.v1_poc_collect_host_facts"
    state_path = next(state_root.glob("hap_*/state.json"))
    assert load_host_apply_state(state_path, plan_path, authority, tmp_path, state_root) == document


def test_not_ready_recovery_is_retained_as_non_admission_limitation(tmp_path: Path) -> None:
    """Prototype bootstrap may run, but state cannot imply V1 recovery admission."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    plan = cast("dict[str, object]", json.loads(content))
    plan["blockers"] = ["HOST_MUTATION_NOT_AUTHORIZED", "RECOVERY_PREFLIGHT_NOT_READY"]
    unsigned = dict(plan)
    unsigned.pop("fingerprint")
    plan["fingerprint"] = _fingerprint(unsigned)
    content = _canonical(plan) + b"\n"
    plan_path.write_bytes(content)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)

    result = apply_host_plan(plan_path, authority, tmp_path, state_root, _Runner(), _Readback())
    document = cast("dict[str, object]", json.loads(result))

    assert document["result"] == "COMPLETE"
    assert document["v1_admitted"] is False
    assert document["admission_limitations"] == ["RECOVERY_PREFLIGHT_NOT_READY"]


def test_deployment_rejects_source_drift_before_state_or_commands(tmp_path: Path) -> None:
    """A phase-two authority cannot activate images built from superseded source."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    changed = tmp_path / "apps/acquisition-worker/src/changed.py"
    changed.parent.mkdir(parents=True)
    changed.write_text("changed = True\n", encoding="utf-8")
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_BUILD_INPUT_INVALID"):
        apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())

    assert runner.calls == []
    assert not state_root.exists()


def test_deployment_rejects_build_result_drift_before_state_or_commands(
    tmp_path: Path,
) -> None:
    """The retained result bytes bound by phase two cannot be replaced after review."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    results = tmp_path / "var/hk-v1/host/application-build-results.json"
    results.write_bytes(results.read_bytes() + b"\n")
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_BUILD_READBACK_INVALID"):
        apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())

    assert runner.calls == []
    assert not state_root.exists()


def test_deployment_rejects_plan_images_not_cross_bound_to_build_rows(tmp_path: Path) -> None:
    """Self-consistent phase-two actions cannot substitute an unbuilt image identity."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    plan = cast("dict[str, object]", json.loads(content))
    actions = cast("list[str]", plan["actions"])
    targets = cast("list[str]", plan["targets"])
    replacement = "sha256:" + "f" * 64
    original = "sha256:" + "1" * 64
    plan["actions"] = [value.replace(original, replacement) for value in actions]
    plan["targets"] = [value.replace(original, replacement) for value in targets]
    unsigned = dict(plan)
    unsigned.pop("fingerprint")
    plan["fingerprint"] = _fingerprint(unsigned)
    content = _canonical(plan) + b"\n"
    plan_path.write_bytes(content)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_BUILD_READBACK_INVALID"):
        apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())

    assert runner.calls == []
    assert not state_root.exists()


def test_deployment_image_readback_mismatch_rolls_back_and_never_reports_complete(
    tmp_path: Path,
) -> None:
    """A running container on any other image ID makes phase two fail closed."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)

    result = apply_host_plan(
        plan_path, authority, tmp_path, state_root, _Runner(), _MismatchedDeploymentReadback()
    )
    document = cast("dict[str, object]", json.loads(result))

    assert document["result"] == "FAILED_ROLLED_BACK"
    assert document["complete"] is False
    assert document["rollback_complete"] is True


def test_complete_terminal_replay_revalidates_current_deployment_semantics(tmp_path: Path) -> None:
    """A retained COMPLETE result cannot outlive current supervision/image readback."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    apply_host_plan(plan_path, authority, tmp_path, state_root, _Runner(), _Readback())
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_DEPLOYMENT_READBACK_INVALID"):
        apply_host_plan(
            plan_path,
            authority,
            tmp_path,
            state_root,
            runner,
            _MismatchedDeploymentReadback(),
        )

    assert runner.calls == []


def test_deployment_rollback_resumes_from_last_retained_exact_action(tmp_path: Path) -> None:
    """A rollback crash resumes remaining predecessor actions and verifies host facts."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    crashing = _Runner(fail_deploy_call=3, crash_deploy_call=6)

    with pytest.raises(_SyntheticCrash):
        apply_host_plan(plan_path, authority, tmp_path, state_root, crashing, _Readback())

    resumed = _Runner()
    result = apply_host_plan(plan_path, authority, tmp_path, state_root, resumed, _Readback())
    document = cast("dict[str, object]", json.loads(result))
    assert document["result"] == "FAILED_ROLLED_BACK"
    assert document["complete"] is False
    assert document["rollback_complete"] is True
    assert len(cast("list[object]", document["step_receipts"])) == 3
    assert len(cast("list[object]", document["rollback_receipts"])) == 10
    assert len(resumed.calls) == 8
    assert resumed.calls[-1][2] == "tools.v1_poc_collect_host_facts"


def test_deployment_wrong_predecessor_readback_never_reports_rollback_complete(
    tmp_path: Path,
) -> None:
    """Successful rollback commands cannot conceal a wrong or missing predecessor image."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)

    result = apply_host_plan(
        plan_path,
        authority,
        tmp_path,
        state_root,
        _Runner(fail_deploy_call=3),
        _MismatchedRollbackReadback(),
    )
    document = cast("dict[str, object]", json.loads(result))

    assert document["result"] == "FAILED_ROLLBACK_UNVERIFIED"
    assert document["rollback_complete"] is False


def test_rolled_back_terminal_replay_revalidates_current_predecessors(tmp_path: Path) -> None:
    """A retained rollback-success result cannot replay after predecessor drift."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    apply_host_plan(
        plan_path,
        authority,
        tmp_path,
        state_root,
        _Runner(fail_deploy_call=3),
        _Readback(),
    )
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_ROLLBACK_READBACK_INVALID"):
        apply_host_plan(
            plan_path,
            authority,
            tmp_path,
            state_root,
            runner,
            _MismatchedRollbackReadback(),
        )

    assert runner.calls == []


def test_canonical_rollback_readback_rejects_wrong_missing_and_unexpected_images(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The canonical readback proves each predecessor image and declared absence."""
    expected = tuple(
        (
            service,
            None if service == "review-api" else "sha256:" + str(index) * 64,
            None if service == "review-api" else "running",
        )
        for index, service in enumerate(_SERVICES, start=1)
    )
    facts: dict[str, object] = {
        "containers": [
            {
                "image_id": image_id,
                "name": f"asklegal-{service}",
                "runtime_state": "running",
            }
            for service, image_id, _runtime_state in expected
            if image_id is not None
        ]
    }

    def load_facts(_path: Path) -> object:
        return object()

    def validate_facts(_facts: object) -> dict[str, object]:
        return facts

    monkeypatch.setattr(host_apply, "load_host_facts_output", load_facts)
    monkeypatch.setattr(host_apply, "validated_complete_host_facts", validate_facts)
    readback = CanonicalHostFactsReadback()

    assert readback.rollback_ready(tmp_path / "facts.json", expected)
    containers = cast("list[dict[str, object]]", facts["containers"])
    containers[0]["image_id"] = "sha256:" + "f" * 64
    assert not readback.rollback_ready(tmp_path / "facts.json", expected)
    containers[0]["image_id"] = expected[0][1]
    containers[0]["runtime_state"] = "exited"
    assert not readback.rollback_ready(tmp_path / "facts.json", expected)
    containers[0]["runtime_state"] = "running"
    containers.pop()
    assert not readback.rollback_ready(tmp_path / "facts.json", expected)
    containers.append(
        {
            "image_id": "sha256:" + "e" * 64,
            "name": "asklegal-review-api",
            "runtime_state": "exited",
        }
    )
    assert not readback.rollback_ready(tmp_path / "facts.json", expected)


def test_canonical_deployment_requires_exact_supervised_runtime_inventory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Detached apps, inactive units, unhealthy rows, and orphan containers fail closed."""
    expected = tuple(
        (service, "sha256:" + str(index) * 64) for index, service in enumerate(_SERVICES, start=1)
    )
    expected_by_container = {f"asklegal-{service}": image_id for service, image_id in expected}
    facts: dict[str, object] = {
        "containers": [
            {
                "health": "NONE",
                "image_id": expected_by_container.get(name, "sha256:" + "a" * 64),
                "name": name,
                "runtime_state": "running",
            }
            for name in host_apply._CONTAINER_NAMES
        ],
        "systemd": {
            "target": {
                "active_state": "active",
                "load_state": "loaded",
                "unit_file_state": "enabled",
                "unit_name": "asklegal.target",
            },
            "service_units": [
                {"active_state": "active", "load_state": "loaded", "unit_name": name}
                for name in host_apply._SYSTEMD_SERVICE_UNITS
            ],
            "timer_units": [
                {"active_state": "active", "load_state": "loaded", "unit_name": name}
                for name in host_apply._SYSTEMD_TIMER_UNITS
            ],
        },
        "applications": [
            {
                "active_state": "active",
                "application_id": application_id,
                "container_name": container_name,
                "health": "NONE",
                "systemd_unit": unit_name,
            }
            for application_id, container_name, unit_name in host_apply._APPLICATIONS
        ],
    }

    def load_facts(_path: Path) -> object:
        return object()

    def validate_facts(_facts: object) -> dict[str, object]:
        return facts

    monkeypatch.setattr(host_apply, "load_host_facts_output", load_facts)
    monkeypatch.setattr(host_apply, "validated_complete_host_facts", validate_facts)
    readback = CanonicalHostFactsReadback()

    assert readback.deployment_ready(tmp_path / "facts.json", expected)
    services = cast(
        "list[dict[str, object]]", cast("dict[str, object]", facts["systemd"])["service_units"]
    )
    services[0]["active_state"] = "inactive"
    assert not readback.deployment_ready(tmp_path / "facts.json", expected)
    services[0]["active_state"] = "active"
    containers = cast("list[dict[str, object]]", facts["containers"])
    containers.append(
        {
            "health": "NONE",
            "image_id": "sha256:" + "f" * 64,
            "name": "acq-batch",
            "runtime_state": "running",
        }
    )
    assert not readback.deployment_ready(tmp_path / "facts.json", expected)


def test_deployment_manifest_requires_exact_root_regular_0400_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Persistent restart input rejects byte drift, weak modes, and symlinks."""
    expected = tuple(
        (service, "sha256:" + str(index) * 64) for index, service in enumerate(_SERVICES, start=1)
    )
    content = b"".join(f"{service} {image_id}\n".encode("ascii") for service, image_id in expected)
    manifest = tmp_path / "deployment-images"
    manifest.write_bytes(content)
    manifest.chmod(0o400)
    monkeypatch.setattr(host_apply, "_DEPLOYMENT_MANIFEST", manifest)
    real_fstat = os.fstat

    def root_owned_fstat(descriptor: int) -> os.stat_result:
        metadata = list(real_fstat(descriptor))
        metadata[4] = 0
        metadata[5] = 0
        return os.stat_result(metadata)

    monkeypatch.setattr(host_apply.os, "fstat", root_owned_fstat)
    readback = CanonicalHostFactsReadback()

    assert readback.deployment_manifest_ready(expected)
    manifest.chmod(0o600)
    assert not readback.deployment_manifest_ready(expected)
    manifest.chmod(0o400)
    manifest.chmod(0o600)
    manifest.write_bytes(content + b"drift\n")
    manifest.chmod(0o400)
    assert not readback.deployment_manifest_ready(expected)
    manifest.unlink()
    target = tmp_path / "target"
    target.write_bytes(content)
    manifest.symlink_to(target)
    assert not readback.deployment_manifest_ready(expected)


def test_deployment_helper_must_exist_before_state_or_commands(tmp_path: Path) -> None:
    """An unavailable repository-owned mutator is a visible pre-effect blocker."""
    plan_path = tmp_path / "deploy-plan.json"
    content = _deployment_plan(plan_path)
    helper = tmp_path / "infrastructure/poc/provisioning/90-host-apply.sh"
    helper.unlink()
    state_root = tmp_path / "state"
    authority = tmp_path / "authority.json"
    _authority(authority, content, tmp_path, state_root)
    runner = _Runner()

    with pytest.raises(HostApplyError, match="HOST_APPLY_HELPER_UNAVAILABLE"):
        apply_host_plan(plan_path, authority, tmp_path, state_root, runner, _Readback())

    assert runner.calls == []
    assert not state_root.exists()


def test_host_helper_snapshots_and_restores_absence_and_target_state() -> None:
    """Rollback covers exact predecessor config, unit, network, image, and target state."""
    helper = (
        Path(__file__).parents[2] / "infrastructure/poc/provisioning/90-host-apply.sh"
    ).read_text(encoding="utf-8")
    assert "printf 'absent\\n' > \"$snapshot_stage/etc-asklegal.state\"" in helper
    assert '"$snapshot_stage/bootstrap-helpers/$helper.state"' in helper
    assert '"$snapshot_stage/management-register-migrations.state"' in helper
    assert "/usr/local/libexec/asklegal-register-migrate" in helper
    assert "/usr/local/libexec/asklegal-vault-bootstrap" in helper
    assert "/usr/local/libexec/asklegal-vault-application-rotation-network" in helper
    assert "/opt/asklegal/management-register/migrations" in helper
    assert "rm -rf -- /etc/asklegal" in helper
    assert "systemctl enable asklegal.target" in helper
    assert "systemctl disable asklegal.target" in helper
    assert "systemctl start asklegal.target" in helper
    assert "systemctl stop asklegal.target || true" in helper
    assert "systemctl restart asklegal.target" in helper
    assert "systemctl is-active --quiet asklegal.target" in helper
    assert "target-active.before" in helper
    assert "RESTORE_NETWORK_SET" in helper
    assert "RESTORE_PREDECESSOR_SERVICE_IMAGE" in helper
    assert 'docker rm -f "asklegal-${service}"' in helper
    assert "I_HAVE_CONSOLE_ACCESS=1" not in helper
    assert 'sync -d "$manifest_stage"' in helper
    assert "sync -d /etc/asklegal/deployment-images" in helper
    assert "sync -f /etc/asklegal" in helper
    assert "systemctl restart asklegal-register-migrate.service" in helper
    assert "systemctl restart asklegal-vault-bootstrap.service" in helper
    rollback = helper.split("*'|RESTORE_HOST_FIREWALL|'*)", maxsplit=1)[1]
    assert "touch /run/asklegal-firewall-confirmed" in rollback
    assert "rm -f /run/asklegal-firewall-confirmed" not in rollback
