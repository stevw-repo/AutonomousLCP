"""Exact local predecessor-state store contract for the HK V1 due cycle."""

from __future__ import annotations

import os
from multiprocessing import get_context
from multiprocessing.queues import Queue
from pathlib import Path
from threading import Barrier, Event, Thread

import asklegal_acquisition_worker.hk_v1_due_predecessor as predecessor
import pytest
from asklegal_acquisition_worker.hk_v1_due_predecessor import (
    DueCyclePredecessorConflict,
    DueCyclePredecessorError,
    DueCyclePredecessorState,
    DueCyclePredecessorWriteReceipt,
    LocalDueCyclePredecessorStore,
)
from asklegal_evidence_vault import VaultName
from asklegal_reporting import (
    DueCycleKind,
    DueImmutableReference,
    HongKongV1DueCycleInstruction,
    hk_v1_due_cycle_manifest_key,
    load_hk_v1_coverage_matrix,
)


def _state(
    *,
    cycle_id: str = "hk-v1-daily-20260826",
    kind: DueCycleKind = DueCycleKind.DAILY_CURRENT_LAW,
    scheduled_at: str = "2026-08-26T00:00:00Z",
    cutoff: str = "2026-08-26T00:00:00Z",
    predecessor: str | None = None,
) -> DueCyclePredecessorState:
    matrix = load_hk_v1_coverage_matrix()
    return DueCyclePredecessorState(
        HongKongV1DueCycleInstruction(
            cycle_id,
            kind,
            scheduled_at,
            cutoff,
            matrix.revision,
            matrix.fingerprint,
        ),
        "sha256:" + "a" * 64,
        predecessor,
        DueImmutableReference(
            VaultName.PRIMARY.value,
            hk_v1_due_cycle_manifest_key(cycle_id),
            "v" + "b" * 64,
            "sha256:" + "b" * 64,
            123,
        ),
        "sha256:" + "b" * 64,
    )


def _process_write(root: str, queue: Queue[bool]) -> None:
    """Run one exact initial CAS in a separate process for flock proof."""
    queue.put(LocalDueCyclePredecessorStore(Path(root)).compare_and_set(None, _state()).created)


def _process_divergent_write(
    root: str, cycle_id: str, conflict_label: str, queue: Queue[tuple[str, str]]
) -> None:
    """Compete one distinct initial CAS in a separate process."""
    try:
        result = LocalDueCyclePredecessorStore(Path(root)).compare_and_set(
            None,
            _state(cycle_id=cycle_id),
        )
        queue.put(("created", result.state.instruction.cycle_id))
    except DueCyclePredecessorConflict:
        queue.put(("conflict", conflict_label))


def test_initial_compare_and_set_round_trips_exact_canonical_state(tmp_path: Path) -> None:
    """The first state is persisted and strictly reconstructed from its fixed file."""
    matrix = load_hk_v1_coverage_matrix()
    state = DueCyclePredecessorState(
        instruction=HongKongV1DueCycleInstruction(
            "hk-v1-daily-20260826",
            DueCycleKind.DAILY_CURRENT_LAW,
            "2026-08-26T00:00:00Z",
            "2026-08-26T00:00:00Z",
            matrix.revision,
            matrix.fingerprint,
        ),
        plan_fingerprint="sha256:" + "a" * 64,
        predecessor_fingerprint=None,
        manifest_reference=DueImmutableReference(
            VaultName.PRIMARY.value,
            hk_v1_due_cycle_manifest_key("hk-v1-daily-20260826"),
            "v" + "b" * 64,
            "sha256:" + "b" * 64,
            123,
        ),
        report_fingerprint="sha256:" + "b" * 64,
    )
    store = LocalDueCyclePredecessorStore(tmp_path)

    receipt = store.compare_and_set(None, state)

    assert receipt.created is True
    assert store.load(DueCycleKind.DAILY_CURRENT_LAW) == receipt.state


def test_identical_retry_adopts_and_stale_or_divergent_writes_fail(tmp_path: Path) -> None:
    """Lost acknowledgement is safe, but same-key divergence never replaces state."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    first = _state()
    created = store.compare_and_set(None, first)

    assert store.compare_and_set(None, first).created is False
    with pytest.raises(DueCyclePredecessorConflict):
        store.compare_and_set(None, _state(cycle_id="hk-v1-daily-other-20260826"))
    with pytest.raises(DueCyclePredecessorConflict):
        store.compare_and_set("sha256:" + "d" * 64, first)
    assert store.load(DueCycleKind.DAILY_CURRENT_LAW) == created.state


def test_successor_requires_consumed_predecessor_and_strictly_later_times(tmp_path: Path) -> None:
    """Continuity cannot regress schedule or cutoff, even under a correct CAS fingerprint."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    first = store.compare_and_set(None, _state()).state
    successor = _state(
        cycle_id="hk-v1-daily-20260827",
        scheduled_at="2026-08-27T00:00:00Z",
        cutoff="2026-08-27T00:00:00Z",
        predecessor=first.state_fingerprint,
    )
    assert store.compare_and_set(first.state_fingerprint, successor).created is True

    with pytest.raises(DueCyclePredecessorConflict):
        store.compare_and_set(
            successor.state_fingerprint,
            _state(
                cycle_id="hk-v1-daily-20260828",
                scheduled_at="2026-08-27T00:00:00Z",
                cutoff="2026-08-28T00:00:00Z",
                predecessor=successor.state_fingerprint,
            ),
        )


def test_malformed_or_noncanonical_retained_state_fails_closed(tmp_path: Path) -> None:
    """The store never treats malformed retained JSON as an absent predecessor."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    (tmp_path / "daily-current-law.json").write_bytes(b'{"schema_id":"bad"}')

    with pytest.raises(DueCyclePredecessorError):
        store.load(DueCycleKind.DAILY_CURRENT_LAW)


@pytest.mark.parametrize(
    ("requested_kind", "stored_kind", "filename", "stored_filename"),
    [
        (
            DueCycleKind.DAILY_CURRENT_LAW,
            DueCycleKind.WEEKLY_RELEASE,
            "daily-current-law.json",
            "weekly-release.json",
        ),
        (
            DueCycleKind.WEEKLY_RELEASE,
            DueCycleKind.DAILY_CURRENT_LAW,
            "weekly-release.json",
            "daily-current-law.json",
        ),
    ],
)
def test_fixed_kind_file_rejects_canonical_state_for_another_kind(
    tmp_path: Path,
    requested_kind: DueCycleKind,
    stored_kind: DueCycleKind,
    filename: str,
    stored_filename: str,
) -> None:
    """A canonical state cannot be replayed through another kind's fixed path."""
    target_root = tmp_path / "target"
    source_root = tmp_path / "source"
    store = LocalDueCyclePredecessorStore(target_root)
    source = LocalDueCyclePredecessorStore(source_root)
    retained = _state(kind=stored_kind)
    source.compare_and_set(None, retained)
    (target_root / filename).write_bytes((source_root / stored_filename).read_bytes())

    with pytest.raises(DueCyclePredecessorError):
        store.load(requested_kind)
    with pytest.raises(DueCyclePredecessorError):
        store.compare_and_set(None, _state(kind=requested_kind))


def test_symlink_and_oversized_state_paths_fail_closed(tmp_path: Path) -> None:
    """Neither roots nor retained targets may become aliases or unbounded reads."""
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(DueCyclePredecessorError):
        LocalDueCyclePredecessorStore(alias)

    store = LocalDueCyclePredecessorStore(tmp_path / "state")
    state_file = tmp_path / "state" / "daily-current-law.json"
    state_file.write_bytes(b"x" * 65_537)
    with pytest.raises(DueCyclePredecessorError):
        store.load(DueCycleKind.DAILY_CURRENT_LAW)


@pytest.mark.parametrize("root", [Path("relative"), Path("/"), Path("/var") / "child" / ".."])
def test_constructor_rejects_noncanonical_or_broad_lexical_roots(root: Path) -> None:
    """Traversal, relative, and filesystem-wide roots cannot receive state files."""
    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_ROOT_INVALID"):
        LocalDueCyclePredecessorStore(root)


def test_constructor_rejects_non_path_root_before_filesystem_mutation() -> None:
    """A string cannot smuggle expansion or traversal into the state-root boundary."""
    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_ROOT_INVALID"):
        LocalDueCyclePredecessorStore(str(Path("/var") / "not-a-path"))


def test_constructor_uses_no_follow_component_walk_when_parent_becomes_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A late ancestor alias fails rather than pinning a redirected state authority."""
    root = tmp_path / "state" / "nested"
    original_open = predecessor.os.open
    injected = False

    def inject_alias(path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        nonlocal injected
        if path == "nested" and not injected:
            injected = True
            (tmp_path / "alternate").mkdir()
            (tmp_path / "state").rmdir()
            (tmp_path / "state").symlink_to(tmp_path / "alternate", target_is_directory=True)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(predecessor.os, "open", inject_alias)

    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_ROOT_INVALID"):
        LocalDueCyclePredecessorStore(root)
    assert not (tmp_path / "alternate" / "nested").exists()


def test_constructor_fsyncs_each_new_parent_before_announcing_nested_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A newly made root component is never treated as durable before its parent syncs."""
    root = tmp_path / "durable" / "nested"

    def fail_fsync(_descriptor: int) -> None:
        message = "injected mkdir durability failure"
        raise OSError(message)

    monkeypatch.setattr(predecessor.os, "fsync", fail_fsync)
    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_IO"):
        LocalDueCyclePredecessorStore(root)
    monkeypatch.undo()

    store = LocalDueCyclePredecessorStore(root)
    assert store.load(DueCycleKind.DAILY_CURRENT_LAW) is None


@pytest.mark.parametrize("mode", [0o770, 0o777])
def test_constructor_rejects_existing_root_with_group_or_world_access(
    tmp_path: Path, mode: int
) -> None:
    """Another local account cannot write or inspect the predecessor authority."""
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    root.chmod(mode)

    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_ROOT_INVALID"):
        LocalDueCyclePredecessorStore(root)


def test_constructor_creates_nested_root_with_exact_owner_only_mode(tmp_path: Path) -> None:
    """Created predecessor roots expose no group or world access bits."""
    root = tmp_path / "state" / "nested"
    LocalDueCyclePredecessorStore(root).close()

    assert root.stat().st_mode & 0o777 == 0o700


def test_constructor_rejects_root_descriptor_with_other_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ownership decision comes from the opened root descriptor, not path metadata."""
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    root_inode = root.stat().st_ino
    original_fstat = predecessor.os.fstat

    def wrong_owner(descriptor: int) -> os.stat_result:
        details = original_fstat(descriptor)
        if details.st_ino != root_inode:
            return details
        fields = list(details)
        fields[4] = details.st_uid + 1
        return os.stat_result(fields)

    monkeypatch.setattr(predecessor.os, "fstat", wrong_owner)
    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_ROOT_INVALID"):
        LocalDueCyclePredecessorStore(root)


def test_constructor_normalizes_descriptor_inspection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raw descriptor failure cannot escape the local state-root configuration boundary."""

    def fail_fstat(_descriptor: int) -> os.stat_result:
        message = "injected descriptor failure"
        raise OSError(message)

    monkeypatch.setattr(predecessor.os, "fstat", fail_fstat)
    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_ROOT_INVALID"):
        LocalDueCyclePredecessorStore(tmp_path / "state")


def test_close_failure_cannot_retain_the_global_flock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cleanup failure after a locked operation cannot strand another store behind flock."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    other = LocalDueCyclePredecessorStore(tmp_path)
    original_close = predecessor.os.close
    original_dup = predecessor.os.dup
    duplicate: int | None = None

    def inject_duplicate(descriptor: int) -> int:
        nonlocal duplicate
        duplicate = original_dup(descriptor)
        return duplicate

    def fail_duplicate_close(descriptor: int) -> None:
        if descriptor == duplicate:
            message = "injected close failure"
            raise OSError(message)
        original_close(descriptor)

    monkeypatch.setattr(predecessor.os, "dup", inject_duplicate)
    monkeypatch.setattr(predecessor.os, "close", fail_duplicate_close)
    try:
        assert store.load(DueCycleKind.DAILY_CURRENT_LAW) is None
    finally:
        monkeypatch.setattr(predecessor.os, "close", original_close)
        monkeypatch.setattr(predecessor.os, "dup", original_dup)
        store.close()
    assert duplicate is None
    complete = Event()

    def load_other() -> None:
        other.load(DueCycleKind.DAILY_CURRENT_LAW)
        complete.set()

    thread = Thread(target=load_other)
    thread.start()
    thread.join(timeout=1)
    assert complete.is_set()


def test_replaced_configured_root_fails_closed_without_following_new_authority(
    tmp_path: Path,
) -> None:
    """A store pinned to one root cannot silently continue in a replacement directory."""
    root = tmp_path / "state"
    store = LocalDueCyclePredecessorStore(root)
    root.rename(tmp_path / "former-state")
    root.mkdir()

    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_ROOT_REPLACED"):
        store.load(DueCycleKind.DAILY_CURRENT_LAW)
    assert not (root / "daily-current-law.json").exists()


def test_preexisting_predicted_temporary_is_never_removed_after_exclusive_create_rejects_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cleanup can remove only the temporary inode this CAS actually created."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    sentinel = tmp_path / ".daily-current-law.json.known.tmp"
    sentinel.write_bytes(b"preserve")

    def known_token(_size: int) -> str:
        return "known"

    monkeypatch.setattr(predecessor, "token_hex", known_token)

    with pytest.raises(DueCyclePredecessorError):
        store.compare_and_set(None, _state())

    assert sentinel.read_bytes() == b"preserve"
    assert store.load(DueCycleKind.DAILY_CURRENT_LAW) is None


@pytest.mark.parametrize(
    ("reference", "report"),
    [
        (
            DueImmutableReference(
                VaultName.RECOVERY.value,
                hk_v1_due_cycle_manifest_key("hk-v1-daily-20260826"),
                "v" + "b" * 64,
                "sha256:" + "b" * 64,
                123,
            ),
            "sha256:" + "b" * 64,
        ),
        (
            DueImmutableReference(
                VaultName.PRIMARY.value,
                "hk-v1/due-cycle/not-the-manifest.json",
                "v" + "b" * 64,
                "sha256:" + "b" * 64,
                123,
            ),
            "sha256:" + "b" * 64,
        ),
        (
            DueImmutableReference(
                VaultName.PRIMARY.value,
                hk_v1_due_cycle_manifest_key("hk-v1-daily-20260826"),
                "v" + "b" * 64,
                "sha256:" + "b" * 64,
                0,
            ),
            "sha256:" + "b" * 64,
        ),
        (
            DueImmutableReference(
                VaultName.PRIMARY.value,
                hk_v1_due_cycle_manifest_key("hk-v1-daily-20260826"),
                "v" + "b" * 64,
                "sha256:" + "c" * 64,
                123,
            ),
            "sha256:" + "b" * 64,
        ),
    ],
)
def test_state_refuses_detached_or_non_primary_cycle_manifest_binding(
    reference: DueImmutableReference, report: str
) -> None:
    """State publication binds only the exact primary manifest recovered for its cycle."""
    matrix = load_hk_v1_coverage_matrix()
    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_INVALID"):
        DueCyclePredecessorState(
            HongKongV1DueCycleInstruction(
                "hk-v1-daily-20260826",
                DueCycleKind.DAILY_CURRENT_LAW,
                "2026-08-26T00:00:00Z",
                "2026-08-26T00:00:00Z",
                matrix.revision,
                matrix.fingerprint,
            ),
            "sha256:" + "a" * 64,
            None,
            reference,
            report,
        )


def test_compare_and_set_rebuilds_tampered_frozen_state_before_locking(tmp_path: Path) -> None:
    """Object-level mutation cannot turn an already-constructed state into trusted bytes."""
    state = _state()
    object.__setattr__(state, "state_fingerprint", "sha256:" + "f" * 64)
    store = LocalDueCyclePredecessorStore(tmp_path)

    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_INVALID"):
        store.compare_and_set(None, state)
    assert store.load(DueCycleKind.DAILY_CURRENT_LAW) is None


def test_compare_and_set_rebuilds_nested_instruction_before_any_state_fingerprint_use(
    tmp_path: Path,
) -> None:
    """Mutation beneath an exact outer dataclass is rejected as a closed input failure."""
    state = _state()
    object.__setattr__(state.instruction, "cycle_kind", "forged")
    store = LocalDueCyclePredecessorStore(tmp_path)

    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_INVALID"):
        store.compare_and_set(None, state)
    assert store.load(DueCycleKind.DAILY_CURRENT_LAW) is None


def test_state_constructor_normalizes_tampered_nested_contract_to_closed_error() -> None:
    """A pre-mutated nested dataclass cannot leak an attribute error from state construction."""
    instruction = _state().instruction
    object.__setattr__(instruction, "cycle_kind", "forged")
    valid = _state()

    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_INVALID"):
        DueCyclePredecessorState(
            instruction,
            valid.plan_fingerprint,
            valid.predecessor_fingerprint,
            valid.manifest_reference,
            valid.report_fingerprint,
        )


def test_receipt_owns_a_rebuilt_state_snapshot_after_caller_mutation() -> None:
    """A receipt cannot expose a later-mutated state object as a retained publication."""
    state = _state()
    receipt = DueCyclePredecessorWriteReceipt(state, created=True)
    expected = receipt.state.state_fingerprint
    object.__setattr__(state, "state_fingerprint", "sha256:" + "f" * 64)

    assert receipt.state.state_fingerprint == expected


def test_exact_adoption_requires_directory_fsync_before_acknowledgment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost-ack retry is not successful until its retained directory is durably observed."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    state = _state()
    assert store.compare_and_set(None, state).created is True

    def fail_fsync(_descriptor: int) -> None:
        message = "injected adoption fsync failure"
        raise OSError(message)

    monkeypatch.setattr(predecessor.os, "fsync", fail_fsync)
    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_IO"):
        store.compare_and_set(None, state)


def test_closed_store_rejects_future_operations(tmp_path: Path) -> None:
    """Lifecycle close revokes the descriptor rather than allowing accidental reuse."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    store.close()

    with pytest.raises(DueCyclePredecessorError, match="DUE_PREDECESSOR_CLOSED"):
        store.load(DueCycleKind.DAILY_CURRENT_LAW)


def test_process_divergent_writers_leave_one_retained_current_state(tmp_path: Path) -> None:
    """Cross-process CAS allows only one competing initial publication to become current."""
    context = get_context("fork")
    queue = context.Queue()
    first = context.Process(
        target=_process_divergent_write,
        args=(str(tmp_path), "hk-v1-daily-one-20260826", "one", queue),
    )
    second = context.Process(
        target=_process_divergent_write,
        args=(str(tmp_path), "hk-v1-daily-two-20260826", "two", queue),
    )
    first.start()
    second.start()
    first.join()
    second.join()

    outcomes = sorted([queue.get(timeout=1), queue.get(timeout=1)])
    assert outcomes[0][0] == "conflict"
    assert outcomes[1][0] == "created"
    retained = LocalDueCyclePredecessorStore(tmp_path).load(DueCycleKind.DAILY_CURRENT_LAW)
    assert retained is not None
    assert retained.instruction.cycle_id == outcomes[1][1]


def test_noop_replace_cannot_acknowledge_or_leave_its_owned_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mocked or broken replacement that retained nothing cannot report a created state."""
    store = LocalDueCyclePredecessorStore(tmp_path)

    def noop_replace(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(predecessor.os, "replace", noop_replace)
    with pytest.raises(DueCyclePredecessorError):
        store.compare_and_set(None, _state())

    assert store.load(DueCycleKind.DAILY_CURRENT_LAW) is None
    assert not list(tmp_path.glob(".daily-current-law.json.*.tmp"))


def test_wrong_target_replace_cannot_acknowledge_a_missing_fixed_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacement must make the fixed kind path readable, not merely move bytes somewhere."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    original_replace = predecessor.os.replace

    def wrong_target(source: str, _target: str, *args: object, **kwargs: object) -> None:
        original_replace(source, "unrelated.json", *args, **kwargs)

    monkeypatch.setattr(predecessor.os, "replace", wrong_target)
    with pytest.raises(DueCyclePredecessorError):
        store.compare_and_set(None, _state())

    assert store.load(DueCycleKind.DAILY_CURRENT_LAW) is None
    assert not list(tmp_path.glob(".daily-current-law.json.*.tmp"))


def test_post_replace_tamper_cannot_acknowledge_unreadable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The created receipt follows strict fixed-path readback, not a successful syscall alone."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    original_replace = predecessor.os.replace

    def replace_then_tamper(source: str, target: str, *args: object, **kwargs: object) -> None:
        original_replace(source, target, *args, **kwargs)
        (tmp_path / "daily-current-law.json").write_bytes(b"not canonical predecessor state")

    monkeypatch.setattr(predecessor.os, "replace", replace_then_tamper)
    with pytest.raises(DueCyclePredecessorError):
        store.compare_and_set(None, _state())

    assert not list(tmp_path.glob(".daily-current-law.json.*.tmp"))


def test_concurrent_identical_writers_create_once_and_adopt_once(tmp_path: Path) -> None:
    """The per-kind flock makes concurrent lost-ack retries deterministic."""
    state = _state()
    barrier = Barrier(2)
    created: list[bool] = []

    def write() -> None:
        store = LocalDueCyclePredecessorStore(tmp_path)
        barrier.wait()
        created.append(store.compare_and_set(None, state).created)

    first = Thread(target=write)
    second = Thread(target=write)
    first.start()
    second.start()
    first.join()
    second.join()
    assert sorted(created) == [False, True]


def test_replace_failure_removes_temporary_file_and_releases_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed pre-replace write leaves neither a provisional state nor stale temp."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    original_replace = predecessor.os.replace

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        message = "injected"
        raise OSError(message)

    monkeypatch.setattr(predecessor.os, "replace", fail_replace)
    with pytest.raises(DueCyclePredecessorError):
        store.compare_and_set(None, _state())
    assert not list(tmp_path.glob(".daily-current-law.json.*.tmp"))
    monkeypatch.setattr(predecessor.os, "replace", original_replace)
    assert store.compare_and_set(None, _state()).created is True


def test_process_identical_writers_create_once_and_adopt_once(tmp_path: Path) -> None:
    """The advisory lock is cross-process, not merely a thread mutex."""
    context = get_context("fork")
    queue = context.Queue()
    first = context.Process(target=_process_write, args=(str(tmp_path), queue))
    second = context.Process(target=_process_write, args=(str(tmp_path), queue))
    first.start()
    second.start()
    first.join()
    second.join()
    assert (first.exitcode, second.exitcode) == (0, 0)
    assert sorted([queue.get(timeout=1), queue.get(timeout=1)]) == [False, True]


@pytest.mark.parametrize("failure", ["write", "fsync-file", "fsync-directory"])
def test_atomic_write_failures_leave_store_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Each pre-ack atomic-write failure leaves no false predecessor success."""
    store = LocalDueCyclePredecessorStore(tmp_path)
    original_write = predecessor.os.write
    original_fsync = predecessor.os.fsync

    def fail_write(*_args: object, **_kwargs: object) -> int:
        return 0

    calls = 0

    def fail_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if failure == "fsync-file" or calls > 1:
            message = "injected"
            raise OSError(message)
        original_fsync(descriptor)

    if failure == "write":
        monkeypatch.setattr(predecessor.os, "write", fail_write)
    else:
        monkeypatch.setattr(predecessor.os, "fsync", fail_fsync)
    with pytest.raises(DueCyclePredecessorError):
        store.compare_and_set(None, _state())
    monkeypatch.setattr(predecessor.os, "write", original_write)
    monkeypatch.setattr(predecessor.os, "fsync", original_fsync)
    assert store.compare_and_set(None, _state()).created is (failure != "fsync-directory")
