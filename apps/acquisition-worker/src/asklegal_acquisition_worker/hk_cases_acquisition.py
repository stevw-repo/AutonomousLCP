"""Deterministic, listing-first Hong Kong Cases acquisition planning.

This module owns only worker-local planning and manifest facts.  It does not
perform source reads, legal processing, provider calls, or release actions.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Never, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_source_connectors.hk_judiciary import (
    JudiciaryObservationKind,
    registered_judiciary_current_list_route,
    registered_judiciary_observation_contract,
)
from asklegal_source_connectors.hk_judiciary_authentic import (
    JudiciaryIncrementalObservation,
    JudiciaryYearPartition,
    JudiciaryYearResultPage,
    build_judiciary_next_result_url,
    parse_judiciary_current_list_observation,
    parse_judiciary_rss_observation,
    parse_judiciary_year_result_page,
    reconcile_judiciary_year_partition,
)

from asklegal_acquisition_worker.acquisition_journal import (
    AccountedExcludedPayload,
    AcquisitionCycleResult,
    DiscoveredPayload,
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    WorkItemIdentity,
)
from asklegal_acquisition_worker.resumable_acquisition import (
    AcquisitionClock,
    AcquisitionCycleReport,
    CaptureTransport,
    CycleBudget,
    ResumableAcquisitionRunner,
    RetainedObjectVerifier,
    ScheduledWorkItem,
    runner_verified_capture_bindings,
)
from asklegal_acquisition_worker.retained_evidence_import import (
    RetainedImportedObjectReference,
    RetainedImportReceipt,
)
from asklegal_acquisition_worker.source_role_evidence import (
    SourceRoleDisposition,
    validate_source_role_dispositions,
)

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_BUNDLE_REF = re.compile(r"^cases/judgment-bundles/sha256/[0-9a-f]{64}\.json$")
_RETAINED_PAGE = re.compile(r"^judiciary-year-(?P<year>[0-9]{4})-page-(?P<page>[1-9][0-9]*)$")
_RELATIONSHIP_KINDS = (
    "CORRECTION_ARTIFACT",
    "REISSUE_ARTIFACT",
    "LANGUAGE",
    "TRANSLATION_ARTIFACT",
    "LISTING_ALIAS",
    "PROCEEDING_IDENTITY",
)
_REF_PARTS = 5
_INVALID_PREFIX = "CASES_RETAINED_PREFIX_INVALID"
_EARLIEST_YEAR = 1997
_EARLIEST_DATE = "1997-07-01"
_CUTOFF = re.compile(r"^(?P<year>[0-9]{4})-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class RetainedJudiciaryEvidenceReader(Protocol):
    """Worker-local read-only boundary for an exact retained Judiciary object."""

    def read(self, reference: RetainedImportedObjectReference) -> bytes:
        """Read the exact imported object bound by the retained report."""
        raise NotImplementedError


class VerifiedCaptureEvidenceReader(Protocol):
    """Read an exact journal-bound capture after the shared runner verifies it."""

    def read_exact(self, object_ref: str, content_fingerprint: str, body_length: int) -> bytes:
        """Return only the exact retained body named by the runner binding."""
        raise NotImplementedError


class CasesWorkKind(StrEnum):
    """Closed worker roles for Cases enumeration and source-derived artifacts."""

    CURRENT_LIST_OBSERVATION = "CURRENT_LIST_OBSERVATION"
    RSS_OBSERVATION = "RSS_OBSERVATION"
    LISTING_PAGE = "LISTING_PAGE"
    JUDGMENT_ARTIFACT = "JUDGMENT_ARTIFACT"
    CORRECTION_ARTIFACT = "CORRECTION_ARTIFACT"
    REISSUE_ARTIFACT = "REISSUE_ARTIFACT"
    LANGUAGE = "LANGUAGE"
    TRANSLATION_ARTIFACT = "TRANSLATION_ARTIFACT"
    LISTING_ALIAS = "LISTING_ALIAS"
    PROCEEDING_IDENTITY = "PROCEEDING_IDENTITY"


class CasesCycleMode(StrEnum):
    """Closed scheduling intent; discovery signals never inherit reconciliation authority."""

    INCREMENTAL_DISCOVERY = "INCREMENTAL_DISCOVERY"
    FULL_RECONCILIATION = "FULL_RECONCILIATION"


@dataclass(frozen=True, slots=True)
class CasesWorkNode:
    """One canonical node; dependencies are node keys, not caller-created work IDs."""

    key: str
    kind: CasesWorkKind
    endpoint_id: str
    endpoint_version: str
    year: int
    page: int
    scheduled: ScheduledWorkItem
    depends_on: tuple[str, ...]
    captures_body: bool = True


@dataclass(frozen=True, slots=True)
class CasesListingOccurrence:
    """One listing-row relationship record; physical capture may be shared."""

    key: str
    listing_node_key: str
    dis_id: int
    judgment_node_key: str
    relationship_node_keys: tuple[str, ...]
    presentation_url: str | None
    reconciled_in_scope: bool


@dataclass(frozen=True, slots=True)
class CasesWorkGraph:
    """A deterministic initial graph; later verified listings expand it in new runs."""

    cycle_id: str
    observation_cutoff: str
    nodes: tuple[CasesWorkNode, ...]
    occurrences: tuple[CasesListingOccurrence, ...] = ()
    mode: CasesCycleMode = CasesCycleMode.FULL_RECONCILIATION
    reconciled_partitions: tuple[JudiciaryYearPartition, ...] = ()
    reconciliation_failures: tuple[int, ...] = ()

    @property
    def runner_dependencies(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Translate canonical node dependencies to the shared runner identities."""
        ids = {node.key: node.scheduled.identity.work_item_id for node in self.nodes}
        return tuple(
            (
                node.scheduled.identity.work_item_id,
                tuple(sorted(ids[key] for key in node.depends_on)),
            )
            for node in self.nodes
        )


class CasesJudgmentBundleStore(Protocol):
    """Worker-local immutable writer/read-back boundary for judgment bundles."""

    def conditional_create(self, object_ref: str, body: bytes) -> None:
        """Create only an absent immutable object, or prove identical content."""
        raise NotImplementedError

    def read(self, object_ref: str) -> bytes:
        """Read the exact object immediately after immutable creation."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RetainedJudiciaryPrefix:
    """Exact immutable listing-object facts imported from the verified W prefix."""

    source_attempt_id: str
    source_report_fingerprint: str
    authority_manifest_fingerprint: str
    execution_authorization_fingerprint: str
    observation_cutoff: str
    imported_listing_refs: tuple[tuple[str, str, str, str, int], ...]

    def __post_init__(self) -> None:
        """Require each prefix fact to name one exact retained listing object."""
        if (
            not self.source_attempt_id
            or not self.observation_cutoff
            or any(
                _FINGERPRINT.fullmatch(value) is None
                for value in (
                    self.source_report_fingerprint,
                    self.authority_manifest_fingerprint,
                    self.execution_authorization_fingerprint,
                )
            )
            or type(self.imported_listing_refs) is not tuple
            or not self.imported_listing_refs
        ):
            _invalid_prefix()
        seen: set[tuple[int, int]] = set()
        for value in self.imported_listing_refs:
            if type(value) is not tuple or len(value) != _REF_PARTS:
                _invalid_prefix()
            endpoint_id, locator, object_ref, fingerprint, length = value
            match = _RETAINED_PAGE.fullmatch(endpoint_id) if type(endpoint_id) is str else None
            if (
                match is None
                or type(locator) is not str
                or type(object_ref) is not str
                or type(fingerprint) is not str
                or _FINGERPRINT.fullmatch(fingerprint) is None
                or type(length) is not int
                or length <= 0
            ):
                _invalid_prefix()
            coordinate = (int(match.group("year")), int(match.group("page")))
            if coordinate in seen:
                _invalid_prefix()
            seen.add(coordinate)

    @property
    def last_listing(self) -> tuple[int, int]:
        """Return the last coordinate reconstructed from exact retained objects."""
        return max(_retained_coordinate(item[0]) for item in self.imported_listing_refs)

    @property
    def last_locator(self) -> str:
        """Return the final retained locator used only for sequential page construction."""
        year, page = self.last_listing
        matches = ((item, _RETAINED_PAGE.fullmatch(item[0])) for item in self.imported_listing_refs)
        return next(
            item[1]
            for item, match in matches
            if match is not None
            and match.group("year") == str(year)
            and match.group("page") == str(page)
        )


@dataclass(frozen=True, slots=True)
class CasesBaselinePlan:
    """The first retained-prefix successor work item and its immutable source facts."""

    retained_prefix: RetainedJudiciaryPrefix
    first_network_item: ScheduledWorkItem


@dataclass(frozen=True, slots=True)
class YearShardDisposition:
    """Canonical non-successful/successful accounting for one calendar-year shard."""

    year: int
    first_in_scope_date: str
    final_page: int
    verified_listing_pages: int
    discovered_judgments: int
    verified_judgments: int
    retryable_items: int
    result: AcquisitionCycleResult


@dataclass(frozen=True, slots=True)
class CasesAcquisitionManifest:
    """Complete acquisition facts required by later, separately admitted processing."""

    cycle_id: str
    earliest_decision_date: str
    observation_cutoff: str
    year_dispositions: tuple[YearShardDisposition, ...]
    judgment_bundle_refs: tuple[str, ...]
    discrepancy_refs: tuple[str, ...]
    journal_head_fingerprint: str
    result: AcquisitionCycleResult
    fingerprint: str
    source_dispositions: tuple[SourceRoleDisposition, ...] = ()

    def to_json(self) -> dict[str, JsonValue]:
        """Return exactly the fingerprinted manifest document, including its digest."""
        return {**_manifest_body(self), "fingerprint": self.fingerprint}

    @classmethod
    def from_json(cls, document: object) -> CasesAcquisitionManifest:
        """Read only one exact canonical manifest and recheck its displayed digest."""
        typed = checked_json_value(document)
        required_fields = {
            "cycle_id",
            "discrepancy_refs",
            "earliest_decision_date",
            "fingerprint",
            "journal_head_fingerprint",
            "judgment_bundle_refs",
            "observation_cutoff",
            "result",
            "year_dispositions",
        }
        if type(typed) is not dict or frozenset(typed) not in {
            frozenset(required_fields),
            frozenset((*required_fields, "source_dispositions")),
        }:
            _invalid_prefix()
        try:
            values = typed["year_dispositions"]
            if type(values) is not list:
                _invalid_prefix()
            shards = tuple(
                YearShardDisposition(
                    year=_integer(item["year"]),
                    first_in_scope_date=_text(item["first_in_scope_date"]),
                    final_page=_integer(item["final_page"]),
                    verified_listing_pages=_integer(item["verified_listing_pages"]),
                    discovered_judgments=_integer(item["discovered_judgments"]),
                    verified_judgments=_integer(item["verified_judgments"]),
                    retryable_items=_integer(item["retryable_items"]),
                    result=AcquisitionCycleResult(_text(item["result"])),
                )
                for item in values
                if type(item) is dict
                and set(item)
                == {
                    "discovered_judgments",
                    "final_page",
                    "first_in_scope_date",
                    "result",
                    "retryable_items",
                    "verified_judgments",
                    "verified_listing_pages",
                    "year",
                }
            )
            if len(shards) != len(values):
                _invalid_prefix()
            claimed_result = AcquisitionCycleResult(_text(typed["result"]))
            raw_sources = typed.get("source_dispositions", [])
            if type(raw_sources) is not list:
                _invalid_prefix()
            source_dispositions = validate_source_role_dispositions(
                tuple(SourceRoleDisposition.from_json(item) for item in raw_sources)
            )
            manifest = build_cases_acquisition_manifest(
                cycle_id=_text(typed["cycle_id"]),
                observation_cutoff=_text(typed["observation_cutoff"]),
                year_dispositions=shards,
                judgment_bundle_refs=_texts(typed["judgment_bundle_refs"]),
                discrepancy_refs=_texts(typed["discrepancy_refs"]),
                journal_head_fingerprint=_text(typed["journal_head_fingerprint"]),
                runner_result=(
                    None if claimed_result is AcquisitionCycleResult.NO_CHANGE else claimed_result
                ),
                source_dispositions=source_dispositions,
            )
            if claimed_result is AcquisitionCycleResult.NO_CHANGE:
                if manifest.result is not AcquisitionCycleResult.COMPLETE:
                    _invalid_prefix()
                provisional = CasesAcquisitionManifest(
                    cycle_id=manifest.cycle_id,
                    earliest_decision_date=manifest.earliest_decision_date,
                    observation_cutoff=manifest.observation_cutoff,
                    year_dispositions=manifest.year_dispositions,
                    judgment_bundle_refs=manifest.judgment_bundle_refs,
                    discrepancy_refs=manifest.discrepancy_refs,
                    journal_head_fingerprint=manifest.journal_head_fingerprint,
                    result=AcquisitionCycleResult.NO_CHANGE,
                    fingerprint="",
                    source_dispositions=manifest.source_dispositions,
                )
                manifest = CasesAcquisitionManifest(
                    cycle_id=provisional.cycle_id,
                    earliest_decision_date=provisional.earliest_decision_date,
                    observation_cutoff=provisional.observation_cutoff,
                    year_dispositions=provisional.year_dispositions,
                    judgment_bundle_refs=provisional.judgment_bundle_refs,
                    discrepancy_refs=provisional.discrepancy_refs,
                    journal_head_fingerprint=provisional.journal_head_fingerprint,
                    result=provisional.result,
                    fingerprint=f"sha256:{sha256(canonicalize(checked_json_value(_manifest_body(provisional)))).hexdigest()}",
                    source_dispositions=provisional.source_dispositions,
                )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(_INVALID_PREFIX) from error
        if (
            _text(typed["earliest_decision_date"]) != _EARLIEST_DATE
            or _text(typed["fingerprint"]) != manifest.fingerprint
        ):
            _invalid_prefix()
        return manifest


@dataclass(frozen=True, slots=True)
class CasesAcceptedPredecessorState:
    """Typed accepted source state against which a full reconciliation may prove equality."""

    manifest: CasesAcquisitionManifest
    accepted_ref: str
    fingerprint: str

    def __post_init__(self) -> None:
        """Reject a claimed acceptance not bound to its exact successful manifest."""
        if type(self.manifest) is not CasesAcquisitionManifest:
            _invalid_prefix()
        try:
            revalidated = CasesAcquisitionManifest.from_json(self.manifest.to_json())
        except TypeError, ValueError:
            _invalid_prefix()
        if (
            revalidated != self.manifest
            or self.manifest.result
            not in {AcquisitionCycleResult.COMPLETE, AcquisitionCycleResult.NO_CHANGE}
            or type(self.accepted_ref) is not str
            or not self.accepted_ref
            or self.fingerprint
            != _accepted_predecessor_fingerprint(self.manifest.fingerprint, self.accepted_ref)
        ):
            _invalid_prefix()

    @classmethod
    def issue(
        cls, manifest: CasesAcquisitionManifest, accepted_ref: str
    ) -> CasesAcceptedPredecessorState:
        """Bind one exact admitted predecessor manifest and its retained acceptance ref."""
        if type(manifest) is not CasesAcquisitionManifest or type(accepted_ref) is not str:
            _invalid_prefix()
        return cls(
            manifest,
            accepted_ref,
            _accepted_predecessor_fingerprint(manifest.fingerprint, accepted_ref),
        )


def _accepted_predecessor_fingerprint(manifest_fingerprint: str, accepted_ref: str) -> str:
    value = checked_json_value(
        {"accepted_ref": accepted_ref, "manifest_fingerprint": manifest_fingerprint}
    )
    return f"sha256:{sha256(canonicalize(value)).hexdigest()}"


def build_cases_acquisition_manifest(  # noqa: PLR0913 - mirrors the frozen manifest boundary.
    *,
    cycle_id: str,
    observation_cutoff: str,
    year_dispositions: tuple[YearShardDisposition, ...],
    judgment_bundle_refs: tuple[str, ...],
    discrepancy_refs: tuple[str, ...],
    journal_head_fingerprint: str,
    runner_result: AcquisitionCycleResult | None = None,
    cycle_mode: CasesCycleMode = CasesCycleMode.FULL_RECONCILIATION,
    accepted_predecessor: CasesAcceptedPredecessorState | None = None,
    source_dispositions: tuple[SourceRoleDisposition, ...] = (),
) -> CasesAcquisitionManifest:
    """Project only an exact complete inventory; every incomplete shard stays withheld."""
    if (
        type(cycle_id) is not str
        or not cycle_id
        or type(observation_cutoff) is not str
        or not observation_cutoff
        or type(year_dispositions) is not tuple
        or not year_dispositions
        or type(judgment_bundle_refs) is not tuple
        or type(discrepancy_refs) is not tuple
        or _FINGERPRINT.fullmatch(journal_head_fingerprint) is None
        or (runner_result is not None and type(runner_result) is not AcquisitionCycleResult)
        or runner_result is AcquisitionCycleResult.NO_CHANGE
        or type(cycle_mode) is not CasesCycleMode
        or (
            accepted_predecessor is not None
            and type(accepted_predecessor) is not CasesAcceptedPredecessorState
        )
        or any(type(ref) is not str or not ref for ref in judgment_bundle_refs + discrepancy_refs)
        or len(set(judgment_bundle_refs)) != len(judgment_bundle_refs)
        or any(_BUNDLE_REF.fullmatch(ref) is None for ref in judgment_bundle_refs)
    ):
        _invalid_prefix()
    try:
        source_dispositions = validate_source_role_dispositions(source_dispositions)
    except (TypeError, ValueError) as error:
        raise ValueError(_INVALID_PREFIX) from error
    cutoff_year = _canonical_cutoff(observation_cutoff).year
    prior_year = _EARLIEST_YEAR - 1
    retryable = False
    terminal = False
    for shard in year_dispositions:
        if (
            type(shard) is not YearShardDisposition
            or type(shard.year) is not int
            or shard.year != prior_year + 1
            or type(shard.first_in_scope_date) is not str
            or (shard.year == _EARLIEST_YEAR and shard.first_in_scope_date != _EARLIEST_DATE)
            or (
                shard.year != _EARLIEST_YEAR
                and shard.first_in_scope_date != f"{shard.year:04d}-01-01"
            )
            or any(
                type(value) is not int or value < 0
                for value in (
                    shard.final_page,
                    shard.verified_listing_pages,
                    shard.discovered_judgments,
                    shard.verified_judgments,
                    shard.retryable_items,
                )
            )
            or shard.verified_listing_pages > shard.final_page
            or shard.verified_judgments > shard.discovered_judgments
            or type(shard.result) is not AcquisitionCycleResult
        ):
            _invalid_prefix()
        prior_year = shard.year
        retryable = (
            retryable
            or shard.retryable_items > 0
            or (shard.result is AcquisitionCycleResult.INCOMPLETE_RETRYABLE)
        )
        terminal = terminal or shard.result is not AcquisitionCycleResult.COMPLETE
    complete_shape = (
        prior_year == cutoff_year
        and all(
            shard.final_page >= 1
            and shard.verified_listing_pages == shard.final_page
            and shard.verified_judgments == shard.discovered_judgments
            and shard.result is AcquisitionCycleResult.COMPLETE
            for shard in year_dispositions
        )
        and len(judgment_bundle_refs)
        == sum(shard.verified_judgments for shard in year_dispositions)
    )
    result = (
        runner_result
        if runner_result is not None and runner_result is not AcquisitionCycleResult.COMPLETE
        else AcquisitionCycleResult.INCOMPLETE_RETRYABLE
        if retryable
        else AcquisitionCycleResult.INCOMPLETE_TERMINAL
        if terminal or not complete_shape
        else AcquisitionCycleResult.COMPLETE
    )
    if cycle_mode is CasesCycleMode.INCREMENTAL_DISCOVERY:
        result = (
            result
            if result is not AcquisitionCycleResult.COMPLETE
            else AcquisitionCycleResult.INCOMPLETE_TERMINAL
        )
    elif (
        result is AcquisitionCycleResult.COMPLETE
        and accepted_predecessor is not None
        and _inventory_signature(year_dispositions, judgment_bundle_refs, discrepancy_refs)
        == _inventory_signature(
            accepted_predecessor.manifest.year_dispositions,
            accepted_predecessor.manifest.judgment_bundle_refs,
            accepted_predecessor.manifest.discrepancy_refs,
        )
    ):
        result = AcquisitionCycleResult.NO_CHANGE
    if (
        result in {AcquisitionCycleResult.COMPLETE, AcquisitionCycleResult.NO_CHANGE}
        and source_dispositions
        and any(
            item.result not in {AcquisitionCycleResult.COMPLETE, AcquisitionCycleResult.NO_CHANGE}
            for item in source_dispositions
        )
    ):
        _invalid_prefix()
    provisional = CasesAcquisitionManifest(
        cycle_id=cycle_id,
        earliest_decision_date=_EARLIEST_DATE,
        observation_cutoff=observation_cutoff,
        year_dispositions=year_dispositions,
        judgment_bundle_refs=judgment_bundle_refs,
        discrepancy_refs=discrepancy_refs,
        journal_head_fingerprint=journal_head_fingerprint,
        result=result,
        fingerprint="",
        source_dispositions=source_dispositions,
    )
    return CasesAcquisitionManifest(
        cycle_id=provisional.cycle_id,
        earliest_decision_date=provisional.earliest_decision_date,
        observation_cutoff=provisional.observation_cutoff,
        year_dispositions=provisional.year_dispositions,
        judgment_bundle_refs=provisional.judgment_bundle_refs,
        discrepancy_refs=provisional.discrepancy_refs,
        journal_head_fingerprint=provisional.journal_head_fingerprint,
        result=provisional.result,
        fingerprint=(
            f"sha256:{sha256(canonicalize(checked_json_value(_manifest_body(provisional)))).hexdigest()}"
        ),
        source_dispositions=provisional.source_dispositions,
    )


def _inventory_signature(
    year_dispositions: tuple[YearShardDisposition, ...],
    judgment_bundle_refs: tuple[str, ...],
    discrepancy_refs: tuple[str, ...],
) -> bytes:
    """Canonical source-state facts; cycle metadata cannot manufacture equality."""
    return canonicalize(
        checked_json_value(
            {
                "discrepancy_refs": list(discrepancy_refs),
                "judgment_bundle_refs": list(judgment_bundle_refs),
                "year_dispositions": [
                    {
                        "discovered_judgments": shard.discovered_judgments,
                        "final_page": shard.final_page,
                        "first_in_scope_date": shard.first_in_scope_date,
                        "result": shard.result.value,
                        "retryable_items": shard.retryable_items,
                        "verified_judgments": shard.verified_judgments,
                        "verified_listing_pages": shard.verified_listing_pages,
                        "year": shard.year,
                    }
                    for shard in year_dispositions
                ],
            }
        )
    )


def _manifest_body(manifest: CasesAcquisitionManifest) -> dict[str, JsonValue]:
    """Return the only fields covered by a Cases acquisition manifest fingerprint."""
    value = checked_json_value(
        {
            "cycle_id": manifest.cycle_id,
            "discrepancy_refs": list(manifest.discrepancy_refs),
            "earliest_decision_date": manifest.earliest_decision_date,
            "journal_head_fingerprint": manifest.journal_head_fingerprint,
            "judgment_bundle_refs": list(manifest.judgment_bundle_refs),
            "observation_cutoff": manifest.observation_cutoff,
            "result": manifest.result.value,
            "year_dispositions": [
                {
                    "discovered_judgments": shard.discovered_judgments,
                    "final_page": shard.final_page,
                    "first_in_scope_date": shard.first_in_scope_date,
                    "result": shard.result.value,
                    "retryable_items": shard.retryable_items,
                    "verified_judgments": shard.verified_judgments,
                    "verified_listing_pages": shard.verified_listing_pages,
                    "year": shard.year,
                }
                for shard in manifest.year_dispositions
            ],
        }
    )
    if type(value) is not dict:
        _invalid_prefix()
    if manifest.source_dispositions:
        value["source_dispositions"] = [item.to_json() for item in manifest.source_dispositions]
    return value


def _text(value: JsonValue) -> str:
    if type(value) is not str:
        _invalid_prefix()
    return value


def _integer(value: JsonValue) -> int:
    if type(value) is not int:
        _invalid_prefix()
    return value


def _texts(value: JsonValue) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        _invalid_prefix()
    return tuple(_text(item) for item in value)


def persist_verified_cases_judgment_bundles(  # noqa: C901, PLR0912 - one closed bundle gate.
    *,
    state_root: Path,
    graph: CasesWorkGraph,
    report: AcquisitionCycleReport,
    store: CasesJudgmentBundleStore,
) -> tuple[str, ...]:
    """Persist immutable read-back-verified bundles for every verified physical judgment."""
    if (
        type(state_root) is not type(Path())
        or not state_root.is_absolute()
        or type(graph) is not CasesWorkGraph
        or type(report) is not AcquisitionCycleReport
        or report.cycle_id != graph.cycle_id
        or not callable(getattr(store, "conditional_create", None))
        or not callable(getattr(store, "read", None))
    ):
        _invalid_prefix()
    bindings = {
        binding.work_item_id: binding for binding in runner_verified_capture_bindings(report)
    }
    disposition_by_id = {item.work_item_id: item for item in report.item_dispositions}
    with LocalAcquisitionJournal(state_root, graph.cycle_id) as journal:
        latest_entries = {entry.work_item.work_item_id: entry for entry in journal.replay()}
    node_by_key = {node.key: node for node in graph.nodes}
    refs: list[str] = []
    judgments = tuple(node for node in graph.nodes if node.kind is CasesWorkKind.JUDGMENT_ARTIFACT)
    for judgment in judgments:
        work_item_id = judgment.scheduled.identity.work_item_id
        binding = bindings.get(work_item_id)
        disposition = disposition_by_id.get(work_item_id)
        if binding is None:
            if disposition is not None and disposition.transition in {
                JournalTransition.CAPTURED_VERIFIED,
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
            }:
                _invalid_prefix()
            continue
        occurrences = tuple(
            occurrence
            for occurrence in graph.occurrences
            if occurrence.judgment_node_key == judgment.key
            and (
                graph.mode is CasesCycleMode.INCREMENTAL_DISCOVERY or occurrence.reconciled_in_scope
            )
        )
        if not occurrences:
            continue
        occurrence_documents: list[dict[str, object]] = []
        for occurrence in occurrences:
            relationship_documents: list[dict[str, str]] = []
            if len(occurrence.relationship_node_keys) != len(_RELATIONSHIP_KINDS):
                _invalid_prefix()
            for key, expected_kind in zip(
                occurrence.relationship_node_keys, _RELATIONSHIP_KINDS, strict=True
            ):
                relationship = node_by_key.get(key)
                if (
                    relationship is None
                    or relationship.kind.value != expected_kind
                    or relationship.captures_body
                ):
                    _invalid_prefix()
                relationship_disposition = disposition_by_id.get(
                    relationship.scheduled.identity.work_item_id
                )
                entry = latest_entries.get(relationship.scheduled.identity.work_item_id)
                if (
                    relationship_disposition is None
                    or relationship_disposition.transition
                    is not JournalTransition.ACCOUNTED_EXCLUDED
                    or entry is None
                    or entry.transition is not JournalTransition.ACCOUNTED_EXCLUDED
                    or type(entry.payload) is not AccountedExcludedPayload
                    or entry.payload.reason_code != "SOURCE_RELATIONSHIP_RETAINED"
                ):
                    _invalid_prefix()
                relationship_documents.append(
                    {
                        "disposition": "SOURCE_RELATIONSHIP_RETAINED",
                        "kind": expected_kind,
                        "relationship_node_key": key,
                        "work_item_id": relationship.scheduled.identity.work_item_id,
                    }
                )
            occurrence_documents.append(
                {
                    "dis_id": occurrence.dis_id,
                    "listing_node_key": occurrence.listing_node_key,
                    "occurrence_key": occurrence.key,
                    "presentation": {
                        "disposition": "PRESENTATION_LOCATOR_RETAINED"
                        if occurrence.presentation_url is not None
                        else "NOT_DECLARED",
                        "url": occurrence.presentation_url,
                    },
                    "relationships": relationship_documents,
                }
            )
        bundle_document = checked_json_value(
            {
                "capture": {
                    "body_length": binding.body_length,
                    "content_fingerprint": binding.content_fingerprint,
                    "object_ref": binding.object_ref,
                    "work_item_id": binding.work_item_id,
                },
                "judgment_node_key": judgment.key,
                "occurrences": occurrence_documents,
                "schema_id": "asklegal.hk-case-judgment-bundle/v1",
            }
        )
        body = canonicalize(bundle_document)
        digest = sha256(body).hexdigest()
        object_ref = f"cases/judgment-bundles/sha256/{digest}.json"
        try:
            store.conditional_create(object_ref, body)
            retained = store.read(object_ref)
        except Exception as error:
            message = "CASES_JUDGMENT_BUNDLE_WRITE_FAILED"
            raise ValueError(message) from error
        if (
            type(retained) is not bytes
            or retained != body
            or sha256(retained).hexdigest() != digest
        ):
            message = "CASES_JUDGMENT_BUNDLE_READBACK_FAILED"
            raise ValueError(message)
        refs.append(object_ref)
    if len(refs) != len(set(refs)):
        _invalid_prefix()
    return tuple(sorted(refs))


def project_cases_manifest_from_runner(
    *,
    graph: CasesWorkGraph,
    report: AcquisitionCycleReport,
    discrepancy_refs: tuple[str, ...],
    judgment_bundle_refs: tuple[str, ...],
    accepted_predecessor: CasesAcceptedPredecessorState | None = None,
) -> CasesAcquisitionManifest:
    """Project actual shared-journal dispositions without a false complete frontier."""
    if (
        type(graph) is not CasesWorkGraph
        or type(report) is not AcquisitionCycleReport
        or report.cycle_id != graph.cycle_id
        or type(discrepancy_refs) is not tuple
        or type(judgment_bundle_refs) is not tuple
    ):
        _invalid_prefix()
    terminal_by_id = {item.work_item_id: item for item in report.item_dispositions}
    partition_by_year = {item.year: item for item in graph.reconciled_partitions}
    reconciliation_failures = set(graph.reconciliation_failures)
    dispositions: list[YearShardDisposition] = []
    cutoff = _canonical_cutoff(graph.observation_cutoff)
    admitted_occurrences = tuple(
        occurrence
        for occurrence in graph.occurrences
        if graph.mode is CasesCycleMode.INCREMENTAL_DISCOVERY or occurrence.reconciled_in_scope
    )
    admitted_judgment_keys = {occurrence.judgment_node_key for occurrence in admitted_occurrences}
    admitted_relationship_keys = {
        key for occurrence in admitted_occurrences for key in occurrence.relationship_node_keys
    }
    provisional_only_keys = (
        (
            {
                occurrence.judgment_node_key
                for occurrence in graph.occurrences
                if not occurrence.reconciled_in_scope
            }
            | {
                key
                for occurrence in graph.occurrences
                if not occurrence.reconciled_in_scope
                for key in occurrence.relationship_node_keys
            }
        )
        - admitted_judgment_keys
        - admitted_relationship_keys
    )
    for year in range(_EARLIEST_YEAR, cutoff.year + 1):
        listing_nodes = tuple(
            node
            for node in graph.nodes
            if node.year == year and node.kind is CasesWorkKind.LISTING_PAGE
        )
        judgment_nodes = tuple(
            node
            for node in graph.nodes
            if node.year == year
            and node.kind is CasesWorkKind.JUDGMENT_ARTIFACT
            and node.captures_body
            and node.key in admitted_judgment_keys
        )
        listing_terminals = tuple(
            terminal_by_id.get(node.scheduled.identity.work_item_id) for node in listing_nodes
        )
        judgment_terminals = tuple(
            terminal_by_id.get(node.scheduled.identity.work_item_id) for node in judgment_nodes
        )
        relationship_nodes = tuple(
            node
            for node in graph.nodes
            if node.year == year
            and not node.captures_body
            and node.key in admitted_relationship_keys
        )
        relationship_terminals = tuple(
            terminal_by_id.get(node.scheduled.identity.work_item_id) for node in relationship_nodes
        )
        partition = partition_by_year.get(year)
        verified_listings = tuple(
            item
            for item in listing_terminals
            if item is not None
            and item.transition
            in {JournalTransition.CAPTURED_VERIFIED, JournalTransition.IMPORTED_CAPTURE_VERIFIED}
        )
        verified_judgments = tuple(
            item
            for item in judgment_terminals
            if item is not None
            and item.transition
            in {JournalTransition.CAPTURED_VERIFIED, JournalTransition.IMPORTED_CAPTURE_VERIFIED}
        )
        retryable = sum(
            item is None or item.transition is JournalTransition.RETRYABLE_FAILURE
            for item in listing_terminals + judgment_terminals
        )
        non_success = tuple(
            item
            for item in listing_terminals + judgment_terminals + relationship_terminals
            if item is None
            or item.transition
            not in {
                JournalTransition.CAPTURED_VERIFIED,
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
                JournalTransition.RETRYABLE_FAILURE,
                JournalTransition.ACCOUNTED_EXCLUDED,
            }
        )
        if any(
            item is None or item.transition is not JournalTransition.ACCOUNTED_EXCLUDED
            for item in relationship_terminals
        ):
            non_success = (*non_success, None)
        expected_judgments = (
            len(_partition_in_scope_dis_ids(partition, cutoff.date()))
            if partition is not None
            else 0
        )
        partition_complete = graph.mode is CasesCycleMode.INCREMENTAL_DISCOVERY or (
            partition is not None
            and partition.complete
            and tuple(sorted(node.page for node in listing_nodes))
            == tuple(range(1, partition.reported_pages + 1))
            and len(judgment_nodes) == expected_judgments
        )
        if year in reconciliation_failures:
            shard_result = AcquisitionCycleResult.SOURCE_CONTRACT_CHANGED
        elif retryable:
            shard_result = AcquisitionCycleResult.INCOMPLETE_RETRYABLE
        elif non_success or not partition_complete:
            shard_result = AcquisitionCycleResult.INCOMPLETE_TERMINAL
        else:
            shard_result = AcquisitionCycleResult.COMPLETE
        dispositions.append(
            YearShardDisposition(
                year=year,
                first_in_scope_date=_EARLIEST_DATE
                if year == _EARLIEST_YEAR
                else f"{year:04d}-01-01",
                final_page=(
                    partition.reported_pages
                    if partition is not None
                    else max((node.page for node in listing_nodes), default=0)
                ),
                verified_listing_pages=len(verified_listings),
                discovered_judgments=len(judgment_nodes),
                verified_judgments=len(verified_judgments),
                retryable_items=retryable,
                result=shard_result,
            )
        )
    return build_cases_acquisition_manifest(
        cycle_id=graph.cycle_id,
        observation_cutoff=graph.observation_cutoff,
        year_dispositions=tuple(dispositions),
        judgment_bundle_refs=judgment_bundle_refs,
        discrepancy_refs=discrepancy_refs,
        journal_head_fingerprint=report.journal_head_fingerprint,
        runner_result=_project_cases_runner_result(
            graph=graph,
            report=report,
            reconciliation_failures=reconciliation_failures,
            provisional_node_keys=provisional_only_keys,
        ),
        cycle_mode=graph.mode,
        accepted_predecessor=accepted_predecessor,
        source_dispositions=_cases_source_dispositions(graph, report),
    )


def _cases_source_dispositions(
    graph: CasesWorkGraph, report: AcquisitionCycleReport
) -> tuple[SourceRoleDisposition, ...]:
    """Bind the two due Cases roles to their own exact journal items."""
    due_sources = {
        "HK-CASE-HKLII-DISCOVERY",
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
    }
    terminals = {item.work_item_id: item for item in report.item_dispositions}
    projected: list[SourceRoleDisposition] = []
    for source_id in sorted(due_sources):
        nodes = tuple(
            node for node in graph.nodes if node.scheduled.identity.source_role == source_id
        )
        if not nodes:
            continue
        transitions = tuple(terminals.get(node.scheduled.identity.work_item_id) for node in nodes)
        verified = sum(
            item is not None
            and item.transition
            in {
                JournalTransition.CAPTURED_VERIFIED,
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
            }
            for item in transitions
        )
        retryable = sum(
            item is None
            or item.transition
            in {
                JournalTransition.DISCOVERED,
                JournalTransition.STARTED,
                JournalTransition.TRANSPORT_STARTED,
                JournalTransition.RETRYABLE_FAILURE,
                JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
            }
            for item in transitions
        )
        rejected = len(nodes) - verified - retryable
        result = (
            AcquisitionCycleResult.INCOMPLETE_RETRYABLE
            if retryable
            else AcquisitionCycleResult.INCOMPLETE_TERMINAL
            if rejected
            else AcquisitionCycleResult.COMPLETE
        )
        projected.append(
            SourceRoleDisposition(source_id, len(nodes), verified, retryable, rejected, result)
        )
    return validate_source_role_dispositions(tuple(projected))


def _project_cases_runner_result(
    *,
    graph: CasesWorkGraph,
    report: AcquisitionCycleReport,
    reconciliation_failures: set[int],
    provisional_node_keys: set[str],
) -> AcquisitionCycleResult | None:
    """Ignore only non-success proved to belong wholly to provisional item work."""
    global_stop_results = {
        AcquisitionCycleResult.BUDGET_EXHAUSTED,
        AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE,
        AcquisitionCycleResult.AUTHORIZATION_FAILURE,
        AcquisitionCycleResult.SOURCE_CONTRACT_CHANGED,
    }
    if report.result in global_stop_results:
        return report.result
    if reconciliation_failures:
        return AcquisitionCycleResult.SOURCE_CONTRACT_CHANGED
    if graph.mode is not CasesCycleMode.FULL_RECONCILIATION:
        return report.result
    provisional_results = {
        AcquisitionCycleResult.INCOMPLETE_RETRYABLE,
        AcquisitionCycleResult.INCOMPLETE_TERMINAL,
        AcquisitionCycleResult.RETRY_EXHAUSTED,
    }
    if report.result not in provisional_results:
        return report.result
    successful_transitions = {
        JournalTransition.CAPTURED_VERIFIED,
        JournalTransition.IMPORTED_CAPTURE_VERIFIED,
        JournalTransition.ACCOUNTED_EXCLUDED,
    }
    non_successful_items = tuple(
        item for item in report.item_dispositions if item.transition not in successful_transitions
    )
    provisional_work_ids = {
        node.scheduled.identity.work_item_id
        for node in graph.nodes
        if node.key in provisional_node_keys
    }
    if non_successful_items and all(
        item.work_item_id in provisional_work_ids for item in non_successful_items
    ):
        return None
    return report.result


def retained_judiciary_prefix_from_receipt(
    receipt: RetainedImportReceipt, reader: RetainedJudiciaryEvidenceReader
) -> RetainedJudiciaryPrefix:
    """Reconstruct the frozen W prefix from exact retained report/object bindings.

    Receipt summaries, including ``last_listing``, are deliberately not used to
    decide where enumeration resumes.  Every retained listing body is read back
    through the injected evidence boundary and bound again to its report facts.
    """
    if (
        type(receipt) is not RetainedImportReceipt
        or not callable(getattr(reader, "read", None))
        or receipt.source_family != "CASES"
        or not receipt.source_attempt_id
        or _FINGERPRINT.fullmatch(receipt.source_report_fingerprint) is None
        or type(receipt.imported_object_references) is not tuple
    ):
        _invalid_prefix()
    listings: list[tuple[str, str, str, str, int]] = []
    authorities: set[str] = set()
    executions: set[str] = set()
    for reference in receipt.imported_object_references:
        if type(reference) is not RetainedImportedObjectReference:
            _invalid_prefix()
        if _RETAINED_PAGE.fullmatch(reference.endpoint_id) is None:
            continue
        try:
            body = reader.read(reference)
        except Exception as error:
            raise ValueError(_INVALID_PREFIX) from error
        if (
            type(body) is not bytes
            or len(body) != reference.body_length
            or f"sha256:{sha256(body).hexdigest()}" != reference.content_fingerprint
            or reference.media_type != "text/html"
        ):
            _invalid_prefix()
        listings.append(
            (
                reference.endpoint_id,
                reference.final_url,
                reference.object_ref,
                reference.content_fingerprint,
                reference.body_length,
            )
        )
        authorities.add(reference.authority_manifest_fingerprint)
        executions.add(reference.execution_authorization_fingerprint)
    if (
        not listings
        or len(authorities) != 1
        or len(executions) != 1
        or max(_retained_coordinate(item[0]) for item in listings) != (2011, 363)
    ):
        _invalid_prefix()
    return RetainedJudiciaryPrefix(
        source_attempt_id=receipt.source_attempt_id,
        source_report_fingerprint=receipt.source_report_fingerprint,
        authority_manifest_fingerprint=next(iter(authorities)),
        execution_authorization_fingerprint=next(iter(executions)),
        observation_cutoff="retained-w-prefix",
        imported_listing_refs=tuple(
            sorted(listings, key=lambda item: _retained_coordinate(item[0]))
        ),
    )


def build_cases_baseline_plan(
    *,
    retained_prefix: RetainedJudiciaryPrefix,
    cycle_id: str = "cyc_20260906_cases_baseline",
    successor_locator: str | None = None,
    observation_cutoff: str | None = None,
) -> CasesBaselinePlan:
    """Resume the retained official sequence with exactly its next page, never page one."""
    if type(retained_prefix) is not RetainedJudiciaryPrefix:
        _invalid_prefix()
    year, page = retained_prefix.last_listing
    if type(cycle_id) is not str or not cycle_id:
        _invalid_prefix()
    locator = (
        _next_page_locator(retained_prefix.last_locator, page + 1)
        if successor_locator is None
        else successor_locator
    )
    if type(locator) is not str:
        _invalid_prefix()
    bound_cutoff = (
        retained_prefix.observation_cutoff if observation_cutoff is None else observation_cutoff
    )
    if observation_cutoff is not None:
        _canonical_cutoff(bound_cutoff)
    contract = registered_judiciary_observation_contract(
        JudiciaryObservationKind.YEAR_RECONCILIATION
    )
    identity = WorkItemIdentity.issue(
        source_family="CASES",
        source_role=contract.source_id,
        cycle_id=cycle_id,
        observation_cutoff=bound_cutoff,
        procedure_version=contract.endpoint_version,
        locator=locator,
        stage="LISTING_PAGE",
        parent_id=f"year-{year}",
        media_type="text/html",
        max_bytes=8_388_608,
    )
    return CasesBaselinePlan(
        retained_prefix=retained_prefix,
        first_network_item=ScheduledWorkItem(
            identity=identity,
            priority=(year, page + 1, f"listing-{year}-{page + 1}"),
            host="legalref.judiciary.hk",
            not_before_monotonic_ns=0,
        ),
    )


def build_cases_work_graph(
    *,
    cycle_id: str,
    observation_cutoff: str,
    retained_prefix: RetainedJudiciaryPrefix,
    locator_for_year_page: Callable[[int, int], str],
) -> CasesWorkGraph:
    """Build the first resumable graph from the exact retained W prefix.

    The initial graph has exactly one runnable frontier per year.  New verified
    listing pages extend their own year frontier in a subsequent shared-runner
    invocation, so no year can skip an unverified predecessor while independent
    years remain concurrently schedulable.
    """
    if (
        type(cycle_id) is not str
        or not cycle_id
        or type(observation_cutoff) is not str
        or type(retained_prefix) is not RetainedJudiciaryPrefix
        or not callable(locator_for_year_page)
    ):
        _invalid_prefix()
    cutoff_year = _canonical_cutoff(observation_cutoff).year
    if cutoff_year < _EARLIEST_YEAR:
        _invalid_prefix()
    prefix_by_coordinate = {
        _retained_coordinate(reference[0]): reference
        for reference in retained_prefix.imported_listing_refs
    }
    nodes: list[CasesWorkNode] = []
    for (year, page), reference in sorted(prefix_by_coordinate.items()):
        key = reference[0]
        previous_key = f"judiciary-year-{year}-page-{page - 1}"
        dependencies = (
            (previous_key,)
            if page > 1
            and previous_key in {item[0] for item in retained_prefix.imported_listing_refs}
            else ()
        )
        nodes.append(
            _listing_node(
                key=key,
                year=year,
                page=page,
                locator=reference[1],
                cycle_id=cycle_id,
                observation_cutoff=observation_cutoff,
                depends_on=dependencies,
            )
        )
    known_by_year = {
        year: max(page for (candidate_year, page) in prefix_by_coordinate if candidate_year == year)
        for year in {year for year, _page in prefix_by_coordinate}
    }
    for year in range(_EARLIEST_YEAR, cutoff_year + 1):
        next_page = known_by_year.get(year, 0) + 1
        if next_page == 1 or year == retained_prefix.last_listing[0]:
            key = f"judiciary-year-{year}-page-{next_page}"
            if key in {node.key for node in nodes}:
                continue
            try:
                locator = locator_for_year_page(year, next_page)
            except Exception as error:
                raise ValueError(_INVALID_PREFIX) from error
            predecessor = f"judiciary-year-{year}-page-{next_page - 1}"
            nodes.append(
                _listing_node(
                    key=key,
                    year=year,
                    page=next_page,
                    locator=locator,
                    cycle_id=cycle_id,
                    observation_cutoff=observation_cutoff,
                    depends_on=(predecessor,) if next_page > 1 else (),
                )
            )
    if not nodes:
        _invalid_prefix()
    return CasesWorkGraph(
        cycle_id=cycle_id,
        observation_cutoff=observation_cutoff,
        nodes=tuple(sorted(nodes, key=lambda node: (node.year, node.page, node.key))),
        mode=CasesCycleMode.FULL_RECONCILIATION,
    )


def build_cases_observation_graph(*, cycle_id: str, observation_cutoff: str) -> CasesWorkGraph:
    """Create executable current-list and RSS discovery work from registered contracts."""
    if type(cycle_id) is not str or not cycle_id or type(observation_cutoff) is not str:
        _invalid_prefix()
    _canonical_cutoff(observation_cutoff)
    nodes = tuple(
        _observation_node(kind, cycle_id=cycle_id, observation_cutoff=observation_cutoff)
        for kind in (JudiciaryObservationKind.CURRENT_LIST, JudiciaryObservationKind.RSS)
    )
    return CasesWorkGraph(
        cycle_id,
        observation_cutoff,
        nodes,
        mode=CasesCycleMode.INCREMENTAL_DISCOVERY,
    )


def _observation_node(
    kind: JudiciaryObservationKind, *, cycle_id: str, observation_cutoff: str
) -> CasesWorkNode:
    contract = registered_judiciary_observation_contract(kind)
    work_kind = (
        CasesWorkKind.CURRENT_LIST_OBSERVATION
        if kind is JudiciaryObservationKind.CURRENT_LIST
        else CasesWorkKind.RSS_OBSERVATION
    )
    identity = WorkItemIdentity.issue(
        source_family="CASES",
        source_role=contract.source_id,
        cycle_id=cycle_id,
        observation_cutoff=observation_cutoff,
        procedure_version=contract.endpoint_version,
        locator=contract.locator,
        stage=work_kind.value,
        parent_id="incremental-observation",
        media_type=contract.media_type,
        max_bytes=contract.max_bytes,
    )
    return CasesWorkNode(
        key=f"judiciary-{kind.value.casefold().replace('_', '-')}",
        kind=work_kind,
        endpoint_id=contract.endpoint_id,
        endpoint_version=contract.endpoint_version,
        year=int(observation_cutoff[:4]),
        page=0,
        scheduled=ScheduledWorkItem(
            identity=identity,
            priority=(0, 0, work_kind.value),
            host="legalref.judiciary.hk",
            not_before_monotonic_ns=0,
        ),
        depends_on=(),
    )


def _listing_node(  # noqa: PLR0913 - exact work identity components are independently bound.
    *,
    key: str,
    year: int,
    page: int,
    locator: str,
    cycle_id: str,
    observation_cutoff: str,
    depends_on: tuple[str, ...],
) -> CasesWorkNode:
    if type(locator) is not str or not locator or type(depends_on) is not tuple:
        _invalid_prefix()
    contract = registered_judiciary_observation_contract(
        JudiciaryObservationKind.YEAR_RECONCILIATION
    )
    identity = WorkItemIdentity.issue(
        source_family="CASES",
        source_role=contract.source_id,
        cycle_id=cycle_id,
        observation_cutoff=observation_cutoff,
        procedure_version=contract.endpoint_version,
        locator=locator,
        stage=CasesWorkKind.LISTING_PAGE.value,
        parent_id=f"year-{year}",
        media_type="text/html",
        max_bytes=8_388_608,
    )
    return CasesWorkNode(
        key=key,
        kind=CasesWorkKind.LISTING_PAGE,
        endpoint_id=contract.endpoint_id,
        endpoint_version=contract.endpoint_version,
        year=year,
        page=page,
        scheduled=ScheduledWorkItem(
            identity=identity,
            priority=(year, page, key),
            host="legalref.judiciary.hk",
            not_before_monotonic_ns=0,
        ),
        depends_on=depends_on,
    )


def run_cases_resumable_graph(  # noqa: PLR0913 - shared runner safety controls remain explicit.
    *,
    state_root: Path,
    graph: CasesWorkGraph,
    retained_prefix: RetainedJudiciaryPrefix,
    transport: CaptureTransport,
    retained_verifier: RetainedObjectVerifier,
    clock: AcquisitionClock,
    sleeper: Callable[[float], None],
    budget: CycleBudget,
) -> AcquisitionCycleReport:
    """Import W without a request and run every current frontier through Task 3's runner."""
    if (
        type(state_root) is not type(Path())
        or not state_root.is_absolute()
        or type(graph) is not CasesWorkGraph
        or type(retained_prefix) is not RetainedJudiciaryPrefix
        or graph.cycle_id != graph.nodes[0].scheduled.identity.cycle_id
        or graph.observation_cutoff != graph.nodes[0].scheduled.identity.observation_cutoff
    ):
        _invalid_prefix()
    imports = _prefix_preverified_imports(graph, retained_prefix)
    with LocalAcquisitionJournal(state_root, graph.cycle_id) as journal:
        _account_relationship_work(journal, graph)
        return ResumableAcquisitionRunner(
            journal=journal,
            items=tuple(node.scheduled for node in graph.nodes),
            transport=transport,
            retained_verifier=retained_verifier,
            clock=clock,
            sleeper=sleeper,
            budget=budget,
            per_host_limit=4,
            dependencies=graph.runner_dependencies,
            preverified_imports=imports,
        ).run()


def _prefix_preverified_imports(
    graph: CasesWorkGraph, retained_prefix: RetainedJudiciaryPrefix
) -> tuple[tuple[str, ImportedCaptureVerifiedPayload], ...]:
    """Bind each exact retained listing reference to its graph node without redownload."""
    node_by_key = {node.key: node for node in graph.nodes}
    imports: list[tuple[str, ImportedCaptureVerifiedPayload]] = []
    for (
        endpoint_id,
        locator,
        object_ref,
        fingerprint,
        length,
    ) in retained_prefix.imported_listing_refs:
        node = node_by_key.get(endpoint_id)
        if node is None and graph.mode is CasesCycleMode.INCREMENTAL_DISCOVERY:
            continue
        if node is None or node.kind is not CasesWorkKind.LISTING_PAGE:
            _invalid_prefix()
        imports.append(
            (
                node.scheduled.identity.work_item_id,
                ImportedCaptureVerifiedPayload(
                    source_attempt_id=retained_prefix.source_attempt_id,
                    source_report_fingerprint=retained_prefix.source_report_fingerprint,
                    authority_manifest_fingerprint=retained_prefix.authority_manifest_fingerprint,
                    execution_authorization_fingerprint=(
                        retained_prefix.execution_authorization_fingerprint
                    ),
                    status=200,
                    media_type="text/html",
                    final_url=locator,
                    body_length=length,
                    content_fingerprint=fingerprint,
                    object_ref=object_ref,
                    read_back_verified=True,
                ),
            )
        )
    return tuple(imports)


def _account_relationship_work(journal: LocalAcquisitionJournal, graph: CasesWorkGraph) -> None:
    """Give every source relationship a durable, hash-bound terminal disposition."""
    entries = journal.replay()
    existing = {entry.work_item.work_item_id for entry in entries}
    relationships = tuple(
        node
        for node in graph.nodes
        if not node.captures_body and node.scheduled.identity.work_item_id not in existing
    )
    if not relationships:
        return
    origins = tuple(
        entry.payload.cycle_started_at_epoch_us
        for entry in entries
        if entry.transition is JournalTransition.DISCOVERED
        and type(entry.payload) is DiscoveredPayload
    )
    if not origins or len(set(origins)) != 1:
        _invalid_prefix()
    additions: list[tuple[WorkItemIdentity, JournalTransition, object]] = []
    for node in relationships:
        additions.extend(
            (
                (
                    node.scheduled.identity,
                    JournalTransition.DISCOVERED,
                    DiscoveredPayload(origins[0]),
                ),
                (
                    node.scheduled.identity,
                    JournalTransition.ACCOUNTED_EXCLUDED,
                    AccountedExcludedPayload("SOURCE_RELATIONSHIP_RETAINED"),
                ),
            )
        )
    journal.append_many(tuple(additions))


def _append_provisional_listing_work(  # noqa: PLR0913 - explicit graph mutation state.
    *,
    graph: CasesWorkGraph,
    node: CasesWorkNode,
    page: JudiciaryYearResultPage,
    nodes: list[CasesWorkNode],
    occurrences: list[CasesListingOccurrence],
    known_keys: set[str],
    known_occurrence_keys: set[str],
) -> None:
    """Create exact durable descendants without granting reconciled admission."""
    for ordinal, occurrence in enumerate(page.occurrences, start=1):
        occurrence_key = f"{node.key}-occurrence-{ordinal}"
        if occurrence_key in known_occurrence_keys:
            continue
        judgment_key = next(
            (
                candidate.key
                for candidate in nodes
                if candidate.captures_body
                and candidate.kind is CasesWorkKind.JUDGMENT_ARTIFACT
                and candidate.scheduled.identity.locator == occurrence.artifact_url
            ),
            None,
        )
        if judgment_key is None:
            judgment_key = f"judiciary-judgment-{occurrence.dis_id}"
            nodes.append(
                _artifact_node(
                    key=judgment_key,
                    kind=CasesWorkKind.JUDGMENT_ARTIFACT,
                    year=node.year,
                    page=node.page,
                    locator=occurrence.artifact_url,
                    cycle_id=graph.cycle_id,
                    observation_cutoff=graph.observation_cutoff,
                    depends_on=(node.key,),
                    captures_body=True,
                )
            )
            known_keys.add(judgment_key)
        relationship_keys: list[str] = []
        for relationship_id, kind_name in zip(
            occurrence.relationship_ids[1:], _RELATIONSHIP_KINDS, strict=True
        ):
            relationship_key = f"{occurrence_key}-{relationship_id.rsplit('-', maxsplit=1)[-1]}"
            relationship_keys.append(relationship_key)
            if relationship_key in known_keys:
                continue
            nodes.append(
                _artifact_node(
                    key=relationship_key,
                    kind=CasesWorkKind(kind_name),
                    year=node.year,
                    page=node.page,
                    locator=occurrence.artifact_url,
                    cycle_id=graph.cycle_id,
                    observation_cutoff=graph.observation_cutoff,
                    depends_on=(node.key, judgment_key),
                    captures_body=False,
                    parent_id=occurrence_key,
                )
            )
            known_keys.add(relationship_key)
        occurrences.append(
            CasesListingOccurrence(
                key=occurrence_key,
                listing_node_key=node.key,
                dis_id=occurrence.dis_id,
                judgment_node_key=judgment_key,
                relationship_node_keys=tuple(relationship_keys),
                presentation_url=occurrence.presentation_url,
                reconciled_in_scope=False,
            )
        )
        known_occurrence_keys.add(occurrence_key)


def expand_cases_graph_from_verified_listings(  # noqa: C901, PLR0912, PLR0915 - closed partition expansion.
    *,
    graph: CasesWorkGraph,
    report: AcquisitionCycleReport,
    reader: VerifiedCaptureEvidenceReader,
    contract_version: str,
) -> CasesWorkGraph:
    """Parse verified listings and append only their exact successor/artifact children."""
    if (
        type(graph) is not CasesWorkGraph
        or type(report) is not AcquisitionCycleReport
        or report.cycle_id != graph.cycle_id
        or not callable(getattr(reader, "read_exact", None))
        or type(contract_version) is not str
    ):
        _invalid_prefix()
    disposition_by_id = {item.work_item_id: item for item in report.item_dispositions}
    bindings = {item.work_item_id: item for item in runner_verified_capture_bindings(report)}
    nodes = list(graph.nodes)
    occurrences = list(graph.occurrences)
    known_keys = {node.key for node in nodes}
    known_occurrence_keys = {occurrence.key for occurrence in occurrences}
    parsed_by_year: dict[int, dict[int, tuple[CasesWorkNode, JudiciaryYearResultPage]]] = {}
    failed_years = set(graph.reconciliation_failures)
    partition_by_year = {item.year: item for item in graph.reconciled_partitions}
    for node in tuple(graph.nodes):
        if node.kind is not CasesWorkKind.LISTING_PAGE:
            continue
        disposition = disposition_by_id.get(node.scheduled.identity.work_item_id)
        if (
            disposition is None
            or disposition.transition
            not in {
                JournalTransition.CAPTURED_VERIFIED,
                JournalTransition.IMPORTED_CAPTURE_VERIFIED,
            }
            or disposition.object_ref is None
        ):
            continue
        binding = bindings.get(node.scheduled.identity.work_item_id)
        if binding is None:
            failed_years.add(node.year)
            continue
        try:
            body = reader.read_exact(
                binding.object_ref,
                binding.content_fingerprint,
                binding.body_length,
            )
            page = parse_judiciary_year_result_page(
                body, year=node.year, page=node.page, contract_version=contract_version
            )
        except KeyError, OSError, TypeError, ValueError:
            failed_years.add(node.year)
            continue
        year_pages = parsed_by_year.setdefault(node.year, {})
        if node.page in year_pages:
            failed_years.add(node.year)
            continue
        year_pages[node.page] = (node, page)

    for page_map in parsed_by_year.values():
        for node, page in page_map.values():
            _append_provisional_listing_work(
                graph=graph,
                node=node,
                page=page,
                nodes=nodes,
                occurrences=occurrences,
                known_keys=known_keys,
                known_occurrence_keys=known_occurrence_keys,
            )

    cutoff_date = _canonical_cutoff(graph.observation_cutoff).date()
    for year, page_map in sorted(parsed_by_year.items()):
        if year in failed_years or year in partition_by_year:
            continue
        page_numbers = tuple(sorted(page_map))
        pages = tuple(page_map[page][1] for page in page_numbers)
        first = pages[0]
        if (
            page_numbers != tuple(range(1, page_numbers[-1] + 1))
            or any(
                (page.year, page.reported_results, page.reported_pages)
                != (first.year, first.reported_results, first.reported_pages)
                for page in pages
            )
            or page_numbers[-1] > first.reported_pages
        ):
            failed_years.add(year)
            continue
        if page_numbers[-1] < first.reported_pages:
            current_node, current_page = page_map[page_numbers[-1]]
            if current_page.advertised_next_page is None:
                failed_years.add(year)
                continue
            next_key = f"judiciary-year-{year}-page-{current_page.advertised_next_page}"
            if next_key not in known_keys:
                next_locator = build_judiciary_next_result_url(
                    current_node.scheduled.identity.locator,
                    result_page=current_page,
                    form_contract_version=contract_version,
                )
                nodes.append(
                    _listing_node(
                        key=next_key,
                        year=year,
                        page=current_page.advertised_next_page,
                        locator=next_locator,
                        cycle_id=graph.cycle_id,
                        observation_cutoff=graph.observation_cutoff,
                        depends_on=(current_node.key,),
                    )
                )
                known_keys.add(next_key)
            continue
        try:
            partition = reconcile_judiciary_year_partition(
                pages,
                contract_version=_partition_contract_version(contract_version),
            )
        except TypeError, ValueError:
            failed_years.add(year)
            continue
        partition_by_year[year] = partition
        admitted_dis_ids = set(_partition_in_scope_dis_ids(partition, cutoff_date))
        listing_keys = {page_map[page_number][0].key for page_number in page_numbers}
        occurrences = [
            replace(occurrence, reconciled_in_scope=True)
            if occurrence.listing_node_key in listing_keys and occurrence.dis_id in admitted_dis_ids
            else occurrence
            for occurrence in occurrences
        ]
    return CasesWorkGraph(
        cycle_id=graph.cycle_id,
        observation_cutoff=graph.observation_cutoff,
        nodes=tuple(sorted(nodes, key=lambda item: (item.year, item.page, item.key))),
        occurrences=tuple(sorted(occurrences, key=lambda item: item.key)),
        mode=graph.mode,
        reconciled_partitions=tuple(sorted(partition_by_year.values(), key=lambda item: item.year)),
        reconciliation_failures=tuple(sorted(failed_years)),
    )


def _invalid_current_list_route() -> Never:
    message = "JUDICIARY_CURRENT_LIST_ROUTE_INVALID"
    raise ValueError(message)


def expand_cases_graph_from_verified_observations(  # noqa: C901, PLR0912, PLR0915 - closed expansion.
    *,
    graph: CasesWorkGraph,
    report: AcquisitionCycleReport,
    reader: VerifiedCaptureEvidenceReader,
) -> CasesWorkGraph:
    """Parse registered discovery observations before creating any descendant work."""
    if (
        type(graph) is not CasesWorkGraph
        or graph.mode is not CasesCycleMode.INCREMENTAL_DISCOVERY
        or type(report) is not AcquisitionCycleReport
        or report.cycle_id != graph.cycle_id
        or not callable(getattr(reader, "read_exact", None))
    ):
        _invalid_prefix()
    bindings = {item.work_item_id: item for item in runner_verified_capture_bindings(report)}
    parsed: list[tuple[CasesWorkNode, JudiciaryIncrementalObservation]] = []
    for node in graph.nodes:
        if node.kind not in {
            CasesWorkKind.CURRENT_LIST_OBSERVATION,
            CasesWorkKind.RSS_OBSERVATION,
        }:
            continue
        binding = bindings.get(node.scheduled.identity.work_item_id)
        if binding is None:
            continue
        kind = (
            JudiciaryObservationKind.CURRENT_LIST
            if node.kind is CasesWorkKind.CURRENT_LIST_OBSERVATION
            else JudiciaryObservationKind.RSS
        )
        contract = registered_judiciary_observation_contract(kind)
        if (
            node.endpoint_id != contract.endpoint_id
            or node.endpoint_version != contract.endpoint_version
            or node.scheduled.identity.source_role != contract.source_id
            or node.scheduled.identity.locator != contract.locator
            or node.scheduled.identity.media_type != contract.media_type
        ):
            _invalid_prefix()
        try:
            if kind is JudiciaryObservationKind.CURRENT_LIST:
                entry_url, session_url = registered_judiciary_current_list_route()
                if (
                    node.scheduled.identity.locator != entry_url
                    or binding.final_url != session_url
                    or binding.redirect_chain != (session_url,)
                ):
                    _invalid_current_list_route()
            body = reader.read_exact(
                binding.object_ref, binding.content_fingerprint, binding.body_length
            )
            observation = (
                parse_judiciary_current_list_observation(body, contract=contract)
                if kind is JudiciaryObservationKind.CURRENT_LIST
                else parse_judiciary_rss_observation(body, contract=contract)
            )
        except Exception as error:
            message = "CASES_INCREMENTAL_CONTRACT_CHANGED"
            raise ValueError(message) from error
        if observation.proves_complete or observation.proves_no_change:
            _invalid_prefix()
        parsed.append((node, observation))

    # Mutate only after every captured observation has passed its exact parser.
    nodes = list(graph.nodes)
    occurrences = list(graph.occurrences)
    known_keys = {node.key for node in nodes}
    known_occurrences = {occurrence.key for occurrence in occurrences}
    for observation_node, observation_value in parsed:
        for ordinal, source_occurrence in enumerate(observation_value.occurrences, start=1):
            decision_date = source_occurrence.decision_date.isoformat()
            if not _EARLIEST_DATE <= decision_date <= graph.observation_cutoff[:10]:
                message = "CASES_INCREMENTAL_OCCURRENCE_OUT_OF_SCOPE"
                raise ValueError(message)
            occurrence_key = f"{observation_node.key}-occurrence-{ordinal}"
            if occurrence_key in known_occurrences:
                continue
            judgment_key = next(
                (
                    candidate.key
                    for candidate in nodes
                    if candidate.captures_body
                    and candidate.kind is CasesWorkKind.JUDGMENT_ARTIFACT
                    and candidate.scheduled.identity.locator == source_occurrence.artifact_url
                ),
                None,
            )
            if judgment_key is None:
                judgment_key = f"judiciary-judgment-{source_occurrence.dis_id}"
                if judgment_key in known_keys:
                    _invalid_prefix()
                nodes.append(
                    _artifact_node(
                        key=judgment_key,
                        kind=CasesWorkKind.JUDGMENT_ARTIFACT,
                        year=source_occurrence.decision_date.year,
                        page=0,
                        locator=source_occurrence.artifact_url,
                        cycle_id=graph.cycle_id,
                        observation_cutoff=graph.observation_cutoff,
                        depends_on=(observation_node.key,),
                        captures_body=True,
                    )
                )
                known_keys.add(judgment_key)
            relationship_keys: list[str] = []
            for relationship_id, kind_name in zip(
                source_occurrence.relationship_ids[1:], _RELATIONSHIP_KINDS, strict=True
            ):
                relationship_key = f"{occurrence_key}-{relationship_id.rsplit('-', maxsplit=1)[-1]}"
                relationship_keys.append(relationship_key)
                if relationship_key in known_keys:
                    continue
                nodes.append(
                    _artifact_node(
                        key=relationship_key,
                        kind=CasesWorkKind(kind_name),
                        year=source_occurrence.decision_date.year,
                        page=0,
                        locator=source_occurrence.artifact_url,
                        cycle_id=graph.cycle_id,
                        observation_cutoff=graph.observation_cutoff,
                        depends_on=(observation_node.key, judgment_key),
                        captures_body=False,
                        parent_id=occurrence_key,
                    )
                )
                known_keys.add(relationship_key)
            occurrences.append(
                CasesListingOccurrence(
                    key=occurrence_key,
                    listing_node_key=observation_node.key,
                    dis_id=source_occurrence.dis_id,
                    judgment_node_key=judgment_key,
                    relationship_node_keys=tuple(relationship_keys),
                    presentation_url=None,
                    reconciled_in_scope=False,
                )
            )
            known_occurrences.add(occurrence_key)
    return CasesWorkGraph(
        graph.cycle_id,
        graph.observation_cutoff,
        tuple(sorted(nodes, key=lambda item: (item.year, item.page, item.key))),
        tuple(sorted(occurrences, key=lambda item: item.key)),
        graph.mode,
    )


def _canonical_cutoff(value: str) -> datetime:
    """Parse one exact whole-second UTC cutoff used by graph and scope decisions."""
    if type(value) is not str or _CUTOFF.fullmatch(value) is None:
        _invalid_prefix()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(_INVALID_PREFIX) from error
    if parsed.tzinfo is not UTC or parsed.isoformat().replace("+00:00", "Z") != value:
        _invalid_prefix()
    return parsed


def _partition_contract_version(value: str) -> str:
    """Map the current form-only revision to its unchanged result-table contract."""
    return "1.0.12" if value == "1.0.13" else value


def _partition_in_scope_dis_ids(partition: JudiciaryYearPartition, cutoff: date) -> tuple[int, ...]:
    """Apply the inclusive V1 start and cycle cutoff to a reconciled publisher year."""
    if type(partition) is not JudiciaryYearPartition or type(cutoff) is not date:
        _invalid_prefix()
    return tuple(
        dis_id
        for dis_id, decision_date in zip(partition.dis_ids, partition.decision_dates, strict=True)
        if decision_date is not None
        and date(1997, 7, 1) <= decision_date <= cutoff
        and dis_id in partition.in_scope_dis_ids
    )


def _artifact_node(  # noqa: PLR0913 - each immutable work identity fact is independently bound.
    *,
    key: str,
    kind: CasesWorkKind,
    year: int,
    page: int,
    locator: str,
    cycle_id: str,
    observation_cutoff: str,
    depends_on: tuple[str, ...],
    captures_body: bool,
    parent_id: str | None = None,
) -> CasesWorkNode:
    contract = registered_judiciary_observation_contract(JudiciaryObservationKind.JUDGMENT_ARTIFACT)
    identity = WorkItemIdentity.issue(
        source_family="CASES",
        source_role=contract.source_id,
        cycle_id=cycle_id,
        observation_cutoff=observation_cutoff,
        procedure_version=contract.endpoint_version,
        locator=locator,
        stage=kind.value,
        parent_id=f"year-{year}" if parent_id is None else parent_id,
        media_type="text/html",
        max_bytes=8_388_608,
    )
    return CasesWorkNode(
        key=key,
        kind=kind,
        endpoint_id=contract.endpoint_id,
        endpoint_version=contract.endpoint_version,
        year=year,
        page=page,
        scheduled=ScheduledWorkItem(
            identity=identity,
            priority=(year, page, key),
            host="legalref.judiciary.hk",
            not_before_monotonic_ns=0,
        ),
        depends_on=depends_on,
        captures_body=captures_body,
    )


def _next_page_locator(locator: str, page: int) -> str:
    parsed = urlsplit(locator)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "legalref.judiciary.hk"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or page < 1
    ):
        _invalid_prefix()
    pairs = [
        (name, value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        if name != "page"
    ]
    pairs.append(("page", str(page)))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), ""))


def _retained_coordinate(endpoint_id: str) -> tuple[int, int]:
    match = _RETAINED_PAGE.fullmatch(endpoint_id)
    if match is None:
        _invalid_prefix()
    return int(match.group("year")), int(match.group("page"))


def _invalid_prefix() -> Never:
    raise ValueError(_INVALID_PREFIX)
