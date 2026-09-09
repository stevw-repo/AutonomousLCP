"""Provider-neutral local protocol for one exact V1 credential rotation.

The module contains no credential values, filesystem operations, commands, or
service adapters. It accepts only opaque references and exact detached receipts
from injected ports.
"""

# Every caught ordinary exception is deliberately normalized to a closed code.
# ruff: noqa: BLE001

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Never, Protocol, TypedDict, cast

_CREDENTIAL_NAMES = frozenset(
    {
        "embedding-provider",
        "grafana-admin",
        "model-egress-proxy",
        "model-provider",
        "pinecone-poc",
        "promotion-egress-proxy",
        "review-api",
        "review-client",
        "source-egress-proxy",
        "sql-acquisition",
        "sql-bootstrap-password",
        "sql-control",
        "sql-processing",
        "sql-promotion",
        "sql-review",
        "vault-primary-acquisition",
        "vault-primary-control",
        "vault-primary-processing",
        "vault-primary-promotion",
        "vault-primary-review",
        "vault-primary-root-access",
        "vault-primary-root-secret",
        "vault-recovery-acquisition",
        "vault-recovery-promotion",
        "vault-recovery-root-access",
        "vault-recovery-root-secret",
    }
)
_UNIT_NAME = re.compile(r"^asklegal-[a-z0-9-]+[.]service$")
_ROTATION_ID = re.compile(r"^rot_[0-9a-f]{48}$")
_BINDING_REF = re.compile(r"^binding_[0-9a-f]{48}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


def required_credential_names() -> tuple[str, ...]:
    """Return the closed V1 sealed-credential inventory in canonical order."""
    return tuple(sorted(_CREDENTIAL_NAMES))


class CredentialRotationState(StrEnum):
    """Closed terminal states for one rotation attempt."""

    SUCCEEDED = "SUCCEEDED"
    ROLLED_BACK = "ROLLED_BACK"
    BLOCKED = "BLOCKED"


class CredentialRotationBlocker(StrEnum):
    """Closed sanitized failure reasons."""

    ACKNOWLEDGEMENT_UNRECONCILED = "ACKNOWLEDGEMENT_UNRECONCILED"
    ADAPTER_FAILED = "ADAPTER_FAILED"
    CANDIDATE_REJECTED = "CANDIDATE_REJECTED"
    DEPENDENT_UNITS_UNHEALTHY = "DEPENDENT_UNITS_UNHEALTHY"
    OBSOLETE_BINDING_REMAINS = "OBSOLETE_BINDING_REMAINS"
    PLAINTEXT_STAGING_REMAINS = "PLAINTEXT_STAGING_REMAINS"
    PREDECESSOR_STILL_ACCEPTED = "PREDECESSOR_STILL_ACCEPTED"
    RECEIPT_MISMATCH = "RECEIPT_MISMATCH"
    REPLAY_DRIFT = "REPLAY_DRIFT"
    ROLLBACK_NOT_PROVED = "ROLLBACK_NOT_PROVED"


class AcknowledgementLost(Exception):
    """An operation may have completed but its acknowledgement was lost."""


def _invalid_type(label: str) -> Never:
    raise TypeError(label)


def _invalid_value(label: str) -> Never:
    raise ValueError(label)


def _require_text(value: object, pattern: re.Pattern[str], label: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _invalid_value(label)
    return value


def _require_credential_name(value: object) -> str:
    if type(value) is not str or value not in _CREDENTIAL_NAMES:
        _invalid_value("credential name")
    return value


def _require_units(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        _invalid_type("dependent units")
    units = cast("tuple[object, ...]", value)
    if any(type(item) is not str or _UNIT_NAME.fullmatch(item) is None for item in units):
        _invalid_value("dependent unit")
    validated = cast("tuple[str, ...]", units)
    if tuple(sorted(validated)) != validated or len(set(validated)) != len(validated):
        _invalid_value("dependent units must be sorted and unique")
    return validated


@dataclass(frozen=True, slots=True)
class CredentialManifestEntry:
    """One credential name and the exact units that consume it."""

    credential_name: str
    dependent_units: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject open names and ambiguous unit inventories."""
        _require_credential_name(self.credential_name)
        _require_units(self.dependent_units)


def _manifest_fingerprint(entries: tuple[CredentialManifestEntry, ...]) -> str:
    document = [
        {
            "credential_name": entry.credential_name,
            "dependent_units": list(entry.dependent_units),
        }
        for entry in entries
    ]
    encoded = json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CredentialManifest:
    """One detached collision-free credential-to-unit manifest."""

    manifest_fingerprint: str
    entries: tuple[CredentialManifestEntry, ...]

    def __post_init__(self) -> None:
        """Reject drift, duplicates, and caller-selected fingerprints."""
        _require_text(self.manifest_fingerprint, _FINGERPRINT, "manifest fingerprint")
        if type(self.entries) is not tuple or not self.entries:
            _invalid_type("credential manifest entries")
        if any(type(entry) is not CredentialManifestEntry for entry in self.entries):
            _invalid_type("credential manifest entry")
        detached = tuple(
            CredentialManifestEntry(entry.credential_name, entry.dependent_units)
            for entry in self.entries
        )
        object.__setattr__(self, "entries", detached)
        names = tuple(entry.credential_name for entry in detached)
        if names != tuple(sorted(names)):
            _invalid_value("credential manifest entries must be sorted")
        if len(set(names)) != len(names):
            _invalid_value("duplicate credential")
        if self.manifest_fingerprint != _manifest_fingerprint(detached):
            _invalid_value("manifest fingerprint mismatch")


@dataclass(frozen=True, slots=True)
class CredentialRotationPlan:
    """One exact value-free rotation request."""

    rotation_id: str
    manifest_fingerprint: str
    credential_name: str
    predecessor_binding_ref: str
    candidate_binding_ref: str
    dependent_units: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject malformed or secret-bearing plan facts."""
        _validate_binding(self)


class _BindingFields(Protocol):
    @property
    def rotation_id(self) -> str: ...

    @property
    def manifest_fingerprint(self) -> str: ...

    @property
    def credential_name(self) -> str: ...

    @property
    def predecessor_binding_ref(self) -> str: ...

    @property
    def candidate_binding_ref(self) -> str: ...

    @property
    def dependent_units(self) -> tuple[str, ...]: ...


def _validate_binding(value: _BindingFields) -> None:
    _require_text(value.rotation_id, _ROTATION_ID, "rotation ID")
    _require_text(value.manifest_fingerprint, _FINGERPRINT, "manifest fingerprint")
    _require_credential_name(value.credential_name)
    _require_text(value.predecessor_binding_ref, _BINDING_REF, "binding reference")
    _require_text(value.candidate_binding_ref, _BINDING_REF, "binding reference")
    if value.predecessor_binding_ref == value.candidate_binding_ref:
        _invalid_value("binding references must be distinct")
    _require_units(value.dependent_units)


@dataclass(frozen=True, slots=True)
class _BoundReceipt:
    rotation_id: str
    manifest_fingerprint: str
    credential_name: str
    predecessor_binding_ref: str
    candidate_binding_ref: str
    dependent_units: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate the common exact plan binding."""
        _validate_binding(self)


@dataclass(frozen=True, slots=True)
class StageReceipt(_BoundReceipt):
    """Exact read-back proving the candidate sealed binding exists."""


@dataclass(frozen=True, slots=True)
class SwitchReceipt(_BoundReceipt):
    """Exact read-back proving which binding is current."""

    current_binding_ref: str

    def __post_init__(self) -> None:
        """Validate the current binding read-back."""
        super(SwitchReceipt, self).__post_init__()
        _require_text(self.current_binding_ref, _BINDING_REF, "binding reference")


@dataclass(frozen=True, slots=True)
class RestartReceipt(_BoundReceipt):
    """Exact account of the dependent units restarted for one binding."""

    active_binding_ref: str
    restarted_units: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate the binding and exact restarted-unit inventory."""
        super(RestartReceipt, self).__post_init__()
        _require_text(self.active_binding_ref, _BINDING_REF, "binding reference")
        _require_units(self.restarted_units)


@dataclass(frozen=True, slots=True)
class AuthenticationReceipt(_BoundReceipt):
    """Exact credential acceptance and dependent-health read-back."""

    checked_binding_ref: str
    credential_accepted: bool
    dependent_services_healthy: bool

    def __post_init__(self) -> None:
        """Validate closed authentication and health facts."""
        super(AuthenticationReceipt, self).__post_init__()
        _require_text(self.checked_binding_ref, _BINDING_REF, "binding reference")
        if type(self.credential_accepted) is not bool:
            _invalid_type("credential acceptance")
        if type(self.dependent_services_healthy) is not bool:
            _invalid_type("dependent service health")


@dataclass(frozen=True, slots=True)
class CleanupReceipt(_BoundReceipt):
    """Exact absence read-back after irreversible cleanup."""

    obsolete_predecessor_absent: bool
    plaintext_staging_absent: bool

    def __post_init__(self) -> None:
        """Validate exact boolean absence facts."""
        super(CleanupReceipt, self).__post_init__()
        if type(self.obsolete_predecessor_absent) is not bool:
            _invalid_type("obsolete predecessor absence")
        if type(self.plaintext_staging_absent) is not bool:
            _invalid_type("plaintext staging absence")


@dataclass(frozen=True, slots=True)
class RollbackReceipt(_BoundReceipt):
    """Exact store read-back after attempting predecessor restoration."""

    predecessor_binding_restored: bool
    candidate_material_absent: bool
    plaintext_staging_absent: bool

    def __post_init__(self) -> None:
        """Validate exact boolean restoration facts."""
        super(RollbackReceipt, self).__post_init__()
        if type(self.predecessor_binding_restored) is not bool:
            _invalid_type("predecessor restoration")
        if type(self.candidate_material_absent) is not bool:
            _invalid_type("candidate absence")
        if type(self.plaintext_staging_absent) is not bool:
            _invalid_type("plaintext staging absence")


@dataclass(frozen=True, slots=True)
class CredentialRotationReport(_BoundReceipt):
    """One terminal, sanitized, value-free protocol result."""

    state: CredentialRotationState
    complete: bool
    new_value_works: bool
    old_value_rejected: bool
    old_binding_restored: bool
    candidate_material_absent: bool
    obsolete_binding_absent: bool
    plaintext_staging_absent: bool
    blocker_codes: tuple[CredentialRotationBlocker, ...]

    def __post_init__(self) -> None:
        """Reject an internally inconsistent terminal claim."""
        super(CredentialRotationReport, self).__post_init__()
        if type(self.state) is not CredentialRotationState:
            _invalid_type("rotation state")
        for value in (
            self.complete,
            self.new_value_works,
            self.old_value_rejected,
            self.old_binding_restored,
            self.candidate_material_absent,
            self.obsolete_binding_absent,
            self.plaintext_staging_absent,
        ):
            if type(value) is not bool:
                _invalid_type("rotation report boolean")
        if type(self.blocker_codes) is not tuple or any(
            type(code) is not CredentialRotationBlocker for code in self.blocker_codes
        ):
            _invalid_type("rotation blocker codes")
        expected = tuple(sorted(set(self.blocker_codes), key=lambda code: code.value))
        if self.blocker_codes != expected:
            _invalid_value("rotation blocker codes must be sorted and unique")
        if self.complete != (self.state is CredentialRotationState.SUCCEEDED):
            _invalid_value("rotation completion mismatch")
        if self.complete and (
            self.blocker_codes
            or not self.new_value_works
            or not self.old_value_rejected
            or not self.obsolete_binding_absent
            or not self.plaintext_staging_absent
            or self.old_binding_restored
        ):
            _invalid_value("unproved rotation success")
        if self.state is CredentialRotationState.ROLLED_BACK and (
            not self.blocker_codes
            or not self.old_binding_restored
            or not self.candidate_material_absent
            or not self.plaintext_staging_absent
            or self.obsolete_binding_absent
        ):
            _invalid_value("unproved rollback")


class SealedCredentialStore(ABC):
    """Opaque sealed-binding operations; values never cross this port."""

    @abstractmethod
    def stage_candidate(self, plan: CredentialRotationPlan) -> StageReceipt:
        """Stage the candidate, returning its exact read-back."""
        ...

    @abstractmethod
    def read_staged_candidate(self, plan: CredentialRotationPlan) -> StageReceipt | None:
        """Reconcile a lost stage acknowledgement."""
        ...

    @abstractmethod
    def switch_binding(self, plan: CredentialRotationPlan, stage: StageReceipt) -> SwitchReceipt:
        """Switch to the exact staged binding and read it back."""
        ...

    @abstractmethod
    def read_switched_binding(self, plan: CredentialRotationPlan) -> SwitchReceipt | None:
        """Reconcile a lost switch acknowledgement."""
        ...

    @abstractmethod
    def remove_obsolete(
        self, plan: CredentialRotationPlan, switch: SwitchReceipt
    ) -> CleanupReceipt:
        """Remove predecessor/plaintext material and prove absence."""
        ...

    @abstractmethod
    def read_cleanup(self, plan: CredentialRotationPlan) -> CleanupReceipt | None:
        """Reconcile a lost cleanup acknowledgement."""
        ...

    @abstractmethod
    def restore_predecessor(self, plan: CredentialRotationPlan) -> RollbackReceipt:
        """Restore the predecessor and remove candidate/plaintext material."""
        ...

    @abstractmethod
    def read_rollback(self, plan: CredentialRotationPlan) -> RollbackReceipt | None:
        """Reconcile a lost rollback acknowledgement."""
        ...


class DependentUnitController(ABC):
    """Exact dependent-unit restart boundary."""

    @abstractmethod
    def restart_exact(self, plan: CredentialRotationPlan, *, binding_ref: str) -> RestartReceipt:
        """Restart only the plan's exact dependent units."""
        ...

    @abstractmethod
    def read_restart(
        self, plan: CredentialRotationPlan, *, binding_ref: str
    ) -> RestartReceipt | None:
        """Read back the exact restart state without issuing another restart."""
        ...


class CredentialHealthChecker(ABC):
    """Candidate/predecessor authentication and health boundary."""

    @abstractmethod
    def check_binding(
        self, plan: CredentialRotationPlan, *, binding_ref: str
    ) -> AuthenticationReceipt:
        """Read back acceptance and dependent health for one binding."""
        ...


def build_credential_manifest(
    entries: tuple[CredentialManifestEntry, ...],
) -> CredentialManifest:
    """Build one deterministic, detached, collision-free manifest."""
    if type(entries) is not tuple or not entries:
        _invalid_type("credential manifest entries")
    if any(type(entry) is not CredentialManifestEntry for entry in entries):
        _invalid_type("credential manifest entry")
    detached = tuple(
        CredentialManifestEntry(entry.credential_name, entry.dependent_units) for entry in entries
    )
    names = tuple(entry.credential_name for entry in detached)
    if len(set(names)) != len(names):
        _invalid_value("duplicate credential")
    ordered = tuple(sorted(detached, key=lambda entry: entry.credential_name))
    return CredentialManifest(_manifest_fingerprint(ordered), ordered)


def plan_rotation(
    manifest: CredentialManifest,
    *,
    credential_name: str,
    rotation_id: str,
    predecessor_binding_ref: str,
    candidate_binding_ref: str,
) -> CredentialRotationPlan:
    """Select and detach one exact manifest entry for rotation."""
    if type(manifest) is not CredentialManifest:
        _invalid_type("credential manifest")
    safe_manifest = CredentialManifest(manifest.manifest_fingerprint, manifest.entries)
    _require_credential_name(credential_name)
    matches = tuple(
        entry for entry in safe_manifest.entries if entry.credential_name == credential_name
    )
    if len(matches) != 1:
        _invalid_value("credential not in manifest")
    return CredentialRotationPlan(
        rotation_id=rotation_id,
        manifest_fingerprint=safe_manifest.manifest_fingerprint,
        credential_name=credential_name,
        predecessor_binding_ref=predecessor_binding_ref,
        candidate_binding_ref=candidate_binding_ref,
        dependent_units=matches[0].dependent_units,
    )


def _matches_plan(value: _BindingFields, plan: CredentialRotationPlan) -> bool:
    return (
        value.rotation_id == plan.rotation_id
        and value.manifest_fingerprint == plan.manifest_fingerprint
        and value.credential_name == plan.credential_name
        and value.predecessor_binding_ref == plan.predecessor_binding_ref
        and value.candidate_binding_ref == plan.candidate_binding_ref
        and value.dependent_units == plan.dependent_units
    )


def _copy_plan(plan: CredentialRotationPlan) -> CredentialRotationPlan:
    """Create a validated copy that an adapter may mutate without rebinding authority."""
    return CredentialRotationPlan(
        rotation_id=plan.rotation_id,
        manifest_fingerprint=plan.manifest_fingerprint,
        credential_name=plan.credential_name,
        predecessor_binding_ref=plan.predecessor_binding_ref,
        candidate_binding_ref=plan.candidate_binding_ref,
        dependent_units=plan.dependent_units,
    )


def _detach_stage(value: object) -> StageReceipt | None:
    if type(value) is not StageReceipt:
        return None
    try:
        receipt = value
        return StageReceipt(
            receipt.rotation_id,
            receipt.manifest_fingerprint,
            receipt.credential_name,
            receipt.predecessor_binding_ref,
            receipt.candidate_binding_ref,
            receipt.dependent_units,
        )
    except Exception:
        return None


def _detach_switch(value: object) -> SwitchReceipt | None:
    if type(value) is not SwitchReceipt:
        return None
    try:
        receipt = value
        return SwitchReceipt(
            receipt.rotation_id,
            receipt.manifest_fingerprint,
            receipt.credential_name,
            receipt.predecessor_binding_ref,
            receipt.candidate_binding_ref,
            receipt.dependent_units,
            receipt.current_binding_ref,
        )
    except Exception:
        return None


def _detach_restart(value: object) -> RestartReceipt | None:
    if type(value) is not RestartReceipt:
        return None
    try:
        receipt = value
        return RestartReceipt(
            receipt.rotation_id,
            receipt.manifest_fingerprint,
            receipt.credential_name,
            receipt.predecessor_binding_ref,
            receipt.candidate_binding_ref,
            receipt.dependent_units,
            receipt.active_binding_ref,
            receipt.restarted_units,
        )
    except Exception:
        return None


def _detach_authentication(value: object) -> AuthenticationReceipt | None:
    if type(value) is not AuthenticationReceipt:
        return None
    try:
        receipt = value
        return AuthenticationReceipt(
            receipt.rotation_id,
            receipt.manifest_fingerprint,
            receipt.credential_name,
            receipt.predecessor_binding_ref,
            receipt.candidate_binding_ref,
            receipt.dependent_units,
            receipt.checked_binding_ref,
            receipt.credential_accepted,
            receipt.dependent_services_healthy,
        )
    except Exception:
        return None


def _detach_cleanup(value: object) -> CleanupReceipt | None:
    if type(value) is not CleanupReceipt:
        return None
    try:
        receipt = value
        return CleanupReceipt(
            receipt.rotation_id,
            receipt.manifest_fingerprint,
            receipt.credential_name,
            receipt.predecessor_binding_ref,
            receipt.candidate_binding_ref,
            receipt.dependent_units,
            receipt.obsolete_predecessor_absent,
            receipt.plaintext_staging_absent,
        )
    except Exception:
        return None


def _detach_rollback(value: object) -> RollbackReceipt | None:
    if type(value) is not RollbackReceipt:
        return None
    try:
        receipt = value
        return RollbackReceipt(
            receipt.rotation_id,
            receipt.manifest_fingerprint,
            receipt.credential_name,
            receipt.predecessor_binding_ref,
            receipt.candidate_binding_ref,
            receipt.dependent_units,
            receipt.predecessor_binding_restored,
            receipt.candidate_material_absent,
            receipt.plaintext_staging_absent,
        )
    except Exception:
        return None


def _detach_report(value: object) -> CredentialRotationReport | None:
    if type(value) is not CredentialRotationReport:
        return None
    try:
        report = value
        return CredentialRotationReport(
            report.rotation_id,
            report.manifest_fingerprint,
            report.credential_name,
            report.predecessor_binding_ref,
            report.candidate_binding_ref,
            report.dependent_units,
            report.state,
            report.complete,
            report.new_value_works,
            report.old_value_rejected,
            report.old_binding_restored,
            report.candidate_material_absent,
            report.obsolete_binding_absent,
            report.plaintext_staging_absent,
            report.blocker_codes,
        )
    except Exception:
        return None


def _blockers(
    *codes: CredentialRotationBlocker,
) -> tuple[CredentialRotationBlocker, ...]:
    return tuple(sorted(set(codes), key=lambda code: code.value))


def _report(  # noqa: PLR0913
    plan: CredentialRotationPlan,
    *,
    state: CredentialRotationState,
    blockers: tuple[CredentialRotationBlocker, ...],
    new_value_works: bool = False,
    old_value_rejected: bool = False,
    old_binding_restored: bool = False,
    candidate_material_absent: bool = False,
    obsolete_binding_absent: bool = False,
    plaintext_staging_absent: bool = False,
) -> CredentialRotationReport:
    return CredentialRotationReport(
        rotation_id=plan.rotation_id,
        manifest_fingerprint=plan.manifest_fingerprint,
        credential_name=plan.credential_name,
        predecessor_binding_ref=plan.predecessor_binding_ref,
        candidate_binding_ref=plan.candidate_binding_ref,
        dependent_units=tuple(plan.dependent_units),
        state=state,
        complete=state is CredentialRotationState.SUCCEEDED,
        new_value_works=new_value_works,
        old_value_rejected=old_value_rejected,
        old_binding_restored=old_binding_restored,
        candidate_material_absent=candidate_material_absent,
        obsolete_binding_absent=obsolete_binding_absent,
        plaintext_staging_absent=plaintext_staging_absent,
        blocker_codes=blockers,
    )


def _rollback(  # noqa: C901, PLR0913
    plan: CredentialRotationPlan,
    store: SealedCredentialStore,
    units: DependentUnitController,
    checker: CredentialHealthChecker,
    *,
    initial: tuple[CredentialRotationBlocker, ...],
    new_value_works: bool,
    old_value_rejected: bool,
    force_blocked: bool = False,
) -> CredentialRotationReport:
    rollback_value: object | None
    rollback_ack_unreconciled = False
    try:
        rollback_value = store.restore_predecessor(_copy_plan(plan))
    except AcknowledgementLost:
        try:
            rollback_value = store.read_rollback(_copy_plan(plan))
        except Exception:
            rollback_value = None
        rollback_ack_unreconciled = rollback_value is None
    except Exception:
        rollback_value = None

    rollback = _detach_rollback(rollback_value)
    rollback_ack_unreconciled = rollback_ack_unreconciled or (
        rollback_value is not None and rollback is None
    )
    store_proved = (
        rollback is not None
        and _matches_plan(rollback, plan)
        and rollback.predecessor_binding_restored
        and rollback.candidate_material_absent
        and rollback.plaintext_staging_absent
    )
    restart_proved = False
    health_proved = False
    restart_ack_unreconciled = False
    if store_proved:
        try:
            restarted_value: object | None = units.restart_exact(
                _copy_plan(plan), binding_ref=plan.predecessor_binding_ref
            )
        except AcknowledgementLost:
            try:
                restarted_value = units.read_restart(
                    _copy_plan(plan), binding_ref=plan.predecessor_binding_ref
                )
            except Exception:
                restarted_value = None
            restart_ack_unreconciled = restarted_value is None
        except Exception:
            restarted_value = None
        restarted = _detach_restart(restarted_value)
        restart_ack_unreconciled = restart_ack_unreconciled or (
            restarted_value is not None and restarted is None
        )
        if restarted is not None:
            restart_proved = (
                _matches_plan(restarted, plan)
                and restarted.active_binding_ref == plan.predecessor_binding_ref
                and restarted.restarted_units == plan.dependent_units
            )
    if store_proved and restart_proved:
        try:
            checked_value = checker.check_binding(
                _copy_plan(plan), binding_ref=plan.predecessor_binding_ref
            )
        except Exception:
            checked_value = None
        checked = _detach_authentication(checked_value)
        if checked is not None:
            health_proved = (
                _matches_plan(checked, plan)
                and checked.checked_binding_ref == plan.predecessor_binding_ref
                and checked.credential_accepted
                and checked.dependent_services_healthy
            )

    proved = store_proved and restart_proved and health_proved
    blockers = (
        initial if proved else _blockers(*initial, CredentialRotationBlocker.ROLLBACK_NOT_PROVED)
    )
    if rollback_ack_unreconciled or restart_ack_unreconciled:
        blockers = _blockers(*blockers, CredentialRotationBlocker.ACKNOWLEDGEMENT_UNRECONCILED)
    state = (
        CredentialRotationState.BLOCKED
        if force_blocked or not proved
        else CredentialRotationState.ROLLED_BACK
    )
    return _report(
        plan,
        state=state,
        blockers=blockers,
        new_value_works=new_value_works,
        old_value_rejected=old_value_rejected,
        old_binding_restored=proved,
        candidate_material_absent=proved,
        plaintext_staging_absent=proved,
    )


def _replay_report(
    plan: CredentialRotationPlan,
    prior_value: object,
    store: SealedCredentialStore,
    units: DependentUnitController,
    checker: CredentialHealthChecker,
) -> CredentialRotationReport:
    prior = _detach_report(prior_value)
    if prior is None or not _matches_plan(prior, plan):
        return _report(
            plan,
            state=CredentialRotationState.BLOCKED,
            blockers=_blockers(CredentialRotationBlocker.REPLAY_DRIFT),
        )
    if prior.state is CredentialRotationState.BLOCKED:
        return prior
    try:
        if prior.state is CredentialRotationState.SUCCEEDED:
            switched = _detach_switch(store.read_switched_binding(_copy_plan(plan)))
            restarted = _detach_restart(
                units.read_restart(_copy_plan(plan), binding_ref=plan.candidate_binding_ref)
            )
            candidate = _detach_authentication(
                checker.check_binding(_copy_plan(plan), binding_ref=plan.candidate_binding_ref)
            )
            predecessor = _detach_authentication(
                checker.check_binding(_copy_plan(plan), binding_ref=plan.predecessor_binding_ref)
            )
            cleanup = _detach_cleanup(store.read_cleanup(_copy_plan(plan)))
            proved = (
                switched is not None
                and _matches_plan(switched, plan)
                and switched.current_binding_ref == plan.candidate_binding_ref
                and restarted is not None
                and _matches_plan(restarted, plan)
                and restarted.active_binding_ref == plan.candidate_binding_ref
                and restarted.restarted_units == plan.dependent_units
                and candidate is not None
                and _matches_plan(candidate, plan)
                and candidate.checked_binding_ref == plan.candidate_binding_ref
                and candidate.credential_accepted
                and candidate.dependent_services_healthy
                and predecessor is not None
                and _matches_plan(predecessor, plan)
                and predecessor.checked_binding_ref == plan.predecessor_binding_ref
                and not predecessor.credential_accepted
                and predecessor.dependent_services_healthy
                and cleanup is not None
                and _matches_plan(cleanup, plan)
                and cleanup.obsolete_predecessor_absent
                and cleanup.plaintext_staging_absent
            )
            if proved:
                return _report(
                    plan,
                    state=CredentialRotationState.SUCCEEDED,
                    blockers=(),
                    new_value_works=True,
                    old_value_rejected=True,
                    obsolete_binding_absent=True,
                    plaintext_staging_absent=True,
                )
        else:
            rollback = _detach_rollback(store.read_rollback(_copy_plan(plan)))
            restarted = _detach_restart(
                units.read_restart(_copy_plan(plan), binding_ref=plan.predecessor_binding_ref)
            )
            predecessor = _detach_authentication(
                checker.check_binding(_copy_plan(plan), binding_ref=plan.predecessor_binding_ref)
            )
            proved = (
                rollback is not None
                and _matches_plan(rollback, plan)
                and rollback.predecessor_binding_restored
                and rollback.candidate_material_absent
                and rollback.plaintext_staging_absent
                and restarted is not None
                and _matches_plan(restarted, plan)
                and restarted.active_binding_ref == plan.predecessor_binding_ref
                and restarted.restarted_units == plan.dependent_units
                and predecessor is not None
                and _matches_plan(predecessor, plan)
                and predecessor.checked_binding_ref == plan.predecessor_binding_ref
                and predecessor.credential_accepted
                and predecessor.dependent_services_healthy
            )
            if proved:
                return _report(
                    plan,
                    state=CredentialRotationState.ROLLED_BACK,
                    blockers=prior.blocker_codes,
                    new_value_works=prior.new_value_works,
                    old_value_rejected=prior.old_value_rejected,
                    old_binding_restored=True,
                    candidate_material_absent=True,
                    plaintext_staging_absent=True,
                )
    except Exception:
        return _report(
            plan,
            state=CredentialRotationState.BLOCKED,
            blockers=_blockers(CredentialRotationBlocker.REPLAY_DRIFT),
        )
    return _report(
        plan,
        state=CredentialRotationState.BLOCKED,
        blockers=_blockers(CredentialRotationBlocker.REPLAY_DRIFT),
    )


def rotate_credentials(  # noqa: C901, PLR0911, PLR0912, PLR0915
    plan: CredentialRotationPlan,
    *,
    store: SealedCredentialStore,
    units: DependentUnitController,
    checker: CredentialHealthChecker,
    prior_report: CredentialRotationReport | None = None,
) -> CredentialRotationReport:
    """Execute the value-free rotation protocol through injected opaque ports."""
    if type(plan) is not CredentialRotationPlan:
        _invalid_type("credential rotation plan")
    expected = _copy_plan(plan)
    if prior_report is not None:
        return _replay_report(expected, prior_report, store, units, checker)

    stage_value: object | None
    try:
        stage_value = store.stage_candidate(_copy_plan(expected))
    except AcknowledgementLost:
        try:
            stage_value = store.read_staged_candidate(_copy_plan(expected))
        except Exception:
            stage_value = None
        if stage_value is None:
            return _rollback(
                expected,
                store,
                units,
                checker,
                initial=_blockers(CredentialRotationBlocker.ACKNOWLEDGEMENT_UNRECONCILED),
                new_value_works=False,
                old_value_rejected=False,
                force_blocked=True,
            )
    except Exception:
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.ADAPTER_FAILED),
            new_value_works=False,
            old_value_rejected=False,
            force_blocked=True,
        )
    stage = _detach_stage(stage_value)
    if stage is None or not _matches_plan(stage, expected):
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.RECEIPT_MISMATCH),
            new_value_works=False,
            old_value_rejected=False,
            force_blocked=True,
        )

    switch_value: object | None
    try:
        switch_value = store.switch_binding(
            _copy_plan(expected), cast("StageReceipt", _detach_stage(stage))
        )
    except AcknowledgementLost:
        try:
            switch_value = store.read_switched_binding(_copy_plan(expected))
        except Exception:
            switch_value = None
        if switch_value is None:
            return _rollback(
                expected,
                store,
                units,
                checker,
                initial=_blockers(CredentialRotationBlocker.ACKNOWLEDGEMENT_UNRECONCILED),
                new_value_works=False,
                old_value_rejected=False,
            )
    except Exception:
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.ADAPTER_FAILED),
            new_value_works=False,
            old_value_rejected=False,
        )
    switch = _detach_switch(switch_value)
    if (
        switch is None
        or not _matches_plan(switch, expected)
        or (switch.current_binding_ref != expected.candidate_binding_ref)
    ):
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.RECEIPT_MISMATCH),
            new_value_works=False,
            old_value_rejected=False,
        )

    restart_ack_unreconciled = False
    try:
        restarted_value: object | None = units.restart_exact(
            _copy_plan(expected), binding_ref=expected.candidate_binding_ref
        )
    except AcknowledgementLost:
        try:
            restarted_value = units.read_restart(
                _copy_plan(expected), binding_ref=expected.candidate_binding_ref
            )
        except Exception:
            restarted_value = None
        restart_ack_unreconciled = restarted_value is None
    except Exception:
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.ADAPTER_FAILED),
            new_value_works=False,
            old_value_rejected=False,
        )
    restarted = _detach_restart(restarted_value)
    restart_ack_unreconciled = restart_ack_unreconciled or (
        restarted_value is not None and restarted is None
    )
    if (
        restarted is None
        or not _matches_plan(restarted, expected)
        or (
            restarted.active_binding_ref != expected.candidate_binding_ref
            or restarted.restarted_units != expected.dependent_units
        )
    ):
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(
                CredentialRotationBlocker.ACKNOWLEDGEMENT_UNRECONCILED
                if restart_ack_unreconciled
                else CredentialRotationBlocker.RECEIPT_MISMATCH
            ),
            new_value_works=False,
            old_value_rejected=False,
        )

    try:
        candidate_value = checker.check_binding(
            _copy_plan(expected), binding_ref=expected.candidate_binding_ref
        )
    except Exception:
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.ADAPTER_FAILED),
            new_value_works=False,
            old_value_rejected=False,
        )
    candidate = _detach_authentication(candidate_value)
    if (
        candidate is None
        or not _matches_plan(candidate, expected)
        or (candidate.checked_binding_ref != expected.candidate_binding_ref)
    ):
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.RECEIPT_MISMATCH),
            new_value_works=False,
            old_value_rejected=False,
        )
    if not candidate.credential_accepted:
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.CANDIDATE_REJECTED),
            new_value_works=False,
            old_value_rejected=False,
        )
    if not candidate.dependent_services_healthy:
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.DEPENDENT_UNITS_UNHEALTHY),
            new_value_works=False,
            old_value_rejected=False,
        )

    try:
        predecessor_value = checker.check_binding(
            _copy_plan(expected), binding_ref=expected.predecessor_binding_ref
        )
    except Exception:
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.ADAPTER_FAILED),
            new_value_works=True,
            old_value_rejected=False,
        )
    predecessor = _detach_authentication(predecessor_value)
    if (
        predecessor is None
        or not _matches_plan(predecessor, expected)
        or (predecessor.checked_binding_ref != expected.predecessor_binding_ref)
    ):
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.RECEIPT_MISMATCH),
            new_value_works=True,
            old_value_rejected=False,
        )
    if not predecessor.dependent_services_healthy:
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.DEPENDENT_UNITS_UNHEALTHY),
            new_value_works=True,
            old_value_rejected=False,
            force_blocked=True,
        )
    if predecessor.credential_accepted:
        return _rollback(
            expected,
            store,
            units,
            checker,
            initial=_blockers(CredentialRotationBlocker.PREDECESSOR_STILL_ACCEPTED),
            new_value_works=True,
            old_value_rejected=False,
            force_blocked=True,
        )

    cleanup_value: object | None
    try:
        cleanup = cast("SwitchReceipt", _detach_switch(switch))
        cleanup_value = store.remove_obsolete(_copy_plan(expected), cleanup)
    except AcknowledgementLost:
        try:
            cleanup_value = store.read_cleanup(_copy_plan(expected))
        except Exception:
            cleanup_value = None
        if cleanup_value is None:
            return _report(
                expected,
                state=CredentialRotationState.BLOCKED,
                blockers=_blockers(CredentialRotationBlocker.ACKNOWLEDGEMENT_UNRECONCILED),
                new_value_works=True,
                old_value_rejected=True,
            )
    except Exception:
        return _report(
            expected,
            state=CredentialRotationState.BLOCKED,
            blockers=_blockers(CredentialRotationBlocker.ADAPTER_FAILED),
            new_value_works=True,
            old_value_rejected=True,
        )
    cleanup = _detach_cleanup(cleanup_value)
    if cleanup is None or not _matches_plan(cleanup, expected):
        return _report(
            expected,
            state=CredentialRotationState.BLOCKED,
            blockers=_blockers(CredentialRotationBlocker.RECEIPT_MISMATCH),
            new_value_works=True,
            old_value_rejected=True,
        )
    blockers: list[CredentialRotationBlocker] = []
    if not cleanup.obsolete_predecessor_absent:
        blockers.append(CredentialRotationBlocker.OBSOLETE_BINDING_REMAINS)
    if not cleanup.plaintext_staging_absent:
        blockers.append(CredentialRotationBlocker.PLAINTEXT_STAGING_REMAINS)
    if blockers:
        return _report(
            expected,
            state=CredentialRotationState.BLOCKED,
            blockers=_blockers(*blockers),
            new_value_works=True,
            old_value_rejected=True,
            obsolete_binding_absent=cleanup.obsolete_predecessor_absent,
            plaintext_staging_absent=cleanup.plaintext_staging_absent,
        )
    return _report(
        expected,
        state=CredentialRotationState.SUCCEEDED,
        blockers=(),
        new_value_works=True,
        old_value_rejected=True,
        obsolete_binding_absent=True,
        plaintext_staging_absent=True,
    )


_MANIFEST_SCHEMA = "asklegal.hk-v1-credential-manifest/v1"
_PLAN_SCHEMA = "asklegal.hk-v1-credential-rotation-plan/v1"
_AUTHORITY_SCHEMA = "asklegal.hk-v1-credential-rotation-authority/v1"
_STATE_SCHEMA = "asklegal.hk-v1-credential-rotation-state/v1"
_AUTHORITY_ID = re.compile(r"^auth_[0-9a-f]{48}$")
_MAX_LOCAL_DOCUMENT_BYTES = 1_000_000


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def credential_manifest_bytes(manifest: CredentialManifest) -> bytes:
    """Serialize the exact reference-only manifest accepted by the local CLI."""
    if type(manifest) is not CredentialManifest:
        _invalid_type("credential manifest")
    return _canonical_bytes(
        {
            "entries": [
                {
                    "credential_name": entry.credential_name,
                    "dependent_units": list(entry.dependent_units),
                }
                for entry in manifest.entries
            ],
            "manifest_fingerprint": manifest.manifest_fingerprint,
            "schema_id": _MANIFEST_SCHEMA,
        }
    )


def _manifest_entry(raw: object) -> CredentialManifestEntry:
    if type(raw) is not dict:
        _invalid_value("credential manifest")
    entry = cast("dict[str, object]", raw)
    if set(entry) != {"credential_name", "dependent_units"}:
        _invalid_value("credential manifest")
    units = entry.get("dependent_units")
    if type(units) is not list:
        _invalid_value("credential manifest")
    raw_units = cast("list[object]", units)
    if any(type(item) is not str for item in raw_units):
        _invalid_value("credential manifest")
    return CredentialManifestEntry(
        _require_credential_name(entry.get("credential_name")),
        tuple(cast("list[str]", raw_units)),
    )


def parse_credential_manifest_bytes(content: bytes) -> CredentialManifest:
    """Parse one canonical exact-key reference-only manifest from retained bytes."""
    if type(content) is not bytes or not content:
        _invalid_value("credential manifest")
    if len(content) > _MAX_LOCAL_DOCUMENT_BYTES:
        _invalid_value("credential manifest")
    try:
        value: object = json.loads(content)
    except UnicodeDecodeError, json.JSONDecodeError:
        _invalid_value("credential manifest")
    if type(value) is not dict:
        _invalid_value("credential manifest")
    document = cast("dict[str, object]", value)
    if _canonical_bytes(document) != content:
        _invalid_value("credential manifest")
    if (
        set(document) != {"entries", "manifest_fingerprint", "schema_id"}
        or document.get("schema_id") != _MANIFEST_SCHEMA
    ):
        _invalid_value("credential manifest")
    raw_entries = document.get("entries")
    if type(raw_entries) is not list:
        _invalid_value("credential manifest")
    entries = tuple(_manifest_entry(raw) for raw in cast("list[object]", raw_entries))
    fingerprint = _require_text(
        document.get("manifest_fingerprint"), _FINGERPRINT, "manifest fingerprint"
    )
    return CredentialManifest(fingerprint, entries)


def load_credential_manifest(path: Path) -> CredentialManifest:
    """Load one canonical, exact-key, reference-only manifest file."""
    return parse_credential_manifest_bytes(path.read_bytes())


def credential_rotation_plan_fingerprint(plan: CredentialRotationPlan) -> str:
    """Fingerprint every reference-only plan fact."""
    if type(plan) is not CredentialRotationPlan:
        _invalid_type("credential rotation plan")
    return (
        "sha256:"
        + hashlib.sha256(
            _canonical_bytes(
                {
                    "candidate_binding_ref": plan.candidate_binding_ref,
                    "credential_name": plan.credential_name,
                    "dependent_units": list(plan.dependent_units),
                    "manifest_fingerprint": plan.manifest_fingerprint,
                    "predecessor_binding_ref": plan.predecessor_binding_ref,
                    "rotation_id": plan.rotation_id,
                }
            )
        ).hexdigest()
    )


def credential_rotation_plan_bytes(plan: CredentialRotationPlan) -> bytes:
    """Render one value-free plan for stdout or reviewer inspection."""
    return _canonical_bytes(
        {
            "candidate_binding_ref": plan.candidate_binding_ref,
            "credential_name": plan.credential_name,
            "dependent_units": list(plan.dependent_units),
            "manifest_fingerprint": plan.manifest_fingerprint,
            "plan_fingerprint": credential_rotation_plan_fingerprint(plan),
            "predecessor_binding_ref": plan.predecessor_binding_ref,
            "rotation_id": plan.rotation_id,
            "schema_id": _PLAN_SCHEMA,
        }
    )


@dataclass(frozen=True, slots=True)
class LocalRotationLayout:
    """Explicit local sealed-binding, journal, and health-evidence paths."""

    sealed_root: Path
    predecessor_binding_dir: Path
    candidate_binding_dir: Path
    state_root: Path

    def __post_init__(self) -> None:
        """Reject aliases, broad roots, and binding references not encoded by directory names."""
        for path in (self.sealed_root, self.state_root):
            if not path.is_absolute() or path == Path(path.anchor) or path.is_symlink():
                _invalid_value("local rotation root")
        for path in (self.predecessor_binding_dir, self.candidate_binding_dir):
            if (
                not path.is_absolute()
                or path.is_symlink()
                or path.parent != self.sealed_root
                or _BINDING_REF.fullmatch(path.name) is None
            ):
                _invalid_value("sealed binding directory")
        if self.predecessor_binding_dir == self.candidate_binding_dir:
            _invalid_value("sealed binding directories")


def plan_local_rotation(
    manifest_path: Path,
    layout: LocalRotationLayout,
    *,
    credential_name: str,
    rotation_id: str,
) -> CredentialRotationPlan:
    """Build a plan from canonical manifest bytes and opaque sealed-directory names only."""
    manifest = load_credential_manifest(manifest_path)
    return plan_rotation(
        manifest,
        credential_name=credential_name,
        rotation_id=rotation_id,
        predecessor_binding_ref=layout.predecessor_binding_dir.name,
        candidate_binding_ref=layout.candidate_binding_dir.name,
    )


def _layout_fingerprint(layout: LocalRotationLayout) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            _canonical_bytes(
                {
                    "candidate_binding_dir": str(layout.candidate_binding_dir),
                    "predecessor_binding_dir": str(layout.predecessor_binding_dir),
                    "sealed_root": str(layout.sealed_root),
                    "state_root": str(layout.state_root),
                }
            )
        ).hexdigest()
    )


def _bound_document(plan: CredentialRotationPlan, phase: str) -> dict[str, object]:
    return {
        "candidate_binding_ref": plan.candidate_binding_ref,
        "credential_name": plan.credential_name,
        "dependent_units": list(plan.dependent_units),
        "manifest_fingerprint": plan.manifest_fingerprint,
        "phase": phase,
        "predecessor_binding_ref": plan.predecessor_binding_ref,
        "rotation_id": plan.rotation_id,
        "schema_id": _STATE_SCHEMA,
    }


class _LocalJournal:
    def __init__(self, root: Path, plan: CredentialRotationPlan) -> None:
        self._root = root / plan.rotation_id
        self._plan = plan

    def write(self, phase: str, extra: dict[str, object]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        document = {**_bound_document(self._plan, phase), **extra}
        target = self._root / f"{phase}.json"
        temporary = self._root / f".{phase}.tmp"
        temporary.write_bytes(_canonical_bytes(document))
        temporary.replace(target)

    def read(self, phase: str, keys: set[str]) -> dict[str, object] | None:
        path = self._root / f"{phase}.json"
        if path.is_symlink() or not path.is_file():
            return None
        content = path.read_bytes()
        if len(content) > _MAX_LOCAL_DOCUMENT_BYTES:
            return None
        try:
            value: object = json.loads(content)
        except UnicodeDecodeError, json.JSONDecodeError:
            return None
        expected = _bound_document(self._plan, phase)
        if type(value) is not dict:
            return None
        document = cast("dict[str, object]", value)
        if (
            _canonical_bytes(document) != content
            or set(document) != set(expected) | keys
            or any(document.get(key) != item for key, item in expected.items())
        ):
            return None
        return document


class FileSealedCredentialStore(SealedCredentialStore):
    """Exact filesystem binding switch; sealed bytes are never opened or copied."""

    def __init__(self, layout: LocalRotationLayout, plan: CredentialRotationPlan) -> None:
        """Bind one exact layout and plan without reading sealed bytes."""
        self._sealed_root = layout.sealed_root
        self._predecessor = self._sealed_root / plan.predecessor_binding_ref
        self._candidate = self._sealed_root / plan.candidate_binding_ref
        self._plan = plan
        self._journal = _LocalJournal(layout.state_root, plan)
        self._current = self._sealed_root / f"current-{plan.credential_name}"
        self._plaintext = self._sealed_root / "plaintext-staging" / plan.credential_name

    def _current_ref(self) -> str | None:
        if not self._current.is_symlink():
            return None
        target = str(self._current.readlink())
        return target if _BINDING_REF.fullmatch(target) is not None else None

    def _switch(self, binding_ref: str) -> None:
        target = self._sealed_root / binding_ref
        if target.is_symlink() or not target.is_dir():
            _invalid_value("sealed binding unavailable")
        temporary = self._current.with_name(f".{self._current.name}.tmp")
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
        temporary.symlink_to(binding_ref)
        temporary.replace(self._current)
        if self._current_ref() != binding_ref:
            raise AcknowledgementLost

    def _remove(self, path: Path, expected_ref: str) -> bool:
        if path != self._sealed_root / expected_ref or path.is_symlink():
            return False
        if path.exists():
            shutil.rmtree(path)
        return not path.exists()

    def stage_candidate(self, plan: CredentialRotationPlan) -> StageReceipt:
        """Prove the sealed candidate and predecessor pointer before staging."""
        if (
            not _matches_plan(plan, self._plan)
            or self._current_ref() != plan.predecessor_binding_ref
            or not self._predecessor.is_dir()
            or not self._candidate.is_dir()
            or self._plaintext.exists()
        ):
            _invalid_value("sealed stage unavailable")
        receipt = StageReceipt(**_receipt_kwargs(plan))
        self._journal.write("stage", {})
        return receipt

    def read_staged_candidate(self, plan: CredentialRotationPlan) -> StageReceipt | None:
        """Reread one exact retained stage receipt."""
        if not _matches_plan(plan, self._plan) or self._journal.read("stage", set()) is None:
            return None
        return StageReceipt(**_receipt_kwargs(plan))

    def switch_binding(self, plan: CredentialRotationPlan, stage: StageReceipt) -> SwitchReceipt:
        """Atomically switch the reference-only current-binding symlink."""
        if not _matches_plan(plan, self._plan) or not _matches_plan(stage, plan):
            _invalid_value("sealed switch unavailable")
        self._switch(plan.candidate_binding_ref)
        self._journal.write("switch", {"current_binding_ref": plan.candidate_binding_ref})
        return SwitchReceipt(
            **_receipt_kwargs(plan), current_binding_ref=plan.candidate_binding_ref
        )

    def read_switched_binding(self, plan: CredentialRotationPlan) -> SwitchReceipt | None:
        """Reread both the switch receipt and current-binding symlink."""
        document = self._journal.read("switch", {"current_binding_ref"})
        if (
            not _matches_plan(plan, self._plan)
            or document is None
            or document.get("current_binding_ref") != plan.candidate_binding_ref
            or self._current_ref() != plan.candidate_binding_ref
        ):
            return None
        return SwitchReceipt(
            **_receipt_kwargs(plan), current_binding_ref=plan.candidate_binding_ref
        )

    def remove_obsolete(
        self, plan: CredentialRotationPlan, switch: SwitchReceipt
    ) -> CleanupReceipt:
        """Remove only the exact predecessor after successful rejection proof."""
        if not _matches_plan(plan, self._plan) or not _matches_plan(switch, plan):
            _invalid_value("sealed cleanup unavailable")
        obsolete_absent = self._remove(self._predecessor, plan.predecessor_binding_ref)
        plaintext_absent = not self._plaintext.exists()
        self._journal.write(
            "cleanup",
            {
                "obsolete_predecessor_absent": obsolete_absent,
                "plaintext_staging_absent": plaintext_absent,
            },
        )
        return CleanupReceipt(
            **_receipt_kwargs(plan),
            obsolete_predecessor_absent=obsolete_absent,
            plaintext_staging_absent=plaintext_absent,
        )

    def read_cleanup(self, plan: CredentialRotationPlan) -> CleanupReceipt | None:
        """Reread cleanup and independently prove filesystem absence."""
        document = self._journal.read(
            "cleanup", {"obsolete_predecessor_absent", "plaintext_staging_absent"}
        )
        if not _matches_plan(plan, self._plan) or document is None:
            return None
        return CleanupReceipt(
            **_receipt_kwargs(plan),
            obsolete_predecessor_absent=(
                document.get("obsolete_predecessor_absent") is True
                and not self._predecessor.exists()
            ),
            plaintext_staging_absent=(
                document.get("plaintext_staging_absent") is True and not self._plaintext.exists()
            ),
        )

    def restore_predecessor(self, plan: CredentialRotationPlan) -> RollbackReceipt:
        """Restore the predecessor pointer and remove only the exact candidate."""
        if not _matches_plan(plan, self._plan):
            _invalid_value("sealed rollback unavailable")
        self._switch(plan.predecessor_binding_ref)
        candidate_absent = self._remove(self._candidate, plan.candidate_binding_ref)
        plaintext_absent = not self._plaintext.exists()
        restored = self._current_ref() == plan.predecessor_binding_ref
        self._journal.write(
            "rollback",
            {
                "candidate_material_absent": candidate_absent,
                "plaintext_staging_absent": plaintext_absent,
                "predecessor_binding_restored": restored,
            },
        )
        return RollbackReceipt(
            **_receipt_kwargs(plan),
            predecessor_binding_restored=restored,
            candidate_material_absent=candidate_absent,
            plaintext_staging_absent=plaintext_absent,
        )

    def read_rollback(self, plan: CredentialRotationPlan) -> RollbackReceipt | None:
        """Reread rollback and independently prove exact filesystem state."""
        document = self._journal.read(
            "rollback",
            {
                "candidate_material_absent",
                "plaintext_staging_absent",
                "predecessor_binding_restored",
            },
        )
        if not _matches_plan(plan, self._plan) or document is None:
            return None
        return RollbackReceipt(
            **_receipt_kwargs(plan),
            predecessor_binding_restored=(
                document.get("predecessor_binding_restored") is True
                and self._current_ref() == plan.predecessor_binding_ref
            ),
            candidate_material_absent=(
                document.get("candidate_material_absent") is True and not self._candidate.exists()
            ),
            plaintext_staging_absent=(
                document.get("plaintext_staging_absent") is True and not self._plaintext.exists()
            ),
        )


class _ReceiptKwargs(TypedDict):
    rotation_id: str
    manifest_fingerprint: str
    credential_name: str
    predecessor_binding_ref: str
    candidate_binding_ref: str
    dependent_units: tuple[str, ...]


def _receipt_kwargs(plan: CredentialRotationPlan) -> _ReceiptKwargs:
    return {
        "candidate_binding_ref": plan.candidate_binding_ref,
        "credential_name": plan.credential_name,
        "dependent_units": plan.dependent_units,
        "manifest_fingerprint": plan.manifest_fingerprint,
        "predecessor_binding_ref": plan.predecessor_binding_ref,
        "rotation_id": plan.rotation_id,
    }


class SystemCommandRunner(Protocol):
    """Value-free system command boundary."""

    def run(self, arguments: tuple[str, ...]) -> bool:
        """Run exact non-secret arguments and return only terminal success."""
        ...


class QuietSubprocessRunner:
    """No-shell, no-output runner used only after exact execution authority."""

    def run(self, arguments: tuple[str, ...]) -> bool:
        """Discard command output so adapter failures cannot leak credential material."""
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


class SystemdDependentUnitController(DependentUnitController):
    """Exact systemd restart adapter with value-free retained acknowledgement."""

    def __init__(
        self, runner: SystemCommandRunner, state_root: Path, plan: CredentialRotationPlan
    ) -> None:
        """Bind an injected runner and one exact value-free journal."""
        self._runner = runner
        self._plan = plan
        self._journal = _LocalJournal(state_root, plan)

    def restart_exact(self, plan: CredentialRotationPlan, *, binding_ref: str) -> RestartReceipt:
        """Restart exactly the manifest-bound dependent units and retain receipt."""
        if not _matches_plan(plan, self._plan) or binding_ref not in {
            plan.predecessor_binding_ref,
            plan.candidate_binding_ref,
        }:
            _invalid_value("systemd restart unavailable")
        if not self._runner.run(("/usr/bin/systemctl", "restart", *plan.dependent_units)):
            _invalid_value("systemd restart failed")
        phase = f"restart-{binding_ref}"
        self._journal.write(
            phase,
            {"active_binding_ref": binding_ref, "restarted_units": list(plan.dependent_units)},
        )
        return RestartReceipt(
            **_receipt_kwargs(plan),
            active_binding_ref=binding_ref,
            restarted_units=plan.dependent_units,
        )

    def read_restart(
        self, plan: CredentialRotationPlan, *, binding_ref: str
    ) -> RestartReceipt | None:
        """Reread one exact retained restart receipt without restarting."""
        phase = f"restart-{binding_ref}"
        document = self._journal.read(phase, {"active_binding_ref", "restarted_units"})
        if (
            not _matches_plan(plan, self._plan)
            or document is None
            or document.get("active_binding_ref") != binding_ref
            or document.get("restarted_units") != list(plan.dependent_units)
        ):
            return None
        return RestartReceipt(
            **_receipt_kwargs(plan),
            active_binding_ref=binding_ref,
            restarted_units=plan.dependent_units,
        )


class SystemdCredentialHealthChecker(CredentialHealthChecker):
    """Fixed credential-authentication helper plus live systemd health."""

    def __init__(
        self,
        runner: SystemCommandRunner,
        sealed_root: Path,
        plan: CredentialRotationPlan,
    ) -> None:
        """Bind the sealed root and injected no-output command runner."""
        self._runner = runner
        self._plan = plan
        self._sealed_root = sealed_root

    def check_binding(
        self, plan: CredentialRotationPlan, *, binding_ref: str
    ) -> AuthenticationReceipt:
        """Combine exact acceptance evidence with every dependent unit's health."""
        if not _matches_plan(plan, self._plan):
            _invalid_value("health check unavailable")
        accepted = self._runner.run(
            (
                "/usr/local/libexec/asklegal-credential-health",
                "authenticate",
                "--credential-name",
                plan.credential_name,
                "--sealed-root",
                str(self._sealed_root),
                "--binding-ref",
                binding_ref,
            )
        )
        healthy = all(
            self._runner.run(("/usr/bin/systemctl", "is-active", "--quiet", unit))
            for unit in plan.dependent_units
        )
        return AuthenticationReceipt(
            **_receipt_kwargs(plan),
            checked_binding_ref=binding_ref,
            credential_accepted=accepted,
            dependent_services_healthy=healthy,
        )


def _load_execution_authority(
    path: Path, plan: CredentialRotationPlan, layout: LocalRotationLayout
) -> None:
    content = path.read_bytes()
    if len(content) > _MAX_LOCAL_DOCUMENT_BYTES:
        _invalid_value("rotation authority")
    value: object = json.loads(content)
    expected = {
        "authorized": True,
        "manifest_fingerprint": plan.manifest_fingerprint,
        "layout_fingerprint": _layout_fingerprint(layout),
        "plan_fingerprint": credential_rotation_plan_fingerprint(plan),
        "rotation_id": plan.rotation_id,
        "schema_id": _AUTHORITY_SCHEMA,
    }
    if type(value) is not dict:
        _invalid_value("rotation authority")
    document = cast("dict[str, object]", value)
    if (
        set(document) != set(expected) | {"authority_id"}
        or any(document.get(key) != item for key, item in expected.items())
        or _AUTHORITY_ID.fullmatch(str(document.get("authority_id"))) is None
        or _canonical_bytes(document) != content
    ):
        _invalid_value("rotation authority")


def execution_authority_bytes(
    plan: CredentialRotationPlan,
    layout: LocalRotationLayout,
    *,
    authority_id: str,
) -> bytes:
    """Freeze the exact value-free authority an operator must review and supply."""
    _require_text(authority_id, _AUTHORITY_ID, "authority ID")
    return _canonical_bytes(
        {
            "authority_id": authority_id,
            "authorized": True,
            "layout_fingerprint": _layout_fingerprint(layout),
            "manifest_fingerprint": plan.manifest_fingerprint,
            "plan_fingerprint": credential_rotation_plan_fingerprint(plan),
            "rotation_id": plan.rotation_id,
            "schema_id": _AUTHORITY_SCHEMA,
        }
    )


def _report_document(report: CredentialRotationReport) -> dict[str, object]:
    return {
        "blocker_codes": [code.value for code in report.blocker_codes],
        "candidate_binding_ref": report.candidate_binding_ref,
        "candidate_material_absent": report.candidate_material_absent,
        "complete": report.complete,
        "credential_name": report.credential_name,
        "dependent_units": list(report.dependent_units),
        "manifest_fingerprint": report.manifest_fingerprint,
        "new_value_works": report.new_value_works,
        "obsolete_binding_absent": report.obsolete_binding_absent,
        "old_binding_restored": report.old_binding_restored,
        "old_value_rejected": report.old_value_rejected,
        "plaintext_staging_absent": report.plaintext_staging_absent,
        "predecessor_binding_ref": report.predecessor_binding_ref,
        "rotation_id": report.rotation_id,
        "schema_id": "asklegal.hk-v1-credential-rotation-report/v1",
        "state": report.state.value,
    }


def _report_bytes(report: CredentialRotationReport) -> bytes:
    return _canonical_bytes(_report_document(report))


def credential_rotation_report_bytes(report: CredentialRotationReport) -> bytes:
    """Serialize one validated terminal rotation report for retained evidence."""
    if type(report) is not CredentialRotationReport:
        _invalid_type("credential rotation report")
    return _report_bytes(report)


def _retained_report_document(path: Path) -> tuple[dict[str, object], bytes] | None:
    if path.is_symlink() or not path.is_file():
        return None
    content = path.read_bytes()
    if len(content) > _MAX_LOCAL_DOCUMENT_BYTES:
        return None
    try:
        value: object = json.loads(content)
    except UnicodeDecodeError, json.JSONDecodeError:
        return None
    if type(value) is not dict:
        return None
    return cast("dict[str, object]", value), content


def parse_credential_rotation_report_bytes(content: bytes) -> CredentialRotationReport:
    """Reconstruct one canonical terminal report without trusting its summary flags."""
    if type(content) is not bytes or not content or len(content) > _MAX_LOCAL_DOCUMENT_BYTES:
        _invalid_value("credential rotation report")
    try:
        value: object = json.loads(content)
    except UnicodeDecodeError, json.JSONDecodeError:
        _invalid_value("credential rotation report")
    if type(value) is not dict:
        _invalid_value("credential rotation report")
    document = cast("dict[str, object]", value)
    raw_blockers = document.get("blocker_codes")
    raw_units = document.get("dependent_units")
    if type(raw_blockers) is not list or type(raw_units) is not list:
        _invalid_value("credential rotation report")
    try:
        report = CredentialRotationReport(
            rotation_id=_require_text(document.get("rotation_id"), _ROTATION_ID, "rotation ID"),
            manifest_fingerprint=_require_text(
                document.get("manifest_fingerprint"), _FINGERPRINT, "manifest fingerprint"
            ),
            credential_name=_require_credential_name(document.get("credential_name")),
            predecessor_binding_ref=_require_text(
                document.get("predecessor_binding_ref"), _BINDING_REF, "binding reference"
            ),
            candidate_binding_ref=_require_text(
                document.get("candidate_binding_ref"), _BINDING_REF, "binding reference"
            ),
            dependent_units=tuple(cast("list[str]", raw_units)),
            state=CredentialRotationState(str(document.get("state"))),
            complete=document.get("complete") is True,
            new_value_works=document.get("new_value_works") is True,
            old_value_rejected=document.get("old_value_rejected") is True,
            old_binding_restored=document.get("old_binding_restored") is True,
            candidate_material_absent=document.get("candidate_material_absent") is True,
            obsolete_binding_absent=document.get("obsolete_binding_absent") is True,
            plaintext_staging_absent=document.get("plaintext_staging_absent") is True,
            blocker_codes=tuple(
                CredentialRotationBlocker(str(item)) for item in cast("list[object]", raw_blockers)
            ),
        )
    except TypeError, ValueError:
        _invalid_value("credential rotation report")
    if (
        document.get("schema_id") != "asklegal.hk-v1-credential-rotation-report/v1"
        or set(document) != set(_report_document(report))
        or _canonical_bytes(document) != content
        or _report_document(report) != document
    ):
        _invalid_value("credential rotation report")
    return report


def _retained_report(path: Path, plan: CredentialRotationPlan) -> CredentialRotationReport | None:
    retained = _retained_report_document(path)
    if retained is None:
        return None
    _document, content = retained
    try:
        report = parse_credential_rotation_report_bytes(content)
    except TypeError, ValueError:
        return None
    if not _matches_plan(report, plan):
        return None
    return report


def _retain_report(path: Path, report: CredentialRotationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(_report_bytes(report))
    temporary.replace(path)


def execute_local_rotation(
    plan: CredentialRotationPlan,
    layout: LocalRotationLayout,
    authority_path: Path,
    *,
    runner: SystemCommandRunner,
    prior_report: CredentialRotationReport | None = None,
) -> CredentialRotationReport:
    """Compose exact filesystem/systemd/health adapters after authority validation."""
    _load_execution_authority(authority_path, plan, layout)
    report_path = layout.state_root / plan.rotation_id / "report.json"
    retained = prior_report or _retained_report(report_path, plan)
    report = rotate_credentials(
        plan,
        store=FileSealedCredentialStore(layout, plan),
        units=SystemdDependentUnitController(runner, layout.state_root, plan),
        checker=SystemdCredentialHealthChecker(
            runner,
            layout.sealed_root,
            plan,
        ),
        prior_report=retained,
    )
    _retain_report(report_path, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan one exact local V1 credential rotation")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--credential-name", required=True)
    parser.add_argument("--rotation-id", required=True)
    parser.add_argument("--sealed-root", required=True, type=Path)
    parser.add_argument("--predecessor-binding-dir", required=True, type=Path)
    parser.add_argument("--candidate-binding-dir", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authority", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Plan by default; execute only with one exact detached authority file."""
    arguments = _parser().parse_args(argv)
    try:
        layout = LocalRotationLayout(
            arguments.sealed_root,
            arguments.predecessor_binding_dir,
            arguments.candidate_binding_dir,
            arguments.state_root,
        )
        plan = plan_local_rotation(
            arguments.manifest,
            layout,
            credential_name=arguments.credential_name,
            rotation_id=arguments.rotation_id,
        )
        if not arguments.execute:
            sys.stdout.buffer.write(credential_rotation_plan_bytes(plan) + b"\n")
            return 0
        if type(arguments.authority) is not Path:
            _invalid_value("rotation authority")
        report = execute_local_rotation(
            plan,
            layout,
            arguments.authority,
            runner=QuietSubprocessRunner(),
        )
        sys.stdout.buffer.write(_report_bytes(report) + b"\n")
    except Exception:
        sys.stdout.buffer.write(
            b'{"blocker_code":"ROTATION_INPUT_NOT_READY","state":"NOT_READY"}\n'
        )
        return 2
    else:
        return 0 if report.complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
