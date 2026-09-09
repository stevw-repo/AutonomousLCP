"""Immutable acquisition-journal and derived-checkpoint proofs."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import asklegal_acquisition_worker.acquisition_journal as acquisition_journal_model
import pytest
from asklegal_acquisition_worker.acquisition_journal import (
    AccountedExcludedPayload,
    AcquisitionCheckpoint,
    AcquisitionCycleResult,
    AcquisitionFailureCode,
    AcquisitionJournalEntry,
    AcquisitionJournalError,
    AuthorizationRejectedPayload,
    CapturedVerifiedPayload,
    CheckpointItem,
    ContractRejectedPayload,
    CycleSafetyProfilePayload,
    DiscoveredPayload,
    ElapsedBudgetExhaustedPayload,
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    RetryableFailurePayload,
    RetryExhaustedPayload,
    StartedPayload,
    TerminalUnavailablePayload,
    TransportStartedPayload,
    WorkItemIdentity,
)
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

_ZERO_FINGERPRINT = "sha256:" + "0" * 64
_CYCLE_STARTED_AT_EPOCH_US = 1_777_766_400_000_000


def _item(*, parent_id: str = "year-2011", page: int = 364) -> WorkItemIdentity:
    return WorkItemIdentity.issue(
        source_family="CASES",
        source_role="HK-CASE-JUDICIARY-LRS-INVENTORY",
        cycle_id="cyc_20260902_cases",
        observation_cutoff="2026-09-02T10:33:42+08:00",
        procedure_version="JUDICIARY_RESULT_1.0.12",
        locator=(
            f"https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?page={page}"
        ),
        stage="LISTING_PAGE",
        parent_id=parent_id,
        media_type="text/html",
        max_bytes=16_777_216,
    )


def _journal(tmp_path: Path) -> LocalAcquisitionJournal:
    return LocalAcquisitionJournal(tmp_path / "cycle-state", "cyc_20260902_cases")


def _captured(
    *, attempt: int = 1, object_ref: str = "objects/sha256/abc"
) -> CapturedVerifiedPayload:
    return CapturedVerifiedPayload(
        attempt=attempt,
        status=200,
        media_type="text/html",
        final_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?page=364"
        ),
        redirect_chain=(),
        body_length=4_096,
        content_fingerprint="sha256:" + "a" * 64,
        object_ref=object_ref,
        read_back_verified=True,
    )


def _imported() -> ImportedCaptureVerifiedPayload:
    return ImportedCaptureVerifiedPayload(
        source_attempt_id="hkel-live-baseline-basic-law20-20260828b",
        source_report_fingerprint="sha256:" + "b" * 64,
        authority_manifest_fingerprint="sha256:" + "c" * 64,
        execution_authorization_fingerprint="sha256:" + "d" * 64,
        status=200,
        media_type="text/html",
        final_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?page=363"
        ),
        body_length=4_096,
        content_fingerprint="sha256:" + "a" * 64,
        object_ref="objects/sha256/retained",
        read_back_verified=True,
    )


def _profile(  # noqa: PLR0913 - test helper exposes every independently varied profile fact.
    *,
    cycle_started_at_epoch_us: int = _CYCLE_STARTED_AT_EPOCH_US,
    maximum_starts: int = 100,
    maximum_retained_bytes: int = 16_777_216,
    maximum_elapsed_seconds: int = 60,
    maximum_redirects: int = 100,
    per_host_limit: int = 4,
    minimum_start_interval_ns: int = 1_000_000_000,
    maximum_attempts_per_item: int = 2,
    maximum_redirects_per_start: int = 1,
) -> CycleSafetyProfilePayload:
    return CycleSafetyProfilePayload(
        schema_id="asklegal.acquisition-cycle-safety-profile",
        schema_version="1.0.0",
        maximum_starts=maximum_starts,
        maximum_retained_bytes=maximum_retained_bytes,
        maximum_elapsed_seconds=maximum_elapsed_seconds,
        maximum_redirects=maximum_redirects,
        per_host_limit=per_host_limit,
        minimum_start_interval_ns=minimum_start_interval_ns,
        maximum_attempts_per_item=maximum_attempts_per_item,
        maximum_redirects_per_start=maximum_redirects_per_start,
        cycle_started_at_epoch_us=cycle_started_at_epoch_us,
    )


def _started(
    attempt: int = 1,
    *,
    cycle_started_at_epoch_us: int = _CYCLE_STARTED_AT_EPOCH_US,
    reserved_redirects: int = 1,
) -> StartedPayload:
    return StartedPayload(
        attempt=attempt,
        started_at_epoch_us=cycle_started_at_epoch_us,
        host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
        reserved_redirects=reserved_redirects,
    )


def _transport_started(
    attempt: int = 1,
    *,
    cycle_started_at_epoch_us: int = _CYCLE_STARTED_AT_EPOCH_US,
) -> TransportStartedPayload:
    return TransportStartedPayload(
        attempt=attempt,
        started_at_epoch_us=cycle_started_at_epoch_us,
        host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
    )


def _append_modern_prefix(
    journal: LocalAcquisitionJournal,
    item: WorkItemIdentity,
    *,
    profile: CycleSafetyProfilePayload | None = None,
) -> None:
    selected = profile or _profile()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(selected.cycle_started_at_epoch_us),
    )
    journal.append(item, JournalTransition.CYCLE_SAFETY_PROFILE_BOUND, selected)


def _read_document(path: Path) -> dict[str, JsonValue]:
    document = parse_json_bytes(path.read_bytes(), max_bytes=16_777_216)
    if not isinstance(document, dict) or type(document) is not dict:
        raise AssertionError
    return document


def _write_document(path: Path, document: dict[str, JsonValue]) -> None:
    path.write_bytes(canonicalize(checked_json_value(document)))


def _refingerprint(document: dict[str, JsonValue]) -> None:
    body = {key: value for key, value in document.items() if key != "fingerprint"}
    document["fingerprint"] = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"


def _compact_payload(payload_type: type[DiscoveredPayload | StartedPayload]) -> object:
    """Create hostile pre-modern payload state without relying on its public constructor."""
    payload = object.__new__(payload_type)
    if payload_type is DiscoveredPayload:
        object.__setattr__(payload, "cycle_started_at_epoch_us", None)
    else:
        object.__setattr__(payload, "attempt", 1)
        object.__setattr__(payload, "started_at_epoch_us", None)
        object.__setattr__(payload, "host_not_before_epoch_us", None)
        object.__setattr__(payload, "reserved_redirects", 0)
    return payload


def _construct(constructor: Callable[..., object], **kwargs: object) -> object:
    """Invoke a constructor dynamically so runtime rejection remains under direct test."""
    return constructor(**kwargs)


def test_work_item_identity_is_stable_and_rejects_fact_drift() -> None:
    """Changing a request fact without changing its ID must fail at every object boundary."""
    item = _item()

    assert item.work_item_id.startswith("awi_")
    assert WorkItemIdentity.from_json(item.to_json()) == item
    with pytest.raises(AcquisitionJournalError, match="WORK_ITEM_INVALID"):
        replace(item, locator=item.locator + "&drift=1")
    hostile = item.to_json()
    hostile["locator"] = item.locator + "&drift=1"
    with pytest.raises(AcquisitionJournalError, match="WORK_ITEM_INVALID"):
        WorkItemIdentity.from_json(hostile)


def test_closed_types_reject_unknown_fields_values_and_bool_integers() -> None:
    """Permissive JSON or truthy integers would make replay disagree with direct construction."""
    item = _item()
    entry = AcquisitionJournalEntry.issue(
        sequence=1,
        previous_entry_fingerprint=_ZERO_FINGERPRINT,
        work_item=item,
        transition=JournalTransition.DISCOVERED,
        payload=DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
    )
    unknown = entry.to_json()
    unknown["unknown"] = "FORGED"
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ENTRY_INVALID"):
        AcquisitionJournalEntry.from_json(unknown)
    invalid_transition = entry.to_json()
    invalid_transition["transition"] = "CAPTURED"
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ENTRY_INVALID"):
        AcquisitionJournalEntry.from_json(invalid_transition)
    hostile_payload = entry.to_json()
    hostile_payload["payload"] = {"attempt": 1}
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ENTRY_INVALID"):
        AcquisitionJournalEntry.from_json(hostile_payload)
    started = AcquisitionJournalEntry.issue(
        sequence=1,
        previous_entry_fingerprint=_ZERO_FINGERPRINT,
        work_item=item,
        transition=JournalTransition.STARTED,
        payload=_started(),
    ).to_json()
    started_payload = started["payload"]
    assert isinstance(started_payload, dict)
    started_payload["attempt"] = True
    _refingerprint(started)
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ENTRY_INVALID"):
        AcquisitionJournalEntry.from_json(started)


def test_direct_dataclass_construction_enforces_the_parsed_invariants() -> None:
    """Object construction must not be a weaker path than canonical JSON parsing."""
    item = _item()
    entry = AcquisitionJournalEntry.issue(
        sequence=1,
        previous_entry_fingerprint=_ZERO_FINGERPRINT,
        work_item=item,
        transition=JournalTransition.DISCOVERED,
        payload=DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
    )
    with pytest.raises(AcquisitionJournalError, match="TRANSITION_PAYLOAD_INVALID"):
        StartedPayload(
            attempt=True,
            started_at_epoch_us=_CYCLE_STARTED_AT_EPOCH_US,
            host_not_before_epoch_us=_CYCLE_STARTED_AT_EPOCH_US + 1_000_000,
            reserved_redirects=1,
        )
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ENTRY_INVALID"):
        replace(entry, sequence=True)
    with pytest.raises(AcquisitionJournalError, match="CHECKPOINT_INVALID"):
        CheckpointItem(
            work_item_id=item.work_item_id,
            latest_sequence=True,
            transition=JournalTransition.DISCOVERED,
            attempt_count=0,
            object_ref=None,
            retry_not_before=None,
        )
    with pytest.raises(AcquisitionJournalError, match="CHECKPOINT_INVALID"):
        AcquisitionCheckpoint(
            cycle_id=item.cycle_id,
            through_sequence=0,
            journal_head_fingerprint=_ZERO_FINGERPRINT,
            items=(),
            fingerprint="sha256:" + "1" * 64,
        )


def test_compact_scheduler_payloads_reject_direct_construction() -> None:
    """Restoring either compact constructor would reopen unproved timing state."""
    with pytest.raises(TypeError):
        _construct(DiscoveredPayload)
    with pytest.raises(TypeError):
        _construct(StartedPayload, attempt=1)


@pytest.mark.parametrize(
    ("transition", "payload"),
    [
        (JournalTransition.DISCOVERED, {}),
        (JournalTransition.STARTED, {"attempt": 1}),
    ],
)
def test_compact_scheduler_payloads_reject_json(
    transition: JournalTransition,
    payload: dict[str, JsonValue],
) -> None:
    """The exact entry parser cannot retain either pre-modern payload shape."""
    item = _item()
    modern_payload: DiscoveredPayload | StartedPayload = (
        DiscoveredPayload(cycle_started_at_epoch_us=1_777_766_400_000_000)
        if transition is JournalTransition.DISCOVERED
        else StartedPayload(
            attempt=1,
            started_at_epoch_us=1_777_766_400_000_000,
            host_not_before_epoch_us=1_777_766_401_000_000,
            reserved_redirects=1,
        )
    )
    document = AcquisitionJournalEntry.issue(
        sequence=1,
        previous_entry_fingerprint=_ZERO_FINGERPRINT,
        work_item=item,
        transition=transition,
        payload=modern_payload,
    ).to_json()
    document["payload"] = payload
    _refingerprint(document)

    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ENTRY_INVALID"):
        AcquisitionJournalEntry.from_json(document)


@pytest.mark.parametrize(
    ("transition", "payload_type"),
    [
        (JournalTransition.DISCOVERED, DiscoveredPayload),
        (JournalTransition.STARTED, StartedPayload),
    ],
)
def test_compact_scheduler_payloads_reject_journal_append(
    tmp_path: Path,
    transition: JournalTransition,
    payload_type: type[DiscoveredPayload | StartedPayload],
) -> None:
    """Bypassing a frozen constructor cannot append compact state to a modern journal."""
    journal = _journal(tmp_path)
    if transition is JournalTransition.STARTED:
        cycle_started_at_epoch_us = 1_777_766_400_000_000
        item = _item()
        journal.append(
            item,
            JournalTransition.DISCOVERED,
            DiscoveredPayload(cycle_started_at_epoch_us),
        )
        journal.append(
            item,
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            CycleSafetyProfilePayload(
                schema_id="asklegal.acquisition-cycle-safety-profile",
                schema_version="1.0.0",
                maximum_starts=2,
                maximum_retained_bytes=16_777_216,
                maximum_elapsed_seconds=60,
                maximum_redirects=2,
                per_host_limit=1,
                minimum_start_interval_ns=1_000_000_000,
                maximum_attempts_per_item=2,
                maximum_redirects_per_start=1,
                cycle_started_at_epoch_us=cycle_started_at_epoch_us,
            ),
        )
    else:
        item = _item()
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ENTRY_INVALID"):
        journal.append(item, transition, _compact_payload(payload_type))


def test_cycle_profile_rejects_removed_migration_constructor_fields() -> None:
    """Reintroducing migration metadata would make profile bytes schema-ambiguous."""
    with pytest.raises(TypeError):
        _construct(
            CycleSafetyProfilePayload,
            schema_id="asklegal.acquisition-cycle-safety-profile",
            schema_version="1.0.0",
            maximum_starts=2,
            maximum_retained_bytes=16_777_216,
            maximum_elapsed_seconds=60,
            maximum_redirects=2,
            per_host_limit=1,
            minimum_start_interval_ns=1_000_000_000,
            maximum_attempts_per_item=2,
            maximum_redirects_per_start=1,
            cycle_started_at_epoch_us=1_777_766_400_000_000,
            legacy_through_sequence=0,
            legacy_journal_head_fingerprint=_ZERO_FINGERPRINT,
            legacy_host_not_before_epoch_us=None,
        )


def test_cycle_profile_rejects_removed_migration_json_fields() -> None:
    """Historical migration keys cannot survive as accepted modern profile bytes."""
    cycle_started_at_epoch_us = 1_777_766_400_000_000
    document = AcquisitionJournalEntry.issue(
        sequence=1,
        previous_entry_fingerprint=_ZERO_FINGERPRINT,
        work_item=_item(),
        transition=JournalTransition.DISCOVERED,
        payload=DiscoveredPayload(cycle_started_at_epoch_us),
    ).to_json()
    document["transition"] = JournalTransition.CYCLE_SAFETY_PROFILE_BOUND.value
    document["payload"] = {
        "schema_id": "asklegal.acquisition-cycle-safety-profile",
        "schema_version": "1.0.0",
        "maximum_starts": 2,
        "maximum_retained_bytes": 16_777_216,
        "maximum_elapsed_seconds": 60,
        "maximum_redirects": 2,
        "per_host_limit": 1,
        "minimum_start_interval_ns": 1_000_000_000,
        "maximum_attempts_per_item": 2,
        "maximum_redirects_per_start": 1,
        "cycle_started_at_epoch_us": cycle_started_at_epoch_us,
        "legacy_through_sequence": 0,
        "legacy_journal_head_fingerprint": _ZERO_FINGERPRINT,
        "legacy_host_not_before_epoch_us": None,
    }
    _refingerprint(document)

    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ENTRY_INVALID"):
        AcquisitionJournalEntry.from_json(document)


def test_modern_started_requires_a_bound_profile_on_append(tmp_path: Path) -> None:
    """Any pre-profile request start lacks the immutable controls needed to prove admission."""
    cycle_started_at_epoch_us = 1_777_766_400_000_000
    item = _item()
    started_payload = StartedPayload(
        attempt=1,
        started_at_epoch_us=cycle_started_at_epoch_us,
        host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
        reserved_redirects=1,
    )
    append_journal = _journal(tmp_path / "append")
    append_journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(cycle_started_at_epoch_us),
    )
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        append_journal.append(item, JournalTransition.STARTED, started_payload)


def test_modern_started_requires_a_bound_profile_on_replay(tmp_path: Path) -> None:
    """Raw modern starts cannot bypass the immutable pre-start safety profile."""
    cycle_started_at_epoch_us = 1_777_766_400_000_000
    item = _item()
    started_payload = StartedPayload(
        attempt=1,
        started_at_epoch_us=cycle_started_at_epoch_us,
        host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
        reserved_redirects=1,
    )
    replay_root = tmp_path / "replay"
    replay_journal = _journal(replay_root)
    discovered = AcquisitionJournalEntry.issue(
        sequence=1,
        previous_entry_fingerprint=_ZERO_FINGERPRINT,
        work_item=item,
        transition=JournalTransition.DISCOVERED,
        payload=DiscoveredPayload(cycle_started_at_epoch_us),
    )
    started = AcquisitionJournalEntry.issue(
        sequence=2,
        previous_entry_fingerprint=discovered.fingerprint,
        work_item=item,
        transition=JournalTransition.STARTED,
        payload=started_payload,
    )
    entries = replay_root / "cycle-state" / "acquisition-journals" / item.cycle_id / "entries"
    _write_document(entries / "00000000000000000001.json", discovered.to_json())
    _write_document(entries / "00000000000000000002.json", started.to_json())
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_REPLAY_INVALID"):
        replay_journal.replay()


@pytest.mark.parametrize(
    ("transition", "attempt_count"),
    [
        (JournalTransition.DISCOVERED, 1),
        (JournalTransition.STARTED, 0),
    ],
)
def test_checkpoint_item_rejects_impossible_transition_attempt_state(
    transition: JournalTransition,
    attempt_count: int,
) -> None:
    """Removing transition-specific attempt checks must fail at object and JSON boundaries."""
    item = _item()
    with pytest.raises(AcquisitionJournalError, match="CHECKPOINT_INVALID"):
        CheckpointItem(
            work_item_id=item.work_item_id,
            latest_sequence=1,
            transition=transition,
            attempt_count=attempt_count,
            object_ref=None,
            retry_not_before=None,
        )
    document: dict[str, JsonValue] = {
        "work_item_id": item.work_item_id,
        "latest_sequence": 1,
        "transition": transition.value,
        "attempt_count": attempt_count,
        "object_ref": None,
        "retry_not_before": None,
    }
    with pytest.raises(AcquisitionJournalError, match="CHECKPOINT_INVALID"):
        CheckpointItem.from_json(document)


@pytest.mark.parametrize("attack", ["LATEST_AFTER_HEAD", "NONEMPTY_WITHOUT_ITEMS"])
def test_checkpoint_rejects_impossible_replay_sequence_relationships(attack: str) -> None:
    """Removing journal/item sequence relations must fail for issue, construction, and parse."""
    item = _item()
    checkpoint_item = CheckpointItem(
        work_item_id=item.work_item_id,
        latest_sequence=2 if attack == "LATEST_AFTER_HEAD" else 1,
        transition=JournalTransition.DISCOVERED,
        attempt_count=0,
        object_ref=None,
        retry_not_before=None,
    )
    items = (checkpoint_item,) if attack == "LATEST_AFTER_HEAD" else ()
    through_sequence = 1
    head = "sha256:" + "b" * 64
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.acquisition-checkpoint",
        "schema_version": "1.0.0",
        "cycle_id": item.cycle_id,
        "through_sequence": through_sequence,
        "journal_head_fingerprint": head,
        "items": [checkpoint_item.to_json() for checkpoint_item in items],
    }
    fingerprint = f"sha256:{sha256(canonicalize(body)).hexdigest()}"

    with pytest.raises(AcquisitionJournalError, match="CHECKPOINT_INVALID"):
        AcquisitionCheckpoint.issue(
            cycle_id=item.cycle_id,
            through_sequence=through_sequence,
            journal_head_fingerprint=head,
            items=items,
        )
    with pytest.raises(AcquisitionJournalError, match="CHECKPOINT_INVALID"):
        AcquisitionCheckpoint(
            cycle_id=item.cycle_id,
            through_sequence=through_sequence,
            journal_head_fingerprint=head,
            items=items,
            fingerprint=fingerprint,
        )
    document = {**body, "fingerprint": fingerprint}
    with pytest.raises(AcquisitionJournalError, match="CHECKPOINT_INVALID"):
        AcquisitionCheckpoint.from_json(document)


def test_append_hash_chains_entries_and_replays_exact_interrupted_started_state(
    tmp_path: Path,
) -> None:
    """A process loss after STARTED must retain an exact unfinished state for resumption."""
    journal = _journal(tmp_path)
    item = _item()

    discovered = journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
    )
    profile = journal.append(
        item,
        JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
        _profile(),
    )
    started = journal.append(item, JournalTransition.STARTED, _started())

    assert discovered.sequence == 1
    assert discovered.previous_entry_fingerprint == _ZERO_FINGERPRINT
    assert profile.sequence == 2
    assert profile.previous_entry_fingerprint == discovered.fingerprint
    assert started.sequence == 3
    assert started.previous_entry_fingerprint == profile.fingerprint
    assert journal.replay() == (discovered, profile, started)
    checkpoint = journal.write_checkpoint()
    assert checkpoint == journal.load_checkpoint()
    assert checkpoint.items[0].transition is JournalTransition.STARTED
    assert checkpoint.items[0].attempt_count == 1


def test_append_enforces_started_attempt_and_one_terminal_disposition(tmp_path: Path) -> None:
    """Outcomes without STARTED and a second terminal would create false or ambiguous state."""
    journal = _journal(tmp_path)
    item = _item()
    _append_modern_prefix(journal, item)
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        journal.append(item, JournalTransition.CAPTURED_VERIFIED, _captured())
    journal.append(item, JournalTransition.STARTED, _started())
    journal.append(item, JournalTransition.TRANSPORT_STARTED, _transport_started())
    journal.append(item, JournalTransition.CAPTURED_VERIFIED, _captured())
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        journal.append(
            item,
            JournalTransition.TERMINAL_UNAVAILABLE,
            TerminalUnavailablePayload(
                attempt=1,
                failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE,
            ),
        )


def test_retry_requires_monotonic_attempts_and_preserves_retry_time(tmp_path: Path) -> None:
    """Attempt drift would let a resumed request overwrite the scheduler's retry history."""
    journal = _journal(tmp_path)
    item = _item()
    _append_modern_prefix(journal, item)
    journal.append(item, JournalTransition.STARTED, _started())
    journal.append(item, JournalTransition.TRANSPORT_STARTED, _transport_started())
    journal.append(
        item,
        JournalTransition.RETRYABLE_FAILURE,
        RetryableFailurePayload(
            attempt=1,
            failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE,
            retry_not_before="2026-09-02T10:35:00+08:00",
        ),
    )
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        journal.append(item, JournalTransition.STARTED, _started(3))
    journal.append(item, JournalTransition.STARTED, _started(2))
    checkpoint = journal.write_checkpoint()
    assert checkpoint.items[0].attempt_count == 2
    assert checkpoint.items[0].retry_not_before is None


@pytest.mark.parametrize(
    "payload",
    [
        ContractRejectedPayload(
            attempt=1,
            failure_code=AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED,
        ),
        TerminalUnavailablePayload(
            attempt=1,
            failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE,
        ),
    ],
)
def test_terminal_failure_payloads_round_trip_exactly(payload: object) -> None:
    """Terminal failure categories must remain closed and recoverable across JSON replay."""
    transition = (
        JournalTransition.CONTRACT_REJECTED
        if type(payload) is ContractRejectedPayload
        else JournalTransition.TERMINAL_UNAVAILABLE
    )
    entry = AcquisitionJournalEntry.issue(
        sequence=3,
        previous_entry_fingerprint="sha256:" + "1" * 64,
        work_item=_item(),
        transition=transition,
        payload=payload,
    )
    assert AcquisitionJournalEntry.from_json(entry.to_json()) == entry


def test_worker_interruption_is_closed_retryable_only() -> None:
    """An orphaned physical start must not be relabeled as a timeout or terminal outage."""
    retryable = RetryableFailurePayload(
        attempt=1,
        failure_code=AcquisitionFailureCode.WORKER_INTERRUPTED,
        retry_not_before="2026-09-02T10:35:00+08:00",
    )
    entry = AcquisitionJournalEntry.issue(
        sequence=3,
        previous_entry_fingerprint="sha256:" + "1" * 64,
        work_item=_item(),
        transition=JournalTransition.RETRYABLE_FAILURE,
        payload=retryable,
    )
    assert AcquisitionJournalEntry.from_json(entry.to_json()).payload == retryable
    with pytest.raises(AcquisitionJournalError, match="TRANSITION_PAYLOAD_INVALID"):
        TerminalUnavailablePayload(
            attempt=1,
            failure_code=AcquisitionFailureCode.WORKER_INTERRUPTED,
        )


@pytest.mark.parametrize(
    ("retry_not_before", "expectation"),
    [
        ("2026-09-02T00:00:00.999999+00:00", "rejected"),
        ("2026-09-02T00:00:01+00:00", "accepted"),
        ("2026-09-02T00:00:01.000001+00:00", "accepted"),
    ],
)
def test_marker_free_modern_interruption_cannot_retry_before_started_host_floor(
    tmp_path: Path,
    retry_not_before: str,
    expectation: str,
) -> None:
    """Removing the exact modern floor check must admit the one-microsecond forgery."""
    cycle_started_at_epoch_us = 1_788_307_200_000_000
    case = tmp_path / retry_not_before.replace(":", "_")
    journal = _journal(case)
    item = _item()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(cycle_started_at_epoch_us),
    )
    journal.append(
        item,
        JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
        CycleSafetyProfilePayload(
            schema_id="asklegal.acquisition-cycle-safety-profile",
            schema_version="1.0.0",
            maximum_starts=2,
            maximum_retained_bytes=16_777_216,
            maximum_elapsed_seconds=60,
            maximum_redirects=2,
            per_host_limit=1,
            minimum_start_interval_ns=1_000_000_000,
            maximum_attempts_per_item=2,
            maximum_redirects_per_start=1,
            cycle_started_at_epoch_us=cycle_started_at_epoch_us,
        ),
    )
    started = journal.append(
        item,
        JournalTransition.STARTED,
        StartedPayload(
            attempt=1,
            started_at_epoch_us=cycle_started_at_epoch_us,
            host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
            reserved_redirects=1,
        ),
    )
    payload = RetryableFailurePayload(
        attempt=1,
        failure_code=AcquisitionFailureCode.WORKER_INTERRUPTED,
        retry_not_before=retry_not_before,
    )
    if expectation == "accepted":
        appended = journal.append(item, JournalTransition.RETRYABLE_FAILURE, payload)
        assert journal.replay()[-1] == appended
        return

    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        journal.append(item, JournalTransition.RETRYABLE_FAILURE, payload)
    forged = AcquisitionJournalEntry.issue(
        sequence=4,
        previous_entry_fingerprint=started.fingerprint,
        work_item=item,
        transition=JournalTransition.RETRYABLE_FAILURE,
        payload=payload,
    )
    entry_path = (
        case
        / "cycle-state"
        / "acquisition-journals"
        / item.cycle_id
        / "entries"
        / "00000000000000000004.json"
    )
    _write_document(entry_path, forged.to_json())
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_REPLAY_INVALID"):
        journal.replay()


def test_proven_admission_failure_requires_the_started_retry_floor_and_no_marker(
    tmp_path: Path,
) -> None:
    """A marker-free no-transport disposition cannot forge an early retry or hide a call."""
    payload_type = acquisition_journal_model.AdmissionFailedBeforeTransportPayload
    transition = JournalTransition("ADMISSION_FAILED_BEFORE_TRANSPORT")
    cycle_started_at_epoch_us = 1_788_307_200_000_000
    item = _item()

    journal = _journal(tmp_path / "unmarked")
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(cycle_started_at_epoch_us),
    )
    journal.append(
        item,
        JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
        CycleSafetyProfilePayload(
            schema_id="asklegal.acquisition-cycle-safety-profile",
            schema_version="1.0.0",
            maximum_starts=1,
            maximum_retained_bytes=16_777_216,
            maximum_elapsed_seconds=60,
            maximum_redirects=1,
            per_host_limit=1,
            minimum_start_interval_ns=1_000_000_000,
            maximum_attempts_per_item=2,
            maximum_redirects_per_start=1,
            cycle_started_at_epoch_us=cycle_started_at_epoch_us,
        ),
    )
    journal.append(
        item,
        JournalTransition.STARTED,
        StartedPayload(
            attempt=1,
            started_at_epoch_us=cycle_started_at_epoch_us,
            host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
            reserved_redirects=1,
        ),
    )
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        journal.append(
            item,
            transition,
            payload_type(
                attempt=1,
                retry_not_before="2026-09-02T00:00:00.999999+00:00",
            ),
        )
    valid_payload = payload_type(
        attempt=1,
        retry_not_before="2026-09-02T00:00:01+00:00",
    )
    valid = journal.append(item, transition, valid_payload)
    assert AcquisitionJournalEntry.from_json(valid.to_json()).payload == valid_payload
    checkpoint = journal.write_checkpoint()
    assert checkpoint.items[0].transition is transition
    assert checkpoint.items[0].retry_not_before == valid_payload.retry_not_before

    marked = _journal(tmp_path / "marked")
    marked.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(cycle_started_at_epoch_us),
    )
    marked.append(
        item,
        JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
        CycleSafetyProfilePayload(
            schema_id="asklegal.acquisition-cycle-safety-profile",
            schema_version="1.0.0",
            maximum_starts=1,
            maximum_retained_bytes=16_777_216,
            maximum_elapsed_seconds=60,
            maximum_redirects=1,
            per_host_limit=1,
            minimum_start_interval_ns=1_000_000_000,
            maximum_attempts_per_item=2,
            maximum_redirects_per_start=1,
            cycle_started_at_epoch_us=cycle_started_at_epoch_us,
        ),
    )
    marked.append(
        item,
        JournalTransition.STARTED,
        StartedPayload(
            attempt=1,
            started_at_epoch_us=cycle_started_at_epoch_us,
            host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
            reserved_redirects=1,
        ),
    )
    marked.append(
        item,
        JournalTransition.TRANSPORT_STARTED,
        TransportStartedPayload(
            attempt=1,
            started_at_epoch_us=cycle_started_at_epoch_us,
            host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
        ),
    )
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        marked.append(item, transition, valid_payload)


def test_scheduler_durability_payloads_validate_direct_json_and_replay_state(
    tmp_path: Path,
) -> None:
    """Cycle clock, host pacing, and redirect reservation facts must survive replay exactly."""
    discovered = DiscoveredPayload(cycle_started_at_epoch_us=1_777_766_400_000_000)
    started = StartedPayload(
        attempt=1,
        started_at_epoch_us=1_777_766_400_000_000,
        host_not_before_epoch_us=1_777_766_401_000_000,
        reserved_redirects=2,
    )
    journal = _journal(tmp_path)
    item = _item()
    journal.append(item, JournalTransition.DISCOVERED, discovered)
    journal.append(
        item,
        JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
        _profile(maximum_redirects_per_start=2),
    )
    journal.append(item, JournalTransition.STARTED, started)

    replayed = journal.replay()
    assert replayed[0].payload == discovered
    assert AcquisitionJournalEntry.from_json(replayed[0].to_json()).payload == discovered
    assert replayed[2].payload == started
    assert AcquisitionJournalEntry.from_json(replayed[2].to_json()).payload == started

    with pytest.raises(AcquisitionJournalError, match="TRANSITION_PAYLOAD_INVALID"):
        DiscoveredPayload(cycle_started_at_epoch_us=True)
    with pytest.raises(AcquisitionJournalError, match="TRANSITION_PAYLOAD_INVALID"):
        StartedPayload(
            attempt=1,
            started_at_epoch_us=10,
            host_not_before_epoch_us=9,
            reserved_redirects=1,
        )
    with pytest.raises(AcquisitionJournalError, match="TRANSITION_PAYLOAD_INVALID"):
        StartedPayload(
            attempt=1,
            started_at_epoch_us=10,
            host_not_before_epoch_us=11,
            reserved_redirects=21,
        )


@pytest.mark.parametrize(
    ("transition", "payload", "result"),
    [
        (
            JournalTransition.AUTHORIZATION_REJECTED,
            AuthorizationRejectedPayload(attempt=1),
            AcquisitionCycleResult.AUTHORIZATION_FAILURE,
        ),
        (
            JournalTransition.RETRY_EXHAUSTED,
            RetryExhaustedPayload(attempt=1),
            AcquisitionCycleResult.RETRY_EXHAUSTED,
        ),
    ],
)
def test_authorization_and_retry_exhaustion_are_exact_terminal_replay_states(
    tmp_path: Path,
    transition: JournalTransition,
    payload: AuthorizationRejectedPayload | RetryExhaustedPayload,
    result: AcquisitionCycleResult,
) -> None:
    """Removing either terminal enum/payload must make durable stop reconstruction fail."""
    assert result.value in {"AUTHORIZATION_FAILURE", "RETRY_EXHAUSTED"}
    journal = _journal(tmp_path)
    item = _item()
    _append_modern_prefix(journal, item)
    journal.append(item, JournalTransition.STARTED, _started())
    journal.append(item, JournalTransition.TRANSPORT_STARTED, _transport_started())
    if transition is JournalTransition.RETRY_EXHAUSTED:
        journal.append(
            item,
            JournalTransition.RETRYABLE_FAILURE,
            RetryableFailurePayload(
                attempt=1,
                failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE,
                retry_not_before="2026-09-02T10:35:00+08:00",
            ),
        )
    entry = journal.append(item, transition, payload)

    assert AcquisitionJournalEntry.from_json(entry.to_json()).payload == payload
    checkpoint = journal.write_checkpoint()
    assert checkpoint.items[0].transition is transition
    assert checkpoint.items[0].attempt_count == 1


def test_worker_interruption_code_remains_exclusive_to_retryable_payload() -> None:
    """New terminal scheduler payloads must not broaden interruption categorization."""
    assert AuthorizationRejectedPayload(attempt=1).to_json() == {"attempt": 1}
    assert RetryExhaustedPayload(attempt=1).to_json() == {"attempt": 1}


def test_elapsed_budget_marker_preserves_captured_checkpoint_while_stopping_cycle(
    tmp_path: Path,
) -> None:
    """A cycle stop must be durable without erasing the verified item's disposition."""
    journal = _journal(tmp_path)
    item = _item()
    _append_modern_prefix(journal, item)
    journal.append(item, JournalTransition.STARTED, _started())
    journal.append(item, JournalTransition.TRANSPORT_STARTED, _transport_started())
    journal.append(item, JournalTransition.CAPTURED_VERIFIED, _captured())
    marker = journal.append(
        item,
        JournalTransition.ELAPSED_BUDGET_EXHAUSTED,
        ElapsedBudgetExhaustedPayload(maximum_elapsed_seconds=1),
    )

    assert AcquisitionJournalEntry.from_json(marker.to_json()).payload == marker.payload
    checkpoint = journal.write_checkpoint()
    assert checkpoint.items[0].transition is JournalTransition.CAPTURED_VERIFIED
    assert checkpoint.items[0].object_ref == "objects/sha256/abc"
    assert checkpoint.items[0].latest_sequence == marker.sequence
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        journal.append(
            item,
            JournalTransition.ELAPSED_BUDGET_EXHAUSTED,
            ElapsedBudgetExhaustedPayload(maximum_elapsed_seconds=1),
        )


def test_accounted_exclusion_is_terminal_without_a_started_request(tmp_path: Path) -> None:
    """A deliberately unrequested item may be accounted without inventing an attempt."""
    journal = _journal(tmp_path)
    item = _item()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
    )
    excluded = journal.append(
        item,
        JournalTransition.ACCOUNTED_EXCLUDED,
        AccountedExcludedPayload(reason_code="OUTSIDE_OBSERVATION_WINDOW"),
    )
    assert journal.write_checkpoint().items[0].latest_sequence == excluded.sequence


def test_replay_rejects_sequence_gap_predecessor_drift_and_body_object_mismatch(
    tmp_path: Path,
) -> None:
    """Filename order, digest lineage, and embedded work facts are all authoritative."""
    for attack in ("GAP", "PREDECESSOR", "WORK_ITEM"):
        root = tmp_path / attack.lower()
        journal = LocalAcquisitionJournal(root, "cyc_20260902_cases")
        item = _item()
        _append_modern_prefix(journal, item)
        entries = root / "acquisition-journals" / item.cycle_id / "entries"
        second = entries / "00000000000000000002.json"
        if attack == "GAP":
            second.rename(entries / "00000000000000000003.json")
        else:
            document = _read_document(second)
            if attack == "PREDECESSOR":
                document["previous_entry_fingerprint"] = "sha256:" + "f" * 64
            else:
                work_item = document["work_item"]
                assert isinstance(work_item, dict)
                work_item["locator"] = str(work_item["locator"]) + "&forged=1"
            _refingerprint(document)
            _write_document(second, document)
        with pytest.raises(AcquisitionJournalError, match="JOURNAL_REPLAY_INVALID"):
            journal.replay()


def test_replay_rejects_unknown_fields_invalid_transition_and_nonregular_entry(
    tmp_path: Path,
) -> None:
    """Hostile journal bytes and filesystem object types never become replay state."""
    for attack in ("UNKNOWN", "TRANSITION", "FIFO"):
        root = tmp_path / attack.lower()
        journal = LocalAcquisitionJournal(root, "cyc_20260902_cases")
        journal.append(
            _item(),
            JournalTransition.DISCOVERED,
            DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
        )
        entry_path = (
            root
            / "acquisition-journals"
            / "cyc_20260902_cases"
            / "entries"
            / "00000000000000000001.json"
        )
        if attack == "FIFO":
            entry_path.unlink()
            os.mkfifo(entry_path)
        else:
            document = _read_document(entry_path)
            if attack == "UNKNOWN":
                document["unknown"] = "FORGED"
            else:
                document["transition"] = "FORGED"
            _refingerprint(document)
            _write_document(entry_path, document)
        with pytest.raises(AcquisitionJournalError, match="JOURNAL_REPLAY_INVALID"):
            journal.replay()


def test_replay_rejects_a_forged_second_terminal_disposition(tmp_path: Path) -> None:
    """A valid hash chain cannot legitimize an invalid per-item lifecycle."""
    journal = _journal(tmp_path)
    item = _item()
    _append_modern_prefix(journal, item)
    journal.append(item, JournalTransition.STARTED, _started())
    journal.append(item, JournalTransition.TRANSPORT_STARTED, _transport_started())
    terminal = journal.append(item, JournalTransition.CAPTURED_VERIFIED, _captured())
    forged = AcquisitionJournalEntry.issue(
        sequence=6,
        previous_entry_fingerprint=terminal.fingerprint,
        work_item=item,
        transition=JournalTransition.TERMINAL_UNAVAILABLE,
        payload=TerminalUnavailablePayload(
            attempt=1,
            failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE,
        ),
    )
    path = (
        tmp_path
        / "cycle-state"
        / "acquisition-journals"
        / item.cycle_id
        / "entries"
        / "00000000000000000006.json"
    )
    _write_document(path, forged.to_json())
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_REPLAY_INVALID"):
        journal.replay()


@pytest.mark.parametrize("attack", ["SYMLINK_ROOT", "FILE_ROOT", "SYMLINK_CHILD"])
def test_journal_rejects_symlinked_or_non_directory_authority_roots(
    tmp_path: Path, attack: str
) -> None:
    """A filesystem alias or non-directory cannot choose journal authority."""
    root = tmp_path / "state"
    if attack == "SYMLINK_ROOT":
        target = tmp_path / "target"
        target.mkdir()
        root.symlink_to(target, target_is_directory=True)
    elif attack == "FILE_ROOT":
        root.write_text("not a directory", encoding="utf-8")
    else:
        root.mkdir()
        target = tmp_path / "journals-target"
        target.mkdir()
        (root / "acquisition-journals").symlink_to(target, target_is_directory=True)
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ROOT_INVALID"):
        LocalAcquisitionJournal(root, "cyc_20260902_cases")


@pytest.mark.parametrize("replaced", ["JOURNALS", "CYCLE", "ENTRIES"])
def test_pinned_journal_rejects_fixed_descendant_replacement_before_any_write(
    tmp_path: Path,
    replaced: str,
) -> None:
    """Dropping descendant identity checks must split one cycle into two valid authorities."""
    root = tmp_path / "cycle-state"
    journal = LocalAcquisitionJournal(root, "cyc_20260902_cases")
    item = _item()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
    )
    journals = root / "acquisition-journals"
    cycle = journals / item.cycle_id
    entries = cycle / "entries"
    replaced_path = {"JOURNALS": journals, "CYCLE": cycle, "ENTRIES": entries}[replaced]
    detached_path = replaced_path.with_name(replaced_path.name + "-detached")
    replaced_path.rename(detached_path)
    if replaced == "JOURNALS":
        (replaced_path / item.cycle_id / "entries").mkdir(parents=True)
    elif replaced == "CYCLE":
        (replaced_path / "entries").mkdir(parents=True)
    else:
        replaced_path.mkdir()
    detached_entries = (
        detached_path / item.cycle_id / "entries"
        if replaced == "JOURNALS"
        else detached_path / "entries"
        if replaced == "CYCLE"
        else detached_path
    )
    replacement_entries = root / "acquisition-journals" / item.cycle_id / "entries"
    detached_before = tuple(path.name for path in detached_entries.iterdir())
    replacement_before = tuple(path.name for path in replacement_entries.iterdir())

    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ROOT_INVALID"):
        journal.append(item, JournalTransition.STARTED, _started())
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ROOT_INVALID"):
        journal.replay()
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ROOT_INVALID"):
        journal.write_checkpoint()
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ROOT_INVALID"):
        journal.load_checkpoint()
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ALREADY_OPEN"):
        LocalAcquisitionJournal(root, item.cycle_id)

    assert tuple(path.name for path in detached_entries.iterdir()) == detached_before
    assert tuple(path.name for path in replacement_entries.iterdir()) == replacement_before
    assert not (detached_path / "checkpoint.json").exists()
    assert not (root / "acquisition-journals" / item.cycle_id / "checkpoint.json").exists()
    journal.close()


def test_bad_or_incomplete_checkpoint_is_discarded_and_rebuilt_from_journal(
    tmp_path: Path,
) -> None:
    """Checkpoint drift cannot hide any journal item or become durable authority."""
    journal = _journal(tmp_path)
    first = _item()
    second = _item(parent_id="year-2012", page=1)
    for item in (first, second):
        journal.append(
            item,
            JournalTransition.DISCOVERED,
            DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
        )
    expected = journal.write_checkpoint()
    checkpoint_path = (
        tmp_path / "cycle-state" / "acquisition-journals" / first.cycle_id / "checkpoint.json"
    )
    document = _read_document(checkpoint_path)
    items = document["items"]
    assert isinstance(items, list)
    document["items"] = items[:1]
    _refingerprint(document)
    _write_document(checkpoint_path, document)

    rebuilt = journal.load_checkpoint()

    assert rebuilt == expected
    assert AcquisitionCheckpoint.from_json(_read_document(checkpoint_path)) == expected


def test_checkpoint_object_drift_is_rebuilt_even_when_its_fingerprint_is_valid(
    tmp_path: Path,
) -> None:
    """A self-consistent stale checkpoint still cannot contradict replayed object state."""
    journal = _journal(tmp_path)
    item = _item()
    _append_modern_prefix(journal, item)
    journal.append(item, JournalTransition.STARTED, _started())
    journal.append(item, JournalTransition.TRANSPORT_STARTED, _transport_started())
    journal.append(item, JournalTransition.CAPTURED_VERIFIED, _captured())
    expected = journal.write_checkpoint()
    checkpoint_path = (
        tmp_path / "cycle-state" / "acquisition-journals" / item.cycle_id / "checkpoint.json"
    )
    document = _read_document(checkpoint_path)
    items = document["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    items[0]["object_ref"] = "objects/sha256/forged"
    _refingerprint(document)
    _write_document(checkpoint_path, document)

    assert journal.load_checkpoint() == expected


@pytest.mark.parametrize("attack", ["BAD_BYTES", "HEAD_DRIFT"])
def test_bad_checkpoint_bytes_or_head_are_rebuilt_from_the_valid_journal(
    tmp_path: Path,
    attack: str,
) -> None:
    """Trusting checkpoint bytes or a self-consistent wrong head must fail this regression."""
    journal = _journal(tmp_path)
    item = _item()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
    )
    expected = journal.write_checkpoint()
    checkpoint_path = (
        tmp_path / "cycle-state" / "acquisition-journals" / item.cycle_id / "checkpoint.json"
    )
    if attack == "BAD_BYTES":
        checkpoint_path.write_bytes(b"not-json")
    else:
        document = _read_document(checkpoint_path)
        document["journal_head_fingerprint"] = "sha256:" + "f" * 64
        _refingerprint(document)
        _write_document(checkpoint_path, document)

    assert journal.load_checkpoint() == expected
    assert AcquisitionCheckpoint.from_json(_read_document(checkpoint_path)) == expected


def test_bad_journal_fails_closed_even_when_a_valid_checkpoint_exists(tmp_path: Path) -> None:
    """Consulting the checkpoint before replay must never hide corrupted journal authority."""
    journal = _journal(tmp_path)
    item = _item()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
    )
    journal.write_checkpoint()
    checkpoint_path = (
        tmp_path / "cycle-state" / "acquisition-journals" / item.cycle_id / "checkpoint.json"
    )
    checkpoint_before = checkpoint_path.read_bytes()
    entry_path = (
        tmp_path
        / "cycle-state"
        / "acquisition-journals"
        / item.cycle_id
        / "entries"
        / "00000000000000000001.json"
    )
    document = _read_document(entry_path)
    document["unknown"] = "FORGED"
    _refingerprint(document)
    _write_document(entry_path, document)

    with pytest.raises(AcquisitionJournalError, match="JOURNAL_REPLAY_INVALID"):
        journal.load_checkpoint()
    assert checkpoint_path.read_bytes() == checkpoint_before


def test_append_rebuilds_an_object_origin_entry_before_trusting_it(tmp_path: Path) -> None:
    """Frozen dataclass mutation cannot bypass the same body and fingerprint checks as replay."""
    journal = _journal(tmp_path)
    item = _item()
    payload = DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US)
    object.__setattr__(item, "locator", item.locator + "&forged=1")
    with pytest.raises(AcquisitionJournalError, match="WORK_ITEM_INVALID"):
        journal.append(item, JournalTransition.DISCOVERED, payload)


def test_cycle_profile_and_physical_start_validate_direct_json_and_replay(
    tmp_path: Path,
) -> None:
    """Removing exact profile or physical-start facts must reopen unsafe resume behavior."""
    cycle_started_at_epoch_us = 1_777_766_400_000_000
    profile = CycleSafetyProfilePayload(
        schema_id="asklegal.acquisition-cycle-safety-profile",
        schema_version="1.0.0",
        maximum_starts=100,
        maximum_retained_bytes=100,
        maximum_elapsed_seconds=60,
        maximum_redirects=100,
        per_host_limit=4,
        minimum_start_interval_ns=1_000_000_000,
        maximum_attempts_per_item=2,
        maximum_redirects_per_start=1,
        cycle_started_at_epoch_us=cycle_started_at_epoch_us,
    )
    physical_start = TransportStartedPayload(
        attempt=1,
        started_at_epoch_us=cycle_started_at_epoch_us + 2_000_000,
        host_not_before_epoch_us=cycle_started_at_epoch_us + 3_000_000,
    )
    journal = _journal(tmp_path)
    item = _item()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(cycle_started_at_epoch_us),
    )
    bound = journal.append(
        item,
        JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
        profile,
    )
    journal.append(
        item,
        JournalTransition.STARTED,
        StartedPayload(
            attempt=1,
            started_at_epoch_us=cycle_started_at_epoch_us,
            host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
            reserved_redirects=1,
        ),
    )
    started = journal.append(
        item,
        JournalTransition.TRANSPORT_STARTED,
        physical_start,
    )

    assert AcquisitionJournalEntry.from_json(bound.to_json()).payload == profile
    assert AcquisitionJournalEntry.from_json(started.to_json()).payload == physical_start
    checkpoint = journal.write_checkpoint()
    assert checkpoint.items[0].transition is JournalTransition.STARTED
    assert checkpoint.items[0].attempt_count == 1
    assert AcquisitionCycleResult.INCOMPLETE_TERMINAL.value == "INCOMPLETE_TERMINAL"

    with pytest.raises(AcquisitionJournalError, match="TRANSITION_PAYLOAD_INVALID"):
        replace(profile, schema_version="2.0.0")
    with pytest.raises(AcquisitionJournalError, match="TRANSITION_PAYLOAD_INVALID"):
        replace(physical_start, host_not_before_epoch_us=cycle_started_at_epoch_us)


def test_cycle_profile_is_unique_and_matches_the_modern_discovery_origin(
    tmp_path: Path,
) -> None:
    """A cycle cannot bind two profiles or a profile for another discovery origin."""
    journal = _journal(tmp_path)
    item = _item()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
    )
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        journal.append(
            item,
            JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
            _profile(cycle_started_at_epoch_us=_CYCLE_STARTED_AT_EPOCH_US + 1),
        )
    profile = _profile()
    journal.append(item, JournalTransition.CYCLE_SAFETY_PROFILE_BOUND, profile)
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        journal.append(item, JournalTransition.CYCLE_SAFETY_PROFILE_BOUND, profile)


@pytest.mark.parametrize(
    ("transition", "payload"),
    [
        (JournalTransition.CAPTURED_VERIFIED, _captured()),
        (
            JournalTransition.RETRYABLE_FAILURE,
            RetryableFailurePayload(
                attempt=1,
                failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE,
                retry_not_before="2026-09-02T10:35:00+08:00",
            ),
        ),
        (
            JournalTransition.CONTRACT_REJECTED,
            ContractRejectedPayload(
                attempt=1,
                failure_code=AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED,
            ),
        ),
        (
            JournalTransition.TERMINAL_UNAVAILABLE,
            TerminalUnavailablePayload(
                attempt=1,
                failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE,
            ),
        ),
        (
            JournalTransition.AUTHORIZATION_REJECTED,
            AuthorizationRejectedPayload(attempt=1),
        ),
    ],
)
def test_modern_physical_outcome_requires_matching_transport_started_marker(
    tmp_path: Path,
    transition: JournalTransition,
    payload: object,
) -> None:
    """A modern admitted start cannot be forged directly into a physical outcome."""
    cycle_started_at_epoch_us = 1_777_766_400_000_000
    journal = _journal(tmp_path)
    item = _item()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(cycle_started_at_epoch_us),
    )
    journal.append(
        item,
        JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
        CycleSafetyProfilePayload(
            schema_id="asklegal.acquisition-cycle-safety-profile",
            schema_version="1.0.0",
            maximum_starts=2,
            maximum_retained_bytes=16_777_216,
            maximum_elapsed_seconds=60,
            maximum_redirects=2,
            per_host_limit=1,
            minimum_start_interval_ns=1_000_000_000,
            maximum_attempts_per_item=2,
            maximum_redirects_per_start=1,
            cycle_started_at_epoch_us=cycle_started_at_epoch_us,
        ),
    )
    journal.append(
        item,
        JournalTransition.STARTED,
        StartedPayload(
            attempt=1,
            started_at_epoch_us=cycle_started_at_epoch_us,
            host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
            reserved_redirects=1,
        ),
    )

    with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
        journal.append(item, transition, payload)


def test_forged_modern_retry_exhaustion_without_physical_marker_fails_replay(
    tmp_path: Path,
) -> None:
    """A forged retry and exhaustion pair cannot hide a missing modern physical marker."""
    cycle_started_at_epoch_us = 1_777_766_400_000_000
    journal = _journal(tmp_path)
    item = _item()
    journal.append(
        item,
        JournalTransition.DISCOVERED,
        DiscoveredPayload(cycle_started_at_epoch_us),
    )
    journal.append(
        item,
        JournalTransition.CYCLE_SAFETY_PROFILE_BOUND,
        CycleSafetyProfilePayload(
            schema_id="asklegal.acquisition-cycle-safety-profile",
            schema_version="1.0.0",
            maximum_starts=2,
            maximum_retained_bytes=16_777_216,
            maximum_elapsed_seconds=60,
            maximum_redirects=2,
            per_host_limit=1,
            minimum_start_interval_ns=1_000_000_000,
            maximum_attempts_per_item=1,
            maximum_redirects_per_start=1,
            cycle_started_at_epoch_us=cycle_started_at_epoch_us,
        ),
    )
    started = journal.append(
        item,
        JournalTransition.STARTED,
        StartedPayload(
            attempt=1,
            started_at_epoch_us=cycle_started_at_epoch_us,
            host_not_before_epoch_us=cycle_started_at_epoch_us + 1_000_000,
            reserved_redirects=1,
        ),
    )
    retry = AcquisitionJournalEntry.issue(
        sequence=4,
        previous_entry_fingerprint=started.fingerprint,
        work_item=item,
        transition=JournalTransition.RETRYABLE_FAILURE,
        payload=RetryableFailurePayload(
            attempt=1,
            failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE,
            retry_not_before="2026-09-02T10:35:00+08:00",
        ),
    )
    exhausted = AcquisitionJournalEntry.issue(
        sequence=5,
        previous_entry_fingerprint=retry.fingerprint,
        work_item=item,
        transition=JournalTransition.RETRY_EXHAUSTED,
        payload=RetryExhaustedPayload(attempt=1),
    )
    entries = tmp_path / "cycle-state" / "acquisition-journals" / item.cycle_id / "entries"
    _write_document(entries / "00000000000000000004.json", retry.to_json())
    _write_document(entries / "00000000000000000005.json", exhausted.to_json())

    with pytest.raises(AcquisitionJournalError, match="JOURNAL_REPLAY_INVALID"):
        journal.replay()


def test_offline_import_is_terminal_without_invented_transport(tmp_path: Path) -> None:
    """Offline evidence reaches a terminal checkpoint with zero attempts."""
    item = _item(page=363)
    imported = _imported()
    with _journal(tmp_path) as journal:
        _append_modern_prefix(journal, item)
        journal.append(item, JournalTransition.IMPORTED_CAPTURE_VERIFIED, imported)
        checkpoint = journal.write_checkpoint()

    assert checkpoint.items[0].transition is JournalTransition.IMPORTED_CAPTURE_VERIFIED
    assert checkpoint.items[0].attempt_count == 0
    assert checkpoint.items[0].object_ref == imported.object_ref


def test_offline_import_requires_profile_and_rejects_mutation(tmp_path: Path) -> None:
    """Imports require the modern cycle profile and exact read-back truth."""
    item = _item(page=363)
    imported = _imported()
    with _journal(tmp_path) as journal:
        journal.append(
            item,
            JournalTransition.DISCOVERED,
            DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
        )
        with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
            journal.append(item, JournalTransition.IMPORTED_CAPTURE_VERIFIED, imported)
        journal.append(item, JournalTransition.CYCLE_SAFETY_PROFILE_BOUND, _profile())
        with pytest.raises(AcquisitionJournalError, match="TRANSITION_PAYLOAD_INVALID"):
            replace(imported, read_back_verified=False)
        journal.append(item, JournalTransition.IMPORTED_CAPTURE_VERIFIED, imported)
        with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
            journal.append(item, JournalTransition.IMPORTED_CAPTURE_VERIFIED, imported)


def test_offline_import_payload_json_is_closed() -> None:
    """Unknown offline-import fields cannot enter the hash chain."""
    item = _item(page=363)
    entry = AcquisitionJournalEntry.issue(
        sequence=1,
        previous_entry_fingerprint=_ZERO_FINGERPRINT,
        work_item=item,
        transition=JournalTransition.IMPORTED_CAPTURE_VERIFIED,
        payload=_imported(),
    )
    assert AcquisitionJournalEntry.from_json(entry.to_json()) == entry
    hostile = entry.to_json()
    payload = hostile["payload"]
    assert type(payload) is dict
    payload["attempt"] = 0
    with pytest.raises(AcquisitionJournalError, match="JOURNAL_ENTRY_INVALID"):
        AcquisitionJournalEntry.from_json(hostile)


def test_append_many_validates_whole_batch_before_first_write(tmp_path: Path) -> None:
    """Batch publication cannot leave a prefix for a semantically invalid batch."""
    item = _item(page=363)
    with _journal(tmp_path) as journal:
        entries = journal.append_many(
            (
                (
                    item,
                    JournalTransition.DISCOVERED,
                    DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
                ),
                (item, JournalTransition.CYCLE_SAFETY_PROFILE_BOUND, _profile()),
                (item, JournalTransition.IMPORTED_CAPTURE_VERIFIED, _imported()),
            )
        )
        assert len(entries) == 3
        assert len(journal.replay()) == 3

    other = _item(page=362)
    with _journal(tmp_path / "invalid") as journal:
        with pytest.raises(AcquisitionJournalError, match="JOURNAL_TRANSITION_INVALID"):
            journal.append_many(
                (
                    (
                        other,
                        JournalTransition.DISCOVERED,
                        DiscoveredPayload(_CYCLE_STARTED_AT_EPOCH_US),
                    ),
                    (other, JournalTransition.IMPORTED_CAPTURE_VERIFIED, _imported()),
                )
            )
        assert journal.replay() == ()
