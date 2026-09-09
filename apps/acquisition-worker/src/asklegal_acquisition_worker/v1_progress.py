"""Read-only operator projection over retained Hong Kong V1 acquisition state."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Never

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_observability import (
    HKV1FamilyCycleResult,
    HKV1FamilyProgress,
    HKV1ProgressSnapshot,
    aggregate_hk_v1_progress,
    serialize_hk_v1_progress,
)

from asklegal_acquisition_worker.acquisition_journal import (
    AccountedExcludedPayload,
    CapturedVerifiedPayload,
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    RetainedAcquisitionJournalSnapshot,
    read_retained_acquisition_journal,
)
from asklegal_acquisition_worker.hk_cases_acquisition import CasesAcquisitionManifest
from asklegal_acquisition_worker.hk_legislation_acquisition import (
    LegislationAcquisitionManifest,
)
from asklegal_acquisition_worker.resumable_acquisition import semantic_journal_head

_MAX_RESULT_BYTES = 16_777_216
_UNAVAILABLE = "HK_V1_PROGRESS_UNAVAILABLE"
_SUCCESS = frozenset(
    {
        JournalTransition.CAPTURED_VERIFIED,
        JournalTransition.IMPORTED_CAPTURE_VERIFIED,
        JournalTransition.ACCOUNTED_EXCLUDED,
    }
)
_RETRYABLE = frozenset(
    {
        JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
        JournalTransition.RETRYABLE_FAILURE,
        JournalTransition.ELAPSED_BUDGET_EXHAUSTED,
    }
)
_ACTIVE = frozenset({JournalTransition.STARTED, JournalTransition.TRANSPORT_STARTED})
_QUEUED = frozenset({JournalTransition.DISCOVERED, JournalTransition.CYCLE_SAFETY_PROFILE_BOUND})
_REJECTED = frozenset(
    {
        JournalTransition.CONTRACT_REJECTED,
        JournalTransition.AUTHORIZATION_REJECTED,
        JournalTransition.RETRY_EXHAUSTED,
        JournalTransition.TERMINAL_UNAVAILABLE,
    }
)


class HKV1ProgressError(ValueError):
    """Closed failure to project retained V1 progress."""


@dataclass(frozen=True, slots=True)
class _SealedResult:
    result: HKV1FamilyCycleResult
    fingerprint: str


def _fail() -> Never:
    raise HKV1ProgressError(_UNAVAILABLE) from None


def _read_exact_file(path: Path) -> bytes:
    if type(path) is not type(Path()) or not path.is_absolute():
        _fail()
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or not 0 < details.st_size <= _MAX_RESULT_BYTES
        ):
            _fail()
        chunks: list[bytes] = []
        remaining = _MAX_RESULT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if not content or len(content) != details.st_size:
            _fail()
        return content  # noqa: TRY300 - cleanup is intentionally centralized below.
    except (OSError, ValueError) as error:
        if isinstance(error, HKV1ProgressError):
            raise
        raise HKV1ProgressError(_UNAVAILABLE) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _load_result(
    path: Path | None,
    *,
    family: str,
    cycle_id: str,
    expected_journal_head: str,
) -> _SealedResult | None:
    if path is None:
        return None
    content = _read_exact_file(path)
    try:
        document = parse_json_bytes(content, max_bytes=_MAX_RESULT_BYTES)
        manifest: CasesAcquisitionManifest | LegislationAcquisitionManifest
        if family == "CASES":
            manifest = CasesAcquisitionManifest.from_json(document)
        elif family == "LEGISLATION":
            manifest = LegislationAcquisitionManifest.from_json(document)
        else:  # pragma: no cover - internal closed caller.
            _fail()
        if canonicalize(checked_json_value(manifest.to_json())) != content:
            _fail()
        result = HKV1FamilyCycleResult(str(manifest.result))
    except (TypeError, ValueError) as error:
        if isinstance(error, HKV1ProgressError):
            raise
        raise HKV1ProgressError(_UNAVAILABLE) from error
    if manifest.cycle_id != cycle_id or manifest.journal_head_fingerprint != expected_journal_head:
        _fail()
    return _SealedResult(result, manifest.fingerprint)


def _retained_bytes(snapshot: RetainedAcquisitionJournalSnapshot) -> int:
    total = 0
    for entry in snapshot.entries:
        if entry.transition is JournalTransition.CAPTURED_VERIFIED:
            payload = entry.payload
            if type(payload) is not CapturedVerifiedPayload:
                _fail()
            total += payload.body_length
        elif entry.transition is JournalTransition.IMPORTED_CAPTURE_VERIFIED:
            payload = entry.payload
            if type(payload) is not ImportedCaptureVerifiedPayload:
                _fail()
            total += payload.body_length
        elif (
            entry.transition is JournalTransition.ACCOUNTED_EXCLUDED
            and type(entry.payload) is not AccountedExcludedPayload
        ):
            _fail()
    return total


def _family_progress(
    *,
    family: str,
    cycle_id: str,
    state_root: Path,
    result_path: Path | None,
) -> HKV1FamilyProgress:
    snapshot = read_retained_acquisition_journal(state_root, cycle_id)
    if any(entry.work_item.source_family != family for entry in snapshot.entries):
        _fail()
    transitions = tuple(item.transition for item in snapshot.checkpoint.items)
    if any(
        transition not in _SUCCESS | _RETRYABLE | _ACTIVE | _QUEUED | _REJECTED
        for transition in transitions
    ):
        _fail()
    semantic_head = semantic_journal_head(snapshot.entries)
    sealed = _load_result(
        result_path,
        family=family,
        cycle_id=cycle_id,
        expected_journal_head=semantic_head,
    )
    verified = sum(item in _SUCCESS for item in transitions)
    rejected = sum(item in _REJECTED for item in transitions)
    return HKV1FamilyProgress(
        material_family=family,
        cycle_id=cycle_id,
        discovered_count=len(transitions),
        verified_count=verified,
        retryable_count=sum(item in _RETRYABLE for item in transitions),
        rejected_count=rejected,
        terminal_count=verified + rejected,
        active_count=sum(item in _ACTIVE for item in transitions),
        queued_count=sum(item in _QUEUED for item in transitions),
        retained_byte_count=_retained_bytes(snapshot),
        journal_head_fingerprint=snapshot.checkpoint.journal_head_fingerprint,
        last_progress_at=snapshot.last_progress_at,
        cycle_result=None if sealed is None else sealed.result,
        result_fingerprint=None if sealed is None else sealed.fingerprint,
    )


def load_hk_v1_progress(  # noqa: PLR0913 - exact two-family retained inputs.
    *,
    state_root: Path,
    cases_cycle_id: str,
    legislation_cycle_id: str,
    cases_result_path: Path | None,
    legislation_result_path: Path | None,
    as_of: datetime,
) -> HKV1ProgressSnapshot:
    """Project exactly Cases and Legislation from replayed retained local state."""
    try:
        families = (
            _family_progress(
                family="CASES",
                cycle_id=cases_cycle_id,
                state_root=state_root,
                result_path=cases_result_path,
            ),
            _family_progress(
                family="LEGISLATION",
                cycle_id=legislation_cycle_id,
                state_root=state_root,
                result_path=legislation_result_path,
            ),
        )
        return aggregate_hk_v1_progress(families, as_of)
    except HKV1ProgressError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise HKV1ProgressError(_UNAVAILABLE) from error


def canonical_hk_v1_progress(snapshot: HKV1ProgressSnapshot) -> bytes:
    """Serialize the closed no-secret projection as canonical JSON plus newline."""
    try:
        serialized = serialize_hk_v1_progress(snapshot)
        payload: object = {
            **serialized,
            "families": [dict(family) for family in serialized["families"]],
        }
        return canonicalize(checked_json_value(payload)) + b"\n"
    except (TypeError, ValueError) as error:
        raise HKV1ProgressError(_UNAVAILABLE) from error
