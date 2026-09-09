"""Plan and execute one exact local archive-before-cleanup operation."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Never, cast

_PLAN_SCHEMA = "asklegal.hk-v1-archive-cleanup-plan/v1"
_AUTHORITY_SCHEMA = "asklegal.hk-v1-archive-cleanup-authority/v1"
_STATE_SCHEMA = "asklegal.hk-v1-archive-cleanup-state/v1"
_PLAN_ID_PREFIX = "acp_"
_AUTHORITY_ID_PREFIX = "auth_"
_DIGEST_PREFIX = "sha256:"
_MAX_DOCUMENT_BYTES = 5_000_000
_MAX_MODE = 0o7777
_PROTECTION_NAMES = (
    "approval_state",
    "current_baseline",
    "fixtures",
    "latest_journals",
    "promotion_evidence",
)


def _fail(label: str) -> Never:
    raise ValueError(label)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _digest(content: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(content).hexdigest()


def _identifier(value: object, prefix: str, label: str) -> str:
    if (
        type(value) is not str
        or not value.startswith(prefix)
        or len(value) != len(prefix) + 48
        or any(character not in "0123456789abcdef" for character in value[len(prefix) :])
    ):
        _fail(label)
    return value


def _fingerprint(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value.startswith(_DIGEST_PREFIX)
        or len(value) != len(_DIGEST_PREFIX) + 64
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        _fail(label)
    return value


def _safe_path(path: Path, label: str) -> Path:
    if not path.is_absolute() or path == Path(path.anchor) or path != path.resolve(strict=False):
        _fail(label)
    current = path
    while current != Path(current.anchor):
        if current.is_symlink():
            _fail(label)
        current = current.parent
    return path


def _overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


@dataclass(frozen=True, slots=True)
class ArchiveProtectionSet:
    """Explicit paths that can never become cleanup candidates."""

    latest_journals: tuple[Path, ...]
    current_baseline: tuple[Path, ...]
    fixtures: tuple[Path, ...]
    approval_state: tuple[Path, ...]
    promotion_evidence: tuple[Path, ...]

    def __post_init__(self) -> None:
        """Require every protected category and reject aliases or overlaps."""
        all_paths: list[Path] = []
        for paths in (
            self.latest_journals,
            self.current_baseline,
            self.fixtures,
            self.approval_state,
            self.promotion_evidence,
        ):
            if type(paths) is not tuple or not paths:
                _fail("archive protection set")
            all_paths.extend(_safe_path(path, "archive protection path") for path in paths)
        if len(set(all_paths)) != len(all_paths):
            _fail("duplicate archive protection path")

    def document(self) -> dict[str, object]:
        """Return the exact category-preserving value-free projection."""
        return {
            "approval_state": [str(path) for path in self.approval_state],
            "current_baseline": [str(path) for path in self.current_baseline],
            "fixtures": [str(path) for path in self.fixtures],
            "latest_journals": [str(path) for path in self.latest_journals],
            "promotion_evidence": [str(path) for path in self.promotion_evidence],
        }

    @property
    def paths(self) -> tuple[Path, ...]:
        """Flatten the closed protected inventory."""
        return tuple(
            path
            for paths in (
                self.latest_journals,
                self.current_baseline,
                self.fixtures,
                self.approval_state,
                self.promotion_evidence,
            )
            for path in paths
        )


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    """Exact recursive metadata for one regular file or directory."""

    relative_path: str
    kind: str
    byte_length: int
    fingerprint: str
    mode: int
    mtime_ns: int

    def __post_init__(self) -> None:
        """Reject traversal, unsupported kinds, and malformed metadata."""
        relative = Path(self.relative_path)
        if (
            type(self.relative_path) is not str
            or not self.relative_path
            or relative.is_absolute()
            or ".." in relative.parts
            or self.kind not in {"DIRECTORY", "FILE"}
            or type(self.byte_length) is not int
            or self.byte_length < 0
            or type(self.mode) is not int
            or not 0 <= self.mode <= _MAX_MODE
            or type(self.mtime_ns) is not int
            or self.mtime_ns < 0
        ):
            _fail("archive member")
        _fingerprint(self.fingerprint, "archive member fingerprint")

    def document(self) -> dict[str, object]:
        """Return canonical metadata without any source bytes."""
        return {
            "byte_length": self.byte_length,
            "fingerprint": self.fingerprint,
            "kind": self.kind,
            "mode": self.mode,
            "mtime_ns": self.mtime_ns,
            "relative_path": self.relative_path,
        }


@dataclass(frozen=True, slots=True)
class ArchiveCandidate:
    """One explicit source root and its complete recursive inventory."""

    source_path: Path
    archive_name: str
    byte_length: int
    fingerprint: str
    mode: int
    mtime_ns: int
    members: tuple[ArchiveMember, ...]

    def __post_init__(self) -> None:
        """Reject implicit paths, ambiguous names, and inventory drift."""
        _safe_path(self.source_path, "archive source path")
        if (
            type(self.archive_name) is not str
            or not self.archive_name
            or "/" in self.archive_name
            or self.archive_name in {".", ".."}
            or type(self.members) is not tuple
            or not self.members
            or type(self.byte_length) is not int
            or self.byte_length < 0
            or type(self.mode) is not int
            or type(self.mtime_ns) is not int
        ):
            _fail("archive candidate")
        _fingerprint(self.fingerprint, "archive candidate fingerprint")
        relative_paths = tuple(member.relative_path for member in self.members)
        root = self.members[0]
        if (
            relative_paths[0] != "."
            or relative_paths != tuple(sorted(relative_paths, key=lambda item: (item != ".", item)))
            or len(set(relative_paths)) != len(relative_paths)
            or self.byte_length
            != sum(member.byte_length for member in self.members if member.kind == "FILE")
            or self.fingerprint
            != _digest(_canonical([member.document() for member in self.members]))
            or self.mode != root.mode
            or self.mtime_ns != root.mtime_ns
        ):
            _fail("archive candidate inventory")

    def document(self) -> dict[str, object]:
        """Return one exact plan member."""
        return {
            "archive_name": self.archive_name,
            "byte_length": self.byte_length,
            "fingerprint": self.fingerprint,
            "members": [member.document() for member in self.members],
            "mode": self.mode,
            "mtime_ns": self.mtime_ns,
            "source_path": str(self.source_path),
        }


@dataclass(frozen=True, slots=True)
class ArchiveCleanupPlan:
    """Frozen exact inventory, destination, and protected-set authority subject."""

    plan_id: str
    plan_fingerprint: str
    destination: Path
    protections: ArchiveProtectionSet
    candidates: tuple[ArchiveCandidate, ...]

    def __post_init__(self) -> None:
        """Reject a forged identity, overlapping sources, or protected deletion."""
        _identifier(self.plan_id, _PLAN_ID_PREFIX, "archive plan ID")
        _fingerprint(self.plan_fingerprint, "archive plan fingerprint")
        _safe_path(self.destination, "archive destination")
        if type(self.candidates) is not tuple or not self.candidates:
            _fail("archive candidates")
        sources = tuple(candidate.source_path for candidate in self.candidates)
        if len(set(sources)) != len(sources):
            _fail("duplicate archive source")
        if any(
            _overlaps(first, second)
            for index, first in enumerate(sources)
            for second in sources[index + 1 :]
        ):
            _fail("overlapping archive sources")
        if any(_overlaps(source, self.destination) for source in sources):
            _fail("archive destination must be distinct")
        if any(
            _overlaps(source, protected)
            for source in sources
            for protected in self.protections.paths
        ):
            _fail("protected archive source")
        expected = _freeze_plan(self.destination, self.protections, self.candidates)
        if self.plan_id != expected[0] or self.plan_fingerprint != expected[1]:
            _fail("archive plan fingerprint")

    def document(self) -> dict[str, object]:
        """Render one canonical reviewer-facing plan."""
        return {
            "candidates": [candidate.document() for candidate in self.candidates],
            "destination": str(self.destination),
            "plan_fingerprint": self.plan_fingerprint,
            "plan_id": self.plan_id,
            "protections": self.protections.document(),
            "schema_id": _PLAN_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class ArchiveCleanupReport:
    """Value-free terminal copy/readback/deletion result."""

    plan_id: str
    plan_fingerprint: str
    state: str
    copied: tuple[str, ...]
    deleted: tuple[str, ...]
    complete: bool

    def document(self) -> dict[str, object]:
        """Return the exact terminal report."""
        return {
            "complete": self.complete,
            "copied": list(self.copied),
            "deleted": list(self.deleted),
            "plan_fingerprint": self.plan_fingerprint,
            "plan_id": self.plan_id,
            "schema_id": "asklegal.hk-v1-archive-cleanup-report/v1",
            "state": self.state,
        }


def _member(path: Path, relative: str) -> ArchiveMember:
    metadata = path.stat(follow_symlinks=False)
    kind = "DIRECTORY" if path.is_dir() else "FILE"
    content = b"" if kind == "DIRECTORY" else path.read_bytes()
    return ArchiveMember(
        relative,
        kind,
        len(content),
        _digest(content),
        stat.S_IMODE(metadata.st_mode),
        metadata.st_mtime_ns,
    )


def _descendants(root: Path) -> tuple[Path, ...]:
    """Walk one explicit root without a glob or symlink traversal."""
    found: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.is_symlink():
            _fail("archive source contains unsupported member")
        _safe_path(child, "archive source contains unsupported member")
        if not (child.is_file() or child.is_dir()):
            _fail("archive source contains unsupported member")
        found.append(child)
        if child.is_dir():
            found.extend(_descendants(child))
    return tuple(found)


def inventory_candidate(path: Path, archive_name: str) -> ArchiveCandidate:
    """Inventory one explicit path recursively without following a symlink."""
    source = _safe_path(path, "archive source path")
    if source.is_symlink() or not source.exists() or not (source.is_file() or source.is_dir()):
        _fail("archive source path")
    members: list[ArchiveMember] = [_member(source, ".")]
    if source.is_dir():
        members.extend(
            _member(child, child.relative_to(source).as_posix()) for child in _descendants(source)
        )
        members[1:] = sorted(members[1:], key=lambda item: item.relative_path)
    projection = [member.document() for member in members]
    root = members[0]
    return ArchiveCandidate(
        source,
        archive_name,
        sum(member.byte_length for member in members if member.kind == "FILE"),
        _digest(_canonical(projection)),
        root.mode,
        root.mtime_ns,
        tuple(members),
    )


def _freeze_plan(
    destination: Path,
    protections: ArchiveProtectionSet,
    candidates: tuple[ArchiveCandidate, ...],
) -> tuple[str, str]:
    body = {
        "candidates": [candidate.document() for candidate in candidates],
        "destination": str(destination),
        "protections": protections.document(),
    }
    fingerprint = _digest(_canonical(body))
    return _PLAN_ID_PREFIX + hashlib.sha256(fingerprint.encode()).hexdigest()[:48], fingerprint


def build_archive_cleanup_plan(
    candidate_paths: tuple[Path, ...],
    destination: Path,
    protections: ArchiveProtectionSet,
) -> ArchiveCleanupPlan:
    """Freeze metadata for only the explicitly supplied candidate roots."""
    if type(candidate_paths) is not tuple or not candidate_paths:
        _fail("archive candidate paths")
    target = _safe_path(destination, "archive destination")
    if target.is_symlink() or not target.is_dir():
        _fail("archive destination")
    candidates = tuple(
        inventory_candidate(path, f"{index:04d}-{path.name}")
        for index, path in enumerate(candidate_paths, start=1)
    )
    plan_id, fingerprint = _freeze_plan(target, protections, candidates)
    return ArchiveCleanupPlan(plan_id, fingerprint, target, protections, candidates)


def archive_cleanup_plan_bytes(plan: ArchiveCleanupPlan) -> bytes:
    """Serialize a canonical plan that can be retained for restart replay."""
    return _canonical(plan.document())


def archive_cleanup_authority_bytes(plan: ArchiveCleanupPlan, authority_id: str) -> bytes:
    """Freeze exact authority for this plan and no other cleanup."""
    _identifier(authority_id, _AUTHORITY_ID_PREFIX, "archive authority ID")
    return _canonical(
        {
            "authority_id": authority_id,
            "authorized": True,
            "destination": str(plan.destination),
            "plan_fingerprint": plan.plan_fingerprint,
            "plan_id": plan.plan_id,
            "schema_id": _AUTHORITY_SCHEMA,
        }
    )


def _path_tuple(value: object, label: str) -> tuple[Path, ...]:
    if type(value) is not list or not value:
        _fail(label)
    raw = cast("list[object]", value)
    if any(type(item) is not str for item in raw):
        _fail(label)
    return tuple(_safe_path(Path(cast("str", item)), label) for item in raw)


def _load_member(value: object) -> ArchiveMember:
    if type(value) is not dict:
        _fail("archive plan member")
    item = cast("dict[str, object]", value)
    expected = {"byte_length", "fingerprint", "kind", "mode", "mtime_ns", "relative_path"}
    if set(item) != expected:
        _fail("archive plan member")
    return ArchiveMember(
        cast("str", item["relative_path"]),
        cast("str", item["kind"]),
        cast("int", item["byte_length"]),
        cast("str", item["fingerprint"]),
        cast("int", item["mode"]),
        cast("int", item["mtime_ns"]),
    )


def _load_candidate(value: object) -> ArchiveCandidate:
    if type(value) is not dict:
        _fail("archive plan candidate")
    item = cast("dict[str, object]", value)
    expected = {
        "archive_name",
        "byte_length",
        "fingerprint",
        "members",
        "mode",
        "mtime_ns",
        "source_path",
    }
    raw_members = item.get("members")
    if set(item) != expected or type(raw_members) is not list:
        _fail("archive plan candidate")
    return ArchiveCandidate(
        _safe_path(Path(cast("str", item["source_path"])), "archive source path"),
        cast("str", item["archive_name"]),
        cast("int", item["byte_length"]),
        cast("str", item["fingerprint"]),
        cast("int", item["mode"]),
        cast("int", item["mtime_ns"]),
        tuple(_load_member(member) for member in cast("list[object]", raw_members)),
    )


def load_archive_cleanup_plan(path: Path) -> ArchiveCleanupPlan:
    """Load one canonical retained plan without requiring source paths to remain."""
    _safe_path(path, "archive plan")
    if path.is_symlink() or not path.is_file():
        _fail("archive plan")
    content = path.read_bytes()
    if len(content) > _MAX_DOCUMENT_BYTES:
        _fail("archive plan")
    value: object = json.loads(content)
    if type(value) is not dict:
        _fail("archive plan")
    document = cast("dict[str, object]", value)
    if _canonical(document) != content or set(document) != {
        "candidates",
        "destination",
        "plan_fingerprint",
        "plan_id",
        "protections",
        "schema_id",
    }:
        _fail("archive plan")
    raw_protections = document.get("protections")
    raw_candidates = document.get("candidates")
    if (
        document.get("schema_id") != _PLAN_SCHEMA
        or type(raw_protections) is not dict
        or type(raw_candidates) is not list
    ):
        _fail("archive plan")
    protected = cast("dict[str, object]", raw_protections)
    if set(protected) != set(_PROTECTION_NAMES):
        _fail("archive protections")
    protections = ArchiveProtectionSet(
        _path_tuple(protected["latest_journals"], "latest journals"),
        _path_tuple(protected["current_baseline"], "current baseline"),
        _path_tuple(protected["fixtures"], "fixtures"),
        _path_tuple(protected["approval_state"], "approval state"),
        _path_tuple(protected["promotion_evidence"], "promotion evidence"),
    )
    return ArchiveCleanupPlan(
        _identifier(document.get("plan_id"), _PLAN_ID_PREFIX, "archive plan ID"),
        _fingerprint(document.get("plan_fingerprint"), "archive plan fingerprint"),
        _safe_path(Path(cast("str", document["destination"])), "archive destination"),
        protections,
        tuple(_load_candidate(item) for item in cast("list[object]", raw_candidates)),
    )


def _load_authority(path: Path, plan: ArchiveCleanupPlan) -> None:
    _safe_path(path, "archive authority")
    if path.is_symlink() or not path.is_file():
        _fail("archive authority")
    content = path.read_bytes()
    if len(content) > _MAX_DOCUMENT_BYTES:
        _fail("archive authority")
    value: object = json.loads(content)
    expected = {
        "authorized": True,
        "destination": str(plan.destination),
        "plan_fingerprint": plan.plan_fingerprint,
        "plan_id": plan.plan_id,
        "schema_id": _AUTHORITY_SCHEMA,
    }
    if type(value) is not dict:
        _fail("archive authority")
    document = cast("dict[str, object]", value)
    if (
        _canonical(document) != content
        or set(document) != set(expected) | {"authority_id"}
        or any(document.get(key) != item for key, item in expected.items())
    ):
        _fail("archive authority")
    _identifier(document.get("authority_id"), _AUTHORITY_ID_PREFIX, "archive authority ID")


def _copy_candidate(candidate: ArchiveCandidate, target: Path) -> None:
    temporary = target.with_name(f".{target.name}.tmp")
    if target.is_symlink() or temporary.is_symlink():
        _fail("archive staging path")
    if temporary.exists() or temporary.is_symlink():
        if temporary.is_file():
            temporary.unlink()
        else:
            shutil.rmtree(temporary)
    if candidate.source_path.is_symlink() or not candidate.source_path.exists():
        _fail("archive source unavailable")
    if inventory_candidate(candidate.source_path, candidate.archive_name) != candidate:
        _fail("archive source drift")
    if candidate.source_path.is_file():
        shutil.copy2(candidate.source_path, temporary)
    else:
        shutil.copytree(candidate.source_path, temporary, symlinks=False)
    temporary.replace(target)


def _matches_inventory(candidate: ArchiveCandidate, path: Path) -> bool:
    try:
        observed = inventory_candidate(path, candidate.archive_name)
    except OSError, ValueError:
        return False
    return (
        observed.byte_length == candidate.byte_length
        and observed.fingerprint == candidate.fingerprint
        and observed.mode == candidate.mode
        and observed.mtime_ns == candidate.mtime_ns
        and observed.members == candidate.members
    )


def _state_path(plan: ArchiveCleanupPlan) -> Path:
    return plan.destination / plan.plan_id / "archive-cleanup-state.json"


def _write_state(
    plan: ArchiveCleanupPlan, copied: tuple[str, ...], deleted: tuple[str, ...]
) -> None:
    path = _state_path(plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "copied": list(copied),
        "deleted": list(deleted),
        "plan_fingerprint": plan.plan_fingerprint,
        "plan_id": plan.plan_id,
        "schema_id": _STATE_SCHEMA,
    }
    temporary = path.with_suffix(".tmp")
    if temporary.is_symlink():
        _fail("archive state")
    temporary.write_bytes(_canonical(document))
    temporary.replace(path)


def _read_state(plan: ArchiveCleanupPlan) -> tuple[tuple[str, ...], tuple[str, ...]]:
    path = _state_path(plan)
    if path.is_symlink() or not path.is_file():
        return (), ()
    content = path.read_bytes()
    if len(content) > _MAX_DOCUMENT_BYTES:
        _fail("archive state")
    value: object = json.loads(content)
    if type(value) is not dict:
        _fail("archive state")
    document = cast("dict[str, object]", value)
    raw_copied = document.get("copied")
    raw_deleted = document.get("deleted")
    if (
        _canonical(document) != content
        or set(document) != {"copied", "deleted", "plan_fingerprint", "plan_id", "schema_id"}
        or document.get("schema_id") != _STATE_SCHEMA
        or document.get("plan_id") != plan.plan_id
        or document.get("plan_fingerprint") != plan.plan_fingerprint
        or type(raw_copied) is not list
        or type(raw_deleted) is not list
    ):
        _fail("archive state")
    copied = cast("list[object]", raw_copied)
    deleted = cast("list[object]", raw_deleted)
    if any(type(item) is not str for item in (*copied, *deleted)):
        _fail("archive state")
    copied_names = tuple(cast("list[str]", copied))
    deleted_names = tuple(cast("list[str]", deleted))
    if (
        len(set(copied_names)) != len(copied_names)
        or len(set(deleted_names)) != len(deleted_names)
        or not set(deleted_names).issubset(copied_names)
    ):
        _fail("archive state")
    return copied_names, deleted_names


def _copy_and_checkpoint(
    plan: ArchiveCleanupPlan,
    copied_set: set[str],
    deleted_set: set[str],
    archive_root: Path,
) -> None:
    for candidate in plan.candidates:
        target = archive_root / candidate.archive_name
        if target.is_symlink():
            _fail("archive staging path")
        if candidate.archive_name in copied_set:
            if not _matches_inventory(candidate, target):
                _fail("archive readback mismatch")
            continue
        if target.exists() and not _matches_inventory(candidate, target):
            _fail("archive readback mismatch")
        if not target.exists():
            _copy_candidate(candidate, target)
        if not _matches_inventory(candidate, target):
            _fail("archive readback mismatch")
        copied_set.add(candidate.archive_name)
        _write_state(plan, tuple(sorted(copied_set)), tuple(sorted(deleted_set)))


def _delete_and_checkpoint(
    plan: ArchiveCleanupPlan,
    copied_set: set[str],
    deleted_set: set[str],
    archive_root: Path,
) -> None:
    for candidate in plan.candidates:
        if candidate.archive_name in deleted_set:
            if candidate.source_path.exists() or candidate.source_path.is_symlink():
                _fail("archive deletion replay drift")
            continue
        target = archive_root / candidate.archive_name
        if not _matches_inventory(candidate, target):
            _fail("archive readback mismatch")
        if candidate.source_path.is_symlink():
            _fail("archive source symlink")
        if candidate.source_path.exists():
            current = inventory_candidate(candidate.source_path, candidate.archive_name)
            if current != candidate:
                _fail("archive source drift")
            if candidate.source_path.is_file():
                candidate.source_path.unlink()
            else:
                shutil.rmtree(candidate.source_path)
        deleted_set.add(candidate.archive_name)
        _write_state(plan, tuple(sorted(copied_set)), tuple(sorted(deleted_set)))


def execute_archive_cleanup(plan: ArchiveCleanupPlan, authority_path: Path) -> ArchiveCleanupReport:
    """Copy, recursively read back, then delete only exact authorized sources."""
    _safe_path(plan.destination, "archive destination")
    if plan.destination.is_symlink() or not plan.destination.is_dir():
        _fail("archive destination")
    operation_root = plan.destination / plan.plan_id
    archive_root = operation_root / "items"
    if operation_root.is_symlink() or archive_root.is_symlink():
        _fail("archive staging path")
    if operation_root.exists() and not operation_root.is_dir():
        _fail("archive staging path")
    if archive_root.exists() and not archive_root.is_dir():
        _fail("archive staging path")
    _load_authority(authority_path, plan)
    copied, deleted = _read_state(plan)
    names = tuple(candidate.archive_name for candidate in plan.candidates)
    if any(name not in names for name in (*copied, *deleted)):
        _fail("archive state")
    archive_root.mkdir(parents=True, exist_ok=True)
    copied_set = set(copied)
    deleted_set = set(deleted)
    _copy_and_checkpoint(plan, copied_set, deleted_set, archive_root)
    _delete_and_checkpoint(plan, copied_set, deleted_set, archive_root)
    complete = copied_set == set(names) and deleted_set == set(names)
    return ArchiveCleanupReport(
        plan.plan_id,
        plan.plan_fingerprint,
        "SUCCEEDED" if complete else "BLOCKED",
        tuple(sorted(copied_set)),
        tuple(sorted(deleted_set)),
        complete,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--candidate", action="append", type=Path)
    parser.add_argument("--latest-journal", action="append", type=Path)
    parser.add_argument("--current-baseline", action="append", type=Path)
    parser.add_argument("--fixture", action="append", type=Path)
    parser.add_argument("--approval-state", action="append", type=Path)
    parser.add_argument("--promotion-evidence", action="append", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--authority", type=Path)
    return parser


def _paths(value: object, label: str) -> tuple[Path, ...]:
    if type(value) is not list or not value:
        _fail(label)
    paths = cast("list[object]", value)
    if any(not isinstance(item, Path) for item in paths):
        _fail(label)
    return tuple(cast("list[Path]", paths))


def main(argv: Sequence[str] | None = None) -> int:
    """Inventory by default; execute only a separately retained authorized plan."""
    arguments = _parser().parse_args(argv)
    try:
        if arguments.execute:
            if not isinstance(arguments.plan_file, Path) or not isinstance(
                arguments.authority, Path
            ):
                _fail("archive execution input")
            report = execute_archive_cleanup(
                load_archive_cleanup_plan(arguments.plan_file), arguments.authority
            )
            sys.stdout.buffer.write(_canonical(report.document()) + b"\n")
            return 0 if report.complete else 2
        if not isinstance(arguments.destination, Path):
            _fail("archive destination")
        protections = ArchiveProtectionSet(
            _paths(arguments.latest_journal, "latest journals"),
            _paths(arguments.current_baseline, "current baseline"),
            _paths(arguments.fixture, "fixtures"),
            _paths(arguments.approval_state, "approval state"),
            _paths(arguments.promotion_evidence, "promotion evidence"),
        )
        plan = build_archive_cleanup_plan(
            _paths(arguments.candidate, "archive candidate paths"),
            arguments.destination,
            protections,
        )
        sys.stdout.buffer.write(archive_cleanup_plan_bytes(plan) + b"\n")
    except OSError, shutil.Error, TypeError, ValueError:
        sys.stdout.buffer.write(
            b'{"blocker_code":"ARCHIVE_CLEANUP_NOT_READY","state":"NOT_READY"}\n'
        )
        return 2
    else:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
