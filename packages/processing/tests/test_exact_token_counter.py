"""Acceptance tests for the hermetic exact semantic token counter."""

from __future__ import annotations

import builtins
import hashlib
import shutil
import socket
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import tiktoken
import tiktoken.load
import tiktoken.registry
from asklegal_contracts import parse_json_bytes
from asklegal_processing.profiles import ProfileError, SemanticProfileSet, load_semantic_profile_set
from asklegal_processing.tokenization import ExactTokenCounter
from test_profiles import (
    SyntheticProfileReader,
    reseal_synthetic_profile,
    synthetic_profile_document,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_RESOURCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "asklegal_processing"
    / "_resources"
    / "o200k_base.tiktoken"
)
_RESOURCE_FINGERPRINT = "sha256:446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
_DISTRIBUTION_FINGERPRINT = (
    "sha256:d186a5c60c6a0213f04a7a802264083dea1bbde92a2d4c7069e1a56630aef830"
)


def _profile_set(
    mutate: Callable[[dict[str, JsonValue]], None] | None = None,
) -> SemanticProfileSet:
    document = parse_json_bytes(synthetic_profile_document(), max_bytes=100_000)
    assert isinstance(document, dict)
    tokenizers = document["tokenizer_specifications"]
    profiles = document["profiles"]
    assert isinstance(tokenizers, list)
    assert isinstance(profiles, list)
    assert isinstance(tokenizers[0], dict)
    tokenizer = tokenizers[0]
    tokenizer["tokenizer_id"] = "o200k_base"
    tokenizer["distribution_name"] = "tiktoken"
    tokenizer["distribution_version"] = "0.12.0"
    tokenizer["distribution_fingerprint"] = _DISTRIBUTION_FINGERPRINT
    tokenizer["encoding_resource_fingerprint"] = _RESOURCE_FINGERPRINT
    for profile in profiles:
        assert isinstance(profile, dict)
        profile["tokenizer"] = "o200k_base"
    if mutate is not None:
        mutate(document)
    return load_semantic_profile_set(SyntheticProfileReader(reseal_synthetic_profile(document)))


def _counter(profile_set: SemanticProfileSet | None = None) -> ExactTokenCounter:
    return ExactTokenCounter(
        _profile_set() if profile_set is None else profile_set,
        "o200k_base",
        _RESOURCE_PATH.read_bytes(),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The Hong Kong Court of Final Appeal held that the ordinance is in force.", 15),
        ("香港終審法院裁定\uff0c該條例現正生效。", 17),
        ("香港法例 Cap. 622 第 2 條 — Companies Ordinance.", 17),
    ],
)
def test_exact_counter_matches_frozen_multilingual_o200k_base_vectors(
    text: str, expected: int
) -> None:
    """A rank, regex, or special-token drift must change one frozen legal vector."""
    assert _counter().count(text) == expected


def test_exact_counter_exposes_its_profile_bound_tokenizer_identity() -> None:
    """Promotion cannot bind a counter to an embedding profile without its exact identity."""
    assert _counter().tokenizer_id == "o200k_base"


def test_exact_counter_rejects_unknown_tokenizer_id() -> None:
    """Callers cannot substitute an alias or an unissued tokenizer catalogue entry."""
    with pytest.raises(ProfileError, match="TOKENIZER_ID_UNSUPPORTED"):
        ExactTokenCounter(_profile_set(), "cl100k_base", _RESOURCE_PATH.read_bytes())


def test_exact_counter_rejects_missing_and_mismatched_rank_resource() -> None:
    """A resource absence or one-byte change cannot silently select a cache fallback."""
    profile_set = _profile_set()
    with pytest.raises(ProfileError, match="TOKENIZER_RESOURCE_INVALID"):
        ExactTokenCounter(profile_set, "o200k_base", b"")
    with pytest.raises(ProfileError, match="TOKENIZER_RESOURCE_FINGERPRINT_MISMATCH"):
        ExactTokenCounter(profile_set, "o200k_base", _RESOURCE_PATH.read_bytes() + b"\n")


def test_exact_counter_rejects_malformed_rank_bytes_before_any_cache_fallback() -> None:
    """Malformed supplied bytes cannot trigger the upstream resolver to repair them."""
    malformed = b"not-a-tokenizer-rank\n"

    def mutate(document: dict[str, JsonValue]) -> None:
        tokenizers = document["tokenizer_specifications"]
        assert isinstance(tokenizers, list)
        assert isinstance(tokenizers[0], dict)
        tokenizers[0]["encoding_resource_fingerprint"] = (
            f"sha256:{hashlib.sha256(malformed).hexdigest()}"
        )

    with pytest.raises(ProfileError, match="TOKENIZER_RESOURCE_FINGERPRINT_MISMATCH"):
        ExactTokenCounter(_profile_set(mutate), "o200k_base", malformed)


def test_exact_counter_rejects_distribution_version_drift() -> None:
    """A resealed profile cannot claim that another installed tokenizer release is exact."""

    def mutate(document: dict[str, JsonValue]) -> None:
        tokenizers = document["tokenizer_specifications"]
        assert isinstance(tokenizers, list)
        assert isinstance(tokenizers[0], dict)
        tokenizers[0]["distribution_version"] = "0.12.1"

    with pytest.raises(ProfileError, match="TOKENIZER_DISTRIBUTION_MISMATCH"):
        _counter(_profile_set(mutate))


def test_exact_counter_rejects_same_version_installed_distribution_tree_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A repacked same-version runtime must fail before an encoding is constructed."""
    source_root = Path(tiktoken.__file__).resolve().parent
    site_packages = tmp_path / "site-packages"
    copied_root = site_packages / "tiktoken"
    shutil.copytree(source_root, copied_root)
    shutil.copytree(source_root.parent / "tiktoken_ext", site_packages / "tiktoken_ext")
    copied_core = copied_root / "core.py"
    copied_core.write_bytes(copied_core.read_bytes() + b"# repacked same-version runtime\n")
    monkeypatch.setattr(tiktoken, "__file__", str(copied_root / "__init__.py"))

    with pytest.raises(ProfileError, match="TOKENIZER_DISTRIBUTION_MISMATCH"):
        _counter()


def test_exact_counter_rejects_nonexact_text_type() -> None:
    """A string subclass cannot override text behavior during a counted request."""

    class TextSubclass(str):
        __slots__ = ()

    with pytest.raises(ProfileError, match="TOKEN_TEXT_INVALID"):
        _counter().count(TextSubclass("香港法例"))


def test_exact_counter_never_uses_tiktoken_registry_cache_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counter builds only from supplied bytes, never ambient resolver state."""
    resource = _RESOURCE_PATH.read_bytes()

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        message = "ambient resolver use"
        raise AssertionError(message)

    monkeypatch.setattr(tiktoken, "get_encoding", forbidden)
    monkeypatch.setattr(tiktoken.registry, "get_encoding", forbidden)
    monkeypatch.setattr(tiktoken.load, "read_file_cached", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    assert ExactTokenCounter(_profile_set(), "o200k_base", resource).count("香港法例") == 3
