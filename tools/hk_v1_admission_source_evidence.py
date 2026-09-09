"""Closed source-owner evidence for HK V1 admission Gates A and B.

The aggregate carries the exact canonical source-execution reports and every object
they name.  Its parser re-runs the source executor's closed report grammar and
recomputes every retained object digest; scenario outcomes are derived from those
owner artifacts rather than accepted as caller assertions.
"""

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Never, cast

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

import tools.hk_v1_source_execution as source_execution

_MAX_BYTES = 64_000_000
_AUTHORITY_SCHEMA = "asklegal.hk-v1-source-authority-evidence/v1"
_EXERCISE_SCHEMA = "asklegal.hk-v1-source-exercise-evidence/v1"
_FAMILIES = ("GLD", "HKEL", "JUDICIARY")
_SCENARIOS = (
    "SOURCE_COMPLETENESS",
    "SOURCE_CONTRACT_DRIFT",
    "SOURCE_INCOMPLETE",
    "SOURCE_NO_CHANGE",
    "SOURCE_RESTART",
    "SOURCE_RETRY",
)
_PAIR_SIZE = 2
_ERROR = "HK_V1_SOURCE_ADMISSION_EVIDENCE_INVALID"


class SourceAdmissionEvidenceError(ValueError):
    """One closed source evidence construction or parsing failure."""


def _fail() -> Never:
    raise SourceAdmissionEvidenceError(_ERROR)


@dataclass(frozen=True, slots=True)
class RetainedSourceAttempt:
    """One exact report and the explicit retained root containing its objects."""

    report_path: Path
    output_root: Path


@dataclass(frozen=True, slots=True)
class SourceExerciseInputs:
    """Exact real owner attempts proving every required Gate-B exercise."""

    completeness: tuple[RetainedSourceAttempt, ...]
    contract_drift: RetainedSourceAttempt
    incomplete: RetainedSourceAttempt
    no_change: tuple[RetainedSourceAttempt, ...]
    restart_before: RetainedSourceAttempt
    restart_after: RetainedSourceAttempt
    retry_before: RetainedSourceAttempt
    retry_after: RetainedSourceAttempt


@dataclass(frozen=True, slots=True)
class SourceAuthorityEvidence:
    """Derived complete two-family source authority facts."""

    observation_cutoff: str
    authority_manifest_fingerprint: str
    execution_authorization_fingerprints: tuple[str, ...]
    source_families: tuple[str, ...]
    fingerprint: str
    result: str = "COMPLETE"


@dataclass(frozen=True, slots=True)
class SourceExerciseEvidence:
    """Derived six-scenario source exercise facts."""

    observation_cutoff: str
    authority_manifest_fingerprint: str
    scenario_names: tuple[str, ...]
    fingerprint: str
    result: str = "COMPLETE"


@dataclass(frozen=True, slots=True)
class _AttemptFacts:
    attempt_id: str
    source_family: str
    cutoff: str
    authority_fingerprint: str
    execution_authorization_fingerprint: str
    predecessor_attempt_id: str | None
    change_state: str
    result: str
    report_fingerprint: str
    object_set_fingerprint: str


def _read_attempt(  # noqa: C901 - closed report plus exact object readback.
    value: RetainedSourceAttempt,
) -> dict[str, JsonValue]:
    root = value.output_root.resolve(strict=True)
    report_path = value.report_path.resolve(strict=True)
    report_path.relative_to(root)
    if value.output_root.is_symlink() or value.report_path.is_symlink():
        _fail()
    report_raw = report_path.read_bytes()
    if not report_raw or len(report_raw) > _MAX_BYTES:
        _fail()
    try:
        parsed = parse_json_bytes(report_raw, max_bytes=_MAX_BYTES)
    except ValueError:
        _fail()
    if type(parsed) is not dict or canonicalize(parsed) != report_raw:
        _fail()
    report = cast("dict[str, object]", parsed)
    try:
        source_execution._predecessor_report_binding(report)
    except source_execution.PredecessorValidationError, TypeError, ValueError:
        _fail()
    objects: dict[str, dict[str, JsonValue]] = {}
    references = list(cast("list[object]", report["endpoints"]))
    raw_attempts = report.get("transport_attempts")
    if type(raw_attempts) is list:
        references.extend(cast("list[object]", raw_attempts))
    for raw_reference in references:
        if type(raw_reference) is not dict:
            _fail()
        reference = cast("dict[str, object]", raw_reference)
        key = reference.get("object_key")
        fingerprint = reference.get("body_fingerprint")
        byte_length = reference.get("byte_length")
        if type(key) is not str or type(fingerprint) is not str or type(byte_length) is not int:
            _fail()
        lexical = root / key
        if lexical.is_symlink():
            _fail()
        path = lexical.resolve(strict=True)
        path.relative_to(root)
        body = path.read_bytes()
        if len(body) != byte_length or "sha256:" + sha256(body).hexdigest() != fingerprint:
            _fail()
        projection: dict[str, JsonValue] = {
            "body_hex": body.hex(),
            "byte_length": len(body),
            "fingerprint": fingerprint,
            "object_key": key,
        }
        existing = objects.get(key)
        if existing is not None and existing != projection:
            _fail()
        objects[key] = projection
    return {
        "objects": [objects[key] for key in sorted(objects)],
        "report_bytes": report_raw.hex(),
        "report_fingerprint": "sha256:" + sha256(report_raw).hexdigest(),
    }


def _parse_attempt(  # noqa: C901, PLR0912, PLR0915 - closed embedded owner grammar.
    value: object,
) -> _AttemptFacts:
    if type(value) is not dict:
        _fail()
    document = cast("dict[str, object]", value)
    if set(document) != {
        "objects",
        "report_bytes",
        "report_fingerprint",
    }:
        _fail()
    report_hex = document.get("report_bytes")
    report_fingerprint = document.get("report_fingerprint")
    objects_raw = document.get("objects")
    if (
        type(report_hex) is not str
        or type(report_fingerprint) is not str
        or type(objects_raw) is not list
    ):
        _fail()
    try:
        report_raw = bytes.fromhex(report_hex)
        parsed = parse_json_bytes(report_raw, max_bytes=_MAX_BYTES)
    except ValueError:
        _fail()
    if (
        not report_raw
        or type(parsed) is not dict
        or canonicalize(parsed) != report_raw
        or report_fingerprint != "sha256:" + sha256(report_raw).hexdigest()
    ):
        _fail()
    report = cast("dict[str, object]", parsed)
    try:
        family, cutoff, authority, _provenance, execution_authority = (
            source_execution._predecessor_report_binding(report)
        )
    except source_execution.PredecessorValidationError, TypeError, ValueError:
        _fail()
    if execution_authority is None:
        _fail()
    objects: dict[str, tuple[str, int, bytes]] = {}
    for raw_object in cast("list[object]", objects_raw):
        if type(raw_object) is not dict:
            _fail()
        item = cast("dict[str, object]", raw_object)
        if set(item) != {
            "body_hex",
            "byte_length",
            "fingerprint",
            "object_key",
        }:
            _fail()
        body_hex = item.get("body_hex")
        byte_length = item.get("byte_length")
        fingerprint = item.get("fingerprint")
        key = item.get("object_key")
        if (
            type(body_hex) is not str
            or type(byte_length) is not int
            or type(fingerprint) is not str
            or type(key) is not str
            or key in objects
        ):
            _fail()
        try:
            body = bytes.fromhex(body_hex)
        except ValueError:
            _fail()
        if len(body) != byte_length or fingerprint != "sha256:" + sha256(body).hexdigest():
            _fail()
        objects[key] = (fingerprint, byte_length, body)
    references = list(cast("list[object]", report["endpoints"]))
    transport_attempts = report.get("transport_attempts")
    if type(transport_attempts) is list:
        references.extend(cast("list[object]", transport_attempts))
    referenced_keys: set[str] = set()
    for raw_reference in references:
        if type(raw_reference) is not dict:
            _fail()
        reference = cast("dict[str, object]", raw_reference)
        key = reference.get("object_key")
        if type(key) is not str or key not in objects:
            _fail()
        fingerprint, byte_length, _body = objects[key]
        if (
            reference.get("body_fingerprint") != fingerprint
            or reference.get("byte_length") != byte_length
        ):
            _fail()
        referenced_keys.add(key)
    if referenced_keys != set(objects):
        _fail()
    object_projection = canonicalize(
        checked_json_value(
            [
                {"byte_length": length, "fingerprint": fingerprint, "object_key": key}
                for key, (fingerprint, length, _body) in sorted(objects.items())
            ]
        )
    )
    attempt_id = report.get("attempt_id")
    predecessor = report.get("predecessor_attempt_id")
    change_state = report.get("change_state")
    result = report.get("result")
    if (
        type(attempt_id) is not str
        or (predecessor is not None and type(predecessor) is not str)
        or type(change_state) is not str
        or type(result) is not str
    ):
        _fail()
    return _AttemptFacts(
        attempt_id,
        family,
        cutoff,
        authority,
        execution_authority,
        predecessor,
        change_state,
        result,
        report_fingerprint,
        "sha256:" + sha256(object_projection).hexdigest(),
    )


def _document(schema_id: str, groups: dict[str, tuple[RetainedSourceAttempt, ...]]) -> bytes:
    value: dict[str, JsonValue] = {
        "groups": {
            key: [_read_attempt(attempt) for attempt in attempts]
            for key, attempts in sorted(groups.items())
        },
        "schema_id": schema_id,
    }
    unsigned = canonicalize(checked_json_value(value))
    value["fingerprint"] = "sha256:" + sha256(unsigned).hexdigest()
    return canonicalize(checked_json_value(value))


def build_source_authority_evidence(attempts: tuple[RetainedSourceAttempt, ...]) -> bytes:
    """Build Gate-A authority evidence from exact complete GLD/HKEL/Judiciary attempts."""
    raw = _document(_AUTHORITY_SCHEMA, {"authority": attempts})
    parse_source_authority_evidence(raw)
    return raw


def build_source_exercise_evidence(inputs: SourceExerciseInputs) -> bytes:
    """Build Gate-B evidence from all six exact source execution scenarios."""
    raw = _document(
        _EXERCISE_SCHEMA,
        {
            "SOURCE_COMPLETENESS": inputs.completeness,
            "SOURCE_CONTRACT_DRIFT": (inputs.contract_drift,),
            "SOURCE_INCOMPLETE": (inputs.incomplete,),
            "SOURCE_NO_CHANGE": inputs.no_change,
            "SOURCE_RESTART": (inputs.restart_before, inputs.restart_after),
            "SOURCE_RETRY": (inputs.retry_before, inputs.retry_after),
        },
    )
    parse_source_exercise_evidence(raw)
    return raw


def _parse_document(raw: bytes, schema_id: str) -> tuple[dict[str, list[object]], str]:
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX_BYTES)
    except ValueError:
        _fail()
    if type(value) is not dict or set(value) != {"fingerprint", "groups", "schema_id"}:
        _fail()
    document = cast("dict[str, object]", value)
    fingerprint = document.get("fingerprint")
    groups = document.get("groups")
    unsigned = {"groups": groups, "schema_id": document.get("schema_id")}
    if (
        canonicalize(value) != raw
        or document.get("schema_id") != schema_id
        or type(fingerprint) is not str
        or fingerprint != "sha256:" + sha256(canonicalize(checked_json_value(unsigned))).hexdigest()
        or type(groups) is not dict
    ):
        _fail()
    typed_groups: dict[str, list[object]] = {}
    for key, group in cast("dict[object, object]", groups).items():
        if type(key) is not str or type(group) is not list or not group:
            _fail()
        typed_groups[key] = cast("list[object]", group)
    return typed_groups, fingerprint


def _common(facts: tuple[_AttemptFacts, ...]) -> tuple[str, str]:
    cutoffs = {item.cutoff for item in facts}
    authorities = {item.authority_fingerprint for item in facts}
    if len(cutoffs) != 1 or len(authorities) != 1:
        _fail()
    return next(iter(cutoffs)), next(iter(authorities))


def _complete_family_set(facts: tuple[_AttemptFacts, ...], *, no_change: bool = False) -> None:
    if (
        tuple(sorted(item.source_family for item in facts)) != _FAMILIES
        or any(item.result != "COMPLETE" for item in facts)
        or (no_change and any(item.change_state != "NO_CHANGE_OBSERVED" for item in facts))
    ):
        _fail()


def parse_source_authority_evidence(raw: bytes) -> SourceAuthorityEvidence:
    """Reparse exact Gate-A source reports and derive their common authority."""
    groups, fingerprint = _parse_document(raw, _AUTHORITY_SCHEMA)
    if set(groups) != {"authority"}:
        _fail()
    facts = tuple(_parse_attempt(item) for item in groups["authority"])
    _complete_family_set(facts)
    cutoff, authority = _common(facts)
    return SourceAuthorityEvidence(
        cutoff,
        authority,
        tuple(sorted(item.execution_authorization_fingerprint for item in facts)),
        _FAMILIES,
        fingerprint,
    )


def parse_source_exercise_evidence(raw: bytes) -> SourceExerciseEvidence:
    """Reparse and derive every required Gate-B source behavior scenario."""
    groups, fingerprint = _parse_document(raw, _EXERCISE_SCHEMA)
    if tuple(sorted(groups)) != tuple(sorted(_SCENARIOS)):
        _fail()
    parsed = {key: tuple(_parse_attempt(item) for item in group) for key, group in groups.items()}
    completeness = parsed["SOURCE_COMPLETENESS"]
    no_change = parsed["SOURCE_NO_CHANGE"]
    _complete_family_set(completeness)
    _complete_family_set(no_change, no_change=True)
    drift = parsed["SOURCE_CONTRACT_DRIFT"]
    incomplete = parsed["SOURCE_INCOMPLETE"]
    restart = parsed["SOURCE_RESTART"]
    retry = parsed["SOURCE_RETRY"]
    if (
        len(drift) != 1
        or drift[0].result != "SOURCE_CONTRACT_CHANGED"
        or len(incomplete) != 1
        or incomplete[0].result
        not in {
            "CHALLENGE_AUTHORITY_REQUIRED",
            "EVIDENCE_CAPTURED_INCOMPLETE",
            "OBSERVATION_BUDGET_EXHAUSTED",
            "OBSERVATION_EXECUTION_FAILURE",
            "SESSION_PROCEDURE_NOT_IMPLEMENTED",
            "SOURCE_OUTAGE",
            "TRUNCATED_RESPONSE",
        }
        or len(restart) != _PAIR_SIZE
        or restart[0].report_fingerprint != restart[1].report_fingerprint
        or restart[0].object_set_fingerprint != restart[1].object_set_fingerprint
        or len(retry) != _PAIR_SIZE
        or retry[0].result == "COMPLETE"
        or retry[1].result != "COMPLETE"
        or retry[1].source_family != retry[0].source_family
        or retry[1].predecessor_attempt_id != retry[0].attempt_id
    ):
        _fail()
    all_facts = tuple(item for group in parsed.values() for item in group)
    cutoff, authority = _common(all_facts)
    return SourceExerciseEvidence(cutoff, authority, _SCENARIOS, fingerprint)
