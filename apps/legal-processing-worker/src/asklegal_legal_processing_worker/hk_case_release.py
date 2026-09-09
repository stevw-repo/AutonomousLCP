# ruff: noqa: BLE001, C901, TRY300, TRY301
"""Application-owned refusal checkpoint for the incomplete Hong Kong Cases release."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from asklegal_corpus import (
    AuthorityNoteEvidence,
    CorpusError,
    CorpusRelease,
    CorpusReleaseInput,
    ServingRecord,
    ServingRecordProfile,
    TraceabilityEntry,
    TraceabilityReference,
    freeze_corpus_release,
    serving_payload_fingerprint,
)
from asklegal_legal_desks.hk_case_judgment import accept_complete_cases_acquisition_manifest
from asklegal_legal_desks.hk_case_output import HKCaseProposedServingRecord
from asklegal_legal_desks.hk_case_records import (
    HKCaseRecordAccountingCheckpoint,
    HKCaseRecordAccountingError,
    HKCaseRecordBlockerCode,
    replay_hk_case_record_accounting_checkpoint,
)

_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_REQUIRED_BLOCKERS = tuple(sorted(HKCaseRecordBlockerCode, key=lambda item: item.value))


class HKCaseReleaseGateStatus(StrEnum):
    """The only truthful Task 5 application result."""

    WITHHELD_NOT_RELEASED = "WITHHELD_NOT_RELEASED"


class HKCaseReleaseGateErrorCode(StrEnum):
    """Closed application refusal-checkpoint failures."""

    CHECKPOINT_INVALID = "HK_CASE_RELEASE_CHECKPOINT_INVALID"
    CHECKPOINT_NOT_WITHHELD = "HK_CASE_RELEASE_CHECKPOINT_NOT_WITHHELD"
    POSITIVE_INPUT_INVALID = "HK_CASE_POSITIVE_RELEASE_INPUT_INVALID"


class HKCaseReleaseGateError(ValueError):
    """One sanitized fail-closed application error."""

    code: HKCaseReleaseGateErrorCode

    def __init__(self, code: HKCaseReleaseGateErrorCode) -> None:
        """Expose one stable code without retaining hostile input."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HKCaseReleaseWithholdingCheckpoint:
    """A deterministic refusal result, deliberately not a Withholding Release."""

    status: HKCaseReleaseGateStatus
    accounting_checkpoint_fingerprint: str
    blocker_codes: tuple[HKCaseRecordBlockerCode, ...]
    listing_count: int
    zero_proposition_count: int
    quarantine_listing_ids: tuple[str, ...]
    blocked_listing_ids: tuple[str, ...]
    withholding_fingerprint: str

    def __post_init__(self) -> None:
        """Recompute the exact negative projection and its fingerprint."""
        try:
            _withholding_facts(self)
        except HKCaseReleaseGateError:
            raise
        except Exception:
            raise HKCaseReleaseGateError(HKCaseReleaseGateErrorCode.CHECKPOINT_INVALID) from None

    def __copy__(self) -> HKCaseReleaseWithholdingCheckpoint:
        """Reconstruct and revalidate a shallow copy."""
        return _copy_checkpoint(self)

    def __deepcopy__(self, memo: dict[int, object]) -> HKCaseReleaseWithholdingCheckpoint:
        """Reconstruct and revalidate a deep copy of immutable primitives."""
        del memo
        return _copy_checkpoint(self)


@dataclass(frozen=True, slots=True)
class HKCaseReleaseCandidate:
    """One strictly validated Desk candidate plus its immutable source bindings."""

    proposed_record: HKCaseProposedServingRecord
    artifact_ref: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCasePositiveReleaseRequest:
    """Complete retained inputs for one positive Case CorpusRelease freeze."""

    observation_cutoff: str
    candidates: tuple[HKCaseReleaseCandidate, ...]
    release_evidence_refs: tuple[str, ...]
    release_validation_refs: tuple[str, ...]
    zero_record_justification_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HKCaseRecordTraceabilityBinding:
    """Explicit retained legal identity and evidence bindings for one Case record."""

    record_id: str
    serving_profile_id: str
    legal_item_id: str
    official_version_ids: tuple[str, ...]
    legal_location_ids: tuple[str, ...]
    evidence_refs: tuple[TraceabilityReference, ...]
    authority_note_evidence: AuthorityNoteEvidence
    grouping_ids: tuple[str, ...] = ()
    display_citation_ids: tuple[str, ...] = ()


def build_hk_case_record_traceability(
    release: CorpusRelease,
    serving_profile: ServingRecordProfile,
    bindings: tuple[HKCaseRecordTraceabilityBinding, ...],
) -> tuple[TraceabilityEntry, ...]:
    """Map exact retained Case identities to every released record without invention."""
    try:
        if (
            type(release) is not CorpusRelease
            or release.scope_id != "HK-CASE-BINDING-POST-1997"
            or type(serving_profile) is not ServingRecordProfile
            or type(bindings) is not tuple
        ):
            raise TypeError
        by_record = {item.record_id: item for item in bindings}
        if len(by_record) != len(bindings) or set(by_record) != {
            item.record.record_id for item in release.records
        }:
            raise TypeError
        entries: list[TraceabilityEntry] = []
        for released in release.records:
            binding = by_record[released.record.record_id]
            if (
                type(binding) is not HKCaseRecordTraceabilityBinding
                or binding.serving_profile_id != serving_profile.serving_record_profile_id
                or any(
                    type(values) is not tuple or values != tuple(sorted(set(values)))
                    for values in (
                        binding.official_version_ids,
                        binding.legal_location_ids,
                        binding.grouping_ids,
                        binding.display_citation_ids,
                    )
                )
            ):
                raise TypeError
            entries.append(
                TraceabilityEntry(
                    binding.record_id,
                    released.serving_payload_fingerprint,
                    binding.serving_profile_id,
                    binding.legal_item_id,
                    binding.official_version_ids,
                    binding.legal_location_ids,
                    release.scope_id,
                    release.release_id,
                    binding.evidence_refs,
                    binding.authority_note_evidence,
                    binding.grouping_ids,
                    binding.display_citation_ids,
                )
            )
        return tuple(entries)
    except (AttributeError, TypeError, ValueError) as error:
        raise HKCaseReleaseGateError(HKCaseReleaseGateErrorCode.POSITIVE_INPUT_INVALID) from error


def build_hk_case_corpus_release(request: HKCasePositiveReleaseRequest) -> CorpusRelease:
    """Map exact accepted Case records into the fixed V1 Case release scope."""
    try:
        if type(request) is not HKCasePositiveReleaseRequest:
            raise TypeError
        containers = (
            request.candidates,
            request.release_evidence_refs,
            request.release_validation_refs,
            request.zero_record_justification_refs,
        )
        if any(type(value) is not tuple for value in containers):
            raise TypeError
        if not request.release_evidence_refs or not request.release_validation_refs:
            raise TypeError
        for refs in containers[1:]:
            if any(type(item) is not str or not item for item in refs):
                raise TypeError
            if refs != tuple(sorted(set(refs))):
                raise TypeError
        if (not request.candidates) != bool(request.zero_record_justification_refs):
            raise TypeError
        records: list[ServingRecord] = []
        for candidate in request.candidates:
            if (
                type(candidate) is not HKCaseReleaseCandidate
                or type(candidate.proposed_record) is not HKCaseProposedServingRecord
                or type(candidate.artifact_ref) is not str
                or not candidate.artifact_ref
                or type(candidate.evidence_refs) is not tuple
                or not candidate.evidence_refs
                or candidate.evidence_refs != tuple(sorted(set(candidate.evidence_refs)))
                or any(type(item) is not str or not item for item in candidate.evidence_refs)
            ):
                raise TypeError
            proposed = candidate.proposed_record
            record = ServingRecord(
                proposed.record_id,
                proposed.text,
                proposed.country,
                proposed.jurisdiction,
                proposed.material_type,
                proposed.source,
                proposed.authority_note,
                candidate.artifact_ref,
                candidate.evidence_refs,
            )
            if serving_payload_fingerprint(record) != proposed.payload_fingerprint:
                raise TypeError
            records.append(record)
        return freeze_corpus_release(
            CorpusReleaseInput(
                "HK-CASE-BINDING-POST-1997",
                request.observation_cutoff,
                request.release_evidence_refs,
                request.release_validation_refs,
                zero_record_justification_refs=request.zero_record_justification_refs,
            ),
            records,
        )
    except HKCaseReleaseGateError:
        raise
    except (AttributeError, CorpusError, TypeError, ValueError) as error:
        raise HKCaseReleaseGateError(HKCaseReleaseGateErrorCode.POSITIVE_INPUT_INVALID) from error


def withhold_hk_case_release(
    accounting: HKCaseRecordAccountingCheckpoint,
) -> HKCaseReleaseWithholdingCheckpoint:
    """Turn exact negative Desk accounting into an application refusal checkpoint."""
    try:
        accounting.__post_init__()
        if type(accounting) is not HKCaseRecordAccountingCheckpoint:
            raise TypeError
        replay_hk_case_record_accounting_checkpoint(accounting)
        accounting_fingerprint = accounting.checkpoint_fingerprint
        if accounting.blockers != _REQUIRED_BLOCKERS:
            raise HKCaseReleaseGateError(HKCaseReleaseGateErrorCode.CHECKPOINT_NOT_WITHHELD)
        result = HKCaseReleaseWithholdingCheckpoint(
            status=HKCaseReleaseGateStatus.WITHHELD_NOT_RELEASED,
            accounting_checkpoint_fingerprint=accounting_fingerprint,
            blocker_codes=accounting.blockers,
            listing_count=accounting.listing_count,
            zero_proposition_count=accounting.zero_proposition_count,
            quarantine_listing_ids=accounting.quarantine_listing_ids,
            blocked_listing_ids=accounting.blocked_listing_ids,
            withholding_fingerprint=_withholding_fingerprint_values(
                {
                    "status": HKCaseReleaseGateStatus.WITHHELD_NOT_RELEASED,
                    "accounting_checkpoint_fingerprint": accounting_fingerprint,
                    "blocker_codes": accounting.blockers,
                    "listing_count": accounting.listing_count,
                    "zero_proposition_count": accounting.zero_proposition_count,
                    "quarantine_listing_ids": accounting.quarantine_listing_ids,
                    "blocked_listing_ids": accounting.blocked_listing_ids,
                }
            ),
        )
        replay_hk_case_record_accounting_checkpoint(accounting)
        if accounting.checkpoint_fingerprint != accounting_fingerprint:
            raise TypeError
        return result
    except HKCaseReleaseGateError:
        raise
    except HKCaseRecordAccountingError:
        raise HKCaseReleaseGateError(HKCaseReleaseGateErrorCode.CHECKPOINT_INVALID) from None
    except Exception:
        raise HKCaseReleaseGateError(HKCaseReleaseGateErrorCode.CHECKPOINT_INVALID) from None


def withhold_hk_case_release_after_complete_acquisition(
    acquisition_manifest: bytes,
    accounting: HKCaseRecordAccountingCheckpoint,
) -> HKCaseReleaseWithholdingCheckpoint:
    """Require complete acquisition before preserving the existing no-release checkpoint."""
    try:
        accept_complete_cases_acquisition_manifest(acquisition_manifest)
    except Exception:
        raise HKCaseReleaseGateError(HKCaseReleaseGateErrorCode.CHECKPOINT_INVALID) from None
    return withhold_hk_case_release(accounting)


def replay_hk_case_release_withholding_checkpoint(
    checkpoint: HKCaseReleaseWithholdingCheckpoint,
) -> HKCaseReleaseWithholdingCheckpoint:
    """Revalidate one detached refusal checkpoint and return that exact object."""
    if type(checkpoint) is not HKCaseReleaseWithholdingCheckpoint:
        raise HKCaseReleaseGateError(HKCaseReleaseGateErrorCode.CHECKPOINT_INVALID)
    checkpoint.__post_init__()
    return checkpoint


def canonical_hk_case_release_withholding_checkpoint(
    checkpoint: HKCaseReleaseWithholdingCheckpoint,
) -> bytes:
    """Return the complete canonical refusal-checkpoint bytes."""
    replay_hk_case_release_withholding_checkpoint(checkpoint)
    return _canonical(_withholding_document(checkpoint, include_fingerprint=True))


def _withholding_facts(checkpoint: HKCaseReleaseWithholdingCheckpoint) -> None:
    if (
        type(checkpoint.status) is not HKCaseReleaseGateStatus
        or checkpoint.status is not HKCaseReleaseGateStatus.WITHHELD_NOT_RELEASED
        or checkpoint.blocker_codes != _REQUIRED_BLOCKERS
        or type(checkpoint.listing_count) is not int
        or checkpoint.listing_count < 0
        or type(checkpoint.zero_proposition_count) is not int
        or not 0 <= checkpoint.zero_proposition_count <= checkpoint.listing_count
    ):
        raise TypeError
    _fingerprint(checkpoint.accounting_checkpoint_fingerprint)
    for identities in (checkpoint.quarantine_listing_ids, checkpoint.blocked_listing_ids):
        if (
            type(identities) is not tuple
            or identities != tuple(sorted(set(identities)))
            or any(type(item) is not str or not item for item in identities)
        ):
            raise TypeError
    if set(checkpoint.quarantine_listing_ids).intersection(checkpoint.blocked_listing_ids):
        raise TypeError
    if checkpoint.withholding_fingerprint != _fingerprint_bytes(
        _canonical(_withholding_document(checkpoint, include_fingerprint=False))
    ):
        raise TypeError


def _withholding_document(
    checkpoint: HKCaseReleaseWithholdingCheckpoint, *, include_fingerprint: bool
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_id": "asklegal.hk-case-release-withholding-checkpoint/v1",
        "status": checkpoint.status.value,
        "accounting_checkpoint_fingerprint": checkpoint.accounting_checkpoint_fingerprint,
        "blocker_codes": [item.value for item in checkpoint.blocker_codes],
        "listing_count": checkpoint.listing_count,
        "zero_proposition_count": checkpoint.zero_proposition_count,
        "quarantine_listing_ids": list(checkpoint.quarantine_listing_ids),
        "blocked_listing_ids": list(checkpoint.blocked_listing_ids),
    }
    if include_fingerprint:
        document["withholding_fingerprint"] = checkpoint.withholding_fingerprint
    return document


def _withholding_fingerprint_values(values: Mapping[str, object]) -> str:
    checkpoint = object.__new__(HKCaseReleaseWithholdingCheckpoint)
    for field_name, value in values.items():
        object.__setattr__(checkpoint, field_name, value)
    object.__setattr__(checkpoint, "withholding_fingerprint", "")
    return _fingerprint_bytes(
        _canonical(_withholding_document(checkpoint, include_fingerprint=False))
    )


def _copy_checkpoint(
    checkpoint: HKCaseReleaseWithholdingCheckpoint,
) -> HKCaseReleaseWithholdingCheckpoint:
    return HKCaseReleaseWithholdingCheckpoint(
        checkpoint.status,
        checkpoint.accounting_checkpoint_fingerprint,
        checkpoint.blocker_codes,
        checkpoint.listing_count,
        checkpoint.zero_proposition_count,
        checkpoint.quarantine_listing_ids,
        checkpoint.blocked_listing_ids,
        checkpoint.withholding_fingerprint,
    )


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _fingerprint(value: object) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        raise TypeError
    return value


def _fingerprint_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


__all__ = [
    "HKCaseReleaseGateError",
    "HKCaseReleaseGateErrorCode",
    "HKCaseReleaseGateStatus",
    "HKCaseReleaseWithholdingCheckpoint",
    "canonical_hk_case_release_withholding_checkpoint",
    "replay_hk_case_release_withholding_checkpoint",
    "withhold_hk_case_release",
    "withhold_hk_case_release_after_complete_acquisition",
]
