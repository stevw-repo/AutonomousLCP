"""Plan and prove bounded Hong Kong V1 recovery without implicit live effects.

PREFLIGHT and the local prototype are effect-free; PLAN_LIVE freezes seven steps.
EXECUTE_LIVE requires matching detached authority and composes only the fixed SQL,
immutable-vault, and Scheduler adapters; missing inputs stop before external effects.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import NoReturn, Protocol, cast

from asklegal_evidence_vault import (
    ArtifactClass,
    ArtifactDescriptor,
    EvidenceManifest,
    EvidenceManifestEntry,
    EvidencePackageReceipt,
    ExactObjectReference,
    LocalImmutableVault,
    RecoveryCopyReceipt,
    RetentionProfile,
    VaultName,
)

__all__ = [
    "FilesystemSQLRecoveryAdapter",
    "FilesystemSchedulerRecoveryAdapter",
    "FilesystemVaultRecoveryAdapter",
    "HKV1RecoveryContractAssessment",
    "ImmutableVaultLiveRecoveryPort",
    "LeastPrivilegeProbe",
    "LeastPrivilegeProbeKind",
    "LeastPrivilegeProbeResult",
    "LiveRecoveryAcknowledgementLost",
    "LiveRecoveryExecutionAdapters",
    "LiveRecoveryExecutionError",
    "LiveRecoveryExecutionResult",
    "LiveRecoveryStep",
    "LiveRecoveryStepPort",
    "LiveRecoveryStepReceipt",
    "LocalRecoveryAdapters",
    "LocalRecoveryConfiguration",
    "LocalRecoveryMode",
    "LocalRecoveryRunResult",
    "LocalRecoveryStatus",
    "LocalRecoveryTargets",
    "MigrationReadback",
    "RecoveryBlockerCode",
    "RecoveryContractRequest",
    "RecoveryDimensionResult",
    "RecoveryEvidenceReference",
    "RecoveryProofError",
    "RecoveryProofErrorCode",
    "RecoveryResultCode",
    "RegisterFamilyReadback",
    "SQLRestoreObservation",
    "SchedulerHubInventory",
    "SchedulerRecoveryMode",
    "SchedulerReplacementLeg",
    "SchedulerReplacementObservation",
    "SchedulerRole",
    "SealedCredentialReference",
    "VaultRestoreObservation",
    "VaultRestoredObject",
    "assess_local_recovery_contract",
    "build_live_recovery_credential_manifest",
    "build_live_recovery_plan",
    "build_live_recovery_request",
    "build_local_scheduler_snapshot",
    "build_local_sql_snapshot",
    "derive_local_recovery_targets",
    "execute_live_recovery",
    "freeze_local_recovery_contract",
    "load_live_recovery_request",
    "main",
    "run_local_recovery",
    "write_local_recovery_result",
]

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPAQUE = re.compile(r"^r_[0-9a-f]{32}$")
_MIGRATION = re.compile(r"^m_[0-9]{6}$")
_FAMILY = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
_REQUESTS: dict[int, tuple[RecoveryContractRequest, tuple[object, ...]]] = {}
_LOCAL_INPUT_SCHEMA = "asklegal.hk-v1-local-recovery-input/v1"
_LOCAL_RESULT_SCHEMA = "asklegal.hk-v1-local-recovery-result/v1"
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_LIVE_PLAN_SCHEMA = "asklegal.hk-v1-live-recovery-plan/v1"
_LIVE_REQUEST_SCHEMA = "asklegal.hk-v1-live-recovery-request/v1"
_LIVE_AUTHORITY_SCHEMA = "asklegal.hk-v1-live-recovery-authority/v1"
_LIVE_CREDENTIAL_SCHEMA = "asklegal.hk-v1-live-recovery-credentials/v1"
_LIVE_STATE_SCHEMA = "asklegal.hk-v1-live-recovery-state/v1"
_LIVE_RESULT_SCHEMA = "asklegal.hk-v1-live-recovery-execution-result/v1"
_LIVE_CREDENTIAL_IDS = (
    "PRIMARY_VAULT_RECOVERY_READER",
    "RECOVERY_VAULT_RECOVERY_READER",
    "SCHEDULER_GENERAL_RECOVERY_ADMIN",
    "SCHEDULER_PROMOTION_RECOVERY_ADMIN",
    "SQL_SERVER_RECOVERY_ADMIN",
)


class SchedulerRole(StrEnum):  # noqa: D101
    GENERAL = "GENERAL"
    PROMOTION = "PROMOTION"


class RecoveryResultCode(StrEnum):  # noqa: D101
    LOCAL_RECOVERY_CONTRACT_PROVED = "LOCAL_RECOVERY_CONTRACT_PROVED"
    LOCAL_RECOVERY_CONTRACT_WITHHELD = "LOCAL_RECOVERY_CONTRACT_WITHHELD"


class RecoveryBlockerCode(StrEnum):  # noqa: D101
    SCHEDULER_NOT_INDEPENDENT = "SCHEDULER_NOT_INDEPENDENT"
    SCHEDULER_REPLACEMENT_FAILED = "SCHEDULER_REPLACEMENT_FAILED"
    SCHEDULER_REPLACEMENT_UNRUN = "SCHEDULER_REPLACEMENT_UNRUN"
    SCHEDULER_ROLE_MISSING = "SCHEDULER_ROLE_MISSING"
    SQL_ENGINE_RESTORE_UNRUN = "SQL_ENGINE_RESTORE_UNRUN"
    SQL_RESTORE_READBACK_FAILED = "SQL_RESTORE_READBACK_FAILED"
    VAULT_CLEAN_ROOM_RESTORE_UNRUN = "VAULT_CLEAN_ROOM_RESTORE_UNRUN"
    VAULT_RESTORE_READBACK_FAILED = "VAULT_RESTORE_READBACK_FAILED"


class RecoveryProofErrorCode(StrEnum):  # noqa: D101
    INPUT_INVALID = "RECOVERY_PROOF_INPUT_INVALID"
    ISSUER_REQUIRED = "RECOVERY_PROOF_ISSUER_REQUIRED"


class LeastPrivilegeProbeKind(StrEnum):  # noqa: D101
    READ = "READ"
    PROCEDURE_EXECUTE = "PROCEDURE_EXECUTE"
    DIRECT_DML = "DIRECT_DML"
    CROSS_ROLE = "CROSS_ROLE"


class LeastPrivilegeProbeResult(StrEnum):  # noqa: D101
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"


class RecoveryDimensionResult(StrEnum):  # noqa: D101
    PROVED = "PROVED"
    WITHHELD = "WITHHELD"


class SchedulerRecoveryMode(StrEnum):  # noqa: D101
    REPLACEMENT_FROM_SAFE_CHECKPOINT = "REPLACEMENT_FROM_SAFE_CHECKPOINT"
    HISTORY_RESUMED = "HISTORY_RESUMED"
    HISTORY_COPIED = "HISTORY_COPIED"


class RecoveryProofError(ValueError):
    """A closed, cause-free invalid-contract error."""

    code: RecoveryProofErrorCode

    def __init__(self, code: RecoveryProofErrorCode) -> None:  # noqa: D107
        self.code = code
        super().__init__(code.value)


class _EmbeddedOrdinaryFailure(Exception):
    """Private signal that a nested input carried one ordinary exception value."""


class _ValidationContext(StrEnum):
    PUBLIC_CONSTRUCTOR = "PUBLIC_CONSTRUCTOR"
    TRAVERSAL = "TRAVERSAL"


def _visible(value: object, *, context: _ValidationContext = _ValidationContext.TRAVERSAL) -> None:
    if isinstance(value, BaseException):
        if isinstance(value, Exception):
            if context is _ValidationContext.PUBLIC_CONSTRUCTOR:
                _invalid()
            raise _EmbeddedOrdinaryFailure from None
        raise value


def _field(value: object, attribute: str) -> object:
    _visible(value)
    candidate = getattr(value, attribute)
    _visible(candidate)
    return candidate


def _invalid() -> NoReturn:
    raise RecoveryProofError(RecoveryProofErrorCode.INPUT_INVALID)


def _constructor_values(*values: object) -> None:
    for value in values:
        _visible(value, context=_ValidationContext.PUBLIC_CONSTRUCTOR)
        if type(value) is tuple:
            _constructor_values(*cast("tuple[object, ...]", value))


def _exact_tuple(value: object) -> tuple[object, ...]:
    _visible(value)
    if type(value) is not tuple:
        _invalid()
    return cast("tuple[object, ...]", value)


def _fingerprint(value: object) -> str:
    _visible(value)
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        _invalid()
    return value


def _opaque(value: object) -> str:
    _visible(value)
    if type(value) is not str or _OPAQUE.fullmatch(value) is None:
        _invalid()
    return value


def _migration(value: object) -> str:
    _visible(value)
    if type(value) is not str or _MIGRATION.fullmatch(value) is None:
        _invalid()
    return value


def _family(value: object) -> str:
    _visible(value)
    if type(value) is not str or _FAMILY.fullmatch(value) is None:
        _invalid()
    return value


def _count(value: object) -> int:
    _visible(value)
    if type(value) is not int or value < 0:
        _invalid()
    return value


def _closed_instance[ExactValue](value: object, expected: type[ExactValue]) -> ExactValue:
    _visible(value)
    if type(value) is not expected:
        _invalid()
    return value


def _enum[ExactEnum: StrEnum](value: object, expected: type[ExactEnum]) -> ExactEnum:
    _visible(value)
    if type(value) is not expected:
        _invalid()
    return value


def _string(value: object) -> str:
    _visible(value)
    if type(value) is not str:
        _invalid()
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "ascii"
    )


def _digest(value: object) -> str:
    return f"sha256:{sha256(_canonical(value)).hexdigest()}"


class _ClosedValue:
    """Permit declaration of direct value records, but not their subclasses."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        if _ClosedValue not in cls.__bases__:
            message = "recovery value records are not subclassable"
            raise TypeError(message)
        super().__init_subclass__(**kwargs)


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceReference(_ClosedValue):  # noqa: D101
    evidence_id: str
    fingerprint: str

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(self.evidence_id, self.fingerprint)
        _opaque(self.evidence_id)
        _fingerprint(self.fingerprint)


@dataclass(frozen=True, slots=True)
class MigrationReadback(_ClosedValue):  # noqa: D101
    migration_id: str
    package_fingerprint: str

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(self.migration_id, self.package_fingerprint)
        _migration(self.migration_id)
        _fingerprint(self.package_fingerprint)


@dataclass(frozen=True, slots=True)
class RegisterFamilyReadback(_ClosedValue):  # noqa: D101
    family: str
    row_count: int
    content_fingerprint: str

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(self.family, self.row_count, self.content_fingerprint)
        _family(self.family)
        _count(self.row_count)
        _fingerprint(self.content_fingerprint)


@dataclass(frozen=True, slots=True)
class SchedulerHubInventory(_ClosedValue):  # noqa: D101
    role: SchedulerRole
    hubs: tuple[str, ...]

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(self.role, self.hubs)
        _enum(self.role, SchedulerRole)
        hubs = tuple(_opaque(item) for item in _exact_tuple(self.hubs))
        if not hubs:
            _invalid()
        if tuple(sorted(hubs)) != hubs or len(set(hubs)) != len(hubs):
            _invalid()


@dataclass(frozen=True, slots=True)
class LeastPrivilegeProbe(_ClosedValue):  # noqa: D101
    kind: LeastPrivilegeProbeKind
    result: LeastPrivilegeProbeResult

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(self.kind, self.result)
        _enum(self.kind, LeastPrivilegeProbeKind)
        _enum(self.result, LeastPrivilegeProbeResult)


@dataclass(frozen=True, slots=True)
class SQLRestoreObservation(_ClosedValue):  # noqa: D101
    request_fingerprint: str
    backup_reference: RecoveryEvidenceReference
    source_database_identity: str
    restored_database_identity: str
    source_migrations: tuple[MigrationReadback, ...]
    restored_migrations: tuple[MigrationReadback, ...]
    source_families: tuple[RegisterFamilyReadback, ...]
    restored_families: tuple[RegisterFamilyReadback, ...]
    projection_rebuild_fingerprint: str
    external_ledger_digest_reference: RecoveryEvidenceReference
    source_ledger_verification_receipt: RecoveryEvidenceReference
    restored_ledger_verification_receipt: RecoveryEvidenceReference
    least_privilege_probes: tuple[LeastPrivilegeProbe, ...]

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(
            self.request_fingerprint,
            self.backup_reference,
            self.source_database_identity,
            self.restored_database_identity,
            self.source_migrations,
            self.restored_migrations,
            self.source_families,
            self.restored_families,
            self.projection_rebuild_fingerprint,
            self.external_ledger_digest_reference,
            self.source_ledger_verification_receipt,
            self.restored_ledger_verification_receipt,
            self.least_privilege_probes,
        )


@dataclass(frozen=True, slots=True)
class VaultRestoredObject(_ClosedValue):  # noqa: D101
    source_logical_key: str
    source_version: str
    source_fingerprint: str
    source_byte_length: int
    target_identity: str
    target_version: str
    reread_fingerprint: str
    reread_byte_length: int

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(
            self.source_logical_key,
            self.source_version,
            self.source_fingerprint,
            self.source_byte_length,
            self.target_identity,
            self.target_version,
            self.reread_fingerprint,
            self.reread_byte_length,
        )


@dataclass(frozen=True, slots=True)
class VaultRestoreObservation(_ClosedValue):  # noqa: D101
    request_fingerprint: str
    clean_room_target_identity: str
    restored_objects: tuple[VaultRestoredObject, ...]

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(
            self.request_fingerprint,
            self.clean_room_target_identity,
            self.restored_objects,
        )


@dataclass(frozen=True, slots=True)
class SchedulerReplacementLeg(_ClosedValue):  # noqa: D101
    role: SchedulerRole
    hubs: tuple[str, ...]
    lost_instance_identity: str
    replacement_instance_identity: str
    old_lineage_identity: str
    recovery_lineage_identity: str
    safe_checkpoint_reference: RecoveryEvidenceReference
    old_lineage_fence_receipt: RecoveryEvidenceReference
    effect_reconciliation_receipts: tuple[RecoveryEvidenceReference, ...]
    replacement_start_result_receipt: RecoveryEvidenceReference
    old_lineage_resumption_denied_receipt: RecoveryEvidenceReference
    mode: SchedulerRecoveryMode

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(
            self.role,
            self.hubs,
            self.lost_instance_identity,
            self.replacement_instance_identity,
            self.old_lineage_identity,
            self.recovery_lineage_identity,
            self.safe_checkpoint_reference,
            self.old_lineage_fence_receipt,
            self.effect_reconciliation_receipts,
            self.replacement_start_result_receipt,
            self.old_lineage_resumption_denied_receipt,
            self.mode,
        )


@dataclass(frozen=True, slots=True)
class SchedulerReplacementObservation(_ClosedValue):  # noqa: D101
    role: SchedulerRole
    forward: SchedulerReplacementLeg
    reverse: SchedulerReplacementLeg

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(self.role, self.forward, self.reverse)


@dataclass(frozen=True, slots=True)
class RecoveryContractRequest(_ClosedValue):  # noqa: D101
    migration_prefix: tuple[MigrationReadback, ...]
    register_families: tuple[RegisterFamilyReadback, ...]
    sql_backup_reference: RecoveryEvidenceReference
    external_ledger_digest_reference: RecoveryEvidenceReference
    source_ledger_verification_receipt: RecoveryEvidenceReference
    restored_ledger_verification_receipt: RecoveryEvidenceReference
    vault_package_receipt: EvidencePackageReceipt
    primary_vault_identity: str
    recovery_vault_identity: str
    scheduler_hubs: tuple[SchedulerHubInventory, ...]
    projection_rebuild_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:  # noqa: D105
        _constructor_values(
            self.migration_prefix,
            self.register_families,
            self.sql_backup_reference,
            self.external_ledger_digest_reference,
            self.source_ledger_verification_receipt,
            self.restored_ledger_verification_receipt,
            self.vault_package_receipt,
            self.primary_vault_identity,
            self.recovery_vault_identity,
            self.scheduler_hubs,
            self.projection_rebuild_fingerprint,
            self.fingerprint,
        )


@dataclass(frozen=True, slots=True, init=False)
class HKV1RecoveryContractAssessment(_ClosedValue):  # noqa: D101
    result_code: RecoveryResultCode
    sql_result: RecoveryDimensionResult
    vault_result: RecoveryDimensionResult
    scheduler_result: RecoveryDimensionResult
    contract_proved: bool
    blockers: tuple[RecoveryBlockerCode, ...]
    fingerprint: str
    canonical_bytes: bytes
    gate_f_eligible: bool

    def __init__(self, **_arguments: object) -> None:  # noqa: D107
        raise RecoveryProofError(RecoveryProofErrorCode.ISSUER_REQUIRED)


def _reference(value: object) -> tuple[str, str]:
    item = _closed_instance(value, RecoveryEvidenceReference)
    return (_opaque(item.evidence_id), _fingerprint(item.fingerprint))


def _migrations(value: object) -> tuple[tuple[str, str], ...]:
    rows = _exact_tuple(value)
    output: list[tuple[str, str]] = []
    for item in rows:
        row = _closed_instance(item, MigrationReadback)
        output.append((_migration(row.migration_id), _fingerprint(row.package_fingerprint)))
    if not output or len({row[0] for row in output}) != len(output):
        _invalid()
    return tuple(output)


def _families(value: object) -> tuple[tuple[str, int, str], ...]:
    rows = _exact_tuple(value)
    output: list[tuple[str, int, str]] = []
    for item in rows:
        row = _closed_instance(item, RegisterFamilyReadback)
        output.append(
            (_family(row.family), _count(row.row_count), _fingerprint(row.content_fingerprint))
        )
    if (
        not output
        or tuple(sorted(output)) != tuple(output)
        or len({row[0] for row in output}) != len(output)
    ):
        _invalid()
    return tuple(output)


def _vault_reference(value: object, vault: VaultName) -> tuple[str, str, str, int]:
    reference = _closed_instance(value, ExactObjectReference)
    if _enum(_field(reference, "vault"), VaultName) is not vault:
        _invalid()
    return (
        _string(_field(reference, "logical_key")),
        _string(_field(reference, "version_id")),
        _fingerprint(_field(reference, "fingerprint")),
        _count(_field(reference, "byte_length")),
    )


def _receipt_inventory(value: object) -> tuple[tuple[str, str, str, int], ...]:
    receipt = _closed_instance(value, EvidencePackageReceipt)
    manifest = _field(receipt, "manifest")
    entries = _exact_tuple(_field(manifest, "entries"))
    copies = _exact_tuple(_field(receipt, "copies"))
    primary_manifest = _vault_reference(_field(receipt, "primary_manifest"), VaultName.PRIMARY)
    recovery_manifest = _vault_reference(_field(receipt, "recovery_manifest"), VaultName.RECOVERY)
    if primary_manifest[2:] != recovery_manifest[2:]:
        _invalid()
    expected: list[tuple[str, str, str, int]] = []
    primary_entries: set[tuple[str, str, str, int]] = set()
    for entry in entries:
        primary = _vault_reference(_field(entry, "primary"), VaultName.PRIMARY)
        if primary in primary_entries:
            _invalid()
        primary_entries.add(primary)
    copied: set[tuple[str, str, str, int]] = set()
    for copy in copies:
        primary = _vault_reference(_field(copy, "primary"), VaultName.PRIMARY)
        recovery = _vault_reference(_field(copy, "recovery"), VaultName.RECOVERY)
        if primary not in primary_entries or primary in copied or primary[2:] != recovery[2:]:
            _invalid()
        copied.add(primary)
        expected.append(recovery)
    if copied != primary_entries:
        _invalid()
    expected.append(recovery_manifest)
    if len({(item[0], item[1]) for item in expected}) != len(expected):
        _invalid()
    return tuple(sorted(expected))


def _hubs(value: object) -> tuple[tuple[SchedulerRole, tuple[str, ...]], ...]:
    rows = _exact_tuple(value)
    output: list[tuple[SchedulerRole, tuple[str, ...]]] = []
    for item in rows:
        row = _closed_instance(item, SchedulerHubInventory)
        role = _enum(_field(row, "role"), SchedulerRole)
        hubs = _exact_tuple(_field(row, "hubs"))
        safe_hubs = tuple(_opaque(part) for part in hubs)
        if (
            not safe_hubs
            or tuple(sorted(safe_hubs)) != safe_hubs
            or len(set(safe_hubs)) != len(safe_hubs)
        ):
            _invalid()
        output.append((role, safe_hubs))
    if {part[0] for part in output} != {SchedulerRole.GENERAL, SchedulerRole.PROMOTION}:
        _invalid()
    return tuple(sorted(output, key=lambda part: part[0].value))


def _request_snapshot(request: object) -> tuple[object, ...]:
    request = _closed_instance(request, RecoveryContractRequest)
    issued = _REQUESTS.get(id(request))
    if issued is None or issued[0] is not request:
        _invalid()
    current = (
        _migrations(_field(request, "migration_prefix")),
        _families(_field(request, "register_families")),
        _reference(_field(request, "sql_backup_reference")),
        _reference(_field(request, "external_ledger_digest_reference")),
        _reference(_field(request, "source_ledger_verification_receipt")),
        _reference(_field(request, "restored_ledger_verification_receipt")),
        _receipt_inventory(_field(request, "vault_package_receipt")),
        _opaque(_field(request, "primary_vault_identity")),
        _opaque(_field(request, "recovery_vault_identity")),
        _hubs(_field(request, "scheduler_hubs")),
        _fingerprint(_field(request, "projection_rebuild_fingerprint")),
    )
    expected = issued[1][:-1]
    if current != expected or _fingerprint(_field(request, "fingerprint")) != issued[1][-1]:
        _invalid()
    return issued[1]


def freeze_local_recovery_contract(  # noqa: PLR0913, PLR0917
    migration_prefix: tuple[MigrationReadback, ...],
    register_families: tuple[RegisterFamilyReadback, ...],
    sql_backup_reference: RecoveryEvidenceReference,
    external_ledger_digest_reference: RecoveryEvidenceReference,
    source_ledger_verification_receipt: RecoveryEvidenceReference,
    restored_ledger_verification_receipt: RecoveryEvidenceReference,
    vault_package_receipt: EvidencePackageReceipt,
    primary_vault_identity: str,
    recovery_vault_identity: str,
    scheduler_hubs: tuple[SchedulerHubInventory, ...],
) -> RecoveryContractRequest:
    """Freeze exact local evidence expectations; this function performs no recovery action."""
    failure: RecoveryProofErrorCode | None = None
    try:
        prefix, families = _migrations(migration_prefix), _families(register_families)
        projection = _digest({"migration_prefix": prefix, "register_families": families})
        snapshot = (
            prefix,
            families,
            _reference(sql_backup_reference),
            _reference(external_ledger_digest_reference),
            _reference(source_ledger_verification_receipt),
            _reference(restored_ledger_verification_receipt),
            _receipt_inventory(vault_package_receipt),
            _opaque(primary_vault_identity),
            _opaque(recovery_vault_identity),
            _hubs(scheduler_hubs),
            projection,
        )
        if snapshot[7] == snapshot[8] or len({snapshot[3], snapshot[4], snapshot[5]}) != 3:  # noqa: PLR2004
            _invalid()
        fingerprint = _digest(
            {
                "migration_prefix": snapshot[0],
                "register_families": snapshot[1],
                "sql_backup_reference": snapshot[2],
                "external_ledger_digest_reference": snapshot[3],
                "source_ledger_verification_receipt": snapshot[4],
                "restored_ledger_verification_receipt": snapshot[5],
                "vault_inventory": snapshot[6],
                "vault_identities": snapshot[7:9],
                "scheduler_hubs": tuple((role.value, hubs) for role, hubs in snapshot[9]),
            }
        )
        request = RecoveryContractRequest(
            migration_prefix,
            register_families,
            sql_backup_reference,
            external_ledger_digest_reference,
            source_ledger_verification_receipt,
            restored_ledger_verification_receipt,
            vault_package_receipt,
            primary_vault_identity,
            recovery_vault_identity,
            scheduler_hubs,
            projection,
            fingerprint,
        )
        _REQUESTS[id(request)] = (request, (*snapshot, fingerprint))
        return request  # noqa: TRY300
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        failure = (
            error.code
            if type(error) is RecoveryProofError
            else RecoveryProofErrorCode.INPUT_INVALID
        )
    raise RecoveryProofError(failure)


def _sql_valid(request: tuple[object, ...], value: object) -> bool:  # noqa: C901, PLR0911
    try:
        observation = _closed_instance(value, SQLRestoreObservation)
        if _fingerprint(_field(observation, "request_fingerprint")) != request[-1]:
            return False
        if _reference(_field(observation, "backup_reference")) != request[2]:
            return False
        if _opaque(_field(observation, "source_database_identity")) == _opaque(
            _field(observation, "restored_database_identity")
        ):
            return False
        if (
            _migrations(_field(observation, "source_migrations")) != request[0]
            or _migrations(_field(observation, "restored_migrations")) != request[0]
        ):
            return False
        if (
            _families(_field(observation, "source_families")) != request[1]
            or _families(_field(observation, "restored_families")) != request[1]
        ):
            return False
        if _fingerprint(_field(observation, "projection_rebuild_fingerprint")) != request[10]:
            return False
        digest, source_receipt, restored_receipt = (
            _reference(_field(observation, "external_ledger_digest_reference")),
            _reference(_field(observation, "source_ledger_verification_receipt")),
            _reference(_field(observation, "restored_ledger_verification_receipt")),
        )
        if (
            digest != request[3]
            or source_receipt != request[4]
            or restored_receipt != request[5]
            or len({digest, source_receipt, restored_receipt}) != 3  # noqa: PLR2004
        ):
            return False
        probes = _exact_tuple(_field(observation, "least_privilege_probes"))
        found: dict[LeastPrivilegeProbeKind, LeastPrivilegeProbeResult] = {}
        for probe in probes:
            item = _closed_instance(probe, LeastPrivilegeProbe)
            kind = _enum(_field(item, "kind"), LeastPrivilegeProbeKind)
            result = _enum(_field(item, "result"), LeastPrivilegeProbeResult)
            if kind in found:
                return False
            found[kind] = result
        return found == {  # noqa: TRY300
            LeastPrivilegeProbeKind.READ: LeastPrivilegeProbeResult.ALLOWED,
            LeastPrivilegeProbeKind.PROCEDURE_EXECUTE: LeastPrivilegeProbeResult.ALLOWED,
            LeastPrivilegeProbeKind.DIRECT_DML: LeastPrivilegeProbeResult.DENIED,
            LeastPrivilegeProbeKind.CROSS_ROLE: LeastPrivilegeProbeResult.DENIED,
        }
    except _EmbeddedOrdinaryFailure:
        raise
    except Exception:  # noqa: BLE001
        return False


def _vault_valid(request: tuple[object, ...], value: object) -> bool:
    try:
        observation = _closed_instance(value, VaultRestoreObservation)
        if _fingerprint(_field(observation, "request_fingerprint")) != request[-1]:
            return False
        target = _opaque(_field(observation, "clean_room_target_identity"))
        if target in request[7:9]:
            return False
        rows = _exact_tuple(_field(observation, "restored_objects"))
        actual: list[tuple[str, str, str, int]] = []
        target_versions: set[tuple[str, str]] = set()
        for item in rows:
            row = _closed_instance(item, VaultRestoredObject)
            source = (
                _string(_field(row, "source_logical_key")),
                _string(_field(row, "source_version")),
                _fingerprint(_field(row, "source_fingerprint")),
                _count(_field(row, "source_byte_length")),
            )
            if (
                _opaque(_field(row, "target_identity")) != target
                or _opaque(_field(row, "target_version")) == source[1]
                or _fingerprint(_field(row, "reread_fingerprint")) != source[2]
                or _count(_field(row, "reread_byte_length")) != source[3]
            ):
                return False
            target_key = (
                _string(_field(row, "target_identity")),
                _string(_field(row, "target_version")),
            )
            if target_key in target_versions:
                return False
            target_versions.add(target_key)
            actual.append(source)
        expected = cast("tuple[tuple[str, str, str, int], ...]", request[6])
        return tuple(sorted(actual)) == expected and len(actual) == len(expected)
    except _EmbeddedOrdinaryFailure:
        raise
    except Exception:  # noqa: BLE001
        return False


def _leg_valid(
    leg: object, role: SchedulerRole, hubs: tuple[str, ...]
) -> tuple[bool, bool, tuple[str, ...]]:
    try:
        value = _closed_instance(leg, SchedulerReplacementLeg)
        if (
            _enum(_field(value, "role"), SchedulerRole) is not role
            or tuple(_opaque(item) for item in _exact_tuple(_field(value, "hubs"))) != hubs
        ):
            return False, False, ()
        identities = (
            _opaque(_field(value, "lost_instance_identity")),
            _opaque(_field(value, "replacement_instance_identity")),
        )
        lineages = (
            _opaque(_field(value, "old_lineage_identity")),
            _opaque(_field(value, "recovery_lineage_identity")),
        )
        if len(set(identities)) != 2 or len(set(lineages)) != 2:  # noqa: PLR2004
            return False, True, ()
        receipts = [
            _reference(_field(value, "safe_checkpoint_reference")),
            _reference(_field(value, "old_lineage_fence_receipt")),
        ]
        receipts.extend(
            _reference(item)
            for item in _exact_tuple(_field(value, "effect_reconciliation_receipts"))
        )
        start = _reference(_field(value, "replacement_start_result_receipt"))
        denied = _reference(_field(value, "old_lineage_resumption_denied_receipt"))
        valid = (
            _enum(_field(value, "mode"), SchedulerRecoveryMode)
            is SchedulerRecoveryMode.REPLACEMENT_FROM_SAFE_CHECKPOINT
            and len(receipts) >= 3  # noqa: PLR2004
            and len(set(receipts)) == len(receipts)
            and start not in receipts
            and denied not in receipts
            and start != denied
        )
        tokens = (
            *identities,
            *lineages,
            *(part for receipt in receipts for part in receipt),
            *start,
            *denied,
        )
        return valid, False, tokens  # noqa: TRY300
    except _EmbeddedOrdinaryFailure:
        raise
    except Exception:  # noqa: BLE001
        return False, False, ()


def _scheduler_valid(  # noqa: C901, PLR0911, PLR0912
    request: tuple[object, ...], value: object
) -> tuple[bool, bool, bool]:
    try:
        observations = _exact_tuple(value)
        by_role: dict[SchedulerRole, SchedulerReplacementObservation] = {}
        for item in observations:
            observation = _closed_instance(item, SchedulerReplacementObservation)
            role = _enum(_field(observation, "role"), SchedulerRole)
            if role in by_role:
                return False, False, True
            by_role[role] = observation
        expected = dict(cast("tuple[tuple[SchedulerRole, tuple[str, ...]], ...]", request[9]))
        if set(by_role) != set(expected):
            return False, False, True
        instance_tokens: set[str] = set()
        for observation in by_role.values():
            for identity in (
                _field(_field(observation, "forward"), "lost_instance_identity"),
                _field(_field(observation, "forward"), "replacement_instance_identity"),
                _field(_field(observation, "reverse"), "replacement_instance_identity"),
            ):
                exact_identity = _opaque(identity)
                if exact_identity in instance_tokens:
                    return False, True, False
                instance_tokens.add(exact_identity)
        all_tokens: set[str] = set()
        independent = False
        for role, hubs in expected.items():
            observation = by_role[role]
            forward_ok, forward_independent, forward_tokens = _leg_valid(
                _field(observation, "forward"), role, hubs
            )
            reverse_ok, reverse_independent, reverse_tokens = _leg_valid(
                _field(observation, "reverse"), role, hubs
            )
            if forward_independent or reverse_independent:
                independent = True
            if not forward_ok or not reverse_ok:
                return False, independent, False
            if _string(_field(_field(observation, "reverse"), "lost_instance_identity")) != _string(
                _field(_field(observation, "forward"), "replacement_instance_identity")
            ) or _string(_field(_field(observation, "reverse"), "old_lineage_identity")) != _string(
                _field(_field(observation, "forward"), "recovery_lineage_identity")
            ):
                return False, independent, False
            reverse_unique_tokens = (*reverse_tokens[1:2], *reverse_tokens[3:])
            for token in (*forward_tokens, *reverse_unique_tokens):
                if token in all_tokens:
                    return False, False, False
                all_tokens.add(token)
        return True, independent, False  # noqa: TRY300
    except _EmbeddedOrdinaryFailure:
        raise
    except Exception:  # noqa: BLE001
        return False, False, False


def _issue(
    sql: RecoveryDimensionResult,
    vault: RecoveryDimensionResult,
    scheduler: RecoveryDimensionResult,
    blockers: tuple[RecoveryBlockerCode, ...],
) -> HKV1RecoveryContractAssessment:
    proved = (
        sql is RecoveryDimensionResult.PROVED
        and vault is RecoveryDimensionResult.PROVED
        and scheduler is RecoveryDimensionResult.PROVED
    )
    result_code = (
        RecoveryResultCode.LOCAL_RECOVERY_CONTRACT_PROVED
        if proved
        else RecoveryResultCode.LOCAL_RECOVERY_CONTRACT_WITHHELD
    )
    ordered = tuple(sorted(set(blockers), key=lambda item: item.value))
    projection = {
        "result_code": result_code.value,
        "sql_result": sql.value,
        "vault_result": vault.value,
        "scheduler_result": scheduler.value,
        "contract_proved": proved,
        "blockers": tuple(item.value for item in ordered),
        "gate_f_eligible": False,
    }
    raw = _canonical(projection)
    result = object.__new__(HKV1RecoveryContractAssessment)
    for field, value in (
        ("result_code", result_code),
        ("sql_result", sql),
        ("vault_result", vault),
        ("scheduler_result", scheduler),
        ("contract_proved", proved),
        ("blockers", ordered),
        ("fingerprint", f"sha256:{sha256(raw).hexdigest()}"),
        ("canonical_bytes", raw),
        ("gate_f_eligible", False),
    ):
        object.__setattr__(result, field, value)
    return result


def assess_local_recovery_contract(
    request: RecoveryContractRequest,
    sql: SQLRestoreObservation,
    vault: VaultRestoreObservation,
    schedulers: tuple[SchedulerReplacementObservation, ...],
) -> HKV1RecoveryContractAssessment:
    """Assess detached local evidence claims without operating any recovery system."""
    failure: RecoveryProofErrorCode | None = None
    frozen: tuple[object, ...] | None = None
    sql_ok = vault_ok = scheduler_ok = independent = missing = False
    try:
        for value in (request, sql, vault, schedulers):
            _visible(value)
        frozen = _request_snapshot(request)
        sql_ok = _sql_valid(frozen, sql)
        vault_ok = _vault_valid(frozen, vault)
        scheduler_ok, independent, missing = _scheduler_valid(frozen, schedulers)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        failure = (
            error.code
            if type(error) is RecoveryProofError
            else RecoveryProofErrorCode.INPUT_INVALID
        )
    if failure is not None:
        raise RecoveryProofError(failure)
    if frozen is None:
        raise AssertionError
    blockers: list[RecoveryBlockerCode] = [
        RecoveryBlockerCode.SQL_ENGINE_RESTORE_UNRUN,
        RecoveryBlockerCode.VAULT_CLEAN_ROOM_RESTORE_UNRUN,
        RecoveryBlockerCode.SCHEDULER_REPLACEMENT_UNRUN,
    ]
    if not sql_ok:
        blockers.append(RecoveryBlockerCode.SQL_RESTORE_READBACK_FAILED)
    if not vault_ok:
        blockers.append(RecoveryBlockerCode.VAULT_RESTORE_READBACK_FAILED)
    if not scheduler_ok:
        blockers.append(
            RecoveryBlockerCode.SCHEDULER_ROLE_MISSING
            if missing
            else RecoveryBlockerCode.SCHEDULER_REPLACEMENT_FAILED
        )
    if independent:
        blockers.append(RecoveryBlockerCode.SCHEDULER_NOT_INDEPENDENT)
    return _issue(
        RecoveryDimensionResult.PROVED if sql_ok else RecoveryDimensionResult.WITHHELD,
        RecoveryDimensionResult.PROVED if vault_ok else RecoveryDimensionResult.WITHHELD,
        RecoveryDimensionResult.PROVED if scheduler_ok else RecoveryDimensionResult.WITHHELD,
        tuple(blockers),
    )


class LocalRecoveryMode(StrEnum):
    """Closed operator modes; preflight is deliberately the default."""

    PREFLIGHT = "PREFLIGHT"
    PLAN_LIVE = "PLAN_LIVE"
    EXECUTE_LOCAL_PROTOTYPE = "EXECUTE_LOCAL_PROTOTYPE"
    EXECUTE_LIVE = "EXECUTE_LIVE"


class LocalRecoveryStatus(StrEnum):
    """Truthful local-run outcomes without a production-complete state."""

    LOCAL_PROTOTYPE_PROVED = "LOCAL_PROTOTYPE_PROVED"
    NOT_READY = "NOT_READY"
    PREFLIGHT_READY = "PREFLIGHT_READY"
    WITHHELD = "WITHHELD"


@dataclass(frozen=True, slots=True)
class LocalRecoveryConfiguration:
    """Explicit local paths and stable identities for one bounded recovery drill."""

    operation_id: str
    request_fingerprint: str
    workspace_root: Path
    sql_snapshot_path: Path
    primary_vault_root: Path
    recovery_vault_root: Path
    scheduler_snapshot_root: Path
    output_path: Path

    def __post_init__(self) -> None:
        """Reject aliases, traversal, and non-absolute operator paths lexically."""
        _opaque(self.operation_id)
        _fingerprint(self.request_fingerprint)
        for path in (
            self.workspace_root,
            self.sql_snapshot_path,
            self.primary_vault_root,
            self.recovery_vault_root,
            self.scheduler_snapshot_root,
            self.output_path,
        ):
            if not path.is_absolute() or ".." in path.parts:
                _invalid()


@dataclass(frozen=True, slots=True)
class LocalRecoveryTargets:
    """Names derived solely from the operation and frozen-request identities."""

    sql_database_name: str
    sql_database_identity: str
    vault_directory_name: str
    vault_identity: str
    scheduler_directory_name: str


@dataclass(frozen=True, slots=True, init=False)
class LocalRecoveryRunResult:
    """Issuer-only canonical result for preflight or a local prototype drill."""

    status: LocalRecoveryStatus
    mode: LocalRecoveryMode
    operation_id: str
    request_fingerprint: str
    targets: LocalRecoveryTargets
    blockers: tuple[str, ...]
    assessment_fingerprint: str | None
    local_contract_proved: bool
    live_recovery_proved: bool
    canonical_bytes: bytes

    def __init__(self, **_arguments: object) -> None:
        """Reject direct construction so callers cannot mint a successful result."""
        raise RecoveryProofError(RecoveryProofErrorCode.ISSUER_REQUIRED)


class LocalSQLRecoveryPort(Protocol):
    """One contained filesystem snapshot restore/read-back boundary."""

    def restore_and_readback(
        self,
        request: RecoveryContractRequest,
        configuration: LocalRecoveryConfiguration,
        targets: LocalRecoveryTargets,
    ) -> SQLRestoreObservation:
        """Restore and reread one exact local prototype snapshot."""
        ...


class LocalVaultRecoveryPort(Protocol):
    """One exact primary/recovery/local-clean-room read-back boundary."""

    def restore_and_readback(
        self,
        request: RecoveryContractRequest,
        configuration: LocalRecoveryConfiguration,
        targets: LocalRecoveryTargets,
    ) -> VaultRestoreObservation:
        """Reread exact vault versions through the repository-owned vault port."""
        ...


class LocalSchedulerRecoveryPort(Protocol):
    """One local file-checkpoint A/B replacement-and-replay boundary."""

    def replace_and_replay(
        self,
        request: RecoveryContractRequest,
        configuration: LocalRecoveryConfiguration,
        targets: LocalRecoveryTargets,
    ) -> tuple[SchedulerReplacementObservation, ...]:
        """Run both same-role replacement directions against retained checkpoints."""
        ...


@dataclass(frozen=True, slots=True)
class LocalRecoveryAdapters:
    """All three explicitly composed local prototype effect boundaries."""

    sql: LocalSQLRecoveryPort
    vault: LocalVaultRecoveryPort
    scheduler: LocalSchedulerRecoveryPort


def _derived_opaque(*parts: str) -> str:
    return f"r_{sha256('|'.join(parts).encode('ascii')).hexdigest()[:32]}"


def derive_local_recovery_targets(
    configuration: LocalRecoveryConfiguration,
) -> LocalRecoveryTargets:
    """Derive all disposable names; callers cannot select arbitrary targets."""
    token = sha256(
        f"{configuration.operation_id}|{configuration.request_fingerprint}".encode("ascii")
    ).hexdigest()[:24]
    return LocalRecoveryTargets(
        sql_database_name=f"asklegal_recovery_sql_{token}",
        sql_database_identity=_derived_opaque(token, "sql-database"),
        vault_directory_name=f"asklegal-recovery-vault-{token}",
        vault_identity=_derived_opaque(token, "vault"),
        scheduler_directory_name=f"asklegal-recovery-scheduler-{token}",
    )


def _validate_local_targets(
    configuration: LocalRecoveryConfiguration,
    targets: LocalRecoveryTargets,
) -> None:
    if type(targets) is not LocalRecoveryTargets or targets != derive_local_recovery_targets(
        configuration
    ):
        _local_failure("LOCAL_RECOVERY_TARGET_INVALID")


def _reference_document(reference: RecoveryEvidenceReference) -> dict[str, object]:
    return {"evidence_id": reference.evidence_id, "fingerprint": reference.fingerprint}


def _migration_documents(rows: tuple[MigrationReadback, ...]) -> list[dict[str, object]]:
    return [
        {"migration_id": row.migration_id, "package_fingerprint": row.package_fingerprint}
        for row in rows
    ]


def _family_documents(rows: tuple[RegisterFamilyReadback, ...]) -> list[dict[str, object]]:
    return [
        {
            "content_fingerprint": row.content_fingerprint,
            "family": row.family,
            "row_count": row.row_count,
        }
        for row in rows
    ]


def _sql_snapshot_document(
    request: RecoveryContractRequest,
    source_database_identity: str,
) -> dict[str, object]:
    _request_snapshot(request)
    source_database_identity = _opaque(source_database_identity)
    return {
        "backup_reference": _reference_document(request.sql_backup_reference),
        "database_identity": source_database_identity,
        "external_ledger_digest_reference": _reference_document(
            request.external_ledger_digest_reference
        ),
        "families": _family_documents(request.register_families),
        "least_privilege": {
            "cross_role": "DENIED",
            "direct_dml": "DENIED",
            "procedure_execute": "ALLOWED",
            "read": "ALLOWED",
        },
        "migrations": _migration_documents(request.migration_prefix),
        "projection_rebuild_fingerprint": request.projection_rebuild_fingerprint,
        "request_fingerprint": request.fingerprint,
        "restored_ledger_verification_receipt": _reference_document(
            request.restored_ledger_verification_receipt
        ),
        "schema": _LOCAL_INPUT_SCHEMA,
        "source_ledger_verification_receipt": _reference_document(
            request.source_ledger_verification_receipt
        ),
    }


def build_local_sql_snapshot(
    request: RecoveryContractRequest,
    source_database_identity: str,
) -> bytes:
    """Build canonical retained input for the contained filesystem SQL drill."""
    return _canonical(_sql_snapshot_document(request, source_database_identity)) + b"\n"


def build_local_scheduler_snapshot(
    request: RecoveryContractRequest,
    role: SchedulerRole,
    lost_instance_identity: str,
    old_lineage_identity: str,
    checkpoint_bytes: bytes,
) -> bytes:
    """Build canonical metadata bound to one separately retained checkpoint body."""
    frozen = _request_snapshot(request)
    role = _enum(role, SchedulerRole)
    hubs = dict(cast("tuple[tuple[SchedulerRole, tuple[str, ...]], ...]", frozen[9]))[role]
    if type(checkpoint_bytes) is not bytes or not checkpoint_bytes:
        _invalid()
    document = {
        "checkpoint_fingerprint": f"sha256:{sha256(checkpoint_bytes).hexdigest()}",
        "hubs": list(hubs),
        "lost_instance_identity": _opaque(lost_instance_identity),
        "old_lineage_identity": _opaque(old_lineage_identity),
        "request_fingerprint": request.fingerprint,
        "role": role.value,
        "schema": _LOCAL_INPUT_SCHEMA,
    }
    return _canonical(document) + b"\n"


def _canonical_document(raw: bytes, label: str) -> dict[str, object]:
    def invalid() -> NoReturn:
        raise ValueError

    try:
        if type(raw) is not bytes or not raw.endswith(b"\n"):
            invalid()
        value: object = json.loads(raw)
        if type(value) is not dict:
            invalid()
        document = cast("dict[object, object]", value)
        if any(type(key) is not str for key in document):
            invalid()
        typed = cast("dict[str, object]", document)
        if _canonical(typed) + b"\n" != raw:
            invalid()
    except UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError:
        raise ValueError(label) from None
    else:
        return typed


def _local_failure(code: str) -> NoReturn:
    raise ValueError(code)


def _real_directory(path: Path) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(status.st_mode) and not stat.S_ISLNK(status.st_mode)


def _real_file(path: Path) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(status.st_mode) and not stat.S_ISLNK(status.st_mode)


def _ensure_generated_directory(root: Path, name: str) -> Path:
    if not _real_directory(root) or "/" in name or name in {"", ".", ".."}:
        _local_failure("LOCAL_RECOVERY_TARGET_INVALID")
    target = root / name
    if target.exists() or target.is_symlink():
        if not _real_directory(target):
            _local_failure("LOCAL_RECOVERY_TARGET_INVALID")
    else:
        target.mkdir(mode=_PRIVATE_DIRECTORY_MODE)
        target.chmod(_PRIVATE_DIRECTORY_MODE, follow_symlinks=False)
    if not _real_directory(target):
        _local_failure("LOCAL_RECOVERY_TARGET_INVALID")
    return target


def _retain_exact(path: Path, content: bytes) -> bytes:
    if path.exists() or path.is_symlink():
        if not _real_file(path) or path.read_bytes() != content:
            _local_failure("LOCAL_RECOVERY_READBACK_FAILED")
    else:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
    path.chmod(_PRIVATE_FILE_MODE, follow_symlinks=False)
    reread = path.read_bytes()
    if reread != content or stat.S_IMODE(path.lstat().st_mode) != _PRIVATE_FILE_MODE:
        _local_failure("LOCAL_RECOVERY_READBACK_FAILED")
    return reread


class FilesystemSQLRecoveryAdapter:
    """Contained byte-and-semantic snapshot restore; never a SQL-engine proof."""

    def restore_and_readback(
        self,
        request: RecoveryContractRequest,
        configuration: LocalRecoveryConfiguration,
        targets: LocalRecoveryTargets,
    ) -> SQLRestoreObservation:
        """Copy one canonical snapshot to its generated target and reread it."""
        _validate_local_targets(configuration, targets)
        raw = configuration.sql_snapshot_path.read_bytes()
        document = _canonical_document(raw, "LOCAL_SQL_SNAPSHOT_INVALID")
        source_identity = _opaque(document.get("database_identity"))
        if document != _sql_snapshot_document(request, source_identity):
            _local_failure("LOCAL_SQL_SNAPSHOT_INVALID")
        target = _ensure_generated_directory(
            configuration.workspace_root, targets.sql_database_name
        )
        _canonical_document(
            _retain_exact(target / "restored-register.json", raw),
            "LOCAL_SQL_READBACK_FAILED",
        )
        return SQLRestoreObservation(
            request.fingerprint,
            request.sql_backup_reference,
            source_identity,
            targets.sql_database_identity,
            request.migration_prefix,
            request.migration_prefix,
            request.register_families,
            request.register_families,
            request.projection_rebuild_fingerprint,
            request.external_ledger_digest_reference,
            request.source_ledger_verification_receipt,
            request.restored_ledger_verification_receipt,
            (
                LeastPrivilegeProbe(
                    LeastPrivilegeProbeKind.READ, LeastPrivilegeProbeResult.ALLOWED
                ),
                LeastPrivilegeProbe(
                    LeastPrivilegeProbeKind.PROCEDURE_EXECUTE,
                    LeastPrivilegeProbeResult.ALLOWED,
                ),
                LeastPrivilegeProbe(
                    LeastPrivilegeProbeKind.DIRECT_DML, LeastPrivilegeProbeResult.DENIED
                ),
                LeastPrivilegeProbe(
                    LeastPrivilegeProbeKind.CROSS_ROLE, LeastPrivilegeProbeResult.DENIED
                ),
            ),
        )


class FilesystemVaultRecoveryAdapter:
    """Exact local primary/recovery reads plus a contained clean-room byte restore."""

    def restore_and_readback(
        self,
        request: RecoveryContractRequest,
        configuration: LocalRecoveryConfiguration,
        targets: LocalRecoveryTargets,
    ) -> VaultRestoreObservation:
        """Verify both vault copies and reread the generated clean-room bytes."""
        _validate_local_targets(configuration, targets)
        primary = LocalImmutableVault(configuration.primary_vault_root, VaultName.PRIMARY)
        recovery = LocalImmutableVault(configuration.recovery_vault_root, VaultName.RECOVERY)
        receipt = request.vault_package_receipt
        source_rows: list[tuple[ExactObjectReference, bytes]] = []
        for copied in receipt.copies:
            primary_bytes = primary.read_exact(copied.primary)
            recovery_bytes = recovery.read_exact(copied.recovery)
            if primary_bytes != recovery_bytes:
                _local_failure("LOCAL_VAULT_READBACK_FAILED")
            source_rows.append((copied.recovery, recovery_bytes))
        primary_manifest = primary.read_exact(receipt.primary_manifest)
        recovery_manifest = recovery.read_exact(receipt.recovery_manifest)
        if primary_manifest != recovery_manifest:
            _local_failure("LOCAL_VAULT_READBACK_FAILED")
        source_rows.append((receipt.recovery_manifest, recovery_manifest))
        target = _ensure_generated_directory(
            configuration.workspace_root, targets.vault_directory_name
        )
        rows: list[VaultRestoredObject] = []
        for index, (reference, content) in enumerate(source_rows):
            target_version = _derived_opaque(
                targets.vault_identity,
                str(index),
                reference.logical_key,
                reference.version_id,
            )
            filename = f"{index:04d}-{target_version}.bin"
            reread = _retain_exact(target / filename, content)
            rows.append(
                VaultRestoredObject(
                    reference.logical_key,
                    reference.version_id,
                    reference.fingerprint,
                    reference.byte_length,
                    targets.vault_identity,
                    target_version,
                    f"sha256:{sha256(reread).hexdigest()}",
                    len(reread),
                )
            )
        return VaultRestoreObservation(request.fingerprint, targets.vault_identity, tuple(rows))


def _evidence_reference(*parts: str) -> RecoveryEvidenceReference:
    body = "|".join(parts).encode("ascii")
    return RecoveryEvidenceReference(
        f"r_{sha256(b'id|' + body).hexdigest()[:32]}",
        f"sha256:{sha256(b'body|' + body).hexdigest()}",
    )


class FilesystemSchedulerRecoveryAdapter:
    """Two-way local checkpoint replacement/replay; never a Scheduler-service proof."""

    def replace_and_replay(
        self,
        request: RecoveryContractRequest,
        configuration: LocalRecoveryConfiguration,
        targets: LocalRecoveryTargets,
    ) -> tuple[SchedulerReplacementObservation, ...]:
        """Replay both roles through forward and reverse generated file states."""
        _validate_local_targets(configuration, targets)
        frozen = _request_snapshot(request)
        expected_hubs = dict(cast("tuple[tuple[SchedulerRole, tuple[str, ...]], ...]", frozen[9]))
        target = _ensure_generated_directory(
            configuration.workspace_root, targets.scheduler_directory_name
        )
        observations: list[SchedulerReplacementObservation] = []
        for role in SchedulerRole:
            stem = role.value.lower()
            metadata_path = configuration.scheduler_snapshot_root / f"{stem}.json"
            checkpoint_path = configuration.scheduler_snapshot_root / f"{stem}-checkpoint.bin"
            metadata = _canonical_document(
                metadata_path.read_bytes(), "LOCAL_SCHEDULER_SNAPSHOT_INVALID"
            )
            checkpoint = checkpoint_path.read_bytes()
            expected_keys = {
                "checkpoint_fingerprint",
                "hubs",
                "lost_instance_identity",
                "old_lineage_identity",
                "request_fingerprint",
                "role",
                "schema",
            }
            if set(metadata) != expected_keys:
                _local_failure("LOCAL_SCHEDULER_SNAPSHOT_INVALID")
            hubs_value = metadata["hubs"]
            if type(hubs_value) is not list:
                _local_failure("LOCAL_SCHEDULER_SNAPSHOT_INVALID")
            hubs = tuple(_opaque(item) for item in cast("list[object]", hubs_value))
            if (
                metadata["schema"] != _LOCAL_INPUT_SCHEMA
                or metadata["role"] != role.value
                or metadata["request_fingerprint"] != request.fingerprint
                or metadata["checkpoint_fingerprint"] != f"sha256:{sha256(checkpoint).hexdigest()}"
                or hubs != expected_hubs[role]
            ):
                _local_failure("LOCAL_SCHEDULER_SNAPSHOT_INVALID")
            lost = _opaque(metadata["lost_instance_identity"])
            old_lineage = _opaque(metadata["old_lineage_identity"])
            replacement = _derived_opaque(
                configuration.operation_id,
                request.fingerprint,
                role.value,
                "forward-instance",
            )
            recovery_lineage = _derived_opaque(
                configuration.operation_id,
                request.fingerprint,
                role.value,
                "forward-lineage",
            )
            reverse_replacement = _derived_opaque(
                configuration.operation_id,
                request.fingerprint,
                role.value,
                "reverse-instance",
            )
            reverse_lineage = _derived_opaque(
                configuration.operation_id,
                request.fingerprint,
                role.value,
                "reverse-lineage",
            )
            forward = self._leg(
                request,
                role,
                hubs,
                lost,
                replacement,
                old_lineage,
                recovery_lineage,
                configuration.operation_id,
                "forward",
            )
            reverse = self._leg(
                request,
                role,
                hubs,
                replacement,
                reverse_replacement,
                recovery_lineage,
                reverse_lineage,
                configuration.operation_id,
                "reverse",
            )
            for direction, leg in (("forward", forward), ("reverse", reverse)):
                body = (
                    _canonical(
                        {
                            "checkpoint_fingerprint": metadata["checkpoint_fingerprint"],
                            "direction": direction,
                            "lost_instance_identity": leg.lost_instance_identity,
                            "old_lineage_identity": leg.old_lineage_identity,
                            "operation_id": configuration.operation_id,
                            "recovery_lineage_identity": leg.recovery_lineage_identity,
                            "replacement_instance_identity": leg.replacement_instance_identity,
                            "request_fingerprint": request.fingerprint,
                            "role": role.value,
                        }
                    )
                    + b"\n"
                )
                _canonical_document(
                    _retain_exact(target / f"{stem}-{direction}.json", body),
                    "LOCAL_SCHEDULER_READBACK_FAILED",
                )
            observations.append(SchedulerReplacementObservation(role, forward, reverse))
        return tuple(observations)

    @staticmethod
    def _leg(  # noqa: PLR0913, PLR0917
        request: RecoveryContractRequest,
        role: SchedulerRole,
        hubs: tuple[str, ...],
        lost: str,
        replacement: str,
        old_lineage: str,
        recovery_lineage: str,
        operation_id: str,
        direction: str,
    ) -> SchedulerReplacementLeg:
        prefix = (operation_id, request.fingerprint, role.value, direction)
        return SchedulerReplacementLeg(
            role,
            hubs,
            lost,
            replacement,
            old_lineage,
            recovery_lineage,
            _evidence_reference(*prefix, "checkpoint"),
            _evidence_reference(*prefix, "fence"),
            (
                _evidence_reference(*prefix, "effect-0"),
                _evidence_reference(*prefix, "effect-1"),
            ),
            _evidence_reference(*prefix, "start"),
            _evidence_reference(*prefix, "old-denied"),
            SchedulerRecoveryMode.REPLACEMENT_FROM_SAFE_CHECKPOINT,
        )


def _preflight_reference(value: object) -> None:
    if type(value) is not dict:
        _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
    document = cast("dict[object, object]", value)
    if set(document) != {"evidence_id", "fingerprint"}:
        _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
    _opaque(document["evidence_id"])
    _fingerprint(document["fingerprint"])


def _preflight_sql_content(  # noqa: C901
    configuration: LocalRecoveryConfiguration,
) -> None:
    document = _canonical_document(
        configuration.sql_snapshot_path.read_bytes(), "LOCAL_RECOVERY_INPUT_INVALID"
    )
    expected_keys = {
        "backup_reference",
        "database_identity",
        "external_ledger_digest_reference",
        "families",
        "least_privilege",
        "migrations",
        "projection_rebuild_fingerprint",
        "request_fingerprint",
        "restored_ledger_verification_receipt",
        "schema",
        "source_ledger_verification_receipt",
    }
    if (
        set(document) != expected_keys
        or document["schema"] != _LOCAL_INPUT_SCHEMA
        or document["request_fingerprint"] != configuration.request_fingerprint
    ):
        _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
    _opaque(document["database_identity"])
    _fingerprint(document["projection_rebuild_fingerprint"])
    for name in (
        "backup_reference",
        "external_ledger_digest_reference",
        "restored_ledger_verification_receipt",
        "source_ledger_verification_receipt",
    ):
        _preflight_reference(document[name])
    migrations = document["migrations"]
    families = document["families"]
    privilege = document["least_privilege"]
    if type(migrations) is not list or not migrations or type(families) is not list or not families:
        _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
    migration_ids: list[str] = []
    for value in cast("list[object]", migrations):
        if type(value) is not dict:
            _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
        row = cast("dict[object, object]", value)
        if set(row) != {"migration_id", "package_fingerprint"}:
            _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
        migration_ids.append(_migration(row["migration_id"]))
        _fingerprint(row["package_fingerprint"])
    family_ids: list[str] = []
    for value in cast("list[object]", families):
        if type(value) is not dict:
            _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
        row = cast("dict[object, object]", value)
        if set(row) != {"content_fingerprint", "family", "row_count"}:
            _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
        family_ids.append(_family(row["family"]))
        _count(row["row_count"])
        _fingerprint(row["content_fingerprint"])
    if len(set(migration_ids)) != len(migration_ids) or family_ids != sorted(set(family_ids)):
        _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
    if privilege != {
        "cross_role": "DENIED",
        "direct_dml": "DENIED",
        "procedure_execute": "ALLOWED",
        "read": "ALLOWED",
    }:
        _local_failure("LOCAL_RECOVERY_INPUT_INVALID")


def _preflight_scheduler_content(configuration: LocalRecoveryConfiguration) -> None:
    for role in SchedulerRole:
        stem = role.value.lower()
        checkpoint = (configuration.scheduler_snapshot_root / f"{stem}-checkpoint.bin").read_bytes()
        document = _canonical_document(
            (configuration.scheduler_snapshot_root / f"{stem}.json").read_bytes(),
            "LOCAL_RECOVERY_INPUT_INVALID",
        )
        if set(document) != {
            "checkpoint_fingerprint",
            "hubs",
            "lost_instance_identity",
            "old_lineage_identity",
            "request_fingerprint",
            "role",
            "schema",
        }:
            _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
        hubs_value = document["hubs"]
        if type(hubs_value) is not list:
            _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
        hubs = tuple(_opaque(value) for value in cast("list[object]", hubs_value))
        if (
            not hubs
            or tuple(sorted(set(hubs))) != hubs
            or document["schema"] != _LOCAL_INPUT_SCHEMA
            or document["role"] != role.value
            or document["request_fingerprint"] != configuration.request_fingerprint
            or document["checkpoint_fingerprint"] != f"sha256:{sha256(checkpoint).hexdigest()}"
        ):
            _local_failure("LOCAL_RECOVERY_INPUT_INVALID")
        _opaque(document["lost_instance_identity"])
        _opaque(document["old_lineage_identity"])


def _preflight_blockers(configuration: LocalRecoveryConfiguration) -> tuple[str, ...]:
    blockers: list[str] = []
    directories = (
        ("WORKSPACE_ROOT_NOT_READY", configuration.workspace_root),
        ("PRIMARY_VAULT_NOT_READY", configuration.primary_vault_root),
        ("RECOVERY_VAULT_NOT_READY", configuration.recovery_vault_root),
        ("SCHEDULER_INPUT_NOT_READY", configuration.scheduler_snapshot_root),
        ("OUTPUT_PARENT_NOT_READY", configuration.output_path.parent),
    )
    for code, path in directories:
        if not _real_directory(path):
            blockers.append(code)
    files = [("SQL_INPUT_NOT_READY", configuration.sql_snapshot_path)]
    files.extend(
        ("SCHEDULER_INPUT_NOT_READY", configuration.scheduler_snapshot_root / name)
        for name in (
            "general-checkpoint.bin",
            "general.json",
            "promotion-checkpoint.bin",
            "promotion.json",
        )
    )
    for code, path in files:
        if not _real_file(path):
            blockers.append(code)
    if not blockers:
        try:
            _preflight_sql_content(configuration)
            _preflight_scheduler_content(configuration)
        except OSError, RecoveryProofError, TypeError, ValueError:
            blockers.append("LOCAL_RECOVERY_INPUT_INVALID")
    return tuple(sorted(set(blockers)))


def _result_document(result: LocalRecoveryRunResult) -> dict[str, object]:
    return {
        "assessment_fingerprint": result.assessment_fingerprint,
        "blockers": list(result.blockers),
        "live_recovery_proved": result.live_recovery_proved,
        "local_contract_proved": result.local_contract_proved,
        "mode": result.mode.value,
        "operation_id": result.operation_id,
        "request_fingerprint": result.request_fingerprint,
        "schema": _LOCAL_RESULT_SCHEMA,
        "status": result.status.value,
        "targets": {
            "scheduler_directory_name": result.targets.scheduler_directory_name,
            "sql_database_identity": result.targets.sql_database_identity,
            "sql_database_name": result.targets.sql_database_name,
            "vault_directory_name": result.targets.vault_directory_name,
            "vault_identity": result.targets.vault_identity,
        },
    }


def _issue_local_result(
    configuration: LocalRecoveryConfiguration,
    mode: LocalRecoveryMode,
    status: LocalRecoveryStatus,
    blockers: Sequence[str],
    assessment: HKV1RecoveryContractAssessment | None = None,
) -> LocalRecoveryRunResult:
    result = object.__new__(LocalRecoveryRunResult)
    targets = derive_local_recovery_targets(configuration)
    for name, value in (
        ("status", status),
        ("mode", mode),
        ("operation_id", configuration.operation_id),
        ("request_fingerprint", configuration.request_fingerprint),
        ("targets", targets),
        ("blockers", tuple(sorted(set(blockers)))),
        (
            "assessment_fingerprint",
            None if assessment is None else assessment.fingerprint,
        ),
        (
            "local_contract_proved",
            assessment is not None and assessment.contract_proved,
        ),
        ("live_recovery_proved", False),
    ):
        object.__setattr__(result, name, value)
    object.__setattr__(result, "canonical_bytes", _canonical(_result_document(result)) + b"\n")
    return result


def run_local_recovery(
    configuration: LocalRecoveryConfiguration,
    *,
    mode: LocalRecoveryMode = LocalRecoveryMode.PREFLIGHT,
    execution_authorized: bool = False,
    request: RecoveryContractRequest | None = None,
    adapters: LocalRecoveryAdapters | None = None,
) -> LocalRecoveryRunResult:
    """Preflight by default; execute only with explicit authority and all local ports."""
    if type(configuration) is not LocalRecoveryConfiguration or type(mode) is not LocalRecoveryMode:
        _invalid()
    blockers = list(_preflight_blockers(configuration))
    if mode is LocalRecoveryMode.PREFLIGHT:
        return _issue_local_result(
            configuration,
            mode,
            LocalRecoveryStatus.NOT_READY if blockers else LocalRecoveryStatus.PREFLIGHT_READY,
            blockers,
        )
    if not execution_authorized:
        blockers.append("EXECUTION_AUTHORITY_REQUIRED")
    if request is None or adapters is None:
        blockers.append("EXECUTION_ADAPTERS_NOT_COMPOSED")
    elif (
        type(request) is not RecoveryContractRequest or type(adapters) is not LocalRecoveryAdapters
    ):
        _invalid()
    elif request.fingerprint != configuration.request_fingerprint:
        blockers.append("REQUEST_FINGERPRINT_MISMATCH")
    if blockers:
        return _issue_local_result(configuration, mode, LocalRecoveryStatus.NOT_READY, blockers)
    if request is None or adapters is None:
        raise AssertionError
    try:
        targets = derive_local_recovery_targets(configuration)
        assessment = assess_local_recovery_contract(
            request,
            adapters.sql.restore_and_readback(request, configuration, targets),
            adapters.vault.restore_and_readback(request, configuration, targets),
            adapters.scheduler.replace_and_replay(request, configuration, targets),
        )
    except OSError, RecoveryProofError, TypeError, ValueError:
        return _issue_local_result(
            configuration,
            mode,
            LocalRecoveryStatus.WITHHELD,
            ("LOCAL_PROTOTYPE_READBACK_FAILED",),
        )
    status = (
        LocalRecoveryStatus.LOCAL_PROTOTYPE_PROVED
        if assessment.contract_proved
        else LocalRecoveryStatus.WITHHELD
    )
    return _issue_local_result(
        configuration,
        mode,
        status,
        tuple(blocker.value for blocker in assessment.blockers),
        assessment,
    )


def write_local_recovery_result(result: LocalRecoveryRunResult, output: Path) -> None:
    """Publish one private canonical result atomically and verify exact read-back."""
    if type(result) is not LocalRecoveryRunResult or not _real_directory(output.parent):
        _local_failure("LOCAL_RECOVERY_OUTPUT_INVALID")
    if (output.exists() or output.is_symlink()) and not _real_file(output):
        _local_failure("LOCAL_RECOVERY_OUTPUT_INVALID")
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.")
        temporary = Path(name)
        os.fchmod(descriptor, _PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(result.canonical_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(output)
        temporary = None
        output.chmod(_PRIVATE_FILE_MODE, follow_symlinks=False)
        if output.read_bytes() != result.canonical_bytes:
            _local_failure("LOCAL_RECOVERY_OUTPUT_INVALID")
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


class LiveRecoveryStep(StrEnum):
    """Exact ordered effects in one disposable local recovery drill."""

    SQL_RESTORE_READBACK = "SQL_RESTORE_READBACK"
    PRIMARY_VAULT_CLEAN_ROOM_READBACK = "PRIMARY_VAULT_CLEAN_ROOM_READBACK"
    RECOVERY_VAULT_CLEAN_ROOM_READBACK = "RECOVERY_VAULT_CLEAN_ROOM_READBACK"
    SCHEDULER_GENERAL_FORWARD = "SCHEDULER_GENERAL_FORWARD"
    SCHEDULER_GENERAL_REVERSE = "SCHEDULER_GENERAL_REVERSE"
    SCHEDULER_PROMOTION_FORWARD = "SCHEDULER_PROMOTION_FORWARD"
    SCHEDULER_PROMOTION_REVERSE = "SCHEDULER_PROMOTION_REVERSE"


@dataclass(frozen=True, slots=True)
class SealedCredentialReference:
    """Reference to one sealed credential file; never the credential value."""

    credential_id: str
    sealed_path: str
    fingerprint: str

    def __post_init__(self) -> None:
        """Validate identity, path confinement, and fingerprint without reading material."""
        path = Path(self.sealed_path)
        if (
            self.credential_id not in _LIVE_CREDENTIAL_IDS
            or not path.is_absolute()
            or ".." in path.parts
            or not path.is_relative_to(Path("/run/credentials"))
        ):
            _local_failure("LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID")
        _fingerprint(self.fingerprint)


@dataclass(frozen=True, slots=True)
class LiveRecoveryStepReceipt:
    """Sanitized exact read-back receipt returned by an owning effect adapter."""

    step: LiveRecoveryStep
    plan_fingerprint: str
    target_identity: str
    effect_fingerprint: str
    readback_fingerprint: str

    def __post_init__(self) -> None:
        """Validate one exact sanitized effect/read-back receipt."""
        if type(self.step) is not LiveRecoveryStep:
            _local_failure("LIVE_RECOVERY_RECEIPT_INVALID")
        _fingerprint(self.plan_fingerprint)
        _opaque(self.target_identity)
        _fingerprint(self.effect_fingerprint)
        _fingerprint(self.readback_fingerprint)


class LiveRecoveryExecutionError(RuntimeError):
    """Closed live recovery planning/execution failure."""


class LiveRecoveryAcknowledgementLost(RuntimeError):
    """Adapter signal that an effect may have completed before its acknowledgement."""


class LiveRecoveryStepPort(Protocol):
    """Create-or-match effect port with an independent read-only reconciliation path."""

    def reconcile(
        self,
        step: LiveRecoveryStep,
        plan: Mapping[str, object],
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt | None:
        """Return an exact existing receipt, or None without creating an effect."""
        ...

    def execute(
        self,
        step: LiveRecoveryStep,
        plan: Mapping[str, object],
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt:
        """Create-or-match the exact planned effect and return verified readback."""
        ...


@dataclass(frozen=True, slots=True)
class LiveRecoveryExecutionAdapters:
    """Separately owned SQL, vault, and Scheduler recovery effect ports."""

    sql: LiveRecoveryStepPort
    vault: LiveRecoveryStepPort
    scheduler: LiveRecoveryStepPort


class _ExactVaultReader(Protocol):
    def read_exact(self, reference: ExactObjectReference) -> bytes: ...


class ImmutableVaultLiveRecoveryPort:
    """Read both real immutable-vault adapters into one isolated local clean room."""

    def __init__(
        self,
        primary: _ExactVaultReader,
        recovery: _ExactVaultReader,
        clean_room_root: Path,
    ) -> None:
        """Bind exact already-authenticated readers and one disposable root."""
        if not _real_directory(clean_room_root):
            _local_failure("LIVE_RECOVERY_CLEAN_ROOM_INVALID")
        self._primary = primary
        self._recovery = recovery
        self._root = clean_room_root

    def reconcile(
        self,
        step: LiveRecoveryStep,
        plan: Mapping[str, object],
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt | None:
        """Reread a previously created clean room without creating a target."""
        target = self._target(step, plan, credentials)
        directory = self._root / target
        if not directory.exists():
            return None
        return self._readback(step, plan, directory, create=False)

    def execute(
        self,
        step: LiveRecoveryStep,
        plan: Mapping[str, object],
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt:
        """Create-or-match one generated clean room and verify every exact version."""
        target = self._target(step, plan, credentials)
        directory = _ensure_generated_directory(self._root, target)
        return self._readback(step, plan, directory, create=True)

    @staticmethod
    def _target(
        step: LiveRecoveryStep,
        plan: Mapping[str, object],
        credentials: tuple[SealedCredentialReference, ...],
    ) -> str:
        expected_credential = (
            "PRIMARY_VAULT_RECOVERY_READER"
            if step is LiveRecoveryStep.PRIMARY_VAULT_CLEAN_ROOM_READBACK
            else "RECOVERY_VAULT_RECOVERY_READER"
            if step is LiveRecoveryStep.RECOVERY_VAULT_CLEAN_ROOM_READBACK
            else None
        )
        if expected_credential is None or expected_credential not in {
            item.credential_id for item in credentials
        }:
            msg = "LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID"
            raise LiveRecoveryExecutionError(msg)
        return ImmutableVaultLiveRecoveryPort._target_from_plan(step, plan)

    @staticmethod
    def _target_from_plan(step: LiveRecoveryStep, plan: Mapping[str, object]) -> str:
        raw_steps = plan.get("steps")
        if type(raw_steps) is not list:
            msg = "LIVE_RECOVERY_PLAN_INVALID"
            raise LiveRecoveryExecutionError(msg)
        for raw in cast("list[object]", raw_steps):
            if type(raw) is dict:
                candidate = cast("dict[str, object]", raw)
                if candidate.get("step") == step.value:
                    return _opaque(candidate.get("target_identity"))
        msg = "LIVE_RECOVERY_PLAN_INVALID"
        raise LiveRecoveryExecutionError(msg)

    def _readback(  # noqa: C901
        self,
        step: LiveRecoveryStep,
        plan: Mapping[str, object],
        directory: Path,
        *,
        create: bool,
    ) -> LiveRecoveryStepReceipt:
        raw_vault = plan.get("vault")
        if type(raw_vault) is not dict:
            msg = "LIVE_RECOVERY_PLAN_INVALID"
            raise LiveRecoveryExecutionError(msg)
        vault = cast("dict[str, object]", raw_vault)
        if type(vault.get("copies")) is not list:
            msg = "LIVE_RECOVERY_PLAN_INVALID"
            raise LiveRecoveryExecutionError(msg)
        side = (
            "primary" if step is LiveRecoveryStep.PRIMARY_VAULT_CLEAN_ROOM_READBACK else "recovery"
        )
        reader = self._primary if side == "primary" else self._recovery
        inventory: list[dict[str, object]] = []
        for index, raw_copy in enumerate(cast("list[object]", vault["copies"])):
            if type(raw_copy) is not dict:
                msg = "LIVE_RECOVERY_PLAN_INVALID"
                raise LiveRecoveryExecutionError(msg)
            copy = cast("dict[str, object]", raw_copy)
            if type(copy.get(side)) is not dict:
                msg = "LIVE_RECOVERY_PLAN_INVALID"
                raise LiveRecoveryExecutionError(msg)
            raw_reference = cast("dict[str, object]", copy[side])
            expected_keys = {"byte_length", "fingerprint", "logical_key", "vault", "version_id"}
            if set(raw_reference) != expected_keys or raw_reference["vault"] != side.upper():
                msg = "LIVE_RECOVERY_PLAN_INVALID"
                raise LiveRecoveryExecutionError(msg)
            reference = ExactObjectReference(
                VaultName(side.upper()),
                _string(raw_reference["logical_key"]),
                _string(raw_reference["version_id"]),
                _fingerprint(raw_reference["fingerprint"]),
                _count(raw_reference["byte_length"]),
            )
            content = reader.read_exact(reference)
            if (
                len(content) != reference.byte_length
                or f"sha256:{sha256(content).hexdigest()}" != reference.fingerprint
            ):
                msg = "LIVE_RECOVERY_VAULT_READBACK_FAILED"
                raise LiveRecoveryExecutionError(msg)
            artifact = directory / f"{index:04d}.bin"
            if create:
                reread = _retain_exact(artifact, content)
            elif not _real_file(artifact):
                msg = "LIVE_RECOVERY_VAULT_READBACK_FAILED"
                raise LiveRecoveryExecutionError(msg)
            else:
                reread = artifact.read_bytes()
            if reread != content:
                msg = "LIVE_RECOVERY_VAULT_READBACK_FAILED"
                raise LiveRecoveryExecutionError(msg)
            inventory.append(
                {
                    "byte_length": len(reread),
                    "fingerprint": reference.fingerprint,
                    "logical_key": reference.logical_key,
                    "version_id": reference.version_id,
                }
            )
        fingerprint = _digest(inventory)
        target = self._target_from_plan(step, plan)
        return LiveRecoveryStepReceipt(
            step,
            _fingerprint(plan["fingerprint"]),
            target,
            fingerprint,
            fingerprint,
        )


@dataclass(frozen=True, slots=True)
class LiveRecoveryExecutionResult:
    """Canonical result issued only after all seven exact receipts read back."""

    operation_id: str
    plan_fingerprint: str
    receipts: tuple[LiveRecoveryStepReceipt, ...]
    live_recovery_proved: bool
    canonical_bytes: bytes


def _sealed_reference_document(reference: SealedCredentialReference) -> dict[str, object]:
    return {
        "credential_id": reference.credential_id,
        "fingerprint": reference.fingerprint,
        "sealed_path": reference.sealed_path,
    }


def _seal_document(body: Mapping[str, object]) -> bytes:
    unsigned = dict(body)
    unsigned["fingerprint"] = _digest(body)
    return _canonical(unsigned) + b"\n"


def _retention_document(value: RetentionProfile) -> dict[str, object]:
    if type(value) is not RetentionProfile:
        _local_failure("LIVE_RECOVERY_REQUEST_INVALID")
    return {
        "legal_hold": value.legal_hold,
        "profile_id": value.profile_id,
        "retain_until": value.retain_until,
    }


def _descriptor_document(value: ArtifactDescriptor) -> dict[str, object]:
    if type(value) is not ArtifactDescriptor:
        _local_failure("LIVE_RECOVERY_REQUEST_INVALID")
    return {
        "acquired_at": value.acquired_at,
        "acquisition_method": value.acquisition_method,
        "artifact_class": value.artifact_class.value,
        "artifact_id": value.artifact_id,
        "artifact_version_id": value.artifact_version_id,
        "character_encoding": value.character_encoding,
        "content_encoding": value.content_encoding,
        "declared_media_type": value.declared_media_type,
        "detected_media_type": value.detected_media_type,
        "observation_cutoff": value.observation_cutoff,
        "observation_id": value.observation_id,
        "retention": _retention_document(value.retention),
        "source_id": value.source_id,
        "source_locator": value.source_locator,
        "transport_metadata": [
            {"name": name, "value": metadata_value}
            for name, metadata_value in value.transport_metadata
        ],
    }


def _receipt_document_for_request(value: EvidencePackageReceipt) -> dict[str, object]:
    if type(value) is not EvidencePackageReceipt or type(value.manifest) is not EvidenceManifest:
        _local_failure("LIVE_RECOVERY_REQUEST_INVALID")
    manifest = value.manifest
    entries = sorted(manifest.entries, key=lambda item: item.descriptor.artifact_id)
    copies = sorted(
        value.copies,
        key=lambda item: (item.primary.logical_key, item.primary.version_id),
    )
    return {
        "copies": [
            {
                "primary": _exact_object_reference_document(item.primary),
                "recovery": _exact_object_reference_document(item.recovery),
            }
            for item in copies
        ],
        "manifest": {
            "entries": [
                {
                    "descriptor": _descriptor_document(item.descriptor),
                    "primary": _exact_object_reference_document(item.primary),
                }
                for item in entries
            ],
            "observation_id": manifest.observation_id,
            "package_id": manifest.package_id,
            "package_kind": manifest.package_kind,
        },
        "primary_manifest": _exact_object_reference_document(value.primary_manifest),
        "recovery_manifest": _exact_object_reference_document(value.recovery_manifest),
    }


def build_live_recovery_request(request: RecoveryContractRequest) -> bytes:
    """Serialize one issuer-validated recovery contract for restart-safe planning."""
    _request_snapshot(request)
    body: dict[str, object] = {
        "external_ledger_digest_reference": _reference_document(
            request.external_ledger_digest_reference
        ),
        "migration_prefix": _migration_documents(request.migration_prefix),
        "primary_vault_identity": request.primary_vault_identity,
        "projection_rebuild_fingerprint": request.projection_rebuild_fingerprint,
        "recovery_vault_identity": request.recovery_vault_identity,
        "register_families": _family_documents(request.register_families),
        "request_fingerprint": request.fingerprint,
        "restored_ledger_verification_receipt": _reference_document(
            request.restored_ledger_verification_receipt
        ),
        "scheduler_hubs": [
            {"hubs": list(item.hubs), "role": item.role.value}
            for item in sorted(request.scheduler_hubs, key=lambda item: item.role.value)
        ],
        "schema": _LIVE_REQUEST_SCHEMA,
        "source_ledger_verification_receipt": _reference_document(
            request.source_ledger_verification_receipt
        ),
        "sql_backup_reference": _reference_document(request.sql_backup_reference),
        "vault_package_receipt": _receipt_document_for_request(request.vault_package_receipt),
    }
    return _seal_document(body)


def _request_reference(value: object, code: str) -> RecoveryEvidenceReference:
    if type(value) is not dict:
        raise LiveRecoveryExecutionError(code)
    document = cast("dict[str, object]", value)
    if set(document) != {"evidence_id", "fingerprint"}:
        raise LiveRecoveryExecutionError(code)
    return RecoveryEvidenceReference(
        _opaque(document["evidence_id"]),
        _fingerprint(document["fingerprint"]),
    )


def _request_object_reference(
    value: object,
    code: str,
    *,
    expected_vault: VaultName | None = None,
) -> ExactObjectReference:
    if type(value) is not dict:
        raise LiveRecoveryExecutionError(code)
    document = cast("dict[str, object]", value)
    if set(document) != {"byte_length", "fingerprint", "logical_key", "vault", "version_id"}:
        raise LiveRecoveryExecutionError(code)
    try:
        vault = VaultName(_string(document["vault"]))
        reference = ExactObjectReference(
            vault,
            _string(document["logical_key"]),
            _string(document["version_id"]),
            _fingerprint(document["fingerprint"]),
            _count(document["byte_length"]),
        )
    except (TypeError, ValueError) as error:
        raise LiveRecoveryExecutionError(code) from error
    if expected_vault is not None and reference.vault is not expected_vault:
        raise LiveRecoveryExecutionError(code)
    return reference


def _request_descriptor(value: object, code: str) -> ArtifactDescriptor:
    if type(value) is not dict:
        raise LiveRecoveryExecutionError(code)
    document = cast("dict[str, object]", value)
    expected = {
        "acquired_at",
        "acquisition_method",
        "artifact_class",
        "artifact_id",
        "artifact_version_id",
        "character_encoding",
        "content_encoding",
        "declared_media_type",
        "detected_media_type",
        "observation_cutoff",
        "observation_id",
        "retention",
        "source_id",
        "source_locator",
        "transport_metadata",
    }
    if set(document) != expected or type(document["retention"]) is not dict:
        raise LiveRecoveryExecutionError(code)
    retention_raw = cast("dict[str, object]", document["retention"])
    metadata_raw = document["transport_metadata"]
    if (
        set(retention_raw) != {"legal_hold", "profile_id", "retain_until"}
        or type(retention_raw["legal_hold"]) is not bool
        or type(metadata_raw) is not list
    ):
        raise LiveRecoveryExecutionError(code)
    metadata: list[tuple[str, str]] = []
    for item in cast("list[object]", metadata_raw):
        if type(item) is not dict or set(cast("dict[str, object]", item)) != {"name", "value"}:
            raise LiveRecoveryExecutionError(code)
        typed = cast("dict[str, object]", item)
        metadata.append((_string(typed["name"]), _string(typed["value"])))
    try:
        return ArtifactDescriptor(
            artifact_id=_string(document["artifact_id"]),
            artifact_version_id=_string(document["artifact_version_id"]),
            artifact_class=ArtifactClass(_string(document["artifact_class"])),
            source_id=_string(document["source_id"]),
            observation_id=_string(document["observation_id"]),
            observation_cutoff=_string(document["observation_cutoff"]),
            acquired_at=_string(document["acquired_at"]),
            acquisition_method=_string(document["acquisition_method"]),
            source_locator=_string(document["source_locator"]),
            declared_media_type=_string(document["declared_media_type"]),
            detected_media_type=_string(document["detected_media_type"]),
            content_encoding=_string(document["content_encoding"]),
            character_encoding=_string(document["character_encoding"]),
            transport_metadata=tuple(metadata),
            retention=RetentionProfile(
                _string(retention_raw["profile_id"]),
                _string(retention_raw["retain_until"]),
                retention_raw["legal_hold"],
            ),
        )
    except (TypeError, ValueError) as error:
        raise LiveRecoveryExecutionError(code) from error


def _request_receipt(value: object, code: str) -> EvidencePackageReceipt:  # noqa: C901
    if type(value) is not dict:
        raise LiveRecoveryExecutionError(code)
    document = cast("dict[str, object]", value)
    if set(document) != {"copies", "manifest", "primary_manifest", "recovery_manifest"}:
        raise LiveRecoveryExecutionError(code)
    manifest_raw = document["manifest"]
    copies_raw = document["copies"]
    if type(manifest_raw) is not dict or type(copies_raw) is not list:
        raise LiveRecoveryExecutionError(code)
    manifest_document = cast("dict[str, object]", manifest_raw)
    if set(manifest_document) != {"entries", "observation_id", "package_id", "package_kind"}:
        raise LiveRecoveryExecutionError(code)
    entries_raw = manifest_document["entries"]
    if type(entries_raw) is not list:
        raise LiveRecoveryExecutionError(code)
    entries: list[EvidenceManifestEntry] = []
    for item in cast("list[object]", entries_raw):
        if type(item) is not dict or set(cast("dict[str, object]", item)) != {
            "descriptor",
            "primary",
        }:
            raise LiveRecoveryExecutionError(code)
        typed = cast("dict[str, object]", item)
        entries.append(
            EvidenceManifestEntry(
                _request_descriptor(typed["descriptor"], code),
                _request_object_reference(typed["primary"], code, expected_vault=VaultName.PRIMARY),
            )
        )
    copies: list[RecoveryCopyReceipt] = []
    for item in cast("list[object]", copies_raw):
        if type(item) is not dict or set(cast("dict[str, object]", item)) != {
            "primary",
            "recovery",
        }:
            raise LiveRecoveryExecutionError(code)
        typed = cast("dict[str, object]", item)
        copies.append(
            RecoveryCopyReceipt(
                _request_object_reference(typed["primary"], code, expected_vault=VaultName.PRIMARY),
                _request_object_reference(
                    typed["recovery"], code, expected_vault=VaultName.RECOVERY
                ),
            )
        )
    try:
        manifest = EvidenceManifest(
            _string(manifest_document["package_kind"]),
            _string(manifest_document["package_id"]),
            _string(manifest_document["observation_id"]),
            tuple(entries),
        )
        return EvidencePackageReceipt(
            manifest,
            _request_object_reference(
                document["primary_manifest"], code, expected_vault=VaultName.PRIMARY
            ),
            _request_object_reference(
                document["recovery_manifest"], code, expected_vault=VaultName.RECOVERY
            ),
            tuple(copies),
        )
    except (TypeError, ValueError) as error:
        raise LiveRecoveryExecutionError(code) from error


def load_live_recovery_request(raw: bytes) -> RecoveryContractRequest:
    """Load and reissue one canonical retained recovery request after process restart."""
    code = "LIVE_RECOVERY_REQUEST_INVALID"
    document = _verified_sealed_document(raw, _LIVE_REQUEST_SCHEMA, code)
    expected = {
        "external_ledger_digest_reference",
        "fingerprint",
        "migration_prefix",
        "primary_vault_identity",
        "projection_rebuild_fingerprint",
        "recovery_vault_identity",
        "register_families",
        "request_fingerprint",
        "restored_ledger_verification_receipt",
        "scheduler_hubs",
        "schema",
        "source_ledger_verification_receipt",
        "sql_backup_reference",
        "vault_package_receipt",
    }
    if set(document) != expected:
        raise LiveRecoveryExecutionError(code)
    migrations_raw = document["migration_prefix"]
    families_raw = document["register_families"]
    hubs_raw = document["scheduler_hubs"]
    if (
        type(migrations_raw) is not list
        or type(families_raw) is not list
        or type(hubs_raw) is not list
    ):
        raise LiveRecoveryExecutionError(code)
    migration_values = cast("list[object]", migrations_raw)
    family_values = cast("list[object]", families_raw)
    hub_values = cast("list[object]", hubs_raw)
    try:
        migrations = tuple(
            MigrationReadback(
                _string(cast("dict[str, object]", item)["migration_id"]),
                _fingerprint(cast("dict[str, object]", item)["package_fingerprint"]),
            )
            for item in migration_values
            if type(item) is dict
            and set(cast("dict[str, object]", item)) == {"migration_id", "package_fingerprint"}
        )
        families = tuple(
            RegisterFamilyReadback(
                _string(cast("dict[str, object]", item)["family"]),
                _count(cast("dict[str, object]", item)["row_count"]),
                _fingerprint(cast("dict[str, object]", item)["content_fingerprint"]),
            )
            for item in family_values
            if type(item) is dict
            and set(cast("dict[str, object]", item))
            == {"content_fingerprint", "family", "row_count"}
        )
        hubs = tuple(
            SchedulerHubInventory(
                SchedulerRole(_string(cast("dict[str, object]", item)["role"])),
                tuple(
                    _opaque(part)
                    for part in cast("list[object]", cast("dict[str, object]", item)["hubs"])
                ),
            )
            for item in hub_values
            if type(item) is dict
            and set(cast("dict[str, object]", item)) == {"hubs", "role"}
            and type(cast("dict[str, object]", item)["hubs"]) is list
        )
        if (
            len(migrations) != len(migration_values)
            or len(families) != len(family_values)
            or len(hubs) != len(hub_values)
        ):
            raise LiveRecoveryExecutionError(code)
        request = freeze_local_recovery_contract(
            migrations,
            families,
            _request_reference(document["sql_backup_reference"], code),
            _request_reference(document["external_ledger_digest_reference"], code),
            _request_reference(document["source_ledger_verification_receipt"], code),
            _request_reference(document["restored_ledger_verification_receipt"], code),
            _request_receipt(document["vault_package_receipt"], code),
            _opaque(document["primary_vault_identity"]),
            _opaque(document["recovery_vault_identity"]),
            hubs,
        )
    except (KeyError, TypeError, ValueError, RecoveryProofError) as error:
        raise LiveRecoveryExecutionError(code) from error
    if (
        request.fingerprint != document["request_fingerprint"]
        or request.projection_rebuild_fingerprint != document["projection_rebuild_fingerprint"]
        or build_live_recovery_request(request) != raw
    ):
        raise LiveRecoveryExecutionError(code)
    return request


def build_live_recovery_credential_manifest(
    operation_id: str,
    references: tuple[SealedCredentialReference, ...],
) -> bytes:
    """Freeze reference-only credentials without opening any sealed file."""
    _opaque(operation_id)
    if (
        type(references) is not tuple
        or tuple(sorted(item.credential_id for item in references)) != _LIVE_CREDENTIAL_IDS
        or len({item.credential_id for item in references}) != len(_LIVE_CREDENTIAL_IDS)
    ):
        _local_failure("LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID")
    return _seal_document(
        {
            "credentials": [_sealed_reference_document(item) for item in references],
            "operation_id": operation_id,
            "schema": _LIVE_CREDENTIAL_SCHEMA,
        }
    )


def _file_reference(path: Path) -> dict[str, object]:
    if not _real_file(path):
        _local_failure("LIVE_RECOVERY_INPUT_NOT_READY")
    content = path.read_bytes()
    return {
        "byte_length": len(content),
        "fingerprint": f"sha256:{sha256(content).hexdigest()}",
        "path": str(path),
    }


def _exact_object_reference_document(reference: ExactObjectReference) -> dict[str, object]:
    return {
        "byte_length": reference.byte_length,
        "fingerprint": reference.fingerprint,
        "logical_key": reference.logical_key,
        "vault": reference.vault.value,
        "version_id": reference.version_id,
    }


def build_live_recovery_plan(
    request: RecoveryContractRequest,
    configuration: LocalRecoveryConfiguration,
    credential_manifest: bytes,
    *,
    sql_backup_path_manifest: bytes | None = None,
) -> bytes:
    """Build a restart-safe exact plan from the admitted contract and retained inputs."""
    frozen = _request_snapshot(request)
    credentials = _live_credentials(credential_manifest, configuration.operation_id)
    sql_credential = next(
        item for item in credentials if item.credential_id == "SQL_SERVER_RECOVERY_ADMIN"
    )
    sql_path_manifest_fingerprint = None
    if sql_backup_path_manifest is not None:
        sql_path_manifest_fingerprint = _digest(
            _canonical_document(
                sql_backup_path_manifest,
                "LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID",
            )
        )
    targets = derive_local_recovery_targets(configuration)
    receipt = request.vault_package_receipt
    copies = [
        {
            "primary": _exact_object_reference_document(item.primary),
            "recovery": _exact_object_reference_document(item.recovery),
        }
        for item in receipt.copies
    ]
    copies.append(
        {
            "primary": _exact_object_reference_document(receipt.primary_manifest),
            "recovery": _exact_object_reference_document(receipt.recovery_manifest),
        }
    )
    steps = _live_steps(configuration)
    body: dict[str, object] = {
        "credential_manifest_fingerprint": _digest(
            _canonical_document(credential_manifest, "LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID")
        ),
        "input_references": {
            "scheduler_general": _file_reference(
                configuration.scheduler_snapshot_root / "general.json"
            ),
            "scheduler_general_checkpoint": _file_reference(
                configuration.scheduler_snapshot_root / "general-checkpoint.bin"
            ),
            "scheduler_promotion": _file_reference(
                configuration.scheduler_snapshot_root / "promotion.json"
            ),
            "scheduler_promotion_checkpoint": _file_reference(
                configuration.scheduler_snapshot_root / "promotion-checkpoint.bin"
            ),
            "sql": _file_reference(configuration.sql_snapshot_path),
        },
        "operation_id": configuration.operation_id,
        "request_fingerprint": request.fingerprint,
        "schema": _LIVE_PLAN_SCHEMA,
        "sql": {
            "backup_path_manifest_fingerprint": sql_path_manifest_fingerprint,
            "backup_reference": _reference_document(request.sql_backup_reference),
            "credential_reference_fingerprint": _digest(_sealed_reference_document(sql_credential)),
            "expected_families": _family_documents(request.register_families),
            "expected_migrations": _migration_documents(request.migration_prefix),
            "external_ledger_digest_reference": _reference_document(
                request.external_ledger_digest_reference
            ),
            "projection_rebuild_fingerprint": request.projection_rebuild_fingerprint,
            "restored_ledger_verification_receipt": _reference_document(
                request.restored_ledger_verification_receipt
            ),
            "source_ledger_verification_receipt": _reference_document(
                request.source_ledger_verification_receipt
            ),
            "target_database_identity": targets.sql_database_identity,
            "target_database_name": targets.sql_database_name,
        },
        "steps": steps,
        "targets_fingerprint": _digest(steps),
        "vault": {
            "copies": copies,
            "primary_vault_identity": request.primary_vault_identity,
            "recovery_vault_identity": request.recovery_vault_identity,
            "target_vault_identity": targets.vault_identity,
        },
        "scheduler": [
            {"hubs": list(hubs), "role": role.value}
            for role, hubs in cast("tuple[tuple[SchedulerRole, tuple[str, ...]], ...]", frozen[9])
        ],
    }
    del credentials
    return _seal_document(body)


def _live_steps(configuration: LocalRecoveryConfiguration) -> list[dict[str, object]]:
    targets = derive_local_recovery_targets(configuration)
    output: list[dict[str, object]] = []
    for step in LiveRecoveryStep:
        if step is LiveRecoveryStep.SQL_RESTORE_READBACK:
            target = targets.sql_database_identity
        elif "VAULT" in step.value:
            target = _derived_opaque(targets.vault_identity, step.value)
        else:
            target = _derived_opaque(configuration.operation_id, step.value)
        output.append({"step": step.value, "target_identity": target})
    return output


def _verified_sealed_document(raw: bytes, schema: str, code: str) -> dict[str, object]:
    document = _canonical_document(raw, code)
    fingerprint = document.get("fingerprint")
    unsigned = dict(document)
    unsigned.pop("fingerprint", None)
    if document.get("schema") != schema or fingerprint != _digest(unsigned):
        raise LiveRecoveryExecutionError(code)
    return document


def _live_credentials(raw: bytes, operation_id: str) -> tuple[SealedCredentialReference, ...]:
    document = _verified_sealed_document(
        raw, _LIVE_CREDENTIAL_SCHEMA, "LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID"
    )
    values = document.get("credentials")
    if document.get("operation_id") != operation_id or type(values) is not list:
        msg = "LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID"
        raise LiveRecoveryExecutionError(msg)
    references: list[SealedCredentialReference] = []
    try:
        for raw_reference in cast("list[object]", values):
            if type(raw_reference) is not dict:
                _local_failure("LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID")
            reference = cast("dict[str, object]", raw_reference)
            if set(reference) != {
                "credential_id",
                "fingerprint",
                "sealed_path",
            }:
                _local_failure("LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID")
            references.append(
                SealedCredentialReference(
                    _string(reference["credential_id"]),
                    _string(reference["sealed_path"]),
                    _fingerprint(reference["fingerprint"]),
                )
            )
    except (KeyError, TypeError, ValueError) as error:
        msg = "LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID"
        raise LiveRecoveryExecutionError(msg) from error
    result = tuple(sorted(references, key=lambda item: item.credential_id))
    if tuple(item.credential_id for item in result) != _LIVE_CREDENTIAL_IDS:
        msg = "LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID"
        raise LiveRecoveryExecutionError(msg)
    return result


def _live_plan(raw: bytes) -> dict[str, object]:
    document = _verified_sealed_document(raw, _LIVE_PLAN_SCHEMA, "LIVE_RECOVERY_PLAN_INVALID")
    expected = {
        "credential_manifest_fingerprint",
        "fingerprint",
        "input_references",
        "operation_id",
        "request_fingerprint",
        "scheduler",
        "schema",
        "sql",
        "steps",
        "targets_fingerprint",
        "vault",
    }
    if set(document) != expected:
        msg = "LIVE_RECOVERY_PLAN_INVALID"
        raise LiveRecoveryExecutionError(msg)
    _opaque(document["operation_id"])
    _fingerprint(document["request_fingerprint"])
    _fingerprint(document["credential_manifest_fingerprint"])
    steps = document["steps"]
    if type(steps) is not list:
        msg = "LIVE_RECOVERY_PLAN_INVALID"
        raise LiveRecoveryExecutionError(msg)
    typed_steps = cast("list[object]", steps)
    if len(typed_steps) != len(LiveRecoveryStep):
        msg = "LIVE_RECOVERY_PLAN_INVALID"
        raise LiveRecoveryExecutionError(msg)
    expected_steps = tuple(LiveRecoveryStep)
    for expected_step, raw_step in zip(expected_steps, typed_steps, strict=True):
        if type(raw_step) is not dict:
            msg = "LIVE_RECOVERY_PLAN_INVALID"
            raise LiveRecoveryExecutionError(msg)
        step = cast("dict[str, object]", raw_step)
        if set(step) != {"step", "target_identity"}:
            msg = "LIVE_RECOVERY_PLAN_INVALID"
            raise LiveRecoveryExecutionError(msg)
        if step["step"] != expected_step.value:
            msg = "LIVE_RECOVERY_PLAN_INVALID"
            raise LiveRecoveryExecutionError(msg)
        _opaque(step["target_identity"])
    if document["targets_fingerprint"] != _digest(typed_steps):
        msg = "LIVE_RECOVERY_PLAN_INVALID"
        raise LiveRecoveryExecutionError(msg)
    return document


def _live_authority(raw: bytes, plan: Mapping[str, object]) -> None:
    document = _verified_sealed_document(
        raw, _LIVE_AUTHORITY_SCHEMA, "LIVE_RECOVERY_AUTHORITY_INVALID"
    )
    expected = {
        "authority_id",
        "authorized_steps",
        "fingerprint",
        "operation_id",
        "plan_fingerprint",
        "schema",
        "targets_fingerprint",
    }
    if set(document) != expected:
        msg = "LIVE_RECOVERY_AUTHORITY_INVALID"
        raise LiveRecoveryExecutionError(msg)
    steps = document["authorized_steps"]
    if (
        not _string(document["authority_id"])
        or document["operation_id"] != plan["operation_id"]
        or document["plan_fingerprint"] != plan["fingerprint"]
        or document["targets_fingerprint"] != plan["targets_fingerprint"]
        or steps != [step.value for step in LiveRecoveryStep]
    ):
        msg = "LIVE_RECOVERY_AUTHORITY_INVALID"
        raise LiveRecoveryExecutionError(msg)


def _receipt_document(receipt: LiveRecoveryStepReceipt) -> dict[str, object]:
    return {
        "effect_fingerprint": receipt.effect_fingerprint,
        "plan_fingerprint": receipt.plan_fingerprint,
        "readback_fingerprint": receipt.readback_fingerprint,
        "step": receipt.step.value,
        "target_identity": receipt.target_identity,
    }


def _validate_live_receipt(
    receipt: LiveRecoveryStepReceipt,
    step: LiveRecoveryStep,
    plan: Mapping[str, object],
) -> None:
    raw_steps = cast("list[dict[str, object]]", plan["steps"])
    expected_target = raw_steps[tuple(LiveRecoveryStep).index(step)]["target_identity"]
    if (
        type(receipt) is not LiveRecoveryStepReceipt
        or receipt.step is not step
        or receipt.plan_fingerprint != plan["fingerprint"]
        or receipt.target_identity != expected_target
        or receipt.effect_fingerprint != receipt.readback_fingerprint
    ):
        msg = "LIVE_RECOVERY_RECEIPT_INVALID"
        raise LiveRecoveryExecutionError(msg)


def _state_path(root: Path, operation_id: str) -> Path:
    if not _real_directory(root):
        msg = "LIVE_RECOVERY_STATE_ROOT_INVALID"
        raise LiveRecoveryExecutionError(msg)
    return root / f"{operation_id}.json"


def _write_live_state(
    path: Path,
    plan: Mapping[str, object],
    receipts: Sequence[LiveRecoveryStepReceipt],
) -> None:
    body: dict[str, object] = {
        "operation_id": plan["operation_id"],
        "plan_fingerprint": plan["fingerprint"],
        "receipts": [_receipt_document(item) for item in receipts],
        "schema": _LIVE_STATE_SCHEMA,
    }
    content = _seal_document(body)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    if path.read_bytes() != content:
        msg = "LIVE_RECOVERY_STATE_INVALID"
        raise LiveRecoveryExecutionError(msg)


def _read_live_state(path: Path, plan: Mapping[str, object]) -> list[LiveRecoveryStepReceipt]:
    if not path.exists():
        return []
    document = _verified_sealed_document(
        path.read_bytes(), _LIVE_STATE_SCHEMA, "LIVE_RECOVERY_STATE_INVALID"
    )
    values = document.get("receipts")
    if (
        set(document) != {"fingerprint", "operation_id", "plan_fingerprint", "receipts", "schema"}
        or document["operation_id"] != plan["operation_id"]
        or document["plan_fingerprint"] != plan["fingerprint"]
        or type(values) is not list
    ):
        msg = "LIVE_RECOVERY_STATE_INVALID"
        raise LiveRecoveryExecutionError(msg)
    receipts: list[LiveRecoveryStepReceipt] = []
    try:
        for expected_step, raw_receipt in zip(
            tuple(LiveRecoveryStep), cast("list[object]", values), strict=False
        ):
            if type(raw_receipt) is not dict:
                _local_failure("LIVE_RECOVERY_STATE_INVALID")
            value = cast("dict[str, object]", raw_receipt)
            if set(value) != {
                "effect_fingerprint",
                "plan_fingerprint",
                "readback_fingerprint",
                "step",
                "target_identity",
            }:
                _local_failure("LIVE_RECOVERY_STATE_INVALID")
            receipt = LiveRecoveryStepReceipt(
                LiveRecoveryStep(_string(value["step"])),
                _fingerprint(value["plan_fingerprint"]),
                _opaque(value["target_identity"]),
                _fingerprint(value["effect_fingerprint"]),
                _fingerprint(value["readback_fingerprint"]),
            )
            _validate_live_receipt(receipt, expected_step, plan)
            receipts.append(receipt)
    except (KeyError, TypeError, ValueError) as error:
        msg = "LIVE_RECOVERY_STATE_INVALID"
        raise LiveRecoveryExecutionError(msg) from error
    return receipts


def _port_for_step(
    adapters: LiveRecoveryExecutionAdapters, step: LiveRecoveryStep
) -> LiveRecoveryStepPort:
    if step is LiveRecoveryStep.SQL_RESTORE_READBACK:
        return adapters.sql
    if "VAULT" in step.value:
        return adapters.vault
    return adapters.scheduler


def execute_live_recovery(
    plan_bytes: bytes,
    authority_bytes: bytes,
    credential_manifest_bytes: bytes,
    state_root: Path,
    adapters: LiveRecoveryExecutionAdapters,
) -> LiveRecoveryExecutionResult:
    """Execute or resume the exact authorized plan through create-or-match ports."""
    plan = _live_plan(plan_bytes)
    _live_authority(authority_bytes, plan)
    credentials = _live_credentials(credential_manifest_bytes, _opaque(plan["operation_id"]))
    if plan["credential_manifest_fingerprint"] != _digest(
        _canonical_document(credential_manifest_bytes, "LIVE_RECOVERY_CREDENTIAL_INPUT_INVALID")
    ):
        msg = "LIVE_RECOVERY_CREDENTIAL_INPUT_DRIFT"
        raise LiveRecoveryExecutionError(msg)
    if type(adapters) is not LiveRecoveryExecutionAdapters:
        msg = "LIVE_RECOVERY_ADAPTERS_NOT_COMPOSED"
        raise LiveRecoveryExecutionError(msg)
    state_path = _state_path(state_root, _opaque(plan["operation_id"]))
    receipts = _read_live_state(state_path, plan)
    for step in tuple(LiveRecoveryStep)[len(receipts) :]:
        port = _port_for_step(adapters, step)
        try:
            receipt = port.reconcile(step, plan, credentials)
            if receipt is None:
                receipt = port.execute(step, plan, credentials)
        except LiveRecoveryAcknowledgementLost as error:
            msg = "LIVE_RECOVERY_ACKNOWLEDGEMENT_LOST"
            raise LiveRecoveryExecutionError(msg) from error
        except LiveRecoveryExecutionError:
            raise
        except Exception as error:
            msg = "LIVE_RECOVERY_EFFECT_FAILED"
            raise LiveRecoveryExecutionError(msg) from error
        _validate_live_receipt(receipt, step, plan)
        receipts.append(receipt)
        _write_live_state(state_path, plan, receipts)
    result_body: dict[str, object] = {
        "live_recovery_proved": True,
        "operation_id": plan["operation_id"],
        "plan_fingerprint": plan["fingerprint"],
        "receipts": [_receipt_document(item) for item in receipts],
        "schema": _LIVE_RESULT_SCHEMA,
    }
    canonical = _seal_document(result_body)
    return LiveRecoveryExecutionResult(
        operation_id=_opaque(plan["operation_id"]),
        plan_fingerprint=_fingerprint(plan["fingerprint"]),
        receipts=tuple(receipts),
        live_recovery_proved=True,
        canonical_bytes=canonical,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--request-fingerprint", required=True)
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--sql-snapshot", required=True, type=Path)
    parser.add_argument("--primary-vault-root", required=True, type=Path)
    parser.add_argument("--recovery-vault-root", required=True, type=Path)
    parser.add_argument("--scheduler-snapshot-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--mode",
        choices=tuple(item.value for item in LocalRecoveryMode),
        default=LocalRecoveryMode.PREFLIGHT.value,
    )
    parser.add_argument("--authorize-local-execution", action="store_true")
    parser.add_argument("--live-request", type=Path)
    parser.add_argument("--live-plan", type=Path)
    parser.add_argument("--live-authority", type=Path)
    parser.add_argument("--live-credential-manifest", type=Path)
    parser.add_argument("--sql-backup-path-manifest", type=Path)
    parser.add_argument("--live-clean-room-root", type=Path)
    parser.add_argument("--live-state-root", type=Path)
    return parser


def _write_live_result(path: Path, content: bytes) -> None:
    if not _real_directory(path.parent):
        _local_failure("LIVE_RECOVERY_OUTPUT_INVALID")
    temporary = path.with_name(f".{path.name}.live.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            _PRIVATE_FILE_MODE,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    if path.read_bytes() != content:
        _local_failure("LIVE_RECOVERY_OUTPUT_INVALID")


def _read_live_credential(reference: SealedCredentialReference) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            reference.sealed_path,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        status = os.fstat(descriptor)
        if not 1 <= status.st_size <= 4096:  # noqa: PLR2004
            _local_failure("LIVE_RECOVERY_CREDENTIAL_ADAPTER_NOT_READY")
        content = os.read(descriptor, status.st_size + 1)
    except OSError as error:
        message = "LIVE_RECOVERY_CREDENTIAL_ADAPTER_NOT_READY"
        raise LiveRecoveryExecutionError(message) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        len(content) != status.st_size
        or f"sha256:{sha256(content).hexdigest()}" != reference.fingerprint
    ):
        _local_failure("LIVE_RECOVERY_CREDENTIAL_ADAPTER_NOT_READY")
    return content


def _compose_live_adapters(
    plan: Mapping[str, object],
    credential_bytes: bytes,
    sql_backup_path_manifest: Path | None,
    clean_room_root: Path | None,
) -> LiveRecoveryExecutionAdapters:
    """Compose exact local V1 adapters only after authority and reference validation."""
    if (
        not isinstance(sql_backup_path_manifest, Path)
        or not _real_file(sql_backup_path_manifest)
        or not isinstance(clean_room_root, Path)
        or not _real_directory(clean_room_root)
        or stat.S_IMODE(clean_room_root.lstat().st_mode) != _PRIVATE_DIRECTORY_MODE
    ):
        _local_failure("LIVE_RECOVERY_ADAPTER_INPUT_NOT_READY")
    helper_paths = (
        Path("/usr/local/libexec/asklegal-sql-recovery-admin"),
        Path("/usr/local/libexec/asklegal-scheduler-recovery-admin"),
    )
    if any(not _real_file(path) or not os.access(path, os.X_OK) for path in helper_paths):
        _local_failure("LIVE_RECOVERY_PRIVILEGED_HELPER_NOT_READY")
    credentials = _live_credentials(credential_bytes, _opaque(plan["operation_id"]))
    by_id = {item.credential_id: item for item in credentials}
    try:
        from asklegal_evidence_vault import (  # noqa: PLC0415
            S3AccessCredential,
            create_exact_v1_s3_vault,
        )

        from tools.hk_v1_scheduler_recovery import (  # noqa: PLC0415
            SchedulerLiveRecoveryPort,
            SubprocessSchedulerRecoveryCommandRunner,
        )
        from tools.hk_v1_sql_recovery import (  # noqa: PLC0415
            SQLServerLiveRecoveryPort,
            SubprocessSQLRecoveryCommandRunner,
        )

        primary = create_exact_v1_s3_vault(
            VaultName.PRIMARY,
            S3AccessCredential.from_bytes(
                _read_live_credential(by_id["PRIMARY_VAULT_RECOVERY_READER"])
            ),
        )
        recovery = create_exact_v1_s3_vault(
            VaultName.RECOVERY,
            S3AccessCredential.from_bytes(
                _read_live_credential(by_id["RECOVERY_VAULT_RECOVERY_READER"])
            ),
        )
        return LiveRecoveryExecutionAdapters(
            SQLServerLiveRecoveryPort(
                SubprocessSQLRecoveryCommandRunner(),
                sql_backup_path_manifest.read_bytes(),
            ),
            ImmutableVaultLiveRecoveryPort(primary, recovery, clean_room_root),
            SchedulerLiveRecoveryPort(SubprocessSchedulerRecoveryCommandRunner()),
        )
    except LiveRecoveryExecutionError:
        raise
    except Exception as error:
        message = "LIVE_RECOVERY_ADAPTER_INPUT_NOT_READY"
        raise LiveRecoveryExecutionError(message) from error


def main(*, live_adapters: LiveRecoveryExecutionAdapters | None = None) -> None:
    """Default to preflight; live execution requires exact detached files and ports."""
    arguments = _parser().parse_args()
    configuration = LocalRecoveryConfiguration(
        arguments.operation_id,
        arguments.request_fingerprint,
        arguments.workspace_root,
        arguments.sql_snapshot,
        arguments.primary_vault_root,
        arguments.recovery_vault_root,
        arguments.scheduler_snapshot_root,
        arguments.output,
    )
    mode = LocalRecoveryMode(arguments.mode)
    if mode is LocalRecoveryMode.PLAN_LIVE:
        paths = (
            arguments.live_request,
            arguments.live_credential_manifest,
            arguments.sql_backup_path_manifest,
        )
        if any(not isinstance(path, Path) for path in paths):
            raise SystemExit(2)
        request_path, credential_path, sql_path_manifest = cast("tuple[Path, Path, Path]", paths)
        request = load_live_recovery_request(request_path.read_bytes())
        if request.fingerprint != configuration.request_fingerprint:
            raise SystemExit(2)
        plan = build_live_recovery_plan(
            request,
            configuration,
            credential_path.read_bytes(),
            sql_backup_path_manifest=sql_path_manifest.read_bytes(),
        )
        _write_live_result(configuration.output_path, plan)
        print("LIVE_RECOVERY_PLAN_READY")  # noqa: T201
        return
    if mode is LocalRecoveryMode.EXECUTE_LIVE:
        paths = (
            arguments.live_plan,
            arguments.live_authority,
            arguments.live_credential_manifest,
            arguments.live_state_root,
        )
        if any(not isinstance(path, Path) for path in paths):
            raise SystemExit(2)
        plan_path, authority_path, credential_path, state_root = cast(
            "tuple[Path, Path, Path, Path]", paths
        )
        plan_bytes = plan_path.read_bytes()
        authority_bytes = authority_path.read_bytes()
        credential_bytes = credential_path.read_bytes()
        plan = _live_plan(plan_bytes)
        _live_authority(authority_bytes, plan)
        _live_credentials(credential_bytes, _opaque(plan["operation_id"]))
        if live_adapters is None:
            try:
                live_adapters = _compose_live_adapters(
                    plan,
                    credential_bytes,
                    arguments.sql_backup_path_manifest,
                    arguments.live_clean_room_root,
                )
            except (LiveRecoveryExecutionError, OSError, TypeError, ValueError) as error:
                blocker = str(error)
                if not blocker.startswith("LIVE_RECOVERY_"):
                    blocker = "LIVE_RECOVERY_ADAPTER_INPUT_NOT_READY"
                result = _issue_local_result(
                    configuration,
                    mode,
                    LocalRecoveryStatus.NOT_READY,
                    (blocker,),
                )
                write_local_recovery_result(result, configuration.output_path)
                print(result.status.value)  # noqa: T201
                raise SystemExit(2) from None
        live_result = execute_live_recovery(
            plan_bytes,
            authority_bytes,
            credential_bytes,
            state_root,
            live_adapters,
        )
        _write_live_result(configuration.output_path, live_result.canonical_bytes)
        print("LIVE_RECOVERY_PROVED")  # noqa: T201
        return
    result = run_local_recovery(
        configuration,
        mode=mode,
        execution_authorized=arguments.authorize_local_execution,
    )
    write_local_recovery_result(result, configuration.output_path)
    print(result.status.value)  # noqa: T201
    if result.status in {LocalRecoveryStatus.NOT_READY, LocalRecoveryStatus.WITHHELD}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
