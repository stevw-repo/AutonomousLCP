"""Issue exact HK V1 provider capability evidence from two clean executions.

One execution is complete only when it contains both an owner-issued semantic
evaluation and an owner-issued embedding/ranked-retrieval evaluation.  The
second execution must use a distinct run identity and reproduce the stable
semantic and retrieval result projection exactly.  Provider request IDs and
latency are retained, but are not mistaken for result drift.

Preflight and issuance perform no provider, Pinecone, or network call.  The
single-run execute mode requires a detached, expiring, plan-bound authority and
uses the live adapters to build/read back one disposable evaluation target and
produce owner receipts.  Two process-distinct executions are then composed by
the separate issuer mode.
"""

from __future__ import annotations

import argparse
import fcntl
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from stat import S_IMODE
from typing import TYPE_CHECKING, Never, cast

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_processing import (
    AzureDeployment,
    AzureSemanticTaskRunner,
    BoundedModelTransport,
    ExactTokenCounter,
    LiveSemanticEvaluationCase,
    LiveSemanticEvaluationError,
    LiveSemanticEvaluationReceipt,
    ProcessingError,
    ProviderBudgetRequest,
    SemanticDecision,
    SemanticProfileSet,
    SemanticTaskGate,
    SemanticTaskRequest,
    load_semantic_profile_set,
    parse_live_semantic_evaluation,
    preflight_provider_budget,
    run_live_semantic_evaluation,
    semantic_evaluation_request_id,
    semantic_provider_input_text,
)
from asklegal_promotion import (
    AzureOpenAIConfig,
    AzureOpenAIEmbeddingAdapter,
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingReceipt,
    EmbeddingRequest,
    LiveRetrievalCase,
    LiveRetrievalEvaluationError,
    LiveRetrievalEvaluationReceipt,
    LiveRetrievalQueryPort,
    OutcomeUnknown,
    PineconeConfig,
    PineconeProviderCallReceipt,
    PineconeServingTargetStore,
    PromotionError,
    ProviderTransport,
    ServingCapabilityProfile,
    TargetDefinition,
    TargetRecord,
    live_vector_fingerprint,
    load_serving_capability_profile,
    parse_live_retrieval_evaluation,
    retrieval_setup_request_id,
    run_live_retrieval_evaluation,
    serving_metadata,
    serving_metadata_fingerprint,
    target_state_fingerprint,
)
from asklegal_promotion.profiles import ProfileError as ServingProfileError

if TYPE_CHECKING:
    from asklegal_legal_desks import SemanticTaskProfile
    from asklegal_promotion.ports import EmbeddingPort, EmbeddingTokenCounter

_SCHEMA = "asklegal.hk-v1-provider-admission/v1"
_MAX_RECEIPT_BYTES = 8_000_000
_MAX_REPORT_BYTES = 16_000_000
_REQUIRED_RUN_COUNT = 2
_SEMANTIC_CASE_COUNT = 3
_RETRIEVAL_CASE_COUNT = 4
_SHA256_FINGERPRINT_LENGTH = 71
_MAX_PORT = 65535
_PRIVATE_DIRECTORY_MODE = 0o700
_PINECONE_DESCRIBE_CALLS = 3
_ERROR = "PROVIDER_ADMISSION_INVALID"
_AUTHORITY_SCHEMA = "asklegal.hk-v1-provider-execution-authority/v1"
_OPERATIONS = [
    "AZURE_SEMANTIC",
    "AZURE_EMBEDDING",
    "PINECONE_CREATE",
    "PINECONE_UPSERT",
    "PINECONE_READBACK",
    "PINECONE_QUERY",
]
_SUITE_PATH = Path(__file__).resolve().parents[1] / "contracts/hk-v1-provider-golden-suite.json"
_REPORT_KEYS = frozenset(
    {
        "embedding_profile_fingerprint",
        "fingerprint",
        "model_profile_fingerprint",
        "observation_cutoff",
        "proposal_fingerprint",
        "repeat_fingerprint",
        "result",
        "runs",
        "schema_id",
        "schema_version",
        "serving_profile_fingerprint",
        "suite_fingerprint",
        "target_fingerprint",
        "target_name",
    }
)
_RUN_KEYS = frozenset({"retrieval_evaluation", "run_id", "run_number", "semantic_evaluation"})


class ProviderAdmissionError(ValueError):
    """Two clean provider executions were not proved exactly."""


@dataclass(frozen=True, slots=True)
class ProviderAdmissionEvidence:
    """Parsed two-run provider admission evidence."""

    run_ids: tuple[str, str]
    observation_cutoff: str
    proposal_fingerprint: str
    semantic_profile_fingerprint: str
    embedding_profile_fingerprint: str
    serving_profile_fingerprint: str
    suite_fingerprint: str
    target_name: str
    target_fingerprint: str
    semantic_case_count: int
    retrieval_case_count: int
    repeat_fingerprint: str
    fingerprint: str
    result: str = "ADMITTED"


@dataclass(frozen=True, slots=True)
class _Run:
    run_id: str
    semantic: LiveSemanticEvaluationReceipt
    retrieval: LiveRetrievalEvaluationReceipt
    semantic_document: dict[str, JsonValue]
    retrieval_document: dict[str, JsonValue]
    stable_fingerprint: str
    semantic_provider_ids: tuple[str, ...]
    semantic_effect_ids: tuple[str, ...]
    embedding_provider_ids: tuple[str, ...]
    embedding_receipt_ids: tuple[str, ...]
    query_provider_ids: tuple[str, ...]
    query_receipt_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _GoldenSuite:
    fingerprint: str
    semantic: dict[str, dict[str, JsonValue]]
    retrieval: dict[str, dict[str, JsonValue]]


@dataclass(frozen=True, slots=True)
class _ExecutionAuthority:
    authority_id: str
    authorized_by: str
    expires_at: str
    run_id: str
    observation_cutoff: str
    proposal_fingerprint: str
    suite_fingerprint: str
    semantic_profile_fingerprint: str
    serving_profile_fingerprint: str
    tokenizer_resource_fingerprint: str
    semantic_deployment: str
    embedding_deployment: str
    pinecone_project_id: str
    pinecone_index: str
    namespace: str
    max_semantic_calls: int
    max_embedding_calls: int
    max_pinecone_create_attempts: int
    max_pinecone_describe_calls: int
    max_pinecone_fetch_calls: int
    max_pinecone_upsert_batches: int
    max_pinecone_full_readbacks: int
    max_pinecone_list_calls: int
    max_pinecone_queries: int
    max_pinecone_reconciliation_calls: int
    max_pinecone_stats_calls: int
    expected_pinecone_provider_calls: int
    max_input_tokens: int
    max_cost_microunits: int
    output_root: str
    state_root: str
    plan_fingerprint: str
    fingerprint: str


class _AuthorityGate:
    def __init__(self, max_writes: int, authority: _ExecutionAuthority | None = None) -> None:
        self.writes = 0
        self._max_writes = max_writes
        self._authority = authority
        self._root: Path | None = None
        self._selected: str | None = None
        self._call_class = "EVALUATION"

    def bind(self, root: Path) -> None:
        self._root = root

    def select(self, operation: str) -> None:
        self._selected = operation

    def select_call_class(self, call_class: str) -> None:
        if call_class not in {"EVALUATION", "RECONCILIATION"}:
            _fail()
        self._call_class = call_class

    def _paths(self, operation: str) -> tuple[Path, Path]:
        if self._root is None:
            _fail()
        identity = sha256((self._selected or operation).encode()).hexdigest()
        return (
            self._root / f"{identity}.pinecone.intent.json",
            self._root / f"{identity}.pinecone.receipt.json",
        )

    def is_in_flight(self, operation: str) -> bool:
        intent, receipt = self._paths(operation)
        return intent.exists() and not receipt.exists()

    def is_complete(self, operation: str) -> bool:
        intent, receipt = self._paths(operation)
        return intent.exists() and receipt.exists()

    def complete(self, operation: str) -> None:
        intent, receipt = self._paths(operation)
        if not intent.exists():
            _fail()
        _write_exact(
            receipt,
            _runtime_record("asklegal.hk-v1-pinecone-effect-receipt/v1", {"operation": operation}),
        )
        self._selected = None

    def require_write(self, operation: str) -> None:
        if not operation.startswith(("creating index ", "upserting into ")):
            _fail()
        self.writes += 1
        if self.writes > self._max_writes:
            _fail()
        intent, receipt = self._paths(operation)
        if receipt.exists():
            return
        if intent.exists():
            _fail()
        _write_exact(
            intent,
            _runtime_record("asklegal.hk-v1-pinecone-effect-intent/v1", {"operation": operation}),
        )

    def require_delete(self, operation: str) -> None:
        del operation
        _fail()

    def record_provider_call(self, receipt: PineconeProviderCallReceipt) -> None:
        if (
            self._root is None
            or self._authority is None
            or receipt.provider_request_id in {"", "unreported"}
        ):
            _fail()
        identity = sha256(receipt.provider_request_id.encode()).hexdigest()
        _write_exact(
            self._root / f"{identity}.pinecone.call.json",
            _runtime_record(
                "asklegal.hk-v1-pinecone-provider-call/v1",
                {
                    "authority_fingerprint": self._authority.fingerprint,
                    "call_class": self._call_class,
                    "cost_basis": receipt.cost_basis,
                    "latency_milliseconds": receipt.latency_milliseconds,
                    "method": receipt.method,
                    "operation": receipt.operation,
                    "plan_fingerprint": self._authority.plan_fingerprint,
                    "provider_reported_cost_microunits": (
                        receipt.provider_reported_cost_microunits
                    ),
                    "provider_request_id": receipt.provider_request_id,
                    "request_fingerprint": receipt.request_fingerprint,
                    "request_units": receipt.request_units,
                    "run_id": self._authority.run_id,
                    "target_name": self._authority.pinecone_index,
                },
            ),
        )

    def provider_calls(self) -> tuple[dict[str, JsonValue], ...]:
        if self._root is None:
            _fail()
        return tuple(
            _runtime_parse(path, "asklegal.hk-v1-pinecone-provider-call/v1")
            for path in sorted(self._root.glob("*.pinecone.call.json"))
        )


@dataclass(frozen=True, slots=True)
class _ExactProfileReader:
    raw: bytes
    reference: ImmutableReference

    def read_exact(self, reference: ImmutableReference) -> bytes:
        if reference != self.reference:
            _fail()
        return self.raw


class _BudgetedSemanticRunner:
    def __init__(
        self,
        profiles: SemanticProfileSet,
        counter: ExactTokenCounter,
        delegate: AzureSemanticTaskRunner,
    ) -> None:
        self._profiles = profiles
        self._counter = counter
        self._delegate = delegate
        self._planned: tuple[ProviderBudgetRequest, ...] = ()

    def invoke(
        self, profile: SemanticTaskProfile, request: SemanticTaskRequest
    ) -> SemanticDecision:
        profile_id = profile.profile_id
        maximum = profile.max_output_tokens
        count = self._counter.count(semantic_provider_input_text(request))
        planned = (*self._planned, ProviderBudgetRequest(profile_id, count, maximum))
        preflight_provider_budget(planned, self._profiles)
        result = self._delegate.invoke(profile, request)
        self._planned = planned
        return result


class _JournaledSemanticRunner:
    def __init__(self, root: Path, delegate: _BudgetedSemanticRunner) -> None:
        self._root = root
        self._delegate = delegate

    def invoke(
        self, profile: SemanticTaskProfile, request: SemanticTaskRequest
    ) -> SemanticDecision:
        path = self._root / f"{request.request_id}.semantic.json"
        intent = self._root / f"{request.request_id}.semantic.intent.json"
        if path.exists():
            document = _runtime_parse(path, "asklegal.hk-v1-semantic-effect-journal/v1")
            if document.get("profile_id") != profile.profile_id:
                _fail()
            decision = document.get("decision")
            if not isinstance(decision, dict):
                _fail()
            return SemanticDecision(
                cast("str", decision["request_id"]),
                cast("str", decision["task"]),
                cast("str", decision["phase"]),  # type: ignore[arg-type]
                cast("str", decision["decision_code"]),
                tuple(cast("list[str]", decision["supporting_evidence_refs"])),
                tuple(cast("list[str]", decision["unresolved_facts"])),
                cast("str", decision["challenge_code"]),  # type: ignore[arg-type]
                cast("str", decision["output_fingerprint"]),
                cast("str", decision["provider"]),
                cast("str", decision["provider_request_id"]),
                cast("str", decision["effect_receipt_id"]),
            )
        if intent.exists():
            _fail()
        _write_exact(
            intent,
            _runtime_record(
                "asklegal.hk-v1-semantic-effect-intent/v1",
                {"profile_id": profile.profile_id, "request_id": request.request_id},
            ),
        )
        result = self._delegate.invoke(profile, request)
        raw = _runtime_record(
            "asklegal.hk-v1-semantic-effect-journal/v1",
            {
                "decision": {
                    "challenge_code": result.challenge_code,
                    "decision_code": result.decision_code,
                    "effect_receipt_id": result.effect_receipt_id,
                    "output_fingerprint": result.output_fingerprint,
                    "phase": result.phase,
                    "provider": result.provider,
                    "provider_request_id": result.provider_request_id,
                    "request_id": result.request_id,
                    "supporting_evidence_refs": list(result.supporting_evidence_refs),
                    "task": result.task,
                    "unresolved_facts": list(result.unresolved_facts),
                },
                "profile_id": profile.profile_id,
            },
        )
        _write_exact(path, raw)
        return result


class _JournaledEmbeddingPort:
    def __init__(self, root: Path, delegate: EmbeddingPort) -> None:
        self._root = root
        self._delegate = delegate

    def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> EmbeddedVector:
        path = self._root / f"{request.request_id}.embedding.json"
        intent = self._root / f"{request.request_id}.embedding.intent.json"
        if path.exists():
            document = _runtime_parse(path, "asklegal.hk-v1-embedding-effect-journal/v1")
            receipt = document.get("receipt")
            values = document.get("values")
            if (
                document.get("profile_id") != profile.profile_id
                or not isinstance(receipt, dict)
                or not isinstance(values, list)
                or any(type(value) not in {int, float} for value in values)
            ):
                _fail()
            retained = cast("dict[str, JsonValue]", receipt)
            return EmbeddedVector(
                tuple(float(value) for value in cast("list[int | float]", values)),
                EmbeddingReceipt(
                    cast("str", retained["receipt_id"]),
                    cast("str", retained["request_id"]),
                    cast("str", retained["provider_request_id"]),
                    cast("int", retained["dimensions"]),
                    cast("str", retained["vector_fingerprint"]),
                    cast("int", retained["input_tokens"]),
                    cast("int", retained["latency_milliseconds"]),
                    cast("str", retained["result"]),
                ),
            )
        if intent.exists():
            _fail()
        _write_exact(
            intent,
            _runtime_record(
                "asklegal.hk-v1-embedding-effect-intent/v1",
                {"profile_id": profile.profile_id, "request_id": request.request_id},
            ),
        )
        result = self._delegate.embed(profile, request)
        receipt = result.receipt
        _write_exact(
            path,
            _runtime_record(
                "asklegal.hk-v1-embedding-effect-journal/v1",
                {
                    "profile_id": profile.profile_id,
                    "receipt": {
                        "dimensions": receipt.dimensions,
                        "input_tokens": receipt.input_tokens,
                        "latency_milliseconds": receipt.latency_milliseconds,
                        "provider_request_id": receipt.provider_request_id,
                        "receipt_id": receipt.receipt_id,
                        "request_id": receipt.request_id,
                        "result": receipt.result,
                        "vector_fingerprint": receipt.vector_fingerprint,
                    },
                    "values": list(result.values),
                },
            ),
        )
        return result


def _fail() -> Never:
    raise ProviderAdmissionError(_ERROR)


def _document(raw: bytes, *, maximum: int) -> dict[str, JsonValue]:
    try:
        value = parse_json_bytes(raw, max_bytes=maximum)
    except ValueError:
        _fail()
    if type(value) is not dict or canonicalize(value) != raw:
        _fail()
    return cast("dict[str, JsonValue]", value)


def _fingerprinted(document: dict[str, JsonValue], field: str = "fingerprint") -> bool:
    supplied = document.get(field)
    unsigned = {key: value for key, value in document.items() if key != field}
    return (
        type(supplied) is str and supplied == "sha256:" + sha256(canonicalize(unsigned)).hexdigest()
    )


def _suite_document(raw: bytes) -> dict[str, JsonValue]:
    """Accept the repository text-file newline, but no other byte variation."""
    candidate = raw[:-1] if raw.endswith(b"\n") else raw
    if not candidate or b"\r" in raw or raw not in {candidate, candidate + b"\n"}:
        _fail()
    return _document(candidate, maximum=_MAX_RECEIPT_BYTES)


def _execution_authority(raw: bytes, *, now: str) -> _ExecutionAuthority:
    document = _suite_document(raw)
    expected_keys = {
        "allowed_operations",
        "authority_id",
        "authorized_by",
        "embedding_deployment",
        "expires_at",
        "fingerprint",
        "immutable",
        "max_cost_microunits",
        "max_embedding_calls",
        "max_input_tokens",
        "max_pinecone_create_attempts",
        "max_pinecone_describe_calls",
        "max_pinecone_fetch_calls",
        "max_pinecone_full_readbacks",
        "max_pinecone_list_calls",
        "max_pinecone_queries",
        "max_pinecone_reconciliation_calls",
        "max_pinecone_stats_calls",
        "max_pinecone_upsert_batches",
        "max_semantic_calls",
        "expected_pinecone_provider_calls",
        "namespace",
        "observation_cutoff",
        "output_root",
        "pinecone_index",
        "pinecone_project_id",
        "plan_fingerprint",
        "proposal_fingerprint",
        "run_id",
        "schema_id",
        "schema_version",
        "semantic_deployment",
        "semantic_profile_fingerprint",
        "serving_profile_fingerprint",
        "state_root",
        "suite_fingerprint",
        "tokenizer_resource_fingerprint",
    }
    run_id = document.get("run_id")
    fingerprints = (
        document.get("proposal_fingerprint"),
        document.get("semantic_profile_fingerprint"),
        document.get("serving_profile_fingerprint"),
        document.get("suite_fingerprint"),
        document.get("tokenizer_resource_fingerprint"),
        document.get("plan_fingerprint"),
    )
    integers = (
        document.get("max_semantic_calls"),
        document.get("max_embedding_calls"),
        document.get("max_input_tokens"),
        document.get("max_cost_microunits"),
        document.get("max_pinecone_create_attempts"),
        document.get("max_pinecone_describe_calls"),
        document.get("max_pinecone_fetch_calls"),
        document.get("max_pinecone_upsert_batches"),
        document.get("max_pinecone_full_readbacks"),
        document.get("max_pinecone_list_calls"),
        document.get("max_pinecone_queries"),
        document.get("max_pinecone_reconciliation_calls"),
        document.get("max_pinecone_stats_calls"),
        document.get("expected_pinecone_provider_calls"),
    )
    if (
        set(document) != expected_keys
        or document.get("schema_id") != _AUTHORITY_SCHEMA
        or document.get("schema_version") != 1
        or document.get("immutable") is not True
        or document.get("allowed_operations") != _OPERATIONS
        or not _fingerprinted(document)
        or type(run_id) is not str
        or not run_id
        or any(
            type(value) is not str or _full_fingerprint(value) is False for value in fingerprints
        )
        or any(type(value) is not int or value < 1 for value in integers)
        or any(
            type(document.get(field)) is not str or not document.get(field)
            for field in (
                "authority_id",
                "authorized_by",
                "embedding_deployment",
                "expires_at",
                "namespace",
                "observation_cutoff",
                "output_root",
                "pinecone_index",
                "pinecone_project_id",
                "semantic_deployment",
                "state_root",
            )
        )
    ):
        _fail()
    try:
        expiry = datetime.fromisoformat(cast("str", document["expires_at"]))
        current = datetime.fromisoformat(now)
    except AttributeError, ValueError:
        _fail()
    if (
        expiry.tzinfo is None
        or current.tzinfo is None
        or expiry.astimezone(UTC) <= current.astimezone(UTC)
    ):
        _fail()
    return _ExecutionAuthority(
        cast("str", document["authority_id"]),
        cast("str", document["authorized_by"]),
        cast("str", document["expires_at"]),
        run_id,
        cast("str", document["observation_cutoff"]),
        cast("str", document["proposal_fingerprint"]),
        cast("str", document["suite_fingerprint"]),
        cast("str", document["semantic_profile_fingerprint"]),
        cast("str", document["serving_profile_fingerprint"]),
        cast("str", document["tokenizer_resource_fingerprint"]),
        cast("str", document["semantic_deployment"]),
        cast("str", document["embedding_deployment"]),
        cast("str", document["pinecone_project_id"]),
        cast("str", document["pinecone_index"]),
        cast("str", document["namespace"]),
        cast("int", document["max_semantic_calls"]),
        cast("int", document["max_embedding_calls"]),
        cast("int", document["max_pinecone_create_attempts"]),
        cast("int", document["max_pinecone_describe_calls"]),
        cast("int", document["max_pinecone_fetch_calls"]),
        cast("int", document["max_pinecone_upsert_batches"]),
        cast("int", document["max_pinecone_full_readbacks"]),
        cast("int", document["max_pinecone_list_calls"]),
        cast("int", document["max_pinecone_queries"]),
        cast("int", document["max_pinecone_reconciliation_calls"]),
        cast("int", document["max_pinecone_stats_calls"]),
        cast("int", document["expected_pinecone_provider_calls"]),
        cast("int", document["max_input_tokens"]),
        cast("int", document["max_cost_microunits"]),
        cast("str", document["output_root"]),
        cast("str", document["state_root"]),
        cast("str", document["plan_fingerprint"]),
        cast("str", document["fingerprint"]),
    )


def _full_fingerprint(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _SHA256_FINGERPRINT_LENGTH
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _load_suite() -> _GoldenSuite:  # noqa: C901, PLR0912, PLR0915 - closed contract parser.
    try:
        raw = _SUITE_PATH.read_bytes()
    except OSError:
        _fail()
    document = _suite_document(raw)
    if (
        frozenset(document)
        != frozenset(
            {
                "fingerprint",
                "immutable",
                "required_language_slices",
                "required_material_families",
                "retrieval_cases",
                "schema_id",
                "schema_version",
                "semantic_cases",
                "suite_id",
                "suite_version",
            }
        )
        or document.get("schema_id") != "asklegal.hk-v1-provider-golden-suite/v1"
        or document.get("schema_version") != 1
        or document.get("immutable") is not True
        or document.get("suite_id") != "hk-v1-two-family-provider-golden"
        or document.get("suite_version") != "1.0.0"
        or document.get("required_language_slices")
        != ["EN", "ZH_HANT", "BILINGUAL", "CROSS_LANGUAGE"]
        or document.get("required_material_families") != ["CASES", "LEGISLATION"]
        or not _fingerprinted(document)
    ):
        _fail()
    raw_semantic = document.get("semantic_cases")
    raw_retrieval = document.get("retrieval_cases")
    if (
        not isinstance(raw_semantic, list)
        or len(raw_semantic) != _SEMANTIC_CASE_COUNT
        or not isinstance(raw_retrieval, list)
        or len(raw_retrieval) != _RETRIEVAL_CASE_COUNT
    ):
        _fail()
    semantic: dict[str, dict[str, JsonValue]] = {}
    for value in cast("list[JsonValue]", raw_semantic):
        if not isinstance(value, dict):
            _fail()
        case = cast("dict[str, JsonValue]", value)
        if frozenset(case) != frozenset(
            {
                "case_fingerprint",
                "case_id",
                "challenge_task",
                "evidence_bytes_utf8",
                "evidence_refs",
                "expected_challenge",
                "expected_primary",
                "input_fingerprint",
                "language_slice",
                "material_family",
                "package_fingerprint",
                "primary_task",
                "subject_id",
            }
        ) or not _fingerprinted(case, "case_fingerprint"):
            _fail()
        evidence_bytes = case.get("evidence_bytes_utf8")
        evidence_refs = case.get("evidence_refs")
        expected_primary = case.get("expected_primary")
        expected_challenge = case.get("expected_challenge")
        if (
            type(evidence_bytes) is not str
            or not evidence_bytes
            or type(evidence_refs) is not list
            or not evidence_refs
            or any(
                type(item) is not str or not item for item in cast("list[object]", evidence_refs)
            )
            or type(expected_primary) is not dict
            or type(expected_challenge) is not dict
            or set(cast("dict[str, object]", expected_primary))
            != {"challenge_code", "decision_code", "supporting_evidence_refs", "unresolved_facts"}
            or set(cast("dict[str, object]", expected_challenge))
            != {"challenge_code", "decision_code", "supporting_evidence_refs", "unresolved_facts"}
            or case.get("input_fingerprint")
            != "sha256:" + sha256(evidence_bytes.encode()).hexdigest()
            or case.get("package_fingerprint")
            != "sha256:"
            + sha256(
                canonicalize(
                    checked_json_value(
                        {
                            "case_id": case.get("case_id"),
                            "evidence_bytes_utf8": evidence_bytes,
                            "evidence_refs": evidence_refs,
                            "subject_id": case.get("subject_id"),
                        }
                    )
                )
            ).hexdigest()
        ):
            _fail()
        for expected, challenge_code in (
            (cast("dict[str, object]", expected_primary), "NOT_APPLICABLE"),
            (cast("dict[str, object]", expected_challenge), "PASS"),
        ):
            if (
                type(expected.get("decision_code")) is not str
                or not expected.get("decision_code")
                or expected.get("supporting_evidence_refs") != evidence_refs
                or expected.get("unresolved_facts") != []
                or expected.get("challenge_code") != challenge_code
            ):
                _fail()
        case_id = case.get("case_id")
        if type(case_id) is not str or not case_id or case_id in semantic:
            _fail()
        semantic[case_id] = case
    retrieval: dict[str, dict[str, JsonValue]] = {}
    for value in cast("list[JsonValue]", raw_retrieval):
        if not isinstance(value, dict):
            _fail()
        case = cast("dict[str, JsonValue]", value)
        if frozenset(case) != frozenset(
            {
                "case_fingerprint",
                "case_id",
                "expected_records",
                "language_slice",
                "material_family",
                "query_fingerprint",
                "query_text",
                "top_k",
            }
        ) or not _fingerprinted(case, "case_fingerprint"):
            _fail()
        query_text = case.get("query_text")
        expected_records = case.get("expected_records")
        if (
            type(query_text) is not str
            or not query_text
            or case.get("query_fingerprint") != "sha256:" + sha256(query_text.encode()).hexdigest()
            or type(expected_records) is not list
            or not expected_records
        ):
            _fail()
        for raw_record in cast("list[object]", expected_records):
            if type(raw_record) is not dict:
                _fail()
            record = cast("dict[str, object]", raw_record)
            if set(record) != {
                "authority_note",
                "country",
                "jurisdiction",
                "material_type",
                "payload_fingerprint",
                "record_id",
                "source",
                "text",
            }:
                _fail()
            payload = {
                "authority_note": record.get("authority_note"),
                "country": record.get("country"),
                "jurisdiction": record.get("jurisdiction"),
                "source": record.get("source"),
                "text": record.get("text"),
                "type": record.get("material_type"),
            }
            if (
                any(type(value) is not str or not value for value in payload.values())
                or type(record.get("record_id")) is not str
                or not record.get("record_id")
                or record.get("payload_fingerprint")
                != "sha256:" + sha256(canonicalize(checked_json_value(payload))).hexdigest()
            ):
                _fail()
        case_id = case.get("case_id")
        if type(case_id) is not str or not case_id or case_id in retrieval:
            _fail()
        retrieval[case_id] = case
    if (
        {str(case["material_family"]) for case in semantic.values()} != {"CASES", "LEGISLATION"}
        or {str(case["material_family"]) for case in retrieval.values()} != {"CASES", "LEGISLATION"}
        or {str(case["language_slice"]) for case in semantic.values()}
        != {"EN", "ZH_HANT", "BILINGUAL"}
        or {str(case["language_slice"]) for case in retrieval.values()}
        != {"EN", "ZH_HANT", "BILINGUAL", "CROSS_LANGUAGE"}
    ):
        _fail()
    return _GoldenSuite(cast("str", document["fingerprint"]), semantic, retrieval)


def _semantic_cases(
    suite: _GoldenSuite, profiles: SemanticProfileSet
) -> tuple[LiveSemanticEvaluationCase, ...]:
    by_task = {profile.task: profile.profile_id for profile in profiles.profiles}
    cases: list[LiveSemanticEvaluationCase] = []
    for case_id, value in suite.semantic.items():
        primary_task = cast("str", value["primary_task"])
        challenge_task = cast("str", value["challenge_task"])
        try:
            primary_profile = by_task[primary_task]
            challenge_profile = by_task[challenge_task]
        except KeyError:
            _fail()
        evidence_text = cast("str", value["evidence_bytes_utf8"])
        evidence_refs = tuple(cast("list[str]", value["evidence_refs"]))
        package_fingerprint = cast("str", value["package_fingerprint"])
        subject_id = cast("str", value["subject_id"])
        input_fingerprint = cast("str", value["input_fingerprint"])
        cases.append(
            LiveSemanticEvaluationCase(
                case_id,
                (
                    SemanticTaskRequest(
                        "suite-owned-before-run-binding",
                        primary_task,
                        "DECISION",
                        primary_profile,
                        package_fingerprint,
                        subject_id,
                        evidence_refs,
                        evidence_text.encode(),
                        input_fingerprint,
                    ),
                    SemanticTaskRequest(
                        "suite-owned-before-run-binding",
                        challenge_task,
                        "CHALLENGE",
                        challenge_profile,
                        package_fingerprint,
                        subject_id,
                        evidence_refs,
                        evidence_text.encode(),
                        input_fingerprint,
                    ),
                ),
                cast(
                    "str",
                    cast("dict[str, JsonValue]", value["expected_primary"])["decision_code"],
                ),
                cast("str", value["case_fingerprint"]),
            )
        )
    return tuple(cases)


def _retrieval_cases(
    suite: _GoldenSuite,
    profile: EmbeddingProfile,
    counter: EmbeddingTokenCounter,
) -> tuple[LiveRetrievalCase, ...]:
    if counter.tokenizer_id != profile.tokenizer:
        _fail()
    cases: list[LiveRetrievalCase] = []
    for position, (case_id, value) in enumerate(suite.retrieval.items()):
        query = cast("str", value["query_text"])
        token_count = counter.count(query)
        if type(token_count) is not int or not 1 <= token_count <= profile.max_input_tokens:
            _fail()
        expected_records = cast("list[dict[str, JsonValue]]", value["expected_records"])
        cases.append(
            LiveRetrievalCase(
                case_id,
                EmbeddingRequest(
                    "suite-owned-before-run-binding",
                    "golden-query:" + case_id,
                    cast("str", value["query_fingerprint"]),
                    query,
                    cast("str", value["query_fingerprint"]),
                    token_count,
                    profile.profile_id,
                    "provider-admission-golden-suite",
                    position,
                    "provider-admission:" + cast("str", value["case_fingerprint"]),
                ),
                tuple(cast("str", record["record_id"]) for record in expected_records),
                cast("int", value["top_k"]),
                cast("str", value["case_fingerprint"]),
            )
        )
    return tuple(cases)


def execute_provider_admission(  # noqa: PLR0913 - exact live admission lineage.
    *,
    run_ids: tuple[str, str],
    observation_cutoff: str,
    proposal_fingerprint: str,
    semantic_profiles: SemanticProfileSet,
    serving_profile: ServingCapabilityProfile,
    semantic_gate: SemanticTaskGate,
    embeddings: EmbeddingPort,
    target: LiveRetrievalQueryPort,
    target_name: str,
    target_fingerprint: str,
    token_counter: EmbeddingTokenCounter,
    target_setups: tuple[dict[str, JsonValue], dict[str, JsonValue]],
    now: str,
) -> bytes:
    """Execute the repository-owned suite twice and issue its exact evidence."""
    suite = _load_suite()
    semantic_cases = _semantic_cases(suite, semantic_profiles)
    retrieval_cases = _retrieval_cases(suite, serving_profile.embedding, token_counter)
    semantic_runs: list[bytes] = []
    retrieval_runs: list[bytes] = []
    if len(run_ids) != _REQUIRED_RUN_COUNT or run_ids[0] == run_ids[1]:
        _fail()
    for index, run_id in enumerate(run_ids):
        semantic_runs.append(
            run_live_semantic_evaluation(
                run_id=run_id,
                observation_cutoff=observation_cutoff,
                proposal_fingerprint=proposal_fingerprint,
                serving_profile_fingerprint=serving_profile.fingerprint,
                suite_fingerprint=suite.fingerprint,
                profile_set=semantic_profiles,
                cases=semantic_cases,
                gate=semantic_gate,
                environment=semantic_profiles.environment,
                now=now,
            )
        )
        retrieval_runs.append(
            run_live_retrieval_evaluation(
                run_id=run_id,
                observation_cutoff=observation_cutoff,
                proposal_fingerprint=proposal_fingerprint,
                serving_profile_fingerprint=serving_profile.fingerprint,
                suite_fingerprint=suite.fingerprint,
                target_name=target_name,
                target_fingerprint=target_fingerprint,
                target_setup=target_setups[index],
                profile=serving_profile.embedding,
                cases=retrieval_cases,
                embeddings=embeddings,
                target=target,
            )
        )
    return issue_provider_admission_evidence(
        semantic_run_1=semantic_runs[0],
        retrieval_run_1=retrieval_runs[0],
        semantic_run_2=semantic_runs[1],
        retrieval_run_2=retrieval_runs[1],
    )


def _stable_semantic(document: dict[str, JsonValue]) -> dict[str, JsonValue]:
    stable = _document(canonicalize(document), maximum=_MAX_RECEIPT_BYTES)
    stable.pop("fingerprint", None)
    stable.pop("run_id", None)
    cases = stable.get("cases")
    if not isinstance(cases, list):
        _fail()
    for raw_case in cast("list[JsonValue]", cases):
        if not isinstance(raw_case, dict):
            _fail()
        case = cast("dict[str, JsonValue]", raw_case)
        for role in ("primary", "challenge"):
            raw_decision = case.get(role)
            if not isinstance(raw_decision, dict):
                _fail()
            decision = cast("dict[str, JsonValue]", raw_decision)
            for volatile in (
                "effect_receipt_id",
                "output_fingerprint",
                "provider_request_id",
                "request_id",
            ):
                decision.pop(volatile, None)
    return stable


def _stable_retrieval(  # noqa: C901, PLR0912 - closed nested receipt projection.
    document: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    stable = _document(canonicalize(document), maximum=_MAX_RECEIPT_BYTES)
    stable.pop("fingerprint", None)
    stable.pop("run_id", None)
    setup_raw = stable.get("target_setup")
    if not isinstance(setup_raw, dict):
        _fail()
    setup = cast("dict[str, JsonValue]", setup_raw)
    setup.pop("fingerprint", None)
    setup.pop("run_id", None)
    setup_records = setup.get("records")
    if not isinstance(setup_records, list):
        _fail()
    for raw_setup_record in cast("list[JsonValue]", setup_records):
        if not isinstance(raw_setup_record, dict):
            _fail()
        embedded_raw = raw_setup_record.get("embedding_receipt")
        if not isinstance(embedded_raw, dict):
            _fail()
        embedded = cast("dict[str, JsonValue]", embedded_raw)
        for volatile in (
            "latency_milliseconds",
            "provider_request_id",
            "receipt_id",
            "request_id",
        ):
            embedded.pop(volatile, None)
    cases = stable.get("cases")
    if not isinstance(cases, list):
        _fail()
    for raw_case in cast("list[JsonValue]", cases):
        if not isinstance(raw_case, dict):
            _fail()
        case = cast("dict[str, JsonValue]", raw_case)
        receipt = case.get("embedding_receipt")
        if not isinstance(receipt, dict):
            _fail()
        retained = cast("dict[str, JsonValue]", receipt)
        for volatile in (
            "latency_milliseconds",
            "provider_request_id",
            "receipt_id",
            "request_id",
        ):
            retained.pop(volatile, None)
        query_raw = case.get("query_receipt")
        if not isinstance(query_raw, dict):
            _fail()
        query = cast("dict[str, JsonValue]", query_raw)
        for volatile in ("provider_request_id", "receipt_id", "request_id"):
            query.pop(volatile, None)
    calls = stable.get("target_provider_calls")
    if not isinstance(calls, list):
        _fail()
    for raw_call in cast("list[JsonValue]", calls):
        if not isinstance(raw_call, dict):
            _fail()
        call = cast("dict[str, JsonValue]", raw_call)
        for volatile in (
            "authority_fingerprint",
            "fingerprint",
            "latency_milliseconds",
            "plan_fingerprint",
            "provider_request_id",
            "run_id",
        ):
            call.pop(volatile, None)
    calls.sort(
        key=lambda item: (
            str(cast("dict[str, JsonValue]", item).get("operation")),
            str(cast("dict[str, JsonValue]", item).get("request_fingerprint")),
        )
    )
    return stable


def _case_map(document: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    values = document.get("cases")
    if not isinstance(values, list):
        _fail()
    result: dict[str, dict[str, JsonValue]] = {}
    for value in cast("list[JsonValue]", values):
        if not isinstance(value, dict) or type(value.get("case_id")) is not str:
            _fail()
        case = cast("dict[str, JsonValue]", value)
        case_id = cast("str", case["case_id"])
        if case_id in result:
            _fail()
        result[case_id] = case
    return result


def _validate_suite_cases(  # noqa: C901 - exact cross-owner suite bindings.
    suite: _GoldenSuite,
    semantic_document: dict[str, JsonValue],
    retrieval_document: dict[str, JsonValue],
) -> None:
    if (
        semantic_document.get("suite_fingerprint") != suite.fingerprint
        or retrieval_document.get("suite_fingerprint") != suite.fingerprint
    ):
        _fail()
    semantic = _case_map(semantic_document)
    retrieval = _case_map(retrieval_document)
    if set(semantic) != set(suite.semantic) or set(retrieval) != set(suite.retrieval):
        _fail()
    for case_id, expected in suite.semantic.items():
        actual = semantic[case_id]
        primary = actual.get("primary")
        challenge = actual.get("challenge")
        if not isinstance(primary, dict) or not isinstance(challenge, dict):
            _fail()
        bindings = {
            "evidence_refs": expected["evidence_refs"],
            "expected_decision_code": cast("dict[str, JsonValue]", expected["expected_primary"])[
                "decision_code"
            ],
            "input_fingerprint": expected["input_fingerprint"],
            "package_fingerprint": expected["package_fingerprint"],
            "suite_case_fingerprint": expected["case_fingerprint"],
        }
        if (
            any(actual.get(key) != value for key, value in bindings.items())
            or primary.get("task") != expected["primary_task"]
            or challenge.get("task") != expected["challenge_task"]
            or primary.get("provider") != "AZURE_OPENAI"
            or challenge.get("provider") != "AZURE_OPENAI"
            or any(
                actual_decision.get(key) != expected_decision.get(key)
                for actual_decision, expected_decision in (
                    (primary, cast("dict[str, JsonValue]", expected["expected_primary"])),
                    (challenge, cast("dict[str, JsonValue]", expected["expected_challenge"])),
                )
                for key in (
                    "challenge_code",
                    "decision_code",
                    "supporting_evidence_refs",
                    "unresolved_facts",
                )
            )
        ):
            _fail()
    for case_id, expected in suite.retrieval.items():
        actual = retrieval[case_id]
        expected_records = cast("list[dict[str, JsonValue]]", expected["expected_records"])
        expected_ids = [record["record_id"] for record in expected_records]
        returned = actual.get("returned")
        if (
            actual.get("expected_record_ids") != expected_ids
            or actual.get("query_request_fingerprint") != expected["query_fingerprint"]
            or actual.get("top_k") != expected["top_k"]
            or actual.get("suite_case_fingerprint") != expected["case_fingerprint"]
            or type(returned) is not list
            or any(
                not any(
                    type(item) is dict
                    and item.get("record_id") == expected_record["record_id"]
                    and item.get("payload_fingerprint") == expected_record["payload_fingerprint"]
                    for item in cast("list[object]", returned)
                )
                for expected_record in expected_records
            )
        ):
            _fail()
    setup = retrieval_document.get("target_setup")
    if not isinstance(setup, dict) or not isinstance(setup.get("records"), list):
        _fail()
    setup_records = {
        cast("str", item["record_id"]): item
        for item in cast("list[dict[str, JsonValue]]", setup["records"])
    }
    golden_records = {
        cast("str", record["record_id"]): record
        for case in suite.retrieval.values()
        for record in cast("list[dict[str, JsonValue]]", case["expected_records"])
    }
    if set(setup_records) != set(golden_records) or any(
        setup_records[record_id].get("payload_fingerprint")
        != golden_records[record_id].get("payload_fingerprint")
        for record_id in golden_records
    ):
        _fail()
    expected_setup_cases = {
        cast(
            "str", cast("list[dict[str, JsonValue]]", case["expected_records"])[0]["record_id"]
        ): case_id
        for case_id, case in suite.retrieval.items()
    }
    if any(
        setup_records[record_id].get("case_id") != case_id
        for record_id, case_id in expected_setup_cases.items()
    ):
        _fail()


_TARGET_CALL_KEYS = frozenset(
    {
        "authority_fingerprint",
        "call_class",
        "cost_basis",
        "fingerprint",
        "latency_milliseconds",
        "method",
        "operation",
        "plan_fingerprint",
        "provider_reported_cost_microunits",
        "provider_request_id",
        "request_fingerprint",
        "request_units",
        "run_id",
        "schema_id",
        "schema_version",
        "target_name",
    }
)
_TARGET_OPERATION_COUNTS = {
    "INDEX_CREATE": 1,
    "INDEX_DESCRIBE_OR_LIST": 3,
    "INDEX_STATS": 1,
    "VECTOR_FETCH": 2,
    "VECTOR_LIST": 1,
    "VECTOR_QUERY": 4,
    "VECTOR_UPSERT": 2,
}
_TARGET_RECONCILIATION_COUNTS = {
    "INDEX_DESCRIBE_OR_LIST": 2,
    "VECTOR_FETCH": 2,
    "VECTOR_LIST": 1,
}


def _target_provider_ids(retrieval_document: dict[str, JsonValue]) -> tuple[str, ...]:
    raw_calls = retrieval_document.get("target_provider_calls")
    if not isinstance(raw_calls, list) or len(raw_calls) not in {
        sum(_TARGET_OPERATION_COUNTS.values()),
        sum(_TARGET_OPERATION_COUNTS.values()) + sum(_TARGET_RECONCILIATION_COUNTS.values()),
    }:
        _fail()
    run_id = retrieval_document.get("run_id")
    target_name = retrieval_document.get("target_name")
    authority_fingerprints: set[str] = set()
    plan_fingerprints: set[str] = set()
    provider_ids: list[str] = []
    counts: dict[str, int] = {}
    reconciliation_counts: dict[str, int] = {}
    for raw_call in cast("list[JsonValue]", raw_calls):
        if not isinstance(raw_call, dict):
            _fail()
        call = cast("dict[str, JsonValue]", raw_call)
        operation = call.get("operation")
        provider_id = call.get("provider_request_id")
        authority_fingerprint = call.get("authority_fingerprint")
        plan_fingerprint = call.get("plan_fingerprint")
        if (
            frozenset(call) != _TARGET_CALL_KEYS
            or call.get("schema_id") != "asklegal.hk-v1-pinecone-provider-call/v1"
            or call.get("schema_version") != 1
            or not _fingerprinted(call)
            or call.get("run_id") != run_id
            or call.get("target_name") != target_name
            or call.get("call_class") not in {"EVALUATION", "RECONCILIATION"}
            or type(operation) is not str
            or operation not in _TARGET_OPERATION_COUNTS
            or type(provider_id) is not str
            or provider_id in {"", "unreported"}
            or not _full_fingerprint(call.get("request_fingerprint"))
            or not _full_fingerprint(authority_fingerprint)
            or not _full_fingerprint(plan_fingerprint)
            or type(call.get("latency_milliseconds")) is not int
            or cast("int", call["latency_milliseconds"]) < 0
            or call.get("request_units") != 1
            or call.get("provider_reported_cost_microunits") is not None
            or call.get("cost_basis") != "PROVIDER_BILLING_OUT_OF_BAND_CALL_CEILING"
            or call.get("method") not in {"GET", "POST"}
        ):
            _fail()
        provider_ids.append(provider_id)
        authority_fingerprints.add(cast("str", authority_fingerprint))
        plan_fingerprints.add(cast("str", plan_fingerprint))
        selected_counts = (
            counts if call.get("call_class") == "EVALUATION" else reconciliation_counts
        )
        selected_counts[operation] = selected_counts.get(operation, 0) + 1
    if (
        len(provider_ids) != len(set(provider_ids))
        or counts != _TARGET_OPERATION_COUNTS
        or reconciliation_counts not in ({}, _TARGET_RECONCILIATION_COUNTS)
        or len(authority_fingerprints) != 1
        or len(plan_fingerprints) != 1
    ):
        _fail()
    query_ids = {
        cast("str", cast("dict[str, JsonValue]", case["query_receipt"])["provider_request_id"])
        for case in _case_map(retrieval_document).values()
    }
    call_query_ids = {
        cast("str", call["provider_request_id"])
        for call in cast("list[dict[str, JsonValue]]", raw_calls)
        if call.get("call_class") == "EVALUATION" and call.get("operation") == "VECTOR_QUERY"
    }
    if query_ids != call_query_ids:
        _fail()
    return tuple(provider_ids)


def _require_target_calls_match_authority(
    retrieval_document: dict[str, JsonValue], authority: _ExecutionAuthority
) -> None:
    """Bind every retained target transport receipt to this exact authority."""
    _target_provider_ids(retrieval_document)
    raw_calls = cast("list[dict[str, JsonValue]]", retrieval_document["target_provider_calls"])
    raw_evaluation_calls = [call for call in raw_calls if call.get("call_class") == "EVALUATION"]
    if (
        len(raw_evaluation_calls) != authority.expected_pinecone_provider_calls
        or len(raw_calls) - len(raw_evaluation_calls) > authority.max_pinecone_reconciliation_calls
        or any(
            call.get("authority_fingerprint") != authority.fingerprint
            or call.get("plan_fingerprint") != authority.plan_fingerprint
            or call.get("run_id") != authority.run_id
            or call.get("target_name") != authority.pinecone_index
            for call in raw_calls
        )
    ):
        _fail()


def _attempt_ids(  # noqa: C901 - closed nested receipt projection.
    semantic_document: dict[str, JsonValue], retrieval_document: dict[str, JsonValue]
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    semantic_provider: list[str] = []
    semantic_effect: list[str] = []
    for case in _case_map(semantic_document).values():
        for role in ("primary", "challenge"):
            decision = case.get(role)
            if not isinstance(decision, dict):
                _fail()
            semantic_provider.append(str(decision.get("provider_request_id")))
            semantic_effect.append(str(decision.get("effect_receipt_id")))
    embedding_provider: list[str] = []
    embedding_receipt: list[str] = []
    query_provider = list(_target_provider_ids(retrieval_document))
    query_receipt: list[str] = []
    setup = retrieval_document.get("target_setup")
    if not isinstance(setup, dict) or not isinstance(setup.get("records"), list):
        _fail()
    for setup_record in cast("list[JsonValue]", setup["records"]):
        if not isinstance(setup_record, dict):
            _fail()
        embedding = setup_record.get("embedding_receipt")
        if not isinstance(embedding, dict):
            _fail()
        embedding_provider.append(str(embedding.get("provider_request_id")))
        embedding_receipt.append(str(embedding.get("receipt_id")))
    for case in _case_map(retrieval_document).values():
        embedding = case.get("embedding_receipt")
        query = case.get("query_receipt")
        if not isinstance(embedding, dict) or not isinstance(query, dict):
            _fail()
        embedding_provider.append(str(embedding.get("provider_request_id")))
        embedding_receipt.append(str(embedding.get("receipt_id")))
        query_receipt.append(str(query.get("receipt_id")))
    values = (
        tuple(semantic_provider),
        tuple(semantic_effect),
        tuple(embedding_provider),
        tuple(embedding_receipt),
        tuple(query_provider),
        tuple(query_receipt),
    )
    if any(len(items) != len(set(items)) for items in values):
        _fail()
    return values


def _run(semantic_raw: bytes, retrieval_raw: bytes) -> _Run:
    try:
        semantic = parse_live_semantic_evaluation(semantic_raw)
        retrieval = parse_live_retrieval_evaluation(retrieval_raw)
    except LiveSemanticEvaluationError, LiveRetrievalEvaluationError, TypeError, ValueError:
        _fail()
    semantic_document = _document(semantic_raw, maximum=_MAX_RECEIPT_BYTES)
    retrieval_document = _document(retrieval_raw, maximum=_MAX_RECEIPT_BYTES)
    suite = _load_suite()
    _validate_suite_cases(suite, semantic_document, retrieval_document)
    if (
        semantic.run_id != retrieval.run_id
        or semantic.observation_cutoff != retrieval.observation_cutoff
        or semantic.proposal_fingerprint != retrieval.proposal_fingerprint
        or semantic.serving_profile_fingerprint != retrieval.serving_profile_fingerprint
    ):
        _fail()
    stable = canonicalize(
        checked_json_value(
            {
                "retrieval": _stable_retrieval(retrieval_document),
                "semantic": _stable_semantic(semantic_document),
            }
        )
    )
    attempts = _attempt_ids(semantic_document, retrieval_document)
    return _Run(
        semantic.run_id,
        semantic,
        retrieval,
        semantic_document,
        retrieval_document,
        "sha256:" + sha256(stable).hexdigest(),
        *attempts,
    )


def _lineage(run: _Run) -> tuple[str, ...]:
    return (
        run.semantic.observation_cutoff,
        run.semantic.proposal_fingerprint,
        run.semantic.semantic_profile_fingerprint,
        run.retrieval.embedding_profile_fingerprint,
        run.semantic.serving_profile_fingerprint,
        run.retrieval.target_name,
        run.retrieval.target_fingerprint,
        run.semantic.suite_fingerprint,
        str(run.semantic.case_count),
        str(run.retrieval.case_count),
    )


def _distinct_attempts(first: _Run, second: _Run) -> bool:
    pairs = (
        (first.semantic_provider_ids, second.semantic_provider_ids),
        (first.semantic_effect_ids, second.semantic_effect_ids),
        (first.embedding_provider_ids, second.embedding_provider_ids),
        (first.embedding_receipt_ids, second.embedding_receipt_ids),
        (first.query_provider_ids, second.query_provider_ids),
        (first.query_receipt_ids, second.query_receipt_ids),
    )
    call_bindings = tuple(
        {
            cast("str", call[field])
            for call in cast(
                "list[dict[str, JsonValue]]", run.retrieval_document["target_provider_calls"]
            )
        }
        for run in (first, second)
        for field in ("authority_fingerprint", "plan_fingerprint")
    )
    return all(set(left).isdisjoint(right) for left, right in pairs) and all(
        call_bindings[index].isdisjoint(call_bindings[index + 2]) for index in range(2)
    )


def issue_provider_admission_evidence(
    *,
    semantic_run_1: bytes,
    retrieval_run_1: bytes,
    semantic_run_2: bytes,
    retrieval_run_2: bytes,
) -> bytes:
    """Issue one canonical report only from two matching complete executions."""
    first = _run(semantic_run_1, retrieval_run_1)
    second = _run(semantic_run_2, retrieval_run_2)
    if (
        first.run_id == second.run_id
        or _lineage(first) != _lineage(second)
        or first.stable_fingerprint != second.stable_fingerprint
        or not _distinct_attempts(first, second)
    ):
        _fail()
    document: dict[str, object] = {
        "embedding_profile_fingerprint": first.retrieval.embedding_profile_fingerprint,
        "model_profile_fingerprint": first.semantic.semantic_profile_fingerprint,
        "observation_cutoff": first.semantic.observation_cutoff,
        "proposal_fingerprint": first.semantic.proposal_fingerprint,
        "repeat_fingerprint": first.stable_fingerprint,
        "result": "ADMITTED",
        "runs": [
            {
                "retrieval_evaluation": first.retrieval_document,
                "run_id": first.run_id,
                "run_number": 1,
                "semantic_evaluation": first.semantic_document,
            },
            {
                "retrieval_evaluation": second.retrieval_document,
                "run_id": second.run_id,
                "run_number": 2,
                "semantic_evaluation": second.semantic_document,
            },
        ],
        "schema_id": _SCHEMA,
        "schema_version": 1,
        "serving_profile_fingerprint": first.semantic.serving_profile_fingerprint,
        "suite_fingerprint": first.semantic.suite_fingerprint,
        "target_fingerprint": first.retrieval.target_fingerprint,
        "target_name": first.retrieval.target_name,
    }
    unsigned = canonicalize(checked_json_value(document))
    document["fingerprint"] = "sha256:" + sha256(unsigned).hexdigest()
    raw = canonicalize(checked_json_value(document))
    parse_provider_admission_evidence(raw)
    return raw


def parse_provider_admission_evidence(raw: bytes) -> ProviderAdmissionEvidence:
    """Reparse and independently rederive a two-clean-run admission report."""
    document = _document(raw, maximum=_MAX_REPORT_BYTES)
    if (
        frozenset(document) != _REPORT_KEYS
        or document.get("schema_id") != _SCHEMA
        or document.get("schema_version") != 1
        or document.get("result") != "ADMITTED"
    ):
        _fail()
    fingerprint = document.get("fingerprint")
    unsigned = {key: value for key, value in document.items() if key != "fingerprint"}
    if (
        type(fingerprint) is not str
        or fingerprint != "sha256:" + sha256(canonicalize(unsigned)).hexdigest()
    ):
        _fail()
    raw_runs = document.get("runs")
    if not isinstance(raw_runs, list) or len(raw_runs) != _REQUIRED_RUN_COUNT:
        _fail()
    runs: list[_Run] = []
    for index, raw_run in enumerate(cast("list[JsonValue]", raw_runs), start=1):
        if not isinstance(raw_run, dict) or frozenset(raw_run) != _RUN_KEYS:
            _fail()
        run = cast("dict[str, JsonValue]", raw_run)
        semantic_value = run.get("semantic_evaluation")
        retrieval_value = run.get("retrieval_evaluation")
        if not isinstance(semantic_value, dict) or not isinstance(retrieval_value, dict):
            _fail()
        parsed = _run(canonicalize(semantic_value), canonicalize(retrieval_value))
        if run.get("run_number") != index or run.get("run_id") != parsed.run_id:
            _fail()
        runs.append(parsed)
    first, second = runs
    expected = {
        "embedding_profile_fingerprint": first.retrieval.embedding_profile_fingerprint,
        "model_profile_fingerprint": first.semantic.semantic_profile_fingerprint,
        "observation_cutoff": first.semantic.observation_cutoff,
        "proposal_fingerprint": first.semantic.proposal_fingerprint,
        "repeat_fingerprint": first.stable_fingerprint,
        "serving_profile_fingerprint": first.semantic.serving_profile_fingerprint,
        "suite_fingerprint": first.semantic.suite_fingerprint,
        "target_fingerprint": first.retrieval.target_fingerprint,
        "target_name": first.retrieval.target_name,
    }
    if (
        first.run_id == second.run_id
        or _lineage(first) != _lineage(second)
        or first.stable_fingerprint != second.stable_fingerprint
        or not _distinct_attempts(first, second)
        or any(document.get(key) != value for key, value in expected.items())
    ):
        _fail()
    return ProviderAdmissionEvidence(
        (first.run_id, second.run_id),
        first.semantic.observation_cutoff,
        first.semantic.proposal_fingerprint,
        first.semantic.semantic_profile_fingerprint,
        first.retrieval.embedding_profile_fingerprint,
        first.semantic.serving_profile_fingerprint,
        first.semantic.suite_fingerprint,
        first.retrieval.target_name,
        first.retrieval.target_fingerprint,
        first.semantic.case_count,
        first.retrieval.case_count,
        first.stable_fingerprint,
        fingerprint,
    )


def _read(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        _fail()
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_RECEIPT_BYTES:
        _fail()
    return raw


def _write_exact(path: Path, raw: bytes) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
        _fail()
    if path.exists():
        if not path.is_file() or path.read_bytes() != raw:
            _fail()
        return
    temporary = path.parent / f".{path.name}.{token_hex(16)}.tmp"
    try:
        temporary.write_bytes(raw)
        temporary.chmod(0o600)
        if temporary.read_bytes() != raw:
            _fail()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_exact(path: Path, raw: bytes) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
        _fail()
    temporary = path.parent / f".{path.name}.{token_hex(16)}.tmp"
    try:
        temporary.write_bytes(raw)
        temporary.chmod(0o600)
        if temporary.read_bytes() != raw:
            _fail()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _runtime_record(schema_id: str, fields: dict[str, object]) -> bytes:
    document: dict[str, object] = {"schema_id": schema_id, "schema_version": 1, **fields}
    document["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(document))).hexdigest()
    )
    return canonicalize(checked_json_value(document))


def _runtime_parse(path: Path, schema_id: str) -> dict[str, JsonValue]:
    document = _document(_read(path), maximum=_MAX_RECEIPT_BYTES)
    if document.get("schema_id") != schema_id or document.get("schema_version") != 1:
        _fail()
    if not _fingerprinted(document):
        _fail()
    return document


def _profile_reader(raw: bytes, reference_type: ReferenceType, prefix: str) -> _ExactProfileReader:
    fingerprint = "sha256:" + sha256(raw).hexdigest()
    reference = ImmutableReference(
        reference_type, prefix + sha256(raw).hexdigest()[:48], fingerprint
    )
    return _ExactProfileReader(raw, reference)


@dataclass(frozen=True, slots=True)
class _LiveConfiguration:
    authority: _ExecutionAuthority
    semantic_profiles: SemanticProfileSet
    serving_profile: ServingCapabilityProfile
    semantic_runner: _BudgetedSemanticRunner
    embeddings: EmbeddingPort
    target: PineconeServingTargetStore
    token_counter: ExactTokenCounter
    authority_gate: _AuthorityGate


def _argument_path(value: object) -> Path:
    if not isinstance(value, Path):
        _fail()
    return value


def _state_root(arguments: argparse.Namespace, output_root: Path) -> Path:
    state_root = _argument_path(arguments.state_root)
    if (
        not state_root.is_absolute()
        or state_root.is_symlink()
        or not state_root.is_dir()
        or state_root != state_root.resolve()
        or output_root == state_root
        or output_root.is_relative_to(state_root)
        or state_root.is_relative_to(output_root)
        or S_IMODE(state_root.stat().st_mode) != _PRIVATE_DIRECTORY_MODE
    ):
        _fail()
    return state_root


def _preflight_plan(arguments: argparse.Namespace) -> bytes:
    """Derive the exact single-run effect plan without constructing a transport."""
    suite = _load_suite()
    semantic_raw = _read(_argument_path(arguments.semantic_profile))
    serving_raw = _read(_argument_path(arguments.serving_profile))
    tokenizer_raw = _read(_argument_path(arguments.tokenizer_resource))
    semantic_profiles = load_semantic_profile_set(
        _profile_reader(semantic_raw, ReferenceType.WORKFLOW_PROFILE, "wap_")
    )
    serving_profile = load_serving_capability_profile(
        _profile_reader(serving_raw, ReferenceType.CAPABILITY_PROFILE, "cap_")
    )
    model = AzureDeployment.from_credential_json(_read(_argument_path(arguments.model_credential)))
    embedding = AzureOpenAIConfig.from_credential_json(
        _read(_argument_path(arguments.embedding_credential))
    )
    pinecone = PineconeConfig.from_credential_json(
        _read(_argument_path(arguments.pinecone_credential))
    )
    output_root = _argument_path(arguments.output_root)
    state_root = _state_root(arguments, output_root)
    if (
        type(arguments.run_id) is not str
        or not arguments.run_id
        or type(arguments.observation_cutoff) is not str
        or type(arguments.proposal_fingerprint) is not str
        or not output_root.is_absolute()
        or output_root.is_symlink()
        or {profile.deployment_name for profile in semantic_profiles.profiles} != {model.deployment}
        or {profile.api_contract for profile in semantic_profiles.profiles} != {model.api_version}
        or embedding.deployment != serving_profile.embedding.deployment_name
        or embedding.api_version != serving_profile.embedding.api_contract
        or pinecone.project_id != serving_profile.pinecone_project_id
        or not pinecone.index.startswith(serving_profile.index_prefix)
    ):
        _fail()
    counter = ExactTokenCounter(
        semantic_profiles, serving_profile.embedding.tokenizer, tokenizer_raw
    )
    semantic_cases = _semantic_cases(suite, semantic_profiles)
    retrieval_cases = _retrieval_cases(suite, serving_profile.embedding, counter)
    planned: list[ProviderBudgetRequest] = []
    for case in semantic_cases:
        for request in case.requests:
            profile = next(
                item for item in semantic_profiles.profiles if item.profile_id == request.profile_id
            )
            bound = replace(
                request,
                request_id=semantic_evaluation_request_id(
                    arguments.run_id, case.case_id, request.phase
                ),
            )
            planned.append(
                ProviderBudgetRequest(
                    profile.profile_id,
                    counter.count(semantic_provider_input_text(bound)),
                    profile.max_output_tokens,
                )
            )
    budget = preflight_provider_budget(tuple(planned), semantic_profiles)
    retrieval_tokens = sum(
        counter.count(cast("str", value["query_text"]))
        + sum(
            counter.count(cast("str", record["text"]))
            for record in cast("list[dict[str, JsonValue]]", value["expected_records"])
        )
        for value in suite.retrieval.values()
    )
    upsert_batches = (
        len(retrieval_cases) + serving_profile.batch_size - 1
    ) // serving_profile.batch_size
    fetch_calls = (
        len(retrieval_cases) + serving_profile.readback_page_size - 1
    ) // serving_profile.readback_page_size
    describe_calls = _PINECONE_DESCRIBE_CALLS
    list_calls = 1
    stats_calls = 1
    provider_calls = (
        describe_calls
        + 1
        + upsert_batches
        + stats_calls
        + list_calls
        + fetch_calls
        + len(retrieval_cases)
    )
    document = {
        "allowed_operations": _OPERATIONS,
        "embedding_deployment": embedding.deployment,
        "max_cost_microunits": budget.worst_case_cost_microunits
        + serving_profile.embedding.cost_limit_microunits,
        "max_embedding_calls": len(retrieval_cases) * 2,
        "max_input_tokens": budget.total_input_tokens + retrieval_tokens,
        "max_pinecone_create_attempts": 1,
        "max_pinecone_describe_calls": describe_calls,
        "max_pinecone_fetch_calls": fetch_calls,
        "max_pinecone_full_readbacks": 1,
        "max_pinecone_list_calls": list_calls,
        "max_pinecone_queries": len(retrieval_cases),
        "max_pinecone_reconciliation_calls": sum(_TARGET_RECONCILIATION_COUNTS.values()),
        "max_pinecone_stats_calls": stats_calls,
        "max_pinecone_upsert_batches": upsert_batches,
        "max_semantic_calls": len(planned),
        "namespace": serving_profile.namespace,
        "observation_cutoff": arguments.observation_cutoff,
        "output_root": str(output_root),
        "pinecone_index": pinecone.index,
        "pinecone_project_id": pinecone.project_id,
        "proposal_fingerprint": arguments.proposal_fingerprint,
        "expected_pinecone_provider_calls": provider_calls,
        "run_id": arguments.run_id,
        "schema_id": "asklegal.hk-v1-provider-execution-plan/v1",
        "schema_version": 1,
        "semantic_deployment": model.deployment,
        "semantic_profile_fingerprint": semantic_profiles.fingerprint,
        "serving_profile_fingerprint": serving_profile.fingerprint,
        "state_root": str(state_root),
        "suite_fingerprint": suite.fingerprint,
        "tokenizer_resource_fingerprint": "sha256:" + sha256(tokenizer_raw).hexdigest(),
    }
    return _runtime_record(
        "asklegal.hk-v1-provider-execution-plan/v1",
        {
            key: value
            for key, value in document.items()
            if key not in {"schema_id", "schema_version"}
        },
    )


def _live_configuration(arguments: argparse.Namespace) -> _LiveConfiguration:
    """Validate every local byte before constructing any effect-capable adapter."""
    plan = _document(_preflight_plan(arguments), maximum=_MAX_RECEIPT_BYTES)
    _load_suite()
    if type(arguments.now) is not str or not arguments.now:
        _fail()
    authority = _execution_authority(_read(_argument_path(arguments.authority)), now=arguments.now)
    semantic_raw = _read(_argument_path(arguments.semantic_profile))
    serving_raw = _read(_argument_path(arguments.serving_profile))
    tokenizer_raw = _read(_argument_path(arguments.tokenizer_resource))
    model_credential = _read(_argument_path(arguments.model_credential))
    embedding_credential = _read(_argument_path(arguments.embedding_credential))
    pinecone_credential = _read(_argument_path(arguments.pinecone_credential))
    semantic_profiles = load_semantic_profile_set(
        _profile_reader(semantic_raw, ReferenceType.WORKFLOW_PROFILE, "wap_")
    )
    serving_profile = load_serving_capability_profile(
        _profile_reader(serving_raw, ReferenceType.CAPABILITY_PROFILE, "cap_")
    )
    model = AzureDeployment.from_credential_json(model_credential)
    embedding = AzureOpenAIConfig.from_credential_json(embedding_credential)
    pinecone = PineconeConfig.from_credential_json(pinecone_credential)
    deployments = {profile.deployment_name for profile in semantic_profiles.profiles}
    contracts = {profile.api_contract for profile in semantic_profiles.profiles}
    output_limits = {profile.max_output_tokens for profile in semantic_profiles.profiles}
    proxy_host = arguments.proxy_host
    proxy_port = arguments.proxy_port
    if (
        type(proxy_host) is not str
        or not proxy_host
        or type(proxy_port) is not int
        or not 1 <= proxy_port <= _MAX_PORT
        or deployments != {model.deployment}
        or contracts != {model.api_version}
        or len(output_limits) != 1
        or embedding.deployment != serving_profile.embedding.deployment_name
        or embedding.api_version != serving_profile.embedding.api_contract
        or pinecone.project_id != serving_profile.pinecone_project_id
        or not pinecone.index.startswith(serving_profile.index_prefix)
        or authority.run_id != arguments.run_id
        or authority.observation_cutoff != arguments.observation_cutoff
        or authority.proposal_fingerprint != arguments.proposal_fingerprint
        or authority.suite_fingerprint != _load_suite().fingerprint
        or authority.semantic_profile_fingerprint != semantic_profiles.fingerprint
        or authority.serving_profile_fingerprint != serving_profile.fingerprint
        or authority.tokenizer_resource_fingerprint != "sha256:" + sha256(tokenizer_raw).hexdigest()
        or authority.semantic_deployment != model.deployment
        or authority.embedding_deployment != embedding.deployment
        or authority.pinecone_project_id != pinecone.project_id
        or authority.pinecone_index != pinecone.index
        or authority.namespace != serving_profile.namespace
        or not isinstance(arguments.output_root, Path)
        or not arguments.output_root.is_absolute()
        or arguments.output_root.is_symlink()
        or authority.output_root != str(arguments.output_root)
        or authority.state_root != str(arguments.state_root)
        or authority.plan_fingerprint != plan.get("fingerprint")
        or any(
            getattr(authority, field) != plan.get(field)
            for field in (
                "max_cost_microunits",
                "max_embedding_calls",
                "max_input_tokens",
                "max_pinecone_create_attempts",
                "max_pinecone_describe_calls",
                "max_pinecone_fetch_calls",
                "max_pinecone_full_readbacks",
                "max_pinecone_list_calls",
                "max_pinecone_queries",
                "max_pinecone_reconciliation_calls",
                "max_pinecone_stats_calls",
                "max_pinecone_upsert_batches",
                "max_semantic_calls",
                "expected_pinecone_provider_calls",
            )
        )
    ):
        _fail()
    tokenizer_id = serving_profile.embedding.tokenizer
    counter = ExactTokenCounter(semantic_profiles, tokenizer_id, tokenizer_raw)
    suite = _load_suite()
    semantic_cases = _semantic_cases(suite, semantic_profiles)
    retrieval_cases = _retrieval_cases(suite, serving_profile.embedding, counter)
    planned: list[ProviderBudgetRequest] = []
    for case in semantic_cases:
        for request in case.requests:
            bound = replace(
                request,
                request_id=semantic_evaluation_request_id(
                    authority.run_id, case.case_id, request.phase
                ),
            )
            profile = next(
                item for item in semantic_profiles.profiles if item.profile_id == request.profile_id
            )
            planned.append(
                ProviderBudgetRequest(
                    profile.profile_id,
                    counter.count(semantic_provider_input_text(bound)),
                    profile.max_output_tokens,
                )
            )
    budget = preflight_provider_budget(tuple(planned), semantic_profiles)
    retrieval_tokens = sum(
        counter.count(cast("str", value["query_text"]))
        + sum(
            counter.count(cast("str", record["text"]))
            for record in cast("list[dict[str, JsonValue]]", value["expected_records"])
        )
        for value in suite.retrieval.values()
    )
    if (
        authority.max_semantic_calls != len(planned)
        or authority.max_embedding_calls != len(retrieval_cases) * 2
        or authority.max_pinecone_create_attempts != 1
        or authority.max_pinecone_describe_calls != _PINECONE_DESCRIBE_CALLS
        or authority.max_pinecone_fetch_calls
        != (len(retrieval_cases) + serving_profile.readback_page_size - 1)
        // serving_profile.readback_page_size
        or authority.max_pinecone_upsert_batches
        != (len(retrieval_cases) + serving_profile.batch_size - 1) // serving_profile.batch_size
        or authority.max_pinecone_full_readbacks != 1
        or authority.max_pinecone_list_calls != 1
        or authority.max_pinecone_queries != len(retrieval_cases)
        or authority.max_pinecone_reconciliation_calls
        != sum(_TARGET_RECONCILIATION_COUNTS.values())
        or authority.max_pinecone_stats_calls != 1
        or authority.expected_pinecone_provider_calls
        != authority.max_pinecone_describe_calls
        + authority.max_pinecone_create_attempts
        + authority.max_pinecone_upsert_batches
        + authority.max_pinecone_stats_calls
        + authority.max_pinecone_list_calls
        + authority.max_pinecone_fetch_calls
        + authority.max_pinecone_queries
        or budget.total_input_tokens + retrieval_tokens > authority.max_input_tokens
        or budget.worst_case_cost_microunits > authority.max_cost_microunits
        or authority.max_cost_microunits
        > semantic_profiles.cost_limit_microunits + serving_profile.embedding.cost_limit_microunits
    ):
        _fail()
    semantic_transport = BoundedModelTransport(
        proxy_host,
        proxy_port,
        semantic_profiles.retry_profile.timeout_seconds,
    )
    semantic_runner = AzureSemanticTaskRunner(
        model,
        semantic_transport,
        max_output_tokens=next(iter(output_limits)),
    )
    embedding_transport = ProviderTransport(
        proxy_host, proxy_port, serving_profile.provider_timeout_seconds
    )
    target_transport = ProviderTransport(
        proxy_host, proxy_port, serving_profile.target_timeout_seconds
    )
    gate = _AuthorityGate(
        authority.max_pinecone_create_attempts + authority.max_pinecone_upsert_batches,
        authority,
    )
    return _LiveConfiguration(
        authority,
        semantic_profiles,
        serving_profile,
        _BudgetedSemanticRunner(semantic_profiles, counter, semantic_runner),
        AzureOpenAIEmbeddingAdapter(
            embedding,
            embedding_transport,
            serving_profile_fingerprint=serving_profile.fingerprint,
        ),
        PineconeServingTargetStore(
            pinecone,
            target_transport,
            operation_gate=gate,
            provider_call_sink=gate.record_provider_call,
            namespace=serving_profile.namespace,
            page_size=serving_profile.readback_page_size,
        ),
        counter,
        gate,
    )


def _prepare_target(  # noqa: C901, PLR0912, PLR0915 - exact effect phase.
    configuration: _LiveConfiguration, suite: _GoldenSuite, run_id: str
) -> tuple[dict[str, JsonValue], TargetDefinition]:
    serving = configuration.serving_profile
    target = configuration.target
    target_name = target.target_name
    definition = TargetDefinition(
        target_name,
        target_state_fingerprint(
            target_name, serving.dimensions, serving.metric, serving.namespace
        ),
        serving.dimensions,
        serving.metric,
        serving.namespace,
    )
    create_operation = f"creating index {target_name}"
    configuration.authority_gate.select(create_operation)
    if configuration.authority_gate.is_complete(create_operation):
        if target.describe(target_name) != definition:
            _fail()
    elif configuration.authority_gate.is_in_flight(create_operation):
        if target.describe(target_name) != definition:
            _fail()
        configuration.authority_gate.complete(create_operation)
    else:
        target.create(definition)
        if target.describe(target_name) != definition:
            _fail()
        if configuration.authority_gate.is_in_flight(create_operation):
            configuration.authority_gate.complete(create_operation)
    records: list[TargetRecord] = []
    retained: list[dict[str, JsonValue]] = []
    for case_id, value in suite.retrieval.items():
        expected = cast("list[dict[str, JsonValue]]", value["expected_records"])[0]
        text = cast("str", expected["text"])
        token_count = configuration.token_counter.count(text)
        request = EmbeddingRequest(
            retrieval_setup_request_id(run_id, case_id),
            cast("str", expected["record_id"]),
            cast("str", expected["payload_fingerprint"]),
            text,
            "sha256:" + sha256(text.encode()).hexdigest(),
            token_count,
            serving.embedding.profile_id,
            "provider-admission-setup-" + run_id,
            len(records),
            "provider-admission-setup:" + cast("str", value["case_fingerprint"]),
        )
        embedded = configuration.embeddings.embed(serving.embedding, request)
        receipt = embedded.receipt
        if (
            receipt.request_id != request.request_id
            or receipt.result != "SUCCEEDED"
            or receipt.dimensions != serving.dimensions
            or receipt.input_tokens != token_count
            or receipt.provider_request_id in {"", "unreported"}
        ):
            _fail()
        record = TargetRecord(
            cast("str", expected["record_id"]),
            cast("str", expected["payload_fingerprint"]),
            embedded.values,
            text,
            cast("str", expected["country"]),
            cast("str", expected["jurisdiction"]),
            cast("str", expected["material_type"]),
            cast("str", expected["source"]),
            cast("str", expected["authority_note"]),
        )
        if serving_metadata_fingerprint(serving_metadata(record)) != record.content_fingerprint:
            _fail()
        records.append(record)
        retained.append(
            {
                "case_id": case_id,
                "embedding_receipt": {
                    "dimensions": receipt.dimensions,
                    "input_tokens": receipt.input_tokens,
                    "latency_milliseconds": receipt.latency_milliseconds,
                    "provider_request_id": receipt.provider_request_id,
                    "receipt_id": receipt.receipt_id,
                    "request_id": receipt.request_id,
                    "result": receipt.result,
                    "vector_fingerprint": receipt.vector_fingerprint,
                },
                "payload_fingerprint": record.content_fingerprint,
                "record_id": record.record_id,
            }
        )
    for start in range(0, len(records), serving.batch_size):
        batch = tuple(records[start : start + serving.batch_size])
        operation = f"upserting into {target_name} batch {start // serving.batch_size + 1}"
        configuration.authority_gate.select(operation)
        if configuration.authority_gate.is_complete(operation):
            continue
        if configuration.authority_gate.is_in_flight(operation):
            readback = {record.record_id: record for record in target.enumerate(target_name)}
            if any(readback.get(record.record_id) != record for record in batch):
                _fail()
            configuration.authority_gate.complete(operation)
            continue
        target.upsert_batch(target_name, batch)
        configuration.authority_gate.complete(operation)
    stats = target.describe_stats(target_name)
    if stats.get("totalVectorCount") != len(records):
        _fail()
    readback = target.enumerate(target_name)
    expected_readback = tuple(sorted(records, key=lambda item: item.record_id))
    if readback != expected_readback:
        _fail()
    inventory = [
        {
            "payload_fingerprint": item["payload_fingerprint"],
            "record_id": item["record_id"],
            "vector_fingerprint": cast("dict[str, JsonValue]", item["embedding_receipt"])[
                "vector_fingerprint"
            ],
        }
        for item in retained
    ]
    setup: dict[str, object] = {
        "readback_inventory_fingerprint": "sha256:"
        + sha256(canonicalize(checked_json_value(inventory))).hexdigest(),
        "record_count": len(retained),
        "records": retained,
        "run_id": run_id,
        "target_fingerprint": definition.state_fingerprint,
        "target_name": definition.name,
    }
    setup["fingerprint"] = "sha256:" + sha256(canonicalize(checked_json_value(setup))).hexdigest()
    return cast("dict[str, JsonValue]", checked_json_value(setup)), definition


def _execute(arguments: argparse.Namespace) -> tuple[bytes, bytes]:
    """Hold one process-exclusive authority lock across the complete resumable run."""
    configuration = _live_configuration(arguments)
    output_root = _argument_path(arguments.output_root)
    state_root = _state_root(arguments, output_root)
    lock_path = state_root / f"{configuration.authority.fingerprint}.lock"
    if lock_path.is_symlink():
        _fail()
    with lock_path.open("a+b") as lock:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _fail()
        return _execute_locked(arguments, configuration)


def _execute_locked(  # noqa: C901, PLR0912, PLR0915 - resumable closed phase machine.
    arguments: argparse.Namespace,
    configuration: _LiveConfiguration,
) -> tuple[bytes, bytes]:
    suite = _load_suite()
    output_root = _argument_path(arguments.output_root)
    if not output_root.is_absolute() or output_root.is_symlink() or not output_root.is_dir():
        _fail()
    state_root = _state_root(arguments, output_root)
    authority_path = _argument_path(arguments.authority)
    if not authority_path.is_absolute() or authority_path.parent == state_root:
        _fail()
    marker_path = state_root / f"{configuration.authority.fingerprint}.consumed.json"
    marker_fields = {
        "authority_fingerprint": configuration.authority.fingerprint,
        "output_root": str(output_root),
        "run_id": configuration.authority.run_id,
        "state_root": str(state_root),
    }
    reserved_marker = _runtime_record(
        "asklegal.hk-v1-provider-authority-consumption/v1",
        {**marker_fields, "status": "RESERVED"},
    )
    if marker_path.exists():
        marker = _runtime_parse(marker_path, "asklegal.hk-v1-provider-authority-consumption/v1")
        if any(marker.get(key) != value for key, value in marker_fields.items()) or marker.get(
            "status"
        ) not in {"RESERVED", "COMPLETE"}:
            _fail()
    else:
        _write_exact(marker_path, reserved_marker)
        marker = _document(reserved_marker, maximum=_MAX_RECEIPT_BYTES)
    state_path = output_root / "execution-state.json"
    if state_path.exists():
        state = _runtime_parse(state_path, "asklegal.hk-v1-provider-run-state/v1")
        if (
            state.get("authority_fingerprint") != configuration.authority.fingerprint
            or state.get("run_id") != configuration.authority.run_id
        ):
            _fail()
    else:
        if marker.get("status") == "COMPLETE":
            _fail()
        state = cast(
            "dict[str, JsonValue]",
            parse_json_bytes(
                _runtime_record(
                    "asklegal.hk-v1-provider-run-state/v1",
                    {
                        "authority_fingerprint": configuration.authority.fingerprint,
                        "retrieval_fingerprint": None,
                        "run_id": configuration.authority.run_id,
                        "semantic_fingerprint": None,
                        "status": "STARTED",
                    },
                ),
                max_bytes=_MAX_RECEIPT_BYTES,
            ),
        )
        _write_exact(state_path, canonicalize(state))
    effects_root = output_root / "effects"
    effects_root.mkdir(mode=0o700, exist_ok=True)
    configuration.authority_gate.bind(effects_root)
    configuration = replace(
        configuration,
        semantic_runner=configuration.semantic_runner,
        embeddings=_JournaledEmbeddingPort(effects_root, configuration.embeddings),
    )
    semantic_gate = SemanticTaskGate(
        _JournaledSemanticRunner(effects_root, configuration.semantic_runner)
    )
    semantic_path = output_root / "semantic-evaluation.json"
    retrieval_path = output_root / "retrieval-evaluation.json"
    target_setup_path = output_root / "target-setup.json"
    target_reconciliation_path = output_root / "target-reconciliation.json"
    if state.get("status") == "COMPLETE":
        semantic_raw = _read(semantic_path)
        retrieval_raw = _read(retrieval_path)
        parsed = _run(semantic_raw, retrieval_raw)
        retrieval_document = _document(retrieval_raw, maximum=_MAX_RECEIPT_BYTES)
        authority = configuration.authority
        if (
            parsed.run_id != authority.run_id
            or parsed.semantic.observation_cutoff != authority.observation_cutoff
            or parsed.semantic.proposal_fingerprint != authority.proposal_fingerprint
            or parsed.semantic.suite_fingerprint != authority.suite_fingerprint
            or parsed.semantic.semantic_profile_fingerprint
            != authority.semantic_profile_fingerprint
            or parsed.semantic.serving_profile_fingerprint != authority.serving_profile_fingerprint
            or parsed.retrieval.target_name != authority.pinecone_index
            or state.get("semantic_fingerprint") != parsed.semantic.fingerprint
            or state.get("retrieval_fingerprint") != parsed.retrieval.fingerprint
        ):
            _fail()
        _require_target_calls_match_authority(retrieval_document, authority)
        _replace_exact(
            marker_path,
            _runtime_record(
                "asklegal.hk-v1-provider-authority-consumption/v1",
                {**marker_fields, "status": "COMPLETE"},
            ),
        )
        return semantic_raw, retrieval_raw
    if retrieval_path.exists():
        retrieval_raw = _read(retrieval_path)
        retrieval_receipt = parse_live_retrieval_evaluation(retrieval_raw)
        retrieval_document = _document(retrieval_raw, maximum=_MAX_RECEIPT_BYTES)
        setup = cast("dict[str, JsonValue]", retrieval_document["target_setup"])
        target = TargetDefinition(
            retrieval_receipt.target_name,
            retrieval_receipt.target_fingerprint,
            configuration.serving_profile.dimensions,
            configuration.serving_profile.metric,
            configuration.serving_profile.namespace,
        )
    elif target_setup_path.exists():
        setup = _document(_read(target_setup_path), maximum=_MAX_RECEIPT_BYTES)
        if (
            not _fingerprinted(setup)
            or setup.get("run_id") != configuration.authority.run_id
            or type(setup.get("target_name")) is not str
            or type(setup.get("target_fingerprint")) is not str
            or not isinstance(setup.get("records"), list)
        ):
            _fail()
        target = TargetDefinition(
            cast("str", setup.get("target_name")),
            cast("str", setup.get("target_fingerprint")),
            configuration.serving_profile.dimensions,
            configuration.serving_profile.metric,
            configuration.serving_profile.namespace,
        )
        if target_reconciliation_path.exists():
            reconciliation = _runtime_parse(
                target_reconciliation_path,
                "asklegal.hk-v1-provider-target-reconciliation/v1",
            )
            if (
                reconciliation.get("authority_fingerprint") != configuration.authority.fingerprint
                or reconciliation.get("run_id") != configuration.authority.run_id
                or reconciliation.get("setup_fingerprint") != setup.get("fingerprint")
                or reconciliation.get("target_name") != target.name
            ):
                _fail()
        else:
            configuration.authority_gate.select_call_class("RECONCILIATION")
            try:
                described = configuration.target.describe(configuration.target.target_name)
                retained = {
                    cast("str", item["record_id"]): item
                    for item in cast("list[dict[str, JsonValue]]", setup["records"])
                }
                readback = configuration.target.enumerate(target.name)
            finally:
                configuration.authority_gate.select_call_class("EVALUATION")
            if (
                described != target
                or set(retained) != {record.record_id for record in readback}
                or any(
                    retained[record.record_id].get("payload_fingerprint")
                    != record.content_fingerprint
                    or cast(
                        "dict[str, JsonValue]", retained[record.record_id]["embedding_receipt"]
                    ).get("vector_fingerprint")
                    != live_vector_fingerprint(record.vector)
                    for record in readback
                )
            ):
                _fail()
            reconciliation_calls = [
                call
                for call in configuration.authority_gate.provider_calls()
                if call.get("call_class") == "RECONCILIATION"
            ]
            reconciliation_counts: dict[str, int] = {}
            for call in reconciliation_calls:
                operation = cast("str", call.get("operation"))
                reconciliation_counts[operation] = reconciliation_counts.get(operation, 0) + 1
            if reconciliation_counts != _TARGET_RECONCILIATION_COUNTS:
                _fail()
            _write_exact(
                target_reconciliation_path,
                _runtime_record(
                    "asklegal.hk-v1-provider-target-reconciliation/v1",
                    {
                        "authority_fingerprint": configuration.authority.fingerprint,
                        "provider_call_fingerprints": sorted(
                            cast("str", call["fingerprint"]) for call in reconciliation_calls
                        ),
                        "run_id": configuration.authority.run_id,
                        "setup_fingerprint": setup["fingerprint"],
                        "target_name": target.name,
                    },
                ),
            )
    else:
        setup, target = _prepare_target(configuration, suite, configuration.authority.run_id)
        _write_exact(target_setup_path, canonicalize(setup))
    serving = configuration.serving_profile
    if (
        target.dimensions != serving.dimensions
        or target.metric != serving.metric
        or target.namespace != serving.namespace
    ):
        _fail()
    if any(
        type(value) is not str or not value
        for value in (arguments.observation_cutoff, arguments.proposal_fingerprint, arguments.now)
    ):
        _fail()
    if semantic_path.exists():
        semantic_raw = _read(semantic_path)
        parse_live_semantic_evaluation(semantic_raw)
    else:
        semantic_raw = run_live_semantic_evaluation(
            run_id=configuration.authority.run_id,
            observation_cutoff=arguments.observation_cutoff,
            proposal_fingerprint=arguments.proposal_fingerprint,
            serving_profile_fingerprint=serving.fingerprint,
            suite_fingerprint=suite.fingerprint,
            profile_set=configuration.semantic_profiles,
            cases=_semantic_cases(suite, configuration.semantic_profiles),
            gate=semantic_gate,
            environment=configuration.semantic_profiles.environment,
            now=arguments.now,
        )
        _write_exact(semantic_path, semantic_raw)
    if retrieval_path.exists():
        retrieval_raw = _read(retrieval_path)
    else:
        retrieval_raw = run_live_retrieval_evaluation(
            run_id=configuration.authority.run_id,
            observation_cutoff=arguments.observation_cutoff,
            proposal_fingerprint=arguments.proposal_fingerprint,
            serving_profile_fingerprint=serving.fingerprint,
            suite_fingerprint=suite.fingerprint,
            target_name=target.name,
            target_fingerprint=target.state_fingerprint,
            target_setup=setup,
            profile=serving.embedding,
            cases=_retrieval_cases(suite, serving.embedding, configuration.token_counter),
            embeddings=configuration.embeddings,
            target=configuration.target,
            provider_call_reader=configuration.authority_gate.provider_calls,
        )
        _write_exact(retrieval_path, retrieval_raw)
    semantic_receipt = parse_live_semantic_evaluation(semantic_raw)
    retrieval_receipt = parse_live_retrieval_evaluation(retrieval_raw)
    retrieval_document = _document(retrieval_raw, maximum=_MAX_RECEIPT_BYTES)
    _require_target_calls_match_authority(retrieval_document, configuration.authority)
    complete = _runtime_record(
        "asklegal.hk-v1-provider-run-state/v1",
        {
            "authority_fingerprint": configuration.authority.fingerprint,
            "retrieval_fingerprint": retrieval_receipt.fingerprint,
            "run_id": configuration.authority.run_id,
            "semantic_fingerprint": semantic_receipt.fingerprint,
            "status": "COMPLETE",
        },
    )
    _replace_exact(state_path, complete)
    _replace_exact(
        marker_path,
        _runtime_record(
            "asklegal.hk-v1-provider-authority-consumption/v1",
            {**marker_fields, "status": "COMPLETE"},
        ),
    )
    return semantic_raw, retrieval_raw


def main(argv: list[str] | None = None) -> int:
    """Preflight, execute, or issue a retained two-run provider report."""
    parser = argparse.ArgumentParser(description="Execute or issue exact HK V1 provider evidence")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    parser.add_argument("--semantic-run-1", type=Path)
    parser.add_argument("--retrieval-run-1", type=Path)
    parser.add_argument("--semantic-run-2", type=Path)
    parser.add_argument("--retrieval-run-2", type=Path)
    parser.add_argument("--semantic-profile", type=Path)
    parser.add_argument("--serving-profile", type=Path)
    parser.add_argument("--tokenizer-resource", type=Path)
    parser.add_argument("--model-credential", type=Path)
    parser.add_argument("--embedding-credential", type=Path)
    parser.add_argument("--pinecone-credential", type=Path)
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--proxy-host")
    parser.add_argument("--proxy-port", type=int)
    parser.add_argument("--observation-cutoff")
    parser.add_argument("--proposal-fingerprint")
    parser.add_argument("--now")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.preflight:
            plan = _preflight_plan(arguments)
            _write_exact(_argument_path(arguments.plan_output), plan)
            plan_document = _document(plan, maximum=_MAX_RECEIPT_BYTES)
            sys.stdout.write(
                "PREFLIGHT_PASSED_NO_EFFECTS "
                + cast("str", plan_document["fingerprint"])
                + f" semantic_calls={plan_document['max_semantic_calls']}"
                + f" embedding_calls={plan_document['max_embedding_calls']}"
                + f" pinecone_create_attempts={plan_document['max_pinecone_create_attempts']}"
                + f" pinecone_describe_calls={plan_document['max_pinecone_describe_calls']}"
                + f" pinecone_fetch_calls={plan_document['max_pinecone_fetch_calls']}"
                + f" pinecone_upsert_batches={plan_document['max_pinecone_upsert_batches']}"
                + f" pinecone_full_readbacks={plan_document['max_pinecone_full_readbacks']}"
                + f" pinecone_list_calls={plan_document['max_pinecone_list_calls']}"
                + f" pinecone_queries={plan_document['max_pinecone_queries']}"
                + " pinecone_reconciliation_calls="
                + f"{plan_document['max_pinecone_reconciliation_calls']}"
                + f" pinecone_stats_calls={plan_document['max_pinecone_stats_calls']}"
                + f" pinecone_provider_calls={plan_document['expected_pinecone_provider_calls']}"
                + f" max_input_tokens={plan_document['max_input_tokens']}"
                + f" max_cost_microunits={plan_document['max_cost_microunits']}\n"
            )
            return 0
        if arguments.execute:
            semantic_raw, retrieval_raw = _execute(arguments)
            parsed = _run(semantic_raw, retrieval_raw)
            sys.stdout.write("EXECUTED " + parsed.run_id + "\n")
            return 0
        report = issue_provider_admission_evidence(
            semantic_run_1=_read(_argument_path(arguments.semantic_run_1)),
            retrieval_run_1=_read(_argument_path(arguments.retrieval_run_1)),
            semantic_run_2=_read(_argument_path(arguments.semantic_run_2)),
            retrieval_run_2=_read(_argument_path(arguments.retrieval_run_2)),
        )
        _write_exact(_argument_path(arguments.output), report)
    except (
        OSError,
        OutcomeUnknown,
        ProcessingError,
        PromotionError,
        ProviderAdmissionError,
        ServingProfileError,
        TypeError,
        ValueError,
    ):
        sys.stderr.write("FAIL PROVIDER_ADMISSION_INVALID\n")
        return 2
    sys.stdout.write("ADMITTED " + parse_provider_admission_evidence(report).fingerprint + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
