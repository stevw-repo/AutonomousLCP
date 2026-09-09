"""Focused live retrieval owner-receipt tests."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import cast

import pytest
from _v1_serving_profile_fixture import exact_serving_profile
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_promotion import (
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingReceipt,
    EmbeddingRequest,
    LiveRetrievalCase,
    LiveRetrievalEvaluationError,
    LiveRetrievalQueryResult,
    LiveRetrievedRecord,
    live_query_result_fingerprint,
    parse_live_retrieval_evaluation,
    query_readback_receipt_id,
    retrieval_setup_request_id,
    run_live_retrieval_evaluation,
    target_state_fingerprint,
)

_PROPOSAL = "sha256:" + "1" * 64
_SUITE = "sha256:" + "2" * 64
_SUITE_CASE = "sha256:" + "3" * 64


class _Embeddings:
    def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> EmbeddedVector:
        dimensions = profile.dimensions
        values = tuple(0.25 for _ in range(dimensions))
        return EmbeddedVector(
            values,
            EmbeddingReceipt(
                "emc_" + sha256(request.request_id.encode()).hexdigest()[:48],
                request.request_id,
                "azure-" + request.request_id,
                dimensions,
                "sha256:" + sha256(b"vector").hexdigest(),
                request.token_count,
                12,
                "SUCCEEDED",
            ),
        )


class _Target:
    def query_with_receipt(
        self, name: str, vector: tuple[float, ...], top_k: int, request_id: str
    ) -> LiveRetrievalQueryResult:
        assert name
        assert vector
        assert top_k == 2
        records = (
            LiveRetrievedRecord(
                "case-record-1",
                0.99,
                "Article text",
                "Hong Kong",
                "Hong Kong",
                "legislation",
                "HKeL",
                "current at cutoff",
            ),
            LiveRetrievedRecord(
                "case-record-2",
                0.75,
                "Judgment text",
                "Hong Kong",
                "Hong Kong",
                "case",
                "Judiciary",
                "binding court",
            ),
        )
        result_fingerprint = live_query_result_fingerprint(records)
        provider_request_id = "pinecone-" + request_id
        return LiveRetrievalQueryResult(
            records,
            request_id,
            provider_request_id,
            query_readback_receipt_id(request_id, provider_request_id, result_fingerprint),
            result_fingerprint,
        )


def _receipt() -> bytes:
    serving = exact_serving_profile()
    target_name = "asklegal-v1-hk-local-20260908t120000"
    target_fingerprint = target_state_fingerprint(
        target_name, serving.dimensions, serving.metric, serving.namespace
    )
    request = EmbeddingRequest(
        "retrieval-eval-request",
        "retrieval-query",
        "sha256:" + "2" * 64,
        "Hong Kong ordinance amendment",
        "sha256:" + "3" * 64,
        4,
        serving.embedding.profile_id,
        "evaluation-batch",
        0,
        "evaluation-cache-key",
    )
    setup_request = retrieval_setup_request_id("provider-run-1", "legislation-en")
    setup_inventory = [
        {
            "payload_fingerprint": "sha256:" + "8" * 64,
            "record_id": "case-record-1",
            "vector_fingerprint": "sha256:" + "9" * 64,
        }
    ]
    target_setup: dict[str, object] = {
        "readback_inventory_fingerprint": "sha256:"
        + sha256(canonicalize(checked_json_value(setup_inventory))).hexdigest(),
        "record_count": 1,
        "records": [
            {
                "case_id": "legislation-en",
                "embedding_receipt": {
                    "dimensions": 4,
                    "input_tokens": 4,
                    "latency_milliseconds": 3,
                    "provider_request_id": "azure-setup-1",
                    "receipt_id": "emc_setup_1",
                    "request_id": setup_request,
                    "result": "SUCCEEDED",
                    "vector_fingerprint": "sha256:" + "9" * 64,
                },
                "payload_fingerprint": "sha256:" + "8" * 64,
                "record_id": "case-record-1",
            }
        ],
        **_setup_envelope(serving.namespace),
        "target_fingerprint": target_fingerprint,
        "target_name": target_name,
    }
    target_setup["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(target_setup))).hexdigest()
    )
    return run_live_retrieval_evaluation(
        run_id="provider-run-1",
        observation_cutoff="2026-09-08T12:00:00+08:00",
        proposal_fingerprint=_PROPOSAL,
        serving_profile_fingerprint=serving.fingerprint,
        suite_fingerprint=_SUITE,
        target_name=target_name,
        target_fingerprint=target_fingerprint,
        target_setup=target_setup,  # pyright: ignore[reportArgumentType]
        profile=serving.embedding,
        cases=(LiveRetrievalCase("legislation-en", request, ("case-record-1",), 2, _SUITE_CASE),),
        embeddings=_Embeddings(),
        target=_Target(),
    )


def test_actual_embedding_and_ranked_query_issue_passed_receipt() -> None:
    """Actual injected embedding and target calls produce one passed receipt."""
    receipt = parse_live_retrieval_evaluation(_receipt())
    assert receipt.result == "PASSED"
    assert receipt.run_id == "provider-run-1"
    assert receipt.case_count == 1


def test_retrieval_receipt_rejects_expected_record_removed_from_results() -> None:
    """The parser rederives expected membership instead of trusting PASSED."""
    document = cast("dict[str, object]", json.loads(_receipt()))
    case = cast("dict[str, object]", cast("list[object]", document["cases"])[0])
    case["expected_record_ids"] = ["not-returned"]
    forged = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(LiveRetrievalEvaluationError):
        parse_live_retrieval_evaluation(forged)


def _setup_envelope(namespace: str) -> dict[str, object]:
    return {
        "initial_namespace_record_count": 0,
        "pinecone_data_plane_host": "https://testing-index-1.example.pinecone.io",
        "pinecone_project_id": "project-1",
        "run_id": "provider-run-1",
        "setup_mode": "CREATE_FRESH",
        "setup_owner_run_id": "provider-run-1",
        "source_target_setup_fingerprint": None,
        "target_namespace": namespace,
    }
