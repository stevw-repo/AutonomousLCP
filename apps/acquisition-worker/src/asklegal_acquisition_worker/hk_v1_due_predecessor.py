"""Atomic local predecessor state for resumable Hong Kong V1 due cycles."""

from __future__ import annotations

import fcntl
import os
import stat
import threading
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Protocol, Self

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_reporting import (
    DueCycleKind,
    DueImmutableReference,
    HongKongV1DueCycleError,
    HongKongV1DueCycleInstruction,
    hk_v1_due_cycle_manifest_key,
)

_SCHEMA_ID = "asklegal.hk-v1-due-cycle-predecessor-state"
_SCHEMA_VERSION = "1.0.0"
_MAX_BYTES = 65_536
_FINGERPRINT_LENGTH = 71
_PRIVATE_ROOT_MODE = 0o700
_FILENAMES = {
    DueCycleKind.DAILY_CURRENT_LAW: "daily-current-law.json",
    DueCycleKind.WEEKLY_RELEASE: "weekly-release.json",
    DueCycleKind.MONTHLY_CROSS_CHECK: "monthly-cross-check.json",
    DueCycleKind.FULL_PERIODIC: "full-periodic.json",
}


class DueCyclePredecessorError(ValueError):
    """One closed local predecessor parsing or filesystem failure."""


class DueCyclePredecessorConflict(DueCyclePredecessorError):
    """A stale or divergent compare-and-set attempt."""


@dataclass(frozen=True, slots=True)
class DueCyclePredecessorState:
    """One exact, fingerprint-bound predecessor state publication."""

    instruction: HongKongV1DueCycleInstruction
    plan_fingerprint: str
    predecessor_fingerprint: str | None
    manifest_reference: DueImmutableReference
    report_fingerprint: str
    state_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate the typed state and derive its immutable self-fingerprint."""
        object.__setattr__(self, "instruction", _rebuild_instruction_value(self.instruction))
        object.__setattr__(
            self, "manifest_reference", _rebuild_reference_value(self.manifest_reference)
        )
        _validate_state_fields(self)
        object.__setattr__(self, "state_fingerprint", _fingerprint(_unsigned_body(self)))


@dataclass(frozen=True, slots=True)
class DueCyclePredecessorWriteReceipt:
    """One created or exact-adopted state publication."""

    state: DueCyclePredecessorState
    created: bool

    def __post_init__(self) -> None:
        """Keep receipts exact and boolean rather than truthy."""
        if type(self.state) is not DueCyclePredecessorState or type(self.created) is not bool:
            msg = "DUE_PREDECESSOR_RECEIPT_INVALID"
            raise DueCyclePredecessorError(msg)
        object.__setattr__(self, "state", _rebuild_state(self.state))


class DueCyclePredecessorStore(Protocol):
    """The narrow durable predecessor boundary used by due-cycle activities."""

    def load(self, kind: DueCycleKind) -> DueCyclePredecessorState | None:
        """Load one exact latest state for a recurring cycle kind."""
        ...

    def compare_and_set(
        self,
        expected_fingerprint: str | None,
        new_state: DueCyclePredecessorState,
    ) -> DueCyclePredecessorWriteReceipt:
        """Atomically create one successor or exactly adopt a lost acknowledgement."""
        ...


class LocalDueCyclePredecessorStore:
    """One pinned-root, globally serialized local predecessor store.

    The global per-root lock deliberately sacrifices cross-kind parallelism for
    a prototype-safe authority: no replaceable path under the root controls
    synchronization.
    """

    def __init__(self, root: object) -> None:
        """Bind exactly one existing or newly created absolute non-symlink root."""
        root = _validated_root_path(root)
        self._root = root
        self._root_fd = _walk_root(root, create=True)
        try:
            details = _fstat_root(self._root_fd)
            _require_private_root(details)
            self._root_identity = (details.st_dev, details.st_ino)
            _verify_walk_identity(root, self._root_identity)
        except BaseException:
            with suppress(OSError):
                os.close(self._root_fd)
            raise
        self._thread_lock = threading.Lock()
        self._closed = False

    @property
    def acquisition_state_root(self) -> Path:
        """Return the pinned root also owning sibling family acquisition journals."""
        return self._root

    def close(self) -> None:
        """Idempotently release the pinned root descriptor."""
        with self._thread_lock:
            if not self._closed:
                self._closed = True
                try:
                    os.close(self._root_fd)
                except OSError as error:
                    msg = "DUE_PREDECESSOR_IO"
                    raise DueCyclePredecessorError(msg) from error

    def __enter__(self) -> Self:
        """Permit explicit store lifecycle ownership."""
        return self

    def __exit__(self, *_: object) -> None:
        """Release the pinned descriptor at context exit."""
        self.close()

    def load(self, kind: DueCycleKind) -> DueCyclePredecessorState | None:
        """Load and strictly parse the fixed state object under its lock."""
        _filename(kind)
        with self._locked(kind) as directory_fd:
            return _read_locked(directory_fd, _filename(kind), kind)

    def compare_and_set(
        self,
        expected_fingerprint: str | None,
        new_state: DueCyclePredecessorState,
    ) -> DueCyclePredecessorWriteReceipt:
        """Atomically publish one monotonic state or adopt exact retained bytes."""
        state = _rebuild_state(new_state)
        _fingerprint_or_none(expected_fingerprint)
        if state.predecessor_fingerprint != expected_fingerprint:
            msg = "DUE_PREDECESSOR_EXPECTED_MISMATCH"
            raise DueCyclePredecessorConflict(msg)
        kind = state.instruction.cycle_kind
        content = _serialize(state)
        with self._locked(kind) as directory_fd:
            current = _read_locked(directory_fd, _filename(kind), kind)
            if current is not None and _serialize(current) == content:
                try:
                    os.fsync(directory_fd)
                except OSError as error:
                    msg = "DUE_PREDECESSOR_IO"
                    raise DueCyclePredecessorError(msg) from error
                return DueCyclePredecessorWriteReceipt(current, created=False)
            current_fingerprint = None if current is None else current.state_fingerprint
            if current_fingerprint != expected_fingerprint:
                msg = "DUE_PREDECESSOR_STALE"
                raise DueCyclePredecessorConflict(msg)
            if current is not None:
                _validate_successor(current, state)
            _write_locked(directory_fd, _filename(kind), content, kind)
            return DueCyclePredecessorWriteReceipt(state, created=True)

    @contextmanager
    def _locked(self, kind: DueCycleKind) -> Generator[int]:
        """Use the pinned root fd itself as the unreplaceable global lock."""
        _filename(kind)
        self._thread_lock.acquire()
        locked = False
        try:
            if self._closed:
                msg = "DUE_PREDECESSOR_CLOSED"
                raise DueCyclePredecessorError(msg)
            self._verify_root_identity()
            fcntl.flock(self._root_fd, fcntl.LOCK_EX)
            locked = True
            self._verify_root_identity()
            yield self._root_fd
            self._verify_root_identity()
        except OSError as error:
            msg = "DUE_PREDECESSOR_IO"
            raise DueCyclePredecessorError(msg) from error
        finally:
            try:
                if locked:
                    fcntl.flock(self._root_fd, fcntl.LOCK_UN)
            except OSError as error:
                msg = "DUE_PREDECESSOR_IO"
                raise DueCyclePredecessorError(msg) from error
            finally:
                self._thread_lock.release()

    def _verify_root_identity(self) -> None:
        """Fail closed if the configured lexical root no longer reaches the pinned inode."""
        _require_private_root(os.fstat(self._root_fd))
        current_fd = _walk_root(self._root, create=False)
        try:
            current = os.fstat(current_fd)
            if (current.st_dev, current.st_ino) != self._root_identity:
                msg = "DUE_PREDECESSOR_ROOT_REPLACED"
                raise DueCyclePredecessorError(msg)
        finally:
            try:
                os.close(current_fd)
            except OSError as error:
                msg = "DUE_PREDECESSOR_IO"
                raise DueCyclePredecessorError(msg) from error


def _filename(kind: object) -> str:
    if type(kind) is not DueCycleKind:
        msg = "DUE_PREDECESSOR_KIND_INVALID"
        raise DueCyclePredecessorError(msg)
    return _FILENAMES[kind]


def _validated_root_path(root: object) -> Path:
    """Accept only one explicit, lexical, non-filesystem-wide Path root."""
    if (
        type(root) is not type(Path())
        or not root.is_absolute()
        or root == Path(root.anchor)
        or any(part in {".", ".."} for part in root.parts)
    ):
        msg = "DUE_PREDECESSOR_ROOT_INVALID"
        raise DueCyclePredecessorError(msg)
    return root


def _open_directory(path: str, *, parent_fd: int | None = None) -> int:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except OSError as error:
        msg = "DUE_PREDECESSOR_ROOT_INVALID"
        raise DueCyclePredecessorError(msg) from error
    try:
        details = _fstat_root(descriptor)
    except DueCyclePredecessorError:
        with suppress(OSError):
            os.close(descriptor)
        raise
    if not stat.S_ISDIR(details.st_mode):
        os.close(descriptor)
        msg = "DUE_PREDECESSOR_ROOT_INVALID"
        raise DueCyclePredecessorError(msg)
    return descriptor


def _require_private_root(details: os.stat_result) -> None:
    """Require the pinned state authority to be owned and private to this process user."""
    if details.st_uid != os.geteuid() or stat.S_IMODE(details.st_mode) != _PRIVATE_ROOT_MODE:
        msg = "DUE_PREDECESSOR_ROOT_INVALID"
        raise DueCyclePredecessorError(msg)


def _fstat_root(descriptor: int) -> os.stat_result:
    """Inspect one root-walk descriptor without leaking a raw filesystem error."""
    try:
        return os.fstat(descriptor)
    except OSError as error:
        msg = "DUE_PREDECESSOR_ROOT_INVALID"
        raise DueCyclePredecessorError(msg) from error


def _walk_root(root: Path, *, create: bool) -> int:
    """Open every configured root component from `/` without following aliases."""
    _validated_root_path(root)
    current_fd = _open_directory(root.anchor)
    try:
        for component in root.parts[1:]:
            try:
                next_fd = _open_directory(component, parent_fd=current_fd)
            except DueCyclePredecessorError:
                if not create:
                    raise
                try:
                    os.mkdir(component, mode=_PRIVATE_ROOT_MODE, dir_fd=current_fd)
                except FileExistsError:
                    pass
                except OSError as error:
                    msg = "DUE_PREDECESSOR_ROOT_INVALID"
                    raise DueCyclePredecessorError(msg) from error
                else:
                    try:
                        os.fsync(current_fd)
                    except OSError as error:
                        msg = "DUE_PREDECESSOR_IO"
                        raise DueCyclePredecessorError(msg) from error
                next_fd = _open_directory(component, parent_fd=current_fd)
            try:
                os.close(current_fd)
            except OSError as error:
                os.close(next_fd)
                msg = "DUE_PREDECESSOR_IO"
                raise DueCyclePredecessorError(msg) from error
            current_fd = next_fd
    except BaseException:
        with suppress(OSError):
            os.close(current_fd)
        raise
    return current_fd


def _verify_walk_identity(root: Path, identity: tuple[int, int]) -> None:
    """Verify one fresh no-follow walk still terminates at the expected root inode."""
    current_fd = _walk_root(root, create=False)
    try:
        current = _fstat_root(current_fd)
        if (current.st_dev, current.st_ino) != identity:
            msg = "DUE_PREDECESSOR_ROOT_REPLACED"
            raise DueCyclePredecessorError(msg)
    finally:
        os.close(current_fd)


def _read_locked(
    directory_fd: int, filename: str, expected_kind: DueCycleKind
) -> DueCyclePredecessorState | None:
    try:
        descriptor = os.open(
            filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_fd
        )
    except FileNotFoundError:
        return None
    except OSError as error:
        msg = "DUE_PREDECESSOR_IO"
        raise DueCyclePredecessorError(msg) from error
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_size > _MAX_BYTES:
            msg = "DUE_PREDECESSOR_FILE_INVALID"
            raise DueCyclePredecessorError(msg)
        chunks: list[bytes] = []
        remaining = _MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if not content or len(content) > _MAX_BYTES:
            msg = "DUE_PREDECESSOR_FILE_INVALID"
            raise DueCyclePredecessorError(msg)
        return _parse(content, expected_kind)
    except OSError as error:
        msg = "DUE_PREDECESSOR_IO"
        raise DueCyclePredecessorError(msg) from error
    finally:
        os.close(descriptor)


def _write_locked(
    directory_fd: int, filename: str, content: bytes, expected_kind: DueCycleKind
) -> None:
    temporary = f".{filename}.{token_hex(16)}.tmp"
    descriptor: int | None = None
    owned = False
    owned_identity: tuple[int, int] | None = None
    acknowledged = False
    try:
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
        owned = True
        details = os.fstat(descriptor)
        owned_identity = (details.st_dev, details.st_ino)
        cursor = 0
        while cursor < len(content):
            written = os.write(descriptor, content[cursor:])
            if written <= 0:
                msg = "DUE_PREDECESSOR_WRITE_INVALID"
                raise DueCyclePredecessorError(msg)
            cursor += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, filename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
        retained = _read_locked(directory_fd, filename, expected_kind)
        if retained is None or _serialize(retained) != content:
            msg = "DUE_PREDECESSOR_WRITE_VERIFY"
            raise DueCyclePredecessorError(msg)
        acknowledged = True
    except OSError as error:
        msg = "DUE_PREDECESSOR_IO"
        raise DueCyclePredecessorError(msg) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if owned and not acknowledged and owned_identity is not None:
            _remove_owned_temporary(directory_fd, temporary, owned_identity)


def _remove_owned_temporary(directory_fd: int, temporary: str, identity: tuple[int, int]) -> None:
    """Remove only a still-present regular temporary inode created by this CAS."""
    try:
        details = os.stat(temporary, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        msg = "DUE_PREDECESSOR_IO"
        raise DueCyclePredecessorError(msg) from error
    if stat.S_ISREG(details.st_mode) and (details.st_dev, details.st_ino) == identity:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            return
        except OSError as error:
            msg = "DUE_PREDECESSOR_IO"
            raise DueCyclePredecessorError(msg) from error


def _parse(content: bytes, expected_kind: DueCycleKind | None = None) -> DueCyclePredecessorState:
    try:
        document = parse_json_bytes(content, max_bytes=_MAX_BYTES)
        if not isinstance(document, dict) or frozenset(document) != frozenset(
            {
                "schema_id",
                "schema_version",
                "instruction",
                "plan_fingerprint",
                "predecessor_fingerprint",
                "manifest_reference",
                "report_fingerprint",
                "state_fingerprint",
            }
        ):
            msg = "DUE_PREDECESSOR_INVALID"
            raise DueCyclePredecessorError(msg)
        if document["schema_id"] != _SCHEMA_ID or document["schema_version"] != _SCHEMA_VERSION:
            msg = "DUE_PREDECESSOR_INVALID"
            raise DueCyclePredecessorError(msg)
        state = DueCyclePredecessorState(
            _instruction(document["instruction"]),
            _fingerprint_value(document["plan_fingerprint"]),
            _fingerprint_optional(document["predecessor_fingerprint"]),
            _reference(document["manifest_reference"]),
            _fingerprint_value(document["report_fingerprint"]),
        )
        if expected_kind is not None and state.instruction.cycle_kind is not expected_kind:
            msg = "DUE_PREDECESSOR_INVALID"
            raise DueCyclePredecessorError(msg)
        if document["state_fingerprint"] != state.state_fingerprint or _serialize(state) != content:
            msg = "DUE_PREDECESSOR_INVALID"
            raise DueCyclePredecessorError(msg)
    except (HongKongV1DueCycleError, TypeError, ValueError) as error:
        if isinstance(error, DueCyclePredecessorError):
            raise
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg) from error
    else:
        return state


def _instruction(value: JsonValue) -> HongKongV1DueCycleInstruction:
    return HongKongV1DueCycleInstruction.from_json(value)


def _rebuild_instruction_value(value: object) -> HongKongV1DueCycleInstruction:
    """Clone an instruction through its strict JSON boundary before state canonicalization."""
    if type(value) is not HongKongV1DueCycleInstruction:
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg)
    try:
        return _instruction(
            {
                "cycle_id": value.cycle_id,
                "cycle_kind": value.cycle_kind.value,
                "scheduled_at": value.scheduled_at,
                "observation_cutoff": value.observation_cutoff,
                "matrix_revision": value.matrix_revision,
                "matrix_fingerprint": value.matrix_fingerprint,
            }
        )
    except (AttributeError, HongKongV1DueCycleError, TypeError, ValueError) as error:
        if isinstance(error, DueCyclePredecessorError):
            raise
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg) from error


def _reference(value: JsonValue) -> DueImmutableReference:
    if not isinstance(value, dict) or frozenset(value) != frozenset(
        {"vault", "logical_key", "version_id", "fingerprint", "byte_length"}
    ):
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg)
    return DueImmutableReference(
        _text(value["vault"]),
        _text(value["logical_key"]),
        _text(value["version_id"]),
        _fingerprint_value(value["fingerprint"]),
        _integer(value["byte_length"]),
    )


def _rebuild_reference_value(value: object) -> DueImmutableReference:
    """Clone a reference through its strict JSON boundary before state canonicalization."""
    if type(value) is not DueImmutableReference:
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg)
    try:
        return _reference(
            {
                "vault": value.vault,
                "logical_key": value.logical_key,
                "version_id": value.version_id,
                "fingerprint": value.fingerprint,
                "byte_length": value.byte_length,
            }
        )
    except (AttributeError, HongKongV1DueCycleError, TypeError, ValueError) as error:
        if isinstance(error, DueCyclePredecessorError):
            raise
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg) from error


def _validate_state_fields(state: DueCyclePredecessorState) -> None:
    if type(state.instruction) is not HongKongV1DueCycleInstruction:
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg)
    _fingerprint_value(state.plan_fingerprint)
    _fingerprint_or_none(state.predecessor_fingerprint)
    if (
        type(state.manifest_reference) is not DueImmutableReference
        or state.manifest_reference.vault != "PRIMARY"
        or state.manifest_reference.logical_key
        != hk_v1_due_cycle_manifest_key(state.instruction.cycle_id)
        or state.manifest_reference.fingerprint != state.report_fingerprint
        or state.manifest_reference.byte_length <= 0
    ):
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg)
    _fingerprint_value(state.report_fingerprint)


def _rebuild_state(state: object) -> DueCyclePredecessorState:
    """Rebuild every nested contract before trusting an object-originated state."""
    if type(state) is not DueCyclePredecessorState:
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg)
    try:
        rebuilt = DueCyclePredecessorState(
            _rebuild_instruction_value(state.instruction),
            _fingerprint_value(state.plan_fingerprint),
            _fingerprint_optional(state.predecessor_fingerprint),
            _rebuild_reference_value(state.manifest_reference),
            _fingerprint_value(state.report_fingerprint),
        )
        if _fingerprint_value(state.state_fingerprint) != rebuilt.state_fingerprint:
            msg = "DUE_PREDECESSOR_INVALID"
            raise DueCyclePredecessorError(msg)
    except (AttributeError, HongKongV1DueCycleError, TypeError, ValueError) as error:
        if isinstance(error, DueCyclePredecessorError):
            raise
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg) from error
    return rebuilt


def _validate_successor(current: DueCyclePredecessorState, new: DueCyclePredecessorState) -> None:
    old = current.instruction
    latest = new.instruction
    if (
        old.cycle_kind is not latest.cycle_kind
        or old.cycle_id == latest.cycle_id
        or latest.scheduled_at <= old.scheduled_at
        or latest.observation_cutoff <= old.observation_cutoff
    ):
        msg = "DUE_PREDECESSOR_REGRESSION"
        raise DueCyclePredecessorConflict(msg)


def _serialize(state: DueCyclePredecessorState) -> bytes:
    return canonicalize(
        checked_json_value({**_unsigned_body(state), "state_fingerprint": state.state_fingerprint})
    )


def _unsigned_body(state: DueCyclePredecessorState) -> dict[str, object]:
    instruction = state.instruction
    reference = state.manifest_reference
    return {
        "schema_id": _SCHEMA_ID,
        "schema_version": _SCHEMA_VERSION,
        "instruction": {
            "cycle_id": instruction.cycle_id,
            "cycle_kind": instruction.cycle_kind.value,
            "scheduled_at": instruction.scheduled_at,
            "observation_cutoff": instruction.observation_cutoff,
            "matrix_revision": instruction.matrix_revision,
            "matrix_fingerprint": instruction.matrix_fingerprint,
        },
        "plan_fingerprint": state.plan_fingerprint,
        "predecessor_fingerprint": state.predecessor_fingerprint,
        "manifest_reference": {
            "vault": reference.vault,
            "logical_key": reference.logical_key,
            "version_id": reference.version_id,
            "fingerprint": reference.fingerprint,
            "byte_length": reference.byte_length,
        },
        "report_fingerprint": state.report_fingerprint,
    }


def _fingerprint(value: object) -> str:
    return f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"


def _fingerprint_value(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != _FINGERPRINT_LENGTH
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg)
    return value


def _fingerprint_optional(value: object) -> str | None:
    if value is None:
        return None
    return _fingerprint_value(value)


def _fingerprint_or_none(value: object) -> None:
    _fingerprint_optional(value)


def _text(value: object) -> str:
    if type(value) is not str:
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg)
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        msg = "DUE_PREDECESSOR_INVALID"
        raise DueCyclePredecessorError(msg)
    return value
