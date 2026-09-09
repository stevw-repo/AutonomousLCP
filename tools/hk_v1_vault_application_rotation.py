"""Fail-closed boundary for rotating the complete V1 vault application set.

This module validates the retained plaintext-staging receipt and exposes an
authority-gated host adapter plus an exact candidate-image helper boundary for
the two isolated vault networks.  Tests inject no-effect ports; the CLI refuses
mutation without a matching plan fingerprint and root authority.
"""

# The orchestration intentionally normalizes ordinary adapter errors into a
# closed report and therefore has an explicit multi-return state machine.
# ruff: noqa: BLE001, C901, PLR0911, PLR0912, PLR0913, S110, SIM105

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe
from typing import Never, Protocol, cast, runtime_checkable
from urllib.parse import quote

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_control_plane.bootstrap import (
    VaultIdentityAdministrationPort,
    VersityIdentityAdministration,
)
from asklegal_evidence_vault import (
    S3AccessCredential,
    S3VaultError,
    V1S3VaultSettings,
    VaultName,
    create_v1_s3_client,
)

from tools.hk_v1_stage_vault_credential_rotation import (
    deployment_credential_names,
    stage_vault_credential_rotation,
)
from tools.v1_poc_build_images import workspace_source_fingerprint

_MAX_DOCUMENT_BYTES = 65_536
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_BINDING = re.compile(r"^binding_[0-9a-f]{48}$")
_ROTATION = re.compile(r"^rot_[0-9a-f]{48}$")
_SEALED_STATE = re.compile(r"^sealed_[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_STAGING_SCHEMA = "asklegal.hk-v1-vault-credential-staging-receipt"
_REPORT_SCHEMA = "asklegal.hk-v1-vault-application-rotation-report"
_VERSION = "1.0.0"

_PRIMARY_NAMES = (
    "vault-primary-acquisition",
    "vault-primary-control",
    "vault-primary-processing",
    "vault-primary-promotion",
    "vault-primary-review",
)
_RECOVERY_NAMES = (
    "vault-recovery-acquisition",
    "vault-recovery-promotion",
)
_ROTATED_NAMES = tuple(sorted((*_PRIMARY_NAMES, *_RECOVERY_NAMES)))
_DEPENDENT_UNITS = (
    "asklegal-acquisition-worker.service",
    "asklegal-control-plane.service",
    "asklegal-legal-processing-worker.service",
    "asklegal-promotion-worker.service",
    "asklegal-review-api.service",
)
_CREDENTIAL_UNITS = (
    ("vault-primary-acquisition", ("asklegal-acquisition-worker.service",)),
    ("vault-primary-control", ("asklegal-control-plane.service",)),
    ("vault-primary-processing", ("asklegal-legal-processing-worker.service",)),
    ("vault-primary-promotion", ("asklegal-promotion-worker.service",)),
    ("vault-primary-review", ("asklegal-review-api.service",)),
    ("vault-recovery-acquisition", ("asklegal-acquisition-worker.service",)),
    ("vault-recovery-promotion", ("asklegal-promotion-worker.service",)),
)
_MAX_SEALED_BYTES = 1_048_576
_SEALED_FILE_MODE = 0o400
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_LIVE_STATE_SCHEMA = "asklegal.hk-v1-vault-application-rotation-live-state"
_BUILD_RESULTS_SCHEMA = "asklegal.hk-v1-application-build-results/v1"
_APPLICATION_SERVICES = (
    "acquisition-worker",
    "control-plane",
    "legal-processing-worker",
    "promotion-worker",
    "review-api",
)
_CLEANUP_PHASES = frozenset({"CLEANING_SOURCE", "CLEANING_CANDIDATE", "CLEANED", "TERMINAL"})


class VaultApplicationRotationError(RuntimeError):
    """One sanitized boundary failure."""


def _fail(code: str) -> Never:
    raise VaultApplicationRotationError(code)


class RotationState(StrEnum):
    """Closed terminal states for the seven-credential operation."""

    SUCCEEDED = "SUCCEEDED"
    ROLLED_BACK = "ROLLED_BACK"
    BLOCKED = "BLOCKED"


class RotationBlocker(StrEnum):
    """Sanitized operation and production-composition blockers."""

    APPLICATION_AUTHENTICATION_ADAPTER_MISSING = "APPLICATION_AUTHENTICATION_ADAPTER_MISSING"
    ACCEPTANCE_JOURNAL_FAILED = "ACCEPTANCE_JOURNAL_FAILED"
    CANDIDATE_AUTHENTICATION_FAILED = "CANDIDATE_AUTHENTICATION_FAILED"
    CANDIDATE_IMAGE_PROVENANCE_MISSING = "CANDIDATE_IMAGE_PROVENANCE_MISSING"
    CANDIDATE_SEAL_FAILED = "CANDIDATE_SEAL_FAILED"
    CROSS_VAULT_IAM_RECONCILIATION_ADAPTER_MISSING = (
        "CROSS_VAULT_IAM_RECONCILIATION_ADAPTER_MISSING"
    )
    DEPENDENT_UNIT_FAILURE = "DEPENDENT_UNIT_FAILURE"
    DUAL_VAULT_NETWORK_EXECUTION_ADAPTER_MISSING = "DUAL_VAULT_NETWORK_EXECUTION_ADAPTER_MISSING"
    HOST_TRANSACTIONAL_SEAL_SWITCH_ADAPTER_MISSING = (
        "HOST_TRANSACTIONAL_SEAL_SWITCH_ADAPTER_MISSING"
    )
    HOST_RECONCILE_BATCH_PLAN_UNSUPPORTED = "HOST_RECONCILE_BATCH_PLAN_UNSUPPORTED"
    IDENTITY_READBACK_FAILED = "IDENTITY_READBACK_FAILED"
    IDENTITY_UPDATE_FAILED = "IDENTITY_UPDATE_FAILED"
    OBSOLETE_IDENTITY_RETIREMENT_ADAPTER_MISSING = "OBSOLETE_IDENTITY_RETIREMENT_ADAPTER_MISSING"
    PLAINTEXT_CLEANUP_FAILED = "PLAINTEXT_CLEANUP_FAILED"
    PREDECESSOR_STILL_ACCEPTED = "PREDECESSOR_STILL_ACCEPTED"
    RECEIPT_MISMATCH = "RECEIPT_MISMATCH"
    ROLLBACK_NOT_PROVED = "ROLLBACK_NOT_PROVED"
    SEALED_SWITCH_FAILED = "SEALED_SWITCH_FAILED"
    TERMINAL_CLEANUP_COORDINATOR_MISSING = "TERMINAL_CLEANUP_COORDINATOR_MISSING"


@dataclass(frozen=True, slots=True)
class VaultApplicationRotationPlan:
    """Value-free binding for one complete vault-application rotation."""

    rotation_id: str
    staging_receipt_fingerprint: str
    predecessor_binding_ref: str
    candidate_binding_ref: str
    predecessor_sealed_state_ref: str
    control_plane_candidate_image_id: str
    application_build_results_fingerprint: str | None
    sealed_credential_names: tuple[str, ...]
    rotated_credential_names: tuple[str, ...]
    credential_units: tuple[tuple[str, tuple[str, ...]], ...]
    dependent_units: tuple[str, ...]
    predecessor_plaintext_sha256: tuple[tuple[str, str], ...]
    candidate_plaintext_sha256: tuple[tuple[str, str], ...]
    plan_fingerprint: str

    def __post_init__(self) -> None:
        """Reject caller-selected or incomplete batch bindings."""
        if (
            _ROTATION.fullmatch(self.rotation_id) is None
            or _FINGERPRINT.fullmatch(self.staging_receipt_fingerprint) is None
            or _BINDING.fullmatch(self.predecessor_binding_ref) is None
            or _BINDING.fullmatch(self.candidate_binding_ref) is None
            or self.predecessor_binding_ref == self.candidate_binding_ref
            or _SEALED_STATE.fullmatch(self.predecessor_sealed_state_ref) is None
            or _IMAGE_ID.fullmatch(self.control_plane_candidate_image_id) is None
            or (
                self.application_build_results_fingerprint is not None
                and _FINGERPRINT.fullmatch(self.application_build_results_fingerprint) is None
            )
            or self.sealed_credential_names != _ROTATED_NAMES
            or self.rotated_credential_names != _ROTATED_NAMES
            or self.credential_units != _CREDENTIAL_UNITS
            or self.dependent_units != _DEPENDENT_UNITS
            or tuple(name for name, _digest in self.predecessor_plaintext_sha256) != _ROTATED_NAMES
            or tuple(name for name, _digest in self.candidate_plaintext_sha256) != _ROTATED_NAMES
            or any(
                re.fullmatch(r"[0-9a-f]{64}", digest) is None
                for _name, digest in (
                    *self.predecessor_plaintext_sha256,
                    *self.candidate_plaintext_sha256,
                )
            )
        ):
            _fail("ROTATION_PLAN_INVALID")
        expected = _fingerprint(
            _plan_body(
                rotation_id=self.rotation_id,
                staging_receipt_fingerprint=self.staging_receipt_fingerprint,
                predecessor_binding_ref=self.predecessor_binding_ref,
                candidate_binding_ref=self.candidate_binding_ref,
                predecessor_sealed_state_ref=self.predecessor_sealed_state_ref,
                control_plane_candidate_image_id=self.control_plane_candidate_image_id,
                application_build_results_fingerprint=self.application_build_results_fingerprint,
                predecessor_plaintext_sha256=self.predecessor_plaintext_sha256,
                candidate_plaintext_sha256=self.candidate_plaintext_sha256,
            )
        )
        if self.plan_fingerprint != expected:
            _fail("ROTATION_PLAN_INVALID")


@dataclass(frozen=True, slots=True)
class BoundReceipt:
    """Exact adapter readback bound to one plan."""

    plan_fingerprint: str
    binding_ref: str


@dataclass(frozen=True, slots=True)
class HostCleanupReceipt:
    """Exact success cleanup readback."""

    plan_fingerprint: str
    predecessor_sealed_absent: bool
    predecessor_plaintext_absent: bool
    candidate_plaintext_absent: bool


@dataclass(frozen=True, slots=True)
class HostRollbackReceipt:
    """Exact predecessor-restoration readback."""

    plan_fingerprint: str
    predecessor_active: bool
    candidate_sealed_absent: bool
    candidate_plaintext_absent: bool


@dataclass(frozen=True, slots=True)
class UnitReceipt:
    """Exact restart and health readback."""

    plan_fingerprint: str
    binding_ref: str
    units: tuple[str, ...]
    healthy: bool


@dataclass(frozen=True, slots=True)
class UnitStopReceipt:
    """Exact proof that only the five dependent units are inactive."""

    plan_fingerprint: str
    units: tuple[str, ...]
    stopped: bool


@dataclass(frozen=True, slots=True)
class AcceptanceReceipt:
    """Exact acceptance partition for the seven named credentials."""

    plan_fingerprint: str
    binding_ref: str
    accepted_names: tuple[str, ...]
    rejected_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VaultApplicationRotationReport:
    """Secret-free terminal result."""

    plan_fingerprint: str
    staging_receipt_fingerprint: str
    candidate_binding_ref: str
    rotation_id: str
    state: RotationState
    complete: bool
    new_values_accepted: bool
    old_values_rejected: bool
    predecessor_restored: bool
    candidate_sealed_absent: bool
    plaintext_absent: bool
    blocker_codes: tuple[RotationBlocker, ...]

    def __post_init__(self) -> None:
        """Reject a success or rollback not proved by its closed facts."""
        if (
            type(self.blocker_codes) is not tuple
            or any(type(item) is not RotationBlocker for item in self.blocker_codes)
            or any(
                type(item) is not bool
                for item in (
                    self.complete,
                    self.new_values_accepted,
                    self.old_values_rejected,
                    self.predecessor_restored,
                    self.candidate_sealed_absent,
                    self.plaintext_absent,
                )
            )
        ):
            _fail("ROTATION_REPORT_INVALID")
        if (
            _FINGERPRINT.fullmatch(self.plan_fingerprint) is None
            or _FINGERPRINT.fullmatch(self.staging_receipt_fingerprint) is None
            or _BINDING.fullmatch(self.candidate_binding_ref) is None
            or _ROTATION.fullmatch(self.rotation_id) is None
            or type(self.state) is not RotationState
            or self.blocker_codes
            != tuple(sorted(set(self.blocker_codes), key=lambda item: item.value))
            or self.complete != (self.state is RotationState.SUCCEEDED)
        ):
            _fail("ROTATION_REPORT_INVALID")
        if self.state is RotationState.SUCCEEDED and (
            self.blocker_codes
            or not self.new_values_accepted
            or not self.old_values_rejected
            or self.predecessor_restored
            or self.candidate_sealed_absent
            or not self.plaintext_absent
        ):
            _fail("ROTATION_REPORT_INVALID")
        if self.state is RotationState.ROLLED_BACK and (
            not self.blocker_codes
            or self.new_values_accepted
            or self.old_values_rejected
            or not self.predecessor_restored
            or not self.candidate_sealed_absent
            or self.plaintext_absent
        ):
            _fail("ROTATION_REPORT_INVALID")
        if self.state is RotationState.BLOCKED and not self.blocker_codes:
            _fail("ROTATION_REPORT_INVALID")


@dataclass(frozen=True, slots=True, repr=False)
class _CredentialSets:
    predecessor: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...]
    candidate: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...]


@dataclass(frozen=True, slots=True, repr=False)
class PreparedVaultApplicationRotation:
    """Validated plan plus in-memory credentials that never enter evidence."""

    plan: VaultApplicationRotationPlan
    credentials: _CredentialSets
    source_root: Path
    candidate_root: Path


@dataclass(frozen=True, slots=True)
class _StagingReceiptBinding:
    raw: bytes
    fingerprint: str
    rotation_id: str
    predecessor_binding_ref: str
    candidate_binding_ref: str
    source_root: Path
    candidate_root: Path


class HostCredentialSetPort(Protocol):
    """Transactional full-set sealing and exact active-binding boundary."""

    def inspect_predecessor(self, credential_names: tuple[str, ...]) -> str:
        """Return an opaque fingerprint of the seven active sealed credentials."""
        ...

    def stage_candidate(
        self, plan: VaultApplicationRotationPlan, candidate_root: Path
    ) -> BoundReceipt:
        """Seal exactly the seven candidates without switching them."""
        ...

    def stop_and_check(self, plan: VaultApplicationRotationPlan) -> UnitStopReceipt:
        """Stop exactly the five dependent application units and prove inactivity."""
        ...

    def switch_candidate(
        self, plan: VaultApplicationRotationPlan, staged: BoundReceipt
    ) -> BoundReceipt:
        """Switch the exact complete sealed set and read it back."""
        ...

    def restart_and_check(
        self, plan: VaultApplicationRotationPlan, *, binding_ref: str
    ) -> UnitReceipt:
        """Restart only the five dependent units and prove health."""
        ...

    def record_acceptance(self, plan: VaultApplicationRotationPlan) -> BoundReceipt:
        """Durably bind candidate acceptance and predecessor rejection before cleanup."""
        ...

    def finalize_success(
        self, plan: VaultApplicationRotationPlan, switched: BoundReceipt
    ) -> HostCleanupReceipt:
        """Remove predecessor sealed and both plaintext sets, then prove absence."""
        ...

    def restore_predecessor(self, plan: VaultApplicationRotationPlan) -> HostRollbackReceipt:
        """Restore the exact predecessor and discard candidate material."""
        ...


class SealedPredecessorInspector(Protocol):
    """Read-only exact active sealed-set inspection boundary."""

    def inspect_predecessor(self, credential_names: tuple[str, ...]) -> str:
        """Return an opaque fingerprint of the seven active sealed credentials."""
        ...


class TerminalCleanupPort(Protocol):
    """Crash-resumable proof and predecessor-retirement boundary."""

    def finalize_success(
        self, plan: VaultApplicationRotationPlan, switched: BoundReceipt
    ) -> HostCleanupReceipt:
        """Resume the journaled removal of both plaintext staging roots."""
        ...

    def prove_succeeded_after_cleanup(
        self, plan: VaultApplicationRotationPlan
    ) -> VaultApplicationRotationReport:
        """Reconstruct success only from durable acceptance and cleanup facts."""
        ...

    def retire_predecessor_after_report(
        self, plan: VaultApplicationRotationPlan, report_path: Path
    ) -> BoundReceipt:
        """Retire rollback blobs only after the exact success report exists."""
        ...

    def retain_succeeded_report(
        self,
        plan: VaultApplicationRotationPlan,
        report_path: Path,
        report: VaultApplicationRotationReport,
    ) -> None:
        """Retain the exact report inside the pinned root-owned state directory."""
        ...


class FlatSealedPredecessorInspector:
    """Read-only inspector for the flat paths consumed by current systemd units."""

    def __init__(self, sealed_root: Path) -> None:
        """Bind one absolute, existing, nonsymlink sealed root."""
        if (
            not sealed_root.is_absolute()
            or sealed_root == Path(sealed_root.anchor)
            or sealed_root.is_symlink()
            or _has_symlink_component(sealed_root.parent)
            or not sealed_root.is_dir()
            or stat.S_IMODE(sealed_root.stat().st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            _fail("PREDECESSOR_SEALED_STATE_INVALID")
        self._root = sealed_root
        self._owner_uid = sealed_root.stat().st_uid

    def inspect_predecessor(self, credential_names: tuple[str, ...]) -> str:
        """Hash names and opaque sealed bytes without decrypting or printing them."""
        if credential_names != _ROTATED_NAMES:
            _fail("PREDECESSOR_SEALED_STATE_INVALID")
        rows: list[JsonValue] = []
        directory = os.open(
            self._root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            directory_facts = os.fstat(directory)
            if (
                not stat.S_ISDIR(directory_facts.st_mode)
                or stat.S_IMODE(directory_facts.st_mode) != _PRIVATE_DIRECTORY_MODE
                or directory_facts.st_uid != self._owner_uid
            ):
                _fail("PREDECESSOR_SEALED_STATE_INVALID")
            for name in credential_names:
                descriptor = os.open(
                    f"{name}.cred",
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=directory,
                )
                try:
                    facts = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(facts.st_mode)
                        or stat.S_IMODE(facts.st_mode) != _SEALED_FILE_MODE
                        or facts.st_uid != self._owner_uid
                        or not 1 <= facts.st_size <= _MAX_SEALED_BYTES
                    ):
                        _fail("PREDECESSOR_SEALED_STATE_INVALID")
                    chunks: list[bytes] = []
                    remaining = facts.st_size
                    while remaining:
                        chunk = os.read(descriptor, remaining)
                        if not chunk:
                            _fail("PREDECESSOR_SEALED_STATE_INVALID")
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    after = os.fstat(descriptor)
                    if (
                        after.st_size != facts.st_size
                        or after.st_mtime_ns != facts.st_mtime_ns
                        or after.st_ino != facts.st_ino
                        or after.st_dev != facts.st_dev
                    ):
                        _fail("PREDECESSOR_SEALED_STATE_INVALID")
                    raw = b"".join(chunks)
                finally:
                    os.close(descriptor)
                if not raw or len(raw) > _MAX_SEALED_BYTES:
                    _fail("PREDECESSOR_SEALED_STATE_INVALID")
                rows.append(
                    {
                        "mode": _SEALED_FILE_MODE,
                        "name": name,
                        "owner_uid": self._owner_uid,
                        "sha256": sha256(raw).hexdigest(),
                        "size": len(raw),
                    }
                )
            current = self._root.stat()
            if self._root.is_symlink() or (current.st_dev, current.st_ino) != (
                directory_facts.st_dev,
                directory_facts.st_ino,
            ):
                _fail("PREDECESSOR_SEALED_STATE_INVALID")
        finally:
            os.close(directory)
        return "sealed_" + sha256(canonicalize(checked_json_value(rows))).hexdigest()


class ExactCommandRunner(Protocol):
    """No-shell system command boundary with bounded, value-free readback."""

    def run(self, arguments: tuple[str, ...]) -> bool:
        """Run fixed arguments while discarding all provider output."""
        ...

    def read(self, arguments: tuple[str, ...], *, max_bytes: int) -> bytes | None:
        """Return one bounded stdout value, or None on any failure."""
        ...

    def seal(self, name: str, source_descriptor: int, output: Path) -> bool:
        """Seal from one already validated descriptor without reopening its path."""
        ...


class QuietExactCommandRunner:
    """Production subprocess runner that never uses a shell or exposes stderr."""

    def run(self, arguments: tuple[str, ...]) -> bool:
        """Run one exact argv with no ambient credential or output inheritance."""
        completed = subprocess.run(  # noqa: S603
            arguments,
            check=False,
            close_fds=True,
            env={"PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return completed.returncode == 0

    def read(self, arguments: tuple[str, ...], *, max_bytes: int) -> bytes | None:
        """Capture only a short non-secret status and reject truncation."""
        completed = subprocess.run(  # noqa: S603
            arguments,
            check=False,
            close_fds=True,
            env={"PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode != 0 or len(completed.stdout) > max_bytes:
            return None
        return completed.stdout

    def seal(self, name: str, source_descriptor: int, output: Path) -> bool:
        """Pass only a validated descriptor to systemd-creds, never plaintext argv."""
        completed = subprocess.run(  # noqa: S603
            (
                "/usr/bin/systemd-creds",
                "encrypt",
                "--with-key=host+tpm2",
                f"--name={name}",
                f"/proc/self/fd/{source_descriptor}",
                str(output),
            ),
            check=False,
            close_fds=True,
            pass_fds=(source_descriptor,),
            env={"PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return completed.returncode == 0


@runtime_checkable
class _HeadBucketClient(Protocol):
    def head_bucket(self, **kwargs: object) -> Mapping[str, object]:
        """Read only bucket metadata under one explicit application identity."""
        ...


class S3HeadBucketAuthenticator:
    """Classify only successful or authentication-rejected S3 HEAD requests."""

    def check(
        self,
        plan: VaultApplicationRotationPlan,
        *,
        binding_ref: str,
        credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    ) -> AcceptanceReceipt:
        """Probe all seven explicit credentials without ambient lookup or output."""
        if (
            type(plan) is not VaultApplicationRotationPlan
            or binding_ref not in {plan.predecessor_binding_ref, plan.candidate_binding_ref}
            or tuple(vault for vault, _items in credentials)
            != (VaultName.PRIMARY, VaultName.RECOVERY)
        ):
            _fail("AUTHENTICATION_INPUT_INVALID")
        accepted: list[str] = []
        rejected: list[str] = []
        offset = 0
        for vault, items in credentials:
            settings = V1S3VaultSettings.for_vault(vault)
            for credential in items:
                if offset >= len(_ROTATED_NAMES):
                    _fail("AUTHENTICATION_INPUT_INVALID")
                name = (*_PRIMARY_NAMES, *_RECOVERY_NAMES)[offset]
                offset += 1
                candidate = create_v1_s3_client(
                    settings,
                    credential,
                    retry_attempts=1,
                    connect_timeout_seconds=5,
                    read_timeout_seconds=10,
                )
                if not isinstance(candidate, _HeadBucketClient):
                    _fail("AUTHENTICATION_PROVIDER_FAILED")
                try:
                    candidate.head_bucket(Bucket=settings.bucket)
                except Exception as error:
                    response_value: object = vars(error).get("response")
                    try:
                        response = checked_json_value(response_value)
                    except TypeError:
                        response = None
                    metadata = (
                        response.get("ResponseMetadata") if isinstance(response, dict) else None
                    )
                    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
                    code_value = response.get("Error") if isinstance(response, dict) else None
                    code = code_value.get("Code") if isinstance(code_value, dict) else None
                    if status not in {401, 403} and code not in {
                        "AccessDenied",
                        "InvalidAccessKeyId",
                        "SignatureDoesNotMatch",
                    }:
                        code = "AUTHENTICATION_PROVIDER_FAILED"
                        raise VaultApplicationRotationError(code) from None
                    rejected.append(name)
                else:
                    accepted.append(name)
        if offset != len(_ROTATED_NAMES):
            _fail("AUTHENTICATION_INPUT_INVALID")
        return AcceptanceReceipt(
            plan.plan_fingerprint,
            binding_ref,
            tuple(sorted(accepted)),
            tuple(sorted(rejected)),
        )


class VaultCredentialAcceptancePort(Protocol):
    """Provider-aware classification of accepted versus rejected credentials."""

    def check(
        self,
        plan: VaultApplicationRotationPlan,
        *,
        binding_ref: str,
        credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    ) -> AcceptanceReceipt:
        """Return only classified acceptance names; unknown provider errors raise."""
        ...


class ExactIdentitySetPort(Protocol):
    """Replace and read back both complete ordinary-user sets."""

    def replace(
        self,
        credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    ) -> None:
        """Replace both exact identity sets or raise."""
        ...


class _VersityRotationAdministration(VaultIdentityAdministrationPort, Protocol):
    """Existing signed administrator surface needed for exact-set reconciliation."""

    def rotation_users(self) -> tuple[tuple[str, str, str], ...]:
        """Return the bounded provider readback already strictly parsed upstream."""
        ...

    def delete_rotation_user(self, access: str) -> None:
        """Delete one exact plan-bound obsolete access identity."""
        ...


class VersityRotationAdministration(VersityIdentityAdministration):
    """Narrow rotation extension of the existing fixed signed admin transport."""

    def rotation_users(self) -> tuple[tuple[str, str, str], ...]:
        """Expose the existing strict bounded XML readback for reconciliation."""
        return self._users()

    def delete_rotation_user(self, access: str) -> None:
        """Delete one already plan-validated access identity through signed PATCH."""
        self._request("/delete-user?access=" + quote(access, safe=""), b"", 204)


class ReconciledVersityIdentitySetAdapter:
    """Converge two vaults between only the plan-bound old and new identity sets."""

    def __init__(
        self,
        administrators: tuple[
            tuple[VaultName, _VersityRotationAdministration],
            tuple[VaultName, _VersityRotationAdministration],
        ],
        predecessor: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
        candidate: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
        *,
        plan: VaultApplicationRotationPlan,
        authorized_plan_fingerprint: str,
    ) -> None:
        """Bind both exact target sets before any provider request is possible."""
        vaults = (VaultName.PRIMARY, VaultName.RECOVERY)
        if (
            tuple(vault for vault, _admin in administrators) != vaults
            or tuple(vault for vault, _items in predecessor) != vaults
            or tuple(vault for vault, _items in candidate) != vaults
            or type(plan) is not VaultApplicationRotationPlan
            or authorized_plan_fingerprint != plan.plan_fingerprint
        ):
            _fail("IDENTITY_ADMINISTRATION_INPUT_INVALID")
        self._administrators = administrators
        self._predecessor = predecessor
        self._candidate = candidate

    @staticmethod
    def _pairs(items: tuple[S3AccessCredential, ...]) -> tuple[tuple[str, str], ...]:
        return tuple(item.reveal_for_client() for item in items)

    def replace(
        self,
        credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    ) -> None:
        """Converge exactly, permitting only old/new values and exact signed deletes."""
        if credentials not in (self._predecessor, self._candidate):
            _fail("IDENTITY_ADMINISTRATION_INPUT_INVALID")
        for (vault, administrator), (target_vault, target_items), (
            predecessor_vault,
            predecessor_items,
        ), (candidate_vault, candidate_items) in zip(
            self._administrators,
            credentials,
            self._predecessor,
            self._candidate,
            strict=True,
        ):
            if not (vault is target_vault is predecessor_vault is candidate_vault):
                _fail("IDENTITY_ADMINISTRATION_INPUT_INVALID")
            allowed = set(self._pairs(predecessor_items)) | set(self._pairs(candidate_items))
            current = administrator.rotation_users()
            if len({access for access, _secret, _role in current}) != len(current):
                _fail("IDENTITY_READBACK_FAILED")
            if any(
                role != "user" or (access, secret) not in allowed
                for access, secret, role in current
            ):
                _fail("IDENTITY_READBACK_FAILED")
            administrator.provision(target_items)
            requested = {access for access, _secret in self._pairs(target_items)}
            for access, _secret, _role in administrator.rotation_users():
                if access not in requested:
                    administrator.delete_rotation_user(access)
            if administrator.readback(target_items) != tuple(
                access for access, _secret in self._pairs(target_items)
            ):
                _fail("IDENTITY_READBACK_FAILED")


class BootstrapIdentitySetAdapter:
    """Safe subset of the existing bootstrap IAM API for stable access IDs."""

    def __init__(
        self,
        administrators: tuple[
            tuple[VaultName, VaultIdentityAdministrationPort],
            tuple[VaultName, VaultIdentityAdministrationPort],
        ],
    ) -> None:
        """Bind the Primary and Recovery administrators in exact order."""
        if tuple(vault for vault, _admin in administrators) != (
            VaultName.PRIMARY,
            VaultName.RECOVERY,
        ):
            _fail("IDENTITY_ADMINISTRATION_INPUT_INVALID")
        self._administrators = administrators

    def replace(
        self,
        credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    ) -> None:
        """Update stable identities and require exact bootstrap readback."""
        if tuple(vault for vault, _items in credentials) != (
            VaultName.PRIMARY,
            VaultName.RECOVERY,
        ):
            _fail("IDENTITY_ADMINISTRATION_INPUT_INVALID")
        for (vault, administrator), (credential_vault, items) in zip(
            self._administrators, credentials, strict=True
        ):
            if vault is not credential_vault:
                _fail("IDENTITY_ADMINISTRATION_INPUT_INVALID")
            expected = tuple(item.reveal_for_client()[0] for item in items)
            administrator.provision(items)
            if administrator.readback(items) != expected:
                _fail("IDENTITY_READBACK_FAILED")


class DualNetworkRotationAdapter:
    """Fixed-argv host boundary for the exact candidate-image network helper."""

    def __init__(
        self,
        runner: ExactCommandRunner,
        prepared: PreparedVaultApplicationRotation,
        *,
        plan_path: Path,
        authorized_plan_fingerprint: str,
    ) -> None:
        """Bind the authorized canonical plan to the fixed helper invocation."""
        if (
            type(prepared) is not PreparedVaultApplicationRotation
            or authorized_plan_fingerprint != prepared.plan.plan_fingerprint
            or prepared.plan.application_build_results_fingerprint is None
            or not plan_path.is_absolute()
            or plan_path.is_symlink()
            or parse_rotation_plan_bytes(plan_path.read_bytes()) != prepared.plan
        ):
            _fail("ROTATION_NETWORK_INPUT_INVALID")
        self._runner = runner
        self._prepared = prepared
        self._plan = _copy_plan(prepared.plan)
        self._plan_path = plan_path
        self._authorized_plan_fingerprint = authorized_plan_fingerprint
        self._plan_descriptor = os.open(plan_path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        self._root_descriptors: dict[Path, int] = {}
        self._root_pins: dict[Path, tuple[int, int, int]] = {}
        for root in (prepared.source_root, prepared.candidate_root):
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            facts = os.fstat(descriptor)
            self._root_descriptors[root] = descriptor
            self._root_pins[root] = (facts.st_dev, facts.st_ino, facts.st_uid)
        self._validate_effect_inputs()

    def _validate_effect_inputs(self) -> None:
        """Rebind every authorized pathname and full staging set before effects."""
        if (
            self._authorized_plan_fingerprint != self._plan.plan_fingerprint
            or self._prepared.plan != self._plan
        ):
            _fail("ROTATION_NETWORK_INPUT_DRIFT")
        plan_facts = os.fstat(self._plan_descriptor)
        try:
            current_plan = self._plan_path.stat(follow_symlinks=False)
            plan_raw = os.pread(self._plan_descriptor, plan_facts.st_size, 0)
            plan_after = os.fstat(self._plan_descriptor)
            current_plan_after = self._plan_path.stat(follow_symlinks=False)
        except OSError as error:
            code = "ROTATION_NETWORK_INPUT_DRIFT"
            raise VaultApplicationRotationError(code) from error
        if (
            not stat.S_ISREG(plan_facts.st_mode)
            or stat.S_IMODE(plan_facts.st_mode) != _PRIVATE_FILE_MODE
            or (current_plan.st_dev, current_plan.st_ino) != (plan_facts.st_dev, plan_facts.st_ino)
            or (current_plan_after.st_dev, current_plan_after.st_ino)
            != (plan_facts.st_dev, plan_facts.st_ino)
            or (plan_after.st_dev, plan_after.st_ino, plan_after.st_size, plan_after.st_mtime_ns)
            != (plan_facts.st_dev, plan_facts.st_ino, plan_facts.st_size, plan_facts.st_mtime_ns)
            or len(plan_raw) != plan_facts.st_size
            or parse_rotation_plan_bytes(plan_raw) != self._plan
        ):
            _fail("ROTATION_NETWORK_INPUT_DRIFT")
        for root, expected_binding in (
            (self._prepared.source_root, self._plan.predecessor_binding_ref),
            (self._prepared.candidate_root, self._plan.candidate_binding_ref),
        ):
            descriptor = self._root_descriptors[root]
            pinned = self._root_pins[root]
            try:
                facts = os.fstat(descriptor)
                current = root.stat(follow_symlinks=False)
            except OSError as error:
                code = "ROTATION_NETWORK_INPUT_DRIFT"
                raise VaultApplicationRotationError(code) from error
            if (
                not stat.S_ISDIR(facts.st_mode)
                or stat.S_IMODE(facts.st_mode) != _PRIVATE_DIRECTORY_MODE
                or (facts.st_dev, facts.st_ino, facts.st_uid) != pinned
                or (current.st_dev, current.st_ino, current.st_uid) != pinned
                or _snapshot_binding(_credential_snapshot(root)) != expected_binding
            ):
                _fail("ROTATION_NETWORK_INPUT_DRIFT")
            after = os.fstat(descriptor)
            current_after = root.stat(follow_symlinks=False)
            if (after.st_dev, after.st_ino, after.st_uid) != pinned or (
                current_after.st_dev,
                current_after.st_ino,
                current_after.st_uid,
            ) != pinned:
                _fail("ROTATION_NETWORK_INPUT_DRIFT")

    def _run(self, action: str, target: str) -> dict[str, JsonValue]:
        self._validate_effect_inputs()
        raw = self._runner.read(
            (
                "/usr/local/libexec/asklegal-vault-application-rotation-network",
                "--action",
                action,
                "--target",
                target,
                "--plan",
                str(self._plan_path),
                "--authorized-plan-fingerprint",
                self._authorized_plan_fingerprint,
                "--predecessor-directory",
                str(self._prepared.source_root),
                "--candidate-directory",
                str(self._prepared.candidate_root),
                "--root-credential-directory",
                str(self._prepared.source_root),
            ),
            max_bytes=_MAX_DOCUMENT_BYTES,
        )
        if raw is None:
            _fail("ROTATION_NETWORK_PROVIDER_FAILED")
        raw = raw.removesuffix(b"\n")
        try:
            value = parse_json_bytes(raw, max_bytes=_MAX_DOCUMENT_BYTES)
        except (TypeError, ValueError) as error:
            code = "ROTATION_NETWORK_RECEIPT_INVALID"
            raise VaultApplicationRotationError(code) from error
        if type(value) is not dict or canonicalize(checked_json_value(value)) != raw:
            _fail("ROTATION_NETWORK_RECEIPT_INVALID")
        document = cast("dict[str, JsonValue]", value)
        body = dict(document)
        fingerprint = body.pop("fingerprint", None)
        if (
            set(document)
            != {
                "accepted_names",
                "action",
                "application_build_results_fingerprint",
                "candidate_binding_ref",
                "control_plane_candidate_image_id",
                "fingerprint",
                "plan_fingerprint",
                "predecessor_binding_ref",
                "rejected_names",
                "schema_id",
                "schema_version",
                "target",
            }
            or document.get("schema_id")
            != "asklegal.hk-v1-vault-application-rotation-network-receipt"
            or document.get("schema_version") != _VERSION
            or document.get("action") != action
            or document.get("target") != target
            or document.get("plan_fingerprint") != self._prepared.plan.plan_fingerprint
            or document.get("predecessor_binding_ref")
            != self._prepared.plan.predecessor_binding_ref
            or document.get("candidate_binding_ref") != self._prepared.plan.candidate_binding_ref
            or document.get("control_plane_candidate_image_id")
            != self._prepared.plan.control_plane_candidate_image_id
            or document.get("application_build_results_fingerprint")
            != self._prepared.plan.application_build_results_fingerprint
            or fingerprint != _fingerprint(body)
        ):
            _fail("ROTATION_NETWORK_RECEIPT_INVALID")
        return document

    def replace(
        self,
        credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    ) -> None:
        """Converge both vaults to the exact predecessor or candidate set."""
        target = (
            "candidate"
            if credentials == self._prepared.credentials.candidate
            else "predecessor"
            if credentials == self._prepared.credentials.predecessor
            else ""
        )
        if not target:
            _fail("ROTATION_NETWORK_INPUT_INVALID")
        document = self._run("reconcile", target)
        if document.get("accepted_names") != [] or document.get("rejected_names") != []:
            _fail("ROTATION_NETWORK_RECEIPT_INVALID")

    def check(
        self,
        plan: VaultApplicationRotationPlan,
        *,
        binding_ref: str,
        credentials: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
    ) -> AcceptanceReceipt:
        """Probe the exact selected set through both isolated vault networks."""
        if rotation_plan_bytes(plan) != rotation_plan_bytes(self._prepared.plan):
            _fail("ROTATION_PLAN_DRIFT")
        target = (
            "candidate"
            if credentials == self._prepared.credentials.candidate
            and binding_ref == plan.candidate_binding_ref
            else "predecessor"
            if credentials == self._prepared.credentials.predecessor
            and binding_ref == plan.predecessor_binding_ref
            else ""
        )
        if not target:
            _fail("ROTATION_NETWORK_INPUT_INVALID")
        document = self._run("probe", target)
        accepted = document.get("accepted_names")
        rejected = document.get("rejected_names")
        if (
            type(accepted) is not list
            or type(rejected) is not list
            or any(type(item) is not str for item in (*accepted, *rejected))
        ):
            _fail("ROTATION_NETWORK_RECEIPT_INVALID")
        return AcceptanceReceipt(
            plan.plan_fingerprint,
            binding_ref,
            tuple(cast("list[str]", accepted)),
            tuple(cast("list[str]", rejected)),
        )


class TransactionalFlatHostCredentialSet:
    """Root-only, restartable flat sealed-file adapter for the current units."""

    def __init__(
        self,
        sealed_root: Path,
        state_root: Path,
        plan: VaultApplicationRotationPlan,
        *,
        runner: ExactCommandRunner,
        source_root: Path,
        candidate_root: Path,
        runtime_credential_root: Path,
        authorized_plan_fingerprint: str,
        host_owner_uid: int,
        staging_owner_uid: int,
    ) -> None:
        """Bind exact private roots and refuse construction outside root authority."""
        if (
            os.geteuid() != 0
            or type(plan) is not VaultApplicationRotationPlan
            or authorized_plan_fingerprint != plan.plan_fingerprint
        ):
            _fail("LIVE_ROTATION_AUTHORITY_REQUIRED")
        for root in (sealed_root, state_root):
            if (
                not root.is_absolute()
                or root == Path(root.anchor)
                or root.is_symlink()
                or _has_symlink_component(root.parent)
                or not root.is_dir()
                or stat.S_IMODE(root.stat().st_mode) != _PRIVATE_DIRECTORY_MODE
                or root.stat().st_uid != host_owner_uid
            ):
                _fail("LIVE_ROTATION_PATH_INVALID")
        self._sealed_root = sealed_root
        self._state_root = state_root
        self._host_owner_uid = host_owner_uid
        self._plan = _copy_plan(plan)
        self._runner = runner
        self._source_root = source_root
        self._candidate_root = candidate_root
        if (
            not runtime_credential_root.is_absolute()
            or runtime_credential_root.is_symlink()
            or _has_symlink_component(runtime_credential_root.parent)
            or not runtime_credential_root.is_dir()
            or runtime_credential_root.stat().st_uid != host_owner_uid
        ):
            _fail("LIVE_ROTATION_PATH_INVALID")
        self._runtime_credential_root = runtime_credential_root
        self._predecessor_plaintext_sha256 = dict(plan.predecessor_plaintext_sha256)
        self._candidate_plaintext_sha256 = dict(plan.candidate_plaintext_sha256)
        self._work = state_root / plan.rotation_id
        self._predecessor = self._work / "predecessor"
        self._candidate = self._work / "candidate"
        self._journal = self._work / "state.json"
        self._ensure_work_roots()
        journal = self._read_journal() if self._journal.exists() else None
        for root in (source_root, candidate_root):
            if root.is_symlink():
                _fail("LIVE_ROTATION_PATH_INVALID")
            if root.exists():
                if (
                    not root.is_absolute()
                    or root == Path(root.anchor)
                    or root.is_symlink()
                    or _has_symlink_component(root.parent)
                    or not root.is_dir()
                    or stat.S_IMODE(root.stat().st_mode) != _PRIVATE_DIRECTORY_MODE
                    or root.stat().st_uid != staging_owner_uid
                ):
                    _fail("LIVE_ROTATION_PATH_INVALID")
            else:
                phase = journal.get("phase") if journal is not None else None
                allowed_absent = (
                    phase in _CLEANUP_PHASES
                    if root == source_root
                    else phase in {"CLEANING_CANDIDATE", "CLEANED", "TERMINAL"}
                )
                if not allowed_absent:
                    _fail("LIVE_ROTATION_PATH_INVALID")
        self._directory_fds: dict[Path, int] = {}
        self._directory_pins: dict[Path, tuple[int, int]] = {}
        for root, owner in (
            (self._sealed_root, host_owner_uid),
            (self._state_root, host_owner_uid),
            (self._work, host_owner_uid),
            (self._predecessor, host_owner_uid),
            (self._candidate, host_owner_uid),
            (self._runtime_credential_root, host_owner_uid),
        ):
            self._pin_directory(root, owner)
        for root in (self._source_root, self._candidate_root):
            if root.exists():
                self._pin_directory(root, staging_owner_uid)
        for parent in {self._source_root.parent, self._candidate_root.parent}:
            if parent not in self._directory_fds:
                self._pin_directory(parent, staging_owner_uid)
        active_state = self._sealed_state(self._sealed_root)
        if active_state != plan.predecessor_sealed_state_ref:
            journal = self._read_journal()
            if journal.get("phase") not in {
                "STAGED",
                "STOPPED",
                "SWITCHING",
                "SWITCHED",
                "CANDIDATE_ACTIVE",
                "AUTHENTICATION_PROVED",
                "CLEANING_SOURCE",
                "CLEANING_CANDIDATE",
                "CLEANED",
                "TERMINAL",
            } or not self._active_matches_journal(journal, active_state):
                _fail("PREDECESSOR_SEALED_STATE_DRIFT")

    def _pin_directory(self, path: Path, owner_uid: int) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        facts = os.fstat(descriptor)
        path_facts = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(facts.st_mode)
            or stat.S_IMODE(facts.st_mode) != _PRIVATE_DIRECTORY_MODE
            or facts.st_uid != owner_uid
            or (facts.st_dev, facts.st_ino) != (path_facts.st_dev, path_facts.st_ino)
        ):
            os.close(descriptor)
            _fail("LIVE_ROTATION_PATH_INVALID")
        self._directory_fds[path] = descriptor
        self._directory_pins[path] = (facts.st_dev, facts.st_ino)

    def _validate_pins(self) -> None:
        for path, descriptor in self._directory_fds.items():
            facts = os.fstat(descriptor)
            try:
                current = path.stat(follow_symlinks=False)
            except OSError as error:
                code = "LIVE_ROTATION_PATH_DRIFT"
                raise VaultApplicationRotationError(code) from error
            if (facts.st_dev, facts.st_ino) != (
                current.st_dev,
                current.st_ino,
            ) or self._directory_pins[path] != (facts.st_dev, facts.st_ino):
                _fail("LIVE_ROTATION_PATH_DRIFT")

    def _directory_descriptor(self, path: Path) -> int:
        try:
            return self._directory_fds[path]
        except KeyError as error:
            code = "LIVE_ROTATION_PATH_INVALID"
            raise VaultApplicationRotationError(code) from error

    def _exists_at(self, path: Path) -> bool:
        try:
            os.stat(
                path.name,
                dir_fd=self._directory_descriptor(path.parent),
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return False
        return True

    def _sealed_state(self, root: Path) -> str:
        directory = self._directory_descriptor(root)
        rows: list[JsonValue] = []
        for name in _ROTATED_NAMES:
            raw = self._opaque_raw(root / f"{name}.cred")
            facts = os.stat(
                f"{name}.cred",
                dir_fd=directory,
                follow_symlinks=False,
            )
            rows.append(
                {
                    "mode": _SEALED_FILE_MODE,
                    "name": name,
                    "owner_uid": self._host_owner_uid,
                    "sha256": sha256(raw).hexdigest(),
                    "size": facts.st_size,
                }
            )
        return "sealed_" + sha256(canonicalize(checked_json_value(rows))).hexdigest()

    def inspect_predecessor(self, credential_names: tuple[str, ...]) -> str:
        """Return the constructor-bound predecessor state."""
        if credential_names != _ROTATED_NAMES:
            _fail("PREDECESSOR_SEALED_STATE_INVALID")
        return self._plan.predecessor_sealed_state_ref

    def _ensure_work_roots(self) -> None:
        for root in (self._work, self._predecessor, self._candidate):
            try:
                root.mkdir(mode=_PRIVATE_DIRECTORY_MODE)
            except FileExistsError:
                pass
            if (
                root.is_symlink()
                or not root.is_dir()
                or stat.S_IMODE(root.stat().st_mode) != _PRIVATE_DIRECTORY_MODE
                or root.stat().st_uid != self._host_owner_uid
            ):
                _fail("LIVE_ROTATION_STATE_INVALID")
        if self._journal.exists():
            document = self._read_journal()
            if document.get("plan_fingerprint") != self._plan.plan_fingerprint:
                _fail("LIVE_ROTATION_STATE_DRIFT")

    def _read_journal(self) -> dict[str, JsonValue]:
        try:
            if hasattr(self, "_directory_fds") and self._work in self._directory_fds:
                descriptor = os.open(
                    "state.json",
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=self._directory_descriptor(self._work),
                )
                try:
                    facts = os.fstat(descriptor)
                    raw = os.pread(descriptor, facts.st_size, 0)
                finally:
                    os.close(descriptor)
            else:
                raw = self._journal.read_bytes()
            value = parse_json_bytes(raw, max_bytes=_MAX_DOCUMENT_BYTES)
        except (OSError, TypeError, ValueError) as error:
            code = "LIVE_ROTATION_STATE_INVALID"
            raise VaultApplicationRotationError(code) from error
        if type(value) is not dict:
            _fail("LIVE_ROTATION_STATE_INVALID")
        document = cast("dict[str, JsonValue]", value)
        phase = document.get("phase")
        switched = document.get("switched_names")
        if (
            set(document)
            != {
                "acceptance_proved",
                "phase",
                "plan_fingerprint",
                "schema_id",
                "schema_version",
                "switched_names",
            }
            or type(document.get("acceptance_proved")) is not bool
            or type(phase) is not str
            or phase
            not in {
                "STAGED",
                "STOPPED",
                "SWITCHING",
                "SWITCHED",
                "CANDIDATE_ACTIVE",
                "AUTHENTICATION_PROVED",
                "CLEANING_SOURCE",
                "CLEANING_CANDIDATE",
                "CLEANED",
                "TERMINAL",
                "PREDECESSOR_ACTIVE",
                "ROLLED_BACK",
            }
            or type(switched) is not list
            or any(type(item) is not str for item in switched)
            or cast("list[str]", switched)
            != list(_ROTATED_NAMES[: len(cast("list[str]", switched))])
            or (phase == "SWITCHING" and not switched)
            or (
                phase
                in {
                    "SWITCHED",
                    "CANDIDATE_ACTIVE",
                    "AUTHENTICATION_PROVED",
                    "CLEANING_SOURCE",
                    "CLEANING_CANDIDATE",
                    "CLEANED",
                    "TERMINAL",
                }
                and switched != list(_ROTATED_NAMES)
            )
            or (
                document.get("acceptance_proved") is True
                and phase
                not in {
                    "AUTHENTICATION_PROVED",
                    "CLEANING_SOURCE",
                    "CLEANING_CANDIDATE",
                    "CLEANED",
                    "TERMINAL",
                }
            )
            or document.get("schema_id") != _LIVE_STATE_SCHEMA
            or document.get("schema_version") != _VERSION
            or canonicalize(checked_json_value(document)) != raw
        ):
            _fail("LIVE_ROTATION_STATE_INVALID")
        return document

    def _write_journal(
        self,
        phase: str,
        switched: tuple[str, ...] | None = None,
        *,
        acceptance_proved: bool | None = None,
    ) -> None:
        previous = self._read_journal() if self._journal.exists() else None
        if switched is None:
            switched = (
                tuple(cast("list[str]", previous["switched_names"])) if previous is not None else ()
            )
        if acceptance_proved is None:
            acceptance_proved = previous is not None and previous.get("acceptance_proved") is True
        raw = canonicalize(
            checked_json_value(
                {
                    "phase": phase,
                    "acceptance_proved": acceptance_proved,
                    "plan_fingerprint": self._plan.plan_fingerprint,
                    "schema_id": _LIVE_STATE_SCHEMA,
                    "schema_version": _VERSION,
                    "switched_names": list(switched),
                }
            )
        )
        work = self._directory_descriptor(self._work)
        temporary = f".state.{token_urlsafe(18)}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
            dir_fd=work,
        )
        try:
            view = memoryview(raw)
            offset = 0
            while offset < len(view):
                count = os.write(descriptor, view[offset:])
                if count < 1:
                    _fail("LIVE_ROTATION_STATE_INVALID")
                offset += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.rename(
            temporary,
            "state.json",
            src_dir_fd=work,
            dst_dir_fd=work,
        )
        os.fsync(work)

    def _opaque_raw(self, path: Path) -> bytes:
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=self._directory_descriptor(path.parent),
        )
        try:
            facts = os.fstat(descriptor)
            if (
                not stat.S_ISREG(facts.st_mode)
                or stat.S_IMODE(facts.st_mode) != _SEALED_FILE_MODE
                or facts.st_uid != self._host_owner_uid
                or not 1 <= facts.st_size <= _MAX_SEALED_BYTES
            ):
                _fail("SEALED_CREDENTIAL_INVALID")
            raw = os.pread(descriptor, facts.st_size, 0)
            after = os.fstat(descriptor)
            if (
                len(raw) != facts.st_size
                or after.st_dev != facts.st_dev
                or after.st_ino != facts.st_ino
                or after.st_size != facts.st_size
                or after.st_mtime_ns != facts.st_mtime_ns
            ):
                _fail("SEALED_CREDENTIAL_INVALID")
            return raw
        finally:
            os.close(descriptor)

    def _active_matches_journal(self, journal: dict[str, JsonValue], active_state: str) -> bool:
        try:
            if self._sealed_state(self._candidate) == active_state:
                return True
            switched = frozenset(cast("list[str]", journal["switched_names"]))
            return all(
                self._opaque_raw(self._sealed_root / f"{name}.cred")
                == self._opaque_raw(
                    (self._candidate if name in switched else self._predecessor) / f"{name}.cred"
                )
                for name in _ROTATED_NAMES
            )
        except OSError, VaultApplicationRotationError:
            return False

    def _copy_sealed(self, source: Path, destination: Path) -> None:
        source_directory = self._directory_descriptor(source.parent)
        destination_directory = self._directory_descriptor(destination.parent)
        descriptor = os.open(
            source.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=source_directory,
        )
        try:
            facts = os.fstat(descriptor)
            if (
                not stat.S_ISREG(facts.st_mode)
                or stat.S_IMODE(facts.st_mode) != _SEALED_FILE_MODE
                or facts.st_uid != self._host_owner_uid
                or not 1 <= facts.st_size <= _MAX_SEALED_BYTES
            ):
                _fail("SEALED_CREDENTIAL_INVALID")
            chunks: list[bytes] = []
            remaining = facts.st_size
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    _fail("SEALED_CREDENTIAL_INVALID")
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            if (
                after.st_dev != facts.st_dev
                or after.st_ino != facts.st_ino
                or after.st_size != facts.st_size
                or after.st_mtime_ns != facts.st_mtime_ns
            ):
                _fail("SEALED_CREDENTIAL_INVALID")
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
        temporary = f".{destination.name}.{token_urlsafe(18)}.tmp"
        output_descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            _SEALED_FILE_MODE,
            dir_fd=destination_directory,
        )
        try:
            view = memoryview(raw)
            offset = 0
            while offset < len(view):
                count = os.write(output_descriptor, view[offset:])
                if count < 1:
                    _fail("SEALED_CREDENTIAL_INVALID")
                offset += count
            os.fsync(output_descriptor)
        finally:
            os.close(output_descriptor)
        os.rename(
            temporary,
            destination.name,
            src_dir_fd=destination_directory,
            dst_dir_fd=destination_directory,
        )

    def _bound(self, plan: VaultApplicationRotationPlan) -> None:
        if rotation_plan_bytes(plan) != rotation_plan_bytes(self._plan):
            _fail("ROTATION_PLAN_DRIFT")

    def stage_candidate(
        self, plan: VaultApplicationRotationPlan, candidate_root: Path
    ) -> BoundReceipt:
        """Retain all seven predecessors and seal all candidates before downtime."""
        self._bound(plan)
        self._validate_pins()
        if candidate_root != self._candidate_root:
            _fail("CANDIDATE_ROOT_DRIFT")
        journal = self._read_journal() if self._journal.exists() else None
        if journal is not None and journal.get("phase") in {
            "SWITCHING",
            "SWITCHED",
            "CANDIDATE_ACTIVE",
            "AUTHENTICATION_PROVED",
            "CLEANING_SOURCE",
            "CLEANING_CANDIDATE",
            "CLEANED",
            "TERMINAL",
        }:
            return BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)
        for name in _ROTATED_NAMES:
            predecessor = self._predecessor / f"{name}.cred"
            if not self._exists_at(predecessor):
                self._copy_sealed(self._sealed_root / f"{name}.cred", predecessor)
            candidate = self._candidate / f"{name}.cred"
            if not self._exists_at(candidate):
                self._seal_bound_candidate(name, candidate)
            self._opaque_raw(candidate)
            os.chmod(
                candidate.name,
                _SEALED_FILE_MODE,
                dir_fd=self._directory_descriptor(candidate.parent),
                follow_symlinks=False,
            )
        if journal is None or journal.get("phase") != "STOPPED":
            self._write_journal("STAGED")
        return BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)

    def _seal_bound_candidate(self, name: str, output: Path) -> None:
        source = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=self._directory_descriptor(self._candidate_root),
        )
        try:
            facts = os.fstat(source)
            if (
                not stat.S_ISREG(facts.st_mode)
                or stat.S_IMODE(facts.st_mode) != _PRIVATE_FILE_MODE
                or not 1 <= facts.st_size <= _MAX_SEALED_BYTES
            ):
                _fail("CANDIDATE_PLAINTEXT_DRIFT")
            before = os.pread(source, facts.st_size, 0)
            if (
                len(before) != facts.st_size
                or sha256(before).hexdigest() != self._candidate_plaintext_sha256[name]
                or not self._runner.seal(
                    name,
                    source,
                    Path(
                        f"/proc/self/fd/{self._directory_descriptor(output.parent)}/{output.name}"
                    ),
                )
            ):
                _fail("CANDIDATE_PLAINTEXT_DRIFT")
            after_facts = os.fstat(source)
            after = os.pread(source, facts.st_size, 0)
            if (
                after != before
                or after_facts.st_size != facts.st_size
                or after_facts.st_mtime_ns != facts.st_mtime_ns
                or after_facts.st_ino != facts.st_ino
                or after_facts.st_dev != facts.st_dev
            ):
                _fail("CANDIDATE_PLAINTEXT_DRIFT")
        finally:
            os.close(source)

    def stop_and_check(self, plan: VaultApplicationRotationPlan) -> UnitStopReceipt:
        """Stop and prove inactive exactly the five application services."""
        self._bound(plan)
        self._validate_pins()
        stopped = self._runner.run(("/usr/bin/systemctl", "stop", *plan.dependent_units))
        stopped = stopped and all(
            self._runner.read(
                (
                    "/usr/bin/systemctl",
                    "show",
                    "--property=ActiveState",
                    "--value",
                    unit,
                ),
                max_bytes=32,
            )
            == b"inactive\n"
            for unit in plan.dependent_units
        )
        if stopped:
            journal = self._read_journal() if self._journal.exists() else None
            if journal is None or journal.get("phase") not in {
                "SWITCHING",
                "SWITCHED",
                "CANDIDATE_ACTIVE",
                "AUTHENTICATION_PROVED",
                "CLEANING_SOURCE",
                "CLEANING_CANDIDATE",
                "CLEANED",
                "TERMINAL",
            }:
                self._write_journal("STOPPED")
        return UnitStopReceipt(plan.plan_fingerprint, plan.dependent_units, stopped)

    def switch_candidate(
        self, plan: VaultApplicationRotationPlan, staged: BoundReceipt
    ) -> BoundReceipt:
        """Promote each staged blob with a per-file restartable journal."""
        self._bound(plan)
        self._validate_pins()
        if not _matches(staged, plan, plan.candidate_binding_ref):
            _fail("RECEIPT_MISMATCH")
        journal = self._read_journal() if self._journal.exists() else None
        if journal is not None and journal.get("phase") in {
            "SWITCHED",
            "CANDIDATE_ACTIVE",
            "AUTHENTICATION_PROVED",
            "CLEANING_SOURCE",
            "CLEANING_CANDIDATE",
            "CLEANED",
            "TERMINAL",
        }:
            return BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)
        switched: list[str] = []
        for name in _ROTATED_NAMES:
            rebound = self._candidate / f".{name}.rebound.cred"
            self._seal_bound_candidate(name, rebound)
            candidate_directory = self._directory_descriptor(self._candidate)
            os.chmod(
                rebound.name,
                _SEALED_FILE_MODE,
                dir_fd=candidate_directory,
                follow_symlinks=False,
            )
            os.rename(
                rebound.name,
                f"{name}.cred",
                src_dir_fd=candidate_directory,
                dst_dir_fd=candidate_directory,
            )
            self._copy_sealed(
                self._candidate / f"{name}.cred",
                self._sealed_root / f"{name}.cred",
            )
            switched.append(name)
            self._write_journal("SWITCHING", tuple(switched))
        self._write_journal("SWITCHED", tuple(switched))
        return BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)

    def restart_and_check(
        self, plan: VaultApplicationRotationPlan, *, binding_ref: str
    ) -> UnitReceipt:
        """Restart exact applications and require every ActiveState readback."""
        self._bound(plan)
        self._validate_pins()
        if binding_ref not in {plan.predecessor_binding_ref, plan.candidate_binding_ref}:
            _fail("BINDING_REF_INVALID")
        healthy = self._runner.run(("/usr/bin/systemctl", "restart", *plan.dependent_units))
        healthy = healthy and all(
            self._runner.read(
                (
                    "/usr/bin/systemctl",
                    "show",
                    "--property=ActiveState",
                    "--value",
                    unit,
                ),
                max_bytes=32,
            )
            == b"active\n"
            for unit in plan.dependent_units
        )
        expected = (
            self._candidate_plaintext_sha256
            if binding_ref == plan.candidate_binding_ref
            else self._predecessor_plaintext_sha256
        )
        healthy = healthy and self._runtime_credentials_match(expected)
        if healthy:
            phase = (
                "CANDIDATE_ACTIVE"
                if binding_ref == plan.candidate_binding_ref
                else "PREDECESSOR_ACTIVE"
            )
            journal = self._read_journal() if self._journal.exists() else None
            if journal is None or journal.get("phase") not in {
                "AUTHENTICATION_PROVED",
                "CLEANING_SOURCE",
                "CLEANING_CANDIDATE",
                "CLEANED",
                "TERMINAL",
            }:
                self._write_journal(phase)
        return UnitReceipt(plan.plan_fingerprint, binding_ref, plan.dependent_units, healthy)

    def _runtime_credentials_match(self, expected: dict[str, str]) -> bool:
        try:
            runtime = self._directory_descriptor(self._runtime_credential_root)
            for name, units in _CREDENTIAL_UNITS:
                service = units[0].removeprefix("asklegal-").removesuffix(".service")
                service_descriptor = os.open(
                    service,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=runtime,
                )
                try:
                    service_facts = os.fstat(service_descriptor)
                    if (
                        not stat.S_ISDIR(service_facts.st_mode)
                        or service_facts.st_uid != self._host_owner_uid
                    ):
                        return False
                    descriptor = os.open(
                        name,
                        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                        dir_fd=service_descriptor,
                    )
                    facts = os.fstat(descriptor)
                    try:
                        if (
                            not stat.S_ISREG(facts.st_mode)
                            or stat.S_IMODE(facts.st_mode) != _SEALED_FILE_MODE
                            or facts.st_uid != self._host_owner_uid
                            or not 1 <= facts.st_size <= _MAX_SEALED_BYTES
                        ):
                            return False
                        raw = os.pread(descriptor, facts.st_size, 0)
                        after = os.fstat(descriptor)
                        if (
                            len(raw) != facts.st_size
                            or sha256(raw).hexdigest() != expected[name]
                            or after.st_dev != facts.st_dev
                            or after.st_ino != facts.st_ino
                            or after.st_size != facts.st_size
                            or after.st_mtime_ns != facts.st_mtime_ns
                        ):
                            return False
                    finally:
                        os.close(descriptor)
                finally:
                    os.close(service_descriptor)
        except OSError:
            return False
        return True

    def record_acceptance(self, plan: VaultApplicationRotationPlan) -> BoundReceipt:
        """Persist the exact dual authentication proof before destructive cleanup."""
        self._bound(plan)
        self._validate_pins()
        journal = self._read_journal() if self._journal.exists() else None
        if journal is None or journal.get("phase") not in _CLEANUP_PHASES:
            self._write_journal("AUTHENTICATION_PROVED", _ROTATED_NAMES, acceptance_proved=True)
        return BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)

    def _remove_exact_plaintext(self, root: Path) -> bool:
        if root not in self._directory_fds:
            return not self._exists_at(root)
        try:
            directory = self._directory_descriptor(root)
            entries = tuple(sorted(os.listdir(directory)))  # noqa: PTH208
            if not frozenset(entries) <= frozenset(deployment_credential_names()):
                return False
            for name in entries:
                descriptor = os.open(
                    name,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=directory,
                )
                try:
                    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                        return False
                finally:
                    os.close(descriptor)
            for name in entries:
                os.unlink(name, dir_fd=directory)
            parent = self._directory_descriptor(root.parent)
            bound = os.fstat(directory)
            current = os.stat(root.name, dir_fd=parent, follow_symlinks=False)
            if (bound.st_dev, bound.st_ino) != (current.st_dev, current.st_ino):
                _fail("LIVE_ROTATION_PATH_DRIFT")
            os.rmdir(root.name, dir_fd=parent)
            os.close(directory)
            del self._directory_fds[root]
            del self._directory_pins[root]
        except OSError:
            return False
        return not self._exists_at(root)

    def finalize_success(
        self, plan: VaultApplicationRotationPlan, switched: BoundReceipt
    ) -> HostCleanupReceipt:
        """Remove plaintext while retaining sealed rollback until report durability."""
        self._bound(plan)
        self._validate_pins()
        if not _matches(switched, plan, plan.candidate_binding_ref):
            _fail("RECEIPT_MISMATCH")
        journal = self._read_journal()
        if journal.get("phase") == "TERMINAL":
            return HostCleanupReceipt(
                plan_fingerprint=plan.plan_fingerprint,
                predecessor_sealed_absent=True,
                predecessor_plaintext_absent=True,
                candidate_plaintext_absent=True,
            )
        if journal.get("phase") == "CLEANED":
            return HostCleanupReceipt(
                plan.plan_fingerprint,
                not self._predecessor.exists(),
                not self._exists_at(self._source_root),
                not self._exists_at(self._candidate_root),
            )
        if (
            journal.get("phase")
            not in {"AUTHENTICATION_PROVED", "CLEANING_SOURCE", "CLEANING_CANDIDATE"}
            or journal.get("acceptance_proved") is not True
        ):
            _fail("ACCEPTANCE_NOT_PROVED")
        if journal.get("phase") == "AUTHENTICATION_PROVED":
            self._write_journal("CLEANING_SOURCE", _ROTATED_NAMES, acceptance_proved=True)
        source_absent = self._remove_exact_plaintext(self._source_root)
        if not source_absent:
            return HostCleanupReceipt(
                plan_fingerprint=plan.plan_fingerprint,
                predecessor_sealed_absent=not self._predecessor.exists(),
                predecessor_plaintext_absent=False,
                candidate_plaintext_absent=not self._exists_at(self._candidate_root),
            )
        journal = self._read_journal()
        if journal.get("phase") != "CLEANING_CANDIDATE":
            self._write_journal("CLEANING_CANDIDATE", _ROTATED_NAMES, acceptance_proved=True)
        candidate_absent = self._remove_exact_plaintext(self._candidate_root)
        predecessor_absent = not self._predecessor.exists()
        if source_absent and candidate_absent:
            self._write_journal("CLEANED", _ROTATED_NAMES, acceptance_proved=True)
        return HostCleanupReceipt(
            plan.plan_fingerprint,
            predecessor_absent,
            source_absent,
            candidate_absent,
        )

    def restore_predecessor(self, plan: VaultApplicationRotationPlan) -> HostRollbackReceipt:
        """Restore every old sealed blob before discarding candidate material."""
        self._bound(plan)
        self._validate_pins()
        restored = True
        try:
            for name in _ROTATED_NAMES:
                self._copy_sealed(
                    self._predecessor / f"{name}.cred",
                    self._sealed_root / f"{name}.cred",
                )
        except OSError, VaultApplicationRotationError:
            restored = False
        if restored:
            try:
                restored = (
                    self._sealed_state(self._sealed_root) == plan.predecessor_sealed_state_ref
                )
            except OSError, VaultApplicationRotationError:
                restored = False
        candidate_sealed_absent = False
        candidate_plaintext_absent = False
        if restored:
            try:
                candidate_directory = self._directory_descriptor(self._candidate)
                for name in _ROTATED_NAMES:
                    try:
                        os.unlink(f"{name}.cred", dir_fd=candidate_directory)
                    except FileNotFoundError:
                        pass
                os.rmdir("candidate", dir_fd=self._directory_descriptor(self._work))
                candidate_sealed_absent = True
            except OSError:
                pass
            candidate_plaintext_absent = self._remove_exact_plaintext(self._candidate_root)
        if restored and candidate_sealed_absent and candidate_plaintext_absent:
            self._write_journal("ROLLED_BACK", acceptance_proved=False)
        return HostRollbackReceipt(
            plan.plan_fingerprint,
            restored,
            candidate_sealed_absent,
            candidate_plaintext_absent,
        )

    def retire_predecessor_after_report(
        self, plan: VaultApplicationRotationPlan, report_path: Path
    ) -> BoundReceipt:
        """Delete old sealed rollback only after an exact durable success report."""
        self._bound(plan)
        self._validate_pins()
        if (
            not report_path.is_absolute()
            or report_path.parent != self._state_root
            or report_path.is_symlink()
            or _has_symlink_component(report_path.parent)
            or not report_path.is_file()
            or stat.S_IMODE(report_path.stat().st_mode) != _PRIVATE_FILE_MODE
        ):
            _fail("ROTATION_REPORT_INVALID")
        report_descriptor = os.open(
            report_path.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=self._directory_descriptor(self._state_root),
        )
        try:
            facts = os.fstat(report_descriptor)
            if (
                stat.S_IMODE(facts.st_mode) != _PRIVATE_FILE_MODE
                or facts.st_uid != self._host_owner_uid
            ):
                _fail("ROTATION_REPORT_INVALID")
            report_raw = os.pread(report_descriptor, facts.st_size, 0)
        finally:
            os.close(report_descriptor)
        report = parse_succeeded_rotation_report_bytes(report_raw)
        journal = self._read_journal()
        if (
            report.plan_fingerprint != plan.plan_fingerprint
            or report.rotation_id != plan.rotation_id
            or journal.get("phase") not in {"CLEANED", "TERMINAL"}
            or journal.get("acceptance_proved") is not True
            or self._exists_at(self._source_root)
            or self._exists_at(self._candidate_root)
        ):
            _fail("ROTATION_REPORT_INVALID")
        try:
            if self._exists_at(self._predecessor):
                predecessor_directory = self._directory_descriptor(self._predecessor)
                for name in _ROTATED_NAMES:
                    try:
                        os.unlink(f"{name}.cred", dir_fd=predecessor_directory)
                    except FileNotFoundError:
                        pass
                os.rmdir("predecessor", dir_fd=self._directory_descriptor(self._work))
        except OSError as error:
            code = "PREDECESSOR_RETIREMENT_FAILED"
            raise VaultApplicationRotationError(code) from error
        self._write_journal("TERMINAL", _ROTATED_NAMES, acceptance_proved=True)
        return BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)

    def retain_succeeded_report(
        self,
        plan: VaultApplicationRotationPlan,
        report_path: Path,
        report: VaultApplicationRotationReport,
    ) -> None:
        """Write the success report through the pinned root-owned state descriptor."""
        self._bound(plan)
        self._validate_pins()
        raw = rotation_report_bytes(report)
        if (
            report_path.parent != self._state_root
            or parse_succeeded_rotation_report_bytes(raw) != report
        ):
            _fail("ROTATION_REPORT_INVALID")
        state = self._directory_descriptor(self._state_root)
        try:
            existing = os.open(
                report_path.name,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=state,
            )
        except FileNotFoundError:
            existing = None
        if existing is not None:
            try:
                facts = os.fstat(existing)
                current = os.pread(existing, facts.st_size, 0)
                if (
                    stat.S_IMODE(facts.st_mode) != _PRIVATE_FILE_MODE
                    or facts.st_uid != self._host_owner_uid
                    or current != raw
                ):
                    _fail("ROTATION_REPORT_INVALID")
            finally:
                os.close(existing)
            return
        temporary = f".{report_path.name}.{token_urlsafe(18)}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
            dir_fd=state,
        )
        try:
            view = memoryview(raw)
            offset = 0
            while offset < len(view):
                count = os.write(descriptor, view[offset:])
                if count < 1:
                    _fail("ROTATION_REPORT_INVALID")
                offset += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(
                temporary,
                report_path.name,
                src_dir_fd=state,
                dst_dir_fd=state,
                follow_symlinks=False,
            )
        finally:
            os.unlink(temporary, dir_fd=state)

    def prove_succeeded_after_cleanup(
        self, plan: VaultApplicationRotationPlan
    ) -> VaultApplicationRotationReport:
        """Reconstruct terminal success after a crash between cleanup and report."""
        self._bound(plan)
        self._validate_pins()
        journal = self._read_journal()
        try:
            active = self._sealed_state(self._sealed_root)
            candidate = self._sealed_state(self._candidate)
        except (OSError, VaultApplicationRotationError) as error:
            code = "TERMINAL_SUCCESS_NOT_PROVED"
            raise VaultApplicationRotationError(code) from error
        if (
            journal.get("phase") not in {"CLEANED", "TERMINAL"}
            or journal.get("acceptance_proved") is not True
            or journal.get("switched_names") != list(_ROTATED_NAMES)
            or self._exists_at(self._source_root)
            or self._exists_at(self._candidate_root)
            or active != candidate
            or not self._runtime_credentials_match(self._candidate_plaintext_sha256)
        ):
            _fail("TERMINAL_SUCCESS_NOT_PROVED")
        return _report(
            plan,
            state=RotationState.SUCCEEDED,
            blockers=(),
            new_values_accepted=True,
            old_values_rejected=True,
            plaintext_absent=True,
        )


def _fingerprint(body: dict[str, JsonValue]) -> str:
    return "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def _plan_body(
    *,
    rotation_id: str,
    staging_receipt_fingerprint: str,
    predecessor_binding_ref: str,
    candidate_binding_ref: str,
    predecessor_sealed_state_ref: str,
    control_plane_candidate_image_id: str,
    application_build_results_fingerprint: str | None,
    predecessor_plaintext_sha256: tuple[tuple[str, str], ...],
    candidate_plaintext_sha256: tuple[tuple[str, str], ...],
) -> dict[str, JsonValue]:
    return {
        "candidate_binding_ref": candidate_binding_ref,
        "control_plane_candidate_image_id": control_plane_candidate_image_id,
        "application_build_results_fingerprint": application_build_results_fingerprint,
        "candidate_plaintext_sha256": cast(
            "list[JsonValue]",
            [
                {"credential_name": name, "sha256": digest}
                for name, digest in candidate_plaintext_sha256
            ],
        ),
        "predecessor_plaintext_sha256": cast(
            "list[JsonValue]",
            [
                {"credential_name": name, "sha256": digest}
                for name, digest in predecessor_plaintext_sha256
            ],
        ),
        "credential_units": cast(
            "list[JsonValue]",
            [
                {"credential_name": name, "dependent_units": list(units)}
                for name, units in _CREDENTIAL_UNITS
            ],
        ),
        "dependent_units": cast("list[JsonValue]", list(_DEPENDENT_UNITS)),
        "predecessor_binding_ref": predecessor_binding_ref,
        "predecessor_sealed_state_ref": predecessor_sealed_state_ref,
        "rotated_credential_names": cast("list[JsonValue]", list(_ROTATED_NAMES)),
        "rotation_id": rotation_id,
        "sealed_credential_names": cast("list[JsonValue]", list(_ROTATED_NAMES)),
        "staging_receipt_fingerprint": staging_receipt_fingerprint,
    }


def _copy_plan(plan: VaultApplicationRotationPlan) -> VaultApplicationRotationPlan:
    """Detach the trusted binding from any adapter-mutated object reference."""
    return VaultApplicationRotationPlan(
        rotation_id=plan.rotation_id,
        staging_receipt_fingerprint=plan.staging_receipt_fingerprint,
        predecessor_binding_ref=plan.predecessor_binding_ref,
        candidate_binding_ref=plan.candidate_binding_ref,
        predecessor_sealed_state_ref=plan.predecessor_sealed_state_ref,
        control_plane_candidate_image_id=plan.control_plane_candidate_image_id,
        application_build_results_fingerprint=plan.application_build_results_fingerprint,
        sealed_credential_names=plan.sealed_credential_names,
        rotated_credential_names=plan.rotated_credential_names,
        credential_units=plan.credential_units,
        dependent_units=plan.dependent_units,
        predecessor_plaintext_sha256=plan.predecessor_plaintext_sha256,
        candidate_plaintext_sha256=plan.candidate_plaintext_sha256,
        plan_fingerprint=plan.plan_fingerprint,
    )


def _parse_credential(raw: bytes) -> S3AccessCredential:
    try:
        return S3AccessCredential.from_bytes(raw)
    except (S3VaultError, ValueError) as error:
        code = "STAGING_CREDENTIAL_INVALID"
        raise VaultApplicationRotationError(code) from error


def _credential_groups(root: Path) -> tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...]:
    return (
        (
            VaultName.PRIMARY,
            tuple(_parse_credential((root / name).read_bytes()) for name in _PRIMARY_NAMES),
        ),
        (
            VaultName.RECOVERY,
            tuple(_parse_credential((root / name).read_bytes()) for name in _RECOVERY_NAMES),
        ),
    )


def _credential_snapshot(root: Path) -> dict[str, bytes]:
    """Read the exact full set from stable no-follow descriptors."""
    values: dict[str, bytes] = {}
    if tuple(sorted(item.name for item in root.iterdir())) != deployment_credential_names():
        _fail("STAGING_CREDENTIAL_INVALID")
    for name in deployment_credential_names():
        descriptor = os.open(root / name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            facts = os.fstat(descriptor)
            if (
                not stat.S_ISREG(facts.st_mode)
                or stat.S_IMODE(facts.st_mode) != _PRIVATE_FILE_MODE
                or not 1 <= facts.st_size <= _MAX_SEALED_BYTES
            ):
                _fail("STAGING_CREDENTIAL_INVALID")
            raw = os.pread(descriptor, facts.st_size, 0)
            after = os.fstat(descriptor)
            if (
                len(raw) != facts.st_size
                or after.st_dev != facts.st_dev
                or after.st_ino != facts.st_ino
                or after.st_size != facts.st_size
                or after.st_mtime_ns != facts.st_mtime_ns
            ):
                _fail("STAGING_CREDENTIAL_INVALID")
            values[name] = raw
        finally:
            os.close(descriptor)
    return values


def _snapshot_binding(values: dict[str, bytes]) -> str:
    inventory: list[JsonValue] = [
        {"name": name, "sha256": sha256(raw).hexdigest(), "size": len(raw)}
        for name, raw in sorted(values.items())
    ]
    return "binding_" + sha256(canonicalize(checked_json_value(inventory))).hexdigest()[:48]


def _access_sets(
    groups: tuple[tuple[VaultName, tuple[S3AccessCredential, ...]], ...],
) -> tuple[tuple[VaultName, tuple[str, ...]], ...]:
    return tuple(
        (vault, tuple(item.reveal_for_client()[0] for item in credentials))
        for vault, credentials in groups
    )


def _candidate_image_provenance(
    *, build_results_path: Path, image_inputs_path: Path, workspace_root: Path
) -> tuple[str, str]:
    """Derive the control-plane image ID from exact source-bound build results."""
    try:
        build_raw = build_results_path.read_bytes()
        inputs_raw = image_inputs_path.read_bytes()
        build_value = parse_json_bytes(build_raw, max_bytes=1_000_000)
        inputs_value = json.loads(inputs_raw)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = "APPLICATION_BUILD_RESULTS_INVALID"
        raise VaultApplicationRotationError(code) from error
    if type(build_value) is not dict or type(inputs_value) is not dict:
        _fail("APPLICATION_BUILD_RESULTS_INVALID")
    build = cast("dict[str, JsonValue]", build_value)
    inputs = cast("dict[str, object]", inputs_value)
    if (
        set(build)
        != {
            "application_image_inputs_fingerprint",
            "fingerprint",
            "images",
            "schema_id",
            "schema_version",
        }
        or build.get("schema_id") != _BUILD_RESULTS_SCHEMA
        or build.get("schema_version") != _VERSION
        or canonicalize(checked_json_value(build)) + b"\n" != build_raw
    ):
        _fail("APPLICATION_BUILD_RESULTS_INVALID")
    unsigned = dict(build)
    supplied = unsigned.pop("fingerprint")
    expected_inputs = _fingerprint(
        {
            "application_image_inputs": checked_json_value(inputs),
            "workspace_source_fingerprint": workspace_source_fingerprint(workspace_root),
        }
    )
    if (
        supplied != _fingerprint(unsigned)
        or build.get("application_image_inputs_fingerprint") != expected_inputs
    ):
        _fail("APPLICATION_BUILD_RESULTS_INVALID")
    raw_images = build.get("images")
    declared_images = inputs.get("images")
    if type(raw_images) is not list or type(declared_images) is not list:
        _fail("APPLICATION_BUILD_RESULTS_INVALID")
    expected_paths: dict[str, str] = {}
    for raw in cast("list[object]", declared_images):
        if type(raw) is not dict:
            _fail("APPLICATION_BUILD_RESULTS_INVALID")
        item = cast("dict[object, object]", raw)
        service = item.get("artifact_id")
        path = item.get("application_path")
        if type(service) is not str or type(path) is not str or service in expected_paths:
            _fail("APPLICATION_BUILD_RESULTS_INVALID")
        expected_paths[service] = path
    results: dict[str, str] = {}
    for raw in raw_images:
        if type(raw) is not dict or set(raw) != {
            "application_path",
            "image_id",
            "installed_tree_sha512",
            "service_id",
            "tag",
        }:
            _fail("APPLICATION_BUILD_RESULTS_INVALID")
        service = raw.get("service_id")
        path = raw.get("application_path")
        image_id = raw.get("image_id")
        tree = raw.get("installed_tree_sha512")
        tag = raw.get("tag")
        if (
            type(service) is not str
            or service in results
            or expected_paths.get(service) != path
            or tag != f"asklegal/{service}:hk-v1-candidate"
            or type(image_id) is not str
            or _IMAGE_ID.fullmatch(image_id) is None
            or type(tree) is not str
            or re.fullmatch(r"[0-9a-f]{128}", tree) is None
        ):
            _fail("APPLICATION_BUILD_RESULTS_INVALID")
        results[service] = image_id
    if tuple(sorted(results)) != _APPLICATION_SERVICES:
        _fail("APPLICATION_BUILD_RESULTS_INVALID")
    return results["control-plane"], "sha256:" + sha256(build_raw).hexdigest()


def _staging_receipt_binding(receipt_path: Path) -> _StagingReceiptBinding:
    """Parse the immutable value-free receipt even after its roots are retired."""
    if receipt_path.is_symlink() or not receipt_path.is_file():
        _fail("STAGING_RECEIPT_INVALID")
    raw = receipt_path.read_bytes()
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX_DOCUMENT_BYTES)
    except (TypeError, ValueError) as error:
        code = "STAGING_RECEIPT_INVALID"
        raise VaultApplicationRotationError(code) from error
    if type(value) is not dict:
        _fail("STAGING_RECEIPT_INVALID")
    document = cast("dict[str, JsonValue]", value)
    expected_keys = {
        "candidate_binding_ref",
        "candidate_root",
        "credential_names",
        "fingerprint",
        "predecessor_binding_ref",
        "rotated_credential_count",
        "rotation_id",
        "schema_id",
        "schema_version",
        "source_root",
        "unchanged_credential_count",
    }
    fingerprint = document.get("fingerprint")
    body = {key: item for key, item in document.items() if key != "fingerprint"}
    if (
        set(document) != expected_keys
        or document.get("schema_id") != _STAGING_SCHEMA
        or document.get("schema_version") != _VERSION
        or document.get("credential_names") != list(_ROTATED_NAMES)
        or document.get("rotated_credential_count") != len(_ROTATED_NAMES)
        or document.get("unchanged_credential_count")
        != len(deployment_credential_names()) - len(_ROTATED_NAMES)
        or type(fingerprint) is not str
        or _FINGERPRINT.fullmatch(fingerprint) is None
        or fingerprint != _fingerprint(body)
        or canonicalize(checked_json_value(document)) != raw
    ):
        _fail("STAGING_RECEIPT_INVALID")
    rotation_id = document.get("rotation_id")
    predecessor_ref = document.get("predecessor_binding_ref")
    candidate_ref = document.get("candidate_binding_ref")
    source_value = document.get("source_root")
    candidate_value = document.get("candidate_root")
    if (
        type(rotation_id) is not str
        or _ROTATION.fullmatch(rotation_id) is None
        or type(predecessor_ref) is not str
        or _BINDING.fullmatch(predecessor_ref) is None
        or type(candidate_ref) is not str
        or _BINDING.fullmatch(candidate_ref) is None
        or type(source_value) is not str
        or type(candidate_value) is not str
    ):
        _fail("STAGING_RECEIPT_INVALID")
    source_root = Path(source_value)
    candidate_root = Path(candidate_value)
    if (
        not source_root.is_absolute()
        or source_root == Path(source_root.anchor)
        or not candidate_root.is_absolute()
        or candidate_root == Path(candidate_root.anchor)
    ):
        _fail("STAGING_RECEIPT_INVALID")
    return _StagingReceiptBinding(
        raw=raw,
        fingerprint=fingerprint,
        rotation_id=rotation_id,
        predecessor_binding_ref=predecessor_ref,
        candidate_binding_ref=candidate_ref,
        source_root=source_root,
        candidate_root=candidate_root,
    )


def prepare_vault_application_rotation(
    receipt_path: Path,
    *,
    host: SealedPredecessorInspector,
    control_plane_candidate_image_id: str,
    application_build_results_fingerprint: str | None = None,
) -> PreparedVaultApplicationRotation:
    """Validate the exact staging replay and bind the active sealed predecessor."""
    if _IMAGE_ID.fullmatch(control_plane_candidate_image_id) is None:
        _fail("STAGING_RECEIPT_INVALID")
    binding = _staging_receipt_binding(receipt_path)
    source_root = binding.source_root
    candidate_root = binding.candidate_root
    if not source_root.is_dir() or not candidate_root.is_dir():
        _fail("STAGING_RECEIPT_INVALID")
    try:
        replay = stage_vault_credential_rotation(
            source_root=source_root,
            candidate_root=candidate_root,
            receipt_path=receipt_path,
            rotation_id=binding.rotation_id,
        )
    except (OSError, TypeError, ValueError) as error:
        code = "STAGING_RECEIPT_INVALID"
        raise VaultApplicationRotationError(code) from error
    if replay != binding.raw:
        _fail("STAGING_RECEIPT_INVALID")
    sealed_state = host.inspect_predecessor(_ROTATED_NAMES)
    if type(sealed_state) is not str or _SEALED_STATE.fullmatch(sealed_state) is None:
        _fail("PREDECESSOR_SEALED_STATE_INVALID")
    predecessor_snapshot = _credential_snapshot(source_root)
    candidate_snapshot = _credential_snapshot(candidate_root)
    if (
        _snapshot_binding(predecessor_snapshot) != binding.predecessor_binding_ref
        or _snapshot_binding(candidate_snapshot) != binding.candidate_binding_ref
    ):
        _fail("STAGING_RECEIPT_INVALID")
    predecessor_digests = tuple(
        (name, sha256(predecessor_snapshot[name]).hexdigest()) for name in _ROTATED_NAMES
    )
    candidate_digests = tuple(
        (name, sha256(candidate_snapshot[name]).hexdigest()) for name in _ROTATED_NAMES
    )
    plan_body = _plan_body(
        rotation_id=binding.rotation_id,
        staging_receipt_fingerprint=binding.fingerprint,
        predecessor_binding_ref=binding.predecessor_binding_ref,
        candidate_binding_ref=binding.candidate_binding_ref,
        predecessor_sealed_state_ref=sealed_state,
        control_plane_candidate_image_id=control_plane_candidate_image_id,
        application_build_results_fingerprint=application_build_results_fingerprint,
        predecessor_plaintext_sha256=predecessor_digests,
        candidate_plaintext_sha256=candidate_digests,
    )
    plan = VaultApplicationRotationPlan(
        rotation_id=binding.rotation_id,
        staging_receipt_fingerprint=binding.fingerprint,
        predecessor_binding_ref=binding.predecessor_binding_ref,
        candidate_binding_ref=binding.candidate_binding_ref,
        predecessor_sealed_state_ref=sealed_state,
        control_plane_candidate_image_id=control_plane_candidate_image_id,
        application_build_results_fingerprint=application_build_results_fingerprint,
        sealed_credential_names=_ROTATED_NAMES,
        rotated_credential_names=_ROTATED_NAMES,
        credential_units=_CREDENTIAL_UNITS,
        dependent_units=_DEPENDENT_UNITS,
        predecessor_plaintext_sha256=predecessor_digests,
        candidate_plaintext_sha256=candidate_digests,
        plan_fingerprint=_fingerprint(plan_body),
    )
    return PreparedVaultApplicationRotation(
        plan=plan,
        credentials=_CredentialSets(
            predecessor=_credential_groups(source_root),
            candidate=_credential_groups(candidate_root),
        ),
        source_root=source_root,
        candidate_root=candidate_root,
    )


def production_adapter_blockers(
    prepared: PreparedVaultApplicationRotation,
) -> tuple[RotationBlocker, ...]:
    """Name exactly why the current repository cannot safely execute on-host."""
    if type(prepared) is not PreparedVaultApplicationRotation:
        message = "prepared vault application rotation"
        raise TypeError(message)
    blockers: list[RotationBlocker] = []
    if prepared.plan.application_build_results_fingerprint is None:
        blockers.append(RotationBlocker.CANDIDATE_IMAGE_PROVENANCE_MISSING)
    return tuple(sorted(blockers, key=lambda item: item.value))


def _matches(receipt: object, plan: VaultApplicationRotationPlan, binding_ref: str) -> bool:
    return (
        type(receipt) is BoundReceipt
        and receipt.plan_fingerprint == plan.plan_fingerprint
        and receipt.binding_ref == binding_ref
    )


def _acceptance(
    receipt: object,
    plan: VaultApplicationRotationPlan,
    *,
    binding_ref: str,
    accepted: tuple[str, ...],
    rejected: tuple[str, ...],
) -> bool:
    return (
        type(receipt) is AcceptanceReceipt
        and receipt.plan_fingerprint == plan.plan_fingerprint
        and receipt.binding_ref == binding_ref
        and receipt.accepted_names == accepted
        and receipt.rejected_names == rejected
    )


def _unit_ok(receipt: object, plan: VaultApplicationRotationPlan, binding_ref: str) -> bool:
    return (
        type(receipt) is UnitReceipt
        and receipt.plan_fingerprint == plan.plan_fingerprint
        and receipt.binding_ref == binding_ref
        and receipt.units == plan.dependent_units
        and receipt.healthy
    )


def _stopped(receipt: object, plan: VaultApplicationRotationPlan) -> bool:
    return (
        type(receipt) is UnitStopReceipt
        and receipt.plan_fingerprint == plan.plan_fingerprint
        and receipt.units == plan.dependent_units
        and receipt.stopped
    )


def _blockers(*values: RotationBlocker) -> tuple[RotationBlocker, ...]:
    return tuple(sorted(set(values), key=lambda item: item.value))


def _report(
    plan: VaultApplicationRotationPlan,
    *,
    state: RotationState,
    blockers: tuple[RotationBlocker, ...],
    new_values_accepted: bool = False,
    old_values_rejected: bool = False,
    predecessor_restored: bool = False,
    candidate_sealed_absent: bool = False,
    plaintext_absent: bool = False,
) -> VaultApplicationRotationReport:
    return VaultApplicationRotationReport(
        plan_fingerprint=plan.plan_fingerprint,
        staging_receipt_fingerprint=plan.staging_receipt_fingerprint,
        candidate_binding_ref=plan.candidate_binding_ref,
        rotation_id=plan.rotation_id,
        state=state,
        complete=state is RotationState.SUCCEEDED,
        new_values_accepted=new_values_accepted,
        old_values_rejected=old_values_rejected,
        predecessor_restored=predecessor_restored,
        candidate_sealed_absent=candidate_sealed_absent,
        plaintext_absent=plaintext_absent,
        blocker_codes=blockers,
    )


def _rollback(
    prepared: PreparedVaultApplicationRotation,
    *,
    host: HostCredentialSetPort,
    identities: ExactIdentitySetPort,
    authenticator: VaultCredentialAcceptancePort,
    initial: RotationBlocker,
) -> VaultApplicationRotationReport:
    plan = _copy_plan(prepared.plan)
    identity_restored = False
    host_receipt: HostRollbackReceipt | None = None
    units_ok = False
    old_ok = False
    new_rejected = False
    try:
        stopped_ok = _stopped(host.stop_and_check(_copy_plan(plan)), plan)
    except Exception:
        stopped_ok = False
    if not stopped_ok:
        return _report(
            plan,
            state=RotationState.BLOCKED,
            blockers=_blockers(initial, RotationBlocker.ROLLBACK_NOT_PROVED),
        )
    try:
        identities.replace(prepared.credentials.predecessor)
        identity_restored = True
    except Exception:
        pass
    try:
        value = host.restore_predecessor(_copy_plan(plan))
        if type(value) is HostRollbackReceipt:
            host_receipt = value
    except Exception:
        pass
    try:
        units_ok = _unit_ok(
            host.restart_and_check(_copy_plan(plan), binding_ref=plan.predecessor_binding_ref),
            _copy_plan(plan),
            plan.predecessor_binding_ref,
        )
    except Exception:
        pass
    try:
        old_result = authenticator.check(
            _copy_plan(plan),
            binding_ref=plan.predecessor_binding_ref,
            credentials=prepared.credentials.predecessor,
        )
        old_ok = _acceptance(
            old_result,
            plan,
            binding_ref=plan.predecessor_binding_ref,
            accepted=plan.rotated_credential_names,
            rejected=(),
        )
        new_result = authenticator.check(
            _copy_plan(plan),
            binding_ref=plan.candidate_binding_ref,
            credentials=prepared.credentials.candidate,
        )
        new_rejected = _acceptance(
            new_result,
            plan,
            binding_ref=plan.candidate_binding_ref,
            accepted=(),
            rejected=plan.rotated_credential_names,
        )
    except Exception:
        pass
    host_ok = (
        host_receipt is not None
        and host_receipt.plan_fingerprint == plan.plan_fingerprint
        and host_receipt.predecessor_active
        and host_receipt.candidate_sealed_absent
        and host_receipt.candidate_plaintext_absent
    )
    proved = identity_restored and host_ok and units_ok and old_ok and new_rejected
    return _report(
        plan,
        state=RotationState.ROLLED_BACK if proved else RotationState.BLOCKED,
        blockers=(
            _blockers(initial)
            if proved
            else _blockers(initial, RotationBlocker.ROLLBACK_NOT_PROVED)
        ),
        predecessor_restored=proved,
        candidate_sealed_absent=host_ok,
        plaintext_absent=False,
    )


def execute_vault_application_rotation(
    prepared: PreparedVaultApplicationRotation,
    *,
    host: HostCredentialSetPort,
    identities: ExactIdentitySetPort,
    authenticator: VaultCredentialAcceptancePort,
) -> VaultApplicationRotationReport:
    """Execute all seven identities or return an exactly proved rollback."""
    if type(prepared) is not PreparedVaultApplicationRotation:
        message = "prepared vault application rotation"
        raise TypeError(message)
    plan = _copy_plan(prepared.plan)
    if type(identities) is BootstrapIdentitySetAdapter:
        unsupported = RotationBlocker.CROSS_VAULT_IAM_RECONCILIATION_ADAPTER_MISSING
        if _access_sets(prepared.credentials.predecessor) != _access_sets(
            prepared.credentials.candidate
        ):
            unsupported = RotationBlocker.OBSOLETE_IDENTITY_RETIREMENT_ADAPTER_MISSING
        return _report(
            plan,
            state=RotationState.BLOCKED,
            blockers=_blockers(unsupported),
        )
    try:
        staged = host.stage_candidate(_copy_plan(plan), prepared.candidate_root)
    except Exception:
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.CANDIDATE_SEAL_FAILED,
        )
    if not _matches(staged, plan, plan.candidate_binding_ref):
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.RECEIPT_MISMATCH,
        )
    try:
        stopped = host.stop_and_check(_copy_plan(plan))
    except Exception:
        stopped = None
    if not _stopped(stopped, plan):
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.DEPENDENT_UNIT_FAILURE,
        )
    try:
        identities.replace(prepared.credentials.candidate)
    except Exception:
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.IDENTITY_UPDATE_FAILED,
        )
    try:
        switched = host.switch_candidate(_copy_plan(plan), staged)
    except Exception:
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.SEALED_SWITCH_FAILED,
        )
    if not _matches(switched, plan, plan.candidate_binding_ref):
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.RECEIPT_MISMATCH,
        )
    try:
        units = host.restart_and_check(_copy_plan(plan), binding_ref=plan.candidate_binding_ref)
    except Exception:
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.DEPENDENT_UNIT_FAILURE,
        )
    if not _unit_ok(units, plan, plan.candidate_binding_ref):
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.DEPENDENT_UNIT_FAILURE,
        )
    try:
        candidate = authenticator.check(
            _copy_plan(plan),
            binding_ref=plan.candidate_binding_ref,
            credentials=prepared.credentials.candidate,
        )
    except Exception:
        candidate = None
    if not _acceptance(
        candidate,
        plan,
        binding_ref=plan.candidate_binding_ref,
        accepted=plan.rotated_credential_names,
        rejected=(),
    ):
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.CANDIDATE_AUTHENTICATION_FAILED,
        )
    try:
        predecessor = authenticator.check(
            _copy_plan(plan),
            binding_ref=plan.predecessor_binding_ref,
            credentials=prepared.credentials.predecessor,
        )
    except Exception:
        predecessor = None
    if not _acceptance(
        predecessor,
        plan,
        binding_ref=plan.predecessor_binding_ref,
        accepted=(),
        rejected=plan.rotated_credential_names,
    ):
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.PREDECESSOR_STILL_ACCEPTED,
        )
    try:
        acceptance_journal = host.record_acceptance(_copy_plan(plan))
    except Exception:
        acceptance_journal = None
    if not _matches(acceptance_journal, plan, plan.candidate_binding_ref):
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.ACCEPTANCE_JOURNAL_FAILED,
        )
    try:
        cleanup = host.finalize_success(_copy_plan(plan), switched)
    except Exception:
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.PLAINTEXT_CLEANUP_FAILED,
        )
    if (
        type(cleanup) is not HostCleanupReceipt
        or cleanup.plan_fingerprint != plan.plan_fingerprint
        or not cleanup.predecessor_plaintext_absent
        or not cleanup.candidate_plaintext_absent
    ):
        return _rollback(
            prepared,
            host=host,
            identities=identities,
            authenticator=authenticator,
            initial=RotationBlocker.PLAINTEXT_CLEANUP_FAILED,
        )
    return _report(
        plan,
        state=RotationState.SUCCEEDED,
        blockers=(),
        new_values_accepted=True,
        old_values_rejected=True,
        plaintext_absent=True,
    )


def rotation_report_bytes(report: VaultApplicationRotationReport) -> bytes:
    """Serialize only the closed value-free terminal facts."""
    body: dict[str, JsonValue] = {
        "blocker_codes": cast("list[JsonValue]", [item.value for item in report.blocker_codes]),
        "candidate_sealed_absent": report.candidate_sealed_absent,
        "candidate_binding_ref": report.candidate_binding_ref,
        "complete": report.complete,
        "new_values_accepted": report.new_values_accepted,
        "old_values_rejected": report.old_values_rejected,
        "plaintext_absent": report.plaintext_absent,
        "plan_fingerprint": report.plan_fingerprint,
        "staging_receipt_fingerprint": report.staging_receipt_fingerprint,
        "predecessor_restored": report.predecessor_restored,
        "rotation_id": report.rotation_id,
        "schema_id": _REPORT_SCHEMA,
        "schema_version": _VERSION,
        "state": report.state.value,
    }
    return canonicalize(checked_json_value({**body, "fingerprint": _fingerprint(body)}))


def parse_rotation_report_bytes(raw: bytes) -> VaultApplicationRotationReport:
    """Parse only a canonical terminal report, including strict success facts."""
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX_DOCUMENT_BYTES)
    except (TypeError, ValueError) as error:
        code = "ROTATION_REPORT_INVALID"
        raise VaultApplicationRotationError(code) from error
    if type(value) is not dict:
        _fail("ROTATION_REPORT_INVALID")
    document = cast("dict[str, JsonValue]", value)
    expected_keys = {
        "blocker_codes",
        "candidate_sealed_absent",
        "candidate_binding_ref",
        "complete",
        "fingerprint",
        "new_values_accepted",
        "old_values_rejected",
        "plaintext_absent",
        "plan_fingerprint",
        "predecessor_restored",
        "rotation_id",
        "schema_id",
        "schema_version",
        "state",
        "staging_receipt_fingerprint",
    }
    if (
        set(document) != expected_keys
        or document.get("schema_id") != _REPORT_SCHEMA
        or document.get("schema_version") != _VERSION
    ):
        _fail("ROTATION_REPORT_INVALID")
    blocker_values = document.get("blocker_codes")
    try:
        report = VaultApplicationRotationReport(
            plan_fingerprint=cast("str", document.get("plan_fingerprint")),
            staging_receipt_fingerprint=cast("str", document.get("staging_receipt_fingerprint")),
            candidate_binding_ref=cast("str", document.get("candidate_binding_ref")),
            rotation_id=cast("str", document.get("rotation_id")),
            state=RotationState(cast("str", document.get("state"))),
            complete=cast("bool", document.get("complete")),
            new_values_accepted=cast("bool", document.get("new_values_accepted")),
            old_values_rejected=cast("bool", document.get("old_values_rejected")),
            predecessor_restored=cast("bool", document.get("predecessor_restored")),
            candidate_sealed_absent=cast("bool", document.get("candidate_sealed_absent")),
            plaintext_absent=cast("bool", document.get("plaintext_absent")),
            blocker_codes=tuple(
                RotationBlocker(cast("str", item))
                for item in cast("list[JsonValue]", blocker_values)
            ),
        )
    except (TypeError, ValueError) as error:
        code = "ROTATION_REPORT_INVALID"
        raise VaultApplicationRotationError(code) from error
    if rotation_report_bytes(report) != raw:
        _fail("ROTATION_REPORT_INVALID")
    return report


def parse_succeeded_rotation_report_bytes(raw: bytes) -> VaultApplicationRotationReport:
    """Load a report only when every deployment-admission success fact is present."""
    report = parse_rotation_report_bytes(raw)
    if (
        report.state is not RotationState.SUCCEEDED
        or not report.complete
        or not report.new_values_accepted
        or not report.old_values_rejected
        or not report.plaintext_absent
        or report.blocker_codes
    ):
        _fail("ROTATION_REPORT_NOT_SUCCEEDED")
    return report


def _read_retained_rotation_plan(path: Path) -> VaultApplicationRotationPlan:
    """Read one stable private plan without following a replaced pathname."""
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        facts = os.fstat(descriptor)
        current = path.stat(follow_symlinks=False)
        raw = os.pread(descriptor, facts.st_size, 0)
        after = os.fstat(descriptor)
    except OSError as error:
        code = "ROTATION_PLAN_INVALID"
        raise VaultApplicationRotationError(code) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        not stat.S_ISREG(facts.st_mode)
        or stat.S_IMODE(facts.st_mode) != _PRIVATE_FILE_MODE
        or (current.st_dev, current.st_ino) != (facts.st_dev, facts.st_ino)
        or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        != (facts.st_dev, facts.st_ino, facts.st_size, facts.st_mtime_ns)
        or len(raw) != facts.st_size
    ):
        _fail("ROTATION_PLAN_INVALID")
    return parse_rotation_plan_bytes(raw)


def _terminal_replay_plan(
    receipt_path: Path,
    plan_path: Path,
    *,
    control_plane_candidate_image_id: str,
    application_build_results_fingerprint: str,
) -> tuple[VaultApplicationRotationPlan, _StagingReceiptBinding]:
    """Cross-bind retained value-free evidence after plaintext retirement began."""
    binding = _staging_receipt_binding(receipt_path)
    plan = _read_retained_rotation_plan(plan_path)
    if (
        plan.rotation_id != binding.rotation_id
        or plan.staging_receipt_fingerprint != binding.fingerprint
        or plan.predecessor_binding_ref != binding.predecessor_binding_ref
        or plan.candidate_binding_ref != binding.candidate_binding_ref
        or plan.control_plane_candidate_image_id != control_plane_candidate_image_id
        or plan.application_build_results_fingerprint != application_build_results_fingerprint
    ):
        _fail("ROTATION_PLAN_DRIFT")
    return plan, binding


def rotation_plan_bytes(plan: VaultApplicationRotationPlan) -> bytes:
    """Serialize the complete value-free batch plan for host reconciliation."""
    body = _plan_body(
        rotation_id=plan.rotation_id,
        staging_receipt_fingerprint=plan.staging_receipt_fingerprint,
        predecessor_binding_ref=plan.predecessor_binding_ref,
        candidate_binding_ref=plan.candidate_binding_ref,
        predecessor_sealed_state_ref=plan.predecessor_sealed_state_ref,
        control_plane_candidate_image_id=plan.control_plane_candidate_image_id,
        application_build_results_fingerprint=plan.application_build_results_fingerprint,
        predecessor_plaintext_sha256=plan.predecessor_plaintext_sha256,
        candidate_plaintext_sha256=plan.candidate_plaintext_sha256,
    )
    return canonicalize(
        checked_json_value(
            {
                **body,
                "plan_fingerprint": plan.plan_fingerprint,
                "schema_id": "asklegal.hk-v1-vault-application-rotation-plan",
                "schema_version": _VERSION,
            }
        )
    )


def parse_rotation_plan_bytes(raw: bytes) -> VaultApplicationRotationPlan:
    """Parse one canonical batch plan without trusting its summary fields."""
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX_DOCUMENT_BYTES)
    except (TypeError, ValueError) as error:
        code = "ROTATION_PLAN_INVALID"
        raise VaultApplicationRotationError(code) from error
    if type(value) is not dict:
        _fail("ROTATION_PLAN_INVALID")
    document = cast("dict[str, JsonValue]", value)
    rotation_id = document.get("rotation_id")
    staging_fingerprint = document.get("staging_receipt_fingerprint")
    predecessor_ref = document.get("predecessor_binding_ref")
    candidate_ref = document.get("candidate_binding_ref")
    sealed_ref = document.get("predecessor_sealed_state_ref")
    control_image_id = document.get("control_plane_candidate_image_id")
    build_results_fingerprint = document.get("application_build_results_fingerprint")
    predecessor_digest_rows = document.get("predecessor_plaintext_sha256")
    digest_rows = document.get("candidate_plaintext_sha256")
    plan_fingerprint = document.get("plan_fingerprint")
    if not all(
        type(item) is str
        for item in (
            rotation_id,
            staging_fingerprint,
            predecessor_ref,
            candidate_ref,
            sealed_ref,
            control_image_id,
            plan_fingerprint,
        )
    ):
        _fail("ROTATION_PLAN_INVALID")
    if build_results_fingerprint is not None and type(build_results_fingerprint) is not str:
        _fail("ROTATION_PLAN_INVALID")
    if type(predecessor_digest_rows) is not list or type(digest_rows) is not list:
        _fail("ROTATION_PLAN_INVALID")
    parsed_digests: list[tuple[tuple[str, str], ...]] = []
    for rows in (predecessor_digest_rows, digest_rows):
        result: list[tuple[str, str]] = []
        for row in rows:
            if type(row) is not dict or set(row) != {"credential_name", "sha256"}:
                _fail("ROTATION_PLAN_INVALID")
            name = row.get("credential_name")
            digest = row.get("sha256")
            if type(name) is not str or type(digest) is not str:
                _fail("ROTATION_PLAN_INVALID")
            result.append((name, digest))
        parsed_digests.append(tuple(result))
    plan = VaultApplicationRotationPlan(
        rotation_id=cast("str", rotation_id),
        staging_receipt_fingerprint=cast("str", staging_fingerprint),
        predecessor_binding_ref=cast("str", predecessor_ref),
        candidate_binding_ref=cast("str", candidate_ref),
        predecessor_sealed_state_ref=cast("str", sealed_ref),
        control_plane_candidate_image_id=cast("str", control_image_id),
        application_build_results_fingerprint=build_results_fingerprint,
        sealed_credential_names=_ROTATED_NAMES,
        rotated_credential_names=_ROTATED_NAMES,
        credential_units=_CREDENTIAL_UNITS,
        dependent_units=_DEPENDENT_UNITS,
        predecessor_plaintext_sha256=parsed_digests[0],
        candidate_plaintext_sha256=parsed_digests[1],
        plan_fingerprint=cast("str", plan_fingerprint),
    )
    if rotation_plan_bytes(plan) != raw:
        _fail("ROTATION_PLAN_INVALID")
    return plan


def retain_rotation_plan(path: Path, plan: VaultApplicationRotationPlan) -> bytes:
    """Atomically retain or exactly replay one mode-0600 value-free plan."""
    return _retain_value_free(path, rotation_plan_bytes(plan))


def retain_rotation_report(path: Path, report: VaultApplicationRotationReport) -> bytes:
    """Atomically retain or exactly replay one value-free terminal report."""
    return _retain_value_free(path, rotation_report_bytes(report))


def complete_terminal_cleanup(
    *,
    plan: VaultApplicationRotationPlan,
    host: TerminalCleanupPort,
    report_path: Path,
) -> VaultApplicationRotationReport:
    """Resume success-report retention, then retire rollback blobs idempotently."""
    if type(plan) is not VaultApplicationRotationPlan:
        message = "vault application rotation plan"
        raise TypeError(message)
    cleanup = host.finalize_success(
        _copy_plan(plan), BoundReceipt(plan.plan_fingerprint, plan.candidate_binding_ref)
    )
    if not cleanup.predecessor_plaintext_absent or not cleanup.candidate_plaintext_absent:
        _fail("TERMINAL_CLEANUP_FAILED")
    report = host.prove_succeeded_after_cleanup(_copy_plan(plan))
    host.retain_succeeded_report(_copy_plan(plan), report_path, report)
    receipt = host.retire_predecessor_after_report(_copy_plan(plan), report_path)
    if not _matches(receipt, plan, plan.candidate_binding_ref):
        _fail("TERMINAL_CLEANUP_FAILED")
    return report


def _retain_value_free(path: Path, raw: bytes) -> bytes:
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not path.parent.is_dir()
        or path.parent.is_symlink()
        or _has_symlink_component(path.parent)
    ):
        _fail("ROTATION_PLAN_OUTPUT_INVALID")
    if path.exists():
        if (
            not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != _PRIVATE_FILE_MODE
            or path.read_bytes() != raw
        ):
            _fail("ROTATION_PLAN_OUTPUT_DRIFT")
        return raw
    temporary = path.parent / f".{path.name}.{token_urlsafe(18)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        _PRIVATE_FILE_MODE,
    )
    try:
        view = memoryview(raw)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count < 1:
                _fail("ROTATION_PLAN_OUTPUT_INVALID")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.link(temporary, path, follow_symlinks=False)
    except OSError:
        temporary.unlink(missing_ok=True)
        if path.exists():
            if (
                path.is_file()
                and not path.is_symlink()
                and stat.S_IMODE(path.stat().st_mode) == _PRIVATE_FILE_MODE
                and path.read_bytes() == raw
            ):
                return raw
            _fail("ROTATION_PLAN_OUTPUT_DRIFT")
        _fail("ROTATION_PLAN_OUTPUT_INVALID")
    temporary.unlink()
    if path.read_bytes() != raw or stat.S_IMODE(path.stat().st_mode) != _PRIVATE_FILE_MODE:
        _fail("ROTATION_PLAN_OUTPUT_INVALID")
    return raw


def production_blocker_bytes(prepared: PreparedVaultApplicationRotation) -> bytes:
    """Render the exact no-effect production-adapter blockers."""
    blockers = production_adapter_blockers(prepared)
    body: dict[str, JsonValue] = {
        "blocker_codes": cast("list[JsonValue]", [item.value for item in blockers]),
        "plan_fingerprint": prepared.plan.plan_fingerprint,
        "rotation_id": prepared.plan.rotation_id,
        "schema_id": "asklegal.hk-v1-vault-application-rotation-preflight",
        "schema_version": _VERSION,
        "state": "NOT_READY" if blockers else "READY",
    }
    return canonicalize(checked_json_value({**body, "fingerprint": _fingerprint(body)}))


def retain_production_preflight(path: Path, prepared: PreparedVaultApplicationRotation) -> bytes:
    """Atomically retain the exact value-free NOT_READY adapter readback."""
    return _retain_value_free(path, production_blocker_bytes(prepared))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or authority-gate the seven-credential vault rotation"
    )
    parser.add_argument("action", choices=("preflight", "execute"))
    parser.add_argument("--staging-receipt", required=True, type=Path)
    parser.add_argument("--sealed-root", required=True, type=Path)
    parser.add_argument("--plan-output", required=True, type=Path)
    parser.add_argument("--preflight-output", type=Path)
    parser.add_argument("--application-build-results", required=True, type=Path)
    parser.add_argument("--application-image-inputs", required=True, type=Path)
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--runtime-credential-root", type=Path)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--authorized-plan-fingerprint")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect without effects and retain one plan plus explicit blockers."""
    arguments = _parser().parse_args(argv)
    try:
        image_id, build_results_fingerprint = _candidate_image_provenance(
            build_results_path=arguments.application_build_results.absolute(),
            image_inputs_path=arguments.application_image_inputs.absolute(),
            workspace_root=arguments.workspace_root.absolute(),
        )
        receipt_path = arguments.staging_receipt.absolute()
        plan_path = arguments.plan_output.absolute()
        staging_binding = _staging_receipt_binding(receipt_path)
        if arguments.action == "execute" and (
            not staging_binding.source_root.is_dir() or not staging_binding.candidate_root.is_dir()
        ):
            if (
                arguments.state_root is None
                or arguments.runtime_credential_root is None
                or arguments.report_output is None
                or os.geteuid() != 0
            ):
                _fail("LIVE_ROTATION_AUTHORITY_REQUIRED")
            plan, replay_binding = _terminal_replay_plan(
                receipt_path,
                plan_path,
                control_plane_candidate_image_id=image_id,
                application_build_results_fingerprint=build_results_fingerprint,
            )
            if arguments.authorized_plan_fingerprint != plan.plan_fingerprint:
                _fail("LIVE_ROTATION_AUTHORITY_REQUIRED")
            host = TransactionalFlatHostCredentialSet(
                arguments.sealed_root.absolute(),
                arguments.state_root.absolute(),
                plan,
                runner=QuietExactCommandRunner(),
                source_root=replay_binding.source_root,
                candidate_root=replay_binding.candidate_root,
                runtime_credential_root=arguments.runtime_credential_root.absolute(),
                authorized_plan_fingerprint=arguments.authorized_plan_fingerprint,
                host_owner_uid=0,
                staging_owner_uid=receipt_path.stat().st_uid,
            )
            report = complete_terminal_cleanup(
                plan=plan,
                host=host,
                report_path=arguments.report_output.absolute(),
            )
            raw = rotation_report_bytes(report)
            sys.stdout.buffer.write(raw + b"\n")
            return 0
        prepared = prepare_vault_application_rotation(
            receipt_path,
            host=FlatSealedPredecessorInspector(arguments.sealed_root.absolute()),
            control_plane_candidate_image_id=image_id,
            application_build_results_fingerprint=build_results_fingerprint,
        )
        retain_rotation_plan(plan_path, prepared.plan)
        if arguments.action == "preflight":
            if arguments.preflight_output is None:
                _fail("ROTATION_PREFLIGHT_OUTPUT_REQUIRED")
            raw = retain_production_preflight(arguments.preflight_output.absolute(), prepared)
        else:
            if (
                arguments.state_root is None
                or arguments.runtime_credential_root is None
                or arguments.report_output is None
                or arguments.authorized_plan_fingerprint != prepared.plan.plan_fingerprint
                or os.geteuid() != 0
            ):
                _fail("LIVE_ROTATION_AUTHORITY_REQUIRED")
            state_root = arguments.state_root.absolute()
            report_path = arguments.report_output.absolute()
            host = TransactionalFlatHostCredentialSet(
                arguments.sealed_root.absolute(),
                state_root,
                prepared.plan,
                runner=QuietExactCommandRunner(),
                source_root=prepared.source_root,
                candidate_root=prepared.candidate_root,
                runtime_credential_root=arguments.runtime_credential_root.absolute(),
                authorized_plan_fingerprint=arguments.authorized_plan_fingerprint,
                host_owner_uid=0,
                staging_owner_uid=receipt_path.stat().st_uid,
            )
            network = DualNetworkRotationAdapter(
                QuietExactCommandRunner(),
                prepared,
                plan_path=plan_path,
                authorized_plan_fingerprint=arguments.authorized_plan_fingerprint,
            )
            report = execute_vault_application_rotation(
                prepared,
                host=host,
                identities=network,
                authenticator=network,
            )
            if report.state is RotationState.SUCCEEDED:
                report = complete_terminal_cleanup(
                    plan=prepared.plan,
                    host=host,
                    report_path=report_path,
                )
            else:
                _retain_value_free(report_path, rotation_report_bytes(report))
            raw = rotation_report_bytes(report)
    except OSError, TypeError, ValueError, VaultApplicationRotationError:
        print("VAULT_APPLICATION_ROTATION_PREFLIGHT_NOT_READY", file=sys.stderr)  # noqa: T201
        return 2
    sys.stdout.buffer.write(raw + b"\n")
    if arguments.action == "execute":
        return 0 if parse_rotation_report_bytes(raw).state is RotationState.SUCCEEDED else 2
    return 2 if production_adapter_blockers(prepared) else 0


if __name__ == "__main__":
    raise SystemExit(main())
