"""Authority-gated executor for one exact canonical HK V1 host reconcile plan."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Never, Protocol, cast

from asklegal_application_runtime import exclusive_local_state_lock

from tools.hk_v1_host_reconcile import build_application_build_results
from tools.v1_poc_build_images import workspace_source_fingerprint
from tools.v1_poc_collect_host_facts import (
    host_facts_document,
    load_host_facts_output,
    validated_complete_host_facts,
)

_AUTHORITY_SCHEMA = "asklegal.hk-v1-host-apply-authority/v1"
_STATE_SCHEMA = "asklegal.hk-v1-host-apply-state/v1"
_VERSION = "1.0.0"
_MAX_BYTES = 5_000_000
_FP = re.compile(r"^sha256:[0-9a-f]{64}$")
_AUTHORITY_ID = re.compile(r"^auth_[0-9a-f]{48}$")
_SAFE_FIELD = re.compile(r"^[a-z0-9][a-z0-9._/:-]*$")
_SERVICES = (
    "acquisition-worker",
    "control-plane",
    "legal-processing-worker",
    "promotion-worker",
    "review-api",
)
_IMAGE_ACTION_COUNT = len(_SERVICES)
_PHASE_ACTION_COUNT = _IMAGE_ACTION_COUNT + 1
_DEPLOYMENT_ACTION_COUNT = 13
_DEPLOYMENT_ROLLBACK_COUNT = 10
_BUILD_OUTPUT_FIELDS = 4
_CANDIDATE_TAG_SUFFIX = "hk-v1-candidate"
_DEPLOYMENT_MANIFEST = Path("/etc/asklegal/deployment-images")
_DEPLOYMENT_MANIFEST_MODE = 0o400
_BOOTSTRAP_RECEIPT_MODE = 0o600
_VAULT_RETENTION_DAYS = 2555
_REGISTER_RECEIPT = Path("/var/lib/asklegal/control/register-migration-readback.json")
_VAULT_RECEIPT = Path("/var/lib/asklegal/control/vault-bootstrap-readback.json")
_SYSTEMD_SERVICE_UNITS = (
    "asklegal-acquisition-worker.service",
    "asklegal-control-plane.service",
    "asklegal-dts-general.service",
    "asklegal-dts-promotion.service",
    "asklegal-egress-model.service",
    "asklegal-egress-promotion.service",
    "asklegal-egress-source.service",
    "asklegal-legal-processing-worker.service",
    "asklegal-networks.service",
    "asklegal-otel-collector.service",
    "asklegal-promotion-worker.service",
    "asklegal-register-migrate.service",
    "asklegal-review-api.service",
    "asklegal-sql-server.service",
    "asklegal-vault-bootstrap.service",
    "asklegal-vault-primary.service",
    "asklegal-vault-recovery.service",
)
_SYSTEMD_TIMER_UNITS = (
    "asklegal-audit-archive.timer",
    "asklegal-full-reconciliation.timer",
    "asklegal-ordinary-observation.timer",
    "asklegal-recovery-verification.timer",
    "asklegal-telemetry-retention.timer",
)
_APPLICATIONS = (
    ("ACQUISITION_WORKER", "asklegal-acquisition-worker", "asklegal-acquisition-worker.service"),
    ("CONTROL_PLANE", "asklegal-control-plane", "asklegal-control-plane.service"),
    (
        "LEGAL_PROCESSING_WORKER",
        "asklegal-legal-processing-worker",
        "asklegal-legal-processing-worker.service",
    ),
    ("PROMOTION_WORKER", "asklegal-promotion-worker", "asklegal-promotion-worker.service"),
    ("REVIEW_API", "asklegal-review-api", "asklegal-review-api.service"),
)
_CONTAINER_NAMES = tuple(
    sorted(
        {
            "asklegal-acquisition-worker",
            "asklegal-control-plane",
            "asklegal-dts-general",
            "asklegal-dts-promotion",
            "asklegal-egress-model",
            "asklegal-egress-promotion",
            "asklegal-egress-source",
            "asklegal-legal-processing-worker",
            "asklegal-otel-collector",
            "asklegal-promotion-worker",
            "asklegal-review-api",
            "asklegal-sql-server",
            "asklegal-vault-primary",
            "asklegal-vault-recovery",
        }
    )
)
_INCOMPLETE_BLOCKERS = {
    "ACTIONABLE_HOST_INVENTORY_UNAVAILABLE",
    "HOST_FACTS_INCOMPLETE",
    "RECOVERY_PREFLIGHT_REPORT_INVALID",
    "RECOVERY_PREFLIGHT_REPORT_REQUIRED",
}
_DEPLOYMENT_CREDENTIAL_BLOCKERS = {
    "CREDENTIAL_ROTATION_EXECUTION_AUTHORITY_REQUIRED",
    "CREDENTIAL_ROTATION_PLAN_INVALID",
    "CREDENTIAL_ROTATION_PLAN_REQUIRED",
    "CREDENTIAL_ROTATION_REPORT_INVALID",
    "CREDENTIAL_ROTATION_REPORT_REQUIRED",
}


class HostApplyError(ValueError):
    """One exact safe host-plan, authority, action, execution, or replay failure."""


@dataclass(frozen=True, slots=True)
class HostApplyCommandResult:
    """Secret-free process result consumed at the command boundary."""

    returncode: int
    stdout: str
    stderr: str


class HostApplyRunner(Protocol):
    """Closed argv-only host command boundary."""

    def run(self, argv: tuple[str, ...], *, cwd: Path) -> HostApplyCommandResult:
        """Execute an already validated argv without a shell."""
        ...


class HostFactsReadback(Protocol):
    """Owning canonical host-facts readback boundary."""

    def fingerprint(self, path: Path) -> str:
        """Parse the collected envelope and return its semantic fingerprint."""
        ...

    def firewall_ready(self, path: Path) -> bool:
        """Reparse and require the exact input/forward/direct-egress policies."""
        ...

    def deployment_ready(self, path: Path, expected_images: tuple[tuple[str, str], ...]) -> bool:
        """Require every application container running the authority-bound image ID."""
        ...

    def deployment_manifest_ready(self, expected_images: tuple[tuple[str, str], ...]) -> bool:
        """Require the persistent root-owned launch manifest to match the authority."""
        ...

    def bootstrap_ready(self) -> bool:
        """Require current exact SQL/vault bootstrap readback receipt bytes."""
        ...

    def rollback_ready(
        self,
        path: Path,
        expected_images: tuple[tuple[str, str | None, str | None], ...],
    ) -> bool:
        """Require every declared predecessor image or predecessor absence."""
        ...


@dataclass(frozen=True, slots=True)
class _ImageAction:
    sequence: int
    service: str
    context: str
    tag: str
    inputs_fingerprint: str
    raw: str


@dataclass(frozen=True, slots=True)
class _RollbackAction:
    sequence: int
    service: str
    image_id: str | None
    raw: str


@dataclass(frozen=True, slots=True)
class _Plan:
    fingerprint: str
    actions: tuple[str, ...]
    targets: tuple[str, ...]
    image_actions: tuple[_ImageAction, ...]
    recollect_action: str
    recollect_output: str
    rollback_actions: tuple[_RollbackAction, ...]
    image_inputs_fingerprint: str


@dataclass(frozen=True, slots=True)
class _DeploymentPlan:
    fingerprint: str
    actions: tuple[str, ...]
    targets: tuple[str, ...]
    recollect_action: str
    recollect_output: str
    rollback_actions: tuple[str, ...]
    build_results_fingerprint: str
    image_inputs_fingerprint: str
    expected_images: tuple[tuple[str, str], ...]
    predecessor_images: tuple[tuple[str, str | None, str | None], ...]
    admission_limitations: tuple[str, ...]


_HostPlan = _Plan | _DeploymentPlan


@dataclass(frozen=True, slots=True)
class _Authority:
    authority_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _Execution:
    plan: _HostPlan
    authority: _Authority
    repository_root: Path
    state_path: Path
    runner: HostApplyRunner
    readback: HostFactsReadback


def _fail(code: str) -> Never:
    raise HostApplyError(code)


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


def _bytes_fingerprint(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _fingerprint_text(value: object, code: str) -> str:
    fingerprint = str(value)
    if _FP.fullmatch(fingerprint) is None:
        _fail(code)
    return fingerprint


def _safe_path(path: Path, code: str, *, file: bool = False) -> Path:
    if not path.is_absolute() or path == Path(path.anchor) or path != path.resolve(strict=False):
        _fail(code)
    current = path
    while current != Path(current.anchor):
        if current.is_symlink():
            _fail(code)
        current = current.parent
    if file and not path.is_file():
        _fail(code)
    return path


def _object(value: object, code: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(code)
    candidate = cast("dict[object, object]", value)
    if any(type(key) is not str for key in candidate):
        _fail(code)
    return cast("dict[str, object]", candidate)


def _strings(value: object, code: str) -> tuple[str, ...]:
    if type(value) is not list:
        _fail(code)
    items = cast("list[object]", value)
    if any(type(item) is not str or not item for item in items):
        _fail(code)
    return tuple(cast("list[str]", items))


def _read_document(
    path: Path, code: str, *, trailing_newline: bool
) -> tuple[bytes, dict[str, object]]:
    _safe_path(path, code, file=True)
    try:
        content = path.read_bytes()
        if len(content) > _MAX_BYTES:
            _fail(code)
        raw = content[:-1] if trailing_newline and content.endswith(b"\n") else content
        if trailing_newline and raw == content:
            _fail(code)
        document = _object(json.loads(raw), code)
    except HostApplyError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise HostApplyError(code) from error
    if _canonical(document) != raw:
        _fail(code)
    return content, document


def _parse_image_action(value: str, expected_sequence: int) -> _ImageAction:
    match = re.fullmatch(
        r"([0-9]{3})\|BUILD_APPLICATION_IMAGE\|service=([^|]+)\|"
        r"context=([^|]+)\|tag=([^|]+)\|inputs=(sha256:[0-9a-f]{64})",
        value,
    )
    if match is None:
        _fail("HOST_APPLY_ACTION_INVALID")
    sequence = int(match.group(1))
    service, context, tag, inputs = match.group(2, 3, 4, 5)
    if (
        sequence != expected_sequence
        or service != _SERVICES[expected_sequence - 1]
        or context != f"apps/{service}"
        or tag != f"asklegal/{service}:{_CANDIDATE_TAG_SUFFIX}"
        or any(_SAFE_FIELD.fullmatch(item) is None for item in (service, context, tag))
    ):
        _fail("HOST_APPLY_ACTION_INVALID")
    return _ImageAction(sequence, service, context, tag, inputs, value)


def _parse_rollback_action(value: str, expected_sequence: int) -> _RollbackAction:
    image = re.fullmatch(
        r"([0-9]{3})\|PRESERVE_RUNNING_IMAGE\|service=([^|]+)\|"
        r"image_id=(sha256:[0-9a-f]{64})",
        value,
    )
    absent = re.fullmatch(
        r"([0-9]{3})\|PRESERVE_RUNNING_SERVICE\|service=([^|]+)\|"
        r"state=ABSENT_IN_RETAINED_INVENTORY",
        value,
    )
    match = image or absent
    if match is None:
        _fail("HOST_APPLY_ROLLBACK_INVALID")
    sequence = int(match.group(1))
    service = match.group(2)
    if (
        sequence != expected_sequence
        or service != tuple(reversed(_SERVICES))[expected_sequence - 1]
    ):
        _fail("HOST_APPLY_ROLLBACK_INVALID")
    return _RollbackAction(sequence, service, image.group(3) if image else None, value)


def _parse_plan(path: Path) -> _HostPlan:
    _content, document = _read_document(path, "HOST_APPLY_PLAN_INVALID", trailing_newline=True)
    required = {
        "actions",
        "application_build_results_fingerprint",
        "application_image_inputs_fingerprint",
        "authority_required",
        "blockers",
        "credential_rotation_plan_fingerprint",
        "desired_topology_fingerprint",
        "fingerprint",
        "host_facts_fingerprint",
        "mode",
        "mutation_authorized",
        "mutations_performed",
        "recovery_preflight_report_fingerprint",
        "rollback",
        "runtime_commands_fingerprint",
        "schema_version",
        "systemd_inputs_fingerprint",
        "targets",
    }
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    actions = _strings(document.get("actions"), "HOST_APPLY_PLAN_INVALID")
    blockers = _strings(document.get("blockers"), "HOST_APPLY_PLAN_INVALID")
    targets = _strings(document.get("targets"), "HOST_APPLY_PLAN_INVALID")
    if (
        set(document) != required
        or document.get("mode") != "PLAN"
        or document.get("schema_version") != 1
        or document.get("mutation_authorized") is not False
        or document.get("mutations_performed") != []
        or _FP.fullmatch(str(supplied)) is None
        or supplied != _fingerprint(unsigned)
        or targets != tuple(sorted(set(targets)))
    ):
        _fail("HOST_APPLY_PLAN_INVALID")
    if not actions or _INCOMPLETE_BLOCKERS.intersection(blockers):
        _fail("HOST_APPLY_PLAN_NOT_ACTIONABLE")
    build_results_fingerprint = document.get("application_build_results_fingerprint")
    if build_results_fingerprint is not None:
        if _FP.fullmatch(str(build_results_fingerprint)) is None:
            _fail("HOST_APPLY_PLAN_INVALID")
        return _parse_deployment_plan(document, str(supplied), actions, targets, blockers)
    if len(actions) != _PHASE_ACTION_COUNT:
        _fail("HOST_APPLY_ACTION_SET_UNSUPPORTED")
    image_actions = tuple(
        _parse_image_action(value, sequence) for sequence, value in enumerate(actions[:5], start=1)
    )
    image_inputs = str(document.get("application_image_inputs_fingerprint"))
    if _FP.fullmatch(image_inputs) is None or any(
        action.inputs_fingerprint != image_inputs for action in image_actions
    ):
        _fail("HOST_APPLY_ACTION_INVALID")
    recollect = actions[-1]
    match = re.fullmatch(
        r"006\|RECOLLECT_HOST_FACTS\|output="
        r"(var/hk-v1/host/post-image-build\.json)\|required=immutable-image-digests",
        recollect,
    )
    if match is None:
        _fail("HOST_APPLY_ACTION_INVALID")
    rollback = _object(document.get("rollback"), "HOST_APPLY_ROLLBACK_INVALID")
    rollback_values = _strings(rollback.get("actions"), "HOST_APPLY_ROLLBACK_INVALID")
    if (
        rollback.get("state") != "CANDIDATE_IMAGES_NOT_ACTIVATED"
        or len(rollback_values) != _IMAGE_ACTION_COUNT
    ):
        _fail("HOST_APPLY_ROLLBACK_INVALID")
    rollback_actions = tuple(
        _parse_rollback_action(value, sequence)
        for sequence, value in enumerate(rollback_values, start=1)
    )
    return _Plan(
        cast("str", supplied),
        actions,
        targets,
        image_actions,
        recollect,
        match.group(1),
        rollback_actions,
        image_inputs,
    )


def _parse_deployment_plan(  # noqa: C901 - validates one closed ordered transaction.
    document: dict[str, object],
    fingerprint: str,
    actions: tuple[str, ...],
    targets: tuple[str, ...],
    blockers: tuple[str, ...],
) -> _DeploymentPlan:
    credential_fingerprint = document.get("credential_rotation_plan_fingerprint")
    if (
        _FP.fullmatch(str(credential_fingerprint)) is None
        or f"credential-rotation-report:{credential_fingerprint}" not in targets
        or _DEPLOYMENT_CREDENTIAL_BLOCKERS.intersection(blockers)
    ):
        _fail("HOST_APPLY_PLAN_NOT_ACTIONABLE")
    if len(actions) != _DEPLOYMENT_ACTION_COUNT:
        _fail("HOST_APPLY_ACTION_SET_UNSUPPORTED")
    exact_prefixes = (
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
        (
            "005|APPLY_HOST_FIREWALL|source=infrastructure/poc/provisioning/60-firewall.sh|"
            "deadman_seconds=900"
        ),
    )
    if actions[:5] != exact_prefixes:
        _fail("HOST_APPLY_ACTION_INVALID")
    expected_images: list[tuple[str, str]] = []
    for index, service in enumerate(_SERVICES, start=6):
        match = re.fullmatch(
            rf"{index:03d}\|VERIFY_DIGEST_PINNED_CANDIDATE\|service={re.escape(service)}\|"
            rf"unit=asklegal-{re.escape(service)}\.service\|candidate_tag="
            rf"asklegal/{re.escape(service)}:{_CANDIDATE_TAG_SUFFIX}\|"
            r"image_id=(sha256:[0-9a-f]{64})",
            actions[index - 1],
        )
        if match is None or f"image-replacement:{service}:{match.group(1)}" not in targets:
            _fail("HOST_APPLY_ACTION_INVALID")
        expected_images.append((service, match.group(1)))
    bindings = ",".join(f"{service}@{image_id}" for service, image_id in expected_images)
    if (
        actions[10]
        != (
            "011|ENABLE_START_TARGET_AND_TIMERS|target=asklegal.target|"
            f"source=infrastructure/poc/systemd_unit_inputs.json|bindings={bindings}"
        )
        or actions[11]
        != (
            "012|RECOLLECT_HOST_FACTS|output=var/hk-v1/host/post-reconcile.json|"
            "required=all-11-fact-classes"
        )
        or actions[12]
        != (
            "013|CONFIRM_HOST_FIREWALL|source=post-reconcile-host-facts|"
            "marker=/run/asklegal-firewall-confirmed"
        )
    ):
        _fail("HOST_APPLY_ACTION_INVALID")
    rollback = _object(document.get("rollback"), "HOST_APPLY_ROLLBACK_INVALID")
    rollback_actions = _strings(rollback.get("actions"), "HOST_APPLY_ROLLBACK_INVALID")
    if (
        rollback.get("state") != "ORDERED_REVERSIBLE_PLAN"
        or len(rollback_actions) != _DEPLOYMENT_ROLLBACK_COUNT
    ):
        _fail("HOST_APPLY_ROLLBACK_INVALID")
    if rollback_actions[5:9] != (
        "006|RESTORE_RUNTIME_CONFIGURATION|source=state-owned-predecessor-snapshot",
        "007|RESTORE_NETWORK_SET|source=retained-host-facts",
        "008|RESTORE_HOST_FIREWALL|source=state-owned-predecessor-snapshot",
        "009|RESTORE_SYSTEMD_UNIT_BYTES|source=state-owned-predecessor-snapshot",
    ) or rollback_actions[-1] != (
        "010|RECOLLECT_HOST_FACTS|output=var/hk-v1/host/post-rollback.json|"
        "required=all-11-fact-classes"
    ):
        _fail("HOST_APPLY_ROLLBACK_INVALID")
    predecessor_images: dict[str, tuple[str | None, str | None]] = {}
    for index, (service, raw) in enumerate(
        zip(reversed(_SERVICES), rollback_actions[:5], strict=True), start=1
    ):
        image = re.fullmatch(
            rf"{index:03d}\|RESTORE_PREDECESSOR_SERVICE_IMAGE\|service={re.escape(service)}\|"
            r"runtime_state=([a-z]+)\|image_id=(sha256:[0-9a-f]{64})",
            raw,
        )
        absent = re.fullmatch(
            rf"{index:03d}\|RESTORE_PREDECESSOR_SERVICE_ABSENCE\|service={re.escape(service)}",
            raw,
        )
        if image is None and absent is None:
            _fail("HOST_APPLY_ROLLBACK_INVALID")
        predecessor_images[service] = (
            (None, None) if image is None else (image.group(2), image.group(1))
        )
    image_inputs_fingerprint = _fingerprint_text(
        document.get("application_image_inputs_fingerprint"), "HOST_APPLY_PLAN_INVALID"
    )
    _fingerprint_text(
        document.get("recovery_preflight_report_fingerprint"), "HOST_APPLY_PLAN_INVALID"
    )
    recovery_limitations = tuple(value for value in blockers if value.startswith("RECOVERY_"))
    if any(value != "RECOVERY_PREFLIGHT_NOT_READY" for value in recovery_limitations):
        _fail("HOST_APPLY_PLAN_NOT_ACTIONABLE")
    return _DeploymentPlan(
        fingerprint,
        actions,
        targets,
        actions[-2],
        "var/hk-v1/host/post-reconcile.json",
        rollback_actions,
        str(document["application_build_results_fingerprint"]),
        image_inputs_fingerprint,
        tuple(expected_images),
        tuple((service, *predecessor_images[service]) for service in _SERVICES),
        recovery_limitations,
    )


def _parse_authority(
    path: Path, plan: _HostPlan, repository_root: Path, state_root: Path
) -> _Authority:
    content, document = _read_document(path, "HOST_APPLY_AUTHORITY_INVALID", trailing_newline=False)
    required = {
        "actions",
        "authority_id",
        "decision",
        "fingerprint",
        "plan_fingerprint",
        "repository_root",
        "schema_id",
        "schema_version",
        "state_root",
        "targets",
    }
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    authority_id = str(document.get("authority_id"))
    if (
        set(document) != required
        or document.get("schema_id") != _AUTHORITY_SCHEMA
        or document.get("schema_version") != _VERSION
        or _AUTHORITY_ID.fullmatch(authority_id) is None
        or document.get("decision") != "AUTHORIZED"
        or document.get("plan_fingerprint") != plan.fingerprint
        or document.get("actions") != list(plan.actions)
        or document.get("targets") != list(plan.targets)
        or document.get("repository_root") != str(repository_root)
        or document.get("state_root") != str(state_root)
        or supplied != _fingerprint(unsigned)
    ):
        _fail("HOST_APPLY_AUTHORITY_INVALID")
    return _Authority(authority_id, _bytes_fingerprint(content))


def build_host_apply_authority(
    plan_path: Path,
    repository_root: Path,
    state_root: Path,
    *,
    authority_id: str,
) -> bytes:
    """Build canonical authority bytes for one exact retained host plan."""
    _safe_path(repository_root, "HOST_APPLY_ROOT_INVALID")
    _safe_path(state_root, "HOST_APPLY_ROOT_INVALID")
    plan = _parse_plan(plan_path)
    if _AUTHORITY_ID.fullmatch(authority_id) is None:
        _fail("HOST_APPLY_AUTHORITY_INVALID")
    body: dict[str, object] = {
        "actions": list(plan.actions),
        "authority_id": authority_id,
        "decision": "AUTHORIZED",
        "plan_fingerprint": plan.fingerprint,
        "repository_root": str(repository_root),
        "schema_id": _AUTHORITY_SCHEMA,
        "schema_version": _VERSION,
        "state_root": str(state_root),
        "targets": list(plan.targets),
    }
    return _canonical({**body, "fingerprint": _fingerprint(body)})


def load_host_apply_authority(
    authority_path: Path,
    plan_path: Path,
    repository_root: Path,
    state_root: Path,
) -> str:
    """Validate one retained authority and return its exact fingerprint."""
    plan = _parse_plan(plan_path)
    return _parse_authority(authority_path, plan, repository_root, state_root).fingerprint


def _state_body(  # noqa: PLR0913 - retained state binds each independent outcome.
    plan: _HostPlan,
    authority: _Authority,
    *,
    result: str,
    step_receipts: list[object],
    rollback_receipts: list[object],
    recollected_fingerprint: str | None,
    rollback_complete: bool,
    recollected_path: str | None = None,
    build_results_fingerprint: str | None = None,
    build_results_path: str | None = None,
    complete: bool = False,
) -> dict[str, object]:
    return {
        "admission_limitations": (
            list(plan.admission_limitations) if isinstance(plan, _DeploymentPlan) else []
        ),
        "application_build_results_fingerprint": build_results_fingerprint,
        "application_build_results_path": build_results_path,
        "authority_fingerprint": authority.fingerprint,
        "authority_id": authority.authority_id,
        "complete": complete,
        "index_deleted": False,
        "plan_fingerprint": plan.fingerprint,
        "provider_called": False,
        "reboot_performed": False,
        "recollected_host_facts_fingerprint": recollected_fingerprint,
        "recollected_host_facts_path": recollected_path,
        "result": result,
        "rollback_complete": rollback_complete,
        "rollback_receipts": rollback_receipts,
        "routing_mutated": False,
        "schema_id": _STATE_SCHEMA,
        "schema_version": _VERSION,
        "source_called": False,
        "step_receipts": step_receipts,
        "v1_admitted": False,
    }


def _seal_state(body: dict[str, object]) -> bytes:
    return _canonical({**body, "fingerprint": _fingerprint(body)})


def _state_path(state_root: Path, plan: _HostPlan) -> Path:
    return state_root / ("hap_" + plan.fingerprint.removeprefix("sha256:")[:48]) / "state.json"


def _write_state(path: Path, content: bytes) -> None:
    _safe_path(path, "HOST_APPLY_STATE_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{token_hex(16)}.tmp")
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    if path.read_bytes() != content:
        _fail("HOST_APPLY_STATE_INVALID")


def _load_state(path: Path, plan: _HostPlan, authority: _Authority) -> dict[str, object] | None:
    if not path.exists():
        return None
    content, document = _read_document(path, "HOST_APPLY_STATE_INVALID", trailing_newline=False)
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    if (
        supplied != _fingerprint(unsigned)
        or document.get("schema_id") != _STATE_SCHEMA
        or document.get("schema_version") != _VERSION
        or document.get("plan_fingerprint") != plan.fingerprint
        or document.get("authority_id") != authority.authority_id
        or document.get("authority_fingerprint") != authority.fingerprint
        or _canonical(document) != content
    ):
        _fail("HOST_APPLY_STATE_INVALID")
    _validate_state_shape(document, plan)
    return document


def _validate_state_shape(document: dict[str, object], plan: _HostPlan) -> None:
    required = {
        "admission_limitations",
        "application_build_results_fingerprint",
        "application_build_results_path",
        "authority_fingerprint",
        "authority_id",
        "complete",
        "fingerprint",
        "index_deleted",
        "plan_fingerprint",
        "provider_called",
        "reboot_performed",
        "recollected_host_facts_fingerprint",
        "recollected_host_facts_path",
        "result",
        "rollback_complete",
        "rollback_receipts",
        "routing_mutated",
        "schema_id",
        "schema_version",
        "source_called",
        "step_receipts",
        "v1_admitted",
    }
    steps = document.get("step_receipts")
    rollbacks = document.get("rollback_receipts")
    result = document.get("result")
    if (
        set(document) != required
        or type(document.get("complete")) is not bool
        or document.get("v1_admitted") is not False
        or document.get("admission_limitations")
        != (list(plan.admission_limitations) if isinstance(plan, _DeploymentPlan) else [])
        or document.get("index_deleted") is not False
        or document.get("provider_called") is not False
        or document.get("reboot_performed") is not False
        or document.get("routing_mutated") is not False
        or document.get("source_called") is not False
        or type(steps) is not list
        or type(rollbacks) is not list
        or result not in _allowed_results(plan)
    ):
        _fail("HOST_APPLY_STATE_INVALID")
    step_items = cast("list[object]", steps)
    rollback_items = cast("list[object]", rollbacks)
    if len(step_items) > len(plan.actions) or len(rollback_items) > len(plan.rollback_actions):
        _fail("HOST_APPLY_STATE_INVALID")
    expected_actions = plan.actions[: len(step_items)]
    if any(
        _receipt_action(item, sequence) != action
        for sequence, (item, action) in enumerate(
            zip(step_items, expected_actions, strict=True), start=1
        )
    ):
        _fail("HOST_APPLY_STATE_INVALID")
    rollback_actions = tuple(
        action.raw if isinstance(action, _RollbackAction) else action
        for action in plan.rollback_actions
    )
    if any(
        _receipt_action(item, sequence) != action
        for sequence, (item, action) in enumerate(
            zip(
                rollback_items,
                rollback_actions[: len(rollback_items)],
                strict=True,
            ),
            start=1,
        )
    ):
        _fail("HOST_APPLY_STATE_INVALID")
    if isinstance(plan, _DeploymentPlan):
        _validate_deployment_state(document, plan, step_items, rollback_items)
        return
    if document.get("complete") is not False:
        _fail("HOST_APPLY_STATE_INVALID")
    if result == "PHASE_COMPLETE_REPLAN_REQUIRED" and (
        len(step_items) != _PHASE_ACTION_COUNT
        or rollback_items
        or document.get("rollback_complete") is not False
        or _FP.fullmatch(str(document.get("recollected_host_facts_fingerprint"))) is None
        or type(document.get("recollected_host_facts_path")) is not str
        or not Path(str(document.get("recollected_host_facts_path"))).is_absolute()
        or _FP.fullmatch(str(document.get("application_build_results_fingerprint"))) is None
        or type(document.get("application_build_results_path")) is not str
        or not Path(str(document.get("application_build_results_path"))).is_absolute()
    ):
        _fail("HOST_APPLY_STATE_INVALID")
    if result == "IN_PROGRESS" and (
        len(step_items) not in {0, _IMAGE_ACTION_COUNT}
        or rollback_items
        or document.get("rollback_complete") is not False
        or document.get("recollected_host_facts_fingerprint") is not None
        or document.get("recollected_host_facts_path") is not None
    ):
        _fail("HOST_APPLY_STATE_INVALID")
    if result in {"FAILED_ROLLED_BACK", "FAILED_ROLLBACK_UNVERIFIED"} and (
        len(step_items) not in {_IMAGE_ACTION_COUNT, _PHASE_ACTION_COUNT}
        or len(rollback_items) != _IMAGE_ACTION_COUNT
        or document.get("recollected_host_facts_fingerprint") is not None
        or document.get("recollected_host_facts_path") is not None
        or (document.get("rollback_complete") is True) != (result == "FAILED_ROLLED_BACK")
    ):
        _fail("HOST_APPLY_STATE_INVALID")


def _allowed_results(plan: _HostPlan) -> set[str]:
    if isinstance(plan, _DeploymentPlan):
        return {
            "COMPLETE",
            "FAILED_ROLLED_BACK",
            "FAILED_ROLLBACK_UNVERIFIED",
            "IN_PROGRESS",
            "ROLLBACK_IN_PROGRESS",
        }
    return {
        "FAILED_ROLLED_BACK",
        "FAILED_ROLLBACK_UNVERIFIED",
        "IN_PROGRESS",
        "PHASE_COMPLETE_REPLAN_REQUIRED",
    }


def _all_receipts_succeeded(items: list[object]) -> bool:
    return all(_object(item, "HOST_APPLY_STATE_INVALID").get("returncode") == 0 for item in items)


def _validate_deployment_state(
    document: dict[str, object],
    plan: _DeploymentPlan,
    steps: list[object],
    rollbacks: list[object],
) -> None:
    result = document["result"]
    facts_fingerprint = document["recollected_host_facts_fingerprint"]
    facts_path = document["recollected_host_facts_path"]
    if document.get("application_build_results_fingerprint") != plan.build_results_fingerprint:
        _fail("HOST_APPLY_STATE_INVALID")
    if document.get("application_build_results_path") is not None:
        _fail("HOST_APPLY_STATE_INVALID")
    if result == "IN_PROGRESS":
        recollected = len(steps) == len(plan.actions) - 1
        if (
            len(steps) > len(plan.actions) - 1
            or rollbacks
            or not _all_receipts_succeeded(steps)
            or (facts_fingerprint is not None) != recollected
            or (facts_path is not None) != recollected
            or (recollected and _FP.fullmatch(str(facts_fingerprint)) is None)
            or (recollected and type(facts_path) is not str)
            or document["rollback_complete"] is not False
            or document["complete"] is not False
        ):
            _fail("HOST_APPLY_STATE_INVALID")
    if result == "ROLLBACK_IN_PROGRESS" and (
        not steps
        or len(rollbacks) >= len(plan.rollback_actions)
        or facts_fingerprint is not None
        or facts_path is not None
        or document["rollback_complete"] is not False
        or document["complete"] is not False
    ):
        _fail("HOST_APPLY_STATE_INVALID")
    if result == "COMPLETE" and (
        len(steps) != len(plan.actions)
        or rollbacks
        or not _all_receipts_succeeded(steps)
        or _FP.fullmatch(str(facts_fingerprint)) is None
        or type(facts_path) is not str
        or document["rollback_complete"] is not False
        or document["complete"] is not True
    ):
        _fail("HOST_APPLY_STATE_INVALID")
    if result in {"FAILED_ROLLED_BACK", "FAILED_ROLLBACK_UNVERIFIED"} and (
        not steps
        or len(rollbacks) != len(plan.rollback_actions)
        or document["complete"] is not False
        or (document["rollback_complete"] is True) != (result == "FAILED_ROLLED_BACK")
    ):
        _fail("HOST_APPLY_STATE_INVALID")


def _receipt_action(value: object, sequence: int) -> str:
    receipt = _object(value, "HOST_APPLY_STATE_INVALID")
    if (
        set(receipt)
        != {
            "action",
            "argv_fingerprint",
            "readback",
            "returncode",
            "sequence",
            "stderr_fingerprint",
            "stdout_fingerprint",
        }
        or receipt.get("sequence") != sequence
        or type(receipt.get("returncode")) is not int
        or _FP.fullmatch(str(receipt.get("argv_fingerprint"))) is None
        or _FP.fullmatch(str(receipt.get("stderr_fingerprint"))) is None
        or _FP.fullmatch(str(receipt.get("stdout_fingerprint"))) is None
        or type(receipt.get("readback")) is not dict
    ):
        _fail("HOST_APPLY_STATE_INVALID")
    return str(receipt.get("action"))


def _command_receipt(
    *,
    sequence: int,
    action: str,
    argv: tuple[str, ...],
    result: HostApplyCommandResult,
    readback: dict[str, object],
) -> dict[str, object]:
    return {
        "action": action,
        "argv_fingerprint": _fingerprint(list(argv)),
        "readback": readback,
        "returncode": result.returncode,
        "sequence": sequence,
        "stderr_fingerprint": _bytes_fingerprint(result.stderr.encode("utf-8")),
        "stdout_fingerprint": _bytes_fingerprint(result.stdout.encode("utf-8")),
    }


def _build_receipts(
    plan: _Plan, argv: tuple[str, ...], result: HostApplyCommandResult
) -> tuple[list[object], tuple[tuple[str, str, str, str], ...] | None]:
    if result.returncode != 0:
        return (
            [
                _command_receipt(
                    sequence=action.sequence,
                    action=action.raw,
                    argv=argv,
                    result=result,
                    readback={"image_built": False},
                )
                for action in plan.image_actions
            ],
            None,
        )
    lines = tuple(line for line in result.stdout.splitlines() if line)
    if len(lines) != len(plan.image_actions):
        _fail("HOST_APPLY_BUILD_READBACK_INVALID")
    parsed: dict[str, tuple[str, str, str]] = {}
    for line in lines:
        parts = line.split(" ")
        if (
            len(parts) != _BUILD_OUTPUT_FIELDS
            or parts[0] not in _SERVICES
            or parts[0] in parsed
            or parts[1] != f"asklegal/{parts[0]}:{_CANDIDATE_TAG_SUFFIX}"
            or _FP.fullmatch(parts[2]) is None
            or re.fullmatch(r"[0-9a-f]{128}", parts[3]) is None
        ):
            _fail("HOST_APPLY_BUILD_READBACK_INVALID")
        parsed[parts[0]] = (parts[1], parts[2], parts[3])
    if frozenset(parsed) != frozenset(_SERVICES):
        _fail("HOST_APPLY_BUILD_READBACK_INVALID")
    receipts: list[object] = []
    rows: list[tuple[str, str, str, str]] = []
    for action in plan.image_actions:
        tag, image_id, installed_tree_sha512 = parsed[action.service]
        if tag != action.tag:
            _fail("HOST_APPLY_BUILD_READBACK_INVALID")
        receipts.append(
            _command_receipt(
                sequence=action.sequence,
                action=action.raw,
                argv=argv,
                result=result,
                readback={
                    "image_id": image_id,
                    "installed_tree_sha512": installed_tree_sha512,
                },
            )
        )
        rows.append((action.service, action.tag, image_id, installed_tree_sha512))
    return receipts, tuple(rows)


def _build_results_path(repository_root: Path) -> Path:
    return repository_root / "var/hk-v1/host/application-build-results.json"


def _current_build_inputs(repository_root: Path, expected_fingerprint: str) -> dict[str, object]:
    image_inputs_path = repository_root / "infrastructure/poc/application_image_inputs.json"
    _safe_path(image_inputs_path, "HOST_APPLY_BUILD_INPUT_INVALID", file=True)
    try:
        raw = image_inputs_path.read_bytes()
        if len(raw) > _MAX_BYTES:
            _fail("HOST_APPLY_BUILD_INPUT_INVALID")
        image_inputs = _object(json.loads(raw), "HOST_APPLY_BUILD_INPUT_INVALID")
    except HostApplyError:
        raise
    except (OSError, TypeError, ValueError) as error:
        code = "HOST_APPLY_BUILD_INPUT_INVALID"
        raise HostApplyError(code) from error
    current_inputs_fingerprint = _fingerprint(
        {
            "application_image_inputs": image_inputs,
            "workspace_source_fingerprint": workspace_source_fingerprint(repository_root),
        }
    )
    if current_inputs_fingerprint != expected_fingerprint:
        _fail("HOST_APPLY_BUILD_INPUT_INVALID")
    return image_inputs


def _write_build_results(execution: _Execution, rows: tuple[tuple[str, str, str, str], ...]) -> str:
    if not isinstance(execution.plan, _Plan):
        _fail("HOST_APPLY_ACTION_INVALID")
    image_inputs = _current_build_inputs(
        execution.repository_root, execution.plan.image_inputs_fingerprint
    )
    content = build_application_build_results(image_inputs, rows, root=execution.repository_root)
    output = _build_results_path(execution.repository_root)
    _write_state(output, content)
    fingerprint, _path = _retained_build_results(execution)
    return fingerprint


def _validated_build_results(
    repository_root: Path, expected_image_inputs_fingerprint: str
) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    """Reread one exact current build-result set against current source inputs."""
    output = _build_results_path(repository_root)
    content, document = _read_document(
        output, "HOST_APPLY_BUILD_READBACK_INVALID", trailing_newline=True
    )
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    images = document.get("images")
    if (
        set(document)
        != {
            "application_image_inputs_fingerprint",
            "fingerprint",
            "images",
            "schema_id",
            "schema_version",
        }
        or document.get("schema_id") != "asklegal.hk-v1-application-build-results/v1"
        or document.get("schema_version") != _VERSION
        or document.get("application_image_inputs_fingerprint") != expected_image_inputs_fingerprint
        or supplied != _fingerprint(unsigned)
        or type(images) is not list
    ):
        _fail("HOST_APPLY_BUILD_READBACK_INVALID")
    service_ids: list[str] = []
    service_images: list[tuple[str, str]] = []
    for value in cast("list[object]", images):
        item = _object(value, "HOST_APPLY_BUILD_READBACK_INVALID")
        service = str(item.get("service_id"))
        if (
            set(item)
            != {
                "application_path",
                "image_id",
                "installed_tree_sha512",
                "service_id",
                "tag",
            }
            or service not in _SERVICES
            or item.get("application_path") != f"apps/{service}"
            or item.get("tag") != f"asklegal/{service}:{_CANDIDATE_TAG_SUFFIX}"
            or _FP.fullmatch(str(item.get("image_id"))) is None
            or re.fullmatch(r"[0-9a-f]{128}", str(item.get("installed_tree_sha512"))) is None
        ):
            _fail("HOST_APPLY_BUILD_READBACK_INVALID")
        service_ids.append(service)
        service_images.append((service, str(item["image_id"])))
    if tuple(service_ids) != _SERVICES:
        _fail("HOST_APPLY_BUILD_READBACK_INVALID")
    return _bytes_fingerprint(content), str(output), tuple(service_images)


def _retained_build_results(execution: _Execution) -> tuple[str, str]:
    if not isinstance(execution.plan, _Plan):
        _fail("HOST_APPLY_BUILD_READBACK_INVALID")
    fingerprint, path, _images = _validated_build_results(
        execution.repository_root, execution.plan.image_inputs_fingerprint
    )
    return fingerprint, path


def _validate_current_deployment_inputs(repository_root: Path, plan: _DeploymentPlan) -> None:
    """Stop a stale source or replaced build-result set before any host effect."""
    _current_build_inputs(repository_root, plan.image_inputs_fingerprint)
    fingerprint, _path, images = _validated_build_results(
        repository_root, plan.image_inputs_fingerprint
    )
    if fingerprint != plan.build_results_fingerprint or images != plan.expected_images:
        _fail("HOST_APPLY_BUILD_READBACK_INVALID")


def _rollback(
    plan: _Plan, runner: HostApplyRunner, repository_root: Path
) -> tuple[list[object], bool]:
    receipts: list[object] = []
    complete = True
    for action in plan.rollback_actions:
        argv = (
            "/usr/bin/docker",
            "container",
            "inspect",
            "--format",
            "{{.Image}}",
            f"asklegal-{action.service}",
        )
        result = runner.run(argv, cwd=repository_root)
        observed = result.stdout.strip()
        if action.image_id is None:
            matched = result.returncode != 0
        else:
            matched = result.returncode == 0 and observed == action.image_id
        complete = complete and matched
        receipts.append(
            _command_receipt(
                sequence=action.sequence,
                action=action.raw,
                argv=argv,
                result=result,
                readback={"predecessor_preserved": matched},
            )
        )
    return receipts, complete


def _terminal_state(document: dict[str, object]) -> bytes | None:
    if document.get("result") not in {
        "COMPLETE",
        "PHASE_COMPLETE_REPLAN_REQUIRED",
        "FAILED_ROLLED_BACK",
        "FAILED_ROLLBACK_UNVERIFIED",
    }:
        return None
    return _canonical(document)


def _failed_execution(execution: _Execution, steps: list[object]) -> bytes:
    if not isinstance(execution.plan, _Plan):
        _fail("HOST_APPLY_STATE_INVALID")
    rollback_receipts, rollback_complete = _rollback(
        execution.plan, execution.runner, execution.repository_root
    )
    result = "FAILED_ROLLED_BACK" if rollback_complete else "FAILED_ROLLBACK_UNVERIFIED"
    failed = _state_body(
        execution.plan,
        execution.authority,
        result=result,
        step_receipts=steps,
        rollback_receipts=rollback_receipts,
        recollected_fingerprint=None,
        rollback_complete=rollback_complete,
    )
    content = _seal_state(failed)
    _write_state(execution.state_path, content)
    return content


def _execute_build(execution: _Execution) -> tuple[list[object], bytes | None]:
    if not isinstance(execution.plan, _Plan):
        _fail("HOST_APPLY_ACTION_INVALID")
    argv = (
        str(execution.repository_root / ".venv/bin/python"),
        "-m",
        "tools.v1_poc_build_images",
        "--tag-suffix",
        _CANDIDATE_TAG_SUFFIX,
    )
    result = execution.runner.run(argv, cwd=execution.repository_root)
    steps, rows = _build_receipts(execution.plan, argv, result)
    if rows is None:
        return steps, _failed_execution(execution, steps)
    build_results_fingerprint = _write_build_results(execution, rows)
    build_results_path = str(_build_results_path(execution.repository_root))
    progress = _state_body(
        execution.plan,
        execution.authority,
        result="IN_PROGRESS",
        step_receipts=steps,
        rollback_receipts=[],
        recollected_fingerprint=None,
        rollback_complete=False,
        build_results_fingerprint=build_results_fingerprint,
        build_results_path=build_results_path,
    )
    _write_state(execution.state_path, _seal_state(progress))
    return steps, None


def _execute_recollect(execution: _Execution, steps: list[object]) -> bytes:
    if not isinstance(execution.plan, _Plan):
        _fail("HOST_APPLY_ACTION_INVALID")
    build_results_fingerprint, build_results_path = _retained_build_results(execution)
    output = execution.repository_root / execution.plan.recollect_output
    _safe_path(output, "HOST_APPLY_ACTION_INVALID")
    if not output.is_relative_to(execution.repository_root):
        _fail("HOST_APPLY_ACTION_INVALID")
    argv = (
        str(execution.repository_root / ".venv/bin/python"),
        "-m",
        "tools.v1_poc_collect_host_facts",
        "--acknowledge-read-only-host-inspection",
        "--output",
        str(output),
    )
    result = execution.runner.run(argv, cwd=execution.repository_root)
    if result.returncode != 0:
        steps.append(
            _command_receipt(
                sequence=6,
                action=execution.plan.recollect_action,
                argv=argv,
                result=result,
                readback={"host_facts_collected": False},
            )
        )
        return _failed_execution(execution, steps)
    host_fingerprint = execution.readback.fingerprint(output)
    if _FP.fullmatch(host_fingerprint) is None:
        _fail("HOST_APPLY_RECOLLECT_READBACK_INVALID")
    steps.append(
        _command_receipt(
            sequence=6,
            action=execution.plan.recollect_action,
            argv=argv,
            result=result,
            readback={"host_facts_fingerprint": host_fingerprint},
        )
    )
    complete = _state_body(
        execution.plan,
        execution.authority,
        result="PHASE_COMPLETE_REPLAN_REQUIRED",
        step_receipts=steps,
        rollback_receipts=[],
        recollected_fingerprint=host_fingerprint,
        rollback_complete=False,
        recollected_path=str(output),
        build_results_fingerprint=build_results_fingerprint,
        build_results_path=build_results_path,
    )
    content = _seal_state(complete)
    _write_state(execution.state_path, content)
    return content


def _deployment_body(  # noqa: PLR0913 - each retained outcome is independently bound.
    execution: _Execution,
    plan: _DeploymentPlan,
    *,
    result: str,
    steps: list[object],
    rollbacks: list[object],
    recollected_fingerprint: str | None = None,
    recollected_path: str | None = None,
    rollback_complete: bool = False,
    complete: bool = False,
) -> dict[str, object]:
    return _state_body(
        plan,
        execution.authority,
        result=result,
        step_receipts=steps,
        rollback_receipts=rollbacks,
        recollected_fingerprint=recollected_fingerprint,
        recollected_path=recollected_path,
        build_results_fingerprint=plan.build_results_fingerprint,
        build_results_path=None,
        rollback_complete=rollback_complete,
        complete=complete,
    )


def _deployment_helper(execution: _Execution) -> Path:
    helper = execution.repository_root / "infrastructure/poc/provisioning/90-host-apply.sh"
    _safe_path(helper, "HOST_APPLY_HELPER_UNAVAILABLE", file=True)
    return helper


def _collector_argv(execution: _Execution, output: Path) -> tuple[str, ...]:
    return (
        str(execution.repository_root / ".venv/bin/python"),
        "-m",
        "tools.v1_poc_collect_host_facts",
        "--acknowledge-read-only-host-inspection",
        "--output",
        str(output),
    )


def _deployment_action_result(
    execution: _Execution,
    raw: str,
    *,
    rollback: bool,
) -> tuple[tuple[str, ...], HostApplyCommandResult, dict[str, object], str | None, str | None]:
    if "|RECOLLECT_HOST_FACTS|" not in raw:
        argv = (
            "/usr/bin/bash",
            str(_deployment_helper(execution)),
            raw,
            str(execution.state_path.parent),
        )
        result = execution.runner.run(argv, cwd=execution.repository_root)
        return argv, result, {"action_complete": result.returncode == 0}, None, None
    output_name = "post-rollback.json" if rollback else "post-reconcile.json"
    output = execution.repository_root / "var/hk-v1/host" / output_name
    _safe_path(output, "HOST_APPLY_ACTION_INVALID")
    argv = _collector_argv(execution, output)
    result = execution.runner.run(argv, cwd=execution.repository_root)
    if result.returncode != 0:
        return argv, result, {"host_facts_collected": False}, None, None
    fingerprint = execution.readback.fingerprint(output)
    if _FP.fullmatch(fingerprint) is None:
        _fail("HOST_APPLY_RECOLLECT_READBACK_INVALID")
    if not rollback and not execution.readback.firewall_ready(output):
        failed = HostApplyCommandResult(1, result.stdout, "HOST_APPLY_FIREWALL_READBACK_INVALID")
        return argv, failed, {"host_facts_collected": True, "firewall_admitted": False}, None, None
    if (
        not rollback
        and isinstance(execution.plan, _DeploymentPlan)
        and (
            not execution.readback.deployment_ready(output, execution.plan.expected_images)
            or not execution.readback.deployment_manifest_ready(execution.plan.expected_images)
            or not execution.readback.bootstrap_ready()
        )
    ):
        failed = HostApplyCommandResult(1, result.stdout, "HOST_APPLY_DEPLOYMENT_READBACK_INVALID")
        return (
            argv,
            failed,
            {"host_facts_collected": True, "deployment_admitted": False},
            None,
            None,
        )
    if (
        rollback
        and isinstance(execution.plan, _DeploymentPlan)
        and not execution.readback.rollback_ready(output, execution.plan.predecessor_images)
    ):
        failed = HostApplyCommandResult(1, result.stdout, "HOST_APPLY_ROLLBACK_READBACK_INVALID")
        return (
            argv,
            failed,
            {"host_facts_collected": True, "rollback_admitted": False},
            None,
            None,
        )
    return (
        argv,
        result,
        {"host_facts_fingerprint": fingerprint},
        fingerprint,
        str(output),
    )


def _deployment_rollback(
    execution: _Execution,
    plan: _DeploymentPlan,
    steps: list[object],
    retained_rollbacks: list[object],
) -> bytes:
    rollbacks = list(retained_rollbacks)
    recollected_fingerprint: str | None = None
    recollected_path: str | None = None
    remaining = plan.rollback_actions[len(rollbacks) :]
    for sequence, raw in enumerate(remaining, start=len(rollbacks) + 1):
        argv, result, readback, observed_fingerprint, observed_path = _deployment_action_result(
            execution, raw, rollback=True
        )
        rollbacks.append(
            _command_receipt(
                sequence=sequence,
                action=raw,
                argv=argv,
                result=result,
                readback=readback,
            )
        )
        if observed_fingerprint is not None:
            recollected_fingerprint = observed_fingerprint
            recollected_path = observed_path
        if sequence < len(plan.rollback_actions):
            progress = _deployment_body(
                execution,
                plan,
                result="ROLLBACK_IN_PROGRESS",
                steps=steps,
                rollbacks=rollbacks,
            )
            _write_state(execution.state_path, _seal_state(progress))
    rollback_complete = _all_receipts_succeeded(rollbacks) and recollected_fingerprint is not None
    result_name = "FAILED_ROLLED_BACK" if rollback_complete else "FAILED_ROLLBACK_UNVERIFIED"
    failed = _deployment_body(
        execution,
        plan,
        result=result_name,
        steps=steps,
        rollbacks=rollbacks,
        recollected_fingerprint=recollected_fingerprint,
        recollected_path=recollected_path,
        rollback_complete=rollback_complete,
    )
    content = _seal_state(failed)
    _write_state(execution.state_path, content)
    return content


def _apply_deployment_locked(  # noqa: C901 - terminal replay and transaction states are closed.
    execution: _Execution, plan: _DeploymentPlan
) -> bytes:
    _deployment_helper(execution)
    retained = _load_state(execution.state_path, plan, execution.authority)
    if retained is not None:
        terminal = _terminal_state(retained)
        if terminal is not None:
            fingerprint = retained.get("recollected_host_facts_fingerprint")
            path_value = retained.get("recollected_host_facts_path")
            if fingerprint is not None and type(path_value) is not str:
                _fail("HOST_APPLY_RECOLLECT_READBACK_INVALID")
            facts_path = None if path_value is None else Path(cast("str", path_value))
            if fingerprint is not None and (
                facts_path is None or execution.readback.fingerprint(facts_path) != fingerprint
            ):
                _fail("HOST_APPLY_RECOLLECT_READBACK_INVALID")
            result = retained.get("result")
            if result == "COMPLETE" and (
                facts_path is None
                or not execution.readback.firewall_ready(facts_path)
                or not execution.readback.deployment_ready(facts_path, plan.expected_images)
                or not execution.readback.deployment_manifest_ready(plan.expected_images)
                or not execution.readback.bootstrap_ready()
            ):
                _fail("HOST_APPLY_DEPLOYMENT_READBACK_INVALID")
            if result == "FAILED_ROLLED_BACK" and (
                facts_path is None
                or not execution.readback.rollback_ready(facts_path, plan.predecessor_images)
            ):
                _fail("HOST_APPLY_ROLLBACK_READBACK_INVALID")
            return terminal
    steps = [] if retained is None else list(cast("list[object]", retained["step_receipts"]))
    rollbacks = (
        [] if retained is None else list(cast("list[object]", retained["rollback_receipts"]))
    )
    recollected_fingerprint = (
        None
        if retained is None
        else cast("str | None", retained["recollected_host_facts_fingerprint"])
    )
    recollected_path = (
        None if retained is None else cast("str | None", retained["recollected_host_facts_path"])
    )
    if retained is not None and retained.get("result") == "ROLLBACK_IN_PROGRESS":
        return _deployment_rollback(execution, plan, steps, rollbacks)
    if retained is None:
        initial = _deployment_body(
            execution,
            plan,
            result="IN_PROGRESS",
            steps=[],
            rollbacks=[],
        )
        _write_state(execution.state_path, _seal_state(initial))
    for sequence, raw in enumerate(plan.actions[len(steps) :], start=len(steps) + 1):
        argv, result, readback, facts_fingerprint, facts_path = _deployment_action_result(
            execution, raw, rollback=False
        )
        steps.append(
            _command_receipt(
                sequence=sequence,
                action=raw,
                argv=argv,
                result=result,
                readback=readback,
            )
        )
        if result.returncode != 0:
            progress = _deployment_body(
                execution,
                plan,
                result="ROLLBACK_IN_PROGRESS",
                steps=steps,
                rollbacks=[],
            )
            _write_state(execution.state_path, _seal_state(progress))
            return _deployment_rollback(execution, plan, steps, [])
        if facts_fingerprint is not None:
            recollected_fingerprint = facts_fingerprint
            recollected_path = facts_path
        if sequence < len(plan.actions):
            progress = _deployment_body(
                execution,
                plan,
                result="IN_PROGRESS",
                steps=steps,
                rollbacks=[],
                recollected_fingerprint=recollected_fingerprint,
                recollected_path=recollected_path,
            )
            _write_state(execution.state_path, _seal_state(progress))
            continue
        complete = _deployment_body(
            execution,
            plan,
            result="COMPLETE",
            steps=steps,
            rollbacks=[],
            recollected_fingerprint=recollected_fingerprint,
            recollected_path=recollected_path,
            complete=True,
        )
        content = _seal_state(complete)
        _write_state(execution.state_path, content)
        return content
    _fail("HOST_APPLY_STATE_INVALID")


def _apply_locked(execution: _Execution) -> bytes:
    if isinstance(execution.plan, _DeploymentPlan):
        return _apply_deployment_locked(execution, execution.plan)
    retained = _load_state(execution.state_path, execution.plan, execution.authority)
    if retained is not None:
        terminal = _terminal_state(retained)
        if terminal is not None:
            if retained.get("result") == "PHASE_COMPLETE_REPLAN_REQUIRED":
                output = execution.repository_root / execution.plan.recollect_output
                observed = execution.readback.fingerprint(output)
                if observed != retained.get("recollected_host_facts_fingerprint"):
                    _fail("HOST_APPLY_RECOLLECT_READBACK_INVALID")
                build_fingerprint, build_path = _retained_build_results(execution)
                if build_fingerprint != retained.get(
                    "application_build_results_fingerprint"
                ) or build_path != retained.get("application_build_results_path"):
                    _fail("HOST_APPLY_BUILD_READBACK_INVALID")
            return terminal
    steps = [] if retained is None else list(cast("list[object]", retained["step_receipts"]))
    if retained is None:
        initial = _state_body(
            execution.plan,
            execution.authority,
            result="IN_PROGRESS",
            step_receipts=[],
            rollback_receipts=[],
            recollected_fingerprint=None,
            rollback_complete=False,
        )
        _write_state(execution.state_path, _seal_state(initial))
    if not steps:
        steps, terminal = _execute_build(execution)
        if terminal is not None:
            return terminal
    return _execute_recollect(execution, steps)


def load_host_apply_state(
    state_path: Path,
    plan_path: Path,
    authority_path: Path,
    repository_root: Path,
    state_root: Path,
) -> dict[str, object]:
    """Validate and load one exact plan/authority-bound retained apply state."""
    _safe_path(repository_root, "HOST_APPLY_ROOT_INVALID")
    _safe_path(state_root, "HOST_APPLY_ROOT_INVALID")
    plan = _parse_plan(plan_path)
    authority = _parse_authority(authority_path, plan, repository_root, state_root)
    if state_path != _state_path(state_root, plan):
        _fail("HOST_APPLY_STATE_INVALID")
    document = _load_state(state_path, plan, authority)
    if document is None:
        _fail("HOST_APPLY_STATE_INVALID")
    return document


def apply_host_plan(  # noqa: PLR0913, PLR0917 - exact inputs and ports are independent.
    plan_path: Path,
    authority_path: Path,
    repository_root: Path,
    state_root: Path,
    runner: HostApplyRunner,
    readback: HostFactsReadback,
) -> bytes:
    """Apply only the exact current image-build/recollect phase and then stop."""
    _safe_path(repository_root, "HOST_APPLY_ROOT_INVALID")
    _safe_path(state_root, "HOST_APPLY_ROOT_INVALID")
    if not repository_root.is_dir() or (state_root.exists() and not state_root.is_dir()):
        _fail("HOST_APPLY_ROOT_INVALID")
    plan = _parse_plan(plan_path)
    authority = _parse_authority(authority_path, plan, repository_root, state_root)
    if isinstance(plan, _Plan):
        _current_build_inputs(repository_root, plan.image_inputs_fingerprint)
    else:
        _validate_current_deployment_inputs(repository_root, plan)
    execution = _Execution(
        plan,
        authority,
        repository_root,
        _state_path(state_root, plan),
        runner,
        readback,
    )
    if isinstance(plan, _DeploymentPlan):
        _deployment_helper(execution)
    with exclusive_local_state_lock(execution.state_path):
        return _apply_locked(execution)


class SubprocessArgvRunner:
    """Real argv-only adapter; no shell, glob expansion, or caller command text."""

    def run(self, argv: tuple[str, ...], *, cwd: Path) -> HostApplyCommandResult:
        """Run one fixed command and retain only bounded output for verification."""
        completed = subprocess.run(  # noqa: S603 - argv is closed and planner-validated.
            argv,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=3_600,
        )
        return HostApplyCommandResult(
            completed.returncode,
            completed.stdout[-100_000:],
            completed.stderr[-100_000:],
        )


class CanonicalHostFactsReadback:
    """Production parser for the exact collector-owned host facts envelope."""

    def fingerprint(self, path: Path) -> str:
        """Reparse all host facts before the executor reports phase completion."""
        facts = load_host_facts_output(path)
        return _fingerprint(host_facts_document(facts))

    def firewall_ready(self, path: Path) -> bool:
        """Require the exact firewall policies before the dead-man is confirmed."""
        facts = validated_complete_host_facts(load_host_facts_output(path))
        firewall = facts.get("firewall")
        if type(firewall) is not dict:
            return False
        document = cast("dict[str, object]", firewall)
        return all(
            document.get(name) == "DROP"
            for name in ("input_default", "forward_default", "direct_container_egress_default")
        )

    def deployment_ready(  # noqa: C901, PLR0911 - every exact runtime layer fails closed.
        self, path: Path, expected_images: tuple[tuple[str, str], ...]
    ) -> bool:
        """Require the exact supervised, healthy, non-orphan runtime inventory."""
        facts = validated_complete_host_facts(load_host_facts_output(path))
        containers = facts.get("containers")
        systemd = facts.get("systemd")
        applications = facts.get("applications")
        if (
            type(containers) is not list
            or type(systemd) is not dict
            or type(applications) is not list
        ):
            return False
        observed: dict[str, tuple[str, str, str]] = {}
        for value in cast("list[object]", containers):
            if type(value) is not dict:
                return False
            item = cast("dict[str, object]", value)
            name = item.get("name")
            image_id = item.get("image_id")
            runtime_state = item.get("runtime_state")
            health = item.get("health")
            if (
                type(name) is not str
                or type(image_id) is not str
                or type(runtime_state) is not str
                or type(health) is not str
                or name in observed
            ):
                return False
            observed[name] = (image_id, runtime_state, health)
        if tuple(sorted(observed)) != _CONTAINER_NAMES or not all(
            observed[name][1] == "running" and observed[name][2] in {"HEALTHY", "NONE"}
            for name in _CONTAINER_NAMES
        ):
            return False
        if not all(
            observed.get(f"asklegal-{service}")
            == (image_id, "running", observed[f"asklegal-{service}"][2])
            for service, image_id in expected_images
        ):
            return False
        systemd_document = cast("dict[str, object]", systemd)
        target = systemd_document.get("target")
        service_units = systemd_document.get("service_units")
        timer_units = systemd_document.get("timer_units")
        if (
            type(target) is not dict
            or type(service_units) is not list
            or type(timer_units) is not list
        ):
            return False

        def active_units(values: list[object], expected: tuple[str, ...]) -> bool:
            rows: list[tuple[str, str, str]] = []
            for value in values:
                if type(value) is not dict:
                    return False
                row = cast("dict[str, object]", value)
                unit_name = row.get("unit_name")
                load_state = row.get("load_state")
                active_state = row.get("active_state")
                if not all(type(item) is str for item in (unit_name, load_state, active_state)):
                    return False
                rows.append(
                    (cast("str", unit_name), cast("str", load_state), cast("str", active_state))
                )
            return tuple(name for name, _load, _active in rows) == expected and all(
                load == "loaded" and active == "active" for _name, load, active in rows
            )

        target_row = cast("dict[str, object]", target)
        if (
            target_row.get("unit_name") != "asklegal.target"
            or target_row.get("load_state") != "loaded"
            or target_row.get("active_state") != "active"
            or target_row.get("unit_file_state") != "enabled"
            or not active_units(cast("list[object]", service_units), _SYSTEMD_SERVICE_UNITS)
            or not active_units(cast("list[object]", timer_units), _SYSTEMD_TIMER_UNITS)
        ):
            return False
        application_rows: list[tuple[str, str, str]] = []
        for value in cast("list[object]", applications):
            if type(value) is not dict:
                return False
            row = cast("dict[str, object]", value)
            identity = (
                row.get("application_id"),
                row.get("container_name"),
                row.get("systemd_unit"),
            )
            if not all(type(item) is str for item in identity):
                return False
            if row.get("active_state") != "active" or row.get("health") not in {"HEALTHY", "NONE"}:
                return False
            application_rows.append(cast("tuple[str, str, str]", identity))
        return tuple(application_rows) == _APPLICATIONS

    def deployment_manifest_ready(self, expected_images: tuple[tuple[str, str], ...]) -> bool:
        """Open without following symlinks and prove exact durable launch input bytes."""
        expected = b"".join(
            f"{service} {image_id}\n".encode("ascii") for service, image_id in expected_images
        )
        try:
            descriptor = os.open(
                _DEPLOYMENT_MANIFEST,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
        except OSError:
            return False
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != _DEPLOYMENT_MANIFEST_MODE
                or metadata.st_uid != 0
                or metadata.st_gid != 0
                or metadata.st_size != len(expected)
            ):
                return False
            content = os.read(descriptor, len(expected) + 1)
            return content == expected and os.read(descriptor, 1) == b""
        except OSError:
            return False
        finally:
            os.close(descriptor)

    def bootstrap_ready(self) -> bool:
        """Require both root-owned canonical receipts and their closed success claims."""
        register = self._bootstrap_receipt(_REGISTER_RECEIPT)
        vault = self._bootstrap_receipt(_VAULT_RECEIPT)
        if register is None or vault is None:
            return False
        register_unsigned = dict(register)
        register_unsigned.pop("fingerprint")
        vault_unsigned = dict(vault)
        vault_unsigned.pop("fingerprint")
        identities = register.get("application_identities")
        migration_prefix = register.get("migration_prefix")
        vaults = vault.get("vaults")
        migration_rows = (
            cast("list[object]", migration_prefix) if type(migration_prefix) is list else []
        )
        vault_rows = cast("list[object]", vaults) if type(vaults) is list else []
        return (
            set(register)
            == {
                "application_identities",
                "database",
                "fingerprint",
                "migration_prefix",
                "result",
                "schema_id",
                "schema_version",
                "verified",
            }
            and register.get("schema_id") == "asklegal.hk-v1-register-bootstrap-readback/v1"
            and register.get("schema_version") == _VERSION
            and register.get("database") == "AskLegalPocOperational"
            and register.get("result") == "COMPLETE"
            and register.get("verified") is True
            and identities
            == [
                "asklegal_acquisition_app",
                "asklegal_control_app",
                "asklegal_legal_processing_app",
                "asklegal_promotion_app",
                "asklegal_review_app",
            ]
            and bool(migration_rows)
            and register.get("fingerprint") == _fingerprint(register_unsigned)
            and set(vault)
            == {
                "fingerprint",
                "result",
                "retention_days",
                "retention_mode",
                "schema_id",
                "schema_version",
                "vaults",
                "verified",
            }
            and vault.get("schema_id") == "asklegal.hk-v1-vault-bootstrap-readback/v1"
            and vault.get("schema_version") == _VERSION
            and vault.get("result") == "COMPLETE"
            and vault.get("verified") is True
            and vault.get("retention_mode") == "COMPLIANCE"
            and vault.get("retention_days") == _VAULT_RETENTION_DAYS
            and bool(vault_rows)
            and [
                cast("dict[str, object]", item).get("vault")
                for item in vault_rows
                if type(item) is dict
            ]
            == ["PRIMARY", "RECOVERY"]
            and all(
                type(item) is dict
                and item.get("object_lock") == "Enabled"
                and item.get("versioning") == "Enabled"
                for item in vault_rows
            )
            and vault.get("fingerprint") == _fingerprint(vault_unsigned)
        )

    @staticmethod
    def _bootstrap_receipt(  # noqa: PLR0911 - each file invariant fails closed.
        path: Path,
    ) -> dict[str, object] | None:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        except OSError:
            return None
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != _BOOTSTRAP_RECEIPT_MODE
                or metadata.st_uid != 0
                or metadata.st_gid != 0
                or not 1 <= metadata.st_size <= _MAX_BYTES
            ):
                return None
            content = os.read(descriptor, metadata.st_size + 1)
            if len(content) != metadata.st_size or os.read(descriptor, 1) != b"":
                return None
            parsed: object = json.loads(content)
            if type(parsed) is not dict:
                return None
            document = cast("dict[str, object]", parsed)
            if content != _canonical(document):
                return None
            return document  # noqa: TRY300 - descriptor must close in finally.
        except OSError, UnicodeDecodeError, ValueError:
            return None
        finally:
            os.close(descriptor)

    def rollback_ready(
        self,
        path: Path,
        expected_images: tuple[tuple[str, str | None, str | None], ...],
    ) -> bool:
        """Require every exact predecessor image and every declared absence."""
        facts = validated_complete_host_facts(load_host_facts_output(path))
        containers = facts.get("containers")
        if type(containers) is not list:
            return False
        observed: dict[str, tuple[str, str]] = {}
        for value in cast("list[object]", containers):
            if type(value) is not dict:
                return False
            item = cast("dict[str, object]", value)
            name = item.get("name")
            image_id = item.get("image_id")
            runtime_state = item.get("runtime_state")
            if type(name) is not str or type(image_id) is not str or type(runtime_state) is not str:
                return False
            observed[name] = (image_id, runtime_state)
        return all(
            (
                f"asklegal-{service}" not in observed
                if image_id is None
                else observed.get(f"asklegal-{service}") == (image_id, runtime_state)
            )
            for service, image_id, runtime_state in expected_images
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--authority", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Require an explicit execute flag and exact authority before host commands."""
    arguments = _parser().parse_args(argv)
    if not arguments.execute:
        sys.stderr.write("HOST_APPLY_EXECUTE_FLAG_REQUIRED\n")
        return 2
    try:
        result = apply_host_plan(
            arguments.plan,
            arguments.authority,
            arguments.repository_root,
            arguments.state_root,
            SubprocessArgvRunner(),
            CanonicalHostFactsReadback(),
        )
    except HostApplyError, OSError, subprocess.SubprocessError, ValueError:
        sys.stderr.write("HOST_APPLY_NOT_READY\n")
        return 2
    sys.stdout.buffer.write(result + b"\n")
    document = cast("dict[str, object]", json.loads(result))
    if document.get("result") == "COMPLETE":
        return 0
    return 3 if document.get("result") == "PHASE_COMPLETE_REPLAN_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
