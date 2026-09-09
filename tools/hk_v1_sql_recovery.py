"""Concrete no-shell command adapter for one authorized local SQL recovery drill.

The privileged helper is a separately installed host boundary.  This adapter never
places credential values in argv: it passes one already-bound systemd credential-file
reference and validates the helper's complete canonical read-back before issuing the
generic live-recovery receipt.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import NoReturn, Protocol, cast

from tools.hk_v1_recovery_proof import (
    LiveRecoveryExecutionError,
    LiveRecoveryStep,
    LiveRecoveryStepReceipt,
    SealedCredentialReference,
)

__all__ = [
    "FilesystemSealedCredentialVerifier",
    "SQLBackupPathBinding",
    "SQLRecoveryCommandResult",
    "SQLRecoveryCommandRunner",
    "SQLServerLiveRecoveryPort",
    "SealedCredentialVerifier",
    "SubprocessSQLRecoveryCommandRunner",
    "build_sql_backup_path_manifest",
]

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPAQUE = re.compile(r"^r_[0-9a-f]{32}$")
_TARGET_DATABASE = re.compile(r"^asklegal_recovery_sql_[0-9a-f]{24}$")
_MIGRATION = re.compile(r"^m_[0-9]{6}$")
_FAMILY = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
_BACKUP_ROOT = PurePosixPath("/var/opt/mssql/backup")
_MANIFEST_SCHEMA = "asklegal.hk-v1-sql-backup-paths/v1"
_READBACK_SCHEMA = "asklegal.hk-v1-sql-recovery-readback/v1"
_NOT_FOUND_SCHEMA = "asklegal.hk-v1-sql-recovery-not-found/v1"
_SQL_CREDENTIAL_ID = "SQL_SERVER_RECOVERY_ADMIN"
_MAX_COMMAND_OUTPUT = 2 * 1024 * 1024
_MAX_COMMAND_TIMEOUT_SECONDS = 3600
_MAX_CREDENTIAL_BYTES = 1024
_DEFAULT_HELPER = Path("/usr/local/libexec/asklegal-sql-recovery-admin")
_COMMAND_FLAGS = (
    "--plan-fingerprint",
    "--request-fingerprint",
    "--backup-evidence-id",
    "--backup-fingerprint",
    "--backup-path",
    "--target-database-name",
    "--target-database-identity",
    "--credential-file",
    "--credential-fingerprint",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "ascii"
    )


def _digest(value: object) -> str:
    return f"sha256:{sha256(_canonical(value)).hexdigest()}"


def _fail(code: str) -> NoReturn:
    raise LiveRecoveryExecutionError(code)


def _fingerprint(value: object, code: str) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        _fail(code)
    return value


def _opaque(value: object, code: str) -> str:
    if type(value) is not str or _OPAQUE.fullmatch(value) is None:
        _fail(code)
    return value


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value:
        _fail(code)
    return value


def _canonical_document(raw: bytes, code: str) -> dict[str, object]:
    def invalid() -> NoReturn:
        raise ValueError

    try:
        if type(raw) is not bytes or not raw.endswith(b"\n") or len(raw) > _MAX_COMMAND_OUTPUT:
            invalid()
        parsed: object = json.loads(raw)
        if type(parsed) is not dict:
            invalid()
        document = cast("dict[object, object]", parsed)
        if any(type(key) is not str for key in document):
            invalid()
        typed = cast("dict[str, object]", document)
        if _canonical(typed) + b"\n" != raw:
            invalid()
    except UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError:
        _fail(code)
    else:
        return typed


def _sealed_document(raw: bytes, schema: str, code: str) -> dict[str, object]:
    document = _canonical_document(raw, code)
    unsigned = dict(document)
    fingerprint = unsigned.pop("fingerprint", None)
    if document.get("schema") != schema or fingerprint != _digest(unsigned):
        _fail(code)
    return document


def _reference(value: object, code: str) -> dict[str, str]:
    if type(value) is not dict:
        _fail(code)
    document = cast("dict[object, object]", value)
    if set(document) != {"evidence_id", "fingerprint"}:
        _fail(code)
    return {
        "evidence_id": _opaque(document["evidence_id"], code),
        "fingerprint": _fingerprint(document["fingerprint"], code),
    }


@dataclass(frozen=True, slots=True)
class SQLBackupPathBinding:
    """One immutable evidence-reference to SQL-container-visible backup path."""

    evidence_id: str
    fingerprint: str
    sql_visible_path: str

    def __post_init__(self) -> None:
        """Restrict backups to exact regular-looking files in SQL's backup namespace."""
        _opaque(self.evidence_id, "LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
        _fingerprint(self.fingerprint, "LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
        path = PurePosixPath(self.sql_visible_path)
        if (
            not path.is_absolute()
            or ".." in path.parts
            or path.parent == path
            or path.suffix.casefold() != ".bak"
            or not path.is_relative_to(_BACKUP_ROOT)
            or self.sql_visible_path != path.as_posix()
            or not self.sql_visible_path.isascii()
            or not self.sql_visible_path.isprintable()
        ):
            _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")


def _binding_document(binding: SQLBackupPathBinding) -> dict[str, object]:
    if type(binding) is not SQLBackupPathBinding:
        _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
    return {
        "backup_reference": {
            "evidence_id": binding.evidence_id,
            "fingerprint": binding.fingerprint,
        },
        "sql_visible_path": binding.sql_visible_path,
    }


def build_sql_backup_path_manifest(bindings: tuple[SQLBackupPathBinding, ...]) -> bytes:
    """Create a canonical immutable mapping without reading any backup or credential."""
    if type(bindings) is not tuple or not bindings:
        _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
    documents = tuple(_binding_document(item) for item in bindings)
    keys = tuple(
        (
            cast("dict[str, str]", item["backup_reference"])["evidence_id"],
            cast("dict[str, str]", item["backup_reference"])["fingerprint"],
        )
        for item in documents
    )
    paths = tuple(cast("str", item["sql_visible_path"]) for item in documents)
    if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys) or len(set(paths)) != len(paths):
        _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
    body: dict[str, object] = {"bindings": list(documents), "schema": _MANIFEST_SCHEMA}
    return _canonical({**body, "fingerprint": _digest(body)}) + b"\n"


def _manifest_binding(raw: bytes, expected_reference: dict[str, str]) -> tuple[str, str]:
    document = _sealed_document(raw, _MANIFEST_SCHEMA, "LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
    if set(document) != {"bindings", "fingerprint", "schema"}:
        _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
    raw_bindings = document["bindings"]
    if type(raw_bindings) is not list or not raw_bindings:
        _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
    found: list[SQLBackupPathBinding] = []
    for raw_binding in cast("list[object]", raw_bindings):
        if type(raw_binding) is not dict:
            _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
        binding = cast("dict[str, object]", raw_binding)
        if set(binding) != {"backup_reference", "sql_visible_path"}:
            _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
        reference = _reference(binding["backup_reference"], "LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
        found.append(
            SQLBackupPathBinding(
                reference["evidence_id"],
                reference["fingerprint"],
                _text(binding["sql_visible_path"], "LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID"),
            )
        )
    rebuilt = build_sql_backup_path_manifest(tuple(found))
    if rebuilt != raw:
        _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_INVALID")
    matches = [
        item
        for item in found
        if item.evidence_id == expected_reference["evidence_id"]
        and item.fingerprint == expected_reference["fingerprint"]
    ]
    if len(matches) != 1:
        _fail("LIVE_SQL_BACKUP_REFERENCE_NOT_MAPPED")
    return matches[0].sql_visible_path, _digest(document)


@dataclass(frozen=True, slots=True)
class SQLRecoveryCommandResult:
    """Bounded subprocess result; stderr is retained only for disposal."""

    exit_code: int
    stdout: bytes
    stderr: bytes

    def __post_init__(self) -> None:
        """Reject coercion and unbounded results at the command boundary."""
        if (
            type(self.exit_code) is not int
            or type(self.stdout) is not bytes
            or type(self.stderr) is not bytes
            or len(self.stdout) > _MAX_COMMAND_OUTPUT
            or len(self.stderr) > _MAX_COMMAND_OUTPUT
        ):
            _fail("LIVE_SQL_RECOVERY_COMMAND_RESULT_INVALID")


class SQLRecoveryCommandRunner(Protocol):
    """Run one already-validated fixed argv without shell interpretation."""

    def run(self, argv: tuple[str, ...]) -> SQLRecoveryCommandResult:
        """Return bounded bytes and never interpolate a shell command."""
        ...


class SealedCredentialVerifier(Protocol):
    """Verify the exact referenced runtime file without returning its value."""

    def verify(self, reference: SealedCredentialReference) -> bool:
        """Return true only when the current sealed bytes match their binding."""
        ...


class FilesystemSealedCredentialVerifier:
    """Bounded no-follow verifier for a systemd runtime credential file."""

    def verify(self, reference: SealedCredentialReference) -> bool:
        """Hash exact current bytes, retaining neither bytes nor error details."""
        descriptor: int | None = None
        try:
            descriptor = os.open(
                reference.sealed_path,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            status = os.fstat(descriptor)
            if not 1 <= status.st_size <= _MAX_CREDENTIAL_BYTES:
                return False
            content = os.read(descriptor, _MAX_CREDENTIAL_BYTES + 1)
            return (
                len(content) == status.st_size
                and f"sha256:{sha256(content).hexdigest()}" == reference.fingerprint
            )
        except OSError:
            return False
        finally:
            if descriptor is not None:
                os.close(descriptor)


@dataclass(frozen=True, slots=True)
class SubprocessSQLRecoveryCommandRunner:
    """Concrete fixed-argv runner with a closed environment and bounded runtime."""

    timeout_seconds: int = 600

    def __post_init__(self) -> None:
        """Keep a recovery command finite."""
        if (
            type(self.timeout_seconds) is not int
            or not 1 <= self.timeout_seconds <= _MAX_COMMAND_TIMEOUT_SECONDS
        ):
            _fail("LIVE_SQL_RECOVERY_COMMAND_RUNNER_INVALID")

    def run(self, argv: tuple[str, ...]) -> SQLRecoveryCommandResult:
        """Execute the exact argv directly; never invoke a shell."""
        if (
            type(argv) is not tuple
            or len(argv) != 2 + (2 * len(_COMMAND_FLAGS))
            or any(type(item) is not str for item in argv)
            or argv[0] != str(_DEFAULT_HELPER)
            or argv[1] not in {"reconcile-readback", "restore-and-readback"}
            or argv[2::2] != _COMMAND_FLAGS
            or any(not item.isascii() or not item.isprintable() for item in argv)
        ):
            _fail("LIVE_SQL_RECOVERY_COMMAND_INVALID")
        try:
            completed = subprocess.run(  # noqa: S603
                argv,
                check=False,
                capture_output=True,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
                shell=False,
                timeout=self.timeout_seconds,
            )
        except OSError, subprocess.SubprocessError:
            _fail("LIVE_SQL_RECOVERY_COMMAND_FAILED")
        return SQLRecoveryCommandResult(
            completed.returncode,
            completed.stdout[:_MAX_COMMAND_OUTPUT],
            completed.stderr[:_MAX_COMMAND_OUTPUT],
        )


@dataclass(frozen=True, slots=True)
class _SQLPlan:
    operation_id: str
    plan_fingerprint: str
    request_fingerprint: str
    backup_reference: dict[str, str]
    target_database_name: str
    target_database_identity: str
    credential_reference_fingerprint: str
    manifest_fingerprint: str
    expected_migrations: list[object]
    expected_families: list[object]
    projection_rebuild_fingerprint: str
    external_ledger_digest_reference: dict[str, str]
    source_ledger_verification_receipt: dict[str, str]
    restored_ledger_verification_receipt: dict[str, str]


def _sql_plan(plan: object) -> _SQLPlan:  # noqa: C901
    code = "LIVE_SQL_RECOVERY_PLAN_INVALID"
    if type(plan) is not dict:
        _fail(code)
    root = cast("dict[str, object]", plan)
    sql_raw = root.get("sql")
    if type(sql_raw) is not dict:
        _fail(code)
    sql = cast("dict[str, object]", sql_raw)
    expected_keys = {
        "backup_path_manifest_fingerprint",
        "backup_reference",
        "credential_reference_fingerprint",
        "expected_families",
        "expected_migrations",
        "external_ledger_digest_reference",
        "projection_rebuild_fingerprint",
        "restored_ledger_verification_receipt",
        "source_ledger_verification_receipt",
        "target_database_identity",
        "target_database_name",
    }
    if set(sql) != expected_keys:
        _fail(code)
    target_name = _text(sql["target_database_name"], code)
    if _TARGET_DATABASE.fullmatch(target_name) is None:
        _fail(code)
    migrations = _migration_rows(sql["expected_migrations"], code)
    families = _family_rows(sql["expected_families"], code)
    operation_id = _opaque(root.get("operation_id"), code)
    request_fingerprint = _fingerprint(root.get("request_fingerprint"), code)
    token = sha256(f"{operation_id}|{request_fingerprint}".encode("ascii")).hexdigest()[:24]
    derived_name = f"asklegal_recovery_sql_{token}"
    derived_identity = f"r_{sha256(f'{token}|sql-database'.encode('ascii')).hexdigest()[:32]}"
    if type(migrations) is not list or not migrations or type(families) is not list or not families:
        _fail(code)
    steps = root.get("steps")
    if type(steps) is not list:
        _fail(code)
    expected_target = None
    for raw_step in cast("list[object]", steps):
        if type(raw_step) is dict:
            typed_step = cast("dict[str, object]", raw_step)
            if typed_step.get("step") == LiveRecoveryStep.SQL_RESTORE_READBACK:
                expected_target = typed_step.get("target_identity")
    target_identity = _opaque(sql["target_database_identity"], code)
    if (
        expected_target != target_identity
        or target_name != derived_name
        or target_identity != derived_identity
    ):
        _fail(code)
    return _SQLPlan(
        operation_id,
        _fingerprint(root.get("fingerprint"), code),
        request_fingerprint,
        _reference(sql["backup_reference"], code),
        target_name,
        target_identity,
        _fingerprint(sql["credential_reference_fingerprint"], code),
        _fingerprint(sql["backup_path_manifest_fingerprint"], code),
        migrations,
        families,
        _fingerprint(sql["projection_rebuild_fingerprint"], code),
        _reference(sql["external_ledger_digest_reference"], code),
        _reference(sql["source_ledger_verification_receipt"], code),
        _reference(sql["restored_ledger_verification_receipt"], code),
    )


def _migration_rows(value: object, code: str) -> list[object]:
    if type(value) is not list or not value:
        _fail(code)
    rows: list[dict[str, object]] = []
    for raw in cast("list[object]", value):
        if type(raw) is not dict:
            _fail(code)
        row = cast("dict[str, object]", raw)
        if set(row) != {"migration_id", "package_fingerprint"}:
            _fail(code)
        migration_id = _text(row["migration_id"], code)
        if _MIGRATION.fullmatch(migration_id) is None:
            _fail(code)
        rows.append(
            {
                "migration_id": migration_id,
                "package_fingerprint": _fingerprint(row["package_fingerprint"], code),
            }
        )
    ids = tuple(cast("str", row["migration_id"]) for row in rows)
    expected = tuple(f"m_{index:06d}" for index in range(1, len(rows) + 1))
    if ids != expected:
        _fail(code)
    return cast("list[object]", rows)


def _family_rows(value: object, code: str) -> list[object]:
    if type(value) is not list or not value:
        _fail(code)
    rows: list[dict[str, object]] = []
    for raw in cast("list[object]", value):
        if type(raw) is not dict:
            _fail(code)
        row = cast("dict[str, object]", raw)
        if set(row) != {"content_fingerprint", "family", "row_count"}:
            _fail(code)
        family = _text(row["family"], code)
        count = row["row_count"]
        if _FAMILY.fullmatch(family) is None or type(count) is not int or count < 0:
            _fail(code)
        rows.append(
            {
                "content_fingerprint": _fingerprint(row["content_fingerprint"], code),
                "family": family,
                "row_count": count,
            }
        )
    names = tuple(cast("str", row["family"]) for row in rows)
    if names != tuple(sorted(names)) or len(set(names)) != len(names):
        _fail(code)
    return cast("list[object]", rows)


def _credential(
    credentials: tuple[SealedCredentialReference, ...], expected_fingerprint: str
) -> SealedCredentialReference:
    if type(credentials) is not tuple:
        _fail("LIVE_SQL_RECOVERY_CREDENTIAL_INVALID")
    matches = [item for item in credentials if item.credential_id == _SQL_CREDENTIAL_ID]
    if len(matches) != 1:
        _fail("LIVE_SQL_RECOVERY_CREDENTIAL_INVALID")
    credential = matches[0]
    sealed_path = PurePosixPath(credential.sealed_path)
    if (
        credential.sealed_path != sealed_path.as_posix()
        or not credential.sealed_path.isascii()
        or not credential.sealed_path.isprintable()
    ):
        _fail("LIVE_SQL_RECOVERY_CREDENTIAL_INVALID")
    if (
        _digest(
            {
                "credential_id": credential.credential_id,
                "fingerprint": credential.fingerprint,
                "sealed_path": credential.sealed_path,
            }
        )
        != expected_fingerprint
    ):
        _fail("LIVE_SQL_RECOVERY_CREDENTIAL_DRIFT")
    return credential


def _command(
    helper: Path,
    mode: str,
    sql: _SQLPlan,
    backup_path: str,
    credential: SealedCredentialReference,
) -> tuple[str, ...]:
    return (
        str(helper),
        mode,
        "--plan-fingerprint",
        sql.plan_fingerprint,
        "--request-fingerprint",
        sql.request_fingerprint,
        "--backup-evidence-id",
        sql.backup_reference["evidence_id"],
        "--backup-fingerprint",
        sql.backup_reference["fingerprint"],
        "--backup-path",
        backup_path,
        "--target-database-name",
        sql.target_database_name,
        "--target-database-identity",
        sql.target_database_identity,
        "--credential-file",
        credential.sealed_path,
        "--credential-fingerprint",
        credential.fingerprint,
    )


def _not_found(raw: bytes, sql: _SQLPlan) -> bool:
    document = _sealed_document(raw, _NOT_FOUND_SCHEMA, "LIVE_SQL_RECOVERY_READBACK_INVALID")
    return document == {
        "fingerprint": document["fingerprint"],
        "plan_fingerprint": sql.plan_fingerprint,
        "schema": _NOT_FOUND_SCHEMA,
        "target_database_identity": sql.target_database_identity,
        "target_database_name": sql.target_database_name,
    }


def _receipt(raw: bytes, sql: _SQLPlan, backup_path: str) -> LiveRecoveryStepReceipt:
    code = "LIVE_SQL_RECOVERY_READBACK_INVALID"
    document = _sealed_document(raw, _READBACK_SCHEMA, code)
    expected: dict[str, object] = {
        "backup_reference": sql.backup_reference,
        "backup_path_manifest_fingerprint": sql.manifest_fingerprint,
        "database_state": "ONLINE",
        "dbcc_checkdb": "CLEAN",
        "external_ledger_digest_reference": sql.external_ledger_digest_reference,
        "ledger_verification": "VERIFIED",
        "migration_prefix": sql.expected_migrations,
        "plan_fingerprint": sql.plan_fingerprint,
        "projection_rebuild": "VERIFIED",
        "projection_rebuild_fingerprint": sql.projection_rebuild_fingerprint,
        "register_families": sql.expected_families,
        "request_fingerprint": sql.request_fingerprint,
        "restore_verification_fingerprint": document.get("restore_verification_fingerprint"),
        "restored_ledger_verification_receipt": sql.restored_ledger_verification_receipt,
        "schema": _READBACK_SCHEMA,
        "sql_visible_backup_path": backup_path,
        "source_database_identity": document.get("source_database_identity"),
        "source_ledger_verification_receipt": sql.source_ledger_verification_receipt,
        "target_database_identity": sql.target_database_identity,
        "target_database_name": sql.target_database_name,
    }
    comparison = dict(document)
    comparison.pop("fingerprint", None)
    source_identity = _opaque(document.get("source_database_identity"), code)
    verification = _fingerprint(document.get("restore_verification_fingerprint"), code)
    if source_identity == sql.target_database_identity or comparison != expected:
        _fail(code)
    return LiveRecoveryStepReceipt(
        LiveRecoveryStep.SQL_RESTORE_READBACK,
        sql.plan_fingerprint,
        sql.target_database_identity,
        verification,
        verification,
    )


class SQLServerLiveRecoveryPort:
    """Exact SQL Server restore/read-back adapter for the generic live recovery executor."""

    def __init__(
        self,
        runner: SQLRecoveryCommandRunner,
        backup_path_manifest: bytes,
        *,
        helper_path: Path = _DEFAULT_HELPER,
        credential_verifier: SealedCredentialVerifier | None = None,
    ) -> None:
        """Bind one runner, immutable mapping, and absolute privileged helper path."""
        if helper_path != _DEFAULT_HELPER:
            _fail("LIVE_SQL_RECOVERY_HELPER_INVALID")
        self._runner = runner
        self._manifest = backup_path_manifest
        self._helper = helper_path
        self._credential_verifier = credential_verifier or FilesystemSealedCredentialVerifier()

    def reconcile(
        self,
        step: LiveRecoveryStep,
        plan: object,
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt | None:
        """Reread only; target absence is the sole non-error empty result."""
        sql, path, credential = self._inputs(step, plan, credentials)
        result = self._runner.run(
            _command(self._helper, "reconcile-readback", sql, path, credential)
        )
        if result.exit_code == 3 and _not_found(result.stdout, sql):  # noqa: PLR2004
            return None
        if result.exit_code != 0:
            _fail("LIVE_SQL_RECOVERY_COMMAND_FAILED")
        return _receipt(result.stdout, sql, path)

    def execute(
        self,
        step: LiveRecoveryStep,
        plan: object,
        credentials: tuple[SealedCredentialReference, ...],
    ) -> LiveRecoveryStepReceipt:
        """Restore-or-match the exact target and require complete semantic read-back."""
        sql, path, credential = self._inputs(step, plan, credentials)
        result = self._runner.run(
            _command(self._helper, "restore-and-readback", sql, path, credential)
        )
        if result.exit_code != 0:
            _fail("LIVE_SQL_RECOVERY_COMMAND_FAILED")
        return _receipt(result.stdout, sql, path)

    def _inputs(
        self,
        step: LiveRecoveryStep,
        plan: object,
        credentials: tuple[SealedCredentialReference, ...],
    ) -> tuple[_SQLPlan, str, SealedCredentialReference]:
        if step is not LiveRecoveryStep.SQL_RESTORE_READBACK:
            _fail("LIVE_SQL_RECOVERY_STEP_INVALID")
        sql = _sql_plan(plan)
        path, manifest_fingerprint = _manifest_binding(self._manifest, sql.backup_reference)
        if manifest_fingerprint != sql.manifest_fingerprint:
            _fail("LIVE_SQL_BACKUP_PATH_MANIFEST_DRIFT")
        credential = _credential(credentials, sql.credential_reference_fingerprint)
        if not self._credential_verifier.verify(credential):
            _fail("LIVE_SQL_RECOVERY_CREDENTIAL_DRIFT")
        return sql, path, credential
