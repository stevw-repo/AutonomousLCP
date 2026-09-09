"""Canonical plan-only preflight for Hong Kong V1 host reconciliation.

This module deliberately has no apply mode and no command, Docker, systemd,
credential, SQL, vault, or reboot adapter.  It freezes the exact declared
targets and current blockers from retained host facts so a future live planner
cannot mistake repository intent for mutation authority.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import cast

from tools.hk_v1_rotate_credentials import (
    CredentialRotationPlan,
    credential_rotation_plan_bytes,
)
from tools.hk_v1_vault_application_rotation import (
    VaultApplicationRotationError,
    parse_rotation_plan_bytes,
    parse_succeeded_rotation_report_bytes,
)
from tools.v1_poc_build_images import workspace_source_fingerprint
from tools.v1_poc_collect_host_facts import (
    HKV1HostFacts,
    host_facts_document,
    load_host_facts_output,
)
from tools.v1_poc_host_admission import POLICY_PATH as HOST_POLICY_PATH
from tools.v1_poc_host_admission import check_policy, evaluate_host_facts_envelope
from tools.v1_poc_render_units import RUNTIME_COMMANDS_PATH
from tools.v1_poc_systemd_units import SYSTEMD_POLICY_PATH, check_systemd_input_policy
from tools.v1_poc_topology import TOPOLOGY_PATH, validate_topology

_MAX_DOCUMENT_BYTES = 1_000_000
_INPUT_INVALID = "HOST_RECONCILE_INPUT_INVALID"
_OUTPUT_INVALID = "HOST_RECONCILE_OUTPUT_INVALID"
_TOPOLOGY_INVALID = "HOST_RECONCILE_DESIRED_TOPOLOGY_INVALID"
_AUTHORITY_REQUIRED = (
    "EXACT_FINGERPRINTED_HOST_RECONCILE_PLAN",
    "SEPARATE_POST_APPLY_REBOOT_AUTHORITY",
)
_CREDENTIAL_AUTHORITY = "EXACT_CREDENTIAL_ROTATION_EXECUTION_AUTHORITY"
_RECOVERY_AUTHORITY = "EXACT_LOCAL_RECOVERY_EXECUTION_AUTHORITY"
_RECOVERY_SCHEMA = "asklegal.hk-v1-local-recovery-result/v1"
_IMAGE_INPUTS_PATH = Path("infrastructure/poc/application_image_inputs.json")
_BUILD_RESULTS_SCHEMA = "asklegal.hk-v1-application-build-results/v1"
_BUILD_RESULTS_VERSION = "1.0.0"
_CANDIDATE_TAG_SUFFIX = "hk-v1-candidate"
_APPLICATION_SERVICES = (
    "acquisition-worker",
    "control-plane",
    "legal-processing-worker",
    "promotion-worker",
    "review-api",
)


class HostReconcileMode(StrEnum):
    """The only implemented host-reconcile mode."""

    PLAN = "PLAN"


class HostReconcileBlocker(StrEnum):
    """Closed reasons this repository-only plan cannot become an apply request."""

    ACTIONABLE_HOST_INVENTORY_UNAVAILABLE = "ACTIONABLE_HOST_INVENTORY_UNAVAILABLE"
    APPLICATION_IMAGE_PINS_REQUIRED = "APPLICATION_IMAGE_PINS_REQUIRED"
    CREDENTIAL_ROTATION_ADAPTER_UNAVAILABLE = "CREDENTIAL_ROTATION_ADAPTER_UNAVAILABLE"
    CREDENTIAL_ROTATION_EXECUTION_AUTHORITY_REQUIRED = (
        "CREDENTIAL_ROTATION_EXECUTION_AUTHORITY_REQUIRED"
    )
    CREDENTIAL_ROTATION_PLAN_INVALID = "CREDENTIAL_ROTATION_PLAN_INVALID"
    CREDENTIAL_ROTATION_PLAN_REQUIRED = "CREDENTIAL_ROTATION_PLAN_REQUIRED"
    CREDENTIAL_ROTATION_REPORT_INVALID = "CREDENTIAL_ROTATION_REPORT_INVALID"
    CREDENTIAL_ROTATION_REPORT_REQUIRED = "CREDENTIAL_ROTATION_REPORT_REQUIRED"
    DESIRED_SERVICE_INVENTORY_MISMATCH = "DESIRED_SERVICE_INVENTORY_MISMATCH"
    HOST_FACTS_INCOMPLETE = "HOST_FACTS_INCOMPLETE"
    HOST_FACTS_NONCONFORMING = "HOST_FACTS_NONCONFORMING"
    HOST_MUTATION_NOT_AUTHORIZED = "HOST_MUTATION_NOT_AUTHORIZED"
    RECOVERY_ADAPTER_UNAVAILABLE = "RECOVERY_ADAPTER_UNAVAILABLE"
    RECOVERY_EXECUTION_AUTHORITY_REQUIRED = "RECOVERY_EXECUTION_AUTHORITY_REQUIRED"
    RECOVERY_PREFLIGHT_NOT_READY = "RECOVERY_PREFLIGHT_NOT_READY"
    RECOVERY_PREFLIGHT_REPORT_INVALID = "RECOVERY_PREFLIGHT_REPORT_INVALID"
    RECOVERY_PREFLIGHT_REPORT_REQUIRED = "RECOVERY_PREFLIGHT_REPORT_REQUIRED"


@dataclass(frozen=True, slots=True)
class HostReconcileRollback:
    """Explicit rollback status for a plan that cannot perform mutation."""

    state: str
    actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HostReconcilePlan:
    """Detached canonical host-preflight result."""

    mode: HostReconcileMode
    desired_topology_fingerprint: str
    systemd_inputs_fingerprint: str
    runtime_commands_fingerprint: str
    application_image_inputs_fingerprint: str
    application_build_results_fingerprint: str | None
    host_facts_fingerprint: str
    credential_rotation_plan_fingerprint: str | None
    recovery_preflight_report_fingerprint: str | None
    targets: tuple[str, ...]
    actions: tuple[str, ...]
    blockers: tuple[HostReconcileBlocker, ...]
    rollback: HostReconcileRollback
    mutations_performed: tuple[str, ...]
    mutation_authorized: bool
    authority_required: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _DesiredState:
    topology: dict[str, object]
    systemd: dict[str, object]
    runtime: dict[str, object]
    host_policy: dict[str, object]
    image_inputs: dict[str, object]
    not_rendered: frozenset[str]
    credential_fingerprint: str | None
    credential_terminal: bool
    recovery_fingerprint: str | None
    build_results: dict[str, tuple[str, str, str]] | None


@dataclass(frozen=True, slots=True)
class _ActionInputs:
    facts: HKV1HostFacts
    runtime: dict[str, object]
    image_inputs: dict[str, object]
    image_inputs_fingerprint: str
    credential_fingerprint: str | None
    recovery_fingerprint: str | None
    recovery_ready: bool
    build_results: dict[str, tuple[str, str, str]] | None


def build_application_build_results(
    image_inputs: dict[str, object], rows: tuple[tuple[str, str, str, str], ...], *, root: Path
) -> bytes:
    """Seal exact image IDs and installed-tree digests from one admitted build invocation."""
    expected = {
        _text(item.get("artifact_id")): _text(item.get("application_path"))
        for item in _objects(image_inputs.get("images"))
    }
    normalized = tuple(sorted(rows, key=lambda item: item[0]))
    if tuple(item[0] for item in normalized) != _APPLICATION_SERVICES:
        raise ValueError(_INPUT_INVALID)
    images: list[dict[str, object]] = []
    for service, tag, image_id, tree_sha512 in normalized:
        if (
            service not in expected
            or tag != f"asklegal/{service}:{_CANDIDATE_TAG_SUFFIX}"
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
            or re.fullmatch(r"[0-9a-f]{128}", tree_sha512) is None
        ):
            raise ValueError(_INPUT_INVALID)
        images.append(
            {
                "application_path": expected[service],
                "image_id": image_id,
                "installed_tree_sha512": tree_sha512,
                "service_id": service,
                "tag": tag,
            }
        )
    body: dict[str, object] = {
        "application_image_inputs_fingerprint": _build_inputs_fingerprint(root, image_inputs),
        "images": images,
        "schema_id": _BUILD_RESULTS_SCHEMA,
        "schema_version": _BUILD_RESULTS_VERSION,
    }
    return _canonical({**body, "fingerprint": _fingerprint(body)}) + b"\n"


def _build_results_input(
    path: Path, image_inputs: dict[str, object], root: Path
) -> tuple[str, dict[str, tuple[str, str, str]]]:
    document, raw = _canonical_input(path)
    if set(document) != {
        "application_image_inputs_fingerprint",
        "fingerprint",
        "images",
        "schema_id",
        "schema_version",
    }:
        raise ValueError(_INPUT_INVALID)
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint")
    if (
        document["schema_id"] != _BUILD_RESULTS_SCHEMA
        or document["schema_version"] != _BUILD_RESULTS_VERSION
        or document["application_image_inputs_fingerprint"]
        != _build_inputs_fingerprint(root, image_inputs)
        or supplied != _fingerprint(unsigned)
    ):
        raise ValueError(_INPUT_INVALID)
    expected = {
        _text(item.get("artifact_id")): _text(item.get("application_path"))
        for item in _objects(image_inputs.get("images"))
    }
    results: dict[str, tuple[str, str, str]] = {}
    for item in _objects(document["images"]):
        if set(item) != {
            "application_path",
            "image_id",
            "installed_tree_sha512",
            "service_id",
            "tag",
        }:
            raise ValueError(_INPUT_INVALID)
        service = _text(item["service_id"])
        path_value = _text(item["application_path"])
        tag = _text(item["tag"])
        image_id = _text(item["image_id"])
        tree = _text(item["installed_tree_sha512"])
        if (
            service in results
            or expected.get(service) != path_value
            or tag != f"asklegal/{service}:{_CANDIDATE_TAG_SUFFIX}"
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
            or re.fullmatch(r"[0-9a-f]{128}", tree) is None
        ):
            raise ValueError(_INPUT_INVALID)
        results[service] = (tag, image_id, tree)
    if tuple(sorted(results)) != _APPLICATION_SERVICES:
        raise ValueError(_INPUT_INVALID)
    return _bytes_fingerprint(raw), results


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _fingerprint(value: object) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


def _build_inputs_fingerprint(root: Path, image_inputs: dict[str, object]) -> str:
    return _fingerprint(
        {
            "application_image_inputs": image_inputs,
            "workspace_source_fingerprint": workspace_source_fingerprint(root),
        }
    )


def _bytes_fingerprint(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _derived_opaque(*parts: str) -> str:
    return f"r_{sha256('|'.join(parts).encode('ascii')).hexdigest()[:32]}"


def _load_object(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise ValueError(_INPUT_INVALID)
    value: object = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError(_INPUT_INVALID)
    candidate = cast("dict[object, object]", value)
    if not all(type(key) is str for key in candidate):
        raise ValueError(_INPUT_INVALID)
    return cast("dict[str, object]", candidate)


def _objects(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise TypeError(_INPUT_INVALID)
    result: list[dict[str, object]] = []
    for item in cast("list[object]", value):
        if not isinstance(item, dict):
            raise TypeError(_INPUT_INVALID)
        candidate = cast("dict[object, object]", item)
        if not all(type(key) is str for key in candidate):
            raise ValueError(_INPUT_INVALID)
        result.append(cast("dict[str, object]", candidate))
    return tuple(result)


def _text(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError(_INPUT_INVALID)
    return value


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(_INPUT_INVALID)
    return tuple(_text(item) for item in cast("list[object]", value))


def _canonical_input(path: Path) -> tuple[dict[str, object], bytes]:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError(_INPUT_INVALID)
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES or not raw.endswith(b"\n"):
        raise ValueError(_INPUT_INVALID)
    value: object = json.loads(raw)
    if type(value) is not dict:
        raise ValueError(_INPUT_INVALID)
    candidate = cast("dict[object, object]", value)
    if any(type(key) is not str for key in candidate):
        raise ValueError(_INPUT_INVALID)
    document = cast("dict[str, object]", candidate)
    if _canonical(document) + b"\n" != raw:
        raise ValueError(_INPUT_INVALID)
    return document, raw


def _credential_input(path: Path) -> str:
    document, raw = _canonical_input(path)
    expected = {
        "candidate_binding_ref",
        "credential_name",
        "dependent_units",
        "manifest_fingerprint",
        "plan_fingerprint",
        "predecessor_binding_ref",
        "rotation_id",
        "schema_id",
    }
    if set(document) != expected:
        raise ValueError(_INPUT_INVALID)
    units = document["dependent_units"]
    if type(units) is not list:
        raise ValueError(_INPUT_INVALID)
    raw_units = cast("list[object]", units)
    if any(type(value) is not str for value in raw_units):
        raise ValueError(_INPUT_INVALID)
    plan = CredentialRotationPlan(
        rotation_id=_text(document["rotation_id"]),
        manifest_fingerprint=_text(document["manifest_fingerprint"]),
        credential_name=_text(document["credential_name"]),
        predecessor_binding_ref=_text(document["predecessor_binding_ref"]),
        candidate_binding_ref=_text(document["candidate_binding_ref"]),
        dependent_units=tuple(cast("list[str]", raw_units)),
    )
    if credential_rotation_plan_bytes(plan) + b"\n" != raw:
        raise ValueError(_INPUT_INVALID)
    return _bytes_fingerprint(raw)


def _batch_credential_input(plan_path: Path, report_path: Path) -> str:
    """Bind only an exact succeeded seven-credential report to its canonical plan."""
    plan_raw = plan_path.read_bytes()
    report_raw = report_path.read_bytes()
    plan = parse_rotation_plan_bytes(plan_raw)
    report = parse_succeeded_rotation_report_bytes(report_raw)
    if (
        report.plan_fingerprint != plan.plan_fingerprint
        or report.rotation_id != plan.rotation_id
        or report.candidate_binding_ref != plan.candidate_binding_ref
        or report.staging_receipt_fingerprint != plan.staging_receipt_fingerprint
    ):
        raise ValueError(_INPUT_INVALID)
    return _bytes_fingerprint(report_raw)


def _recovery_input(path: Path) -> tuple[str, bool]:
    document, raw = _canonical_input(path)
    expected = {
        "assessment_fingerprint",
        "blockers",
        "live_recovery_proved",
        "local_contract_proved",
        "mode",
        "operation_id",
        "request_fingerprint",
        "schema",
        "status",
        "targets",
    }
    if set(document) != expected:
        raise ValueError(_INPUT_INVALID)
    blockers = document["blockers"]
    targets = document["targets"]
    if type(blockers) is not list or type(targets) is not dict:
        raise ValueError(_INPUT_INVALID)
    raw_blockers = cast("list[object]", blockers)
    if (
        document["schema"] != _RECOVERY_SCHEMA
        or document["mode"] != "PREFLIGHT"
        or document["assessment_fingerprint"] is not None
        or document["local_contract_proved"] is not False
        or document["live_recovery_proved"] is not False
        or any(type(value) is not str or not value for value in raw_blockers)
        or raw_blockers != sorted(set(cast("list[str]", raw_blockers)))
    ):
        raise ValueError(_INPUT_INVALID)
    target = cast("dict[object, object]", targets)
    if set(target) != {
        "scheduler_directory_name",
        "sql_database_identity",
        "sql_database_name",
        "vault_directory_name",
        "vault_identity",
    } or any(type(key) is not str or type(value) is not str for key, value in target.items()):
        raise ValueError(_INPUT_INVALID)
    operation_id = _text(document["operation_id"])
    request_fingerprint = _text(document["request_fingerprint"])
    token = sha256(f"{operation_id}|{request_fingerprint}".encode("ascii")).hexdigest()[:24]
    if (
        re.fullmatch(r"r_[0-9a-f]{32}", operation_id) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", request_fingerprint) is None
        or re.fullmatch(
            r"asklegal_recovery_sql_[0-9a-f]{24}",
            cast("str", target["sql_database_name"]),
        )
        is None
        or re.fullmatch(
            r"asklegal-recovery-vault-[0-9a-f]{24}",
            cast("str", target["vault_directory_name"]),
        )
        is None
        or re.fullmatch(
            r"asklegal-recovery-scheduler-[0-9a-f]{24}",
            cast("str", target["scheduler_directory_name"]),
        )
        is None
        or re.fullmatch(r"r_[0-9a-f]{32}", cast("str", target["sql_database_identity"])) is None
        or re.fullmatch(r"r_[0-9a-f]{32}", cast("str", target["vault_identity"])) is None
        or target["sql_database_name"] != f"asklegal_recovery_sql_{token}"
        or target["sql_database_identity"] != _derived_opaque(token, "sql-database")
        or target["vault_directory_name"] != f"asklegal-recovery-vault-{token}"
        or target["vault_identity"] != _derived_opaque(token, "vault")
        or target["scheduler_directory_name"] != f"asklegal-recovery-scheduler-{token}"
    ):
        raise ValueError(_INPUT_INVALID)
    status = document["status"]
    ready = status == "PREFLIGHT_READY"
    if status not in {"NOT_READY", "PREFLIGHT_READY"} or ready != (not blockers):
        raise ValueError(_INPUT_INVALID)
    return _bytes_fingerprint(raw), ready


def _operational_contract_inputs(  # noqa: C901, PLR0912
    credential_rotation_plan: Path | None,
    recovery_preflight_report: Path | None,
    vault_application_rotation_plan: Path | None,
    vault_application_rotation_report: Path | None,
) -> tuple[
    set[HostReconcileBlocker],
    str | None,
    str | None,
    tuple[str, ...],
    bool,
]:
    blockers: set[HostReconcileBlocker] = set()
    authority_required: list[str] = list(_AUTHORITY_REQUIRED)
    credential_fingerprint: str | None = None
    recovery_fingerprint: str | None = None
    credential_terminal = False
    batch_supplied = (
        vault_application_rotation_plan is not None or vault_application_rotation_report is not None
    )
    if credential_rotation_plan is not None and batch_supplied:
        blockers.add(HostReconcileBlocker.CREDENTIAL_ROTATION_PLAN_INVALID)
    elif batch_supplied:
        if vault_application_rotation_plan is None:
            blockers.add(HostReconcileBlocker.CREDENTIAL_ROTATION_PLAN_REQUIRED)
        elif vault_application_rotation_report is None:
            blockers.add(HostReconcileBlocker.CREDENTIAL_ROTATION_REPORT_REQUIRED)
        else:
            try:
                credential_fingerprint = _batch_credential_input(
                    vault_application_rotation_plan,
                    vault_application_rotation_report,
                )
                credential_terminal = True
            except OSError, TypeError, ValueError, VaultApplicationRotationError:
                blockers.add(HostReconcileBlocker.CREDENTIAL_ROTATION_REPORT_INVALID)
    elif credential_rotation_plan is None:
        blockers.add(HostReconcileBlocker.CREDENTIAL_ROTATION_PLAN_REQUIRED)
    else:
        try:
            credential_fingerprint = _credential_input(credential_rotation_plan)
        except OSError, TypeError, ValueError:
            blockers.add(HostReconcileBlocker.CREDENTIAL_ROTATION_PLAN_INVALID)
        else:
            blockers.add(HostReconcileBlocker.CREDENTIAL_ROTATION_EXECUTION_AUTHORITY_REQUIRED)
            authority_required.append(_CREDENTIAL_AUTHORITY)
    if recovery_preflight_report is None:
        blockers.add(HostReconcileBlocker.RECOVERY_PREFLIGHT_REPORT_REQUIRED)
    else:
        try:
            recovery_fingerprint, recovery_ready = _recovery_input(recovery_preflight_report)
        except OSError, TypeError, ValueError:
            blockers.add(HostReconcileBlocker.RECOVERY_PREFLIGHT_REPORT_INVALID)
        else:
            if recovery_ready:
                blockers.add(HostReconcileBlocker.RECOVERY_EXECUTION_AUTHORITY_REQUIRED)
                authority_required.append(_RECOVERY_AUTHORITY)
            else:
                blockers.add(HostReconcileBlocker.RECOVERY_PREFLIGHT_NOT_READY)
    return (
        blockers,
        credential_fingerprint,
        recovery_fingerprint,
        tuple(authority_required),
        credential_terminal,
    )


def _topology_targets(desired: _DesiredState) -> set[str]:
    targets: set[str] = set()
    for service in _objects(desired.topology.get("services")):
        service_id = _text(service.get("service_id"))
        if service_id in desired.not_rendered:
            continue
        targets.add(f"desired-service:{service_id}")
        for credential in _texts(service.get("credential_names")):
            targets.add(f"credential:{_text(credential)}")
    for network in _objects(desired.topology.get("networks")):
        targets.add(f"network:{_text(network.get('network_id'))}")
    return targets


def _unit_targets(desired: _DesiredState) -> set[str]:
    targets = {"target:asklegal.target"}
    for service in _objects(desired.systemd.get("service_units")):
        targets.add(f"service:{_text(service.get('unit_name'))}")
    for bootstrap in _objects(desired.systemd.get("bootstrap_units")):
        unit_name = _text(bootstrap.get("unit_name"))
        targets.add(f"service:{unit_name}")
        targets.add(
            f"unit-source:infrastructure/poc/units/{unit_name}->/etc/systemd/system/{unit_name}"
        )
    for timer in _objects(desired.systemd.get("timer_units")):
        targets.add(f"timer:{_text(timer.get('unit_name'))}")
        targets.add(f"timer-service:{_text(timer.get('trigger_unit_name'))}")
    for service in _objects(desired.runtime.get("services")):
        unit_name = _text(service.get("unit_name"))
        targets.add(
            f"unit-source:infrastructure/poc/units/{unit_name}->/etc/systemd/system/{unit_name}"
        )
    for timer in _objects(desired.systemd.get("timer_units")):
        for unit_name in (_text(timer.get("trigger_unit_name")), _text(timer.get("unit_name"))):
            targets.add(
                f"unit-source:infrastructure/poc/units/{unit_name}->/etc/systemd/system/{unit_name}"
            )
    targets.add(
        "unit-source:infrastructure/poc/units/asklegal.target->/etc/systemd/system/asklegal.target"
    )
    targets.update(
        {
            "bootstrap-helper-source:infrastructure/poc/libexec/asklegal-register-migrate->/usr/local/libexec/asklegal-register-migrate",
            "bootstrap-helper-source:infrastructure/poc/libexec/asklegal-vault-bootstrap->/usr/local/libexec/asklegal-vault-bootstrap",
            "bootstrap-helper-source:infrastructure/poc/libexec/asklegal-vault-application-rotation-network->/usr/local/libexec/asklegal-vault-application-rotation-network",
            "migration-source:packages/management-register-adapter/migrations->/opt/asklegal/management-register/migrations",
        }
    )
    return targets


def _path_targets(desired: _DesiredState) -> set[str]:
    targets: set[str] = set()
    storage = desired.host_policy.get("storage")
    if not isinstance(storage, dict):
        raise TypeError(_INPUT_INVALID)
    storage_document = cast("dict[str, object]", storage)
    for path in _texts(storage_document.get("required_paths")):
        targets.add(f"path:{path}")
    for service in _objects(desired.runtime.get("services")):
        for mount in _objects(service.get("mounts")):
            targets.add(f"path:{_text(mount.get('source'))}")
    return targets


def _image_targets(desired: _DesiredState) -> set[str]:
    targets: set[str] = set()
    application_contexts = {
        _text(item.get("artifact_id")): _text(item.get("application_path"))
        for item in _objects(desired.image_inputs.get("images"))
    }
    for service in _objects(desired.runtime.get("services")):
        service_id = _text(service.get("service_id"))
        image = _text(service.get("image"))
        if desired.build_results is not None and service_id in desired.build_results:
            _tag, image_id, _tree = desired.build_results[service_id]
            targets.add(f"image-replacement:{service_id}:{image_id}")
        elif service.get("image_state") == "PINNED_BY_DIGEST":
            targets.add(f"image-replacement:{service_id}:{image}")
        else:
            context = application_contexts.get(service_id)
            if context is None:
                raise ValueError(_INPUT_INVALID)
            candidate_tag = f"asklegal/{service_id}:{_CANDIDATE_TAG_SUFFIX}"
            targets.add(f"image-build:{service_id}:{candidate_tag}:{context}")
    return targets


def _targets(desired: _DesiredState) -> tuple[str, ...]:
    targets = (
        _topology_targets(desired)
        | _unit_targets(desired)
        | _path_targets(desired)
        | _image_targets(desired)
    )
    if desired.credential_fingerprint is not None:
        kind = "report" if desired.credential_terminal else "plan"
        targets.add(f"credential-rotation-{kind}:{desired.credential_fingerprint}")
    if desired.recovery_fingerprint is not None:
        targets.add(f"recovery-preflight-report:{desired.recovery_fingerprint}")
    return tuple(sorted(targets))


def _current_images(facts: HKV1HostFacts) -> dict[str, str]:
    containers = facts.legacy_facts.get("containers")
    if containers is None:
        return {}
    return {_text(item.get("name")): _text(item.get("image_id")) for item in _objects(containers)}


def _current_container_states(facts: HKV1HostFacts) -> dict[str, tuple[str, str]]:
    containers = facts.legacy_facts.get("containers")
    if containers is None:
        return {}
    return {
        _text(item.get("name")): (_text(item.get("image_id")), _text(item.get("runtime_state")))
        for item in _objects(containers)
    }


def _plan_actions(inputs: _ActionInputs) -> tuple[tuple[str, ...], HostReconcileRollback]:
    """Return exact ordered declarations; never invoke any mutation adapter."""
    if not inputs.facts.complete:
        return (), HostReconcileRollback("NOT_READY_INCOMPLETE_HOST_FACTS", ())
    contexts = {
        _text(item.get("artifact_id")): _text(item.get("application_path"))
        for item in _objects(inputs.image_inputs.get("images"))
    }
    unpinned = tuple(
        sorted(
            (
                _text(service.get("service_id")),
                f"asklegal/{_text(service.get('service_id'))}:{_CANDIDATE_TAG_SUFFIX}",
                _text(service.get("unit_name")),
            )
            for service in _objects(inputs.runtime.get("services"))
            if service.get("image_state") != "PINNED_BY_DIGEST"
        )
    )
    current_images = _current_images(inputs.facts)
    if unpinned and inputs.build_results is None:
        action_rows = [
            f"{sequence:03d}|BUILD_APPLICATION_IMAGE|service={service_id}|"
            f"context={contexts[service_id]}|tag={tag}|"
            f"inputs={inputs.image_inputs_fingerprint}"
            for sequence, (service_id, tag, _unit_name) in enumerate(unpinned, start=1)
        ]
        action_rows.append(
            f"{len(unpinned) + 1:03d}|RECOLLECT_HOST_FACTS|"
            "output=var/hk-v1/host/post-image-build.json|"
            "required=immutable-image-digests"
        )
        actions = tuple(action_rows)
        rollback_rows: list[str] = []
        for sequence, (service_id, _tag, _unit_name) in enumerate(reversed(unpinned), start=1):
            container = f"asklegal-{service_id}"
            image_id = current_images.get(container)
            if image_id is None:
                rollback_rows.append(
                    f"{sequence:03d}|PRESERVE_RUNNING_SERVICE|service={service_id}|"
                    "state=ABSENT_IN_RETAINED_INVENTORY"
                )
            else:
                rollback_rows.append(
                    f"{sequence:03d}|PRESERVE_RUNNING_IMAGE|service={service_id}|"
                    f"image_id={image_id}"
                )
        return actions, HostReconcileRollback(
            "CANDIDATE_IMAGES_NOT_ACTIVATED", tuple(rollback_rows)
        )

    if inputs.build_results is None:
        raise ValueError(_INPUT_INVALID)
    action_values: list[str] = [
        "PROVISION_RUNTIME_PATHS|source=infrastructure/poc/provisioning/30-identities.sh",
        (
            "STAGE_RUNTIME_CONFIGURATION|unit_source=infrastructure/poc/units|"
            "config_destination=/etc/asklegal|helper_source=infrastructure/poc/libexec|"
            "helper_destination=/usr/local/libexec|"
            "migration_source=packages/management-register-adapter/migrations|"
            "migration_destination=/opt/asklegal/management-register/migrations"
        ),
        ("INSTALL_SYSTEMD_UNITS|source=infrastructure/poc/units|destination=/etc/systemd/system"),
        (
            "RECONCILE_NETWORKS|unit=asklegal-networks.service|"
            "source=infrastructure/poc/systemd_unit_inputs.json"
        ),
        (
            "APPLY_HOST_FIREWALL|source=infrastructure/poc/provisioning/60-firewall.sh|"
            "deadman_seconds=900"
        ),
    ]
    for service_id in _APPLICATION_SERVICES:
        tag, image_id, _tree = inputs.build_results[service_id]
        unit_name = next(
            _text(item["unit_name"])
            for item in _objects(inputs.runtime["services"])
            if item.get("service_id") == service_id
        )
        action_values.append(
            "VERIFY_DIGEST_PINNED_CANDIDATE|"
            f"service={service_id}|unit={unit_name}|candidate_tag={tag}|image_id={image_id}"
        )
    bindings = ",".join(
        f"{service_id}@{inputs.build_results[service_id][1]}"
        for service_id in _APPLICATION_SERVICES
    )
    action_values.append(
        "ENABLE_START_TARGET_AND_TIMERS|target=asklegal.target|"
        f"source=infrastructure/poc/systemd_unit_inputs.json|bindings={bindings}"
    )
    action_values.append(
        "RECOLLECT_HOST_FACTS|output=var/hk-v1/host/post-reconcile.json|"
        "required=all-11-fact-classes"
    )
    action_values.append(
        "CONFIRM_HOST_FIREWALL|source=post-reconcile-host-facts|"
        "marker=/run/asklegal-firewall-confirmed"
    )
    actions = tuple(
        f"{sequence:03d}|{value}" for sequence, value in enumerate(action_values, start=1)
    )
    current_states = _current_container_states(inputs.facts)
    rollback_values: list[str] = []
    for service_id in reversed(_APPLICATION_SERVICES):
        prior = current_states.get(f"asklegal-{service_id}")
        if prior is None:
            rollback_values.append(f"RESTORE_PREDECESSOR_SERVICE_ABSENCE|service={service_id}")
        else:
            image_id, runtime_state = prior
            rollback_values.append(
                f"RESTORE_PREDECESSOR_SERVICE_IMAGE|service={service_id}|"
                f"runtime_state={runtime_state}|image_id={image_id}"
            )
    rollback_values.extend(
        (
            "RESTORE_RUNTIME_CONFIGURATION|source=state-owned-predecessor-snapshot",
            "RESTORE_NETWORK_SET|source=retained-host-facts",
            "RESTORE_HOST_FIREWALL|source=state-owned-predecessor-snapshot",
            "RESTORE_SYSTEMD_UNIT_BYTES|source=state-owned-predecessor-snapshot",
        )
    )
    rollback_values.append(
        "RECOLLECT_HOST_FACTS|output=var/hk-v1/host/post-rollback.json|required=all-11-fact-classes"
    )
    rollback = HostReconcileRollback(
        "ORDERED_REVERSIBLE_PLAN",
        tuple(f"{sequence:03d}|{value}" for sequence, value in enumerate(rollback_values, start=1)),
    )
    return actions, rollback


def _projection_without_fingerprint(  # noqa: PLR0913 - exact plan input bindings.
    *,
    desired_topology_fingerprint: str,
    systemd_inputs_fingerprint: str,
    runtime_commands_fingerprint: str,
    application_image_inputs_fingerprint: str,
    application_build_results_fingerprint: str | None,
    host_facts_fingerprint: str,
    credential_rotation_plan_fingerprint: str | None,
    recovery_preflight_report_fingerprint: str | None,
    targets: tuple[str, ...],
    actions: tuple[str, ...],
    blockers: tuple[HostReconcileBlocker, ...],
    rollback: HostReconcileRollback,
    authority_required: tuple[str, ...],
) -> dict[str, object]:
    return {
        "actions": list(actions),
        "authority_required": list(authority_required),
        "blockers": [item.value for item in blockers],
        "desired_topology_fingerprint": desired_topology_fingerprint,
        "application_image_inputs_fingerprint": application_image_inputs_fingerprint,
        "application_build_results_fingerprint": application_build_results_fingerprint,
        "credential_rotation_plan_fingerprint": credential_rotation_plan_fingerprint,
        "host_facts_fingerprint": host_facts_fingerprint,
        "mode": HostReconcileMode.PLAN.value,
        "mutation_authorized": False,
        "mutations_performed": [],
        "rollback": {"actions": list(rollback.actions), "state": rollback.state},
        "runtime_commands_fingerprint": runtime_commands_fingerprint,
        "recovery_preflight_report_fingerprint": recovery_preflight_report_fingerprint,
        "schema_version": 1,
        "systemd_inputs_fingerprint": systemd_inputs_fingerprint,
        "targets": list(targets),
    }


def build_host_reconcile_plan(  # noqa: PLR0913
    root: Path,
    facts: HKV1HostFacts,
    *,
    credential_rotation_plan: Path | None = None,
    vault_application_rotation_plan: Path | None = None,
    vault_application_rotation_report: Path | None = None,
    recovery_preflight_report: Path | None = None,
    application_build_results: Path | None = None,
) -> HostReconcilePlan:
    """Freeze one exact no-effect plan from checked-in desired state and retained facts."""
    check_policy(root)
    check_systemd_input_policy(root)
    topology = _load_object(root / TOPOLOGY_PATH)
    topology_findings = validate_topology(topology)
    if topology_findings:
        raise ValueError(_TOPOLOGY_INVALID)
    systemd = _load_object(root / SYSTEMD_POLICY_PATH)
    runtime = _load_object(root / RUNTIME_COMMANDS_PATH)
    host_policy = _load_object(root / HOST_POLICY_PATH)
    image_inputs = _load_object(root / _IMAGE_INPUTS_PATH)
    build_results_fingerprint: str | None = None
    build_results: dict[str, tuple[str, str, str]] | None = None
    if application_build_results is not None:
        build_results_fingerprint, build_results = _build_results_input(
            application_build_results, image_inputs, root
        )
    evaluation = evaluate_host_facts_envelope(host_policy, facts)
    not_rendered = frozenset(
        _text(item.get("service_id")) for item in _objects(runtime.get("not_rendered"))
    )
    topology_services = {
        _text(item.get("service_id"))
        for item in _objects(topology.get("services"))
        if _text(item.get("service_id")) not in not_rendered
    }
    unit_services = {
        _text(item.get("service_id")) for item in _objects(systemd.get("service_units"))
    }
    (
        input_blockers,
        credential_fingerprint,
        recovery_fingerprint,
        authority_required,
        credential_terminal,
    ) = _operational_contract_inputs(
        credential_rotation_plan,
        recovery_preflight_report,
        vault_application_rotation_plan,
        vault_application_rotation_report,
    )
    blockers: set[HostReconcileBlocker] = {
        HostReconcileBlocker.HOST_MUTATION_NOT_AUTHORIZED,
        *input_blockers,
    }
    if not facts.complete:
        blockers.add(HostReconcileBlocker.HOST_FACTS_INCOMPLETE)
    if evaluation.findings:
        blockers.add(HostReconcileBlocker.HOST_FACTS_NONCONFORMING)
    if build_results is None and any(
        item.get("artifact_state") == "PIN_REQUIRED" for item in _objects(topology["services"])
    ):
        blockers.add(HostReconcileBlocker.APPLICATION_IMAGE_PINS_REQUIRED)
    if topology_services != unit_services:
        blockers.add(HostReconcileBlocker.DESIRED_SERVICE_INVENTORY_MISMATCH)
    ordered_blockers = tuple(sorted(blockers, key=lambda item: item.value))
    desired_fingerprint = _fingerprint(topology)
    systemd_fingerprint = _fingerprint(systemd)
    runtime_fingerprint = _fingerprint(runtime)
    image_inputs_fingerprint = _build_inputs_fingerprint(root, image_inputs)
    facts_fingerprint = _fingerprint(host_facts_document(facts))
    targets = _targets(
        _DesiredState(
            topology=topology,
            systemd=systemd,
            runtime=runtime,
            host_policy=host_policy,
            image_inputs=image_inputs,
            not_rendered=not_rendered,
            credential_fingerprint=credential_fingerprint,
            credential_terminal=credential_terminal,
            recovery_fingerprint=recovery_fingerprint,
            build_results=build_results,
        )
    )
    actions, rollback = _plan_actions(
        _ActionInputs(
            facts=facts,
            runtime=runtime,
            image_inputs=image_inputs,
            image_inputs_fingerprint=image_inputs_fingerprint,
            credential_fingerprint=credential_fingerprint,
            recovery_fingerprint=recovery_fingerprint,
            recovery_ready=(
                HostReconcileBlocker.RECOVERY_EXECUTION_AUTHORITY_REQUIRED in ordered_blockers
            ),
            build_results=build_results,
        )
    )
    unsigned = _projection_without_fingerprint(
        desired_topology_fingerprint=desired_fingerprint,
        systemd_inputs_fingerprint=systemd_fingerprint,
        runtime_commands_fingerprint=runtime_fingerprint,
        application_image_inputs_fingerprint=image_inputs_fingerprint,
        application_build_results_fingerprint=build_results_fingerprint,
        host_facts_fingerprint=facts_fingerprint,
        credential_rotation_plan_fingerprint=credential_fingerprint,
        recovery_preflight_report_fingerprint=recovery_fingerprint,
        targets=targets,
        actions=actions,
        blockers=ordered_blockers,
        rollback=rollback,
        authority_required=authority_required,
    )
    return HostReconcilePlan(
        mode=HostReconcileMode.PLAN,
        desired_topology_fingerprint=desired_fingerprint,
        systemd_inputs_fingerprint=systemd_fingerprint,
        runtime_commands_fingerprint=runtime_fingerprint,
        application_image_inputs_fingerprint=image_inputs_fingerprint,
        application_build_results_fingerprint=build_results_fingerprint,
        host_facts_fingerprint=facts_fingerprint,
        credential_rotation_plan_fingerprint=credential_fingerprint,
        recovery_preflight_report_fingerprint=recovery_fingerprint,
        targets=targets,
        actions=actions,
        blockers=ordered_blockers,
        rollback=rollback,
        mutations_performed=(),
        mutation_authorized=False,
        authority_required=authority_required,
        fingerprint=_fingerprint(unsigned),
    )


def host_reconcile_plan_document(plan: HostReconcilePlan) -> dict[str, object]:
    """Project one canonical plan without permitting caller-selected fields."""
    document = _projection_without_fingerprint(
        desired_topology_fingerprint=plan.desired_topology_fingerprint,
        systemd_inputs_fingerprint=plan.systemd_inputs_fingerprint,
        runtime_commands_fingerprint=plan.runtime_commands_fingerprint,
        application_image_inputs_fingerprint=plan.application_image_inputs_fingerprint,
        application_build_results_fingerprint=plan.application_build_results_fingerprint,
        host_facts_fingerprint=plan.host_facts_fingerprint,
        credential_rotation_plan_fingerprint=plan.credential_rotation_plan_fingerprint,
        recovery_preflight_report_fingerprint=plan.recovery_preflight_report_fingerprint,
        targets=plan.targets,
        actions=plan.actions,
        blockers=plan.blockers,
        rollback=plan.rollback,
        authority_required=plan.authority_required,
    )
    document["fingerprint"] = plan.fingerprint
    return document


def _write_plan(path: Path, plan: HostReconcilePlan) -> None:
    if not path.is_absolute() or not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError(_OUTPUT_INVALID)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ValueError(_OUTPUT_INVALID)
    raw = _canonical(host_reconcile_plan_document(plan)) + b"\n"
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan",), default="plan")
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--credential-rotation-plan", type=Path)
    parser.add_argument("--vault-application-rotation-plan", type=Path)
    parser.add_argument("--vault-application-rotation-report", type=Path)
    parser.add_argument("--recovery-preflight-report", type=Path)
    parser.add_argument("--application-build-results", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write a deterministic plan-only report; apply is intentionally absent."""
    arguments = _parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    plan = build_host_reconcile_plan(
        root,
        load_host_facts_output(arguments.facts),
        credential_rotation_plan=arguments.credential_rotation_plan,
        vault_application_rotation_plan=arguments.vault_application_rotation_plan,
        vault_application_rotation_report=arguments.vault_application_rotation_report,
        recovery_preflight_report=arguments.recovery_preflight_report,
        application_build_results=arguments.application_build_results,
    )
    _write_plan(arguments.output, plan)
    print(  # noqa: T201
        f"PASS HOST_RECONCILE_PLAN_ONLY {plan.fingerprint} blockers={len(plan.blockers)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
