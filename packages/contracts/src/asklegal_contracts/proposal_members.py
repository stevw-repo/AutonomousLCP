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
_ISSUED_ID = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")
_LOOKUP_ID = re.compile(r"^rtl_[0-9a-f]{48}$")
_SHARD_ID = re.compile(r"^rts_[0-9a-f]{48}$")
_SCHEMA_VERSION = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,9})?Z$"
)
_PAIR_SIZE = 2
_PREDICATE_SIZE = 3
_REFERENCE_TYPES = frozenset(
    {
        "ACTOR",
        "AGGREGATE",
        "APPROVAL",
        "ARTIFACT",
        "ATTESTATION",
        "BUILD",
        "CAPABILITY_PROFILE",
        "CARRY_FORWARD_SELECTION",
        "COMMAND",
        "COMMAND_RESULT",
        "CONFIGURATION",
        "CONTRACT",
        "CONTRACT_SET",
        "CORPUS_RELEASE",
        "COVERAGE_GAP",
        "DECISION",
        "DESIRED_STATE_INVENTORY",
        "EFFECT_INTENT",
        "EFFECT_RECEIPT",
        "EMBEDDING_PROFILE",
        "EMBEDDING_RECEIPT",
        "EMBEDDING_REQUEST",
        "EVIDENCE",
        "EXECUTION_EVENT",
        "EXECUTION_LINEAGE",
        "LEGAL_ITEM",
        "LEGAL_LOCATION",
        "LEGAL_STATUS_EVENT",
        "OBSERVATION",
        "OFFICIAL_VERSION",
        "PINECONE_INDEX_GENERATION",
        "POLICY_PROFILE",
        "PROMOTION_MANIFEST",
        "PROPOSAL_PACKAGE",
        "QUARANTINE",
        "QUERY_CONTRACT",
        "RECORD_TRACEABILITY_LOOKUP",
        "RELEASE_SCOPE",
        "RELEASE_SCOPE_REGISTRY",
        "ROUTING_CONFIGURATION",
        "RULEBOOK",
        "SEARCH_RECORD",
        "SERVING_STATE",
        "SOURCE",
        "SOURCE_ENDPOINT",
        "SOURCE_SNAPSHOT",
        "VALIDATION",
        "WORKFLOW_PROFILE",
        "WORK_ITEM",
    }
)
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
_PROMOTION_EFFECT_BINDINGS = {
    "BACKUP_MUTATION": ("MANAGE_BACKUP", "BACKUP_STORE"),
    "EMBEDDING_PROVIDER_CALL": ("CALL_EMBEDDING_PROVIDER", "EMBEDDING_PROVIDER"),
    "PINECONE_MUTATION": ("MUTATE_PINECONE", "SERVING_TARGET"),
    "RELEASE_PUBLICATION": ("PUBLISH_RELEASE", "RELEASE_STORE"),
    "ROUTING_ACTIVATION": ("ACTIVATE_ROUTING", "ROUTING_TARGET"),
}
_PROMOTION_STOP_CONDITIONS = (
    "ATTEMPT_CEILING",
    "AUTHORITY_INVALID",
    "CANCELLATION_BEFORE_EFFECT",
    "CAPABILITY_INACTIVE",
    "DEADLINE",
    "POSTCONDITION_MET",
    "PRECONDITION_CHANGED",
)


class ProposalMemberViolation(RuntimeError):
    """One closed semantic failure in a frozen proposal member."""

    def __init__(self, role: str, detail: str) -> None:
        """Create a stable failure without embedding source content."""
        self.role = role
        self.detail = detail
        super().__init__(f"{role}: {detail}")


@dataclass(frozen=True, slots=True)
class _PromotionActionBindings:
    candidate_serving_state_fingerprint: str
    desired_state_fingerprint: str
    embedding_profile_fingerprint: str
    valid_from: str
    valid_until: str


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
    record_owners: tuple[tuple[str, str, str], ...]
    evidence_refs: tuple[str, ...]
    validation_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DesiredFacts:
    inventory_id: str
    inventory_fingerprint: str
    scope_releases: tuple[tuple[str, str], ...]
    record_ids: tuple[str, ...]
    records: tuple[_DesiredRecord, ...]


@dataclass(frozen=True, slots=True)
class _DesiredRecord:
    record_id: str
    serving_payload_fingerprint: str
    scope_id: str
    release_id: str


@dataclass(frozen=True, slots=True)
class _TraceabilityShardDescriptor:
    scope_id: str
    release_id: str
    path: str
    entry_count: int
    fingerprint: str


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
    record_owners: list[tuple[str, str, str]] = []
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
        records = _strings(role, release, "record_ids", pattern=_RECORD_ID)
        evidence = _strings(role, release, "evidence_refs", nonempty=True)
        validation = _strings(role, release, "validation_refs", nonempty=True)
        selections.append((scope_id, release_id))
        record_ids.extend(records)
        record_owners.extend((record_id, scope_id, release_id) for record_id in records)
        evidence_refs.extend(evidence)
        validation_refs.extend(validation)
    if selections != sorted(set(selections)) or len(record_ids) != len(set(record_ids)):
        _fail(role, "release identity")
    return _ReleaseFacts(
        tuple(selections),
        tuple(sorted(record_ids)),
        tuple(sorted(record_owners)),
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
            "records",
            "scope_releases",
        },
    )
    _exact(_text(role, value, "observation_cutoff"), bindings.observation_cutoff, role, "cutoff")
    inventory_id = _identifier(role, value, "inventory_id", "dsi")
    inventory_fingerprint = _sha256(role, value, "inventory_fingerprint")
    raw_records = _objects(role, value, "records")
    records: list[_DesiredRecord] = []
    for record in raw_records:
        _keys(
            role,
            record,
            {
                "record_id",
                "release_id",
                "scope_id",
                "serving_payload_fingerprint",
            },
        )
        records.append(
            _DesiredRecord(
                _identifier(role, record, "record_id", "rec"),
                _sha256(role, record, "serving_payload_fingerprint"),
                _identifier(role, record, "scope_id", "rsc"),
                _identifier(role, record, "release_id", "rel"),
            )
        )
    if not records or records != sorted(records, key=lambda item: item.record_id):
        _fail(role, "records")
    record_ids = tuple(record.record_id for record in records)
    if len(record_ids) != len(set(record_ids)):
        _fail(role, "records")
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
        tuple(records),
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
            "action_contract_version",
            "actions",
            "base_serving_state_id",
            "batch_size",
            "candidate_serving_state_fingerprint",
            "candidate_serving_state_id",
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
    _strings(role, value, "exact_retirement_target_ids")
    _text(role, value, "environment")
    _text(role, value, "freeze_date")
    _text(role, value, "jurisdiction")
    _text(role, value, "project_id")
    valid_from = _text(role, value, "valid_from")
    valid_until = _text(role, value, "valid_until")
    if valid_from >= valid_until:
        _fail(role, "validity window")
    _exact(
        _text(role, value, "action_contract_version"),
        "1.0.0",
        role,
        "action contract version",
    )
    _promotion_actions(
        value,
        _PromotionActionBindings(
            _sha256(role, value, "candidate_serving_state_fingerprint"),
            _sha256(role, value, "desired_state_fingerprint"),
            _sha256(role, value, "embedding_profile_fingerprint"),
            valid_from,
            valid_until,
        ),
    )
    _predicates(value)
    return _ManifestFacts(
        _integer(role, value, "batch_size", minimum=1),
        _sha256(role, value, "coverage_fingerprint"),
        _sha256(role, value, "desired_state_fingerprint"),
        _sha256(role, value, "embedding_profile_fingerprint"),
    )


def _promotion_actions(
    value: dict[str, JsonValue],
    bindings: _PromotionActionBindings,
) -> None:
    role = "PROMOTION_MANIFEST"
    actions = _objects(role, value, "actions")
    if not actions:
        _fail(role, "actions")
    action_ids: list[str] = []
    idempotency_keys: list[str] = []
    for expected_sequence, action in enumerate(actions, start=1):
        action_id, idempotency_key = _promotion_action(
            action,
            expected_sequence,
            bindings,
        )
        action_ids.append(action_id)
        idempotency_keys.append(idempotency_key)
    if len(set(action_ids)) != len(action_ids) or len(set(idempotency_keys)) != len(
        idempotency_keys
    ):
        _fail(role, "action identity")


def _promotion_action(
    action: dict[str, JsonValue],
    expected_sequence: int,
    bindings: _PromotionActionBindings,
) -> tuple[str, str]:
    role = "PROMOTION_MANIFEST"
    _keys(
        role,
        action,
        {
            "action_id",
            "attempt_ceiling",
            "capability_profile_ref",
            "compensation",
            "deadline",
            "destination_class",
            "effect_command_fingerprint",
            "effect_type",
            "expected_remote_precondition_ref",
            "input_refs",
            "owning_application",
            "permitted_checkpoint",
            "required_capability",
            "retry_class",
            "sequence",
            "stable_idempotency_key",
            "stop_conditions",
            "success_postcondition_ref",
        },
    )
    if _integer(role, action, "sequence", minimum=1) != expected_sequence:
        _fail(role, "action sequence")
    action_id = _text(role, action, "action_id")
    checkpoint = _text(role, action, "permitted_checkpoint")
    if _CODE.fullmatch(action_id) is None or _CODE.fullmatch(checkpoint) is None:
        _fail(role, "action code")
    effect_type = _text(role, action, "effect_type")
    binding = _PROMOTION_EFFECT_BINDINGS.get(effect_type)
    if (
        binding is None
        or _text(role, action, "owning_application") != "PROMOTION_WORKER"
        or _text(role, action, "required_capability") != binding[0]
        or _text(role, action, "destination_class") != binding[1]
    ):
        _fail(role, "action effect binding")
    inputs = _promotion_references(action.get("input_refs"), nonempty=True)
    capability = _promotion_reference(action.get("capability_profile_ref"))
    if capability[0] != "CAPABILITY_PROFILE" or not capability[1].startswith("cap_"):
        _fail(role, "action capability profile")
    required_inputs = {
        "BACKUP_MUTATION": {("SERVING_STATE", bindings.candidate_serving_state_fingerprint)},
        "EMBEDDING_PROVIDER_CALL": {
            ("DESIRED_STATE_INVENTORY", bindings.desired_state_fingerprint),
            ("EMBEDDING_PROFILE", bindings.embedding_profile_fingerprint),
        },
        "PINECONE_MUTATION": {
            ("DESIRED_STATE_INVENTORY", bindings.desired_state_fingerprint),
            ("SERVING_STATE", bindings.candidate_serving_state_fingerprint),
        },
        "RELEASE_PUBLICATION": {("DESIRED_STATE_INVENTORY", bindings.desired_state_fingerprint)},
        "ROUTING_ACTIVATION": {("SERVING_STATE", bindings.candidate_serving_state_fingerprint)},
    }[effect_type]
    if not required_inputs.issubset({(item[0], item[2]) for item in inputs}):
        _fail(role, "action input binding")
    _sha256(role, action, "effect_command_fingerprint")
    idempotency_key = _text(role, action, "stable_idempotency_key")
    retry_class = _text(role, action, "retry_class")
    attempt_ceiling = _integer(role, action, "attempt_ceiling", minimum=1)
    if retry_class not in {"NEVER", "RECONCILE_BEFORE_RETRY", "SAFE_SAME_INTENT"} or (
        retry_class == "NEVER" and attempt_ceiling != 1
    ):
        _fail(role, "action retry")
    deadline = _text(role, action, "deadline")
    if _UTC_TIMESTAMP.fullmatch(deadline) is None or not (
        bindings.valid_from < deadline <= bindings.valid_until
    ):
        _fail(role, "action deadline")
    stops = action.get("stop_conditions")
    if not isinstance(stops, list) or tuple(stops) != _PROMOTION_STOP_CONDITIONS:
        _fail(role, "action stop conditions")
    _promotion_contract_reference(action.get("expected_remote_precondition_ref"))
    _promotion_contract_reference(action.get("success_postcondition_ref"))
    _promotion_compensation(action.get("compensation"))
    return action_id, idempotency_key


def _promotion_references(
    value: JsonValue | None,
    *,
    nonempty: bool,
) -> tuple[tuple[str, str, str], ...]:
    role = "PROMOTION_MANIFEST"
    if not isinstance(value, list):
        _fail(role, "action references")
    result = tuple(_promotion_reference(item) for item in value)
    if (nonempty and not result) or result != tuple(sorted(set(result))):
        _fail(role, "action references")
    return result


def _promotion_reference(value: JsonValue | None) -> tuple[str, str, str]:
    role = "PROMOTION_MANIFEST"
    if not isinstance(value, dict):
        _fail(role, "action reference")
    _keys(role, value, {"fingerprint", "ref_id", "ref_type"})
    ref_type = _text(role, value, "ref_type")
    ref_id = _text(role, value, "ref_id")
    if ref_type not in _REFERENCE_TYPES or _ISSUED_ID.fullmatch(ref_id) is None:
        _fail(role, "action reference")
    return ref_type, ref_id, _sha256(role, value, "fingerprint")


def _promotion_contract_reference(value: JsonValue | None) -> None:
    role = "PROMOTION_MANIFEST"
    if not isinstance(value, dict):
        _fail(role, "action contract reference")
    _keys(role, value, {"contract_id", "fingerprint", "version"})
    _text(role, value, "contract_id")
    if _SCHEMA_VERSION.fullmatch(_text(role, value, "version")) is None:
        _fail(role, "action contract reference")
    _sha256(role, value, "fingerprint")


def _promotion_compensation(value: JsonValue | None) -> None:
    role = "PROMOTION_MANIFEST"
    if not isinstance(value, dict):
        _fail(role, "action compensation")
    mode = _text(role, value, "mode")
    if mode == "NO_COMPENSATION" and set(value) == {"mode"}:
        return
    if mode == "DECLARED_COMPENSATION" and set(value) == {"contract_ref", "mode"}:
        _promotion_contract_reference(value.get("contract_ref"))
        return
    _fail(role, "action compensation")


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
    shard_contents: Mapping[str, bytes],
    desired: _DesiredFacts,
) -> tuple[str, ...]:
    _traceability_manifest_identity(value)
    profile_ids = _traceability_profiles(value)
    descriptors = _traceability_descriptors(value, desired)
    observed_entries, used_profiles = _traceability_shard_entries(
        descriptors,
        shard_contents,
        frozenset(profile_ids),
    )
    role = "RECORD_TRACEABILITY"
    total_entry_count = _integer(role, value, "total_entry_count")
    if sum(item.entry_count for item in descriptors) != total_entry_count or (
        total_entry_count != len(desired.records)
    ):
        _fail(role, "entry count")
    if set(profile_ids) != used_profiles:
        _fail(role, "serving profile use")
    if tuple(sorted(observed_entries, key=lambda item: item.record_id)) != desired.records:
        _fail(role, "desired-state binding")
    identities = tuple(item.record_id for item in observed_entries)
    if len(identities) != len(set(identities)):
        _fail(role, "duplicate entry")
    return tuple(sorted(identities))


def _traceability_manifest_identity(value: dict[str, JsonValue]) -> None:
    role = "RECORD_TRACEABILITY"
    _keys(
        role,
        value,
        {
            "entry_schema_fingerprint",
            "entry_schema_id",
            "entry_schema_version",
            "lookup_revision_id",
            "manifest_schema_fingerprint",
            "schema_id",
            "schema_version",
            "serving_record_profiles",
            "shards",
            "total_entry_count",
        },
    )
    if (
        _text(role, value, "schema_id") != "asklegal.record-traceability-lookup-manifest"
        or _text(role, value, "schema_version") != "1.0.0"
        or _text(role, value, "entry_schema_id") != "asklegal.record-traceability-entry"
        or _text(role, value, "entry_schema_version") != "1.0.0"
        or _LOOKUP_ID.fullmatch(_text(role, value, "lookup_revision_id")) is None
    ):
        _fail(role, "manifest identity")
    _sha256(role, value, "manifest_schema_fingerprint")
    _sha256(role, value, "entry_schema_fingerprint")


def _traceability_profiles(value: dict[str, JsonValue]) -> tuple[str, ...]:
    role = "RECORD_TRACEABILITY"
    profiles = _objects(role, value, "serving_record_profiles")
    profile_ids: list[str] = []
    for profile in profiles:
        _keys(
            role,
            profile,
            {"schema_fingerprint", "schema_version", "serving_record_profile_id"},
        )
        profile_id = _text(role, profile, "serving_record_profile_id")
        if _ISSUED_ID.fullmatch(profile_id) is None:
            _fail(role, "serving profile")
        if _SCHEMA_VERSION.fullmatch(_text(role, profile, "schema_version")) is None:
            _fail(role, "serving profile")
        _sha256(role, profile, "schema_fingerprint")
        profile_ids.append(profile_id)
    if profile_ids != sorted(set(profile_ids)):
        _fail(role, "serving profiles")
    return tuple(profile_ids)


def _traceability_descriptors(
    value: dict[str, JsonValue], desired: _DesiredFacts
) -> tuple[_TraceabilityShardDescriptor, ...]:
    role = "RECORD_TRACEABILITY"
    descriptors = _objects(role, value, "shards")
    if not descriptors:
        _fail(role, "shards")
    descriptor_facts: list[_TraceabilityShardDescriptor] = []
    for descriptor in descriptors:
        _keys(
            role,
            descriptor,
            {
                "artifact_fingerprint",
                "corpus_release_id",
                "entry_count",
                "lookup_shard_id",
                "media_type",
                "path",
                "release_scope_id",
            },
        )
        scope_id = _identifier(role, descriptor, "release_scope_id", "rsc")
        release_id = _identifier(role, descriptor, "corpus_release_id", "rel")
        shard_id = _text(role, descriptor, "lookup_shard_id")
        path = _text(role, descriptor, "path")
        if (
            _SHARD_ID.fullmatch(shard_id) is None
            or path != f"entries/{shard_id}.ndjson"
            or _text(role, descriptor, "media_type") != "application/x-ndjson"
        ):
            _fail(role, "shard descriptor")
        descriptor_facts.append(
            _TraceabilityShardDescriptor(
                scope_id,
                release_id,
                path,
                _integer(role, descriptor, "entry_count"),
                _sha256(role, descriptor, "artifact_fingerprint"),
            )
        )
    observed_scopes = tuple((item.scope_id, item.release_id) for item in descriptor_facts)
    if observed_scopes != desired.scope_releases:
        _fail(role, "shard scope binding")
    return tuple(descriptor_facts)


def _traceability_shard_entries(
    descriptors: tuple[_TraceabilityShardDescriptor, ...],
    shard_contents: Mapping[str, bytes],
    profile_ids: frozenset[str],
) -> tuple[tuple[_DesiredRecord, ...], set[str]]:
    role = "RECORD_TRACEABILITY"
    expected_paths = {item.path for item in descriptors}
    if set(shard_contents) != expected_paths or any(
        type(content) is not bytes for content in shard_contents.values()
    ):
        _fail(role, "shard inventory")

    observed_entries: list[_DesiredRecord] = []
    used_profiles: set[str] = set()
    for descriptor in descriptors:
        content = shard_contents[descriptor.path]
        if _fingerprint(content) != descriptor.fingerprint:
            _fail(role, "shard fingerprint")
        lines = _ndjson_lines(content, descriptor.entry_count)
        documents = tuple(_document(role, line) for line in lines)
        shard_entries = tuple(_traceability_entry(document, profile_ids) for document in documents)
        shard_ids = tuple(item.record_id for item in shard_entries)
        if shard_ids != tuple(sorted(set(shard_ids))) or any(
            item.scope_id != descriptor.scope_id or item.release_id != descriptor.release_id
            for item in shard_entries
        ):
            _fail(role, "shard entries")
        observed_entries.extend(shard_entries)
        used_profiles.update(
            _text(role, document, "serving_record_profile_id") for document in documents
        )
    return tuple(observed_entries), used_profiles


def _ndjson_lines(content: bytes, expected_count: int) -> tuple[bytes, ...]:
    role = "RECORD_TRACEABILITY"
    if expected_count == 0:
        if content:
            _fail(role, "zero-entry shard")
        return ()
    if not content.endswith(b"\n") or b"\r" in content or content.startswith(b"\xef\xbb\xbf"):
        _fail(role, "NDJSON framing")
    lines = tuple(content[:-1].split(b"\n"))
    if len(lines) != expected_count or any(not line for line in lines):
        _fail(role, "NDJSON count")
    return lines


def _traceability_reference(value: JsonValue | None, field: str) -> tuple[str, str, str]:
    role = "RECORD_TRACEABILITY"
    if not isinstance(value, dict):
        _fail(role, field)
    _keys(role, value, {"fingerprint", "ref_id", "ref_type"})
    ref_type = _text(role, value, "ref_type")
    ref_id = _text(role, value, "ref_id")
    fingerprint_value = _sha256(role, value, "fingerprint")
    if ref_type not in _REFERENCE_TYPES or _ISSUED_ID.fullmatch(ref_id) is None:
        _fail(role, field)
    return ref_type, ref_id, fingerprint_value


def _traceability_references(
    value: Mapping[str, JsonValue], field: str, *, required: bool = False
) -> tuple[tuple[str, str, str], ...]:
    role = "RECORD_TRACEABILITY"
    raw = value.get(field)
    if not isinstance(raw, list):
        _fail(role, field)
    references = tuple(_traceability_reference(item, field) for item in raw)
    if references != tuple(sorted(set(references))) or (required and not references):
        _fail(role, field)
    return references


def _traceability_entry(value: dict[str, JsonValue], profile_ids: frozenset[str]) -> _DesiredRecord:
    role = "RECORD_TRACEABILITY"
    _keys(
        role,
        value,
        {
            "authority_note_evidence",
            "corpus_release_id",
            "display_citation_ids",
            "evidence_refs",
            "grouping_ids",
            "legal_item_id",
            "legal_location_ids",
            "official_version_ids",
            "release_scope_id",
            "search_record_id",
            "serving_payload_fingerprint",
            "serving_record_profile_id",
        },
    )
    profile_id = _text(role, value, "serving_record_profile_id")
    if profile_id not in profile_ids:
        _fail(role, "entry profile")
    _identifier(role, value, "legal_item_id", "lit")
    _strings(
        role,
        value,
        "official_version_ids",
        pattern=re.compile(r"^ofv_[0-9a-f]{48}$"),
        nonempty=True,
    )
    _strings(
        role,
        value,
        "legal_location_ids",
        pattern=re.compile(r"^loc_[0-9a-f]{48}$"),
        nonempty=True,
    )
    _strings(role, value, "grouping_ids", pattern=_ISSUED_ID)
    _strings(role, value, "display_citation_ids", pattern=_ISSUED_ID)
    _traceability_references(value, "evidence_refs", required=True)
    authority = value.get("authority_note_evidence")
    if not isinstance(authority, dict):
        _fail(role, "authority_note_evidence")
    _keys(
        role,
        authority,
        {"decision_ref", "rendered_value_fingerprint", "supporting_evidence_refs"},
    )
    _sha256(role, authority, "rendered_value_fingerprint")
    _traceability_reference(authority.get("decision_ref"), "decision_ref")
    _traceability_references(authority, "supporting_evidence_refs")
    return _DesiredRecord(
        _identifier(role, value, "search_record_id", "rec"),
        _sha256(role, value, "serving_payload_fingerprint"),
        _identifier(role, value, "release_scope_id", "rsc"),
        _identifier(role, value, "corpus_release_id", "rel"),
    )


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
    traceability_shards_by_path: Mapping[str, bytes],
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
        or tuple((item.record_id, item.scope_id, item.release_id) for item in desired.records)
        != releases.record_owners
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
    trace_record_ids = _traceability(
        documents["RECORD_TRACEABILITY"],
        traceability_shards_by_path,
        desired,
    )
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
