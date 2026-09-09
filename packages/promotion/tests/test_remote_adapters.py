"""Offline tests for the real Azure OpenAI and Pinecone promotion adapters.

The transport is stubbed so the suite never leaves the machine. What is proved here
is the adapter's own behaviour: it refuses an unadmitted profile, refuses a vector
whose width does not match the profile, refuses to write or destroy without the
matching authorization, and reads back what the provider actually returned.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_promotion.builder import serving_metadata, serving_metadata_fingerprint
from asklegal_promotion.model import (
    EmbeddingProfile,
    EmbeddingRequest,
    OutcomeUnknown,
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
        self._replies = [checked_json_value(reply) for reply in replies]
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[dict[str, JsonValue]] = []

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: JsonValue | None = None,
    ) -> ProviderResponse:
        """Return the next queued reply, recording the call and what it carried."""
        del headers
        self.calls.append((method, url))
        if isinstance(body, dict):
            self.bodies.append(body)
        payload = self._replies.pop(0) if self._replies else {}
        return ProviderResponse(200, payload, "stub-request-id", 7)


class StubOperationGate:
    """Explicit test-only target authority with separate deletion control."""

    def __init__(self, *, deletion: bool = False) -> None:
        """Select whether this test authority also grants exact deletion."""
        self._deletion = deletion

    def require_write(self, operation: str) -> None:
        """Permit an exact test write."""
        del operation

    def require_delete(self, operation: str) -> None:
        """Permit deletion only in the separate deletion-authority fixture."""
        if not self._deletion:
            raise PromotionError(PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN, operation)


_WRITE_GATE = StubOperationGate()
_DELETE_GATE = StubOperationGate(deletion=True)


def _azure() -> AzureOpenAIConfig:
    return AzureOpenAIConfig("https://example.openai.azure.com", "embed-1", "2024-10-21", "k")


def _profile(
    *, provider: str = "AZURE_OPENAI", deployment_name: str = "embed-1"
) -> EmbeddingProfile:
    return EmbeddingProfile(
        profile_id="prof_1",
        profile_fingerprint="sha256:" + "0" * 64,
        provider=provider,
        resource_class="HOSTED",
        geography_class="US",
        deployment_name=deployment_name,
        model_id="text-embedding-3-small",
        model_version="1",
        api_contract="2024-10-21",
        tokenizer="cl100k_base",
        dimensions=_DIMENSIONS,
        encoding="float32",
        normalization="NONE",
        metric="cosine",
        max_input_tokens=8191,
        cost_limit_microunits=1000,
        expires_at="2027-01-01T00:00:00Z",
        allowed_environments=("POC",),
    )


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
    reply = {
        "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
        "usage": {"prompt_tokens": 3, "total_tokens": 3},
    }
    adapter = AzureOpenAIEmbeddingAdapter(_azure(), StubTransport([reply]))

    result = adapter.embed(_profile(), _request())

    assert len(result.values) == _DIMENSIONS
    assert result.receipt.input_tokens == 3
    assert result.receipt.provider_request_id == "stub-request-id"
    assert result.receipt.result == "SUCCEEDED"
    assert result.receipt.vector_fingerprint.startswith("sha256:")


def test_embedding_adapter_rejects_provider_token_accounting_drift() -> None:
    """A provider count that differs from the exact local count signals contract drift."""
    reply = {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}], "usage": {"prompt_tokens": 11}}
    adapter = AzureOpenAIEmbeddingAdapter(_azure(), StubTransport([reply]))

    with pytest.raises(PromotionError) as failure:
        adapter.embed(_profile(), _request())

    assert failure.value.code is PromotionErrorCode.PROFILE_INVALID
    assert adapter.calls == []


@pytest.mark.parametrize(
    "reply",
    [
        {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]},
        {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}], "usage": []},
        {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}], "usage": {}},
        {
            "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
            "usage": {"prompt_tokens": 3},
        },
        {
            "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
            "usage": {"prompt_tokens": 3, "total_tokens": 11},
        },
        {
            "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
            "usage": {"prompt_tokens": None, "total_tokens": 3},
        },
    ],
)
def test_embedding_adapter_requires_complete_consistent_provider_usage(
    reply: dict[str, object],
) -> None:
    """Missing, malformed, or internally contradictory accounting fails closed."""
    adapter = AzureOpenAIEmbeddingAdapter(_azure(), StubTransport([reply]))

    with pytest.raises(PromotionError) as failure:
        adapter.embed(_profile(), _request())

    assert failure.value.code is PromotionErrorCode.PROFILE_INVALID
    assert adapter.calls == []


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
    return PineconeConfig("key", "https://api.pinecone.io", _INDEX, "project-1")


@pytest.mark.parametrize("project_field", ["project_id", "project"])
def test_pinecone_credential_accepts_current_and_retained_project_field(
    project_field: str,
) -> None:
    """The retained prototype credential alias decodes to the same exact identity."""
    credential = {
        "api_key": "key",
        "control_plane_host": "https://api.pinecone.io",
        "index": _INDEX,
        project_field: "project-1",
    }
    loaded = PineconeConfig.from_credential_json(canonicalize(checked_json_value(credential)))
    assert loaded.project_id == "project-1"


def test_pinecone_credential_rejects_ambiguous_project_fields() -> None:
    """Supplying both spellings cannot silently choose one project identity."""
    credential = {
        "api_key": "key",
        "control_plane_host": "https://api.pinecone.io",
        "index": _INDEX,
        "project": "project-1",
        "project_id": "project-2",
    }
    with pytest.raises(PromotionError):
        PineconeConfig.from_credential_json(canonicalize(checked_json_value(credential)))


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
    store = PineconeServingTargetStore(_pinecone(), StubTransport([]))

    with pytest.raises(PromotionError) as error:
        store.upsert_batch(_INDEX, (_record(),))

    assert error.value.code is PromotionErrorCode.PROFILE_INVALID


def test_serving_target_refuses_any_index_other_than_the_single_admitted_replacement() -> None:
    """A project credential cannot be used to mutate a caller-chosen second index."""
    transport = StubTransport([])
    store = PineconeServingTargetStore(_pinecone(), transport, operation_gate=_WRITE_GATE)

    with pytest.raises(PromotionError) as error:
        store.upsert_batch("another-index", (_record(),))

    assert error.value.code is PromotionErrorCode.INDEX_NAME_INVALID
    assert transport.calls == []


def test_serving_target_readback_retains_the_admitted_namespace() -> None:
    """Describe must compare the same namespace that governs every vector operation."""
    transport = StubTransport([_index_listing()])
    store = PineconeServingTargetStore(_pinecone(), transport, namespace="hk-v1")

    definition = store.describe(_INDEX)

    assert definition.namespace == "hk-v1"
    assert definition.state_fingerprint == target_state_fingerprint(
        _INDEX, _DIMENSIONS, "cosine", "hk-v1"
    )


def test_serving_target_writes_when_authorized() -> None:
    """An authorized upsert resolves the data plane and posts once."""
    transport = StubTransport([_index_listing(), {"upsertedCount": 1}])
    store = PineconeServingTargetStore(_pinecone(), transport, operation_gate=_WRITE_GATE)

    store.upsert_batch(_INDEX, (_record(),))

    assert ("POST", f"{_DATA_PLANE}/vectors/upsert") in transport.calls
    assert tuple(receipt.operation for receipt in store.provider_call_receipts) == (
        "INDEX_DESCRIBE_OR_LIST",
        "VECTOR_UPSERT",
    )
    assert all(
        receipt.provider_request_id == "stub-request-id" for receipt in store.provider_call_receipts
    )
    assert all(receipt.request_units == 1 for receipt in store.provider_call_receipts)
    assert all(
        receipt.provider_reported_cost_microunits is None
        and receipt.cost_basis == "PROVIDER_BILLING_OUT_OF_BAND_CALL_CEILING"
        for receipt in store.provider_call_receipts
    )


@pytest.mark.parametrize("acknowledgement", [{}, {"upsertedCount": 0}, []])
def test_serving_target_reports_an_unknown_outcome_without_an_exact_acknowledgement(
    acknowledgement: JsonValue,
) -> None:
    """A missing, malformed, or wrong-count ack must enter exact reconciliation."""
    transport = StubTransport([_index_listing(), acknowledgement])
    store = PineconeServingTargetStore(_pinecone(), transport, operation_gate=_WRITE_GATE)

    with pytest.raises(OutcomeUnknown):
        store.upsert_batch(_INDEX, (_record(),))


def test_serving_target_refuses_to_delete_without_destructive_authorization() -> None:
    """Losing an index is not recoverable here, so writing authority is not enough."""
    store = PineconeServingTargetStore(
        _pinecone(),
        StubTransport([]),
        operation_gate=_WRITE_GATE,
    )

    with pytest.raises(PromotionError) as error:
        store.delete_exact(_INDEX, _INDEX)

    assert error.value.code is PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN


def test_serving_target_refuses_a_broad_selector() -> None:
    """A name that is not the exact target has no representation."""
    store = PineconeServingTargetStore(
        _pinecone(),
        StubTransport([]),
        operation_gate=_DELETE_GATE,
    )

    with pytest.raises(PromotionError) as error:
        store.delete_exact(_INDEX, "something-else")

    assert error.value.code is PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN


def test_serving_target_replays_an_identical_definition_without_creating() -> None:
    """Re-creating the same target must be a replay, not a collision or a write."""
    transport = StubTransport([_index_listing()])
    store = PineconeServingTargetStore(_pinecone(), transport, operation_gate=_WRITE_GATE)
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
    store = PineconeServingTargetStore(_pinecone(), transport, operation_gate=_WRITE_GATE)
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


def test_ranked_query_retains_provider_and_readback_receipt_identities() -> None:
    """The read-only query owner preserves the real response identity."""
    transport = StubTransport(
        [
            _index_listing(),
            {
                "matches": [
                    {
                        "id": "rec_1",
                        "metadata": serving_metadata(_record()),
                        "score": 0.99,
                    }
                ]
            },
        ]
    )
    store = PineconeServingTargetStore(_pinecone(), transport)

    result = store.query_with_receipt(_INDEX, (0.1, 0.2, 0.3, 0.4), 1, "query-run-1")

    assert result.request_id == "query-run-1"
    assert result.provider_request_id == "stub-request-id"
    assert result.receipt_id.startswith("qrr_")
    assert result.records[0].record_id == "rec_1"


def test_list_fetch_and_retrieval_use_the_exact_url_encoded_namespace() -> None:
    """Read-back must inspect the same namespace that received the vectors."""
    namespace = "hk v1/+?"
    transport = StubTransport(
        [
            _index_listing(),
            {"vectors": [{"id": "rec_1"}], "pagination": {}},
            {"vectors": {"rec_1": {"metadata": {}, "values": [0.1, 0.2, 0.3, 0.4]}}},
            {
                "vectors": {
                    "rec_1": {
                        "metadata": serving_metadata(_record()),
                        "values": [0.1, 0.2, 0.3, 0.4],
                    }
                }
            },
            {
                "matches": [
                    {
                        "id": "rec_1",
                        "score": 1.0,
                        "metadata": serving_metadata(_record()),
                        "values": [0.1, 0.2, 0.3, 0.4],
                    }
                ]
            },
        ]
    )
    store = PineconeServingTargetStore(_pinecone(), transport, namespace=namespace)

    store.enumerate(_INDEX)
    store.verify_queries(_INDEX, ("rec_1",))

    encoded = "hk%20v1%2F%2B%3F"
    assert (
        "GET",
        f"{_DATA_PLANE}/vectors/list?namespace={encoded}&limit=100",
    ) in transport.calls
    fetches = [url for method, url in transport.calls if method == "GET" and "/fetch?" in url]
    assert fetches == [
        f"{_DATA_PLANE}/vectors/fetch?namespace={encoded}&ids=rec_1",
        f"{_DATA_PLANE}/vectors/fetch?namespace={encoded}&ids=rec_1",
    ]
    assert transport.calls[-1] == ("POST", f"{_DATA_PLANE}/query")
    assert transport.bodies[-1] == (
        {
            "filter": {"text": {"$eq": "text"}},
            "includeMetadata": True,
            "includeValues": True,
            "namespace": namespace,
            "topK": 1,
            "vector": [0.1, 0.2, 0.3, 0.4],
        }
    )


def test_the_whole_six_field_payload_reaches_the_target() -> None:
    """Every contract field must be written, and nothing outside the closed set.

    This is the defect this test exists for: the write once carried `text` and
    `content_fingerprint` only, so `authority_note` never reached the index and a
    reconstructed provision came back looking like the published text.
    """
    transport = StubTransport([_index_listing(), {"upsertedCount": 1}])
    store = PineconeServingTargetStore(_pinecone(), transport, operation_gate=_WRITE_GATE)

    store.upsert_batch(_INDEX, (_record(),))

    vectors = transport.bodies[-1]["vectors"]
    assert isinstance(vectors, list)
    first = vectors[0]
    assert isinstance(first, dict)
    written = first["metadata"]
    assert isinstance(written, dict)
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
    store = PineconeServingTargetStore(_pinecone(), transport, operation_gate=_WRITE_GATE)

    with pytest.raises(PromotionError) as error:
        store.upsert_batch(_INDEX, (_record(authority_note=""),))

    assert error.value.code is PromotionErrorCode.SERVING_PAYLOAD_INVALID
    assert "authority_note" in error.value.detail


def test_a_payload_that_does_not_match_its_fingerprint_is_refused() -> None:
    """The bytes written must be the bytes that were approved."""
    transport = StubTransport([_index_listing(), {"upsertedCount": 1}])
    store = PineconeServingTargetStore(_pinecone(), transport, operation_gate=_WRITE_GATE)
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
    store = PineconeServingTargetStore(_pinecone(), transport, operation_gate=_WRITE_GATE)
    unfingerprinted = replace(_record(), content_fingerprint="")

    with pytest.raises(PromotionError) as error:
        store.upsert_batch(_INDEX, (unfingerprinted,))

    assert error.value.code is PromotionErrorCode.SERVING_PAYLOAD_INVALID
    assert "nothing" in error.value.detail
