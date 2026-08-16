"""Closed filesystem loader for executable Source Rulebook Packages."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

from .model import (
    GenerativeTask,
    LegalDisposition,
    LoadedRulebook,
    PackageFile,
    PredicateOperator,
    ReadinessState,
    ReleaseScope,
    RulebookError,
    RulebookErrorCode,
    RulebookManifest,
    RuleDefinition,
    RulePredicate,
    SemanticTaskProfile,
    SourceDefinition,
)

ENGINE_VERSION = "1.0.0"
REQUIRED_DIRECTORIES = frozenset(
    {
        "attestations",
        "catalogues",
        "contracts",
        "evaluations",
        "expected",
        "fixtures",
        "profiles",
        "renderers",
        "rules",
        "scopes",
        "sources",
    }
)
FILE_ROLES = frozenset(
    {
        "ATTESTATION",
        "CATALOGUE",
        "CONTRACT",
        "DETERMINISTIC_FIXTURE",
        "EVALUATION",
        "EXPECTED_ARTIFACT",
        "PROFILE",
        "RENDERER",
        "RULES",
        "SCOPE_REGISTRY",
        "SEMANTIC_FIXTURE",
        "SOURCE_UNIVERSE",
    }
)
SOURCE_ROLES = frozenset(
    {"CONTROLLING", "CORROBORATING", "DISCOVERY", "EXCLUDED", "SPECIFICATION", "TRIGGER"}
)
GENERATIVE_TASKS = frozenset(item.value for item in GenerativeTask)
_MAX_FILE_BYTES = 2_000_000


def _object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _array(value: JsonValue | None, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _string(value: JsonValue | None, label: str) -> str:
    if type(value) is not str or not value:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _integer(value: JsonValue | None, label: str) -> int:
    if type(value) is not int:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _boolean(value: JsonValue | None, label: str) -> bool:
    if type(value) is not bool:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return value


def _strings(value: JsonValue | None, label: str) -> tuple[str, ...]:
    result = tuple(_string(item, label) for item in _array(value, label))
    if len(result) != len(set(result)):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)
    return result


def _exact_keys(document: Mapping[str, JsonValue], expected: frozenset[str], label: str) -> None:
    if frozenset(document) != expected:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, label)


def _read_json(path: Path) -> dict[str, JsonValue]:
    try:
        raw = path.read_bytes()
        return _object(parse_json_bytes(raw, max_bytes=_MAX_FILE_BYTES), path.name)
    except (OSError, ValueError) as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, path.name) from error


def _fingerprint_bytes(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _manifest_fingerprint(document: dict[str, JsonValue]) -> str:
    projection = dict(document)
    projection.pop("package_fingerprint", None)
    return _fingerprint_bytes(canonicalize(checked_json_value(projection)))


def _validate_path(relative: str) -> None:
    pure = PurePosixPath(relative)
    if (
        not relative
        or relative != unicodedata.normalize("NFC", relative)
        or relative.startswith("/")
        or "\\" in relative
        or "." in pure.parts
        or ".." in pure.parts
        or pure.as_posix() != relative
    ):
        raise RulebookError(RulebookErrorCode.PATH_INVALID, relative)


def _package_files(root: Path) -> tuple[str, ...]:
    members: list[str] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RulebookError(RulebookErrorCode.PATH_INVALID, path.name)
        if path.is_file():
            members.append(path.relative_to(root).as_posix())
    return tuple(sorted(members, key=lambda value: value.encode()))


def _parse_manifest(document: dict[str, JsonValue]) -> RulebookManifest:
    _exact_keys(
        document,
        frozenset(
            {
                "schema_id",
                "schema_version",
                "package_id",
                "package_version",
                "package_fingerprint",
                "jurisdiction",
                "environment",
                "material_family",
                "legal_desk_owner",
                "effective_cutoff",
                "predecessor",
                "contract_locks",
                "code_locks",
                "source_universe_fingerprint",
                "scope_readiness",
                "unresolved_policy_codes",
                "impact_declaration",
                "minimum_engine_version",
                "files",
            }
        ),
        "package.json",
    )
    if document["schema_id"] != "asklegal.executable-source-rulebook-package":
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "schema_id")
    file_entries: list[PackageFile] = []
    for raw_entry in _array(document["files"], "files"):
        entry = _object(raw_entry, "file")
        _exact_keys(
            entry,
            frozenset({"path", "role", "byte_size", "fingerprint"}),
            "file",
        )
        file_entries.append(
            PackageFile(
                _string(entry["path"], "path"),
                _string(entry["role"], "role"),
                _integer(entry["byte_size"], "byte_size"),
                _string(entry["fingerprint"], "fingerprint"),
            )
        )
    readiness: list[tuple[str, ReadinessState]] = []
    for raw_entry in _array(document["scope_readiness"], "scope_readiness"):
        entry = _object(raw_entry, "scope_readiness")
        _exact_keys(entry, frozenset({"scope_id", "state"}), "scope_readiness")
        try:
            readiness.append(
                (
                    _string(entry["scope_id"], "scope_id"),
                    ReadinessState(_string(entry["state"], "state")),
                )
            )
        except ValueError as error:
            raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "readiness") from error
    predecessor_value = document["predecessor"]
    if predecessor_value is not None and type(predecessor_value) is not str:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "predecessor")
    return RulebookManifest(
        package_id=_string(document["package_id"], "package_id"),
        package_version=_string(document["package_version"], "package_version"),
        package_fingerprint=_string(document["package_fingerprint"], "package_fingerprint"),
        jurisdiction=_string(document["jurisdiction"], "jurisdiction"),
        environment=_string(document["environment"], "environment"),
        material_family=_string(document["material_family"], "material_family"),
        legal_desk_owner=_string(document["legal_desk_owner"], "legal_desk_owner"),
        effective_cutoff=_string(document["effective_cutoff"], "effective_cutoff"),
        predecessor=predecessor_value,
        contract_locks=_strings(document["contract_locks"], "contract_locks"),
        code_locks=_strings(document["code_locks"], "code_locks"),
        source_universe_fingerprint=_string(
            document["source_universe_fingerprint"], "source_universe_fingerprint"
        ),
        scope_readiness=tuple(readiness),
        unresolved_policy_codes=_strings(
            document["unresolved_policy_codes"], "unresolved_policy_codes"
        ),
        impact_declaration=_string(document["impact_declaration"], "impact_declaration"),
        minimum_engine_version=_string(
            document["minimum_engine_version"], "minimum_engine_version"
        ),
        files=tuple(file_entries),
    )


def _validate_inventory(root: Path, manifest: RulebookManifest) -> None:
    actual = _package_files(root)
    actual_members = tuple(path for path in actual if path != "package.json")
    declared = tuple(entry.path for entry in manifest.files)
    if declared != tuple(sorted(declared, key=lambda value: value.encode())):
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "file order")
    if (
        actual.count("package.json") != 1
        or len(declared) != len(set(declared))
        or actual_members != declared
    ):
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH)
    if not REQUIRED_DIRECTORIES.issubset({path.name for path in root.iterdir() if path.is_dir()}):
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, "required directories")
    for entry in manifest.files:
        _validate_path(entry.path)
        if entry.role not in FILE_ROLES:
            raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, entry.role)
        raw = (root / entry.path).read_bytes()
        if entry.byte_size != len(raw) or entry.fingerprint != _fingerprint_bytes(raw):
            raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, entry.path)


def _parse_sources(root: Path, manifest: RulebookManifest) -> tuple[SourceDefinition, ...]:
    path = root / "sources/source-universe.json"
    if _fingerprint_bytes(path.read_bytes()) != manifest.source_universe_fingerprint:
        raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "source universe")
    document = _read_json(path)
    _exact_keys(document, frozenset({"complete", "sources"}), "source universe")
    if document["complete"] is not True:
        raise RulebookError(RulebookErrorCode.INCOMPLETE_SOURCE_INVENTORY)
    sources: list[SourceDefinition] = []
    for raw_source in _array(document["sources"], "sources"):
        source = _object(raw_source, "source")
        _exact_keys(
            source,
            frozenset(
                {
                    "source_id",
                    "role",
                    "endpoint_families",
                    "checking_tier",
                    "permitted_use",
                    "completeness_rule",
                    "outage_consequence",
                }
            ),
            "source",
        )
        role = _string(source["role"], "source role")
        if role not in SOURCE_ROLES:
            raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, role)
        permitted_use = _string(source["permitted_use"], "permitted_use")
        if (role == "EXCLUDED") != (permitted_use == "EXCLUDED"):
            raise RulebookError(RulebookErrorCode.INCOMPLETE_SOURCE_INVENTORY)
        sources.append(
            SourceDefinition(
                _string(source["source_id"], "source_id"),
                role,
                _strings(source["endpoint_families"], "endpoint_families"),
                _string(source["checking_tier"], "checking_tier"),
                permitted_use,
                _string(source["completeness_rule"], "completeness_rule"),
                _string(source["outage_consequence"], "outage_consequence"),
            )
        )
    if not sources or len({source.source_id for source in sources}) != len(sources):
        raise RulebookError(RulebookErrorCode.INCOMPLETE_SOURCE_INVENTORY)
    return tuple(sources)


def _parse_scopes(root: Path, sources: tuple[SourceDefinition, ...]) -> tuple[ReleaseScope, ...]:
    document = _read_json(root / "scopes/release-scopes.json")
    _exact_keys(document, frozenset({"complete_non_overlap", "scopes"}), "scopes")
    if document["complete_non_overlap"] is not True:
        raise RulebookError(RulebookErrorCode.OVERLAPPING_SCOPES)
    source_ids = {source.source_id for source in sources}
    scopes: list[ReleaseScope] = []
    owned: set[str] = set()
    for raw_scope in _array(document["scopes"], "scopes"):
        scope = _object(raw_scope, "scope")
        _exact_keys(
            scope,
            frozenset(
                {
                    "scope_id",
                    "ownership_keys",
                    "required_source_ids",
                    "zero_record_rule",
                    "withholding_rule",
                    "readiness",
                    "blocker_codes",
                }
            ),
            "scope",
        )
        ownership = _strings(scope["ownership_keys"], "ownership_keys")
        if not ownership or owned.intersection(ownership):
            raise RulebookError(RulebookErrorCode.OVERLAPPING_SCOPES)
        owned.update(ownership)
        required_sources = _strings(scope["required_source_ids"], "required_source_ids")
        if not required_sources or not set(required_sources).issubset(source_ids):
            raise RulebookError(RulebookErrorCode.INCOMPLETE_SOURCE_INVENTORY)
        try:
            readiness = ReadinessState(_string(scope["readiness"], "readiness"))
        except ValueError as error:
            raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "readiness") from error
        scopes.append(
            ReleaseScope(
                _string(scope["scope_id"], "scope_id"),
                ownership,
                required_sources,
                _string(scope["zero_record_rule"], "zero_record_rule"),
                _string(scope["withholding_rule"], "withholding_rule"),
                readiness,
                _strings(scope["blocker_codes"], "blocker_codes"),
            )
        )
    if not scopes or len({scope.scope_id for scope in scopes}) != len(scopes):
        raise RulebookError(RulebookErrorCode.OVERLAPPING_SCOPES)
    return tuple(scopes)


def _parse_rules(root: Path, scopes: tuple[ReleaseScope, ...]) -> tuple[RuleDefinition, ...]:
    document = _read_json(root / "rules/terminal-rules.json")
    _exact_keys(document, frozenset({"rules"}), "rules")
    scope_ids = {scope.scope_id for scope in scopes}
    rules: list[RuleDefinition] = []
    for raw_rule in _array(document["rules"], "rules"):
        rule = _object(raw_rule, "rule")
        _exact_keys(
            rule,
            frozenset(
                {
                    "rule_id",
                    "scope_id",
                    "predicates",
                    "evidence_roles",
                    "disposition",
                    "reason_code",
                    "failure_code",
                    "next_action",
                }
            ),
            "rule",
        )
        predicates: list[RulePredicate] = []
        for raw_predicate in _array(rule["predicates"], "predicates"):
            predicate = _object(raw_predicate, "predicate")
            _exact_keys(predicate, frozenset({"fact", "operator", "value"}), "predicate")
            try:
                operator = PredicateOperator(_string(predicate["operator"], "operator"))
            except ValueError as error:
                raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "operator") from error
            value = predicate["value"]
            if value is not None and type(value) is not str:
                raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "predicate value")
            if operator is PredicateOperator.EQUALS and value is None:
                raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "EQUALS value")
            predicates.append(
                RulePredicate(
                    _string(predicate["fact"], "fact"),
                    operator,
                    value,
                )
            )
        scope_id = _string(rule["scope_id"], "scope_id")
        if scope_id not in scope_ids:
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, scope_id)
        try:
            disposition = LegalDisposition(_string(rule["disposition"], "disposition"))
        except ValueError as error:
            raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, "disposition") from error
        failure = rule["failure_code"]
        if failure is not None and type(failure) is not str:
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "failure_code")
        rules.append(
            RuleDefinition(
                _string(rule["rule_id"], "rule_id"),
                scope_id,
                tuple(predicates),
                _strings(rule["evidence_roles"], "evidence_roles"),
                disposition,
                _string(rule["reason_code"], "reason_code"),
                failure,
                _string(rule["next_action"], "next_action"),
            )
        )
    if not rules or len({rule.rule_id for rule in rules}) != len(rules):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "rules")
    return tuple(rules)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "timestamp") from error
    if parsed.tzinfo is None:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "timestamp")
    return parsed.astimezone(UTC)


def _parse_profiles(
    root: Path,
    environment: str,
    now: str,
) -> tuple[SemanticTaskProfile, ...]:
    document = _read_json(root / "profiles/semantic-profiles.json")
    _exact_keys(document, frozenset({"profiles"}), "profiles")
    profiles: list[SemanticTaskProfile] = []
    for raw_profile in _array(document["profiles"], "profiles"):
        profile = _object(raw_profile, "profile")
        fields = frozenset(
            {
                "profile_id",
                "task",
                "provider",
                "resource_class",
                "geography_class",
                "deployment_name",
                "model_id",
                "model_version",
                "api_contract",
                "tokenizer",
                "prompt_fingerprint",
                "input_schema",
                "output_schema",
                "evidence_budget_bytes",
                "max_output_tokens",
                "content_filter_policy",
                "retry_policy",
                "data_handling_profile",
                "evaluator_id",
                "threshold_basis_points",
                "expires_at",
                "stateful_features",
                "allowed_environments",
            }
        )
        _exact_keys(profile, fields, "profile")
        task = _string(profile["task"], "task")
        if task not in GENERATIVE_TASKS:
            raise RulebookError(RulebookErrorCode.UNKNOWN_CODE, task)
        model_id = _string(profile["model_id"], "model_id")
        model_version = _string(profile["model_version"], "model_version")
        deployment = _string(profile["deployment_name"], "deployment_name")
        floating_tokens = (model_id, model_version, deployment)
        if any(token.lower() in {"latest", "current", "default"} for token in floating_tokens):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "floating model")
        allowed = _strings(profile["allowed_environments"], "allowed_environments")
        if environment not in allowed or _boolean(
            profile["stateful_features"], "stateful_features"
        ):
            raise RulebookError(RulebookErrorCode.ENVIRONMENT_MISUSE, "semantic profile")
        expires_at = _string(profile["expires_at"], "expires_at")
        if _timestamp(expires_at) <= _timestamp(now):
            raise RulebookError(RulebookErrorCode.EXPIRED_PROFILE)
        profiles.append(
            SemanticTaskProfile(
                _string(profile["profile_id"], "profile_id"),
                task,
                _string(profile["provider"], "provider"),
                _string(profile["resource_class"], "resource_class"),
                _string(profile["geography_class"], "geography_class"),
                deployment,
                model_id,
                model_version,
                _string(profile["api_contract"], "api_contract"),
                _string(profile["tokenizer"], "tokenizer"),
                _string(profile["prompt_fingerprint"], "prompt_fingerprint"),
                _string(profile["input_schema"], "input_schema"),
                _string(profile["output_schema"], "output_schema"),
                _integer(profile["evidence_budget_bytes"], "evidence_budget_bytes"),
                _integer(profile["max_output_tokens"], "max_output_tokens"),
                _string(profile["content_filter_policy"], "content_filter_policy"),
                _string(profile["retry_policy"], "retry_policy"),
                _string(profile["data_handling_profile"], "data_handling_profile"),
                _string(profile["evaluator_id"], "evaluator_id"),
                _integer(profile["threshold_basis_points"], "threshold_basis_points"),
                expires_at,
                stateful_features=False,
                allowed_environments=allowed,
            )
        )
    profile_ids = tuple(profile.profile_id for profile in profiles)
    profile_tasks = tuple(profile.task for profile in profiles)
    if len(profile_ids) != len(set(profile_ids)) or len(profile_tasks) != len(set(profile_tasks)):
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "duplicate profile")
    return tuple(profiles)


def _fixture_and_evaluation_ids(root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    fixture_ids: list[str] = []
    fixture_inputs: set[str] = set()
    for path in sorted((root / "fixtures").rglob("*.json")):
        document = _read_json(path)
        fixture_ids.append(_string(document.get("fixture_id"), "fixture_id"))
        input_fingerprint = document.get("input_fingerprint")
        if type(input_fingerprint) is str:
            fixture_inputs.add(input_fingerprint)
    evaluation_ids: list[str] = []
    reference_inputs: set[str] = set()
    for path in sorted((root / "evaluations").glob("*.json")):
        document = _read_json(path)
        evaluation_ids.append(_string(document.get("evaluation_id"), "evaluation_id"))
        refs = document.get("protected_reference_fingerprints")
        if refs is not None:
            reference_inputs.update(_strings(refs, "protected_reference_fingerprints"))
    if set(fixture_ids).intersection(evaluation_ids) or fixture_inputs.intersection(
        reference_inputs
    ):
        raise RulebookError(RulebookErrorCode.EVALUATION_LEAKAGE)
    return tuple(fixture_ids), tuple(evaluation_ids)


def load_rulebook_package(
    root: Path,
    *,
    environment: str,
    contract_set_fingerprint: str,
    now: str,
    engine_version: str = ENGINE_VERSION,
) -> LoadedRulebook:
    """Load and fully validate one exact package or reject it atomically."""
    if not root.is_dir():
        raise RulebookError(RulebookErrorCode.INVENTORY_MISMATCH, str(root))
    manifest_document = _read_json(root / "package.json")
    manifest = _parse_manifest(manifest_document)
    if manifest.package_fingerprint != _manifest_fingerprint(manifest_document):
        raise RulebookError(RulebookErrorCode.FINGERPRINT_DRIFT, "package manifest")
    if manifest.minimum_engine_version != engine_version:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "engine version")
    if contract_set_fingerprint not in manifest.contract_locks:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "contract set")
    if manifest.environment != environment:
        raise RulebookError(RulebookErrorCode.ENVIRONMENT_MISUSE)
    if manifest.jurisdiction == "ZZZ":
        if environment != "LOCAL_SYNTHETIC" or manifest.material_family != "TEST_LEGAL_MATERIAL":
            raise RulebookError(RulebookErrorCode.ENVIRONMENT_MISUSE, "reserved package")
    elif environment == "LOCAL_SYNTHETIC":
        raise RulebookError(RulebookErrorCode.ENVIRONMENT_MISUSE, "real jurisdiction")
    _validate_inventory(root, manifest)
    sources = _parse_sources(root, manifest)
    scopes = _parse_scopes(root, sources)
    declared_readiness = dict(manifest.scope_readiness)
    if declared_readiness != {scope.scope_id: scope.readiness for scope in scopes}:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "scope readiness")
    rules = _parse_rules(root, scopes)
    profiles = _parse_profiles(root, environment, now)
    fixture_ids, evaluation_ids = _fixture_and_evaluation_ids(root)
    attestations = tuple(
        _string(_read_json(path).get("attestation_id"), "attestation_id")
        for path in sorted((root / "attestations").glob("*.json"))
    )
    if not fixture_ids or not evaluation_ids or not attestations:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "proof inventory")
    return LoadedRulebook(
        manifest,
        sources,
        scopes,
        rules,
        profiles,
        fixture_ids,
        evaluation_ids,
        attestations,
    )
