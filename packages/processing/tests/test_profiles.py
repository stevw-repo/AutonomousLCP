"""Strict immutable semantic provider-profile contract tests."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import asklegal_processing.profiles as semantic_profiles
import pytest
from asklegal_contracts import ContractViolation, SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_legal_desks import GenerativeTask
from asklegal_processing.profiles import (
    ProfileError,
    ProviderRetryProfile,
    load_semantic_profile_set,
)


class _Reader:
    """One immutable synthetic profile object for loader tests."""

    def __init__(self, raw: bytes) -> None:
        self.reference = ImmutableReference(
            ReferenceType.WORKFLOW_PROFILE,
            f"wap_{'1' * 48}",
            f"sha256:{sha256(raw).hexdigest()}",
        )
        self._raw = raw

    def read_exact(self, reference: ImmutableReference) -> bytes:
        """Return bytes only for the exact expected immutable reference."""
        assert reference == self.reference
        return self._raw

    def replace_bytes(self, raw: bytes) -> None:
        """Simulate immutable-storage drift after reference issuance."""
        self._raw = raw


@dataclass(frozen=True, slots=True)
class _ProfileOptions:
    """Synthetic semantic variations used by strict loader tests."""

    model_version: str = "1.0.0"
    stateful_features: bool = False
    allowed_environments: list[str] | None = None
    expires_at: str = "2099-01-01T00:00:00Z"
    extra_profile_field: bool = False
    partial: bool = False


def _profile_document(options: _ProfileOptions | None = None) -> bytes:
    settings = options or _ProfileOptions()
    profile = {
        "allowed_environments": settings.allowed_environments or ["LOCAL_SYNTHETIC"],
        "api_contract": "2026-08-01",
        "content_filter_policy": "STRICT",
        "data_handling_profile": "NO_TRAINING",
        "deployment_name": "synthetic-semantic-v1",
        "evaluator_id": "synthetic-evaluator-v1",
        "evidence_budget_bytes": 2048,
        "expires_at": settings.expires_at,
        "geography_class": "SYNTHETIC",
        "input_schema": "synthetic-input-v1",
        "max_output_tokens": 128,
        "model_id": "synthetic-model-v1",
        "model_version": settings.model_version,
        "output_schema": "synthetic-output-v1",
        "profile_id": "semantic-profile-v1",
        "prompt_fingerprint": f"sha256:{'2' * 64}",
        "provider": "AZURE_OPENAI",
        "resource_class": "SYNTHETIC",
        "retry_policy": "bounded-v1",
        "stateful_features": settings.stateful_features,
        "task": "HK_CASE_PROPOSITION_ANALYSIS",
        "threshold_basis_points": 9000,
        "tokenizer": "synthetic-tokenizer-v1",
    }
    if settings.extra_profile_field:
        profile["forbidden"] = "field"
    profiles = [profile]
    if not settings.partial:
        profiles = [
            {
                **profile,
                "profile_id": f"semantic-profile-{index}",
                "task": task.value,
            }
            for index, task in enumerate(GenerativeTask, start=1)
        ]
    document = {
        "billing_denominator_tokens": 1_000_000,
        "billing_rounding_rule": "PER_REQUEST_PER_DIRECTION_CEILING",
        "budget_profiles": [
            {
                "input_cost_microunits_per_million": 1,
                "max_input_tokens": 1024,
                "output_cost_microunits_per_million": 2,
                "profile_id": item["profile_id"],
            }
            for item in profiles
        ],
        "cost_limit_microunits": 1000,
        "environment": "LOCAL_SYNTHETIC",
        "expires_at": settings.expires_at,
        "fingerprint": "",
        "immutable": True,
        "profiles": profiles,
        "quota_limit_tokens": 4096,
        "request_quota": 64,
        "retry_profile": {
            "attempt_ceiling": 2,
            "backoff_seconds": [1],
            "timeout_seconds": 30,
        },
        "revision": "1.0.0",
        "schema_id": "asklegal.hk-v1-semantic-profile-set",
        "schema_version": "1.1.0",
        "tokenizer_specifications": [
            {
                "distribution_fingerprint": f"sha256:{'4' * 64}",
                "distribution_name": "synthetic-tokenizer-library",
                "distribution_version": "1.0.0",
                "encoding_resource_fingerprint": f"sha256:{'3' * 64}",
                "tokenizer_id": "synthetic-tokenizer-v1",
            }
        ],
    }
    fingerprint_projection = dict(document)
    fingerprint_projection.pop("fingerprint")
    document["fingerprint"] = (
        f"sha256:{sha256(canonicalize(checked_json_value(fingerprint_projection))).hexdigest()}"
    )
    return canonicalize(checked_json_value(document))


def _reseal(document: dict[str, JsonValue]) -> bytes:
    """Return exact canonical synthetic bytes after one hostile mutation."""
    projection = dict(document)
    projection.pop("fingerprint")
    document["fingerprint"] = (
        f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    )
    return canonicalize(checked_json_value(document))


class SyntheticProfileReader(_Reader):
    """Public test-only reader reused by the pure preflight suite."""


def synthetic_profile_document(options: _ProfileOptions | None = None) -> bytes:
    """Return the canonical complete synthetic semantic profile document."""
    return _profile_document(options)


def reseal_synthetic_profile(document: dict[str, JsonValue]) -> bytes:
    """Reseal one deliberately mutated synthetic profile document."""
    return _reseal(document)


def test_semantic_profile_rejects_placeholder_model_version() -> None:
    """A floating model version cannot become a provider profile."""
    with pytest.raises(ProfileError, match="MODEL_VERSION_NOT_EXACT"):
        load_semantic_profile_set(
            _Reader(_profile_document(_ProfileOptions(model_version="latest")))
        )


def test_semantic_profile_accepts_exact_azure_dated_model_version() -> None:
    """Azure deployment model revisions are published as exact calendar dates."""
    loaded = load_semantic_profile_set(
        _Reader(_profile_document(_ProfileOptions(model_version="2026-03-05")))
    )
    assert {profile.model_version for profile in loaded.profiles} == {"2026-03-05"}


@pytest.mark.parametrize("model_version", ["01", "\u0661"])
def test_semantic_profile_rejects_noncanonical_numeric_model_version(model_version: str) -> None:
    """Unicode and zero-padded numeric versions cannot evade exact grammar."""
    with pytest.raises(ProfileError, match="MODEL_VERSION_NOT_EXACT"):
        load_semantic_profile_set(
            _Reader(_profile_document(_ProfileOptions(model_version=model_version)))
        )


def test_semantic_profile_loads_a_detached_exact_profile_set() -> None:
    """Only a fully exact synthetic document becomes frozen semantic values."""
    loaded = load_semantic_profile_set(_Reader(_profile_document()))
    assert loaded.revision == "1.0.0"
    assert loaded.profiles[0].model_version == "1.0.0"
    assert loaded.profiles[0].allowed_environments == ("LOCAL_SYNTHETIC",)
    assert loaded.tokenizer_specifications[0].tokenizer_id == "synthetic-tokenizer-v1"
    assert loaded.budget_profiles[0].profile_id == loaded.profiles[0].profile_id
    assert loaded.request_quota == 64
    assert loaded.billing_denominator_tokens == 1_000_000
    assert loaded.billing_rounding_rule == "PER_REQUEST_PER_DIRECTION_CEILING"


def test_semantic_profile_schema_freezes_tokenizer_and_billing_contract() -> None:
    """The normative schema binds every new offline tokenizer and budget fact."""
    root = Path(__file__).resolve().parents[3] / "contracts"
    value = parse_json_bytes(_profile_document(), max_bytes=100_000)
    SchemaRegistry.from_contracts_root(root).validate(
        value,
        "schemas/hk-v1-semantic-profile.schema.json",
    )


def test_semantic_profile_rejects_missing_budget_mapping() -> None:
    """Every semantic profile must have exactly one immutable budget mapping."""
    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    budgets = document["budget_profiles"]
    assert isinstance(budgets, list)
    budgets.pop()
    with pytest.raises(ProfileError, match="BUDGET_PROFILE_MAPPING_INVALID"):
        load_semantic_profile_set(_Reader(_reseal(document)))


def test_semantic_profile_rejects_duplicate_budget_mapping() -> None:
    """A second mapping cannot override the price or ceiling for one profile."""
    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    budgets = document["budget_profiles"]
    assert isinstance(budgets, list)
    assert isinstance(budgets[0], dict)
    duplicate = dict(budgets[0])
    duplicate["max_input_tokens"] = 1023
    budgets.append(duplicate)
    with pytest.raises(ProfileError, match="BUDGET_PROFILE_MAPPING_INVALID"):
        load_semantic_profile_set(_Reader(_reseal(document)))


def test_semantic_profile_rejects_missing_and_unreferenced_tokenizer_specs() -> None:
    """Tokenizer IDs and exact specifications form one closed used catalogue."""
    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    document["tokenizer_specifications"] = []
    with pytest.raises(ProfileError, match="TOKENIZER_PROFILE_MAPPING_INVALID"):
        load_semantic_profile_set(_Reader(_reseal(document)))

    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    tokenizers = document["tokenizer_specifications"]
    assert isinstance(tokenizers, list)
    assert isinstance(tokenizers[0], dict)
    extra = dict(tokenizers[0])
    extra["tokenizer_id"] = "unused-synthetic-tokenizer-v1"
    tokenizers.append(extra)
    with pytest.raises(ProfileError, match="TOKENIZER_PROFILE_MAPPING_INVALID"):
        load_semantic_profile_set(_Reader(_reseal(document)))


def test_semantic_profile_rejects_boolean_numeric_budget_fact() -> None:
    """JSON booleans cannot pass through Python's integer subtype relation."""
    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    document["request_quota"] = True
    with pytest.raises(ProfileError, match="PROFILE_DOCUMENT_INVALID"):
        load_semantic_profile_set(_Reader(_reseal(document)))


def test_semantic_public_fingerprint_binds_tokenizer_and_price_facts() -> None:
    """Resealed result-affecting tokenizer or price drift changes issued identity."""
    baseline = load_semantic_profile_set(_Reader(_profile_document()))
    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    tokenizers = document["tokenizer_specifications"]
    assert isinstance(tokenizers, list)
    assert isinstance(tokenizers[0], dict)
    tokenizers[0]["encoding_resource_fingerprint"] = f"sha256:{'5' * 64}"
    changed_tokenizer = load_semantic_profile_set(_Reader(_reseal(document)))
    assert changed_tokenizer.fingerprint != baseline.fingerprint

    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    budgets = document["budget_profiles"]
    assert isinstance(budgets, list)
    assert isinstance(budgets[0], dict)
    budgets[0]["input_cost_microunits_per_million"] = 2
    changed_price = load_semantic_profile_set(_Reader(_reseal(document)))
    assert changed_price.fingerprint != baseline.fingerprint
    assert changed_price.fingerprint != changed_tokenizer.fingerprint


def test_semantic_profile_rejects_unknown_profile_field() -> None:
    """An unrecognized field cannot silently expand the provider contract."""
    with pytest.raises(ProfileError, match="PROFILE_KEYS_INVALID"):
        load_semantic_profile_set(
            _Reader(_profile_document(_ProfileOptions(extra_profile_field=True)))
        )


def test_semantic_profile_rejects_stateful_feature() -> None:
    """State retained at the provider is forbidden for the admitted profile."""
    with pytest.raises(ProfileError, match="STATEFUL_PROVIDER_FEATURE_FORBIDDEN"):
        load_semantic_profile_set(
            _Reader(_profile_document(_ProfileOptions(stateful_features=True)))
        )


def test_semantic_profile_rejects_environment_mismatch() -> None:
    """The document environment must be explicitly admitted by every profile."""
    with pytest.raises(ProfileError, match="PROFILE_ENVIRONMENT_MISMATCH"):
        load_semantic_profile_set(
            _Reader(_profile_document(_ProfileOptions(allowed_environments=["OTHER"])))
        )


def test_semantic_profile_rejects_expired_profile() -> None:
    """A profile whose shared expiry has elapsed cannot be loaded."""
    with pytest.raises(ProfileError, match="PROFILE_EXPIRED"):
        load_semantic_profile_set(
            _Reader(_profile_document(_ProfileOptions(expires_at="2000-01-01T00:00:00Z")))
        )


def test_semantic_profile_rejects_fractional_timestamp_in_schema_and_loader_scope() -> None:
    """The profile contract deliberately accepts only whole-second UTC instants."""
    with pytest.raises(ProfileError, match="PROFILE_EXPIRY_INVALID"):
        load_semantic_profile_set(
            _Reader(_profile_document(_ProfileOptions(expires_at="2099-01-01T00:00:00.1Z")))
        )


def test_semantic_profile_rejects_reader_toctou_drift() -> None:
    """The second immutable read must exactly repeat the first profile bytes."""
    raw = _profile_document()

    class _DriftingReader(_Reader):
        def read_exact(self, reference: ImmutableReference) -> bytes:
            value = super().read_exact(reference)
            self.replace_bytes(raw + b"x")
            return value

    with pytest.raises(ProfileError, match="PROFILE_READBACK_MISMATCH"):
        load_semantic_profile_set(_DriftingReader(raw))


def test_semantic_profile_rejects_partial_v1_task_catalogue() -> None:
    """One semantic task cannot stand in for the complete admitted V1 catalogue."""
    with pytest.raises(ProfileError, match="SEMANTIC_TASK_CATALOGUE_INCOMPLETE"):
        load_semantic_profile_set(_Reader(_profile_document(_ProfileOptions(partial=True))))


def test_semantic_profile_rejects_embedded_placeholder_token() -> None:
    """A placeholder substring is forbidden even when hidden inside a known leaf."""
    raw = _profile_document()
    document = parse_json_bytes(raw, max_bytes=100_000)
    assert isinstance(document, dict)
    profiles = document["profiles"]
    assert isinstance(profiles, list)
    assert isinstance(profiles[0], dict)
    profiles[0]["deployment_name"] = "synthetic-default-deployment"
    with pytest.raises(ProfileError, match="PROFILE_PLACEHOLDER_FORBIDDEN"):
        load_semantic_profile_set(_Reader(_reseal(document)))


def test_semantic_profile_allows_benign_risk_hyphen_text() -> None:
    """Credential screening is structured, not a false-positive `risk-` substring ban."""
    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    profiles = document["profiles"]
    assert isinstance(profiles, list)
    assert isinstance(profiles[0], dict)
    profiles[0]["resource_class"] = "risk-safe"
    assert load_semantic_profile_set(_Reader(_reseal(document))).profiles


def test_semantic_profile_rejects_structured_secret_value() -> None:
    """A real token-shaped value is forbidden in a recognized influential field."""
    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    profiles = document["profiles"]
    assert isinstance(profiles, list)
    assert isinstance(profiles[0], dict)
    profiles[0]["model_id"] = "sk-abcdef123456"
    with pytest.raises(ProfileError, match="PROFILE_SECRET_FORBIDDEN"):
        load_semantic_profile_set(_Reader(_reseal(document)))


def test_semantic_reader_gets_disposable_reference_copies() -> None:
    """Neither read receives the reader-owned reference instance."""
    raw = _profile_document()

    class _IdentityReader(_Reader):
        def read_exact(self, reference: ImmutableReference) -> bytes:
            assert reference is not self.reference
            return super().read_exact(reference)

    assert load_semantic_profile_set(_IdentityReader(raw)).profiles


def test_semantic_reader_reference_is_sampled_once_and_remains_stable() -> None:
    """Reader-owned reference identity cannot be reread or changed mid-read."""
    raw = _profile_document()

    class _OneSampleReader(_Reader):
        @property
        def reference(self) -> ImmutableReference:
            if getattr(self, "_reference_sampled", False):
                raise AssertionError
            self._reference_sampled = True
            return self._reference

        @reference.setter
        def reference(self, value: ImmutableReference) -> None:
            self._reference = value

        def read_exact(self, reference: ImmutableReference) -> bytes:
            assert reference == self._reference
            return self._raw

    assert load_semantic_profile_set(_OneSampleReader(raw)).profiles


def test_semantic_reader_reference_mutation_is_refused() -> None:
    """A reader cannot alter its authoritative reference during a disposable read."""
    raw = _profile_document()

    class _MutatingReader(_Reader):
        def read_exact(self, reference: ImmutableReference) -> bytes:
            value = super().read_exact(reference)
            object.__setattr__(self.reference, "ref_id", f"wap_{'2' * 48}")
            return value

    with pytest.raises(ProfileError, match="PROFILE_REFERENCE_MUTATED"):
        load_semantic_profile_set(_MutatingReader(raw))


def test_semantic_reader_oserror_is_normalized_but_interrupts_escape() -> None:
    """Storage faults close as profile errors while BaseException remains visible."""
    raw = _profile_document()

    class _OSErrorReader(_Reader):
        def read_exact(self, reference: ImmutableReference) -> bytes:
            del reference
            message = "offline"
            raise OSError(message)

    class _InterruptReader(_Reader):
        def read_exact(self, reference: ImmutableReference) -> bytes:
            del reference
            raise KeyboardInterrupt

    with pytest.raises(ProfileError, match="PROFILE_READ_FAILED"):
        load_semantic_profile_set(_OSErrorReader(raw))
    with pytest.raises(KeyboardInterrupt):
        load_semantic_profile_set(_InterruptReader(raw))


def test_semantic_reference_property_oserror_is_normalized() -> None:
    """Obtaining the single authoritative reference has the same ordinary fault policy."""

    class _PropertyFaultReader:
        @property
        def reference(self) -> ImmutableReference:
            message = "offline"
            raise OSError(message)

        def read_exact(self, reference: ImmutableReference) -> bytes:
            del reference
            raise AssertionError

    with pytest.raises(ProfileError, match="PROFILE_READ_FAILED"):
        load_semantic_profile_set(_PropertyFaultReader())


def test_semantic_direct_reconstruction_replays_closed_invariants() -> None:
    """Direct dataclass construction and replacement cannot bypass loader bounds."""
    loaded = load_semantic_profile_set(_Reader(_profile_document()))
    with pytest.raises(ProfileError, match="PROFILE_RETRY_INVALID"):
        ProviderRetryProfile(1, 1, (1,))
    with pytest.raises(ProfileError, match="PROFILE_RETRY_INVALID"):
        ProviderRetryProfile(4, 1, (0, 0, 0))
    with pytest.raises(TypeError):
        replace(loaded, quota_limit_tokens=0)
    with pytest.raises(TypeError):
        replace(loaded, quota_limit_tokens=5_000)
    malformed_profile = replace(loaded.profiles[0])
    object.__setattr__(malformed_profile, "task", [])
    with pytest.raises(TypeError):
        replace(loaded, profiles=(malformed_profile, *loaded.profiles[1:]))

    class _Text(str):
        __slots__ = ()

    with pytest.raises(TypeError):
        replace(loaded, revision=_Text("1.0.0"))


def test_semantic_profile_copy_and_pickle_are_nontransferable() -> None:
    """Reader-issued immutable authority cannot be copied or serialized."""
    loaded = load_semantic_profile_set(_Reader(_profile_document()))
    with pytest.raises(TypeError, match="PROFILE_NONTRANSFERABLE"):
        copy.copy(loaded)


def test_semantic_active_environment_is_authenticated_identity() -> None:
    """A different admitted active environment yields a different issued identity."""
    local = load_semantic_profile_set(_Reader(_profile_document()))
    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    document["environment"] = "OTHER"
    profiles = document["profiles"]
    assert isinstance(profiles, list)
    for profile in profiles:
        assert isinstance(profile, dict)
        profile["allowed_environments"] = ["OTHER"]
    other = load_semantic_profile_set(_Reader(_reseal(document)))
    assert other.environment == "OTHER"
    assert other.fingerprint != local.fingerprint


def _direct_semantic_set(
    expires_at: str,
    divergent_expiry: str | None = None,
    *,
    tokenizer_overrides: dict[str, object] | None = None,
    budget_overrides: dict[str, object] | None = None,
) -> semantic_profiles.SemanticProfileSet:
    """Build a coherent, unissued public projection for direct-validator tests."""
    loaded = load_semantic_profile_set(_Reader(_profile_document()))
    profiles = tuple(
        replace(
            profile,
            expires_at=divergent_expiry if position == 0 and divergent_expiry else expires_at,
        )
        for position, profile in enumerate(loaded.profiles)
    )
    tokenizer_specifications = loaded.tokenizer_specifications
    if tokenizer_overrides:
        original = tokenizer_specifications[0]
        forged = object.__new__(semantic_profiles.TokenizerSpecification)
        for name in (
            "tokenizer_id",
            "distribution_name",
            "distribution_version",
            "distribution_fingerprint",
            "encoding_resource_fingerprint",
        ):
            object.__setattr__(
                forged,
                name,
                tokenizer_overrides.get(name, getattr(original, name)),
            )
        tokenizer_specifications = (forged, *tokenizer_specifications[1:])
    budget_profiles = loaded.budget_profiles
    if budget_overrides:
        original_budget = budget_profiles[0]
        forged_budget = object.__new__(semantic_profiles.SemanticBudgetProfile)
        for name in (
            "profile_id",
            "max_input_tokens",
            "input_cost_microunits_per_million",
            "output_cost_microunits_per_million",
        ):
            object.__setattr__(
                forged_budget,
                name,
                budget_overrides.get(name, getattr(original_budget, name)),
            )
        budget_profiles = (forged_budget, *budget_profiles[1:])
    projection = {
        "billing_denominator_tokens": loaded.billing_denominator_tokens,
        "billing_rounding_rule": loaded.billing_rounding_rule,
        "budget_profiles": [
            {
                "input_cost_microunits_per_million": (budget.input_cost_microunits_per_million),
                "max_input_tokens": budget.max_input_tokens,
                "output_cost_microunits_per_million": (budget.output_cost_microunits_per_million),
                "profile_id": budget.profile_id,
            }
            for budget in budget_profiles
        ],
        "cost_limit_microunits": loaded.cost_limit_microunits,
        "environment": loaded.environment,
        "profiles": [
            {
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
            for profile in profiles
        ],
        "quota_limit_tokens": loaded.quota_limit_tokens,
        "request_quota": loaded.request_quota,
        "retry_profile": {
            "attempt_ceiling": loaded.retry_profile.attempt_ceiling,
            "backoff_seconds": list(loaded.retry_profile.backoff_seconds),
            "timeout_seconds": loaded.retry_profile.timeout_seconds,
        },
        "revision": loaded.revision,
        "tokenizer_specifications": [
            {
                "distribution_fingerprint": item.distribution_fingerprint,
                "distribution_name": item.distribution_name,
                "distribution_version": item.distribution_version,
                "encoding_resource_fingerprint": item.encoding_resource_fingerprint,
                "tokenizer_id": item.tokenizer_id,
            }
            for item in tokenizer_specifications
        ],
        "type": "asklegal.semantic-profile-set.public.v1",
    }
    fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    direct = object.__new__(semantic_profiles.SemanticProfileSet)
    for name, value in (
        ("revision", loaded.revision),
        ("profiles", profiles),
        ("tokenizer_specifications", tokenizer_specifications),
        ("budget_profiles", budget_profiles),
        ("retry_profile", loaded.retry_profile),
        ("request_quota", loaded.request_quota),
        ("quota_limit_tokens", loaded.quota_limit_tokens),
        ("cost_limit_microunits", loaded.cost_limit_microunits),
        ("billing_denominator_tokens", loaded.billing_denominator_tokens),
        ("billing_rounding_rule", loaded.billing_rounding_rule),
        ("environment", loaded.environment),
        ("fingerprint", fingerprint),
        ("_witness", None),
    ):
        object.__setattr__(direct, name, value)
    return direct


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("tokenizer_id", ""),
        ("distribution_name", ""),
        ("distribution_version", "latest"),
        ("distribution_fingerprint", "sha256:not-a-digest"),
        ("encoding_resource_fingerprint", "sha256:not-a-digest"),
    ],
)
def test_semantic_direct_validator_replays_every_tokenizer_field(
    field_name: str, invalid_value: object
) -> None:
    """A coherently resealed forged tokenizer object cannot bypass its constructor."""
    with pytest.raises(ProfileError, match="PROFILE_SET_INVALID"):
        _direct_semantic_set(
            "2099-01-01T00:00:00Z",
            tokenizer_overrides={field_name: invalid_value},
        ).validate()


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("profile_id", ""),
        ("max_input_tokens", True),
        ("input_cost_microunits_per_million", -1),
        ("output_cost_microunits_per_million", -1),
    ],
)
def test_semantic_direct_validator_replays_every_budget_field(
    field_name: str, invalid_value: object
) -> None:
    """A coherently resealed forged budget object cannot bypass its constructor."""
    with pytest.raises(ProfileError, match="PROFILE_SET_INVALID"):
        _direct_semantic_set(
            "2099-01-01T00:00:00Z",
            budget_overrides={field_name: invalid_value},
        ).validate()


@pytest.mark.parametrize(
    ("group", "field_name"),
    [
        ("root", "request_quota"),
        ("root", "quota_limit_tokens"),
        ("root", "cost_limit_microunits"),
        ("retry", "timeout_seconds"),
        ("retry", "backoff_seconds"),
        ("budget", "max_input_tokens"),
        ("budget", "input_cost_microunits_per_million"),
        ("budget", "output_cost_microunits_per_million"),
        ("profile", "evidence_budget_bytes"),
        ("profile", "max_output_tokens"),
        ("profile", "threshold_basis_points"),
    ],
)
def test_semantic_schema_and_loader_reject_unsafe_integer_boundary(
    group: str, field_name: str
) -> None:
    """Schema and loader share the exact I-JSON safe-integer upper boundary."""
    document = parse_json_bytes(_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    unsafe = 9_007_199_254_740_992
    if group == "root":
        document[field_name] = unsafe
    elif group == "retry":
        retry = document["retry_profile"]
        assert isinstance(retry, dict)
        retry[field_name] = [unsafe] if field_name == "backoff_seconds" else unsafe
    elif group == "budget":
        budgets = document["budget_profiles"]
        assert isinstance(budgets, list)
        budget = budgets[0]
        assert isinstance(budget, dict)
        budget[field_name] = unsafe
    elif group == "profile":
        profiles = document["profiles"]
        assert isinstance(profiles, list)
        profile = profiles[0]
        assert isinstance(profile, dict)
        profile[field_name] = unsafe
    else:
        raise AssertionError
    root = Path(__file__).resolve().parents[3] / "contracts"
    registry = SchemaRegistry.from_contracts_root(root)
    with pytest.raises(ContractViolation):
        registry.validate(document, "schemas/hk-v1-semantic-profile.schema.json")
    raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    with pytest.raises(ProfileError, match="PROFILE_DOCUMENT_INVALID"):
        load_semantic_profile_set(_Reader(raw))


def test_semantic_direct_validator_requires_whole_second_utc_expiry() -> None:
    """Unissued coherent projections share the loader/schema whole-second grammar."""
    _direct_semantic_set("2099-01-01T00:00:00Z").validate()

    class _Timestamp(str):
        __slots__ = ()

    for expires_at in (
        "2099-01-01T00:00:00.123000Z",
        "2099-01-01T00:00:00+00:00",
        "20990101T000000Z",
        "2099-01-01T00:00:00,123000Z",
        "2099-02-30T00:00:00Z",
        _Timestamp("2099-01-01T00:00:00Z"),
    ):
        with pytest.raises(ProfileError, match="PROFILE_SET_INVALID"):
            _direct_semantic_set(expires_at).validate()


def test_semantic_direct_validator_requires_one_shared_profile_expiry() -> None:
    """Complete unissued task sets cannot bypass the loader's shared expiry fact."""
    _direct_semantic_set("2099-01-01T00:00:00Z").validate()
    with pytest.raises(ProfileError, match="PROFILE_SET_INVALID"):
        _direct_semantic_set("2099-01-01T00:00:00Z", "2098-01-01T00:00:00Z").validate()
