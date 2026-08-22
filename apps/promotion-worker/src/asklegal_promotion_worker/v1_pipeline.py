"""Fail-closed V1 promotion payload boundary.

The former live POC accepted arbitrary records, embedded them, and wrote them to
Pinecone under a deployment-wide environment switch. That path is deliberately
removed. This module retains only the strict record parser used at the future
approved-manifest boundary and a fingerprint comparison helper; it contains no
provider adapter, scheduler activity, effect handoff, or promotion orchestrator.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_promotion import (
    PromotionError,
    PromotionErrorCode,
    TargetRecord,
    serving_metadata,
    serving_metadata_fingerprint,
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class PromotionPipelineError(RuntimeError):
    """One exact promotion-payload failure, safe to log."""


@dataclass(frozen=True, slots=True)
class PromotionRecordInput:
    """One manifest-selected record crossing the embed-to-target boundary."""

    record_id: str
    serving_payload_fingerprint: str
    text: str
    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str

    @classmethod
    def from_json(cls, value: object) -> PromotionRecordInput:
        """Parse all six serving fields and their already-approved fingerprint."""
        document = checked_json_value(value)
        if not isinstance(document, dict):
            message = "promotion record must be an object"
            raise PromotionPipelineError(message)
        record_id = document.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            message = "promotion record needs a record_id"
            raise PromotionPipelineError(message)
        fingerprint = document.get("serving_payload_fingerprint")
        if not isinstance(fingerprint, str) or _SHA256.fullmatch(fingerprint) is None:
            message = f"promotion record {record_id} needs serving_payload_fingerprint"
            raise PromotionPipelineError(message)
        fields: dict[str, str] = {}
        for key in ("text", "country", "jurisdiction", "type", "source", "authority_note"):
            field = document.get(key)
            if not isinstance(field, str) or not field:
                message = f"promotion record {record_id} needs {key}"
                raise PromotionPipelineError(message)
            fields[key] = field
        return cls(
            record_id,
            fingerprint,
            fields["text"],
            fields["country"],
            fields["jurisdiction"],
            fields["type"],
            fields["source"],
            fields["authority_note"],
        )

    def to_json(self) -> dict[str, str]:
        """Render the exact durable representation without changing its claim."""
        return {
            "record_id": self.record_id,
            "serving_payload_fingerprint": self.serving_payload_fingerprint,
            "text": self.text,
            "country": self.country,
            "jurisdiction": self.jurisdiction,
            "type": self.material_type,
            "source": self.source,
            "authority_note": self.authority_note,
        }


def write_authorized(_environment: Mapping[str, str]) -> bool:
    """Refuse the retired deployment-wide write flag under every environment."""
    return False


def target_record_from_approved_payload(item: object) -> TargetRecord:
    """Rebuild one record only when its bytes match the approved fingerprint."""
    parsed = PromotionRecordInput.from_json(item)
    document = checked_json_value(item)
    if not isinstance(document, dict):
        message = "promotion record must be an object"
        raise PromotionPipelineError(message)
    record = TargetRecord(
        parsed.record_id,
        parsed.serving_payload_fingerprint,
        _numeric_vector(document.get("vector")),
        parsed.text,
        parsed.country,
        parsed.jurisdiction,
        parsed.material_type,
        parsed.source,
        parsed.authority_note,
    )
    actual_fingerprint = serving_metadata_fingerprint(serving_metadata(record))
    if actual_fingerprint != parsed.serving_payload_fingerprint:
        raise PromotionError(
            PromotionErrorCode.MANIFEST_DRIFT,
            f"record {parsed.record_id} serving payload",
        )
    return record


def _numeric_vector(value: JsonValue | None) -> tuple[float, ...]:
    if not isinstance(value, list):
        message = "promotion record needs a numeric vector"
        raise PromotionPipelineError(message)
    result: list[float] = []
    for member in value:
        if isinstance(member, bool) or not isinstance(member, int | float):
            message = "promotion record vector must contain only numbers"
            raise PromotionPipelineError(message)
        result.append(float(member))
    return tuple(result)
