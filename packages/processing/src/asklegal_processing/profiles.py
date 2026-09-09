"""Immutable, provider-disabled semantic profile contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Never, Protocol
from weakref import ref

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_legal_desks import SEMANTIC_TASK_PAIRS, GenerativeTask, SemanticTaskProfile

from .model import ProcessingError

_MAX_PROFILE_BYTES = 2_000_000
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_INTEGER_VERSION = re.compile(r"^(0|[1-9][0-9]*)$")
_DATED_VERSION = re.compile(r"^(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])$")
_WHOLE_SECOND_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_PLACEHOLDERS = frozenset({"latest", "default", "current", "auto"})
_SECRET_VALUE = re.compile(
    r"(?:^|[^a-z0-9])(?:sk-(?:proj|svcacct)-[a-z0-9_-]{8,}|sk-[a-z0-9]{8,}|pcsk_[a-z0-9_-]{8,})(?:$|[^a-z0-9])"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?:^|[^a-z0-9])(?:api[_-]?key|access[_-]?token|bearer|secret|password|connection[_-]?string)"
    r"\s*(?:[:=]|\s)\s*[^\s]+"
)
_SET_KEYS = frozenset(
    {
        "billing_denominator_tokens",
        "billing_rounding_rule",
        "budget_profiles",
        "cost_limit_microunits",
        "environment",
        "expires_at",
        "fingerprint",
        "immutable",
        "profiles",
        "quota_limit_tokens",
        "request_quota",
        "retry_profile",
        "revision",
        "schema_id",
        "schema_version",
        "tokenizer_specifications",
    }
)
_PROFILE_KEYS = frozenset(
    {
        "allowed_environments",
        "api_contract",
        "content_filter_policy",
        "data_handling_profile",
        "deployment_name",
        "evaluator_id",
        "evidence_budget_bytes",
        "expires_at",
        "geography_class",
        "input_schema",
        "max_output_tokens",
        "model_id",
        "model_version",
        "output_schema",
        "profile_id",
        "prompt_fingerprint",
        "provider",
        "resource_class",
        "retry_policy",
        "stateful_features",
        "task",
        "threshold_basis_points",
        "tokenizer",
    }
)
_RETRY_KEYS = frozenset({"attempt_ceiling", "backoff_seconds", "timeout_seconds"})
_TOKENIZER_KEYS = frozenset(
    {
        "distribution_fingerprint",
        "distribution_name",
        "distribution_version",
        "encoding_resource_fingerprint",
        "tokenizer_id",
    }
)
_BUDGET_KEYS = frozenset(
    {
        "input_cost_microunits_per_million",
        "max_input_tokens",
        "output_cost_microunits_per_million",
        "profile_id",
    }
)
_ATTEMPT_CEILING = 3
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_BILLING_DENOMINATOR_TOKENS = 1_000_000
_BILLING_ROUNDING_RULE = "PER_REQUEST_PER_DIRECTION_CEILING"

type _SemanticCatalogues = tuple[
    tuple[SemanticTaskProfile, ...],
    tuple[TokenizerSpecification, ...],
    tuple[SemanticBudgetProfile, ...],
]
type _BillingContext = tuple[int, str, str]


@dataclass(frozen=True, slots=True)
class _IssuanceRecord:
    fingerprint: str
    projection: bytes


class ProfileError(ProcessingError):
    """One closed semantic provider-profile failure."""


class ProfileReader(Protocol):
    """Reader bound to one immutable workflow-profile reference."""

    @property
    def reference(self) -> ImmutableReference:
        """Return the sole authoritative immutable reference exactly once."""
        ...

    def read_exact(self, reference: ImmutableReference) -> bytes:
        """Read the exact immutable bytes for one profile reference."""
        ...


@dataclass(frozen=True, slots=True)
class ProviderRetryProfile:
    """Bounded retry values, with no implicit provider default."""

    attempt_ceiling: int
    timeout_seconds: int
    backoff_seconds: tuple[int, ...]

    def __post_init__(self) -> None:
        """Keep direct construction as strict as decoded construction."""
        if not _retry_profile_is_admitted(self):
            _fail("PROFILE_RETRY_INVALID")


@dataclass(frozen=True, slots=True)
class TokenizerSpecification:
    """Exact local distribution and disconnected encoding-resource identity."""

    tokenizer_id: str
    distribution_name: str
    distribution_version: str
    distribution_fingerprint: str
    encoding_resource_fingerprint: str

    def __post_init__(self) -> None:
        """Reject aliases, placeholders, and malformed exact identities."""
        if not _tokenizer_specification_is_admitted(self):
            _fail("TOKENIZER_SPECIFICATION_INVALID")


@dataclass(frozen=True, slots=True)
class SemanticBudgetProfile:
    """Exact per-semantic-profile input ceiling and synthetic price rates."""

    profile_id: str
    max_input_tokens: int
    input_cost_microunits_per_million: int
    output_cost_microunits_per_million: int

    def __post_init__(self) -> None:
        """Keep every direct budget fact inside the canonical integer domain."""
        if not _semantic_budget_profile_is_admitted(self):
            _fail("BUDGET_PROFILE_INVALID")


@dataclass(frozen=True, slots=True, weakref_slot=True, init=False, eq=False)
class SemanticProfileSet:
    """All exact semantic task profiles valid under one immutable document."""

    revision: str
    profiles: tuple[SemanticTaskProfile, ...]
    tokenizer_specifications: tuple[TokenizerSpecification, ...]
    budget_profiles: tuple[SemanticBudgetProfile, ...]
    retry_profile: ProviderRetryProfile
    request_quota: int
    quota_limit_tokens: int
    cost_limit_microunits: int
    billing_denominator_tokens: int
    billing_rounding_rule: str
    environment: str
    fingerprint: str
    _witness: object | None = field(default=None, repr=False, compare=False)

    def validate(self) -> None:
        """Reject invalid direct or reconstructed profile-set values."""
        if (
            type(self.revision) is not str
            or _VERSION.fullmatch(self.revision) is None
            or type(self.profiles) is not tuple
            or not self.profiles
            or any(type(profile) is not SemanticTaskProfile for profile in self.profiles)
            or len(self.profiles) != len(GenerativeTask)
            or any(not _semantic_profile_is_admitted(profile) for profile in self.profiles)
            or len({profile.profile_id for profile in self.profiles}) != len(self.profiles)
            or {profile.task for profile in self.profiles}
            != {task.value for task in GenerativeTask}
            or len({profile.expires_at for profile in self.profiles}) != 1
            or type(self.tokenizer_specifications) is not tuple
            or not self.tokenizer_specifications
            or any(
                type(specification) is not TokenizerSpecification
                for specification in self.tokenizer_specifications
            )
            or any(
                not _tokenizer_specification_is_admitted(specification)
                for specification in self.tokenizer_specifications
            )
            or len({item.tokenizer_id for item in self.tokenizer_specifications})
            != len(self.tokenizer_specifications)
            or {profile.tokenizer for profile in self.profiles}
            != {item.tokenizer_id for item in self.tokenizer_specifications}
            or type(self.budget_profiles) is not tuple
            or any(type(item) is not SemanticBudgetProfile for item in self.budget_profiles)
            or any(not _semantic_budget_profile_is_admitted(item) for item in self.budget_profiles)
            or len({item.profile_id for item in self.budget_profiles}) != len(self.budget_profiles)
            or {profile.profile_id for profile in self.profiles}
            != {item.profile_id for item in self.budget_profiles}
            or type(self.retry_profile) is not ProviderRetryProfile
            or not _retry_profile_is_admitted(self.retry_profile)
            or not _safe_positive_integer(self.request_quota)
            or not _safe_positive_integer(self.quota_limit_tokens)
            or not _safe_nonnegative_integer(self.cost_limit_microunits)
            or not _billing_contract_is_admitted(
                self.billing_denominator_tokens,
                self.billing_rounding_rule,
            )
            or not _safe_direct_text(self.environment)
            or any(
                self.environment not in profile.allowed_environments for profile in self.profiles
            )
            or type(self.fingerprint) is not str
        ):
            _fail("PROFILE_SET_INVALID")
        computed = _semantic_set_fingerprint(
            self.revision,
            (self.profiles, self.tokenizer_specifications, self.budget_profiles),
            self.retry_profile,
            (self.request_quota, self.quota_limit_tokens, self.cost_limit_microunits),
            (
                self.billing_denominator_tokens,
                self.billing_rounding_rule,
                self.environment,
            ),
        )
        if _FINGERPRINT.fullmatch(self.fingerprint) is None or self.fingerprint != computed:
            _fail("PROFILE_SET_INVALID")

    def __reduce__(self) -> Never:
        """Immutable-reader authority is process-local and non-transferable."""
        _assert_issued(self)
        message = "PROFILE_NONTRANSFERABLE"
        raise TypeError(message)


_ISSUED: dict[int, tuple[ref[SemanticProfileSet], _IssuanceRecord]] = {}


def _fail(code: str) -> Never:
    raise ProfileError(code)


def _model_version_is_exact(value: str) -> bool:
    """Accept the exact version grammars used by Azure model deployments."""
    return any(
        pattern.fullmatch(value) is not None
        for pattern in (_VERSION, _INTEGER_VERSION, _DATED_VERSION)
    )


def _object(value: JsonValue | None, code: str) -> dict[str, JsonValue]:
    if type(value) is not dict:
        _fail(code)
    return value


def _keys(value: dict[str, JsonValue], expected: frozenset[str]) -> None:
    if frozenset(value) != expected:
        _fail("PROFILE_KEYS_INVALID")


def _text(value: JsonValue | None, code: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        _fail(code)
    return value


def _positive(value: JsonValue | None, code: str) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_SAFE_INTEGER:
        _fail(code)
    return value


def _nonnegative(value: JsonValue | None, code: str) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_SAFE_INTEGER:
        _fail(code)
    return value


def _safe_positive_integer(value: object) -> bool:
    return type(value) is int and 1 <= value <= _MAX_SAFE_INTEGER


def _safe_nonnegative_integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= _MAX_SAFE_INTEGER


def _billing_contract_is_admitted(denominator: object, rounding_rule: object) -> bool:
    """Require exact builtins before constant comparison or billing arithmetic."""
    return (
        type(denominator) is int
        and denominator == _BILLING_DENOMINATOR_TOKENS
        and type(rounding_rule) is str
        and rounding_rule == _BILLING_ROUNDING_RULE
    )


def _retry_profile_is_admitted(value: ProviderRetryProfile) -> bool:
    """Replay every retry invariant for direct and nested reconstruction."""
    return (
        type(value.attempt_ceiling) is int
        and 1 <= value.attempt_ceiling <= _ATTEMPT_CEILING
        and _safe_positive_integer(value.timeout_seconds)
        and type(value.backoff_seconds) is tuple
        and all(_safe_nonnegative_integer(item) for item in value.backoff_seconds)
        and len(value.backoff_seconds) == value.attempt_ceiling - 1
    )


def _fingerprint(value: JsonValue | None, code: str = "PROFILE_FINGERPRINT_MISMATCH") -> str:
    result = _text(value, code)
    if _FINGERPRINT.fullmatch(result) is None:
        _fail(code)
    return result


def _timestamp(value: JsonValue | None, code: str) -> tuple[str, datetime]:
    result = _text(value, code)
    parsed = _whole_second_utc(result)
    if parsed is None:
        _fail(code)
    return result, parsed


def _whole_second_utc(value: object) -> datetime | None:
    """Parse precisely the one UTC timestamp grammar accepted by this contract."""
    if type(value) is not str or _WHOLE_SECOND_UTC.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        return None
    if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value:
        return None
    return parsed


def _environment_list(value: JsonValue | None) -> tuple[str, ...]:
    if type(value) is not list:
        _fail("PROFILE_ENVIRONMENT_INVALID")
    items = tuple(
        _no_placeholder(_text(item, "PROFILE_ENVIRONMENT_INVALID"), "PROFILE_PLACEHOLDER_FORBIDDEN")
        for item in value
    )
    if not items or len(set(items)) != len(items) or items != tuple(sorted(items)):
        _fail("PROFILE_ENVIRONMENT_INVALID")
    return items


def _no_placeholder(value: str, code: str) -> str:
    if any(token in value.casefold() for token in _PLACEHOLDERS):
        _fail(code)
    return value


def _screen(value: JsonValue) -> None:
    """Reject placeholder and credential-like content at every decoded leaf."""
    if type(value) is str:
        lowered = value.casefold()
        if _SECRET_VALUE.search(lowered) or _SECRET_ASSIGNMENT.search(lowered):
            _fail("PROFILE_SECRET_FORBIDDEN")
    elif type(value) is list:
        for item in value:
            _screen(item)
    elif type(value) is dict:
        for item in value.values():
            _screen(item)


def _safe_direct_text(value: object) -> bool:
    """Apply the closed string boundary to direct dataclass construction."""
    if type(value) is not str or not value or value.strip() != value:
        return False
    lowered = value.casefold()
    return not any(token in lowered for token in _PLACEHOLDERS) and not (
        _SECRET_VALUE.search(lowered) or _SECRET_ASSIGNMENT.search(lowered)
    )


def _tokenizer_specification_is_admitted(value: TokenizerSpecification) -> bool:
    """Replay every exact tokenizer identity invariant without reconstructing it."""
    return (
        all(
            _safe_direct_text(item)
            for item in (
                value.tokenizer_id,
                value.distribution_name,
                value.distribution_version,
                value.distribution_fingerprint,
                value.encoding_resource_fingerprint,
            )
        )
        and _VERSION.fullmatch(value.distribution_version) is not None
        and _FINGERPRINT.fullmatch(value.distribution_fingerprint) is not None
        and _FINGERPRINT.fullmatch(value.encoding_resource_fingerprint) is not None
    )


def _semantic_budget_profile_is_admitted(value: SemanticBudgetProfile) -> bool:
    """Replay every immutable budget invariant without reconstructing it."""
    return (
        _safe_direct_text(value.profile_id)
        and _safe_positive_integer(value.max_input_tokens)
        and _safe_nonnegative_integer(value.input_cost_microunits_per_million)
        and _safe_nonnegative_integer(value.output_cost_microunits_per_million)
    )


def _future_timestamp(value: object) -> bool:
    """Keep direct reconstruction subject to the loader expiry boundary."""
    parsed = _whole_second_utc(value)
    return parsed is not None and parsed > datetime.now(UTC)


def _semantic_profile_is_admitted(profile: SemanticTaskProfile) -> bool:
    """Replay loader-level stateless profile checks for direct construction."""
    if type(profile.task) is not str or type(profile.provider) is not str:
        return False
    return not (
        profile.provider != "AZURE_OPENAI"
        or profile.task not in {task.value for task in GenerativeTask}
        or not all(
            _safe_direct_text(value)
            for value in (
                profile.profile_id,
                profile.resource_class,
                profile.geography_class,
                profile.deployment_name,
                profile.model_id,
                profile.model_version,
                profile.api_contract,
                profile.tokenizer,
                profile.prompt_fingerprint,
                profile.input_schema,
                profile.output_schema,
                profile.content_filter_policy,
                profile.retry_policy,
                profile.data_handling_profile,
                profile.evaluator_id,
            )
        )
        or not _model_version_is_exact(profile.model_version)
        or _FINGERPRINT.fullmatch(profile.prompt_fingerprint) is None
        or not _safe_positive_integer(profile.evidence_budget_bytes)
        or not _safe_positive_integer(profile.max_output_tokens)
        or not _safe_nonnegative_integer(profile.threshold_basis_points)
        or not _future_timestamp(profile.expires_at)
        or profile.stateful_features is not False
        or type(profile.allowed_environments) is not tuple
        or not profile.allowed_environments
        or any(not _safe_direct_text(item) for item in profile.allowed_environments)
        or len(set(profile.allowed_environments)) != len(profile.allowed_environments)
        or profile.allowed_environments != tuple(sorted(profile.allowed_environments))
    )


def _semantic_profile_projection(profile: SemanticTaskProfile) -> dict[str, object]:
    """Return every influential public profile field in canonical JSON shape."""
    return {
        "allowed_environments": list(profile.allowed_environments),
        "api_contract": profile.api_contract,
        "content_filter_policy": profile.content_filter_policy,
        "data_handling_profile": profile.data_handling_profile,
        "deployment_name": profile.deployment_name,
        "evaluator_id": profile.evaluator_id,
        "evidence_budget_bytes": profile.evidence_budget_bytes,
        "expires_at": profile.expires_at,
        "geography_class": profile.geography_class,
        "input_schema": profile.input_schema,
        "max_output_tokens": profile.max_output_tokens,
        "model_id": profile.model_id,
        "model_version": profile.model_version,
        "output_schema": profile.output_schema,
        "profile_id": profile.profile_id,
        "prompt_fingerprint": profile.prompt_fingerprint,
        "provider": profile.provider,
        "resource_class": profile.resource_class,
        "retry_policy": profile.retry_policy,
        "stateful_features": profile.stateful_features,
        "task": profile.task,
        "threshold_basis_points": profile.threshold_basis_points,
        "tokenizer": profile.tokenizer,
    }


def _tokenizer_projection(specification: TokenizerSpecification) -> dict[str, object]:
    return {
        "distribution_fingerprint": specification.distribution_fingerprint,
        "distribution_name": specification.distribution_name,
        "distribution_version": specification.distribution_version,
        "encoding_resource_fingerprint": specification.encoding_resource_fingerprint,
        "tokenizer_id": specification.tokenizer_id,
    }


def _budget_projection(profile: SemanticBudgetProfile) -> dict[str, object]:
    return {
        "input_cost_microunits_per_million": profile.input_cost_microunits_per_million,
        "max_input_tokens": profile.max_input_tokens,
        "output_cost_microunits_per_million": profile.output_cost_microunits_per_million,
        "profile_id": profile.profile_id,
    }


def _semantic_set_fingerprint(
    revision: str,
    catalogues: _SemanticCatalogues,
    retry_profile: ProviderRetryProfile,
    limits: tuple[int, int, int],
    context: _BillingContext,
) -> str:
    """Fingerprint the complete durable public profile-set projection."""
    projection = _semantic_projection_bytes(
        revision,
        catalogues,
        retry_profile,
        limits,
        context,
    )
    return f"sha256:{sha256(projection).hexdigest()}"


def _semantic_projection_bytes(
    revision: str,
    catalogues: _SemanticCatalogues,
    retry_profile: ProviderRetryProfile,
    limits: tuple[int, int, int],
    context: _BillingContext,
) -> bytes:
    """Canonical immutable public projection used for issuance and replay."""
    profiles, tokenizer_specifications, budget_profiles = catalogues
    denominator, rounding, environment = context
    projection = {
        "billing_denominator_tokens": denominator,
        "billing_rounding_rule": rounding,
        "budget_profiles": [_budget_projection(profile) for profile in budget_profiles],
        "cost_limit_microunits": limits[2],
        "environment": environment,
        "profiles": [_semantic_profile_projection(profile) for profile in profiles],
        "quota_limit_tokens": limits[1],
        "request_quota": limits[0],
        "retry_profile": {
            "attempt_ceiling": retry_profile.attempt_ceiling,
            "backoff_seconds": list(retry_profile.backoff_seconds),
            "timeout_seconds": retry_profile.timeout_seconds,
        },
        "revision": revision,
        "tokenizer_specifications": [
            _tokenizer_projection(specification) for specification in tokenizer_specifications
        ],
        "type": "asklegal.semantic-profile-set.public.v1",
    }
    return canonicalize(checked_json_value(projection))


def _assert_issued(value: SemanticProfileSet) -> None:
    """Deeply replay facts before accepting this process-local issued identity."""
    entry = _ISSUED.pop(id(value), None)
    if entry is None or entry[0]() is not value:
        _fail("PROFILE_SET_INVALID")
    if not _billing_contract_is_admitted(
        value.billing_denominator_tokens,
        value.billing_rounding_rule,
    ):
        _fail("PROFILE_SET_INVALID")
    try:
        projection = _semantic_projection_bytes(
            value.revision,
            (value.profiles, value.tokenizer_specifications, value.budget_profiles),
            value.retry_profile,
            (value.request_quota, value.quota_limit_tokens, value.cost_limit_microunits),
            (
                value.billing_denominator_tokens,
                value.billing_rounding_rule,
                value.environment,
            ),
        )
    except Exception as error:
        message = "PROFILE_SET_INVALID"
        raise ProfileError(message) from error
    record = entry[1]
    if record.fingerprint != value.fingerprint or record.projection != projection:
        _fail("PROFILE_SET_INVALID")
    if entry[0]() is not value or id(value) in _ISSUED:
        _fail("PROFILE_SET_INVALID")
    _ISSUED[id(value)] = entry


def validate_semantic_profile_set_authority(value: SemanticProfileSet) -> None:
    """Revalidate the exact process-local immutable profile authority."""
    _assert_issued(value)


def _reader_exact(reader: ProfileReader, original: tuple[ReferenceType, str, str]) -> bytes:
    """Read a disposable reference while normalizing ordinary reader failures."""
    try:
        result = reader.read_exact(ImmutableReference(*original))
    except Exception as error:
        message = "PROFILE_READ_FAILED"
        raise ProfileError(message) from error
    if type(result) is not bytes:
        _fail("PROFILE_READ_INVALID")
    return bytes(memoryview(result))


def _immutable_raw(reader: ProfileReader) -> bytes:
    try:
        candidate = reader.reference
    except Exception as error:
        message = "PROFILE_READ_FAILED"
        raise ProfileError(message) from error
    if type(candidate) is not ImmutableReference:
        _fail("PROFILE_REFERENCE_INVALID")
    original: tuple[ReferenceType, str, str] = (
        candidate.ref_type,
        candidate.ref_id,
        candidate.fingerprint,
    )
    try:
        reference = ImmutableReference(*original)
    except Exception as error:
        message = "PROFILE_REFERENCE_INVALID"
        raise ProfileError(message) from error
    if reference.ref_type is not ReferenceType.WORKFLOW_PROFILE:
        _fail("PROFILE_REFERENCE_INVALID")
    raw = _reader_exact(reader, original)
    if (candidate.ref_type, candidate.ref_id, candidate.fingerprint) != original:
        _fail("PROFILE_REFERENCE_MUTATED")
    if not raw or f"sha256:{sha256(raw).hexdigest()}" != reference.fingerprint:
        _fail("PROFILE_FINGERPRINT_MISMATCH")
    second = _reader_exact(reader, original)
    if (candidate.ref_type, candidate.ref_id, candidate.fingerprint) != original:
        _fail("PROFILE_REFERENCE_MUTATED")
    if second != raw:
        _fail("PROFILE_READBACK_MISMATCH")
    return raw


def _parse_profile(value: JsonValue, environment: str, expires_at: str) -> SemanticTaskProfile:
    profile = _object(value, "PROFILE_DOCUMENT_INVALID")
    _keys(profile, _PROFILE_KEYS)
    task = _text(profile.get("task"), "SEMANTIC_TASK_INVALID")
    try:
        GenerativeTask(task)
    except ValueError:
        _fail("SEMANTIC_TASK_INVALID")
    model_version = _no_placeholder(
        _text(profile.get("model_version"), "MODEL_VERSION_NOT_EXACT"), "MODEL_VERSION_NOT_EXACT"
    )
    if not _model_version_is_exact(model_version):
        _fail("MODEL_VERSION_NOT_EXACT")
    stateful = profile.get("stateful_features")
    if type(stateful) is not bool:
        _fail("PROFILE_DOCUMENT_INVALID")
    if stateful:
        _fail("STATEFUL_PROVIDER_FEATURE_FORBIDDEN")
    environments = _environment_list(profile.get("allowed_environments"))
    if environment not in environments:
        _fail("PROFILE_ENVIRONMENT_MISMATCH")
    profile_expiry, profile_expiry_at = _timestamp(
        profile.get("expires_at"), "PROFILE_EXPIRY_INVALID"
    )
    if profile_expiry != expires_at:
        _fail("PROFILE_EXPIRY_MISMATCH")
    if profile_expiry_at <= datetime.now(UTC):
        _fail("PROFILE_EXPIRED")
    provider = _text(profile.get("provider"), "PROVIDER_INVALID")
    if provider != "AZURE_OPENAI":
        _fail("PROVIDER_INVALID")
    strings = {
        key: _no_placeholder(
            _text(profile.get(key), "PROFILE_DOCUMENT_INVALID"), "PROFILE_PLACEHOLDER_FORBIDDEN"
        )
        for key in (
            "api_contract",
            "content_filter_policy",
            "data_handling_profile",
            "deployment_name",
            "evaluator_id",
            "geography_class",
            "input_schema",
            "model_id",
            "output_schema",
            "profile_id",
            "resource_class",
            "retry_policy",
            "tokenizer",
        )
    }
    _no_placeholder(strings["deployment_name"], "DEPLOYMENT_NOT_EXACT")
    _no_placeholder(strings["model_id"], "MODEL_ID_NOT_EXACT")
    return SemanticTaskProfile(
        strings["profile_id"],
        task,
        provider,
        strings["resource_class"],
        strings["geography_class"],
        strings["deployment_name"],
        strings["model_id"],
        model_version,
        strings["api_contract"],
        strings["tokenizer"],
        _fingerprint(profile.get("prompt_fingerprint")),
        strings["input_schema"],
        strings["output_schema"],
        _positive(profile.get("evidence_budget_bytes"), "PROFILE_DOCUMENT_INVALID"),
        _positive(profile.get("max_output_tokens"), "PROFILE_DOCUMENT_INVALID"),
        strings["content_filter_policy"],
        strings["retry_policy"],
        strings["data_handling_profile"],
        strings["evaluator_id"],
        _nonnegative(profile.get("threshold_basis_points"), "PROFILE_DOCUMENT_INVALID"),
        expires_at=profile_expiry,
        stateful_features=False,
        allowed_environments=environments,
    )


def _document(raw: bytes) -> tuple[dict[str, JsonValue], str, str, str, str]:
    """Decode and authenticate the set-level immutable profile document."""
    try:
        parsed = parse_json_bytes(raw, max_bytes=_MAX_PROFILE_BYTES)
    except ContractViolation as error:
        message = "PROFILE_DOCUMENT_INVALID"
        raise ProfileError(message) from error
    if raw != canonicalize(checked_json_value(parsed)):
        _fail("PROFILE_CANONICAL_BYTES_REQUIRED")
    document = _object(parsed, "PROFILE_DOCUMENT_INVALID")
    _screen(document)
    _keys(document, _SET_KEYS)
    if (
        document.get("schema_id") != "asklegal.hk-v1-semantic-profile-set"
        or document.get("schema_version") != "1.1.0"
        or document.get("immutable") is not True
    ):
        _fail("PROFILE_DOCUMENT_INVALID")
    revision = _text(document.get("revision"), "PROFILE_DOCUMENT_INVALID")
    if _VERSION.fullmatch(revision) is None:
        _fail("PROFILE_DOCUMENT_INVALID")
    environment = _no_placeholder(
        _text(document.get("environment"), "PROFILE_ENVIRONMENT_INVALID"),
        "PROFILE_PLACEHOLDER_FORBIDDEN",
    )
    expires_at, expires_at_value = _timestamp(document.get("expires_at"), "PROFILE_EXPIRY_INVALID")
    if expires_at_value <= datetime.now(UTC):
        _fail("PROFILE_EXPIRED")
    projection = dict(document)
    supplied_fingerprint = _fingerprint(projection.pop("fingerprint", None))
    if (
        supplied_fingerprint
        != f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    ):
        _fail("PROFILE_FINGERPRINT_MISMATCH")
    return document, revision, environment, expires_at, supplied_fingerprint


def _profiles(
    document: dict[str, JsonValue], environment: str, expires_at: str
) -> tuple[SemanticTaskProfile, ...]:
    """Build the closed, unique task-profile tuple."""
    profiles_value = document.get("profiles")
    if type(profiles_value) is not list or not profiles_value:
        _fail("PROFILE_DOCUMENT_INVALID")
    profiles = tuple(_parse_profile(value, environment, expires_at) for value in profiles_value)
    if len({profile.profile_id for profile in profiles}) != len(profiles) or len(
        {profile.task for profile in profiles}
    ) != len(profiles):
        _fail("PROFILE_DOCUMENT_INVALID")
    tasks = frozenset(GenerativeTask(profile.task) for profile in profiles)
    if tasks != frozenset(GenerativeTask) or any(
        not frozenset(pair) <= tasks for pair in SEMANTIC_TASK_PAIRS
    ):
        _fail("SEMANTIC_TASK_CATALOGUE_INCOMPLETE")
    return profiles


def _tokenizer_specifications(
    document: dict[str, JsonValue], profiles: tuple[SemanticTaskProfile, ...]
) -> tuple[TokenizerSpecification, ...]:
    """Decode one exact, closed tokenizer specification per used tokenizer ID."""
    raw = document.get("tokenizer_specifications")
    if type(raw) is not list or not raw:
        _fail("TOKENIZER_PROFILE_MAPPING_INVALID")
    values: list[TokenizerSpecification] = []
    for item in raw:
        specification = _object(item, "TOKENIZER_SPECIFICATION_INVALID")
        _keys(specification, _TOKENIZER_KEYS)
        distribution_version = _text(
            specification.get("distribution_version"), "TOKENIZER_SPECIFICATION_INVALID"
        )
        if _VERSION.fullmatch(distribution_version) is None:
            _fail("TOKENIZER_SPECIFICATION_INVALID")
        values.append(
            TokenizerSpecification(
                _no_placeholder(
                    _text(specification.get("tokenizer_id"), "TOKENIZER_SPECIFICATION_INVALID"),
                    "PROFILE_PLACEHOLDER_FORBIDDEN",
                ),
                _no_placeholder(
                    _text(
                        specification.get("distribution_name"),
                        "TOKENIZER_SPECIFICATION_INVALID",
                    ),
                    "PROFILE_PLACEHOLDER_FORBIDDEN",
                ),
                distribution_version,
                _fingerprint(
                    specification.get("distribution_fingerprint"),
                    "TOKENIZER_SPECIFICATION_INVALID",
                ),
                _fingerprint(
                    specification.get("encoding_resource_fingerprint"),
                    "TOKENIZER_SPECIFICATION_INVALID",
                ),
            )
        )
    result = tuple(values)
    identifiers = tuple(item.tokenizer_id for item in result)
    if len(set(identifiers)) != len(identifiers) or set(identifiers) != {
        profile.tokenizer for profile in profiles
    }:
        _fail("TOKENIZER_PROFILE_MAPPING_INVALID")
    return result


def _budget_profiles(
    document: dict[str, JsonValue], profiles: tuple[SemanticTaskProfile, ...]
) -> tuple[SemanticBudgetProfile, ...]:
    """Decode exactly one immutable input ceiling and price map per profile."""
    raw = document.get("budget_profiles")
    if type(raw) is not list or not raw:
        _fail("BUDGET_PROFILE_MAPPING_INVALID")
    values: list[SemanticBudgetProfile] = []
    for item in raw:
        budget = _object(item, "BUDGET_PROFILE_INVALID")
        _keys(budget, _BUDGET_KEYS)
        values.append(
            SemanticBudgetProfile(
                _no_placeholder(
                    _text(budget.get("profile_id"), "BUDGET_PROFILE_INVALID"),
                    "PROFILE_PLACEHOLDER_FORBIDDEN",
                ),
                _positive(budget.get("max_input_tokens"), "BUDGET_PROFILE_INVALID"),
                _nonnegative(
                    budget.get("input_cost_microunits_per_million"),
                    "BUDGET_PROFILE_INVALID",
                ),
                _nonnegative(
                    budget.get("output_cost_microunits_per_million"),
                    "BUDGET_PROFILE_INVALID",
                ),
            )
        )
    result = tuple(values)
    identifiers = tuple(item.profile_id for item in result)
    if len(set(identifiers)) != len(identifiers) or set(identifiers) != {
        profile.profile_id for profile in profiles
    }:
        _fail("BUDGET_PROFILE_MAPPING_INVALID")
    return result


def _retry_profile(document: dict[str, JsonValue]) -> ProviderRetryProfile:
    """Build the exact retry ceiling, timeout, and fixed backoff sequence."""
    retry = _object(document.get("retry_profile"), "PROFILE_DOCUMENT_INVALID")
    _keys(retry, _RETRY_KEYS)
    attempts = _positive(retry.get("attempt_ceiling"), "PROFILE_DOCUMENT_INVALID")
    timeout = _positive(retry.get("timeout_seconds"), "PROFILE_DOCUMENT_INVALID")
    backoff_value = retry.get("backoff_seconds")
    if type(backoff_value) is not list:
        _fail("PROFILE_DOCUMENT_INVALID")
    backoff = tuple(_nonnegative(item, "PROFILE_DOCUMENT_INVALID") for item in backoff_value)
    if len(backoff) != attempts - 1:
        _fail("PROFILE_DOCUMENT_INVALID")
    return ProviderRetryProfile(attempts, timeout, backoff)


def load_semantic_profile_set(reader: ProfileReader) -> SemanticProfileSet:
    """Load one exact canonical profile set and close reader TOCTOU races."""
    document, revision, environment, expires_at, _ = _document(_immutable_raw(reader))
    profiles = _profiles(document, environment, expires_at)
    tokenizer_specifications = _tokenizer_specifications(document, profiles)
    budget_profiles = _budget_profiles(document, profiles)
    retry = _retry_profile(document)
    request_quota = _positive(document.get("request_quota"), "PROFILE_DOCUMENT_INVALID")
    quota = _positive(document.get("quota_limit_tokens"), "PROFILE_DOCUMENT_INVALID")
    cost = _nonnegative(document.get("cost_limit_microunits"), "PROFILE_DOCUMENT_INVALID")
    denominator = _positive(document.get("billing_denominator_tokens"), "BILLING_CONTRACT_INVALID")
    rounding = _text(document.get("billing_rounding_rule"), "BILLING_CONTRACT_INVALID")
    if denominator != _BILLING_DENOMINATOR_TOKENS or rounding != _BILLING_ROUNDING_RULE:
        _fail("BILLING_CONTRACT_INVALID")
    fingerprint = _semantic_set_fingerprint(
        revision,
        (profiles, tokenizer_specifications, budget_profiles),
        retry,
        (request_quota, quota, cost),
        (denominator, rounding, environment),
    )
    value = object.__new__(SemanticProfileSet)
    for name, item in (
        ("revision", revision),
        ("profiles", profiles),
        ("tokenizer_specifications", tokenizer_specifications),
        ("budget_profiles", budget_profiles),
        ("retry_profile", retry),
        ("request_quota", request_quota),
        ("quota_limit_tokens", quota),
        ("cost_limit_microunits", cost),
        ("billing_denominator_tokens", denominator),
        ("billing_rounding_rule", rounding),
        ("environment", environment),
        ("fingerprint", fingerprint),
        ("_witness", None),
    ):
        object.__setattr__(value, name, item)
    value.validate()
    key = id(value)

    def cleanup(stored: ref[SemanticProfileSet], key: int = key) -> None:
        if _ISSUED.get(key, (None, None))[0] is stored:
            _ISSUED.pop(key, None)

    stored = ref(value, cleanup)
    _ISSUED[key] = (
        stored,
        _IssuanceRecord(
            fingerprint,
            _semantic_projection_bytes(
                revision,
                (profiles, tokenizer_specifications, budget_profiles),
                retry,
                (request_quota, quota, cost),
                (denominator, rounding, environment),
            ),
        ),
    )
    return value
