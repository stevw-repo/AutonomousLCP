"""Rotate the Primary Versity root pair without exposing values or replacing vault data."""

# Root-only orchestration collapses provider/system errors to closed value-free codes.
# ruff: noqa: BLE001, C901, D101, D102, D103, D105, D107, E501, EM101, FBT003, PLR0911, PLR0913, TRY300

from __future__ import annotations

import argparse
import fcntl
import os
import re
import stat
import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe
from typing import Never, Protocol, cast

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import S3AccessCredential, S3VaultError

from tools.hk_v1_vault_application_rotation import (
    ExactCommandRunner,
    QuietExactCommandRunner,
    candidate_image_provenance,
    credential_snapshot,
    snapshot_binding,
    staging_receipt_binding,
)

_VERSION = "1.0.0"
_PLAN_SCHEMA = "asklegal.hk-v1-primary-vault-root-rotation-plan"
_REPORT_SCHEMA = "asklegal.hk-v1-primary-vault-root-rotation-report"
_NETWORK_SCHEMA = "asklegal.hk-v1-primary-vault-root-rotation-network-receipt"
_ROOT_NAMES = ("vault-primary-root-access", "vault-primary-root-secret")
_APPLICATION_NAMES = (
    "vault-primary-acquisition",
    "vault-primary-control",
    "vault-primary-processing",
    "vault-primary-promotion",
    "vault-primary-review",
)
_APPLICATION_UNITS = (
    "asklegal-acquisition-worker.service",
    "asklegal-control-plane.service",
    "asklegal-legal-processing-worker.service",
    "asklegal-promotion-worker.service",
    "asklegal-review-api.service",
)
_VAULT_UNIT = "asklegal-vault-primary.service"
_BOOTSTRAP_UNIT = "asklegal-vault-bootstrap.service"
_STOP_UNITS = (*_APPLICATION_UNITS, _BOOTSTRAP_UNIT, _VAULT_UNIT)
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_BINDING = re.compile(r"^binding_[0-9a-f]{48}$")
_ROTATION = re.compile(r"^rot_[0-9a-f]{48}$")
_SEALED = re.compile(r"^sealed_[0-9a-f]{64}$")
_DATA = re.compile(r"^vaultdata_[0-9a-f]{64}$")
_RUNTIME = re.compile(r"^runtimecfg_[0-9a-f]{64}$")
_IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX = 65_536
_SEALED_MAX = 1_048_576
_PRIVATE_DIR = 0o700
_PRIVATE_FILE = 0o600
_SEALED_FILE = 0o400
_EXECUTABLE_FILE = 0o755
_STATE_SCHEMA = "asklegal.hk-v1-primary-vault-root-rotation-state"
_STATE_PHASES = {
    "STAGED",
    "STOPPED",
    "SWITCHED",
    "SERVICES_ACTIVE",
    "AUTHENTICATION_PROVED",
    "PREDECESSOR_RESTORED",
}
_RUNTIME_ARTIFACTS = (
    (
        "vault-primary-launcher",
        Path("infrastructure/poc/units/launch/vault-primary.sh"),
        Path("/etc/asklegal/launch/vault-primary.sh"),
    ),
    (
        "primary-root-network-helper",
        Path("infrastructure/poc/libexec/asklegal-vault-primary-root-rotation-network"),
        Path("/usr/local/libexec/asklegal-vault-primary-root-rotation-network"),
    ),
)


class PrimaryVaultRootRotationError(RuntimeError):
    """One sanitized root-rotation failure."""


def _fail(code: str) -> Never:
    raise PrimaryVaultRootRotationError(code)


class RootRotationState(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    ROLLED_BACK = "ROLLED_BACK"
    BLOCKED = "BLOCKED"


class RootRotationBlocker(StrEnum):
    CANDIDATE_SEAL_FAILED = "CANDIDATE_SEAL_FAILED"
    DEPENDENT_UNIT_FAILURE = "DEPENDENT_UNIT_FAILURE"
    DOCKER_CONFIGURATION_EXPOSED = "DOCKER_CONFIGURATION_EXPOSED"
    NEW_ROOT_REJECTED = "NEW_ROOT_REJECTED"
    OLD_ROOT_STILL_ACCEPTED = "OLD_ROOT_STILL_ACCEPTED"
    RECEIPT_MISMATCH = "RECEIPT_MISMATCH"
    ROLLBACK_NOT_PROVED = "ROLLBACK_NOT_PROVED"
    SEALED_SWITCH_FAILED = "SEALED_SWITCH_FAILED"
    VAULT_DATA_DRIFT = "VAULT_DATA_DRIFT"


@dataclass(frozen=True, slots=True)
class PrimaryVaultRootRotationPlan:
    rotation_id: str
    staging_receipt_fingerprint: str
    predecessor_binding_ref: str
    candidate_binding_ref: str
    predecessor_sealed_state_ref: str
    vault_data_state_ref: str
    predecessor_runtime_configuration_ref: str
    candidate_runtime_configuration_ref: str
    control_plane_candidate_image_id: str
    application_build_results_fingerprint: str
    credential_names: tuple[str, ...]
    stopped_units: tuple[str, ...]
    plan_fingerprint: str

    def __post_init__(self) -> None:
        if (
            _ROTATION.fullmatch(self.rotation_id) is None
            or _FINGERPRINT.fullmatch(self.staging_receipt_fingerprint) is None
            or _BINDING.fullmatch(self.predecessor_binding_ref) is None
            or _BINDING.fullmatch(self.candidate_binding_ref) is None
            or self.predecessor_binding_ref == self.candidate_binding_ref
            or _SEALED.fullmatch(self.predecessor_sealed_state_ref) is None
            or _DATA.fullmatch(self.vault_data_state_ref) is None
            or _RUNTIME.fullmatch(self.predecessor_runtime_configuration_ref) is None
            or _RUNTIME.fullmatch(self.candidate_runtime_configuration_ref) is None
            or self.predecessor_runtime_configuration_ref
            == self.candidate_runtime_configuration_ref
            or _IMAGE.fullmatch(self.control_plane_candidate_image_id) is None
            or _FINGERPRINT.fullmatch(self.application_build_results_fingerprint) is None
            or self.credential_names != _ROOT_NAMES
            or self.stopped_units != _STOP_UNITS
            or self.plan_fingerprint != _fingerprint(_plan_body(self))
        ):
            _fail("PRIMARY_ROOT_ROTATION_PLAN_INVALID")


@dataclass(frozen=True, slots=True, repr=False)
class _RootPairs:
    predecessor: S3AccessCredential
    candidate: S3AccessCredential


@dataclass(frozen=True, slots=True, repr=False)
class PreparedPrimaryVaultRootRotation:
    plan: PrimaryVaultRootRotationPlan
    pairs: _RootPairs
    source_root: Path
    candidate_root: Path
    vault_data_root: Path
    runtime_sources: tuple[Path, ...]
    runtime_destinations: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class RootHostReceipt:
    plan_fingerprint: str
    binding_ref: str
    units_healthy: bool
    vault_data_state_ref: str
    docker_configuration_value_free: bool


@dataclass(frozen=True, slots=True)
class RootProbeReceipt:
    plan_fingerprint: str
    binding_ref: str
    accepted: bool


@dataclass(frozen=True, slots=True)
class RootRollbackReceipt:
    plan_fingerprint: str
    predecessor_active: bool
    candidate_sealed_absent: bool


@dataclass(frozen=True, slots=True)
class PrimaryVaultRootRotationReport:
    plan_fingerprint: str
    staging_receipt_fingerprint: str
    candidate_binding_ref: str
    rotation_id: str
    state: RootRotationState
    complete: bool
    new_root_accepted: bool
    old_root_rejected: bool
    vault_data_preserved: bool
    docker_configuration_value_free: bool
    predecessor_restored: bool
    candidate_sealed_absent: bool
    staging_retained_for_application_rotation: bool
    blocker_codes: tuple[RootRotationBlocker, ...]

    def __post_init__(self) -> None:
        if (
            _FINGERPRINT.fullmatch(self.plan_fingerprint) is None
            or _FINGERPRINT.fullmatch(self.staging_receipt_fingerprint) is None
            or _BINDING.fullmatch(self.candidate_binding_ref) is None
            or _ROTATION.fullmatch(self.rotation_id) is None
            or self.complete != (self.state is RootRotationState.SUCCEEDED)
            or self.blocker_codes
            != tuple(sorted(set(self.blocker_codes), key=lambda item: item.value))
            or not self.staging_retained_for_application_rotation
        ):
            _fail("PRIMARY_ROOT_ROTATION_REPORT_INVALID")
        if self.state is RootRotationState.SUCCEEDED and (
            self.blocker_codes
            or not self.new_root_accepted
            or not self.old_root_rejected
            or not self.vault_data_preserved
            or not self.docker_configuration_value_free
            or self.predecessor_restored
            or self.candidate_sealed_absent
        ):
            _fail("PRIMARY_ROOT_ROTATION_REPORT_INVALID")
        if self.state is RootRotationState.ROLLED_BACK and (
            not self.blocker_codes
            or self.new_root_accepted
            or self.old_root_rejected
            or not self.vault_data_preserved
            or not self.docker_configuration_value_free
            or not self.predecessor_restored
            or not self.candidate_sealed_absent
        ):
            _fail("PRIMARY_ROOT_ROTATION_REPORT_INVALID")
        if self.state is RootRotationState.BLOCKED and not self.blocker_codes:
            _fail("PRIMARY_ROOT_ROTATION_REPORT_INVALID")


class RootHostPort(Protocol):
    def stage_candidate(self, plan: PrimaryVaultRootRotationPlan, root: Path) -> bool: ...
    def stop_and_check(self, plan: PrimaryVaultRootRotationPlan) -> bool: ...
    def switch_candidate(self, plan: PrimaryVaultRootRotationPlan) -> bool: ...
    def restart_and_check(
        self, plan: PrimaryVaultRootRotationPlan, *, binding_ref: str
    ) -> RootHostReceipt: ...
    def record_acceptance(self, plan: PrimaryVaultRootRotationPlan) -> bool: ...
    def restore_predecessor(self, plan: PrimaryVaultRootRotationPlan) -> RootRollbackReceipt: ...


class RootProbePort(Protocol):
    def check(
        self, plan: PrimaryVaultRootRotationPlan, *, binding_ref: str
    ) -> RootProbeReceipt: ...


def _fingerprint(body: dict[str, JsonValue]) -> str:
    return "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()


def _plan_body(plan: PrimaryVaultRootRotationPlan) -> dict[str, JsonValue]:
    return {
        "application_build_results_fingerprint": plan.application_build_results_fingerprint,
        "candidate_binding_ref": plan.candidate_binding_ref,
        "candidate_runtime_configuration_ref": plan.candidate_runtime_configuration_ref,
        "control_plane_candidate_image_id": plan.control_plane_candidate_image_id,
        "credential_names": list(plan.credential_names),
        "predecessor_binding_ref": plan.predecessor_binding_ref,
        "predecessor_runtime_configuration_ref": plan.predecessor_runtime_configuration_ref,
        "predecessor_sealed_state_ref": plan.predecessor_sealed_state_ref,
        "rotation_id": plan.rotation_id,
        "staging_receipt_fingerprint": plan.staging_receipt_fingerprint,
        "stopped_units": list(plan.stopped_units),
        "vault_data_state_ref": plan.vault_data_state_ref,
    }


def root_rotation_plan_bytes(plan: PrimaryVaultRootRotationPlan) -> bytes:
    return canonicalize(
        checked_json_value(
            {
                **_plan_body(plan),
                "plan_fingerprint": plan.plan_fingerprint,
                "schema_id": _PLAN_SCHEMA,
                "schema_version": _VERSION,
            }
        )
    )


def parse_root_rotation_plan_bytes(raw: bytes) -> PrimaryVaultRootRotationPlan:
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX)
    except (TypeError, ValueError) as error:
        raise PrimaryVaultRootRotationError("PRIMARY_ROOT_ROTATION_PLAN_INVALID") from error
    if type(value) is not dict:
        _fail("PRIMARY_ROOT_ROTATION_PLAN_INVALID")
    document = cast("dict[str, JsonValue]", value)
    text_fields = (
        "rotation_id",
        "staging_receipt_fingerprint",
        "predecessor_binding_ref",
        "candidate_binding_ref",
        "predecessor_sealed_state_ref",
        "vault_data_state_ref",
        "predecessor_runtime_configuration_ref",
        "candidate_runtime_configuration_ref",
        "control_plane_candidate_image_id",
        "application_build_results_fingerprint",
        "plan_fingerprint",
    )
    if any(type(document.get(field)) is not str for field in text_fields):
        _fail("PRIMARY_ROOT_ROTATION_PLAN_INVALID")
    plan = PrimaryVaultRootRotationPlan(
        rotation_id=cast("str", document["rotation_id"]),
        staging_receipt_fingerprint=cast("str", document["staging_receipt_fingerprint"]),
        predecessor_binding_ref=cast("str", document["predecessor_binding_ref"]),
        candidate_binding_ref=cast("str", document["candidate_binding_ref"]),
        predecessor_sealed_state_ref=cast("str", document["predecessor_sealed_state_ref"]),
        vault_data_state_ref=cast("str", document["vault_data_state_ref"]),
        predecessor_runtime_configuration_ref=cast(
            "str", document["predecessor_runtime_configuration_ref"]
        ),
        candidate_runtime_configuration_ref=cast(
            "str", document["candidate_runtime_configuration_ref"]
        ),
        control_plane_candidate_image_id=cast("str", document["control_plane_candidate_image_id"]),
        application_build_results_fingerprint=cast(
            "str", document["application_build_results_fingerprint"]
        ),
        credential_names=_ROOT_NAMES,
        stopped_units=_STOP_UNITS,
        plan_fingerprint=cast("str", document["plan_fingerprint"]),
    )
    if root_rotation_plan_bytes(plan) != raw:
        _fail("PRIMARY_ROOT_ROTATION_PLAN_INVALID")
    return plan


def _pair(snapshot: dict[str, bytes]) -> S3AccessCredential:
    try:
        return S3AccessCredential.from_bytes(
            canonicalize(
                checked_json_value(
                    {
                        "access_key_id": snapshot[_ROOT_NAMES[0]].decode("utf-8", errors="strict"),
                        "secret_access_key": snapshot[_ROOT_NAMES[1]].decode(
                            "utf-8", errors="strict"
                        ),
                    }
                )
            )
        )
    except (UnicodeDecodeError, S3VaultError, ValueError) as error:
        raise PrimaryVaultRootRotationError("PRIMARY_ROOT_CREDENTIAL_INVALID") from error


def _sealed_state(root: Path) -> str:
    rows: list[JsonValue] = []
    for name in _ROOT_NAMES:
        path = root / f"{name}.cred"
        if path.is_symlink() or not path.is_file():
            _fail("PRIMARY_ROOT_SEALED_STATE_INVALID")
        facts = path.stat()
        raw = path.read_bytes()
        if stat.S_IMODE(facts.st_mode) != _SEALED_FILE or not 1 <= len(raw) <= _SEALED_MAX:
            _fail("PRIMARY_ROOT_SEALED_STATE_INVALID")
        rows.append({"name": name, "sha256": sha256(raw).hexdigest(), "size": len(raw)})
    return "sealed_" + sha256(canonicalize(checked_json_value(rows))).hexdigest()


def vault_data_state(root: Path) -> str:
    """Hash every regular persisted-vault byte and reject links/special files."""
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        _fail("PRIMARY_VAULT_DATA_INVALID")
    rows: list[JsonValue] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            _fail("PRIMARY_VAULT_DATA_INVALID")
        facts = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(facts.st_mode):
            rows.append({"kind": "directory", "path": relative})
        elif stat.S_ISREG(facts.st_mode):
            digest = sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1_048_576):
                    digest.update(chunk)
            after = path.stat(follow_symlinks=False)
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                facts.st_dev,
                facts.st_ino,
                facts.st_size,
                facts.st_mtime_ns,
            ):
                _fail("PRIMARY_VAULT_DATA_DRIFT")
            rows.append(
                {
                    "kind": "file",
                    "path": relative,
                    "sha256": digest.hexdigest(),
                    "size": facts.st_size,
                }
            )
        else:
            _fail("PRIMARY_VAULT_DATA_INVALID")
    return "vaultdata_" + sha256(canonicalize(checked_json_value(rows))).hexdigest()


def _runtime_configuration_ref(paths: tuple[Path, ...]) -> str:
    if len(paths) != len(_RUNTIME_ARTIFACTS):
        _fail("PRIMARY_ROOT_RUNTIME_CONFIGURATION_INVALID")
    rows: list[JsonValue] = []
    for (label, _relative, destination), path in zip(_RUNTIME_ARTIFACTS, paths, strict=True):
        if path.is_symlink():
            _fail("PRIMARY_ROOT_RUNTIME_CONFIGURATION_INVALID")
        if not path.exists():
            rows.append({"destination": str(destination), "label": label, "present": False})
            continue
        if not path.is_file():
            _fail("PRIMARY_ROOT_RUNTIME_CONFIGURATION_INVALID")
        raw = path.read_bytes()
        if not raw or len(raw) > _SEALED_MAX:
            _fail("PRIMARY_ROOT_RUNTIME_CONFIGURATION_INVALID")
        rows.append(
            {
                "destination": str(destination),
                "label": label,
                "mode": stat.S_IMODE(path.stat().st_mode),
                "present": True,
                "sha256": sha256(raw).hexdigest(),
                "size": len(raw),
            }
        )
    return "runtimecfg_" + sha256(canonicalize(checked_json_value(rows))).hexdigest()


def _safe_future_directory(path: Path) -> bool:
    if not path.is_absolute() or path == Path(path.anchor) or path.is_symlink():
        return False
    current = path
    while current != Path(current.anchor):
        if current.is_symlink():
            return False
        if current.exists() and not current.is_dir():
            return False
        current = current.parent
    return True


def prepare_primary_vault_root_rotation(
    receipt_path: Path,
    *,
    sealed_root: Path,
    vault_data_root: Path,
    control_plane_candidate_image_id: str,
    application_build_results_fingerprint: str,
    retained_plan: PrimaryVaultRootRotationPlan | None = None,
    workspace_root: Path | None = None,
    runtime_destinations: tuple[Path, ...] | None = None,
) -> PreparedPrimaryVaultRootRotation:
    binding = staging_receipt_binding(receipt_path)
    predecessor = credential_snapshot(binding.source_root)
    candidate = credential_snapshot(binding.candidate_root)
    if (
        snapshot_binding(predecessor) != binding.predecessor_binding_ref
        or snapshot_binding(candidate) != binding.candidate_binding_ref
        or any(candidate[name] == predecessor[name] for name in _ROOT_NAMES)
    ):
        _fail("PRIMARY_ROOT_STAGING_DRIFT")
    predecessor_pair = _pair(predecessor)
    candidate_pair = _pair(candidate)
    if set(predecessor_pair.reveal_for_client()) & set(candidate_pair.reveal_for_client()):
        _fail("PRIMARY_ROOT_STAGING_DRIFT")
    predecessor_sealed_state_ref = (
        retained_plan.predecessor_sealed_state_ref
        if retained_plan is not None
        else _sealed_state(sealed_root)
    )
    repository = Path.cwd().resolve() if workspace_root is None else workspace_root
    destinations = (
        tuple(item[2] for item in _RUNTIME_ARTIFACTS)
        if runtime_destinations is None
        else runtime_destinations
    )
    sources = tuple(repository / item[1] for item in _RUNTIME_ARTIFACTS)
    if (
        not repository.is_absolute()
        or repository.is_symlink()
        or not repository.is_dir()
        or any(path.is_symlink() or not path.is_file() for path in sources)
        or any(stat.S_IMODE(path.stat().st_mode) != _EXECUTABLE_FILE for path in sources)
    ):
        _fail("PRIMARY_ROOT_RUNTIME_CONFIGURATION_INVALID")
    candidate_runtime_ref = _runtime_configuration_ref(sources)
    predecessor_runtime_ref = (
        retained_plan.predecessor_runtime_configuration_ref
        if retained_plan is not None
        else _runtime_configuration_ref(destinations)
    )
    provisional_body: dict[str, JsonValue] = {
        "application_build_results_fingerprint": application_build_results_fingerprint,
        "candidate_binding_ref": binding.candidate_binding_ref,
        "candidate_runtime_configuration_ref": candidate_runtime_ref,
        "control_plane_candidate_image_id": control_plane_candidate_image_id,
        "credential_names": list(_ROOT_NAMES),
        "predecessor_binding_ref": binding.predecessor_binding_ref,
        "predecessor_runtime_configuration_ref": predecessor_runtime_ref,
        "predecessor_sealed_state_ref": predecessor_sealed_state_ref,
        "rotation_id": binding.rotation_id,
        "staging_receipt_fingerprint": binding.fingerprint,
        "stopped_units": list(_STOP_UNITS),
        "vault_data_state_ref": vault_data_state(vault_data_root),
    }
    plan = PrimaryVaultRootRotationPlan(
        rotation_id=binding.rotation_id,
        staging_receipt_fingerprint=binding.fingerprint,
        predecessor_binding_ref=binding.predecessor_binding_ref,
        candidate_binding_ref=binding.candidate_binding_ref,
        predecessor_sealed_state_ref=cast("str", provisional_body["predecessor_sealed_state_ref"]),
        vault_data_state_ref=cast("str", provisional_body["vault_data_state_ref"]),
        predecessor_runtime_configuration_ref=predecessor_runtime_ref,
        candidate_runtime_configuration_ref=candidate_runtime_ref,
        control_plane_candidate_image_id=control_plane_candidate_image_id,
        application_build_results_fingerprint=application_build_results_fingerprint,
        credential_names=_ROOT_NAMES,
        stopped_units=_STOP_UNITS,
        plan_fingerprint=_fingerprint(provisional_body),
    )
    if retained_plan is not None and plan != retained_plan:
        _fail("PRIMARY_ROOT_ROTATION_PLAN_DRIFT")
    return PreparedPrimaryVaultRootRotation(
        plan,
        _RootPairs(predecessor_pair, candidate_pair),
        binding.source_root,
        binding.candidate_root,
        vault_data_root,
        sources,
        destinations,
    )


def _report(
    plan: PrimaryVaultRootRotationPlan,
    *,
    state: RootRotationState,
    blockers: tuple[RootRotationBlocker, ...],
    new: bool = False,
    old_rejected: bool = False,
    data: bool = False,
    config: bool = False,
    restored: bool = False,
    candidate_absent: bool = False,
) -> PrimaryVaultRootRotationReport:
    return PrimaryVaultRootRotationReport(
        plan.plan_fingerprint,
        plan.staging_receipt_fingerprint,
        plan.candidate_binding_ref,
        plan.rotation_id,
        state,
        state is RootRotationState.SUCCEEDED,
        new,
        old_rejected,
        data,
        config,
        restored,
        candidate_absent,
        True,
        tuple(sorted(set(blockers), key=lambda item: item.value)),
    )


def _rollback(
    prepared: PreparedPrimaryVaultRootRotation,
    host: RootHostPort,
    probe: RootProbePort,
    initial: RootRotationBlocker,
) -> PrimaryVaultRootRotationReport:
    plan = prepared.plan
    try:
        stopped = host.stop_and_check(plan)
        restored = host.restore_predecessor(plan)
        restarted = host.restart_and_check(plan, binding_ref=plan.predecessor_binding_ref)
        old = probe.check(plan, binding_ref=plan.predecessor_binding_ref)
        new = probe.check(plan, binding_ref=plan.candidate_binding_ref)
        proved = (
            stopped
            and restored.plan_fingerprint == plan.plan_fingerprint
            and restored.predecessor_active
            and restored.candidate_sealed_absent
            and restarted.binding_ref == plan.predecessor_binding_ref
            and restarted.units_healthy
            and restarted.vault_data_state_ref == plan.vault_data_state_ref
            and restarted.docker_configuration_value_free
            and old.accepted
            and not new.accepted
        )
    except Exception:
        proved = False
    return _report(
        plan,
        state=RootRotationState.ROLLED_BACK if proved else RootRotationState.BLOCKED,
        blockers=(initial,) if proved else (initial, RootRotationBlocker.ROLLBACK_NOT_PROVED),
        data=proved,
        config=proved,
        restored=proved,
        candidate_absent=proved,
    )


def execute_primary_vault_root_rotation(
    prepared: PreparedPrimaryVaultRootRotation,
    *,
    host: RootHostPort,
    probe: RootProbePort,
) -> PrimaryVaultRootRotationReport:
    plan = prepared.plan
    steps = (
        (
            lambda: host.stage_candidate(plan, prepared.candidate_root),
            RootRotationBlocker.CANDIDATE_SEAL_FAILED,
        ),
        (lambda: host.stop_and_check(plan), RootRotationBlocker.DEPENDENT_UNIT_FAILURE),
        (lambda: host.switch_candidate(plan), RootRotationBlocker.SEALED_SWITCH_FAILED),
    )
    for action, blocker in steps:
        try:
            if not action():
                return _rollback(prepared, host, probe, blocker)
        except Exception:
            return _rollback(prepared, host, probe, blocker)
    try:
        restarted = host.restart_and_check(plan, binding_ref=plan.candidate_binding_ref)
    except Exception:
        return _rollback(prepared, host, probe, RootRotationBlocker.DEPENDENT_UNIT_FAILURE)
    if not restarted.units_healthy:
        return _rollback(prepared, host, probe, RootRotationBlocker.DEPENDENT_UNIT_FAILURE)
    if restarted.vault_data_state_ref != plan.vault_data_state_ref:
        return _rollback(prepared, host, probe, RootRotationBlocker.VAULT_DATA_DRIFT)
    if not restarted.docker_configuration_value_free:
        return _rollback(prepared, host, probe, RootRotationBlocker.DOCKER_CONFIGURATION_EXPOSED)
    try:
        candidate = probe.check(plan, binding_ref=plan.candidate_binding_ref)
        predecessor = probe.check(plan, binding_ref=plan.predecessor_binding_ref)
    except Exception:
        return _rollback(prepared, host, probe, RootRotationBlocker.NEW_ROOT_REJECTED)
    if not candidate.accepted:
        return _rollback(prepared, host, probe, RootRotationBlocker.NEW_ROOT_REJECTED)
    if predecessor.accepted:
        return _rollback(prepared, host, probe, RootRotationBlocker.OLD_ROOT_STILL_ACCEPTED)
    try:
        if not host.record_acceptance(plan):
            return _rollback(prepared, host, probe, RootRotationBlocker.RECEIPT_MISMATCH)
    except Exception:
        return _rollback(prepared, host, probe, RootRotationBlocker.RECEIPT_MISMATCH)
    return _report(
        plan,
        state=RootRotationState.SUCCEEDED,
        blockers=(),
        new=True,
        old_rejected=True,
        data=True,
        config=True,
    )


def root_rotation_report_bytes(report: PrimaryVaultRootRotationReport) -> bytes:
    body: dict[str, JsonValue] = {
        "blocker_codes": [item.value for item in report.blocker_codes],
        "candidate_binding_ref": report.candidate_binding_ref,
        "candidate_sealed_absent": report.candidate_sealed_absent,
        "complete": report.complete,
        "docker_configuration_value_free": report.docker_configuration_value_free,
        "new_root_accepted": report.new_root_accepted,
        "old_root_rejected": report.old_root_rejected,
        "plan_fingerprint": report.plan_fingerprint,
        "predecessor_restored": report.predecessor_restored,
        "rotation_id": report.rotation_id,
        "schema_id": _REPORT_SCHEMA,
        "schema_version": _VERSION,
        "staging_receipt_fingerprint": report.staging_receipt_fingerprint,
        "staging_retained_for_application_rotation": report.staging_retained_for_application_rotation,
        "state": report.state.value,
        "vault_data_preserved": report.vault_data_preserved,
    }
    return canonicalize(checked_json_value({**body, "fingerprint": _fingerprint(body)}))


def parse_succeeded_root_rotation_report_bytes(raw: bytes) -> PrimaryVaultRootRotationReport:
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX)
    except (TypeError, ValueError) as error:
        raise PrimaryVaultRootRotationError("PRIMARY_ROOT_ROTATION_REPORT_INVALID") from error
    if type(value) is not dict or canonicalize(checked_json_value(value)) != raw:
        _fail("PRIMARY_ROOT_ROTATION_REPORT_INVALID")
    document = cast("dict[str, JsonValue]", value)
    if (
        set(document)
        != {
            "blocker_codes",
            "candidate_binding_ref",
            "candidate_sealed_absent",
            "complete",
            "docker_configuration_value_free",
            "fingerprint",
            "new_root_accepted",
            "old_root_rejected",
            "plan_fingerprint",
            "predecessor_restored",
            "rotation_id",
            "schema_id",
            "schema_version",
            "staging_receipt_fingerprint",
            "staging_retained_for_application_rotation",
            "state",
            "vault_data_preserved",
        }
        or document.get("schema_id") != _REPORT_SCHEMA
        or document.get("schema_version") != _VERSION
    ):
        _fail("PRIMARY_ROOT_ROTATION_REPORT_INVALID")
    boolean_fields = (
        "candidate_sealed_absent",
        "complete",
        "docker_configuration_value_free",
        "new_root_accepted",
        "old_root_rejected",
        "predecessor_restored",
        "staging_retained_for_application_rotation",
        "vault_data_preserved",
    )
    if any(type(document.get(field)) is not bool for field in boolean_fields):
        _fail("PRIMARY_ROOT_ROTATION_REPORT_INVALID")
    if type(document.get("blocker_codes")) is not list or any(
        type(item) is not str for item in cast("list[JsonValue]", document["blocker_codes"])
    ):
        _fail("PRIMARY_ROOT_ROTATION_REPORT_INVALID")
    body = dict(document)
    fingerprint = body.pop("fingerprint", None)
    if type(fingerprint) is not str or fingerprint != _fingerprint(body):
        _fail("PRIMARY_ROOT_ROTATION_REPORT_INVALID")
    try:
        blockers = tuple(
            RootRotationBlocker(item) for item in cast("list[str]", document["blocker_codes"])
        )
        report = PrimaryVaultRootRotationReport(
            plan_fingerprint=cast("str", document["plan_fingerprint"]),
            staging_receipt_fingerprint=cast("str", document["staging_receipt_fingerprint"]),
            candidate_binding_ref=cast("str", document["candidate_binding_ref"]),
            rotation_id=cast("str", document["rotation_id"]),
            state=RootRotationState(cast("str", document["state"])),
            complete=document["complete"] is True,
            new_root_accepted=document["new_root_accepted"] is True,
            old_root_rejected=document["old_root_rejected"] is True,
            vault_data_preserved=document["vault_data_preserved"] is True,
            docker_configuration_value_free=document["docker_configuration_value_free"] is True,
            predecessor_restored=document["predecessor_restored"] is True,
            candidate_sealed_absent=document["candidate_sealed_absent"] is True,
            staging_retained_for_application_rotation=(
                document["staging_retained_for_application_rotation"] is True
            ),
            blocker_codes=blockers,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PrimaryVaultRootRotationError("PRIMARY_ROOT_ROTATION_REPORT_INVALID") from error
    if report.state is not RootRotationState.SUCCEEDED:
        _fail("PRIMARY_ROOT_ROTATION_NOT_SUCCEEDED")
    return report


def _read_owned_evidence(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        _fail("PRIMARY_ROOT_ROTATION_EVIDENCE_INVALID")
    facts = path.stat()
    if stat.S_IMODE(facts.st_mode) != _PRIVATE_FILE or facts.st_uid != os.geteuid():
        _fail("PRIMARY_ROOT_ROTATION_EVIDENCE_INVALID")
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX:
        _fail("PRIMARY_ROOT_ROTATION_EVIDENCE_INVALID")
    return raw


def validate_root_report_for_application_rotation(
    report_path: Path,
    root_plan_path: Path,
    staging_receipt: Path,
    *,
    control_plane_candidate_image_id: str,
    application_build_results_fingerprint: str,
) -> str:
    raw = _read_owned_evidence(report_path)
    report = parse_succeeded_root_rotation_report_bytes(raw)
    plan = parse_root_rotation_plan_bytes(_read_owned_evidence(root_plan_path))
    binding = staging_receipt_binding(staging_receipt)
    if (
        report.plan_fingerprint != plan.plan_fingerprint
        or report.staging_receipt_fingerprint != binding.fingerprint
        or report.candidate_binding_ref != binding.candidate_binding_ref
        or report.rotation_id != binding.rotation_id
        or plan.staging_receipt_fingerprint != binding.fingerprint
        or plan.predecessor_binding_ref != binding.predecessor_binding_ref
        or plan.candidate_binding_ref != binding.candidate_binding_ref
        or plan.rotation_id != binding.rotation_id
        or plan.control_plane_candidate_image_id != control_plane_candidate_image_id
        or plan.application_build_results_fingerprint != application_build_results_fingerprint
    ):
        _fail("PRIMARY_ROOT_ROTATION_REPORT_DRIFT")
    return "sha256:" + sha256(raw).hexdigest()


def _retain(path: Path, raw: bytes) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
        _fail("PRIMARY_ROOT_ROTATION_OUTPUT_INVALID")
    if path.exists():
        if not path.is_file() or path.read_bytes() != raw:
            _fail("PRIMARY_ROOT_ROTATION_OUTPUT_DRIFT")
        return
    temporary = path.parent / f".{path.name}.{token_urlsafe(18)}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _PRIVATE_FILE)
    try:
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.rename(path)


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            _fail("PRIMARY_ROOT_ROTATION_WRITE_FAILED")
        view = view[written:]


def retain_root_rotation_plan(path: Path, plan: PrimaryVaultRootRotationPlan) -> None:
    _retain(path, root_rotation_plan_bytes(plan))


@contextmanager
def exclusive_root_rotation_execution(state_root: Path) -> Generator[None]:
    """Hold one non-blocking process lock for the complete effectful transaction."""
    if not state_root.is_absolute() or state_root.is_symlink() or not state_root.is_dir():
        _fail("PRIMARY_ROOT_ROTATION_PATH_INVALID")
    lock_path = state_root / "primary-root-rotation.lock"
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
        _PRIVATE_FILE,
    )
    try:
        facts = os.fstat(descriptor)
        if (
            not stat.S_ISREG(facts.st_mode)
            or stat.S_IMODE(facts.st_mode) != _PRIVATE_FILE
            or facts.st_uid != os.geteuid()
        ):
            _fail("PRIMARY_ROOT_ROTATION_LOCK_INVALID")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PrimaryVaultRootRotationError("PRIMARY_ROOT_ROTATION_ALREADY_RUNNING") from error
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


class RootNetworkAdapter:
    def __init__(
        self,
        runner: ExactCommandRunner,
        prepared: PreparedPrimaryVaultRootRotation,
        plan_path: Path,
        authorized_plan_fingerprint: str,
        *,
        sealed_root: Path,
        helper_path: Path,
    ) -> None:
        if (
            authorized_plan_fingerprint != prepared.plan.plan_fingerprint
            or parse_root_rotation_plan_bytes(plan_path.read_bytes()) != prepared.plan
        ):
            _fail("PRIMARY_ROOT_ROTATION_AUTHORITY_REQUIRED")
        self._runner = runner
        self._prepared = prepared
        self._plan_path = plan_path
        self._authorized = authorized_plan_fingerprint
        self._sealed_root = sealed_root
        self._helper_path = helper_path

    def check(self, plan: PrimaryVaultRootRotationPlan, *, binding_ref: str) -> RootProbeReceipt:
        if plan != self._prepared.plan:
            _fail("PRIMARY_ROOT_ROTATION_PLAN_DRIFT")
        if (
            self._helper_path.is_symlink()
            or not self._helper_path.is_file()
            or stat.S_IMODE(self._helper_path.stat().st_mode) != _EXECUTABLE_FILE
            or self._helper_path.read_bytes() != self._prepared.runtime_sources[1].read_bytes()
            or _runtime_configuration_ref(self._prepared.runtime_sources)
            != plan.candidate_runtime_configuration_ref
        ):
            _fail("PRIMARY_ROOT_ROTATION_NETWORK_FAILED")
        target = (
            "candidate"
            if binding_ref == plan.candidate_binding_ref
            else "predecessor"
            if binding_ref == plan.predecessor_binding_ref
            else ""
        )
        if not target:
            _fail("PRIMARY_ROOT_ROTATION_PLAN_DRIFT")
        expectation = (
            "accepted"
            if (
                (
                    target == "candidate"
                    and _sealed_state(self._sealed_root) != plan.predecessor_sealed_state_ref
                )
                or (
                    target == "predecessor"
                    and _sealed_state(self._sealed_root) == plan.predecessor_sealed_state_ref
                )
            )
            else "rejected"
        )
        raw = self._runner.read(
            (
                str(self._helper_path),
                "--target",
                target,
                "--expect",
                expectation,
                "--plan",
                str(self._plan_path),
                "--authorized-plan-fingerprint",
                self._authorized,
                "--control-plane-image-id",
                plan.control_plane_candidate_image_id,
                "--predecessor-directory",
                str(self._prepared.source_root),
                "--candidate-directory",
                str(self._prepared.candidate_root),
            ),
            max_bytes=_MAX,
        )
        if raw is None:
            _fail("PRIMARY_ROOT_ROTATION_NETWORK_FAILED")
        raw = raw.removesuffix(b"\n")
        value = parse_json_bytes(raw, max_bytes=_MAX)
        if type(value) is not dict or canonicalize(checked_json_value(value)) != raw:
            _fail("PRIMARY_ROOT_ROTATION_NETWORK_RECEIPT_INVALID")
        document = cast("dict[str, JsonValue]", value)
        body = dict(document)
        fingerprint = body.pop("fingerprint", None)
        accepted = document.get("accepted")
        if (
            set(document)
            != {
                "accepted",
                "application_build_results_fingerprint",
                "candidate_binding_ref",
                "control_plane_candidate_image_id",
                "fingerprint",
                "plan_fingerprint",
                "predecessor_binding_ref",
                "schema_id",
                "schema_version",
                "target",
            }
            or document.get("application_build_results_fingerprint")
            != plan.application_build_results_fingerprint
            or document.get("control_plane_candidate_image_id")
            != plan.control_plane_candidate_image_id
            or document.get("schema_id") != _NETWORK_SCHEMA
            or document.get("schema_version") != _VERSION
            or document.get("plan_fingerprint") != plan.plan_fingerprint
            or document.get("candidate_binding_ref") != plan.candidate_binding_ref
            or document.get("predecessor_binding_ref") != plan.predecessor_binding_ref
            or document.get("target") != target
            or type(accepted) is not bool
            or fingerprint != _fingerprint(body)
        ):
            _fail("PRIMARY_ROOT_ROTATION_NETWORK_RECEIPT_INVALID")
        return RootProbeReceipt(plan.plan_fingerprint, binding_ref, accepted)


class TransactionalPrimaryRootHost:
    """Root-only two-file sealed switch with exact service/config/data readback."""

    def __init__(
        self,
        sealed_root: Path,
        state_root: Path,
        runtime_credential_root: Path,
        prepared: PreparedPrimaryVaultRootRotation,
        *,
        runner: ExactCommandRunner,
        authorized_plan_fingerprint: str,
    ) -> None:
        if os.geteuid() != 0 or authorized_plan_fingerprint != prepared.plan.plan_fingerprint:
            _fail("PRIMARY_ROOT_ROTATION_AUTHORITY_REQUIRED")
        self._sealed_root = sealed_root
        self._state_root = state_root
        self._runtime_root = runtime_credential_root
        self._prepared = prepared
        self._plan = prepared.plan
        self._runner = runner
        self._work = state_root / f"{self._plan.rotation_id}-primary-root"
        self._predecessor = self._work / "predecessor"
        self._candidate = self._work / "candidate"
        self._runtime_predecessor = self._work / "runtime-predecessor"
        self._runtime_candidate = self._work / "runtime-candidate"
        self._journal = self._work / "state.json"
        for root in (sealed_root, state_root):
            if not root.is_absolute() or root.is_symlink() or not root.is_dir():
                _fail("PRIMARY_ROOT_ROTATION_PATH_INVALID")
        if not _safe_future_directory(runtime_credential_root):
            _fail("PRIMARY_ROOT_ROTATION_PATH_INVALID")
        self._work.mkdir(mode=_PRIVATE_DIR, exist_ok=True)
        self._predecessor.mkdir(mode=_PRIVATE_DIR, exist_ok=True)
        self._candidate.mkdir(mode=_PRIVATE_DIR, exist_ok=True)
        self._runtime_predecessor.mkdir(mode=_PRIVATE_DIR, exist_ok=True)
        self._runtime_candidate.mkdir(mode=_PRIVATE_DIR, exist_ok=True)
        if self._journal.exists() and self._journal_plan() != self._plan.plan_fingerprint:
            _fail("PRIMARY_ROOT_ROTATION_STATE_DRIFT")
        if (
            not self._journal.exists()
            and _sealed_state(sealed_root) != self._plan.predecessor_sealed_state_ref
        ):
            _fail("PRIMARY_ROOT_SEALED_STATE_DRIFT")
        if self._journal.exists() and not self._active_is_bound_state():
            _fail("PRIMARY_ROOT_SEALED_STATE_DRIFT")
        if self._journal.exists() and not self._active_runtime_is_bound_mix():
            _fail("PRIMARY_ROOT_RUNTIME_CONFIGURATION_DRIFT")
        if self._journal.exists() and (
            _sealed_state(self._predecessor) != self._plan.predecessor_sealed_state_ref
            or _runtime_configuration_ref(self._runtime_work_paths(self._runtime_predecessor))
            != self._plan.predecessor_runtime_configuration_ref
            or _runtime_configuration_ref(self._runtime_work_paths(self._runtime_candidate))
            != self._plan.candidate_runtime_configuration_ref
        ):
            _fail("PRIMARY_ROOT_ROTATION_STATE_DRIFT")

    @staticmethod
    def _same_file_bytes(left: Path, right: Path) -> bool:
        if left.is_symlink() or right.is_symlink() or not left.is_file() or not right.is_file():
            return False
        return left.read_bytes() == right.read_bytes()

    def _active_is_bound_state(self) -> bool:
        for name in _ROOT_NAMES:
            active = self._sealed_root / f"{name}.cred"
            predecessor = self._predecessor / f"{name}.cred"
            candidate = self._candidate / f"{name}.cred"
            if not self._same_file_bytes(active, predecessor) and not (
                candidate.exists() and self._same_file_bytes(active, candidate)
            ):
                return False
        return True

    @staticmethod
    def _same_runtime_file(left: Path, right: Path) -> bool:
        return TransactionalPrimaryRootHost._same_file_bytes(left, right) and stat.S_IMODE(
            left.stat().st_mode
        ) == stat.S_IMODE(right.stat().st_mode)

    def _active_runtime_is_bound_mix(self) -> bool:
        for index, (label, _relative, _destination) in enumerate(_RUNTIME_ARTIFACTS):
            active = self._prepared.runtime_destinations[index]
            predecessor = self._runtime_predecessor / label
            absent = self._runtime_predecessor / f"{label}.absent"
            candidate = self._runtime_candidate / label
            predecessor_match = (
                absent.is_file() and not absent.is_symlink() and not active.exists()
            ) or self._same_runtime_file(active, predecessor)
            if not predecessor_match and not self._same_runtime_file(active, candidate):
                return False
        return True

    def _journal_plan(self) -> str:
        raw = self._journal.read_bytes()
        value = parse_json_bytes(raw, max_bytes=_MAX)
        if (
            type(value) is not dict
            or canonicalize(checked_json_value(value)) != raw
            or set(value) != {"phase", "plan_fingerprint", "schema_id", "schema_version"}
            or value.get("schema_id") != _STATE_SCHEMA
            or value.get("schema_version") != _VERSION
            or value.get("phase") not in _STATE_PHASES
            or type(value.get("plan_fingerprint")) is not str
        ):
            _fail("PRIMARY_ROOT_ROTATION_STATE_INVALID")
        return cast("str", value["plan_fingerprint"])

    def _write_journal(self, phase: str) -> None:
        raw = canonicalize(
            checked_json_value(
                {
                    "phase": phase,
                    "plan_fingerprint": self._plan.plan_fingerprint,
                    "schema_id": _STATE_SCHEMA,
                    "schema_version": _VERSION,
                }
            )
        )
        temporary = self._work / f".state.{token_urlsafe(18)}.tmp"
        temporary.write_bytes(raw)
        temporary.chmod(_PRIVATE_FILE)
        temporary.replace(self._journal)

    def _copy(self, source: Path, destination: Path) -> None:
        self._copy_with_mode(source, destination, _SEALED_FILE)

    def _copy_with_mode(self, source: Path, destination: Path, mode: int) -> None:
        if source.is_symlink() or not source.is_file():
            _fail("PRIMARY_ROOT_SEALED_STATE_INVALID")
        raw = source.read_bytes()
        if not 1 <= len(raw) <= _SEALED_MAX:
            _fail("PRIMARY_ROOT_SEALED_STATE_INVALID")
        temporary = destination.parent / f".{destination.name}.{token_urlsafe(18)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            _write_all(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        temporary.replace(destination)

    def _runtime_work_paths(self, root: Path) -> tuple[Path, ...]:
        return tuple(root / label for label, _relative, _destination in _RUNTIME_ARTIFACTS)

    def _stage_runtime_configuration(self) -> bool:
        for index, (label, _relative, _destination) in enumerate(_RUNTIME_ARTIFACTS):
            candidate = self._runtime_candidate / label
            if not candidate.exists():
                self._copy_with_mode(
                    self._prepared.runtime_sources[index], candidate, _EXECUTABLE_FILE
                )
            predecessor = self._runtime_predecessor / label
            absent = self._runtime_predecessor / f"{label}.absent"
            if not predecessor.exists() and not absent.exists():
                current = self._prepared.runtime_destinations[index]
                if current.exists():
                    self._copy_with_mode(
                        current,
                        predecessor,
                        stat.S_IMODE(current.stat().st_mode),
                    )
                else:
                    _retain(absent, b"absent")
        predecessor_paths = tuple(
            self._runtime_predecessor / label
            for label, _relative, _destination in _RUNTIME_ARTIFACTS
        )
        return (
            _runtime_configuration_ref(self._runtime_work_paths(self._runtime_candidate))
            == self._plan.candidate_runtime_configuration_ref
            and _runtime_configuration_ref(predecessor_paths)
            == self._plan.predecessor_runtime_configuration_ref
        )

    def _switch_runtime_configuration(self) -> bool:
        for index, source in enumerate(self._runtime_work_paths(self._runtime_candidate)):
            self._copy_with_mode(
                source, self._prepared.runtime_destinations[index], _EXECUTABLE_FILE
            )
        return (
            _runtime_configuration_ref(self._prepared.runtime_destinations)
            == self._plan.candidate_runtime_configuration_ref
        )

    def stage_candidate(self, plan: PrimaryVaultRootRotationPlan, root: Path) -> bool:
        if plan != self._plan or root != self._prepared.candidate_root:
            _fail("PRIMARY_ROOT_ROTATION_PLAN_DRIFT")
        if snapshot_binding(credential_snapshot(root)) != plan.candidate_binding_ref:
            _fail("PRIMARY_ROOT_STAGING_DRIFT")
        # Stage the immutable probe helper first. Rollback authentication proof
        # must remain possible even when its live predecessor was absent and is
        # therefore removed before the proof runs.
        if not self._stage_runtime_configuration():
            return False
        for name in _ROOT_NAMES:
            predecessor = self._predecessor / f"{name}.cred"
            if not predecessor.exists():
                self._copy(self._sealed_root / f"{name}.cred", predecessor)
            candidate = self._candidate / f"{name}.cred"
            source = root / name
            if source.is_symlink() or not source.is_file():
                _fail("PRIMARY_ROOT_STAGING_DRIFT")
            temporary = self._candidate / f".{name}.{token_urlsafe(18)}.tmp"
            descriptor = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                if not self._runner.seal(name, descriptor, temporary):
                    temporary.unlink(missing_ok=True)
                    return False
            finally:
                os.close(descriptor)
            try:
                if temporary.is_symlink() or not temporary.is_file():
                    _fail("PRIMARY_ROOT_SEALED_STATE_INVALID")
                temporary.chmod(_SEALED_FILE)
                temporary.replace(candidate)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        if _sealed_state(self._predecessor) != plan.predecessor_sealed_state_ref:
            _fail("PRIMARY_ROOT_SEALED_STATE_DRIFT")
        self._write_journal("STAGED")
        return True

    def stop_and_check(self, plan: PrimaryVaultRootRotationPlan) -> bool:
        if plan != self._plan:
            _fail("PRIMARY_ROOT_ROTATION_PLAN_DRIFT")
        stopped = self._runner.run(("/usr/bin/systemctl", "stop", *plan.stopped_units))
        stopped = stopped and all(
            self._runner.read(
                ("/usr/bin/systemctl", "show", "--property=ActiveState", "--value", unit),
                max_bytes=32,
            )
            == b"inactive\n"
            for unit in plan.stopped_units
        )
        if stopped:
            self._write_journal("STOPPED")
        return stopped

    def switch_candidate(self, plan: PrimaryVaultRootRotationPlan) -> bool:
        if plan != self._plan:
            _fail("PRIMARY_ROOT_ROTATION_PLAN_DRIFT")
        for name in _ROOT_NAMES:
            self._copy(self._candidate / f"{name}.cred", self._sealed_root / f"{name}.cred")
        if not self._switch_runtime_configuration():
            return False
        self._write_journal("SWITCHED")
        return _sealed_state(self._sealed_root) == _sealed_state(self._candidate)

    def _config_value_free(self) -> bool:
        config_raw = self._runner.read(
            (
                "/usr/bin/docker",
                "inspect",
                "--format",
                "{{json .Config}}",
                "asklegal-vault-primary",
            ),
            max_bytes=32_768,
        )
        mounts_raw = self._runner.read(
            (
                "/usr/bin/docker",
                "inspect",
                "--format",
                "{{json .Mounts}}",
                "asklegal-vault-primary",
            ),
            max_bytes=32_768,
        )
        if config_raw is None or mounts_raw is None:
            return False
        values = [
            self._prepared.source_root.joinpath(name).read_bytes() for name in _ROOT_NAMES
        ] + [self._prepared.candidate_root.joinpath(name).read_bytes() for name in _ROOT_NAMES]
        if any(value in config_raw or value in mounts_raw for value in values):
            return False
        try:
            config = parse_json_bytes(config_raw.strip(), max_bytes=32_768)
            mounts = parse_json_bytes(mounts_raw.strip(), max_bytes=32_768)
        except TypeError, ValueError:
            return False
        if not isinstance(config, dict) or not isinstance(mounts, list):
            return False
        environment = config.get("Env")
        expected_command = [
            "-ceu",
            'ROOT_ACCESS_KEY_ID="$(cat /run/asklegal/vault-primary-root-access)"; export ROOT_ACCESS_KEY_ID; ROOT_SECRET_ACCESS_KEY="$(cat /run/asklegal/vault-primary-root-secret)"; export ROOT_SECRET_ACCESS_KEY; exec /usr/local/bin/docker-entrypoint.sh "$@"',
            "asklegal-versity-file-entrypoint",
            "posix",
            "--versioning-dir",
            "/vault/versions",
            "--sidecar",
            "/vault/sidecar",
            "/vault/objects",
        ]
        if (
            not isinstance(environment, list)
            or any(not isinstance(item, str) or item.startswith("ROOT_") for item in environment)
            or config.get("Entrypoint") != ["/bin/sh"]
            or config.get("Cmd") != expected_command
        ):
            return False
        by_destination = {
            item.get("Destination"): item for item in mounts if isinstance(item, dict)
        }
        for name in _ROOT_NAMES:
            item = by_destination.get(f"/run/asklegal/{name}")
            if not isinstance(item, dict) or item.get("RW") is not False:
                return False
            if item.get("Source") != str(self._runtime_root / name):
                return False
        data = by_destination.get("/vault")
        return (
            isinstance(data, dict)
            and data.get("Source") == str(self._prepared.vault_data_root)
            and data.get("RW") is True
        )

    def restart_and_check(
        self, plan: PrimaryVaultRootRotationPlan, *, binding_ref: str
    ) -> RootHostReceipt:
        if plan != self._plan or binding_ref not in {
            plan.predecessor_binding_ref,
            plan.candidate_binding_ref,
        }:
            _fail("PRIMARY_ROOT_ROTATION_PLAN_DRIFT")
        expected_state = (
            plan.predecessor_sealed_state_ref
            if binding_ref == plan.predecessor_binding_ref
            else _sealed_state(self._candidate)
        )
        if _sealed_state(self._sealed_root) != expected_state:
            _fail("PRIMARY_ROOT_SEALED_STATE_DRIFT")
        vault_ok = self._runner.run(("/usr/bin/systemctl", "restart", _VAULT_UNIT))
        vault_ok = (
            vault_ok
            and self._runner.read(
                ("/usr/bin/systemctl", "show", "--property=ActiveState", "--value", _VAULT_UNIT),
                max_bytes=32,
            )
            == b"active\n"
        )
        bootstrap_ok = vault_ok and self._runner.run(
            ("/usr/bin/systemctl", "restart", _BOOTSTRAP_UNIT)
        )
        applications_ok = bootstrap_ok and self._runner.run(
            ("/usr/bin/systemctl", "restart", *_APPLICATION_UNITS)
        )
        applications_ok = applications_ok and all(
            self._runner.read(
                ("/usr/bin/systemctl", "show", "--property=ActiveState", "--value", unit),
                max_bytes=32,
            )
            == b"active\n"
            for unit in _APPLICATION_UNITS
        )
        data = vault_data_state(self._prepared.vault_data_root)
        config = self._config_value_free()
        healthy = applications_ok and data == plan.vault_data_state_ref and config
        if healthy:
            self._write_journal("SERVICES_ACTIVE")
        return RootHostReceipt(plan.plan_fingerprint, binding_ref, healthy, data, config)

    def record_acceptance(self, plan: PrimaryVaultRootRotationPlan) -> bool:
        if plan != self._plan:
            _fail("PRIMARY_ROOT_ROTATION_PLAN_DRIFT")
        if _sealed_state(self._sealed_root) != _sealed_state(self._candidate):
            _fail("PRIMARY_ROOT_SEALED_STATE_DRIFT")
        self._write_journal("AUTHENTICATION_PROVED")
        return True

    def restore_predecessor(self, plan: PrimaryVaultRootRotationPlan) -> RootRollbackReceipt:
        if plan != self._plan:
            _fail("PRIMARY_ROOT_ROTATION_PLAN_DRIFT")
        restored = True
        try:
            for name in _ROOT_NAMES:
                self._copy(self._predecessor / f"{name}.cred", self._sealed_root / f"{name}.cred")
            restored = (
                _sealed_state(self._sealed_root) == plan.predecessor_sealed_state_ref
                # The value-free launcher/helper are a security prerequisite,
                # not credential state. Retain them during credential rollback
                # so restarting the predecessor root never recreates the
                # Docker Config.Env exposure this transaction repairs.
                and self._switch_runtime_configuration()
            )
        except Exception:
            restored = False
        candidate_absent = False
        if restored:
            try:
                for name in _ROOT_NAMES:
                    (self._candidate / f"{name}.cred").unlink(missing_ok=True)
                self._candidate.rmdir()
                candidate_absent = True
                self._write_journal("PREDECESSOR_RESTORED")
            except OSError:
                pass
        return RootRollbackReceipt(plan.plan_fingerprint, restored, candidate_absent)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "execute"))
    parser.add_argument("--staging-receipt", type=Path, required=True)
    parser.add_argument("--sealed-root", type=Path, required=True)
    parser.add_argument("--vault-data-root", type=Path, required=True)
    parser.add_argument("--application-build-results", type=Path, required=True)
    parser.add_argument("--application-image-inputs", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--plan-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--runtime-credential-root", type=Path)
    parser.add_argument("--authorized-plan-fingerprint")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        plan_path = arguments.plan_output.absolute()
        retained_plan: PrimaryVaultRootRotationPlan | None = None
        if arguments.action == "execute":
            if plan_path.is_symlink() or not plan_path.is_file():
                _fail("PRIMARY_ROOT_ROTATION_AUTHORITY_REQUIRED")
            retained_plan = parse_root_rotation_plan_bytes(plan_path.read_bytes())
        image_id, build_fingerprint = candidate_image_provenance(
            build_results_path=arguments.application_build_results.absolute(),
            image_inputs_path=arguments.application_image_inputs.absolute(),
            workspace_root=arguments.workspace_root.absolute(),
        )
        prepared = prepare_primary_vault_root_rotation(
            arguments.staging_receipt.absolute(),
            sealed_root=arguments.sealed_root.absolute(),
            vault_data_root=arguments.vault_data_root.absolute(),
            control_plane_candidate_image_id=image_id,
            application_build_results_fingerprint=build_fingerprint,
            retained_plan=retained_plan,
            workspace_root=arguments.workspace_root.absolute(),
        )
        retain_root_rotation_plan(plan_path, prepared.plan)
        if arguments.action == "preflight":
            sys.stdout.buffer.write(root_rotation_plan_bytes(prepared.plan) + b"\n")
            return 0
        if (
            os.geteuid() != 0
            or arguments.state_root is None
            or arguments.runtime_credential_root is None
            or arguments.report_output is None
            or arguments.authorized_plan_fingerprint != prepared.plan.plan_fingerprint
        ):
            _fail("PRIMARY_ROOT_ROTATION_AUTHORITY_REQUIRED")
        with exclusive_root_rotation_execution(arguments.state_root.absolute()):
            runner = QuietExactCommandRunner()
            host = TransactionalPrimaryRootHost(
                arguments.sealed_root.absolute(),
                arguments.state_root.absolute(),
                arguments.runtime_credential_root.absolute(),
                prepared,
                runner=runner,
                authorized_plan_fingerprint=arguments.authorized_plan_fingerprint,
            )
            network = RootNetworkAdapter(
                runner,
                prepared,
                plan_path,
                cast("str", arguments.authorized_plan_fingerprint),
                sealed_root=arguments.sealed_root.absolute(),
                helper_path=(
                    arguments.state_root.absolute()
                    / f"{prepared.plan.rotation_id}-primary-root"
                    / "runtime-candidate"
                    / "primary-root-network-helper"
                ),
            )
            report = execute_primary_vault_root_rotation(prepared, host=host, probe=network)
            raw = root_rotation_report_bytes(report)
            _retain(arguments.report_output.absolute(), raw)
        sys.stdout.buffer.write(raw + b"\n")
        return 0 if report.state is RootRotationState.SUCCEEDED else 2
    except OSError, TypeError, ValueError, PrimaryVaultRootRotationError:
        sys.stderr.write("PRIMARY_VAULT_ROOT_ROTATION_NOT_READY\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
