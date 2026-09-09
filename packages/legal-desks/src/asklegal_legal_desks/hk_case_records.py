# ruff: noqa: BLE001, C901, PLR0911, PLR0912, PLR0915, TRY300, TRY301
"""Source-neutral Hong Kong Cases listing accounting without release authority."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, is_dataclass
from datetime import date, datetime
from enum import EnumType, StrEnum
from hashlib import sha256
from typing import TypeIs

from . import (
    hk_case_authority_graph as _authority_graph_module,
)
from . import (
    hk_case_coverage_ledger as _coverage_ledger_module,
)
from . import (
    hk_case_judgment as _judgment_module,
)
from . import (
    hk_case_output as _output_module,
)
from . import (
    hk_case_proposition as _proposition_module,
)
from . import (
    hk_case_semantic_task as _semantic_task_module,
)
from .hk_case_authority_graph import (
    HKCaseAuthorityGraph,
    HKCaseAuthoritySelection,
    HKCaseAuthoritySelectionState,
    replay_hk_case_authority_graph,
)
from .hk_case_judgment import (
    HKCaseJudgment,
    HKCaseJudgmentBundle,
    HKCaseJudgmentDisposition,
    HKCaseJudgmentOpinion,
    HKCaseJudgmentParagraph,
    HKCaseJudgmentTranslation,
)
from .hk_case_proposition import (
    HKCaseAdmittedProposition,
    HKCaseAdmittedSemanticDecision,
    HKCasePropositionAdmissionDisposition,
    HKCasePropositionAdmissionResult,
    HKCasePropositionRequestPair,
    HKCasePropositionSemanticRequest,
    replay_hk_case_proposition_admission_projection,
)

_COURTS = frozenset({"CFA", "CA", "CFI", "CT"})
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}")
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_EARLIEST_V1_DATE = date(1997, 7, 1)
_EARLIEST_V1_YEAR = 1997
_MAXIMUM_YEAR = 9999
_MAX_INVENTORY_PROJECTION_BYTES = 512_000_000
_MAX_INVENTORY_ENTRIES = 1_000_000
_AUTHORITY_GRAPH_IDENTITY_ROOT_INDEX = 3
_INVENTORY_PROJECTION_SCHEMA = "asklegal.hk-judiciary-accounting-projection/v1"
_AUTHORITY_ISSUANCE_TYPE_UNAVAILABLE = "HK_CASE_AUTHORITY_ISSUANCE_TYPE_UNAVAILABLE"
_CAPTURE_MODULES = (
    _authority_graph_module,
    _coverage_ledger_module,
    _judgment_module,
    _output_module,
    _proposition_module,
    _semantic_task_module,
)
_CAPTURE_DATACLASS_TYPES: frozenset[type[object]] = frozenset(
    value
    for module in _CAPTURE_MODULES
    for value in vars(module).values()
    if type(value) is type and is_dataclass(value)
)
_CAPTURE_ENUM_TYPES: frozenset[object] = frozenset(
    value
    for module in _CAPTURE_MODULES
    for value in vars(module).values()
    if isinstance(value, EnumType)
)
_AUTHORITY_OUTPUT_ISSUANCE_TYPE = vars(_authority_graph_module).get(
    "_HKCaseAuthorityOutputIssuance"
)
_AUTHORITY_OUTPUT_ISSUANCE_VALIDATOR = vars(_authority_graph_module).get("_issued_output_facts")
_PROPOSITION_ADMISSION_ISSUANCE_VALIDATOR = vars(_proposition_module).get("_issued_admission_facts")
if (
    type(_AUTHORITY_OUTPUT_ISSUANCE_TYPE) is not type
    or not is_dataclass(_AUTHORITY_OUTPUT_ISSUANCE_TYPE)
    or not callable(_AUTHORITY_OUTPUT_ISSUANCE_VALIDATOR)
    or not callable(_PROPOSITION_ADMISSION_ISSUANCE_VALIDATOR)
):
    raise RuntimeError(_AUTHORITY_ISSUANCE_TYPE_UNAVAILABLE)


class HKCaseReleaseRunKind(StrEnum):
    """The predecessor relation for an accounting attempt, never release authority."""

    INITIAL = "INITIAL"
    CHANGED = "CHANGED"


class HKCaseListingRecordDisposition(StrEnum):
    """Closed source-neutral outcomes for one official listing."""

    OUT_OF_V1_DATE_SCOPE = "OUT_OF_V1_DATE_SCOPE"
    JUDGMENT_BUNDLE_BLOCKED = "JUDGMENT_BUNDLE_BLOCKED"
    PROPOSITION_ADMISSION_BLOCKED = "PROPOSITION_ADMISSION_BLOCKED"
    COMPLETE_ZERO_PROPOSITIONS = "COMPLETE_ZERO_PROPOSITIONS"
    AUTHORITY_QUARANTINED = "AUTHORITY_QUARANTINED"


class HKCaseRecordBlockerCode(StrEnum):
    """Repository-owned reasons this checkpoint cannot become a release."""

    AUTHENTIC_INVENTORY_NOT_ADMITTED = "AUTHENTIC_INVENTORY_NOT_ADMITTED"
    SEMANTIC_WORKFLOW_NOT_ADMITTED = "SEMANTIC_WORKFLOW_NOT_ADMITTED"
    CURRENT_AUTHORITY_NOT_ESTABLISHED = "CURRENT_AUTHORITY_NOT_ESTABLISHED"
    REGISTER_IDENTITY_ISSUANCE_UNAVAILABLE = "REGISTER_IDENTITY_ISSUANCE_UNAVAILABLE"


_REQUIRED_BLOCKERS = tuple(sorted(HKCaseRecordBlockerCode, key=lambda item: item.value))


class HKCaseRecordAccountingErrorCode(StrEnum):
    """Closed failures at the Task 5 listing-accounting boundary."""

    REQUEST_INVALID = "HK_CASE_RECORD_REQUEST_INVALID"
    INVENTORY_INVALID = "HK_CASE_RECORD_INVENTORY_INVALID"
    INVENTORY_SCOPE_MISMATCH = "HK_CASE_RECORD_INVENTORY_SCOPE_MISMATCH"
    LISTING_ACCOUNTING_DUPLICATE = "HK_CASE_LISTING_ACCOUNTING_DUPLICATE"
    LISTING_ACCOUNTING_INCOMPLETE = "HK_CASE_LISTING_ACCOUNTING_INCOMPLETE"
    LISTING_ACCOUNTING_EXTRANEOUS = "HK_CASE_LISTING_ACCOUNTING_EXTRANEOUS"
    LISTING_WORK_INVALID = "HK_CASE_LISTING_WORK_INVALID"
    PROPOSITION_ACCOUNTING_INCOMPLETE = "HK_CASE_PROPOSITION_ACCOUNTING_INCOMPLETE"
    AUTHORITY_GRAPH_INVALID = "HK_CASE_AUTHORITY_GRAPH_INVALID"
    POSITIVE_SELECTION_UNSUPPORTED = "HK_CASE_POSITIVE_SELECTION_UNSUPPORTED"
    CHECKPOINT_INVALID = "HK_CASE_RECORD_CHECKPOINT_INVALID"


class HKCaseRecordAccountingError(ValueError):
    """One sanitized fail-closed Task 5 accounting error."""

    code: HKCaseRecordAccountingErrorCode

    def __init__(self, code: HKCaseRecordAccountingErrorCode) -> None:
        """Expose one stable code without preserving hostile input."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HKCaseRecordAccountingRequest:
    """One exact court/year accounting request with explicit predecessor semantics."""

    scope_id: str
    court_family: str
    calendar_year: int
    observation_cutoff: str
    run_kind: HKCaseReleaseRunKind
    prior_release_id: str | None

    def __post_init__(self) -> None:
        """Validate the exact court/year and predecessor relation."""
        try:
            _identity(self.scope_id)
            if type(self.court_family) is not str or self.court_family not in _COURTS:
                raise TypeError
            if (
                type(self.calendar_year) is not int
                or not _EARLIEST_V1_YEAR <= self.calendar_year <= _MAXIMUM_YEAR
                or _utc(self.observation_cutoff).date().year < self.calendar_year
                or type(self.run_kind) is not HKCaseReleaseRunKind
            ):
                raise TypeError
            if self.run_kind is HKCaseReleaseRunKind.INITIAL:
                if self.prior_release_id is not None:
                    raise TypeError
            elif self.prior_release_id is None:
                raise TypeError
            else:
                _identity(self.prior_release_id)
        except HKCaseRecordAccountingError:
            raise
        except Exception:
            raise HKCaseRecordAccountingError(
                HKCaseRecordAccountingErrorCode.REQUEST_INVALID
            ) from None


@dataclass(frozen=True, slots=True)
class HKCaseListingWork:
    """One listing's supplied local Task 1 and optional Task 3 result."""

    listing_id: str
    bundle: HKCaseJudgmentBundle | None
    admission: HKCasePropositionAdmissionResult | None
    blocking_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject loose work shapes before upstream replay."""
        try:
            _identity(self.listing_id)
            if type(self.bundle) not in {HKCaseJudgmentBundle, type(None)} or type(
                self.admission
            ) not in {HKCasePropositionAdmissionResult, type(None)}:
                raise TypeError
            _texts(self.blocking_refs, allow_empty=True)
        except Exception:
            raise HKCaseRecordAccountingError(
                HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID
            ) from None


@dataclass(frozen=True, slots=True)
class HKCaseListingRecordAccounting:
    """Text-free immutable accounting for one official listing."""

    listing_id: str
    source_listing_fingerprint: str
    disposition: HKCaseListingRecordDisposition
    bundle_fingerprint: str | None
    admission_fingerprint: str | None
    proposition_ids: tuple[str, ...]
    quarantined_proposition_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    blocking_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Revalidate the complete text-free listing projection."""
        try:
            _listing_accounting_facts(self)
        except HKCaseRecordAccountingError:
            raise
        except Exception:
            raise HKCaseRecordAccountingError(
                HKCaseRecordAccountingErrorCode.CHECKPOINT_INVALID
            ) from None


@dataclass(frozen=True, slots=True)
class HKCaseRecordAccountingCheckpoint:
    """Complete local listing accounting that explicitly grants no release authority."""

    scope_id: str
    court_family: str
    calendar_year: int
    observation_cutoff: str
    run_kind: HKCaseReleaseRunKind
    prior_release_id: str | None
    inventory_fingerprint: str
    listing_accounting: tuple[HKCaseListingRecordAccounting, ...]
    listing_count: int
    disposition_count: int
    zero_proposition_count: int
    quarantine_listing_ids: tuple[str, ...]
    blocked_listing_ids: tuple[str, ...]
    blockers: tuple[HKCaseRecordBlockerCode, ...]
    checkpoint_fingerprint: str

    def __post_init__(self) -> None:
        """Recompute all counts, closed blockers, and the canonical digest."""
        try:
            _checkpoint_facts(self)
        except HKCaseRecordAccountingError:
            raise
        except Exception:
            raise HKCaseRecordAccountingError(
                HKCaseRecordAccountingErrorCode.CHECKPOINT_INVALID
            ) from None

    def __copy__(self) -> HKCaseRecordAccountingCheckpoint:
        """Reconstruct and revalidate a shallow copy."""
        return _copy_checkpoint(self)

    def __deepcopy__(self, memo: dict[int, object]) -> HKCaseRecordAccountingCheckpoint:
        """Reconstruct and revalidate a deep copy of immutable primitives."""
        del memo
        return _copy_checkpoint(self)


@dataclass(frozen=True, slots=True)
class _RequestSnapshot:
    scope_id: str
    court_family: str
    calendar_year: int
    observation_cutoff: str
    run_kind: HKCaseReleaseRunKind
    prior_release_id: str | None


@dataclass(frozen=True, slots=True)
class _InventoryFact:
    listing_id: str
    court_family: str
    decision_date: str
    listing_fingerprint: str


@dataclass(frozen=True, slots=True)
class _InventorySnapshot:
    court_family: str
    earliest_decision_date: str
    observation_cutoff: str
    inventory_fingerprint: str
    entries: tuple[_InventoryFact, ...]


@dataclass(frozen=True, slots=True)
class _ListingWorkSnapshot:
    listing_id: str
    bundle: _BundleSnapshot | None
    admission: _AdmissionSnapshot | None
    blocking_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BundleSnapshot:
    listing_id: str
    disposition: HKCaseJudgmentDisposition
    judgment_id: str | None
    court_id: str | None
    decision_date: str | None
    evidence_refs: tuple[str, ...]
    bundle_fingerprint: str
    complete_projection: bytes


@dataclass(frozen=True, slots=True)
class _AdmissionSnapshot:
    disposition: HKCasePropositionAdmissionDisposition
    judgment_subject_id: str
    judgment_fingerprint: str
    proposition_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    admission_fingerprint: str
    complete_projection: bytes


@dataclass(frozen=True, slots=True)
class _ListingWorkCapture:
    snapshot: _ListingWorkSnapshot


@dataclass(frozen=True, slots=True)
class _WorkFact:
    listing_id: str
    disposition: HKCaseListingRecordDisposition
    bundle_fingerprint: str | None
    admission_fingerprint: str | None
    proposition_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    blocking_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _FrozenCallerObject:
    """One getter-free exact dataclass snapshot containing only private children."""

    object_type: type[object]
    attributes: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class _OriginalListingWork:
    """Live references retained only for later issuance replay and drift rejection."""

    item: HKCaseListingWork
    listing_id: object
    bundle: HKCaseJudgmentBundle | None
    admission: HKCasePropositionAdmissionResult | None
    admission_issuance: object | None
    blocking_refs: object


@dataclass(frozen=True, slots=True)
class _OriginalAuthorityOutput:
    """One exact Task 4 result and captured process-local witness identity."""

    output: HKCaseAuthoritySelection | HKCaseAuthorityGraph
    issuance: object


@dataclass(frozen=True, slots=True)
class _CallerIdentityNode:
    """Exact caller-owned object/container identity and recursively covered fields."""

    reference: object
    children: tuple[tuple[str, _CallerIdentityNode], ...]


@dataclass(frozen=True, slots=True)
class _CallerInputCapture:
    """Complete phase-one capture made before any validation or callback."""

    request: _FrozenCallerObject
    inventory_projection: bytes
    listing_work: tuple[_FrozenCallerObject, ...]
    authority_graph: _FrozenCallerObject
    originals: tuple[_OriginalListingWork, ...]
    authority_outputs: tuple[_OriginalAuthorityOutput, ...]
    identity_roots: tuple[_CallerIdentityNode, ...]


def account_hk_case_records(
    request: HKCaseRecordAccountingRequest,
    inventory_projection: bytes,
    listing_work: tuple[HKCaseListingWork, ...],
    authority_graph: HKCaseAuthorityGraph,
) -> HKCaseRecordAccountingCheckpoint:
    """Account one exact local scope and stop before any positive record or release."""
    try:
        caller = _capture_caller_inputs(
            request,
            inventory_projection,
            listing_work,
            authority_graph,
        )
        detached_request = _thaw_exact_dataclass(caller.request)
        if type(detached_request) is not HKCaseRecordAccountingRequest:
            raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.REQUEST_INVALID)
        request_snapshot = _request_snapshot(detached_request)
        detached_work: list[HKCaseListingWork] = []
        for frozen_item in caller.listing_work:
            item = _thaw_exact_dataclass(frozen_item)
            if type(item) is not HKCaseListingWork:
                raise HKCaseRecordAccountingError(
                    HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID
                )
            detached_work.append(item)
        work_capture = _listing_work_capture(tuple(detached_work))
        _validate_original_admission_issuance(caller.originals)
        detached_graph = _thaw_exact_dataclass(caller.authority_graph)
        if type(detached_graph) is not HKCaseAuthorityGraph:
            raise HKCaseRecordAccountingError(
                HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID
            )
        selection_states = _detached_authority_graph_states(
            detached_graph,
            caller.authority_outputs,
        )
        _replay_original_authority_graph(authority_graph)
        _replay_original_listing_work(caller.originals)
        _assert_caller_work_unchanged(caller, authority_graph)
        return _account_hk_case_records(
            request_snapshot,
            caller.inventory_projection,
            tuple(item.snapshot for item in work_capture),
            selection_states,
        )
    except HKCaseRecordAccountingError:
        raise
    except Exception:
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.REQUEST_INVALID) from None


def _account_hk_case_records(
    request: _RequestSnapshot,
    inventory_projection: bytes,
    listing_work: tuple[_ListingWorkSnapshot, ...],
    selection_states: Mapping[str, HKCaseAuthoritySelectionState],
) -> HKCaseRecordAccountingCheckpoint:
    inventory_snapshot = _inventory_snapshot(inventory_projection)
    _inventory_matches_request(inventory_snapshot, request)
    work_ids = tuple(item.listing_id for item in listing_work)
    if len(work_ids) != len(set(work_ids)):
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_ACCOUNTING_DUPLICATE
        )
    scoped_entries = tuple(
        entry
        for entry in inventory_snapshot.entries
        if _in_scope(entry.decision_date, request.calendar_year)
    )
    expected_ids = tuple(entry.listing_id for entry in scoped_entries)
    missing = set(expected_ids).difference(work_ids)
    extra = set(work_ids).difference(expected_ids)
    if missing:
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_ACCOUNTING_INCOMPLETE
        )
    if extra:
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_ACCOUNTING_EXTRANEOUS
        )
    work_by_id = {item.listing_id: item for item in listing_work}
    facts = tuple(_work_fact(work_by_id[entry.listing_id], entry) for entry in scoped_entries)
    proposition_ids = tuple(
        proposition_id for fact in facts for proposition_id in fact.proposition_ids
    )
    if len(proposition_ids) != len(set(proposition_ids)) or set(proposition_ids) != set(
        selection_states
    ):
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.PROPOSITION_ACCOUNTING_INCOMPLETE
        )
    rows: list[HKCaseListingRecordAccounting] = []
    for entry, fact in zip(scoped_entries, facts, strict=True):
        quarantined: tuple[str, ...] = ()
        disposition = fact.disposition
        if fact.proposition_ids:
            states = tuple(selection_states[item] for item in fact.proposition_ids)
            if any(state is not HKCaseAuthoritySelectionState.QUARANTINED for state in states):
                raise HKCaseRecordAccountingError(
                    HKCaseRecordAccountingErrorCode.POSITIVE_SELECTION_UNSUPPORTED
                )
            quarantined = fact.proposition_ids
            disposition = HKCaseListingRecordDisposition.AUTHORITY_QUARANTINED
        rows.append(
            HKCaseListingRecordAccounting(
                listing_id=fact.listing_id,
                source_listing_fingerprint=entry.listing_fingerprint,
                disposition=disposition,
                bundle_fingerprint=fact.bundle_fingerprint,
                admission_fingerprint=fact.admission_fingerprint,
                proposition_ids=fact.proposition_ids,
                quarantined_proposition_ids=quarantined,
                evidence_refs=fact.evidence_refs,
                blocking_refs=fact.blocking_refs,
            )
        )
    ordered_rows = tuple(sorted(rows, key=lambda item: item.listing_id))
    quarantine_ids = tuple(
        row.listing_id
        for row in ordered_rows
        if row.disposition is HKCaseListingRecordDisposition.AUTHORITY_QUARANTINED
    )
    blocked_ids = tuple(
        row.listing_id
        for row in ordered_rows
        if row.disposition
        in {
            HKCaseListingRecordDisposition.JUDGMENT_BUNDLE_BLOCKED,
            HKCaseListingRecordDisposition.PROPOSITION_ADMISSION_BLOCKED,
        }
    )
    zero_count = sum(
        row.disposition is HKCaseListingRecordDisposition.COMPLETE_ZERO_PROPOSITIONS
        for row in ordered_rows
    )
    return HKCaseRecordAccountingCheckpoint(
        scope_id=request.scope_id,
        court_family=request.court_family,
        calendar_year=request.calendar_year,
        observation_cutoff=request.observation_cutoff,
        run_kind=request.run_kind,
        prior_release_id=request.prior_release_id,
        inventory_fingerprint=inventory_snapshot.inventory_fingerprint,
        listing_accounting=ordered_rows,
        listing_count=len(ordered_rows),
        disposition_count=len(ordered_rows),
        zero_proposition_count=zero_count,
        quarantine_listing_ids=quarantine_ids,
        blocked_listing_ids=blocked_ids,
        blockers=_REQUIRED_BLOCKERS,
        checkpoint_fingerprint=_checkpoint_fingerprint_values(
            {
                "scope_id": request.scope_id,
                "court_family": request.court_family,
                "calendar_year": request.calendar_year,
                "observation_cutoff": request.observation_cutoff,
                "run_kind": request.run_kind,
                "prior_release_id": request.prior_release_id,
                "inventory_fingerprint": inventory_snapshot.inventory_fingerprint,
                "listing_accounting": ordered_rows,
                "listing_count": len(ordered_rows),
                "disposition_count": len(ordered_rows),
                "zero_proposition_count": zero_count,
                "quarantine_listing_ids": quarantine_ids,
                "blocked_listing_ids": blocked_ids,
                "blockers": _REQUIRED_BLOCKERS,
            }
        ),
    )


def replay_hk_case_record_accounting_checkpoint(
    checkpoint: HKCaseRecordAccountingCheckpoint,
) -> HKCaseRecordAccountingCheckpoint:
    """Revalidate one detached negative checkpoint and return that exact object."""
    if type(checkpoint) is not HKCaseRecordAccountingCheckpoint:
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.CHECKPOINT_INVALID)
    checkpoint.__post_init__()
    return checkpoint


def canonical_hk_case_record_accounting_checkpoint(
    checkpoint: HKCaseRecordAccountingCheckpoint,
) -> bytes:
    """Return the complete text-free canonical checkpoint projection."""
    replay_hk_case_record_accounting_checkpoint(checkpoint)
    return _canonical(_checkpoint_document(checkpoint, include_fingerprint=True))


def _capture_caller_inputs(
    request: HKCaseRecordAccountingRequest,
    inventory_projection: bytes,
    listing_work: tuple[HKCaseListingWork, ...],
    authority_graph: HKCaseAuthorityGraph,
) -> _CallerInputCapture:
    """Phase one: copy the complete caller graph using exact slot reads only."""
    if type(request) is not HKCaseRecordAccountingRequest:
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.REQUEST_INVALID)
    try:
        frozen_request = _freeze_exact_dataclass(request)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.REQUEST_INVALID) from None
    if type(inventory_projection) is not bytes:
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.INVENTORY_INVALID)
    if type(listing_work) is not tuple or any(
        type(item) is not HKCaseListingWork for item in listing_work
    ):
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID)
    try:
        originals: list[_OriginalListingWork] = []
        for item in listing_work:
            listing_id = object.__getattribute__(item, "listing_id")
            bundle_value = object.__getattribute__(item, "bundle")
            admission_value = object.__getattribute__(item, "admission")
            blocking_refs = object.__getattribute__(item, "blocking_refs")
            if type(bundle_value) not in {HKCaseJudgmentBundle, type(None)} or type(
                admission_value
            ) not in {HKCasePropositionAdmissionResult, type(None)}:
                raise TypeError
            bundle = bundle_value if type(bundle_value) is HKCaseJudgmentBundle else None
            admission = (
                admission_value
                if type(admission_value) is HKCasePropositionAdmissionResult
                else None
            )
            admission_issuance = (
                None if admission is None else object.__getattribute__(admission, "issuance")
            )
            originals.append(
                _OriginalListingWork(
                    item,
                    listing_id,
                    bundle,
                    admission,
                    admission_issuance,
                    blocking_refs,
                )
            )
        frozen_work: list[_FrozenCallerObject] = []
        prior_object_ids: set[int] = set()
        for original in originals:
            object_ids: set[int] = set()
            frozen = _FrozenCallerObject(
                HKCaseListingWork,
                (
                    ("listing_id", _freeze_exact_value(original.listing_id, object_ids)),
                    ("bundle", _freeze_exact_value(original.bundle, object_ids)),
                    ("admission", _freeze_exact_value(original.admission, object_ids)),
                    ("blocking_refs", _freeze_exact_value(original.blocking_refs, object_ids)),
                ),
            )
            if prior_object_ids.intersection(object_ids):
                raise TypeError
            prior_object_ids.update(object_ids)
            frozen_work.append(frozen)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        if isinstance(error, HKCaseRecordAccountingError):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID
        ) from None
    if type(authority_graph) is not HKCaseAuthorityGraph:
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID)
    try:
        selections_value = object.__getattribute__(authority_graph, "selections")
        if not _is_selection_tuple(selections_value):
            raise TypeError
        selection_outputs = tuple(
            _OriginalAuthorityOutput(
                item,
                object.__getattribute__(item, "issuance"),
            )
            for item in selections_value
        )
        authority_outputs = (
            *selection_outputs,
            _OriginalAuthorityOutput(
                authority_graph,
                object.__getattribute__(authority_graph, "issuance"),
            ),
        )
        frozen_graph = _freeze_exact_dataclass(authority_graph)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID
        ) from None
    return _CallerInputCapture(
        frozen_request,
        inventory_projection,
        tuple(frozen_work),
        frozen_graph,
        tuple(originals),
        authority_outputs,
        tuple(
            _capture_identity_tree(value)
            for value in (request, inventory_projection, listing_work, authority_graph)
        ),
    )


def _freeze_exact_dataclass(value: object) -> _FrozenCallerObject:
    frozen = _freeze_exact_value(value, set())
    if type(frozen) is not _FrozenCallerObject:
        raise TypeError
    return frozen


def _freeze_exact_value(value: object, object_ids: set[int]) -> object:
    """Copy an allow-listed exact tree without validation, equality, or methods."""
    value_type = type(value)
    if value_type in {str, bytes, int, bool, type(None)}:
        return value
    if _is_object_tuple(value):
        return tuple(_freeze_exact_value(item, object_ids) for item in value)
    if value_type in _CAPTURE_ENUM_TYPES or value_type is HKCaseReleaseRunKind:
        return value
    allowed_local = {HKCaseRecordAccountingRequest, HKCaseListingWork}
    if value_type not in _CAPTURE_DATACLASS_TYPES and value_type not in allowed_local:
        raise TypeError
    object_ids.add(id(value))
    return _FrozenCallerObject(
        value_type,
        tuple(
            (
                field_name,
                _freeze_exact_value(
                    object.__getattribute__(value, field_name),
                    object_ids,
                ),
            )
            for field_name in _dataclass_field_names(value_type)
        ),
    )


def _dataclass_field_names(value_type: type[object]) -> tuple[str, ...]:
    declared = vars(value_type).get("__dataclass_fields__")
    if not _is_object_dict(declared) or any(type(name) is not str for name in declared):
        raise TypeError
    return tuple(declared)


def _thaw_exact_dataclass(value: _FrozenCallerObject) -> object:
    thawed = _thaw_exact_value(value)
    if type(thawed) is not value.object_type:
        raise TypeError
    return thawed


def _thaw_exact_value(value: object) -> object:
    if _is_frozen_caller_object(value):
        thawed = object.__new__(value.object_type)
        for field_name, field_value in value.attributes:
            object.__setattr__(thawed, field_name, _thaw_exact_value(field_value))
        return thawed
    if _is_object_tuple(value):
        return tuple(_thaw_exact_value(item) for item in value)
    return value


def _same_frozen_value(left: object, right: object) -> bool:
    """Compare private snapshots without dispatching caller equality methods."""
    if type(left) is not type(right):
        return False
    if _is_frozen_caller_object(left):
        if not _is_frozen_caller_object(right):
            return False
        if left.object_type is not right.object_type or len(left.attributes) != len(
            right.attributes
        ):
            return False
        return all(
            left_name == right_name and _same_frozen_value(left_value, right_value)
            for (left_name, left_value), (right_name, right_value) in zip(
                left.attributes,
                right.attributes,
                strict=True,
            )
        )
    if _is_object_tuple(left):
        if not _is_object_tuple(right):
            return False
        return len(left) == len(right) and all(
            _same_frozen_value(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if type(left) in _CAPTURE_ENUM_TYPES or type(left) is HKCaseReleaseRunKind:
        return left is right
    return bool(left == right)


def _capture_identity_tree(value: object) -> _CallerIdentityNode:
    """Capture every exact dataclass/tuple/bytes identity with closed field coverage."""
    if _is_object_tuple(value):
        return _CallerIdentityNode(
            value,
            tuple((str(index), _capture_identity_tree(item)) for index, item in enumerate(value)),
        )
    value_type = type(value)
    if value_type in _CAPTURE_DATACLASS_TYPES or value_type in {
        HKCaseRecordAccountingRequest,
        HKCaseListingWork,
    }:
        return _CallerIdentityNode(
            value,
            tuple(
                (
                    field_name,
                    _capture_identity_tree(object.__getattribute__(value, field_name)),
                )
                for field_name in _dataclass_field_names(value_type)
            ),
        )
    return _CallerIdentityNode(value, ())


def _assert_identity_tree(node: _CallerIdentityNode) -> None:
    """Reject equal replacements before structural drift comparison."""
    value = node.reference
    if not node.children:
        return
    if _is_object_tuple(value):
        if len(value) != len(node.children):
            raise TypeError
        for (index_text, child), current in zip(node.children, value, strict=True):
            if int(index_text) < 0 or (
                _identity_bearing(child.reference) and current is not child.reference
            ):
                raise TypeError
            _assert_identity_tree(child)
        return
    names = _dataclass_field_names(type(value))
    if names != tuple(name for name, _ in node.children):
        raise TypeError
    for name, child in node.children:
        current = object.__getattribute__(value, name)
        if _identity_bearing(child.reference) and current is not child.reference:
            raise TypeError
        _assert_identity_tree(child)


def _identity_bearing(value: object) -> bool:
    value_type = type(value)
    return (
        _is_object_tuple(value)
        or value_type is bytes
        or value_type in _CAPTURE_DATACLASS_TYPES
        or value_type in {HKCaseRecordAccountingRequest, HKCaseListingWork}
    )


def _replay_original_listing_work(originals: tuple[_OriginalListingWork, ...]) -> None:
    """Replay original process-local issuance only after global detached capture."""
    try:
        for original in originals:
            if original.bundle is not None:
                original.bundle.__post_init__()
            if original.admission is not None:
                original.admission.__post_init__()
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        if isinstance(error, HKCaseRecordAccountingError):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID
        ) from None


def _detached_authority_graph_states(
    detached: HKCaseAuthorityGraph,
    originals: tuple[_OriginalAuthorityOutput, ...],
) -> dict[str, HKCaseAuthoritySelectionState]:
    """Validate the complete detached graph projection before live provenance replay."""
    try:
        selections = object.__getattribute__(detached, "selections")
        if not _is_selection_tuple(selections):
            raise TypeError
        identities: list[str] = []
        states: dict[str, HKCaseAuthoritySelectionState] = {}
        selection_documents: list[dict[str, object]] = []
        if len(originals) != len(selections) + 1:
            raise TypeError
        for item, original in zip(selections, originals[:-1], strict=True):
            proposition_id = _identity(object.__getattribute__(item, "proposition_id"))
            state = object.__getattribute__(item, "state")
            authority_note_required = object.__getattribute__(item, "authority_note_required")
            if (
                type(state) is not HKCaseAuthoritySelectionState
                or type(authority_note_required) is not bool
                or (authority_note_required and state is not HKCaseAuthoritySelectionState.CURRENT)
            ):
                raise TypeError
            selection_document: dict[str, object] = {
                "authority_note_required": authority_note_required,
                "proposition_id": proposition_id,
                "state": state.value,
            }
            _detached_authority_issuance(
                object.__getattribute__(item, "issuance"),
                kind="SELECTION",
                projection=_canonical(selection_document),
            )
            _validate_original_authority_issuance(
                original,
                kind="SELECTION",
                projection=_canonical(selection_document),
            )
            identities.append(proposition_id)
            states[proposition_id] = state
            selection_documents.append(selection_document)
        if len(identities) != len(set(identities)):
            raise TypeError
        quarantined_edge_ids_value = object.__getattribute__(detached, "quarantined_edge_ids")
        if not _is_object_tuple(quarantined_edge_ids_value) or any(
            type(item) is not str or not item for item in quarantined_edge_ids_value
        ):
            raise TypeError
        quarantined_edge_ids = quarantined_edge_ids_value
        if len(quarantined_edge_ids) != len(set(quarantined_edge_ids)):
            raise TypeError
        graph_document: dict[str, object] = {
            "quarantined_edge_ids": list(quarantined_edge_ids),
            "selections": selection_documents,
        }
        _detached_authority_issuance(
            object.__getattribute__(detached, "issuance"),
            kind="GRAPH",
            projection=_canonical(graph_document),
        )
        _validate_original_authority_issuance(
            originals[-1],
            kind="GRAPH",
            projection=_canonical(graph_document),
        )
        return states
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID
        ) from None


def _detached_authority_issuance(
    issuance: object,
    *,
    kind: str,
    projection: bytes,
) -> None:
    """Bind one detached output's complete primitives to its captured issuance."""
    if type(issuance) is not _AUTHORITY_OUTPUT_ISSUANCE_TYPE:
        raise TypeError
    if (
        object.__getattribute__(issuance, "kind") != kind
        or object.__getattribute__(issuance, "projection") != projection
    ):
        raise TypeError


def _validate_original_authority_issuance(
    original: _OriginalAuthorityOutput,
    *,
    kind: str,
    projection: bytes,
) -> None:
    """Ask Task 4 to bind the phase-one witness identity to its exact result."""
    if object.__getattribute__(original.output, "issuance") is not original.issuance:
        raise TypeError
    _call_owner_validator(
        _AUTHORITY_OUTPUT_ISSUANCE_VALIDATOR,
        original.output,
        kind,
        projection,
    )


def _validate_original_admission_issuance(
    originals: tuple[_OriginalListingWork, ...],
) -> None:
    """Ask Task 3 to bind every captured result and witness before live replay."""
    try:
        for original in originals:
            if original.admission is None:
                continue
            if (
                object.__getattribute__(original.admission, "issuance")
                is not original.admission_issuance
            ):
                raise TypeError
            _call_owner_validator(
                _PROPOSITION_ADMISSION_ISSUANCE_VALIDATOR,
                original.admission,
            )
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID
        ) from None


def _call_owner_validator(validator: object, *arguments: object) -> None:
    """Call one import-time-validated owner function without a static cast."""
    if not callable(validator):
        raise TypeError
    validator(*arguments)


def _replay_original_authority_graph(original: HKCaseAuthorityGraph) -> None:
    """Replay live process-local graph issuance only after detached validation."""
    try:
        replay_hk_case_authority_graph(original)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID
        ) from None


def _assert_caller_work_unchanged(
    caller: _CallerInputCapture,
    authority_graph: HKCaseAuthorityGraph,
) -> None:
    """Reject permanent replay drift; restored transient values remain harmless."""
    try:
        for index, root in enumerate(caller.identity_roots):
            try:
                _assert_identity_tree(root)
            except Exception as error:
                if index == _AUTHORITY_GRAPH_IDENTITY_ROOT_INDEX:
                    raise HKCaseRecordAccountingError(
                        HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID
                    ) from error
                raise
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        if isinstance(error, HKCaseRecordAccountingError):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID
        ) from None
    try:
        for original, expected in zip(
            caller.originals,
            caller.listing_work,
            strict=True,
        ):
            current = _freeze_exact_dataclass(original.item)
            if not _same_frozen_value(current, expected):
                raise TypeError
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID
        ) from None
    try:
        current_graph = _freeze_exact_dataclass(authority_graph)
        if not _same_frozen_value(current_graph, caller.authority_graph):
            raise TypeError
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID
        ) from None


def _request_snapshot(request: HKCaseRecordAccountingRequest) -> _RequestSnapshot:
    if type(request) is not HKCaseRecordAccountingRequest:
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.REQUEST_INVALID)
    snapshot = _RequestSnapshot(
        object.__getattribute__(request, "scope_id"),
        object.__getattribute__(request, "court_family"),
        object.__getattribute__(request, "calendar_year"),
        object.__getattribute__(request, "observation_cutoff"),
        object.__getattribute__(request, "run_kind"),
        object.__getattribute__(request, "prior_release_id"),
    )
    try:
        _identity(snapshot.scope_id)
        if type(snapshot.court_family) is not str or snapshot.court_family not in _COURTS:
            raise TypeError
        if (
            type(snapshot.calendar_year) is not int
            or not _EARLIEST_V1_YEAR <= snapshot.calendar_year <= _MAXIMUM_YEAR
            or _utc(snapshot.observation_cutoff).date().year < snapshot.calendar_year
            or type(snapshot.run_kind) is not HKCaseReleaseRunKind
        ):
            raise TypeError
        if snapshot.run_kind is HKCaseReleaseRunKind.INITIAL:
            if snapshot.prior_release_id is not None:
                raise TypeError
        elif snapshot.prior_release_id is None:
            raise TypeError
        else:
            _identity(snapshot.prior_release_id)
    except HKCaseRecordAccountingError:
        raise
    except Exception:
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.REQUEST_INVALID) from None
    return snapshot


def _listing_work_capture(
    listing_work: tuple[HKCaseListingWork, ...],
) -> tuple[_ListingWorkCapture, ...]:
    if type(listing_work) is not tuple or any(
        type(item) is not HKCaseListingWork for item in listing_work
    ):
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID)
    try:
        captures: list[_ListingWorkCapture] = []
        for item in listing_work:
            listing_id = object.__getattribute__(item, "listing_id")
            bundle = object.__getattribute__(item, "bundle")
            admission = object.__getattribute__(item, "admission")
            blocking_refs = object.__getattribute__(item, "blocking_refs")
            _identity(listing_id)
            if type(bundle) not in {HKCaseJudgmentBundle, type(None)} or type(admission) not in {
                HKCasePropositionAdmissionResult,
                type(None),
            }:
                raise TypeError
            if bundle is not None:
                bundle.__post_init__()
            snapshot = _ListingWorkSnapshot(
                listing_id,
                None if bundle is None else _bundle_snapshot(bundle),
                None if admission is None else _admission_snapshot(admission),
                _texts(blocking_refs, allow_empty=True),
            )
            captures.append(_ListingWorkCapture(snapshot))
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID
        ) from None
    return tuple(captures)


def _bundle_snapshot(bundle: HKCaseJudgmentBundle) -> _BundleSnapshot:
    """Detach every Task 1 primitive, including transient judgment text."""
    if type(bundle) is not HKCaseJudgmentBundle:
        raise TypeError
    listing_id = _identity(object.__getattribute__(bundle, "listing_id"))
    disposition = object.__getattribute__(bundle, "disposition")
    judgment = object.__getattribute__(bundle, "judgment")
    translations_value = object.__getattribute__(bundle, "translations")
    bundle_fingerprint = _fingerprint(object.__getattribute__(bundle, "bundle_fingerprint"))
    if type(disposition) is not HKCaseJudgmentDisposition or not _is_translation_tuple(
        translations_value
    ):
        raise TypeError
    translations = translations_value
    translation_documents = tuple(_translation_snapshot(item) for item in translations)
    if judgment is None:
        judgment_document = None
        judgment_id = court_id = decision_date = None
        opinion_refs: tuple[str, ...] = ()
    else:
        if type(judgment) is not HKCaseJudgment:
            raise TypeError
        judgment_document, judgment_id, court_id, decision_date, opinion_refs = _judgment_snapshot(
            judgment
        )
    translation_refs = tuple(item[1] for item in translation_documents)
    complete_projection = _canonical(
        {
            "listing_id": listing_id,
            "disposition": disposition.value,
            "judgment": judgment_document,
            "translations": [item[0] for item in translation_documents],
            "bundle_fingerprint": bundle_fingerprint,
        }
    )
    return _BundleSnapshot(
        listing_id,
        disposition,
        judgment_id,
        court_id,
        decision_date,
        tuple(sorted({*opinion_refs, *translation_refs})),
        bundle_fingerprint,
        complete_projection,
    )


def _judgment_snapshot(
    judgment: HKCaseJudgment,
) -> tuple[dict[str, object], str, str, str, tuple[str, ...]]:
    judgment_id = _identity(object.__getattribute__(judgment, "judgment_id"))
    case_name = _nonempty_text(object.__getattribute__(judgment, "case_name"))
    court_id = object.__getattribute__(judgment, "court_id")
    if type(court_id) is not str or court_id not in _COURTS:
        raise TypeError
    decision_date = _date_text(object.__getattribute__(judgment, "decision_date"))
    neutral = _strings(object.__getattribute__(judgment, "neutral_citations"), allow_empty=True)
    reported = _strings(object.__getattribute__(judgment, "reported_citations"), allow_empty=True)
    proceedings = _strings(
        object.__getattribute__(judgment, "proceeding_numbers"), allow_empty=True
    )
    opinions_value = object.__getattribute__(judgment, "opinions")
    if not _is_opinion_tuple(opinions_value):
        raise TypeError
    opinions = opinions_value
    opinion_documents = tuple(_opinion_snapshot(item) for item in opinions)
    document: dict[str, object] = {
        "judgment_id": judgment_id,
        "case_name": case_name,
        "court_id": court_id,
        "decision_date": decision_date,
        "neutral_citations": list(neutral),
        "reported_citations": list(reported),
        "proceeding_numbers": list(proceedings),
        "opinions": [item[0] for item in opinion_documents],
    }
    return (
        document,
        judgment_id,
        court_id,
        decision_date,
        tuple(item[1] for item in opinion_documents),
    )


def _opinion_snapshot(opinion: HKCaseJudgmentOpinion) -> tuple[dict[str, object], str]:
    if type(opinion) is not HKCaseJudgmentOpinion:
        raise TypeError
    paragraphs_value = object.__getattribute__(opinion, "paragraphs")
    if not _is_paragraph_tuple(paragraphs_value):
        raise TypeError
    paragraphs = paragraphs_value
    evidence_ref = _identity(object.__getattribute__(opinion, "evidence_ref"))
    return (
        {
            "opinion_id": _identity(object.__getattribute__(opinion, "opinion_id")),
            "judge_names": list(_strings(object.__getattribute__(opinion, "judge_names"))),
            "opinion_role": _nonempty_text(object.__getattribute__(opinion, "opinion_role")),
            "language": _nonempty_text(object.__getattribute__(opinion, "language")),
            "paragraphs": [_paragraph_snapshot(item) for item in paragraphs],
            "evidence_ref": evidence_ref,
            "evidence_fingerprint": _fingerprint(
                object.__getattribute__(opinion, "evidence_fingerprint")
            ),
            "evidence_byte_length": _positive_int(
                object.__getattribute__(opinion, "evidence_byte_length")
            ),
            "content_fingerprint": _fingerprint(
                object.__getattribute__(opinion, "content_fingerprint")
            ),
        },
        evidence_ref,
    )


def _translation_snapshot(
    translation: HKCaseJudgmentTranslation,
) -> tuple[dict[str, object], str]:
    if type(translation) is not HKCaseJudgmentTranslation:
        raise TypeError
    paragraphs_value = object.__getattribute__(translation, "paragraphs")
    if not _is_paragraph_tuple(paragraphs_value):
        raise TypeError
    paragraphs = paragraphs_value
    evidence_ref = _identity(object.__getattribute__(translation, "evidence_ref"))
    return (
        {
            "translation_id": _identity(object.__getattribute__(translation, "translation_id")),
            "opinion_id": _identity(object.__getattribute__(translation, "opinion_id")),
            "language": _nonempty_text(object.__getattribute__(translation, "language")),
            "paragraphs": [_paragraph_snapshot(item) for item in paragraphs],
            "evidence_ref": evidence_ref,
            "evidence_fingerprint": _fingerprint(
                object.__getattribute__(translation, "evidence_fingerprint")
            ),
            "evidence_byte_length": _positive_int(
                object.__getattribute__(translation, "evidence_byte_length")
            ),
            "content_fingerprint": _fingerprint(
                object.__getattribute__(translation, "content_fingerprint")
            ),
        },
        evidence_ref,
    )


def _paragraph_snapshot(paragraph: HKCaseJudgmentParagraph) -> dict[str, object]:
    if type(paragraph) is not HKCaseJudgmentParagraph:
        raise TypeError
    return {
        "paragraph_id": _identity(object.__getattribute__(paragraph, "paragraph_id")),
        "locator": _nonempty_text(object.__getattribute__(paragraph, "locator")),
        "text": _nonempty_text(object.__getattribute__(paragraph, "text")),
    }


def _admission_snapshot(
    admission: HKCasePropositionAdmissionResult,
) -> _AdmissionSnapshot:
    """Detach the complete canonical Task 3 projection plus every consumed primitive."""
    if type(admission) is not HKCasePropositionAdmissionResult:
        raise TypeError
    disposition = object.__getattribute__(admission, "disposition")
    if type(disposition) is not HKCasePropositionAdmissionDisposition:
        raise TypeError
    projection = object.__getattribute__(admission, "admission_projection")
    if type(projection) is not bytes or not projection:
        raise TypeError
    request_pair = object.__getattribute__(admission, "request_pair")
    admitted_decision = object.__getattribute__(admission, "admitted_decision")
    if (
        type(request_pair) is not HKCasePropositionRequestPair
        or type(admitted_decision) is not HKCaseAdmittedSemanticDecision
    ):
        raise TypeError
    decision = object.__getattribute__(request_pair, "decision")
    if type(decision) is not HKCasePropositionSemanticRequest:
        raise TypeError
    subject_id = _identity(object.__getattribute__(decision, "subject_id"))
    judgment_fingerprint = _fingerprint(
        object.__getattribute__(request_pair, "judgment_fingerprint")
    )
    propositions = object.__getattribute__(admission, "propositions")
    admitted_propositions = object.__getattribute__(admitted_decision, "propositions")
    if (
        not _is_object_tuple(propositions)
        or not _is_object_tuple(admitted_propositions)
        or any(type(item) is not HKCaseAdmittedProposition for item in propositions)
        or any(type(item) is not HKCaseAdmittedProposition for item in admitted_propositions)
    ):
        raise TypeError
    proposition_ids = tuple(
        _identity(object.__getattribute__(item, "proposition_id")) for item in propositions
    )
    admitted_proposition_ids = tuple(
        _identity(object.__getattribute__(item, "proposition_id")) for item in admitted_propositions
    )
    evidence_refs = _texts(object.__getattribute__(decision, "evidence_refs"))
    if (
        proposition_ids != admitted_proposition_ids
        or replay_hk_case_proposition_admission_projection(
            request_pair,
            admitted_decision,
        )
        != projection
        or _fingerprint_bytes(projection)
        != object.__getattribute__(admission, "admission_fingerprint")
    ):
        raise TypeError
    return _AdmissionSnapshot(
        disposition,
        subject_id,
        judgment_fingerprint,
        tuple(sorted(proposition_ids)),
        evidence_refs,
        _fingerprint(object.__getattribute__(admission, "admission_fingerprint")),
        projection,
    )


def _inventory_snapshot(projection: bytes) -> _InventorySnapshot:
    try:
        if (
            type(projection) is not bytes
            or not projection
            or len(projection) > _MAX_INVENTORY_PROJECTION_BYTES
        ):
            raise TypeError
        document_value = _parse_projection(projection)
        if not _is_object_dict(document_value) or _canonical(document_value) != projection:
            raise TypeError
        document = document_value
        required = {
            "schema_id",
            "source_inventory_fingerprint",
            "court_family",
            "earliest_decision_date",
            "observation_cutoff",
            "entries",
            "projection_fingerprint",
        }
        if set(document) != required or document["schema_id"] != _INVENTORY_PROJECTION_SCHEMA:
            raise TypeError
        fingerprint = _fingerprint(document["source_inventory_fingerprint"])
        projection_fingerprint = _fingerprint(document["projection_fingerprint"])
        fingerprint_facts = dict(document)
        del fingerprint_facts["projection_fingerprint"]
        if projection_fingerprint != _fingerprint_bytes(_canonical(fingerprint_facts)):
            raise TypeError
        court = document["court_family"]
        if type(court) is not str or court not in _COURTS:
            raise TypeError
        earliest = _date_text(document["earliest_decision_date"])
        cutoff = _utc_text(document["observation_cutoff"])
        entries_value = document["entries"]
        if not _is_object_list(entries_value) or len(entries_value) > _MAX_INVENTORY_ENTRIES:
            raise TypeError
        entries = entries_value
        facts = tuple(_inventory_entry_from_document(entry) for entry in entries)
        ids = tuple(item.listing_id for item in facts)
        if facts != tuple(sorted(facts, key=lambda item: item.listing_id)) or len(ids) != len(
            set(ids)
        ):
            raise TypeError
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.INVENTORY_INVALID
        ) from None
    return _InventorySnapshot(court, earliest, cutoff, fingerprint, facts)


def _inventory_entry_from_document(document: object) -> _InventoryFact:
    if not _is_object_dict(document) or set(document) != {
        "listing_identity",
        "court_family",
        "decision_date",
        "listing_fact_fingerprint",
    }:
        raise TypeError
    listing_id = _identity(document["listing_identity"])
    court = document["court_family"]
    if type(court) is not str or court not in _COURTS:
        raise TypeError
    return _InventoryFact(
        listing_id,
        court,
        _date_text(document["decision_date"]),
        _fingerprint(document["listing_fact_fingerprint"]),
    )


def _inventory_matches_request(inventory: _InventorySnapshot, request: _RequestSnapshot) -> None:
    if (
        inventory.court_family != request.court_family
        or inventory.earliest_decision_date != _EARLIEST_V1_DATE.isoformat()
        or inventory.observation_cutoff != request.observation_cutoff
        or any(entry.court_family != request.court_family for entry in inventory.entries)
    ):
        raise HKCaseRecordAccountingError(HKCaseRecordAccountingErrorCode.INVENTORY_SCOPE_MISMATCH)


def _work_fact(work: _ListingWorkSnapshot, entry: _InventoryFact) -> _WorkFact:
    try:
        if work.listing_id != entry.listing_id:
            raise TypeError
        blocking_refs = _texts(work.blocking_refs, allow_empty=True)
        bundle = work.bundle
        admission = work.admission
        if bundle is None:
            if admission is not None or not blocking_refs:
                raise TypeError
            return _WorkFact(
                work.listing_id,
                HKCaseListingRecordDisposition.JUDGMENT_BUNDLE_BLOCKED,
                None,
                None,
                (),
                (),
                blocking_refs,
            )
        if bundle.listing_id != work.listing_id:
            raise TypeError
        bundle_fingerprint = _fingerprint(bundle.bundle_fingerprint)
        if bundle.disposition is HKCaseJudgmentDisposition.OUT_OF_V1_DATE_SCOPE:
            if (
                admission is not None
                or blocking_refs
                or date.fromisoformat(entry.decision_date) >= _EARLIEST_V1_DATE
            ):
                raise TypeError
            return _WorkFact(
                work.listing_id,
                HKCaseListingRecordDisposition.OUT_OF_V1_DATE_SCOPE,
                bundle_fingerprint,
                None,
                (),
                (),
                (),
            )
        if (
            bundle.disposition is not HKCaseJudgmentDisposition.LOADED
            or bundle.judgment_id is None
            or bundle.court_id != entry.court_family
            or bundle.decision_date != entry.decision_date
        ):
            raise TypeError
        evidence_refs = bundle.evidence_refs
        _texts(evidence_refs)
        if admission is None:
            if not blocking_refs:
                raise TypeError
            return _WorkFact(
                work.listing_id,
                HKCaseListingRecordDisposition.PROPOSITION_ADMISSION_BLOCKED,
                bundle_fingerprint,
                None,
                (),
                evidence_refs,
                blocking_refs,
            )
        if blocking_refs:
            raise TypeError
        if (
            admission.judgment_subject_id != bundle.judgment_id
            or admission.judgment_fingerprint != bundle_fingerprint
        ):
            raise TypeError
        proposition_ids = admission.proposition_ids
        _texts(proposition_ids, allow_empty=True)
        if len(proposition_ids) != len(set(proposition_ids)):
            raise TypeError
        admission_evidence = _texts(admission.evidence_refs)
        evidence_refs = tuple(sorted(set(evidence_refs).union(admission_evidence)))
        if (
            admission.disposition
            is HKCasePropositionAdmissionDisposition.COMPLETE_ZERO_PROPOSITIONS
        ):
            if proposition_ids:
                raise TypeError
            disposition = HKCaseListingRecordDisposition.COMPLETE_ZERO_PROPOSITIONS
        elif (
            admission.disposition is HKCasePropositionAdmissionDisposition.COMPLETE_PROPOSITIONS
            and proposition_ids
        ):
            disposition = HKCaseListingRecordDisposition.AUTHORITY_QUARANTINED
        else:
            raise TypeError
        return _WorkFact(
            work.listing_id,
            disposition,
            bundle_fingerprint,
            _fingerprint(admission.admission_fingerprint),
            proposition_ids,
            evidence_refs,
            (),
        )
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        if isinstance(error, HKCaseRecordAccountingError):
            raise
        raise HKCaseRecordAccountingError(
            HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID
        ) from None


def _listing_accounting_facts(row: HKCaseListingRecordAccounting) -> None:
    _identity(row.listing_id)
    _fingerprint(row.source_listing_fingerprint)
    if type(row.disposition) is not HKCaseListingRecordDisposition:
        raise TypeError
    if row.bundle_fingerprint is not None:
        _fingerprint(row.bundle_fingerprint)
    if row.admission_fingerprint is not None:
        _fingerprint(row.admission_fingerprint)
    propositions = _texts(row.proposition_ids, allow_empty=True)
    quarantined = _texts(row.quarantined_proposition_ids, allow_empty=True)
    evidence = _texts(row.evidence_refs, allow_empty=True)
    blocking = _texts(row.blocking_refs, allow_empty=True)
    if any(
        items != tuple(sorted(set(items)))
        for items in (propositions, quarantined, evidence, blocking)
    ):
        raise TypeError
    if row.disposition is HKCaseListingRecordDisposition.JUDGMENT_BUNDLE_BLOCKED:
        valid = (
            row.bundle_fingerprint is None
            and row.admission_fingerprint is None
            and not propositions
            and not quarantined
            and not evidence
            and bool(blocking)
        )
    elif row.disposition is HKCaseListingRecordDisposition.PROPOSITION_ADMISSION_BLOCKED:
        valid = (
            row.bundle_fingerprint is not None
            and row.admission_fingerprint is None
            and not propositions
            and not quarantined
            and bool(evidence)
            and bool(blocking)
        )
    elif row.disposition is HKCaseListingRecordDisposition.COMPLETE_ZERO_PROPOSITIONS:
        valid = (
            row.bundle_fingerprint is not None
            and row.admission_fingerprint is not None
            and not propositions
            and not quarantined
            and bool(evidence)
            and not blocking
        )
    elif row.disposition is HKCaseListingRecordDisposition.AUTHORITY_QUARANTINED:
        valid = (
            row.bundle_fingerprint is not None
            and row.admission_fingerprint is not None
            and bool(propositions)
            and quarantined == propositions
            and bool(evidence)
            and not blocking
        )
    else:
        valid = (
            row.bundle_fingerprint is not None
            and row.admission_fingerprint is None
            and not propositions
            and not quarantined
            and not evidence
            and not blocking
        )
    if not valid:
        raise TypeError


def _checkpoint_facts(checkpoint: HKCaseRecordAccountingCheckpoint) -> None:
    request = HKCaseRecordAccountingRequest(
        checkpoint.scope_id,
        checkpoint.court_family,
        checkpoint.calendar_year,
        checkpoint.observation_cutoff,
        checkpoint.run_kind,
        checkpoint.prior_release_id,
    )
    request.__post_init__()
    _fingerprint(checkpoint.inventory_fingerprint)
    rows = checkpoint.listing_accounting
    if type(rows) is not tuple or any(
        type(row) is not HKCaseListingRecordAccounting for row in rows
    ):
        raise TypeError
    for row in rows:
        row.__post_init__()
    ids = tuple(row.listing_id for row in rows)
    if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
        raise TypeError
    if (
        type(checkpoint.listing_count) is not int
        or type(checkpoint.disposition_count) is not int
        or type(checkpoint.zero_proposition_count) is not int
        or checkpoint.listing_count != len(rows)
        or checkpoint.disposition_count != len(rows)
        or checkpoint.zero_proposition_count
        != sum(
            row.disposition is HKCaseListingRecordDisposition.COMPLETE_ZERO_PROPOSITIONS
            for row in rows
        )
    ):
        raise TypeError
    quarantine_ids = tuple(
        row.listing_id
        for row in rows
        if row.disposition is HKCaseListingRecordDisposition.AUTHORITY_QUARANTINED
    )
    blocked_ids = tuple(
        row.listing_id
        for row in rows
        if row.disposition
        in {
            HKCaseListingRecordDisposition.JUDGMENT_BUNDLE_BLOCKED,
            HKCaseListingRecordDisposition.PROPOSITION_ADMISSION_BLOCKED,
        }
    )
    if (
        checkpoint.quarantine_listing_ids != quarantine_ids
        or checkpoint.blocked_listing_ids != blocked_ids
        or checkpoint.blockers != _REQUIRED_BLOCKERS
        or checkpoint.checkpoint_fingerprint
        != _fingerprint_bytes(
            _canonical(_checkpoint_document(checkpoint, include_fingerprint=False))
        )
    ):
        raise TypeError


def _checkpoint_document(
    checkpoint: HKCaseRecordAccountingCheckpoint, *, include_fingerprint: bool
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_id": "asklegal.hk-case-record-accounting-checkpoint/v1",
        "scope_id": checkpoint.scope_id,
        "court_family": checkpoint.court_family,
        "calendar_year": checkpoint.calendar_year,
        "observation_cutoff": checkpoint.observation_cutoff,
        "run_kind": checkpoint.run_kind.value,
        "prior_release_id": checkpoint.prior_release_id,
        "inventory_fingerprint": checkpoint.inventory_fingerprint,
        "listing_accounting": [
            {
                "listing_id": row.listing_id,
                "source_listing_fingerprint": row.source_listing_fingerprint,
                "disposition": row.disposition.value,
                "bundle_fingerprint": row.bundle_fingerprint,
                "admission_fingerprint": row.admission_fingerprint,
                "proposition_ids": list(row.proposition_ids),
                "quarantined_proposition_ids": list(row.quarantined_proposition_ids),
                "evidence_refs": list(row.evidence_refs),
                "blocking_refs": list(row.blocking_refs),
            }
            for row in checkpoint.listing_accounting
        ],
        "listing_count": checkpoint.listing_count,
        "disposition_count": checkpoint.disposition_count,
        "zero_proposition_count": checkpoint.zero_proposition_count,
        "quarantine_listing_ids": list(checkpoint.quarantine_listing_ids),
        "blocked_listing_ids": list(checkpoint.blocked_listing_ids),
        "blockers": [item.value for item in checkpoint.blockers],
    }
    if include_fingerprint:
        document["checkpoint_fingerprint"] = checkpoint.checkpoint_fingerprint
    return document


def _checkpoint_fingerprint_values(values: Mapping[str, object]) -> str:
    checkpoint = object.__new__(HKCaseRecordAccountingCheckpoint)
    for field_name, value in values.items():
        object.__setattr__(checkpoint, field_name, value)
    object.__setattr__(checkpoint, "checkpoint_fingerprint", "")
    return _fingerprint_bytes(
        _canonical(_checkpoint_document(checkpoint, include_fingerprint=False))
    )


def _copy_checkpoint(
    checkpoint: HKCaseRecordAccountingCheckpoint,
) -> HKCaseRecordAccountingCheckpoint:
    return HKCaseRecordAccountingCheckpoint(
        checkpoint.scope_id,
        checkpoint.court_family,
        checkpoint.calendar_year,
        checkpoint.observation_cutoff,
        checkpoint.run_kind,
        checkpoint.prior_release_id,
        checkpoint.inventory_fingerprint,
        checkpoint.listing_accounting,
        checkpoint.listing_count,
        checkpoint.disposition_count,
        checkpoint.zero_proposition_count,
        checkpoint.quarantine_listing_ids,
        checkpoint.blocked_listing_ids,
        checkpoint.blockers,
        checkpoint.checkpoint_fingerprint,
    )


def _in_scope(decision_date: str, calendar_year: int) -> bool:
    parsed = date.fromisoformat(decision_date)
    start = _EARLIEST_V1_DATE if calendar_year == _EARLIEST_V1_YEAR else date(calendar_year, 1, 1)
    return start <= parsed <= date(calendar_year, 12, 31)


def _identity(value: object) -> str:
    if type(value) is not str or _IDENTITY.fullmatch(value) is None:
        raise TypeError
    return value


def _fingerprint(value: object) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        raise TypeError
    return value


def _nonempty_text(value: object) -> str:
    if type(value) is not str or not value:
        raise TypeError
    return value


def _positive_int(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise TypeError
    return value


def _texts(values: object, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not _is_object_tuple(values) or (not allow_empty and not values):
        raise TypeError
    return tuple(_identity(value) for value in values)


def _strings(values: object, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not _is_object_tuple(values) or (not allow_empty and not values):
        raise TypeError
    return tuple(_nonempty_text(value) for value in values)


def _is_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _is_frozen_caller_object(value: object) -> TypeIs[_FrozenCallerObject]:
    return type(value) is _FrozenCallerObject


def _is_selection_tuple(
    value: object,
) -> TypeIs[tuple[HKCaseAuthoritySelection, ...]]:
    return _is_object_tuple(value) and all(type(item) is HKCaseAuthoritySelection for item in value)


def _is_translation_tuple(
    value: object,
) -> TypeIs[tuple[HKCaseJudgmentTranslation, ...]]:
    return _is_object_tuple(value) and all(
        type(item) is HKCaseJudgmentTranslation for item in value
    )


def _is_opinion_tuple(value: object) -> TypeIs[tuple[HKCaseJudgmentOpinion, ...]]:
    return _is_object_tuple(value) and all(type(item) is HKCaseJudgmentOpinion for item in value)


def _is_paragraph_tuple(value: object) -> TypeIs[tuple[HKCaseJudgmentParagraph, ...]]:
    return _is_object_tuple(value) and all(type(item) is HKCaseJudgmentParagraph for item in value)


def _is_object_dict(value: object) -> TypeIs[dict[str, object]]:
    return type(value) is dict


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return type(value) is list


def _date_text(value: object) -> str:
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise TypeError
    return value


def _utc(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise TypeError
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if parsed.microsecond or parsed.isoformat().replace("+00:00", "Z") != value:
        raise TypeError
    return parsed


def _utc_text(value: object) -> str:
    if type(value) is not str:
        raise TypeError
    _utc(value)
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _parse_projection(projection: bytes) -> object:
    return json.loads(
        projection.decode("utf-8"),
        object_pairs_hook=_closed_json_object,
        parse_constant=_reject_json_constant,
    )


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError
        document[key] = value
    return document


def _reject_json_constant(value: str) -> object:
    del value
    raise ValueError


def _fingerprint_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


__all__ = [
    "HKCaseListingRecordAccounting",
    "HKCaseListingRecordDisposition",
    "HKCaseListingWork",
    "HKCaseRecordAccountingCheckpoint",
    "HKCaseRecordAccountingError",
    "HKCaseRecordAccountingErrorCode",
    "HKCaseRecordAccountingRequest",
    "HKCaseRecordBlockerCode",
    "HKCaseReleaseRunKind",
    "account_hk_case_records",
    "canonical_hk_case_record_accounting_checkpoint",
    "replay_hk_case_record_accounting_checkpoint",
]
