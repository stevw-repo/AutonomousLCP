"""Offline tests for the real Azure OpenAI and Pinecone promotion adapters.

The transport is stubbed so the suite never leaves the machine. What is proved here
is the adapter's own behaviour: it refuses an unadmitted profile, refuses a vector
whose width does not match the profile, refuses to write or destroy without the
matching authorization, and reads back what the provider actually returned.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from asklegal_promotion.builder import serving_metadata, serving_metadata_fingerprint
from asklegal_promotion.model import (
    EmbeddingProfile,
    EmbeddingRequest,
    PromotionError,
    PromotionErrorCode,
    TargetDefinition,
    TargetRecord,
)
from asklegal_promotion.remote import (
    AzureOpenAIConfig,
    AzureOpenAIEmbeddingAdapter,
    PineconeConfig,
    PineconeServingTargetStore,
    ProviderResponse,
    target_state_fingerprint,
)

_DIMENSIONS = 4
_INDEX = "testing-index-1"
_DATA_PLANE = "https://testing-index-1-abc.svc.example.pinecone.io"


class StubTransport:
    """Records every call and replays queued replies in order."""

    def __init__(self, replies: list[object]) -> None:
        """Queue the replies this transport will return."""
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[dict[str, object]] = []

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: object | None = None,
    ) -> ProviderResponse:
        """Return the next queued reply, recording the call and what it carried."""
        del headers
        self.calls.append((method, url))
        if isinstance(body, dict):
            self.bodies.append(body)
        payload = self._replies.pop(0) if self._replies else {}
        return ProviderResponse(200, payload, "stub-request-id", 7)


def _azure() -> AzureOpenAIConfig:
    return AzureOpenAIConfig("https://example.openai.azure.com", "embed-1", "2024-10-21", "k")


def _profile(**overrides: object) -> EmbeddingProfile:
    base = {
        "profile_id": "prof_1",
        "profile_fingerprint": "sha256:" + "0" * 64,
        "provider": "AZURE_OPENAI",
        "resource_class": "HOSTED",
        "geography_class": "US",
        "deployment_name": "embed-1",
        "model_id": "text-embedding-3-small",
        "model_version": "1",
        "api_contract": "2024-10-21",
        "tokenizer": "cl100k_base",
        "dimensions": _DIMENSIONS,
        "encoding": "float32",
        "normalization": "NONE",
        "metric": "cosine",
        "max_input_tokens": 8191,
        "cost_limit_microunits": 1000,
        "expires_at": "2027-01-01T00:00:00Z",
        "allowed_environments": ("POC",),
    }
    return EmbeddingProfile(**{**base, **overrides})


def _request() -> EmbeddingRequest:
    return EmbeddingRequest(
        request_id="req_1",
        record_id="rec_1",
        serving_payload_fingerprint="sha256:" + "1" * 64,
        text="text",
        text_fingerprint="sha256:" + "2" * 64,
        token_count=3,
        profile_id="prof_1",
        batch_id="batch_1",
        batch_position=0,
        cache_key="ck_1",
    )


def test_embedding_adapter_returns_the_provider_vector_and_its_accounting() -> None:
    """A well-formed reply becomes an exact vector plus a redacted receipt."""
    reply = {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}], "usage": {"prompt_tokens": 11}}
    adapter = AzureOpenAIEmbeddingAdapter(_azure(), StubTransport([reply]))

    result = adapter.embed(_profile(), _request())

    assert len(result.values) == _DIMENSIONS
    assert result.receipt.input_tokens == 11
    assert result.receipt.provider_request_id == "stub-request-id"
    assert result.receipt.result == "SUCCEEDED"
    assert result.receipt.vector_fingerprint.startswith("sha256:")


def test_embedding_adapter_refuses_a_provider_the_profile_does_not_admit() -> None:
    """A profile naming another provider must never reach Azure."""
    adapter = AzureOpenAIEmbeddingAdapter(_azure(), StubTransport([]))

    with pytest.raises(PromotionError) as error:
        adapter.embed(_profile(provider="LOCAL_FAKE"), _request())

    assert error.value.code is PromotionErrorCode.PROFILE_INVALID


def test_embedding_adapter_refuses_a_deployment_the_credential_does_not_match() -> None:
    """A profile and credential that disagree would silently embed with the wrong model."""
    adapter = AzureOpenAIEmbeddingAdapter(_azure(), StubTransport([]))

    with pytest.raises(PromotionError) as error:
        adapter.embed(_profile(deployment_name="other-deployment"), _request())

    assert error.value.code is PromotionErrorCode.PROFILE_INVALID


def test_embedding_adapter_refuses_a_vector_of_the_wrong_width() -> None:
    """A dimension mismatch fails here, not later at upsert time."""
    reply = {"data": [{"embedding": [0.1, 0.2]}]}
    adapter = AzureOpenAIEmbeddingAdapter(_azure(), StubTransport([reply]))

    with pytest.raises(PromotionError) as error:
        adapter.embed(_profile(), _request())

    assert error.value.code is PromotionErrorCode.VECTOR_INVALID


def _pinecone() -> PineconeConfig:
    return PineconeConfig("key", "https://api.pinecone.io", _INDEX)


def _index_listing() -> dict[str, object]:
    return {
        "indexes": [
            {
                "name": _INDEX,
                "dimension": _DIMENSIONS,
                "metric": "cosine",
                "host": _DATA_PLANE.removeprefix("https://"),
            }
        ]
    }


def _record(**overrides: str) -> TargetRecord:
    fields = {
        "metadata_text": "text",
        "country": "HK",
        "jurisdiction": "HKSAR",
        "material_type": "ORDINANCE",
        "source": "HKEL",
        "authority_note": "WARNING: reconstructed, not the published consolidation",
    }
    fields.update(overrides)
    record = TargetRecord("rec_1", "", (0.1, 0.2, 0.3, 0.4), **fields)
    if not all(fields.values()):
        return record
    fingerprint = serving_metadata_fingerprint(serving_metadata(record))
    return replace(record, content_fingerprint=fingerprint)


def test_serving_target_refuses_to_write_without_authorization() -> None:
    """An unauthorized upsert must not reach a real index."""
    store = PineconeServingTargetStore(_pinecone(), StubTransport([]), write_authorized=False)

    with pytest.raises(PromotionError) as error:
        store.upsert_batch(_INDEX, (_record(),))

    assert error.value.code is PromotionErrorCode.PROFILE_INVALID


def test_serving_target_writes_when_authorized() -> None:
    """An authorized upsert resolves the data plane and posts once."""
    transport = StubTransport([_index_listing(), {"upsertedCount": 1}])
    store = PineconeServingTargetStore(_pinecone(), transport, write_authorized=True)

    store.upsert_batch(_INDEX, (_record(),))

    assert ("POST", f"{_DATA_PLANE}/vectors/upsert") in transport.calls


def test_serving_target_refuses_to_delete_without_destructive_authorization() -> None:
    """Losing an index is not recoverable here, so writing authority is not enough."""
    store = PineconeServingTargetStore(
        _pinecone(),
        StubTransport([]),
        write_authorized=True,
        destructive_authorized=False,
    )

    with pytest.raises(PromotionError) as error:
        store.delete_exact(_INDEX, _INDEX)

    assert error.value.code is PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN


def test_serving_target_refuses_a_broad_selector() -> None:
    """A name that is not the exact target has no representation."""
    store = PineconeServingTargetStore(
        _pinecone(),
        StubTransport([]),
        write_authorized=True,
        destructive_authorized=True,
    )

    with pytest.raises(PromotionError) as error:
        store.delete_exact(_INDEX, "something-else")

    assert error.value.code is PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN


def test_serving_target_replays_an_identical_definition_without_creating() -> None:
    """Re-creating the same target must be a replay, not a collision or a write."""
    transport = StubTransport([_index_listing()])
    store = PineconeServingTargetStore(_pinecone(), transport, write_authorized=True)
    definition = TargetDefinition(
        _INDEX,
        target_state_fingerprint(_INDEX, _DIMENSIONS, "cosine", ""),
        _DIMENSIONS,
        "cosine",
        "",
    )

    store.create(definition)

    assert all(method != "POST" for method, _ in transport.calls)


def test_serving_target_reports_a_configuration_collision() -> None:
    """An existing index with different geometry must not be silently reused."""
    transport = StubTransport([_index_listing()])
    store = PineconeServingTargetStore(_pinecone(), transport, write_authorized=True)
    definition = TargetDefinition(
        _INDEX,
        target_state_fingerprint(_INDEX, 8, "dotproduct", ""),
        8,
        "dotproduct",
        "",
    )

    with pytest.raises(PromotionError) as error:
        store.create(definition)

    assert error.value.code is PromotionErrorCode.TARGET_COLLISION


def test_retrieval_gate_fails_when_an_expected_record_is_missing() -> None:
    """The gate must fail when the target cannot return what was promoted."""
    transport = StubTransport([_index_listing(), {"vectors": {}}])
    store = PineconeServingTargetStore(_pinecone(), transport)

    with pytest.raises(PromotionError) as error:
        store.verify_queries(_INDEX, ("rec_1",))

    assert error.value.code is PromotionErrorCode.RETRIEVAL_GATE_FAILED


def test_the_whole_six_field_payload_reaches_the_target() -> None:
    """Every contract field must be written, and nothing outside the closed set.

    This is the defect this test exists for: the write once carried `text` and
    `content_fingerprint` only, so `authority_note` never reached the index and a
    reconstructed provision came back looking like the published text.
    """
    transport = StubTransport([_index_listing(), {"upsertedCount": 1}])
    store = PineconeServingTargetStore(_pinecone(), transport, write_authorized=True)

    store.upsert_batch(_INDEX, (_record(),))

    written = transport.bodies[-1]["vectors"][0]["metadata"]
    assert set(written) == {
        "authority_note",
        "country",
        "jurisdiction",
        "source",
        "text",
        "type",
    }
    assert written["authority_note"] == "WARNING: reconstructed, not the published consolidation"
    assert "content_fingerprint" not in written


def test_a_record_missing_its_authority_note_is_refused() -> None:
    """A warning that is absent must stop the write, not travel as an empty string."""
    transport = StubTransport([_index_listing(), {"upsertedCount": 1}])
    store = PineconeServingTargetStore(_pinecone(), transport, write_authorized=True)

    with pytest.raises(PromotionError) as error:
        store.upsert_batch(_INDEX, (_record(authority_note=""),))

    assert error.value.code is PromotionErrorCode.SERVING_PAYLOAD_INVALID
    assert "authority_note" in error.value.detail


def test_a_payload_that_does_not_match_its_fingerprint_is_refused() -> None:
    """The bytes written must be the bytes that were approved."""
    transport = StubTransport([_index_listing(), {"upsertedCount": 1}])
    store = PineconeServingTargetStore(_pinecone(), transport, write_authorized=True)
    tampered = replace(_record(), metadata_text="something else entirely")

    with pytest.raises(PromotionError) as error:
        store.upsert_batch(_INDEX, (tampered,))

    assert error.value.code is PromotionErrorCode.SERVING_PAYLOAD_INVALID


def test_reading_back_returns_all_six_fields_and_derives_the_fingerprint() -> None:
    """What the target holds must round-trip, fingerprint included."""
    stored = serving_metadata(_record())
    transport = StubTransport(
        [
            _index_listing(),
            {"vectors": [{"id": "rec_1"}], "pagination": {}},
            {"vectors": {"rec_1": {"values": [0.1, 0.2, 0.3, 0.4], "metadata": stored}}},
        ]
    )
    store = PineconeServingTargetStore(_pinecone(), transport)

    read_back = store.enumerate(_INDEX)

    assert len(read_back) == 1
    assert read_back[0] == _record()


def test_a_legacy_record_without_the_payload_reports_no_fingerprint() -> None:
    """Records written before the fix must reconcile as wrong, not as unknown-but-fine."""
    transport = StubTransport(
        [
            _index_listing(),
            {"vectors": [{"id": "rec_1"}], "pagination": {}},
            {"vectors": {"rec_1": {"values": [0.1], "metadata": {"text": "text"}}}},
        ]
    )
    store = PineconeServingTargetStore(_pinecone(), transport)

    read_back = store.enumerate(_INDEX)

    assert read_back[0].content_fingerprint == ""
    assert read_back[0].authority_note == ""


def test_a_record_carrying_no_fingerprint_at_all_is_refused() -> None:
    """An unfingerprinted record cannot be shown to be the one that was approved."""
    transport = StubTransport([_index_listing(), {"upsertedCount": 1}])
    store = PineconeServingTargetStore(_pinecone(), transport, write_authorized=True)
    unfingerprinted = replace(_record(), content_fingerprint="")

    with pytest.raises(PromotionError) as error:
        store.upsert_batch(_INDEX, (unfingerprinted,))

    assert error.value.code is PromotionErrorCode.SERVING_PAYLOAD_INVALID
    assert "nothing" in error.value.detail
