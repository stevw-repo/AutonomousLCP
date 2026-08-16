"""Typed M4 acquisition-result port and deterministic register fake."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Literal, Protocol

type WatcherCode = Literal[
    "SUPPORTED_NO_CHANGE",
    "POSSIBLE_CHANGE",
    "SOURCE_UNAVAILABLE",
    "SOURCE_CONTRACT_CHANGED",
    "INCOMPLETE_OBSERVATION",
    "UNSAFE_RESPONSE",
]
type ScraperCode = Literal[
    "SNAPSHOT_PRESERVED",
    "SUPPORTED_NO_CHANGE_AFTER_CAPTURE",
    "PARTIAL_CAPTURE",
    "SOURCE_UNAVAILABLE",
    "SOURCE_CONTRACT_CHANGED",
    "UNSAFE_RESPONSE",
]
type DispositionCode = Literal[
    "COMPLETE_NO_CHANGE",
    "SNAPSHOT_PRESERVED",
    "SOURCE_CONTRACT_REVIEW",
    "COVERAGE_GAP",
    "QUARANTINE",
]
type ConsequenceCode = Literal["NONE", "LEGAL_PROCESSING_ELIGIBLE"]

_WATCHER_CODES = frozenset(
    {
        "SUPPORTED_NO_CHANGE",
        "POSSIBLE_CHANGE",
        "SOURCE_UNAVAILABLE",
        "SOURCE_CONTRACT_CHANGED",
        "INCOMPLETE_OBSERVATION",
        "UNSAFE_RESPONSE",
    }
)
_SCRAPER_CODES = frozenset(
    {
        "SNAPSHOT_PRESERVED",
        "SUPPORTED_NO_CHANGE_AFTER_CAPTURE",
        "PARTIAL_CAPTURE",
        "SOURCE_UNAVAILABLE",
        "SOURCE_CONTRACT_CHANGED",
        "UNSAFE_RESPONSE",
    }
)
_DISPOSITIONS = frozenset(
    {
        "COMPLETE_NO_CHANGE",
        "SNAPSHOT_PRESERVED",
        "SOURCE_CONTRACT_REVIEW",
        "COVERAGE_GAP",
        "QUARANTINE",
    }
)


class AcquisitionRecordConflict(RuntimeError):
    """One observation identity was reused for different immutable input."""


@dataclass(frozen=True, slots=True)
class AcquisitionObservationRecord:
    """One authoritative, explicit M4 outcome for one source observation."""

    observation_id: str
    input_fingerprint: str
    source_id: str
    endpoint_id: str
    observation_cutoff: str
    watcher_result: WatcherCode
    scraper_result: ScraperCode | None
    disposition: DispositionCode
    consequence: ConsequenceCode
    evidence_package_id: str
    primary_manifest_version: str
    recovery_manifest_version: str
    manifest_fingerprint: str
    source_snapshot_id: str
    issue_id: str

    def __post_init__(self) -> None:
        for field in (
            "observation_id",
            "input_fingerprint",
            "source_id",
            "endpoint_id",
            "observation_cutoff",
            "evidence_package_id",
            "primary_manifest_version",
            "recovery_manifest_version",
            "manifest_fingerprint",
            "source_snapshot_id",
            "issue_id",
        ):
            value = getattr(self, field)
            if type(value) is not str:
                raise TypeError(f"{field} must be an exact string")
        if self.watcher_result not in _WATCHER_CODES:
            raise ValueError("watcher_result is outside the closed M4 catalogue")
        if self.scraper_result is not None and self.scraper_result not in _SCRAPER_CODES:
            raise ValueError("scraper_result is outside the closed M4 catalogue")
        if self.disposition not in _DISPOSITIONS:
            raise ValueError("disposition is outside the closed M4 catalogue")
        if self.consequence not in {"NONE", "LEGAL_PROCESSING_ELIGIBLE"}:
            raise ValueError("consequence is outside the closed M4 catalogue")
        if self.disposition == "SNAPSHOT_PRESERVED":
            if not self.source_snapshot_id or self.scraper_result != "SNAPSHOT_PRESERVED":
                raise ValueError("preserved disposition requires one preserved scraper snapshot")
            if self.consequence != "LEGAL_PROCESSING_ELIGIBLE":
                raise ValueError("a preserved snapshot must explicitly authorize legal processing")
            if self.issue_id:
                raise ValueError("a preserved snapshot cannot also be an unresolved issue")
        else:
            if self.source_snapshot_id:
                raise ValueError("non-preserved outcomes cannot name a Source Snapshot")
            if self.consequence != "NONE":
                raise ValueError("non-preserved outcomes authorize no downstream work")
            needs_issue = self.disposition in {
                "COVERAGE_GAP",
                "QUARANTINE",
                "SOURCE_CONTRACT_REVIEW",
            }
            if needs_issue != bool(self.issue_id):
                raise ValueError("failed outcomes require exactly one explicit issue identity")


class AcquisitionRegisterStore(Protocol):
    """Authoritative M4 outcome persistence without source or vault access."""

    def record_observation(
        self,
        record: AcquisitionObservationRecord,
    ) -> AcquisitionObservationRecord:
        """Record once or return an exact replay of the same immutable outcome."""
        ...

    def get_observation(self, observation_id: str) -> AcquisitionObservationRecord:
        """Resolve one exact observation outcome."""
        ...


class InMemoryAcquisitionRegister:
    """Thread-safe local fake that enforces one outcome per observation."""

    def __init__(self) -> None:
        """Create an empty M4 register projection."""
        self._lock = RLock()
        self._records: dict[str, AcquisitionObservationRecord] = {}

    def record_observation(
        self,
        record: AcquisitionObservationRecord,
    ) -> AcquisitionObservationRecord:
        """Atomically select one immutable observation result."""
        if type(record) is not AcquisitionObservationRecord:
            raise TypeError("record must be an exact AcquisitionObservationRecord")
        with self._lock:
            existing = self._records.get(record.observation_id)
            if existing is None:
                self._records[record.observation_id] = record
                return record
            if existing != record:
                raise AcquisitionRecordConflict(record.observation_id)
            return existing

    def get_observation(self, observation_id: str) -> AcquisitionObservationRecord:
        """Return one recorded result without inferring a missing outcome."""
        with self._lock:
            try:
                return self._records[observation_id]
            except KeyError as error:
                raise LookupError(observation_id) from error

    @property
    def records(self) -> tuple[AcquisitionObservationRecord, ...]:
        """Return deterministic observation order for coverage accounting."""
        with self._lock:
            return tuple(self._records[key] for key in sorted(self._records))
