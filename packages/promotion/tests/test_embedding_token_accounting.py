"""Exact token-accounting tests for embedding request construction."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from asklegal_promotion import (
    EmbeddingProfileInput,
    EmbeddingRequestInput,
    PromotionError,
    PromotionErrorCode,
    embedding_request,
    freeze_embedding_profile,
)


@dataclass(frozen=True, slots=True)
class _LiteralCounter:
    """Small exact test tokenizer whose result is independent of UTF-8 length."""

    tokenizer_id: str = "o200k_base"

    def count(self, text: str) -> int:
        assert text == "香港法例"
        return 3


@dataclass(frozen=True, slots=True)
class _ConfiguredCounter:
    tokenizer_id: str
    result: int

    def count(self, text: str) -> int:
        del text
        return self.result


def _profile():
    return freeze_embedding_profile(
        EmbeddingProfileInput(
            "LOCAL_FAKE",
            "LOCAL_ONLY",
            "LOCAL_ONLY",
            "synthetic-embedding",
            "synthetic-model",
            "1.0.0",
            "local-v1",
            "o200k_base",
            4,
            "FLOAT32",
            "NONE",
            "COSINE",
            10,
            100,
            "2027-01-01T00:00:00Z",
            ("dev",),
        )
    )


def test_embedding_request_uses_exact_tokens_instead_of_utf8_byte_length() -> None:
    """Reintroducing UTF-8 byte length would report 12 instead of three tokens."""
    request = embedding_request(
        EmbeddingRequestInput(
            "rec_" + "1" * 48,
            "sha256:" + "2" * 64,
            "香港法例",
            "art_" + "3" * 48,
            0,
        ),
        _profile(),
        _LiteralCounter(),
    )

    assert request.token_count == 3


def _request_with(counter: _ConfiguredCounter):
    return embedding_request(
        EmbeddingRequestInput(
            "rec_" + "1" * 48,
            "sha256:" + "2" * 64,
            "香港法例",
            "art_" + "3" * 48,
            0,
        ),
        _profile(),
        counter,
    )


def test_embedding_request_rejects_counter_for_another_tokenizer() -> None:
    """A numerically plausible count from another tokenizer cannot satisfy the profile."""
    with pytest.raises(PromotionError) as failure:
        _request_with(_ConfiguredCounter("cl100k_base", 3))
    assert failure.value.code is PromotionErrorCode.PROFILE_INVALID


@pytest.mark.parametrize("count", [True, 0, 11])
def test_embedding_request_rejects_noncanonical_or_oversized_counts(count: int) -> None:
    """Boolean, empty, and over-profile counts fail before a provider request exists."""
    with pytest.raises(PromotionError) as failure:
        _request_with(_ConfiguredCounter("o200k_base", count))
    assert failure.value.code is PromotionErrorCode.VECTOR_INVALID
