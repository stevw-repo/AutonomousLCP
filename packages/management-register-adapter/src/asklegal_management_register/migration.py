"""Closed, forward-only, fingerprinted SQL Server migration runner."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from asklegal_contracts.canonical import canonicalize
from asklegal_contracts.strict_json import parse_json_bytes

from asklegal_management_register.dbapi import ConnectionFactory

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_MAX_MANIFEST_BYTES = 64 * 1024
_ALLOWED_OPERATIONS = frozenset({"expand", "contract", "projection_rebuild", "corrective"})


@dataclass(frozen=True, slots=True)
class Batch:
    """One exact UTF-8/LF T-SQL batch."""

    path: str
    byte_length: int
    fingerprint: bytes


@dataclass(frozen=True, slots=True)
class MigrationPackage:
    """One closed forward-only migration package."""

    migration_id: str
    operation: str
    compatible_contract_range: str
    batches: tuple[Batch, ...]
    package_fingerprint: bytes
    directory: Path


class MigrationViolation(RuntimeError):
    """A migration package or applied prefix failed closed validation."""


def load_package(directory: Path) -> MigrationPackage:
    """Validate a migration manifest and every exact declared batch byte."""
    raw_manifest = (directory / "manifest.json").read_bytes()
    parsed = parse_json_bytes(raw_manifest, max_bytes=_MAX_MANIFEST_BYTES)
    manifest = _mapping(parsed, "manifest")
    if set(manifest) != {
        "schema_version",
        "migration_id",
        "operation",
        "compatible_contract_range",
        "batches",
        "package_fingerprint",
    }:
        raise MigrationViolation("manifest keys are not closed")
    if _integer(manifest["schema_version"], "schema_version") != 1:
        raise MigrationViolation("unsupported manifest schema")

    migration_id = _text(manifest["migration_id"], "migration_id")
    if len(migration_id) != 6 or not migration_id.isascii() or not migration_id.isdigit():
        raise MigrationViolation("migration_id must be six ASCII digits")
    if directory.name.split("_", 1)[0] != migration_id:
        raise MigrationViolation("directory and migration_id differ")
    operation = _text(manifest["operation"], "operation")
    if operation not in _ALLOWED_OPERATIONS:
        raise MigrationViolation("unknown migration operation")

    raw_batches = _sequence(manifest["batches"], "batches")
    if not raw_batches:
        raise MigrationViolation("migration must declare at least one batch")
    batches = tuple(_batch(item) for item in raw_batches)
    declared_names = [batch.path for batch in batches]
    if declared_names != sorted(declared_names) or len(set(declared_names)) != len(batches):
        raise MigrationViolation("batch list is not one unique ordered prefix")
    actual_names = sorted(path.name for path in directory.iterdir() if path.is_file())
    if actual_names != sorted(["manifest.json", *declared_names]):
        raise MigrationViolation("migration directory contains undeclared files")

    for batch in batches:
        raw = (directory / batch.path).read_bytes()
        if len(raw) != batch.byte_length or sha256(raw).digest() != batch.fingerprint:
            raise MigrationViolation(f"batch bytes differ: {batch.path}")
        if b"\r" in raw or b"\x00" in raw:
            raise MigrationViolation(f"batch is not UTF-8/LF text: {batch.path}")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise MigrationViolation(f"batch is not UTF-8: {batch.path}") from error
        if any(line.strip().upper() == "GO" for line in text.splitlines()):
            raise MigrationViolation(f"GO is forbidden: {batch.path}")

    expected_package_fingerprint = _fingerprint(manifest["package_fingerprint"])
    fingerprint_input = dict(manifest)
    del fingerprint_input["package_fingerprint"]
    actual_package_fingerprint = sha256(canonicalize(fingerprint_input)).digest()
    if actual_package_fingerprint != expected_package_fingerprint:
        raise MigrationViolation("package fingerprint differs")

    return MigrationPackage(
        migration_id=migration_id,
        operation=operation,
        compatible_contract_range=_text(
            manifest["compatible_contract_range"], "compatible_contract_range"
        ),
        batches=batches,
        package_fingerprint=expected_package_fingerprint,
        directory=directory,
    )


def apply_packages(
    connection_factory: ConnectionFactory,
    package_directories: tuple[Path, ...],
    *,
    runner_build: str,
) -> None:
    """Apply one explicitly supplied migration prefix under a finite transaction lock."""
    packages = tuple(load_package(path) for path in package_directories)
    ids = tuple(package.migration_id for package in packages)
    if ids != tuple(sorted(ids)) or len(set(ids)) != len(ids):
        raise MigrationViolation("migration packages are not one ordered unique prefix")

    connection = connection_factory()
    cursor = connection.cursor()
    try:
        cursor.execute("SET XACT_ABORT ON;")
        cursor.execute(
            """
            DECLARE @result int;
            EXEC @result = sys.sp_getapplock
                @Resource = 'asklegal:management-register:migrations',
                @LockMode = 'Exclusive',
                @LockOwner = 'Transaction',
                @LockTimeout = 10000;
            IF @result < 0 THROW 51100, 'ASKLEGAL_MIGRATION_LOCK_FAILED', 1;
            """
        )
        for package in packages:
            cursor.execute(
                """
                IF OBJECT_ID('migration.applied_fact', 'U') IS NOT NULL
                    SELECT package_fingerprint
                    FROM migration.applied_fact
                    WHERE migration_id = ?;
                ELSE
                    SELECT CAST(NULL AS binary(32)) WHERE 1 = 0;
                """,
                (package.migration_id,),
            )
            applied = cursor.fetchone()
            if applied is not None:
                recorded = applied[0]
                if not isinstance(recorded, bytes) or recorded != package.package_fingerprint:
                    raise MigrationViolation(
                        f"applied migration fingerprint differs: {package.migration_id}"
                    )
                continue
            for batch in package.batches:
                cursor.execute((package.directory / batch.path).read_text(encoding="utf-8"))
            cursor.execute(
                """
                INSERT migration.applied_fact
                    (migration_id, package_fingerprint, runner_build,
                     database_name, executor_name, applied_at)
                VALUES (?, ?, ?, DB_NAME(), USER_NAME(), SYSUTCDATETIME());
                """,
                (package.migration_id, package.package_fingerprint, runner_build),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def _batch(value: JsonValue) -> Batch:
    mapping = _mapping(value, "batch")
    if set(mapping) != {"path", "byte_length", "sha256"}:
        raise MigrationViolation("batch keys are not closed")
    path = _text(mapping["path"], "batch.path")
    if Path(path).name != path or not path.endswith(".sql"):
        raise MigrationViolation("batch path must be one local .sql filename")
    return Batch(
        path=path,
        byte_length=_integer(mapping["byte_length"], "batch.byte_length"),
        fingerprint=_fingerprint(mapping["sha256"]),
    )


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise MigrationViolation(f"{label} must be an object")
    return value


def _sequence(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise MigrationViolation(f"{label} must be an array")
    return value


def _text(value: JsonValue, label: str) -> str:
    if not isinstance(value, str):
        raise MigrationViolation(f"{label} must be text")
    return value


def _integer(value: JsonValue, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MigrationViolation(f"{label} must be a non-negative integer")
    return value


def _fingerprint(value: JsonValue) -> bytes:
    text = _text(value, "fingerprint")
    if len(text) != 64:
        raise MigrationViolation("fingerprint must contain 64 hexadecimal characters")
    try:
        return bytes.fromhex(text)
    except ValueError as error:
        raise MigrationViolation("fingerprint is not hexadecimal") from error
