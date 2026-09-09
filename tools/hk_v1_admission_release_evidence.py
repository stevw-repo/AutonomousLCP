"""Closed Gate C accounting built only from four exact CorpusRelease objects."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Never

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import CorpusRelease, serving_payload_fingerprint

SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_SCHEMA = "asklegal.hk-v1-live-release-accounting/v1"
_VERSION = "1.0.0"
_INVALID = "HK_V1_LIVE_RELEASE_ACCOUNTING_INVALID"


class LiveReleaseAccountingError(ValueError):
    """One malformed or internally inconsistent four-release artifact."""


@dataclass(frozen=True, slots=True)
class LiveReleaseAccounting:
    """Parsed exact four-scope release inventory."""

    observation_cutoff: str
    proposal_fingerprint: str
    release_fingerprints: tuple[str, ...]
    total_record_count: int
    fingerprint: str


def _fail() -> Never:
    raise LiveReleaseAccountingError(_INVALID)


def _fingerprint(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


def _validated_release(release: CorpusRelease) -> dict[str, JsonValue]:
    if type(release) is not CorpusRelease:
        _fail()
    record_rows = [
        {
            "content_fingerprint": entry.serving_payload_fingerprint,
            "record_id": entry.record.record_id,
        }
        for entry in release.records
    ]
    if any(
        entry.serving_payload_fingerprint != serving_payload_fingerprint(entry.record)
        for entry in release.records
    ):
        _fail()
    records_fingerprint = _fingerprint(canonicalize(checked_json_value(record_rows)))
    release_body = {
        "evidence_refs": list(release.evidence_refs),
        "observation_cutoff": release.observation_cutoff,
        "records_fingerprint": records_fingerprint,
        "scope_id": release.scope_id,
        "validation_refs": list(release.validation_refs),
        "withholding_refs": list(release.withholding_refs),
        "zero_record_justification_refs": list(release.zero_record_justification_refs),
    }
    if (
        release.records_fingerprint != records_fingerprint
        or release.release_fingerprint
        != _fingerprint(canonicalize(checked_json_value(release_body)))
        or (
            not release.records
            and not (release.zero_record_justification_refs or release.withholding_refs)
        )
    ):
        _fail()
    return {
        "record_count": len(release.records),
        "records_fingerprint": release.records_fingerprint,
        "release_fingerprint": release.release_fingerprint,
        "release_id": release.release_id,
        "scope_id": release.scope_id,
    }


def build_live_release_accounting(
    releases: tuple[CorpusRelease, ...],
    *,
    proposal_fingerprint: str,
) -> bytes:
    """Build only after rederiving all four release and record fingerprints."""
    if type(releases) is not tuple or len(releases) != len(SCOPES):
        _fail()
    ordered = tuple(sorted(releases, key=lambda item: item.scope_id))
    if tuple(item.scope_id for item in ordered) != SCOPES:
        _fail()
    cutoffs = {item.observation_cutoff for item in ordered}
    if len(cutoffs) != 1:
        _fail()
    body: dict[str, JsonValue] = {
        "schema_id": _SCHEMA,
        "schema_version": _VERSION,
        "observation_cutoff": next(iter(cutoffs)),
        "proposal_fingerprint": proposal_fingerprint,
        "releases": [_validated_release(item) for item in ordered],
        "result": "COMPLETE",
    }
    fingerprint = _fingerprint(canonicalize(checked_json_value(body)))
    return canonicalize(checked_json_value({**body, "fingerprint": fingerprint}))


def parse_live_release_accounting(content: bytes) -> LiveReleaseAccounting:
    """Strictly parse one owner-produced four-release projection."""
    try:
        value = parse_json_bytes(content, max_bytes=2_000_000)
    except (RuntimeError, ValueError) as error:
        raise LiveReleaseAccountingError(_INVALID) from error
    fields = {
        "fingerprint",
        "observation_cutoff",
        "proposal_fingerprint",
        "releases",
        "result",
        "schema_id",
        "schema_version",
    }
    if not isinstance(value, dict) or set(value) != fields or canonicalize(value) != content:
        _fail()
    unsigned = dict(value)
    supplied = unsigned.pop("fingerprint", None)
    raw_releases = value.get("releases")
    if (
        value.get("schema_id") != _SCHEMA
        or value.get("schema_version") != _VERSION
        or value.get("result") != "COMPLETE"
        or supplied != _fingerprint(canonicalize(checked_json_value(unsigned)))
        or type(raw_releases) is not list
        or len(raw_releases) != len(SCOPES)
    ):
        _fail()
    fingerprints: list[str] = []
    total = 0
    for scope, raw in zip(SCOPES, raw_releases, strict=True):
        if type(raw) is not dict or set(raw) != {
            "record_count",
            "records_fingerprint",
            "release_fingerprint",
            "release_id",
            "scope_id",
        }:
            _fail()
        count = raw.get("record_count")
        fingerprint = raw.get("release_fingerprint")
        if (
            raw.get("scope_id") != scope
            or type(count) is not int
            or count < 0
            or type(fingerprint) is not str
            or not fingerprint.startswith("sha256:")
        ):
            _fail()
        total += count
        fingerprints.append(fingerprint)
    cutoff = value.get("observation_cutoff")
    proposal = value.get("proposal_fingerprint")
    if type(cutoff) is not str or type(proposal) is not str or type(supplied) is not str:
        _fail()
    return LiveReleaseAccounting(cutoff, proposal, tuple(fingerprints), total, supplied)
