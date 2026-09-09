"""Live retrieval evaluation over the configured embedding and query ports."""

from __future__ import annotations

import re
import struct
from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Never, Protocol, cast

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .builder import serving_metadata_fingerprint, verify_embedding_profile
from .model import EmbeddingProfile, EmbeddingRequest
from .ports import EmbeddingPort

_SCHEMA = "asklegal.hk-v1-live-retrieval-evaluation/v1"
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CUTOFF = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00\Z")
_MAX_BYTES = 8_000_000
_MAX_TOP_K = 100
_ERROR = "LIVE_RETRIEVAL_EVALUATION_INVALID"
_QUERY_RECEIPT = re.compile(r"qrr_[0-9a-f]{48}\Z")


class LiveRetrievalEvaluationError(ValueError):
    """One invalid live retrieval evaluation or receipt."""


def _fail() -> Never:
    raise LiveRetrievalEvaluationError(_ERROR)


def _full_fingerprint(value: object) -> bool:
    return type(value) is str and _FINGERPRINT.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class LiveRetrievedRecord:
    """One actual ranked query result with its six exact serving fields."""

    record_id: str
    score: float
    text: str
    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str


class LiveRetrievalQueryPort(Protocol):
    """Read-only query surface implemented by the real serving target adapter."""

    def query_with_receipt(
        self, name: str, vector: tuple[float, ...], top_k: int, request_id: str
    ) -> LiveRetrievalQueryResult:
        """Return ranked results and the actual target readback receipt."""
        ...


@dataclass(frozen=True, slots=True)
class LiveRetrievalCase:
    """One actual query plus independently selected expected record identities."""

    case_id: str
    request: EmbeddingRequest
    expected_record_ids: tuple[str, ...]
    top_k: int
    suite_case_fingerprint: str


@dataclass(frozen=True, slots=True)
class LiveRetrievalQueryResult:
    """One actual target response with safe provider and readback identities."""

    records: tuple[LiveRetrievedRecord, ...]
    request_id: str
    provider_request_id: str
    receipt_id: str
    result_fingerprint: str


@dataclass(frozen=True, slots=True)
class LiveRetrievalEvaluationReceipt:
    """Parsed passed retrieval receipt bound to one target and V1 lineage."""

    run_id: str
    observation_cutoff: str
    proposal_fingerprint: str
    embedding_profile_fingerprint: str
    serving_profile_fingerprint: str
    suite_fingerprint: str
    target_name: str
    target_fingerprint: str
    case_count: int
    fingerprint: str
    result: str = "PASSED"


def _payload_fingerprint(record: LiveRetrievedRecord) -> str:
    return serving_metadata_fingerprint(
        {
            "authority_note": record.authority_note,
            "country": record.country,
            "jurisdiction": record.jurisdiction,
            "source": record.source,
            "text": record.text,
            "type": record.material_type,
        }
    )


def retrieval_embedding_request_id(run_id: str, case_id: str) -> str:
    """Derive one run-bound embedding request identity."""
    return "rer_" + sha256(f"{run_id}\x1f{case_id}\x1fEMBED".encode()).hexdigest()[:48]


def retrieval_query_request_id(run_id: str, case_id: str) -> str:
    """Derive one run-bound target-query request identity."""
    return "rqr_" + sha256(f"{run_id}\x1f{case_id}\x1fQUERY".encode()).hexdigest()[:48]


def retrieval_setup_request_id(run_id: str, case_id: str) -> str:
    """Derive one run-bound golden-record embedding request identity."""
    return "rsr_" + sha256(f"{run_id}\x1f{case_id}\x1fSETUP".encode()).hexdigest()[:48]


def live_query_result_fingerprint(records: tuple[LiveRetrievedRecord, ...]) -> str:
    """Fingerprint the exact ranked result projection returned by the target."""
    projection = [
        {
            "payload_fingerprint": _payload_fingerprint(record),
            "record_id": record.record_id,
            "score": record.score,
        }
        for record in records
    ]
    return "sha256:" + sha256(canonicalize(checked_json_value(projection))).hexdigest()


def live_vector_fingerprint(values: tuple[float, ...]) -> str:
    """Fingerprint exact float32 provider vector bytes for setup readback."""
    return "sha256:" + sha256(b"".join(struct.pack("!f", value) for value in values)).hexdigest()


def query_readback_receipt_id(
    request_id: str, provider_request_id: str, result_fingerprint: str
) -> str:
    """Derive the immutable safe identity of one actual target readback."""
    material = f"{request_id}\x1f{provider_request_id}\x1f{result_fingerprint}".encode()
    return "qrr_" + sha256(material).hexdigest()[:48]


def run_live_retrieval_evaluation(  # noqa: PLR0913 - exact evaluation lineage.
    *,
    run_id: str,
    observation_cutoff: str,
    proposal_fingerprint: str,
    serving_profile_fingerprint: str,
    suite_fingerprint: str,
    target_name: str,
    target_fingerprint: str,
    target_setup: dict[str, JsonValue],
    profile: EmbeddingProfile,
    cases: tuple[LiveRetrievalCase, ...],
    embeddings: EmbeddingPort,
    target: LiveRetrievalQueryPort,
    provider_call_reader: Callable[[], tuple[dict[str, JsonValue], ...]] | None = None,
) -> bytes:
    """Run actual embeddings and ranked target queries; emit only if every case passes."""
    try:
        verify_embedding_profile(profile)
    except Exception as error:
        raise LiveRetrievalEvaluationError(_ERROR) from error
    if (
        type(run_id) is not str
        or not run_id
        or _CUTOFF.fullmatch(observation_cutoff) is None
        or any(
            _FINGERPRINT.fullmatch(value) is None
            for value in (
                proposal_fingerprint,
                serving_profile_fingerprint,
                target_fingerprint,
                profile.profile_fingerprint,
            )
        )
        or not target_name
        or _FINGERPRINT.fullmatch(suite_fingerprint) is None
        or not cases
        or len({case.case_id for case in cases}) != len(cases)
    ):
        _fail()
    results: list[dict[str, JsonValue]] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        if (
            not case.case_id
            or not case.expected_record_ids
            or len(set(case.expected_record_ids)) != len(case.expected_record_ids)
            or type(case.top_k) is not int
            or not 1 <= case.top_k <= _MAX_TOP_K
            or case.request.profile_id != profile.profile_id
            or _FINGERPRINT.fullmatch(case.suite_case_fingerprint) is None
        ):
            _fail()
        request = replace(
            case.request,
            request_id=retrieval_embedding_request_id(run_id, case.case_id),
        )
        embedded = embeddings.embed(profile, request)
        if (
            embedded.receipt.request_id != request.request_id
            or embedded.receipt.result != "SUCCEEDED"
            or embedded.receipt.dimensions != profile.dimensions
            or len(embedded.values) != profile.dimensions
            or not embedded.receipt.provider_request_id
            or embedded.receipt.provider_request_id == "unreported"
            or not embedded.receipt.receipt_id
        ):
            _fail()
        query_request_id = retrieval_query_request_id(run_id, case.case_id)
        query = target.query_with_receipt(
            target_name, embedded.values, case.top_k, query_request_id
        )
        returned = query.records
        returned_ids = tuple(item.record_id for item in returned)
        if (
            not returned
            or len(returned) > case.top_k
            or len(set(returned_ids)) != len(returned_ids)
            or not set(case.expected_record_ids).issubset(returned_ids)
            or any(not item.record_id for item in returned)
            or query.request_id != query_request_id
            or not query.provider_request_id
            or query.provider_request_id == "unreported"
            or query.result_fingerprint != live_query_result_fingerprint(returned)
            or query.receipt_id
            != query_readback_receipt_id(
                query_request_id, query.provider_request_id, query.result_fingerprint
            )
        ):
            _fail()
        results.append(
            {
                "case_id": case.case_id,
                "embedding_receipt": {
                    "dimensions": embedded.receipt.dimensions,
                    "input_tokens": embedded.receipt.input_tokens,
                    "latency_milliseconds": embedded.receipt.latency_milliseconds,
                    "provider_request_id": embedded.receipt.provider_request_id,
                    "receipt_id": embedded.receipt.receipt_id,
                    "request_id": embedded.receipt.request_id,
                    "result": embedded.receipt.result,
                    "vector_fingerprint": embedded.receipt.vector_fingerprint,
                },
                "expected_record_ids": list(case.expected_record_ids),
                "query_receipt": {
                    "provider_request_id": query.provider_request_id,
                    "receipt_id": query.receipt_id,
                    "request_id": query.request_id,
                    "result": "SUCCEEDED",
                    "result_fingerprint": query.result_fingerprint,
                },
                "query_request_fingerprint": request.text_fingerprint,
                "returned": [
                    {
                        "payload_fingerprint": _payload_fingerprint(item),
                        "record_id": item.record_id,
                        "score": item.score,
                    }
                    for item in returned
                ],
                "top_k": case.top_k,
                "suite_case_fingerprint": case.suite_case_fingerprint,
            }
        )
    document: dict[str, object] = {
        "cases": results,
        "embedding_profile_fingerprint": profile.profile_fingerprint,
        "observation_cutoff": observation_cutoff,
        "proposal_fingerprint": proposal_fingerprint,
        "result": "PASSED",
        "run_id": run_id,
        "schema_id": _SCHEMA,
        "serving_profile_fingerprint": serving_profile_fingerprint,
        "suite_fingerprint": suite_fingerprint,
        "target_setup": target_setup,
        "target_fingerprint": target_fingerprint,
        "target_name": target_name,
        "target_provider_calls": (
            list(provider_call_reader()) if provider_call_reader is not None else []
        ),
    }
    unsigned = canonicalize(checked_json_value(document))
    document["fingerprint"] = "sha256:" + sha256(unsigned).hexdigest()
    raw = canonicalize(checked_json_value(document))
    parse_live_retrieval_evaluation(raw)
    return raw


def parse_live_retrieval_evaluation(  # noqa: C901, PLR0912, PLR0915 - closed receipt grammar.
    raw: bytes,
) -> LiveRetrievalEvaluationReceipt:
    """Strictly rederive one passed live retrieval receipt and all result accounting."""
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX_BYTES)
    except ValueError:
        _fail()
    if type(value) is not dict:
        _fail()
    document = cast("dict[str, object]", value)
    if set(document) != {
        "cases",
        "embedding_profile_fingerprint",
        "fingerprint",
        "observation_cutoff",
        "proposal_fingerprint",
        "result",
        "run_id",
        "schema_id",
        "serving_profile_fingerprint",
        "suite_fingerprint",
        "target_fingerprint",
        "target_name",
        "target_provider_calls",
        "target_setup",
    }:
        _fail()
    unsigned = {key: item for key, item in document.items() if key != "fingerprint"}
    fingerprints = tuple(
        document.get(key)
        for key in (
            "embedding_profile_fingerprint",
            "proposal_fingerprint",
            "serving_profile_fingerprint",
            "suite_fingerprint",
            "target_fingerprint",
        )
    )
    cases = document.get("cases")
    target_setup = document.get("target_setup")
    target_provider_calls = document.get("target_provider_calls")
    if (
        canonicalize(value) != raw
        or document.get("schema_id") != _SCHEMA
        or document.get("result") != "PASSED"
        or type(document.get("run_id")) is not str
        or not document["run_id"]
        or type(document.get("observation_cutoff")) is not str
        or _CUTOFF.fullmatch(cast("str", document["observation_cutoff"])) is None
        or type(document.get("target_name")) is not str
        or not document["target_name"]
        or any(
            type(item) is not str or _FINGERPRINT.fullmatch(item) is None for item in fingerprints
        )
        or document.get("fingerprint")
        != "sha256:" + sha256(canonicalize(checked_json_value(unsigned))).hexdigest()
        or type(cases) is not list
        or not cases
        or type(target_setup) is not dict
        or type(target_provider_calls) is not list
        or any(type(item) is not dict for item in cast("list[object]", target_provider_calls))
    ):
        _fail()
    setup = cast("dict[str, object]", target_setup)
    setup_records = setup.get("records")
    if (
        set(setup)
        != {
            "fingerprint",
            "readback_inventory_fingerprint",
            "record_count",
            "records",
            "run_id",
            "target_fingerprint",
            "target_name",
        }
        or setup.get("run_id") != document.get("run_id")
        or setup.get("target_name") != document.get("target_name")
        or setup.get("target_fingerprint") != document.get("target_fingerprint")
        or type(setup_records) is not list
        or not setup_records
        or setup.get("record_count") != len(cast("list[JsonValue]", setup_records))
        or setup.get("fingerprint")
        != "sha256:"
        + sha256(
            canonicalize(
                checked_json_value(
                    {key: value for key, value in setup.items() if key != "fingerprint"}
                )
            )
        ).hexdigest()
    ):
        _fail()
    setup_ids: list[str] = []
    setup_inventory: list[dict[str, object]] = []
    for raw_setup_record in cast("list[object]", setup_records):
        if type(raw_setup_record) is not dict:
            _fail()
        setup_record = cast("dict[str, object]", raw_setup_record)
        if set(setup_record) != {
            "case_id",
            "embedding_receipt",
            "payload_fingerprint",
            "record_id",
        }:
            _fail()
        setup_receipt = setup_record.get("embedding_receipt")
        if type(setup_receipt) is not dict:
            _fail()
        retained = cast("dict[str, object]", setup_receipt)
        case_id = setup_record.get("case_id")
        record_id = setup_record.get("record_id")
        if (
            type(case_id) is not str
            or not case_id
            or type(record_id) is not str
            or not record_id
            or not _full_fingerprint(setup_record.get("payload_fingerprint"))
            or set(retained)
            != {
                "dimensions",
                "input_tokens",
                "latency_milliseconds",
                "provider_request_id",
                "receipt_id",
                "request_id",
                "result",
                "vector_fingerprint",
            }
            or retained.get("request_id")
            != retrieval_setup_request_id(cast("str", document["run_id"]), case_id)
            or retained.get("result") != "SUCCEEDED"
            or type(retained.get("provider_request_id")) is not str
            or retained.get("provider_request_id") in {"", "unreported"}
            or type(retained.get("receipt_id")) is not str
            or not retained.get("receipt_id")
            or type(retained.get("dimensions")) is not int
            or cast("int", retained["dimensions"]) < 1
            or type(retained.get("input_tokens")) is not int
            or cast("int", retained["input_tokens"]) < 1
            or type(retained.get("latency_milliseconds")) is not int
            or cast("int", retained["latency_milliseconds"]) < 0
            or not _full_fingerprint(retained.get("vector_fingerprint"))
        ):
            _fail()
        setup_ids.append(record_id)
        setup_inventory.append(
            {
                "payload_fingerprint": setup_record["payload_fingerprint"],
                "record_id": record_id,
                "vector_fingerprint": retained["vector_fingerprint"],
            }
        )
    if (
        len(setup_ids) != len(set(setup_ids))
        or setup.get("readback_inventory_fingerprint")
        != "sha256:" + sha256(canonicalize(checked_json_value(setup_inventory))).hexdigest()
    ):
        _fail()
    case_ids: list[str] = []
    for raw_case in cast("list[object]", cases):
        if type(raw_case) is not dict:
            _fail()
        case = cast("dict[str, object]", raw_case)
        if set(case) != {
            "case_id",
            "embedding_receipt",
            "expected_record_ids",
            "query_receipt",
            "query_request_fingerprint",
            "returned",
            "top_k",
            "suite_case_fingerprint",
        }:
            _fail()
        expected = case.get("expected_record_ids")
        returned = case.get("returned")
        receipt = case.get("embedding_receipt")
        query_receipt = case.get("query_receipt")
        if (
            type(case.get("case_id")) is not str
            or type(expected) is not list
            or not expected
            or any(type(item) is not str or not item for item in cast("list[object]", expected))
            or type(returned) is not list
            or not returned
            or type(case.get("top_k")) is not int
            or not 1 <= cast("int", case["top_k"]) <= _MAX_TOP_K
            or len(cast("list[object]", returned)) > cast("int", case["top_k"])
            or type(case.get("query_request_fingerprint")) is not str
            or _FINGERPRINT.fullmatch(cast("str", case["query_request_fingerprint"])) is None
            or type(receipt) is not dict
            or set(cast("dict[str, object]", receipt))
            != {
                "dimensions",
                "input_tokens",
                "latency_milliseconds",
                "provider_request_id",
                "receipt_id",
                "request_id",
                "result",
                "vector_fingerprint",
            }
            or cast("dict[object, object]", receipt).get("result") != "SUCCEEDED"
            or type(cast("dict[object, object]", receipt).get("provider_request_id")) is not str
            or not cast("dict[object, object]", receipt).get("provider_request_id")
            or cast("dict[object, object]", receipt).get("provider_request_id") == "unreported"
            or type(cast("dict[object, object]", receipt).get("receipt_id")) is not str
            or not cast("dict[object, object]", receipt).get("receipt_id")
            or type(case.get("suite_case_fingerprint")) is not str
            or _FINGERPRINT.fullmatch(cast("str", case["suite_case_fingerprint"])) is None
            or type(query_receipt) is not dict
            or set(cast("dict[str, object]", query_receipt))
            != {
                "provider_request_id",
                "receipt_id",
                "request_id",
                "result",
                "result_fingerprint",
            }
        ):
            _fail()
        returned_ids: list[str] = []
        for raw_result in cast("list[object]", returned):
            if type(raw_result) is not dict:
                _fail()
            result = cast("dict[str, object]", raw_result)
            if set(result) != {
                "payload_fingerprint",
                "record_id",
                "score",
            }:
                _fail()
            if (
                type(result.get("record_id")) is not str
                or not result["record_id"]
                or type(result.get("payload_fingerprint")) is not str
                or _FINGERPRINT.fullmatch(cast("str", result["payload_fingerprint"])) is None
                or type(result.get("score")) not in {int, float}
            ):
                _fail()
            returned_ids.append(cast("str", result["record_id"]))
        if len(returned_ids) != len(set(returned_ids)) or not set(
            cast("list[str]", expected)
        ).issubset(returned_ids):
            _fail()
        query_document = cast("dict[str, object]", query_receipt)
        expected_query_request = retrieval_query_request_id(
            cast("str", document["run_id"]), cast("str", case["case_id"])
        )
        result_fingerprint = (
            "sha256:"
            + sha256(
                canonicalize(
                    checked_json_value(
                        [
                            {
                                "payload_fingerprint": item["payload_fingerprint"],
                                "record_id": item["record_id"],
                                "score": item["score"],
                            }
                            for item in cast("list[dict[str, object]]", returned)
                        ]
                    )
                )
            ).hexdigest()
        )
        if (
            query_document.get("request_id") != expected_query_request
            or type(query_document.get("provider_request_id")) is not str
            or not query_document.get("provider_request_id")
            or query_document.get("provider_request_id") == "unreported"
            or query_document.get("result") != "SUCCEEDED"
            or query_document.get("result_fingerprint") != result_fingerprint
            or type(query_document.get("receipt_id")) is not str
            or _QUERY_RECEIPT.fullmatch(cast("str", query_document["receipt_id"])) is None
            or query_document.get("receipt_id")
            != query_readback_receipt_id(
                expected_query_request,
                cast("str", query_document["provider_request_id"]),
                result_fingerprint,
            )
        ):
            _fail()
        embedding_document = cast("dict[str, object]", receipt)
        if embedding_document.get("request_id") != retrieval_embedding_request_id(
            cast("str", document["run_id"]), cast("str", case["case_id"])
        ):
            _fail()
        case_ids.append(cast("str", case["case_id"]))
    if case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
        _fail()
    return LiveRetrievalEvaluationReceipt(
        cast("str", document["run_id"]),
        cast("str", document["observation_cutoff"]),
        cast("str", document["proposal_fingerprint"]),
        cast("str", document["embedding_profile_fingerprint"]),
        cast("str", document["serving_profile_fingerprint"]),
        cast("str", document["suite_fingerprint"]),
        cast("str", document["target_name"]),
        cast("str", document["target_fingerprint"]),
        len(case_ids),
        cast("str", document["fingerprint"]),
    )
