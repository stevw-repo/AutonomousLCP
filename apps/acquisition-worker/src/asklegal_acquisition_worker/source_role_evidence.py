"""Closed per-source accounting embedded in one family acquisition manifest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Never

from asklegal_contracts.json_types import JsonValue, checked_json_value

from asklegal_acquisition_worker.acquisition_journal import AcquisitionCycleResult

_DISPOSITION_INVALID = "SOURCE_ROLE_DISPOSITION_INVALID"
_DISPOSITIONS_INVALID = "SOURCE_ROLE_DISPOSITIONS_INVALID"


def _fail(code: str = _DISPOSITION_INVALID) -> Never:
    raise ValueError(code)


@dataclass(frozen=True, slots=True)
class SourceRoleDisposition:
    """Actual journal accounting for one source role in one family cycle."""

    source_id: str
    required_item_count: int
    verified_item_count: int
    retryable_item_count: int
    rejected_item_count: int
    result: AcquisitionCycleResult

    def __post_init__(self) -> None:
        """Reject missing accounting and every false complete result."""
        counts = (
            self.required_item_count,
            self.verified_item_count,
            self.retryable_item_count,
            self.rejected_item_count,
        )
        if (
            type(self.source_id) is not str
            or not self.source_id.startswith("HK-")
            or any(type(value) is not int or value < 0 for value in counts)
            or self.required_item_count <= 0
            or self.verified_item_count + self.retryable_item_count + self.rejected_item_count
            != self.required_item_count
            or type(self.result) is not AcquisitionCycleResult
        ):
            _fail()
        complete = self.result in {
            AcquisitionCycleResult.COMPLETE,
            AcquisitionCycleResult.NO_CHANGE,
        }
        if complete != (
            self.verified_item_count == self.required_item_count
            and self.retryable_item_count == 0
            and self.rejected_item_count == 0
        ):
            _fail()
        if (
            self.result is AcquisitionCycleResult.INCOMPLETE_RETRYABLE
            and self.retryable_item_count == 0
        ):
            _fail()

    def to_json(self) -> dict[str, JsonValue]:
        """Return the exact fingerprint-covered role projection."""
        return {
            "source_id": self.source_id,
            "required_item_count": self.required_item_count,
            "verified_item_count": self.verified_item_count,
            "retryable_item_count": self.retryable_item_count,
            "rejected_item_count": self.rejected_item_count,
            "result": self.result.value,
        }

    @classmethod
    def from_json(cls, value: object) -> SourceRoleDisposition:
        """Parse one closed role projection without coercion or unknown fields."""
        try:
            document = checked_json_value(value)
            if type(document) is not dict or set(document) != {
                "source_id",
                "required_item_count",
                "verified_item_count",
                "retryable_item_count",
                "rejected_item_count",
                "result",
            }:
                _fail()
            source_id = document["source_id"]
            required = _count(document, "required_item_count")
            verified = _count(document, "verified_item_count")
            retryable = _count(document, "retryable_item_count")
            rejected = _count(document, "rejected_item_count")
            result = document["result"]
            if type(source_id) is not str or type(result) is not str:
                _fail()
            return cls(
                source_id,
                required,
                verified,
                retryable,
                rejected,
                AcquisitionCycleResult(result),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(_DISPOSITION_INVALID) from error


def _count(document: dict[str, JsonValue], field: str) -> int:
    value = document[field]
    if type(value) is not int:
        _fail()
    return value


def validate_source_role_dispositions(
    value: tuple[SourceRoleDisposition, ...],
) -> tuple[SourceRoleDisposition, ...]:
    """Require one sorted, duplicate-free exact tuple."""
    if (
        type(value) is not tuple
        or any(type(item) is not SourceRoleDisposition for item in value)
        or tuple(item.source_id for item in value)
        != tuple(sorted({item.source_id for item in value}))
    ):
        _fail(_DISPOSITIONS_INVALID)
    for item in value:
        item.__post_init__()
    return value
