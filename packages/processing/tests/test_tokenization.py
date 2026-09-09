"""Pure exact-count budget preflight tests for semantic provider work."""

from __future__ import annotations

import builtins
import socket
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import asklegal_processing.profiles as semantic_profiles
import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_processing.profiles import (
    ProfileError,
    SemanticProfileSet,
    load_semantic_profile_set,
)
from asklegal_processing.tokenization import (
    ProviderBudgetDecision,
    ProviderBudgetRequest,
    preflight_provider_budget,
)
from test_profiles import (
    SyntheticProfileReader,
    reseal_synthetic_profile,
    synthetic_profile_document,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue


def _profile_set() -> SemanticProfileSet:
    return load_semantic_profile_set(SyntheticProfileReader(synthetic_profile_document()))


def _mutated_profile_set(
    mutate: Callable[[dict[str, JsonValue]], None],
) -> SemanticProfileSet:
    document = parse_json_bytes(synthetic_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    mutate(document)
    return load_semantic_profile_set(SyntheticProfileReader(reseal_synthetic_profile(document)))


def test_preflight_uses_per_request_per_direction_ceiling() -> None:
    """Each nonzero direction is rounded up before request charges are summed."""
    profile_set = _profile_set()
    first, second = profile_set.profiles[:2]
    decision = preflight_provider_budget(
        (
            ProviderBudgetRequest(first.profile_id, 1, 1),
            ProviderBudgetRequest(second.profile_id, 1, 1),
        ),
        profile_set,
    )
    assert decision == ProviderBudgetDecision(2, 2, 4)
    assert all(
        type(value) is int
        for value in (
            decision.total_input_tokens,
            decision.total_worst_case_output_tokens,
            decision.worst_case_cost_microunits,
        )
    )


def test_preflight_never_opens_cache_imports_tokenizers_or_uses_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pure preflight consumes counts and profile facts without hidden I/O."""
    profile_set = _profile_set()
    request = ProviderBudgetRequest(profile_set.profiles[0].profile_id, 1, 1)

    def forbidden_open(*args: object, **kwargs: object) -> None:
        del args, kwargs
        message = "ambient cache access"
        raise AssertionError(message)

    def forbidden_socket(*args: object, **kwargs: object) -> None:
        del args, kwargs
        message = "network access"
        raise AssertionError(message)

    original_import = builtins.__import__

    def guarded_import(
        name: str,
        global_vars: Mapping[str, object] | None = None,
        local_vars: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = (),
        level: int = 0,
    ) -> object:
        if name.partition(".")[0] in {"tiktoken", "tokenizers", "openai"}:
            message = "tokenizer or provider import"
            raise AssertionError(message)
        return original_import(name, global_vars, local_vars, fromlist, level)

    monkeypatch.setattr(builtins, "open", forbidden_open)
    monkeypatch.setattr(socket, "socket", forbidden_socket)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert preflight_provider_budget((request,), profile_set).total_input_tokens == 1


def test_preflight_rechecks_expiry_after_profile_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """A once-valid issued profile cannot remain usable after its exact expiry."""
    profile_set = _profile_set()

    class _ExpiredClock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            del tz
            return cls(2100, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(semantic_profiles, "datetime", _ExpiredClock)
    request = ProviderBudgetRequest(profile_set.profiles[0].profile_id, 1, 1)
    with pytest.raises(ProfileError, match="PROFILE_SET_INVALID"):
        preflight_provider_budget((request,), profile_set)


def test_preflight_rejects_hostile_billing_constant_subclasses_before_arithmetic() -> None:
    """Same-valued subclasses cannot override billing arithmetic or contract identity."""

    class _HostileDenominator(int):
        calls = 0

        def __rdivmod__(self, other: object) -> tuple[int, int]:
            del other
            type(self).calls += 1
            return 0, 0

    profile_set = _profile_set()
    object.__setattr__(
        profile_set,
        "billing_denominator_tokens",
        _HostileDenominator(1_000_000),
    )
    request = ProviderBudgetRequest(profile_set.profiles[0].profile_id, 1, 1)
    with pytest.raises(ProfileError, match="PROFILE_SET_INVALID"):
        preflight_provider_budget((request,), profile_set)
    assert _HostileDenominator.calls == 0

    class _RoundingRule(str):
        __slots__ = ()

    profile_set = _profile_set()
    object.__setattr__(
        profile_set,
        "billing_rounding_rule",
        _RoundingRule("PER_REQUEST_PER_DIRECTION_CEILING"),
    )
    with pytest.raises(ProfileError, match="PROFILE_SET_INVALID"):
        preflight_provider_budget((request,), profile_set)


def test_preflight_rejects_bool_as_exact_count() -> None:
    """A bool cannot masquerade as an already measured integer token count."""
    profile_set = _profile_set()
    request = object.__new__(ProviderBudgetRequest)
    object.__setattr__(request, "profile_id", profile_set.profiles[0].profile_id)
    object.__setattr__(request, "input_tokens", True)
    object.__setattr__(request, "worst_case_output_tokens", 0)
    with pytest.raises(ProfileError, match="BUDGET_REQUEST_INVALID"):
        preflight_provider_budget((request,), profile_set)


def test_preflight_rejects_empty_and_duplicate_requests() -> None:
    """A preflight covers a nonempty unique request inventory exactly once."""
    profile_set = _profile_set()
    with pytest.raises(ProfileError, match="BUDGET_REQUESTS_EMPTY"):
        preflight_provider_budget((), profile_set)
    request = ProviderBudgetRequest(profile_set.profiles[0].profile_id, 1, 1)
    with pytest.raises(ProfileError, match="BUDGET_REQUEST_DUPLICATE"):
        preflight_provider_budget((request, request), profile_set)


def test_preflight_rejects_unknown_profile_mapping() -> None:
    """Measured counts cannot select a profile absent from the immutable set."""
    profile_set = _profile_set()
    with pytest.raises(ProfileError, match="BUDGET_PROFILE_MAPPING_INVALID"):
        preflight_provider_budget((ProviderBudgetRequest("unknown-profile", 1, 1),), profile_set)


def test_preflight_rejects_input_and_output_one_above_profile_limits() -> None:
    """Both exact per-request direction ceilings fail at their first excess token."""
    profile_set = _profile_set()
    profile = profile_set.profiles[0]
    with pytest.raises(ProfileError, match="INPUT_TOKEN_LIMIT_EXCEEDED"):
        preflight_provider_budget(
            (ProviderBudgetRequest(profile.profile_id, 1025, 0),), profile_set
        )
    with pytest.raises(ProfileError, match="OUTPUT_TOKEN_LIMIT_EXCEEDED"):
        preflight_provider_budget(
            (ProviderBudgetRequest(profile.profile_id, 0, profile.max_output_tokens + 1),),
            profile_set,
        )


def test_preflight_rejects_request_and_aggregate_quota_overflow() -> None:
    """Request count and total token quota are independent closed ceilings."""
    profile_set = _mutated_profile_set(lambda document: document.__setitem__("request_quota", 1))
    request = ProviderBudgetRequest(profile_set.profiles[0].profile_id, 1, 0)
    with pytest.raises(ProfileError, match="REQUEST_QUOTA_EXCEEDED"):
        preflight_provider_budget(
            (request, ProviderBudgetRequest(profile_set.profiles[0].profile_id, 2, 0)),
            profile_set,
        )

    profile_set = _profile_set()
    requests = tuple(
        ProviderBudgetRequest(profile.profile_id, 1024, profile.max_output_tokens)
        for profile in profile_set.profiles[:4]
    )
    with pytest.raises(ProfileError, match="TOKEN_QUOTA_EXCEEDED"):
        preflight_provider_budget(requests, profile_set)


def test_preflight_rejects_checked_multiplication_overflow() -> None:
    """Python's unbounded integers cannot bypass the contract arithmetic range."""

    def expensive(document: dict[str, JsonValue]) -> None:
        budgets = document["budget_profiles"]
        assert isinstance(budgets, list)
        assert isinstance(budgets[0], dict)
        budgets[0]["input_cost_microunits_per_million"] = 9_007_199_254_740_991

    profile_set = _mutated_profile_set(expensive)
    with pytest.raises(ProfileError, match="ARITHMETIC_OVERFLOW"):
        preflight_provider_budget(
            (ProviderBudgetRequest(profile_set.profiles[0].profile_id, 2, 0),), profile_set
        )


def test_preflight_rejects_per_request_and_aggregate_addition_overflow() -> None:
    """Direction and aggregate sums stay inside the same checked integer domain."""

    def enormous(document: dict[str, JsonValue]) -> None:
        document["quota_limit_tokens"] = 9_007_199_254_740_991
        budgets = document["budget_profiles"]
        assert isinstance(budgets, list)
        for budget in budgets[:2]:
            assert isinstance(budget, dict)
            budget["max_input_tokens"] = 9_007_199_254_740_991
            budget["input_cost_microunits_per_million"] = 0
            budget["output_cost_microunits_per_million"] = 0

    profile_set = _mutated_profile_set(enormous)
    first, second = profile_set.profiles[:2]
    with pytest.raises(ProfileError, match="ARITHMETIC_OVERFLOW"):
        preflight_provider_budget(
            (ProviderBudgetRequest(first.profile_id, 9_007_199_254_740_991, 1),),
            profile_set,
        )
    with pytest.raises(ProfileError, match="ARITHMETIC_OVERFLOW"):
        preflight_provider_budget(
            (
                ProviderBudgetRequest(first.profile_id, 9_007_199_254_740_990, 0),
                ProviderBudgetRequest(second.profile_id, 2, 0),
            ),
            profile_set,
        )


def test_preflight_accepts_cost_limit_and_rejects_one_microunit_over() -> None:
    """The immutable aggregate cost ceiling is inclusive and exact to one microunit."""

    def exact_cost(document: dict[str, JsonValue]) -> None:
        document["cost_limit_microunits"] = 1
        budgets = document["budget_profiles"]
        assert isinstance(budgets, list)
        assert isinstance(budgets[0], dict)
        budgets[0]["input_cost_microunits_per_million"] = 1_000_000
        budgets[0]["output_cost_microunits_per_million"] = 1_000_000

    exact = _mutated_profile_set(exact_cost)
    profile_id = exact.profiles[0].profile_id
    assert (
        preflight_provider_budget(
            (ProviderBudgetRequest(profile_id, 1, 0),), exact
        ).worst_case_cost_microunits
        == 1
    )
    with pytest.raises(ProfileError, match="COST_LIMIT_EXCEEDED"):
        preflight_provider_budget((ProviderBudgetRequest(profile_id, 1, 1),), exact)
