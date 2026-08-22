"""Fail-closed semantic validation for the eleven V1 proposal members."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Never

from asklegal_contracts.canonical import canonicalize
from asklegal_contracts.errors import ContractViolation
from asklegal_contracts.json_types import JsonValue
from asklegal_contracts.strict_json import parse_json_bytes

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*_[0-9a-f]{48}$")
_RECORD_ID = re.compile(r"^rec_[0-9a-f]{48}$")
_PAIR_SIZE = 2
_PREDICATE_SIZE = 3
_REQUIRED_ROLES = frozenset(
    {
        "CHANGE_INVENTORY",
        "CORPUS_RELEASES",
        "COST_AND_CAPACITY",
        "COVERAGE_STATUS",
        "DESIRED_STATE_INVENTORIES",
        "PROMOTION_MANIFEST",
        "RECORD_TRACEABILITY",
        "RECOVERY_READINESS",
        "REVIEW_REPORT",
        "SERVING_STATE_DEFINITION",
        "VALIDATION",
    }
)
_CHANGE_CATEGORIES = (
    "additions",
    "carried_forward",
    "replacements",
    "retirements",
    "unchanged",
    "withholdings",
)
_ACTIVE_CHANGE_CATEGORIES = (*_CHANGE_CATEGORIES[:3], _CHANGE_CATEGORIES[4])
_COVERAGE_WARNING = {
    "CURRENT": "NO_COVERAGE_WARNING",
    "KNOWN_GAP": "COVERAGE_KNOWN_GAP",
    "NOT_READY": "COVERAGE_NOT_READY",
    "WITHHELD": "COVERAGE_WITHHELD",
}
_REQUIRED_VALIDATION_CHECKS = frozenset(
    {"EVIDENCE_BOUND", "SCOPE_COMPLETE", "TRACEABILITY_COMPLETE"}
)


class ProposalMemberViolation(RuntimeError):
    """One closed semantic failure in a frozen proposal member."""

    def __init__(self, role: str, detail: str) -> None:
        """Create a stable failure without embedding source content."""
        self.role = role
        self.detail = detail
        super().__init__(f"{role}: {detail}")


@dataclass(frozen=True, slots=True)
class ProposalMemberBindings:
    """Authority facts the proposal members must reproduce exactly."""

    observation_cutoff: str
    promotion_manifest_id: str
    promotion_manifest_fingerprint: str
    base_serving_state_id: str
    candidate_serving_state_id: str
    candidate_serving_state_fingerprint: str


@dataclass(frozen=True, slots=True)
class _ReleaseFacts:
    scope_releases: tuple[tuple[str, str], ...]
    record_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    validation_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DesiredFacts:
    inventory_id: str
    inventory_fingerprint: str
    scope_releases: tuple[tuple[str, str], ...]
    record_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CoverageFacts:
    manifest_id: str
    fingerprint: str
    scope_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ManifestFacts:
    batch_size: int
    coverage_fingerprint: str
    desired_state_fingerprint: str
    embedding_profile_fingerprint: str


def _stable_id(prefix: str, *values: str) -> str:
    digest = sha256(chr(31).join(values).encode()).hexdigest()[:48]
    return f"{prefix}_{digest}"


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _fail(role: str, detail: str) -> Never:
    raise ProposalMemberViolation(role, detail)


def _document(role: str, content: bytes) -> dict[str, JsonValue]:
    try:
        value = parse_json_bytes(content, max_bytes=1_000_000)
    except ContractViolation as error:
        raise ProposalMemberViolation(role, "JSON") from error
    if not isinstance(value, dict) or canonicalize(value) != content:
        _fail(role, "canonical object")
    if value == {"role": role}:
        _fail(role, "placeholder")
    return value


def _keys(role: str, value: Mapping[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        _fail(role, "fields")


def _text(role: str, value: Mapping[str, JsonValue], field: str) -> str:
    return _string_value(role, value.get(field), field)


def _string_value(role: str, value: JsonValue | None, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        _fail(role, field)
    return value


def _integer(
    role: str,
    value: Mapping[str, JsonValue],
    field: str,
    *,
    minimum: int = 0,
) -> int:
    result = value.get(field)
    if type(result) is not int or result < minimum:
        _fail(role, field)
    return result


def _boolean(role: str, value: Mapping[str, JsonValue], field: str) -> bool:
    result = value.get(field)
    if type(result) is not bool:
        _fail(role, field)
    return result


def _identifier(role: str, value: Mapping[str, JsonValue], field: str, prefix: str) -> str:
    result = _text(role, value, field)
    if _IDENTIFIER.fullmatch(result) is None or not result.startswith(f"{prefix}_"):
        _fail(role, field)
    return result


def _sha256(role: str, value: Mapping[str, JsonValue], field: str) -> str:
    result = _text(role, value, field)
    if _FINGERPRINT.fullmatch(result) is None:
        _fail(role, field)
    return result


def _strings(
    role: str,
    value: Mapping[str, JsonValue],
    field: str,
    *,
    pattern: re.Pattern[str] | None = None,
    nonempty: bool = False,
) -> tuple[str, ...]:
    raw = value.get(field)
    if not isinstance(raw, list):
        _fail(role, field)
    result = tuple(_string_value(role, item, field) for item in raw)
    if result != tuple(sorted(set(result))) or (nonempty and not result):
        _fail(role, field)
    if pattern is not None and any(pattern.fullmatch(item) is None for item in result):
        _fail(role, field)
    return result


def _objects(role: str, value: Mapping[str, JsonValue], field: str) -> list[dict[str, JsonValue]]:
    raw = value.get(field)
    if not isinstance(raw, list):
        _fail(role, field)
    result: list[dict[str, JsonValue]] = []
    for item in raw:
        if not isinstance(item, dict):
            _fail(role, field)
        result.append(item)
    return result


def _exact(value: str, expected: str, role: str, field: str) -> None:
    if value != expected:
        _fail(role, field)


def _disjoint(role: str, values: tuple[tuple[str, ...], ...]) -> None:
    flattened = tuple(item for group in values for item in group)
    if len(flattened) != len(set(flattened)):
        _fail(role, "overlapping categories")


def _parse_documents(contents_by_role: Mapping[str, bytes]) -> dict[str, dict[str, JsonValue]]:
    if set(contents_by_role) != set(_REQUIRED_ROLES):
        _fail("PROPOSAL", "roles")
    return {role: _document(role, contents_by_role[role]) for role in sorted(_REQUIRED_ROLES)}


def _change_inventory(
    value: dict[str, JsonValue],
    bindings: ProposalMemberBindings,
    desired: _DesiredFacts,
) -> None:
    role = "CHANGE_INVENTORY"
    _keys(role, value, {"observation_cutoff", *_CHANGE_CATEGORIES})
    _exact(_text(role, value, "observation_cutoff"), bindings.observation_cutoff, role, "cutoff")
    categories = tuple(
        _strings(role, value, category, pattern=_RECORD_ID) for category in _CHANGE_CATEGORIES
    )
    _disjoint(role, categories)
    by_category = dict(zip(_CHANGE_CATEGORIES, categories, strict=True))
    active = tuple(
        sorted(item for category in _ACTIVE_CHANGE_CATEGORIES for item in by_category[category])
    )
    if active != desired.record_ids:
        _fail(role, "desired records")


def _corpus_releases(
    value: dict[str, JsonValue], bindings: ProposalMemberBindings
) -> _ReleaseFacts:
    role = "CORPUS_RELEASES"
    _keys(role, value, {"observation_cutoff", "releases"})
    _exact(_text(role, value, "observation_cutoff"), bindings.observation_cutoff, role, "cutoff")
    releases = _objects(role, value, "releases")
    if not releases:
        _fail(role, "releases")
    selections: list[tuple[str, str]] = []
    record_ids: list[str] = []
    evidence_refs: list[str] = []
    validation_refs: list[str] = []
    for release in releases:
        _keys(
            role,
            release,
            {
                "evidence_refs",
                "observation_cutoff",
                "record_ids",
                "release_id",
                "scope_id",
                "validation_refs",
            },
        )
        scope_id = _identifier(role, release, "scope_id", "rsc")
        release_id = _identifier(role, release, "release_id", "rel")
        _exact(
            _text(role, release, "observation_cutoff"),
            bindings.observation_cutoff,
            role,
            "release cutoff",
        )
        records = _strings(role, release, "record_ids", pattern=_RECORD_ID, nonempty=True)
        evidence = _strings(role, release, "evidence_refs", nonempty=True)
        validation = _strings(role, release, "validation_refs", nonempty=True)
        selections.append((scope_id, release_id))
        record_ids.extend(records)
        evidence_refs.extend(evidence)
        validation_refs.extend(validation)
    if selections != sorted(set(selections)) or len(record_ids) != len(set(record_ids)):
        _fail(role, "release identity")
    return _ReleaseFacts(
        tuple(selections),
        tuple(sorted(record_ids)),
        tuple(sorted(set(evidence_refs))),
        tuple(sorted(set(validation_refs))),
    )


def _desired_state(value: dict[str, JsonValue], bindings: ProposalMemberBindings) -> _DesiredFacts:
    role = "DESIRED_STATE_INVENTORIES"
    _keys(
        role,
        value,
        {
            "inventory_fingerprint",
            "inventory_id",
            "observation_cutoff",
            "record_ids",
            "scope_releases",
        },
    )
    _exact(_text(role, value, "observation_cutoff"), bindings.observation_cutoff, role, "cutoff")
    inventory_id = _identifier(role, value, "inventory_id", "dsi")
    inventory_fingerprint = _sha256(role, value, "inventory_fingerprint")
    record_ids = _strings(role, value, "record_ids", pattern=_RECORD_ID, nonempty=True)
    raw_selections = value.get("scope_releases")
    if not isinstance(raw_selections, list):
        _fail(role, "scope_releases")
    selections: list[tuple[str, str]] = []
    for raw in raw_selections:
        if not isinstance(raw, list) or len(raw) != _PAIR_SIZE:
            _fail(role, "scope_releases")
        scope_id = _string_value(role, raw[0], "scope_releases")
        release_id = _string_value(role, raw[1], "scope_releases")
        if (
            re.fullmatch(r"rsc_[0-9a-f]{48}", scope_id) is None
            or re.fullmatch(r"rel_[0-9a-f]{48}", release_id) is None
        ):
            _fail(role, "scope_releases")
        selections.append((scope_id, release_id))
    if not selections or selections != sorted(set(selections)):
        _fail(role, "scope_releases")
    return _DesiredFacts(
        inventory_id,
        inventory_fingerprint,
        tuple(selections),
        record_ids,
    )


def _coverage(
    value: dict[str, JsonValue],
    content: bytes,
    bindings: ProposalMemberBindings,
) -> _CoverageFacts:
    role = "COVERAGE_STATUS"
    allowed = {"observation_cutoff", "scopes", "serving_state_id", "source_cycle"}
    if set(value) not in (
        allowed,
        allowed - {"source_cycle"},
    ):
        _fail(role, "fields")
    _exact(_text(role, value, "observation_cutoff"), bindings.observation_cutoff, role, "cutoff")
    _exact(
        _identifier(role, value, "serving_state_id", "srv"),
        bindings.candidate_serving_state_id,
        role,
        "serving state",
    )
    scopes = _objects(role, value, "scopes")
    scope_ids: list[str] = []
    for scope in scopes:
        _keys(
            role,
            scope,
            {
                "gap_refs",
                "last_verified_at",
                "quarantine_refs",
                "scope_id",
                "source_failure_refs",
                "status",
                "warning",
            },
        )
        scope_ids.append(_identifier(role, scope, "scope_id", "rsc"))
        _text(role, scope, "last_verified_at")
        gaps = _strings(role, scope, "gap_refs")
        quarantines = _strings(role, scope, "quarantine_refs")
        failures = _strings(role, scope, "source_failure_refs")
        status = _text(role, scope, "status")
        warning = _text(role, scope, "warning")
        if _COVERAGE_WARNING.get(status) != warning:
            _fail(role, "warning")
        evidence_count = len(gaps) + len(quarantines) + len(failures)
        if (status == "CURRENT") == bool(evidence_count):
            _fail(role, "scope evidence")
    if not scope_ids or scope_ids != sorted(set(scope_ids)):
        _fail(role, "scopes")
    if "source_cycle" in value:
        _source_cycle(value.get("source_cycle"), bindings)
    fingerprint = _fingerprint(content)
    return _CoverageFacts(
        _stable_id("csm", bindings.candidate_serving_state_id, fingerprint),
        fingerprint,
        tuple(scope_ids),
    )


def _source_cycle(raw: JsonValue | None, bindings: ProposalMemberBindings) -> None:
    role = "COVERAGE_STATUS"
    expected = {
        "accounting_complete",
        "byte_length",
        "duplicate_source_ids",
        "fingerprint",
        "gap_source_ids",
        "logical_key",
        "missing_source_ids",
        "observation_cutoff",
        "release_blocking",
        "vault",
        "version_id",
    }
    if not isinstance(raw, dict):
        _fail(role, "source_cycle")
    _keys(role, raw, expected)
    _exact(_text(role, raw, "vault"), "PRIMARY", role, "source_cycle vault")
    logical_key = _text(role, raw, "logical_key")
    if not logical_key.startswith("poc/report/source-coverage-cycle/"):
        _fail(role, "source_cycle logical_key")
    _text(role, raw, "version_id")
    _sha256(role, raw, "fingerprint")
    _integer(role, raw, "byte_length", minimum=1)
    _exact(
        _text(role, raw, "observation_cutoff"),
        bindings.observation_cutoff,
        role,
        "source_cycle cutoff",
    )
    accounting = _boolean(role, raw, "accounting_complete")
    blocking = _boolean(role, raw, "release_blocking")
    missing = _strings(role, raw, "missing_source_ids")
    duplicates = _strings(role, raw, "duplicate_source_ids")
    gaps = _strings(role, raw, "gap_source_ids")
    if accounting == bool(missing or duplicates) or blocking != bool(gaps or missing or duplicates):
        _fail(role, "source_cycle accounting")


def _promotion_manifest(
    value: dict[str, JsonValue],
    content: bytes,
    bindings: ProposalMemberBindings,
) -> _ManifestFacts:
    role = "PROMOTION_MANIFEST"
    _keys(
        role,
        value,
        {
            "action_ids",
            "base_serving_state_id",
            "batch_size",
            "candidate_serving_state_fingerprint",
            "candidate_serving_state_id",
            "capability_enabled",
            "coverage_fingerprint",
            "desired_state_fingerprint",
            "embedding_profile_fingerprint",
            "environment",
            "exact_retirement_target_ids",
            "freeze_date",
            "jurisdiction",
            "project_id",
            "rollback_serving_state_id",
            "valid_from",
            "valid_until",
            "validity_predicates",
        },
    )
    actual_fingerprint = _fingerprint(content)
    _exact(actual_fingerprint, bindings.promotion_manifest_fingerprint, role, "fingerprint")
    _exact(
        _stable_id("pmn", actual_fingerprint),
        bindings.promotion_manifest_id,
        role,
        "manifest identity",
    )
    _exact(
        _identifier(role, value, "base_serving_state_id", "srv"),
        bindings.base_serving_state_id,
        role,
        "base state",
    )
    _exact(
        _identifier(role, value, "candidate_serving_state_id", "srv"),
        bindings.candidate_serving_state_id,
        role,
        "candidate state",
    )
    _exact(
        _sha256(role, value, "candidate_serving_state_fingerprint"),
        bindings.candidate_serving_state_fingerprint,
        role,
        "candidate fingerprint",
    )
    _identifier(role, value, "rollback_serving_state_id", "srv")
    actions = _strings(role, value, "action_ids", nonempty=True)
    _strings(role, value, "exact_retirement_target_ids")
    _text(role, value, "environment")
    _text(role, value, "freeze_date")
    _text(role, value, "jurisdiction")
    _text(role, value, "project_id")
    _boolean(role, value, "capability_enabled")
    valid_from = _text(role, value, "valid_from")
    valid_until = _text(role, value, "valid_until")
    if valid_from >= valid_until or not actions:
        _fail(role, "validity window")
    _predicates(value)
    return _ManifestFacts(
        _integer(role, value, "batch_size", minimum=1),
        _sha256(role, value, "coverage_fingerprint"),
        _sha256(role, value, "desired_state_fingerprint"),
        _sha256(role, value, "embedding_profile_fingerprint"),
    )


def _predicates(value: dict[str, JsonValue]) -> None:
    role = "PROMOTION_MANIFEST"
    raw = value.get("validity_predicates")
    if not isinstance(raw, list) or not raw:
        _fail(role, "validity_predicates")
    predicates: list[tuple[str, str, str]] = []
    for item in raw:
        if not isinstance(item, list) or len(item) != _PREDICATE_SIZE:
            _fail(role, "validity_predicates")
        predicate_id = _string_value(role, item[0], "validity_predicates")
        version = _string_value(role, item[1], "validity_predicates")
        predicate_fingerprint = _string_value(role, item[2], "validity_predicates")
        if (
            re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version)
            is None
            or _FINGERPRINT.fullmatch(predicate_fingerprint) is None
        ):
            _fail(role, "validity_predicates")
        predicates.append((predicate_id, version, predicate_fingerprint))
    if predicates != sorted(set(predicates)):
        _fail(role, "validity_predicates")


def _traceability(
    value: dict[str, JsonValue],
    bindings: ProposalMemberBindings,
) -> tuple[str, ...]:
    role = "RECORD_TRACEABILITY"
    _keys(role, value, {"observation_cutoff", "records"})
    _exact(_text(role, value, "observation_cutoff"), bindings.observation_cutoff, role, "cutoff")
    records = _objects(role, value, "records")
    identities: list[str] = []
    for record in records:
        _keys(
            role,
            record,
            {
                "artifact_ref",
                "evidence_refs",
                "record_id",
                "release_id",
                "scope_id",
                "serving_payload_fingerprint",
            },
        )
        identities.append(_identifier(role, record, "record_id", "rec"))
        _identifier(role, record, "artifact_ref", "art")
        _identifier(role, record, "release_id", "rel")
        _identifier(role, record, "scope_id", "rsc")
        _sha256(role, record, "serving_payload_fingerprint")
        _strings(role, record, "evidence_refs", nonempty=True)
    if identities != sorted(set(identities)):
        _fail(role, "records")
    return tuple(identities)


def _cost_and_capacity(
    value: dict[str, JsonValue], manifest: _ManifestFacts, record_count: int
) -> None:
    role = "COST_AND_CAPACITY"
    _keys(
        role,
        value,
        {
            "batch_size",
            "estimated_cost_microunits",
            "embedding_profile_fingerprint",
            "record_count",
            "result",
        },
    )
    if (
        _integer(role, value, "batch_size", minimum=1) != manifest.batch_size
        or _integer(role, value, "estimated_cost_microunits") < 0
        or _integer(role, value, "record_count") != record_count
        or _sha256(role, value, "embedding_profile_fingerprint")
        != manifest.embedding_profile_fingerprint
        or _text(role, value, "result") != "PASS"
    ):
        _fail(role, "admission")


def _recovery_readiness(value: dict[str, JsonValue], bindings: ProposalMemberBindings) -> None:
    role = "RECOVERY_READINESS"
    _keys(
        role,
        value,
        {
            "candidate_serving_state_id",
            "predecessor_retained",
            "rollback_serving_state_id",
            "two_copy_backup_required",
        },
    )
    if (
        _identifier(role, value, "candidate_serving_state_id", "srv")
        != bindings.candidate_serving_state_id
        or _identifier(role, value, "rollback_serving_state_id", "srv")
        != bindings.base_serving_state_id
        or not _boolean(role, value, "predecessor_retained")
        or not _boolean(role, value, "two_copy_backup_required")
    ):
        _fail(role, "readiness")


def _serving_state(
    value: dict[str, JsonValue],
    bindings: ProposalMemberBindings,
    desired: _DesiredFacts,
    coverage: _CoverageFacts,
) -> None:
    role = "SERVING_STATE_DEFINITION"
    _keys(
        role,
        value,
        {
            "coverage_manifest_id",
            "desired_state_inventory_id",
            "serving_state_fingerprint",
            "serving_state_id",
        },
    )
    if (
        _identifier(role, value, "coverage_manifest_id", "csm") != coverage.manifest_id
        or _identifier(role, value, "desired_state_inventory_id", "dsi") != desired.inventory_id
        or _identifier(role, value, "serving_state_id", "srv")
        != bindings.candidate_serving_state_id
        or _sha256(role, value, "serving_state_fingerprint")
        != bindings.candidate_serving_state_fingerprint
    ):
        _fail(role, "serving state")


def _validation(
    value: dict[str, JsonValue],
    required_refs: frozenset[str],
) -> None:
    role = "VALIDATION"
    _keys(role, value, {"checks", "result"})
    if _text(role, value, "result") != "PASS":
        _fail(role, "result")
    checks = _objects(role, value, "checks")
    check_ids: list[str] = []
    observed_refs: set[str] = set()
    for check in checks:
        _keys(role, check, {"check_id", "evidence_refs", "result"})
        check_ids.append(_text(role, check, "check_id"))
        if _text(role, check, "result") != "PASS":
            _fail(role, "check result")
        observed_refs.update(_strings(role, check, "evidence_refs", nonempty=True))
    if check_ids != sorted(set(check_ids)) or not _REQUIRED_VALIDATION_CHECKS.issubset(check_ids):
        _fail(role, "checks")
    if not required_refs.issubset(observed_refs):
        _fail(role, "evidence binding")


def _review_report(
    value: dict[str, JsonValue],
    manifest: _ManifestFacts,
    record_count: int,
) -> None:
    role = "REVIEW_REPORT"
    _keys(
        role,
        value,
        {
            "coverage_fingerprint",
            "desired_state_fingerprint",
            "record_count",
            "result",
            "statement",
        },
    )
    if (
        _sha256(role, value, "coverage_fingerprint") != manifest.coverage_fingerprint
        or _sha256(role, value, "desired_state_fingerprint") != manifest.desired_state_fingerprint
        or _integer(role, value, "record_count") != record_count
        or _text(role, value, "result") != "READY"
    ):
        _fail(role, "report")
    _text(role, value, "statement")


def _validate_bindings(bindings: ProposalMemberBindings) -> None:
    role = "PROPOSAL"
    values: tuple[tuple[str, str, re.Pattern[str]], ...] = (
        ("promotion_manifest_id", bindings.promotion_manifest_id, _IDENTIFIER),
        ("base_serving_state_id", bindings.base_serving_state_id, _IDENTIFIER),
        ("candidate_serving_state_id", bindings.candidate_serving_state_id, _IDENTIFIER),
        (
            "promotion_manifest_fingerprint",
            bindings.promotion_manifest_fingerprint,
            _FINGERPRINT,
        ),
        (
            "candidate_serving_state_fingerprint",
            bindings.candidate_serving_state_fingerprint,
            _FINGERPRINT,
        ),
    )
    if not bindings.observation_cutoff:
        _fail(role, "observation_cutoff")
    for field, value, pattern in values:
        if pattern.fullmatch(value) is None:
            _fail(role, field)
    if not bindings.promotion_manifest_id.startswith("pmn_"):
        _fail(role, "promotion_manifest_id")
    for field, value in (
        ("base_serving_state_id", bindings.base_serving_state_id),
        ("candidate_serving_state_id", bindings.candidate_serving_state_id),
    ):
        if not value.startswith("srv_"):
            _fail(role, field)


def validate_v1_proposal_members(
    contents_by_role: Mapping[str, bytes],
    bindings: ProposalMemberBindings,
) -> None:
    """Require one semantically coherent, canonical, reviewable V1 proposal."""
    if type(bindings) is not ProposalMemberBindings:
        _fail("PROPOSAL", "bindings")
    _validate_bindings(bindings)
    documents = _parse_documents(contents_by_role)
    desired = _desired_state(documents["DESIRED_STATE_INVENTORIES"], bindings)
    releases = _corpus_releases(documents["CORPUS_RELEASES"], bindings)
    if (
        desired.scope_releases != releases.scope_releases
        or desired.record_ids != releases.record_ids
    ):
        _fail("PROPOSAL", "release inventory binding")
    coverage = _coverage(
        documents["COVERAGE_STATUS"], contents_by_role["COVERAGE_STATUS"], bindings
    )
    if coverage.scope_ids != tuple(scope_id for scope_id, _release_id in releases.scope_releases):
        _fail("PROPOSAL", "coverage scope binding")
    manifest = _promotion_manifest(
        documents["PROMOTION_MANIFEST"],
        contents_by_role["PROMOTION_MANIFEST"],
        bindings,
    )
    if (
        manifest.coverage_fingerprint != coverage.fingerprint
        or manifest.desired_state_fingerprint != desired.inventory_fingerprint
    ):
        _fail("PROPOSAL", "manifest member binding")
    _change_inventory(documents["CHANGE_INVENTORY"], bindings, desired)
    trace_record_ids = _traceability(documents["RECORD_TRACEABILITY"], bindings)
    if trace_record_ids != desired.record_ids:
        _fail("PROPOSAL", "traceability record binding")
    _cost_and_capacity(documents["COST_AND_CAPACITY"], manifest, len(desired.record_ids))
    _recovery_readiness(documents["RECOVERY_READINESS"], bindings)
    _serving_state(documents["SERVING_STATE_DEFINITION"], bindings, desired, coverage)
    _validation(
        documents["VALIDATION"],
        frozenset((*releases.evidence_refs, *releases.validation_refs)),
    )
    _review_report(documents["REVIEW_REPORT"], manifest, len(desired.record_ids))
