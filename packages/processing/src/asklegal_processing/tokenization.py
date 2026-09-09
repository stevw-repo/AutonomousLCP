"""Hermetic semantic token counting and pure provider-budget preflight."""

from __future__ import annotations

from base64 import b64decode
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Never, Protocol

import tiktoken
from tiktoken.core import Encoding

from .profiles import (
    ProfileError,
    SemanticBudgetProfile,
    SemanticProfileSet,
    validate_semantic_profile_set_authority,
)

if TYPE_CHECKING:
    from asklegal_legal_desks import SemanticTaskProfile

_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_O200K_BASE = "o200k_base"
_TIKTOKEN_DISTRIBUTION = "tiktoken"
_TIKTOKEN_VERSION = "0.12.0"
_TIKTOKEN_CP314_LINUX_AMD64_FINGERPRINT = (
    "sha256:d186a5c60c6a0213f04a7a802264083dea1bbde92a2d4c7069e1a56630aef830"
)
_TIKTOKEN_CP314_LINUX_AMD64_RUNTIME_TREE_FINGERPRINT = (
    "sha256:b6f28eef6b4fcb18bc35af19c93f006cadf87511b72fd91614482c294697e562"
)
_O200K_BASE_RESOURCE_FINGERPRINT = (
    "sha256:446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
)
_O200K_BASE_PATTERN = (
    r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?"""
    r"""|[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?"""
    r"""|\p{N}{1,3}"""
    r"""| ?[^\s\p{L}\p{N}]+[\r\n/]*"""
    r"""|\s*[\r\n]+"""
    r"""|\s+(?!\S)"""
    r"""|\s+"""
)
_O200K_BASE_SPECIAL_TOKENS = {"<|endoftext|>": 199999, "<|endofprompt|>": 200018}


class TokenCounter(Protocol):
    """Exact token-count boundary for one already admitted tokenizer."""

    @property
    def tokenizer_id(self) -> str:
        """Return the exact tokenizer identity implemented by this counter."""
        ...

    def count(self, text: str) -> int:
        """Return the exact count for one exact builtin text value."""
        ...


@dataclass(frozen=True, slots=True)
class ExactTokenCounter:
    """One local ``o200k_base`` counter built solely from supplied rank bytes."""

    _encoding: Encoding
    _tokenizer_id: str

    def __init__(
        self,
        profile_set: SemanticProfileSet,
        tokenizer_id: str,
        encoding_resource: bytes,
    ) -> None:
        """Validate issued profile identity and supplied resource before constructing an encoder."""
        _validate_exact_tokenizer_inputs(profile_set, tokenizer_id, encoding_resource)
        object.__setattr__(self, "_tokenizer_id", tokenizer_id)
        object.__setattr__(
            self, "_encoding", o200k_base_encoding_from_exact_resource(encoding_resource)
        )

    @property
    def tokenizer_id(self) -> str:
        """Return the exact profile-bound tokenizer identity."""
        return self._tokenizer_id

    def count(self, text: str) -> int:
        """Count without a registry, resource cache, alias, or network fallback."""
        if type(text) is not str:
            _fail("TOKEN_TEXT_INVALID")
        count = len(self._encoding.encode_ordinary(text))
        if type(count) is not int or count < 0 or count > _MAX_SAFE_INTEGER:
            _fail("TOKEN_COUNT_INVALID")
        return count


@dataclass(frozen=True, slots=True)
class ExactTokenizerResourceCounter:
    """Exact counter issued from a named tokenizer and its pinned rank bytes."""

    _encoding: Encoding
    _tokenizer_id: str

    def __init__(self, tokenizer_id: str, encoding_resource: bytes) -> None:
        """Validate the sole supported tokenizer resource before construction."""
        if tokenizer_id != _O200K_BASE:
            _fail("TOKENIZER_ID_UNSUPPORTED")
        digest = f"sha256:{sha256(encoding_resource).hexdigest()}"
        if digest != _O200K_BASE_RESOURCE_FINGERPRINT:
            _fail("TOKENIZER_RESOURCE_FINGERPRINT_MISMATCH")
        object.__setattr__(self, "_tokenizer_id", tokenizer_id)
        object.__setattr__(
            self,
            "_encoding",
            o200k_base_encoding_from_exact_resource(encoding_resource),
        )

    @property
    def tokenizer_id(self) -> str:
        """Return the exact tokenizer identity."""
        return self._tokenizer_id

    def count(self, text: str) -> int:
        """Count one exact input without registry or network fallback."""
        if type(text) is not str:
            _fail("TOKEN_TEXT_INVALID")
        return len(self._encoding.encode_ordinary(text))


@dataclass(frozen=True, slots=True)
class ProviderBudgetRequest:
    """One unique planned provider request with counts measured upstream."""

    profile_id: str
    input_tokens: int
    worst_case_output_tokens: int

    def __post_init__(self) -> None:
        """Reject coercion and values outside the canonical integer domain."""
        if not _valid_request(self):
            _fail("BUDGET_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class ProviderBudgetDecision:
    """Exact conservative aggregate accepted before any provider effect."""

    total_input_tokens: int
    total_worst_case_output_tokens: int
    worst_case_cost_microunits: int


def _fail(code: str) -> Never:
    raise ProfileError(code)


def _validate_exact_tokenizer_inputs(
    profile_set: SemanticProfileSet,
    tokenizer_id: str,
    encoding_resource: bytes,
) -> None:
    """Close profile, distribution, resource, and tokenizer-alias substitution paths."""
    if type(profile_set) is not SemanticProfileSet:
        _fail("PROFILE_SET_INVALID")
    validate_semantic_profile_set_authority(profile_set)
    profile_set.validate()
    if type(tokenizer_id) is not str or tokenizer_id != _O200K_BASE:
        _fail("TOKENIZER_ID_UNSUPPORTED")
    if type(encoding_resource) is not bytes or not encoding_resource:
        _fail("TOKENIZER_RESOURCE_INVALID")
    specifications = {
        specification.tokenizer_id: specification
        for specification in profile_set.tokenizer_specifications
    }
    specification = specifications.get(tokenizer_id)
    if specification is None:
        _fail("TOKENIZER_ID_UNSUPPORTED")
    if (
        specification.distribution_name != _TIKTOKEN_DISTRIBUTION
        or specification.distribution_version != _TIKTOKEN_VERSION
        or specification.distribution_fingerprint != _TIKTOKEN_CP314_LINUX_AMD64_FINGERPRINT
        or tiktoken.__version__ != _TIKTOKEN_VERSION
        or _installed_tiktoken_tree_fingerprint()
        != _TIKTOKEN_CP314_LINUX_AMD64_RUNTIME_TREE_FINGERPRINT
    ):
        _fail("TOKENIZER_DISTRIBUTION_MISMATCH")
    if specification.encoding_resource_fingerprint != _O200K_BASE_RESOURCE_FINGERPRINT:
        _fail("TOKENIZER_RESOURCE_FINGERPRINT_MISMATCH")
    fingerprint = f"sha256:{sha256(encoding_resource).hexdigest()}"
    if fingerprint != specification.encoding_resource_fingerprint:
        _fail("TOKENIZER_RESOURCE_FINGERPRINT_MISMATCH")


def _installed_tiktoken_tree_fingerprint() -> str:
    """Measure code bytes directly, without trusting editable or dist-info metadata."""
    module_path = getattr(tiktoken, "__file__", None)
    if type(module_path) is not str:
        _fail("TOKENIZER_DISTRIBUTION_MISMATCH")
    init_path = Path(module_path)
    if init_path.is_symlink() or init_path.name != "__init__.py":
        _fail("TOKENIZER_DISTRIBUTION_MISMATCH")
    package_root = init_path.resolve().parent
    site_packages = package_root.parent
    extension_root = site_packages / "tiktoken_ext"
    if (
        package_root.name != "tiktoken"
        or package_root.is_symlink()
        or not package_root.is_dir()
        or extension_root.is_symlink()
        or not extension_root.is_dir()
    ):
        _fail("TOKENIZER_DISTRIBUTION_MISMATCH")
    try:
        files = tuple(
            sorted(
                (
                    path
                    for root in (package_root, extension_root)
                    for path in root.rglob("*")
                    if path.is_file()
                    and not path.is_symlink()
                    and "__pycache__" not in path.parts
                    and path.suffix != ".pyc"
                ),
                key=lambda path: path.relative_to(site_packages).as_posix(),
            )
        )
        if not files:
            _fail("TOKENIZER_DISTRIBUTION_MISMATCH")
        digest = sha256()
        for path in files:
            relative = path.relative_to(site_packages).as_posix().encode("utf-8")
            digest.update(relative)
            digest.update(b"\0")
            digest.update(sha256(path.read_bytes()).digest())
        return f"sha256:{digest.hexdigest()}"
    except ProfileError:
        raise
    except (OSError, ValueError) as error:
        message = "TOKENIZER_DISTRIBUTION_MISMATCH"
        raise ProfileError(message) from error


def o200k_base_encoding_from_exact_resource(encoding_resource: bytes) -> Encoding:
    """Decode the pinned BPE bytes directly, never the upstream cached URL loader."""
    ranks: dict[bytes, int] = {}
    assigned_ranks: set[int] = set()
    try:
        for line in encoding_resource.splitlines():
            if not line:
                continue
            token, rank = line.split()
            decoded = b64decode(token, validate=True)
            parsed_rank = int(rank)
            if not decoded or parsed_rank < 0 or parsed_rank > _MAX_SAFE_INTEGER:
                _fail("TOKENIZER_RESOURCE_MALFORMED")
            if decoded in ranks or parsed_rank in assigned_ranks:
                _fail("TOKENIZER_RESOURCE_MALFORMED")
            ranks[decoded] = parsed_rank
            assigned_ranks.add(parsed_rank)
        if not ranks:
            _fail("TOKENIZER_RESOURCE_MALFORMED")
        return Encoding(
            name=_O200K_BASE,
            pat_str=_O200K_BASE_PATTERN,
            mergeable_ranks=ranks,
            special_tokens=_O200K_BASE_SPECIAL_TOKENS,
        )
    except ProfileError:
        raise
    except Exception as error:
        message = "TOKENIZER_RESOURCE_MALFORMED"
        raise ProfileError(message) from error


def _safe_nonnegative(value: object) -> bool:
    return type(value) is int and 0 <= value <= _MAX_SAFE_INTEGER


def _valid_request(request: object) -> bool:
    return (
        type(request) is ProviderBudgetRequest
        and type(request.profile_id) is str
        and bool(request.profile_id)
        and request.profile_id.strip() == request.profile_id
        and _safe_nonnegative(request.input_tokens)
        and _safe_nonnegative(request.worst_case_output_tokens)
    )


def _checked_add(left: int, right: int) -> int:
    if left > _MAX_SAFE_INTEGER - right:
        _fail("ARITHMETIC_OVERFLOW")
    return left + right


def _checked_multiply(left: int, right: int) -> int:
    if left != 0 and right > _MAX_SAFE_INTEGER // left:
        _fail("ARITHMETIC_OVERFLOW")
    return left * right


def _ceiling_charge(tokens: int, rate: int, denominator: int) -> int:
    product = _checked_multiply(tokens, rate)
    quotient, remainder = divmod(product, denominator)
    return _checked_add(quotient, int(remainder != 0))


def _profile_maps(
    profile_set: SemanticProfileSet,
) -> tuple[dict[str, SemanticTaskProfile], dict[str, SemanticBudgetProfile]]:
    profiles = {profile.profile_id: profile for profile in profile_set.profiles}
    budgets = {profile.profile_id: profile for profile in profile_set.budget_profiles}
    if len(profiles) != len(profile_set.profiles) or set(profiles) != set(budgets):
        _fail("BUDGET_PROFILE_MAPPING_INVALID")
    tokenizers = {item.tokenizer_id for item in profile_set.tokenizer_specifications}
    if tokenizers != {profile.tokenizer for profile in profile_set.profiles}:
        _fail("TOKENIZER_PROFILE_MAPPING_INVALID")
    return profiles, budgets


def _validated_requests(
    requests: tuple[ProviderBudgetRequest, ...], request_quota: int
) -> tuple[ProviderBudgetRequest, ...]:
    if type(requests) is not tuple:
        _fail("BUDGET_REQUEST_INVALID")
    if not requests:
        _fail("BUDGET_REQUESTS_EMPTY")
    if any(not _valid_request(request) for request in requests):
        _fail("BUDGET_REQUEST_INVALID")
    if len(set(requests)) != len(requests):
        _fail("BUDGET_REQUEST_DUPLICATE")
    if len(requests) > request_quota:
        _fail("REQUEST_QUOTA_EXCEEDED")
    return requests


def _request_totals(
    request: ProviderBudgetRequest,
    profile: SemanticTaskProfile,
    budget: SemanticBudgetProfile,
    profile_set: SemanticProfileSet,
) -> tuple[int, int]:
    if request.input_tokens > budget.max_input_tokens:
        _fail("INPUT_TOKEN_LIMIT_EXCEEDED")
    if request.worst_case_output_tokens > profile.max_output_tokens:
        _fail("OUTPUT_TOKEN_LIMIT_EXCEEDED")
    request_tokens = _checked_add(request.input_tokens, request.worst_case_output_tokens)
    input_cost = _ceiling_charge(
        request.input_tokens,
        budget.input_cost_microunits_per_million,
        profile_set.billing_denominator_tokens,
    )
    output_cost = _ceiling_charge(
        request.worst_case_output_tokens,
        budget.output_cost_microunits_per_million,
        profile_set.billing_denominator_tokens,
    )
    return request_tokens, _checked_add(input_cost, output_cost)


def preflight_provider_budget(
    requests: tuple[ProviderBudgetRequest, ...],
    profile_set: SemanticProfileSet,
) -> ProviderBudgetDecision:
    """Fail closed unless the complete exact request inventory fits every limit."""
    if type(profile_set) is not SemanticProfileSet:
        _fail("PROFILE_SET_INVALID")
    validate_semantic_profile_set_authority(profile_set)
    profile_set.validate()
    admitted_requests = _validated_requests(requests, profile_set.request_quota)
    profiles, budgets = _profile_maps(profile_set)
    total_input = 0
    total_output = 0
    total_tokens = 0
    total_cost = 0
    for request in admitted_requests:
        profile = profiles.get(request.profile_id)
        budget = budgets.get(request.profile_id)
        if profile is None or budget is None:
            _fail("BUDGET_PROFILE_MAPPING_INVALID")
        total_input = _checked_add(total_input, request.input_tokens)
        total_output = _checked_add(total_output, request.worst_case_output_tokens)
        request_tokens, request_cost = _request_totals(request, profile, budget, profile_set)
        total_tokens = _checked_add(total_tokens, request_tokens)
        total_cost = _checked_add(total_cost, request_cost)

    if total_tokens > profile_set.quota_limit_tokens:
        _fail("TOKEN_QUOTA_EXCEEDED")
    if total_cost > profile_set.cost_limit_microunits:
        _fail("COST_LIMIT_EXCEEDED")
    return ProviderBudgetDecision(total_input, total_output, total_cost)
