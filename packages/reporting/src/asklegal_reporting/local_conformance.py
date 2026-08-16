"""Deterministic M7 scenario and complete local-platform report values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

_SCENARIO_ID = re.compile(r"^E2E-(?:00[1-9]|0[12][0-9]|03[0-2])$")
_EXPECTED_SCENARIOS = tuple(f"E2E-{index:03d}" for index in range(1, 33))
_STATEMENT = "local synthetic platform proved"


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """One exact terminal scenario result with safe trace references."""

    scenario_id: str
    result_code: str
    summary: str
    authoritative_refs: tuple[str, ...]
    fact_count: int
    effect_count: int
    fingerprint: str = ""

    def __post_init__(self) -> None:
        """Reject malformed, failed, or mutable-looking scenario results."""
        if _SCENARIO_ID.fullmatch(self.scenario_id) is None:
            raise ValueError("invalid M7 scenario identity")
        if not self.result_code or not self.summary:
            raise ValueError("scenario result code and summary are required")
        if type(self.authoritative_refs) is not tuple:
            raise TypeError("authoritative_refs must be an exact tuple")
        if len(self.authoritative_refs) != len(set(self.authoritative_refs)):
            raise ValueError("authoritative_refs must be unique")
        if type(self.fact_count) is not int or self.fact_count < 0:
            raise TypeError("fact_count must be a non-negative exact integer")
        if type(self.effect_count) is not int or self.effect_count < 0:
            raise TypeError("effect_count must be a non-negative exact integer")
        expected = _fingerprint(_scenario_body(self))
        if self.fingerprint and self.fingerprint != expected:
            raise ValueError("scenario fingerprint drift")
        object.__setattr__(self, "fingerprint", expected)


@dataclass(frozen=True, slots=True)
class LocalConformanceReport:
    """One complete immutable report for the closed M7 scenario catalogue."""

    statement: str
    profile_fingerprint: str
    scenarios: tuple[ScenarioResult, ...]
    canonical_bytes: bytes
    fingerprint: str


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _scenario_body(result: ScenarioResult) -> bytes:
    return canonicalize(
        checked_json_value(
            {
                "authoritative_refs": list(result.authoritative_refs),
                "effect_count": result.effect_count,
                "fact_count": result.fact_count,
                "result_code": result.result_code,
                "scenario_id": result.scenario_id,
                "summary": result.summary,
            }
        )
    )


def build_local_conformance_report(
    profile_fingerprint: str,
    scenarios: tuple[ScenarioResult, ...],
) -> LocalConformanceReport:
    """Freeze the complete successful 32-scenario local-platform report."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", profile_fingerprint):
        raise ValueError("profile fingerprint must be one exact SHA-256 fingerprint")
    ordered = tuple(sorted(scenarios, key=lambda item: item.scenario_id))
    if tuple(item.scenario_id for item in ordered) != _EXPECTED_SCENARIOS:
        raise ValueError("M7 report requires every scenario exactly once")
    body = canonicalize(
        checked_json_value(
            {
                "external_systems": "LOCAL_FAKES_ONLY",
                "profile_fingerprint": profile_fingerprint,
                "scenario_results": [
                    {
                        "fingerprint": item.fingerprint,
                        "result_code": item.result_code,
                        "scenario_id": item.scenario_id,
                    }
                    for item in ordered
                ],
                "schema_id": "asklegal.local-conformance-report",
                "schema_version": "1.0.0",
                "statement": _STATEMENT,
            }
        )
    )
    return LocalConformanceReport(
        _STATEMENT,
        profile_fingerprint,
        ordered,
        body,
        _fingerprint(body),
    )
