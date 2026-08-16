"""M5 Legal Processing result port and deterministic local register fake."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Protocol


class LegalProcessingRecordConflict(RuntimeError):
    """One processing result identity was reused for different content."""


@dataclass(frozen=True, slots=True)
class LegalProcessingRecord:
    """One immutable Management Register projection for an M5 result."""

    result_id: str
    input_fingerprint: str
    observation_id: str
    source_snapshot_id: str
    package_id: str
    package_fingerprint: str
    rule_id: str
    disposition: str
    reason_code: str
    failure_code: str
    evidence_refs: tuple[str, ...]
    candidate_artifact_id: str
    candidate_artifact_fingerprint: str
    semantic_decision_fingerprint: str
    next_action: str


class LegalProcessingRegisterStore(Protocol):
    """Authoritative immutable M5 result storage boundary."""

    def record_processing_result(self, record: LegalProcessingRecord) -> LegalProcessingRecord:
        """Record once or return an exact replay."""
        ...

    def get_processing_result(self, result_id: str) -> LegalProcessingRecord:
        """Resolve one exact M5 result without inference."""
        ...


class InMemoryLegalProcessingRegister:
    """Thread-safe M5 fake enforcing exact replay."""

    def __init__(self) -> None:
        """Create an empty result projection."""
        self._lock = RLock()
        self._records: dict[str, LegalProcessingRecord] = {}

    def record_processing_result(self, record: LegalProcessingRecord) -> LegalProcessingRecord:
        """Select one exact result per deterministic result identity."""
        if type(record) is not LegalProcessingRecord:
            raise TypeError("record must be an exact LegalProcessingRecord")
        with self._lock:
            existing = self._records.get(record.result_id)
            if existing is None:
                self._records[record.result_id] = record
                return record
            if existing != record:
                raise LegalProcessingRecordConflict(record.result_id)
            return existing

    def get_processing_result(self, result_id: str) -> LegalProcessingRecord:
        """Return an existing result or fail visibly."""
        with self._lock:
            try:
                return self._records[result_id]
            except KeyError as error:
                raise LookupError(result_id) from error

    @property
    def records(self) -> tuple[LegalProcessingRecord, ...]:
        """Return stable identity order for coverage proof."""
        with self._lock:
            return tuple(self._records[key] for key in sorted(self._records))
